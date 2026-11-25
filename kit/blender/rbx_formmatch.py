"""rbx_formmatch.py — the FORM-MATCH teacher: how far a build's surface is from a real reference model's, and WHERE.

a.form_match("<model.glb>", height=<studs>, rot=(rx, ry, rz)) lays the reference beside the build exactly as
a.import_mesh would place it (scaled uniformly to `height`, turned by `rot`, its base on y 0 and centred in x and z)
— never built, only measured — and measures both ways:
  - EXTRA: each point of the build's surface, how far OUTSIDE the reference it sits (material the real one has not)
  - MISSING: each point of the reference's surface, how far outside the BUILD it sits (material the build lacks)
in mm, per region of the reference's box (x right / centre / left, y low / mid / high, z front / middle / back), the
worst first: "front-high-left: missing 5.2 mm (the real one's surface beyond the build over 4% of it)". A sculptor
reads a reference like this; the build's own sculpt stays its own (the reference is measured, never taken in).
The geometry (placement, region names, the statistics) is plain numpy (kit/test/python/test_formmatch.py); the
nearest-surface queries use Blender's BVH tree.
"""

import math

import numpy as np

AXES = (("right", "centre", "left"), ("low", "mid", "high"), ("front", "middle", "back"))
SAMPLE = 60000          # points sampled from each surface (vertices, evenly strided)
TOL_MM = 0.5            # under this, a point counts as on the surface


def rot_matrix(rot):
    """degrees (x, y, z) -> 3x3, CFrame.Angles order (Rx @ Ry @ Rz): the same turn a.import_mesh gives"""
    rx, ry, rz = (math.radians(float(v)) for v in rot)
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return mx @ my @ mz


def place(verts_rbx, height, rot=(0, 0, 0)):
    """the reference's vertices (model frame: x right, y up, z back) turned by rot, scaled uniformly so its y size is
    `height`, its base on y 0 and centred in x and z -> (N, 3)"""
    v = np.asarray(verts_rbx, dtype=np.float64) @ rot_matrix(rot).T
    lo, hi = v.min(axis=0), v.max(axis=0)
    k = float(height) / max(float(hi[1] - lo[1]), 1e-12)
    v = v * k
    lo, hi = v.min(axis=0), v.max(axis=0)
    return v - np.array([(lo[0] + hi[0]) / 2.0, lo[1], (lo[2] + hi[2]) / 2.0])


def region_of(points, lo, hi):
    """(N, 3) -> (N,) region index 0..26 over the box lo..hi (thirds on each axis)"""
    t = np.clip((np.asarray(points) - lo) / np.maximum(hi - lo, 1e-12), 0, 0.9999)
    q = (t * 3).astype(int)
    # x thirds: + x is the model's right (a.import_mesh's frame): third 2 -> "right"
    return (2 - q[:, 0]) * 9 + q[:, 1] * 3 + q[:, 2]


def region_name(r):
    return f"{AXES[2][r % 3]}-{AXES[1][(r // 3) % 3]}-{AXES[0][r // 9]}"


def summary(extra_mm, extra_reg, missing_mm, missing_reg, top=6, tol=TOL_MM):
    """per-point signed gaps (mm, > 0: off the other surface) and their regions -> the report: overall numbers and
    the worst regions, each with what it is and how much of the surface it covers"""
    out = {"extra_mean_mm": round(float(np.mean(np.maximum(extra_mm, 0))), 2) if len(extra_mm) else None,
           "missing_mean_mm": round(float(np.mean(np.maximum(missing_mm, 0))), 2) if len(missing_mm) else None,
           "extra_p90_mm": round(float(np.percentile(np.maximum(extra_mm, 0), 90)), 2) if len(extra_mm) else None,
           "missing_p90_mm": round(float(np.percentile(np.maximum(missing_mm, 0), 90)), 2) if len(missing_mm) else None}
    rows = []
    for kind, d, reg in (("extra", extra_mm, extra_reg), ("missing", missing_mm, missing_reg)):
        if not len(d):
            continue
        n = len(d)
        for r in np.unique(reg):
            sel = (reg == r) & (d > tol)
            if not sel.any():
                continue
            share = float(sel.sum()) / n
            mean = float(d[sel].mean())
            rows.append({"region": region_name(int(r)), "kind": kind, "mean_mm": round(mean, 2),
                         "max_mm": round(float(d[sel].max()), 2), "share": round(share, 4),
                         "weight": round(mean * share, 4)})
    rows.sort(key=lambda x: -x["weight"])
    out["worst"] = rows[:top]
    return out


