"""gait_r6.py — R6-NATIVE locomotion (walk, run, sprint, idle), in the vocabulary of finished R6 animations.

    python kit/anim/gait_r6.py <Name>.gait.json --out <clip.json>        (a .gait.json with "rig": "R6")

An R6 character has straight one-piece legs and arms: a human gait folded onto it reads stiff (kit lesson, the
owner's verdict 2026-10-11). What Roblox animators do instead (measured with kit/anim/measure.py on the DevForum
'[R6] Run + Walk' pack, azazinchic's run, Roblox's own R6 walk - VETLOG 2026-10-11):
- the legs are PENDULUMS of +-45..+-100 degrees, and they TRANSLATE: a swing leg rises 0.5-0.7 studs into the
  torso and moves 0.8-1.3 studs forward (a knee it does not have), a landing leg reaches DOWN, a stance leg drags
  back; the sole touches the floor only around the vertical, where it runs at the ground speed;
- the arms swing against the same side's leg - small with a forward/back translation in a walk (+-20), pumping to
  155 degrees with the hand dropping 0.85 and reaching 0.7 forward in a sprint, elbows out (roll, yaw);
- the torso leans a constant 6-17 degrees, sits 0.1-0.2 studs low, twists +-6 (walk) to +-18 (sprint) against the
  leading leg, rolls a little; the head counters the twist EXACTLY and the lean fully;
- the cycle is 0.8 s (walk), 0.57 s (sprint), keyed linear at 60 fps - the shape lives in the curves.

Every number here is a parameter; `kit anim fit <Name> --to <Reference>` (kit/anim/fit_r6.py) sets them from a
reference clip's measured curves. Parameters (per kind defaults in KINDS): speed, cycle, duty (stance fraction),
amp_fwd / amp_back (deg: the leg ahead at contact / behind at lift-off), band (deg around vertical where the sole
is on the floor), knee (studs the swing leg rises), reach (studs it moves forward), reach_down (studs the landing
leg extends down), drag (studs the stance leg slides back), overshoot (deg past contact), lean, drop, forward,
twist, sway, bob, rise, arm_fwd, arm_back, arm_in, arm_out, arm_reach, arm_drop, head (0..1 lean counter),
look (deg), fps. Idle: period, breathe, arm_out.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C                 # noqa: E402
import strike as S               # noqa: E402  (R6 constants, euler, frame_of, sha helpers)
from gait_curves import _slopes  # noqa: E402

KINDS = {
    "walk":   dict(speed=8.0, cycle=0.8, duty=0.6, amp_fwd=50.0, amp_back=46.0, band=12.0, knee=0.6, reach=0.75, reach_down=0.15,
                   drag=0.25, overshoot=3.0, lean=6.0, drop=0.09, forward=0.09, twist=6.0, sway=1.0, bob=0.025, rise=0.0,
                   arm_fwd=29.0, arm_back=16.0, arm_in=7.0, arm_out=3.0, arm_reach=0.27, arm_drop=0.1, head=1.0, look=0.0),
    "run":    dict(speed=16.0, cycle=0.62, duty=0.5, amp_fwd=64.0, amp_back=68.0, band=12.0, knee=0.5, reach=1.0, reach_down=0.1,
                   drag=0.15, overshoot=4.0, lean=14.0, drop=0.08, forward=0.1, twist=15.0, sway=4.0, bob=0.08, rise=0.05,
                   arm_fwd=110.0, arm_back=20.0, arm_in=30.0, arm_out=25.0, arm_reach=0.5, arm_drop=0.4, head=1.0, look=0.0),
    "sprint": dict(speed=24.0, cycle=0.567, duty=0.45, amp_fwd=64.0, amp_back=98.0, band=12.0, knee=0.65, reach=1.3, reach_down=0.4,
                   drag=0.25, overshoot=5.0, lean=14.0, drop=0.13, forward=0.19, twist=18.0, sway=1.3, bob=0.05, rise=0.05,
                   arm_fwd=155.0, arm_back=42.0, arm_in=32.0, arm_out=37.0, arm_reach=0.7, arm_drop=0.7, head=1.0, look=0.0),
    "idle":   dict(period=3.2, breathe=0.035, arm_out=5.0, lean=0.0, sway=0.0, look=0.0),
}
# a fit may move these this far (lower, upper); the rest is fixed by the spec
FIT_RANGES = {
    "duty": (0.35, 0.7), "amp_fwd": (20.0, 90.0), "amp_back": (20.0, 110.0), "knee": (0.0, 1.0), "reach": (0.0, 1.6),
    "reach_down": (0.0, 0.6), "drag": (-0.3, 0.6), "overshoot": (0.0, 12.0), "lean": (-5.0, 30.0), "drop": (-0.1, 0.4),
    "forward": (-0.2, 0.4), "twist": (0.0, 30.0), "sway": (0.0, 8.0), "bob": (0.0, 0.2), "rise": (0.0, 0.3),
    "arm_fwd": (0.0, 170.0), "arm_back": (-20.0, 80.0), "arm_in": (-20.0, 70.0), "arm_out": (-20.0, 70.0),
    "arm_reach": (0.0, 1.0), "arm_drop": (0.0, 1.0), "head": (0.0, 1.5), "look": (-15.0, 15.0),
}
L = float(np.linalg.norm(S.SOLE["Right Leg"]))
PARTS = ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def hermite(points, u):
    """a monotone cubic through (u, value) keypoints, clamped to the ends"""
    pts = sorted(points)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    m = _slopes(xs, ys)
    u = min(max(u, xs[0]), xs[-1])
    i = 0
    while i < len(xs) - 2 and xs[i + 1] <= u:
        i += 1
    h = xs[i + 1] - xs[i]
    s = (u - xs[i]) / h
    h00, h10, h01, h11 = 2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s, -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2
    return h00 * ys[i] + h10 * h * m[i] + h01 * ys[i + 1] + h11 * h * m[i + 1]


def periodic(points, q):
    """a periodic monotone cubic: points as (phase 0..1, value); the loop closes on its first point"""
    pts = sorted((x % 1.0, y) for x, y in points if x < 1.0 - 1e-9)
    ext = [(x - 1.0, y) for x, y in pts] + pts + [(x + 1.0, y) for x, y in pts]
    return hermite(ext, q % 1.0)


def pitch_of_local(R_local, leg):
    """the forward/back angle (deg, + = forward) a leg's local rotation gives its sole"""
    s = R_local @ S.SOLE[leg]
    return math.degrees(math.atan2(-s[2], -s[1]))


