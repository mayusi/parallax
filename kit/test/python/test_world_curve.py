"""kit/world/curve.py - the smooth line through typed points (the terrain tool's rivers), the Python twin of
kit/lib/worldcurve.luau. Both are held to ONE table of cases (kit/test/fixtures/curve_cases.json), and the curve's own
properties are held here without the table: it passes through every typed point in order, a ring closes, no joint
turns sharply where the typed points leave room.
Run: python kit/test/python/run.py -k world_curve"""

import importlib.util
import json
import math
import os
import random
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
_spec = importlib.util.spec_from_file_location("kit_world_curve", os.path.join(ROOT, "kit", "world", "curve.py"))
CV = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CV)

with open(os.path.join(ROOT, "kit", "test", "fixtures", "curve_cases.json"), encoding="utf-8") as _f:
    CASES = json.load(_f)["cases"]


def joints(line):
    return [CV.turn(line[i - 1], line[i], line[i + 1]) for i in range(1, len(line) - 1)]


def pieces(line):
    return [math.dist(line[i - 1], line[i]) for i in range(1, len(line))]


class TableTest(unittest.TestCase):
    def test_every_case_of_the_shared_table_number_for_number(self):
        self.assertGreaterEqual(len(CASES), 10)
        for c in CASES:
            out = CV.through(c["points"], step=c.get("step"), max_turn=c.get("maxTurn"), least=c.get("least"), closed=bool(c.get("closed")))
            self.assertEqual(len(out), len(c["out"]), c["name"])
            for got, want in zip(out, c["out"]):
                self.assertEqual(len(got), len(want), c["name"])
                for a, b in zip(got, want):
                    self.assertAlmostEqual(a, b, places=9, msg=c["name"])
            self.assertAlmostEqual(CV.sharpest(c["points"]), c["sharpest"], places=9, msg=c["name"])


