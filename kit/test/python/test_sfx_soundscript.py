"""kit sfx soundscript: the journey's dynamics in order; neighbours that sound the same are named."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "audio"))
import soundscript  # noqa: E402
import synth  # noqa: E402

DOC = """# {name} — sound direction

## Pick
pending — my recommendation: A

## Directions
### A — x
Sketch: direction/{name}_A.ogg
"""


def write_ogg(path, x):
    wav = path[:-4] + ".wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(synth.SR)
        st = np.stack([x, x], 1)
        w.writeframes((np.clip(st, -1, 1) * 32767).astype("<i2").tobytes())
    subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "libvorbis", path], check=True)


class SoundScript(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        os.chdir(self.tmp)
        d = os.path.join("games", "G", "assets", "sounds", "direction")
        os.makedirs(d)
        sr = synth.SR
        rng = np.random.default_rng(1)
        quiet = rng.normal(0, 0.01, sr * 6)
        busy = rng.normal(0, 0.01, sr * 6)
        for k in range(30):  # loud clicks: a busy place
            i = int(k * 0.2 * sr)
            busy[i:i + 200] += rng.normal(0, 0.6, 200)
        for name, x in (("Quiet", quiet), ("Quiet2", quiet * 1.02), ("Busy", busy)):
            open(os.path.join(d, f"{name}.md"), "w", encoding="utf-8").write(DOC.format(name=name))
            write_ogg(os.path.join(d, f"{name}_A.ogg"), x)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_sounding_neighbours_are_named(self):
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(soundscript.main(["G", "--order", "Quiet,Quiet2,Busy", "--out", os.path.join(self.tmp, "s.png")]), 0)
        r = json.loads(buf.getvalue().strip().splitlines()[-1])
        self.assertEqual(r["flat"], ["Quiet -> Quiet2"])


if __name__ == "__main__":
    unittest.main()
