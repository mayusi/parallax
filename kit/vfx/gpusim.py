"""gpusim.py - smoke and fire SIMULATED AND RENDERED ON THE GPU (PyTorch + CUDA; board/plans/archive/aaa-vfx-research.md: pros bake
high-resolution sims; Blender's Mantaflow is CPU-only - res 160 took ~38 s a frame on this machine). A 3D grid fluid
(semi-Lagrangian advection, buoyancy, vorticity confinement, a pressure projection) and a volume renderer with exact
self-shadowing from any of six sides (the light's transmittance is a running sum along a grid axis), so ONE simulation
gives every lit variant - the six-way-lighting idea - in seconds.

    python kit/vfx/gpusim.py --specs assets/textures --out build/fxlab [name ...] [--force]
    python kit/vfx/gpusim.py --specs assets/textures --new <name> [--fire]     a NEW sim's spec on the hero profile

"profile": "hero" (a spec's top-level key; what --new writes): the defaults under the spec's own params become a 256 x
256 x 320 grid, vorticity 2.0, 80 pressure iterations, the speeds scaled to the grid - refused if its own params take it
under 256 cells a side or vorticity 2 (LIMITATIONS_FIXES_V4 3.4 step 4). No profile: the old defaults below, kept so a
judged sheet bakes again byte for byte.

Spec (assets/textures/<name>.json): {"engine": "fx", "recipe": "gpu_smoke" | "gpu_fire", "frames": 64, "grid": 8,
"cell": 128, "seed": 1, "params": {...}} - params:
  res [x, y, z]      grid cells (x right, y depth, z up), default [128, 128, 160]; 256^3 and up run on this machine
                     (measured: 2.75 GiB, 0.28 s a step at 256^3; 5.4 GiB at 320^3) - a grid that will not fit in the
                     GPU's or the machine's free memory is refused before it runs (budget()), naming the largest cube
  steps              simulation steps over the whole sheet (default 4 x frames)
  inflow_until       fraction of the steps the source keeps feeding (0.45)
  emitter            source radius, fraction of x (0.12); emitter_z: its height, fraction of z (0.12)
  velocity           upward inflow speed, cells a step (1.4); spread: sideways jitter (0.6)
  buoyancy, weight   lift from heat, sink from smoke (1.0, 0.05); vorticity (0.7); turbulence (0.6)
  cooling, dissipation   heat and smoke loss a step (0.012, 0.002)
  max_speed, damping     the CFL speed limit (2.5 cells a step) and velocity damping a step (0.004)
  density            render extinction (110); albedo [r, g, b] (0.9); ambient (0.1)
  light              top | left | right | back | front (the key light's side); key 1.7; fill 0.3 (from above)
  sheet_start / sheet_end    the slice of the simulation the frames cover (0.12, 1.0)
  maccormack         sharp advection of what is seen (true; false = plain semi-Lagrangian, softer)
  edge_fade          the fraction of the frame over which smoke fades out at the sides / top (0.1); edge_floor: the floor too
  fire               gpu_fire: fuel burns into heat + smoke; emission colour from temperature (blackbody ramp)
  stem               { radius 0.06, until 0.7, density 0.8, heat 0.5, velocity 1.0 }: a second floor source, a dust
                     column the rising mass draws up (a mushroom cloud's stem)
  heat               the main source's temperature (1.0); a big short hot release + buoyancy rolls into a vortex ring
  ceiling            an inversion at this fraction of the height: the mass stops rising and spreads (a mushroom cap)
  surge              { radius 0.08, width 0.05, height 0.12, until 0.25, speed 1.6, density 0.9, heat 0.15 }: a ring on
                     the floor blowing OUTWARD (a base surge rolling along the ground)
  swirl              { strength 1.0, core 0.08, rise 0.3, inflow 0.3, height 0.15, until 1.0 }: a VORTEX round the vertical axis
                     (Rankine: rigid inside `core`, core/r outside), spinning up over `rise`, air drawn in below
                     `height`; spin flings the column out, inflow pulls it in - balance the two (a fire whirl, a tornado)
  view               "top": the camera ABOVE, looking down the vertical axis - a surge seen along the floor's normal is a
                     dust DISC spreading on a surface (a bullet's hit on a wall, filmed face-on); the key light's "top" is
                     then the camera's side ("left" / "right" give relief across the disc); use edge_floor: true
Lit variants: specs {"recipe": "lit_variant", "of": <this sim>, "light": <side>} are rendered from the SAME frames; view
variants {"recipe": "view_variant", "of": <sim>, "yaw": 90, "light"?} = the same cloud seen from round the side (impostors:
a sprite's `views` table picks by where the camera is round the effect).
Writes build/fxlab/<name>/NNN.npy (linear HDR, premultiplied RGBA, float16) + frames.json, as fxlab does; fxfinish packs
them. Prints one JSON line {status, summary, next_action, renders}.
"""
import json
import math
import os
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F

DEV = "cuda" if torch.cuda.is_available() else "cpu"
SIDES = ("top", "left", "right", "back", "front")


