"""REPEAT (kit/blender/rbx_repeat.py, rbx.Asset.repeat): where the copies of a part go - a row, a ring, along a
path - each proven on numbers; a copy's own small difference is the same on every build; and in a real build the
copies are where the numbers say, the mirror doubles them, and the build says what it repeated.
Fixtures: kit/selftest/blender/build_repeat.py (a shape round: no bake) and check_repeat_cases.py (the corner
cases the first build's review found: frames, a ring in a row, a zone on copies, the detailed and game pair)."""

import json
import math
import os
import subprocess
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402
import rbx_repeat as R  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()


def at(m, p=(0.0, 0.0, 0.0)):
    return (m @ np.array([*p, 1.0]))[:3]


def turned(m, v):
    return m[:3, :3] @ np.array(v, np.float64)


class Row(unittest.TestCase):
    def test_each_copy_a_step_from_the_last(self):
        ms = R.row(4, (0.5, 0, -0.25))
        self.assertEqual(len(ms), 4)
        self.assertTrue(np.array_equal(ms[0], np.eye(4)))                  # the part itself, where it was put
        for k, m in enumerate(ms):
            self.assertTrue(np.allclose(at(m, (1, 2, 3)), (1 + 0.5 * k, 2, 3 - 0.25 * k)))
            self.assertTrue(np.allclose(m[:3, :3], np.eye(3)))             # moved, never turned

    def test_one_is_the_part_alone(self):
        self.assertEqual(len(R.row(1, (1, 0, 0))), 1)

    def test_what_is_not_allowed_is_said(self):
        for bad in (0, -2, 2.5, "many", None, R.MAX_COPIES + 1, float("inf"), float("nan")):
            with self.assertRaises(ValueError, msg=bad):
                R.row(bad, (1, 0, 0))
        for bad in ((1, 0), "x", (1, 0, float("nan")), None):
            with self.assertRaises(ValueError, msg=bad):
                R.row(3, bad)


class Ring(unittest.TestCase):
    def test_a_full_turn_spaces_them_evenly_and_puts_none_on_the_first(self):
        ms = R.ring(8, "Y", (0, 0, 0))
        pts = [at(m, (1, 0.4, 0)) for m in ms]
        for k, p in enumerate(pts):
            self.assertAlmostEqual(float(np.hypot(p[0], p[2])), 1.0, places=9)      # on the circle
            self.assertAlmostEqual(float(p[1]), 0.4, places=9)                      # at its height
        gaps = [float(np.linalg.norm(pts[k] - pts[(k + 1) % 8])) for k in range(8)]
        self.assertAlmostEqual(max(gaps), min(gaps), places=9)                      # the last is as far from the first
        self.assertTrue(np.allclose(pts[2], (0, 0.4, -1)))                          # a right-handed quarter turn about +Y

    def test_about_a_centre_and_any_axis(self):
        ms = R.ring(4, "Z", (2, 1, 0))
        self.assertTrue(np.allclose(at(ms[1], (3, 1, 5)), (2, 2, 5)))               # +X of the centre -> +Y of it
        tilt = R.ring(3, (1, 1, 0), (0, 0, 0))
        axis = np.array([1, 1, 0]) / math.sqrt(2)
        for m in tilt:
            self.assertTrue(np.allclose(turned(m, axis), axis))                     # the axis itself does not move
        self.assertEqual([m.tolist() for m in R.ring(4, "y")], [m.tolist() for m in R.ring(4, "Y")])

    def test_an_arc_has_a_copy_at_each_end(self):
        ms = R.ring(4, "Y", (0, 0, 0), angle=90)
        self.assertTrue(np.allclose(at(ms[0], (1, 0, 0)), (1, 0, 0)))
        self.assertTrue(np.allclose(at(ms[-1], (1, 0, 0)), (0, 0, -1)))             # 90 degrees on: the far end
        self.assertTrue(np.allclose(at(ms[1], (1, 0, 0)), (math.cos(math.radians(30)), 0, -math.sin(math.radians(30)))))

    def test_a_rise_makes_a_helix(self):
        ms = R.ring(5, "Y", (0, 0, 0), angle=180, rise=2.0)
        ys = [float(at(m, (1, 0, 0))[1]) for m in ms]
        self.assertTrue(np.allclose(ys, [0, 0.5, 1.0, 1.5, 2.0]))
        self.assertTrue(np.allclose(at(ms[-1], (1, 0, 0)), (-1, 2, 0)))

    def test_more_than_a_full_turn_needs_a_rise(self):
        for angle in (720, 1080, -720, 361):
            with self.assertRaises(ValueError, msg=angle) as e:           # the copies would land on each other
                R.ring(4, "Y", angle=angle)
            self.assertIn("land on each other", str(e.exception))
        ms = R.ring(9, "Y", angle=720, rise=3.0)                           # two turns of a spring
        self.assertTrue(np.allclose(at(ms[-1], (1, 0, 0)), (1, 3, 0)))    # the last straight above the first
        self.assertTrue(np.allclose(at(ms[4], (1, 0, 0)), (1, 1.5, 0)))   # one turn up: half the rise

    def test_a_full_turn_typed_a_hair_off_is_still_a_full_turn(self):
        for angle in (360.0000001, 359.9999999):
            pts = [at(m, (1, 0, 0)) for m in R.ring(4, "Y", angle=angle)]
            gaps = [float(np.linalg.norm(pts[k] - pts[(k + 1) % 4])) for k in range(4)]
            self.assertGreater(min(gaps), 1.4, angle)                      # four quarter turns: none on the first

    def test_what_is_not_allowed_is_said(self):
        for kw in (dict(around="W"), dict(around=(0, 0, 0)), dict(angle=0), dict(angle="wide"), dict(centre=(1, 2)),
                   dict(angle=float("inf")), dict(rise=float("nan"))):
            with self.assertRaises(ValueError, msg=kw):
                R.ring(4, **{"around": "Y", **kw})


