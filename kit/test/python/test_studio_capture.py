"""kit/tools/studio_capture.py: the shared Studio capture bridge (card 4s96) - the parts that need no Studio. The colour
signals (found on synthetic window pictures, told apart, the same colours the Studio side draws), the cut to the 3D
view and the crop fractions, when a window is maximised for a 1600 px view, the moving walk's timing (a UI arrival:
the read closest to each moment, timed from the frame the go colour left), the fingerprints both sides compute (a
place older than the repo is named), and the run's scripts (the job inside them, the harness asked for by version,
nothing that calls out)."""

import json
import os
import re
import sys
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import studio_capture as sc  # noqa: E402

N = sc.NEXTS


def view(colour, size=(640, 360)):
    return Image.new("RGB", size, colour)


def scene(n, size=(640, 360)):
    im = Image.new("RGB", size, (20 + 9 * n, 24, 40))
    im.paste(Image.new("RGB", (size[0] // 3, size[1] // 3), (200, 150 - 20 * n, 60 + 30 * n)), (20 * n + 20, 60))
    return im


def window(colour, at=(10, 170), size=(1407, 701)):
    """a Studio window picture with its 3D view covered by `colour`"""
    win = Image.new("RGB", (1936, 1096), (36, 38, 44))
    win.paste(Image.new("RGB", size, colour), at)
    return win


class Signals(unittest.TestCase):
    def test_the_start_colour_finds_the_3d_view_in_the_window(self):
        self.assertEqual(sc.flash_box(window(sc.START), sc.START), (10, 170, 1417, 871))
        self.assertEqual(sc.flash_box(window(sc.START, (0, 0), (1700, 900)), sc.START), (0, 0, 1700, 900))
        self.assertIsNone(sc.flash_box(window((90, 60, 40)), sc.START))

    def test_every_signal_is_told_apart(self):
        self.assertEqual(sc.signal(view(sc.START)), ("start", None))
        self.assertEqual(sc.signal(view(sc.END)), ("end", None))
        self.assertEqual([sc.signal(view(c)) for c in N], [("next", i) for i in range(6)])
        self.assertIsNone(sc.signal(scene(2)))

    def test_the_studio_side_draws_the_same_colours(self):
        with open(os.path.join(ROOT, "kit", "studio", "capture_bridge.luau"), encoding="utf-8") as fh:
            src = fh.read()

        def rgb(name):
            m = re.search(rf"Bridge\.{name} = Color3\.fromRGB\((\d+), (\d+), (\d+)\)", src)
            return tuple(int(x) for x in m.groups())

        self.assertEqual(rgb("START"), sc.START)
        self.assertEqual(rgb("END"), sc.END)
        nexts = re.search(r"Bridge\.NEXTS = \{(.*?)\n\}", src, re.S).group(1)
        self.assertEqual([tuple(int(x) for x in t) for t in re.findall(r"fromRGB\((\d+), (\d+), (\d+)\)", nexts)],
                         list(N))


class Cut(unittest.TestCase):
    def test_crop_fractions_cut_the_sides_of_the_view(self):
        self.assertEqual(sc.crop_box((1600, 900), (0, 0, 0, 0)), (0, 0, 1600, 900))
        self.assertEqual(sc.crop_box((1600, 900), (0.03, 0.06, 0.04, 0)), (48, 54, 1536, 900))
        # a silly fraction never leaves an empty picture
        left, top, right, bottom = sc.crop_box((100, 100), (0.9, 0.9, 0.9, 0.9))
        self.assertTrue(right > left and bottom > top)

    def test_crop_text(self):
        self.assertEqual(sc.parse_crop("0.03,0.06,0.04,0"), (0.03, 0.06, 0.04, 0.0))
        self.assertEqual(sc.parse_crop("0.1"), (0.1, 0.0, 0.0, 0.0))
        self.assertEqual(sc.parse_crop("x,0.2"), (0.0, 0.2, 0.0, 0.0))

    def test_a_window_is_maximised_only_when_that_gives_a_wider_view(self):
        self.assertTrue(sc.needs_maximise(1400, 2560, False))  # (a 1400 px window on a wide screen)
        self.assertFalse(sc.needs_maximise(1400, 2560, True))  # (maximised already)
        self.assertFalse(sc.needs_maximise(2100, 2560, False))  # (already room for 1600 px beside the panels)
        self.assertFalse(sc.needs_maximise(1400, 1400, False))  # (the screen is no wider: nothing to gain)


class MovingWalk(unittest.TestCase):
    def test_each_moment_keeps_the_read_closest_to_it_timed_from_the_go(self):
        clip = sc.Clip([0, 0.15, 0.4])
        clip.feed(view(sc.START), 0.0)
        clip.feed(view(N[0]), 0.5)
        clip.feed(view(N[0]), 0.9)  # the go colour's last read
        clip.feed(scene(0), 0.94)  # the first read without it: t0 = 0.92, +- 0.02
        reads = {0.94: 0, 1.0: 1, 1.06: 2, 1.12: 3, 1.18: 4, 1.3: 5, 1.36: 6}
        for at, n in reads.items():
            clip.feed(scene(n), at)
        got = clip.frames()
        self.assertEqual([i for i, _m, _r, _img in got], [0, 1, 2])
        self.assertAlmostEqual(clip.t0, 0.92)
        self.assertAlmostEqual(got[0][2], 0.02)  # moment 0 <- the first read (0.02 s after the go left)
        self.assertAlmostEqual(got[1][2], 0.14)  # 0.15 <- the read at 1.06
        self.assertAlmostEqual(got[2][2], 0.38)  # 0.4 <- the read at 1.30 (0.02 off; the one at 1.36 is 0.04 off)
        self.assertAlmostEqual(clip.worst(), 0.02 + 0.02)
        self.assertFalse(clip.over)
        clip.feed(view(sc.END), 1.5)
        self.assertTrue(clip.over)

    def test_nothing_is_kept_before_the_start_or_the_go(self):
        clip = sc.Clip([0, 1])
        clip.feed(scene(1), 0.0)  # (before the start: another session's view, never kept)
        clip.feed(view(sc.START), 0.1)
        clip.feed(scene(2), 0.2)  # (after the start, before the go: the script is getting ready)
        self.assertEqual(clip.frames(), [])
        self.assertIsNone(clip.t0)

    def test_the_walk_ends_by_itself_past_the_last_moment(self):
        clip = sc.Clip([0, 0.2])
        for at, img in ((0.0, view(sc.START)), (0.1, view(N[0])), (0.2, scene(0)), (0.5, scene(1)), (0.9, scene(2))):
            clip.feed(img, at)
        self.assertTrue(clip.over)


class HeldWalk(unittest.TestCase):
    def test_numbered_pictures_through_the_shared_walk(self):
        walk, saved = sc.Walk([str(k) for k in range(1, 9)]), []
        a, b = scene(1), scene(2)
        for f in (view(sc.START), view(N[0]), a, a, view(N[1]), b, b, view(N[2]), view(sc.END)):
            saved += walk.feed(f)
        self.assertEqual([(s, ok) for s, _img, ok in saved], [("1", True), ("2", True)])
        self.assertTrue(walk.over)


class Fingerprints(unittest.TestCase):
    def test_fnv1a_known_values_and_carriage_returns_left_out(self):
        self.assertEqual(sc.fingerprint(""), "811c9dc5")
        self.assertEqual(sc.fingerprint("a"), "e40c292c")
        self.assertEqual(sc.fingerprint("foobar"), "bf9cf968")
        self.assertEqual(sc.fingerprint("a\r\nb"), sc.fingerprint("a\nb"))
        self.assertNotEqual(sc.fingerprint("a\nb"), sc.fingerprint("a\nc"))

    def test_a_tree_print_counts_every_node_and_ignores_order_and_the_roots_name(self):
        model = {"ClassName": "ScreenGui", "Name": "X", "Children": [
            {"ClassName": "Frame", "Name": "Hud", "Children": [{"ClassName": "TextLabel", "Name": "Score"}]},
            {"ClassName": "ImageLabel", "Name": "Plate"}]}
        p = sc.tree_print(model)
        self.assertTrue(p.startswith("4:"))
        swapped = dict(model, Name="Other", Children=list(reversed(model["Children"])))
        self.assertEqual(sc.tree_print(swapped), p)
        renamed = json.loads(json.dumps(model))
        renamed["Children"][0]["Children"][0]["Name"] = "Combo"
        self.assertNotEqual(sc.tree_print(renamed), p)


class Scripts(unittest.TestCase):
    def test_long_strings_hold_any_text(self):
        for text in ("plain", "a]]b", "x]=]y]]", "\nstarts with a newline", "ends ]"):
            lit = sc.long_string(text)
            eq = re.match(r"\[(=*)\[\n", lit).group(1)
            self.assertTrue(lit.endswith("]" + eq + "]"))
            self.assertEqual(lit[len(eq) + 3:-(len(eq) + 2)], text)
            self.assertNotIn("]" + eq + "]", text)

    def test_the_kit_closure_follows_relative_requires(self):
        got = sc.kit_closure(["VfxStage"], os.path.join(ROOT, "src", "kit"))
        self.assertIn("VfxStage", got)
        self.assertIn("VfxMesh", got)  # (VfxStage requires "./VfxMesh")
        self.assertIn("VfxArc", got)  # (VfxMesh requires "./VfxArc": transitively)

    def test_a_run_carries_its_job_and_asks_for_its_harness_by_version(self):
        if not os.path.isfile(os.path.join(ROOT, "src", "ui", "RushHud.model.json")):
            self.skipTest("the author's src/ui/RushHud.model.json is not shipped with the kit")
        with tempfile.TemporaryDirectory() as tmp:
            job, paths = sc.write_snippets("ui_playtest", {"screen": "RushHud", "bar": "Hud.Health"},
                                           os.path.join(tmp, "RushHud"))
            run = open(paths["run"], encoding="utf-8").read()
            install = open(paths["install"], encoding="utf-8").read()
            collect = open(paths["collect"], encoding="utf-8").read()
        bridge = sc.fingerprint(open(os.path.join(ROOT, "kit", "studio", "capture_bridge.luau"), encoding="utf-8").read())
        harness = sc.fingerprint(open(os.path.join(ROOT, "kit", "ui", "playtest.luau"), encoding="utf-8").read())
        self.assertIn(f'Bridge = "{bridge}"', run)
        self.assertIn(f'UiPlaytest = "{harness}"', run)
        self.assertIn("if #missing > 0 then", run)
        self.assertIn('\\"status\\": \\"install\\"', run)  # (the answer when the place lacks this version)
        self.assertIn('.run(JOB)', run)
        self.assertEqual(job["key"], "RushHud")
        self.assertEqual(job["capture"], {"flash": sc.FLASH, "hold": sc.HOLD})
        self.assertIn("Ui", job["kitPrints"])
        self.assertEqual(job["screenPrints"]["RushHud"],
                         sc.tree_print(json.load(open(os.path.join(ROOT, "src", "ui", "RushHud.model.json"), encoding="utf-8"))))
        sent = json.loads(re.search(r"local JOB = \[(=*)\[\n(.*)\]\1\]", run, re.S).group(2))
        self.assertEqual(sent["bar"], "Hud.Health")
        self.assertIn(f'put("UiPlaytest", "{harness}", [', install)
        self.assertIn('"RushHud"', collect)
        for text in (run, install, collect):  # nothing in a run's scripts calls out of Studio
            self.assertNotIn("GetAsync", text)
            self.assertNotIn("127.0.0.1", text)
            self.assertNotIn("RequestAsync", text)

    def test_every_generated_script_parses_as_luau(self):
        # (an install script once read "m.Name = name" then "(m :: any).Source = ..." on the next line: Luau refused it
        # as an ambiguous call - measured in Studio 2026-11-19)
        import shutil  # noqa: PLC0415
        import subprocess  # noqa: PLC0415

        stylua = shutil.which("stylua")
        if not stylua:
            self.skipTest("stylua is not on PATH")
        with tempfile.TemporaryDirectory() as tmp:
            for harness in sc.HARNESSES:
                _job, paths = sc.write_snippets(harness, {"screen": "RushHud"}, os.path.join(tmp, harness))
                for path in paths.values():
                    r = subprocess.run([stylua, "--check", path], capture_output=True, text=True)
                    self.assertNotIn("error parsing", r.stdout + r.stderr, path)

    def test_the_booth_harnesses_call_nothing_outside_studio(self):
        for rel in sc.MODULES.values():
            with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
                src = fh.read()
            for word in ("GetAsync", "PostAsync", "RequestAsync", "127.0.0.1", "localhost", "HttpEnabled"):
                self.assertNotIn(word, src, rel)


if __name__ == "__main__":
    unittest.main()
