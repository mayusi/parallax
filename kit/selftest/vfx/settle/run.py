#!/usr/bin/env python3
"""The self-test of PIECES THAT COME TO REST (kit/vfx/settle.py, a debris layer's "rest"; the VFX methods audit, stage 10).

    python kit/selftest/vfx/settle/run.py good     a made slab cut by the real fracture command, its pieces flown by
                                                   the real settle command with a life of 2.5 s: every piece comes to
                                                   rest before the fade, lying flat on the floor, away from where it
                                                   sat; the same at 30 and at 144 frames a second (the last piece's
                                                   rest within 0.6 s of the 60 fps one), and no two
                                                   pieces at rest lie in each other at any of the three
    python kit/selftest/vfx/settle/run.py late     the same plan with a life of 0.5 s: pieces are still moving when the
                                                   fade starts - the command must fail naming "still moving" (exit 1)
    python kit/selftest/vfx/settle/run.py through  the same plan flown the OLD way (every piece by itself, passing through
                                                   the others): the check must fail naming "lies_apart"
    python kit/selftest/vfx/settle/run.py parity   (and PIECES THAT MEET, stage 23: 13 piles - squares in each other, a
                                                   square dropped on a slab at rest, six pieces dropped on one place,
                                                   a triangle thrown into a slab, a real slab's own pieces - flown 3
                                                   seconds together by all three: the same numbers to 1e-7)
                                                   pieces flown step by step by the GAME's rule (the text of debrisStep
                                                   in src/kit/VfxStage.luau, run by lune), by the PLAYER's (player.js,
                                                   run by node) and by settle.py: the same eleven numbers after every
                                                   one of 240 steps, for six pieces at three frame rates; and the
                                                   player parses as the module it is

Nothing here flies a piece in Roblox or in the browser player.
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
import fracture  # noqa: E402
import settle  # noqa: E402

STAGE = os.path.join(ROOT, "src", "kit", "VfxStage.luau")
PLAYER = os.path.join(ROOT, "kit", "vfx", "player", "player.js")


def call(mod, argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = mod.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def made(root):
    code, said = call(fracture, ["made_slab", "--size", "12,10,0.5", "--pieces", "14", "--out-dir", root, "--look-dir", root])
    if code != 0:
        raise ValueError("the made slab could not be cut: " + said["summary"][:160])


# cases for the parity: [state, dt, g, floor, hy, hw] flown 240 steps (a fall from rest, a hard throw, a spinning
# piece, one already on the ground, one sliding flat, a thick block)
STARTS = [[[0, 0.25, 0, 6, 14, -3, 0, 0, 3.1, -1.2, 0], 0.25, 2.0], [[1, 5, 2, 30, 0, 4, 0, 0, -7.5, 4, 0], 0.25, 1.5],
          [[-3, 0.25, 1, -2, 22, 9, 0, 0, 11, 2, 0], 0.1, 0.8], [[0, 0.25, 0, 0, 0, 0, 0, 0, 0, 0, 0], 0.25, 2.0],
          [[2, 0.25, -1, 9, 0, -9, 0, 0, 0, 5, 0], 0.25, 1.0], [[0, 3, 0, 1, -4, 1, 1.2, 0, 2, 0, 0], 1.0, 1.1]]
RATES = [1 / 60, 1 / 30, 1 / 144]
LUAU_HEAD = 'local fs = require("@lune/fs")\nlocal serde = require("@lune/serde")\nlocal process = require("@lune/process")\n'
LUAU_TAIL = """
local out = {}
for i, c in serde.decode("json", fs.readFile(process.args[1])) do
	local s, trail = c[1], {}
	for n = 1, 240 do
		s = debrisStep(s, c[2], c[3], c[4], c[5], c[6])
		trail[n] = table.clone(s)
	end
	out[i] = trail