def hot_spots(points_mm, gaps_mm, over=4.0, cell=15.0, top=5):
    """the worst places, clustered: points more than `over` mm off, binned in `cell` mm cubes -> the top clusters by
    total gap: [{"at": (x, y, z) mm, "mean_mm", "points"}] — where the clay must move (a region is a third of the box)"""
    p = np.asarray(points_mm)
    g = np.asarray(gaps_mm)
    sel = g > over
    if not sel.any():
        return []
    p, g = p[sel], g[sel]
    key = np.floor(p / cell).astype(np.int64)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    inv = np.asarray(inv).ravel()
    tot = np.bincount(inv, weights=g, minlength=len(uniq))
    cnt = np.bincount(inv, minlength=len(uniq))
    out = []
    for k in np.argsort(-tot)[:top]:
        m = inv == k
        c = p[m].mean(axis=0)
        out.append({"at": [round(float(v), 1) for v in c], "mean_mm": round(float(g[m].mean()), 1), "points": int(cnt[k])})
    return out


def words(row):
    if row["kind"] == "missing":
        return (f"{row['region']}: missing {row['mean_mm']:g} mm (the real surface beyond the build over "
                f"{row['share']:.0%} of it, up to {row['max_mm']:g})")
    return (f"{row['region']}: extra {row['mean_mm']:g} mm (the build beyond the real surface over {row['share']:.0%} "
            f"of it, up to {row['max_mm']:g})")


def crispness(points_mm, normals, r=2.0, queries=2500, seed=0, chunk=400):
    """how much of a surface FOLDS within r mm (edges, rims, ridges, creases): for sample points, the spread of the
    normals around them (1 - |their mean normal| within r) -> {"fold_share": the share of points whose spread passes
    0.03 (a turn of ~14 degrees inside r), "p90": the 90th-percentile spread}. Judges call a sculpt "melted" / "soft"
    when its fold share is far under the real object's — measured the same way on both, at the same r"""
    p = np.asarray(points_mm, dtype=np.float64)
    n = np.asarray(normals, dtype=np.float64)
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    if len(p) < 10:
        return {"fold_share": 0.0, "p90": 0.0}
    rng = np.random.default_rng(seed)
    q = rng.choice(len(p), size=min(queries, len(p)), replace=False)
    spread = np.empty(len(q))
    pp = (p * p).sum(axis=1)
    for i in range(0, len(q), chunk):
        qi = q[i:i + chunk]
        d2 = pp[qi][:, None] + pp[None, :] - 2.0 * (p[qi] @ p.T)   # (chunk x N, never chunk x N x 3)
        near = (d2 <= r * r).astype(np.float64)
        mean = (near @ n) / np.maximum(near.sum(axis=1, keepdims=True), 1.0)
        spread[i:i + chunk] = 1.0 - np.linalg.norm(mean, axis=1)
    return {"fold_share": round(float((spread > 0.03).mean()), 4), "p90": round(float(np.percentile(spread, 90)), 4)}


def crisp_words(build, ref):
    """the two crispness reports -> a line when the build folds clearly less than the reference, else "" """
    if ref["fold_share"] <= 0:
        return ""
    k = build["fold_share"] / ref["fold_share"]
    if k >= 0.75:
        return ""
    return (f"SOFT: {build['fold_share']:.0%} of the surface folds within 2 mm against the reference's "
            f"{ref['fold_share']:.0%} ({k:.0%} of it) — the share is SURFACE-WIDE: pinched rims alone did not move it on "
            f"a skull (12% -> 12%); its fine relief at the material's scale did (s.noise(0.35, 6, kind=\"ridged\"): 12% "
            f"-> 21% against 22.5%) — then crisp the rims (sharp=True, chamfer joins, brushes)")


def surface_samples(verts, tris, n=60000, seed=0):
    """area-weighted points on a triangle mesh and their face normals -> (points (n, 3), normals (n, 3))"""
    v = np.asarray(verts, dtype=np.float64)
    t = np.asarray(tris, dtype=np.int64)
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    cr = np.cross(b - a, c - a)
    area = np.linalg.norm(cr, axis=1)
    if area.sum() <= 0:
        return np.zeros((0, 3)), np.zeros((0, 3))
    rng = np.random.default_rng(seed)
    f = rng.choice(len(t), size=n, p=area / area.sum())
    u, w = rng.random(n), rng.random(n)
    flip = u + w > 1
    u[flip], w[flip] = 1 - u[flip], 1 - w[flip]
    pts = a[f] + (b[f] - a[f]) * u[:, None] + (c[f] - a[f]) * w[:, None]
    return pts, cr[f] / np.maximum(area[f][:, None], 1e-12)


