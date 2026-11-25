"""Smooth curves from traced outlines (kit/blender/curvefit.py, used by kit trace): an ellipse traces back within 1 px
of the true curve with FEWER anchors than the old pixel polygon had points and a better fit; sharp corners stay sharp
and in place; a tight bend is not mistaken for a corner; old traces without curves keep their polygon."""

import os
import sys
import unittest

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import curvefit as C  # noqa: E402
import rbx_trace as RT  # noqa: E402
import trace as T  # noqa: E402

TOL = 0.9  # (trace.CURVE_TOL — checked below)
PROFILE = [(250, 300), (1150, 300), (1150, 340), (720, 340), (720, 420), (640, 420), (640, 345),  # barrel, receiver
           (560, 345), (520, 470), (470, 470), (500, 345), (350, 345), (330, 400), (250, 400)]  # grip, stock


def ellipse(a, b):
    w, h = int(2 * a + 60), int(2 * b + 60)
    cx, cy = w / 2, h / 2
    y, x = np.mgrid[0:h, 0:w]
    return (((x + 0.5 - cx) / a) ** 2 + ((y + 0.5 - cy) / b) ** 2) <= 1.0, (a, b, cx, cy)


def off_ellipse(p, a, b, cx, cy):
    """distance (px, first order) of points from the true ellipse"""
    x, y = p[:, 0] - cx, p[:, 1] - cy
    return np.abs((x / a) ** 2 + (y / b) ** 2 - 1) / np.hypot(2 * x / a ** 2, 2 * y / b ** 2)


def iou(poly, mask, ss=4):
    h, w = mask.shape
    im = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(im).polygon([(x * ss, y * ss) for x, y in poly], fill=255)
    pm = np.asarray(im) > 127
    mm = np.repeat(np.repeat(mask, ss, 0), ss, 1)
    return float((pm & mm).sum() / (pm | mm).sum())


def curves_of(mask):
    contour = T._contour(mask)
    return C.fit(*C.subpixel(contour), tol=TOL), T._simplify(contour, 1.5)


class TestCurves(unittest.TestCase):
    def test_ellipses_within_a_pixel_with_fewer_anchors(self):
        for a, b in ((300.0, 120.0), (60.0, 40.0), (25.0, 12.0)):
            m, geo = ellipse(a, b)
            cv, dp = curves_of(m)
            dense = np.array(C.sample(cv, 0.01))
            err = float(off_ellipse(dense, *geo).max())
            self.assertLessEqual(err, 1.0, f"{a:.0f}x{b:.0f}: the curve strays {err:.2f} px from the true ellipse")
            self.assertLess(len(cv), len(dp), f"{a:.0f}x{b:.0f}: {len(cv)} anchors vs {len(dp)} polygon points")
            poly = C.sample(cv, C.outline_flatness(cv, 1.5))  # (what a traced outline gets)
            self.assertGreaterEqual(iou(poly, m), iou(dp, m), f"{a:.0f}x{b:.0f}: the sampled outline fits worse")

    def test_sharp_corners_stay_sharp_and_in_place(self):
        im = Image.new("L", (1400, 700), 0)
        ImageDraw.Draw(im).polygon(PROFILE, fill=255)
        m = np.asarray(im) > 127
        cv, dp = curves_of(m)
        anchors = np.array([b[0] for b in cv])
        for corner in PROFILE:
            # PIL fills the pixel AT a vertex: the raster's own corner is the vertex or one pixel past it on each axis
            gap = min(float(np.min(np.hypot(*(anchors - (np.array(corner, float) + (dx, dy))).T)))
                      for dx in (0, 1) for dy in (0, 1))
            self.assertLessEqual(gap, 0.75, f"corner {corner}: nearest curve anchor {gap:.2f} px from the raster's corner")
        self.assertLessEqual(len(cv), len(dp) + 3)  # straight edges: about one segment each
        self.assertGreaterEqual(iou(C.sample(cv, C.outline_flatness(cv, 1.5)), m), iou(dp, m))

    def test_photo_edge_noise_is_not_shape(self):
        """a photographed outline wobbles by a pixel here and there (sensor noise, compression, a reflection on the
        edge): the curves must not chase it — fewer anchors than the old polygon had points, at an equal or better fit
        (measured on the M107 photo: 279 anchors vs 314 points, IoU 0.987 vs 0.980)"""
        rng = np.random.default_rng(1)
        im = Image.new("L", (1400, 700), 0)
        ImageDraw.Draw(im).polygon(PROFILE, fill=255)
        m = np.asarray(im) > 127
        clean = m.copy()
        edge = m & ~(np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1))
        ys, xs = np.nonzero(edge)
        for k in rng.choice(len(ys), size=len(ys) // 6, replace=False):  # 1 px bumps and nicks along the outline
            y, x = ys[k], xs[k]
            m[max(0, y - 1):y + 2, max(0, x - 1):x + 2] = rng.random() < 0.5
        cv, dp = curves_of(m)
        self.assertLess(len(cv), len(dp), f"{len(cv)} anchors vs {len(dp)} polygon points: the noise was followed")
        self.assertGreaterEqual(iou(C.sample(cv, C.outline_flatness(cv, 1.5)), clean), iou(dp, clean))

    def test_tolerance_is_the_traces(self):
        with open(os.path.join(os.path.dirname(C.__file__), "trace.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn(f"CURVE_TOL = {TOL} ", src)

    def test_tight_bend_is_a_curve_not_a_corner(self):
        m, _geo = ellipse(25.0, 12.0)  # its ends turn as sharply as a corner, but no straight edges meet there
        _pts, corners = C.subpixel(T._contour(m))
        self.assertEqual(corners, [])

    def test_rounded_rectangle(self):
        im = Image.new("L", (900, 400), 0)
        ImageDraw.Draw(im).rounded_rectangle((100, 100, 800, 300), radius=100, fill=255)
        m = np.asarray(im) > 127
        cv, dp = curves_of(m)
        self.assertLess(len(cv), len(dp))
        self.assertGreaterEqual(iou(C.sample(cv, C.outline_flatness(cv, 1.5)), m), iou(dp, m))

    def test_curves_are_closed_and_continuous(self):
        m, _geo = ellipse(60.0, 40.0)
        cv, _dp = curves_of(m)
        for b0, b1 in zip(cv, cv[1:] + cv[:1]):
            self.assertLess(float(np.linalg.norm(np.asarray(b0[3]) - np.asarray(b1[0]))), 1e-6)


class TestSmoothForBuilds(unittest.TestCase):
    def test_finer_sampling_on_request_and_old_traces_unchanged(self):
        m, _geo = ellipse(60.0, 40.0)
        cv, _dp = curves_of(m)
        design = [[[float(x) / 200, float(y) / 200] for x, y in b] for b in cv]
        t = RT.Trace({"outline": [[0, 0], [1, 0], [1, 1]], "curves": {"outline": design}})
        coarse, fine = RT.smooth(t, flat=0.002), RT.smooth(t, flat=0.0002)
        self.assertGreater(len(fine), len(coarse))
        old = RT.Trace({"outline": [[0, 0], [1, 0], [1, 1]]})
        self.assertEqual(RT.smooth(old), [(0, 0), (1, 0), (1, 1)])
        with self.assertRaises(KeyError):
            RT.smooth(old, part="grip")


if __name__ == "__main__":
    unittest.main()
