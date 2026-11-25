"""What the placed-seams / bake-cage review left (card xxp7): a part laid along the author's seams is brought to the
rest's texel density alone - the parts without placed seams keep theirs (average_islands_scale moved them a few
percent) - and the saved mesh carries no seam flags (kit/selftest/blender/build_seam_density.py); two identical
parts stacked on one place of the map given two cages are refused (build_cage_stacked.py)."""

import json
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class Density(unittest.TestCase):
    def test_one_density_and_no_seam_flags(self):
        env = dict(os.environ, KIT_BAKE_CACHE="0")
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                              os.path.join(ROOT, "kit", "selftest", "blender", "build_seam_density.py")],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=1200, env=env)
        self.assertEqual(out.returncode, 0, out.stdout[-1500:] + out.stderr[-1500:])
        i = out.stdout.rfind("DENS ")
        got = json.JSONDecoder().raw_decode(out.stdout[i + 5:])[0]
        d = got["density"]
        self.assertAlmostEqual(d["Handle"] / d["Block"], 1.0, delta=0.03, msg=d)
        self.assertEqual(got["seam_edges"], 0)


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class Stacked(unittest.TestCase):
    def test_two_cages_on_one_place_of_the_map_are_refused(self):
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                              os.path.join(ROOT, "kit", "selftest", "blender", "build_cage_stacked.py")],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("lie on one place of the map", out.stdout + out.stderr)
        self.assertIn("different cages", out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
