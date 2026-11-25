"""Surfaces that repeat, and a painted light (kit/blender/rbx_tile.py; the owner's method lists: seamless /
tileable, stylised shading; the 3D methods audit, stage X)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_tile as T  # noqa: E402


def slope(n=64):
    """a map that gets lighter left to right AND top to bottom: its edges do not meet either way"""
    x = np.linspace(0.2, 0.8, n)
    img = (x[None, :] + x[:, None]) / 2
    return np.repeat(img[..., None], 3, axis=2)


class Tiles(unittest.TestCase):
    def test_a_sloped_map_steps_both_ways_and_is_said(self):
        found = T.steps(slope())
        self.assertGreater(found["u"]["step"], 0.2)
        self.assertGreater(found["v"]["step"], 0.2)
        said = T.tile_problem("the colour map", found)
        self.assertIn("does not repeat left to right", said)
        self.assertIn("and top to bottom", said)

    def test_made_to_repeat_its_edges_meet_both_ways_and_its_middle_is_not_touched(self):
        img = slope()
        made = T.tileable(img)
        found = T.steps(made)
        self.assertLess(found["u"]["step"], T.TILE_BAR)
        self.assertLess(found["v"]["step"], T.TILE_BAR)
        self.assertIsNone(T.tile_problem("the colour map", found))
        self.assertTrue(np.allclose(made[16:48, 16:48], img[16:48, 16:48]))

    def test_a_map_that_repeats_one_way_only_names_the_other(self):
        x = np.linspace(0.2, 0.8, 64)
        img = np.repeat(np.tile(x[:, None], (1, 64))[..., None], 3, axis=2)      # constant along u, sloped along v
        said = T.tile_problem("the colour map", T.steps(img))
        self.assertIn("top to bottom", said)
        self.assertNotIn("left to right", said)


class Held(unittest.TestCase):
    def test_a_hard_line_on_a_twentieth_of_an_edge_fails(self):
        # (the review: 12 of 256 rows stepping by half passed - the 95th percentile did not see them)
        img = np.full((256, 256, 3), 0.5)
        img[:12, :2] = 0.0
        img[:12, -2:] = 1.0
        found = T.steps(img)
        self.assertGreater(found["u"]["share"], 0.04)
        self.assertIn("does not repeat left to right", T.tile_problem("the rough map", found))

    def test_a_faded_normal_map_is_made_unit_again(self):
        px = np.zeros((2, 2, 4))
        px[..., :3] = np.array([0.5, 0.5, 0.8])            # (0, 0, 0.6): two normals blended, too short
        px[..., 3] = 1.0
        out = T.unit_normals(px)
        v = out[..., :3] * 2 - 1
        self.assertTrue(np.allclose(np.linalg.norm(v, axis=-1), 1.0))
        self.assertTrue(np.allclose(out[..., 3], 1.0))
        self.assertTrue(np.allclose(v[0, 0], (0, 0, 1)))

    def test_the_painted_light_is_read_off_the_map(self):
        tone = np.array([1.0] * 50 + [0.7] * 50 + [0.4] * 50)
        luma = np.array([0.8] * 50 + [0.65] * 50 + [0.5] * 50)
        ratio = T.lit_over_shade(luma, tone, 0.4)
        self.assertAlmostEqual(ratio, 1.6)
        self.assertIsNone(T.style_problem("main", ratio, 0.4))
        flat = T.lit_over_shade(np.full(150, 0.8), tone, 0.4)          # the light never reached the map
        self.assertAlmostEqual(flat, 1.0)
        self.assertIn("the light is not in the map", T.style_problem("main", flat, 0.4))
        self.assertIsNone(T.lit_over_shade(luma, np.ones(150), 0.4))   # a ramp of one tone: nothing to read


class Painted(unittest.TestCase):
    N = [(0, 1, 0), (0, -1, 0), (1, 0, 0), (0.35, 1.0, 0.45)]

    def test_what_faces_the_light_is_as_it_is_and_what_faces_away_is_the_shade(self):
        got = T.ramp(self.N, bands=0, shade=0.4)
        self.assertAlmostEqual(float(got[3]), 1.0, places=6)                     # straight at the light
        self.assertGreater(float(got[0]), float(got[2]))                         # up is lighter than sideways
        self.assertGreater(float(got[2]), float(got[1]))                         # ... than down
        self.assertGreaterEqual(float(got.min()), 0.4)

    def test_bands_are_flat_tones(self):
        fan = [(np.cos(a), np.sin(a), 0.0) for a in np.linspace(0, 2 * np.pi, 400)]
        self.assertEqual(T.tones(T.ramp(fan, bands=3)), 3)
        self.assertEqual(T.tones(T.ramp(fan, bands=2)), 2)
        self.assertGreater(T.tones(T.ramp(fan, bands=0)), 20)                    # a smooth ramp
        two = T.ramp(fan, bands=2, shade=0.5)
        self.assertEqual(sorted(set(np.round(two, 3))), [0.5, 1.0])

    def test_a_normal_need_not_be_unit(self):
        self.assertAlmostEqual(float(T.ramp([(0, 5, 0)], bands=0)[0]), float(T.ramp([(0, 1, 0)], bands=0)[0]))


if __name__ == "__main__":
    unittest.main()
