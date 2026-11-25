"""kit/vfx/shapetrace.py - the scene's drawn shapes as curves - on shapes whose outline is known: the made flame
(kit/selftest/vfx/trace/made.py) and small pictures drawn here. What is proven is what a later stage leans on: a held
drawing is ONE drawing, the tones are the cel's flat colours (never the anti-aliased rim between them), a cut-out stays
a hole, a drawn point stays sharp while a round end stays round, and what is not a drawing is refused."""

import json
import os
import sys
import unittest

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "selftest", "vfx", "trace"))
import made  # noqa: E402
import shapetrace as T  # noqa: E402


def drawn(polys, size=(320, 240), holes=()):
    """polygons -> a bool picture (anti-aliased by drawing 4x larger, like made.py)"""
    im = Image.new("L", (size[0] * 4, size[1] * 4), 0)
    pen = ImageDraw.Draw(im)
    for p in polys:
        pen.polygon([(x * 4, y * 4) for x, y in p], fill=255)
    for p in holes:
        pen.polygon([(x * 4, y * 4) for x, y in p], fill=0)
    return np.asarray(im.resize(size, Image.BOX)) >= 128


def circle(cx, cy, r, n=96):
    return [(cx + r * np.cos(a), cy + r * np.sin(a)) for a in np.linspace(0, 2 * np.pi, n, endpoint=False)]