def midline_profile(points_mm, half=4.0, step=3.0):
    """the FRONT of an object along its midline (the model frame: x right, y up, the front toward -z): for each
    height band `step` mm tall, the front-most z of the points within `half` mm of x = 0 -> {band's foot y: z}. A
    face's landmarks read straight off it — the chin, the teeth, the nose's opening (deep), the nasal bones, the brow"""
    p = np.asarray(points_mm, dtype=np.float64)
    p = p[np.abs(p[:, 0]) <= half]
    out = {}
    if not len(p):
        return out
    bands = np.floor(p[:, 1] / step).astype(int)
    for b in np.unique(bands):
        out[round(float(b * step), 3)] = float(p[bands == b, 2].min())
    return out


def profile_gaps(ref, build, over=3.0, step=3.0):
    """where a build's midline profile leaves the reference's by more than `over` mm, as runs of neighbouring bands
    -> [{"y": (from, to), "mm": mean signed gap (+ = the build behind the reference), "words": ...}], the biggest
    (gap x length) first: a landmark guessed (a bite plane 9 mm too high, a nose opening 6 mm too tall) shows here"""
    ys = sorted(y for y in ref if y in build)
    runs, cur = [], []
    for y in ys:
        g = build[y] - ref[y]
        if abs(g) > over and (not cur or (abs(y - cur[-1][0] - step) < 1e-6 and np.sign(g) == np.sign(cur[-1][1]))):
            cur.append((y, g))
            continue
        if cur:
            runs.append(cur)
        cur = [(y, g)] if abs(g) > over else []
    if cur:
        runs.append(cur)
    out = []
    for r in runs:
        y0, y1 = r[0][0], r[-1][0] + step
        g = float(np.mean([x[1] for x in r]))
        rz, bz = float(np.mean([ref[x[0]] for x in r])), float(np.mean([build[x[0]] for x in r]))
        what = (f"the build {g:.1f} mm BEHIND the reference (its front at z {bz:.0f}, the reference's at {rz:.0f}): add "
                f"clay or move it forward") if g > 0 else (
                f"the build {-g:.1f} mm IN FRONT of the reference (its front at z {bz:.0f}, the reference's at "
                f"{rz:.0f}): carve, open or move it back")
        out.append({"y": (round(y0, 1), round(y1, 1)), "mm": round(g, 1),
                    "words": f"midline y {y0:.0f}-{y1:.0f} mm: {what}"})
    return sorted(out, key=lambda r: -abs(r["mm"]) * (r["y"][1] - r["y"][0]))


def fragment_levels(levels, window=0.1, share=0.35):
    """a reference's slice heights where its BIGGEST ISLAND is a fragment, not the section (kit refs measure keeps
    the biggest island; a skull sliced through its teeth falls apart into pieces: 26 x 47 mm where 100 x 86 and
    69 x 56 lie just below and above) — {h: words}: its island under `share` of the biggest one within `window` of
    height on BOTH sides. Comparing a build to a fragment fails a whole, correct section"""
    lv = sorted((round(float(x["h"]), 4), float(x["width_mm"]) * float(x["depth_mm"]), x) for x in levels)
    out = {}
    for h, area, x in lv:
        below = [a for hh, a, _ in lv if h - window - 1e-9 <= hh < h]
        above = [a for hh, a, _ in lv if h < hh <= h + window + 1e-9]
        if below and above and area < share * min(max(below), max(above)):
            i = [hh for hh, _a, _x in lv].index(h)
            near = [lv[i - 1][2], lv[i + 1][2]]   # (the slices just below and above)
            out[h] = (f"{h:.0%} height: the reference's slice is in pieces there (its biggest island "
                      f"{x['width_mm']:g} x {x['depth_mm']:g} mm, " +
                      " / ".join(f"{y['width_mm']:g} x {y['depth_mm']:g}" for y in near) +
                      " around it) — not compared: hold a height where it is whole")
    return out


# ------------------------------------------------------------------------------------------------ Blender side
def _load_glb(path):
    """the GLB's largest mesh, world transforms applied, in Blender coordinates -> (verts (N, 3), tris (M, 3))"""
    import bpy  # noqa: PLC0415

    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    best = max(meshes, key=lambda o: len(o.data.polygons))
    me = best.data
    me.calc_loop_triangles()
    mw = np.array(best.matrix_world)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
    tri = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", tri)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    return co, tri.reshape(-1, 3)


