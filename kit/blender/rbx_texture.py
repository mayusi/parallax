"""rbx_texture.py — a picture's look on the kit's own geometry: the arithmetic half of a.texture_from (numpy, no bpy).

`lune run kit gen texture <asset> --image <picture>` exports the asset's last full build (kit/blender/texture_export.py)
and has TRELLIS.2 paint it from the picture (kit/gen/trellis2_texture.py) -> assets/models/<asset>.tex.glb. At bake
time a.texture_from(...) carries that mesh's maps onto the asset's own atlas by a closest-surface bake (rbx.py,
_transfer_texture). What is left is arithmetic, kept here so it is tested without Blender:
- write_ply / read_ply: the exported mesh, in the kit's own space (Roblox studs, Y up, -Z front) — the frame a glTF
  file uses, so the textured GLB comes back (Blender's glTF import: Y up -> Z up) exactly where the parts are built;
- mix: the transferred maps over the kit's own, by `amount` and only where a bake ray found the textured surface;
- facts: how much of the atlas the textured surface covered, and how far its maps moved the kit's.
"""

import numpy as np

CHANNELS = ("color", "rough", "metal")


def write_ply(path, verts, tris, comment="kit gen texture: Roblox studs, Y up, -Z front"):
    """vertices (n, 3) + triangles (m, 3) -> a binary little-endian PLY (what trimesh and Blender read)"""
    verts = np.ascontiguousarray(np.asarray(verts, dtype=np.float64).reshape(-1, 3), dtype="<f4")
    tris = np.asarray(tris, dtype=np.int64).reshape(-1, 3)
    if len(tris) and (tris.min() < 0 or tris.max() >= len(verts)):
        raise ValueError(f"write_ply: a triangle points past the {len(verts)} vertices")
    face = np.empty(len(tris), dtype=[("n", "u1"), ("i", "<i4", (3,))])
    face["n"] = 3
    face["i"] = tris
    header = (f"ply\nformat binary_little_endian 1.0\ncomment {comment}\nelement vertex {len(verts)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              f"element face {len(tris)}\nproperty list uchar int vertex_indices\nend_header\n")
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii"))
        fh.write(verts.tobytes())
        fh.write(face.tobytes())


def read_ply(path):
    """a PLY written by write_ply -> (vertices float32 (n, 3), triangles int32 (m, 3))"""
    with open(path, "rb") as fh:
        data = fh.read()
    end = data.index(b"end_header\n") + len(b"end_header\n")
    head = data[:end].decode("ascii").splitlines()
    nv = int(next(h for h in head if h.startswith("element vertex")).split()[-1])
    nf = int(next(h for h in head if h.startswith("element face")).split()[-1])
    verts = np.frombuffer(data, dtype="<f4", count=nv * 3, offset=end).reshape(nv, 3)
    face = np.frombuffer(data, dtype=[("n", "u1"), ("i", "<i4", (3,))], count=nf, offset=end + nv * 12)
    if nf and not (face["n"] == 3).all():
        raise ValueError(f"read_ply: {path} has faces that are not triangles")
    return verts.copy(), face["i"].astype(np.int32)


def mix(kit, src, hit, amount):
    """kit, src: (H, W, 4) maps (RGB + alpha); hit: (H, W), 1 where the bake ray found the textured surface and 0
    where it missed; amount 0..1 -> the kit's map with src mixed in by amount where it was found (alpha kept)"""
    w = np.clip(np.asarray(hit, dtype=np.float32), 0, 1)[..., None] * float(np.clip(amount, 0, 1))
    out = np.array(kit, dtype=np.float32, copy=True)
    out[..., :3] = out[..., :3] * (1 - w) + np.asarray(src, dtype=np.float32)[..., :3] * w
    return out


def facts(kit, src, hit, island, channels=CHANNELS):
    """kit, src: {channel: (H, W, 4) map}; hit: (H, W) as in mix; island: (H, W), 1 on the atlas's own texels (its
    UV islands, without the bake margin) -> {coverage_pct: the share of those texels the textured surface was found
    under, mean_diff: per channel, the mean |src - kit| over them (0..1: 1 = black against white), mean_rgb: the
    colour channel's mean (0..255) for the kit and the texture there}"""
    isl = np.asarray(island) > 0.5
    got = isl & (np.asarray(hit) > 0.5)
    n = int(isl.sum())
    out = {"coverage_pct": round(100.0 * int(got.sum()) / n, 2) if n else 0.0, "texels": n, "mean_diff": {},
           "mean_rgb": {}}
    for ch in channels:
        width = 3 if ch == "color" else 1  # (a one-number map carries its value in R, G and B alike)
        a, b = np.asarray(kit[ch])[..., :width][got], np.asarray(src[ch])[..., :width][got]
        out["mean_diff"][ch] = round(float(np.abs(b - a).mean()), 4) if got.any() else None
        if ch == "color" and got.any():
            out["mean_rgb"] = {"kit": [round(float(v) * 255, 1) for v in a.mean(axis=0)],
                               "texture": [round(float(v) * 255, 1) for v in b.mean(axis=0)]}
    return out
