"""EDGE FLOW, MOVED (kit/blender/rbx_flow.py; the 3D methods audit's PARTLY "a tool that moves vertices or slides a
loop to redistribute flow")."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_flow as F  # noqa: E402


def grid(xs, ys, z=None):
    """a sheet of vertices at xs x ys (rows of loops bunched where xs bunches), its edges, its border edges"""
    pts = np.array([(x, y, 0.0 if z is None else z(x, y)) for y in ys for x in xs])
    nx = len(xs)
    edges, border = [], []
    for j in range(len(ys)):
        for i in range(nx):
            v = j * nx + i
            if i + 1 < nx:
                edges.append((v, v + 1))
                border.append(j in (0, len(ys) - 1))
            if j + 1 < len(ys):
                edges.append((v, v + nx))
                border.append(i in (0, nx - 1))
    return pts, np.array(edges), np.array(border)


def flat(p, idx=None):
    q = np.array(p, float)
    q[:, 2] = 0.0
    return q


class Classify(unittest.TestCase):
    def test_a_sheets_inside_is_free_its_sides_slide_its_corners_stay(self):
        pts, e, b = grid([0, 1, 2], [0, 1, 2])
        kind, chain = F.classify(pts, e, b)
        self.assertEqual(kind.tolist(), [2, 1, 2, 1, 0, 1, 2, 1, 2])
        self.assertEqual(sorted(chain[1]), [0, 2])


class Relax(unittest.TestCase):
    def test_bunched_loops_spread_out_and_the_border_holds(self):
        xs = [0.0, 0.05, 0.1, 0.15, 0.2, 1.0, 2.0, 3.0, 4.0]       # five loops bunched at one end
        pts, e, b = grid(xs, [0.0, 1.0, 2.0, 3.0])
        kind, chain = F.classify(pts, e, b)
        before = F.spread(pts, e)
        out = F.relax(pts, e, kind, chain, flat, iterations=60, held_edges=e[b])
        after = F.spread(out, e)
        self.assertLess(after, before * 0.25, (before, after))
        corners = kind == 2
        self.assertTrue(np.allclose(out[corners], pts[corners]))   # (a corner never moves)
        self.assertTrue(np.allclose(out[:, 2], 0.0))              # (the sheet stays a sheet)
        # (a border vertex slides along ITS OWN border: a bottom-row one stays on the bottom row, never round the
        # corner onto a side)
        for v in np.flatnonzero(kind == 1):
            same = [np.isclose(out[v, ax], pts[v, ax]) for ax in (0, 1) if pts[v, ax] in (0.0, 4.0, 3.0)]
            self.assertTrue(any(same), (v, pts[v], out[v]))
        self.assertTrue((out[:, 0] >= -1e-9).all() and (out[:, 0] <= 4 + 1e-9).all())

    def test_on_a_curved_surface_every_vertex_is_laid_back_on_it(self):
        def dome(x, y):
            return np.sqrt(np.maximum(25.0 - (x - 2) ** 2 - (y - 1.5) ** 2, 0.0))

        def project(p, idx=None):
            c = np.array([2.0, 1.5, 0.0])
            d = np.asarray(p, float) - c
            return c + d / np.linalg.norm(d, axis=1, keepdims=True) * 5.0
        xs = [0.0, 0.05, 0.1, 0.15, 0.2, 1.0, 2.0, 3.0, 4.0]
        pts, e, b = grid(xs, [0.0, 1.0, 2.0, 3.0], dome)
        kind, chain = F.classify(pts, e, b)
        out = F.relax(pts, e, kind, chain, project, iterations=40, held_edges=e[b])
        free = kind == 0
        r = np.linalg.norm(out[free] - np.array([2.0, 1.5, 0.0]), axis=1)
        self.assertTrue(np.allclose(r, 5.0))
        # (its border runs curved over the dome: a curved sharp line is held whole - the inside evens out)
        self.assertTrue(np.allclose(out[kind == 2], pts[kind == 2]))
        self.assertLess(np.abs(out[kind == 1] - pts[kind == 1]).max(), 0.01)   # (only its straight stretches slide)
        inside = e[(kind[e[:, 0]] == 0) & (kind[e[:, 1]] == 0)]
        self.assertLess(F.spread(out, inside), F.spread(pts, inside) * 0.95)  # (held between its bunched borders)

    def test_a_chain_vertex_stays_on_its_own_edge_line(self):
        got = F.on_segments([[0.5, 0.3, 0.0], [3.0, 0.0, 0.0]], [[0, 0, 0], [1, 0, 0]], [[1, 0, 0], [2, 0, 0]])
        self.assertTrue(np.allclose(got, [[0.5, 0, 0], [2.0, 0, 0]]))

    def test_a_vertex_with_no_edge_never_moves(self):
        # (review 2026-11-17: a loose vertex had no neighbours' middle - it was pulled to the origin)
        pts, e, b = grid([0.0, 0.1, 1.0, 2.0], [0.0, 1.0, 2.0])
        pts = np.vstack([pts, [[5.0, 5.0, 5.0]]])
        kind, chain = F.classify(pts, e, b)
        out = F.relax(pts, e, kind, chain, flat, held_edges=e[b])
        self.assertTrue(np.allclose(out[-1], [5.0, 5.0, 5.0]))

    def test_the_surface_is_told_which_vertices_it_lays_back(self):
        pts, e, b = grid([0.0, 0.1, 1.0, 2.0], [0.0, 1.0, 2.0])
        kind, chain = F.classify(pts, e, b)
        seen = []
        F.relax(pts, e, kind, chain, lambda q, idx: (seen.append(list(idx)), flat(q))[1], iterations=1,
                held_edges=e[b])
        self.assertEqual(seen[0], np.flatnonzero(kind == 0).tolist())

    def test_an_even_sheet_does_not_move(self):
        pts, e, b = grid([0, 1, 2, 3], [0, 1, 2, 3])
        kind, chain = F.classify(pts, e, b)
        out = F.relax(pts, e, kind, chain, flat, held_edges=e[b])
        self.assertTrue(np.allclose(out, pts))
        self.assertAlmostEqual(F.spread(pts, e), 0.0)


if __name__ == "__main__":
    unittest.main()
