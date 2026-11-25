"""kit ui saliency: the first-look gate (LIMITATIONS_FIXES_V4 UI-X 6.4 step 4 / 13.6, UEyes / UIGaze). A screen whose
focus does not take >= 85% of simulated first looks fails; the blur+contrast map, the UEyes location prior, the
UIGaze protocol (gaze points -> a map, CC / NSS / KLD) and the UEyes calibration are measured here on fixtures."""

import csv
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
FIX = os.path.join(ROOT, "kit", "selftest", "ui", "saliency")
sys.path.insert(0, os.path.join(ROOT, "kit", "ui"))
import saliency  # noqa: E402

W0 = dict(saliency.DEFAULTS)  # the tests never read a calibration file from the working tree


def fixture(name):
    img = Image.open(os.path.join(FIX, f"{name}.png")).convert("RGB")
    boxes = saliency.read_boxes(os.path.join(FIX, f"{name}.boxes.json"), img.size[0])
    return img, boxes


def two_boxes(bright_left, size=(480, 270)):
    """two equal boxes on grey; one of them high-contrast"""
    im = Image.new("RGB", size, (60, 60, 64))
    d = ImageDraw.Draw(im)
    hi, lo = (250, 250, 250), (70, 70, 74)
    d.rectangle([60, 110, 140, 160], fill=hi if bright_left else lo)
    d.rectangle([340, 110, 420, 160], fill=lo if bright_left else hi)
    boxes = {"Root": (0, 0, size[0], size[1]), "Root.Left": (60, 110, 80, 50), "Root.Right": (340, 110, 80, 50)}
    return im, boxes


class Gate(unittest.TestCase):
    def test_a_drowned_focus_fails_and_a_loud_one_passes(self):
        img, boxes = fixture("SalBad")
        bad = saliency.judge(img, boxes, "Hud.Ammo", W0)
        self.assertLess(bad["match"], saliency.MIN_MATCH)
        self.assertEqual(bad["elsewhere"][0][0], "Hud.Banner")  # (what took the eye is named)
        img, boxes = fixture("SalGood")
        good = saliency.judge(img, boxes, "Hud.Ammo", W0)
        self.assertGreaterEqual(good["match"], saliency.MIN_MATCH)
        self.assertEqual(len(good["looks"]), W0["viewers"])

    def test_contrast_decides_between_two_equal_boxes(self):
        for left in (True, False):
            img, boxes = two_boxes(left)
            res = saliency.judge(img, boxes, "Root.Left" if left else "Root.Right", dict(W0, prior=0.0))
            self.assertGreaterEqual(res["match"], 0.85)

    def test_the_viewers_are_seeded(self):
        img, boxes = fixture("SalBad")
        self.assertEqual(saliency.first_looks(img, W0, 6, seed=3), saliency.first_looks(img, W0, 6, seed=3))

    def test_a_look_inside_a_child_of_the_focus_counts_and_the_pad_is_about_one_degree(self):
        boxes = {"Hud.Ammo": (100, 100, 50, 20), "Hud.Ammo.Count": (110, 104, 20, 10), "Hud.Map": (0, 0, 20, 20)}
        self.assertTrue(saliency.lands_on((115, 108), boxes, "Hud.Ammo", 0))
        self.assertTrue(saliency.lands_on((155, 110), boxes, "Hud.Ammo", 8))
        self.assertFalse(saliency.lands_on((155, 110), boxes, "Hud.Ammo", 0))
        self.assertFalse(saliency.lands_on((10, 10), boxes, "Hud.Ammo", 8))
        self.assertEqual(saliency.landed_on((115, 108), boxes, "Hud.Ammo"), "Hud.Ammo.Count")
        self.assertIsNone(saliency.landed_on((400, 400), boxes, "Hud.Ammo"))


class Prior(unittest.TestCase):
    def test_the_ueyes_top_left_bias_moves_the_peak(self):
        p0 = saliency.prior_map(90, 160, 0.0)
        p1 = saliency.prior_map(90, 160, 1.0)
        y0, x0 = np.unravel_index(int(np.argmax(p0)), p0.shape)
        y1, x1 = np.unravel_index(int(np.argmax(p1)), p1.shape)
        self.assertAlmostEqual(x0 / 159, 0.5, delta=0.02)
        self.assertAlmostEqual(x1 / 159, 0.25, delta=0.02)
        self.assertLess(y1, y0)

    def test_on_a_blank_picture_the_prior_alone_decides(self):
        img = Image.new("RGB", (320, 180), (40, 40, 40))
        S = saliency.saliency_map(img, dict(W0, prior=1.0, topleft=1.0))
        self.assertEqual(S.shape, (180, 320))
        y, x = np.unravel_index(int(np.argmax(S)), S.shape)
        self.assertLess(x, 160)
        self.assertLess(y, 90)


