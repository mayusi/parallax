"""textures.py — procedural particle textures + flipbooks for Roblox VFX, with a texture gate.

Usage: python kit/vfx/textures.py [--specs DIR] [--out DIR] [name ...|all] | --check <png ...>   (normally: lune run kit vfx)
Specs: assets/textures/<name>.json -> build/textures/<name>.png
  {"kind": "glow|spark|ring|star|dust|smoke|fire", "size": 256, "grid": 1|2|4|8, "seed": 1, "softness": 0.5}
Textures are WHITE/grayscale with alpha: the preset's color sequence tints them in Roblox.
Flipbooks (grid > 1) keep a transparent border around every cell so mipmaps don't bleed between frames.
Gate: square, power of two, <= 1024, RGBA, not empty, not fully opaque, cell borders transparent.
Prints one JSON line: {status, summary, next_action, textures:[{name, file, checks}]}.
"""

import json
import os
import sys

import numpy as np
from PIL import Image

SPECS = os.path.join("assets", "textures")  # project texture specs (kit passes --specs)
OUT = os.path.join("build", "textures")
KINDS = ("glow", "spark", "ring", "star", "dust", "smoke", "fire")


# ------------------------------------------------------------------ noise
def value_noise(n, cells, rng, octaves=4):
    out = np.zeros((n, n))
    amp, total = 1.0, 0.0
    for o in range(octaves):
        c = cells * (2**o)
        grid = rng.random((c + 1, c + 1))
        grid[-1, :] = grid[0, :]
        grid[:, -1] = grid[:, 0]
        xs = np.linspace(0, c, n, endpoint=False)
        i = xs.astype(int)
        f = xs - i
        f = f * f * (3 - 2 * f)
        a = grid[np.ix_(i, i)]
        b = grid[np.ix_(i, i + 1)]
        cc = grid[np.ix_(i + 1, i)]
        d = grid[np.ix_(i + 1, i + 1)]
        fx, fy = f[None, :], f[:, None]
        out += amp * (a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + cc * (1 - fx) * fy + d * fx * fy)
        total += amp
        amp *= 0.5
    return out / total


def radial(n):
    y, x = np.mgrid[0:n, 0:n]
    c = (n - 1) / 2
    return np.sqrt((x - c) ** 2 + (y - c) ** 2) / c, np.arctan2(y - c, x - c)


# ------------------------------------------------------------------ single-frame kinds (alpha in 0..1)
def frame(kind, n, rng, t, softness):
    r, ang = radial(n)
    if kind == "glow":
        return np.clip(1 - r, 0, 1) ** (1.5 + 3 * softness)
    if kind == "spark":
        y, x = np.mgrid[0:n, 0:n] / (n - 1) * 2 - 1
        core = np.exp(-(x / 0.08) ** 2) * np.clip(1 - np.abs(y) ** (1.2 + softness), 0, 1)
        return np.clip(core, 0, 1)
    if kind == "ring":
        width = 0.06 + 0.1 * softness
        return np.clip(np.exp(-((r - 0.8) / width) ** 2) * (r < 0.98), 0, 1)
    if kind == "star":
        rays = np.abs(np.cos(ang * 2)) ** 18 + np.abs(np.sin(ang * 2)) ** 18 * 0.6
        return np.clip((rays * np.clip(1 - r, 0, 1) ** 2 + np.clip(1 - r * 2.2, 0, 1)), 0, 1)
    if kind == "dust":
        noise = value_noise(n, 4, rng)
        return np.clip(np.clip(1 - r, 0, 1) ** 1.5 * (0.4 + noise), 0, 1) * (r < 0.97)
    if kind in ("smoke", "fire"):
        # t: 0 -> 1 across the flipbook. Puff grows, noise drifts, edges erode.
        noise = np.roll(value_noise(n, 3, rng, octaves=5), -int(t * n * 0.2), axis=0)  # drifts upward over time
        # billowy silhouette: the radius is pushed in/out by noise, with a soft edge band
        band = 0.18 + 0.2 * softness
        if kind == "smoke":
            grow = 0.6 + 0.3 * t
            rr = r + (noise - 0.5) * 0.45
            shape = np.clip((grow - rr) / band, 0, 1)
            body = 0.55 + 0.45 * noise
            erode = np.clip((noise - 0.75 * t) / 0.35 + 0.4, 0, 1)  # late frames break apart
            return np.clip(shape * body * erode * (1 - 0.35 * t), 0, 1) * (r < 0.97)
        y = np.mgrid[0:n, 0:n][0] / (n - 1)  # 0 = top row
        rr = r + (noise - 0.5) * 0.5 + np.clip(0.55 - y, 0, 1) * 0.6  # flame narrows toward the top
        grow = 0.75 - 0.25 * t
        shape = np.clip((grow - rr) / band, 0, 1)
        core = 0.65 + 0.35 * noise
        erode = np.clip((noise - 0.8 * t) / 0.3 + 0.5, 0, 1)
        return np.clip(shape * core * erode, 0, 1) * (r < 0.97)
    raise ValueError(f'unknown kind "{kind}" ({"|".join(KINDS)})')


