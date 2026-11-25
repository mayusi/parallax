"""kit refs dims: real dimensions with their sources (kit/refs/dims.py) — offline: an infobox parsed from recorded
wikitext (a weapon's and a cartridge's), quantities in their units, rows kept once, disagreements flagged, a dissected
model's parts as low-trust rows."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "refs"))
import dims  # noqa: E402

WEAPON = """{{Short description|x}}
{{Infobox weapon
| name   = Automatic Pistol, Caliber .45, M1911
| wars   = {{plainlist|
*[[World War I]]
*[[World War II]]}}
| weight = {{convert|2.44|lb|kg|abbr=on}} unloaded, with magazine
| length = {{convert|8.5|in|mm|abbr=on}}
| part_length = 5.03 in (127 mm) (Government)
| cartridge = [[.45 ACP]]
}}
Body text {{convert|9|in}} that is not the infobox."""

CARTRIDGE = """{{Infobox firearm cartridge
|name= .45 ACP
|bullet= .452
|rim_dia= .480
|case_length= .898 <!-- SAAMI -->
|length= 1.275
}}"""


class TestDims(unittest.TestCase):
    def setUp(self):
        self.old, dims.STORE = dims.STORE, os.path.join(tempfile.mkdtemp(), "real_specs")

    def tearDown(self):
        dims.STORE = self.old

    def test_weapon_infobox(self):
        name, fields = dims.infobox(WEAPON)
        self.assertEqual(name, "infobox weapon")
        self.assertIn("World War II", fields["wars"])  # a nested template stays one field
        rows = {(r["part"], r["dim"]): r for r in dims.from_wikipedia("M1911 pistol", "colt m1911", wikitext=WEAPON)}
        self.assertAlmostEqual(rows[("overall", "length")]["value"], 215.9, places=1)
        self.assertAlmostEqual(rows[("barrel", "length")]["value"], 127.762, places=2)
        self.assertAlmostEqual(rows[("overall", "mass")]["value"], 1.1068, places=3)
        self.assertEqual(rows[("overall", "mass")]["unit"], "kg")

    def test_cartridge_infobox_is_inches(self):
        rows = {(r["part"], r["dim"]): r["value"] for r in dims.from_wikipedia(".45 ACP", ".45 acp", wikitext=CARTRIDGE)}
        self.assertAlmostEqual(rows[("bullet", "diameter")], 11.481, places=2)
        self.assertAlmostEqual(rows[("case", "length")], 22.809, places=2)   # the comment after it is ignored
        self.assertAlmostEqual(rows[("overall", "length")], 32.385, places=2)

    def test_a_metric_cartridge_infobox_is_millimetres(self):
        # 5.56x45mm NATO's infobox gives bare millimetres: read as inches they came out x25.4 (the ARP's dims)
        metric = ("{{Infobox firearm cartridge\n| name = 5.56x45mm NATO\n| bullet = 5.70\n| neck = 6.43\n"
                  "| base = 9.58\n| rim_dia = 9.60\n| case_length = 44.70\n| length = 57.40\n}}")
        rows = {(r["part"], r["dim"]): r["value"] for r in dims.from_wikipedia("5.56x45mm NATO", "5.56", wikitext=metric)}
        self.assertAlmostEqual(rows[("bullet", "diameter")], 5.70, places=2)
        self.assertAlmostEqual(rows[("case", "length")], 44.70, places=2)
        self.assertAlmostEqual(rows[("overall", "length")], 57.40, places=2)

    def test_rows_kept_once_and_disagreements_flagged(self):
        a = {"object": "Colt M1911", "part": "overall", "dim": "length", "value": 215.9, "unit": "mm", "source": "w1",
             "kind": "wikipedia"}
        self.assertEqual(len(dims.add_rows([a, a])), 1)
        dims.add_rows([dict(a, value=216.0, source="w2", kind="wikidata"),
                       dict(a, part="barrel", value=127.0, source="w1"), dict(a, part="barrel", value=101.6, source="w3")])
        groups = {g["part"]: g for g in dims.find("m1911")}
        self.assertFalse(groups["overall"]["conflict"])  # 215.9 vs 216: 0.05%
        self.assertTrue(groups["barrel"]["conflict"])    # 127 vs 101.6: 25%
        self.assertEqual({r["trust"] for r in groups["overall"]["rows"]}, {"medium"})

    def test_a_dissected_model_gives_low_trust_part_rows(self):
        path = os.path.join(tempfile.mkdtemp(), "m.inspect.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"name": "m", "source": "lib/m.glb", "parts": [
                {"name": "Grip_Safety_x", "own_mm": [46.8, 31.6, 17.3], "see_through": [{"d_mm": 3.1}]}]}, fh)
        rows = dims.from_model(path, "colt m1911")
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r["kind"] == "model" for r in rows))
        self.assertEqual(rows[-1]["dim"], "opening 1 diameter")
        self.assertTrue(rows[0]["part"].startswith("safety"))

    def test_quantities(self):
        self.assertEqual(dims.quantity("{{cvt|1.1|kg}}"), (1.1, "kg"))
        self.assertEqual(dims.quantity("about 8.25 in long"), (8.25, "in"))
        self.assertIsNone(dims.quantity("varies"))

    def test_size_words_match_whole_plain_words_as_a_start(self):
        self.assertTrue(dims._has("iso 4762 socket head cap screw m3-0.5", "m3"))
        self.assertFalse(dims._has("iso 4762 socket head cap screw m30-3.5", "m3"))
        self.assertTrue(dims._has("colt m1911 safety (grip_safety)", "safet"))
        self.assertFalse(dims._has("colt m1911 unsafety", "safet"))


if __name__ == "__main__":
    unittest.main()
