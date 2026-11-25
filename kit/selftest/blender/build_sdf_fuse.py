"""build_sdf_fuse.py — fixture: a.sdf_fuse (Blender's own distance-field nodes weld parts into one mesh). Two
overlapping blocks and a bore cut through them, filleted where they meet: ONE watertight part comes out, the inputs
leave the build — kit/test/python/test_sdf_fuse.py reads build/models/_selftest_sdf_fuse.check.json. Never "fix"
this file."""

import json
import os
import sys

_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_root, "kit", "blender")) and os.path.dirname(_root) != _root:
    _root = os.path.dirname(_root)
sys.path.insert(0, os.path.join(_root, "kit", "blender"))
import bmesh  # noqa: E402
import rbx  # noqa: E402

a = rbx.Asset("_selftest_sdf_fuse", tex=256, size=(0.6, 0.5, 0.6))
a.real_scale(280.0)
a.material("steel", **rbx.look("stainless_brushed"), life="light")
a.box("Base", (0.6, 0.2, 0.6), (0, 0.1, 0), "steel")
a.box("Post", (0.2, 0.4, 0.2), (0, 0.3, 0), "steel")
a.cylinder("Bore", 0.05, 0.8, (0, 0.25, 0), "steel")
fused = a.sdf_fuse("Body", ["Base", "Post", ("Bore", "DIFFERENCE")], voxel_mm=1.0, fillet=2)
bm = bmesh.new()
bm.from_mesh(fused.data)
check = {"parts": sorted(o.name for o, _g in a.parts), "faces": len(fused.data.polygons),
         "non_manifold": sum(1 for e in bm.edges if not e.is_manifold), "volume_studs3": abs(bm.calc_volume())}
bm.free()
os.makedirs(os.path.join(_root, "build", "models"), exist_ok=True)
with open(os.path.join(_root, "build", "models", "_selftest_sdf_fuse.check.json"), "w", encoding="utf-8") as fh:
    json.dump(check, fh)
