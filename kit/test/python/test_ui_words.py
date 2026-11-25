"""kit ui words: the lettering step bakes what specs ask for, by a name the compiler also derives"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WORDS = os.path.join(HERE, "..", "..", "ui", "words.py")
_spec = importlib.util.spec_from_file_location("kit_ui_words", WORDS)
words = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(words)


class TestWords(unittest.TestCase):
    def test_slug_matches_the_compiler(self):
        # kit/lib/ui.luau: lower, runs of non-alphanumerics to "_", trimmed, 40 chars, "w_" prefix
        self.assertEqual(words.slug("NEW GAME"), "w_new_game")
        self.assertEqual(words.slug("  Press Any Button!! "), "w_press_any_button")
        self.assertEqual(words.slug("!!!"), "w_word")

    def test_recipe_merges_identity_defaults_node_overrides_and_tokens(self):
        node = {"text": "QUIT", "textSize": 50, "lettering": {"seed": 4, "shadow_color": "accent"}}
        rec = words.recipe(node, {"style": "persona", "outline": 0.07, "seed": 9}, {"accent": "#a24dff"})
        self.assertEqual(rec["seed"], 4)
        self.assertEqual(rec["outline"], 0.07)
        self.assertEqual(rec["size"], 50)
        self.assertEqual(rec["shadow_color"], "#a24dff")

    def test_two_recipes_for_one_name_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            ui = os.path.join(d, "ui")
            os.makedirs(os.path.join(ui, "identities"))
            json.dump({"name": "x", "tokens": {}}, open(os.path.join(ui, "identities", "x.json"), "w"))
            root = {"type": "panel", "name": "R", "children": [
                {"type": "label", "name": "A", "text": "GO", "lettering": {"seed": 1}},
                {"type": "label", "name": "B", "text": "GO", "lettering": {"seed": 2}}]}
            json.dump({"name": "S", "identity": "x", "root": root}, open(os.path.join(ui, "S.json"), "w"))
            r = subprocess.run([sys.executable, WORDS, "--ui", ui, "--art", os.path.join(d, "art")], capture_output=True, text=True)
            out = json.loads(r.stdout.strip().splitlines()[-1])
            self.assertEqual(out["status"], "fail")
            self.assertIn("lettered differently", out["next_action"])


if __name__ == "__main__":
    unittest.main()
