"""block.py — the BLOCKING PASS on the owner's rig (AAA plan #1, board/plans/archive/2026-10-18-aaa-anim-gaps.md; Arc System
Works, GDC 2015: the X factor was a workflow that lets the artist's intention carry through to the final result).
A strike move's KEY POSES only - held (constant interpolation, no in-betweens), the katana in the hands, the legs in IK
- go onto the owner's R6_IK rig as an editable Blender file; the owner moves what is wrong; the kit reads every change
back as edits to the move's keys (strike.py `key_edits`), so his poses survive every rebuild.

    python kit/anim/block.py export <Move>     -> assets/animations/<Move>Block.pose.json (+ prints the bake steps)
    python kit/anim/block.py base <Move>       -> assets/animations/blocks/<Move>.base.json (the as-exported bake)
    python kit/anim/block.py read <Move>       -> assets/animations/blocks/<Move>.edits.json (his changes per key)
`kit anim block <Move> [--base | --read]` runs these (and the bakes between)."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402

ANIM = os.path.join("assets", "animations")
BLOCKS = os.path.join(ANIM, "blocks")
BUILD = os.path.join(os.environ.get("KIT_BUILD", "build"), "animations")
FLOOR = -3.0                      # the character-space floor (strike.FLOOR_R6)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))


def key_frames(move):
    """the frames that are the move's KEY POSES: its keys' times, or - a move keyed densely for the solver (a spin keyed
    every 30 deg of turn so the grip never cuts the chord through the body, 2026-11-04) - the times it names in
    `block_keys` (seconds), so the blocking shows the owner its poses, not every interpolation key"""
    fps = int(move.get("fps") or 30)
    times = move.get("block_keys") or [k["t"] for k in move["keys"]]
    return sorted({int(round(float(t) * fps)) for t in times})


def soles(c, rig):
    """each foot's sole centre per frame (character space)"""
    W = C.world_frames(c, rig)
    return {lg: [(f[lg] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3] for f in W] for lg in ("Right Leg", "Left Leg")}


def export(name, suffix="Block", smooth=False):
    import pose_from as PF
    import strike as S
    move = json.load(open(os.path.join(ANIM, f"{name}.move.json"), encoding="utf-8"))
    move.pop("step", None)
    c, _ = S.generate(move)
    rig = C.load_rig("r6")
    spec = PF.pose_from(c, f"{name}{suffix}", every=1)
    frames = set(key_frames(move))
    # held (constant) for blocking; SMOOTH (Blender's bezier between the same keys) for the owner to ANIMATE on
    keys = [dict(k, ease="bezier" if smooth else "constant") for k in spec["keys"] if int(round(float(k["f"]))) in frames]
    so = soles(c, rig)
    sw = move.get("sword") or {}
    sp = float(sw.get("grip", 0.75))
    stage = lambda v: [round(float(v[0]), 4), round(float(v[1]) - FLOOR, 4), round(-float(v[2]), 4)]   # char -> stage
    for k in keys:
        f = int(round(float(k["f"])))
        # the arms as the strike holds the katana: each hand ON the hilt, the blade's direction - the rig solves the
        # arms to the hands and turns the sword in the fist (pose_r6 grip "animated")
        G = np.array(c["sword"]["grip_path"][f], float)
        d = np.array(c["sword"]["tip"][f], float) - G
        d /= np.linalg.norm(d)
        k["right_arm"] = {"hand": stage(G + d * sp / 2), "blade": [round(float(d[0]), 4), round(float(d[1]), 4), round(-float(d[2]), 4)]}
        k["left_arm"] = {"hand": stage(G - d * sp / 2)}
        for lg, field in (("Right Leg", "right_foot"), ("Left Leg", "left_foot")):
            p = so[lg][f]
            k[field] = {"at": [round(float(p[0]), 3), round(float(-p[2]), 3)], "lift": round(max(0.0, float(p[1]) - FLOOR), 3)}
    spec.update(keys=keys, legs="ik", dossier=move.get("dossier"), blocking=True, arm_stretch=float(move.get("arm_slide", 0.5)),
                sword={"blade": float(sw.get("length", 3.6)), "spacing": sp, "grip": "animated", "kind": sw.get("kind")},
                note=(f"FOR THE OWNER TO ANIMATE: {name} on the R6_IK rig, its {len(keys)} keys SMOOTH (bezier) - move, add "
                      f"or delete keys on any controller (Body, Head.001, Arm.R / Arm.L, Foot.R / Foot.L, the Uleg "
                      f"sockets), retime them, save; the kit reads it back (kit anim block {name} --edit --read)") if smooth else
                     (f"BLOCKING for the owner: {name}'s {len(keys)} key poses only, HELD (no in-betweens) on the R6_IK rig "
                      f"- move any controller (Body, Arm.R / Arm.L, Foot.R / Foot.L, the Uleg sockets) at a key frame, "
                      f"save; the kit reads it back (kit anim block {name} --read)"))
    spec.setdefault("pose_from", {})["block_of"] = name
    path = os.path.join(ANIM, f"{name}{suffix}.pose.json")
    json.dump(spec, open(path, "w", encoding="utf-8", newline="\n"), indent=1)
    return path, [k["f"] for k in keys]


