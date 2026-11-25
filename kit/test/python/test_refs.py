"""The reference finder must never let a licence through that a game cannot use (non-commercial, no-derivatives,
unknown), and must read every common spelling of the ones it can."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "refs"))
import find  # noqa: E402
import patent  # noqa: E402


class TestLicence(unittest.TestCase):
    def test_usable(self):
        for short, want in (("CC0", "cc0"), ("CC0 1.0", "cc0"), ("Public domain", "pdm"), ("PD-US", "pdm"),
                            ("CC BY 4.0", "by"), ("CC BY 2.0", "by"), ("CC BY-SA 4.0", "by-sa"), ("cc-by-sa-3.0", "by-sa"),
                            ("CC BY-SA 3.0 de", "by-sa")):
            self.assertEqual(find._licence(short), want, short)

    def test_never_usable(self):
        for short in ("CC BY-NC 2.0", "CC BY-NC-SA 4.0", "cc-by-nc-sa-3.0", "CC BY-ND 2.0", "CC BY-NC-ND 4.0",
                      "GFDL", "", None, "All rights reserved"):
            self.assertNotIn(find._licence(short), find.OK_LICENSES, short)

    def test_patent_numbers(self):
        for text, want in (("D885516", "D885516"), ("USD885516S", "D885516"), ("d885,516", "D885516"),
                           ("US D885516 S1", "D885516"), ("10123456", None), ("US10123456B2", None), ("", None)):
            self.assertEqual(patent.number_of(text), want, text)

    def test_utility_patent_numbers(self):
        """a utility patent (the mechanism's drawings: Browning's 1911 is US 984,519) -> 7 digits, zero-padded"""
        for text, want in (("984519", "0984519"), ("US 984,519", "0984519"), ("US0984519A", "0984519"),
                           ("580924", "0580924"), ("12", None), ("hello", None)):
            self.assertEqual(patent.number_of(text), want, text)

    def test_patent_figures(self):
        """two drawings and a small label on a page -> two figures, the label dropped"""
        import numpy as np
        page = np.zeros((1000, 800), bool)
        page[200:450, 100:300] = True   # figure 1 (a filled block stands in for a drawing)
        page[600:900, 400:700] = True   # figure 2
        page[470:480, 150:180] = True   # "FIG. 1" label: small, dropped
        boxes = patent.figures(page)
        self.assertEqual(len(boxes), 2, boxes)

    def test_slug(self):
        self.assertEqual(find.slug("Treasure Chest!"), "treasure_chest")
        self.assertEqual(find.slug("   "), "refs")


if __name__ == "__main__":
    unittest.main()


class TestMuseums(unittest.TestCase):
    """The Met and Cleveland sources keep ONLY their CC0 works, carry the real dimensions, and use the Met's v1.1
    search (v1 retired 2026-10-01). The network is stubbed: canned API answers."""

    def setUp(self):
        import json  # noqa: PLC0415

        self.calls = []
        met_search = {"total": 3, "objectIDs": [1, 2, 3]}
        met_objects = {
            1: {"isPublicDomain": True, "primaryImage": "https://images.metmuseum.org/a.jpg", "title": "Flintlock Pistol",
                "artistDisplayName": "", "culture": "French", "objectURL": "https://www.metmuseum.org/art/collection/search/1",
                "dimensions": "L. 24 3/4 in. (62.7 cm)", "dimensionsParsed": [{"element": "Overall", "dimensionType": "Length", "dimension": 62.7}]},
            2: {"isPublicDomain": False, "primaryImage": "https://images.metmuseum.org/b.jpg", "title": "A modern work"},
            3: {"isPublicDomain": True, "primaryImage": "https://images.metmuseum.org/c.jpg", "title": "Cabinet",
                "objectName": "Cabinet", "classification": "Woodwork-Furniture", "tags": [{"term": "Birds"}]},
        }
        cma = {"data": [
            {"id": 7, "title": "Pair of Flintlock Pistols", "creators": [{"description": "Lazarino Cominazzo"}],
             "url": "https://clevelandart.org/art/7", "share_license_status": "CC0", "measurements": "Overall: 45.1 cm",
             "dimensions": {"overall": {"length": 0.451}}, "images": {"web": {"url": "https://openaccess-cdn.clevelandart.org/7.jpg", "width": "1600", "height": "900"}}},
            {"id": 8, "title": "Copyrighted", "share_license_status": "Copyrighted",
             "images": {"web": {"url": "https://openaccess-cdn.clevelandart.org/8.jpg"}}},
            {"id": 9, "title": "Side Chair", "type": "Furniture", "share_license_status": "CC0",
             "images": {"web": {"url": "https://openaccess-cdn.clevelandart.org/9.jpg"}}}]}

        def fake_get(url, timeout=30, limit=None):
            self.calls.append(url)
            if "v1.1/search" in url:
                return json.dumps(met_search).encode(), "application/json"
            if "/v1/objects/" in url:
                return json.dumps(met_objects[int(url.rsplit("/", 1)[1])]).encode(), "application/json"
            if "clevelandart.org/api/artworks" in url:
                return json.dumps(cma).encode(), "application/json"
            raise AssertionError(f"unexpected url {url}")

        self.real_get, find._get = find._get, fake_get

    def tearDown(self):
        find._get = self.real_get

    def test_the_met_keeps_open_access_only_with_its_dimensions(self):
        got = find.met("flintlock pistol", 4, {"cc0", "pdm", "by", "by-sa"})
        self.assertEqual([r["id"] for r in got], ["1"])
        self.assertEqual(got[0]["license"], "cc0")
        self.assertIn("62.7 cm", got[0]["dimensions"])
        self.assertTrue(any("/v1.1/search" in u for u in self.calls))
        self.assertFalse(any("/v1/search" in u for u in self.calls))  # the retired search is never called

    def test_cleveland_keeps_cc0_only_with_its_dimensions(self):
        got = find.cleveland("flintlock pistol", 4, {"cc0", "by"})
        self.assertEqual([r["id"] for r in got], ["7"])
        self.assertEqual((got[0]["width"], got[0]["height"]), (1600, 900))
        self.assertEqual(got[0]["dimensions_parsed"]["overall"]["length"], 0.451)

    def test_a_museum_record_must_be_about_the_query(self):
        # the museums' search matches anywhere in a record: a cabinet came back for "glock 17 gen 5 left side slide
        # markings". A record stays only when a word of the query that is not a view word ("left", "side", ...) is in
        # its own name
        self.assertEqual([r["id"] for r in find.met("flintlock pistol left side", 4, {"cc0"})], ["1"])
        self.assertEqual([r["id"] for r in find.cleveland("flintlock pistol side view", 4, {"cc0"})], ["7"])
        self.assertFalse(find._relevant("glock 17 gen 5 left side slide markings", "Cabinet", "Woodwork-Furniture"))
        self.assertTrue(find._relevant("flintlock pistols", "Flintlock Pistol"))

    def test_no_cc0_asked_for_no_museum_called(self):
        self.assertEqual(find.met("x", 4, {"by"}), [])
        self.assertEqual(find.cleveland("x", 4, {"by"}), [])
        self.assertEqual(self.calls, [])


class TestCropFrame(unittest.TestCase):
    """kit refs crop lays the profiles' mm frame back on the picture: the anchor's rear end at f = 0, its top at top_mm"""

    def _trace(self, front):
        # the anchor (a slide) from u 0.1 to 0.9 along a 1000 px length, its top at v 0.3, the frame at x0 50, y1 700
        slide = [[0.1, 0.2], [0.9, 0.2], [0.9, 0.3], [0.1, 0.3]]
        t = {"front": front, "frame": {"x0": 50.0, "y1": 700.0, "length_px": 1000.0}, "parts": {"slide": slide}}
        prof = {"anchor": "slide", "mm_per_unit": 250.0, "top_mm": 14.0}  # 0.8 units = 200 mm
        return t, prof

    def test_front_right(self):
        import crop  # noqa: PLC0415

        t, prof = self._trace("right")
        px = crop.frame(t, prof)
        self.assertEqual(tuple(round(c, 6) for c in px(0.0, 14.0)), (150.0, 400.0))  # u 0.1, v 0.3
        self.assertEqual(tuple(round(c, 6) for c in px(200.0, 14.0 - 25.0)), (950.0, 500.0))  # u 0.9, v 0.2

    def test_front_left_runs_the_other_way(self):
        import crop  # noqa: PLC0415

        t, prof = self._trace("left")
        px = crop.frame(t, prof)
        self.assertEqual(round(px(0.0, 14.0)[0], 6), 950.0)  # the rear end on the RIGHT of a front-left picture
        self.assertEqual(round(px(200.0, 14.0)[0], 6), 150.0)