class Path(unittest.TestCase):
    L = [(0, 0, 0), (2, 0, 0), (2, 0, 2)]                  # a path with a square corner

    def test_evenly_by_the_paths_own_length_end_to_end(self):
        ms = R.path(self.L, count=5, smooth=False)
        pts = [at(m).round(9).tolist() for m in ms]
        self.assertEqual(pts, [[0, 0, 0], [1, 0, 0], [2, 0, 0], [2, 0, 1], [2, 0, 2]])

    def test_the_part_is_modelled_at_the_paths_start(self):
        ms = R.path([(1, 1, 1), (3, 1, 1)], count=3)
        self.assertTrue(np.array_equal(ms[0], np.eye(4)))
        self.assertTrue(np.allclose(at(ms[2], (1.2, 1, 1)), (3.2, 1, 1)))           # carried with its own offset

    def test_follow_turns_each_copy_to_the_path_and_does_not_roll_it(self):
        ms = R.path(self.L, count=5, smooth=False)
        self.assertTrue(np.allclose(turned(ms[1], (1, 0, 0)), (1, 0, 0)))           # before the corner: as modelled
        self.assertTrue(np.allclose(turned(ms[3], (1, 0, 0)), (0, 0, 1)))           # after it: along the new leg
        self.assertTrue(np.allclose(turned(ms[3], (0, 1, 0)), (0, 1, 0)))           # ... and its top still up
        flat = R.path(self.L, count=5, smooth=False, follow=False)
        self.assertTrue(all(np.allclose(m[:3, :3], np.eye(3)) for m in flat))       # follow=False: only moved

    def test_spacing_instead_of_a_count(self):
        ms = R.path([(0, 0, 0), (1, 0, 0)], spacing=0.3)
        self.assertEqual([round(float(at(m)[0]), 9) for m in ms], [0.0, 0.3, 0.6, 0.9])   # none past the end

    def test_smooth_goes_through_the_points_rounded(self):
        ms = R.path(self.L, count=41)
        pts = np.array([at(m) for m in ms])
        self.assertTrue(np.allclose(pts[0], (0, 0, 0)) and np.allclose(pts[-1], (2, 0, 2)))
        self.assertLess(float(np.abs(pts - np.array([2, 0, 0])).sum(axis=1).min()), 0.08)   # near the corner point
        gaps = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        self.assertLess(float(gaps.max() / gaps.min()), 1.08)                       # evenly spaced along it
        turns = [float(np.degrees(np.arccos(np.clip(np.dot(turned(a, (1, 0, 0)), turned(b, (1, 0, 0))), -1, 1))))
                 for a, b in zip(ms, ms[1:])]
        self.assertLess(max(turns), 30.0)                                           # no copy snaps a quarter turn
        self.assertTrue(np.allclose(turned(ms[-1], (1, 0, 0)), (0, 0, 1), atol=0.2))

    def test_a_path_straight_back_on_itself_still_turns(self):
        ms = R.path([(0, 0, 0), (1, 0, 0), (0, 0.001, 0)], count=3, smooth=False)
        self.assertTrue(np.isfinite(np.array(ms)).all())
        self.assertLess(float(turned(ms[-1], (1, 0, 0))[0]), -0.99)

    def test_turning_right_round_on_the_ground_keeps_the_copy_on_its_feet(self):
        for pts in ([(0, 0, 0), (1, 0, 0), (0.2, 0, 0)], [(0, 0, 0), (0, 0, 1), (0, 0, 0.2)]):
            ms = R.path(pts, count=3, smooth=False)
            first = np.array(pts[1], np.float64) - np.array(pts[0], np.float64)
            self.assertTrue(np.allclose(turned(ms[-1], first), -first), pts)          # facing back the way it came
            self.assertTrue(np.allclose(turned(ms[-1], (0, 1, 0)), (0, 1, 0)), pts)   # ... and not upside down

    def test_a_curve_starts_as_the_part_was_modelled_and_ends_along_its_last_leg(self):
        # (the first build turned every copy from the curve's first little piece: 3.5 - 32 degrees off, all of them)
        for pts in ([(0, 0, 0), (4, 0, 0), (4, 0, 0.5)], [(0, 0, 0), (0.3, 0, 0), (4, 0, 0), (4, 0, 3)],
                    [(0, 0, 0), (2, 0, 0), (2, 0, 2)]):
            ms = R.path(pts, count=25)
            self.assertTrue(np.array_equal(ms[0], np.eye(4)), pts)                    # the part itself
            self.assertTrue(np.allclose(turned(ms[-1], (1, 0, 0)), (0, 0, 1), atol=1e-9), pts)   # along the last leg
            self.assertTrue(all(float(turned(m, (0, 1, 0))[1]) > 1 - 1e-9 for m in ms), pts)     # every top still up
            # each copy faces the way the CURVE runs at its place (the curve itself, drawn far finer than it is used)
            fine = R._smooth(np.array(pts, np.float64), False, 600)
            way = np.gradient(fine, axis=0)
            way /= np.linalg.norm(way, axis=1)[:, None]
            offs = []
            for m in R.path(pts, count=200):
                j = int(np.argmin(np.linalg.norm(fine - at(m), axis=1)))
                offs.append(float(np.degrees(np.arccos(np.clip(np.dot(turned(m, (1, 0, 0)), way[j]), -1, 1)))))
            self.assertLess(max(offs), 1.0, pts)                   # (the first build: every copy 3.5 - 32 degrees off)

    def test_a_straight_run_before_the_corner_is_not_turned_at_all(self):
        ms = R.path([(0, 0, 0), (2, 0, 0), (4, 0, 0), (4, 0, 2)], count=13)
        for m in ms:
            if float(at(m)[0]) < 2.0 - 1e-6:                                          # on the first, straight leg
                self.assertTrue(np.allclose(m[:3, :3], np.eye(3), atol=1e-9))
                self.assertAlmostEqual(float(at(m)[2]), 0.0, places=9)

    def test_a_curve_through_unevenly_spaced_points_never_runs_backwards(self):
        ms = R.path([(0, 0, 0), (0.3, 0, 0), (4, 0, 0), (4.3, 0, 0), (8, 0, 0.5)], count=120)
        xs = [float(at(m)[0]) for m in ms]
        self.assertTrue(all(b > a for a, b in zip(xs, xs[1:])))

    def test_a_closed_path_is_a_loop(self):
        sq = [(0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2), (0, 0, 0)]
        ms = R.path(sq, count=8, smooth=False)
        self.assertEqual([at(m).round(9).tolist() for m in ms],
                         [[0, 0, 0], [1, 0, 0], [2, 0, 0], [2, 0, 1], [2, 0, 2], [1, 0, 2], [0, 0, 2], [0, 0, 1]])
        self.assertEqual(len(R.path(sq, spacing=1.0, smooth=False)), 8)               # not a ninth on the first
        self.assertEqual(len(R.path(sq[:-1], spacing=1.0, smooth=False)), 7)          # open: its end is an end
        rnd = np.array([at(m) for m in R.path(sq, count=8)])                          # rounded through the join too
        gaps = [float(np.linalg.norm(rnd[k] - rnd[(k + 1) % 8])) for k in range(8)]
        self.assertGreater(min(gaps), 0.5)
        self.assertLess(max(gaps) / min(gaps), 1.25)

    def test_what_is_not_allowed_is_said(self):
        for pts in ([(0, 0, 0)], "abc", [(0, 0), (1, 1)], [(0, 0, 0), (0, 0, 0)], None):
            with self.assertRaises(ValueError, msg=pts):
                R.path(pts, count=3)
        for kw in ({}, dict(count=3, spacing=0.5), dict(spacing=0), dict(spacing="near"), dict(count=0)):
            with self.assertRaises(ValueError, msg=kw):
                R.path(self.L, **kw)
        with self.assertRaises(ValueError):
            R.path([(0, 0, 0), (1000, 0, 0)], spacing=0.5)                          # 2001 copies: a mistake


