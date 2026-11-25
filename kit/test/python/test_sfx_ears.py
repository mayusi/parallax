"""ears.py / synth.py recipe v2 / sets.py — measuring sound without hearing it, and the sound-set family gates."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "audio"))
import ears as E  # noqa: E402
import sets as S  # noqa: E402
import synth  # noqa: E402

SR = 44100


def tone(hz, seconds, decay=None, amp=0.5):
    t = np.arange(int(seconds * SR)) / SR
    x = amp * np.sin(2 * np.pi * hz * t)
    return x * np.exp(-t / decay) if decay else x


class Loudness(unittest.TestCase):
    def test_1k_sine_reads_its_textbook_loudness(self):
        # BS.1770: a full-scale 997 Hz sine reads -3.01 LUFS; at amplitude 0.5 it is 6 dB lower
        self.assertAlmostEqual(E.lufs(tone(997, 3.0, amp=1.0), SR), -3.0, delta=0.15)
        self.assertAlmostEqual(E.lufs(tone(997, 3.0, amp=0.5), SR), -9.0, delta=0.15)

    def test_short_sounds_do_not_jump_at_the_block_edge(self):
        # a 0.5 s sound and the same sound 128 samples shorter (OGG decoding) read the same (was 2.5 LU apart)
        x = tone(800, 0.5, decay=0.12)
        self.assertAlmostEqual(E.lufs(x, SR), E.lufs(x[:-128], SR), delta=0.3)


class Ears(unittest.TestCase):
    def test_a_struck_bar_darkens_and_has_one_onset(self):
        x = tone(3000, 0.6, decay=0.05) + tone(400, 0.6, decay=0.3)
        e = E.measure(x, SR)
        self.assertEqual(e["onsets"], 1)
        self.assertGreater(e["centroid_start_hz"], e["centroid_end_hz"])
        self.assertLess(e["transient_ms"], 3)

    def test_three_beeps_are_three_onsets(self):
        x = np.zeros(int(0.9 * SR))
        for k in range(3):
            s = int((0.05 + k * 0.25) * SR)
            x[s : s + int(0.08 * SR)] += tone(1200, 0.08)
        self.assertEqual(E.measure(x, SR)["onsets"], 3)

    def test_hits_after_digital_silence_all_count(self):
        # silence, a soft swing, then a hit: the rise out of -180 dB once hid every later hit
        x = np.zeros(int(0.8 * SR))
        s1, s2 = int(0.1 * SR), int(0.35 * SR)
        x[s1 : s1 + int(0.2 * SR)] += tone(900, 0.2, decay=0.06, amp=0.3)
        x[s2 : s2 + int(0.3 * SR)] += tone(2000, 0.3, decay=0.08, amp=0.9)
        got = E.onsets(x, SR)
        self.assertEqual(len(got), 2)
        self.assertAlmostEqual(got[1], 0.35, delta=0.02)

    def test_sub_and_air_shares(self):
        self.assertGreater(E.measure(tone(50, 0.5), SR)["sub_share"], 0.9)
        rng = np.random.default_rng(0)
        hiss = synth.sweep_filter(rng.standard_normal(SR // 2), {"type": "highpass", "cutoff": 6000})
        self.assertGreater(E.measure(hiss, SR)["high_share"], 0.8)

    def test_delta_words_name_the_biggest_difference_first(self):
        a = E.measure(tone(3000, 0.3, decay=0.05), SR)
        b = E.measure(tone(600, 0.3, decay=0.05), SR)
        _, words = E.delta(a, b)
        self.assertIn("brighter", words[0])
        self.assertGreater(E.distance(a, b), E.distance(a, a))
        self.assertEqual(E.distance(a, a), 0.0)


class RecipeV2(unittest.TestCase):
    def test_heavier_is_lower_and_drops_light_only_layers(self):
        recipe = {"layers": [{"source": "sine", "freq": 440}, {"source": "sine", "freq": 60, "role": "sub", "min_weight": 0.4}]}
        light, lp = synth.apply_weight(dict(recipe, weight=0.1))
        heavy, hp = synth.apply_weight(dict(recipe, weight=0.9))
        self.assertEqual(len(light), 1)
        self.assertEqual(len(heavy), 2)
        self.assertLess(hp, 1.0)
        self.assertGreater(lp, 1.0)

    def test_modal_strike_varies_takes_but_keeps_the_body(self):
        layer = {"source": "modal", "modes": [[820, 0.8, 1.0], [2262, 0.6, 0.7], [4431, 0.4, 0.4]]}
        a = synth.render_layer(layer, SR // 2, np.random.default_rng(1), 1.0, 0)
        b = synth.render_layer(layer, SR // 2, np.random.default_rng(2), 1.0, 1)
        ea, eb = E.measure(a, SR), E.measure(b, SR)
        self.assertGreater(E.distance(ea, eb), 0.05)  # (a different strike point)
        self.assertLess(abs(np.log2(ea["brightness_hz"] / eb["brightness_hz"])), 0.5)  # (the same bar)

    def test_loudness_target_is_reached_through_the_limiter(self):
        recipe = {"duration": 0.6, "fx": {"loudness": -14}, "layers": [
            {"source": "click", "gain": 1.0},
            {"source": "sine", "freq": 300, "env": {"attack": 0.001, "decay": 0.3}, "gain": 0.3}]}
        x = synth.render(recipe, 1, 1.0)
        self.assertAlmostEqual(E.lufs(x, SR), -14, delta=0.8)
        self.assertLessEqual(np.max(np.abs(x)), 10 ** (-1 / 20) + 1e-6)

    def test_seeded_noise_is_the_same_every_take(self):
        layer = {"source": "noise", "seed": 5, "env": {"decay": 0.1}}
        a = synth.render_layer(layer, 4410, np.random.default_rng(1), 1.0)
        b = synth.render_layer(layer, 4410, np.random.default_rng(99), 1.0)
        self.assertTrue(np.allclose(a, b))


class Sets(unittest.TestCase):
    def test_members_resolve_dna_and_weights(self):
        spec = {"dna": {"ring": {"source": "sine", "freq": 800, "gain": 0.5}},
                "members": {"hit": {"use": {"ring": {"gain": 0.2}}, "layers": [{"source": "click"}], "weights": [0.9, 0.1, 0.5]}}}
        r = S.resolve(spec)
        self.assertEqual(sorted(r), ["hit_heavy", "hit_light", "hit_medium"])
        self.assertEqual(r["hit_light"]["weight"], 0.1)
        self.assertEqual(r["hit_heavy"]["layers"][0]["gain"], 0.2)

    def test_an_unknown_dna_layer_is_an_error(self):
        with self.assertRaises(ValueError):
            S.resolve({"dna": {}, "members": {"x": {"use": ["nope"]}}})

    def test_a_role_that_lies_is_named(self):
        recipe = {"duration": 0.4, "layers": [{"role": "sub", "source": "sine", "freq": 2000}]}
        self.assertTrue(S.role_errors("x", recipe))
        recipe["layers"][0]["freq"] = 50
        self.assertFalse(S.role_errors("x", recipe))



class Library(unittest.TestCase):
    def test_a_long_take_splits_into_its_events(self):
        import sfxlib as L

        x = np.zeros(int(3.0 * SR))
        for t in (0.2, 1.1, 2.3):
            s = int(t * SR)
            x[s : s + int(0.3 * SR)] += tone(700, 0.3, decay=0.05)
        ev = L.split_events(x, SR)
        self.assertEqual(len(ev), 3)
        self.assertAlmostEqual(ev[1][0], 1.1, delta=0.03)

    def test_words_come_from_the_path_and_the_ears(self):
        import sfxlib as L

        self.assertEqual(L.path_words("Kenney/Impact Sounds/impactMetal_heavy_003.ogg"), ["heavy", "impact", "kenney", "metal"])
        e = E.measure(tone(60, 0.3, decay=0.08), SR)
        self.assertIn("sub", L.ear_words(e))



class Modal(unittest.TestCase):
    def test_a_struck_bar_gives_back_its_own_modes(self):
        import modal as M

        truth = [[820, 1.1, 1.0], [2262, 0.85, 0.7], [3190, 0.5, 0.25], [4431, 0.55, 0.45], [7325, 0.35, 0.25]]
        x = synth.modal(int(1.6 * SR), np.random.default_rng(1), {"modes": truth, "strike": 0.32}, 0, 1.0)
        got = M.extract(x, SR, n_modes=8)
        self.assertEqual(len(got), 5)
        for (hz, dec, _), (ghz, gdec, _) in zip(truth, got):
            self.assertAlmostEqual(ghz, hz, delta=hz * 0.005)
            self.assertAlmostEqual(gdec, dec, delta=dec * 0.15)

    def test_noise_has_no_modes(self):
        import modal as M

        x = np.random.default_rng(0).standard_normal(SR) * np.exp(-np.arange(SR) / SR * 6)
        with self.assertRaises(ValueError):
            M.extract(x, SR)

if __name__ == "__main__":
    unittest.main()
