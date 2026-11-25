"""meshseq.py - MESH SEQUENCES (board/plans/archive/aaa-vfx-research.md: pros bake simulations to vertex-animation textures; Roblox
has no vertex shaders, so the frames ride an EditableMesh): a surface that MOVES in 3D, baked frame by frame on a FIXED
grid (cols x rows, the same topology every frame), replayed by the `seq` mesh shape (VfxMesh / the player) at `fps`.

    python kit/vfx/meshseq.py <name> --recipe billow|crown [--frames 32] [--cols 24] [--rows 12] [--seed 1]

  billow  a cloud puff that GROWS and BOILS: a sphere pushed out by ridged 3D noise (cauliflower lobes) whose pattern
          drifts and swirls (curl advection) as it rises and flattens underneath - a hero smoke / explosion mass
  crown   a splash / dust CROWN: a tube that rises from the ground, its rim tearing into spikes and curling outward,
          then collapsing back - impacts on water or sand
Writes assets/effects/seq/<name>.json { about, recipe, args, cols, rows, frames: [[x, y, z, ...] per frame] } (unit
size: the layer's scale sizes it; synced into the game as VfxPresets.seq.<name>); prints one JSON line.
"""
import json
import math
import os
import sys

import numpy as np

OUT = os.path.join("assets", "effects", "seq")


def hash3(i, j, k, seed):
    x = np.sin(i * 127.1 + j * 311.7 + k * 74.7 + seed * 19.19) * 43758.5453
    return x - np.floor(x)


def noise3(x, y, z, seed=0.0):
    i, j, k = np.floor(x), np.floor(y), np.floor(z)
    fx, fy, fz = x - i, y - j, z - k
    ux, uy, uz = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy), fz * fz * (3 - 2 * fz)
    L = lambda a, b, t: a + (b - a) * t  # noqa: E731
    x00 = L(hash3(i, j, k, seed), hash3(i + 1, j, k, seed), ux)
    x10 = L(hash3(i, j + 1, k, seed), hash3(i + 1, j + 1, k, seed), ux)
    x01 = L(hash3(i, j, k + 1, seed), hash3(i + 1, j, k + 1, seed), ux)
    x11 = L(hash3(i, j + 1, k + 1, seed), hash3(i + 1, j + 1, k + 1, seed), ux)
    return L(L(x00, x10, uy), L(x01, x11, uy), uz) * 2 - 1


def billowy(x, y, z, seed, octaves=4):
    """cauliflower: summed RIDGED noise (1 - |n|), each octave smaller lobes on the bigger ones"""
    total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
    for o in range(octaves):
        n = noise3(x * freq, y * freq, z * freq, seed + o * 7.3)
        total = total + (1 - np.abs(n)) * amp
        norm += amp
        amp *= 0.5
        freq *= 2.1
    return total / norm


def curl(x, y, z, seed):
    e = 0.05
    def psi(px, py, pz):
        return (noise3(px, py, pz, seed), noise3(px + 31.4, py + 7.1, pz + 2.9, seed), noise3(px + 11.3, py + 53.7, pz + 17.2, seed))
    dx1, dx0 = psi(x + e, y, z), psi(x - e, y, z)
    dy1, dy0 = psi(x, y + e, z), psi(x, y - e, z)
    dz1, dz0 = psi(x, y, z + e), psi(x, y, z - e)
    k = 1 / (2 * e)
    return ((dy1[2] - dy0[2]) - (dz1[1] - dz0[1])) * k, ((dz1[0] - dz0[0]) - (dx1[2] - dx0[2])) * k, ((dx1[1] - dx0[1]) - (dy1[0] - dy0[0])) * k


def ease_out(t, p=3):
    return 1 - (1 - t) ** p


def billow(frames, cols, rows, seed):
    u = np.linspace(0, 1, cols + 1)[None, :]
    v = np.linspace(0, 1, rows + 1)[:, None]
    th, ph = u * 2 * math.pi, v * math.pi  # v = 0 bottom pole .. 1 top pole
    dx, dy, dz = np.sin(ph) * np.cos(th), -np.cos(ph), np.sin(ph) * np.sin(th)
    dx, dz = np.broadcast_to(dx, (rows + 1, cols + 1)), np.broadcast_to(dz, (rows + 1, cols + 1))
    dy = np.broadcast_to(dy, (rows + 1, cols + 1))
    out = []
    for f in range(frames):
        t = f / max(frames - 1, 1)
        grow = 0.35 + 0.65 * ease_out(t)
        drift = t * 1.6
        # the swirl: the noise is sampled at points carried round a curl field (the pattern rolls, not just scrolls)
        cx, cy, cz = curl(dx * 1.2, dy * 1.2 + drift, dz * 1.2, seed + 3)
        sx, sy, sz = dx * 1.8 + cx * 0.25 * t, dy * 1.8 + cy * 0.25 * t - drift, dz * 1.8 + cz * 0.25 * t
        lobes = billowy(sx, sy, sz, seed)
        amp = 0.18 + 0.32 * t  # the boil deepens as it grows
        r = grow * (1 + amp * (lobes - 0.55))
        # rising and flattening underneath (a cloud sits on its own flat base); a slight wider top (the mushroom start)
        y = dy * r * (np.where(dy < 0, 0.55, 1.0)) + 0.45 * ease_out(t, 2)
        widen = 1 + 0.12 * t * np.clip(dy, 0, 1)
        out.append(np.stack([dx * r * widen, y, dz * r * widen], -1))
    return out