def _bl_to_rbx(v):
    """Blender (x, y, z) -> the model frame (x, y up, z back): BL_FROM_RBX maps (x, y, z) -> (x, -z, y)"""
    v = np.asarray(v)
    return np.stack([v[:, 0], v[:, 2], -v[:, 1]], axis=1)


def _surface(objs):
    """the build's parts joined (world -> model frame, studs) -> (verts, tris)"""
    vs, ts, off = [], [], 0
    for o in objs:
        me = o.data
        me.calc_loop_triangles()
        mw = np.array(o.matrix_world)
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
        tri = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tri)
        vs.append(_bl_to_rbx(co))
        ts.append(tri.reshape(-1, 3) + off)
        off += len(co)
    return np.concatenate(vs), np.concatenate(ts)


def _signed_gaps(points, verts, tris):
    """each point's distance OFF the surface (verts, tris): > 0 outside it (along the nearest face's normal), < 0
    inside -> (N,) in the points' units"""
    from mathutils import Vector  # noqa: PLC0415
    from mathutils.bvhtree import BVHTree  # noqa: PLC0415

    tree = BVHTree.FromPolygons([tuple(map(float, v)) for v in verts], [tuple(map(int, t)) for t in tris])
    out = np.zeros(len(points))
    for i, p in enumerate(points):
        loc, nrm, _idx, dist = tree.find_nearest(Vector(p))
        if loc is None:
            out[i] = np.nan
            continue
        out[i] = dist if (Vector(p) - loc).dot(nrm) >= 0 else -dist
    return out


def run(asset, objs, spec):
    """spec: {"path", "height", "rot", "bar_mm"} -> the report (mm), with "lines": the worst regions in words"""
    mm = float(getattr(asset, "mm_per_stud", None) or 280.0)
    rv, rt = _load_glb(spec["path"])
    rv = place(_bl_to_rbx(rv), spec["height"], spec.get("rot") or (0, 0, 0))
    bv, bt = _surface(objs)
    lo, hi = rv.min(axis=0), rv.max(axis=0)

    def sample(v):
        step = max(1, len(v) // SAMPLE)
        return v[::step]

    mine = sample(bv)
    theirs = sample(rv)
    extra = _signed_gaps(mine, rv, rt) * mm
    missing = _signed_gaps(theirs, bv, bt) * mm
    ok_e, ok_m = ~np.isnan(extra), ~np.isnan(missing)
    rep = summary(extra[ok_e], region_of(mine[ok_e], lo, hi), missing[ok_m], region_of(theirs[ok_m], lo, hi))
    rep["lines"] = [words(r) for r in rep["worst"]]
    # the HOT SPOTS (model frame, mm: x right, y up from the base, z back): where to add clay, where to carve
    rep["extra_spots"] = hot_spots(mine[ok_e] * mm, extra[ok_e])
    rep["missing_spots"] = hot_spots(theirs[ok_m] * mm, missing[ok_m])
    rep["lines"] += [f"extra at {s_['at']} mm: {s_['mean_mm']} mm out" for s_ in rep["extra_spots"][:3]]
    rep["lines"] += [f"missing at {s_['at']} mm: {s_['mean_mm']} mm short" for s_ in rep["missing_spots"][:3]]
    # the MIDLINE PROFILE (every vertex, not the sample: a 3 mm band near x = 0 needs them all): its landmarks
    gaps = profile_gaps(midline_profile(rv * mm), midline_profile(bv * mm), over=max(3.0, float(spec.get("bar_mm")
                                                                                                 or 3.0)))
    rep["midline_gaps"] = gaps[:8]
    rep["lines"] += [g["words"] for g in gaps[:3]]
    # SOFTNESS: the build's folds against the reference's, the same sampling and radius on both ("melted", in numbers)
    rc = crispness(*surface_samples(rv * mm, rt, 40000, 1))
    bc = crispness(*surface_samples(bv * mm, bt, 40000, 2))
    rep["crisp"] = {"build": bc, "reference": rc}
    soft = crisp_words(bc, rc)
    if soft:
        rep["lines"].append(soft)
    rep["reference"] = spec["path"].replace("\\", "/")
    rep["bar_mm"] = spec.get("bar_mm")
    worst = max((rep.get("extra_p90_mm") or 0), (rep.get("missing_p90_mm") or 0))
    rep["ok"] = spec.get("bar_mm") is None or worst <= float(spec["bar_mm"])
    return rep
