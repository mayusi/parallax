#!/usr/bin/env python3
"""PIECES THAT COME TO REST AND MEET (the owner's methods list: Rigid body simulation; the VFX methods audit, stages
10 and 23).

A fracture plan's pieces (kit/vfx/fracture.py) flew by the debris layer's old flight: gravity, one soft bounce, then
they SHRANK away in mid-tumble. A slab that breaks leaves its pieces on the ground. With `"rest": true` on a debris
layer that flies `"pieces"`, every piece falls, bounces losing most of its speed, slides to a stop, tips onto a flat
face and LIES there until the layer's life ends (it fades out over the last 15 %, it does not shrink).

    lune run kit vfx settle <plan> [--life 2.5] [--gravity 120] [--speed 30] [--height 0] [--fps <one rate>] [--plans-dir assets/effects/fractures]

flies the plan's pieces TOGETHER by the rule, at 30, 60 and 144 frames a second (pieces that meet land a little
differently at each: where two touch decides who gives way), and says when the LAST one comes to rest (the latest
of the three), how far the furthest lies from where it sat and how many lie on another. It fails when a piece is
not at rest by the time the fade starts (85 % of --life) at any of the three: a layer with that life would fade
pieces out in mid-move, and says the life that does do (found by flying them for long); and when two pieces at
rest lie in each other. --height is how far above the floor (the effect's origin) the layer's `point` puts the
slab: a slab up high lands later. It writes nothing.

THE RULE (`step`; the game's `debrisStep` in src/kit/VfxStage.luau and the player's in kit/vfx/player/player.js are
the same arithmetic, held to it by kit/selftest/vfx/settle/run.py parity). A piece's state is eleven numbers:
x, y, z, vx, vy, vz, tilt, yaw, tilt speed, yaw speed, at rest (0 / 1). One step of `dt` seconds:
- gravity, then the move; the tilt and the yaw turn by their speeds;
- the piece's half height as it lies NOW is |cos tilt| x half its thickness + |sin tilt| x half its width; when its
  middle is lower than that above the floor it is put ON the floor;
- a real hit (falling faster than two steps of gravity) bounces back 0.3 of the fall, keeps 0.6 of its sideways
  speed and half its tumble; anything slower is no bounce: the piece is on the ground;
- on the ground it slides to a stop (its speed dies by 6 a second), stops tumbling and tips to the NEAREST flat face
  (a whole turn of pi); slow enough and flat enough, it is at rest: it does not move again.

PIECES MEET (`meet`, stage 23; the game's and the player's `debrisMeet`): all the pieces that have left the slab
take one step together. Before each piece's own `step`:
- what it lies ON: the floor, or the top of a piece that is ON THE GROUND (not falling) whose outline holds this
  piece's middle and whose top is at or under this piece's underside (a falling piece is caught by a top it passed
  in this step, however fast it falls). A piece at rest whose floor has gone is not at rest: it falls;
- two pieces on the ground whose heights overlap and whose outlines lie IN each other by over SKIN are pushed
  apart along the shortest way out (their real convex outlines as they lie: mirrored on the other face, turned by
  the yaw), until they lie half of SKIN deep, the lighter (smaller area) giving way more, by at most PART x dt a
  step (dt taken as 1/30 s at most): a slide, not a jump. A piece that was pushed in a step is not at rest in it;
  pushes on one piece that cancel (it is jammed between others) move it nowhere, and it can rest - so a jammed
  pile can end up to twice SKIN deep. Pieces that only touch are left alone. Only a piece lying FLAT holds another
  up. SKIN and PART are in the plan's own studs: a play at another scale is the same flight, larger.

Still NOT a rigid-body solver: pieces do not meet in the air (they pass through each other until both are on the
ground, so one can sink into another as it lands and then slide out of it), a meeting never turns or tips a piece
and passes no speed on, a piece lies on another only whole (its middle over it: never propped on an edge, and its
corners can hang over nothing), the floor is one flat height (the effect's origin), a piece tips about one axis
only. Where two pieces meet depends on the frame rate by a little, so the piles differ between 30, 60 and 144
frames a second (the last rest by a few tenths of a second). Roblox's own physics (unanchored parts) would do the
real thing in the game and nothing in the browser player; this rule is the same in both.
"""
import json
import math
import os
import sys

