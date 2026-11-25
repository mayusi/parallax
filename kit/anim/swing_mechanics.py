"""swing_mechanics.py — A3, THE SWING BUILDER's solver (LIMITATIONS_FIXES_V4 4.4 / 13.4.1, card x9gk; plain numpy).

A weapon attack is a whip, not an arm: the body hits through a CHAIN, each link peaking a little after the one before -
the pelvis, then the torso, then (on an R6, whose arms slide along the shoulder) the shoulder, then the arm, then the
blade snapping on the Hit. Under it the legs work: the lead foot is PLANTED before the Hit, and the pelvis DROPS into the
stance, the rigid R6 legs splayed so the feet stay on the floor (no "stilts": a body lowered by sinking into the floor).
The owner judged the arm-only swings ("stilts, arm-only swing": SwordTrickCut, DTDrillSpin4) and asked for this.

    solve_swing(design_slot, dossier=None, ref_motion=None, intent="aggressive") -> plan
    check_swing(plan) -> [problems]   (empty: the plan keeps every number of the contract)

The CONTRACT (13.4.1), all at 60 fps:
    lead foot     v_sole == 0 for >= 2 frames before the Hit (and through the hold)
    pelvis        drops 0.25..0.60 studs into the stance; each leg tilted acos(1 - drop / LEG) so the foot stays planted
    the chain     peaks at  pelvis +0 -> torso +2 -> shoulder slide +4 -> arm +5 -> blade +6 frames, the blade ON the Hit
    torso         its peak turn rate 1,100..3,300 degrees / s
    shoulder      the R6 shoulder slide 0.6..1.7 studs
    hold          2..4 frames held at the end of the strike (heavier: longer)
    settle        eased (smoothstep), over >= 50% of the time left after the hold
    beats         {"windup": [t0, t1], "strike": [...], "hold": [...], "settle": [...]} stamped into the plan

The plan is CHANNELS a clip builder keys from (kit/anim/strike.py is the next sprint: a probe on ONE real move the
owner names - card x9gk), plus the beats; check_swing measures the same numbers on any plan, so a built clip's channels
can be held to them too.

    python kit/anim/swing_mechanics.py plan '<design json>' [--intent calm|proper|aggressive]
    python kit/anim/swing_mechanics.py check <plan.json>
"""

import json
import math
import sys

import numpy as np

FPS = 60
LEG = 2.0            # an R6 leg, studs (hip to sole)
DROP = (0.25, 0.60)  # the pelvis drop, studs
TURN = (1100.0, 3300.0)   # the torso's peak turn rate, degrees / s
SLIDE = (0.6, 1.7)   # the R6 shoulder slide, studs
HOLD = (2, 4)        # frames held at the end of the strike
PLANT_MIN = 2        # frames the lead foot is still before the Hit
SETTLE_MIN = 0.5     # the settle's share of the time after the hold
# the chain: each link's PEAK frame after the pelvis's (13.4.1); the blade's is the Hit
CHAIN = (("pelvis", 0), ("torso", 2), ("shoulder", 4), ("arm", 5), ("blade", 6))
# intent (the anim lane's calm / proper / aggressive, kit anim --intent): how hard the body throws it
INTENT = {
    "calm": {"drop": 0.28, "turn": 1300.0, "slide": 0.7, "step": 0.6},
    "proper": {"drop": 0.40, "turn": 2000.0, "slide": 1.1, "step": 0.9},
    "aggressive": {"drop": 0.55, "turn": 2800.0, "slide": 1.5, "step": 1.2},
}
# how far each link turns (degrees) for a kind of attack (a horizontal cut turns the body most, a thrust least)
AMPLITUDE = {
    "horizontal": {"pelvis": 35.0, "torso": 70.0, "arm": 110.0, "blade": 150.0},
    "diagonal": {"pelvis": 30.0, "torso": 60.0, "arm": 120.0, "blade": 160.0},
    "overhead": {"pelvis": 15.0, "torso": 35.0, "arm": 140.0, "blade": 170.0},
    "rising": {"pelvis": 25.0, "torso": 50.0, "arm": 120.0, "blade": 160.0},
    "thrust": {"pelvis": 20.0, "torso": 40.0, "arm": 60.0, "blade": 60.0},
}


