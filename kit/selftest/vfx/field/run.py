#!/usr/bin/env python3
"""The self-test of AN AUTHORED VECTOR FIELD (kit/vfx/field.py, a swarm layer's "field"; the VFX methods audit, stage 11).

    python kit/selftest/vfx/field/run.py good     the four starters made by the real command into a folder of this
                                                  run's own: each passes its checks and draws its picture; and each
                                                  does what it is said to - the wind carries every speck the same way,
                                                  the vortex turns specks round its axis (they keep their distance or
                                                  close in, none flies off), the path draws specks onto its line and
                                                  along it to where they hang past its end, the fountain lifts specks up its axis
    python kit/selftest/vfx/field/run.py still    a field whose one vortex sits far outside its bounds: the air in the
                                                  bounds stands still - the command must fail naming "stands still"
    python kit/selftest/vfx/field/run.py parity   the velocity asked at 200 places of five fields of the GAME's rule (the
                                                  text of fieldAt in src/kit/VfxStage.luau, run by lune), of the
                                                  PLAYER's (player.js, run by node) and of field.py: the same three
                                                  numbers from all three; and the player parses as the module it is

Nothing here moves a swarm in Roblox or in the browser player.
"""
import contextlib
import io
import json
import math
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import field  # noqa: E402

STAGE = os.path.join(ROOT, "src", "kit", "VfxStage.luau")
PLAYER = os.path.join(ROOT, "kit", "vfx", "player", "player.js")


