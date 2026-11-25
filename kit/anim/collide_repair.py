"""collide_repair.py — MOVING IT CLEAR (the owner's limitations list 2026-11-15, A-R05 / AN-24: "... collision REPAIR
was not found"). kit/anim/collide.py names what passes through the body and at which frame; this moves it out, by the
least it can, inside bounds, and says what it did - or refuses, named, and leaves the clip as it was.

    {"op": "clear"}                                   in a `kit anim derive` recipe (kit/anim/derive.py)
    {"op": "clear", "max_deg": 30, "max_slide": 0.45, "blade_deg": 25}
    python kit/anim/collide_repair.py <clip.json> [--out <file>]     the same on a clip file (no --out: what it would do)

WHAT IT MOVES, one fault at a time, the worst first, judged by collide.py's own swept reading after every move:
  a hand   the arm is turned about its shoulder, and - an R6 arm slides - slid outward, the cheapest of both that
           takes the hand out (cost = degrees + 60 x studs), eased in and out over EASE frames either side.
  a foot   the leg is turned about its hip the same way (a leg does not slide here: the feet rule owns that).
  a blade  held in no hand (thrown, sheathed): turned about its grip point, eased the same way.
  a HELD blade and its arms TOGETHER (the owner's V3 list, anim stage C.1: the repair refused every weapon a hand held
           and every arm that held one - 38 of the 65 refusals on the 82 frozen colliding clips): the blade is turned
           about the point between the hands that hold it (one hand: the point it is on), the least that takes it out,
           and those hands are put back on it (kit/anim/grip_solve.py, only on the frames the eased move touches); a
           holding ARM whose hand is in the body is moved as an arm is and carries the weapon with its hand, the
           other hand of a two-handed grip put back on it. Taken only when no hand ends off the hilt, no arm reads
           deeper anywhere, and the blade stays within blade_deg.
WHEN THOSE ARE REFUSED (LIMITATIONS_FIXES_V4 4.4 / 13.4.2, "torso counter-tilt + root step-pivot"):
  the step  a foot in the OTHER leg: both legs turned apart about their hips, mirrored (neither foot standing).
  a counter-tilt  the TORSO (the head on it) turned away about the hips - leaned, twisted, or tilted sideways about
           the standing leg's hip (the body pivots over it) - by at most tilt_deg (20), while every hand and foot
           STAYS: each arm re-aimed from its moved shoulder onto where its hand was and slid the difference (at most
           max_slide), each leg from its moved hip onto where its foot was (a standing foot may move FOOT_DRIFT along
           it). The weapon is not moved. Alone, or as a start the refused move then finishes - judged whole: the fault
           under its bar by room, no reading anywhere in the body worse, no snap, the hands on the weapon kept.
  Measured on read-only copies of the 44 non-Sample-Game clips of the 82 frozen colliding ones: 9 -> 15 repaired,
  35 -> 29 refused (79.5% -> 65.9%); what is left is 0.37 - 0.50 studs in (a blade or a limb through the middle of
  the torso or head) - wider bounds (tilt 35, blade 40) repaired ONE more. A pose that far in is the move's to change.
A move is judged on the check's own SWEPT reading of the frames it touches (a fault that lives between two frames is
seen): it is taken when the fault is under its bar BY ROOM (ROOM studs: a repair that stops on the bar is one
frame's rounding from failing again) and no other reading of the thing moved - the other blocks, the other arm, the
weapon - got worse than it was or than its own bar less the room. Tried: turns about the Torso's three axes.

WHAT IT REFUSES (the clip is left untouched and the reason is the failure):
  a held weapon or a holding arm whose coupled move (above) cannot clear it within its bounds, or that would leave a
           hand off the hilt or an arm deeper in the body; a hand that was on the weapon and is off it after the
           moves;
  a leg whose foot STANDS ON THE FLOOR at any frame the move touches (turning it would drag the foot);
  the left arm of a clip with a second weapon (that weapon's track is made from the move's keys);
  a fault that needs more than its bounds (max_deg, max_slide, blade_deg) - a pose that far in is wrong, not grazing.
           Moves near one another add up: the bound is on what any one frame ends up moved by;
  (a STEPPED clip is repaired on its smooth motion - kit/anim/clip.destep - and stepped again on the same windows,
           each hold the repaired sample: it was refused before);
  a clip that still fails after PASSES moves.
A declared contact is not a fault and is not moved (collide.py leaves it out). A looping clip's move wraps round its
seam. The weapon's own joint track (kit/anim/grip.py: it is relative to the right arm) is made again after a blade
is turned AND after the right arm is moved. A prop's clip is given back as it is.
NOT DONE: the swing's design is not consulted - a blade turned 20 degrees at the Hit still passes this check and may
miss its drawn path or its contact: those gates run after it in the build and say so."""
import copy
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

MAX_DEG = 30.0       # degrees an arm or a leg may be turned about its joint
MAX_SLIDE = 0.45     # studs an arm may be slid out of its shoulder
BLADE_DEG = 25.0     # degrees a one-handed blade may be turned about its grip
STEP_DEG = 3.0
SLIDES = (0.0, 0.15, 0.3, 0.45, 0.6)
EASE = 6             # frames either side of the fault's frame the move is eased over
PASSES = 24          # moves at most
ROOM = 0.1           # studs under its bar a repaired reading must be
SNAP_GROW = 8.0      # degrees a coupled move may add to an arm's turn between two frames (the hands put back on a turned
#                      blade can flip an arm's roll at the edge of the move: two of the first 18 coupled repairs on the
#                      frozen clips snapped an arm 16 and 100 degrees in a frame - the build's pop gate failed them)
TILT_DEG = 20.0      # degrees the torso may be counter-tilted away from what is in it (the hands and the feet kept)
FOOT_DRIFT = 0.05    # studs a foot standing on the floor may move along its leg under a counter-tilt
PARTIAL = 0.02       # studs a tilt must take out of a fault it cannot clear to be tried with the refused move
ARMS = ("Right Arm", "Left Arm")
LEGS = ("Right Leg", "Left Leg")
BODY_PARTS = ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _rot(axis, rad):
    """Rodrigues: the 3x3 turn of `rad` about the unit `axis`"""
    x, y, z = axis
    c, s = math.cos(rad), math.sin(rad)
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]], float)
    return np.eye(3) * c + s * k + (1 - c) * np.outer(axis, axis)


