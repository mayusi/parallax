"""A model's own motion made ready for the game (kit/blender/rbx_cycleplay.py; the owner's method lists: keyframes,
curves, loops, animation export, animation compression; the 3D methods audit, G3): the table, its thinning, what it
plays at a time, a loop held closed."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_cycleplay as P  # noqa: E402

JOINTS = {"wheel": {"name": "Wheel", "kind": "hinge"}, "pin": {"name": "Pin", "kind": "slide"}}


def eased(a, b, n):
    out = []
    for i in range(n + 1):
        w = i / n
        w = w * w * (3 - 2 * w)
        out.append(a + (b - a) * w)
    return out


def cycle(loop_back=False):
    """a wheel turning 0 -> 90 over 24 frames (eased), a pin held, then let down 0.1 over the last 6"""
    wheel = eased(0.0, 90.0, 24)
    frames = {}
    for i, w in enumerate(wheel):
        frames[1 + i] = {"wheel": w, "pin": 0.0}
    for i, p in enumerate(eased(0.0, 0.1, 6)[1:]):
        frames[26 + i] = {"wheel": 0.0 if loop_back else 90.0, "pin": 0.0 if loop_back else p}
    return frames


class Table(unittest.TestCase):
    def test_every_frame_every_keyed_joint_by_its_joints_name(self):
        t = P.table(cycle(), JOINTS, 24)
        self.assertEqual((t["joints"], t["kinds"], t["fps"]), (["Pin", "Wheel"], ["slide", "hinge"], 24))
        self.assertEqual(len(t["times"]), 31)
        self.assertEqual((t["times"][0], t["times"][24]), (0.0, 1.0))
        self.assertEqual(t["values"][0], [0.0, 0.0])
        self.assertEqual(t["values"][24], [0.0, 90.0])
        self.assertAlmostEqual(t["values"][-1][0], 0.1)

    def test_a_joint_never_keyed_stands_at_rest_and_a_fixed_one_is_left_out(self):
        # (the build checks the cycle with every unkeyed joint at rest: the game must play the same)
        joints = dict(JOINTS, plate={"name": "Plate", "kind": "fixed"})
        t = P.table({1: {"wheel": 0.0}, 2: {"wheel": 5.0}}, joints, 24)
        self.assertEqual(t["joints"], ["Pin", "Wheel"])
        self.assertEqual(t["values"], [[0.0, 0.0], [0.0, 5.0]])


class Thin(unittest.TestCase):
    def test_a_straight_run_keeps_its_two_ends_and_a_held_joint_costs_nothing(self):
        frames = {f: {"wheel": 3.0 * (f - 1), "pin": 0.0} for f in range(1, 31)}
        t = P.thin(P.table(frames, JOINTS, 24))
        self.assertEqual(len(t["times"]), 2)
        self.assertEqual(t["values"], [[0.0, 0.0], [0.0, 87.0]])

    def test_an_eased_curve_keeps_the_keys_a_line_cannot_stand_in_for_and_stays_within_the_tolerance(self):
        full = P.table(cycle(), JOINTS, 24)
        t = P.thin(full)
        self.assertLess(len(t["times"]), len(full["times"]))
        self.assertGreater(len(t["times"]), 6)                            # an ease is not two keys
        deg, studs = P.worst(full, t)
        self.assertLessEqual(deg, P.TOL_DEG + 1e-9)
        self.assertLessEqual(studs, P.TOL_STUDS + 1e-9)
        self.assertEqual((t["times"][0], t["times"][-1]), (full["times"][0], full["times"][-1]))

    def test_one_or_two_keys_are_left_alone(self):
        t = P.table({1: {"wheel": 0.0}, 2: {"wheel": 5.0}}, JOINTS, 24)
        self.assertEqual(P.thin(t)["times"], t["times"])

    def test_a_tiny_slide_keeps_its_easing(self):
        # the review's find: a pin that moves a hundredth of a stud was thinned to two keys (10% of its travel off)
        frames = {1 + i: {"pin": v, "wheel": 0.0} for i, v in enumerate(eased(0.0, 0.01, 12))}
        full = P.table(frames, JOINTS, 24)
        t = P.thin(full)
        self.assertGreater(len(t["times"]), 2)
        self.assertLessEqual(P.worst(full, t)[1], 0.02 * 0.01 + 1e-9)

    def test_a_long_straight_run_is_thinned_in_windows_and_fast(self):
        import time
        frames = {f: {"wheel": 0.05 * f, "pin": 0.0} for f in range(1, 2001)}
        t0 = time.time()
        t = P.thin(P.table(frames, JOINTS, 24))
        self.assertLess(time.time() - t0, 1.5)
        self.assertLessEqual(len(t["times"]), 2000 // P.WINDOW + 3)
        self.assertEqual(P.worst(P.table(frames, JOINTS, 24), t)[0] < 1e-6, True)


class At(unittest.TestCase):
    def setUp(self):
        self.t = {"fps": 24, "joints": ["Wheel"], "kinds": ["hinge"], "times": [0.0, 1.0, 2.0],
                  "values": [[0.0], [90.0], [0.0]]}

    def test_a_straight_line_between_the_keys_round_a_time(self):
        self.assertEqual(P.at(self.t, 0.5), [45.0])
        self.assertEqual(P.at(self.t, 1.0), [90.0])
        self.assertEqual(P.at(self.t, 1.75), [22.5])

    def test_before_and_after_hold_and_a_loop_comes_round(self):
        self.assertEqual(P.at(self.t, -1.0), [0.0])
        self.assertEqual(P.at(self.t, 9.0), [0.0])
        self.assertEqual(P.at(self.t, 2.5, loop=True), [45.0])
        self.assertEqual(P.at(self.t, 4.0, loop=True), [0.0])


class Loop(unittest.TestCase):
    def test_a_cycle_that_ends_where_it_began_may_loop(self):
        self.assertIsNone(P.loop_problem(P.table(cycle(loop_back=True), JOINTS, 24)))

    def test_one_that_ends_elsewhere_names_the_joint_and_the_jump(self):
        said = P.loop_problem(P.table(cycle(), JOINTS, 24))
        self.assertIn("Pin ends at 0.1 and begins at 0 studs", said)
        t = {"fps": 24, "joints": ["Wheel"], "kinds": ["hinge"], "times": [0.0, 1.0], "values": [[0.0], [90.0]]}
        self.assertIn("jump 90 degrees", P.loop_problem(t))
        t["values"][1] = [0.4]                                            # within half a degree: closed
        self.assertIsNone(P.loop_problem(t))

    def test_a_whole_turn_on_is_where_it_began(self):
        # the review's find: a wheel spun 0 -> 360 was refused as a jump of 360 degrees
        t = {"fps": 24, "joints": ["Wheel"], "kinds": ["hinge"], "times": [0.0, 2.0], "values": [[0.0], [360.0]]}
        self.assertIsNone(P.loop_problem(t))
        t["values"][1] = [-720.3]
        self.assertIsNone(P.loop_problem(t))
        t["values"][1] = [361.0]
        self.assertIn("Wheel", P.loop_problem(t))
        slide = {"fps": 24, "joints": ["Pin"], "kinds": ["slide"], "times": [0.0, 2.0], "values": [[0.0], [360.0]]}
        self.assertIn("Pin", P.loop_problem(slide))                       # (a slide has no whole turn)


if __name__ == "__main__":
    unittest.main()
