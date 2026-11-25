"""rbx_sculpt — sculpting in code: a field of signed distances (plain numpy; the meshing is Blender's OpenVDB, tested in
test_sculpt_mesh.py). Each test pins what a sculpt relies on: true distances, the smooth blend's fillet, strokes that
taper, relief at the asked size, symmetry, and a narrow band that never misses the surface."""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_sculpt as S  # noqa: E402

RNG = np.random.default_rng(7)


def _pts(n=400, r=40.0):
    return RNG.uniform(-r, r, size=(n, 3))


class Shapes(unittest.TestCase):
    def test_ball_and_box_are_true_distances(self):
        p = _pts()
        self.assertTrue(np.allclose(S.Ball((1, 2, 3), 10).d(p), np.linalg.norm(p - (1, 2, 3), axis=1) - 10))
        box = S.Box((0, 0, 0), (20, 10, 6))
        self.assertAlmostEqual(float(box.d(np.array([[15.0, 0, 0]]))[0]), 5.0)   # (5 mm off the +x face)
        self.assertAlmostEqual(float(box.d(np.array([[0.0, 0, 0]]))[0]), -3.0)   # (3 mm in from the nearest face)
        self.assertAlmostEqual(float(box.d(np.array([[13.0, 9.0, 0]]))[0]), 5.0)  # (3-4-5 off an edge)

    def test_a_rounded_box_rounds_its_edges(self):
        sharp, round_ = S.Box((0, 0, 0), (20, 20, 20)), S.Box((0, 0, 0), (20, 20, 20), round=4)
        corner = np.array([[10.0, 10.0, 10.0]])
        self.assertAlmostEqual(float(sharp.d(corner)[0]), 0.0)
        self.assertGreater(float(round_.d(corner)[0]), 2.0)   # (the corner shaved off: outside the rounded box)
        face = np.array([[10.0, 0, 0]])
        self.assertAlmostEqual(float(round_.d(face)[0]), 0.0)   # (the flats where they were)

    def test_capsule_tapers_from_end_to_end(self):
        c = S.Capsule((0, 0, 0), (0, 50, 0), 10, 4)
        self.assertAlmostEqual(float(c.d(np.array([[0.0, -10.0, 0]]))[0]), 0.0, places=6)   # (round a end, r 10)
        self.assertAlmostEqual(float(c.d(np.array([[0.0, 54.0, 0]]))[0]), 0.0, places=6)    # (round b end, r 4)
        self.assertLess(float(c.d(np.array([[0.0, 25.0, 0]]))[0]), -5.0)                    # (inside its middle)
        same = S.Capsule((0, 0, 0), (0, 0, 30), 5)   # (equal radii: a plain capsule)
        q = np.array([[8.0, 0.0, 15.0], [0.0, 0.0, 40.0]])
        self.assertTrue(np.allclose(same.d(q), [3.0, 5.0]))
        swallowed = S.Capsule((0, 0, 0), (0, 1, 0), 10, 2)   # (one ball inside the other: just the big one)
        self.assertAlmostEqual(float(swallowed.d(np.array([[20.0, 0, 0]]))[0]), 10.0)

    def test_ellipsoid_and_torus_surfaces(self):
        e = S.Ellipsoid((0, 0, 0), (30, 10, 20))
        on = np.array([[30.0, 0, 0], [0, 10.0, 0], [0, 0, 20.0]])
        self.assertTrue(np.allclose(e.d(on), 0.0, atol=1e-9))
        self.assertTrue(np.all(e.d(np.array([[0.0, 0, 0]])) < 0))
        t = S.Torus((0, 0, 0), 20, 5)
        self.assertAlmostEqual(float(t.d(np.array([[25.0, 0, 0]]))[0]), 0.0)
        self.assertAlmostEqual(float(t.d(np.array([[0.0, 0, 0]]))[0]), 15.0)   # (the hole's centre: 15 mm from the tube)
        turned = S.Torus((0, 0, 0), 20, 5, rot=(90, 0, 0))   # (its axis turned from y to z)
        self.assertAlmostEqual(float(turned.d(np.array([[0.0, 25.0, 0]]))[0]), 0.0, places=6)


