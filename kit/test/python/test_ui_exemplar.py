"""kit ui exemplar: the PROCESS page is read from the files (the owner's words first, pieces by route with the recipe
that remakes them, the stills with their resolution) and the vault's copy leaves out the git rounds"""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_exemplar", os.path.join(HERE, "..", "..", "ui", "exemplar.py"))
exemplar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exemplar)


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(obj if isinstance(obj, str) else json.dumps(obj))


class TestExemplar(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        s = self.specs = os.path.join(self.root, "ui")
        write(f"{s}/identities/fx.json", {"name": "fx", "tokens": {"bg": "#000000"}, "fonts": {"font": "Oswald"}})
        write(f"{s}/Title.json", {"name": "Title", "identity": "fx", "quality": "hero", "kind": "menu", "focus": "Root.Logo",
                                  "root": {"name": "Root", "children": [{"type": "label", "name": "Logo", "text": "GO", "lettering": True},
                                                                         {"type": "label", "name": "Hint", "text": "press"}]}})
        write(f"{s}/art/fx/w_go.letter.json", {"text": "GO", "style": "flat", "font": "oswald", "size": 200})
        write(f"{s}/Title.judge.json", {"owner": {"score": 90, "words": "love it"}, "score": 50, "judges": 2})
        os.makedirs(f"{s}/refs/fx")
        Image.new("RGB", (1920, 1080)).save(f"{s}/refs/fx/a.png")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_the_page_comes_from_the_files(self):
        text = exemplar.page("Title", self.specs, os.path.join(self.specs, "refs"), with_rounds=False)
        self.assertIn('The owner: 90/100 — "love it"', text)
        self.assertLess(text.index("The owner"), text.index("## 1 The stills"))     # the owner first
        self.assertIn("| `Root.Logo` | `fx/w_go` | letter | golden | text GO; style flat; font oswald; size 200 |", text)
        self.assertIn("(1 small typed text(s)", text)
        self.assertIn("1920x1080", text)
        self.assertIn("the starter's copy carries it", text)                         # no git rounds in the vault copy
        self.assertIsNone(exemplar.page("Nope", self.specs, self.specs))


if __name__ == "__main__":
    unittest.main()
