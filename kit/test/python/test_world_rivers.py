"""kit world rivers: water in the carved valleys - the biggest drainage of the stored heights, painted as "river"."""

import json
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "world"))
import rivers  # noqa: E402


def valley(n=40):
    """a V-valley running down +z: the floor at x = n/2, sloping toward z = n"""
    x = np.arange(n)[:, None]
    z = np.arange(n)[None, :]
    return (np.abs(x - n // 2) * 2.0 + (n - z) * 0.5).astype(float)


def write(h, paint_role=0, roles=("meadow", "lush", "dirt", "mud", "rock", "cliff", "snow", "sand", "scree")):
    nx, nz = h.shape
    hm = {"nx": nx, "nz": nz, "step": 4.0, "heights": h.ravel().tolist(), "roles": list(roles),
          "paint": str(paint_role) * (nx * nz)}
    fd, path = tempfile.mkstemp(suffix=".hm.json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(hm, fh)
    return path


class Rivers(unittest.TestCase):
    def test_the_water_runs_down_the_valley_floor(self):
        path = write(valley())
        self.assertEqual(rivers.main([path, "--share", "0.03", "--out", path + ".png"]), 0)
        hm = json.load(open(path, encoding="utf-8"))
        self.assertEqual(hm["roles"][-1], "river")
        paint = np.array([int(c) for c in hm["paint"]]).reshape(hm["nx"], hm["nz"])
        xs, zs = np.nonzero(paint == len(hm["roles"]) - 1)
        self.assertGreater(len(xs), 8)
        self.assertTrue(np.all(np.abs(xs - 20) <= 2))  # (on the floor, not up the sides)
        self.assertEqual(hm["heights"], valley().ravel().tolist())  # (heights untouched)

    def test_running_again_keeps_one_river_role_and_the_same_cells(self):
        path = write(valley())
        rivers.main([path, "--share", "0.03", "--out", path + ".png"])
        first = json.load(open(path, encoding="utf-8"))
        rivers.main([path, "--share", "0.03", "--out", path + ".png"])
        again = json.load(open(path, encoding="utf-8"))
        self.assertEqual(again["roles"].count("river"), 1)
        river = str(len(again["roles"]) - 1)
        self.assertEqual(first["paint"].count(river), again["paint"].count(river))

    def test_an_unpainted_heightmap_is_refused(self):
        fd, path = tempfile.mkstemp(suffix=".hm.json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"nx": 4, "nz": 4, "heights": [0] * 16}, fh)
        self.assertEqual(rivers.main([path]), 1)


if __name__ == "__main__":
    unittest.main()
