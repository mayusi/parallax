"""decals.py - A DECAL'S PICTURE, MADE HERE (kit world decal; the owner's method list: "Decal-based detailing").
A decal is a picture laid on a wall or a floor: a leak under a ledge, a stain, a crack, moss in a corner, soot over a
torch. This makes the picture - by rule, from a seed, nothing downloaded - as an RGBA PNG whose border is fully clear
(a decal whose edge is not clear shows its own square on the wall), and holds it to that before it is written.

   python kit/world/decals.py make <out_dir> --name <Name> --kind leak|stain|crack|moss|soot
                                   [--seed n] [--size 256|512|1024] [--tint r,g,b]

-> <out_dir>/<Name>.png + <Name>.decal.json. It is in a game only once the picture is uploaded and its id stands in the
project's ids file as decals.<Name> (kit/lib/worlddecal.luau reads both).
No blood: a tint that reads as blood is refused (the owner's rule, 2026-10-29)."""
import json
import math
import os
import sys

KINDS = ("leak", "stain", "crack", "moss", "soot")
TINT = {"leak": (46, 40, 33), "stain": (66, 56, 42), "crack": (22, 21, 20), "moss": (58, 84, 40), "soot": (16, 15, 15)}
COVER = {"leak": (0.03, 0.7), "stain": (0.05, 0.7), "crack": (0.003, 0.3), "moss": (0.05, 0.7), "soot": (0.05, 0.7)}
EDGE = 0.12  # (the share of the picture, from each side, over which it fades to nothing)
WORDS = ("--name", "--kind", "--seed", "--size", "--tint")


def bloody(tint):
    """does a colour read as blood: a red or a crimson (its hue within 12 degrees of red on the orange side, 35 on the
    purple side), coloured (saturation 0.35 or more) and not black (its brightest band 30 or more of 255). Rust and
    brick-orange lie further toward orange and pass; a brick red does not.
    The same rule stands in kit/lib/worlddecal.luau (Decal.bloody): one table of colours holds both."""
    r, g, b = (float(c) for c in tint)
    hi, lo = max(r, g, b), min(r, g, b)
    if hi < 30 or hi <= 0 or (hi - lo) / hi < 0.35 or r < hi:
        return False
    hue = 60.0 * (g - b) / (hi - lo)  # (red is the brightest band: -60 .. 60, 0 = pure red, under 0 toward purple)
    return -35.0 <= hue <= 12.0


def arguments(argv):
    """the command's words -> (settings, None) or (None, why)"""
    use = "usage: make <out_dir> --name <Name> --kind leak|stain|crack|moss|soot [--seed n] [--size 256|512|1024] [--tint r,g,b]"
    if len(argv) < 2 or argv[0] != "make" or argv[1].startswith("--"):
        return None, use
    s = {"out": argv[1], "name": None, "kind": None, "seed": 1, "size": 512, "tint": None}
    k = 2
    said = set()
    while k < len(argv):
        word = argv[k]
        if word not in WORDS or k + 1 >= len(argv):
            return None, f"decal: {word} is not a word it knows ({', '.join(WORDS)}), or has no value"
        value = argv[k + 1]
        k += 2
        if word in said:
            return None, f"decal: {word} is said twice"
        said.add(word)
        if word == "--name":
            if not value or not all((c.isascii() and c.isalnum()) or c == "_" for c in value):
                return None, f"decal: --name is the decal's name (letters, digits, _) (got {value})"
            s["name"] = value
        elif word == "--kind":
            if value not in KINDS:
                return None, f"decal: --kind is one of {', '.join(KINDS)} (got {value})"
            s["kind"] = value
        else:
            try:
                numbers = [float(v) for v in value.split(",")]
            except ValueError:
                return None, f"decal: {word} is a number (got {value})"
            if any(n != n or n in (math.inf, -math.inf) or n % 1 != 0 for n in numbers):
                return None, f"decal: {word} is a whole number (got {value})"
            if word == "--tint":
                if len(numbers) != 3 or any(not 0 <= n <= 255 for n in numbers):
                    return None, f"decal: --tint is r,g,b, each 0 to 255 (got {value})"
                s["tint"] = tuple(int(n) for n in numbers)
            elif len(numbers) != 1:
                return None, f"decal: {word} is one number (got {value})"
            elif word == "--seed":
                if not 0 <= numbers[0] <= 65535:
                    return None, f"decal: --seed is a whole number 0 to 65535 (got {value})"
                s["seed"] = int(numbers[0])
            else:
                if numbers[0] not in (256, 512, 1024):
                    return None, f"decal: --size is 256, 512 or 1024 (got {value})"
                s["size"] = int(numbers[0])
    if s["name"] is None:
        return None, "decal: --name says what the decal is called"
    if s["kind"] is None:
        return None, f"decal: --kind says what it is ({', '.join(KINDS)})"
    if s["tint"] is None:
        s["tint"] = TINT[s["kind"]]
    if bloody(s["tint"]):
        return None, f"decal: the tint {s['tint']} reads as blood: not made (no blood or gore in this kit)"
    return s, None


