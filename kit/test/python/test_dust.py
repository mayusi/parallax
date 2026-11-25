"""rbx_wear.dust_mask (a.material(dust=)): dust on the faces that look up, none on walls or undersides, more in
recesses, wiped off edges — the world-space-normal placement AAA texturing tools use."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
import rbx_wear as W  # noqa: E402


def m(up, concave=0.0, convex=0.0, noise=0.5):
    f = lambda v: np.full((1, 1, 1), v, np.float32)  # noqa: E731
    return float(W.dust_mask(f(up), f(concave), f(convex), f(noise))[0, 0, 0])


class Dust(unittest.TestCase):
    def test_up_faces_take_dust_walls_and_undersides_none(self):
        self.assertGreater(m(1.0), 0.4)
        self.assertEqual(m(0.0), 0.0)        # (a wall)
        self.assertEqual(m(0.5), 0.0)        # (60 deg off level: too steep to hold it)

    def test_recesses_hold_more_edges_are_wiped(self):
        self.assertGreater(m(1.0, concave=1.0), m(1.0))
        self.assertLess(m(1.0, convex=1.0), 0.5 * m(1.0))


if __name__ == "__main__":
    unittest.main()
