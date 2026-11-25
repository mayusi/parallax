"""kit sfx ambience: a world's zones come from its own blueprint (water ops, forests, stone clusters)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "audio"))
import ambience  # noqa: E402

BP = {
    "terrain": [
        {"heightmap": {"center": [0, 0, 0], "size": [1024, 1024]}},
        {"water": {"center": [200, 10, 200], "size": [280, 6, 240]}},
        {"water": {"center": [0, 0, 0], "size": [5000, 6, 5000], "backdrop": True}},
    ],
    "build": [
        {"forest": {"name": "Woods", "center": [-300, 0, -100], "area": [260, 200]}},
        {"wall": {"name": "WallN", "from": [0, -350], "to": [120, -350]}},
        {"tower": {"name": "TowerNW", "center": [0, 0, -350], "radius": 9}},
        {"building": {"name": "Keep", "center": [60, 0, -318], "size": [44, 30]}},
        {"ruin": {"name": "Chapel", "center": [-265, 0, 40], "size": [44, 30]}},
        {"scatter": {"name": "Rocks", "center": [0, 0, 0]}},
    ],
}


class Zones(unittest.TestCase):
    def test_water_forest_and_stone_clusters_come_from_the_blueprint(self):
        zs = ambience.zones(BP)
        kinds = sorted(z["kind"] for z in zs)
        self.assertEqual(kinds, ["forest", "stone", "stone", "water"])  # (the backdrop sea is not a zone)
        water = next(z for z in zs if z["kind"] == "water")
        self.assertEqual((water["x"], water["z"], water["r"]), (200, 200, 140.0))
        forest = next(z for z in zs if z["kind"] == "forest")
        self.assertEqual(forest["r"], 130.0)

    def test_a_castle_is_one_stone_zone_named_after_its_keep(self):
        stones = [z for z in ambience.zones(BP) if z["kind"] == "stone"]
        castle = next(z for z in stones if z["name"].startswith("Keep"))
        self.assertEqual(castle["name"], "Keep+2")  # (the keep, its wall and its tower: one cluster)
        self.assertTrue(-360 < castle["z"] < -300)
        self.assertGreater(castle["r"], 50)
        self.assertTrue(any(z["name"] == "Chapel" for z in stones))  # (300 studs away: its own zone)


if __name__ == "__main__":
    unittest.main()


class GameRoot(unittest.TestCase):
    def test_kit_game_none_is_the_project_root_never_the_active_game(self):
        import tempfile

        old_cwd, old_env = os.getcwd(), os.environ.get("KIT_GAME")
        tmp = tempfile.mkdtemp()
        try:
            os.chdir(tmp)
            os.makedirs(os.path.join("games", "Other"))
            with open(os.path.join("games", ".active"), "w", encoding="utf-8") as fh:
                fh.write("Other")
            os.environ["KIT_GAME"] = "none"
            self.assertEqual(ambience.game_root(), ".")
            os.environ.pop("KIT_GAME")
            self.assertEqual(ambience.game_root(), os.path.join("games", "Other"))  # (unset: the active game)
        finally:
            os.chdir(old_cwd)
            if old_env is None:
                os.environ.pop("KIT_GAME", None)
            else:
                os.environ["KIT_GAME"] = old_env
