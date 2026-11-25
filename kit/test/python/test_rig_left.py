"""What the rig stage's review left (card ver5): a.joint takes its limits the right way round or says so (a min past
its max was sorted quietly by the solvers)."""

import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class Limits(unittest.TestCase):
    def run_script(self, mn, mx):
        src = ("import sys\n"
               f"sys.path.insert(0, {os.path.join(ROOT, 'kit', 'blender')!r})\n"
               "import rbx\n"
               "a = rbx.Asset('_selftest_joint_limits', tex=64, size=(1, 1, 1))\n"
               f"a.joint('Lid', 'lid', 'hinge', (1, 0, 0), min={mn}, max={mx})\n"
               "print('JOINT OK')\n")
        path = os.path.join(tempfile.mkdtemp(), "joint.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src)
        return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", path], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)

    def test_the_wrong_way_round_is_said(self):
        out = self.run_script(90, 10)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn('joint "Lid": min=90 is past max=10', out.stdout + out.stderr)

    def test_the_right_way_round_is_taken(self):
        out = self.run_script(-30, 90)
        self.assertIn("JOINT OK", out.stdout)


import sys  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import numpy as np  # noqa: E402
import rbx_ik  # noqa: E402

ARM = [{"kind": "hinge", "pivot": (0, 0, 0), "axis": (0, 0, 1), "min": 0, "max": 90},
       {"kind": "hinge", "pivot": (2, 0, 0), "axis": (0, 0, 1), "min": 0, "max": 90}]
TIP = (4, 0, 0)


class ProvenWhy(unittest.TestCase):
    """a pose that cannot be met is given a PROVEN reason where one can be had (card ver5: the solver's guess)"""

    def why(self, target, chain=ARM, tip=TIP):
        return rbx_ik.problem("Arm / x", rbx_ik.reach(chain, tip, target), target, chain, tip)

    def test_the_sweep_agrees_with_one_pose_at_a_time(self):
        v = np.array([[10.0, 20.0], [45.0, -30.0], [0.0, 0.0]])
        self.assertTrue(np.allclose(rbx_ik.forward_many(ARM, v, TIP), [rbx_ik.forward(ARM, x, TIP)[0] for x in v]))

    def test_behind_its_limits_is_proven_the_limits(self):
        said = self.why((0, -3, 0))
        self.assertIn("its joints' limits stop it, proven", said)

    def test_off_the_plane_its_hinges_turn_in_is_proven_the_layout(self):
        said = self.why((0, 0, 2))
        self.assertIn("cannot turn its tip there at any angle, proven", said)
        bound = float(said.split("nearer than ")[1].split(" studs")[0])
        self.assertLessEqual(bound, 2.0)   # (a lower bound: the true nearest is 2 studs off the plane)
        self.assertGreater(bound, 1.5)

    def test_a_chain_too_long_for_the_grid_is_proven_by_branch_and_bound(self):
        # (until 2026-11-18 a chain of 5 joints was not swept and its reason said "not proven" - his V3 list, 3D
        #  stage G.1d, asked for the proof; branch and bound gives it at any length)
        long_ = [{"kind": "hinge", "pivot": (float(i), 0, 0), "axis": (0, 0, 1), "min": 0, "max": 10}
                 for i in range(5)]
        said = self.why((0, -4, 0), long_, (5, 0, 0))
        self.assertIn("its joints' limits stop it, proven", said)
        self.assertNotIn("not proven", said)

    def test_a_proof_out_of_budget_still_says_it_is_a_guess(self):
        # (hinges about three different axes, as a robot arm's: neither a flat chain's plane nor a turret's sweep
        #  bounds it - only branch and bound could, and three boxes prove nothing)
        axes = [(0, 0, 1), (0, 1, 0), (1, 0, 0)]
        long_ = [{"kind": "hinge", "pivot": (float(i), 0, 0), "axis": axes[i % 3], "min": -10, "max": 10}
                 for i in range(6)]
        keep = rbx_ik.BNB_BUDGET
        rbx_ik.BNB_BUDGET = 3
        try:
            said = self.why((5.5, 2.0, 1.0), long_, (6, 0, 0))   # (near the edge of what it reaches: no first box
            #                                                     rules it out, and the solver stops 0.45 short)
        finally:
            rbx_ik.BNB_BUDGET = keep
        self.assertIn("not proven", said)                 # (three boxes prove nothing about its limits)
        self.assertIn("ran out of its budget", said)

    def test_past_its_length_is_said_as_before(self):
        self.assertIn("the chain is 4.00 long", self.why((9, 0, 0)))


if __name__ == "__main__":
    unittest.main()
