"""A MODEL'S OWN RIG, SOLVED (the owner's method lists, 2026-11-13: "IK", "constraints", "skeletons / hierarchy /
bone placement"; the 3D methods audit, stage R: "IK for a model's parts: missing").

A kit model's rig is a CHAIN OF JOINTS between rigid groups - a crane's boom on its turret, an excavator's arm, a
desk lamp, a walker's leg: each joint a hinge about an axis through a pivot (degrees) or a slide along an axis
(studs), each with its limits, each carried by the one before it. Posing such a chain by hand is guessing three
numbers to put its tip somewhere. INVERSE KINEMATICS is asking for the tip's place and getting the numbers:
here by cyclic coordinate descent - joint by joint from the tip back, each turned (or slid) to bring the tip
nearest the target, held to its limits, round and round until the tip is there or no longer moves.
Pure numpy; the game's twin is src/kit/ModelRules.reach (the same steps, numbers only)."""

import numpy as np

ROUNDS = 200       # times round the chain at most, from one start
NEAR = 1e-3        # studs: the tip is THERE
MET = 0.02         # studs: near enough to stop looking for a better start
STARTS = 12        # fresh starts tried when the first does not get there (the review: one start from zero gave
#                    up on one reachable place in six - a straight arm cannot bend toward a place on its own line)


def _starts(lo, hi, count):
    """the fresh starts, the same every time and the same in the game's twin: values spread inside the limits by
    a small fixed generator (Park - Miller; exact in a double)"""
    x = 20261115
    out = []
    for _ in range(count):
        row = []
        for a_, b_ in zip(lo, hi):
            x = (x * 16807) % 2147483647
            row.append(a_ + (b_ - a_) * (x / 2147483647.0))
        out.append(row)
    return out


def _rot(axis, deg):
    """the turn about a unit axis by degrees -> (3, 3)"""
    a = np.asarray(axis, float)
    a = a / max(float(np.linalg.norm(a)), 1e-30)
    t = np.radians(float(deg))
    c, s = np.cos(t), np.sin(t)
    x, y, z = a
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                     [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                     [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])


def forward(chain, values, tip):
    """where a chain's tip is with its joints at `values` -> (tip (3,), frames: each joint's (pivot, axis) as
    posed). chain: joints from the base outward, each {"kind": "hinge" | "slide", "pivot": (3,), "axis": (3,),
    "min", "max"} in the REST pose (the model's frame); tip: the point carried by the last joint, at rest."""
    R, t = np.eye(3), np.zeros(3)                     # the transform everything past the joints so far has taken
    frames = []
    for j, v in zip(chain, values):
        pivot = R @ np.asarray(j["pivot"], float) + t
        axis = R @ np.asarray(j["axis"], float)
        axis = axis / max(float(np.linalg.norm(axis)), 1e-30)
        frames.append((pivot, axis))
        if j["kind"] == "slide":
            t = t + axis * float(v)
        else:
            turn = _rot(axis, v)
            R, t = turn @ R, turn @ (t - pivot) + pivot
    return R @ np.asarray(tip, float) + t, frames


def _descend(chain, tip, goal, values, lo, hi, rounds, near):
    """one start, run down: round the chain from the tip back until the tip is there or has stopped moving"""
    values = np.array(values, float)
    at, _ = forward(chain, values, tip)
    miss, used = float(np.linalg.norm(goal - at)), 0
    for used in range(1, int(rounds) + 1):
        for i in range(len(chain) - 1, -1, -1):
            at, frames = forward(chain, values, tip)
            pivot, axis = frames[i]
            if chain[i]["kind"] == "slide":
                step = float((goal - at) @ axis)
            else:
                a = (at - pivot) - axis * float((at - pivot) @ axis)        # the tip and the goal, seen along
                b = (goal - pivot) - axis * float((goal - pivot) @ axis)    # the joint's own axis
                if np.linalg.norm(a) < 1e-9 or np.linalg.norm(b) < 1e-9:
                    continue
                step = float(np.degrees(np.arctan2(float(np.cross(a, b) @ axis), float(a @ b))))
            values[i] = float(np.clip(values[i] + step, lo[i], hi[i]))
        at, _ = forward(chain, values, tip)
        now = float(np.linalg.norm(goal - at))
        still = abs(miss - now) < 1e-7
        miss = now
        if now < near or still:
            break
    return values, miss, used