def _weights(n, f, loop):
    """{frame: share of the move} eased over EASE frames either side of f; a loop wraps round its seam"""
    out = {}
    period = n - 1 if loop and n > 2 else None
    for o in range(-EASE, EASE + 1):
        w = 0.5 * (1.0 + math.cos(math.pi * o / (EASE + 1)))
        k = f + o
        if period:
            k %= period
        elif not 0 <= k < n:
            continue
        out[k] = max(out.get(k, 0.0), w)
    if period and 0 in out:
        out[n - 1] = out[0]                                  # (the seam's two frames are one pose)
    return out


def _kind(a, b):
    """the bar a pair is held to (kit/anim/collide.py): the weapon, a hand in the torso / the other arm / else, a foot"""
    if a == "weapon":
        return "weapon"
    if a in ARMS:
        return "hand_arm" if b in ARMS else "hand_torso" if b == "Torso" else "hand"
    return "foot"


def _holders(clip, rig, i):
    """the arms that hold the weapon at frame i -> {arm: where along the weapon's line its hand is} (collide.py's own
    rule: the hand within HOLD of the line, anywhere from HANDLE behind the grip point to the tip)"""
    import clip as C
    import collide as K
    sw = clip.get("sword") if isinstance(clip.get("sword"), dict) else {}
    if not sw.get("tip") or not sw.get("grip_path") or i >= len(sw["tip"]) or i >= len(sw["grip_path"]):
        return {}
    g, t = np.array(sw["grip_path"][i], float), np.array(sw["tip"][i], float)
    length = float(np.linalg.norm(t - g))
    if length < 1e-9:
        return {}
    ax = (t - g) / length
    W = C.fk(rig, C.character_transforms(clip, rig, i))
    held = {}
    for arm in ARMS:
        h = (W[arm] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]
        at = float(np.clip(np.dot(h - g, ax), -K.HANDLE, length))
        if float(np.linalg.norm(h - (g + at * ax))) <= K.HOLD:
            held[arm] = at
    return held


def _span(clip, f):
    return _weights(len(clip["times"]), f, bool(clip.get("loop")))


def _pairs(clip, f):
    """collide.py's own SWEPT reading of the frames a move at f touches -> {"a|b": depth}. A move is judged on this,
    not on frame f alone: a fault that lives between two frames is seen, and so is what the eased move does to the
    neighbours"""
    import collide as K
    n = len(clip["times"])
    lo, hi = max(0, f - EASE - 1), min(n - 1, f + EASE + 1)
    cut = {k: v for k, v in clip.items() if k not in ("joints", "times", "sword", "root", "stepped", "grip", "grip_left")}
    cut["joints"] = {j: {"frames": t["frames"][lo:hi + 1]} for j, t in clip["joints"].items() if t.get("frames")}
    cut["times"] = clip["times"][lo:hi + 1]
    if isinstance(clip.get("root"), list) and len(clip["root"]) == n:
        cut["root"] = clip["root"][lo:hi + 1]
    sw = clip.get("sword")
    if isinstance(sw, dict):
        cut["sword"] = {k: (v[lo:hi + 1] if isinstance(v, list) and len(v) == n else v) for k, v in sw.items()}
    return K.read(cut)["pairs"]


def _fine(before, after, mover, block):
    """is a trial move good? The fault's own pair under its bar BY ROOM; every other pair of the thing moved no worse
    than it was, or under its own bar by room"""
    import collide as K
    for key, depth in after.items():
        a, b = key.split("|")
        if mover not in (a, b):
            continue
        bar = K.BARS[_kind(a, b)]
        top = bar - ROOM if (a == mover and b == block) else max(before.get(key, 0.0), bar - ROOM)
        if depth > top + 1e-9:
            return False
    return True


def _turn_limb(clip, limb, f, ang, sl, ax):
    import derive as D
    F = D.frames_of(clip, limb)
    side = 1.0 if limb.startswith("Right") else -1.0
    out = [np.array(x, float) for x in F]
    for k, w in _span(clip, f).items():
        dq = D.qexp(np.asarray(ax, float) * math.radians(ang * w) / 2)
        out[k] = np.concatenate([D.qmul(dq, F[k][:4]), F[k][4:7] + np.array([side * sl * w, 0, 0])])
    D.set_frames(clip, limb, out)


def _move_limb(clip, rig, limb, block, f, max_deg, max_slide):
    """the cheapest turn (+ slide, an arm) of `limb` about its joint that takes its end out of `block` round frame f,
    written into the clip eased over its neighbours -> what was done; ValueError when its bounds do not reach"""
    before = _pairs(clip, f)
    was = before.get(f"{limb}|{block}", 0.0)
    cands = []
    ang = STEP_DEG
    while ang <= max_deg + 1e-9:
        for sl in (SLIDES if limb in ARMS else (0.0,)):
            if sl > max_slide + 1e-9:
                continue
            # (the Torso's own axes: forward / back, sideways, and about the vertical - an arm that points along one
            # of them only rolls about it, so all three are tried)
            for ax in ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
                cands.append((ang + 60 * sl, ang, sl, ax))
        ang += STEP_DEG
    if limb in ARMS:
        cands += [(60 * sl, 0.0, sl, (0, 0, 1)) for sl in SLIDES if 0 < sl <= max_slide + 1e-9]
    for _cost, ang, sl, ax in sorted(cands, key=lambda c: c[0]):
        trial = dict(clip, joints=dict(clip["joints"]))
        trial["joints"][limb] = {"frames": [list(x) for x in clip["joints"][limb]["frames"]]}
        _turn_limb(trial, limb, f, ang, sl, ax)
        if _fine(before, _pairs(trial, f), limb, block):
            _turn_limb(clip, limb, f, ang, sl, ax)
            return {"what": limb, "out_of": block, "frame": f, "deg": ang, "slide": sl, "was": round(was, 3)}
    raise ValueError(f"the {limb} is {was:.2f} studs into the {block} round frame {f} and no turn of {max_deg:g} "
                     f"degrees{' with a slide of ' + format(max_slide, 'g') + ' studs' if limb in ARMS else ''} takes it "
                     "out: a pose that far in is the move's to change")


