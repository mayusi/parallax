"""REAL-SCALE patterns, measured back: a.material(pattern="checkering" | "stipple", pattern_mm=<pitch>) is baked at the
group's measured texture density, and the kit's own dissector (kit library inspect -> baked_detail) reads the pitch
off the exported normal map. 20 lines per inch (1.27 mm) checkering must come back as 1.27 mm, 1 mm stippling as 1 mm
— the sculpt a real grip carries, at its real size."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

KIT = os.path.abspath(os.path.join(HERE, "..", ".."))
BLENDER = cad_check.blender()

BUILD = r'''
import os, sys
sys.path.insert(0, os.path.join(sys.argv[sys.argv.index("--") + 1], "blender"))
import rbx
kind, pitch = sys.argv[sys.argv.index("--") + 2], float(sys.argv[sys.argv.index("--") + 3])
a = rbx.Asset(f"_test_pattern_{kind}", tex=1024, size=(0.4, 0.05, 0.4))
a.real_scale(100.0)  # 1 stud = 100 mm: a 40 x 40 mm plate
a.material("grip", color=(0.35, 0.2, 0.1), rough=0.6, pattern=kind, pattern_mm=pitch)
a.box("Plate", (0.40, 0.05, 0.40), (0, 0, 0), "grip", bevel=0.005)
a.build()
'''


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class TestRealScalePatterns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        script = os.path.join(cls.tmp, "build.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(BUILD)
        env = dict(os.environ, KIT_BUILD=cls.tmp)
        cls.pitch = {}
        for kind, pitch in (("checkering", 1.27), ("stipple", 1.0)):
            subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", KIT,
                            kind, str(pitch), "--no-preview"], check=True, capture_output=True, timeout=600, env=env)
            blend = os.path.join(cls.tmp, "models", f"_test_pattern_{kind}.blend")
            subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(KIT, "refs", "inspect_model.py"), "--", blend, "--name", kind, "--out", cls.tmp,
                            "--length-mm", "40", "--px", "64"], check=True, capture_output=True, timeout=600, env=env)
            with open(os.path.join(cls.tmp, f"{kind}.inspect.json"), encoding="utf-8") as fh:
                part = json.load(fh)["parts"][0]
            cls.pitch[kind] = (part.get("baked_detail") or {}).get("pattern") or {}

    def test_checkering_at_20_lines_per_inch(self):
        p = self.pitch["checkering"]
        self.assertTrue(p.get("found"), p)
        self.assertAlmostEqual(p["pitch_mm"], 1.27, delta=0.064)  # within 5%

    def test_stippling_at_1_mm(self):
        p = self.pitch["stipple"]
        self.assertTrue(p.get("found"), p)
        self.assertAlmostEqual(p["pitch_mm"], 1.0, delta=0.05)


if __name__ == "__main__":
    unittest.main()
