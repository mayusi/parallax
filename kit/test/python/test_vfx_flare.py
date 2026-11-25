"""Unit tests of the lens flare's rule (kit/vfx/flare.py) and its three pictures (kit/vfx/lens.py).
Run: python -m pytest kit/test/python/test_vfx_flare.py -q"""
import contextlib
import io
import json
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import flare as F  # noqa: E402
import lens as L  # noqa: E402


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = F.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


class TheRule(unittest.TestCase):
    def test_the_glow_sits_on_the_light(self):
        m = F.marks(0.3, 0.7, 16 / 9, {})
        self.assertEqual((m[0]["kind"], m[0]["x"], m[0]["y"]), (1, 0.3, 0.7))
        self.assertEqual(m[0]["w"], m[0]["h"])                       # round, whatever the screen's shape

    def test_every_ghost_is_on_the_line_through_the_middle(self):
        lx, ly = 0.15, 0.8
        for g in (m for m in F.marks(lx, ly, 4 / 3, {"ghosts": 8}) if m["kind"] == 3):
            cross = (0.5 - lx) * (g["y"] - ly) - (0.5 - ly) * (g["x"] - lx)
            self.assertAlmostEqual(cross, 0, places=12)

    def test_ghosts_lie_on_both_sides_of_the_middle(self):
        ghosts = [m for m in F.marks(0.2, 0.5, 16 / 9, {"ghosts": 5}) if m["kind"] == 3]
        self.assertTrue(any(g["x"] < 0.5 for g in ghosts) and any(g["x"] > 0.5 for g in ghosts))

    def test_a_light_at_the_middle_stacks_its_ghosts_there(self):
        for g in (m for m in F.marks(0.5, 0.5, 16 / 9, {}) if m["kind"] == 3):
            self.assertEqual((g["x"], g["y"]), (0.5, 0.5))
        self.assertFalse([c for c in F.check(F.marks(0.5, 0.5, 16 / 9, {}), 0.5, 0.5, {}) if not c["ok"]])

    def test_the_flare_fades_as_the_light_leaves_and_is_gone_past_the_edge(self):
        on = F.marks(1.0, 0.5, 16 / 9, {})[0]["a"]
        half = F.marks(1.075, 0.5, 16 / 9, {})[0]["a"]
        self.assertEqual(on, 1.0)
        self.assertAlmostEqual(half, 0.5, places=9)
        self.assertEqual(F.marks(1.16, 0.5, 16 / 9, {}), [])               # (1.15 is the edge itself)
        self.assertEqual(F.marks(0.5, -0.2, 16 / 9, {"ghosts": 8, "streak": 1}), [])

    def test_the_streak_is_level_and_as_long_as_said_on_any_screen(self):
        for aspect in (16 / 9, 4 / 3, 0.46):
            s = [m for m in F.marks(0.5, 0.5, aspect, {"streak": 0.6})][1]
            self.assertEqual(s["kind"], 2)
            self.assertAlmostEqual(s["w"] / aspect, 0.6)             # 0.6 of the screen's WIDTH
            self.assertGreater(s["w"], s["h"] * 4)
        self.assertEqual([m["kind"] for m in F.marks(0.5, 0.5, 1.6, {"streak": 0, "ghosts": 0})], [1])

    def test_squeeze_widens_ghosts_only_and_is_held_to_its_range(self):
        plain = [m for m in F.marks(0.3, 0.3, 1.6, {"ghosts": 3}) if m["kind"] == 3]
        wide = [m for m in F.marks(0.3, 0.3, 1.6, {"ghosts": 3, "squeeze": 2}) if m["kind"] == 3]
        most = [m for m in F.marks(0.3, 0.3, 1.6, {"ghosts": 3, "squeeze": 50}) if m["kind"] == 3]
        for a, b, c in zip(plain, wide, most):
            self.assertAlmostEqual(b["w"], a["w"] * 2)
            self.assertEqual(b["h"], a["h"])
            self.assertAlmostEqual(c["w"], a["w"] * 3)
        self.assertEqual(F.marks(0.3, 0.3, 1.6, {"squeeze": 2})[0]["w"], F.marks(0.3, 0.3, 1.6, {})[0]["w"])  # the glow stays round

    def test_the_number_of_ghosts_is_whole_and_at_most_eight(self):
        count = lambda f: sum(1 for m in F.marks(0.3, 0.3, 1.6, f) if m["kind"] == 3)  # noqa: E731
        self.assertEqual([count({"ghosts": g}) for g in (0, 1, 5.9, 8, 40, -3)], [0, 1, 5, 8, 8, 0])


