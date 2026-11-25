"""kit trace --organic: a curved organic form's tapers are its shape. The perspective check (straight members keep their
thickness: a barrel, a rail) once failed a skull's side photo ("thickness changes 25% along its length"); --organic
skips it and says so in the trace, a hard-surface trace keeps it."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import make as MK  # noqa: E402
import trace as T  # noqa: E402  (kit/blender/trace.py: system python, no bpy)

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def teardrop(path):
    """a dark skull-like side silhouette on white: a big round vault tapering to a narrow jaw"""
    im = Image.new("RGB", (900, 600), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse((120, 80, 560, 520), fill=(40, 35, 30))                 # the vault
    d.polygon([(420, 200), (800, 330), (790, 390), (420, 470)], fill=(40, 35, 30))   # tapering to the jaw
    im.save(path)


class Organic(unittest.TestCase):
    def _trace(self, organic):
        name = f"_test_organic_trace_{int(organic)}"
        with tempfile.TemporaryDirectory() as tmp:
            pic = os.path.join(tmp, "side.png")
            teardrop(pic)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                T.trace(pic, None, name, bg="light", organic=organic)
        # where the trace writes: the active game's folder (games/.active) or the root - the test read the root only
        # and failed once a lane made SampleGame the active game (2026-11-01)
        root = T.game_root()
        for p in (os.path.join(root, "assets", "models", f"{name}.trace.json"),
                  os.path.join(root, "build", "renders", f"{name}_trace.png")):
            saved = None
            if p.endswith(".json") and os.path.isfile(p):
                with open(p, encoding="utf-8") as fh:
                    saved = json.load(fh)
            if os.path.isfile(p):
                os.remove(p)
            if saved is not None:
                self.saved = saved
        return buf.getvalue()

    def test_a_hard_trace_keeps_the_perspective_check(self):
        out = self._trace(False)
        self.assertIn("PERSPECTIVE", out)

    def test_an_organic_trace_skips_it_and_says_so(self):
        out = self._trace(True)
        self.assertNotIn("PERSPECTIVE", out)
        self.assertTrue(self.saved.get("organic"))

    def test_kit_make_knows_organic_words(self):
        self.assertTrue(MK.is_organic("a human skull"))
        self.assertTrue(MK.is_organic("a mossy boulder"))
        self.assertFalse(MK.is_organic("a rocket launcher"))   # (whole words: "rock" in "rocket" is no rock)
        self.assertFalse(MK.is_organic("Glock 17 Gen 5"))


if __name__ == "__main__":
    unittest.main()
