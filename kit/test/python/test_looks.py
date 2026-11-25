"""rbx.look — real surfaces' whole recipes (kit/materials/looks.json): every look resolves, passes the strict PBR rules,
names a real pattern and a pinned scan, says where its numbers come from, and takes overrides."""

import json
import os
import re
import sys
import unittest

KIT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, os.path.join(KIT, "blender"))
import rbx_looks as L  # noqa: E402
import rbx_pbr as P  # noqa: E402


def _patterns():
    with open(os.path.join(KIT, "blender", "rbx.py"), encoding="utf-8") as fh:
        text = fh.read()
    block = re.search(r"^PATTERNS = \(([^)]*)\)", text, re.MULTILINE).group(1)
    return set(re.findall(r'"(\w+)"', block))


class Looks(unittest.TestCase):
    def test_every_look_is_physically_based_and_sourced(self):
        names = [n for n, _a, _s in L.looks()]
        self.assertGreaterEqual(len(names), 25)
        for name, about, source in L.looks():
            kw = L.look(name)
            self.assertEqual(P.judge(name, kw["color"], kw["metal"], kw["rough"], strict=True), [], name)
            self.assertIn(kw["metal"], (0.0, 1.0), name)
            self.assertTrue(about and source, name)   # (what it is, and where its numbers come from)
            self.assertTrue(0.0 <= kw.get("vary", 0.0) <= 1.0, name)

    def test_patterns_are_the_kits(self):
        known = _patterns()
        for name, _a, _s in L.looks():
            pat = L.look(name).get("pattern")
            if pat:
                self.assertIn(pat, known, name)

    def test_scans_are_pinned(self):
        pins = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "materials", "pins.json")
        if not os.path.isfile(pins):
            self.skipTest("no scan cache on this machine")
        with open(pins, encoding="utf-8") as fh:
            pinned = set(json.load(fh))
        for name, _a, _s in L.looks():
            scan = L.look(name).get("scan")
            if scan:
                self.assertIn(scan, pinned, name)

    def test_a_finish_rides_along_for_life(self):
        kw = L.look("nitride_slide")
        self.assertEqual(kw["finish"], "nitride")
        self.assertEqual(P.life_class(kw["color"], kw["metal"], kw["rough"], finish=kw["finish"]), "coating")
        oak = L.look("oak_wood")
        self.assertNotIn("finish", oak)
        self.assertEqual(P.life_class(oak["color"], oak["metal"], oak["rough"]), "dielectric")

    def test_overrides_and_errors(self):
        red = L.look("powder_coat", color=(0.3, 0.05, 0.04), rough=0.4)
        self.assertEqual((red["color"], red["rough"]), ((0.3, 0.05, 0.04), 0.4))
        self.assertEqual(red["pattern"], "coat")   # (the rest of the look kept)
        with self.assertRaises(KeyError):
            L.look("unobtainium")
        with self.assertRaises(TypeError):
            L.look("oak_wood", life="used")   # (life is a.material's, not the look's)


if __name__ == "__main__":
    unittest.main()