class Blends(unittest.TestCase):
    def test_smin_is_a_fillet_under_the_minimum(self):
        a, b = np.array([1.0, -2.0, 3.0, 0.0]), np.array([1.0, 5.0, -4.0, 0.0])
        self.assertTrue(np.array_equal(S.smin(a, b, 0.0), np.minimum(a, b)))
        k = 2.0
        s = S.smin(a, b, k)
        self.assertTrue(np.all(s <= np.minimum(a, b) + 1e-12))
        self.assertAlmostEqual(float(s[0]), 1.0 - k / 4.0)   # (where the two meet: the deepest, k / 4)
        self.assertAlmostEqual(float(s[1]), -2.0)            # (far apart: the plain minimum)

    def test_two_balls_blended_grow_a_neck(self):
        hard = S.Canvas(voxel=1.0).ball((-10, 0, 0), 8).ball((10, 0, 0), 8)
        soft = S.Canvas(voxel=1.0).ball((-10, 0, 0), 8).ball((10, 0, 0), 8, blend=10)   # (2 - 10 / 4 < 0)
        mid = np.array([[0.0, 0, 0]])
        self.assertGreater(float(hard.d(mid)[0]), 0)    # (two balls 4 mm apart: a gap)
        self.assertLess(float(soft.d(mid)[0]), 0)       # (blended: clay fills the gap — one piece)

    def test_carve_and_keep(self):
        s = S.Canvas(voxel=1.0).box((0, 0, 0), (40, 40, 40)).ball((0, 0, 20), 10, carve=True)
        self.assertGreater(float(s.d(np.array([[0.0, 0, 18]]))[0]), 0)   # (inside the carved ball: empty)
        self.assertLess(float(s.d(np.array([[15.0, 0, 0]]))[0]), 0)
        k = S.Canvas(voxel=1.0).box((0, 0, 0), (40, 40, 40))
        k.keep(S.Ball((0, 0, 0), 22))
        self.assertGreater(float(k.d(np.array([[19.0, 19.0, 19.0]]))[0]), 0)   # (the corner trimmed away)
        with self.assertRaises(ValueError):
            S.Canvas().ball((0, 0, 0), 3, carve=True)   # (nothing to carve yet)


