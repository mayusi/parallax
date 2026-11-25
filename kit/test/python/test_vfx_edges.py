"""Unit tests of EDGE DETECTION on a texture (kit/vfx/fxfinish.py `post.edges`).
Run: python -m pytest kit/test/python/test_vfx_edges.py -q"""
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
TWO = np.where(XX < 64, 0.9, 0.3)


def frame(tone, a=DISC):
    return np.dstack([tone * a] * 3 + [a]).astype(np.float32)  # premultiplied, as frames on disk are


def straight(tone, a=DISC):
    return np.dstack([tone] * 3 + [a]).astype(np.float64)


def lines(tone, a=DISC, **ed):
    return F.edge_lines(np.dstack([tone] * 3).astype(np.float64), a, ed)


class TheLine(unittest.TestCase):
    def test_a_step_inside_the_shape_is_a_line_as_well_as_its_silhouette(self):
        ln = lines(TWO)
        self.assertGreater(ln[64, 24], 0.9)                         # the silhouette, left
        self.assertGreater(ln[64, 103], 0.9)                        # and right, where the tone is dark
        self.assertGreater(max(ln[50, 63], ln[50, 64]), 0.9)        # the border between the two tones
        self.assertEqual(ln[64, 44], 0)                             # the middle of the bright tone
        self.assertEqual(ln[64, 84], 0)                             # the middle of the dark tone
        self.assertEqual(ln[8, 8], 0)                               # outside

    def test_one_flat_tone_has_its_silhouette_only(self):
        ln = lines(np.full((N, N), 0.7))
        self.assertGreater(ln[64, 24], 0.9)
        self.assertEqual(float(ln[R < 34].max()), 0)

    def test_a_step_in_colour_alone_is_a_line(self):
        # red against a green of the same brightness: nothing steps in tone, and the eye sees an edge
        col = np.zeros((N, N, 3))
        col[..., 0] = XX < 64
        col[..., 1] = (XX >= 64) * 0.545
        ln = F.edge_lines(col, DISC, {})
        self.assertGreater(max(ln[50, 63], ln[50, 64]), 0.9)
        self.assertEqual(ln[64, 44], 0)

    def test_a_soft_ramp_is_no_edge(self):
        ramp = 0.3 + 0.6 * (XX - 24) / 80                            # the same two tones, 80 px apart
        self.assertEqual(float(lines(ramp)[R < 34].max()), 0)

    def test_a_soft_glow_has_no_edge_at_all(self):
        soft = np.exp(-(R / 30) ** 2)
        self.assertEqual(float(F.edge_lines(np.ones((N, N, 3)), soft, {}).max()), 0)

    def test_the_threshold_decides_how_sharp_a_step_is_a_line(self):
        faint = np.where(XX < 64, 0.5, 0.42)                         # a step of 0.08: about 0.03 a pixel
        self.assertEqual(float(lines(faint)[R < 34].max()), 0)
        self.assertGreater(float(lines(faint, threshold=0.015)[R < 34].max()), 0.5)

    def test_single_pixel_noise_is_not_drawn(self):
        rng = np.random.default_rng(3)
        noisy = 0.6 + (rng.random((N, N)) - 0.5) * 0.1
        self.assertLess(float((lines(noisy)[R < 34] > 0).mean()), 0.001)

    def test_grow_widens_the_line(self):
        self.assertGreater((lines(TWO, grow=2) > 0.5).sum(), (lines(TWO) > 0.5).sum() * 2)

    def test_a_strip_that_wraps_has_its_seam_measured(self):
        a = np.ones((32, N))
        tone = np.where(XX[:32] < 64, 0.9, 0.2)                      # a step at the middle AND across the seam
        col = np.dstack([tone] * 3)
        flat = F.edge_lines(col, a, {})
        joined = F.edge_lines(col, a, {}, wrap=True)
        self.assertEqual(flat[16, 0], 0)
        self.assertGreater(joined[16, 0], 0.9)
        self.assertGreater(joined[16, 64], 0.9)

    def test_without_the_silhouette_only_the_inner_steps_are_lines(self):
        ln = F.edge_lines(np.dstack([TWO] * 3), DISC, {}, silhouette=False)
        self.assertGreater(max(ln[50, 63], ln[50, 64]), 0.9)
        # (the shape's rim still steps in what is SEEN there - a bright fill ending - so only a dark rim is free of it)
        self.assertEqual(float(F.edge_lines(np.zeros((N, N, 3)), DISC, {}, silhouette=False).max()), 0)


