"""test_world_imagery.py - REAL GROUND COVER FROM AN AERIAL PICTURE (kit/world/imagery.py; the owner's method list:
"Satellite imagery-based terrain"). No network here: what is asked of the service, what is taken from it and what is
refused, how a picture is read as the painter's roles, and that the read lies on the land the same way the heights do.
Not claimed here: that the read is right about a real place. It is a read of colour; the audit page says what one
real picture read as, and where that was wrong."""
import importlib.util
import io
import json
import os
import tempfile
import unittest
import urllib.parse

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_world_imagery", os.path.join(HERE, "..", "..", "world", "imagery.py"))
I = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(I)


YOSEMITE = [-119.66, 37.715, -119.53, 37.765]
DEM_COVERS = (-13320490.268323116, 4535526.190545658, -13306018.73451999, 4549997.7243487835)  # (the service's own answer)


def png(array, mode="RGB"):
    buf = io.BytesIO()
    Image.fromarray(np.asarray(array, dtype=np.uint8), mode).save(buf, "PNG")
    return buf.getvalue()


def noisy(size, seed=1):
    return np.random.default_rng(seed).integers(0, 255, (size, size, 3))


class Asking(unittest.TestCase):
    def test_what_is_asked_of_the_service(self):
        url = urllib.parse.urlparse(I.query(YOSEMITE, 512))
        self.assertEqual((url.scheme, url.hostname), ("https", "imagery.nationalmap.gov"))
        self.assertTrue(url.path.endswith("/USGSNAIPImagery/ImageServer/exportImage"))
        q = dict(urllib.parse.parse_qsl(url.query))
        # the picture is asked for the square the box's HEIGHTS cover, in the web map's own grid: nothing is left
        # for the service to widen
        asked = [float(v) for v in q["bbox"].split(",")]
        for got, want in zip(asked, DEM_COVERS):
            self.assertAlmostEqual(got, want, places=4)
        self.assertEqual((q["bboxSR"], q["imageSR"], q["size"], q["format"], q["bandIds"], q["f"], q["interpolation"]),
                         ("102100", "102100", "512,512", "png", "0,1,2", "image", "RSP_BilinearInterpolation"))

    def test_the_ground_a_boxs_heights_cover(self):
        # MEASURED (2026-11-15, the elevation service asked what it covers for this box at a square size): the box
        # widened about its middle to a square on the web map's grid
        for got, want in zip(I.covered(YOSEMITE), DEM_COVERS):
            self.assertAlmostEqual(got, want, places=4)
        on = I.ground(YOSEMITE)
        self.assertEqual(on["lon"], [-119.66, -119.53])  # (the wide side is as typed)
        self.assertAlmostEqual(on["lat"][0], 37.6886, places=3)  # (the narrow side is widened: 0.05 degrees typed)
        self.assertAlmostEqual(on["lat"][1], 37.7914, places=3)
        self.assertAlmostEqual(on["side_m"] / 1000, 11.45, places=1)  # (its real side: the web map stretches it)
        # a tall box is widened east-west instead
        tall = I.ground([-119.60, 37.70, -119.59, 37.80])
        self.assertEqual(tall["lat"], [37.7, 37.8])
        self.assertTrue(tall["lon"][0] < -119.60 and tall["lon"][1] > -119.59)
        self.assertAlmostEqual((tall["lon"][0] + tall["lon"][1]) / 2, -119.595, places=5)
        self.assertAlmostEqual(tall["side_m"] / 1000, 11.12, places=1)
        # there and back
        x, y = I.mercator(-119.6, 37.7)
        lon, lat = I.unmercator(x, y)
        self.assertAlmostEqual(lon, -119.6, places=9)
        self.assertAlmostEqual(lat, 37.7, places=9)
        self.assertAlmostEqual(I.mercator(180, 0)[0], 20037508.34, places=1)

    def test_a_box_or_a_size_that_is_none_is_refused(self):
        for bbox in ([-119.5, 37.7, -119.6, 37.8], [-119.6, 37.8, -119.5, 37.7], [-181, 0, 0, 1], [0, 0, 1, 91], [0, 0, 0, 1],
                     [0, 84, 1, 86], [0, -86, 1, 0]):
            with self.assertRaises(ValueError):
                I.query(bbox, 512)
        for size in (8, 15, 2049, 512.5, "512"):
            with self.assertRaises(ValueError):
                I.query([0, 0, 1, 1], size)
        I.query([0, 0, 1, 1], 16)
        I.query([0, 0, 1, 1], 2048)

    def test_the_boxes_real_size(self):
        w, h = I.box_metres(0, -0.5, 1, 0.5)  # (a degree each way on the equator: about 111 km)
        self.assertAlmostEqual(w / 1000, 111.19, places=1)
        self.assertAlmostEqual(h / 1000, 111.19, places=1)
        w60, _ = I.box_metres(0, 59.5, 1, 60.5)  # (at 60 degrees north a degree of longitude is half as wide)
        self.assertAlmostEqual(w60 / w, 0.5, places=3)


