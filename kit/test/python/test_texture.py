"""kit gen texture + a.texture_from: the arithmetic that must hold for a picture's paint to land on the kit's own
geometry — the unit box TRELLIS.2 paints in is undone exactly (kit/gen/trellis2_texture.py), the exported mesh file
reads back as written, the painted maps mix in only where the bake found the painted surface, and the coverage is
counted on the atlas's own texels (kit/blender/rbx_texture.py)."""

import os
import socket
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "gen"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
import rbx_texture as RT  # noqa: E402

_connect = socket.socket.connect
import trellis2_texture as T2  # noqa: E402


def trellis_unit(v):
    """TRELLIS.2's Trellis2TexturingPipeline.preprocess_mesh, as written there: centre, scale, Y up -> Z up"""
    v = np.array(v, dtype=np.float64)
    lo, hi = v.min(axis=0), v.max(axis=0)
    v = (v - (lo + hi) / 2) * (0.99999 / (hi - lo).max())
    tmp = v[:, 1].copy()
    v[:, 1] = -v[:, 2]
    v[:, 2] = tmp
    return v


def trellis_out(v):
    """its postprocess_mesh's turn back ("swap Y and Z axes, invert Y")"""
    v = np.array(v, dtype=np.float64)
    v[:, 1], v[:, 2] = v[:, 2], -v[:, 1].copy()
    return v


class TestFrame(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(3)
        # a sword-like box: long in Y (Roblox up), thin in Z, off the origin
        self.v = rng.random((500, 3)) * np.array([0.75, 4.4, 0.16]) + np.array([-0.375, 0.0, -0.08])

    def test_importing_the_runner_leaves_the_network_alone(self):
        # (the offline guard is applied when the runner RUNS, by trellis2_run, not when its helpers are imported)
        self.assertIs(socket.socket.connect, _connect)

    def test_unit_frame_is_trellis_own_box(self):
        centre, scale = T2.unit_frame(self.v)
        mine = (self.v - centre) * scale
        theirs = trellis_out(trellis_unit(self.v))  # (their two turns cancel: the input's own axes)
        self.assertLess(float(np.abs(mine - theirs).max()), 1e-12)
        self.assertTrue(bool((np.abs(trellis_unit(self.v)) <= 0.5).all()))

    def test_restore_puts_the_painted_mesh_back_where_it_was_built(self):
        centre, scale = T2.unit_frame(self.v)
        painted = trellis_out(trellis_unit(self.v)).astype(np.float32)  # (the GLB keeps float32)
        back = T2.restore(painted, centre, scale)
        self.assertLess(float(np.abs(back - self.v).max()), 4.4 * 1e-6)
        self.assertEqual(back.shape, self.v.shape)

    def test_surface_mean_reads_uv_with_v_up(self):
        # a texture red in its top half, blue in its bottom half (rows top-down, as an image is stored)
        tex = np.zeros((8, 8, 3), np.uint8)
        tex[:4] = (255, 0, 0)
        tex[4:] = (0, 0, 255)
        verts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], np.float64)
        faces = np.array([[0, 1, 2], [0, 2, 3]])
        top = np.array([[0.1, 0.6], [0.9, 0.6], [0.9, 0.9], [0.1, 0.9]])  # v up: the TOP of the image
        self.assertEqual(T2.surface_mean(verts, faces, top, tex, samples=2000), [255.0, 0.0, 0.0])
        bottom = top - np.array([0.0, 0.5])
        self.assertEqual(T2.surface_mean(verts, faces, bottom, tex, samples=2000), [0.0, 0.0, 255.0])

    def test_surface_mean_weighs_by_area(self):
        tex = np.zeros((4, 4, 3), np.uint8)
        tex[:, :2] = 200  # left half grey, right half black
        verts = np.array([[0, 0, 0], [3, 0, 0], [3, 1, 0], [10, 0, 0], [11, 0, 0], [11, 1, 0]], np.float64)
        faces = np.array([[0, 1, 2], [3, 4, 5]])  # a 3x larger triangle reads the grey half
        uv = np.array([[0.1, 0.5], [0.2, 0.5], [0.2, 0.6], [0.8, 0.5], [0.9, 0.5], [0.9, 0.6]])
        m = T2.surface_mean(verts, faces, uv, tex, samples=40000)[0]
        self.assertAlmostEqual(m, 200 * 0.75, delta=3.0)


