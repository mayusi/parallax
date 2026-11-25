"""art.py — the UI art every game needs, drawn in code (Pillow), white-on-transparent so ImageColor3 tints it.

    python kit/ui/art.py --out build/ui/art

Writes build/ui/art/<name>.png + art.json ({name: {size, slice}}). `kit upload` puts them on Roblox (ids.ui.<name>);
screen specs reference them as "image": "art:<name>" (the compiler resolves the id; the preview draws the PNG).

    ring        thick circle outline              cooldown rings (two-half gradient trick), selection circles
    disc        soft-edged filled circle          dots, pips, radial glows behind icons
    glow        radial falloff                    behind buttons / pickups / crosshair bloom
    vignette    dark edges, clear middle          damage flash, low health, focus
    scope_mask  black with a clear circular lens  sniper scopes (stretch to the screen; ScaleType Fit keeps it round)
    reticle     mil-dot crosshair with stadia     sniper reticle (drawn on a transparent 1024 canvas)
    panel       rounded rect, top highlight       9-slice panels/buttons (slice centre given in art.json)
    panel_line  rounded rect OUTLINE only         9-slice frames / sci-fi borders
    corner      L-shaped bracket                  sci-fi corner brackets (rotate 0/90/180/270)
    keycap      rounded key with a bottom lip     key hints: [E] Interact, [RMB] Scope
    gradient_v  white -> transparent, vertical    fades, light sweeps, panel sheen
    stripes     diagonal hazard stripes           warning bars, locked slots
    spark       four-point star                   UI particles (Ui.burst presets)
    shard       a sharp sliver                    UI particles: a hit's flying flecks
Everything is supersampled 4x then downscaled: anti-aliased edges, no jaggies.
"""

import argparse
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter

SS = 4  # supersampling


def canvas(n):
    return Image.new("RGBA", (n * SS, n * SS), (255, 255, 255, 0))


def down(img, n):
    return img.resize((n, n), Image.LANCZOS)


def ring(n=256, width=0.12):
    img = canvas(n)
    d = ImageDraw.Draw(img)
    pad = 2 * SS
    w = int(n * SS * width)
    d.ellipse([pad, pad, n * SS - pad, n * SS - pad], outline=(255, 255, 255, 255), width=w)
    return down(img, n)


def disc(n=128, soft=0.18):
    img = canvas(n)
    d = ImageDraw.Draw(img)
    pad = int(n * SS * soft * 0.5)
    d.ellipse([pad, pad, n * SS - pad, n * SS - pad], fill=(255, 255, 255, 255))
    return down(img.filter(ImageFilter.GaussianBlur(n * SS * soft * 0.25)), n)


def radial(n, fn):
    img = Image.new("RGBA", (n, n), (255, 255, 255, 0))
    px = img.load()
    c = (n - 1) / 2
    for y in range(n):
        for x in range(n):
            r = math.hypot(x - c, y - c) / c
            px[x, y] = (255, 255, 255, max(0, min(255, int(255 * fn(r)))))
    return img


def glow(n=256):
    return radial(n, lambda r: (1 - min(r, 1)) ** 2.2)


def vignette(n=512):
    return radial(n, lambda r: max(0.0, (r - 0.55) / 0.6) ** 1.6 * 0.95)


def scope_mask(n=1024):
    # opaque black outside a circle, a soft dark rim inside the lens; tint with ImageColor3 (keep black)
    def fn(r):
        if r > 0.94:
            return 1.0
        if r > 0.86:
            return 0.55 + (r - 0.86) / 0.08 * 0.45  # the dark tube rim
        return max(0.0, (r - 0.62) / 0.24) ** 2 * 0.5  # lens edge darkening
    img = radial(n, fn)
    return Image.merge("RGBA", (*(Image.new("L", (n, n), 0),) * 3, img.getchannel("A")))


def reticle(n=1024):
    img = canvas(n)
    d = ImageDraw.Draw(img)
    S = n * SS
    c = S / 2
    thin, thick = max(2, int(S * 0.0016)), max(4, int(S * 0.0055))
    gap = S * 0.012
    # thick posts from the edge, thin wires in the middle
    for a, b in (((0, c), (S * 0.30, c)), ((S, c), (S * 0.70, c)), ((c, S), (c, S * 0.70))):
        d.line([a, b], fill=(255, 255, 255, 255), width=thick)
    d.line([(c, 0), (c, S * 0.30)], fill=(255, 255, 255, 255), width=thick)
    for a, b in (((S * 0.30, c), (c - gap, c)), ((c + gap, c), (S * 0.70, c)), ((c, S * 0.30), (c, c - gap)), ((c, c + gap), (c, S * 0.70))):
        d.line([a, b], fill=(255, 255, 255, 255), width=thin)
    # mil dots
    for k in range(1, 5):
        off = k * S * 0.04
        rr = S * 0.0045
        for (x, y) in ((c + off, c), (c - off, c), (c, c + off), (c, c - off)):
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(255, 255, 255, 255))
    # bullet-drop stadia below the centre
    for k in range(1, 4):
        y = c + k * S * 0.05
        hw = S * (0.03 - k * 0.006)
        d.line([(c - hw, y), (c + hw, y)], fill=(255, 255, 255, 255), width=thin)
    rr = S * 0.003
    d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=(255, 255, 255, 255))
    return down(img, n)


