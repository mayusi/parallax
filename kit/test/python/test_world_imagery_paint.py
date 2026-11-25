"""test_world_imagery_paint.py - THE PAINTER READS AN AERIAL PICTURE (kit/world/terrain.py --imagery; the owner's method
list: "Satellite imagery-based terrain"). On a small land made for it - a real-land design whose "DEM" and whose
picture are written here by hand, no network - the painted roles are held to the picture: soil takes what the picture
shows, cliffs and scree stay the land's own, a picture of another box is refused.
Not claimed here: that a real place's read is right (see test_world_imagery.py and the audit page)."""
import contextlib
import importlib.util
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
WORLD = os.path.join(HERE, "..", "..", "world")
sys.path.insert(0, WORLD)
_spec = importlib.util.spec_from_file_location("kit_world_terrain", os.path.join(WORLD, "terrain.py"))
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)

BBOX = [-119.66, 37.715, -119.53, 37.765]
ROLE = {name: i for i, name in enumerate(T.ROLES)}
GREEN, GREY, WHITE, BLUE, BROWN = (70, 120, 50), (140, 140, 140), (250, 250, 250), (30, 60, 120), (120, 90, 60)


class Land(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kit_imagery_")
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def place(self, heights, picture, picture_bbox=None, sidecar=True):
        """a design with its DEM (heights in metres, [row = south-north, col = west-east], row 0 north) and a
        picture of the same box (or of another)"""
        Image.fromarray(np.asarray(heights, dtype=np.float32), "F").save(os.path.join(self.dir, "land.dem.tif"))
        with open(os.path.join(self.dir, "land.dem.json"), "w", encoding="utf-8") as fh:
            json.dump({"bbox": BBOX, "width_m": 1000.0, "height_m": 1000.0}, fh)
        Image.fromarray(np.asarray(picture, dtype=np.uint8), "RGB").save(os.path.join(self.dir, "land.img.png"))
        if sidecar:
            with open(os.path.join(self.dir, "land.img.json"), "w", encoding="utf-8") as fh:
                json.dump(dict({"bbox": picture_bbox or BBOX, "credit": "a test picture", "covers": {"side_m": 1000.0}},
                               **(self.sidecar_more or {})), fh)
        with open(os.path.join(self.dir, "land.design.json"), "w", encoding="utf-8") as fh:
            json.dump({"dem": {"file": "land.dem.tif", "relief": self.relief, "blur": 0}}, fh)

    relief = 4
    sidecar_more = None

    def run_painter(self, *more, design=True):
        out = os.path.join(self.dir, "land.hm.json")
        argv = [out, "--size", "128", "--erosion", "0", "--thermal", "0", "--stream", "0"]
        if design:
            argv += ["--design", os.path.join(self.dir, "land.design.json")]
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            code = T.main(argv + list(more))
        verdict = json.loads(said.getvalue().strip().splitlines()[-1])
        data = None
        if code == 0:
            with open(out, encoding="utf-8") as fh:
                data = json.load(fh)
        roles = None
        if data:
            n = data["nx"]
            roles = np.array([int(c) for c in data["paint"]]).reshape(n, n)  # [x, z]: x east, z south
        return code, verdict, data, roles

    def picture(self):
        return os.path.join(self.dir, "land.img.png")

    def flat(self):
        h = np.zeros((33, 33))
        h[0, 0] = 1  # (a land needs some relief to be a land)
        return h


class Painted(Land):
    def test_the_soil_takes_what_the_picture_shows_where_it_shows_it(self):
        pic = np.zeros((40, 40, 3), dtype=np.uint8)
        pic[:, :20] = GREEN  # (the west half)
        pic[:, 20:] = GREY  # (the east half)
        pic[:10, 30:] = WHITE  # (the north-east corner)
        pic[30:, :10] = BROWN  # (the south-west corner)
        self.place(self.flat(), pic)
        code, verdict, data, roles = self.run_painter("--imagery", self.picture())
        self.assertEqual(code, 0, verdict)
        n = roles.shape[0]
        self.assertEqual(roles[n // 8, n // 2], ROLE["meadow"])  # (west, middle)
        self.assertEqual(roles[n * 5 // 8, n // 2], ROLE["rock"])  # (east, middle)
        self.assertEqual(roles[n * 7 // 8, n // 8], ROLE["snow"])  # (east, north: z small)
        self.assertEqual(roles[n // 8, n * 7 // 8], ROLE["dirt"])  # (west, south)
        # the picture it read is kept with the land: its file, its box, its credit
        self.assertEqual(data["imagery"], {"file": "land.img.png", "credit": "a test picture", "bbox": BBOX})
        # ... and without the picture the same land is one meadow (the rule's own answer for flat soil)
        code, verdict, data, plain = self.run_painter()
        self.assertEqual(code, 0)
        self.assertNotIn("imagery", data)
        self.assertEqual(plain[n * 5 // 8, n // 2], ROLE["meadow"])
        self.assertTrue((plain != roles).mean() > 0.4)

    def test_the_designs_own_word_is_read_and_the_command_line_wins(self):
        pic = np.zeros((40, 40, 3), dtype=np.uint8)
        pic[:, :] = GREY
        self.place(self.flat(), pic)
        with open(os.path.join(self.dir, "land.design.json"), "w", encoding="utf-8") as fh:
            json.dump({"dem": {"file": "land.dem.tif", "relief": 4, "blur": 0}, "paint": {"imagery": "land.img.png"}}, fh)
        code, verdict, data, roles = self.run_painter()
        self.assertEqual(code, 0, verdict)
        self.assertTrue((roles == ROLE["rock"]).mean() > 0.9)
        self.assertEqual(data["imagery"]["file"], "land.img.png")
        # the command line's picture wins over the design's (here the design names one that is not there)
        with open(os.path.join(self.dir, "land.design.json"), "w", encoding="utf-8") as fh:
            json.dump({"dem": {"file": "land.dem.tif", "relief": 4, "blur": 0}, "paint": {"imagery": "nope.img.png"}}, fh)
        code, verdict, data, roles = self.run_painter("--imagery", self.picture())
        self.assertEqual(code, 0, verdict)
        self.assertTrue((roles == ROLE["rock"]).mean() > 0.9)
        # a design's word that is no file's name is refused
        for word in (5, "", True, ["land.img.png"]):
            with open(os.path.join(self.dir, "land.design.json"), "w", encoding="utf-8") as fh:
                json.dump({"dem": {"file": "land.dem.tif", "relief": 4, "blur": 0}, "paint": {"imagery": word}}, fh)
            code, verdict, _, _ = self.run_painter()
            self.assertEqual(code, 1, (word, verdict))
            self.assertIn("imagery is a picture's file", verdict["summary"])

    def test_what_the_picture_reads_as_water_says_nothing(self):
        pic = np.zeros((40, 40, 3), dtype=np.uint8)
        pic[:, :] = BLUE
        self.place(self.flat(), pic)
        code, verdict, data, roles = self.run_painter("--imagery", self.picture())
        self.assertEqual(code, 0, verdict)
        _, _, _, plain = self.run_painter()
        self.assertTrue((roles == plain).all())


class Kept(Land):
    relief = 120

    def test_cliffs_and_scree_are_the_lands_own_and_snow_lies_on_no_wall(self):
        h = np.zeros((33, 33))
        h[:, 16:] = 100.0  # (a wall down the middle: the east half stands high)
        pic = np.zeros((40, 40, 3), dtype=np.uint8)
        pic[:, :] = WHITE  # (the picture says snow everywhere)
        self.place(h, pic)
        code, verdict, data, roles = self.run_painter("--imagery", self.picture())
        self.assertEqual(code, 0, verdict)
        _, _, _, plain = self.run_painter()
        steep = (plain == ROLE["cliff"]) | (plain == ROLE["scree"])
        self.assertTrue(steep.sum() > 50)  # (the wall is there)
        self.assertTrue((roles[steep] == plain[steep]).all())  # (and stays what the land's shape made it)
        self.assertTrue((roles[~steep & (plain <= 2)] == ROLE["snow"]).mean() > 0.95)  # (the level soil is snow)


class Rule(unittest.TestCase):
    """the painter's own function on a land of every slope: what the picture may change, cell by cell"""

    def land(self):
        n, cell = 96, 4.0
        deg = np.linspace(0, 72, n)  # (level in the west, a wall in the east)
        h = np.repeat(np.cumsum(np.tan(np.radians(deg)) * cell)[:, None], n, axis=1)
        flow = np.zeros((n, n))
        flow[3:8, :] = 1000.0  # (water runs down the level west)
        gx, gz = np.gradient(h, cell)
        return h, cell, flow, np.degrees(np.arctan(np.sqrt(gx * gx + gz * gz)))

    def paint(self, word):
        h, cell, flow, _ = self.land()
        opts = {} if word is None else {"imagery": np.full(h.shape, word, dtype=object)}
        return T.paint(h, cell, flow, None, 38, 7, opts)[0]

    def test_what_a_picture_may_change_and_what_it_may_not(self):
        _, _, _, slope = self.land()
        plain = self.paint(None)
        for name in ("meadow", "mud", "rock", "cliff", "scree"):  # (the land has each: or this test holds nothing)
            self.assertTrue((plain == ROLE[name]).sum() > 20, name)
        soil = plain <= 2
        rock = plain == ROLE["rock"]
        self.assertTrue((rock & (slope >= 48)).sum() > 20)  # (rock too steep for snow, and no cliff)
        self.assertTrue((rock & (slope < 48)).sum() > 20)
        # the soil takes what the picture shows; rock a slope made stays rock (no sand on 45 degrees)
        for word, role in (("meadow", 0), ("lush", 1), ("dirt", 2), ("rock", 4), ("sand", 7), ("mud", 3)):
            want = np.where(soil, role, plain)
            self.assertTrue((self.paint(word) == want).all(), word)
        # snow alone lies on that rock too, on nothing steeper than 48 degrees
        want = np.where((soil | rock) & (slope < 48), ROLE["snow"], plain)
        self.assertTrue((self.paint("snow") == want).all())
        self.assertTrue((self.paint("water") == plain).all())


class Refused(Land):
    def refuse(self, text, *more, **kw):
        code, verdict, _, _ = self.run_painter(*more, **kw)
        self.assertEqual(code, 1, verdict)
        self.assertEqual(verdict["status"], "fail")
        self.assertIn(text, verdict["summary"])

    def test_a_picture_that_is_not_this_lands_is_refused(self):
        pic = np.zeros((40, 40, 3), dtype=np.uint8)
        pic[:, :] = GREEN
        self.place(self.flat(), pic, picture_bbox=[-119.0, 37.0, -118.9, 37.1])
        self.refuse("an aerial picture colours the land it was taken of", "--imagery", self.picture())
        for k in range(4):  # (each of the box's four numbers is held, and closely)
            near = list(BBOX)
            near[k] += 0.001
            self.place(self.flat(), pic, picture_bbox=near)
            self.refuse("an aerial picture colours the land it was taken of", "--imagery", self.picture())
        self.place(self.flat(), pic, sidecar=False)
        os.remove(os.path.join(self.dir, "land.img.json")) if os.path.isfile(os.path.join(self.dir, "land.img.json")) else None
        self.refuse("has no sidecar", "--imagery", self.picture())
        self.place(self.flat(), pic)
        self.refuse("no picture", "--imagery", os.path.join(self.dir, "other.img.png"))
        # no real land under it: a land of noise has no place a picture could be of
        self.refuse("the cover of a REAL place", "--imagery", self.picture(), design=False)
        # a climate (or a snowline) beside it: two tellers of the soil's cover
        self.refuse("one of them", "--imagery", self.picture(), "--climate", "wind=270,rain=0.6")
        self.refuse("one of them", "--imagery", self.picture(), "--snowline", "50")
        self.refuse("--imagery needs the picture's file", "--imagery")
        self.refuse("--imagery is said twice", "--imagery", self.picture(), "--imagery", self.picture())
        self.refuse("--no-paint says not to", "--imagery", self.picture(), "--no-paint")

    def test_a_sidecar_that_cannot_be_trusted_is_said_in_one_line(self):
        pic = np.zeros((40, 40, 3), dtype=np.uint8)
        pic[:, :] = GREEN
        said = "an aerial picture colours the land it was taken of"
        for box in (["a", 1, 2, 3], [str(v) for v in BBOX], BBOX[:3], None, "box", [True, 1, 2, 3]):
            self.place(self.flat(), pic)
            with open(os.path.join(self.dir, "land.img.json"), "w", encoding="utf-8") as fh:
                json.dump({"bbox": box, "credit": "a test picture", "covers": {}}, fh)
            self.refuse(said, "--imagery", self.picture())
        # the land's own sidecar with no box
        self.place(self.flat(), pic)
        with open(os.path.join(self.dir, "land.dem.json"), "w", encoding="utf-8") as fh:
            json.dump({"width_m": 1000.0}, fh)
        self.refuse(said, "--imagery", self.picture())
        # a picture fetched before it was asked for the ground the heights cover
        self.place(self.flat(), pic)
        with open(os.path.join(self.dir, "land.img.json"), "w", encoding="utf-8") as fh:
            json.dump({"bbox": BBOX, "credit": "a test picture"}, fh)
        self.refuse("does not lie on the land", "--imagery", self.picture())
        # no credit
        for credit in (None, "", 5):
            self.sidecar_more = {"credit": credit}
            self.place(self.flat(), pic)
            self.refuse("names no credit", "--imagery", self.picture())
        self.sidecar_more = None
        # damaged files: one line, no crash, no land written
        self.place(self.flat(), pic)
        with open(os.path.join(self.dir, "land.img.json"), "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        self.refuse("cannot be read", "--imagery", self.picture())
        self.place(self.flat(), pic)
        with open(self.picture(), "wb") as fh:
            fh.write(b"not a picture")
        self.refuse("cannot be read", "--imagery", self.picture())
        self.assertFalse(os.path.exists(os.path.join(self.dir, "land.hm.json")))


if __name__ == "__main__":
    unittest.main()