def reach(chain, tip, target, start=None, rounds=ROUNDS, near=NEAR):
    """the joint values that put the chain's tip nearest `target` -> {"values", "miss": studs left, "rounds",
    "held": the joints sitting on a limit, "starts": how many starts it took}. start: the values to begin from
    (default: each joint's 0, held to its limits) - when that does not get there, fresh starts are tried and the
    best kept. A joint's limits may be given either way round."""
    lo = np.array([min(float(j["min"]), float(j["max"])) for j in chain])
    hi = np.array([max(float(j["min"]), float(j["max"])) for j in chain])
    goal = np.asarray(target, float)
    first = np.clip(np.zeros(len(chain)) if start is None else np.asarray(start, float), lo, hi)
    best, tried = None, 0
    for begin in [first] + _starts(lo, hi, STARTS):
        tried += 1
        values, miss, used = _descend(chain, tip, goal, begin, lo, hi, rounds, near)
        if best is None or miss < best[1]:
            best = (values, miss, used)
        if best[1] <= MET:
            break
    values, miss, used = best
    held = [i for i in range(len(chain)) if hi[i] - lo[i] < 359.999 and
            (values[i] <= lo[i] + 1e-6 or values[i] >= hi[i] - 1e-6)]
    return {"values": [round(float(v), 4) for v in values], "miss": round(miss, 4), "rounds": used, "held": held,
            "starts": tried}


def span(chain, tip):
    """how far a chain can reach from its first pivot at most: the lengths between its hinges (and from the last
    to the tip), and its slides' travel -> studs (a target further than this from the first pivot can never be
    met). A slide's own pivot is no elbow: it adds its travel, not a link."""
    hinges = [np.asarray(j["pivot"], float) for j in chain if j["kind"] != "slide"]
    pts = ([np.asarray(chain[0]["pivot"], float)] if chain and chain[0]["kind"] == "slide" else []) + hinges + \
        [np.asarray(tip, float)]
    links = sum(float(np.linalg.norm(b - a)) for a, b in zip(pts[:-1], pts[1:]))
    slides = sum(max(abs(float(j["min"])), abs(float(j["max"]))) for j in chain if j["kind"] == "slide")
    return links + slides


SWEEP_BUDGET = 60000   # poses tried at most by the sweep that PROVES a place out of reach (every joint stepped)
SWEEP_JOINTS = 4       # longer chains are not swept: their reason stays the solver's guess, said as that


def _rot_many(axes, degs):
    """turns about unit axes (m, 3) by degrees (m,) -> (m, 3, 3)"""
    a = axes / np.maximum(np.linalg.norm(axes, axis=1, keepdims=True), 1e-30)
    t = np.radians(degs)
    c, s_, k = np.cos(t), np.sin(t), 1 - np.cos(t)
    x, y, z = a[:, 0], a[:, 1], a[:, 2]
    return np.stack([np.stack([c + x * x * k, x * y * k - z * s_, x * z * k + y * s_], 1),
                     np.stack([y * x * k + z * s_, c + y * y * k, y * z * k - x * s_], 1),
                     np.stack([z * x * k - y * s_, z * y * k + x * s_, c + z * z * k], 1)], 1)


