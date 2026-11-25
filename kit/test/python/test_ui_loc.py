"""kit ui loc: a pseudo-translation is accented, 40% longer and bracketed (numbers left alone); a picture with a
letter sidecar is listed as a word that will not translate"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ui"))
_spec = importlib.util.spec_from_file_location("kit_ui_loc", os.path.join(HERE, "..", "..", "ui", "loc.py"))
loc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(loc)


class TestLoc(unittest.TestCase):
    def test_pseudo_and_lettered(self):
        p = loc.pseudo("Close")
        self.assertTrue(p.startswith("[") and p.endswith("]"))
        self.assertIn("Ç", p)
        self.assertGreaterEqual(len(p), len("Close") * 1.4)
        self.assertEqual(loc.pseudo("1,250"), "1,250")                       # (numbers are universal)
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "art", "zz"))
            with open(os.path.join(d, "art", "zz", "w_go.letter.json"), "w", encoding="utf-8") as fh:
                json.dump({"text": "GO!"}, fh)
            model = {"Children": [{"Name": "Hud", "ClassName": "Frame", "Children": [
                {"Name": "Word", "ClassName": "ImageLabel", "Properties": {"Attributes": {"Attributes": {"KitArt": {"String": "zz/w_go"}}}}},
                {"Name": "Icon", "ClassName": "ImageLabel", "Properties": {"Attributes": {"Attributes": {"KitArt": {"String": "zz/icon"}}}}}]}]}
            self.assertEqual(loc.lettered(model, d), [("Hud.Word", "zz/w_go", "GO!")])


class TestExport(unittest.TestCase):
    def test_every_text_and_lettered_word_lands_in_the_csv(self):
        import csv
        with tempfile.TemporaryDirectory() as d:
            models = os.path.join(d, "m")
            os.makedirs(models)
            os.makedirs(os.path.join(d, "art", "zz"))
            with open(os.path.join(d, "art", "zz", "w_go.letter.json"), "w", encoding="utf-8") as fh:
                json.dump({"text": "GO!"}, fh)
            model = {"ClassName": "ScreenGui", "Children": [{"Name": "Hud", "ClassName": "Frame", "Children": [
                {"Name": "Title", "ClassName": "TextLabel", "Properties": {"Text": "Shop"}},
                {"Name": "Count", "ClassName": "TextLabel", "Properties": {"Text": "1,250"}},
                {"Name": "Word", "ClassName": "ImageLabel", "Properties": {"Attributes": {"Attributes": {"KitArt": {"String": "zz/w_go"}}}}}]}]}
            with open(os.path.join(models, "S.model.json"), "w", encoding="utf-8") as fh:
                json.dump(model, fh)
            out = os.path.join(d, "loc.csv")
            loc.export(models, d, out)
            with open(out, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        self.assertEqual([r["Source"] for r in rows], ["Shop", "GO!"])          # (numbers are universal: left out)
        self.assertIn("LETTERED", rows[1]["Context"])
        self.assertEqual(list(rows[0].keys()), ["Key", "Context", "Example", "Source", "en"])


if __name__ == "__main__":
    unittest.main()