def _turn_blade(clip, rig, f, ang, ax):
    """the blade turned about the point of its line the holding hand is on (no holder: its grip point), eased"""
    sw = clip["sword"]
    for k, w in _span(clip, f).items():
        R = _rot(ax, math.radians(ang * w))
        gk, tk = np.array(sw["grip_path"][k], float), np.array(sw["tip"][k], float)
        at = next(iter(_holders(clip, rig, k).values()), 0.0)
        pivot = gk + at * (tk - gk) / max(float(np.linalg.norm(tk - gk)), 1e-9)
        g2, t2 = pivot + R @ (gk - pivot), pivot + R @ (tk - pivot)
        sw["grip_path"][k], sw["tip"][k] = g2.tolist(), t2.tolist()
        if isinstance(sw.get("edge"), list) and k < len(sw["edge"]):
            sw["edge"][k] = (R @ np.array(sw["edge"][k], float)).tolist()


def _move_blade(clip, rig, block, f, blade_deg):
    """a one-handed blade turned about the point its hand is on, by the least that takes it out of `block` round f"""
    import clip as C
    sw = clip["sword"]
    g, t = np.array(sw["grip_path"][f], float), np.array(sw["tip"][f], float)
    d = t - g
    before = _pairs(clip, f)
    was = before.get(f"weapon|{block}", 0.0)
    to = C.fk(rig, C.character_transforms(clip, rig, f))[block][:3, 3] - g
    n1 = np.cross(d, to)
    if float(np.linalg.norm(n1)) < 1e-6:                     # (the blade points at the block's middle: any side will do)
        n1 = np.cross(d, np.array([0.0, 1.0, 0.0]) if abs(d[1]) < 0.9 * np.linalg.norm(d) else np.array([1.0, 0.0, 0.0]))
    n1 = n1 / np.linalg.norm(n1)
    n2 = np.cross(d, n1)
    n2 = n2 / np.linalg.norm(n2)
    ang = STEP_DEG
    while ang <= blade_deg + 1e-9:
        for ax in (n1, -n1, n2, -n2):
            trial = dict(clip, sword={k: ([list(x) for x in v] if isinstance(v, list) else v) for k, v in sw.items()})
            _turn_blade(trial, rig, f, ang, ax)
            if _fine(before, _pairs(trial, f), "weapon", block):
                _turn_blade(clip, rig, f, ang, ax)
                return {"what": "weapon", "out_of": block, "frame": f, "deg": ang, "slide": 0.0, "was": round(was, 3)}
        ang += STEP_DEG
    raise ValueError(f"the weapon is {was:.2f} studs into the {block} round frame {f} and no turn of {blade_deg:g} degrees "
                     "about the hand that holds it takes it out: the swing's line is the move's to change")


def _sides(held):
    """the grip_solve hands of the arms that hold: two | right | left"""
    return "two" if len(held) > 1 else ("right" if "Right Arm" in held else "left")


def _hold_again(trial, clip, rig, f, said):
    """the hands that held the weapon put back on it (grip_solve), on the frames the eased move at f touches only -
    a hand that is off the weapon elsewhere in the clip (let go on purpose) is left as it was -> the trial; ValueError
    from the solve"""
    import grip_solve as GS
    given = dict(trial, hands=said)
    sw = trial.get("sword") or {}
    n = len(trial["times"])
    if not (isinstance(sw.get("edge"), list) and len(sw["edge"]) == n) and not isinstance(trial.get("grip"), list):
        # (an older clip keeps no edge track and no weapon joint: the solve only needs one to follow a moved arm - a
        # stand-in at right angles to the blade places the hands, and is never written into the clip)
        edges = []
        for gk, tk in zip(sw["grip_path"], sw["tip"]):
            d = np.array(tk, float) - np.array(gk, float)
            e = np.cross(d, [0.0, 1.0, 0.0]) if abs(d[1]) < 0.9 * max(float(np.linalg.norm(d)), 1e-9) else np.cross(d, [1.0, 0.0, 0.0])
            edges.append((e / max(float(np.linalg.norm(e)), 1e-9)).tolist())
        given["sword"] = {**sw, "edge": edges}
    solved, _ = GS.solve(given, hands=said)
    span = _span(trial, f)
    for arm in (("Right Arm", "Left Arm") if said == "two" else (GS.ARM[said],)):
        F = [list(x) for x in trial["joints"][arm]["frames"]]
        for k in span:
            F[k] = list(solved["joints"][arm]["frames"][k])
        trial["joints"][arm] = {**trial["joints"][arm], "frames": F}
    if "grip" in trial:
        _regrip(trial)
    return trial


def _turn_held_blade(clip, rig, f, ang, ax, pivot_at, arm=None):
    """the blade turned, eased, about a point of its line: `arm`'s hand where that hand is on it at each frame (a
    hand slides along a hilt from frame to frame), else the holding hands' middle at each frame, else `pivot_at`
    studs from its grip point"""
    sw = clip["sword"]
    for k, w in _span(clip, f).items():
        R = _rot(ax, math.radians(ang * w))
        gk, tk = np.array(sw["grip_path"][k], float), np.array(sw["tip"][k], float)
        hk = _holders(clip, rig, k)
        at_k = hk[arm] if arm in hk else (float(np.mean(list(hk.values()))) if (arm is None and hk) else pivot_at)
        pivot = gk + at_k * (tk - gk) / max(float(np.linalg.norm(tk - gk)), 1e-9)
        sw["grip_path"][k] = (pivot + R @ (gk - pivot)).tolist()
        sw["tip"][k] = (pivot + R @ (tk - pivot)).tolist()
        if isinstance(sw.get("edge"), list) and k < len(sw["edge"]):
            sw["edge"][k] = (R @ np.array(sw["edge"][k], float)).tolist()