class TestCurves(unittest.TestCase):
    def test_a_circle_has_no_sharp_point_and_few_points(self):
        m = drawn([circle(160, 120, 70)])
        (shape,) = T.shapes_of(m)
        pts, flags = shape["outer"]
        self.assertEqual(int(flags.sum()), 0)
        self.assertLess(len(pts), 90)                         # 440 px of outline as a curve, not a pixel chain
        r = np.hypot(pts[:, 0] - 160, pts[:, 1] - 120)
        self.assertLess(float(np.abs(r - 70).max()), 1.2)

    def test_a_square_keeps_its_four_corners(self):
        m = drawn([[(80, 60), (240, 60), (240, 180), (80, 180)]])
        (shape,) = T.shapes_of(m)
        pts, flags = shape["outer"]
        self.assertEqual(int(flags.sum()), 4)
        for corner in ((80, 60), (240, 60), (240, 180), (80, 180)):
            self.assertLess(float(np.hypot(*(pts[flags] - np.array(corner)).T).min()), 2.0)

    def test_a_cut_out_stays_a_hole_and_a_pinhole_does_not(self):
        m = drawn([circle(160, 120, 80)], holes=[circle(150, 110, 22)])
        m[150, 200] = False                                   # one dead pixel: the clip's noise, not a cut-out
        shapes = T.shapes_of(T.clean(m))
        self.assertEqual(len(shapes), 1)
        self.assertEqual(len(shapes[0]["holes"]), 1)
        again = T.fill(shapes, (320, 240)) > 0.5
        self.assertFalse(bool(again[110, 150]))               # the hole is a hole when drawn again
        self.assertTrue(bool(again[150, 200]))

    def test_drawn_again_it_covers_what_was_traced(self):
        m = drawn([made.outline(3)[0]], size=(made.W, made.H))
        again = T.fill(T.shapes_of(m), (made.W, made.H)) > 0.5
        self.assertGreater((again & m).sum() / float((again | m).sum()), 0.975)

    def test_drawn_larger_the_tip_is_still_a_point(self):
        # a sheet's cell is another size than the frame: the curve is drawn at that size, never a picture scaled up
        body, _, _, tip = made.outline(2)
        m = drawn([body], size=(made.W, made.H))
        big = T.fill(T.shapes_of(m), (made.W * 3, made.H * 3), scale=3.0) > 0.5
        ys, xs = np.nonzero(big)
        top = ys.min()
        self.assertLess(abs(top / 3.0 - tip[1]), 2.0)
        self.assertLessEqual(int(big[top + 6].sum()), 24)     # 2 px under the tip (of the small picture) it is still narrow
        self.assertLessEqual(int(big[top].sum()), 6)          # ... and the tip itself is a point, not a 3 px step


    def test_a_long_straight_step_beside_short_ones_does_not_swing_the_curve_out(self):
        # a real trace (2026-11-13): an edge cut straight by --box, thinned to two far points, beside a dense curve -
        # the curve through them bulged 19 px past its own points and drew a hairline to the cell's edge
        pts = np.array([(0, 0), (200, 0), (203, 3), (204, 8), (203, 13), (200, 16), (0, 16), (-3, 13), (-4, 8), (-3, 3)], dtype=float)
        poly = T.spline(pts, np.zeros(len(pts), dtype=bool))
        self.assertLess(float(max(pts[:, 0].min() - poly[:, 0].min(), poly[:, 0].max() - pts[:, 0].max(),
                                  pts[:, 1].min() - poly[:, 1].min(), poly[:, 1].max() - pts[:, 1].max())), 1.5)
        dense, corners = T.outline(pts, [True] + [False] * 9)
        self.assertEqual(corners, [0])
        self.assertTrue(np.allclose(dense[0], pts[0]))


    def test_the_curve_lies_on_the_edge_so_a_thin_shape_is_still_itself(self):
        # an outline follows the CENTRES of the boundary pixels: the curves came out a pixel thin - a square lost a row
        # and a column, a line 3 px wide covered two thirds of itself (a review, 2026-11-13)
        def fit(m):
            again = T.fill(T.shapes_of(m), (m.shape[1], m.shape[0])) > 0.5
            return (again & m).sum() / float((again | m).sum())

        square = np.zeros((240, 320), dtype=bool)
        square[60:180, 80:240] = True
        self.assertGreater(fit(square), 0.995)
        for wide in (3, 5):
            line = np.zeros((240, 320), dtype=bool)
            line[100:100 + wide, 40:280] = True
            self.assertGreater(fit(line), 0.98, f"a line {wide} px wide")
        yy, xx = np.mgrid[0:240, 0:320]
        crescent = (np.hypot(xx - 160, yy - 120) < 80) & ~(np.hypot(xx - 168, yy - 120) < 80)      # 8 px at its widest
        self.assertGreater(fit(crescent), 0.95)
        pts, _ = T.shapes_of(square)[0]["outer"]
        self.assertAlmostEqual(float(pts[:, 0].min()), 80.0, delta=0.3)       # pixel 80 begins at 80 ...
        self.assertAlmostEqual(float(pts[:, 0].max()), 240.0, delta=0.3)      # ... and pixel 239 ends at 240


