"""A bake cage the script sets, through REAL builds (kit/selftest/blender/build_bake_cage.py and its shallow twin;
the 3D methods audit, S3b): the depths are taken and said; a part's own cage changes THAT part's bake and no
other's; a cage under its high's need fails with the depth it needs, and the rays that found nothing are counted."""

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


def run(script, out):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=out)
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                          cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                          errors="replace")


def verdict(r):
    return json.loads(next(x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x))


def line(r, word):
    got = next((x for x in r.stdout.splitlines() if x.startswith(word + " ")), None)
    assert got, (r.stderr or r.stdout)[-800:]
    return json.loads(got[len(word) + 1:])


def check(v, name, group="main"):
    return next(c for c in v["groups"][group]["checks"] if c["name"] == name)

OUT = os.path.join("build", "_test_bake_cage_build")


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = run("build_bake_cage.py", OUT)
        cls.v = verdict(cls.good)
        cls.bad = run("build_bake_cage_shallow.py", OUT)
        cls.b = verdict(cls.bad)

    def test_the_depths_the_script_set_are_taken_and_said(self):
        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        low = self.v["facts"]["low"]["groups"]["main"]
        self.assertEqual(low["cage_mm"], 2.0)
        self.assertEqual(low["cage_set"]["group_mm"], 2.0)
        self.assertEqual(low["cage_set"]["parts"]["LugA"]["mm"], 3.0)
        self.assertGreater(low["cage_set"]["parts"]["LugA"]["need_mm"], 0.0)
        self.assertIn("cage set: main 2 mm, LugA 3 mm", self.v["summary"])
        self.assertTrue(check(self.v, "bake_cage")["ok"])

    def test_a_good_cage_leaves_no_texel_unbaked(self):
        at = line(self.good, "CAGE")
        self.assertGreater(at["LugA"]["texels"], 1000)
        self.assertEqual((at["LugA"]["dark"], at["LugB"]["dark"]), (0, 0))
        self.assertLessEqual(self.v["facts"]["low"]["groups"]["main"]["bake_misses"]["missed"], 0.01)
        self.assertTrue(check(self.v, "bake_misses")["ok"])

    def test_a_parts_own_cage_changes_that_parts_bake_alone(self):
        at = line(self.bad, "CAGE")
        self.assertGreater(at["LugA"]["dark"], 200)                  # its rays started inside its high
        self.assertEqual(at["LugB"]["dark"], 0)                      # the part beside it kept the group's cage

    def test_a_cage_under_its_highs_need_fails_with_the_depth_it_needs(self):
        self.assertEqual(self.b["status"], "fail")
        c = check(self.b, "bake_cage")
        self.assertFalse(c["ok"])
        self.assertIn("LugA: its cage is 0.02 mm", c["fix"])
        self.assertIn("at least", c["fix"])
        m = check(self.b, "bake_misses")
        self.assertFalse(m["ok"])
        self.assertEqual(m["severity"], "error")                     # (the script set the cage: an error)
        self.assertEqual(list(self.b["facts"]["low"]["groups"]["main"]["bake_misses"]["parts"]), ["LugA"])


if __name__ == "__main__":
    unittest.main()
