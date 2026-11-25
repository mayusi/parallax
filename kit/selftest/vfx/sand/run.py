#!/usr/bin/env python3
"""The self-test of SAND, SIMULATED AND BAKED (kit/vfx/sand.py; the VFX methods audit, stage 17).

    python kit/selftest/vfx/sand/run.py good    a pillar let go and a pour, baked by the real command. The pillar:
                                                every frame holds the pillar's own sand (to a hundredth), it ends
                                                lower and wider than it started, no steeper than its angle of repose
                                                (34 degrees, +4 for the grid) and not flatter than 24, as wide along x
                                                as along z; a pillar of sand that holds 45 degrees ends higher than one
                                                that holds 20. The pour: every frame holds what was poured by then, the
                                                heap's top rises and is under the spout. The same asks give the same
                                                bake twice; the method gate takes each bake (and refuses a soft bake, a
                                                missing file, a layer that loops it)
    python kit/selftest/vfx/sand/run.py flat    a pillar lower than its sand's slope (it does not slide): the command
                                                must refuse it, saying "the sand moves" (exit 1)
    python kit/selftest/vfx/sand/run.py made    a good bake whose last frame was raised by a twentieth by hand (sand from
                                                nowhere): the gate must refuse the layer that plays it

Nothing here plays a bake in Roblox or in the browser player.
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
import methods  # noqa: E402
import sand  # noqa: E402

import numpy as np  # noqa: E402


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def bake(root, name, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = sand.main([name, *argv, "--out-dir", os.path.join(root, "seq"), "--look-dir", os.path.join(root, "look")])
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def heights(root, name):
    with open(os.path.join(root, "seq", f"{name}.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    return d, np.array(d["frames"]).reshape(len(d["frames"]), d["rows"] + 1, d["cols"] + 1, 3)[..., 1]


class NoSpecs:
    def get(self, key):
        return None


def gate(root, layer):
    by = methods.load()[1]
    return methods.proved(by["granular"], [dict({"kind": "mesh", "pivot": "origin", "shape": "seq", "life": 2}, **layer)], NoSpecs(), root, "s") is not None


def good(root):
    wrong = []
    for name, argv in (("pillar", []), ("fine", ["--repose", "20"]), ("coarse", ["--repose", "45"]), ("poured", ["--mode", "pour"])):
        code, said = bake(root, name, *argv)
        if code != 0:
            return say("fail", f"sand self-test: {name} was refused: {said['summary'][:200]}", "kit/vfx/sand.py")
        if not os.path.isfile(said["look"]):
            wrong.append(f"{name}: no picture to look at")
    d, h = heights(root, "pillar")
    n = d["cols"]
    vol = h.sum((1, 2))
    if float(np.abs(vol - vol[0]).max()) > 0.01 * vol[0]:
        wrong.append(f"the pillar's sand goes from {vol.min() / vol[0]:.3f} to {vol.max() / vol[0]:.3f} of what it was")
    wide = lambda g: float((g > 0.01).mean())  # noqa: E731
    if not (h[-1].max() < 0.7 * h[0].max() and wide(h[-1]) > 1.5 * wide(h[0])):
        wrong.append(f"the pillar did not end lower and wider: {h[0].max():.3f} -> {h[-1].max():.3f} high, {wide(h[0]):.2f} -> {wide(h[-1]):.2f} of its ground")
    steep = math.degrees(math.atan(max(np.abs(np.diff(h[-1], axis=0)).max(), np.abs(np.diff(h[-1], axis=1)).max()) * n))
    if not 28 <= steep <= 35.5:
        wrong.append(f"the heap's steepest slope ends at {steep:.0f} degrees (its sand holds 34)")
    if float(np.abs(h[-1] - h[-1].T).max()) > 1e-3:
        wrong.append("the heap is wider one way than the other")
    moved = np.abs(h[1:] - h[:-1]).max((1, 2))
    slide = int(round(d["args"]["settle"] * d["args"]["fps"]))
    if not (moved[: slide - 1] > 1e-4).all():
        wrong.append(f"the slide stands still in {int((moved[: slide - 1] <= 1e-4).sum())} of its {slide - 1} frames (it stutters)")
    code, said = bake(root, "long", "--settle", "2.0")
    if code == 0 or "longer than the sequence" not in said["summary"]:
        wrong.append("a --settle longer than the sequence was not refused")
    tops = [float(heights(root, k)[1][-1].max()) for k in ("fine", "pillar", "coarse")]
    if not tops[0] < tops[1] < tops[2]:
        wrong.append(f"sand that holds a steeper slope does not stand higher: {tops}")
    d, h = heights(root, "poured")
    a = d["args"]
    cell = 1.0 / (d["cols"] * d["rows"])
    for f in range(1, len(h)):
        want = a["rate"] * f / a["fps"] / a["size"] ** 3
        if abs(float(h[f].sum()) * cell - want) > 0.02 * want + 1e-6:
            wrong.append(f"the pour holds {h[f].sum() * cell:.5f} at frame {f + 1}, {want:.5f} was poured")
            break
    if not (h[-1].max() > h[len(h) // 2].max() > h[2].max() and np.unravel_index(int(h[-1].argmax()), h[-1].shape) == (d["rows"] // 2, d["cols"] // 2)):
        wrong.append("the poured heap's top does not rise under the spout")
    first = open(os.path.join(root, "seq", "pillar.json"), encoding="utf-8").read()
    bake(root, "pillar")
    if open(os.path.join(root, "seq", "pillar.json"), encoding="utf-8").read() != first:
        wrong.append("the same asks gave another bake")
    with open(os.path.join(root, "seq", "blob.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(json.loads(first), recipe="soft"), fh)
    for what, layer, want in (("the pillar", {"params": {"seq": "pillar"}}, True), ("the pour", {"params": {"seq": "poured"}}, True),
                              ("the pillar, looped", {"params": {"seq": "pillar", "loop": True}}, False), ("a soft bake", {"params": {"seq": "blob"}}, False),
                              ("a name with no file", {"params": {"seq": "nothing"}}, False), ("a plain disc", {"shape": "disc"}, False)):
        if gate(root, layer) != want:
            wrong.append(f"the gate {'refused' if want else 'took'} {what}")
    if wrong:
        return say("fail", "sand self-test: " + "; ".join(wrong), "kit/vfx/sand.py, kit/vfx/methods.py (kept_file)")
    return say("pass", "sand self-test: a pillar slumps to a round heap at its angle of repose with all its sand, steeper sand stands higher, a pour holds "
               "what was poured and rises under its spout; the gate takes the bakes and nothing else", "none")


def flat(root):
    code, said = bake(root, "low", "--height", "0.3", "--width", "6")
    return say("fail" if code != 0 and "the sand moves" in said["summary"] else "pass",
               said["summary"] if code != 0 else "sand self-test: a pillar too low to slide was baked", said["next_action"] if code != 0 else "kit/vfx/sand.py (check)")


def made(root):
    code, said = bake(root, "dune")
    if code != 0:
        return say("pass", "sand self-test: the good bake was refused, so nothing was changed: " + said["summary"][:160], "kit/vfx/sand.py")
    path = os.path.join(root, "seq", "dune.json")
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    took = gate(root, {"params": {"seq": "dune"}})
    d["frames"][-1] = [x * 1.05 if k % 3 == 1 else x for k, x in enumerate(d["frames"][-1])]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    if took and not gate(root, {"params": {"seq": "dune"}}):
        failed = [c for c in sand.check(d) if not c["ok"]]
        if "no sand is made or lost" not in [c["name"] for c in failed]:
            return say("pass", "sand self-test: sand from nowhere was refused, but not for being made: " + ", ".join(c["name"] for c in failed), "kit/vfx/sand.py (check)")
        return say("fail", "sand self-test: the gate refuses the bake with sand from nowhere: " + "; ".join(f"{c['name']}: {c['value']}" for c in failed), failed[0]["fix"])
    return say("pass", "sand self-test: a bake whose last frame was raised by a fifth still proves sand", "kit/vfx/methods.py (kept_file)")


def main(argv):
    cases = {"good": good, "flat": flat, "made": made}
    if len(argv) != 1 or argv[0] not in cases:
        return say("fail", "sand self-test: name the case", "good | flat | made")
    root = tempfile.mkdtemp(prefix="kit_sand_")
    try:
        return cases[argv[0]](root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
