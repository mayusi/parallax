"""The level-of-detail simulation is KEPT between builds by the mesh's own key (card fbvv: it ran on every full
build and group, about 3.5 s on a 200k-triangle mesh): the second ask of the same mesh comes from the cache with
the same answer, a mesh moved by a hair is asked again."""

import json
import os
import subprocess
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class LodKept(unittest.TestCase):
    def test_kept_the_same_and_asked_again_when_it_changes(self):
        cache = tempfile.mkdtemp()
        src = textwrap.dedent(f"""
            import sys, json, time
            sys.path.insert(0, {os.path.join(ROOT, 'kit', 'blender')!r})
            import bpy, rbx_optimize as O
            bpy.ops.mesh.primitive_uv_sphere_add(segments=256, ring_count=128, radius=1.0)
            ob = bpy.context.active_object
            bpy.ops.object.modifier_add(type="DISPLACE")
            ob.modifiers[-1].texture = bpy.data.textures.new("n", "CLOUDS")
            ob.modifiers[-1].strength = 0.1
            bpy.ops.object.modifier_apply(modifier=ob.modifiers[-1].name)
            out = {{}}
            t = time.time(); a, k1 = O.lod_preview_kept(ob, 280.0, {cache!r}); out["first_s"] = time.time() - t
            t = time.time(); b, k2 = O.lod_preview_kept(ob, 280.0, {cache!r}); out["second_s"] = time.time() - t
            out.update(k1=k1, k2=k2, same=(json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)),
                       fresh_same=(json.dumps(O.lod_preview(ob, 280.0), sort_keys=True) == json.dumps(b, sort_keys=True)))
            ob.data.vertices[0].co.z += 0.001
            c, k3 = O.lod_preview_kept(ob, 280.0, {cache!r})
            out["k3"] = k3
            out["tris"] = sum(len(p.vertices) - 2 for p in ob.data.polygons)
            print("LOD " + json.dumps(out))
            """)
        path = os.path.join(tempfile.mkdtemp(), "lod.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", path], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
        line = [x for x in out.stdout.splitlines() if x.startswith("LOD ")]
        self.assertTrue(line, out.stdout[-1500:] + out.stderr[-1500:])
        got = json.loads(line[0][4:])
        self.assertFalse(got["k1"])
        self.assertTrue(got["k2"])
        self.assertTrue(got["same"])
        self.assertTrue(got["fresh_same"])        # (the kept answer is what a fresh simulation says)
        self.assertFalse(got["k3"])               # (a point moved a millimetre: asked again)
        self.assertLess(got["second_s"], got["first_s"] / 5)


if __name__ == "__main__":
    unittest.main()
