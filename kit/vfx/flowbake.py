"""flowbake.py - BAKED FLOW (board/plans/archive/aaa-vfx-research.md): pros scroll textures along a flow map in a shader; Roblox has
no custom shaders, so the flow is baked INTO a looping flipbook. A still texture is advected along a flow field (a curl
swirl, a straight wind, a vortex, an outward burst) with the standard two-phase flow-map trick (two copies half a cycle
apart, cross-faded by a triangle wave): the loop has no pop at its seam.

    python kit/vfx/flowbake.py <out> --from <texture key> [--flow swirl|wind|vortex|burst] [--strength 24]
                               [--frames 16] [--cell 256]

  --from      a built texture (build/textures/<key>.png; its first cell if it is a sheet)
  --flow      swirl  = curl of periodic noise (liquid, smoke, plasma)        wind  = straight +U with turbulence
              vortex = round the centre (portals, whirlpools, tornado tops)  burst = outward from the centre (shock, heat)
  --strength  the farthest a pixel travels in one cycle, px of the cell
Writes _downloads/kit_generated/textures/<out>.png (a 4x4 / 8x8 sheet) + assets/textures/<out>.json (play it as a Loop
flipbook); prints one JSON line {status, summary, next_action, loop_seam}.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image

OUT = os.path.join("_downloads", "kit_generated", "textures")
SPECS = os.path.join("assets", "textures")


def periodic_field(n, beta, seed):
    rng = np.random.default_rng(seed)
    f = np.sqrt(np.fft.fftfreq(n)[:, None] ** 2 + np.fft.fftfreq(n)[None, :] ** 2)
    f[0, 0] = 1
    amp = 1 / f ** beta
    amp[0, 0] = 0
    v = np.real(np.fft.ifft2((rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))) * amp))
    return (v - v.mean()) / max(v.std(), 1e-9)


def flow_field(kind, n, seed=7):
    """unit-ish (vx, vy) per pixel"""
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    cx = cy = (n - 1) / 2
    dx, dy = xx - cx, yy - cy
    r = np.sqrt(dx * dx + dy * dy) + 1e-6
    if kind == "swirl":
        psi = periodic_field(n, 2.6, seed)
        vx = np.roll(psi, -1, 0) - np.roll(psi, 1, 0)
        vy = -(np.roll(psi, -1, 1) - np.roll(psi, 1, 1))
    elif kind == "wind":
        t = periodic_field(n, 2.2, seed)
        vx = np.ones_like(xx) + 0.35 * t
        vy = 0.35 * periodic_field(n, 2.2, seed + 1)
    elif kind == "vortex":
        fall = np.clip(r / (n * 0.5), 0.15, 1)
        vx, vy = -dy / r / fall, dx / r / fall
    elif kind == "burst":
        vx, vy = dx / r, dy / r
    else:
        raise SystemExit(json.dumps({"status": "fail", "summary": f"flowbake: unknown flow {kind}", "next_action": "--flow swirl|wind|vortex|burst"}))
    m = max(np.abs(vx).max(), np.abs(vy).max(), 1e-9)
    return vx / m, vy / m


def sample(img, x, y, wrap):
    n_y, n_x = img.shape[:2]
    if wrap:
        x, y = x % n_x, y % n_y
    else:
        x, y = np.clip(x, 0, n_x - 1.001), np.clip(y, 0, n_y - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    x1, y1 = (x0 + 1) % n_x if wrap else np.minimum(x0 + 1, n_x - 1), (y0 + 1) % n_y if wrap else np.minimum(y0 + 1, n_y - 1)
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy) + img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy)


def main(argv):
    if not argv or argv[0].startswith("--") or "--from" not in argv:
        print(json.dumps({"status": "fail", "summary": "flowbake: needs <out> --from <texture>", "next_action": "python kit/vfx/flowbake.py <out> --from <key> [--flow swirl]"}))
        return 1
    out = argv[0]
    opt = lambda k, d: argv[argv.index(k) + 1] if k in argv else d  # noqa: E731
    src_key = opt("--from", "")
    kind = opt("--flow", "swirl")
    strength = float(opt("--strength", 24))
    frames = int(opt("--frames", 16))
    cell = int(opt("--cell", 256))
    grid = int(round(math.sqrt(frames)))
    if grid * grid != frames or grid not in (2, 4, 8) or cell * grid > 1024:
        print(json.dumps({"status": "fail", "summary": f"flowbake: {frames} frames x {cell} px does not make a 2x2 / 4x4 / 8x8 sheet <= 1024", "next_action": "--frames 16 --cell 256, or --frames 64 --cell 128"}))
        return 1
    path = os.path.join("build", "textures", f"{src_key}.png")
    if not os.path.isfile(path):
        print(json.dumps({"status": "fail", "summary": f"flowbake: no {path}", "next_action": "lune run kit vfx (build the source texture first)"}))
        return 1
    src = Image.open(path).convert("RGBA")
    spec_path = os.path.join(SPECS, f"{src_key}.json")
    sgrid = 1
    if os.path.isfile(spec_path):
        g = json.load(open(spec_path, encoding="utf-8")).get("grid", 1)
        sgrid = g if isinstance(g, int) else 1
    if sgrid > 1:
        src = src.crop((0, 0, src.width // sgrid, src.height // sgrid))
    src = np.asarray(src.resize((cell, cell), Image.LANCZOS), dtype=np.float64) / 255.0
    # tileable sources (masks, scrolling skins) wrap; a sprite with a clear border clamps
    wrap = kind in ("swirl", "wind") and src[0, :, 3].mean() > 0.02 and src[:, 0, 3].mean() > 0.02
    vx, vy = flow_field(kind, cell)
    yy, xx = np.mgrid[0:cell, 0:cell].astype(np.float64)
    sheet = np.zeros((cell * grid, cell * grid, 4))
    for i in range(frames):
        ph = i / frames
        pa, pb = ph % 1.0, (ph + 0.5) % 1.0
        wa = 1 - abs(2 * pa - 1)  # the triangle weights: each copy is invisible at the moment it resets
        a = sample(src, xx - vx * strength * pa, yy - vy * strength * pa, wrap)
        b = sample(src, xx - vx * strength * pb, yy - vy * strength * pb, wrap)
        f = a * wa + b * (1 - wa)
        r, c = divmod(i, grid)
        sheet[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell] = f
    # the loop seam: last frame -> first frame vs an ordinary frame step
    def cell_of(k):
        r, c = divmod(k, grid)
        return sheet[r * cell:(r + 1) * cell, c * cell:(c + 1) * cell]
    step = np.mean(np.abs(cell_of(1) - cell_of(0)))
    seam = float(np.mean(np.abs(cell_of(0) - cell_of(frames - 1))) / max(step, 1e-9))
    os.makedirs(OUT, exist_ok=True)
    png = os.path.join(OUT, f"{out}.png")
    Image.fromarray((np.clip(sheet, 0, 1) * 255).astype(np.uint8), "RGBA").save(png)
    spec = {"engine": "fx", "recipe": "import", "about": f"{src_key} baked along a {kind} flow (kit/vfx/flowbake.py: two-phase flow map, loops): play as a Loop flipbook",
            "pack": "kit generated (baked flow)", "source": png.replace(os.sep, "/"), "frames": frames, "grid": grid, "cell": cell,
            "premultiply": False, "post": {"alpha": "coverage", "tonemap": False, "border": 0 if wrap else 0.03}}
    os.makedirs(SPECS, exist_ok=True)
    with open(os.path.join(SPECS, f"{out}.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(spec, fh, indent=1)
    ok = seam <= 1.5
    print(json.dumps({"status": "pass" if ok else "fail", "summary": f"flowbake: {out} = {src_key} along {kind}, {frames} frames ({grid}x{grid}), loop seam {seam:.2f}x a frame step",
                      "next_action": f"lune run kit vfx (registers it), play with flipbook {{layout: {grid}x{grid}, mode: Loop}}" if ok else "the loop pops: raise --frames or lower --strength",
                      "loop_seam": round(seam, 2)}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
