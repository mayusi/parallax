"""DEFORM (kit/blender/rbx_deform.py, rbx.Asset.bend / twist / taper / conform): a part built straight, then bent,
twisted, tapered or laid onto another surface - each proven on numbers; and in Blender the part, its copies and
its detailed version move together and the build says what was deformed.
Fixture: kit/selftest/blender/build_deform.py and check_deform_cases.py."""

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
import rbx_deform as D  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()


def bar(length=2.0, half=0.1, n=21):
    """a square bar along +Z from z = 0: n sections of four corners, and its middle line"""
    zs = np.linspace(0.0, length, n)
    corners = [(-half, -half), (half, -half), (half, half), (-half, half)]
    pts = np.array([(x, y, z) for z in zs for x, y in corners])
    mid = np.array([(0.0, 0.0, z) for z in zs])
    return pts, mid


def length_of(line):
    return float(np.linalg.norm(np.diff(line, axis=0), axis=1).sum())


class Bend(unittest.TestCase):
    def test_the_middle_line_keeps_its_length_and_ends_turned_by_the_whole_angle(self):
        pts, mid = bar(n=201)
        o = (0.0, 0.0, 1.0)
        for angle in (30, 90, 180, -90):
            out = D.bend(mid, "Z", "Y", angle, origin=o)
            self.assertAlmostEqual(length_of(out), 2.0, places=3, msg=angle)
            end = out[-1] - out[-2]
            end /= np.linalg.norm(end)
            want = (0.0, math.sin(math.radians(angle)), math.cos(math.radians(angle)))
            self.assertTrue(np.allclose(end, want, atol=0.02), (angle, end))          # toward +Y for a positive angle

    def test_the_inside_shortens_and_the_outside_stretches(self):
        pts, _mid = bar(n=201)
        out = D.bend(pts, "Z", "Y", 90)
        inner = out[2::4]                                                             # the corners at y = +0.1
        outer = out[0::4]                                                             # the corners at y = -0.1
        r = 2.0 / (math.pi / 2)
        self.assertAlmostEqual(length_of(inner), (r - 0.1) * math.pi / 2, places=3)
        self.assertAlmostEqual(length_of(outer), (r + 0.1) * math.pi / 2, places=3)

    def test_a_section_stays_a_flat_square_of_its_own_size(self):
        pts, _mid = bar()
        out = D.bend(pts, "Z", "Y", 120).reshape(-1, 4, 3)
        for sec in out:
            sides = [float(np.linalg.norm(sec[i] - sec[(i + 1) % 4])) for i in range(4)]
            self.assertTrue(np.allclose(sides, 0.2, atol=1e-9))
            n = np.cross(sec[1] - sec[0], sec[3] - sec[0])
            self.assertAlmostEqual(float(abs(n @ (sec[2] - sec[0]))), 0.0, places=9)

    def test_only_the_stretch_between_start_and_stop_bends(self):
        pts, mid = bar(n=41)
        out = D.bend(pts, "Z", "Y", 90, start=0.25, stop=0.75)
        before = pts[:, 2] <= 0.5 + 1e-9
        self.assertTrue(np.array_equal(out[before], pts[before]))                     # before it: untouched
        line = D.bend(mid, "Z", "Y", 90, start=0.25, stop=0.75, origin=(0, 0, 1))
        tail = line[mid[:, 2] >= 1.5 - 1e-9]
        ways = np.diff(tail, axis=0)
        ways /= np.linalg.norm(ways, axis=1)[:, None]
        self.assertTrue(np.allclose(ways, (0, 1, 0), atol=1e-9))                      # past it: straight, turned 90
        self.assertAlmostEqual(length_of(line), 2.0, places=2)

    def test_no_angle_no_change_and_the_other_way_is_the_mirror(self):
        pts, _mid = bar()
        self.assertTrue(np.array_equal(D.bend(pts, "Z", "Y", 0), pts))
        a, b = D.bend(pts, "Z", "Y", -60), D.bend(pts, "Z", "-Y", 60)
        self.assertTrue(np.allclose(a, b))

    def test_any_axis_and_a_direction_given_as_numbers(self):
        pts, _mid = bar()
        turned = pts[:, [2, 0, 1]]                                                    # the same bar along +X
        a = D.bend(pts, "Z", "Y", 70)
        b = D.bend(turned, (1, 0, 0), (0, 0, 2.5), 70)
        self.assertTrue(np.allclose(a[:, [2, 0, 1]], b))

    def test_a_stretch_gets_a_slice_at_each_end_that_lies_inside_the_part(self):
        pts, _mid = bar()
        self.assertEqual(D.edges(pts, "Z"), [])                                       # the whole length: none needed
        cut = D.edges(pts, "Z", start=0.25, stop=0.75)
        self.assertEqual([round(float(p[2]), 9) for p, _n in cut], [0.5, 1.5])
        self.assertEqual([round(float(p[2]), 9) for p, _n in D.edges(pts, "Z", start=0.5)], [1.0])

    def test_no_more_than_a_full_turn(self):
        thin, _mid = bar(length=4.0, half=0.02)
        D.bend(thin, "Z", "Y", 360)                                                   # a bar bent into a ring
        for angle in (361, 720, -400):
            with self.assertRaises(ValueError, msg=angle):                            # it would lie on itself
                D.bend(thin, "Z", "Y", angle)

    def test_what_is_not_allowed_is_said(self):
        pts, _mid = bar()
        for kw in (dict(toward="Z"), dict(toward=(0, 0, 0)), dict(angle="far"), dict(angle=float("nan")),
                   dict(angle=5000), dict(start=0.6, stop=0.4), dict(start=-0.1), dict(along="W"), dict(along="X"
                                                                                                         )):
            args = {"along": "Z", "toward": "Y", "angle": 30, **kw}
            if kw.get("along") == "X":
                with self.assertRaises(ValueError):                                   # a flat sheet has no length there
                    D.bend(np.array([(0.0, 0, 0), (0, 1, 0), (0, 0, 1)]), **args)
                continue
            with self.assertRaises(ValueError, msg=kw):
                D.bend(pts, **args)

    def test_a_bend_too_tight_for_the_parts_thickness_is_refused(self):
        thick, _mid = bar(length=0.5, half=0.4)
        with self.assertRaises(ValueError) as e:
            D.bend(thick, "Z", "Y", 180)                                              # radius 0.16, the part reaches 0.4
        self.assertIn("fold through itself", str(e.exception))
        D.bend(thick, "Z", "Y", 40)                                                   # radius 0.72: fine


