#!/usr/bin/env python3
"""liquid.py - LIQUID, SIMULATED AND BAKED INTO A FLIPBOOK (the owner's methods list: Liquid simulation, FLIP fluid
simulation, Particle fluid simulation, Foam and spray simulation; the VFX methods audit, stage 25). A tank seen from
the SIDE (x across, y up, 1 wide and 1 tall), a body of liquid in it, gravity. Two solvers, both from first
principles:

  flip   FLIP / PIC: the liquid is particles that carry its speed; each step their speeds are laid on a grid, the
         grid is made to keep its volume (a pressure solve: nothing flows into a full cell or through a wall, the
         surface is free), and the CHANGE is handed back to the particles (0.95 FLIP, 0.05 PIC)
  pbf    a particle fluid (position based fluids): no grid - every particle is pushed off its neighbours until the
         liquid is nowhere denser than at rest

Scenes: `dam` (a block of liquid against the left wall, let go), `drop` (a pool, and a round body of liquid falling
into it), `slosh` (a pool that starts tilted).

FOAM AND SPRAY are read off the solved liquid, they are not painted: SPRAY is liquid that has left the body (a
particle with almost no neighbours), FOAM is surface liquid where the flow is being squeezed or torn fast (air is
beaten in); foam lives a moment and dies. Both are drawn brighter than the body. FLIP's particles are kept from
bunching (pushed apart when nearer than 0.7 of their spacing): without that a dam's picture lost an eighth of its
liquid. The particle fluid's lattice relaxes before the first frame (that settling is not the liquid moving).

NEVER MATCHED TO A REAL SCENE: no clip of liquid was read for this (a download waits on the owner). The tests hold
the physics - a still pool stays still, a body in the air falls as gravity says, no liquid is made or lost or
leaves the tank, the grid keeps its volume, the liquid does not gain energy, a dam's front runs no faster than
shallow-water theory allows - not that it LOOKS like any liquid he has in mind.
NOT here: three dimensions (it is a slice: a splash's crown, a jet turning in depth cannot be), surface tension
(no drops that bead), air, anything in the liquid's way but the tank's walls, light bending in it.
"""
import math

import numpy as np

SOLVERS = ("flip", "pbf")
SCENES = ("dam", "drop", "slosh")
NX = 48            # cells across the tank the FLIP grid has (and up it)
PER = 2            # particles a cell each way, at the start
FLIP = 0.95        # how much of a particle's own speed it keeps (the rest is the grid's)
SPRAY_NEAR = 3     # a particle with fewer neighbours than this (within 1.5 cells) has left the body
FOAM_LIFE = 0.5    # seconds a bit of foam lasts
APART = 0.7        # of the spacing particles are laid at: FLIP's particles are kept at least this far from each other
JOLT = (2.0, 3.0)  # x gravity: a particle's speed changing faster than the first is foam, by the second more it is all foam


def body(scene, n=NX, per=PER, fill=0.4, seed=1):
    """the liquid at the first frame -> its particles' places, jittered on a lattice (so no row of them is a wall)"""
    rng = np.random.default_rng(seed)
    step = 1.0 / (n * per)
    xs = (np.arange(n * per) + 0.5) * step
    x, y = np.meshgrid(xs, xs)
    x, y = x.reshape(-1), y.reshape(-1)
    if scene == "dam":
        keep = (x < 0.3) & (y < 0.9 * fill)   # (a taller block's run-up on the far wall leaves the top of the picture)
    elif scene == "drop":
        keep = (y < 0.6 * fill) | ((x - 0.5) ** 2 + (y - 0.72) ** 2 < 0.12 ** 2)
    elif scene == "slosh":
        keep = y < fill + 0.5 * fill * (x - 0.5) * 2
    else:
        raise ValueError(f"scene is one of {', '.join(SCENES)}")
    p = np.stack([x[keep], y[keep]], -1)
    return p + rng.uniform(-0.25, 0.25, p.shape) * step


# --------------------------------------------------------------------------------------------------- FLIP / PIC

def _corners(gx, gy, hi_i, hi_j):
    i0, j0 = np.floor(gx).astype(int), np.floor(gy).astype(int)
    fx, fy = gx - i0, gy - j0
    for di, dj, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        yield np.clip(j0 + dj, 0, hi_j), np.clip(i0 + di, 0, hi_i), w