class Varied(unittest.TestCase):
    def test_no_vary_no_difference(self):
        for v in (None, {}, {"size": 0, "turn": 0, "shift": 0}):
            self.assertTrue(all(np.array_equal(m, np.eye(4)) for m in R.varied(5, v, "Tooth")), v)

    def test_the_first_is_the_part_itself_the_rest_differ_within_what_was_asked(self):
        ms = R.varied(40, {"size": 0.2, "turn": 15, "shift": 0.05}, "Tooth")
        self.assertTrue(np.array_equal(ms[0], np.eye(4)))
        scales = [float(np.cbrt(abs(np.linalg.det(m[:3, :3])))) for m in ms[1:]]
        self.assertTrue(0.8 <= min(scales) and max(scales) <= 1.2)
        self.assertGreater(max(scales) - min(scales), 0.15)                         # they really differ
        for m in ms[1:]:
            self.assertLessEqual(float(np.abs(m[:3, 3]).max()), 0.05 + 1e-9)
            r = m[:3, :3] / float(np.cbrt(np.linalg.det(m[:3, :3])))
            ang = math.degrees(math.acos(max(-1.0, min(1.0, (float(np.trace(r)) - 1) / 2))))
            self.assertLessEqual(ang, 15.0 + 1e-6)
            self.assertGreater(float(np.linalg.det(m[:3, :3])), 0)                  # never turned inside out

    def test_the_same_on_every_build_and_its_own_per_part(self):
        v = {"size": 0.2, "turn": 10}
        self.assertEqual([m.tolist() for m in R.varied(6, v, "a/Tooth/0")], [m.tolist() for m in R.varied(6, v, "a/Tooth/0")])
        self.assertNotEqual([m.tolist() for m in R.varied(6, v, "a/Tooth/0")], [m.tolist() for m in R.varied(6, v, "a/Peg/0")])

    def test_one_knob_moves_no_other(self):
        a = R.varied(6, {"size": 0.2}, "Tooth")
        b = R.varied(6, {"size": 0.2, "shift": 0.1}, "Tooth")
        for m, n in zip(a, b):
            self.assertTrue(np.allclose(m[:3, :3], n[:3, :3]))                      # the sizes stayed

    def test_what_is_not_allowed_is_said(self):
        for bad in ({"size": 1.0}, {"size": -0.1}, {"turn": 200}, {"shift": -1}, {"twist": 3}, {"size": "big"},
                    {"shift": float("inf")}, {"turn": float("nan")}, {"size": float("nan")}):
            with self.assertRaises(ValueError, msg=bad):
                R.varied(3, bad, "x")


