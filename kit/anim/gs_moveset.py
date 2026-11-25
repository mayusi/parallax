"""gs_moveset.py — a GREATSWORD moveset authored from scratch on the owner's R6 rig, from what the owner's LOVED swings
measured (2026-10-12, assets/animations/library/owner_picks.json; Sword Fox Slash 1-4, BEST R6 Slash 1-2, HQ DownSlam):

- the weight is in the FOLLOW-THROUGH, not the wind-up: loved wind-ups 0-0.2 s, recoveries 0.4-1.25 s; the one long
  wind-up in the set (a mace 'Charged Swing', 1.0 s) was rated BAD
- the torso turns BIG: 109-143 deg per swing (the old "R6 has no waist, <= 55 deg" rule came from an AI judge and is
  wrong for the owner); the legs barely move; both hands stay on the hilt (0.4-0.9 studs apart) and swing as one unit
- peak hand speed 35-52 studs/s; the swing ends HELD past the target and settles slowly

    python kit/anim/gs_moveset.py [--only GsM1,GsM2] -> assets/animations/<Name>.pose.json (then `kit anim <Name>`)

Poses are torso-relative (hand + blade in the torso's own frame, so a 130 deg turn keeps the sword right); every move
starts on the previous move's last pose (the combo flows) and the head keeps its eyes on the target (forward)."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import strike_r6 as S  # noqa: E402  (torso_frame / to_world, GS_SWORD)

SWORD = dict(S.GS_SWORD)
FEET = {"right_foot": {"at": [0.85, -0.55], "lift": 0, "turn": 35}, "left_foot": {"at": [-0.55, 0.75], "lift": 0, "turn": 5}}


def P(pos, lean, turn, tilt, hand, blade):
    return {"body": {"pos": list(pos), "lean": lean, "turn": turn, "tilt": tilt}, "hand": hand, "blade": blade}


GUARD = P((0, -0.45, 0), 8, 20, -3, (-0.1, -0.55, 1.45), (0.0, 0.45, 0.9))
# a move = a list of (frame, pose, ease into this key, extra key fields); frame 0 is the start pose
MOVES = {
    # M1: a right-high DIAGONAL down to the left - snap up over the right shoulder (0.12 s), hips lead the swing, the
    # torso turns 132 deg, the blade drives through low left and HOLDS there (the weight), the front foot steps in
    # M1 v2 (2026-10-12, after the owner's 3/10): MY poses, spaced by the LEARNED attack rules (kit/anim/craft.py on the
    # owner's 74 loved / 50 bad attacks): snap to the wind-up and HOLD it (loved: ~60% of an attack is held, ~2 holds),
    # burst through the strike (accel ~0.08 s, decel ~0.13 s), the front foot LANDS ON the strike frame (step_t ~0),
    # the stance widens 1.2 -> ~2.4 studs, the hips drop ~0.35 and the weight goes over the front foot (+0.34), lean
    # ~40 deg (loved 43, bad 19), the torso turns ~175 deg (loved 174, bad 90); a long settling hold on the follow
    "GsM1": {"event": 15, "moves": [
        (0, GUARD, "sine_inout", {}),
        (6, P((0, -0.42, -0.10), -4, 80, -8, (0.75, 1.4, 0.3), (0.3, 0.55, -0.8)), "sine_inout", {}),
        (10, P((0, -0.44, -0.12), -6, 84, -9, (0.78, 1.45, 0.25), (0.32, 0.5, -0.82)), "sine_inout",
         {"left_foot": {"at": [-0.65, 1.1], "lift": 0.4, "turn": 0}}),
        (15, P((-0.25, -0.70, 0.78), 24, -5, 3, (0.1, 0.1, 1.85), (-0.55, -0.15, 0.82)), "quad_in",
         {"left_foot": {"at": [-1.0, 1.45], "lift": 0, "turn": -35}, "right_foot": {"at": [0.9, -0.55], "lift": 0.15, "turn": 10}}),
        (19, "MID", "bezier", {"left_foot": {"at": [-1.3, 1.1], "lift": 0.3, "turn": -55}}),
        (25, P((-0.75, -0.80, 0.30), 30, -100, 6, (-0.7, -0.35, 1.55), (-0.25, 0.48, 0.84)), "bezier",
         {"left_foot": {"at": [-1.55, 0.75], "lift": 0, "turn": -75}, "right_foot": {"at": [0.75, -0.05], "lift": 0, "turn": -55}}),
        # HELD follow-through (A/B 2026-10-12: the bootstrap taste model prefers the held finish 0.80 (0.74-0.90) over a
        # continuous settle 0.61 (0.44-0.73); the loved "keeps moving" spacing did NOT separate loved from bad attacks)
        (51, P((-0.8, -0.78, 0.28), 28, -96, 5, (-0.65, -0.3, 1.58), (-0.22, 0.46, 0.86)), "sine_inout", {}),
    ]},
    # M2 (pipeline v2): from M1's finish, a REVERSE sweep left -> right: coil further left and HOLD, burst through a
    # centre-front hit with the RIGHT foot landing on it (weight over it), the blade carries far past to the right,
    # the feet re-plant around the turn, a long settling hold
    "GsM2": {"event": 16, "moves": [
        (8, P((-0.8, -0.74, 0.20), 18, -122, 5, (-1.0, 0.45, 0.25), (-0.3, 0.45, -0.85)), "sine_inout", {}),
        (11, P((-0.82, -0.75, 0.18), 17, -126, 5, (-1.02, 0.48, 0.22), (-0.32, 0.46, -0.84)), "sine_inout",
         {"right_foot": {"at": [0.4, 0.5], "lift": 0.35, "turn": 0}}),
        (16, P((-0.3, -0.70, 0.95), 24, -20, -3, (0.0, 0.1, 1.85), (0.6, 0.05, 0.8)), "quad_in",
         {"right_foot": {"at": [0.55, 1.5], "lift": 0, "turn": 20}}),
        (20, "MID", "bezier", {"left_foot": {"at": [-1.0, 0.6], "lift": 0.25, "turn": 30}}),
        (26, P((0.2, -0.80, 0.90), 30, 72, -6, (0.7, -0.35, 1.55), (0.25, 0.48, 0.84)), "bezier",
         {"left_foot": {"at": [-0.6, 0.2], "lift": 0, "turn": 60}}),
        (52, P((0.22, -0.78, 0.88), 28, 68, -5, (0.65, -0.3, 1.58), (0.22, 0.46, 0.86)), "sine_inout", {}),
    ]},
    # M3 (pipeline v2), the FINISHER: from M2's finish, heave the blade up over the head and HOLD (leaning back), chop
    # down the centre into a deep lunge - the left foot lands ON the hit, the hips drop - the tip near the ground, a
    # long heavy hold, then haul it back up into the guard
    "GsM3": {"event": 19, "moves": None},
    # IDLE (learned idle rules: a slow even breath - wind 27-52% of the cycle, symmetric in / out; arms a little out):
    # the two-handed guard breathing over 3 s, the chest rising, the stance settling, the heavy blade's tip sagging and
    # being lifted with the breath, a short hold at the top; loops on itself
    # IDLE v2: the greatsword hangs in the RIGHT hand at the side, point down and angled out (readable from the gameplay
    # camera; a sword resting in front hides behind the body), the left arm relaxed - both arms low like the loved
    # idles (arm_out 22-63 deg); a slow even breath, the tip lifting a little with it, a short hold at the top
    "GsGuardIdle": {"event": None, "loop": True, "chain": False, "resting": True,
                    "left": {"swing": 10, "out": 18, "twist": 0, "slide": [0, 0, 0]}, "moves": [
        (0, P((0, -0.30, 0), 3, 8, -2, (1.3, -1.05, 0.7), (0.52, -0.33, 0.79)), "sine_inout", {}),
        (68, P((0, -0.26, -0.02), 1, 9, -1, (1.3, -0.98, 0.69), (0.53, -0.29, 0.8)), "sine_inout", {}),
        (86, P((0, -0.26, -0.02), 1, 9, -1, (1.3, -0.97, 0.69), (0.53, -0.28, 0.8)), "sine_inout", {}),
        (150, P((0, -0.32, 0.01), 4, 7, -3, (1.3, -1.02, 0.71), (0.52, -0.33, 0.79)), "sine_inout", {}),
        (180, P((0, -0.30, 0), 3, 8, -2, (1.3, -1.05, 0.7), (0.52, -0.33, 0.79)), "sine_inout", {}),
    ]},
}

M3_X0 = [30, 20, -43.43, 17.59, 48, 0.61, -0.08, 2.04]   # tuned 2026-10-12 (kit/anim/tune.py: rules + taste, judged polished)


def m3_moves(x=M3_X0):
    """M3, the overhead FINISHER (my design), parameterised for kit/anim/tune.py: x = wind turn, hit turn, follow turn,
    hit lean, follow lean, hit hand height, follow hand height, the forward drive at the hit"""
    wt, ht, ft, hl, fl, hy, fy, hz = x
    return [
        (9, P((0.1, -0.55, 0.55), -10, wt, -4, (0.2, 2.05, 0.1), (0.0, 0.3, -0.95)), "sine_inout", {}),
        (14, P((0.1, -0.54, 0.52), -12, wt + 5, -5, (0.22, 2.1, 0.05), (0.0, 0.28, -0.96)), "sine_inout",
         {"left_foot": {"at": [-0.6, 1.3], "lift": 0.4, "turn": 0}}),
        (19, P((-0.15, -0.80, hz), hl, ht, 3, (0.0, hy, 1.85), (0.0, 0.12, 0.99)), "quad_in",
         {"left_foot": {"at": [-0.7, 2.0], "lift": 0, "turn": -5}}),
        (23, "MID", "bezier", {}),
        (29, P((-0.2, -0.95, hz - 0.15), fl, ft, 5, (-0.1, fy, 1.75), (-0.2, 0.72, 0.66)), "bezier", {}),
        (60, "MID", "quad_out", {}),
        (84, GUARD, "sine_inout", {"left_foot": dict(FEET["left_foot"]), "right_foot": dict(FEET["right_foot"])}),
    ]


MOVES["GsM3"]["moves"] = m3_moves()

ORDER = ["GsM1", "GsM2", "GsM3", "GsGuardIdle"]


def rot(body, v):
    Rm, _ = S.torso_frame(body)
    return [round(sum(Rm[i][j] * v[j] for j in range(3)), 4) for i in range(3)]


def key(f, pose, ease, extra):
    b = dict(pose["body"])
    yaw = math.radians(0.25 * b["turn"])                     # the eyes stay on the target: the head turns a little
    k = {"f": f, "ease": ease, "body": b,
         "head": {"look": [round(math.sin(yaw), 4), -0.08 - 0.004 * max(b["lean"], 0), round(math.cos(yaw), 4)]},
         "right_arm": {"hand": S.to_world(b, pose["hand"]), "blade": rot(b, pose["blade"])}}
    k.update(extra)
    return k


def build():
    out, last, feet = {}, None, dict(FEET)
    for name in ORDER:
        mv = MOVES[name]
        steps = mv["moves"] if mv["moves"][0][0] == 0 else [(0, last, "sine_inout", {})] + mv["moves"]
        if mv.get("chain") is False:
            feet = dict(FEET)
        steps = [list(st) for st in steps]
        for i, st in enumerate(steps):                       # "MID": halfway between the neighbouring poses
            if st[1] == "MID":
                A, Bp = steps[i - 1][1], steps[i + 1][1]
                mix = lambda x, y: [round((float(u) + float(v)) / 2, 4) for u, v in zip(x, y)]
                st[1] = {"body": {kk: (mix(A["body"][kk], Bp["body"][kk]) if isinstance(A["body"][kk], list)
                                       else round((A["body"][kk] + Bp["body"][kk]) / 2, 3)) for kk in A["body"]},
                         "hand": mix(A["hand"], Bp["hand"]), "blade": mix(A["blade"], Bp["blade"])}
        keys = []
        for i, (f, pose, ease, extra) in enumerate(steps):
            k = key(f, pose, ease, extra)
            if i == 0:
                k["left_arm"] = dict(mv["left"]) if mv.get("left") else "hilt"
                k.update({kk: dict(v) for kk, v in feet.items()})
            keys.append(k)
            for kk in ("left_foot", "right_foot"):
                if kk in extra:
                    feet[kk] = dict(extra[kk])
        # a step's ease shapes the segment INTO it; the rig (Blender) eases the segment LEAVING a key - so each key
        # carries the NEXT step's ease (found 2026-10-12: the strike's quad_in landed after the hit and stopped the swing)
        for i in range(len(keys) - 1):
            keys[i]["ease"] = steps[i + 1][2]
        keys[-1]["ease"] = "sine_inout"
        if not mv.get("loop"):
            keys.append(dict(keys[-1], f=steps[-1][0] + 4))
        out[name] = {"name": name, "axes": "stage: x right, y up from the floor, z forward (the character stands at the origin facing +z)",
                     "note": "AUTHORED from scratch (kit/anim/gs_moveset.py) on the owner's measured loved swings: fast wind-up, big torso turn, held follow-through, two hands on the hilt",
                     "fps": 60, "loop": bool(mv.get("loop")), "priority": "Idle" if mv.get("loop") else "Action", "sword": dict(SWORD),
                     "events": [{"name": "Hit", "f": mv["event"]}] if mv.get("event") is not None else [],
                     "offsets": {"head": 3, "arms": 2}, "keys": keys}
        if mv.get("chain") is not False:
            last = steps[-1][1]
    return out


def blade_check(spec, game_yaw=0.0, resting=False):
    """READABILITY from the GAMEPLAY camera (Roblox's camera sits behind and above the player, looking along the
    character's starting facing +z): a blade whose tip stays inside the body's column (laterally within 1.1 studs of
    the torso, below the head) is hidden by the body - the owner sees no sword. M3's held chop hid it that way."""
    bad = []
    hits = {int(e["f"]) for e in spec.get("events") or []}
    for k in spec["keys"]:
        b = k["body"]
        _, c = S.torso_frame(b)
        hand = k["right_arm"]["hand"]
        d = k["right_arm"]["blade"]
        n = math.sqrt(sum(v * v for v in d)) or 1.0
        tip = [hand[i] + 4.0 * d[i] / n for i in range(3)]
        lateral = abs(tip[0] - c[0])                         # seen from behind: left / right of the body column
        above = tip[1] - (c[1] + 1.6)                        # above the head
        if k["f"] in hits:
            continue                                         # the hit frame: the blade passes in front (a blur)
        if tip[1] < (-0.05 if resting else 0.15):
            bad.append(f"f{k['f']} tip {tip[1]:.1f} studs: INTO THE FLOOR")
        elif lateral < 1.1 and above < 0:
            bad.append(f"f{k['f']} (tip {lateral:.1f} studs off the body's column, {-above:.1f} under the head)")
    return bad


def main(argv):
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
    made = []
    for name, spec in build().items():
        if only and name not in only:
            continue
        path = os.path.join("assets", "animations", f"{name}.pose.json")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            json.dump(spec, fh, indent=1)
            fh.write(chr(10))
        made.append(name)
        hidden = blade_check(spec, resting=bool(MOVES[name].get("resting")))
        if hidden:
            print(f"  {name}: BLADE HIDDEN at " + "; ".join(hidden), file=sys.stderr)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"gs_moveset: {', '.join(made)} -> assets/animations/*.pose.json",
                      "next_action": " && ".join(f"lune run kit anim {n}" for n in made)}))
    return 0


