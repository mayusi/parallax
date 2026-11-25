"""make_ivy.py — English ivy GROWN up a wall (rbx_ivy) and built as meshes: the stems on the wall, each leaf a REAL
photographed leaf (foliage_leaves.py's atlas: its own outline, mapped onto its own photo) on a curved petiole.

    blender -b --factory-startup -P kit/blender/make_ivy.py -- <leaves.json> <stems.glb> <leaves.glb>
        [--width 2400] [--height 2000] [--seed 3] [--up 0.4] [--wander 0.7] [--branch 0.06] [--tips 90]

Wall frame: x right, y up (mm), the leaves out toward +z (glTF's front). Exported in metres. The stems carry no
texture (the build gives them the kit's bark); the leaves carry the leaf atlas. Prints one JSON line.
"""

import json
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rbx_ivy  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
leaves_json, stems_out, leaves_out = (os.path.abspath(p) for p in argv[:3])


def arg(name, default, cast=float):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


W, H = arg("--width", 2400.0), arg("--height", 2000.0)
with open(leaves_json, encoding="utf-8") as fh:
    LJ = json.load(fh)
atlas_path = os.path.join(os.path.dirname(leaves_json), LJ["atlas"])
normal_path = os.path.join(os.path.dirname(leaves_json), LJ["normal"]) if LJ.get("normal") else None
rbx_ivy.R_MAX = arg("--rmax", 15.0)
g = rbx_ivy.grow(W, H, seed=arg("--seed", 3, int), up=arg("--up", 0.4), wander=arg("--wander", 0.7),
                 branch_p=arg("--branch", 0.06), max_tips=arg("--tips", 90, int), roots=arg("--roots", 3, int))
rng = np.random.default_rng(arg("--seed", 3, int) + 7)

# ------------------------------------------------------------------------------------------------ the leaf shapes
RING = 24
shapes = []
for lf in LJ["leaves"]:
    o = np.array(lf["outline"], float)
    idx = np.linspace(0, len(o), RING, endpoint=False).astype(int)
    o = o[idx]
    uv = np.array(lf["uv"], float)[idx]
    # frame -> uv is affine (the atlas cell is the photo scaled): fitted exactly, for the inner ring and the centre
    A = np.column_stack([o, np.ones(len(o))])
    M, *_ = np.linalg.lstsq(A, uv, rcond=None)
    c = o.mean(axis=0)
    shapes.append({"o": o, "M": M, "c": c})


def frame_uv(s, p):
    return np.column_stack([p, np.ones(len(p))]) @ s["M"]


# ------------------------------------------------------------------------------------------------------ the stems
SIDES = 8
sv, sf = [], []
for st in g["stems"]:
    pts, r = st["pts"], st["r"]
    n = len(pts)
    base = len(sv)
    for i in range(n):
        d = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        d = d / max(np.linalg.norm(d), 1e-9)
        side = np.array([-d[1], d[0], 0.0])
        out = np.array([0.0, 0.0, 1.0])
        centre = np.array([pts[i][0], pts[i][1], r[i] * 0.92])   # (pressed to the wall by its rootlets)
        for k in range(SIDES):
            a = 2 * np.pi * k / SIDES
            sv.append(centre + r[i] * (np.cos(a) * side + np.sin(a) * out))
    for i in range(n - 1):
        for k in range(SIDES):
            a0, a1 = base + i * SIDES + k, base + i * SIDES + (k + 1) % SIDES
            b0, b1 = a0 + SIDES, a1 + SIDES
            sf.append((a0, b0, b1, a1))
    # capped ends (a closed tube)
    sf.append(tuple(base + k for k in range(SIDES))[::-1])
    sf.append(tuple(base + (n - 1) * SIDES + k for k in range(SIDES)))

