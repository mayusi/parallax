"""kit/tools/scans.py — a scan fetch extracts only the image maps of a zip whose every entry stays in its folder, pins
the tile's real size, and talks to ambientCG alone (no network here: the pure checks)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
import scans as S  # noqa: E402


class SafeEntries(unittest.TestCase):
    def test_a_flat_map_is_safe(self):
        self.assertTrue(S.safe_member("Bark014_2K-JPG_Color.jpg"))

    def test_escapes_are_refused(self):
        for bad in ("../evil.jpg", "a/../../evil.jpg", "/etc/passwd", "C:/Windows/x.jpg", "..\\x.jpg", ""):
            self.assertFalse(S.safe_member(bad), bad)


class Maps(unittest.TestCase):
    def test_only_the_maps_and_the_preview(self):
        names = ["Bark014_2K-JPG_Color.jpg", "Bark014_2K-JPG_NormalGL.jpg", "Bark014_2K-JPG_Roughness.jpg",
                 "Bark014.png", "Bark014_2K-JPG.blend", "Bark014_2K-JPG.usdc", "Bark014_2K-JPG.mtlx",
                 "sub/Bark014_2K-JPG_Color.jpg", "Other_2K-JPG_Color.jpg", "../Bark014_2K-JPG_AO.jpg"]
        self.assertEqual(S.map_members(names, "Bark014"),
                         ["Bark014.png", "Bark014_2K-JPG_Color.jpg", "Bark014_2K-JPG_NormalGL.jpg",
                          "Bark014_2K-JPG_Roughness.jpg"])


class Tile(unittest.TestCase):
    def test_listed_and_unlisted_sizes(self):
        self.assertEqual(S.tile_cm({"dimensionX": 120, "dimensionY": 120}), [120, 120])
        self.assertIsNone(S.tile_cm({"dimensionX": 0, "dimensionY": 0}))
        self.assertIsNone(S.tile_cm({}))


class Host(unittest.TestCase):
    def test_only_ambientcg_over_https(self):
        for url in ("https://evil.example/get?file=x.zip", "https://ambientcg.com.evil.example/x",
                    "http://notambientcg.com/x", "http://ambientcg.com/get?file=x.zip",
                    "https://struffelproductions.com.evil.example/x"):
            self.assertFalse(S.allowed(url), url)
            with self.assertRaises(ValueError, msg=url):
                S._get(url)
        self.assertTrue(S.allowed("https://ambientcg.com/get?file=Bark014_2K-JPG.zip"))
        self.assertTrue(S.allowed("https://acg-download.struffelproductions.com/file/ambientCG-Web/download/x.zip"))

    def test_a_redirect_off_the_hosts_is_refused(self):
        h = S._Stay()
        with self.assertRaises(ValueError):
            h.redirect_request(None, None, 302, "Found", {}, "https://evil.example/x.zip")
        with self.assertRaises(ValueError):
            h.redirect_request(None, None, 302, "Found", {}, "http://acg-download.struffelproductions.com/x.zip")

    def test_ids_are_letters_and_digits(self):
        for bad in ("../x", "Bark014/..", "", "a b"):
            with self.assertRaises(ValueError, msg=bad):
                S.lookup(bad)


if __name__ == "__main__":
    unittest.main()
