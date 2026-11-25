"""SWEEP (kit/blender/rbx_sweep.py, rbx.Asset.sweep): a section carried along a path - proven on solids whose
volume is known (a cylinder, a cone, a mitred bar, a picture frame, a torus), on its frames (carried without
rolling, a loop meeting itself) and on what it refuses."""

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
import rbx_sweep as S  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()

SQ = [(-0.1, -0.1), (0.1, -0.1), (0.1, 0.1), (-0.1, 0.1)]


def closed(verts, faces):
    """every edge used by exactly two faces, once each way (a closed, consistently wound mesh)"""
    seen = {}
    for f in faces:
        for a, b in zip(f, f[1:] + f[:1]):
            seen[(a, b)] = seen.get((a, b), 0) + 1
    return all(n == 1 for n in seen.values()) and all((b, a) in seen for a, b in seen)


class Section(unittest.TestCase):
    def test_a_radius_is_a_regular_polygon_with_a_flat_side_down(self):
        o = S.outline(0.5, 8)
        self.assertEqual(o.shape, (8, 2))
        self.assertTrue(np.allclose(np.linalg.norm(o, axis=1), 0.5))
        self.assertAlmostEqual(float(o[0, 1]), float(o[-1, 1]), places=9)             # the lowest side is level
        self.assertAlmostEqual(float(o[:, 1].min()), float(o[0, 1]), places=9)

    def test_an_outline_is_turned_counter_clockwise(self):
        a, b = S.outline(SQ), S.outline(SQ[::-1])
        for o in (a, b):
            area = 0.5 * float(np.sum(o[:, 0] * np.roll(o[:, 1], -1) - np.roll(o[:, 0], -1) * o[:, 1]))
            self.assertAlmostEqual(area, 0.04, places=12)

    def test_what_is_not_allowed_is_said(self):
        for bad in (0, -1, float("nan"), "round", [(0, 0), (1, 0)], [(0, 0), (1, 0), (2, 0)], [(0, 0), (0, 0), (1, 1)],
                    [(0, 0, 0), (1, 0, 0), (0, 1, 0)]):
            with self.assertRaises(ValueError, msg=bad):
                S.outline(bad)
        for sides in (2, 2.5, "many", S.MAX_SIDES + 1):
            with self.assertRaises(ValueError, msg=sides):
                S.outline(0.5, sides)


