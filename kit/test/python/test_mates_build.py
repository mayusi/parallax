"""Sockets and mates through REAL builds (kit/selftest/blender/build_mates.py and its twins; his D-R04; the 3D
methods audit, stage L): a socket measured against its part's built surface, a mate held, and each way of
breaking them said by name."""

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
OUT = os.path.join("build", "_test_mates_build")


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
        cls.good = verdict("build_mates.py")
        cls.grown = verdict("build_mates_grown.py")
        cls.fat = verdict("build_mates_fat.py")
        cls.apart = verdict("build_mates_apart.py")

    def test_sockets_on_their_parts_and_the_mate_held(self):
        self.assertEqual(self.good["status"], "pass", self.good["summary"][:300])
        self.assertIn("sockets: 2 on their parts, 1 of 1 mates held", self.good["summary"])
        man = json.load(open(os.path.join(ROOT, OUT, "models", "_selftest_mates_good.manifest.json"),
                             encoding="utf-8"))
        self.assertEqual(man["sockets"]["Well"], {"part": "Body", "pos": [0.0, 1.0, 0.0],
                                                   "axis": [0.0, 1.0, 0.0], "size": 0.5})
        self.assertEqual(man["anchors"]["Well"], [0.0, 1.0, 0.0])          # (the game's Attachment)
        self.assertEqual(man["mates"][0]["fit"], [0.01, 0.05])

    def test_a_part_grown_without_its_socket_is_said_by_the_sockets_name(self):
        self.assertEqual(self.grown["status"], "fail")
        self.assertIn('Well: it lies 0.5 studs off "Body"', errors(self.grown)["mates"])
        self.assertIn("sockets: 1 OFF their parts", self.grown["summary"])

    def test_a_plug_too_wide_does_not_go_in(self):
        self.assertIn("Peg in Well: the plug (0.6 across) does not go into 0.5", errors(self.fat)["mates"])
        # (a mate that fails is not a socket off its part: the two are counted apart)
        self.assertIn("sockets: 2 on their parts, 0 of 1 mates held", self.fat["summary"])

    def test_a_plug_moved_aside_is_said_with_how_far(self):
        self.assertIn("Peg in Well: they are 0.4 studs apart", errors(self.apart)["mates"])


if __name__ == "__main__":
    unittest.main()