if __name__ == "__main__" and "--run" not in sys.argv:
    sys.exit(main(sys.argv[1:]))


def run_spec(name="GsRun", cycle=36, x=(50, 52, 78, 62, 0.85, 0.22)):
    """the greatsword RUN, authored to the LEARNED run profile (kit/anim/craft.py on the owner's 10 loved / 18 bad runs):
    a ~0.6 s cycle, lean ~28 deg (the rejected RigRun leaned 12-16), weight forward, hip bob ~0.18, the free arm
    snapping forward and swinging PAST (overshoot ~1.1, asym ~2), a flight phase; FK legs (the owner's runs) with the
    R6 knee = the leg sliding up; the greatsword trails low behind in the right hand (readable from behind)."""
    h = cycle // 2

    def leg(swing, up=0.0, fwd=0.0):
        return {"swing": swing, "out": 3, "twist": 0, "slide": [0, round(up, 3), round(fwd, 3)]}

    def arm(swing, out=12, up=0.0, fwd=0.0):
        return {"swing": swing, "out": out, "twist": 0, "slide": [0, round(up, 3), round(fwd, 3)]}

    # one step (right foot leads) then the mirror; (frame, lean, turn, plant, pos_y, right_leg, left_leg, left_arm, sword hand dz)
    half = [
        (0, 28, 10, "right", 0.0, leg(x[0], 0.0, 0.12), leg(-x[1], 0.2, -0.05), arm(x[2] * 0.4, 12, -0.1, 0.1), x[5]),
        (4, 31, 8, "right", -0.07, leg(x[0] * 0.56, 0.0, 0.06), leg(-x[1] * 0.5, 0.38, 0.0), arm(x[2], 12, -0.28, 0.28), x[5] * 0.45),
        (9, 30, 0, "right", -0.04, leg(-6, 0.0, 0.0), leg(x[0] * 0.52, 0.45, 0.18), arm(x[3], 12, -0.2, 0.2), 0.0),
        (14, 27, -6, None, 0.13, leg(-x[1] * 0.85, 0.14, -0.05), leg(x[0] * 1.04, 0.22, 0.14), arm(x[3] * 0.16, 13), -x[5] * 0.7),
    ]
    keys = []
    for side in (0, 1):
        for f, lean, turn, plant, py, rl, ll, la, dz in half:
            fr = f + side * h
            if side:                                          # the mirror step: legs swap, the free arm swings back
                rl, ll = ll, rl
                la = arm(-la["swing"] * x[4], la["out"], 0.0, 0.0)
                turn, plant, dz = -turn, {"right": "left", None: None}[plant], -dz
            body = {"pos": [0, py, 0.25], "lean": lean, "turn": turn, "tilt": -2 if side == 0 else 2}
            if plant:
                body["plant"] = plant
            hand = S.to_world({"pos": [0, py - 0.45, 0.25], "lean": lean, "turn": turn}, (0.95, -0.5, -0.45 + dz))
            blade = rot({"lean": lean, "turn": turn}, (0.3, -0.55, -0.78))   # back and DOWN: a forward lean tilts torso-back UP
            keys.append({"f": fr, "ease": "bezier", "body": body, "head": {"look": [0, -0.05, 1]},
                         "right_leg": rl, "left_leg": ll, "left_arm": la,
                         "right_arm": {"hand": hand, "blade": blade}})
    keys.append(dict(keys[0], f=cycle))
    return {"name": name, "axes": "stage: x right, y up from the floor, z forward (root-relative)", "fps": 60, "loop": True,
            "priority": "Movement", "legs": "fk", "sword": dict(SWORD), "events": [], "keys": keys,
            "note": "AUTHORED (kit/anim/gs_moveset.py run_spec) to the learned run profile: lean ~28, weight forward, flight, the free arm overshooting; the greatsword trailing low behind"}


if __name__ == "__main__" and "--run" in sys.argv:
    spec = run_spec()
    hidden = blade_check(spec)
    if hidden:
        print("  GsRun: BLADE " + "; ".join(hidden), file=sys.stderr)
    with open(os.path.join("assets", "animations", "GsRun.pose.json"), "w", encoding="utf-8", newline="") as fh:
        json.dump(spec, fh, indent=1)
        fh.write(chr(10))
    print(json.dumps({"schema": 1, "status": "pass", "summary": "gs_moveset: GsRun -> assets/animations/GsRun.pose.json", "next_action": "lune run kit anim GsRun"}))