# ----------------------------------------------------------------------------------- the leaves and their petioles
lv, lf_, luv = [], [], []
UP = np.array([0.0, 1.0, 0.0])
Z = np.array([0.0, 0.0, 1.0])
PET_SIDES, PET_SEG = 4, 4
for L in g["leaves"]:
    if L["node"][1] < 1.1 * L["length"]:   # (a leaf this low would hang into the ground: ivy's foot is bare wood)
        continue
    # a tone group by weight (wall ivy mostly mid to dark green — the flora: "pale green to dark green"), then a leaf
    tones = sorted({lf.get("tone", 1.0) for lf in LJ["leaves"]}, reverse=True)
    weights = [0.35, 0.4, 0.25] if len(tones) == 3 else [1.0 / len(tones)] * len(tones)   # (by rank: light .. dark)
    acc, pick_t = 0.0, tones[-1]
    for t, w_ in zip(tones, weights):
        acc += w_
        if L.get("tone", 0.5) <= acc:
            pick_t = t
            break
    group = [i for i, lf in enumerate(LJ["leaves"]) if lf.get("tone", 1.0) == pick_t] or list(range(len(shapes)))
    s = shapes[group[L["leaf"] % len(group)]]
    node = np.array([L["node"][0], L["node"][1], L["stem_r"] * 1.6])
    lat = np.array([L["lateral"][0], L["lateral"][1], 0.0])
    pet = L["petiole"]
    # the petiole: a quadratic curve out from the wall, then sideways and a little down
    p0 = node
    p1 = node + Z * pet * 0.65 + lat * pet * 0.25
    p2 = node + Z * pet * L["lift"] + lat * pet * 0.6 - UP * pet * 0.12
    # the blade: facing out and up to the light (tilt), tip hanging down and a little sideways, rolled
    # PHOTOTROPIC: a wall ivy's blades turn out to the light (normal out, tilted up 15-45 deg), tips hang down within
    # ~35 deg either way, overlapping the leaves below like shingles (the reference wall); the first build's random
    # rolls read as scattered cards
    normal = np.array([0.0, np.sin(L["tilt"]), np.cos(L["tilt"])])
    tipdir = -UP + lat * (0.25 + 0.6 * L.get("swing", 0.0))
    tipdir -= normal * (tipdir @ normal)
    tipdir /= max(np.linalg.norm(tipdir), 1e-9)
    across = np.cross(normal, tipdir)
    c_, s_ = np.cos(L["roll"]), np.sin(L["roll"])
    tipdir, across = c_ * tipdir + s_ * across, -s_ * tipdir + c_ * across
    Lm = L["length"]
    fold = rng.uniform(0.10, 0.22)     # (the blade's V along its midrib)
    curl = rng.uniform(-0.05, 0.12)    # (its tip curls)

    def place(p):
        x, y = p[:, 0], p[:, 1]
        off = fold * np.abs(x) + curl * y ** 2
        return p2 + Lm * (x[:, None] * across + y[:, None] * tipdir + off[:, None] * normal)

    o = s["o"]
    inner = s["c"] + 0.5 * (o - s["c"])
    pts = np.vstack([s["c"][None, :], inner, o])
    uvs = frame_uv(s, pts)
    base = len(lv)
    lv.extend(place(pts))
    luv.extend(uvs)
    for k in range(RING):
        k1 = (k + 1) % RING
        lf_.append((base, base + 1 + k, base + 1 + k1))                         # (the centre fan)
        lf_.append((base + 1 + k, base + 1 + RING + k, base + 1 + RING + k1, base + 1 + k1))   # (the outer ring)
    # the petiole tube, its UVs on the leaf's own midrib (green, as a petiole is)
    pbase = len(lv)
    mid_uv = frame_uv(s, np.array([[0.0, 0.08]]))[0]
    for j in range(PET_SEG + 1):
        t = j / PET_SEG
        q = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t * t * p2
        dq = 2 * (1 - t) * (p1 - p0) + 2 * t * (p2 - p1)
        dq /= max(np.linalg.norm(dq), 1e-9)
        a1 = np.cross(dq, UP)
        a1 = a1 / max(np.linalg.norm(a1), 1e-9) if np.linalg.norm(a1) > 1e-6 else np.array([1.0, 0, 0])
        a2 = np.cross(dq, a1)
        rp = 1.3 * (1 - 0.3 * t)
        for k in range(PET_SIDES):
            a = 2 * np.pi * k / PET_SIDES
            lv.append(q + rp * (np.cos(a) * a1 + np.sin(a) * a2))
            luv.append(mid_uv)
    for j in range(PET_SEG):
        for k in range(PET_SIDES):
            a0 = pbase + j * PET_SIDES + k
            a1_ = pbase + j * PET_SIDES + (k + 1) % PET_SIDES
            lf_.append((a0, a0 + PET_SIDES, a1_ + PET_SIDES, a1_))


