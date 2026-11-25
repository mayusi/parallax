"""THE FADES A GAME PLAYS (kit/blender/rbx_cycleplay.blend / fades): the game's own blend (src/kit/ModelRules.blend:
smoothstep in time, a straight line in the joints, a joint the new cycle moves jumps there if it was not moving, one
it does not eases back to rest) and the fades a build checks."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "blender")))
import rbx_cycleplay as P  # noqa: E402


class Blend(unittest.TestCase):
    def test_the_games_blend_eased_on_a_straight_line(self):
        self.assertEqual(P.blend({"A": 0.0}, {"A": 10.0}, 0.5)["A"], 5.0)        # (smoothstep's middle is the middle)
        self.assertAlmostEqual(P.blend({"A": 0.0}, {"A": 10.0}, 0.25)["A"], 10 * 0.15625)
        self.assertEqual(P.blend({}, {"A": 10.0}, 0.1)["A"], 10.0)              # (not moving before: it jumps)
        self.assertAlmostEqual(P.blend({"B": 4.0}, {"A": 1.0}, 0.5)["B"], 2.0)  # (not in the new cycle: to rest)
        self.assertEqual(P.blend({"A": 3.0}, {"A": 9.0}, 2.0)["A"], 9.0)        # (clamped)


class Fades(unittest.TestCase):
    def test_from_rest_from_a_one_shots_end_and_from_moments_of_a_loop(self):
        loop = {f: {"W": float(f)} for f in range(1, 21)}
        shot = {f: {"P": float(f)} for f in range(1, 6)}
        got = P.fades([("Turn", True, loop), ("Seat", False, shot)], joints=("W", "P"))
        labels = [lb for lb, _s in got]
        self.assertIn("from rest into Turn", labels)
        self.assertIn("from Seat at frame 5 into Turn", labels)                # (a one-shot: its end only)
        self.assertNotIn("from Seat at frame 1 into Turn", labels)
        turn_from = [lb for lb in labels if lb.startswith("from Turn") and lb.endswith("into Seat")]
        self.assertEqual(len(turn_from), P.FADE_FROM)                         # (a loop: cut off anywhere)
        rest = dict(got)["from rest into Seat"]
        self.assertEqual(rest[0]["W"], 0.0)                                   # (every joint stands at 0 at rest)
        self.assertEqual(len(rest), len(P.FADE_STEPS))


if __name__ == "__main__":
    unittest.main()
