"""rbx_inspect.py — DEEP CHECKS on every part, measured (no taste, no guessing). Called by Asset.build().

Why: a model can pass every global gate (manifold, silhouette IoU, score) and still be wrong part by part — a
charging handle floating in a port, springs where the manual says there are none, a pin spanning an opening in
mid-air, an open tube you can see into, rings that do not clamp the rail. These checks find those, by number:

  visibility    ray-casts from 26 directions: how much of each part can be SEEN. `internal()` parts must be
                hidden; the design spec's `visible` (exterior / through / hidden) is enforced per part.
  support       fasteners (pins, screws, rods, rivets, axles) must pass THROUGH material along their length —
                a stretch in open air is reported in mm, with where it is.
  clear paths   a.clear_path(...) — a bore, a sight line, a duct, a chimney: nothing may block it.
  spec parts    refs/<name>.spec.json "parts": what each part IS (from the manual / references), what it attaches
                to (must touch), its visibility. Model parts the spec does not describe are "undocumented".
  part review   every part family gets a close-up tile (in context + isolated) and an entry in
                assets/models/<asset>.parts.md that the kit keeps in sync: a part whose geometry changed goes back
                to TODO. hero/aaa builds FAIL while any entry is TODO or says `verdict: fix`.
"""

import hashlib
import json
import math
import os
import re
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

import rbx_critic

FASTENER_WORDS = {"pin", "screw", "rivet", "rod", "axle", "dowel", "stud", "nail", "bolthead"}
# what must sit in a hole / cavity of its host (fastener_seat): fasteners, nuts and springs
SEATED_WORDS = {"pin", "screw", "rivet", "dowel", "stud", "nail", "bolthead", "nut", "spring"}
DIRS = [Vector((x, y, z)).normalized() for x in (-1, 0, 1) for y in (-1, 0, 1) for z in (-1, 0, 1) if (x, y, z) != (0, 0, 0)]
# Blender space (Z up, -Y front after BL_FROM_RBX) direction names, for messages
_DIR_NAMES = {(1, 0, 0): "right", (-1, 0, 0): "left", (0, 0, 1): "top", (0, 0, -1): "below", (0, -1, 0): "front",
              (0, 1, 0): "back"}


def base(name):
    return name.split("~")[0]


def family(name):
    """Rivet556 / Rivet579 -> Rivet; BipodLeg-1 / BipodLeg1 -> BipodLeg; Case0..4 -> Case."""
    n = re.sub(r"[-+]?\d+$", "", base(name))
    return n or base(name)


def _words(name):
    return {w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", base(name))}


def _dir_name(d):
    k = tuple(int(round(v)) for v in d)
    names = [_DIR_NAMES[(k[0], 0, 0)] if k[0] else None, _DIR_NAMES[(0, k[1], 0)] if k[1] else None,
             _DIR_NAMES[(0, 0, k[2])] if k[2] else None]
    return "-".join(n for n in names if n)


class World:
    """every part's world-space triangles in one BVH, with face -> part ownership."""

    def __init__(self, parts):
        self.parts = [(o, g) for o, g in parts if o.type == "MESH" and len(o.data.polygons)]
        verts, polys, self.owner = [], [], []
        self.area = []
        for k, (o, _g) in enumerate(self.parts):
            mw = o.matrix_world
            b = len(verts)
            verts += [mw @ v.co for v in o.data.vertices]
            o.data.calc_loop_triangles()
            for tri in o.data.loop_triangles:  # the mesh's OWN triangulation (samples use the same one)
                polys.append(tuple(i + b for i in tri.vertices))
                self.owner.append(k)
        self.tree = BVHTree.FromPolygons(verts, polys, all_triangles=True, epsilon=0.0)
        lo = Vector([min(v[i] for v in verts) for i in range(3)]) if verts else Vector()
        hi = Vector([max(v[i] for v in verts) for i in range(3)]) if verts else Vector()
        self.lo, self.hi = lo, hi
        self.diag = max((hi - lo).length, 1e-6)
        self.index = {o.name: k for k, (o, _g) in enumerate(self.parts)}

    def embedded(self, k, n=160):
        """how much of part k's VOLUME lies inside OTHER parts' solids — a screw with no hole, a spring with no
        cavity: -> (the share of points sampled inside k that are inside another part, that part's name or None)"""
        import random  # noqa: PLC0415

        trees = self.__dict__.setdefault("_part_trees", {})

        def tree(j):
            if j not in trees:
                trees[j] = part_tree(self.parts[j][0])
            return trees[j]

        def box(j):
            o = self.parts[j][0]
            cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
            return (Vector([min(c[i] for c in cs) for i in range(3)]), Vector([max(c[i] for c in cs) for i in range(3)]))

        lo, hi = box(k)
        rng = random.Random(7)
        pts, tries = [], 0
        while len(pts) < n and tries < n * 25:
            tries += 1
            p = Vector([lo[i] + (hi[i] - lo[i]) * rng.random() for i in range(3)])
            if inside_tree(tree(k), p):
                pts.append(p)
        if len(pts) < 12:
            return 0.0, None
        near = []
        for j in range(len(self.parts)):
            if j == k:
                continue
            jl, jh = box(j)
            if all(jl[i] <= hi[i] and lo[i] <= jh[i] for i in range(3)):
                near.append((j, jl, jh))
        hits = {}
        for p in pts:
            for j, jl, jh in near:
                if all(jl[i] <= p[i] <= jh[i] for i in range(3)) and inside_tree(tree(j), p):
                    hits[j] = hits.get(j, 0) + 1
                    break
        if not hits:
            return 0.0, None
        host = max(hits, key=hits.get)
        return sum(hits.values()) / len(pts), self.parts[host][0].name

    def samples(self, k, n=140):
        """area-weighted surface samples of part k: [(point, normal, weight)] in world space."""
        o = self.parts[k][0]
        mw = o.matrix_world
        nm = mw.to_3x3().inverted_safe().transposed()
        faces = [(p.area, mw @ p.center, (nm @ p.normal).normalized()) for p in o.data.polygons if p.area > 0]
        if not faces:
            return []
        total = sum(f[0] for f in faces)
        if len(faces) <= n:
            return [(c, nrm, a / total) for a, c, nrm in faces]
        # deterministic stratified pick by cumulative area
        out, acc, step, t = [], 0.0, total / n, total / n / 2
        for a, c, nrm in faces:
            acc += a
            while t < acc and len(out) < n:
                out.append((c, nrm, 1.0 / n))
                t += step
        return out

    def visibility(self, k):
        """(visible area fraction 0..1, the directions it is seen from most)."""
        eps = self.diag * 2e-5
        seen, total, by_dir = 0.0, 0.0, {}
        for c, nrm, w in self.samples(k):
            total += w
            for d in DIRS:
                if nrm.dot(d) <= 0.05:
                    continue
                hit = self.tree.ray_cast(c + nrm * eps + d * eps, d, self.diag * 3)
                if hit[0] is None:
                    seen += w
                    key = _dir_name(d)
                    by_dir[key] = by_dir.get(key, 0.0) + w
                    break
        frac = seen / total if total else 0.0
        top = sorted(by_dir, key=lambda x: -by_dir[x])[:3]
        return frac, top

    def inside(self, p, k):
        """is point p inside another part's solid? Parity of each part's surface crossings along three rays,
        majority vote (a single ray is fooled by grazing boolean faces)."""
        votes = {}
        for d in (Vector((0.5774, 0.5832, 0.5714)).normalized(), Vector((-0.6123, 0.4871, -0.6229)).normalized(),
                  Vector((0.3011, -0.8934, 0.3335)).normalized()):
            counts, start = {}, p
            for _ in range(64):
                hit = self.tree.ray_cast(start, d, self.diag * 3)
                if hit[0] is None:
                    break
                o = self.owner[hit[2]]
                if o != k:
                    counts[o] = counts.get(o, 0) + 1
                start = hit[0] + d * (self.diag * 1e-6)
            for o, c in counts.items():
                if c % 2:
                    votes[o] = votes.get(o, 0) + 1
        return any(v >= 2 for v in votes.values())

    def support(self, k):
        """a fastener's longest stretch in open air (world units), and where along it (0..1)."""
        o = self.parts[k][0]
        mw = o.matrix_world
        pts = np.array([tuple(mw @ v.co) for v in o.data.vertices])
        if len(pts) < 4:
            return 0.0, None, 0.0
        c = pts.mean(0)
        u, sv, vt = np.linalg.svd(pts - c, full_matrices=False)
        ax = vt[0]
        t = (pts - c) @ ax
        t0, t1 = float(t.min()), float(t.max())
        radial = np.linalg.norm((pts - c) - np.outer(t, ax), axis=1)
        r = float(np.percentile(radial, 50)) or 1e-4
        length = t1 - t0
        if length < 2.5 * 2 * r:
            return 0.0, None, length  # not elongated: not a fastener shape
        a = Vector(tuple(ax))
        # two directions perpendicular to the axis
        p1 = a.orthogonal().normalized()
        p2 = a.cross(p1).normalized()
        n = 28
        ok = []
        for i in range(n):
            tt = t0 + r + (length - 2 * r) * (i + 0.5) / n
            p = Vector(tuple(c + ax * tt))
            found = self.inside(p, k)  # embedded in another part's solid: supported
            for j in range(0 if found else 10):
                ang = j / 10 * 2 * math.pi
                d = (p1 * math.cos(ang) + p2 * math.sin(ang)).normalized()
                start = p + d * (r * 1.08)
                reach = r * 1.6 + self.diag * 0.002
                hit = self.tree.ray_cast(start, d, reach)
                hops = 0
                while hit[0] is not None and self.owner[hit[2]] == k and hops < 3:
                    start = hit[0] + d * (self.diag * 1e-5)
                    reach -= hit[3]
                    hit = self.tree.ray_cast(start, d, max(reach, 1e-6))
                    hops += 1
                if hit[0] is not None and self.owner[hit[2]] != k:
                    found = True
                    break
            ok.append(found)
        # longest unsupported run
        best, cur, best_end = 0, 0, 0
        for i, v in enumerate(ok):
            cur = 0 if v else cur + 1
            if cur > best:
                best, best_end = cur, i
        span = best * (length - 2 * r) / n
        where = (best_end + 0.5 - best / 2) / n if best else None
        return span, where, length

    def clear(self, p0, p1, radius):
        """rays from p0 to p1 (centre + 6 around at 0.8 radius): -> [(part name, distance along)] that block."""
        d = p1 - p0
        dist = d.length
        if dist < 1e-9:
            return []
        d = d / dist
        q1 = d.orthogonal().normalized()
        q2 = d.cross(q1).normalized()
        offsets = [Vector()] + [(q1 * math.cos(a) + q2 * math.sin(a)) * radius * 0.8 for a in
                                (i / 6 * 2 * math.pi for i in range(6))]
        blocks = []
        for off in offsets:
            hit = self.tree.ray_cast(p0 + off, d, dist)
            if hit[0] is not None:
                blocks.append((base(self.parts[self.owner[hit[2]]][0].name), round(hit[3], 4)))
        return blocks


def dense_clusters(items, r, need, at=lambda x: x):
    """the items with at least `need` items (themselves included) within r of them. Exact, through a spatial hash
    (cells of size r: every neighbour within r is in the 27 cells around): a slide buried in its frame gives tens
    of thousands of points, and comparing all pairs took minutes (measured: 267 s for one selftest fixture)."""
    pos = [at(x) for x in items]

    def cell(p):
        return math.floor(p[0] / r), math.floor(p[1] / r), math.floor(p[2] / r)

    cells = {}
    for i, p in enumerate(pos):
        cells.setdefault(cell(p), []).append(i)
    out = []
    for i, p in enumerate(pos):
        cx, cy, cz = cell(p)
        k = 0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for j in cells.get((cx + dx, cy + dy, cz + dz), ()):
                        if (p - pos[j]).length < r:
                            k += 1
                    if k >= need:
                        break
                if k >= need:
                    break
            if k >= need:
                break
        if k >= need:
            out.append(items[i])
    return out


_RAYS5 = [Vector(v).normalized() for v in ((0.5774, 0.5832, 0.5714), (-0.6123, 0.4871, -0.6229),
                                          (0.3011, -0.8934, 0.3335), (0.8121, 0.1532, -0.5631), (-0.2417, -0.4466, 0.8615))]


def part_tree(obj):
    """a BVH tree of ONE part's own faces, world space"""
    mw = obj.matrix_world
    me = obj.data
    return BVHTree.FromPolygons([mw @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])


def inside_tree(tree, q):
    """q inside the closed part `tree` holds (its own faces only — a part_tree): parity along five rays, majority.
    On the whole model's tree a face of ANOTHER part lying exactly on this one's (a plate seated on its host) is the
    one hit, and stepping past it skips the host's face too: the parity flips"""
    odd = 0
    for d in _RAYS5:
        n, start = 0, q
        for _ in range(512):
            h = tree.ray_cast(start, d)
            if h[0] is None:
                break
            n += 1
            start = h[0] + d * 1e-6
        odd += n % 2
    return odd >= 3


DENSE_CAP = 60000   # samples a part at most: a grown ivy's 4,600 leaves sampled every 1.8 mm ran Blender out of memory


def dense_samples(obj, spacing, cap=DENSE_CAP):
    """[(point, normal)] over obj's surface, ~one per spacing^2 (every triangle gets at least one), world space — at
    most ~`cap`: a huge surface is sampled on an even stride of its triangles (every region still seen)."""
    mw = obj.matrix_world
    nm = mw.to_3x3().inverted_safe().transposed()
    me = obj.data
    me.calc_loop_triangles()
    vs = [mw @ v.co for v in me.vertices]
    out = []
    tris = me.loop_triangles
    n_tris = len(tris)
    stride = 1
    if n_tris > cap // 2:
        area = sum(t.area for t in tris) * (mw.median_scale ** 2)
        est = max(n_tris, area / max(spacing * spacing, 1e-12) * 2)
        stride = max(1, int(math.ceil(est / cap)))
    for ti in range(0, n_tris, stride):
        tri = tris[ti]
        if stride > 1:   # (a sparse sample: one point a triangle, the stride covers the surface)
            a, b, c = (vs[i] for i in tri.vertices)
            out.append(((a + b + c) / 3, (nm @ tri.normal).normalized()))
            continue
        a, b, c = (vs[i] for i in tri.vertices)
        n = (nm @ tri.normal).normalized()
        area = ((b - a).cross(c - a)).length / 2
        k = max(1, int(math.sqrt(max(area / (spacing * spacing), 1) * 2)))
        for i in range(k):
            for j in range(k - i):
                u, v = (i + 1 / 3) / k, (j + 1 / 3) / k
                if u + v < 1:
                    out.append((a + (b - a) * u + (c - a) * v, n))
    return out


def _rbx(p):
    """Blender world -> Roblox space (x right, y up, z back)"""
    return (round(p.x, 3), round(p.z, 3), round(-p.y, 3))


_FACING_BL = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 0, 1), "-Y": (0, 0, -1), "+Z": (0, -1, 0), "-Z": (0, 1, 0)}


