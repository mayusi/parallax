"""curves.py — CURVE TOOLS for a clip (the owner's method lists 2026-11-13: Graph Editor editing - "NOT there: tangent
handles, a signal filter"; the audit: board/plans/archive/2026-11-13-anim-methods-audit.md). Two ops for a `kit anim derive`
recipe (kit/anim/derive.py), on the dense per-frame tracks the kit stores:

  {"op": "filter", "hz": 8, "joints": ["Head", "Torso"], "keep": [0.43]}
      a SIGNAL FILTER: a low-pass with no time shift (a Gaussian over each named joint's rotation and slide) that lets
      half of a shake at `hz` times a second through and less of anything faster. The first and last frame, every
      Hit, and every time in `keep` stay EXACTLY where they were (the filtered curve is blended back to the original
      round them over `ease` seconds, default 0.05). joints: default every joint. The blade's own track is never
      filtered: it is what the hands must still hold.
  {"op": "handles", "from": 0.20, "to": 0.43, "out": [0.6, 0.0], "in": [0.2, 1.0]}
      TANGENT HANDLES on the timing of one stretch: between the two times the motion is replayed along a cubic
      bezier in time - `out` is the handle leaving the first pose, `in` the one arriving at the second, each [x, y]
      in the unit square ([0.33, 0.33] / [0.67, 0.67] is as it was; out [0.6, 0] in [0.2, 1] gathers slowly and
      snaps). Both poses and the clip's length are kept; the blade keeps its length.

WHAT THEY REFUSE (a tool that quietly breaks a clip is worse than none):
  filter   a STEPPED clip (its holds would be smoothed away); a filter that takes a hand off the weapon (either hand
           more than 0.1 studs further from the weapon's line than it was: the blade is not filtered, so a filter on
           the torso or an arm of a sword clip does that); a filter that takes more than a tenth off the cut - the
           striker's path length or how far a filtered joint gets from its first pose - unless the recipe says
           "soften": true.
  handles  a stretch with a Hit inside it (the Hit would no longer sit on the fastest frame); handles that make the
           striker's fastest frame more than twice as fast as it was (a hold then a snap that pops).
What a filter is FOR: a track that shakes (noise from a capture, a solver that chatters). `roughness` is the number
it moves: the mean change, in degrees, of a joint's frame-to-frame turn from one frame to the next. Measured on the
kit's fixture (the loved kesa, its HEAD given 1.5 degrees of noise a frame; see kit/test/python/test_anim_curves.py):
the filtered head ends nearer the clean one than the noisy one was, with the Hit pose and both ends untouched."""
import math

import numpy as np

EASE_S = 0.05        # seconds a kept moment is blended back over
LOSS = 0.10          # the share of the cut a filter may take (the striker's path, a joint's whole turn) unasked
HAND_OFF = 0.1       # studs a hand may end further from the weapon's line (kit/anim/in_hand.py's own bar)
FASTER = 2.0         # handles may not make the striker's fastest frame more than this times what it was


def _tracks(c):
    """every per-frame vector track of the clip that moves with its motion -> [(get, set)] of [n, k] arrays"""
    out = []
    for j, jd in c["joints"].items():
        if jd.get("frames"):
            out.append(("joint", j))
    sw = c.get("sword") if isinstance(c.get("sword"), dict) else {}
    for k in ("tip", "grip_path", "edge"):
        if isinstance(sw.get(k), list) and len(sw[k]) == len(c["times"]):
            out.append(("sword", k))
    if isinstance(c.get("root"), list) and len(c["root"]) == len(c["times"]):
        out.append(("root", None))
    return out


def _get(c, ref):
    kind, k = ref
    return np.array(c["joints"][k]["frames"] if kind == "joint" else c["sword"][k] if kind == "sword" else c["root"], float)


def _set(c, ref, A):
    kind, k = ref
    A = np.array(A, float)
    if kind in ("joint", "root") and A.shape[1] >= 4:        # a rotation: one hemisphere, unit length
        q = A[:, :4]
        for i in range(1, len(q)):
            if np.dot(q[i], q[i - 1]) < 0:
                q[i] = -q[i]
        q /= np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)
        A[:, :4] = q
    rows = [[round(float(v), 6) for v in r] for r in A]
    if kind == "joint":
        c["joints"][k]["frames"] = rows
    elif kind == "sword":
        c["sword"][k] = rows
    else:
        c["root"] = rows


def _aligned(A, quat):
    A = np.array(A, float)
    if quat:
        for i in range(1, len(A)):
            if np.dot(A[i, :4], A[i - 1, :4]) < 0:
                A[i, :4] = -A[i, :4]
    return A


