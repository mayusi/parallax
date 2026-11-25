"""rbx_refmesh.py — a REFERENCE MODEL read as numbers, never taken in (plain numpy: build scripts, tests, tools alike).

    import rbx_refmesh as R
    ref = R.load("~/.cache/roblox-kit/library/<uid>/Object_3.glb", height=217, rot=(0, 180, 0))  # mm, the sculpt frame
    L = R.landmarks(ref, {"nasion": ("front_min", 110, 130), "chin": ("front_max", 0, 12), ...})
    pieces = R.slice_pieces(ref, y=40)            # EVERY piece of a horizontal slice (the jaw's two halves too)
    sil = R.outline(ref, "side")                   # the exact side silhouette, rastered from the mesh (no picture)

The frame is the sculpt's (and a.form_match's): mm, x right, y up from the base, z back, the front toward -z.
"""

import json
import math
import os
import struct

import numpy as np


# ------------------------------------------------------------------------------------------------ reading
def glb_mesh(path):
    """a GLB's triangles with every node's transform applied (glTF frame: y up) -> (verts (N, 3), tris (M, 3))"""
    with open(os.path.expanduser(path), "rb") as fh:
        b = fh.read()
    if b[:4] != b"glTF":
        raise ValueError(f"{path}: not a GLB")
    jlen = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + jlen])
    bin0 = 20 + jlen + 8

    def view(acc_i, dtype, width):
        acc = doc["accessors"][acc_i]
        bv = doc["bufferViews"][acc["bufferView"]]
        off = bin0 + bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        size = np.dtype(dtype).itemsize * width
        stride = bv.get("byteStride", size)
        raw = np.frombuffer(b, dtype=np.uint8, count=(acc["count"] - 1) * stride + size, offset=off)
        rows = np.lib.stride_tricks.as_strided(raw, shape=(acc["count"], size), strides=(stride, 1))
        return rows.copy().view(dtype).reshape(acc["count"], width)

    def local(n):
        if "matrix" in n:
            return np.array(n["matrix"], dtype=np.float64).reshape(4, 4).T
        t = np.eye(4)
        x, y, z, w = n.get("rotation", [0, 0, 0, 1])
        r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        t[:3, :3] = r * np.array(n.get("scale", [1, 1, 1]))[None, :]
        t[:3, 3] = n.get("translation", [0, 0, 0])
        return t

    vs, ts, off = [], [], 0
    codes = {5121: np.uint8, 5123: np.uint16, 5125: np.uint32}

    def walk(i, parent):
        nonlocal off
        n = doc["nodes"][i]
        m = parent @ local(n)
        if "mesh" in n:
            for prim in doc["meshes"][n["mesh"]]["primitives"]:
                if prim.get("mode", 4) != 4:
                    continue
                v = view(prim["attributes"]["POSITION"], np.float32, 3).astype(np.float64)
                if "indices" in prim:
                    acc = doc["accessors"][prim["indices"]]
                    t = view(prim["indices"], codes[acc["componentType"]], 1).astype(np.int64).reshape(-1, 3)
                else:
                    t = np.arange(len(v)).reshape(-1, 3)
                vs.append(v @ m[:3, :3].T + m[:3, 3])
                ts.append(t + off)
                off += len(v)
        for c in n.get("children", []):
            walk(c, m)

    for root in doc["scenes"][doc.get("scene", 0)]["nodes"]:
        walk(root, np.eye(4))
    if not vs:
        raise ValueError(f"{path}: no triangle mesh")
    return np.concatenate(vs), np.concatenate(ts)


def _rot(rot):
    rx, ry, rz = (math.radians(float(v)) for v in rot)
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    return (np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]]) @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
            @ np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]))


class Ref:
    """a reference mesh placed in the sculpt frame (mm): verts, tris"""

    def __init__(self, verts, tris):
        self.verts, self.tris = np.asarray(verts, dtype=np.float64), np.asarray(tris, dtype=np.int64)

    @property
    def lo(self):
        return self.verts.min(axis=0)

    @property
    def hi(self):
        return self.verts.max(axis=0)


