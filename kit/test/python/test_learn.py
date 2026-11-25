"""kit learn: the kit's knowledge from dissected reference models (kit/refs/learn.py). Each model counts once, a part's
role comes from its name's words (and can be fixed), material classes, compare names a build's gaps."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "refs"))
import learn  # noqa: E402


def part(name, bevel=None, share=None, colour=None, metal=None, kind="block"):
    p = {"name": name, "kind": kind, "edges": {}, "material": [{}]}
    if bevel is not None:
        p["edges"] = {"bevel_size_mm": {"typical": bevel}, "bevel_mm": 10.0, "bevelled_share": share, "sharp_mm": 2.0}
    if colour is not None:
        p["colour_wear"] = {"colour_mean": colour}
    if metal is not None:
        p["material"] = [{"metallic": metal}]
    return p


class TestLearn(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old, learn.STORE = learn.STORE, os.path.join(self.tmp, "learned")

    def tearDown(self):
        learn.STORE = self.old

    def write(self, name, parts):
        p = os.path.join(self.tmp, f"{name}.inspect.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"name": name, "source": "", "parts": parts}, fh)
        return p

    def test_each_model_counts_once(self):
        learn.add(self.write("many", [part(f"Slide{i}", bevel=1.0, share=0.9) for i in range(10)]), "firearm")
        learn.add(self.write("one", [part("Slide", bevel=3.0, share=0.9)]), "firearm")
        r = learn.rng(learn._load("firearm")["samples"]["bevel_size_mm"]["role:slide"])
        self.assertEqual((r["low"], r["high"], r["models"], r["parts"]), (1.0, 3.0, 2, 11))
        self.assertEqual(learn.learned("firearm", "bevel_size_mm", "role:slide", "high"), 3.0)

    def test_adding_again_replaces_and_remove_forgets(self):
        path = self.write("m", [part("Grip", bevel=0.5, share=0.5)])
        learn.add(path, "firearm")
        learn.add(path, "firearm")
        self.assertEqual(learn.rng(learn._load("firearm")["samples"]["bevel_size_mm"]["all"])["parts"], 1)
        data = learn._load("firearm")
        learn.remove_model(data, "m")
        self.assertEqual(data["models"], {})
        self.assertEqual(data["samples"]["bevel_size_mm"], {})

    def test_roles_from_names_and_fixes(self):
        self.assertEqual(learn.role("Magazine_spring1_Magazine_spring_blinn_0"), "spring")
        self.assertEqual(learn.role("Grip_Screw_left_bot_gripscrewleftb"), "screw")
        self.assertEqual(learn.role("Base_Frame_Base_Frame1_0"), "frame")
        self.assertIsNone(learn.role("pCylinder1_lambert1_0"))
        self.assertEqual(learn.role("Trigger1_Trigger_blinn_0", {"Trigger1_Trigger_blinn_0": "hammer"}), "hammer")

    def test_material_classes(self):
        self.assertEqual(learn.material_class(part("g", colour=[0.596, 0.317, 0.171])), "wood")
        self.assertEqual(learn.material_class(part("f", colour=[0.165, 0.165, 0.165])), "dark_metal")
        self.assertEqual(learn.material_class(part("b", colour=[0.6, 0.62, 0.62], metal=0.9)), "bright_metal")
        self.assertEqual(learn.material_class(part("p", colour=[0.1, 0.1, 0.1], metal=0.0)), "polymer")

    def test_compare_names_the_gap(self):
        learn.add(self.write("a", [part("Frame", bevel=1.0, share=0.9)]), "firearm")
        learn.add(self.write("b", [part("Frame", bevel=1.2, share=0.95)]), "firearm")
        gaps, rows = learn.compare(self.write("ours", [part("Frame", bevel=1.1, share=0.1)]), "firearm")
        flagged = {(m, g, side) for _, m, g, side, *_ in gaps}
        self.assertIn(("bevelled_share", "role:frame", "below"), flagged)
        self.assertNotIn(("bevel_size_mm", "role:frame", "below"), flagged)  # 1.1 mm is inside 1.0..1.2
        self.assertTrue(any("bevelled_share" in r for r in rows))


if __name__ == "__main__":
    unittest.main()
