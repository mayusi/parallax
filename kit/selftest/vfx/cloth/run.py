#!/usr/bin/env python3
"""The self-test of CLOTH, SIMULATED AND BAKED (kit/vfx/cloth.py; the VFX methods audit, stage 15).

    python kit/selftest/vfx/cloth/run.py good    three sheets baked by the real command: a banner held at its top in
                                                 a wind into +z, a flag held at its pole that loops, a sheet held at
                                                 two corners and let go flat. Each: the held points stay, no link is
                                                 longer than 1.12 times its length, no point jumps; the banner's free
                                                 edge is blown the wind's way and hangs below its top; the flag's ends
                                                 meet; the let-go sheet ends lower than it started; the same asks give
                                                 the same bake twice; and the method gate takes each bake (and refuses
                                                 a billow, a missing file, a looped layer on a bake that does not loop)
    python kit/selftest/vfx/cloth/run.py still   a sheet in no wind: the command must refuse it, saying "hangs still"
    python kit/selftest/vfx/cloth/run.py torn    a good bake whose middle frame's free half was pulled down by hand:   
                                                 the gate must refuse the layer that plays it ("the gate refuses")

Nothing here plays a bake in Roblox or in the browser player.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import cloth  # noqa: E402
import methods  # noqa: E402


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def bake(root, name, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cloth.main([name, *argv, "--out-dir", os.path.join(root, "seq"), "--look-dir", os.path.join(root, "look")])
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def frames(root, name):
    with open(os.path.join(root, "seq", f"{name}.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    n = d["cols"] + 1
    return d, [[f[k:k + 3] for k in range(0, len(f), 3)] for f in d["frames"]], n


class NoSpecs:
    def get(self, key):
        return None


def gate(root, layer):
    by = methods.load()[1]
    return methods.proved(by["cloth"], [dict({"kind": "mesh", "pivot": "origin", "shape": "seq", "life": 2}, **layer)], NoSpecs(), root, "s") is not None


def good(root):
    wrong = []
    asks = {"banner": ["--pin", "top", "--wind", "0,0,14"], "flag": ["--pin", "left", "--wind", "3,0,14", "--loop"],
            "sheet": ["--pin", "corners", "--start", "flat", "--wind", "0,0,0"]}
    for name, argv in asks.items():
        code, said = bake(root, name, *argv)
        if code != 0:
            return say("fail", f"cloth self-test: the {name} was refused: {said['summary'][:200]}", "kit/vfx/cloth.py")
        if not os.path.isfile(said["look"]):
            wrong.append(f"{name}: no picture to look at")
        if not all(c["ok"] for c in cloth.check(json.load(open(said["seq"], encoding="utf-8")))):
            wrong.append(f"{name}: its own file fails its checks")
    d, fr, n = frames(root, "banner")
    rows = d["rows"]
    free_z = [sum(p[2] for p in f[rows * n:]) / n for f in fr]
    free_y = [sum(p[1] for p in f[rows * n:]) / n for f in fr]
    if not all(z > 0.02 for z in free_z):
        wrong.append(f"the banner's free edge is not blown the wind's way (+z): least {min(free_z):.3f}")
    if not all(y < -0.3 for y in free_y):
        wrong.append(f"the banner's free edge does not hang below its top: {max(free_y):.3f}")
    if any(abs(p[1]) > 1e-6 or abs(p[2]) > 1e-6 for f in fr for p in f[:n]):
        wrong.append("the banner's held top row moved")
    d, fr, n = frames(root, "flag")
    seam = max(sum((a - b) ** 2 for a, b in zip(p, q)) ** 0.5 for p, q in zip(fr[0], fr[-1]))
    inside = max(sum((a - b) ** 2 for a, b in zip(p, q)) ** 0.5 for k in range(len(fr) - 1) for p, q in zip(fr[k], fr[k + 1]))
    if seam > 2 * inside:
        wrong.append(f"the flag's loop jumps at its seam: {seam:.3f} against {inside:.3f} inside it")
    far = [sum(f[j * n + d["cols"]][2] for j in range(d["rows"] + 1)) / (d["rows"] + 1) for f in fr]
    if not sum(far) / len(far) > 0.02:
        wrong.append(f"the flag's free end is not carried the way its wind blows (+z): {sum(far) / len(far):.3f}")
    code, said = bake(root, "fast", "--fps", "60", "--frames", "64", "--cols", "12", "--rows", "6")
    if code != 0:
        wrong.append("the banner baked at 60 frames a second was refused: " + said["summary"][:120])
    d, fr, n = frames(root, "sheet")
    mid = (d["rows"] * n) + n // 2
    if not (abs(fr[0][mid][1]) < 1e-6 and fr[-1][mid][1] < -0.2):
        wrong.append(f"the sheet let go flat did not fall: its far edge from {fr[0][mid][1]:.3f} to {fr[-1][mid][1]:.3f}")
    first = open(os.path.join(root, "seq", "banner.json"), encoding="utf-8").read()
    bake(root, "banner", *asks["banner"])
    if open(os.path.join(root, "seq", "banner.json"), encoding="utf-8").read() != first:
        wrong.append("the same asks gave another bake")
    # the method gate
    with open(os.path.join(root, "seq", "puff.json"), "w", encoding="utf-8") as fh:
        json.dump({"recipe": "billow", "args": {}, "cols": 4, "rows": 2, "frames": [[0.0] * 45, [0.1] * 45]}, fh)
    asked = [("the banner", {"params": {"seq": "banner"}}, True), ("the flag, looped", {"params": {"seq": "flag", "loop": True}}, True),
             ("the banner, looped (baked without --loop)", {"params": {"seq": "banner", "loop": True}}, False),
             ("the banner played at 2 frames a second", {"params": {"seq": "banner", "fps": 2}}, False),
             ("a billow", {"params": {"seq": "puff"}}, False), ("a name with no file", {"params": {"seq": "nothing"}}, False),
             ("a plain ring", {"shape": "ring"}, False)]
    for what, layer, want in asked:
        if gate(root, layer) != want:
            wrong.append(f"the gate {'refused' if want else 'took'} {what}")
    if wrong:
        return say("fail", "cloth self-test: " + "; ".join(wrong), "kit/vfx/cloth.py, kit/vfx/methods.py (kept_file)")
    return say("pass", "cloth self-test: a banner, a looping flag and a sheet let go - held edges stay, no link stretches, the wind pushes the sheet its way, "
               "the loop's ends meet, the same asks bake the same frames, and the gate takes the bakes and nothing else", "none")


def still(root):
    code, said = bake(root, "calm", "--wind", "0,0,0")
    return say("fail" if code != 0 and "hangs still" in said["summary"] else "pass",
               said["summary"] if code != 0 else "cloth self-test: a sheet in no wind was baked", said["next_action"] if code != 0 else "kit/vfx/cloth.py (check)")


def torn(root):
    code, said = bake(root, "banner", "--pin", "top", "--wind", "0,0,14")
    if code != 0:
        return say("pass", "cloth self-test: the good bake was refused, so nothing was torn: " + said["summary"][:160], "kit/vfx/cloth.py")
    path = os.path.join(root, "seq", "banner.json")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    took = gate(root, {"params": {"seq": "banner"}})
    k = len(d["frames"]) // 2
    n = d["cols"] + 1  # the free half of the sheet, pulled half as long again downward (the held row is left where it is)
    d["frames"][k] = [x * 1.5 if i % 3 == 1 and i // 3 >= n * (d["rows"] // 2) else x for i, x in enumerate(d["frames"][k])]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    if took and not gate(root, {"params": {"seq": "banner"}}):
        failed = [c for c in cloth.check(d) if not c["ok"]]
        return say("fail", "cloth self-test: the gate refuses the torn bake: " + "; ".join(f"{c['name']}: {c['value']}" for c in failed), failed[0]["fix"])
    return say("pass", "cloth self-test: a bake whose middle frame was pulled to twice its size still proves cloth", "kit/vfx/methods.py (kept_file)")


def main(argv):
    cases = {"good": good, "still": still, "torn": torn}
    if len(argv) != 1 or argv[0] not in cases:
        return say("fail", "cloth self-test: name the case", "good | still | torn")
    root = tempfile.mkdtemp(prefix="kit_cloth_")
    try:
        return cases[argv[0]](root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
