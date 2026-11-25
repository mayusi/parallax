"""kit/gen/relief.py: an ornament's relief from its picture's normals and depth — a dome's normals integrate back
into a dome, zero outside its outline, and "toward the viewer" is taken from the depth map, never assumed."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gen"))
import relief as R  # noqa: E402


def dome(n=48, r=20.0):
    """a spherical cap seen from the front: camera-space normals (z into the picture), depth, its mask"""
    y, x = np.mgrid[0:n, 0:n].astype(float)
    cx = cy = (n - 1) / 2
    dx, dy = x - cx, y - cy
    rr = dx ** 2 + dy ** 2
    mask = rr < r ** 2
    z = np.sqrt(np.clip(r ** 2 - rr, 0, None))  # height toward the viewer
    normal = np.dstack([dx, dy, -np.maximum(z, 1e-3)])  # facing the camera: n_z < 0
    normal /= np.linalg.norm(normal, axis=2, keepdims=True)
    depth = 100.0 - z  # nearer = smaller depth
    return normal, depth, mask, z


class TestRelief(unittest.TestCase):
    def test_a_domes_normals_integrate_back_into_a_dome(self):
        normal, depth, mask, z = dome()
        h = R.relief_height(normal, depth, mask, detail=0)
        self.assertEqual(float(h[~mask].max()), 0.0)  # flat outside the outline
        self.assertGreater(np.corrcoef(h[mask], z[mask])[0, 1], 0.9)  # the same shape
        cy = cx = h.shape[0] // 2
        self.assertGreater(h[cy, cx], 0.9)  # highest in the middle

    def test_toward_the_viewer_comes_from_the_depth_map(self):
        normal, depth, mask, z = dome()
        flipped = normal * np.array([-1.0, -1.0, 1.0])  # a different handedness of the slopes
        h = R.relief_height(flipped, depth, mask, detail=0)
        self.assertGreater(np.corrcoef(h[mask], z[mask])[0, 1], 0.9)  # still a dome, not a dent

    def test_the_detail_boost_keeps_the_range_and_the_outline(self):
        normal, depth, mask, _ = dome()
        h = R.relief_height(normal, depth, mask, detail=1.5)
        self.assertAlmostEqual(float(h.max()), 1.0, places=6)
        self.assertEqual(float(h[~mask].max()), 0.0)

    def test_compression_shrinks_steep_slopes_more_than_gentle_ones(self):
        gx = np.array([0.1, 10.0])
        cx, _ = R.compress(gx, np.zeros(2))
        self.assertGreater(cx[0] / gx[0], cx[1] / gx[1])

    def test_shade_is_a_picture_in_0_1(self):
        normal, depth, mask, _ = dome()
        s = R.shade(R.relief_height(normal, depth, mask))
        self.assertTrue(0.0 <= s.min() and s.max() <= 1.0)


if __name__ == "__main__":
    unittest.main()
