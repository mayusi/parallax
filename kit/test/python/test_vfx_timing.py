"""kit vfx timing (kit/vfx/timing.py; the V3 doc, VFX stage E.3: "<= +-1 frame visual peak vs SFX transient"): a
sound hit must land on a picture hit within ONE frame of the player's 24 fps (it was two, 83 ms), a big picture hit
needs its sound, and a recording with nothing to judge it against says "unchecked" (exit 0) instead of failing.
Run: python -m pytest kit/test/python/test_vfx_timing.py -q"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import timing as T  # noqa: E402


class Judge(unittest.TestCase):
    def test_one_frame_is_the_bar(self):
        self.assertAlmostEqual(T.TOL, 1 / 24.0)
        _, ok = T.judge([(1.0, 1.0)], [(1.03, 1.0)])            # 30 ms: inside one frame
        self.assertEqual(ok, [])
        _, late = T.judge([(1.0, 1.0)], [(1.06, 1.0)])          # 60 ms: inside the OLD two frames, past one
        self.assertEqual(len(late), 1)
        self.assertIn("LATE by 60 ms", late[0])
        _, early = T.judge([(1.0, 1.0)], [(0.95, 1.0)])
        self.assertIn("EARLY", early[0])
        _, none = T.judge([(1.0, 1.0)], [(1.7, 0.3)])           # nothing near at all (over the 0.5 s pairing reach)
        self.assertIn("no picture hit", none[0])

    def test_a_big_picture_hit_needs_its_sound_a_small_one_does_not(self):
        _, p = T.judge([(1.0, 1.0)], [(1.0, 1.0), (2.0, 0.9)])
        self.assertEqual(len(p), 1)
        self.assertIn("2.00 s has no sound", p[0])
        _, quiet = T.judge([(1.0, 1.0)], [(1.0, 1.0), (2.0, 0.3)])
        self.assertEqual(quiet, [])

    def test_pairs_say_how_far_off_each_is(self):
        pairs, _ = T.judge([(1.0, 1.0), (2.0, 0.5)], [(1.02, 1.0), (1.98, 0.7)])
        self.assertEqual([p["offset"] for p in pairs], [0.02, -0.02])


class Command(unittest.TestCase):
    def test_nothing_to_judge_against_is_unchecked_not_a_failure(self):
        # (exit 0 and status "unchecked": the play command records many effects with no sound layers)
        code = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import timing; "
                               "timing.out('unchecked', 'x', 'none')", os.path.join(HERE, "..", "..", "vfx")]).returncode
        self.assertEqual(code, 0)
        code = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import timing; "
                               "timing.out('warn', 'x', 'none')", os.path.join(HERE, "..", "..", "vfx")]).returncode
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
