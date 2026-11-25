"""A tile repeats both ways as baked (card s4wc: "a tile's fade smears a patterned finish for an eighth at each
edge"): a NEW tile's noise is drawn on a flat torus - x and z each round a circle the tile's width long, in four
dimensions (rbx_wear.wrap_xz, perlin4 / fbm4; Blender's noise nodes in 4D) - so no cross-fade is needed."""

import json
import os
import subprocess
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_wear as W  # noqa: E402

BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


class Torus(unittest.TestCase):
    def test_4d_noise_like_3d(self):
        p = np.random.default_rng(0).random((100000, 4)).astype(np.float32) * 20
        f = W.fbm4(p, 4, 3)
        self.assertAlmostEqual(float(f.mean()), 0.0, delta=0.02)
        self.assertAlmostEqual(float(f.std()), 0.23, delta=0.04)
        self.assertTrue(np.array_equal(f, W.fbm4(p, 4, 3)))

    def test_a_tile_field_repeats_both_ways(self):
        L = 2240.0
        X, Z = np.meshgrid(np.linspace(-L / 2, L / 2, 101), np.linspace(0, L, 101))
        q = W.wrap_xz(np.stack([X, np.zeros_like(X), Z], axis=2), L, L)
        g = W.fbm3(q, np.ones(X.shape, bool), 5, 4, 300.0)
        self.assertLess(float(np.abs(g[:, 0] - g[:, -1]).max()), 1e-5)
        self.assertLess(float(np.abs(g[0] - g[-1]).max()), 1e-5)
        step = np.linalg.norm(np.diff(q[50], axis=0), axis=1)
        self.assertTrue(np.allclose(step, L / 100, rtol=1e-3))   # (at the places' own scale: a flat torus)


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class TheTile(unittest.TestCase):
    def test_a_new_tile_repeats_as_baked(self):
        env = dict(os.environ, KIT_BAKE_CACHE="0")
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                              os.path.join(ROOT, "kit", "selftest", "blender", "build_tile_torus.py"), "--",
                              "--no-preview"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=1800, env=env)
        self.assertEqual(out.returncode, 0, out.stdout[-1500:] + out.stderr[-1500:])
        st = json.JSONDecoder().raw_decode(out.stdout[out.stdout.find('{"schema"'):])[0]
        ts = st["facts"]["trim_sheet"]
        self.assertTrue(ts["noise_on_a_loop"])
        self.assertFalse(ts["faded"], ts["tile"])
        self.assertFalse([c for c in st["design"] if c["name"] in ("trim_fade", "tile_seam") and not c["ok"]])


if __name__ == "__main__":
    unittest.main()
