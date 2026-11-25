"""kit/world/studio_shots.py: a world's look stations captured in Roblox Studio (kit world studio). The parts that
need no Studio: the frame the capture cuts out and the field of view that makes it show what the Blender shot shows,
which Studio window is read (another place's is never touched), the colour signals the walk and the capture agree by
(Studio's script cannot call out), the walk's own book-keeping - a picture is never filed under another station's
name - and the script itself (it refuses every place but the scratch place and an older build of it, and reaches for
nothing outside Studio)."""

import math
import os
import sys
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "world"))
import studio_shots as ss  # noqa: E402

N = ss.NEXTS  # the six "a station is coming" colours: station i shows N[i % 6]


def view(colour=(30, 34, 52), size=(640, 360)):
    return Image.new("RGB", size, colour)


def scene(n, size=(640, 360)):
    """a picture of a station: something in it (never one flat colour), different for each n"""
    im = Image.new("RGB", size, (20 + 9 * n, 24, 40))
    im.paste(Image.new("RGB", (size[0] // 3, size[1] // 3), (200, 150 - 20 * n, 60 + 30 * n)), (40 * n + 20, 60))
    return im


class Frame(unittest.TestCase):
    def test_the_frame_stays_clear_of_the_sides_and_is_16_by_9(self):
        for vw, vh in ((1407, 701), (1600, 900), (1920, 1080)):
            left, top, right, bottom = ss.frame_box(vw, vh)
            self.assertGreaterEqual(left, ss.MARGIN - 1, (vw, vh))
            self.assertLessEqual(right, vw - ss.MARGIN + 1, (vw, vh))
            self.assertTrue(0 <= top and bottom <= vh, (vw, vh))
            self.assertAlmostEqual((right - left) / (bottom - top), 16 / 9, delta=0.01)
            self.assertEqual(left, vw - right)  # (in the middle: the camera looks through its centre)

    def test_whatever_the_views_shape_the_corners_are_out_of_the_frame(self):
        # Studio's view cube sits in the top right corner: a frame is clear of it at the sides, or above and below
        for vw, vh in ((1407, 701), (1280, 1024), (1024, 768), (800, 900), (2560, 1300), (3840, 2000)):
            left, top, right, bottom = ss.frame_box(vw, vh)
            sides = left >= ss.MARGIN - 1 and vw - right >= ss.MARGIN - 1
            ends = (top >= ss.MARGIN - 1 and vh - bottom >= ss.MARGIN - 1
                    and left >= ss.MARGIN // 2 - 1 and vw - right >= ss.MARGIN // 2 - 1)
            self.assertTrue(sides or ends, (vw, vh, left, top, right, bottom))
            self.assertTrue(0 <= left and right <= vw and 0 <= top and bottom <= vh, (vw, vh))

    def test_a_tall_view_clears_top_and_bottom_instead_and_the_tool_strip_at_its_side(self):
        left, top, right, bottom = ss.frame_box(600, 900)
        self.assertEqual((left, right), (ss.MARGIN // 2, 600 - ss.MARGIN // 2))
        self.assertGreaterEqual(top, ss.MARGIN)
        self.assertGreaterEqual(900 - bottom, ss.MARGIN)

    def test_the_field_of_view_makes_the_frame_show_exactly_the_station(self):
        for vw, vh, fov in ((1407, 701, 70), (1600, 900, 50), (1280, 1024, 70)):
            cam = ss.fit_fov(fov, vw, vh)
            _, bh = ss.frame_size(vw, vh)
            # what the frame's height spans, seen through the camera's wider view, is the station's own fov
            seen = math.degrees(2 * math.atan(math.tan(math.radians(cam) / 2) * bh / vh))
            self.assertAlmostEqual(seen, fov, places=6)
            self.assertGreater(cam, fov)

    def test_no_margin_and_a_wide_view_keeps_the_stations_own_fov(self):
        self.assertAlmostEqual(ss.fit_fov(70, 1920, 1080, margin=0), 70, places=6)
        self.assertEqual(ss.frame_box(1920, 1080, margin=0), (0, 0, 1920, 1080))


class Windows(unittest.TestCase):
    def test_only_the_scratch_places_own_window_is_ever_picked(self):
        tops = [(11, "MyPlace.2 - Roblox Studio"),
                (22, r"C:\proj\build\worlds\studio\T\KitWorldScratch_T.rbxlx - Roblox Studio"), (33, "Notepad")]
        self.assertEqual(ss.pick_window(tops, "KitWorldScratch_T"), (22, None))
        # once loaded Studio may show the bare file name: the same place
        self.assertEqual(ss.pick_window([(5, "KitWorldScratch_T.rbxlx - Roblox Studio")], "kitworldscratch_t"), (5, None))

    def test_a_place_whose_name_only_starts_the_same_is_another_place(self):
        tops = [(7, r"C:\p\KitWorldScratch_Courtyard.rbxlx - Roblox Studio")]
        h, why = ss.pick_window(tops, "KitWorldScratch_Court")
        self.assertIsNone(h)
        self.assertIn("KitWorldScratch_Courtyard", why)
        both = tops + [(8, r"C:\p\KitWorldScratch_Court.rbxlx - Roblox Studio")]
        self.assertEqual(ss.pick_window(both, "KitWorldScratch_Court"), (8, None))  # (not "2 windows")

    def test_another_places_studio_is_named_and_not_picked(self):
        h, why = ss.pick_window([(11, "MyPlace.2 - Roblox Studio"), (33, "Roblox Studio")], "KitWorldScratch_T")
        self.assertIsNone(h)
        self.assertIn("MyPlace.2", why)
        self.assertIn("never touched", why)
        self.assertIn("not open", why)

    def test_no_studio_and_the_place_open_twice_say_so(self):
        self.assertEqual(ss.pick_window([(1, "Notepad")], "KitWorldScratch_T"), (None, "Roblox Studio is not open"))
        h, why = ss.pick_window([(1, "KitWorldScratch_T.rbxlx - Roblox Studio"),
                                 (2, r"D:\x\KitWorldScratch_T.rbxlx - Roblox Studio")], "KitWorldScratch_T")
        self.assertIsNone(h)
        self.assertIn("2 Roblox Studio windows", why)


class Signals(unittest.TestCase):
    def window(self, colour, notice=False):
        """a Studio window with its 3D view (at 10, 170, 1407 x 701) covered by a signal colour"""
        win = Image.new("RGB", (1936, 1096), (36, 38, 44))
        win.paste(Image.new("RGB", (1407, 701), colour), (10, 170))
        if notice:  # (a plugin's own notice over a corner of the view)
            win.paste(Image.new("RGB", (330, 70), (20, 110, 230)), (1080, 790))
        return win

    def test_the_start_signal_says_where_the_3d_view_is(self):
        self.assertEqual(ss.flash_box(self.window(ss.START), ss.START), (10, 170, 1417, 871))
        self.assertEqual(ss.flash_box(self.window(ss.START, notice=True), ss.START), (10, 170, 1417, 871))

    def test_a_scene_or_a_small_patch_is_no_signal(self):
        self.assertIsNone(ss.flash_box(self.window((90, 60, 40)), ss.START))
        win = Image.new("RGB", (1936, 1096), (36, 38, 44))
        win.paste(Image.new("RGB", (120, 80), ss.START), (400, 400))  # (a magenta thing in the world, not the cover)
        self.assertIsNone(ss.flash_box(win, ss.START))

    def test_every_signal_is_told_apart_and_a_view_is_none(self):
        self.assertEqual(ss.signal(view(ss.START)), ("start", None))
        self.assertEqual(ss.signal(view(ss.END)), ("end", None))
        self.assertEqual([ss.signal(view(c)) for c in N], [("next", i) for i in range(len(N))])
        self.assertIsNone(ss.signal(scene(1)))
        self.assertIsNone(ss.signal(view((250, 240, 60))))  # (a yellowish wall is not the yellow signal)
        # no two signals are close enough to be read as each other
        every = [ss.START, ss.END, *N]
        for a in every:
            for b in every:
                if a is not b:
                    self.assertGreaterEqual(max(abs(x - y) for x, y in zip(a, b)), 100, (a, b))


class TheWalk(unittest.TestCase):
    STATIONS = ("eye_1", "eye_2", "eye_3")

    def run_walk(self, frames, stations=STATIONS):
        walk, saved = ss.Walk(stations), []
        for f in frames:
            saved += [(name, img, ok) for name, img, ok in walk.feed(f)]
        return walk, saved

    def names(self, saved):
        return [(name, ok) for name, _img, ok in saved]

    def test_each_station_is_saved_once_two_reads_agree(self):
        a, b, c = scene(1), scene(2), scene(3)
        walk, saved = self.run_walk([view(ss.START), view(ss.START), view(N[0]), view(N[0]), a, a, a,
                                     view(N[1]), b, b, view(N[2]), c, c, view(ss.END)])
        self.assertEqual(self.names(saved), [("eye_1", True), ("eye_2", True), ("eye_3", True)])
        self.assertTrue(walk.over)
        self.assertIs(saved[1][1], b)

    def test_a_view_that_never_settles_is_still_saved_and_flagged(self):
        walk, saved = self.run_walk([view(ss.START), view(N[0]), scene(1), scene(3), scene(1), view(N[1]),
                                     scene(2), scene(2), view(ss.END)])
        self.assertEqual(self.names(saved), [("eye_1", False), ("eye_2", True)])

    def test_a_signal_nobody_read_loses_that_picture_and_never_shifts_the_names(self):
        # eye_2's signal was missed (a slow read, a busy GPU): its view b came with no signal before it. b must not be
        # filed at all, and c - announced by eye_3's own colour - is eye_3, not eye_2
        a, b, c = scene(1), scene(2), scene(3)
        walk, saved = self.run_walk([view(ss.START), view(N[0]), a, a, b, b, view(N[2]), c, c, view(ss.END)])
        self.assertEqual(self.names(saved), [("eye_1", True), ("eye_3", True)])
        self.assertIs(saved[1][1], c)

    def test_a_hold_nobody_read_does_not_file_the_next_view_under_its_name(self):
        # nothing was read during eye_1's hold: the first clean view on screen is eye_2's
        b = scene(2)
        walk, saved = self.run_walk([view(ss.START), view(N[0]), view(N[1]), b, b, view(ss.END)])
        self.assertEqual(self.names(saved), [("eye_2", True)])
        self.assertIs(saved[0][1], b)

    def test_a_signal_seen_twice_is_one_signal(self):
        # a read in the middle of eye_1's signal did not see it (a plugin's notice over the view): still eye_1 coming,
        # and what that read showed is not eye_1's picture
        a = scene(1)
        walk, saved = self.run_walk([view(ss.START), view(N[0]), scene(3), view(N[0]), a, a, view(ss.END)])
        self.assertEqual(self.names(saved), [("eye_1", True)])
        self.assertIs(saved[0][1], a)

    def test_more_than_six_stations_keep_their_own_names(self):
        stations = tuple(f"s{i}" for i in range(9))
        frames = [view(ss.START)]
        for i in range(9):
            frames += [view(N[i % 6]), scene(i % 5), scene(i % 5)]
        walk, saved = self.run_walk(frames + [view(ss.END)], stations)
        self.assertEqual(self.names(saved), [(f"s{i}", True) for i in range(9)])

    def test_a_colour_for_a_station_that_does_not_exist_files_nothing(self):
        a = scene(1)
        walk, saved = self.run_walk([view(ss.START), view(N[4]), a, a, view(ss.END)], stations=("eye_1", "eye_2"))
        self.assertEqual(saved, [])

    def test_nothing_is_saved_before_the_start_signal_or_after_the_end(self):
        a = scene(1)
        walk, saved = self.run_walk([a, a, view(N[0]), a, a])
        self.assertEqual((saved, walk.started), ([], False))
        walk, saved = self.run_walk([view(ss.START), view(N[0]), a, a, view(ss.END), view(N[1]), a, a])
        self.assertEqual(self.names(saved), [("eye_1", True)])

    def test_a_signal_colour_is_never_saved_as_a_picture(self):
        walk, saved = self.run_walk([view(ss.START), view(N[0]), view(N[1]), view(N[2]), view(ss.END)])
        self.assertEqual(saved, [])


class Script(unittest.TestCase):
    STATIONS = [{"name": "eye_1", "cam": [4.211, 8.5, -41.979], "target": [1.131, 7.0, 9.93], "fov": 70,
                 "rig": [3.5, 1.0, -30.0]},
                {"name": "over", "cam": [-100.5, 154.7, 95.5], "target": [0.0, -0.5, 2.5], "fov": 50, "rig": None}]

    def code(self, text):
        """the script without its comments (they may name what it avoids)"""
        return "\n".join(line.split("--")[0] for line in text.splitlines())

    def test_it_carries_every_stations_camera_in_roblox_axes(self):
        text = ss.snippet(self.STATIONS, "GothicCourtyard", "abc123")
        self.assertIn('{ name = "eye_1", cam = Vector3.new(4.211, 8.5, -41.979), target = Vector3.new(1.131, 7, 9.93), '
                      'fov = 70, rig = Vector3.new(3.5, 1, -30) },', text)
        self.assertIn('{ name = "over", cam = Vector3.new(-100.5, 154.7, 95.5), target = Vector3.new(0, -0.5, 2.5), fov = 50 },', text)
        self.assertNotRegex(text, r"@[A-Z]+@")  # (no placeholder left unfilled)

    def test_it_refuses_another_place_and_an_older_build_before_touching_anything(self):
        text = ss.snippet(self.STATIONS, "GothicCourtyard", "abc123")
        self.assertIn('local WORLD, BUILD, ASPECT, MARGIN = "GothicCourtyard", "abc123",', text)
        place = text.index("marker.Value == WORLD")
        self.assertIn("REFUSED", text[place:place + 320])
        build = text.index("built.Value == BUILD")
        self.assertIn("REFUSED", text[build:build + 320])
        self.assertIn("OLDER build", text[build:build + 320])
        for touch in ("SetAttribute", "Instance.new", "camera.CFrame =", "applyAll", "CoreGui"):
            self.assertGreater(self.code(text).index(touch), self.code(text).index("built.Value == BUILD"), touch)

    def test_it_calls_nothing_outside_studio_and_saves_nothing(self):
        code = self.code(ss.snippet(self.STATIONS, "GothicCourtyard", "abc123"))
        for banned in ("HttpService", "GetAsync", "PostAsync", "RequestAsync", "http://", "SavePlace", "PublishTo",
                       "InsertService", "MarketplaceService", "loadstring"):
            self.assertNotIn(banned, code, banned)

    def test_the_signals_the_margin_and_the_time_are_the_ones_the_capture_reads(self):
        text = ss.snippet(self.STATIONS, "T")
        for colour in (ss.START, ss.END, *ss.NEXTS):
            self.assertIn("Color3.fromRGB(%d, %d, %d)" % colour, text)
        self.assertIn("flash(NEXTS[(i - 1) % #NEXTS + 1])", text)  # (station i, counted from 1: N[(i - 1) % 6])
        self.assertIn(", %d\n" % ss.MARGIN, text.split("local FLASH")[0])
        # (the same box as frame_size: both of its ways)
        self.assertIn("math.min(vs.X - 2 * MARGIN, vs.Y * ASPECT)", text)
        self.assertIn("math.min(vs.X - MARGIN, (vs.Y - 2 * MARGIN) * ASPECT)", text)
        self.assertEqual(ss.walk_seconds(2), ss.SETTLE + ss.FLASH + 2 * (ss.FLASH + ss.MOVE + ss.HOLD) + ss.FLASH)
        self.assertIn(", %d\n" % math.ceil(ss.walk_seconds(2)), text.split("local NEXTS")[0])

    def test_the_end_signal_also_comes_after_an_error(self):
        # (or the capture would wait out its whole time for a walk that has stopped)
        text = ss.snippet(self.STATIONS, "T")
        walk_ends = text.index("local ok, err = pcall(function()")
        after = text[text.index("\tend)\n", walk_ends):]
        self.assertIn("pcall(flash, Color3.fromRGB(%d, %d, %d))" % ss.END, after)
        self.assertLess(after.index("pcall(flash"), after.index('marker:SetAttribute("Status"'))

    def test_a_name_outside_ascii_is_still_a_luau_string(self):
        stations = [dict(self.STATIONS[0], name="at_Château")]
        text = ss.snippet(stations, 'Vieille "Cour"')
        self.assertIn('name = "at_Château"', text)
        self.assertIn('"Vieille \\"Cour\\""', text)
        self.assertNotRegex(text, r"\\u[0-9a-fA-F]{4}")  # (JSON's escape: Luau reads \u{...} only)
        self.assertEqual(ss.lua_str("a\x01b"), '"a\\u{0001}b"')


if __name__ == "__main__":
    unittest.main()
