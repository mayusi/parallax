"""TWO-SIDED surfaces (rbx.Asset.two_sided; the owner's method lists, 2026-11-13: "two-sided" faces; the 3D
methods audit, S1): a sheet of faces with no thickness gets its back as real faces a hair behind it - a closed
solid, seen and lit from both sides in any engine."""

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
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_two_sided"))
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(ROOT, "kit", "selftest", "blender", "check_two_sided_cases.py"), "--",
                            "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=900, env=e,
                           encoding="utf-8", errors="replace")
        line = next((x for x in r.stdout.splitlines() if x.startswith("TWO_SIDED ")), None)
        assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
        cls.d = json.loads(line.split(" ", 1)[1])

    def test_a_sheet_becomes_a_closed_solid_a_hair_thick(self):
        self.assertEqual(self.d["before"][:3], [10, 0, 0])               # ten open edges round six faces
        for part in self.d["after"]:                                      # the part and its mirror copy
            self.assertEqual(part[:3], [0, 0, 0])                        # closed, no fin, wound alike
            self.assertEqual(part[4], 6 + 6 + 10)                        # front, back, and the rim round them
            self.assertAlmostEqual(part[5], self.d["area"] * 0.01, delta=self.d["area"] * 0.01 * 0.06)   # area x 0.01
        self.assertEqual(len(self.d["after"]), 2)
        self.assertEqual(self.d["facts"], ["Leaf"])

    def test_the_front_stays_where_it_was_made_and_the_back_is_behind_it(self):
        self.assertTrue(self.d["front_kept"])
        self.assertTrue(self.d["behind"])
        for off in self.d["behind"]:                                      # every back point: the thickness, behind
            self.assertLess(off, 0.0)
            self.assertAlmostEqual(off, -0.01, delta=0.0015)             # (a bent sheet's point normals lean a little)

    def test_a_sheet_with_one_side_or_folded_tighter_than_its_thickness_is_refused(self):
        self.assertIn("no two sides to tell apart", self.d["one_side"]["said"])
        self.assertIn("would pass through itself", self.d["crossing"]["said"])
        self.assertTrue(self.d["one_side"]["unchanged"] and self.d["crossing"]["unchanged"])

    def test_a_solid_is_refused_and_left_as_it_was(self):
        self.assertIn("has no border - it is a solid already", self.d["solid"]["said"])
        self.assertTrue(self.d["solid"]["unchanged"])

    def test_a_thickness_of_a_modelling_size_is_refused(self):
        self.assertIn("thickness=0.5", self.d["thick"]["said"])
        self.assertTrue(self.d["thick"]["unchanged"])


if __name__ == "__main__":
    unittest.main()
