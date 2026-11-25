"""kit/gen/qwen_edit.py + kit/vision/setup.py: a requested camera snaps to the nearest of the Multiple-Angles LoRA's 96
poses (the prompt words it was trained on), the output keeps the input's aspect in multiples of 16, a zip with a path
outside its folder is refused whole, and the big on-demand entries are pinned (size + sha256, a commit or a tag)."""

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "gen"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vision"))
import qwen_edit as Q  # noqa: E402
import setup as S  # noqa: E402


class TestPose(unittest.TestCase):
    def test_snaps_to_the_trained_words(self):
        self.assertEqual(Q.pose(80, 10, "mid"), ("right side view eye-level shot medium shot", 90, 0))
        self.assertEqual(Q.pose(-45, 30, "far"), ("front-left quarter view elevated shot wide shot", 315, 30))
        self.assertEqual(Q.pose(350, -90, "near"), ("front view low-angle shot close-up", 0, -30))
        self.assertEqual(Q.pose(180, 90, "mid")[1:], (180, 60))

    def test_every_pose_is_one_of_96(self):
        seen = {Q.pose(a, e, d)[0] for a in range(0, 360, 5) for e in range(-40, 70, 5) for d in Q.DISTANCES}
        self.assertEqual(len(seen), 96)


class TestSize(unittest.TestCase):
    def test_aspect_and_multiples_of_16(self):
        for w, h in ((1920, 1440), (1600, 1067), (640, 480), (500, 2000)):
            W, H = Q.out_size(w, h, 1024)
            self.assertEqual((W % 16, H % 16), (0, 0))
            self.assertAlmostEqual(W / H, w / h, delta=0.03 * w / h)
            self.assertLess(abs(W * H - 1024 * 1024) / (1024 * 1024), 0.06)


class TestUnzip(unittest.TestCase):
    def _zip(self, d, names):
        p = os.path.join(d, "t.zip")
        with zipfile.ZipFile(p, "w") as z:
            for n in names:
                z.writestr(n, "x")
        return p

    def test_plain_zip_unpacks(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out")
            os.makedirs(out)
            self.assertEqual(S.unzip_safe(self._zip(d, ["a.dll", "sub/b.txt"]), out), 2)
            self.assertTrue(os.path.isfile(os.path.join(out, "sub", "b.txt")))

    def test_path_outside_is_refused_whole(self):
        for bad in ("../evil.txt", "sub/../../evil.txt", "/abs.txt"):
            with tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "out")
                os.makedirs(out)
                with self.assertRaises(ValueError):
                    S.unzip_safe(self._zip(d, ["ok.txt", bad]), out)
                self.assertEqual(os.listdir(out), [])  # (nothing written, not even the safe file)


class TestPins(unittest.TestCase):
    def test_on_demand_entries_are_pinned(self):
        # (the big generation entries are fetched only on request: since the hardware tiers that is the "gen" tier -
        # never in a default `kit vision setup`, which takes the core tier - where they used to be "on_demand")
        with open(S.MANIFEST, encoding="utf-8") as fh:
            whole = json.load(fh)
        man = whole["models"]
        default, _ = S.selected(whole, "core", None)
        for name in ("qwen-image-edit", "sd-cpp"):
            m = man[name]
            self.assertEqual(m["tier"], "gen")
            self.assertNotIn(name, default)
            for f in m["files"]:
                self.assertRegex(f["sha256"], r"^[0-9a-f]{64}$")
                self.assertGreater(f["size"], 0)
                self.assertTrue(re.search(r"/resolve/[0-9a-f]{40}/", f["url"])
                                or "/releases/download/master-929-3f8527a/" in f["url"], f["url"])
        self.assertTrue(man["sd-cpp"]["tool"])


class TestUsage(unittest.TestCase):
    def test_angle_needs_both_angles(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.png")
            Image.new("RGB", (64, 64)).save(p)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = Q.main(["angle", p, "--azimuth", "90"])
            self.assertEqual(code, 1)
            self.assertIn("--elevation", json.loads(buf.getvalue().strip().splitlines()[-1])["summary"])


if __name__ == "__main__":
    unittest.main()
