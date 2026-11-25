"""drivers.py — A DRIVER for a clip (the owner's method lists 2026-11-13: driver / expression-driven animation - "the
kit authors none"; the audit: board/plans/archive/2026-11-13-anim-methods-audit.md). One op for a `kit anim derive` recipe
(kit/anim/derive.py): one joint's turning follows another's by a rule, written once instead of keyed frame by frame.

  {"op": "drive", "joint": "Head", "by": "Torso", "weight": 0.5, "delay": 0.05, "axis": [0, 1, 0]}
      at every frame the driven `joint` is given `weight` times the turn the driver `by` has made SINCE THE CLIP'S
      FIRST FRAME (0.5: half of it; -0.3: a third of it the other way, a counter-turn; up to 2 either way), read
      `delay` seconds earlier (0: with it; 0.05: it arrives three frames late at 60 a second), on top of the turn the
      joint already has. The driver's turn is followed all the way round (a torso that spins 300 degrees gives 150
      at 0.5, with no jump). axis: only the driver's turn ABOUT that axis counts (its twist: [0, 1, 0] = how far it
      has turned left or right), not its lean. Both turns are read and given in the kit's own clip space: each
      part's turn as its PARENT's axes see it. The joint's slide is left alone.
      A part still rides its parent: the head sits on the torso, so "Head by Torso 0.5" makes the head turn one and
      a half times as far as the torso in the world; a head that should stay behind takes a NEGATIVE weight.

What stays exactly as it was: the first frame (the driver has not turned yet), every other joint, the blade, the
events, the clip's length.

WHAT IT REFUSES, the clip left as it was (a tool that quietly breaks a clip is worse than none):
  - a joint driven by itself, a joint the clip does not key, a weight of 0 or beyond 2, a delay that is not a time
    inside the clip, an axis that is not a direction;
  - a driver that takes a hand off the weapon (either hand more than 0.1 studs further from the weapon's line than
    it was: the blade is not driven, so on a sword clip an arm or the torso cannot be - the head and the legs can);
  - a LOOP whose last frame would no longer be its first (the driver must come back to where it started), and any
    delay on a loop (the turn read late at the last frame is not the one at the first);
  - a clip whose joints do not all carry one frame for each of its times;
  - a delay on a STEPPED clip (the driven joint would move between the held poses).
What it does NOT check: where the Hit sits. A driven arm or torso moves what strikes; the build's own motion gates
(the Hit on the fastest frame, the weapon in the hand, pops) judge the clip the recipe makes, as they judge any."""
import copy
import math

import numpy as np

HAND_OFF = 0.1       # studs a hand may end further from the weapon's line (kit/anim/in_hand.py's own bar)
CLOSES = 0.5         # degrees a loop's last frame may be turned off its first
MOST = 2.0           # the largest weight, either way


def _mul(a, b):
    """a then... the product a * b of two quaternions [x, y, z, w]"""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz])


def _inv(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])


def _unit(q):
    q = np.asarray(q, float)
    q = q / max(float(np.linalg.norm(q)), 1e-12)
    return -q if q[3] < 0 else q


def _norm(q):
    """unit length, the sign as it is (a turn followed past 180 degrees keeps its way round)"""
    q = np.asarray(q, float)
    return q / max(float(np.linalg.norm(q)), 1e-12)


def _twist(q, axis):
    """the part of a turn that is about `axis` (swing-twist), its sign as the turn's"""
    along = float(np.dot(q[:3], axis))
    t = np.array([*(along * np.asarray(axis, float)), q[3]])
    if float(np.linalg.norm(t)) < 1e-9:                      # a half turn about something square to the axis: no twist
        return np.array([0.0, 0.0, 0.0, 1.0])
    return _norm(t)


def _power(q, w, about=None):
    """the same turn, `w` times as far - the way round the quaternion itself says (w < 0 in its last number: past 180).
    about: the axis it was last seen turning on (a turn of exactly one whole round has none of its own left)"""
    q = _norm(q)
    s = float(np.linalg.norm(q[:3]))
    if s < 1e-9:
        if q[3] < 0 and about is not None:                    # one whole turn: `w` of it is w x 360 degrees about that axis
            return np.array([*(np.asarray(about, float) * math.sin(math.pi * w)), math.cos(math.pi * w)])
        return np.array([0.0, 0.0, 0.0, 1.0])
    half = math.atan2(s, float(q[3])) * w
    return np.array([*(q[:3] / s * math.sin(half)), math.cos(half)])


def _slerp(a, b, u):
    """between two neighbours of one continuous run (b on a's side)"""
    a, b = _norm(a), _norm(b)
    if float(np.dot(a, b)) < 0:
        b = -b
    return _norm(_mul(a, _power(_mul(_inv(a), b), u)))


def angle(q):
    """how far a turn turns, degrees, all the way round (0 to 360)"""
    q = _norm(q)
    return 2.0 * math.degrees(math.atan2(float(np.linalg.norm(q[:3])), float(q[3])))


def off_rest(q):
    """how far a turn leaves a part from where it was, degrees (0 to 180: a whole turn leaves it where it was)"""
    return angle(_unit(q))


def _fps(c):
    n = len(c["times"])
    return (n - 1) / float(c["times"][-1]) if n > 1 and float(c["times"][-1]) > 0 else float(c.get("fps") or 30)


