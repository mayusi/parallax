#!/usr/bin/env python3
"""The self-test of A POINT CLOUD (kit/vfx/points.py, a swarm layer's "cloud"; the VFX methods audit, stage 18).

    python kit/selftest/vfx/points/run.py good     the five starters and a cloud sampled from a MADE picture (a letter
                                                   A drawn here), by the real command: each passes its checks; the
                                                   picture's points all lie on the letter's strokes and reach its
                                                   three corners; a made swarm flown by the rule is on its points
                                                   within 8 / pull seconds at 30, 60 and 144 frames a second, never
                                                   passes its point, and with a pull of 0 goes nowhere; the method gate
                                                   takes a swarm that names the cloud (and refuses a missing cloud, a
                                                   pull of 0, a swarm of a third of the points)
    python kit/selftest/vfx/points/run.py clump    a cloud file whose points are all in one corner: the command must
                                                   refuse it, saying "not a clump" (exit 1)
    python kit/selftest/vfx/points/run.py parity   the new speed asked of the GAME's rule (the text of cloudPull in
                                                   src/kit/VfxStage.luau, run by lune), of the PLAYER's (player.js, run
                                                   by node) and of points.py in 2,000 cases: the same number from all
                                                   three; and the player parses as the module it is

Nothing here gathers a swarm in Roblox or in the browser player.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import methods  # noqa: E402
import points  # noqa: E402

STAGE = os.path.join(ROOT, "src", "kit", "VfxStage.luau")
PLAYER = os.path.join(ROOT, "kit", "vfx", "player", "player.js")


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def call(root, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = points.main([*argv, "--out-dir", os.path.join(root, "points"), "--look-dir", os.path.join(root, "look")])
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


class NoSpecs:
    def get(self, key):
        return None


def gate(root, layer):
    by = methods.load()[1]
    return methods.proved(by["point_cloud"], [dict({"kind": "swarm", "life": 2}, **layer)], NoSpecs(), root, "s") is not None


def letter(path):
    """a letter A, strokes 14 px wide, on nothing: returns its strokes as segments in the picture's pixels"""
    from PIL import Image, ImageDraw

    strokes = [((40, 160), (100, 30)), ((100, 30), (160, 160)), ((65, 110), (135, 110))]
    img = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    pen = ImageDraw.Draw(img)
    for a, b in strokes:
        pen.line([a, b], fill=(255, 220, 120, 255), width=14)
    img.save(path)
    return strokes


def off_stroke(p, strokes):
    best = 1e9
    for (ax, ay), (bx, by) in strokes:
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, ((p[0] - ax - t * dx) ** 2 + (p[1] - ay - t * dy) ** 2) ** 0.5)
    return best


