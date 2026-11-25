"""Which poses of a timeline are checked (kit/blender/rbx_travel.walk; his D-R05, the rest: an action cycle's
collision check picks its poses by how far the parts move, never by a count of frames)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_travel as T  # noqa: E402


def gone(moves, picked, g):
    """the furthest `g` went between two checked poses"""
    worst, acc, at = 0.0, 0.0, set(picked)
    for i, m in enumerate(moves, 1):
        acc += m.get(g, 0.0)
        if i in at:
            worst, acc = max(worst, acc), 0.0
    return worst


class Walk(unittest.TestCase):
    def test_no_part_goes_further_than_its_step_between_two_checked_poses(self):
        moves = [{"a": 0.03, "b": 0.001}] * 40
        picked, scale, coarse = T.walk(moves, set(), {"a": 0.1, "b": 0.1})
        self.assertFalse(coarse)
        self.assertEqual(scale, 1.0)
        self.assertLessEqual(gone(moves, picked, "a"), 0.1 + 1e-9)
        self.assertEqual((picked[0], picked[-1]), (0, 40))
        self.assertLess(len(picked), 20)                      # (three moves of 0.03 fit one step: not every pose)

    def test_the_thin_part_sets_the_pace(self):
        moves = [{"thick": 0.05, "thin": 0.05}] * 20
        wide, _, _ = T.walk(moves, set(), {"thick": 0.5, "thin": 0.5})
        fine, _, _ = T.walk(moves, set(), {"thick": 0.5, "thin": 0.05})
        self.assertGreater(len(fine), len(wide))
        self.assertLessEqual(gone(moves, fine, "thin"), 0.05 + 1e-9)

    def test_a_held_stretch_is_not_checked_again_and_again(self):
        moves = [{"a": 0.2}] + [{"a": 0.0}] * 30 + [{"a": 0.2}]
        picked, _, _ = T.walk(moves, set(), {"a": 0.1})
        self.assertLessEqual(len(picked), 4)

    def test_the_poses_always_asked_for_are_kept(self):
        moves = [{"a": 0.0}] * 10
        picked, _, _ = T.walk(moves, {4, 8}, {"a": 0.1})
        self.assertEqual(picked, [0, 4, 8, 10])

    def test_more_poses_than_a_build_checks_is_said_as_coarse(self):
        moves = [{"a": 1.0}] * 2000
        picked, scale, coarse = T.walk(moves, set(), {"a": 0.5}, most=100)
        self.assertTrue(coarse)
        self.assertGreater(scale, 1.0)
        self.assertLessEqual(len(picked), 100)
        self.assertLessEqual(gone(moves, picked, "a"), 0.5 * scale + 1.0 + 1e-9)


if __name__ == "__main__":
    unittest.main()
