"""game_fidelity's close-up follows the model's size (card 3aan): CLOSE_MM_PX a pixel, CLOSE_MIN to CLOSE_RES px, a
whole number of windows - a small part is no longer judged eight times finer than the car rim it was tuned on."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_game_fidelity import _lift  # noqa: E402

G = _lift("game_fidelity.py", {"close_res", "CLOSE_RES", "CLOSE_MM_PX", "CLOSE_MIN", "WIN"})


class CloseScale(unittest.TestCase):
    def test_the_car_rim_is_judged_as_tuned(self):
        self.assertEqual(G["close_res"](525.0 / 280.0, 280.0), 2048)   # (its 525 mm frame: 2048 px, as before)

    def test_a_small_part_at_the_rims_scale(self):
        px = G["close_res"](125.0 / 280.0, 280.0)                        # (the 112 mm plate's frame)
        self.assertEqual(px % G["WIN"], 0)
        self.assertLessEqual(125.0 / px, 0.26)
        self.assertGreaterEqual(125.0 / px, 0.2)

    def test_the_floor_and_the_ceiling(self):
        self.assertEqual(G["close_res"](0.01, 280.0), G["CLOSE_MIN"])
        self.assertEqual(G["close_res"](50.0, 280.0), G["CLOSE_RES"])


if __name__ == "__main__":
    unittest.main()
