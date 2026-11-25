"""kit/vfx/track.py - following the camera inside a shot - on a MADE shot whose camera move is known
(kit/selftest/vfx/track/madepan.py). What is proven is what the tracker is trusted for: it gives each frame's place in
the first frame's picture to a fraction of a pixel, calls a standing camera standing and never invents a move from
grain, says so when it cannot follow, and the trace refuses a moving camera without it and reads the drawings on twos
with it."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "selftest", "vfx", "track"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "selftest", "vfx", "trace"))
import made  # noqa: E402
import madepan as P  # noqa: E402
import shapetrace as S  # noqa: E402
import track as T  # noqa: E402

CORNERS = np.array([[0, 0, 1], [640, 0, 1], [0, 360, 1], [640, 360, 1], [320, 180, 1]], dtype=np.float64).T


def worst(tr, truth):
    """the farthest any corner of any frame lands from where it truly is in the first frame, in px"""
    return max(float(np.linalg.norm((np.asarray(a) @ CORNERS - b @ CORNERS)[:2], axis=0).max()) for a, b in zip(tr["to_first"], truth))


class TestTrack(unittest.TestCase):
    def test_a_pan_and_a_zoom_are_followed_to_a_fraction_of_a_pixel(self):
        # (with the zoom, a pan of 3.354 world px a frame measures 3.354 x the zoom so far in the frames' own px: about 3.45)
        for kw, pan in (({}, 3.354 * 1.03), ({"zoom": 0.0}, 3.354), ({"pan": (-2.0, 0.0), "zoom": 0.0}, 2.0), ({"pan": (0.5, 0.0), "zoom": 0.0}, 0.5)):
            frames, truth = P.scene(**kw)
            tr = T.track(frames, made.HUE)
            self.assertTrue(tr["known"] and tr["moves"], kw)
            self.assertEqual(tr["followed"], 1.0, kw)
            self.assertLess(worst(tr, truth), 0.3, kw)
            self.assertAlmostEqual(tr["pan"], pan, delta=0.06, msg=str(kw))
        frames, truth = P.scene(pan=(0, 0), zoom=0.004)
        tr = T.track(frames, made.HUE)
        self.assertTrue(tr["moves"])
        self.assertAlmostEqual(tr["zoom"], 1 / 1.06, delta=0.003)       # a later frame is 1.06 times the first: zoomed in
        self.assertLess(tr["pan"], 0.1)
        self.assertLess(worst(tr, truth), 0.4)

    def test_the_words_say_which_way(self):
        frames, _ = P.scene(pan=(3.0, -1.5), zoom=0.0)
        said = T.says(T.track(frames, made.HUE))
        self.assertIn("right and up", said)
        frames, _ = P.scene(pan=(-3.0, 1.5), zoom=0.0)
        self.assertIn("left and down", T.says(T.track(frames, made.HUE)))
        frames, _ = P.scene(pan=(0, 0), zoom=0.004)
        said = T.says(T.track(frames, made.HUE))
        self.assertIn("zooms in", said)
        self.assertNotIn("pans", said)

    def test_a_standing_camera_stands_and_grain_is_not_a_tremble(self):
        frames, truth = P.scene(pan=(0, 0), zoom=0.0)
        tr = T.track(frames, made.HUE)
        self.assertTrue(tr["known"])
        self.assertFalse(tr["moves"])
        self.assertLess(tr["drift"], 0.3)
        self.assertIn("stands still", T.says(tr))
        # heavy grain on every frame, a camera that does not move: still standing
        rng = np.random.default_rng(5)
        noisy = np.clip(frames.astype(np.int16) + rng.integers(-14, 15, size=frames.shape), 0, 255).astype(np.uint8)
        tr = T.track(noisy, made.HUE)
        self.assertTrue(tr["known"])
        self.assertFalse(tr["moves"], T.says(tr))

    def test_what_cannot_be_followed_is_said_not_guessed(self):
        for frames in (made.scene(), made.flood()):                     # a flat night, a flat wall: nothing to hold on to
            tr = T.track(frames, made.HUE)
            self.assertFalse(tr["known"])
            self.assertFalse(tr["moves"])
            self.assertIn("could not be followed", T.says(tr))
            self.assertTrue(all(np.allclose(t, np.eye(3)) for t in tr["to_first"]))   # no move is invented
        # a cut inside the stretch: the pair across it is not followed, the rest is
        a, _ = P.scene(pan=(2.0, 0.0), zoom=0.0)
        cut = np.concatenate([a[:8], a[8:, ::-1, ::-1]])                 # the second half upside down: another picture
        tr = T.track(cut, made.HUE)
        self.assertFalse(tr["steps"][7]["followed"])
        self.assertTrue(tr["steps"][3]["followed"] and tr["steps"][11]["followed"])

    def test_the_effect_does_not_pull_the_camera(self):
        """the flame appears, changes and goes: with or without its colour named, the camera read is the background's"""
        frames, truth = P.scene()
        self.assertLess(worst(T.track(frames, None), truth), 0.4)       # (no hue: the flame's points are outvoted)
        still, truth0 = P.scene(pan=(0, 0), zoom=0.0)
        self.assertFalse(T.track(still, None)["moves"])

    def test_stabilised_the_background_stands_still(self):
        frames, _ = P.scene(flame=False)
        tr = T.track(frames, None)
        steady, win = T.stabilise(frames, tr)
        x0, y0, x1, y1 = win
        self.assertEqual(steady.shape[1:3], (y1 - y0, x1 - x0))
        self.assertGreater((x1 - x0) * (y1 - y0), 0.7 * 640 * 360)
        before = float(np.abs(frames[-1].astype(np.float64)[y0:y1, x0:x1] - frames[0].astype(np.float64)[y0:y1, x0:x1]).mean())
        after = float(np.abs(steady[-1].astype(np.float64) - steady[0].astype(np.float64)).mean())
        self.assertLess(after, 0.35 * before)                            # what is left is grain and resampling
        self.assertLess(after, 4.0)
        self.assertTrue((steady[-1].reshape(-1, 3).max(axis=1) > 0).mean() > 0.999)   # the window holds no empty border
        full, _ = T.stabilise(frames, tr, crop=False)
        self.assertEqual(full.shape, frames.shape)

    def test_frames_that_share_no_window(self):
        frames, _ = P.scene(pan=(60.0, 0.0), zoom=0.0)
        tr = {"size": [640, 360], "to_first": [np.eye(3).tolist(), [[1, 0, 2000.0], [0, 1, 0], [0, 0, 1]]]}
        self.assertIsNone(T.window(tr))
        self.assertEqual(T.stabilise(frames[:2], tr), (None, None))


