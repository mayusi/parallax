"""UVs by part (3D crafts S2, kit/blender/rbx_uvparts.py): the pure pieces — the map's use (overlaps once), copies
found by shape (any face order, any start corner; never a mirror), boundary loops, circles and the lathe's axis, a
turned band's profile in the mesh's own order (a profile that folds back near itself), what is seen -> a weight."""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_uvparts as U  # noqa: E402  (no bpy at import: the Blender parts import it inside)


def _rz(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1.0]])


class TestCoverage(unittest.TestCase):
    def test_full_half_and_overlap_once(self):
        full = [[[0, 0], [1, 0], [1, 1]], [[0, 0], [1, 1], [0, 1]]]
        self.assertAlmostEqual(U.coverage(full, 64), 1.0, places=6)
        half = [[[0, 0], [1, 0], [1, 1]]]
        self.assertAlmostEqual(U.coverage(half, 64), 0.5, delta=0.02)
        twice = half + half   # (a copy laid on its original: one place, counted once)
        self.assertAlmostEqual(U.coverage(twice, 64), U.coverage(half, 64), places=9)

    def test_off_the_map_counts_nothing(self):
        off = [[[10, 0], [11, 0], [11, 1]]]   # (a copy moved off the map while its original bakes)
        self.assertEqual(U.coverage(off, 32), 0.0)


