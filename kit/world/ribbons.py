"""ribbons.py - RIVERS AS RIBBON MESHES that drain into the land's sinks (LIMITATIONS_FIXES_V4 5.1 / 5.4 step 3 /
13.5: "ribbon river meshes -> --sink", "scrolling UV MeshPart rivers draining into --sink").

    python kit/world/ribbons.py <heightmap.hm.json> [--share 0.012] [--out <dir>] [--allow-pits]

kit world rivers paints the cells where the most water gathers as Roblox Water (voxels): flat, still, and a river
that ran into a pit pooled there unsaid. This traces each river as a LINE (D8: every cell's water to its lowest
neighbour, as kit/world/rivers.py routes it; the map's edge and the heightmap's own --sink basins, recorded in its
recipe, are where water leaves the land) and lays a RIBBON along it:
  * from each river head down its receivers to where the water LEAVES: a sink (the basin terrain.py carved toward),
    the map's edge, or a PIT (a cell lower than all its neighbours, no sink: water with nowhere to go - an error
    unless --allow-pits: give the land a --sink there, or let the river reach the edge); a tributary stops where it
    meets a river already traced (it drains where that one does);
  * smoothed (Chaikin, its ends kept), as wide as its water (WIDTH0 + WIDTH_K * sqrt(the cells that drain through),
    WIDTH_MIN..WIDTH_MAX studs), its surface DEPTH under the land along its line and never rising downstream;
  * a strip of quads, u across (0..1), v along it in widths (v = length / mean width): a texture scrolled along v is
    the water flowing; cut into pieces of at most PIECE studs (a MeshPart is 2048 a side) and MAX_TRIS triangles.
Writes <out>/<name>.ribbons.json (every ribbon: its drain, length, points, widths and mesh) and one .obj a piece.
Pure numpy (no Blender). One JSON line: status / summary / next_action.
Not here: the water's look in Roblox (a scrolling texture on an uploaded MeshPart: the upload is the owner's), and
banks cut to the ribbon (the voxel water role still fills the bed under it)."""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from terrain import sink_config, sink_mask  # noqa: E402

DEPTH = 0.6  # studs: the water's surface under the land along its line
WIDTH0, WIDTH_K, WIDTH_MIN, WIDTH_MAX = 3.0, 0.35, 4.0, 40.0
PIECE = 1024.0
PIT_DEPTH = 3.0  # studs: a closed hollow deeper than this, no sink in it, that a river runs through would stand as a lake  # studs of ribbon a mesh piece at most
MAX_TRIS = 10000
MIN_CELLS = 6  # a traced line shorter than this many cells is a puddle, not a river

_OFFS = [(-1, -1, math.sqrt(2)), (-1, 0, 1.0), (-1, 1, math.sqrt(2)), (0, -1, 1.0), (0, 1, 1.0),
         (1, -1, math.sqrt(2)), (1, 0, 1.0), (1, 1, math.sqrt(2))]


def receivers(h, base=None):
    """each cell's receiver (flat index): its steepest lower neighbour; itself on the edge, in a sink, in a pit"""
    n0, n1 = h.shape
    idx = np.arange(n0 * n1).reshape(n0, n1)
    p = np.pad(h, 1, mode="edge")
    best = np.zeros((n0, n1))
    rec = idx.copy()
    for dx, dz, L in _OFFS:
        nb = p[1 + dx: 1 + dx + n0, 1 + dz: 1 + dz + n1]
        drop = (h - nb) / L
        better = drop > best + 1e-12
        best = np.where(better, drop, best)
        ni = np.clip(np.arange(n0)[:, None] + dx, 0, n0 - 1) * n1 + np.clip(np.arange(n1)[None, :] + dz, 0, n1 - 1)
        rec = np.where(better, ni, rec)
    edge = np.zeros((n0, n1), bool)
    edge[0, :], edge[-1, :], edge[:, 0], edge[:, -1] = True, True, True, True
    rec = np.where(edge, idx, rec)
    if base is not None:
        rec = np.where(base, idx, rec)
    return rec.ravel(), edge.ravel()


