"""kit world colorscript: the journey's mood in order; flat neighbours are named."""

import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "world"))
import colorscript  # noqa: E402

DOC = """# {name} — direction

## Pick
pending — my recommendation: A

## Directions
### A — x
Frame: direction/{name}_A.png
"""


class ColourScript(unittest.TestCase):
    def setUp(self):
        from PIL import Image

        self.cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        os.chdir(self.tmp)
        d = os.path.join("games", "G", "assets", "worlds", "direction")
        os.makedirs(d)
        for name, rgb in (("Warm", (200, 150, 90)), ("Warm2", (205, 152, 92)), ("Cold", (90, 110, 160))):
            open(os.path.join(d, f"{name}.md"), "w", encoding="utf-8").write(DOC.format(name=name))
            Image.fromarray(np.full((36, 64, 3), rgb, np.uint8)).save(os.path.join(d, f"{name}_A.png"))

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_flat_pair_is_named_and_a_change_is_not(self):
        out = os.path.join(self.tmp, "cs.png")
        self.assertEqual(colorscript.main(["G", "--order", "Warm,Warm2,Cold", "--out", out]), 0)
        self.assertTrue(os.path.isfile(out))
        import io, contextlib, json
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            colorscript.main(["G", "--order", "Warm,Warm2,Cold", "--out", out])
        r = json.loads(buf.getvalue().strip().splitlines()[-1])
        self.assertEqual(r["flat"], ["Warm -> Warm2"])

    def test_the_recommendation_is_used_until_a_pick(self):
        path, letter, picked = colorscript.chosen_frame(os.path.join("games", "G", "assets", "worlds", "direction", "Cold.md"))
        self.assertEqual((letter, picked), ("A", False))
        self.assertTrue(path.endswith("Cold_A.png"))


if __name__ == "__main__":
    unittest.main()
