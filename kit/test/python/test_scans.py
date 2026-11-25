"""kit/blender/rbx_scans.py: scanned materials keep their VARIATION while the build keeps its own average colour and
roughness — finding a scan's maps, its real tile size, the tint that moves its average onto the wanted colour, and
the once-measured averages kept beside the maps."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_scans as S  # noqa: E402


def make_cache(root, scan="Metal999", tile_cm=None, maps=("Color", "Roughness", "Displacement", "NormalGL")):
    folder = os.path.join(root, scan)
    os.makedirs(folder)
    names = [f"{scan}_2K-JPG_{m}.jpg" for m in maps]
    for n in names:
        open(os.path.join(folder, n), "wb").close()
    with open(os.path.join(root, "pins.json"), "w", encoding="utf-8") as fh:
        json.dump({scan: {"file": f"{scan}_2K-JPG.zip", "size": 1, "sha256": "x", "maps": names, "tile_cm": tile_cm}}, fh)


class TestScans(unittest.TestCase):
    def test_find_gives_each_map_and_the_real_tile(self):
        with tempfile.TemporaryDirectory() as d:
            make_cache(d, tile_cm=[130, 65])
            s = S.find("Metal999", root=d)
            self.assertEqual(sorted(s["maps"]), ["color", "height", "normal", "rough"])
            self.assertAlmostEqual(s["tile_m"], 1.3)  # (the longer side)
            make_cache(os.path.join(d, "b"))
            self.assertEqual(S.find("Metal999", root=os.path.join(d, "b"))["tile_m"], S.DEFAULT_TILE_M)

    def test_an_unknown_scan_names_the_ones_there_and_the_download_rule(self):
        with tempfile.TemporaryDirectory() as d:
            make_cache(d)
            with self.assertRaises(S.ScanMissing) as cm:
                S.find("Gold001", root=d)
            self.assertIn("Metal999", str(cm.exception))
            self.assertIn("owner's OK", str(cm.exception))

    def test_tint_moves_the_average_onto_the_wanted_colour(self):
        t = S.tint((0.4, 0.2, 0.1), (0.2, 0.2, 0.2))
        self.assertEqual(t, (2.0, 1.0, 0.5))
        self.assertEqual(S.tint((1.0, 1.0, 1.0), (0.0, 0.01, 0.5))[0], 4.0)  # (clamped: a black scan cannot go white)

    def test_srgb_to_linear_matches_the_standard_curve(self):
        self.assertAlmostEqual(S.srgb_to_linear(0.0), 0.0)
        self.assertAlmostEqual(S.srgb_to_linear(1.0), 1.0)
        self.assertAlmostEqual(S.srgb_to_linear(0.5), 0.21404, places=4)

    def test_the_averages_are_measured_once_and_kept(self):
        calls = []

        def measure(path, srgb):
            calls.append((os.path.basename(path), srgb))
            return [0.3, 0.2, 0.1] if srgb else [0.6, 0.6, 0.6]

        with tempfile.TemporaryDirectory() as d:
            make_cache(d)
            a = S.stats("Metal999", measure, root=d)
            b = S.stats("Metal999", measure, root=d)
        self.assertEqual(a, b)
        self.assertEqual(a, {"mean_color": [0.3, 0.2, 0.1], "mean_rough": 0.6})
        self.assertEqual(len(calls), 2)  # colour (sRGB) + roughness (data), then never again
        self.assertEqual([c[1] for c in calls], [True, False])


if __name__ == "__main__":
    unittest.main()
