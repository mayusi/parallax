"""An action cycle checked by how far its parts move, through REAL builds (kit/selftest/blender/
build_cycle_fast_pin.py and _clear.py; his D-R05, the rest; the 3D methods audit, stage L): a wheel that swings its
lug half round in two frames, through a pin that is only in the way while both move together."""

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
OUT = os.path.join("build", "_test_cycle_fast_build")


def verdict(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)   # (strict: the kit reads this line the same way)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pin = verdict("build_cycle_fast_pin.py")
        cls.clear = verdict("build_cycle_fast_clear.py")

    def test_a_pin_met_between_two_frames_is_caught_and_only_by_the_cycle(self):
        self.assertEqual(self.pin["status"], "fail")
        bad = {c["name"]: c["fix"] for c in self.pin["design"] if c["severity"] == "error"}
        self.assertIn("mechanism_cycle", bad)
        self.assertIn("'pin' drives into 'wheel'", bad["mechanism_cycle"])
        self.assertNotIn("mechanism", bad)                    # each joint alone is clear: only together they meet
        self.assertGreater(self.pin["facts"]["cycle"]["sampled"], 20)   # (the old check looked at 2 frames)
        self.assertLessEqual(self.pin["facts"]["cycle"]["gap"], 0.05)

    def test_the_same_swing_with_the_pin_held_up_is_clear(self):
        self.assertEqual(self.clear["status"], "pass", self.clear["summary"][:300])
        self.assertEqual(self.clear["facts"]["cycle"]["collisions"], 0)
        self.assertNotIn("coarse", self.clear["facts"]["cycle"])


if __name__ == "__main__":
    unittest.main()
