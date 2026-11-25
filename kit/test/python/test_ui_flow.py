"""kit ui flow: a flow is checked against its compiled screens — real screens, a button to press, shared pieces that
exist, and a way back to the start (a screen the player cannot leave is a trap)"""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ui"))
_spec = importlib.util.spec_from_file_location("kit_ui_flow", os.path.join(HERE, "..", "..", "ui", "flow.py"))
flow = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(flow)


def screen(root, kids):
    return {"ClassName": "ScreenGui", "Children": [{"Name": root, "ClassName": "Frame", "Children": kids}]}


HUD = screen("Hud", [{"Name": "Shop", "ClassName": "TextButton", "Children": [{"Name": "Icon", "ClassName": "ImageLabel"}]},
                     {"Name": "Note", "ClassName": "TextLabel"}])
SHOP = screen("Shop", [{"Name": "Close", "ClassName": "ImageButton"}, {"Name": "Cart", "ClassName": "ImageLabel"}])


class TestFlow(unittest.TestCase):
    def test_a_good_flow_passes_and_a_trap_does_not(self):
        models = {"Hud": HUD, "Shop": SHOP}
        good = {"start": "Hud", "steps": [
            {"from": "Hud", "to": "Shop", "on": "Hud.Shop", "transition": "shared", "shared": {"from": "Hud.Shop.Icon", "to": "Shop.Cart"}},
            {"from": "Shop", "to": "Hud", "on": "Shop.Close", "transition": "fade"}]}
        self.assertEqual(flow.check(good, models), [])
        trap = {"start": "Hud", "steps": [{"from": "Hud", "to": "Shop", "on": "Hud.Shop"}]}
        self.assertTrue(any("no way back" in b for b in flow.check(trap, models)))
        bad = {"start": "Hud", "steps": [
            {"from": "Hud", "to": "Shop", "on": "Hud.Note", "transition": "wipe"},
            {"from": "Shop", "to": "Hud", "on": "Shop.Gone", "transition": "shared", "shared": {"from": "Shop.X", "to": "Hud.Y"}}]}
        probs = " | ".join(flow.check(bad, models))
        self.assertIn("not a button", probs)
        self.assertIn("is not one of", probs)
        self.assertIn("no node 'Shop.Gone'", probs)
        self.assertIn("shared.from", probs)


if __name__ == "__main__":
    unittest.main()
