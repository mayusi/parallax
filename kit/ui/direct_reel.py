"""direct_reel.py — a direction's SIGNATURE MOMENT in motion (v8.1). The owner's word: "cooler" = motion (the smear
card's dash reel, the Umbra health reel 9.2); a still sells a layout, a reel sells the moment. Every direction on a
board carries one signature moment as timed beats; this renders it as an animated sketch on the game's world shot.

    python kit/ui/direct_reel.py <brief> [<key> ...] [--game G] [--fps 24] [--width 640]
    (lune run kit ui direct reel <brief> [<key> ...])

-> build/ui/directions/<game>/<brief>/<key>.reel.gif + <key>.strip.jpg (six frames across the moment); the board shows the
reel in place of the still when it exists.

The timing lives in the brief, on the direction's `frame`:
  frame.reel   {"duration": 1.8, "fps": 24, "push": 0.03,              the ground pushes in 3% over the moment
                "events": [{"t": 0.0, "dur": 0.08, "kind": "invert"},   whole-frame beats: invert / white / black /
                           {"t": 0.1, "dur": 0.2, "kind": "shake", "amp": 16}, shake / desat / tint (+ "color")
                           ...]}
  an element   "t": [t0, t1]          on screen from t0 to t1 (default: always - the HUD at rest)
               "in": {"dur": 0.12, "from": {"alpha": 0, "dx": -300, "dy": 0, "scale": 1.4}, "ease": "back"}
               "out": {"dur": 0.2, "to": {"alpha": 0, "dy": 40}, "ease": "in"}
               "wipe": {"dur": 0.25, "axis": "x" | "y", "from": "start" | "end" | "centre"}   a reveal (a door closing)
               "pulse": {"period": 0.5, "amp": 0.08}   a beat on the scale (and alpha)
Elements without any of these stay as the static HUD. Prints one JSON line.
"""
import argparse
import json
import math
import os
import random
import re
import sys

from PIL import Image, ImageChops, ImageEnhance, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import direct  # noqa: E402

S = 0.5  # frames are composed at half of 1920x1080, then written at --width


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}, ensure_ascii=False))
    return 0 if status == "pass" else 1


def ease(x, kind="out"):
    x = min(1.0, max(0.0, x))
    if kind == "in":
        return x ** 3
    if kind == "linear":
        return x
    if kind == "back":
        c1 = 1.70158
        c3 = c1 + 1
        return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2
    if kind == "snap":  # holds, then lands: a stamp
        return 0.0 if x < 0.6 else ease((x - 0.6) / 0.4, "back")
    return 1 - (1 - x) ** 3


def timed(el):
    return isinstance(el, dict) and any(k in el for k in ("t", "in", "out", "wipe", "pulse"))


def sprite(el, pal, tv):
    """the element drawn once at full size, cropped to its pixels and scaled to the composing size -> (img, x, y)"""
    layer = direct.draw_element(el, pal, tv)
    box = layer.getbbox()
    if not box:
        return None
    crop = layer.crop(box)
    w, h = max(1, round(crop.width * S)), max(1, round(crop.height * S))
    return crop.resize((w, h), Image.LANCZOS), box[0] * S, box[1] * S


