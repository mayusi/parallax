"""kit/tools/look.py: kit look closeup frames the parts a word names, from the build manifest's part boxes."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import look as L  # noqa: E402

BOUNDS = {"CanisterL": [[-1, 0, 0], [-0.8, 0.2, 2]], "CanisterR": [[0.8, 0, 0], [1, 0.2, 2]],
          "BladeL": [[-1, 0, -3], [-0.9, 0.1, -1]]}


class Frame(unittest.TestCase):
    def test_a_word_frames_every_part_it_names(self):
        centre, size, hits = L.frame(BOUNDS, ["Canister"])
        self.assertEqual(sorted(hits), ["CanisterL", "CanisterR"])
        self.assertAlmostEqual(centre[0], 0.0)
        self.assertAlmostEqual(size, 2.0)

    def test_one_part_alone_and_no_match(self):
        centre, size, hits = L.frame(BOUNDS, ["bladel"])
        self.assertEqual(hits, ["BladeL"])
        self.assertAlmostEqual(size, 2.0)
        self.assertIsNone(L.frame(BOUNDS, ["Reel"]))


class Albedo(unittest.TestCase):
    def test_the_30_240_rule_on_non_metal_texels(self):
        import tempfile

        import numpy as np
        from PIL import Image

        with tempfile.TemporaryDirectory() as d:
            c = np.zeros((10, 10, 3), np.uint8)
            c[:5] = 120             # (a mid albedo)
            c[5:7] = 15             # (too dark for a non-metal)
            c[7:] = 200             # (a bright metal: not judged)
            m = np.zeros((10, 10), np.uint8)
            m[7:] = 255
            Image.fromarray(c).save(os.path.join(d, "c.png"))
            Image.fromarray(m).save(os.path.join(d, "m.png"))
            dark, bright, _p5, _p95 = L.albedo_check(os.path.join(d, "c.png"), os.path.join(d, "m.png"))
            self.assertAlmostEqual(dark, 20 / 70, places=3)
            self.assertEqual(bright, 0.0)


if __name__ == "__main__":
    unittest.main()
