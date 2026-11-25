"""Unit tests of what the browser player says its preview is NOT (kit/vfx/player/player.js previewNotes; the owner's
limitations file, F-R05): the rule's own text, run by node. No node, or a broken rule: these FAIL, they are not skipped.
Run: python -m pytest kit/test/python/test_vfx_previewnotes.py -q"""
import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PLAYER = os.path.join(ROOT, "kit", "vfx", "player", "player.js")
PAGE = os.path.join(ROOT, "kit", "vfx", "player", "index.html")


def notes(layers):
    text = open(PLAYER, encoding="utf-8").read()
    a, b = text.index("export function previewNotes("), text.index("// (end of previewNotes)")
    with tempfile.TemporaryDirectory() as tmp:
        prog = os.path.join(tmp, "notes.cjs")
        with open(prog, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text[a:b].replace("export function", "function") + "\nconsole.log(JSON.stringify(JSON.parse(process.argv[2]).map(previewNotes)));\n")
        r = subprocess.run(["node", prog, json.dumps(layers)], capture_output=True, text=True, timeout=60, check=False)
        return json.loads(r.stdout.strip().splitlines()[-1])


class WhatThePreviewIsNot(unittest.TestCase):
    def test_debris_says_its_floor_is_flat_and_is_no_proof_of_a_collision(self):
        rocks, pieces = notes([{"kind": "debris", "count": 8}, {"kind": "debris", "pieces": "slab_a", "rest": True}])
        for got in (rocks, pieces):
            self.assertEqual(len(got), 1)
            self.assertIn("ONE flat floor", got[0])
            self.assertIn("not proof of a collision", got[0])
        self.assertIn("do not meet in the air", pieces[0])

    def test_what_the_player_draws_otherwise_than_the_game(self):
        haze, erode, base, spun = notes([{"kind": "mesh", "shape": "ring", "haze": {"strength": 0.5}}, {"kind": "mesh", "shape": "ring", "erode": [0.5, 1]},
                                         {"kind": "mesh", "shape": "seq", "pivot": "base"}, {"kind": "mesh", "shape": "seq", "spin": [0, 90, 0]}])
        self.assertIn("drawn PLAIN here", haze[0])
        self.assertIn("HERE only", erode[0])
        self.assertIn("another place in the game", base[0])
        self.assertIn("first frame's middle in the game", spun[0])

    def test_a_layer_the_player_shows_as_the_game_does_says_nothing(self):
        for got in notes([{"kind": "mesh", "shape": "ring"}, {"kind": "mesh", "shape": "seq", "pivot": "origin", "spin": [0, 90, 0]}, {"kind": "sprite", "texture": "glow"},
                          {"kind": "swarm", "count": 40}, None, "debris", {}]):
            self.assertEqual(got, [])

    def test_the_page_shows_them_beside_the_layer_and_in_the_inspector(self):
        page = open(PAGE, encoding="utf-8").read()
        self.assertIn("previewNotes } from", page)
        self.assertEqual(page.count("previewNotes(el)"), 2)
        self.assertIn("this preview differs from the game", page)


if __name__ == "__main__":
    unittest.main()
