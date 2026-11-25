"""pose_bank.py — the POSE BANK: the key poses of every animation the owner LOVED, so new moves are INVENTED from what
loved R6 animators actually do (owner 2026-10-12: "invent the poses by learning from the catalog ... what about the
footwork"), never from hand-made geometry (the from-scratch greatsword was rated 3/10 twice).

    python kit/anim/pose_bank.py build      -> _artifacts/r6lib/pose_bank.json (from assets/animations/library/owner_picks.json)
    python kit/anim/pose_bank.py stats

Per loved, not-laggy, non-dance clip: its PHASE poses - guard (frame 0), wind-up (the speed pause before the strike
that is farthest from the guard), strike (the fastest arm frame), follow (the first pause after the strike), end - each
with every R6 joint's frame (so a pose can be reused exactly) and DESCRIPTORS to search by:
  turn / lean / roll (deg, the torso vs the clip's own guard), hip (the torso's height change), hands_local (each arm's
  end in the torso's frame: x right, y up, -z forward - Roblox axes), hands_gap, feet (each leg's end vs the root, xz),
  width (stance), plus the clip's timing (phase times) and kind.
Measured from the library 2026-10-12: 111 of 117 loved combat clips STEP (median 2.5 studs, lift 1.6, stance 1.0 -> 3.0
studs wide, hip drop 0.9): loved R6 footwork is big."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402

LIB = os.path.join("_artifacts", "r6lib")
BANK = os.path.join(LIB, "pose_bank.json")
PICKS = os.path.join("assets", "animations", "library", "owner_picks.json")
ARM_END = np.array([0.0, -1.0, 0.0])


def yaw_pitch_roll(m):
    """the torso's heading (deg, + = turned to its right), forward lean (+ = bent forward) and roll"""
    R = np.asarray(m)[:3, :3]
    f = R @ np.array([0.0, 0.0, -1.0])
    up = R @ np.array([0.0, 1.0, 0.0])
    yaw = math.degrees(math.atan2(-f[0], -f[2]))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, -f[1]))))
    right = R @ np.array([1.0, 0.0, 0.0])
    roll = math.degrees(math.asin(max(-1.0, min(1.0, -right[1]))))
    return -yaw, pitch, roll


def end_of(w, part):
    m = np.asarray(w[part])
    return m[:3, :3] @ ARM_END + m[:3, 3]


def phases(c, rig):
    W = C.world_frames(c, rig)
    fps = float(c.get("fps") or 30)
    arms = [p for p in ("Right Arm", "Left Arm") if p in W[0]]
    if not arms or len(W) < 4:
        return None, None
    P = np.array([[end_of(w, p) for p in arms] for w in W])          # frames x arms x 3
    s = np.linalg.norm(np.diff(P, axis=0), axis=2).max(axis=1) * fps  # the fastest arm's speed per frame step
    k = int(np.argmax(s))
    g = P[0]
    pause = [i for i in range(1, len(s) - 1) if s[i] <= s[i - 1] and s[i] <= s[i + 1]]
    before = [i for i in pause if i < k] or [max(0, k - 3)]
    wind = max(before, key=lambda i: float(np.linalg.norm(P[i] - g)))
    after = [i for i in pause if i > k] or [min(len(W) - 1, k + 3)]
    follow = after[0]
    return W, {"guard": 0, "wind": wind, "strike": k + 1, "follow": follow, "end": len(W) - 1}


def describe(c, W, i, rig):
    w, w0 = W[i], W[0]
    t, t0 = np.asarray(w["Torso"]), np.asarray(w0["Torso"])
    y, p, r = yaw_pitch_roll(t)
    y0, p0, r0 = yaw_pitch_roll(t0)
    Rt = t[:3, :3]
    d = {"turn": round((y - y0 + 180) % 360 - 180, 1), "lean": round(p, 1), "roll": round(r, 1),
         "hip": round(float(t[1, 3] - t0[1, 3]), 3)}
    hl = {}
    for p_ in ("Right Arm", "Left Arm"):
        if p_ in w:
            hl[p_] = [round(float(v), 3) for v in Rt.T @ (end_of(w, p_) - t[:3, 3])]
    d["hands_local"] = hl
    if len(hl) == 2:
        d["hands_gap"] = round(float(np.linalg.norm(np.array(hl["Right Arm"]) - np.array(hl["Left Arm"]))), 3)
    feet = {}
    for p_ in ("Right Leg", "Left Leg"):
        if p_ in w:
            e = end_of(w, p_)
            feet[p_] = [round(float(e[0]), 3), round(float(e[1]), 3), round(float(e[2]), 3)]
    d["feet"] = feet
    d["dirs"] = {p_: [round(float(v), 4) for v in Rt.T @ (np.asarray(w[p_])[:3, :3] @ ARM_END)]
                 for p_ in ("Right Arm", "Left Arm", "Right Leg", "Left Leg") if p_ in w}      # each limb's direction, torso frame
    if len(feet) == 2:
        a, b = np.array(feet["Right Leg"]), np.array(feet["Left Leg"])
        d["width"] = round(float(np.linalg.norm((a - b)[[0, 2]])), 3)
    d["joints"] = {j: [round(float(v), 5) for v in c["joints"][j]["frames"][i]] for j in c["joints"]}
    return d


def build():
    rig = C.load_rig("r6")
    picks = json.load(open(PICKS, encoding="utf-8"))["picks"]
    bank, n = [], 0
    for r in picks:
        if r["verdict"] != "love" or r["laggy"] or r["kind"] == "dance":
            continue
        path = os.path.join(LIB, "clips", f"{r['id']}.clip.json")
        if not os.path.isfile(path):
            continue
        c = json.load(open(path, encoding="utf-8"))
        W, ph = phases(c, rig)
        if not ph:
            continue
        n += 1
        fps = float(c.get("fps") or 30)
        for name, i in ph.items():
            e = describe(c, W, i, rig)
            e.update({"clip": r["id"], "name": r["name"], "pack": r["pack"], "kind": r["kind"], "phase": name, "frame": i,
                      "t": round(i / fps, 4), "duration": round(float(c["times"][-1]), 4),
                      "has_legs": "Right Leg" in c["joints"] and "Left Leg" in c["joints"]})
            bank.append(e)
    os.makedirs(LIB, exist_ok=True)
    json.dump({"clips": n, "poses": bank}, open(BANK, "w", encoding="utf-8"))
    return n, bank


def load():
    return json.load(open(BANK, encoding="utf-8"))["poses"]


def main(argv):
    if argv and argv[0] == "build":
        n, bank = build()
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"pose bank: {len(bank)} poses from {n} loved clips -> {BANK}",
                          "next_action": "python kit/anim/pose_bank.py stats"}))
        return 0
    bank = load()
    from collections import Counter
    print("poses", len(bank), "by phase", dict(Counter(e["phase"] for e in bank)), "by kind", dict(Counter(e["kind"] for e in bank)))
    for ph in ("wind", "strike", "follow"):
        sel = [e for e in bank if e["phase"] == ph]
        print(f"  {ph}: turn median {np.median([abs(e['turn']) for e in sel]):.0f} deg, lean {np.median([e['lean'] for e in sel]):.0f}, "
              f"hip {np.median([e['hip'] for e in sel]):.2f}, width {np.median([e.get('width', 0) for e in sel if e.get('width')]):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
