#!/usr/bin/env python3
"""The self-test of FORCED PERSPECTIVE (kit/vfx/forced.py, a mesh layer's "forced"; the VFX methods audit, stage 13).

    python kit/selftest/vfx/forced/run.py good     the rule at distances from 1 to 4,000 studs: with keep 1 the layer is
                                                   as large ON THE SCREEN as at its ref wherever the multiplier is not
                                                   held by min / max; with keep 0.5 it shrinks with distance, but less
                                                   than the lens would have it; with a negative keep more; the
                                                   multiplier is 1 at ref, never leaves min..max, and never falls as
                                                   the distance grows (keep above 0); the real command says the same
    python kit/selftest/vfx/forced/run.py off      a block with keep 0 (it does nothing): the command must refuse it,
                                                   saying "does nothing" (exit 1)
    python kit/selftest/vfx/forced/run.py parity   the multiplier asked of the GAME's rule (the text of forcedScale in
                                                   src/kit/VfxStage.luau, run by lune), of the PLAYER's (player.js, run
                                                   by node) and of forced.py at 600 distance / block pairs: the same
                                                   number from all three; and the player parses as the module it is

Nothing here sizes a layer in Roblox or in the browser player.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import forced  # noqa: E402

STAGE = os.path.join(ROOT, "src", "kit", "VfxStage.luau")
PLAYER = os.path.join(ROOT, "kit", "vfx", "player", "player.js")
DISTS = [0.0, 0.0005, 1, 2.5, 7, 10, 19.9, 20, 40, 41, 80, 159, 160, 161, 400, 1000, 4000, 1e6, 33.3, 55.5]
BLOCKS = [{"ref": 40}, {"ref": 40, "keep": 1, "min": 0.25, "max": 4}, {"ref": 40, "keep": 0.5}, {"ref": 40, "keep": -1}, {"ref": 12, "keep": 0.3, "min": 0.5, "max": 2},
          {"ref": 300, "keep": 1, "min": 0.01, "max": 100}, {"ref": 40, "keep": -0.4, "min": 1, "max": 1}, {"ref": 1, "keep": 1}, {"ref": 5000, "keep": 0.75, "max": 9},
          {"ref": 40, "keep": 0}] + [{"ref": 40, "keep": k / 10} for k in range(-10, 11)][:20]


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def call(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = forced.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def cut(path, first, end):
    text = open(path, encoding="utf-8").read()
    a, b = text.find(first), text.find(end)
    if a < 0 or b < a:
        raise ValueError(f"{os.path.relpath(path, ROOT)} has no forcedScale between its two marks")
    return text[a:text.rfind("\n", a, b)]


LUAU_HEAD = 'local fs = require("@lune/fs")\nlocal serde = require("@lune/serde")\nlocal process = require("@lune/process")\n'
LUAU_TAIL = """
local out = {}
for i, c in serde.decode("json", fs.readFile(process.args[1])) do
	out[i] = forcedScale(c[1], c[2])
