"""kit ui style: an identity becomes a StyleSheet model — its colour tokens as Color3 attributes, its rules with a
selector, a priority and their properties as JSON that refer to the tokens ($accent), a transition from its hover"""
import importlib.util
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_style", os.path.join(HERE, "..", "..", "ui", "style.py"))
style = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(style)


class TestStyle(unittest.TestCase):
    def test_an_identity_becomes_a_stylesheet(self):
        ident = {"tokens": {"accent": "#ff8000", "text": "#ffffff", "bg": "#000000", "panel": "#111111"},
                 "fonts": {"font": "Oswald", "titleFont": "Bangers"}, "shape": {"radius": 14},
                 "motion": {"hover": {"duration": 0.2}}}
        m = style.build(ident, "zz")
        self.assertEqual(m["ClassName"], "StyleSheet")
        attrs = m["Properties"]["Attributes"]["Attributes"]
        self.assertEqual(attrs["accent"]["Color3"], [1.0, 128 / 255, 0.0])
        self.assertEqual(attrs["Kit_Style"]["String"], "zz")
        rules = {c["Name"]: c for c in m["Children"]}
        self.assertTrue(all(c["ClassName"] == "StyleRule" for c in m["Children"]))
        prim = json.loads(rules["Primary"]["Properties"]["Attributes"]["Attributes"]["Kit_Props"]["String"])
        self.assertEqual(prim["BackgroundColor3"], "$accent")                  # (a token reference, not a copy)
        self.assertEqual(rules["Primary"]["Properties"]["Selector"], ".KitPrimary")
        self.assertEqual(rules["Primary"]["Properties"]["Attributes"]["Attributes"]["Kit_Transition"]["String"], "0.2,Quad,Out")
        title = json.loads(rules["Title"]["Properties"]["Attributes"]["Attributes"]["Kit_Props"]["String"])
        self.assertEqual(title["Font"], {"Enum": "Font", "Name": "Bangers"})
        corners = json.loads(rules["Corners"]["Properties"]["Attributes"]["Attributes"]["Kit_Props"]["String"])
        self.assertEqual(corners["CornerRadius"], {"UDim": [0, 14]})


if __name__ == "__main__":
    unittest.main()
