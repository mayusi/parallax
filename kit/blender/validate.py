"""validate.py — run the Roblox mesh gate on any FBX/.blend (e.g. a downloaded CC0 model).

Usage: lune run kit validate <file.fbx|file.blend>
  (= blender -b --factory-startup -P kit/blender/validate.py -- <file>)
Prints one JSON line: {status, summary, next_action, groups:{mesh: checks}}. Assets built with rbx.Asset
are validated automatically by build(); use this for meshes that came from somewhere else.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
import rbx_validate  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
if not args or not os.path.isfile(args[0]):
    print(json.dumps({"status": "fail", "summary": f"no such file: {args[:1]}", "next_action": "pass a path"}))
    sys.exit(1)

path = os.path.abspath(args[0])
if path.lower().endswith(".blend"):
    bpy.ops.wm.open_mainfile(filepath=path)
else:
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)

results = {o.name: rbx_validate.validate_mesh(o) for o in rbx_validate.mesh_objects()}
if not results:
    status, summary, next_action = "fail", "no mesh objects in file", "check the file actually contains meshes"
else:
    status, summary, next_action = rbx_validate.verdict(results)
print(json.dumps({"schema": 1, "file": args[0], "status": status, "summary": summary, "next_action": next_action, "groups": results}))
sys.exit(0 if status == "pass" else 1)
