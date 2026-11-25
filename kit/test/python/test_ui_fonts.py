"""kit/ui/fonts.py: every Roblox Enum.Font maps to a family in the manifest, every pinned (fetched) face loads in
Pillow at the weight the manifest asks for, and the preview draws Garamond with the real serif, not Segoe UI."""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.join(HERE, "..", "..", "ui")
sys.path.insert(0, UI)

# loaded under its own name: the kit's tests share one process and other modules may be called `fonts`
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("kit_ui_fonts", os.path.join(UI, "fonts.py"))
fonts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fonts)

ROBLOX_FONTS = [
    "Legacy", "Arial", "ArialBold", "SourceSans", "SourceSansBold", "SourceSansLight", "SourceSansItalic", "Bodoni",
    "Garamond", "Cartoon", "Code", "Highway", "SciFi", "Arcade", "Fantasy", "Antique", "SourceSansSemibold", "Gotham",
    "GothamMedium", "GothamBold", "GothamBlack", "AmaticSC", "Bangers", "Creepster", "DenkOne", "Fondamento",
    "FredokaOne", "GrenzeGotisch", "IndieFlower", "JosefinSans", "Jura", "Kalam", "LuckiestGuy", "Merriweather",
    "Michroma", "Nunito", "Oswald", "PatrickHand", "PermanentMarker", "Roboto", "RobotoCondensed", "RobotoMono",
    "Sarpanch", "SpecialElite", "TitilliumWeb", "Ubuntu", "BuilderSans", "BuilderSansMedium", "BuilderSansBold",
    "BuilderSansExtraBold", "Arimo", "ArimoBold",
]


class TestManifest(unittest.TestCase):
    def test_every_roblox_font_has_a_family_in_an_allowed_licence_folder(self):
        m = fonts.manifest()
        for name in ROBLOX_FONTS:
            self.assertIn(name, m["fonts"], f"{name} missing from fonts.json")
            fam = m["families"][m["fonts"][name]["family"]]
            if not fam.get("system"):
                self.assertIn(fam["licence"], ("ofl", "apache", "ufl"), name)

    def test_stand_ins_are_declared_not_silent(self):
        m = fonts.manifest()
        for name in ("Gotham", "GothamBold", "BuilderSans", "Garamond", "Bodoni", "SciFi"):
            self.assertTrue(m["fonts"][name].get("approx"), f"{name} is drawn with a twin: fonts.json must say approx")

    def test_wanted_files_prefers_variable_fonts_else_the_static_set(self):
        self.assertEqual(fonts.wanted_files({"X[wght].ttf": {}, "X-Italic[wght].ttf": {}, "X-Bold.ttf": {}}),
                         ["X[wght].ttf", "X-Italic[wght].ttf"])
        self.assertEqual(sorted(fonts.wanted_files({"X-Regular.ttf": {}, "X-Bold.ttf": {}, "X-Thin.ttf": {}})),
                         ["X-Bold.ttf", "X-Regular.ttf"])


class TestPinnedFacesLoad(unittest.TestCase):
    def test_every_pinned_family_loads_at_its_weight(self):
        from PIL import ImageFont
        lock = fonts.pins()
        m = fonts.manifest()
        checked = 0
        for name, entry in m["fonts"].items():
            fam = m["families"].get(entry["family"], {})
            if fam.get("system") or fam.get("folder") not in lock:
                continue
            r = fonts.resolve(name)
            if r is None:  # pinned in the kit but not fetched on this machine: not provable here
                continue
            f = ImageFont.truetype(r["path"], 32)
            if r["variable"]:
                values = []
                for axis in f.get_variation_axes():  # (the weight axis by NAME: Fredoka is [wdth, wght])
                    tag = axis.get("name", b"")
                    tag = tag.decode("latin-1") if isinstance(tag, bytes) else str(tag)
                    if tag.lower() in ("weight", "wght"):
                        values.append(min(max(r["weight"], axis["minimum"]), axis["maximum"]))
                    else:
                        values.append(axis["default"])
                f.set_variation_by_axes(values)
            self.assertGreater(f.getlength("Souls"), 0, name)
            checked += 1
        if checked == 0:
            self.skipTest("no pinned family is fetched on this machine (lune run kit ui fonts) — nothing to prove here")

    def test_garamond_draws_a_real_serif_when_cached(self):
        r = fonts.resolve("Garamond")
        if r is None:
            self.skipTest("EB Garamond not fetched on this machine (python kit/ui/fonts.py fetch ebgaramond)")
        from PIL import ImageFont
        self.assertEqual(ImageFont.truetype(r["path"], 24).getname()[0], "EB Garamond")
        self.assertTrue(r["approx"], "Roblox's Garamond is the Guru face: the twin must be declared approximate")


if __name__ == "__main__":
    unittest.main()