def build(spec):
    kind = spec["kind"]
    size = int(spec.get("size", 256))
    grid = int(spec.get("grid", 1))
    softness = float(spec.get("softness", 0.5))
    rng = np.random.default_rng(int(spec.get("seed", 1)))
    cell = size // grid
    pad = max(2, cell // 32)
    alpha = np.zeros((size, size))
    frames = grid * grid
    for k in range(frames):
        t = k / max(1, frames - 1)
        inner = cell - 2 * pad
        # animated kinds reuse ONE noise field (same seed every frame) so frames evolve instead of flickering
        frame_rng = np.random.default_rng(int(spec.get("seed", 1))) if kind in ("smoke", "fire") else rng
        a = frame(kind, inner, frame_rng, t, softness)
        row, col = divmod(k, grid)
        y0, x0 = row * cell + pad, col * cell + pad
        alpha[y0 : y0 + inner, x0 : x0 + inner] = a
    rgba = np.zeros((size, size, 4), dtype=np.uint8)
    rgba[..., :3] = 255
    rgba[..., 3] = np.clip(np.nan_to_num(alpha) * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA"), grid


# ------------------------------------------------------------------ gate
def check(path, grid=1):
    checks = []

    def add(name, ok, value, limit, fix, severity="error"):
        checks.append({"name": name, "ok": bool(ok), "severity": severity, "value": value, "limit": limit, "fix": "" if ok else fix})

    img = Image.open(path)
    w, h = img.size
    add("square", w == h, [w, h], "w == h", "particle textures must be square")
    add("pow2", w > 0 and (w & (w - 1)) == 0, w, "power of two", "use 128/256/512/1024")
    add("max_size", w <= 1024, w, 1024, "Roblox downscales above 1024 — use size <= 1024")
    add("rgba", img.mode == "RGBA", img.mode, "RGBA", "export with an alpha channel")
    if img.mode != "RGBA":
        return checks
    a = np.asarray(img)[..., 3].astype(np.float64) / 255
    add("not_empty", a.max() > 0.2, round(float(a.max()), 3), "> 0.2", "alpha is (nearly) empty — raise density/softness")
    add("not_opaque", a.mean() < 0.8, round(float(a.mean()), 3), "< 0.8", "texture is a solid block — particles need soft alpha edges")
    cell = w // grid
    border = []
    for row in range(grid):
        for col in range(grid):
            c = a[row * cell : (row + 1) * cell, col * cell : (col + 1) * cell]
            border.append(max(c[0, :].max(), c[-1, :].max(), c[:, 0].max(), c[:, -1].max()))
    worst = round(float(max(border)), 3)
    add("cell_border", worst < 0.02, worst, "< 0.02", "frames touch the cell edge — shrink the shape or add padding (mip bleed)")
    return checks


def main(names, only_check, specs=SPECS, out=OUT):
    os.makedirs(out, exist_ok=True)
    results, errors = [], []
    if only_check:
        for path in only_check:
            cs = check(path, 1)
            results.append({"name": os.path.basename(path), "file": path, "checks": cs})
    else:
        if names == ["all"]:
            names = sorted(f[:-5] for f in os.listdir(specs) if f.endswith(".json"))
        for name in names:
            try:
                with open(os.path.join(specs, f"{name}.json"), encoding="utf-8") as fh:
                    spec = json.load(fh)
                path = os.path.join(out, f"{name}.png")
                if spec.get("engine") == "fx":  # rendered by kit/vfx/fxlab.py + gated by kit/vfx/fxfinish.py
                    continue
                if spec.get("engine") == "blender":  # rendered by kit/vfx/flipbook.py (Blender step): only gate it
                    if not os.path.isfile(path):
                        errors.append(f"{name}: not rendered yet — run: lune run kit vfx (renders Blender flipbooks first)")
                        continue
                    grid = int(spec.get("grid", 4))
                    results.append({"name": name, "file": os.path.relpath(path).replace("\\", "/"), "grid": grid, "checks": check(path, grid)})
                    continue
                img, grid = build(spec)
                img.save(path)
                results.append({"name": name, "file": os.path.relpath(path).replace("\\", "/"), "grid": grid, "checks": check(path, grid)})
            except FileNotFoundError:
                errors.append(f"{name}: no spec at {specs}/{name}.json")
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                errors.append(f"{name}: {type(exc).__name__}: {exc}")
    for r in results:
        for c in r["checks"]:
            if not c["ok"] and c["severity"] == "error":
                errors.append(f"{r['name']}: {c['name']}={c['value']} — {c['fix']}")
    status = "fail" if errors else "pass"
    print(
        json.dumps(
            {
                "schema": 1,
                "status": status,
                "summary": "; ".join(errors) if errors else f"{len(results)} texture(s) pass: " + ", ".join(r["name"] for r in results),
                "next_action": errors[0] if errors else "none — upload build/textures/*.png, then: lune run kit asset-id <file> <rbxassetid>",
                "textures": results,
            }
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--check":
        sys.exit(main([], args[1:]))
    opts = {"--specs": SPECS, "--out": OUT}
    while args and args[0] in opts:
        opts[args[0]], args = args[1], args[2:]
    sys.exit(main(args or ["all"], None, opts["--specs"], opts["--out"]))