class Resolve(unittest.TestCase):
    def test_one_of_three_says_which(self):
        self.assertEqual(R.resolve(3, step=(1, 0, 0))[0], "row")
        self.assertEqual(R.resolve(3, around="Y")[0], "ring")
        self.assertEqual(R.resolve(3, along=[(0, 0, 0), (1, 0, 0)])[0], "path")
        for kw in ({}, dict(step=(1, 0, 0), around="Y"), dict(around="Y", along=[(0, 0, 0), (1, 0, 0)])):
            with self.assertRaises(ValueError, msg=kw) as e:
                R.resolve(3, **kw)
            self.assertIn("ONE of", str(e.exception))

    def test_at_given_places_the_first_is_the_part(self):
        kind, ms = R.resolve(at=[(1, 0, 2), (1.5, 0, 2.2), (4, 1, -3)])
        self.assertEqual((kind, len(ms)), ("places", 3))
        self.assertTrue(np.array_equal(ms[0], np.eye(4)))                             # where it was modelled
        self.assertTrue(np.allclose(at(ms[2], (1, 0, 2)), (4, 1, -3)))                # moved to its place
        self.assertTrue(all(np.allclose(m[:3, :3], np.eye(3)) for m in ms))           # never turned
        for bad in ([(0, 0, 0)], [(0, 0, 0), (0, 0, 0)], "here", [(0, 0), (1, 1)]):
            with self.assertRaises(ValueError, msg=bad):
                R.resolve(at=bad)
        with self.assertRaises(ValueError):
            R.resolve(5, at=[(0, 0, 0), (1, 0, 0)])                                   # a count that is not its length
        with self.assertRaises(ValueError):
            R.resolve(at=[(0, 0, 0), (1, 0, 0)], angle=90)                            # a ring's option

    def test_an_option_of_another_kind_is_refused_not_dropped(self):
        line = [(0, 0, 0), (1, 0, 0)]
        for kw in (dict(step=(1, 0, 0), angle=90), dict(step=(1, 0, 0), centre=(0, 1, 0)), dict(step=(1, 0, 0), rise=1),
                   dict(step=(1, 0, 0), smooth=False), dict(around="Y", spacing=0.5), dict(around="Y", follow=False),
                   dict(along=line, rise=2), dict(along=line, centre=(0, 0, 0))):
            with self.assertRaises(ValueError, msg=kw) as e:
                R.resolve(3, **kw)
            self.assertIn("not an option of a", str(e.exception))

    def test_what_is_left_unsaid_is_the_plain_thing(self):
        self.assertEqual([m.tolist() for m in R.resolve(5, around="Y")[1]], [m.tolist() for m in R.ring(5, "Y")])
        bent = [(0, 0, 0), (1, 0, 0), (1, 0, 1)]
        self.assertEqual([m.tolist() for m in R.resolve(5, along=bent)[1]], [m.tolist() for m in R.path(bent, 5)])


