"""kit judge --record says when a new verdict is inside the judges' noise (the Glock's material rounds, 2026-10-10:
59.5, 58.5, 58.2, 60.1 — two panels asking for opposite changes round to round): not progress, and three in a row is
a plateau to stop tuning."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import judge as J  # noqa: E402


class Noise(unittest.TestCase):
    def test_the_glock_material_rounds(self):
        self.assertEqual(J.progress([59.5]), "")
        self.assertEqual(J.progress([59.5, 58.5]), "noise")
        self.assertEqual(J.progress([59.5, 58.5, 58.2]), "plateau")
        self.assertEqual(J.progress([59.5, 58.5, 58.2, 60.1]), "noise")   # (+0.6 on the best before it: no step)

    def test_a_real_step_is_progress(self):
        self.assertEqual(J.progress([56.8, 61.2]), "")   # (the sRGB wear fix: +4.4)
        self.assertEqual(J.progress([61.2, 61.8, 64.0]), "")

    def test_a_wide_panel_widens_the_band(self):
        self.assertEqual(J.progress([60.0, 62.0], spread=2.6), "")
        self.assertEqual(J.progress([60.0, 62.0], spread=4.4), "noise")


class Stall(unittest.TestCase):
    def test_the_skull_tweak_rounds_stall_the_judge(self):
        # (2026-10-11: seven builds, 36.5 / 37.5 / 38 / 39 / 35 — the kit kept packing judge rounds for tweaks)
        self.assertIn("no step", J.stalled([28.0, 36.5, 38.0, 39.0, 35.0, 37.0]))
        self.assertIn("noise", J.stalled([59.5, 58.5, 58.2]))
        self.assertEqual(J.stalled([30.0, 38.0, 45.0]), "")          # (climbing: keep going)
        self.assertEqual(J.stalled([36.5, 38.0, 39.0, 44.0]), "")    # (a real step past the best)

    def test_a_stalled_asset_gets_no_packet_without_a_structural_change(self):
        import json
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(repo, "assets", "models"))
            with open(os.path.join(repo, "assets", "models", "thing.judge.json"), "w", encoding="utf-8") as fh:
                json.dump({"history": [{"score": s_, "at": "2026-10-11 09:00"} for s_ in (28.0, 36.5, 38.0, 39.0, 35.0, 37.0)]}, fh)
            with mock.patch.object(J, "REPO", repo), mock.patch.object(J, "_manifest", return_value={"tier": "hero"}), \
                    mock.patch.object(J, "_out", side_effect=lambda st, su, nx, **kw: (st, su, nx)):
                status, summary, nxt = J.packet("thing")
                self.assertEqual(status, "fail")
                self.assertIn("STALLED", summary)
                self.assertIn("--structural", nxt)
                # with a named structural change it goes on (here: to the next missing piece, the renders)
                status2, summary2, _ = J.packet("thing", structural="sections lofted from the reference")
                self.assertNotIn("STALLED", summary2)


if __name__ == "__main__":
    unittest.main()
