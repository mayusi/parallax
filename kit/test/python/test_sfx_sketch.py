"""kit sfx sketch: a sonic direction sketch - a timeline scene played in one convolution space."""

import json
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "audio"))
import ears  # noqa: E402
import sketch  # noqa: E402
import synth  # noqa: E402

HIT = {"duration": 0.3, "layers": [{"role": "body", "source": "noise", "filter": {"type": "bandpass", "cutoff": 1200, "q": 1},
                                    "env": {"attack": 0.001, "decay": 0.08, "sustain": 0, "release": 0.02}, "gain": 1}]}


def scene(space, send=None):
    ev = {"name": "hit", "recipe": HIT, "at": [0.5], "pan": -0.8}
    if send is not None:
        ev["send"] = send  # (a test of the SPACE: the hit sent fully into it)
    return {"duration": 4, "lufs": -20, "space": space, "events": [ev]}


def run(sc):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "s.scene.json")
    json.dump(sc, open(p, "w"))
    out = os.path.join(d, "s.ogg")
    assert sketch.main([p, "--out", out]) == 0
    return out


class Sketch(unittest.TestCase):
    def test_stereo_on_target_and_under_full_scale(self):
        out = run(scene({"size": 0.3, "decay": 0.6, "bright": 0.5}))
        import subprocess, shutil
        info = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "stream=channels", "-of", "csv=p=0", out],
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual(info, "2")
        raw = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-i", out, "-f", "f32le", "-ac", "2", "-"],
                             capture_output=True, check=True).stdout
        x = np.frombuffer(raw, dtype="<f4").reshape(-1, 2).astype(float)
        self.assertLess(np.max(np.abs(x)), 1.0)  # (decoded: the encoder's overshoot stays under full scale)
        self.assertLess(ears.lufs(x.mean(1), synth.SR), -19.0)  # (never over the target)
        self.assertGreater(ears.lufs(x.mean(1), synth.SR), -32.0)  # (a lone hit lands under it: its dynamics are kept)
        self.assertGreater(np.abs(x[:, 0]).sum(), np.abs(x[:, 1]).sum() * 2)  # (panned left: the left carries it)

    def test_a_bigger_space_rings_longer(self):
        def tail(space):
            x = synth.load_sample(run(scene(space, send=1.0)))
            env = np.abs(x)
            above = np.nonzero(env > np.max(env) * 10 ** (-40 / 20))[0]
            return (above[-1] - above[0]) / synth.SR
        self.assertGreater(tail({"size": 0.9, "decay": 3.0, "bright": 0.4}), tail({"size": 0.2, "decay": 0.4, "bright": 0.4}) + 0.8)

    def test_the_ir_decays_by_its_rt60(self):
        ir = sketch.space_ir({"size": 0.5, "decay": 1.0, "bright": 0.5, "predelay": 0.0})
        e = ir[0] ** 2
        sr = synth.SR
        early = e[int(0.05 * sr):int(0.15 * sr)].mean()
        late = e[int(0.95 * sr):int(1.05 * sr)].mean()
        self.assertLess(10 * np.log10(late / early), -45)  # (~-54 dB over 0.9 s for RT60 = 1 s)


    def test_a_recorded_impulse_response_is_the_space(self):
        import subprocess, shutil, wave
        d = tempfile.mkdtemp()
        ir = os.path.join(d, "hall.wav")
        sr = synth.SR
        rng = np.random.default_rng(1)
        n = int(2.5 * sr)
        tail = rng.normal(0, 1, (4, n)) * np.exp(-np.arange(n) / (0.5 * sr))  # (a 4-channel "B-format" file)
        with wave.open(ir, "wb") as w:
            w.setnchannels(4)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((np.clip(tail.T / np.max(np.abs(tail)), -1, 1) * 32767).astype("<i2").tobytes())
        stereo = sketch.load_ir(ir)
        self.assertEqual(stereo.shape[0], 2)
        out = run(scene({"ir": ir}, send=1.0))
        x = synth.load_sample(out)
        env = np.abs(x)
        above = np.nonzero(env > np.max(env) * 10 ** (-40 / 20))[0]
        self.assertGreater((above[-1] - above[0]) / sr, 1.2)  # (the recorded room's long tail is heard)

    def test_a_source_walking_away_gets_quieter_step_by_step(self):
        step = {"duration": 0.15, "layers": [{"role": "body", "source": "noise", "filter": {"type": "bandpass", "cutoff": 900, "q": 1},
                                              "env": {"attack": 0.001, "decay": 0.05, "sustain": 0, "release": 0.02}, "gain": 1, "seed": 3}]}
        sc = {"duration": 8, "lufs": -24, "events": [{"name": "walker", "recipe": step, "at": [0.5 + 0.5 * k for k in range(14)],
                                                      "walk": {"dist": [0.05, 0.95]}}]}
        x = synth.load_sample(run(sc))
        sr = synth.SR
        lv = [np.max(np.abs(x[int((0.5 + 0.5 * k) * sr):int((0.5 + 0.5 * k + 0.12) * sr)])) for k in range(14)]
        self.assertLess(20 * np.log10(lv[-1] / lv[0]), -15)  # (far is ~ -20 dB: heard leaving)
        self.assertTrue(all(b <= a * 1.12 for a, b in zip(lv, lv[1:])))  # (never coming back)

    def test_a_walk_with_only_a_pan_and_a_zero_every_do_not_break(self):
        sc = {"duration": 2, "lufs": -24, "events": [
            {"name": "pan only", "recipe": HIT, "at": [0.2, 0.8, 1.4], "walk": {"pan": [-0.8, 0.8]}},
            {"name": "zero every", "recipe": HIT, "every": [0, 0], "until": 0.5}]}
        out = run(sc)
        self.assertTrue(os.path.isfile(out))

if __name__ == "__main__":
    unittest.main()