def good(root):
    wrong = []
    for kind in points.STARTERS:
        code, said = call(root, kind, "--new", kind)
        if code != 0:
            wrong.append(f"the {kind} starter was refused: {said['summary'][:120]}")
        elif not os.path.isfile(said["look"]):
            wrong.append(f"{kind}: no picture to look at")
    pic = os.path.join(root, "letter.png")
    strokes = letter(pic)
    code, said = call(root, "letter", "--picture", pic, "--count", "70")
    if code != 0:
        return say("fail", "points self-test: the letter's cloud was refused: " + said["summary"][:200], "kit/vfx/points.py")
    with open(os.path.join(root, "points", "letter.json"), encoding="utf-8") as fh:
        pts = json.load(fh)["points"]
    # back into the picture's pixels: the cloud is the pixels about their middle, over the farthest one's distance
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    span = max(xs) - min(xs)
    k = 120 / span  # (the A is 120 px wide at its feet, to the strokes' middles; the half width of a stroke is the slack)
    back = [((p[0] - min(xs)) * k + 40, 160 - (p[1] - min(ys)) * k) for p in pts]
    far = max(off_stroke(b, strokes) for b in back)
    if far > 16:
        wrong.append(f"a point of the letter's cloud lies {far:.0f} px off its strokes")
    for name, corner in (("its top", (100, 30)), ("its left foot", (40, 160)), ("its right foot", (160, 160))):
        if min(((b[0] - corner[0]) ** 2 + (b[1] - corner[1]) ** 2) ** 0.5 for b in back) > 24:
            wrong.append(f"no point of the cloud is near {name}")
    if len(pts) != 70 or any(abs(p[2]) > 1e-9 for p in pts):
        wrong.append("the letter's cloud is not 70 points standing upright")
    # THE RULE
    for rate in (30, 60, 144):
        for w in (4.0, 8.0, 20.0):
            t = points.gather(pts, w, size=6.0, dt=1 / rate)
            if t is None or t > 8 / w + 0.2:
                wrong.append(f"at {rate} frames a second and a pull of {w:g} the swarm is whole after {t} s (8 / pull = {8 / w:.2f})")
    d, v = 5.0, 0.0
    for _ in range(600):
        v = points.pull(d, v, 8.0, 1 / 60)
        d += v / 60
        if d < -1e-9:
            wrong.append("a particle passed its point (the spring overshoots)")
            break
    if abs(d) > 1e-3:
        wrong.append(f"a particle 5 studs from its point is still {d:.4f} away after ten seconds")
    if points.pull(5.0, 2.0, 0.0, 1 / 60) != 2.0:
        wrong.append("a pull of 0 changes a particle's speed")
    for huge in (1.0, 5.0):  # a frame a second long, a stall: nothing flies off
        if abs(points.pull(5.0, 0.0, 30.0, huge) * huge) > 5.0:
            wrong.append(f"a step of {huge:g} s throws a particle past its point")
    asked = [("a swarm of 70 that names the letter", {"count": 70, "cloud": {"name": "letter", "size": 6, "pull": [[0, 0], [0.4, 10], [1, 10]]}}, True),
             ("a swarm with no pull said (8 unless said)", {"count": 70, "cloud": {"name": "letter"}}, True),
             ("a pull that is 0 all its life, said with envelopes", {"count": 70, "cloud": {"name": "letter", "pull": [[0, 0, 0.3], [1, 0, 0.3]]}}, False),
             ("a pull too weak for a particle's life", {"count": 70, "cloud": {"name": "letter", "pull": 0.5}}, False),
             ("a pull that is there for an instant", {"count": 70, "cloud": {"name": "letter", "pull": [[0, 0], [0.5, 0], [0.505, 20], [0.51, 0], [1, 0]]}}, False),
             ("a cloud a tenth of a stud across", {"count": 70, "cloud": {"name": "letter", "size": 0.1}}, False),
             ("a swarm of Rock said to be 150 (40 are played)", {"count": 150, "shape": "Rock", "cloud": {"name": "letter"}}, False),
             ("a pull of 0 all its life", {"count": 70, "cloud": {"name": "letter", "pull": 0}}, False),
             ("a swarm of 40 on 70 points", {"count": 40, "cloud": {"name": "letter"}}, False),
             ("a cloud that is not there", {"count": 70, "cloud": {"name": "nothing"}}, False),
             ("a swarm with no cloud", {"count": 70, "curl": {"strength": 10}}, False)]
    for what, layer, want in asked:
        if gate(root, layer) != want:
            wrong.append(f"the gate {'refused' if want else 'took'} {what}")
    if wrong:
        return say("fail", "points self-test: " + "; ".join(wrong), "kit/vfx/points.py, kit/vfx/methods.py (kept_file)")
    return say("pass", "points self-test: five starters and a letter's cloud - the letter's points lie on its strokes and reach its corners, a swarm is whole "
               "within 8 / pull seconds at three frame rates and never passes its points, and the gate takes a swarm that gathers and nothing else", "none")


