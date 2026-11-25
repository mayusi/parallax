"""THE FADES A GAME PLAYS through REAL builds (rbx_cycleplay.fades; kit/selftest/blender/build_cycle_fade.py and
build_cycle_loop.py): a fade from rest that drives a part in fails the build - the cycle itself clear; a fade
between two cycles that would is said by name (the build cannot know the game plays it)."""

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


def build(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_cycle_fade"))
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"], cwd=ROOT,
                       capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8", errors="replace")
    return json.loads(next(x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x))


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fade = build("build_cycle_fade.py")
        cls.loop = build("build_cycle_loop.py")

    def test_a_fade_from_rest_that_drives_a_part_in_fails_and_the_cycle_itself_is_clear(self):
        v = self.fade
        self.assertNotEqual(v["status"], "pass")
        self.assertIn("design.cycle_fade=", v["summary"])
        self.assertIn("from rest into Hold", v["summary"])
        self.assertNotIn("mechanism_cycle=", v["summary"])                 # (the cycle never takes that pose)
        self.assertEqual(v["facts"]["cycle"]["fades"]["from_rest"], 1)

    def test_a_fade_between_two_cycles_that_would_is_said_by_name_and_never_fails(self):
        v = self.loop
        self.assertEqual(v["status"], "pass", v["summary"][:400])
        self.assertGreaterEqual(v["facts"]["cycle"]["fades"]["between"], 1)
        self.assertEqual(v["facts"]["cycle"]["fades"]["from_rest"], 0)
        self.assertIn("cycle_fade_between", v["summary"])                  # (the warning, named in the summary)


if __name__ == "__main__":
    unittest.main()
