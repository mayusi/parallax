"""rearm.py — put a WEAPON into a finished R6 clip: the body as the animator (or the mocap) made it, both arms
re-solved onto the hilt, the blade drawn and timed.

    python kit/anim/rearm.py <Name>.rearm.json --out <clip.json>

The spec: {"name": "GreatswordLight1", "from": "SwordA", "sword": {"length": 4.8, "grip": 0.75, "grip_pitch": 0},
"hands": 2, "lag": 0.04, "events": [...], "feel": {...}, "gate": {...}}

Why: the best attack timing the kit has is REAL (UAL2's sword combo, folded to R6 - the owner's reference), and
every finished R6 attack keeps the body and lets the weapon follow the right arm. An R6 arm has no wrist: the blade's
direction is the right arm's, turned by `grip_pitch` (0 = out of the fist, perpendicular to the arm, the classic
Roblox grip; 90 = along the arm). The hilt sits in the right hand; a second hand (`hands`: 2) is solved onto it a
`grip` behind along the blade - the two-sphere solve of kit/anim/strike.py moves the hilt the least so both reach;
the steel trails the body by `lag` seconds (weight). Hits are re-timed to the blade tip's fastest frames (one per
strike). Torso, head and legs are untouched.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C      # noqa: E402
import strike as S    # noqa: E402

PARTS = ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def frame_at(joint, times, t):
    """the joint's (rotation 3x3, pos) at time t by linear/slerp interpolation of its frames"""
    fr = joint["frames"]
    if t <= times[0]:
        f = fr[0]
        return C.quat_mat(f[:4]), np.array(f[4:7], dtype=float)
    if t >= times[-1]:
        f = fr[-1]
        return C.quat_mat(f[:4]), np.array(f[4:7], dtype=float)
    k = int(np.searchsorted(np.array(times), t, side="right") - 1)
    k = max(0, min(k, len(fr) - 2))
    a, b = fr[k], fr[k + 1]
    u = (t - times[k]) / max(times[k + 1] - times[k], 1e-9)
    q = C.slerp(a[:4], b[:4], u)
    pos = np.array(a[4:7], dtype=float) * (1 - u) + np.array(b[4:7], dtype=float) * u
    return C.quat_mat(q), pos


def rearm(src, spec):
    sword = spec.get("sword") or {}
    length = float(sword.get("length", 4.8))
    spacing = float(sword.get("grip", 0.75))
    grip_pitch = math.radians(float(sword.get("grip_pitch", 0.0)))
    hands = int(spec.get("hands", 2))
    lag = float(spec.get("lag", 0.04))
    times = list(src["times"])
    J = src["joints"]
    if "Torso" not in J or "Right Arm" not in J:
        raise ValueError("the source clip needs Torso and Right Arm frames")
    grip_local = S.unit(np.array([0.0, -math.sin(grip_pitch), -math.cos(grip_pitch)]))   # the blade, in the arm's frame
    out = {k: [] for k in ("Right Arm", "Left Arm")}
    tips, grips, residuals = [], [], []
    twists = {"Right Arm": None, "Left Arm": None}
    inertia = float(spec.get("inertia", lag))                  # seconds: the steel's own momentum (a one-pole lag)
    G_f, d_f, G_solved = None, None, None
    for i, t in enumerate(times):
        torso_m, torso_p = C.quat_mat(J["Torso"]["frames"][i][:4]), np.array(J["Torso"]["frames"][i][4:7], dtype=float)
        # the steel trails: the right arm's pose a little earlier decides where the hilt is ...
        ts = max(times[0], t - lag)
        ra_m, ra_p = frame_at(J["Right Arm"], times, ts)
        tm_s, tp_s = frame_at(J["Torso"], times, ts)
        R_world = tm_s @ ra_m
        piv = tp_s + tm_s @ (S.SHOULDER["Right Arm"] + ra_p)
        hand = piv + R_world @ S.HAND["Right Arm"]
        d = S.unit(R_world @ grip_local)
        G = hand - d * spacing / 2 if hands == 2 else hand
        # ... and a heavy blade keeps its momentum: hilt and direction follow with a time constant (a whip in the
        # source becomes a sweep; a two-hand solve on a whip snapped the off hand half a turn in one frame)
        if inertia > 1e-6 and i > 0:
            dt = times[i] - times[i - 1]
            alpha = dt / (inertia + dt)
            G = G_f + (G - G_f) * alpha
            d = S.slerp(d_f, d, alpha)
        G_f, d_f = G.copy(), d.copy()
        if hands == 2:
            # the two reach spheres meet on a circle: the solve is started from the previous hilt (warm) so it stays
            # on the same branch frame to frame, and the solved hilt keeps its momentum too (a source hand far out
            # of two-hand reach - a mocap whip - otherwise teleports the hilt across the chest)
            start = G if G_solved is None else G_solved + (G - G_solved) * 0.5
            G, res = S.solve_grip(start, d, torso_m, torso_p, spacing)
            if G_solved is not None and inertia > 1e-6:
                dt = times[i] - times[i - 1]
                G = G_solved + (G - G_solved) * (dt / (inertia + dt))
                G, res = S.solve_grip(G, d, torso_m, torso_p, spacing)
            G_solved = G.copy()
            residuals.append(res)
            targets = {"Right Arm": G + d * spacing / 2, "Left Arm": G - d * spacing / 2}
        else:
            targets = {"Right Arm": G}
        grips.append(G)
        tips.append(G + d * (length - spacing / 2))
        for arm in ("Right Arm", "Left Arm"):
            if arm in targets:
                R, twists[arm] = S.arm_rotation(arm, targets[arm], torso_m, torso_p, d, twists[arm])
                out[arm].append(S.frame_of(R))
            elif arm in J:
                out[arm].append(list(J[arm]["frames"][i]))
    clip = {k: v for k, v in src.items() if k not in ("source", "events", "sword", "keys", "fitted_to", "params", "style", "finish", "finished", "finish_log")}
    clip["name"] = spec["name"]
    clip["joints"] = {k: dict(v) for k, v in J.items()}
    for arm, frames in out.items():
        if frames:
            clip["joints"][arm] = {"frames": frames}
    clip["sword"] = {"length": length, "grip": spacing, "tip": [[round(float(x), 4) for x in p] for p in tips],
                     "grip_path": [[round(float(x), 4) for x in p] for p in grips]}
    # Hits: one per strike, the frame after each local peak of the tip's speed at half the clip's top or more
    fps = int(src.get("fps") or 30)
    speeds = np.array([float(np.linalg.norm(tips[i + 1] - tips[i])) * fps for i in range(len(tips) - 1)])
    events = list(spec.get("events") or [])
    clip.pop("hit_inferred", None)                             # (the source clip's: this clip's Hits are its own)
    if not events and len(speeds) and speeds.max() > 1.0 and not src.get("loop"):
        top, last = float(speeds.max()), -10
        for i in range(len(speeds)):
            before = speeds[i - 1] if i > 0 else -1.0
            after = speeds[i + 1] if i + 1 < len(speeds) else -1.0
            if speeds[i] >= 0.5 * top and speeds[i] >= before and speeds[i] > after and i - last >= 4:
                events.append({"name": "Hit", "t": round(times[min(i + 1, len(times) - 1)], 4)})
                last = i
                clip["hit_inferred"] = [e["t"] for e in events]   # (placed at speed peaks: kit/anim/contact.py holds them to the geometry)
    clip["events"] = events
    clip["beats"] = spec.get("beats", src.get("beats"))
    clip["feel"] = spec.get("feel", src.get("feel"))
    gate = spec.get("gate")
    if gate is None:
        # the solved arms sweep after a whipping source: the pop bar is at least 60 unless the spec says otherwise
        gate = dict(src.get("gate") or {})
        gate["pop_deg"] = max(float(gate.get("pop_deg", 15)), 60.0)
        if (src.get("source") or {}).get("kind") == "import":
            gate.setdefault("penetration", 0.35)
    clip["gate"] = gate
    clip["priority"] = spec.get("priority", src.get("priority", "Action"))
    return clip, {"tip_peak": round(float(speeds.max()), 2) if len(speeds) else 0.0, "grip_moved": round(float(max(residuals)), 3) if residuals else 0.0,
                  "hits": [e["t"] for e in events if e.get("name") == "Hit"]}


