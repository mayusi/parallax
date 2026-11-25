"""kit sfx set: the masking GATE (LIMITATIONS_FIXES_V4 SFX-X B) - an error for a set made since the gate (first
committed on/after MASKING_ENFORCED_FROM, or not committed yet) and for one that declares "masking": "enforce"; a
warning for the sets that were in the repo before it. No set is named anywhere: the rule is the set file's birth date."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "audio"))
import sets  # noqa: E402


def layer(cut, seed=1):
    return {"role": "body", "source": "noise", "filter": {"type": "bandpass", "cutoff": cut, "q": 1.2},
            "env": {"attack": 0.001, "decay": 0.12, "sustain": 0, "release": 0.03}, "gain": 1.0, "seed": seed}


# two bodies in one band at one moment: the masking check names them (test_sfx_masking.py proves the detector)
MASKING_SET = {"about": "a masking fixture", "loudness": -16, "variations": 1,
               "members": {"mask_probe": {"class": "hit", "duration": 0.5, "layers": [layer(600), layer(650, seed=2)]}}}


class MaskingMode(unittest.TestCase):
    def test_a_declared_enforce_is_an_error_whatever_its_age(self):
        with mock.patch.object(sets, "set_born", return_value="2026-10-13"):
            level, why = sets.masking_mode({"masking": "enforce"}, "x.json")
        self.assertEqual(level, "error")
        self.assertIn("enforce", why)

    def test_a_set_born_on_or_after_the_gate_is_an_error(self):
        for born in (sets.MASKING_ENFORCED_FROM, "2027-01-02"):
            with mock.patch.object(sets, "set_born", return_value=born):
                self.assertEqual(sets.masking_mode({}, "x.json")[0], "error")

    def test_an_uncommitted_set_is_new_so_an_error(self):
        with mock.patch.object(sets, "set_born", return_value=""):
            level, why = sets.masking_mode({}, "x.json")
        self.assertEqual(level, "error")
        self.assertIn("not committed", why)

    def test_an_older_set_keeps_the_warning_and_is_told_how_to_opt_in(self):
        with mock.patch.object(sets, "set_born", return_value="2026-10-18"):
            level, why = sets.masking_mode({}, "x.json")
        self.assertEqual(level, "warn")
        self.assertIn('"masking": "enforce"', why)

    def test_a_set_git_cannot_date_is_a_warning(self):
        with mock.patch.object(sets, "set_born", return_value=None):
            self.assertEqual(sets.masking_mode({}, "x.json")[0], "warn")

    def test_a_new_set_cannot_opt_out_by_declaring_warn(self):
        with mock.patch.object(sets, "set_born", return_value=""):
            self.assertEqual(sets.masking_mode({"masking": "warn"}, "x.json")[0], "error")

    def test_the_repos_older_sets_read_their_real_birth_from_git(self):
        # the sets that already warned stay warnings (their first commits are before the gate); nothing is listed
        for rel in ("assets/sounds/sets/footsteps.json", "assets/sounds/sets/katana_steel.json",
                    "games/SampleDojo/assets/sounds/sets/dojo_music.json",
                    "games/SampleRegion/assets/sounds/sets/sampleregion_ambience.json"):
            p = os.path.join(ROOT, rel)
            if not os.path.isfile(p):
                continue
            born = sets.set_born(p)
            if born is None:
                self.skipTest("git is not available here")
            self.assertTrue(born and born < sets.MASKING_ENFORCED_FROM, f"{rel}: born {born!r}")
            self.assertEqual(sets.masking_mode({}, p)[0], "warn", rel)

    def test_an_untracked_file_in_the_repo_is_born_today(self):
        d = tempfile.mkdtemp(dir=os.path.join(ROOT, "build")) if os.path.isdir(os.path.join(ROOT, "build")) else None
        if d is None:
            self.skipTest("no build folder")
        try:
            p = os.path.join(d, "fresh_set.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(MASKING_SET, fh)
            born = sets.set_born(p)
            if born is None:
                self.skipTest("git is not available here")
            self.assertEqual(born, "")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class MaskingInRunSet(unittest.TestCase):
    """the gate inside the real set run: the same masking fixture fails a new set and only warns on an old one"""

    def run_fixture(self, born):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "mask_fixture.json")
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(MASKING_SET, fh)
            with mock.patch.object(sets, "set_born", return_value=born):
                return sets.run_set(p, os.path.join(d, "out"))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_new_set_masking_is_an_error(self):
        r = self.run_fixture("")
        self.assertFalse(r["ok"])
        self.assertTrue(any("mask each other" in e and "masking is an error here" in e for e in r["errors"]), r["errors"])
        self.assertEqual(r["masking"]["level"], "error")

    def test_old_set_masking_stays_a_warning(self):
        r = self.run_fixture("2026-10-13")
        self.assertFalse(any("mask each other" in e for e in r["errors"]), r["errors"])
        self.assertTrue(any("mask each other" in w for w in r["warnings"]), r["warnings"])
        self.assertEqual(r["masking"]["level"], "warn")


if __name__ == "__main__":
    unittest.main()
