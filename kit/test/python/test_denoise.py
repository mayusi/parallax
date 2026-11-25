"""kit/blender/rbx_denoise.py: a noisy hard-surface mesh made clean without melting it (a subdivided cube with noise:
its faces flat again, its 90-degree edges still edges), and the crispness measure that tells a modelled surface from a
melted or a noisy one."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "blender")))
import rbx_denoise as D  # noqa: E402


def cube(n=12):
    """a unit cube, each side an n x n grid of quads split into triangles, welded -> (V, F)"""
    pts, tris = [], []
    g = np.linspace(-0.5, 0.5, n + 1)
    for axis in range(3):
        for sign in (-1.0, 1.0):
            a, b = [k for k in range(3) if k != axis]
            base = len(pts)
            for i in range(n + 1):
                for j in range(n + 1):
                    p = [0.0, 0.0, 0.0]
                    p[axis], p[a], p[b] = 0.5 * sign, g[i], g[j]
                    pts.append(p)
            for i in range(n):
                for j in range(n):
                    q = [base + i * (n + 1) + j, base + (i + 1) * (n + 1) + j, base + (i + 1) * (n + 1) + j + 1,
                         base + i * (n + 1) + j + 1]
                    tri = [(q[0], q[1], q[2]), (q[0], q[2], q[3])]
                    tris += [t[::-1] for t in tri] if sign < 0 else tri
    P = np.asarray(pts)
    _, inv = np.unique(np.round(P * 1e6).astype(np.int64), axis=0, return_inverse=True)
    inv = inv.ravel()
    V = np.zeros((inv.max() + 1, 3))
    V[inv] = P
    return V, inv[np.asarray(tris)]


class Denoise(unittest.TestCase):
    def test_a_clean_cube_reads_flat_with_edges(self):
        V, F = cube()
        c = D.crispness(V, F)
        self.assertGreater(c["flat_share"], 0.9)
        self.assertGreater(c["sharp_share"], 0.03)   # (its 12 edges: 12 n of ~18 n^2 face pairs, 0.056 at n = 12)

    def test_noise_goes_and_the_edges_stay(self):
        V, F = cube()
        rng = np.random.default_rng(7)
        noisy = V + rng.normal(0, 0.006, V.shape)
        before = D.crispness(noisy, F)
        out = D.denoise(noisy, F)
        after = D.crispness(out, F)
        self.assertLess(before["flat_share"], 0.2)
        self.assertGreater(after["flat_share"], 2 * before["flat_share"])
        self.assertGreater(after["sharp_share"], 0.03)   # the cube's edges are still edges, not rounded
        # the faces sit back on their planes: the distance of each vertex to its nearest side
        off = np.abs(np.abs(out).max(axis=1) - 0.5)
        self.assertLess(float(np.median(off)), float(np.median(np.abs(np.abs(noisy).max(axis=1) - 0.5))))

    def test_a_wavy_flat_side_comes_back_flat(self):
        V, F = cube(24)
        wavy = V.copy()
        side = np.isclose(V[:, 0], 0.5)
        wavy[side, 0] += 0.0025 * np.sin(V[side, 1] * 9) * np.cos(V[side, 2] * 7)   # (a slow ripple: 0.25 % of it)
        out, flat = D.planarize(wavy, F)
        self.assertTrue(any(abs(r["normal"][0]) > 0.99 for r in flat))
        # flat inside; eased over its last 4 vertex rings (1/24 apart), so no step forms where it meets its neighbours
        mid = side & (np.abs(V[:, 1]) < 0.3) & (np.abs(V[:, 2]) < 0.3)
        self.assertLess(float(np.ptp(out[mid, 0])), 0.1 * float(np.ptp(wavy[mid, 0])))
        rim = side & (np.maximum(np.abs(V[:, 1]), np.abs(V[:, 2])) > 0.49)
        self.assertLess(float(np.abs(out[rim] - wavy[rim]).max()), 1e-12)   # (the border itself does not move)

    def test_a_curve_is_left_alone(self):
        # a cylinder's side (no caps): its faces turn 5.6 degrees apart, no direction holds 5 % of its area
        n, rings = 64, 12
        th = np.linspace(0, 2 * np.pi, n, endpoint=False)
        V = np.array([(np.cos(t), np.sin(t), z) for z in np.linspace(-1, 1, rings) for t in th])
        F = []
        for k in range(rings - 1):
            for i in range(n):
                a, b, c, d = k * n + i, k * n + (i + 1) % n, (k + 1) * n + (i + 1) % n, (k + 1) * n + i
                F += [(a, b, c), (a, c, d)]
        out, _flat = D.planarize(V, np.array(F), min_share=0.05)
        self.assertLess(float(np.abs(out - V).max()), 1e-9)

    def test_ring_pairs_are_the_faces_sharing_a_vertex(self):
        F = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6]])
        I, J = D.ring_pairs(F, 7)
        self.assertEqual(sorted(zip(I.tolist(), J.tolist())), [(0, 1), (1, 0)])


if __name__ == "__main__":
    unittest.main()
