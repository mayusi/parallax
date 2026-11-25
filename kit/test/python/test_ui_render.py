"""kit ui render (a Blender script): the pure parts testable without Blender — the font picker takes the UPRIGHT face
over its italic twin unless the font entry says italic (13 faces rendered slanted: audit 2026-10-16)"""
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.modules.setdefault("bpy", types.ModuleType("bpy"))  # (render.py runs inside Blender; the picker needs none of it)
_spec = importlib.util.spec_from_file_location("kit_ui_render", os.path.join(HERE, "..", "..", "ui", "render.py"))
render = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render)


class TestRenderFonts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old_env = os.environ.get("ROBLOX_KIT_CACHE")
        os.environ["ROBLOX_KIT_CACHE"] = self.tmp
        folder = os.path.join(self.tmp, "fonts", "face")
        os.makedirs(folder)
        for f in ("Face-Italic[wght].ttf", "Face[wght].ttf"):
            open(os.path.join(folder, f), "wb").close()
        self.table = {"families": {"face": {"folder": "face"}},
                      "fonts": {"Face": {"family": "face", "weight": 400}, "FaceItalic": {"family": "face", "weight": 400, "italic": True}}}
        self.old_here = render.HERE
        render.HERE = self.tmp
        with open(os.path.join(self.tmp, "fonts.json"), "w", encoding="utf-8") as fh:
            json.dump(self.table, fh)

    def tearDown(self):
        render.HERE = self.old_here
        if self.old_env is None:
            os.environ.pop("ROBLOX_KIT_CACHE", None)
        else:
            os.environ["ROBLOX_KIT_CACHE"] = self.old_env

    def test_upright_unless_the_entry_says_italic(self):
        self.assertEqual(os.path.basename(render.resolve_font("Face")), "Face[wght].ttf")
        self.assertEqual(os.path.basename(render.resolve_font("FaceItalic")), "Face-Italic[wght].ttf")


if __name__ == "__main__":
    unittest.main()
