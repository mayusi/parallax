"""kit/vfx/dissolve.py - a texture breaking up over the cells of a sheet - on textures made here whose answer is
known. What is proven is what the sheet is trusted for: cell 0 is the texture and the last cell is empty, nothing comes
back, every cell removes an even share of the area, the pattern tiles, thin parts go first, the burning edge sits on
the front, each check catches the fault it is named for, and a sheet that fails leaves nothing behind."""

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
sys.path.insert(0, os.path.join(HERE, "..", "..", "selftest", "vfx", "dissolve"))
import dissolve as D  # noqa: E402
import run as made  # noqa: E402


def opts(**kw):
    return D.checked(kw)


def named(checks):
    return {c["name"]: c for c in checks}


def area(cells, alpha):
    held = alpha > 0.02
    return [float(((c[..., 3] / np.maximum(alpha, 1e-6))[held] > 0.5).mean()) for c in cells]


class TestPattern(unittest.TestCase):
    def test_the_noise_tiles_both_ways(self):
        n = D.periodic_noise(128, 5, 3)
        self.assertGreaterEqual(float(n.min()), 0.0)
        self.assertLessEqual(float(n.max()), 1.0)
        inside = float(np.abs(n[:, 1:] - n[:, :-1]).mean())
        self.assertLess(float(np.abs(n[:, 0] - n[:, -1]).mean()), 2 * inside)
        self.assertLess(float(np.abs(n[0, :] - n[-1, :]).mean()), 2 * inside)
        self.assertFalse(np.allclose(D.periodic_noise(128, 5, 3), D.periodic_noise(128, 5, 4)))
        self.assertTrue(np.allclose(D.periodic_noise(128, 5, 3), D.periodic_noise(128, 5, 3)))

    def test_levelling_spreads_the_values_evenly(self):
        rng = np.random.default_rng(1)
        field = rng.random((64, 64)) ** 3  # bunched near 0
        where = np.ones((64, 64), bool)
        where[:8] = False
        lv = D.level(field, where)
        inside = np.sort(lv[where])
        self.assertAlmostEqual(float(inside[0]), 0.5 / inside.size, places=6)
        self.assertAlmostEqual(float(np.diff(inside).max()), 1.0 / inside.size, places=6)
        self.assertTrue(np.array_equal(lv[~where], field[~where]))
        # the order is kept: what was lower is still lower
        a, b = np.argsort(field[where], kind="stable"), np.argsort(lv[where], kind="stable")
        self.assertTrue(np.array_equal(a, b))
        self.assertTrue(np.array_equal(D.level(field, np.zeros((64, 64), bool)), field))

    def test_the_dither_screen_is_an_ordered_8x8(self):
        self.assertEqual(sorted(D.BAYER.flatten().tolist()), [float(i) for i in range(64)])
        f = D.pattern_field(np.ones((64, 64)), opts(pattern="dither", dot=2, soft=0))
        self.assertTrue(np.array_equal(f[:16, :16], f[16:32, 16:32]))
        self.assertEqual(float(f[0, 0]), float(f[1, 1]))  # one dot is 2 px
        self.assertEqual(len(np.unique(f)), 64)


