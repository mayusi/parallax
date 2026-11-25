"""The arithmetic of sharpening a generated part (kit/gen/sharpen_math.py): where the cameras stand, where a point
lands in a view's picture, how much a view counts at a surface point, the blend into the colour map, the maps a game
material gets from the sharpened colour (which way a normal map leans is pinned here), and the fold that lays a
generated pair of wings straight back. Pure numpy: no Blender, no image model."""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "gen"))
import sharpen_math as M  # noqa: E402


def camera(yaw, pitch, at=(0.0, 0.0, 0.0), far=5.0):
    """an orthographic camera's world matrix looking at `at` from yaw / pitch (Blender: -Z forward, +Y up)"""
    back = M.view_direction(yaw, pitch)
    right = np.cross((0.0, 0.0, 1.0), back)
    right /= np.linalg.norm(right)
    up = np.cross(back, right)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = right, up, back, np.asarray(at) + back * far
    return m


class TestCameras(unittest.TestCase):
    def test_yaw_0_is_the_camera_on_minus_y_and_positive_yaw_swings_to_plus_x(self):
        np.testing.assert_allclose(M.view_direction(0, 0), (0, -1, 0), atol=1e-12)
        np.testing.assert_allclose(M.view_direction(90, 0), (1, 0, 0), atol=1e-12)
        np.testing.assert_allclose(M.view_direction(0, 90), (0, 0, 1), atol=1e-12)
        self.assertAlmostEqual(float(np.linalg.norm(M.view_direction(37, 21))), 1.0)

    def test_a_frame_is_a_megapixel_on_the_image_models_grid_and_its_spans_follow_its_pixels(self):
        rx, ry, hw, hh = M.frame(2.0, 1.0)
        self.assertEqual((rx % 16, ry % 16), (0, 0))
        self.assertAlmostEqual(rx * ry / (1024 * 1024), 1.0, delta=0.06)
        self.assertAlmostEqual(hw / hh, rx / ry, places=9)           # (square pixels: no stretch when projected back)
        self.assertGreaterEqual(hw, 1.0)                              # the object (2 wide) is inside the frame
        self.assertGreaterEqual(hh, 0.5)
        tall = M.frame(1.0, 3.0)
        self.assertGreater(tall[1], tall[0])
        self.assertAlmostEqual(tall[2] / tall[3], tall[0] / tall[1], places=9)

    def test_a_point_lands_right_of_centre_when_it_is_to_the_cameras_right_and_above_when_it_is_up(self):
        cam = camera(0, 0)                                           # on -Y, looking along +Y: +X is its right
        uv = M.ortho_uv([(0, 0, 0), (0.5, 0, 0), (0, 0, 0.25), (0, 3.0, 0)], cam, 1.0, 0.5)
        np.testing.assert_allclose(uv[0], (0.5, 0.5), atol=1e-12)
        np.testing.assert_allclose(uv[1], (0.75, 0.5), atol=1e-12)   # half a unit right of a 2-wide frame
        np.testing.assert_allclose(uv[2], (0.5, 0.75), atol=1e-12)   # v runs UP
        np.testing.assert_allclose(uv[3], (0.5, 0.5), atol=1e-12)    # depth does not move an orthographic point
        np.testing.assert_allclose(M.toward_camera(cam), (0, -1, 0), atol=1e-12)
        left = M.ortho_uv([(0, -0.5, 0)], camera(90, 0), 1.0, 1.0)   # from +X, the part's -Y (its nose) is LEFT
        self.assertLess(float(left[0][0]), 0.5)


