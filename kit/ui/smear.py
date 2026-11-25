"""smear.py — a SMEAR treatment of a real picture (graphic design / animation smear frames): the cut-out figure's own
pixels dragged along a direction in bands of different lengths (a pixel-sort streak, not a blur), the trail cooling
toward a tint the further it runs, echo copies of the figure trailing behind (the animator's smear frame), a few hard
speed lines, and the sharp figure on top. Writes a UI piece (+ .smear.json: the recipe and the source).

    python kit/ui/smear.py <identity>/<piece> --from <picture> [--angle 200] [--length 520] [--decay 0.55]
        [--bands 3,9] [--tint #a66cff] [--tint-k 0.85] [--echoes 3] [--echo-gap 70] [--lines 9] [--size 1400]
        [--seed 7] [--art assets/ui/art]

--angle: where the trail RUNS, in degrees (0 = right, 90 = down, 180 = left; the figure moves the other way).
--length: the longest trail in output px; each band of rows draws its own length (--bands = min,max band height px).
--decay: how much of the trail's alpha is left at its far end (0..1).
A picture with an opaque background is cut out first (kit vision cutout).
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def hex_rgb(s):
    s = s.lstrip("#")
    return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def has_transparent_border(im):
    if im.mode != "RGBA":
        return False
    a = np.array(im.getchannel("A"))
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    return (edge < 16).mean() > 0.9


def streak(rgba, length, decay, bands, tint, tint_k, rng):
    """the trail to the LEFT of every opaque pixel: each band of rows drags its own length; colour cools to tint"""
    h, w, _ = rgba.shape
    A = rgba[:, :, 3] / 255.0
    P = rgba[:, :, :3] * A[:, :, None]          # premultiplied
    SA, SP = A.copy(), P.copy()
    D = np.zeros_like(A)                        # how far each trail pixel is from its source
    # per-row reach: bands of random height, each its own length (a few long ones, most medium, some short)
    reach = np.zeros(h, dtype=np.float32)
    y = 0
    while y < h:
        bh = rng.randint(bands[0], bands[1])
        r = rng.random()
        f = 1.0 if r < 0.18 else (rng.uniform(0.45, 0.8) if r < 0.75 else rng.uniform(0.12, 0.35))
        reach[y:y + bh] = length * f
        y += bh
    tau = length / max(1e-3, -math.log(max(1e-3, decay)))
    s = 1
    while s <= length:
        w_ = math.exp(-s / tau)
        shA = np.zeros_like(SA)
        shP = np.zeros_like(SP)
        shD = np.zeros_like(D)
        shA[:, :-s] = SA[:, s:] * w_
        shP[:, :-s] = SP[:, s:] * w_
        shD[:, :-s] = D[:, s:] + s
        ok = (shD <= reach[:, None]) & (shA > SA)
        SA = np.where(ok, shA, SA)
        SP = np.where(ok[:, :, None], shP, SP)
        D = np.where(ok, shD, D)
        s *= 2
    col = SP / np.maximum(SA[:, :, None], 1e-4)
    k = np.clip(D / max(length, 1), 0, 1)[:, :, None] * tint_k
    col = col * (1 - k) + tint[None, None, :] * k
    # a lift along the trail: the streak glows a little where it leaves the body
    col = np.clip(col * (1 + 0.25 * (1 - k)), 0, 255)
    trail = (D > 0)
    out = np.zeros_like(rgba)
    out[:, :, :3] = col
    out[:, :, 3] = np.where(trail, SA * 255 * 0.92, 0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--angle", type=float, default=200)
    ap.add_argument("--length", type=int, default=520)
    ap.add_argument("--decay", type=float, default=0.55)
    ap.add_argument("--bands", default="3,9")
    ap.add_argument("--tint", default="#a66cff")
    ap.add_argument("--tint-k", type=float, default=0.7)
    ap.add_argument("--pad", type=int, default=None, help="the canvas margin (default: from the length); a FLIPBOOK of smears shares one pad")
    ap.add_argument("--no-crop", action="store_true", help="keep the whole canvas (flipbook frames stay aligned)")
    ap.add_argument("--split", action="store_true", help="also write <piece>_figure.png: the sharp figure alone on the same canvas (to break a frame)")
    ap.add_argument("--echoes", type=int, default=3)
    ap.add_argument("--echo-gap", type=int, default=70)
    ap.add_argument("--echo-tint", default=None, help="default: --tint")
    ap.add_argument("--lines", type=int, default=9, help="hard speed lines through the trail")
    ap.add_argument("--line-color", default="#f5f0ff")
    ap.add_argument("--size", type=int, default=1400, help="the figure's longest side")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--art", default="assets/ui/art")
    a = ap.parse_args()
    if "/" not in a.target:
        return emit("fail", "smear: name the piece as <identity>/<name>", "lune run kit ui smear witch/witch_smear --from <picture>")
    ident, piece = a.target.split("/", 1)
    if not os.path.isfile(a.src):
        return emit("fail", f"smear: no picture at {a.src}", "point --from at a real picture")
    t0 = time.time()
    rng = random.Random(a.seed)
    im = Image.open(a.src).convert("RGBA")
    cut = False
    if not has_transparent_border(im):
        work = os.path.join(ROOT, "build", "vision", "smear")
        os.makedirs(work, exist_ok=True)
        src_png = os.path.join(work, f"{ident}_{piece}_src.png")
        im.save(src_png)
        out = os.path.join(work, f"{ident}_{piece}_cut.png")
        r = subprocess.run(["lune", "run", "kit", "vision", "cutout", src_png, "--rgba", "-o", out], capture_output=True, text=True, cwd=ROOT)
        rgba_path = out[:-4] + "_rgba.png"
        if not os.path.isfile(rgba_path):
            return emit("fail", f"smear: the cutout failed: {(r.stdout + r.stderr)[-300:]}", "lune run kit vision setup birefnet")
        im = Image.open(rgba_path).convert("RGBA")
        cut = True
    bb = im.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    im = im.crop(bb)
    k = a.size / max(im.size)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    # a canvas with room for the trail on every side, turned so the trail runs to the LEFT
    pad = a.pad if a.pad is not None else a.length + a.echoes * a.echo_gap + 40
    canvas = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    canvas.alpha_composite(im, (pad, pad))
    turn = 180 - a.angle  # rotate so the trail direction becomes 180 (left)
    rot = canvas.rotate(turn, resample=Image.BICUBIC, expand=False)
    fig = np.array(rot).astype(np.float32)
    lo, hi = (int(v) for v in a.bands.split(","))
    tint = hex_rgb(a.tint)
    trail = streak(fig, a.length, a.decay, (lo, hi), tint, a.tint_k, rng)
    layer = Image.fromarray(trail.astype(np.uint8), "RGBA")
    # echo copies: the figure repeated back along the trail, fading and cooling (the smear frame)
    etint = hex_rgb(a.echo_tint or a.tint)
    echoes = Image.new("RGBA", rot.size, (0, 0, 0, 0))
    for i in range(a.echoes, 0, -1):
        # each echo: the pose as a cooled silhouette with a bright rim — readable as its own frame over the trail
        e = fig.copy()
        alpha = e[:, :, 3] / 255.0
        e[:, :, :3] = e[:, :, :3] * 0.25 + etint * 0.75
        e[:, :, 3] = alpha * 255 * (0.72 - 0.16 * i)
        eim = Image.fromarray(np.clip(e, 0, 255).astype(np.uint8), "RGBA")
        rim_a = eim.getchannel("A").filter(ImageFilter.MaxFilter(5))
        rim = Image.new("RGBA", eim.size, tuple(int(v) for v in np.clip(etint * 0.4 + 160, 0, 255)) + (0,))
        rim.putalpha(rim_a.point(lambda v: int(v * 0.5)))
        rim.alpha_composite(eim)
        echoes.alpha_composite(rim, (-i * a.echo_gap, 0))
    # hard speed lines: thin, bright, starting inside the figure, running the length of the trail
    lines = Image.new("RGBA", rot.size, (0, 0, 0, 0))
    dl = ImageDraw.Draw(lines)
    alpha_rows = np.where(fig[:, :, 3].max(axis=1) > 128)[0]
    lc = tuple(int(v) for v in hex_rgb(a.line_color))
    for _ in range(a.lines if len(alpha_rows) else 0):
        y = int(rng.choice(alpha_rows))
        xs = np.where(fig[y, :, 3] > 128)[0]
        x1 = int(xs.min()) + rng.randint(0, max(1, (xs.max() - xs.min()) // 3))
        x0 = x1 - int(a.length * rng.uniform(0.5, 1.15))
        th = rng.choice([1, 1, 2, 3])
        dl.rectangle([x0, y, x1, y + th], fill=lc + (int(255 * rng.uniform(0.35, 0.8)),))
    lines = lines.filter(ImageFilter.GaussianBlur(0.6))
    out = Image.new("RGBA", rot.size, (0, 0, 0, 0))
    out.alpha_composite(layer)
    out.alpha_composite(echoes)
    out.alpha_composite(lines)
    out.alpha_composite(rot)
    out = out.rotate(-turn, resample=Image.BICUBIC, expand=False)
    figure_only = rot.rotate(-turn, resample=Image.BICUBIC, expand=False)
    bb = None if a.no_crop else out.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if bb:
        out = out.crop(bb)
        figure_only = figure_only.crop(bb)
    out_dir = os.path.join(a.art, ident)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{piece}.png")
    out.save(out_path)
    if a.split:
        figure_only.save(os.path.join(out_dir, f"{piece}_figure.png"))
    side = {"schema": 1, "kind": "smear", "from": a.src, "cutout": cut, "angle": a.angle, "length": a.length, "decay": a.decay,
            "bands": a.bands, "tint": a.tint, "tint_k": a.tint_k, "echoes": a.echoes, "echo_gap": a.echo_gap, "lines": a.lines,
            "split": a.split, "pad": a.pad, "no_crop": a.no_crop, "size": a.size, "seed": a.seed, "out": list(out.size),
            "about": f"a smear of {os.path.basename(a.src)}: its pixels dragged {a.length}px toward {a.angle} deg in bands, cooling to {a.tint}, {a.echoes} echo frames",
            "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(os.path.join(out_dir, f"{piece}.smear.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(side, fh, indent=1)
    return emit("pass", f"smear: {ident}/{piece}.png {out.width}x{out.height} from {os.path.basename(a.src)} ({'cut out, ' if cut else ''}trail {a.length}px at {a.angle} deg, {a.echoes} echoes; {time.time() - t0:.1f}s)",
                f"LOOK at {out_path} on the ground it will sit on; tune --length / --bands / --echoes / --tint", out=out_path)


if __name__ == "__main__":
    sys.exit(main())
