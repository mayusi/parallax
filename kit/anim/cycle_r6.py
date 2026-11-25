"""cycle_r6.py — locomotion cycles for the owner's R6 rig, built from MEASURED key poses of approved R6 animations.

    python kit/anim/cycle_r6.py learn <reference clip.json> --kind <walk|run|sprint|...> [--phases 4]
    python kit/anim/cycle_r6.py <kind> --as <Name> [--params '{"scale": 1.1, "cycle": 36}'] [--out <path>]

Why this shape (2026-10-11): two runs written from rules alone (RigRun, RigRun2) were rejected as "bad" and
"genuinely horrible", though their swing amplitudes, phases and bob matched the approved sprint. Rendered as
silhouettes (kit/anim/silhouette.py) the difference was the SHAPE of each pose, which angles do not describe:
- an approved R6 run carries both legs FORWARD under the leaned body (slides of 0.3-1.3 studs) and fakes the knee by
  sliding the swinging leg UP and forward at passing - RigRun2 rotated rigid legs instead, so they splayed (splits);
- its forward hand rises to head height and crosses the body's midline; the back hand sits out at the hip - RigRun2
  swung both arms straight fore-aft (airplane arms);
- the body hardly bobs (0.07 studs).
So the cycle is described where the craft describes it: each phase of a step (contact, down, passing, up - or more
breakdowns) as the torso's lean / turn / tilt, each leg's clean swing + slide (the R6 knee), each HAND's position, the
head's facing, and how high the lowest foot is. `learn` measures that table from an approved clip (both steps folded
into one, mirrored, so the table is one step); the generator rebuilds a cycle from it with knobs:
- scale       amplitude of the swings, slides and hand reach about the passing pose (1.0 = the reference)
- cycle       frames at 60 fps (the reference's own by default); Roblox plays locomotion at WalkSpeed / natural speed
- asym        the second step's scale (break the mirror: approved clips differ 5-12 deg left / right)
- lean        degrees added to the torso lean
- arm_cross   studs the forward hand moves further across the body (+) or out (-)
- knee        scale of the passing knee drive (the swing leg's up / forward slide)
- offsets     the drag hierarchy in frames ({"arms": 1, "head": 2, "body.lean": 1, ...}; kit/anim/pose_r6.py)
Presets live in kit/anim/cycle_presets.json, each with the clip it was learned from."""
import copy
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import pose_from as PF  # noqa: E402

