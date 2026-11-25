"""kit sfx set's LOOP SEAM gate (sound mission ladder 2, ambience beds): a loop joins unheard, or the gate says where."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "audio"))
import sets  # noqa: E402
import synth  # noqa: E402

SR = 48000
GATES = {"seam_level_db": 3.0, "seam_bright": 0.25, "bed_min_s": 12.0}


def tone(seconds):
    t = np.arange(int(seconds * SR)) / SR
    return 0.3 * np.sin(2 * np.pi * 220 * t)  # (220 Hz: whole cycles in every whole second -> a perfect loop)


class Seam(unittest.TestCase):
    def test_a_perfect_loop_passes(self):
        self.assertEqual(sets.seam_errors("tone", tone(13), SR, GATES), [])

    def test_a_click_at_the_seam_is_named(self):
        x = tone(13)
        x[-1] += 0.4
        errs = sets.seam_errors("tone", x, SR, GATES)
        self.assertTrue(any("clicks at its seam" in e for e in errs), errs)

    def test_a_level_jump_at_the_seam_is_named(self):
        x = tone(13) * np.linspace(1.0, 0.45, int(13 * SR))  # (fades smoothly, then jumps back up at the repeat)
        errs = sets.seam_errors("tone", x, SR, GATES)
        self.assertTrue(any("dB from its start" in e for e in errs), errs)

    def test_a_colour_jump_between_two_sounding_ends_is_named_but_a_quiet_end_is_not(self):
        t = np.arange(int(13 * SR)) / SR
        x = 0.3 * np.sin(2 * np.pi * 220 * t)
        q = SR // 4
        jump = x.copy()
        jump[-q:] = 0.3 * np.sin(2 * np.pi * 5000 * t[-q:])  # (the last quarter second turns bright)
        self.assertTrue(any("bright vs its start" in e for e in sets.seam_errors("tone", jump, SR, GATES)))
        quiet = x.copy()
        quiet[-q:] *= 1e-4  # (it ends near-silent before the next downbeat: no colour to compare)
        self.assertFalse(any("bright vs its start" in e for e in sets.seam_errors("tone", quiet, SR, GATES)))

    def test_a_short_bed_repeats_like_a_rhythm(self):
        errs = sets.seam_errors("tone", tone(4), SR, GATES)
        self.assertTrue(any("repeats like a rhythm" in e for e in errs), errs)

    def test_a_synth_loop_with_gusts_and_the_subsonic_filter_joins(self):
        # (the subsonic filter now runs round the loop; gusts fit whole cycles into the loop's own length)
        recipe = {"duration": 13, "loop": True, "fx": {"loudness": -24}, "layers": [
            {"source": "noise", "color": "brown", "filter": {"type": "lowpass", "cutoff": 400},
             "env": {"attack": 0, "decay": 0, "sustain": 1, "release": 0}, "mod": {"rate": 0.2, "depth": 0.8, "seed": 3}}]}
        x = synth.render(recipe, seed=1, pitch=1.0)
        errs = sets.seam_errors("brown", x, synth.SR, GATES)
        self.assertFalse(any("clicks" in e or "dB from" in e for e in errs), errs)

    def test_gusts_join_round_the_loop(self):
        t = np.arange(0, 10, 1 / 100)
        g = synth.gusts({"rate": 0.3, "depth": 0.7, "seed": 2}, t, 10.0, None)
        self.assertLess(abs(synth.gusts({"rate": 0.3, "depth": 0.7, "seed": 2}, np.array([10.0]), 10.0, None)[0] - g[0]), 1e-9)
        self.assertGreaterEqual(g.min(), 0.3 - 1e-9)
        self.assertLessEqual(g.max(), 1.0 + 1e-9)



class SubDrop(unittest.TestCase):
    """the SUB DROP on the impact: the share of the first 150 ms under 120 Hz"""

    def test_a_sub_thump_is_all_sub_and_a_click_is_none(self):
        t = np.arange(int(0.3 * SR)) / SR
        thump = np.sin(2 * np.pi * 55 * t) * np.exp(-t * 12)
        click = np.random.default_rng(1).standard_normal(len(t)) * np.exp(-t * 200)
        self.assertGreater(sets.early_sub(thump, SR), 0.9)
        self.assertLess(sets.early_sub(click, SR), 0.05)

    def test_it_starts_at_the_onset_not_the_file_start(self):
        t = np.arange(int(0.3 * SR)) / SR
        thump = np.sin(2 * np.pi * 55 * t) * np.exp(-t * 12)
        late = np.concatenate([np.zeros(int(0.5 * SR)), thump])  # (half a second of silence first)
        self.assertGreater(sets.early_sub(late, SR), 0.9)
        self.assertEqual(sets.early_sub(np.zeros(1000), SR), 0.0)


class SampleEnd(unittest.TestCase):
    def test_a_recording_cut_mid_tail_fades_instead_of_clicking(self):
        synth._SAMPLES["cut.ogg"] = np.ones(int(0.1 * synth.SR))  # (a file that stops at full level)
        out = synth.sample_source({"sample": "cut.ogg"}, int(0.3 * synth.SR), 0, 1.0)
        m = int(0.1 * synth.SR)
        self.assertLess(abs(out[m - 1]), 0.01)
        self.assertGreater(out[m // 2], 0.99)  # (the body untouched)
        self.assertLess(np.max(np.abs(np.diff(out))), 0.01)  # (no step anywhere)

    def test_a_library_pack_missing_on_this_checkout_says_how_to_get_it(self):
        import json
        import tempfile

        import sfxlib

        fd, idx = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"entries": {"pack.step": {"id": "pack.step", "file": "_nowhere/step.ogg", "trim": None,
                                                 "licence": "CC0", "source": "pack"}}, "sources": {}}, fh)
        old, sfxlib.INDEX = sfxlib.INDEX, idx
        try:
            with self.assertRaisesRegex(ValueError, "library recording missing.*pack pack.*VETLOG"):
                synth.load_sample("lib:pack.step")
        finally:
            sfxlib.INDEX = old


if __name__ == "__main__":
    unittest.main()
