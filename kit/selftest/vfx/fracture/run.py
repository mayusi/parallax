"""run.py - the fracture plan's selftest cases (kit selftest): a made slab cut by the real command.

    python kit/selftest/vfx/fracture/run.py good   a 12 x 8 slab struck off-centre, in 14 pieces: the pieces make up
                                                   the slab to a thousandth and each is convex; laid back at their
                                                   centres they cover the slab with no gap and no overlap (painted,
                                                   pixel by pixel); the piece nearest the blow leaves first and
                                                   fastest; a quarter of a second after the blow every piece is
                                                   further from the blow than it sat; the plan is written
    python kit/selftest/vfx/fracture/run.py gap    the same plan with one piece taken out: it no longer makes up the
                                                   slab - this case fails, naming "do not make up the slab"

    python kit/selftest/vfx/fracture/run.py parity one piece's solid, asked of the GAME's shape (the text of `piece` in
                                                   src/kit/VfxMesh.luau, run by lune) and of the PLAYER's (player.js,
                                                   run by node) for three outlines: the same points and the same
                                                   texture places from both, and a closed prism (the rim rows are the
                                                   outline at the bottom and the top, the end rows their middles)

What each part does when it is wrong is proven part by part in kit/test/python/test_vfx_fracture.py.
Prints one JSON line {schema, status, summary, next_action}; everything is written to a folder of this run's own
under build/selftest/, removed at the end.
"""

import contextlib
import io
import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import fracture  # noqa: E402