def noise(rng, n, cells, octaves=4):
    """smooth noise 0..1 on an n x n picture: random grids of `cells` and finer, each drawn up to the picture's size"""
    import numpy as np
    from PIL import Image

    out = np.zeros((n, n))
    total = 0.0
    for o in range(octaves):
        c = max(2, cells * 2 ** o)
        grid = (rng.random((c, c)) * 255).astype(np.uint8)
        out += np.asarray(Image.fromarray(grid, "L").resize((n, n), Image.BICUBIC), dtype=float) / 255.0 * 0.5 ** o
        total += 0.5 ** o
    return np.clip(out / total, 0, 1)


def window(n):
    """the fade to nothing at the picture's four sides: 0 on the border, 1 inside (a smooth step over EDGE)"""
    import numpy as np

    t = np.clip((np.arange(n) + 0.5) / n / EDGE, 0, 1)
    t = np.minimum(t, t[::-1])
    w = t * t * (3 - 2 * t)
    w[:2] = 0.0
    w[-2:] = 0.0
    return np.outer(w, w)


def alpha(kind, seed, n):
    """how much of the decal lies at each pixel, 0..1, [row (0 = the top), column], before the border's fade"""
    import numpy as np

    rng = np.random.default_rng(seed * 7919 + KINDS.index(kind))
    v, u = np.meshgrid((np.arange(n) + 0.5) / n, (np.arange(n) + 0.5) / n, indexing="ij")  # (v down, u right)
    grain = noise(rng, n, 6)
    if kind == "leak":
        # water ran down from the top: streaks of their own width and length, widest where they start
        a = np.zeros((n, n))
        for _ in range(int(rng.integers(3, 7))):
            x0, width, length = rng.uniform(0.25, 0.75), rng.uniform(0.02, 0.07), rng.uniform(0.45, 0.95)
            drift = (noise(rng, n, 3, 2)[:, 0] - 0.5) * 0.08
            centre = x0 + drift[:, None] * v
            run = np.clip(1 - v / length, 0, 1)
            a = np.maximum(a, np.exp(-((u - centre) / (width * (0.4 + 0.6 * run) + 1e-6)) ** 2) * run ** 0.7)
        band = np.exp(-((v - 0.1) / 0.06) ** 2) * np.clip(1 - np.abs(u - 0.5) / 0.42, 0, 1)  # (where it gathered)
        return np.clip(np.maximum(a, band * 0.8) * (0.55 + 0.6 * grain), 0, 1)
    if kind == "stain":
        # a blotch with a ragged rim, darker at its tide line
        r = np.hypot(u - 0.5, v - 0.5) / (0.3 + 0.12 * (noise(rng, n, 4) - 0.5) * 2)
        body = np.clip(1.15 - r, 0, 1) ** 0.6
        rim = np.exp(-((r - 0.95) / 0.07) ** 2)
        return np.clip((0.45 * body + 0.55 * rim * body ** 0.3) * (0.6 + 0.6 * grain), 0, 1)
    if kind == "moss":
        # clumps: where the noise is high, thicker toward the middle
        r = np.hypot(u - 0.5, v - 0.5)
        clumps = noise(rng, n, 7) * (1.15 - 1.5 * r)
        return np.clip((clumps - 0.38) / 0.16, 0, 1) * (0.7 + 0.3 * grain)
    if kind == "soot":
        # smoke rose from the bottom: narrow and darkest where it began, wider and thinner upward
        rise = np.clip(1 - v, 0, 1)
        centre = 0.5 + (noise(rng, n, 3, 2)[:, 0][:, None] - 0.5) * 0.1
        width = 0.06 + 0.2 * rise
        return np.clip(np.exp(-((u - centre) / width) ** 2) * np.clip(1.25 - 1.1 * rise, 0, 1) ** 1.5 * (0.6 + 0.5 * grain), 0, 1)
    # crack: a few walks from near the middle, each branching once or twice, drawn four times larger and brought down
    from PIL import Image, ImageDraw

    big = n * 4
    img = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(img)
    starts = [(rng.uniform(0.4, 0.6), rng.uniform(0.4, 0.6), rng.uniform(0, 2 * math.pi), 3.2) for _ in range(int(rng.integers(2, 4)))]
    walks = 0
    while starts and walks < 14:
        x, y, heading, width = starts.pop()
        walks += 1
        for step in range(int(rng.integers(18, 40))):
            heading += rng.normal(0, 0.12)  # (a crack runs on: it wanders a little and now and then kinks)
            if rng.random() < 0.1:
                heading += rng.choice((-1, 1)) * rng.uniform(0.4, 0.9)
            nx, ny = x + math.cos(heading) * 0.018, y + math.sin(heading) * 0.018
            draw.line((x * big, y * big, nx * big, ny * big), fill=255, width=max(1, int(round(width * big / 512))))
            x, y = nx, ny
            if width > 1.4 and rng.random() < 0.06:
                starts.append((x, y, heading + rng.choice((-1, 1)) * rng.uniform(0.5, 1.1), width * 0.6))
            width = max(1.0, width * 0.985)
    return np.asarray(img.resize((n, n), Image.LANCZOS), dtype=float) / 255.0