class TestWeights(unittest.TestCase):
    def test_a_view_counts_by_how_squarely_it_sees_a_surface_and_not_at_all_where_it_cannot(self):
        toward = np.array([0.0, -1.0, 0.0])
        n = np.array([[0, -1, 0], [0, 1, 0], [math.sin(math.radians(60)), -math.cos(math.radians(60)), 0], [0, -1, 0]],
                     dtype=float)
        w = M.view_weight(n, toward, seen=[1, 1, 1, 0])
        np.testing.assert_allclose(w, (1.0, 0.0, 0.125, 0.0), atol=1e-12)   # facing, away, 60 degrees off, hidden

    def test_the_blend_keeps_untouched_texels_and_shares_touched_ones_by_weight(self):
        old = np.full((2, 2, 3), 0.2)
        said = np.full((2, 2), M.OWN_SAY)
        first = np.full((2, 2, 3), 0.8)
        w1 = np.array([[1.0, 0.0], [0.5, 0.0]])
        new, said2 = M.blend(old, said, first, w1)
        np.testing.assert_allclose(new[0, 1], 0.2)                       # no view touched it: its own colour, exactly
        self.assertAlmostEqual(float(new[0, 0, 0]), (0.2 * 0.03 + 0.8) / 1.03)   # the view, bar its own small say
        self.assertGreater(float(new[0, 0, 0]), float(new[1, 0, 0]))     # half the weight: less of the view
        second = np.full((2, 2, 3), 0.4)
        newer, _ = M.blend(new, said2, second, np.array([[1.0, 0.0], [0.0, 0.0]]))
        self.assertTrue(0.4 < float(newer[0, 0, 0]) < float(new[0, 0, 0]))   # a second view moves it by its share
        np.testing.assert_allclose(newer[1, 0], new[1, 0])               # ... and only where it looks

    def test_srgb_and_linear_are_each_others_inverse(self):
        c = np.linspace(0.0, 1.0, 23)
        np.testing.assert_allclose(M.linear_to_srgb(M.srgb_to_linear(c)), c, atol=1e-9)
        self.assertAlmostEqual(float(M.srgb_to_linear(0.5)), 0.2140, places=3)

    def test_a_redraw_is_brought_to_the_first_ones_colours(self):
        rng = np.random.default_rng(1)
        first = rng.uniform(0.3, 0.6, (16, 16, 3))
        other = np.clip(first * 0.5 + rng.uniform(0.0, 0.05, first.shape), 0, 1)     # darker, flatter
        got = M.match_colour(other, first, keep=0.0)
        for c in range(3):
            self.assertAlmostEqual(float(got[..., c].mean()), float(first[..., c].mean()), places=6)
            self.assertAlmostEqual(float(got[..., c].std()), float(first[..., c].std()), places=6)
        np.testing.assert_allclose(M.match_colour(first, first), first, atol=1e-12)


class TestMaps(unittest.TestCase):
    def test_light_is_high_a_ramp_rising_right_leans_left_and_rising_up_leans_down(self):
        h, w = 64, 64
        right = np.tile(np.linspace(0.1, 0.9, w), (h, 1))                 # lighter to the right
        _c, _r, n = M.maps(np.stack([right] * 3, axis=-1), normal_strength=40.0)
        self.assertLess(float(n[32, 32, 0]), 0.5)                          # the surface rises right: it faces left
        self.assertAlmostEqual(float(n[32, 32, 1]), 0.5, places=3)
        self.assertGreater(float(n[32, 32, 2]), 0.5)
        up = np.tile(np.linspace(0.9, 0.1, h)[:, None], (1, w))            # lighter at the TOP of the picture
        _c, _r, n = M.maps(np.stack([up] * 3, axis=-1), normal_strength=40.0)
        self.assertLess(float(n[32, 32, 1]), 0.5)                          # rises UP the picture: it faces down

    def test_a_dark_carved_line_is_a_groove_whose_walls_face_each_other(self):
        img = np.full((64, 64, 3), 0.7)
        img[:, 30:34] = 0.2                                                # a dark vertical line
        _c, rough, n = M.maps(img, normal_strength=30.0)
        self.assertGreater(float(n[32, 29, 0]), 0.5)                       # the left wall faces right, into the groove
        self.assertLess(float(n[32, 34, 0]), 0.5)                          # the right wall faces left
        self.assertGreater(float(rough[32, 31]), float(rough[32, 10]))     # the recess is duller than the face

    def test_gold_keeps_the_light_and_dark_and_black_padding_does_not_set_the_range(self):
        img = np.zeros((32, 32, 3))
        img[8:24, 8:24] = np.linspace(0.2, 0.6, 16)[None, :, None]         # a used island on black padding
        gold, _r, _n = M.maps(img, metal_ramp=M.GOLD)
        lum = gold @ np.array([0.2126, 0.7152, 0.0722])
        self.assertTrue(np.all(np.diff(lum[16, 8:24]) >= -1e-9))           # darker stays darker
        self.assertGreater(float(gold[16, 23, 0]), 0.95)                   # its brightest texel: bright gold ...
        self.assertGreater(float(gold[16, 23, 0]), float(gold[16, 23, 2]) + 0.3)   # ... and gold, not white
        self.assertLess(float(lum[16, 8]), 0.12)                           # its darkest: the patina
        plain, _r, _n = M.maps(img)
        np.testing.assert_allclose(plain, img)                             # without a ramp: its own colour


