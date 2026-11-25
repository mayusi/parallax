"""Unit tests of CHROMATIC ABERRATION baked into a texture (kit/vfx/fxfinish.py `post.aberration`).
Run: python -m pytest kit/test/python/test_vfx_aberration.py -q"""
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import fxfinish as F  # noqa: E402
import methods as M  # noqa: E402

N = 128
PASS = {"alpha": "coverage", "tonemap": False, "border": 0}
YY, XX = np.mgrid[0:N, 0:N]
R = np.hypot(XX - 63.5, YY - 63.5)
DISC = (R < 40).astype(np.float64)
WHITE = np.dstack([np.ones((N, N, 3)), DISC])


def seen(f):
    return f[..., :3] * f[..., 3:]


class TheSplit(unittest.TestCase):
    def test_radial_red_reaches_past_the_rim_and_blue_stops_short_of_it(self):
        o = F.apply_aberration(WHITE, {"amount": 0.04})
        np.testing.assert_allclose(o[64, 22], [1, 0, 0, 1], atol=0.02)      # outside the disc's rim: red alone
        np.testing.assert_allclose(o[64, 105], [1, 0, 0, 1], atol=0.02)     # the same on the other side
        np.testing.assert_allclose(o[64, 25], [1, 1, 0, 1], atol=0.02)      # just inside it: no blue yet (yellow)
        np.testing.assert_allclose(o[64, 64], [1, 1, 1, 1], atol=1e-6)      # the middle is untouched
        np.testing.assert_allclose(o[40, 64], [1, 1, 1, 1], atol=1e-6)
        self.assertEqual(o[64, 8, 3], 0)                                    # and nothing far outside

    def test_radial_parts_more_the_further_from_the_middle(self):
        def fringe(radius):
            disc = (R < radius).astype(np.float64)
            o = F.apply_aberration(np.dstack([np.ones((N, N, 3)), disc]), {"amount": 0.04})
            row = o[64]
            return int(((row[:, 0] > 0.5) & (row[:, 2] < 0.5) & (row[:, 3] > 0.5)).sum())   # red-or-yellow pixels on one row
        self.assertGreater(fringe(50), fringe(25) + 2)

    def test_the_rim_moves_by_the_amount_said(self):
        # a thin white ring at radius 50 of a 128 cell, amount 0.04: red is drawn 1.08 times as large -> 4 px further out
        ring = (np.abs(R - 50) < 1.5).astype(np.float64)
        o = F.apply_aberration(np.dstack([np.ones((N, N, 3)), ring]), {"amount": 0.04})
        red_at = float((seen(o)[64, 64:, 0] * np.arange(64)).sum() / seen(o)[64, 64:, 0].sum())
        green_at = float((seen(o)[64, 64:, 1] * np.arange(64)).sum() / seen(o)[64, 64:, 1].sum())
        blue_at = float((seen(o)[64, 64:, 2] * np.arange(64)).sum() / seen(o)[64, 64:, 2].sum())
        self.assertAlmostEqual(red_at - green_at, 50 * 0.08, delta=0.4)
        self.assertAlmostEqual(green_at - blue_at, 50 * 0.08, delta=0.4)

    def test_axis_slides_red_one_way_and_blue_the_other_the_same_everywhere(self):
        o = F.apply_aberration(WHITE, {"amount": 0.04, "mode": "axis", "angle": 0})
        np.testing.assert_allclose(o[64, 106], [1, 0, 0, 1], atol=0.02)     # red leads to the right
        np.testing.assert_allclose(o[64, 21], [0, 0, 1, 1], atol=0.02)      # blue trails to the left
        np.testing.assert_allclose(o[64, 64], [1, 1, 1, 1], atol=1e-6)
        up = F.apply_aberration(WHITE, {"amount": 0.04, "mode": "axis", "angle": 90})
        np.testing.assert_allclose(up[21, 64], [1, 0, 0, 1], atol=0.02)     # 90 degrees: red goes UP the picture
        np.testing.assert_allclose(up[106, 64], [0, 0, 1, 1], atol=0.02)

    def test_green_and_the_whole_light_of_each_colour_are_kept(self):
        o = F.apply_aberration(WHITE, {"amount": 0.04, "mode": "axis", "angle": 30})
        np.testing.assert_allclose(seen(o)[..., 1], seen(WHITE)[..., 1], atol=1e-9)          # green does not move
        for c in (0, 2):                                                    # a slide loses no light of a colour
            self.assertAlmostEqual(float(seen(o)[..., c].sum()), float(seen(WHITE)[..., c].sum()), delta=2.0)

    def test_a_colour_that_is_not_there_makes_no_fringe(self):
        green = np.dstack([np.zeros((N, N)), np.ones((N, N)), np.zeros((N, N)), DISC])
        o = F.apply_aberration(green, {"amount": 0.04})
        self.assertEqual(float(seen(o)[..., 0].max()), 0)
        self.assertEqual(float(seen(o)[..., 2].max()), 0)
        np.testing.assert_allclose(seen(o)[..., 1], seen(green)[..., 1], atol=1e-9)
        np.testing.assert_allclose(o[..., 3], DISC, atol=1e-9)              # and no opaque ring of nothing round it

    def test_a_shape_with_little_red_gets_a_faint_red_fringe_never_a_dark_ring(self):
        ice = np.dstack([np.full((N, N), 0.3), np.full((N, N), 0.6), np.ones((N, N)), DISC])
        o = F.apply_aberration(ice, {"amount": 0.04})
        out = o[64, 22]                                                     # just outside the rim: red's light alone
        np.testing.assert_allclose(out[:3], [1, 0, 0], atol=0.02)           # it is RED there
        self.assertAlmostEqual(float(out[3]), 0.3, delta=0.03)              # as opaque as that light is bright: faint
        dark = (o[..., :3].max(axis=2) < 0.25) & (o[..., 3] > 0.5)          # an opaque dark pixel anywhere = the ring
        self.assertEqual(int(dark.sum()), 0)
        np.testing.assert_allclose(seen(o)[..., 1], seen(ice)[..., 1], atol=1e-9)

    def test_a_picture_that_fills_its_cell_keeps_its_colours_at_the_edge(self):
        full = np.dstack([np.full((N, N, 3), 0.5), np.ones((N, N))])
        for ab in ({"amount": 0.03}, {"amount": 0.03, "mode": "axis", "angle": 0}):
            np.testing.assert_allclose(F.apply_aberration(full, ab), full, atol=1e-6, err_msg=str(ab))

    def test_axis_slides_the_same_length_whichever_way_on_a_cell_that_is_not_square(self):
        yy, xx = np.mgrid[0:64, 0:256]
        dot = (np.hypot(xx - 127.5, yy - 31.5) < 6).astype(np.float64)
        f = np.dstack([np.ones((64, 256, 3)), dot])

        def red_move(angle):
            o = F.apply_aberration(f, {"amount": 0.05, "mode": "axis", "angle": angle})
            r = seen(o)[..., 0]
            return (float((r * xx).sum() / r.sum()) - 127.5, 31.5 - float((r * yy).sum() / r.sum()))   # (right, up)

        right, up, diag = red_move(0), red_move(90), red_move(45)
        self.assertAlmostEqual(right[0], 3.2, delta=0.1)                    # 0.05 of the SHORT side (64)
        self.assertAlmostEqual(up[1], 3.2, delta=0.1)                       # the same length going up
        self.assertAlmostEqual(diag[0], diag[1], delta=0.1)                 # and 45 degrees is 45 degrees

    def test_colours_stay_colours(self):
        o = F.apply_aberration(WHITE, {"amount": 0.1})
        self.assertTrue(0 <= o.min() and o.max() <= 1)
        self.assertFalse(np.isnan(o).any())


