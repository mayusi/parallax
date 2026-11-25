"""kit world refs: stills measured by script (horizon, values, haze, palette) and a render compared -> one edit."""

import json
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "world"))
import refs  # noqa: E402


def still(folder, name, horizon=0.4, hazy=True, seed=0, sky=(0.62, 0.70, 0.82)):
    """a smooth sky above `horizon`, textured land below: far land pale + desaturated when hazy, near land vivid"""
    from PIL import Image

    rng = np.random.default_rng(seed)
    h, w = 300, 480
    a = np.zeros((h, w, 3))
    r = int(horizon * h)
    a[:r] = np.array(sky) + np.linspace(0, 0.05, r)[:, None, None]
    near, far = np.array([0.20, 0.42, 0.12]), (np.array([0.50, 0.58, 0.60]) if hazy else np.array([0.20, 0.42, 0.12]))
    for y in range(r, h):
        t = (y - r) / max(h - r - 1, 1)
        base = far * (1 - t) + near * t
        a[y] = base + rng.normal(0, 0.06, (w, 3))
    path = os.path.join(folder, name)
    Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)).save(path)
    return path


class TestRefs(unittest.TestCase):
    def test_the_horizon_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            for hz in (0.3, 0.45, 0.6):
                m = refs.measure(still(d, f"s{hz}.png", horizon=hz))
                self.assertAlmostEqual(m["horizon_pct"], hz * 100, delta=4.0)

    def test_haze_reads_aerial_perspective(self):
        with tempfile.TemporaryDirectory() as d:
            hazy = refs.measure(still(d, "a.png", hazy=True))
            clear = refs.measure(still(d, "b.png", hazy=False))
            self.assertGreater(hazy["haze"], clear["haze"] + 0.2)

    def test_identity_and_one_edit(self):
        with tempfile.TemporaryDirectory() as d:
            refs_dir = os.path.join(d, "W")
            os.makedirs(refs_dir)
            for i in range(6):
                still(refs_dir, f"r{i}.png", horizon=0.40 + 0.01 * i, seed=i)
            ident_path = os.path.join(d, "w.json")
            self.assertEqual(refs.main([refs_dir, ident_path, "--name", "W"]), 0)
            ident = json.load(open(ident_path, encoding="utf-8"))
            self.assertAlmostEqual(ident["horizon_pct"], 42.5, delta=4.0)
            self.assertTrue(os.path.isfile(os.path.join(refs_dir, "REFS.md")))
            render = still(d, "render.png", horizon=0.70, seed=9)  # far too little sky
            m, diffs = refs.compare(render, ident)
            self.assertTrue(diffs)
            self.assertEqual(diffs[0][1], "horizon")
            self.assertIn("raise the camera", diffs[0][3])

    def test_too_few_stills_is_not_an_identity(self):
        with tempfile.TemporaryDirectory() as d:
            refs_dir = os.path.join(d, "W")
            os.makedirs(refs_dir)
            still(refs_dir, "only.png")
            self.assertEqual(refs.main([refs_dir, os.path.join(d, "w.json")]), 1)


if __name__ == "__main__":
    unittest.main()