def forward_many(chain, values, tip):
    """`forward` for many poses at once: values (m, n) -> the tips (m, 3)"""
    v = np.asarray(values, float)
    m = len(v)
    R = np.tile(np.eye(3), (m, 1, 1))
    t = np.zeros((m, 3))
    for i, j in enumerate(chain):
        pivot = np.einsum("mij,j->mi", R, np.asarray(j["pivot"], float)) + t
        axis = np.einsum("mij,j->mi", R, np.asarray(j["axis"], float))
        axis = axis / np.maximum(np.linalg.norm(axis, axis=1, keepdims=True), 1e-30)
        if j["kind"] == "slide":
            t = t + axis * v[:, i:i + 1]
        else:
            turn = _rot_many(axis, v[:, i])
            R = turn @ R
            t = np.einsum("mij,mj->mi", turn, t - pivot) + pivot
    return np.einsum("mij,j->mi", R, np.asarray(tip, float)) + t


def nearest_bound(chain, tip, target, lo, hi, budget=SWEEP_BUDGET):
    """every joint stepped through [lo, hi] -> (the nearest the tip came, a LOWER BOUND on the nearest it can come
    anywhere in those limits: the sweep's nearest less the furthest the tip can move inside one step of the grid -
    each hinge's half step times its lever, each slide's half step), or None for a chain too long to sweep"""
    n = len(chain)
    if not 1 <= n <= SWEEP_JOINTS:
        return None
    per = max(3, int(budget ** (1.0 / n)))
    axes = [np.linspace(a_, b_, per) if b_ > a_ else np.array([a_]) for a_, b_ in zip(lo, hi)]
    grid = np.stack([g_.ravel() for g_ in np.meshgrid(*axes, indexing="ij")], 1)
    miss = np.linalg.norm(forward_many(chain, grid, tip) - np.asarray(target, float), axis=1)
    slack = 0.0
    for i, (j, ax_) in enumerate(zip(chain, axes)):
        half = (float(ax_[1] - ax_[0]) / 2.0) if len(ax_) > 1 else 0.0
        slack += half if j["kind"] == "slide" else np.radians(half) * span(chain[i:], tip)
    best = float(miss.min())
    return best, best - slack


BNB_BUDGET = 200000   # joint-value boxes looked at, at most, by the branch-and-bound proof
TIGHT = 0.5           # a box is ruled out only past this share of the nearest pose found: a bound worth saying


def prove_far(chain, tip, target, lo, hi, near, budget=None):
    """BRANCH AND BOUND - a chain of ANY length (his V3 list, 3D stage G.1d: the grid sweep stops at SWEEP_JOINTS, and
    its even grid cannot rule out a place just past `near`): the box of joint values [lo, hi] is split, the widest
    side (by how far it moves the tip) first, and a box is RULED OUT when the tip at its centre misses by more than
    the furthest the tip can move inside it (each hinge's half width times its lever, each slide's half width - the
    sweep's own bound) plus `near` (and TIGHT of the nearest found, so the bound said is not a loose one). -> (the
    nearest pose found, a PROVEN lower bound on the nearest any pose comes -
    None when the budget ran out first, met: a pose within `near` was found)"""
    budget = BNB_BUDGET if budget is None else budget
    lever = np.array([1.0 if j["kind"] == "slide" else float(np.radians(1.0)) * span(chain[i:], tip)
                      for i, j in enumerate(chain)])
    L, H = np.array([lo], float), np.array([hi], float)
    goal = np.asarray(target, float)
    best, bound, seen = float("inf"), float("inf"), 0
    while len(L):
        if seen + len(L) > budget:
            return best, None, False
        half = (H - L) / 2.0
        miss = np.linalg.norm(forward_many(chain, L + half, tip) - goal, axis=1)
        seen += len(L)
        best = min(best, float(miss.min()))
        if best <= near:
            return best, None, True
        low = miss - half @ lever
        out = low > max(near, TIGHT * best)   # (TIGHT: the bound said is at least that share of the nearest found)
        if out.any():
            bound = min(bound, float(low[out].min()))
        L, H, half = L[~out], H[~out], half[~out]
        if not len(L):
            break
        d = np.argmax(half * lever, axis=1)
        k = np.arange(len(L))
        mid = (L[k, d] + H[k, d]) / 2.0
        L2, H1 = L.copy(), H.copy()
        H1[k, d] = mid
        L2[k, d] = mid
        L, H = np.vstack([L, L2]), np.vstack([H1, H])
    return best, bound, False


