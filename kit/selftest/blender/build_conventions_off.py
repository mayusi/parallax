"""build_conventions_off.py — NEGATIVE fixture for THE CONVENTIONS (rbx_conventions): a crate built 20 studs away
from its origin, its lid in a group named "TopCover" and painted with a material named "Dark-Steel". Must be
flagged, each by name: `naming` (the group and the material) and `pivot` (the origin lies off the model). After the
build one line `CONVENTIONS {json}` for kit/test/python/test_conventions_build.py: the exported file of ONE group
read back against the OTHER group's mesh (it must say what differs), against its own (nothing), and what the build
itself said. Used by `lune run kit selftest`. Never "fix" this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bpy  # noqa: E402
import rbx  # noqa: E402

a = rbx.Asset("_selftest_conventions_off", tex=64, size=(2.0, 1.4, 2.0), ground=True)
a.material("wood", color=(0.42, 0.3, 0.18), rough=0.7)
a.material("Dark-Steel", color=(0.2, 0.2, 0.22), metal=1.0, rough=0.5)
a.box("Crate", (2.0, 1.0, 2.0), (20.0, 0.5, 0), "wood", bevel=0)
a.box("Lid", (2.2, 0.4, 1.0), (20.0, 1.2, 0), "Dark-Steel", bevel=0, group="TopCover")
a.build()

manifest = json.load(open(os.path.join(rbx.BUILD, "models", "_selftest_conventions_off.manifest.json"),
                          encoding="utf-8"))
main, lid = bpy.data.objects["_selftest_conventions_off"], bpy.data.objects["_selftest_conventions_off_TopCover"]
out = {"own": a._read_back(main, manifest["groups"]["main"]["fbx"]),
       "other": a._read_back(main, manifest["groups"]["TopCover"]["fbx"]),
       "lid_own": a._read_back(lid, manifest["groups"]["TopCover"]["fbx"]),
       "objects_after": sorted(o.name for o in bpy.data.objects),
       "normal": manifest["groups"]["main"].get("normal_convention")}
main.scale = (100.0, 100.0, 100.0)   # the mesh the build "meant", 100 times larger than the file holds
bpy.context.view_layer.update()
out["scaled"] = a._read_back(main, manifest["groups"]["main"]["fbx"])
main.scale = (1.0, 1.0, 1.0)
bpy.context.view_layer.update()

# files written WRONG on purpose, into the build's scratch renders folder, each read back against the lid (an
# L-shaped mesh would be better still: the lid is a plain box, so a half turn is told by its PLACE here)
os.makedirs(rbx.RENDERS, exist_ok=True)


def written(name, turn=True, **settings):
    path = os.path.join(rbx.RENDERS, f"_selftest_conventions_{name}.fbx")
    a._select_only(lid)
    if turn:
        lid.data.transform(rbx.UPLOAD_TURN)
    try:
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True, bake_anim=False, add_leaf_bones=False,
                                 **{"axis_forward": "-Z", "axis_up": "Y", "apply_unit_scale": True,
                                    "apply_scale_options": "FBX_SCALE_UNITS", **settings})
    finally:
        if turn:
            lid.data.transform(rbx.UPLOAD_TURN.inverted())
    return a._read_back(lid, path)


out["as_meant"] = written("as_meant")
out["on_its_side"] = written("side", axis_forward="Y", axis_up="Z")       # the axes a default export writes
out["not_turned"] = written("not_turned", turn=False)                     # the half turn for Roblox left out
out["hundredfold"] = written("hundredfold", global_scale=100.0)
print("CONVENTIONS " + json.dumps(out))