PLANS = os.path.join("assets", "effects", "fractures")
BOUNCE, GRIP, TUMBLE, YAW_KEEP = 0.3, 0.6, 0.5, 0.6  # of the fall kept as bounce; of the sideways speed, the tumble and the yaw kept at a hit
SLIDE, TIP = 6.0, 10.0                               # a second: how fast a slide dies and a tilt falls flat
STILL = 0.004                                        # x gravity: slower than this on the ground is still
FLAT = 0.01                                          # radians from flat that count as lying
FADE = 0.85                                          # the share of the layer's life at which pieces at rest start to fade
RATES = (30, 60, 144)                                # frames a second a life is tried at (pieces that meet land a little differently at each)


def step(s, dt, g, floor, hy, hw):
    """one piece, one step -> its new state (a new list)"""
    x, y, z, vx, vy, vz, tilt, yaw, wt, wy, rest = s
    if rest == 1:
        return list(s)
    vy = vy - g * dt
    x = x + vx * dt
    y = y + vy * dt
    z = z + vz * dt
    tilt = tilt + wt * dt
    yaw = yaw + wy * dt
    h = abs(math.cos(tilt)) * hy + abs(math.sin(tilt)) * hw
    if y <= floor + h:
        y = floor + h
        if vy < 0:
            if -vy > g * dt * 2:
                vy = -vy * BOUNCE
                vx = vx * GRIP
                vz = vz * GRIP
                wt = wt * TUMBLE
                wy = wy * YAW_KEEP
            else:
                vy = 0
        if vy == 0:
            k = max(0, 1 - SLIDE * dt)
            vx = vx * k
            vz = vz * k
            wy = wy * k
            wt = 0
            target = math.floor(tilt / math.pi + 0.5) * math.pi
            tilt = tilt + (target - tilt) * min(1, TIP * dt)
            y = floor + abs(math.cos(tilt)) * hy + abs(math.sin(tilt)) * hw
            if math.sqrt(vx * vx + vz * vz) < g * STILL and abs(target - tilt) < FLAT:
                rest = 1
                tilt = target
                vx = 0
                vz = 0
                wy = 0
                y = floor + hy
    return [x, y, z, vx, vy, vz, tilt, yaw, wt, wy, rest]


SKIN = 0.02   # studs: two pieces at rest may lie this deep in each other (pieces that only touch are left alone)
PART = 8.0    # studs a second: how fast two pieces that lie in each other are pushed apart (a slide, not a jump)
NUDGE = 0.001 # studs: pushes on one piece that cancel to under this in a step are not a push (a jammed pile is at rest)
HITCH = 1 / 30  # seconds: the longest step a push is sized for (a frame that hangs does not throw pieces apart)


def lying(s, shape, turn=0.0):
    """the outline of a piece as it lies on the ground: its own flat points [x, z, x, z ...] mirrored when it lies
    on its other face, THEN turned by its yaw and by the yaw of the frame the slab is played in (`turn`: the piece
    is drawn frame x yaw x tilt, so the mirror is about its OWN z) -> [x, z, x, z ...] in the world"""
    flip = math.floor(s[6] / math.pi + 0.5) % 2 != 0
    c, n = math.cos(s[7] + turn), math.sin(s[7] + turn)
    out = []
    for k in range(0, len(shape), 2):
        px, pz = shape[k], shape[k + 1]
        if flip:
            pz = -pz
        out.append(s[0] + px * c + pz * n)
        out.append(s[2] - px * n + pz * c)
    return out


def within(poly, x, z):
    """is the place inside the convex outline (either way round)"""
    pos, neg, n = False, False, len(poly)
    for k in range(0, n, 2):
        ax, az = poly[k], poly[k + 1]
        bx, bz = poly[(k + 2) % n], poly[(k + 3) % n]
        cr = (bx - ax) * (z - az) - (bz - az) * (x - ax)
        if cr > 0:
            pos = True
        elif cr < 0:
            neg = True
    return not (pos and neg)