class Twist(unittest.TestCase):
    def test_every_section_turned_about_the_axis_by_its_share(self):
        pts, _mid = bar(n=11)
        out = D.twist(pts, "Z", 90).reshape(-1, 4, 3)
        src = pts.reshape(-1, 4, 3)
        for k, (a, b) in enumerate(zip(src, out)):
            t = math.radians(90 * k / 10)
            c, s = math.cos(t), math.sin(t)
            want = np.stack([a[:, 0] * c - a[:, 1] * s, a[:, 0] * s + a[:, 1] * c, a[:, 2]], axis=1)   # right-handed
            self.assertTrue(np.allclose(b, want), k)

    def test_between_start_and_stop_and_the_whole_angle_after(self):
        pts, _mid = bar(n=41)
        out = D.twist(pts, "Z", 60, start=0.5)
        self.assertTrue(np.allclose(out[pts[:, 2] <= 1.0], pts[pts[:, 2] <= 1.0]))
        last, was = out[-4:], pts[-4:]
        c, s = math.cos(math.radians(60)), math.sin(math.radians(60))
        self.assertTrue(np.allclose(last[:, 0], was[:, 0] * c - was[:, 1] * s))

    def test_about_its_own_axis_wherever_the_part_is(self):
        pts, _mid = bar()
        far = pts + np.array([5.0, -3.0, 2.0])
        self.assertTrue(np.allclose(D.twist(far, "Z", 45) - np.array([5.0, -3.0, 2.0]), D.twist(pts, "Z", 45)))

    def test_what_is_not_allowed_is_said(self):
        pts, _mid = bar()
        for kw in (dict(angle="much"), dict(angle=float("inf")), dict(angle=99999), dict(start=1.0, stop=1.0)):
            with self.assertRaises(ValueError, msg=kw):
                D.twist(pts, **{"along": "Z", "angle": 30, **kw})