class TestCells(unittest.TestCase):
    def setUp(self):
        self.src = made.skin()
        self.alpha = self.src[..., 3]

    def test_from_the_texture_whole_to_nothing_and_nothing_comes_back(self):
        for kw in ({}, {"soft": 0}, {"pattern": "dither", "soft": 0}, {"cells": 64, "cell": 128}, {"cells": 4, "density": 1}):
            o = opts(**kw)
            src = made.skin(o["cell"])
            cells = D.cells_of(src, o)
            self.assertEqual(len(cells), o["cells"])
            self.assertTrue(np.array_equal(cells[0], src), kw)
            self.assertEqual(float(cells[-1][..., 3].max()), 0.0, kw)
            for k in range(len(cells) - 1):
                self.assertLessEqual(float((cells[k + 1][..., 3] - cells[k][..., 3]).max()), 1e-9, (kw, k))
            self.assertGreater(float(cells[-2][..., 3].max()), 0.0, kw)  # the cell before the last still holds something

    def test_every_cell_removes_an_even_share_of_the_area(self):
        cells = D.cells_of(self.src, opts(soft=0))
        a = area(cells, self.alpha)
        steps = [a[k] - a[k + 1] for k in range(15)]
        self.assertAlmostEqual(min(steps), 1 / 15, delta=0.004)
        self.assertAlmostEqual(max(steps), 1 / 15, delta=0.004)
        # ... whatever the front's width and the number of cells: the half-gone line advances evenly (with 64 cells
        # and the default front, and with a front a fifth of the pattern wide, the first cells used to remove nothing)
        for kw in ({"cells": 64, "cell": 128}, {"soft": 0.2}, {"soft": 0.4}, {"cells": 4}):
            o = opts(**kw)
            src = made.skin(o["cell"])
            a = area(D.cells_of(src, o), src[..., 3])
            steps = [a[k] - a[k + 1] for k in range(o["cells"] - 1)]
            even = 1.0 / (o["cells"] - 1)
            self.assertGreater(min(steps), 0.5 * even, kw)
            self.assertLess(max(steps), 1.8 * even, kw)
            self.assertEqual([c["name"] for c in D.check(src, D.cells_of(src, o), o) if not c["ok"] and c["name"] != "breaks"], [], kw)

    def test_thin_parts_go_first_when_density_says_so(self):
        thin = (self.alpha > 0.02) & (self.alpha < 0.3)
        thick = self.alpha > 0.7

        def lost(density):
            mid = D.cells_of(self.src, opts(soft=0, density=density))[8][..., 3]
            return float((mid[thin] == 0).mean()), float((mid[thick] == 0).mean())

        t0, k0 = lost(0)
        t1, k1 = lost(1)
        self.assertLess(abs(t0 - k0), 0.2)   # the pattern alone does not know thin from thick
        self.assertGreater(t1, 0.95)         # steered by alpha: the thin parts are gone by the middle
        self.assertLess(k1, 0.05)

    def test_a_hard_cut_has_no_half_transparent_pixels(self):
        mid = D.cells_of(self.src, opts(soft=0))[8][..., 3]
        covered = self.alpha > 0.1
        ratio = mid[covered] / self.alpha[covered]
        self.assertTrue(np.all((ratio == 0) | (np.abs(ratio - 1) < 1e-9)))

    def test_the_burning_edge_is_on_the_front_only(self):
        o = opts(edge=0.06, edge_color=[255, 255, 255])
        cells = D.cells_of(self.src, o)
        plain = D.cells_of(self.src, opts())
        self.assertTrue(np.array_equal(cells[0], plain[0]))    # none on the whole texture
        self.assertTrue(np.array_equal(cells[-1], plain[-1]))  # none on the empty cell
        changed = np.abs(cells[8][..., :3] - plain[8][..., :3]).max(axis=2) > 0.05
        self.assertGreater(int(changed.sum()), 100)
        self.assertGreater(float((plain[11][..., 3][changed] < 0.05).mean()), 0.9)  # those pixels are the next to go
        self.assertTrue(np.array_equal(cells[8][..., 3], plain[8][..., 3]))            # the edge adds colour, not cover
        with self.assertRaises(ValueError):
            opts(edge=0.06)

    def test_a_plain_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, path = D.load_source("plain", tmp, tmp, 128)
            self.assertIsNone(path)
            self.assertTrue(np.all(src == 1.0))
            self.assertEqual(D.source_id(None), "plain")


