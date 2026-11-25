"""A brush stroke that follows the surface (kit/blender/rbx_mask.stroke_distance; the audit, "texture painting": a
picture is projected flat, a brush that follows the surface round a corner is not built - card yp3e). Two faces of a
box meet along an edge, each its own island on the map; a stroke down that edge reaches its radius onto BOTH faces
across the seam, and nothing on the box's far face - which lies within the radius of the stroke as the crow flies
through a thin box, but far round it along the surface."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
import rbx_mask as M  # noqa: E402

N = 96   # texels a side of the map: three islands of 32 x 32, side by side


def box_map(thick=40.0):
    """a box 320 mm wide and tall, `thick` mm deep: its front face (z = 0), its right side face (x = 320) and its
    back face (z = thick), each a 32 x 32 island - 10 mm a texel along the faces"""
    pos = np.zeros((N, N, 3))
    ins = np.zeros((N, N), bool)
    s = np.arange(32) * 10.0 + 5.0
    a, b = np.meshgrid(s, s, indexing="ij")            # (a: down the map's rows, b: across)
    # front: x = b, y = a, z = 0  (its right column ends at x = 315: the edge at x = 320)
    pos[0:32, 0:32] = np.stack([b, a, np.zeros_like(a)], -1)
    # side: x = 320, y = a, z = b * thick / 320 (its own island, laid apart on the map)
    pos[0:32, 32:64] = np.stack([np.full_like(a, 320.0), a, b * thick / 320.0], -1)
    # back: x = 320 - b, y = a, z = thick
    pos[0:32, 64:96] = np.stack([320.0 - b, a, np.full_like(a, thick)], -1)
    ins[0:32, :] = True
    return pos, ins


class Stroke(unittest.TestCase):
    def test_it_wraps_round_the_edge_onto_both_faces(self):
        pos, ins = box_map(thick=320.0)
        stroke = [(320.0, 20.0, 0.0), (320.0, 300.0, 0.0)]          # down the front-side edge
        d = M.stroke_distance(pos, ins, stroke, 60.0)
        front = d[0:32, 0:32][10:20]
        side = d[0:32, 32:64][10:20]
        self.assertTrue(np.isfinite(front[:, -6:]).all())             # (the front's last 60 mm)
        self.assertTrue(np.isfinite(side[:, :6]).all())               # (the side's first 60 mm)
        self.assertFalse(np.isfinite(front[:, :20]).any())            # (beyond the radius: nothing)
        # along the surface: a side texel 45 mm round the edge is ~45 mm away
        self.assertAlmostEqual(float(np.median(side[:, 4])), 45.0, delta=8.0)

    def test_the_far_face_of_a_thin_box_takes_nothing(self):
        pos, ins = box_map(thick=40.0)                                 # (the back face 40 mm behind the front)
        stroke = [(200.0, 20.0, 0.0), (200.0, 300.0, 0.0)]           # (down the middle of the FRONT face)
        d = M.stroke_distance(pos, ins, stroke, 60.0)
        back = d[0:32, 64:96]
        straight = np.linalg.norm(pos[0:32, 64:96] - np.array([200.0, 150.0, 0.0]), axis=-1)
        self.assertTrue((straight[:, 10:14] < 60.0).any())             # (as the crow flies, some of it is in reach)
        self.assertFalse(np.isfinite(back).any())                      # (along the surface, none of it is)
        self.assertTrue(np.isfinite(d[0:32, 0:32]).any())

    def test_values_fall_off_and_a_stroke_off_the_model_is_refused(self):
        v = M.stroke_values(np.array([0.0, 30.0, 59.0, np.inf]), 60.0, soft=0.5)
        self.assertEqual(v[0], 1.0)
        self.assertEqual(v[1], 1.0)
        self.assertLess(v[2], 0.05)
        self.assertEqual(v[3], 0.0)
        pos, ins = box_map()
        with self.assertRaises(ValueError):
            M.stroke_distance(pos, ins, [(160.0, 160.0, 500.0)], 60.0)


if __name__ == "__main__":
    unittest.main()