def fill(h, base=None, eps=1e-3):
    """PRIORITY-FLOOD (Barnes, Lehman & Mulla 2014, with an epsilon): every closed hollow is filled to its spill
    point plus eps a cell, so all water reaches an outlet - the map's edge or a sink. A raw heightmap holds hundreds
    of shallow hollows (SampleRegion's: every one of its 376 traced rivers ended in one before this)."""
    import heapq

    n0, n1 = h.shape
    out = h.copy()
    done = np.zeros((n0, n1), bool)
    heap = []
    seeds = np.zeros((n0, n1), bool)
    seeds[0, :], seeds[-1, :], seeds[:, 0], seeds[:, -1] = True, True, True, True
    if base is not None:
        seeds |= base
    for i, j in zip(*np.nonzero(seeds)):
        heapq.heappush(heap, (float(out[i, j]), int(i), int(j)))
        done[i, j] = True
    while heap:
        v, i, j = heapq.heappop(heap)
        for dx, dz, _ in _OFFS:
            a, b = i + dx, j + dz
            if 0 <= a < n0 and 0 <= b < n1 and not done[a, b]:
                done[a, b] = True
                if out[a, b] <= v:
                    out[a, b] = v + eps
                heapq.heappush(heap, (float(out[a, b]), a, b))
    return out


def accumulate(h, rec):
    """drainage area in cells (each cell passes 1 + what reached it to its receiver)"""
    order = np.argsort(h.ravel(), kind="stable")[::-1]
    acc = np.ones(h.size)
    for i in order.tolist():
        r = int(rec[i])
        if r != i:
            acc[r] += acc[i]
    return acc


def chaikin(pts, rounds=2):
    """corner cutting, its two ends kept where they are"""
    p = np.asarray(pts, float)
    for _ in range(rounds):
        if len(p) < 3:
            return p
        q = [p[0]]
        for a, b in zip(p[:-1], p[1:]):
            q.append(0.75 * a + 0.25 * b)
            q.append(0.25 * a + 0.75 * b)
        q.append(p[-1])
        p = np.array(q)
    return p


def strip(points, widths, ys):
    """a ribbon of quads along (x, z) points: -> verts [(x, y, z)], faces [(i, j, k)] (counter-clockwise from above),
    uvs [(u, v)] - u across 0..1, v along in mean widths"""
    P = np.asarray(points, float)
    n = len(P)
    t = np.zeros_like(P)
    t[1:-1] = P[2:] - P[:-2]
    t[0] = P[1] - P[0]
    t[-1] = P[-1] - P[-2]
    t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)
    left = np.stack([-t[:, 1], t[:, 0]], axis=1)  # (x, z): the left of the flow seen from above
    seg = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    wbar = float(np.mean(widths))
    verts, uvs = [], []
    for k in range(n):
        for side, u in ((1.0, 0.0), (-1.0, 1.0)):
            x = P[k, 0] + left[k, 0] * widths[k] / 2 * side
            z = P[k, 1] + left[k, 1] * widths[k] / 2 * side
            verts.append((float(x), float(ys[k]), float(z)))
            uvs.append((u, float(seg[k] / wbar)))
    faces = []
    for k in range(n - 1):
        a, b, c, d = 2 * k, 2 * k + 1, 2 * k + 2, 2 * k + 3
        # (the left edge is a, c; seen from above (+y) with x right and z down the screen these wind counter-clockwise)
        faces.append((a, c, b))
        faces.append((b, c, d))
    return verts, faces, uvs, float(seg[-1])