def apart(a, b):
    """two convex outlines -> (how deep they lie in each other, the way a must go to get out: x, z); 0 = they do not"""
    best, bx, bz = math.inf, 0.0, 0.0
    for poly in (a, b):
        n = len(poly)
        for k in range(0, n, 2):
            ex, ez = poly[(k + 2) % n] - poly[k], poly[(k + 3) % n] - poly[k + 1]
            ln = math.sqrt(ex * ex + ez * ez)
            if ln < 1e-9:
                continue
            nx, nz = ez / ln, -ex / ln
            a0, a1, b0, b1 = math.inf, -math.inf, math.inf, -math.inf
            for q in range(0, len(a), 2):
                d = a[q] * nx + a[q + 1] * nz
                a0, a1 = min(a0, d), max(a1, d)
            for q in range(0, len(b), 2):
                d = b[q] * nx + b[q + 1] * nz
                b0, b1 = min(b0, d), max(b1, d)
            o = min(a1, b1) - max(a0, b0)
            if o <= 0:
                return 0.0, 0.0, 0.0
            if o < best - 1e-9:   # (two ways out as deep as each other: the first, in every runtime)
                best = o
                if a0 + a1 < b0 + b1:
                    bx, bz = -nx, -nz
                else:
                    bx, bz = nx, nz
    if best == math.inf:
        return 0.0, 0.0, 0.0
    return best, bx, bz


def meet(S, shapes, H, W, A, dt, g, base, turn=0.0, unit=1.0):
    """ALL the pieces that have left the slab, one step: what each lies ON (the floor, or the top of a piece that is
    on the ground under its middle), pieces on the ground that lie IN each other pushed apart, then every piece's own
    `step` -> (the new states, the floor under each)

    S: the states; shapes: each piece's flat outline about its state's x, z; H, W: half its thickness and half its
    width (as `step`); A: its area (the lighter of two gives way more); base: the ground's height; turn: the yaw of
    the frame the slab is played in; unit: studs to one of the plan's (the play's scale: SKIN, PART and NUDGE are
    the plan's, so a play at any scale is the same flight, larger)."""
    n = len(S)
    S = [list(s) for s in S]
    mvx, mvz = [0.0] * n, [0.0] * n
    skin, push_most = SKIN * unit, PART * unit * min(dt, HITCH)
    half = [abs(math.cos(S[i][6])) * H[i] + abs(math.sin(S[i][6])) * W[i] for i in range(n)]
    poly = [lying(S[i], shapes[i], turn) for i in range(n)]
    lies = [abs(S[i][6] - math.floor(S[i][6] / math.pi + 0.5) * math.pi) < FLAT for i in range(n)]
    reach = []
    for i in range(n):
        r = 0.0
        for k in range(0, len(shapes[i]), 2):
            r = max(r, shapes[i][k] * shapes[i][k] + shapes[i][k + 1] * shapes[i][k + 1])
        reach.append(math.sqrt(r))
    order = list(range(n))   # from the lowest up: what a piece lies on is always lower than it
    for a in range(1, n):
        k = order[a]
        b = a - 1
        while b >= 0 and S[order[b]][1] > S[k][1]:
            order[b + 1] = order[b]
            b -= 1
        order[b + 1] = k
    floor = [base] * n
    down = [False] * n
    pushed = [False] * n
    for a in range(n):
        i = order[a]
        bottom = S[i][1] - half[i]
        fell = max(0.0, -S[i][4] * dt)   # (a falling piece is caught by a top it passed in this step)
        for b in range(a):
            j = order[b]
            top = S[j][1] + half[j]
            if down[j] and lies[j] and top > floor[i] and top <= bottom + fell + 1e-6 and within(poly[j], S[i][0], S[i][2]):
                floor[i] = top
        down[i] = S[i][4] == 0 and bottom <= floor[i] + 1e-6
        if S[i][10] == 1 and abs(bottom - floor[i]) > 1e-6:
            S[i][10] = 0   # what it lay on has gone (or come): it is not at rest
    for i in range(n):
        for j in range(i + 1, n):
            if not (down[i] and down[j]):
                continue
            if min(S[i][1] + half[i], S[j][1] + half[j]) - max(S[i][1] - half[i], S[j][1] - half[j]) <= 1e-4:
                continue   # one lies ON the other, or over it
            dx, dz = S[i][0] - S[j][0], S[i][2] - S[j][2]
            if dx * dx + dz * dz >= (reach[i] + reach[j]) * (reach[i] + reach[j]):
                continue
            deep, nx, nz = apart(poly[i], poly[j])
            if deep <= skin + 1e-9:
                continue
            m = min(deep - skin / 2, push_most)   # (parted to HALF the skin: a pair just parted is not at the edge of being pushed again)
            wi = A[j] / (A[i] + A[j])
            mi, mj = m * wi, m * (1 - wi)
            mvx[i] += nx * mi   # (all the pushes of a step are worked out from where the pieces lay at its start, and added)
            mvz[i] += nz * mi
            mvx[j] -= nx * mj
            mvz[j] -= nz * mj
    for i in range(n):
        d = math.sqrt(mvx[i] * mvx[i] + mvz[i] * mvz[i])
        if d > NUDGE * unit:   # pushes that cancel (a piece jammed between others) move nothing: it can be at rest
            k = min(1.0, push_most / d)
            S[i][0] += mvx[i] * k
            S[i][2] += mvz[i] * k
            pushed[i] = True
            S[i][10] = 0
    out = [step(S[i], dt, g, floor[i], H[i], W[i]) for i in range(n)]
    for i in range(n):
        if pushed[i]:
            out[i][10] = 0   # (a piece that is being pushed is not at rest, however slow it is)
    return out, floor