class OnTheFrame(unittest.TestCase):
    def test_lines_are_drawn_over_the_picture_in_their_colour(self):
        f, _ = F.apply_edges(straight(TWO), {"color": [0.0, 0.0, 1.0]})
        np.testing.assert_allclose(f[64, 24, :3], [0, 0, 1], atol=0.02)
        np.testing.assert_allclose(f[64, 44, :3], [0.9] * 3, atol=0.01)   # the fill is untouched away from a line
        np.testing.assert_allclose(f[64, 84, :3], [0.3] * 3, atol=0.01)
        self.assertEqual(f[64, 44, 3], 1)
        self.assertEqual(f[8, 8, 3], 0)

    def test_a_bright_line_has_no_dark_fringe_where_it_leaves_the_shape(self):
        # outside the shape there is nothing under the line: wherever any of it shows, its colour is its own
        f, line = F.apply_edges(straight(np.full((N, N), 0.2)), {"color": [1.0, 1.0, 1.0]})
        fringe = (DISC == 0) & (line > 0.02)
        self.assertGreater(int(fringe.sum()), 50)
        self.assertGreater(float(f[fringe][:, :3].min()), 0.99)
        partial = fringe & (line < 0.9)
        self.assertGreater(int(partial.sum()), 10)                    # (the case a full-strength line would hide)
        np.testing.assert_allclose(f[partial][:, 3], line[partial])

    def test_keep_false_is_the_lines_alone(self):
        f, _ = F.apply_edges(straight(TWO), {"color": [1.0, 1.0, 1.0], "keep": False})
        self.assertGreater(f[64, 24, 3], 0.9)
        self.assertEqual(f[64, 44, 3], 0)                            # no fill
        self.assertEqual(f[8, 8, 3], 0)
        self.assertLess(float((f[..., 3] > 0.5).mean()), 0.1)

    def test_bands_get_their_lines_at_the_default_threshold(self):
        blob = np.exp(-(R / 25) ** 2)                                # a smooth falloff: no edge of its own inside
        self.assertEqual(float(F.apply_edges(F.finish_frame(frame(blob), dict(PASS), N), {})[1][R < 34].max()), 0)
        for bands in (3, 4):
            cel = F.finish_frame(frame(blob), dict(PASS, color="cel", bands=bands), N)
            self.assertGreater(int((F.apply_edges(cel, {})[1][R < 34] > 0.5).sum()), 200, bands)

    def test_the_frame_step_itself_does_not_draw_them(self):
        # (they are drawn after the dissolve, in build: finish_frame alone gives the picture without lines)
        np.testing.assert_array_equal(F.finish_frame(frame(TWO), dict(PASS), N), F.finish_frame(frame(TWO), dict(PASS, edges={}), N))