class TestPly(unittest.TestCase):
    def test_round_trip(self):
        v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1.5]], np.float64)
        t = np.array([[0, 1, 2], [0, 1, 3], [0, 2, 3], [1, 2, 3]])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.ply")
            RT.write_ply(p, v, t)
            with open(p, "rb") as fh:
                self.assertTrue(fh.read(40).startswith(b"ply\nformat binary_little_endian 1.0\n"))
            v2, t2 = RT.read_ply(p)
        self.assertTrue(np.array_equal(v2, v.astype(np.float32)))
        self.assertTrue(np.array_equal(t2, t))

    def test_a_triangle_past_the_vertices_is_refused(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            RT.write_ply(os.path.join(d, "m.ply"), np.zeros((3, 3)), [[0, 1, 3]])


def maps(h, w, rgb):
    a = np.ones((h, w, 4), np.float32)
    a[..., :3] = rgb
    return a


class TestMix(unittest.TestCase):
    def setUp(self):
        self.kit, self.src = maps(4, 4, (0.2, 0.4, 0.6)), maps(4, 4, (1.0, 0.0, 0.0))
        self.src[..., 3] = 0.5  # (the painted map's alpha never reaches the kit's)

    def test_full_mix_where_found_is_the_painted_map(self):
        out = RT.mix(self.kit, self.src, np.ones((4, 4)), 1.0)
        self.assertTrue(np.allclose(out[..., :3], (1.0, 0.0, 0.0)))
        self.assertTrue(np.allclose(out[..., 3], 1.0))

    def test_nothing_changes_where_the_ray_missed_or_at_mix_zero(self):
        hit = np.zeros((4, 4))
        self.assertTrue(np.allclose(RT.mix(self.kit, self.src, hit, 1.0), self.kit))
        self.assertTrue(np.allclose(RT.mix(self.kit, self.src, np.ones((4, 4)), 0.0), self.kit))

    def test_mix_is_linear_and_per_texel(self):
        hit = np.zeros((4, 4))
        hit[0, 0] = 1.0
        out = RT.mix(self.kit, self.src, hit, 0.25)
        self.assertTrue(np.allclose(out[0, 0, :3], (0.4, 0.3, 0.45)))
        self.assertTrue(np.allclose(out[1:, :, :3], (0.2, 0.4, 0.6)))
        self.assertTrue(np.allclose(self.kit[0, 0, :3], (0.2, 0.4, 0.6)))  # (the input is never written)


class TestFacts(unittest.TestCase):
    def test_coverage_counts_the_atlas_own_texels_only(self):
        island = np.zeros((4, 4))
        island[:2] = 1  # 8 texels of atlas; the rest is margin / empty
        hit = np.ones((4, 4))  # (the bake margin spreads hits into the gutter: those must not count)
        hit[0, :2] = 0  # 2 atlas texels where the ray missed
        kit = {"color": maps(4, 4, (0.5, 0.5, 0.5)), "rough": maps(4, 4, 0.3), "metal": maps(4, 4, 1.0)}
        src = {"color": maps(4, 4, (0.7, 0.5, 0.3)), "rough": maps(4, 4, 0.8), "metal": maps(4, 4, 0.0)}
        f = RT.facts(kit, src, hit, island)
        self.assertEqual(f["coverage_pct"], 75.0)
        self.assertEqual(f["texels"], 8)
        self.assertAlmostEqual(f["mean_diff"]["color"], (0.2 + 0.0 + 0.2) / 3, places=4)
        self.assertAlmostEqual(f["mean_diff"]["rough"], 0.5, places=4)
        self.assertAlmostEqual(f["mean_diff"]["metal"], 1.0, places=4)
        self.assertEqual(f["mean_rgb"]["kit"], [127.5, 127.5, 127.5])
        self.assertEqual(f["mean_rgb"]["texture"], [178.5, 127.5, 76.5])

    def test_nothing_found_says_so(self):
        kit = {"color": maps(2, 2, 0.5)}
        f = RT.facts(kit, {"color": maps(2, 2, 0.1)}, np.zeros((2, 2)), np.ones((2, 2)), ("color",))
        self.assertEqual(f["coverage_pct"], 0.0)
        self.assertIsNone(f["mean_diff"]["color"])


if __name__ == "__main__":
    unittest.main()
