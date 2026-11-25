"""cards_blender.py — the Blender half of `kit ui spin --cards K` (run headless by kit/ui/spin.py):

    blender -b --factory-startup --python-exit-code 2 -P kit/ui/cards_blender.py -- --job <job.json>

The job: {"layers": [<png>, ...] (far -> near), "size": [w, h], "gap": 0.06, "fbx": <out>} -> one quad per layer, its
picture on it with the picture's own alpha cutting it, spaced `gap` apart in depth (the near ones in front), exported as one
FBX — PARALLAX CARDS for a VFX or a ViewportFrame (each quad is its own object + material, named card_0 .. card_K-1).
"""
import json
import sys

import bpy  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
job = json.load(open(argv[argv.index("--job") + 1], encoding="utf-8"))
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
sc = bpy.context.scene
w, h = job["size"]
sx, sy = (2.0, 2.0 * h / w) if w >= h else (2.0 * w / h, 2.0)  # the long side = 2 units
gap = float(job.get("gap", 0.06))
made = []
for k, path in enumerate(job["layers"]):
    me = bpy.data.meshes.new(f"card_{k}")
    me.from_pydata([(-sx / 2, -sy / 2, 0), (sx / 2, -sy / 2, 0), (sx / 2, sy / 2, 0), (-sx / 2, sy / 2, 0)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="uv")
    for li, (u, v) in zip(range(4), [(0, 0), (1, 0), (1, 1), (0, 1)]):
        uv.data[li].uv = (u, v)
    mat = bpy.data.materials.new(f"card_{k}")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(path)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    if hasattr(mat, "blend_method"):
        mat.blend_method = "CLIP"
    me.materials.append(mat)
    ob = bpy.data.objects.new(f"card_{k}", me)
    ob.location.z = k * gap
    sc.collection.objects.link(ob)
    made.append(ob)
bpy.ops.object.select_all(action="DESELECT")
for ob in made:
    ob.select_set(True)
bpy.ops.export_scene.fbx(filepath=job["fbx"], use_selection=True, object_types={"MESH"}, apply_unit_scale=True, path_mode="COPY", embed_textures=True)
print("CARDS_DONE", len(made))
