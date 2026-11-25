"""kit ui rate: the owner's one-key rating page shows the engine / preview / verifier pictures and records through
`kit verdict screen <Screen> <score> "<words>"` (a stub stands in for lune here)"""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_rate", os.path.join(HERE, "..", "..", "ui", "rate.py"))
rate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rate)


class TestRate(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "booth"))
        Image.new("RGB", (8, 8)).save(os.path.join(self.root, "S.png"))
        Image.new("RGB", (8, 8)).save(os.path.join(self.root, "booth", "S_engine.png"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_the_page_shows_the_pictures_and_eleven_keys(self):
        html = rate.page("S", self.root)
        self.assertIn("the engine (Studio)", html)
        self.assertIn("the preview", html)
        self.assertEqual(html.count("data:image/png;base64,"), 2)
        self.assertEqual(html.count("onclick=\"go("), 11)          # 0..10

    def test_a_rating_goes_through_kit_verdict(self):
        stub = os.path.join(self.root, "stub.py")
        with open(stub, "w", encoding="utf-8") as fh:
            fh.write("import sys\nprint('summary: verdict ' + ' | '.join(sys.argv[1:]))\n")
        ok, said = rate.record("S", 8, "  sharp  ", [sys.executable, stub])
        self.assertTrue(ok)
        self.assertEqual(said, "summary: verdict verdict | screen | S | 8 | sharp")
        ok, said = rate.record("S", 3, "", [sys.executable, stub])
        self.assertIn("(rated by key, no words)", said)
        ok, said = rate.record("S", 3, "--tag evil", [sys.executable, stub])   # (words are never read as a flag)
        self.assertTrue(said.endswith("| (tag evil)"), said)
        self.assertIn('name="token" value="abc"', rate.page("S", self.root, "abc"))


if __name__ == "__main__":
    unittest.main()