def load(path, height, rot=(0, 0, 0)):
    """a reference GLB placed as a.form_match places it: turned by rot (degrees, the kit's order), scaled to `height`
    mm tall, its base at y 0, centred in x and z -> Ref (mm). glTF is already y-up with the front toward +z for most
    exports: rot=(0, 180, 0) turns that front to -z, the kit's"""
    v, t = glb_mesh(path)
    v = v @ _rot(rot).T
    lo, hi = v.min(axis=0), v.max(axis=0)
    s = float(height) / max(hi[1] - lo[1], 1e-12)
    v = (v - [(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2]) * s
    return Ref(*weld(v, t))


def weld(verts, tris, tol=1e-3):
    """vertices nearer than tol mm made one (a scan's mesh splits them along its texture seams: two triangles
    meeting there share no index, and every slice of it fell into pieces) -> (verts, tris) without degenerate faces"""
    key = np.round(np.asarray(verts) / tol).astype(np.int64)
    _u, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.reshape(-1)
    t = inv[np.asarray(tris)]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    return np.asarray(verts)[first], t


# ------------------------------------------------------------------------------------------------ slicing
def section(ref, axis, at):
    """a plane slice of the mesh (axis 0 / 1 / 2 = x / y / z at `at` mm) -> (segments [(edge key, edge key)], points
    {edge key: (u, v)}) in the OTHER two axes. Each crossing is keyed by the mesh EDGE it lies on (its two vertex
    indices), so two triangles sharing an edge share the point exactly — rounded coordinates split loops apart"""
    v, t = ref.verts, ref.tris
    d = v[:, axis] - at
    d = np.where(d == 0, 1e-9, d)   # (a vertex exactly on the plane: nudged to one side)
    dt = d[t]
    cross = ((dt > 0).any(axis=1)) & ((dt < 0).any(axis=1))
    other = [i for i in range(3) if i != axis]
    segs, pts = [], {}
    for tri in t[cross]:
        keys = []
        for i in range(3):
            a, b = int(tri[i]), int(tri[(i + 1) % 3])
            if (d[a] > 0) != (d[b] > 0):
                k = (a, b) if a < b else (b, a)
                if k not in pts:
                    f = d[k[0]] / (d[k[0]] - d[k[1]])
                    p = v[k[0]] + (v[k[1]] - v[k[0]]) * f
                    pts[k] = (float(p[other[0]]), float(p[other[1]]))
                keys.append(k)
        if len(keys) == 2:
            segs.append((keys[0], keys[1]))
    return segs, pts


def _label(mask):
    """4-connected regions of a 2D boolean mask -> (labels int array, 0 = none, count)"""
    lab = np.zeros(mask.shape, dtype=np.int32)
    n = 0
    h, w = mask.shape
    for start in map(tuple, np.argwhere(mask)):
        if lab[start]:
            continue
        n += 1
        stack = [start]
        lab[start] = n
        while stack:
            i, j = stack.pop()
            for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= a < h and 0 <= b < w and mask[a, b] and not lab[a, b]:
                    lab[a, b] = n
                    stack.append((a, b))
    return lab, n


def _grow2(mask, r):
    out = mask.copy()
    for _ in range(r):
        g = out.copy()
        g[1:] |= out[:-1]
        g[:-1] |= out[1:]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        out = g
    return out


def slice_pieces(ref, y, res=0.5, close=3, min_size=2.0):
    """EVERY piece of the horizontal slice at height y (mm) — not the biggest island alone (a skull's jaw at its teeth
    falls into pieces; each one is a section of its own bone). A scan is full of holes (this skull: 34 surfaces,
    14,573 open edges): its slice is open chains, so it is RASTERED at res mm, gaps under `close` px bridged, the
    outside flooded from the border — the rest is solid — and each solid region is a piece -> [{"centre": (x, z),
    "width", "depth", "area" (mm^2), "mask", "lo", "res"}], biggest first"""
    segs, pts = section(ref, 1, y)
    if not segs:
        return []
    q = np.array(list(pts.values()))
    lo = q.min(axis=0) - (close + 3) * res
    n = np.ceil((q.max(axis=0) + (close + 3) * res - lo) / res).astype(int) + 1
    wall = np.zeros(n, dtype=bool)
    for a, b in segs:
        pa, pb = np.array(pts[a]), np.array(pts[b])
        k = max(2, int(np.linalg.norm(pb - pa) / (res * 0.5)) + 1)
        line = pa[None, :] + (pb - pa)[None, :] * np.linspace(0, 1, k)[:, None]
        ij = np.floor((line - lo) / res).astype(int)
        wall[ij[:, 0], ij[:, 1]] = True
    wall = _grow2(wall, close)
    lab, _n = _label(~wall)
    outside = np.zeros_like(wall)
    for border in set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1]):
        if border:
            outside |= lab == border
    solid = ~_grow2(outside, close)   # (a closing: the walls grown to bridge gaps, then shrunk back by as much)
    lab, count = _label(solid)
    out = []
    for k in range(1, count + 1):
        cells = np.argwhere(lab == k)
        c_lo, c_hi = cells.min(axis=0), cells.max(axis=0)
        size = (c_hi - c_lo + 1) * res
        if max(size) < min_size:
            continue
        mid = lo + (c_lo + c_hi + 1) / 2.0 * res
        out.append({"centre": (float(mid[0]), float(mid[1])), "width": float(max(size[0], 0)),
                    "depth": float(max(size[1], 0)), "area": float(len(cells) * res * res), "mask": lab == k,
                    "lo": tuple(float(x) for x in lo), "res": res})
    out.sort(key=lambda r: -r["area"])
    return out


