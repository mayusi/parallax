"""delight_swap.py - a scan given its colour without the photographed light (kit/tools/delight.py; his D-R03).

blender -b --factory-startup -P delight_swap.py -- <scan.glb> <albedo.png> <out.glb>"""

import os
import sys

import bpy

ARGS = [os.path.abspath(a) for a in sys.argv[sys.argv.index("--") + 1:]]
GLB, ALBEDO, OUT = ARGS[:3]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
img = bpy.data.images.load(ALBEDO)
img.pack()
done = 0
for m in bpy.data.materials:
    if not m.use_nodes:
        continue
    for n in m.node_tree.nodes:
        if n.type == "TEX_IMAGE":
            n.image = img
            done += 1
if not done:
    raise SystemExit("delight_swap: the scan has no colour texture to replace")
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=False, export_yup=True)
print("SWAP", done)
