"""kit sfx set: the masking warning - two layers that hit together in the same loudest bands smear into one."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "audio"))
import sets  # noqa: E402


def layer(cut, q=1.2, seed=1, delay=0.0, gain=1.0):
    return {"role": "body", "source": "noise", "filter": {"type": "bandpass", "cutoff": cut, "q": q}, "delay": delay,
            "env": {"attack": 0.001, "decay": 0.12, "sustain": 0, "release": 0.03}, "gain": gain, "seed": seed}


class Masking(unittest.TestCase):
    def test_two_layers_in_one_band_at_one_moment_are_named(self):
        w = sets.masking_warnings("fight", {"duration": 0.5, "layers": [layer(600), layer(650, seed=2)]})
        self.assertEqual(len(w), 1)
        self.assertIn("layers 1 (body) and 2 (body)", w[0])
        self.assertIn("Hz", w[0])

    def test_carved_bands_do_not_fight(self):
        self.assertEqual(sets.masking_warnings("carved", {"duration": 0.5, "layers": [layer(250, 2.5), layer(3500, 2.5, 2)]}), [])

    def test_offset_in_time_does_not_fight(self):
        self.assertEqual(sets.masking_warnings("offset", {"duration": 0.6, "layers": [layer(600), layer(650, seed=2, delay=0.12)]}), [])

    def test_a_quiet_sweetener_is_not_a_fight(self):
        self.assertEqual(sets.masking_warnings("sweet", {"duration": 0.5, "layers": [layer(600), layer(650, seed=2, gain=0.2)]}), [])


if __name__ == "__main__":
    unittest.main()
