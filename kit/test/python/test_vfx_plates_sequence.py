"""kit/vfx/plates.py (B4 impact plates) + kit/vfx/sequence.py (V5 sequences) - LIMITATIONS_FIXES_V4 §3.4 step 3.
What is proven: each plate kind bakes a 1024 x 1024 sheet whose cells are what its checks say (the clear middle, the
cover, hard ink, a kanji written on stroke by stroke); a plate that covers the hit, a soft plate and a frozen one are
caught; a hostile spec is refused; the sequence tool checks a file by the GAME's rules (a broken V5 shape is named),
refuses a sequence whose plate was never baked, and draws the timeline.
Run: python -m pytest kit/test/python/test_vfx_plates_sequence.py -q"""

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
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import plates as P  # noqa: E402
import sequence as S  # noqa: E402


def failed(cks):
    return {c["name"]: c["value"] for c in cks if not c["ok"]}


def run(tool, argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = tool.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


class Plates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_each_kind_bakes_and_passes(self):
        for kind in P.KINDS:
            spec = P.checked({"kind": kind, "frames": 4, "rate": 2})
            cells, rgba, cks = P.bake(spec)
            self.assertFalse(failed(cks), kind)
            self.assertEqual(rgba.shape, (1024, 1024, 4))
            self.assertEqual(len(cells), 4)
            self.assertTrue((rgba[..., :3] == 255).all())            # white ink: the game tints it

    def test_the_middle_stays_clear(self):
        spec = P.checked({"kind": "lines", "frames": 4, "focus": [0.4, 0.6]})
        cells, _, _ = P.bake(spec)
        n = spec["cell"]
        fx, fy = int(0.4 * n), int(0.6 * n)
        for c in cells:
            self.assertLess(float(c[fy - 10:fy + 10, fx - 10:fx + 10].max()), 0.5)
            self.assertGreater(float((c > 0.5).mean()), 0.06)

    def test_covered_soft_and_frozen_plates_caught(self):
        spec = P.checked({"kind": "halftone", "frames": 4})
        cells, _, _ = P.bake(spec)
        covered = [np.ones_like(c) for c in cells]
        self.assertIn("clear", failed(P.checks(spec, covered)))
        self.assertIn("cover", failed(P.checks(spec, covered)))
        import cv2
        soft = [cv2.GaussianBlur(c, (0, 0), 6.0) for c in cells]
        self.assertIn("ink", failed(P.checks(spec, soft)))
        frozen = [cells[0]] * 4
        self.assertIn("moves", failed(P.checks(spec, frozen)))

    def test_kanji_written_on(self):
        spec = P.checked({"kind": "kanji", "frames": 16, "char": "大"})
        cells, _, cks = P.bake(spec)
        self.assertFalse(failed(cks))
        ink = [float((c > 0.5).mean()) for c in cells]
        self.assertLess(ink[0], 0.5 * ink[-1])
        backwards = cells[::-1]
        self.assertIn("written", failed(P.checks(spec, backwards)))

    def test_drawn_burst(self):
        # B4's "drawn" kind (LIMITATIONS_FIXES_V4 13.3.4: "halftone / kanji / drawn impact sheets"): it bakes and passes
        # every check, its middle stays clear, every cell is the same burst drawn again (boil) with brush strokes that
        # press and release (taper)
        spec = P.checked({"kind": "drawn", "frames": 16, "seed": 3})
        cells, rgba, cks = P.bake(spec)
        self.assertFalse(failed(cks), cks)
        self.assertEqual({c["name"] for c in cks} >= {"boil", "taper", "clear", "cover", "moves", "ink"}, True)
        self.assertEqual(rgba.shape, (1024, 1024, 4))
        ink = [float((c > 0.5).mean()) for c in cells]
        self.assertGreater(ink[-1], ink[0])                       # it grows out from the hit
        one = P.checked({"kind": "drawn", "frames": 1})
        self.assertFalse(failed(P.bake(one)[2]))

    def test_drawn_held_copy_new_pictures_and_ruled_lines_caught(self):
        import cv2
        spec = P.checked({"kind": "drawn", "frames": 4, "seed": 2})
        cells, _, _ = P.bake(spec)
        held = [cells[0]] * 4                                     # one drawing held: not drawn again
        self.assertIn("boil", failed(P.checks(spec, held)))
        others = [P.bake(P.checked({"kind": "drawn", "frames": 4, "seed": s}))[0][0] for s in (11, 12, 13, 14)]
        moved = [np.roll(c, (37 * i, 53 * i), axis=(0, 1)) for i, c in enumerate(others)]
        self.assertIn("boil", failed(P.checks(spec, moved)))      # four unrelated pictures: not one drawing
        n = spec["cell"]
        ruled = []
        for k in range(4):                                        # one-width spokes round a clear middle: a vector
            img = np.zeros((n, n), np.uint8)
            for i in range(24):
                a = i / 24 * 2 * np.pi + k * 0.01
                p0 = (int(n / 2 + 0.2 * n * np.cos(a)), int(n / 2 + 0.2 * n * np.sin(a)))
                p1 = (int(n / 2 + 0.48 * n * np.cos(a)), int(n / 2 + 0.48 * n * np.sin(a)))
                cv2.line(img, p0, p1, 255, 6)
            ruled.append(img.astype(np.float32) / 255.0)
        self.assertIn("taper", failed(P.checks(spec, ruled)))

    def test_hostile_specs_refused(self):
        for bad in ({"kind": "fire"}, {"kind": "lines", "frames": 9}, {"kind": "lines", "rate": 0},
                    {"kind": "lines", "focus": [0.0, 0.5]}, {"kind": "lines", "seed": True},
                    {"kind": "kanji", "char": "龍"}, None):
            with self.assertRaises(ValueError):
                P.checked(bad)

    def test_cli_writes_sheet_and_spec_keeping_an_uploaded_id(self):
        argv = ["t_plate", "--kind", "lines", "--frames", "4", "--out", self.tmp, "--specs-dir", self.tmp, "--look-dir", self.tmp]
        code, line = run(P, argv)
        self.assertEqual(code, 0, line["summary"])
        self.assertEqual(Image.open(os.path.join(self.tmp, "t_plate.png")).size, (1024, 1024))
        path = os.path.join(self.tmp, "t_plate.plate.json")
        spec = json.load(open(path, encoding="utf-8"))
        self.assertEqual((spec["texture"], spec["grid"], spec["id"]), ("t_plate", [2, 2], ""))
        spec["id"] = "rbxassetid://123"                             # the owner uploaded it
        json.dump(spec, open(path, "w", encoding="utf-8"))
        self.assertEqual(run(P, argv)[0], 0)                          # baked again
        self.assertEqual(json.load(open(path, encoding="utf-8"))["id"], "rbxassetid://123")


class Sequence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(ROOT)                                   # the rules are run as lune run kit/vfx/sequence.luau

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def seq(self, name, mutate=None):
        s = S.template(name)
        s["beats"][1]["impact_plate"]["plate"] = "p1"
        if mutate:
            mutate(s)
        with open(os.path.join(self.tmp, f"{name}.seq.json"), "w", encoding="utf-8") as fh:
            json.dump(s, fh)
        with open(os.path.join(self.tmp, "p1.plate.json"), "w", encoding="utf-8") as fh:
            json.dump({"frames": 4}, fh)

    def args(self, name):
        return [name, "--dir", self.tmp, "--plates-dir", self.tmp, "--look-dir", self.tmp]

    def test_template_passes_and_draws(self):
        self.seq("good")
        code, line = run(S, self.args("good"))
        self.assertEqual(code, 0, line["summary"])
        self.assertIn("impact at frame 36", line["summary"])
        img = Image.open(os.path.join(self.tmp, "good_timeline.png"))
        self.assertGreater(img.size[0], 500)

    def test_broken_shape_named_by_the_game_rules(self):
        self.seq("noplate", lambda s: s["beats"][1].pop("impact_plate"))
        code, line = run(S, self.args("noplate"))
        self.assertEqual(code, 1)
        self.assertIn("IMPACT beat", line["summary"])
        self.seq("onecut", lambda s: [s["beats"].pop(), s["beats"].pop()])
        code, line = run(S, self.args("onecut"))
        self.assertEqual(code, 1)
        self.assertIn("multi-cut reveal", line["summary"])

    def test_unbaked_plate_refused(self):
        self.seq("ghost", lambda s: s["beats"][1]["impact_plate"].update(plate="never_baked"))
        code, line = run(S, self.args("ghost"))
        self.assertEqual(code, 1)
        self.assertIn("never_baked", line["summary"])

    def test_new_never_overwrites(self):
        code, _ = run(S, ["fresh", "--new", "--dir", self.tmp])
        self.assertEqual(code, 0)
        code, line = run(S, ["fresh", "--new", "--dir", self.tmp])
        self.assertEqual(code, 1)
        self.assertIn("exists", line["summary"])


if __name__ == "__main__":
    unittest.main()
