#!/usr/bin/env python3
"""A LENS FLARE that behaves like one (the owner's methods list: Lens flare, Anamorphic effects; the VFX methods audit).

Until now the kit's "flare" was a drawn star texture and speed streaks: marks that sit still on the screen. A real
flare is the LENS answering a light: a glow where the light is, a long level streak through it (the anamorphic lens),
and a string of GHOSTS on the straight line from the light through the middle of the screen - near the light on its
side, mirrored on the far side - that swing as the light or the camera moves. Roblox has no lens flare; the `lens`
layer draws one as pictures placed every frame (src/kit/VfxStage.luau `flareMarks`; the browser player's
`flareMarks`, the same rule), from where the layer's `point` falls on the screen.

    lune run kit vfx flare [--light 0.25,0.3] [--aspect 1.778] [--ghosts 5] [--size 0.18] [--streak 0.6] [--squeeze 1.6]
                           [--color 255,220,170] [--out build/vfx/flare/look.png]

draws where the marks fall for a light at that place of the screen (0,0 = top left, 1,1 = bottom right), on black, and
says what it checked. It makes nothing a preset reads: the look picture is for the eye (OPEN it), the layer is

    {"kind": "lens", "point": ..., "flare": {"strength": 0.8, "ghosts": 5, "size": 0.18, "streak": 0.6, "squeeze": 1.6,
                                             "color": [255, 220, 170]}}

and its three pictures are made once a project by `python kit/vfx/lens.py lens_glow lens_ghost lens_streak`.

THE RULE (`marks`; the game's and the player's are held to it by kit/selftest/vfx/flare/run.py parity):
- sizes are shares of the screen's HEIGHT (`w` too: the caller divides by the aspect for a share of the width);
- the glow sits on the light, `size` across; the streak sits on the light, `streak` screen WIDTHS long, level;
- ghost i sits at light + (middle - light) * K[i]: K below 1 is on the light's side, above 1 past the middle;
  `squeeze` (1..3) makes ghosts wider than tall, as an anamorphic lens does;
- everything fades out as the light leaves the screen (gone 15 % of the screen past the edge); behind the camera the
  caller draws nothing.

What it checks (`check`): the glow is on the light; every ghost is on the line through the light and the middle;
ghosts lie on BOTH sides of the middle (five or more); nothing is drawn for a light well off the screen; the streak
is level and longer than it is tall.

Not built: the light being hidden by something in front of it (no occlusion test), a flare for more than one light a
layer, real bloom. Roblox draws the pictures alpha-blended, not added: a flare over a bright sky reads weaker than in
a film.
"""
import json
import math
import os
import sys

# where each ghost sits along the line (0 = the light, 1 = the middle of the screen, 2 = the light mirrored), how big
# it is against `size`, and how strong - the SAME three lists as VfxStage.luau and player.js (the parity case)
K = [0.35, 0.62, 0.9, 1.25, 1.6, 1.85, 2.1, 2.4]
S = [0.22, 0.4, 0.16, 0.6, 0.3, 0.9, 0.25, 0.5]
A = [0.5, 0.35, 0.6, 0.25, 0.4, 0.18, 0.45, 0.2]
GONE = 0.3  # the flare is gone when the light is this far past the screen's edge (of the half screen)
LOOK = os.path.join("build", "vfx", "flare", "look.png")