class ThePacker(unittest.TestCase):
    def build(self, frames, post, **spec):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "t"))
            for i, f in enumerate(frames):
                np.save(os.path.join(tmp, "t", f"{i:03d}.npy"), f.astype(np.float32))
            return F.build("t", dict({"engine": "fx", "grid": 1, "frames": len(frames), "post": post}, **spec), tmp)

    def test_a_sheet_is_packed_with_its_colours_parted(self):
        img = self.build([WHITE], dict(PASS, aberration={"amount": 0.04}))[0]
        px = np.asarray(img).astype(int)
        self.assertTrue(px[64, 22, 0] > 240 and px[64, 22, 1] < 15 and px[64, 22, 2] < 15 and px[64, 22, 3] > 240)
        self.assertTrue((px[64, 64] > 250).all())
        plain = np.asarray(self.build([WHITE], dict(PASS))[0])
        self.assertFalse(np.array_equal(px, plain))
        for off in (None, False):
            np.testing.assert_array_equal(np.asarray(self.build([WHITE], dict(PASS, aberration=off))[0]), plain)

    def test_it_is_the_last_look_a_drawn_line_parts_too(self):
        two = np.dstack([np.where(XX < 64, 0.9, 0.3)[..., None] * np.ones(3) * DISC[..., None], DISC])
        img = self.build([two], dict(PASS, edges={"color": [1.0, 1.0, 1.0]}, aberration={"amount": 0.04, "mode": "axis", "angle": 0}))[0]
        px = np.asarray(img).astype(int)
        row = px[30]                                                        # across the white line down the tones' border
        self.assertTrue(((row[:, 0] > 200) & (row[:, 2] < 150)).any() and ((row[:, 2] > 200) & (row[:, 0] < 150)).any())

    def test_the_fringe_is_not_counted_as_the_shape_running_off_its_cell(self):
        big = [np.dstack([np.ones((N, N, 3)), (R < 58).astype(np.float64)])]
        self.assertEqual(self.build(big, {"alpha": "coverage", "tonemap": False, "aberration": {"amount": 0.03}})[2],
                         self.build(big, {"alpha": "coverage", "tonemap": False})[2])

    def test_a_fringe_that_reaches_the_cells_edge_is_said(self):
        """a review leftover (stage 12): a red fringe pushed past the cell's edge was cut without a warning"""
        def said(disc):
            built = self.build([np.dstack([np.ones((N, N, 3)) * disc[..., None], disc]).astype(np.float32)], dict(PASS, aberration={"amount": 0.06}), grid=1)
            row = {c["name"]: c for c in F.check(built[0], built[1], built[2], built[3], built[4], False)}["fringe_whole"]
            return row["ok"], row["severity"], built[0].info["fringe_cut"]
        ok, _, cut = said(DISC)                                             # a disc with room round it: its fringe is whole
        self.assertTrue(ok)
        self.assertLess(cut, 0.05)
        ok, severity, cut = said((R < 62).astype(np.float64))               # a disc that nearly fills its cell: red runs off it
        self.assertEqual((ok, severity), (False, "warn"))
        self.assertGreater(cut, F.FRINGE_CUT)
        self.assertEqual(F.fringe_cut(np.ones((8, 8, 4)), np.ones((8, 8, 4))), 0.0)   # a picture that fills its cell loses nothing

    def test_a_picture_with_nothing_to_part_is_refused(self):
        green = np.dstack([np.zeros((N, N)), np.ones((N, N)), np.zeros((N, N)), DISC])
        full = np.dstack([np.full((N, N, 3), 0.5), np.ones((N, N))])
        for name, frame in (("empty", np.zeros((N, N, 4))), ("one colour", green), ("flat to the rim", full)):
            with self.assertRaisesRegex(ValueError, "parted next to nothing", msg=name):
                self.build([frame], dict(PASS, aberration={"amount": 0.04}))

    def test_a_small_shape_at_the_middle_is_said_as_it_is_and_axis_does_part_it(self):
        yy, xx = np.mgrid[0:512, 0:512]
        dot = (np.hypot(xx - 255.5, yy - 255.5) < 4).astype(np.float64)
        f = np.dstack([np.ones((512, 512, 3)), dot])
        with self.assertRaisesRegex(ValueError, "sits small at the cell's middle"):
            self.build([f], dict(PASS, aberration={"amount": 0.02}))
        self.build([f], dict(PASS, aberration={"amount": 0.02, "mode": "axis"}))     # slid apart, it shows

    def test_under_a_pixel_is_measured_on_the_sheet_as_it_is_saved(self):
        yy, xx = np.mgrid[0:512, 0:512]
        f = np.dstack([np.ones((512, 512, 3)), (np.hypot(xx - 255.5, yy - 255.5) < 200).astype(np.float64)])
        self.build([f], dict(PASS, aberration={"amount": 0.004}))                    # 2 px on a 512 cell
        with self.assertRaisesRegex(ValueError, "under a pixel"):
            self.build([f], dict(PASS, aberration={"amount": 0.004}), size=128)      # saved at 128: half a pixel

    def test_a_beams_texture_is_refused(self):
        with self.assertRaisesRegex(ValueError, "beam's texture"):
            self.build([WHITE], dict(PASS, aberration={"amount": 0.04}), beam=True)

    def test_a_wrong_block_is_refused_in_words(self):
        for ab, word in ((True, "is a block"), (0.03, "is a block"), ({"strength": 1}, "does not read strength"), ({"amount": 0.5}, "amount is 0.004 to 0.1"),
                         ({"amount": True}, "amount is 0.004"), ({"amount": float("nan")}, "amount is 0.004"), ({"mode": "lens"}, 'mode is "radial"'),
                         ({"angle": 30}, 'read with "mode": "axis" only'), ({"mode": "axis", "angle": 999}, "angle is degrees"),
                         ({"amount": 0.005}, "under a pixel")):
            with self.assertRaisesRegex(ValueError, word, msg=str(ab)):
                self.build([WHITE], dict(PASS, aberration=ab))

    def test_a_strip_that_wraps_is_refused(self):
        strip = np.dstack([np.ones((32, N, 3)), np.ones((32, N))])
        with self.assertRaisesRegex(ValueError, "not for a strip that wraps"):
            self.build([strip], {"alpha": "coverage", "tonemap": False, "aberration": {"amount": 0.05}}, wrap=True)


class TheRegister(unittest.TestCase):
    def test_chromatic_aberration_is_the_baked_split_or_the_screens_fringe(self):
        _, by = M.load()
        m = by["chromatic_aberration"]
        self.assertEqual(m["state"], "has")

        def specs(post):
            class One:
                def get(_, key):
                    return {"engine": "fx", "recipe": "made", "post": post} if key == "tex" else None
            return One()

        def tex(post):
            return M.proved(m, [{"kind": "sprite", "texture": "tex", "life": 1}], specs(post), ".", "s") is not None

        self.assertTrue(tex({"aberration": {"amount": 0.03}}))
        self.assertFalse(tex({"aberration": False}))
        self.assertFalse(tex({"edges": {}}))
        self.assertIsNotNone(M.proved(m, [{"kind": "lens", "life": 1, "aberration": 0.6}], specs({}), ".", "s"))
        self.assertIsNone(M.proved(m, [{"kind": "lens", "life": 1, "aberration": 0}], specs({}), ".", "s"))


if __name__ == "__main__":
    unittest.main()
