"""A model's own motion through REAL builds (kit/selftest/blender/build_cycle_loop.py and its jumping twin; the 3D
methods audit, G3): the manifest carries each action cycle as the table the game plays, thinned and true to the
frames the build checked; a looped cycle that does not end where it began fails by the joint's name."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import cad_check  # noqa: E402
import rbx_cycleplay as P  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join("build", "_test_cycleplay_build")


def build(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v, cls.jump = build("build_cycle_loop.py"), build("build_cycle_loop_jump.py")
        with open(os.path.join(ROOT, OUT, "models", "_selftest_cycle_loop.manifest.json"), encoding="utf-8") as fh:
            cls.cycles = {c["name"]: c for c in json.load(fh)["cycles"]}

    def test_the_manifest_carries_each_cycle_as_the_table_the_game_plays(self):
        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        turn, seat = self.cycles["Turn"]["play"], self.cycles["Seat"]["play"]
        self.assertEqual(turn["joints"], ["Pin", "Wheel"])                # by the joints' names (the game's Motor6Ds)
        self.assertEqual(turn["kinds"], ["slide", "hinge"])
        self.assertEqual((turn["loop"], seat["loop"]), (True, False))
        self.assertEqual((turn["length"], seat["length"]), (2.5, 0.5))    # 61 frames and 13 at 24 a second
        self.assertEqual(seat["marks"], {"seated": 0.5})
        self.assertEqual(len(turn["times"]), len(turn["values"]))
        self.assertEqual((turn["times"][0], turn["times"][-1]), (0.0, 2.5))

    def test_the_table_is_thinned_and_still_the_curve_the_build_checked(self):
        turn = self.cycles["Turn"]["play"]
        self.assertLess(len(turn["times"]), turn["frames"])               # fewer keys than frames
        wheel = turn["joints"].index("Wheel")
        # the wheel is keyed 0 at frame 1, 180 at frame 25, eased between: half way (12 frames in) it stands at 90
        self.assertAlmostEqual(P.at(turn, 0.5)[wheel], 90.0, delta=0.3)
        self.assertAlmostEqual(P.at(turn, 0.25)[wheel], 180 * (0.25 * 0.25 * (3 - 0.5)), delta=0.3)
        self.assertAlmostEqual(P.at(turn, 1.0)[wheel], 180.0, delta=0.01)
        self.assertAlmostEqual(P.at(turn, 2.5)[wheel], 0.0, delta=0.01)   # back where it began
        pin = turn["joints"].index("Pin")
        self.assertAlmostEqual(P.at(turn, 30 / 24)[pin], 0.12, delta=0.003)   # frame 31: the pin right down
        self.assertEqual(self.v["facts"]["cycle"]["play"]["Turn"]["keys"], len(turn["times"]))

    def test_a_looped_cycle_that_ends_elsewhere_fails_by_the_joints_name(self):
        self.assertEqual(self.jump["status"], "fail")
        said = [c for c in self.jump["design"] if c["name"] == "cycle_loop"]
        self.assertEqual([c["severity"] for c in said], ["error"])
        self.assertIn("Turn: Wheel ends at 180 and begins at 0 degrees", said[0]["value"][0])
        self.assertFalse(any(c["name"] == "cycle_loop" for c in self.v["design"]))


if __name__ == "__main__":
    unittest.main()
