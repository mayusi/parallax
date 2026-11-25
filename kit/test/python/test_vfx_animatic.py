"""kit/vfx/animatic.py (the VFX studio-route plan, V2): the timing animatic - a scene set's motion in flat shapes,
made from its beat chart and the scene's measured timing before the effect's look is built.

The plan and the preset are arithmetic and are held to it here: a shape's size from the share of the frame the
scene's beat covers, a beat's time and length from the chart, how its light arrives and goes from the scene's main
shot (and a NOTE wherever the scene could not say), the hit-stops from the chart's holds, the drawing rhythm, the id.
The run round a recording is proven on a made project with no browser (kit/selftest/vfx/animatic/madeanimatic.py:
its recordings are made from the plan itself): the animatic's own check of its recording, the beat pages, the
side-by-side video, --check (stale after a re-timed chart, after a replaced video), and --drift - a built effect
whose beat arrives three frames late against the animatic is named, one that is on time is not.

Needs ffmpeg for the made project (frames go through its pipe).
"""

import contextlib
import io
import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from glob import glob
from unittest import mock

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "selftest", "vfx", "animatic"))
import animatic as A  # noqa: E402
import madeanimatic as M  # noqa: E402

HERO = {"pos": [-15.0, 5.0, -24.0], "look": [0.0, 7.0, 0.0], "fov": 66.0}
FX = {"duration": 1.2}             # the made effect's clock: as long as its chart, no hit-stop
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def timing(arrive=0.0, go=0.25, on=2, cut_in=False, stay_cut=False, cut_away=False, peak=0.3):
    return {"cut_in": cut_in, "stay_cut": stay_cut, "cut_away": cut_away, "on": on, "peak": peak,
            "seconds": {"arrive": arrive, "go": go}}