class Taking(unittest.TestCase):
    def test_a_picture_of_the_size_asked_is_taken(self):
        a = I.accept(png(noisy(32)), 32)
        self.assertEqual(a.shape, (32, 32, 3))
        self.assertTrue((a == noisy(32)).all())

    def test_what_is_no_picture_of_the_place_is_refused(self):
        for data, text in ((b"<html>error</html>", "not a PNG"),
                           (png(noisy(16)), "unexpected picture (16, 16), asked 32 x 32"),
                           (png(np.full((32, 32, 3), 120)), "one flat colour"),
                           (b"\x89PNG\r\n\x1a\n" + b"0" * (I.MAX_BYTES + 1), "larger than the cap")):
            with self.assertRaises(ValueError) as stop:
                I.accept(data, 32)
            self.assertIn(text, str(stop.exception))
        # a picture that is partly empty (the box runs off the coverage)
        rgba = np.dstack([noisy(32), np.full((32, 32), 255)])
        rgba[:8, :, 3] = 0
        with self.assertRaises(ValueError) as stop:
            I.accept(png(rgba, "RGBA"), 32)
        self.assertIn("25.0 % of the picture is empty", str(stop.exception))
        rgba[:8, :, 3] = 255
        rgba[0, :10, 3] = 0  # (under 2 %: taken)
        I.accept(png(rgba, "RGBA"), 32)
        rgba[0, :21, 3] = 0  # (21 of 1024: just over 2 %)
        with self.assertRaises(ValueError):
            I.accept(png(rgba, "RGBA"), 32)
        # where it has no flight the service may send black: over 2 % of it is refused
        dark = noisy(32).clip(1, 255)
        dark[:4] = 0
        with self.assertRaises(ValueError) as stop:
            I.accept(png(dark), 32)
        self.assertIn("12.5 % of the picture is black", str(stop.exception))
        dark = noisy(32).clip(1, 255)
        dark[0, :20] = 0  # (under 2 %: a few dark pixels are a shadow)
        I.accept(png(dark), 32)
        # a picture that is nearly one colour is none
        faint = np.full((32, 32, 3), 120)
        faint[::2] += 2  # (std 1)
        with self.assertRaises(ValueError):
            I.accept(png(faint), 32)
        faint[::2] += 4  # (std 3)
        I.accept(png(faint), 32)


class Answer:
    """what a service answers with, for a fetch that reaches no network"""

    def __init__(self, data, url):
        self.data, self.url = data, url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def geturl(self):
        return self.url

    def read(self, n=-1):
        return self.data if n < 0 else self.data[:n]


