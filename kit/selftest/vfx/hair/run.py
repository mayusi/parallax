#!/usr/bin/env python3
"""The self-test of HAIR AND FUR, SIMULATED AND BAKED (kit/vfx/hair.py; the VFX methods audit, stage 19).

    python kit/selftest/vfx/hair/run.py good    three bakes by the real command: a head of hair tossed, a fringe that
                                                sways and loops, a fringe in a wind. Each: every strand is 0.9 to 1.1
                                                of its length in every frame, the roots keep their places on one body,
                                                each strip is a ribbon that narrows to its tip. The tossed hair lies
                                                outside its head, its roots turn as far as the toss, and its tips lag
                                                the turn (they swing against their roots). The swaying fringe hangs
                                                below its row, its tips travel further side to side than its roots,
                                                and its loop's ends meet. The wind carries the fringe its way. The
                                                same asks bake the same frames; the gate takes each bake (and refuses a
                                                cloth bake, a looped layer on a bake without --loop, a missing file)
    python kit/selftest/vfx/hair/run.py still   hair with no move and no wind: the command must refuse it, saying
                                                "the hair moves" (exit 1)
    python kit/selftest/vfx/hair/run.py stiff   a good bake rewritten by hand so that every frame is the first frame
                                                turned with its roots (hair as one stiff piece): the gate must refuse
                                                the layer that plays it, saying "one stiff piece"

Nothing here plays a bake in Roblox or in the browser player; the strips of the seq shape are not built here.
"""
import contextlib
import io
import json
import math
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import hair  # noqa: E402
import methods  # noqa: E402

