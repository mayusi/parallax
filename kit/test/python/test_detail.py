"""kit refs detail (kit/refs/detail.py) — a SMALL part traced at sub-pixel precision: a 6 px disc (a screw head in a
side view) traced from a 4x enlargement comes back rounder and nearer its true area than the whole-picture trace's
native pixels give it (Lanczos here: no GPU in a test)."""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "refs"))
import detail as D  # noqa: E402


def disc(r=6.0, size=24, c=(11.7, 12.3)):
    yy, xx = np.mgrid[0:size * 8, 0:size * 8] / 8.0   # (anti-aliased: 8x8 supersampling)
    inside = ((xx - c[0]) ** 2 + (yy - c[1]) ** 2) < r * r
    a = inside.reshape(size, 8, size, 8).mean(axis=(1, 3))
    im = (255 * (1 - a))[..., None].repeat(3, axis=2).astype(np.uint8)   # (a dark disc on white)
    return im, math.pi * r * r


def poly_area(p):
    p = np.asarray(p)
    return 0.5 * abs(np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1)))


class Detail(unittest.TestCase):
    def test_a_small_disc_traced_rounder_and_truer(self):
        import cv2  # noqa: PLC0415

        im, true = disc()
        native = (im.mean(axis=2) < 128).astype(np.uint8)
        c, _ = cv2.findContours(native, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        native_area = cv2.contourArea(max(c, key=cv2.contourArea))
        big, how = D.enlarge(im, 4, model=False)
        self.assertEqual(how, "Lanczos")
        pieces = D.trace(D.part_mask(big, ("dark", 128), 4), 4, sigma=0.4, eps=0.15)
        self.assertEqual(len(pieces), 1)
        got = poly_area(pieces[0]["outline"])
        self.assertLess(abs(got - true) / true, 0.05, (got, true))
        self.assertLess(abs(got - true), abs(native_area - true))           # (truer than the native pixels)
        self.assertGreater(len(pieces[0]["outline"]), 20)                   # (a round outline, not a blocky one)
        cx = np.mean([p[0] for p in pieces[0]["outline"]])
        self.assertAlmostEqual(cx, 11.7, delta=0.25)                        # (centred to a quarter pixel)

    def test_a_ring_keeps_its_hole(self):
        yy, xx = np.mgrid[0:40, 0:40]
        d = np.hypot(xx - 20, yy - 20)
        im = np.full((40, 40, 3), 255, np.uint8)
        im[(d < 12) & (d > 6)] = (20, 20, 20)
        big, _ = D.enlarge(im, 4, model=False)
        pieces = D.trace(D.part_mask(big, ("dark", 128), 4), 4, sigma=0.3, eps=0.2)
        self.assertEqual(len(pieces[0]["holes"]), 1)


if __name__ == "__main__":
    unittest.main()