def clump(root):
    os.makedirs(os.path.join(root, "points"), exist_ok=True)
    with open(os.path.join(root, "points", "knot.json"), "w", encoding="utf-8") as fh:
        json.dump({"points": [[0.9 + 0.004 * i, 0.3 + 0.003 * (i % 5), 0.0] for i in range(30)]}, fh)
    code, said = call(root, "knot")
    return say("fail" if code != 0 and "not a clump" in said["summary"] else "pass",
               said["summary"] if code != 0 else "points self-test: thirty points in one corner were taken as a cloud", said["next_action"] if code != 0 else "kit/vfx/points.py (check)")


def cut(path, first, end):
    text = open(path, encoding="utf-8").read()
    a, b = text.find(first), text.find(end)
    if a < 0 or b < a:
        raise ValueError(f"{os.path.relpath(path, ROOT)} has no cloudPull between its two marks")
    return text[a:text.rfind("\n", a, b)]


LUAU_HEAD = 'local fs = require("@lune/fs")\nlocal serde = require("@lune/serde")\nlocal process = require("@lune/process")\n'
LUAU_TAIL = """
local out = {}
for i, c in serde.decode("json", fs.readFile(process.args[1])) do
	out[i] = cloudPull(c[1], c[2], c[3], c[4])
end
print(serde.encode("json", out))
"""
JS_TAIL = """
const cases = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(cases.map(c => cloudPull(c[0], c[1], c[2], c[3]))));
"""


def parity(root):
    asked = [[d, v, w, dt] for d in (-40.0, -3.3, -0.01, 0.0, 0.2, 5.0, 77.7, 400.0, 1e-6, -1e4) for v in (-90.0, -1.5, 0.0, 0.3, 12.0, 250.0, 1e3, -1e-3)
             for w in (0.0, 0.5, 4.0, 8.0, 60.0) for dt in (0.0, 1 / 144, 1 / 60, 1 / 30, 1 / 15)]
    os.makedirs(root, exist_ok=True)
    data = os.path.join(root, "cases.json")
    with open(data, "w", encoding="utf-8") as fh:
        json.dump(asked, fh)
    luau, js = os.path.join(root, "game.luau"), os.path.join(root, "player.cjs")
    with open(luau, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(LUAU_HEAD + cut(STAGE, "local function cloudPull(", "-- (end of cloudPull)") + "\n" + LUAU_TAIL)
    with open(js, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(cut(PLAYER, "function cloudPull(", "// (end of cloudPull)") + "\n" + JS_TAIL)
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
    want = [points.pull(*c) for c in asked]
    for who, answers in got.items():
        off = [n for n, (a, b) in enumerate(zip(want, answers)) if not isinstance(b, (int, float)) or abs(a - b) > 1e-9 * max(1, abs(a))]
        if len(answers) != len(want) or off:
            problems.append(f"{who} gives another speed in {len(off)} of {len(want)} cases (first: {asked[off[0]] if off else None})")
    if len(set(round(x, 6) for x in want)) < 500:
        problems.append("the cases ask for too few different speeds to tell the three apart")
    return problems, len(asked)


def main(argv):
    case = argv[0] if argv else "good"
    if case == "parity":
        root = os.path.join("build", "selftest", f"vfx_points_parity_{os.getpid()}")
        try:
            problems, n = parity(root)
        except ValueError as e:
            problems, n = [str(e)], 0
        finally:
            shutil.rmtree(root, ignore_errors=True)
        if problems:
            return say("fail", "points parity: " + "; ".join(problems), "src/kit/VfxStage.luau cloudPull, kit/vfx/player/player.js cloudPull and kit/vfx/points.py pull are ONE rule")
        return say("pass", f"points parity: the game's cloudPull, the player's and the rule give the same speed in {n} cases", "none")
    cases = {"good": good, "clump": clump}
    if case not in cases:
        return say("fail", "points self-test: name the case", "good | clump | parity")
    root = tempfile.mkdtemp(prefix="kit_points_")
    try:
        return cases[case](root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
