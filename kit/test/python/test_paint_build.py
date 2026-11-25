"""Vertex paint, through a REAL build (kit/selftest/blender/build_paint.py; the 3D methods audit, S4): the paint is
in the colour map where it was asked and nowhere else, in the exported file's vertex colours, and still said on a
build taken from the bake's cache."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join("build", "_test_paint_build")


def run():
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", "build_paint.py"), "--", "--no-preview"],
                          cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                          errors="replace")


def read(r):
    line = next((x for x in r.stdout.splitlines() if x.startswith("PAINT ")), None)
    assert line, (r.stderr or r.stdout)[-800:]
    v = json.loads(next(x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x))
    return json.loads(line[6:]), v


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.at, cls.v = read(run())
        cls.at2, cls.v2 = read(run())                # (its maps from the bake's cache)

    def test_the_paint_is_in_the_colour_map_where_it_was_asked(self):
        post, cap = self.at["Post"], self.at["Cap"]
        # (the rule: 0.40 of the stone at a fifth of its height, 0.81 at three quarters - 0.67 and 0.91 as sRGB)
        self.assertAlmostEqual(post["low"] / post["high"], 0.67 / 0.91, delta=0.06)
        self.assertGreater(cap["high"], 1.05 * post["high"])          # the cap: nobody painted it
        self.assertAlmostEqual(cap["low"], cap["high"], delta=0.08)

    def test_the_paint_is_in_the_exported_files_vertex_colours(self):
        f = self.at["file"]
        self.assertIsNotNone(f)
        self.assertLess(f["darkest"], 0.35)                           # the post's foot
        self.assertGreater(f["lightest"], 0.95)
        self.assertGreater(f["white_share"], 0.3)                     # the cap's corners, and the post's top
        check = next(c for c in self.v["groups"]["main"]["checks"] if c["name"] == "export_read_back")
        self.assertTrue(check["ok"], check)

    def test_the_build_says_the_paint_and_a_cached_build_says_the_same(self):
        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        p = self.v["facts"]["paint"]["main"]
        self.assertEqual(p["on"], ["Post"])
        self.assertAlmostEqual(p["darkest"], 0.25, delta=0.03)
        self.assertAlmostEqual(p["lightest"], 1.0, delta=0.03)
        self.assertIn("painted: main (Post:", self.v["summary"])
        self.assertEqual(self.v2["facts"]["paint"], self.v["facts"]["paint"])
        self.assertEqual(self.at2["file"], self.at["file"])
        self.assertEqual(self.at2["Post"], self.at["Post"])


if __name__ == "__main__":
    unittest.main()
