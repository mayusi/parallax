"""a.physics(group, like=<material>): Roblox's own density, friction and elasticity for a named material
(kit/blender/rbx_physics.py, measured in Studio 2026-11-18; his V3 list, 3D stage G.2e)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402
import rbx_physics as RP  # noqa: E402

BLENDER = cad_check.blender()


class Table(unittest.TestCase):
    def test_roblox_names_in_any_case_and_the_words_a_brief_says(self):
        self.assertEqual(RP.like("Metal"), ("Metal", (7.85, 0.4, 0.25)))
        self.assertEqual(RP.like("woodplanks")[0], "WoodPlanks")
        self.assertEqual(RP.like("Bronze")[0], "Metal")          # (the engine has one Metal for every metal)
        self.assertEqual(RP.like("stone")[0], "Rock")
        self.assertEqual(RP.like("Wood")[1], (0.35, 0.48, 0.2))  # (Roblox's wood, not a textbook's 0.7)

    def test_an_unknown_material_is_refused_with_the_nearest_names(self):
        with self.assertRaises(ValueError) as e:
            RP.like("metl")
        self.assertIn("did you mean", str(e.exception))
        self.assertIn("Metal", str(e.exception))

    def test_every_number_is_in_the_range_a_physics_call_takes(self):
        for name, (d, f, e) in RP.MATERIALS.items():
            self.assertTrue(0.01 <= d <= 100 and 0 <= f <= 2 and 0 <= e <= 1, name)


BUILD = '''
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[sys.argv.index("--") + 1], "kit", "blender"))
import rbx
a = rbx.Asset("_test_physics_like", size=(1.0, 1.0, 1.0), ground=False)
a.material("bronze", color=(0.55, 0.36, 0.18), metal=1.0, rough=0.4)
a.box("Body", (1.0, 1.0, 1.0), (0, 0, 0), "bronze", bevel=0)
a.physics("main", like="bronze", friction=0.1)
try:
    a.physics("main", like="unobtainium")
    bad = None
except ValueError as e:
    bad = str(e)
print("PHYS " + json.dumps({"rec": a._physics["main"], "bad": bad}))
'''


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class InTheBuild(unittest.TestCase):
    def test_like_gives_the_group_the_engines_numbers_and_a_number_given_beside_it_wins(self):
        with tempfile.TemporaryDirectory() as d:
            script = os.path.join(d, "b.py")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write(BUILD)
            r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", ROOT],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=600, env=dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join(d, "build")))
        line = next((x for x in r.stdout.splitlines() if x.startswith("PHYS ")), None)
        self.assertIsNotNone(line, (r.stderr or r.stdout)[-800:])
        got = json.loads(line[5:])
        self.assertEqual(got["rec"], {"like": "Metal", "density": 7.85, "friction": 0.1, "elasticity": 0.25})
        self.assertIn("is not a Roblox material", got["bad"])


if __name__ == "__main__":
    unittest.main()
