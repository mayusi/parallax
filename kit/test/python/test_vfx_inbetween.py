"""Unit tests of motion vectors in the texture packer (kit/vfx/fxfinish.py `post.inbetween`).
Run: python -m pytest kit/test/python/test_vfx_inbetween.py -q"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import fxfinish as F  # noqa: E402
import methods as M  # noqa: E402

N = 96


def disc(cx, cy, radius=16.0, light=1.0, colour=(0.9, 0.6, 0.3)):
    """a straight-alpha cell, as the packer's looks are"""
    yy, xx = np.mgrid[0:N, 0:N]
    a = np.clip((radius - np.hypot(xx - cx, yy - cy)) / 3 + 0.5, 0, 1) * light
    return np.dstack([np.full((N, N), c) * (a > 0) for c in colour] + [a]).astype(np.float64)


def middle(c):
    yy, xx = np.mgrid[0:N, 0:N]
    return float((xx * c[..., 3]).sum() / c[..., 3].sum()), float((yy * c[..., 3]).sum() / c[..., 3].sum())


class TheBlock(unittest.TestCase):
    def test_what_is_wrong_is_said_in_words(self):
        for ib, word in ((2, "is true, or a block"), ({"times": 2}, "does not read times"), ({"loop": 1}, "loop is true or false")):
            with self.assertRaisesRegex(ValueError, word, msg=str(ib)):
                F.inbetween_block(ib)
        self.assertIsNone(F.inbetween_block(None))
        self.assertIsNone(F.inbetween_block(False))
        self.assertEqual(F.inbetween_block(True), {"loop": False})
        self.assertEqual(F.inbetween_block({}), {"loop": False})                          # (an empty block is ON, as the gate reads it)
        self.assertEqual(F.inbetween_block({"loop": True}), {"loop": True})

    def test_every_cell_is_a_moment_of_the_frames_own_timeline(self):
        got = F.moments(4, 8, False)
        self.assertEqual((got[0], got[-1]), ((0, 0.0), (3, 0.0)))                         # the first frame, the last frame
        at = [i + t for i, t in got]
        self.assertTrue(all(abs((b - a) - 3 / 7) < 1e-9 for a, b in zip(at, at[1:])))     # evenly on
        self.assertEqual(F.moments(4, 8, True), [(0, 0.0), (0, 0.5), (1, 0.0), (1, 0.5), (2, 0.0), (2, 0.5), (3, 0.0), (3, 0.5)])
        self.assertEqual([m for m in F.moments(6, 16, False) if m[1] == 0.0], [(0, 0.0), (1, 0.0), (2, 0.0), (3, 0.0), (4, 0.0), (5, 0.0)])
        self.assertEqual(len(F.moments(3, 64, True)), 64)


class TheVectors(unittest.TestCase):
    def test_a_slide_is_measured_as_it_is(self):
        a, b = F._premult(disc(40, 48)), F._premult(disc(48, 44))
        flow = F.motion(a, b)
        inside = a[..., 3] > 0.9
        self.assertAlmostEqual(float(np.median(flow[..., 0][inside])), 8.0, delta=0.6)
        self.assertAlmostEqual(float(np.median(flow[..., 1][inside])), -4.0, delta=0.6)

    def test_a_cell_carried_all_the_way_is_the_next_cell(self):
        a, b = F._premult(disc(40, 48)), F._premult(disc(48, 48))
        self.assertLess(float(np.abs(F.moved(a, F.motion(a, b), 1.0) - b).mean()), 0.2 * float(np.abs(a - b).mean()))
        self.assertTrue(np.allclose(F.moved(a, np.zeros((N, N, 2), np.float32), 0.7), a))     # no vectors: it stays