def _mm(asset, studs):
    mmps = getattr(asset, "mm_per_stud", None)
    if not mmps:
        return f"{studs:.3f} studs"
    v = studs * mmps
    return f"{v:.1f} mm" if v < 10 else f"{v:.0f} mm"  # a 0.5 mm skin is not "0 mm"


def _load_spec(asset):
    if getattr(asset, "spec_inline", None):
        return asset.spec_inline
    if not getattr(asset, "spec_name", None):
        return None
    from rbx import REPO  # noqa: PLC0415

    path = os.path.join(REPO, "refs", f"{asset.spec_name}.spec.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _spec_match(spec_name, part_name):
    b = base(part_name)
    return b == spec_name or family(b) == spec_name or (spec_name.endswith("*") and b.startswith(spec_name[:-1]))


def ref_sizes(asset, w, linked, views_path):
    """-> (rows, note). Each reference part linked from the spec ({ref: [spec names]}) beside the model's parts that
    match: both as SIDE-VIEW boxes in mm of what is seen, the length measured from the back and the height from the
    foot (the frame kit refs views measures the traced parts in). The two frames are lined up first by the median offset of all the
    linked parts: a common shift is not an error; a part too long, too short or out of place is. A row is off when
    its length, height or place differs by more than 5% of its size or 3 mm, whichever is bigger (a traced
    picture is good to a few pixels)."""
    mmps = getattr(asset, "mm_per_stud", None)
    if not mmps:
        return [], "no scale — a.real_scale(mm_per_stud) gives the model millimetres to measure against"
    if not os.path.isfile(views_path):
        return [], f"no {os.path.basename(views_path)} — lune run kit refs views {asset.spec_name or '<asset>'}"
    with open(views_path, encoding="utf-8") as fh:
        ref = json.load(fh).get("parts") or {}
    # Blender world: Roblox z (back) is -y, Roblox y (up) is z. The back = the largest Roblox z; the foot = the
    # lowest point
    back, foot = -w.lo.y, w.lo.z
    # what the reference shows of a part is what is SEEN of it from the side (SAM masks what is visible): a grip
    # whose top is buried in the receiver is measured where it shows, not by its whole box. Rays along X from both
    # flanks, every 2 mm: each part's extent where it is the first surface hit
    step = max(2.0 / mmps, 1e-4)
    boxes = {}
    ny = int((w.hi.y - w.lo.y) / step) + 1
    nz = int((w.hi.z - w.lo.z) / step) + 1
    span = (w.hi.x - w.lo.x) + 2.0
    for x0, dx in ((w.lo.x - 1.0, 1.0), (w.hi.x + 1.0, -1.0)):
        d = Vector((dx, 0.0, 0.0))
        for i in range(ny):
            by = w.lo.y + i * step
            for j in range(nz):
                bz = w.lo.z + j * step
                hit = w.tree.ray_cast(Vector((x0, by, bz)), d, span)
                if hit[0] is None:
                    continue
                nm = w.parts[w.owner[hit[2]]][0].name
                b = boxes.get(nm)
                boxes[nm] = ((-by, -by, bz, bz) if b is None else
                             (min(b[0], -by), max(b[1], -by), min(b[2], bz), max(b[3], bz)))
    rows = []
    for name, specs in linked.items():
        side = (ref.get(name) or {}).get("side")
        if not side:
            rows.append({"ref": name, "parts": specs, "note": f'"{name}" is not a traced part of the side view'})
            continue
        q = side.get("quality") or {}
        doubt = list(q.get("why") or []) if q and not q.get("ok", True) else []
        hit = [nm for nm in boxes if any(_spec_match(sn, base(nm)) for sn in specs)]
        if not hit:
            if doubt:  # (spec_parts names the missing part; the doubt is still said)
                rows.append({"ref": name, "parts": specs, "doubtful": doubt, "note_only": True})
            continue
        half = step / 2  # (an edge lies between the last ray that hit and the first that missed: half a step out)
        z0 = min(boxes[nm][0] for nm in hit) - half
        z1 = max(boxes[nm][1] for nm in hit) + half
        y0 = min(boxes[nm][2] for nm in hit) - half
        y1 = max(boxes[nm][3] for nm in hit) + half
        rows.append({"ref": name, "parts": specs, "ref_along": side["along_mm"], "ref_across": side["across_mm"],
                     "along": [(back - z1) * mmps, (back - z0) * mmps], "across": [(y0 - foot) * mmps,
                                                                                   (y1 - foot) * mmps]})
        if doubt:
            rows[-1]["doubtful"] = doubt  # kit trace judged this mask doubtful: its size may be the mask's mistake
    full = [r for r in rows if "along" in r]
    if full:
        mid = lambda a: (a[0] + a[1]) / 2  # noqa: E731
        shift = [sorted(mid(r["ref_" + k]) - mid(r[k]) for r in full)[len(full) // 2] for k in ("along", "across")]
        for r in full:
            off = []
            for k, sh in zip(("along", "across"), shift):
                got, want = r[k], r["ref_" + k]
                size_g, size_w = got[1] - got[0], want[1] - want[0]
                tol = max(0.05 * size_w, 3.0)
                off.append((size_g - size_w, mid(got) + sh - mid(want), tol))
            r["size_mm"] = [round(r["along"][1] - r["along"][0], 1), round(r["across"][1] - r["across"][0], 1)]
            r["ref_size_mm"] = [round(r["ref_along"][1] - r["ref_along"][0], 1),
                                round(r["ref_across"][1] - r["ref_across"][0], 1)]
            r["size_off_mm"] = [round(d, 1) for d, _p, _t in off]
            r["place_off_mm"] = [round(pz, 1) for _d, pz, _t in off]
            r["ok"] = all(abs(d) <= t and abs(pz) <= t for d, pz, t in off)
            r["along"] = [round(x, 1) for x in r["along"]]
            r["across"] = [round(x, 1) for x in r["across"]]
        return rows, f"frames lined up by {shift[0]:+.1f} mm along, {shift[1]:+.1f} mm up (the median of {len(full)} parts)"
    return rows, "no linked part is modelled yet"


def _ref_row_text(r):
    """'wolf: 193 x 81 mm in the reference, the model 180 x 75 (length -13 mm, height -6 mm; 4 mm too far back)'"""
    (dl, dh), (pa, pu) = r["size_off_mm"], r["place_off_mm"]
    bits = [f"length {dl:+.0f} mm" if abs(dl) >= 1 else "", f"height {dh:+.0f} mm" if abs(dh) >= 1 else ""]
    if abs(pa) >= 1:
        bits.append(f"{abs(pa):.0f} mm too far {'forward' if pa > 0 else 'back'}")
    if abs(pu) >= 1:
        bits.append(f"{abs(pu):.0f} mm too {'high' if pu > 0 else 'low'}")
    return (f"{r['ref']}: {r['ref_size_mm'][0]:.0f} x {r['ref_size_mm'][1]:.0f} mm in the reference, the model "
            f"{r['size_mm'][0]:.0f} x {r['size_mm'][1]:.0f} ({', '.join(b for b in bits if b) or 'within a mm'})")


def run(asset, parts, internal, mirrored_to_rbx):
    """-> (checks, facts). parts: [(obj, group)] before join (cutters already gone, floaters excluded)."""
    w = World(parts)
    checks, facts = [], {}
    names = [o.name for o, _g in w.parts]
    strict = "error" if asset.quality in ("hero", "aaa") else "warn"

    # ---------------------------------------------------------------- visibility (internal parts, spec)
    spec = _load_spec(asset)
    want_vis = {}
    for sp in (spec or {}).get("parts", []):
        if sp.get("visible"):
            for nm in names:
                if _spec_match(sp["name"], nm):
                    want_vis[nm] = sp["visible"]
    vis = {}
    for k, nm in enumerate(names):
        if base(nm) in internal or nm in want_vis:
            vis[nm] = w.visibility(k)
    shown = []
    for nm, (frac, dirs) in vis.items():
        want = want_vis.get(nm, "hidden" if base(nm) in internal else None)
        if want == "hidden" and frac > 0.04:
            shown.append(f"{base(nm)} {frac:.0%} visible (from {', '.join(dirs)})")
        elif want == "exterior" and frac < 0.02:  # a flush pin shows only its ends (~5%): seen is seen
            shown.append(f"{base(nm)} only {frac:.0%} visible but the spec says exterior")
    facts["visibility"] = {base(k): round(v[0], 3) for k, v in vis.items()}
    checks.append(rbx_critic._check(
        "part_visibility", not shown, shown[:6] or "every hidden part hidden, every exterior part seen", "as designed",
        "parts seen where they should not be (or hidden where they should show): " + "; ".join(shown[:4]) +
        " — an internal part you can SEE is part of the look: either it is really visible on the object (say so in "
        "the spec: visible='through', and detail it), or close the opening it shows through (end cap, bushing, cover)",
        strict))

    # ---------------------------------------------------------------- fasteners in mid-air
    loose = []
    for k, nm in enumerate(names):
        if not (_words(nm) & FASTENER_WORDS) or base(nm) in internal:
            continue  # internal rods / pins are judged by the mechanism, not by looks
        span, where, length = w.support(k)
        if span > max(length * 0.4, w.diag * 0.004):  # a pin may cross a pocket to reach what it holds
            loose.append(f"{base(nm)}: {_mm(asset, span)} of its {_mm(asset, length)} in open air (around {where:.0%} along it)")
    facts["unsupported_fasteners"] = loose
    checks.append(rbx_critic._check(
        "fastener_support", not loose, loose[:6] or "every pin / screw / rod passes through material", "through material",
        "fasteners spanning air: " + "; ".join(loose[:4]) + " — a pin goes THROUGH holes in walls/bosses: shorten it "
        "to the wall it crosses, move it into the material, or add the boss it sits in", strict))

    # ---------------------------------------------------------------- fasteners / internals SEATED in a hole
    # the other half of down-to-the-screws (the owner, 2026-10-07): a screw, a pin, a spring or any a.internal() part
    # sits in a HOLE / CAVITY of its host, never in solid metal (a take-apart would pull it out of nothing). A part with
    # more than a third of its volume inside another part's solid is named with that part.
    seats = []
    for k, (o, _g) in enumerate(w.parts):
        nm = o.name
        if not ((_words(nm) & SEATED_WORDS) or base(nm) in internal):
            continue
        share, host = w.embedded(k)
        if share > 0.35:
            seats.append(f"{base(nm)}: {share:.0%} of it inside {base(host)}")
    facts["buried_fasteners"] = seats
    checks.append(rbx_critic._check(
        "fastener_seat", not seats, seats[:6] or "every screw / pin / spring / internal part sits in a hole or cavity",
        "in a hole", "parts sunk in solid material: " + "; ".join(seats[:4]) + " — cut the hole it sits in (a screw: "
        "clearance('M3') in the host's a.cad code; a pin: its bore; a spring: its channel), or move it to the cavity "
        "it belongs in", strict))

    # ---------------------------------------------------------------- dark finishes (rbx_pbr.dark_story)
    # two big dark materials a step apart in value, and (hero / aaa) a dark finish worn like a used one: what the Glock
    # needed before the owner's 85/100 (2026-10-10). Weighted by each material's VISIBLE area (internal parts out,
    # each part's area x its visible share): a magazine body inside the grip is not "big"
    import rbx_pbr  # noqa: PLC0415

    key_of = {info["mat"].name: key for key, info in asset.mats.items() if info.get("mat") is not None}  # (by the
    # material itself: an imported mesh's materials are "gen_<name>", a re-used session's carry .001)
    area = {}
    model_diag = max((max(o.dimensions) for o, _g in w.parts), default=0.0) or 1.0
    for k, (o, g) in enumerate(w.parts):
        slots = list(o.data.materials)
        if base(o.name) in internal or g in ("glass", "marks") or o.get("kit_text") or not slots:
            continue
        sc = o.matrix_world.to_scale()
        s2 = abs(sc.x * sc.y * sc.z) ** (2.0 / 3.0)
        by = {}
        for p in o.data.polygons:
            m = slots[p.material_index] if p.material_index < len(slots) else None
            if m is not None and m.name in key_of:
                by[key_of[m.name]] = by.get(key_of[m.name], 0.0) + p.area * s2
        if not by:
            continue
        # EVERY part by its visible share (a barrel inside a slide is not "big"); a small part (under 3% of the model)
        # by its whole area: too small to tip a share, not worth the rays
        frac = (vis[o.name][0] if o.name in vis else w.visibility(k)[0]) if max(o.dimensions) >= 0.03 * model_diag \
            else 1.0
        for n, a_ in by.items():
            area[n] = area.get(n, 0.0) + a_ * frac
    rows = [{"name": n, "area": a_, **{key: asset.mats[n].get(key) for key in
                                        ("color", "metal", "burnish", "rub", "emit")}}
            for n, a_ in area.items() if n in asset.mats]
    story = rbx_pbr.dark_story(rows, worn=asset.quality in ("hero", "aaa"))
    facts["dark_finishes"] = {"main": story["main"], "alike": story["alike"], "unworn": story["unworn"]}
    said = ([f"{a_} and {b_} read as ONE mass ({va} vs {vb} sRGB)" for a_, b_, va, vb in story["alike"]]
            + [f"{n}: a dark finish with no edge wear" for n in story["unworn"]])
    checks.append(rbx_critic._check(
        "dark_finishes", not said, said[:4] or "the big dark materials read apart, and worn",
        f"dark materials {rbx_pbr.DARK_STEP}+ sRGB apart; a hero's worn",
        "; ".join(said[:3]) + " — " + "; ".join(
            ([f"step one material {rbx_pbr.DARK_STEP}+ sRGB lighter or darker (the owner-rated Glock: frame 86 / "
              "slide 47 sRGB — at 57 / 47 two fresh judges read both 'the same blue-navy')"] if story["alike"] else [])
            + (["wear it like a used one: a.material(..., life=\"used\") (burnished edges 2-2.5 mm, "
                "rubbed flats) — eight judges read a bare dark finish as 'no wear at all'"] if story["unworn"] else [])),
        "warn"))

    # ---------------------------------------------------------------- bevels: hard edges left SHARP
    # the owner (2026-10-07): "you can never make parts bevelled". Every visible part's hard edges (> 30 deg) measured
    # like a reference model's (kit/refs/dissect.py): the share that is bevelled. The bar: hero / aaa at least half,
    # a prop a quarter — raised to what REAL models of this kind do for this part's role (a.learned_from("firearm"):
    # kit/learned, where 2+ models agree); the fix names their typical bevel size
    refs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "refs")
    if refs_dir not in sys.path:
        sys.path.insert(0, refs_dir)
    import dissect  # noqa: PLC0415
    import learn  # noqa: PLC0415

    cat = asset.design.get("learned")
    known = learn._load(cat)["samples"] if cat else {}
    mmps_e = getattr(asset, "mm_per_stud", None) or 280.0
    to_m = mmps_e / 1000.0
    unbevelled, bev_facts, faceted = [], {}, []
    # the high-and-low route's parts are measured against their high by the silhouette check (facts.low); this
    # estimate reported sags their CAD tessellation cannot have (the car rim's barrel "2.583 mm" on a 1.0 mm mesh)
    low_parts = {o_.name.split("~high")[0] for o_, _g in getattr(asset, "_high_parts", [])}
    for k, (o, g) in enumerate(w.parts):
        nm = base(o.name)
        if nm in internal or g in ("glass", "marks") or o.get("kit_text") or max(o.dimensions) * mmps_e < 5:
            continue
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.transform(o.matrix_world)
        bmesh.ops.scale(bm, vec=(to_m, to_m, to_m), verts=bm.verts)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-7)
        e = dissect.edges(bm, max(o.dimensions) * to_m)
        bm.free()
        sag = (e or {}).get("facet_sag_mm")
        if (sag is not None and nm not in low_parts and (e.get("facet_mm") or 0) > 20
                and sag > (0.08 if strict == "error" else 0.25)):
            faceted.append(f"{nm}: its curve steps {e['facet_deg']:g} deg, {sag:g} mm off the true curve")
        if not e or (e["sharp_mm"] + e["bevel_mm"]) < 10 or e["bevelled_share"] is None:
            continue  # no hard edges to speak of (a pin, a spring, a round knob)
        role = learn.role(nm)
        real = learn.rng(known.get("bevelled_share", {}).get(f"role:{role}", [])) if role else None
        bar = 0.5 if strict == "error" else 0.25
        if real and real["models"] >= 2:
            bar = max(bar, real["typical"] if strict == "error" else real["low"])
        bev_facts[nm] = {"bevelled_share": e["bevelled_share"], "sharp_mm": e["sharp_mm"],
                         "bevel_size_mm": (e.get("bevel_size_mm") or {}).get("typical"), "bar": round(bar, 2)}
        runs = [dict(r, at=[r["at"][0], r["at"][2], -r["at"][1]]) for r in e.get("sharp_runs") or []]  # (Roblox axes)
        bev_facts[nm]["sharp_runs"] = runs
        if e.get("share_unreliable"):
            bev_facts[nm]["share_unreliable"] = e["share_unreliable"]
        if e["bevelled_share"] < bar:
            size = learn.learned(cat, "bevel_size_mm", f"role:{role}") if cat and role else None
            where = "; ".join(f"{r['mm']:.0f} mm at ({', '.join(f'{c:.0f}' for c in r['at'])}) mm, {r['deg']} deg"
                              for r in runs[:2])
            flip = e.get("share_unreliable")
            unbevelled.append(f"{nm}: {e['bevelled_share']:.0%} of its hard edges bevelled, {e['sharp_mm']:.0f} mm "
                              f"sharp (bar {bar:.0%}" + (f"; real {role}s round theirs ~{size:g} mm" if size else "") + ")"
                              + (f" — longest sharp runs: {where} (Roblox axes)" if where else "")
                              + (f" — its share is UNRELIABLE here: one transition network {flip['width_mm']:g} mm wide "
                                 f"sits by the {flip['line_mm']:g} mm line between 'bevels' and 'a curved surface' "
                                 "(a lofted surface + its fillets): round the sharp runs, never reshape to the line"
                                 if flip else ""))
    facts["bevels"] = bev_facts
    checks.append(rbx_critic._check(
        "sharp_edges", not unbevelled, unbevelled[:6] or "every visible part's hard edges bevelled to the bar",
        "bevelled", "hard edges left sharp: " + "; ".join(unbevelled[:4]) + " — a real part's edges are rounded or "
        "chamfered (a sharp CG edge reads fake and catches no light): a.cad round_edges / fillet_soft(edges, r) / "
        "a.box(..., bevel=r) / a.extrude(..., bevel=r); sizes: kit learned show <category> (bevel_size_mm by role)",
        strict))
    # faceting: a curve shown as a polygon — judged by how far its facets sit from the true curve (the sagitta), not
    # the step alone: 16 sides are invisible on a 3 mm pin (0.03 mm) and show on a 20 mm barrel (0.2 mm)
    facts["faceted"] = faceted
    if low_parts:
        facts["faceting_replaced_by"] = {"silhouette": sorted(low_parts)}   # (those parts: the silhouette check)
    checks.append(rbx_critic._check(
        "faceting", not faceted, faceted[:6] or "every curve smooth to the eye", "smooth curves",
        "curves shown as polygons: " + "; ".join(faceted[:4]) + " — more segments (a.cylinder(..., segments=48), "
        "a.tube(..., segments=12)) or build it in a.cad (tessellated to 0.05 mm)", strict))

    # ---------------------------------------------------------------- wrap-around: horizontal slices vs a reference
    # a.section_match(ref): the build sliced at the reference's heights exactly as kit refs measure slices a model
    # (measure.levels: the biggest island's width, depth, roundness) — a grip built as a box reads square where the
    # real one wraps around (squareness 6+ against ~2)
    wrap, wrap_facts, wrap_skipped = [], [], []
    if asset.design.get("section_match"):
        import measure  # noqa: PLC0415  (kit/refs: the same slicing as a reference model's)
        import rbx_formmatch  # noqa: PLC0415  (fragment_levels: a reference slice in pieces is not a section)

        joined = bmesh.new()
        for o, g in w.parts:
            if g in ("glass", "marks"):
                continue
            me = o.data.copy()
            me.transform(o.matrix_world)
            joined.from_mesh(me)
            bpy.data.meshes.remove(me)
        bmesh.ops.scale(joined, vec=(to_m, to_m, to_m), verts=joined.verts)
        jlo, jhi, jext = measure._bounds(joined)
        jaxis = 0 if jext.x >= jext.y else 1
        for spec in asset.design["section_match"]:
            try:
                with open(spec["ref"], encoding="utf-8") as fh:
                    ref_all = json.load(fh).get("levels", [])
                ref_lv = {round(lv["h"], 2): lv for lv in ref_all}
            except (OSError, ValueError):
                wrap.append(f"{os.path.basename(spec['ref'])}: no reference levels (kit refs measure <model> first)")
                continue
            pieces = {round(h, 2): w for h, w in rbx_formmatch.fragment_levels(ref_all).items()}
            mine = {round(lv["h"], 2): lv for lv in measure.levels(joined, jlo, jhi, jaxis, 1 - jaxis, spec["levels"])}
            for h in spec["levels"]:
                r, m = ref_lv.get(round(h, 2)), mine.get(round(h, 2))
                wrap_facts.append({"h": h, "build": m, "reference": r})
                if round(h, 2) in pieces:
                    wrap_facts[-1]["skipped"] = True   # (on the row: kit fit leaves out THIS reference's slice only)
                    wrap_skipped.append(pieces[round(h, 2)])
                    continue
                if not r or not m:
                    wrap.append(f"{h:.0%} height: no slice in the {'reference' if not r else 'build'}")
                    continue
                if m["squareness"] > r["squareness"] + spec["bar"] and m["squareness"] > 3.0:
                    wrap.append(f"{h:.0%} height: a rounded box (squareness {m['squareness']:g}) where the reference "
                                f"wraps round ({r['squareness']:g})")
                k_m, k_r = m["depth_mm"] / max(m["width_mm"], 1e-6), r["depth_mm"] / max(r["width_mm"], 1e-6)
                if abs(k_m / k_r - 1) > 0.25:
                    wrap.append(f"{h:.0%} height: {m['width_mm']:g} x {m['depth_mm']:g} mm against the reference's "
                                f"{r['width_mm']:g} x {r['depth_mm']:g} (depth / width {k_m:.2f} vs {k_r:.2f})")
        joined.free()
    facts["section_match"] = wrap_facts
    if wrap_skipped:
        facts["section_match_skipped"] = wrap_skipped
    if asset.design.get("form_match"):   # a.form_match: the build's surface against a real model's, region by region
        import rbx_formmatch  # noqa: PLC0415

        seen = [o for o, g in w.parts if g not in ("glass", "marks")]
        reps = [rbx_formmatch.run(asset, seen, spec) for spec in asset.design["form_match"]]
        facts["form_match"] = reps
        bad = [ln for r in reps if not r["ok"] for ln in r["lines"][:3]]
        checks.append(rbx_critic._check(
            "form_match", not bad, bad[:4] or [ln for r in reps for ln in r["lines"][:3]] or "on the reference's form",
            "within the bar of the reference's surface",
            "the form strays from the real model: " + "; ".join(bad[:3]) + " — sculpt toward it there (missing: add "
            "clay; extra: carve or move it), then build again: the report says what moved", "warn"))
    if asset.design.get("section_match"):
        checks.append(rbx_critic._check(
            "section_match", not wrap, wrap[:6] or (["every compared slice wraps like the reference's"] + wrap_skipped
                                                    if wrap_skipped else "every slice wraps like the reference's"),
            "as the reference",
            "slices unlike the reference: " + "; ".join(wrap[:4]) + " — loft the part through the reference's own "
            "sections: in its a.cad code `part = loft_sections(from_levels(P['levels'], height_mm, length_mm, "
            "hs=(...)))` with params={'levels': <the measure.json levels>}", strict))

    # ---------------------------------------------------------------- slivers: thin walls on otherwise solid parts
    # two cuts / outlines that nearly coincide leave a shelf ~1 mm thick (under a grip, along a magazine): measure the
    # wall thickness at every visible surface point by an inward ray; flag clusters of thin points on thick parts
    # a SLIVER is a thin spot on a part that is otherwise thick (a 2 mm shelf left on a 56 mm receiver); a part that is
    # thin everywhere (sheet metal, a lens, a wire) is thin by design
    mmps = getattr(asset, "mm_per_stud", None)
    thr = (1.5 / mmps) if mmps else w.diag * 0.001
    eps = w.diag * 2e-5
    slivers = []
    for k, (o, g) in enumerate(w.parts):
        if base(o.name) in internal or g in ("glass", "marks") or o.get("kit_text"):
            continue
        ext = sorted(o.dimensions)
        if ext[0] < thr * 2:
            continue
        seen = []
        for p, n in dense_samples(o, thr * 1.2):
            if w.tree.ray_cast(p + n * eps, n, w.diag * 3)[0] is not None:
                continue  # not seen from straight out
            hit = w.tree.ray_cast(p - n * eps, -n, thr * 20)
            own = hit[0] is not None and w.owner[hit[2]] == k
            t = hit[3] if own else thr * 20
            # the far face is parallel (within ~10 deg): a slab or a shelf. A pointed blade's two edges converge (a feather,
            # a sword's tip: ~20 deg) and thin out to the point by design — no sliver (the Gjallarhorn's feathers)
            parallel = own and hit[1].dot(n) < -0.985
            seen.append((p, t if parallel or t >= thr else thr * 20))
        if not seen:
            continue
        ts = sorted(t for _p, t in seen)
        if ts[len(ts) // 2] < thr * 4:
            continue  # thin by design
        thin = [(p, t) for p, t in seen if thr * 0.03 < t < thr]
        clustered = dense_clusters(thin, thr * 4, 4, at=lambda q: q[0])
        if len(clustered) >= 4:
            lo = Vector([min(q[0][i] for q in clustered) for i in range(3)])
            hi = Vector([max(q[0][i] for q in clustered) for i in range(3)])
            t = sorted(q[1] for q in clustered)[len(clustered) // 2]
            # (the box's centre alone misled: a cluster spread over both wings of a mirrored part centres in thin air —
            #  its extent and its thinnest point say where to look)
            worst = min(clustered, key=lambda q: q[1])[0]
            slivers.append(f"{base(o.name)}: {_mm(asset, t)} thick over {len(clustered)} points around {_rbx((lo + hi) / 2)}"
                           f" (spanning {_rbx(lo)} to {_rbx(hi)}; thinnest at {_rbx(worst)})")
    facts["slivers"] = slivers
    checks.append(rbx_critic._check(
        "slivers", not slivers, slivers[:5] or "no thin shelves / slivers on solid parts", "none",
        "thin slivers on solid parts: " + "; ".join(slivers[:3]) + " — two cuts or outlines nearly coincide: split the "
        "pieces from ONE shape (rbx_trace.region(..., minus=[...]) gives exactly shared boundaries) or make the cut "
        "overlap clearly; never leave a shelf thinner than ~1.2 mm on a solid part", strict))

    # ---------------------------------------------------------------- plates sit ON their host
    # a thin part (a floor plate, an armour plate, a panel, a badge) must rest on what holds it over most of its back:
    # a flat plate under a slanted face overhangs it and reads as a loose shelf
    overhang = []
    ptrees = {}  # part index -> its own BVH tree (built when a plate needs it)
    boxes = []
    for o, _g in w.parts:
        cs_ = [o.matrix_world @ Vector(c) for c in o.bound_box]
        boxes.append((Vector([min(c[i] for c in cs_) for i in range(3)]), Vector([max(c[i] for c in cs_) for i in range(3)])))
    for k, (o, g) in enumerate(w.parts):
        if base(o.name) in internal or o.get("kit_text") or g in ("glass", "marks"):
            continue
        ext = sorted(o.dimensions)
        if not (ext[0] < thr * 4 and ext[1] > ext[0] * 5):
            continue  # not a plate
        # the plate's thin axis (world) = the smallest extent of its bounding box
        cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
        lo = Vector([min(c[i] for c in cs) for i in range(3)])
        hi = Vector([max(c[i] for c in cs) for i in range(3)])
        ax = min(range(3), key=lambda i: hi[i] - lo[i])
        best = None
        for sign in (1, -1):  # the side facing the host is the one with contact
            d = Vector([0, 0, 0])
            d[ax] = sign
            n_ok = n_all = 0
            samples_ = dense_samples(o, max(hi - lo) / 30)
            if sum(1 for _p, n in samples_ if abs(n.dot(d)) > 0.98) < len(samples_) * 0.35:  # truly flat faces
                n_all = 0
                break  # no flat broad faces: a ring, a wire, a rod - not a plate
            missed = []
            for p, n in samples_:
                if n.dot(d) < 0.8:
                    continue
                n_all += 1
                hit = w.tree.ray_cast(p + d * eps, d, thr * 1.5)
                if hit[0] is not None and w.owner[hit[2]] != k:
                    n_ok += 1
                else:
                    missed.append(p + d * eps)
            if missed:
                # a back seated flush on its host or sunk into it (rbx_parts.plate sinks 0.002 studs, as a mount should)
                # starts its ray INSIDE the host and finds no face: it rests, it does not overhang. Tested on a strided
                # subset, part by part (a shared face cannot flip one part's parity)
                hosts = [j for j, (lo_j, hi_j) in enumerate(boxes) if j != k
                         and all(lo_j[i] - thr <= hi[i] and lo[i] <= hi_j[i] + thr for i in range(3))]
                step = max(1, len(missed) // 40)
                tested = missed[::step]
                for j in hosts:
                    if j not in ptrees:
                        ptrees[j] = part_tree(w.parts[j][0])
                seated = sum(1 for q in tested if any(inside_tree(ptrees[j], q) for j in hosts)) if hosts else 0
                n_ok += round(len(missed) * seated / len(tested))
            if n_all and (best is None or n_ok / n_all > best[0]):
                best = (n_ok / n_all, sign)
        if best is not None and best[0] < 0.7:
            overhang.append(f"{base(o.name)}: only {best[0]:.0%} of its back rests on anything")
    facts["plate_support"] = overhang
    checks.append(rbx_critic._check(
        "plate_support", not overhang, overhang[:5] or "every plate rests on its host", ">= 70% contact",
        "plates hanging off their host: " + "; ".join(overhang[:3]) + " — shape the plate from the host's own outline "
        "(rbx_trace.region of the host's edge, offset a little) instead of a box, so it follows a slanted / curved face",
        strict))

    # ---------------------------------------------------------------- markings sit on ONE flat face of ONE part
    bad_marks = []
    for k, (o, g) in enumerate(w.parts):
        if not o.get("kit_text"):
            continue
        f = Vector(_FACING_BL.get(o.get("kit_facing", "+X"), (1, 0, 0)))
        cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
        lo = Vector([min(c[i] for c in cs) for i in range(3)])
        hi = Vector([max(c[i] for c in cs) for i in range(3)])
        axes = [i for i in range(3) if abs(f[i]) < 0.5]
        hosts, depths = {}, []
        for a_ in range(9):
            for b_ in range(4):
                p = (lo + hi) / 2
                p[axes[0]] = lo[axes[0]] + (hi[axes[0]] - lo[axes[0]]) * (a_ + 0.5) / 9
                p[axes[1]] = lo[axes[1]] + (hi[axes[1]] - lo[axes[1]]) * (b_ + 0.5) / 4
                start = p + f * (w.diag * 0.01)
                for _ in range(6):  # through the letters themselves, to what is behind them
                    hit = w.tree.ray_cast(start, -f, w.diag * 0.05)
                    if hit[0] is None:
                        hosts["(nothing)"] = hosts.get("(nothing)", 0) + 1
                        break
                    if w.owner[hit[2]] == k:
                        start = hit[0] - f * eps
                        continue
                    hn = base(w.parts[w.owner[hit[2]]][0].name)
                    hosts[hn] = hosts.get(hn, 0) + 1
                    depths.append(hit[0].dot(f))
                    break
        main_host = max(hosts, key=hosts.get) if hosts else "(nothing)"
        others = {h: n for h, n in hosts.items() if h != main_host}
        flat = (max(depths) - min(depths)) if depths else 0.0
        if others or main_host == "(nothing)" or flat > thr:
            why = []
            if others:
                why.append(f"crosses {', '.join(sorted(others))}")
            if main_host == "(nothing)":
                why.append("floats in air")
            if flat > thr:
                why.append(f"the surface behind it steps by {_mm(asset, flat)} (an edge / a cut runs under it)")
            bad_marks.append(f"{base(o.name)} on {main_host}: {'; '.join(why)}")
    facts["markings"] = bad_marks
    checks.append(rbx_critic._check(
        "marking_placement", not bad_marks, bad_marks[:5] or "every marking on one flat face", "one flat face",
        "markings badly placed: " + "; ".join(bad_marks[:3]) + " — move the text to a clear flat area of one part "
        "(no pins, holes, edges, seams or other parts under it), or shrink it", strict))

    # ---------------------------------------------------------------- clear paths (bores, sight lines, ducts)
    for cp in getattr(asset, "clear_paths", []):
        p0 = mirrored_to_rbx @ Vector(cp["p0"])
        p1 = mirrored_to_rbx @ Vector(cp["p1"])
        blocks = w.clear(p0, p1, cp["radius"])
        by = sorted({b[0] for b in blocks})
        checks.append(rbx_critic._check(
            f"clear:{cp['name']}", not blocks, by[:4] or "clear", "nothing in the way",
            f"{cp['name']} is blocked by {', '.join(by[:4])} (first at {_mm(asset, min(b[1] for b in blocks)) if blocks else ''} "
            f"from its start) — {cp.get('why', 'open the path')}", strict))

    # ---------------------------------------------------------------- the design spec, part by part
    if spec and spec.get("parts"):
        from rbx_precision import _distance  # noqa: PLC0415

        by = {}
        for o, g in w.parts:
            by.setdefault(base(o.name), rbx_critic._Part(o, g))
        tol = min(0.01, max(0.002, w.diag * 0.002))
        missing, detached, described = [], [], set()
        # a game build's floaters are baked into their group's maps: present, nothing to measure. A MASTER has every
        # spec part as real geometry (its floaters stay parts), so there a baked one is missing
        baked = set() if getattr(asset, "stage", "game") == "master" else {
            base(o.name) for o, _g in getattr(asset, "_floater_parts", ())}
        for sp in spec["parts"]:
            hits = [nm for nm in by if _spec_match(sp["name"], nm)]
            described |= set(hits)
            if not hits:
                if any(_spec_match(sp["name"], nm) for nm in baked):
                    continue
                missing.append(f"{sp['name']} ({sp.get('what', '')[:60]})")
                continue
            for other in sp.get("attaches", []):
                others = [nm for nm in by if _spec_match(other, nm)]
                if not others:
                    detached.append(f"{sp['name']} -> {other}: no such part")
                    continue
                d = min(_distance(by[h], by[o2]) for h in hits for o2 in others)
                if d > tol:
                    detached.append(f"{sp['name']} is {_mm(asset, d)} from {other} (must attach)")
        # a part the spec says attaches must MEET its partner where they face each other: a visible gap between
        # them (a grip hanging below its seat, a lid not closing, a panel standing off) is measured in mm
        gaps = []
        gmax = (14.0 / mmps) if mmps else w.diag * 0.01
        perp = [Vector(v).normalized() for v in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]
        for sp in spec["parts"]:
            for other in sp.get("attaches", []):
                for a_name in [nm for nm in by if _spec_match(sp["name"], nm) and nm not in internal]:
                    # a SEAT check: a smaller part sitting on / in a bigger one (a grip in its seat, a sight on a rail);
                    # two big shells around a hollow interior and wire coils are not seats
                    ka = w.index.get(by[a_name].obj.name) if hasattr(by[a_name], "obj") else None
                    if ka is None:
                        ka = next((i for i, (o, _g) in enumerate(w.parts) if base(o.name) == a_name), None)
                    if ka is None:
                        continue
                    partners = {i for i, (o, _g) in enumerate(w.parts) if _spec_match(other, base(o.name))}
                    oa = w.parts[ka][0]
                    if oa.get("kit_tube") or not partners:
                        continue
                    va = oa.dimensions.x * oa.dimensions.y * oa.dimensions.z
                    vb = max(w.parts[i][0].dimensions.x * w.parts[i][0].dimensions.y * w.parts[i][0].dimensions.z for i in partners)
                    if va >= vb * 0.5:
                        continue
                    found, contact = [], []
                    back = thr * 0.4  # start a little BEHIND the surface: a partner lying exactly on it is contact
                    for p, n in dense_samples(w.parts[ka][0], thr * 2):
                        hit = w.tree.ray_cast(p - n * back, n, gmax + back)
                        while hit[0] is not None and w.owner[hit[2]] == ka:
                            hit = w.tree.ray_cast(hit[0] + n * eps, n, gmax)  # through our own face
                        if hit[0] is None or w.owner[hit[2]] not in partners:
                            continue
                        d_ = (hit[0] - p).dot(n)
                        if d_ < thr:
                            contact.append(p)
                            continue
                        hit = (hit[0], hit[1], hit[2], d_)
                        if hit[1].dot(n) > -0.9:
                            continue  # not FACING surfaces: a bevel meeting a flat, a dovetail undercut - a seam, not a gap
                        q = p + n * (hit[3] / 2)
                        if any(w.tree.ray_cast(q, d, w.diag * 3)[0] is None for d in perp if abs(d.dot(n)) < 0.3):
                            found.append((p, hit[3]))
                    # a gap point with real contact close by is a RECESS in a seated interface (a rail slot under a
                    # sight base, a groove): only daylight with no contact around it is a part standing off
                    found = [f_ for f_ in found if not any((f_[0] - c_).length < thr * 5 for c_ in contact)]
                    if len(found) < 0.6 * (len(found) + len(contact)):
                        continue  # mostly seated: what is left are recesses
                    clustered = dense_clusters(found, thr * 6, 4, at=lambda f_: f_[0])
                    if len(clustered) >= 4:
                        dmed = sorted(d for _p, d in clustered)[len(clustered) // 2]
                        ctr_ = sum((p for p, _d in clustered), Vector()) / len(clustered)
                        gaps.append(f"{a_name} -> {other}: a visible {_mm(asset, dmed)} gap around {_rbx(ctr_)}")
        facts["spec_parts_gaps"] = gaps
        checks.append(rbx_critic._check(
            "attach_gaps", not gaps, gaps[:5] or "attached parts meet", "no visible gap",
            "attached parts standing apart: " + "; ".join(gaps[:3]) + " — extend / seat the part into its partner "
            "(a grip into its seat, a lid onto its rim) so no daylight shows between them", strict))
        undocumented = sorted({family(nm) for nm in by if nm not in described})
        facts["spec_parts"] = {"described": len(described), "missing": missing, "detached": detached,
                               "undocumented": undocumented}
        checks.append(rbx_critic._check(
            "spec_parts", not missing, missing[:6] or "every spec part modelled", "all present",
            "the spec names parts the model lacks: " + "; ".join(missing[:5]) + " — model them (the spec is what the "
            "real object HAS)", strict))
        checks.append(rbx_critic._check(
            "spec_attach", not detached, detached[:6] or "every part attaches where the spec says", "attached",
            "parts not attached as specified: " + "; ".join(detached[:4]) + " — a part sits ON / IN what holds it",
            strict))
        checks.append(rbx_critic._check(
            "spec_undocumented", not undocumented, undocumented[:10] or "every part is described", "described",
            f"parts the spec does not describe: {', '.join(undocumented[:8])} — what IS each in reality? add it to "
            f"refs/{asset.spec_name}.spec.json parts (what / attaches / visible / source) or remove it", strict))

    # ---------------------------------------------------------------- sizes against the reference, in mm
    # a spec part with "ref": "<a traced part of the side view>" (kit trace --part: SAM's mask of that part of the
    # reference, measured by kit refs views) is set beside it on every build — the judges should never be the first
    # to see that a bracket is half its height
    linked = {}
    for sp in (spec or {}).get("parts", []):
        if sp.get("ref"):
            linked.setdefault(sp["ref"], []).append(sp["name"])
    if linked:
        from rbx import REPO  # noqa: PLC0415

        views = (spec or {}).get("views") or f"refs/{asset.spec_name}.views.json"  # (a fixture names its own)
        rows, note = ref_sizes(asset, w, linked, os.path.join(REPO, views))
        facts["ref_sizes"] = {"note": note, "rows": rows}
        measured = [r for r in rows if "ok" in r]
        off = sorted((r for r in measured if not r["ok"]),
                     key=lambda r: -max(abs(x) for x in r["size_off_mm"] + r["place_off_mm"]))
        unknown = [r["note"] for r in rows if "note" in r]
        checks.append(rbx_critic._check(
            "ref_sizes", bool(measured) and not off and not unknown,
            [_ref_row_text(r) for r in off[:6]] + unknown[:3] or f"{len(measured)} part(s) within 5% / 3 mm",
            "every linked part within 5% (or 3 mm) of the reference",
            ("parts off the reference: " + "; ".join(_ref_row_text(r) for r in off[:4]) if off else
             "; ".join(unknown[:2]) if unknown else note) + " — resize / move the part (its spec \"ref\" is the "
            "traced part of the reference it must match; a wrong trace is retraced, never matched)"
            + ("" if not any(r.get("doubtful") for r in off) else
               " — but first retrace the doubtful mask(s) among them (ref_sizes_doubtful)"), strict))
        # a ref to a mask kit trace judged doubtful (filled its box, one area with its neighbour, a dropped claw, a
        # plain box): what it measures may be the mask's mistake, not the model's — said, never failed on
        doubtful = [f"ref '{r['ref']}' is a doubtful mask: {'; '.join(r['doubtful'])}"
                    for r in rows if r.get("doubtful")]
        checks.append(rbx_critic._check(
            "ref_sizes_doubtful", not doubtful, doubtful[:4] or "every linked part's mask judged clean by kit trace",
            "every spec \"ref\" links a clean traced mask",
            "; ".join(doubtful[:3]) + " — retrace it with --part-point \"name=x,y;x,y\" or --part-text "
            "name=\"what it is\" (lune run kit trace ...), then lune run kit refs views again", "warn"))
    return checks, facts, w


# ==================================================================== the forced per-part review
def _box_sig(o):
    cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
    lo = [min(c[i] for c in cs) for i in range(3)]
    hi = [max(c[i] for c in cs) for i in range(3)]
    mats = ",".join(sorted(m.name for m in o.data.materials if m))
    return f"{base(o.name)}|{[round(v, 3) for v in lo]}|{[round(v, 3) for v in hi]}|{mats}"


def _fingerprint_v1(objs):
    """the first fingerprint (bounding box + materials): a hole or a reshape INSIDE the same box went unnoticed.
    A review answered under it is accepted once while it still matches, then re-stamped with _fingerprint."""
    h = hashlib.sha1()
    for o in sorted(objs, key=lambda x: x.name):
        h.update(_box_sig(o).encode())
    return h.hexdigest()[:8]


def _fingerprint(objs):
    """what a part family IS: where it sits (bounding box), what it is made of, and its SHAPE — volume and area
    to 4 significant digits. A hole, a chamfer or a reshape inside the same box changes them; the same shape
    re-triangulated (another boolean solver, another bevel order) does not."""
    h = hashlib.sha1()
    for o in sorted(objs, key=lambda x: x.name):
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.transform(o.matrix_world)
        vol, area = abs(bm.calc_volume()), sum(f.calc_area() for f in bm.faces)
        bm.free()
        h.update(f"{_box_sig(o)}|{vol:.4g}|{area:.4g}".encode())
    return h.hexdigest()[:8]


def _edge_options(v, fmt, d):
    """fmt(v), and the other rounding too when v sits within d of a rounding edge"""
    out = [fmt(v)]
    for w in (v - d, v + d):
        r = fmt(w)
        if r not in out:
            out.append(r)
    return out


def _sig_variants(name, lo, hi, mats, vol, area, cap=64):
    """the fingerprint strings ONE object can have while a number of it sits within float noise of a rounding edge —
    the first is its own (what _fingerprint hashes). A boolean's noise moves a volume by ~1e-7: across a 4-digit
    boundary that flipped the hash, and an unchanged family went back to TODO every other build (the Gjallarhorn's
    feathers, 2026-10-06). The tolerance is 1e-5 (relative for volume / area, studs for the box): far below any
    real reshape."""
    import itertools

    box = lambda x: round(x, 3)  # noqa: E731  (as _box_sig)
    opts = ([_edge_options(v, box, 1e-5) for v in lo] + [_edge_options(v, box, 1e-5) for v in hi]
            + [_edge_options(vol, lambda x: f"{x:.4g}", abs(vol) * 1e-5 + 1e-12),
               _edge_options(area, lambda x: f"{x:.4g}", abs(area) * 1e-5 + 1e-12)])
    out = []
    for c in itertools.product(*opts):
        out.append(f"{name}|{list(c[0:3])}|{list(c[3:6])}|{mats}|{c[6]}|{c[7]}")
        if len(out) >= cap:
            break
    return out


def _fingerprint_variants(objs, cap=4096):
    """every fingerprint the family could have under float noise at a rounding edge (see _sig_variants)"""
    import itertools

    per = []
    for o in sorted(objs, key=lambda x: x.name):
        cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
        lo = [min(c[i] for c in cs) for i in range(3)]
        hi = [max(c[i] for c in cs) for i in range(3)]
        mats = ",".join(sorted(m.name for m in o.data.materials if m))
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.transform(o.matrix_world)
        vol, area = abs(bm.calc_volume()), sum(f.calc_area() for f in bm.faces)
        bm.free()
        per.append(_sig_variants(base(o.name), lo, hi, mats, vol, area))
    out = set()
    for combo in itertools.product(*per):
        h = hashlib.sha1()
        for sig in combo:
            h.update(sig.encode())
        out.add(h.hexdigest()[:8])
        if len(out) >= cap:
            break
    return out


def fingerprints(fams):
    return {fam: _fingerprint([o for o, _g in members]) for fam, members in fams.items()}


def families(parts):
    fam = {}
    for o, g in parts:
        if o.type == "MESH" and len(o.data.polygons):
            fam.setdefault(family(o.name), []).append((o, g))
    return fam


_ENTRY = re.compile(r"^- (?P<fam>[A-Za-z_][\w*]*) \[(?P<fp>[0-9a-f]{8})\]:\s*(?P<body>.*)$")
FIELDS = ("real:", "attaches:", "works:", "verdict:")


def sync_review(asset, fams, path, fps=None, repo=None):
    """keep assets/models/<asset>.parts.md in step with the model: one entry per part family, fingerprinted.
    -> (todo families, fix families, stale families, {family: reference problems}) — an answered family without a
    reference picture on disk (review_refs) is not done either."""
    import review_refs  # noqa: PLC0415

    repo = repo or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(path))))
    fps = fps or fingerprints(fams)
    old = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                m = _ENTRY.match(line.rstrip("\n"))
                if m:
                    old[m["fam"]] = (m["fp"], m["body"].strip())
    lines = [f"# {asset.name} — part review (kept in sync by the kit; you write the answers)",
             "",
             "Every part family gets one line. Answer from the REFERENCES / MANUAL, not from memory, in this form:",
             "`- Part [fp]: real: <what it is on the real object> | attaches: <what holds it> | works: <what it does /",
             "how it moves> | ref: <the picture(s) you modelled it from> | verdict: ok` — or `verdict: fix <what is",
             "wrong>` (a fix verdict fails hero/aaa builds). ref: a photo or drawing of THIS part on the real object or,",
             "when it has none, of the closest SIMILAR part (another make's, an exploded diagram's) — a file on disk:",
             "`lune run kit refs parts <asset>` lists the parts without one and the searches to run (kit refs find).",
             "A part answered by a MEASUREMENT (a pin's diameter, a screw's size) may cite a dimension row instead:",
             "`ref: dims:<id>` (`lune run kit refs dims find \"<object> <part>\"`).",
             "Every part, inside ones too, needs one: a part answered without a picture or a dims row is not answered.",
             "Look at build/renders/parts/<asset>_parts_todo.png first. A part whose geometry changes goes",
             "back to TODO (its fingerprint changed) with its last answer kept: `TODO (changed since: <answer>)` — look",
             "again; if the answer still holds, remove the `TODO (changed since: ` wrapper, else rewrite it.",
             ""]
    todo, fix, stale, norefs = [], [], [], {}
    for fam in sorted(fams):
        fp = fps[fam]
        prev = old.get(fam)
        if prev and prev[0] != fp and prev[0] in _fingerprint_variants([o for o, _g in fams[fam]]):
            fp = prev[0]  # unchanged: a number sat on a rounding edge (float noise) — the answered fingerprint stays
        if prev and prev[0] != fp and prev[0] == _fingerprint_v1([o for o, _g in fams[fam]]):
            prev = (fp, prev[1])  # answered under the old box-only fingerprint and unchanged since: re-stamp
        body = prev[1] if prev else "TODO"
        if prev and prev[0] != fp and body != "TODO":
            stale.append(fam)
            # the last real answer stays WHOLE inside the wrapper — never nested, never cut (nesting it on every
            # change truncated answers away: measured on the M107 after a few rebuilds)
            m_ = re.match(r"TODO \(changed since: (.*)\)$", body)
            body = f"TODO (changed since: {m_.group(1) if m_ else body})"
        if body.startswith("TODO") or not all(f in body for f in FIELDS):
            todo.append(fam)
        elif re.search(r"verdict:\s*fix", body):
            fix.append(fam)
        else:
            _ok, probs = review_refs.ref_problems(body, repo)
            if probs:
                norefs[fam] = probs
        lines.append(f"- {fam} [{fp}]: {body}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return todo, fix, stale, norefs


TILES = "tiles-2"  # bump when the tiles' look changes: every tile is rendered again


def part_tiles(asset, fams, out_dir, world, size=360, fps=None, todo=(), changed_only=False):
    """two workbench tiles per family: in context (the family orange, the rest pale) and isolated (3/4 view).
    Rendered ON DEMAND: a family keeps its tiles while its fingerprint is unchanged — on a full build only while
    nothing else changed either (its context view shows the neighbours), on a --geo check (changed_only) whatever
    the rest did: fresh tiles for exactly the parts that changed, in seconds.
    -> (index [{family, members, tiles, visible, size, materials, fp, scene}], tiles rendered); out_dir/index.json
    also lists `todo` (the families the review asks about: partsheet.py gives them their own sheet)."""
    fps = fps or fingerprints(fams)
    old = {}
    try:
        with open(os.path.join(out_dir, "index.json"), encoding="utf-8") as fh:
            prev = json.load(fh)
        if prev.get("tiles") == f"{TILES}/{size}":
            old = {e["family"]: e for e in prev.get("families", []) if e.get("fp")}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        old = {}
    # the context view shows every part AND floater; the caption shows mm: all of it decides whether a tile is current
    floats = sorted((o for o, _g in getattr(asset, "_floater_parts", ())), key=lambda o: o.name)
    scene_fp = hashlib.sha1(("".join(f"{f}:{fps[f]};" for f in sorted(fps))
                             + "".join(f"{o.name}:{_fingerprint([o])};" for o in floats)
                             + f"|{getattr(asset, 'mm_per_stud', None)}").encode()).hexdigest()[:12]

    def reusable(fam):
        e = old.get(fam)
        return (e is not None and e["fp"] == fps[fam] and (changed_only or e.get("scene") == scene_fp)
                and all(os.path.isfile(os.path.join(out_dir, t)) for t in e.get("tiles", ())))

    rendered = 0
    sc = asset.scene
    keep = {"engine": sc.render.engine, "rx": sc.render.resolution_x, "ry": sc.render.resolution_y,
            "film": sc.render.film_transparent, "cam": sc.camera, "vt": sc.view_settings.view_transform,
            "look": sc.view_settings.look, "exposure": sc.view_settings.exposure}
    sh = sc.display.shading
    keep_sh = (sh.light, sh.color_type, tuple(sh.single_color), sh.show_object_outline, sh.show_xray, sh.xray_alpha)
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.view_settings.exposure = 0.0  # (a studio render before this must not leave its exposure)
    sc.render.film_transparent = False
    sc.render.resolution_x = sc.render.resolution_y = size
    sh.light = "STUDIO"
    sh.color_type = "OBJECT"
    sh.show_object_outline = True
    os.makedirs(out_dir, exist_ok=True)
    all_objs = [o for o, _g in world.parts]
    hidden_before = {o.name: o.hide_render for o in sc.objects}
    old_color = {o.name: tuple(o.color) for o in all_objs}
    cam = bpy.data.objects.new("PartCam", bpy.data.cameras.new("PartCam"))
    sc.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    sc.camera = cam
    index = []
    try:
        for fam, members in sorted(fams.items()):
            objs = [o for o, _g in members]
            cs = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
            lo = Vector([min(c[i] for c in cs) for i in range(3)])
            hi = Vector([max(c[i] for c in cs) for i in range(3)])
            ctr = (lo + hi) / 2
            span = max((hi - lo).length, world.diag * 0.04)
            k0 = world.index.get(objs[0].name)
            frac, dirs = world.visibility(k0) if k0 is not None else (0.0, [])
            # the most-seen direction (or the right side) for the context view
            dvec = Vector((1, 0, 0))
            for d in DIRS:
                if dirs and _dir_name(d) == dirs[0]:
                    dvec = d
            if reusable(fam):
                e = old[fam]
                index.append({**e, "members": [base(o.name) for o in objs], "visible": round(frac, 2),
                              "seen_from": dirs, "size": _mm(asset, max(hi - lo)),
                              "materials": sorted({m.name for o in objs for m in o.data.materials if m})})
                continue
            rendered += 1
            tiles = []
            # a part you can barely see from outside is reviewed through an X-ray of everything else
            sh.show_xray = frac < 0.3
            sh.xray_alpha = 0.22
            first = objs[0]
            fcs = [first.matrix_world @ Vector(c) for c in first.bound_box]
            flo = Vector([min(c[i] for c in fcs) for i in range(3)])
            fhi = Vector([max(c[i] for c in fcs) for i in range(3)])
            for mode in ("context", "isolated"):
                for o in sc.objects:
                    if o.type == "MESH":
                        o.hide_render = (mode == "isolated" and o not in objs) or hidden_before.get(o.name, False)
                for o in all_objs:
                    o.color = (1.0, 0.45, 0.05, 1) if o in objs else (0.82, 0.83, 0.85, 1)
                view = dvec if mode == "context" else Vector((0.8, -0.9, 0.55)).normalized()
                # isolated: frame ONE member (members can be 650 mm apart: two dots tell you nothing)
                c_, sp_ = (ctr, span) if mode == "context" else ((flo + fhi) / 2, max((fhi - flo).length, world.diag * 0.02))
                cam.data.ortho_scale = sp_ * (2.6 if mode == "context" else 1.25)
                cam.location = c_ + view * (world.diag * 3)
                cam.data.clip_end = world.diag * 8
                cam.rotation_euler = (c_ - cam.location).to_track_quat("-Z", "Z" if abs(view.z) < 0.95 else "Y").to_euler()
                tile = os.path.join(out_dir, f"{fam}_{mode}.png")
                sc.render.filepath = tile
                bpy.ops.render.render(write_still=True)
                tiles.append(os.path.relpath(tile, out_dir).replace("\\", "/"))
            mats = sorted({m.name for o in objs for m in o.data.materials if m})
            ext = hi - lo
            index.append({"family": fam, "members": [base(o.name) for o in objs], "tiles": tiles,
                          "visible": round(frac, 2), "seen_from": dirs,
                          "size": _mm(asset, max(ext)), "materials": mats, "fp": fps[fam], "scene": scene_fp})
    finally:
        for o in sc.objects:
            if o.name in hidden_before:
                o.hide_render = hidden_before[o.name]
        for o in all_objs:
            o.color = old_color[o.name]
        bpy.data.objects.remove(cam)
        sc.render.engine = keep["engine"]
        sc.render.resolution_x, sc.render.resolution_y = keep["rx"], keep["ry"]
        sc.render.film_transparent = keep["film"]
        sc.camera = keep["cam"]
        sc.view_settings.view_transform = keep["vt"]
        sc.view_settings.look = keep["look"]  # (the whole view: a studio render after this must find its own)
        sc.view_settings.exposure = keep["exposure"]
        sh.light, sh.color_type, sh.single_color, sh.show_object_outline = keep_sh[0], keep_sh[1], keep_sh[2], keep_sh[3]
        sh.show_xray, sh.xray_alpha = keep_sh[4], keep_sh[5]
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"asset": asset.name, "tiles": f"{TILES}/{size}", "todo": sorted(set(todo)), "families": index},
                  fh, indent=1)
    return index, rendered
