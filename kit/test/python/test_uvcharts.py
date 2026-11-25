"""rbx_uvcharts — a dense organic surface's UV charts follow its FORM (the smoothed normal's side), not its relief:
a noisy ball is six charts with seams only where they meet, specks voted away (plain numpy)."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_uvcharts as C  # noqa: E402


def ball(n=48, noise=0.0, seed=1):
    """a UV-sphere of radius 1 (quads, triangle fans at the poles), its radius jittered by `noise` per vertex"""
    rng = np.random.default_rng(seed)
    verts = [(0.0, 0.0, 1.0)]
    for i in range(1, n):
        th = np.pi * i / n
        for j in range(2 * n):
            ph = 2 * np.pi * j / (2 * n)
            verts.append((np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)))
    verts.append((0.0, 0.0, -1.0))
    v = np.asarray(verts)
    v *= (1.0 + noise * rng.standard_normal(len(v)))[:, None]
    ring = lambda i, j: 1 + (i - 1) * 2 * n + (j % (2 * n))  # noqa: E731
    faces = [[0, ring(1, j), ring(1, j + 1)] for j in range(2 * n)]
    for i in range(1, n - 1):
        faces += [[ring(i, j), ring(i + 1, j), ring(i + 1, j + 1), ring(i, j + 1)] for j in range(2 * n)]
    last = len(v) - 1
    faces += [[ring(n - 1, j + 1), ring(n - 1, j), last] for j in range(2 * n)]
    return v, faces


class Charts(unittest.TestCase):
    def test_a_ball_is_six_sides(self):
        v, f = ball()
        lab = C.charts(v, f)
        self.assertEqual(sorted(set(lab.tolist())), [0, 1, 2, 3, 4, 5])
        _n, c = C.face_normals(v, f)
        side = np.abs(c).argmax(axis=1) * 2 + (c[np.arange(len(c)), np.abs(c).argmax(axis=1)] < 0)
        self.assertGreater((lab == side).mean(), 0.95)   # (each face on the side it faces)

    def test_relief_does_not_split_the_charts(self):
        v, f = ball(noise=0.06)   # (a rough ball: its faces' own normals turn every face)
        own = C.face_normals(v, f)[0]
        own_side = np.abs(own).argmax(axis=1)
        lab = C.charts(v, f)
        pairs = C.face_neighbours(f)
        raw_cuts = int((own_side[pairs[:, 0]] != own_side[pairs[:, 1]]).sum())
        cuts = int((lab[pairs[:, 0]] != lab[pairs[:, 1]]).sum())
        self.assertLess(cuts * 3, raw_cuts, (cuts, raw_cuts))   # (far fewer borders than its relief would cut)

    def test_seams_are_the_chart_borders(self):
        v, f = ball()
        lab = C.charts(v, f)
        seams = C.seam_edges(f, lab)
        pairs = C.face_neighbours(f)
        self.assertEqual(len(seams), int((lab[pairs[:, 0]] != lab[pairs[:, 1]]).sum()))
        self.assertTrue(all(a < b for a, b in seams))

    def _plate_and_cube(self):
        """a big plate facing +y (20 x 20, 10 x 10 quads) and a small closed cube (0.3) resting on its middle"""
        v, f = [], []
        for i in range(11):
            for j in range(11):
                v.append((-10 + 2 * i, 0.0, -10 + 2 * j))
        for i in range(10):
            for j in range(10):
                a = i * 11 + j
                f.append([a, a + 1, a + 12, a + 11])   # (+y: wound so the normal points up)
        o = len(v)
        for x in (-0.15, 0.15):
            for y in (0.01, 0.31):
                for z in (-0.15, 0.15):
                    v.append((x, y, z))
        c = lambda x, y, z: o + x * 4 + y * 2 + z   # noqa: E731
        f += [[c(0, 0, 0), c(0, 0, 1), c(0, 1, 1), c(0, 1, 0)], [c(1, 0, 0), c(1, 1, 0), c(1, 1, 1), c(1, 0, 1)],
              [c(0, 0, 0), c(1, 0, 0), c(1, 0, 1), c(0, 0, 1)], [c(0, 1, 0), c(0, 1, 1), c(1, 1, 1), c(1, 1, 0)],
              [c(0, 0, 0), c(0, 1, 0), c(1, 1, 0), c(1, 0, 0)], [c(0, 0, 1), c(1, 0, 1), c(1, 1, 1), c(0, 1, 1)]]
        return np.asarray(v, dtype=float), f

    def test_a_small_closed_piece_never_sits_in_one_chart(self):
        # (the stump's fungi: smoothed with the bark around them, every face took the bark's side — one chart, no seam,
        #  a conformal unwrap collapsed it to no UV area)
        v, f = self._plate_and_cube()
        cube = slice(100, 106)
        swamped = np.full(len(f), 2)   # (everything +y: the cube in the plate's chart)
        out = C.split_closed(v, f, swamped)
        self.assertEqual(len(set(out[cube].tolist())), 6)   # (the closed cube: its own six sides)
        self.assertTrue(np.all(out[:100] == 2))              # (the open plate keeps its chart)
        self.assertEqual(len(set(C.charts(v, f, parts=[0] * 100 + [1] * 6)[cube].tolist())), 6)

    def test_a_shelf_keeps_its_own_sides(self):
        # two thin plates back to back in one cell: their normals cancel — each keeps its own (+y / -y)
        v = np.array([[0, 0, 0], [1, 0, 0], [1, 0, 1], [0, 0, 1], [0, -0.001, 0], [1, -0.001, 0], [1, -0.001, 1],
                      [0, -0.001, 1]], dtype=float)
        f = [[0, 3, 2, 1], [4, 5, 6, 7]]   # (the first faces +y, the second -y)
        sn = C.smoothed_normals(v, f, cells=4)
        self.assertGreater(sn[0, 1], 0.9)
        self.assertLess(sn[1, 1], -0.9)


if __name__ == "__main__":
    unittest.main()
