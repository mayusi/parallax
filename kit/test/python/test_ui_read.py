"""kit ui read: the geometry and the naming (no model needed) — straight-border snap, band split, roles by convention"""
import importlib.util
import os
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_read", os.path.join(HERE, "..", "..", "ui", "read.py"))
read = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(read)


def scene_with_panel():
    """noisy sand with a dark bordered square (a minimap) at 40..200 and a caption strip under it to 240"""
    rng = np.random.default_rng(3)
    g = (170 + rng.normal(0, 12, (400, 400))).clip(0, 255)
    g[40:200, 40:200] = 80
    g[40, 40:200] = g[199, 40:200] = 230        # the square's top / bottom borders
    g[40:200, 40] = g[40:200, 199] = 230        # its sides
    g[200:240, 40:200] = 60                     # a caption strip
    g[239, 40:200] = 230                        # its bottom rule
    return g.astype(np.uint8)


class TestRead(unittest.TestCase):
    def test_straighten_snaps_a_loose_box_to_the_panel_borders(self):
        box = read.straighten(scene_with_panel(), [10, 10, 260, 300])
        self.assertLessEqual(abs(box[0] - 40), 2)
        self.assertLessEqual(abs(box[1] - 40), 2)
        self.assertLessEqual(abs(box[2] - 200), 3)

    def test_split_bands_separates_a_map_from_its_caption(self):
        parts = read.split_bands(scene_with_panel(), [40, 40, 200, 240])
        self.assertEqual(len(parts), 2)
        self.assertLess(parts[0][3], parts[1][3])

    def test_collage_seam_flags_side_by_side_screens_only(self):
        from PIL import Image
        rng = np.random.default_rng(5)
        left = (120 + rng.normal(0, 30, (270, 300, 3))).clip(0, 255)
        right = (40 + rng.normal(0, 10, (270, 180, 3))).clip(0, 255)
        collage = Image.fromarray(np.concatenate([left, right], axis=1).astype(np.uint8))
        self.assertIsNotNone(read.collage_seam(collage))
        scene = (120 + rng.normal(0, 30, (270, 480, 3))).clip(0, 255)
        scene[200:230, :, :] = 20  # a full-width HUD bar: horizontal lines never count
        self.assertIsNone(read.collage_seam(Image.fromarray(scene.astype(np.uint8))))

    def test_fighting_pieces_are_named_by_shape_and_place(self):
        self.assertEqual(read.fight_role([192, 112, 1728, 143]), "health bars")
        self.assertEqual(read.fight_role([60, 40, 760, 80]), "P1 health bar")
        self.assertEqual(read.fight_role([1160, 40, 1860, 80]), "P2 health bar")
        self.assertEqual(read.fight_role([970, 981, 1705, 1080]), "P2 super / tension gauge")
        self.assertIsNone(read.fight_role([800, 400, 1000, 600]))  # mid-screen: the category decides
        self.assertEqual(read.role("bar", "bottom-right", 600, 60, "fighting"), "P2 super / tension gauge")

    def test_a_draft_ties_each_piece_to_its_nearest_edge(self):
        self.assertEqual(read.place([12, 12, 274, 270]), ([12, 12], "topleft"))
        self.assertEqual(read.place([1631, 935, 1907, 1036]), (["100%-13", "100%-44"], "bottomright"))
        self.assertEqual(read.place([860, 100, 1060, 160]), (["50%", 100], "top"))
        spec = read.draft_spec("X", "field", [
            {"label": "minimap", "looks_like": "map", "box_1080": [12, 12, 274, 270], "size_1080": [262, 258], "colours": [{"hex": "#334455"}]},
            {"label": "interface panel", "looks_like": "panel", "box_1080": [12, 309, 274, 359], "size_1080": [262, 50]},
            {"label": "interface panel", "looks_like": "panel", "box_1080": [12, 409, 274, 459], "size_1080": [262, 50]},
            {"label": "kill feed / notifications", "looks_like": "text", "box_1080": [1600, 80, 1900, 200], "size_1080": [300, 120]}], "x.png")
        kids = spec["root"]["children"]
        self.assertEqual([k["name"] for k in kids], ["Minimap", "InterfacePanel", "InterfacePanel2", "KillFeedNotifications"])
        self.assertEqual(kids[0]["color"], "#334455")
        self.assertEqual(kids[3]["type"], "label")
        self.assertEqual(spec["insets"], "core")

    def test_a_ranking_request_names_its_genre(self):
        self.assertEqual(read.asked_genre("a fighting game screenshot with health bars"), "fighting")
        self.assertEqual(read.asked_genre("the VS screen"), "fighting")
        self.assertEqual(read.asked_genre("a realistic shooter HUD with ammo"), "shooter")
        self.assertIsNone(read.asked_genre("a JRPG pause menu on a canvas"))  # ('canvas' holds 'vs': a word, not a match)
        self.assertEqual(read.asked_genre("a brawl arena HUD"), "fighting")   # (the audit: 'brawl' went unrecognised)
        self.assertEqual(read.asked_genre("a racing HUD with a speedometer"), "racing")
        self.assertIsNone(read.asked_genre("a dogfight flight sim"))

    def test_a_racing_frame_names_its_dial_minimap_and_position(self):
        self.assertIn("racing", read.GENRE_NAMES)
        self.assertEqual(read.role("graphic", "bottom-right", 400, 270, "racing"), "speedometer / tach dial")
        self.assertEqual(read.role("map", "bottom-left", 300, 300, "racing"), "minimap")
        self.assertEqual(read.role("text", "top-left", 500, 90, "racing"), "race position / lap")
        self.assertEqual(read.role("digits", "bottom-right", 300, 90, "shooter"), "weapon / ammo block")  # (other genres unchanged)

    def test_a_menus_repeated_cards_are_found_and_a_lone_box_is_not(self):
        g = np.full((540, 960), 20, np.uint8)
        for y in (60, 200, 340):                      # three equal cards in a column, gold-ish borders
            g[y:y + 110, 100:600] = 35
            g[y, 100:600] = g[y + 109, 100:600] = 220
            g[y:y + 110, 100] = g[y:y + 110, 599] = 220
        g[100:300, 700:900] = 35                      # a lone panel: no repeat
        g[100, 700:900] = g[299, 700:900] = 220
        g[100:300, 700] = g[100:300, 899] = 220
        rows = read.card_rows(g)
        self.assertEqual(sorted(k for _, k, n in rows), [1, 2, 3])
        self.assertTrue(all(n == 3 for _, _, n in rows))
        self.assertTrue(all(b[0] < 650 for b, _, _ in rows))   # the lone panel is not a row

    def test_near_matching_rows_are_one_list_not_two(self):
        g = np.full((540, 960), 20, np.uint8)
        for (x, w), y in zip(((100, 500), (110, 512), (120, 526)), (60, 200, 340)):   # (the review's chained case)
            g[y:y + 110, x:x + w] = 35
            g[y, x:x + w] = g[y + 109, x:x + w] = 220
            g[y:y + 110, x] = g[y:y + 110, x + w - 1] = 220
        rows = read.card_rows(g)
        self.assertEqual(len(rows), len({tuple(b) for b, _, _ in rows}))   # no card listed twice

    def test_genre_words_are_whole_words(self):
        self.assertEqual(read.asked_genre("a gunfight shooter HUD"), "shooter")
        self.assertIsNone(read.asked_genre("a dogfight flight sim"))
        # ("vs mode" is no versus SCREEN: never fighting — since 2026-10-16 the racing words name it racing)
        self.assertEqual(read.asked_genre("a racing game HUD vs mode"), "racing")
        self.assertEqual(read.asked_genre("fighter select"), "fighting")

    def test_a_half_is_only_a_half_beside_its_collage(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "c16.JPG"), "wb").write(b"x")
            self.assertTrue(read.is_half(d, "c16_R.JPG"))     # any case
            self.assertFalse(read.is_half(d, "boss_R.png"))   # a real reference that just ends in _R

    def test_the_words_in_a_piece_name_it(self):
        self.assertEqual(read.role_from_words(["TENSION"], "bottom-left"), "super / tension gauge")
        self.assertEqual(read.role_from_words(["93."], "top-centre"), "round timer")
        self.assertEqual(read.role_from_words(["ASPECT OF HESTIA", "LEGENDARY"], "centre"), "card with rarity")
        self.assertIsNone(read.role_from_words(["EXTRA LIFE?"[:5]], "top-left"))   # 'EXTRA' is not 'EX' (whole words)
        self.assertIsNone(read.role_from_words(["93"], "bottom-left"))             # a number is a timer only top-centre

    def test_a_genre_must_win_clearly(self):
        import numpy as np
        order = [g for g, _ in read.GENRES]
        def gl(**v):
            return np.array([v.get(g, -9.0) for g in order])
        self.assertEqual(read.pick_genre(gl(fighting=0.64, platformer=-4.64)), "fighting")   # GGST
        self.assertEqual(read.pick_genre(gl(fighting=-1.81, platformer=-1.98)), "other")     # a near tie: no conventions
        self.assertEqual(read.pick_genre(gl(platformer=-1.74, fighting=-4.09)), "platformer")
        self.assertEqual(read.pick_genre(gl(shooter=-3.0)), "other")                           # under the floor

    def test_roles_follow_hud_conventions(self):
        self.assertEqual(read.role("map", "top-left", 260, 260), "minimap")
        self.assertEqual(read.role("bar", "bottom-right", 270, 100), "weapon / ammo block")
        self.assertEqual(read.role("bar", "top-centre", 600, 40), "compass strip")
        self.assertEqual(read.role("graphic", "top-left", 450, 260), "date / status card")
        self.assertEqual(read.where(100, 100), "top-left")
        self.assertEqual(read.where(1800, 1000), "bottom-right")


    def test_a_told_rpg_genre_names_the_battle_pieces(self):
        self.assertEqual(read.rpg_role([1150, 860, 1900, 1040]), "party status (portraits, HP / SP)")
        self.assertIsNone(read.rpg_role([100, 860, 500, 1040]))           # (bottom-LEFT is not the party strip)
        self.assertEqual(read.role("graphic", "top-left", 400, 200, "rpg"), "skill / action name")
        self.assertEqual(read.role("panel", "bottom-right", 600, 120, "rpg"), "interface panel")  # (not a weapon block)
        self.assertEqual(read.role_from_words(["WEAK"], "centre", "rpg"), "hit callout (WEAK / CRITICAL)")
        self.assertEqual(read.role_from_words(["CRITICAL", "HIT"], "centre", "rpg"), "hit callout (WEAK / CRITICAL)")
        self.assertEqual(read.role_from_words(["CRITICAL", "HEALTH"], "top-left"), "health")      # (not told rpg)
        self.assertIsNone(read.role_from_words(["MISS"], "centre", "shooter"))
        self.assertEqual(read.role_from_words(["HIT", "POINTS"], "top-left"), "health")
        self.assertIn("rpg", read.GENRE_NAMES)
        self.assertNotIn("rpg", {g for g, _ in read.GENRES})               # (never read from the frame: told)

if __name__ == "__main__":
    unittest.main()