def _ease(u):
    """smoothstep 0..1 (zero rate at both ends)"""
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3.0 - 2.0 * u)


def _sweep(n, peak, amp, window):
    """a channel turning `amp` over `window` frames on a cosine rate profile whose PEAK is at frame `peak` -> (n,)
    values (0 before, amp after): the rate's peak = amp * pi / (2 * window) per frame"""
    t = np.arange(n, dtype=np.float64)
    u = (t - (peak - window / 2.0)) / window
    return amp * (1.0 - np.cos(np.pi * np.clip(u, 0.0, 1.0))) / 2.0


def solve_swing(design_slot, dossier=None, ref_motion=None, intent="aggressive"):
    """one attack's swing as channels + beats (the contract in this file's header). design_slot: {"hit": s (the Hit's
    time), "duration": s, "kind": horizontal|diagonal|overhead|rising|thrust, "weight": light|heavy, "lead":
    left|right, "windup": s (optional, the wind-up's start)}. dossier: the move dossier ({"phases": {"windup": [t0,
    t1], ...}} narrows the wind-up start). ref_motion: measured numbers from the move's reference ({"turn": deg/s,
    "slide": studs, "drop": studs}), clamped into the contract. -> {"fps", "frames", "channels", "beats", "peaks",
    "intent", "params"}"""
    if intent not in INTENT:
        raise ValueError(f"swing: intent {intent!r} - one of {', '.join(INTENT)}")
    kind = str(design_slot.get("kind") or "horizontal")
    if kind not in AMPLITUDE:
        raise ValueError(f"swing: kind {kind!r} - one of {', '.join(AMPLITUDE)}")
    hit_t = float(design_slot["hit"])
    dur = float(design_slot.get("duration") or hit_t + 0.6)
    if not 0.15 <= hit_t < dur:
        raise ValueError(f"swing: the Hit at {hit_t} s must fall inside the move (0.15 s .. {dur} s)")
    heavy = str(design_slot.get("weight") or "light") == "heavy"
    p = dict(INTENT[intent])
    for k, lo_hi in (("turn", TURN), ("slide", SLIDE), ("drop", DROP)):   # a measured reference wins, kept in range
        v = (ref_motion or {}).get(k)
        if isinstance(v, (int, float)) and math.isfinite(v):
            p[k] = float(min(max(v, lo_hi[0]), lo_hi[1]))
    n = int(round(dur * FPS)) + 1
    hit = int(round(hit_t * FPS))
    pelvis_peak = hit - CHAIN[-1][1]
    if pelvis_peak < 2:
        raise ValueError("swing: the Hit comes too early for the chain (the pelvis must peak 6 frames before it)")
    amp = dict(AMPLITUDE[kind])
    # the torso's window from its turn rate: rate peak (deg / frame) = amp * pi / (2 * window). A small turn (an
    # overhead, a thrust) at the contract's rate would be over in under four frames - too short to read and too short
    # for a frame-sampled rate to keep it: the window stays four frames and the torso turns as far as the rate needs
    torso_window = amp["torso"] * math.pi / (2.0 * p["turn"] / FPS)
    if torso_window < 4.0:
        torso_window = 4.0
        amp["torso"] = p["turn"] / FPS * 2.0 * torso_window / math.pi
        amp["pelvis"] = max(amp["pelvis"], 0.5 * amp["torso"])
    wind0 = (dossier or {}).get("phases", {}).get("windup", [None])[0] if dossier else None
    wind0 = design_slot.get("windup", wind0)
    windup = int(round(float(wind0) * FPS)) if wind0 is not None else max(0, pelvis_peak - int(round(0.25 * FPS)))
    hold = HOLD[1] if heavy else HOLD[0] + (1 if intent != "calm" else 0)
    hold_end = min(n - 1, hit + hold)
    ch = {}
    peaks = {}
    for link, delay in CHAIN:
        pk = pelvis_peak + delay
        peaks[link] = pk
        if link == "shoulder":
            continue
        window = torso_window * {"pelvis": 1.3, "torso": 1.0, "arm": 0.8, "blade": 0.6}[link]
        ch[f"{link}_yaw"] = _sweep(n, pk, amp[link], window)
    # the R6 shoulder slides along its socket, peaking at its own frame and coming back over the settle
    slide = _sweep(n, peaks["shoulder"], p["slide"], torso_window * 0.9)
    # the settle: after the hold, every channel eases back toward its start over the rest of the move
    t = np.arange(n, dtype=np.float64)
    settle_u = _ease((t - hold_end) / max(1.0, (n - 1) - hold_end))
    back = 1.0 - 0.5 * settle_u   # (a recovery keeps half the turn: the body ends facing its cut, ready)
    for k in list(ch):
        v = ch[k].copy()
        v[hold_end:] = v[hold_end] * back[hold_end:]
        ch[k] = v
    slide[hold_end:] = slide[hold_end] * (1.0 - settle_u[hold_end:])
    ch["shoulder_slide"] = slide
    # the pelvis drop: down over the wind-up into the strike, held, up over the settle
    down = _ease((t - windup) / max(1.0, hit - windup))
    drop = -p["drop"] * down
    drop[hold_end:] = -p["drop"] * (1.0 - settle_u[hold_end:])
    ch["pelvis_y"] = drop
    # anti-stilt: each rigid leg tilted so the foot stays on the floor while the hip comes down
    ch["leg_tilt"] = np.degrees(np.arccos(np.clip(1.0 + drop / LEG, -1.0, 1.0)))
    # the lead foot: a step in over the wind-up, PLANTED from PLANT frames before the Hit through the hold
    plant = hit - max(PLANT_MIN + 2, int(round(0.07 * FPS)))
    step = p["step"] * _ease((t - windup) / max(1.0, plant - windup))
    ch["lead_foot_z"] = step
    beats = {"windup": [windup / FPS, pelvis_peak / FPS], "strike": [pelvis_peak / FPS, hit / FPS],
             "hold": [hit / FPS, hold_end / FPS], "settle": [hold_end / FPS, (n - 1) / FPS]}
    return {"fps": FPS, "frames": n, "hit": hit, "plant": plant, "hold_end": hold_end, "intent": intent,
            "kind": kind, "lead": design_slot.get("lead") or "left", "peaks": peaks, "beats": beats,
            "params": {**p, "torso_window": round(torso_window, 3), "hold": hold},
            "channels": {k: [round(float(x), 5) for x in v] for k, v in ch.items()}}


