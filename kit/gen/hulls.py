"""hulls.py — a model's COLLISION as convex pieces: CoACD (approximate convex decomposition, collision-aware; MIT,
SarahWeiii/CoACD, SIGGRAPH 2022, arXiv 2205.02961; VETLOG) cuts a closed mesh into a few convex hulls that follow
its concave places - a sword's guard and grip stay apart, a ring keeps its hole - where ONE hull (Roblox's "Hull")
closes every gap and a box closes more.

Runs in its own environment (~/.cache/roblox-kit/envs/coacd: coacd 1.0.14 + numpy, every wheel's sha256 checked
against PyPI's at install - VETLOG):

    <envs/coacd>/Scripts/python.exe kit/gen/hulls.py <mesh.obj> <out.json> [--threshold 0.05] [--max 16] [--seed 0]

-> <out.json>: {hulls: [{verts, faces, volume}], mesh: {volume, triangles}, coverage, excess, threshold, seconds}
and the same as the last printed line (schema 1: status, summary, next_action). The pure parts (reading the OBJ, the
volume, what the hulls cover) need only numpy and are unit-tested (kit/test/python/test_hybrid.py).

What is measured, so a decomposition is never taken on trust:
  coverage  the share of points spread over the MESH's surface that lie inside (or on) some hull - a hull set that
            leaves part of the model with no collision has a hole a player walks through (bar: >= COVER_BAR)
  excess    the hulls' summed volume over the mesh's volume, less one - how much empty space they close (a
            single hull round an L is ~0.5; CoACD's pieces should stay under EXCESS_BAR)"""

import json
import os
import sys
import time

import numpy as np

COVER_BAR = 0.99    # of the surface's points inside some hull
EXCESS_BAR = 0.35   # the hulls may hold this much more than the mesh (overlaps between hulls count twice)
INSIDE_EPS = 1e-3   # a point this far outside a hull's face (a share of the mesh's size) still counts as on it
SAMPLES = 20000


def read_obj(path):
    """-> (verts (N, 3), triangles (T, 3)) - polygons fanned into triangles"""
    vs, tris = [], []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("v "):
                vs.append([float(x) for x in line.split()[1:4]])
            elif line.startswith("f "):
                ids = [int(x.split("/")[0]) for x in line.split()[1:]]
                ids = [i - 1 if i > 0 else len(vs) + i for i in ids]
                tris += [(ids[0], ids[k], ids[k + 1]) for k in range(1, len(ids) - 1)]
    return np.array(vs, float).reshape(-1, 3), np.array(tris, np.int64).reshape(-1, 3)


def volume(verts, tris):
    """the enclosed volume of a closed triangle mesh (signed tetrahedra from the origin; outward faces -> positive)"""
    t = np.asarray(verts, float)[np.asarray(tris, np.int64)]
    return float(np.einsum("ij,ij->i", t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6.0)


def is_closed(tris):
    """every edge shared by exactly two triangles (no open rim, no pinch)"""
    t = np.asarray(tris, np.int64).reshape(-1, 3)
    if not len(t):
        return False
    e = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
    _u, counts = np.unique(e, axis=0, return_counts=True)
    return bool((counts == 2).all())


def surface_points(verts, tris, n=SAMPLES, seed=0):
    t = np.asarray(verts, float)[np.asarray(tris, np.int64)]
    area = 0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
    if area.sum() <= 0:
        return np.zeros((0, 3))
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(t), size=n, p=area / area.sum())
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    w = np.stack([1 - s, s * (1 - r2), s * r2], axis=1)
    return (t[pick] * w[:, :, None]).sum(axis=1)


def planes(verts, tris):
    """a convex hull's face planes -> (normals (F, 3) outward, offsets (F,)): n . x <= d inside"""
    v = np.asarray(verts, float)
    t = v[np.asarray(tris, np.int64)]
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    ln = np.linalg.norm(n, axis=1)
    keep = ln > 1e-12
    n, t = n[keep] / ln[keep, None], t[keep]
    d = np.einsum("ij,ij->i", n, t[:, 0])
    c = v.mean(axis=0)   # (outward: the hull's own centre lies inside every plane)
    flip = (n @ c) > d
    n[flip], d[flip] = -n[flip], -d[flip]
    return n, d


