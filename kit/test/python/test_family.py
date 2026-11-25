"""A FAMILY OF MODULES THAT SNAP (kit/blender/rbx_family.py; the 3D methods audit's PARTLY "a family of parts that snap
to each other (dovetail joints, hallway tiles) is not built")."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_family as F  # noqa: E402


def rect(u0, v0, u1, v1):
    return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]


def wall(thick=0.5, lip=0.0, size=(4.0, 4.0)):
    """a 4 x 4 cell: a wall `thick` studs at its left (seen from outside), with a lip `lip` high along the floor"""
    loops = [rect(0, 0, thick, size[1])] + ([rect(thick, 0, size[0], lip)] if lip else [])
    return F.fill(loops, (0, 0), size)


class Fill(unittest.TestCase):
    def test_a_cut_fills_inside_its_loop_and_a_hole_stays_empty(self):
        r = F.fill([rect(0, 0, 4, 4), rect(1, 1, 3, 3)], (0, 0), (4, 4), res=0.5)
        self.assertTrue(r[0, 0] and not r[4, 4])             # (even-odd: the inner loop is a hole)
        self.assertEqual(r.shape, (8, 8))

    def test_a_cut_as_loose_edges_fills_as_its_loops_do(self):
        loops = [rect(0, 0, 4, 4), rect(1, 1, 3, 3)]
        segs = [(lp[i], lp[(i + 1) % len(lp)]) for lp in loops for i in range(len(lp))][::-1]   # (any order)
        self.assertTrue((F.fill_segments(segs, (0, 0), (4, 4), 0.5) == F.fill(loops, (0, 0), (4, 4), 0.5)).all())

    def test_facing_sides_see_each_other_mirrored_left_to_right_with_one_up(self):
        for a_, b_ in (("+X", "-X"), ("+Z", "-Z"), ("+Y", "-Y")):
            (ra, ua), (rb, ub) = F.FRAMES[a_], F.FRAMES[b_]
            self.assertEqual(tuple(-c for c in ra), rb)
            self.assertEqual(ua, ub)

    def test_every_cell_is_its_own_window_the_same_size_on_every_module(self):
        # (review 2026-11-17: one raster split by integer division drifted; a free depth compared by its own width)
        w = F.windows((0.0, 0.0), (3.99, 8.0), 1.33, 4.0)
        self.assertEqual(len(w), 6)
        self.assertEqual({tuple(round(x, 6) for x in c[3]) for c in w}, {(1.33, 4.0)})
        self.assertAlmostEqual(w[1][2][0], 1.33)                          # (cell u=1 starts one grid cell on)
        free_a = F.windows((0.0, 0.0), (4.0, 4.0), 0.0, 4.0)
        free_b = F.windows((0.0, 0.0), (4.2, 4.0), 0.0, 4.0)
        self.assertEqual(free_a[0][3], free_b[0][3])                      # (a free axis: one window size, ...)
        self.assertAlmostEqual(free_b[0][4][0], 2.1)                      # (... centred on the side's middle)

    def test_a_quarter_turn_carries_every_wall_sides_frame_onto_anothers(self):
        def turn(p):                     # (+90 deg about +Y, as CFrame.Angles(0, pi/2, 0): +X goes to -Z)
            x, y, z = p
            return (z, y, -x)
        normal = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Z": (0, 0, 1), "-Z": (0, 0, -1)}
        for side, n in normal.items():
            nn = turn(n)
            other = next(k for k, v in normal.items() if v == nn)
            self.assertEqual(turn(F.FRAMES[side][0]), tuple(F.FRAMES[other][0]), (side, other))
            self.assertEqual(turn(F.FRAMES[side][1]), tuple(F.FRAMES[other][1]))
            fwd = tuple(-c for c in n)                                     # (right = forward x up, from outside)
            up = F.FRAMES[side][1]
            right = (fwd[1] * up[2] - fwd[2] * up[1], fwd[2] * up[0] - fwd[0] * up[2], fwd[0] * up[1] - fwd[1] * up[0])
            self.assertEqual(right, tuple(F.FRAMES[side][0]))


class Meet(unittest.TestCase):
    def test_a_lopsided_side_meets_its_mirror_not_itself(self):
        left, right = wall(), np.fliplr(wall())
        self.assertEqual(F.meet(left, right)[0], "fits")      # (face to face: the shared plane mirrored)
        self.assertEqual(F.meet(left, left)[0], "other")

    def test_a_wall_a_little_thicker_is_the_seam_a_player_sees(self):
        a, b = wall(0.5), np.fliplr(wall(0.6))
        verdict, iou = F.meet(a, b)
        self.assertEqual(verdict, "seam", iou)

    def test_a_step_is_judged_by_its_width_not_by_the_share_of_the_area(self):
        # (review: a 0.1 stud step on a full side passed an area test at 0.975)
        full = F.fill([rect(0, 0, 4, 4)], (0, 0), (4, 4))
        step = F.fill([rect(0, 0, 4, 3.9)], (0, 0), (4, 4))
        self.assertEqual(F.meet(full, np.fliplr(step))[0], "seam")
        jitter = F.fill([rect(0, 0, 4, 3.99)], (0, 0), (4, 4))            # (under a raster cell: jitter)
        self.assertEqual(F.meet(full, np.fliplr(jitter))[0], "fits")

    def test_two_open_cells_meet_as_open(self):
        z = np.zeros((10, 10), bool)
        self.assertEqual(F.meet(z, z)[0], "open")

    def test_the_packed_rows_read_back(self):
        r = wall(lip=1.0)
        self.assertTrue((F.unpack(F.pack(r)) == r).all())


class Family(unittest.TestCase):
    def test_connectors_mates_and_seams_over_a_hall(self):
        sym = F.fill([rect(0, 0, 4, 0.5)], (0, 0), (4, 4))                  # a floor: symmetric, mates itself
        lip_l = wall(lip=1.0)
        lip_r = np.fliplr(lip_l)
        thick = np.fliplr(wall(0.6, lip=1.0))
        mods = {
            "Straight": {"+X": [[F.pack(sym)]], "-X": [[F.pack(sym)]]},
            "Corner": {"+X": [[F.pack(lip_l)]], "-Z": [[F.pack(np.zeros_like(sym))]]},
            "End": {"-X": [[F.pack(lip_r)]]},
            "Bad": {"-X": [[F.pack(thick)]]},
        }
        got = F.family(mods)
        s = got["sides"]
        self.assertEqual(s["Straight"]["+X"][0][0], s["Straight"]["-X"][0][0])
        c_sym, c_l, c_r = s["Straight"]["+X"][0][0], s["Corner"]["+X"][0][0], s["End"]["-X"][0][0]
        self.assertIn(c_sym, got["mates"][c_sym])                           # (symmetric: mates itself)
        self.assertIn(c_r, got["mates"][c_l])                               # (the lip meets its mirror)
        self.assertNotIn(c_l, got["mates"][c_l])
        self.assertEqual(s["Corner"]["-Z"][0][0], "open")
        bad = s["Bad"]["-X"][0][0]
        self.assertNotIn(bad, got["mates"][c_l])
        self.assertTrue(any(("Bad" in x and "Corner" in x) for x in got["seams"]), got["seams"])


class Review(unittest.TestCase):
    def test_a_one_sided_hall_meets_end_to_end_and_its_turned_self_is_only_said(self):
        # (review: a pipe along one wall - its +X mates its -X; against its own mirror it almost meets)
        pipe = F.fill([rect(0, 0, 0.5, 4), rect(3.5, 0, 4, 4), rect(0, 0, 4, 0.5), rect(0.5, 0.5, 1.0, 1.0)],
                      (0, 0), (4, 4))
        got = F.family({"Pipe": {"+X": [[F.pack(pipe)]], "-X": [[F.pack(np.fliplr(pipe))]]}})
        a, b = got["sides"]["Pipe"]["+X"][0][0], got["sides"]["Pipe"]["-X"][0][0]
        self.assertIn(b, got["mates"][a])
        self.assertEqual(got["seams"], [])                                  # (no fail ...)
        self.assertTrue(got["turned"])                                      # (... only said)

    def test_a_chain_of_near_alikes_never_hides_a_seam(self):
        # (review: slabs 2.0, 2.05, 1.97 high fell in one connector; 2.05 against 1.97 is a seam)
        def slab(h):
            return F.pack(F.fill([rect(0, 0, 4, h)], (0, 0), (4, 4)))
        got = F.family({"A": {"+X": [[slab(2.0)]]}, "B": {"-X": [[slab(2.05)]]}, "C": {"-X": [[slab(1.97)]]}})
        self.assertTrue(got["seams"], got)

    def test_a_two_cell_side_meets_as_a_whole_cell_for_mirrored_cell(self):
        left, right = wall(), np.fliplr(wall())
        sym = F.fill([rect(0, 0, 4, 0.5)], (0, 0), (4, 4))
        got = F.family({"A": {"+X": [[F.pack(left), F.pack(sym)]]}, "B": {"-X": [[F.pack(sym), F.pack(right)]]},
                        "C": {"-X": [[F.pack(right), F.pack(sym)]]}})
        self.assertIn("B.-X", got["whole"]["A.+X"])                         # (cell 0 against B's cell 1 ...)
        self.assertNotIn("C.-X", got["whole"].get("A.+X", []))             # (... C's cells are the wrong way round)


class Facing(unittest.TestCase):
    def test_a_top_meets_only_a_bottom_and_walls_only_walls(self):
        slab = F.pack(F.fill([rect(0, 0, 4, 4)], (0, 0), (4, 4)))
        strip = F.pack(F.fill([rect(0, 0, 0.5, 4)], (0, 0), (4, 4)))
        strip2 = F.pack(F.fill([rect(0, 0, 0.6, 4)], (0, 0), (4, 4)))
        got = F.family({"A": {"+Y": [[strip]], "-Y": [[slab]], "+X": [[slab]]},
                        "B": {"+Y": [[strip2]], "-Y": [[slab]], "-Z": [[slab]]}})
        s = got["sides"]
        self.assertNotEqual(s["A"]["-Y"][0][0], s["A"]["+X"][0][0])        # (a floor and a wall: two kinds)
        self.assertEqual(s["A"]["+X"][0][0], s["B"]["-Z"][0][0])            # (a wall side and a turned one)
        self.assertEqual(got["seams"], [])                                  # (two tops never stand face to face)


if __name__ == "__main__":
    unittest.main()
