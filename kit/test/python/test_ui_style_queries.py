"""kit ui style: an identity's breakpoints ("queries") exported as StyleQuery + "@Name" StyleRules (LIMITATIONS_FIXES_V4
UI-X, v7), and the export REFUSING a query the engine would silently ignore (an unknown condition, a malformed size,
an impossible min/max, an input that is not an Enum.PreferredInput, a query with no rules)."""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
FIX = os.path.join(ROOT, "kit", "selftest", "ui", "style_queries")
sys.path.insert(0, os.path.join(ROOT, "kit", "ui"))
import style  # noqa: E402

GOOD_Q = {"Phone": {"when": {"MaxSize": [900, 500]}, "rules": {".KitTitle": {"TextSize": 28}}},
          "Pad": {"when": {"PreferredInput": "Gamepad", "AspectRatioRange": [1.2, 2.5]}, "rules": {"UIStroke": {"Thickness": 3}}}}


class Queries(unittest.TestCase):
    def test_good_queries_export_as_a_query_and_a_scoped_rule(self):
        self.assertEqual(style.query_problems({"queries": GOOD_Q}), [])
        model = style.build({"tokens": {"text": "#ffffff"}, "queries": GOOD_Q}, "t")
        by = {c["Name"]: c for c in model["Children"]}
        q = by["Phone"]
        self.assertEqual(q["ClassName"], "StyleQuery")
        self.assertEqual(json.loads(q["Properties"]["Attributes"]["Attributes"]["Kit_Conditions"]["String"]), {"MaxSize": [900, 500]})
        at = by["AtPhone"]
        self.assertEqual(at["Properties"]["Selector"], "@Phone")
        inner = at["Children"][0]
        self.assertEqual(inner["Properties"]["Selector"], ".KitTitle")
        self.assertEqual(json.loads(inner["Properties"]["Attributes"]["Attributes"]["Kit_Props"]["String"]), {"TextSize": 28})

    def test_an_identity_without_queries_exports_as_before(self):
        self.assertEqual(style.query_problems({}), [])
        names = [c["ClassName"] for c in style.build({"tokens": {}}, "t")["Children"]]
        self.assertNotIn("StyleQuery", names)

    def test_each_bad_query_is_named(self):
        bad = style.query_problems({"queries": {
            "Wide": {"when": {"Width": 900}, "rules": {"Frame": {"Visible": False}}},
            "Tiny": {"when": {"MaxSize": [900]}, "rules": {"Frame": {"Visible": False}}},
            "Never": {"when": {"MinSize": [1000, 800], "MaxSize": [900, 500]}, "rules": {"Frame": {"Visible": False}}},
            "Mouse": {"when": {"PreferredInput": "Mouse"}, "rules": {"Frame": {"Visible": False}}},
            "Empty": {"when": {"MaxSize": [900, 500]}, "rules": {}},
            "Ratio": {"when": {"AspectRatioRange": [2, 1]}, "rules": {"Frame": {"Visible": False}}},
        }})
        text = "\n".join(bad)
        for words in ('"Width" is not a StyleQuery condition', "MaxSize is [width, height]", "can never be active",
                      "PreferredInput is one of", "a query with no rules styles nothing", "AspectRatioRange is [low, high]"):
            self.assertIn(words, text)

    def test_the_selftest_fixture_fails_the_export_and_its_control_passes(self):
        out = tempfile.mkdtemp()
        try:
            self.assertEqual(style.main(["bad_queries", "--ui", FIX, "--out", out]), 1)
            self.assertFalse(os.path.isfile(os.path.join(out, "bad_queries.model.json")))
            self.assertEqual(style.main(["good_queries", "--ui", FIX, "--out", out]), 0)
            self.assertTrue(os.path.isfile(os.path.join(out, "good_queries.model.json")))
        finally:
            shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