class Strokes(unittest.TestCase):
    def test_a_stroke_passes_its_points_at_their_radii(self):
        s = S.Canvas(voxel=0.5).stroke([(0, 0, 0), (20, 0, 0), (40, 10, 0)], [6, 4, 2])
        for p, r in (((0, 0, 0), 6), ((20, 0, 0), 4), ((40, 10, 0), 2)):
            self.assertAlmostEqual(float(s.d(np.array([p], dtype=float))[0]), -r, places=6)
        with self.assertRaises(ValueError):
            S.stroke_node([(0, 0, 0), (1, 0, 0)], [1, 2, 3])

    def test_a_crease_presses_a_line_in(self):
        s = S.Canvas(voxel=0.25).box((0, 0, 0), (40, 40, 40))
        on_top = np.array([[0.0, 20.0, 0.0]])
        self.assertAlmostEqual(float(s.d(on_top)[0]), 0.0)
        s.crease([(-15, 20, 0), (15, 20, 0)], 2.0)
        self.assertGreater(float(s.d(on_top)[0]), 0.5)   # (the line's middle is now air: the groove)

    def test_pruning_each_block_changes_no_value_in_the_band(self):
        # many small operations spread over a big body + relief: each block keeps only the few that reach it, and
        # the sampled field is IDENTICAL to the whole tree's (smin / smax are exact past the blend; the band clips)
        s = S.Canvas(voxel=0.5, mirror="x").ellipsoid((0, 0, 0), (40, 25, 30))
        for i in range(24):
            a = i * 0.26
            s.ball((30 * math.cos(a), 18 * math.sin(a), 20 * math.sin(2 * a)), 3.0, blend=2.0, carve=bool(i % 3 == 0))
        s.stroke([(-30, 20, 0), (0, 26, 5), (30, 20, 0)], 2.5, blend=3.0)
        s.box((0, -30, 0), (100, 20, 100), carve=True, blend=4.0)
        s.noise(0.4, 6.0, seed=3)

        def blocks(prune):
            s.prune = prune
            lo, shape, bl, solid = s.sample(block=16, band=3.0)
            return {tuple(int(x) for x in ijk): v for ijk, v in bl}, sorted(map(tuple, solid))

        whole, sw = blocks(False)
        cut, sc = blocks(True)
        self.assertEqual(sorted(whole), sorted(cut))
        self.assertEqual(sw, sc)
        w_ = np.concatenate([whole[k].ravel() for k in whole])
        c_ = np.concatenate([cut[k].ravel() for k in whole])
        self.assertEqual(int(((w_ < 0) != (c_ < 0)).sum()), 0)              # (no voxel changes side)
        near = np.abs(w_) < s.voxel                                           # (what the mesher reads)
        self.assertLess(float(np.abs(w_ - c_)[near].max()), 1e-5)
        # (at the band's rim a relief's own cut-off sees a slightly different value: hundredths of a mm, never read)
        self.assertLess(float(np.abs(w_ - c_).max()), 0.05)
        self.assertLess(s.stats["kept_per_block"], s.stats["operations"] * 0.6)   # (most blocks drop most of them)

    def test_a_scans_height_map_stamps_the_surface_at_its_real_size(self):
        import tempfile

        chk = np.kron(np.array([[0, 1] * 4, [1, 0] * 4] * 4, dtype=np.float32), np.ones((8, 8)))   # (a checker)
        s = S.Canvas(voxel=0.25).ball((0, 0, 0), 20)
        with tempfile.TemporaryDirectory() as d:
            from PIL import Image

            path = os.path.join(d, "check_Displacement.png")
            Image.fromarray((chk * 255).astype(np.uint8)).save(path)
            h = S.load_height(path, size=64)
            self.assertEqual(h.shape, (64, 64))
            self.assertTrue(os.path.isfile(os.path.join(d, "check_Displacement_h64.npy")))
            s.stamp(path, tile_mm=16, depth=0.5, centre=(0, 0, 0), size=64)
        # on the +x side the yz-plane map shows: radial distance 20 +- 0.5 by the checker
        ys = np.linspace(-3, 3, 200)
        dirs = np.stack([np.full_like(ys, 20.0), ys, np.zeros_like(ys)], axis=1)
        dist = []
        for p in dirs:
            r = np.linspace(18, 22, 801)
            q = p[None, :] / np.linalg.norm(p) * r[:, None]
            inside = s.d(q) < 0
            dist.append(r[np.nonzero(inside)[0][-1]])
        dist = np.array(dist)
        self.assertGreater(float(dist.max() - dist.min()), 0.6)     # (the checker raised and pressed, ~1 mm apart)
        self.assertLess(float(np.abs(dist - 20).max()), 0.6)        # (never past its depth)
        self.assertIsInstance(s.root, S.Displace)                    # (a relief: the band and the pruning know it)

    def test_a_stiff_fit_moves_the_big_form_and_keeps_the_detail(self):
        # a UV sphere r 20 with a 1.5 mm bump; the reference: a plain sphere r 22
        nu, nv = 48, 24
        th = np.linspace(0, 2 * np.pi, nu, endpoint=False)
        ph = np.linspace(0.15, np.pi - 0.15, nv)
        T_, P_ = np.meshgrid(th, ph, indexing="ij")
        dirs = np.stack([np.sin(P_) * np.cos(T_), np.cos(P_), np.sin(P_) * np.sin(T_)], axis=-1).reshape(-1, 3)
        r = np.full(len(dirs), 20.0)
        bump = np.argmax(dirs[:, 2])
        r[bump] += 1.5
        v = dirs * r[:, None]
        idx = np.arange(len(v)).reshape(nu, nv)
        quads = np.array([[idx[i, j], idx[(i + 1) % nu, j], idx[(i + 1) % nu, j + 1], idx[i, j + 1]]
                          for i in range(nu) for j in range(nv - 1)])
        rng = np.random.default_rng(0)
        g = rng.normal(size=(60000, 3))
        target = g / np.linalg.norm(g, axis=1, keepdims=True) * 22.0
        out = S.fit_field(v, quads, np.zeros((0, 3), dtype=np.int64), target, strength=0.7, rounds=3)
        rad = np.linalg.norm(out, axis=1)
        self.assertAlmostEqual(float(np.median(rad)), 22.0, delta=0.4)          # (the big form: onto the reference)
        self.assertGreater(float(rad[bump] - np.median(rad)), 0.8)               # (the bump: still ours)

    def test_sharpening_puts_a_rounded_corner_back_on_the_edge(self):
        box = S.Box((0, 0, 0), (20, 20, 20))
        rounded = np.array([[9.7, 9.7, 0.0], [9.75, 9.7, 3.0]])   # (a mesher's vertex cut across the edge x = y = 10)
        edge = np.array([[10.0, 10.0, 0.0], [10.0, 10.0, 3.0]])
        before = np.linalg.norm(rounded[:, :2] - edge[:, :2], axis=1)
        after = S.sharpen(box.d, rounded, np.arange(2), voxel=0.5)
        moved = np.linalg.norm(after[:, :2] - edge[:, :2], axis=1)
        self.assertTrue((moved < before * 0.3).all())
        # a vertex on a flat face stays on it
        flat = S.sharpen(box.d, np.array([[10.0, 2.0, 1.0]]), np.arange(1), voxel=0.5)
        self.assertAlmostEqual(float(flat[0, 0]), 10.0, delta=0.02)
        # the feature vertices of a cube are its corners; a flat sheet has none
        cube_v = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], dtype=float)
        quads = np.array([[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]])
        self.assertEqual(len(S.feature_verts(cube_v, quads, np.zeros((0, 3)))), 8)
        sheet = np.array([[x, y, 0] for y in range(3) for x in range(3)], dtype=float)
        sq = np.array([[0, 1, 4, 3], [1, 2, 5, 4], [3, 4, 7, 6], [4, 5, 8, 7]])
        self.assertEqual(len(S.feature_verts(sheet, sq, np.zeros((0, 3)))), 0)

    def test_a_chamfer_join_is_a_flat_bevel_not_a_fillet(self):
        # two half-spaces (x < 0, y < 0) joined with a 4 mm join: the chamfer's surface is the straight line x + y = 4
        a = np.array([0.5, 2.0, 3.5])
        pts_a, pts_b = a, 4.0 - a
        cham = S.cmin(pts_a, pts_b, 4.0)
        self.assertTrue(np.allclose(cham, 0.0, atol=1e-9))                 # (every point of the line: on the bevel)
        self.assertGreater(float(S.smin(np.array([2.0]), np.array([2.0]), 4.0)[0]), 0.5)   # (the fillet is a curve)
        s = S.Canvas(voxel=0.25).box((0, 0, 0), (20, 20, 20)).box((0, 12, 0), (10, 6, 10), blend=3, edge="chamfer")
        self.assertEqual(s.root.edge, "chamfer")
        with self.assertRaises(ValueError):
            S.Canvas(voxel=0.5).ball((0, 0, 0), 5).ball((6, 0, 0), 2, edge="bevelled")
        # pruning stays exact with chamfer joins (the bevel never reaches past the band + its width)
        s.ball((30, 0, 0), 3, blend=2, edge="chamfer").ball((-30, 5, 0), 3, blend=2, carve=False)

        def blocks(prune):
            s.prune = prune
            _lo, _sh, bl, _so = s.sample(block=16, band=3.0)
            return np.concatenate([v.ravel() for _ijk, v in sorted(bl, key=lambda t: tuple(t[0]))])

        w_, c_ = blocks(False), blocks(True)
        self.assertEqual(int(((w_ < 0) != (c_ < 0)).sum()), 0)

    def test_a_mirrored_keep_keeps_the_shape_and_its_reflection_both(self):
        # a slab |z| < 30 kept to a ball off-centre at z = +10 (r 20), mirrored in z: the keep and its reflection's
        # (z = -10): only |z| < 10 remains — not their union (which kept z from -30 to 30)
        s = S.Canvas(voxel=0.5, mirror="z").box((0, 0, 0), (40, 40, 60))
        s.keep(S.Ball((0, 0, 10), 20))
        inside = lambda z: float(s.d(np.array([[0.0, 0.0, float(z)]]))[0]) < 0  # noqa: E731
        self.assertTrue(inside(0) and inside(8) and inside(-8))
        self.assertFalse(inside(15) or inside(-15))
        # ...and a symmetric shape kept on a mirrored canvas is unchanged by it
        t = S.Canvas(voxel=0.5, mirror="x").box((0, 0, 0), (40, 40, 40)).keep(S.Ball((0, 0, 0), 15))
        self.assertTrue(float(t.d(np.array([[0.0, 0.0, 14.0]]))[0]) < 0)

    def test_a_strap_is_a_flat_plate_not_a_tube(self):
        s = S.Canvas(voxel=0.25).strap([(-20, 0, 0), (20, 0, 0)], height=10, thickness=4)
        self.assertLess(float(s.d(np.array([[0.0, 4.6, 0.0]]))[0]), 0)     # (half its height up: inside)
        self.assertGreater(float(s.d(np.array([[0.0, 0.0, 2.3]]))[0]), 0)  # (past half its thickness: outside)
        # near a CORNER of its section: inside a plate, outside the ellipse a chain of ellipsoids would make
        corner = np.array([[0.0, 4.0, 1.4]])
        self.assertLess(float(s.d(corner)[0]), 0)
        self.assertGreater((1.4 / 2.0) ** 2 + (4.0 / 5.0) ** 2, 1.0)
        # a vertical strap: its height runs along z (a jaw's rising branch, front to back)
        v = S.Canvas(voxel=0.25).strap([(0, 0, 0), (0, 30, 0)], height=12, thickness=5)
        self.assertLess(float(v.d(np.array([[0.0, 15.0, 5.5]]))[0]), 0)
        self.assertGreater(float(v.d(np.array([[3.0, 15.0, 0.0]]))[0]), 0)
        # a bent strap stays one plate: the turn filled, no notch at the joint
        b = S.Canvas(voxel=0.25).strap([(0, 0, 0), (20, 0, 0), (30, 0, 15)], height=8, thickness=4)
        self.assertLess(float(b.d(np.array([[20.0, 0.0, 0.5]]))[0]), 0)
        # ...and it ENDS at its end points: no block standing past them
        self.assertGreater(float(b.d(np.array([[-1.0, 0.0, 0.0]]))[0]), 0)
        self.assertAlmostEqual(float(s.d(np.array([[20.0, 0.0, 0.0]]))[0]), 0.0, delta=0.05)
        with self.assertRaises(ValueError):
            S.strap_node([(0, 0, 0)], 4, 2)

    def test_points_drawn_by_eye_land_on_the_surface(self):
        s = S.Canvas(voxel=0.5).ball((0, 0, 0), 20).ellipsoid((0, 10, 0), (12, 14, 12), blend=4)
        drawn = [(0, 30, 0), (6, 12, 3), (14, 2, 9)]          # (above the dome, inside it, near it)
        on = np.array(s.on_surface(drawn))
        self.assertLess(float(np.max(np.abs(s.d(on)))), 0.05)
        under = np.array(s.on_surface(drawn, depth=1.0))
        self.assertTrue(np.allclose(s.d(under), -1.0, atol=0.05))

    def test_a_crease_floating_over_a_dome_is_warned_and_snap_lays_it_on(self):
        top = np.array([[0.0, 20.0, 0.0]])
        floating = S.Canvas(voxel=0.25).ball((0, 0, 0), 20).crease([(-6, 24, 0), (6, 24, 0)], 1.5)
        self.assertAlmostEqual(float(floating.d(top)[0]), 0.0, delta=0.05)   # (4 mm above the dome: it cut nothing)
        self.assertEqual(len(floating.warnings), 1)
        self.assertIn("snap=True", floating.warnings[0])
        snapped = S.Canvas(voxel=0.25).ball((0, 0, 0), 20).crease([(-6, 24, 0), (6, 24, 0)], 1.5, snap=True)
        self.assertGreater(float(snapped.d(top)[0]), 0.3)         # (on the surface: the groove is cut)
        self.assertEqual(snapped.warnings, [])

    def test_a_laid_path_adds_points_only_where_a_chord_leaves_the_surface(self):
        # (every span is a capsule evaluated at every voxel: a point every width made a skull's sutures 280 capsules)
        s = S.Canvas(voxel=0.45).ellipsoid((0, 142, 10), (70, 73, 86))
        drawn = [(x, 214.0 - x * 0.3, -22.0) for x in range(0, 60, 4)]   # (a vault-sized dome, drawn above it)
        laid = np.array(s._lay_on(drawn, 0.75))
        self.assertLessEqual(len(laid), len(drawn) + 2)
        mids = (laid[1:] + laid[:-1]) / 2.0
        self.assertLess(float(np.max(np.abs(s.d(mids)))), 0.75 * 0.25 + 0.01)
        sparse = np.array(S.Canvas(voxel=0.25).ball((0, 0, 0), 20)._lay_on([(-15, 24, 0), (15, 24, 0)], 0.75))
        self.assertGreater(len(sparse), 2)                        # (two ends across a small ball: points added)
        self.assertLess(float(np.max(np.abs(S.Ball((0, 0, 0), 20).d((sparse[1:] + sparse[:-1]) / 2.0)))), 0.2)


