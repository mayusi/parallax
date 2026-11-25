"""The conventions through a REAL build (kit/selftest/blender/build_conventions_off.py): a group and a material
named against the rule and a model built off its origin are flagged by name; every exported file is read back; a
file read back against the wrong mesh, or a mesh 100 times the file's size, is said."""

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


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_conventions_build"))
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(ROOT, "kit", "selftest", "blender", "build_conventions_off.py"), "--",
                            "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e,
                           encoding="utf-8", errors="replace")
        line = next((x for x in r.stdout.splitlines() if x.startswith("CONVENTIONS ")), None)
        assert line, (r.stderr or r.stdout)[-800:]
        cls.out = json.loads(line[12:])
        cls.v = json.loads(next(x for x in reversed(r.stdout.splitlines())
                                if x.startswith("{") and '"status"' in x))

    def check(self, name):
        return [c for c in self.v["design"] if c["name"] == name]

    def test_a_group_and_a_material_named_against_the_rule_are_flagged_by_name(self):
        said = self.check("naming")
        self.assertEqual([c["severity"] for c in said], ["warn"])
        text = " ".join(said[0]["value"])
        self.assertIn('group "TopCover"', text)
        self.assertIn('material "Dark-Steel"', text)
        self.assertNotIn('"main"', text)
        self.assertNotIn('"wood"', text)

    def test_a_model_built_off_its_origin_says_how_far(self):
        said = self.check("pivot")
        self.assertEqual(len(said), 1)
        self.assertIn("18.90 studs outside", said[0]["value"])           # its box starts at x = 18.9

    def test_every_exported_file_is_read_back_and_is_the_mesh_exported(self):
        for g in ("main", "TopCover"):
            checks = {c["name"]: c for c in self.v["groups"][g]["checks"]}
            self.assertTrue(checks["export_read_back"]["ok"], g)
            self.assertEqual(checks["export_read_back"]["severity"], "error")
            self.assertTrue(checks["normal_convention"]["ok"], g)
        self.assertEqual((self.out["own"], self.out["lid_own"]), (None, None))
        self.assertIn("OpenGL", self.out["normal"])

    def test_a_file_read_back_against_the_wrong_mesh_says_what_differs(self):
        self.assertIsNotNone(self.out["other"])
        self.assertIn("different shape", self.out["other"])
        self.assertIn("0.01x the size", self.out["scaled"])              # the file is a hundredth of the mesh

    def test_a_file_written_with_the_wrong_axes_scale_or_turn_is_caught(self):
        # the review's find: read back by the file's own header, every one of these passed
        self.assertIsNone(self.out["as_meant"])
        self.assertIsNotNone(self.out["on_its_side"])                    # other axes: no longer undone by the header
        self.assertIsNotNone(self.out["not_turned"])                     # would face backwards in the game
        self.assertIn("100x the size", self.out["hundredfold"])

    def test_reading_back_leaves_nothing_behind_in_the_file(self):
        self.assertEqual(self.out["objects_after"],
                         ["_selftest_conventions_off", "_selftest_conventions_off_TopCover"])


if __name__ == "__main__":
    unittest.main()