def to_grid(pos, vel, n):
    """the particles' speeds laid on the grid's faces -> (u, v, which faces got any, which cells hold liquid)"""
    u, wu = np.zeros((n, n + 1)), np.zeros((n, n + 1))
    v, wv = np.zeros((n + 1, n)), np.zeros((n + 1, n))
    for j, i, w in _corners(pos[:, 0] * n, pos[:, 1] * n - 0.5, n, n - 1):
        np.add.at(u, (j, i), w * vel[:, 0])
        np.add.at(wu, (j, i), w)
    for j, i, w in _corners(pos[:, 0] * n - 0.5, pos[:, 1] * n, n - 1, n):
        np.add.at(v, (j, i), w * vel[:, 1])
        np.add.at(wv, (j, i), w)
    wet = np.zeros((n, n), bool)
    wet[np.clip((pos[:, 1] * n).astype(int), 0, n - 1), np.clip((pos[:, 0] * n).astype(int), 0, n - 1)] = True
    return np.where(wu > 0, u / np.maximum(wu, 1e-12), 0.0), np.where(wv > 0, v / np.maximum(wv, 1e-12), 0.0), wet


def from_grid(pos, u, v, n):
    """the grid's speed at each particle's place"""
    out = np.zeros_like(pos)
    for j, i, w in _corners(pos[:, 0] * n, pos[:, 1] * n - 0.5, n, n - 1):
        out[:, 0] += w * u[j, i]
    for j, i, w in _corners(pos[:, 0] * n - 0.5, pos[:, 1] * n, n - 1, n):
        out[:, 1] += w * v[j, i]
    return out


def divergence(u, v, n):
    return (u[:, 1:] - u[:, :-1] + v[1:, :] - v[:-1, :]) * n


def project(u, v, wet, dt, n, tol=1e-6, most=400):
    """the pressure that makes the liquid keep its volume (0 in the air: a free surface; nothing through a wall),
    taken off the speeds -> (u, v, the pressure). Conjugate gradients on the wet cells"""
    u, v = u.copy(), v.copy()
    u[:, 0] = u[:, -1] = 0.0
    v[0, :] = v[-1, :] = 0.0
    open_ = np.full((n, n), 4.0)      # how many of a cell's four sides are not a wall
    open_[0, :] -= 1
    open_[-1, :] -= 1
    open_[:, 0] -= 1
    open_[:, -1] -= 1

    def lap(p):
        s = open_ * p
        s[:, 1:] -= p[:, :-1]
        s[:, :-1] -= p[:, 1:]
        s[1:, :] -= p[:-1, :]
        s[:-1, :] -= p[1:, :]
        return np.where(wet, s, 0.0) * n * n

    rhs = np.where(wet, -divergence(u, v, n) / dt, 0.0)
    p = np.zeros((n, n))
    r = rhs.copy()
    d = r.copy()
    rr = float((r * r).sum())
    goal = tol * tol * max(rr, 1e-30)
    for _ in range(most):
        if rr <= goal:
            break
        ad = lap(d)
        alpha = rr / max(float((d * ad).sum()), 1e-30)
        p += alpha * d
        r -= alpha * ad
        new = float((r * r).sum())
        d = r + (new / rr) * d
        rr = new
    u[:, 1:-1] -= dt * (p[:, 1:] - p[:, :-1]) * n
    v[1:-1, :] -= dt * (p[1:, :] - p[:-1, :]) * n
    return u, v, p


def spread(f, known, passes=2):
    """faces no particle reached take the mean of their known neighbours (a particle at the surface reads them)"""
    f, known = f.copy(), known.copy()
    for _ in range(passes):
        s = np.zeros_like(f)
        c = np.zeros_like(f)
        for sl_to, sl_from in (((slice(None), slice(1, None)), (slice(None), slice(None, -1))), ((slice(None), slice(None, -1)), (slice(None), slice(1, None))),
                               ((slice(1, None), slice(None)), (slice(None, -1), slice(None))), ((slice(None, -1), slice(None)), (slice(1, None), slice(None)))):
            s[sl_to] += np.where(known[sl_from], f[sl_from], 0.0)
            c[sl_to] += known[sl_from]
        fill = ~known & (c > 0)
        f[fill] = s[fill] / c[fill]
        known = known | fill
    return f


def separate(pos, n=NX, per=PER, share=APART):
    """particles nearer each other than `share` of the spacing they were laid at are pushed apart, half the way each
    (FLIP lets particles bunch: bunched liquid fills fewer cells, and a dam's picture lost an eighth of its liquid)"""
    from scipy.spatial import cKDTree

    d0 = share / (n * per)
    pr = cKDTree(pos).query_pairs(d0, output_type="ndarray")
    if len(pr) == 0:
        return pos
    i, j = pr[:, 0], pr[:, 1]
    d = pos[i] - pos[j]
    r = np.sqrt((d * d).sum(-1))
    way = np.where(r[:, None] > 1e-9, d / np.maximum(r, 1e-9)[:, None], np.array([1.0, 0.0]))
    push = 0.5 * (d0 - r)[:, None] * way
    out = pos.copy()
    np.add.at(out, i, push)
    np.add.at(out, j, -push)
    return out


