"""madepan.py - a MADE shot whose camera moves by a known amount (no real footage): the made flame of
kit/selftest/vfx/trace/made.py standing in a larger night world full of small lights, filmed by a camera that pans
and zooms a little on every frame. The flame is drawn on twos IN THE WORLD: with the camera followed, its drawings
hold two frames each; without, every frame differs from the last.

    scene(pan=(3.0, -1.5), zoom=0.004) -> (frames (N, 360, 640, 3) bytes, truth: per frame the 3x3 matrix that takes
                                           a point of that frame to where it is in frame 0)
"""

import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "trace"))
import made  # noqa: E402

W, H = 640, 360
WORLD = (1000, 640)          # (width, height) of the world the camera looks into
AT = (180.0, 140.0)          # where the frame-0 view's top left sits in the world
SS = 2


def world(k=None):
    """the world as a picture (float32 RGB): a night sky, dark blocks, a few hundred small cold lights; with drawing
    k's flame standing in it when k is given"""
    ww, wh = WORLD
    yy = np.linspace(0.0, 1.0, wh)[:, None]
    f = np.zeros((wh, ww, 3), dtype=np.float32)
    f[:] = (30, 42, 62)
    f += yy[..., None] * np.array([12.0, 14.0, 20.0], dtype=np.float32)
    rng = np.random.default_rng(77)
    canvas = Image.fromarray(np.clip(f, 0, 255).astype(np.uint8))
    pen = ImageDraw.Draw(canvas)
    for _ in range(26):                                        # blocks: roofs and walls, darker than the sky
        x, y = int(rng.integers(0, ww - 60)), int(rng.integers(wh // 3, wh - 40))
        w, h = int(rng.integers(30, 120)), int(rng.integers(30, 160))
        tone = int(rng.integers(14, 30))
        pen.rectangle([x, y, x + w, y + h], fill=(tone, tone + 2, tone + 8))
    for _ in range(420):                                       # lights: cold (blue-white), never in the fire's hue band
        x, y = float(rng.uniform(0, ww)), float(rng.uniform(0, wh))
        r = float(rng.uniform(1.2, 3.2))
        v = int(rng.integers(120, 235))
        pen.ellipse([x - r, y - r, x + r, y + r], fill=(v - 30, v - 10, v))
    back = np.asarray(canvas, dtype=np.float32)
    if k is not None:
        body, hole, core, _ = made.outline(k)
        for poly, cut, colour in ((body, hole, made.BODY), (core, None, made.CORE)):
            cov = Image.new("L", (ww * SS, wh * SS), 0)
            p = ImageDraw.Draw(cov)
            p.polygon([((x + AT[0]) * SS, (y + AT[1]) * SS) for x, y in poly], fill=255)
            if cut is not None:
                p.polygon([((x + AT[0]) * SS, (y + AT[1]) * SS) for x, y in cut], fill=0)
            a = np.asarray(cov.resize((ww, wh), Image.BOX), dtype=np.float32)[..., None] / 255.0
            back = back * (1 - a) + np.array(colour, dtype=np.float32) * a
    return back


def view(i, pan, zoom):
    """the 3x3 matrix taking a WORLD point to frame i's picture: the view's top left slides by `pan` px a frame, and
    the picture grows by `zoom` a frame about its own centre"""
    z = 1.0 + zoom * i
    cx, cy = W / 2.0, H / 2.0
    ox, oy = AT[0] + pan[0] * i, AT[1] + pan[1] * i
    # frame = centre + z * ((world - top left) - centre)
    return np.array([[z, 0.0, cx - z * (ox + cx)], [0.0, z, cy - z * (oy + cy)], [0.0, 0.0, 1.0]])


def scene(pan=(3.0, -1.5), zoom=0.004, flame=True):
    """the made shot -> (frames, truth). 2 empty frames, six drawings on twos, 2 empty frames (as made.scene)"""
    order = [None, None] + [k for k in range(made.DRAWINGS) for _ in range(made.HOLD)] + [None, None]
    worlds = {k: world(k if flame else None) for k in set(order)}
    frames, views = [], []
    for i, k in enumerate(order):
        m = view(i, pan, zoom)
        pic = cv2.warpAffine(worlds[k], m[:2], (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        grain = np.random.default_rng(2000 + i).integers(-3, 4, size=pic.shape)
        frames.append(np.clip(pic + grain, 0, 255).astype(np.uint8))
        views.append(m)
    truth = [views[0] @ np.linalg.inv(m) for m in views]
    return np.stack(frames), truth