end
print(serde.encode("json", out))
"""
JS_TAIL = """
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(cases.map(c => { let s = c[0]; const trail = []; for (let n = 0; n < 240; n++) { s = debrisStep(s, c[1], c[2], c[3], c[4], c[5]); trail.push(s.slice()); } return trail; })));
"""


def cut(path, first, end):
    text = open(path, encoding="utf-8").read()
    a, b = text.find(first), text.find(end)
    if a < 0 or b < a:
        raise ValueError(f"{os.path.relpath(path, ROOT)} has no debrisStep between its two marks")
    return text[a:text.rfind("\n", a, b)]


def parity(root):
    asked = [[s, dt, 120.0, 0.0, hy, hw] for s, hy, hw in STARTS for dt in RATES] + [[STARTS[1][0], 1 / 60, 40.0, -2.5, 0.25, 1.5]]
    os.makedirs(root, exist_ok=True)
    data = os.path.join(root, "cases.json")
    with open(data, "w", encoding="utf-8") as fh:
        json.dump(asked, fh)
    luau, js = os.path.join(root, "game.luau"), os.path.join(root, "player.cjs")
    with open(luau, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(LUAU_HEAD + cut(STAGE, "local function debrisStep(", "-- (end of debrisStep)") + "\n" + LUAU_TAIL)
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(cut(PLAYER, "function debrisStep(", "// (end of debrisStep)") + "\n" + JS_TAIL)
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
    want = []
    rested = 0
    for s, dt, g, floor, hy, hw in asked:
        trail = []
        for _ in range(240):
            s = settle.step(s, dt, g, floor, hy, hw)
            trail.append(s)
        rested += s[10] == 1
        want.append(trail)
    for who, answers in got.items():
        off = None
        for n, (mine, theirs) in enumerate(zip(want, answers)):
            if len(theirs) != 240 or any(len(b) != 11 or any(abs(float(x) - float(y)) > 1e-9 for x, y in zip(a, b)) for a, b in zip(mine, theirs)):
                off = n if off is None else off
        if len(answers) != len(want) or off is not None:
            problems.append(f"{who} flies another flight (first in case {off}: dt {asked[off or 0][1]:.4f})")
    if rested < len(asked) - 3:
        problems.append(f"only {rested} of {len(asked)} test pieces come to rest in 240 steps: the cases do not reach the rule's end")
    return problems, len(asked), rested


START_LUAU = """
local out = {}
local c = serde.decode("json", fs.readFile(process.args[1]))
for _, k in c.asks do
	for _, pc in c.pieces do
		local s, hy, hw, shape = debrisStart(pc, c.thick, k[1], k[2])
		table.insert(out, { s, hy, hw, shape })
	end
end
print(serde.encode("json", out))
"""
START_JS = """
const c = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
const out = []; for (const k of c.asks) for (const pc of c.pieces) out.push(debrisStart(pc, c.thick, k[0], k[1]));
console.log(JSON.stringify(out));
"""


def start_parity(root, plan):
    """a piece AS IT SITS IN THE SLAB, by the game's debrisStart, the player's and the rule's start (stage 10's
    leftover: only the step was compared) - every piece of a made slab at scales 1 and 2.5, pushes 1 and 0.6"""
    asks = [[1.0, 1.0], [2.5, 1.0], [1.0, 0.6], [2.5, 0.6]]
    thick = plan["size"][2]
    data = os.path.join(root, "start.json")
    with open(data, "w", encoding="utf-8") as fh:
        json.dump({"asks": asks, "pieces": plan["pieces"], "thick": thick}, fh)
    luau, js = os.path.join(root, "start.luau"), os.path.join(root, "start.cjs")
    with open(luau, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(LUAU_HEAD + cut(STAGE, "local function debrisStart(", "-- (end of debrisStart)") + "\n" + START_LUAU)
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(cut(PLAYER, "function debrisStart(", "// (end of debrisStart)") + "\n" + START_JS)
    want = []
    for scale, push in asks:
        for pc in plan["pieces"]:
            s, hy, hw, shape = settle.start(pc, thick, push)
            want.append([[v * scale if i < 6 else v for i, v in enumerate(s)], hy * scale, hw * scale, [v * scale for v in shape]])
    problems = []
    for who, cmd in (("the game (VfxStage.luau)", ["lune", "run", luau, data]), ("the player (player.js)", ["node", js, data])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False, cwd=ROOT)
            got = json.loads(r.stdout.strip().splitlines()[-1])
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
            problems.append(f"{who}'s start could not be asked: {type(e).__name__}: {str(e)[:120]}")
            continue
        bad = [n for n, (a, b) in enumerate(zip(want, got))
               if len(b) != 4 or len(b[0]) != 11 or any(abs(float(x) - float(y)) > 1e-9 for x, y in zip(a[0], b[0]))
               or abs(a[1] - b[1]) > 1e-9 or abs(a[2] - b[2]) > 1e-9
               or len(b[3]) != len(a[3]) or any(abs(float(x) - float(y)) > 1e-9 for x, y in zip(a[3], b[3]))]
        if len(got) != len(want) or bad:
            problems.append(f"{who} starts a piece elsewhere than the rule ({len(bad)} of {len(want)}, first: piece {bad[0] % len(plan['pieces']) if bad else '?'})")
    problems += yaw_parity(root)
    return problems, len(want)


# the turns a slab is played in: yaw alone, and yaw with a tilt (pitch, roll) - [x, y, z] of a Y-X-Z turn, radians
TURNS = [[0, 0, 0], [0, 0.7, 0], [0, -2.4, 0], [0, 3.1, 0], [0.3, 1.2, -0.4], [-0.6, -0.9, 0.25], [0.2, 2.8, 0.5]]
YAW_LUAU = """local roblox = require("@lune/roblox")
local CFrame = roblox.CFrame
local out = {}
for _, t in serde.decode("json", fs.readFile(process.args[1])) do
	table.insert(out, frameYaw(CFrame.fromEulerAnglesYXZ(t[1], t[2], t[3])))