def marks(lx, ly, aspect, f):
    """the pictures of one flare for a light at (lx, ly) of the screen -> [{kind: 1 glow | 2 streak | 3 ghost, i, x, y,
    w, h (shares of the screen's height), a (0..1), c (0..1 along the colour)}]"""
    size = f.get("size", 0.18)
    n = max(0, min(8, int(math.floor(f.get("ghosts", 5)))))
    streak = f.get("streak", 0)
    squeeze = max(1.0, min(3.0, f.get("squeeze", 1)))
    d = max(abs(lx - 0.5), abs(ly - 0.5)) * 2
    vis = 1.0 if d <= 1 else (0.0 if d >= 1 + GONE else 1 - (d - 1) / GONE)
    if vis <= 0:
        return []
    out = [{"kind": 1, "i": 0, "x": lx, "y": ly, "w": size, "h": size, "a": vis, "c": 0.0}]
    if streak > 0:
        out.append({"kind": 2, "i": 0, "x": lx, "y": ly, "w": streak * aspect, "h": size * 0.35, "a": vis * 0.9, "c": 0.0})
    for i in range(1, n + 1):
        s = size * S[i - 1]
        out.append({"kind": 3, "i": i, "x": lx + (0.5 - lx) * K[i - 1], "y": ly + (0.5 - ly) * K[i - 1], "w": s * squeeze, "h": s,
                    "a": vis * A[i - 1], "c": i / n})
    return out


def check(found, lx, ly, f):
    """-> [{name, ok, value, limit, fix}] for one flare's marks"""
    rows = []

    def add(name, ok, value, limit, fix):
        rows.append({"name": name, "ok": bool(ok), "value": value, "limit": limit, "fix": fix})

    glow = [m for m in found if m["kind"] == 1]
    ghosts = [m for m in found if m["kind"] == 3]
    streak = [m for m in found if m["kind"] == 2]
    d = max(abs(lx - 0.5), abs(ly - 0.5)) * 2
    if d >= 1 + GONE:
        add("gone", not found, len(found), "0 marks for a light well off the screen", "a flare whose light is not in the picture is a mark with no cause")
        return rows
    add("glow", len(glow) == 1 and math.hypot(glow[0]["x"] - lx, glow[0]["y"] - ly) < 1e-6 if glow else False, len(glow), "one glow, on the light",
        "the glow is the light seen through the lens: it sits on the light")
    # a ghost off the line through the light and the middle is not a flare's ghost (the line swings with the light)
    off = 0.0
    ax, ay = 0.5 - lx, 0.5 - ly
    span = math.hypot(ax, ay)
    for m in ghosts:
        bx, by = m["x"] - lx, m["y"] - ly
        off = max(off, abs(ax * by - ay * bx) / span if span > 1e-9 else math.hypot(bx, by))
    add("axis", off < 1e-6, round(off, 6), "every ghost on the line from the light through the middle (< 0.000001 of the screen)",
        "ghosts are reflections inside the lens: they lie on the line through the light and the middle of the picture")
    if len(ghosts) >= 5 and span > 1e-6:
        side = [(m["x"] - 0.5) * ax + (m["y"] - 0.5) * ay for m in ghosts]
        add("both_sides", any(v < 0 for v in side) and any(v > 0 for v in side), [sum(1 for v in side if v < 0), sum(1 for v in side if v > 0)],
            "ghosts on the light's side AND past the middle", "a flare's ghosts are strung across the picture, not bunched at the light")
    if f.get("streak", 0) > 0:
        add("streak", len(streak) == 1 and streak[0]["w"] > streak[0]["h"] * 2 if streak else False, [round(m["w"], 3) for m in streak] + [round(m["h"], 3) for m in streak],
            "one level streak, over twice as long as its picture is tall (the line inside it is a sixth of that)", "the anamorphic streak is a long thin line through the light")
    add("fades", all(0 <= m["a"] <= 1 for m in found), [round(m["a"], 3) for m in found][:4], "every strength from 0 to 1", "a strength outside 0..1")
    return rows