def call(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fracture.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def painted(plan, px=40):
    """every piece painted at its place, one layer a piece -> how many pieces cover each pixel of the slab"""
    w, d = plan["size"][0], plan["size"][1]
    count = np.zeros((int(d * px), int(w * px)), dtype=np.int32)
    for pc in plan["pieces"]:
        layer = Image.new("L", (count.shape[1], count.shape[0]), 0)
        pts = [((pc["centre"][0] + x + w / 2) * px, (d / 2 - (pc["centre"][1] + z)) * px) for x, z in pc["points"]]
        ImageDraw.Draw(layer).polygon(pts, fill=1)
        count += np.asarray(layer, dtype=np.int32)
    return count


ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
MESH = os.path.join(ROOT, "src", "kit", "VfxMesh.luau")
PLAYER = os.path.join(ROOT, "kit", "vfx", "player", "player.js")
LUAU = """
local fs = require("@lune/fs")
local serde = require("@lune/serde")
local process = require("@lune/process")
local Vector3 = { new = function(x, y, z) return { x, y, z } end }
local Vector2 = { new = function(x, y) return { x, y } end }
local function grid(cols, rows, at, uvAt)
	local pos, uv = {}, {}
	for j = 0, rows do
		for i = 0, cols do
			table.insert(pos, at(i / cols, j / rows))
			table.insert(uv, uvAt(i / cols, j / rows))
		end
	end
	return { pos = pos, uv = uv, cols = cols, rows = rows }
end
local %s
local out = {}
for i, c in serde.decode("json", fs.readFile(process.args[1])) do
	out[i] = piece(c)
end
print(serde.encode("json", out))
"""
JS = """
function gridGeo(cols, rows, at, uvAt) {
  const pos = [], uv = [];
  for (let j = 0; j <= rows; j++) for (let i = 0; i <= cols; i++) { pos.push(at(i / cols, j / rows)); uv.push(uvAt(i / cols, j / rows)); }
  return { pos, uv, cols, rows };
}
const SHAPES = {
%s
};
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(cases.map(c => SHAPES.piece(c))));
"""


def cut(path, first, after):
    text = open(path, encoding="utf-8").read()
    a = text.find(first)
    b = text.find(after, a)
    if a < 0 or b < a:
        raise ValueError(f"{os.path.relpath(path, ROOT)} has no piece shape where it is looked for")
    return text[a:b].rstrip()


def parity(root):
    """-> problems. The game's piece shape and the player's, each as its own file's TEXT, on the same outlines"""
    cases = [{"points": [[-1, -1], [1, -1], [1, 1], [-1, 1]], "height": 0.5, "centre": [2, -1], "slab": [12, 8]},
             {"points": [[-0.8, -0.3], [0.1, -0.9], [1.2, 0.2], [0.3, 0.9], [-0.9, 0.5]], "height": 0.2, "centre": [-3, 2.5], "slab": [10, 10]},
             {"points": [[0, -1], [1, 1], [-1, 1]], "height": 1.0, "centre": [0, 0], "slab": [4, 4]}]
    os.makedirs(root, exist_ok=True)
    data = os.path.join(root, "cases.json")
    with open(data, "w", encoding="utf-8") as fh:
        json.dump(cases, fh)
    luau, js = os.path.join(root, "game.luau"), os.path.join(root, "player.cjs")
    body = cut(MESH, "piece = function(p)", "\t-- a faceted stone")
    with open(luau, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(LUAU % body.rstrip(","))
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(JS % cut(PLAYER, "  piece: (p) =>", "  rock: (p) =>"))
    problems, got = [], {}
    for who, cmd in (("the game (VfxMesh.luau)", ["lune", "run", luau, data]), ("the player (player.js)", ["node", js, data])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
            got[who] = json.loads(r.stdout.strip().splitlines()[-1])
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
            problems.append(f"{who} could not be asked: {type(e).__name__}: {str(e)[:120]}")
    for who, shapes in got.items():
        for c, g in zip(cases, shapes):
            n, h = len(c["points"]), c["height"]
            pos, uv = np.asarray(g["pos"], dtype=np.float64), np.asarray(g["uv"], dtype=np.float64)
            if g["cols"] != n or g["rows"] != 3 or pos.shape != (4 * (n + 1), 3):
                problems.append(f"{who}: a piece of {n} corners is not four rows of {n + 1} points")
                continue
            rows = pos.reshape(4, n + 1, 3)
            rim = np.asarray(c["points"] + [c["points"][0]], dtype=np.float64)
            ok = (np.allclose(rows[0][:, [0, 2]], 0) and np.allclose(rows[3][:, [0, 2]], 0) and np.allclose(rows[1][:, [0, 2]], rim) and np.allclose(rows[2][:, [0, 2]], rim)
                  and np.allclose(rows[0][:, 1], -h / 2) and np.allclose(rows[1][:, 1], -h / 2) and np.allclose(rows[2][:, 1], h / 2) and np.allclose(rows[3][:, 1], h / 2))
            if not ok:
                problems.append(f"{who}: a piece of {n} corners is not a closed prism of its outline")
            want = np.column_stack([0.5 + (c["centre"][0] + pos[:, 0]) / c["slab"][0], 0.5 + (c["centre"][1] + pos[:, 2]) / c["slab"][1]])
            if not np.allclose(uv, want):
                problems.append(f"{who}: a piece's texture places are not its places in the slab")
    if len(got) == 2:
        a, b = got.values()
        if not all(np.allclose(x["pos"], y["pos"]) and np.allclose(x["uv"], y["uv"]) for x, y in zip(a, b)):
            problems.append("the game and the player build different pieces from one outline")
    return problems


def main(argv):
    case = argv[0] if argv else "good"
    if case == "parity":
        root = os.path.join("build", "selftest", f"vfx_fracture_parity_{os.getpid()}")
        try:
            problems = parity(root)
        except ValueError as e:
            problems = [str(e)]
        finally:
            shutil.rmtree(root, ignore_errors=True)
        if problems:
            print(json.dumps({"schema": 1, "status": "fail", "summary": "fracture parity: " + "; ".join(problems), "next_action": "src/kit/VfxMesh.luau `piece` and kit/vfx/player/player.js `piece` must build the same solid"}))
            return 1
        print(json.dumps({"schema": 1, "status": "pass", "summary": "fracture parity: the game's piece shape and the player's build the same closed prism, with the slab's texture places, for three outlines", "next_action": "none"}))
        return 0
    root = os.path.join("build", "selftest", f"vfx_fracture_{case}_{os.getpid()}")
    problems = []
    try:
        code, v = call(["made_slab", "--size", "12,8,0.6", "--pieces", "14", "--impact", "-2,1", "--out-dir", os.path.join(root, "plans"), "--look-dir", os.path.join(root, "look")])
        store = os.path.join(root, "plans", "made_slab.json")
        if code != 0 or not os.path.isfile(store):
            problems.append(f"the good slab was refused: {v['summary']}")
        else:
            plan = json.load(open(store, encoding="utf-8"))
            if case == "gap":
                plan["pieces"].pop(3)
                o = fracture.checked({"size": plan["size"], "pieces": 14, "impact": plan["impact"]})
                failed = [c for c in fracture.check(plan, o) if not c["ok"]]
                if not any(c["name"] == "tiles" for c in failed):
                    print(json.dumps({"schema": 1, "status": "pass", "summary": "fracture gap: a slab with a piece missing passed as whole", "next_action": "kit/vfx/fracture.py: the `tiles` check"}))
                    return 0
                tiles = next(c for c in failed if c["name"] == "tiles")
                print(json.dumps({"schema": 1, "status": "fail", "summary": f"fracture made_slab: tiles = {tiles['value']} (needs {tiles['limit']}): {tiles['fix']}", "next_action": tiles["fix"]}))
                return 1
            pieces = plan["pieces"]
            if len(pieces) != 14:
                problems.append(f"{len(pieces)} pieces, not 14")
            total = sum(pc["area"] for pc in pieces)
            if abs(total - 96.0) > 0.096:
                problems.append(f"the pieces' areas add up to {total:.3f}, the slab is 96")
            cover = painted(plan)
            inner = cover[4:-4, 4:-4]
            gaps, doubled = float((inner == 0).mean()), float((inner > 1).mean())
            if gaps > 0.002 or doubled > 0.03:  # (a painted edge belongs to both its pieces: a line of pixels a seam)
                problems.append(f"laid back together the pieces leave {gaps:.1%} of the slab bare and cover {doubled:.1%} twice")
            ix, iz = plan["impact"]
            dist = [math.hypot(pc["centre"][0] - ix, pc["centre"][1] - iz) for pc in pieces]
            speed = [math.hypot(*pc["vel"]) for pc in pieces]
            first = int(np.argmin([pc["delay"] for pc in pieces]))
            if first != int(np.argmin(dist)):
                problems.append("the piece that leaves first is not the one nearest the blow")
            if speed[int(np.argmin(dist))] < 0.9 * max(speed):
                problems.append("the piece nearest the blow is not among the fastest")
            for k, pc in enumerate(pieces):
                x, y, z = fracture.fly(pc, 0.25, thick=plan["size"][2])
                if math.hypot(x - ix, z - iz) <= dist[k] + 1e-6 and dist[k] > 1e-3:
                    problems.append(f"piece {k} is no further from the blow a quarter of a second after it")
                    break
            if not os.path.isfile(os.path.join(root, "look", "made_slab.png")):
                problems.append("no LOOK picture was written")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    if problems:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"fracture {case}: " + "; ".join(problems), "next_action": "kit/vfx/fracture.py"}))
        return 1
    print(json.dumps({"schema": 1, "status": "pass", "summary": "fracture good: 14 convex pieces that make up the slab with no gap and no overlap; the nearest leaves first and fastest; all fly away from the blow",
                      "next_action": "none"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