def start(piece, thick, push=1.0, height=0.0):
    """a plan's piece as it sits in the slab (`height` above the floor) -> (state, hy, hw, its flat outline)
    The state's x, z is the middle of the piece's BOX (the game's MeshPart and the player's mesh sit and turn there).
    `push` scales the plan's SPIN as well as its speed (a slab played slow turned its pieces as fast as ever - into
    each other: a review leftover of stage 23)"""
    xs = [q[0] for q in piece["points"]]
    zs = [q[1] for q in piece["points"]]
    ox, oz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    hw = max(max(zs) - min(zs), 0.05) / 2  # (it tips about its own X: the side that stands up is its Z)
    v = piece["vel"]
    sp = piece["spin"]
    shape = []
    for q in piece["points"]:
        shape += [q[0] - ox, q[1] - oz]
    return ([piece["centre"][0] + ox, height + thick / 2, piece["centre"][1] + oz, v[0] * push, v[1] * push, v[2] * push, 0.0, 0.0, sp[0] * push, sp[1] * push, 0],
            thick / 2, hw, shape)


def fly(plan, life, g=120.0, speed=None, fps=60, height=0.0, alone=False):
    """every piece of a plan flown TOGETHER for `life` seconds -> [{rest_at (seconds or None), moved, top, flat, y,
    hy, floor, on (lies on another piece), deep (how deep it lies in another at the end)}]
    alone=True: the old flight, every piece by itself (they pass through each other)"""
    made = (plan.get("made") or {}).get("speed") or 0
    push = speed / made if speed is not None and made > 0 else 1.0   # (a speed of 0 pushes nothing, as in the game and the player)
    thick = plan["size"][2]
    dt = 1.0 / fps
    pcs = plan["pieces"]
    n = len(pcs)
    made_ = [start(pc, thick, push, height) for pc in pcs]
    S = [m[0] for m in made_]
    H, W, shapes = [m[1] for m in made_], [m[2] for m in made_], [m[3] for m in made_]
    A = [max(float(pc.get("area") or 0), 1e-6) for pc in pcs]
    x0 = [(s[0], s[2]) for s in S]
    rest_at, top, floor = [None] * n, [s[1] for s in S], [0.0] * n
    t = 0.0
    for _ in range(int(round(life * fps))):
        t += dt
        live = [i for i in range(n) if t >= (pcs[i].get("delay") or 0)]   # (the break has not reached the others)
        if alone:
            new, fl = [step(S[i], dt, g, 0.0, H[i], W[i]) for i in live], [0.0] * len(live)
        else:
            new, fl = meet([S[i] for i in live], [shapes[i] for i in live], [H[i] for i in live], [W[i] for i in live], [A[i] for i in live], dt, g, 0.0)
        for k, i in enumerate(live):
            S[i] = new[k]
            floor[i] = floor[i] if fl is None else fl[k]
            top[i] = max(top[i], S[i][1])
            if S[i][10] == 1:
                rest_at[i] = t if rest_at[i] is None else rest_at[i]
            else:
                rest_at[i] = None   # (pushed, or what it lay on went: it is moving again)
    polys = [lying(S[i], shapes[i]) for i in range(n)]
    deep = [0.0] * n
    for i in range(n):
        for j in range(i + 1, n):
            if min(S[i][1] + H[i], S[j][1] + H[j]) - max(S[i][1] - H[i], S[j][1] - H[j]) > 1e-4:
                d = apart(polys[i], polys[j])[0]
                deep[i], deep[j] = max(deep[i], d), max(deep[j], d)
    return [{"rest_at": rest_at[i], "moved": math.hypot(S[i][0] - x0[i][0], S[i][2] - x0[i][1]), "top": top[i],
             "flat": abs(S[i][6] - math.floor(S[i][6] / math.pi + 0.5) * math.pi) < FLAT, "y": S[i][1], "hy": H[i], "floor": floor[i],
             "on": floor[i] > 1e-6, "deep": deep[i], "x": S[i][0], "z": S[i][2]} for i in range(n)]


