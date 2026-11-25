"""profile.py — the CRAFT numbers of an R6 clip, and how far they are from an approved reference.

    python kit/anim/anim_profile.py <clip.json> [--vs <reference clip.json>] [--walkspeed 16] [--out <profile.json>]

Why: "it looks bad" has causes the craft names (board/plans/archive/2026-10-11-anim-research.md), and every one is measurable:
- AMPLITUDE: how far each limb swings, and how far the torso twists (the fundamental of each pitch / yaw curve)
- OPPOSITION / DRAG: each limb's phase against the lead leg (arms opposite the legs; a late arm reads as lag)
- BOB: the body's height change per step (twice a cycle); too much reads as flailing
- TWINNING: left vs right half a cycle apart; a perfect mirror is lifeless
- SNAP: a swing's peak speed / mean speed (1.57 = a sine: floaty; finished R6 runs measure 2.8-2.9: they hang at the
  extremes and whip through the middle)
- GROUND SPEED (loops): the sole's fore-aft sweep per step / the step time = the speed the feet do not skate at;
  Roblox time-scales locomotion with WalkSpeed, so the clip should be played at WalkSpeed / natural speed
- SHAPE (loops; what the angles above missed on the rejected RigRun / RigRun2, kit/anim/silhouette.py): where the
  FORWARD HAND goes (studs from the body's midline and above the torso's centre: approved runs bring it to the midline
  at chest-to-head height; airplane arms stay out at the side), how far the FRONT FOOT reaches ahead of the torso
  (splits), how high the HEEL kicks behind, and a same-side arm / leg fault (the arm must oppose its leg)
One-shots (attacks): the fastest striker's timeline - startup (to the first fast frame), active (the fast window),
recovery (after it) - and its snap.
With --vs, every gap beyond tolerance becomes a sentence ("arm swing 31% under the reference")."""
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

LIMBS = ("Right Leg", "Left Leg", "Right Arm", "Left Arm")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def harmonic(sig, k=1):
    """amplitude and phase (0..1 of the cycle) of the k-th harmonic of a periodic signal"""
    n = len(sig)
    t = np.arange(n)
    z = np.sum((sig - sig.mean()) * np.exp(-2j * np.pi * k * t / n))
    return float(abs(z) * 2 / n), float((-np.angle(z) / (2 * np.pi * k)) % (1.0 / k))


def snap(sig, loop):
    d = np.abs(np.diff(np.append(sig, sig[0]) if loop else sig))
    return float(d.max() / max(d.mean(), 1e-9))


def curves(clip):
    loop = bool(clip.get("loop"))
    n = len(clip["times"]) - (1 if loop and len(clip["times"]) > 2 else 0)
    out = {}
    for j, d in clip["joints"].items():
        fr = d["frames"][:n]
        pyr = np.degrees(np.unwrap(np.radians([M.pyr(C.quat_mat(f[:4])) for f in fr]), axis=0))
        if j in LIMBS:
            # a limb's SWING: the angle of its down-axis in the forward / up plane (0 = hanging, + = forward), continuous
            # through 90 - an euler pitch flips there (gimbal), and finished R6 sprints swing arms to 155
            down = np.array([C.quat_mat(f[:4]) @ np.array([0, -1.0, 0]) for f in fr])
            swing = np.degrees(np.unwrap(np.arctan2(-down[:, 2], -down[:, 1])))
            pyr = pyr.copy()
            pyr[:, 0] = swing
        out[j] = {"pyr": pyr, "pos": np.array([f[4:7] for f in fr], dtype=float)}
    return out, n, loop


