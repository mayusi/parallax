"""A repair steered by a named opening, through REAL builds (kit/selftest/blender/build_repair_named.py and its
twin; his D-R12, the rest; the 3D methods audit, stage L): a bin whose mouth is named stays open through a.repair
and through the build's own closing step, and its tear is still capped."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join("build", "_test_repair_named_build")


def verdict(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)   # (strict: the kit reads this line the same way)


def errors(v):
    return {c["name"]: str(c.get("value")) for c in v["design"] if c["severity"] == "error"}


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = verdict("build_repair_named.py")
        cls.thin = verdict("build_repair_named_thin.py")

    def test_the_tear_is_capped_and_the_named_mouth_left_open(self):
        self.assertEqual(self.good["status"], "pass", self.good["summary"][:300])
        self.assertIn("repaired: Bin (1 hole capped, left open as named: Mouth)", self.good["summary"])
        self.assertIn("openings: 1 open", self.good["summary"])
        self.assertNotIn("filled by the build", self.good["summary"])

    def test_a_named_mouth_in_a_sheet_is_never_filled_and_the_sheet_is_said(self):
        self.assertEqual(self.thin["status"], "fail")
        bad = errors(self.thin)
        self.assertIn("openings", bad)
        self.assertIn("left open as named: Mouth", bad["openings"])
        self.assertIn("a.two_sided", bad["openings"])
        self.assertNotIn("open_ways", bad)                    # (it used to be capped, then failed as closed)
        self.assertNotIn("filled by the build", self.thin["summary"])


if __name__ == "__main__":
    unittest.main()
