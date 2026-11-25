"""THE FITTED BAKE CAGE and THE WRONG SURFACE through REAL builds (kit/selftest/blender/build_cage_fit.py; card urp5):
one part no single depth bakes - a 3 mm high-only dome beside two slots and a leaning fin. The fitted cage bakes both
right, read off the baked map against the truth; one shallow depth loses the dome and fails; the kit's own deep
depth crosses the walls and is said."""

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
OUT = os.path.join("build", "_test_cage_fit_build")


def run(mode):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", "build_cage_fit.py"), "--", mode,
                           "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e,
                          encoding="utf-8", errors="replace")


def verdict(r):
    return json.loads(next(x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x))


def truth(r):
    got = next((x for x in r.stdout.splitlines() if x.startswith("CAGEFIT ")), None)
    assert got, (r.stderr or r.stdout)[-800:]
    return json.loads(got[len("CAGEFIT "):])


def check(v, name):
    return next((c for c in v["groups"]["main"]["checks"] if c["name"] == name), None)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {m: run(m) for m in ("fit", "one", "none", "parts")}
        cls.v = {m: verdict(r) for m, r in cls.runs.items()}
        cls.t = {m: truth(r) for m, r in cls.runs.items()}

    def test_the_fitted_cage_bakes_the_dome_and_the_walls_right_on_the_map(self):
        t = self.t["fit"]
        self.assertGreater(t["wall_texels"], 5000)
        self.assertLess(t["wall_wrong"], 0.01, t)
        self.assertLess(t["dome_err_p50"], 1.0, t)
        self.assertLess(t["dome_err_p90"], 2.0, t)                  # (no wrong ring at its edge)

    def test_the_fitted_cage_passes_its_checks_and_says_its_depths(self):
        v = self.v["fit"]
        for name in ("bake_cross", "bake_cage_pinch", "bake_misses"):
            self.assertTrue(check(v, name)["ok"], (name, check(v, name)))
        low = v["facts"]["low"]["groups"]["main"]
        self.assertEqual(low["cage_set"]["fit"], "all")
        self.assertEqual(low["cage_fit"]["pinched"], 0)
        self.assertGreater(low["cage_fit"]["mm"]["max"], 3.0)      # (deep at the dome ...)
        self.assertLess(low["cage_fit"]["mm"]["min"], 0.61)        # (... and short of the fin's 0.61 mm gap)
        self.assertFalse(low.get("normal_texels_calmed"))          # (nothing in the raw bake needed hiding)
        self.assertIn("cage set: main fit", v["summary"])

    def test_one_shallow_depth_loses_the_dome_and_fails_twice(self):
        v, t = self.v["one"], self.t["one"]
        self.assertGreater(t["dome_err_p50"], 10.0, t)
        self.assertFalse(check(v, "bake_cage")["ok"])
        self.assertIn("needs 2.", check(v, "bake_cage")["value"])   # (the dome lives on the high only: counted)
        cross = check(v, "bake_cross")
        self.assertFalse(cross["ok"])
        self.assertEqual(cross.get("severity"), "error")
        self.assertNotEqual(v["status"], "pass")

    def test_the_kits_own_deep_depth_crosses_the_walls_and_is_said(self):
        v, t = self.v["none"], self.t["none"]
        self.assertLess(t["dome_err_p50"], 1.0, t)                  # (deep enough for the dome ...)
        self.assertGreater(t["wall_wrong"], 0.05, t)                # (... and past the fin, even after calming)
        cross = check(v, "bake_cross")
        self.assertFalse(cross["ok"])
        self.assertEqual(cross.get("severity"), "warn")
        self.assertGreater(v["facts"]["low"]["groups"]["main"]["bake_cross"]["crossed"], 0.05)


    def test_a_fitted_part_beside_another_in_an_exploded_group_bakes_right_and_is_held_as_set(self):
        v, t = self.v["parts"], self.t["parts"]
        self.assertLess(t["wall_wrong"], 0.01, t)
        self.assertLess(t["dome_err_p50"], 1.0, t)
        low = v["facts"]["low"]["groups"]["main"]
        self.assertEqual(low["cage_set"]["fit"], ["Body"])
        self.assertEqual(set(low["bake_cross"]["by_part"]), {"Body", "Peg"})   # (two parts: baked apart)
        crosses = [c for c in v["groups"]["main"]["checks"] if c["name"] == "bake_cross"]
        self.assertEqual(sorted(c["severity"] for c in crosses), ["error", "warn"])   # (the body set, the peg not)
        self.assertTrue(all(c["ok"] for c in crosses), crosses)


if __name__ == "__main__":
    unittest.main()
