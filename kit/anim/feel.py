"""feel.py — the FEEL pass: what separates a finished attack from a correct one. Retimes and sharpens any R6 clip.

    python kit/anim/feel.py <Name>.feel.json --out <clip.json>

The spec: {"name": "ClaymoreHit1Feel", "from": "ClaymoreHit1", "hits": "auto" | [t, ...],
           "anticipation": 1.5, "snap": 0.5, "hitstop": 3, "overshoot": 0.18, "settle": 4,
           "recovery": 1.15, "lag": {"Head": 1}, "gate": {...}}

What it does to the clip around EVERY hit (the clip's Hit events, or the blade's / hands' speed peaks when
"hits" is "auto"):
- anticipation: the 0.2 s before the wind-up's end run `anticipation` times slower (a hold the eye reads as intent);
- snap: the frames from the wind-up's end into the hit run `snap` times faster (two frames of smear, not six of
  travel);
- hitstop: the hit pose is held `hitstop` extra frames IN THE CLIP (the impact freeze; the runtime may add more);
- overshoot: right after the hold the pose keeps going past the hit by `overshoot` of the last step, then settles
  back over `settle` frames (follow-through - the weight of the swing);
- recovery: everything after that runs `recovery` times slower (the slow return every finished attack has);
- lag: named joints trail the body by N frames (the head and the off hand arrive late: secondary motion).
Measured on finished R6 attacks (kit lesson 2026-10-11): action 0.07-0.27 s, recovery over half the clip, torso
1100-3300 deg/s at the hit - these parameters put a clip there."""
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


def frame_at(frames, times, t):
    """[qx,qy,qz,qw,x,y,z] at time t (slerp / lerp between frames)"""
    if t <= times[0]:
        return list(frames[0])
    if t >= times[-1]:
        return list(frames[-1])
    k = int(np.searchsorted(np.array(times), t, side="right") - 1)
    k = max(0, min(k, len(frames) - 2))
    a, b = frames[k], frames[k + 1]
    u = (t - times[k]) / max(times[k + 1] - times[k], 1e-9)
    q = C.slerp(a[:4], b[:4], u)
    pos = [a[4 + j] + (b[4 + j] - a[4 + j]) * u for j in range(3)]
    return [float(v) for v in q] + pos


def hit_times(clip, rig, spec):
    hits = spec.get("hits", "auto")
    if isinstance(hits, list):
        return [float(t) for t in hits]
    evs = [float(e["t"]) for e in (clip.get("events") or []) if str(e.get("name", "")).lower() in C.HIT_NAMES]
    if evs:
        return evs
    m = C.metrics(clip, rig, {"foot_slide": 99, "foot_skate": 99, "pop_deg": 999, "penetration": 99, "loop_seam_deg": 999, "hit_before": 999, "hit_after": 999})
    fastest = m.get("fastest")
    if not fastest:
        return []
    return [float(m["effectors"][fastest]["peak_t"])]


MAX_SNAP_DEG = 110.0     # the most the torso may turn in the one snapped frame (finished R6 attacks: 40-110 deg)


def snap_per_hit(src, times, hits, fps, snap):
    """the snap factor per hit, widened where the source already turns the torso fast: one output frame never
    carries more than MAX_SNAP_DEG of torso turn (a spinning combo snapped at 0.55 made a 174 deg frame)"""
    out = {}
    tor = src["joints"].get("Torso", {}).get("frames") or []
    for h in hits:
        need = snap
        if tor:
            a = frame_at(tor, times, max(times[0], h - 0.08))
            b = frame_at(tor, times, h)
            d = abs(float(np.dot(np.array(a[:4]), np.array(b[:4]))))
            turn = 2.0 * np.degrees(np.arccos(min(1.0, d)))          # degrees the torso turns through the snap window
            frames_needed = max(1.0, turn / MAX_SNAP_DEG)             # output frames that turn needs
            need = frames_needed / (0.08 * fps)                      # as a snap factor over the 0.08 s window
        out[h] = float(min(1.0, max(snap, need)))
    return out


