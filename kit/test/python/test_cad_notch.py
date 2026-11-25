"""a.cad(..., round_mm=) rounds each edge LOCALLY (kit/blender/rbx_round.py): a slab with one 1 mm notch keeps its full
2 mm round on almost every edge, narrower only at the notch — Blender's clamp_overlap used to shrink the WHOLE round
to the notch's 0.45 mm (every traced Scarborough Fair part read sharper than the art). Fixture:
kit/selftest/blender/build_cad_notch.py."""

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
MANIFEST = os.path.join(REPO, "build", "models", "_selftest_cad_notch.manifest.json")


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class CadNotch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.isfile(MANIFEST):
            os.remove(MANIFEST)
        script = os.path.join(REPO, "kit", "selftest", "blender", "build_cad_notch.py")
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", "--no-preview"], cwd=REPO,
                           capture_output=True, text=True, timeout=900)
        assert r.returncode == 0 and os.path.isfile(MANIFEST), (r.stderr or r.stdout)[-800:]
        with open(MANIFEST, encoding="utf-8") as fh:
            m = json.load(fh)
        cls.c = next(c for c in m["facts"]["cad"] if c["part"] == "Notched")

    def test_the_full_round_everywhere_but_the_notch(self):
        built = {p[0]: p[2] for p in self.c["round_built"]}
        full = built.get(2.0, 0.0)
        self.assertGreaterEqual(full / sum(built.values()), 0.8, built)   # (most of the edges' length: the full 2 mm)
        self.assertLess(min(built), 2.0, built)                              # (the notch's: narrower)
        widest = max(self.c["round_built"], key=lambda p: p[0])
        self.assertNotIn("clamped", widest, self.c["round_built"])          # (a clamped widest pass = the collapse)

    def test_closed(self):
        self.assertEqual(self.c["open_edges"], 0)


if __name__ == "__main__":
    unittest.main()
