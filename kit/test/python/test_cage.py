"""a.cage() (kit/blender/rbx_cage.py) — a soft-hard part by subdivision: an L-shaped (concave) outline 12 mm thick
with 1.5 mm holding loops comes out closed, close to its extrusion's volume (a little under it: the soft edges took
some off), and crisp corners keep more of it than soft ones. The fixture: kit/selftest/blender/build_cage.py."""

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
MANIFEST = os.path.join(REPO, "build", "models", "_selftest_cage.manifest.json")
EXTRUDED = (60 * 12 + 20 * 18) * 12.0   # the L's area x its depth: 12960 mm3


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Cage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.isfile(MANIFEST):
            os.remove(MANIFEST)
        script = os.path.join(REPO, "kit", "selftest", "blender", "build_cage.py")
        cls.run_ = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", "--no-preview"], cwd=REPO,
                                  capture_output=True, text=True, timeout=900)
        assert cls.run_.returncode == 0 and os.path.isfile(MANIFEST), (cls.run_.stderr or cls.run_.stdout)[-800:]
        with open(MANIFEST, encoding="utf-8") as fh:
            m = json.load(fh)
        cls.cage = {c["part"]: c for c in (m.get("design") or {}).get("cage") or m.get("facts", {}).get("cage") or []}

    def test_closed_and_near_the_extrusion(self):
        for part in ("Soft", "Crisp"):
            c = self.cage[part]
            self.assertEqual(c["open_edges"], 0, c)
            self.assertLess(c["volume_mm3"], EXTRUDED, c)                  # (soft edges took some off ...)
            self.assertGreater(c["volume_mm3"], 0.9 * EXTRUDED, c)         # (... not the shape)

    def test_crisp_corners_keep_more(self):
        self.assertGreater(self.cage["Crisp"]["volume_mm3"], self.cage["Soft"]["volume_mm3"])


if __name__ == "__main__":
    unittest.main()