def _clip(name, suffix="Block"):
    return json.load(open(os.path.join(BUILD, f"{name}{suffix}.clip.json"), encoding="utf-8"))


def _tag(suffix):
    return "" if suffix == "Block" else f".{suffix.lower()}"


def base(name, suffix="Block"):
    os.makedirs(BLOCKS, exist_ok=True)
    path = os.path.join(BLOCKS, f"{name}{_tag(suffix)}.base.json")
    json.dump(_clip(name, suffix), open(path, "w", encoding="utf-8", newline="\n"))
    return path


def rotvec(R):
    q = C.mat_quat(np.asarray(R, float))            # x, y, z, w
    x, y, z, w = (float(v) for v in q)
    s = np.sqrt(max(1e-12, 1 - w * w))
    ang = 2 * np.arccos(max(-1.0, min(1.0, w)))
    if ang > np.pi:
        ang -= 2 * np.pi
    return np.array([x, y, z]) / s * ang if s > 1e-6 else np.zeros(3)


def euler_of(R):
    """(pitch, yaw, roll) degrees of R = Rx(pitch) Ry(yaw) Rz(roll) (clip.euler_mat, strike's torso)"""
    R = np.asarray(R, float)
    yaw = np.arcsin(max(-1.0, min(1.0, R[0, 2])))
    pitch = np.arctan2(-R[1, 2], R[2, 2])
    roll = np.arctan2(-R[0, 1], R[0, 0])
    return np.degrees([pitch, yaw, roll])


def edits(b, e, move):
    """his changes at each key: the hilt (grip), the blade's direction, the torso's yaw / pitch / roll and height, the
    feet, the legs' sockets - deltas in the move's own terms (character space; degrees)"""
    rig = C.load_rig("r6")
    fps = int(move.get("fps") or 30)
    sb, se = soles(b, rig), soles(e, rig)
    out, hips = {}, {"right": [], "left": []}
    Tb, Te = b["joints"]["Torso"]["frames"], e["joints"]["Torso"]["frames"]
    # a move with `block_keys`: only those are poses he sees and moves (between them the blocking holds the last one)
    blk = set(key_frames(move)) if move.get("block_keys") else None
    for ki, k in enumerate(move["keys"]):
        f = min(len(Tb) - 1, int(round(float(k["t"]) * fps)))
        if blk is not None and int(round(float(k["t"]) * fps)) not in blk:
            continue
        ed = {}
        gb, ge = np.array(b["sword"]["grip_path"][f]), np.array(e["sword"]["grip_path"][f])
        db = np.array(b["sword"]["tip"][f]) - gb
        de = np.array(e["sword"]["tip"][f]) - ge
        db, de = db / np.linalg.norm(db), de / np.linalg.norm(de)
        if np.linalg.norm(ge - gb) > 0.02:
            ed["grip"] = [round(float(x), 4) for x in ge - gb]
        if float(np.degrees(np.arccos(np.clip(db @ de, -1, 1)))) > 1.0:
            ed["dir"] = [round(float(x), 4) for x in de - db]
        # the torso's change in the move's own angles: both poses decomposed Rx(pitch) Ry(yaw) Rz(roll), subtracted
        # (a rotation vector mixed the axes: a yaw of 15 read back with a roll of -4.6 - review 2026-10-18)
        da = (euler_of(C.quat_mat(Te[f][:4])) - euler_of(C.quat_mat(Tb[f][:4])) + 180.0) % 360.0 - 180.0
        for ax, field in ((0, "pitch"), (1, "yaw"), (2, "roll")):
            if abs(da[ax]) > 1.0:
                ed[field] = round(float(da[ax]), 2)
        dy = float(Te[f][5] - Tb[f][5])
        if abs(dy) > 0.02:
            ed["pos_y"] = round(dy, 4)
        for lg, field in (("Right Leg", "right"), ("Left Leg", "left")):
            d = se[lg][f] - sb[lg][f]
            if np.hypot(d[0], d[2]) > 0.02:
                ed[field] = [round(float(d[0]), 4), round(float(d[2]), 4)]
            # the leg's socket in the torso frame (the owner moved the Uleg sockets for his legs, 2026-10-18)
            Lb, Le = b["joints"][lg]["frames"][f], e["joints"][lg]["frames"][f]
            hips[field].append(np.array(Le[4:7], float) - np.array(Lb[4:7], float))
        if ed:
            out[str(ki)] = ed
    res = {"move": move["name"], "keys": out}
    hip = {s: np.mean(v, axis=0) for s, v in hips.items() if v}
    if any(np.linalg.norm(v) > 0.05 for v in hip.values()):
        res["hip_offset"] = {s: [round(float(x), 4) for x in v] for s, v in hip.items()}
    return res