def build(*args):
    """the fixture as a shape round -> (the report, {part: {"mid", "size"}})"""
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_repeat"))
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P",
                        os.path.join(REPO, "kit", "selftest", "blender", "build_repeat.py"), "--", "--no-preview",
                        "--geo", "--report", *args], cwd=REPO, capture_output=True, text=True, timeout=900, env=e,
                       encoding="utf-8", errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith('{"schema"')), None)
    parts = next((x for x in r.stdout.splitlines() if x.startswith("REPEAT_PARTS ")), None)
    assert r.returncode == 0 and line and parts, (r.stderr or r.stdout)[-800:]
    return json.loads(line), json.loads(parts.split(" ", 1)[1])


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.parts = build()
        cls.again, cls.parts2 = build()

    def copies(self, name):
        return [self.parts[k] for k in sorted((k for k in self.parts if k.split("~")[0] == name),
                                              key=lambda k: int(k.split("~m")[1]) if "~m" in k else 0)]

    def test_the_build_passes_and_says_what_it_repeated(self):
        self.assertEqual(self.report["status"], "pass")
        rep = self.report["facts"]["repeats"]
        self.assertEqual({k: v["copies"] for k, v in rep.items()},
                         {"Tooth": 12, "Post": 8, "Stud": 9, "Peg": 9, "Fin": 4})
        self.assertEqual(rep["Peg"]["how"], ["row x3", "row x3"])
        self.assertIn("repeats: Fin x4 (row x4), Peg x9 (row x3 in row x3), Post x8 (ring x8), Stud x9 (path x9), "
                      "Tooth x12 (row x12)", self.report["summary"])

    def test_a_row_is_where_the_step_says(self):
        teeth = self.copies("Tooth")
        self.assertEqual(len(teeth), 12)
        for k, t in enumerate(teeth):
            self.assertTrue(np.allclose(t["mid"], (-1.65 + 0.3 * k, 0.34, -1.8), atol=2e-4), (k, t))
            self.assertTrue(np.allclose(t["size"], (0.16, 0.3, 0.2), atol=2e-4))

    def test_a_ring_is_on_its_circle(self):
        posts = self.copies("Post")
        self.assertEqual(len(posts), 8)
        for k, p in enumerate(posts):
            a = math.radians(45 * k)
            self.assertTrue(np.allclose(p["mid"], (math.cos(a), 0.44, -math.sin(a)), atol=2e-3), (k, p))

    def test_a_path_is_followed_round_its_corner(self):
        studs = self.copies("Stud")
        self.assertEqual(len(studs), 9)
        self.assertTrue(np.allclose(studs[0]["mid"], (-1.6, 0.25, 1.2), atol=2e-4))
        self.assertTrue(np.allclose(studs[-1]["mid"], (0.0, 0.25, 1.8), atol=2e-3))
        self.assertTrue(np.allclose(studs[2]["size"], (0.3, 0.1, 0.1), atol=2e-3))       # along x before the corner
        self.assertTrue(np.allclose(studs[-1]["size"], (0.1, 0.1, 0.3), atol=2e-3))      # along z after it

    def test_a_row_inside_a_row_is_a_grid_and_every_peg_is_its_own(self):
        pegs = self.copies("Peg")
        self.assertEqual(len(pegs), 9)
        mids = sorted((round(p["mid"][0], 2), round(p["mid"][2], 2)) for p in pegs)
        self.assertEqual(mids, sorted((round(1.1 + 0.3 * i, 2), round(0.9 + 0.3 * j, 2)) for i in range(3) for j in range(3)))
        heights = {round(p["size"][1], 3) for p in pegs}
        self.assertGreater(len(heights), 5)                                              # sizes of their own
        self.assertTrue(np.allclose(pegs[0]["size"], (0.14, 0.24, 0.14), atol=2e-4))     # the part itself: as modelled

    def test_the_mirror_doubles_the_row(self):
        fins = self.copies("Fin")
        self.assertEqual(len(fins), 8)
        right = sorted(round(f["mid"][2], 3) for f in fins if f["mid"][0] > 0)
        left = sorted(round(f["mid"][2], 3) for f in fins if f["mid"][0] < 0)
        self.assertEqual(right, [-0.9, -0.4, 0.1, 0.6])
        self.assertEqual(left, right)
        self.assertTrue(all(abs(abs(f["mid"][0]) - 1.95) < 2e-4 for f in fins))

    def test_the_same_copies_on_every_build(self):
        self.assertEqual(self.parts, self.parts2)

    def test_a_copy_is_one_of_the_parts_copies_and_no_name_is_used_twice(self):
        names = list(self.parts)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 1 + 12 + 8 + 9 + 9 + 8)