def check(flown, life, long_last=None, pushed=True):
    """long_last: when the last piece rests given all the time it needs (None = some piece never rests); pushed: False
    when the layer's speed is 0 (nothing is meant to fly: the 'flew' check is not asked)"""
    rows = []

    def add(name, ok, value, limit, fix):
        rows.append({"name": name, "ok": bool(ok), "value": value, "limit": limit, "fix": fix})

    late = [f for f in flown if f["rest_at"] is None or f["rest_at"] > life * FADE]
    last = max((f["rest_at"] for f in flown if f["rest_at"] is not None), default=None)
    add("rests", not late, len(late), f"0 pieces still moving when the fade starts ({life * FADE:.2f} s of a life of {life:g} s)",
        f"pieces would fade out in mid-move: a life of {math.ceil((long_last / FADE + 0.05) * 10) / 10:.1f} s or more, a lower speed, or more gravity"
        if long_last is not None else "a piece never comes to rest, however long the life: more gravity or a lower speed")
    def lies(f):
        return abs(f["y"] - f["hy"] - f.get("floor", 0.0)) < 1e-6 and f["flat"]

    add("on_the_floor", all(lies(f) for f in flown if f["rest_at"] is not None),
        sum(1 for f in flown if f["rest_at"] is not None and not lies(f)),
        "every piece at rest lies flat on the floor or on a piece under it", "a piece at rest floats or leans: a fault in the rule")
    worst = max((f.get("deep", 0.0) for f in flown if f["rest_at"] is not None), default=0.0)
    add("lies_apart", worst <= 2 * SKIN, round(worst, 4), f"no two pieces at rest on one level lie over {2 * SKIN} studs deep in each other",
        "pieces at rest lie in each other: a fault in the rule (kit/vfx/settle.py meet)")
    add("flew", pushed is False or max(f["moved"] for f in flown) > 0.1, round(max(f["moved"] for f in flown), 2), "a piece ends over 0.1 studs from where it sat",
        "nothing left the slab: a speed above 0")
    return rows, last


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status == "pass" else 1


