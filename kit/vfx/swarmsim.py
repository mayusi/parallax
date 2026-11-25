"""swarmsim.py - tune a `swarm` layer WITHOUT recording: the player's SwarmLayer maths (kit/vfx/player/player.js:
curl3 noise, attract + swirl, gravity, drag, floor; the same seeds are not reproduced, the same physics is) ported to numpy,
run over the preset's swarm layers, and the MASS measured per time - its centre, its spread on x / y / z, its height band.

    lune run kit vfx swarm <preset> [--layers <name prefix>] [--at 0.5,1,1.5] [--sheet]

A flock / cloud reads WIDE (spread x, z > y); a fountain reads TALL (spread y > x) - ember_murmuration round 1 rose as a
fountain of hair (spread y 10 vs x 6) and a parameter sweep here found the flat rolling mass in seconds where each
recording costs minutes (2026-10-24). --sheet draws side + top scatter views to build/vfx/swarm/<preset>.png.
Prints one JSON line (status / summary / next_action) like every kit tool."""
import json
import math
import os
import sys

import numpy as np


def hash3(i, j, k):
    x = np.sin(i * 127.1 + j * 311.7 + k * 74.7) * 43758.5453
    return x - np.floor(x)


def noise3(x, y, z):
    i, j, k = np.floor(x), np.floor(y), np.floor(z)
    fx, fy, fz = x - i, y - j, z - k
    ux, uy, uz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
    L = lambda a, b, t: a + (b - a) * t
    x00 = L(hash3(i, j, k), hash3(i + 1, j, k), ux); x10 = L(hash3(i, j + 1, k), hash3(i + 1, j + 1, k), ux)
    x01 = L(hash3(i, j, k + 1), hash3(i + 1, j, k + 1), ux); x11 = L(hash3(i, j + 1, k + 1), hash3(i + 1, j + 1, k + 1), ux)
    return L(L(x00, x10, uy), L(x01, x11, uy), uz) * 2 - 1


def curl3(x, y, z):
    e = 0.1
    psi = lambda a, b, c: (noise3(a, b, c), noise3(a + 31.4, b + 7.1, c + 2.9), noise3(a + 11.3, b + 53.7, c + 17.2))
    dx1, dx0, dy1, dy0 = psi(x + e, y, z), psi(x - e, y, z), psi(x, y + e, z), psi(x, y - e, z)
    dz1, dz0 = psi(x, y, z + e), psi(x, y, z - e)
    k = 1 / (2 * e)
    return np.stack([((dy1[2] - dy0[2]) - (dz1[1] - dz0[1])) * k, ((dz1[0] - dz0[0]) - (dx1[2] - dx0[2])) * k,
                     ((dx1[1] - dx0[1]) - (dy1[0] - dy0[0])) * k], -1)