def _continuous(rel):
    out = [np.array([0.0, 0.0, 0.0, 1.0])]
    for r in rel[1:]:
        r = _norm(r)
        out.append(-r if float(np.dot(r, out[-1])) < 0 else r)
    return out


def added(c, by, weight=0.5, delay=0.0, axis=None):
    """the turn the driver gives at every frame -> [n, 4]"""
    fps = _fps(c)
    Q = [_norm(f[:4]) for f in c["joints"][by]["frames"]]
    rel = _continuous([_mul(q, _inv(Q[0])) for q in Q])      # the turn since the first frame, as the PARENT's axes see it
    if axis is not None:
        ax = np.asarray(axis, float) / np.linalg.norm(axis)
        rel = _continuous([_twist(r, ax) for r in rel])
    out, about = [], None
    for i in range(len(Q)):
        x = i - delay * fps
        if x <= 0:
            r = np.array([0.0, 0.0, 0.0, 1.0])
        else:
            lo = min(int(math.floor(x)), len(Q) - 1)
            hi = min(lo + 1, len(Q) - 1)
            r = _slerp(rel[lo], rel[hi], x - lo)
        if float(np.linalg.norm(r[:3])) > 1e-6:
            about = r[:3] / np.linalg.norm(r[:3])
        out.append(_power(r, weight, about))
    return np.array(out)


def _num(v):
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def op_drive(c, joint, by, weight=0.5, delay=0.0, axis=None):
    """-> what it did, in words. Raises ValueError (the clip left as it was) for a driver that cannot be what was
    asked, or that would break the clip"""
    keyed = [j for j, jd in c["joints"].items() if isinstance(jd, dict) and jd.get("frames")]
    for who, j in (("joint", joint), ("by", by)):
        if not isinstance(j, str) or j not in keyed:
            raise ValueError(f"drive: `{who}` is one of the clip's joints ({', '.join(keyed)})")
    if joint == by:
        raise ValueError(f"drive: {joint} cannot be driven by itself")
    if not _num(weight) or weight == 0 or abs(weight) > MOST:
        raise ValueError(f"drive: weight is the share of the driver's turn the joint is given: not 0, up to {MOST:g} either way")
    n = len(c["times"])
    uneven = [j for j in keyed if len(c["joints"][j]["frames"]) != n]
    if uneven:
        raise ValueError(f"drive: {uneven[0]} carries {len(c['joints'][uneven[0]]['frames'])} frames and the clip {n} times: "
                         "every joint carries one frame for each time")
    length = float(c["times"][-1])
    if not _num(delay) or delay < 0 or delay >= length:
        raise ValueError(f"drive: delay is a time in seconds inside the clip (0 to {length:.2f})")
    if axis is not None and (not isinstance(axis, (list, tuple)) or len(axis) != 3 or not all(_num(v) for v in axis)
                             or float(np.linalg.norm(axis)) < 1e-6):
        raise ValueError("drive: axis is a direction [x, y, z] (only the driver's turn about it counts)")
    if delay > 0 and c.get("stepped"):
        raise ValueError("drive: this clip is STEPPED (poses held on 2s or 3s): a delayed driver would move the joint "
                         "between its held poses - drive it with delay 0, or before its steps are made")
    if delay > 0 and c.get("loop"):
        raise ValueError("drive: this clip LOOPS: a delayed driver's turn at the last frame is not the one at the first - "
                         "drive a loop with delay 0")
    import curves as CV
    was = copy.deepcopy(c["joints"][joint]["frames"])
    hands = CV._hands_off_frames(c)
    D = added(c, by, weight, delay, axis)
    rows = []
    for f, d in zip(was, D):
        q = _unit(_mul(d, _unit(f[:4])))
        rows.append([*q, *f[4:7]])
    rows[0] = list(was[0])                                   # (the rest is laid on the first frame's own side)
    CV._set(c, ("joint", joint), rows)
    c["joints"][joint]["frames"][0] = list(was[0])           # the first frame: exactly what it was
    why = None
    off = CV._further(hands, CV._hands_off_frames(c))
    if off:
        h, a, b, k = off
        why = (f"drive: {joint} driven by {by} takes a hand off the weapon ({h} {a:.2f} -> {b:.2f} studs off the weapon's "
               f"line at frame {k}): the blade is not driven, so what holds it cannot be")
    elif c.get("loop") and off_rest(D[-1]) > CLOSES:
        why = (f"drive: this clip LOOPS and {by}'s turn leaves {joint}'s last frame {off_rest(D[-1]):.0f} degrees off its "
               f"first: {joint}'s last frame would no longer be its first")
    if why:
        c["joints"][joint]["frames"] = was
        raise ValueError(why)
    c["joints"][joint].pop("keys", None)                     # (its sparse keys, if it had any, are no longer its motion)
    most = max(range(len(D)), key=lambda i: angle(D[i]))
    return (f"drive: {joint} follows {by} ({weight:g} of its turn since the first frame"
            f"{', about ' + str(list(axis)) if axis is not None else ''}{', ' + format(delay, 'g') + ' s late' if delay else ''}): "
            f"at most {angle(D[most]):.1f} degrees added, at frame {most}; the first frame is as it was, the last is turned "
            f"{off_rest(D[-1]):.1f} degrees")