class Surface(unittest.TestCase):
    def test_noise_is_seeded_and_bounded(self):
        p = _pts(2000, 5.0)
        for kind, fn in S.NOISES.items():
            a = fn(p, seed=3) if kind in ("cells", "cracks", "perlin") else fn(p, 4, 3)
            b = fn(p, seed=3) if kind in ("cells", "cracks", "perlin") else fn(p, 4, 3)
            c = fn(p, seed=4) if kind in ("cells", "cracks", "perlin") else fn(p, 4, 4)
            self.assertTrue(np.array_equal(a, b), kind)
            self.assertFalse(np.allclose(a, c), kind)
            self.assertLessEqual(float(np.abs(a).max()), 1.25, kind)
            self.assertGreater(float(a.std()), 0.05, kind)   # (it varies)
        lattice = np.array([[0.0, 0, 0], [3.0, -2.0, 7.0]])
        self.assertTrue(np.allclose(S.perlin(lattice), 0.0))   # (gradient noise: zero at every lattice point)

    def test_relief_at_the_asked_size(self):
        s = S.Canvas(voxel=0.5).ball((0, 0, 0), 20).noise(1.0, 4.0, kind="fbm")
        dirs = RNG.normal(size=(300, 3))
        dirs /= np.linalg.norm(dirs, axis=1)[:, None]
        radii = []
        for d in dirs:   # (the surface along each ray, by bisection)
            lo_, hi_ = 10.0, 30.0
            for _ in range(40):
                m = (lo_ + hi_) / 2
                if s.d(np.array([d * m]))[0] < 0:
                    lo_ = m
                else:
                    hi_ = m
            radii.append(lo_)
        radii = np.array(radii)
        self.assertLess(float(np.abs(radii - 20).max()), 1.3)   # (about +-1 mm)
        self.assertGreater(float(radii.std()), 0.15)            # (and really rough)

    def test_stretched_relief_runs_along_its_axis(self):
        s = S.Canvas(voxel=0.5).box((0, 0, 0), (200, 200, 200)).noise(1.0, (3.0, 60.0, 3.0), kind="ridged")
        face = np.array([[100.0, y, z] for y in np.linspace(-40, 40, 41) for z in np.linspace(-40, 40, 41)])
        h = s.d(face).reshape(41, 41)   # (rows: y up the face, columns: z across it)
        along = float(np.abs(np.diff(h, axis=0)).mean())
        across = float(np.abs(np.diff(h, axis=1)).mean())
        self.assertGreater(across, 4 * along)   # (ridges run up y: it changes across them, hardly along them)
        with self.assertRaises(ValueError):
            S.Canvas().ball((0, 0, 0), 5).noise(1.0, (3.0, 0.0, 3.0))

    def test_inflate_in_a_region_only(self):
        s = S.Canvas(voxel=0.5).ball((0, 0, 0), 20)
        s.inflate(3.0, where=S.Ball((0, 20, 0), 6), falloff=4)
        top, side = np.array([[0.0, 22.0, 0]]), np.array([[22.0, 0, 0]])
        self.assertLess(float(s.d(top)[0]), 0)      # (swelled 3 mm on top)
        self.assertGreater(float(s.d(side)[0]), 0)  # (untouched on the side)

    def test_mirror_keeps_either_side(self):
        s = S.Canvas(voxel=0.5, mirror="x").ball((-30, 0, 0), 10)   # (authored on the - side)
        self.assertLess(float(s.d(np.array([[-30.0, 0, 0]]))[0]), 0)
        self.assertLess(float(s.d(np.array([[30.0, 0, 0]]))[0]), 0)

    def test_rotation_is_the_kits_order(self):
        # CFrame.Angles(rx, ry, rz) = Rx @ Ry @ Rz (rbx.py _rot): x turned 90 about y, then that frame about x
        m = S._rot((90, 90, 0))
        rx = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
        ry = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]])
        self.assertTrue(np.allclose(m, rx @ ry))

    def test_mirror_makes_it_symmetric(self):
        s = S.Canvas(voxel=0.5, mirror="x").ball((10, 0, 0), 5).stroke([(5, 5, 0), (15, 9, 3)], 2)
        p = _pts(300, 25.0)
        q = p * (-1, 1, 1)
        self.assertTrue(np.allclose(s.d(p), s.d(q)))
        self.assertLess(float(s.d(np.array([[-10.0, 0, 0]]))[0]), 0)   # (the mirrored ball exists)


