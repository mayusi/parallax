"""A model's own rig, solved, through REAL builds (kit/selftest/blender/build_rig.py and its twins; the 3D methods
audit, stage R): the named poses are solved and replayed through the kit's own joint rule, the manifest carries
them and the follower joint; a pose out of reach fails; a chain listed out of order stops the build."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import cad_check  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join("build", "_test_rig_build")


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
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = run("build_rig.py")
        cls.v = verdict(cls.good)
        got = next(x for x in cls.good.stdout.splitlines() if x.startswith("RIG "))
        cls.at = json.loads(got[4:])
        cls.far = verdict(run("build_rig_far.py"))
        cls.order = run("build_rig_order.py")
        cls.fold = verdict(run("build_rig_fold.py"))

    def test_the_named_poses_are_solved_and_put_the_tip_on_its_target(self):
        import numpy as np  # noqa: PLC0415

        import rbx_ik  # noqa: PLC0415

        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        arm = self.at["chains"]["Arm"]
        self.assertEqual(arm["joints"], ["Shoulder", "Elbow"])
        self.assertEqual(sorted(arm["poses"]), ["out", "stowed"])
        # the values in the manifest, run forward here on the joints as the manifest holds them
        man = json.load(open(os.path.join(ROOT, OUT, "models", "_selftest_rig_good.manifest.json"), encoding="utf-8"))
        chain = [man["joints"][n] for n in arm["joints"]]
        for pose in arm["poses"].values():
            at, _ = rbx_ik.forward(chain, [pose["values"][n] for n in arm["joints"]], arm["tip"])
            self.assertLess(float(np.linalg.norm(at - np.array(pose["target"]))), 0.02, pose)
            for n, j in zip(arm["joints"], chain):
                self.assertTrue(j["min"] <= pose["values"][n] <= j["max"])
        self.assertIn("chains: Arm (Shoulder > Elbow; 2 of 2 poses met)", self.v["summary"])

    def test_the_follower_joint_is_carried(self):
        self.assertEqual(self.at["wrist"], {"joint": "Elbow", "ratio": -1.0, "offset": 0.0})

    def test_a_pose_out_of_reach_fails_and_is_not_written(self):
        self.assertEqual(self.far["status"], "fail")
        c = next(x for x in self.far["design"] if x["name"] == "reach")
        self.assertIn("Arm / out: the tip stops", c["fix"])
        self.assertIn("the chain is 4.03 long", c["fix"])

    def test_a_pose_clear_joint_by_joint_but_not_together_is_caught(self):
        # (stage P: each joint's own travel is clear of the bollard; the two posed together put the forearm in it)
        self.assertEqual(self.fold["status"], "fail")
        bad = {c["name"]: c for c in self.fold["design"] if c["severity"] == "error"}
        self.assertEqual(sorted(bad), ["reach_clear"], sorted(bad))
        self.assertIn("Arm / down", str(bad["reach_clear"]["value"]))
        self.assertIn("Fore into Bollard", str(bad["reach_clear"]["value"]))

    def test_the_good_arms_poses_are_clear_whole(self):
        self.assertFalse(any(c["name"] == "reach_clear" for c in self.v["design"]))

    def test_a_chain_listed_tip_first_stops_the_build(self):
        self.assertNotEqual(self.order.returncode, 0)
        self.assertIn("list the joints from the base outward", self.order.stderr + self.order.stdout)


if __name__ == "__main__":
    unittest.main()
