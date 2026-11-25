"""shape_ref.py — the BODY SHAPE of a combat clip, measured the way the loved 10-18 greatsword recipe was found (owner
2026-11-04: both round-0 sets 'All bad' - stilts, arm-only swings, a slow upright spin with a flopping blade). The
numbers a dossier checks so a stilt or arm-only candidate FAILS a gate instead of reaching the owner:
    crouch_max_studs       how far the torso sinks under rest at its lowest (loved Hq pack / GsCombo: 0.3-0.6)
    crouch_hold_share      the share of the clip spent at least half that low (a crouch HELD, not a dip)
    leg_slide_in_max       how far a rigid leg's top slides INTO the torso (R6's bent knee), the deeper leg
    lean_fwd_max_deg       the torso's forward lean at its most
    hand_sweep_studs       the main hand's path in the TORSO frame: the widest distance between two of its points
                           (loved slashes 4.5-5.5: high and wide one side -> low the other; an arm-only swing ~2)
    hand_drop_studs        that hand's height range in the torso frame (high -> low)
    finish_hold_s          the held finish: the longest stretch after the Hit with the main hand < 2 studs/s (torso frame)
    spin_turns_per_s       the body's fastest sustained turn (0.25 s windows) in turns per second
    spin_turns             the body's whole turn over the clip (turns)
    blade_plane_dev_deg    over the spin (frames turning at >= half the peak rate), the blade's worst angle off ONE
                           plane fitted to it (a flat disc ~0; a blade that flops to the floor / behind the head: big)
    blade_plane_tilt_deg   that plane's tilt off level (0 = a flat disc round the body)
    blade_reach_studs      the grip's mean horizontal distance from the torso centre over the spin (arm's length ~2)
    python kit/anim/shape_ref.py <clip.json | library id> ...   -> one JSON row per clip"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SHAPE_MEASURES = ("crouch_max_studs", "crouch_hold_share", "leg_slide_in_max", "lean_fwd_max_deg", "hand_sweep_studs",
                  "hand_drop_studs", "finish_hold_s", "spin_turns_per_s", "spin_turns", "blade_plane_dev_deg",
                  "blade_plane_tilt_deg", "blade_reach_studs")
HOLD_SPEED = 2.0          # studs/s: a hand slower than this in the torso frame is holding


def _yaw(M):
    f = M[:3, :3] @ np.array([0.0, 0.0, -1.0])
    return math.atan2(-f[0], -f[2])


def measure(c, main="Right Arm"):
    import clip as C
    rig = C.load_rig("R6")
    W = C.world_frames(c, rig)
    n = len(W)
    fps = float(c.get("fps", 60))
    drop, lean, slide, hand, yaw = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros((n, 3)), np.zeros(n)
    for i, fr in enumerate(W):
        T = fr["Torso"]
        up = T[:3, :3] @ np.array([0.0, 1.0, 0.0])
        lean[i] = math.degrees(math.atan2(-up[2], up[1]))
        # the sink is the torso's height under rest (3 over the floor); a clip with a root track carries it there
        drop[i] = -float(T[1, 3])
        s = []
        for part, hx in (("Right Leg", 0.5), ("Left Leg", -0.5)):
            top = (fr[part] @ np.array([0.0, 1.0, 0.0, 1.0]))[:3]
            hip = (T @ np.array([hx, -1.0, 0.0, 1.0]))[:3]
            s.append(float((top - hip) @ up))
        slide[i] = max(s)
        h = (fr[main] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]
        hand[i] = (np.linalg.inv(T) @ np.r_[h, 1.0])[:3]
        yaw[i] = _yaw(T)
    yaw = np.unwrap(yaw)
    out = {}
    out["crouch_max_studs"] = float(drop.max())
    out["crouch_hold_share"] = float(np.mean(drop >= 0.5 * drop.max())) if drop.max() > 0.05 else 0.0
    out["leg_slide_in_max"] = float(slide.max())
    out["lean_fwd_max_deg"] = float(lean.max())
    sub = hand[:: max(1, n // 120)]
    out["hand_sweep_studs"] = float(max(np.linalg.norm(sub[:, None] - sub[None], axis=2).max(), 0.0))
    out["hand_drop_studs"] = float(hand[:, 1].max() - hand[:, 1].min())
    # the held FINISH: the longest run of frames after the Hit (no Hit: the whole clip) with the hand holding - the
    # clip may recover to its idle after it, so the run is not only the last one
    sp = np.r_[np.linalg.norm(np.diff(hand, axis=0), axis=1) * fps, 0.0]
    hit = next((float(e["t"]) for e in c.get("events", []) if e.get("name") == "Hit"), 0.0)
    best = run = 0
    for v in sp[int(round(hit * fps)):]:
        run = run + 1 if v < HOLD_SPEED else 0
        best = max(best, run)
    out["finish_hold_s"] = float(best / fps)
    w = max(1, int(round(0.25 * fps)))
    rate = np.abs(yaw[w:] - yaw[:-w]) / (w / fps) / (2 * math.pi) if n > w else np.zeros(1)
    out["spin_turns_per_s"] = float(rate.max()) if len(rate) else 0.0
    out["spin_turns"] = float(abs(yaw[-1] - yaw[0]) / (2 * math.pi))
    sw = c.get("sword") or {}
    tip, grip = sw.get("tip"), sw.get("grip_path")
    out.update(blade_plane_dev_deg=float("nan"), blade_plane_tilt_deg=float("nan"), blade_reach_studs=float("nan"))
    if tip and grip and len(tip) >= n and len(rate) and rate.max() > 0.3:
        # the sword tracks are ROOT-local: compose the root in (clip.world_frames does for the body)
        root = c.get("root")
        dirs, reach = [], []
        # the SPIN's frames: turning at >= half the peak rate over a short CENTRED window (a forward window counted the
        # entry's last 0.25 s, the blade still swinging out, as spin)
        h = max(1, int(round(0.05 * fps)))
        inst = np.array([abs(yaw[min(n - 1, i + h)] - yaw[max(0, i - h)]) / ((min(n - 1, i + h) - max(0, i - h)) / fps)
                         / (2 * math.pi) for i in range(n)])
        # the longest run of them (a one-frame pop at the stop turning faster than the spin is not the spin), less
        # its first / last 3 frames (the blade swinging out / whipping down there)
        ok = (inst >= 0.5 * rate.max()) & (inst <= 2.0 * rate.max())
        runs, i0 = [], None
        for i, v in enumerate(list(ok) + [False]):
            if v and i0 is None:
                i0 = i
            elif not v and i0 is not None:
                runs.append((i0, i))
                i0 = None
        a, b = max(runs, key=lambda r: r[1] - r[0]) if runs else (0, 0)
        spin = np.arange(a + 3, b - 3) if b - a > 8 else np.arange(a, b)
        for i in spin:
            g, t = np.asarray(grip[i], float), np.asarray(tip[i], float)
            if isinstance(root, list) and i < len(root):
                R, o = C.quat_mat(root[i][:4]), np.asarray(root[i][4:7], float)
                g, t = R @ g + o, R @ t + o
            b = t - g
            dirs.append(b / max(np.linalg.norm(b), 1e-9))
            ctr = W[i]["Torso"][:3, 3]
            reach.append(float(np.linalg.norm((g - ctr)[[0, 2]])))
        D = np.array(dirs)
        # the plane through the origin best holding every blade direction: its normal is the least singular vector
        nrm = np.linalg.svd(D, full_matrices=False)[2][-1]
        out["blade_plane_dev_deg"] = float(np.degrees(np.arcsin(np.clip(np.abs(D @ nrm), 0, 1))).max())
        out["blade_plane_tilt_deg"] = float(np.degrees(np.arccos(min(1.0, abs(float(nrm[1]))))))
        out["blade_reach_studs"] = float(np.mean(reach))
    return {k: round(v, 3) if v == v else v for k, v in out.items()}


def load_any(a):
    if os.path.exists(a):
        return json.load(open(a, encoding="utf-8"))
    sys.path.insert(0, os.path.join(HERE, "..", "..", "diagnostics"))
    import translate_test as TT
    return TT.loved_clip(a)[0]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for a in sys.argv[1:]:
        print(json.dumps({"clip": a, **measure(load_any(a))}))