def profile(clip, walkspeed=16.0):
    cv, n, loop = curves(clip)
    fps = float(clip.get("fps") or 30)
    dur = n / fps if loop else float(clip["times"][-1])
    p = {"name": clip.get("name"), "loop": loop, "cycle_s": round(dur, 4), "frames": n}
    if loop and "Right Leg" in cv:
        _, lead = harmonic(cv["Right Leg"]["pyr"][:, 0])
        for j in LIMBS:
            if j not in cv:
                continue
            amp, ph = harmonic(cv[j]["pyr"][:, 0])
            p[f"{j} swing amp"] = round(amp, 1)
            p[f"{j} phase"] = round((ph - lead) % 1.0, 3)
            p[f"{j} snap"] = round(snap(cv[j]["pyr"][:, 0], True), 2)
            pos = cv[j]["pos"]
            p[f"{j} slide max"] = round(float(np.abs(pos).max()), 2)
            sw = cv[j]["pyr"][:, 0]
            if sw.max() > 185 or sw.min() < -185:
                p.setdefault("faults", []).append(f"{j} swings OVER THE TOP ({sw.min():.0f}..{sw.max():.0f}): a key pair more than 180 apart interpolates the short way - add a breakdown at the bottom")
        if "Torso" in cv:
            amp, ph = harmonic(cv["Torso"]["pyr"][:, 1])
            p["torso twist amp"] = round(amp, 1)
            p["torso twist phase"] = round((ph - lead) % 1.0, 3)
            p["lean"] = round(float(cv["Torso"]["pyr"][:, 0].mean()), 1)
            p["bob"] = round(harmonic(cv["Torso"]["pos"][:, 1], 2)[0], 3)
        if "Head" in cv and "Torso" in cv:
            ha, hp = harmonic(cv["Head"]["pyr"][:, 1])
            ta, tp = harmonic(cv["Torso"]["pyr"][:, 1])
            p["head counter"] = round(ha / max(ta, 1e-6), 2) if abs(((hp - tp) % 1.0) - 0.5) < 0.15 else 0.0
        twin = []
        for r, l in (("Right Leg", "Left Leg"), ("Right Arm", "Left Arm")):
            if r in cv and l in cv:
                twin.append(float(np.abs(cv[r]["pyr"][:, 0] - np.roll(cv[l]["pyr"][:, 0], n // 2)).mean()))
        if twin:
            p["asymmetry deg"] = round(float(np.mean(twin)), 1)
        # the speed the feet do not skate at: the sole's fore-aft sweep per step, over half a cycle
        rig = C.load_rig("r6")
        frames = C.world_frames(clip, rig)[:n]
        sole = np.array([(f["Right Leg"] @ np.array([0, -1.0, 0, 1.0]))[2] for f in frames])
        sweep = float(sole.max() - sole.min())
        nat = sweep / max(dur / 2.0, 1e-6)
        p["natural ground speed"] = round(nat, 2)
        p[f"play rate at WalkSpeed {walkspeed:g}"] = round(walkspeed / max(nat, 1e-6), 2)
        p.update(shape(frames, rig, cv, p))
    elif not loop:
        m = C.metrics(clip, C.load_rig("r6"), {"foot_slide": 99, "foot_skate": 99, "pop_deg": 999, "penetration": 99,
                                                "loop_seam_deg": 999, "hit_before": 999, "hit_after": 999})
        eff = m["effectors"].get("Blade") or (m["effectors"].get(m.get("fastest")) if m.get("fastest") else None)
        if eff and eff.get("positions"):
            pos = np.array(eff["positions"], dtype=float)
            sp = np.linalg.norm(np.diff(pos, axis=0), axis=1) * fps
            fast = np.where(sp > 0.5 * sp.max())[0]
            if len(fast):
                p["startup_s"] = round(fast[0] / fps, 3)
                p["active_s"] = round((fast[-1] - fast[0] + 1) / fps, 3)
                p["recovery_s"] = round(max(0.0, dur - (fast[-1] + 1) / fps), 3)
                p["strike snap"] = round(float(sp.max() / max(sp.mean(), 1e-9)), 2)
                p["peak speed"] = round(float(sp.max()), 1)
    return p


def shape(frames, rig, cv, p):
    """the SHAPE numbers (studs, world, against the torso): forward hand to the midline / height, front-foot reach,
    heel kick; and the same-side fault"""
    def tip(part, m):
        return (m @ np.array([0, -rig["sizes"][part][1] / 2.0, 0, 1.0]))[:3]
    floor = min(min(C.lowest(rig, q, f[q]) for q in ("Right Leg", "Left Leg")) for f in frames)
    out, cross, height, ahead, kick = {}, [], [], [], []
    for side, s in (("Right", 1.0), ("Left", -1.0)):
        T = np.array([f["Torso"][:3, 3] for f in frames])
        hand = np.array([tip(f"{side} Arm", f[f"{side} Arm"]) for f in frames])
        foot = np.array([tip(f"{side} Leg", f[f"{side} Leg"]) for f in frames])
        hf = -(hand[:, 2] - T[:, 2])
        front = hf > np.quantile(hf, 0.75)
        cross.append(float((s * (hand[front, 0] - T[front, 0])).mean()))
        height.append(float((hand[front, 1] - T[front, 1]).max()))
        ff = -(foot[:, 2] - T[:, 2])
        ahead.append(float(ff.max()))
        kick.append(float((foot[ff < np.quantile(ff, 0.33), 1] - floor).max()))
    out["forward hand from midline"] = round(float(np.mean(cross)), 2)
    out["forward hand height"] = round(float(np.mean(height)), 2)
    out["front foot reach"] = round(float(np.mean(ahead)), 2)
    out["heel kick"] = round(float(np.mean(kick)), 2)
    for side in ("Right", "Left"):
        a, l = cv.get(f"{side} Arm"), cv.get(f"{side} Leg")
        if a is not None and l is not None and np.std(a["pyr"][:, 0]) > 1 and np.std(l["pyr"][:, 0]) > 1:
            r = float(np.corrcoef(a["pyr"][:, 0], l["pyr"][:, 0])[0, 1])
            if r > 0.2:
                p.setdefault("faults", []).append(f"{side.lower()} arm swings WITH its own leg (correlation {r:+.2f}): arms must oppose the legs - the {side.lower()} arm goes forward with the other leg")
    return out


SHAPE_TOL = {"forward hand from midline": (0.35, "the forward hand stays {a:.2f} studs {w} the midline than the reference - {fix}",
                                           "further out from", "closer to", "swing it ACROSS the body (airplane arms otherwise)", "less across"),
             "forward hand height": (0.35, "the forward hand rises {d:+.2f} studs vs the reference - {fix}", "", "",
                                     "pump it higher, toward the chest / face", "lower"),
             "front foot reach": (0.3, "the front foot reaches {d:+.2f} studs vs the reference - {fix}", "", "",
                                  "reach further", "keep the legs under the body (splits)"),
             "heel kick": (0.35, "the heel kicks {d:+.2f} studs vs the reference - {fix}", "", "",
                           "kick the trailing leg up behind", "less heel kick")}


TOL = {"swing amp": 0.2, "twist amp": 0.25, "bob": 0.35, "snap": 0.2, "cycle_s": 0.25, "asymmetry deg": None, "lean": None}


def gaps(p, ref):
    out = []
    for k, v in p.items():
        if k not in ref or not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        r = ref[k]
        if "phase" in k:
            d = ((v - r + 0.5) % 1.0) - 0.5
            if abs(d) > 0.06:
                out.append(f"{k}: {d:+.2f} cycle vs the reference ({'late' if d > 0 else 'early'}; {abs(d) * p.get('cycle_s', 1):.2f} s)")
            continue
        if k == "asymmetry deg":
            if v < 2.0 <= r:
                out.append(f"twinned: left / right differ {v}° (reference {r}°) - break the mirror")
            continue
        if k == "lean":
            if abs(v - r) > 5:
                out.append(f"lean {v}° vs {r}°")
            continue
        if k in SHAPE_TOL:
            tol, text, far, near, up_fix, down_fix = SHAPE_TOL[k]
            d = v - r
            if abs(d) > tol:
                if k == "forward hand from midline":
                    out.append(text.format(a=abs(d), w=far if d > 0 else near, fix=up_fix if d > 0 else down_fix))
                else:
                    out.append(text.format(d=d, w="", fix=up_fix if d < 0 else down_fix))
            continue
        tol = next((t for key, t in TOL.items() if key in k and t), None)
        if tol and abs(r) > 1e-6 and abs(v - r) / abs(r) > tol:
            out.append(f"{k}: {v} vs {r} ({(v - r) / abs(r) * 100:+.0f}%)")
    return out


def main(argv):
    if not argv:
        return emit("fail", "profile: needs <clip.json> [--vs <ref clip.json>]", "lune run kit anim profile <Name> --vs <Ref>")
    with open(argv[0], encoding="utf-8") as fh:
        clip = json.load(fh)
    ws = float(argv[argv.index("--walkspeed") + 1]) if "--walkspeed" in argv else 16.0
    p = profile(clip, ws)
    result = {"profile": p}
    note = ", ".join(f"{k} {v}" for k, v in p.items() if k not in ("name", "loop", "frames"))
    if "--vs" in argv:
        with open(argv[argv.index("--vs") + 1], encoding="utf-8") as fh:
            ref = json.load(fh)
        rp = profile(ref, ws)
        g = list(p.get("faults") or []) + gaps(p, rp)
        result.update({"reference": rp, "gaps": g})
        note = f"{len(g)} gap(s) vs {rp.get('name')}" + (": " + "; ".join(g) if g else " - within the reference's profile")
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=1)
    return emit("pass", f"profile {p.get('name')}: {note}", "close the gaps in the source (amplitudes, phases / offsets, eases for snap), then profile again" if result.get("gaps") else "none - proceed", **result)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