class TheChecks(unittest.TestCase):
    def test_a_ghost_off_the_line_is_caught(self):
        m = F.marks(0.25, 0.3, 16 / 9, {"ghosts": 5})
        m[3]["y"] += 0.02
        self.assertIn("axis", [c["name"] for c in F.check(m, 0.25, 0.3, {"ghosts": 5}) if not c["ok"]])

    def test_a_glow_off_the_light_is_caught(self):
        m = F.marks(0.25, 0.3, 16 / 9, {})
        m[0]["x"] += 0.05
        self.assertIn("glow", [c["name"] for c in F.check(m, 0.25, 0.3, {}) if not c["ok"]])

    def test_ghosts_bunched_on_one_side_are_caught(self):
        m = F.marks(0.25, 0.3, 16 / 9, {"ghosts": 5})
        for g in (x for x in m if x["kind"] == 3):                   # all pulled to the light's side of the middle
            k = 0.1 * g["i"]
            g["x"], g["y"] = 0.25 + (0.5 - 0.25) * k, 0.3 + (0.5 - 0.3) * k
        self.assertIn("both_sides", [c["name"] for c in F.check(m, 0.25, 0.3, {"ghosts": 5}) if not c["ok"]])

    def test_marks_for_a_light_off_the_screen_are_caught(self):
        m = F.marks(0.25, 0.3, 16 / 9, {})
        self.assertIn("gone", [c["name"] for c in F.check(m, 1.4, 0.5, {}) if not c["ok"]])


class TheCommand(unittest.TestCase):
    def test_it_draws_the_look_and_says_what_it_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = os.path.join(tmp, "look.png")
            code, said = run(["--light", "0.2,0.25", "--streak", "0.7", "--out", png])
            self.assertEqual((code, said["status"], said["marks"]), (0, "pass", 7))
            self.assertTrue(os.path.isfile(png))
            from PIL import Image
            import numpy as np
            img = np.asarray(Image.open(png).convert("L"), dtype=np.float64)
            h, w = img.shape
            self.assertGreater(img[int(0.25 * h), int(0.2 * w)], 200)      # the light is where it was put
            self.assertLess(img[int(0.9 * h), int(0.1 * w)], 5)            # and nothing where no mark is

    def test_a_light_off_the_screen_draws_no_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = os.path.join(tmp, "look.png")
            code, said = run(["--light", "1.5,0.5", "--out", png])
            self.assertEqual((code, said["marks"]), (0, 0))
            self.assertFalse(os.path.exists(png))

    def test_wrong_options_are_refused_in_words(self):
        for argv, word in ((["--light", "0.2"], "--light"), (["--ghosts", "12"], "--ghosts"), (["--glare", "1"], "not an option"),
                           (["--aspect", "9"], "--aspect"), (["--color", "300,0,0"], "--color"), (["--light"], "no value")):
            code, said = run(argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, said["summary"], argv)


class ThePictures(unittest.TestCase):
    def test_the_three_are_in_the_lens_set_and_keep_their_alpha(self):
        for name in ("lens_glow", "lens_ghost", "lens_streak"):
            self.assertIn(name, L.LENS)
            rgb, a = L.LENS[name][0]()
            self.assertEqual(rgb.shape[:2], a.shape)
            self.assertTrue(0 <= a.min() and a.max() <= 1)
            self.assertLess(max(a[0].max(), a[-1].max(), a[:, 0].max(), a[:, -1].max()), 0.02, name)  # no edge of the picture shows

    def test_the_streak_is_much_longer_than_tall(self):
        _, a = L.streak()
        n = a.shape[0]
        wide = (a[n // 2] > 0.1).sum()
        tall = (a[:, n // 2] > 0.1).sum()
        self.assertGreater(wide, tall * 5)
        self.assertTrue(math.isclose(a[n // 2, n // 4], a[n // 2, n - 1 - n // 4], rel_tol=1e-9))  # the same to both ends


if __name__ == "__main__":
    unittest.main()
