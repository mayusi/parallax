"""made.py — a small made "scene" for the trace's proof (kit selftest + kit/test/python/test_vfx_trace.py): a drawn
flame whose every outline is KNOWN, because the frames are made from it.

    the scene (24 a second, 640 x 360)   2 frames of the night alone; then SIX drawings of one flame, each held two
                                         frames (on twos); then 2 frames of the night alone
    the flame                            an orange teardrop with ONE sharp tip at its top and a round foot, ONE cut-out
                                         (a hole the night shows through) and a yellow core under it; every drawing is
                                         taller and leans a little more, the cut-out rides up with it
    the night                            a blue-grey gradient, a dark figure standing beside the flame (not in the
                                         fire's hue band) and a grain of +-3 on every frame (a clip's noise: two frames
                                         of one drawing are never byte-identical)
    flood()                              the same flame in front of a WALL in the fire's own hue band: the cut-out is the
                                         wall, not a drawing - the trace must refuse it

The fire is in the hue band 5-55 the kit measures for fire (kit/selftest/vfx/dailies/clips.py uses the same).
"""

import numpy as np
from PIL import Image, ImageDraw

W, H = 640, 360
FPS = 24.0
HUE = (5.0, 55.0)
BODY = (240, 120, 30)
CORE = (255, 225, 90)
DRAWINGS = 6
HOLD = 2
SS = 4


def width(u, half):
    """the flame's half width at height u (0 = its foot, 1 = its tip): a round foot, a pinch to ONE sharp tip"""
    return half * (np.sqrt(4.0 * u * (1.0 - u)) if u < 0.5 else 1.0 - ((u - 0.5) / 0.5) ** 2)


def outline(k):
    """drawing k's flame -> (body polygon, cut-out polygon, core polygon, tip) in px: a teardrop standing on a round
    foot; every drawing taller and leaning more"""
    height = 150.0 + 16.0 * k
    lean = 6.0 * k
    cx, base, half = 330.0, 310.0, 52.0
    us = np.linspace(0.0, 1.0, 96)
    right = [(cx + lean * u * u + width(u, half), base - height * u) for u in us]
    left = [(cx + lean * u * u - width(u, half), base - height * u) for u in us]
    tip = (cx + lean, base - height)
    body = right[:-1] + [tip] + left[::-1][1:-1]
    hy, hx = base - height * 0.52, cx + lean * 0.27 - 18.0
    hole = [(hx + 9.0 * np.cos(a), hy + 16.0 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 40, endpoint=False)]
    cy = base - height * 0.24
    core = [(cx + 4.0 + 16.0 * np.cos(a), cy + 20.0 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 40, endpoint=False)]
    return body, hole, core, tip


def night(wall=False):
    yy = np.linspace(0.0, 1.0, H)[:, None]
    f = np.zeros((H, W, 3), dtype=np.float32)
    if wall:
        f[:] = (228, 110, 36)                                # a wall in the fire's hue band, lit
        f -= yy[..., None] * 20.0
    else:
        f[:] = (34, 46, 66)
        f += yy[..., None] * np.array([10.0, 12.0, 16.0], dtype=np.float32)
    f[120:330, 150:215] = (28, 24, 30)                       # a figure beside the flame
    return f


def truth(k):
    """drawing k's true masks -> (body with its cut-out, core), each (H, W) bool"""
    body, hole, core, _ = outline(k)
    im = Image.new("L", (W * SS, H * SS), 0)
    pen = ImageDraw.Draw(im)
    pen.polygon([(x * SS, y * SS) for x, y in body], fill=255)
    pen.polygon([(x * SS, y * SS) for x, y in hole], fill=0)
    b = np.asarray(im.resize((W, H), Image.BOX)) >= 128
    im = Image.new("L", (W * SS, H * SS), 0)
    ImageDraw.Draw(im).polygon([(x * SS, y * SS) for x, y in core], fill=255)
    return b, np.asarray(im.resize((W, H), Image.BOX)) >= 128


def picture(k=None, wall=False, seed=0):
    """one frame: the night (or the wall), with drawing k's flame when k is given; anti-aliased like a clip's frame"""
    back = night(wall)
    if k is not None:
        body, hole, core, _ = outline(k)
        cov = Image.new("L", (W * SS, H * SS), 0)
        pen = ImageDraw.Draw(cov)
        pen.polygon([(x * SS, y * SS) for x, y in body], fill=255)
        pen.polygon([(x * SS, y * SS) for x, y in hole], fill=0)
        a = np.asarray(cov.resize((W, H), Image.BOX), dtype=np.float32)[..., None] / 255.0
        back = back * (1 - a) + np.array(BODY, dtype=np.float32) * a
        cov = Image.new("L", (W * SS, H * SS), 0)
        ImageDraw.Draw(cov).polygon([(x * SS, y * SS) for x, y in core], fill=255)
        a = np.asarray(cov.resize((W, H), Image.BOX), dtype=np.float32)[..., None] / 255.0
        back = back * (1 - a) + np.array(CORE, dtype=np.float32) * a
    grain = np.random.default_rng(1000 + seed).integers(-3, 4, size=back.shape)
    return np.clip(back + grain, 0, 255).astype(np.uint8)


def scene(wall=False):
    """the made scene -> (N, H, W, 3) bytes: 2 empty frames, six drawings on twos, 2 empty frames"""
    out, n = [], 0
    for _ in range(2):
        out.append(picture(None, wall, n))
        n += 1
    for k in range(DRAWINGS):
        for _ in range(HOLD):
            out.append(picture(k, wall, n))
            n += 1
    for _ in range(2):
        out.append(picture(None, wall, n))
        n += 1
    return np.stack(out)


def flood():
    return scene(wall=True)