def state(el, t, end):
    """(visible, alpha, dx, dy, scale, reveal) of a timed element at time t"""
    window = el.get("t") if isinstance(el.get("t"), (list, tuple)) else ([el["t"]] if isinstance(el.get("t"), (int, float)) else [0, end])
    window = window or [0, end]
    t0 = float(window[0])
    t1 = float(window[1]) if len(window) > 1 else end
    if t < t0 or t > t1:
        return False, 0, 0, 0, 1, 1
    a, dx, dy, sc, reveal = 1.0, 0.0, 0.0, 1.0, 1.0
    if el.get("in"):
        i = el["in"]
        k = ease((t - t0) / max(1e-6, float(i.get("dur", 0.15))), i.get("ease", "out"))
        f = i.get("from") or {}
        a = a * (f.get("alpha", 1) + (1 - f.get("alpha", 1)) * k)
        dx += f.get("dx", 0) * (1 - k)
        dy += f.get("dy", 0) * (1 - k)
        sc *= f.get("scale", 1) + (1 - f.get("scale", 1)) * k
    if el.get("out"):
        o = el["out"]
        dur = float(o.get("dur", 0.2))
        if t > t1 - dur:
            k = ease((t - (t1 - dur)) / max(1e-6, dur), o.get("ease", "in"))
            to = o.get("to") or {}
            a *= 1 + (to.get("alpha", 1) - 1) * k
            dx += to.get("dx", 0) * k
            dy += to.get("dy", 0) * k
            sc *= 1 + (to.get("scale", 1) - 1) * k
    if el.get("wipe"):
        reveal = ease((t - t0) / max(1e-6, float(el["wipe"].get("dur", 0.25))), el["wipe"].get("ease", "out"))
    if el.get("pulse"):
        p = el["pulse"]
        s = math.sin(2 * math.pi * (t - t0) / max(0.05, float(p.get("period", 0.5))))
        sc *= 1 + float(p.get("amp", 0.06)) * max(0.0, s)
        a *= 1 - 0.35 * float(p.get("amp", 0.06)) * 5 * max(0.0, -s)
    return True, max(0.0, min(1.0, a)), dx, dy, sc, reveal


