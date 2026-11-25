"""kit sfx set's MATERIAL MATRIX (mission 07 5.3): weapon x surface cells expanded from one set's DNA, merged by rule."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "audio"))
import sets  # noqa: E402

SPEC = {
    "dna": {"crack": {"role": "transient", "source": "click"}, "ring": {"role": "tail", "source": "modal", "modes": [[800, 1, 1]]},
            "thud": {"role": "body", "source": "noise"}},
    "members": {"sword_hit_metal": {"class": "hit", "use": ["crack", "ring"], "duration": 1.4}},
    "matrix": {
        "verb": "hit",
        "base": {"class": "hit", "weights": [0.2, 0.8]},
        "weapons": {"sword": {"use": ["crack"]}, "fist": {"use": {"thud": {"gain": 1.1}}, "layers": [{"role": "transient", "source": "noise"}]}},
        "surfaces": {"metal": {"use": {"ring": {}}}, "wood": {"use": {"thud": {"gain": 0.7}}, "layers": [{"role": "body", "source": "modal", "modes": [[310, 0.1, 1]]}]}},
    },
}


class Matrix(unittest.TestCase):
    def test_every_cell_becomes_a_member_and_a_named_member_keeps_its_recipe(self):
        members, cells = sets.expand_matrix(SPEC)
        self.assertEqual(sorted(cells), ["fist_hit_metal", "fist_hit_wood", "sword_hit_metal", "sword_hit_wood"])
        self.assertEqual(cells["fist_hit_wood"], ("fist", "wood"))
        self.assertEqual(members["sword_hit_metal"]["duration"], 1.4)  # (the hand-made one, not the matrix's)
        self.assertNotIn("weights", members["sword_hit_metal"])

    def test_layers_add_up_and_use_merges_with_the_surface_last(self):
        members, _ = sets.expand_matrix(SPEC)
        fw = members["fist_hit_wood"]
        self.assertEqual([l["source"] for l in fw["layers"]], ["noise", "modal"])  # (weapon's, then surface's)
        self.assertEqual(fw["use"]["thud"]["gain"], 0.7)  # (the surface decides what it is hit on)
        self.assertEqual(fw["weights"], [0.2, 0.8])
        self.assertEqual(sorted(members["sword_hit_wood"]["use"]), ["crack", "thud"])

    def test_resolve_carries_the_cell_and_names_the_weights(self):
        recipes = sets.resolve(SPEC)
        self.assertIn("fist_hit_wood_light", recipes)
        self.assertIn("fist_hit_wood_heavy", recipes)
        self.assertEqual(recipes["fist_hit_wood_heavy"]["_cell"], ("fist", "wood"))
        self.assertEqual(recipes["sword_hit_metal"]["_cell"], ("sword", "metal"))  # (hand-made, still its cell)

    def test_no_matrix_changes_nothing(self):
        members, cells = sets.expand_matrix({"members": {"a": {"use": []}}})
        self.assertEqual(cells, {})
        self.assertEqual(list(members), ["a"])


if __name__ == "__main__":
    unittest.main()