def coverage(points, hulls, size):
    """the share of points inside (or within INSIDE_EPS x size of) at least one convex hull [(verts, tris)]"""
    if not len(points):
        return 0.0
    inside = np.zeros(len(points), bool)
    eps = INSIDE_EPS * float(size)
    for hv, ht in hulls:
        n, d = planes(hv, ht)
        if not len(n):
            continue
        inside |= ((points @ n.T) - d <= eps).all(axis=1)
    return float(inside.mean())


def judge(verts, tris, hulls):
    """-> facts about a hull set for a mesh: coverage, excess, the volumes"""
    size = float(np.max(verts.max(axis=0) - verts.min(axis=0))) if len(verts) else 1.0
    mv = abs(volume(verts, tris))
    hv = [abs(volume(h, t)) for h, t in hulls]
    cov = coverage(surface_points(verts, tris), hulls, size)
    excess = (sum(hv) / mv - 1.0) if mv > 0 else None
    return {"hull_count": len(hulls), "coverage": round(cov, 4),
            "excess": None if excess is None else round(excess, 4),
            "mesh": {"volume": round(mv, 6), "triangles": int(len(tris))},
            "hull_volumes": [round(x, 6) for x in hv],
            "ok": bool(cov >= COVER_BAR and excess is not None and excess <= EXCESS_BAR)}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))


def main(argv):
    if len(argv) < 2:
        return emit("fail", "hulls: <mesh.obj> <out.json> [--threshold 0.05] [--max 16]", "give a closed mesh")
    t0 = time.time()
    src, out = argv[0], argv[1]

    def opt(flag, default):
        return type(default)(argv[argv.index(flag) + 1]) if flag in argv else default
    threshold, most, seed = opt("--threshold", 0.05), opt("--max", 16), opt("--seed", 0)
    try:
        import coacd  # noqa: PLC0415
    except ImportError:
        return emit("fail", "hulls: CoACD is not installed in this python (it lives in its own env)",
                    "~/.cache/roblox-kit/envs/coacd/Scripts/python.exe kit/gen/hulls.py ... (VETLOG: coacd 1.0.14)")
    verts, tris = read_obj(src)
    if not len(tris):
        return emit("fail", f"hulls: {src} has no faces", "export the model's game mesh as OBJ first")
    coacd.set_log_level("error")
    # (CoACD's own search defaults - 150 tree-search iterations, 20 nodes, depth 3 - took 511 s on a 4,000-quad lobed
    #  ball for 7 hulls (100% covered, +5% volume); these took 108 s for 8 hulls, the same cover and volume)
    # (a CLOSED mesh is cut as it is: CoACD's "auto" voxel-remeshed the H9 blade - 8 mm thick, 850 mm long - at 1/50
    #  of its length, fattening it into one hull 8.5x its volume; only an open or pinched mesh is remeshed first)
    closed = is_closed(tris)
    parts = coacd.run_coacd(coacd.Mesh(verts, tris), threshold=float(threshold), max_convex_hull=int(most),
                            seed=int(seed), preprocess_mode="off" if closed else "on",
                            resolution=opt("--resolution", 1000),
                            mcts_iterations=opt("--iterations", 40), mcts_max_depth=opt("--depth", 2),
                            mcts_nodes=opt("--nodes", 10))
    hulls = [(np.asarray(v, float), np.asarray(f, np.int64)) for v, f in parts]
    facts = judge(verts, tris, hulls)
    facts.update({"threshold": threshold, "max": most, "seed": seed, "remeshed_first": not closed, "engine": f"coacd {getattr(coacd, '__version__', '1.0.14')}",
                  "seconds": round(time.time() - t0, 1), "source": os.path.abspath(src).replace("\\", "/"),
                  "hulls": [{"verts": np.round(v, 6).tolist(), "faces": f.tolist()} for v, f in hulls]})
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(facts, f)
    said = (f"{facts['hull_count']} convex hulls cover {facts['coverage']:.1%} of the surface, "
            f"{facts['excess']:+.0%} volume over the mesh")
    if facts["ok"]:
        return emit("pass", f"hulls: {said}", f"the collision pieces are in {out}", **{k: facts[k] for k in
                    ("hull_count", "coverage", "excess", "seconds")})
    return emit("fail", f"hulls: {said} (bars: cover >= {COVER_BAR:.0%}, excess <= {EXCESS_BAR:.0%})",
                "a lower --threshold (finer pieces) or a higher --max", **{k: facts[k] for k in
                ("hull_count", "coverage", "excess", "seconds")})


if __name__ == "__main__":
    main(sys.argv[1:])
