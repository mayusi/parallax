"""ears.lufs_crosscheck: the kit's BS.1770-4 meter beside pyloudnorm's (vetted, OPTIONAL). Without pyloudnorm nothing
is compared and nothing passes by default (ok None, a note says why); with it, a disagreement fails. The real
comparison runs only when pyloudnorm is installed; a stub proves the wiring and the fail path either way."""

import os
import sys
import types
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "audio"))
import ears  # noqa: E402

SR = 48000


def sine(seconds=2.0, f=1000.0, amp=0.5):
    t = np.arange(int(seconds * SR)) / SR
    return amp * np.sin(2 * np.pi * f * t)


def stub(value):
    """a fake pyloudnorm whose meter reads `value` (the wiring, not the standard)"""
    m = types.ModuleType("pyloudnorm")

    class Meter:
        def __init__(self, rate):
            self.rate = rate

        def integrated_loudness(self, x):
            return value

    m.Meter = Meter
    return m


class CrossCheck(unittest.TestCase):
    def test_not_installed_is_never_a_pass(self):
        with mock.patch.object(ears, "_pyloudnorm", return_value=None):
            r = ears.lufs_crosscheck(sine(), SR)
        self.assertFalse(r["available"])
        self.assertIsNone(r["ok"])
        self.assertIn("not installed", r["note"])
        self.assertAlmostEqual(r["ours"], -9.03, delta=0.05)  # (a 0.5 full-scale 1 kHz sine: -3.01 - 6.02)

    def test_agreement_within_tolerance_passes_and_a_disagreement_fails(self):
        ours = ears.lufs(sine(), SR)
        with mock.patch.object(ears, "_pyloudnorm", return_value=stub(ours + 0.2)):
            self.assertTrue(ears.lufs_crosscheck(sine(), SR)["ok"])
        with mock.patch.object(ears, "_pyloudnorm", return_value=stub(ours + 2.0)):
            r = ears.lufs_crosscheck(sine(), SR)
        self.assertFalse(r["ok"])
        self.assertAlmostEqual(r["diff_lu"], -2.0, delta=0.01)

    def test_a_sound_shorter_than_one_block_is_not_compared(self):
        with mock.patch.object(ears, "_pyloudnorm", return_value=stub(-20.0)):
            r = ears.lufs_crosscheck(sine(0.25), SR)
        self.assertTrue(r["available"])
        self.assertIsNone(r["ok"])
        self.assertIn("400 ms", r["note"])

    def test_silence_by_their_meter_is_not_compared(self):
        with mock.patch.object(ears, "_pyloudnorm", return_value=stub(float("-inf"))):
            self.assertIsNone(ears.lufs_crosscheck(sine(), SR)["ok"])

    @unittest.skipUnless(ears._pyloudnorm() is not None, "pyloudnorm not installed (vetted, waits on the owner's yes)")
    def test_real_pyloudnorm_agrees_with_our_meter(self):
        rng = np.random.default_rng(3)
        for x in (sine(), sine(3.0, 100.0, 0.3), 0.1 * rng.standard_normal(SR * 2)):
            r = ears.lufs_crosscheck(x, SR)
            self.assertTrue(r["ok"], r)


if __name__ == "__main__":
    unittest.main()
