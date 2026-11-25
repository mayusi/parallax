#!/usr/bin/env python3
"""The self-test of the lens flare (kit/vfx/flare.py, the lens layer's "flare"; the VFX methods audit, stage 6).

    python kit/selftest/vfx/flare/run.py good     the rule's marks for lights across the screen, at its edge and off
                                                  it, at three screen shapes: every one passes the flare's own checks
                                                  (the glow on the light, every ghost on the line through the light
                                                  and the middle, ghosts on both sides, nothing for a light off the
                                                  screen); and the three pictures (kit/vfx/lens.py) are what they are
                                                  said to be: the glow hot in the middle and clear at its edge, the
                                                  ghost a rim brighter than its middle, the streak long and thin
    python kit/selftest/vfx/flare/run.py stray    one ghost moved off the line: the checks must catch it (exit 1)
    python kit/selftest/vfx/flare/run.py parity   the marks asked of the GAME's function (the text of flareMarks in
                                                  src/kit/VfxStage.luau, run by lune), of the PLAYER's (player.js, run
                                                  by node) and of the rule: the same marks from all three

Nothing here draws a flare in Roblox or in the browser player: where the pictures land on a real screen is not checked.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import flare  # noqa: E402
import lens  # noqa: E402

STAGE = os.path.join(ROOT, "src", "kit", "VfxStage.luau")
PLAYER = os.path.join(ROOT, "kit", "vfx", "player", "player.js")
LIGHTS = [(0.25, 0.3), (0.5, 0.5), (0.9, 0.1), (0.02, 0.98), (0.5, 0.05), (1.0, 0.5), (1.1, 0.5), (0.5, -0.12), (1.2, 1.2), (-0.4, 0.5), (0.7, 0.62)]
FLARES = [{}, {"ghosts": 8, "size": 0.3, "streak": 0.8, "squeeze": 2.2}, {"ghosts": 0, "streak": 0.4}, {"ghosts": 5.9, "size": 0.05, "squeeze": 9},
          {"ghosts": 3, "streak": 0}, {"ghosts": 12, "squeeze": 0.2, "streak": 2}]
ASPECTS = [16 / 9, 4 / 3, 9 / 19.5]


def cases():
    return [[lx, ly, a, f] for lx, ly in LIGHTS for a in ASPECTS for f in FLARES]


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def bad_rows(found, lx, ly, f):
    return [c for c in flare.check(found, lx, ly, f) if not c["ok"]]


def pictures():
    """-> problems with the three pictures the flare draws"""
    problems = []
    _, g = lens.glow()
    n = g.shape[0]
    if not (g[n // 2, n // 2] > 0.9 and g[n // 2, 2] < 0.02 and g[2, n // 2] < 0.02 and g[2, 2] < 0.001):
        problems.append("the glow is not hot in the middle and clear at its edge (a square would show round the light)")
    _, gh = lens.ghost()
    rim, mid = gh[n // 2, int(n * 0.92)], gh[n // 2, n // 2]
    if not (rim > mid * 1.5 and 0.1 < mid < 0.5 and gh[2, 2] < 0.001 and gh[n // 2, n - 2] < 0.02):
        problems.append("the ghost is not a faint disc with a brighter rim, clear outside it")
    _, st = lens.streak()
    rows = (st > 0.1).any(axis=1).sum() / n
    cols = (st > 0.1).any(axis=0).sum() / n
    if not (cols > 0.6 and rows < 0.2 and st[n // 2, n // 2] > 0.9 and st[n // 2, 2] < 0.05 and st[2, n // 2] < 0.01):
        problems.append(f"the streak is not a long thin level line (it covers {cols:.2f} of the width, {rows:.2f} of the height)")
    return problems


LUAU_HEAD = 'local fs = require("@lune/fs")\nlocal serde = require("@lune/serde")\nlocal process = require("@lune/process")\n'
LUAU_TAIL = """
local out = {}
for i, c in serde.decode("json", fs.readFile(process.args[1])) do
	out[i] = flareMarks(c[1], c[2], c[3], c[4])
