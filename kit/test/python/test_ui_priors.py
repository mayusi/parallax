"""kit ui read prior: where a genre puts each piece, aggregated from the reads of several games"""
import importlib.util
import json
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_priors", os.path.join(HERE, "..", "..", "ui", "priors.py"))
priors = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(priors)


def write(d, game, still, genre, elements):
    os.makedirs(os.path.join(d, game), exist_ok=True)
    json.dump({"genre": genre, "elements": [{"label": lab, "box_1080": box} for lab, box in elements]},
              open(os.path.join(d, game, still + ".read.json"), "w", encoding="utf-8"))


class TestPriors(unittest.TestCase):
    def test_pieces_are_aggregated_across_games_of_one_genre(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "gameA", "s1", "fighting", [("health bars", [200, 100, 1700, 140]), ("round timer", [900, 40, 1020, 160]),
                                                 ("interface panel", [0, 0, 50, 50])])
            write(d, "gameB", "s2", "fighting", [("health bars", [180, 60, 1740, 110]), ("round timer", [910, 30, 1010, 140])])
            write(d, "gameC", "s3", "shooter", [("minimap", [10, 10, 260, 260])])
            write(os.path.join(d, "gameA"), "candidates", "s9", "fighting", [("health bars", [0, 0, 10, 10])])  # (candidates are not refs)
            items = priors.collect(d, "fighting")
            p = priors.priors(items)
            self.assertEqual(set(p), {"health bars", "round timer"})       # generic panels and other genres left out
            self.assertEqual(p["health bars"]["games"], 2)
            self.assertEqual(p["health bars"]["box_1080"], [190, 80, 1720, 125])
            self.assertEqual(p["round timer"]["size_1080"], [110, 115])

    def test_one_sample_per_still_and_a_box_that_agrees_with_its_size(self):
        items = [("A", "s1", "bar", [0, 0, 100, 10]), ("A", "s1", "bar", [0, 0, 300, 10]), ("A", "s1", "bar", [0, 0, 300, 10]),
                 ("B", "s2", "bar", [100, 100, 200, 120]), ("C", "s3", "bar", [100, 100, 200, 120])]
        p = priors.priors(items)["bar"]
        self.assertEqual(p["stills"], 3)
        w = p["box_1080"][2] - p["box_1080"][0]
        self.assertEqual(w, p["size_1080"][0])                     # the box and the size agree
        self.assertEqual(p["size_1080"][0], 100)                   # 3 stills (one sample each): 300, 100, 100 -> 100

    def test_list_rows_and_rarities_fold_into_one_piece(self):
        self.assertEqual(priors.piece_name("card / list row 2 of 3 (legendary)"), "card / list row")
        self.assertEqual(priors.piece_name("found: a soul vessel"), "found: a soul vessel")   # (descriptions stay apart)


if __name__ == "__main__":
    unittest.main()
