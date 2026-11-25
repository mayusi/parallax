"""strip.py — the TIME STRIP of a clip: `python kit/anim/strip.py build/animations/<Name>.clip.json [--gif] [--columns N]`

Columns are the authored keys and every event (or N frames evenly spaced); rows are FRONT (its right arm on YOUR left),
SIDE (the character faces right) and THREE-QUARTER (from its front-right). Each cell draws the pose as the engine-read
rig's boxes, the previous column as an onion skin, and the hands' and feet's arcs over the WHOLE clip with a dot at
this frame — so timing, arcs and silhouette are judged in one look. Under the rows: a timeline with the keys, the
events and the beats. --gif also writes <Name>.gif: every frame, the three views side by side (motion for a judge).
Output: <Name>.png next to the clip, and a verdict line for `kit anim`.
"""

import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip as C  # noqa: E402

CELL, SCALE = 200, 22
MAX_COLUMNS = 12
QUARTER = math.radians(35)
BG, GRID, TEXT, DIM = (20, 22, 28), (50, 54, 64), (220, 220, 220), (140, 140, 150)
ARC = {"RightHand": (255, 110, 100), "LeftHand": (255, 190, 110), "RightFoot": (110, 230, 160),
       "LeftFoot": (190, 160, 255), "Right Arm": (255, 110, 100), "Left Arm": (255, 190, 110),
       "Right Leg": (110, 230, 160), "Left Leg": (190, 160, 255)}


def part_color(name):
    if "Head" in name:
        return (235, 205, 160)
    if "Torso" in name:
        return (90, 140, 220)
    right = name.startswith("Right")
    if "Arm" in name or "Hand" in name:
        return (230, 90, 80) if right else (240, 160, 70)
    if "Leg" in name or "Foot" in name:
        return (80, 180, 120) if right else (150, 120, 220)
    return (170, 170, 180)


def project(p, view):
    """root-space (x, y, z) -> (screen x, screen y, depth): y up on screen, nearer the camera = larger depth"""
    x, y, z = float(p[0]), float(p[1]), float(p[2])
    if view == "front":   # camera in front (at -Z) looking +Z: screen right = world -X
        return -x, y, -z
    if view == "side":    # camera on the character's right (+X) looking -X: screen right = -Z (forward)
        return -z, y, x
    c, s = math.cos(QUARTER), math.sin(QUARTER)  # the world yawed so the camera sits front-right
    xr, zr = x * c + z * s, -x * s + z * c
    return -xr, y, -zr


def hull(points):
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def to_screen(sx, sy, ox, oy, cy):
    return ox + CELL / 2 + sx * SCALE, oy + CELL / 2 + cy * SCALE - sy * SCALE


def body_polys(rig, world, view):
    """[(depth, part, screen polygon)] back to front"""
    out = []
    for part in rig["order"]:
        pts = [project(c, view) for c in C.corners(rig, part, world[part])]
        poly = hull([(round(a, 4), round(b, 4)) for a, b, _ in pts])
        out.append((sum(d for _, _, d in pts) / len(pts), part, poly))
    return sorted(out, key=lambda t: t[0])


def draw_pose(draw, ox, oy, cy, rig, world, view, ghost=False):
    for _, part, poly in body_polys(rig, world, view):
        pts = [to_screen(x, y, ox, oy, cy) for x, y in poly]
        if ghost:
            draw.polygon(pts, outline=(95, 100, 115, 150))
        else:
            draw.polygon(pts, fill=part_color(part) + (235,), outline=(10, 10, 14, 255))


def draw_arcs(draw, ox, oy, cy, tracks, view, here):
    """every effector's path over the whole clip (thin), the point at this frame (dot)"""
    for name, pos in tracks.items():
        col = ARC.get(name, (200, 200, 200))
        pts = [to_screen(*project(p, view)[:2], ox, oy, cy) for p in pos]
        if len(pts) >= 2:
            draw.line(pts, fill=col + (120,), width=1)
        x, y = pts[min(here, len(pts) - 1)]
        draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=col + (255,))


def vertical_center(rig, frames):
    """the body's vertical middle over the clip (so feet and raised hands both fit the cell)"""
    lo, hi = 1e9, -1e9
    for w in frames:
        for part in rig["order"]:
            ys = C.corners(rig, part, w[part])[:, 1]
            lo, hi = min(lo, float(ys.min())), max(hi, float(ys.max()))
    return -(lo + hi) / 2


def columns(clip, limit):
    """the frames to show: the keys and events (authored), else evenly spaced"""
    times = np.array(clip["times"], dtype=float)
    keyed = set()
    for j in clip["joints"].values():
        for k in j.get("keys") or []:
            keyed.add(round(float(k["t"]), 6))
    for ev in clip.get("events") or []:
        keyed.add(round(float(ev["t"]), 6))
    if 3 <= len(keyed) <= limit:
        wanted = sorted(keyed)
    else:  # a bake has no authored keys: evenly spaced frames, plus the events
        wanted = sorted(set(round(float(t), 6) for t in np.linspace(0, float(times[-1]), min(limit, len(times)))) | keyed)
    out = []
    for t in wanted:
        i = int(np.argmin(np.abs(times - t)))
        if not out or out[-1] != i:
            out.append(i)
    return out