end
print(serde.encode("json", out))
"""
JS_TAIL = """
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(cases.map(c => flareMarks(c[0], c[1], c[2], c[3]))));
"""


def cut(path, first, end):
    text = open(path, encoding="utf-8").read()
    a, b = text.find(first), text.find(end)
    if a < 0 or b < a:
        raise ValueError(f"{os.path.relpath(path, ROOT)} has no flareMarks between its two marks")
    return text[a:text.rfind("\n", a, b)]


def parity(root):
    """-> problems. The game's function and the player's, each as its own file's TEXT, against the rule"""
    asked = cases()
    os.makedirs(root, exist_ok=True)
    data = os.path.join(root, "cases.json")
    with open(data, "w", encoding="utf-8") as fh:
        json.dump(asked, fh)
    luau, js = os.path.join(root, "game.luau"), os.path.join(root, "player.cjs")
    with open(luau, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(LUAU_HEAD + cut(STAGE, "local FLARE_K = {", "-- (end of flareMarks)") + "\n" + LUAU_TAIL)
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(cut(PLAYER, "const FLARE_K = [", "// (end of flareMarks)") + "\n" + JS_TAIL)
    problems, got = [], {}
    for who, cmd in (("the game (VfxStage.luau)", ["lune", "run", luau, data]), ("the player (player.js)", ["node", js, data])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False, cwd=ROOT)
            got[who] = json.loads(r.stdout.strip().splitlines()[-1])
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
            problems.append(f"{who} could not be asked: {type(e).__name__}: {str(e)[:120]}")
    # the player as a WHOLE must parse (as the module it is: `node --check player.js` passes a broken one) - a flare
    # that breaks the draw loop breaks every effect's preview, and cutting flareMarks out of the text would not see it
    whole = os.path.join(root, "player_whole.mjs")
    shutil.copyfile(PLAYER, whole)
    try:
        r = subprocess.run(["node", "--check", whole], capture_output=True, text=True, timeout=120, check=False)
        if r.returncode != 0:
            problems.append("kit/vfx/player/player.js does not parse: " + " ".join(r.stderr.split())[:200])
    except (OSError, subprocess.TimeoutExpired) as e:
        problems.append(f"the player could not be parsed: {type(e).__name__}")
    want = [flare.marks(*c) for c in asked]
    keys = ("kind", "i", "x", "y", "w", "h", "a", "c")
    for who, answers in got.items():
        if len(answers) != len(want):
            problems.append(f"{who} answered {len(answers)} of {len(want)} cases")
            continue
        off = []
        for n, (mine, theirs) in enumerate(zip(want, answers)):
            theirs = theirs if isinstance(theirs, list) else []  # (an empty Luau table is written {})
            if len(mine) != len(theirs) or any(abs(float(a[k]) - float(b.get(k, 1e9))) > 1e-9 for a, b in zip(mine, theirs) for k in keys):
                off.append(n)
        if off:
            lx, ly, a, f = asked[off[0]]
            problems.append(f"{who} places other marks in {len(off)} of {len(want)} cases: first for a light at {lx},{ly}, aspect {a:.3f}, flare {json.dumps(f)}")
    return problems, len(asked)


def main(argv):
    case = argv[0] if argv else "good"
    if case == "parity":
        root = os.path.join("build", "selftest", f"vfx_flare_parity_{os.getpid()}")
        try:
            problems, n = parity(root)
        except ValueError as e:
            problems, n = [str(e)], 0
        finally:
            shutil.rmtree(root, ignore_errors=True)
        if problems:
            return say("fail", "flare parity: " + "; ".join(problems), "src/kit/VfxStage.luau flareMarks, kit/vfx/player/player.js flareMarks and kit/vfx/flare.py marks are ONE rule")
        return say("pass", f"flare parity: the game's flareMarks, the player's and the rule place the same marks in {n} cases", "none")
    if case == "stray":
        lx, ly, f = 0.25, 0.3, {"ghosts": 5, "streak": 0.6}
        found = flare.marks(lx, ly, 16 / 9, f)
        ghost = [m for m in found if m["kind"] == 3][2]
        ghost["y"] += 0.04  # a ghost that does not swing with the light
        rows = bad_rows(found, lx, ly, f)
        if rows:
            return say("fail", "flare stray: " + "; ".join(f"{c['name']} = {c['value']} (needs {c['limit']})" for c in rows), rows[0]["fix"])
        return say("pass", "flare stray: a ghost off the line was let through", "kit/vfx/flare.py check")
    problems = []
    seen = 0
    for lx, ly, a, f in cases():
        found = flare.marks(lx, ly, a, f)
        seen += len(found)
        for c in bad_rows(found, lx, ly, f):
            problems.append(f"a light at {lx},{ly} (aspect {a:.2f}, flare {json.dumps(f)}): {c['name']} = {c['value']}")
        if max(abs(lx - 0.5), abs(ly - 0.5)) <= 0.5 and not found:
            problems.append(f"a light at {lx},{ly} is on the screen and draws nothing")
    # the ghosts swing: a light moved across the screen moves the far ghosts the other way
    left = [m for m in flare.marks(0.2, 0.5, 16 / 9, {"ghosts": 8}) if m["kind"] == 3]
    right = [m for m in flare.marks(0.8, 0.5, 16 / 9, {"ghosts": 8}) if m["kind"] == 3]
    if not (left[-1]["x"] > 0.5 > right[-1]["x"] and left[0]["x"] < 0.5 < right[0]["x"]):
        problems.append("the ghosts do not swing about the middle when the light crosses the screen")
    problems += pictures()
    if problems:
        return say("fail", "flare good: " + "; ".join(problems[:4]) + (f" (+{len(problems) - 4} more)" if len(problems) > 4 else ""), "kit/vfx/flare.py marks / kit/vfx/lens.py")
    return say("pass", f"flare good: {len(cases())} lights and flares ({seen} marks) keep the glow on the light and every ghost on the line through the middle; "
               "the far ghosts swing against the light; the glow, the ghost and the streak are what they are said to be", "none")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
