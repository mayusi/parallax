"""A MODEL'S OWN MOTION, MADE READY FOR THE GAME (the owner's method lists, 2026-11-13: "keyframes", "poses",
"animation clips", "curves", "loops", "skeleton and animation export", "animation compression"; the 3D methods
audit, stage G3: "a.cycle: joint keys on one timeline - and they never reach the game").

`a.cycle` keys a mechanism's joints together on the .blend's timeline and the build checks them frame by frame; the
manifest carried the keys, and nothing in the game read them. Here the cycle becomes a TABLE the game plays: every
joint's value at a list of times, sampled from the SAME eased curve the build checked (so what plays is what was
checked), thinned to the keys a straight line between cannot stand in for, with its loop held closed.
Pure Python: the build feeds it; src/kit/ModelRules.luau reads the table back (cycleAt)."""

TOL_DEG = 0.25      # a hinge may sit this far (degrees) from the eased curve AT ITS FRAMES between two kept keys
TOL_STUDS = 0.002   # ... a slide this far (studs)
TOL_OF_TRAVEL = 0.02  # ... and neither further than this share of how far the joint travels in the cycle (a pin
#                       that moves a hundredth of a stud keeps its easing)
WINDOW = 64         # frames one straight line may stand in for (thinning looks no further ahead: its cost stays
#                     in line with the cycle's length)
LOOP_DEG = 0.5      # a looped cycle's last pose may differ from its first by this much (degrees) ...
LOOP_STUDS = 0.005  # ... or this much (studs): more is a jump every time it comes round


def table(per_frame, joints, fps):
    """per_frame: {frame: {group: value}} (rbx_cycle.frames); joints: {group: {"name", "kind", ...}}.
    -> {"fps", "joints": [joint names], "kinds": [...], "times": [seconds from the first frame], "values": [[a
    value a joint] a time]} - every frame, not yet thinned. EVERY moving joint of `joints` is in it: one the cycle
    never keys stands at rest (0) throughout - as the build poses it when it checks the cycle, so the game plays
    what was checked whatever an earlier cycle left behind."""
    frames = sorted(per_frame)
    groups = sorted((g for g, j in joints.items() if j.get("kind") != "fixed"), key=lambda g: joints[g]["name"])
    f0 = frames[0]
    return {"fps": int(fps), "joints": [joints[g]["name"] for g in groups],
            "kinds": [joints[g]["kind"] for g in groups],
            "times": [round((f - f0) / float(fps), 6) for f in frames],
            "values": [[round(float(per_frame[f].get(g, 0.0)), 5) for g in groups] for f in frames]}


def _tols(t):
    """how far each joint may stray: the fixed bar, or a share of its own travel when that is smaller"""
    out = []
    for j, kind in enumerate(t["kinds"]):
        col = [row[j] for row in t["values"]]
        travel = max(col) - min(col)
        out.append(min(TOL_DEG if kind == "hinge" else TOL_STUDS, TOL_OF_TRAVEL * travel) if travel > 0 else 0.0)
    return out


def thin(t):
    """the table with only the keys it needs: a time is dropped when a straight line between the keys kept either
    side of it stands within the tolerance of every joint's value there (greedy, from the first key; the first and
    the last always stay). -> the same shape, fewer times"""
    times, values, kinds = t["times"], t["values"], t["kinds"]
    n = len(times)
    if n <= 2:
        return dict(t)
    kept = [0]
    a = 0
    tols = _tols(t)
    while a < n - 1:
        b = a + 1
        # push b as far as a straight line a..b still stands in for everything between
        while b + 1 < n and b + 1 - a <= WINDOW:
            c, ok = b + 1, True
            span = times[c] - times[a]
            for m in range(a + 1, c):
                w = (times[m] - times[a]) / span if span > 0 else 0.0
                for j in range(len(kinds)):
                    line = values[a][j] + (values[c][j] - values[a][j]) * w
                    if abs(line - values[m][j]) > tols[j] + 1e-12:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
            b = c
        kept.append(b)
        a = b
    return {**t, "times": [times[i] for i in kept], "values": [values[i] for i in kept]}


