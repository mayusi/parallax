"""kit ui gauge: a .gauge.json + a plate's anchors -> a screen spec whose live cells sit over the wells, scaled"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("kit_ui_gauge", os.path.join(HERE, "..", "..", "ui", "gauge.py"))
gauge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gauge)


class TestGauge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "art", "t"))
        with open(os.path.join(self.tmp, "art", "t", "plate.anchors.json"), "w", encoding="utf-8") as fh:
            json.dump({"schema": 1, "size": [2000, 500], "rows": [
                {"row": 0, "cells": [{"x": 100 + i * 200, "y": 100, "w": 160, "h": 80} for i in range(3)], "lean_px": 20},
                {"row": 1, "cells": [{"x": 100 + i * 200, "y": 300, "w": 160, "h": 80} for i in range(2)], "lean_px": 20}]}, fh)
        with open(os.path.join(self.tmp, "G.gauge.json"), "w", encoding="utf-8") as fh:
            json.dump({"identity": "t", "plate": "plate", "plate_width": 1000, "at": [50, 20], "fills": [2, 2], "fill": "hp",
                       "fill_empty": None, "emblem": {"art": "emblem", "size": 200, "at": [-40, -30]},
                       "pips": {"art": "pip", "count": 4, "lit": 1, "size": [30, 40], "gap": 5, "at": [10, 200]},
                       "name": {"text": "SWIFT", "size": 40, "at": [100, -10]}}, fh)

    def run_gauge(self):
        buf = io.StringIO()
        sys.argv = ["gauge.py", "G", "--specs", self.tmp]
        with contextlib.redirect_stdout(buf):
            code = gauge.main()
        return code, json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_cells_sit_over_the_wells_at_the_screen_scale(self):
        code, r = self.run_gauge()
        self.assertEqual(code, 0, r)
        with open(os.path.join(self.tmp, "G.json"), encoding="utf-8") as fh:
            screen = json.load(fh)
        plate = screen["root"]["children"][0]
        self.assertEqual(plate["size"], [1000, 250])  # 2000x500 at width 1000
        kids = {k["name"]: k for k in plate["children"]}
        self.assertEqual(kids["Art"]["image"], "art:t/plate")
        row0 = kids["Row0"]["children"]
        self.assertEqual(len(row0), 2)  # 2 of 3 lit, empties bare (fill_empty null)
        self.assertEqual(row0[0]["pos"], [90, 70])  # 100,100 at half scale, placed by its centre (50+40, 50+20)
        self.assertEqual(row0[0]["anchor"], "center")
        self.assertEqual(row0[0]["size"], [80, 40])
        self.assertEqual(row0[0]["color"], "hp")
        self.assertEqual(row0[1]["pos"], [190, 70])
        self.assertNotIn("rotation", row0[0])  # a level bar: no tilt
        self.assertEqual(len(kids["Row1"]["children"]), 2)
        self.assertEqual(kids["Emblem"]["image"], "art:t/emblem")
        pips = kids["Pips"]["children"]
        self.assertEqual(len(pips), 4)
        self.assertEqual(pips[0]["imageAlpha"], 0.0)  # lit
        self.assertGreater(pips[1]["imageAlpha"], 0.3)  # unlit, dimmed and tinted
        self.assertEqual(pips[1]["imageColor"], "line2")
        self.assertEqual(kids["Name"]["text"], "SWIFT")
        self.assertIn("gauge.json", screen["generated_from"])

    def test_the_measured_crest_sets_the_scale_and_a_nudge_moves_a_traced_piece(self):
        # a traced layout: the plate's box in the picture is 500 px wide, the crest's 125 px; the real crest is 220 px
        art = os.path.join(self.tmp, "art", "t")
        for piece, box in (("plate", [10, 10, 500, 125]), ("emblem", [0, 0, 125, 125]), ("name", [60, -5, 100, 20])):
            with open(os.path.join(art, f"{piece}.trace.json"), "w", encoding="utf-8") as fh:
                json.dump({"schema": 1, "box": box, "scale": 4}, fh)
        with open(os.path.join(self.tmp, "G.gauge.json"), encoding="utf-8") as fh:
            g = json.load(fh)
        g.update({"from_trace": True, "crest_width": 220})
        g.pop("plate_width")
        g["name"] = {"art": "name", "text": "SWIFT", "nudge": [22, -4]}
        with open(os.path.join(self.tmp, "G.gauge.json"), "w", encoding="utf-8") as fh:
            json.dump(g, fh)
        code, r = self.run_gauge()
        self.assertEqual(code, 0, r)
        with open(os.path.join(self.tmp, "G.json"), encoding="utf-8") as fh:
            plate = json.load(fh)["root"]["children"][0]
        self.assertEqual(plate["size"], [880, 220])  # 500 * 220 / 125 wide; 2000x500 anchors keep the aspect
        kids = {k["name"]: k for k in plate["children"]}
        self.assertEqual(kids["Emblem"]["size"], [220, 220])
        self.assertEqual(kids["Emblem"]["pos"], [-18, -18])  # (0 - 10) * 1.76
        self.assertEqual(kids["Name"]["pos"], [88 + 22, -26 - 4])  # traced place + the nudge
        self.assertEqual(kids["Name"]["size"], [176, 35])

    def test_unlit_pips_can_be_their_own_art(self):
        with open(os.path.join(self.tmp, "G.gauge.json"), encoding="utf-8") as fh:
            g = json.load(fh)
        g["pips"] = {"art_lit": "pearl_lit", "art_unlit": "pearl_unlit", "count": 3, "lit": 1, "size": [20, 20], "gap": 4, "at": [10, 200]}
        with open(os.path.join(self.tmp, "G.gauge.json"), "w", encoding="utf-8") as fh:
            json.dump(g, fh)
        code, r = self.run_gauge()
        self.assertEqual(code, 0, r)
        with open(os.path.join(self.tmp, "G.json"), encoding="utf-8") as fh:
            plate = json.load(fh)["root"]["children"][0]
        pips = {k["name"]: k for k in plate["children"]}["Pips"]["children"]
        self.assertEqual([p["image"] for p in pips], ["art:t/pearl_lit", "art:t/pearl_unlit", "art:t/pearl_unlit"])
        self.assertEqual(pips[1]["imageAlpha"], 0.0)  # the dark pearl is drawn as painted, not ghosted
        self.assertIsNone(pips[1].get("imageColor"))

    def test_rendered_gem_cells_cover_the_wells(self):
        art = os.path.join(self.tmp, "art", "t")
        for nm in ("cell_lit", "cell_unlit"):
            with open(os.path.join(art, f"{nm}.anchors.json"), "w", encoding="utf-8") as fh:
                json.dump({"schema": 1, "size": [400, 200], "gem": {"x": 100, "y": 50, "w": 200, "h": 100}}, fh)
        with open(os.path.join(self.tmp, "G.gauge.json"), encoding="utf-8") as fh:
            g = json.load(fh)
        g["cells"] = {"art_lit": "cell_lit", "art_unlit": "cell_unlit"}
        with open(os.path.join(self.tmp, "G.gauge.json"), "w", encoding="utf-8") as fh:
            json.dump(g, fh)
        code, r = self.run_gauge()
        self.assertEqual(code, 0, r)
        with open(os.path.join(self.tmp, "G.json"), encoding="utf-8") as fh:
            plate = json.load(fh)["root"]["children"][0]
        row0 = {k["name"]: k for k in plate["children"]}["Row0"]["children"]
        self.assertEqual(row0[0]["image"], "art:t/cell_lit")
        self.assertEqual(row0[2]["image"], "art:t/cell_unlit")  # 2 of 3 lit; the third is the unlit picture
        # the well is 80x40 at (50, 50); the slab is half the picture -> the picture is 160x80, centred on the well (90, 70)
        self.assertEqual(row0[0]["size"], [160, 80])
        self.assertEqual(row0[0]["pos"], [90, 70])
        self.assertEqual(row0[0]["anchor"], "center")

    def test_cells_follow_a_bowed_bar(self):
        with open(os.path.join(self.tmp, "art", "t", "plate.anchors.json"), encoding="utf-8") as fh:
            an = json.load(fh)
        for i, c in enumerate(an["rows"][0]["cells"]):
            c["rot"] = [-6.5, 0.0, 6.5][i]   # rising, level, falling
        with open(os.path.join(self.tmp, "art", "t", "plate.anchors.json"), "w", encoding="utf-8") as fh:
            json.dump(an, fh)
        code, r = self.run_gauge()
        self.assertEqual(code, 0, r)
        with open(os.path.join(self.tmp, "G.json"), encoding="utf-8") as fh:
            plate = json.load(fh)["root"]["children"][0]
        row0 = {k["name"]: k for k in plate["children"]}["Row0"]["children"]
        self.assertEqual(row0[0]["rotation"], -6.5)
        self.assertNotIn("rotation", row0[1])

    def test_missing_anchors_is_a_clear_fail(self):
        os.remove(os.path.join(self.tmp, "art", "t", "plate.anchors.json"))
        code, r = self.run_gauge()
        self.assertEqual(code, 1)
        self.assertIn("kit ui render t/plate", r["next_action"])


if __name__ == "__main__":
    unittest.main()