class TestFold(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(4)
        head_a = rng.uniform(0.0, 0.35, 6000)
        head_c = rng.uniform(-0.15, 0.15, 6000)
        wing_a = rng.uniform(0.35, 1.0, 12000)
        side = np.where(rng.uniform(size=12000) < 0.5, 1.0, -1.0)
        wing_c = side * (0.13 + math.tan(math.radians(28.0)) * (wing_a - 0.35)) + rng.uniform(-0.04, 0.04, 12000)
        self.along, self.across = np.concatenate([head_a, wing_a]), np.concatenate([head_c, wing_c])

    def test_the_wings_part_where_the_head_ends_and_each_splays_28_degrees(self):
        split = M.find_split(self.along, self.across)
        self.assertAlmostEqual(split, 0.35, delta=0.02)
        wings = M.splay(self.along, self.across, split)
        self.assertAlmostEqual(wings[0][0], 28.0, delta=1.0)
        self.assertAlmostEqual(wings[1][0], 28.0, delta=1.0)
        self.assertAlmostEqual(wings[0][1], 0.13, delta=0.02)
        self.assertAlmostEqual(wings[1][1], -0.13, delta=0.02)
        self.assertIsNone(M.find_split(np.linspace(0, 1, 500), np.zeros(500)))   # one solid body: nothing parts

    def test_folded_they_run_straight_back_and_the_head_has_not_moved(self):
        split = M.find_split(self.along, self.across)
        wings = M.splay(self.along, self.across, split)
        a2, c2 = M.fold(self.along, self.across, split, wings)
        ahead = self.along <= split
        np.testing.assert_allclose(a2[ahead], self.along[ahead])
        np.testing.assert_allclose(c2[ahead], self.across[ahead])
        far = a2 > split + 0.15                                            # past the eased stretch
        for side in (1.0, -1.0):
            sel = far & (np.sign(self.across) == side)
            slope = np.polyfit(a2[sel], c2[sel], 1)[0]
            self.assertLess(abs(math.degrees(math.atan(slope))), 1.5)      # straight back
        self.assertLess(c2.max() - c2.min(), 0.6 * (self.across.max() - self.across.min()))   # no longer as wide
        self.assertAlmostEqual(float(c2.max()), float(-c2.min()), delta=0.03)                # still symmetric
        wide = M.flare(a2, c2, 1.6)                                        # the wings out to their host's width ...
        nose = a2 < a2.min() + 0.2 * (a2.max() - a2.min())
        np.testing.assert_allclose(wide[nose], c2[nose])                   # ... the head as it was
        back = a2 > a2.min() + 0.52 * (a2.max() - a2.min())                 # (the flare ends at half the length)
        np.testing.assert_allclose(wide[back], c2[back] * 1.6)
        mid = (~nose) & (~back)
        self.assertTrue(np.all(np.abs(wide[mid]) >= np.abs(c2[mid]) - 1e-12))   # eased between: never narrower
        self.assertTrue(np.all(np.abs(wide[mid]) <= np.abs(c2[mid]) * 1.6 + 1e-12))
        np.testing.assert_allclose(M.flare(a2, c2, 1.0), c2)               # a factor of 1 moves nothing
        kept, kept_c = M.fold(self.along, self.across, split, wings, keep=90.0)   # asked to keep all of the splay
        np.testing.assert_allclose(kept, self.along)                               # (the measured one is 28 and a bit)
        np.testing.assert_allclose(kept_c, self.across)

    def test_a_wedge_is_levelled_to_one_width_behind_the_head(self):
        rng = np.random.default_rng(3)
        along = rng.uniform(0.0, 1.0, 40000)
        half = 0.10 + 0.25 * along                                         # a wedge: 0.10 at the nose, 0.35 at the tail
        across = rng.uniform(-1.0, 1.0, along.size) * half
        out = M.level(along, across, 0.5, start=0.30, end=0.50)
        head = along < 0.28
        np.testing.assert_allclose(out[head], across[head])                # the head has not moved
        for lo_, hi_ in ((0.52, 0.60), (0.70, 0.80), (0.90, 0.99)):        # behind it: one width, 0.5 of the length
            band = (along > lo_) & (along < hi_)
            self.assertAlmostEqual(float(np.abs(out[band]).max()), 0.25, delta=0.012)
        mid_band = (along > 0.38) & (along < 0.42)                         # in between: on its way there
        self.assertGreater(float(np.abs(out[mid_band]).max()), float(np.abs(across[mid_band]).max()))
        self.assertLess(float(np.abs(out[mid_band]).max()), 0.25)
        self.assertTrue(np.all(np.sign(out) == np.sign(across)))           # no point crosses the middle plane
        tail = along > 0.9                                                 # ... and the tail came IN (it was 0.34 wide)
        self.assertLess(float(np.abs(out[tail]).max()), float(np.abs(across[tail]).max()))

    def test_a_tail_lengthens_only_what_lies_behind_the_head_and_eases_in(self):
        along = np.linspace(2.0, 3.0, 1001)                                # a part one unit long, its nose at 2.0
        out = M.tail(along, 2.0, start=0.4, end=0.6)
        head = along <= 2.4
        np.testing.assert_allclose(out[head], along[head], atol=1e-9)      # the head has not moved
        self.assertTrue(np.all(np.diff(out) > 0))                          # nothing folds over
        step = np.diff(out) / np.diff(along)
        np.testing.assert_allclose(step[along[:-1] > 2.62], 2.0, atol=1e-3)   # behind the ease: twice as long
        mid = step[(along[:-1] > 2.45) & (along[:-1] < 2.55)]
        self.assertTrue(np.all((mid > 1.05) & (mid < 1.95)))               # in between: on its way, no step
        self.assertAlmostEqual(float(out.max() - out.min()), 0.4 + 0.2 * 1.5 + 0.4 * 2.0, places=3)
        np.testing.assert_allclose(M.tail(along, 1.0), along)              # a factor of 1 moves nothing

    def test_a_snout_lengthens_only_what_lies_ahead_of_the_eyes(self):
        along = np.linspace(0.0, 1.0, 101)
        out = M.snout(along, 1.25, upto=0.2)
        np.testing.assert_allclose(out[along >= 0.2], along[along >= 0.2])   # behind the eyes: as it was
        self.assertAlmostEqual(float(out[0]), 0.2 - 0.2 * 1.25)              # the nose: a quarter further out
        self.assertTrue(np.all(np.diff(out) > 0))                            # nothing folds over
        np.testing.assert_allclose(M.snout(along, 1.0), along)

    def test_a_nod_drops_the_nose_and_leaves_everything_behind_the_hinge(self):
        along = np.array([0.0, 0.1, 0.3, 0.6, 1.0])
        up = np.array([0.4, 0.4, 0.42, 0.9, 0.0])                            # (the last two give the height its range)
        a2, z2 = M.nod(along, up, 20.0, hinge=0.30, height=0.42, ease=0.12)
        np.testing.assert_allclose(a2[2:], along[2:], atol=1e-12)            # at and behind the hinge: unmoved
        np.testing.assert_allclose(z2[2:], up[2:], atol=1e-12)
        self.assertLess(float(z2[0]), float(up[0]) - 0.08)                   # the nose has dropped ...
        lever = math.hypot(0.3, 0.4 - 0.378)
        self.assertAlmostEqual(math.hypot(a2[0] - 0.3, z2[0] - 0.378), lever, places=9)   # ... on a rigid turn
        self.assertGreater(float(a2[0]), 0.0)                                # and drawn back a little, not forward
        flat_a, flat_z = M.nod(along, up, 0.0)
        np.testing.assert_allclose(flat_a, along)
        np.testing.assert_allclose(flat_z, up)


if __name__ == "__main__":
    unittest.main()
