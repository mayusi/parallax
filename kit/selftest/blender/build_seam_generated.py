"""build_seam_generated.py - fixture for SEAMS PLACED ON A GENERATED MESH (a.seams; the 3D methods audit's last
PARTLY of seam placement). A generator's mesh brings its own atlas and its paint laid on it; it used to keep that
layout whatever the author placed and fail seam_placed ("its map is not cut where the seams were placed"). Here a
generator-like ball (its own UVs, a map painted red where x > 0 and blue where x < 0) is imported and cut down the
back of its middle (one ring of the sphere's own meridian edges): it is laid along that cut in the atlas, and its
paint is baked across from the generator's own layout - every face keeps its colour.
After --: "mixed" - the same ball JOINED with a kit-made block in one group (the automatic unwrap lays every face
afresh; the ball's paint is baked across through its own layout all the same).
Prints SEAMGEN {...}. Used by kit/test/python/test_seam_generated_build.py. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))

import bpy  # noqa: E402
import numpy as np  # noqa: E402

BUILD = os.path.abspath(os.environ.get("KIT_BUILD") or os.path.join(_root, "build"))
WORK = os.path.join(BUILD, "selftest", "seam_generated")
os.makedirs(WORK, exist_ok=True)
GLB = os.path.join(WORK, "ball.glb")


def make_ball():
    """a generator-like mesh: a ball with its OWN atlas and a painted map"""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=0.4)
    ob = bpy.context.active_object
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    n = 256
    img = bpy.data.images.new("paint", n, n)
    px = np.zeros((n, n, 4), np.float32)
    px[..., 3] = 1
    me = ob.data
    uv = me.uv_layers.active
    for p in me.polygons:
        col = (0.9, 0.05, 0.05) if p.center.x > 0 else (0.05, 0.1, 0.9)
        us = np.array([uv.data[li].uv[:] for li in p.loop_indices])
        x0, y0 = (us.min(0) * n).astype(int)
        x1, y1 = np.ceil(us.max(0) * n).astype(int)
        px[max(y0 - 1, 0):y1 + 1, max(x0 - 1, 0):x1 + 1, :3] = col
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = os.path.join(WORK, "paint.png")
    img.file_format = "PNG"
    img.save()
    mat = bpy.data.materials.new("paint")
    mat.use_nodes = True
    t = mat.node_tree.nodes.new("ShaderNodeTexImage")
    t.image = img
    mat.node_tree.links.new(t.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    me.materials.append(mat)
    bpy.ops.export_scene.gltf(filepath=GLB, export_format="GLB")


make_ball()
import rbx  # noqa: E402

HOW = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv[:-1] else "alone"
NAME = "_selftest_seam_generated" + ("_mixed" if HOW == "mixed" else "")
if HOW == "mixed":
    a = rbx.Asset(NAME, tex=256, size=(1.25, 0.8, 0.8), ground=False, stage="master")
    a.material("grey", (0.5, 0.5, 0.5), rough=0.5)
    a.import_mesh("Ball", GLB, height=0.8, pos=(-0.25, 0, 0), ground=False)
    a.box("Block", (0.5, 0.5, 0.5), (0.35, 0, 0), "grey")   # (sunk 0.05 into the ball's side: one body)
else:
    a = rbx.Asset(NAME, tex=256, size=(0.8, 0.8, 0.8), ground=False, stage="master")
    a.import_mesh("Ball", GLB, height=0.8, ground=False)
X0 = -0.25 if HOW == "mixed" else 0.0   # (the ball's middle)
a.seams("Ball", cut=lambda p, q: abs(p[0] - X0) < 0.03 and abs(q[0] - X0) < 0.03 and p[2] > 0.0 and q[2] > 0.0)
verdict = {}
try:
    a.build()
except SystemExit:
    pass
models = os.path.join(BUILD, "models")
bpy.ops.wm.open_mainfile(filepath=os.path.join(models, f"{NAME}.blend"))
img = bpy.data.images.load(os.path.join(models, "textures", f"{NAME}_color.png"))
W, H = img.size
px = np.array(img.pixels[:]).reshape(H, W, 4)
wrong = n = 0
for ob in [o for o in bpy.data.objects if o.type == "MESH"]:
    me = ob.data
    uv = me.uv_layers.get("UVMap") or me.uv_layers.active
    for p in me.polygons:
        c = ob.matrix_world @ p.center
        dx = c.x - X0
        if abs(dx) < 0.08 or (dx * dx + c.y * c.y + c.z * c.z) ** 0.5 < 0.36 or (HOW == "mixed" and dx > 0.15):
            continue   # (the band along the cut straddles both colours; only the ball's own skin, clear of the block)
        u = np.mean([uv.data[li].uv[:] for li in p.loop_indices], axis=0)
        r, _g, b = px[min(int(u[1] * H), H - 1), min(int(u[0] * W), W - 1), :3]
        n += 1
        wrong += int((dx > 0) != (r > b))
print("SEAMGEN " + json.dumps({"faces": n, "wrong_colour": wrong}))