def build(name, verts, faces, uvs=None, image=None, normal=None, rough=0.45):
    me = bpy.data.meshes.new(name)
    V = np.asarray(verts, float) / 1000.0   # (mm -> m)
    # the wall frame (x right, y up, z out) into BLENDER's (z up): the glTF export turns Blender's (x, -z, y)... back
    # into y up, +z front — built in the wall frame as it was, the wall's up came out as depth (the stems lay flat)
    V = np.column_stack([V[:, 0], -V[:, 2], V[:, 1]])
    me.from_pydata([tuple(v) for v in V], [], [tuple(f) for f in faces])
    if uvs is not None:
        uvl = me.uv_layers.new(name="UVMap")
        loops_v = np.empty(len(me.loops), np.int64)
        me.loops.foreach_get("vertex_index", loops_v)
        U = np.asarray(uvs, float)[loops_v]
        uvl.data.foreach_set("uv", U.astype(np.float32).ravel())
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if image:
        tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(image)
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = rough   # (the flora: "more or less dull or somewhat glossy")
    if normal:   # (the veins' relief: foliage_leaves' normal map from each leaf's own photo)
        ntex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        ntex.image = bpy.data.images.load(normal)
        ntex.image.colorspace_settings.name = "Non-Color"
        nmap = mat.node_tree.nodes.new("ShaderNodeNormalMap")
        nmap.inputs["Strength"].default_value = 1.0
        mat.node_tree.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
        mat.node_tree.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Metallic"].default_value = 0.0
    me.materials.append(mat)
    return ob


bpy.ops.wm.read_factory_settings(use_empty=True)
st = build("IvyStems", sv, sf)
lv_ob = build("IvyLeaves", lv, lf_, luv, atlas_path, normal=normal_path, rough=0.32)   # (ivy's waxy cuticle)
for ob, path in ((st, stems_out), (lv_ob, leaves_out)):
    for o in bpy.context.scene.objects:
        o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True)
def box(v):
    v = np.asarray(v, float)
    return [[round(float(x), 2) for x in v.min(axis=0)], [round(float(x), 2) for x in v.max(axis=0)]]


# each GLB's box in the wall frame (mm): the build places both by it, so the stems and the leaves stay one plant
side = {"wall_mm": [W, H], "stems_box_mm": box(sv), "leaves_box_mm": box(lv), "stems": stems_out, "leaves": leaves_out}
with open(os.path.splitext(leaves_out)[0].replace("__leaves.gen", "__ivy") + ".json", "w", encoding="utf-8") as fh:
    json.dump(side, fh, indent=1)
stem_len = sum(float(np.linalg.norm(np.diff(s["pts"], axis=0), axis=1).sum()) for s in g["stems"])
print(json.dumps({"schema": 1, "status": "pass",
                  "summary": f"make_ivy: {len(g['stems'])} stems ({stem_len / 1000:.1f} m), {len(g['leaves'])} leaves "
                             f"on a {W:.0f} x {H:.0f} mm wall", "next_action": "none",
                  "stems": len(g["stems"]), "leaves": len(g["leaves"]), "stem_m": round(stem_len / 1000, 2),
                  "tris_leaves": len(lf_), "verts": len(lv) + len(sv)}))