end
print(serde.encode("json", out))
"""
YAW_JS = """
const turns = JSON.parse(readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(turns.map((t) => frameYaw(new THREE.Quaternion().setFromEuler(new THREE.Euler(t[0], t[1], t[2], "YXZ"))))));
"""


def yaw_parity(root):
    """the frame's yaw a slab's pieces are met by, read by the GAME from a Roblox CFrame (Lune's own roblox library) and by
    the PLAYER from a three.js quaternion, on the same turns - each must give the turn's own yaw (stage 23's leftover:
    how each side turns a piece was read side by side, never run)"""
    data = os.path.join(root, "turns.json")
    with open(data, "w", encoding="utf-8") as fh:
        json.dump(TURNS, fh)
    luau, js = os.path.join(root, "yaw.luau"), os.path.join(root, "yaw.mjs")
    three = os.path.join(ROOT, "kit", "vfx", "player", "vendor", "three.module.js").replace(os.sep, "/")
    with open(luau, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(LUAU_HEAD + cut(STAGE, "local function frameYaw(", "-- (end of frameYaw)") + "\n" + YAW_LUAU)
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f'import * as THREE from "file:///{three}";\nimport {{ readFileSync }} from "fs";\n'
                 + cut(PLAYER, "function frameYaw(", "// (end of frameYaw)") + "\n" + YAW_JS)
    problems = []
    for who, cmd in (("the game (Roblox's CFrame)", ["lune", "run", luau, data]), ("the player (three.js)", ["node", js, data])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False, cwd=ROOT)
            got = json.loads(r.stdout.strip().splitlines()[-1])
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
            problems.append(f"{who}'s yaw could not be asked: {type(e).__name__}: {str(e)[:120]}")
            continue
        off = [i for i, (t, y) in enumerate(zip(TURNS, got)) if abs(math.remainder(float(y) - t[1], 2 * math.pi)) > 1e-5]
        if len(got) != len(TURNS) or off:
            problems.append(f"{who} reads another yaw than the turn's (turn {off[0] if off else '?'}: {TURNS[off[0]] if off else ''} -> {got[off[0]] if off else ''})")
    return problems


# PIECES THAT MEET (stage 23): [states, shapes, H, W, A, dt, g, base, steps] flown 3 seconds TOGETHER by all three
SQ = [-1, -1, 1, -1, 1, 1, -1, 1]           # a square 2 x 2
BIG = [-3, -2, 3, -2, 3, 2, -3, 2]          # a slab 6 x 4
TRI = [-1.5, -0.8, 1.5, -0.8, 0, 1.3]       # a triangle


def piles():
    """made piles: two squares in each other on the ground; a square dropped on a slab at rest (it lies ON it); six
    pieces dropped on one place from six heights, spinning; a triangle thrown along the ground into a slab"""
    out = [[[[0, 0.25, 0, 0, 0, 0, 0, 0, 0, 0, 0], [0.7, 0.25, 0.4, 0, 0, 0, 0, 0.6, 0, 0, 0]], [SQ, SQ], [0.25, 0.25], [1, 1], [4, 4]],
           [[[0, 0.25, 0, 0, 0, 0, 0, 0, 0, 0, 1], [0.5, 6, -0.3, 0, 0, 0, 0, 0.3, 0, 1.5, 0]], [BIG, SQ], [0.25, 0.25], [2, 1], [24, 4]],
           [[[0.1 * k, 2 + 2.5 * k, 0.07 * k * k, 0.3 * k, 0, -0.2 * k, 0, 0.5 * k, 2.0 - k, 0.7 * k, 0] for k in range(6)],
            [SQ, TRI, SQ, BIG, TRI, SQ], [0.25] * 6, [1, 1.05, 1, 2, 1.05, 1], [4, 1.6, 4, 24, 1.6, 4]],
           [[[0, 0.25, 0, 0, 0, 0, 0, 0, 0, 0, 1], [-9, 0.25, 0.5, 30, 0, 0, 0, 0, 0, 3, 0]], [BIG, TRI], [0.25, 0.25], [2, 1.05], [24, 1.6]]]
    # each pile at three frame rates, each with its own frame yaw and play scale (the pile is made that much larger: the same flight)
    made_ = []
    for p in out:
        for dt, base, turn, unit in ((1 / 60, 0.0, 0.0, 1.0), (1 / 30, -1.5, 0.7, 1.0), (1 / 144, 0.0, -2.1, 3.0)):
            st = [[s[0] * unit, s[1] * unit, s[2] * unit, s[3] * unit, s[4] * unit, s[5] * unit, *s[6:]] for s in p[0]]
            made_.append([st, [[v * unit for v in sh] for sh in p[1]], [h * unit for h in p[2]], [w * unit for w in p[3]], p[4], dt, 120.0 * unit, base * unit,
                          int(round(3.0 / dt)), turn, unit])
    return made_


LUAU_MEET = """
local out = {}
for i, c in serde.decode("json", fs.readFile(process.args[1])) do
	local s, trail = c[1], {}
	for n = 1, c[9] do
		s = debrisMeet(s, c[2], c[3], c[4], c[5], c[6], c[7], c[8], c[10], c[11])
		trail[n] = s
	end
	out[i] = trail
