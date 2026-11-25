"""diffusionlight.py — DiffusionLight's chrome-ball maths, vendored for `kit vision light` (kit/gen/vision3.py).

Where it comes from (VETLOG.md, 2026-10-06):
  DiffusionLight/DiffusionLight-Turbo-diffusers @ ef7a372e54d5cfeeb47ae5900a5531dbc0628b56  inpaint.py: the ball's
      place and masks, the two prompts and their mix per exposure, the Turbo -> exposure LoRA switch at t = 800
  DiffusionLight/DiffusionLight @ 7130ec4  ball2envmap.py (ball -> equirectangular map), exposure2hdr.py (three
      exposures -> one HDR map), relighting/tonemapper.py (the preview's tone map)
Changed for the kit: numpy + torch only (skimage, ezexr, tqdm and multiprocessing dropped); one picture at a time; the
anti-aliased resize of the map is an exact box filter (the map is sampled at `scale` x its size); the LDR maps are
merged as floats (the original saved them as 8-bit PNGs first); EXR files are written with OpenEXR 3.

MIT License

Copyright (c) 2023, 2025 Pakkapon Phongthawee

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import numpy as np

SIZE = 1024  # SDXL's picture: the input is fitted into 1024 x 1024 (black padding), as the authors recommend
BALL = 256  # the ball, in the middle of the picture
DILATE = 20  # the inpainting mask is the ball + 10 px all round (a sharper rim)
EVS = (0.0, -2.5, -5.0)  # the exposures painted; the HDR map is merged from them
PROMPT = "a perfect mirrored reflective chrome ball sphere"
PROMPT_BLACK = "a perfect black dark mirrored reflective chrome ball sphere"
NEGATIVE = "matte, diffuse, flat, dull"
SWITCH_T = 800  # the Turbo LoRA until this timestep, then the exposure LoRA
EXPOSURE_LORA_SCALE = 0.75
CONTROL_SCALE = 0.5
STEPS = 30  # UniPC
SEED = 200  # the authors' seed: DiffusionLight is sensitive to it, and it must be the same for every exposure
GAMMA = 2.4


def fit_square(rgb):
    """an (H, W, 3) uint8 picture -> (SIZE, SIZE, 3) with its longer side SIZE, centred on black; + the content box"""
    from PIL import Image  # noqa: PLC0415

    h, w = rgb.shape[:2]
    k = SIZE / max(h, w)
    nw, nh = max(1, round(w * k)), max(1, round(h * k))
    im = Image.fromarray(rgb).resize((nw, nh), Image.LANCZOS)
    out = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    x0, y0 = (SIZE - nw) // 2, (SIZE - nh) // 2
    out[y0:y0 + nh, x0:x0 + nw] = np.asarray(im)
    return out, (x0, y0, nw, nh)


def circle_mask(size):
    x = np.linspace(-1, 1, size)
    y = np.linspace(1, -1, size)
    yy, xx = np.meshgrid(y, x, indexing="ij")
    return (1 - xx ** 2 - yy ** 2) >= 0


def control_and_mask(depth):
    """the depth picture (SIZE, SIZE) uint8 with a white (near) disc where the ball goes; the inpainting mask"""
    c = (SIZE - BALL) // 2
    disc = circle_mask(BALL)
    d = np.asarray(depth, dtype=np.uint8).copy()
    d[c:c + BALL, c:c + BALL] = d[c:c + BALL, c:c + BALL] * (1 - disc) + disc * 255
    mask = np.zeros_like(d)
    h = DILATE // 2
    mask[c - h:c + BALL + h, c - h:c + BALL + h] = circle_mask(BALL + DILATE) * 255
    return d, mask


def crop_ball(image):
    """the painted ball, BALL x BALL, from a SIZE x SIZE result"""
    c = (SIZE - BALL) // 2
    return np.asarray(image)[c:c + BALL, c:c + BALL, :3]


def prompt_mix(ev):
    """how much of PROMPT (vs PROMPT_BLACK) an exposure uses: 1 at EV 0, 0 at the lowest EV"""
    return (ev - EVS[-1]) / (0 - EVS[-1])


def ball_to_envmap(ball, height=256, scale=4):
    """a chrome ball (B, B, 3) float -> its equirectangular map (height, 2 * height, 3).
    The map's middle column looks where the camera looks, its left half is the camera's left, its top row is up."""
    import torch  # noqa: PLC0415

    size = height * scale
    theta, phi = np.meshgrid(np.linspace(0, np.pi * 2, size * 2), np.linspace(0, np.pi, size), indexing="xy")
    reflect = np.stack([np.sin(phi) * np.cos(theta), np.sin(phi) * np.sin(theta), np.cos(phi)], axis=-1)
    view = np.array([1.0, 0.0, 0.0])  # from the ball to the camera
    n = view + reflect
    n /= np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)
    grid = torch.from_numpy(-n[..., 1:])[None].float()  # (pos = 1 - (n + 1) / 2) * 2 - 1 = -n: ball left = +y, top = +z
    t = torch.from_numpy(np.ascontiguousarray(ball, dtype=np.float32))[None].permute(0, 3, 1, 2)
    with torch.no_grad():
        env = torch.nn.functional.grid_sample(t, grid, mode="bilinear", padding_mode="border", align_corners=True)
    env = env[0].permute(1, 2, 0).numpy()
    return env.reshape(height, scale, 2 * height, scale, 3).mean(axis=(1, 3))


def merge_exposures(maps, evs=EVS, gamma=GAMMA):
    """LDR maps in [0, 1] (one per EV, brightest first) -> one linear HDR map (exposure2hdr.py's bracketing)"""
    order = sorted(range(len(evs)), key=lambda i: -evs[i])
    maps = [np.asarray(maps[i], dtype=np.float64)[..., :3] for i in order]
    evs = [evs[i] for i in order]
    scaler = np.array([0.212671, 0.715160, 0.072169])
    image0_linear = np.power(maps[0], gamma)
    lum = [(np.power(m, gamma) / (2 ** ev)) @ scaler for m, ev in zip(maps, evs)]
    out = lum[-1]
    for i in range(len(evs) - 1, 0, -1):
        maxval = 1 / (2 ** evs[i - 1])
        p1 = np.clip((lum[i - 1] - 0.9 * maxval) / (0.1 * maxval), 0, 1)
        p2 = out > lum[i - 1]
        m = (p1 * p2).astype(np.float64)
        out = lum[i - 1] * (1 - m) + out * m
    return (image0_linear * (out / (lum[0] + 1e-10))[..., None]).astype(np.float32)


def tonemap(hdr, gamma=GAMMA, percentile=99, max_mapping=0.9):
    """HDR -> [0, 1] for looking at (TonemapHDR: the percentile maps to max_mapping)"""
    p = np.power(np.maximum(hdr, 0), 1 / gamma)
    nz = p > 0
    r = np.percentile(p[nz] if nz.any() else p, percentile)
    return np.clip(p * (max_mapping / (r + 1e-10)), 0, 1).astype(np.float32)


def write_exr(path, rgb):
    """an (H, W, 3) float32 linear image -> a ZIP-compressed scanline EXR (OpenEXR 3)"""
    import OpenEXR  # noqa: PLC0415

    header = {"compression": OpenEXR.ZIP_COMPRESSION, "type": OpenEXR.scanlineimage}
    with OpenEXR.File(header, {"RGB": np.ascontiguousarray(rgb, dtype=np.float32)}) as f:
        f.write(path)