def at(t, seconds, loop=False):
    """every joint's value at a time (what src/kit/ModelRules.cycleAt does in the game): a straight line between
    the two keys round it; before the first key or after the last, that key - or, looped, round again"""
    times, values = t["times"], t["values"]
    length = times[-1]
    s = float(seconds)
    if loop and length > 0:
        s = s % length
    if s <= times[0]:
        return list(values[0])
    if s >= length:
        return list(values[-1])
    for i in range(len(times) - 1):
        if times[i] <= s <= times[i + 1]:
            span = times[i + 1] - times[i]
            w = (s - times[i]) / span if span > 0 else 1.0
            return [a + (b - a) * w for a, b in zip(values[i], values[i + 1])]
    return list(values[-1])


def worst(full, thinned):
    """how far the thinned table strays from the full one at the full one's own times -> (the largest difference in
    a hinge, degrees; in a slide, studs)"""
    deg = studs = 0.0
    for s, row in zip(full["times"], full["values"]):
        got = at(thinned, s)
        for j, kind in enumerate(full["kinds"]):
            d = abs(got[j] - row[j])
            if kind == "hinge":
                deg = max(deg, d)
            else:
                studs = max(studs, d)
    return deg, studs


def loop_problem(t):
    """a cycle said to LOOP must end where it began -> None, or which joint jumps and by how much"""
    first, last = t["values"][0], t["values"][-1]
    for name, kind, a, b in zip(t["joints"], t["kinds"], first, last):
        if kind == "hinge":   # (a whole turn on is the same place: a wheel spun 0 -> 360 loops without a jump)
            off = abs(a - b) % 360.0
            if min(off, 360.0 - off) <= LOOP_DEG:
                continue
        if abs(a - b) > (LOOP_DEG if kind == "hinge" else LOOP_STUDS):
            unit = "degrees" if kind == "hinge" else "studs"
            return (f"{name} ends at {b:g} and begins at {a:g} {unit}: it would jump {abs(a - b):g} {unit} every "
                    "time the cycle comes round - key it back to where it began, or do not loop it")
    return None


def blend(frm, to, w):
    """the game's fade, as src/kit/ModelRules.blend: a joint the new cycle moves eases from where it was (or jumps
    there, if it was not moving), one it does not eases back to rest - smoothstep in time, a straight line in the
    joints' values -> {joint: value}"""
    e = min(max(float(w), 0.0), 1.0)
    e = e * e * (3 - 2 * e)
    out = {}
    for name, b in to.items():
        a = frm.get(name)
        out[name] = b if a is None else a + (b - a) * e
    for name, a in frm.items():
        if name not in out:
            out[name] = a * (1 - e)
    return out


FADE_STEPS = (0.2, 0.4, 0.6, 0.8)   # where on its line a fade is posed (its two ends are the cycles' own poses)
FADE_FROM = 6                       # a looped cycle is cut off anywhere: this many of its moments faded FROM


def fades(cycles, joints=()):
    """THE FADES A GAME PLAYS (Models.play(..., {fade = s})): into every cycle's first pose from rest, from a
    one-shot's last pose (it ends before the next plays), and from FADE_FROM moments of a looped one (cut off
    anywhere). The game fades from EVERY joint as it stands (src/kit/Models.play: each Motor6D's value, 0 at rest):
    joints - every joint's key, 0 where the cycle faded from does not move it.
    cycles: [(name, loop, {frame: {joint: value}})] -> [(label, {step: {joint: value}})]"""
    zero = {j: 0.0 for j in joints}
    out = []
    for name_b, _loop_b, pf_b in cycles:
        to = pf_b[min(pf_b)]
        starts = [("rest", dict(zero))]
        for name_a, loop_a, pf_a in cycles:
            fr = sorted(pf_a)
            picks = ([fr[int(round(i * (len(fr) - 1) / max(FADE_FROM - 1, 1)))] for i in range(FADE_FROM)]
                     if loop_a else [fr[-1]])
            starts += [(f"{name_a} at frame {f}", {**zero, **pf_a[f]}) for f in dict.fromkeys(picks)]
        for label, frm in starts:
            out.append((f"from {label} into {name_b}", {k: blend(frm, to, w) for k, w in enumerate(FADE_STEPS)}))
    return out
