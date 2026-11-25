"""THE FITTED BAKE CAGE and THE WRONG SURFACE (kit/blender/rbx_bakecage.py; the 3D methods audit's PARTLY: "a
hand-sculpted cage around a complex part is not supported")."""

import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_bakecage as C  # noqa: E402

INF = math.inf


class Solve(unittest.TestCase):
    def test_every_point_of_the_high_is_cleared_and_the_corners_far_from_it_stay_at_the_floor(self):
        # two triangles: 0-1-2 and 1-2-3; a point 3 mm proud near vertex 0, everything else lying on the low
        corners = [(0, 1, 2), (0, 1, 2), (1, 2, 3)]
        place = [(0.8, 0.1, 0.1), (0.2, 0.4, 0.4), (0.1, 0.1, 0.8)]
        need = [3.0, 0.1, 0.1]
        h, unmet, _cap = C.fit_solve(corners, place, [(1, 1, 1)] * 3, need, 4, [INF] * 4, 0.25)
        self.assertGreaterEqual(0.8 * h[0] + 0.1 * h[1] + 0.1 * h[2], 3.0 - 1e-3)
        self.assertAlmostEqual(h[3], 0.25)                              # (no point needs vertex 3 raised)
        self.assertFalse(unmet.any())

    def test_a_corner_at_its_room_takes_no_more_the_others_rise_instead(self):
        corners, place = [(0, 1, 2)], [(0.4, 0.3, 0.3)]
        h, unmet, _cap = C.fit_solve(corners, place, [(1, 1, 1)], [2.0], 3, [0.5, INF, INF], 0.25)
        self.assertLessEqual(h[0], 0.5 + 1e-9)
        self.assertGreaterEqual(0.4 * h[0] + 0.3 * h[1] + 0.3 * h[2], 2.0 - 1e-3)
        self.assertFalse(unmet.any())

    def test_a_point_no_corner_can_reach_past_its_room_is_unmet(self):
        h, unmet, _cap = C.fit_solve([(0, 1, 2)], [(1 / 3, 1 / 3, 1 / 3)], [(1, 1, 1)], [2.0], 3, [0.5, 0.5, 0.5], 0.25)
        self.assertEqual(h.tolist(), [0.5, 0.5, 0.5])
        self.assertTrue(unmet[0])

    def test_a_face_held_by_the_room_across_it_holds_its_corners_down(self):
        # (the corner's own room is open - it looks over the wall - but the middle of its face has 1 mm in front)
        ceiling = ([(0, 1, 2)], [(1 / 3, 1 / 3, 1 / 3)], [(1, 1, 1)], [0.45])
        h, unmet, _cap = C.fit_solve([(0, 1, 2)], [(0.9, 0.05, 0.05)], [(1, 1, 1)], [3.0], 3, [INF] * 3, 0.25,
                               ceiling=ceiling)
        self.assertLessEqual(sum(h) / 3, 0.45 + 1e-3)               # (the cage over the face's middle stays short)
        self.assertTrue(unmet[0])                                   # (and the point it could not clear is said)

    def test_the_taper_never_lifts_a_face_past_the_room_across_it(self):
        # (review 2026-11-17: the taper undid the ceiling - a face held to 0.45 mm went to 4.6 next to an 8 mm need)
        ceiling = ([(0, 1, 2)], [(1 / 3, 1 / 3, 1 / 3)], [(1, 1, 1)], [0.45])
        h, _unmet, cap = C.fit_solve([(1, 3, 4)], [(0.1, 0.45, 0.45)], [(1, 1, 1)], [8.0], 5, [INF] * 5, 0.25,
                                     ceiling=ceiling)
        h = C.hold_down(C.taper(h, [[1, 2], [0, 2, 3], [0, 1, 4], [1], [2]], cap), ceiling)
        self.assertLessEqual(sum(h[:3]) / 3, 0.45 + 1e-3)
        self.assertGreater(h[3], 4.0)                                # (the deep corner keeps its depth)

    def test_a_corner_pushed_slantwise_must_go_further(self):
        # (a corner whose own normal leans 60 deg off the triangle's: half its push clears the face)
        h, _, _cap = C.fit_solve([(0, 1, 2)], [(1.0, 0.0, 0.0)], [(0.5, 1, 1)], [1.0], 3, [INF] * 3, 0.25)
        self.assertAlmostEqual(h[0], 2.0, places=3)

    def test_the_taper_never_steps_under_the_share_and_never_past_the_room(self):
        nb = [[1], [0, 2], [1, 3], [2]]
        h = C.taper([4.0, 0.25, 0.25, 0.25], nb, [INF, INF, 1.0, INF])
        self.assertAlmostEqual(h[1], 4.0 * C.FIT_RATIO)
        self.assertAlmostEqual(h[2], 1.0)                               # (it wanted 1.44: the room)
        self.assertGreaterEqual(h[3], C.FIT_RATIO * h[2] - 1e-9)

    def test_pinched_is_short_of_where_the_high_stands_never_of_the_margin(self):
        # (a point lying on the low needs no depth: a corner held to 0.04 mm by a fin over it is not pinched)
        self.assertFalse(C.short_of([(0, 1, 2)], [(1, 0, 0)], [(1, 1, 1)], [0.0], [0.04, 1, 1])[0])
        self.assertTrue(C.short_of([(0, 1, 2)], [(1, 0, 0)], [(1, 1, 1)], [0.5], [0.04, 1, 1])[0])

    def test_unmet_points_are_said_with_the_part(self):
        self.assertIsNone(C.pinch_problem("main", 0, 100, []))
        said = C.pinch_problem("main", 12, 400, ["Body"])
        self.assertIn("12 of 400 points of the high (on Body)", said)
        self.assertIn("its own group", said)