def shifted(frames, offsets):
    import cv2
    return np.stack([cv2.warpAffine(f, np.float32([[1, 0, dx], [0, 1, dy]]), (640, 360), borderMode=cv2.BORDER_REFLECT)
                     for f, (dx, dy) in zip(frames, offsets)])


class TestComesBack(unittest.TestCase):
    """(a review, 2026-11-14) a camera that moves and ends where it began was read at its last frame only: "standing" """

    def setUp(self):
        self.base, _ = P.scene(pan=(0, 0), zoom=0.0)

    def test_an_impact_shake_that_ends_at_rest_moves(self):
        rng = np.random.default_rng(1)
        shake = [(0, 0)] * 2 + [tuple(int(v) for v in rng.integers(-6, 7, 2)) for _ in range(11)] + [(0, 0)] * 3
        frames = shifted(self.base, shake)
        tr = T.track(frames, made.HUE)
        self.assertTrue(tr["known"] and tr["moves"])
        self.assertLess(tr["drift"], 1.0)                                # the last frame is back on the first
        self.assertGreater(tr["far"], 4.0)
        self.assertIn("comes back", T.says(tr))
        raw = S.trace_frames(frames, 24.0, made.HUE, 3, None, None)
        laid, _ = T.stabilise(frames, tr)
        fixed = S.trace_frames(laid, 24.0, made.HUE, 3, None, None)
        self.assertGreater(len(raw["drawings"]), 8)                      # shaken, nearly every frame is a "new drawing"
        self.assertEqual([d["hold"] for d in fixed["drawings"]], [2] * 6)

    def test_a_pan_there_and_back_and_a_roll_move(self):
        import cv2
        back = shifted(self.base, [(4 * min(i, 15 - i), 0) for i in range(16)])
        tr = T.track(back, made.HUE)
        self.assertTrue(tr["moves"])
        self.assertLess(tr["drift"], 1.0)
        rolled = np.stack([cv2.warpAffine(f, cv2.getRotationMatrix2D((320, 180), 0.2 * min(i, 15 - i), 1.0), (640, 360), borderMode=cv2.BORDER_REFLECT)
                           for i, f in enumerate(self.base)])
        tr = T.track(rolled, made.HUE)
        self.assertTrue(tr["moves"])
        self.assertGreater(tr["tilt"], 1.0)
        self.assertIn("rolls", T.says(tr))

    def test_the_limits_are_shares_of_the_frame(self):
        import cv2
        for pan, want in ((0.6, True), (0.0, False)):
            big, _ = P.scene(pan=(pan, 0), zoom=0.0)
            small = np.stack([cv2.resize(f, (320, 180), interpolation=cv2.INTER_AREA) for f in big])
            self.assertEqual((T.track(big, made.HUE)["moves"], T.track(small, made.HUE)["moves"]), (want, want), pan)

    def test_one_thing_that_moves_in_a_corner_is_not_the_camera(self):
        # the only detail is a patch in one quarter of a flat frame, sliding: its points agree, and are not spread
        frames = np.full((12, 360, 640, 3), 40, dtype=np.uint8)
        rng = np.random.default_rng(4)
        patch = rng.integers(0, 255, size=(120, 160, 3)).astype(np.uint8)
        patch = np.repeat(np.repeat(patch[::8, ::8], 8, axis=0), 8, axis=1)
        for i in range(12):
            frames[i, 20:140, 20 + 4 * i:180 + 4 * i] = patch
        tr = T.track(frames, None)
        self.assertFalse(tr["known"])
        self.assertFalse(tr["moves"])