def _copy_moving(clip):
    """a trial copy: the joints, the sword paths and the grip tracks new lists (the rest shared)"""
    t = dict(clip, joints={j: {**v, "frames": [list(x) for x in v["frames"]]} for j, v in clip["joints"].items()})
    if isinstance(clip.get("sword"), dict):
        t["sword"] = {k: ([list(x) for x in v] if isinstance(v, list) else v) for k, v in clip["sword"].items()}
    if isinstance(clip.get("grip"), list):
        t["grip"] = [list(x) for x in clip["grip"]]
    return t


def _hand_off(clip, rig, k, arm):
    """how far `arm`'s hand is from the weapon's line at frame k (in_hand.py's own reading: the line from BEHIND studs
    behind the grip point to the tip)"""
    import clip as C
    import in_hand as IH
    sw = clip["sword"]
    g, t = np.array(sw["grip_path"][k], float), np.array(sw["tip"][k], float)
    L = float(np.linalg.norm(t - g))
    ax = (t - g) / max(L, 1e-9)
    h = (C.fk(rig, C.character_transforms(clip, rig, k))[arm] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]
    return float(np.linalg.norm(h - (g + float(np.clip(np.dot(h - g, ax), -IH.BEHIND, L)) * ax)))


def _kept_on(clip, trial, rig, arms, f):
    """every holding hand still on the weapon on the frames the move touched: within in_hand.py's LOOSE bar, or no
    further off than it was (the hand gate's bar is tighter than the collision check's reach)"""
    import in_hand as IH
    for k in _span(clip, f):
        for arm in arms:
            if _hand_off(trial, rig, k, arm) > max(IH.LOOSE, _hand_off(clip, rig, k, arm)) + 1e-6:
                return False
    return True


def _no_snap(clip, trial, arms, f):
    """no arm a coupled move touched turns faster between two frames than it did by more than SNAP_GROW degrees"""
    import grip_solve as GS
    lo, hi = max(0, min(_span(clip, f)) - 1), min(len(clip["times"]) - 1, max(_span(clip, f)) + 1)
    for arm in arms:
        if arm not in clip["joints"]:
            continue
        was = GS._turns(clip["joints"][arm]["frames"][lo:hi + 1])
        now = GS._turns(trial["joints"][arm]["frames"][lo:hi + 1])
        if len(now) and float(np.max(np.asarray(now) - np.asarray(was))) > SNAP_GROW:
            return False
        if any(_pop(now, i) and not _pop(was, i) for i in range(len(now))):
            return False                                     # (the build's own pop rule: kit/anim/clip.py pop_deg)
    return True


def _pop(steps, i):
    """the build's pop: a one-frame turn over pop_deg with both neighbours three times smaller (kit/anim/clip.py)"""
    import clip as C
    prev = steps[i - 1] if i > 0 else 0.0
    nxt = steps[i + 1] if i + 1 < len(steps) else 0.0
    return steps[i] > C.GATES["pop_deg"] and steps[i] > 3 * max(prev, nxt, 1e-6)


def _no_worse(before, after, movers):
    """every pair of the things moved no worse than it was, or under its own bar by room"""
    import collide as K
    for key, depth in after.items():
        a, b = key.split("|")
        if a not in movers and b not in movers:
            continue
        if depth > max(before.get(key, 0.0), K.BARS[_kind(a, b)] - ROOM) + 1e-9:
            return False
    return True


def _move_held_blade(clip, rig, block, f, blade_deg, held):
    """a HELD blade and its holding arms together (V3 C.1): the blade turned about the holding hands' middle by the
    least that takes it out of `block` round f, the hands put back on it -> what was done; ValueError when nothing
    within blade_deg does"""
    import clip as C
    sw = clip["sword"]
    g, t = np.array(sw["grip_path"][f], float), np.array(sw["tip"][f], float)
    d = t - g
    before = _pairs(clip, f)
    was = before.get(f"weapon|{block}", 0.0)
    mid_at = float(np.mean(list(held.values()))) if held else 0.0
    # the pivots tried: through an arm that HOLDS it, that arm's own hand first (the blade swings off the forearm and
    # the arm stays where it is - turned about the hands' middle, the arm follows it in); then the hands' middle,
    # then each hand
    pivots = ([(held[block], block)] if block in held else []) + [(mid_at, None)] + [(v, k) for k, v in held.items()
                                                                                       if k != block]
    said = _sides(held)
    arms = set(held)
    mid = g + mid_at * d / max(float(np.linalg.norm(d)), 1e-9)
    to = C.fk(rig, C.character_transforms(clip, rig, f))[block][:3, 3] - mid
    n1 = np.cross(d, to)
    if float(np.linalg.norm(n1)) < 1e-6:
        n1 = np.cross(d, np.array([0.0, 1.0, 0.0]) if abs(d[1]) < 0.9 * np.linalg.norm(d) else np.array([1.0, 0.0, 0.0]))
    n1 = n1 / np.linalg.norm(n1)
    n2 = np.cross(d, n1)
    n2 = n2 / np.linalg.norm(n2)
    why = None
    ang = STEP_DEG
    while ang <= blade_deg + 1e-9:
        for (at, by), ax in ((p_, a_) for p_ in pivots for a_ in (n1, -n1, n2, -n2)):
            trial = _copy_moving(clip)
            _turn_held_blade(trial, rig, f, ang, ax, at, by)
            # (turned about a holding hand, that hand is still on it: a hand still holding is not moved - only when
            # one came off the weapon are the hands put back on it)
            still = _kept_on(clip, trial, rig, held, f)
            try:
                if still:
                    if "grip" in trial:
                        _regrip(trial)
                else:
                    _hold_again(trial, clip, rig, f, said)
            except ValueError as e:
                why = str(e)
                continue
            after = _pairs(trial, f)
            if (_fine(before, after, "weapon", block) and _no_worse(before, after, arms) and _no_snap(clip, trial, arms, f)
                    and _kept_on(clip, trial, rig, held, f)):
                for k in ("joints", "sword", "grip"):
                    if k in trial:
                        clip[k] = trial[k]
                return {"what": "weapon", "out_of": block, "frame": f, "deg": ang, "slide": 0.0, "was": round(was, 3),
                        "held": said}
        ang += STEP_DEG
    who = "both hands" if said == "two" else "the " + said + " hand"
    raise ValueError(f"the weapon is {was:.2f} studs into the {block} round frame {f}, held in {who}, and no turn of "
                     f"{blade_deg:g} degrees about the hands with the hands kept on it takes it out"
                     + (f" (the last try: {why})" if why else "") + ": the swing's line is the move's to change")


