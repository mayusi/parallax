"""The VFX route's tools (mission 02-vfx) on synthetic inputs with known answers: the breakdown's cut detector,
the chart's beat-sheet parser + plan, the bar's phases and the direction of its edits."""

import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vfx"))
import bar  # noqa: E402
import breakdown  # noqa: E402
import chart  # noqa: E402


class TestBreakdownCuts(unittest.TestCase):
    def test_a_hard_cut_is_found_and_a_slow_fade_is_not(self):
        with tempfile.TemporaryDirectory() as d:
            names = []
            for i in range(30):  # 1 s at 30 fps: a blue shot slowly brightening, a hard cut to orange at frame 20
                c = (20, 30, 60 + 3 * i) if i < 20 else (230, 120, 20)
                n = f"{i:05d}.png"
                Image.new("RGB", (64, 36), c).save(os.path.join(d, n))
                names.append(n)
            cuts = breakdown.find_cuts(d, names, 30.0, 0.35)
        self.assertEqual(len(cuts), 1)
        self.assertAlmostEqual(cuts[0][0], 20 / 30, places=2)


class TestChartBeats(unittest.TestCase):
    SHEET = "\n".join([
        "# x - scene beat sheet",
        "| Beat | Scene time | What is on screen (vision) | Shape | Colour | Size vs the body | Motion / hold | Text |",
        "|---|---|---|---|---|---|---|---|",
        "| 0 gather | 0-2 s | light gathers inward | ring | gold | small | slow in |  |",
        "| 1 key strike | 2-2.5 s | a blinding line | streak | white | huge | hold on impact |  |",
        "| 2 fade | 2.5-4 s |  |  |  |  |  |  |",  # an empty skeleton row: not a beat yet
        "| 3 smoke | 2.5-4 s | grey smoke drifts | cloud | grey | big | slow |  |",
        "",
    ])

    def test_only_filled_rows_with_a_scene_time_are_beats(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(self.SHEET)
        try:
            beats = chart.parse_beats(f.name)
        finally:
            os.remove(f.name)
        self.assertEqual([b["label"] for b in beats], ["0 gather", "1 key strike", "3 smoke"])
        self.assertEqual((beats[1]["t0"], beats[1]["t1"]), (2.0, 2.5))

    def test_the_plan_scales_scene_time_onto_the_effect_clock_with_holds_and_slow_mo(self):
        beats = [{"label": "a", "t0": 0, "t1": 2, "cells": {"Motion / hold": "slow in"}},
                 {"label": "b", "t0": 2, "t1": 2.5, "cells": {"Motion / hold": "hold on impact"}},
                 {"label": "c", "t0": 2.5, "t1": 4, "cells": {"Motion / hold": ""}}]
        P = chart.plan(beats, 2.0, 1)
        self.assertEqual([r["t"] for r in P["beats"]], [0.0, 1.0, 1.25])
        self.assertEqual(P["beats"][0]["slow"], 2.0)
        self.assertGreater(P["beats"][1]["hold"], 0)
        self.assertTrue(P["beats"][1]["key"])


class TestBarPhases(unittest.TestCase):
    @staticmethod
    def entry(share, lum=200.0, hue_bin=9):
        h = [0] * bar.HUE_BINS
        h[hue_bin] = 10
        return {"share": share, "lum": lum, "sat": 0.5, "hue": h, "extent": [share, share], "rgb": [150, 60, 220]}

    def test_anticipation_climax_tail_from_the_effect_curve(self):
        curve = [0.02] * 12 + [0.1, 0.5, 0.9, 0.95, 0.8, 0.6] + [0.1] * 6  # 1 s build, a 0.5 s blast, a tail
        res = bar.phases([self.entry(s) for s in curve])
        ph = res["phases"]
        self.assertGreater(ph["anticipation"]["seconds"], ph["climax"]["seconds"])
        self.assertGreater(ph["climax"]["share"], ph["tail"]["share"])
        self.assertAlmostEqual(sum(p["seconds"] for p in ph.values()), len(curve) / bar.FPS, places=1)

    def test_edits_point_the_right_way(self):
        mine = {"seconds": 1.0, "share": 0.05, "lum": 250.0, "sat": 0.2, "hue": [0] * 9 + [1] + [0, 0], "extent": [0.2, 0.2], "rgb": [255, 255, 255]}
        theirs = {"seconds": 1.0, "share": 0.5, "lum": 190.0, "sat": 0.6, "hue": [0] * 9 + [1] + [0, 0], "extent": [0.9, 0.8], "rgb": [150, 60, 220]}
        gaps = bar.diffs("climax", mine, theirs, 4.0, 4.0)
        top = gaps[0]
        self.assertIn("fills 5% of the frame", top[1])  # the biggest gap: it draws a tenth of what the bar draws
        self.assertTrue(top[2].startswith("grow"))
        lum = next(g for g in gaps if "luma" in g[1])
        self.assertIn("darker", lum[2])  # brighter than the bar -> darker, more saturated body
        sat = next(g for g in gaps if "saturation" in g[1])
        self.assertIn("pre-saturate", sat[2])

    def test_no_score_anywhere(self):
        mine = self.entry(0.3)
        mine["seconds"] = 1.0
        gaps = bar.diffs("tail", mine, dict(mine), 2.0, 2.0)
        for _, words, edit in gaps:
            self.assertNotIn("/100", words + edit)
            self.assertNotIn("score", (words + edit).lower())


if __name__ == "__main__":
    unittest.main()


import importlib.util  # noqa: E402
import json  # noqa: E402

# loaded under its own name: kit/blender/judge.py is imported as `judge` by the 3D tests in the same process (one
# pytest run of the whole folder gave these tests the 3D judge - the owner's V3 list, section 6.2, kit hygiene)
_spec = importlib.util.spec_from_file_location(
    "kit_vfx_judge", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "vfx", "judge.py"))
