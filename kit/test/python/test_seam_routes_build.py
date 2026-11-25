"""Seams the author places, on EVERY unwrap route (kit/selftest/blender/build_seam_routes.py; the 3D methods audit's
PARTLY "seam placement on a sculpt, a generated mesh, or the high-and-low route's game mesh"): on the high-and-low
route a handle is laid along its cuts - down the front one place on the map a vertex, down the back two; a sculpt's
part leaves its charts and is laid along its cut; a cut too thin to open fails seam_placed there too."""

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


def run(how):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_seam_routes"))
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", "build_seam_routes.py"), "--", how,
                           "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e,
                          encoding="utf-8", errors="replace")


def verdict(r):
    return json.loads(next(x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x))


def check(v, name):
    return next(c for g in v["groups"].values() for c in g["checks"] if c["name"] == name)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = {h: run(h) for h in ("low", "sculpt", "thin", "mixed", "twins")}
        cls.v = {h: verdict(r) for h, r in cls.r.items()}

    def test_the_high_and_low_routes_handle_is_laid_along_its_cuts(self):
        line = next(x for x in self.r["low"].stdout.splitlines() if x.startswith("SEAMS "))
        got = json.loads(line[6:])
        self.assertEqual(got["front"], [1, 1])          # (never cut down the front)
        self.assertEqual(got["back"], [2, 2])           # (cut down the back, as the rule said)
        self.assertTrue(check(self.v["low"], "seam_placed")["ok"])
        self.assertIn("placed seams: Handle 3 piece(s)", self.v["low"]["summary"])
        self.assertGreaterEqual(self.v["low"]["facts"]["uv_parts"]["main"]["given"], 1)   # (laid, then kept)

    def test_a_sculpts_part_is_laid_along_its_cut(self):
        self.assertTrue(check(self.v["sculpt"], "seam_placed")["ok"], self.v["sculpt"]["summary"][:300])
        self.assertIn("placed seams: Ball", self.v["sculpt"]["summary"])

    def test_a_strap_beside_a_sculpt_is_laid_along_its_cut_and_packed_apart_from_the_charts(self):
        v = self.v["mixed"]
        self.assertTrue(check(v, "seam_placed")["ok"], v["summary"][:300])
        self.assertTrue(check(v, "uv_overlap")["ok"], check(v, "uv_overlap"))   # (never on the ball's charts)
        charts = v["facts"].get("uv_charts", {})                                 # (the ball kept its sculpt charts:
        self.assertTrue(any(c.get("charts", 0) > 0 for c in charts.values()), charts)   # the new branch, reached)
        self.assertIn("placed seams: Strap", v["summary"])

    def test_a_placed_part_is_never_stacked_under_its_twin(self):
        v = self.v["twins"]
        self.assertTrue(check(v, "seam_placed")["ok"], check(v, "seam_placed"))

    def test_a_cut_that_cannot_open_fails_on_the_sculpt_route_too(self):
        c = check(self.v["thin"], "seam_placed")
        self.assertFalse(c["ok"])
        self.assertIn("whole on the map", c["fix"])


if __name__ == "__main__":
    unittest.main()