class TestDrawings(unittest.TestCase):
    def test_a_held_drawing_is_one_drawing_despite_the_clips_grain(self):
        frames = made.scene()
        masks = np.stack([T.clean(x) for x in T.cut_out(frames, made.HUE)])
        self.assertEqual(T.drawings(masks), [(2 + 2 * k, 3 + 2 * k) for k in range(made.DRAWINGS)])

    def test_the_tones_are_the_cels_colours_not_the_rim_between_them(self):
        trace = T.trace_frames(made.scene(), made.FPS, made.HUE, tones=4)      # four asked for: the flame has two
        self.assertEqual(len(trace["tones"]), 2)
        self.assertLessEqual(float(np.abs(trace["tones"][0] - np.array(made.BODY)).max()), 10)
        self.assertLessEqual(float(np.abs(trace["tones"][1] - np.array(made.CORE)).max()), 10)

    def test_thin_stripes_of_two_tones_are_two_tones_not_the_mixes_between_them(self):
        # where two tones meet, the clip's pixels are a MIX of them; fourteen stripes 5 px wide hold so many such pixels
        # that the mixes came back as tones of their own - the tones are read from flat patches only (FLAT)
        ss = 4
        body = Image.new("L", (made.W * ss, made.H * ss), 0)
        ImageDraw.Draw(body).ellipse([200 * ss, 60 * ss, 440 * ss, 300 * ss], fill=255)
        core = Image.new("L", (made.W * ss, made.H * ss), 0)
        pen = ImageDraw.Draw(core)
        for k in range(14):
            x = 215 + k * 15
            pen.polygon([(x * ss, 80 * ss), ((x + 5) * ss, 80 * ss), ((x + 25) * ss, 280 * ss), ((x + 20) * ss, 280 * ss)], fill=255)
        a = np.asarray(body.resize((made.W, made.H), Image.BOX), dtype=np.float32)[..., None] / 255.0
        c = np.asarray(core.resize((made.W, made.H), Image.BOX), dtype=np.float32)[..., None] / 255.0 * a
        pic = made.night() * (1 - a) + np.array(made.BODY, dtype=np.float32) * a
        pic = pic * (1 - c) + np.array(made.CORE, dtype=np.float32) * c
        frames = np.stack([np.clip(pic + np.random.default_rng(i).integers(-3, 4, size=pic.shape), 0, 255).astype(np.uint8)
                           for i in range(2)])
        for asked in (3, 4):
            tones = T.trace_frames(frames, made.FPS, made.HUE, tones=asked)["tones"]
            self.assertEqual(len(tones), 2, f"{asked} tones asked for")
            self.assertLessEqual(float(np.abs(tones[0] - np.array(made.BODY)).max()), 10)
            self.assertLessEqual(float(np.abs(tones[1] - np.array(made.CORE)).max()), 10)

    def test_the_made_flame_comes_back_whole(self):
        trace = T.trace_frames(made.scene(), made.FPS, made.HUE)
        self.assertEqual(T.report(trace, "made")[0], "pass")
        self.assertEqual(T.rhythm(trace), 2)
        for k, d in enumerate(trace["drawings"]):
            self.assertEqual((d["hold"], d["pieces"], d["holes"], d["tips"]), (2, 1, 1, 1), f"drawing {k}")
            self.assertGreater(d["fit"], 0.97)

    def test_each_drawing_says_how_much_is_cut_out_and_how_fast_its_middle_moves(self):
        # the V3 doc, stage C.1: per drawing the cut-out ratio (holes over what the outline closes) and the middle's
        # speed from one drawing to the next (frame widths a second)
        def clip(masks):
            frames = np.stack([made.night().astype(np.uint8) for _ in masks])
            for f, m in zip(frames, masks):
                f[m] = made.BODY
            return frames
        h, w = made.night().shape[:2]
        solid = drawn([circle(160, 120, 60)], size=(w, h))
        ring = drawn([circle(160, 120, 60)], size=(w, h), holes=[circle(160, 120, 30)])
        two = [solid, solid, ring, ring]                                     # two drawings on twos
        trace = T.trace_frames(clip(two), made.FPS, made.HUE)
        a, b = trace["drawings"]
        self.assertLess(a["cutout"], 0.01)
        self.assertAlmostEqual(b["cutout"], 0.25, delta=0.03)                # a hole of half the radius: a quarter
        self.assertIsNone(a["speed"])
        self.assertAlmostEqual(b["speed"], 0.0, delta=0.01)                   # the same middle
        moving = [drawn([circle(100 + 20 * (i // 2), 120, 30)], size=(w, h)) for i in range(8)]
        t2 = T.trace_frames(clip(moving), made.FPS, made.HUE)
        speeds = [d["speed"] for d in t2["drawings"][1:]]
        want = 20.0 / w / (2.0 / made.FPS)                               # 20 px every two frames
        self.assertEqual(len(speeds), 3)
        for v in speeds:
            self.assertAlmostEqual(v, want, delta=want * 0.05)
        # stored and read back: the middle normalised to the frame, the numbers kept
        back = T.from_json(json.loads(json.dumps(T.to_json(t2))))
        self.assertAlmostEqual(back["drawings"][1]["centre"][0], t2["drawings"][1]["centre"][0], delta=0.01)
        self.assertEqual(back["drawings"][1]["speed"], t2["drawings"][1]["speed"])
        self.assertEqual(T.to_json(trace)["drawings"][1]["cutout"], b["cutout"])

    def test_a_shape_that_slides_is_not_one_drawing_held_for_ever(self):
        # a pixel a frame never changes much from the frame before: forty such frames came back as ONE drawing held forty
        frames = np.stack([made.night().astype(np.uint8) for _ in range(40)])
        for i in range(40):
            frames[i, 100:170, 100 + i:170 + i] = made.BODY
        trace = T.trace_frames(frames, made.FPS, made.HUE)
        self.assertGreater(len(trace["drawings"]), 10)
        self.assertLessEqual(max(d["hold"] for d in trace["drawings"]), 3)
        self.assertTrue(all(d["drift"] for d in trace["drawings"][:-1]))      # ended by drift, not by a new drawing ...
        self.assertIsNone(T.rhythm(trace))                                    # ... so no rhythm is read from them
        self.assertIn("SLOW DRIFT", T.report(trace, "slide")[1])
        held = T.trace_frames(made.scene(), made.FPS, made.HUE)               # the made flame's holds are real holds
        self.assertFalse(any(d["drift"] for d in held["drawings"]))

    def test_sparks_that_are_nothing_once_their_frames_are_taken_together_do_not_crash(self):
        frames = np.stack([made.night().astype(np.uint8) for _ in range(5)])
        for i in range(5):
            for k in range(6):
                frames[i, 100:106, 60 + k * 90 + i % 2:66 + k * 90 + i % 2] = made.BODY      # 36 px each, a pixel to and fro
        status, said = T.report(T.trace_frames(frames, made.FPS, made.HUE), "sparks")
        self.assertIn(status, ("pass", "fail"))

    def test_the_tips_are_the_silhouettes_not_a_cut_outs(self):
        yy, xx = np.mgrid[0:made.H, 0:made.W]
        m = np.hypot(xx - 320, yy - 180) < 120
        m[150:210, 290:350] = False                                           # a square cut-out in a disc
        frames = np.stack([made.night().astype(np.uint8)] * 2)
        frames[:, m] = made.BODY
        d = T.trace_frames(frames, made.FPS, made.HUE)["drawings"][0]
        self.assertEqual((d["holes"], d["tips"]), (1, 0))

    def test_a_box_leaves_the_rest_of_the_frame_out(self):
        frames = made.scene()
        frames[:, 20:60, 20:60] = made.BODY                   # a lamp in the fire's hue band, away from the flame
        both = T.trace_frames(frames, made.FPS, made.HUE)
        self.assertEqual(max(d["pieces"] for d in both["drawings"]), 2)       # the lamp is traced with the flame
        only = T.trace_frames(frames, made.FPS, made.HUE, box=(0.3, 0.1, 0.8, 0.95))
        self.assertEqual([d["pieces"] for d in only["drawings"]], [1] * made.DRAWINGS)

    def test_a_drawing_the_box_cuts_is_said_to_be_cut(self):
        whole = T.trace_frames(made.scene(), made.FPS, made.HUE)
        self.assertEqual(max(d["cut"] for d in whole["drawings"]), 0.0)
        self.assertNotIn("CUTS", T.report(whole, "made")[1])
        halved = T.trace_frames(made.scene(), made.FPS, made.HUE, box=(0.0, 0.0, 0.52, 1.0))     # the box ends inside the flame
        self.assertGreater(min(d["cut"] for d in halved["drawings"]), 0.1)
        self.assertIn("CUTS 6 of them", T.report(halved, "made")[1])

    def test_with_no_hue_it_reads_what_is_brighter_than_the_quiet_picture(self):
        trace = T.trace_frames(made.scene(), made.FPS, None)
        self.assertEqual(len(trace["drawings"]), made.DRAWINGS)
        self.assertEqual(trace["drawings"][0]["holes"], 1)


class TestRefusals(unittest.TestCase):
    def test_a_wall_in_the_hue_band_is_not_a_drawing(self):
        trace = T.trace_frames(made.flood(), made.FPS, made.HUE)
        status, said = T.report(trace, "flood")
        self.assertEqual(status, "fail")
        self.assertIn("not a drawing", said)
        self.assertEqual(trace["drawings"], [])

    def test_a_dark_clip_says_nothing_lit_up(self):
        frames = np.stack([made.picture(None, False, i) for i in range(6)])
        status, said = T.report(T.trace_frames(frames, made.FPS, made.HUE), "dark")
        self.assertEqual(status, "fail")
        self.assertIn("nothing lit up", said)

    def test_with_no_hue_an_effect_lit_in_every_frame_is_said_not_to_be_seen(self):
        frames = np.stack([made.picture(2, False, i) for i in range(12)])
        status, said = T.report(T.trace_frames(frames, made.FPS, None), "always")
        self.assertEqual(status, "fail")
        self.assertIn("lit in EVERY frame", said)

    def test_the_command_says_what_is_wrong_and_never_throws(self):
        import contextlib
        import io
        import tempfile
        from PIL import Image as Im
        folder = tempfile.mkdtemp(prefix="kit_trace_")
        try:
            Im.fromarray(made.picture(0)).save(os.path.join(folder, "a.png"))
            Im.fromarray(made.picture(0)[:100]).save(os.path.join(folder, "b.png"))      # another size
            for argv in (["--frames", folder, "--out", folder], ["--frames", folder, "--out", folder, "--fps", "0"],
                         ["--frames", folder, "--out", folder, "--fps", "abc"], ["--frames", folder, "--out", folder, "--box"],
                         ["--frames", os.path.join(folder, "none")], ["no_such_set", "--beat", "x"], []):
                said = io.StringIO()
                with contextlib.redirect_stdout(said):
                    code = T.main(argv)
                got = json.loads(said.getvalue().strip().splitlines()[-1])
                self.assertEqual((code, got["status"]), (1, "fail"), argv)
        finally:
            import shutil
            shutil.rmtree(folder, ignore_errors=True)

    def test_speckle_is_refused(self):
        rng = np.random.default_rng(3)
        frames = np.stack([made.picture(None, False, i) for i in range(4)])
        for _ in range(90):                                   # ninety small sparks: a colour band that catches noise
            x, y = int(rng.integers(10, made.W - 20)), int(rng.integers(10, made.H - 20))
            frames[:, y:y + 12, x:x + 12] = made.BODY
        trace = T.trace_frames(frames, made.FPS, made.HUE)
        self.assertEqual(trace["drawings"], [])
        self.assertIn("speckle", trace["refused"][0]["why"])


class TestStore(unittest.TestCase):
    def test_the_stored_trace_draws_the_same_picture(self):
        trace = T.trace_frames(made.scene(), made.FPS, made.HUE)
        back = T.from_json(json.loads(json.dumps(T.to_json(trace))))
        a = T.paint(trace["drawings"][4], trace["tones"], (made.W, made.H))
        b = T.paint(back["drawings"][4], back["tones"], (made.W, made.H))
        self.assertLess(float(np.abs(a - b).mean()), 0.002)
        self.assertEqual(back["on"], 2)

    def test_the_stored_trace_is_normalised_to_the_frame(self):
        data = T.to_json(T.trace_frames(made.scene(), made.FPS, made.HUE))
        for d in data["drawings"]:
            for L in d["layers"]:
                for s in L["shapes"]:
                    for x, y, c in s["outer"]:
                        self.assertTrue(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and c in (0, 1))


if __name__ == "__main__":
    unittest.main()
