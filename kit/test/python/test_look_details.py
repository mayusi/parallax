"""kit look details (kit/tools/look_details.py) — the build's render laid onto the reference by its silhouette: a
scaled, shifted, mirrored copy is found again (overlap ~1); the edge measure tells a crisp square edge from a soft
rounded one; a detail compared with itself is alike 1.0 and edges x1.0 (pure, no Blender)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import look_details as L  # noqa: E402


def shape(h=300, w=500, off=(60, 40), k=1.0):
    import cv2  # noqa: PLC0415

    m = np.zeros((h, w), np.uint8)
    ox, oy = off
    pts = (np.array([[0, 0], [300, 0], [300, 60], [120, 60], [120, 200], [0, 200]]) * k + [ox, oy]).astype(np.int32)
    cv2.fillPoly(m, [pts], 1)
    return m.astype(bool)


class Register(unittest.TestCase):
    def test_a_scaled_shifted_mirrored_render_lands_on_the_reference(self):
        ref = shape()
        ren = shape(h=200, w=260, off=(20, 10), k=0.6)[:, ::-1]      # (smaller, elsewhere, mirrored)
        reg = L.register(ref, ren)
        self.assertTrue(reg["flip"])
        self.assertAlmostEqual(reg["s"], 1 / 0.6, delta=0.03)
        self.assertGreater(reg["iou"], 0.95)

    def test_object_mask_takes_the_object_off_its_backdrop(self):
        rgb = np.zeros((300, 500, 3), np.uint8)
        rgb[shape()] = (150, 40, 60)
        m, bg = L.object_mask(rgb)
        self.assertEqual(int(m.sum()), int(shape().sum()))
        self.assertEqual([int(v) for v in bg], [0, 0, 0])


class Measures(unittest.TestCase):
    def test_a_square_edge_is_sharper_than_a_rounded_one(self):
        import cv2  # noqa: PLC0415

        sq = np.full((120, 120), 40, np.uint8)
        sq[30:90, 30:90] = 220
        soft = cv2.GaussianBlur(sq, (0, 0), 3.0)
        self.assertGreater(L.edge_share(sq), 1.3 * L.edge_share(soft))

    def test_a_detail_against_itself(self):
        rgb = np.random.default_rng(0).integers(0, 255, (200, 200, 3), dtype=np.uint8)
        it = L.compare(rgb, rgb.copy(), [{"label": "gem", "box": [50, 50, 120, 120]}])[0]
        self.assertAlmostEqual(it["alike"], 1.0, places=3)
        self.assertAlmostEqual(it["edges"], 1.0, places=2)
        self.assertEqual(it["flag"], "")


if __name__ == "__main__":
    unittest.main()