class TestChecks(unittest.TestCase):
    def setUp(self):
        self.src = made.skin()
        self.o = opts()
        self.cells = D.cells_of(self.src, self.o)

    def failed(self, cells, o=None, src=None):
        return [c["name"] for c in D.check(self.src if src is None else src, cells, o or self.o) if not c["ok"]]

    def test_the_bake_passes_its_own_checks(self):
        self.assertEqual(self.failed(self.cells), [])
        self.assertEqual(sorted(named(D.check(self.src, self.cells, self.o))), ["breaks", "clears", "monotone", "packs", "source", "steps", "tiles", "whole"])

    def test_each_check_catches_its_fault(self):
        empty = np.zeros_like(self.src)
        self.assertEqual(self.failed([empty] * 16, src=empty), ["source"])
        bad = [c.copy() for c in self.cells]
        bad[0][..., 3] *= 0.9
        self.assertIn("whole", self.failed(bad))
        bad = [c.copy() for c in self.cells]
        bad[-1] = self.cells[-2].copy()
        self.assertIn("clears", self.failed(bad))
        bad = [c.copy() for c in self.cells]
        bad[9] = self.cells[5].copy()
        self.assertIn("monotone", self.failed(bad))
        bad = [c.copy() for c in self.cells]
        bad[6] = self.cells[5].copy()  # a held frame
        self.assertIn("steps", self.failed(bad))
        pop = [self.cells[0].copy() for _ in range(8)] + [self.cells[-1].copy() for _ in range(8)]
        self.assertIn("steps", self.failed(pop))
        # a POP alone: every cell removes something, one of them a third of the texture at once
        fine = D.cells_of(made.skin(128), opts(cells=64, cell=128, soft=0))
        jump = [fine[i] for i in (0, 2, 4, 6, 8, 10, 30, 33, 36, 39, 42, 45, 48, 51, 57, 63)]
        got = named(D.check(made.skin(128), jump, opts(cell=128, soft=0)))
        self.assertFalse(got["steps"]["ok"])
        self.assertGreater(got["steps"]["value"][0], 0.02)   # (no held frame in it: only the jump is wrong)
        self.assertTrue(all(got[k]["ok"] for k in ("whole", "clears", "monotone", "breaks")))
        fade = []
        for k in range(16):
            c = self.src.copy()
            c[..., 3] *= 1 - k / 15.0
            fade.append(c)
        self.assertIn("breaks", self.failed(fade))

    def test_a_wipe_does_not_tile_and_a_screen_must_fit(self):
        ramp = np.linspace(0, 1, 256)[None, :].repeat(256, 0)   # a left-to-right wipe: a pattern that does not wrap
        for soft in (0.08, 0.0):
            o = opts(soft=soft)
            wipe = D.cells_of(self.src, o, ramp)
            self.assertIn("tiles", [c["name"] for c in D.check(self.src, wipe, o, ramp) if not c["ok"]], soft)
        # the noise itself tiles, whatever the front's width and however many cells (a hard cut read off the CELLS
        # steps as hard inside as at its seam: the check reads the pattern)
        for kw in ({"soft": 0}, {"soft": 0.3}, {"cells": 64, "cell": 128, "soft": 0}, {"density": 0}):
            o = opts(**kw)
            src = made.skin(o["cell"])
            field = D.pattern_field(src[..., 3], o)
            self.assertTrue(named(D.check(src, D.cells_of(src, o, field), o, field))["tiles"]["ok"], kw)
        plain = np.ones((128, 128, 4))
        o = opts(cells=64, cell=128, soft=0)
        field = D.pattern_field(plain[..., 3], o)
        self.assertEqual([c["name"] for c in D.check(plain, D.cells_of(plain, o, field), o, field) if not c["ok"]], [])
        # a texture covered at ONE edge only is not one that wraps: it is not asked to tile
        left = self.src.copy()
        left[:, -20:, 3] = 0
        self.assertNotIn("tiles", named(D.check(left, D.cells_of(left, self.o), self.o)))
        for dot, ok in ((4, True), (3, False), (16, True), (5, False)):
            o = opts(pattern="dither", soft=0, dot=dot)
            self.assertEqual("tiles" not in self.failed(D.cells_of(self.src, o), o), ok, dot)
        # a texture that does not wrap is not asked to tile
        lone = self.src.copy()
        lone[:, :20, 3] = 0
        lone[:, -20:, 3] = 0
        self.assertNotIn("tiles", named(D.check(lone, D.cells_of(lone, self.o), self.o)))

    def test_a_sheet_the_packer_would_refuse_is_refused_here(self):
        speck = np.zeros((256, 256, 4))
        speck[..., :3] = 1.0
        speck[100:124, 100:124, 3] = 1.0          # 0.9 % of the cell: sixteen cells each change next to nothing
        o = opts(soft=0)
        got = named(D.check(speck, D.cells_of(speck, o), o))
        self.assertFalse(got["packs"]["ok"])
        self.assertTrue(all(got[k]["ok"] for k in ("source", "whole", "clears", "monotone", "steps")))
        few = opts(soft=0, cells=4)
        self.assertTrue(named(D.check(speck, D.cells_of(speck, few), few))["packs"]["ok"])   # fewer cells: each changes enough
        import fxfinish
        for frames, ok in ((D.cells_of(speck, o), False), (self.cells, True)):
            change = min(float(np.abs(frames[k + 1][..., 3] - frames[k][..., 3]).mean()) for k in range(len(frames) - 1))
            self.assertEqual(change > 0.0008, ok)                                           # (the packer's own limit)
        self.assertGreater(D.PACK, 0.0008)

    def test_options_are_refused_in_plain_words(self):
        for bad in ({"cells": 12}, {"cell": 300}, {"cells": 64, "cell": 256}, {"pattern": "swirl"}, {"soft": 2}, {"curve": 9},
                    {"edge": 0.1}, {"edge": 0.1, "edge_color": [1, 2]}, {"edge_color": "red"}, {"scale": 0}, {"soft": float("nan")}):
            with self.assertRaises(ValueError, msg=str(bad)):
                D.checked(bad)
        with self.assertRaises(ValueError):
            D.checked("not a table")
        self.assertEqual(D.checked({"edge": 0.1, "edge_color": [255, 128, 0]})["edge_color"], [1.0, 128 / 255.0, 0.0])
        self.assertEqual(D.checked({"edge_color": [1, 0.5, 0]})["edge_color"], [1.0, 0.5, 0.0])
        self.assertEqual(D.checked({"tint": [255, 128, 0]})["tint"], [1.0, 128 / 255.0, 0.0])
        with self.assertRaises(ValueError):
            D.checked({"tint": [1, 2]})


class TestCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kit_dissolve_")
        self.built, self.specs, self.frames, self.look = (os.path.join(self.tmp, d) for d in ("built", "specs", "frames", "look"))
        made.save(made.skin(), os.path.join(self.built, "skin.png"))
        self.dirs = ["--textures-dir", self.built, "--specs-dir", self.specs, "--frames-dir", self.frames, "--look-dir", self.look]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_tool(self, *argv, dirs=True):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = D.main(list(argv) + (self.dirs if dirs else []))
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1, lines)  # one JSON line, never a traceback
        return code, json.loads(lines[0])

    def test_a_sheet_is_written_with_what_it_came_from(self):
        code, v = self.run_tool("skin_dz", "--from", "skin", "--edge", "0.06", "--edge-color", "255,240,200")
        self.assertEqual(code, 0, v)
        spec = json.load(open(os.path.join(self.specs, "skin_dz.json"), encoding="utf-8"))
        self.assertEqual((spec["engine"], spec["recipe"], spec["from"], spec["frames"], spec["grid"], spec["cell"]), ("fx", "dissolve", "skin", 16, 4, 256))
        self.assertEqual(spec["dissolve"]["edge_color"], [255, 240, 200])
        self.assertEqual(spec["post"], {"alpha": "coverage", "tonemap": False, "border": 0})
        meta = json.load(open(os.path.join(self.frames, "skin_dz", "frames.json"), encoding="utf-8"))
        self.assertEqual(meta["frames"], 16)
        self.assertEqual(meta["source"], D.source_id(os.path.join(self.built, "skin.png")))
        self.assertEqual(len([f for f in os.listdir(os.path.join(self.frames, "skin_dz")) if f.endswith(".npy")]), 16)
        self.assertTrue(os.path.isfile(os.path.join(self.look, "skin_dz_strip.png")))
        self.assertIn('"over": [0.6, 1]', v["flipbook"])
        self.assertIn('"surface": 1', v["summary"])
        # the spec bakes the same sheet again
        o = D.checked(dict(spec["dissolve"], cells=spec["frames"], cell=spec["cell"]))
        first = np.load(os.path.join(self.frames, "skin_dz", "008.npy")).astype(np.float64)
        again = D.premultiplied(D.cells_of(D.load_source("skin", self.built, self.specs, 256)[0], o)[8])
        self.assertLess(float(np.abs(first - again).max()), 2e-3)

    def test_a_sheet_that_fails_leaves_nothing_and_keeps_an_older_one(self):
        code, v = self.run_tool("skin_dz", "--from", "skin", "--soft", "1")
        self.assertEqual(code, 1)
        self.assertIn("an even fade", v["summary"])
        self.assertIn("nothing written", v["summary"])
        self.assertFalse(os.path.exists(os.path.join(self.specs, "skin_dz.json")))
        self.assertFalse(os.path.exists(os.path.join(self.frames, "skin_dz")))
        self.run_tool("skin_dz", "--from", "skin")
        before = open(os.path.join(self.specs, "skin_dz.json"), encoding="utf-8").read()
        code, v = self.run_tool("skin_dz", "--from", "skin", "--soft", "1")
        self.assertEqual(code, 1)
        self.assertIn("stays as it was", v["summary"])
        self.assertEqual(open(os.path.join(self.specs, "skin_dz.json"), encoding="utf-8").read(), before)

    def test_a_sheets_first_cell_is_the_source(self):
        sheet = np.zeros((512, 512, 4))
        sheet[:256, :256] = made.skin()
        sheet[256:, 256:, 3] = 1.0
        made.save(sheet, os.path.join(self.built, "four.png"))
        os.makedirs(self.specs, exist_ok=True)
        json.dump({"engine": "fx", "recipe": "import", "grid": 2}, open(os.path.join(self.specs, "four.json"), "w"))
        src, _ = D.load_source("four", self.built, self.specs, 256)
        want = np.asarray(Image.open(os.path.join(self.built, "skin.png")).convert("RGBA"), dtype=np.float64) / 255.0
        self.assertLess(float(np.abs(src - want).max()), 0.02)

    def test_the_command_never_throws(self):
        for argv in ([], ["--from", "skin"], ["Bad-Key", "--from", "skin"], ["x_dz"], ["x_dz", "--from"], ["x_dz", "--from", "skin", "--cells", "twelve"],
                     ["x_dz", "--from", "skin", "--bogus", "1"], ["x_dz", "--from", "x_dz"], ["x_dz", "--from", "not_built"], ["x_dz", "--from", "../skin"],
                     ["x_dz", "--from", "skin", "--edge-color", "red"], ["x_dz", "--from", "skin", "--cells", "12"]):
            code, v = self.run_tool(*argv)
            self.assertEqual((code, v["status"]), (1, "fail"), argv)
        open(os.path.join(self.built, "broken.png"), "w").write("not a picture")
        code, v = self.run_tool("x_dz", "--from", "broken")
        self.assertEqual((code, v["status"]), (1, "fail"))

    def test_the_build_step(self):
        self.run_tool("skin_dz", "--from", "skin")
        step = ["--specs", self.specs, "--out", self.frames, "--textures-dir", self.built]
        code, v = self.run_tool(*step, dirs=False)
        self.assertEqual((code, v["baked"]), (0, []))
        first = np.load(os.path.join(self.frames, "skin_dz", "004.npy"))
        shutil.rmtree(os.path.join(self.frames, "skin_dz"))
        code, v = self.run_tool(*step, dirs=False)
        self.assertEqual((code, len(v["baked"])), (0, 1))
        self.assertTrue(np.array_equal(first, np.load(os.path.join(self.frames, "skin_dz", "004.npy"))))
        made.save(made.skin(shift=0.4), os.path.join(self.built, "skin.png"))  # the source texture changed
        code, v = self.run_tool(*step, dirs=False)
        self.assertEqual((code, len(v["baked"])), (0, 1))
        self.assertFalse(np.array_equal(first, np.load(os.path.join(self.frames, "skin_dz", "004.npy"))))
        # a spec whose block is broken, and one whose source is gone, are said - and do not stop the others
        spec = json.load(open(os.path.join(self.specs, "skin_dz.json"), encoding="utf-8"))
        json.dump(dict(spec, dissolve={"pattern": "swirl"}), open(os.path.join(self.specs, "bad_dz.json"), "w"))
        json.dump(dict(spec, **{"from": "gone"}), open(os.path.join(self.specs, "lost_dz.json"), "w"))  # (a key, and nothing built under it)
        json.dump(dict(spec, dissolve="x"), open(os.path.join(self.specs, "worse_dz.json"), "w"))
        os.remove(os.path.join(self.frames, "skin_dz", "frames.json"))
        code, v = self.run_tool(*step, dirs=False)
        self.assertEqual(code, 1)
        self.assertIn("bad_dz", v["summary"])
        self.assertIn("lost_dz", v["summary"])
        self.assertIn("worse_dz", v["summary"])
        self.assertEqual(len(v["baked"]), 1)

    def source_as_fx(self, shift=0.0):
        """the source as an fx texture the packer packs: its spec and one rendered frame"""
        os.makedirs(self.specs, exist_ok=True)
        json.dump({"engine": "fx", "recipe": "import", "frames": 1, "grid": 1, "cell": 256, "post": {"alpha": "coverage", "tonemap": False, "border": 0}},
                  open(os.path.join(self.specs, "skin.json"), "w"))
        os.makedirs(os.path.join(self.frames, "skin"), exist_ok=True)
        np.save(os.path.join(self.frames, "skin", "000.npy"), D.premultiplied(made.skin(shift=shift)).astype(np.float16))

    def pack(self, *more):
        """the packer as `kit vfx` runs it: the general pass, derived sheets left to their own step"""
        import subprocess
        finish = os.path.join(HERE, "..", "..", "vfx", "fxfinish.py")
        r = subprocess.run([sys.executable, finish, "--specs", self.specs, "--frames", self.frames, "--out", self.built,
                            "--registry", os.path.join(self.tmp, "_textures.json"), *more], capture_output=True, text=True, check=False)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_it_is_baked_from_the_source_of_this_run_and_packed_by_its_own_step(self):
        """kit vfx: fx renders -> the packer (derived sheets skipped) -> this step (bake what is stale, pack them)"""
        finish = os.path.join(HERE, "..", "..", "vfx", "fxfinish.py")
        json.dump({"_help": "test"}, open(os.path.join(self.tmp, "_textures.json"), "w"))
        self.source_as_fx()
        self.assertEqual(self.pack("--skip-derived")["status"], "pass")
        self.run_tool("skin_dz", "--from", "skin")
        step = ["--specs", self.specs, "--out", self.frames, "--textures-dir", self.built, "--registry", os.path.join(self.tmp, "_textures.json"), "--pack", finish]
        code, v = self.run_tool(*step, dirs=False)
        self.assertEqual((code, v["baked"], v["packed"]), (0, [], ["skin_dz"]), v)
        self.assertTrue(os.path.isfile(os.path.join(self.built, "skin_dz.png")))
        reg = json.load(open(os.path.join(self.tmp, "_textures.json"), encoding="utf-8"))
        self.assertEqual((reg["skin_dz"]["grid"], reg["skin"]["grid"]), (4, 1))               # both registered, neither dropped
        first = np.asarray(Image.open(os.path.join(self.built, "skin_dz.png")).convert("RGBA"), dtype=np.float64)[:256, :256, 3] / 255.0
        # the source is rendered again: ONE run later the dissolve shows the new source (it used to lag a run behind)
        self.source_as_fx(shift=0.4)
        self.assertEqual(self.pack("--skip-derived")["status"], "pass")
        code, v = self.run_tool(*step, dirs=False)
        self.assertEqual((code, len(v["baked"]), v["packed"]), (0, 1, ["skin_dz"]), v)
        now = np.asarray(Image.open(os.path.join(self.built, "skin_dz.png")).convert("RGBA"), dtype=np.float64)[:256, :256, 3] / 255.0
        self.assertLess(float(np.abs(now - made.skin(shift=0.4)[..., 3]).max()), 0.03)
        self.assertGreater(float(np.abs(now - first).mean()), 0.05)
        # a clean checkout: no frames of the dissolve at all - the general pass does not stumble on it, the step bakes it
        shutil.rmtree(os.path.join(self.frames, "skin_dz"))
        os.remove(os.path.join(self.built, "skin_dz.png"))
        general = self.pack("--skip-derived")
        self.assertEqual(general["status"], "pass", general)
        self.assertNotIn("skin_dz", [t["name"] for t in general["textures"]])
        self.assertEqual(self.pack()["status"], "fail")                                       # (without the flag it would)
        code, v = self.run_tool(*step, dirs=False)
        self.assertEqual((code, len(v["baked"]), v["packed"]), (0, 1, ["skin_dz"]), v)
        self.assertTrue(os.path.isfile(os.path.join(self.built, "skin_dz.png")))
        # the step's own pack leaves the run's review sheet alone
        review = os.path.join(self.built, "_fx_review.png")
        stamp = os.path.getmtime(review)
        self.run_tool(*step, "--force", dirs=False)
        self.assertEqual(os.path.getmtime(review), stamp)

    def test_a_source_is_an_fx_texture_or_plain(self):
        os.makedirs(self.specs, exist_ok=True)
        json.dump({"engine": "blender", "recipe": "volume"}, open(os.path.join(self.specs, "skin.json"), "w"))
        code, v = self.run_tool("skin_dz", "--from", "skin")
        self.assertEqual(code, 1)
        self.assertIn("is not an fx texture", v["summary"])
        os.remove(os.path.join(self.specs, "skin.json"))
        self.run_tool("skin_dz", "--from", "skin")
        made.save(made.skin(), os.path.join(self.built, "skin_dz.png"))
        code, v = self.run_tool("again_dz", "--from", "skin_dz")
        self.assertEqual(code, 1)
        self.assertIn("is itself a dissolve sheet", v["summary"])
        # a spec whose "from" is a path is said by the build step, and reaches no file
        spec = json.load(open(os.path.join(self.specs, "skin_dz.json"), encoding="utf-8"))
        json.dump(dict(spec, **{"from": "../built/skin"}), open(os.path.join(self.specs, "odd_dz.json"), "w"))
        json.dump(dict(spec, **{"from": ""}), open(os.path.join(self.specs, "none_dz.json"), "w"))
        code, v = self.run_tool("--specs", self.specs, "--out", self.frames, "--textures-dir", self.built, dirs=False)
        self.assertEqual(code, 1)
        self.assertIn('odd_dz: its spec\'s "from" is not a texture key', v["summary"])
        self.assertIn('none_dz: its spec\'s "from" is not a texture key', v["summary"])

    def test_a_plain_sheet_may_carry_its_colour(self):
        code, v = self.run_tool("gold_dz", "--from", "plain", "--tint", "255,200,90", "--soft", "0")
        self.assertEqual(code, 0, v)
        cell = np.load(os.path.join(self.frames, "gold_dz", "000.npy")).astype(np.float64)
        self.assertTrue(np.allclose(cell[128, 128, :3], [1.0, 200 / 255.0, 90 / 255.0], atol=0.01))
        self.assertEqual(json.load(open(os.path.join(self.specs, "gold_dz.json"), encoding="utf-8"))["dissolve"]["tint"], [255, 200, 90])
        code, v = self.run_tool("--specs", self.specs, "--out", self.frames, "--textures-dir", self.built, "--force", dirs=False)
        self.assertEqual(code, 0, v)
        again = np.load(os.path.join(self.frames, "gold_dz", "000.npy")).astype(np.float64)
        self.assertTrue(np.allclose(again[128, 128, :3], [1.0, 200 / 255.0, 90 / 255.0], atol=0.01))   # the spec bakes the colour again
        code, v = self.run_tool("skin_dz", "--from", "skin", "--tint", "255,0,0")
        self.assertEqual(code, 1)
        self.assertIn("colours a `plain` sheet", v["summary"])

    def test_a_plain_sheet_is_always_current(self):
        code, v = self.run_tool("plain_dz", "--from", "plain", "--soft", "0")
        self.assertEqual(code, 0, v)
        code, v = self.run_tool("--specs", self.specs, "--out", self.frames, "--textures-dir", self.built, dirs=False)
        self.assertEqual((code, v["baked"]), (0, []))