def main(argv):
    usage = "lune run kit vfx settle <plan> [--life 2.5] [--gravity 120] [--speed 30] [--height 0] [--fps <one rate; without it 30, 60 and 144>]"
    o = {"--life": "2.5", "--gravity": "120", "--speed": "", "--height": "0", "--fps": "", "--plans-dir": PLANS}
    names, i = [], 0
    while i < len(argv):
        if argv[i] in o:
            if i + 1 >= len(argv):
                return out("fail", f"settle: {argv[i]} has no value", usage)
            o[argv[i]] = argv[i + 1]
            i += 2
        elif argv[i].startswith("--"):
            return out("fail", f"settle: {argv[i]} is not an option of it", usage)
        else:
            names.append(argv[i])
            i += 1
    if len(names) != 1:
        return out("fail", "settle: name ONE fracture plan", usage)
    try:
        life, g, height = float(o["--life"]), float(o["--gravity"]), float(o["--height"])
        rates = [int(o["--fps"])] if o["--fps"] else list(RATES)
        speed = float(o["--speed"]) if o["--speed"] else None
        if not (0.2 <= life <= 30 and 1 <= g <= 2000 and 20 <= rates[0] <= 240 and (speed is None or 0 <= speed <= 1000) and 0 <= height <= 500):
            raise ValueError
    except ValueError:
        return out("fail", "settle: --life 0.2..30 (seconds), --gravity 1..2000, --fps 20..240, --speed 0..1000, --height 0..500", usage)
    path = os.path.join(o["--plans-dir"], f"{names[0]}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            plan = json.load(fh)
        if not (isinstance(plan.get("pieces"), list) and plan["pieces"] and len(plan.get("size") or []) == 3):
            raise ValueError("not a fracture plan")
    except (OSError, ValueError) as e:
        return out("fail", f"settle: no fracture plan {path.replace(os.sep, '/')} ({type(e).__name__})", f"lune run kit vfx fracture {names[0]} --size w,d[,h]")
    # pieces that meet land a little differently at every frame rate (where two touch decides who gives way): the
    # life must do at 30, 60 and 144 frames a second, and the LATEST rest of the three is the one said
    flights = {fps: fly(plan, life, g, speed, fps, height) for fps in rates}
    long_last = None
    if any(f["rest_at"] is None or f["rest_at"] > life * FADE for flown in flights.values() for f in flown):  # (only then are the long flights needed)
        longer = [f["rest_at"] for fps in rates for f in fly(plan, 30.0, g, speed, fps, height)]
        long_last = None if any(r is None for r in longer) else max(longer)
    rows, last, far, on = [], 0.0, 0.0, 0
    for fps, flown in flights.items():
        got, at = check(flown, life, long_last, pushed=not (speed is not None and speed == 0))
        for c in got:
            if len(rates) > 1 and not c["ok"]:
                c["value"] = f"{c['value']} at {fps} frames a second"
        rows = got if not rows or (any(not c["ok"] for c in got) and all(c["ok"] for c in rows)) else rows
        last = max(last, at or 0.0)
        far = max(far, max(f["moved"] for f in flown))
        on = max(on, sum(1 for f in flown if f["on"]))
    failed = [c for c in rows if not c["ok"]]
    if failed:
        return out("fail", f"settle {names[0]}: " + "; ".join(f"{c['name']} = {c['value']} (needs {c['limit']})" for c in failed), failed[0]["fix"], checks=rows)
    flown = flights[rates[0]]
    return out("pass", f"settle {names[0]}: {len(flown)} pieces, the last at rest {last:.2f} s after the layer starts, the furthest {far:.1f} studs from where it sat, "
               f"{'none lies' if on == 0 else str(on) + ' lie'} on another, no two lie in each other "
               f"(a life of {life:g} s: the fade starts at {life * FADE:.2f} s; flown at {', '.join(str(r) for r in rates)} frames a second)",
               f'on the debris layer: "pieces": "{names[0]}", "rest": true, "life": {life:g} (kit/skills/parallax-vfx/reference/25-*)', checks=rows,
               last_rest=round(last, 3), furthest=round(far, 2))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
