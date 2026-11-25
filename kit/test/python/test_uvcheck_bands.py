"""rbx_uvcheck.overlap counted in bands of rows (card keak; his limitations review V3: "upgrade the 4096 overlap
detector to tiled chunks"): the same numbers as the whole grid counted at once - the share, the texels, the faces
and the worst places - at a fraction of the memory."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_uvcheck as U  # noqa: E402


def random_faces(seed, n_tris=300):
    rng = np.random.default_rng(seed)
    centres = rng.random((n_tris, 2)) * 0.9 + 0.05
    uv = (centres[:, None, :] + (rng.random((n_tris, 3, 2)) - 0.5) * 0.12).reshape(-1, 2)
    start = np.arange(n_tris) * 3
    total = np.full(n_tris, 3)
    tri = np.arange(n_tris * 3).reshape(-1, 3)
    return uv.ravel(), start, total, tri, np.arange(n_tris)


class Bands(unittest.TestCase):
    def test_the_same_numbers_as_the_whole_grid(self):
        for seed in range(6):
            args = random_faces(seed)
            for res in (256, 1024):
                whole = U.overlap(*args, res=res, band=res * 4)
                for band in (7, 64, 256):
                    got = U.overlap(*args, res=res, band=band)
                    self.assertEqual(got["texels"], whole["texels"], (seed, res, band))
                    self.assertEqual(got["polys"], whole["polys"])
                    self.assertAlmostEqual(got["share"], whole["share"], places=12)
                    self.assertEqual(got["at"], whole["at"])
                    self.assertTrue(np.array_equal(got["mask"], whole["mask"]))
            self.assertGreater(whole["texels"], 0)   # (the fixture does overlap: the comparison means something)

    def test_nothing_twice_is_nothing(self):
        uv = np.array([[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.6, 0.6], [0.9, 0.6], [0.9, 0.9]]).ravel()
        got = U.overlap(uv, np.array([0, 3]), np.array([3, 3]), np.arange(6).reshape(2, 3), np.arange(2), res=512, band=32)
        self.assertEqual((got["texels"], got["polys"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
