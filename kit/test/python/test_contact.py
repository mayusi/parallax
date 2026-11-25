"""a.contact — where use touches it: a block held by a hand over its back half and resting on the ground (fixture
kit/selftest/blender/build_contact.py, run in Blender) bakes masks that cover their share of its map, no more: the
facts say how much each kind touched."""

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
class Contact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = os.path.join(REPO, "kit", "selftest", "blender", "build_contact.py")
        subprocess.run([BLENDER, "-b", "--factory-startup", "-P", script, "--", "--no-preview"], cwd=REPO,
                       capture_output=True, text=True, timeout=900)
        with open(os.path.join(REPO, "build", "models", "_selftest_contact.manifest.json"), encoding="utf-8") as fh:
            cls.facts = json.load(fh)["facts"]

    def test_each_kind_covers_its_share(self):
        c = self.facts["contacts"]["_selftest_contact"]
        self.assertTrue(0.15 < c["hand"] < 0.6, c)     # (the back half of a block, all round: about a third of its map)
        self.assertTrue(0.05 < c["ground"] < 0.4, c)   # (the face it rests on, and a little up its sides)
        self.assertLess(c["ground"], c["hand"])


if __name__ == "__main__":
    unittest.main()