class PropertyTest(unittest.TestCase):
    def test_the_line_passes_through_every_typed_point_in_order(self):
        rnd = random.Random(7)
        for _ in range(200):
            pts = [[rnd.uniform(-300, 300), rnd.uniform(-300, 300)] for _ in range(rnd.randint(3, 8))]
            out = CV.through(pts)
            at = 0
            for p in pts:
                hit = next((k for k in range(at, len(out)) if math.dist(out[k], p) < 1e-9), None)
                self.assertIsNotNone(hit, (p, pts))
                at = hit
            self.assertEqual(out[0], pts[0])
            self.assertEqual(out[-1], pts[-1])

    def test_a_ring_returns_to_its_first_point_and_is_round(self):
        ring = [[100, 0], [0, 100], [-100, 0], [0, -100]]
        out = CV.through(ring, closed=True)
        self.assertEqual(out[0], out[-1])
        self.assertEqual(out[0], [100, 0])
        radii = [math.hypot(x, z) for x, z in out]
        self.assertGreater(min(radii), 88)  # (straight chords between the four points dip to 70.7)
        self.assertLess(max(radii), 108)
        self.assertLess(max(joints(out)), 9)
        # the seam is a joint like any other: no corner where the ring closes
        self.assertLess(CV.turn(out[-2], out[0], out[1]), 9)

    def test_where_the_typed_points_leave_room_no_joint_turns_sharply_and_no_piece_is_long(self):
        rnd = random.Random(11)
        checked = 0
        for _ in range(300):
            # points at least 60 apart, turning at most 60 degrees: a road someone would type
            pts, heading = [[0.0, 0.0]], rnd.uniform(0, 360)
            for _ in range(rnd.randint(2, 6)):
                heading += rnd.uniform(-60, 60)
                d = rnd.uniform(60, 200)
                pts.append([pts[-1][0] + d * math.cos(math.radians(heading)), pts[-1][1] + d * math.sin(math.radians(heading))])
            out = CV.through(pts)
            self.assertLessEqual(max(joints(out)), 9.0, pts)  # (asked: 6; a cut falls on a sample, never between)
            self.assertLessEqual(max(pieces(out)), 12.0 + 1e-6, pts)
            self.assertGreaterEqual(min(pieces(out)), 1.0 - 1e-6, pts)
            self.assertGreater(len(out), len(pts))
            checked += 1
        self.assertEqual(checked, 300)

    def test_a_tight_corner_turns_as_much_a_piece_as_its_legs_leave_room_for(self):
        """a fresh reader, 2026-11-13: "no joint turns more than maxTurn" was false on ordinary corners (17 degrees
        for a right angle typed with 40-stud legs, 59 with 10) and both test files only asked roomy ones. What is
        true: the turn of a joint is limited by the least piece (1 stud) on a bend tighter than that can follow."""
        worst = {}
        for leg in (200, 100, 60, 40, 20, 10):
            out = CV.through([[0, 0], [leg, 0], [leg, leg]])
            worst[leg] = max(joints(out))
            self.assertGreaterEqual(min(pieces(out)), 1.0 - 1e-6, leg)
        for leg in (200, 100, 60):
            self.assertLessEqual(worst[leg], 7.0, worst)  # roomy: about what was asked (6)
        self.assertLessEqual(worst[40], 11.0, worst)
        self.assertLessEqual(worst[20], 20.0, worst)
        self.assertLessEqual(worst[10], 31.0, worst)
        self.assertGreater(worst[10], worst[40])  # (the tighter the typed corner, the sharper its joints)
        # a line that doubles back on itself is a hairpin whatever is asked: its joints are sharp, and say so
        self.assertGreater(max(joints(CV.through([[0, 0], [50, 0], [0, 0.5]]))), 30.0)

    def test_what_an_option_may_be_asked_down_to(self):
        corner = [[0, 0], [100, 0], [100, 100]]
        # a tiny step is floored at half a stud: a blueprint cannot ask for a hundred thousand pieces
        fine = CV.through(corner, step=0.001)
        self.assertLess(len(fine), 1200)
        self.assertGreaterEqual(min(pieces(fine)), 0.25 - 1e-6)
        self.assertEqual(fine, CV.through(corner, step=0.5))
        # a least longer than the step does not overrule the step
        out = CV.through(corner, step=5, least=40)
        self.assertLessEqual(max(pieces(out)), 5.0 + 1e-6)
        self.assertEqual(out, CV.through(corner, step=5, least=2.5))
        # a span a thousand studs long is still cut to the step
        long = CV.through([[0, 0], [1000, 100], [2000, 0]])
        self.assertLessEqual(max(pieces(long)), 12.0 + 1e-6)
        # True is no number (Python would read it as 1)
        self.assertEqual(CV.through(corner, step=True, max_turn=True, least=True), CV.through(corner))

    def test_a_curve_is_never_far_from_what_was_typed(self):
        # (a road typed through a gap between two houses must still pass the gap: the curve bulges, it does not wander)
        pts = [[0, 0], [100, 0], [100, 100], [200, 100]]
        out = CV.through(pts)

        def to_typed(p):
            best = 1e9
            for a, b in zip(pts, pts[1:]):
                vx, vz = b[0] - a[0], b[1] - a[1]
                t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vz) / (vx * vx + vz * vz)))
                best = min(best, math.hypot(p[0] - a[0] - vx * t, p[1] - a[1] - vz * t))
            return best

        self.assertLess(max(to_typed(p) for p in out), 14.0)  # (100-stud legs: the bulge is about an eighth of a leg)
        self.assertGreater(max(to_typed(p) for p in out), 2.0)  # ... and it is a curve, not the typed corners again

    def test_nothing_to_curve(self):
        self.assertEqual(CV.through([[0, 0], [50, 20]]), [[0, 0], [50, 20]])
        self.assertEqual(CV.through([[3, 4]]), [[3, 4]])
        self.assertEqual(CV.through([]), [])
        self.assertEqual(CV.through([[0, 0], [0, 0], [9, 0]]), [[0, 0], [9, 0]])  # a repeat is one point
        self.assertEqual(CV.sharpest([[0, 0], [10, 0], [20, 0]]), 0.0)
        self.assertAlmostEqual(CV.sharpest([[0, 0], [10, 0], [10, 10]]), 90.0)
        self.assertAlmostEqual(CV.sharpest([[0, 0], [10, 0], [10, 0], [10, 10]]), 90.0)  # (a repeat hides no corner)

    def test_options_typed_as_nonsense_fall_back_to_the_defaults(self):
        pts = [[0, 0], [80, 10], [160, -10]]
        want = CV.through(pts)
        for bad in (0, -3, "wide", None, True, False):
            self.assertEqual(CV.through(pts, step=bad, max_turn=bad, least=bad), want, bad)


