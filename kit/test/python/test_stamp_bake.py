"""a.stamp in the bake (AAA-5): the fixture kit/selftest/blender/build_stamp.py — a flat plate with stamps, and the
same plate without (--control) — baked in Blender: the stamped normal map leans away from flat over clearly more
texels than the control's, the facts count the stamps, and a stamp inside a.mirror is refused. (2026-10-18: a
colour-space reset regenerated every stamp image blank; only a bake test sees that.)"""

import json
import os
import subprocess
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()
# where the bake writes: rbx.py's BUILD (KIT_BUILD - the active game's build folder when one is active, else "build")
MODELS = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "models")


def _bake(control):
    name = "_selftest_stamp_ctl" if control else "_selftest_stamp"
    for f in (f"{name}.manifest.json", os.path.join("textures", f"{name}_normal.png"),
              os.path.join("textures", f"{name}_color.png"), "_selftest_stamp.mirror.json"):
        if os.path.isfile(os.path.join(MODELS, f)) and (control is False or not f.startswith("_selftest_stamp.mirror")):
            os.remove(os.path.join(MODELS, f))   # (a stale file from an earlier run must never pass this test)
    script = os.path.join(REPO, "kit", "selftest", "blender", "build_stamp.py")
    args = [BLENDER, "-b", "--factory-startup", "-P", script, "--", "--no-preview"] + (["--control"] if control else [])
    run = subprocess.run(args, cwd=REPO, capture_output=True, text=True, timeout=900)
    return name, run


def _bent(png):
    from PIL import Image  # noqa: PLC0415

    n = np.asarray(Image.open(png).convert("RGB"), np.float32) / 255.0
    return float(((np.abs(n[..., 0] - 0.5) + np.abs(n[..., 1] - 0.5)) > 0.08).mean())


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class StampBake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {}
        for control in (False, True):
            name, run = _bake(control)
            cls.runs[control] = (name, run)

    def _ok(self, control):
        name, run = self.runs[control]
        self.assertEqual(run.returncode, 0, (run.stderr or run.stdout)[-800:])
        return name

    def test_stamps_bend_the_normal_map(self):
        s, c = self._ok(False), self._ok(True)
        bent_s = _bent(os.path.join(MODELS, "textures", f"{s}_normal.png"))
        bent_c = _bent(os.path.join(MODELS, "textures", f"{c}_normal.png"))
        self.assertGreater(bent_s, bent_c + 0.003, (bent_s, bent_c))   # (5 rivets + a panel line: well above flat)

    def test_facts_count_the_stamps(self):
        s = self._ok(False)
        with open(os.path.join(MODELS, f"{s}.manifest.json"), encoding="utf-8") as fh:
            facts = json.load(fh)["facts"]
        self.assertEqual(facts.get("stamps"), {"panel_line": 1, "rivets": 1})

    def test_recesses_darken_the_colour(self):
        from PIL import Image  # noqa: PLC0415

        s, c = self._ok(False), self._ok(True)
        lum = [np.asarray(Image.open(os.path.join(MODELS, "textures", f"{n}_color.png")).convert("L"), np.float32)
               for n in (s, c)]
        darker = float(((lum[1] - lum[0]) > 12).mean())   # (the same plate, the same UVs: texel for texel)
        self.assertGreater(darker, 0.001, darker)          # (the panel line's groove, dark like AO)

    def test_a_stamp_too_fine_for_its_map_is_named(self):
        s = self._ok(False)
        with open(os.path.join(MODELS, f"{s}.manifest.json"), encoding="utf-8") as fh:
            fine = json.load(fh)["facts"].get("stamps_too_fine")
        self.assertTrue(fine and any(f.startswith("panel_line") for f in fine), fine)   # (3 mm on a 256 map)
        self.assertFalse(any(f.startswith("rivets") for f in fine), fine)               # (10 mm domes read)

    def test_stamp_inside_a_mirror_is_refused(self):
        self._ok(False)
        with open(os.path.join(MODELS, "_selftest_stamp.mirror.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["stamp_in_mirror"], "refused")


if __name__ == "__main__":
    unittest.main()