class TestTimingFollows(unittest.TestCase):
    """the dense timing read: under a pan every frame "changes"; with the camera taken out the holds are back"""

    def changes(self, frames):
        import dense
        c = dense.curves(frames, made.HUE)
        lit = np.asarray(c["cover"]) > 0.01   # (the frames the flame is in: the world's small lights cover a tenth of a percent)
        return [bool(x > dense.HELD) for x, on in zip(c["change"], lit) if on]

    def test_a_pan_hides_the_holds_and_the_followed_read_shows_them(self):
        import denseclip as DC
        frames, _ = P.scene(zoom=0.0)
        raw = self.changes(frames)
        self.assertGreater(sum(raw), len(raw) - 2)                       # nearly every lit frame "changes"
        laid, said = DC.steady(frames, made.HUE)
        self.assertIn("read from the stabilised frames", said)
        self.assertEqual(laid.shape, frames.shape)                        # whole frames: "cover" stays a share of the frame
        self.assertIn("pans", said)
        got = self.changes(laid)
        self.assertEqual(got, [True, False] * 6)                          # six drawings on twos: a change, then a hold

    def test_a_standing_or_unfollowable_camera_changes_nothing(self):
        import denseclip as DC
        still, _ = P.scene(pan=(0, 0), zoom=0.0)
        laid, said = DC.steady(still, made.HUE)
        self.assertTrue(laid is still and said is None)
        flat = made.scene()
        laid, said = DC.steady(flat, made.HUE)
        self.assertTrue(laid is flat and said is None)
        short = still[:2]
        self.assertTrue(DC.steady(short, made.HUE)[0] is short)


