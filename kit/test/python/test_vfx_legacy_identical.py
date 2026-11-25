"""kit vfx migrate --identical (kit/vfx/legacy.py; LIMITATIONS_FIXES_V4 3.4 step 4, the preset warnings burned only
where the meaning is identical). What is proven: the mode drops ONLY keys nothing reads (a shake's frequency, a
sprite's spreadAngle beside its spread, a fov layer's fov beside its delta) and never renames a key or turns a card
upright (those change a judged look); the rest of the file is byte-for-byte the same; and the claim it rests on -
neither the stage nor the browser player reads those keys - is held to their source: the day one starts reading
`frequency` or `spreadAngle`, this fails and the mode stops being identical.
Run: python -m pytest kit/test/python/test_vfx_legacy_identical.py -q"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import legacy as L  # noqa: E402

PRESET = """{
 "version": 3,
 "layers": [
  {"name": "s1", "kind": "shake", "amplitude": 2, "frequency": 30, "life": 0.4},
  {"name": "s2", "kind": "sprite", "spread": 20, "spreadAngle": 45, "size": 2},
  {"name": "s3", "kind": "sprite", "spreadAngle": 45, "size": 2},
  {"name": "f1", "kind": "fov", "delta": -8, "fov": -6},
  {"name": "f2", "kind": "fov", "fov": -6},
  {"name": "card", "kind": "sprite", "size": 60, "point": [0, 0, 0]}
 ]
}
"""


class Identical(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        with open(os.path.join(self.tmp, "p.json"), "w", encoding="utf-8", newline="") as fh:
            fh.write(PRESET)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_drops_only_unread_keys(self):
        self.assertEqual(L.main(["--effects", self.tmp, "--identical"]), 0)
        text = open(os.path.join(self.tmp, "p.json"), encoding="utf-8", newline="").read()
        got = json.loads(text)["layers"]
        self.assertNotIn("frequency", got[0])
        self.assertNotIn("spreadAngle", got[1])
        self.assertEqual(got[2].get("spreadAngle"), 45)          # a rename changes the look: left
        self.assertNotIn("spread", got[2])
        self.assertNotIn("fov", got[3])
        self.assertEqual(got[4].get("fov"), -6)                  # likewise
        self.assertNotIn("delta", got[4])
        self.assertNotIn("orientation", got[5])                  # the card is not turned
        # nothing else in the file changed: removing the three pairs from the original gives the new text
        want = PRESET.replace(', "frequency": 30', "").replace(', "spreadAngle": 45, "size": 2}', ', "size": 2}', 1) \
                     .replace(', "fov": -6}', "}", 1)
        self.assertEqual(text, want)
        left = L.hits(json.loads(text))
        self.assertEqual(sorted(h["key"] for h in left), ["fov", "orientation", "spreadAngle"])

    def test_nothing_reads_the_dropped_keys(self):
        stage = open(os.path.join(ROOT, "src", "kit", "VfxStage.luau"), encoding="utf-8").read()
        player = open(os.path.join(ROOT, "kit", "vfx", "player", "player.js"), encoding="utf-8").read()
        for src in (stage, player):
            self.assertIsNone(re.search(r"\bfrequency\b", src))
            self.assertIsNone(re.search(r"\bspreadAngle\b", src))
        self.assertIsNone(re.search(r"\bel\.fov\b", stage))
        self.assertIsNone(re.search(r"\bel\.fov\b", player))
        self.assertIn("numAt(el.delta", player)                   # the fov layer plays its delta


if __name__ == "__main__":
    unittest.main()
