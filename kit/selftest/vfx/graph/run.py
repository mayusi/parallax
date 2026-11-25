#!/usr/bin/env python3
"""The self-test of NODE-BASED COMPOSITING (kit/vfx/comp.py "graph"; the VFX methods audit, stage 21).

    python kit/selftest/vfx/graph/run.py good   the starter graph written and baked by the real command (a steady core
                                                and a halo torn by a panning noise and bent by another, joined): every
                                                check of the sheet passes; the CORE is the same in every frame while
                                                the HALO changes from frame to frame (what one stack cannot do: its
                                                noise and warp act on the whole look); the sheet is not the picture of
                                                any one of its nodes; the kit's packer packs the frames; the same spec
                                                bakes the same frames twice
    python kit/selftest/vfx/graph/run.py idle   the same graph with a node multiplied by nothing wired in: the command
                                                must refuse it, saying which node "do nothing" (exit 1), and write no
                                                frames
    python kit/selftest/vfx/graph/run.py ring   the same graph with two nodes reading each other: the command must
                                                refuse it, saying it "goes round in a ring"

Everything is written to a folder of this run's own, removed at the end. Nothing here shows a sheet in Roblox or in
the browser player.
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import comp  # noqa: E402
import fxfinish  # noqa: E402


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def call(root, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = comp.main([*argv, "--specs-dir", os.path.join(root, "specs"), "--frames-dir", os.path.join(root, "frames"),
                          "--look-dir", os.path.join(root, "look"), "--textures-dir", os.path.join(root, "built")])
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def frames(root, key):
    d = os.path.join(root, "frames", key)
    return [np.load(os.path.join(d, f)).astype(np.float64) for f in sorted(os.listdir(d)) if f.endswith(".npy")] if os.path.isdir(d) else []


def edit(root, key, fn):
    path = os.path.join(root, "specs", f"{key}.json")
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    fn(spec["comp"]["graph"])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh)


def refused(root, key, fn, needle, what):
    code, said = call(root, key, "--new", "graph")
    if code != 0:
        return say("pass", f"graph self-test: the starter was refused, so nothing was spoilt: {said['summary'][:160]}", "kit/vfx/comp.py")
    shutil.rmtree(os.path.join(root, "frames", key), ignore_errors=True)
    edit(root, key, fn)
    code, said = call(root, key)
    if code != 0 and needle in said["summary"] and not frames(root, key):
        return say("fail", "graph self-test: " + said["summary"][:300], said["next_action"][:200])
    return say("pass", f"graph self-test: {what} was baked, or refused for another reason: {said['summary'][:200]}", "kit/vfx/comp.py graph_checked / graph_idle")


def good(root):
    wrong = []
    code, said = call(root, "made_graph", "--new", "graph")
    if code != 0:
        return say("fail", "graph self-test: the starter graph was refused: " + said["summary"][:240], "kit/vfx/comp.py")
    fr = frames(root, "made_graph")
    if len(fr) != 16:
        return say("fail", f"graph self-test: {len(fr)} frames written, not 16", "kit/vfx/comp.py")
    n = fr[0].shape[0]
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(xx - n / 2 + 0.5, yy - n / 2 + 0.5) / n
    core, halo = r < 0.12, (r > 0.26) & (r < 0.40)
    alpha = np.array([f[..., 3] for f in fr])
    core_change, halo_change = float(alpha[:, core].std(0).max()), float(alpha[:, halo].std(0).mean())
    if core_change > 0.004:
        wrong.append(f"the core changes from frame to frame ({core_change:.4f}): the noise and the bend were to touch the halo only")
    if halo_change < 0.02:
        wrong.append(f"the halo does not change from frame to frame ({halo_change:.4f})")
    if float(alpha[:, core].mean()) < 0.3 or float(alpha[:, halo].mean()) < 0.03:
        wrong.append("the core or the halo is missing from the sheet")
    with open(os.path.join(root, "specs", "made_graph.json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    o = comp.checked(spec)
    base = comp.graph_fields(o)
    for name in o["graph"]["order"]:
        if name != o["graph"]["value"] and float(np.abs(comp._node_alone(o, base, 0.0, name) - alpha[0]).mean()) < 0.01:
            wrong.append(f'the sheet is the picture of its node "{name}" alone')
    if not os.path.isfile(str(said.get("look"))):
        wrong.append("no strip to look at")
    first = [f.copy() for f in fr]
    call(root, "made_graph")
    if not all(np.array_equal(a, b) for a, b in zip(first, frames(root, "made_graph"))):
        wrong.append("the same spec baked other frames")
    argv, buf = sys.argv, io.StringIO()
    out = os.path.join(root, "out")
    os.makedirs(out, exist_ok=True)
    sys.argv = ["fxfinish.py", "--specs", os.path.join(root, "specs"), "--frames", os.path.join(root, "frames"), "--out", out,
                "--registry", os.path.join(root, "none.json"), "--no-review", "made_graph"]
    try:
        with contextlib.redirect_stdout(buf):
            code = fxfinish.main()
    finally:
        sys.argv = argv
    if code != 0 or not os.path.isfile(os.path.join(out, "made_graph.png")):
        wrong.append("the kit's packer refused the frames: " + buf.getvalue().strip().splitlines()[-1][:200])
    if wrong:
        return say("fail", "graph self-test: " + "; ".join(wrong), "kit/vfx/comp.py graph_at / frames_of")
    return say("pass", "graph self-test: the starter graph bakes - a core that is the same in every frame and a halo that a noise tears and another bends, "
               "joined; it is no single node's picture, the packer packs it, and the same spec bakes the same frames", "none")


def main(argv):
    case = argv[0] if argv else "good"
    root = tempfile.mkdtemp(prefix="kit_graph_")
    try:
        if case == "idle":
            def spoil(g):
                g["nodes"]["ghost"] = {"op": "mul", "a": "clouds", "b": 0.0}
                g["nodes"]["all"] = {"op": "add", "a": "both", "b": "ghost"}
                g["value"] = "all"
            return refused(root, "made_idle", spoil, "do nothing", "a graph with a node multiplied by nothing")
        if case == "ring":
            def spoil(g):
                g["nodes"]["torn"] = {"op": "mul", "a": "halo", "b": "bent"}
            return refused(root, "made_ring", spoil, "goes round in a ring", "a graph whose nodes read each other")
        if case != "good":
            return say("fail", "graph self-test: name the case", "good | idle | ring")
        return good(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
