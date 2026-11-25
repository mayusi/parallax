"""Unit tests of where a mesh sequence sits ("pivot": "origin"; the VFX methods audit, stage 26): the game centres a
MeshPart on its mesh's FIRST frame's box, so the stage moves the part by that box's middle (src/kit/VfxStage.luau
seqMiddle, run here by lune from the file's own text) to put the file's origin on the layer's point.
Run: python -m pytest kit/test/python/test_vfx_seqpivot.py -q"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import water as W  # noqa: E402

STAGE = os.path.join(ROOT, "src", "kit", "VfxStage.luau")
PLAYER = os.path.join(ROOT, "kit", "vfx", "player", "player.js")
TAIL = """
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local process = require("@lune/process")
local out = {}
for i, frame in serde.decode("json", fs.readFile(process.args[1])) do
	local x, y, z = seqMiddle(frame)
	out[i] = { x, y, z }
end
print(serde.encode("json", out))
"""


def game_middles(frames):
    text = open(STAGE, encoding="utf-8").read()
    a, b = text.index("local function seqMiddle("), text.index("-- (end of seqMiddle)")
    with tempfile.TemporaryDirectory() as tmp:
        data, prog = os.path.join(tmp, "frames.json"), os.path.join(tmp, "middle.luau")
        with open(data, "w", encoding="utf-8") as fh:
            json.dump(frames, fh)
        with open(prog, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text[a:b] + TAIL)
        r = subprocess.run(["lune", "run", prog, data], capture_output=True, text=True, timeout=120, check=False, cwd=ROOT)
        return json.loads(r.stdout.strip().splitlines()[-1])   # (no lune, or a broken rule: this raises - the test FAILS, it is not skipped)


class TheMiddle(unittest.TestCase):
    def test_the_games_rule_is_the_first_frames_box(self):
        dam = W.simulate(W.arguments({"--recipe": "dam", "--frames": "3"}))
        first = W.to_points(dam[0], 20, 20).reshape(-1).tolist()                       # a dam: its first frame stands 0 .. 0.1 over the rest level
        rng = np.random.default_rng(2)
        odd = (rng.uniform(-3, 5, (40, 3)) * [1, 0.2, 2]).reshape(-1).tolist()
        flat = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
        got = game_middles([first, odd, flat, []])
        for frame, mid in zip((first, odd, flat), got):
            p = np.array(frame).reshape(-1, 3)
            for k in range(3):
                self.assertAlmostEqual(mid[k], float((p[:, k].min() + p[:, k].max()) / 2), places=12)
        self.assertEqual(got[3], [0, 0, 0])
        self.assertAlmostEqual(got[0][1], 0.05, places=4)                              # so centred on its box it sat 0.05 x scale under its point
        self.assertAlmostEqual(got[0][0], 0.0, places=9)

    def test_moved_by_that_middle_the_files_origin_is_on_the_point(self):
        """the part's centre shows the mesh's point `middle`; the stage puts the centre at point + middle x scale"""
        p = np.random.default_rng(5).uniform(-1, 2, (30, 3))
        middle = (p.min(0) + p.max(0)) / 2
        point, scale = np.array([10.0, 4.0, -3.0]), 12.0
        centre = point + middle * scale
        shown = centre + (p - middle) * scale
        self.assertLess(float(np.abs(shown - (point + p * scale)).max()), 1e-9)        # every vertex: the point + its own place x scale

    def test_both_runtimes_know_the_word(self):
        stage = open(STAGE, encoding="utf-8").read()
        self.assertIn('if pivot == "origin" then', stage)
        self.assertIn("cf *= CFrame.new(middle * grow)", stage)
        self.assertLess(stage.index("cf *= CFrame.Angles(math.rad(spin.X)"), stage.index("cf *= CFrame.new(middle * grow)"))   # it spins about its origin
        self.assertIn('this.pivot === "base" || this.pivot === "origin"', open(PLAYER, encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
