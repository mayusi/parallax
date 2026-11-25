"""H6 noise in the model's own space (his limitations review V3: "move rbx_layers noise/patterns to world_pos 3D
coordinates" - "UV noise relief leaks at seams"): a new piece's bake draws its noise fields at each texel's place on
the model (rbx_wear.uv_positions / fbm3), so a patch runs on across the unwrap's seams; a piece built before
2026-11-17 bakes as before (rbx_wear.built_before - the owner: "New pieces only")."""

import json
import os
import subprocess
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_layers as L  # noqa: E402
import rbx_wear as W  # noqa: E402

BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
# one 80 x 90 mm sheet in two islands: far apart in the map, meeting on the model at x = 40 mm
UV = np.array([[[0.05, 0.05], [0.45, 0.05], [0.45, 0.95]], [[0.05, 0.05], [0.45, 0.95], [0.05, 0.95]],
               [[0.55, 0.05], [0.95, 0.05], [0.95, 0.95]], [[0.55, 0.05], [0.95, 0.95], [0.55, 0.95]]])
POS = np.array([[[0, 0, 0], [40, 0, 0], [40, 90, 0]], [[0, 0, 0], [40, 90, 0], [0, 90, 0]],
                [[40, 0, 0], [80, 0, 0], [80, 90, 0]], [[40, 0, 0], [80, 90, 0], [40, 90, 0]]], float)


class Places(unittest.TestCase):
    def test_each_texel_knows_its_place(self):
        P, inside = W.uv_positions(UV, POS, 256, pad=0)
        self.assertAlmostEqual(float(inside.mean()), 0.72, delta=0.02)
        row = 128   # (v = 0.5: 45 mm up)
        self.assertAlmostEqual(float(P[row, int(0.25 * 256), 0]), 20.0, delta=0.3)
        self.assertAlmostEqual(float(P[row, int(0.75 * 256), 0]), 60.0, delta=0.3)
        self.assertAlmostEqual(float(P[row, 100, 1]), 45.0, delta=0.4)
        self.assertAlmostEqual(W.mm_per_texel(P, inside), 80.0 / (0.8 * 256), delta=0.02)

    def test_the_margin_takes_its_islands_place(self):
        P0, i0 = W.uv_positions(UV, POS, 256, pad=0)
        P, inside = W.uv_positions(UV, POS, 256)
        self.assertGreater(int(inside.sum()), int(i0.sum()))
        edge = int(0.45 * 256) - 1        # the left island's last texel on that row ...
        out = edge + 5                    # ... and a margin texel past it: the same place
        self.assertTrue(i0[128, edge] and not i0[128, out] and inside[128, out])
        self.assertTrue(np.allclose(P[128, out], P[128, edge], atol=1e-4))


class Field(unittest.TestCase):
    def test_the_field_runs_on_across_a_seam(self):
        P, inside = W.uv_positions(UV, POS, 256)
        f3 = W.fbm3(P, inside, 7, 4, 30.0)
        a, b = int(0.449 * 256), int(0.551 * 256)   # the seam's two sides: 0.5 mm apart on the model
        d3 = float(np.abs(f3[20:236, a] - f3[20:236, b]).mean())
        f2 = W.fbm(256, np.random.default_rng(7), 4, 6)   # (the map's field: the two sides are 26 texels apart)
        d2 = float(np.abs(f2[20:236, a] - f2[20:236, b]).mean())
        self.assertLess(d3, 0.01)
        self.assertGreater(d2, 3 * d3)

    def test_spread_like_the_maps_field_and_the_same_twice(self):
        P = np.random.default_rng(0).random((256, 256, 3)).astype(np.float32) * 400
        inside = np.ones((256, 256), bool)
        f = W.fbm3(P, inside, 3, 4, 50.0)
        self.assertAlmostEqual(float(f.mean()), 0.5, delta=0.03)
        self.assertAlmostEqual(float(f.std()), 0.135, delta=0.04)
        self.assertTrue(np.array_equal(f, W.fbm3(P, inside, 3, 4, 50.0)))

    def test_a_layers_noise_and_its_top_take_the_places(self):
        P, inside = W.uv_positions(UV, POS, 128)
        flat = L.noise(128, np.random.default_rng(1), "patches")
        on = L.noise(128, np.random.default_rng(1), "patches", (P, inside), 1.6)
        self.assertEqual(on.shape, flat.shape)
        self.assertFalse(np.array_equal(on, flat))
        top = L.top_noise(128, np.random.default_rng(2), 0.4, 1.6, (P, inside))
        self.assertTrue(0.0 <= float(top.min()) and float(top.max()) <= 1.0)


class OnlyNewPieces(unittest.TestCase):
    def test_built_before(self):
        self.assertEqual(W.built_before("sword", ROOT)[0], True)  # (a starter on kit/blender/spec_occ_before.json)
        self.assertEqual(W.built_before("_selftest_x", ROOT)[0], True)
        self.assertEqual(W.built_before("a_piece_nobody_has_built_yet", ROOT)[0], False)


def bake(how):
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                          os.path.join(ROOT, "kit", "selftest", "blender", "build_noise3.py"), "--", how],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200)
    i = out.stdout.rfind("NOISE3 ")
    return out.returncode, (json.JSONDecoder().raw_decode(out.stdout[i + 7:])[0] if i >= 0 else None), \
        out.stdout[-1500:] + out.stderr[-1500:]


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class TheBake(unittest.TestCase):
    """a sculpted ball (many islands, smooth everywhere) under a soot layer placed by the noise alone"""

    @classmethod
    def setUpClass(cls):
        cls.off, cls.on = bake("off"), bake("on")

    def test_across_the_map_the_seams_jump(self):
        code, g, log = self.off
        self.assertEqual(code, 0, log)
        self.assertGreater(g["seam_edges"], 100)
        self.assertGreater(g["seam_jump"], 3 * g["plain_jump"], g)

    def test_on_the_model_a_seam_is_like_any_edge(self):
        code, g, log = self.on
        self.assertEqual(code, 0, log)
        self.assertLess(g["seam_jump"], 1.5 * g["plain_jump"], g)


if __name__ == "__main__":
    unittest.main()