def run(argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = A.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


class TestPlan(unittest.TestCase):
    def test_a_shape_covers_the_share_of_the_frame_the_scenes_beat_does(self):
        w, h = A.frame_size(HERO)
        self.assertAlmostEqual(w / h, 16 / 9)
        self.assertAlmostEqual(h, 2 * A.NEAR * math.tan(math.radians(33)))    # what the camera sees NEAR studs ahead
        for shape in ("disc", "ring", "bar", "wall", "arc"):
            for share in (0.05, 0.2, 0.6):
                s = A.size_of(shape, share, HERO)
                self.assertAlmostEqual(A.unit_area(shape) * s * s / (w * h), share, places=6, msg=shape)
        self.assertAlmostEqual(A.size_of("disc", 0.2, HERO, 1.1) / A.size_of("disc", 0.2, HERO), 1.1)    # a measured gain
        # the shapes stand on the camera's own line of sight, in FRONT of the booth (its ground cut every large shape)
        point = A.card_point(HERO)
        self.assertAlmostEqual(math.dist(point, HERO["pos"]), A.NEAR, places=3)
        along = [(q - p) for p, q in zip(HERO["pos"], HERO["look"])]
        ahead = [(q - p) for p, q in zip(HERO["pos"], point)]
        self.assertAlmostEqual(sum(a * b for a, b in zip(along, ahead)) / (math.hypot(*along) * math.hypot(*ahead)), 1.0)

    def test_a_beats_shape_is_read_from_its_words_else_from_how_much_it_fills(self):
        self.assertEqual(A.shape_of("1 key the dance arc", 0.4), "arc")
        self.assertEqual(A.shape_of("2 trailing ribbon", 0.1), "bar")
        self.assertEqual(A.shape_of("a shock wave", 0.3), "ring")
        self.assertEqual(A.shape_of("the white-out", 0.1), "wall")
        self.assertEqual(A.shape_of("0 ignition", 0.79), "wall")           # no word for it: it fills the frame
        self.assertEqual(A.shape_of("4 embers", 0.12), "disc")
        self.assertEqual(A.shape_of("searching", 0.3), "disc")             # ("arc" inside another word is not the word)

    def test_the_chart_gives_the_time_the_scene_gives_the_motion_and_what_it_could_not_say_is_a_note(self):
        beats = [{"beat": "0 the hit", "t": 0.0, "len": 0.5, "hold": 0.1, "key": True},
                 {"beat": "1 a beam", "t": 0.5, "len": 2.0, "hold": 0.0, "slow": 2.0},
                 {"beat": "2 gone", "t": 1.0, "len": 0.4}]
        reads = [{"timing": timing(arrive=0.125, go=0.25, on=1), "share": 0.3},
                 {"timing": timing(arrive=2.0, stay_cut=True, on=None), "share": 0.1},
                 None]
        rows = A.plan_rows(beats, reads, 1.6)
        first, second, third = rows
        self.assertEqual((first["t"], first["life"], first["arrive"], first["go"], first["on"], first["hit"], first["hold"]),
                         (0.0, 0.5, 0.125, 0.25, 1, 0.125, 0.1))
        self.assertEqual((first["shape"], first["share"], first["key"], first["notes"]), ("disc", 0.3, True, []))
        # the chart gives the beam 2 s, the next beat starts after 0.5 s: it is shown that long, and it says so
        self.assertEqual((second["life"], second["shape"], second["slow"]), (0.5, "bar", 2.0))
        self.assertEqual(second["arrive"], 0.25)                           # the scene takes 2 s: half of what it has
        notes = " | ".join(second["notes"])
        for said in ("its going is not known" if False else "how it goes is not known", "takes 2.00 s to arrive",
                     "the next beat starts after 0.50 s", "rhythm could not be read"):
            self.assertIn(said, notes)
        self.assertEqual(second["on"], 2)                                  # no rhythm read: on twos, and said
        # a beat the scene was not read for on this machine: a plain default, said
        self.assertEqual((third["shape"], third["arrive"], third["on"]), ("disc", 0.0, 2))
        self.assertIn("was not read on this machine", third["notes"][0])
        self.assertAlmostEqual(third["life"], 0.4)
        # a shot that opens on the light: how it arrives is not known
        opened = A.plan_rows([{"beat": "x", "t": 0.0, "len": 1.0}], [{"timing": timing(cut_in=True, arrive=0.3), "share": 0.2}], 1.0)[0]
        self.assertEqual(opened["arrive"], 0.0)
        self.assertIn("opens on it already lit", opened["notes"][0])

    def test_the_id_is_of_the_plan_and_another_once_the_chart_is_re_timed(self):
        beats = [{"beat": "0 the hit", "t": 0.0, "len": 0.5, "key": True}, {"beat": "1 the going", "t": 0.5, "len": 0.7}]
        reads = [{"timing": timing(), "share": 0.2}, {"timing": timing(), "share": 0.2}]
        rows = A.plan_rows(beats, reads, 1.2)
        first = A.plan_id("fire", rows, "hero", 1.2)
        self.assertEqual(len(first), 12)
        self.assertEqual(A.plan_id("fire", A.plan_rows(beats, reads, 1.2), "hero", 1.2), first)
        beats[0]["len"] = 0.3
        self.assertNotEqual(A.plan_id("fire", A.plan_rows(beats, reads, 1.2), "hero", 1.2), first)
        beats[0]["len"] = 0.5
        self.assertNotEqual(A.plan_id("fire", rows, "cine", 1.2), first)
        # what is measured back or said later is not the plan: the id does not move with it
        rows[0]["measured"], rows[0]["differs"] = {"hit": 0.03, "share": 0.21}, ["it stays ..."]
        self.assertEqual(A.plan_id("fire", rows, "hero", 1.2), first)
        # the shapes' colour is the plan's (the set's band), and so is WHERE the scene's numbers came from
        banded = A.plan_id("fire", rows, "hero", 1.2, (5.0, 55.0), "aaaa")
        self.assertNotEqual(banded, first)
        self.assertEqual(A.plan_id("fire", rows, "hero", 1.2, [5.0, 55.0], "aaaa"), banded)
        self.assertNotEqual(A.plan_id("fire", rows, "hero", 1.2, (200.0, 240.0), "aaaa"), banded)
        self.assertNotEqual(A.plan_id("fire", rows, "hero", 1.2, (5.0, 55.0), "bbbb"), banded)
        # ... and where the camera stands: the shapes are sized and placed by it (a view moved in kit/vfx/views.json
        # under the same name is another animatic)
        seen = A.plan_id("fire", rows, "hero", 1.2, (5.0, 55.0), "aaaa", HERO)
        self.assertNotEqual(seen, banded)
        self.assertEqual(A.plan_id("fire", rows, "hero", 1.2, (5.0, 55.0), "aaaa", dict(HERO)), seen)
        self.assertNotEqual(A.plan_id("fire", rows, "hero", 1.2, (5.0, 55.0), "aaaa", dict(HERO, pos=[-15.0, 5.0, -20.0])), seen)
        self.assertNotEqual(A.plan_id("fire", rows, "hero", 1.2, (5.0, 55.0), "aaaa", dict(HERO, fov=50.0)), seen)

    def test_where_the_scenes_numbers_came_from_is_one_id_and_another_window_is_another(self):
        found = {"beats": [{"beat": "0", "scene": [10.7, 13.5]}, {"beat": "1", "scene": [13.5, 14.0]}],
                 "breakdown": {"clip": "no/such/clip.mp4", "clip_fps": 24.0}, "cuts": [11.0, 13.5]}
        first = A.source_of(found)
        self.assertEqual((len(first), A.source_of(json.loads(json.dumps(found)))), (12, first))
        for change in (lambda f: f["beats"][0].__setitem__("scene", [10.7, 13.0]),    # the beat reads another window
                       lambda f: f["breakdown"].__setitem__("clip", "no/such/other.mp4"),
                       lambda f: f["breakdown"].__setitem__("clip_fps", 30.0),
                       lambda f: f["cuts"].append(12.0)):
            other = json.loads(json.dumps(found))
            change(other)
            self.assertNotEqual(A.source_of(other), first)
        self.assertEqual(len(A.source_of({"beats": [{"beat": "x"}], "breakdown": None, "cuts": []})), 12)    # no scene at all

    def test_every_number_the_plan_settles_itself_is_a_note_on_its_beat(self):
        said = lambda row: " | ".join(row["notes"])  # noqa: E731
        read = {"timing": timing(arrive=0.0, go=0.9, on=2), "share": 0.2}
        row = A.plan_rows([{"beat": "x", "t": 0.0, "len": 0.5, "hold": 2.5, "slow": 0.5}], [read], 1.0)[0]
        self.assertEqual((row["hold"], row["slow"]), (1.8, 1.0))
        for words in ("the player's longest hit-stop is 1.80 s", "would be FASTER than real time",
                      "the scene takes 0.90 s to go, the beat has 0.42 s after it arrives"):
            self.assertIn(words, said(row))
        row = A.plan_rows([{"beat": "x", "t": 0.0, "len": 0.5, "hold": 0.01, "slow": 0}], [read], 1.0)[0]
        self.assertEqual((row["hold"], row["slow"]), (0.0, 1.0))
        self.assertIn("under the player's shortest hit-stop", said(row))
        self.assertIn("slow 0 is not a speed", said(row))
        self.assertEqual(A.plan_rows([{"beat": "x", "t": 0.0, "slow": 50}], [read], 1.0)[0]["slow"], 20.0)
        # what is not a number, or is below nothing, is read as none - and said
        row = A.plan_rows([{"beat": "x", "t": "soon", "len": "long", "hold": -0.2}], [read], 1.0)[0]
        self.assertEqual((row["t"], row["life"], row["hold"]), (0.0, 1.0, 0.0))
        for words in ('the chart\'s "t" (\'soon\') is not a number', 'the chart\'s "len" (\'long\') is not a number',
                      'the chart\'s "hold" is negative (-0.2)'):
            self.assertIn(words, said(row))
        # ... and what is not a FINITE number neither ("nan" and "inf" are numbers to a computer, and a chart's JSON
        # may hold them): each is read as none and said, never carried into the plan
        row = A.plan_rows([{"beat": "x", "t": "nan", "len": float("inf"), "slow": "nan", "hold": float("nan")}], [read], 1.0)[0]
        self.assertEqual((row["t"], row["life"], row["slow"], row["hold"], row["hit"]), (0.0, 1.0, 1.0, 0.0, 0.0))
        self.assertEqual(sum("is not a number" in n for n in row["notes"]), 4)
        row = A.plan_rows([{"beat": "x", "t": True, "hold": True, "slow": False}], [read], 1.0)[0]     # true is not 1
        self.assertEqual((row["t"], row["hold"], row["slow"]), (0.0, 0.0, 1.0))
        self.assertEqual(sum("is not a number" in n for n in row["notes"]), 3)
        # a beat the next one leaves less than two film frames: shown that long all the same, over the next one, and said
        short, after = A.plan_rows([{"beat": "a", "t": 0.5, "len": 0.5}, {"beat": "b", "t": 0.54, "len": 0.2}],
                                   [read, {"timing": timing(go=0.08), "share": 0.2}], 1.0)
        self.assertAlmostEqual(short["life"], 0.083, places=3)
        self.assertIn("shown for 0.08 s, the least a shape is seen for (it is still there when the next beat starts)", said(short))
        self.assertEqual(after["notes"], [])
        # the chart's end cuts a beat as the next beat does, and the words say which
        self.assertIn("the chart ends after 0.40 s", said(A.plan_rows([{"beat": "x", "t": 0.6, "len": 2.0}], [read], 1.0)[0]))
        # a rhythm slower than a drawing a second is none the player's stepped clock has
        slow = A.plan_rows([{"beat": "x", "t": 0.0, "len": 3.0}], [{"timing": timing(on=40), "share": 0.2}], 3.0)[0]
        self.assertEqual((slow["on"], slow["step"]), (24, 1.0))
        self.assertIn("holds a drawing 40 film frames", said(slow))

    def test_a_beat_the_chart_leaves_no_room_for_is_a_problem_not_a_shape(self):
        read = {"timing": timing(), "share": 0.2}
        rows = A.plan_rows([{"beat": "0 in", "t": 0.0, "len": 0.5}, {"beat": "1 at the end", "t": 1.0}, {"beat": "2 past it", "t": 1.4},
                            {"beat": "3 too near", "t": 0.95}, {"beat": "4 before it", "t": -0.2}], [read] * 5, 1.0)
        self.assertNotIn("problem", rows[0])
        self.assertIn("at or after the chart's end (1.00 s)", rows[1]["problem"])
        self.assertIn("at or after the chart's end", rows[2]["problem"])
        self.assertIn("starts 0.05 s before the chart's end (1.00 s): a shape is seen for 0.08 s at least", rows[3]["problem"])
        self.assertIn("starts before the chart does", rows[4]["problem"])
        # ... and none of them is in the preset
        preset = A.preset_of("s", rows, "hero", HERO, 1.0, None)
        self.assertEqual([el["at"] for el in preset["layers"]], [0.0])
        # a start and a length that are rounded never add up to past the chart's end (the player refuses such a layer)
        for start in (0.3335, 0.3336, 0.6664, 0.0005, 0.9):
            row = A.plan_rows([{"beat": "x", "t": start}], [read], 1.0)[0]
            self.assertNotIn("problem", row, start)
            self.assertLessEqual(row["t"] + row["life"], 1.0 + 1e-9, start)


class TestPreset(unittest.TestCase):
    def setUp(self):
        beats = [{"beat": "0 the hit", "t": 0.0, "len": 0.5, "hold": 0.1, "key": True},
                 {"beat": "1 the dance arc", "t": 0.5, "len": 0.5, "hold": 0.0},
                 {"beat": "2 embers", "t": 1.0, "len": 1.0, "slow": 2.0}]
        reads = [{"timing": timing(arrive=0.125, go=0.25, on=1), "share": 0.3},
                 {"timing": timing(arrive=0.0, go=0.125, on=1), "share": 0.3},
                 {"timing": timing(arrive=0.0, go=0.5, on=2), "share": 0.1}]
        self.rows = A.plan_rows(beats, reads, 2.0)
        self.preset = A.preset_of("fire", self.rows, "hero", HERO, 2.0, (5.0, 55.0))

    def test_one_flat_shape_a_beat_facing_the_camera_in_front_of_the_booth(self):
        p = self.preset
        self.assertEqual((p["version"], p["mode"], p["duration"], p["booth"]), (3, "burst", 2.0, {"views": ["hero"]}))
        self.assertEqual([el["kind"] for el in p["layers"]], ["mesh"] * 3)
        self.assertEqual([el["shape"] for el in p["layers"]], ["disc", "arc", "disc"])
        for el, row in zip(p["layers"], self.rows):
            self.assertEqual((el["point"], el["aim"]), (A.card_point(HERO), HERO["pos"]))
            self.assertEqual((el["at"], el["life"], el["material"]), (row["t"], row["life"], "Neon"))    # ON its beat
            self.assertNotIn("texture", el)                                # no textures, no sims
        self.assertEqual(len({el["name"] for el in p["layers"]}), 3)

    def test_the_light_changes_on_its_drawings_and_is_whole_on_the_hit(self):
        el, row = self.preset["layers"][0], self.rows[0]
        # on ones, half a second: 12 drawings; its light arrives ON the fourth (0.125 s) and takes six to go (0.25 s)
        self.assertEqual(A.drawings_of(row), (24.0, 12, 3, 6))
        light = A.light_of(row)
        self.assertEqual([round(v, 2) for v in light], [0.15, 0.3, 0.45, 1.0, 0.94, 1.0, 0.6, 0.54, 0.48, 0.42, 0.36, 0.3, 0.0])
        keys = el["scale"]
        self.assertEqual([k[0] for k in keys], [round(k / 12, 5) for k in range(13)])   # one key a drawing, ON its drawing
        full = A.size_of("disc", row["share"], HERO)
        for key, share in zip(keys, light):                                # the shape's AREA is its light
            self.assertAlmostEqual((key[1][0] / full) ** 2, max(share, 0.0004), places=3)
        self.assertEqual(el["step"], 24.0)                                 # on ones: 24 drawings a second
        self.assertEqual(self.preset["layers"][2]["step"], 12.0)           # on twos

    def test_whatever_the_beat_its_light_is_whole_on_the_hit_drawing_and_gone_on_the_last(self):
        # the timing read calls a beat arrived at 0.7 of the way from its stretch's floor to its peak, and a beat's own
        # lead-in or going can be taken for that floor: the line sits anywhere from 0.70 to about 0.85 of the whole
        # light. So never more than 0.45 of it before the hit, and WHOLE on it (0.7 on the hit, then 0.85, were each
        # read as the hit or as the drawing after it by luck: two FlameArc beats two frames late, 2026-11-12).
        # EVERY shape of beat the plan can make: so many drawings, the hit on any of them, any going
        for count in range(2, 31):
            for n in range(0, count):
                for fall in range(0, count - n):
                    row = {"life": count / 12.0 + 0.001, "step": 12.0, "on": 2, "arrive": round(n / 12.0, 3), "go": round(fall / 12.0, 3)}
                    self.assertEqual(A.drawings_of(row), (12.0, count, n, fall))
                    light = A.light_of(row)
                    said = (count, n, fall, light)
                    self.assertEqual(len(light), count + 1, said)
                    pre, stay, going = light[:n], light[n:count - fall], light[count - fall:count]
                    self.assertTrue(all(0.14 <= v <= 0.46 for v in pre) and pre == sorted(pre), said)    # started, far from arrived
                    self.assertEqual(light[n], 1.0, said)                                              # WHOLE on the hit
                    self.assertTrue(all(v >= 0.94 for v in stay), said)                                # it stays over any line
                    self.assertTrue(all(a != b for a, b in zip(stay, stay[1:])), said)                 # no two alike in a row
                    self.assertTrue(all(0.29 <= v <= 0.61 for v in going) and going == sorted(going, reverse=True), said)
                    self.assertEqual(light[count], 0.0, said)                                          # gone on the last
        # the plan gives the layer whole drawings: the hit is a drawing that is there, whatever the scene measured
        rows = A.plan_rows([{"beat": "x", "t": 0.2, "len": 1.0}], [{"timing": timing(arrive=0.125, go=0.21, on=2), "share": 0.2}], 2.0)
        row = rows[0]
        self.assertEqual((row["arrive"], row["go"], row["hit"]), (0.167, 0.25, 0.367))     # 0.125 s on twos: the 2nd drawing
        self.assertIn("its light takes 0.125 s to arrive: drawn on twos that is 2 drawing(s), 0.167 s", " | ".join(row["notes"]))
        self.assertIn("its light takes 0.210 s to go: drawn on twos that is 3 drawing(s), 0.250 s", " | ".join(row["notes"]))

    def test_an_arc_draws_itself_in_and_is_wiped_from_its_tail(self):
        arc = self.preset["layers"][1]
        self.assertEqual(arc["params"], A.ARC)
        self.assertEqual(arc["sweep"]["head"][0], [0.0, 1.0])              # it arrives at once: whole from its first frame
        tail = arc["sweep"]["tail"]
        self.assertEqual((tail[0], tail[-1]), ([0.0, 0.0], [1.0, 1.0]))
        self.assertEqual([k[0] for k in tail], sorted({k[0] for k in tail}))
        # at full size throughout, a hair smaller on every other drawing (its rhythm shows; a hit-stop is then the
        # only held drawing)
        sizes = [k[1][0] for k in arc["scale"]]
        self.assertTrue(len(sizes) >= 3 and min(sizes) >= 0.96 * max(sizes) and sizes[0] != sizes[1])
        self.assertEqual([k[0] for k in arc["scale"]], sorted({k[0] for k in arc["scale"]}))

    def test_the_charts_holds_are_hit_stops_on_the_hit_and_slow_motion_is_the_clocks_speed(self):
        self.assertEqual(self.preset["hitstop"], [{"at": 0.125, "hold": 0.1}])       # ON the hit
        warp = self.preset["timewarp"]
        self.assertEqual([k for k in warp if k[0] >= 1.0], [[1.0, 0.5], [2.0, 0.5]])    # half speed through the slowed beat
        self.assertEqual(warp[0], [0.999, 1.0])                            # ... and its own speed up to it
        self.assertEqual([k[0] for k in warp], sorted(k[0] for k in warp))
        # a hold at the very start is put a frame in (the player has no hit-stop at 0), and one under 0.02 s is none
        rows = A.plan_rows([{"beat": "x", "t": 0.0, "len": 1.0, "hold": 0.3}, {"beat": "y", "t": 1.0, "len": 0.5, "hold": 0.01}],
                           [{"timing": timing(), "share": 0.2}] * 2, 1.5)
        stops = A.preset_of("s", rows, "hero", HERO, 1.5, None)["hitstop"]
        self.assertEqual(len(stops), 1)
        self.assertTrue(0 < stops[0]["at"] < 0.02)
        # two beats that hit at one moment are ONE hit-stop there, the longer hold (the player takes only the first
        # stop at a time: the second was silently never held)
        rows = A.plan_rows([{"beat": "a flash", "t": 0.5, "len": 0.5, "hold": 0.1}, {"beat": "a ring", "t": 0.5, "len": 0.5, "hold": 0.25},
                            {"beat": "after", "t": 1.0, "len": 0.5, "hold": 0.05}], [{"timing": timing(), "share": 0.2}] * 3, 1.5)
        self.assertEqual(A.preset_of("s", rows, "hero", HERO, 1.5, None)["hitstop"],
                         [{"at": 0.5, "hold": 0.25}, {"at": 1.0, "hold": 0.05}])
        # whatever the beat's time and rhythm, the layer's stepped clock is ON the hit drawing when the clock stops -
        # by the player's own sum, `floor((stop - at) * step)`. Written in thousandths the hit can be a hair BEFORE its
        # drawing (0.083 is before 2/24; 0.175 - 0.05 is 0.12499999999999999 in a computer): the stop is then a
        # thousandth on
        stopped = {}
        for start, step, n in ((1.9, 24.0, 3), (0.3, 12.0, 1), (0.85, 12.0, 6), (2.2, 24.596, 1), (0.0, 24.0, 2), (0.7, 8.0, 5),
                               (0.5, 12.0, 0), (1.0, 24.0, 4), (0.333, 12.0, 2), (0.0, 12.0, 0), (0.05, 24.0, 3), (0.1, 12.0, 3)):
            row = {"index": 0, "beat": "x", "key": False, "t": start, "life": 2.0, "hold": 0.1, "slow": 1.0, "on": 1, "step": step,
                   "arrive": round(n / step, 3), "go": 0.0, "share": 0.2, "shape": "disc", "hit": round(start + n / step, 3), "notes": []}
            made = A.preset_of("s", [row], "hero", HERO, 5.0, None)
            stop, layer = made["hitstop"][0]["at"], made["layers"][0]
            self.assertEqual(layer["at"], start)
            self.assertGreaterEqual(math.floor((stop - layer["at"]) * layer["step"]), n, (start, step, n))
            self.assertLess(math.floor((stop - 0.001 - layer["at"]) * layer["step"]), max(n, 1), (start, step, n))   # the first such
            stopped[(start, step, n)] = stop
        self.assertEqual((stopped[(1.9, 24.0, 3)], stopped[(0.0, 24.0, 2)], stopped[(0.5, 12.0, 0)], stopped[(0.0, 12.0, 0)]),
                         (2.025, 0.084, 0.5, 0.017))
        self.assertLess(math.floor((0.175 - 0.05) * 24.0), 3)              # (the sum that is a hair short ...)
        self.assertEqual((stopped[(0.05, 24.0, 3)], stopped[(0.1, 12.0, 3)]), (0.176, 0.351))     # ... and the stop a thousandth on

    def test_which_frame_first_shows_a_drawing_is_the_players_own_sum_on_the_recorders_clock(self):
        times = A.DC.frame_times({"duration": 1.2}, 30.0)
        # fifteen steps of a thirtieth are a hair UNDER half a second in a computer: the frame that "should" show 0.5 s
        # does not show a layer that starts there, and the next one does. Nothing is rounded to make it look right
        self.assertLess(times[14], 0.5)
        self.assertEqual(A.first_shown(times, 0.5, 12.0), 15)
        self.assertEqual(A.first_shown(times, 0.3, 12.0), 8)               # (nine steps reach 0.3)
        self.assertEqual(A.first_shown(times, 0.5, 12.0, 2), 20)           # its third drawing: 0.5 + 2/12 s
        self.assertEqual(A.first_shown(times, 0.0, 24.0, 4), 4)            # 4/24 s is five thirtieths: frame 4 shows it
        self.assertEqual(A.first_shown(times, 5.0, 12.0), len(times))      # never shown
        # through a hit-stop: the frame that stops on 0.3 s, and the held ones, show the drawing that is there then
        held = A.DC.frame_times({"duration": 1.2, "hitstop": [{"at": 0.3, "hold": 0.12}]}, 30.0)
        self.assertEqual((A.first_shown(held, 0.3, 24.0), A.first_shown(held, 0.3, 24.0, 1)), (8, 13))

    def test_a_beat_shorter_than_two_drawings_of_its_rhythm_is_drawn_on_a_finer_one(self):
        # on twos a drawing is 1/12 s: a beat of 0.083 s has not two of them, and its curve ended AFTER its life
        # (a key at 1.004: the player refused the whole preset - two of the project's own charts, a review 2026-11-12)
        for life, on in ((0.083, 2), (0.1, 2), (0.15, 3), (0.084, 1), (0.2, 3), (0.166, 2)):
            row = A.plan_rows([{"beat": "x", "t": 0.2, "len": life}], [{"timing": timing(go=0.04, on=on), "share": 0.2}], 1.0)[0]
            self.assertGreaterEqual(row["life"] * row["step"], 2.0, (life, on))
            self.assertLessEqual(row["step"], 60.0)
            finer = row["step"] > A.FILM / on + 1e-9
            self.assertEqual(finer, any("shown on a finer rhythm" in n for n in row["notes"]), (life, on))
            for shape in ("disc", "arc"):
                el = A.layer_of(dict(row, shape=shape), HERO, (5.0, 55.0))
                curves = [el["scale"]] + ([el["sweep"]["head"], el["sweep"]["tail"]] if shape == "arc" else [])
                for keys in curves:
                    us = [k[0] for k in keys]
                    self.assertEqual((us[0], us[-1]), (0.0, 1.0), (life, on, shape))
                    self.assertEqual(us, sorted(set(us)), (life, on, shape))           # rising, none twice, none past 1
        # a beat with room for its rhythm keeps it, and says nothing
        row = A.plan_rows([{"beat": "x", "t": 0.0, "len": 0.5}], [{"timing": timing(on=2), "share": 0.2}], 1.0)[0]
        self.assertEqual((row["step"], row["notes"]), (12.0, []))

    def test_the_colour_is_the_one_the_player_shows_inside_the_sets_band(self):
        # written as it should LOOK, a flat card came out yellow: the player raises linear light to 1/2.2 and its bloom
        # lifts the weaker channels about 3.4 times (measured on six cards, 2026-11-12)
        r, g, b = A.colour_of((5.0, 55.0), False)
        self.assertEqual((r, b), (150, 1))
        self.assertTrue(18 <= g <= 26)                                     # [150, 22, 0] showed as hue 30
        self.assertEqual(A.colour_of((5.0, 55.0), True), A.WHITE_HOT)      # the key beat: white-hot
        self.assertEqual(max(A.colour_of((200.0, 240.0), False)), A.colour_of((200.0, 240.0), False)[2])   # a blue set: blue leads


@unittest.skipUnless(shutil.which("lune"), "lune not found")
class TestThePlayerTakesIt(unittest.TestCase):
    """the presets the plan makes, by the kit's OWN rules (src/kit/VfxValidate, through kit/vfx/validate_preset.luau):
    what `kit vfx play` checks before it plays anything. A review (2026-11-12) found two of the project's own charts
    making presets the player refuses; nothing here had ever asked it."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kit_animatic_presets_")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def written(self, name, beats, reads, duration):
        rows = A.plan_rows(beats, reads, duration)
        self.assertEqual([r["problem"] for r in rows if r.get("problem")], [], name)
        path = os.path.join(self.dir, f"{name}.json")
        A.DC.dump(A.preset_of(name, rows, "hero", HERO, duration, (5.0, 55.0)), path)
        return path

    def test_the_hard_charts_make_presets_the_player_takes(self):
        paths = []
        words = ("0 ignition", "1 key the dance arc", "2 a shock wave", "3 a beam", "4 the white-out", "5 embers")
        for on in (1, 2, 3, None):
            read = {"timing": timing(arrive=0.04, go=0.08, on=on), "share": 0.3}
            slow_in = {"timing": timing(arrive=0.6, go=0.9, on=on), "share": 0.9}
            # beats of every shape, each shorter than the one before, down to under two film frames
            short = [{"beat": w, "t": round(0.3 * k, 3), "len": [0.3, 0.2, 0.12, 0.09, 0.084, 0.05][k], "hold": [0, 0.1, 0, 2.5, 0.01, 0][k]}
                     for k, w in enumerate(words)]
            paths.append(self.written(f"short_on{on}", short, [read] * 6, 2.0))
            paths.append(self.written(f"slow_in_on{on}", short, [slow_in] * 6, 2.0))
            # a hold on the very first frame, two beats on one moment, slow motion back to back, a beat that ends
            # with the chart, a beat the next one leaves 0.04 s
            mixed = [{"beat": "a flash", "t": 0.0, "len": 0.4, "hold": 0.3, "key": True},
                     {"beat": "a ring", "t": 0.4, "len": 0.4, "hold": 0.1, "slow": 3.0},
                     {"beat": "an arc", "t": 0.4, "len": 0.6, "hold": 0.25, "slow": 2.0},
                     {"beat": "a streak", "t": 1.0, "len": 0.5, "slow": 40.0},
                     {"beat": "a blink", "t": 1.5, "len": 0.5},
                     {"beat": "the wall", "t": 1.54, "len": 5.0},
                     {"beat": "last", "t": 2.9, "len": 0.1}]
            paths.append(self.written(f"mixed_on{on}", mixed, [read] * 7, 3.0))
        paths.append(self.written("not_read", [{"beat": "x", "t": 0.3335, "len": 0.09}, {"beat": "y", "t": 0.5}], [None, None], 1.0))
        for path, errors in A.refusals(paths).items():
            self.assertEqual(errors, [], os.path.basename(path))

    def test_the_projects_own_charts_make_presets_the_player_takes(self):
        charts = sorted(glob(os.path.join(REPO, "assets", "effects", "refs_measured", "*.chart.json")))
        if not charts:
            self.skipTest("this project has no beat charts")
        paths = []
        for chart_path in charts:
            chart = json.load(open(chart_path, encoding="utf-8"))
            name = os.path.basename(chart_path).split(".")[0]
            for on in (1, 2, 3):                           # (the scene's clips are private: every rhythm it could read)
                reads = [{"timing": timing(arrive=0.04, go=0.08, on=on), "share": 0.3}] * len(chart["beats"])
                paths.append(self.written(f"{name}_on{on}", chart["beats"], reads, float(chart["duration"])))
            paths.append(self.written(f"{name}_not_read", chart["beats"], [None] * len(chart["beats"]), float(chart["duration"])))
        for path, errors in A.refusals(paths).items():
            self.assertEqual(errors, [], os.path.basename(path))

    def test_a_preset_the_player_refuses_is_said_with_the_rule_it_breaks(self):
        path = self.written("broken", [{"beat": "x", "t": 0.0, "len": 0.5}], [{"timing": timing(), "share": 0.2}], 1.0)
        preset = json.load(open(path))
        preset["layers"][0]["scale"][-1][0] = 1.004            # the key the review found: after the layer's life
        preset["hitstop"] = [{"at": 0.0, "hold": 0.1}]         # ... and a hit-stop the player has no moment for
        A.DC.dump(preset, path)
        errors = A.refused(path)
        self.assertTrue(any(".scale" in e for e in errors), errors)
        self.assertTrue(any("hitstop[1].at" in e for e in errors), errors)
        missing = os.path.join(self.dir, "none.json")
        self.assertEqual(A.refused(missing), ["not a preset that can be read (JSON)"])
        # more files than one command line holds are asked in batches: each still gets its own answer
        good = self.written("good", [{"beat": "x", "t": 0.0, "len": 0.5}], [{"timing": timing(), "share": 0.2}], 1.0)
        many = []
        for i in range(85):
            many.append(os.path.join(self.dir, f"copy_{i:03d}_with_a_long_enough_name_to_fill_a_command_line.json"))
            shutil.copyfile(path if i == 60 else good, many[-1])
        answers = A.refusals(many)
        self.assertEqual(len(answers), 85)
        self.assertEqual([i for i, p in enumerate(many) if answers[os.path.abspath(p)]], [60])
        with mock.patch.object(A.shutil, "which", return_value=None):  # the rules could not be run: that is an error too
            self.assertIn("could not be run", A.refused(path)[0])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not found")
class TestMadeProject(unittest.TestCase):
    def setUp(self):
        self.here = os.getcwd()
        self.root = tempfile.mkdtemp(prefix="kit_animatic_")
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.here)
        shutil.rmtree(self.root, ignore_errors=True)

    def test_the_animatic_is_made_checks_itself_and_knows_when_it_is_stale(self):
        rows, _, _ = M.project(self.root)
        code, got = run(["fire", "--no-record"])
        self.assertEqual((code, got["status"]), (0, "pass"), got["summary"])
        self.assertIn("each hitting where the chart says", got["summary"])
        self.assertTrue(got["summary"].rstrip().endswith("LOOK: build/vfx/animatic/fire_side.mp4"))
        made = json.load(open(os.path.join("build", "vfx", "animatic", "fire.plan.json"), encoding="utf-8"))
        self.assertEqual([b["beat"] for b in made["beats"]], ["0 the hit", "1 the going"])
        for b in made["beats"]:                                            # its own recording read back against the plan
            self.assertAlmostEqual(b["measured"]["hit"], b["hit"], delta=1.5 / 30)
            self.assertTrue(0.5 <= b["measured"]["share"] / b["share"] <= 2.0)
        self.assertEqual(made["shown"][0], "build/vfx/animatic/fire_side.mp4")
        self.assertEqual([os.path.basename(p) for p in made["shown"][1:]], ["beat0_page.png", "beat1_page.png"])
        for p in made["shown"]:
            self.assertTrue(os.path.getsize(p) > 2000, p)
        preset = json.load(open(os.path.join("build", "vfx", "animatic", "fire.json"), encoding="utf-8"))
        self.assertEqual((preset["version"], len(preset["layers"])), (3, 2))
        self.assertFalse(os.path.exists(os.path.join("assets", "effects", "fire.json")))   # never among the effects
        # --check: it is there, it is this plan's, and what he is shown is what its hash is of
        code, check = run(["fire", "--check"])
        self.assertEqual((check["exists"], check["stale"], check["id"], check["shown"]), (True, False, got["id"], made["shown"]))
        self.assertEqual(len(check["drawn"]), 12)
        # the video replaced after it was made: not the one its record was written for
        video = made["shown"][0]
        keep = open(video, "rb").read()
        open(video, "wb").write(keep + b"x")
        swapped = run(["fire", "--check"])[1]
        self.assertTrue(swapped["stale"])
        self.assertIn("not the one its record was written for", swapped["why"])
        open(video, "wb").write(keep)
        self.assertFalse(run(["fire", "--check"])[1]["stale"])
        # the chart re-timed after it was made: another plan, another id
        path = os.path.join("assets", "effects", "refs_measured", "fire.chart.json")
        chart = json.load(open(path))
        chart["beats"][0]["len"] = 0.3
        json.dump(chart, open(path, "w"))
        after = run(["fire", "--check"])[1]
        self.assertTrue(after["stale"])
        self.assertNotEqual(after["id"], got["id"])
        self.assertIn("re-timed", after["why"])
        os.remove(video)                                                   # a file of it gone: no animatic
        self.assertFalse(run(["fire", "--check"])[1]["exists"])

    def test_an_effect_on_the_animatics_timing_passes_and_one_three_frames_late_is_named(self):
        M.project(self.root)
        self.assertEqual(run(["fire", "--no-record"])[0], 0)
        code, drift = run(["fire", "--drift", "fx"])
        self.assertEqual((code, drift["drifts"]), (0, []), drift["summary"])
        late = M.clips.write(os.path.join("build", "vfx", "booth", "fx_play_hero.mp4"),
                             M.recording(M.rows_of("fire")[1], FX, late={1: 3}), 30)
        self.assertTrue(os.path.isfile(late))
        code, drift = run(["fire", "--drift", "fx"])
        self.assertEqual(code, 1)
        self.assertEqual(len(drift["drifts"]), 1)                          # the beat that drifted, and only it
        self.assertIn("beat 1 the going: the effect's light arrives 0.10 s (3 of its frames) after the animatic's", drift["summary"])
        # one frame is not a drift (a drawing on twos is two film frames)
        M.clips.write(os.path.join("build", "vfx", "booth", "fx_play_hero.mp4"),
                      M.recording(M.rows_of("fire")[1], FX, late={1: 1}), 30)
        self.assertEqual(run(["fire", "--drift", "fx"])[0], 0)

    def test_hit_stops_are_held_frames_and_each_recording_is_read_on_its_own_clock(self):
        # the chart holds the first beat 0.12 s: the animatic's clock stands still for it, so the second beat is
        # LATER in the recording than on the chart. The built effect has a hit-stop of its own, elsewhere and longer:
        # its recording runs on another clock again. Each is read on its own - and both are on time.
        rows, made_at, _ = M.project(self.root, holds={0: 0.12}, stops=[{"at": 0.25, "hold": 0.2}])
        code, got = run(["fire", "--no-record"])
        self.assertEqual((code, got["status"]), (0, "pass"), got["summary"])
        made = json.load(open(os.path.join("build", "vfx", "animatic", "fire.plan.json"), encoding="utf-8"))
        preset = json.load(open(os.path.join("build", "vfx", "animatic", "fire.json"), encoding="utf-8"))
        self.assertEqual([h["hold"] for h in preset["hitstop"]], [0.12])
        self.assertEqual(made["clock"]["hitstop"], preset["hitstop"])
        self.assertEqual(made["fps"], 30.0)
        second = made["beats"][1]
        # the recorder's own loop (the fixture's port of it): where the second beat's first frame is
        frames = M.player_clock(preset, 30)
        first = next(i for i, t in enumerate(frames) if t >= second["hit"])
        self.assertGreaterEqual(first / 30 - second["hit"], 2.5 / 30)      # the hold moved it three frames and more
        self.assertAlmostEqual(second["measured"]["hit"], first / 30, delta=1.01 / 30)
        self.assertEqual(len(frames), int(round(A.DC.probe(made_at)[1] * 30)))    # as many frames as its clock has steps
        code, drift = run(["fire", "--drift", "fx"])
        self.assertEqual((code, drift["drifts"]), (0, []), drift["summary"])
        self.assertTrue(all(abs(b["off"]) <= 1.01 / 30 for b in drift["beats"]), drift["beats"])
        # ... and three frames late on its own clock is still named
        effect = json.load(open(os.path.join("assets", "effects", "fx.json")))
        M.clips.write(os.path.join("build", "vfx", "booth", "fx_play_hero.mp4"), M.recording(rows, effect, late={1: 3}), 30)
        code, drift = run(["fire", "--drift", "fx"])
        self.assertEqual(code, 1)
        self.assertIn("beat 1 the going: the effect's light arrives 0.10 s (3 of its frames) after the animatic's", drift["summary"])
        # the built effect with NO hit-stop where the chart holds: its second beat comes early by the hold - named
        plain = dict(effect)
        plain.pop("hitstop")
        early = M.recording(rows, plain)
        json.dump(effect, open(os.path.join("assets", "effects", "fx.json"), "w"))     # (its preset still says it holds)
        M.clips.write(os.path.join("build", "vfx", "booth", "fx_play_hero.mp4"), early, 30)
        code, drift = run(["fire", "--drift", "fx"])
        self.assertEqual(code, 1)
        self.assertIn("before the animatic's", drift["summary"])

    def test_drift_reads_where_each_beats_light_first_arrives_and_what_it_cannot_read_it_says(self):
        rows, _, _ = M.project(self.root)
        self.assertEqual(run(["fire", "--no-record"])[0], 0)
        shot = os.path.join("build", "vfx", "booth", "fx_play_hero.mp4")

        def effect(**how):
            M.clips.write(shot, M.recording(rows, FX, **how), 30)
            return run(["fire", "--drift", "fx"])

        one = 1 / rows[1]["step"] + 0.25 / 30                              # one drawing of the beat, a quarter frame
        # a light that is there at once: one frame late is nothing, three are named
        self.assertEqual(effect(late={1: 1})[0], 0)
        code, got = effect(late={1: 3})
        self.assertEqual((code, got["beats"][1]["off"], got["beats"][1]["allowed"]), (1, 0.1, round(one, 3)))
        # NOTHING buys more than that one drawing. A spark at the beat's start, with the light itself three frames
        # late (an effect that "starts" on time), was let through while a slow start widened the allowance (a review,
        # 2026-11-12); so was a light that grows over eight frames and is at most of itself three frames after the plan
        for how in (dict(late={1: 3}, spark={1: 0.15}), dict(late={1: -3}, ramp={1: 8}), dict(ramp={1: 8})):
            code, got = effect(**how)
            self.assertEqual((code, got["beats"][1]["allowed"]), (1, round(one, 3)), (how, got["summary"]))
            self.assertGreaterEqual(got["beats"][1]["off"], 0.1, how)
            self.assertIn("beat 1 the going: the effect's light arrives", got["summary"])
            self.assertIn("after the animatic's", got["summary"])
        # still growing when its beat ends: it arrives AT LEAST that late
        code, got = effect(ramp={0: 40}, linger=(0,))
        self.assertEqual(code, 1)
        self.assertIn("beat 0 the hit: the effect's light arrives 0.33 s (10 of its frames) at least (it is still rising when "
                      "the beat ends) after the animatic's", got["summary"])
        self.assertIn("it grows over", got["summary"])
        self.assertEqual(len(got["drifts"]), 1)
        # the NEXT beat's light two frames early is in this beat's last frame: this beat is still on time (it was read
        # as arriving there, thirteen frames late), and two frames early is inside one drawing on twos
        code, got = effect(late={1: -2})
        self.assertEqual((code, [b["off"] for b in got["beats"]]), (0, [0.0, -0.067]), got["summary"])
        # light that never goes out between two beats: the second has no arrival of its own. By light alone the beat
        # before lingering and this one coming early by the whole gap look the same: both are named
        for how in (dict(linger=(0,)), dict(late={1: -4})):
            code, got = effect(**how)
            self.assertEqual(code, 1, how)
            self.assertIn("beat 1 the going: no light of its own arrives - what is lit when it starts has been on since the beat "
                          "before", got["summary"])
            self.assertIn("the beat before never goes out, or this one comes early by the whole gap between them", got["summary"])
        # a beat on time but a fifth of the size the plan gives it: the timing holds, and the size is SAID (the look is
        # the style sheet's to judge; "hits where its animatic does" alone would be read as "matches it")
        code, got = effect(dim={1: 0.2})
        self.assertEqual((code, len(got["small"])), (0, 1), got["summary"])
        self.assertIn("1 beat(s) far smaller than planned (only the timing is held here - the look is the style sheet's): "
                      "beat 1 the going covers 0.04 of the frame, the plan 0.20", got["summary"])
        self.assertEqual(effect()[1]["small"], [])
        # an ANIMATIC whose own beats run into each other cannot say when the second arrives: its record says so, and
        # --drift holds the effect to the beats it can read, naming the one it cannot
        # (a big beat whose last going drawing is still brighter than most of the small beat after it: by the PLAN)
        scene = A.scene_reads
        big = lambda found: [dict(read, share=share) for read, share in zip(scene(found), (0.6, 0.2))]  # noqa: E731
        with mock.patch.object(A, "scene_reads", side_effect=big):
            _, rows, _ = M.record_animatic("fire", drawn=True)
            code, got = run(["fire", "--no-record"])
        self.assertEqual(code, 0, got["summary"])
        made = json.load(open(os.path.join("build", "vfx", "animatic", "fire.plan.json"), encoding="utf-8"))
        self.assertEqual([b["measured"]["unseen"] for b in made["beats"]], [None, "opens"])
        self.assertIn("opens on light that is already as strong as its own", " | ".join(made["beats"][1]["notes"]))
        code, got = effect()
        self.assertEqual((code, got["unseen"]), (0, ["1 the going"]), got["summary"])
        self.assertIn("(1 beat(s), each within one drawing of it)", got["summary"])
        self.assertIn("1 beat(s) could not be held to it - the animatic's own light is already on when they start: 1 the going",
                      got["summary"])
        code, got = effect(late={0: 3})                                    # the beat it can read is still held to it
        self.assertEqual(code, 1)
        self.assertIn("beat 0 the hit: the effect's light arrives 0.10 s (3 of its frames) after", got["summary"])
        self.assertIn("could not be held to it", got["summary"])

    def test_the_light_as_the_player_draws_it_is_read_as_arriving_on_the_hit_drawing(self):
        # the read (frames through ffmpeg, the timing read's own floor) on the animatic as the PLAYER draws it, drawing
        # by drawing - the fixture's small player reads the PRESET the tool made, by the player's own rules. Each beat
        # must be read as arriving in the frame that FIRST SHOWS its hit drawing - the fixture's own truth
        # (M.shown_frame), never the tool's answer - and the tool's plan must name that same frame.
        # (Made recordings were lights that are there at once: they could not show a hit drawing on the read's line,
        # nor a beat drawn a frame before its stretch. The real run showed the first, a third review the second.)
        slow = timing(arrive=0.25, go=0.25, on=3)
        cases = {
            "ones": ([{"beat": "0 a flash", "t": 0.0, "len": 0.5, "hold": 0.1}, {"beat": "1 a ring", "t": 0.6, "len": 0.5},
                      {"beat": "2 a wall", "t": 1.2, "len": 0.6, "hold": 0.06}],
                     [timing(arrive=0.125, go=0.083, on=1), timing(arrive=0.042, go=0.125, on=1), timing(arrive=0.0, go=0.25, on=1)]),
            "twos": ([{"beat": "0 the dance arc", "t": 0.1, "len": 0.5, "hold": 0.12}, {"beat": "1 a ribbon", "t": 0.7, "len": 1.0},
                      {"beat": "2 embers", "t": 1.75, "len": 0.25}],
                     [timing(arrive=0.0, go=0.167, on=2), timing(arrive=0.5, go=0.083, on=2), timing(arrive=0.083, go=0.083, on=2)]),
            "threes": ([{"beat": "0 a shock wave", "t": 0.05, "len": 0.9}, {"beat": "1 a beam", "t": 1.0, "len": 0.1},
                        {"beat": "2 smoke", "t": 1.3, "len": 0.7, "hold": 0.2}],
                       [slow, timing(arrive=0.0, go=0.04, on=3), timing(arrive=0.125, go=0.25, on=3)]),
            # round times, where a frame's clock is a hair under the beat's time (0.5, 1.0): whole at once
            "round": ([{"beat": "0 a disc", "t": 0.2, "len": 0.2}, {"beat": "1 a flash", "t": 0.5, "len": 0.3, "hold": 0.1},
                       {"beat": "2 a ring", "t": 1.0, "len": 0.4}],
                      [timing(arrive=0.0, go=0.04, on=1), timing(arrive=0.0, go=0.083, on=2), timing(arrive=0.0, go=0.083, on=1)]),
            # a hit on a frame's own instant (4/24 s is five thirtieths), and a small beat right before a big one
            "edges": ([{"beat": "0 a wall", "t": 0.0, "len": 0.5}, {"beat": "1 a spark", "t": 0.6, "len": 0.1},
                       {"beat": "2 a blast", "t": 0.7, "len": 0.8}],
                      [timing(arrive=0.167, go=0.083, on=1), timing(arrive=0.0, go=0.04, on=1), timing(arrive=0.125, go=0.25, on=1)]),
        }
        shares = {"edges": (0.4, 0.021, 0.413)}
        for name, (beats, timings) in cases.items():
            reads = [{"timing": t, "share": share} for t, share in zip(timings, shares.get(name, (0.5, 0.2, 0.35)))]
            rows = A.plan_rows(beats, reads, 2.0)
            preset = A.preset_of(name, rows, "hero", HERO, 2.0, (5.0, 55.0))
            path = M.clips.write(os.path.join(self.root, f"{name}.mp4"), M.drawn_recording(rows, preset), 30)
            _, oi, got, _ = A.our_reads(path, rows, (5.0, 55.0), preset, preset["layers"])
            for k, (r, g) in enumerate(zip(rows, got)):
                truth = M.shown_frame(preset, k, A.drawings_of(r)[2])
                where = (name, r["beat"], r["t"], r["arrive"], r["step"], truth, {x: v for x, v in (g or {}).items() if x != "shot"})
                self.assertIsNotNone(g, where)
                self.assertNotIn("unread", g, where)
                self.assertEqual((g["planned"], g["frame"], g["opens"]), (truth, truth, False), where)
                self.assertTrue(0.8 <= g["share"] / r["share"] <= 1.25, where)

    def test_a_beat_whose_light_is_not_its_own_is_not_read_and_that_is_said(self):
        # a beat a frame and a half before the next has no stretch of the recording that is its own; the next one
        # starts while the first one's shape is still lit (a shape is shown two film frames at least). Neither can be
        # read: each was read through its neighbour (a small beat before a big one failed the animatic's own check,
        # a small one after a big one "arrived" eight frames early). Now nothing is claimed of them - a note on each,
        # the summary says how many were read, and --drift lists them as not held
        M.project(self.root)
        path = os.path.join("assets", "effects", "refs_measured", "fire.chart.json")
        chart = json.load(open(path))
        chart["beats"] = [dict(chart["beats"][0], t=0.0, len=0.05), dict(chart["beats"][1], t=0.05, len=0.4),
                          dict(chart["beats"][1], beat="2 after", t=0.6, len=0.5)]
        json.dump(chart, open(path, "w"))
        _, rows, _ = M.record_animatic("fire", drawn=True)
        code, got = run(["fire", "--no-record"])
        self.assertEqual(code, 0, got["summary"])
        made = json.load(open(os.path.join("build", "vfx", "animatic", "fire.plan.json"), encoding="utf-8"))
        self.assertEqual([b["measured"]["unseen"] for b in made["beats"]], ["short", "mixed", None])
        self.assertIn("under three frames of its own", " | ".join(made["beats"][0]["notes"]))
        self.assertIn("another beat's shape is still lit when this one hits", " | ".join(made["beats"][1]["notes"]))
        self.assertIn("1 of them read back and hitting where the chart says (2 could not be read back", got["summary"])
        self.assertNotIn("each hitting where the chart says", got["summary"])
        shot = os.path.join("build", "vfx", "booth", "fx_play_hero.mp4")
        M.clips.write(shot, M.recording(rows, FX), 30)
        code, got = run(["fire", "--drift", "fx"])
        self.assertEqual((code, got["unseen"]), (0, ["0 the hit", "1 the going"]), got["summary"])
        self.assertIn("(1 beat(s), each within one drawing of it); 2 beat(s) could not be held to it - another beat's shape is "
                      "still lit when they hit / they have under three frames of their own before the next beat: 0 the hit, "
                      "1 the going", got["summary"])
        M.clips.write(shot, M.recording(rows, FX, late={2: 3}), 30)
        self.assertEqual(run(["fire", "--drift", "fx"])[0], 1)             # the beat that CAN be read is still held
        # ... and an animatic of which NO beat could be read back has not been checked at all: not one he can approve
        chart["beats"] = chart["beats"][:2]
        json.dump(chart, open(path, "w"))
        M.record_animatic("fire", drawn=True)
        code, got = run(["fire", "--no-record"])
        self.assertEqual(code, 1)
        self.assertIn("not one beat of it could be read back (they run into each other): the check has checked nothing",
                      got["summary"])
        self.assertTrue(run(["fire", "--check"])[1]["problems"])

    def test_a_recording_is_taken_without_recording_only_when_it_is_this_plans(self):
        M.project(self.root)
        folder = os.path.join("build", "vfx", "animatic")
        mark, recording = os.path.join(folder, "fire.recorded.json"), os.path.join("build", "vfx", "booth", "fire_animatic_play_hero.mp4")
        record = os.path.join(folder, "fire.plan.json")
        self.assertEqual(run(["fire", "--no-record"])[0], 0)
        made = json.load(open(record, encoding="utf-8"))
        self.assertEqual(made["recording_stamp"], json.load(open(mark))["recording"])
        self.assertEqual(json.load(open(mark))["id"], made["id"])
        fresh = run(["fire", "--check"])[1]
        self.assertEqual((fresh["exists"], fresh["stale"]), (True, False))
        # a read that is REFUSED touches nothing that is here. Asked for a view there is no recording of, the tool
        # removed the animatic he may have approved before it found that out (a review, 2026-11-12)
        code, got = run(["fire", "--no-record", "--view", "player"])
        self.assertEqual(code, 1)
        self.assertIn("no recording build/vfx/booth/fire_animatic_play_player.mp4", got["summary"])
        self.assertEqual(run(["fire", "--check"])[1], fresh)
        self.assertEqual(json.load(open(record, encoding="utf-8")), made)
        # (asked about a view the animatic here is not of: there is none of it, and the answer says which one there is)
        other = run(["fire", "--check", "--view", "player"])[1]
        self.assertEqual((other["exists"], other["problems"]), (False, ["the animatic on this machine is of the view hero, not player"]))
        # the chart re-timed AFTER its recording: the recording is the old plan's. It is refused - a review found it
        # given a new record, with the new plan's id over the old video (2026-11-12) - and what is here stays as it
        # was: the OLD plan's record, which now reads out of date
        path = os.path.join("assets", "effects", "refs_measured", "fire.chart.json")
        was = open(path).read()
        chart = json.loads(was)
        chart["beats"][1]["t"] = 0.6
        json.dump(chart, open(path, "w"))
        code, got = run(["fire", "--no-record"])
        self.assertEqual(code, 1)
        self.assertIn("is not of this plan (the chart or the scene's read changed since it was recorded)", got["summary"])
        self.assertIn("without --no-record", got["next_action"])
        self.assertEqual(json.load(open(record, encoding="utf-8")), made)      # not removed, not given the new plan's id
        stale = run(["fire", "--check"])[1]
        self.assertEqual((stale["exists"], stale["stale"]), (True, True))
        self.assertNotEqual(stale["id"], made["id"])
        open(path, "w").write(was)
        self.assertEqual(run(["fire", "--check"])[1], fresh)               # the chart as it was: his animatic again
        self.assertEqual(run(["fire", "--no-record"])[0], 0)
        # another file under the recording's name (recorded again by something else): the mark is not of it
        found, rows = M.rows_of("fire")
        M.clips.write(recording, M.recording(rows, M.blocking_of(found, rows))[:-1], 30)
        stale = run(["fire", "--check"])[1]
        self.assertTrue(stale["stale"])
        self.assertIn("it was recorded again since it was made", stale["why"])
        code, got = run(["fire", "--no-record"])
        self.assertEqual(code, 1)
        self.assertIn("(the recording was replaced since)", got["summary"])
        self.assertTrue(os.path.isfile(record))
        # a recording nothing says anything about; one made for another view
        M.record_animatic("fire")
        self.assertEqual(run(["fire", "--no-record"])[0], 0)
        os.remove(mark)
        self.assertIn("(no recording of it was made by this tool)", run(["fire", "--no-record"])[1]["summary"])
        M.record_animatic("fire")
        said = json.load(open(mark))
        json.dump(dict(said, view="cine"), open(mark, "w"))
        self.assertIn("(it was recorded for another view)", run(["fire", "--no-record"])[1]["summary"])
        json.dump(dict(said, gains="many"), open(mark, "w"))               # a mark that cannot be read is no mark
        self.assertIn("(no recording of it was made by this tool)", run(["fire", "--no-record"])[1]["summary"])
        # a recording that is merely GONE changes nothing he was shown: the animatic is still his (and no read of it
        # can be made again without recording)
        json.dump(said, open(mark, "w"))
        self.assertEqual(run(["fire", "--no-record"])[0], 0)
        os.remove(recording)
        gone = run(["fire", "--check"])[1]
        self.assertEqual((gone["exists"], gone["stale"]), (True, False))
        self.assertIn("no recording", run(["fire", "--no-record"])[1]["summary"])
        self.assertEqual(run(["fire", "--check"])[1], gone)

    def test_a_recording_of_the_animatic_that_is_not_its_plans_fails_its_own_check(self):
        # the animatic as the player draws it, then the same frames a little EARLY or LATE under a mark that still
        # says "this plan's" (a fourth review, 2026-11-12: two frames early passed - the early light read as "opens
        # on light", which is "not read"; and one frame late passed inside a frame's allowance). The plan knows no
        # other beat is lit there: light before a beat starts can only be the beat, early
        M.project(self.root, drawn=True)
        self.assertEqual(run(["fire", "--no-record"])[0], 0)
        found, rows = M.rows_of("fire")
        blocking = M.blocking_of(found, rows)
        frames = M.drawn_recording(rows, blocking)
        shot = os.path.join("build", "vfx", "booth", "fire_animatic_play_hero.mp4")
        mark = json.load(open(os.path.join("build", "vfx", "animatic", "fire.recorded.json")))
        dark = M.clips.frame(0)[None]

        def shifted(by):
            moved = (np.concatenate([frames[-by:], np.repeat(dark, -by, axis=0)]) if by < 0 else
                     np.concatenate([np.repeat(dark, by, axis=0), frames[:len(frames) - by]]))
            M.clips.write(shot, moved, 30)
            A.mark_recorded("fire", "hero", mark["id"], {}, shot)
            return run(["fire", "--no-record"])

        for by in (-2, -1):
            code, got = shifted(by)
            self.assertEqual(code, 1, (by, got["summary"]))
            self.assertIn("before it starts, where its plan has no beat that strong - the recording is not this plan's", got["summary"])
        for by in (1, 2):
            code, got = shifted(by)
            self.assertEqual(code, 1, (by, got["summary"]))
            self.assertIn("its plan shows the hit in frame", got["summary"])
        # ... and --drift holds nothing to an animatic that failed its own check (an effect exactly on plan was
        # called early against it, one five frames late passed)
        M.clips.write(os.path.join("build", "vfx", "booth", "fx_play_hero.mp4"), M.recording(rows, FX), 30)
        code, got = run(["fire", "--drift", "fx"])
        self.assertEqual(code, 1)
        self.assertIn("its animatic failed its own check", got["summary"])
        self.assertEqual(shifted(0)[0], 0)                                 # the plan's own recording: made, and held to
        self.assertEqual(run(["fire", "--drift", "fx"])[0], 0)
        # the animatic is of ONE view: an effect is held to it in that view, and asked for another it says so
        code, got = run(["fire", "--drift", "fx", "--view", "cine"])
        self.assertEqual(code, 1)
        self.assertIn("the animatic here is of the view hero, not cine", got["summary"])
        # a frame rate under 24 a second cannot show every drawing on ones
        for fps in ("20", "0", "-5", "500"):
            self.assertIn("--fps is 24 to 120 frames a second", run(["fire", "--no-record", "--fps", fps])[1]["summary"])

    def test_an_effect_whose_own_clock_leaves_a_beat_no_room_is_named(self):
        # the chart holds the first beat; the animatic's clock stands still there, and the second beat has room after
        # it. The effect dropped that hit-stop: on its own clock the second beat starts two frames after the first.
        # That was "could not be held" and a PASS; the two clocks differ, and that is the fault
        M.project(self.root)
        path = os.path.join("assets", "effects", "refs_measured", "fire.chart.json")
        chart = json.load(open(path))
        chart["beats"] = [dict(chart["beats"][0], t=0.0, len=0.08, hold=0.3), dict(chart["beats"][1], t=0.09, len=0.6)]
        json.dump(chart, open(path, "w"))
        _, rows, _ = M.record_animatic("fire", drawn=True)
        code, got = run(["fire", "--no-record"])
        self.assertEqual(code, 0, got["summary"])
        made = json.load(open(os.path.join("build", "vfx", "animatic", "fire.plan.json"), encoding="utf-8"))
        self.assertEqual([b["measured"]["unseen"] for b in made["beats"]], [None, None])
        M.clips.write(os.path.join("build", "vfx", "booth", "fx_play_hero.mp4"), M.recording(rows, FX), 30)
        code, got = run(["fire", "--drift", "fx"])
        self.assertEqual(code, 1, got["summary"])
        self.assertIn("on the effect's own clock it has under three frames before the next beat", got["summary"])
        self.assertIn("a hit-stop or slow motion of the chart is not in the effect", got["summary"])

    def test_a_number_changed_in_the_record_is_a_changed_animatic(self):
        # --drift holds an effect to the record's own beats (where each hit is, what was measured back). They are part
        # of what "drawn" is the hash of: edit one, and the animatic is no longer the one he was shown - nothing is
        # held to it, and his yes (recorded for the old "drawn") no longer reads as approved
        M.project(self.root)
        self.assertEqual(run(["fire", "--no-record"])[0], 0)
        record = os.path.join("build", "vfx", "animatic", "fire.plan.json")
        made = json.load(open(record, encoding="utf-8"))
        self.assertEqual(run(["fire", "--drift", "fx"])[0], 0)
        self.assertGreater(len(made.get("clock") or {}), 0)
        for change in (lambda m: m["beats"][1].__setitem__("arrive", 0.5), lambda m: m["beats"][1]["measured"].__setitem__("unseen", "opens"),
                       lambda m: m["beats"][0].__setitem__("hit", 0.2),
                       # ... and the clock and the frame rate the record keeps: --drift reads the animatic on them (a
                       # third review took a hit-stop out of the record and a beat five frames late passed)
                       lambda m: m.__setitem__("clock", {"duration": 1.2, "hitstop": [{"at": 0.2, "hold": 0.2}]}),
                       lambda m: m.__setitem__("fps", 24.0), lambda m: m.__setitem__("gains", {"0": 1.3}),
                       lambda m: m.__setitem__("preset", "0" * 12), lambda m: m.__setitem__("extra", 1)):
            edited = json.loads(json.dumps(made))
            change(edited)
            json.dump(edited, open(record, "w", encoding="utf-8"))
            check = run(["fire", "--check"])[1]
            self.assertTrue(check["stale"])
            self.assertNotEqual(check["drawn"], made["drawn"])
            self.assertIn("a number of its record is not the one its record was written for", check["why"])
            code, got = run(["fire", "--drift", "fx"])
            self.assertEqual(code, 1)
            self.assertIn("out of date", got["summary"])
        json.dump(made, open(record, "w", encoding="utf-8"))
        self.assertEqual(run(["fire", "--check"])[1]["drawn"], made["drawn"])

    def test_an_effect_is_read_on_the_clock_it_was_played_on_not_its_files(self):
        # the effect's FILE names its hit-stop by a beat ("at": "hit"); only the expanded preset - the bundle the play
        # command gives the player, build/vfx/play/<run>.json - says when that is. Read from the file the clock crashed
        # (every recorded play of such an effect lost its dailies: a review, 2026-11-12)
        rows, _, _ = M.project(self.root)
        self.assertEqual(run(["fire", "--no-record"])[0], 0)
        preset, shot = os.path.join("assets", "effects", "fx.json"), os.path.join("build", "vfx", "booth", "fx_play_hero.mp4")
        bundle = os.path.join("build", "vfx", "play", "fx.json")
        raw = json.load(open(preset))
        played = dict(raw, hitstop=[{"at": 0.25, "hold": 0.2}])
        json.dump(dict(raw, beats={"hit": 0.25}, hitstop=[{"at": "hit", "hold": 0.2}]), open(preset, "w"))
        os.makedirs(os.path.dirname(bundle))
        json.dump({"name": "fx", "preset": played}, open(bundle, "w"))
        M.clips.write(shot, M.recording(rows, played), 30)                 # recorded on the clock it was played on
        found = A.DC.piece("fx", None, "hero", None)
        self.assertEqual((found["played"]["hitstop"], found["clock_exact"]), ([{"at": 0.25, "hold": 0.2}], True))
        code, got = run(["fire", "--drift", "fx"])
        self.assertEqual((code, got["drifts"]), (0, []), got["summary"])
        self.assertNotIn("CAUTION", got["summary"])
        # a bundle written AFTER the recording (a later play, perhaps of an edited preset): still the better clock,
        # and it is said that it may not be the recording's
        then = os.path.getmtime(shot)
        os.utime(bundle, (then + 60, then + 60))
        code, got = run(["fire", "--drift", "fx"])
        self.assertEqual(code, 0, got["summary"])
        self.assertIn("CAUTION: the clock this recording is read on may not be the one it was recorded on", got["summary"])
        # no bundle at all: the file's own numbers - its named hit-stop is not among them. Said, and never a crash.
        # On that clock the second beat's stretch starts while the first beat's light is still on (the recording held
        # it six frames): the second beat is named, and the CAUTION says the clock itself is in doubt
        os.remove(bundle)
        found = A.DC.piece("fx", None, "hero", None)
        self.assertEqual((found["played"].get("hitstop"), found["clock_exact"]), (None, False))
        code, got = run(["fire", "--drift", "fx"])
        self.assertEqual(code, 1)
        self.assertIn("CAUTION", got["summary"])
        self.assertIn("beat 1 the going:", got["summary"])
        self.assertIn("record it again to be sure", got["summary"])
        # a bundle of the same name from LONG before the recording (another play, another build) is not this
        # recording's. With a preset that is not composed the file says all there is to say: a stale bundle with a
        # hit-stop the effect never had made a beat six frames late pass, "exactly" (a third review, 2026-11-12)
        json.dump(raw, open(preset, "w"))                                  # the plain preset: no beats, no hit-stop
        os.utime(preset, (then - 30, then - 30))
        M.clips.write(shot, M.recording(rows, raw, late={1: 6}), 30)
        json.dump({"name": "fx", "preset": played}, open(bundle, "w"))
        made_at = os.path.getmtime(shot)
        os.utime(bundle, (made_at - 5000, made_at - 5000))
        found = A.DC.piece("fx", None, "hero", None)
        self.assertEqual((found["played"].get("hitstop"), found["clock_exact"]), (None, True))
        code, got = run(["fire", "--drift", "fx"])
        self.assertEqual(code, 1, got["summary"])
        self.assertIn("beat 1 the going: the effect's light arrives 0.20 s (6 of its frames) after the animatic's", got["summary"])
        self.assertNotIn("CAUTION", got["summary"])
        os.utime(bundle, (made_at - 5, made_at - 5))                       # (written just before it: this recording's)
        self.assertEqual(A.DC.piece("fx", None, "hero", None)["played"].get("hitstop"), [{"at": 0.25, "hold": 0.2}])
        # the dailies of such an effect are drawn, on the clock it was played on
        json.dump({"name": "fx", "preset": played}, open(bundle, "w"))
        os.utime(bundle, (then - 5, then - 5))
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            code = A.dailies.main(["fx", "--tile", "320"])
        self.assertEqual(code, 0, said.getvalue()[-300:])

    def test_drift_answers_only_when_there_is_something_true_to_hold_the_effect_against(self):
        M.project(self.root)
        self.assertEqual(run(["fire", "--no-record"])[0], 0)
        made = json.load(open(os.path.join("build", "vfx", "animatic", "fire.plan.json"), encoding="utf-8"))
        said = lambda: run(["fire", "--drift", "fx"])[1]["summary"]  # noqa: E731
        # whose motion it is. Nothing of the owner's on this board: it is "its animatic", never "its approved motion"
        self.assertIn("fx hits where its animatic (which the owner has not approved yet) does", said())
        os.makedirs("board")

        def locks(**rec):
            json.dump({"stages": {"vfx": {"fire": {"animatic": rec}}}}, open(os.path.join("board", "locks.json"), "w"))

        locks(by="owner", words="yes, that timing", id=made["id"], drawn=made["drawn"])
        self.assertIn("fx hits where its approved motion does", said())
        locks(by="Owner (on the page)", words="yes", id=made["id"], drawn="0" * 12)    # he saw other pictures of this plan
        self.assertIn("the owner approved an EARLIER one: not this", said())
        locks(by="owner", words="yes", id="0" * 12, drawn=made["drawn"])               # ... or another plan
        self.assertIn("the owner approved an EARLIER one: not this", said())
        for rec in (dict(by="claude"), dict(by="owner", who="claude"), dict(who="someone")):   # a model's record is none
            locks(words="yes", id=made["id"], drawn=made["drawn"], **rec)
            self.assertIn("which the owner has not approved yet", said(), rec)
        locks(who="owner", words="yes", id=made["id"], drawn=made["drawn"])            # (the kit's older spelling of his)
        self.assertIn("its approved motion", said())
        # (read as the kit's own lock reads it: Lua trims the six ASCII blanks, nothing else - a no-break space before
        # "owner" is not the owner's)
        locks(by=" \towner ", words="yes", id=made["id"], drawn=made["drawn"])
        self.assertIn("its approved motion", said())
        locks(by="\u00a0owner", words="yes", id=made["id"], drawn=made["drawn"])
        self.assertIn("which the owner has not approved yet", said())
        # an effect's name is plain: it is read as a file in the effects folder, and nothing else
        for name in ("../fx", "fx.json", "a/b"):
            code, got = run(["fire", "--drift", name])
            self.assertEqual(code, 1, name)
            self.assertIn("an effect's name is letters, digits, _ and - only", got["summary"])
        # the effect's preset edited after its recording: the recording is of another effect than the one here
        preset, shot = os.path.join("assets", "effects", "fx.json"), os.path.join("build", "vfx", "booth", "fx_play_hero.mp4")
        then = os.path.getmtime(shot)
        os.utime(preset, (then + 30, then + 30))
        code, got = run(["fire", "--drift", "fx"])
        self.assertEqual(code, 1)
        self.assertIn("fx's preset was edited after its recording was made", got["summary"])
        self.assertIn("kit vfx play fx --record", got["next_action"])
        os.utime(preset, (then - 30, then - 30))
        self.assertEqual(run(["fire", "--drift", "fx"])[0], 0)
        # an effect built from another set has no beats of this one
        data = json.load(open(preset))
        json.dump(dict(data, scene={"set": "water"}), open(preset, "w"))
        os.utime(preset, (then - 30, then - 30))
        code, got = run(["fire", "--drift", "fx"])
        self.assertEqual(code, 1)
        self.assertIn("fx is built from the set water, not from fire", got["summary"])
        json.dump(data, open(preset, "w"))
        os.utime(preset, (then - 30, then - 30))
        self.assertEqual(run(["fire", "--drift", "fx"])[0], 0)
        # an animatic that is out of date is nothing to hold an effect against
        path = os.path.join("assets", "effects", "refs_measured", "fire.chart.json")
        chart = json.load(open(path))
        chart["beats"][0]["len"] = 0.3
        json.dump(chart, open(path, "w"))
        code, got = run(["fire", "--drift", "fx"])
        self.assertEqual(code, 1)
        self.assertIn("its animatic on this machine is out of date (the chart was re-timed", got["summary"])

    def test_a_sets_name_is_plain_and_a_chart_that_is_not_one_is_said(self):
        for name in ("fi re", "../fire", "fire.x", 'f"x'):
            code, got = run([name, "--no-record"])
            self.assertEqual(code, 1, name)
            self.assertIn("a set's name is letters, digits, _ and - only", got["summary"])
            check = run([name, "--check"])[1]
            self.assertEqual((check["exists"], check["problems"]), (False, ["a set's name is letters, digits, _ and - only"]))
        M.project(self.root)
        path = os.path.join("assets", "effects", "refs_measured", "fire.chart.json")
        good = json.load(open(path))
        for chart, words in (([1, 2], "no beat chart"), (dict(good, beats="two"), "has no list of beats"),
                             (dict(good, beats=[]), "has no list of beats"), (dict(good, beats=[1, 2]), "has no list of beats"),
                             (dict(good, duration="long"), "has no duration"), (dict(good, duration=0), "has no duration")):
            json.dump(chart, open(path, "w"))
            code, got = run(["fire", "--no-record"])
            self.assertEqual(code, 1, chart)
            self.assertIn(words, got["summary"], chart)
            check = run(["fire", "--check"])[1]                            # (the page's question: answered, not crashed on)
            self.assertEqual(check["exists"], False)
            self.assertIn(words, check["problems"][0])
            self.assertEqual(run(["fire", "--drift", "fx"])[0], 1)
        # a beat the chart leaves no room for: said by name, and nothing is made
        json.dump(dict(good, beats=good["beats"] + [{"beat": "2 too late", "t": 1.2}]), open(path, "w"))
        code, got = run(["fire", "--no-record"])
        self.assertEqual(code, 1)
        self.assertIn("the chart cannot be shown - beat 2 too late starts at 1.20 s, at or after the chart's end", got["summary"])

    def test_a_page_or_a_video_that_could_not_be_made_is_said_and_nothing_can_be_approved(self):
        M.project(self.root)
        with mock.patch.object(A.dailies, "of", side_effect=RuntimeError("no pages today")):
            code, got = run(["fire", "--no-record"])
        self.assertEqual(code, 1)
        self.assertIn("the beat pages were not made (RuntimeError: no pages today)", got["summary"])
        self.assertTrue(run(["fire", "--check"])[1]["problems"])           # the page offers no Approve on it
        with mock.patch.object(A, "side_frames", side_effect=BrokenPipeError("ffmpeg went away")):
            code, got = run(["fire", "--no-record"])
        self.assertEqual(code, 1)
        self.assertIn("the side-by-side video could not be written (BrokenPipeError: ffmpeg went away)", got["summary"])
        self.assertFalse(os.path.exists(os.path.join("build", "vfx", "animatic", "fire_side.mp4")))
        check = run(["fire", "--check"])[1]
        self.assertTrue(check["problems"])
        self.assertFalse(any(p.endswith(".mp4") for p in check["shown"]))
        # a preset the kit's own rules refuse: said before anything is read, and no record is left
        preset = os.path.join("build", "vfx", "animatic", "fire.json")
        was = open(preset, "rb").read()
        with mock.patch.object(A, "preset_of", return_value={"version": 3, "not": "this plan's preset"}), \
                mock.patch.object(A, "refused", return_value=["preset.layers[1].scale: keypoints must start at time 0 and end at time 1"]):
            code, got = run(["fire", "--no-record"])
        self.assertEqual(code, 1)
        self.assertIn("the plan makes a preset the player refuses - preset.layers[1].scale", got["summary"])
        self.assertEqual(run(["fire", "--check"])[1], check)               # (a run that made nothing left what was there)
        self.assertEqual(open(preset, "rb").read(), was)                   # ... the preset too: a refused one never replaces it
        self.assertFalse(os.path.exists(preset + ".new"))
        with mock.patch.object(A, "refused", side_effect=KeyboardInterrupt()):     # stopped mid-check: nothing left behind
            with self.assertRaises(KeyboardInterrupt):
                run(["fire", "--no-record"])
        self.assertFalse(os.path.exists(preset + ".new"))
        self.assertEqual(open(preset, "rb").read(), was)
        # the preset is what the player shows with --animatic: changed by hand, the animatic is no longer the one made
        open(preset, "ab").write(b" ")
        edited = run(["fire", "--check"])[1]
        self.assertTrue(edited["stale"])
        self.assertIn("its preset (what the player shows with --animatic) is not the one it was made from", edited["why"])
        open(preset, "wb").write(was)
        self.assertEqual(run(["fire", "--check"])[1], check)
        # a recorder that fails before it has written anything leaves what is here as well
        with mock.patch.object(A, "record", return_value={"ok": False, "why": "no browser on this machine"}):
            code, got = run(["fire"])
        self.assertEqual(code, 1)
        self.assertIn("the player did not record it (no browser on this machine)", got["summary"])
        self.assertEqual(run(["fire", "--check"])[1], check)
        self.assertEqual(run(["fire", "--no-record"])[0], 0)               # and with nothing in the way it is made

    def test_what_is_missing_is_said_and_nothing_is_left_that_reads_as_an_animatic(self):
        code, got = run(["nothing_of_that_name", "--no-record"])
        self.assertEqual(code, 1)
        self.assertIn("no beat chart", got["summary"])
        check = run(["nothing_of_that_name", "--check"])[1]
        self.assertEqual((check["exists"], check["problems"]), (False, ["no beat chart of nothing_of_that_name"]))
        M.project(self.root)
        os.remove(os.path.join("build", "vfx", "booth", "fire_animatic_play_hero.mp4"))
        code, got = run(["fire", "--no-record"])                           # no recording, and none asked for
        self.assertEqual(code, 1)
        self.assertIn("no recording", got["summary"])
        self.assertFalse(run(["fire", "--check"])[1]["exists"])
        self.assertEqual(run(["fire", "--drift", "fx"])[0], 1)             # no animatic to hold the effect against
        code, got = run(["fire", "--view"])
        self.assertEqual(code, 1)
        self.assertIn("--view needs a value", got["summary"])
        self.assertIn("no camera view", run(["fire", "--no-record", "--view", "no_such_view"])[1]["summary"])


if __name__ == "__main__":
    unittest.main()