class TheInBetweens(unittest.TestCase):
    def test_the_grid_is_filled_and_each_cell_is_where_its_moment_puts_it(self):
        frames = [disc(x, 48) for x in (30, 40, 50, 60)]
        for count in (8, 16):
            out = F.inbetween(frames, {"loop": False}, count)
            self.assertEqual(len(out), count)
            self.assertIs(out[0], frames[0])
            self.assertIs(out[-1], frames[-1])
            self.assertTrue(all(float(c[..., 3].max()) > 0.9 for c in out))               # no cell is empty
            xs = [middle(c)[0] for c in out]
            want = [30 + 30 * k / (count - 1) for k in range(count)]
            self.assertLess(max(abs(a - b) for a, b in zip(xs, want)), 1.0, count)

    def test_a_cell_between_is_one_shape_where_a_cross_fade_is_two(self):
        a, b = disc(40, 48, radius=14), disc(56, 48, radius=14)                          # 16 px on: more than half its width
        mid = F.inbetween([a, b], {"loop": False}, 3)[1]
        row = mid[48, :, 3]
        solid = np.nonzero(row > 0.5)[0]
        self.assertAlmostEqual(float(solid.mean()), 48.0, delta=1.0)                      # one disc, at the half-way place
        self.assertAlmostEqual(len(solid), 28, delta=3)                                   # as wide as the disc is
        self.assertGreater(float(row[48]), 0.95)
        fade = 0.5 * (a[48, :, 3] + b[48, :, 3])
        self.assertGreater(int((fade > 0.25).sum()), 40)                                  # (a cross-fade: a smear 44 px wide,
        self.assertLess(int((fade > 0.75).sum()), 16)                                     #  solid only where the two overlap)

    def test_colour_is_carried_with_the_shape_and_stays_in_range(self):
        mid = F.inbetween([disc(36, 48, colour=(1.0, 0.2, 0.1)), disc(46, 48, colour=(1.0, 0.2, 0.1))], {"loop": False}, 3)[1]
        self.assertTrue(np.allclose(mid[48, 41, :3], [1.0, 0.2, 0.1], atol=0.03))
        self.assertTrue((mid >= 0).all() and (mid <= 1).all())
        self.assertEqual(mid.dtype, np.float64)

    def test_a_loop_ends_one_step_short_of_its_first_frame(self):
        frames = [disc(30, 48), disc(40, 48), disc(50, 48), disc(40, 48)]                 # there and back
        out = F.inbetween(frames, {"loop": True}, 8)
        self.assertEqual(len(out), 8)
        self.assertAlmostEqual(middle(out[7])[0], 35.0, delta=1.0)                        # between frame 4 (at 40) and frame 1 (at 30)

    def test_a_picture_that_stands_still_is_refused(self):
        with self.assertRaisesRegex(ValueError, "found no motion"):
            F.inbetween([disc(48, 48), disc(48, 48), disc(48, 48)], {"loop": False}, 8)

    def test_a_picture_that_changes_instead_of_moving_is_refused(self):
        with self.assertRaisesRegex(ValueError, "over the whole sheet"):
            F.inbetween([disc(48, 48, light=v) for v in (1.0, 0.7, 0.4)], {"loop": False}, 8)
        with self.assertRaisesRegex(ValueError, "over the whole sheet"):
            F.inbetween([disc(12, 48, radius=6), disc(80, 48, radius=6)], {"loop": False}, 4)

    def test_a_small_thing_that_jumps_beside_a_big_one_that_drifts_is_refused(self):
        def frame(k):
            big, spark = disc(30 + 4 * k, 34, radius=18), disc(20 if k % 2 == 0 else 60, 82, radius=4)
            a = np.maximum(big[..., 3], spark[..., 3])
            return np.dstack([np.full((N, N), c) * (a > 0) for c in (0.9, 0.6, 0.3)] + [a])
        with self.assertRaisesRegex(ValueError, "a part of the picture is not followed"):
            F.inbetween([frame(k) for k in range(4)], {"loop": False}, 8)

    def test_a_held_frame_among_moving_ones_does_not_refuse_the_sheet(self):
        frames = [disc(30, 48), disc(40, 48), disc(40, 48, light=0.98), disc(50, 48)]     # a hold that dims a little, then on
        out = F.inbetween(frames, {"loop": False}, 8)
        self.assertEqual(len(out), 8)


class TheRegister(unittest.TestCase):
    def test_motion_vectors_are_a_sheet_packed_with_in_betweens(self):
        m = M.load()[1]["motion_vectors"]
        self.assertEqual(m["state"], "has")
        want = m["proof"][0]["texture"]
        self.assertTrue(M.texture_proves(want, {"recipe": "flame", "post": {"inbetween": True}}))
        self.assertTrue(M.texture_proves(want, {"recipe": "flame", "post": {"inbetween": {"loop": True}}}))
        self.assertFalse(M.texture_proves(want, {"recipe": "flame", "post": {"inbetween": False}}))
        self.assertFalse(M.texture_proves(want, {"recipe": "flame", "post": {"edges": {}}}))
        self.assertFalse(M.texture_proves(want, {"recipe": "flame"}))
        self.assertFalse(M.texture_proves(want, None))


if __name__ == "__main__":
    unittest.main()
