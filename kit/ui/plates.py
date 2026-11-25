"""plates.py — an identity's drawn art: the frames, slots, bar caps, dividers, bands, highlights, key caps, grain and
ornaments a real game UI is made of, drawn in code from the identity's SHAPE LANGUAGE (its lines, fill, corner
treatment) so every piece belongs to the same world. Not white masks: finished pieces in the identity's colours.

    python kit/ui/plates.py --identities assets/ui/identities --out build/ui/art [identity ...]

Per identity: build/ui/art/<identity>/<plate>.png + art.json ({plate: {size, slice}}). Screen specs use them as
{"type": "plate", "plate": "frame"} (or "image": "art:<identity>/frame"); `kit upload` puts them on Roblox as
ids.ui["<identity>/<plate>"]. Everything is drawn 4x and downscaled: anti-aliased, no jaggies.

identity.json "shape": { "line": "#8a7446", "line2": "#3b2f18", "fill": "#0a0908", "fill_alpha": 0.86,
  "width": 2, "corner": "flourish" | "bracket" | "chamfer" | "round" | "none", "chamfer": 8, "glow": "#d7b870",
  "grain": 0.5 }  — and "plates": { "<name>": { ...overrides... } } to tune one piece (any kind's parameter).

    frame       9-slice panel: fill + outer line + inner hairline + corners      panels, dialogs, tooltips
    frame_line  the same, outline only                                           ghost frames, focus rings
    slot        square item slot: bevelled two-tone edge, inner shadow            inventory, quick slots
    cap         a bar's end piece (drawn for the LEFT end; rotate 180 for right)  health / stamina bar ends
    track       a bar's track: dark, thin line                                   behind every bar
    divider     a thin line fading to both ends with a centre ornament           between rows, under titles
    band        a soft-edged dark band across the screen                         YOU DIED, chapter titles
    vignette    dark edges, clear middle                                         death, low health, menus
    grain       seeded noise tile (tile it; strength = ImageTransparency)        paper / film texture
    highlight   a soft bar fading at both ends, brighter core                    the selected row
    keycap      a key cap in the identity's shape                                [E] Interact
    glow        soft radial glow                                                 behind counters, pickups
    ornament    a lozenge emblem with flourishes                                 title ends, bonfire marker
    corner      an L bracket with a flourish (rotate 0/90/180/270)               corners of a hero panel
    arrow       a small pointer (rotate for up/down/left/right)                  stat deltas, menu cursor
    ring        a thin double ring                                               compass, cooldown
    ribbon      a title ribbon with pointed ends (9-slice keeps the ends)         section titles
"""

import argparse
import json
import math
import os
import random
import re
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SS = 4  # supersample

DEFAULT_SHAPE = {
    "line": "#c8b273",
    "line2": "#5a4a26",
    "fill": "#0b0a09",
    "fill_alpha": 0.88,
    "width": 2,
    "corner": "flourish",
    "chamfer": 8,
    "glow": "#e8d7a0",
    "grain": 0.5,
}

# name -> (kind, size (w, h) at 1x, 9-slice [l, t, r, b] at 1x or None)
PLATES = {
    "frame": ("frame", (192, 192), [64, 64, 128, 128]),
    "frame_line": ("frame_line", (192, 192), [64, 64, 128, 128]),
    "slot": ("slot", (128, 128), [40, 40, 88, 88]),
    "cap": ("cap", (48, 48), None),
    "track": ("track", (128, 128), [16, 16, 112, 112]),
    "divider": ("divider", (512, 24), None),
    "band": ("band", (64, 256), None),
    "vignette": ("vignette", (512, 512), None),
    "grain": ("grain", (256, 256), None),
    "highlight": ("highlight", (512, 48), None),
    "keycap": ("keycap", (96, 96), [26, 26, 70, 70]),
    "glow": ("glow", (256, 256), None),
    "ornament": ("ornament", (128, 128), None),
    "corner": ("corner", (96, 96), None),
    "arrow": ("arrow", (64, 64), None),
    "ring": ("ring", (256, 256), None),
    "ribbon": ("ribbon", (512, 96), [112, 0, 400, 96]),
}


def hex_rgb(s, default=(255, 255, 255)):
    if isinstance(s, (list, tuple)) and len(s) == 3:
        return tuple(int(v) for v in s)
    if not isinstance(s, str) or not s.startswith("#") or len(s) != 7:
        return default
    return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))


def rgba(c, a=1.0):
    return c + (int(round(255 * max(0, min(1, a)))),)


def canvas(w, h):
    return Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))


def down(img, w, h):
    return img.resize((w, h), Image.LANCZOS)


def lighten(c, k):
    return tuple(min(255, int(v + (255 - v) * k)) for v in c)


def darken(c, k):
    return tuple(int(v * (1 - k)) for v in c)


def outline_path(d, box, corner, chamfer, width, color, inset=0):
    """the identity's frame line around box (x0, y0, x1, y1) in SS pixels"""
    x0, y0, x1, y1 = box
    x0, y0, x1, y1 = x0 + inset, y0 + inset, x1 - inset, y1 - inset
    if corner == "chamfer" and chamfer > 0:
        c = chamfer
        pts = [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]
        d.polygon(pts, outline=color, width=width)
    elif corner == "round":
        d.rounded_rectangle([x0, y0, x1, y1], radius=chamfer * 1.5, outline=color, width=width)
    else:
        d.rectangle([x0, y0, x1, y1], outline=color, width=width)


def fill_path(d, box, corner, chamfer, color, inset=0):
    x0, y0, x1, y1 = box
    x0, y0, x1, y1 = x0 + inset, y0 + inset, x1 - inset, y1 - inset
    if corner == "chamfer" and chamfer > 0:
        c = chamfer
        pts = [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c)]
        d.polygon(pts, fill=color)
    elif corner == "round":
        d.rounded_rectangle([x0, y0, x1, y1], radius=chamfer * 1.5, fill=color)
    else:
        d.rectangle([x0, y0, x1, y1], fill=color)


def lozenge(d, cx, cy, r, color, width=0):
    pts = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    if width:
        d.polygon(pts, outline=color, width=width)
    else:
        d.polygon(pts, fill=color)