# ------------------------------------------------------------------------------------------------ outlines
def outline(ref, view, res=0.5, hole_mm2=400.0):
    """the EXACT silhouette of the mesh seen from `view` ("side": looking along x — (forward = -z, up = y); "front":
    along z — (x, up = y)), rastered at res mm from the triangles themselves (no picture, no trace) -> a boolean
    mask and its frame: {"mask": (nu, nv) bool, "lo": (u0, v0), "res"} — a sculpt's from_reference() trims to it"""
    v = ref.verts
    uv = np.stack([-v[:, 2], v[:, 1]], axis=1) if view == "side" else v[:, [0, 1]]
    lo = uv.min(axis=0) - 2 * res
    n = np.ceil((uv.max(axis=0) + 2 * res - lo) / res).astype(int) + 1
    mask = np.zeros(n, dtype=bool)
    for tri in ref.tris:
        p = (uv[tri] - lo) / res
        a, b_, c = p
        mn = np.floor(p.min(axis=0)).astype(int)
        mx = np.ceil(p.max(axis=0)).astype(int)
        if (mx - mn).max() > 400:
            continue
        gu, gv = np.meshgrid(np.arange(mn[0], mx[0] + 1), np.arange(mn[1], mx[1] + 1), indexing="ij")
        q = np.stack([gu.ravel(), gv.ravel()], axis=1).astype(np.float64)
        d = (b_[1] - c[1]) * (a[0] - c[0]) + (c[0] - b_[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue
        l1 = ((b_[1] - c[1]) * (q[:, 0] - c[0]) + (c[0] - b_[0]) * (q[:, 1] - c[1])) / d
        l2 = ((c[1] - a[1]) * (q[:, 0] - c[0]) + (a[0] - c[0]) * (q[:, 1] - c[1])) / d
        ins = (l1 >= -1e-6) & (l2 >= -1e-6) & (1 - l1 - l2 >= -1e-6)
        qi = q[ins].astype(int)
        mask[qi[:, 0], qi[:, 1]] = True
    # a scan's holes go straight THROUGH it: seen from the side they are holes in its silhouette, and a keep trim (a
    # prism through the object) drilled each one as a pit (142 on a skull, up to 10 x 10 mm) — closed unless bigger
    # than hole_mm2 (a real see-through opening: a handle's loop, a trigger guard)
    lab, n_ = _label(~mask)
    border = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1])
    for k in range(1, n_ + 1):
        if k in border:
            continue
        hole = lab == k
        if hole.sum() * res * res < hole_mm2:
            mask |= hole
    return {"mask": mask, "lo": tuple(float(x) for x in lo), "res": float(res)}


