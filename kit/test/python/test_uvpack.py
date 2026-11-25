"""rbx_uvpack — UV islands packed by their real shape (the 3D studio route: tighter packing, 2026-11-12).

The guarantee is checked here with EXACT geometry that shares nothing with the packer's own grid: the distance
between two islands is the least distance between their edges (and no corner of one lies inside the other)."""

import math
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
import rbx_uvpack as P  # noqa: E402


def fan(poly):
    p = np.asarray(poly, float)
    return np.array([[p[0], p[i], p[i + 1]] for i in range(1, len(p) - 1)])


def rect(w, h):
    return fan([(0, 0), (w, 0), (w, h), (0, h)])


def ell(w, h, t):
    return np.concatenate([rect(w, t), rect(t, h)])


def ring(r0, r1, n=24):
    a = np.linspace(0, 2 * math.pi, n + 1)
    o = np.column_stack([np.cos(a), np.sin(a)])
    t = []
    for i in range(n):
        t.append([o[i] * r0, o[i] * r1, o[i + 1] * r1])
        t.append([o[i] * r0, o[i + 1] * r1, o[i + 1] * r0])
    return np.array(t)


def turned(t, a):
    c, s = math.cos(a), math.sin(a)
    return t @ np.array([[c, s], [-s, c]])


def layout(shapes, seed=7):
    rng = np.random.default_rng(seed)
    tri, isl = [], []
    for i, t in enumerate(shapes):
        tri.append(t + rng.uniform(0, 5, 2))
        isl += [i] * len(t)
    return np.concatenate(tri), np.array(isl)


def _seg_dist(a, b):
    """least distance between every segment of a (n,2,2) and every segment of b (m,2,2) -> a float"""
    p, r = a[:, None, 0], a[:, None, 1] - a[:, None, 0]
    q, s = b[None, :, 0], b[None, :, 1] - b[None, :, 0]

    def pt_seg(x, o, d):
        t = np.clip(((x - o) * d).sum(-1) / np.maximum((d * d).sum(-1), 1e-30), 0, 1)
        return np.linalg.norm(x - (o + d * t[..., None]), axis=-1)

    best = np.minimum.reduce([pt_seg(p, q, s), pt_seg(p + r, q, s), pt_seg(q, p, r), pt_seg(q + s, p, r)])
    rxs = r[..., 0] * s[..., 1] - r[..., 1] * s[..., 0]
    qp = q - p
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (qp[..., 0] * s[..., 1] - qp[..., 1] * s[..., 0]) / rxs
        u = (qp[..., 0] * r[..., 1] - qp[..., 1] * r[..., 0]) / rxs
    cross = (np.abs(rxs) > 1e-15) & (t > 0) & (t < 1) & (u > 0) & (u < 1)
    return 0.0 if cross.any() else float(best.min())


def _inside(pt, tris):
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]

    def side(p, q):
        return (q[:, 0] - p[:, 0]) * (pt[1] - p[:, 1]) - (q[:, 1] - p[:, 1]) * (pt[0] - p[:, 0])

    d0, d1, d2 = side(a, b), side(b, c), side(c, a)
    return bool((((d0 > 0) & (d1 > 0) & (d2 > 0)) | ((d0 < 0) & (d1 < 0) & (d2 < 0))).any())


def closest(tri, isl):
    """the least distance between two different islands (0 when they overlap) -> float (inf for one island)"""
    k = int(isl.max()) + 1
    edges = [np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]) for t in (tri[isl == i] for i in range(k))]
    worst = math.inf
    for i in range(k):
        for j in range(i + 1, k):
            if _inside(tri[isl == j][0, 0], tri[isl == i]) or _inside(tri[isl == i][0, 0], tri[isl == j]):
                return 0.0
            worst = min(worst, _seg_dist(edges[i], edges[j]))
    return worst