class Solids(unittest.TestCase):
    def test_a_straight_round_sweep_is_a_cylinder(self):
        v, f = S.solid([(0, 0, 0), (0, 0, 2)], 0.5, sides=64)
        self.assertTrue(closed(v, f))
        self.assertAlmostEqual(S.volume(v, f), 64 * 0.5 * 0.25 * math.sin(2 * math.pi / 64) * 2, places=9)
        self.assertEqual(len(v), 128)                                                 # two rings: nothing between

    def test_a_scale_of_nothing_at_an_end_is_a_point(self):
        v, f = S.solid([(0, 0, 0), (0, 0, 2)], 0.5, sides=64, scale=[(0, 1), (1, 0)])
        self.assertTrue(closed(v, f))
        self.assertEqual(len(v), 65)                                                  # a ring and its tip
        self.assertAlmostEqual(S.volume(v, f), 64 * 0.5 * 0.25 * math.sin(2 * math.pi / 64) * 2 / 3, places=9)
        both, f2 = S.solid([(0, 0, 0), (0, 0, 2)], 0.5, sides=8, scale=[(0, 0), (0.5, 1), (1, 0)])
        self.assertTrue(closed(both, f2))
        self.assertEqual(len(both), 10)                                               # a point, a ring, a point

    def test_a_corner_is_mitred_so_both_legs_keep_their_size(self):
        v, f = S.solid([(0, 0, 0), (2, 0, 0), (2, 0, 2)], SQ, smooth=False)
        self.assertTrue(closed(v, f))
        self.assertAlmostEqual(S.volume(v, f), 0.04 * 4, places=9)                    # two legs of 2, no more, no less
        self.assertEqual(len(v), 12)
        corner = v[4:8]
        self.assertTrue(np.allclose(corner[:, 0] + corner[:, 2], 2.0, atol=1e-9))     # on the corner's mitre plane

    def test_a_rail_that_leaves_its_plane_does_not_turn_along_a_straight_leg(self):
        # (the first build carried the section from corner to corner in one turn: 19.5 degrees of twist along the
        # middle leg here, and 4% of the bar's volume gone)
        v, f = S.solid([(0, 0, 0), (2, 0, 0), (2, 0, 2), (2, 2, 2)], SQ, smooth=False)
        self.assertTrue(closed(v, f))
        self.assertAlmostEqual(S.volume(v, f), 0.04 * 6, places=9)                    # three legs of 2: a true prism
        a_, b_ = v[4:8], v[8:12]                                                      # the middle leg's two ends
        along = np.array([0.0, 0.0, 1.0])
        for p_, q_ in zip(a_, b_):
            run = q_ - p_
            self.assertTrue(np.allclose(run - along * float(run @ along), 0, atol=1e-9))   # every edge straight along it
        helix = [(math.cos(t), 0.4 * t, math.sin(t)) for t in np.linspace(0, 4, 9)]
        v, f = S.solid(helix, SQ, smooth=False)
        length = sum(math.dist(p_, q_) for p_, q_ in zip(helix, helix[1:]))
        self.assertAlmostEqual(S.volume(v, f), 0.04 * length, places=9)

    def test_the_outline_is_drawn_as_seen_from_the_paths_end_looking_back(self):
        ell = [(-0.1, 0), (0.1, 0), (0.1, 0.05), (-0.05, 0.05), (-0.05, 0.2), (-0.1, 0.2)]   # an L: foot to +x, post up
        v, _f = S.solid([(0, 0, 0), (0, 0, 1)], ell)                                  # along +Z (the model's back)
        self.assertAlmostEqual(float(v[:, 1].max()), 0.2, places=9)                   # its post: up
        self.assertAlmostEqual(float(v[v[:, 1] > 0.1][:, 0].max()), -0.05, places=9)  # the post on the -x side
        self.assertAlmostEqual(float(v[:, 0].max()), 0.1, places=9)                   # the foot reaches +x
        v, _f = S.solid([(0, 0, 0), (1, 0, 0)], ell)                                  # along +X: its right is -Z
        self.assertAlmostEqual(float(v[v[:, 1] > 0.1][:, 2].min()), 0.05, places=9)
        up, _f = S.solid([(0, 0, 0), (0, 2, 0)], ell)                                 # straight up: its up is +Z
        self.assertAlmostEqual(float(up[:, 2].max()), 0.2, places=9)

    def test_a_closed_path_is_a_frame_with_no_ends(self):
        v, f = S.solid([(0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2)], SQ, smooth=False, closed=True)
        self.assertTrue(closed(v, f))
        self.assertEqual((len(v), len(f)), (16, 16))                                  # four rings, four sides each
        self.assertAlmostEqual(S.volume(v, f), 0.04 * 8, places=9)
        again, f2 = S.solid([(0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2), (0, 0, 0)], SQ, smooth=False)
        self.assertTrue(np.allclose(v, again) and f == f2)                            # given closed: the same

    def test_a_circle_swept_round_is_a_torus(self):
        circ = [(math.cos(a), 0, math.sin(a)) for a in np.linspace(0, 2 * math.pi, 48, endpoint=False)]
        v, f = S.solid(circ, 0.2, closed=True, sides=48)
        self.assertTrue(closed(v, f))
        self.assertAlmostEqual(S.volume(v, f), 2 * math.pi ** 2 * 0.04, delta=0.01)
        self.assertTrue(np.allclose(np.abs(v[:, 1]).max(), 0.2, atol=0.002))          # it did not roll or lean

    def test_a_profile_changes_the_size_on_the_way_and_two_numbers_the_two_ways_apart(self):
        v, f = S.solid([(0, 0, 0), (0, 0, 1)], SQ, scale=[(0, 1), (0.5, 2), (1, 1)])
        self.assertTrue(closed(v, f))
        self.assertEqual(len(v), 12)                                                  # a station at the profile's point
        self.assertTrue(np.allclose(np.abs(v[4:8, :2]).max(axis=0), (0.2, 0.2)))
        self.assertAlmostEqual(S.volume(v, f), 2 * 0.5 * (0.04 + 0.16 + math.sqrt(0.04 * 0.16)) / 3, places=9)
        flat, _f = S.solid([(0, 0, 0), (0, 0, 1)], SQ, scale=[(0, (1, 1)), (1, (3, 0.5))], up=(0, 1, 0))
        self.assertTrue(np.allclose(np.abs(flat[4:8]).max(axis=0)[:2], (0.3, 0.05)))  # wider and thinner

    def test_a_curve_gets_a_station_where_it_has_turned_and_at_every_point_given(self):
        circ = [(math.cos(t), 0, math.sin(t)) for t in np.linspace(0, 2 * math.pi, 16, endpoint=False)]
        place, ways, shares, loop, _m, legs = S.stations(circ, closed=True)
        self.assertTrue(loop)
        self.assertTrue(32 <= len(place) <= 64, len(place))                           # 360 degrees: about 10 a station
        self.assertLess(float(np.degrees(S._turns(legs).max())), 13.0)                # none much over it
        for p_ in circ:
            self.assertLess(float(np.linalg.norm(place - np.array(p_), axis=1).min()), 1e-9)   # through every point
        line, *_rest = S.stations([(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)])
        self.assertEqual(len(line), 4)                                                # a straight run: its points only

    def test_a_twist_turns_the_section_about_the_path(self):
        v, f = S.solid([(0, 0, 0), (0, 0, 1)], SQ, twist=90, up=(0, 1, 0))
        self.assertTrue(closed(v, f))
        self.assertEqual(len(v), 4 * 10)                                              # a station every 10 degrees
        first = v[:4]
        for k in range(10):                                                           # each ring: the first, turned
            t = math.radians(10 * k)
            c, s = math.cos(t), math.sin(t)
            want = np.stack([first[:, 0] * c - first[:, 1] * s, first[:, 0] * s + first[:, 1] * c,
                             np.full(4, k / 9)], axis=1)
            self.assertTrue(np.allclose(v[4 * k: 4 * k + 4], want), k)
        # (flat triangles between turned squares cut a little inside the true twisted bar: 0.04 less a few percent)
        self.assertTrue(0.04 * 0.92 < S.volume(v, f) < 0.04)


