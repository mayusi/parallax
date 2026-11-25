"""A mask the author places (kit/blender/rbx_mask.py; the owner's method lists: texture painting, masks, material
masks, material blending; the 3D methods audit, S3): a picture laid over the model from a view, a rule on the
point, and a layer that names the mask."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_layers as L  # noqa: E402
import rbx_mask as M  # noqa: E402

LO, HI = (-2.0, 0.0, -1.0), (2.0, 4.0, 1.0)                              # a model 4 wide, 4 tall, 2 deep


class Frames(unittest.TestCase):
    def test_from_the_front_the_models_right_is_on_the_viewers_left(self):
        origin, across, up, width, height = M.view_frame(LO, HI, "front")
        self.assertTrue(np.allclose(origin, (2, 0, -1)) and np.allclose(across, (-1, 0, 0)))
        self.assertTrue(np.allclose(up, (0, 1, 0)))
        self.assertEqual((width, height), (4.0, 4.0))

    def test_from_the_side_and_from_above(self):
        _o, across, up, width, height = M.view_frame(LO, HI, "side")
        self.assertTrue(np.allclose(across, (0, 0, -1)) and np.allclose(up, (0, 1, 0)))
        self.assertEqual((width, height), (2.0, 4.0))
        _o, across, up, width, height = M.view_frame(LO, HI, "top")
        self.assertTrue(np.allclose(across, (-1, 0, 0)) and np.allclose(up, (0, 0, 1)))
        self.assertEqual((width, height), (4.0, 2.0))
        with self.assertRaises(ValueError):
            M.view_frame(LO, HI, "below")


class Pictures(unittest.TestCase):
    def test_the_pictures_top_is_the_models_top_and_its_left_the_models_right(self):
        pic = np.zeros((4, 4))
        pic[0, 0] = 1.0                                                   # the picture's TOP LEFT texel
        frame = M.view_frame(LO, HI, "front")
        got = M.sample([(1.5, 3.5, 0), (-1.5, 3.5, 0), (1.5, 0.5, 0)], pic, frame)
        self.assertEqual(got.tolist(), [1.0, 0.0, 0.0])                   # the model's +x, up high: the top left

    def test_every_depth_behind_a_place_takes_its_value_and_outside_is_nothing(self):
        frame = M.view_frame(LO, HI, "front")
        pic = np.ones((2, 2))
        got = M.sample([(0, 2, -1), (0, 2, 0.7), (5, 2, 0), (0, -1, 0)], pic, frame)
        self.assertEqual(got.tolist(), [1.0, 1.0, 0.0, 0.0])

    def test_a_face_on_the_pictures_border_takes_it(self):
        # (the review: an all-white picture left a box's own sides bare)
        frame = M.view_frame(LO, HI, "front")
        pic = np.ones((8, 8))
        edge = M.sample([(2.0, 2, 0), (-2.0, 2, 0), (0, 4.0, 0), (0, 0.0, 0), (2.0 + 1e-9, 2, 0), (2.1, 2, 0)], pic,
                        frame)
        self.assertEqual(edge.tolist(), [1.0, 1.0, 1.0, 1.0, 1.0, 0.0])

    def test_greys_give_a_soft_edge(self):
        frame = M.view_frame(LO, HI, "front")
        pic = np.tile(np.linspace(0, 1, 64), (8, 1))                      # dark on the picture's left, light right
        left, mid, right = M.sample([(1.9, 2, 0), (0, 2, 0), (-1.9, 2, 0)], pic, frame)
        self.assertLess(left, 0.05)
        self.assertAlmostEqual(mid, 0.5, delta=0.02)
        self.assertGreater(right, 0.95)


class Rules(unittest.TestCase):
    def test_a_rule_is_true_false_or_a_number(self):
        pts = [(0, 1, 0), (0, 3, 0), (0, 2, 0)]
        self.assertEqual(M.by_rule(pts, lambda p: p[1] > 2.5).tolist(), [0.0, 1.0, 0.0])
        self.assertEqual(M.by_rule(pts, lambda p: p[1] / 4.0).tolist(), [0.25, 0.75, 0.5])
        self.assertEqual(M.by_rule(pts, lambda p: p[1] * 10).tolist(), [1.0, 1.0, 1.0])       # held to 1

    def test_the_values_land_on_their_texels_and_say_how_much_is_on(self):
        m = M.to_map(4, [0, 0, 3], [0, 1, 3], [1.0, 0.5, 0.25], reach=0)
        self.assertEqual(m.shape, (4, 4, 1))
        self.assertEqual((float(m[0, 0, 0]), float(m[0, 1, 0]), float(m[3, 3, 0]), float(m[2, 2, 0])),
                         (1.0, 0.5, 0.25, 0.0))

    def test_a_mask_is_carried_past_the_edge_of_its_island_and_no_further_than_its_reach(self):
        # an island of 4 x 4 texels in a 20 x 20 map, its left half masked: what the review of a stripe showed as
        # a notch at a seam is the unasked margin beside the island
        rows, cols = np.mgrid[8:12, 8:12]
        vals = (cols < 10).astype(float)
        m = M.to_map(20, rows.ravel(), cols.ravel(), vals.ravel(), reach=3)[..., 0]
        self.assertTrue((m[8:12, 8:10] == 1).all() and (m[8:12, 10:12] == 0).all())      # the island: as asked
        self.assertTrue((m[8:12, 5:8] == 1).all())                                         # the margin beside the mask
        self.assertTrue((m[8:12, 12:15] == 0).all())                                       # ... beside the plain half
        self.assertEqual(float(m[9, 4]), 0.0)                                              # past the reach: nothing
        self.assertEqual(float(m[0, 0]), 0.0)
        # another part's texels beside it take nothing (the review: a mask on one part bled onto its neighbour)
        near = M.to_map(20, rows.ravel(), cols.ravel(), vals.ravel(), reach=3,
                        others=([8, 9, 10, 11], [6, 6, 6, 6]))[..., 0]
        self.assertTrue((near[8:12, 7] == 1).all() and (near[8:12, 6] == 0).all() and (near[8:12, 5] == 0).all())
        # the map's own edges do not wrap round
        edge = M.to_map(6, [2], [0], [1.0], reach=2)[..., 0]
        self.assertEqual(float(edge[2, 5]), 0.0)
        self.assertEqual(M.said([1.0, 0.9, 0.2, 0.0]), {"on": 0.5, "mean": 0.525})
        self.assertEqual(M.said([]), {"on": 0.0, "mean": 0.0})


class Layers(unittest.TestCase):
    def setUp(self):
        z = np.zeros((4, 4, 1), np.float32)
        self.placed = z.copy()
        self.placed[:2] = 1.0
        self.maps = {"convex": z, "concave": z, "occ": z + 1, "exposed": z + 1, "reach": z,
                     "masks": {"scorch": self.placed}}

    def test_a_layer_may_name_a_placed_mask(self):
        lay = L.layer("rust", where="mask:scorch", amount=1.0, breakup=0.0)
        self.assertEqual(lay["where"], "mask:scorch")
        self.assertTrue(np.array_equal(L.field("mask:scorch", self.maps), self.placed))

    def test_a_mask_nobody_placed_is_nowhere_and_a_wrong_source_is_still_refused(self):
        self.assertEqual(float(L.field("mask:missing", self.maps).max()), 0.0)
        with self.assertRaises(ValueError):
            L.layer("rust", where="everywhere")
        with self.assertRaises(ValueError):
            L.layer("rust", where="mask:")

    def test_a_placed_mask_laid_in_full_covers_exactly_what_was_placed(self):
        cov = np.ones((4, 4, 1), np.float32)
        m, facts = L.mask(L.field("mask:scorch", self.maps), np.zeros((4, 4)), cov, 1.0, 0.0)
        self.assertGreater(float(m[:2].min()), 0.9)
        self.assertLess(float(m[2:].max()), 0.1)
        self.assertAlmostEqual(facts["eligible"], 0.5, places=2)


if __name__ == "__main__":
    unittest.main()