class ThePacker(unittest.TestCase):
    def build(self, frames, post, **spec):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "t"))
            for i, f in enumerate(frames):
                np.save(os.path.join(tmp, "t", f"{i:03d}.npy"), f)
            return F.build("t", dict({"engine": "fx", "grid": 2, "frames": len(frames), "post": post}, **spec), tmp)

    def cell(self, img, i, n=N):
        px = np.asarray(img).astype(np.float64) / 255
        r, c = divmod(i, 2)
        return px[r * n:(r + 1) * n, c * n:(c + 1) * n]

    def test_a_sheet_with_steps_is_packed_with_its_lines(self):
        img, grid, _, change, n = self.build([frame(TWO, (R < r).astype(np.float64)) for r in (25, 30, 35, 40)], dict(PASS, edges={"color": [0, 0, 0]}))
        self.assertEqual((img.size, grid, n), ((256, 256), (2, 2), 4))
        self.assertGreater(change, 0.0008)
        last = self.cell(img, 3)
        self.assertLess(float(last[64, 24, :3].max()), 0.1)          # the silhouette's line
        self.assertLess(float(min(last[50, 63, :3].max(), last[50, 64, :3].max())), 0.1)  # the tones' border
        self.assertAlmostEqual(float(last[64, 44, 0]), 0.9, delta=0.02)

    def test_a_sheet_lined_on_its_silhouette_alone_is_said(self):
        """a review leftover (stage 9): the packer could not tell a sheet with steps inside it from an outline"""
        flat = self.build([frame(0.8)], dict(PASS, edges={}), grid=1)
        stepped = self.build([frame(TWO)], dict(PASS, edges={}), grid=1)
        self.assertLess(flat[0].info["edge_inner"], F.EDGE_LEAST)
        self.assertGreaterEqual(stepped[0].info["edge_inner"], F.EDGE_LEAST)

        def said(built):
            return {c["name"]: c for c in F.check(built[0], built[1], built[2], built[3], built[4], False)}.get("inner_lines")
        self.assertEqual((said(flat)["ok"], said(flat)["severity"]), (False, "warn"))
        self.assertIn("outline", said(flat)["fix"])
        self.assertTrue(said(stepped)["ok"])
        plain = self.build([frame(TWO)], dict(PASS), grid=1)                # no edges asked: nothing is said of them
        self.assertIsNone({c["name"]: c for c in F.check(plain[0], plain[1], plain[2], plain[3], plain[4], False)}.get("inner_lines"))

    def test_a_tool_that_writes_its_spec_again_keeps_the_final_looks(self):
        import json
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.json")
            self.assertEqual(F.last_looks(path), {})                        # no spec yet
            json.dump({"post": dict(PASS, edges={"threshold": 0.05}, aberration={"amount": 0.02}, border=0.1)}, open(path, "w"))
            self.assertEqual(F.last_looks(path), {"edges": {"threshold": 0.05}, "aberration": {"amount": 0.02}})
            json.dump({"post": dict(PASS, edges=False)}, open(path, "w"))
            self.assertEqual(F.last_looks(path), {})                        # switched off is not a look to keep
            open(path, "w").write("not json")
            self.assertEqual(F.last_looks(path), {})

    def test_an_empty_block_is_the_step_at_its_defaults(self):
        fr = [frame(TWO)]
        a = np.asarray(self.build(fr, dict(PASS, edges={}), grid=1)[0])
        b = np.asarray(self.build(fr, dict(PASS, edges={"threshold": 0.08, "grow": 0, "keep": True}), grid=1)[0])
        np.testing.assert_array_equal(a, b)
        self.assertFalse(np.array_equal(a, np.asarray(self.build(fr, dict(PASS), grid=1)[0])))
        for off in (None, False):
            np.testing.assert_array_equal(np.asarray(self.build(fr, dict(PASS, edges=off), grid=1)[0]), np.asarray(self.build(fr, dict(PASS), grid=1)[0]))

    def test_a_sheet_that_asks_for_edges_and_has_none_is_refused(self):
        soft = [np.dstack([np.exp(-(R / r) ** 2)] * 4).astype(np.float32) for r in (20, 24, 28, 32)]
        with self.assertRaisesRegex(ValueError, "found no edge"):
            self.build(soft, dict(PASS, edges={}))
        self.build(soft, dict(PASS))                                 # the same sheet without the step is fine

    def test_one_frame_with_an_edge_is_enough(self):
        soft = np.dstack([np.exp(-(R / 24) ** 2)] * 4).astype(np.float32)
        self.build([soft, soft * 0.9, frame(TWO), soft * 0.8], dict(PASS, edges={}))

    def test_a_small_hard_shape_on_a_big_cell_is_a_real_line(self):
        yy, xx = np.mgrid[0:512, 0:512]
        dot = (np.hypot(xx - 256, yy - 256) < 6).astype(np.float32)
        self.build([np.dstack([dot] * 4)], dict(PASS, edges={}), grid=1)

    def test_a_dissolves_holes_get_their_lines(self):
        # the lines are found AFTER the baked dissolve: a hole it opens inside the shape has a line round it
        flat = [frame(np.full((N, N), 0.8)) for _ in range(4)]
        post = dict(PASS, erode={"start": 0.2, "end": 0.9, "scale": 4, "soft": 0.02, "density": 0}, edges={"color": [0, 0, 0]})
        img = self.build(flat, post, seed=2)[0]
        no_lines = self.build(flat, dict(post, edges=None), seed=2)[0]
        mid, plain = self.cell(img, 2), self.cell(no_lines, 2)
        inner = R < 30
        holes = inner & (plain[..., 3] < 0.05)
        self.assertGreater(int(holes.sum()), 200)                    # the dissolve did open the shape here
        dark = inner & (mid[..., :3].max(axis=2) < 0.2) & (mid[..., 3] > 0.8)
        self.assertGreater(int(dark.sum()), 100)                     # and there are ink lines inside the old silhouette
        self.assertEqual(int((inner & (plain[..., :3].max(axis=2) < 0.2) & (plain[..., 3] > 0.8)).sum()), 0)

    def test_an_ink_ring_is_not_lined_a_second_time(self):
        ring = dict(PASS, outline={"width": 3, "threshold": 0.45, "color": [0.0, 0.0, 0.0]})
        a = np.asarray(self.build([frame(TWO)], dict(ring, edges={"color": [1.0, 0.0, 0.0]}), grid=1)[0]).astype(int)
        red = (a[..., 0] > 128) & (a[..., 1] < 80) & (a[..., 3] > 128)
        self.assertGreater(int((red & (R < 36)).sum()), 50)          # the border of the two tones is lined
        self.assertEqual(int((red & (R > 42)).sum()), 0)             # and nothing is drawn outside the ink ring

    def test_the_line_is_not_counted_as_the_shape_running_off_its_cell(self):
        big = [frame(np.full((N, N), 0.8), (R < 58).astype(np.float64))]
        with_lines = self.build(big, {"alpha": "coverage", "tonemap": False, "edges": {}}, grid=1)[2]
        without = self.build(big, {"alpha": "coverage", "tonemap": False}, grid=1)[2]
        self.assertEqual(with_lines, without)

    def test_a_wrong_block_is_refused_in_words(self):
        fr = [frame(TWO)]
        for ed, word in ((True, "is a block"), ("on", "is a block"), (0, "is a block"), ({"width": 3}, "does not read width"),
                         ({"threshold": 0.35}, "threshold is 0.01 to 0.3"), ({"threshold": True}, "threshold is 0.01"),
                         ({"threshold": float("nan")}, "threshold is 0.01"), ({"grow": 1.5}, "grow is a whole number"),
                         ({"grow": True}, "grow is a whole number"), ({"color": [255, 0, 0]}, "each 0 to 1"),
                         ({"color": [True, False, False]}, "each 0 to 1"), ({"keep": 0}, "keep is true")):
            with self.assertRaisesRegex(ValueError, word, msg=str(ed)):
                self.build(fr, dict(PASS, edges=ed), grid=1)


