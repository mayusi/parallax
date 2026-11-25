"""The real-material library (kit/blender/rbx_materials.py, physicallybased.info CC0 data): measured values come
through as material() keywords, polished metals get a machined finish, lookups find what a person types, and the
critic's check catches a material named like a real one that looks nothing like it — without flagging painted parts."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_materials as M  # noqa: E402


class TestLibrary(unittest.TestCase):
    def test_all_86_load_with_values(self):
        lib = M.load()
        self.assertEqual(len(lib), 86)
        for name in lib:
            v = M.real(name)
            self.assertTrue(all(0.0 <= c <= 1.0 for c in v["color"]), name)
            self.assertTrue(0.0 <= v["metal"] <= 1.0 and 0.0 <= v["rough"] <= 1.0, name)

    def test_linear_colours(self):
        self.assertEqual(M.real("Gray Card")["color"], (0.18, 0.18, 0.18))  # middle grey, linear

    def test_metal_gets_a_machined_finish_unless_told(self):
        self.assertEqual(M.real("Brass")["rough"], M.MACHINED)
        self.assertEqual(M.real("Brass", rough=0.6)["rough"], 0.6)
        self.assertEqual(M.real("Tire")["rough"], 0.7)  # a measured roughness is kept

    def test_lookup(self):
        self.assertEqual(M.find("chrome"), ["Chromium"])
        self.assertIn("Tire", M.find("rubber"))
        self.assertEqual(M.real("gold"), M.real("Gold"))
        with self.assertRaises(KeyError):
            M.real("unobtainium")


class TestCheck(unittest.TestCase):
    def test_toy_gold_is_named(self):
        self.assertIsNotNone(M.check("gold", (1.0, 0.85, 0.0), 0.0))  # yellow plastic
        self.assertIsNotNone(M.check("goldPlate", (0.2, 0.2, 0.9), 1.0))  # camelCase name, blue "gold"

    def test_real_values_pass(self):
        for name in ("Gold", "brass", "copper", "chrome", "silver", "aluminium", "tire", "concrete"):
            target = M.promise(name)
            v = M.real(target)
            self.assertIsNone(M.check(name, v["color"], v["metal"]), name)

    def test_named_coverings_are_not_judged(self):
        for name in ("painted_gold", "dark_brass", "worn copper", "gold_trim", "blued_steel", "steel", "rubber"):
            self.assertIsNone(M.check(name, (0.9, 0.1, 0.1), 0.0), name)


if __name__ == "__main__":
    unittest.main()
