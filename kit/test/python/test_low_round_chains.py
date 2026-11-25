"""The high-and-low route's mid-poly rounds (kit/blender/rbx.py, _chain_widths): one width per chain of edges, so a
chain is bevelled in one pass. The fixture kit/selftest/blender/check_low_round_chains.py builds the car rim's spoke
(fillet_mm=3): its low must round all four 134 mm arm edges with no crease left along them (bevelled at different
widths in separate passes, the arm and its flare left a 43-75 degree crease the whole arm long: the bright slit of
rework 6ebz). The spoke's tip, buried in the barrel, keeps short sharp edges (too little room for a round)."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER) and cad_check.cad_python(), "Blender or the CAD env not found")
class LowRoundChains(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = os.path.join(REPO, "kit", "selftest", "blender", "check_low_round_chains.py")
        run = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script], cwd=REPO, capture_output=True,
                             text=True, timeout=900)
        line = next((ln for ln in run.stdout.splitlines() if ln.startswith("LOWROUND ")), None)
        assert line, (run.stderr or run.stdout)[-800:]
        cls.out = json.loads(line[len("LOWROUND "):])

    def test_no_crease_along_the_arm(self):
        # (the arm is 134 mm; the tip's unrounded edges are under 25 mm)
        self.assertLess(self.out["longest_hard_mm"], 40.0, self.out)

    def test_rounded_in_whole_chains(self):
        rounds = self.out["low_rounds"] or []
        self.assertTrue(rounds, self.out)
        self.assertGreaterEqual(sum(n for _w, n in rounds), 12, self.out)   # (the 12 edges with room)
        self.assertGreaterEqual(self.out["segments"], 3, self.out)


if __name__ == "__main__":
    unittest.main()
