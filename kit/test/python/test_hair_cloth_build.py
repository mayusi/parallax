"""Hair as locks scattered along a flow, and a cloth laid by simulation, through REAL builds
(kit/selftest/blender/build_hair.py, build_cloth.py and their twins; the 3D methods audit, stage H)."""

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
OUT = os.path.join("build", "_test_hair_cloth_build")


def run(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                          cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                          errors="replace")


def verdict(r):
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)   # (strict: the kit reads this line the same way)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Hair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = run("build_hair.py")
        cls.v = verdict(cls.good)
        got = next(x for x in cls.good.stdout.splitlines() if x.startswith("HAIR "))
        cls.at = json.loads(got[5:])
        cls.thin = run("build_hair_thin.py")

    def test_the_locks_root_on_the_scalp_and_lie_along_the_flow(self):
        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        self.assertEqual(self.at["locks"], 40)
        self.assertLess(self.at["root_off"], 0.01)                    # every root on the scalp's top
        self.assertLess(self.at["lean_z"], -0.2)                      # swept back: the way `facing` says
        self.assertIn("Lock x40 (scatter on Scalp x40)", self.v["summary"])

    def test_a_lock_that_hangs_is_a_solid_the_right_way_out(self):
        # (the review: past a droop of about 1.2 a lock folded through itself and came out inside out)
        self.assertGreater(self.at["fringe"]["volume"], 0.0)
        self.assertEqual([c["name"] for c in self.v["design"] if c["name"] == "inside_out"], [])

    def test_a_lock_of_one_segment_stops_the_build(self):
        self.assertNotEqual(self.thin.returncode, 0)
        self.assertIn("lock: segments=1 - a whole number from 2 to 8", self.thin.stderr + self.thin.stdout)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Cloth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = verdict(run("build_cloth.py"))
        cls.missed = verdict(run("build_cloth_missed.py"))

    def test_the_cover_rests_on_the_table_hangs_round_it_and_is_not_inside_it(self):
        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        c = self.v["facts"]["cloths"]["Cover"]
        self.assertGreater(c["resting"], 0.3)                         # the part of it that lies on the table
        self.assertEqual(c["through"], 0.0)
        self.assertLess(c["y"][0], 0.8)                               # its hem hangs below the table's top (1.0)
        self.assertAlmostEqual(c["y"][1], 1.05, delta=0.08)           # ... and it lies ON the top, not above it
        self.assertEqual([x["name"] for x in self.v["design"] if x["name"] == "cloth"], [])
        self.assertIn("cloth laid: Cover over Table", self.v["summary"])

    def test_a_cover_dropped_beside_the_table_fails(self):
        self.assertEqual(self.missed["status"], "fail")
        c = next(x for x in self.missed["design"] if x["name"] == "cloth")
        self.assertIn("never came to rest on Table", c["fix"])


if __name__ == "__main__":
    unittest.main()
