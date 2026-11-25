"""The build's seam check on a REAL baked model (kit/selftest/blender/check_seams_cases.py): a ball's map meets
itself across its seams, the same mesh against a damaged copy of its map fails and says where, a box's seams (all on
sharp edges) are not judged."""

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


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_seams_build"))
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(ROOT, "kit", "selftest", "blender", "check_seams_cases.py"), "--",
                            "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e,
                           encoding="utf-8", errors="replace")
        line = next((x for x in r.stdout.splitlines() if x.startswith("SEAMS ")), None)
        assert line, (r.stderr or r.stdout)[-800:]
        cls.out = json.loads(line[6:])
        verdict = next(x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x)
        cls.v = json.loads(verdict)

    def test_a_baked_balls_map_meets_itself_and_the_build_says_so(self):
        ball = self.out["built"]["ball"]
        self.assertGreater(ball["edges"], 40)                    # (its seams run over smooth surface: judged)
        self.assertEqual(ball["share"], 0.0)
        self.assertLess(ball["p95"], 0.02)
        self.assertIn("seams: ball meet (100% of their length judged)", self.v["summary"])
        self.assertEqual((ball["floor"], ball["beyond"]), (0.0, 0.0))
        check = next(c for c in self.v["groups"]["ball"]["checks"] if c["name"] == "seams")
        self.assertTrue(check["ok"])
        self.assertEqual(self.v["facts"]["seams"]["ball"]["edges"], ball["edges"])

    def test_a_boxs_seams_are_cut_but_none_is_judged(self):
        slab = self.out["built"]["main"]
        self.assertEqual((slab["edges"], slab["share"]), (0, 0.0))
        self.assertGreater(slab["cut_edges"], 0)
        self.assertFalse(any(c["name"] == "seams" for c in self.v["groups"]["main"]["checks"]))

    def test_a_damaged_map_fails_the_check_and_says_where(self):
        bad = self.out["damaged"]
        self.assertGreater(bad["facts"]["beyond"], 0.3)
        self.assertLess(bad["facts"]["floor"], 0.05)              # (the damage is at the seams, not in the islands)
        self.assertEqual([(c["name"], c["ok"], c["severity"]) for c in bad["checks"]], [("seams", False, "warn")])
        self.assertIn("does not meet itself", bad["checks"][0]["fix"])
        self.assertIn("/255 at (", bad["checks"][0]["fix"])
        at = bad["facts"]["worst"][0]["at"]
        self.assertTrue(1.0 <= at[1] <= 5.0 and abs(at[0]) <= 2.01 and abs(at[2]) <= 2.01)   # on the ball, studs
        self.assertEqual(self.out["again"], {"share": 0.0, "ok": True})


if __name__ == "__main__":
    unittest.main()