def main(argv):
    if not argv:
        return emit("fail", "rearm: needs <Name>.rearm.json [--out <clip.json>]", "lune run kit anim rearm GreatswordLight1 --from SwordA")
    path = argv[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    spec["name"] = spec.get("name") or os.path.basename(path).split(".")[0]
    build = os.path.join(os.environ.get("KIT_BUILD", "build"), "animations")
    src_name = spec.get("from")
    if not src_name:
        return emit("fail", f"rearm {spec['name']}: the spec needs \"from\": <Clip>", f"edit {path}")
    src_path = None
    for cand in (os.path.join(build, f"{src_name}.clip.json"), os.path.join(build, f"{src_name}.r6.clip.json")):
        if os.path.isfile(cand):
            with open(cand, encoding="utf-8") as fh:
                c = json.load(fh)
            if c.get("rig") == "R6":
                src_path, src = cand, c
                break
    if src_path is None:
        return emit("fail", f"rearm {spec['name']}: no R6 clip for {src_name} in {build}", f"lune run kit anim {src_name}")
    try:
        clip, info = rearm(src, spec)
    except ValueError as e:
        return emit("fail", f"rearm {spec['name']}: {e}", f"fix {path}")
    clip["source"] = {"kind": "rearm", "file": path, "from": src_path, "sha256": S.sha256_of(path),
                      "data_sha256": S.sha256_of(src_path), "tool_sha256": S.sha256_of_many([__file__, C.__file__]),
                      "rig_sha256": S.sha256_of(C.rig_path("r6"))}
    # the clip it is built from, by IDENTITY (its own spec + tool hashes): kit anim rewrites clip files at compile, so
    # the bytes are no dependency key; when the upstream spec or generator changes, this clip is stale
    up = src.get("source") if isinstance(src.get("source"), dict) else {}
    clip["source"]["from_sha256"] = up.get("sha256")
    clip["source"]["from_tool_sha256"] = up.get("tool_sha256")
    rig = C.load_rig("r6")
    m = C.metrics(clip, rig, clip.get("gate"))
    out = out or os.path.join(build, f"{spec['name']}.clip.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(clip, fh, indent=1)
    note = f"blade tip peaks {info['tip_peak']} studs/s, hilt moved {info['grip_moved']} to reach, Hits at {info['hits']}"
    if m["problems"]:
        return emit("fail", f"rearm {spec['name']}: {m['problems'][0]}", f"the body is the source's: raise its gate in {path} with a note, or shorten lag / grip", problems=m["problems"], **info)
    return emit("pass", f"rearm {spec['name']} from {src_name}: {note}", f"lune run kit anim look {spec['name']} --rig R6", **info)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
