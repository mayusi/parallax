"""run.py - the dissolve's selftest cases (kit selftest): a MADE texture (a streak skin that tiles along U, two
tones, fading out at its top and bottom) baked by the real command into a made project folder.

    python kit/selftest/vfx/dissolve/run.py good   16 cells: cell 0 IS the texture, the last cell is empty, nothing
                                                   comes back, every cell removes its share, the middle cell is cut
                                                   into pieces (its pixels are kept or gone, few in between), the
                                                   burning edge sits on the front and nowhere else, and every cell
                                                   still tiles; the kit's sheet packer packs and passes it (1024 px,
                                                   4x4) with the texture's colours kept; with its frames gone the build
                                                   step bakes the same cells again, with its source texture changed it
                                                   bakes new ones, and untouched it bakes nothing
    python kit/selftest/vfx/dissolve/run.py fade   the same texture with a front as wide as the whole pattern: an even
                                                   fade, NOT a break-up - this case fails, naming "an even fade", and
                                                   leaves no spec and no frames behind

    python kit/selftest/vfx/dissolve/run.py parity the cell a mesh's sheet shows, asked of the GAME's own function (the
                                                   text of sheetFrame in src/kit/VfxStage.luau, run by lune) and of the
                                                   PLAYER's (kit/vfx/player/player.js, run by node) over one sweep of
                                                   lives, windows ("over"), sheet sizes and looping clocks: both must
                                                   give the cell this file works out by hand, everywhere

What each part does when it is wrong is proven part by part in kit/test/python/test_vfx_dissolve.py.
Prints one JSON line {schema, status, summary, next_action}; everything is written to a folder of this run's own
under build/selftest/, removed at the end.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import dissolve  # noqa: E402
import fxfinish  # noqa: E402

BODY, CORE = (1.0, 0.45, 0.15), (1.0, 0.85, 0.35)


def skin(n=256, shift=0.0):
    """the made texture, straight RGBA 0-1: three slanted streaks that wrap along U, a pale core inside an orange
    body, alpha falling to nothing at the top and bottom rows"""
    yy, xx = np.mgrid[0:n, 0:n] / float(n)
    wave = 0.5 + 0.5 * np.sin(2 * np.pi * (xx * 3 + yy + shift))
    alpha = np.clip(np.sin(np.pi * (yy + 0.5 / n)) ** 0.6 * (0.35 + 0.65 * wave), 0, 1)
    core = (wave > 0.75)[..., None]
    rgb = np.where(core, np.array(CORE), np.array(BODY))
    return np.dstack([rgb, alpha])


def save(px, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray((np.clip(px, 0, 1) * 255 + 0.5).astype(np.uint8), "RGBA").save(path)


def call(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = dissolve.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def load(fdir):
    files = sorted(f for f in os.listdir(fdir) if f.endswith(".npy"))
    return [np.load(os.path.join(fdir, f)).astype(np.float64) for f in files]


ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
STAGE = os.path.join(ROOT, "src", "kit", "VfxStage.luau")
PLAYER = os.path.join(ROOT, "kit", "vfx", "player", "player.js")
END = "(end of sheetFrame)"


def sweep():
    """the cases both functions are asked: (mode, over or None, fps, u, age, frames, start)"""
    cases = []
    for frames in (4, 16, 64):
        for over in (None, (0.6, 1.0), (0.0, 0.5), (0.25, 0.75), (0.9, 0.95)):
            for i in range(0, 201):
                cases.append(("OneShot", over, 24, i / 200.0, 0.0, frames, 0))
        for fps, start in ((12, 0), (24, 5), (30, 63)):
            for i in range(0, 120):
                cases.append(("Loop", None, fps, 0.5, i * 0.031, frames, start))
    return cases


def by_hand(mode, over, fps, u, age, frames, start):
    if mode == "OneShot":
        uu = u
        if over is not None:
            uu = min(1.0, max(0.0, (u - over[0]) / max(over[1] - over[0], 1e-4)))
        return min(int(uu * frames // 1), frames - 1)
    return (int(age * fps // 1) + start) % frames


def cut(path, first):
    text = open(path, encoding="utf-8").read()
    a, b = text.find(first), text.find(END)
    if a < 0 or b < a:
        raise ValueError(f"{os.path.relpath(path, ROOT)} has no sheetFrame between its two marks")
    return text[a:text.rfind("\n", a, b)]


LUAU_HEAD = 'local fs = require("@lune/fs")\nlocal serde = require("@lune/serde")\nlocal process = require("@lune/process")\n'
LUAU_TAIL = """
local out = {}
for i, c in serde.decode("json", fs.readFile(process.args[1])) do
	local fb: any = { mode = c[1], fps = c[3] }
	if type(c[2]) == "table" then
		fb.over = c[2]
	end
	out[i] = sheetFrame(fb, c[4], c[5], c[6], c[7])
