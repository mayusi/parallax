"""probe_same_twice.py — runs a build fixture (the path after `--`) and prints `SAME {json}`: for each mesh it built,
an ORDER-SENSITIVE hash of its vertices, faces (with their materials) and UVs, and the sha1 of each map it baked.
A test runs it several times: a build must give the same bytes every time (card nrey: Blender 5.2's
create_uvsphere listed its faces in another order every run, and every later step followed). Never "fix" this file."""

import hashlib
import json
import os
import runpy
import sys

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
script = ARGS[0]
sys.argv = [sys.argv[0]]
_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bpy  # noqa: E402

runpy.run_path(script, run_name="__main__")
import rbx  # noqa: E402

out = {}
for o in sorted((o for o in bpy.data.objects if o.type == "MESH" and not o.hide_render), key=lambda o: o.name):
    me = o.data
    h = hashlib.sha1()
    for v in me.vertices:
        h.update(("%.5f %.5f %.5f;" % tuple(v.co)).encode())
    for p in me.polygons:
        h.update((",".join(map(str, p.vertices)) + "/%d;" % p.material_index).encode())
    uv = me.uv_layers.active
    if uv is not None:
        for d in uv.data:
            h.update(("%.5f %.5f;" % tuple(d.uv)).encode())
    maps = {}
    for f in sorted(os.listdir(rbx.TEXTURES)):
        if f.startswith(o.name + "_") and f.endswith(".png") and "_raw_" not in f:
            with open(os.path.join(rbx.TEXTURES, f), "rb") as fh:
                maps[f[len(o.name) + 1:-4]] = hashlib.sha1(fh.read()).hexdigest()[:12]
    out[o.name] = {"mesh": h.hexdigest()[:12], "maps": maps}
print("SAME " + json.dumps(out))