# ---------------------------------------------------------------- grid helpers (tensors are [Z, Y, X])
def shift(a, dz=0, dy=0, dx=0):
    """a value from the neighbour (edge cells repeat: a closed, zero-gradient wall)"""
    if dz:
        a = torch.cat([a[1:], a[-1:]], 0) if dz > 0 else torch.cat([a[:1], a[:-1]], 0)
    if dy:
        a = torch.cat([a[:, 1:], a[:, -1:]], 1) if dy > 0 else torch.cat([a[:, :1], a[:, :-1]], 1)
    if dx:
        a = torch.cat([a[:, :, 1:], a[:, :, -1:]], 2) if dx > 0 else torch.cat([a[:, :, :1], a[:, :, :-1]], 2)
    return a


def grad(a):
    return ((shift(a, dx=1) - shift(a, dx=-1)) * 0.5, (shift(a, dy=1) - shift(a, dy=-1)) * 0.5, (shift(a, dz=1) - shift(a, dz=-1)) * 0.5)


def advect(fields, ux, uy, uz, base):
    """semi-Lagrangian: every field sampled back along the velocity (trilinear, one grid_sample for all)"""
    Z, Y, X = ux.shape
    gx = (base[0] - ux) / (X - 1) * 2 - 1
    gy = (base[1] - uy) / (Y - 1) * 2 - 1
    gz = (base[2] - uz) / (Z - 1) * 2 - 1
    g = torch.stack([gx, gy, gz], -1)[None]
    stacked = torch.stack(fields, 0)[None]
    out = F.grid_sample(stacked, g, mode="bilinear", padding_mode="border", align_corners=True)[0]
    return [out[i] for i in range(len(fields))]


def maccormack(fields, ux, uy, uz, base):
    """MacCormack advection: a forward step, a backward step, half the round-trip error added back, clamped to the
    neighbourhood the forward step sampled (keeps the small swirls a plain semi-Lagrangian step blurs away)"""
    fwd = advect(fields, ux, uy, uz, base)
    back = advect(fwd, -ux, -uy, -uz, base)
    out = []
    for f0, f1, f2 in zip(fields, fwd, back):
        corr = f1 + 0.5 * (f0 - f2)
        # the clamp: between the min and max of the 6 neighbours of the forward sample (an approximation on the grid)
        lo = torch.minimum(torch.minimum(torch.minimum(shift(f1, dx=1), shift(f1, dx=-1)), torch.minimum(shift(f1, dy=1), shift(f1, dy=-1))), torch.minimum(torch.minimum(shift(f1, dz=1), shift(f1, dz=-1)), f1))
        hi = torch.maximum(torch.maximum(torch.maximum(shift(f1, dx=1), shift(f1, dx=-1)), torch.maximum(shift(f1, dy=1), shift(f1, dy=-1))), torch.maximum(torch.maximum(shift(f1, dz=1), shift(f1, dz=-1)), f1))
        out.append(torch.clamp(corr, lo, hi))
    return out


def project(ux, uy, uz, iters):
    """remove the divergence (incompressible flow): Jacobi on the pressure; the top stays open"""
    div = ((shift(ux, dx=1) - shift(ux, dx=-1)) + (shift(uy, dy=1) - shift(uy, dy=-1)) + (shift(uz, dz=1) - shift(uz, dz=-1))) * 0.5
    p = torch.zeros_like(div)
    for _ in range(iters):
        p = (shift(p, dx=1) + shift(p, dx=-1) + shift(p, dy=1) + shift(p, dy=-1) + shift(p, dz=1) + shift(p, dz=-1) - div) / 6.0
        p[-1] = 0  # open top: the plume leaves
    gx, gy, gz = grad(p)
    return ux - gx, uy - gy, uz - gz


def curl_noise(shape, scale, t, seed):
    """a smooth divergence-free turbulence field (sum of a few random sine waves' curls), cheap on the GPU"""
    Z, Y, X = shape
    g = torch.Generator(device="cpu").manual_seed(seed)
    zz, yy, xx = torch.meshgrid(torch.arange(Z, device=DEV, dtype=torch.float32), torch.arange(Y, device=DEV, dtype=torch.float32),
                                torch.arange(X, device=DEV, dtype=torch.float32), indexing="ij")
    vx = torch.zeros(shape, device=DEV)
    vy = torch.zeros(shape, device=DEV)
    vz = torch.zeros(shape, device=DEV)
    for _ in range(6):
        k = (torch.randn(3, generator=g) * 2 * math.pi / scale).tolist()
        a = torch.randn(3, generator=g).tolist()
        ph = float(torch.rand(1, generator=g)) * 6.28 + t * float(torch.randn(1, generator=g)) * 0.05
        s = torch.cos(k[0] * xx + k[1] * yy + k[2] * zz + ph)  # psi = a * sin(k.x): curl = (k x a) cos(k.x)
        cx, cy, cz = k[1] * a[2] - k[2] * a[1], k[2] * a[0] - k[0] * a[2], k[0] * a[1] - k[1] * a[0]
        vx += cx * s
        vy += cy * s
        vz += cz * s
    m = max(float(torch.sqrt(vx * vx + vy * vy + vz * vz).max()), 1e-6)
    return vx / m, vy / m, vz / m


