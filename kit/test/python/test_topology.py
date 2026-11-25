"""The topology of a built model, measured (kit/blender/rbx_topology.py; the owner's method lists: edge flow,
polygon distribution, internal and hidden faces; the 3D methods audit, stage T)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_topology as T  # noqa: E402


def grid(n, bump=0.0):
    """a square of n x n quads (two triangles each) in the xz plane; bump lifts its middle vertex"""
    pts = [(x, 0.0, z) for z in range(n + 1) for x in range(n + 1)]
    if bump:
        mid = (n // 2) * (n + 1) + n // 2
        pts[mid] = (pts[mid][0], bump, pts[mid][2])
    tris = []
    for z in range(n):
        for x in range(n):
            a = z * (n + 1) + x
            tris += [(a, a + 1, a + n + 2), (a, a + n + 2, a + n + 1)]
    return np.array(pts, float), np.array(tris)


class Waste(unittest.TestCase):
    def test_the_inside_of_a_flat_grid_buys_nothing_and_its_rim_holds_the_outline(self):
        pts, tris = grid(4)
        free = T.flat_verts(pts, tris)
        self.assertEqual(int(free.sum()), 9)                       # the 3 x 3 inside; the 16 on the rim stay
        w = T.waste(pts, tris)
        self.assertEqual((w["verts"], w["tris"]), (9, 18))
        self.assertAlmostEqual(w["share"], 18 / 32)
        self.assertIn("56% of its triangles are spent on nothing", T.waste_problem("main", w))

    def test_a_vertex_that_holds_a_shape_is_kept(self):
        pts, tris = grid(4, bump=0.5)
        free = T.flat_verts(pts, tris)
        mid = 2 * 5 + 2
        self.assertFalse(free[mid])
        self.assertFalse(free[mid + 1])                            # its neighbours carry the slope
        self.assertIsNone(T.waste_problem("main", T.waste(*grid(1))))

    def test_what_the_caller_keeps_is_kept(self):
        pts, tris = grid(4)
        keep = np.zeros(len(pts), bool)
        keep[6] = True                                             # (a corner of the map, say)
        self.assertEqual(int(T.flat_verts(pts, tris, keep).sum()), 8)


class Slivers(unittest.TestCase):
    def test_a_long_thin_triangle_is_one_and_a_plain_one_is_not(self):
        pts = np.array([(0, 0, 0), (1, 0, 0), (0, 1, 0), (100, 0, 0), (50, 0.1, 0)], float)
        s = T.slivers(pts, [(0, 1, 2), (0, 3, 4)])
        self.assertEqual(s["mask"].tolist(), [False, True])
        self.assertEqual(s["count"], 1)
        self.assertAlmostEqual(s["worst"], 1000.0, delta=1.0)      # 100 long, 0.1 wide
        self.assertIn("50% of its triangles are needles", T.sliver_problem("main", s))

    def test_a_long_bevel_is_not_a_needle_it_is_thin_in_studs_too(self):
        # (the review: a 24-stud box with the kit's own bevel, 0.02 wide, read 7% needles)
        pts = np.array([(0, 0, 0), (24, 0, 0), (24, 0.02, 0), (0, 0.02, 0), (0, 0.002, 0), (24, 0.002, 0)], float)
        bevel = T.slivers(pts, [(0, 1, 2), (0, 2, 3)], width=T.NEEDLE_WIDTH)
        self.assertEqual(bevel["count"], 0)
        shim = T.slivers(pts, [(0, 1, 5), (0, 5, 4)], width=T.NEEDLE_WIDTH)
        self.assertEqual(shim["count"], 2)

    def test_a_triangle_with_no_surface_is_not_counted_here(self):
        pts = np.array([(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 0)], float)
        s = T.slivers(pts, [(0, 1, 2), (0, 1, 3)])
        self.assertEqual((s["count"], s["share"]), (0, 0.0))


class Poles(unittest.TestCase):
    def fan(self, n, lift):
        pts = [(0.0, lift, 0.0)] + [(np.cos(2 * np.pi * i / n), 0.0, np.sin(2 * np.pi * i / n)) for i in range(n)]
        tris = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
        return np.array(pts, float), np.array(tris)

    def test_the_tip_of_a_cone_is_a_pole_and_the_middle_of_a_flat_cap_is_not(self):
        self.assertEqual(T.poles(*self.fan(24, 1.0)), [0])
        self.assertEqual(T.poles(*self.fan(24, 0.0)), [])
        self.assertEqual(T.poles(*self.fan(12, 1.0)), [])          # twelve edges: under the limit
        self.assertIn("1 point(s) where more than 16 edges meet", T.pole_problem("main", [0], ["Tip"]))
        self.assertIsNone(T.pole_problem("main", []))


class Shading(unittest.TestCase):
    def test_flat_is_every_corner_on_its_own_faces_normal(self):
        face = np.array([(0, 1, 0)] * 4 + [(1, 0, 0)] * 4, float)
        self.assertEqual(T.shaded(face, face), 1.0)
        round_ = np.array([(0.7, 0.7, 0)] * 8, float)              # every corner the average of the two faces
        self.assertEqual(T.shaded(round_, face), 0.0)
        self.assertIsNone(T.shade_problem("Block", "flat", 1.0))
        self.assertIn("Block: asked flat, and 100% of its corners are shaded round",
                      T.shade_problem("Block", "flat", 0.0))
        self.assertIsNone(T.shade_problem("Ball", "smooth", 0.1))
        self.assertIn("asked smooth", T.shade_problem("Ball", "smooth", 1.0))


class Eyes(unittest.TestCase):
    def test_the_directions_all_look_from_the_faces_own_side(self):
        for normal in ((0, 1, 0), (1, 0, 0), (0.3, -0.5, 0.8)):
            d = T.directions(normal, 24)
            n = np.asarray(normal, float) / np.linalg.norm(normal)
            self.assertEqual(d.shape, (24, 3))
            self.assertTrue(np.allclose(np.linalg.norm(d, axis=1), 1.0))
            self.assertGreater(float((d @ n).min()), 0.16)         # none flatter than about 10 degrees
            self.assertGreater(float((d @ n).max()), 0.97)         # ... and one near straight on
        # spread all the way round, not a fan to one side
        d = T.directions((0, 1, 0), 24)
        self.assertLess(abs(float(d[:, 0].mean())), 0.15)
        self.assertLess(abs(float(d[:, 2].mean())), 0.15)

    def test_never_seen_is_said_with_where(self):
        self.assertIsNone(T.hidden_problem("main", 0.20, 80, ["Lid"]))     # (sunk parts: a fact, not a warning)
        self.assertIn("main: 42% of its triangles (168) can never be seen from outside (most on Lid)",
                      T.hidden_problem("main", 0.42, 168, ["Lid"]))


if __name__ == "__main__":
    unittest.main()
