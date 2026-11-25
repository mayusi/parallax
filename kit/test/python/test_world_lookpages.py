"""kit/world/lookpages.py: a world's look, one page per station (kit world look / kit world studio). The owner on an
unlabelled frame (2026-11-11): "I don't know what I'm exactly looking at" - so a page names its station and what it
shows, lays the reference still above ours at the same framing and full size, pairs a station only with a still
chosen for it (or says "by order", or "none"), never shows a still marked never, and a Studio pane with no capture
says so in words instead of showing a stand-in."""

import json
import os
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "world"))
import lookpages  # noqa: E402

RED, GREEN, BLUE = (200, 30, 30), (30, 190, 60), (40, 60, 210)
PANE = (320, 180)
HEAD, BAND, GAP, M = 196, 68, 18, 24  # (the page's own layout: lookpages.page)


def near(a, b, tol=12):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


class Pairing(unittest.TestCase):
    def setUp(self):
        self.refs = tempfile.mkdtemp()
        for f in ("a_street.jpg", "b_plaza.jpg", "c_stair.jpg", "d_gate.jpg", "e_shrine.jpg", "z_never.jpg"):
            Image.new("RGB", (64, 36), RED).save(os.path.join(self.refs, f))

    def pairing(self, spec):
        with open(os.path.join(self.refs, "stations.json"), "w", encoding="utf-8") as fh:
            json.dump(spec, fh)

    def test_no_pairing_file_takes_the_first_four_stills_in_order_and_says_so(self):
        got = lookpages.pair_refs(["eye_1", "eye_2", "view_x", "at_y", "over"], self.refs)
        self.assertEqual([got[n]["file"] for n in ("eye_1", "eye_2", "view_x", "at_y")],
                         ["a_street.jpg", "b_plaza.jpg", "c_stair.jpg", "d_gate.jpg"])
        self.assertEqual({v["how"] for v in got.values()}, {"order"})
        # a fifth station goes round the first four again: the fifth and sixth stills stay off every page
        self.assertEqual(got["over"]["file"], "a_street.jpg")
        self.assertNotIn("z_never.jpg", [v["file"] for v in got.values()])
        self.assertNotIn("e_shrine.jpg", [v["file"] for v in got.values()])

    def test_a_named_pair_wins_and_the_rest_take_unused_stills(self):
        self.pairing({"never": ["z_never.jpg"], "stations": {
            "eye_2": {"ref": "a_street.jpg", "ref_shows": "the source: a street", "ref_crop": [0, 0, 0.5, 0.5]}}})
        got = lookpages.pair_refs(["eye_1", "eye_2", "over"], self.refs)
        self.assertEqual((got["eye_2"]["file"], got["eye_2"]["how"], got["eye_2"]["shows"], got["eye_2"]["crop"]),
                         ("a_street.jpg", "named", "the source: a street", [0, 0, 0.5, 0.5]))
        self.assertEqual((got["eye_1"]["file"], got["eye_1"]["how"]), ("b_plaza.jpg", "order"))  # (a_ is taken)
        self.assertEqual(got["over"]["file"], "c_stair.jpg")

    def test_a_still_marked_never_is_never_paired_even_when_named(self):
        self.pairing({"never": ["z_never.jpg"], "stations": {"eye_1": {"ref": "z_never.jpg"}}})
        got = lookpages.pair_refs(["eye_1", "s2", "s3", "s4", "s5", "s6", "s7"], self.refs)
        self.assertNotIn("z_never.jpg", [v["file"] for v in got.values()])
        self.assertEqual(got["eye_1"]["how"], "order")

    def test_a_view_with_no_still_says_none_and_why(self):
        self.pairing({"stations": {"view_inside": {"ref": "none", "ref_shows": "the source shows no room"}}})
        got = lookpages.pair_refs(["view_inside", "eye_1"], self.refs)
        self.assertEqual((got["view_inside"]["file"], got["view_inside"]["how"], got["view_inside"]["shows"]),
                         (None, "none", "the source shows no room"))
        self.assertEqual(got["eye_1"]["file"], "a_street.jpg")

    def test_a_world_with_no_stills_pairs_nothing(self):
        got = lookpages.pair_refs(["eye_1"], tempfile.mkdtemp())
        self.assertEqual((got["eye_1"]["file"], got["eye_1"]["how"]), (None, "none"))

    def test_never_holds_whatever_the_letter_case(self):
        # (a Windows folder does not tell Z_NEVER.JPG from z_never.jpg)
        self.pairing({"never": ["Z_NEVER.JPG"], "stations": {"eye_1": {"ref": "z_never.jpg"}}})
        got = lookpages.pair_refs([f"s{i}" for i in range(8)] + ["eye_1"], self.refs)
        self.assertNotIn("z_never.jpg", [v["file"] for v in got.values()])

    def test_a_pairing_file_that_cannot_be_read_shows_no_still_and_says_why(self):
        # its "never" list cannot be read either: a typo must not put a banned still on a page
        with open(os.path.join(self.refs, "stations.json"), "w", encoding="utf-8") as fh:
            fh.write('{ "never": ["z_never.jpg"], "stations": { ')
        got = lookpages.pair_refs(["eye_1", "over"], self.refs)
        self.assertEqual({v["file"] for v in got.values()}, {None})
        _, never, has_file, problem = lookpages.read_pairing(self.refs)
        self.assertEqual((never, has_file), (None, True))
        self.assertIn("cannot be read", problem)
        with open(os.path.join(self.refs, "stations.json"), "w", encoding="utf-8") as fh:
            fh.write('["z_never.jpg"]')  # (not an object)
        self.assertEqual({v["file"] for v in lookpages.pair_refs(["eye_1"], self.refs).values()}, {None})

    def test_a_typo_in_one_entry_costs_that_entry_only(self):
        self.pairing({"never": "z_never.jpg", "stations": {  # (never as a word, not a list: no still is banned by it)
            "eye_1": {"ref": 7},  # (not a name)
            "eye_2": {"ref": "b_plaza.jpg", "ref_crop": "0,0,1,1"},  # (a crop as a string)
            "over": {"ref": "c_stair.jpg", "ref_crop": [0, 0, 1]},  # (three numbers)
            "view_x": "a_street.jpg"}})  # (a string, not an entry)
        got = lookpages.pair_refs(["eye_1", "eye_2", "over", "view_x"], self.refs)
        self.assertEqual((got["eye_2"]["file"], got["eye_2"]["crop"]), ("b_plaza.jpg", None))
        self.assertEqual((got["over"]["file"], got["over"]["crop"]), ("c_stair.jpg", None))
        self.assertEqual((got["eye_1"]["how"], got["view_x"]["how"]), ("order", "order"))


