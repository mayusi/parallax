"""What the topology stage's review left (card fw6p): a.drop_flat takes out the vertices that shape nothing (a box
built of a grid comes back a box); a.shade with a NUMBER is held edge by edge (rbx._angle_held: a sharper edge
shaded round or a gentler one split is counted); a.drop_hidden's eyes include a ring 4 degrees off the face (a face
seen only at a glance is kept); a group that hides 10% or more of its triangles is told what a.drop_hidden takes."""

import json
import os
import subprocess
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_topology as T  # noqa: E402

BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def run(script):
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                          os.path.join(ROOT, "kit", "selftest", "blender", script)],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200)
    k = out.stdout.find('{"schema"')
    return out, (json.JSONDecoder().raw_decode(out.stdout[k:])[0] if k >= 0 else None)


class Eyes(unittest.TestCase):
    def test_a_grazing_ring(self):
        n = np.array([0, 0, 1.0])
        d = T.directions(n, 24, grazing=8)
        self.assertEqual(len(d), 32)
        low = d[24:] @ n
        self.assertTrue(np.allclose(low, np.sin(np.radians(4.0))))
        self.assertGreater(float((d[:24] @ n).min()), 0.16)
        self.assertEqual(len(T.directions(n, 24)), 24)   # (the never-seen measure: as before)


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class InBlender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.flat = run("build_drop_flat.py")
        cls.shade = run("probe_shade_angle.py")

    def test_drop_flat_makes_the_grid_a_box(self):
        out, st = self.flat
        self.assertEqual(out.returncode, 0, out.stdout[-1500:] + out.stderr[-1500:])
        row = st["facts"]["flat_dropped"][0]
        self.assertEqual((row["part"], row["tris_before"], row["tris_after"]), ("Block", 1728, 12))
        self.assertEqual(st["status"], "pass", st["summary"])

    def test_the_never_seen_hint(self):
        _out, st = self.flat
        self.assertIn("never seen:", st["summary"])
        self.assertIn("a.drop_hidden() takes them out", st["summary"])

    def test_a_number_is_held_edge_by_edge(self):
        out, st = self.shade
        self.assertEqual(out.returncode, 0, out.stdout[-1500:] + out.stderr[-1500:])
        i = out.stdout.rfind("SHADE ")
        got = json.JSONDecoder().raw_decode(out.stdout[i + 6:])[0]
        self.assertGreater(got["smooth_all"]["wrong"], 0)          # (its caps shaded round: not held)
        self.assertEqual(got["by_angle"]["wrong"], 0)
        drum = st["facts"]["topology"]["main"]["shading"]["Drum"]
        self.assertEqual((drum["asked"], drum["wrong"]), (45, 0))
        self.assertGreater(drum["judged"], 0)


if __name__ == "__main__":
    unittest.main()