judge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(judge)


class TestVerifier(unittest.TestCase):
    """kit vfx judge is a VERIFIER: one difference + one edit per beat, and a number anywhere is refused"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.packet = os.path.join(self.dir, "packet")
        os.makedirs(self.packet)
        json.dump({"name": "fx", "sheets": {}, "beats": [{"beat": "build", "t": 0.5}, {"beat": "hit", "t": 1.0}]},
                  open(os.path.join(self.packet, "packet.json"), "w"))
        self.effects = os.path.join(self.dir, "effects")

    def answer(self, data):
        p = os.path.join(self.dir, "answer.json")
        json.dump(data, open(p, "w"))
        return judge.record(["--name", "fx", "--packet", self.packet, "--verdict", p, "--effects", self.effects])

    def beats(self):
        return [{"beat": "build", "difference": "the gather is a flat disc, the scene's light streams inward",
                 "edit": "streak sprites aimed at the blade"},
                {"beat": "hit", "difference": "the blast is white, the scene's is violet", "edit": "saturate the core"}]

    def test_a_full_answer_is_kept(self):
        self.assertEqual(self.answer({"verifier": "t@test", "beats": self.beats(), "first": "hit"}), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.effects, "judge", "fx.json")))

    def test_earlier_rounds_are_kept(self):
        self.answer({"verifier": "r1@test", "beats": self.beats(), "first": "hit"})
        self.answer({"verifier": "r2@test", "beats": self.beats(), "first": "build"})
        rec = json.load(open(os.path.join(self.effects, "judge", "fx.json")))
        self.assertEqual(rec["verifier"], "r2@test")
        self.assertEqual([h["verifier"] for h in rec["history"]], ["r1@test"])

    def test_a_score_is_refused(self):
        self.assertEqual(self.answer({"verifier": "t@test", "beats": self.beats(), "overall": 72}), 1)
        smuggled = self.beats()
        smuggled[1]["difference"] += " - I'd say 6/10"
        self.assertEqual(self.answer({"verifier": "t@test", "beats": smuggled}), 1)

    def test_every_beat_needs_a_difference_and_an_edit(self):
        self.assertEqual(self.answer({"verifier": "t@test", "beats": self.beats()[:1]}), 1)


class TestVerifierPacket(unittest.TestCase):
    """v2: the packet holds PLAYER recordings only, plus a detail crop per beat zoomed onto the effect"""

    def setUp(self):
        from PIL import Image, ImageDraw
        self.dir = tempfile.mkdtemp()
        self.effects, self.booth = os.path.join(self.dir, "effects"), os.path.join(self.dir, "booth")
        os.makedirs(self.effects)
        os.makedirs(os.path.join(self.booth, "fx_play"))
        json.dump({"duration": 2, "layers": [], "hitstop": [{"at": 0.5}]}, open(os.path.join(self.effects, "fx.json"), "w"))
        self.Image, self.Draw = Image, ImageDraw

    def run_packet(self):
        out = os.path.join(self.dir, "packet")
        rc = judge.packet(["--name", "fx", "--out", out, "--booth", self.booth, "--effects", self.effects, "--refs", self.dir])
        return rc, out

    def test_a_studio_booth_sheet_is_not_evidence(self):
        self.Image.new("RGB", (64, 36)).save(os.path.join(self.booth, "fx_hero.png"))
        self.assertEqual(self.run_packet()[0], 1)

    def test_player_sheet_and_a_detail_crop_on_the_effect(self):
        self.Image.new("RGB", (64, 36)).save(os.path.join(self.booth, "fx_play_hero.png"))
        for i in range(1, 49):  # 2 s at 24 fps: a bright orange blob at the right of a dark frame
            im = self.Image.new("RGB", (1280, 720), (12, 10, 14))
            self.Draw.Draw(im).ellipse((900, 300, 1060, 420), fill=(255, 150, 30))
            im.save(os.path.join(self.booth, "fx_play", f"hero_{i:03d}.jpg"))
        rc, out = self.run_packet()
        self.assertEqual(rc, 0)
        files = os.listdir(out)
        self.assertIn("sheet_player_fx_play_hero.png", files)
        self.assertIn("detail_beat00.png", files)
        crop = self.Image.open(os.path.join(out, "detail_beat00.png"))
        self.assertEqual(max(crop.size), 768)
        self.assertLess(crop.width / crop.height, 1.7)  # zoomed onto the blob (a 5x floor), not the 16:9 frame (1.78)
        self.assertIn("detail_beat00.png", open(os.path.join(out, "PROMPT.md"), encoding="utf-8").read())


import evolve  # noqa: E402


class TestEvolve(unittest.TestCase):
    def test_overlays_compose_from_the_picked_base(self):
        base = {"time": 0.8, "mute": ["a*"]}
        o = evolve.compose(base, {"time": 1.25, "scale": 1.25, "saturate": 0.3, "mute": ["b*"]})
        self.assertAlmostEqual(o["time"], 1.0)
        self.assertEqual(o["scale"], 1.25)
        self.assertEqual(o["mute"], ["a*", "b*"])
        self.assertEqual(base, {"time": 0.8, "mute": ["a*"]})  # the base itself is never changed

    def test_layer_groups_by_name_and_never_a_muted_one(self):
        s = "sprite"
        preset = {"layers": [{"name": "ring_1", "kind": s}, {"name": "ring_2", "kind": s}, {"name": "ring_3", "kind": s},
                             {"name": "spark_1", "kind": s}, {"name": "core", "kind": "light"},
                             {"name": "arc_1", "kind": "mesh"}, {"name": "arc_2", "kind": "mesh"}, {"name": "arc_3", "kind": "mesh"},
                             {"name": "arc_4", "kind": "mesh"}]}
        self.assertEqual(evolve.groups(preset, []), ["ring", "spark", "core"])  # the mesh shape is never a mix option
        self.assertEqual(evolve.groups(preset, ["ring*"]), ["spark", "core"])


import cost  # noqa: E402


class TestCost(unittest.TestCase):
    def test_peak_particles_meshes_and_luau_time(self):
        P = {"duration": 2, "layers": [
            {"name": "burst", "kind": "sprite", "at": 0.5, "count": 100, "lifetime": [0.2, 0.4]},
            {"name": "stream", "kind": "sprite", "at": 0, "rate": 200, "for": 1, "lifetime": 0.5},
            {"name": "flame", "kind": "mesh", "at": 0, "life": 2, "shape": "flame", "wobble": [0.1, 5, 6]},
            {"name": "light", "kind": "light", "at": 0, "life": 1}]}
        c = cost.cost(P)
        self.assertEqual(c["peak_particles"], 200)  # the stream's 100 alive + the burst's 100 at t = 0.5
        self.assertEqual(c["wobbled_verts_per_frame"], 41 * 17)  # a flame: 40 x 16 segments
        self.assertAlmostEqual(c["luau_ms_per_frame"], round(697 * 0.36 / 1000, 2))
        self.assertEqual(c["lights_peak"], 1)