SQ = [(-10.0, 0.0), (10.0, 0.0), (10.0, 20.0), (-10.0, 20.0)]


class Views(unittest.TestCase):
    """a sculpt started from (or trimmed to) the reference's TRACED views: the photos' silhouette"""

    def test_the_2d_distance_is_exact(self):
        d = S.sdf2d([SQ], np.array([[0.0, 10.0], [15.0, 10.0], [13.0, 24.0], [10.0, 5.0]]))
        self.assertTrue(np.allclose(d, [-10.0, 5.0, 5.0, 0.0]))   # (inside 10 from a side, out 5, a 3-4-5 corner)
        ring = [(-20.0, -20.0), (20.0, -20.0), (20.0, 20.0), (-20.0, 20.0)]
        hole = [(-5.0, -5.0), (5.0, -5.0), (5.0, 5.0), (-5.0, 5.0)]
        d = S.sdf2d([ring, hole], np.array([[0.0, 0.0], [10.0, 0.0]]))
        self.assertGreater(float(d[0]), 0)   # (the hole is outside)
        self.assertAlmostEqual(float(d[1]), -5.0)

    def test_two_views_make_their_visual_hull(self):
        # a side view 40 long x 20 tall (forward, up) and a front view 20 wide x 20 tall: the hull is that box
        side = [[(-20.0, 0.0), (20.0, 0.0), (20.0, 20.0), (-20.0, 20.0)]]
        c = S.Canvas(voxel=0.5).views(side=side, front=[SQ])
        inside = np.array([[0.0, 10.0, 0.0], [9.0, 2.0, -19.0]])
        out = np.array([[11.0, 10.0, 0.0], [0.0, 21.0, 0.0], [0.0, 10.0, 21.0]])
        self.assertTrue(np.all(c.d(inside) < 0))
        self.assertTrue(np.all(c.d(out) > 0))
        lo, hi = c.bounds(pad=0.0)
        self.assertTrue(np.allclose(lo, (-10 - 4.0, -4.0, -20 - 4.0), atol=0.01))   # (the raster's 8-pixel pad)
        with self.assertRaises(ValueError):
            S.Canvas(voxel=0.5).views(side=side)   # (a side alone is an endless prism)

    def test_a_sculpt_is_trimmed_to_the_silhouette(self):
        c = S.Canvas(voxel=0.5).ball((0, 10, 0), 16)
        c.views(front=[SQ], mode="keep")
        self.assertGreater(float(c.d(np.array([[14.0, 10.0, 0.0]]))[0]), 0)   # (past the front view's edge: gone)
        self.assertLess(float(c.d(np.array([[0.0, 10.0, 14.0]]))[0]), 0)    # (along the view: kept)

    def test_a_keep_trim_through_a_thin_island_is_warned_and_min_mm_drops_it(self):
        # a front outline: a 40 x 40 block, a 2 mm island 3 mm beside it (a styloid seen side-on), a 1 mm slit into it
        block = [(-20.0, 0.0), (20.0, 0.0), (20.0, 18.0), (12.0, 18.0), (12.0, 19.0), (20.0, 19.0), (20.0, 40.0),
                 (-20.0, 40.0)]
        island = [(23.0, 10.0), (25.0, 10.0), (25.0, 30.0), (23.0, 30.0)]
        clay = lambda: S.Canvas(voxel=0.4).box((0, 20, 0), (60, 44, 20))  # noqa: E731
        plain = clay().views(front=[block, island], mode="keep")
        fin, slit, body = np.array([[24.0, 20.0, 0.0]]), np.array([[16.0, 18.5, 0.0]]), np.array([[0.0, 20.0, 0.0]])
        self.assertLess(float(plain.d(fin)[0]), 0)            # (the island kept: a 2 mm fin of clay)
        self.assertGreater(float(plain.d(slit)[0]), 0)        # (the slit cut through)
        self.assertEqual(len(plain.warnings), 1)
        self.assertIn("min_mm=4", plain.warnings[0])
        clean = clay().views(front=[block, island], mode="keep", min_mm=4.0)
        self.assertGreater(float(clean.d(fin)[0]), 0)         # (no fin)
        self.assertLess(float(clean.d(slit)[0]), 0)           # (no slit)
        self.assertEqual(clean.warnings, [])
        # ...and the outline's own edges stay where they were: the distance re-measured only near what changed
        edge = np.array([[-20.0, 20.0, 0.0], [0.0, 40.0, 0.0], [-19.0, 20.0, 0.0]])
        self.assertTrue(np.allclose(clean.d(edge), plain.d(edge), atol=0.05))
        near_fixed = np.array([[20.5, 25.0, 0.0], [21.5, 12.0, 0.0]])   # (outside the block, where the island was)
        self.assertTrue(np.allclose(clean.d(near_fixed), [0.5, 1.5], atol=0.3))

    def test_traced_views_become_millimetres(self):
        # a side trace 1 long x 0.5 tall (design units) of a 400 mm object; its front 0.5 wide-ratio 1.0 (square)
        side = ([(0.0, 0.0), (1.0, 0.0), (1.0, 0.5), (0.0, 0.5)], [], 0.5)
        front = ([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], [], 1.0)
        sr, fr = S.trace_rings(side, front, length=400.0)
        self.assertEqual(sr[0][0], (-200.0, 0.0))     # (the back, at the bottom)
        self.assertEqual(sr[0][2], (200.0, 200.0))    # (the front, at the top: 0.5 x 400)
        self.assertEqual(fr[0][1], (-100.0, 0.0))     # (the picture's right is the model's LEFT: -x; width = 200)
        self.assertEqual(fr[0][2], (-100.0, 200.0))
        with self.assertRaises(ValueError):
            S.trace_rings(side, None)                  # (no length)
        _sr, fr2 = S.trace_rings(None, front, width=300.0)
        self.assertEqual(fr2[0][2], (-150.0, 300.0))

    def test_the_band_holds_for_a_traced_hull(self):
        side = [[(-20.0, 0.0), (5.0, 0.0), (20.0, 8.0), (20.0, 20.0), (-20.0, 20.0)]]
        c = S.Canvas(voxel=0.6).views(side=side, front=[SQ], blend=2.0).noise(0.5, 4.0)
        lo, dense = c.dense(exact=True)
        lo2, shape, blocks, solid = c.sample(block=16, band=3.0)
        bw = 3.0 * c.voxel
        full = np.full(tuple(-(-shape // 16) * 16), bw, dtype=np.float32)
        for ijk in solid:
            i, j, k = (int(x) for x in ijk)
            full[i:i + 16, j:j + 16, k:k + 16] = -bw
        for ijk, vals in blocks:
            i, j, k = (int(x) for x in ijk)
            full[i:i + 16, j:j + 16, k:k + 16] = vals
        band = full[:shape[0], :shape[1], :shape[2]]
        self.assertEqual(int(np.count_nonzero((dense < 0) != (band < 0))), 0)


def _cube(c, size):
    """a closed cube as 8 verts + 6 quads"""
    v = np.array([(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)], dtype=float) * size + c
    q = np.array([(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)])
    return v, q


class Specks(unittest.TestCase):
    def test_pieces_are_found_and_specks_dropped(self):
        (va, qa), (vb, qb), (vc, qc) = _cube((0, 0, 0), 50.0), _cube((100, 0, 0), 2.0), _cube((0, 100, 0), 30.0)
        verts = np.concatenate([va, vb, vc])
        quads = np.concatenate([qa, qb + 8, qc + 16])
        edges = np.concatenate([np.stack([quads[:, i], quads[:, (i + 1) % 4]], axis=1) for i in range(4)])
        self.assertEqual(len(np.unique(S.pieces(len(verts), edges))), 3)
        v2, q2, t2, dropped = S.drop_specks(verts, quads, np.zeros((0, 3), int), 12.0)
        self.assertEqual(dropped, 1)   # (the 2 mm cube: under 12 mm across)
        self.assertEqual((len(v2), len(q2)), (16, 12))
        self.assertLess(int(q2.max()), 16)   # (re-indexed)
        self.assertEqual(S.drop_specks(va, qa, np.zeros((0, 3), int), 12.0)[3], 0)


def _uv_sphere(r=20.0, n=24, noise=0.0):
    """a closed UV sphere (quads + the poles' triangles), its radius jittered by `noise` mm"""
    rng = np.random.default_rng(5)
    verts = [(0.0, r, 0.0)]
    for i in range(1, n):
        th = np.pi * i / n
        for j in range(2 * n):
            ph = 2 * np.pi * j / (2 * n)
            verts.append((r * np.sin(th) * np.cos(ph), r * np.cos(th), r * np.sin(th) * np.sin(ph)))
    verts.append((0.0, -r, 0.0))
    v = np.array(verts)
    v *= (1.0 + noise / r * rng.uniform(-1, 1, size=(len(v), 1)))
    ring = lambda i, j: 1 + (i - 1) * 2 * n + (j % (2 * n))   # noqa: E731
    quads = [(ring(i, j), ring(i, j + 1), ring(i + 1, j + 1), ring(i + 1, j)) for i in range(1, n - 1) for j in range(2 * n)]
    tris = [(0, ring(1, j + 1), ring(1, j)) for j in range(2 * n)] +            [(len(v) - 1, ring(n - 1, j), ring(n - 1, j + 1)) for j in range(2 * n)]
    return v, np.array(quads), np.array(tris)


class Smooth(unittest.TestCase):
    def test_taubin_relaxes_noise_and_keeps_the_size(self):
        v, q, t = _uv_sphere(noise=0.8)
        out = S.taubin(v, q, t, 10)
        r0, r1 = np.linalg.norm(v, axis=1), np.linalg.norm(out, axis=1)
        self.assertLess(float(r1.std()), 0.5 * float(r0.std()))     # (the noise relaxed)
        self.assertAlmostEqual(float(r1.mean()), float(r0.mean()), delta=0.25)   # (Taubin: no shrinking)

    def test_a_region_only(self):
        v, q, t = _uv_sphere(noise=0.8)
        w = (v[:, 1] > 5).astype(float)   # (the top cap only)
        out = S.taubin(v, q, t, 10, weight=w)
        self.assertTrue(np.allclose(out[w == 0], v[w == 0]))   # (the rest exactly where it was)
        self.assertFalse(np.allclose(out[w == 1], v[w == 1]))


class Band(unittest.TestCase):
    def _reassemble(self, s, block):
        lo, shape, blocks, solid = s.sample(block=block, band=3.0)
        bw = 3.0 * s.voxel
        full = np.full(tuple(-(-shape // block) * block), bw, dtype=np.float32)
        for ijk in solid:
            i, j, k = (int(x) for x in ijk)
            full[i:i + block, j:j + block, k:k + block] = -bw
        for ijk, vals in blocks:
            i, j, k = (int(x) for x in ijk)
            full[i:i + block, j:j + block, k:k + block] = vals
        return lo, full[:shape[0], :shape[1], :shape[2]]

    def test_the_narrow_band_never_misses_the_surface(self):
        s = S.Canvas(voxel=0.6, mirror="x").ellipsoid((8, 0, 0), (14, 10, 9)).ball((0, 12, 0), 7, blend=4)
        s.capsule((4, -8, 0), (14, -20, 6), 4, 2, blend=2).crease([(-10, 6, 8), (10, 6, 8)], 1.5)
        s.noise(0.6, 3.0, kind="ridged")
        lo, dense = s.dense(exact=True)   # (the truth: every relief evaluated everywhere)
        bw = 3.0 * s.voxel
        near = np.abs(dense) < bw
        for block in (8, 16):   # (16: each block culled again in 8^3 pieces — the default path)
            lo2, band = self._reassemble(s, block=block)
            self.assertTrue(np.allclose(lo, lo2))
            self.assertEqual(dense.shape, band.shape)
            self.assertTrue(np.array_equal(dense < 0, band < 0), block)   # (inside / outside the same everywhere)
            self.assertTrue(np.allclose(dense[near], band[near], atol=1e-4), block)   # (and the band's values)

    def _agrees(self, s, block=16):
        lo, dense = s.dense(exact=True)
        _lo2, band = self._reassemble(s, block=block)
        return int(np.count_nonzero((dense < 0) != (band < 0)))

    def test_a_long_thin_limb_is_not_culled_into_a_box(self):
        # (an elongated ellipsoid's inside rose steeply near its axis: 3,176 voxels wrong, the review 2026-10-10)
        self.assertEqual(self._agrees(S.Canvas(voxel=1.0).ellipsoid((0, 0, 0), (20, 4.5, 4.5))), 0)
        self.assertEqual(self._agrees(S.Canvas(voxel=1.0).ellipsoid((0, 0, 0), (40, 4.5, 4.5), rot=(0, 0, 30))), 0)

    def test_a_hard_edged_inflate_is_not_clipped(self):
        s = S.Canvas(voxel=1.0).ball((0, 0, 0), 30)
        s.inflate(14, where=S.Box((0, 25, 0), (30, 30, 30)))   # (falloff 0: a step)
        self.assertEqual(self._agrees(s), 0)

    def test_relief_survives_a_later_inflate_and_a_coarser_relief(self):
        s = S.Canvas(voxel=0.5).ball((0, 0, 0), 20).noise(1.0, 4.0).inflate(4.0)
        self.assertEqual(self._agrees(s), 0)   # (it was erased: the noise measured from its own surface)
        t = S.Canvas(voxel=0.5).ball((0, 0, 0), 20).noise(0.6, 3.0, seed=1).noise(5.0, 30.0, seed=2)
        self.assertEqual(self._agrees(t), 0)

    def test_lost_names_detail_under_the_voxel(self):
        s = S.Canvas(voxel=0.5).ball((0, 0, 0), 20).crease([(-5, 20, 0), (5, 20, 0)], 0.5)
        s.noise(0.05, 4.0)
        lost = s.lost()
        self.assertEqual([w for _op, w, _f in lost], ["crease", "fbm noise"])
        self.assertEqual(S.Canvas(voxel=0.5).ball((0, 0, 0), 20).lost(), [])


if __name__ == "__main__":
    unittest.main()