class Taper(unittest.TestCase):
    def test_from_whole_at_the_start_to_end_at_the_stop(self):
        pts, _mid = bar(n=11)
        out = D.taper(pts, "Z", end=0.25).reshape(-1, 4, 3)
        for k, sec in enumerate(out):
            side = float(np.linalg.norm(sec[0] - sec[1]))
            self.assertAlmostEqual(side, 0.2 * (1 + (0.25 - 1) * k / 10), places=9)
            self.assertTrue(np.allclose(sec.mean(axis=0), (0, 0, 0.2 * k)))           # about its own axis

    def test_keep_holds_one_direction(self):
        pts, _mid = bar(n=3)
        out = D.taper(pts, "Z", end=0.5, keep="Y")
        self.assertTrue(np.allclose(out[:, 1], pts[:, 1]))                            # its thickness stays
        self.assertTrue(np.allclose(np.abs(out[-4:, 0]), 0.05))                       # its width halves

    def test_a_profile_gives_a_belly(self):
        pts, _mid = bar(n=5)
        out = D.taper(pts, "Z", profile=[(0, 1), (0.5, 2), (1, 0.5)]).reshape(-1, 4, 3)
        sides = [float(np.linalg.norm(sec[0] - sec[1])) for sec in out]
        self.assertTrue(np.allclose(sides, [0.2, 0.3, 0.4, 0.25, 0.1]))
        cuts = D.profile_cuts(pts, "Z", [(0, 1), (0.5, 2), (1, 0.5)])
        self.assertEqual(len(cuts), 1)                                                # one slice: at the belly
        self.assertTrue(np.allclose(cuts[0][0], (0, 0, 1.0)) and np.allclose(cuts[0][1], (0, 0, 1)))

    def test_what_is_not_allowed_is_said(self):
        pts, _mid = bar()
        for kw in ({}, dict(end=0.5, profile=[(0, 1), (1, 2)]), dict(end=0), dict(end=-1), dict(end="thin"),
                   dict(end=float("inf")), dict(profile=[(0, 1)]), dict(profile=[(0, 1), (0, 2)]),
                   dict(profile=[(0, 1), (1.5, 2)]), dict(profile=[(0, 1), (1, 0)]), dict(end=0.5, keep="Z")):
            with self.assertRaises(ValueError, msg=kw):
                D.taper(pts, "Z", **kw)


