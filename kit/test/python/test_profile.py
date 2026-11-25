"""rbx.profile — the outline operations every traced build uses (moved into the kit from the private Silverballer /
Glock scripts after the owner's 85/100 on the Glock, 2026-10-10). Each test pins what a build relies on."""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_profile as P  # noqa: E402

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def _area(poly):
    return 0.5 * abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1])))


def _turn_deg(pts):
    """the largest turn between consecutive legs of a path"""
    worst = 0.0
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        v1, v2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        if l1 > 1e-9 and l2 > 1e-9:
            cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))
            worst = max(worst, math.degrees(math.acos(cos)))
    return worst


class Clip(unittest.TestCase):
    def test_clip_keeps_the_band(self):
        band = P.clip_h(SQUARE, 2.0, 5.0)
        self.assertAlmostEqual(_area(band), 30.0)
        self.assertEqual(P.extents(band), (0.0, 10.0, 2.0, 5.0))
        self.assertAlmostEqual(_area(P.clip_f(SQUARE, hi=4.0)), 40.0)

    def test_spans(self):
        self.assertEqual(P.span_at(SQUARE, 5.0), (0.0, 10.0))
        self.assertEqual(P.vspan(SQUARE, 3.0), (0.0, 10.0))
        self.assertIsNone(P.span_at(SQUARE, 12.0))

    def test_edge_is_a_median(self):
        # a bottom edge at h 0 with one notch 2 mm up between f 4 and 5: the median ignores it
        notched = [(0, 0), (4, 0), (4, 2), (5, 2), (5, 0), (10, 0), (10, 10), (0, 10)]
        self.assertAlmostEqual(P.edge(notched, 0.5, 9.5), 0.0)
        self.assertAlmostEqual(P.edge(notched, 0.5, 9.5, which="upper"), 10.0)


class Transforms(unittest.TestCase):
    def test_rotate_counter_clockwise(self):
        (f, h), = P.rotate([(1.0, 0.0)], (0.0, 0.0), 90)
        self.assertAlmostEqual(f, 0.0)
        self.assertAlmostEqual(h, 1.0)

    def test_between_follows_the_ring(self):
        self.assertEqual(P.between(SQUARE, (10, 0), (0, 10)), [(10.0, 0.0), (10.0, 10.0), (0.0, 10.0)])

    def test_simplify_drops_collinear_noise(self):
        ring = [(x * 0.5, 0.01 * (x % 2)) for x in range(21)] + [(10.0, 10.0), (0.0, 10.0)]
        out = P.simplify(ring, 0.05)
        self.assertLessEqual(len(out), 5)
        self.assertAlmostEqual(_area(out), _area(ring), delta=0.2)

    def test_rounded_is_json_ready(self):
        self.assertEqual(P.rounded([(1.23456, 2.0)]), [[1.23, 2.0]])


class Curves(unittest.TestCase):
    def test_catmull_passes_its_keys_without_creases(self):
        keys = [(0.0, 0.0), (2.0, 1.5), (4.0, 2.0), (6.0, 1.5), (8.0, 0.0)]
        path = P.catmull(keys, step=0.25)
        for k in keys:
            self.assertLess(min(math.hypot(p[0] - k[0], p[1] - k[1]) for p in path), 1e-9)
        self.assertLess(_turn_deg(path), 8.0)   # (the polyline through the same keys turns 36.9 deg at its 2nd key)
        self.assertGreater(_turn_deg(keys), 25.0)

    def test_u_floor_is_a_half_ellipse(self):
        pts = P.u_floor(5.0, 0.0, -3.0, n=40)
        self.assertEqual(pts[0], (5.0, 0.0))
        self.assertAlmostEqual(pts[-1][0], -5.0)
        self.assertAlmostEqual(min(p[1] for p in pts), -3.0)
        self.assertLess(_turn_deg(pts), 10.0)

    def test_u_section_cuts_down_from_the_top(self):
        sec = P.u_section(-4.0, 4.0, 2.0, 6.0, top=10.0, chamfer=0.5)
        f0, f1, h0, h1 = P.extents(sec)
        self.assertAlmostEqual(h0, 10.0 - 6.0)      # (the floor's lowest point: floor_d below the top)
        self.assertAlmostEqual(h1, 13.0)            # (the cutter rises `above` past the top)
        self.assertAlmostEqual(f0, -4.5)
        self.assertAlmostEqual(f1, 4.5)
        square_right = P.u_section(-4.0, 4.0, 2.0, 6.0, top=10.0, chamfer=0.5, chamfer_right=False)
        self.assertAlmostEqual(P.extents(square_right)[1], 4.0)

    def test_smooth_run_takes_the_wiggle_out(self):
        # a strap traced with 0.2 mm pixel wiggle along h -10 .. -40 at f = 30, inside a closed outline
        strap = [(30.0 + (0.2 if k % 2 else -0.2), -10.0 - k) for k in range(31)]
        ring = [(0.0, 0.0), (30.0, 0.0)] + strap + [(30.0, -50.0), (0.0, -50.0)]
        out = P.smooth_run(ring, -10.0, -40.0, near=lambda h: 30.0)
        run = [p for p in out if -40.0 <= p[1] <= -10.0 and p[0] > 20]
        self.assertLess(max(abs(p[0] - 30.0) for p in run), 0.05)
        self.assertEqual(out[:2], ring[:2])         # (everything outside the run left as traced)
        self.assertEqual(out[-2:], ring[-2:])

    def test_smooth_run_never_guesses(self):
        few = [(0.0, 0.0), (1.0, -1.0), (2.0, -2.0)]
        self.assertEqual(P.smooth_run(few, 0.0, -2.0), few)   # (under 6 points: as it was)


if __name__ == "__main__":
    unittest.main()
