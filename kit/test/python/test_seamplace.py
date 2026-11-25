"""Seams the author places (kit/blender/rbx_seamplace.py; the owner's method lists: seam placement; the 3D methods
audit, S3b)."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_seamplace as S  # noqa: E402

# a square tube of four side faces round the y axis (no caps): corners 0..3 at the bottom, 4..7 at the top
PTS = [(-1, 0, -1), (1, 0, -1), (1, 0, 1), (-1, 0, 1), (-1, 2, -1), (1, 2, -1), (1, 2, 1), (-1, 2, 1)]
EDGES = [(0, 1), (1, 2), (2, 3), (3, 0),        # 0..3 the bottom ring
         (4, 5), (5, 6), (6, 7), (7, 4),        # 4..7 the top ring
         (0, 4), (1, 5), (2, 6), (3, 7)]        # 8..11 the four uprights
FACES = [[0, 9, 4, 8], [1, 10, 5, 9], [2, 11, 6, 10], [3, 8, 7, 11]]     # front (-z), +x, back (+z), -x


class Chosen(unittest.TestCase):
    def test_a_rule_on_an_edges_two_ends_picks_the_cut(self):
        back_upright = S.by_rule(PTS, EDGES, lambda a, b: a[2] > 0 and b[2] > 0 and a[0] < 0 and b[0] < 0)
        self.assertEqual(back_upright, [11])
        self.assertEqual(S.by_rule(PTS, EDGES, lambda a, b: False), [])

    def test_edges_sharper_than_an_angle(self):
        n = {8: ((0, 0, -1), (-1, 0, 0)), 9: ((0, 0, -1), (0.5, 0, -0.866)), 3: ((0, 0, -1),) * 2}
        self.assertEqual(S.by_angle(n, 66), [8])                          # 90 degrees: cut; 30 and 0: not
        self.assertEqual(S.by_angle(n, 20), [8, 9])
        self.assertEqual(S.by_angle(n, None), [])


class Pieces(unittest.TestCase):
    def test_an_uncut_tube_is_one_piece_and_a_cut_keeps_it_one(self):
        self.assertEqual(S.islands(FACES, []), [0, 0, 0, 0])
        self.assertEqual(S.islands(FACES, [11]), [0, 0, 0, 0])            # cut down the back: one strip
        self.assertEqual(S.islands(FACES, [8, 9, 10, 11]), [0, 1, 2, 3])  # every upright: four faces

    def test_a_ball_nobody_cut_open_is_said(self):
        # a closed box: 6 faces, 12 edges, every edge used twice
        cube = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 9, 4, 8], [1, 10, 5, 9], [2, 11, 6, 10], [3, 8, 7, 11]]
        self.assertEqual(S.closed(cube, S.islands(cube, [])), [0])
        # the open tube has its two rims: it can be laid flat only once cut, but it is not CLOSED
        self.assertEqual(S.closed(FACES, S.islands(FACES, [])), [])
        # the box cut along three edges of its lid: the lid hangs on a hinge - open edges now
        self.assertEqual(S.closed(cube, S.islands(cube, [4, 5, 6]), [4, 5, 6]), [])


def tube(n, cut):
    """n side quads round a tube, laid as a strip (cut: the strip's two ends are two places) or as a ring"""
    out = []
    for i in range(n):
        j = (i + 1) % n
        if cut:
            u0, u1 = i / n, (i + 1) / n                   # (the last quad's far side is at u = 1, not back at 0)
            out.append([(i, (u0, 0.0)), (j, (u1, 0.0)), (n + j, (u1, 1.0)), (n + i, (u0, 1.0))])
        else:
            import math
            a0, a1 = 2 * math.pi * i / n, 2 * math.pi * j / n
            p = lambda a, r: (0.5 + r * math.cos(a), 0.5 + r * math.sin(a))  # noqa: E731
            out.append([(i, p(a0, 0.2)), (j, p(a1, 0.2)), (n + j, p(a1, 0.3)), (n + i, p(a1 - (a1 - a0), 0.3))])
    return out


class Laid(unittest.TestCase):
    def test_a_tube_laid_as_one_strip_is_one_disc_with_one_cut(self):
        labels, cuts, rings = S.laid(tube(8, True))
        self.assertEqual(len(set(labels)), 1)
        self.assertEqual(cuts, [(0, 8)])                  # the upright where the strip's two ends meet
        self.assertEqual(rings, [])

    def test_a_tube_laid_round_on_itself_is_no_disc_and_has_no_cut(self):
        # (the review: a band nobody cut open was laid as a ring and passed)
        labels, cuts, rings = S.laid(tube(8, False))
        self.assertEqual((len(set(labels)), cuts), (1, []))
        self.assertEqual(rings, [0])

    def test_two_faces_that_share_an_edge_in_two_places_are_two_pieces(self):
        a = [(0, (0, 0)), (1, (1, 0)), (2, (1, 1))]
        b = [(0, (5, 5)), (2, (6, 6)), (3, (5, 6))]       # the edge 0-2 again, somewhere else on the map
        labels, cuts, rings = S.laid([a, b])
        self.assertEqual((labels, cuts, rings), ([0, 1], [(0, 2)], []))


if __name__ == "__main__":
    unittest.main()
