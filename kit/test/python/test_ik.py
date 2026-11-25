"""A model's own rig, solved (kit/blender/rbx_ik.py; the owner's method lists: IK, constraints; the 3D methods
audit, stage R)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_ik as K  # noqa: E402

# an arm in the xy plane: a shoulder at the origin and an elbow 2 studs up, both turning about z; the hand 2 more
ARM = [{"kind": "hinge", "pivot": (0, 0, 0), "axis": (0, 0, 1), "min": -170, "max": 170},
       {"kind": "hinge", "pivot": (0, 2, 0), "axis": (0, 0, 1), "min": -150, "max": 150}]
HAND = (0, 4, 0)


class Forward(unittest.TestCase):
    def test_at_rest_the_tip_is_where_it_was_built(self):
        at, frames = K.forward(ARM, [0, 0], HAND)
        self.assertTrue(np.allclose(at, HAND))
        self.assertTrue(np.allclose(frames[1][0], (0, 2, 0)))

    def test_a_joint_carries_everything_after_it(self):
        at, frames = K.forward(ARM, [90, 0], HAND)                    # the shoulder a quarter turn: the arm lies
        self.assertTrue(np.allclose(at, (-4, 0, 0), atol=1e-9))       # along -x (a turn about +z from +y)
        self.assertTrue(np.allclose(frames[1][0], (-2, 0, 0), atol=1e-9))
        at, _ = K.forward(ARM, [0, 90], HAND)                         # the elbow alone: the forearm turns
        self.assertTrue(np.allclose(at, (-2, 2, 0), atol=1e-9))

    def test_a_slide_moves_along_its_axis_as_posed(self):
        boom = [{"kind": "hinge", "pivot": (0, 0, 0), "axis": (0, 0, 1), "min": -90, "max": 90},
                {"kind": "slide", "pivot": (0, 1, 0), "axis": (0, 1, 0), "min": 0, "max": 3}]
        at, _ = K.forward(boom, [90, 2], (0, 2, 0))
        self.assertTrue(np.allclose(at, (-4, 0, 0), atol=1e-9))       # turned, then run out 2 along the boom


class Reach(unittest.TestCase):
    def test_a_target_within_reach_is_met(self):
        for target in ((2, 2, 0), (-1, 3, 0), (3, -1, 0), (1.5, 0.5, 0)):   # (nearer than 1.04 the elbow's limit stops it)
            found = K.reach(ARM, HAND, target)
            at, _ = K.forward(ARM, found["values"], HAND)
            self.assertLess(found["miss"], 0.01, target)
            self.assertLess(float(np.linalg.norm(at - np.array(target))), 0.01, target)
            self.assertIsNone(K.problem("Arm", found, target, ARM, HAND))

    def test_a_target_out_of_reach_is_said_with_why(self):
        found = K.reach(ARM, HAND, (9, 0, 0))
        self.assertAlmostEqual(found["miss"], 5.0, delta=0.05)        # 9 away, 4 long: stretched straight at it
        said = K.problem("Arm", found, (9, 0, 0), ARM, HAND)
        self.assertIn("Arm: the tip stops 5.00 studs short", said)
        self.assertIn("9.00 studs from the first joint and the chain is 4.00 long", said)

    def test_limits_hold_and_are_named(self):
        stiff = [dict(ARM[0], min=-10, max=10), dict(ARM[1], min=-10, max=10)]
        found = K.reach(stiff, HAND, (-4, 0, 0))
        self.assertTrue(all(-10 <= v <= 10 for v in found["values"]))
        self.assertEqual(found["held"], [0, 1])
        self.assertIn("its joints' limits stop it", K.problem("Arm", found, (-4, 0, 0), stiff, HAND))

    def test_every_place_a_chain_can_take_is_found(self):
        # (the review: 2,000 places made by posing the chain inside its limits - one in six was given up on)
        rng = np.random.default_rng(3)
        chains = {
            "arm": (ARM, HAND),
            "three in a plane": ([dict(ARM[0]), dict(ARM[1]),
                                  {"kind": "hinge", "pivot": (0, 4, 0), "axis": (0, 0, 1), "min": -120, "max": 120}],
                                 (0, 5.5, 0)),
            "turret, boom, stick": ([{"kind": "hinge", "pivot": (0, 0, 0), "axis": (0, 1, 0), "min": -180, "max": 180},
                                     {"kind": "hinge", "pivot": (0, 1, 0), "axis": (0, 0, 1), "min": -100, "max": 100},
                                     {"kind": "hinge", "pivot": (0, 3, 0), "axis": (0, 0, 1), "min": -140, "max": 140}],
                                    (0, 5, 0)),
            "hinge, slide, hinge": ([{"kind": "hinge", "pivot": (0, 0, 0), "axis": (0, 0, 1), "min": -90, "max": 90},
                                     {"kind": "slide", "pivot": (0, 1, 0), "axis": (0, 1, 0), "min": 0, "max": 2},
                                     {"kind": "hinge", "pivot": (0, 2, 0), "axis": (0, 0, 1), "min": -120, "max": 120}],
                                    (0, 3.5, 0)),
        }
        for name, (chain, tip) in chains.items():
            missed = 0
            for _ in range(150):
                made = [rng.uniform(j["min"], j["max"]) for j in chain]
                target, _ = K.forward(chain, made, tip)
                found = K.reach(chain, tip, target)
                at, _ = K.forward(chain, found["values"], tip)
                self.assertAlmostEqual(found["miss"], float(np.linalg.norm(at - target)), delta=1e-3)
                missed += found["miss"] > 0.02
            self.assertLessEqual(missed, 1, name)                     # (150 places: one stray at most)

    def test_a_straight_arm_reaches_a_place_on_its_own_line(self):
        found = K.reach(ARM, HAND, (0, 3, 0))                         # straight up, nearer: it must BEND to get there
        self.assertLess(found["miss"], 0.02)
        self.assertGreater(found["starts"], 1)

    def test_limits_given_the_other_way_round_are_the_same_limits(self):
        back = [dict(ARM[0], min=170, max=-170), dict(ARM[1], min=150, max=-150)]
        self.assertLess(K.reach(back, HAND, (2, 2, 0))["miss"], 0.02)

    def test_a_slide_takes_up_what_the_hinges_cannot(self):
        boom = [{"kind": "hinge", "pivot": (0, 0, 0), "axis": (0, 0, 1), "min": -90, "max": 90},
                {"kind": "slide", "pivot": (0, 1, 0), "axis": (0, 1, 0), "min": 0, "max": 3}]
        found = K.reach(boom, (0, 2, 0), (-3.5, 0, 0))
        self.assertLess(found["miss"], 0.01)
        self.assertAlmostEqual(found["values"][0], 90, delta=0.5)
        self.assertAlmostEqual(found["values"][1], 1.5, delta=0.02)
        self.assertAlmostEqual(K.span(boom, (0, 2, 0)), 5.0)


if __name__ == "__main__":
    unittest.main()
