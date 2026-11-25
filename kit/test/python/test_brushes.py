"""rbx_brushes — sculpt brushes on a meshed surface (headless): pinch draws a sharp line, flatten presses a plane,
inflate pushes along the normal, crease grooves; a mirrored canvas acts on both sides in ONE pass."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_brushes as B  # noqa: E402


def dome():
    xs = np.linspace(-10, 10, 41)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    Z = np.sqrt(np.maximum(30 ** 2 - X ** 2 - Y ** 2, 0)) - 30
    v = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
    idx = np.arange(len(v)).reshape(41, 41)
    faces = [[idx[i, j], idx[i + 1, j], idx[i + 1, j + 1], idx[i, j + 1]] for i in range(40) for j in range(40)]
    return v, faces


class Brushes(unittest.TestCase):
    def test_pinch_draws_the_surface_to_a_line(self):
        v, f = dome()
        nv = B.apply(v, f, {"kind": "pinch", "path": [[0, -8, 0], [0, 8, 0]], "radius": 3, "strength": 0.8})
        near = (np.abs(v[:, 0]) < 3) & (np.abs(v[:, 0]) > 0.4) & (np.abs(v[:, 1]) < 6)
        self.assertLess(np.abs(nv[near, 0]).mean(), np.abs(v[near, 0]).mean() * 0.8)
        self.assertTrue(np.allclose(nv[near, 1], v[near, 1], atol=0.05))   # (across the path only: no bunching)

    def test_flatten_presses_a_plane_and_inflate_pushes_out(self):
        v, f = dome()
        c = np.hypot(v[:, 0], v[:, 1]) < 3
        flat = B.apply(v, f, {"kind": "flatten", "path": [[0, 0, 0]], "radius": 8, "strength": 1.0})
        self.assertLess(np.ptp(flat[c, 2]), np.ptp(v[c, 2]) * 0.5)
        up = B.apply(v, f, {"kind": "inflate", "path": [[0, 0, 0]], "radius": 5, "strength": 1.0})
        self.assertGreater(float((up[c, 2] - v[c, 2]).mean()), 0.3)
        far = np.hypot(v[:, 0], v[:, 1]) > 6
        self.assertTrue(np.allclose(up[far], v[far]))                       # (nothing past the radius moves)

    def test_a_mirrored_brush_acts_on_both_sides_once(self):
        v, f = dome()
        one = B.apply(v, f, {"kind": "inflate", "path": [[5, 0, 0]], "radius": 3, "strength": 1.0}, mirror_axis=0)
        left, right = np.hypot(v[:, 0] + 5, v[:, 1]) < 1, np.hypot(v[:, 0] - 5, v[:, 1]) < 1
        self.assertAlmostEqual(float((one[left] - v[left])[:, 2].mean()), float((one[right] - v[right])[:, 2].mean()),
                               places=3)
        mid = B.apply(v, f, {"kind": "inflate", "path": [[0, 0, 0]], "radius": 3, "strength": 1.0}, mirror_axis=0)
        alone = B.apply(v, f, {"kind": "inflate", "path": [[0, 0, 0]], "radius": 3, "strength": 1.0})
        self.assertTrue(np.allclose(mid, alone))                            # (a midline path: not twice)
        with self.assertRaises(ValueError):
            B.apply(v, f, {"kind": "smudge", "path": [[0, 0, 0]], "radius": 3, "strength": 1})


if __name__ == "__main__":
    unittest.main()