class Cover(unittest.TestCase):
    def test_the_pane_is_filled_and_a_crop_takes_its_part_first(self):
        im = Image.new("RGB", (400, 100), RED)
        im.paste(Image.new("RGB", (200, 100), BLUE), (200, 0))  # (left half red, right half blue)
        whole = lookpages.cover(im, 160, 90)
        self.assertEqual(whole.size, (160, 90))
        self.assertTrue(near(whole.getpixel((40, 45)), RED) and near(whole.getpixel((120, 45)), BLUE))
        left = lookpages.cover(im, 160, 90, [0, 0, 0.5, 1])
        self.assertTrue(near(left.getpixel((10, 45)), RED) and near(left.getpixel((150, 45)), RED))

    def test_a_crop_that_is_not_four_numbers_or_takes_nothing_is_ignored(self):
        im = Image.new("RGB", (400, 100), RED)
        for bad in ("0,0,1,1", [0, 0, 1], 5, [0, 0, "x", 1], [0.5, 0.5, 0.5, 0.5], [0.9, 0, 0.1, 1], None):
            self.assertEqual(lookpages.cover(im, 160, 90, bad).size, (160, 90), bad)
            self.assertIsNone(lookpages.good_crop(bad), bad)
        self.assertEqual(lookpages.good_crop([-1, 0, 2, 1]), [0.0, 0.0, 1.0, 1.0])  # (held inside the picture)
        # a still of one pixel has no part to take: the whole of it fills the pane
        self.assertEqual(lookpages.cover(Image.new("RGB", (1, 1), BLUE), 160, 90, [0, 0, 0.5, 0.5]).size, (160, 90))