class Guarantee(unittest.TestCase):
    def packed(self, shapes, tex, pad=4.0, **kw):
        tri, isl = layout(shapes)
        res = P.pack(tri, isl, tex, pad, **kw)
        self.assertIsNotNone(res)
        out = res["tri"]
        self.assertGreaterEqual(out.min(), 0.0)                       # on the map
        self.assertLessEqual(out.max(), 1.0)
        self.assertGreaterEqual(closest(out * tex, isl), pad - 1e-6)   # never closer than the pad
        # turned and scaled by ONE factor, never mirrored, never stretched
        def edges(t):
            return np.linalg.norm(t - np.roll(t, -1, axis=1), axis=2)

        def signed(t):
            e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
            return e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]

        ratio = edges(out)[edges(tri) > 1e-9] / edges(tri)[edges(tri) > 1e-9]
        self.assertLess(ratio.max() / ratio.min(), 1.0001)
        keep = np.abs(signed(tri)) > 1e-12
        self.assertTrue((np.sign(signed(out)[keep]) == np.sign(signed(tri)[keep])).all())
        self.assertAlmostEqual(res["cover"], P.cover(out), places=6)
        return res, out, isl

    def test_rectangles(self):
        rng = np.random.default_rng(1)
        res, _o, _i = self.packed([rect(rng.uniform(0.2, 3), rng.uniform(0.2, 3)) for _ in range(30)], 256)
        self.assertGreater(res["cover"], 0.6)

    def test_turned_strips_are_laid_flat(self):
        rng = np.random.default_rng(2)
        shapes = [turned(rect(rng.uniform(0.5, 4), rng.uniform(0.1, 0.6)), rng.uniform(0, 3)) for _ in range(40)]
        res, out, isl = self.packed(shapes, 256)
        self.assertGreater(res["cover"], 0.5)
        for i in range(40):                     # every strip's box is its own area again (it lies along an axis)
            t = out[isl == i].reshape(-1, 2)
            box = np.prod(t.max(0) - t.min(0))
            self.assertLess(box / P.cover(out[isl == i]), 1.02)

    def test_small_islands_go_into_the_holes_of_big_ones(self):
        rng = np.random.default_rng(3)
        shapes = [ring(1.4, 2.0)] + [rect(rng.uniform(0.15, 0.4), rng.uniform(0.15, 0.4)) for _ in range(60)]
        res, out, isl = self.packed(shapes, 512)
        r = out[isl == 0].reshape(-1, 2)
        centre, inner = (r.max(0) + r.min(0)) / 2, (r.max(0) - r.min(0)).min() / 2 * (1.4 / 2.0)
        in_hole = sum(np.linalg.norm(out[isl == i].reshape(-1, 2).mean(0) - centre) < inner * 0.9 for i in range(1, 61))
        self.assertGreaterEqual(in_hole, 5)     # the ring's hole is used (a packer by boxes leaves it empty)

    def test_l_shapes_and_tiny_triangles(self):
        rng = np.random.default_rng(4)
        shapes = [turned(ell(rng.uniform(2, 4), rng.uniform(2, 4), 0.5), rng.uniform(0, 3)) for _ in range(6)] + \
                 [fan(rng.uniform(0, 0.08, (3, 2))) for _ in range(80)]
        self.packed(shapes, 256)

    def test_a_strip_longer_than_the_map_lies_on_the_diagonal(self):
        # four strips 10 x 0.25 and thirty small boxes (about 21 square units in all): lying straight, a strip caps
        # the scale at one map side for its 10 units - a cover of 21 / (10 x 10), a fifth of the map. On the
        # diagonal the strips fit a larger scale.
        rng = np.random.default_rng(11)
        shapes = [rect(10.0, 0.25) for _ in range(4)] +                  [rect(rng.uniform(0.4, 0.9), rng.uniform(0.4, 0.9)) for _ in range(30)]
        res, out, isl = self.packed(shapes, 512)
        straight_cap = P.cover(layout(shapes)[0]) / (10.0 * 10.0)
        self.assertGreater(res["cover"], straight_cap * 1.15)
        strip = out[isl == 0].reshape(-1, 2)
        box = strip.max(0) - strip.min(0)
        self.assertLess(max(box) / min(box), 1.3)        # its box is near square: it lies on a diagonal

    def test_packed_by_cells_keeps_the_guarantee(self):
        rng = np.random.default_rng(12)
        shapes = [turned(ell(rng.uniform(2, 4), rng.uniform(2, 4), 0.6), rng.uniform(0, 3)) for _ in range(5)] +                  [rect(rng.uniform(0.3, 1.5), rng.uniform(0.3, 1.5)) for _ in range(9)]
        tri, isl = layout(shapes)
        cells = P.pack(tri, isl, 256, 4.0, order_by="cells")
        self.assertGreaterEqual(closest(cells["tri"] * 256, isl), 4.0 - 1e-6)
        best = P.pack_best(tri, isl, 256, 4.0)
        self.assertGreaterEqual(closest(best["tri"] * 256, isl), 4.0 - 1e-6)
        self.assertIsNone(P.pack_best(tri, isl, 256, 4.0, at_least=0.97))

    def test_a_search_that_starts_too_full_comes_down_to_what_fits(self):
        # 900 tiny islands on a 192 map fit at a few percent of it - far under the 62% the search starts from. It
        # used to give up after eight tries (None above a fifth of the map): the builder then kept a worse layout.
        rng = np.random.default_rng(13)
        shapes = [rect(rng.uniform(0.05, 0.2), rng.uniform(0.05, 0.2)) for _ in range(900)]
        tri, isl = layout(shapes)
        res = P.pack(tri, isl, 192, 4.0)
        self.assertIsNotNone(res)
        self.assertLess(res["cover"], 0.19)
        self.assertGreaterEqual(res["tri"].min(), 0.0)
        self.assertLessEqual(res["tri"].max(), 1.0)
        # ... and on a 128 map they cannot fit at all (900 islands, each a pad round it, on 16,384 texels): None
        self.assertIsNone(P.pack(tri, isl, 128, 4.0))


    def test_one_island_and_a_wider_pad(self):
        res, out, _i = self.packed([rect(2, 1)], 128, pad=8.0)
        self.assertGreater(res["cover"], 0.4)                          # a 2:1 box in a square: under a half
        self.assertGreaterEqual(out.min() * 128, 4.0 - 1e-6)           # half a pad from the map's edge

    def test_a_large_map_packs_on_a_coarser_grid(self):
        rng = np.random.default_rng(5)
        res, _o, _i = self.packed([rect(rng.uniform(0.5, 3), rng.uniform(0.5, 3)) for _ in range(12)], 2048)
        self.assertEqual(res["grid"], 1024)

    def test_a_time_budget_still_returns_a_layout(self):
        rng = np.random.default_rng(6)
        res, _o, _i = self.packed([rect(rng.uniform(0.2, 3), rng.uniform(0.2, 3)) for _ in range(30)], 256,
                                  budget_s=0.01)
        self.assertGreater(res["cover"], 0.3)

    def test_at_least_gives_up_at_once_or_reaches_it(self):
        rng = np.random.default_rng(9)
        shapes = [rect(rng.uniform(0.2, 3), rng.uniform(0.2, 3)) for _ in range(30)]
        tri, isl = layout(shapes)
        self.assertIsNone(P.pack(tri, isl, 256, 4.0, at_least=0.97))    # no layout of these covers 97%: one try, None
        res = P.pack(tri, isl, 256, 4.0, at_least=0.5)
        self.assertGreaterEqual(res["cover"], 0.5)

    def test_nothing_to_pack(self):
        self.assertIsNone(P.pack(np.zeros((0, 3, 2)), np.zeros(0, int), 256))
        self.assertIsNone(P.pack(np.zeros((2, 3, 2)), np.array([0, 1]), 256))    # no area

    def test_what_cannot_be_packed_is_none_never_an_exception(self):
        nan = np.array([[[0, 0], [1, 0], [np.nan, 1]]])
        self.assertIsNone(P.pack(nan, np.array([0]), 256))                       # a corner that is not a number
        noise = np.array([[[0, 0], [1e-9, 0], [2e-9, 1e-17]]])
        self.assertIsNone(P.pack(noise, np.array([0]), 256))                     # an area of rounding noise
        sliver = np.concatenate([rect(1000.0, 1e-4), rect(1.0, 1.0) + 5])        # a hair a thousand squares long
        res = P.pack(sliver, np.array([0, 0, 1, 1]), 64)
        if res is not None:                                                      # packed or not: never off the map
            self.assertGreaterEqual(res["tri"].min(), 0.0)
            self.assertLessEqual(res["tri"].max(), 1.0)

    def test_island_ids_need_not_be_0_to_k(self):
        tri = np.concatenate([rect(1, 1), rect(2, 1) + 5])
        res = P.pack(tri, np.array([5, 5, 9, 9]), 128)
        self.assertGreaterEqual(closest(res["tri"] * 128, np.array([0, 0, 1, 1])), 4.0 - 1e-6)