class TestParity(unittest.TestCase):
    """the game's sheetFrame and the player's are held to one rule by running both texts"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kit_dissolve_parity_")
        self.keep = (made.STAGE, made.PLAYER)

    def tearDown(self):
        made.STAGE, made.PLAYER = self.keep
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_by_hand(self):
        self.assertEqual([made.by_hand("OneShot", (0.6, 1.0), 24, u, 0, 16, 0) for u in (0, 0.59, 0.6, 0.8, 0.999, 1)], [0, 0, 0, 8, 15, 15])
        self.assertEqual([made.by_hand("OneShot", None, 24, u, 0, 16, 0) for u in (0, 0.5, 1)], [0, 8, 15])
        self.assertEqual(made.by_hand("Loop", None, 10, 0.5, 1.25, 16, 3), 15)

    def test_the_two_agree_as_they_are(self):
        problems, n = made.parity(os.path.join(self.tmp, "run"))
        self.assertEqual(problems, [])
        self.assertGreater(n, 4000)

    def test_a_player_that_drifts_is_caught(self):
        text = open(made.PLAYER, encoding="utf-8").read()
        for old, new in (("if (Array.isArray(fb.over)) {", "if (false) {"),                       # the window ignored
                         ("Math.min(Math.floor(uu * frames), frames - 1)", "Math.min(Math.round(uu * frames), frames - 1)"),  # rounding, not flooring
                         ("+ start) % frames", ") % frames")):                                     # the start cell dropped
            self.assertEqual(text.count(old), 1, old)
            made.PLAYER = os.path.join(self.tmp, "player.js")
            open(made.PLAYER, "w", encoding="utf-8").write(text.replace(old, new))
            problems, _ = made.parity(os.path.join(self.tmp, "run"))
            self.assertTrue(any("the player (player.js) shows another cell" in p for p in problems), (old, problems))
            made.PLAYER = self.keep[1]

    def test_a_game_that_drifts_is_caught(self):
        text = open(made.STAGE, encoding="utf-8").read()
        old = "uu = math.clamp((u - u0) / math.max(u1 - u0, 1e-4), 0, 1)"
        self.assertEqual(text.count(old), 1)
        made.STAGE = os.path.join(self.tmp, "VfxStage.luau")
        open(made.STAGE, "w", encoding="utf-8").write(text.replace(old, "uu = math.clamp(u - u0, 0, 1)"))
        problems, _ = made.parity(os.path.join(self.tmp, "run"))
        self.assertTrue(any("the game (VfxStage.luau) shows another cell" in p for p in problems), problems)

    def test_a_file_without_the_function_is_said(self):
        made.STAGE = os.path.join(self.tmp, "empty.luau")
        open(made.STAGE, "w").write("-- nothing here\n")
        with self.assertRaises(ValueError):
            made.parity(os.path.join(self.tmp, "run"))


if __name__ == "__main__":
    unittest.main()