end
print(serde.encode("json", out))
"""
JS_TAIL = """
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(cases.map(c => forcedScale(c[0], c[1]))));
"""


def parity(root):
    asked = [[d, f] for f in BLOCKS for d in DISTS]
    os.makedirs(root, exist_ok=True)
    data = os.path.join(root, "cases.json")
    with open(data, "w", encoding="utf-8") as fh:
        json.dump(asked, fh)
    luau, js = os.path.join(root, "game.luau"), os.path.join(root, "player.cjs")
    with open(luau, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(LUAU_HEAD + cut(STAGE, "local function forcedScale(", "-- (end of forcedScale)") + "\n" + LUAU_TAIL)
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(cut(PLAYER, "function forcedScale(", "// (end of forcedScale)") + "\n" + JS_TAIL)
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
    want = [forced.scale(d, f) for d, f in asked]
    for who, answers in got.items():
        off = [n for n, (a, b) in enumerate(zip(want, answers)) if not isinstance(b, (int, float)) or abs(a - b) > 1e-9 * max(1, abs(a))]
        if len(answers) != len(want) or off:
            d, f = asked[off[0]] if off else (None, None)
            problems.append(f"{who} gives another multiplier in {len(off)} of {len(want)} cases (first: {d} studs, {json.dumps(f)})")
    if len(set(round(w, 6) for w in want)) < 60:
        problems.append("the cases ask for too few different multipliers to tell the three apart")
    return problems, len(asked)


def main(argv):
    case = argv[0] if argv else "good"
    if case == "parity":
        root = os.path.join("build", "selftest", f"vfx_forced_parity_{os.getpid()}")
        try:
            problems, n = parity(root)
        except ValueError as e:
            problems, n = [str(e)], 0
        finally:
            shutil.rmtree(root, ignore_errors=True)
        if problems:
            return say("fail", "forced parity: " + "; ".join(problems), "src/kit/VfxStage.luau forcedScale, kit/vfx/player/player.js forcedScale and kit/vfx/forced.py scale are ONE rule")
        return say("pass", f"forced parity: the game's forcedScale, the player's and the rule give the same multiplier in {n} cases", "none")
    if case == "off":
        code, said = call(["--keep", "0"])
        if code == 0:
            return say("pass", "forced off: a block that does nothing was let through", "kit/vfx/forced.py checked")
        return say("fail", "forced off: " + said["summary"][:300], said["next_action"][:200])
    problems = []
    dists = [1, 3, 10, 20, 39, 40, 41, 80, 160, 400, 4000]
    hold = {"ref": 40, "keep": 1, "min": 0.25, "max": 4}
    for d in dists:
        s = forced.scale(d, hold)
        on_screen = s * 40 / d  # the size on the screen against its size at ref (a thing's size on screen goes as size / distance)
        if 0.25 < s < 4 and abs(on_screen - 1) > 1e-9:
            problems.append(f"keep 1: at {d} studs the layer is {on_screen:.3f} of its on-screen size at ref")
        if not 0.25 <= s <= 4:
            problems.append(f"keep 1: the multiplier {s} at {d} studs left min..max")
    if abs(forced.scale(40, hold) - 1) > 1e-12:
        problems.append("the multiplier is not 1 at ref")
    half, away = {"ref": 40, "keep": 0.5, "min": 0.01, "max": 100}, {"ref": 40, "keep": -0.5, "min": 0.01, "max": 100}
    for d in (80, 160, 400):
        lens = 40 / d                      # what the lens alone makes of it on the screen
        mid = forced.scale(d, half) * 40 / d
        far = forced.scale(d, away) * 40 / d
        if not lens < mid < 1:
            problems.append(f"keep 0.5: at {d} studs the layer is {mid:.3f} on screen (the lens alone: {lens:.3f}): not between the lens and held")
        if not far < lens:
            problems.append(f"keep -0.5: at {d} studs the layer does not shrink faster than the lens ({far:.3f} against {lens:.3f})")
    for f in (hold, half):
        got = [forced.scale(d, f) for d in dists]
        if any(b < a - 1e-12 for a, b in zip(got, got[1:])):
            problems.append(f"keep {f['keep']}: the multiplier falls as the distance grows")
    code, said = call(["--ref", "40", "--keep", "1", "--at", "10,40,160"])
    if code != 0 or [r["multiplier"] for r in said.get("rows", [])] != [0.25, 1.0, 4.0]:
        problems.append("the command does not say x0.25, x1, x4 at 10, 40 and 160 studs for ref 40, keep 1")
    if problems:
        return say("fail", "forced good: " + "; ".join(problems[:4]), "kit/vfx/forced.py scale")
    return say("pass", "forced good: with keep 1 a layer is as large on the screen as at its ref from 10 to 160 studs (held by min / max beyond); keep 0.5 sits "
               "between the lens and held, a negative keep shrinks faster than the lens; the multiplier is 1 at ref and never falls with distance", "none")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
