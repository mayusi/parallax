"""kit/blender/rbx_regions.py: a generated shape's colour REGIONS -> kit finishes (owner 2026-10-16: the made props'
"colour and texture horrible, the model is good" — the form kept, each colour region a real finish). Colour families
(a shadowed red is the red paint, a small grey valve beside it stays), the finish per family, nearest + smoothing."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
import rbx_regions as R  # noqa: E402


class Families(unittest.TestCase):
    def test_a_shadowed_red_is_the_red_paint_a_small_grey_valve_stays(self):
        # (measured on the made extinguisher: 91% (171, 26, 30), 6% (82, 38, 37) = its shading, 3% grey = the valve)
        rgb = np.array([[171, 26, 30]] * 91 + [[82, 38, 37]] * 6 + [[162, 155, 143]] * 3, float)
        got = R.clusters(rgb)
        self.assertEqual(len(got), 2, got)
        self.assertTrue(R.same_family(got[0][0], (171, 26, 30)))
        self.assertAlmostEqual(got[0][1], 0.97, places=2)
        self.assertEqual(R.family(got[1][0])[0], "grey")
        self.assertGreaterEqual(len(got[0][2]), 2)   # (the red family keeps its shades)
        # every face matched against every shade: the shadowed red stays red (one colour per family sent it to grey)
        fams = [g[2] for g in got]
        self.assertEqual(R.nearest_family(np.array([[82.0, 38, 37], [160, 152, 141]]), fams).tolist(), [0, 1])

    def test_black_steel_and_white_are_different_greys(self):
        self.assertFalse(R.same_family((25, 25, 25), (150, 150, 152)))
        self.assertFalse(R.same_family((150, 150, 152), (230, 230, 230)))
        self.assertTrue(R.same_family((140, 116, 83), (96, 80, 61)))   # (two browns: one wood)

    def test_a_stray_family_goes_to_the_biggest(self):
        rgb = np.array([[171, 26, 30]] * 995 + [[30, 200, 40]] * 5, float)   # (0.5%: a stray green speck)
        got = R.clusters(rgb)
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(got[0][1], 1.0, places=3)


class Choose(unittest.TestCase):
    def test_each_family_gets_its_finish(self):
        self.assertEqual(R.choose((171, 27, 31), 0.97, ["a red fire extinguisher"])["finish"], "painted_metal")
        self.assertEqual(R.choose((134, 134, 136), 0.03, ["a red fire extinguisher"])["finish"], "machined_steel")
        # (its measured tone, never the finish's near-white default: the barrel's hoops rendered as white smears)
        self.assertLess(max(R.choose((125, 122, 115), 0.13, ["a wooden wine barrel"])["color"]), 0.25)
        self.assertEqual(R.choose((30, 28, 30), 0.12, ["an extinguisher"])["finish"], "rubber")          # (small)
        self.assertEqual(R.choose((28, 28, 27), 0.87, ["a street lamp post"])["finish"], "painted_metal")  # (body)
        # (the wood scan nearest its colour: the barrel's oak is not the palest scan)
        self.assertEqual(R.choose((142, 116, 83), 0.88, ["a wooden wine barrel"])["scan"], "Wood049")
        self.assertEqual(R.choose((180, 158, 130), 0.88, ["a pale wooden chair"])["scan"], "Wood096")
        self.assertEqual(R.choose((227, 228, 229), 0.13, ["a street lamp"])["finish"], "polymer")
        self.assertEqual(R.choose((142, 116, 83), 0.88, ["a leather bag"])["finish"], "painted_metal")   # (no wood words)


class Assign(unittest.TestCase):
    def test_nearest_then_a_lone_speck_follows_its_neighbours(self):
        targets = np.array([[171, 27, 31], [134, 134, 136]], float)
        rgb = np.array([[170, 30, 30], [168, 25, 33], [140, 136, 130], [172, 28, 29]], float)
        lab = R.nearest(rgb, targets)
        self.assertEqual(lab.tolist(), [0, 0, 1, 0])
        edges = np.array([[0, 2], [1, 2], [3, 2]])   # (face 2 surrounded by red)
        self.assertEqual(R.smooth(lab, edges).tolist(), [0, 0, 0, 0])
        self.assertEqual(R.smooth(lab, np.zeros((0, 2))).tolist(), lab.tolist())


class Despeckle(unittest.TestCase):
    def test_a_small_stray_patch_joins_its_surroundings_a_long_ring_stays(self):
        # a strip of 10 faces: 0-5 wood, 6 a stray steel speck, 7-9 wood; plus faces 10-19 a steel ring (connected)
        lab = np.array([0] * 6 + [1] + [0] * 3 + [1] * 10)
        edges = [(i, i + 1) for i in range(9)] + [(i, i + 1) for i in range(10, 19)] + [(9, 10)]
        area = np.ones(20)
        got = R.despeckle(lab, np.array(edges), area, min_share=0.1)
        self.assertEqual(got[6], 0)                    # (1 face = 5% < 10%: the speck goes)
        self.assertTrue((got[10:] == 1).all())         # (10 faces = 50%: the ring stays)


if __name__ == "__main__":
    unittest.main()