class TestTraceFollows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kit_track_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def save(self, frames, name):
        folder = os.path.join(self.tmp, name)
        os.makedirs(folder)
        for i, f in enumerate(frames):
            Image.fromarray(f).save(os.path.join(folder, f"{i:03d}.png"))
        return folder

    def run_tool(self, mod, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = mod.main(list(argv))
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1, lines)
        return code, json.loads(lines[0])

    def test_a_moving_camera_is_refused_without_track_and_read_on_twos_with_it(self):
        frames, _ = P.scene()
        folder = self.save(frames, "pan")
        hue = f"{made.HUE[0]},{made.HUE[1]}"
        out = os.path.join(self.tmp, "out")
        code, v = self.run_tool(S, "--frames", folder, "--fps", "24", "--hue", hue, "--out", out)
        self.assertEqual(code, 1)
        self.assertIn("the camera pans", v["summary"])
        self.assertIn("every frame would read as a new drawing", v["summary"])
        self.assertIn("--track", v["next_action"])
        self.assertFalse(os.path.exists(os.path.join(out, "trace.json")))
        code, v = self.run_tool(S, "--frames", folder, "--fps", "24", "--hue", hue, "--out", out, "--track")
        self.assertEqual(code, 0, v)
        self.assertEqual((v["drawings"], v["on"]), (6, 2))               # the made flame: six drawings, on twos
        self.assertIn("the camera followed", v["summary"])
        data = json.load(open(os.path.join(out, "trace.json"), encoding="utf-8"))
        self.assertEqual(data["tracked"]["of"], [640, 360])
        x0, y0, x1, y1 = data["tracked"]["window"]
        self.assertEqual(data["size"], [x1 - x0, y1 - y0])               # its curves live in the window
        # ... and the drawings are the ones a standing camera gives: the same areas, drawing by drawing
        still = self.save(P.scene(pan=(0, 0), zoom=0.0)[0], "still")
        out2 = os.path.join(self.tmp, "out2")
        code, w = self.run_tool(S, "--frames", still, "--fps", "24", "--hue", hue, "--out", out2)
        self.assertEqual((code, w["drawings"], w["on"]), (0, 6, 2), w)
        ref = json.load(open(os.path.join(out2, "trace.json"), encoding="utf-8"))
        for a, b in zip(data["drawings"], ref["drawings"]):
            area_a = a["cover"] * (x1 - x0) * (y1 - y0)
            area_b = b["cover"] * 640 * 360
            self.assertAlmostEqual(area_a / area_b, 1.0, delta=0.04)

    def test_track_on_a_camera_that_stands_or_cannot_be_followed(self):
        hue = f"{made.HUE[0]},{made.HUE[1]}"
        still = self.save(P.scene(pan=(0, 0), zoom=0.0)[0], "still")
        code, v = self.run_tool(S, "--frames", still, "--fps", "24", "--hue", hue, "--out", os.path.join(self.tmp, "o1"), "--track")
        self.assertEqual((code, v["drawings"]), (0, 6), v)               # nothing to stabilise: traced as it is
        self.assertNotIn("the camera followed", v["summary"])
        flat = self.save(made.scene(), "flat")
        code, v = self.run_tool(S, "--frames", flat, "--fps", "24", "--hue", hue, "--out", os.path.join(self.tmp, "o2"), "--track")
        self.assertEqual(code, 1)
        self.assertIn("could not be followed", v["summary"])
        code, v = self.run_tool(S, "--frames", flat, "--fps", "24", "--hue", hue, "--out", os.path.join(self.tmp, "o3"))
        self.assertEqual((code, v["drawings"], v["on"]), (0, 6, 2), v)   # without --track it is traced as before

    def test_no_track_is_the_way_out_and_a_box_follows_the_window(self):
        hue = f"{made.HUE[0]},{made.HUE[1]}"
        pan = self.save(P.scene()[0], "pan2")
        out = os.path.join(self.tmp, "nt")
        code, v = self.run_tool(S, "--frames", pan, "--fps", "24", "--hue", hue, "--out", out, "--no-track")
        self.assertEqual(code, 0, v)                                     # traced as the clip has it, and it says so
        self.assertIn("NOT read (--no-track)", v["summary"])
        self.assertEqual(json.load(open(os.path.join(out, "trace.json"), encoding="utf-8"))["tracked"], {"skipped": "--no-track"})
        # a box round the flame, given in shares of the FRAME, still holds the flame once the frames are cut to the window
        code, v = self.run_tool(S, "--frames", pan, "--fps", "24", "--hue", hue, "--out", os.path.join(self.tmp, "bx"), "--track", "--box", "0.25,0.1,0.85,0.95")
        self.assertEqual((code, v["drawings"], v["on"]), (0, 6, 2), v)
        code, v = self.run_tool(S, "--frames", pan, "--fps", "24", "--hue", hue, "--out", os.path.join(self.tmp, "bo"), "--track", "--box", "0,0,0.05,0.05")
        self.assertEqual(code, 1)
        self.assertIn("outside the window", v["summary"])

    def test_the_command(self):
        folder = self.save(P.scene()[0], "pan")
        out = os.path.join(self.tmp, "t")
        code, v = self.run_tool(T, "--frames", folder, "--fps", "24", "--hue", f"{made.HUE[0]},{made.HUE[1]}", "--out", out)
        self.assertEqual(code, 0, v)
        self.assertTrue(v["moves"] and v["known"])
        self.assertTrue(os.path.isfile(os.path.join(out, "track.json")) and os.path.isfile(os.path.join(out, "track_track.png")))
        self.assertEqual(len(json.load(open(os.path.join(out, "track.json"), encoding="utf-8"))["to_first"]), 16)
        flat = self.save(made.scene(), "flat")
        code, v = self.run_tool(T, "--frames", flat, "--fps", "24", "--out", os.path.join(self.tmp, "t2"))
        self.assertEqual((code, v["known"]), (1, False))
        for argv in ([], ["--frames", os.path.join(self.tmp, "none")], ["--frames"], ["no_such_set"], ["--frames", folder, "--hue", "5"]):
            code, v = self.run_tool(T, *argv)
            self.assertEqual((code, v["status"]), (1, "fail"), argv)


if __name__ == "__main__":
    unittest.main()
