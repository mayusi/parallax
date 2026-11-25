"""dissect.py — what a reference model's part is MADE of, beyond its size (used by kit/refs/inspect_model.py, inside
Blender; geometry in metres, every result in mm): its edges and bevels, how it was made (CAD-like flats, a smooth
surface, a sculpt or a scan), its UV layout and texture density, the detail its normal map carries, its colour and wear.

Every function takes the part's WELDED world-space bmesh (inspect_model.part_mesh) — a game mesh split at UV seams
would otherwise be all open edges.

EDGES AND BEVELS. The part is split into FLAT PATCHES (faces grown from a seed while their normal stays within 3 deg
of the seed's). A big patch is a face of the part; a thin one (narrow for its length, under 6% of the part's size
across) or a small one is a TRANSITION face. Transition faces that touch form a NETWORK: a bevel strip (or a net of
strips meeting at corners), or a curved surface when it is wide. For a bevel network, with L = half the length of its
border with the big faces:
    surface width  w = area / L            turning  t = sum(edge angle x edge length) / L   (the corner's angle)
    chamfer (the turning happens at its two borders) : size = w / (2 sin(t / 2))   = the CAD chamfer's offset
    round   (the turning is spread across its faces): size = w / t              = the CAD fillet's radius
An edge between two big faces turning more than 30 deg is SHARP (never bevelled).
"""

import math
import os

import numpy as np

HARD_DEG = 30.0      # an edge turning more than this is a hard edge
PATCH_DEG = 3.0      # faces within this of a patch's seed normal are one flat patch


def _patches(bm):
    """-> (patch id per face, [(normal, area, [face indices], bbox diagonal)])"""
    bm.faces.ensure_lookup_table()
    faces = bm.faces
    area = [f.calc_area() for f in faces]
    pid = [-1] * len(faces)
    cos_t = math.cos(math.radians(PATCH_DEG))
    out = []
    for s in sorted(range(len(faces)), key=lambda i: -area[i]):
        if pid[s] != -1:
            continue
        n0, k = faces[s].normal.copy(), len(out)
        pid[s], stack, members, a = k, [s], [], 0.0
        lo = [1e9] * 3
        hi = [-1e9] * 3
        while stack:
            i = stack.pop()
            f = faces[i]
            members.append(i)
            a += area[i]
            for v in f.verts:
                for c in range(3):
                    lo[c] = min(lo[c], v.co[c])
                    hi[c] = max(hi[c], v.co[c])
            for e in f.edges:
                for g in e.link_faces:
                    j = g.index
                    if pid[j] == -1 and g.normal.dot(n0) >= cos_t:
                        pid[j] = k
                        stack.append(j)
        diag = math.sqrt(sum((hi[c] - lo[c]) ** 2 for c in range(3)))
        out.append((n0, a, members, diag))
    return pid, out, area


def _sag(e, area):
    """a facet edge's sagitta (metres): its narrower face's width across x the angle / 8"""
    ln = e.calc_length()
    if ln <= 0:
        return 0.0
    # a face's width across from this edge: a triangle's height is 2 x area / base, a quad's width area / length
    chord = min((2.0 if len(f.verts) == 3 else 1.0) * area[f.index] / ln for f in e.link_faces)
    return chord * e.calc_face_angle(0.0) / 8.0


def _classify(bm, size):
    """-> (patch id per face, patches, face areas, major per patch): a patch is MAJOR (a face of the part) when it has
    0.5%+ of the area and is not a strip (narrow for its length: under 6% of the part's size across)"""
    pid, patches, area = _patches(bm)
    total = sum(area) or 1e-12
    thin_w = 0.06 * size
    major = []
    for _n, a, _members, diag in patches:
        w = a / max(diag, 1e-12)
        major.append(a >= 0.005 * total and not (w < thin_w and w / max(diag, 1e-12) < 0.1))
    return pid, patches, area, major