def planar_bound(chain, tip, target):
    """a FLAT chain - every hinge's axis parallel (a lamp's arm, a crane's boom past its turret): no turn about that
    axis moves anything along it, only a slide does (by its travel times how far it points along it) -> the exact
    nearest the tip can come to the target along that axis at ANY angle (studs), or None when the hinges are not all
    parallel. What branch and bound cannot afford for a long chain with its hinges free all round, this proves."""
    hinges = [np.asarray(j["axis"], float) / max(float(np.linalg.norm(j["axis"])), 1e-30)
              for j in chain if j["kind"] != "slide"]
    if not hinges:
        return None
    a = hinges[0]
    if any(abs(abs(float(h @ a)) - 1.0) > 1e-6 for h in hinges):
        return None
    lo_ = hi_ = float(np.asarray(tip, float) @ a)
    for j in chain:
        if j["kind"] == "slide":
            ax = np.asarray(j["axis"], float)
            k = float(ax @ a) / max(float(np.linalg.norm(ax)), 1e-30)
            ends = (k * float(j["min"]), k * float(j["max"]))
            lo_, hi_ = lo_ + min(ends), hi_ + max(ends)
    at = float(np.asarray(target, float) @ a)
    return max(0.0, lo_ - at, at - hi_)


TURRET_STEPS = 7200   # the turret's angles stepped by turret_planar_bound (its slack: the lever times half a step)


def turret_planar_bound(chain, tip, target, lo0, hi0):
    """a TURRET carrying a flat chain (a crane, an excavator, a desk lamp: the first joint a hinge, every hinge after
    it parallel): at each angle of the turret in [lo0, hi0] the flat chain's plane bounds how near the tip comes
    (planar_bound); stepped finely, less the most the target can move between two steps -> a PROVEN lower bound at
    any angle of the joints after it (their limits relaxed), or None for another layout"""
    if len(chain) < 2 or chain[0]["kind"] == "slide":
        return None
    rest = chain[1:]
    if planar_bound(rest, tip, target) is None:
        return None
    p = np.asarray(chain[0]["pivot"], float)
    a = np.asarray(chain[0]["axis"], float)
    a = a / max(float(np.linalg.norm(a)), 1e-30)
    hinges = [np.asarray(j["axis"], float) for j in rest if j["kind"] != "slide"]
    b = hinges[0] / max(float(np.linalg.norm(hinges[0])), 1e-30)
    if abs(abs(float(a @ b)) - 1.0) < 1e-6:
        return None          # (the turret turns in the same plane: the chain is flat - planar_bound's own case)
    lo_, hi_ = min(float(lo0), float(hi0)), max(float(lo0), float(hi0))
    angles = np.linspace(lo_, hi_, TURRET_STEPS) if hi_ > lo_ else np.array([lo_])
    rel = np.asarray(target, float) - p
    lever = float(np.linalg.norm(rel - a * float(rel @ a)))      # the target's distance from the turret's axis
    tips_t = (_rot_many(np.tile(a, (len(angles), 1)), -angles) @ rel) + p   # the target in the turret's frame
    plane = [planar_bound(rest, tip, q) for q in tips_t]
    step = float(np.radians(angles[1] - angles[0])) if len(angles) > 1 else 0.0
    return float(min(plane)) - lever * step / 2.0


def _relaxed(chain, tip, target, lo, hi):
    """the exact bounds that hold whatever the later joints' limits: a flat chain's plane, a turret's sweep"""
    out = [x for x in (planar_bound(chain, tip, target), turret_planar_bound(chain, tip, target, lo[0], hi[0]))
           if x is not None]
    return max(out) if out else None


