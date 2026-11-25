"""The moderation gate's image half (kit/tools/mod_gate.py): the drawn blood pool and splatter are held, a fire puff
passes, and an image the tool cannot read is never treated as clean (blood and gore get the uploading account moderated)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import mod_gate as G  # noqa: E402

DRAW = os.path.join(ROOT, "kit", "selftest", "moderation", "draw_blood.py")


class ModGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="modgate_")
        subprocess.run([sys.executable, "-I", DRAW, cls.tmp], check=True, capture_output=True)

    def path(self, name):
        return os.path.join(self.tmp, name)

    def test_a_blood_pool_is_held(self):
        r = G.measure(self.path("pool.png"))
        self.assertTrue(r["flagged"], r)
        self.assertGreater(r["crimson"], 0.9)

    def test_a_splatter_is_held(self):
        r = G.measure(self.path("splat.png"))
        self.assertTrue(r["flagged"], r)

    def test_a_fire_puff_passes(self):
        r = G.measure(self.path("ember.png"))
        self.assertFalse(r["flagged"], r)
        self.assertLess(r["crimson"], 0.02)

    def test_scattered_red_drops_below_the_share_are_still_held_as_a_splatter(self):
        # a grey stone with a sprinkle of red drops: under the 30% hold, over the 8% splatter share, many patches
        im = Image.new("RGBA", (256, 256), (120, 120, 120, 255))
        px = im.load()
        for k in range(12):
            cx, cy = 20 + (k % 4) * 60, 30 + (k // 4) * 80
            for y in range(cy - 12, cy + 12):  # 12 drops of 24 x 24: about 10% of the stone
                for x in range(cx - 12, cx + 12):
                    px[x, y] = (130, 10, 15, 255)
        p = self.path("stone_drops.png")
        im.save(p)
        r = G.measure(p)
        self.assertTrue(0.08 <= r["crimson"] < 0.30, r)
        self.assertGreaterEqual(r["patches"], 6, r)
        self.assertTrue(r["flagged"], r)

    def test_a_clear_image_passes(self):
        p = self.path("clear.png")
        Image.new("RGBA", (64, 64), (200, 0, 0, 0)).save(p)  # red, but nothing shown
        r = G.measure(p)
        self.assertFalse(r["flagged"], r)

    def test_an_unreadable_file_is_reported_not_passed(self):
        p = self.path("broken.png")
        with open(p, "wb") as f:
            f.write(b"not a png")
        out = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "kit", "tools", "mod_gate.py"), p],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        d = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(d["images"], [])
        self.assertEqual(len(d["unreadable"]), 1)


if __name__ == "__main__":
    unittest.main()
