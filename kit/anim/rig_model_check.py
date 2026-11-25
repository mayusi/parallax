"""rig_model_check.py — the mathematical model (kit/anim/r6_rig_model.py) against the owner's rig itself: random poses of
every control, the rig evaluated by Blender, every part's 8 box corners compared.

    blender -b assets/rigs/R6_IK.blend --disable-autoexec --python-exit-code 2 -P kit/anim/rig_model_check.py -- <out.json> [N]
"""
import json
import math
import os
import random
import sys

import bpy
import numpy as np
from mathutils import Euler, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r6_rig_model as M  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = os.path.abspath(argv[0])
N = int(argv[1]) if len(argv) > 1 else 300
rig = bpy.data.objects["Rig1"]
P, B = rig.pose.bones, rig.data.bones
if rig.animation_data:
    rig.animation_data.action = None
REST = {n: (P[n].location.copy(), P[n].rotation_quaternion.copy(), P[n].rotation_euler.copy(), dict(P[n].items())) for n in P.keys()}
BOX = {"Torso": ((0, 0, 3), (2, 1, 2)), "Head": ((0, 0, 4.5), (2, 1, 1)), "Right Arm": ((1.5, 0, 3), (1, 1, 2)),
       "Left Arm": ((-1.5, 0, 3), (1, 1, 2)), "Right Leg": ((0.5, 0, 1), (1, 1, 2)), "Left Leg": ((-0.5, 0, 1), (1, 1, 2))}
CORNERS = {p: [np.array([c[0] + sx * s[0] / 2, c[1] + sy * s[1] / 2, c[2] + sz * s[2] / 2, 1.0])
                for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)] for p, (c, s) in BOX.items()}


def settle():
    """evaluate; then nudge a clamped value so the SoftIK driver cycle re-evaluates with the current slider"""
    bpy.context.view_layer.update()
    for s in ("SoftIK.L", "SoftIK.R"):
        P[s].location.z = 1e-5
    bpy.context.view_layer.update()
    for s in ("SoftIK.L", "SoftIK.R"):
        P[s].location.z = 0.0
    bpy.context.view_layer.update()


def reset():
    for n, (l, q, e, props) in REST.items():
        P[n].location, P[n].rotation_quaternion, P[n].rotation_euler = l, q, e
        for k, v in props.items():
            P[n][k] = v


def rq(rng, deg):
    """a random rotation up to deg degrees about a random axis -> [w, x, y, z]"""
    ax = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))).normalized()
    q = Quaternion(ax, math.radians(rng.uniform(-deg, deg)))
    return [q.w, q.x, q.y, q.z]


def yaw_q(deg, axis):
    q = Quaternion(Vector(axis), math.radians(deg))
    return [q.w, q.x, q.y, q.z]


def random_pose(rng, kind):
    c = {}
    if kind in ("all", "root"):
        c["Main Controller"] = {"loc": [rng.uniform(-1, 1), rng.uniform(-0.3, 0.3), rng.uniform(-1, 1)],
                                "quat": yaw_q(rng.uniform(-180, 180), (0, 1, 0))}       # local y = world up
    c["Body"] = {"loc": [rng.uniform(-0.8, 0.8), rng.uniform(-1.4, 0.3), rng.uniform(-0.8, 0.8)], "quat": rq(rng, 45)}
    c["Head.001"] = {"loc": [rng.uniform(-0.2, 0.2) for _ in range(3)], "quat": rq(rng, 50)}
    for a in ("Arm.R", "Arm.L"):
        c[a] = {"loc": [rng.uniform(-0.4, 0.4) for _ in range(3)], "quat": rq(rng, 120)}
    for f in ("Foot.R", "Foot.L"):
        c[f] = {"loc": [rng.uniform(-1.0, 1.0), rng.uniform(-1.5, 1.5), rng.uniform(-0.3, 1.4)],
                "quat": yaw_q(rng.uniform(-50, 50), (0, 0, 1))}
    for u in ("Uleg.R", "Uleg.L"):
        c[u] = {"loc": [rng.uniform(-0.4, 0.4) for _ in range(3)]}
    for k in ("FKLeg.R", "FKLeg.L"):
        c[k] = {"euler": [rng.uniform(-0.8, 0.8) for _ in range(3)], "loc": [rng.uniform(-0.2, 0.2) for _ in range(3)]}
    for w in ("Leg.R", "Leg.L"):
        c[w] = {"euler": [rng.uniform(-0.5, 0.5) for _ in range(3)]}
    for s, sign in (("SoftIK.L", 1), ("SoftIK.R", -1)):
        slider = rng.choice([0.0, 0.6, 1.0, 1.5, 2.0]) if kind != "ik" else 2.0
        c[s] = {"loc": [slider * sign, 0, 0], "FK": rng.random() < 0.5 if kind != "ik" else False}
    return c


def apply(c):
    reset()
    for name, v in c.items():
        pb = P[name]
        if "loc" in v:
            pb.location = Vector(v["loc"])
        if "quat" in v:
            pb.rotation_quaternion = Quaternion(v["quat"])
        if "euler" in v:
            pb.rotation_euler = Euler(v["euler"], pb.rotation_mode if pb.rotation_mode != "QUATERNION" else "XYZ")
            if pb.rotation_mode == "QUATERNION":       # the model reads euler XYZ for these
                pb.rotation_quaternion = Euler(v["euler"], "XYZ").to_quaternion()
        if "FK" in v:
            pb["FK"] = v["FK"]
    settle()


def rig_delta(part):
    return np.array(rig.matrix_world @ P[part].matrix) @ np.linalg.inv(np.array(B[part].matrix_local))


rng = random.Random(7)
results = {"trials": [], "summary": {}}
for kind, n in (("ik", N // 3), ("all", N - N // 3)):
    for t in range(n):
        c = random_pose(rng, kind)
        apply(c)
        model = M.parts(c)
        errs = {}
        for part, corners in CORNERS.items():
            Dr, Dm = rig_delta(part), model[part]
            errs[part] = max(float(np.linalg.norm((Dr @ p)[:3] - (Dm @ p)[:3])) for p in corners)
        feet = {f: c[f]["loc"] for f in ("Foot.R", "Foot.L")}
        results["trials"].append({"kind": kind, "err": errs, "soft": {s: c[s] for s in ("SoftIK.L", "SoftIK.R")},
                                  "body_loc": c["Body"]["loc"], "feet": feet})
for part in CORNERS:
    for kind in ("ik", "all"):
        es = sorted(tr["err"][part] for tr in results["trials"] if tr["kind"] == kind)
        if es:
            results["summary"][f"{part} [{kind}]"] = {"n": len(es), "median": round(es[len(es) // 2], 5),
                                                     "p95": round(es[int(len(es) * 0.95)], 5), "max": round(es[-1], 5)}
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(results, fh, indent=1)
print("MODEL_CHECK_DONE")
for k, v in results["summary"].items():
    print("SUMMARY", k, v)
