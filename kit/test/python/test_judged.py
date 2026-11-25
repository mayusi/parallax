"""kit/tools/judged.py — a small copy of what the owner judged is kept beside the verdict, once per source file.
Run: python kit/test/python/run.py judged"""

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
TOOL = os.path.join(ROOT, "kit", "tools", "judged.py")


def run(src, dept_dir):
    p = subprocess.run([sys.executable, TOOL, src, dept_dir], capture_output=True, text=True, check=False)
    return p.returncode, json.loads(p.stdout.strip().splitlines()[-1])


def write_wav(path, seconds, rate=22050):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", (i * 37) % 2000 - 1000) for i in range(int(seconds * rate))))


class JudgedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dept = os.path.join(self.tmp.name, "vault", "anim")
        os.makedirs(self.dept)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_big_picture_is_kept_small_and_once(self):
        from PIL import Image

        src = os.path.join(self.tmp.name, "sheet.png")
        Image.new("RGB", (2000, 1000), (200, 40, 40)).save(src)
        code, out = run(src, self.dept)
        self.assertEqual(code, 0, out)
        self.assertTrue(out["rel"].startswith("anim/judged/") and out["rel"].endswith(".jpg"), out)
        self.assertFalse(out["reused"])
        self.assertLessEqual(out["bytes"], 150_000)
        kept = os.path.join(self.dept, "..", out["rel"])
        with Image.open(kept) as im:
            self.assertLessEqual(max(im.size), 640)
        # the same strip judged for another piece: the same copy, no second file
        code2, again = run(src, self.dept)
        self.assertEqual(code2, 0)
        self.assertTrue(again["reused"])
        self.assertEqual(again["rel"], out["rel"])
        self.assertEqual(len(os.listdir(os.path.join(self.dept, "judged"))), 1)

    def test_a_gif_keeps_its_middle_frame(self):
        from PIL import Image

        src = os.path.join(self.tmp.name, "pick.gif")
        frames = [Image.new("RGB", (64, 64), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
        frames[0].save(src, save_all=True, append_images=frames[1:], duration=100, loop=0)
        code, out = run(src, self.dept)
        self.assertEqual(code, 0, out)
        with Image.open(os.path.join(self.dept, "..", out["rel"])) as im:
            r, g, b = im.convert("RGB").getpixel((32, 32))
        self.assertGreater(g, 200)
        self.assertLess(r, 60)

    def test_a_short_sound_is_kept_as_it_is(self):
        src = os.path.join(self.tmp.name, "hit.wav")
        write_wav(src, 1.0)
        code, out = run(src, self.dept)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["kind"], "sound")
        with open(src, "rb") as a, open(os.path.join(self.dept, "..", out["rel"]), "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_a_long_wav_is_cut_to_four_seconds(self):
        src = os.path.join(self.tmp.name, "ambience.wav")
        write_wav(src, 20.0)
        self.assertGreater(os.path.getsize(src), 512_000)
        code, out = run(src, self.dept)
        self.assertEqual(code, 0, out)
        with wave.open(os.path.join(self.dept, "..", out["rel"]), "rb") as w:
            self.assertEqual(w.getnframes(), int(22050 * 4.0))

    def test_what_cannot_be_kept_is_refused(self):
        page = os.path.join(self.tmp.name, "picks.html")
        with open(page, "w", encoding="utf-8") as f:
            f.write("<html></html>")
        code, out = run(page, self.dept)
        self.assertEqual(code, 1)
        self.assertIn("not kept", out["error"])
        big = os.path.join(self.tmp.name, "long.mp3")
        with open(big, "wb") as f:
            f.write(b"ID3" + b"\x01" * 600_000)  # starts like an mp3, too long to keep, and only a wav can be cut
        code, out = run(big, self.dept)
        self.assertEqual(code, 1)
        self.assertIn("only a wav can be cut", out["error"])
        code, out = run(os.path.join(self.tmp.name, "nope.png"), self.dept)
        self.assertEqual(code, 1)
        self.assertIn("no such file", out["error"])

    def test_a_sound_that_does_not_decode_is_never_stored(self):
        zeros = os.path.join(self.tmp.name, "zeroed.wav")
        with open(zeros, "wb") as f:
            f.write(b"\x00" * 8192)
        code, out = run(zeros, self.dept)
        self.assertEqual(code, 1)
        silent = os.path.join(self.tmp.name, "silent.wav")
        with wave.open(silent, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(b"\x00\x00" * 8000)
        code, out = run(silent, self.dept)
        self.assertEqual(code, 1)
        self.assertIn("silence", out["error"])
        fake = os.path.join(self.tmp.name, "fake.mp3")
        with open(fake, "wb") as f:
            f.write(b"not audio")
        code, out = run(fake, self.dept)
        self.assertEqual(code, 1)
        self.assertIn("does not start like", out["error"])
        self.assertFalse(os.path.isdir(os.path.join(self.dept, "judged")))

    def test_bytes_kept_as_a_sound_are_never_handed_back_for_a_picture(self):
        sound = os.path.join(self.tmp.name, "hit.wav")
        write_wav(sound, 0.5)
        code, out = run(sound, self.dept)
        self.assertEqual(code, 0, out)
        same_bytes = os.path.join(self.tmp.name, "hit.png")
        with open(sound, "rb") as a, open(same_bytes, "wb") as b:
            b.write(a.read())
        code, out = run(same_bytes, self.dept)
        self.assertEqual(code, 1)  # not a picture: refused, not the .wav handed back as an "image"
        self.assertIn("could not keep", out["error"])

    def test_a_broken_picture_is_never_stored(self):
        src = os.path.join(self.tmp.name, "zeroed.png")
        with open(src, "wb") as f:
            f.write(b"\x00" * 4096)
        code, out = run(src, self.dept)
        self.assertEqual(code, 1)
        self.assertIn("could not keep", out["error"])
        self.assertFalse(os.path.isdir(os.path.join(self.dept, "judged")))


if __name__ == "__main__":
    unittest.main()