# ------------------------------------------------------------------------------------------------ landmarks
def surface_points(ref, n=200000, seed=0):
    """points spread over the triangles by area (deterministic) — a coarse mesh has no vertex where a rule looks"""
    v, t = ref.verts, ref.tris
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    if area.sum() <= 0:
        return v.copy()
    rng = np.random.default_rng(seed)
    f = rng.choice(len(t), size=n, p=area / area.sum())
    u, w = rng.random(n), rng.random(n)
    flip = u + w > 1
    u[flip], w[flip] = 1 - u[flip], 1 - w[flip]
    return np.concatenate([v, a[f] + (b[f] - a[f]) * u[:, None] + (c[f] - a[f]) * w[:, None]])


def midline(ref, half=3.0, step=1.0):
    """the front of the mesh along x = 0 (its points within `half` mm), band by band `step` mm tall ->
    {y: front-most z}"""
    m = surface_points(ref, 400000)
    m = m[np.abs(m[:, 0]) <= half]
    out = {}
    if not len(m):
        return out
    bands = np.floor(m[:, 1] / step).astype(int)
    for b_ in np.unique(bands):
        out[float((b_ + 0.5) * step)] = float(m[bands == b_, 2].min())
    return out


RULES = ("front_max", "front_min", "top", "bottom", "side_max", "back_max")


def landmarks(ref, rules):
    """NAMED POINTS read off the reference by rules — never guessed (a skull's bite plane put 9 mm high by eye made
    its maxilla "a strip pasted under the cheek"). rules {name: (kind, y_lo, y_hi)}, heights in mm:
      front_max  the midline's most FORWARD point in [y_lo, y_hi]  (a chin, a nose tip, nasal bones, the brow)
      front_min  the midline's most RECESSED point in [y_lo, y_hi] (the nasion between brow and nose, the mouth's
                 deepest bite)
      top / bottom  the highest / lowest point of the whole mesh in the band (x free)
      side_max   the widest point (largest |x|) in the band — a cheekbone, a jaw angle (its right side, x > 0)
      back_max   the most BACKWARD point in the band (an occiput)
    -> {name: (x, y, z) mm}"""
    mid = midline(ref)
    v = surface_points(ref, 200000, seed=1)
    out = {}
    for name, (kind, y0, y1) in rules.items():
        if kind not in RULES:
            raise ValueError(f'landmark "{name}": kind "{kind}" — one of {", ".join(RULES)}')
        if kind in ("front_max", "front_min"):
            ys = [y for y in mid if y0 <= y <= y1]
            if not ys:
                raise ValueError(f'landmark "{name}": no midline between y {y0} and {y1}')
            y = (min if kind == "front_max" else max)(ys, key=lambda yy: mid[yy])
            out[name] = (0.0, y, mid[y])
            continue
        band = v[(v[:, 1] >= y0) & (v[:, 1] <= y1)]
        if not len(band):
            raise ValueError(f'landmark "{name}": nothing between y {y0} and {y1}')
        if kind == "top":
            p = band[np.argmax(band[:, 1])]
        elif kind == "bottom":
            p = band[np.argmin(band[:, 1])]
        elif kind == "side_max":
            p = band[np.argmax(band[:, 0])]
        else:
            p = band[np.argmax(band[:, 2])]
        out[name] = tuple(float(c) for c in p)
    return out
