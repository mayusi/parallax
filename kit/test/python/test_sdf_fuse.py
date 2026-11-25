"""a.sdf_fuse — Blender's own distance-field nodes weld parts into ONE watertight mesh (fixture
kit/selftest/blender/build_sdf_fuse.py, run in Blender): two overlapping blocks and a bore cut through them come out as
a single part with no open edge, its volume the blocks' less the bore's."""

import json
import math
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
class Fuse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = os.path.join(REPO, "build", "models", "_selftest_sdf_fuse.check.json")
        if os.path.isfile(out):
            os.remove(out)
        script = os.path.join(REPO, "kit", "selftest", "blender", "build_sdf_fuse.py")
        subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script], cwd=REPO, capture_output=True, text=True,
                       timeout=900)
        with open(out, encoding="utf-8") as fh:
            cls.check = json.load(fh)

    def test_one_watertight_part(self):
        self.assertEqual(self.check["parts"], ["Body"])
        self.assertEqual(self.check["non_manifold"], 0)

    def test_its_volume_is_the_blocks_less_the_bore(self):
        expect = 0.6 * 0.2 * 0.6 + 0.2 * 0.2 * 0.3 - math.pi * 0.05 ** 2 * 0.5
        self.assertAlmostEqual(self.check["volume_studs3"], expect, delta=expect * 0.03)


if __name__ == "__main__":
    unittest.main()