def edges(bm, size):
    """the part's edges: sharp ones, bevels (width, chamfer or round, the CAD size), flat and curved shares.
    size = the part's longest own extent (metres)."""
    if not bm.faces:
        return None
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.verts.index_update()   # (sharp_runs joins edges by vertex index: a bmesh built with verts.new has dirty ones)
    pid, patches, area, major = _classify(bm, size)
    total = sum(area) or 1e-12
    trans = [not major[pid[i]] for i in range(len(pid))]
    # sharp edges: two different big faces meeting at a hard angle
    sharp_m = 0.0
    sharp_n = 0
    sharp_e = []
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) != 2:
            continue
        a, b = lf[0].index, lf[1].index
        if trans[a] or trans[b] or pid[a] == pid[b]:
            continue
        if math.degrees(e.calc_face_angle(0.0)) > HARD_DEG:
            sharp_m += e.calc_length()
            sharp_n += 1
            sharp_e.append(e)
    # transition networks
    net = [-1] * len(pid)
    nets = []
    for s in range(len(pid)):
        if not trans[s] or net[s] != -1:
            continue
        k = len(nets)
        net[s], stack, members = k, [s], []
        while stack:
            i = stack.pop()
            members.append(i)
            for e in bm.faces[i].edges:
                for g in e.link_faces:
                    j = g.index
                    if trans[j] and net[j] == -1:
                        net[j] = k
                        stack.append(j)
        nets.append(members)
    bevels, curved = [], 0.0
    near_cut = None  # the biggest bevel-like network whose width sits near the 10%-of-size line (see below)
    facets = []  # (angle deg, length m) of the steps a CURVED surface turns by: its faceting
    for e in bm.edges:  # a polygon standing in for a curve: two big facets turning a little (2..30 deg)
        lf = e.link_faces
        if len(lf) == 2 and not trans[lf[0].index] and not trans[lf[1].index] and pid[lf[0].index] != pid[lf[1].index]:
            ang = math.degrees(e.calc_face_angle(0.0))
            if 2.0 < ang <= HARD_DEG:
                facets.append((ang, e.calc_length(), _sag(e, area)))
    for members in nets:
        mset = set(members)
        a_net = sum(area[i] for i in members)
        border, turn_border, turn_all, majors = 0.0, 0.0, 0.0, set()
        seen, inner = set(), []
        for i in members:
            for e in bm.faces[i].edges:
                if e.index in seen:
                    continue
                seen.add(e.index)
                lf = e.link_faces
                if len(lf) != 2:
                    continue
                ln = e.calc_length()
                ang = e.calc_face_angle(0.0)
                other = lf[1].index if lf[0].index in mset else lf[0].index
                inside = lf[0].index in mset and lf[1].index in mset
                turn_all += ang * ln
                if inside and 0.5 < math.degrees(ang) <= 75.0:  # (a 90-deg groove is a feature, not a facet)
                    inner.append((math.degrees(ang), ln, _sag(e, area)))
                if not inside and not trans[other]:
                    border += ln
                    turn_border += ang * ln
                    majors.add(pid[other])
        L = border / 2.0
        w = a_net / L if L > 0 else float("inf")
        if majors and L > 0 and 0.75 * 0.10 * size <= w <= 1.25 * 0.10 * size and (
                near_cut is None or a_net > near_cut[0]):
            # a network this close to the line flips between "bevels" and "a curved surface" on a small, unrelated
            # change (the Glock's lofted grip + every fillet as ONE network: 84% bevelled at 19.2 mm wide, 0% at 22.9,
            # the same real edges both times, 2026-10-10) — the share is unreliable then; the sharp runs are not
            near_cut = (a_net, w)
        if not majors or w >= 0.10 * size or L <= 0:  # wider than 10% of the part: a curved surface
            curved += a_net
            facets += inner
            continue
        t = turn_all / L
        share = turn_border / turn_all if turn_all > 0 else 1.0
        chamfer = share > 0.7
        cad = w / (2 * math.sin(t / 2)) if chamfer and t > 1e-6 else (w / t if t > 1e-6 else w)
        bevels.append({"length_mm": L * 1000, "width_mm": w * 1000, "size_mm": cad * 1000, "turn_deg": math.degrees(t),
                       "chamfer": chamfer, "segments": 1 if chamfer else max(2, round(1 / max(share, 1e-3)))})
    bev_len = sum(b["length_mm"] for b in bevels)

    def q(vals, f):
        if not vals:
            return None
        vals = sorted(vals)
        return round(vals[min(len(vals) - 1, int(f * len(vals)))], 2)

    sizes = [b["size_mm"] for b in bevels for _ in range(max(1, int(b["length_mm"] // 2)))]  # length-weighted
    flat = sum(a for (n, a, m, d), mj in zip(patches, major) if mj)
    facet_mm = sum(f[1] for f in facets) * 1000
    total_f = sum(f[1] for f in facets)

    def weighted(vals, frac):  # [(value, weight)] -> the value at that share of the weight
        acc = 0.0
        for v, w_ in sorted(vals):
            acc += w_
            if acc >= frac * total_f:
                return v
        return None

    facet_deg = round(weighted([(f[0], f[1]) for f in facets], 0.5), 1) if facets else None
    facet_sag = weighted([(f[2], f[1]) for f in facets], 0.9) if facets else None
    return {
        "facet_deg": facet_deg, "facet_mm": round(facet_mm, 1),
        # how far the facets sit from the true curve (sagitta ~ chord x angle / 8), the worst tenth: 22 deg steps on a
        # 3 mm pin are 0.03 mm off (invisible), on a 20 mm barrel 0.2 mm (they show)
        "facet_sag_mm": round(facet_sag * 1000, 3) if facet_sag is not None else None,
        "sharp_edges": sharp_n, "sharp_mm": round(sharp_m * 1000, 1),
        "bevels": len(bevels), "bevel_mm": round(bev_len, 1),
        "bevel_size_mm": {"p10": q(sizes, 0.1), "typical": q(sizes, 0.5), "p90": q(sizes, 0.9)} if bevels else None,
        "chamfer_share": round(sum(b["length_mm"] for b in bevels if b["chamfer"]) / bev_len, 2) if bev_len else None,
        "round_segments": q([b["segments"] for b in bevels if not b["chamfer"]], 0.5),
        "bevelled_share": round(bev_len / (bev_len + sharp_m * 1000), 2) if (bev_len + sharp_m) > 0 else None,
        "sharp_runs": sharp_runs(sharp_e),
        **({"share_unreliable": {"network_mm2": round(near_cut[0] * 1e6), "width_mm": round(near_cut[1] * 1000, 1),
                                 "line_mm": round(0.10 * size * 1000, 1)}} if near_cut else {}),
        "flat_share": round(flat / total, 2), "curved_share": round(curved / total, 2),
    }


def sharp_runs(sharp_edges, top=5):
    """the sharp edges joined into RUNS (edges sharing a vertex) -> the longest `top`: [{"mm": length, "at": its
    length-weighted centre (the mesh's own units x 1000: mm when the mesh is in metres), "deg": its mean angle}] —
    WHERE a part's sharp edges are, not only how many mm (a gate that says "309 mm sharp" sends you hunting)"""
    parent = {}

    def find(v):
        while parent.setdefault(v, v) != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    for e in sharp_edges:
        a, b = (find(v.index) for v in e.verts)
        if a != b:
            parent[a] = b
    runs = {}
    for e in sharp_edges:
        r = runs.setdefault(find(e.verts[0].index), [0.0, [0.0, 0.0, 0.0], 0.0])
        ln = e.calc_length()
        mid = (e.verts[0].co + e.verts[1].co) / 2
        r[0] += ln
        for i in range(3):
            r[1][i] += mid[i] * ln
        r[2] += math.degrees(e.calc_face_angle(0.0)) * ln
    out = [{"mm": round(ln * 1000, 1), "at": [round(c / ln * 1000, 1) for c in cs], "deg": round(dg / ln)}
           for ln, cs, dg in runs.values() if ln > 0]
    return sorted(out, key=lambda r: -r["mm"])[:top]


def surface(bm, edge_info):
    """how the part was MADE: faces per cm2, surface noise (each face's tilt from the mean of its neighbours, away from
    hard edges: a sculpt or a scan is bumpy; a CAD flat or a smooth subdivision surface is not — a cylinder's faces
    tilt both ways and cancel), edge-length spread (a sculpt / remesh has even edges, a CAD export long slivers),
    and a label: cad (mostly flats, quiet), smooth (curved, quiet), sculpt_or_scan (bumpy and dense), faceted (bumpy,
    sparse: a low-poly curve)"""
    if not bm.faces:
        return None
    bm.faces.ensure_lookup_table()
    hard = math.radians(HARD_DEG)
    area = [f.calc_area() for f in bm.faces]
    total = sum(area) or 1e-12
    num = den = 0.0
    for f in bm.faces:
        nb, ok = None, True
        for e in f.edges:
            lf = e.link_faces
            if len(lf) != 2 or e.calc_face_angle(0.0) > hard:
                ok = False
                break
            g = lf[1] if lf[0] is f else lf[0]
            nb = g.normal * area[g.index] if nb is None else nb + g.normal * area[g.index]
        if not ok or nb is None or nb.length < 1e-12:
            continue
        num += math.degrees(f.normal.angle(nb.normalized(), 0.0)) * area[f.index]
        den += area[f.index]
    noise = num / den if den > 0 else 0.0
    lengths = [e.calc_length() for e in bm.edges]
    mean = sum(lengths) / max(len(lengths), 1)
    cv = (sum((x - mean) ** 2 for x in lengths) / max(len(lengths), 1)) ** 0.5 / mean if mean > 0 else 0.0
    per_cm2 = len(bm.faces) / (total * 1e4)
    flat = (edge_info or {}).get("flat_share") or 0.0
    if noise >= 3.0:
        made = "sculpt_or_scan" if per_cm2 >= 100 else "faceted"
    else:
        made = "cad" if flat >= 0.5 else "smooth"
    return {"faces_per_cm2": round(per_cm2, 1), "noise_deg": round(noise, 2), "edge_length_cv": round(cv, 2),
            "quiet_share": round(den / total, 2), "made_as": made}


def _uv_islands(bm, uv):
    """-> (island id per face, seam length m, seam length on hard edges m): faces sharing an edge whose UVs match on
    both sides are one island; an edge whose UVs differ is a seam"""
    bm.faces.ensure_lookup_table()
    bm.verts.index_update()
    up = list(range(len(bm.faces)))

    def root(i):
        while up[i] != i:
            up[i] = up[up[i]]
            i = up[i]
        return i

    hard = math.radians(HARD_DEG)
    seam = hard_seam = 0.0
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) != 2:
            continue
        a = {lp.vert.index: lp[uv].uv for lp in lf[0].loops}
        b = {lp.vert.index: lp[uv].uv for lp in lf[1].loops}
        if all((a[v.index] - b[v.index]).length < 1e-5 for v in e.verts):
            ra, rb = root(lf[0].index), root(lf[1].index)
            if ra != rb:
                up[ra] = rb
        else:
            seam += e.calc_length()
            if e.calc_face_angle(0.0) > hard:
                hard_seam += e.calc_length()
    return [root(i) for i in range(len(up))], seam, hard_seam


def uv_layout(bm, tex=None, size=None):
    """the part's UV layout: islands, seams (and how many sit on hard edges — where a seam belongs), texture density
    in px/mm on the biggest map (tex = (width, height)), stretch (each triangle's px-per-mm along its two principal
    directions: 1.5x apart or more = stretched), mirrored triangles (the minority flipped against the rest), UV area
    used. None: no UVs."""
    uv = bm.loops.layers.uv.active if bm.loops.layers.uv else None
    if uv is None or not bm.faces:
        return None
    roots, seam, hard_seam = _uv_islands(bm, uv)
    if size is None:
        lo = [min(v.co[i] for v in bm.verts) for i in range(3)]
        hi = [max(v.co[i] for v in bm.verts) for i in range(3)]
        size = max(h - lo_ for lo_, h in zip(lo, hi))
    pid, _patches_, _area, major = _classify(bm, size)
    across = 0.0  # seam length running THROUGH a flat face (both sides in one big patch): a seam that shows
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) != 2 or pid[lf[0].index] != pid[lf[1].index] or not major[pid[lf[0].index]]:
            continue
        a_ = {lp.vert.index: lp[uv].uv for lp in lf[0].loops}
        b_ = {lp.vert.index: lp[uv].uv for lp in lf[1].loops}
        if not all((a_[v.index] - b_[v.index]).length < 1e-5 for v in e.verts):
            across += e.calc_length()
    islands = len(set(roots))
    W, H = tex if tex else (1, 1)
    p, q = [], []
    for f in bm.faces:  # fan triangles: 3D corners and UV corners
        ls = f.loops
        for k in range(1, len(ls) - 1):
            p.append([ls[0].vert.co[:], ls[k].vert.co[:], ls[k + 1].vert.co[:]])
            q.append([ls[0][uv].uv[:], ls[k][uv].uv[:], ls[k + 1][uv].uv[:]])
    p = np.asarray(p, dtype=np.float64) * 1000.0  # mm
    q = np.asarray(q, dtype=np.float64) * np.array([W, H])  # px
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    n = np.cross(e1, e2)
    a3 = np.linalg.norm(n, axis=1) / 2
    ok = a3 > 1e-12
    x = e1 / np.maximum(np.linalg.norm(e1, axis=1, keepdims=True), 1e-12)
    y = np.cross(n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12), x)
    P = np.stack([np.stack([(e1 * x).sum(1), (e2 * x).sum(1)], 1), np.stack([(e1 * y).sum(1), (e2 * y).sum(1)], 1)], 1)
    u1, u2 = q[:, 1] - q[:, 0], q[:, 2] - q[:, 0]
    Q = np.stack([np.stack([u1[:, 0], u2[:, 0]], 1), np.stack([u1[:, 1], u2[:, 1]], 1)], 1)
    det_p = P[:, 0, 0] * P[:, 1, 1] - P[:, 0, 1] * P[:, 1, 0]
    ok &= np.abs(det_p) > 1e-12
    J = np.einsum("nij,njk->nik", Q[ok], np.linalg.inv(P[ok]))  # px per mm, per triangle
    s = np.linalg.svd(J, compute_uv=False)
    w = a3[ok]
    tot = w.sum() or 1e-12
    aniso = s[:, 0] / np.maximum(s[:, 1], 1e-12)
    uv_area = np.abs(u1[:, 0] * u2[:, 1] - u1[:, 1] * u2[:, 0])[ok] / 2  # px^2 (UV units^2 without a map)
    density = float(np.sqrt(uv_area.sum() / tot))
    out = {"islands": islands, "seam_mm": round(seam * 1000, 1),
           "seams_on_hard_edges": round(hard_seam / seam, 2) if seam > 0 else None,
           "seams_across_flats": round(across / seam, 2) if seam > 0 else None,
           "stretched_share": round(float(w[aniso > 1.5].sum() / tot), 2),
           # mirrored = flipped against the part's OWN majority (a UV reused for a symmetric half); a whole model whose
           # UVs are all flipped (another program's V convention) is not mirrored
           "mirrored_share": round(float(min(w[np.linalg.det(J) < 0].sum(), w[np.linalg.det(J) >= 0].sum()) / tot), 2),
           "uv_area": round(float(uv_area.sum() / (W * H)), 4)}
    if tex:
        out["px_per_mm"] = round(density, 2)
        out["map_px"] = [W, H]
    return out


def _raster(tris, w, h):
    """the pixels (centres) inside these triangles, given in pixel coordinates (origin bottom-left, like UVs)"""
    mask = np.zeros((h, w), bool)
    for t in tris:
        x0, y0 = np.maximum(np.floor(t.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(t.max(0)).astype(int), [w - 1, h - 1])
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = t
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        l1 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / d
        l2 = ((cy - ay) * (xs - cx) + (ax - cx) * (ys - cy)) / d
        mask[y0:y1 + 1, x0:x1 + 1] |= (l1 >= -1e-9) & (l2 >= -1e-9) & (l1 + l2 <= 1 + 1e-9)
    return mask


def baked_detail(bm, img, out_png=None, work=2048):
    """the detail a part's NORMAL MAP carries (where a game model keeps its sculpt: checkering, stippling, dents):
    its strength under the part's own UVs (the angle the map tilts the surface: mean / p90, the share tilted > 5 deg),
    the repeating PATTERN on its biggest UV island (the spectrum's strongest peak -> its pitch in mm, with how far it
    stands out), and its RELIEF: the height the slopes integrate to (Frankot-Chellappa; detail finer than 8 mm), in
    mm, saved as a picture."""
    import bpy  # noqa: PLC0415  (inside Blender only)

    uv = bm.loops.layers.uv.active if bm.loops.layers.uv else None
    if uv is None or img is None or not bm.faces or img.size[0] == 0:
        return None
    W, H = img.size
    k = min(1.0, work / max(W, H))
    src = img
    if k < 1.0:
        src = img.copy()
        src.scale(max(1, int(W * k)), max(1, int(H * k)))
    w, h = src.size
    a = np.empty(w * h * 4, np.float32)
    src.pixels.foreach_get(a)
    if src is not img:
        bpy.data.images.remove(src)
    n = a.reshape(h, w, 4)[..., :3] * 2.0 - 1.0
    roots, _, _ = _uv_islands(bm, uv)
    tris, area3, isl = [], [], []
    for f in bm.faces:
        ls = f.loops
        for j in range(1, len(ls) - 1):
            t = np.array([ls[0][uv].uv[:], ls[j][uv].uv[:], ls[j + 1][uv].uv[:]], float)
            base = np.floor(t.min(0))
            if (np.floor(t.max(0) - 1e-9) != base).any():
                continue  # crosses a tile's edge
            p0, p1, p2 = ls[0].vert.co, ls[j].vert.co, ls[j + 1].vert.co
            tris.append((t - base) * [w, h])
            area3.append((p1 - p0).cross(p2 - p0).length / 2 * 1e6)  # mm2
            isl.append(roots[f.index])
    if not tris:
        return None
    mask = _raster(tris, w, h)
    if not mask.any():
        return None
    nn = n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-6)
    ang = np.degrees(np.arccos(np.clip(nn[..., 2], -1, 1)))[mask]
    out = {"map_px": [W, H], "strength_deg": round(float(ang.mean()), 2),
           "p90_deg": round(float(np.percentile(ang, 90)), 2), "detail_share": round(float((ang > 5).mean()), 3)}

    def uv_area(t):
        return abs((t[1, 0] - t[0, 0]) * (t[2, 1] - t[0, 1]) - (t[1, 1] - t[0, 1]) * (t[2, 0] - t[0, 0])) / 2

    by = {}
    for t, a3, i in zip(tris, area3, isl):
        g = by.setdefault(i, [[], 0.0, 0.0])
        g[0].append(t)
        g[1] += a3
        g[2] += uv_area(t)
    ts, mm2, px2 = max(by.values(), key=lambda g: g[2])
    px_mm = (px2 / mm2) ** 0.5 if mm2 > 0 else None  # working px per mm on that island
    m = _raster(ts, w, h)
    ys, xs = np.nonzero(m)
    if not px_mm or len(xs) < 64:
        return out
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    mc = m[y0:y1, x0:x1]
    # the island's INSIDE, 1 mm (at least 3 px) in from its border: a seam usually runs along a hard edge, where a baked
    # map carries the rounded-edge shading — a shape, not detail
    for _ in range(max(3, int(round(px_mm)))):
        mc = mc & np.roll(mc, 1, 0) & np.roll(mc, -1, 0) & np.roll(mc, 1, 1) & np.roll(mc, -1, 1)
    if mc.sum() < 64:
        return out
    nzc = np.clip(nn[y0:y1, x0:x1, 2], 0.05, 1.0)
    P = np.where(mc, -nn[y0:y1, x0:x1, 0] / nzc, 0.0)
    Q = np.where(mc, -nn[y0:y1, x0:x1, 1] / nzc, 0.0)
    P[mc] -= P[mc].mean()
    Q[mc] -= Q[mc].mean()
    ch, cw = P.shape
    win = np.outer(np.hanning(ch), np.hanning(cw))
    S = np.abs(np.fft.rfft2(P * win)) ** 2 + np.abs(np.fft.rfft2(Q * win)) ** 2
    fr = np.sqrt(np.fft.rfftfreq(cw)[None, :] ** 2 + np.fft.fftfreq(ch)[:, None] ** 2)  # cycles per px
    ok = (fr > 3.0 / min(ch, cw)) & (fr < 1 / 2.5)
    # (only an in-band frequency can win, and only with some power: on a flat map every in-band S is 0, argmax fell to
    # the zero frequency and the pitch was 1 / 0 - an infinity no JSON reader takes; `kit library inspect` crashed)
    if ok.any() and float(S[ok].max()) > 0.0:
        i = int(np.argmax(np.where(ok, S, -1.0)))
        prom = float(S.flat[i] / max(np.median(S[ok]), 1e-12))
        out["pattern"] = {"pitch_mm": round(float(1 / fr.flat[i] / px_mm), 3), "prominence": round(prom, 1),
                          # a peak counts only on a part that CARRIES detail (5%+ of it tilted): on a near-flat map
                          # the strongest peak is compression noise
                          "found": prom >= 15.0 and out["detail_share"] >= 0.05}
    # relief: the height whose slopes are P, Q (px / px), then px -> mm — DETAIL only: waves longer than 8 mm are left
    # out (a baked rounded edge or a curved surface's normals would integrate into millimetres of fake relief)
    wy = 2 * np.pi * np.fft.fftfreq(ch)[:, None]
    wx = 2 * np.pi * np.fft.fftfreq(cw)[None, :]
    d = wx ** 2 + wy ** 2
    d[0, 0] = 1.0
    Z = (-1j * wx * np.fft.fft2(P) - 1j * wy * np.fft.fft2(Q)) / d
    Z[np.sqrt(d) < 2 * np.pi / (8.0 * px_mm)] = 0
    hgt = np.real(np.fft.ifft2(Z))
    hv = hgt[mc]
    lo, hi = np.percentile(hv, 1), np.percentile(hv, 99)
    out["relief_mm"] = round(float((hi - lo) / px_mm), 4)
    out["island_px_per_mm"] = round(px_mm / k, 2)
    if out_png:
        os.makedirs(os.path.dirname(out_png), exist_ok=True)
        g = np.clip((hgt - lo) / max(hi - lo, 1e-9), 0, 1) * mc
        im = bpy.data.images.new("relief", cw, ch)
        im.pixels.foreach_set(np.dstack([g, g, g, np.ones_like(g)]).astype(np.float32).ravel())
        im.filepath_raw = out_png
        im.file_format = "PNG"
        im.save()
        bpy.data.images.remove(im)
        out["relief_png"] = out_png
    return out


def colour_wear(bm, maps, samples=20000, edge_mm=0.7, flat_mm=4.0):
    """colour, roughness and metal under the part's own UVs (sampled at points spread over its surface by area), and
    WEAR measured where it happens: each sample's distance to the nearest OUTWARD (convex) hard edge and to the nearest
    INWARD (concave) one. edge wear = brightness within edge_mm of an outward edge minus brightness on flats (further
    than flat_mm from any edge): worn bluing / paint shows bright metal; grime = the same inside recesses (dark = dirt).
    maps = {"Base Color": (array h x w x 4, None), "Roughness": (array, channel), "Metallic": (array, channel)}"""
    from mathutils import kdtree  # noqa: PLC0415  (inside Blender only)

    uv = bm.loops.layers.uv.active if bm.loops.layers.uv else None
    base = (maps or {}).get("Base Color")
    if uv is None or base is None or not bm.faces:
        return None
    # the hard edges, split by which way they turn, as points every 0.25 mm
    feats = {"convex": [], "concave": []}
    for e in bm.edges:
        lf = e.link_faces
        if len(lf) != 2 or math.degrees(e.calc_face_angle(0.0)) < 20.0:
            continue
        f1, f2 = lf
        side = "concave" if (f2.calc_center_median() - f1.calc_center_median()).dot(f1.normal) > 0 else "convex"
        a, b = e.verts[0].co, e.verts[1].co
        steps = max(1, int(e.calc_length() * 1000 / 0.25))
        feats[side] += [a.lerp(b, i / steps) for i in range(steps + 1)]
    trees = {}
    for side, pts in feats.items():
        if pts:
            t = kdtree.KDTree(len(pts))
            for i, p in enumerate(pts):
                t.insert(p, i)
            t.balance()
            trees[side] = t
    # samples spread by area
    tri, uvs, areas = [], [], []
    for f in bm.faces:
        ls = f.loops
        for j in range(1, len(ls) - 1):
            tri.append([ls[0].vert.co[:], ls[j].vert.co[:], ls[j + 1].vert.co[:]])
            uvs.append([ls[0][uv].uv[:], ls[j][uv].uv[:], ls[j + 1][uv].uv[:]])
    tri, uvs = np.asarray(tri), np.asarray(uvs)
    areas = np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1) / 2
    if areas.sum() <= 0:
        return None
    rng = np.random.default_rng(0)
    pick = rng.choice(len(tri), size=samples, p=areas / areas.sum())
    r1, r2 = rng.random(samples), rng.random(samples)
    flip = r1 + r2 > 1
    r1[flip], r2[flip] = 1 - r1[flip], 1 - r2[flip]
    bary = np.stack([1 - r1 - r2, r1, r2], 1)[:, :, None]
    pos = (tri[pick] * bary).sum(1)
    st = (uvs[pick] * bary).sum(1) % 1.0

    def look(arr):
        h, w = arr.shape[:2]
        return arr[np.clip((st[:, 1] * h).astype(int), 0, h - 1), np.clip((st[:, 0] * w).astype(int), 0, w - 1)]

    rgb = look(base[0])[:, :3]
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    out = {"colour_mean": [round(float(c), 3) for c in rgb.mean(0)], "brightness_spread": round(float(lum.std()), 3)}
    for role in ("Roughness", "Metallic"):
        if (maps or {}).get(role) is not None:
            arr, ch = maps[role]
            v = look(arr)[:, ch if ch is not None else 0]
            out[role.lower() + "_range"] = [round(float(np.percentile(v, 10)), 3), round(float(np.percentile(v, 90)), 3)]

    def dist(side):
        t = trees.get(side)
        if t is None:
            return np.full(samples, np.inf)
        return np.array([t.find(p)[2] for p in pos]) * 1000.0  # mm

    d_cvx, d_ccv = dist("convex"), dist("concave")
    flat = (d_cvx > flat_mm) & (d_ccv > flat_mm)
    edge = d_cvx < edge_mm
    recess = d_ccv < edge_mm
    if flat.sum() >= 50:
        if edge.sum() >= 50:
            out["edge_wear"] = round(float(lum[edge].mean() - lum[flat].mean()), 3)
        if recess.sum() >= 50:
            out["grime"] = round(float(lum[recess].mean() - lum[flat].mean()), 3)
    out["zones"] = {"edge": int(edge.sum()), "recess": int(recess.sum()), "flat": int(flat.sum())}
    return out
