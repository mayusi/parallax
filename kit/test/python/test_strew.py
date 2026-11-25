"""SCATTER (kit/blender/rbx_strew.py, rbx.Asset.scatter): pieces spread over a surface - by area, never two
closer than the pitch, the same on every build; each stood on the surface with its up along the surface's own,
spun at random or laid along a nap."""

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
import rbx_strew as W  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()

FLOOR = W.triangles([(0, 0, 0), (4, 0, 0), (4, 0, 2), (0, 0, 2)], [[0, 3, 2, 1]])      # 4 x 2, facing +Y
WALL = W.triangles([(0, 0, 0), (0, 2, 0), (0, 2, 2), (0, 0, 2)], [[0, 3, 2, 1]])       # 2 x 2, facing -X
SMALL = W.triangles([(10, 0, 0), (11, 0, 0), (11, 0, 1), (10, 0, 1)], [[0, 3, 2, 1]])  # 1 x 1


def closest(pts):
    d = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=2)
    return float((d + np.eye(len(pts)) * 1e9).min())


class Sample(unittest.TestCase):
    def test_none_closer_than_the_pitch_and_as_many_as_fit(self):
        pts, nrm, used = W.sample(FLOOR, pitch=0.25)
        self.assertGreaterEqual(closest(pts), 0.25)
        self.assertEqual(used, 0.25)
        self.assertTrue(55 <= len(pts) <= 128, len(pts))            # 8 square studs: well filled, never a grid's 128+
        self.assertTrue(np.allclose(pts[:, 1], 0) and (pts[:, 0] >= 0).all() and (pts[:, 0] <= 4).all()
                        and (pts[:, 2] >= 0).all() and (pts[:, 2] <= 2).all())       # on the surface
        self.assertTrue(np.allclose(nrm, (0, 1, 0)))

    def test_a_count_is_met_and_spread_out(self):
        pts, _n, used = W.sample(FLOOR, count=30)
        self.assertEqual(len(pts), 30)
        self.assertGreaterEqual(closest(pts), used - 1e-9)
        self.assertGreater(used, 0.2)                               # 30 on 8 square studs: no two side by side
        halves = (pts[:, 0] < 2).sum()
        self.assertTrue(9 <= halves <= 21, halves)                  # over the whole of it, not in one corner

    def test_a_count_with_a_pitch_that_cannot_hold_it_gives_fewer(self):
        pts, _n, _u = W.sample(SMALL, count=50, pitch=0.5)
        self.assertLess(len(pts), 12)                               # (the caller says so: it never crowds them)
        self.assertGreaterEqual(closest(pts), 0.5)

    def test_spread_by_area(self):
        both = np.concatenate([FLOOR, SMALL])                       # 8 square studs and 1
        pts, _n, _u = W.sample(both, pitch=0.2, seed="area")
        on_small = int((pts[:, 0] >= 10).sum())
        self.assertAlmostEqual(on_small / len(pts), 1 / 9, delta=0.05)

    def test_where_picks_the_faces(self):
        both = np.concatenate([FLOOR, WALL])
        pts, nrm, _u = W.sample(both, pitch=0.2, where=lambda c, n: n[1] > 0.5)      # only what faces up
        self.assertTrue(np.allclose(nrm, (0, 1, 0)) and len(pts) > 20)
        with self.assertRaises(ValueError) as e:
            W.sample(both, pitch=0.2, where=lambda c, n: False)
        self.assertIn("no surface", str(e.exception))

    def test_the_same_on_every_build_and_its_own_per_seed(self):
        a, _n, _u = W.sample(FLOOR, count=20, seed="Roof/Shingle")
        b, _n, _u = W.sample(FLOOR, count=20, seed="Roof/Shingle")
        c, _n, _u = W.sample(FLOOR, count=20, seed="Roof/Moss")
        self.assertTrue(np.array_equal(a, b))
        self.assertFalse(np.array_equal(a, c))

    def test_the_two_sides_of_a_thin_part_do_not_crowd_each_other(self):
        # a plate 0.02 thick: a piece on its top and one on its underside can never touch
        top = W.triangles([(0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2)], [[0, 3, 2, 1]])
        under = W.triangles([(0, -0.02, 0), (2, -0.02, 0), (2, -0.02, 2), (0, -0.02, 2)], [[0, 1, 2, 3]])
        alone, _n, _u = W.sample(top, pitch=0.2, seed="plate")
        both, nrm, _u = W.sample(np.concatenate([top, under]), pitch=0.2, seed="plate")
        on_top = int((nrm[:, 1] > 0).sum())
        self.assertGreater(on_top, 0.85 * len(alone))                # (the first build: half as many)
        self.assertGreater(len(both) - on_top, 0.85 * len(alone))

    def test_a_long_narrow_strip_is_filled_along_its_length(self):
        strip = W.triangles([(0, 0, 0), (40, 0, 0), (40, 0, 0.01), (0, 0, 0.01)], [[0, 3, 2, 1]])
        pts, _n, _u = W.sample(strip, pitch=1.0)
        self.assertGreater(len(pts), 25)                             # 40 long: about 30 fit (the first build: a few)

    def test_negative_places_keep_their_distance_too(self):
        low = W.triangles([(-3, -1, -3), (0.5, -1, -3), (0.5, -1, 0.5), (-3, -1, 0.5)], [[0, 3, 2, 1]])
        pts, _n, _u = W.sample(low, pitch=0.3)
        self.assertGreaterEqual(closest(pts), 0.3)
        self.assertGreater(len(pts), 50)

    def test_a_margin_keeps_points_off_the_picked_faces_border(self):
        pts, _n, _u = W.sample(FLOOR, pitch=0.2, margin=0.5)         # 4 x 2: only the middle 3 x 1
        self.assertTrue((pts[:, 0] >= 0.5).all() and (pts[:, 0] <= 3.5).all())
        self.assertTrue((pts[:, 2] >= 0.5).all() and (pts[:, 2] <= 1.5).all())
        self.assertGreater(len(pts), 20)
        cube = W.triangles([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
                           [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [2, 3, 7, 6], [1, 2, 6, 5], [0, 4, 7, 3]])
        free, _n, _u = W.sample(cube, pitch=0.2, margin=0.3)         # a closed surface has no border
        self.assertTrue((np.abs(free - 0.5).max(axis=1) > 0.49).all() and len(free) > 40)
        for bad in (-0.1, "wide", float("nan")):
            with self.assertRaises(ValueError, msg=bad):
                W.sample(FLOOR, pitch=0.2, margin=bad)
        with self.assertRaises(ValueError) as e:
            W.sample(FLOOR, pitch=0.2, margin=3.0)
        self.assertIn("leaves no room", str(e.exception))

    def test_what_is_not_allowed_is_said(self):
        with self.assertRaises(ValueError) as e:
            W.sample(FLOOR, pitch=0.3, where=lambda c, n: np.array([True, False]))
        self.assertIn("True or False", str(e.exception))
        for kw in ({}, dict(count=0), dict(count=2.5), dict(count="some"), dict(count=W.MAX_POINTS + 1),
                   dict(count=float("inf")), dict(pitch=0), dict(pitch=-1), dict(pitch="near"),
                   dict(pitch=float("nan"))):
            with self.assertRaises(ValueError, msg=kw):
                W.sample(FLOOR, **kw)
        with self.assertRaises(ValueError) as e:
            W.sample(FLOOR, pitch=0.02)                             # thousands: more than a build can carry
        self.assertIn("more than", str(e.exception))


class Placements(unittest.TestCase):
    def test_each_piece_stands_on_its_point_with_its_up_along_the_surface(self):
        pts = np.array([(1.0, 0, 1.0), (0, 1.0, 1.0)])
        nrm = np.array([(0.0, 1, 0), (-1.0, 0, 0)])
        ms = W.placements(pts, nrm)
        for m, p, n in zip(ms, pts, nrm):
            self.assertTrue(np.allclose(m[:3, 3], p))                                 # its origin on the point
            self.assertTrue(np.allclose(m[:3, :3] @ np.array([0, 1.0, 0]), n))        # its up: the surface's
            self.assertAlmostEqual(float(np.linalg.det(m[:3, :3])), 1.0, places=9)    # turned, never squashed

    def test_spun_at_random_or_left_as_it_fell(self):
        pts = np.zeros((12, 3))
        nrm = np.tile((0.0, 1, 0), (12, 1))
        spun = [m[:3, :3] @ np.array([0, 0, 1.0]) for m in W.placements(pts, nrm)]
        self.assertGreater(len({tuple(np.round(v, 3)) for v in spun}), 8)             # every which way
        still = W.placements(pts, nrm, spin=False)
        self.assertTrue(all(np.allclose(m[:3, :3], np.eye(3)) for m in still))
        again = [m[:3, :3] @ np.array([0, 0, 1.0]) for m in W.placements(pts, nrm)]
        self.assertTrue(np.allclose(spun, again))                                     # the same on every build

    def test_a_nap_lays_every_piece_the_same_way_down_the_surface(self):
        # a roof sloping down toward +Z: shingles' fronts (+Z) run down the slope, whatever each one's place
        n = np.array([0.0, math.cos(math.radians(35)), math.sin(math.radians(35))])
        pts = np.array([(0.0, 0, 0), (1.0, 0.3, 0.2), (2.0, -0.2, 0.5)])
        ms = W.placements(pts, np.tile(n, (3, 1)), facing=(0, -1, 0))
        down = np.array([0.0, -1, 0]) - n * float(np.array([0.0, -1, 0]) @ n)
        down /= np.linalg.norm(down)
        for m in ms:
            self.assertTrue(np.allclose(m[:3, :3] @ np.array([0, 0, 1.0]), down, atol=1e-9))
            self.assertTrue(np.allclose(m[:3, :3] @ np.array([0, 1.0, 0]), n, atol=1e-9))
        flat = W.placements(pts[:1], np.array([(0.0, 1, 0)]), facing=(0, -1, 0))      # straight off the surface:
        self.assertTrue(np.allclose(flat[0][:3, :3], np.eye(3)))                      # left as it fell

    def test_a_surface_that_faces_straight_down_still_gets_a_piece_the_right_way_out(self):
        m = W.placements(np.zeros((1, 3)), np.array([(0.0, -1.0, 0.0)]), spin=False)[0]
        self.assertTrue(np.allclose(m[:3, :3] @ np.array([0, 1.0, 0]), (0, -1, 0)))   # its up: out of the surface
        self.assertAlmostEqual(float(np.linalg.det(m[:3, :3])), 1.0, places=9)        # turned, not mirrored

    def test_what_is_not_allowed_is_said(self):
        for bad in ((0, 0, 0), "down", (1, 2), (float("nan"), 0, 0)):
            with self.assertRaises(ValueError, msg=bad):
                W.placements(np.zeros((1, 3)), np.array([(0.0, 1, 0)]), facing=bad)
        with self.assertRaises(ValueError):
            W.placements(np.zeros((2, 3)), np.array([(0.0, 1, 0)]))


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_strew"))
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(REPO, "kit", "selftest", "blender", "build_strew.py"), "--", "--no-preview",
                            "--geo", "--report"], cwd=REPO, capture_output=True, text=True, timeout=900, env=e,
                           encoding="utf-8", errors="replace")
        line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith('{"schema"')), None)
        parts = next((x for x in r.stdout.splitlines() if x.startswith("STREW_PARTS ")), None)
        assert r.returncode == 0 and line and parts, (r.stderr or r.stdout)[-800:]
        cls.report, cls.said = json.loads(line), json.loads(parts.split(" ", 1)[1])
        cls.parts = cls.said["parts"]

    def pieces(self, name):
        return [v for k, v in self.parts.items() if k.split("~")[0] == name]

    def test_the_build_passes_and_says_what_it_scattered(self):
        self.assertEqual(self.report["status"], "pass", self.report["summary"])
        self.assertIn("repeats: Rivet x24 (scatter on Dome x24), Shingle x12 (scatter on Roof x12)",
                      self.report["summary"])
        self.assertEqual([(r["onto"], r["pieces"]) for r in self.report["facts"]["scatters"]],
                         [(["Roof"], 12), (["Dome"], 24)])
        self.assertNotIn("asked", self.report["facts"]["scatters"][0])               # all twelve fitted

    def test_every_piece_is_on_its_surface_the_part_itself_too(self):
        rivets = self.pieces("Rivet")
        self.assertEqual(len(rivets), 24)
        for r in rivets:                                            # none left at the origin, where it was modelled
            mid = [(a + b) / 2 for a, b in zip(r["lo"], r["hi"])]
            away = math.dist(mid, (1.4, 0.2, 0.0))
            self.assertTrue(0.695 < away < 0.73, (mid, away))       # OUTSIDE the dome's skin (radius 0.7), a little sunk
            self.assertGreater(mid[1], 0.3)                         # only where where= said: its upper part
        shingles = self.pieces("Shingle")
        self.assertEqual(len(shingles), 12)
        for s_ in shingles:
            mid = [(a + b) / 2 for a, b in zip(s_["lo"], s_["hi"])]
            self.assertTrue(-2.2 < s_["lo"][0] and s_["hi"][0] < -0.2, s_)            # none over the roof's sides
            self.assertTrue(-1.0 < s_["lo"][2] and s_["hi"][2] < 1.0, s_)             # nor over its eaves or ridge
            # on its slope: the wedge's top runs from y = 0.2 at its front (z = -1) to 1.0 at its back (z = +1);
            # a slate 0.02 thick sunk 0.004 has its middle 0.006 ABOVE the slope along its normal (never below)
            above = (mid[1] - (0.6 + 0.4 * mid[2])) * math.cos(math.atan2(0.8, 2.0))
            self.assertAlmostEqual(above, 0.006, delta=0.003)
        mids = [[(a + b) / 2 for a, b in zip(s_["lo"], s_["hi"])] for s_ in shingles]
        gaps = [math.dist(p, q) for i, p in enumerate(mids) for q in mids[i + 1:]]
        self.assertGreaterEqual(min(gaps), 0.36 - 1e-3)                               # none on another

    def test_a_shingle_lies_along_the_slope_not_flat_and_not_upright(self):
        tall = [s_["hi"][1] - s_["lo"][1] for s_ in self.pieces("Shingle")]
        # 0.28 long down a slope of 21.8 degrees: it rises 0.28 * sin + its 0.02 thickness * cos, every one alike
        want = 0.28 * math.sin(math.atan2(0.8, 2.0)) + 0.02 * math.cos(math.atan2(0.8, 2.0))
        self.assertTrue(all(abs(t - want) < 0.01 for t in tall), (min(tall), max(tall), want))


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Cases(unittest.TestCase):
    """every case is a fault the review of the first build found (2026-11-13)"""

    @classmethod
    def setUpClass(cls):
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_strew"))
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(REPO, "kit", "selftest", "blender", "check_strew_cases.py"), "--",
                            "--no-preview"], cwd=REPO, capture_output=True, text=True, timeout=900, env=e,
                           encoding="utf-8", errors="replace")
        line = next((x for x in r.stdout.splitlines() if x.startswith("STREW_CASES ")), None)
        assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
        cls.d = json.loads(line.split(" ", 1)[1])

    def test_inside_a_frame_the_pieces_are_on_the_surface(self):
        away = [math.dist(m, (-6, 1, -6)) for m in self.d["fstud"]]
        self.assertEqual(len(away), 10)
        self.assertTrue(all(0.515 < d_ < 0.53 for d_ in away), away)      # (the first build: 8.6 studs off)

    def test_inside_a_repeat_every_copy_of_the_part_gets_its_own_pieces(self):
        r = self.d["rstud"]
        self.assertEqual(len(r), 36)
        for k in range(3):
            near = [m for m in r if math.dist(m, (1.5 * k, 0, 6)) < 0.44]
            self.assertEqual(len(near), 12, k)                            # (the first build: 12 pieces in the air)
            self.assertTrue(all(math.dist(m, (1.5 * k, 0, 6)) > 0.41 for m in near))   # outside its skin

    def test_inside_a_mirror_each_side_gets_what_was_asked_and_the_facts_say_it(self):
        m = self.d["mstud"]
        self.assertEqual(len(m), 40)
        for x in (3, -3):
            side = [q for q in m if math.dist(q, (x, 0, -6)) < 0.44]
            self.assertEqual(len(side), 20)
            gaps = [math.dist(p, q) for i, p in enumerate(side) for q in side[i + 1:]]
            self.assertGreaterEqual(min(gaps), self.d["m_fact"]["pitch"] - 0.01)      # (the first build: crowded)
        self.assertEqual(self.d["m_fact"]["pieces"], 20)

    def test_a_deform_and_a_zone_read_a_scattered_piece_as_it_was_modelled(self):
        self.assertEqual(self.d["zoned"], 1)
        self.assertEqual(len(self.d["spikes"]), 8)
        for s_ in self.d["spikes"]:
            self.assertAlmostEqual(s_["tall"], 0.3, delta=0.003)          # (the first build: 0.23, mangled)
            self.assertLess(s_["tip"], 0.02)                              # tapered to a fifth: 0.012 across
            self.assertGreater(s_["foot"], 0.055)                         # its foot as it was: 0.06 across
            self.assertEqual(s_["zoned"], 1)                              # its own top face - on every spike
            self.assertAlmostEqual(s_["zone_at"], s_["far"], delta=0.002)   # ... which is its outer end

    def test_a_varied_piece_still_stands_on_the_surface(self):
        lows = [s_[0] for s_ in self.d["stones"]]
        self.assertEqual(len(lows), 20)
        self.assertTrue(all(abs(v) < 1e-4 for v in lows), lows)           # (the first build: -0.097 .. +0.098)
        tops = [s_[1] for s_ in self.d["stones"]]
        self.assertGreater(max(tops) - min(tops), 0.1)                    # and they really differ in size

    def test_a_margin_keeps_pieces_off_the_edge(self):
        t = self.d["tiles"]
        self.assertGreater(len(t), 15)
        self.assertTrue(all(abs(q[0] + 6) <= 0.7 + 1e-3 and abs(q[2] - 6) <= 0.7 + 1e-3 for q in t))

    def test_fewer_than_asked_is_said(self):
        self.assertEqual(self.d["few"]["asked"], 50)
        self.assertEqual(self.d["few"]["pieces"], self.d["few_made"])
        self.assertLess(self.d["few_made"], 50)

    def test_what_is_not_allowed_is_said(self):
        e = self.d["errors"]
        self.assertIn("INTO the surface", e["sink"])
        self.assertIn("margin=", e["margin"])
        self.assertIn("leaves no room", e["room"])
        self.assertIn("is scattered", e["conform"])
        self.assertEqual(self.d["open_after"], 0)


if __name__ == "__main__":
    unittest.main()
