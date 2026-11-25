"""kfs_import.py — a Roblox KeyframeSequence (dumped by kit/anim/kfs_dump.luau) -> the kit's R6-NATIVE clip.

    python kit/anim/kfs_import.py <dump.json> --spec <Name>.import.json --out <clip.json>

Why: finished R6 animations by Roblox animators (community packs, Roblox's own defaults) are the data the owner's
eye trusts. Imported EXACTLY as they are (no fold, no retarget: an R6 KeyframeSequence IS an R6 clip), they are the
reference every kit gait and strike is measured against, and the quality the owner judges on their rig.

Every Pose holds a joint-space CFrame (Motor6D.Transform); the kit's clip holds the same joint in CHARACTER space:
rot = C0r * T * C0r^T, pos = C0r * t. Each Pose's easing shapes the motion FROM its keyframe TO the next (the
engine's rule; kit/anim/clip.py ease). A joint absent from a keyframe holds across it (the engine interpolates
across missing Poses). The result is sampled at the sequence's NATIVE rate - the finest keyframe spacing, snapped to
24 / 30 / 60 fps - or the spec's fps when that is higher, never lower: a sprint keyed every 60th of a second imported
at 30 fps lost every other frame and played its fast frames as visible snaps (2026-10-11). Its keyframes are kept
as `keys`.
"""
import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C   # noqa: E402

R6_PARTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
# an R15 KeyframeSequence (a Moon Animator / Studio editor pack on an R15 rig): kept in R15 joint names and folded to
# R6 by the compiler like every other R15 clip (2026-10-11: the owner's grapple pack imported as a Head alone)
R15_PARTS = ["LowerTorso", "UpperTorso", "Head", "RightUpperArm", "RightLowerArm", "RightHand", "LeftUpperArm",
             "LeftLowerArm", "LeftHand", "RightUpperLeg", "RightLowerLeg", "RightFoot", "LeftUpperLeg", "LeftLowerLeg",
             "LeftFoot"]
GATE_DEFAULT = {"foot_slide": 1.0, "foot_skate": 1.0, "pop_deg": 60, "penetration": 0.5, "loop_seam_deg": 5.0}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read())
    return h.hexdigest()