def merge(old, new):
    """two rounds of edits -> one: per key and field, deltas summed (dir summed then the move renormalises)"""
    out = {"move": new.get("move") or old.get("move"), "keys": {k: dict(v) for k, v in (old.get("keys") or {}).items()}}
    for k, ed in (new.get("keys") or {}).items():
        cur = out["keys"].setdefault(k, {})
        for f, v in ed.items():
            if f in cur:
                cur[f] = [round(float(a) + float(b), 4) for a, b in zip(cur[f], v)] if isinstance(v, list) else round(float(cur[f]) + float(v), 4)
            else:
                cur[f] = v
    ho = {}
    for src in (old.get("hip_offset") or {}, new.get("hip_offset") or {}):
        for s, v in src.items():
            ho[s] = [round(float(a) + float(b), 4) for a, b in zip(ho.get(s, [0.0, 0.0, 0.0]), v)]
    if ho:
        out["hip_offset"] = ho
    return out


def arm_poses(clip, frames):
    """the owner's ARM POSES from his baked file at the given frames: each arm's torso-relative joint frame and the
    sword in the right arm part's frame (strike.py arms_pose)"""
    rig = C.load_rig("r6")
    W = C.world_frames(clip, rig)
    out = {}
    for f in frames:
        f = min(int(f), len(W) - 1)
        inv = np.linalg.inv(W[f]["Right Arm"])
        g = np.array(clip["sword"]["grip_path"][f], float)
        t = np.array(clip["sword"]["tip"][f], float)
        out[str(f)] = {"Right Arm": [round(float(v), 6) for v in clip["joints"]["Right Arm"]["frames"][f]],
                       "Left Arm": [round(float(v), 6) for v in clip["joints"]["Left Arm"]["frames"][f]],
                       "grip_local": [round(float(v), 5) for v in (inv @ np.append(g, 1.0))[:3]],
                       "tip_local": [round(float(v), 5) for v in (inv @ np.append(t, 1.0))[:3]]}
    return out


def read(name, suffix="Block"):
    move = json.load(open(os.path.join(ANIM, f"{name}.move.json"), encoding="utf-8"))
    b = json.load(open(os.path.join(BLOCKS, f"{name}{_tag(suffix)}.base.json"), encoding="utf-8"))
    res = edits(b, _clip(name, suffix), move)
    path = os.path.join(BLOCKS, f"{name}.edits.json")
    # a SECOND blocking round: the base already carries the first round's edits (the move applies them), so the new
    # deltas ADD to them - never replace them (review 2026-10-18)
    if os.path.exists(path):
        res = merge(json.load(open(path, encoding="utf-8")), res)
    json.dump(res, open(path, "w", encoding="utf-8", newline="\n"), indent=1)
    return path, res


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) < 2 or argv[0] not in ("export", "base", "read", "arms"):
        print(__doc__)
        return 2
    cmd, name = argv[0], argv[1]
    edit = "--edit" in argv                     # the SMOOTH file for the owner to animate on: <Move>Edit
    suffix = "Edit" if edit else "Block"
    if cmd == "arms":
        frames = [int(x) for x in argv[argv.index("--frames") + 1].split(",")] if "--frames" in argv else [0]
        res = arm_poses(_clip(name, suffix), frames)
        os.makedirs(BLOCKS, exist_ok=True)
        path = os.path.join(BLOCKS, f"{name}.arms.json")
        json.dump({"move": name, "from": f"{name}{suffix}", "poses": res}, open(path, "w", encoding="utf-8", newline=chr(10)), indent=1)
        emit("pass", f"block {name}: the owner's arm poses at frames {frames} -> {path}",
             "give the move's keys `arms_pose` from it (strike.py apply_arm_poses), regenerate, look")
        return 0
    if cmd == "export":
        path, frames = export(name, suffix, smooth=edit)
        emit("pass", f"block {name}: {len(frames)} key poses {'smooth' if edit else 'held'} -> {path}",
             f"lune run kit anim {name}{suffix} && lune run kit anim edit {name}{suffix} && lune run kit anim {name}{suffix} "
             f"&& python kit/anim/block.py base {name}{' --edit' if edit else ''}  (then the owner edits "
             f"assets/animations/{name}{suffix}.blend)", frames=frames)
    elif cmd == "base":
        emit("pass", f"block {name}: base saved -> {base(name, suffix)}",
             f"the owner edits assets/animations/{name}Block.blend; then: lune run kit anim block {name} --read")
    else:
        path, res = read(name, suffix)
        n = len(res["keys"])
        emit("pass", f"block {name}: {n} key(s) changed{' + hip sockets' if 'hip_offset' in res else ''} -> {path}",
             "regenerate the move (its generator applies blocks/<Move>.edits.json as key_edits), then look at it"
             if n or "hip_offset" in res else "nothing changed - the owner's file matches the export", keys=res["keys"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