def panel(n=128, radius=0.22):
    img = canvas(n)
    d = ImageDraw.Draw(img)
    S = n * SS
    r = int(S * radius)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=r, fill=(255, 255, 255, 255))
    # top highlight band (lighter) — reads as a lit surface once tinted
    hl = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(hl).rounded_rectangle([SS * 2, SS * 2, S - SS * 2, S * 0.5], radius=r, fill=(255, 255, 255, 40))
    out = down(img, n)
    # darken the lower half slightly (multiply) for a subtle gradient
    px = out.load()
    for y in range(n):
        k = 1 - 0.18 * (y / n)
        for x in range(n):
            p = px[x, y]
            px[x, y] = (int(p[0] * k), int(p[1] * k), int(p[2] * k), p[3])
    return out


def panel_line(n=128, radius=0.22, width=0.05):
    img = canvas(n)
    d = ImageDraw.Draw(img)
    S = n * SS
    d.rounded_rectangle([SS, SS, S - SS, S - SS], radius=int(S * radius), outline=(255, 255, 255, 255), width=int(S * width))
    return down(img, n)


def corner(n=64, width=0.14, length=0.8):
    img = canvas(n)
    d = ImageDraw.Draw(img)
    S = n * SS
    w = int(S * width)
    d.rectangle([0, 0, int(S * length), w], fill=(255, 255, 255, 255))
    d.rectangle([0, 0, w, int(S * length)], fill=(255, 255, 255, 255))
    return down(img, n)


def keycap(n=128):
    img = canvas(n)
    d = ImageDraw.Draw(img)
    S = n * SS
    r = int(S * 0.2)
    d.rounded_rectangle([0, int(S * 0.06), S - 1, S - 1], radius=r, fill=(150, 150, 150, 255))  # lip (darker)
    d.rounded_rectangle([0, 0, S - 1, int(S * 0.9)], radius=r, fill=(255, 255, 255, 255))
    return down(img, n)


def gradient_v(n=256):
    img = Image.new("RGBA", (n, n), (255, 255, 255, 0))
    px = img.load()
    for y in range(n):
        a = int(255 * (1 - y / (n - 1)))
        for x in range(n):
            px[x, y] = (255, 255, 255, a)
    return img


def stripes(n=128):
    img = canvas(n)
    d = ImageDraw.Draw(img)
    S = n * SS
    step = S // 4
    for k in range(-4, 9):
        x = k * step
        d.polygon([(x, S), (x + step // 2, S), (x + step // 2 + S, 0), (x + S, 0)], fill=(255, 255, 255, 255))
    return down(img, n)


# name -> (builder, size, 9-slice centre [left, top, right, bottom] in pixels or None)
def spark(n=64):
    """a four-point star with a hot core: the UI particle (Ui.burst presets tint it)"""
    img = canvas(n)
    d = ImageDraw.Draw(img)
    c, r, w = n * SS / 2, n * SS / 2 - SS, n * SS * 0.11
    d.polygon([(c, c - r), (c + w, c - w), (c + r, c), (c + w, c + w), (c, c + r), (c - w, c + w), (c - r, c), (c - w, c - w)],
              fill=(255, 255, 255, 255))
    return down(img, n)


def shard(n=64):
    """a sharp sliver (a comic hit's flying fleck): long, thin, pointed at both ends"""
    img = canvas(n)
    d = ImageDraw.Draw(img)
    c = n * SS / 2
    d.polygon([(c, SS), (c + n * SS * 0.13, c), (c, n * SS - SS), (c - n * SS * 0.13, c)], fill=(255, 255, 255, 255))
    return down(img, n)


ART = {
    "ring": (ring, 256, None),
    "disc": (disc, 128, None),
    "glow": (glow, 256, None),
    "vignette": (vignette, 512, None),
    "scope_mask": (scope_mask, 1024, None),
    "reticle": (reticle, 1024, None),
    "panel": (panel, 128, [32, 32, 96, 96]),
    "panel_line": (panel_line, 128, [32, 32, 96, 96]),
    "corner": (corner, 64, None),
    "keycap": (keycap, 128, [30, 30, 98, 90]),
    "gradient_v": (gradient_v, 256, None),
    "stripes": (stripes, 128, None),
    "spark": (spark, 64, None),
    "shard": (shard, 64, None),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    made = 0
    meta = {}
    for name, (fn, size, sl) in ART.items():
        path = os.path.join(a.out, f"{name}.png")
        meta[name] = {"size": size, "slice": sl}
        if os.path.isfile(path) and not a.force:
            continue
        fn(size).save(path)
        made += 1
    with open(os.path.join(a.out, "art.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"ui art: {len(ART)} piece(s), {made} drawn", "next_action": "none — proceed"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
