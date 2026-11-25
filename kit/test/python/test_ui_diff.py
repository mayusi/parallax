"""kit ui diff: an approved golden + an unchanged frame match; a moved piece is reported with its region"""
import importlib.util
import json
import os
import tempfile
import unittest

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_diff", os.path.join(HERE, "..", "..", "ui", "diff.py"))
diff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(diff)


class TestDiff(unittest.TestCase):
    def test_golden_then_a_moved_piece(self):
        with tempfile.TemporaryDirectory() as d:
            build, lib, models = os.path.join(d, "b"), os.path.join(d, "l"), os.path.join(d, "m")
            os.makedirs(os.path.join(lib, "zz", "screens", "S"))
            os.makedirs(build)
            os.makedirs(models)
            im = Image.new("RGB", (400, 300), (20, 20, 30))
            ImageDraw.Draw(im).rectangle([50, 50, 150, 120], fill=(240, 200, 40))
            im.save(os.path.join(build, "S.desktop.png"))
            args = ["S", "--build", build, "--library", lib, "--models", models]
            self.assertEqual(diff.main(args + ["--approve"]), 0)
            self.assertTrue(os.path.isfile(os.path.join(lib, "zz", "screens", "S", "golden.png")))
            diff.main(["--build", build, "--library", lib])
            rep = json.load(open(os.path.join(build, "diff", "report.json")))
            self.assertEqual((rep["checked"], rep["changed"]), (1, []))            # (unchanged: no report)
            moved = Image.new("RGB", (400, 300), (20, 20, 30))
            ImageDraw.Draw(moved).rectangle([70, 50, 170, 120], fill=(240, 200, 40))
            moved.save(os.path.join(build, "S.desktop.png"))
            diff.main(["--build", build, "--library", lib])
            rep = json.load(open(os.path.join(build, "diff", "report.json")))
            self.assertEqual(len(rep["changed"]), 1)
            regs = rep["changed"][0]["regions"]
            self.assertTrue(any(x <= 55 and x + w >= 65 for x, _, w, _ in regs))    # (where the piece left)
            self.assertTrue(any(x <= 155 and x + w >= 165 for x, _, w, _ in regs))  # (where it arrived)


if __name__ == "__main__":
    unittest.main()