def locomotion(p, name, fps):
    v, T, d = float(p["speed"]), float(p["cycle"]), float(p["duty"])
    Af, Ab, band = float(p["amp_fwd"]), float(p["amp_back"]), float(p["band"])
    n = int(round(T * fps))
    times = [round(i / fps, 6) for i in range(n + 1)]
    J = {k: [] for k in PARTS}
    lean, drop, fwd = float(p["lean"]), float(p["drop"]), float(p["forward"])
    bob, rise = float(p["bob"]), float(p["rise"])
    flight = max(0.0, 0.5 - d)
    # the pelvis over one leg's half cycle (contact, absorb, up by mid-stance, push, flight), around its drop
    pelvis_pts = [(0.0, -0.3 * bob), (0.14 * d, -bob), (0.5 * d, 0.0), (d, 0.2 * bob + (rise * 0.3 if flight > 1e-6 else 0.0))]
    if flight > 1e-6:
        pelvis_pts.append((d + flight * 0.5, 0.2 * bob + rise))
    pelvis_half = [(x / 0.5, y) for x, y in pelvis_pts]
    # the stance leg: +Af at contact (ahead) to -Ab at lift-off; inside `band` of the vertical its sole is on the
    # floor and runs at EXACTLY the ground speed (theta = asin(v t / L)); the band sits where the pendulum crosses
    # the vertical, which a longer back-swing puts earlier than mid-stance
    # the band is at least 2.5 frames wide (a sprint at 30 fps crosses 12 degrees in half a frame), so the
    # frames the gates see in contact are inside it
    qc_t = max(L * math.sin(math.radians(band)) / v, 1.25 / fps)
    qc = qc_t / T
    q0 = d * Af / max(Af + Ab, 1e-6)                            # the phase the leg is vertical

    def torso_at(phi):
        yaw = -float(p["twist"]) * math.cos(2 * math.pi * phi)
        roll = float(p["sway"]) * math.sin(2 * math.pi * (phi - d / 4))
        y = -drop + periodic(pelvis_half, (phi * 2.0) % 1.0)
        x = 0.04 * math.sin(2 * math.pi * phi)
        return S.euler((-lean, yaw, roll)), np.array([x, y, -fwd]), yaw, roll

    def hip_z(leg, phi):
        m, pp, _, _ = torso_at(phi)
        return float((pp + m @ S.HIP[leg])[2])

    def band_pitch(leg, q, off):
        """inside the band the sole follows a WORLD ground line moving back at v through the point under the hip
        at the vertical crossing - whatever the twisting torso does to the hip meanwhile"""
        line = hip_z(leg, q0 - off) + (q - q0) * T * v
        return math.degrees(math.asin(max(-1.0, min(1.0, (hip_z(leg, q - off) - line) / L))))

    def stance_pitch(leg, q, off):
        if abs(q - q0) <= qc:
            return band_pitch(leg, q, off)
        lo, hi = max(1e-3, q0 - qc), min(d - 1e-3, q0 + qc)
        pts = [(0.0, Af), (lo, band_pitch(leg, lo, off)), (hi, band_pitch(leg, hi, off)), (d, -Ab)]
        return hermite(pts, q)

    over = float(p["overshoot"])
    swing_pts = [(0.0, -Ab), (0.45, -Ab + (Af + Ab) * 0.62), (0.82, Af + over), (1.0, Af)]
    knee, reach, reach_down, drag = float(p["knee"]), float(p["reach"]), float(p["reach_down"]), float(p["drag"])
    arm_fwd, arm_back = float(p["arm_fwd"]), float(p["arm_back"])
    arm_pts = [(0.0, -arm_back), (0.18, -arm_back * 0.75), (0.5, arm_fwd), (0.68, arm_fwd * 0.8)]
    for i, t in enumerate(times):
        phi = (t / T) % 1.0 if i < n else 0.0
        # ---- torso: a constant lean and drop, a twist against the leading leg, a little roll, the bob
        torso_m, torso_p, yaw, roll = torso_at(phi)
        y = float(torso_p[1])
        J["Torso"].append(S.frame_of(torso_m, torso_p))
        for leg, off in (("Right Leg", 0.0), ("Left Leg", 0.5)):
            q = (phi + off) % 1.0
            if q <= d + 1e-9:
                u = q / d
                ang = stance_pitch(leg, q, off)
                # the landing leg reaches down, then the stance leg drags back over the floor
                lift = -reach_down * max(0.0, 1.0 - u / 0.35) ** 1.5
                # no translation while the sole is on the floor (the band): the drag comes after it
                u0, uc = q0 / d, qc / d
                slide = drag * hermite([(0.0, -0.2), (max(0.01, u0 - uc), 0.0), (min(0.99, u0 + uc), 0.0), (1.0, 1.0)], u)
            else:
                u = (q - d) / (1.0 - d)
                ang = hermite(swing_pts, u)
                lift = knee * math.sin(math.pi * u) ** 1.2
                slide = -reach * math.sin(math.pi * min(1.0, u * 1.15)) ** 1.1 + drag * (1.0 - u) * 0.3
            # the leg swings in the WORLD's forward plane (vertical at 0) whatever the torso's lean and twist do
            # to its hip: a twisted torso would otherwise carry a planted sole sideways
            R_local = torso_m.T @ S.euler((ang, 0.0, 0.0))
            hip = torso_p + torso_m @ S.HIP[leg]
            # the translations are WORLD-aligned (a lift is vertical, a slide horizontal) whatever the lean
            sole = hip + torso_m @ (R_local @ S.SOLE[leg]) + np.array([0.0, lift, slide])
            floor_gap = sole[1] - S.FLOOR_R6
            if q <= d + 1e-9:
                # on the floor through the band (by phase), releasing within a third of a frame beyond it; outside
                # it the sole stays clear (a reach-down that touched the floor there would skid at the hermite's speed)
                w = 1.0 if abs(q - q0) <= qc else max(0.0, 1.0 - (abs(q - q0) - qc) * T * fps / 0.3)
                dy = w * (-floor_gap) + (1.0 - w) * max(0.0, 0.06 - floor_gap)
            else:
                dy = max(0.0, 0.06 - floor_gap)
            off_v = torso_m.T @ np.array([0.0, lift + dy, slide])
            J[leg].append(S.frame_of(R_local, (off_v[0], off_v[1], off_v[2])))
        # ---- arms: against the same side's leg; forward bigger than back, the hand dropping and reaching
        for arm, off in (("Right Arm", 0.0), ("Left Arm", 0.5)):     # the right arm is BACK at the right leg's contact
            q = (phi + off) % 1.0
            a = periodic(arm_pts, q)
            f = max(0.0, a) / max(arm_fwd, 1e-6)
            swing = (a + arm_back) / max(arm_fwd + arm_back, 1e-6)  # 0 at the back, 1 at the front
            side = 1.0 if arm == "Right Arm" else -1.0
            yaw_a = -side * float(p["arm_in"]) * (0.35 + 0.65 * f)
            roll_a = side * float(p["arm_out"]) * (0.4 + 0.6 * f)
            R = S.euler((a + 0.6 * lean, yaw_a, roll_a))
            J[arm].append(S.frame_of(R, (0.0, -float(p["arm_drop"]) * f, -float(p["arm_reach"]) * (2 * swing - 1))))
        # ---- head: counters the twist exactly and the lean, nods with the bob
        head_m = S.euler((lean * float(p["head"]) + float(p["look"]) - 8.0 * (y + drop), -yaw, -roll * 0.5))
        J["Head"].append(S.frame_of(head_m))
    return {"schema": 1, "name": name, "rig": "R6", "fps": fps, "duration": times[-1], "loop": True, "priority": "Movement",
            "joints": {k: {"frames": f} for k, f in J.items()}, "times": times, "events": [],
            "locomotion": {"speed": round(v, 3), "direction": [0.0, 0.0, -1.0], "cycle": round(T, 4)},
            "style": {"amp_fwd": Af, "amp_back": Ab, "duty": d}}


