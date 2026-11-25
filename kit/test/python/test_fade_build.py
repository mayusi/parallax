"""See-through by degrees, through REAL builds (kit/selftest/blender/build_fade.py and its twin; the 3D methods
audit, stage X): the degrees are in the written colour map's alpha, the group is marked for blending and no other
is, and a fade that leaves everything solid fails."""

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
OUT = os.path.join("build", "_test_fade_build")


def run(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                          cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                          errors="replace")


def verdict(r):
    got = next(x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x)
    return json.loads(got)   # (strict: the kit reads this line the same way)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = run("build_fade.py")
        cls.v = verdict(cls.good)
        line = next((x for x in cls.good.stdout.splitlines() if x.startswith("FADE ")), None)
        assert line, (cls.good.stderr or cls.good.stdout)[-800:]
        cls.at = json.loads(line[5:])
        cls.again = verdict(run("build_fade.py"))            # (its maps from the bake's cache)
        cls.solid = verdict(run("build_fade_solid.py"))

    def test_the_degrees_are_in_the_written_maps_alpha(self):
        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        # the rule: solid = height / 3 - read from the file at a seventh, a half and six sevenths of the pane
        self.assertAlmostEqual(self.at["low"], 0.4 / 3.0, delta=0.03)
        self.assertAlmostEqual(self.at["mid"], 0.5, delta=0.03)
        self.assertAlmostEqual(self.at["high"], 2.6 / 3.0, delta=0.03)
        self.assertGreater(self.at["degrees"], 100)

    def test_the_faded_group_is_marked_for_blending_and_no_other(self):
        self.assertEqual((self.at["alpha_mode"], self.at["alpha_soft"]), ("Transparency", True))
        self.assertIsNone(self.at["post_alpha_mode"])
        said = self.v["facts"]["cutouts"]["pane"][0]
        self.assertTrue(said["soft"])
        self.assertAlmostEqual(said["cut"], 0.5, delta=0.02)
        self.assertIn("faded: Pane 50% clear over", self.v["summary"])
        self.assertNotIn("cut out:", self.v["summary"])

    def test_a_cached_build_says_the_same(self):
        self.assertEqual(self.again["facts"]["cutouts"], self.v["facts"]["cutouts"])

    def test_a_fade_that_leaves_everything_solid_fails(self):
        self.assertEqual(self.solid["status"], "fail")
        names = {c["name"]: c for g in self.solid["groups"].values() for c in g["checks"] if not c["ok"]}
        self.assertIn("cutout", names)
        self.assertIn("the fade takes nothing", str(names["cutout"]["value"]))
        self.assertIn("fade_grades", names)
        self.assertEqual(names["fade_grades"]["severity"], "warn")
        self.assertIn("one degree everywhere", names["fade_grades"]["fix"])

    def test_a_faded_masters_game_version_keeps_its_colour(self):
        # (the review: baked through its own alpha, the game version's map came out a dirty dark fade)
        self.assertEqual(verdict(run("build_fade_master.py"))["status"], "pass")
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(ROOT, "kit", "selftest", "blender", "build_fade_master.py"), "--",
                            "--no-preview", "--optimize"], cwd=ROOT, capture_output=True, text=True, timeout=1800,
                           env=e, encoding="utf-8", errors="replace")
        v = verdict(r)
        self.assertEqual(v["status"], "pass", v["summary"][:400])
        self.assertNotIn("game_fidelity", v["summary"].split(" · ")[0])


if __name__ == "__main__":
    unittest.main()
