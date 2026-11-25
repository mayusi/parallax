"""Sockets and mates (kit/blender/rbx_mate.py; his D-R04; the 3D methods audit, stage L)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_mate as M  # noqa: E402

UP, DOWN = (0.0, 1.0, 0.0), (0.0, -1.0, 0.0)


def s(pos, axis, size=None):
    return {"pos": pos, "axis": M.unit(axis), "size": size}


class Socket(unittest.TestCase):
    def test_a_socket_on_its_part_is_fine_and_one_left_behind_is_said(self):
        self.assertIsNone(M.on_problem("Well", "Body", 0.004, 2.0))
        self.assertIn('0.3 studs off "Body"', M.on_problem("Well", "Body", 0.3, 2.0))
        self.assertIn("no longer in the model", M.on_problem("Well", "Body", None, 2.0))

    def test_a_large_part_allows_a_little_more(self):
        self.assertIsNone(M.on_problem("Door", "Wall", 0.15, 20.0))
        self.assertIsNotNone(M.on_problem("Door", "Wall", 0.15, 2.0))


class Mate(unittest.TestCase):
    def test_two_sockets_seated_face_to_face_hold(self):
        self.assertIsNone(M.mate_problem("Peg in Well", s((0, 1, 0), DOWN, 0.46), s((0, 1, 0), UP, 0.5),
                                         fit=(0.01, 0.05)))

    def test_apart_or_turned_is_said(self):
        self.assertIn("0.3 studs apart", M.mate_problem("m", s((0, 1.3, 0), DOWN), s((0, 1, 0), UP)))
        self.assertIn("do not face each other", M.mate_problem("m", s((0, 1, 0), UP), s((0, 1, 0), UP)))

    def test_a_slide_may_be_anywhere_along_the_line_but_not_off_it(self):
        self.assertIsNone(M.mate_problem("m", s((0, 1.7, 0), DOWN), s((0, 1, 0), UP), "slide"))
        self.assertIsNone(M.mate_problem("m", s((0, 0.2, 0), UP), s((0, 1, 0), UP), "slide"))
        self.assertIn("0.2 studs off the socket's line",
                      M.mate_problem("m", s((0.2, 1.7, 0), DOWN), s((0, 1, 0), UP), "slide"))
        self.assertIn("not one line", M.mate_problem("m", s((0, 1.7, 0), (1, 0, 0)), s((0, 1, 0), UP), "slide"))

    def test_the_fit_is_held_both_ways(self):
        well = s((0, 1, 0), UP, 0.5)
        self.assertIn("does not go into", M.mate_problem("m", s((0, 1, 0), DOWN, 0.6), well, fit=(0.01, 0.05)))
        self.assertIn("under the 0.01 asked", M.mate_problem("m", s((0, 1, 0), DOWN, 0.49), well, fit=(0.01, 0.05)))
        self.assertIn("rattles", M.mate_problem("m", s((0, 1, 0), DOWN, 0.2), well, fit=(0.01, 0.05)))
        self.assertIn("needs a size on both", M.mate_problem("m", s((0, 1, 0), DOWN), well, fit=(0.01, 0.05)))

    def test_an_unknown_way_of_meeting_is_refused(self):
        with self.assertRaises(ValueError):
            M.mate_problem("m", s((0, 1, 0), DOWN), s((0, 1, 0), UP), "glued")


if __name__ == "__main__":
    unittest.main()
