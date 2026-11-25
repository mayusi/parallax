"""Real-world sizes (kit/real_sizes.json + kit/blender/rbx_sizes.py): Asset(kind=...) checks a model's measured size
against the range real ones come in — ranges read from Infinigen's asset factories, each row linking its source."""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_sizes as Z  # noqa: E402

T = Z.load()
PINNED = re.compile(r"^https://github\.com/princeton-vl/infinigen/blob/[0-9a-f]{40}/src/infinigen/\S+\.py#L\d+(-L\d+)?$")


class TestTable(unittest.TestCase):
    def test_every_row_is_sourced_and_well_formed(self):
        self.assertEqual(T["stud_m"], 0.28)  # Roblox's unit: create.roblox.com/docs/physics/units
        self.assertGreaterEqual(len(T["kinds"]), 10)
        for kind, row in T["kinds"].items():
            with self.subTest(kind=kind):
                self.assertRegex(kind, r"^[a-z_]+$")
                self.assertTrue(row["source"])
                for url in row["source"]:
                    self.assertRegex(url, PINNED)  # a pinned commit and the lines it came from
                self.assertTrue(row["about"])
                lo, hi = row["height"]
                self.assertLess(lo, hi)
                mids = []
                for name, flo, fhi in row["footprint"]:
                    self.assertLess(flo, fhi)
                    mids.append((flo + fhi) / 2)
                self.assertEqual(mids, sorted(mids))  # the smaller side first: the model's sorted sizes map onto it


class TestJudge(unittest.TestCase):
    def test_a_chair_six_studs_tall_is_named_with_its_source(self):
        ok, fix, fact = Z.judge((1.6, 6.0, 1.5), "chair")
        self.assertFalse(ok)
        self.assertIn("0.85-1.00 m tall", fix)
        self.assertIn("Infinigen chair.py", fix)
        self.assertIn("1.68x the largest", fix)  # 6 studs = 1.68 m, against 1.00 m
        self.assertIn("chair: 1.68 m tall", fact)

    def test_a_real_sized_chair_passes(self):
        ok, fix, _ = Z.judge((1.6, 3.3, 1.5), "chair")
        self.assertTrue(ok)
        self.assertEqual(fix, "")

    def test_the_footprint_is_checked_in_any_orientation(self):
        along_z = Z.judge((6.0, 3.6, 7.9), "double_bed")  # 1.68 m wide, 2.2 m long
        along_x = Z.judge((7.9, 3.6, 6.0), "double_bed")
        self.assertTrue(along_z[0])
        self.assertTrue(along_x[0])

    def test_the_leeway_lets_real_objects_stray_a_little(self):
        top = 1.0 / 0.28  # the tallest chair, in studs
        self.assertTrue(Z.judge((1.6, top * 1.2, 1.5), "chair")[0])
        self.assertFalse(Z.judge((1.6, top * 1.3, 1.5), "chair")[0])
        self.assertFalse(Z.judge((1.6, 0.6 / 0.28, 1.5), "chair")[0])  # a 0.6 m chair: under 0.85 by more than 25%

    def test_real_scale_overrides_roblox_unit(self):
        size = (3.0, 6.5, 3.0)  # 6.5 studs: 1.82 m at Roblox's unit, 0.95 m at 145.7 mm a stud
        self.assertFalse(Z.judge(size, "chair")[0])
        ok, _, fact = Z.judge(size, "chair", mm_per_stud=145.7)
        self.assertTrue(ok)
        self.assertIn("146 mm a stud", fact)

    def test_a_flat_model_does_not_divide_by_zero(self):
        ok, fix, _ = Z.judge((3.1, 7.9, 0.0), "door")
        self.assertFalse(ok)
        self.assertIn("m thick", fix)

    def test_an_unknown_kind_lists_the_known_ones(self):
        ok, fix, fact = Z.judge((1, 1, 1), "throne")
        self.assertIsNone(ok)
        self.assertIsNone(fact)
        self.assertIn("chair", fix)
        self.assertIn("add a row with its source", fix)

    def test_typical_size_is_the_ranges_middle_in_studs(self):
        self.assertEqual(Z.typical("chair"), (1.6, 3.3, 1.5))
        self.assertEqual(Z.typical("wall"), (None, 10.7, 0.9))  # its length is free
        self.assertEqual(Z.typical("floor_lamp"), (None, 4.5, None))
        self.assertIsNone(Z.typical("throne"))


if __name__ == "__main__":
    unittest.main()