def flip_step(pos, vel, dt, g, n=NX):
    """one step of FLIP -> (the particles' new places, their new speeds, the pressure, the wet cells)"""
    u0, v0, wet = to_grid(pos, vel, n)
    v1 = v0 - g * dt
    u, v, p = project(u0, v1, wet, dt, n)
    ku = np.zeros((n, n + 1), bool)
    ku[:, :-1] |= wet
    ku[:, 1:] |= wet
    kv = np.zeros((n + 1, n), bool)
    kv[:-1, :] |= wet
    kv[1:, :] |= wet
    u, v, u0, v0 = spread(u, ku), spread(v, kv), spread(u0, ku), spread(v0, kv)
    u[:, 0] = u[:, -1] = 0.0
    v[0, :] = v[-1, :] = 0.0
    new = from_grid(pos, u, v, n)
    vel = FLIP * (vel + new - from_grid(pos, u0, v0, n)) + (1 - FLIP) * new
    mid = pos + 0.5 * dt * new                          # the particle is carried by the grid's flow (a midpoint step)
    pos = separate(pos + dt * from_grid(np.clip(mid, 0.0, 1.0), u, v, n), n)
    return walls(pos, vel, 0.5 / (n * PER)) + (p, wet)


def walls(pos, vel, pad):
    """no particle leaves the tank: one that would is put on the wall and loses its speed into it"""
    pos, vel = pos.copy(), vel.copy()
    for k in (0, 1):
        low, high = pos[:, k] < pad, pos[:, k] > 1 - pad
        pos[low, k], pos[high, k] = pad, 1 - pad
        vel[low, k] = np.maximum(vel[low, k], 0.0)
        vel[high, k] = np.minimum(vel[high, k], 0.0)
    return pos, vel


# --------------------------------------------------------------------------------------------------- particle fluid

def pairs_of(pos, h):
    from scipy.spatial import cKDTree

    pr = cKDTree(pos).query_pairs(h, output_type="ndarray")
    return pr[:, 0], pr[:, 1]


def density(pos, h, i, j):
    """how dense the liquid is at each particle (2D poly6 kernel, every particle weighing 1)"""
    k = 4.0 / (math.pi * h ** 8)
    d2 = ((pos[i] - pos[j]) ** 2).sum(-1)
    w = k * np.maximum(h * h - d2, 0.0) ** 3
    rho = np.full(len(pos), k * h ** 6)
    np.add.at(rho, i, w)
    np.add.at(rho, j, w)
    return rho


