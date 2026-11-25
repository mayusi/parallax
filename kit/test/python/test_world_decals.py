"""test_world_decals.py - A DECAL'S PICTURE, MADE BY RULE (kit/world/decals.py; the owner's method list: "Decal-based
detailing"). Held here: what the command may be told, that every kind's picture has a clear border (no square shows on
the wall), covers a fair share, is the same for the same seed, and that a picture which is no decal is not written.
Not claimed here: that a leak looks like a leak. That is looked at (the audit page says what was seen)."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_world_decals", os.path.join(HERE, "..", "..", "world", "decals.py"))
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)


class Pictures(unittest.TestCase):
    def test_every_kind_is_a_decal_for_many_seeds(self):
        for kind in D.KINDS:
            for seed in (0, 1, 2, 7, 40, 65535):
                rgba = D.picture(kind, seed, 256, D.TINT[kind])
                self.assertEqual(rgba.shape, (256, 256, 4))
                self.assertEqual(rgba.dtype, np.uint8)
                wrong, measured = D.judged(rgba, kind)
                self.assertEqual(wrong, [], (kind, seed, measured))
                # the border is clear on all four sides: two pixels of nothing
                a = rgba[..., 3]
                self.assertEqual(int(a[:2].max()), 0)
                self.assertEqual(int(a[-2:].max()), 0)
                self.assertEqual(int(a[:, :2].max()), 0)
                self.assertEqual(int(a[:, -2:].max()), 0)
                self.assertEqual(measured["border"], 0)
                lo, hi = D.COVER[kind]
                self.assertTrue(lo <= measured["cover"] <= hi)

    def test_the_same_seed_makes_the_same_picture_and_another_seed_another(self):
        for kind in D.KINDS:
            a = D.picture(kind, 3, 128, D.TINT[kind])
            b = D.picture(kind, 3, 128, D.TINT[kind])
            c = D.picture(kind, 4, 128, D.TINT[kind])
            self.assertTrue((a == b).all(), kind)
            self.assertTrue((a[..., 3] != c[..., 3]).mean() > 0.005, kind)
        # two kinds of one seed are two pictures
        self.assertTrue((D.picture("leak", 3, 128, (0, 0, 0))[..., 3] != D.picture("soot", 3, 128, (0, 0, 0))[..., 3]).mean() > 0.05)

    def test_a_kinds_own_shape(self):
        for seed in (1, 2, 3, 4):
            leak = D.alpha("leak", seed, 128) * D.window(128)
            soot = D.alpha("soot", seed, 128) * D.window(128)
            self.assertTrue(leak[:43].mean() > leak[-43:].mean() * 1.5)  # (water ran down from the top)
            self.assertTrue(soot[-43:].mean() > soot[:43].mean() * 1.5)  # (smoke rose from the bottom)
            # soot is narrow where it began and wider above
            low, high = soot[100] > 0.2, soot[50] > 0.05
            self.assertTrue(high.sum() > low.sum())
            # a crack is thin: a small share, in lines
            crack = D.alpha("crack", seed, 128)
            self.assertTrue(0.003 < (crack > 0.1).mean() < 0.12)
            # a stain has a rim darker than its body
            stain = D.alpha("stain", seed, 256)
            self.assertTrue(stain.max() > stain[128, 128] * 1.2)

    def test_the_tint_is_the_pictures_colour(self):
        rgba = D.picture("moss", 2, 128, (58, 84, 40))
        seen = rgba[..., :3][rgba[..., 3] > 30].mean(axis=0)
        self.assertTrue(seen[1] > seen[0] > seen[2])  # (green over red over blue, as the tint)
        self.assertTrue(abs(seen[1] - 84) < 20)
        grey = D.picture("moss", 2, 128, (100, 100, 100))
        self.assertTrue((grey[..., 0] == grey[..., 1]).all() and (grey[..., 1] == grey[..., 2]).all())
        self.assertTrue((grey[..., 3] == rgba[..., 3]).all())  # (the tint does not change the shape)

    def test_the_window_fades_to_nothing(self):
        w = D.window(200)
        self.assertEqual(w.shape, (200, 200))
        self.assertEqual(float(w[0].max()), 0.0)
        self.assertEqual(float(w[:, -1].max()), 0.0)
        self.assertEqual(float(w[1].max()), 0.0)
        self.assertAlmostEqual(float(w[100, 100]), 1.0)
        self.assertAlmostEqual(float(w[100, 30]), 1.0)  # (past the edge's 12 %: untouched)
        self.assertTrue(0 < w[100, 10] < 1)
        self.assertTrue((np.diff(w[100, :100]) >= 0).all())  # (it only rises toward the middle)
        self.assertTrue((w == w.T).all() and (w == w[::-1]).all())


class Judging(unittest.TestCase):
    def blank(self, n=64):
        return np.zeros((n, n, 4), dtype=np.uint8)

    def test_what_is_no_decal_is_said(self):
        # a square that reaches its border: the decal's square would show
        full = self.blank()
        full[..., :3] = 40
        full[..., 3] = 200
        wrong, _ = D.judged(full, "stain")
        self.assertTrue(any("border is not clear" in w for w in wrong))
        self.assertTrue(any("covers 100.0 %" in w for w in wrong))
        # one pixel on the border is enough
        one = self.blank()
        one[20:40, 20:40] = (40, 40, 40, 220)
        self.assertEqual(D.judged(one, "stain")[0], [])
        for spot in ((0, 30), (63, 30), (30, 0), (30, 63), (1, 30), (30, 62)):
            edge = one.copy()
            edge[spot] = (40, 40, 40, 3)
            self.assertTrue(any("border is not clear" in w for w in D.judged(edge, "stain")[0]), spot)
        inner = one.copy()
        inner[2, 30] = (40, 40, 40, 3)  # (the third pixel in is the picture's own)
        self.assertEqual(D.judged(inner, "stain")[0], [])
        # nothing at all, and too faint
        wrong, _ = D.judged(self.blank(), "moss")
        self.assertTrue(any("covers 0.0 %" in w for w in wrong))
        faint = self.blank()
        faint[10:50, 10:50] = (40, 40, 40, 100)
        self.assertTrue(any("too faint" in w for w in D.judged(faint, "stain")[0]))
        faint[10:50, 10:50, 3] = 128
        self.assertEqual(D.judged(faint, "stain")[0], [])
        # a leak heavier at its foot, soot heavier at its top
        low = self.blank()
        low[40:60, 10:54] = (40, 40, 40, 220)
        self.assertTrue(any("heavier at its top" in w for w in D.judged(low, "leak")[0]))
        self.assertEqual([w for w in D.judged(low, "soot")[0]], [])
        self.assertTrue(any("heavier at its foot" in w for w in D.judged(low[::-1].copy(), "soot")[0]))
        self.assertEqual(D.judged(low[::-1].copy(), "leak")[0], [])
        # a crack may be thin where a stain may not
        thin = self.blank()
        thin[30:32, 10:54] = (20, 20, 20, 230)
        self.assertEqual(D.judged(thin, "crack")[0], [])
        self.assertTrue(any("covers" in w for w in D.judged(thin, "stain")[0]))
        # no blood
        red = self.blank()
        red[20:44, 20:44] = (150, 15, 15, 230)
        self.assertTrue(any("reads as blood" in w for w in D.judged(red, "stain")[0]))

    def test_what_reads_as_blood(self):
        # ONE TABLE, held in kit/test/spec/worlddecal.spec.luau too (the build step's tint is judged by the same rule)
        for tint in ((150, 20, 20), (120, 10, 40), (200, 80, 80), (61, 0, 0), (255, 114, 114), (120, 54, 54), (59, 0, 0), (80, 0, 40), (130, 20, 60), (100, 40, 60), (40, 0, 0), (200, 40, 95), (150, 60, 50), (255, 0, 0), (30, 0, 0), (200, 50, 20), (200, 20, 120)):
            self.assertTrue(D.bloody(tint), tint)  # (reds and crimsons, bright or dark, what a reader got past the first rule)
        for tint in ((150, 75, 40), (140, 60, 30), (46, 40, 33), (66, 56, 42), (22, 21, 20), (58, 84, 40), (16, 15, 15), (200, 95, 40), (29, 0, 0), (120, 90, 80), (0, 0, 0), (60, 60, 200), (200, 100, 200), (255, 255, 255), (200, 60, 20), (200, 20, 130), (100, 100, 20)):
            self.assertFalse(D.bloody(tint), tint)  # (rust, brick-orange, the kinds' own tints, black, other colours)
        for kind in D.KINDS:
            self.assertFalse(D.bloody(D.TINT[kind]), kind)


class Command(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kit_decals_")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = D.main(list(argv))
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_a_decal_is_written_with_its_record(self):
        code, said = self.run_main("make", self.dir, "--name", "Leak_1", "--kind", "leak", "--seed", "5", "--size", "256")
        self.assertEqual((code, said["status"]), (0, "pass"), said)
        png = os.path.join(self.dir, "Leak_1.png")
        im = Image.open(png)
        self.assertEqual((im.mode, im.size), ("RGBA", (256, 256)))
        self.assertTrue((np.asarray(im) == D.picture("leak", 5, 256, D.TINT["leak"])).all())
        with open(os.path.join(self.dir, "Leak_1.decal.json"), encoding="utf-8") as fh:
            record = json.load(fh)
        self.assertEqual({k: record[k] for k in ("name", "kind", "seed", "size", "tint", "file")},
                         {"name": "Leak_1", "kind": "leak", "seed": 5, "size": 256, "tint": [46, 40, 33], "file": "Leak_1.png"})
        self.assertEqual(record["checked"]["border"], 0)
        self.assertEqual(said["record"], record)
        # its own tint
        code, said = self.run_main("make", self.dir, "--name", "Rust2", "--kind", "leak", "--tint", "140,60,30")
        self.assertEqual(code, 0, said)  # (a rust stain is no blood: a reader found the first rule refused it)
        code, said = self.run_main("make", self.dir, "--name", "Rust", "--kind", "leak", "--tint", "150,75,40")
        self.assertEqual(code, 0, said)
        self.assertEqual(said["record"]["tint"], [150, 75, 40])
        self.assertEqual(said["record"]["size"], 512)
        self.assertEqual(said["record"]["seed"], 1)

    def test_a_decal_that_fails_leaves_nothing_of_its_name(self):
        code, _ = self.run_main("make", self.dir, "--name", "X", "--kind", "moss")
        self.assertEqual(code, 0)
        real = D.judged
        D.judged = lambda rgba, kind: (["it is no decal"], {})
        try:
            code, said = self.run_main("make", self.dir, "--name", "X", "--kind", "moss", "--seed", "2")
        finally:
            D.judged = real
        self.assertEqual((code, said["status"]), (1, "fail"))
        self.assertIn("X was not made: it is no decal", said["summary"])
        self.assertEqual(os.listdir(self.dir), [])  # (the earlier X is not left to be taken for this one)

    def test_what_is_wrong_is_said(self):
        base = ["make", self.dir, "--name", "X", "--kind", "leak"]
        for argv, text in (
            ([], "usage:"),
            (["make"], "usage:"),
            (["make", "--name", "X"], "usage:"),
            (["paint", self.dir, "--name", "X", "--kind", "leak"], "usage:"),
            (["make", self.dir, "--kind", "leak"], "--name says what the decal is called"),
            (["make", self.dir, "--name", "X"], "--kind says what it is"),
            (["make", self.dir, "--name", "a b", "--kind", "leak"], "--name is the decal's name"),
            (["make", self.dir, "--name", "../x", "--kind", "leak"], "--name is the decal's name"),
            (["make", self.dir, "--name", "X", "--kind", "blood"], "--kind is one of"),
            (base + ["--seed", "-1"], "--seed is a whole number 0 to 65535"),
            (base + ["--seed", "65536"], "--seed is a whole number 0 to 65535"),
            (base + ["--seed", "1.5"], "is a whole number"),
            (base + ["--seed", "x"], "is a number"),
            (base + ["--seed", "nan"], "is a whole number"),
            (base + ["--size", "300"], "--size is 256, 512 or 1024"),
            (base + ["--size", "2048"], "--size is 256, 512 or 1024"),
            (base + ["--tint", "1,2"], "--tint is r,g,b"),
            (base + ["--tint", "1,2,256"], "--tint is r,g,b"),
            (base + ["--tint", "-1,2,3"], "--tint is r,g,b"),
            (base + ["--tint", "150,20,20"], "reads as blood"),
            (base + ["--tint", "120,54,54"], "reads as blood"),
            (base + ["--tint", "59,0,0"], "reads as blood"),
            (base + ["--seed", "1", "--seed", "2"], "said twice"),
            (base + ["--moon", "1"], "--moon is not a word"),
            (base + ["--seed"], "has no value"),
            (base + ["--seed", "1,2"], "--seed is one number"),
        ):
            code, said = self.run_main(*argv)
            self.assertEqual(code, 2, argv)
            self.assertEqual(said["status"], "fail")
            self.assertIn(text, said["summary"], argv)
        self.assertEqual(os.listdir(self.dir), [])
        for more in (["--seed", "0"], ["--seed", "65535"], ["--size", "256"], ["--size", "1024"], ["--tint", "0,0,0"],
                     ["--tint", "255,255,255"]):
            s, why = D.arguments(base + more)
            self.assertIsNone(why, more)
        self.assertEqual(D.KINDS, ("leak", "stain", "crack", "moss", "soot"))


if __name__ == "__main__":
    unittest.main()