class Fetching(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kit_imagery_fetch_")
        self.addCleanup(__import__("shutil").rmtree, self.dir, ignore_errors=True)
        self.out = os.path.join(self.dir, "sub", "Y.img.png")
        self.asked = []
        self.real = I.urllib.request.build_opener
        self.addCleanup(setattr, I.urllib.request, "build_opener", self.real)

    def serve(self, data, url=None):
        test = self

        class Opener:
            def open(self, req, timeout=None):
                test.asked.append((req.full_url, req.get_header("User-agent"), timeout))
                return Answer(data, url or req.full_url)

        def build(*handlers):
            test.handlers = handlers
            return Opener()

        I.urllib.request.build_opener = build

    def test_a_fetch_writes_the_picture_and_what_it_shows(self):
        data = png(noisy(32))
        self.serve(data)
        meta = I.fetch(YOSEMITE, self.out, 32)
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(self.asked[0][0], I.query(YOSEMITE, 32))
        self.assertIn("roblox-kit", self.asked[0][1])
        self.assertEqual(self.handlers, (I.NoRedirect,))  # (a redirect is refused before it is followed)
        with open(self.out, "rb") as fh:
            self.assertEqual(fh.read(), data)
        with open(I.sidecar(self.out), encoding="utf-8") as fh:
            written = json.load(fh)
        self.assertEqual(written, meta)
        self.assertEqual(meta["bbox"], YOSEMITE)
        self.assertEqual(meta["credit"], I.CREDIT)
        self.assertEqual(meta["size"], 32)
        self.assertEqual(meta["covers"], I.ground(YOSEMITE))
        self.assertEqual((meta["width_m"], meta["height_m"]), (meta["covers"]["side_m"], meta["covers"]["side_m"]))
        self.assertEqual(meta["m_per_px"], [round(meta["covers"]["side_m"] / 32, 3)] * 2)
        self.assertEqual(meta["cover"], I.cover(I.read(noisy(32))))

    def test_an_answer_that_is_no_picture_writes_nothing(self):
        self.serve(b'{"error": {"code": 400}}')
        with self.assertRaises(ValueError):
            I.fetch(YOSEMITE, self.out, 32)
        self.assertFalse(os.path.exists(self.out))
        self.assertFalse(os.path.exists(I.sidecar(self.out)))

    def test_an_answer_from_elsewhere_is_refused(self):
        for url in ("https://example.org/x.png", "http://imagery.nationalmap.gov/x.png"):
            self.serve(png(noisy(32)), url)
            with self.assertRaises(ValueError) as stop:
                I.fetch(YOSEMITE, self.out, 32)
            self.assertIn("redirected off imagery.nationalmap.gov", str(stop.exception))
            self.assertFalse(os.path.exists(self.out))
        with self.assertRaises(ValueError) as stop:
            I.NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://example.org/x")
        self.assertIn("redirected off", str(stop.exception))

    def test_an_answer_over_the_cap_is_refused(self):
        self.serve(b"\x89PNG\r\n\x1a\n" + b"0" * (I.MAX_BYTES + 5))
        with self.assertRaises(ValueError) as stop:
            I.fetch(YOSEMITE, self.out, 32)
        self.assertIn("larger than the cap", str(stop.exception))


class Reading(unittest.TestCase):
    def test_a_colour_is_read_as_the_ground_it_shows(self):
        for rgb, want in (((70, 120, 50), "meadow"), ((30, 70, 30), "lush"), ((140, 140, 140), "rock"),
                          ((90, 90, 95), "rock"), ((250, 250, 250), "snow"), ((240, 245, 250), "snow"),
                          ((210, 190, 140), "sand"), ((120, 90, 60), "dirt"), ((40, 35, 30), "mud"),
                          ((30, 60, 120), "water"), ((0, 0, 0), "mud"), ((200, 60, 200), "dirt"),
                          ((60, 100, 100), "dirt"), ((150, 180, 230), "dirt"),  # (teal is no grass; a bright blue no water)
                          # what a fresh reader found read wrong, and is read so now:
                          ((200, 170, 110), "dirt"),  # (dry golden grass is no sand)
                          ((220, 215, 205), "rock"),  # (pale granite is no snow)
                          ((120, 128, 120), "rock")):  # (grey rock with a green cast is no meadow)
            self.assertEqual(I.read(np.array([[rgb]]))[0, 0], want, rgb)
        # every name it reads is one the painter knows, or water
        for name in set(I.read(noisy(64)).ravel()):
            self.assertIn(name, I.ROLES + (I.WATER,))
        self.assertEqual(I.ROLES, ("meadow", "lush", "dirt", "mud", "rock", "snow", "sand"))

    def test_where_one_ground_ends_and_the_next_begins(self):
        """each of the read's limits, a colour on either side of it (v = brightest band / 255, s = (v - lowest) / v)"""
        def name(rgb):
            return I.read(np.array([[rgb]]))[0, 0]

        # snow: v >= 0.92 and s <= 0.08
        self.assertEqual(name((235, 235, 235)), "snow")  # (v 0.922)
        self.assertEqual(name((233, 233, 233)), "rock")  # (v 0.914)
        self.assertEqual(name((250, 250, 231)), "snow")  # (s 0.076)
        self.assertEqual(name((250, 250, 227)), "rock")  # (s 0.092)
        # rock: s < 0.15, v >= 0.25
        self.assertEqual(name((150, 140, 129)), "rock")  # (s 0.14)
        self.assertEqual(name((150, 140, 126)), "dirt")  # (s 0.16: warm and dim)
        self.assertEqual(name((64, 64, 64)), "rock")  # (v 0.251)
        self.assertEqual(name((62, 62, 62)), "mud")  # (v 0.243)
        # mud: v < 0.25 and s < 0.3
        self.assertEqual(name((60, 50, 43)), "mud")  # (s 0.28)
        self.assertEqual(name((60, 48, 40)), "dirt")  # (s 0.33)
        # sand: warm, 0.15 <= s < 0.38, v >= 0.6
        self.assertEqual(name((200, 180, 165)), "sand")  # (s 0.175)
        self.assertEqual(name((154, 130, 100)), "sand")  # (v 0.604, s 0.35)
        self.assertEqual(name((150, 127, 98)), "dirt")  # (v 0.588)
        self.assertEqual(name((200, 170, 126)), "sand")  # (s 0.37)
        self.assertEqual(name((200, 170, 122)), "dirt")  # (s 0.39)
        # green: over red and over blue by 4 %, s >= 0.12
        self.assertEqual(name((100, 106, 80)), "meadow")  # (6 % over red)
        self.assertEqual(name((100, 103, 80)), "dirt")  # (3 % over red)
        self.assertEqual(name((80, 106, 100)), "meadow")
        self.assertEqual(name((80, 103, 100)), "dirt")
        self.assertEqual(name((110, 126, 110)), "meadow")  # (s 0.127)
        self.assertEqual(name((113, 126, 113)), "rock")  # (s 0.103)
        # lush: green and v < 0.35
        self.assertEqual(name((40, 88, 40)), "lush")  # (v 0.345)
        self.assertEqual(name((40, 91, 40)), "meadow")  # (v 0.357)
        # water: blue over red by 15 % and over green by 2 %, v < 0.7
        self.assertEqual(name((100, 100, 118)), "water")  # (18 % over red)
        self.assertEqual(name((100, 100, 112)), "rock")  # (12 %)
        self.assertEqual(name((60, 120, 124)), "water")  # (3 % over green)
        self.assertEqual(name((60, 120, 121)), "dirt")  # (under 2 % over green, and not green enough over blue)
        self.assertEqual(name((100, 120, 176)), "water")  # (v 0.69)
        self.assertEqual(name((100, 120, 181)), "dirt")  # (v 0.71)

    def test_colours_are_not_mixed_before_they_are_read(self):
        # half dark forest and half pale sand, in a fine checker: a cell of the land is one of the two, never the
        # meadow their average would read as (a fresh reader's find)
        a = np.zeros((64, 64, 3), dtype=np.uint8)
        a[:, :] = (30, 70, 30)
        a[::2, 1::2] = (210, 190, 140)
        a[1::2, ::2] = (210, 190, 140)
        a[:, 32:] = (210, 190, 140)  # (the east half is sand alone)
        a[:8, :32] = (140, 140, 140)  # (a strip of rock in the north-west)
        fd, path = tempfile.mkstemp(suffix=".img.png")
        os.close(fd)
        self.addCleanup(os.remove, path)
        Image.fromarray(a).save(path)
        names, _ = I.load(path, 8)
        self.assertEqual(set(names[:4, 1:].ravel()), {"lush"})  # (a tie goes to the name the painter lists first)
        self.assertEqual(set(names[4:, :].ravel()), {"sand"})
        self.assertEqual(set(names[:4, 0].ravel()), {"rock"})
        self.assertNotIn("meadow", set(names.ravel()))
        # a cell takes what covers MOST of it: three parts rock, one part sand
        b = np.zeros((16, 16, 3), dtype=np.uint8)
        b[:, :] = (140, 140, 140)
        b[::2, ::2] = (210, 190, 140)
        Image.fromarray(b).save(path)
        self.assertEqual(set(I.load(path, 4)[0].ravel()), {"rock"})

    def test_the_share_of_each(self):
        a = np.zeros((10, 10, 3), dtype=np.uint8)
        a[:, :] = (70, 120, 50)
        a[:3, :] = (140, 140, 140)
        a[9, :5] = (250, 250, 250)
        self.assertEqual(I.cover(I.read(a)), {"meadow": 0.65, "rock": 0.3, "snow": 0.05})
        self.assertAlmostEqual(sum(I.cover(I.read(noisy(40))).values()), 1.0, places=2)

    def test_the_read_lies_on_the_land_as_the_heights_do(self):
        # a picture whose north-east corner is snow and whose south-west is meadow, rock elsewhere
        a = np.zeros((40, 40, 3), dtype=np.uint8)
        a[:, :] = (140, 140, 140)
        a[:10, 30:] = (250, 250, 250)  # (the picture's top right: north-east)
        a[30:, :10] = (70, 120, 50)  # (bottom left: south-west)
        fd, path = tempfile.mkstemp(suffix=".img.png")
        os.close(fd)
        self.addCleanup(os.remove, path)
        Image.fromarray(a).save(path)
        with open(I.sidecar(path), "w", encoding="utf-8") as fh:
            json.dump({"credit": I.CREDIT, "bbox": [0, 0, 1, 1]}, fh)
        self.addCleanup(os.remove, I.sidecar(path))
        names, meta = I.load(path, 20)
        self.assertEqual(names.shape, (20, 20))
        self.assertEqual(meta["credit"], I.CREDIT)
        # [x, z]: x grows east, z grows south (north is -z)
        self.assertEqual(names[18, 1], "snow")  # (east, north)
        self.assertEqual(names[1, 18], "meadow")  # (west, south)
        self.assertEqual(names[1, 1], "rock")
        self.assertEqual(names[18, 18], "rock")
        self.assertTrue(I.sidecar(path).endswith(".img.json"))


class Words(unittest.TestCase):
    def run_main(self, argv):
        import contextlib

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = I.main(argv)
        return code, json.loads(out.getvalue())

    def test_what_is_wrong_is_said_in_one_line(self):
        for argv, text in (([], "usage:"), (["fetch", "--bbox", "1,2,3,4"], "usage:"),
                           (["fetch", "--bbox", "1,2,3", "--out", "x.png"], "bbox needs 4 numbers"),
                           (["fetch", "--bbox", "a,b,c,d", "--out", "x.png"], "imagery:"),
                           (["fetch", "--bbox", "1,2,3,4", "--out", "x.png", "--size", "big"], "imagery:")):
            code, said = self.run_main(argv)
            self.assertEqual(code, 2, argv)
            self.assertEqual(said["status"], "fail")
            self.assertIn(text, said["summary"])
        code, said = self.run_main(["info", os.path.join(HERE, "no_such.img.png")])
        self.assertEqual((code, said["status"]), (1, "fail"))


if __name__ == "__main__":
    unittest.main()