def _carry_weapon(clip, rig, arm, before_W, f):
    """the weapon carried rigidly with `arm`'s hand on the frames the move at f touched (before_W: each frame's FK
    before the arm moved)"""
    import clip as C
    sw = clip["sword"]
    for k in _span(clip, f):
        A0 = before_W[k][arm]
        A1 = C.fk(rig, C.character_transforms(clip, rig, k))[arm]
        D = A1 @ np.linalg.inv(A0)
        for key in ("grip_path", "tip"):
            sw[key][k] = (D[:3, :3] @ np.array(sw[key][k], float) + D[:3, 3]).tolist()
        if isinstance(sw.get("edge"), list) and k < len(sw["edge"]):
            sw["edge"][k] = (D[:3, :3] @ np.array(sw["edge"][k], float)).tolist()


def _move_holding_arm(clip, rig, arm, block, f, max_deg, max_slide, held_any):
    """a holding ARM whose hand is in `block` (V3 C.1): turned (and slid) about its shoulder as an arm is, the weapon
    carried with the hand, the other hand of a two-handed grip put back on it -> what was done; ValueError"""
    import clip as C
    before = _pairs(clip, f)
    was = before.get(f"{arm}|{block}", 0.0)
    W0 = {k: C.fk(rig, C.character_transforms(clip, rig, k)) for k in _span(clip, f)}
    said = _sides(held_any)
    cands = []
    ang = STEP_DEG
    while ang <= max_deg + 1e-9:
        for sl in SLIDES:
            if sl > max_slide + 1e-9:
                continue
            for ax in ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
                cands.append((ang + 60 * sl, ang, sl, ax))
        ang += STEP_DEG
    cands += [(60 * sl, 0.0, sl, (0, 0, 1)) for sl in SLIDES if 0 < sl <= max_slide + 1e-9]
    why = None
    for _cost, ang, sl, ax in sorted(cands, key=lambda c: c[0]):
        trial = _copy_moving(clip)
        _turn_limb(trial, arm, f, ang, sl, ax)
        _carry_weapon(trial, rig, arm, W0, f)
        try:
            if said == "two":
                _hold_again(trial, clip, rig, f, said)
            elif "grip" in trial:
                _regrip(trial)
        except ValueError as e:
            why = str(e)
            continue
        after = _pairs(trial, f)
        if (_fine(before, after, arm, block) and _no_worse(before, after, set(held_any) | {"weapon"})
                and _no_snap(clip, trial, set(held_any) | {arm}, f) and _kept_on(clip, trial, rig, held_any, f)):
            for k in ("joints", "sword", "grip"):
                if k in trial:
                    clip[k] = trial[k]
            return {"what": arm, "out_of": block, "frame": f, "deg": ang, "slide": sl, "was": round(was, 3), "held": said}
    raise ValueError(f"the {arm} holds the weapon and its hand is {was:.2f} studs into the {block} round frame {f}, and "
                     f"no turn of {max_deg:g} degrees with a slide of {max_slide:g} studs, the weapon carried with it, "
                     "takes it out" + (f" (the last try: {why})" if why else "") + ": a pose that far in is the move's to change")