# ---------------------------------------------------------------- the simulation
# ---------------------------------------------------------------- named profiles (LIMITATIONS_FIXES_V4 3.4 step 4)
# "Raise gpusim.py to 256^3-384^3 (vorticity >= 2)". The defaults below a spec's own params stay what every older bake
# was made with (128-cell grid, vorticity 0.7): a judged sheet bakes again byte for byte (test_vfx_gpusim_profile proves
# one). A spec that says "profile": "hero" takes the hero defaults instead - a NEW bake: a 256 x 256 x 320 grid,
# vorticity confinement 2.0, more pressure iterations for the bigger grid, and the speeds (cells a step) scaled by the
# grid's size over 128, so the motion covers the same share of the frame (measured 2026-11-20: a 256^3 grid with the old
# speeds travels half as far). The spec's own value of a key always wins, as written.
GRID_SPEEDS = ("velocity", "spread", "max_speed", "buoyancy", "weight", "turbulence")
OLD_DEFAULTS = {"res": [128, 128, 160], "vorticity": 0.7, "pressure_iters": 40, "velocity": 1.4, "spread": 0.6,
                "max_speed": 2.5, "buoyancy": 1.0, "weight": 0.05, "turbulence": 0.6}
PROFILES = {
    "hero": {"res": [256, 256, 320], "vorticity": 2.0, "pressure_iters": 80},
}
HERO_RES = (256, 384)   # a hero grid's sides (x and y; z may run taller for a rising mass)
HERO_VORTICITY = 2.0


def params_of(spec):
    """the params a spec is simulated and rendered with: its own, over its profile's defaults (none: its own as they
    are - the same dict, so an older bake cannot change)"""
    p = spec.get("params", {})
    name = spec.get("profile")
    if name is None:
        return p
    prof = PROFILES[name]
    out = dict(prof)
    k = prof["res"][0] / OLD_DEFAULTS["res"][0]
    for key in GRID_SPEEDS:
        out[key] = OLD_DEFAULTS[key] * k
    out.update(p)
    return out


def profile_problems(spec):
    """what is wrong with a spec's profile -> [problem]: an unknown profile, or a hero sim below the doc's bar (its
    grid's sides 256..384 cells, vorticity >= 2) - a "hero" that bakes a small soft sim is not one"""
    name = spec.get("profile")
    if name is None:
        return []
    if name not in PROFILES:
        return [f'profile "{name}" is not one of {", ".join(PROFILES)} (none = the old defaults)']
    if name != "hero":
        return []
    p, bad = params_of(spec), []
    res = p.get("res")
    if not (isinstance(res, list) and len(res) == 3 and all(isinstance(v, int) and not isinstance(v, bool) for v in res)):
        return ["res is [x, y, z] whole cells"]
    lo, hi = HERO_RES
    if not (lo <= res[0] <= hi and lo <= res[1] <= hi and lo <= res[2] <= hi * 1.25):
        bad.append(f"a hero sim's grid is {lo}..{hi} cells a side (z up to {int(hi * 1.25)}): res {res}")
    if not (isinstance(p.get("vorticity"), (int, float)) and p["vorticity"] >= HERO_VORTICITY):
        bad.append(f"a hero sim's vorticity is {HERO_VORTICITY} or more (the fine curls of a 256^3 grid): {p.get('vorticity')}")
    return bad


def starter(fire=False):
    """a NEW sim's spec: the hero profile (what new bakes use); its numbers are the author's to tune"""
    return {"engine": "fx", "recipe": "gpu_fire" if fire else "gpu_smoke", "profile": "hero", "frames": 64, "grid": 8,
            "cell": 128, "seed": 1,
            "about": "a hero GPU sim (kit/vfx/gpusim.py --new): 256 x 256 x 320, vorticity 2 - say what it is and tune it",
            "params": {"light": "top", "inflow_until": 0.3, "edge_fade": 0.12},
            "post": {"alpha": "coverage", "exposure": 1.0}}