def cases(*args):
    """check_repeat_cases.py -> what it printed (nothing is built: seconds)"""
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_repeat"))
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(REPO, "kit", "selftest", "blender", "check_repeat_cases.py"), "--", "--no-preview",
                        *args], cwd=REPO, capture_output=True, text=True, timeout=900, env=e, encoding="utf-8",
                       errors="replace")
    line = next((x for x in r.stdout.splitlines() if x.startswith("REPEAT_CASES ")), None)
    assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
    return json.loads(line.split(" ", 1)[1])


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Cases(unittest.TestCase):
    """every case is a fault the review of the first build found (2026-11-13)"""

    @classmethod
    def setUpClass(cls):
        cls.d = cases()
        cls.parts = cls.d["parts"]

    def copies(self, name):
        return [self.parts[k] for k in sorted((k for k in self.parts if k.split("~")[0] == name),
                                              key=lambda k: int(k.split("~m")[1]) if "~m" in k else 0)]

    def mids(self, name):
        return [c["mid"] for c in self.copies(name)]

    def test_a_row_runs_where_its_block_was_opened_not_in_a_frame_opened_inside_it(self):
        self.assertEqual(self.mids("Turned"), [[k, 0.5, 0.0] for k in range(4)])     # it ran along -z
        for c in self.copies("Turned"):
            self.assertEqual(c["size"], [0.6, 0.2, 0.2])                              # ... the part itself is turned

    def test_a_ring_turns_about_its_blocks_centre_not_about_a_frame_opened_inside_it(self):
        ms = self.mids("Orbit")
        self.assertEqual(len(ms), 4)
        for m in ms:
            self.assertAlmostEqual(math.hypot(m[0], m[2]), 2.5, places=3)             # it turned about x = 2
        self.assertEqual(ms[2], [-2.5, 0.5, 0.0])

    def test_a_block_opened_inside_a_frame_steps_in_that_frame(self):
        ms = self.mids("Inside")
        self.assertEqual([m[0] for m in ms], [0.0, 0.0, 0.0])
        self.assertEqual([round(abs(b[2] - a[2]), 4) for a, b in zip(ms, ms[1:])], [1.0, 1.0])

    def test_a_ring_inside_a_row_is_two_whole_rings(self):
        ms = self.mids("Wheel")
        self.assertEqual(len(ms), 8)
        for k in range(4):
            self.assertAlmostEqual(math.hypot(ms[k][0] + 4, ms[k][2] + 3), 1.0, places=3)        # round the first hub
            self.assertAlmostEqual(math.hypot(ms[k + 4][0], ms[k + 4][2] + 3), 1.0, places=3)    # round the second
            self.assertEqual([round(ms[k + 4][i] - ms[k][i], 4) for i in range(3)], [4.0, 0.0, 0.0])
        self.assertEqual(len({tuple(m) for m in ms}), 8)

    def test_a_copy_differs_about_its_own_middle_wherever_its_geometry_is(self):
        cs = self.copies("Lump")
        self.assertEqual([c["mid"] for c in cs], [[3.1, 1.1, round(3.1 + 0.4 * k, 4)] for k in range(6)])
        sizes = [c["size"][0] for c in cs]
        self.assertGreater(max(sizes) - min(sizes), 0.05)                             # and they really differ

    def test_the_mirror_is_of_the_whole_row(self):
        self.assertEqual([m[0] for m in self.mids("Rail")], [1.0, 1.5, 2.0, -1.0, -1.5, -2.0])

    def test_a_zone_goes_to_every_copy_on_the_half_the_part_has_it(self):
        z = self.d["zones"]
        self.assertEqual(sorted(z), ["Tip", "Tip~m1", "Tip~m2", "Tip~m3", "Tip~m4", "Tip~m5"])
        self.assertTrue(0 < z["Tip"]["faces"] < z["Tip"]["of"])
        for name, row in z.items():
            self.assertEqual((row["faces"], row["of"]), (z["Tip"]["faces"], z["Tip"]["of"]), name)
        for name in ("Tip", "Tip~m1", "Tip~m2"):
            self.assertLess(z[name]["side_x"], -0.05, name)                           # toward the model's middle
        for name in ("Tip~m3", "Tip~m4", "Tip~m5"):
            self.assertGreater(z[name]["side_x"], 0.05, name)                         # the mirror: its own inner half
        self.assertEqual(self.d["zone_fact"]["copies"], 5)

    def test_a_repeated_cutter_is_no_repeated_part_once_it_has_cut(self):
        self.assertIn("Slot", self.d["said"])
        self.assertNotIn("Slot", self.d["live"])
        self.assertIn("Tip", self.d["live"])

    def test_what_is_not_allowed_is_said_and_leaves_nothing_behind(self):
        e = self.d["errors"]
        self.assertIn("is 600 of every part", e["nested"])                            # said at the block
        self.assertIn("a.repeat", e["stamp"])
        self.assertIn("not an option of a row", e["option"])
        self.assertIn("800 copies", e["mirrors"])
        self.assertNotIn("TooMany", self.parts)                                       # nothing of it was made
        self.assertEqual(self.d["open_after"], 0)                                     # no block left open

    def test_the_detailed_and_the_game_version_of_a_part_get_the_same_copies(self):
        d = cases("--pair")
        self.assertEqual(d["said"], ["Lug"])                                          # the high is not a part of its own
        self.assertEqual(len(d["parts"]), 5)
        for name, low in d["parts"].items():
            high = d["highs"][name.replace("Lug", "Lug~high")]
            for i in range(3):   # (two tessellations of one solid: a hair apart; the copies differ by a third)
                self.assertAlmostEqual(low["mid"][i], high["mid"][i], delta=0.002, msg=name)
                self.assertAlmostEqual(low["size"][i], high["size"][i], delta=0.002, msg=name)
        widths = [p["size"][1] for p in d["parts"].values()]
        self.assertGreater(max(widths) - min(widths), 0.05)


if __name__ == "__main__":
    unittest.main()
