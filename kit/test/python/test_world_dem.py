"""kit world dem: real land as a terrain design's base — slopes kept TRUE (metres per stud the same both ways)."""

import json
import math
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "world"))
import dem  # noqa: E402
import terrain  # noqa: E402


def write_dem(folder, a, width_m):
    from PIL import Image

    path = os.path.join(folder, "t.dem.tif")
    Image.fromarray(a.astype(np.float32), mode="F").save(path)
    with open(dem.sidecar(path), "w", encoding="utf-8") as fh:
        json.dump({"width_m": width_m, "height_m": width_m}, fh)
    return path


class TestDem(unittest.TestCase):
    def test_box_metres(self):
        w, h = dem.box_metres(0, 0, 1, 1)  # a degree at the equator ~ 111 km both ways
        self.assertAlmostEqual(w / 1000, 111.2, delta=0.5)
        self.assertAlmostEqual(h / 1000, 111.2, delta=0.5)
        w60, _ = dem.box_metres(0, 59.5, 1, 60.5)  # at 60 deg a degree of longitude is half
        self.assertAlmostEqual(w60 / w, math.cos(math.radians(60)), delta=0.01)

    def test_a_real_slope_stays_true(self):
        # a 1 km wide tilted plane rising 100 m west -> east: a 1024-stud map makes 1 stud = 0.977 m both ways,
        # so the rise in studs = 100 / 0.977 ~ 102.4 and the slope angle is the real one (5.7 deg)
        with tempfile.TemporaryDirectory() as d:
            ramp = np.tile(np.linspace(1000, 1100, 64), (64, 1))  # image x = east
            path = write_dem(d, ramp, 1000.0)
            h = terrain.dem_base(65, 1024, {"file": path, "blur": 0}, d)
            self.assertAlmostEqual(h.max() - h.min(), 100 / (1000 / 1024), delta=2.0)
            self.assertLess(h[0, 32], h[-1, 32])  # the grid's x follows the image's x (east)

    def test_vexag_and_relief(self):
        with tempfile.TemporaryDirectory() as d:
            ramp = np.tile(np.linspace(0, 50, 32), (32, 1))
            path = write_dem(d, ramp, 512.0)
            flat = terrain.dem_base(33, 512, {"file": path, "blur": 0}, d)
            twice = terrain.dem_base(33, 512, {"file": path, "blur": 0, "vexag": 2}, d)
            self.assertAlmostEqual(twice.max(), 2 * flat.max(), delta=0.5)
            fixed = terrain.dem_base(33, 512, {"file": path, "blur": 0, "relief": 80}, d)
            self.assertAlmostEqual(fixed.max(), 80.0, delta=0.01)

    def test_a_missing_dem_is_named(self):
        with self.assertRaises(ValueError):
            terrain.dem_base(33, 512, {"file": "nope.dem.tif"}, tempfile.gettempdir())

    def test_blur_keeps_the_mean(self):
        a = np.zeros((20, 20))
        a[10, 10] = 100.0
        b = terrain.blur(a, 1.5)
        self.assertAlmostEqual(a.sum(), b.sum(), delta=1e-6)
        self.assertLess(b.max(), 100.0)


if __name__ == "__main__":
    unittest.main()
