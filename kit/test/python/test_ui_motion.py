"""kit ui read motion: a reference clip's beats (bursts of change), cuts and holds, in seconds"""
import importlib.util
import os
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_motion", os.path.join(HERE, "..", "..", "ui", "motion.py"))
motion = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(motion)


def clip():
    """60 frames at 30 fps: still, a hard CUT at frame 10 (a new picture), still, a block sliding frames 30..36, still"""
    rng = np.random.default_rng(1)
    a = (80 + rng.normal(0, 4, (90, 160))).clip(0, 255).astype(np.float32)
    b = (200 - a * 0.5).astype(np.float32)
    frames = []
    for i in range(60):
        f = (a if i < 10 else b).copy()
        x = 10 + 12 * min(max(i - 30, 0), 6)
        f[30:60, x:x + 30] = 20
        frames.append(f)
    return frames


class TestMotion(unittest.TestCase):
    def test_a_cut_and_a_move_are_two_beats_with_holds_around_them(self):
        evs, holds, share, thr = motion.events_from(clip(), 1 / 30)
        self.assertEqual(len(evs), 2, evs)
        cut, move = evs
        self.assertTrue(cut["cut"])
        self.assertAlmostEqual(cut["peak"], 9 / 30, places=2)   # the change INTO frame 10
        self.assertFalse(move["cut"])
        self.assertGreaterEqual(move["start"], 0.9)
        self.assertLessEqual(move["end"], 1.3)
        self.assertLess(move["box"][3] - move["box"][1], 0.5)    # the move touched a band, not the frame
        self.assertTrue(any(h["from"] >= 1.2 for h in holds))   # the still end is a hold

    def test_each_piece_gets_its_own_beats(self):
        frames = []
        for i in range(40):
            f = np.full((108, 192), 60, np.float32)
            if i >= 10:
                f[5:25, 5:60] = 220      # the top-left piece changes at frame 10
            if i >= 30:
                f[80:100, 130:185] = 220  # the bottom-right piece at frame 30
            frames.append(f)
        els = [{"label": "a", "box_1080": [0, 0, 640, 300]}, {"label": "b", "box_1080": [1280, 760, 1920, 1080]}]
        beats = motion.piece_beats(frames, 1 / 30, els, (192, 108))
        self.assertEqual(len(beats["a"]), 1)
        self.assertEqual(len(beats["b"]), 1)
        self.assertAlmostEqual(beats["a"][0], 9 / 30, places=2)
        self.assertAlmostEqual(beats["b"][0], 29 / 30, places=2)

    def test_the_beats_become_a_punch_track_a_reel_accepts(self):
        evs = [{"peak": 0.3}, {"peak": 0.67}]
        tr = motion.punch_track(evs, node="Hud.Logo")
        times = [k[0] for k in tr["keys"]]
        self.assertEqual(times, sorted(times))                  # keys in time order
        self.assertIn([0.33, 1.22], tr["keys"])                 # the punch lands just after the beat
        self.assertEqual(max(k[1] for k in tr["keys"]), 1.22)
        self.assertEqual(tr["node"], "Hud.Logo")
        close = motion.punch_track([{"peak": 0.3}, {"peak": 0.4}])  # closer than the settle
        t2 = [k[0] for k in close["keys"]]
        self.assertEqual(t2, sorted(t2))


if __name__ == "__main__":
    unittest.main()