def trace(hm, share=0.012):
    """-> (rivers, stats): every river as {cells, drain, acc} in flow order"""
    nx, nz = int(hm["nx"]), int(hm["nz"])
    step = float(hm.get("step", 4))
    h = np.array(hm["heights"], float).reshape(nx, nz)
    sinks = []
    for one in (hm.get("options") or {}).get("sink") or []:
        s, _ = sink_config(one)
        if s:
            sinks.append(s)
    base = sink_mask(sinks, nx, step) if sinks and nx == nz else None
    filled = fill(h, base)
    rec, edge = receivers(filled, base)
    acc = accumulate(filled, rec)
    river = acc >= np.quantile(acc, 1 - share)
    lake = (filled - h).ravel()  # (how deep a closed hollow's water would stand, cell by cell)
    basef = base.ravel() if base is not None else np.zeros(nx * nz, bool)
    donors = np.zeros(nx * nz, int)
    for i in np.nonzero(river)[0].tolist():
        r = int(rec[i])
        if r != i and river[r]:
            donors[r] += 1
    owner = -np.ones(nx * nz, int)
    rivers = []
    heads = [i for i in np.nonzero(river)[0].tolist() if donors[i] == 0]
    heads.sort(key=lambda i: -h.ravel()[i])
    for head in heads:
        cells, i, joins = [head], head, None
        seen = {head}
        while True:
            r = int(rec[i])
            if r == i:
                break
            if owner[r] >= 0:
                joins = int(owner[r])
                cells.append(r)
                break
            if r in seen:  # (a flat loop: none in D8 with strict drops, held here all the same)
                break
            seen.add(r)
            cells.append(r)
            i = r
        last = cells[-1]
        deepest = max(range(len(cells)), key=lambda q: lake[cells[q]])
        if lake[cells[deepest]] > PIT_DEPTH:
            drain = "pit"  # (it runs through a closed hollow no sink drains: a lake would stand there)
        elif joins is not None:
            drain = rivers[joins]["drain"]
        elif basef[last]:
            drain = "sink"
        elif edge[last]:
            drain = "edge"
        else:
            drain = "pit"
        for c in cells[:-1] if joins is not None else cells:
            owner[c] = len(rivers)
        rivers.append({"cells": cells, "drain": drain, "joins": joins,
                       "acc": [float(acc[c]) for c in cells], "lake": float(lake[cells[deepest]]),
                       "lake_at": divmod(int(cells[deepest]), nz)})
    stats = {"sinks": len(sinks), "river_cells": int(river.sum())}
    return rivers, stats, filled, step


def build(hm, name, share=0.012):
    """-> (ribbons, stats): each river long enough as a ribbon, cut into pieces"""
    rivers, stats, h, step = trace(hm, share)
    nx, nz = h.shape
    half_x, half_z = (nx - 1) * step / 2, (nz - 1) * step / 2
    ribbons = []
    for k, rv in enumerate(rivers):
        if len(rv["cells"]) < MIN_CELLS:
            continue
        ij = [divmod(c, nz) for c in rv["cells"]]
        xz = [(i * step - half_x, j * step - half_z) for i, j in ij]
        ground = np.array([h[i, j] for i, j in ij])
        acc = np.array(rv["acc"])
        pts = chaikin(xz)
        # the cells' heights / drainage along the smoothed line (by the share of the way along)
        s0 = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(np.asarray(xz, float), axis=0), axis=1))]
        s1 = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
        f = s1 / max(s1[-1], 1e-9) * s0[-1]
        g = np.interp(f, s0, ground)
        a = np.interp(f, s0, acc)
        # the water's surface: DEPTH under the land, never rising downstream (water does not climb)
        ys = np.minimum.accumulate(g - DEPTH)
        widths = np.clip(WIDTH0 + WIDTH_K * np.sqrt(a), WIDTH_MIN, WIDTH_MAX)
        # pieces of at most PIECE studs / MAX_TRIS triangles, sharing their seam's points
        cuts = [0]
        while cuts[-1] < len(pts) - 1:
            j = cuts[-1] + 1
            while j < len(pts) - 1 and s1[j + 1] - s1[cuts[-1]] <= PIECE and 2 * (j + 1 - cuts[-1]) <= MAX_TRIS:
                j += 1
            cuts.append(j)
        for p, (c0, c1) in enumerate(zip(cuts[:-1], cuts[1:])):
            sl = slice(c0, c1 + 1)
            verts, faces, uvs, length = strip(pts[sl], widths[sl], ys[sl])
            ribbons.append({"name": f"{name}_river{k + 1}_{p + 1}", "river": k + 1, "piece": p + 1,
                            "drain": rv["drain"], "joins": None if rv["joins"] is None else rv["joins"] + 1,
                            "length": round(length, 2), "tris": len(faces),
                            "points": [[round(float(x), 2), round(float(z), 2)] for x, z in pts[sl]],
                            "widths": [round(float(w), 2) for w in widths[sl]],
                            "surface": [round(float(y), 3) for y in ys[sl]],
                            "ground": [round(float(y), 3) for y in g[sl]],
                            "verts": verts, "faces": faces, "uvs": uvs})
    return ribbons, stats