def idle(p, name, fps):
    T = float(p["period"])
    n = int(round(T * fps))
    times = [round(i / fps, 6) for i in range(n + 1)]
    J = {k: [] for k in PARTS}
    b = float(p["breathe"])
    for i, t in enumerate(times):
        phi = (t / T) % 1.0 if i < n else 0.0
        s = math.sin(2 * math.pi * phi)
        torso_m = S.euler((-float(p["lean"]) - 0.8 * s, 0.0, float(p["sway"]) * s))
        J["Torso"].append(S.frame_of(torso_m, (0.0, b * (s - 1) / 2, 0.0)))
        J["Head"].append(S.frame_of(S.euler((float(p["look"]) + 1.2 * s, 0.0, 0.0))))
        for arm, side in (("Right Arm", 1.0), ("Left Arm", -1.0)):
            J[arm].append(S.frame_of(S.euler((1.5 * s, 0.0, side * (float(p["arm_out"]) + 1.5 * s)))))
        for leg in ("Right Leg", "Left Leg"):
            lift = b * (s - 1) / 2                                  # the legs stay on the floor as the body sinks
            J[leg].append(S.frame_of(np.eye(3), (0.0, -lift, 0.0)))
    return {"schema": 1, "name": name, "rig": "R6", "fps": fps, "duration": times[-1], "loop": True, "priority": "Idle",
            "joints": {k: {"frames": f} for k, f in J.items()}, "times": times, "events": []}