def picture(kind, seed, n, tint):
    """the decal -> an RGBA array [n, n, 4] uint8: the tint, a little uneven, under the alpha with its border faded"""
    import numpy as np

    a = alpha(kind, seed, n) * window(n)
    rng = np.random.default_rng(seed * 104729 + 17)
    shade = 0.8 + 0.4 * noise(rng, n, 9, 3)
    out = np.zeros((n, n, 4), dtype=np.uint8)
    for k in range(3):
        out[..., k] = np.clip(tint[k] * shade, 0, 255).astype(np.uint8)
    out[..., 3] = np.clip(a * 255 * 0.92, 0, 255).astype(np.uint8)
    return out


def judged(rgba, kind):
    """a decal's picture held to what a decal must be -> (what is wrong: a list, what was measured)"""
    import numpy as np

    a = rgba[..., 3].astype(float) / 255.0
    n = a.shape[0]
    frame = np.concatenate([a[:2].ravel(), a[-2:].ravel(), a[:, :2].ravel(), a[:, -2:].ravel()])
    cover = float((a > 0.1).mean())
    third = n // 3
    top, bottom = float(a[:third].mean()), float(a[-third:].mean())
    measured = {"cover": round(cover, 4), "border": round(float(frame.max()), 4), "top": round(top, 4), "bottom": round(bottom, 4),
                "strongest": round(float(a.max()), 3)}
    wrong = []
    if frame.max() > 0:
        wrong.append(f"its border is not clear (alpha {frame.max():.2f} on the picture's edge): the decal's square would show")
    lo, hi = COVER[kind]
    if not lo <= cover <= hi:
        wrong.append(f"it covers {cover * 100:.1f} % of its picture: a {kind} covers {lo * 100:g} to {hi * 100:g} %")
    if a.max() < 0.5:
        wrong.append(f"its strongest spot is {a.max():.2f} of solid: too faint to be seen on a wall")
    if kind == "leak" and top <= bottom:
        wrong.append("a leak is heavier at its top than at its foot, and this one is not")
    if kind == "soot" and bottom <= top:
        wrong.append("soot is heavier at its foot than at its top, and this is not")
    rgb = rgba[..., :3][a > 0.1]
    if rgb.size and bloody(tuple(float(c) for c in rgb.mean(axis=0))):
        wrong.append("it reads as blood (no blood or gore in this kit)")
    return wrong, measured


def make(s):
    from PIL import Image

    rgba = picture(s["kind"], s["seed"], s["size"], s["tint"])
    wrong, measured = judged(rgba, s["kind"])
    png = os.path.join(s["out"], s["name"] + ".png")
    record_path = os.path.join(s["out"], s["name"] + ".decal.json")
    for old in (png, record_path):  # (nothing of an earlier decal of this name is left to be taken for this one)
        if os.path.isfile(old):
            os.remove(old)
    if wrong:
        return None, f"decal: {s['name']} was not made: " + "; ".join(wrong)
    os.makedirs(s["out"], exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(png)
    record = {"name": s["name"], "kind": s["kind"], "seed": s["seed"], "size": s["size"], "tint": list(s["tint"]),
              "file": s["name"] + ".png", "checked": measured}
    with open(record_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(record, fh, indent=1)
    return record, None


def main(argv):
    s, why = arguments(argv)
    if why:
        print(json.dumps({"status": "fail", "summary": why, "next_action": "fix the words and run it again"}))
        return 2
    try:
        record, why = make(s)
    except Exception as e:  # noqa: BLE001 - one verdict line whatever went wrong
        record, why = None, f"decal: {e}"
    if why:
        print(json.dumps({"status": "fail", "summary": why, "next_action": "another --seed, or another --tint"}))
        return 1
    c = record["checked"]
    print(json.dumps({"status": "pass",
                      "summary": f"decal: {s['name']}: a {s['kind']} of {s['size']} px, covering {c['cover'] * 100:.0f} % of its picture, "
                                 f"its border clear -> {os.path.join(s['out'], record['file']).replace(os.sep, '/')}",
                      "next_action": "LOOK at the picture; it is in a game only once it is uploaded",
                      "record": record}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
