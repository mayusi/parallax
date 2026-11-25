"""a place a LONG chain cannot take is PROVEN, not guessed (kit/blender/rbx_ik.py prove_far, his V3 list, 3D stage G.1d):
the grid sweep stops at SWEEP_JOINTS joints and its even grid cannot rule out a place just past the bar; branch and
bound splits the joints' values where it matters and rules a box out only by the sweep's own bound."""

import os
import sys
import time
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_ik as K  # noqa: E402


def arm(n, limit):
    """a flat arm of n one-stud links along +x, each hinge turning about z, held to +-limit degrees"""
    return [{"kind": "hinge", "pivot": (float(i), 0.0, 0.0), "axis": (0.0, 0.0, 1.0), "min": -limit, "max": limit}
            for i in range(n)]


class LongChains(unittest.TestCase):
    def test_six_stiff_hinges_cannot_curl_round_proven_by_their_limits(self):
        chain, tip, target = arm(6, 10.0), (6.0, 0.0, 0.0), (0.0, 3.0, 0.0)   # 3 studs off: well inside its length
        self.assertGreater(len(chain), K.SWEEP_JOINTS)                         # (the grid would not sweep it)
        found = K.reach(chain, tip, target)
        t0 = time.time()
        said = K.problem("Arm", found, target, chain, tip)
        self.assertLess(time.time() - t0, 30.0)
        self.assertIn("its joints' limits stop it, proven", said)
        self.assertNotIn("not proven", said)

    def test_a_flat_chain_cannot_lift_its_tip_off_its_plane_at_any_angle(self):
        chain, tip, target = arm(6, 10.0), (6.0, 0.0, 0.0), (3.0, 0.0, 2.0)
        said = K.problem("Arm", K.reach(chain, tip, target), target, chain, tip)
        self.assertIn("cannot turn its tip there at any angle, proven", said)
        bound = float(said.split("nearer than ")[1].split(" studs")[0])
        self.assertGreater(bound, 1.0)            # (the truth is 2 studs: every pose lies in its plane)
        self.assertLessEqual(bound, 2.0)

    def test_a_flat_chain_s_plane_is_exact_and_a_turret_is_not_flat(self):
        chain, tip = arm(6, 10.0), (6.0, 0.0, 0.0)
        self.assertAlmostEqual(K.planar_bound(chain, tip, (3.0, 0.0, 2.0)), 2.0)
        self.assertAlmostEqual(K.planar_bound(chain, tip, (3.0, 1.0, 0.0)), 0.0)
        lift = chain + [{"kind": "slide", "pivot": (6.0, 0, 0), "axis": (0, 0, 1), "min": 0.0, "max": 1.5}]
        self.assertAlmostEqual(K.planar_bound(lift, tip, (3.0, 0.0, 2.0)), 0.5)     # (a slide lifts it 1.5)
        turret = [{"kind": "hinge", "pivot": (0, 0, 0), "axis": (0, 1, 0), "min": -180, "max": 180}] + chain
        self.assertIsNone(K.planar_bound(turret, tip, (3.0, 0.0, 2.0)))

    def test_a_turret_carrying_a_flat_arm_is_bounded_at_every_angle(self):
        # (a crane: a turret turning about x, then a flat boom of 5 hinges about z: at each turret angle the boom
        #  works in one plane, so a place off that plane is as far as it lies off it - proven over the turret's range)
        boom = arm(5, 180.0)
        turret = [{"kind": "hinge", "pivot": (0.0, 0.0, 0.0), "axis": (1.0, 0.0, 0.0), "min": -180, "max": 180}]
        chain, tip = turret + boom, (5.0, 0.0, 0.0)
        self.assertIsNone(K.planar_bound(chain, tip, (9.0, 0.0, 0.0)))          # (not flat: the turret turns it)
        b = K.turret_planar_bound(chain, tip, (0.0, 0.0, 3.0), -180, 180)
        self.assertIsNotNone(b)
        self.assertLessEqual(b, 0.01)                                           # (reachable: never ruled out)
        far = K.turret_planar_bound(chain, tip, (0.0, 0.0, 3.0), -5, 5)          # (the turret held near 0)
        self.assertGreater(far, 2.5)                                            # (3 studs off the boom's plane)
        rng = np.random.default_rng(3)                                          # (a true lower bound)
        poses = np.column_stack([rng.uniform(-5, 5, 20000), rng.uniform(-180, 180, (20000, 5))])
        nearest = float(np.linalg.norm(K.forward_many(chain, poses, tip) - np.array([0.0, 0.0, 3.0]), axis=1).min())
        self.assertGreaterEqual(nearest, far)

    def test_the_bound_is_a_true_lower_bound_and_a_reachable_place_is_found(self):
        chain, tip = arm(5, 30.0), (5.0, 0.0, 0.0)
        lo, hi = [-30.0] * 5, [30.0] * 5
        far = (0.0, 4.0, 0.0)
        best, bound, met = K.prove_far(chain, tip, far, lo, hi, 0.02)
        self.assertFalse(met)
        self.assertIsNotNone(bound)
        rng = np.random.default_rng(7)                                        # no pose comes nearer than the bound
        poses = rng.uniform(-30.0, 30.0, size=(20000, 5))
        nearest = float(np.linalg.norm(K.forward_many(chain, poses, tip) - np.array(far), axis=1).min())
        self.assertGreaterEqual(nearest, bound)
        self.assertGreaterEqual(nearest + 1e-9, best - (best - bound))
        bent = K.forward(chain, [20.0, 15.0, 10.0, 5.0, 0.0], tip)[0]       # a place a pose inside the limits takes
        _best, _bound, met = K.prove_far(chain, tip, bent, lo, hi, 0.02)
        self.assertTrue(met)

    def test_a_tiny_budget_says_not_proven(self):
        # (a place near the edge of what it reaches: no first box rules it out, and three boxes prove nothing)
        chain, tip, target = arm(6, 10.0), (6.0, 0.0, 0.0), (5.6, 1.9, 0.0)
        self.assertIsNone(K.prove_far(chain, tip, target, [-10.0] * 6, [10.0] * 6, 0.02, budget=3)[1])


if __name__ == "__main__":
    unittest.main()