def _proof(chain, tip, target, lo, hi, near):
    """the grid sweep where it rules the place out, else branch and bound, else the layout's exact bounds -> (nearest
    found, lower bound or None, met)"""
    grid = nearest_bound(chain, tip, target, lo, hi)
    if grid is not None and grid[1] > near:
        return grid[0], grid[1], False
    best, bound, met = prove_far(chain, tip, target, lo, hi, near)
    if grid is not None:
        best = min(best, grid[0])
    if not met and (bound is None or bound <= near):
        rel = _relaxed(chain, tip, target, lo, hi)
        if rel is not None and rel > near:
            bound = rel if bound is None else max(bound, rel)
    return best, bound, met


def problem(name, found, target, chain, tip, near=0.02):
    """a pose the chain cannot take -> a sentence, or None. The reason is PROVEN where it can be (card ver5: it was
    the solver's best guess): past the chain's length; else every joint swept through its limits - no pose there
    comes nearer than a bound - and swept again with the hinges free all round, which tells the limits from the
    way the chain turns. A chain too long to sweep, or a sweep that cannot rule a pose out, keeps the guess and
    says so"""
    if found["miss"] <= near:
        return None
    first = np.asarray(chain[0]["pivot"], float)
    far = float(np.linalg.norm(np.asarray(target, float) - first))
    reach_ = span(chain, tip)
    head = f"{name}: the tip stops {found['miss']:.2f} studs short of its target - "
    if far > reach_:
        return head + f"it lies {far:.2f} studs from the first joint and the chain is {reach_:.2f} long"
    lo = [min(float(j["min"]), float(j["max"])) for j in chain]
    hi = [max(float(j["min"]), float(j["max"])) for j in chain]
    near_h, bound_h, met = _proof(chain, tip, target, lo, hi, near)
    guess = "its joints' limits stop it" if found["held"] else "the chain cannot fold that way"
    if met:   # (the solver's fault, not the chain's: said as that)
        return head + (f"yet a pose inside its limits comes within {near_h:.3f} studs (found by the sweep): the "
                       "solver missed it - a kit fault (rbx_ik), not the chain's")
    if bound_h is None:
        return head + (f"{guess} (the solver's reading, not proven: the proof for a chain of {len(chain)} joints "
                       f"ran out of its budget, nearest {near_h:.2f} studs)")
    held = (near_h, bound_h)
    free_lo = [-180.0 if j["kind"] != "slide" else a_ for j, a_ in zip(chain, lo)]
    free_hi = [180.0 if j["kind"] != "slide" else b_ for j, b_ in zip(chain, hi)]
    # with the hinges free all round: the solver first - a pose it finds within the bar PROVES the chain gets there
    free_chain = [dict(j, min=a_, max=b_) for j, a_, b_ in zip(chain, free_lo, free_hi)]
    solved = reach(free_chain, tip, target)
    if solved["miss"] <= near:
        free, met_f = (solved["miss"], float("-inf")), True
    else:
        near_f, bound_f, met_f = _proof(chain, tip, target, free_lo, free_hi, near)
        free = (min(near_f, solved["miss"]), bound_f if bound_f is not None else float("-inf"))
    if met_f:   # (a pose with the hinges free all round was FOUND within the bar: the limits are what stop it)
        return head + (f"its joints' limits stop it, proven: no pose inside them comes nearer than "
                       f"{held[1]:.2f} studs (every pose inside them ruled out), and with the hinges free all round the tip gets there")
    if free[1] > near:
        return head + (f"the chain cannot turn its tip there at any angle, proven: nearer than {free[1]:.2f} studs it "
                       "never comes (every angle of its joints ruled out) - the place is off the way its joints turn")
    return head + (f"no pose inside its limits comes nearer than {held[1]:.2f} studs, proven (every pose inside them ruled out); "
                   "which of the limits or the joints' layout stops it is not proven")
