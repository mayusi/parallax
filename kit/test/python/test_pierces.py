"""Does a named way pass THROUGH an open loop? (kit/blender/rbx_through.pierces; his D-R12, the rest: a repair
steered by the opening's name)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_through as T  # noqa: E402

MOUTH = [(-0.5, 1, -0.5), (0.5, 1, -0.5), (0.5, 1, 0.5), (-0.5, 1, 0.5)]        # a square hole in the plane y = 1


class Pierces(unittest.TestCase):
    def test_a_way_down_through_the_hole_passes_through_it(self):
        self.assertTrue(T.pierces((0, 1.4, 0), (0, 0.4, 0), MOUTH))
        self.assertTrue(T.pierces((0.3, 0.4, 0.2), (0.3, 1.4, 0.2), MOUTH))     # the other way, off its middle

    def test_a_way_that_stops_short_of_the_hole_does_not(self):
        self.assertFalse(T.pierces((0, 1.4, 0), (0, 1.1, 0), MOUTH))
        tear = [(0, 0, -0.5), (0.5, 0, -0.5), (0.5, 0, 0.5), (0, 0, 0.5)]       # a hole in the floor, y = 0
        self.assertFalse(T.pierces((0, 1.4, 0), (0, 0.4, 0), tear))              # the way ends above the floor

    def test_a_way_beside_the_hole_or_along_its_plane_does_not(self):
        self.assertFalse(T.pierces((3, 1.4, 0), (3, 0.4, 0), MOUTH))
        self.assertFalse(T.pierces((-2, 1, 0), (2, 1, 0), MOUTH))

    def test_a_way_through_the_wall_beside_a_long_slot_does_not(self):
        slot = [(-2, 1, -0.1), (2, 1, -0.1), (2, 1, 0.1), (-2, 1, 0.1)]          # 4 long, 0.2 wide
        self.assertTrue(T.pierces((1.5, 1.4, 0), (1.5, 0.4, 0), slot))           # down through the slot
        self.assertFalse(T.pierces((0, 1.4, 1.5), (0, 0.4, 1.5), slot))          # 1.5 to one side: solid wall

    def test_the_empty_corner_of_an_l_shaped_tear_is_outside_it(self):
        ell = [(0, 1, 0), (2, 1, 0), (2, 1, 1), (1, 1, 1), (1, 1, 2), (0, 1, 2)]
        self.assertTrue(T.pierces((0.5, 1.4, 0.5), (0.5, 0.4, 0.5), ell))
        self.assertFalse(T.pierces((1.6, 1.4, 1.6), (1.6, 0.4, 1.6), ell))

    def test_less_than_a_loop_is_nothing(self):
        self.assertFalse(T.pierces((0, 1.4, 0), (0, 0.4, 0), MOUTH[:2]))


def ring(radius, z, count=16):
    import math

    return [(radius * math.cos(2 * math.pi * i / count), radius * math.sin(2 * math.pi * i / count), z)
            for i in range(count)]


class Kept(unittest.TestCase):
    BORE = ("Bore", (0, 0, -3), (0, 0, 3))

    def test_a_tubes_open_mouth_is_kept(self):
        self.assertEqual(T.kept([ring(0.3, 1.0)], [self.BORE]), {0: ["Bore"]})

    def test_a_thick_tubes_missing_end_ring_is_not(self):
        # the missing face is the RING between the outer loop and the bore's own: the way runs through the bore
        self.assertEqual(T.kept([ring(0.3, 1.0), ring(0.15, 1.0)], [self.BORE]), {})

    def test_two_mouths_in_two_planes_are_both_kept(self):
        self.assertEqual(T.kept([ring(0.3, 1.0), ring(0.3, -1.0)], [self.BORE]), {0: ["Bore"], 1: ["Bore"]})

    def test_a_tear_off_the_way_is_not_kept_and_a_broken_ring_is_skipped(self):
        tear = [(2, 0, 0), (2.2, 0, 0), (2.2, 0.2, 0), (2, 0.2, 0)]
        self.assertEqual(T.kept([tear, [], ring(0.3, 1.0)], [self.BORE]), {2: ["Bore"]})


if __name__ == "__main__":
    unittest.main()