def label_for(clip, i):
    t = float(clip["times"][i])
    bits = [f"t={t:.2f}s"]
    for j in clip["joints"].values():
        for k in j.get("keys") or []:
            if abs(float(k["t"]) - t) < 1e-6:
                bits.append(f"key {k['ease']} {k['dir']}")
                break
        if len(bits) > 1:
            break
    for ev in clip.get("events") or []:
        if abs(float(ev["t"]) - t) < 1e-6:
            bits.append("* " + ev["name"])
    return "  ".join(bits)


def timeline(draw, y, width, clip, cols, cursor=None):
    """a bar for the whole clip: key ticks, events, beats; a cursor for the gif"""
    x0, x1 = 12, width - 12
    dur = max(float(clip["duration"]), 1e-6)

    def xt(t):
        return x0 + (x1 - x0) * float(t) / dur

    draw.line([x0, y, x1, y], fill=GRID, width=2)
    for name, span in (clip.get("beats") or {}).items():
        if isinstance(span, (list, tuple)) and len(span) == 2:
            draw.rectangle([xt(span[0]), y + 6, xt(span[1]), y + 12], fill=(70, 90, 130))
            draw.text((xt(span[0]) + 2, y + 13), name, fill=DIM)
    for i in cols:
        x = xt(clip["times"][i])
        draw.line([x, y - 5, x, y + 5], fill=TEXT)
    for ev in clip.get("events") or []:
        x = xt(ev["t"])
        draw.line([x, y - 9, x, y + 2], fill=(255, 120, 110), width=2)
        draw.text((x + 3, y - 20), ev["name"], fill=(255, 150, 140))
    if cursor is not None:
        x = xt(cursor)
        draw.line([x, y - 12, x, y + 12], fill=(255, 255, 255), width=2)
    draw.text((x0, y + 24), "0.00s", fill=DIM)
    draw.text((x1 - 40, y + 24), f"{dur:.2f}s", fill=DIM)


def render(clip, rig, frames, cols, cy, tracks):
    w = CELL * len(cols)
    img = Image.new("RGB", (w, CELL * 3 + 70), BG)
    draw = ImageDraw.Draw(img, "RGBA")
    views = [("front", "FRONT (its right arm on your left)"), ("side", "SIDE (faces right)"), ("quarter", "THREE-QUARTER (front-right)")]
    for r, (view, title) in enumerate(views):
        oy = r * CELL
        for c, i in enumerate(cols):
            ox = c * CELL
            if c > 0:
                draw_pose(draw, ox, oy, cy, rig, frames[cols[c - 1]], view, ghost=True)
            draw_arcs(draw, ox, oy, cy, tracks, view, i)
            draw_pose(draw, ox, oy, cy, rig, frames[i], view)
            draw.line([ox, oy, ox, oy + CELL], fill=GRID)
        draw.text((6, oy + 4), title, fill=DIM)
    for c, i in enumerate(cols):
        draw.text((c * CELL + 8, CELL * 3 + 6), label_for(clip, i), fill=TEXT)
    timeline(draw, CELL * 3 + 40, w, clip, cols)
    return img


def render_gif(clip, rig, frames, cy, tracks, path):
    scale = 0.6
    cell = int(CELL * scale)
    out = []
    for i in range(len(frames)):
        full = Image.new("RGB", (CELL * 3, CELL + 60), BG)
        draw = ImageDraw.Draw(full, "RGBA")
        for c, view in enumerate(("front", "side", "quarter")):
            draw_arcs(draw, c * CELL, 0, cy, tracks, view, i)
            draw_pose(draw, c * CELL, 0, cy, rig, frames[i], view)
        draw.text((6, 4), f"{clip['name']}  t={float(clip['times'][i]):.2f}s", fill=TEXT)
        timeline(draw, CELL + 28, CELL * 3, clip, [], cursor=clip["times"][i])
        out.append(full.resize((int(CELL * 3 * scale), int((CELL + 60) * scale)), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE))
    ms = max(20, int(round(1000 / float(clip.get("fps") or 30))))
    out[0].save(path, save_all=True, append_images=out[1:], duration=ms, loop=0, optimize=False)
    return cell


def main(argv):
    if not argv:
        print(json.dumps({"status": "fail", "summary": "strip: no clip given", "next_action": "python kit/anim/strip.py build/animations/<Name>.clip.json"}))
        return 1
    path = argv[0]
    want_gif = "--gif" in argv
    limit = MAX_COLUMNS
    for a in argv:
        if a.startswith("--columns="):
            limit = max(2, int(a.split("=", 1)[1]))
    clip = C.load_clip(path)
    rig = C.load_rig(clip["rig"])
    frames = C.world_frames(clip, rig)
    cols = columns(clip, limit)
    cy = vertical_center(rig, frames)
    tracks = {e: [frames[i][e][:3, 3] for i in range(len(frames))] for e in C.EFFECTORS.get(rig["rig"], []) if e in rig["joints"] and "Head" not in e}
    base = path[:-len(".clip.json")] if path.endswith(".clip.json") else os.path.splitext(path)[0]
    out = base + ".png"
    render(clip, rig, frames, cols, cy, tracks).save(out)
    made = [os.path.basename(out)]
    if want_gif:
        render_gif(clip, rig, frames, cy, tracks, base + ".gif")
        made.append(os.path.basename(base + ".gif"))
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"strip {out} ({len(cols)} columns, {len(frames)} frames)" + (", gif" if want_gif else ""),
                      "next_action": f"look at {out.replace(chr(92), '/')}: do the arcs read, is the anticipation bigger than the action, does the Hit sit just after the fastest frame?",
                      "file": out.replace(chr(92), "/"), "made": made}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