class TestCopies(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(1)
        self.a = rng.uniform(-1, 1, (6, 3))
        self.faces_a = [(0, 1, 2), (2, 3, 4, 5), (0, 2, 5)]

    def _two(self, b, faces_b):
        co = np.vstack([self.a, b])
        fv = self.faces_a + [tuple(v + 6 for v in f) for f in faces_b]
        part = [0] * len(self.faces_a) + [1] * len(faces_b)
        return U.copies(co, fv, part)

    def test_turned_copy_any_face_order_and_start(self):
        b = self.a @ _rz(72).T + [0.3, 0.1, 0.0]
        faces_b = [(4, 5, 2, 3), (2, 5, 0), (1, 2, 0)]   # (same faces: other order, other first corner)
        self.assertEqual(self._two(b, faces_b), {1: 0})

    def test_mirror_is_never_a_copy(self):
        b = self.a * [-1, 1, 1]
        self.assertEqual(self._two(b, list(self.faces_a)), {})

    def test_moved_vertex_is_not_a_copy(self):
        b = self.a @ _rz(72).T
        b[3] += [0.05, 0, 0]
        self.assertEqual(self._two(b, list(self.faces_a)), {})

    def _pair(self, faces_b):
        b = self.a @ _rz(72).T + [0.3, 0.1, 0.0]
        co = np.vstack([self.a, b])
        fv = self.faces_a + [tuple(v + 6 for v in f) for f in faces_b]
        part = [0] * len(self.faces_a) + [1] * len(faces_b)
        return co, fv, part

    def test_keep_copies_keeps_a_copy_cut_alike(self):
        # (the quad cut 2-4 in both: triangulate_like's job - the pair is still a copy on the triangles)
        tri_a = [(0, 1, 2), (2, 3, 4), (2, 4, 5), (0, 2, 5)]
        self.faces_a = tri_a
        co, fv, part = self._pair([(4, 5, 2), (2, 3, 4), (0, 1, 2), (0, 2, 5)])
        self.assertEqual(U.keep_copies(co, fv, part, {1: 0}), {1: 0})

    def test_keep_copies_drops_a_copy_cut_otherwise(self):
        # (the rim's Spoke2: its quad cut 3-5 where its original's was cut 2-4 - its corners would be laid from other
        # islands, a striped blotch: dropped, it unwraps on its own)
        self.faces_a = [(0, 1, 2), (2, 3, 4), (2, 4, 5), (0, 2, 5)]
        co, fv, part = self._pair([(0, 1, 2), (2, 3, 5), (3, 4, 5), (0, 2, 5)])
        self.assertEqual(U.copies(co, fv, part), {})
        self.assertEqual(U.keep_copies(co, fv, part, {1: 0}), {})

    def test_keep_copies_ignores_missing_parts(self):
        co, fv, part = self._pair(list(self.faces_a))
        self.assertEqual(U.keep_copies(co, fv, part, {1: 0, 7: 0}), {1: 0})

    def test_kabsch_recovers_a_turn(self):
        r0 = _rz(33)
        r, t, err = U.kabsch(self.a, self.a @ r0.T + [1, 2, 3])
        self.assertTrue(np.allclose(r, r0, atol=1e-9))
        self.assertLess(err, 1e-9)


class TestLoopsCircles(unittest.TestCase):
    def test_two_loops(self):
        edges = [(0, 1), (1, 2), (2, 3), (3, 0), (10, 11), (11, 12), (12, 10)]
        loops = U.loops_of(edges)
        self.assertEqual(sorted(len(lp) for lp in loops), [3, 4])

    def _ring(self, r, z, n=24, centre=(0, 0)):
        t = np.linspace(0, 2 * math.pi, n, endpoint=False)
        return np.stack([centre[0] + r * np.cos(t), centre[1] + r * np.sin(t), np.full(n, z)], 1)

    def test_circle_fit(self):
        c, n, r, off = U.circle3(self._ring(2.5, 1.0))
        self.assertAlmostEqual(r, 2.5, places=9)
        self.assertAlmostEqual(abs(n[2]), 1.0, places=9)
        self.assertLess(off, 1e-9)
        sq = np.array([[1, 1, 0], [-1, 1, 0], [-1, -1, 0], [1, -1, 0], [1, 0, 0], [0, 1, 0]], float)
        self.assertGreater(U.circle3(sq)[3], 0.1)   # (a square is no circle)

    def test_lathe_axis(self):
        ax = U.lathe_axis(self._ring(2.0, 0.0), self._ring(2.3, 0.4), 1e-6)
        self.assertIsNotNone(ax)
        self.assertAlmostEqual(abs(ax[1][2]), 1.0, places=9)
        self.assertIsNone(U.lathe_axis(self._ring(2.0, 0.0), self._ring(2.0, 0.4, centre=(0.5, 0)), 1e-6))


class TestLatheProfile(unittest.TestCase):
    def test_profile_that_folds_back_follows_the_edges(self):
        # the lip's case: front face (r 205 -> 230 at z 0), outer wall (r 233.5), back down to r 207 at z 16 — the
        # first and the last ring are 16 apart, the second 25: by distance the walk jumped from the first to the last
        # (rbx_uvparts' nearest-next fallback gives 0, 54.6, 50, ... here: the strips came out jumbled)
        prof = [(205, 0), (230, 0), (233.5, 3), (233.5, 8), (230, 12), (216, 16), (207, 16)]
        n = 16
        co, ring_of = [], []
        for k, (r, z) in enumerate(prof):
            for j in range(n):
                t = 2 * math.pi * j / n
                co.append((r * math.cos(t), r * math.sin(t), z))
                ring_of.append(k)
        co = np.array(co, float)
        edges = set()
        for k in range(len(prof) - 1):   # each ring joined to the next along the profile (the band's faces)
            for j in range(n):
                edges.add((k * n + j, (k + 1) * n + j))
                edges.add((k * n + j, k * n + (j + 1) % n))
        th, s, r = U.lathe_uv(co, (np.zeros(3), np.array([0, 0, 1.0])), 1e-6, edges=edges, start=0)
        want = np.concatenate([[0.0], np.cumsum([math.dist(prof[i], prof[i + 1]) for i in range(len(prof) - 1)])])
        got = [float(s[np.array(ring_of) == k].mean()) for k in range(len(prof))]
        self.assertTrue(np.allclose(got, want, atol=1e-6), (got, want.tolist()))

    def test_wide_band_split_at_its_best_ring(self):
        # a flange turned in one profile under 66 degrees: flat ring (120 -> 160), chamfer, wall (165), chamfer,
        # flat ring back to 120 - too wide for one strip (165 / 120); cut where both sides stay narrowest
        self.assertIn(U.best_split([120, 160, 165, 165, 160, 120]), (1, 2, 3, 4))
        self.assertEqual(U.best_split([160, 165, 165, 160, 120]), 3)   # (the wall's strip | the flat ring)
        self.assertIsNone(U.best_split([120, 160]))   # (no ring inside the profile to cut at)

    def test_polar(self):
        th, r = U.polar(np.array([[0, 3, 5.0]]), (np.zeros(3), np.array([0, 0, 1.0])))
        self.assertAlmostEqual(float(r[0]), 3.0, places=9)


class TestSeen(unittest.TestCase):
    def test_weight_floor_open_and_between(self):
        self.assertEqual(U.seen_weight(0.0), U.SEEN_FLOOR)
        self.assertEqual(U.seen_weight(1.0), 1.0)
        mid = U.seen_weight((U.SEEN_SHUT + U.SEEN_OPEN) / 2)
        self.assertAlmostEqual(mid, (U.SEEN_FLOOR + 1.0) / 2, places=9)

    def test_hemisphere(self):
        d = U.hemisphere(64)
        self.assertTrue(np.allclose(np.linalg.norm(d, axis=1), 1.0))
        self.assertTrue((d[:, 2] >= 0).all())


if __name__ == "__main__":
    unittest.main()
