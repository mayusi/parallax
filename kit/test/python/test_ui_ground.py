"""kit ui ground: an identity's game frame is cropped to cover 1920x1080, kept outside the art (never uploaded), with
where it came from; the preview finds it before the old art world.png"""
import importlib.util
import json
import os
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_ground", os.path.join(HERE, "..", "..", "ui", "ground.py"))
ground = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ground)


class TestGround(unittest.TestCase):
    def test_a_world_look_becomes_the_identity_ground(self):
        with tempfile.TemporaryDirectory() as d:
            ui = os.path.join(d, "ui")
            os.makedirs(os.path.join(ui, "identities"))
            with open(os.path.join(ui, "identities", "zz.json"), "w") as fh:
                json.dump({}, fh)
            look = os.path.join(d, "look", "Arena")
            os.makedirs(look)
            Image.new("RGB", (960, 600), (10, 120, 30)).save(os.path.join(look, "eye_2.png"))
            rc = ground.main(["zz", "--world", "Arena", "--view", "eye_2", "--ui", ui, "--worlds-look", os.path.join(d, "look")])
            self.assertEqual(rc, 0)
            with Image.open(os.path.join(ui, "grounds", "zz.png")) as out:
                self.assertEqual(out.size, (1920, 1080))                      # (cropped to cover, not stretched)
            with open(os.path.join(ui, "grounds", "zz.json"), encoding="utf-8") as fh:
                side = json.load(fh)
            self.assertEqual(side["world"], "Arena")
            self.assertFalse(os.path.isdir(os.path.join(ui, "art")))           # (never in the uploaded art)
            self.assertEqual(ground.main(["nobody", "--world", "Arena", "--ui", ui]), 1)


if __name__ == "__main__":
    unittest.main()