def warp(times, hits, fps, anticipation, snap, hitstop, recovery):
    """source time -> output time: a piecewise speed map around every hit; returns the output sample times and,
    for each, the source time it shows (holds repeat a source time). `snap` may be one factor or {hit: factor}"""
    dt = 1.0 / fps
    T = times[-1]
    snaps = snap if isinstance(snap, dict) else {h: snap for h in hits}
    # the speed of the source clock per output second, per source time
    def speed(t):
        for h in hits:
            if h - 0.25 <= t < h - 0.08:
                return 1.0 / anticipation            # slow before the strike
            if h - 0.08 <= t < h:
                return 1.0 / snaps.get(h, 0.55)      # fast INTO the strike (snap < 1 means FASTER)
            if h <= t < h + 0.45:
                return 1.0 / recovery                # the slow return
        return 1.0
    samples, src = [], 0.0
    while src < T - 1e-9:
        samples.append(src)
        step = dt * speed(src)
        nxt = src + step
        # the hold: when a step crosses a hit, land exactly on the hit and repeat it `hitstop` frames
        for h in hits:
            if src < h <= nxt:
                if h - src < 0.4 * step:             # the snap lands ON the hit: no near-duplicate frame before the hold
                    samples.pop()
                samples.append(h)
                samples.extend([h] * int(hitstop))
                nxt = h + dt / max(recovery, 1e-6)
                break
        src = nxt
    samples.append(T)
    out_times = [round(i * dt, 6) for i in range(len(samples))]
    return out_times, samples


def _arm_frames(clip, rig, part):
    """the arm's 4x4 at every frame, character space WITHOUT the root (the space the sword's paths are in: grip.py),
    or None when the clip cannot be read on this rig"""
    try:
        return [C.fk(rig, C.character_transforms(clip, rig, i))[part] for i in range(len(clip["times"]))]
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def _segment(times, s_t):
    """the source frame a source time falls after, and how far to the next (0..1)"""
    k = max(0, min(int(np.searchsorted(times, s_t, side="right")) - 1, len(times) - 2))
    return k, float(np.clip((s_t - times[k]) / max(times[k + 1] - times[k], 1e-9), 0.0, 1.0))


def retime_sword(src, clip, rig, src_samples):
    """the weapon's per-frame tracks (tip, grip_path, edge: points / a direction; grip_rot: a rotation) at the retimed
    clip's frames, CARRIED BY THE HAND that holds it. In the game the weapon rides the arm on its own joint (grip.py:
    Handle, Part0 = Right Arm), so between two source frames it is where the arm takes it, and through the overshoot
    it goes past the hit with the arm. Resampled on their own in character space (a straight line between two
    frames, no overshoot) the blade left the hand wherever the arm swings an arc between source frames or overshoots:
    ClaymoreComboBwFeel 0.62 studs off in the snap and the overshoot -> 0.00 (2026-11-19), while its source holds it
    at 0.00 at every frame. A SECOND hand on the weapon is not carried here: seat_off_hand puts it back after the
    retime (GreatswordSlash1Feel's left hand 0.99 -> 0.72 studs off here, 0.00 after it)"""
    times = list(src["times"])
    n = len(times)
    sw = dict(src["sword"])
    part = "Left Arm" if src.get("hands") == "left" else "Right Arm"
    A = _arm_frames(src, rig, part) if n > 1 else None
    B = _arm_frames(clip, rig, part) if A is not None else None
    if B is not None and len(B) != len(src_samples):
        B = None
    for name in ("tip", "grip_path", "edge"):
        if not (sw.get(name) and len(sw[name]) == n):
            continue
        pts = np.array(sw[name], dtype=float)
        if B is None:                                      # (no arm to carry it: resampled where it is)
            sw[name] = [[round(float(v), 4) for v in np.array([np.interp(s_t, times, pts[:, i]) for i in range(3)])] for s_t in src_samples]
            continue
        edge = name == "edge"                              # (a direction: turned with the arm, never moved)
        local = [A[i][:3, :3].T @ pts[i] if edge else A[i][:3, :3].T @ (pts[i] - A[i][:3, 3]) for i in range(n)]
        out = []
        for j, s_t in enumerate(src_samples):
            k, u = _segment(times, s_t)
            lp = local[k] + (local[k + 1] - local[k]) * u
            w = B[j][:3, :3] @ lp + (0.0 if edge else B[j][:3, 3])
            out.append([round(float(v), 4) for v in w])
        sw[name] = out
    # the weapon's per-frame rotation too: left at the source's frame count it no longer matched the times (it is
    # already the arm's own - pose_r6.py writes it relative to the Right Arm - so it is slerped as it is)
    if sw.get("grip_rot") and len(sw["grip_rot"]) == n:
        qs = sw["grip_rot"]
        out_q = []
        for s_t in src_samples:
            k, u = _segment(times, s_t)
            out_q.append([round(float(v), 6) for v in C.slerp(qs[k], qs[k + 1], u)])
        sw["grip_rot"] = out_q
    return sw


