"""rbx.calm_normals (the high-and-low route's baked normal map): a texel tilted past LOW_NORMAL_Z_MIN is a bake ray that
fell past the low's edge (the car rim's valve hole: one texel at z 0.04 glinted below the hole, rework 6ebz) and takes
its neighbours' mean; a steep but real tilt (60 degrees) and every other texel stay as baked. Run in Blender (rbx
imports bpy)."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()

CHECK = r'''
import json, math, sys
import numpy as np
sys.path.insert(0, r"%s")
import rbx
m = np.zeros((16, 16, 4), np.float32)
m[..., :] = (0.5, 0.5, 1.0, 1.0)                       # flat
t = math.radians(20)
m[4:12, 4:12, :3] = (0.5 + 0.5 * math.sin(t), 0.5, 0.5 + 0.5 * math.cos(t))   # a real 20-degree slope
m[7, 7, :3] = (0.5 - 0.5 * 0.40, 0.5 - 0.5 * 0.91, 0.5 + 0.5 * 0.04)         # the valve hole's texel: z 0.04
m[0, 0, :3] = (0.5, 0.0, 0.5)                                                  # a corner texel lying flat (z 0)
s = math.radians(60)
m[14, 3, :3] = (0.5 + 0.5 * math.sin(s), 0.5, 0.5 + 0.5 * math.cos(s))       # a steep real tilt: z 0.5, kept
out, n = rbx.calm_normals(m.copy(), rbx.LOW_NORMAL_Z_MIN)
v = out[..., :3] * 2 - 1
changed = np.argwhere(np.abs(out - m).max(axis=2) > 1e-6).tolist()
print("CALM " + json.dumps({"n": n, "changed": changed, "mid": v[7, 7].tolist(), "corner": v[0, 0].tolist(),
                            "steep": v[14, 3].tolist(), "z_min": rbx.LOW_NORMAL_Z_MIN}))
''' % os.path.join(REPO, "kit", "blender").replace("\\", "/")


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class CalmNormals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        run = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-expr", CHECK], cwd=REPO,
                             capture_output=True, text=True, timeout=300)
        line = next((ln for ln in run.stdout.splitlines() if ln.startswith("CALM ")), None)
        assert line, (run.stderr or run.stdout)[-800:]
        cls.out = json.loads(line[len("CALM "):])

    def test_only_the_two_fallen_texels_change(self):
        self.assertEqual(self.out["n"], 2)
        self.assertEqual(sorted(self.out["changed"]), [[0, 0], [7, 7]])

    def test_a_texel_inside_a_slope_takes_the_slope(self):
        x, y, z = self.out["mid"]
        self.assertAlmostEqual(z, 0.9397, places=3)   # (cos 20 degrees: its eight neighbours' tilt)
        self.assertAlmostEqual(y, 0.0, places=3)

    def test_a_corner_texel_goes_flat_and_steep_real_tilt_stays(self):
        self.assertGreater(self.out["corner"][2], 0.999)
        self.assertAlmostEqual(self.out["steep"][2], 0.5, places=2)


if __name__ == "__main__":
    unittest.main()
