"""A large opening a repair caps (card b7qe: "an open bowl, a cup or a lampshade is capped into a solid when asked" -
the rim alone cannot tell a tray from a box missing its lid): a shallow tray listed without its top
(kit/selftest/blender/build_repair_bowl.py, its opening 71% of its surface). a.repair caps it as asked and the
build WARNS repair_large_cap; named open with a.open_way it is left open, and - a wall with no thickness - given its
back by a.two_sided (the build's own advice), the build passes."""

import json
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def build(*args):
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                          os.path.join(ROOT, "kit", "selftest", "blender", "build_repair_bowl.py"), "--", *args],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200)
    k = out.stdout.find('{"schema"')
    return out.returncode, (json.JSONDecoder().raw_decode(out.stdout[k:])[0] if k >= 0 else None), \
        out.stdout[-1500:] + out.stderr[-1500:]


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class Tray(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.capped, cls.kept = build(), build("kept")

    def test_capped_as_asked_and_warned(self):
        code, st, log = self.capped
        self.assertEqual(code, 0, log)
        row = st["facts"]["repaired"][0]
        self.assertEqual(row["capped"], 1)
        self.assertGreater(row["large_capped"][0]["share"], 0.25)
        warn = [c for c in st["design"] if c["name"] == "repair_large_cap"]
        self.assertTrue(warn and not warn[0]["ok"] and warn[0]["severity"] == "warn", warn)
        self.assertIn("a.open_way", warn[0]["fix"])

    def test_named_open_it_stays_open_and_passes_given_its_back(self):
        code, st, log = self.kept
        self.assertEqual(code, 0, log)
        row = st["facts"]["repaired"][0]
        self.assertEqual((row["capped"], row["kept"]), (0, ["Top"]))
        self.assertFalse([c for c in st["design"] if c["name"] == "repair_large_cap"])
        self.assertEqual(st["status"], "pass", st["summary"])


if __name__ == "__main__":
    unittest.main()
