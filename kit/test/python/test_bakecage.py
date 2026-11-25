"""A bake cage the author sets (kit/blender/rbx_bakecage.py; the owner's method lists: bake cages; the 3D methods
audit, S3b)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_bakecage as C  # noqa: E402


class Need(unittest.TestCase):
    def test_each_parts_need_is_its_own_highs_distance(self):
        d = [0.1] * 99 + [5.0] + [1.0] * 50
        part = [0] * 100 + [1] * 50
        got = C.need(d, part, 3)
        self.assertEqual(got[1], 1.0)
        self.assertEqual(got[0], 5.0)                 # (the 99th of 100 is the last: one proud point counts here)
        self.assertEqual(got[2], 0.0)                 # no point of the high lies nearest this part
        self.assertEqual(C.need([0.1] * 199 + [5.0], [0] * 200, 1)[0], 0.1)   # one stray in 200 does not


class Held(unittest.TestCase):
    def test_a_cage_under_its_need_is_said_with_the_depth_it_needs(self):
        self.assertIsNone(C.problem("Boss", 1.5, 1.2))
        self.assertIsNone(C.problem("Boss", 1.2, 1.2))
        said = C.problem("Boss", 0.3, 1.23)
        self.assertIn("Boss: its cage is 0.3 mm and its high stands 1.23 mm off", said)
        self.assertIn("at least 1.3 mm", said)

    def test_a_cage_far_deeper_than_its_need_is_said_and_a_millimetre_never_is(self):
        self.assertIsNone(C.deep("Boss", 1.0, 0.01))
        self.assertIsNone(C.deep("Boss", 5.0, 1.0))
        self.assertIn("can land on the part beside it", C.deep("Boss", 7.0, 1.0))
        self.assertIn("its high needs 0.01", C.deep("Boss", 6.5, 0.0))


class Misses(unittest.TestCase):
    def test_rays_that_found_nothing_are_said_with_where(self):
        self.assertIsNone(C.miss_problem("main", 0.004, ["LugA"]))
        said = C.miss_problem("main", 0.024, ["LugA", "LugB"])
        self.assertIn("main: 2.4% of its map's texels found no high under their cage (most on LugA, LugB)", said)
        self.assertIn("a.bake_cage", said)


class Cage(unittest.TestCase):
    def test_a_vertex_between_two_parts_takes_the_deeper_cage(self):
        got = C.offsets([[0], [0, 1], [1], []], [0.5, 2.0])
        self.assertEqual(got.tolist(), [0.5, 2.0, 2.0, 0.0])


if __name__ == "__main__":
    unittest.main()