def _gauss(A, sigma):
    """a Gaussian low-pass with no time shift, the ends mirrored (no pull toward zero)"""
    if sigma <= 0.05 or len(A) < 3:
        return A.copy()
    r = max(1, int(math.ceil(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.concatenate([2 * A[0] - A[r:0:-1], A, 2 * A[-1] - A[-2:-r - 2:-1]]) if len(A) > r else np.pad(A, ((r, r), (0, 0)), mode="edge")
    return np.stack([np.convolve(pad[:, d], k, mode="valid") for d in range(A.shape[1])], axis=1)


def kept_frames(c, keep=()):
    fps = float(c.get("fps") or 30)
    n = len(c["times"])
    out = {0, n - 1}
    for e in c.get("events") or []:
        if isinstance(e, dict) and e.get("name") == "Hit" and isinstance(e.get("t"), (int, float)):
            out.add(min(n - 1, max(0, int(round(float(e["t"]) * fps)))))
    for t in keep or ():
        out.add(min(n - 1, max(0, int(round(float(t) * fps)))))
    return sorted(out)


def _strike(c):
    """what strikes, read off the clip -> (its fastest frame in studs a second, the length of its path in studs)"""
    import timing_chart as TC
    s = TC.series(c)
    if not len(s["strike"]):
        return 0.0, 0.0
    return float(np.max(s["strike"])), float(np.sum(s["strike_step"]))


def _turn(c, joint):
    """how far a joint gets from where it starts: the largest angle between any frame and the first, degrees (noise
    on every frame barely moves it; a filter that flattens the motion does)"""
    q = _aligned(np.array(c["joints"][joint]["frames"], float)[:, :4], True)
    q /= np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)
    return float(np.max(2 * np.degrees(np.arccos(np.clip(np.abs(q @ q[0]), 0.0, 1.0)))))


def _hands_off(c):
    """each hand's worst distance to the weapon's line, studs -> {hand: studs} ({} = the clip carries no weapon)"""
    return {h: float(d.max()) for h, d in _hands_off_frames(c).items()}


def _further(before, after):
    """the hand a change takes furthest from the weapon, FRAME BY FRAME (a hand that lets go somewhere in the clip is
    still held to where it was everywhere else) -> (hand, studs before, studs after, frame) or None"""
    worst = None
    for h in after:
        if h not in before or len(before[h]) != len(after[h]):
            continue
        d = after[h] - before[h]
        k = int(np.argmax(d))
        if d[k] > HAND_OFF and (worst is None or d[k] > worst[2] - worst[1]):
            worst = (h, float(before[h][k]), float(after[h][k]), k)
    return worst


def _hands_off_frames(c):
    """each hand's distance to the weapon's line at every frame, studs -> {hand: [n]} ({} = no weapon)"""
    import clip as C
    import in_hand as IH
    import pose_sheet as PS
    p = PS.paths(c, C.world_frames(c, C.load_rig("r6")))
    if "Grip" not in p:
        return {}
    g, t = p["Grip"], p["BladeTip"]
    length = np.linalg.norm(t - g, axis=1)
    ax = (t - g) / np.maximum(length[:, None], 1e-9)
    out = {}
    for hand in ("RightHand", "LeftHand"):
        h = p[hand]
        along = np.clip(np.einsum("ij,ij->i", h - g, ax), -IH.BEHIND, length)
        out[hand] = np.linalg.norm(h - (g + along[:, None] * ax), axis=1)
    return out


def roughness(c, joint):
    """how rough a joint's turning is: the mean change, in degrees, of its frame-to-frame turn from one frame to the
    next (0 = it turns at a steady rate; noise on every frame raises it)"""
    q = _aligned(np.array(c["joints"][joint]["frames"], float)[:, :4], True)
    q /= np.maximum(np.linalg.norm(q, axis=1, keepdims=True), 1e-12)
    turn = 2 * np.degrees(np.arccos(np.clip(np.abs(np.einsum("ij,ij->i", q[1:], q[:-1])), 0.0, 1.0)))
    return float(np.mean(np.abs(np.diff(turn)))) if len(turn) > 1 else 0.0


def op_filter(c, hz=8.0, joints=None, keep=(), ease=EASE_S, soften=False):
    """-> what it did, in words. Raises ValueError (the clip left as it was) for a filter that cannot be what was
    asked, or that would break the clip"""
    import copy
    fps = float(c.get("fps") or 30)
    if isinstance(hz, bool) or not isinstance(hz, (int, float)) or not 0.5 <= hz <= fps / 2:
        raise ValueError(f"filter: hz is how many times a second may still pass, between 0.5 and half the clip's {fps:g} frames a second")
    if joints is not None and (not isinstance(joints, list) or not joints or any(j not in c["joints"] for j in joints)):
        raise ValueError(f"filter: joints is a list of the clip's joints ({', '.join(c['joints'])})")
    if not isinstance(keep, (list, tuple)) or any(isinstance(t, bool) or not isinstance(t, (int, float)) for t in keep):
        raise ValueError("filter: keep is a list of times in seconds")
    if isinstance(ease, bool) or not isinstance(ease, (int, float)) or ease < 0:
        raise ValueError("filter: ease is a time in seconds")
    if c.get("stepped"):
        raise ValueError("filter: this clip is STEPPED (poses held on 2s or 3s): a filter would smooth its holds away - "
                         "filter the clip before its steps are made")
    n = len(c["times"])
    sigma = fps * math.sqrt(2 * math.log(2)) / (2 * math.pi * float(hz))     # half of a shake at hz gets through
    pins = kept_frames(c, keep)
    w = np.ones(n)                                           # 1 = filtered, 0 = as it was (at every kept moment)
    span = max(1.0, float(ease) * fps)
    for p in pins:
        d = np.clip(np.abs(np.arange(n) - p) / span, 0.0, 1.0)
        w = np.minimum(w, d ** 2 * (3 - 2 * d))
    names = list(c["joints"]) if joints is None else list(joints)
    was = copy.deepcopy({j: c["joints"][j]["frames"] for j in names})
    before, hands0 = _strike(c), _hands_off_frames(c)
    turns0 = {j: _turn(c, j) for j in names}
    for j in names:
        if not c["joints"][j].get("frames"):
            continue
        A = _aligned(_get(c, ("joint", j)), True)
        _set(c, ("joint", j), A * (1 - w[:, None]) + _gauss(A, sigma) * w[:, None])
    after, hands1 = _strike(c), _hands_off_frames(c)
    why = None
    far_hand = _further(hands0, hands1)
    off = [(far_hand[0], far_hand[2])] if far_hand else []
    lost = [(j, turns0[j], _turn(c, j)) for j in names if turns0[j] > 20.0 and _turn(c, j) < (1 - LOSS) * turns0[j]]
    if off:
        hand, far = max(off, key=lambda x: x[1])
        why = (f"filter: it takes the {'right' if hand == 'RightHand' else 'left'} hand {far:.2f} studs off the weapon (the "
               "blade is not filtered: it is what the hands hold) - filter joints that do not carry it, or raise hz")
    elif not soften and before[1] > 1e-6 and after[1] < (1 - LOSS) * before[1]:
        why = (f"filter at {hz:g} a second takes the strike's path from {before[1]:.1f} to {after[1]:.1f} studs: that is the cut, "
               "not shake - raise hz, name the joints that shake, or say soften: true")
    elif not soften and lost:
        j, a, b = min(lost, key=lambda x: x[2] / x[1])
        why = (f"filter at {hz:g} a second takes {j}'s reach from {a:.0f} to {b:.0f} degrees: that is the motion, not "
               "shake - raise hz, or say soften: true")
    if why:
        for j in names:
            c["joints"][j]["frames"] = was[j]
        raise ValueError(why)
    return (f"filter: half of what shakes {hz:g} times a second (and more of what is faster) taken out of "
            f"{'every joint' if joints is None else ', '.join(joints)}; {len(pins)} moment(s) kept exactly (frames "
            f"{', '.join(str(p) for p in pins)}); the strike's path {before[1]:.1f} -> {after[1]:.1f} studs, its fastest frame "
            f"{before[0]:.0f} -> {after[0]:.0f} studs a second")


def bezier_y(x, p1, p2):
    """y of the cubic bezier (0,0) p1 p2 (1,1) at horizontal position x (handles keep x monotonic: 0 <= x1, x2 <= 1)"""
    lo, hi = 0.0, 1.0
    for _ in range(40):
        s = (lo + hi) / 2
        bx = 3 * (1 - s) ** 2 * s * p1[0] + 3 * (1 - s) * s ** 2 * p2[0] + s ** 3
        if bx < x:
            lo = s
        else:
            hi = s
    s = (lo + hi) / 2
    return 3 * (1 - s) ** 2 * s * p1[1] + 3 * (1 - s) * s ** 2 * p2[1] + s ** 3


def _handle(v, name):
    if (not isinstance(v, (list, tuple)) or len(v) != 2 or any(isinstance(a, bool) or not isinstance(a, (int, float)) for a in v)
            or not 0 <= v[0] <= 1 or not 0 <= v[1] <= 1):
        raise ValueError(f"handles: `{name}` is [x, y], both between 0 and 1 (the motion never runs backwards or past its poses)")
    return float(v[0]), float(v[1])


def op_handles(c, start, end, out=(1 / 3, 1 / 3), into=(2 / 3, 2 / 3)):
    """-> what it did, in words"""
    import copy
    fps = float(c.get("fps") or 30)
    n = len(c["times"])
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (start, end)):
        raise ValueError("handles: `from` and `to` are times in seconds")
    a, b = int(round(float(start) * fps)), int(round(float(end) * fps))
    whole, fastest = copy.deepcopy({k: c.get(k) for k in ("joints", "sword", "root")}), _strike(c)[0]
    if not 0 <= a < b <= n - 1 or b - a < 2:
        raise ValueError(f"handles: `from` and `to` are two moments of the clip (0 to {c['times'][-1]:.2f} s), at least two frames apart")
    p1, p2 = _handle(out, "out"), _handle(into, "in")
    inside = [e for e in c.get("events") or [] if isinstance(e, dict) and e.get("name") == "Hit"
              and isinstance(e.get("t"), (int, float)) and a < round(float(e["t"]) * fps) < b]
    if inside:
        raise ValueError(f"handles: the stretch holds a Hit ({float(inside[0]['t']):.2f} s): replayed, the Hit would no longer "
                         "sit on the fastest frame - end the stretch at the Hit, or start it after")
    import clip as C
    for ref in _tracks(c):
        A = _aligned(_get(c, ref), ref[0] in ("joint", "root"))
        B = A.copy()
        for i in range(a + 1, b):
            u = a + bezier_y((i - a) / (b - a), p1, p2) * (b - a)
            lo = min(int(math.floor(u)), b - 1)
            f = u - lo
            if ref[0] in ("joint", "root") and A.shape[1] >= 4:
                B[i, :4] = C.slerp(A[lo, :4], A[lo + 1, :4], f)
                B[i, 4:] = A[lo, 4:] * (1 - f) + A[lo + 1, 4:] * f
            else:
                B[i] = A[lo] * (1 - f) + A[lo + 1] * f
        _set(c, ref, B)
    sw = c.get("sword") if isinstance(c.get("sword"), dict) else {}
    if isinstance(sw.get("tip"), list) and isinstance(sw.get("grip_path"), list) and len(sw["tip"]) == n == len(sw["grip_path"]):
        was_tip, was_grip = np.array(whole["sword"]["tip"], float), np.array(whole["sword"]["grip_path"], float)
        tip, grip = np.array(sw["tip"], float), np.array(sw["grip_path"], float)
        for i in range(a + 1, b):                            # the blade keeps its length (two points lerped apart shorten it)
            d = tip[i] - grip[i]
            u = a + bezier_y((i - a) / (b - a), p1, p2) * (b - a)
            lo = min(int(math.floor(u)), b - 1)
            f = u - lo
            L = float(np.linalg.norm(was_tip[lo] - was_grip[lo]) * (1 - f) + np.linalg.norm(was_tip[lo + 1] - was_grip[lo + 1]) * f)
            tip[i] = grip[i] + d / max(float(np.linalg.norm(d)), 1e-9) * L
        sw["tip"] = [[round(float(v), 6) for v in r] for r in tip]
        if isinstance(sw.get("edge"), list) and len(sw["edge"]) == n:
            e = np.array(sw["edge"], float)
            e /= np.maximum(np.linalg.norm(e, axis=1, keepdims=True), 1e-9)
            sw["edge"] = [[round(float(v), 6) for v in r] for r in e]
    now = _strike(c)[0]
    if fastest > 1e-6 and now > FASTER * fastest:
        for k, v in whole.items():
            if v is not None:
                c[k] = v
        raise ValueError(f"handles: they take the strike's fastest frame from {fastest:.0f} to {now:.0f} studs a second (a hold, "
                         "then a snap that pops) - bring the handles nearer the diagonal")
    moved = [e for e in c.get("events") or [] if isinstance(e, dict) and isinstance(e.get("t"), (int, float)) and a < round(float(e["t"]) * fps) < b]
    return (f"handles: {start:g} s to {end:g} s replayed along out {list(p1)} / in {list(p2)}; both poses and the length kept"
            + (f"; {len(moved)} event(s) inside the stretch keep their TIME, not their pose: " + ", ".join(str(e.get('name')) for e in moved)
               if moved else ""))