def simulate(spec, keep):
    p = params_of(spec)
    X, Y, Z = p.get("res", [128, 128, 160])
    frames = int(spec.get("frames", 16))
    steps = int(p.get("steps", frames * 4))
    fire = spec.get("recipe") == "gpu_fire" or p.get("fire", False)
    seed = int(spec.get("seed", 1))
    torch.manual_seed(seed)
    shape = (Z, Y, X)
    ux = torch.zeros(shape, device=DEV)
    uy = torch.zeros(shape, device=DEV)
    uz = torch.zeros(shape, device=DEV)
    dens = torch.zeros(shape, device=DEV)
    temp = torch.zeros(shape, device=DEV)
    fuel = torch.zeros(shape, device=DEV)
    zz, yy, xx = torch.meshgrid(torch.arange(Z, device=DEV, dtype=torch.float32), torch.arange(Y, device=DEV, dtype=torch.float32),
                                torch.arange(X, device=DEV, dtype=torch.float32), indexing="ij")
    base = (xx, yy, zz)
    cx, cy, cz = (X - 1) / 2, (Y - 1) / 2, Z * p.get("emitter_z", 0.12)
    rad = X * p.get("emitter", 0.12)
    r = torch.sqrt((xx - cx) ** 2 + (yy - cy) ** 2 + ((zz - cz) * 1.4) ** 2)
    src = torch.clamp(1 - r / rad, 0, 1) ** 0.7
    # source breakup: a frozen noise mask so the inflow is lumpy, not a perfect ball
    nm = torch.rand((max(Z // 8, 2), max(Y // 8, 2), max(X // 8, 2)), device=DEV, generator=None)
    lump = F.interpolate(nm[None, None], size=shape, mode="trilinear", align_corners=False)[0, 0]
    src = src * (0.55 + 0.9 * lump)
    tvx, tvy, tvz = curl_noise(shape, scale=max(X, Z) * 0.35, t=0, seed=seed + 7)
    # an inversion layer: above `ceiling` (a fraction of the height) heat stops lifting and pushes back, so a rising mass
    # stops, spreads sideways and rolls under at its rim (the flattened mushroom cap); none = 1 everywhere
    ceil = p.get("ceiling")
    lift = torch.clamp((Z * ceil - zz) / (Z * 0.12), -0.6, 1.0) if ceil else torch.ones(shape, device=DEV)
    edge = torch.minimum(torch.minimum(torch.minimum(xx, X - 1 - xx), torch.minimum(yy, Y - 1 - yy)), (Z - 1 - zz) * 1.0)
    sponge = torch.clamp(edge / 6.0, 0, 1) * 0.06 + 0.94  # the outer 6 cells lose 6 % a step
    inflow = int(steps * p.get("inflow_until", 0.45))
    vel, spread = p.get("velocity", 1.4), p.get("spread", 0.6)
    buoy, weight, vort, turb = p.get("buoyancy", 1.0), p.get("weight", 0.05), p.get("vorticity", 0.7), p.get("turbulence", 0.6)
    cool, diss = p.get("cooling", 0.012), p.get("dissipation", 0.002)
    iters = int(p.get("pressure_iters", 40))
    s0, s1 = p.get("sheet_start", 0.12), p.get("sheet_end", 1.0)
    want = [int(round((s0 + (s1 - s0) * k / max(frames - 1, 1)) * (steps - 1))) for k in range(frames)]
    out = []
    for step in range(steps):
        if step % 12 == 0:  # the turbulence and the source's lumps change over time (a fixed pattern stacks into rings)
            tvx, tvy, tvz = curl_noise(shape, scale=max(X, Z) * 0.3, t=step, seed=seed + 7 + step)
            nm = torch.rand((max(Z // 6, 2), max(Y // 6, 2), max(X // 6, 2)), device=DEV)
            lump = F.interpolate(nm[None, None], size=shape, mode="trilinear", align_corners=False)[0, 0]
            src = torch.clamp(1 - r / rad, 0, 1) ** 0.7 * (0.35 + 1.3 * lump)
        if step < inflow:
            fade = 1 - step / max(inflow, 1) * 0.5
            dens = torch.maximum(dens, src * fade)
            temp = torch.maximum(temp, src * p.get("heat", 1.0) * fade)
            if fire:
                fuel = torch.maximum(fuel, src * fade)
            uz = uz + src * vel * 0.5
            ux = ux + src * tvx * spread
            uy = uy + src * tvy * spread
        surge = p.get("surge")
        if surge and step < int(steps * surge.get("until", 0.25)):  # a ring on the floor blowing OUTWARD: a base surge
            rr = torch.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) + 1e-3
            r0, w0 = X * surge.get("radius", 0.08), X * surge.get("width", 0.05)
            band = torch.clamp(1 - torch.abs(rr - r0) / w0, 0, 1) * (zz < Z * surge.get("height", 0.12)).float() * (0.5 + 1.0 * lump)
            dens = torch.maximum(dens, band * surge.get("density", 0.9))
            temp = torch.maximum(temp, band * surge.get("heat", 0.15))
            sp = surge.get("speed", 1.6)
            ux = ux + band * (xx - cx) / rr * sp * 0.5
            uy = uy + band * (yy - cy) / rr * sp * 0.5
        stem = p.get("stem")
        if stem and step < int(steps * stem.get("until", 0.7)):  # a second source on the floor: dust drawn up as a column
            sr = X * stem.get("radius", 0.06)
            sm = torch.clamp(1 - torch.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / sr, 0, 1) * (zz < Z * 0.04).float() * (0.4 + 1.2 * lump)
            dens = torch.maximum(dens, sm * stem.get("density", 0.8))
            temp = torch.maximum(temp, sm * stem.get("heat", 0.5))
            uz = uz + sm * stem.get("velocity", 1.0) * 0.5
        swirl = p.get("swirl")
        if swirl and step < int(steps * swirl.get("until", 1.0)):  # a VORTEX round the vertical axis (a fire whirl, a tornado)
            rr = torch.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) + 1e-3
            core = X * swirl.get("core", 0.08)
            # Rankine: rigid rotation inside the core, falling off as core / r outside; it spins UP over `rise`. A PUSH each
            # step, not a target speed (review 2026-10-25): the CFL cap (max_speed) clips it within a few steps, so
            # `strength` sets how fast the flow reaches the cap and the profile flattens toward it; the cap also slows the rise
            prof = torch.where(rr < core, rr / core, core / rr)
            spin = swirl.get("strength", 1.0) * min(1.0, step / max(1.0, steps * swirl.get("rise", 0.3)))
            ux = ux - (yy - cy) / rr * prof * spin * 0.25
            uy = uy + (xx - cx) / rr * prof * spin * 0.25
            # air drawn in below `height` (the floor by default) - what feeds a whirl. MEASURED (test_gpusim_swirl): the spin
            # alone flings the column OUT (radius x2.4 on a small grid); the inflow pulls most of it back - their balance
            # sets the width (firewhirl's core: strength 2.6 / inflow 0.45 up to 0.45 of the height, at 128 x 256)
            pull = swirl.get("inflow", 0.3) * spin * (zz < Z * swirl.get("height", 0.15)).float() * torch.clamp(rr / core, 0, 1)
            ux = ux - (xx - cx) / rr * pull * 0.25
            uy = uy - (yy - cy) / rr * pull * 0.25
        # forces: buoyancy, vorticity confinement, a little turbulence where there is smoke
        uz = uz + (buoy * temp * lift - weight * dens) * 0.25
        if vort > 0:
            wx = (shift(uz, dy=1) - shift(uz, dy=-1) - shift(uy, dz=1) + shift(uy, dz=-1)) * 0.5
            wy = (shift(ux, dz=1) - shift(ux, dz=-1) - shift(uz, dx=1) + shift(uz, dx=-1)) * 0.5
            wz = (shift(uy, dx=1) - shift(uy, dx=-1) - shift(ux, dy=1) + shift(ux, dy=-1)) * 0.5
            wm = torch.sqrt(wx * wx + wy * wy + wz * wz)
            nx, ny, nz = grad(wm)
            nl = torch.sqrt(nx * nx + ny * ny + nz * nz) + 1e-5
            nx, ny, nz = nx / nl, ny / nl, nz / nl
            ux = ux + vort * (ny * wz - nz * wy)
            uy = uy + vort * (nz * wx - nx * wz)
            uz = uz + vort * (nx * wy - ny * wx)
        if turb > 0:
            k = turb * torch.clamp(dens, 0, 1)
            ux, uy, uz = ux + tvx * k * 0.2, uy + tvy * k * 0.2, uz + tvz * k * 0.2
        if fire:  # fuel burns: heat and smoke where it is, it shrinks
            burn = torch.clamp(fuel, 0, 1) * 0.12
            temp = temp + burn * 2.5
            dens = dens + burn * 0.6
            fuel = fuel - burn
        # stability: a speed limit (CFL: no cell crosses more than `max_speed` cells a step) and a little damping, or a
        # hot release accelerates without bound and the grid fills (measured: the first mushroom filled its box)
        sp = torch.sqrt(ux * ux + uy * uy + uz * uz) + 1e-6
        lim = torch.clamp(p.get("max_speed", 2.5) / sp, max=1.0)
        damp = 1 - p.get("damping", 0.004)
        ux, uy, uz = ux * lim * damp, uy * lim * damp, uz * lim * damp
        # walls: no flow through the sides / floor
        ux[:, :, 0] = ux[:, :, -1] = 0
        uy[:, 0] = uy[:, -1] = 0
        uz[0] = torch.clamp(uz[0], min=0)
        ux, uy, uz = project(ux, uy, uz, iters)
        if p.get("maccormack", True):
            ux, uy, uz = advect([ux, uy, uz], ux, uy, uz, base)  # velocity: plain (stable)
            dens, temp, fuel = maccormack([dens, temp, fuel], ux, uy, uz, base)  # what we SEE: sharp
        else:
            ux, uy, uz, dens, temp, fuel = advect([ux, uy, uz, dens, temp, fuel], ux, uy, uz, base)
        temp = temp * (1 - cool)
        dens = torch.clamp(dens * (1 - diss), 0, 4)
        # open boundaries: what reaches the top or the side walls leaves (a sponge layer fades it out)
        dens = dens * sponge
        temp = temp * sponge
        if step in want:
            for _ in range(want.count(step)):
                out.append((dens.half().cpu(), temp.half().cpu(), fuel.half().cpu()))
    return out


# ---------------------------------------------------------------- the renderer (camera at -Y looking +Y, z up)
def blackbody(t):
    """temperature (0..~3) -> emission colour: dark red -> orange -> yellow -> white"""
    r = torch.clamp(t * 1.4, 0, 1)
    g = torch.clamp((t - 0.45) * 0.75, 0, 1) ** 1.3  # orange through the body, yellow only where it is very hot
    b = torch.clamp((t - 1.6) * 0.9, 0, 1) ** 1.5  # white only at the core
    return r, g, b


def turn(fields, yaw):
    """the volume turned about its vertical axis by `yaw` degrees (a camera moved round the effect by +yaw sees the cloud
    turned by -yaw): every field resampled on the turned grid (trilinear)"""
    if not yaw:
        return fields
    Z, Y, X = fields[0].shape
    a = math.radians(-yaw)
    zz, yy, xx = torch.meshgrid(torch.linspace(-1, 1, Z, device=DEV), torch.linspace(-1, 1, Y, device=DEV), torch.linspace(-1, 1, X, device=DEV), indexing="ij")
    sx = (xx * math.cos(a) - yy * math.sin(a) * (Y / X)) if X else xx
    sy = (xx * math.sin(a) * (X / Y) + yy * math.cos(a))
    g = torch.stack([sx, sy, zz], -1)[None]
    st = torch.stack(fields, 0)[None]
    out = F.grid_sample(st, g, mode="bilinear", padding_mode="zeros", align_corners=True)[0]
    return [out[i] for i in range(len(fields))]


def render(frame, p, light, fire, yaw=0):
    dens, temp, fuel = turn([x.to(DEV).float() for x in frame], yaw)
    top_view = p.get("view") == "top"
    if top_view:  # (2026-11-10) the camera above: z becomes the depth (the top cell first), y the rows; the key's "top"
        # (and "front") is the camera's side, "back" lights it from under the surface (thin edges glow); the fill keeps the
        # grid's +y side here: it rakes in from the picture's far edge - a second side light, the relief of a hit on a wall
        dens, temp, fuel = [torch.flip(f.permute(1, 0, 2), [1]) for f in (dens, temp, fuel)]
        light = {"top": "front"}.get(light, light)
    k = p.get("density", 110.0) / max(dens.shape)  # extinction per cell (resolution-independent)
    sig = dens * k
    # light transmittance from the key's side (an exclusive running sum: a cell is shadowed by what is between it and
    # the light) and a soft fill from above
    def trans_from(side):
        if side == "top":  # from +z going down
            c = torch.flip(torch.cumsum(torch.flip(sig, [0]), 0), [0]) - sig
        elif side == "left":  # from -x going +x
            c = torch.cumsum(sig, 2) - sig
        elif side == "right":
            c = torch.flip(torch.cumsum(torch.flip(sig, [2]), 2), [2]) - sig
        elif side == "back":  # from +y (behind) toward the camera
            c = torch.flip(torch.cumsum(torch.flip(sig, [1]), 1), [1]) - sig
        else:  # front: from the camera's side
            c = torch.cumsum(sig, 1) - sig
        return torch.exp(-c)
    key, fill, amb = p.get("key", 1.7), p.get("fill", 0.3), p.get("ambient", 0.1)
    lit = key * trans_from(light) + fill * trans_from("top") + amb  # (top view: the fill rakes in from the picture's far edge)
    if light == "back":  # light pushed through toward the camera scatters forward: thin edges glow
        lit = lit + key * 0.8 * trans_from("back") * torch.exp(-sig * 2)
    alb = p.get("albedo", [0.9, 0.9, 0.9])
    alb = alb if isinstance(alb, list) else [alb] * 3
    view = torch.exp(-(torch.cumsum(sig, 1) - sig))  # camera transmittance up to each cell
    w = view * (1 - torch.exp(-sig))  # each cell's contribution
    rgb = []
    if fire:
        er, eg, eb = blackbody(temp)
        em = p.get("emission", 2.5) * torch.clamp(temp - 0.25, 0, None)
    for c in range(3):
        col = (w * lit * alb[c]).sum(1)
        if fire:
            col = col + (view * (er, eg, eb)[c] * em * (1 - torch.exp(-sig - 0.02))).sum(1)
        rgb.append(col)
    alpha = 1 - torch.exp(-sig.sum(1))
    img = torch.stack(rgb + [alpha], -1)  # [Z, X, 4], z up
    # a soft edge: smoke that reaches the domain's sides / top fades out before the cell's border, or a spread-out puff
    # shows its sprite as a hard square card (measured 2026-10-22: nuke_v2's surge read as stacked square cards). The
    # floor keeps its edge unless `edge_floor` (a plume stands on it; a free puff does not)
    ef = p.get("edge_fade", 0.1)
    if ef > 0:
        Zi, Xi = img.shape[0], img.shape[1]
        zr = torch.linspace(0, 1, Zi, device=img.device)[:, None]
        xr = torch.linspace(0, 1, Xi, device=img.device)[None, :]
        def ramp(d):
            return torch.clamp(d / ef, 0, 1) ** 1.5
        m = ramp(xr) * ramp(1 - xr) * ramp(1 - zr)
        if p.get("edge_floor", False):
            m = m * ramp(zr)
        img = img * m[..., None]
    img = torch.flip(img, [0])  # row 0 = the top of the picture
    return img


def resize(img, cell, margin=0.06):
    """the domain into the square cell, standing on its floor, a `margin` clear above and at the sides (fxfinish fades
    the cell's edges: a cap touching the edge gets cut)"""
    t = img.permute(2, 0, 1)[None]
    h, w = t.shape[2], t.shape[3]
    s = cell * (1 - margin) / max(h, w)
    t = F.interpolate(t, size=(max(1, round(h * s)), max(1, round(w * s))), mode="bilinear", align_corners=False)
    out = torch.zeros((1, 4, cell, cell), device=t.device)
    oh, ow = t.shape[2], t.shape[3]
    y0, x0 = cell - oh, (cell - ow) // 2  # the plume stands on the cell's floor, centred
    out[:, :, y0:y0 + oh, x0:x0 + ow] = t
    return out[0].permute(1, 2, 0)


def write(out_dir, name, imgs, spec_path, cell, extra=None):
    fdir = os.path.join(out_dir, name)
    os.makedirs(fdir, exist_ok=True)
    for f in os.listdir(fdir):
        if f.endswith(".npy"):
            os.remove(os.path.join(fdir, f))
    for i, img in enumerate(imgs):
        np.save(os.path.join(fdir, f"{i:03d}.npy"), resize(img, cell).cpu().numpy().astype(np.float16))
    meta = {"frames": len(imgs), "spec_mtime": os.path.getmtime(spec_path), "engine": "gpusim"}
    meta.update(extra or {})
    with open(os.path.join(fdir, "frames.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)


# the memory a grid takes, MEASURED on a 12 GB RTX 5070 (LIMITATIONS_FIXES_V4 3.4 step 4, gpusim to 256^3+:
# gpu_dust_puff at 128^3 / 256^3 / 320^3 peaked at 0.34 / 2.75 / 5.40 GiB = 170 / 176 / 177 bytes a cell, 0.09 / 0.28 /
# 0.58 s a step), + a margin. The kept frames live in host memory: 3 fields a frame in float16
GPU_BYTES_PER_CELL = 177 * 1.15
HOST_BYTES_PER_CELL_FRAME = 3 * 2


def budget(spec, free_gpu=None, free_host=None):
    """can this spec's grid run here -> (ok, why, largest cube that fits). free_gpu / free_host in bytes (default:
    what the GPU and the machine have free now). A grid that does not fit is refused BEFORE it runs: an out-of-memory
    crash half way through a long bake says nothing useful"""
    p = params_of(spec)
    X, Y, Z = p.get("res", [128, 128, 160])
    cells = int(X) * int(Y) * int(Z)
    frames = int(spec.get("frames", 16))
    if free_gpu is None:
        free_gpu = torch.cuda.mem_get_info()[0] if DEV == "cuda" else 0
    if free_host is None:
        try:
            import psutil
            free_host = psutil.virtual_memory().available
        except ImportError:
            free_host = float("inf")
    need_gpu = cells * GPU_BYTES_PER_CELL
    need_host = cells * frames * HOST_BYTES_PER_CELL_FRAME
    cube = int(min((free_gpu / GPU_BYTES_PER_CELL) ** (1 / 3), (free_host / (frames * HOST_BYTES_PER_CELL_FRAME)) ** (1 / 3)))
    if need_gpu > free_gpu:
        return False, (f"res {X} x {Y} x {Z} needs ~{need_gpu / 2 ** 30:.1f} GiB of GPU memory, {free_gpu / 2 ** 30:.1f} GiB "
                       f"is free (the largest cube that fits now: {cube}^3)"), cube
    if need_host > free_host:
        return False, (f"res {X} x {Y} x {Z} keeps {frames} frames: ~{need_host / 2 ** 30:.1f} GiB of host memory, "
                       f"{free_host / 2 ** 30:.1f} GiB free (fewer frames, or the largest cube that fits: {cube}^3)"), cube
    return True, "", cube


def steps_per_frame(p, frames):
    """how many simulation steps lie between two sheet frames: under 2 the picked steps alternate 1 and 2 apart (a
    fractional stride), and every other pair of frames is nearly identical (skyfall's surge 2026-10-25: 1.7 per frame,
    fx finish's frames_change failed on the half-steps)"""
    steps = int(p.get("steps", frames * 4))
    s0, s1 = p.get("sheet_start", 0.12), p.get("sheet_end", 1.0)
    return (steps - 1) * (s1 - s0) / max(frames - 1, 1)


def headroom(imgs, p):
    """the cut-off gate (owner 2026-10-22, nuke_v3: "the explosion cuts off at the top"): the smallest gap between the
    smoke and the frame's top / sides over all frames, as a fraction of the frame. Smoke inside the edge-fade band is
    being FADED OFF by the frame - it reads as a flat cut. Returns (top, side, worst frame)"""
    top, side, worst = 1.0, 1.0, -1
    for i, img in enumerate(imgs):
        a = img[..., 3]
        Zi, Xi = a.shape
        rows = torch.nonzero(a.amax(1) > 0.2)
        cols = torch.nonzero(a.amax(0) > 0.2)
        if len(rows):
            t = float(rows.min()) / Zi
            if t < top:
                top, worst = t, i
        if len(cols):
            side = min(side, float(cols.min()) / Xi, float(Xi - 1 - cols.max()) / Xi)
    return top, side, worst


def fresh(out_dir, name, spec_path):
    meta = os.path.join(out_dir, name, "frames.json")
    if not os.path.isfile(meta):
        return False
    with open(meta, encoding="utf-8") as fh:
        return json.load(fh).get("spec_mtime") == os.path.getmtime(spec_path)


def main(argv):
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    specs, out = opt("--specs", os.path.join("assets", "textures")), opt("--out", os.path.join("build", "fxlab"))
    force = "--force" in argv
    if "--new" in argv:   # a NEW sim's spec, on the hero profile (never over an existing spec)
        name = opt("--new", "")
        path = os.path.join(specs, f"{name}.json")
        ok_name = bool(name) and all(c.islower() or c.isdigit() or c == "_" for c in name)
        if not ok_name or os.path.exists(path):
            print(json.dumps({"schema": 1, "status": "fail",
                              "summary": f"gpusim --new: {name!r} " + ("exists already" if ok_name else "is not a texture key (a-z, 0-9, _)"),
                              "next_action": "another name; an existing spec is edited, never overwritten"}))
            return 1
        os.makedirs(specs, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(starter("--fire" in argv), fh, indent=1)
            fh.write("\n")
        print(json.dumps({"schema": 1, "status": "pass",
                          "summary": f"gpusim --new: {path} written on the hero profile (256 x 256 x 320, vorticity 2)",
                          "next_action": f"tune its params, then: python kit/vfx/gpusim.py --specs {specs} --out {out} {name}"}))
        return 0
    names = [a for a in argv if not a.startswith("--") and a not in (specs, out)]
    allspecs = {}
    for f in sorted(os.listdir(specs)):
        if f.endswith(".json"):
            try:
                with open(os.path.join(specs, f), encoding="utf-8") as fh:
                    allspecs[f[:-5]] = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
    sims = [n for n, s in allspecs.items() if s.get("engine") == "fx" and str(s.get("recipe", "")).startswith("gpu_")]
    if names:
        sims = [n for n in sims if n in names]
    results, errors, warnings = [], [], []
    for n in sims:
        spec = allspecs[n]
        path = os.path.join(specs, f"{n}.json")
        variants = [(vn, v) for vn, v in allspecs.items() if v.get("recipe") in ("lit_variant", "view_variant") and v.get("of") == n]
        stale = force or not fresh(out, n, path) or any(not fresh(out, vn, os.path.join(specs, f"{vn}.json")) for vn, _ in variants)
        if not stale:
            continue
        if DEV != "cuda":
            errors.append(f"{n}: no CUDA GPU (torch.cuda.is_available() is False)")
            continue
        problems = profile_problems(spec)
        if problems:
            errors.append(f"{n}: " + "; ".join(problems))
            continue
        fits, why, _ = budget(spec)
        if not fits:
            errors.append(f"{n}: {why}")
            continue
        t0 = time.time()
        try:
            p = params_of(spec)
            fire = spec.get("recipe") == "gpu_fire"
            spf = steps_per_frame(p, int(spec.get("frames", 16)))  # 16: simulate()'s own default (review: 64 here disagreed)
            if spf < 2:
                warnings.append(f"{n}: {spf:.1f} simulation steps per sheet frame - under 2 the frames alternate one and two steps "
                                f"apart and half of them barely move (fx finish: frames_change): more steps, or a wider sheet_start..sheet_end")
            sim = simulate(spec, keep=True)
            t_sim = time.time() - t0
            cell = int(spec.get("cell", 128))
            with torch.no_grad():
                main_imgs = [render(fr, p, p.get("light", "top"), fire) for fr in sim]
                top, side, worst = headroom(main_imgs, p)
                ef = p.get("edge_fade", 0.1)
                if top < ef * 0.6:
                    warnings.append(f"{n}: the smoke reaches the top {top * 100:.0f} % of the frame (frame {worst}) - it is faded off there and reads as a CUT: a taller res z, a lower ceiling or an earlier sheet_end")
                if side < ef * 0.6:
                    warnings.append(f"{n}: the smoke reaches the frame's side ({side * 100:.0f} % gap) - a wider res x / y, or an earlier sheet_end")
                write(out, n, main_imgs, path, cell, {"headroom_top": round(top, 3), "headroom_side": round(side, 3)})
                for vn, v in variants:
                    light = v.get("light", p.get("light", "top"))
                    if light not in SIDES:
                        errors.append(f"{vn}: light must be one of {', '.join(SIDES)}")
                        continue
                    yaw = float(v.get("yaw", 0)) if v.get("recipe") == "view_variant" else 0.0
                    write(out, vn, [render(fr, p, light, fire, yaw) for fr in sim], os.path.join(specs, f"{vn}.json"), cell, {"of": n, "yaw": yaw})
            torch.cuda.empty_cache()
            results.append({"name": n, "frames": len(sim), "variants": [vn for vn, _ in variants], "sim_s": round(t_sim, 1), "total_s": round(time.time() - t0, 1)})
        except Exception as e:  # noqa: BLE001
            errors.append(f"{n}: {type(e).__name__}: {e}")
    print(json.dumps({"schema": 1, "status": "fail" if errors else "pass",
                      "summary": "; ".join(errors) if errors else f"gpusim: {len(results)} GPU sim(s) rendered ({', '.join(r['name'] + ' ' + str(r['total_s']) + ' s' for r in results) or 'all fresh'})" + (f"; WARNINGS: {'; '.join(warnings)}" if warnings else ""),
                      "next_action": "fix the spec named above" if errors else ("fix the cut-off named above (re-simulate), then fxfinish packs the sheets" if warnings else "none - fxfinish packs the sheets"),
                      "renders": results, "warnings": warnings}))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
