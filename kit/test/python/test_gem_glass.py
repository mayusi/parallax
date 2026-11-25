"""rbx_parts.glass_gems — the showcase's stones refract: a P.gem's faces carry its IOR through the build's join and
bake (face attribute kit_gem), and glass_gems gives exactly those faces a twin of their material with full
transmission at that IOR, no roughness, no glow; the plate under it keeps its own. The fixture:
kit/selftest/blender/build_gem_glass.py."""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()
BLEND = os.path.join(REPO, "build", "models", "_selftest_gem_glass.blend")
PROBE = r'''
import bpy, json, sys, os
sys.path.insert(0, os.path.join(os.getcwd(), "kit", "blender"))
import rbx_parts
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
n = rbx_parts.glass_gems(objs)
out = {"faces": n, "mats": []}
for o in objs:
    me = o.data
    for i, m in enumerate(me.materials):
        b = next((x for x in m.node_tree.nodes if x.type == "BSDF_PRINCIPLED"), None) if m and m.use_nodes else None
        used = sum(1 for p in me.polygons if p.material_index == i)
        g = lambda k: (b.inputs[k].default_value if b is not None and k in b.inputs else None)
        out["mats"].append({"name": m.name, "faces": used, "transmission": g("Transmission Weight"), "ior": g("IOR"),
                            "rough": g("Roughness"), "emit": g("Emission Strength")})
print("GEMS " + json.dumps(out))
'''


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class GemGlass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.isfile(BLEND):
            os.remove(BLEND)
        script = os.path.join(REPO, "kit", "selftest", "blender", "build_gem_glass.py")
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", "--no-preview"], cwd=REPO,
                           capture_output=True, text=True, timeout=900)
        assert r.returncode == 0 and os.path.isfile(BLEND), (r.stderr or r.stdout)[-800:]
        with tempfile.TemporaryDirectory() as t:
            probe = os.path.join(t, "probe.py")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write(PROBE)
            r = subprocess.run([BLENDER, "-b", BLEND, "-P", probe], cwd=REPO, capture_output=True, text=True,
                               timeout=600)
        line = next((ln for ln in r.stdout.splitlines() if ln.startswith("GEMS ")), None)
        assert line, (r.stderr or r.stdout)[-800:]
        cls.res = json.loads(line[5:])

    def test_only_the_stone_turns_to_glass(self):
        twin = re.compile(r"_glass\d")                                         # (the glass twin's suffix)
        glass = [m for m in self.res["mats"] if twin.search(m["name"]) and m["faces"]]
        self.assertEqual(len(glass), 1, self.res)
        self.assertEqual(glass[0]["faces"], self.res["faces"])
        self.assertEqual(self.res["faces"], 1 + 8 + 8 + 16 + 16 + 16)          # (every facet of the brilliant)
        self.assertAlmostEqual(glass[0]["ior"], 1.77, places=2)
        self.assertEqual((glass[0]["transmission"], glass[0]["rough"]), (1.0, 0.0))
        self.assertAlmostEqual(glass[0]["emit"], 0.15, places=3)                    # (a faint glow of its own colour)
        self.assertTrue(any(m["faces"] and not twin.search(m["name"]) for m in self.res["mats"]))  # (the plate)


if __name__ == "__main__":
    unittest.main()