import numpy as np  # noqa: E402


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def bake(root, name, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = hair.main([name, *argv, "--out-dir", os.path.join(root, "seq"), "--look-dir", os.path.join(root, "look")])
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def read(root, name):
    with open(os.path.join(root, "seq", f"{name}.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    g = np.array(d["frames"]).reshape(len(d["frames"]), d["strips"], d["rows"] + 1, 2, 3)
    return d, g, g.mean(3)


class NoSpecs:
    def get(self, key):
        return None


def gate(root, layer):
    by = methods.load()[1]
    return methods.proved(by["hair"], [dict({"kind": "mesh", "pivot": "origin", "shape": "seq", "life": 2}, **layer)], NoSpecs(), root, "s") is not None


ASKS = {"tossed": ["--root", "cap", "--move", "toss"], "fringe": ["--root", "line", "--move", "sway", "--amount", "1.5", "--loop"],
        "blown": ["--root", "line", "--move", "none", "--wind", "0,0,10", "--gust", "1"]}


def good(root):
    wrong = []
    for name, argv in ASKS.items():
        code, said = bake(root, name, *argv)
        if code != 0:
            return say("fail", f"hair self-test: {name} was refused: {said['summary'][:200]}", "kit/vfx/hair.py")
        d, g, mid = read(root, name)
        length = np.linalg.norm(mid[:, :, 1:] - mid[:, :, :-1], axis=-1).sum(-1)
        if not (0.9 <= length.min() and length.max() <= 1.1):
            wrong.append(f"{name}: a strand is {length.min():.2f} to {length.max():.2f} of its length")
        apart = np.linalg.norm(mid[:, :, None, 0] - mid[:, None, :, 0], axis=-1)
        if float(np.abs(apart - apart[0:1]).max()) > 0.01:
            wrong.append(f"{name}: its roots do not keep their places on one body")
        width = np.linalg.norm(g[:, :, :, 1] - g[:, :, :, 0], axis=-1)
        if not (width[:, :, 0] > 2 * width[:, :, -1]).all():
            wrong.append(f"{name}: a ribbon does not narrow to its tip")
        if d["cols"] != 1 or d["strips"] != d["args"]["strands"] or len(d["frames"][0]) != d["strips"] * (d["rows"] + 1) * 6:
            wrong.append(f"{name}: the file is not one strip a strand, 2 points wide")
        if not os.path.isfile(said["look"]):
            wrong.append(f"{name}: no picture to look at")
    d, g, mid = read(root, "tossed")
    a = d["args"]
    inside = float(np.linalg.norm(mid, axis=-1).min()) * a["length"]
    if inside < a["head"] / 2 * 0.97:
        wrong.append(f"the tossed hair goes into its head: a point {inside:.2f} studs from its middle (the head is {a['head'] / 2:.2f})")
    span = mid[:, :, 0] - mid[:, :, 0].mean(1, keepdims=True)
    far = int(np.argmax(np.linalg.norm(span[0][:, [0, 2]], axis=-1)))
    turn = np.unwrap(np.arctan2(span[:, far, 2], span[:, far, 0]))
    across = g[:, :, :, 1] - g[:, :, :, 0]
    across = across / np.linalg.norm(across, axis=-1, keepdims=True)
    if float((across[:, :, 1:] * across[:, :, :-1]).sum(-1).min()) <= 0 or float((across[1:] * across[:-1]).sum(-1).min()) <= 0:
        wrong.append("a ribbon of the tossed hair turns over from one row or frame to the next")
    if not 1.2 <= float(turn.max() - turn.min()) <= 1.7:  # (0.8 radians each way)
        wrong.append(f"the tossed head's roots turn {turn.max() - turn.min():.2f} radians in all (the toss is 1.6)")
    swing = next(c for c in hair.check(d) if c["name"] == "the hair moves on its body")
    if not swing["ok"]:
        wrong.append("the tossed hair does not lag its head: " + swing["value"])
    d, g, mid = read(root, "fringe")
    if not (mid[:, :, -1, 1] < mid[:, :, 0, 1] - 0.5).all():
        wrong.append("the fringe does not hang below its row")
    roots_x, tips_x = float(np.ptp(mid[:, :, 0, 0].mean(1))), float(np.ptp(mid[:, :, -1, 0].mean(1)))
    if not tips_x > 1.05 * roots_x:
        wrong.append(f"the fringe's tips travel {tips_x:.2f} side to side, its roots {roots_x:.2f} (hair overshoots what swings it)")
    steps = np.linalg.norm(mid[1:, :, -1] - mid[:-1, :, -1], axis=-1).max(1)
    seam = float(np.linalg.norm(mid[0, :, -1] - mid[-1, :, -1], axis=-1).max())
    if seam > 2.5 * float(np.percentile(steps, 75)):
        wrong.append(f"the fringe's loop jumps at its seam: {seam:.3f} against a usual {np.percentile(steps, 75):.3f}")
    d, g, mid = read(root, "blown")
    if not float(mid[:, :, -1, 2].mean()) > 0.1:
        wrong.append(f"the wind (+z) does not carry the fringe its way: its tips at z = {mid[:, :, -1, 2].mean():.3f}")
    first = open(os.path.join(root, "seq", "tossed.json"), encoding="utf-8").read()
    bake(root, "tossed", *ASKS["tossed"])
    if open(os.path.join(root, "seq", "tossed.json"), encoding="utf-8").read() != first:
        wrong.append("the same asks gave another bake")
    with open(os.path.join(root, "seq", "sail.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(json.loads(first), recipe="cloth"), fh)
    for what, layer, want in (("the tossed hair", {"params": {"seq": "tossed"}}, True), ("the fringe, looped", {"params": {"seq": "fringe", "loop": True}}, True),
                              ("the tossed hair, looped (baked without --loop)", {"params": {"seq": "tossed", "loop": True}}, False),
                              ("a cloth bake", {"params": {"seq": "sail"}}, False), ("a name with no file", {"params": {"seq": "nothing"}}, False),
                              ("the tossed hair shown for a fifth of a second", {"life": 0.2, "params": {"seq": "tossed"}}, False)):
        if gate(root, layer) != want:
            wrong.append(f"the gate {'refused' if want else 'took'} {what}")
    if wrong:
        return say("fail", "hair self-test: " + "; ".join(wrong), "kit/vfx/hair.py, kit/vfx/methods.py (kept_file)")
    return say("pass", "hair self-test: a tossed head of hair, a looping fringe and a fringe in the wind - strands keep their length, roots ride their body, "
               "tips lag and overshoot, the hair stays out of its head, ribbons narrow to their tips; the gate takes the bakes and nothing else", "none")


def still(root):
    code, said = bake(root, "calm", "--move", "none", "--root", "line")
    return say("fail" if code != 0 and "the hair moves" in said["summary"] else "pass",
               said["summary"] if code != 0 else "hair self-test: hair that nothing moves was baked", said["next_action"] if code != 0 else "kit/vfx/hair.py (check)")


def stiff(root):
    code, said = bake(root, "tossed", *ASKS["tossed"])
    if code != 0:
        return say("pass", "hair self-test: the good bake was refused, so nothing was rewritten: " + said["summary"][:160], "kit/vfx/hair.py")
    d, g, mid = read(root, "tossed")
    took = gate(root, {"params": {"seq": "tossed"}})
    span = mid[:, :, 0] - mid[:, :, 0].mean(1, keepdims=True)
    far = int(np.argmax(np.linalg.norm(span[0][:, [0, 2]], axis=-1)))
    turn = np.arctan2(span[:, far, 2], span[:, far, 0])
    turn = turn - turn[0]
    flat = g[0].reshape(-1, 3)
    frames = []
    for t in turn:  # the first frame, turned about y as far as its roots are in each frame
        c, s = math.cos(t), math.sin(t)
        frames.append(np.stack([flat[:, 0] * c - flat[:, 2] * s, flat[:, 1], flat[:, 0] * s + flat[:, 2] * c], -1).round(4).reshape(-1).tolist())
    d["frames"] = frames
    with open(os.path.join(root, "seq", "tossed.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    failed = [c for c in hair.check(d) if not c["ok"]]
    if took and not gate(root, {"params": {"seq": "tossed"}}) and [c["name"] for c in failed] == ["the hair moves on its body"]:
        return say("fail", "hair self-test: the gate refuses hair that rides its head as one stiff piece: " + failed[0]["value"], failed[0]["fix"])
    return say("pass", "hair self-test: hair rewritten as one stiff piece was not refused for that: " + ", ".join(c["name"] for c in failed), "kit/vfx/hair.py (check)")


def main(argv):
    cases = {"good": good, "still": still, "stiff": stiff}
    if len(argv) != 1 or argv[0] not in cases:
        return say("fail", "hair self-test: name the case", "good | still | stiff")
    root = tempfile.mkdtemp(prefix="kit_hair_")
    try:
        return cases[argv[0]](root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