class Best(unittest.TestCase):
    """pack_best: the first ordering, then - for a small set - the second, searching only above the first"""

    def run_best(self, k, first, second):
        calls = []

        def fake(tri, isl, tex, pad_px=4.0, **kw):
            calls.append(kw)
            cover = first if len(calls) == 1 else second
            return None if cover is None else {"cover": cover, "tri": tri, "secs": 0.1}

        real, P.pack = P.pack, fake
        try:
            got = P.pack_best(np.zeros((k, 3, 2)), np.arange(k), 256, 4.0, at_least=0.5)
        finally:
            P.pack = real
        return got, calls

    def test_a_small_set_is_packed_twice_the_second_only_above_the_first(self):
        got, calls = self.run_best(12, 0.60, 0.66)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].get("order_by", "box"), "box")
        self.assertEqual(calls[1]["order_by"], "cells")
        self.assertAlmostEqual(calls[1]["at_least"], 0.60 * 1.005)
        self.assertEqual(got["cover"], 0.66)                    # the fuller one

    def test_the_first_stands_when_the_second_finds_nothing_fuller(self):
        got, _calls = self.run_best(12, 0.60, None)
        self.assertEqual(got["cover"], 0.60)

    def test_the_second_alone_when_the_first_found_nothing(self):
        got, calls = self.run_best(12, None, 0.55)
        self.assertEqual(calls[1]["at_least"], 0.5)             # still held to what the caller asked
        self.assertEqual(got["cover"], 0.55)

    def test_a_large_set_is_packed_once(self):
        got, calls = self.run_best(P.SMALL_SET + 1, 0.60, 0.99)
        self.assertEqual(len(calls), 1)
        self.assertEqual(got["cover"], 0.60)