class Within(unittest.TestCase):
    def test_other_points_are_deformed_as_the_part_is(self):
        pts, mid = bar()
        span = D.span(pts, "Z")
        whole = {"bend": D.bend(pts, "Z", "Y", 80), "twist": D.twist(pts, "Z", 80), "taper": D.taper(pts, "Z", end=0.3)}
        half = pts[: len(pts) // 2]                                                   # only its lower half: half as long
        for kind, out in whole.items():
            fn = getattr(D, kind)
            args = {"bend": ("Z", "Y", 80), "twist": ("Z", 80), "taper": ("Z", 0.3)}[kind]
            same = fn(half, *args, within=span)
            self.assertTrue(np.allclose(same, out[: len(half)]), kind)                # as part of the whole
            self.assertFalse(np.allclose(fn(half, *args), out[: len(half)]), kind)    # on its own: its own length

    def test_a_copy_is_laid_down_from_the_parts_own_leading_side(self):
        pts = np.array([(0.0, 1.0, 0.0), (0.0, 1.05, 0.0)])
        top_only = pts[1:]
        out, _m = D.conform(top_only, "-Y", np.array([1.05]), lead=-1.0)              # the part's underside is at y = 1
        self.assertTrue(np.allclose(out, [(0.0, 0.05, 0.0)]))


class Slices(unittest.TestCase):
    def test_evenly_between_the_start_and_the_stop_never_on_them(self):
        pts, _mid = bar()
        cuts = D.cuts(pts, "Z", 3)
        self.assertEqual([round(float(p[2]), 9) for p, _n in cuts], [0.5, 1.0, 1.5])
        half = D.cuts(pts, "Z", 1, start=0.5)
        self.assertEqual([round(float(p[2]), 9) for p, _n in half], [1.5])
        self.assertEqual(D.cuts(pts, "Z", 0), [])
        for bad in (-1, 2.5, "few", D.MAX_CUTS + 1):
            with self.assertRaises(ValueError, msg=bad):
                D.cuts(pts, "Z", bad)

    def test_a_curve_gets_a_slice_every_ten_degrees(self):
        self.assertEqual([D.needed(a) for a in (0, 5, 10, 11, 90, -90, 360)], [0, 0, 0, 1, 8, 8, 35])
        self.assertEqual(D.needed(1e9), D.MAX_CUTS)

    def test_a_grid_across_the_way_it_travels(self):
        plate = np.array([(x, 1.0, z) for x in (-1.0, 1.0) for z in (-0.5, 0.5)])
        planes = D.grid(plate, "-Y", 0.5)
        across_x = sorted(round(float(p @ n), 9) for p, n in planes if abs(n[0]) > 0.9)
        across_z = sorted(round(abs(float(p @ n)), 9) for p, n in planes if abs(n[2]) > 0.9)
        self.assertEqual(across_x, [-0.5, 0.0, 0.5])                                  # 2 wide: four pieces of 0.5
        self.assertEqual(across_z, [0.0])                                             # 1 deep: two pieces
        for bad in (0, -1, "fine", float("nan")):
            with self.assertRaises(ValueError, msg=bad):
                D.grid(plate, "-Y", bad)


class Conform(unittest.TestCase):
    @staticmethod
    def strap(n=41, thick=0.05, y=1.0):
        xs = np.linspace(-1.0, 1.0, n)
        return np.array([(x, y + t, z) for x in xs for t in (0.0, thick) for z in (-0.1, 0.1)]), xs

    @staticmethod
    def hill(x):
        return 0.3 * np.cos(x * 1.5)

    def test_its_leading_side_lies_on_the_surface_and_it_keeps_its_thickness(self):
        pts, _xs = self.strap()
        reach = pts[:, 1] - self.hill(pts[:, 0])                                      # straight down onto the hill
        out, missed = D.conform(pts, "-Y", reach, gap=0.01)
        self.assertEqual(missed, 0.0)
        under = np.isclose(pts[:, 1], 1.0)
        self.assertTrue(np.allclose(out[under, 1], self.hill(pts[under, 0]) + 0.01))  # the underside: a gap above it
        self.assertTrue(np.allclose(out[~under, 1] - out[under, 1].reshape(-1, 2).repeat(1, axis=0).reshape(-1),
                                    0.05))                                            # the top: 0.05 above its underside
        self.assertTrue(np.allclose(out[:, [0, 2]], pts[:, [0, 2]]))                  # moved along toward only

    def test_a_part_already_curved_keeps_its_own_profile_on_top_of_the_surface(self):
        xs = np.linspace(-1, 1, 21)
        bump = 0.1 * (1 - xs ** 2)
        pts = np.array([(x, 1.0 - b, 0.0) for x, b in zip(xs, bump)])                 # its underside bulges down
        out, _m = D.conform(pts, "-Y", pts[:, 1] - 0.0, gap=0.0)                      # onto a flat floor at y = 0
        self.assertTrue(np.allclose(out[:, 1], 0.1 - bump))                           # its lowest point on the floor

    def test_an_overhang_carries_on_level_and_is_counted(self):
        pts, _xs = self.strap()
        reach = pts[:, 1] - self.hill(pts[:, 0])
        off = pts[:, 0] > 0.5                                                         # the surface ends at x = 0.5
        reach[off] = np.nan
        out, missed = D.conform(pts, "-Y", reach)
        self.assertAlmostEqual(missed, float(off.mean()), places=9)
        edge = float(self.hill(0.5))
        under = np.isclose(pts[:, 1], 1.0) & off
        self.assertTrue(np.allclose(out[under, 1], edge, atol=1e-9))                  # level with the last point on it

    def test_what_is_not_allowed_is_said(self):
        pts, _xs = self.strap()
        with self.assertRaises(ValueError) as e:
            D.conform(pts, "-Y", np.full(len(pts), np.nan))
        self.assertIn("nothing of the part", str(e.exception))
        for kw in (dict(reach=np.zeros(3)), dict(gap="near"), dict(toward=(0, 0, 0))):
            args = {"toward": "-Y", "reach": np.ones(len(pts)), "gap": 0.0, **kw}
            with self.assertRaises(ValueError, msg=kw):
                D.conform(pts, args["toward"], args["reach"], args["gap"])


def blender(script, *args):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_deform"))
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(REPO, "kit", "selftest", "blender", script), "--", "--no-preview", *args],
                          cwd=REPO, capture_output=True, text=True, timeout=900, env=e, encoding="utf-8",
                          errors="replace")


