"""Trim sheets and a kit of modules through REAL builds (kit/selftest/blender/build_trim_sheet.py, build_trim_wall.py
and its off twin; the 3D methods audit, S2): the sheet's maps repeat along their length and its manifest names its
bands; a wall laid into it bakes nothing, carries the sheet's own files and runs its faces along the bands; a module
off its grid fails and a part in a band far too low warns."""

import json
import os
import subprocess
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import cad_check  # noqa: E402
import rbx_trim as T  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join("build", "_test_trim_build")


def build(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    v = json.loads(line)
    laid = next((x for x in r.stdout.splitlines() if x.startswith("TRIM ")), None)
    v["laid"] = json.loads(laid[5:]) if laid else None                   # (the wall fixtures: the built mesh's UVs)
    return v


def manifest(asset):
    with open(os.path.join(ROOT, OUT, "models", f"{asset}.manifest.json"), encoding="utf-8") as fh:
        return json.load(fh)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheet = build("build_trim_sheet.py")                         # first: the walls take their bands from it
        cls.wall, cls.off = build("build_trim_wall.py"), build("build_trim_wall_off.py")
        cls.sm, cls.wm = manifest("_selftest_trim_sheet"), manifest("_selftest_trim_wall")

    def test_the_sheet_names_its_bands_at_one_scale_and_its_maps_repeat(self):
        self.assertEqual(self.sheet["status"], "pass", self.sheet["summary"][:300])
        ts = self.sm["trim_sheet"]
        self.assertEqual((ts["studs"], ts["px"]), (8.0, 512))
        self.assertEqual(sorted(ts["bands"]), ["edge", "planks", "rivets", "stone"])
        for name, height in (("planks", 4.0), ("stone", 1.5), ("edge", 1.0), ("rivets", 0.5)):
            b = ts["bands"][name]
            self.assertAlmostEqual(b["v1"] - b["v0"], height / 8.0, places=4)        # every band at the same scale
        self.assertIn("trim sheet: 4 bands over 8 studs, repeats along its length", self.sheet["summary"])
        # the bake did not repeat, so the sheet was faded - ALL its maps, and the build says so
        self.assertTrue(self.sheet["facts"]["trim_sheet"]["faded"])
        fade = next(c for c in self.sheet["groups"]["main"]["checks"] if c["name"] == "trim_fade")
        self.assertEqual((fade["ok"], fade["severity"]), (False, "warn"))
        for key in ("color", "rough", "metal", "normal"):
            self.assertTrue(self.sm["groups"]["main"]["textures"][key].endswith("_trim.png"), key)
        from PIL import Image  # noqa: PLC0415

        tex = self.sm["groups"]["main"]["textures"]
        self.assertTrue(tex["color"].endswith("_color_trim.png"))                    # (the shipped map: made to repeat)
        made = np.asarray(Image.open(os.path.join(ROOT, tex["color"])).convert("RGB"), float)[::-1] / 255.0
        self.assertEqual(T.tile_step(made)["share"], 0.0)
        raw = np.asarray(Image.open(os.path.join(ROOT, tex["color"].replace("_trim.png", ".png"))).convert("RGB"),
                         float)[::-1] / 255.0
        self.assertGreater(T.tile_step(raw)["step"], T.tile_step(made)["step"])      # the bake's own did not
        # each band's strip of the map holds that band's finish: iron is grey, planks brown (red over blue)
        px = lambda b: made[int((b["v0"] + b["v1"]) / 2 * 512), 256]                 # noqa: E731
        planks, edge = px(ts["bands"]["planks"]), px(ts["bands"]["edge"])
        self.assertGreater(planks[0] - planks[2], 0.08)
        self.assertLess(abs(edge[0] - edge[2]), 0.05)

    def test_a_wall_laid_into_the_sheet_bakes_nothing_and_carries_the_sheets_own_files(self):
        self.assertEqual(self.wall["status"], "pass", self.wall["summary"][:300])
        g = self.wm["groups"]["main"]
        self.assertEqual(g["textures"], self.sm["groups"]["main"]["textures"])       # the SAME files: one upload
        self.assertEqual(g["trim"]["sheet"], "_selftest_trim_sheet")
        self.assertEqual(g["trim"]["parts"], {"Cap": "edge", "Panel": "planks"})
        self.assertEqual(g["trim"]["px_per_stud"], 64.0)                             # the sheet's sharpness, not its own
        self.assertEqual(self.wall["bakes"]["baked"], 0)
        names = {c["name"] for c in self.wall["groups"]["main"]["checks"]}
        self.assertIn("trim_fit", names)
        self.assertFalse(names & {"uv", "uv_overlap", "seams", "uv_coverage"})       # a baked layout's checks: not its
        self.assertIn("trim: main on _selftest_trim_sheet (64 px a stud)", self.wall["summary"])

    def test_every_face_of_the_built_wall_lies_in_its_parts_band_the_right_way_up(self):
        # the built mesh's own UVs (the fixture prints them): the review found tests that read none
        bands = self.sm["trim_sheet"]["bands"]
        of = {"Panel": ("planks", 0.0, 3.5), "Cap": ("edge", 3.5, 4.0)}              # the band, the part's y range
        self.assertGreaterEqual(len(self.wall["laid"]), 12)                          # two boxes' faces at least
        sides = 0
        for row in self.wall["laid"]:
            name, y0, y1 = of[row["part"].split("~")[0]]
            b = bands[name]
            for (x, y, _z), (u, v) in zip(row["pts"], row["uv"]):
                self.assertGreaterEqual(v, b["v0"] - 1e-3, row)                      # inside ITS band: never another's
                self.assertLessEqual(v, b["v1"] + 1e-3, row)
                if abs(row["n"][1]) < 0.5:                                           # a side that stands up
                    # the same way up on the front, the back and the ends: the part's foot at the band's foot
                    want = b["v0"] + (y - y0) / (y1 - y0) * (b["v1"] - b["v0"])
                    self.assertAlmostEqual(v, want, places=3, msg=row)
                if abs(row["n"][0]) < 0.5:                                           # a side the band runs along
                    self.assertAlmostEqual(u, x / 8.0, places=3, msg=row)            # one run: from the part's own end
            sides += abs(row["n"][2]) > 0.5
        self.assertGreaterEqual(sides, 4)                                            # both broad sides of both parts

    def test_the_wall_records_which_build_of_the_sheet_it_was_laid_on(self):
        self.assertEqual(self.wm["groups"]["main"]["trim"]["sheet_build"], self.sm["build_id"])
        self.assertTrue(self.sm["build_id"])

    def test_a_module_knows_its_cells_and_one_off_the_grid_fails_by_name(self):
        self.assertEqual(self.wm["module"], {"grid": [4.0, 4.0, 0.0], "cells": [2, 1, 0]})
        self.assertIn("module: 2 x 1 cells", self.wall["summary"])
        self.assertEqual(self.off["status"], "fail")
        said = [c for c in self.off["design"] if c["name"] == "module_grid"]
        self.assertEqual([c["severity"] for c in said], ["error"])
        self.assertIn("7.5 studs along x is 1.88 cells of 4", said[0]["value"])
        self.assertFalse(any(c["name"] == "module_grid" for c in self.wall["design"]))

    def test_a_part_in_a_band_far_too_low_warns_by_the_parts_and_the_bands_name(self):
        fit = next(c for c in self.off["groups"]["main"]["checks"] if c["name"] == "trim_fit")
        self.assertEqual((fit["ok"], fit["severity"]), (False, "warn"))
        self.assertIn("Panel: its side facing", fit["value"][0])
        self.assertIn('3.5 studs across its band "rivets" (0.5 studs tall): the finish is pulled tall 7.0x',
                      fit["value"][0])
        ok = next(c for c in self.wall["groups"]["main"]["checks"] if c["name"] == "trim_fit")
        self.assertTrue(ok["ok"])


if __name__ == "__main__":
    unittest.main()