SEATED = 1e-3        # studs: an off hand this near its place on the hilt is on it (its frame is left as it was)


def seat_off_hand(clip, rig):
    """a TWO-HANDED clip's off hand put back on the hilt after the retime (in place) -> [[frame, studs along the line
    from the grip point]] for every frame moved. The overshoot's settle blends each arm on its own, so two hands on
    one hilt came apart where the source turns its arms fast (GreatswordSlash1Feel: 40-68 degrees a source frame at
    the hit, the left hand 0.72 studs off over the four settle frames). The weapon keeps the path the retime gave it
    (carried by the Right Arm) and the Right Arm is not touched: only the Left Arm turns, by kit/anim/rearm.py's own
    arm IK (strike.arm_rotation) with its facing held where the arm had it (twist 0: no roll of the block). Its place:
    the source's grip spacing behind the grip point (rearm: G - d * spacing / 2) when the arm reaches it; an R6 arm
    is one block of fixed reach, so where the shoulder is nearer the hilt than that, the hand takes the point of the
    hilt the arm reaches that is nearest its place (from the pommel end, in_hand.BEHIND behind the grip point, to
    grip_solve.APART behind the right hand). A frame whose hilt is out of the arm's reach is moved only when that
    brings the hand nearer the weapon (rearm's IK does not slide an arm): what is left there is the in-hand gate's to
    say. Each moved frame: [frame, studs along the line, studs off it after]. A clip whose hands are not "two" is
    returned untouched"""
    import grip_solve as GS
    import in_hand as IH
    try:
        said = IH.hands_of(clip)
    except ValueError:
        return []
    sw = clip.get("sword") if isinstance(clip.get("sword"), dict) else {}
    J = clip.get("joints") or {}
    n = len(clip.get("times") or [])
    spacing = sw.get("grip")
    if (said != "two" or not isinstance(spacing, (int, float)) or isinstance(spacing, bool) or not 0 < spacing <= 2
            or any(not isinstance(sw.get(k), list) or len(sw[k]) != n for k in ("grip_path", "tip"))
            or any(len((J.get(p) or {}).get("frames") or []) != n for p in ("Torso", "Right Arm", "Left Arm"))):
        return []
    h0 = S.unit(S.HAND["Left Arm"])
    x0 = S.unit(np.array([1.0, 0.0, 0.0]) - h0[0] * h0)       # (the arm block's facing at rest: strike.arm_rotation's)
    frames = [list(f) for f in J["Left Arm"]["frames"]]
    moved = []
    for i in range(n):
        tor = J["Torso"]["frames"][i]
        tm, tp = C.quat_mat(tor[:4]), np.array(tor[4:7], dtype=float)
        f = frames[i]
        slide = np.array(f[4:7], dtype=float)
        piv = tp + tm @ (S.SHOULDER["Left Arm"] + slide)
        Rw = tm @ C.quat_mat(f[:4])
        hand = piv + Rw @ S.HAND["Left Arm"]
        G = np.array(sw["grip_path"][i], dtype=float)
        d = S.unit(np.array(sw["tip"][i], dtype=float) - G)
        place = -float(spacing) / 2
        if float(np.linalg.norm(hand - (G + d * place))) < SEATED:
            continue
        ra = J["Right Arm"]["frames"][i]
        right = float(np.dot(tp + tm @ (S.SHOULDER["Right Arm"] + np.array(ra[4:7], dtype=float))
                             + tm @ C.quat_mat(ra[:4]) @ S.HAND["Right Arm"] - G, d))
        s0 = float(np.dot(piv - G, d))
        perp2 = float(np.sum((piv - (G + s0 * d)) ** 2))
        if abs(float(np.linalg.norm(G + d * place - piv)) - S.REACH) > SEATED and perp2 < S.REACH ** 2:
            r = math.sqrt(S.REACH ** 2 - perp2)
            on = [s for s in (s0 - r, s0 + r) if -IH.BEHIND <= s <= right - GS.APART]
            if on:
                place = min(on, key=lambda s: abs(s - place))
        R, _ = S.arm_rotation("Left Arm", G + d * place, tm, tp + tm @ slide, d, Rw @ x0, twist_rate=0.0)
        q = np.array(C.mat_quat(R), dtype=float)
        q = -q if float(np.dot(q, f[:4])) < 0 else q            # (the same side of the sphere as the frame it replaces)
        new = [round(float(v), 6) for v in q] + [round(float(v), 5) for v in slide]
        length = float(np.linalg.norm(np.array(sw["tip"][i], dtype=float) - G))

        def off(h):                                              # (in_hand's reading: studs from the weapon's line)
            return float(np.linalg.norm(h - (G + float(np.clip(np.dot(h - G, d), -IH.BEHIND, length)) * d)))
        now = off(piv + tm @ C.quat_mat(new[:4]) @ S.HAND["Left Arm"])
        if now >= off(hand) - 1e-6:
            continue                                             # (out of the arm's reach: pointing at it is no nearer)
        frames[i] = new
        moved.append([i, round(place, 3), round(now, 3)])
    if moved:
        J["Left Arm"] = dict(J["Left Arm"], frames=frames)
    return moved


