"""a.seams on a GENERATED mesh (kit/selftest/blender/build_seam_generated.py; the 3D methods audit's last PARTLY of
seam placement): the generator-like ball is laid along the cut placed on it - seam_placed passes, where it used to
keep the generator's layout and fail - and its paint is baked across from the generator's own layout: every face
away from the cut keeps its side's colour."""

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
class SeamGenerated(unittest.TestCase):
    HOW = "alone"

    @classmethod
    def setUpClass(cls):
        script = os.path.join(REPO, "kit", "selftest", "blender", "build_seam_generated.py")
        env = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join(REPO, "build", "_test_seam_generated"))
        run = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "--python", script,
                              "--", cls.HOW], cwd=REPO, capture_output=True, text=True, timeout=1500, env=env)
        out = run.stdout.splitlines()
        line = next((ln for ln in out if ln.startswith("SEAMGEN ")), None)
        assert line, (run.stderr or run.stdout)[-1500:]
        cls.out = json.loads(line[len("SEAMGEN "):])
        # (raw_decode: Blender's own words can follow the verdict on its line)
        cls.verdict = next((json.JSONDecoder().raw_decode(ln)[0] for ln in reversed(out)
                            if ln.startswith("{") and '"schema"' in ln), {})

    def test_the_build_lays_the_generated_part_along_its_cut(self):
        self.assertEqual(self.verdict.get("status"), "pass", self.verdict.get("summary"))
        self.assertIn("placed seams: Ball", self.verdict.get("summary", ""))
        self.assertNotIn("seam_placed", self.verdict.get("summary", "").split("(")[0])

    def test_its_paint_is_carried_onto_the_new_layout(self):
        self.assertGreater(self.out["faces"], 300, self.out)
        self.assertEqual(self.out["wrong_colour"], 0, self.out)


class SeamGeneratedJoined(SeamGenerated):
    """the same ball joined with a kit-made block in ONE group (the automatic unwrap): laid and painted all the same"""
    HOW = "mixed"


if __name__ == "__main__":
    unittest.main()