def rest_density(n=NX, per=PER):
    """the density of liquid at rest: of a lattice at the spacing the body is laid at"""
    step = 1.0 / (n * per)
    h = 2.2 * step
    xs = np.arange(-4, 5) * step
    x, y = np.meshgrid(xs, xs)
    lat = np.stack([x.reshape(-1), y.reshape(-1)], -1)
    i, j = pairs_of(lat, h)
    return float(density(lat, h, i, j)[len(lat) // 2]), h


def pbf_step(pos, vel, dt, g, rho0, h, iters=4, soft=1e-4):
    """one step of position based fluids -> (the particles' new places, their new speeds, their density)"""
    pad = 0.25 * h
    vel = vel + np.array([0.0, -g]) * dt
    new = pos + vel * dt
    new, _ = walls(new, vel, pad)
    rho = None
    for _ in range(iters):
        i, j = pairs_of(new, h)
        d = new[i] - new[j]
        r = np.sqrt((d * d).sum(-1))
        rho = density(new, h, i, j)
        c = np.maximum(rho / rho0 - 1.0, 0.0)                               # only ever pushed APART: a free surface pulls nothing in
        gw = (-30.0 / (math.pi * h ** 5)) * (h - r) ** 2                    # the spiky kernel's slope along the pair
        grad = (gw / np.maximum(r, 1e-9))[:, None] * d / rho0               # dC_i / dx_i from j (and its opposite for j)
        own = np.zeros_like(new)
        np.add.at(own, i, grad)
        np.add.at(own, j, -grad)
        den = (own * own).sum(-1)
        np.add.at(den, i, (grad * grad).sum(-1))
        np.add.at(den, j, (grad * grad).sum(-1))
        lam = -c / (den + soft * (30.0 / (math.pi * h ** 5) * h * h / rho0) ** 2)
        move = np.zeros_like(new)
        np.add.at(move, i, (lam[i] + lam[j])[:, None] * grad)
        np.add.at(move, j, -(lam[i] + lam[j])[:, None] * grad)
        new, _ = walls(new + move, vel, pad)
    vel = (new - pos) / dt
    i, j = pairs_of(new, h)                                                 # a little of its neighbours' speed (XSPH): the liquid moves as one
    d2 = ((new[i] - new[j]) ** 2).sum(-1)
    w = (np.maximum(h * h - d2, 0.0) / (h * h)) ** 3
    dv = np.zeros_like(vel)
    np.add.at(dv, i, w[:, None] * (vel[j] - vel[i]))
    np.add.at(dv, j, w[:, None] * (vel[i] - vel[j]))
    cnt = np.zeros(len(new))
    np.add.at(cnt, i, w)
    np.add.at(cnt, j, w)
    vel = vel + 0.05 * dv / np.maximum(cnt, 1.0)[:, None]
    new, vel = walls(new, vel, pad)
    return new, vel, rho


# --------------------------------------------------------------------------------------------------- the run

def rate_of(g, n=NX):
    """steps a second: the fastest a body can fall across the tank moves under half a cell a step (from gravity alone)"""
    return int(math.ceil(math.sqrt(2.0 * g) * n / 0.5))


def energy(pos, vel, g):
    """the liquid's energy a particle: its motion and its height"""
    return float((0.5 * (vel * vel).sum(-1) + g * pos[:, 1]).mean())


def simulate(a, n=NX, keep=None):
    """the asks -> [(places, speeds, foam 0..1, spray yes / no)] at every frame's moment (frame f at f / fps)

    a: {solver, scene, gravity, fill, frames, fps, seed}; keep(step, pos, vel, extra) is called after every step"""
    from scipy.spatial import cKDTree

    g = a["gravity"]
    pos = body(a["scene"], n, PER, a.get("fill", 0.4), a.get("seed", 1))
    vel = np.zeros_like(pos)
    rate = rate_of(g, n)
    dt = 1.0 / rate
    rho0, h = rest_density(n, PER)
    if a["solver"] == "pbf":   # the lattice it is laid on relaxes first, with no gravity and no speed kept: that is not the liquid moving
        for _ in range(40):
            pos, _, _ = pbf_step(pos, vel, dt, 0.0, rho0, h)
    foam = np.zeros(len(pos))
    out, step = [], 0
    prev = pos
    if keep:
        keep(0, pos, vel, None)
    for f in range(a["frames"]):
        t = f / a["fps"]
        while step * dt < t - 1e-12:
            prev, was = pos, vel
            if a["solver"] == "flip":
                pos, vel, extra, _ = flip_step(pos, vel, dt, g, n)
            else:
                pos, vel, extra = pbf_step(pos, vel, dt, g, rho0, h)
            # foam: surface liquid whose speed is being changed hard (squeezed or torn: air is beaten in); it dies in FOAM_LIFE
            jolt = np.sqrt(((vel - was + np.array([0.0, g * dt])) ** 2).sum(-1)) / dt / g   # (gravity's own pull is no jolt)
            foam = np.maximum(foam - dt / FOAM_LIFE, np.clip((jolt - JOLT[0]) / JOLT[1], 0.0, 1.0))
            step += 1
            if keep:
                keep(step, pos, vel, extra)
        back = (step * dt - t) / dt if step else 0.0
        at = pos * (1 - back) + prev * back
        near = np.array([len(x) - 1 for x in cKDTree(at).query_ball_point(at, 1.5 / n)])
        spray = near < SPRAY_NEAR
        surface = near < 0.75 * math.pi * 1.5 ** 2 * PER * PER * 0.8          # fewer neighbours than a particle deep in the body has
        out.append((at, vel.copy(), np.where(surface, foam, 0.0), spray))
    return out


def render(frame, cell=128):
    """a frame's particles -> its picture, premultiplied RGBA (linear): the body as one smooth shape (a blob a particle,
    cut at half), foam and spray brighter. White: the layer's own colour tints it"""
    from scipy.ndimage import gaussian_filter

    pos, _, foam, spray = frame
    px = np.clip((pos[:, 0] * cell).astype(int), 0, cell - 1)
    py = np.clip(((1 - pos[:, 1]) * cell).astype(int), 0, cell - 1)
    each = (cell / (NX * PER)) ** 2                                         # the picture's cells a particle fills
    dens, white, mist = np.zeros((cell, cell)), np.zeros((cell, cell)), np.zeros((cell, cell))
    np.add.at(dens, (py[~spray], px[~spray]), each)
    np.add.at(white, (py, px), each * foam)
    np.add.at(mist, (py[spray], px[spray]), each)
    blur = cell / NX * 0.9
    dens, white, mist = gaussian_filter(dens, blur), gaussian_filter(white, blur), gaussian_filter(mist, blur * 0.7)
    alpha = np.clip((dens - 0.35) / 0.3, 0.0, 1.0)
    alpha = np.maximum(alpha, np.clip(mist * 9.0, 0.0, 0.9))                 # (one particle of spray is a dot you can see)
    light = 0.55 + 0.45 * np.clip(np.maximum(1.6 * white / np.maximum(dens, 1e-6), mist * 9.0), 0.0, 1.0)
    return np.stack([light * alpha, light * alpha, light * alpha, alpha], -1)


# --------------------------------------------------------------------------------------------------- the bake

import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402

SPECS = os.path.join("assets", "textures")
FRAMES = os.path.join("build", "fxlab")
LOOK = os.path.join("build", "vfx", "liquid")
POST = {"alpha": "coverage", "tonemap": False, "border": 0}   # (kit/vfx/comp.py's: the sheet is packed as it is drawn)
GRIDS = (4, 8)            # cells a side: with the cell's size the sheet is 256, 512 or 1024 px a side (the packer takes no other)
SHEETS = (256, 512, 1024)
WHITE = 0.015    # of the DRAWN liquid's pixels: the least that are white (foam or spray) at its wildest moment, for a dam or a drop baked with foam
RISE = 0.0015    # x gravity: the most the liquid's energy a particle may rise in one step (FLIP's hand-back is not exact)
KEPT = 0.15      # the picture's liquid may differ from its first frame's by this part, at most
DAM_FILL = 0.42  # the most fill a dam may ask (a taller block's run-up on the far wall reaches the top of the picture)
CLEAR = 0.05     # the most there may be of the liquid in the top two rows of a cell
MOVES = 0.03     # x sqrt(gravity): the least the liquid's mean speed, over the frames


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status == "pass" else 1


def checked(spec):
    """a recipe "liquid" spec -> the numbers a bake is made from; ValueError in words when it is not one"""
    if not isinstance(spec, dict) or spec.get("engine") != "fx" or spec.get("recipe") != "liquid" or not isinstance(spec.get("liquid"), dict):
        raise ValueError('a liquid spec is {"engine": "fx", "recipe": "liquid", "frames", "grid", "cell", "liquid": {...}}')
    b = spec["liquid"]
    extra = sorted(set(b) - {"solver", "scene", "gravity", "fill", "seed", "fps", "foam"})
    if extra:
        raise ValueError(f'"liquid" has no "{extra[0]}" (solver, scene, gravity, fill, seed, fps, foam)')

    def num(v, name, lo, hi, whole=False):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi or (whole and v != int(v)):
            raise ValueError(f"{name} is {'a whole number' if whole else 'a number'} from {lo:g} to {hi:g}")
        return int(v) if whole else float(v)

    grid = num(spec.get("grid", 8), '"grid"', GRIDS[0], GRIDS[-1], True)
    if grid not in GRIDS:
        raise ValueError(f'"grid" is {" or ".join(str(x) for x in GRIDS)}')
    a = {"solver": b.get("solver", "flip"), "scene": b.get("scene", "dam"), "gravity": num(b.get("gravity", 4.0), '"gravity"', 1, 20),
         "fill": num(b.get("fill", 0.4), '"fill"', 0.15, 0.5), "seed": num(b.get("seed", 1), '"seed"', 0, 99999, True), "fps": num(b.get("fps", 24), '"fps"', 12, 60, True),
         "foam": b.get("foam", True), "frames": num(spec.get("frames", grid * grid), '"frames"', 2, 64, True), "grid": grid,
         "cell": num(spec.get("cell", 128), '"cell"', 32, 256, True)}
    if a["cell"] * grid not in SHEETS:
        raise ValueError(f'"cell" x "grid" is {a["cell"] * grid}: a sheet is 256, 512 or 1024 px a side (a grid of 8 takes cells of 32, 64 or 128; of 4, 64, 128 or 256)')
    if a["solver"] not in SOLVERS:
        raise ValueError(f'"solver" is one of {", ".join(SOLVERS)}')
    if a["scene"] not in SCENES:
        raise ValueError(f'"scene" is one of {", ".join(SCENES)}')
    if not isinstance(a["foam"], bool):
        raise ValueError('"foam" is true or false')
    if a["scene"] == "dam" and a["fill"] > DAM_FILL:
        raise ValueError(f'"fill" is {DAM_FILL:g} at most for a dam (a taller block runs up the far wall to the top of the picture and is cut off there)')
    if a["frames"] != grid * grid:
        raise ValueError(f'"frames" is {grid * grid} for a grid of {grid} (Roblox plays EVERY cell of a flipbook: an empty one is a blink)')
    if math.sqrt(2 * a["gravity"]) / a["fps"] > 0.2:
        raise ValueError(f'gravity {a["gravity"]:g} at {a["fps"]} frames a second: falling liquid crosses over a fifth of the tank a frame (less gravity or more fps)')
    return a


def solve(a):
    """-> (the frames, their pictures, the checks of THIS run: [{name, ok, value, limit, fix}])"""
    g = a["gravity"]
    log = {"rise": 0.0, "last": None, "first": None, "n": None, "outside": 0}

    def keep(step, pos, vel, extra):
        e = energy(pos, vel, g)
        if log["first"] is None:
            log["first"] = e
        elif e - log["last"] > log["rise"]:
            log["rise"] = e - log["last"]
        log["last"] = e
        log["n"] = len(pos) if log["n"] is None else log["n"]
        log["outside"] += int(len(pos) != log["n"]) + int(((pos < 0) | (pos > 1)).any()) + int(not np.isfinite(pos).all())

    frames = simulate(a, keep=keep)
    cells = [render(f if a["foam"] else (f[0], f[1], f[2] * 0, f[3] & False), a["cell"]) for f in frames]
    area = np.array([float(c[..., 3].sum()) for c in cells])
    drift = float(np.abs(area - area[0]).max() / max(area[0], 1e-9))
    speed = float(np.mean([np.sqrt((f[1] ** 2).sum(-1)).mean() for f in frames[1:]])) / math.sqrt(g)
    top = max(float(c[:2, :, 3].max()) for c in cells)

    def whites(c):   # of the drawn pixels, the share that are white (the body is 0.55, foam and spray up to 1)
        drawn = c[..., 3] > 0.3
        return float(((c[..., 0] / np.maximum(c[..., 3], 1e-6) > 0.75) & drawn).sum() / max(int(drawn.sum()), 1))

    white = max(whites(c) for c in cells)
    rows = [
        {"name": "no liquid is made or lost, none leaves the tank", "ok": log["outside"] == 0, "value": f"{log['outside']} steps with a particle gone or outside",
         "limit": "0", "fix": "a fault in the solver (kit/vfx/liquid.py)"},
        {"name": "the liquid does not gain energy", "ok": log["rise"] <= RISE * g and log["last"] <= log["first"] + RISE * g,
         "value": f"its energy a particle rises by {log['rise'] / g:.5f} x gravity in a step at most, and ends {(log['last'] - log['first']) / g:+.4f} x gravity from its start",
         "limit": f"at most {RISE} x gravity in a step, and no higher at the end", "fix": "less gravity or another seed; else a fault in the solver"},
        {"name": "the liquid moves", "ok": speed >= MOVES, "value": f"its mean speed is {speed:.3f} x sqrt(gravity)", "limit": f"at least {MOVES}",
         "fix": "a scene that moves: dam or drop, or more fill"},
        {"name": "the picture keeps its liquid", "ok": drift <= KEPT, "value": f"the drawn liquid differs from the first frame's by {drift:.2f} at most", "limit": f"at most {KEPT}",
         "fix": "the other solver, or less gravity (the liquid is being squeezed or spread thin)"},
        {"name": "the liquid stays under the top of its cell", "ok": top <= CLEAR, "value": f"{top:.2f} of full in the top two rows", "limit": f"at most {CLEAR} (it would be cut off there)",
         "fix": "less fill or less gravity"},
    ]
    if a["foam"] and a["scene"] in ("dam", "drop"):   # (a slosh may make none: it is not asked of one)
        rows.append({"name": "foam or spray is made", "ok": white >= WHITE, "value": f"{white:.3f} of the drawn liquid is white at its wildest moment", "limit": f"at least {WHITE}",
                     "fix": "more gravity or more fill (the liquid is too calm to beat any air in), or foam: false"})
    return frames, cells, rows


def write_frames(frames_dir, key, cells, spec_path):
    fdir = os.path.join(frames_dir, key)
    os.makedirs(fdir, exist_ok=True)
    for f in os.listdir(fdir):
        if f.endswith(".npy"):
            os.remove(os.path.join(fdir, f))
    for i, c in enumerate(cells):
        np.save(os.path.join(fdir, f"{i:03d}.npy"), c.astype(np.float16))   # (render gives premultiplied RGBA)
    with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as fh:
        json.dump({"frames": len(cells), "spec_mtime": os.path.getmtime(spec_path), "engine": "liquid", "code": code_id()}, fh)


def code_id():
    """which solver made a sheet's frames: this file's own text (a fix to it bakes every liquid sheet again)"""
    import hashlib

    with open(os.path.abspath(__file__), "rb") as fh:
        return hashlib.sha1(fh.read().replace(b"\r\n", b"\n")).hexdigest()[:12]


def unbake(frames_dir, key):
    """a sheet whose bake FAILED has no frames: the old ones are another spec's (the packer would pack them as this one's)"""
    fdir = os.path.join(frames_dir, key)
    for f in os.listdir(fdir) if os.path.isdir(fdir) else []:
        if f.endswith(".npy") or f == "frames.json":
            os.remove(os.path.join(fdir, f))


def strip(cells, path, tile=150):
    """the LOOK picture: every cell over a dark ground, in order"""
    from PIL import Image, ImageDraw

    per = min(len(cells), 8)
    rows = int(math.ceil(len(cells) / per))
    page = Image.new("RGB", (per * (tile + 6) + 6, rows * (tile + 24) + 6), (20, 20, 24))
    pen = ImageDraw.Draw(page)
    for i, c in enumerate(cells):
        r, col = divmod(i, per)
        x, y = 6 + col * (tile + 6), 6 + r * (tile + 24)
        pen.text((x + 2, y + 3), f"frame {i}", fill=(225, 225, 225))
        over = np.clip(c[..., :3] * np.array([0.45, 0.72, 1.0]) + (1 - c[..., 3:]) * 0.08, 0, 1) ** (1 / 2.2)
        page.paste(Image.fromarray((over * 255 + 0.5).astype(np.uint8)).resize((tile, tile), Image.LANCZOS), (x, y + 18))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    page.save(path)


def new_spec(solver, scene, grid=8, cell=128, **block):
    return {"engine": "fx", "recipe": "liquid",
            "about": f"a liquid bake (kit/vfx/liquid.py): {scene}, solved by {solver}, seen from the side. Never matched to a real scene",
            "frames": grid * grid, "grid": grid, "cell": cell, "liquid": dict({"solver": solver, "scene": scene}, **block), "post": dict(POST)}


def bake(key, spec, spec_path, frames_dir, look_dir=None):
    """one sheet -> (status, summary, next_action, extra). Frames are written only when every check passes"""
    a = checked(spec)
    _, cells, rows = solve(a)
    failed = [c for c in rows if not c["ok"]]
    if failed:
        return "fail", f"liquid {key}: " + "; ".join(f"{c['name']}: {c['value']} (needs {c['limit']})" for c in failed), failed[0]["fix"], {"checks": rows}
    write_frames(frames_dir, key, cells, spec_path)
    extra = {"checks": rows}
    if look_dir:
        extra["look"] = os.path.join(look_dir, f"{key}.png").replace(os.sep, "/")
        strip(cells, extra["look"])
    return ("pass", f"liquid {key}: {a['frames']} frames of a {a['scene']} solved by {a['solver']} ({a['grid']} x {a['grid']} cells of {a['cell']} px, played at {a['fps']} "
            f"frames a second) - a flipbook a sprite or a mesh surface plays; lune run kit vfx packs it", "", extra)


def build_step(argv):
    """every recipe "liquid" spec whose frames are missing or older than its spec is baked again (kit vfx runs this
    BEFORE its packer, which packs the frames like every sheet)"""
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv and argv.index(k) + 1 < len(argv) else d  # noqa: E731
    specs, frames_dir = opt("--specs", SPECS), opt("--out", FRAMES)
    done, errors, n = [], [], 0
    for f in sorted(os.listdir(specs)) if os.path.isdir(specs) else []:
        if not f.endswith(".json"):
            continue
        path = os.path.join(specs, f)
        try:
            with open(path, encoding="utf-8") as fh:
                spec = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(spec, dict) or spec.get("engine") != "fx" or spec.get("recipe") != "liquid":
            continue
        key, n = f[:-5], n + 1
        try:
            with open(os.path.join(frames_dir, key, "frames.json"), encoding="utf-8") as fh:
                meta = json.load(fh)
            fresh = meta.get("spec_mtime") == os.path.getmtime(path) and meta.get("code") == code_id()
        except (OSError, ValueError, AttributeError):
            fresh = False
        if fresh and "--force" not in argv:
            continue
        try:
            status, said, _, _ = bake(key, spec, path, frames_dir)
        except ValueError as e:
            status, said = "fail", f"liquid {key}: its spec is not one ({e})"
        except Exception as e:  # noqa: BLE001 - one broken spec must not stop the others, nor print a traceback
            status, said = "fail", f"liquid {key}: could not be baked again ({type(e).__name__}: {e})"
        (done if status == "pass" else errors).append(said)
        if status != "pass":
            unbake(frames_dir, key)
    if errors:
        return out("fail", "liquid: " + "; ".join(errors), "bake it again: lune run kit vfx liquid <key> --solver flip|pbf --scene dam|drop|slosh", baked=done)
    return out("pass", f"liquid: {len(done)} sheet(s) baked again" if done else f"liquid: every liquid sheet's frames are current ({n})", "none", baked=done)


DIRS = ("--specs-dir", "--frames-dir", "--look-dir")
ASKS = {"--solver": "solver", "--scene": "scene", "--gravity": "gravity", "--fill": "fill", "--seed": "seed", "--fps": "fps"}


def _main(argv):
    if "--specs" in argv:
        return build_step(argv)
    usage = "lune run kit vfx liquid <key> [--solver flip|pbf] [--scene dam|drop|slosh] [--gravity 4] [--fill 0.4] [--seed 1] [--fps 24] [--grid 8|4] [--cell 128] [--no-foam]"
    if not argv or argv[0].startswith("--"):
        return out("fail", "liquid: needs a texture key", usage)
    key, rest = argv[0], argv[1:]
    if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
        return out("fail", f'liquid: "{key}" is not a texture key (lower-case letters, digits, _)', usage)
    block, top, dirs, i = {}, {}, {"--specs-dir": SPECS, "--frames-dir": FRAMES, "--look-dir": LOOK}, 0
    while i < len(rest):
        k = rest[i]
        if k == "--no-foam":
            block["foam"] = False
            i += 1
            continue
        if k not in ASKS and k not in DIRS and k not in ("--grid", "--cell"):
            return out("fail", f"liquid: {k} is not one of its options", usage)
        if i + 1 >= len(rest) or rest[i + 1].startswith("--"):
            return out("fail", f"liquid: {k} has no value", usage)
        v = rest[i + 1]
        i += 2
        if k in DIRS:
            dirs[k] = v
        elif k in ("--solver", "--scene"):
            block[ASKS[k]] = v
        else:
            try:
                num = float(v)
                if not math.isfinite(num) or abs(num) > 1e9:
                    raise ValueError
            except ValueError:
                return out("fail", f"liquid: {k} is a number", usage)
            (top if k in ("--grid", "--cell") else block)[k[2:] if k in ("--grid", "--cell") else ASKS[k]] = int(num) if num == int(num) else num
    spec_path = os.path.join(dirs["--specs-dir"], f"{key}.json")
    grid = top.get("grid", 8)
    spec = new_spec(block.pop("solver", "flip"), block.pop("scene", "dam"), grid if isinstance(grid, int) and 0 < grid < 99 else 8, top.get("cell", 128), **block)
    spec["grid"] = grid
    try:
        a = checked(spec)
    except ValueError as e:
        return out("fail", f"liquid {key}: {e}", usage)
    if os.path.isfile(spec_path):   # (another recipe's sheet of this name is not written over)
        try:
            with open(spec_path, encoding="utf-8") as fh:
                old = json.load(fh)
        except (OSError, ValueError):
            old = None
        if not isinstance(old, dict) or old.get("recipe") != "liquid":
            return out("fail", f"liquid {key}: {spec_path.replace(os.sep, '/')} is there and is not a liquid spec", "another key")
    _, cells, rows = solve(a)
    failed = [c for c in rows if not c["ok"]]
    if failed:   # (nothing is written: an earlier good sheet of this name stays)
        return out("fail", f"liquid {key}: " + "; ".join(f"{c['name']}: {c['value']} (needs {c['limit']})" for c in failed), failed[0]["fix"], checks=rows)
    os.makedirs(dirs["--specs-dir"], exist_ok=True)
    with open(spec_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(spec, fh, indent=1)
        fh.write("\n")
    write_frames(dirs["--frames-dir"], key, cells, spec_path)
    look = os.path.join(dirs["--look-dir"], f"{key}.png")
    strip(cells, look)
    return out("pass", f"liquid {key}: {a['frames']} frames of a {a['scene']} solved by {a['solver']} ({a['grid']} x {a['grid']} cells of {a['cell']} px) - "
               f'then lune run kit vfx packs it; on a layer: its "texture": "{key}", played at {a["fps"]} frames a second, once',
               f"OPEN {look.replace(os.sep, '/')}: does the liquid move as THIS effect's does? (never matched to a real scene)", checks=rows,
               look=look.replace(os.sep, "/"), spec=spec_path.replace(os.sep, "/"))


def main(argv):
    try:
        return _main(argv)
    except Exception as e:  # noqa: BLE001 - a command answers in one line, never with a traceback
        return out("fail", f"liquid: {type(e).__name__}: {e}", "lune run kit vfx liquid <key> [--solver flip|pbf] [--scene dam|drop|slosh]")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