def apply(src, spec, rig):
    fps = int(src.get("fps") or 30)
    dt = 1.0 / fps
    times = list(src["times"])
    hits = [h for h in hit_times(src, rig, spec) if 0.0 < h < times[-1]]
    anticipation = float(spec.get("anticipation", 1.5))
    snap = float(spec.get("snap", 0.55))
    hitstop = int(spec.get("hitstop", 3))
    recovery = float(spec.get("recovery", 1.15))
    overshoot = float(spec.get("overshoot", 0.18))
    settle = int(spec.get("settle", 4))
    lag = {k: int(v) for k, v in (spec.get("lag") or {"Head": 1}).items()}
    snaps = snap_per_hit(src, times, hits, fps, snap)
    out_times, src_samples = warp(times, hits, fps, anticipation, snaps, hitstop, recovery)
    J = src["joints"]
    joints = {}
    for part, j in J.items():
        if not j.get("frames"):
            continue
        fr = j["frames"]
        lagged = lag.get(part, 0)
        new = []
        for k, s_t in enumerate(src_samples):
            t = s_t - lagged * dt
            new.append(frame_at(fr, times, max(times[0], t)))
        joints[part] = {"frames": new}
    # overshoot: right after each hit's hold, push the pose past the hit by `overshoot` of the last source step,
    # then settle back over `settle` frames
    hit_out = []
    for h in hits:
        idx = [k for k, s_t in enumerate(src_samples) if abs(s_t - h) < 1e-9]
        if not idx:
            continue
        last = idx[-1]
        hit_out.append(out_times[idx[0]])
        if last + 1 >= len(src_samples):
            continue
        for part, j in joints.items():
            fr = j["frames"]
            before = frame_at(J[part]["frames"], times, max(times[0], h - dt))
            at = frame_at(J[part]["frames"], times, h)
            # the step into the hit, continued: rotation by the same delta again, position the same way
            q_before, q_at = np.array(before[:4]), np.array(at[:4])
            step_q = C.slerp(q_before, q_at, 1.0 + overshoot)
            step_p = [at[4 + i] + (at[4 + i] - before[4 + i]) * overshoot for i in range(3)]
            over = [float(v) for v in step_q] + step_p
            for s_ in range(1, settle + 1):
                k = last + s_
                if k >= len(fr):
                    break
                w = 1.0 - s_ / (settle + 1)                    # fades the overshoot into the retimed clip
                fr[k] = [float(v) for v in C.slerp(fr[k][:4], over[:4], w)] + [fr[k][4 + i] + (over[4 + i] - fr[k][4 + i]) * w for i in range(3)]
    clip = {k: v for k, v in src.items() if k not in ("source", "joints", "times", "events", "sword", "keys", "root", "fitted_to", "params", "style",
                                               "finish", "finished", "finish_log")}
    clip["name"] = spec["name"]
    clip["joints"] = joints
    clip["times"] = out_times
    clip["duration"] = out_times[-1]
    # every other marker (a gun's Shot / CoinToss / MagIn ...) moves with the retime: kept at its source time it fired
    # at the wrong moment of the new clip
    def remap(t):
        k = int(np.argmin([abs(s_t - t) for s_t in src_samples]))
        return out_times[k]
    clip["events"] = [{"name": "Hit", "t": round(t, 6)} for t in hit_out] + [
        dict(e, t=round(remap(float(e["t"])), 6)) for e in (src.get("events") or []) if str(e.get("name", "")).lower() not in C.HIT_NAMES]
    # the WEAPON's own track (a pose clip's animated grip: one frame per source frame, like a joint) is retimed with the
    # arms - copied through unchanged it drifted out of the hand (Sample Game, 2026-10-26)
    if isinstance(src.get("grip"), list) and len(src["grip"]) == len(times):
        clip["grip"] = [frame_at(src["grip"], times, s_t) for s_t in src_samples]
    if isinstance(src.get("grip_left"), list) and len(src["grip_left"]) == len(times):   # (the left hand's gun: Onyx)
        clip["grip_left"] = [frame_at(src["grip_left"], times, s_t) for s_t in src_samples]
    for key in ("sword", "root"):
        if key in src and isinstance(src[key], dict) and key == "sword":
            clip["sword"] = retime_sword(src, clip, rig, src_samples)
        elif key == "root" and isinstance(src.get("root"), list) and len(src["root"]) == len(times):
            clip["root"] = [frame_at(src["root"], times, s_t) for s_t in src_samples]
    seated = seat_off_hand(clip, rig)
    clip["feel"] = dict(src.get("feel") or {})
    clip["feel"]["hitstop"] = {"frames": hitstop, "in_clip": True}
    # the snap INTO the hit is a one-frame turn by design (finished R6 attacks turn the torso 40-110 deg in that frame):
    # the pop gate is lifted for it; everything else keeps the source's gate
    src_gate = dict(src.get("gate") or {})
    clip["gate"] = spec.get("gate") or {**src_gate, "pop_deg": max(float(src_gate.get("pop_deg", 60) or 60), 130.0)}
    return clip, {"hits": [round(h, 3) for h in hits], "frames": f"{len(times)} -> {len(out_times)}", "hit_out": hit_out,
                  "snap": {str(round(h, 3)): round(v, 3) for h, v in snaps.items()},
                  **({"off_hand": seated} if seated else {})}