def crown(frames, cols, rows, seed):
    u = np.linspace(0, 1, cols + 1)[None, :]
    v = np.linspace(0, 1, rows + 1)[:, None]
    th = u * 2 * math.pi
    rng = np.random.default_rng(int(seed))
    n_spikes = 11
    phase = rng.uniform(0, 2 * math.pi)
    jitter = noise3(np.cos(th) * 2, np.sin(th) * 2, np.zeros_like(th), seed)
    out = []
    for f in range(frames):
        t = f / max(frames - 1, 1)
        rise = math.sin(math.pi * min(t / 0.85, 1)) ** 0.8  # up, then down
        R = 0.35 + 0.65 * ease_out(t)
        H = 0.9 * rise
        spike = np.maximum(0, np.sin(n_spikes * th + phase + jitter * 2)) ** 3 * (0.6 + 0.4 * jitter)
        h = H * (v + v ** 3 * spike * 0.9)
        lip = 0.35 * rise * v ** 2.2 * (1 + 0.5 * spike)  # the rim curls outward
        r = R * (1 - 0.18 * v) + lip
        wob = 0.05 * noise3(np.cos(th) * 3, v * 3 + t * 2, np.sin(th) * 3, seed + 1)
        r = r + wob
        out.append(np.stack([np.cos(th) * r * np.ones_like(v), h * np.ones_like(th), np.sin(th) * r * np.ones_like(v)], -1))
    return out


RECIPES = {"billow": billow, "crown": crown}


def main(argv):
    if not argv or argv[0].startswith("--"):
        print(json.dumps({"status": "fail", "summary": "meshseq: name the sequence", "next_action": "python kit/vfx/meshseq.py <name> --recipe billow|crown"}))
        return 1
    name = argv[0]
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    recipe = opt("--recipe", "billow")
    frames, cols, rows, seed = int(opt("--frames", 32)), int(opt("--cols", 24)), int(opt("--rows", 12)), float(opt("--seed", 1))
    if recipe not in RECIPES:
        print(json.dumps({"status": "fail", "summary": f"meshseq: unknown recipe {recipe}", "next_action": f"--recipe {' | '.join(RECIPES)}"}))
        return 1
    if not (2 <= frames <= 64 and 4 <= cols <= 48 and 2 <= rows <= 24):
        print(json.dumps({"status": "fail", "summary": "meshseq: frames 2-64, cols 4-48, rows 2-24 (the data rides into the game)", "next_action": "smaller grid / fewer frames"}))
        return 1
    seq = RECIPES[recipe](frames, cols, rows, seed)
    flat = [[round(float(x), 3) for x in fr.reshape(-1)] for fr in seq]
    nverts = (cols + 1) * (rows + 1)
    # the motion check: a sequence whose frames barely differ is a bug (a frozen bake)
    step = float(np.mean([np.abs(seq[i + 1] - seq[i]).mean() for i in range(len(seq) - 1)]))
    os.makedirs(OUT, exist_ok=True)
    data = {"about": f"{recipe} mesh sequence (kit/vfx/meshseq.py {name} --recipe {recipe} --frames {frames} --cols {cols} --rows {rows} --seed {seed:g})",
            "recipe": recipe, "args": {"frames": frames, "cols": cols, "rows": rows, "seed": seed}, "cols": cols, "rows": rows, "frames": flat}
    path = os.path.join(OUT, f"{name}.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, separators=(",", ":"))
    kb = os.path.getsize(path) / 1024
    ok = step > 1e-3 and kb < 600
    print(json.dumps({"status": "pass" if ok else "fail",
                      "summary": f"meshseq: {path} - {recipe}, {frames} frames x {nverts} vertices, mean move {step:.3f} a frame, {kb:.0f} KB",
                      "next_action": f'a mesh layer: "shape": "seq", "params": {{"seq": "{name}", "fps": 24}}' if ok else "the frames do not move or the data is too big",
                      "vertices": nverts, "kb": round(kb)}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