def cases(*args):
    """check_deform_cases.py -> what it printed (nothing is built: seconds)"""
    r = blender("check_deform_cases.py", *args)
    line = next((x for x in r.stdout.splitlines() if x.startswith("DEFORM_CASES ")), None)
    assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
    return json.loads(line.split(" ", 1)[1])


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Cases(unittest.TestCase):
    R = 2.0 / (math.pi / 2)                                   # the radius of a 2 stud bar bent a quarter turn

    @classmethod
    def setUpClass(cls):
        cls.d = cases()
        cls.parts = cls.d["parts"]

    def near(self, got, want, tol=0.002):
        self.assertTrue(np.allclose(got, want, atol=tol), (got, want))

    def test_a_bar_bent_a_quarter_turn_is_a_quarter_circle(self):
        bar_ = self.parts["Bar"]
        self.near(bar_["lo"], (-0.1, 0.0, -0.1))
        self.near(bar_["hi"], (self.R, self.R + 0.1, 0.1))    # its end face at x = R, its outside at R + 0.1
        self.assertEqual(bar_["verts"], 8 + 8 * 4)            # sliced 8 times: nine pieces of 10 degrees

    def test_a_mirrored_part_bends_the_mirrored_way(self):
        r = 1.0 / (math.pi / 2)
        self.near(self.parts["Hook"]["lo"], (2.9, 0.0, -0.1))
        self.near(self.parts["Hook"]["hi"], (3 + r, r + 0.1, 0.1))
        self.near(self.parts["Hook~m1"]["hi"], (-2.9, r + 0.1, 0.1))                  # curls toward -X
        self.near(self.parts["Hook~m1"]["lo"], (-(3 + r), 0.0, -0.1))

    def test_a_twist_turns_the_top_a_quarter_and_the_middle_part_of_the_way(self):
        s_ = self.d["sections"]
        self.near(s_["drill_top"][:2], (0.1, 0.4))            # the 0.4 x 0.1 section, turned a quarter
        self.assertEqual(s_["drill_top"][2], 4)
        t = math.radians(90 * 4 / 9)                          # the fourth of its eight slices
        self.near(s_["drill_slice4"][:2], (0.4 * math.cos(t) + 0.1 * math.sin(t), 0.4 * math.sin(t) + 0.1 * math.cos(t)))

    def test_a_taper_and_a_profile(self):
        s_ = self.d["sections"]
        self.near(s_["spike_foot"][:2], (0.5, 0.5))
        self.near(s_["spike_top"][:2], (0.1, 0.1))            # end=0.2
        self.assertEqual(self.parts["Spike"]["verts"], 8)     # a straight taper needs no slice
        self.near(s_["vase_belly"][:2], (1.0, 1.0))           # twice as wide half way up
        self.near(s_["vase_top"][:2], (0.25, 0.25))
        self.assertEqual(self.parts["Vase"]["verts"], 12)     # one slice: at the belly

    def test_every_copy_of_a_row_is_deformed_about_its_own_middle(self):
        for k, name in enumerate(("Teeth", "Teeth~m1", "Teeth~m2", "Teeth~m3")):
            self.near(self.parts[name]["lo"], (-5.1 + 0.5 * k, 0.0, -3.1))            # its foot where it was
            self.near(self.parts[name]["hi"], (-4.9 + 0.5 * k, 0.6, -2.9))
        self.near(self.d["sections"]["tooth_top"][:2], (0.05, 0.05))                  # a copy's own tip, a quarter

    def test_a_plate_lies_on_the_dome_a_gap_off_it_and_keeps_its_thickness(self):
        pl = self.d["plate"]
        self.assertTrue(0.014 <= pl["above"][0] <= 0.0201, pl)                        # its underside: the gap above it
        self.assertAlmostEqual(pl["above"][1], 0.07, delta=0.004)                     # its top: its thickness more
        self.assertEqual(pl["under"], pl["top"])
        self.assertAlmostEqual(pl["thick"], 0.05, places=3)
        self.assertGreater(self.parts["Plate"]["verts"], 200)                         # sliced to follow the curve
        self.near(self.parts["Plate"]["lo"][::2], (-4.5, 2.5))                        # moved along toward only
        self.near(self.parts["Plate"]["hi"][::2], (-3.5, 3.5))

    def test_a_part_past_the_surfaces_edge_carries_on_level_and_the_share_is_said(self):
        lo, hi = self.d["tab"]["over_y"]
        self.assertTrue(0.1 < lo and hi < 0.5 and hi - lo < 0.15, (lo, hi))           # neither left up nor dropped
        fact = next(f for f in self.d["facts"] if f["part"] == "Tab")
        self.assertAlmostEqual(fact["past"], 0.5, delta=0.08)

    def test_the_facts_say_each_deform_in_order(self):
        self.assertEqual([(f["part"], f["said"]) for f in self.d["facts"][:8]],
                         [("Bar", "bend 90"), ("Hook", "bend 90"), ("Drill", "twist 90"), ("Spike", "taper 0.2"),
                          ("Vase", "taper by profile"), ("Teeth", "taper 0.25"), ("Plate", "onto Dome"),
                          ("Tab", "onto Dome")])
        self.assertEqual([f["slices"] for f in self.d["facts"][:6]], [8, 8, 8, 0, 1, 0])

    # ---- the faults the review of the first build found
    def test_a_deform_that_starts_half_way_is_sliced_there_and_leaves_the_lower_half_alone(self):
        r = self.d["review"]["half_taper"]
        self.near(r["foot"][:2], (0.4, 0.4))
        self.near(r["mid"][:2], (0.4, 0.4))                   # (the first build: 0.24 - the whole bar tapered)
        self.assertEqual(r["mid"][2], 4)                      # a section of its own at the start
        self.near(r["top"][:2], (0.08, 0.08))
        self.assertEqual(self.parts["HalfTaper"]["verts"], 12)
        stem = self.d["review"]["half_bend"]["stem"]
        self.near(stem["lo"], (7.9, 0.0, -0.1))               # below the bend: the bar as it was
        self.near(stem["hi"], (8.1, 1.0, 0.1))
        self.assertEqual(self.d["review"]["half_bend"]["ring"][2], 4)

    def test_a_twist_turns_the_way_the_maths_says(self):
        prism = np.array([(10.0, 0.0, 0.0), (10.4, 0.0, 0.0), (10.0, 0.0, 0.2), (10.0, 2.0, 0.0), (10.4, 2.0, 0.0),
                          (10.0, 2.0, 0.2)])
        want = sorted([round(float(c), 4) for c in p] for p in D.twist(prism, "Y", 90)[3:])
        self.near(self.d["review"]["prism_top"], want, 1e-3)  # (an off-centre section: the other way round is elsewhere)

    def test_naming_a_copy_is_refused_and_moves_nothing(self):
        self.assertIn('is a copy of "Hook"', self.d["errors"]["copy"])
        before, after = self.d["copy_kept"]
        self.assertEqual(before, after)                       # (the first build flung it round an axis 6 studs off)

    def test_a_floater_is_deformed_like_any_part(self):
        narrow, wide = sorted(self.d["review"]["patch_ends"])
        self.near((narrow, wide), (0.2, 0.4))

    def test_each_copy_is_laid_onto_what_is_under_it(self):
        pad, twin = self.d["review"]["pads"]["Pad"], self.d["review"]["pads"]["Pad~m1"]
        slope = math.tan(math.radians(10))
        # (the first build laid the copy as the part: 0.7 studs in the air above the low end of the ramp)
        self.assertAlmostEqual(abs(pad["lo"][1] - twin["lo"][1]), 4.0 * slope, delta=0.01)
        for p_ in (pad, twin):
            self.assertAlmostEqual(p_["hi"][1] - p_["lo"][1], 0.05 + 0.4 * slope, delta=0.01)   # lying along the slope

    def test_a_part_sunk_in_the_surface_is_brought_back_out_onto_it(self):
        inset = self.d["review"]["inset"]
        self.near((inset["lo"][1], inset["hi"][1]), (1.0, 1.1))   # (the first build: 0 .. 0.1, the block's underside)

    def test_the_share_past_the_edge_is_of_the_part_as_it_lies(self):
        fact = next(f for f in self.d["facts"] if f["part"] == "Tab10")
        self.assertTrue(0.05 < fact["past"] < 0.15, fact)     # (the first build said 0.5: of its eight corners)

    def test_what_is_not_allowed_is_said_and_cuts_nothing(self):
        e = self.d["errors"]
        self.assertIn('no part "Nobody"', e["unknown"])
        self.assertIn("cannot lie on itself", e["itself"])
        self.assertIn("nothing of the part", e["nothing"])
        self.assertIn("fold through itself", e["tight"])
        self.assertIn('along="W"', e["along"])
        self.assertEqual(self.d["stub_verts"][0], self.d["stub_verts"][1])            # refused before any slice

    def test_a_cad_parts_detailed_and_game_versions_bend_as_one_and_its_normals_turn_with_it(self):
        d = cases("--pair")
        self.near(d["low"]["lo"], d["high"]["lo"], 0.003)
        self.near(d["low"]["hi"], d["high"]["hi"], 0.003)
        self.assertGreater(d["low"]["hi"][0], 0.3)                                    # it did bend toward +X
        self.assertEqual(d["brep"][1], True)
        # the detailed version's own normals against its faces: a 60 degree bend left stale would be about 30 off
        # on average and 60 at the far end; turned with the surface they stay within a slice's half angle
        self.assertLess(d["after"]["high"][0], d["before"]["high"][0] + 4.0)
        self.assertLess(d["after"]["high"][1], d["before"]["high"][1] + 7.0)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Built(unittest.TestCase):
    def test_the_fixture_builds_and_says_what_it_deformed(self):
        r = blender("build_deform.py", "--geo")
        line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith('{"schema"')), None)
        self.assertTrue(r.returncode == 0 and line, (r.stderr or r.stdout)[-800:])
        rep = json.loads(line)
        self.assertEqual(rep["status"], "pass", rep["summary"])
        self.assertIn("deformed: Horn (taper 0.15, twist 120, bend 70), Strap (onto Body)", rep["summary"])
        self.assertEqual([f["kind"] for f in rep["facts"]["deforms"]], ["conform", "taper", "twist", "bend"])


if __name__ == "__main__":
    unittest.main()