end
print(serde.encode("json", out))
"""
JS_MEET = """
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(cases.map(c => { let s = c[0]; const trail = []; for (let n = 0; n < c[8]; n++) { s = debrisMeet(s, c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[9], c[10])[0]; trail.push(s); } return trail; })));
"""


FLAG_LUAU = """
local out = {}
for _, c in serde.decode("json", fs.readFile(process.args[1])) do
	local s, _, overlapped = debrisMeet(c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8], c[9], c[10])
	table.insert(out, { overlapped, s })
end
print(serde.encode("json", out))
"""
FLAG_JS = """
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(cases.map(c => { const m = debrisMeet(c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8], c[9]); return [m[2], m[0]]; })));
"""


def flag_parity(root):
    """the EARLY STOP's own question, asked of the game's rule and the player's: two pieces at rest lying 0.5 studs deep
    in each other, stepped by a step too short to push them (slow motion, the part of a step before a hit-stop) - the
    pieces do not move, and BOTH must say they still lie in each other (the review: the early stop was taken then and
    they were never parted); apart, both must say they do not"""
    sq = [-1, -1, 1, -1, 1, 1, -1, 1]
    deep = [[0.0, 0.25, 0.0, 0, 0, 0, 0, 0, 0, 0, 1], [1.5, 0.25, 0.0, 0, 0, 0, 0, 0, 0, 0, 1]]
    far = [[0.0, 0.25, 0.0, 0, 0, 0, 0, 0, 0, 0, 1], [5.0, 0.25, 0.0, 0, 0, 0, 0, 0, 0, 0, 1]]
    asked = [[st, [sq, sq], [0.25, 0.25], [1.0, 1.0], [4.0, 4.0], dt, 120.0, 0.0, 0.0, 1.0] for st in (deep, far) for dt in (0.0, 2e-4, 1 / 60)]
    data = os.path.join(root, "flags.json")
    with open(data, "w", encoding="utf-8") as fh:
        json.dump(asked, fh)
    luau, js = os.path.join(root, "game_flag.luau"), os.path.join(root, "player_flag.cjs")
    with open(luau, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(LUAU_HEAD + cut(STAGE, "local function debrisStep(", "-- (end of debrisMeet)") + "\n" + FLAG_LUAU)
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(cut(PLAYER, "function debrisStep(", "// (end of debrisMeet)") + "\n" + FLAG_JS)
    want = [True, True, True, False, False, False]
    problems = []
    for who, cmd in (("the game (VfxStage.luau)", ["lune", "run", luau, data]), ("the player (player.js)", ["node", js, data])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False, cwd=ROOT)
            got = json.loads(r.stdout.strip().splitlines()[-1])
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
            problems.append(f"{who}'s overlap flag could not be asked: {type(e).__name__}: {str(e)[:120]}")
            continue
        flags = [bool(g[0]) for g in got]
        if flags != want:
            problems.append(f"{who} says pieces lie in each other {flags} where they do {want} (steps 0, 0.0002 and a frame; deep then apart)")
        if got[1][1] != deep:
            problems.append(f"{who} moved pieces in a step too short to push them (the premise of the case)")
    return problems


def meet_parity(root, plan):
    """-> (problems, cases, how many end with a piece ON another, how many were pushed apart)"""
    asked = piles()
    made_ = [settle.start(pc, plan["size"][2]) for pc in plan["pieces"]]   # and a real slab's own pieces, all at once
    asked.append([[m[0] for m in made_], [m[3] for m in made_], [m[1] for m in made_], [m[2] for m in made_], [pc["area"] for pc in plan["pieces"]], 1 / 60, 120.0, 0.0, 180, 0.4, 1.0])
    data = os.path.join(root, "piles.json")
    with open(data, "w", encoding="utf-8") as fh:
        json.dump(asked, fh)
    luau, js = os.path.join(root, "game_meet.luau"), os.path.join(root, "player_meet.cjs")
    with open(luau, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(LUAU_HEAD + cut(STAGE, "local function debrisStep(", "-- (end of debrisMeet)") + "\n" + LUAU_MEET)
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(cut(PLAYER, "function debrisStep(", "// (end of debrisMeet)") + "\n" + JS_MEET)
    problems, got = [], {}
    for who, cmd in (("the game (VfxStage.luau)", ["lune", "run", luau, data]), ("the player (player.js)", ["node", js, data])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False, cwd=ROOT)
            got[who] = json.loads(r.stdout.strip().splitlines()[-1])
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
            problems.append(f"{who} could not be asked how pieces meet: {type(e).__name__}: {str(e)[:120]}")
    want, stacked, parted = [], 0, 0
    for s, shapes, hs, ws, areas, dt, g, base, steps, turn, unit in asked:
        trail, floor, first = [], [base] * len(s), [list(x) for x in s]
        for _ in range(steps):
            s, fl = settle.meet(s, shapes, hs, ws, areas, dt, g, base, turn, unit)
            floor = floor if fl is None else fl
            trail.append(s)
        want.append(trail)
        stacked += any(f > base + 1e-6 and x[10] == 1 for f, x in zip(floor, s))
        deep = max((settle.apart(settle.lying(s[i], shapes[i], turn), settle.lying(s[j], shapes[j], turn))[0] for i in range(len(s)) for j in range(i + 1, len(s))
                    if abs(s[i][1] - s[j][1]) < 1e-4), default=0.0)
        before = max((settle.apart(settle.lying(first[i], shapes[i], turn), settle.lying(first[j], shapes[j], turn))[0] for i in range(len(s)) for j in range(i + 1, len(s))
                      if abs(first[i][1] - first[j][1]) < 1e-4), default=0.0)
        parted += before > settle.SKIN * unit + 1e-6
        if deep > 2 * settle.SKIN * unit:
            problems.append(f"a made pile ends with two pieces on one level {deep:.3f} studs deep in each other (dt {dt:.4f})")
    for who, answers in got.items():
        off = None
        for n, (mine, theirs) in enumerate(zip(want, answers)):
            if len(theirs) != len(mine) or any(len(a) != len(b) or any(len(q) != 11 or any(abs(float(x) - float(y)) > 1e-7 for x, y in zip(p, q)) for p, q in zip(a, b))
                                         for a, b in zip(mine, theirs)):
                off = n if off is None else off
        if len(answers) != len(want) or off is not None:
            problems.append(f"{who} lets pieces meet another way (first in pile {off}: {len(asked[off or 0][0])} pieces, dt {asked[off or 0][5]:.4f})")
    if stacked < 3:
        problems.append(f"only {stacked} made piles end with a piece at rest ON another: the cases do not reach that part of the rule")
    if parted < 3:
        problems.append(f"only {parted} made piles start with pieces in each other: the cases do not reach the push")
    return problems, len(asked), stacked


def main(argv):
    case = argv[0] if argv else "good"
    root = os.path.join("build", "selftest", f"vfx_settle_{case}_{os.getpid()}")
    try:
        if case == "parity":
            try:
                problems, n, rested = parity(root)
                made(root)
                with open(os.path.join(root, "made_slab.json"), encoding="utf-8") as fh:
                    slab = json.load(fh)
                more, piles_n, stacked = meet_parity(root, slab)
                problems += more
                more, starts_n = start_parity(root, slab)
                problems += more
                problems += flag_parity(root)
            except ValueError as e:
                problems, n, rested, piles_n, stacked, starts_n = [str(e)], 0, 0, 0, 0, 0
            if problems:
                return say("fail", "settle parity: " + "; ".join(problems), "src/kit/VfxStage.luau debrisStep + debrisMeet, kit/vfx/player/player.js debrisStep + debrisMeet and kit/vfx/settle.py step + meet are ONE rule")
            return say("pass", f"settle parity: the game's debrisStep, the player's and the rule fly the same flight, step by step, in {n} cases ({rested} come to rest); "
                       f"and pieces MEET the same way in all three, 3 seconds of {piles_n} piles ({stacked} end with a piece lying on another); "
                       f"and every piece STARTS where it sat in the slab - its place, speeds, size and OUTLINE - the same way in all three ({starts_n} starts), "
                       f"and the frame's yaw the pieces are met by is read the same by Roblox's CFrame and by three.js ({len(TURNS)} turns, tilted ones too); and both runtimes' rule says when pieces still lie in each other, which the early stop asks (a step too short to push them too)", "none")
        os.makedirs(root, exist_ok=True)
        made(root)
        if case == "through":
            # the OLD flight (every piece by itself: they pass through each other) held to the new check
            with open(os.path.join(root, "made_slab.json"), encoding="utf-8") as fh:
                plan = json.load(fh)
            rows, _ = settle.check(settle.fly(plan, 2.5, alone=True), 2.5)
            bad = [c for c in rows if not c["ok"]]
            if not bad:
                return say("pass", "settle through: pieces that pass through each other and lie in each other were let through", "kit/vfx/settle.py check (lies_apart)")
            return say("fail", "settle through: " + "; ".join(f"{c['name']} = {c['value']} (needs {c['limit']})" for c in bad), bad[0]["fix"])
        if case == "late":
            code, said = call(settle, ["made_slab", "--plans-dir", root, "--life", "0.5"])
            if code == 0:
                return say("pass", "settle late: pieces still in the air when the fade starts were let through", "kit/vfx/settle.py check")
            return say("fail", "settle late: " + said["summary"][:300], said["next_action"][:200])
        problems, lasts = [], {}
        for fps in (60, 30, 144):
            code, said = call(settle, ["made_slab", "--plans-dir", root, "--life", "2.5", "--fps", str(fps)])
            if code != 0:
                problems.append(f"at {fps} fps: " + said["summary"][:200])
            else:
                lasts[fps] = said["last_rest"]
                if not (0.2 < said["last_rest"] < 2.0 and said["furthest"] > 1):
                    problems.append(f"at {fps} fps the last piece rests at {said['last_rest']} s, the furthest {said['furthest']} studs away")
        if len(lasts) == 3 and max(abs(lasts[f] - lasts[60]) for f in lasts) > 0.6:
            problems.append(f"the flight depends on the frame rate: the last piece rests at {lasts}")
        with open(os.path.join(root, "made_slab.json"), encoding="utf-8") as fh:
            plan = json.load(fh)
        alone = max(f["deep"] for f in settle.fly(plan, 2.5, alone=True))
        if alone < 0.2:
            problems.append(f"the made slab's pieces flown one by one end only {alone:.3f} studs in each other: the case does not show pieces meeting")
        for fps in (60, 30, 144):
            deep = max(f["deep"] for f in settle.fly(plan, 2.5, fps=fps))
            if deep > 2 * settle.SKIN:
                problems.append(f"at {fps} fps two pieces at rest lie {deep:.3f} studs deep in each other")
        if problems:
            return say("fail", "settle good: " + "; ".join(problems), "kit/vfx/settle.py")
        return say("pass", f"settle good: a made slab's 14 pieces all come to rest lying flat before the fade, the last at {lasts[60]} s; "
                   f"within 0.6 s of that at 30 and 144 frames a second (pieces that meet land a little differently at each); no two lie in each other at any of the three", "none")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