class Frames(unittest.TestCase):
    def test_carried_round_a_corner_without_rolling(self):
        place, ways, shares, loop, _m, legs = S.stations([(0, 0, 0), (2, 0, 0), (2, 0, 2)], smooth=False)
        side, up = S.frames(ways, None, False, legs)
        self.assertTrue(np.allclose(up, (0, 1, 0)))                                   # its top stays up
        self.assertTrue(np.allclose(np.cross(side, up), ways))                        # side x up = the way it runs
        self.assertFalse(loop)
        self.assertTrue(np.allclose(shares, (0, 0.5, 1)))

    def test_a_path_straight_up_takes_another_up_and_a_bad_one_is_said(self):
        _p, ways, *_rest = S.stations([(0, 0, 0), (0, 3, 0)])
        _side, up = S.frames(ways)
        self.assertTrue(np.allclose(up[0], (0, 0, 1)))
        for bad in ((0, 1, 0), (0, 0, 0), "up", (1, 2)):
            with self.assertRaises(ValueError, msg=bad):
                S.frames(ways, bad)

    def test_a_loop_out_of_one_plane_meets_itself(self):
        # a trefoil knot: carried round it without rolling, the frame comes home 128 degrees turned; that is taken
        # back out evenly along the loop, so the join is a step like any other
        pts = [(math.sin(t) + 2 * math.sin(2 * t), math.cos(t) - 2 * math.cos(2 * t), -math.sin(3 * t))
               for t in np.linspace(0, 2 * math.pi, 24, endpoint=False)]
        place, ways, _s, loop, _m, legs = S.stations(pts, closed=True)
        self.assertTrue(loop)

        def join(ups):
            back = S._carry(S._carry(ups[-1], ways[-1], legs[-1]), legs[-1], ways[0])
            return math.degrees(math.acos(max(-1.0, min(1.0, float(back @ ups[0])))))

        _side, plain = S.frames(ways, None, False, legs)
        self.assertGreater(join(plain), 90.0)                                         # (it really comes home turned)
        _side, up = S.frames(ways, None, True, legs)
        self.assertLess(join(up), 3.0)                                                # no jump at the join
        v, f = S.solid(pts, 0.08, closed=True)
        self.assertTrue(closed(v, f))
        self.assertGreater(S.volume(v, f), 0)


class Folding(unittest.TestCase):
    def test_a_wide_section_round_a_gentle_arc_is_not_refused(self):
        # (the first build's check read a bend at the path's END that the part does not have, and refused these)
        arc = [(math.cos(t), 0, math.sin(t)) for t in np.linspace(0, math.pi / 2, 24)]
        for r in (0.5, 0.75, 0.9):
            v, f = S.solid(arc, r, sides=8)
            self.assertTrue(closed(v, f) and S.volume(v, f) > 0, r)

    def test_no_edge_of_a_made_part_runs_back_along_its_path(self):
        rng = np.random.default_rng(7)
        made = 0
        for _ in range(120):
            pts = rng.uniform(-2, 2, (int(rng.integers(3, 6)), 3))
            try:
                v, f = S.solid(pts, float(rng.uniform(0.02, 0.12)), sides=4)
            except ValueError:
                continue
            made += 1
            place, _w, _s, _l, _m, legs = S.stations(pts)
            rings = v.reshape(-1, 4, 3)
            for i in range(len(rings) - 1):
                self.assertGreater(float(((rings[i + 1] - rings[i]) @ legs[i]).min()), 0.0)
        self.assertGreater(made, 30)