def look(found, aspect, color, path, height=540):
    """the marks drawn on black (added light), as wide as the aspect says"""
    import numpy as np
    from PIL import Image
    width = int(round(height * aspect))
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float64)
    img = np.zeros((height, width, 3))
    for m in found:
        cx, cy, hw, hh = m["x"] * width, m["y"] * height, m["w"] * height / 2, m["h"] * height / 2
        r = np.sqrt(((xx - cx) / max(hw, 1e-6)) ** 2 + ((yy - cy) / max(hh, 1e-6)) ** 2)
        if m["kind"] == 3:
            shape = np.clip(1 - r, 0, 1) ** 0.5 * 0.5 + np.exp(-((r - 0.86) / 0.07) ** 2) * 0.5 * (r < 1)
        else:
            shape = np.clip(1 - r, 0, 1) ** 2
        tint = np.asarray(color, dtype=np.float64) / 255 * (1 - 0.35 * m["c"]) + np.asarray([0.2, 0.5, 1.0]) * 0.35 * m["c"]
        img += shape[..., None] * tint * m["a"]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    Image.fromarray((np.clip(img, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8), "RGB").save(path)


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status == "pass" else 1


def numbers(text, count, name):
    try:
        got = [float(v) for v in str(text).split(",")]
    except ValueError:
        got = []
    if len(got) != count or not all(math.isfinite(v) for v in got):
        raise ValueError(f"{name} is {count} number(s) with commas")
    return got


def main(argv):
    usage = "lune run kit vfx flare [--light x,y] [--aspect 1.778] [--ghosts 5] [--size 0.18] [--streak 0.6] [--squeeze 1.6] [--color r,g,b] [--out file.png]"
    o = {"--light": "0.25,0.3", "--aspect": "1.778", "--ghosts": "5", "--size": "0.18", "--streak": "0.6", "--squeeze": "1", "--color": "255,220,170", "--out": LOOK}
    i = 0
    while i < len(argv):
        if argv[i] not in o or i + 1 >= len(argv):
            return out("fail", f"flare: {argv[i]} is not an option of it (or has no value)", usage)
        o[argv[i]] = argv[i + 1]
        i += 2
    try:
        lx, ly = numbers(o["--light"], 2, "--light")
        aspect = numbers(o["--aspect"], 1, "--aspect")[0]
        color = numbers(o["--color"], 3, "--color")
        f = {"ghosts": numbers(o["--ghosts"], 1, "--ghosts")[0], "size": numbers(o["--size"], 1, "--size")[0],
             "streak": numbers(o["--streak"], 1, "--streak")[0], "squeeze": numbers(o["--squeeze"], 1, "--squeeze")[0]}
        if not 0.5 <= aspect <= 4:
            raise ValueError("--aspect is the screen's width over its height, 0.5 to 4")
        if not (0 <= f["ghosts"] <= 8 and 0.01 <= f["size"] <= 1 and 0 <= f["streak"] <= 2 and 1 <= f["squeeze"] <= 3):
            raise ValueError("--ghosts 0..8, --size 0.01..1, --streak 0..2, --squeeze 1..3")
        if not all(0 <= c <= 255 for c in color):
            raise ValueError("--color is r,g,b from 0 to 255")
    except ValueError as e:
        return out("fail", f"flare: {e}", usage)
    found = marks(lx, ly, aspect, f)
    checks = check(found, lx, ly, f)
    failed = [c for c in checks if not c["ok"]]
    if failed:
        said = "; ".join(f"{c['name']} = {c['value']} (needs {c['limit']})" for c in failed)
        return out("fail", f"flare: {said}", failed[0]["fix"], checks=checks)
    if not found:
        return out("pass", f"flare: a light at {lx:g},{ly:g} is off the screen: nothing is drawn (as it should be)", "a --light inside 0..1 shows the flare", checks=checks, marks=0)
    look(found, aspect, color, o["--out"])
    return out("pass", f"flare: a light at {lx:g},{ly:g} draws {len(found)} marks ({sum(1 for m in found if m['kind'] == 3)} ghosts on the line through the middle)",
               f"OPEN {o['--out'].replace(os.sep, '/')}: is this the lens answering THIS light? On a lens layer: \"flare\": {{...}} (kit/skills/parallax-vfx/reference/23-*)",
               checks=checks, marks=len(found), look=o["--out"].replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
