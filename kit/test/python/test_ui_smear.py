"""kit ui smear: the trail runs from the figure in the chosen direction, cools toward the tint, and bands differ"""
import importlib.util
import os
import random
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_smear", os.path.join(HERE, "..", "..", "ui", "smear.py"))
smear = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smear)


def figure():
    a = np.zeros((40, 200, 4), dtype=np.float32)
    a[10:30, 150:170] = [255, 40, 40, 255]  # a red block on the right
    return a


class TestSmear(unittest.TestCase):
    def test_the_trail_runs_left_of_the_figure_only(self):
        out = smear.streak(figure(), 100, 0.5, (40, 40), smear.hex_rgb("#0000ff"), 0.8, random.Random(1))
        self.assertGreater(out[20, 120, 3], 0)       # left of the block: trail
        self.assertEqual(out[20, 185, 3], 0)          # right of the block: nothing
        self.assertEqual(out[5, 120, 3], 0)           # above the block's rows: nothing

    def test_the_trail_fades_and_cools_toward_the_tint(self):
        out = smear.streak(figure(), 120, 0.4, (40, 40), smear.hex_rgb("#0000ff"), 0.9, random.Random(2))
        near, far = out[20, 145], out[20, 75]
        self.assertGreater(near[3], far[3])           # alpha decays with distance
        self.assertGreater(far[2] - far[0], near[2] - near[0])  # bluer (the tint) further away

    def test_bands_draw_different_lengths(self):
        out = smear.streak(figure(), 140, 0.6, (2, 3), smear.hex_rgb("#a66cff"), 0.7, random.Random(5))
        reach = [int((out[y, :150, 3] > 0).sum()) for y in range(10, 30)]
        self.assertGreater(len(set(reach)), 2)


if __name__ == "__main__":
    unittest.main()