def call(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = field.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


MIXED = [{"kind": "wind", "dir": [1, 0.5, -2], "speed": 3}, {"kind": "vortex", "at": [1, 0, -1], "axis": [0.3, 1, 0.2], "radius": 3, "speed": -9, "pull": 2, "lift": 4},
         {"kind": "vortex", "at": [-2, 1, 0], "radius": 1.5, "speed": 6}, {"kind": "point", "at": [0, 3, 0], "radius": 2.5, "speed": -7},
         {"kind": "path", "points": [[-5, 0, 0], [-5, 0, 0], [0, 3, 1], [4, -1, 2]], "radius": 2, "speed": 8, "pull": 5},
         {"kind": "path", "points": [[0, -4, 0], [0, 4, 0]], "radius": 1, "speed": -3}]
LUAU_HEAD = 'local fs = require("@lune/fs")\nlocal serde = require("@lune/serde")\nlocal process = require("@lune/process")\n'
LUAU_TAIL = """
local out = {}
for i, c in serde.decode("json", fs.readFile(process.args[1])) do
	local row = {}
	for j, p in c[2] do
		row[j] = fieldAt(c[1], p[1], p[2], p[3])
	end
	out[i] = row
end
print(serde.encode("json", out))
"""
JS_TAIL = """
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(cases.map(c => c[1].map(p => fieldAt(c[0], p[0], p[1], p[2])))));
"""


def cut(path, first, end):
    text = open(path, encoding="utf-8").read()
    a, b = text.find(first), text.find(end)
    if a < 0 or b < a:
        raise ValueError(f"{os.path.relpath(path, ROOT)} has no fieldAt between its two marks")
    return text[a:text.rfind("\n", a, b)]


def parity(root):
    places = field.seeds(9, 194, seed=11) + [[1, 0, -1], [0, 3, 0], [-5, 0, 0], [4, -1, 2], [0, 0, 0], [1.3, 1, -0.8]]  # (and ON the elements)
    fields = [field.STARTERS[k]["elements"] for k in ("vortex", "wind", "fountain", "path")] + [MIXED]
    asked = [[els, places] for els in fields]
    os.makedirs(root, exist_ok=True)
    data = os.path.join(root, "cases.json")
    with open(data, "w", encoding="utf-8") as fh:
        json.dump(asked, fh)
    luau, js = os.path.join(root, "game.luau"), os.path.join(root, "player.cjs")
    with open(luau, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(LUAU_HEAD + cut(STAGE, "local function fieldAt(", "-- (end of fieldAt)") + "\n" + LUAU_TAIL)
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(cut(PLAYER, "function fieldAt(", "// (end of fieldAt)") + "\n" + JS_TAIL)
    problems, got = [], {}
    for who, cmd in (("the game (VfxStage.luau)", ["lune", "run", luau, data]), ("the player (player.js)", ["node", js, data])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False, cwd=ROOT)
            got[who] = json.loads(r.stdout.strip().splitlines()[-1])
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
            problems.append(f"{who} could not be asked: {type(e).__name__}: {str(e)[:120]}")
    whole = os.path.join(root, "player_whole.mjs")  # (`node --check player.js` passes a broken player: it is a module)
    shutil.copyfile(PLAYER, whole)
    try:
        r = subprocess.run(["node", "--check", whole], capture_output=True, text=True, timeout=120, check=False)
        if r.returncode != 0:
            problems.append("kit/vfx/player/player.js does not parse: " + " ".join(r.stderr.split())[:200])
    except (OSError, subprocess.TimeoutExpired) as e:
        problems.append(f"the player could not be parsed: {type(e).__name__}")
    want = [[field.at(els, *p) for p in places] for els in fields]
    moving = sum(1 for row in want for v in row if abs(v[0]) + abs(v[1]) + abs(v[2]) > 1e-6)
    for who, answers in got.items():
        off = [(n, k) for n, (mine, theirs) in enumerate(zip(want, answers)) for k, (a, b) in enumerate(zip(mine, theirs))
               if len(b) != 3 or any(abs(float(x) - float(y)) > 1e-9 for x, y in zip(a, b))]
        if len(answers) != len(want) or any(len(t) != len(places) for t in answers) or off:
            where = f": first in field {off[0][0] + 1} at {places[off[0][1]]}" if off else ""
            problems.append(f"{who} gives another velocity in {len(off)} of {len(fields) * len(places)} places{where}")
    if moving < len(fields) * len(places) * 0.8:
        problems.append(f"only {moving} of the asked places have moving air: the cases do not ask the rule much")
    return problems, len(fields) * len(places)


def behaves(root):
    """-> problems: each starter does what it is said to"""
    problems = []
    for kind in ("vortex", "wind", "fountain", "path"):
        code, said = call([f"made_{kind}", "--new", kind, "--out-dir", root, "--look-dir", root])
        if code != 0 or not os.path.isfile(os.path.join(root, f"made_{kind}.png")):
            problems.append(f"the {kind} starter is refused or has no picture: " + said["summary"][:160])
    if problems:
        return problems
    load = lambda k: json.load(open(os.path.join(root, f"made_{k}.json"), encoding="utf-8"))  # noqa: E731
    ends = lambda f: [(t[0], t[-1]) for t in field.trails(f)]  # noqa: E731
    wind = ends(load("wind"))
    moves = [[b[i] - a[i] for i in range(3)] for a, b in wind]
    if any(math.dist(m, moves[0]) > 1e-6 for m in moves) or moves[0][0] <= 0:
        problems.append("the wind does not carry every speck the same way")
    ways = set()
    for t in field.trails(load("vortex")):
        a, b = t[0], t[-1]
        r0, r1 = math.hypot(a[0], a[2]), math.hypot(b[0], b[2])
        # the angle swept round the axis, added up step by step (the difference of two angles wraps at a whole turn)
        swept = 0.0
        for p, q in zip(t, t[1:]):
            if math.hypot(p[0], p[2]) > 1e-6 and math.hypot(q[0], q[2]) > 1e-6:
                step = math.atan2(q[2], q[0]) - math.atan2(p[2], p[0])
                swept += (step + math.pi) % (2 * math.pi) - math.pi
        if r1 > r0 + 0.5:
            problems.append(f"the vortex throws a speck outward (from {r0:.1f} to {r1:.1f} studs off its axis)")
            break
        if 1 < r0 < 6:
            ways.add(swept > 0)
            if abs(swept) < 0.5:
                problems.append(f"a speck {r0:.1f} studs off the vortex's axis is turned only {abs(swept):.2f} radians in 3 s")
                break
    if len(ways) != 1:
        problems.append("the vortex does not turn every speck the same way round" if ways else "no speck was let go near the vortex")
    path = load("path")
    pts = path["elements"][0]["points"]
    # past its last point the flow still pushes along the line while the pull draws back to that point: the specks come
    # to hang where the two are equal, speed x radius / pull beyond the end
    e, ln = path["elements"][0], math.dist(pts[-2], pts[-1])
    hang = [pts[-1][i] + (pts[-1][i] - pts[-2][i]) / ln * (e["speed"] * e["radius"] / e["pull"]) for i in range(3)]
    near = [math.dist(b, hang) < 1.0 for a, b in ends(path) if min(math.dist(a, q) for q in pts) < 3]
    if len(near) < 5 or sum(near) < len(near) * 0.8:
        problems.append(f"the path does not carry the specks near it along itself to where they hang past its end ({sum(near)} of {len(near)})")
    up = [b[1] - a[1] for a, b in ends(load("fountain")) if math.hypot(a[0], a[2]) < 3]
    if len(up) < 3 or min(up) <= 0:
        problems.append("the fountain does not lift the specks near its axis")
    return problems


def main(argv):
    case = argv[0] if argv else "good"
    root = os.path.join("build", "selftest", f"vfx_field_{case}_{os.getpid()}")
    try:
        if case == "parity":
            try:
                problems, n = parity(root)
            except ValueError as e:
                problems, n = [str(e)], 0
            if problems:
                return say("fail", "field parity: " + "; ".join(problems), "src/kit/VfxStage.luau fieldAt, kit/vfx/player/player.js fieldAt and kit/vfx/field.py at are ONE rule")
            return say("pass", f"field parity: the game's fieldAt, the player's and the rule give the same velocity at {n} places of five fields", "none")
        os.makedirs(root, exist_ok=True)
        if case == "still":
            with open(os.path.join(root, "made_far.json"), "w", encoding="utf-8") as fh:
                json.dump({"schema": 1, "bounds": 4, "elements": [{"kind": "vortex", "at": [300, 0, 0], "radius": 2, "speed": 12}]}, fh)
            code, said = call(["made_far", "--out-dir", root, "--look-dir", root])
            if code == 0:
                return say("pass", "field still: a field whose air stands still in its bounds was let through", "kit/vfx/field.py check")
            return say("fail", "field still: " + said["summary"][:300], said["next_action"][:200])
        problems = behaves(root)
        if problems:
            return say("fail", "field good: " + "; ".join(problems[:4]), "kit/vfx/field.py")
        return say("pass", "field good: the four starters pass their checks and draw their pictures; the wind carries every speck one way, the vortex turns "
                   "specks round its axis and throws none out, the path carries the specks near it along itself to where they hang past its end, the fountain lifts those near its axis", "none")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
