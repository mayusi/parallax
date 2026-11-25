"""kit ui fuzz: words grow 60%, numbers go to 9,999,999, a tracked glyph and a rank letter are left alone, a digit-set
number too narrow for a wider value is reported"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ui"))
_spec = importlib.util.spec_from_file_location("kit_ui_fuzz", os.path.join(HERE, "..", "..", "ui", "fuzz.py"))
fuzz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fuzz)


def node(name, cls, text=None, attrs=None, kids=()):
    p = {"Attributes": {"Attributes": attrs or {}}}
    if text is not None:
        p["Text"] = text
    return {"Name": name, "ClassName": cls, "Properties": p, "Children": list(kids)}


class TestFuzz(unittest.TestCase):
    def test_edge_data(self):
        self.assertEqual(fuzz.stretch("COINS"), "COINS COI")
        self.assertEqual(fuzz.stretch("1,250"), "9,999,999")
        score = node("Score", "Frame", attrs={"Kit_Digits": {"String": "x"}, "Kit_Number": {"String": "46959"}},
                     kids=[node(f"C{i}", "ImageLabel") for i in range(1, 6)])
        rank = node("Rank", "Frame", attrs={"Kit_Digits": {"String": "x"}, "Kit_Number": {"String": "B"}}, kids=[node("C1", "ImageLabel")])
        model = {"Children": [node("Hud", "Frame", kids=[node("Title", "TextLabel", "SHOP"), node("G1", "TextLabel", "Y"), score, rank])]}
        m, narrow = fuzz.edge(model, "long")
        hud = m["Children"][0]["Children"]
        self.assertEqual(hud[0]["Properties"]["Text"], "SHOP SH")
        self.assertEqual(hud[1]["Properties"]["Text"], "Y")                    # (a tracked glyph does not grow)
        _, narrow = fuzz.edge(model, "max")
        self.assertEqual([p for p, _ in narrow], ["Hud.Score"])               # (the rank letter is not a number)


if __name__ == "__main__":
    unittest.main()
