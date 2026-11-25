"""The game's settings a script says, through REAL builds (kit/selftest/blender/build_game_settings.py and its twin;
the 3D methods audit, stage O): a group's physics material and the model's far stand-in reach the manifest and
the model file the game loads; a wrong group or a number out of range stops the build."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join("build", "_test_game_settings_build")


def run(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                          cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                          errors="replace")


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = run("build_game_settings.py")
        got = next((x for x in cls.good.stdout.splitlines() if x.startswith("GAME ")), None)
        assert got, (cls.good.stderr or cls.good.stdout)[-800:]
        cls.at = json.loads(got[5:])
        line = next(x for x in reversed(cls.good.stdout.splitlines()) if x.startswith("{") and '"status"' in x)
        cls.v = json.loads(line)   # (strict: the kit reads this line the same way)
        cls.bad = run("build_game_settings_nogroup.py")

    def test_the_physics_material_is_on_its_group_alone_and_the_far_stand_in_on_the_model(self):
        self.assertEqual(self.at["tyre"], {"friction": 1.6, "elasticity": 0.6})
        self.assertIsNone(self.at["main"])
        self.assertEqual(self.at["far"], "StreamingMesh")
        self.assertIn("game: tyre elasticity 0.6 friction 1.6, far StreamingMesh", self.v["summary"])

    def test_a_group_the_asset_has_not_stops_the_build_and_names_the_ones_it_has(self):
        self.assertNotEqual(self.bad.returncode, 0)
        said = self.bad.stderr + self.bad.stdout
        self.assertIn('physics: no group "tire"', said)
        self.assertIn("main, tyre", said)


if __name__ == "__main__":
    unittest.main()
