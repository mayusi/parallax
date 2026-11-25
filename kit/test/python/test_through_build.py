"""A named opening through REAL builds (kit/selftest/blender/build_open_way.py and its plugged twin; the owner's
limitations page D-R12): a bore named open is looked down on the parts and on the exported mesh; a plug left in it
fails the build by the opening's name and the plug's, in a shape-only round too."""

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


def build(script, *args):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_through_build"))
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview", *args],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.open, cls.plugged = build("build_open_way.py"), build("build_open_way_plugged.py")
        cls.geo = build("build_open_way_plugged.py", "--geo")
        cls.master = build("build_open_way_fine.py")
        cls.game = build("build_open_way_fine.py", "--optimize", "--budget=400", "--retopo")

    def test_a_bore_named_open_is_looked_down_on_the_parts_and_on_the_export(self):
        self.assertEqual(self.open["status"], "pass", self.open["summary"][:300])
        way = self.open["facts"]["open_ways"]["Bore"]
        self.assertEqual((way["parts"], way["export"]), (None, None))     # both looked down, both open
        self.assertEqual(way["width"], 0.5)
        port = self.open["facts"]["open_ways"]["Port"]                    # named inside a turned frame: along X
        self.assertEqual((port["parts"], port["export"]), (None, None))
        self.assertAlmostEqual(abs(port["to"][0] - port["from"][0]), 2.4, places=3)
        self.assertAlmostEqual(port["from"][2], -1.2, places=3)
        self.assertIn("openings: 2 open", self.open["summary"])
        self.assertFalse(any(c["name"] == "open_ways" for c in self.open["design"]))

    def test_a_plug_left_in_the_bore_fails_by_the_openings_name_and_the_plugs(self):
        for v in (self.plugged, self.geo):
            self.assertEqual(v["status"], "fail")
            said = [c for c in v["design"] if c["name"] == "open_ways"]
            self.assertEqual(len(said), 1)                               # (said once: on the parts, not again)
            self.assertEqual(said[0]["severity"], "error")
            self.assertEqual(said[0]["value"],
                             ["Bore: 15 of its 15 lines of sight are stopped by Plug at (0, 0.5, 0.45)"])
            self.assertIn("openings: CLOSED Bore", v["summary"])
            self.assertIsNone(v["facts"]["open_ways"]["Port"]["parts"])   # (the other opening: still open)
        self.assertIsNone(self.plugged["facts"]["open_ways"]["Port"]["export"])   # ... and still looked down

    def test_a_fine_bore_the_game_versions_retopology_closes_fails_that_build(self):
        self.assertEqual(self.master["status"], "pass", self.master["summary"][:300])
        self.assertEqual(self.master["facts"]["open_ways"]["FineBore"]["export"], None)
        self.assertEqual(self.game["status"], "fail")
        way = self.game["facts"]["open_ways"]["FineBore"]
        self.assertIsNone(way["parts"])                                   # open as modelled ...
        self.assertIn("lines of sight are stopped by main", way["export"])   # ... closed in the exported mesh
        said = [c for c in self.game["design"] if c["name"] == "open_ways"]
        self.assertEqual([c["severity"] for c in said], ["error"])        # (a game version is blocked by it)
        self.assertIn("reduction", said[0]["fix"])


if __name__ == "__main__":
    unittest.main()