def params_of(spec):
    kind = spec.get("kind", "run")
    if kind not in KINDS:
        raise ValueError(f"unknown R6 gait kind {kind!r} ({', '.join(KINDS)})")
    p = dict(KINDS[kind])
    p.update({k: v for k, v in spec.items() if k in p})
    return kind, p


def generate(spec):
    kind, p = params_of(spec)
    fps = int(spec.get("fps") or 30)
    name = spec.get("name") or kind.capitalize()
    clip = idle(p, name, fps) if kind == "idle" else locomotion(p, name, fps)
    clip["gate"] = spec.get("gate")
    clip["params"] = p
    if spec.get("fitted_to"):
        clip["fitted_to"] = spec["fitted_to"]
    return clip


def main(argv):
    if not argv:
        return emit("fail", "gait_r6: needs <Name>.gait.json [--out <clip.json>]", "lune run kit anim new Run --gait run --rig R6")
    path = argv[0]
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    spec["name"] = spec.get("name") or os.path.basename(path).split(".")[0]
    try:
        clip = generate(spec)
    except ValueError as e:
        return emit("fail", f"gait_r6 {spec['name']}: {e}", f"fix {path}")
    clip["source"] = {"kind": "gait", "file": path, "sha256": S.sha256_of(path),
                      "tool_sha256": S.sha256_of_many([__file__, C.__file__]), "rig_sha256": S.sha256_of(C.rig_path("r6"))}
    rig = C.load_rig("r6")
    m = C.metrics(clip, rig, spec.get("gate"))
    style = clip.get("style") or {}
    info = {"amp_fwd": style.get("amp_fwd"), "amp_back": style.get("amp_back")}
    if m["problems"]:
        return emit("fail", f"gait_r6 {spec['name']}: {m['problems'][0]}", f"adjust the parameters in {path}, then: lune run kit anim {spec['name']}",
                    problems=m["problems"], **info)
    out = out or os.path.join(os.environ.get("KIT_BUILD", "build"), "animations", f"{spec['name']}.clip.json")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(clip, fh, indent=1)
    what = (f"legs +{style['amp_fwd']}/-{style['amp_back']} deg at {clip['locomotion']['speed']} studs/s, cycle {clip['locomotion']['cycle']} s"
            if style else "a breathing idle")
    fitted = f" (fitted to {spec['fitted_to']['name']}, distance {spec['fitted_to'].get('distance')})" if isinstance(spec.get("fitted_to"), dict) else ""
    return emit("pass", f"gait_r6 {spec['name']} ({spec.get('kind', 'run')}): {len(clip['times'])} frames, {what}{fitted}",
                f"lune run kit anim look {spec['name']} --rig R6", **info)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
