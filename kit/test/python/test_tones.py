"""tones.py — a material's colours measured from a photo's object pixels (linear light): the base, the cavity and edge
tones, and which grime tone fits (a warm pale surface stains, a dark one shows dust)."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
import tones as T  # noqa: E402


class Tones(unittest.TestCase):
    def test_an_aged_bone_photo(self):
        rng = np.random.default_rng(0)
        ivory = np.array([0.86, 0.80, 0.66])               # (sRGB: the pale body)
        recess = np.array([0.45, 0.33, 0.18])              # (sRGB: ochre-brown in the cavities)
        img = np.tile(ivory, (60, 60, 1)) + rng.normal(0, 0.02, (60, 60, 3))
        img[:12, :] = recess
        alpha = np.ones((60, 60))
        alpha[:, :5] = 0                                  # (background: masked out)
        t = T.tones(np.clip(img, 0, 1), alpha)
        self.assertGreater(t["base"][0], 0.55)            # (linear: the ivory's red channel)
        self.assertLess(t["cavity"][0], 0.25)
        self.assertGreater(t["cavity"][0], t["cavity"][2] * 1.6)
        self.assertEqual(t["grime_tone"], "stain")
        self.assertEqual(t["pixels"], 60 * 55)

    def test_an_albedo_npz_is_read_with_its_mask(self):
        import json
        import subprocess
        import tempfile

        alb = np.tile(np.array([0.87, 0.76, 0.58], dtype=np.float16), (40, 40, 1))
        mask = np.zeros((40, 40), dtype=bool)
        mask[5:35, 5:35] = True
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.albedo.npz")
            np.savez(p, albedo=alb, mask=mask, meta="{}")
            out = subprocess.run([sys.executable, os.path.join(os.path.dirname(T.__file__), "tones.py"), p],
                                 capture_output=True, text=True, timeout=60).stdout
        t = json.loads(out.strip().splitlines()[-1])["tones"]
        self.assertEqual(t["pixels"], 900)
        self.assertAlmostEqual(t["base"][0], 0.73, delta=0.02)   # (0.87 sRGB, linear)

    def test_a_dark_finish_shows_dust(self):
        img = np.full((40, 40, 3), 0.18)
        self.assertEqual(T.tones(img)["grime_tone"], "dust")
        with self.assertRaises(ValueError):
            T.tones(img, np.zeros((40, 40)))


if __name__ == "__main__":
    unittest.main()