class TheWrongSurface(unittest.TestCase):
    # crossings along a texel's ray, mm out from it; True = the ray leaves solid material there going out

    def test_the_slot_a_deep_cage_inside_the_far_wall_bakes_its_back(self):
        # (measured: the nearest face either way round - a 4.4 mm depth on a 1.5 mm slot baked the far wall's back,
        # flipped; calm_normals then hid it under the neighbours' mean)
        t, out = [0.0, 1.5, 20.0], [True, False, True]
        truth = C.column_truth(t, out)
        self.assertEqual(truth, 0.0)
        self.assertEqual(C.bake_hit(t, out, 4.4, 11.0), 1.5)
        self.assertTrue(C.wrong(truth, C.bake_hit(t, out, 4.4, 11.0)))
        self.assertFalse(C.wrong(truth, C.bake_hit(t, out, 0.6, 1.5)))     # (a cage short of the far wall)

    def test_the_dome_on_its_plate_is_what_its_texels_bake_and_a_shallow_cage_misses_it(self):
        # (the plate's top and the dome's foot both at 0: the dome sits ON the plate; its top 3 mm out)
        t, out = [0.0, 0.0, 3.0], [True, False, True]
        truth = C.column_truth(t, out)
        self.assertEqual(truth, 3.0)
        self.assertTrue(C.wrong(truth, C.bake_hit(t, out, 1.0, 2.5)))      # (measured: 1 mm, 18.6 deg wrong)
        self.assertFalse(C.wrong(truth, C.bake_hit(t, out, 4.4, 11.0)))    # (measured: 4.4 mm, 0.1 deg)

    def test_a_foot_lying_on_its_plate_seen_once_is_still_the_body_on_it(self):
        # (one cast of the ray sees one of two faces lying on each other: the plate's top OR the dome's foot)
        self.assertEqual(C.column_truth([0.0, 3.0], [True, True]), 3.0)
        self.assertEqual(C.column_truth([0.0, 0.0, 3.0], [False, True, True]), 3.0)

    def test_a_plate_top_the_cast_dropped_under_a_foot_is_put_back_and_the_bake_lands_on_it(self):
        # (the line starts inside the plate; the cast saw the dome's foot at 0, not the plate's top lying on it)
        t, out = C.repair_column([0.0, 3.0], [False, True], inside=True)
        self.assertEqual((t.tolist(), out.tolist()), ([0.0, 0.0, 3.0], [True, False, True]))
        self.assertEqual(C.column_truth(t, out), 3.0)
        self.assertEqual(C.bake_hit(t, out, 1.0, 2.5), 0.0)                # (from inside the dome: its foot / plate)
        self.assertEqual(C.repair_column([0.0, 1.5], [True, False], inside=True)[1].tolist(), [True, False])
        self.assertEqual(C.repair_column([1.5], [False], inside=False)[1].tolist(), [False])

    def test_a_part_of_the_high_only_standing_off_its_host_is_still_what_its_texels_bake(self):
        # (review: a thread 0.3 mm off its host, past STACK_MM - truth stays the host's face unless marked as sitting)
        t, out = [0.0, 0.3, 1.0], [True, False, True]
        self.assertEqual(C.column_truth(t, out), 0.0)
        self.assertEqual(C.column_truth(t, out, sits=[False, True, True]), 1.0)

    def test_a_hole_the_low_leaves_out_is_the_surface_over_its_texel(self):
        t, out = [-2.0], [True]
        self.assertEqual(C.column_truth(t, out), -2.0)
        self.assertFalse(C.wrong(-2.0, C.bake_hit(t, out, 1.0, 5.0)))

    def test_past_a_thin_wall_the_bake_lands_on_the_wrong_surface(self):
        # (a slot 1.5 mm wide, its far side a fin 0.5 mm thick, then open air: a 4.4 mm cage starts beyond the fin)
        t, out = [0.0, 1.5, 2.0], [True, False, True]
        truth = C.column_truth(t, out)
        self.assertEqual(truth, 0.0)
        self.assertEqual(C.bake_hit(t, out, 4.4, 11.0), 2.0)
        self.assertTrue(C.wrong(truth, 2.0))
        self.assertEqual(C.bake_hit(t, out, 1.8, 4.5), 1.5)                # (between the wall and the fin: its face)

    def test_a_low_lying_a_little_under_or_over_its_high_is_its_own_surface(self):
        self.assertEqual(C.column_truth([0.2, -24.0], [True, False]), 0.2)
        self.assertEqual(C.column_truth([-0.2, -24.0], [True, False]), -0.2)
        self.assertIsNone(C.column_truth([-24.0], [False]))

    def test_it_is_said_over_its_share(self):
        self.assertIsNone(C.cross_problem("main", 0.005, ["A"]))
        said = C.cross_problem("main", 0.12, ["Block"])
        self.assertIn("12.0% of its map's texels baked another surface than the one over them (most on Block)", said)
        self.assertIn('a.bake_cage("fit")', said)


if __name__ == "__main__":
    unittest.main()