def _restep(c, stepped):
    """a repaired smooth clip STEPPED again on its own windows: inside each, every frame holds the sample at the
    window's last step (every `on` frames from its start) - the joints, the weapon's paths and joint tracks, the root"""
    fps = float(c.get("fps") or 30)
    n = len(c["times"])
    sw = c.get("sword") if isinstance(c.get("sword"), dict) else {}
    tracks = [j["frames"] for j in c["joints"].values() if j.get("frames")]
    tracks += [sw[k] for k in ("tip", "grip_path", "edge") if isinstance(sw.get(k), list) and len(sw[k]) == n]
    tracks += [c[k] for k in ("root", "grip", "grip_left") if isinstance(c.get(k), list) and len(c[k]) == n]
    for t0, t1, on in stepped:
        i0, i1, on = int(round(t0 * fps)), min(n - 1, int(round(t1 * fps))), max(1, int(on))
        for i in range(i0, i1 + 1):
            key = i0 + ((i - i0) // on) * on
            if key != i:
                for F in tracks:
                    F[i] = list(F[key])
    c["stepped"] = stepped
    return c


def _regrip(c):
    """the weapon's own joint track made again (it is relative to the right arm: kit/anim/grip.py)"""
    import grip as GR
    track = GR.grip_track(c)
    if track is None:
        raise ValueError("the weapon's own joint track could not be made again (its tip, grip or edge track is missing or "
                         "of another length): the clip is left as it was")
    c["grip"] = track


def _joint_frame(rig, part, Wp, Wc, like):
    """the clip frame ([qx, qy, qz, qw, x, y, z]: kit/anim/clip.py's character-space turn + slide at the joint) that puts
    `part` at the 4x4 Wc under its parent at Wp - fk's own sum read backwards; the quaternion kept on `like`'s side"""
    import clip as C
    j = rig["joints"][part]
    c0, c1 = C.cf(j["c0"]), C.cf(j["c1"])
    t4 = np.linalg.inv(c0) @ np.linalg.inv(Wp) @ Wc @ c1
    c0r = c0[:3, :3]
    q = np.array(C.mat_quat(c0r @ t4[:3, :3] @ c0r.T))
    if float(np.dot(q, np.asarray(like[:4], float))) < 0:
        q = -q
    return [round(float(v), 6) for v in q] + [round(float(v), 5) for v in c0r @ t4[:3, 3]] + list(like[7:])


HIP = {"hips": (0.0, -1.0, 0.0), "Right Leg": (1.0, -1.0, 0.0), "Left Leg": (-1.0, -1.0, 0.0)}   # (Torso space)
TILTS = (((1, 0, 0), "lean"), ((-1, 0, 0), "lean"), ((0, 1, 0), "twist"), ((0, -1, 0), "twist"), ((0, 0, 1), "side"),
         ((0, 0, -1), "side"))


def _counter_tilt(clip, rig, f, ang, ax, pivot, stands, max_slide):
    """THE COUNTER-TILT (LIMITATIONS_FIXES_V4 4.4 / 13.4.2): a trial copy with the TORSO (and the head on it) turned
    `ang` degrees about the Torso's own axis `ax` at frame f, through `pivot` (the hips' middle, or one hip: the body
    pivots over that leg), eased over the move's frames - while the hands and the feet STAY where they were: each arm
    is turned from its moved shoulder back onto where its hand was (and slid along itself the difference, an R6 arm
    slides), each leg from its moved hip back onto where its foot was (a leg does not slide: its foot may move the
    difference along it). The weapon is not moved: the hands on it are where they were -> (trial, the most an arm was
    slid). ValueError: an arm would need more than max_slide, or a foot standing on the floor would move over FOOT_DRIFT"""
    import clip as C
    trial = _copy_moving(clip)
    slid = 0.0
    import grip_solve as GS
    for k, w in _span(clip, f).items():
        if w <= 1e-9:
            continue
        W = C.fk(rig, C.character_transforms(clip, rig, k))
        T0 = W["Torso"]
        axis = T0[:3, :3] @ np.asarray(ax, float)           # (the Torso's own axis at each frame: a lean through the
        P = (T0 @ np.array([*HIP[pivot], 1.0]))[:3]         # hips leaves both hips where they are)
        G = np.eye(4)
        G[:3, :3] = _rot(axis, math.radians(ang * w))
        G[:3, 3] = P - G[:3, :3] @ P
        T1 = G @ T0
        new = {"Torso": T1}
        for limb in ARMS + LEGS:
            if limb not in clip["joints"] or not clip["joints"][limb].get("frames"):
                continue
            c0 = C.cf(rig["joints"][limb]["c0"])
            piv0, piv1 = (T0 @ c0)[:3, 3], (T1 @ c0)[:3, 3]
            end = (W[limb] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]
            d0, d1 = end - piv0, end - piv1
            Q = GS._arc(d0, d1)
            M = np.eye(4)
            M[:3, :3] = Q @ W[limb][:3, :3]
            M[:3, 3] = piv1 + Q @ (W[limb][:3, 3] - piv0)
            gap = float(np.linalg.norm(d1) - np.linalg.norm(d0))
            if limb in ARMS:
                if abs(gap) > max_slide + 1e-9:
                    raise ValueError(f"the {limb} would slide {abs(gap):.2f} studs to keep its hand")
                M[:3, 3] += gap * d1 / max(float(np.linalg.norm(d1)), 1e-9)
                slid = max(slid, abs(gap))
            elif stands.get(limb) is not None and stands[limb][k] and abs(gap) > FOOT_DRIFT:
                raise ValueError(f"the {limb}'s standing foot would move {abs(gap):.2f} studs")
            new[limb] = M
        for part, M in new.items():
            Wp = np.eye(4) if part == "Torso" else T1
            trial["joints"][part]["frames"][k] = _joint_frame(rig, part, Wp, M, clip["joints"][part]["frames"][k])
    if "grip" in trial:
        _regrip(trial)
    return trial, slid


def _commit(clip, trial):
    for k in ("joints", "sword", "grip"):
        if k in trial:
            clip[k] = trial[k]


def _by_tilt(clip, rig, a, b, f, tilt_deg, max_slide, stands, held, regular=None):
    """the fault a|b round f taken out by a COUNTER-TILT of the torso (above), the least that does; else - when the
    move that was refused (`regular`, a function that moves a trial copy or raises) can finish what a tilt began - a
    tilt and that move together. Each is taken only when the fault is under its bar by ROOM, no other reading anywhere
    in the body got worse (or is under its bar by room), no joint snaps, and every hand on the weapon stays on it ->
    [what was done] | None"""
    if not (clip["joints"].get("Torso") or {}).get("frames"):
        return None                                          # (a clip with no torso track has no torso to tilt)
    before = _pairs(clip, f)
    was = before.get(f"{a}|{b}", 0.0)
    everyone = set(BODY_PARTS) | {"weapon"}
    joints = ["Torso"] + [j for j in ARMS + LEGS if j in clip["joints"]]
    standing = [leg for leg in LEGS if stands.get(leg) is not None and any(stands[leg][k] for k in _span(clip, f))]
    side_pivot = standing[0] if len(standing) == 1 else "hips"
    near = []

    def kept(trial):
        return _no_snap(clip, trial, joints, f) and (not held or _kept_on(clip, trial, rig, held, f))

    def good(trial):
        after = _pairs(trial, f)
        return _fine(before, after, a, b) and _no_worse(before, after, everyone) and kept(trial), after

    ang = STEP_DEG
    while ang <= tilt_deg + 1e-9:
        for ax, how in TILTS:
            pivot = side_pivot if how == "side" else "hips"
            try:
                trial, slid = _counter_tilt(clip, rig, f, ang, ax, pivot, stands, max_slide)
            except ValueError:
                continue
            ok, after = good(trial)
            move = {"what": "Torso", "out_of": b, "frame": f, "deg": ang, "slide": round(slid, 3), "was": round(was, 3),
                    "how": f"counter-tilt ({how}, about the {'hips' if pivot == 'hips' else pivot.split()[0].lower() + ' hip'})",
                    "for": a}
            if ok:
                _commit(clip, trial)
                return [move]
            # (a tilt that takes some of it out is kept as a start for the refused move - the pair is judged whole,
            # every reading and the hands, on what the two do together: `good` below)
            gain = was - after.get(f"{a}|{b}", 0.0)
            if gain > PARTIAL and _no_worse(before, after, everyone - {a, b}):
                near.append((gain, ang, trial, move))
        ang += STEP_DEG
    near.sort(key=lambda x: (-round(x[0], 2), x[1]))      # (the tilts that took the most out first; the least among equals)
    if regular is not None:
        # a tilt and the refused move together
        for _gain, _ang, trial, move in near[:2]:
            t2 = _copy_moving(trial)
            try:
                second = regular(t2)
            except ValueError:
                continue
            if good(t2)[0]:
                _commit(clip, t2)
                return [move, second]
    # (NOT taken part of the way: measured on the 44 frozen non-GT colliding clips, a tilt kept for what it took out
    # and the fault met again on the next pass repaired one clip FEWER - 14 against 15 - the greedy partial led a
    # clip into a refusal its whole-way search did not meet)
    return None


def _step_apart(clip, rig, a, b, f, max_deg, stands):
    """THE STEP: a foot in the OTHER leg (a dash's crossed legs) - both legs turned apart about their hips, mirrored,
    the stance widened by the least that takes the foot out; refused (None) when either foot stands on the floor at a
    frame the move touches (turning it would drag it) -> [what was done] | None"""
    span = _span(clip, f)
    if any(stands[leg][k] for leg in (a, b) for k in span):
        return None
    before = _pairs(clip, f)
    was = before.get(f"{a}|{b}", 0.0)
    ang = STEP_DEG
    while ang <= max_deg + 1e-9:
        for ax in ((0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)):
            trial = _copy_moving(clip)
            _turn_limb(trial, a, f, ang, 0.0, ax)
            _turn_limb(trial, b, f, ang, 0.0, tuple(-v for v in ax))
            after = _pairs(trial, f)
            if (_fine(before, after, a, b) and _no_worse(before, after, {a, b})
                    and _no_snap(clip, trial, [a, b], f)):
                _commit(clip, trial)
                return [{"what": leg, "out_of": b if leg == a else a, "frame": f, "deg": ang, "slide": 0.0, "was": round(was, 3),
                         "how": "stepped apart"} for leg in (a, b)]
        ang += STEP_DEG
    return None


def repair(clip, max_deg=MAX_DEG, max_slide=MAX_SLIDE, blade_deg=BLADE_DEG, tilt_deg=TILT_DEG):
    """-> (the repaired clip - a copy, or the clip itself when nothing was over a bar - , [what was done]).
    ValueError names what could not be repaired; the clip given is never changed"""
    import clip as C
    import collide as K
    import in_hand as IH
    for name, v, top in (("max_deg", max_deg, 90.0), ("max_slide", max_slide, SLIDES[-1]), ("blade_deg", blade_deg, 90.0),
                         ("tilt_deg", tilt_deg, 45.0)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= top:
            raise ValueError(f"clear: {name} is a number from 0 to {top:g}")
    if clip.get("prop"):
        return clip, []                                      # (a prop is not a body: the gate does not read it either)
    r = K.read(clip)
    if not K.over(r):
        return clip, []
    if clip.get("stepped"):
        # (V3 C.1: repaired on its smooth motion, then stepped again on the very windows - it was refused)
        smooth = C.destep(clip)
        smooth.pop("stepped", None)
        fixed, done = repair(smooth, max_deg, max_slide, blade_deg, tilt_deg)
        if not done:
            return clip, []
        out = _restep(copy.deepcopy(fixed), copy.deepcopy(clip["stepped"]))
        if K.over(K.read(out)):
            raise ValueError("repaired on its smooth motion, the clip stepped again still passes through the body ("
                             + K.words(K.read(out), str(clip.get("name"))) + "): a hold sits in it - the move's to change")
        return out, done
    rig = C.load_rig("r6")
    c = copy.deepcopy(clip)
    done = []
    n = len(c["times"])
    spent = {}                                               # what -> per frame, the degrees and studs moved so far
    armed = isinstance(c.get("sword"), dict) and bool(c["sword"].get("tip"))
    free = IH.read(clip)["free"] if armed else []
    # a foot that stands on the floor: within 0.1 studs of the lowest that foot ever is (the clip's travel carried)
    low = {leg: np.array([C.lowest(rig, leg, w[leg]) for w in C.world_frames(clip, rig)]) for leg in LEGS}
    stands = {leg: low[leg] <= float(low[leg].min()) + 0.1 for leg in LEGS}

    def book(move):
        """moves near one another add up: the BOUND is on what a frame ends up moved by, not on one move"""
        top = blade_deg if move["what"] == "weapon" else tilt_deg if move["what"] == "Torso" else max_deg
        deg, sl = spent.setdefault(move["what"], (np.zeros(n), np.zeros(n)))
        for k, w in _span(c, move["frame"]).items():
            deg[k] += move["deg"] * w
            sl[k] += move["slide"] * w
        if float(deg.max()) > top + 1e-9 or float(sl.max()) > max_slide + 1e-9:
            k = int(np.argmax(deg)) if float(deg.max()) > top + 1e-9 else int(np.argmax(sl))
            raise ValueError(f"the {move['what']} would be moved {deg[k]:.0f} degrees" + (f" and {sl[k]:.2f} studs" if sl[k] else "")
                             + f" in all at frame {k} to stay out of the {move['out_of']} (at most {top:g} degrees"
                             + (f", {max_slide:g} studs" if move["what"] != "weapon" else "") + "): a pose that far in is the "
                             "move's to change")
        done.append(move)

    def fix(a, b, f, regular, held_now, step=None):
        """the move the fault asks for (`regular`, on the clip); refused, the legs stepped apart (a foot in the other
        leg), then a counter-tilt of the torso (alone, or with the refused move finishing it) - V4 4.4 / 13.4.2; all
        refused: the first refusal, with what else was tried"""
        try:
            moved = regular(c)
        except ValueError as e:
            first = e
        else:
            book(moved)
            return
        got = step() if step else None
        if not got:
            got = _by_tilt(c, rig, a, b, f, tilt_deg, max_slide, stands, held_now, regular)
        if not got:
            raise ValueError(f"{first}; nor does a counter-tilt of the torso of up to {tilt_deg:g} degrees (the hands "
                             "and the feet kept where they were)" + (" or the legs stepped apart" if step else "")) from first
        for move in got:
            book(move)

    def holding_in(span, held):
        out = {}
        for k in span:                                       # (every hand that holds it anywhere the move touches)
            for arm_, at_ in held.get(k, {}).items():
                out.setdefault(arm_, at_)
        return out

    for _ in range(PASSES):
        bad = K.over(r)
        if not bad:
            break
        kind, w = max(bad, key=lambda b: b[1]["depth"] - K.BARS[b[0]])
        f, a, b = int(w["frame"]), w["a"], w["b"]
        span = sorted(_span(c, f))
        held = {k: _holders(c, rig, k) for k in span} if armed else {}
        if kind == "weapon":
            holding = holding_in(span, held)
            if holding:
                holding = {**holding, **held.get(f, {})}     # (where they are at the fault's own frame, when there)
                if "Left Arm" in holding and c.get("grip_left"):
                    raise ValueError(f"the weapon passes through the {b} at frame {f} and the Left Arm carries the second "
                                     "weapon: that weapon's track is made from the move's keys and cannot be made again here")
                fix(a, b, f, lambda t, b=b, f=f, h=holding: _move_held_blade(t, rig, b, f, blade_deg, h), holding)
            else:
                def blade(t, b=b, f=f):
                    m = _move_blade(t, rig, b, f, blade_deg)
                    if "grip" in t:
                        _regrip(t)
                    return m
                fix(a, b, f, blade, {})
        elif kind == "hand_arm":
            raise ValueError(f"the {a}'s hand is in the {b} at frame {f}: which arm gives way is the move's to say")
        elif a in ARMS:
            holds = next((k for k in span if a in held.get(k, {})), None)
            if holds is not None and not (a == "Left Arm" and c.get("grip_left")):
                both = holding_in(span, held)
                fix(a, b, f, lambda t, a=a, b=b, f=f, h=both: _move_holding_arm(t, rig, a, b, f, max_deg, max_slide, h), both)
                r = K.read(c)
                continue
            if a == "Left Arm" and c.get("grip_left"):
                raise ValueError(f"the Left Arm carries the second weapon and its hand is in the {b} at frame {f}: that weapon's "
                                 "track is made from the move's keys and cannot be made again here")

            def arm_move(t, a=a, b=b, f=f):
                m = _move_limb(t, rig, a, b, f, max_deg, max_slide)
                if a == "Right Arm" and "grip" in t:          # (the weapon rides the right arm: its joint track follows)
                    _regrip(t)
                return m
            fix(a, b, f, arm_move, holding_in(span, held))
        else:
            def leg_move(t, a=a, b=b, f=f, span=span):
                on = next((k for k in span if stands[a][k]), None)
                if on is not None:
                    raise ValueError(f"the {a}'s foot is in the {b} at frame {f} and that foot stands on the floor (frame "
                                     f"{on}): turning the leg would drag it - where it stands is the move's to change")
                return _move_limb(t, rig, a, b, f, max_deg, max_slide)
            step = (lambda a=a, b=b, f=f: _step_apart(c, rig, a, b, f, max_deg, stands)) if b in LEGS else None
            fix(a, b, f, leg_move, holding_in(span, held), step)
        r = K.read(c)
    if K.over(r):
        raise ValueError(f"still over a bar after {PASSES} moves ({K.words(r, str(clip.get('name')))})")
    if armed:                                                # (a hand that was on the weapon is still on it)
        now = IH.read(c)["free"]
        off = [i for i in range(min(len(free), len(now))) if free[i] <= IH.LOOSE < now[i]]
        if off:
            raise ValueError(f"moved clear, a hand comes off the weapon ({now[off[0]]:.2f} studs at frame {off[0]}): the "
                             "grip is solved where the move is made (its keys)")
    return c, done


def words(done):
    """what was done, in a line: each thing moved, its largest move and where"""
    if not done:
        return "nothing passes through the body: nothing moved"
    said = []
    for what in sorted({d["what"] for d in done}):
        mine = [d for d in done if d["what"] == what]
        deg, sl = max(d["deg"] for d in mine), max(d["slide"] for d in mine)
        first = mine[0]
        frames = sorted({d["frame"] for d in mine})
        hows = sorted({d["how"] for d in mine if d.get("how")})
        how = (f"turned {deg:g} degrees" + (f" and slid {sl:g} studs" if sl and what != "Torso" else "")
               + (" at the most" if len(mine) > 1 else "") + (f" - {', '.join(hows)}" if hows else "")
               + (f", the arms slid {sl:g} studs at the most to keep the hands" if sl and what == "Torso" else ""))
        said.append(f"the {what} {how} ({len(mine)} move(s) round frame(s) {', '.join(map(str, frames))}; it was "
                    f"{first['was']:.2f} studs into the {first['out_of']})")
    return "; ".join(said)


def op_clear(c, max_deg=MAX_DEG, max_slide=MAX_SLIDE, blade_deg=BLADE_DEG, tilt_deg=TILT_DEG):
    """the derive op: the clip repaired in place -> the log line; ValueError (the recipe fails, named) when it cannot"""
    fixed, done = repair(c, max_deg, max_slide, blade_deg, tilt_deg)
    if done:
        keep = dict(fixed)
        c.clear()
        c.update(keep)
    return "clear: " + words(done)


def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    try:
        with open(argv[0], encoding="utf-8") as fh:
            c = json.load(fh)
        fixed, done = repair(c)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"anim clear: not repaired - {e}", "change the move (its keys, its grip), or say a meant "
                    "contact (\"contact\"); the clip was left as it was")
    out = flag(argv, "--out")
    if out and done:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(fixed, fh)
    return emit("pass", f"anim clear {c.get('name')}: {words(done)}" + ("" if out or not done else " (nothing written: no --out)"),
                "none - proceed" if not done else "look at the frames it moved (kit anim sheet), then build", moves=done)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
