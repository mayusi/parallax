"""What a model costs to draw, past its triangles (kit/blender/rbx_batch.py; the owner's method lists: draw calls,
overdraw; the 3D methods audit, stage O)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_batch as B  # noqa: E402


class Draws(unittest.TestCase):
    GROUPS = [{"name": "main"}, {"name": "slide", "moves": True}, {"name": "glass", "see_through": True},
              {"name": "grip"}, {"name": "rail"}]

    def test_a_group_earns_its_draw_by_moving_or_by_being_seen_through(self):
        found = B.draws(self.GROUPS)
        self.assertEqual(found["draws"], 5)
        self.assertEqual(found["moving"], ["slide"])
        self.assertEqual(found["see_through"], ["glass"])
        self.assertEqual(found["solid"], ["main", "grip", "rail"])
        self.assertEqual(found["saved"], 2)
        self.assertIsNone(B.draw_problem(found))                     # three solid groups: under the bar

    def test_many_solid_groups_that_never_move_apart_are_said(self):
        found = B.draws([{"name": f"g{i}"} for i in range(6)])
        said = B.draw_problem(found)
        self.assertIn("6 solid groups never move apart", said)
        self.assertIn("5 draws saved", said)
        self.assertEqual(B.draws([{"name": "main"}])["saved"], 0)


class Layers(unittest.TestCase):
    def test_rays_that_met_no_see_through_surface_are_not_counted(self):
        found = B.layers([0, 0, 2, 2, 4])
        self.assertEqual((found["rays"], found["most"]), (3, 4))
        self.assertAlmostEqual(found["mean"], 2.67, places=2)
        self.assertEqual(B.layers([0, 0])["rays"], 0)
        self.assertIsNone(B.overdraw_problem(B.layers([0, 0])))

    def test_see_through_parts_stacked_deep_are_said(self):
        self.assertIsNone(B.overdraw_problem(B.layers([2] * 100)))    # a pane: in and out
        said = B.overdraw_problem(B.layers([12] * 100))
        self.assertIn("crosses up to 12 see-through layers", said)


class Views(unittest.TestCase):
    def test_a_views_rays_cover_the_box_and_run_through_it(self):
        starts, direction, reach = B.grid((0, 0, 0), (2, 4, 6), axis=2, sign=1, n=4)
        self.assertEqual(starts.shape, (16, 3))
        self.assertTrue(np.allclose(direction, (0, 0, -1)))
        self.assertTrue((starts[:, 2] > 6).all())                     # from outside the far face
        self.assertAlmostEqual(float(starts[:, 0].min()), 0.25)
        self.assertAlmostEqual(float(starts[:, 1].max()), 3.5)
        self.assertGreater(reach, 6.0)
        starts, direction, _ = B.grid((0, 0, 0), (2, 4, 6), axis=0, sign=-1, n=2)
        self.assertTrue(np.allclose(direction, (1, 0, 0)))
        self.assertTrue((starts[:, 0] < 0).all())


if __name__ == "__main__":
    unittest.main()
