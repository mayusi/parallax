#!/usr/bin/env python3
"""The self-test of A SOFT BODY, SIMULATED AND BAKED (kit/vfx/soft.py; the VFX methods audit, stage 16).

    python kit/selftest/vfx/soft/run.py good    two balls baked by the real command: one dropped straight, one thrown
                                                sideways. Each: it falls as a thing falls until it lands (its underside
                                                within a quarter stud of gravity's own drop), never goes under the
                                                floor, is flatter and WIDER in its flattest frame than when it started,
                                                keeps its volume to a tenth, its skin stays closed; the dropped one
                                                does not roll, the thrown one ends further along its throw; the same
                                                asks give the same bake twice; and the method gate takes each bake (and
                                                refuses a cloth bake, a missing file, a layer that loops it)
    python kit/selftest/vfx/soft/run.py rigid   a ball that never reaches the floor in its frames (it keeps its shape):
                                                the command must refuse it, saying "a rigid ball" (exit 1)
    python kit/selftest/vfx/soft/run.py open    a good bake whose seam was pulled open by hand in one frame: the gate
                                                must refuse the layer that plays it ("the gate refuses")

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
import methods  # noqa: E402
import soft  # noqa: E402

import numpy as np  # noqa: E402


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def bake(root, name, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = soft.main([name, *argv, "--out-dir", os.path.join(root, "seq"), "--look-dir", os.path.join(root, "look")])
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def read(root, name):
    with open(os.path.join(root, "seq", f"{name}.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    return d, np.array(d["frames"]).reshape(len(d["frames"]), d["rows"] + 1, d["cols"] + 1, 3)


class NoSpecs:
    def get(self, key):
        return None


def gate(root, layer):
    by = methods.load()[1]
    return methods.proved(by["soft_body"], [dict({"kind": "mesh", "pivot": "origin", "shape": "seq", "life": 2}, **layer)], NoSpecs(), root, "s") is not None


def good(root):
    wrong = []
    asks = {"dropped": [], "thrown": ["--throw", "14,0,0"]}
    for name, argv in asks.items():
        code, said = bake(root, name, *argv)
        if code != 0:
            return say("fail", f"soft self-test: the {name} ball was refused: {said['summary'][:200]}", "kit/vfx/soft.py")
        d, g = read(root, name)
        size, pts = d["args"]["size"], g.reshape(len(g), -1, 3)
        for f in (4, 8):  # (default: dropped 6 studs at gravity 60 - it lands after frame 10)
            t = f / d["args"]["fps"]
            want = (d["args"]["drop"] - 0.5 * d["args"]["gravity"] * t * t) / size
            if abs(float(pts[f, :, 1].min()) - want) > 0.25 / size:
                wrong.append(f"{name}: at frame {f + 1} its underside is at {pts[f, :, 1].min():.3f}, gravity alone puts it at {want:.3f}")
        if float(pts[..., 1].min()) < -1e-6:
            wrong.append(f"{name}: a point under the floor ({pts[..., 1].min():.4f})")
        tall = np.ptp(pts[..., 1], axis=1)
        k = int(np.argmin(tall))
        if not (tall[k] < 0.85 and float(np.ptp(pts[k, :, 0])) > 1.05):
            wrong.append(f"{name}: in its flattest frame it is {tall[k]:.2f} tall and {np.ptp(pts[k, :, 0]):.2f} wide (a ball that gives is flatter AND wider)")
        vols = [soft.volume(f) for f in g]
        if not 0.9 <= min(vols) / vols[0] <= max(vols) / vols[0] <= 1.1:
            wrong.append(f"{name}: its volume goes from {min(vols) / vols[0]:.2f} to {max(vols) / vols[0]:.2f} of the first frame's")
        if float(np.abs(g[:, :, 0] - g[:, :, -1]).max()) > 1e-6:
            wrong.append(f"{name}: its seam is open")
        if not os.path.isfile(said["look"]):
            wrong.append(f"{name}: no picture to look at")
    d, g = read(root, "dropped")
    last = g[-1].reshape(-1, 3)
    if abs(float(g[-1, -1, 0, 2] - last[:, 2].mean())) > 1e-4 or abs(float(last[:, 2].mean())) > 1e-4:
        wrong.append("the ball dropped straight rolled over or wandered")
    d, g = read(root, "thrown")
    if not float(g[-1].reshape(-1, 3)[:, 0].mean()) > 1.0:
        wrong.append("the thrown ball did not go the way it was thrown (+x)")
    first = open(os.path.join(root, "seq", "dropped.json"), encoding="utf-8").read()
    bake(root, "dropped")
    if open(os.path.join(root, "seq", "dropped.json"), encoding="utf-8").read() != first:
        wrong.append("the same asks gave another bake")
    with open(os.path.join(root, "seq", "sail.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(json.loads(first), recipe="cloth"), fh)
    asked = [("the dropped ball", {"params": {"seq": "dropped"}}, True), ("the thrown ball", {"params": {"seq": "thrown"}}, True),
             ("the dropped ball, looped", {"params": {"seq": "dropped", "loop": True}}, False), ("a cloth bake", {"params": {"seq": "sail"}}, False),
             ("a name with no file", {"params": {"seq": "nothing"}}, False), ("a plain orb", {"shape": "orb"}, False)]
    for what, layer, want in asked:
        if gate(root, layer) != want:
            wrong.append(f"the gate {'refused' if want else 'took'} {what}")
    if wrong:
        return say("fail", "soft self-test: " + "; ".join(wrong), "kit/vfx/soft.py, kit/vfx/methods.py (kept_file)")
    return say("pass", "soft self-test: a dropped ball and a thrown one - each falls as a thing falls, lands flatter and wider, keeps its volume, stays "
               "on the floor and closed; the dropped one does not roll, the thrown one goes its way; the gate takes the bakes and nothing else", "none")


def rigid(root):
    code, said = bake(root, "high", "--drop", "300", "--frames", "12")
    return say("fail" if code != 0 and "a rigid ball" in said["summary"] else "pass",
               said["summary"] if code != 0 else "soft self-test: a ball that never lands was baked as a soft body", said["next_action"] if code != 0 else "kit/vfx/soft.py (check)")


def opened(root):
    code, said = bake(root, "blob")
    if code != 0:
        return say("pass", "soft self-test: the good bake was refused, so nothing was opened: " + said["summary"][:160], "kit/vfx/soft.py")
    path = os.path.join(root, "seq", "blob.json")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    took = gate(root, {"params": {"seq": "blob"}})
    k = len(d["frames"]) // 2
    w = d["cols"] + 1
    for j in range(2, d["rows"] - 1):
        d["frames"][k][(j * w + d["cols"]) * 3] += 0.08  # the seam's second column, pulled away from its twin
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    if took and not gate(root, {"params": {"seq": "blob"}}):
        failed = [c for c in soft.check(d) if not c["ok"]]
        return say("fail", "soft self-test: the gate refuses the opened bake: " + "; ".join(f"{c['name']}: {c['value']}" for c in failed), failed[0]["fix"])
    return say("pass", "soft self-test: a bake whose seam was pulled open still proves a soft body", "kit/vfx/methods.py (kept_file)")


def main(argv):
    cases = {"good": good, "rigid": rigid, "open": opened}
    if len(argv) != 1 or argv[0] not in cases:
        return say("fail", "soft self-test: name the case", "good | rigid | open")
    root = tempfile.mkdtemp(prefix="kit_soft_")
    try:
        return cases[argv[0]](root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