class RiverTest(unittest.TestCase):
    """kit world terrain: a river shape with "curve": true is carved along the smooth line through its points"""

    def setUp(self):
        spec = importlib.util.spec_from_file_location("kit_world_terrain_curve", os.path.join(ROOT, "kit", "world", "terrain.py"))
        self.T = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.T)

    def land(self, curve):
        river = {"type": "river", "points": [[-150, -150], [0, -150], [0, 150]], "width": 16, "depth": 12, "edge": 8}
        if curve is not None:
            river["curve"] = curve
        h, _, _ = self.T.designed(128, 512.0, {"noise": {"relief": 0}, "shapes": [river]}, 1)
        return h

    def at(self, h, x, z):
        i = lambda v: int(round((v + 256.0) / 512.0 * 127))  # noqa: E731
        return float(h[i(x), i(z)])

    def test_the_bed_follows_the_curve_not_the_typed_corner(self):
        hard, soft = self.land(None), self.land(True)
        top = float(hard.max())
        self.assertAlmostEqual(top - float(hard.min()), 12.0, delta=0.5)
        # the point of the curve's own line that swings farthest from the two typed legs (a curve through points
        # runs wide of a corner; it never cuts it)
        typed = [[-150.0, -150.0], [0.0, -150.0], [0.0, 150.0]]

        def to_typed(q):
            best = 1e9
            for a, b in zip(typed, typed[1:]):
                vx, vz = b[0] - a[0], b[1] - a[1]
                t = max(0.0, min(1.0, ((q[0] - a[0]) * vx + (q[1] - a[1]) * vz) / (vx * vx + vz * vz)))
                best = min(best, math.hypot(q[0] - a[0] - vx * t, q[1] - a[1] - vz * t))
            return best

        off = max(CV.through(typed), key=to_typed)
        self.assertGreater(to_typed(off), 16.0)  # (past the hard river's bed and its bank)
        self.assertLess(self.at(soft, off[0], off[1]), top - 9.0)  # in the bed with the curve
        self.assertGreater(self.at(hard, off[0], off[1]), top - 1.5)  # dry land without it
        # the typed corner itself: in the hard river's bed; the curve still passes through it
        self.assertLess(self.at(hard, 0, -150), top - 9.0)
        self.assertLess(self.at(soft, 0, -150), top - 9.0)
        # far along a straight leg both are the same river
        self.assertAlmostEqual(self.at(hard, 0, 100), self.at(soft, 0, 100), delta=0.6)

    def test_curve_false_and_no_curve_are_the_same_land(self):
        self.assertTrue(np.array_equal(self.land(None), self.land(False)))
        self.assertFalse(np.array_equal(self.land(None), self.land(True)))

    def test_the_river_reads_curve_as_the_compiler_reads_a_paths(self):
        """(a fresh reader: {} was no curve here and a curve in the compiler; "no" was a curve here and an error
        there; { "step" } was ignored; a 3-number point was cut to two without a word)"""
        self.assertTrue(np.array_equal(self.land({}), self.land(True)))
        self.assertTrue(np.array_equal(self.land({"closed": False}), self.land(True)))
        self.assertFalse(np.array_equal(self.land({"step": 60, "least": 30, "maxTurn": 40}), self.land(True)))
        for bad in ("no", "yes", 1, 0, [True]):
            with self.assertRaises(ValueError, msg=bad):
                self.land(bad)
        river = {"type": "river", "points": [[-150, 0, -150], [0, 0, -150], [0, 0, 150]], "width": 16, "depth": 12, "curve": True}
        with self.assertRaises(ValueError):
            self.T.designed(64, 512.0, {"noise": {"relief": 0}, "shapes": [river]}, 1)


if __name__ == "__main__":
    unittest.main()