class Refused(unittest.TestCase):
    def test_what_is_not_allowed_is_said(self):
        line = [(0, 0, 0), (0, 0, 1)]
        circ = [(math.cos(a), 0, math.sin(a)) for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)]
        for kw, word in (
                (dict(points=[(0, 0, 0)], section=0.1), "two or more points"),
                (dict(points=[(0, 0, 0), (0, 0, 0)], section=0.1), "same place"),
                (dict(points=line, section=0.3, scale=[(0, 1), (0.5, 0), (1, 1)]), "only an END"),
                (dict(points=line, section=0.3, scale=-1), "under 0"),
                (dict(points=line, section=0.3, scale=[(0, 1)]), "scale="),
                (dict(points=line, section=0.3, twist="lots"), "twist="),
                (dict(points=circ, section=0.2, closed=True, twist=90), "whole number of turns"),
                (dict(points=circ, section=0.2, closed=True, scale=[(0, 1), (1, 0)]), "no end for a point"),
                (dict(points=circ, section=0.2, closed=True, scale=[(0, 1), (1, 0.5)]), "end as it began"),
                (dict(points=[(0, 0, 0), (1, 0, 0), (1, 0, 0.2), (0, 0, 0.2)], section=0.3), "fold through itself"),
                # (a fold the first build's check missed: the turn falls between two stations)
                (dict(points=[[-0.96, -0.05, -1.78], [-0.49, 0.26, -0.95], [1.04, 1.8, -0.94]], section=0.5, sides=4),
                 "fold through itself"),
                # a leg too short for its two mitres (the first build made it, folded)
                (dict(points=[(-1, 0, 0), (0, 0, 0), (-0.1732, 0, 0.1)], section=SQ, smooth=False), "fold through"),
                (dict(points=line, section=0.3, scale=0), "0 everywhere"),
                (dict(points=line, section=0.3, scale=[(0, 0), (1, 0)]), "0 everywhere"),
                (dict(points=line, section=0.3, scale=[(0, (1, 1)), (1, (1, 0))]), "one way only"),
                (dict(points=line, section=0.3, twist=20000), "fifty turns"),
                (dict(points=[(0, 0, 0), (1, 0, 0), (0.1, 0, 0.05)], section=0.05, smooth=False), "too sharp"),
                (dict(points=[(0, 0, 0), (1, 0, 0), (1, 0, 1)], section=0.1, closed=True, smooth=False, up=(1, 0, 1)),
                 None),
        ):
            if word is None:
                S.solid(**kw)                                                         # (a triangle loop: fine)
                continue
            with self.assertRaises(ValueError, msg=kw) as e:
                S.solid(**kw)
            self.assertIn(word, str(e.exception), kw)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_sweep"))
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(REPO, "kit", "selftest", "blender", "build_sweep.py"), "--", "--no-preview",
                            "--geo", "--report"], cwd=REPO, capture_output=True, text=True, timeout=900, env=e,
                           encoding="utf-8", errors="replace")
        line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith('{"schema"')), None)
        parts = next((x for x in r.stdout.splitlines() if x.startswith("SWEEP_PARTS ")), None)
        assert r.returncode == 0 and line and parts, (r.stderr or r.stdout)[-800:]
        cls.report, cls.said = json.loads(line), json.loads(parts.split(" ", 1)[1])

    def test_the_build_passes_and_says_what_it_swept(self):
        self.assertEqual(self.report["status"], "pass", self.report["summary"])
        self.assertIn("swept: Horn, Rail, Ring, Strap", self.report["summary"])
        self.assertEqual([r["part"] for r in self.report["facts"]["sweeps"]], ["Horn", "Rail", "Ring", "Strap"])

    def test_the_parts_are_the_solids_the_numbers_say(self):
        by = {r["part"]: r for r in self.said["sweeps"]}
        parts = self.said["parts"]
        for name, row in by.items():
            self.assertEqual(parts[name]["verts"], row["verts"], name)                # nothing merged, nothing lost
            self.assertGreater(row["volume"], 0, name)                                # wound outward
        self.assertTrue(by["Ring"]["closed"] and not by["Horn"]["closed"])
        self.assertAlmostEqual(by["Rail"]["volume"], 0.0272 * 4.8, places=4)          # its section's area x both legs
        self.assertTrue(np.allclose(parts["Horn"]["hi"], (-0.4, 1.8, -0.6), atol=1e-3))   # its tip: the path's end
        self.assertTrue(np.allclose(parts["Rail"]["lo"], (-1.6, 0.2, 0.0), atol=1e-3))
        self.assertTrue(np.allclose(parts["Rail"]["hi"], (1.72, 0.36, 1.72), atol=1e-3))  # the mitred corner's outside


if __name__ == "__main__":
    unittest.main()
