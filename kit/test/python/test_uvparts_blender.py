"""UVs by part in Blender (kit/blender/rbx_uvparts.py, the bmesh pieces): triangulate_like cuts a turned copy's n-gon
along its original's diagonals - the fixture (kit/selftest/blender/check_triangulate_like.py) is a hexagon and its
copy started at each of its six corners; BEAUTY alone must cut at least one otherwise (the fixture still shows the
fault: the car rim's Spoke2, rework 6ebz), triangulate_like none."""

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


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class TriangulateLike(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = os.path.join(REPO, "kit", "selftest", "blender", "check_triangulate_like.py")
        run = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", script], cwd=REPO, capture_output=True,
                             text=True, timeout=300)
        line = next((ln for ln in run.stdout.splitlines() if ln.startswith("TRI_LIKE ")), None)
        assert line, (run.stderr or run.stdout)[-800:]
        cls.out = json.loads(line[len("TRI_LIKE "):])

    def test_found_as_copies(self):
        self.assertEqual(self.out["copies"], [{"1": 0}] * 6)

    def test_beauty_alone_cuts_some_otherwise(self):
        self.assertFalse(all(self.out["beauty_alike"]), self.out)

    def test_cut_like_the_original_every_start(self):
        self.assertEqual(self.out["like_alike"], [True] * 6, self.out)
        self.assertEqual(self.out["failed"], [[]] * 6, self.out)
        self.assertEqual(self.out["faces"], [8] * 6, self.out)   # (4 triangles a hexagon, both)


if __name__ == "__main__":
    unittest.main()