def main(argv):
    if not argv:
        return emit("fail", "feel: needs <Name>.feel.json [--out <clip.json>]", "lune run kit anim feel <Name> --from <Clip>")
    path = argv[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    spec["name"] = spec.get("name") or os.path.basename(path).split(".")[0]
    build = os.path.join(os.environ.get("KIT_BUILD", "build"), "animations")
    src_name = spec.get("from")
    src = None
    for cand in (os.path.join(build, f"{src_name}.clip.json"), os.path.join(build, f"{src_name}.r6.clip.json")):
        if os.path.isfile(cand):
            with open(cand, encoding="utf-8") as fh:
                c = json.load(fh)
            if c.get("rig") == "R6":
                src, src_path = c, cand
                break
    if src is None:
        return emit("fail", f"feel {spec['name']}: no R6 clip for {src_name} in {build}", f"lune run kit anim {src_name}")
    rig = C.load_rig("r6")
    clip, info = apply(src, spec, rig)
    clip["source"] = {"kind": "feel", "file": path, "from": src_path, "sha256": S.sha256_of(path), "data_sha256": S.sha256_of(src_path),
                      "tool_sha256": S.sha256_of_many([__file__, C.__file__]), "rig_sha256": S.sha256_of(C.rig_path("r6"))}
    # the clip it is built from, by IDENTITY (its own spec + tool hashes): kit anim rewrites clip files at compile, so
    # the bytes are no dependency key; when the upstream spec or generator changes, this clip is stale
    up = src.get("source") if isinstance(src.get("source"), dict) else {}
    clip["source"]["from_sha256"] = up.get("sha256")
    clip["source"]["from_tool_sha256"] = up.get("tool_sha256")
    m = C.metrics(clip, rig, clip.get("gate"))
    out = out or os.path.join(build, f"{spec['name']}.clip.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(clip, fh, indent=1)
    note = f"hits at {info['hits']} -> {len(info['hit_out'])} holds, frames {info['frames']}"
    if m["problems"]:
        return emit("fail", f"feel {spec['name']}: {m['problems'][0]}", f"soften snap / overshoot in {path}", problems=m["problems"], **info)
    return emit("pass", f"feel {spec['name']} from {src_name}: {note}", f"lune run kit anim look {spec['name']} --rig R6", **info)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