class Metrics(unittest.TestCase):
    def test_cc_nss_kld(self):
        rng = np.random.default_rng(1)
        a = rng.random((20, 30))
        self.assertAlmostEqual(saliency.cc(a, a), 1.0, places=6)
        self.assertAlmostEqual(saliency.cc(a, -a), -1.0, places=6)
        fix = np.zeros_like(a)
        fix[np.unravel_index(int(np.argmax(a)), a.shape)] = 1
        self.assertGreater(saliency.nss(a, fix), 1.0)
        self.assertEqual(saliency.nss(a, np.zeros_like(a)), 0.0)
        self.assertAlmostEqual(saliency.kld(a, a), 0.0, places=6)
        self.assertGreater(saliency.kld(a, 1 - a), 0.01)

    def test_uigaze_points_become_a_map_peaking_at_them(self):
        m = saliency.points_to_map([(10, 5)], 20, 40, 2.0)
        self.assertEqual(np.unravel_index(int(np.argmax(m)), m.shape), (5, 10))
        self.assertEqual(m.max(), 1.0)
        self.assertEqual(saliency.points_to_map([], 4, 4, 1.0).max(), 0.0)

    def test_a_vlm_answer_on_a_0_1000_scale_is_read_in_picture_pixels(self):
        pts = saliency.parse_points("Sure: [[500, 250], [1000,0]] and [2000, 5] junk [x, y]", 1920, 1080)
        self.assertEqual(pts, [(960.0, 270.0), (1920.0, 0.0)])
        self.assertEqual(saliency.parse_points("", 10, 10), [])
        self.assertIn("{n}", saliency.UIGAZE_PROMPT)


class Calibration(unittest.TestCase):
    def make_ueyes(self, root, n=8):
        """a UEyes-shaped folder: info.csv + images/ + saliency_maps/fixmaps_1s + heatmaps_1s; people look at a
        small dim square in the bottom-right, never at the loud bar top-left"""
        os.makedirs(os.path.join(root, "images"))
        os.makedirs(os.path.join(root, "saliency_maps", "fixmaps_1s"))
        os.makedirs(os.path.join(root, "saliency_maps", "heatmaps_1s"))
        rng = np.random.default_rng(5)
        with open(os.path.join(root, "info.csv"), "w", encoding="utf-8", newline="") as fh:
            wr = csv.writer(fh)
            wr.writerow(["Image Name", "Category", "Block", "Train/Test"])
            for i in range(n):
                name = f"ui_{i}.png"
                wr.writerow([name, "mobile", 1, "test" if i % 4 == 3 else "train"])
                im = Image.new("RGB", (320, 180), (90, 90, 96))
                d = ImageDraw.Draw(im)
                x, y = int(rng.integers(180, 260)), int(rng.integers(100, 140))
                d.rectangle([x, y, x + 24, y + 16], fill=(120, 120, 128))
                d.rectangle([10, 10, 150, 30], fill=(255, 255, 255))
                im.save(os.path.join(root, "images", name))
                fx = Image.new("L", (320, 180), 0)
                ImageDraw.Draw(fx).point([(x + 12, y + 8)], fill=255)
                fx.save(os.path.join(root, "saliency_maps", "fixmaps_1s", name))
                ht = Image.new("L", (320, 180), 0)
                ImageDraw.Draw(ht).ellipse([x - 4, y - 4, x + 28, y + 20], fill=255)
                ht.save(os.path.join(root, "saliency_maps", "heatmaps_1s", name))
            # a row whose maps are missing is skipped, not a crash
            wr.writerow(["missing.png", "web", 1, "train"])

    def test_the_folder_is_read_and_split(self):
        with tempfile.TemporaryDirectory() as root:
            self.make_ueyes(root)
            tr = saliency.ueyes_items(root, "train")
            te = saliency.ueyes_items(root, "test")
            self.assertEqual((len(tr), len(te)), (6, 2))
            self.assertTrue(all(h for _, _, h, _ in tr))
            self.assertEqual(saliency.ueyes_items(os.path.join(root, "nowhere")), [])

    def test_calibration_fits_the_people_better_than_the_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            self.make_ueyes(root)
            items = saliency.ueyes_items(root, "train")
            base = {k: v for k, v in W0.items() if k != "source"}
            before = saliency.score(items, base)[0]
            res = saliency.calibrate(root, limit=50, grid={"prior": (0.0, 0.7), "topleft": (0.0, 0.7),
                                                           "w_lum": (0.2, 1.0)}, write=False)
            self.assertIsNotNone(res)
            self.assertGreater(res["train_nss"], before)
            self.assertIn("6 train / 2 test", res["source"])
            self.assertEqual(len(res["info_sha1"]), 40)

    def test_calibrate_without_ueyes_says_what_is_owed(self):
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as root, redirect_stdout(buf):
            code = saliency.main(["calibrate", "--ueyes", root])
        self.assertEqual(code, 1)
        out = json.loads(buf.getvalue())
        self.assertIn("UEyes", out["next_action"])
        self.assertIn("VETLOG", out["next_action"])


class Cli(unittest.TestCase):
    def test_check_exits_by_the_gate(self):
        for name, want in (("SalBad", 1), ("SalGood", 0)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = saliency.main(["check", "--frame", os.path.join(FIX, f"{name}.png"), "--boxes",
                                      os.path.join(FIX, f"{name}.boxes.json"), "--focus", "Hud.Ammo"])
            self.assertEqual(code, want, buf.getvalue())

    def test_no_focus_and_an_unknown_focus_fail_with_the_fix(self):
        for focus, said in ((None, "names no"), ("Hud.Nope", "has no box")):
            buf = io.StringIO()
            args = ["check", "--frame", os.path.join(FIX, "SalGood.png"), "--boxes", os.path.join(FIX, "SalGood.boxes.json")]
            if focus:
                args += ["--focus", focus]
            with redirect_stdout(buf):
                self.assertEqual(saliency.main(args), 1)
            self.assertIn(said, json.loads(buf.getvalue())["summary"])


if __name__ == "__main__":
    unittest.main()
