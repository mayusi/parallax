"""learn_compose.py — INVENT a move by combining what loved animators did (owner 2026-10-12: "invent the poses by
learning from the catalog ... what about the footwork"). A move = the BODY of one loved animation (Torso + legs +
the root's height: the stance, the steps, the weight shift, the torso's arc, the timing) under the ARMS of another
(two-handed sword arms, relative to the torso), the arms PHASE-ALIGNED: their guard / wind-up / strike / follow / end
(kit/anim/pose_bank.py phases) are re-timed onto the body's, so the arms strike when the body strikes.

    from learn_compose import compose
    clip = compose(body_clip, arms_clip, arms=("Right Arm", "Left Arm"), head="body")

Both clips are the kit's R6 clips (joint frames relative to the parent part), so the composition is exact per joint:
the legs plant where the body animator planted them, the hands stay together where the sword animator put them."""
import copy
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import derive as D  # noqa: E402
import pose_bank as PB  # noqa: E402


def warp(src_marks, dst_marks, t):
    """piecewise-linear time map: dst time t -> the source time at the same phase position"""
    for i in range(len(dst_marks) - 1):
        a, b = dst_marks[i], dst_marks[i + 1]
        if t <= b or i == len(dst_marks) - 2:
            u = 0.0 if b - a < 1e-9 else min(max((t - a) / (b - a), 0.0), 1.0)
            return src_marks[i] + u * (src_marks[i + 1] - src_marks[i])
    return src_marks[-1]


def marks(c, rig):
    _, ph = PB.phases(c, rig)
    fps = float(c.get("fps") or 30)
    m = [ph["guard"], ph["wind"], ph["strike"], ph["follow"], ph["end"]]
    for i in range(1, len(m)):                       # strictly increasing (a degenerate phase gets one frame)
        m[i] = max(m[i], m[i - 1] + 1)
    return [x / fps for x in m]


def compose(body, arms_src, arms=("Right Arm", "Left Arm"), head="body", name=None):
    rig = C.load_rig("r6")
    out = copy.deepcopy(body)
    out["name"] = name or f"{body.get('name')}+{arms_src.get('name')}"
    mb, ma = marks(body, rig), marks(arms_src, rig)
    fa = float(arms_src.get("fps") or 30)
    take = list(arms) + (["Head"] if head == "arms" else [])
    for j in take:
        if j not in arms_src["joints"]:
            continue
        F = D.frames_of(arms_src, j)
        D.set_frames(out, j, [D.sample(F, warp(ma, mb, t) * fa) for t in out["times"]])
        out["joints"][j].pop("keys", None)
    out["source"] = {"kind": "learn_compose", "body": body.get("name"), "arms": arms_src.get("name"),
                     "body_phases_s": [round(x, 3) for x in mb], "arms_phases_s": [round(x, 3) for x in ma]}
    out["events"] = [{"name": "Hit", "t": round(mb[2], 4)}]
    return out
