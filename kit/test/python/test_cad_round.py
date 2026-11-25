"""a.cad(..., round_mm=) — every real edge of a CAD part rounded on the mesh (Scarborough Fair 2026-10-22: no fillet
took on its traced outlines, every edge stayed knife-sharp; the owner, "guns ... are all smoothen out"). The fixture
kit/selftest/blender/build_cad_round.py builds one slab sharp and rounded: the facts carry round_mm on the rounded one
only, and the bevelled mesh stays closed (no open edges)."""

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
MANIFEST = os.path.join(REPO, "build", "models", "_selftest_cad_round.manifest.json")


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class CadRound(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.isfile(MANIFEST):
            os.remove(MANIFEST)
        script = os.path.join(REPO, "kit", "selftest", "blender", "build_cad_round.py")
        cls.run_ = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", "--no-preview"], cwd=REPO,
                                  capture_output=True, text=True, timeout=900)
        assert cls.run_.returncode == 0 and os.path.isfile(MANIFEST), (cls.run_.stderr or cls.run_.stdout)[-800:]
        with open(MANIFEST, encoding="utf-8") as fh:
            m = json.load(fh)
        cls.cad = {c["part"]: c for c in (m.get("design") or {}).get("cad") or m.get("facts", {}).get("cad") or []}

    def test_round_mm_is_recorded(self):
        self.assertEqual(self.cad["Round"].get("round_mm"), 2.0, self.cad["Round"])
        self.assertNotIn("round_mm", self.cad["Sharp"])

    def test_the_rounded_part_stays_closed(self):
        self.assertEqual(self.cad["Round"].get("open_edges"), 0)


if __name__ == "__main__":
    unittest.main()