def _rate_peak(values):
    v = np.asarray(values, dtype=np.float64)
    if len(v) < 2:
        return 0, 0.0
    d = np.abs(np.diff(v))
    i = int(np.argmax(d))
    return i + 1, float(d[i])   # (the frame the step ENDS on: where the link moves fastest)


def check_swing(plan):
    """every number of the contract measured on the plan's channels -> [problems] (empty: it holds)"""
    out = []
    fps = int(plan.get("fps") or FPS)
    ch = {k: np.asarray(v, dtype=np.float64) for k, v in (plan.get("channels") or {}).items()}
    need = ["pelvis_yaw", "torso_yaw", "shoulder_slide", "arm_yaw", "blade_yaw", "pelvis_y", "leg_tilt", "lead_foot_z"]
    missing = [k for k in need if k not in ch]
    if missing:
        return [f"channels missing: {', '.join(missing)}"]
    hit = int(plan["hit"])
    # the lead foot: still for >= PLANT_MIN frames before the Hit
    v = np.abs(np.diff(ch["lead_foot_z"]))
    still = 0
    for f in range(hit - 1, -1, -1):
        if f < len(v) and v[f] <= 1e-6:
            still += 1
        else:
            break
    if still < PLANT_MIN:
        out.append(f"lead foot: still {still} frame(s) before the Hit (at least {PLANT_MIN})")
    # the pelvis drop and the legs that carry it
    lowest = -float(ch["pelvis_y"].min())
    if not DROP[0] - 1e-6 <= lowest <= DROP[1] + 1e-6:
        out.append(f"pelvis drop {lowest:.2f} studs (the contract: {DROP[0]}..{DROP[1]})")
    want_tilt = np.degrees(np.arccos(np.clip(1.0 + ch["pelvis_y"] / LEG, -1.0, 1.0)))
    if float(np.abs(ch["leg_tilt"] - want_tilt).max()) > 0.5:
        out.append("stilts: the legs do not tilt with the pelvis drop (a foot leaves the floor or sinks into it)")
    # the chain's order and spacing
    pk = {}
    for link, key in (("pelvis", "pelvis_yaw"), ("torso", "torso_yaw"), ("shoulder", "shoulder_slide"),
                      ("arm", "arm_yaw"), ("blade", "blade_yaw")):
        f, _ = _rate_peak(ch[key][: hit + 2])
        pk[link] = f
    base = pk["pelvis"]
    for link, delay in CHAIN:
        got = pk[link] - base
        if abs(got - delay) > 1:
            out.append(f"chain: {link} peaks at +{got} frames after the pelvis (the contract: +{delay})")
    if abs(pk["blade"] - hit) > 1:
        out.append(f"chain: the blade peaks {pk['blade'] - hit:+d} frames from the Hit (it must snap ON the Hit)")
    # the torso's turn rate
    _, step_deg = _rate_peak(ch["torso_yaw"])
    rate = step_deg * fps
    if not TURN[0] - 1 <= rate <= TURN[1] + 1:
        out.append(f"torso turn rate {rate:.0f} deg/s (the contract: {TURN[0]:.0f}..{TURN[1]:.0f})")
    slide = float(ch["shoulder_slide"].max())
    if not SLIDE[0] - 1e-6 <= slide <= SLIDE[1] + 1e-6:
        out.append(f"shoulder slide {slide:.2f} studs (the contract: {SLIDE[0]}..{SLIDE[1]})")
    # the hold and the settle
    hold = int(plan["hold_end"]) - hit
    if not HOLD[0] <= hold <= HOLD[1]:
        out.append(f"hold {hold} frame(s) (the contract: {HOLD[0]}..{HOLD[1]})")
    b = plan.get("beats") or {}
    if not all(k in b for k in ("windup", "strike", "hold", "settle")):
        out.append("beats: windup / strike / hold / settle not all stamped")
    else:
        after = (int(plan["frames"]) - 1 - hit) / fps
        settle = b["settle"][1] - b["settle"][0]
        if after <= 0 or settle / after < SETTLE_MIN:
            out.append(f"settle {settle:.2f} s of the {after:.2f} s after the Hit (at least {SETTLE_MIN:.0%})")
    return out


def main(argv):
    if len(argv) >= 2 and argv[0] == "plan":
        design = json.loads(argv[1])
        intent = argv[argv.index("--intent") + 1] if "--intent" in argv else "aggressive"
        plan = solve_swing(design, intent=intent)
        problems = check_swing(plan)
        print(json.dumps({"status": "pass" if not problems else "fail", "plan": plan, "problems": problems}))
        return 0 if not problems else 1
    if len(argv) >= 2 and argv[0] == "check":
        with open(argv[1], encoding="utf-8") as fh:
            plan = json.load(fh)
        problems = check_swing(plan.get("plan", plan))
        print(json.dumps({"status": "pass" if not problems else "fail", "problems": problems}))
        return 0 if not problems else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
