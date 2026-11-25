"""A sewn seam as a stamp (kit/blender/rbx_stamps.py, kind "stitches"; the owner's method lists: clothing folds and
seams; the 3D methods audit, stage H)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_stamps as S  # noqa: E402


class Stitches(unittest.TestCase):
    def test_a_row_of_thread_dashes_along_the_long_side(self):
        h = S.height("stitches", size_mm=(40.0, 4.0), px_per_mm=8.0, pitch_mm=4.0, thread_mm=1.0)
        self.assertEqual(h.shape, (32, 320))
        mid = h[16]                                               # along the seam's middle
        up = mid > 0.25                                           # where a thread lies
        starts = int((up[1:] & ~up[:-1]).sum())
        self.assertIn(starts, (9, 10))                            # ten stitches in 40 mm at 4 mm (the ends fade)
        self.assertAlmostEqual(float(h.max()), 0.5, delta=0.08)   # a thread half its width proud
        self.assertLess(float(h.min()), -0.1)                     # ... and a dip where the needle went in
        self.assertLess(abs(float(h[2].max())), 0.05)             # nothing beside the thread

    def test_it_runs_along_whichever_side_is_long_and_reads_its_own_options_only(self):
        tall = S.height("stitches", size_mm=(4.0, 40.0), px_per_mm=8.0, pitch_mm=4.0, thread_mm=1.0)
        self.assertEqual(tall.shape, (320, 32))
        self.assertGreater(float(tall[:, 16].max()), 0.4)
        with self.assertRaises(ValueError):
            S.check("stitches", count=3)
        with self.assertRaises(ValueError):
            S.check("stitches", pitch_mm=0)
        with self.assertRaises(ValueError):                           # a stitch and its gap: two threads at least
            S.check("stitches", pitch_mm=1.0, thread_mm=1.0)
        wide = S.height("stitches", size_mm=(40.0, 1.0), px_per_mm=8.0, thread_mm=3.0)
        self.assertLessEqual(float(wide.max()), 0.55)                 # the thread is held to the stamp's width
        self.assertEqual(S.finest_mm("stitches", (40.0, 4.0), thread_mm=0.8), 0.8)


if __name__ == "__main__":
    unittest.main()
