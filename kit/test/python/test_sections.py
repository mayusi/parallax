"""kit refs sections: two models' cross-sections aligned on their rearmost section and MEASURED apart — a U where the
reference is a U reads near 0, a solid box where the reference is a U reads as ours' extra shape, a missing lip as the
reference's missing share."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "refs"))
import sections as S  # noqa: E402


def _rect(x0, x1, h0, h1, nm="o"):
    return [[[x0, h0], [x1, h0], nm], [[x1, h0], [x1, h1], nm], [[x1, h1], [x0, h1], nm], [[x0, h1], [x0, h0], nm]]


def _cut(slices, along=()):
    return {"cross": [{"d": d, "segs": s} for d, s in slices], "along": list(along), "mm_per_unit": 1.0}


class Deviation(unittest.TestCase):
    def test_same_shape_reads_zero(self):
        a = _rect(-10, 10, -20, 0)
        r = S.deviation(a, a)
        self.assertEqual(r["p90"], 0.0)
        self.assertEqual(r["missing"], 0.0)
        self.assertEqual(r["extra"], 0.0)

    def test_offset_reads_its_distance(self):
        r = S.deviation(_rect(-10, 10, -20, 0), _rect(-10, 10, -22, -2))
        self.assertGreater(r["p90"], 1.5)
        self.assertLess(r["p90"], 2.6)

    def test_missing_and_extra_tell_which_side_lacks_shape(self):
        ref = _rect(-10, 10, -20, 0) + _rect(-6, 6, -16, -4)   # a hollow section: outer and inner walls
        ours = _rect(-10, 10, -20, 0)                           # a solid one
        r = S.deviation(ours, ref)
        self.assertGreater(r["missing"], 0.2)   # (the reference's inner wall: nothing of ours near it)
        self.assertEqual(r["extra"], 0.0)       # (all of ours lies on the reference's outer wall)

    def test_empty_sides(self):
        self.assertEqual(S.deviation([], _rect(0, 1, 0, 1))["missing"], 1.0)
        self.assertEqual(S.deviation(_rect(0, 1, 0, 1), [])["extra"], 1.0)


class Compare(unittest.TestCase):
    def test_aligned_on_the_rearmost_section(self):
        # the reference sits 5 mm higher and 3 mm to the side in its own units: alignment takes both out
        ours = _cut([(3.0, _rect(-8, 8, -18, 0)), (40.0, _rect(-12, 12, -30, 0))])
        ref = _cut([(3.0, _rect(-5, 11, -13, 5)), (40.0, _rect(-9, 15, -25, 5))])
        rows, fo, fr = S.compare(ours, ref)
        self.assertEqual(fo, (0.0, 0))
        self.assertEqual(fr, (3.0, 5))
        self.assertEqual([r["d"] for r in rows], [3.0, 40.0])
        self.assertTrue(all(r["p90"] == 0.0 for r in rows))

    def test_frame_of_skips_empty_rear_sections(self):
        self.assertEqual(S.frame_of([{"d": 1.0, "segs": _rect(-2, 2, -4, 0)}, {"d": 9.0, "segs": []}]), (0.0, 0))
        self.assertIsNone(S.frame_of([{"d": 1.0, "segs": []}]))


class Scale(unittest.TestCase):
    def test_mm_per_stud_from_the_manifest(self):
        self.assertEqual(S.manifest_mm_per_stud({"mm_per_stud": 300}), 300.0)
        self.assertEqual(S.manifest_mm_per_stud({"facts": {"cad": [{"part": "A"}, {"mm_per_stud": 280.0}]}}), 280.0)
        self.assertEqual(S.manifest_mm_per_stud({"facts": {}}), 0.0)


class Sheets(unittest.TestCase):
    def test_draws_one_panel_per_station(self):
        ours = _cut([(d, _rect(-10, 10, -20, 0)) for d in (1, 2, 3, 4, 5, 6, 7)],
                    along=[{"x": 0.0, "segs": _rect(0, 60, -20, 0)}])
        rows, fo, fr = S.compare(ours, ours)
        with tempfile.TemporaryDirectory() as tmp:
            from PIL import Image

            p = S.draw_cross(ours, ours, fo, fr, rows, os.path.join(tmp, "x.png"), cols=5)
            with Image.open(p) as im:
                w, h = im.size
            self.assertEqual(w % 5, 0)              # (5 panels across, 2 rows for 7 stations)
            self.assertGreater(h, 2 * 20 * S.PX)    # (each panel at least the 20 mm section tall)
            q = S.draw_along(ours, ours, fo, fr, os.path.join(tmp, "a.png"), length=60.0)
            self.assertTrue(os.path.isfile(q))


if __name__ == "__main__":
    unittest.main()
