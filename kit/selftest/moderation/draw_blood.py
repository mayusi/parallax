"""draw_blood.py - the moderation gate's BAD fixtures, drawn here (never real gore, never uploaded).
Never uploaded, never used in a game: they exist so `kit selftest` proves kit/tools/mod_gate.py holds them back.
  pool.png     - one dark-red pool with a lit rim on a clear background (what most of the 17 decals were)
  splat.png    - a spray of separate dark-red drops of many sizes on a clear background
  ember.png    - the GOOD control: an orange-yellow fire puff with a red-orange edge (a VFX texture's colours)
Usage: python -I draw_blood.py <out folder>. Never "fix" this file to make a gate pass."""

import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter


def pool(path):
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rnd = random.Random(7)
    pts = []
    for i in range(48):
        a = i / 48 * 2 * math.pi
        r = 170 + rnd.uniform(-35, 35)
        pts.append((256 + r * math.cos(a), 256 + 0.8 * r * math.sin(a)))
    d.polygon(pts, fill=(110, 8, 12, 255))
    d.ellipse((150, 170, 300, 260), fill=(150, 16, 20, 255))
    im = im.filter(ImageFilter.GaussianBlur(1.5))
    im.save(path)


def splat(path):
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rnd = random.Random(11)
    d.ellipse((200, 200, 312, 300), fill=(120, 10, 14, 255))
    for _ in range(40):
        a = rnd.uniform(0, 2 * math.pi)
        dist = rnd.uniform(70, 230)
        x, y = 256 + dist * math.cos(a), 250 + dist * math.sin(a)
        s = rnd.uniform(4, 22)
        d.ellipse((x - s, y - s * 0.8, x + s, y + s * 0.8), fill=(rnd.randint(95, 160), 8, 14, 255))
    im.save(path)


def ember(path):
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    px = im.load()
    for y in range(512):
        for x in range(512):
            r = math.hypot(x - 256, y - 256) / 220.0
            if r < 1.0:
                t = 1.0 - r
                px[x, y] = (255, int(90 + 165 * t), int(20 + 150 * t * t), int(255 * min(1.0, t * 2.5)))
    im.save(path)


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    pool(os.path.join(out, "pool.png"))
    splat(os.path.join(out, "splat.png"))
    ember(os.path.join(out, "ember.png"))
    print(out)