class Pages(unittest.TestCase):
    def setUp(self):
        self.look = tempfile.mkdtemp()
        self.refs = tempfile.mkdtemp()
        self.studio = tempfile.mkdtemp()
        stations = [{"name": "eye_1", "kind": "spawn", "title": "spawn 1", "about": "what a player sees first",
                     "cam": [0, 8, -40], "target": [0, 7, 10], "fov": 70, "rig": [0, 1, -30]},
                    {"name": "over", "kind": "over", "title": "the whole place from above", "about": "from a corner",
                     "cam": [-100, 150, 90], "target": [0, 0, 0], "fov": 50, "rig": None}]
        with open(os.path.join(self.look, "stations.json"), "w", encoding="utf-8") as fh:
            json.dump({"world": "T", "res": [1920, 1080], "stations": stations}, fh)
        for s in stations:
            Image.new("RGB", (640, 360), GREEN).save(os.path.join(self.look, s["name"] + ".png"))
        with open(os.path.join(self.look, "eye_1.labels.json"), "w", encoding="utf-8") as fh:
            json.dump({"labels": [{"text": "the cathedral", "px": [10, 10], "seen": True},
                                  {"text": "lamp 2", "px": [-5, 10], "seen": False}]}, fh)
        Image.new("RGB", (640, 360), RED).save(os.path.join(self.refs, "a_ref.jpg"))

    def centre(self, page, pane):
        """the colour at the middle of the page's n-th pane (0 = the top one)"""
        with Image.open(page) as im:
            return im.convert("RGB").getpixel((M + PANE[0] // 2, HEAD + pane * (BAND + PANE[1] + GAP) + BAND + PANE[1] // 2))

    def test_a_pair_is_the_reference_above_ours_one_page_a_station(self):
        r = lookpages.build(self.look, "T", refs_dir=self.refs, pane=PANE)
        self.assertEqual(r["status"], "pass")
        self.assertEqual([os.path.basename(p) for p in r["pages"]], ["01_eye_1.png", "02_over.png"])
        with Image.open(r["pages"][0]) as im:
            self.assertEqual(im.size, (PANE[0] + 2 * M, HEAD + 2 * (BAND + PANE[1] + GAP) + 54))
        self.assertTrue(near(self.centre(r["pages"][0], 0), RED), "the reference still is the top pane")
        self.assertTrue(near(self.centre(r["pages"][0], 1), GREEN), "ours in Blender is under it")
        self.assertTrue(r["look"].startswith("LOOK: "))
        self.assertIn("2 station page(s)", r["look"])
        self.assertIn(os.path.join(self.look, "pages").replace(os.sep, "/"), r["look"])
        with open(os.path.join(self.look, "pages", "index.json"), encoding="utf-8") as fh:
            rows = json.load(fh)["pages"]
        self.assertEqual([(x["station"], x["reference"], x["paired"]) for x in rows],
                         [("eye_1", "a_ref.jpg", "order"), ("over", "a_ref.jpg", "order")])
        self.assertEqual(r["by_order"], ["eye_1", "over"])  # (said, not hidden: nobody chose these pairs)

    def test_a_station_says_what_it_shows_from_the_labels_its_camera_sees(self):
        with open(os.path.join(self.look, "stations.json"), encoding="utf-8") as fh:
            station = json.load(fh)["stations"][0]
        title, shows, in_view = lookpages.station_words(station, self.look, {})
        self.assertEqual((title, shows, in_view), ("spawn 1", "what a player sees first", ["the cathedral"]))
        title, shows, _ = lookpages.station_words(station, self.look, {"eye_1": {"title": "the lane in", "shows": "ours: the lane"}})
        self.assertEqual((title, shows), ("the lane in", "ours: the lane"))  # (the pairing file's own words win)

    def test_three_panes_and_a_missing_capture_says_so_in_words(self):
        os.makedirs(os.path.join(self.studio, "shots"))
        Image.new("RGB", (1246, 701), BLUE).save(os.path.join(self.studio, "shots", "eye_1.png"))
        with open(os.path.join(self.studio, "shots", "capture.json"), "w", encoding="utf-8") as fh:
            json.dump({"stations": {"eye_1": {"native": [1246, 701], "settled": True}}}, fh)
        r = lookpages.build(self.look, "T", refs_dir=self.refs, studio_dir=self.studio,
                            studio_why="Roblox Studio is not open", pane=PANE)
        self.assertEqual((r["status"], r["captured"]), ("pass", 1))
        self.assertTrue(all(p.startswith(self.studio.replace(os.sep, "/")) for p in r["pages"]))
        with Image.open(r["pages"][0]) as im:
            self.assertEqual(im.size[1], HEAD + 3 * (BAND + PANE[1] + GAP) + 54)
        self.assertTrue(near(self.centre(r["pages"][0], 0), RED))
        self.assertTrue(near(self.centre(r["pages"][0], 1), GREEN))
        self.assertTrue(near(self.centre(r["pages"][0], 2), BLUE), "the Studio capture is the third pane")
        # the station with no capture: its pane is the hatched "not captured" panel - never a copy of another pane
        got = self.centre(r["pages"][1], 2)
        self.assertFalse(near(got, GREEN) or near(got, RED) or near(got, BLUE), got)
        self.assertIn("1 of 2 captured", r["summary"])
        self.assertIn("ours in Roblox Studio (1 of 2 captured)", r["look"])

    def test_a_broken_pairing_file_still_makes_the_pages_and_says_so_on_them(self):
        with open(os.path.join(self.refs, "stations.json"), "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        r = lookpages.build(self.look, "T", refs_dir=self.refs, pane=PANE)
        self.assertEqual((r["status"], len(r["pages"])), ("pass", 2))
        self.assertIn("NO reference still shown", r["summary"])
        self.assertIn("cannot be read", r["pairing_problem"])
        self.assertFalse(near(self.centre(r["pages"][0], 0), RED), "no still is shown while its never list is unread")
        self.assertTrue(near(self.centre(r["pages"][0], 1), GREEN))

    def test_no_stations_is_a_failure_that_names_the_command(self):
        r = lookpages.build(tempfile.mkdtemp(), "T")
        self.assertEqual(r["status"], "fail")
        self.assertIn("kit world look T", r["next_action"])

    def test_a_station_that_is_gone_leaves_no_page_behind(self):
        r = lookpages.build(self.look, "T", refs_dir=self.refs, pane=PANE)
        self.assertEqual(len(r["pages"]), 2)
        with open(os.path.join(self.look, "stations.json"), encoding="utf-8") as fh:
            spec = json.load(fh)
        spec["stations"] = spec["stations"][:1]
        with open(os.path.join(self.look, "stations.json"), "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        lookpages.build(self.look, "T", refs_dir=self.refs, pane=PANE)
        self.assertEqual(sorted(f for f in os.listdir(os.path.join(self.look, "pages")) if f.endswith(".png")),
                         ["01_eye_1.png"])


class Text(unittest.TestCase):
    def test_a_long_line_is_cut_with_an_ellipsis_never_run_off_the_page(self):
        from PIL import ImageDraw

        d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        text, f = lookpages.fit_text(d, "In view: " + "; ".join(f"lamp {i}: the stair's foot" for i in range(30)), 400, 30)
        self.assertLessEqual(d.textlength(text, font=f), 400)
        self.assertTrue(text.endswith("..."))
        rows = lookpages.wrap(d, "one two three four five six seven eight nine ten " * 6, lookpages.font(20), 200, 2)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(d.textlength(r, font=lookpages.font(20)) <= 200 for r in rows))


if __name__ == "__main__":
    unittest.main()