def sha256_of_many(paths):
    h = hashlib.sha256()
    for p in paths:
        with open(p, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def cf_parts(components):
    x, y, z = components[:3]
    r = np.array(components[3:12], dtype=float).reshape(3, 3)
    return r, np.array([x, y, z], dtype=float)


def to_character(rig, part, pose_cf):
    """joint-space Pose CFrame -> (3x3 rotation, pos) at the joint in character space"""
    c0 = np.array(rig["joints"][part]["c0"], dtype=float)
    c0r = c0[3:12].reshape(3, 3)
    t_rot, t_pos = cf_parts(pose_cf)
    return c0r @ t_rot @ c0r.T, c0r @ t_pos


def euler_of(m):
    """3x3 -> [x, y, z] degrees in CFrame.Angles order (Rx * Ry * Rz)"""
    sy = max(-1.0, min(1.0, float(m[0, 2])))
    y = math.asin(sy)
    if abs(sy) < 0.999999:
        x = math.atan2(-m[1, 2], m[2, 2])
        z = math.atan2(-m[0, 1], m[0, 0])
    else:
        x = math.atan2(m[2, 1], m[1, 1])
        z = 0.0
    return [round(math.degrees(v), 4) for v in (x, y, z)]


def native_fps(kfs):
    """the finest keyframe spacing as a frame rate, snapped to 24 / 30 / 60 (a hand-keyed clip: 30)"""
    ts = sorted({round(float(kf["t"]), 6) for kf in kfs})
    gaps = [b - a for a, b in zip(ts, ts[1:]) if b - a > 1e-4]
    if not gaps:
        return 30
    rate = 1.0 / min(gaps)
    return min((24, 30, 60), key=lambda r: abs(r - rate)) if rate < 75 else 60


def convert(dump, spec, rig):
    kfs = dump["keyframes"]
    if len(kfs) < 2:
        raise ValueError("a KeyframeSequence needs at least two keyframes")
    fps = max(int(spec.get("fps") or 30), native_fps(kfs))
    t0 = float(kfs[0]["t"])
    for kf in kfs:
        kf["t"] = float(kf["t"]) - t0
    duration = float(kfs[-1]["t"])
    r15 = any("UpperTorso" in kf["poses"] or "LowerTorso" in kf["poses"] for kf in kfs)
    if r15:
        rig = C.load_rig("r15")
    parts = [p for p in (R15_PARTS if r15 else R6_PARTS) if any(p in kf["poses"] for kf in kfs)]
    if not parts:
        raise ValueError("no R6 or R15 joint is posed")
    # per joint: its own key list (a keyframe without the joint holds it; the easing is the previous key's)
    keys = {p: [] for p in parts}
    for kf in kfs:
        for p in parts:
            pose = kf["poses"].get(p)
            if pose is None:
                continue
            rot, pos = to_character(rig, p, pose["cf"])
            keys[p].append({"t": kf["t"], "rot": rot, "pos": pos, "ease": pose.get("easing", "Linear"), "dir": pose.get("dir", "In"),
                            "quat": C.mat_quat(rot)})
    n = int(round(duration * fps))
    times = [round(i / fps, 6) for i in range(n + 1)]
    loop = bool(spec["loop"]) if spec.get("loop") is not None else bool(dump.get("loop"))   # the spec overrides an editor default
    joints = {}
    for p in parts:
        ks = keys[p]
        if ks[0]["t"] > 1e-9:                                 # rest until the first key (the engine's rule)
            ks.insert(0, {"t": 0.0, "rot": np.eye(3), "pos": np.zeros(3), "ease": "Linear", "dir": "In", "quat": [0, 0, 0, 1]})
        if loop and ks[-1]["t"] < duration - 1e-9:            # a loop returns to its first key at the end
            ks.append({**ks[0], "t": duration})
        frames = []
        for t in times:
            k = 0
            while k + 1 < len(ks) and ks[k + 1]["t"] <= t + 1e-9:
                k += 1
            a = ks[k]
            if k + 1 >= len(ks) or ks[k + 1]["t"] - a["t"] < 1e-9:
                q, pos = a["quat"], a["pos"]
            else:
                b = ks[k + 1]
                u = (t - a["t"]) / (b["t"] - a["t"])
                w = C.ease(a["ease"], a["dir"], u)
                q = C.slerp(a["quat"], b["quat"], w)
                pos = a["pos"] * (1 - w) + b["pos"] * w
            frames.append([round(float(v), 6) for v in q] + [round(float(v), 5) for v in pos])
        joints[p] = {"frames": frames,
                     "keys": [{"t": round(k["t"], 6), "rot": euler_of(k["rot"]), "pos": [round(float(v), 5) for v in k["pos"]],
                               "ease": k["ease"], "dir": k["dir"]} for k in ks]}
    events = list(spec.get("events") or [])
    for kf in kfs:
        for m in kf.get("markers") or []:
            events.append({"name": m["name"], "t": round(kf["t"], 6)})
    clip = {"schema": 1, "name": spec["name"], "rig": "R15" if r15 else "R6", "fps": fps, "duration": times[-1], "loop": loop,
            "priority": spec.get("priority") or dump.get("priority") or ("Movement" if loop else "Action"),
            "joints": joints, "times": times, "events": events, "beats": spec.get("beats"), "feel": spec.get("feel"),
            "gate": spec.get("gate") if spec.get("gate") is not None else dict(GATE_DEFAULT)}
    if spec.get("speed"):
        clip["locomotion"] = {"speed": float(spec["speed"]), "direction": [0.0, 0.0, -1.0], "cycle": round(duration, 4)}
    return clip, {"keyframes": len(kfs), "native_fps": native_fps(kfs), "joints": parts, "easings": sorted({k["ease"] for p in parts for k in keys[p]})}


def main(argv):
    if not argv:
        return emit("fail", "kfs_import: needs <dump.json> --spec <Name>.import.json [--out <clip.json>]", "lune run kit anim import <file.rbxm> --clip <KeyframeSequence> --as <Name>")
    dump_path = argv[0]
    spec_path = argv[argv.index("--spec") + 1] if "--spec" in argv else None
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    spec = {}
    if spec_path:
        with open(spec_path, encoding="utf-8") as fh:
            spec = json.load(fh)
    if dump_path.lower().endswith((".rbxm", ".rbxmx", ".rbxl", ".rbxlx")):
        # a model file straight from the spec: kit/anim/kfs_dump.luau (Lune reads the Roblox binary) dumps the
        # named KeyframeSequence beside the clip
        import subprocess
        import tempfile
        tmp = os.path.join(tempfile.mkdtemp(), "kfs.json")
        args = ["lune", "run", os.path.join(HERE, "kfs_dump.luau"), dump_path, tmp] + ([spec["clip"]] if spec.get("clip") else [])
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode != 0:
            last = (r.stdout.strip().splitlines() or [r.stderr.strip()])[-1]
            try:
                return emit("fail", json.loads(last).get("summary", last), json.loads(last).get("next_action", ""))
            except Exception:
                return emit("fail", f"kfs_import: the dump failed: {last[:300]}", "lune run kit/anim/kfs_dump.luau <file> <out.json> <clip>")
        dump_path = tmp
    with open(dump_path, encoding="utf-8") as fh:
        dump = json.load(fh)
    if "keyframes" not in dump:
        # a Studio report (kit/anim/kfs_studio.luau): {assetId: {sequences: [...]}} or {sequences: [...]} - pick the
        # named sequence (--clip in the spec), else the only one
        seqs = []
        if isinstance(dump.get("sequences"), list):
            seqs = dump["sequences"]
        else:
            for v in dump.values():
                if isinstance(v, dict) and isinstance(v.get("sequences"), list):
                    seqs.extend(v["sequences"])
        want = spec.get("clip")
        names = [q.get("name") for q in seqs]
        pick = [q for q in seqs if not want or q.get("name") == want]
        if not pick:
            return emit("fail", f"kfs_import: no KeyframeSequence {want!r} in {dump_path}", f"one of: {', '.join(map(str, names))}")
        if len(pick) > 1 and not want:
            return emit("fail", f"kfs_import: {dump_path} holds {len(pick)} sequences", f"name one: --clip <{' | '.join(map(str, names))}>")
        dump = dict(pick[0])
        dump.setdefault("file", dump_path)
    spec["name"] = spec.get("name") or dump.get("name") or "Imported"
    rig = C.load_rig("r6")
    try:
        clip, info = convert(dump, spec, rig)
    except ValueError as e:
        return emit("fail", f"kfs_import {spec['name']}: {e}", "pick another KeyframeSequence (--clip <name>)")
    src = spec.get("file") or dump.get("file")
    clip["source"] = {"kind": "import", "file": spec_path or dump_path, "data": src, "clip": dump.get("name"),
                      "sha256": sha256_of(spec_path) if spec_path else sha256_of(dump_path),
                      "data_sha256": sha256_of(src) if src and os.path.isfile(src) else None,
                      "tool_sha256": sha256_of_many([__file__, C.__file__]), "rig_sha256": sha256_of(C.rig_path(clip["rig"].lower()))}
    rig = C.load_rig(clip["rig"].lower())                  # an R15 sequence is measured on the R15 rig
    m = C.metrics(clip, rig, clip.get("gate"))
    out = out or os.path.join(os.environ.get("KIT_BUILD", "build"), "animations", f"{spec['name']}.clip.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(clip, fh, indent=1)
    note = f"{info['keyframes']} keyframes -> {len(clip['times'])} frames at {clip['fps']} fps, joints {', '.join(info['joints'])}, easing {', '.join(info['easings'])}"
    if m["problems"]:
        return emit("fail", f"kfs_import {spec['name']}: {m['problems'][0]}", f"this is the source as it is: raise its gate in {spec_path} with a note, or pick another clip",
                    problems=m["problems"], **info)
    return emit("pass", f"kfs_import {spec['name']}: {note}", f"lune run kit anim look {spec['name']} --rig R6", **info)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