def num_at(v, u, dflt):
    if v is None:
        return dflt
    if isinstance(v, (int, float)):
        return v
    for a, b in zip(v, v[1:]):
        if u <= b[0]:
            k = (u - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0
            return a[1] + (b[1] - a[1]) * min(max(k, 0), 1)
    return v[-1][1]


def run(el, times, rng):
    n = max(1, min(150, int(el.get("count", 40))))  # the player's cap
    lt = el.get("lifetime", [1, 1]); lt = [lt, lt] if isinstance(lt, (int, float)) else lt
    sp = el.get("speed", [4, 8]); sp = [sp, sp] if isinstance(sp, (int, float)) else sp
    u = rng.uniform(-1, 1, n); th = rng.uniform(0, 2 * math.pi, n); s = np.sqrt(1 - u * u)
    d = np.stack([s * np.cos(th), u, s * np.sin(th)], -1)
    at = el.get("at", 0); born = at + el.get("spawn", 0) * np.arange(n) / max(n - 1, 1)
    life = lt[0] + (lt[1] - lt[0]) * rng.random(n)
    pos = np.array(el.get("point", [0, 0, 0]), float) + d * el.get("radius", 1) * np.cbrt(rng.random(n))[:, None]
    vel = d * (sp[0] + (sp[1] - sp[0]) * rng.random(n))[:, None]
    seed = rng.random(n) * 100
    curl, att, grav, drag, floor = el.get("curl"), el.get("attract"), el.get("gravity", 0), el.get("drag", 0), el.get("floor")
    dt, t, out = 1 / 60, 0.0, {}
    for T in sorted(times):
        while t < T:
            t += dt
            live = (t >= born)
            if curl:
                sc = curl.get("scale", 4)
                c = curl3(pos[:, 0] / sc + seed * 0.01, pos[:, 1] / sc + t * curl.get("speed", 0.3), pos[:, 2] / sc)
                vel += live[:, None] * c * curl.get("strength", 10) * dt
            if att:
                lu = min(1.0, max(0.0, (t - at) / max(el.get("life") or 1, 1e-3)))  # curves over the LAYER's life
                to = np.array(att.get("point", el.get("point")), float) - pos
                dist = np.maximum(np.linalg.norm(to, axis=1), 0.5); to /= np.maximum(np.linalg.norm(to, axis=1), 1e-6)[:, None]
                vel += live[:, None] * to * num_at(att.get("strength", 20), lu, 20) * dt
                sw = num_at(att.get("swirl", 0), lu, 0)
                if sw:
                    vel += live[:, None] * np.cross(to, [0, 1, 0]) * (sw / np.sqrt(dist))[:, None] * dt
            vel[:, 1] -= live * grav * dt
            dg = num_at(drag, min(1.0, max(0.0, (t - at) / max(el.get("life") or 1, 1e-3))), 0)  # drag curves too
            if dg: vel[live] *= np.exp(-dg * 0.693 * dt)  # born particles only: the player clones vel0 at birth
            pos += live[:, None] * vel * dt
            if floor:
                fy = floor.get("y", 0); low = pos[:, 1] < fy
                pos[low, 1] = fy; vel[low] *= [0.8, -floor.get("bounce", 0.4), 0.8]
        alive = (t >= born) & (t - born <= life)
        out[T] = pos[alive].copy()
    return out


def main(argv):
    if not argv:
        print(json.dumps({"schema": 1, "status": "fail", "summary": "swarm: needs a preset", "next_action": "lune run kit vfx swarm <preset> [--layers <prefix>] [--at 0.5,1]"}))
        return 1
    name = argv[0]
    prefix = argv[argv.index("--layers") + 1] if "--layers" in argv else ""
    # the EXPANDED preset (kit vfx expand): swarms inside parts count, beats are times, points are resolved below
    import subprocess
    r = subprocess.run(["lune", "run", "kit", "vfx", "expand", name], capture_output=True, text=True, encoding="utf-8", shell=os.name == "nt")
    txt = r.stdout[r.stdout.find("{"):]
    try:
        preset = json.loads(txt[:txt.rfind("}") + 1])
    except ValueError as e:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"swarm: cannot expand {name}: {e}", "next_action": f"lune run kit vfx expand {name}"}))
        return 1
    pts = preset.get("points") or {}
    def pt(v):  # a point name -> its coordinates; missing -> the origin (the player's default)
        v = pts.get(v, v) if isinstance(v, str) else v
        return v if isinstance(v, list) and len(v) == 3 else [0, 0, 0]
    for l in preset.get("layers", []):
        if l.get("kind") == "swarm":
            l["point"] = pt(l.get("point"))
            if isinstance(l.get("attract"), dict):
                l["attract"]["point"] = pt(l["attract"].get("point", l["point"]))
    layers = [l for l in preset.get("layers", []) if l.get("kind") == "swarm" and l.get("name", "").startswith(prefix)]
    if not layers:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"swarm: no swarm layers in {name} (prefix '{prefix}')", "next_action": "name the layers' prefix"}))
        return 1
    if "--at" in argv:
        times = [float(x) for x in argv[argv.index("--at") + 1].split(",")]
    else:
        lo = min(l.get("at", 0) for l in layers)
        hi = max(l.get("at", 0) + max(l.get("lifetime", [1, 1]) if isinstance(l.get("lifetime"), list) else [l.get("lifetime", 1)]) for l in layers)
        times = [round(lo + (hi - lo) * f, 2) for f in (0.2, 0.4, 0.6, 0.8)]
    res = [run(el, times, np.random.default_rng(i + 1)) for i, el in enumerate(layers)]
    rows = []
    for T in times:
        P = [r[T] for r in res if len(r[T])]
        if not P:
            rows.append({"t": T, "n": 0})
            continue
        P = np.concatenate(P)
        c, s = P.mean(0), P.std(0)
        rows.append({"t": T, "n": int(len(P)), "centre": np.round(c, 1).tolist(), "spread": np.round(s, 1).tolist(),
                     "y_band": np.round(np.percentile(P[:, 1], [5, 95]), 1).tolist(),
                     "reads": "tall (a fountain / column)" if s[1] > 1.2 * max(s[0], s[2]) else "wide (a mass / flock)" if max(s[0], s[2]) > 1.5 * s[1] else "round"})
    if "--sheet" in argv:
        from PIL import Image, ImageDraw
        W = 300
        img = Image.new("RGB", (W * len(times), W * 2), (24, 20, 30))
        dr = ImageDraw.Draw(img)
        for li, el in enumerate(layers):
            for ti, T in enumerate(times):
                for row, (a, b) in enumerate(((0, 1), (0, 2))):
                    for p in res[li][T]:
                        x = ti * W + W / 2 + p[a] * 8
                        y = row * W + (W - 20 - p[b] * 8 if row == 0 else W / 2 + p[b] * 8)
                        dr.point((x, y), fill=(255, 190, 120) if el.get("material", "Neon") == "Neon" else (120, 120, 130))
        for ti, T in enumerate(times):
            dr.text((ti * W + 4, 4), f"t={T} side (x-y)", fill=(255, 255, 255))
            dr.text((ti * W + 4, W + 4), "top (x-z)", fill=(255, 255, 255))
        os.makedirs(os.path.join("build", "vfx", "swarm"), exist_ok=True)
        img.save(os.path.join("build", "vfx", "swarm", f"{name}.png"))
    line = "; ".join(f"t={r['t']}: " + (f"{r['reads']}, centre y {r['centre'][1]}, spread {r['spread']}" if r["n"] else "none alive") for r in rows)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"swarm {name} ({len(layers)} layers): {line}",
                      "next_action": "tune attract / swirl / drag / curl until the mass reads as the brief says, then record", "rows": rows}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
