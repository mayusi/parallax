"""pose_from.py — a finished R6 clip -> an EDITABLE key-pose file on the owner's rig (assets/animations/<Name>.pose.json).

    python kit/anim/pose_from.py <reference clip.json> --as <Name> [--every N] [--despike] [--reduce <tol>] [--out <path>]

Why: an approved animation is the best starting point there is. This reads every joint of the reference and writes it
as what the rig's controllers do (kit/anim/pose_r6.py's vocabulary), FK legs as the rig ships:
- the torso joint -> body {pos, lean, turn, tilt}      (body_rot = Rz(−turn)·Rx(−lean)·Ry(tilt), decomposed exactly)
- each arm / leg joint -> {swing, out, twist, slide}    (limb_rot = Ry(±out)·Rx(swing)·Rz(twist), decomposed exactly)
- the head's WORLD facing -> head {look, tilt}         (the rig's head ignores the body's turn: the facing is kept)
Keys at every reference frame (--every N: every Nth, the ends kept). `kit anim <Name>` then rebuilds it on the rig;
`kit anim profile <Name> --vs <Ref>` should report no gaps. Edit from there: amplitudes, offsets, eases, timing.
--despike re-spaces the reference's SNAPS first (kit/anim/snaps.py: single frames that jump much further than their
neighbours; the path is kept, the jolt is spread). --reduce <tol> keeps per controller only the keys curve
simplification needs (kit/anim/keyreduce.py, tolerance in degrees): an editable file with the animator's structure.

WHAT THE CLIP SAYS RIDES ALONG (the owner's V3 list, anim stage C.2; card r66z: `kit anim derive` rebuilt its clip
from reduced body keys that carried no weapon and none of what the clip says, so a grip solve, a slide, a beat or a
Hit was thrown away there): the reference's events, beats, hands, slides, match, contact, target, upper and
on_blade are written into the pose file (the build copies them onto the baked clip); its WEAPON is written as the
pose file's sword - its blade length, grip spacing and kind, the grip "animated" (the weapon turns in the fist as a
Handle joint, kit/anim/grip.py) - and every key of the right arm says where the blade points and its edge faces at
that frame, with keys added where the blade turns in the fist (its own joint track reduced the same way).
NOT CARRIED: a weapon whose grip point leaves the fist (a toss: the pose route keeps the weapon in the fist unless a
key says "toss"); a second weapon (grip_left)."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import snaps as SN  # noqa: E402
import keyreduce as KR  # noqa: E402

P3 = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])   # Roblox -> Blender
LIMBS = {"Right Arm": "right_arm", "Left Arm": "left_arm", "Right Leg": "right_leg", "Left Leg": "left_leg"}
ON_LINE = 0.1        # studs from the weapon's line for the reference's left hand to be ON it (in_hand.py's LOOSE bar)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def stage_of(v):
    """Roblox character vector -> stage [right, up, forward]"""
    return [round(float(v[0]), 4), round(float(v[1]), 4), round(float(-v[2]), 4)]


def limb_params(R_rbx, side):
    """R = Ry(s·out)·Rx(swing)·Rz(twist) (Blender axes) -> degrees"""
    R = P3 @ R_rbx @ P3.T
    swing = math.asin(max(-1.0, min(1.0, -R[1, 2])))
    twist = math.atan2(R[1, 0], R[1, 1])
    a = math.atan2(R[0, 2], R[2, 2])
    s = 1.0 if side.startswith("Left") else -1.0
    return {"swing": round(math.degrees(swing), 2), "out": round(math.degrees(a) * s, 2), "twist": round(math.degrees(twist), 2)}


def body_params(R_rbx):
    """R = Rz(−turn)·Rx(−lean)·Ry(tilt) (Blender axes) -> degrees"""
    R = P3 @ R_rbx @ P3.T
    B = math.asin(max(-1.0, min(1.0, R[2, 1])))
    Cc = math.atan2(-R[2, 0], R[2, 2])
    A = math.atan2(-R[0, 1], R[1, 1])
    return {"lean": round(-math.degrees(B), 2), "turn": round(-math.degrees(A), 2), "tilt": round(math.degrees(Cc), 2)}


def head_params(R_world_rbx):
    R = P3 @ R_world_rbx @ P3.T
    d = R @ np.array([0, 1.0, 0])                       # the head's forward, Blender
    Cc = math.atan2(-R[2, 0], R[2, 2])                   # the tilt about its own forward
    return {"look": [round(float(d[0]), 4), round(float(d[2]), 4), round(float(d[1]), 4)], "tilt": round(math.degrees(Cc), 2)}


def source_gate(ref):
    """the gate this file is held to: the kit's defaults, except where the SOURCE itself needs more - then the
    tightest bar the source passes (+ a margin), noted. R6 legs never bend, so a finished R6 attack pivots and dips
    its stance; the gate then catches the transfer making it WORSE, not the source being what it is"""
    rig = C.load_rig("r6")
    loose = {"foot_slide": 99, "foot_skate": 99, "pop_deg": 999, "penetration": 99, "loop_seam_deg": 999,
             "hit_before": 999, "hit_after": 999}
    m = C.metrics(ref, rig, loose)
    gate, notes = {}, []
    slide = float((m.get("feet") or {}).get("slide_max_studs_frame") or 0.0)
    if slide > 0.1:
        gate["foot_slide"] = round(slide + 0.1, 2)
        notes.append(f"its planted foot moves {slide:.2f} studs in a frame")
    for key, ladder, word in (("penetration", (0.08, 0.15, 0.25, 0.4, 0.6, 0.8, 1.0, 1.5, 2.0), "parts dip below the floor"),
                              ("pop_deg", (60, 75, 90, 120, 150, 180), "a joint turns fast in a frame")):
        if not C.metrics(ref, rig, dict(loose, **{key: ladder[0]}))["problems"]:
            continue
        for v in ladder[1:]:
            if not C.metrics(ref, rig, dict(loose, **{key: v}))["problems"]:
                gate[key] = v
                notes.append(f"{word} (passes at {v})")
                break
    if not gate:
        return {}
    return {"gate": gate, "gate_note": f"measured from the source {ref.get('name')}: " + "; ".join(notes)}


CARRIED = ("events", "beats", "hands", "slides", "match", "contact", "target", "upper", "on_blade")


def weapon_of(ref):
    """the reference's weapon as the pose route's sword (None: it carries none, or its paths are not the clip's length)
    -> ({blade, spacing, grip: animated, kind?}, per frame (blade direction, edge or None) in stage axes)"""
    sw = ref.get("sword") if isinstance(ref.get("sword"), dict) else {}
    n = len(ref.get("times") or [])
    tips, grips = sw.get("tip"), sw.get("grip_path")
    if not (isinstance(tips, list) and isinstance(grips, list) and len(tips) == len(grips) == n and n):
        return None, None
    edges = sw.get("edge") if isinstance(sw.get("edge"), list) and len(sw["edge"]) == n else None
    spacing = sw.get("grip")
    spacing = float(spacing) if isinstance(spacing, (int, float)) and not isinstance(spacing, bool) and 0 < spacing <= 2 else 0.75
    length = float(np.median([np.linalg.norm(np.subtract(t, g)) for t, g in zip(tips, grips)]))
    # (pose_r6 puts the tip blade + 0.36 + spacing / 2 from the grip point: the blade the pose file says, back from the
    # reference's own grip-to-tip - its "length" is the whole weapon, 3.6 against 3.35 on the loved kesa)
    spec = {"blade": round(max(0.5, length - 0.36 - spacing / 2), 4), "spacing": round(spacing, 4), "grip": "animated"}
    if sw.get("kind"):
        spec["kind"] = sw["kind"]
    aim = []
    for i in range(n):
        d = np.subtract(tips[i], grips[i])
        d = d / max(float(np.linalg.norm(d)), 1e-9)
        aim.append((stage_of(d), stage_of(edges[i]) if edges else None))
    return spec, aim


def pose_from(ref, name, every=1, reduce=None):
    J = ref["joints"]
    times = ref["times"]
    n = len(times)
    idx = sorted(set(list(range(0, n, max(1, every))) + [n - 1]))
    sword, aim = weapon_of(ref)
    own = None
    if reduce:                                   # per joint: only the frames curve simplification keeps
        own = {j: set(v) for j, v in KR.reduce_clip(ref, float(reduce)).items()}
        if "Head" in J and "Torso" in J:         # the rig's head faces in the WORLD: reduce its world track
            world = [list(C.mat_quat(C.quat_mat(t[:4]) @ C.quat_mat(h[:4]))) + list(h[4:7])
                     for t, h in zip(J["Torso"]["frames"], J["Head"]["frames"])]
            own["Head"] = set(KR.reduce_track(world, float(reduce))) | own["Torso"]
        if sword and "Right Arm" in own:         # the blade turning in the fist keys the right arm too
            grip = ref.get("grip") if isinstance(ref.get("grip"), list) and len(ref["grip"]) == n else None
            if grip:
                own["Right Arm"] |= set(KR.reduce_track(grip, float(reduce)))
            # (a hand on the hilt: the hilt moves with the right arm and the blade - the left arm is keyed with them)
            if "Left Arm" in own:
                own["Left Arm"] |= own["Right Arm"]
        idx = sorted(set().union(*own.values()))
    # the left hand ON the weapon's line in the reference (within ON_LINE studs): the lock below says where along the
    # blade from the right fist ("left": d), and pose_r6 (its lock, held: below) puts the left hand there by the least turn
    # (and slide) of the arm its keys gave - its limb keys, interpolated apart from the right arm, left the hilt by up
    # to 0.044 studs between keys on the loved cuts (V4 4.4 / 13.4.2)
    on_line = {}
    if sword and "Left Arm" in J and "Right Arm" in J and ref.get("rig") == "R6":
        rig = C.load_rig("r6")
        sw = ref["sword"]
        for i, W in enumerate(C.world_frames(ref, rig)):
            g = np.array(sw["grip_path"][i], float)
            d = np.subtract(sw["tip"][i], g)
            d = d / max(float(np.linalg.norm(d)), 1e-9)
            hr = (W["Right Arm"] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]
            hl = (W["Left Arm"] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]
            if float(np.linalg.norm(hl - (g + float(np.dot(hl - g, d)) * d))) <= ON_LINE:
                on_line[i] = round(float(np.dot(hl - hr, d)), 4)
    keys = []
    for i in idx:
        k = {"f": round(float(times[i]) * 60.0, 3), "ease": "linear"}
        Rt = C.quat_mat(J["Torso"]["frames"][i][:4]) if "Torso" in J else np.eye(3)
        if "Torso" in J and (own is None or i in own.get("Torso", ())):
            k["body"] = {"pos": stage_of(J["Torso"]["frames"][i][4:7]), **body_params(Rt)}
        if "Head" in J and (own is None or i in own.get("Head", ())):
            k["head"] = head_params(Rt @ C.quat_mat(J["Head"]["frames"][i][:4]))
        for part, field in LIMBS.items():
            if part in J and (own is None or i in own.get(part, ())):
                f = J[part]["frames"][i]
                k[field] = {**limb_params(C.quat_mat(f[:4]), part), "slide": stage_of(f[4:7])}
                if part == "Right Arm" and aim:
                    k[field]["blade"] = aim[i][0]
                    if aim[i][1] is not None:
                        k[field]["edge"] = aim[i][1]
        keys.append(k)
    if sword and aim:
        # THE WRIST-PLANE LOCK (V4 4.4 / 13.4.2): the blade and its edge at EVERY reference frame, so the bake keys
        # the weapon's turn in the fist frame by frame (pose_r6.lock_grip) - keyed only where the right arm is, the
        # kesa's blade left its source by up to 15.6 degrees between keys and its left hand 0.14 studs off the hilt.
        # (The bake's half, pose_r6.lock_grip, measured 0.006 deg / 0.0001 studs on three loved cuts, is HELD: a change
        # to pose_r6.py re-stales all 213 pose-route clips by its tool sha - the owner's call when to re-bake them.
        # Until then pose_r6 reads no "lock" and the pose file bakes as before)
        sword = dict(sword, lock=[{"f": round(float(times[i]) * 60.0, 3), "blade": aim[i][0],
                                   **({"edge": aim[i][1]} if aim[i][1] is not None else {}),
                                   **({"left": on_line[i]} if i in on_line else {})} for i in range(n)])
    return {"name": name, "axes": "stage: x right, y up from the floor, z forward (root-relative)", "fps": 60,
            "loop": bool(ref.get("loop")), "priority": ref.get("priority", "Movement"), "legs": "fk",
            "pose_from": {"reference": ref.get("name"), "keys": len(keys), "reduce": reduce},
            **source_gate(ref),
            "note": f"the finished R6 clip {ref.get('name')} on the owner's rig as editable key poses (kit/anim/pose_from.py): FK legs, limb swings + slides, body and head - edit amplitudes, offsets, eases and timing from here",
            **({"sword": sword} if sword else {}),
            **{k: ref[k] for k in CARRIED if ref.get(k) is not None},
            "keys": keys}


def main(argv):
    if not argv or "--as" not in argv:
        return emit("fail", "pose_from: needs <reference clip.json> --as <Name>", "lune run kit anim pose-from <Ref> --as <Name>")
    with open(argv[0], encoding="utf-8") as fh:
        ref = json.load(fh)
    if ref.get("rig") != "R6":
        return emit("fail", f"pose_from: {argv[0]} is not an R6 clip", "import the reference as R6 first")
    name = argv[argv.index("--as") + 1]
    every = int(argv[argv.index("--every") + 1]) if "--every" in argv else 1
    despiked = {}
    if "--despike" in argv:
        ref, despiked = SN.fix(ref)
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join("assets", "animations", f"{name}.pose.json")
    reduce = float(argv[argv.index("--reduce") + 1]) if "--reduce" in argv else None
    spec = pose_from(ref, name, every, reduce)
    if despiked:
        spec["pose_from"]["despiked"] = despiked
    with open(out, "w", encoding="utf-8", newline="") as fh:
        json.dump(spec, fh, indent=1)
        fh.write("\n")
    return emit("pass", f"pose_from {name}: {len(spec['keys'])} key poses from {ref.get('name')} -> {out}",
                f"lune run kit anim {name} && lune run kit anim profile {name} --vs {ref.get('name')}", keys=len(spec["keys"]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
