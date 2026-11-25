"""kit world meshes kind "wall": the modular castle masonry (castle_blender.py) - pure geometry + the stone atlas."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "world"))
import castle_blender as cb  # noqa: E402

REC = {"name": "t", "kind": "wall", "seed": 3}


class Wall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = cb.wall_mesh(REC)
        cls.v = np.array(cls.m.v)

    def test_it_fits_a_mesh_budget_and_stays_in_its_module(self):
        tris = sum(len(f) - 2 for f in self.m.f)
        self.assertLess(tris, 9000)  # (meshes_blender.MAX_TRIS)
        self.assertGreaterEqual(self.v[:, 0].min(), -1e-6)
        self.assertLessEqual(self.v[:, 0].max(), 24 + 1e-6)

    def test_modules_tile_without_a_seam(self):
        # every course's joint pattern wraps: the block edges cut at x = 0 and at x = L sit at the same heights
        front = self.v[(self.v[:, 1] < 0.15) & (self.v[:, 1] > -0.2)]  # (the face, its chamfer rims and jitter)
        z0 = {round(z, 3) for x, _, z in front if abs(x) < 1e-6}
        zL = {round(z, 3) for x, _, z in front if abs(x - 24) < 1e-6}
        self.assertGreater(len(z0), 10)
        self.assertEqual(z0, zL)

    def test_every_face_uses_one_atlas_tile(self):
        uv = np.array(self.m.uv)
        self.assertTrue(np.all((uv >= 0) & (uv <= 1)))
        for f in self.m.f[:400]:
            cols = {int(uv[i][0] * cb.TILE_N) for i in f}
            self.assertEqual(len(cols), 1)

    def test_the_blind_arches_are_open_to_their_recess(self):
        # nothing stands at the wall's face inside an opening (the old mortar core closed them)
        cx, ar = 6.0, 3.0
        inside = (np.abs(self.v[:, 0] - cx) < ar - 0.3) & (self.v[:, 2] > 4) & (self.v[:, 2] < 7.5) & (np.abs(self.v[:, 1]) < 0.3)
        self.assertEqual(int(inside.sum()), 0)

    def test_inset_moves_each_edge_in_by_its_amount(self):
        sq = [(0, 0), (2, 0), (2, 1), (0, 1)]
        out = cb.inset(sq, [0.1, 0.0, 0.1, 0.0])
        self.assertAlmostEqual(out[0][1], 0.1)
        self.assertAlmostEqual(out[1][0], 2.0)  # (a cut edge keeps its line)
        self.assertAlmostEqual(out[2][1], 0.9)


class Atlas(unittest.TestCase):
    def test_one_homogeneous_stone_not_a_patchwork(self):
        img = cb.atlas([138, 131, 120], 256, 3)
        t = 256 // cb.TILE_N
        means = np.array([img[(k // cb.TILE_N) * t:(k // cb.TILE_N + 1) * t, (k % cb.TILE_N) * t:(k % cb.TILE_N + 1) * t, :3].mean()
                          for k in range(cb.STONE_TILES)])
        self.assertLess(means.std() / means.mean(), 0.1)
        mortar = img[(cb.MORTAR0 // cb.TILE_N) * t:(cb.MORTAR0 // cb.TILE_N + 1) * t, :t * 4, :3].mean()
        self.assertLess(mortar, means.min())  # (joints read darker than any stone)
        self.assertEqual(img.dtype, np.float32)



class TowerRoofRoot(unittest.TestCase):
    def test_tower_and_roof_fit_the_budget(self):
        for f, rec in ((cb.tower_mesh, {"seed": 3}), (cb.tower_mesh, {"seed": 3, "ruin": 0.6}), (cb.roof_mesh, {"seed": 3})):
            m = f(rec)
            self.assertLess(sum(len(x) - 2 for x in m.f), 9000)

    def test_arrow_slits_are_open(self):
        rec = {"seed": 3, "radius": 6.5, "slits": 4}
        m = cb.tower_mesh(rec)
        v = np.array(m.v)
        r = np.hypot(v[:, 0], v[:, 1])
        ang = np.arctan2(v[:, 1], v[:, 0])
        # the slit list is seeded: rebuild it the way tower_mesh does and look into each slit's middle
        import random, math
        rng = random.Random(3)
        slits = [(2 * math.pi * k / 4 + rng.uniform(-0.2, 0.2), rng.uniform(7, 30 - 7.5 - 5)) for k in range(4)]
        for sa, sz in slits:
            d = np.abs((ang - sa + np.pi) % (2 * np.pi) - np.pi)
            face = (d < 0.1 / 6.5) & (np.abs(r - 6.5) < 0.05) & (v[:, 2] > sz + 0.6) & (v[:, 2] < sz + 2.4)
            self.assertEqual(int(face.sum()), 0)

    def test_roof_is_made_of_slates_on_slate_tiles(self):
        m = cb.roof_mesh({"seed": 3})
        uv = np.array(m.uv)
        tiles = {int(u * cb.TILE_N) + cb.TILE_N * (cb.TILE_N - 1 - int(v * cb.TILE_N)) for u, v in uv}
        self.assertTrue(any(cb.SLATE0 <= t < cb.STONE_TILES for t in tiles))
        self.assertGreater(len(m.f), 400)
        img = cb.atlas([150, 139, 120], 256, 3, slate=[50, 56, 68])
        t = 256 // cb.TILE_N
        slate = img[(cb.SLATE0 // cb.TILE_N) * t:(cb.SLATE0 // cb.TILE_N + 1) * t, :, :3].mean()
        self.assertLess(slate, img[:t, :, :3].mean() * 0.7)

    def test_root_bark_runs_continuously_and_glows_only_in_fissures(self):
        bark, glow = cb.root_mesh({"seed": 4, "path": [[0, 60, 60], [0, 10, 30], [0, 0, 10], [-3, -3, 0]], "strands": 3})
        self.assertLess(sum(len(x) - 2 for x in bark.f), 9000)
        self.assertGreater(len(glow.f), 20)
        self.assertLess(len(glow.f), len(bark.f) * 0.2)  # (light lives in the cracks, not on the surface)
        uv = np.array(bark.uv)
        f0, f1 = bark.f[0], bark.f[8]  # (the first ring's face and the next ring's, same strand)
        self.assertAlmostEqual(uv[f0[3]][1], uv[f1[0]][1], places=6)  # (v continues from ring to ring: no patchwork)
        tex = cb.bark_texture([118, 92, 52], 128, 1)
        self.assertLess(np.abs(tex[0, :, :3] - tex[-1, :, :3]).mean(), 0.08)  # (tiles: the top and bottom edges meet)


class ReviewRegressions(unittest.TestCase):
    """the 2026-10-24 adversarial review's repros"""

    def test_no_block_covers_a_slit_on_any_seed(self):
        import math, random
        for seed in range(1, 9):
            m = cb.tower_mesh({"seed": seed, "radius": 6.5, "height": 30, "slits": 5})
            rng = random.Random(seed)
            slits = [(2 * math.pi * k / 5 + rng.uniform(-0.2, 0.2), rng.uniform(7, 30 - 7.5 - 5)) for k in range(5)]
            v = np.array(m.v)
            r = np.hypot(v[:, 0], v[:, 1])
            ang = np.arctan2(v[:, 1], v[:, 0])
            for sa, sz in slits:
                d = np.abs((ang - sa + np.pi) % (2 * np.pi) - np.pi)
                inside = (d < 0.2 / 6.5) & (np.abs(r - 6.5) < 0.05) & (v[:, 2] > sz + 0.3) & (v[:, 2] < sz + 2.7)
                self.assertEqual(int(inside.sum()), 0, f"seed {seed} slit at {sa:.2f}")

    def test_a_ruined_parapet_is_capped_not_hollow(self):
        m = cb.wall_mesh({"name": "t", "seed": 2, "ruin": 0.8})
        v = np.array(m.v)
        b1 = 14.0 + 0.85 + 1.6
        tops = [f for f in m.f if all(abs(v[i][2] - b1) < 1e-6 for i in f) and all(-1e-6 <= v[i][1] <= 1.3 + 1e-6 for i in f)]
        covered = sum(max(v[i][0] for i in f) - min(v[i][0] for i in f) for f in tops)
        self.assertGreaterEqual(covered, 24 - 1e-6)

    def test_the_tower_crenels_are_open_from_inside(self):
        import math
        m = cb.tower_mesh({"seed": 1, "radius": 6.5, "height": 30})
        para_r = 6.5 + 0.75
        nm = max(8, int(2 * math.pi * para_r / 3.6))
        v = np.array(m.v)
        for f in m.f:
            pts = v[f]
            if not np.all(np.abs(np.hypot(pts[:, 0], pts[:, 1]) - (para_r - 1.1)) < 1e-3):
                continue
            if pts[:, 2].max() <= 30 - 2.3 + 0.1:
                continue  # (the breastwork below the crenels may run all round)
            a = math.atan2(pts[:, 1].mean(), pts[:, 0].mean()) % (2 * math.pi)
            k = a / (2 * math.pi / nm)
            self.assertLessEqual(k - math.floor(k), 0.6 + 1e-3, "an inner face closes a crenel")

    def test_cairn_tops_are_projected_from_above(self):
        m = cb.cairn_mesh({"seed": 3, "stones": 5})
        v, uv = np.array(m.v), np.array(m.uv)
        top, side = [], []
        for f in m.f:
            pa, pb, pc = v[f[0]], v[f[1]], v[f[2]]
            n = np.cross(pb - pa, pc - pa)
            area = np.linalg.norm(n) / 2
            if area < 1e-9:
                continue
            ua, ub, uc = uv[f[0]], uv[f[1]], uv[f[2]]
            uv_area = abs((ub[0] - ua[0]) * (uc[1] - ua[1]) - (uc[0] - ua[0]) * (ub[1] - ua[1])) / 2
            (top if abs(n[2]) / (2 * area) > 0.9 else side).append(uv_area / area)
        # a top face gets texture area like a side face does (projected sideways it collapsed to a streak)
        self.assertGreater(np.median(top), 0.3 * np.median(side))

    def test_root_bark_repeats_once_per_circumference_everywhere(self):
        bark, _ = cb.root_mesh({"seed": 1, "path": [[0, 0, 40], [5, 5, 20], [0, 0, 5], [-4, -2, 0]], "strands": 2})
        uv = np.array(bark.uv)
        vs = uv[:, 1]
        self.assertTrue(np.all(np.isfinite(vs)))
        step = np.abs(np.diff(vs.reshape(-1, 4)[:, 0]))
        step = step[step > 0]
        self.assertLess(np.percentile(step, 95) / np.percentile(step, 5), 12)  # (was 0.17x..5.3x swings: ~31x)

    def test_an_open_arch_is_a_doorway_through_the_wall(self):
        rec = {"name": "p", "seed": 9, "length": 10, "bays": 1, "arch_r": 2.4, "corbels": False, "parapet": False, "back": False, "thick": 3}
        for open_, expect_empty in ((True, True), (False, False)):
            v = np.array(cb.wall_mesh(dict(rec, open=open_)).v)
            inside = (np.abs(v[:, 0] - 5) < 2.0) & (v[:, 2] > 4) & (v[:, 2] < 7.5) & (v[:, 1] > 0.2) & (v[:, 1] < 3.2)
            self.assertEqual(int(inside.sum()) == 0, expect_empty)  # (a blind arch keeps its back wall)

    def test_a_gate_is_open_to_the_ground_through_the_whole_wall(self):
        rec = {"name": "g", "seed": 5, "length": 8.1, "bays": 1, "arch_r": 4.05, "open": "ground", "thick": 2.7}
        v = np.array(cb.wall_mesh(rec).v)
        cx, ar, sp = 4.05, 4.05, 8.0
        shape = ((v[:, 2] <= sp) & (np.abs(v[:, 0] - cx) < ar - 0.15) & (v[:, 2] > 0.15)) | ((np.hypot(v[:, 0] - cx, v[:, 2] - sp) < ar - 0.15) & (v[:, 2] > sp))
        self.assertEqual(int((shape & (v[:, 1] > -0.45) & (v[:, 1] < 2.65)).sum()), 0)

    def test_a_tower_door_is_open_and_within_budget(self):
        m = cb.tower_mesh({"seed": 7, "radius": 8.7, "height": 30, "door": {"angle": 0, "width": 4.1, "height": 7.3}})
        v = np.array(m.v)
        r, a = np.hypot(v[:, 0], v[:, 1]), np.arctan2(v[:, 1], v[:, 0])
        self.assertEqual(int(((np.abs(a) < 1.6 / 8.7) & (v[:, 2] > 0.3) & (v[:, 2] < 6.8) & (r > 6.4) & (r < 10)).sum()), 0)
        self.assertLess(sum(len(f) - 2 for f in m.f), 9000)

if __name__ == "__main__":
    unittest.main()