end
print(serde.encode("json", out))
"""
JS_TAIL = """
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(cases.map(c => sheetFrame(c[1] ? { mode: c[0], fps: c[2], over: c[1] } : { mode: c[0], fps: c[2] }, c[3], c[4], c[5], c[6]))));
"""


def parity(root):
    """-> (problems, cases asked). The game's function and the player's, each as its own file's TEXT, on the same cases"""
    cases = sweep()
    # (a window is written [u0, u1]; no window is written false: a JSON null inside a list reads oddly in Luau)
    rows = [[m, list(o) if o else False, f, u, age, n, st] for m, o, f, u, age, n, st in cases]
    os.makedirs(root, exist_ok=True)
    data = os.path.join(root, "cases.json")
    with open(data, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    luau = os.path.join(root, "game.luau")
    with open(luau, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(LUAU_HEAD + cut(STAGE, "local function sheetFrame(") + "\n" + LUAU_TAIL)
    js = os.path.join(root, "player.cjs")
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(cut(PLAYER, "function sheetFrame(") + "\n" + JS_TAIL)
    problems, got = [], {}
    for who, cmd in (("the game (VfxStage.luau)", ["lune", "run", luau, data]), ("the player (player.js)", ["node", js, data])):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
            got[who] = json.loads(r.stdout.strip().splitlines()[-1])
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
            problems.append(f"{who} could not be asked: {type(e).__name__}: {str(e)[:120]}")
    want = [by_hand(*c) for c in cases]
    for who, cells in got.items():
        if len(cells) != len(want):
            problems.append(f"{who} answered {len(cells)} of {len(want)} cases")
            continue
        off = [i for i, (x, y) in enumerate(zip(cells, want)) if x != y]
        if off:
            m, o, f, u, age, n, st = cases[off[0]]
            problems.append(f"{who} shows another cell in {len(off)} of {len(want)} cases: first at mode {m}, over {o}, u {u}, age {age}, "
                            f"{n} cells: cell {cells[off[0]]}, by hand {want[off[0]]}")
    return problems, len(want)


def main(argv):
    case = argv[0] if argv else "good"
    if case == "parity":
        root = os.path.join("build", "selftest", f"vfx_dissolve_parity_{os.getpid()}")
        try:
            problems, n = parity(root)
        except ValueError as e:
            problems, n = [str(e)], 0
        finally:
            shutil.rmtree(root, ignore_errors=True)
        if problems:
            print(json.dumps({"schema": 1, "status": "fail", "summary": "dissolve parity: " + "; ".join(problems), "next_action": "src/kit/VfxStage.luau sheetFrame and kit/vfx/player/player.js sheetFrame must be the same rule"}))
            return 1
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"dissolve parity: the game's sheetFrame and the player's show the same cell in all {n} cases (lives, windows, sheet sizes, looping clocks)", "next_action": "none"}))
        return 0
    root = os.path.join("build", "selftest", f"vfx_dissolve_{case}_{os.getpid()}")
    built, specs, frames, look = (os.path.join(root, d) for d in ("textures", "specs", "fxlab", "look"))
    dirs = ["--textures-dir", built, "--specs-dir", specs, "--frames-dir", frames, "--look-dir", look]
    problems = []
    try:
        src = skin()
        save(src, os.path.join(built, "made_skin.png"))
        src = np.asarray(Image.open(os.path.join(built, "made_skin.png")).convert("RGBA"), dtype=np.float64) / 255.0  # (as the tool reads it)
        if case == "fade":
            code, verdict = call(["made_skin_dz", "--from", "made_skin", "--soft", "1", *dirs])
            left = os.path.isfile(os.path.join(specs, "made_skin_dz.json")) or os.path.isdir(os.path.join(frames, "made_skin_dz"))
            if code == 0 or left:
                print(json.dumps({"schema": 1, "status": "pass", "summary": "dissolve fade: an even fade was baked as a break-up" + (" and left files behind" if left else ""),
                                  "next_action": "kit/vfx/dissolve.py: the `breaks` check"}))
                return 0
            print(json.dumps({"schema": 1, "status": "fail", "summary": verdict["summary"], "next_action": verdict["next_action"]}))
            return 1
        code, verdict = call(["made_skin_dz", "--from", "made_skin", "--edge", "0.06", "--edge-color", "255,255,255", *dirs])
        if code != 0:
            problems.append(f"the good sheet was refused: {verdict['summary']}")
        else:
            cells = load(os.path.join(frames, "made_skin_dz"))
            spec = json.load(open(os.path.join(specs, "made_skin_dz.json"), encoding="utf-8"))
            alpha = src[..., 3]
            a = [c[..., 3] for c in cells]
            if len(cells) != 16 or spec.get("recipe") != "dissolve" or spec.get("grid") != 4 or spec.get("from") != "made_skin":
                problems.append(f"the spec is not a 16-cell dissolve of made_skin: {len(cells)} cells, {spec.get('recipe')}, grid {spec.get('grid')}")
            if float(np.abs(a[0] - alpha).max()) > 0.01:
                problems.append("cell 0 is not the texture")
            if float(a[-1].max()) > 0.004:
                problems.append("the last cell is not empty")
            if max(float((a[k + 1] - a[k]).max()) for k in range(15)) > 0.01:
                problems.append("a pixel came back after it had gone")
            held = alpha > 0.02
            share = [float(((x / np.maximum(alpha, 1e-6))[held] > 0.5).mean()) for x in a]  # the AREA each cell still shows
            steps = [share[k] - share[k + 1] for k in range(15)]
            if min(steps) < 0.025 or max(steps) > 0.11:
                problems.append(f"the cells do not remove even shares of the area: {min(steps):.3f} to {max(steps):.3f} (even = 0.067)")
            covered = alpha > 0.1
            ratio = a[8][covered] / alpha[covered]
            half = float(((ratio > 0.15) & (ratio < 0.85)).mean())
            if half > 0.2:
                problems.append(f"the middle cell is {half:.0%} half-transparent: a fade, not pieces")
            gone = float((ratio < 0.05).mean())
            if not 0.3 < gone < 0.7:
                problems.append(f"the middle cell has lost {gone:.0%} of the texture (about half was asked)")
            # the burning edge: white only near the front (pixels the next cells remove), never deep inside
            rgb = cells[8][..., :3] / np.maximum(a[8][..., None], 1e-3)  # (frames are premultiplied)
            white = (rgb.min(axis=2) > 0.9) & (a[8] > 0.2) & ~(src[..., :3].min(axis=2) > 0.9)
            if white.sum() < 50:
                problems.append("no burning edge in the middle cell")
            elif float((a[11][white] < 0.05).mean()) < 0.9:
                problems.append("the burning edge is not on the front: its pixels outlast three more cells")
            seam = max(float(np.abs(x[:, 0] - x[:, -1]).mean()) for x in a)
            if seam > 0.05:
                problems.append(f"a cell no longer tiles along U: a step of {seam:.3f} across its seam")
            # the kit's packer takes it, and the texture's colours come through
            img, grid, clipped, change, n = fxfinish.build("made_skin_dz", spec, frames)
            failed = [c["name"] for c in fxfinish.check(img, grid, clipped, change, n, False, want=spec["frames"]) if not c["ok"] and c["severity"] == "error"]
            sheet = np.asarray(img, dtype=np.float64) / 255.0
            if failed or img.size != (1024, 1024) or tuple(grid) != (4, 4):
                problems.append(f"the packer: {failed or 'no failed check'}, size {img.size}, grid {tuple(grid)}")
            first = sheet[:256, :256]
            body = (src[..., 3] > 0.6) & (src[..., 1] < 0.6)
            if float(np.abs(first[..., :3][body] - np.array(BODY)).max()) > 0.03:
                problems.append("the packed sheet changed the body's colour")
            if float(np.abs(first[..., 3] - alpha).max()) > 0.02:
                problems.append("the packed sheet's first cell is not the texture")
            # the build step: fresh frames are left alone, missing ones baked again the same, a changed source baked anew
            step = ["--specs", specs, "--out", frames, "--textures-dir", built]
            code, v = call(step)
            if code != 0 or v.get("baked"):
                problems.append(f"the build step baked a sheet that was current: {v['summary']}")
            shutil.rmtree(os.path.join(frames, "made_skin_dz"))
            code, v = call(step)
            again = load(os.path.join(frames, "made_skin_dz")) if os.path.isdir(os.path.join(frames, "made_skin_dz")) else []
            if code != 0 or len(again) != 16 or max(float(np.abs(x - y).max()) for x, y in zip(again, cells)) > 1e-3:
                problems.append(f"with its frames gone the build step did not bake the same cells again: {v['summary']}")
            save(skin(shift=0.3), os.path.join(built, "made_skin.png"))
            code, v = call(step)
            moved = load(os.path.join(frames, "made_skin_dz"))
            if code != 0 or not v.get("baked") or float(np.abs(moved[0] - cells[0]).mean()) < 0.01:
                problems.append(f"with its source texture changed the build step kept the old cells: {v['summary']}")
            if not os.path.isfile(os.path.join(look, "made_skin_dz_strip.png")):
                problems.append("no LOOK strip was written")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    if problems:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"dissolve {case}: " + "; ".join(problems), "next_action": "kit/vfx/dissolve.py"}))
        return 1
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"dissolve {case}: 16 cells from the texture whole to nothing, in pieces, the edge on the front, tiling; packed 1024 px 4x4; baked again when stale, left alone when current",
                      "next_action": "none"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