class TheRegister(unittest.TestCase):
    def setUp(self):
        _, self.by = M.load()

    def specs(self, post):
        class One:
            def get(_, key):
                return {"engine": "fx", "recipe": "made", "post": post} if key == "tex" else None
        return One()

    def proved(self, mid, post):
        return M.proved(self.by[mid], [{"kind": "sprite", "texture": "tex", "life": 1}], self.specs(post), ".", "s") is not None

    def test_edge_detection_is_edges_not_a_ring_round_the_shape(self):
        self.assertEqual(self.by["edge_detection"]["state"], "has")
        self.assertTrue(self.proved("edge_detection", {"edges": {"threshold": 0.1}}))
        self.assertTrue(self.proved("edge_detection", {"edges": {}}))                # the step at its defaults
        self.assertFalse(self.proved("edge_detection", {"outline": {"width": 3}}))   # the silhouette alone
        self.assertFalse(self.proved("edge_detection", {"edges": False}))            # switched off
        self.assertFalse(self.proved("edge_detection", {}))

    def test_an_outline_is_any_of_the_ways_the_kit_draws_one(self):
        self.assertEqual(self.by["outlines"]["state"], "has")
        self.assertTrue(self.proved("outlines", {"outline": {"width": 3}}))
        self.assertTrue(self.proved("outlines", {"edges": {"threshold": 0.1}}))
        self.assertFalse(self.proved("outlines", {}))
        self.assertIsNotNone(M.proved(self.by["outlines"], [{"kind": "highlight", "life": 1}], self.specs({}), ".", "s"))


if __name__ == "__main__":
    unittest.main()
