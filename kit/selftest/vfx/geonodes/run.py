#!/usr/bin/env python3
"""The self-test of GEOMETRY NODES, BAKED (kit/vfx/geonodes.py + geonodes_bake.py; the VFX methods audit, stage 22).

    python kit/selftest/vfx/geonodes/run.py good    a ripple and a scatter baked by the real command THROUGH BLENDER.
                                                    The ripple: every point's height in every frame is the tree's own
                                                    formula (amount * sin(2 pi (r * waves - t * speed)) * (1 - 2r)+,
                                                    to 0.002), its grid does not slide, a looped bake's last frame
                                                    steps into its first. The scatter: every strip is a square flat on
                                                    the ground whose middle stays put, quads nearer the middle grow
                                                    sooner, a quad's size at a frame is the front's own formula, it
                                                    turns at the spin said. The files say which Blender and which nodes
                                                    made them; the gate takes both (and refuses a hair bake, a looped
                                                    scatter, a missing file)
    python kit/selftest/vfx/geonodes/run.py early   a scatter of four frames (its front has not come): the command
                                                    must refuse it, saying "the mesh moves" (exit 1)
    python kit/selftest/vfx/geonodes/run.py slid    a good ripple whose grid was pushed sideways by hand in one frame:
                                                    the gate must refuse the layer that plays it ("the gate refuses")

Where there is no Blender every case FAILS saying "NOT RUN - no Blender here" (none of them says its needle then):
the self-test list shows three rows that are not green, which is what happened - nothing was baked.
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
import geonodes  # noqa: E402
import methods  # noqa: E402

import numpy as np  # noqa: E402


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def bake(root, name, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = geonodes.main([name, *argv, "--out-dir", os.path.join(root, "seq"), "--look-dir", os.path.join(root, "look")])
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def read(root, name):
    with open(os.path.join(root, "seq", f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


class NoSpecs:
    def get(self, key):
        return None


def gate(root, layer):
    by = methods.load()[1]
    return methods.proved(by["geometry_nodes"], [dict({"kind": "mesh", "pivot": "origin", "shape": "seq", "life": 2}, **layer)], NoSpecs(), root, "s") is not None


def good(root):
    wrong = []
    code, said = bake(root, "ring", "--recipe", "ripple", "--loop", "--speed", "2", "--frames", "24", "--cols", "16", "--rows", "16")
    if code != 0:
        return say("fail", "geonodes self-test: the ripple was refused: " + said["summary"][:240], "kit/vfx/geonodes.py, kit/vfx/geonodes_bake.py")
    d = read(root, "ring")
    a = d["args"]
    g = np.array(d["frames"]).reshape(len(d["frames"]), 17, 17, 3)
    r = np.hypot(g[0, ..., 0], g[0, ..., 2])
    worst = 0.0
    for f in range(len(g)):
        t = (f + 1) / a["fps"]
        want = a["amount"] * np.sin(2 * math.pi * (r * a["waves"] - t * a["speed"])) * np.maximum(1 - 2 * r, 0)
        worst = max(worst, float(np.abs(g[f, ..., 1] - want).max()))
    if worst > 0.002:
        wrong.append(f"the ripple's height is {worst:.4f} off its tree's own formula")
    if float(np.abs(g[..., [0, 2]] - g[0:1, ..., [0, 2]]).max()) > 1e-6:
        wrong.append("the ripple's grid slides")
    if not (g[0, 0, 0, 0] < g[0, 0, -1, 0] and g[0, 0, 0, 2] != g[0, -1, 0, 2]):
        wrong.append("the ripple's points are not in the sequence's order (rows of columns)")
    steps = np.abs(g[1:] - g[:-1]).max((1, 2, 3))
    if float(np.abs(g[0] - g[-1]).max()) > 1.5 * float(steps.max()):
        wrong.append("the looped ripple jumps from its last frame to its first")
    if not (isinstance(d.get("blender"), str) and "GeometryNodeSetPosition" in d.get("nodes", []) and "GeometryNodeInputSceneTime" in d["nodes"]):
        wrong.append("the ripple's file does not say the Blender and the nodes that made it")
    code, said = bake(root, "wide", "--recipe", "ripple", "--frames", "8", "--cols", "30", "--rows", "10", "--waves", "2")
    if code != 0:
        wrong.append("a ripple on a grid that is not square was refused: " + said["summary"][:160])
    else:
        w = read(root, "wide")
        gw = np.array(w["frames"]).reshape(8, 11, 31, 3)
        rw = np.hypot(gw[0, ..., 0], gw[0, ..., 2])
        t = 4 / w["args"]["fps"]
        want = w["args"]["amount"] * np.sin(2 * math.pi * (rw * w["args"]["waves"] - t * w["args"]["speed"])) * np.maximum(1 - 2 * rw, 0)
        if float(np.abs(gw[3, ..., 1] - want).max()) > 0.002 or not np.allclose(gw[0, 0, :, 0], np.linspace(-0.5, 0.5, 31), atol=1e-3):
            wrong.append("a ripple on 30 x 10 points is not its formula, or its columns are not along x")
    code, said = bake(root, "back", "--recipe", "ripple", "--speed", "20", "--fps", "24")
    if code == 0 or "quarter of a ring a frame" not in said["summary"]:
        wrong.append("a ripple at 20 rings a second and 24 frames a second was taken (its rings would run back in)")
    code, said = bake(root, "shards", "--recipe", "scatter", "--frames", "32")
    if code != 0:
        return say("fail", "geonodes self-test: the scatter was refused: " + said["summary"][:240], "kit/vfx/geonodes.py, kit/vfx/geonodes_bake.py")
    d = read(root, "shards")
    a = d["args"]
    q = np.array(d["frames"]).reshape(len(d["frames"]), d["strips"], 4, 3)
    if not 0.6 * a["count"] <= d["strips"] <= 1.6 * a["count"]:
        wrong.append(f"{d['strips']} quads for a count of about {a['count']}")
    size = np.linalg.norm(q[:, :, 1] - q[:, :, 0], axis=-1)
    centre = q.mean(2)
    rad = np.linalg.norm(centre[0][:, [0, 2]], axis=-1)
    off = 0.0
    for f in range(len(q)):
        t = (f + 1) / a["fps"]
        want = a["size"] * np.clip((t * a["speed"] - rad) / a["rise"], 0.02, 1)
        off = max(off, float(np.abs(size[f] - want).max()))
    if off > 0.002:
        wrong.append(f"a quad's size is {off:.4f} off the front's own formula")
    k = int(np.argmin(rad))  # the first to be full size: its turn between two late frames is spin / fps
    edge = q[:, k, 1] - q[:, k, 0]
    ang = np.unwrap(np.arctan2(edge[:, 2], edge[:, 0]))
    turn = abs(float(ang[-1] - ang[-2]))
    if abs(turn - abs(a["spin"]) / a["fps"]) > 0.01:
        wrong.append(f"a quad turns {turn:.3f} radians a frame, the spin said is {abs(a['spin']) / a['fps']:.3f}")
    if "GeometryNodeInstanceOnPoints" not in d.get("nodes", []) or "GeometryNodeDistributePointsOnFaces" not in d["nodes"]:
        wrong.append("the scatter's file does not name the nodes that instanced it")
    for name in ("ring", "shards"):
        if not all(c["ok"] for c in geonodes.check(read(root, name))):
            wrong.append(f"{name}: its own file fails its checks")
    with open(os.path.join(root, "seq", "mane.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(read(root, "ring"), recipe="hair"), fh)
    for what, layer, want in (("the ripple, looped", {"params": {"seq": "ring", "loop": True}}, True), ("the scatter", {"params": {"seq": "shards"}}, True),
                              ("the scatter, looped", {"params": {"seq": "shards", "loop": True}}, False), ("a hair bake", {"params": {"seq": "mane"}}, False),
                              ("a name with no file", {"params": {"seq": "nothing"}}, False)):
        if gate(root, layer) != want:
            wrong.append(f"the gate {'refused' if want else 'took'} {what}")
    if wrong:
        return say("fail", "geonodes self-test: " + "; ".join(wrong), "kit/vfx/geonodes.py, kit/vfx/geonodes_bake.py, kit/vfx/methods.py (kept_file)")
    return say("pass", f"geonodes self-test (Blender {d['blender']}): a ripple whose every height is its tree's formula and a scatter whose quads grow as the "
               "front's formula says, square, in place and turning at the spin said; the gate takes the bakes and nothing else", "none")


def early(root):
    code, said = bake(root, "soon", "--recipe", "scatter", "--frames", "4")
    return say("fail" if code != 0 and "the mesh moves" in said["summary"] else "pass",
               said["summary"] if code != 0 else "geonodes self-test: a scatter whose front has not come was baked", said["next_action"] if code != 0 else "kit/vfx/geonodes.py (check)")


def slid(root):
    code, said = bake(root, "ring", "--recipe", "ripple", "--waves", "2", "--frames", "16", "--cols", "12", "--rows", "12")
    if code != 0:
        return say("pass", "geonodes self-test: the good ripple was refused, so nothing was slid: " + said["summary"][:160], "kit/vfx/geonodes.py")
    d = read(root, "ring")
    took = gate(root, {"params": {"seq": "ring"}})
    d["frames"][7] = [x + 0.05 if i % 3 == 0 else x for i, x in enumerate(d["frames"][7])]
    with open(os.path.join(root, "seq", "ring.json"), "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    failed = [c for c in geonodes.check(d) if not c["ok"]]
    if took and not gate(root, {"params": {"seq": "ring"}}) and "the grid stays where it is" in [c["name"] for c in failed]:
        return say("fail", "geonodes self-test: the gate refuses the slid ripple: " + "; ".join(f"{c['name']}: {c['value']}" for c in failed), failed[0]["fix"])
    return say("pass", "geonodes self-test: a ripple whose grid was slid by hand still proves Geometry Nodes", "kit/vfx/geonodes.py (check)")


def main(argv):
    cases = {"good": good, "early": early, "slid": slid}
    if len(argv) != 1 or argv[0] not in cases:
        return say("fail", "geonodes self-test: name the case", "good | early | slid")
    if not geonodes.blender():  # (NOT a pass and NOT the caught fault: nothing was baked, and the row must say so)
        return say("fail", f"geonodes self-test ({argv[0]}): NOT RUN - no Blender here to run a tree in; nothing was baked or checked", "install Blender or set KIT_BLENDER, then run it again")
    root = tempfile.mkdtemp(prefix="kit_geonodes_")
    try:
        return cases[argv[0]](root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
