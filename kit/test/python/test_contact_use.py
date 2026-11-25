"""a.contact by PART and the DRIP kind (AAA-7, wear storytelling): rbx_wear.drip and box_from_points in numpy, and the
fixture kit/selftest/blender/build_contact_use.py baked in Blender — streaks under a fitting cover a thin share of the
map (broken runs, never a painted band), the handle's box comes from its part."""

import json
import os
import subprocess
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
import cad_check  # noqa: E402
import rbx_wear  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()


class DripTone(unittest.TestCase):
    def test_streak_darkens_dulls_and_demetals(self):
        col = np.full((2, 2, 3), 0.8, np.float32)
        rough = np.full((2, 2, 3), 0.3, np.float32)
        metal = np.ones((2, 2, 3), np.float32)
        mask = np.array([[[0.0], [1.0]], [[0.5], [0.0]]], np.float32)
        c2, r2, m2 = rbx_wear.drip(col, rough, metal, mask)
        self.assertTrue(np.allclose(c2[0, 0], 0.8) and np.allclose(r2[0, 0], 0.3) and np.allclose(m2[0, 0], 1.0))
        self.assertLess(c2[0, 1].mean(), 0.5)                       # (a full streak: well toward the dark drip tone)
        self.assertGreater(c2[0, 1, 0], c2[0, 1, 2])                # (...and brown: red over blue)
        self.assertAlmostEqual(float(r2[0, 1, 0]), 0.3 + rbx_wear.DRIP_DULL, places=5)
        self.assertAlmostEqual(float(m2[0, 1, 0]), 1 - rbx_wear.DRIP_DEMETAL, places=5)
        self.assertTrue(c2[0, 1].mean() < c2[1, 0].mean() < 0.8)    # (half a streak: half way)


class BoxFromPoints(unittest.TestCase):
    def test_box_round_points_with_pad(self):
        at, size = rbx_wear.box_from_points([[-1, 0, 2], [1, 0.5, 3], [0, 1, 2.5]], pad=0.1)
        self.assertEqual(at, (0.0, 0.5, 2.5))
        self.assertTrue(np.allclose(size, (2.2, 1.2, 1.2)))

    def test_flat_part_keeps_a_size(self):
        _at, size = rbx_wear.box_from_points([[0, 0, 0], [1, 0, 1]])
        self.assertGreater(min(size), 0)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class ContactUseBake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = os.path.join(REPO, "kit", "selftest", "blender", "build_contact_use.py")
        manifest = os.path.join(REPO, "build", "models", "_selftest_contact_use.manifest.json")
        if os.path.isfile(manifest):
            os.remove(manifest)   # (a manifest left by an earlier green run must never pass a broken build)
        cls.run_ = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", "--no-preview"], cwd=REPO,
                                  capture_output=True, text=True, timeout=900)
        assert cls.run_.returncode == 0 and os.path.isfile(manifest), (cls.run_.stderr or cls.run_.stdout)[-800:]
        with open(manifest, encoding="utf-8") as fh:
            cls.facts = json.load(fh)["facts"]

    def test_drip_and_hand_cover_their_share(self):
        c = self.facts["contacts"]["_selftest_contact_use"]
        self.assertTrue(0.003 < c["drip"] < 0.12, c)   # (thin broken runs under one small fitting, not a band)
        self.assertTrue(0.01 < c["hand"] < 0.3, c)     # (the handle bar's box, from its part)


if __name__ == "__main__":
    unittest.main()
