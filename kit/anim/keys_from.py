"""keys_from.py — a finished R6 reference clip -> EDITABLE technique keys (a .move.json for kit/anim/strike.py).

    python kit/anim/keys_from.py <reference R6 clip.json> --as <Name> --out <Name>.move.json [--length 5.2]
        [--grip 0.8] [--grip-pitch 20] [--every 2]

Why: the owner's bar is what Roblox animators ship. Re-arming keeps a reference's body but cannot change what the
arms do; a generator from scratch has none of the body. This reads the reference's BODY as strike.py keys - the
torso's pitch / yaw / roll / position, each foot's floor point and height, the head's look - at the frames where
its curves turn (the animator's own key poses), and the weapon's hilt and direction where the reference's right
hand is. strike.py then regenerates the reference's body with the kit's own solver; edit the `grip` / `dir` keys to
give the move a greatsword arc while the body stays the animator's. kit anim measure <Name> --vs <Ref> says how
close the regeneration is."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C      # noqa: E402
import measure as M   # noqa: E402
import strike as S    # noqa: E402


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def turning_points(values, min_gap):
    """indices where a curve turns (local extremes), at least min_gap apart, plus the ends"""
    idx = {0, len(values) - 1}
    last = -min_gap
    for i in range(1, len(values) - 1):
        if (values[i] - values[i - 1]) * (values[i + 1] - values[i]) < 0 and i - last >= min_gap:
            idx.add(i)
            last = i
    return idx


def keys_from(ref, length, spacing, grip_pitch, every, hands=2):
    rig = C.load_rig("r6")
    frames = C.world_frames(ref, rig)
    times = ref["times"]
    J = ref["joints"]
    n = len(times)
    torso = [(C.quat_mat(J["Torso"]["frames"][i][:4]), np.array(J["Torso"]["frames"][i][4:7], dtype=float)) for i in range(n)]
    def unwrapped(series):
        """degrees, continuous across +-180 (a spinning torso keyed wrapped would turn the long way between keys)"""
        arr = np.degrees(np.unwrap(np.radians(np.array(series, dtype=float)), axis=0))
        return [tuple(float(v) for v in row) for row in arr]

    pyr_t = unwrapped([M.pyr(m) for m, _ in torso])
    head = unwrapped([M.pyr(C.quat_mat(J["Head"]["frames"][i][:4])) if "Head" in J else (0.0, 0.0, 0.0) for i in range(n)])
    leg_rot = {leg: unwrapped([M.pyr(C.quat_mat(J[leg]["frames"][i][:4])) for i in range(n)]) for leg in ("Right Leg", "Left Leg") if leg in J}
    arm_rot = {arm: unwrapped([M.pyr(C.quat_mat(J[arm]["frames"][i][:4])) for i in range(n)]) for arm in ("Right Arm", "Left Arm") if arm in J}
    arm_pitch = [M.pyr(C.quat_mat(J["Right Arm"]["frames"][i][:4]))[0] if "Right Arm" in J else 0.0 for i in range(n)]
    grip_local = S.unit(np.array([0.0, -math.sin(math.radians(grip_pitch)), -math.cos(math.radians(grip_pitch))]))
    # the frames where the animator's curves turn: torso pitch, torso height, the sword arm
    picks = turning_points([p[0] for p in pyr_t], every) | turning_points([p[1] for _, p in torso], every) | turning_points(arm_pitch, every)
    if every <= 1:                                        # --every 1: every frame of the reference is a key
        picks = set(range(n))
    else:                                                 # never more than 4 frames without a key
        picks |= set(range(0, n, 4))
    keys = []
    for i in sorted(picks):
        m, p = torso[i]
        pitch, yaw, roll = pyr_t[i]
        key = {"t": round(times[i], 4), "pitch": round(pitch, 1), "yaw": round(yaw, 1), "roll": round(roll, 1),
               "pos": [round(float(v), 3) for v in p]}
        # strike.py keys the torso as euler((pitch, yaw, roll)) in the clip's own convention: the measured pyr IS that
        for leg, name in (("Right Leg", "right"), ("Left Leg", "left")):
            if leg in frames[i]:
                sole = frames[i][leg] @ np.array([0.0, -1.0, 0.0, 1.0])
                key[name] = [round(float(sole[0]), 3), 0.0, round(float(sole[2]), 3)]
                key[name + "_h"] = round(max(0.0, float(sole[1]) - S.FLOOR_R6), 3)
            if leg in leg_rot:                                    # and the leg exactly as the animator keyed it
                key[name + "_rot"] = [round(float(v), 1) for v in leg_rot[leg][i]]
                key[name + "_off"] = [round(float(v), 3) for v in J[leg]["frames"][i][4:7]]
        key["legs"] = "keyed"
        hp, hy, _ = head[i]
        key["look_pitch"] = round(hp + 0.5 * pitch, 1)
        key["look_yaw"] = round(hy + 0.6 * yaw, 1)
        rh, lh = key.get("right_h", 0.0), key.get("left_h", 0.0)
        key["weight"] = "both" if abs(rh - lh) < 0.05 else ("right" if rh < lh else "left")
        if "Right Arm" in J:
            ra = C.quat_mat(J["Right Arm"]["frames"][i][:4])
            ra_p = np.array(J["Right Arm"]["frames"][i][4:7], dtype=float)
            R_world = m @ ra
            hand = p + m @ (S.SHOULDER["Right Arm"] + ra_p) + R_world @ S.HAND["Right Arm"]
            d = S.unit(R_world @ grip_local)
            G = hand - d * spacing / 2
            key["grip"] = [round(float(v), 3) for v in G]
            key["dir"] = [round(float(v), 3) for v in d]
        if hands == 1:                                        # the arms as the animator keyed them; the blade rides the right
            for arm, name in (("Right Arm", "right_arm"), ("Left Arm", "left_arm")):
                if arm in arm_rot:
                    key[name + "_rot"] = [round(float(v), 1) for v in arm_rot[arm][i]]
                    key[name + "_off"] = [round(float(v), 3) for v in J[arm]["frames"][i][4:7]]
            key["arms"] = "keyed"
        key["ease"] = "Linear" if every <= 1 else "InOut"
        keys.append(key)
    return keys


def main(argv):
    if not argv or "--as" not in argv:
        return emit("fail", "keys_from: needs <reference clip.json> --as <Name> [--out <Name>.move.json]", "lune run kit anim keys ClaymoreWhirl2 --from RefFinisher")
    ref_path = argv[0]
    name = argv[argv.index("--as") + 1]
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join("assets", "animations", f"{name}.move.json")
    length = float(argv[argv.index("--length") + 1]) if "--length" in argv else 5.2
    spacing = float(argv[argv.index("--grip") + 1]) if "--grip" in argv else 0.8
    grip_pitch = float(argv[argv.index("--grip-pitch") + 1]) if "--grip-pitch" in argv else 20.0
    every = int(argv[argv.index("--every") + 1]) if "--every" in argv else 2
    hands = int(argv[argv.index("--hands") + 1]) if "--hands" in argv else 2
    with open(ref_path, encoding="utf-8") as fh:
        ref = json.load(fh)
    if ref.get("rig") != "R6" or "Torso" not in ref["joints"]:
        return emit("fail", f"keys_from: {ref_path} is not an R6 clip with a Torso", "import the reference as it is (kit anim import <file.rbxm> ...)")
    keys = keys_from(ref, length, spacing, grip_pitch, every, hands)
    move = {"name": name, "kind": "strike", "fps": int(ref.get("fps") or 30), "priority": ref.get("priority", "Action"),
            "loop": bool(ref.get("loop")), "lag": 0.03, "inertia": 0.05,
            "sword": {"length": length, "grip": spacing, "grip_pitch": grip_pitch}, "hands": hands,
            "feel": ref.get("feel") or {"hitstop": 0.05, "impact_frames": 1, "camera_shake": 0.3},
            "events": [e for e in (ref.get("events") or []) if str(e.get("name", "")).lower() == "hit"],
            "keys": keys, "gate": {"pop_deg": 60, "penetration": 0.5, "foot_slide": 1.0},
            "keys_from": {"reference": ref.get("name"), "file": ref_path, "keys": len(keys)},
            "note": f"technique keys read from the reference {ref.get('name')} (kit/anim/keys_from.py): the body is the animator's at its own turning frames; edit grip / dir for the weapon arc"}
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        json.dump(move, fh, indent=2)
        fh.write("\n")
    # how faithful: regenerate through strike.py and measure against the reference
    try:
        clip, info = S.generate(dict(move))
        cv_a, _ = M.curves(clip)
        cv_b, _ = M.curves(ref)
        dist = M.distance(cv_a, cv_b, loop=False)
    except Exception as e:  # noqa: BLE001
        return emit("pass", f"keys_from {name}: {len(keys)} keys from {ref.get('name')} -> {out} (strike.py could not regenerate it yet: {str(e)[:120]})",
                    f"edit {out}, then: lune run kit anim {name}", keys=len(keys))
    return emit("pass", f"keys_from {name}: {len(keys)} keys from {ref.get('name')} -> {out}; regenerated distance {dist['total']} ("
                + ", ".join(f"{p} {v['score']}" for p, v in dist["per_joint"].items()) + ")",
                f"lune run kit anim {name} && lune run kit anim look {name} --rig R6 (then edit grip / dir in {out})", keys=len(keys), distance=dist["total"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