def place(frame, spr, el, st):
    img, x, y = spr
    _, a, dx, dy, sc, reveal = st
    if reveal < 1:
        w = el.get("wipe") or {}
        axis, start = w.get("axis", "x"), w.get("from", "start")
        W_, H_ = img.size
        if axis == "x":
            keep = max(1, round(W_ * reveal))
            x0 = 0 if start == "start" else (W_ - keep if start == "end" else (W_ - keep) // 2)
            img = img.crop((x0, 0, x0 + keep, H_))
            x += x0
        else:
            keep = max(1, round(H_ * reveal))
            y0 = 0 if start == "start" else (H_ - keep if start == "end" else (H_ - keep) // 2)
            img = img.crop((0, y0, W_, y0 + keep))
            y += y0
    if abs(sc - 1) > 1e-3:
        cx, cy = x + img.width / 2, y + img.height / 2
        img = img.resize((max(1, round(img.width * sc)), max(1, round(img.height * sc))), Image.BILINEAR)
        x, y = cx - img.width / 2, cy - img.height / 2
    if a < 0.999:
        alpha = img.getchannel("A").point(lambda v: int(v * a))
        img = img.copy()
        img.putalpha(alpha)
    x, y = round(x + dx * S), round(y + dy * S)
    fw, fh = frame.size
    # clip to the frame (alpha_composite needs the sprite inside)
    if x >= fw or y >= fh or x + img.width <= 0 or y + img.height <= 0:
        return
    cl, ct = max(0, -x), max(0, -y)
    img = img.crop((cl, ct, min(img.width, fw - x), min(img.height, fh - y)))
    frame.alpha_composite(img, dest=(x + cl, y + ct))


def apply_events(rgb, events, t, pal, rng):
    for ev in events:
        t0, dur = float(ev.get("t", 0)), float(ev.get("dur", 0.1))
        if not t0 <= t <= t0 + dur:
            continue
        k = ev.get("kind")
        p = (t - t0) / max(1e-6, dur)
        if k == "invert":
            rgb = ImageOps.invert(rgb)
        elif k in ("white", "black"):
            fill = (255, 255, 255) if k == "white" else (0, 0, 0)
            rgb = Image.blend(rgb, Image.new("RGB", rgb.size, fill), float(ev.get("amount", 0.9)) * (1 - p))
        elif k == "tint":
            rgb = Image.blend(rgb, Image.new("RGB", rgb.size, direct.colour(pal, ev.get("color", "accent"))), float(ev.get("amount", 0.4)) * (1 - p))
        elif k == "desat":
            rgb = ImageEnhance.Color(rgb).enhance(1 - float(ev.get("amount", 1.0)) * min(1.0, p * 3))
        elif k == "shake":
            amp = float(ev.get("amp", 14)) * S * (1 - p)
            rgb = ImageChops.offset(rgb, round(rng.uniform(-amp, amp)), round(rng.uniform(-amp, amp)))
    return rgb


def strip_picks(beats, fps, n_frames, k=6):
    """six frames that SHOW the moment: each beat's SETTLED state (the frame just before the next beat starts - a frame
    right after a beat starts shows nothing landed yet; the blind critic saw no towers in Skyline Pulse's first strip),
    the opening frame and the final rest"""
    ts = sorted(float(b[0]) for b in beats if b and re.fullmatch(r"\d+(\.\d+)?", str(b[0])))
    end = (n_frames - 1) / fps
    want = [min(ts[0] + 2 / fps, end)] if ts else [0.0]
    for i, t in enumerate(ts):
        nxt = ts[i + 1] if i + 1 < len(ts) else end
        want.append(max(t, nxt - 1 / fps))
    want.append(end)
    frames = sorted({min(n_frames - 1, max(0, round(t * fps))) for t in want})
    if len(frames) < k:  # too few: add evenly spaced frames (then the closest neighbours go below)
        frames = sorted(set(frames) | {round(j * (n_frames - 1) / (k - 1)) for j in range(k)})
    while len(frames) > k:  # too many: drop the frame closest to its neighbour (near-duplicates go first), never the ends
        gaps = [(min(frames[i] - frames[i - 1], frames[i + 1] - frames[i]), i) for i in range(1, len(frames) - 1)]
        frames.pop(min(gaps)[1])
    while len(frames) < k:  # a reel shorter than k frames: repeat the last
        frames.append(frames[-1])
    return frames[:k]


FAINT = 0.04  # under 4% of the frame ever changing: a blind critic said 'almost nothing happens' (Smith's Wall r1)


def moment_change(frames):
    """how much of the frame the moment visibly changes: the largest share of pixels (vs the first frame) that move
    by more than 40 levels, at any time in the reel - the critics' 'almost nothing happens' in a number"""
    import numpy as np
    first = np.asarray(frames[0].convert("L"), dtype=np.int16)
    best = 0.0
    for f in frames[1:]:
        diff = np.abs(np.asarray(f.convert("L"), dtype=np.int16) - first)
        best = max(best, float((diff > 40).mean()))
    return round(best, 4)


def render(direction, out_dir, fps=None, width=640):
    fr = direction.get("frame") or {}
    reel = fr.get("reel") or {}
    beats = (direction.get("signature_moment") or {}).get("beats") or []
    last = max([float(b[0]) for b in beats if b and str(b[0]).replace(".", "", 1).isdigit()] or [1.0])
    fps = max(1, int(fps or reel.get("fps", 24)))
    end = max(float(reel.get("duration", last + 0.6)), 2 / fps)
    pal, tv = direction.get("palette") or {}, direction.get("type_voice") or {}
    cw, ch = round(direct.W * S), round(direct.H * S)
    big = direct.ground_image(direction, round(cw * 1.06), round(ch * 1.06))
    push = float(reel.get("push", 0.03))
    sprites, skipped = [], []
    for n, el in enumerate(fr.get("elements") or []):
        try:
            sprites.append((el, sprite(el, pal, tv)))
        except Exception as e:  # noqa: BLE001
            skipped.append(f"element {n + 1}: {type(e).__name__} {e}")
    rng = random.Random(7)
    frames = []
    n_frames = max(2, round(end * fps))
    for i in range(n_frames):
        t = i / fps
        z = 1 + push * (t / end)  # the slow push-in: the moment leans toward the player
        gw, gh = round(cw * z), round(ch * z)
        g = big.resize((gw, gh), Image.BILINEAR)
        g = g.crop(((gw - cw) // 2, (gh - ch) // 2, (gw - cw) // 2 + cw, (gh - ch) // 2 + ch))
        frame = g.convert("RGBA")
        for el, spr in sprites:
            if not spr:
                continue
            st = state(el, t, end) if timed(el) else (True, 1, 0, 0, 1, 1)
            if st[0]:
                place(frame, spr, el, st)
        rgb = apply_events(frame.convert("RGB"), reel.get("events") or [], t, pal, rng)
        frames.append(rgb.resize((width, round(width * ch / cw)), Image.LANCZOS))
    os.makedirs(out_dir, exist_ok=True)
    k = direction.get("key")
    gif = os.path.join(out_dir, f"{k}.reel.gif")
    # ONE palette for the whole moment, built by octree from frames across it: a per-frame median cut let the dark
    # majority swallow small bright pieces (Fulgurite's green glass shards came out grey-green)
    sample = [frames[round(j * (len(frames) - 1) / 7)] for j in range(8)]
    sheet = Image.new("RGB", (sample[0].width * len(sample), sample[0].height))
    for j, f in enumerate(sample):
        sheet.paste(f, (j * f.width, 0))
    palette = sheet.quantize(colors=255, method=Image.Quantize.FASTOCTREE)
    pal_frames = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    pal_frames[0].save(gif, save_all=True, append_images=pal_frames[1:], duration=round(1000 / fps), loop=0, optimize=True)
    picks = strip_picks(beats, fps, n_frames)
    visible = moment_change(frames)
    tw = 426
    th = round(tw * ch / cw)
    strip = Image.new("RGB", (tw * 3, th * 2), (8, 8, 10))
    for j, fi in enumerate(picks):
        strip.paste(frames[fi].resize((tw, th), Image.LANCZOS), ((j % 3) * tw, (j // 3) * th))
    sp = os.path.join(out_dir, f"{k}.strip.jpg")
    strip.save(sp, quality=86)
    return gif, sp, n_frames, skipped, visible


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--game", default=None)
    ap.add_argument("--fps", type=int, default=None)
    ap.add_argument("--width", type=int, default=640)
    a = ap.parse_args(argv)
    try:
        _, d = direct.load(a.name, a.game)
    except (OSError, json.JSONDecodeError) as e:
        return emit("fail", f"direct reel: {e}", f"lune run kit ui direct new {a.name} --ask \"...\"")
    out = direct.out_dir(d)
    made, skipped, still = [], [], []
    for x in d.get("directions") or []:
        if not str(x.get("title") or "").strip() or (a.keys and x.get("key") not in a.keys):
            continue
        if not any(timed(el) for el in (x.get("frame") or {}).get("elements") or []) and not ((x.get("frame") or {}).get("reel") or {}).get("events"):
            still.append(x["key"])
            continue
        gif, sp, n, bad, vis = render(x, out, a.fps, a.width)
        made.append({"key": x["key"], "gif": gif.replace(chr(92), "/"), "strip": sp.replace(chr(92), "/"), "frames": n, "visible": vis})
        skipped += [f"{x['key']} {b}" for b in bad]
    if not made:
        return emit("fail", f"direct reel {a.name}: no direction has timing yet ({', '.join(still) or 'none'})",
                    "give the signature moment's elements \"t\" / \"in\" / \"wipe\" and frame.reel events (see kit/ui/direct_reel.py)")
    note = f"; still only: {', '.join(still)}" if still else ""
    note += f"; {len(skipped)} element(s) skipped ({skipped[0]})" if skipped else ""
    faint = [f"{m['key']} ({m['visible'] * 100:.0f}%)" for m in made if m["visible"] < FAINT]
    note += f"; the moment barely SHOWS in {', '.join(faint)} - make it bigger or longer" if faint else ""
    return emit("pass", f"direct reel {a.name}: {len(made)} signature moment(s) in motion -> {out.replace(chr(92), '/')}{note}",
                f"LOOK at the strips, then lune run kit ui direct board {a.name} (the board plays the reels)", reels=made)


if __name__ == "__main__":
    sys.exit(main())
