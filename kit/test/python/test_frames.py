"""kit refs frames (kit/refs/frames.py) — a video's frames cut down to DIFFERENT SHARP views: a blurred frame and a
held (repeated) frame are dropped, distinct sharp views kept in time order; end to end through ffmpeg when it is
installed."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "refs"))
import frames as F  # noqa: E402


def view(k, size=96):
    """a distinct sharp 'view' (one object turned: the same fine detail, a different layout): a fine checker with a
    dark block at its own place"""
    yy, xx = np.mgrid[0:size, 0:size]
    im = (((xx // 4) + (yy // 4)) % 2 * 120 + 100).astype(np.uint8)
    x0 = (11 * k) % (size - 32)
    im[16:80, x0:x0 + 32] //= 4
    return im


class Select(unittest.TestCase):
    def test_blurred_and_repeated_frames_are_dropped(self):
        import cv2  # noqa: PLC0415

        a, b, c = view(0), view(2), view(4)
        blurred = cv2.GaussianBlur(b, (0, 0), 4)
        held = a.copy()
        held[0, 0] = 0                                     # (one pixel different: the camera held still)
        kept, _sh = F.select([a, blurred, b, held, c])
        self.assertEqual(len(kept), 3)
        self.assertNotIn(1, kept)                          # (the blurred frame)
        self.assertEqual(len({0, 3} & set(kept)), 1)       # (one of the two copies of the same view)
        self.assertTrue({2, 4} <= set(kept))

    def test_max_keeps_the_sharpest(self):
        kept, sh = F.select([view(k) for k in range(6)], max_keep=2)
        self.assertEqual(len(kept), 2)
        self.assertTrue(all(sh[i] >= sorted(sh)[-3] for i in kept))


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class EndToEnd(unittest.TestCase):
    def test_a_clip_becomes_its_distinct_views(self):
        from PIL import Image  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as t:
            seq = [view(0)] * 4 + [view(2)] * 4 + [view(4)] * 4      # (3 views, each held 4 frames)
            for i, im in enumerate(seq):
                Image.fromarray(im).save(os.path.join(t, f"s_{i:03d}.png"))
            clip = os.path.join(t, "clip.mp4")
            subprocess.run([shutil.which("ffmpeg"), "-loglevel", "error", "-framerate", "4", "-i",
                            os.path.join(t, "s_%03d.png"), "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv444p",
                            clip], check=True)
            out = os.path.join(t, "frames")
            p = subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "refs", "frames.py"), clip, "--name",
                                "x", "--fps", "4", "--out", out], capture_output=True, text=True,
                               env={**os.environ, "KIT_BUILD": t})
            res = json.loads(p.stdout.strip().splitlines()[-1])
            self.assertEqual((res["status"], res["kept"]), ("pass", 3), p.stdout + p.stderr)
            self.assertEqual(len(os.listdir(out)), 3)


if __name__ == "__main__":
    unittest.main()