def flourish_corner(d, cx, cy, dx, dy, size, line, line2, width):
    """a corner ornament at (cx, cy); (dx, dy) points INTO the panel: a lozenge on the corner, a hairline inward"""
    lozenge(d, cx, cy, size * 0.55, line)
    lozenge(d, cx, cy, size * 0.3, line2)
    d.line([(cx + dx * size * 0.7, cy), (cx + dx * size * 1.9, cy)], fill=line, width=max(1, width // 2))
    d.line([(cx, cy + dy * size * 0.7), (cx, cy + dy * size * 1.9)], fill=line, width=max(1, width // 2))
    d.ellipse([cx + dx * size * 2.2 - width, cy - width, cx + dx * size * 2.2 + width, cy + width], fill=line)
    d.ellipse([cx - width, cy + dy * size * 2.2 - width, cx + width, cy + dy * size * 2.2 + width], fill=line)


def bracket_corner(d, cx, cy, dx, dy, size, line, width):
    w = width * 2
    d.line([(cx, cy), (cx + dx * size * 2.5, cy)], fill=line, width=w)
    d.line([(cx, cy), (cx, cy + dy * size * 2.5)], fill=line, width=w)


def corners(d, box, corner, size, line, line2, width):
    x0, y0, x1, y1 = box
    for cx, cy, dx, dy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x1, y1, -1, -1), (x0, y1, 1, -1)):
        if corner == "flourish":
            flourish_corner(d, cx, cy, dx, dy, size, line, line2, width)
        elif corner == "bracket":
            bracket_corner(d, cx, cy, dx, dy, size, line, width)


# ------------------------------------------------------------------ the plates
def p_frame(sh, size, outline_only=False):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    line, line2, fill = hex_rgb(sh["line"]), hex_rgb(sh["line2"]), hex_rgb(sh["fill"])
    width = max(1, int(sh["width"] * SS))
    margin = 14 * SS
    box = (margin, margin, w * SS - margin, h * SS - margin)
    corner = sh["corner"]
    chamfer = int(sh["chamfer"] * SS)
    if not outline_only:
        fill_path(d, box, corner, chamfer, rgba(fill, sh["fill_alpha"]))
        # a lit top edge inside: the panel is a surface, not a hole
        top = Image.new("RGBA", im.size, (0, 0, 0, 0))
        td = ImageDraw.Draw(top)
        for i in range(10 * SS):
            a = int(38 * (1 - i / (10 * SS)))
            td.line([(box[0] + chamfer, box[1] + width + i), (box[2] - chamfer, box[1] + width + i)], fill=rgba(lighten(fill, 0.5), a / 255))
        im.alpha_composite(top)
        d = ImageDraw.Draw(im)
    outline_path(d, box, corner, chamfer, width, rgba(line))
    outline_path(d, box, corner, max(0, chamfer - 3 * SS), max(1, width // 2), rgba(line2, 0.9), inset=4 * SS)
    corners(d, box, corner, 4 * SS, rgba(line), rgba(line2), width)
    return down(im, w, h)


def p_slot(sh, size):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    line, line2, fill = hex_rgb(sh["line"]), hex_rgb(sh["line2"]), hex_rgb(sh["fill"])
    width = max(1, int(sh["width"] * SS))
    m = 10 * SS
    box = (m, m, w * SS - m, h * SS - m)
    d.rectangle(box, fill=rgba(darken(fill, 0.2), 0.94))
    # inner shadow: darker towards the edges
    for i in range(8 * SS):
        a = int(90 * (1 - i / (8 * SS)))
        d.rectangle([box[0] + i, box[1] + i, box[2] - i, box[3] - i], outline=(0, 0, 0, a), width=1)
    # two-tone bevel: light top-left, dark bottom-right
    d.line([(box[0], box[3]), (box[0], box[1]), (box[2], box[1])], fill=rgba(lighten(line, 0.25)), width=width)
    d.line([(box[2], box[1]), (box[2], box[3]), (box[0], box[3])], fill=rgba(line2), width=width)
    d.rectangle([box[0] + width * 2, box[1] + width * 2, box[2] - width * 2, box[3] - width * 2], outline=rgba(line, 0.55), width=max(1, width // 2))
    return down(im, w, h)


def p_cap(sh, size):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    line, line2 = hex_rgb(sh["line"]), hex_rgb(sh["line2"])
    cx, cy = w * SS * 0.62, h * SS / 2
    r = h * SS * 0.26
    lozenge(d, cx, cy, r, rgba(line))
    lozenge(d, cx, cy, r * 0.55, rgba(line2))
    lozenge(d, cx, cy, r * 0.22, rgba(lighten(line, 0.5)))
    # a short stem towards the bar (right side)
    d.line([(cx + r * 0.6, cy), (w * SS, cy)], fill=rgba(line), width=max(1, int(sh["width"] * SS)))
    # a small tail outward (left)
    d.line([(cx - r * 1.5, cy), (cx - r * 0.6, cy)], fill=rgba(line, 0.8), width=max(1, int(sh["width"] * SS * 0.6)))
    d.ellipse([cx - r * 1.75, cy - r * 0.25, cx - r * 1.25, cy + r * 0.25], fill=rgba(line))
    return down(im, w, h)


def p_track(sh, size):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    line2, fill = hex_rgb(sh["line2"]), hex_rgb(sh["fill"])
    m = 6 * SS
    box = [m, m, w * SS - m, h * SS - m]
    d.rectangle(box, fill=rgba(darken(fill, 0.1), 0.92))
    d.rectangle(box, outline=rgba(line2, 0.9), width=max(1, int(sh["width"] * SS * 0.75)))
    d.rectangle([box[0] + 2 * SS, box[1] + 2 * SS, box[2] - 2 * SS, box[3] - 2 * SS], outline=(0, 0, 0, 120), width=SS)
    return down(im, w, h)


def p_divider(sh, size):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    line, line2 = hex_rgb(sh["line"]), hex_rgb(sh["line2"])
    cy = h * SS / 2
    width = max(1, int(sh["width"] * SS * 0.6))
    for x in range(0, w * SS, SS):
        t = x / (w * SS)
        a = max(0.0, 1 - abs(t - 0.5) * 2) ** 0.6
        d.line([(x, cy), (x + SS, cy)], fill=rgba(line, a), width=width)
    cx = w * SS / 2
    r = h * SS * 0.42
    lozenge(d, cx, cy, r, rgba(line))
    lozenge(d, cx, cy, r * 0.5, rgba(line2))
    for sx in (-1, 1):
        d.ellipse([cx + sx * r * 2.2 - r * 0.22, cy - r * 0.22, cx + sx * r * 2.2 + r * 0.22, cy + r * 0.22], fill=rgba(line))
    return down(im, w, h)


def p_band(sh, size):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    for y in range(h * SS):
        t = y / (h * SS)
        a = max(0.0, min(1.0, (0.5 - abs(t - 0.5)) * 3.2))  # soft edges, solid middle
        d.line([(0, y), (w * SS, y)], fill=(0, 0, 0, int(255 * a ** 1.4 * 0.94)))
    return down(im, w, h)


def radial(w, h, fn):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = im.load()
    cx, cy = (w - 1) / 2, (h - 1) / 2
    for y in range(h):
        for x in range(w):
            r = math.hypot((x - cx) / cx, (y - cy) / cy)
            px[x, y] = fn(r)
    return im


def p_vignette(sh, size):
    w, h = size

    def fn(r):
        a = max(0.0, min(1.0, (r - 0.45) / 0.75)) ** 1.6
        return (0, 0, 0, int(255 * a))

    return radial(w, h, fn)


def p_grain(sh, size):
    w, h = size
    rnd = random.Random(7)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = im.load()
    strength = float(sh.get("grain", 0.5))
    for y in range(h):
        for x in range(w):
            v = rnd.random()
            a = int(255 * strength * (0.25 + 0.75 * v ** 3))
            tone = 255 if v > 0.5 else 0
            px[x, y] = (tone, tone, tone, a)
    return im.filter(ImageFilter.GaussianBlur(0.35))


def p_highlight(sh, size):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    glow, line = hex_rgb(sh["glow"]), hex_rgb(sh["line"])
    cy = h * SS / 2
    for x in range(0, w * SS, SS):
        t = x / (w * SS)
        a = max(0.0, 1 - abs(t - 0.5) * 2) ** 0.9
        d.line([(x, 0), (x, h * SS)], fill=rgba(glow, 0.62 * a))
        # a brighter core band through the middle, like light on a worn gold strip
        d.line([(x, cy - h * SS * 0.18), (x, cy + h * SS * 0.18)], fill=rgba(lighten(glow, 0.2), 0.35 * a))
    # a bright hairline top + bottom, fading the same way
    for x in range(0, w * SS, SS):
        t = x / (w * SS)
        a = max(0.0, 1 - abs(t - 0.5) * 2) ** 0.8
        d.line([(x, SS), (x + SS, SS)], fill=rgba(lighten(line, 0.3), 0.9 * a), width=SS)
        d.line([(x, h * SS - SS), (x + SS, h * SS - SS)], fill=rgba(lighten(line, 0.3), 0.9 * a), width=SS)
    return down(im, w, h)


def p_keycap(sh, size):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    line, line2, fill = hex_rgb(sh["line"]), hex_rgb(sh["line2"]), hex_rgb(sh["fill"])
    m = 10 * SS
    box = (m, m, w * SS - m, h * SS - m - 4 * SS)
    d.rounded_rectangle([box[0], box[1] + 4 * SS, box[2], box[3] + 4 * SS], radius=3 * SS, fill=rgba(line2))  # the lip
    fill_path(d, box, "round", 2, rgba(fill, 0.96))
    outline_path(d, box, "round", 2, max(1, int(sh["width"] * SS)), rgba(line))
    return down(im, w, h)


def p_glow(sh, size):
    w, h = size
    g = hex_rgb(sh["glow"])

    def fn(r):
        a = max(0.0, 1 - r) ** 2.2
        return g + (int(255 * a),)

    return radial(w, h, fn)


def p_ornament(sh, size):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    line, line2 = hex_rgb(sh["line"]), hex_rgb(sh["line2"])
    cx, cy = w * SS / 2, h * SS / 2
    r = w * SS * 0.3
    lozenge(d, cx, cy, r, rgba(line), width=max(1, int(sh["width"] * SS)))
    lozenge(d, cx, cy, r * 0.72, rgba(line2))
    lozenge(d, cx, cy, r * 0.4, rgba(line))
    lozenge(d, cx, cy, r * 0.16, rgba(lighten(line, 0.6)))
    for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        d.line([(cx + sx * r * 1.1, cy + sy * r * 1.1), (cx + sx * r * 1.55, cy + sy * r * 1.55)], fill=rgba(line), width=max(1, int(sh["width"] * SS * 0.6)))
        d.ellipse([cx + sx * r * 1.62 - 2 * SS, cy + sy * r * 1.62 - 2 * SS, cx + sx * r * 1.62 + 2 * SS, cy + sy * r * 1.62 + 2 * SS], fill=rgba(line))
    return down(im, w, h)


def p_corner(sh, size):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    line, line2 = hex_rgb(sh["line"]), hex_rgb(sh["line2"])
    width = max(1, int(sh["width"] * SS))
    m = 12 * SS
    bracket_corner(d, m, m, 1, 1, 10 * SS, rgba(line), max(1, width // 2))
    flourish_corner(d, m, m, 1, 1, 4 * SS, rgba(line), rgba(line2), width)
    return down(im, w, h)


def p_arrow(sh, size):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    line = hex_rgb(sh["line"])
    cx, cy = w * SS / 2, h * SS / 2
    r = w * SS * 0.28
    d.polygon([(cx, cy - r), (cx + r, cy + r * 0.8), (cx - r, cy + r * 0.8)], fill=rgba(line))
    return down(im, w, h)


def p_ring(sh, size):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    line, line2 = hex_rgb(sh["line"]), hex_rgb(sh["line2"])
    width = max(1, int(sh["width"] * SS))
    m = 6 * SS
    d.ellipse([m, m, w * SS - m, h * SS - m], outline=rgba(line), width=width)
    m2 = m + 5 * SS
    d.ellipse([m2, m2, w * SS - m2, h * SS - m2], outline=rgba(line2), width=max(1, width // 2))
    return down(im, w, h)


def p_ribbon(sh, size):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    line, fill = hex_rgb(sh["line"]), hex_rgb(sh["fill"])
    width = max(1, int(sh["width"] * SS))
    W, H = w * SS, h * SS
    m = 8 * SS
    notch = 28 * SS
    pts = [(m + notch, m), (W - m - notch, m), (W - m, H / 2), (W - m - notch, H - m), (m + notch, H - m), (m, H / 2)]
    d.polygon(pts, fill=rgba(fill, sh["fill_alpha"]))
    d.polygon(pts, outline=rgba(line), width=width)
    inner = [(p[0] + (3 * SS if p[0] < W / 2 else -3 * SS), p[1] + (3 * SS if p[1] < H / 2 else -3 * SS)) for p in pts]
    d.polygon(inner, outline=rgba(line, 0.45), width=max(1, width // 2))
    return down(im, w, h)


# ------------------------------------------------------------------ the chunky family (simulators, casual, cartoon)
# finished colour pieces: a thick dark outline, a lit top (gloss), a shaded bottom, a white inner rim — drawn per
# colour token the identity lists in shape.buttons, and per rarity_* token for cards
def _chunky_body(d, box, radius, fill, line, width, gloss, shade, rim=True):
    x0, y0, x1, y1 = box
    # drop of darker colour at the bottom edge, the body, then the gloss band on top
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=rgba(line))
    inner = [x0 + width, y0 + width, x1 - width, y1 - width]
    d.rounded_rectangle(inner, radius=max(2, radius - width), fill=rgba(darken(fill, shade)))
    body_h = (inner[3] - inner[1])
    d.rounded_rectangle([inner[0], inner[1], inner[2], inner[3] - int(body_h * 0.14)], radius=max(2, radius - width), fill=rgba(fill))
    if gloss > 0:
        g = Image.new("RGBA", (int(inner[2] - inner[0]), int(body_h)), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        gd.rounded_rectangle([0, 0, g.width - 1, int(g.height * 0.46)], radius=max(2, radius - width), fill=(255, 255, 255, int(255 * gloss)))
        gd.rounded_rectangle([0, int(g.height * 0.3), g.width - 1, g.height - 1], radius=max(2, radius - width), fill=(0, 0, 0, 0))
        mask = Image.new("L", g.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, g.width - 1, g.height - 1], radius=max(2, radius - width), fill=255)
        g.putalpha(ImageChops.multiply(g.getchannel("A"), mask))
        return g, inner
    return None, inner


def p_bubble(sh, size, fill=None, radius_frac=0.24):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    fill = hex_rgb(fill or sh.get("fill2") or sh["fill"])
    line = hex_rgb(sh["line"])
    width = max(2, int(sh["width"] * SS))
    m = 8 * SS
    box = (m, m, w * SS - m, h * SS - m)
    radius = int(min(w, h) * SS * radius_frac)
    g, inner = _chunky_body(d, box, radius, fill, line, width, float(sh.get("gloss", 0.3)), float(sh.get("shade", 0.18)))
    if g is not None:
        im.alpha_composite(g, (int(inner[0]), int(inner[1])))
    d = ImageDraw.Draw(im)
    # the white inner rim that reads as a bevel
    d.rounded_rectangle([inner[0] + 1, inner[1] + 1, inner[2] - 1, inner[3] - 1], radius=max(2, radius - width), outline=(255, 255, 255, 110), width=max(1, SS))
    return down(im, w, h)


def p_pill(sh, size, fill=None):
    return p_bubble(sh, size, fill, radius_frac=0.5)


def p_badge(sh, size, fill=None):
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    fill = hex_rgb(fill or sh.get("fill2") or sh["fill"])
    line = hex_rgb(sh["line"])
    width = max(2, int(sh["width"] * SS))
    m = 6 * SS
    box = [m, m, w * SS - m, h * SS - m]
    d.ellipse(box, fill=rgba(line))
    inner = [box[0] + width, box[1] + width, box[2] - width, box[3] - width]
    ih = inner[3] - inner[1]
    d.ellipse(inner, fill=rgba(darken(fill, float(sh.get("shade", 0.18)))))
    # the lit body: the same ellipse lifted off the bottom, so a shaded crescent stays along the lower edge
    d.ellipse([inner[0], inner[1], inner[2], inner[3] - ih * 0.14], fill=rgba(fill))
    gloss = float(sh.get("gloss", 0.3))
    if gloss > 0:
        # a small highlight near the top, not a lid
        cx = (inner[0] + inner[2]) / 2
        iw = inner[2] - inner[0]
        d.ellipse([cx - iw * 0.3, inner[1] + ih * 0.1, cx + iw * 0.3, inner[1] + ih * 0.38], fill=(255, 255, 255, int(255 * gloss)))
    return down(im, w, h)


def p_card(sh, size, rarity_colour=None):
    """an item card: a cream body with a thick coloured (rarity) outline and a coloured header strip"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    body = hex_rgb(sh.get("card") or sh["fill"])
    edge = hex_rgb(rarity_colour or sh["line"])
    line = hex_rgb(sh["line"])
    width = max(2, int(sh["width"] * SS))
    m = 8 * SS
    box = [m, m, w * SS - m, h * SS - m]
    radius = int(min(w, h) * SS * 0.14)
    d.rounded_rectangle(box, radius=radius, fill=rgba(line))
    d.rounded_rectangle([box[0] + width // 2, box[1] + width // 2, box[2] - width // 2, box[3] - width // 2], radius=radius, fill=rgba(edge))
    inner = [box[0] + width * 2, box[1] + width * 2, box[2] - width * 2, box[3] - width * 2]
    d.rounded_rectangle(inner, radius=max(2, radius - width), fill=rgba(body))
    # the header strip in the rarity colour, lighter
    d.rounded_rectangle([inner[0], inner[1], inner[2], inner[1] + int((inner[3] - inner[1]) * 0.22)], radius=max(2, radius - width), fill=rgba(lighten(edge, 0.25)))
    d.rectangle([inner[0], inner[1] + int((inner[3] - inner[1]) * 0.12), inner[2], inner[1] + int((inner[3] - inner[1]) * 0.22)], fill=rgba(lighten(edge, 0.25)))
    return down(im, w, h)


def p_banner(sh, size, fill=None):
    """a chunky title tag: a wide rounded bubble with a deeper bottom lip"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    fill = hex_rgb(fill or sh.get("fill2") or sh["fill"])
    line = hex_rgb(sh["line"])
    width = max(2, int(sh["width"] * SS))
    m = 8 * SS
    box = (m, m, w * SS - m, h * SS - m - 6 * SS)
    radius = int(h * SS * 0.3)
    d.rounded_rectangle([box[0], box[1] + 6 * SS, box[2], box[3] + 6 * SS], radius=radius, fill=rgba(darken(line, 0.1)))  # the lip
    g, inner = _chunky_body(d, box, radius, fill, line, width, float(sh.get("gloss", 0.3)), float(sh.get("shade", 0.18)))
    if g is not None:
        im.alpha_composite(g, (int(inner[0]), int(inner[1])))
    return down(im, w, h)


def p_track_chunky(sh, size):
    """the chunky bar track: dark inset with an outline (9-slice)"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    line = hex_rgb(sh["line"])
    width = max(2, int(sh["width"] * SS))
    m = 6 * SS
    box = [m, m, w * SS - m, h * SS - m]
    radius = int(min(w, h) * SS * 0.5)
    d.rounded_rectangle(box, radius=radius, fill=rgba(line))
    inner = [box[0] + width, box[1] + width, box[2] - width, box[3] - width]
    d.rounded_rectangle(inner, radius=max(2, radius - width), fill=rgba(darken(line, 0.45)))
    d.rounded_rectangle([inner[0], inner[1], inner[2], inner[1] + (inner[3] - inner[1]) * 0.35], radius=max(2, radius - width), fill=(0, 0, 0, 70))
    return down(im, w, h)


def p_gloss(sh, size):
    """a white diagonal shine strip, for a hover sweep or a highlight overlay"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    d.polygon([(W * 0.3, 0), (W * 0.55, 0), (W * 0.25, H), (W * 0, H)], fill=(255, 255, 255, 120))
    d.polygon([(W * 0.62, 0), (W * 0.7, 0), (W * 0.4, H), (W * 0.32, H)], fill=(255, 255, 255, 70))
    return down(im, w, h).filter(ImageFilter.GaussianBlur(1.2))


def p_burst(sh, size):
    """a star burst of rays (behind a featured item, a hatch, a level-up)"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    glow = hex_rgb(sh["glow"])
    cx, cy = w * SS / 2, h * SS / 2
    R = w * SS * 0.5
    for i in range(16):
        a0 = i * (2 * math.pi / 16)
        a1 = a0 + (math.pi / 16) * 0.9
        pts = [(cx, cy), (cx + R * math.cos(a0), cy + R * math.sin(a0)), (cx + R * math.cos(a1), cy + R * math.sin(a1))]
        d.polygon(pts, fill=rgba(glow, 0.55 if i % 2 == 0 else 0.3))
    # fade the rays outward
    fade = radial(w * SS, h * SS, lambda r: (255, 255, 255, int(255 * max(0.0, 1 - r) ** 1.2)))
    im.putalpha(ImageChops.multiply(im.getchannel("A"), fade.getchannel("A")))
    return down(im, w, h)


def p_close(sh, size):
    """the red close button: a badge with a white X"""
    w, h = size
    im = p_badge(sh, size, sh.get("danger", "#ff4d4d"))
    big = im.resize((w * SS, h * SS), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    cx, cy = w * SS / 2, h * SS / 2
    r = w * SS * 0.2
    lw = max(2, int(sh["width"] * SS * 0.9))
    d.line([(cx - r, cy - r), (cx + r, cy + r)], fill=(255, 255, 255, 255), width=lw)
    d.line([(cx - r, cy + r), (cx + r, cy - r)], fill=(255, 255, 255, 255), width=lw)
    return down(big, w, h)


def p_plus(sh, size):
    """the green plus button (buy more): a badge with a white +"""
    w, h = size
    im = p_badge(sh, size, sh.get("good", "#4cd964"))
    big = im.resize((w * SS, h * SS), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    cx, cy = w * SS / 2, h * SS / 2
    r = w * SS * 0.22
    lw = max(2, int(sh["width"] * SS * 0.9))
    d.line([(cx - r, cy), (cx + r, cy)], fill=(255, 255, 255, 255), width=lw)
    d.line([(cx, cy - r), (cx, cy + r)], fill=(255, 255, 255, 255), width=lw)
    return down(big, w, h)


def p_slant(sh, size):
    """a white parallelogram (skewed right ~20 degrees) to tint with "color": gauge segments, slanted bands,
    anything an action HUD draws at an angle (the engine has no skew)"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    k = H * 0.5  # the horizontal run of the slant (~27 degrees: an action HUD's lean)
    d.polygon([(k, 0), (W, 0), (W - k, H), (0, H)], fill=(255, 255, 255, 255))
    return down(im, w, h)


def _jagged(W, H, seed, jag, n_per_edge=7, inset=0.0):
    """the points of a torn-paper outline: each edge walks in n uneven steps, every point kicked in or out"""
    import random
    rnd = random.Random(seed)
    pts = []
    corners = [(inset, inset), (W - inset, inset), (W - inset, H - inset), (inset, H - inset)]
    for i in range(4):
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 4]
        n = n_per_edge + rnd.randint(-2, 2)
        ts = sorted(rnd.uniform(0, 1) for _ in range(n - 1))
        for t in [0.0] + ts:
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            # kick perpendicular to the edge (outwards +, inwards -), bigger kicks near the corners
            nx, ny = (y1 - y0), -(x1 - x0)
            ln = max(1e-6, (nx * nx + ny * ny) ** 0.5)
            k = rnd.uniform(-jag, jag) * (1.0 + 0.6 * (abs(t - 0.5) * 2))
            pts.append((x + nx / ln * k, y + ny / ln * k))
    return pts


def p_torn(sh, size, fill=None, seed=5):
    """a torn-paper cutout (Persona-type): a jagged white shape with the identity's hard outline — tint it with
    "color"; a black card behind a white one (torn_black) makes the double-cut look"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    jag = min(W, H) * 0.09
    lw = max(2, int(sh["width"] * SS * 1.4))
    pts = _jagged(W, H, seed, jag, inset=jag + lw)
    d.polygon(pts, fill=(255, 255, 255, 255) if fill is None else rgba(hex_rgb(fill)), outline=rgba(hex_rgb(sh.get("line", "#000000"), (0, 0, 0))), width=lw)
    return down(im, w, h)


def p_torn_field(sh, size, seed=57):
    """a torn FIELD: the big diagonal paper that covers a third of a title screen — drawn large (960 x 540) with many
    small tears, so stretching it over a screen keeps the tears at paper scale (a 240 px plate stretched tenfold
    grows fist-sized jags)"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    jag = min(W, H) * 0.03
    lw = max(2, int(sh["width"] * SS * 1.2))
    pts = _jagged(W, H, seed, jag, n_per_edge=16, inset=jag + lw)
    d.polygon(pts, fill=(255, 255, 255, 255), outline=rgba(hex_rgb(sh.get("line", "#000000"), (0, 0, 0))), width=lw)
    return down(im, w, h)


def _cut_pts(W, H, seed, depth, cuts_per_edge=2, inset=0.0, spike=0.35):
    """the points of a SCISSOR-cut outline (Persona's shapes): every edge is a few long straight runs that break at
    sharp corners — a kick in or out of `depth`, plus the odd spike — never a per-pixel wobble (that reads as noise)"""
    import random
    rnd = random.Random(seed)
    pts = []
    corners = [(inset, inset), (W - inset, inset), (W - inset, H - inset), (inset, H - inset)]
    for i in range(4):
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 4]
        n = max(1, cuts_per_edge + rnd.randint(-1, 1))
        ts = sorted(rnd.uniform(0.12, 0.88) for _ in range(n))
        nx, ny = (y1 - y0), -(x1 - x0)
        ln = max(1e-6, (nx * nx + ny * ny) ** 0.5)
        nx, ny = nx / ln, ny / ln
        # the corner itself is cut off a little (a clipped corner, never a square one)
        ck = rnd.uniform(0.2, 0.6) * depth
        pts.append((x0 + nx * ck * rnd.choice((-1, 1)) * 0.5, y0 + ny * ck * rnd.choice((-1, 1)) * 0.5))
        for t in ts:
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            k = rnd.uniform(0.45, 1.0) * depth * rnd.choice((-1, 1))
            pts.append((x + nx * k, y + ny * k))
            if rnd.random() < spike:  # a spike: the next point sits close along the edge, kicked the other way
                t2 = min(0.95, t + rnd.uniform(0.03, 0.08))
                x2, y2 = x0 + (x1 - x0) * t2, y0 + (y1 - y0) * t2
                pts.append((x2 - nx * k * rnd.uniform(0.3, 0.8), y2 - ny * k * rnd.uniform(0.3, 0.8)))
    return pts


def p_cut(sh, size, fill=None, seed=5, depth_k=0.16, cuts=2):
    """a scissor-cut paper shape (Persona's command tags, dialogue boxes, title field): long straight runs, sharp
    corners, a hard outline in the identity's line colour; tint with "color"; cut_black behind it = the double cut"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    depth = min(W, H) * depth_k
    lw = max(2, int(sh["width"] * SS * 1.4))
    pts = _cut_pts(W, H, seed, depth, cuts_per_edge=cuts, inset=depth + lw)
    d.polygon(pts, fill=(255, 255, 255, 255) if fill is None else rgba(hex_rgb(fill)), outline=rgba(hex_rgb(sh.get("line", "#000000"), (0, 0, 0))), width=lw)
    return down(im, w, h)


def p_cut_b(sh, size):
    return p_cut(sh, size, seed=29)


def p_cut_c(sh, size):
    return p_cut(sh, size, seed=47, cuts=3)


def p_cut_black(sh, size):
    """the ink layer of a double cut: the same scissor shape in the line colour, slightly fuller"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    depth = min(W, H) * 0.14
    pts = _cut_pts(W, H, 11, depth, cuts_per_edge=2, inset=depth)
    d.polygon(pts, fill=rgba(hex_rgb(sh.get("line", "#000000"), (0, 0, 0))))
    return down(im, w, h)


def p_cut_field(sh, size, seed=73):
    """the scissor-cut FIELD of a title screen (960 x 540, stretched over a third of the frame): a few long
    diagonal runs with two or three big spikes — the P5 title's red field has ~6 straight edges, not a thousand tears"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    depth = min(W, H) * 0.12
    lw = max(2, int(sh["width"] * SS * 1.2))
    pts = _cut_pts(W, H, seed, depth, cuts_per_edge=2, inset=depth + lw, spike=0.5)
    d.polygon(pts, fill=(255, 255, 255, 255), outline=rgba(hex_rgb(sh.get("line", "#000000"), (0, 0, 0))), width=lw)
    return down(im, w, h)


def p_cut_strip(sh, size, seed=19):
    """a long scissor-cut STRIP (a menu line, a prompt bar): a parallelogram with clipped ends and one or two
    nicks along the long edges — the strips in Persona's command list and title menu"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    import random
    rnd = random.Random(seed)
    lw = max(2, int(sh["width"] * SS * 1.4))
    sk = H * rnd.uniform(0.25, 0.45)  # the lean of the ends
    m = lw + H * 0.06
    pts = [(m + sk, m), (W - m, m), (W - m - sk * rnd.uniform(0.6, 1.2), H - m), (m, H - m)]
    # a nick or two on the long edges
    out = []
    for i, (x, y) in enumerate(pts):
        out.append((x, y))
        (x1, y1) = pts[(i + 1) % 4]
        if abs(y1 - y) < H * 0.2 and rnd.random() < 0.8:  # a long edge
            t = rnd.uniform(0.3, 0.7)
            nx, ny = x + (x1 - x) * t, y + (y1 - y) * t
            k = H * rnd.uniform(0.08, 0.18) * (1 if y < H / 2 else -1)
            out.append((nx - (x1 - x) * 0.03, ny + k))
            out.append((nx + (x1 - x) * 0.03, ny))
    d.polygon(out, fill=(255, 255, 255, 255), outline=rgba(hex_rgb(sh.get("line", "#000000"), (0, 0, 0))), width=lw)
    return down(im, w, h)


def _tear_edge(W, y, seed, amp, n=40, fringe=0.0):
    """one long horizontal TEAR: many small irregular steps (paper fibres), a few deep notches — the edge of
    Persona's title band"""
    import random
    rnd = random.Random(seed)
    pts = []
    x = 0.0
    while x < W:
        x += W / n * rnd.uniform(0.4, 1.6)
        notch = amp * rnd.uniform(0.6, 1.0) * (3.0 if rnd.random() < 0.06 else 1.0)
        pts.append((min(x, W), y + rnd.uniform(-notch, notch) + fringe))
    return pts


def p_tear_band(sh, size, seed=81):
    """the title BAND: a long torn strip across the frame, two tones (white and a 62 % grey: the tint gives the
    accent and a darker accent), the darker tone a torn stripe inside it — tint with "color": accent"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    amp = H * 0.045
    top = _tear_edge(W, H * 0.12, seed, amp)
    bot = _tear_edge(W, H * 0.88, seed + 1, amp)
    d.polygon([(0, top[0][1])] + top + [(W, bot[-1][1])] + list(reversed(bot)) + [(0, bot[0][1])], fill=(255, 255, 255, 255))
    # the darker inner tear (the shadowed fold of the paper)
    t2 = _tear_edge(W, H * 0.55, seed + 2, amp * 0.8)
    b2 = _tear_edge(W, H * 0.86, seed + 3, amp * 0.6)
    d.polygon([(0, t2[0][1])] + t2 + [(W, b2[-1][1])] + list(reversed(b2)) + [(0, b2[0][1])], fill=(158, 158, 158, 255))
    return down(im, w, h)


def p_tear_fringe(sh, size, seed=81):
    """the PAPER FRINGE of the title band: thin white torn lines just outside its two edges (the same tear, offset),
    placed under the band with "color": "paper" — the white rim that makes the band read as torn paper"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    amp = H * 0.045
    for y0, s_off, sign in ((H * 0.12, 0, -1), (H * 0.88, 1, 1)):
        edge = _tear_edge(W, y0, seed + s_off, amp)
        outer = [(x, y + sign * H * 0.035) for x, y in _tear_edge(W, y0, seed + s_off + 50, amp * 1.4)]
        d.polygon(edge + list(reversed(outer)), fill=(255, 255, 255, 255))
    return down(im, w, h)


def p_zebra(sh, size):
    """diagonal zebra stripes (Persona's background stamps), white on clear, in a scissor-cut patch — tint "paper"
    over ink; stripes vary in width like hand-cut paper"""
    import random
    w, h = size
    im = canvas(w, h)
    stripes = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    ds = ImageDraw.Draw(stripes)
    W, H = w * SS, h * SS
    rnd = random.Random(13)
    x = -H
    while x < W + H:
        sw = rnd.uniform(0.035, 0.075) * W
        ds.polygon([(x, 0), (x + sw, 0), (x + sw - H * 0.8, H), (x - H * 0.8, H)], fill=(255, 255, 255, 255))
        x += sw * rnd.uniform(1.8, 2.6)
    mask = Image.new("L", (W, H), 0)
    depth = min(W, H) * 0.08
    ImageDraw.Draw(mask).polygon(_cut_pts(W, H, 5, depth, cuts_per_edge=2, inset=depth), fill=255)
    im.paste(stripes, (0, 0), mask)
    return down(im, w, h)


def p_torn_b(sh, size):
    """a second torn cutout shape (another tear): a pile of cutouts must not repeat one silhouette"""
    return p_torn(sh, size, seed=23)


def p_torn_c(sh, size):
    return p_torn(sh, size, seed=41)


def p_torn_black(sh, size):
    """the dark layer of a double cut: a torn shape in the identity's line colour, slightly bigger, to sit behind
    a torn white one offset by a few px"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    jag = min(W, H) * 0.1
    pts = _jagged(W, H, 11, jag, inset=jag * 0.6)
    d.polygon(pts, fill=rgba(hex_rgb(sh.get("line", "#000000"), (0, 0, 0))))
    return down(im, w, h)


def p_halftone(sh, size):
    """a halftone dot screen (pop-art shading): white dots growing from nothing at the left to full at the right,
    on transparent — tint with "color", fade with imageAlpha; rotate the node for a diagonal screen"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    import math
    W, H = w * SS, h * SS
    pitch = max(5, int(min(W, H) / 14))
    ang = math.radians(45.0)
    ca, sa = math.cos(ang), math.sin(ang)
    n = int((W + H) / pitch) + 2
    for i in range(-n, n):
        for j in range(-n, n):
            # a square grid rotated 45 degrees (the printer's screen angle), dots sized by their x across the plate
            cx = i * pitch * ca - j * pitch * sa + W / 2
            cy = i * pitch * sa + j * pitch * ca + H / 2
            if cx < -pitch or cx > W + pitch or cy < -pitch or cy > H + pitch:
                continue
            t = max(0.0, min(1.0, cx / max(1, W)))
            r = pitch * 0.62 * (0.08 + 0.92 * t)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 255))
    return down(im, w, h)


def p_dots(sh, size, cells=8):
    """a SEAMLESS halftone tile: uniform dots on a 45-degree screen whose period divides the tile exactly — use it
    with "fit": "tile" over a whole sky (the gradient halftone stretched over a screen gives fist-sized dots)"""
    import math
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    period = W / cells                    # the lattice repeats every `period` along x and y
    pitch = period / math.sqrt(2)         # the 45-degree grid's own spacing
    r = pitch * 0.5 * float(sh.get("dots", 0.55))
    ca = sa = math.sqrt(0.5)
    n = int(cells * 2.5) + 4
    for i in range(-n, n):
        for j in range(-n, n):
            cx = (i * pitch * ca - j * pitch * sa) % W
            cy = (i * pitch * sa + j * pitch * ca) % H
            for ox in (-W, 0, W):
                for oy in (-H, 0, H):
                    x_, y_ = cx + ox, cy + oy
                    if -r <= x_ <= W + r and -r <= y_ <= H + r:
                        d.ellipse([x_ - r, y_ - r, x_ + r, y_ + r], fill=(255, 255, 255, 255))
    return down(im, w, h)


def p_chevron(sh, size):
    """a big flat ARROW (a thick tail and a wide head, pointing right) with the identity's ink rim — tint it with
    "color" and rotate it: the giant selection arrow across a Persona-type command menu"""
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    lw = max(2, int(sh["width"] * SS * 1.2))
    tail = H * 0.42
    head = W * 0.36
    pts = [(lw, H / 2 - tail / 2), (W - head, H / 2 - tail / 2), (W - head, lw), (W - lw, H / 2), (W - head, H - lw),
           (W - head, H / 2 + tail / 2), (lw, H / 2 + tail / 2)]
    d.polygon(pts, fill=(255, 255, 255, 255), outline=rgba(hex_rgb(sh.get("line", "#000000"), (0, 0, 0))), width=lw)
    return down(im, w, h)


def p_rays(sh, size):
    """a speed-line burst: wedges radiating from the centre with uneven widths and gaps (a comic's emphasis),
    white on transparent — tint with "color"; sit it behind a rank letter or a hit callout"""
    import math
    import random
    w, h = size
    im = canvas(w, h)
    d = ImageDraw.Draw(im)
    W, H = w * SS, h * SS
    cx, cy = W / 2, H / 2
    R = min(W, H) / 2
    rnd = random.Random(3)
    a = 0.0
    while a < 2 * math.pi:
        width = rnd.uniform(0.22, 0.42)          # fat hand-cut wedges (Persona's emphasis), not needles
        gap = rnd.uniform(0.04, 0.14)
        r0 = R * rnd.uniform(0.14, 0.26)
        r1 = R * rnd.uniform(0.66, 1.0)           # uneven reach, always inside the circle: no box edge
        tip = a + width * rnd.uniform(0.3, 0.7)
        lw = max(1, int(sh["width"] * SS * 0.35))   # a thin ink rim: the wedge's colour must stay the wedge
        d.polygon([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + r1 * math.cos(tip), cy + r1 * math.sin(tip)),
                   (cx + r0 * math.cos(a + width), cy + r0 * math.sin(a + width))], fill=(255, 255, 255, 255),
                  outline=rgba(hex_rgb(sh.get("line", "#000000"), (0, 0, 0))), width=lw)
        a += width + gap
    return down(im, w, h)


def p_check(sh, size):
    """the green check badge (claimed, equipped, done): a badge with a white tick"""
    w, h = size
    im = p_badge(sh, size, sh.get("good", "#4cd964"))
    big = im.resize((w * SS, h * SS), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    cx, cy = w * SS / 2, h * SS / 2
    r = w * SS * 0.22
    lw = max(2, int(sh["width"] * SS * 0.9))
    d.line([(cx - r, cy), (cx - r * 0.25, cy + r * 0.75), (cx + r, cy - r * 0.7)], fill=(255, 255, 255, 255), width=lw, joint="curve")
    return down(big, w, h)


KINDS = {
    "frame": lambda sh, size: p_frame(sh, size),
    "frame_line": lambda sh, size: p_frame(sh, size, outline_only=True),
    "slot": p_slot,
    "cap": p_cap,
    "track": p_track,
    "divider": p_divider,
    "band": p_band,
    "vignette": p_vignette,
    "grain": p_grain,
    "highlight": p_highlight,
    "keycap": p_keycap,
    "glow": p_glow,
    "ornament": p_ornament,
    "corner": p_corner,
    "arrow": p_arrow,
    "ring": p_ring,
    "ribbon": p_ribbon,
    "bubble": p_bubble,
    "pill": p_pill,
    "badge": p_badge,
    "card": p_card,
    "banner": p_banner,
    "track_chunky": p_track_chunky,
    "gloss": p_gloss,
    "burst": p_burst,
    "close": p_close,
    "plus": p_plus,
    "check": p_check,
    "slant": p_slant,
    "torn": p_torn,
    "cut": p_cut,
    "cut_b": p_cut_b,
    "cut_c": p_cut_c,
    "cut_black": p_cut_black,
    "cut_field": p_cut_field,
    "cut_strip": p_cut_strip,
    "tear_band": p_tear_band,
    "tear_fringe": p_tear_fringe,
    "zebra": p_zebra,
    "torn_b": p_torn_b,
    "torn_field": p_torn_field,
    "torn_c": p_torn_c,
    "torn_black": p_torn_black,
    "halftone": p_halftone,
    "dots": p_dots,
    "rays": p_rays,
    "chevron": p_chevron,
}

# the chunky kinds, drawn for every identity (its shape decides how they look) — and per colour / rarity below
PLATES.update({
    "bubble": ("bubble", (192, 192), [60, 60, 132, 132]),
    "pill": ("pill", (192, 96), [60, 0, 132, 96]),
    "badge": ("badge", (128, 128), None),
    "card": ("card", (192, 256), [40, 72, 152, 216]),
    "banner": ("banner", (512, 96), [120, 0, 392, 96]),
    "track_chunky": ("track_chunky", (192, 48), [40, 0, 152, 48]),
    "gloss": ("gloss", (256, 256), None),
    "burst": ("burst", (512, 512), None),
    "close": ("close", (96, 96), None),
    "plus": ("plus", (96, 96), None),
    "check": ("check", (96, 96), None),
    "slant": ("slant", (96, 48), None),
    "torn": ("torn", (240, 120), None),
    "cut": ("cut", (240, 120), None),
    "cut_b": ("cut_b", (240, 120), None),
    "cut_c": ("cut_c", (240, 120), None),
    "cut_black": ("cut_black", (240, 120), None),
    "cut_field": ("cut_field", (960, 540), None),
    "cut_strip": ("cut_strip", (480, 96), None),
    "tear_band": ("tear_band", (1920, 480), None),
    "tear_fringe": ("tear_fringe", (1920, 480), None),
    "zebra": ("zebra", (320, 320), None),
    "torn_b": ("torn_b", (240, 120), None),
    "torn_field": ("torn_field", (960, 540), None),
    "torn_c": ("torn_c", (240, 120), None),
    "torn_black": ("torn_black", (240, 120), None),
    "halftone": ("halftone", (160, 160), None),
    "dots": ("dots", (160, 160), None),
    "rays": ("rays", (256, 256), None),
    "chevron": ("chevron", (480, 240), None),
})


def opaque_share(im):
    """the share of a piece's box that is actually painted (alpha over half) — the compiler weighs the accent
    FIELD by it: a torn wedge covers a fraction of its box, not the box"""
    a = im.convert("RGBA").getchannel("A")
    if a.width * a.height > 512 * 512:
        a = a.resize((512, max(1, round(512 * a.height / a.width))))
    hist = a.histogram()
    return round(sum(hist[128:]) / max(1, sum(hist)), 3)


def variants(identity, shape):
    """colour variants: bubble_<token> / pill_<token> / badge_<token> / banner_<token> for each token in
    shape.buttons, card_<rarity> for each rarity_* token — finished pieces in that colour"""
    tokens = identity.get("tokens") or {}
    out = {}
    for tok in shape.get("buttons") or []:
        col = tokens.get(tok)
        if not col:
            continue
        for kind, size, slice_ in (("bubble", (192, 192), [60, 60, 132, 132]), ("pill", (192, 96), [60, 0, 132, 96]),
                                   ("badge", (128, 128), None), ("banner", (512, 96), [120, 0, 392, 96])):
            out[f"{kind}_{tok}"] = (kind, size, slice_, col)
    for tok, col in tokens.items():
        if tok.startswith("rarity_"):
            out[f"card_{tok[7:]}"] = ("card", (192, 256), [40, 72, 152, 216], col)
    return out


GLINT_FX = ("shimmer", "ping", "split")  # (the runtime fx that need a white copy of their picture: kit/lib/ui.luau "fx")


def fx_glints(ui_dir):
    """{identity: {piece}}: every picture a screen puts a shimmer / ping / split on (its "fx" key) needs a GLINT — a
    white silhouette of the piece (ImageColor3 only darkens a picture, so a sheen must be its own white copy)"""
    out = {}
    if not os.path.isdir(ui_dir):
        return out
    for f in sorted(os.listdir(ui_dir)):
        if not f.endswith(".json") or f.count(".") != 1:
            continue
        try:
            with open(os.path.join(ui_dir, f), encoding="utf-8") as fh:
                spec = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(spec, dict) or not isinstance(spec.get("root"), dict):
            continue
        ident = spec.get("identity")

        def walk(n):
            if not isinstance(n, dict):
                return
            fx = n.get("fx")
            kinds = [e.get("kind") for e in fx if isinstance(e, dict)] if isinstance(fx, list) else []
            img = n.get("image")
            if any(k in GLINT_FX for k in kinds) and isinstance(img, str) and img.startswith("art:"):
                name = img[4:]
                if "/" in name:
                    idn, piece = name.split("/", 1)
                    out.setdefault(idn, set()).add(piece)
                elif ident:
                    out.setdefault(ident, set()).add(name)
            for c in n.get("children") or []:
                walk(c)

        walk(spec["root"])
    return out


def glint(img):
    """the piece's white silhouette: RGB white, the alpha kept (tinted by ImageColor3 in game)"""
    a = img.convert("RGBA").getchannel("A")
    w = Image.new("RGBA", img.size, (255, 255, 255, 0))
    w.putalpha(a)
    return w


def draw_identity(identity, out_dir, art_dir=None, glints=()):
    """draw every plate kind in the identity's shape language; then take in the identity's OWN art files
    (assets/ui/art/<identity>/*.png: generated icons the owner kept, emblems, logos) with the same manifest shape"""
    shape = dict(DEFAULT_SHAPE)
    shape.update(identity.get("shape") or {})
    overrides = identity.get("plates") or {}
    os.makedirs(out_dir, exist_ok=True)
    meta = {}
    for name, (kind, size, slice_) in PLATES.items():
        sh = dict(shape)
        ov = overrides.get(name) or {}
        sh.update({k: v for k, v in ov.items() if k not in ("kind", "size", "slice")})
        kind = ov.get("kind", kind)
        size = tuple(ov.get("size", size))
        slice_ = ov.get("slice", slice_)
        if kind not in KINDS:
            raise ValueError(f"{name}: unknown plate kind {kind} (kinds: {', '.join(KINDS)})")
        img = KINDS[kind](sh, size)
        img.save(os.path.join(out_dir, f"{name}.png"))
        meta[name] = {"size": size[0] if size[0] == size[1] else list(size), "slice": slice_, "opaque": opaque_share(img)}
    for name, (kind, size, slice_, col) in variants(identity, shape).items():
        img = KINDS[kind](shape, tuple(size), col)
        img.save(os.path.join(out_dir, f"{name}.png"))
        meta[name] = {"size": size[0] if size[0] == size[1] else list(size), "slice": slice_, "opaque": opaque_share(img)}
    if art_dir and os.path.isdir(art_dir):
        for f in sorted(os.listdir(art_dir)):
            if not f.lower().endswith(".png"):
                continue
            name = os.path.splitext(f)[0]
            if name in PLATES:
                raise ValueError(f"{art_dir}/{f}: '{name}' is a drawn plate's name — call the file something else")
            im = Image.open(os.path.join(art_dir, f)).convert("RGBA")
            im.save(os.path.join(out_dir, f"{name}.png"))
            meta[name] = {"size": im.width if im.width == im.height else [im.width, im.height], "slice": None, "file": True, "opaque": opaque_share(im)}
        # a BITMAP FONT's metrics (kit/ui/font.py: ink, space, track, kerning, codes) ride in the manifest as
        # "<set>__font", so the compiler can set any text in it
        for f in sorted(os.listdir(art_dir)):
            if f.endswith(".font.json"):
                with open(os.path.join(art_dir, f), encoding="utf-8") as fh:
                    fm = json.load(fh)
                meta[f[: -len(".font.json")] + "__font"] = {"font": {k: fm.get(k) for k in ("cell", "ink", "space", "track", "kern", "codes", "chars")}}
    for name in sorted(glints):
        src = os.path.join(out_dir, f"{name}.png")
        if name in meta and os.path.isfile(src):
            g = glint(Image.open(src))
            g.save(os.path.join(out_dir, f"{name}__glint.png"))
            meta[f"{name}__glint"] = dict(meta[name], file=True, glint_of=name)
    import atlas as _atlas  # (kit/ui/atlas.py: the small pieces packed into sheets, every run)
    ident = os.path.basename(os.path.normpath(out_dir))
    held = set()
    hold_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(art_dir))), "upload.hold.json") if art_dir else None
    if hold_path and os.path.isfile(hold_path):
        with open(hold_path, encoding="utf-8") as fh:
            held = {k.split("/", 1)[1] for k in (json.load(fh).get("hold") or {}) if k.startswith(ident + "/")}
    _atlas.pack(out_dir, meta, held)
    with open(os.path.join(out_dir, "art.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(meta, fh, indent=1)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--identities", default="assets/ui/identities")
    ap.add_argument("--out", default="build/ui/art")
    ap.add_argument("names", nargs="*")
    a = ap.parse_args()
    files = []
    if os.path.isdir(a.identities):
        files = sorted(f for f in os.listdir(a.identities) if f.endswith(".json"))
    if a.names:
        files = [f for f in files if f[:-5] in a.names]
    done, problems = [], []
    glints = fx_glints(os.path.dirname(os.path.abspath(a.identities)))
    for f in files:
        name = f[:-5]
        if not re.match(r"^[A-Za-z0-9_]+$", name):
            problems.append(f"{name}: an identity's file name is letters, digits and _ only (it becomes art:<identity>/<plate>)")
            continue
        try:
            with open(os.path.join(a.identities, f), encoding="utf-8") as fh:
                identity = json.load(fh)
            art_dir = os.path.join(os.path.dirname(os.path.abspath(a.identities)), "art", name)
            meta = draw_identity(identity, os.path.join(a.out, name), art_dir, glints.get(name, ()))
            done.append((name, len(meta)))
        except Exception as e:  # noqa: BLE001 — every identity reports, the run goes on
            problems.append(f"{name}: {e}")
    status = "fail" if problems else "pass"
    summary = f"{len(done)} identit{'y' if len(done) == 1 else 'ies'} drawn (" + ", ".join(f"{n}: {k} plates" for n, k in done) + ")" if done else "no identities (assets/ui/identities/<name>.json)"
    nxt = problems[0] if problems else ("look at " + a.out + "/<identity>/*.png — do the plates belong to one world?" if done else "none")
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": nxt, "identities": [n for n, _ in done], "problems": problems}))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