class Pieces(unittest.TestCase):
    def test_islands_by_shared_corner_at_the_same_uv(self):
        vert = np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7], [8, 9, 10], [9, 10, 11], [10, 11, 12]])
        uv = np.random.default_rng(1).uniform(0, 1, (13, 2))[vert]
        self.assertEqual(P.islands(vert, uv).tolist(), [0, 0, 1, 1, 2, 2, 2])

    def test_a_long_strip_is_one_island_and_a_seam_cuts_it(self):
        n = 3000
        vert = np.array([[i, i + 1, i + 2] for i in range(n)])
        pts = np.column_stack([np.arange(n + 2) * 0.001, (np.arange(n + 2) % 2) * 0.01])
        self.assertEqual(int(P.islands(vert, pts[vert]).max()), 0)
        cut = pts[vert].copy()
        cut[n // 2:] += 5.0                     # the same mesh vertices at another uv: a seam
        self.assertEqual(int(P.islands(vert, cut).max()), 1)

    def test_islands_whatever_order_the_vertex_ids_are_in(self):
        # a long strip whose vertex ids are shuffled: joining corner to corner moved a label one triangle a round
        # (200,000 triangles: 520 s, measured by the review); the roots are joined now
        rng = np.random.default_rng(0)
        n = 30000
        vert = np.array([np.arange(n), np.arange(n) + 1, np.arange(n) + 2]).T
        pts = np.column_stack([np.arange(n + 2) * 0.001, (np.arange(n + 2) % 2) * 0.01])
        perm = rng.permutation(n + 2)
        self.assertEqual(int(P.islands(perm[vert], pts[vert]).max()), 0)
        two = pts[vert].copy()
        two[n // 3:] += 7.0
        self.assertEqual(int(P.islands(perm[vert], two).max()), 1)

    def test_a_many_pointed_island_is_laid_flat_too(self):
        rng = np.random.default_rng(3)
        pts = turned(rng.uniform(0, 1, (5000, 2)) * (6.0, 1.0), math.radians(40))   # a 6 x 1 cloud, turned
        q = P._rot(pts, P.min_rect_angle(pts))
        d = q.max(0) - q.min(0)
        self.assertLess(d[0] * d[1], 6.0 * 1.08)                               # near its own box again
        self.assertGreater(d[0], d[1])

    def test_the_raster_marks_every_cell_a_triangle_touches(self):
        rng = np.random.default_rng(8)
        for _ in range(20):
            t = rng.uniform(0, 30, (1, 3, 2))
            masks, lo = P._raster(t, np.array([0, 1]))
            w = rng.dirichlet((1, 1, 1), 4000)                         # points all over the triangle
            pts = (w @ t[0]) - lo[0]
            cells = np.floor(pts).astype(int)
            self.assertTrue(masks[0][cells[:, 1], cells[:, 0]].all())

    def test_an_island_lies_over_the_texel_centres_of_its_box(self):
        # (sizes in texels -> where it starts; the centres it covers = the j + 0.5 inside [start, start + size])
        def centres(size, cell=1.0):
            start = float(P._centred(np.array([[size / cell, 1.0]]), cell)[0, 0]) * cell
            j = np.arange(0, 64) + 0.5
            return int(((j > start) & (j < start + size)).sum()), start

        self.assertEqual(centres(0.46), (1, 0.27))               # a strip thinner than a texel: its one row
        self.assertEqual(centres(0.05)[0], 1)
        self.assertEqual(centres(1.3)[0], 2)                     # (at the edge: 1)
        self.assertEqual(centres(2.9)[0], 3)
        self.assertEqual(centres(3.0), (3, 0.0))
        self.assertEqual(centres(3.02), (3, 0.0))                # just over three: at the edge, three for sure
        self.assertEqual(centres(3.2)[0], 4)
        for cell in (2.0, 4.0):                                  # a coarser grid: texel centres all the same
            self.assertEqual(centres(0.46, cell)[0], 1)
            self.assertEqual(centres(5.3, cell)[0], 6)

    def test_centred_islands_take_the_same_cells(self):
        rng = np.random.default_rng(12)
        for cell in (1.0, 2.0, 4.0):
            e = rng.uniform(0.01, 40, (4000, 2))
            off = P._centred(e, cell)
            self.assertTrue((off >= 0).all())
            self.assertTrue((np.floor(off + e) <= np.floor(e)).all())    # never one cell more than from the corner
        self.assertFalse(P._centred(rng.uniform(0.01, 40, (500, 2)), 1.5).any())   # no whole texels a cell: none

    def test_the_raster_of_a_centred_island_is_as_large_as_its_size_says(self):
        # (through _raster's own coordinates, far from 0 and a hair round whole texels: where a start of its own
        # could push an island's far edge into one more cell)
        rng = np.random.default_rng(13)
        for cell in (1.0, 2.0, 4.0, 1.5):
            for _ in range(300):
                size = rng.uniform(0.05, 12, 2)
                if rng.random() < 0.4:                              # a whole number of texels, give or take
                    size = (np.round(size * cell) + rng.choice([0.0, 1e-12, -1e-12, 3e-7])) / cell
                    size = np.maximum(size, 0.05)
                at = rng.uniform(-3000, 3000, 2)
                t = (rect(size[0], size[1]) + at)
                want = np.floor(t.reshape(-1, 2).max(0) - t.reshape(-1, 2).min(0)).astype(int) + 1
                masks, lo = P._raster(t, np.array([0, 2]), cell)
                self.assertEqual(masks[0].shape, (want[1], want[0]), (cell, size))
                p = t.reshape(-1, 2) - lo[0]                        # the island in its own cells: inside them
                self.assertTrue((p > -1e-9).all() and (p[:, 0] < want[0] + 1e-6).all()
                                and (p[:, 1] < want[1] + 1e-6).all(), (cell, size, p.min(0), p.max(0)))

    def thin_strips(self):
        """long walls among larger pieces, packed on a 64 px map -> [(thin size in texels, its low and high edge)]:
        the search ends near 2 texels a unit, so 0.2 units is some 0.4 texels - under half, the case that matters"""
        t = [rect(30, 9), rect(30, 6), rect(18, 4), rect(19, 0.2), rect(12, 0.19), rect(9, 0.22)]
        tri = np.concatenate(t)
        isl = np.repeat(np.arange(len(t)), 2)
        res = P.pack(tri, isl, 64)
        self.assertIsNotNone(res)
        out = res["tri"] * 64
        rows = []
        for i in (3, 4, 5):
            p = out[isl == i].reshape(-1, 2)
            d = p.max(0) - p.min(0)
            ax = int(np.argmin(d))                                # its thin axis, however it was turned
            rows.append((float(d[ax]), float(p[:, ax].min()), float(p[:, ax].max())))
        return rows

    def test_a_thin_strip_is_packed_over_a_row_of_texel_centres(self):
        for d, lo_, hi_ in self.thin_strips():
            self.assertLess(d, 0.5)                               # (under half a texel: at an edge it has no centre)
            c = math.floor(lo_) + 0.5
            self.assertTrue(lo_ + 0.1 < c < hi_ - 0.1, (d, lo_, hi_))

    def test_that_test_fails_without_the_centring(self):
        real, P._centred = P._centred, lambda ext, cell=1.0: np.zeros_like(np.asarray(ext, np.float64))
        try:
            missed = [not (lo_ < math.floor(lo_) + 0.5 < hi_) for _d, lo_, hi_ in self.thin_strips()]
        finally:
            P._centred = real
        self.assertTrue(all(missed), missed)                      # from a texel's edge none of them has a centre

    def test_smallest_rectangle(self):
        t = turned(rect(4, 1), math.radians(30))
        q = P._rot(t.reshape(-1, 2), P.min_rect_angle(t.reshape(-1, 2)))
        d = q.max(0) - q.min(0)
        self.assertAlmostEqual(d[0] * d[1], 4.0, delta=0.05)           # flat again (to the half degree it searches)
        self.assertGreater(d[0], d[1])                                 # its long side along U

    def test_cover_is_the_triangles_area(self):
        self.assertAlmostEqual(P.cover(rect(0.5, 0.25)), 0.125)


if __name__ == "__main__":
    unittest.main()
