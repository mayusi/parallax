"""kit ui motion-ref: a synthetic clip of two panels sliding in (cubic ease-out, 0.2 s apart) is measured back: their
start, duration, ease and the stagger between them"""
import importlib.util
import os
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_motionref", os.path.join(HERE, "..", "..", "ui", "motionref.py"))
motionref = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(motionref)


class TestMotionRef(unittest.TestCase):
    def test_two_panels_sliding_in(self):
        import cv2
        fps, n = 30, 45
        with tempfile.TemporaryDirectory() as d:
            clip = os.path.join(d, "menu.mp4")
            vw = cv2.VideoWriter(clip, cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 240))
            for i in range(n):
                t = i / fps
                im = np.full((240, 320, 3), 30, np.uint8)
                for k, (t0, y) in enumerate(((0.2, 40), (0.4, 140))):
                    p = min(1.0, max(0.0, (t - t0) / 0.4))
                    e = 1 - (1 - p) ** 3
                    x = int(-120 + e * 160)
                    if x > -120:
                        im[y:y + 60, max(0, x):max(0, x + 120)] = (230, 230, 230)
                vw.write(im)
            vw.release()
            frames, times, f = motionref.read_frames(clip)
            boxes = [(0, 30, 320, 80), (0, 130, 320, 80)]
            r = [motionref.measure(frames, times, b) for b in boxes]
        self.assertTrue(all(r))
        self.assertAlmostEqual(r[0]["start"], 0.2, delta=0.07)
        self.assertAlmostEqual(r[1]["start"] - r[0]["start"], 0.2, delta=0.07)    # (the stagger)
        self.assertAlmostEqual(r[0]["duration"], 0.4, delta=0.1)
        self.assertIn(r[0]["ease"], ("cubic", "quart", "quad", "expo", "sine"))   # (an ease-OUT, not linear; clipped entries blur cubic toward sine)


if __name__ == "__main__":
    unittest.main()