def write_obj(path, rb):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"# {rb['name']} - a river ribbon (kit/world/ribbons.py); Roblox axes, studs\n")
        for x, y, z in rb["verts"]:
            fh.write(f"v {x:.3f} {y:.3f} {z:.3f}\n")
        for u, v in rb["uvs"]:
            fh.write(f"vt {u:.4f} {v:.4f}\n")
        fh.write("vn 0 1 0\n")
        for a, b, c in rb["faces"]:
            fh.write(f"f {a + 1}/{a + 1}/1 {b + 1}/{b + 1}/1 {c + 1}/{c + 1}/1\n")


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "usage: ribbons.py <heightmap.hm.json>",
                          "next_action": "lune run kit world rivers <Name> --ribbons"}))
        return 2
    path = argv[0]
    share = float(argv[argv.index("--share") + 1]) if "--share" in argv else 0.012
    name = os.path.basename(path).split(".")[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join("build", "worlds", "rivers", name)
    with open(path, encoding="utf-8") as fh:
        hm = json.load(fh)
    ribbons, stats = build(hm, name, share)
    os.makedirs(out, exist_ok=True)
    for rb in ribbons:
        write_obj(os.path.join(out, rb["name"] + ".obj"), rb)
    with open(os.path.join(out, name + ".ribbons.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"heightmap": path.replace(os.sep, "/"), "sinks": stats["sinks"], "ribbons": ribbons}, fh)
    rivers = {}
    for rb in ribbons:
        rivers[rb["river"]] = rb["drain"]
    png = os.path.join(out, name + ".ribbons.png")
    try:  # the map: the land, every ribbon drawn at its width, coloured by where it drains (the evidence to look at)
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon

        nx, nz = int(hm["nx"]), int(hm["nz"])
        step = float(hm.get("step", 4))
        hx, hz = (nx - 1) * step / 2, (nz - 1) * step / 2
        fig, ax = plt.subplots(figsize=(8, 8), dpi=120)
        ax.imshow(np.array(hm["heights"], float).reshape(nx, nz).T, cmap="gist_earth", origin="lower",
                  extent=(-hx, hx, -hz, hz))
        col = {"sink": "#1f6fff", "edge": "#00d0ff", "pit": "#ff2a2a"}
        for rb in ribbons:
            V = rb["verts"]
            left = [(V[k][0], V[k][2]) for k in range(0, len(V), 2)]
            right = [(V[k][0], V[k][2]) for k in range(1, len(V), 2)]
            ax.add_patch(Polygon(left + right[::-1], closed=True, color=col[rb["drain"]], alpha=0.9, lw=0))
        for one in (hm.get("options") or {}).get("sink") or []:
            s, _ = sink_config(one)
            if s:
                ax.add_patch(plt.Circle((s[0], s[1]), s[2], fill=False, color="white", lw=1.2, ls="--"))
        ax.set_title(f"{name}: ribbons by drain (blue sink, cyan edge, red pit)", fontsize=9)
        fig.savefig(png, bbox_inches="tight")
        plt.close(fig)
    except Exception:  # (the map is a convenience: the ribbons are the product)
        png = None
    drains = {d: sum(1 for v in rivers.values() if v == d) for d in ("sink", "edge", "pit")}
    pits = drains["pit"] > 0 and "--allow-pits" not in argv
    summary = (f"{len(rivers)} river(s) as {len(ribbons)} ribbon piece(s), {sum(rb['tris'] for rb in ribbons)} tris: "
               f"{drains['sink']} drain into a sink ({stats['sinks']} in the recipe), {drains['edge']} to the edge, "
               f"{drains['pit']} into a pit")
    print(json.dumps({
        "status": "fail" if pits or not ribbons else "pass",
        "summary": summary if ribbons else f"no river to lay ({stats['river_cells']} river cells)",
        "next_action": ("a river ends in a pit (water with nowhere to go): give the land a --sink there "
                        "(lune run kit world terrain <Name> --sink x,z,radius) or let it reach the edge"
                        if pits else f"LOOK: {out.replace(os.sep, '/')}/ (one .obj a piece, Roblox axes)"),
        "drains": drains,
        "pieces": len(ribbons),
    }))
    return 1 if pits or not ribbons else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
