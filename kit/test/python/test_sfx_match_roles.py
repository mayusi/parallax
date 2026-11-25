"""kit sfx match's verdict: one difference per layer ROLE and ONE edit (verifier over judge), from ears numbers."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "audio"))
import match  # noqa: E402

BASE = {"lufs": -16.0, "crest_db": 14.0, "brightness_hz": 2000.0, "tail_ms": 400.0, "transient_ms": 6.0,
        "attack_ms": 5.0, "sub_share": 0.20, "high_share": 0.15, "flux": 2.0, "onsets": 1}

RECIPE = {"layers": [
    {"role": "transient", "source": "click", "env": {"attack": 0.001, "release": 0.02}},
    {"role": "body", "source": "noise", "filter": {"type": "lowpass", "cutoff": 3000}, "env": {"release": 0.3}},
    {"role": "sub", "source": "sine", "gain": 0.8},
    {"role": "tail", "source": "noise", "env": {"release": 0.5}},
]}


class TestRolesReport(unittest.TestCase):
    def test_a_matching_sound_has_no_edit(self):
        roles, edit, _ = match.roles_report(RECIPE, dict(BASE), dict(BASE))
        self.assertIsNone(edit)
        for role in ("transient", "body", "sub", "tail"):
            self.assertEqual(roles[role], ["matches the reference"])

    def test_too_little_sub_is_the_sub_layers_gain(self):
        after = dict(BASE, sub_share=0.05)
        roles, edit, _ = match.roles_report(RECIPE, after, dict(BASE))
        self.assertIn("less sub", roles["sub"][0])
        self.assertTrue(edit.startswith("layer 3 (sub, sine): gain +"), edit)

    def test_a_short_tail_lengthens_the_tail_layers_release(self):
        after = dict(BASE, tail_ms=100.0)
        _, edit, _ = match.roles_report(RECIPE, after, dict(BASE))
        self.assertTrue(edit.startswith("layer 4 (tail, noise): env release 0.500 -> 0.800"), edit)

    def test_too_bright_lowers_the_body_cutoff(self):
        after = dict(BASE, brightness_hz=3000.0)
        roles, edit, _ = match.roles_report(RECIPE, after, dict(BASE))
        self.assertIn("brighter", roles["body"][0])
        self.assertTrue(edit.startswith("layer 2 (body, noise): filter cutoff 3000 -> 2000 Hz"), edit)

    def test_the_biggest_difference_wins_and_loudness_is_the_mix(self):
        after = dict(BASE, lufs=-6.0, tail_ms=480.0)  # 10 LU louder (x6.7) beats an 80 ms tail (x1)
        roles, edit, _ = match.roles_report(RECIPE, after, dict(BASE))
        self.assertTrue(edit.startswith("fx.loudness -10.0 LU"), edit)
        self.assertIn("mix", roles)

    def test_a_missing_role_is_named(self):
        recipe = {"layers": [{"role": "transient", "source": "click"}]}
        _, edit, _ = match.roles_report(recipe, dict(BASE, sub_share=0.0), dict(BASE))
        self.assertIn("add a 'sub' layer", edit)


if __name__ == "__main__":
    unittest.main()