PRESETS = os.path.join(HERE, "cycle_presets.json")
HIP = {"Right Leg": np.array([1.0, -1.0, 0]), "Left Leg": np.array([-1.0, -1.0, 0])}     # torso-local, Roblox axes
REST = {"Right Leg": np.array([0.5, -2.0, 0]), "Left Leg": np.array([-0.5, -2.0, 0])}
KNOBS = {"scale": 1.0, "cycle": None, "asym": 0.94, "lean": 0.0, "arm_cross": 0.0, "knee": 1.0, "offsets": None}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def rx(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def tip(rig, part, m):
    h = rig["sizes"][part][1] / 2.0
    return (m @ np.array([0, -h, 0, 1.0]))[:3]


def leg_of(T, M):
    """a leg's pose against the torso as the rig's FK leg does it: a clean SWING (+ = forward) about the hip, and the
    SLIDE (stage axes: right, up, forward) that puts the leg where it is - the R6 knee"""
    L = np.linalg.inv(T) @ M
    side = "Right Leg" if L[0, 3] > 0 else "Left Leg"
    d = L[:3, :3] @ np.array([0, -1.0, 0])
    th = math.atan2(-d[2], -d[1])
    pred = HIP[side] + rx(th) @ (REST[side] - HIP[side])
    sl = L[:3, 3] - pred
    return math.degrees(th), [float(sl[0]), float(sl[1]), float(-sl[2])]


def learn(path, phases=4):
    """the reference's step as `phases` poses per step at even shares, from the right foot's most forward reach;
    the left step is mirrored onto the right one and the two averaged (asymmetry is a knob, not data)"""
    with open(path, encoding="utf-8") as fh:
        clip = json.load(fh)
    rig = C.load_rig("r6")
    loop = bool(clip.get("loop"))
    allf = C.world_frames(clip, rig)
    n = len(allf) - (1 if loop and len(allf) > 2 else 0)
    fr = allf[:n]
    J = clip["joints"]
    floor = min(min(C.lowest(rig, p, f[p]) for p in ("Right Leg", "Left Leg")) for f in fr)
    ahead = [-(tip(rig, "Right Leg", f["Right Leg"])[2] - f["Torso"][2, 3]) for f in fr]
    c0 = int(np.argmax(ahead))
    fps = float(clip.get("fps") or 30)

    def sample(t):
        """frame t (fractional) by linear blend of the two nearest measured frames' parameters"""
        i0 = int(math.floor(t)) % n
        i1 = (i0 + 1) % n
        a = t - math.floor(t)
        return [measure(i0), measure(i1), a]

    cache = {}

    def measure(i):
        if i in cache:
            return cache[i]
        f = fr[i]
        Rt = C.quat_mat(J["Torso"]["frames"][i][:4])
        body = PF.body_params(Rt)
        head = PF.head_params(Rt @ C.quat_mat(J["Head"]["frames"][i][:4])) if "Head" in J else {"look": [0, 0, 1], "tilt": 0}
        out = {"lean": body["lean"], "turn": body["turn"], "tilt": body["tilt"],
               "head_look": head["look"], "head_tilt": head["tilt"],
               "low": min(C.lowest(rig, p, f[p]) for p in ("Right Leg", "Left Leg")) - floor}
        for side in ("Right", "Left"):
            sw, sl = leg_of(f["Torso"], f[f"{side} Leg"])
            out[f"{side}_leg"] = {"swing": sw, "slide": sl}
            h = tip(rig, f"{side} Arm", f[f"{side} Arm"])
            out[f"{side}_hand"] = [float(h[0]), float(h[1] - floor), float(-h[2])]
        cache[i] = out
        return out

    def blend(a, b, w):
        if isinstance(a, dict):
            return {k: blend(a[k], b[k], w) for k in a}
        if isinstance(a, list):
            return [blend(x, y, w) for x, y in zip(a, b)]
        return a * (1 - w) + b * w

    def at(t):
        m0, m1, w = sample(t)
        return blend(m0, m1, w)

    def mirror(m):
        """the left step seen as a right step: swap sides, negate x, turn and tilt"""
        return {"lean": m["lean"], "turn": -m["turn"], "tilt": -m["tilt"],
                "head_look": [-m["head_look"][0], m["head_look"][1], m["head_look"][2]], "head_tilt": -m["head_tilt"],
                "low": m["low"],
                "Right_leg": {"swing": m["Left_leg"]["swing"], "slide": [-m["Left_leg"]["slide"][0]] + m["Left_leg"]["slide"][1:]},
                "Left_leg": {"swing": m["Right_leg"]["swing"], "slide": [-m["Right_leg"]["slide"][0]] + m["Right_leg"]["slide"][1:]},
                "Right_hand": [-m["Left_hand"][0]] + m["Left_hand"][1:], "Left_hand": [-m["Right_hand"][0]] + m["Right_hand"][1:]}

    table = []
    for q in range(phases):
        a = at(c0 + q * n / (2 * phases))
        b = mirror(at(c0 + n / 2 + q * n / (2 * phases)))
        m = blend(a, b, 0.5)
        # name the step's legs: F = the leg that reached forward at the step's start (right), B = the other
        table.append({"lean": round(m["lean"], 2), "turn": round(m["turn"], 2), "tilt": round(m["tilt"], 2),
                      "head_look": [round(v, 4) for v in m["head_look"]], "head_tilt": round(m["head_tilt"], 2),
                      "low": round(max(0.0, m["low"]), 3),
                      "F_leg": {"swing": round(m["Right_leg"]["swing"], 2), "slide": [round(v, 3) for v in m["Right_leg"]["slide"]]},
                      "B_leg": {"swing": round(m["Left_leg"]["swing"], 2), "slide": [round(v, 3) for v in m["Left_leg"]["slide"]]},
                      "F_hand": [round(v, 3) for v in m["Right_hand"]], "B_hand": [round(v, 3) for v in m["Left_hand"]]})
    return {"from": clip.get("name") or os.path.basename(path), "cycle": round(n / fps * 60.0, 2), "phases": phases,
            "table": table}


def mid(table, key, sub=None):
    vals = [(t[key] if sub is None else t[key][sub]) for t in table]
    return np.mean(np.array(vals, dtype=float), axis=0)


def scaled(v, centre, s):
    return centre + (np.asarray(v, dtype=float) - centre) * s


def step(preset, knobs, f0, F, s):
    """one step from the table: F = the side whose leg reaches forward at its start; s = this step's scale"""
    tb = preset["table"]
    B = "left" if F == "right" else "right"
    m = 1.0 if F == "right" else -1.0                  # the table is a RIGHT step; a left step mirrors x / turn / tilt
    H = float(knobs["cycle"]) / 2.0
    S = float(knobs["scale"]) * s
    # centres the amplitude scales about: the mean pose over the step (both legs, both hands)
    leg_c = (mid(tb, "F_leg", "swing") + mid(tb, "B_leg", "swing")) / 2.0
    lean_c = mid(tb, "lean")
    keys = []
    for q, t in enumerate(tb):
        k = {"f": round(f0 + H * q / len(tb), 3)}
        turn = t["turn"] * S * m
        k["body"] = {"lean": round(lean_c + (t["lean"] - lean_c) * S + float(knobs["lean"]), 2), "turn": round(turn, 2),
                     "tilt": round(t["tilt"] * S * m, 2), "plant": "both", "clear": round(t["low"], 3)}
        if q == 0 and f0 == 0:
            k["body"]["pos"] = [0, 0, 0]
        look = list(t["head_look"])
        k["head"] = {"look": [round(look[0] * m, 4), look[1], look[2]], "tilt": round(t["head_tilt"] * m, 2)}
        for role, side in (("F", F), ("B", B)):
            lg = t[f"{role}_leg"]
            sl = np.array(lg["slide"], dtype=float)
            sl[0] *= m
            if sl[1] > 0.15:                                             # the passing knee drive: up and forward
                sl[1] *= float(knobs["knee"])
            sl[2] = float(scaled(sl[2], 0.4, S))                         # the forward carry scales about its mean
            k[f"{side}_leg"] = {"swing": round(float(scaled(lg["swing"], leg_c, S)), 2), "out": 0, "twist": 0,
                                "slide": [round(float(v), 3) for v in sl]}
            hand = np.array(t[f"{role}_hand"], dtype=float)
            hand[0] *= m
            hand[2] = float(scaled(hand[2], 0.2, S))
            hand[1] = float(scaled(hand[1], 2.3, S))
            if hand[2] > 0.8:                                             # the forward hand: across the body
                hand[0] -= (1.0 if side == "right" else -1.0) * float(knobs["arm_cross"])
            k[f"{side}_arm"] = {"hand": [round(float(v), 3) for v in hand]}
        keys.append(k)
    return keys


def build(kind, name, overrides=None, presets=None):
    presets = presets or load_presets()
    if kind not in presets:
        raise KeyError(kind)
    preset = presets[kind]
    knobs = dict(KNOBS)
    knobs.update(overrides or {})
    if knobs["cycle"] is None:
        knobs["cycle"] = int(round(preset["cycle"] / 2.0)) * 2
    Cn = float(knobs["cycle"])
    keys = step(preset, knobs, 0, "right", 1.0) + step(preset, knobs, Cn / 2.0, "left", float(knobs["asym"]))
    last = copy.deepcopy(keys[0])
    last["f"] = Cn
    keys.append(last)
    spec = {"name": name, "axes": "stage: x right, y up from the floor, z forward (root-relative)", "fps": 60, "loop": True,
            "priority": "Movement", "legs": "fk",
            "cycle": {"kind": kind, "learned_from": preset["from"], "knobs": knobs, "tool": "kit/anim/cycle_r6.py"},
            "note": f"a {kind} cycle rebuilt from the measured key poses of {preset['from']} (kit/anim/cycle_r6.py): legs as swing + slide (the R6 knee), hands placed where the reference puts them, the lowest foot at its measured height",
            "keys": keys}
    if knobs.get("offsets"):
        spec["offsets"] = knobs["offsets"]
    return spec


def load_presets():
    if not os.path.isfile(PRESETS):
        return {}
    with open(PRESETS, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv):
    if argv and argv[0] == "learn":
        if len(argv) < 2 or "--kind" not in argv:
            return emit("fail", "cycle_r6 learn: needs <reference clip.json> --kind <name>", "python kit/anim/cycle_r6.py learn build/animations/CommunityRun.clip.json --kind run")
        kind = argv[argv.index("--kind") + 1]
        phases = int(argv[argv.index("--phases") + 1]) if "--phases" in argv else 4
        p = learn(argv[1], phases)
        presets = load_presets()
        presets[kind] = p
        with open(PRESETS, "w", encoding="utf-8", newline="") as fh:
            json.dump(presets, fh, indent=1)
            fh.write("\n")
        return emit("pass", f"cycle_r6 learn {kind}: {phases} poses per step from {p['from']} (cycle {p['cycle']} frames) -> {PRESETS}",
                    f"lune run kit anim new <Name> --cycle {kind}")
    presets = load_presets()
    if not argv or argv[0] not in presets or "--as" not in argv:
        return emit("fail", f"cycle_r6: needs <{'|'.join(sorted(presets)) or 'learn first'}> --as <Name> [--params '{{...}}']",
                    "lune run kit anim new RigRun3 --cycle run")
    kind, name = argv[0], argv[argv.index("--as") + 1]
    overrides = json.loads(argv[argv.index("--params") + 1]) if "--params" in argv else {}
    unknown = [k for k in overrides if k not in KNOBS]
    if unknown:
        return emit("fail", f"cycle_r6: unknown knob(s) {unknown}", f"one of: {sorted(KNOBS)}")
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join("assets", "animations", f"{name}.pose.json")
    spec = build(kind, name, overrides, presets)
    with open(out, "w", encoding="utf-8", newline="") as fh:
        json.dump(spec, fh, indent=1)
        fh.write("\n")
    return emit("pass", f"cycle_r6 {name}: a {kind} cycle ({spec['cycle']['knobs']['cycle']} frames at 60 fps) from {spec['cycle']['learned_from']} -> {out}",
                f"lune run kit anim {name} && lune run kit anim profile {name} --vs {spec['cycle']['learned_from']} && lune run kit anim sil {name} --vs {spec['cycle']['learned_from']}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
