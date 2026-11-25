"""Which collision shape and which level of detail a mesh gets in the game (kit/blender/rbx_fidelity.py; the owner's
method lists, 2026-11-13: collision meshes, primitive colliders, convex hulls, LOD setup; the 3D methods audit, G1
and G2): the choice from the empty space a cheaper shape would turn solid, and from pixels on the screen."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_fidelity as F  # noqa: E402


def cells_of(lo, hi, inside):
    """a shape given as a rule on points -> (solid grid, hull grid, pitch)"""
    pitch, shape, pts = F.grid(lo, hi)
    solid = inside(pts)
    hull = F.in_hull(pts[solid], pts)
    step = (np.asarray(hi, float) - np.asarray(lo, float)) / np.asarray(shape)
    return solid.reshape(shape), hull.reshape(shape), step


class Grid(unittest.TestCase):
    def test_the_cells_cover_the_box_and_are_no_finer_than_the_floor(self):
        pitch, shape, pts = F.grid((0, 0, 0), (12, 6, 3))
        self.assertAlmostEqual(pitch, 0.25)
        self.assertEqual(shape, (48, 24, 12))
        self.assertEqual(len(pts), 48 * 24 * 12)
        self.assertTrue(np.allclose(pts.min(axis=0), 0.125) and np.allclose(pts.max(axis=0), (11.875, 5.875, 2.875)))
        pitch, shape, _ = F.grid((0, 0, 0), (1, 1, 1))                    # a small prop: the floor, not 48 cells
        self.assertEqual((pitch, shape), (0.25, (4, 4, 4)))
        pitch, shape, _ = F.grid((0, 0, 0), (96, 8, 8))                   # a large one: 96 cells, a stud each
        self.assertEqual((pitch, shape), (1.0, (96, 8, 8)))

    def test_a_block_fits_only_where_every_cell_is_empty(self):
        empty = np.zeros((6, 6, 6), bool)
        empty[1:4, 1:5, 2:4] = True
        self.assertTrue(F.fits(empty, (3, 4, 2)))
        self.assertFalse(F.fits(empty, (4, 4, 2)))
        self.assertFalse(F.fits(empty, (3, 4, 3)))
        self.assertEqual(F.largest_cube(empty), 2)
        self.assertEqual(F.largest_cube(np.zeros((4, 4, 4), bool)), 0)
        self.assertFalse(F.fits(np.ones((2, 2, 2), bool), (3, 1, 1)))     # larger than the grid itself


class Hull(unittest.TestCase):
    def test_a_point_between_two_arms_is_inside_the_hull_and_one_beyond_is_not(self):
        ell = np.array([(0, 0, 0), (4, 0, 0), (4, 1, 0), (0, 4, 0), (1, 4, 0), (0, 0, 1), (4, 0, 1), (0, 4, 1)], float)
        got = F.in_hull(ell, np.array([(1.5, 1.5, 0.5), (3.5, 3.5, 0.5), (-0.2, 1, 0.5)], float))
        self.assertEqual(got.tolist(), [True, False, False])


class Collision(unittest.TestCase):
    def test_a_crate_gets_a_box(self):
        solid, hull, p = cells_of((0, 0, 0), (4, 4, 4), lambda q: np.ones(len(q), bool))
        m = F.measure(solid, hull, p)
        self.assertEqual(F.choose(m)[0], "Box")
        self.assertEqual((m["gap_box"], m["fill_box"]), (0.0, 1.0))

    def test_a_ball_gets_its_hull_its_corners_are_not_solid(self):
        solid, hull, p = cells_of((-5, -5, -5), (5, 5, 5), lambda q: (q ** 2).sum(axis=1) <= 25)
        m = F.measure(solid, hull, p)
        self.assertGreaterEqual(m["gap_box"], 1.5)                        # the box's corners: about 2 studs of air
        self.assertLess(m["gap_hull"], F.ROOM)
        self.assertEqual(F.choose(m)[0], "Hull")

    def test_a_trough_gets_the_approximate_concave_shape(self):
        # a slab 8 x 3 x 8 with a hollow 4 x 2 x 4 in its top: nobody stands in it, a foot goes into it
        def trough(q):
            hollow = (abs(q[:, 0]) < 2) & (q[:, 1] > 1) & (abs(q[:, 2]) < 2)
            return ~hollow
        solid, hull, p = cells_of((-4, 0, -4), (4, 3, 4), trough)
        m = F.measure(solid, hull, p)
        self.assertAlmostEqual(m["gap_hull"], 2.0, delta=0.3)
        self.assertFalse(m["body_hull"])
        self.assertEqual(F.choose(m)[0], "Default")

    def test_an_arch_a_character_walks_through_is_kept_exact(self):
        # a wall 12 wide, 8 tall, 2 thick with a doorway 4 wide and 6 tall
        def arch(q):
            return ~((abs(q[:, 0]) < 2) & (q[:, 1] < 6))
        solid, hull, p = cells_of((-6, 0, -1), (6, 8, 1), arch)
        m = F.measure(solid, hull, p)
        self.assertTrue(m["body_hull"])
        self.assertEqual(F.choose(m)[0], "PreciseConvexDecomposition")

    def test_a_doorway_in_a_thin_wall_is_a_doorway(self):
        # the review's find: walls are half a stud to a stud thick - the character passes THROUGH, it does not fit
        # inside the wall's thickness
        for thick in (0.5, 1.0, 1.5):
            def arch(q):
                return ~((abs(q[:, 0]) < 2) & (q[:, 1] < 6))
            solid, hull, p = cells_of((-6, 0, -thick / 2), (6, 8, thick / 2), arch)
            self.assertEqual(F.choose(F.measure(solid, hull, p))[0], "PreciseConvexDecomposition", thick)

    def test_a_window_in_a_thin_wall_is_not_boxed_shut_and_a_plain_thin_wall_is_a_box(self):
        def window(q):   # half a stud thick, a window 2 x 2 nobody walks through
            return ~((abs(q[:, 0]) < 1) & (q[:, 1] > 3) & (q[:, 1] < 5))
        solid, hull, p = cells_of((-6, 0, -0.25), (6, 8, 0.25), window)
        self.assertEqual(F.choose(F.measure(solid, hull, p))[0], "Default")
        solid, hull, p = cells_of((-6, 0, -0.25), (6, 8, 0.25), lambda q: np.ones(len(q), bool))
        self.assertEqual(F.choose(F.measure(solid, hull, p))[0], "Box")

    def test_a_shallow_dent_the_size_of_a_door_in_a_thick_wall_is_not_one(self):
        def dent(q):   # a wall 4 thick with a door-sized dent a quarter stud deep
            return ~((abs(q[:, 0]) < 2) & (q[:, 1] < 6) & (q[:, 2] > 1.75))
        solid, hull, p = cells_of((-6, 0, -2), (6, 8, 2), dent)
        m = F.measure(solid, hull, p)
        self.assertFalse(m["body_hull"])
        self.assertEqual(F.choose(m)[0], "Box")

    def test_one_stray_empty_cell_on_a_large_mesh_is_not_a_room(self):
        # 100 studs long: a cell is over a stud - one empty cell is the grid's noise, never a felt space
        solid, hull, p = cells_of((0, 0, 0), (100, 4, 4), lambda q: np.ones(len(q), bool))
        solid = solid.copy()
        solid[10, 1, 1] = False
        m = F.measure(solid, hull, p)
        self.assertGreater(m["pitch"], 1.0)
        self.assertFalse(m["room_box"])
        self.assertEqual(F.choose(m)[0], "Box")

    def test_a_slot_too_low_to_stand_in_is_not_a_doorway(self):
        def slot(q):
            return ~((abs(q[:, 0]) < 2) & (q[:, 1] < 3))
        solid, hull, p = cells_of((-6, 0, -1), (6, 8, 1), slot)
        self.assertEqual(F.choose(F.measure(solid, hull, p))[0], "Default")

    def test_a_thing_under_a_stud_is_a_box_whatever_its_shape(self):
        solid, hull, p = cells_of((0, 0, 0), (0.8, 0.8, 0.8), lambda q: q[:, 0] < 0.2)
        self.assertEqual(F.choose(F.measure(solid, hull, p), size=(0.8, 0.8, 0.8))[0], "Box")


class Declared(unittest.TestCase):
    def setUp(self):
        solid, hull, p = cells_of((-6, 0, -1), (6, 8, 1), lambda q: ~((abs(q[:, 0]) < 2) & (q[:, 1] < 6)))
        self.arch = F.measure(solid, hull, p)
        solid, hull, p = cells_of((0, 0, 0), (4, 4, 4), lambda q: np.ones(len(q), bool))
        self.crate = F.measure(solid, hull, p)

    def test_a_cheap_shape_that_closes_a_doorway_is_an_error(self):
        for cheap in ("Box", "Hull"):
            level, what, fix = F.judge(cheap, self.arch)
            self.assertEqual(level, "error")
            self.assertIn("standing character", what)
            self.assertIn('"precise"', fix)

    def test_a_dear_shape_on_a_crate_is_a_warning_and_the_rules_own_choice_is_silent(self):
        level, what, _fix = F.judge("PreciseConvexDecomposition", self.crate)
        self.assertEqual(level, "warn")
        self.assertIn("no more than Box", what)
        self.assertIsNone(F.judge("Box", self.crate))
        self.assertIsNone(F.judge("PreciseConvexDecomposition", self.arch))


class Render(unittest.TestCase):
    def test_pixels_a_stud_covers(self):
        self.assertAlmostEqual(F.px_per_stud(250), 3.085, places=2)       # 1080 lines, 70 degrees
        self.assertAlmostEqual(F.px_per_stud(500), 1.542, places=2)

    def test_a_move_nobody_sees_stays_automatic(self):
        name, why, px = F.render_choice({"lod1": 0.2, "lod2": 0.5})       # 0.6 px and 0.8 px
        self.assertEqual(name, "Automatic")
        self.assertLess(max(px.values()), F.SEEN_PX)
        self.assertIn("under the 1.5 px", why)

    def test_a_move_that_is_seen_asks_for_precise_and_names_where(self):
        name, why, _px = F.render_choice({"lod1": 0.2, "lod2": 1.2})      # 1.85 px at 500 studs
        self.assertEqual(name, "Precise")
        self.assertIn("at 500 studs", why)
        self.assertNotIn("at 250 studs", why)

    def test_a_mesh_of_a_few_triangles_is_automatic_whatever_the_simulation_says(self):
        name, why, _px = F.render_choice({"lod1": 9.0, "lod2": 9.0}, tris=28)
        self.assertEqual(name, "Automatic")
        self.assertIn("28 triangles", why)
        self.assertEqual(F.render_choice({"lod1": 9.0, "lod2": 9.0}, tris=5000)[0], "Precise")


class Columns(unittest.TestCase):
    def test_a_column_is_inside_between_a_face_in_and_a_face_out(self):
        inside, on = F.fill_column(10, 0.0, 1.0, [(2.2, 1), (6.7, -1)])
        self.assertEqual(inside.tolist(), [False] * 2 + [True] * 5 + [False] * 3)   # centres 2.5 .. 6.5
        self.assertEqual(np.flatnonzero(on).tolist(), [2, 6])

    def test_two_parts_that_overlap_are_inside_all_the_way(self):
        # part A 1..8, part B 4..6 inside it: the nearest-face test read 4..6 as a hollow
        inside, _on = F.fill_column(10, 0.0, 1.0, [(1.0, 1), (4.0, 1), (6.0, -1), (8.0, -1)])
        self.assertEqual(inside.tolist(), [False] + [True] * 7 + [False] * 2)

    def test_a_shell_turned_inside_out_is_still_solid_and_no_hit_is_empty(self):
        inside, _on = F.fill_column(6, 0.0, 1.0, [(1.0, -1), (4.0, 1)])
        self.assertEqual(inside.tolist(), [False, True, True, True, False, False])
        inside, on = F.fill_column(6, 0.0, 1.0, [])
        self.assertFalse(inside.any() or on.any())


if __name__ == "__main__":
    unittest.main()
