"""rbx_brushes.py — SCULPT BRUSHES on the meshed surface, the way Blender's sculpt mode moves vertices, but driven by
measured paths in code and headless (bpy.ops.sculpt.brush_stroke needs a window's 3D view: a build has none).

A primitive sculpt (balls, ellipsoids, blends) reads "melted": its forms meet in fillets, its planes are domes. A
sculptor's second pass is brushes — PINCH a rim or a ridge into a sharp line, FLATTEN a plane, INFLATE / deflate a
form, CREASE a groove — each with a smooth falloff. Here each one is a function of the vertices (mm):

    s.brush("pinch", path=[...], radius=4, strength=0.6)          # a sharp ridge / rim along the path
    s.brush("flatten", path=[centre], radius=12, strength=0.8)    # a plane where the form bulged
    s.brush("inflate", path=[...], radius=6, strength=1.5)        # mm along the normal (negative: deflate)
    s.brush("crease", path=[...], radius=2.5, strength=0.8)       # pinch + pressed in: a groove with crisp walls

Brushes run after meshing (and sharpening), before any smoothing; a mirrored canvas mirrors them (one pass).
"""

import numpy as np

KINDS = ("pinch", "flatten", "inflate", "crease")


def falloff(d, radius):
    """Blender's 'smooth' falloff: 1 at the centre, 0 at the radius, flat at both ends"""
    t = np.clip(1.0 - d / max(radius, 1e-9), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def nearest_on_path(p, path):
    """for points p (N, 3) the nearest point on a polyline -> (points (N, 3), distances (N,), unit tangents (N, 3))"""
    path = np.asarray(path, dtype=np.float64).reshape(-1, 3)
    if len(path) == 1:
        q = np.repeat(path, len(p), axis=0)
        return q, np.linalg.norm(p - q, axis=1), np.zeros_like(p)
    best_d = np.full(len(p), np.inf)
    best_q = np.zeros_like(p)
    best_t = np.zeros_like(p)
    for a, b in zip(path, path[1:]):
        ab = b - a
        L2 = float(ab @ ab) or 1e-12
        t = np.clip(((p - a) @ ab) / L2, 0.0, 1.0)
        q = a + t[:, None] * ab
        d = np.linalg.norm(p - q, axis=1)
        m = d < best_d
        best_d[m], best_q[m] = d[m], q[m]
        best_t[m] = ab / np.sqrt(L2)
    return best_q, best_d, best_t


def vertex_normals(verts, faces):
    """area-weighted vertex normals of a mesh of quads and triangles (vectorized per face size)"""
    v = np.asarray(verts, dtype=np.float64)
    n = np.zeros_like(v)
    by = {}
    for f in faces:
        by.setdefault(len(f), []).append(f)
    for size, fs in by.items():
        f = np.asarray(fs, dtype=np.int64)
        for k in range(1, size - 1):
            c = np.cross(v[f[:, k]] - v[f[:, 0]], v[f[:, k + 1]] - v[f[:, 0]])
            for col in (0, k, k + 1):
                np.add.at(n, f[:, col], c)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def apply(verts, faces, brush, normals=None, mirror_axis=None):
    """one brush {"kind", "path", "radius", "strength"} on the vertices -> new vertices. mirror_axis: the brush also
    acts across that axis — as ONE pass over both paths (a midline path mirrored onto itself would act twice)"""
    kind = brush["kind"]
    if kind not in KINDS:
        raise ValueError(f'brush "{kind}": one of {", ".join(KINDS)}')
    v = np.asarray(verts, dtype=np.float64).copy()
    r, s = float(brush["radius"]), float(brush["strength"])
    q, d, tan = nearest_on_path(v, brush["path"])
    if mirror_axis is not None:
        q2, d2, t2 = nearest_on_path(v, mirrored(brush, mirror_axis)["path"])
        m = d2 < d
        q[m], d[m], tan[m] = q2[m], d2[m], t2[m]
    w = falloff(d, r)
    hit = w > 0
    if not hit.any():
        return v
    n = vertex_normals(v, faces) if normals is None else normals
    if kind == "inflate":
        v[hit] += n[hit] * (s * w[hit])[:, None]
    elif kind in ("pinch", "crease"):
        # toward the path, across it only (never along it: a pinch draws a line, it does not bunch the mesh up)
        to = q - v
        to -= (to * n).sum(axis=1, keepdims=True) * n     # (in the surface: the line sharpens, the form keeps)
        tp = tan - (tan * n).sum(axis=1, keepdims=True) * n   # (the path's direction IN the surface)
        tp /= np.maximum(np.linalg.norm(tp, axis=1, keepdims=True), 1e-12)
        to -= (to * tp).sum(axis=1, keepdims=True) * tp
        v[hit] += to[hit] * np.clip(s * w[hit], 0.0, 1.0)[:, None]
        if kind == "crease":
            v[hit] -= n[hit] * (0.35 * r * s * w[hit])[:, None]
    else:  # flatten: onto the plane fitted to the vertices under the brush
        pts = v[hit]
        c = (pts * w[hit, None]).sum(axis=0) / w[hit].sum()
        cov = ((pts - c) * w[hit, None]).T @ (pts - c)
        nrm = np.linalg.eigh(cov)[1][:, 0]
        off = (pts - c) @ nrm
        v[hit] -= (off * np.clip(s * w[hit], 0.0, 1.0))[:, None] * nrm[None, :]
    return v


def mirrored(brush, axis):
    b = dict(brush)
    p = np.asarray(brush["path"], dtype=np.float64).reshape(-1, 3).copy()
    p[:, axis] *= -1
    b["path"] = p.tolist()
    return b
