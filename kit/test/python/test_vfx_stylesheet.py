"""kit/vfx/stylesheet.py - the style sheet: every beat's look, ours beside the scene's (the VFX studio-route plan, V1)
- on a small made project: a preset, its chart with two beats, a "scene" clip and "our" recording (the made clips of
kit/selftest/vfx/dailies/clips.py), in a temp folder the tool is run from.

What is proven: one pair a beat at the asked size (two frames a picture, read at full size); the id is of the
preset, the set and the chart's plan - so a preset edited after the owner's yes has another id and the sheet on this
machine is STALE; a sheet whose beat never lights up is not one he can approve; the shortfalls are kit vfx
keyread's own rule, said in plain words."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "selftest", "vfx", "stylesheet"))
import keyread  # noqa: E402
import madeproject  # noqa: E402
import stylesheet  # noqa: E402

clips, project = madeproject.clips, madeproject.project

FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def run(argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = stylesheet.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


class TestWords(unittest.TestCase):
    def test_the_shortfalls_are_the_key_reads_own_rule_in_plain_words(self):
        scene = {"coverage": 0.40, "light": 0.20, "layers": 5, "detail": 24.0, "pieces": 18}
        ours = {"coverage": 0.36, "light": 0.10, "layers": 3, "detail": 15.0, "pieces": 12}
        said = stylesheet.gaps(scene, ours)
        self.assertEqual(len(said), len(keyread.compare(scene, ours)))      # the same gaps, never one more or less
        self.assertIn("ours is 10 % white-hot, the scene's frame is 20 % white-hot", said)
        self.assertIn("ours has 3 colour bands, the scene's frame 5", said)
        self.assertFalse(any("covers" in s for s in said))                  # 0.36 of 0.40 holds: not said
        self.assertEqual(stylesheet.gaps(scene, scene), [])
        self.assertEqual(stylesheet.gaps(None, ours), [])                   # no read on one side: nothing claimed
        rng = np.random.default_rng(7)                                      # ... and the same count for ANY two reads
        for _ in range(300):
            a, b = ({"coverage": float(rng.random()), "light": float(rng.random()), "layers": int(rng.integers(1, 6)),
                     "detail": float(rng.random() * 30), "pieces": int(rng.integers(0, 30))} for _ in range(2))
            self.assertEqual(len(stylesheet.gaps(a, b)), len(keyread.compare(a, b)), (a, b))

    def test_the_plan_text_is_the_chart_tools(self):
        chart = {"duration": 3.4, "beats": [{"t": 0, "len": 0.3, "hold": 0, "key": False},
                                             {"t": 0.3, "len": 0.4, "hold": 0.12, "key": True}]}
        self.assertEqual(stylesheet.plan_key(chart), "3.40|0.00,0.30,0.00,0;0.30,0.40,0.12,1")
        sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
        import chart as chart_tool
        self.assertEqual(stylesheet.plan_key(chart), chart_tool.plan_key(chart))

    def test_the_main_colours_are_the_effects_not_the_nights(self):
        frame = clips.frame(60)
        colours = stylesheet.swatches(frame, clips.HUE)
        self.assertTrue(colours)
        self.assertAlmostEqual(sum(share for _, share in colours), 1.0, places=2)
        rgb, share = colours[0]
        self.assertGreater(rgb[0], rgb[2] + 100)                            # the fire's orange leads; the night is not in it
        self.assertEqual(stylesheet.swatches(clips.frame(0), clips.HUE), [])


@unittest.skipUnless(FFMPEG, "ffmpeg / ffprobe not on PATH")
class TestSheet(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kit_stylesheet_test_")
        self.here = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.here)
        shutil.rmtree(self.root, ignore_errors=True)

    def test_every_beat_is_a_pair_and_the_id_follows_the_preset(self):
        project(self.root, clips.our_frames())
        code, got = run(["fx", "--tile", "640"])
        self.assertEqual((code, got["status"]), (0, "pass"), got)
        self.assertTrue(got["summary"].endswith("LOOK: build/vfx/stylesheet/fx/"), got["summary"])
        self.assertEqual([b["file"] for b in got["beats"]], ["beat0.png", "beat1.png"])
        from PIL import Image
        pair = Image.open(os.path.join("build", "vfx", "stylesheet", "fx", "beat0.png"))
        self.assertTrue(1280 <= pair.width <= 1568, pair.width)            # two 640 px frames: a reader gets them 1:1
        first = got["beats"][0]
        self.assertGreater(first["ours"]["read"]["coverage"], 0.05)         # our frame at OUR peak: the big disc
        self.assertGreater(first["scene"]["read"]["coverage"], 0.05)
        self.assertTrue(first["scene"]["colours"] and first["ours"]["colours"])
        # --check: there is a sheet, it is of this preset and this recording, and it names the pictures drawn
        code, check = run(["fx", "--check"])
        self.assertEqual((check["exists"], check["stale"], check["problems"], check["id"]), (True, False, [], got["id"]))
        self.assertTrue(check["drawn"] and len(check["drawn"]) == 12)
        self.assertEqual(check["files"], ["beat0.png", "beat1.png"])       # the files that hash is of, in order
        # the SAME preset recorded again with another look (a texture changed, the preset's file did not): the sheet
        # here is stale; drawn again its id is the same and its PICTURES are not - his yes was for the pictures
        brighter = clips.our_frames().copy()
        brighter[brighter[..., 0] > 200] = (255, 235, 90)
        clips.write(os.path.join("build", "vfx", "booth", "fx_play_hero.mp4"), brighter, 30)
        self.assertTrue(run(["fx", "--check"])[1]["stale"])
        self.assertEqual(run(["fx", "--check"])[1]["why"], "the effect was recorded again since it was drawn")
        code, again = run(["fx", "--tile", "640"])
        self.assertEqual((code, again["id"]), (0, got["id"]))
        redrawn = run(["fx", "--check"])[1]
        self.assertEqual((redrawn["exists"], redrawn["stale"], redrawn["id"]), (True, False, got["id"]))
        self.assertNotEqual(redrawn["drawn"], check["drawn"])
        # the preset is edited after the sheet: another id, and the sheet here is of the old one
        path = os.path.join("assets", "effects", "fx.json")
        preset = json.load(open(path))
        preset["layers"].append({"kind": "sprite", "name": "new_flame"})
        json.dump(preset, open(path, "w"))
        code, after = run(["fx", "--check"])
        self.assertNotEqual(after["id"], got["id"])
        self.assertTrue(after["stale"])
        # a re-timed chart is another sheet too
        json.dump(preset, open(path, "w"))
        chart_path = os.path.join("assets", "effects", "refs_measured", "fire.chart.json")
        chart = json.load(open(chart_path))
        chart["beats"][0]["len"] = 0.3
        json.dump(chart, open(chart_path, "w"))
        self.assertNotEqual(run(["fx", "--check"])[1]["id"], after["id"])

    def test_a_beat_that_never_lights_up_is_not_a_sheet_he_can_approve(self):
        project(self.root, clips.blank_frames())
        code, got = run(["fx"])
        self.assertEqual((code, got["status"]), (1, "fail"))
        self.assertIn("ours never lights up", got["summary"])
        code, check = run(["fx", "--check"])
        self.assertTrue(check["exists"] and check["problems"])              # drawn, and it says why it cannot be approved

    def test_check_reads_the_pictures_themselves_not_what_the_record_says_of_them(self):
        project(self.root, clips.our_frames())
        self.assertEqual(run(["fx"])[0], 0)
        first = run(["fx", "--check"])[1]
        look = os.path.join("build", "vfx", "stylesheet", "fx")
        # a pair picture replaced after the drawing: his yes is asked for what is on disk NOW, and that is not a sheet
        shutil.copyfile(os.path.join(look, "beat0.png"), os.path.join(look, "beat1.png"))
        swapped = run(["fx", "--check"])[1]
        self.assertTrue(swapped["exists"] and swapped["stale"])
        self.assertNotEqual(swapped["drawn"], first["drawn"])
        self.assertIn("not the ones its record was written for", swapped["why"])
        self.assertEqual(swapped["problems"], [])                           # (the sheet's own problems are another thing)
        os.remove(os.path.join(look, "beat1.png"))                          # a pair that is gone: no sheet at all
        gone = run(["fx", "--check"])[1]
        self.assertEqual((gone["exists"], gone["drawn"]), (False, None))
        self.assertEqual(run(["fx"])[0], 0)                                 # drawn again: a sheet, with its pictures' hash
        again = run(["fx", "--check"])[1]
        self.assertEqual((again["exists"], again["stale"], again["drawn"]), (True, False, first["drawn"]))

    def test_a_drawing_that_fails_half_way_leaves_no_sheet_to_approve(self):
        project(self.root, clips.our_frames())
        self.assertEqual(run(["fx"])[0], 0)
        self.assertTrue(run(["fx", "--check"])[1]["exists"])
        real = stylesheet.pair
        stylesheet.pair = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("the drawing failed"))
        try:
            with self.assertRaises(RuntimeError):
                run(["fx"])
        finally:
            stylesheet.pair = real
        check = run(["fx", "--check"])[1]
        self.assertFalse(check["exists"])                                   # not the OLD sheet over a half-made folder
        self.assertIsNone(check["drawn"])

    def test_a_recording_that_ends_before_a_beat_says_so_not_that_it_never_lit(self):
        project(self.root, clips.our_frames())
        path = os.path.join("assets", "effects", "refs_measured", "fire.chart.json")
        chart = json.load(open(path))
        chart["beats"][1]["t"] = 5.0                                        # a beat the 1.3 s recording never reaches
        json.dump(chart, open(path, "w"))
        code, got = run(["fx"])
        self.assertEqual(code, 1)
        self.assertIn("the recording holds under 3 frames of its stretch", got["summary"])
        self.assertNotIn("never lights up", got["summary"])

    def test_a_flag_with_no_value_is_refused_not_given_the_next_flag(self):
        # `--view` with nothing after it once took the --effects the kit appends for its value: the sheet was then
        # drawn from another folder (a review, 2026-11-12)
        project(self.root, clips.our_frames())
        code, got = run(["fx", "--view", "--effects", os.path.join("assets", "effects")])
        self.assertEqual(code, 1)
        self.assertIn("--view needs a value", got["summary"])
        self.assertEqual(run(["fx", "--view"])[0], 1)
        code, got = run(["fx", "--nope", "1"])
        self.assertEqual(code, 1)
        self.assertIn("--nope is not one of", got["summary"])
        code, check = run(["fx", "--check", "--tile"])                      # asked as a check: answered as one
        self.assertEqual((code, check["exists"], check["problems"]), (0, False, ["--tile needs a value"]))
        self.assertFalse(os.path.exists(os.path.join("build", "vfx", "stylesheet", "fx")))   # nothing was drawn

    def test_no_recording_no_preset_no_sheet(self):
        project(self.root, clips.our_frames())
        os.remove(os.path.join("build", "vfx", "booth", "fx_play_hero.mp4"))
        code, got = run(["fx"])
        self.assertEqual(code, 1)
        self.assertIn("no recording", got["summary"])
        code, check = run(["fx", "--check"])
        self.assertEqual((check["exists"], check["stale"]), (False, False))
        self.assertTrue(check["id"])                                        # the id needs no sheet: the lock can read it anywhere
        code, none = run(["nothing_here", "--check"])
        self.assertEqual((none["exists"], none["id"]), (False, None))


if __name__ == "__main__":
    unittest.main()
