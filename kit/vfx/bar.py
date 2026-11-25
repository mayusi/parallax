"""bar.py — the BAR: measure an effect against owner-named reference clips (mission 02-vfx 5.3). Never a score.

    lune run kit vfx bar <style> <clip> [--from s] [--to s] [--label name] [--approved]
    lune run kit vfx measure <effect> --vs-bar <style> [--recording <mp4>] [--from s] [--to s]

"I still don't see AAA" has no number until the bar is a clip. A style (ultimate, impact, aura, projectile, ...) holds
<= 3 private clips (git-ignored under assets/effects/refs/; the owner's yes per clip: --approved records it). `bar`
measures one clip into numbers (committed, no pictures) -> assets/effects/bars/<style>/<label>.json:
  * the effect curve: per frame (12 fps) the share of EFFECT pixels (bright AND saturated, or white-hot) and their
    luminance
  * three PHASES from that curve: anticipation (before the rise), climax (the run around the peak >= 50 % of it),
    tail (after) — their lengths, effect share, luminance, saturation, hue histogram (12 bins), the effect's
    extents (bounding box share of the frame) at the phase's fullest frame, the dominant colour
`measure` measures the effect's recording the same way (default: the newest booth / player hero recording) and
returns per phase ONE difference (the biggest gap against the style's clips, their median) + ONE edit, in words.
The owner's eye stays the bar; these numbers only point at what to change next.
Prints one JSON line {schema, status, summary, next_action, ...}.
"""

import colorsys
import glob
import json
import math
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

BARS = os.path.join("assets", "effects", "bars")
FPS = 12
HUE_BINS = 12
PHASES = ("anticipation", "climax", "tail")


def out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status in ("pass", "warn") else 1


def frames_of(clip, start, end, tmp):
    args = ["ffmpeg", "-v", "error", "-y", "-ss", str(start)] + (["-to", str(end)] if end else []) + \
           ["-i", clip, "-vf", f"fps={FPS},scale=320:-2", os.path.join(tmp, "%05d.png")]
    subprocess.run(args, check=True, timeout=1800)
    return [os.path.join(tmp, f) for f in sorted(os.listdir(tmp)) if f.endswith(".png")]


def read_frame(path):
    """effect mask + per-pixel colour of one frame"""
    a = np.asarray(Image.open(path).convert("RGB"), np.float32)
    lum = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    mx, mn = a.max(axis=-1), a.min(axis=-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    mask = (lum >= 200) | ((lum >= 110) & (sat >= 0.35))  # white-hot, or bright AND saturated: energy, not scenery
    return a, lum, sat, mask


def measure_clip(clip, start=0.0, end=None):
    with tempfile.TemporaryDirectory(prefix="kit_bar_") as tmp:
        paths = frames_of(clip, start, end, tmp)
        if len(paths) < 6:
            raise ValueError(f"{clip}: {len(paths)} frame(s) at {FPS} fps - too short to measure")
        per = []
        for p in paths:
            a, lum, sat, mask = read_frame(p)
            share = float(mask.mean())
            entry = {"share": share, "lum": float(lum[mask].mean()) if mask.any() else 0.0,
                     "sat": float(sat[mask].mean()) if mask.any() else 0.0}
            if mask.any():
                px = a[mask & (sat >= 0.2)] / 255.0  # white-hot pixels have no hue (colorsys calls them red)
                hues = np.array([colorsys.rgb_to_hsv(*c)[0] for c in px[:: max(1, len(px) // 4000)]]) if len(px) else np.zeros(0)
                entry["hue"] = np.histogram(hues, bins=HUE_BINS, range=(0, 1))[0].tolist()
                ys, xs = np.nonzero(mask)
                entry["extent"] = [float((xs.max() - xs.min() + 1) / mask.shape[1]), float((ys.max() - ys.min() + 1) / mask.shape[0])]
                entry["rgb"] = [int(v) for v in np.median(a[mask], axis=0)]
            else:
                entry["hue"], entry["extent"], entry["rgb"] = [0] * HUE_BINS, [0.0, 0.0], [0, 0, 0]
            per.append(entry)
    return phases(per)


def phases(per):
    """anticipation / climax / tail from the effect-share curve (smoothed over 3 frames)"""
    s = np.array([e["share"] for e in per])
    sm = np.convolve(s, np.ones(3) / 3, mode="same")
    p = int(np.argmax(sm))
    peak = float(sm[p]) or 1e-9
    c0 = p
    while c0 > 0 and sm[c0 - 1] >= 0.5 * peak:
        c0 -= 1
    c1 = p
    while c1 < len(sm) - 1 and sm[c1 + 1] >= 0.5 * peak:
        c1 += 1
    spans = {"anticipation": (0, c0), "climax": (c0, c1 + 1), "tail": (c1 + 1, len(per))}
    res = {"fps": FPS, "frames": len(per), "seconds": round(len(per) / FPS, 2), "peak_share": round(peak, 4),
           "curve": [round(float(v), 4) for v in sm], "phases": {}}
    for name, (a, b) in spans.items():
        seg = per[a:b]
        if not seg:
            res["phases"][name] = {"seconds": 0.0}
            continue
        full = max(seg, key=lambda e: e["share"])
        hue = np.sum([e["hue"] for e in seg], axis=0).astype(float)
        res["phases"][name] = {
            "seconds": round(len(seg) / FPS, 2),
            "share": round(float(np.mean([e["share"] for e in seg])), 4),
            "lum": round(float(np.mean([e["lum"] for e in seg if e["share"] > 0] or [0])), 1),
            "sat": round(float(np.mean([e["sat"] for e in seg if e["share"] > 0] or [0])), 3),
            "hue": [round(v, 4) for v in (hue / hue.sum() if hue.sum() else hue).tolist()],
            "extent": [round(v, 3) for v in full["extent"]],
            "rgb": full["rgb"],
        }
    return res


def hue_name(i):
    return ["red", "orange", "yellow", "yellow-green", "green", "green-cyan", "cyan", "azure", "blue", "violet",
            "magenta", "pink"][i]


def diffs(phase, mine, bar, mine_total, bar_total):
    """every gap of one phase as (size, words, edit); size = how far off, comparable across kinds. Lengths compare as
    SHARES of the whole (the rhythm): an anime scene holds for seconds a game effect cannot"""
    out_ = []
    if bar.get("seconds", 0) > 0 or mine.get("seconds", 0) > 0:
        a, b = mine.get("seconds", 0.0) / max(mine_total, 0.01), bar.get("seconds", 0.0) / max(bar_total, 0.01)
        r = math.log((a + 0.03) / (b + 0.03))
        want = b * mine_total
        out_.append((abs(r), f"{phase} is {a:.0%} of the effect ({mine.get('seconds', 0):.2f} s) vs {b:.0%} of the bar",
                     f"{'shorten' if r > 0 else 'lengthen'} the {phase} to ~{want:.2f} s of your {mine_total:.2f} s"
                     + (" (the bar's tail fades fast: front-loaded curves)" if phase == "tail" and r > 0 else "")))
    # frame share only compares when the bar is not a close-up: an anime close-up fills the frame edge to edge (the
    # SSJ burst: 100 % x 100 %) where a game camera frames the whole body - that gap is framing, not the effect
    closeup = min(bar.get("extent") or [0, 0]) >= 0.95
    if "share" in mine and "share" in bar and not closeup:
        r = math.log((mine["share"] + 0.005) / (bar["share"] + 0.005))
        out_.append((abs(r) * 0.8, f"{phase} fills {mine['share']:.0%} of the frame with effect vs {bar['share']:.0%}",
                     f"{'grow' if r < 0 else 'shrink'} what the {phase} draws: the bar's fullest frame spans "
                     f"{bar['extent'][0]:.0%} x {bar['extent'][1]:.0%} of the frame, yours {mine['extent'][0]:.0%} x {mine['extent'][1]:.0%}"))
    if mine.get("lum") and bar.get("lum"):
        d = (mine["lum"] - bar["lum"]) / 60.0
        out_.append((abs(d), f"{phase}'s effect pixels average luma {mine['lum']:.0f} vs {bar['lum']:.0f}",
                     "a white-hot core for 0.03-0.1 s and brighter cores (brightness 5-50)" if d < 0 else
                     f"darker, more saturated body in the {phase}: a dark twin behind the bright shape, less additive stacking"))
    if mine.get("hue") and bar.get("hue") and sum(bar["hue"]) and sum(mine["hue"]):
        l1 = 0.5 * sum(abs(x - y) for x, y in zip(mine["hue"], bar["hue"]))
        bi, mi = int(np.argmax(bar["hue"])), int(np.argmax(mine["hue"]))
        out_.append((l1 * 2.0, f"{phase}'s colour is mostly {hue_name(mi)} vs the bar's {hue_name(bi)} ({l1:.0%} of the hues differ)",
                     f"move the {phase}'s dominant colour toward {hue_name(bi)} (the bar's fullest frame: rgb {bar['rgb']})"))
    if mine.get("sat") and bar.get("sat"):
        d = (mine["sat"] - bar["sat"]) / 0.25
        out_.append((abs(d) * 0.7, f"{phase}'s saturation {mine['sat']:.2f} vs {bar['sat']:.2f}",
                     "pre-saturate the colours (additive Neon washes measured colours out)" if d < 0 else "desaturate the matter (smoke, dust): saturated energy, desaturated matter"))
    return sorted(out_, key=lambda x: -x[0])


def median_bar(entries):
    """the style's clips as one bar: per phase the median of every number (hue: the mean histogram)"""
    if len(entries) == 1:
        return entries[0]
    res = {"phases": {}, "seconds": float(np.median([e["seconds"] for e in entries]))}
    for ph in PHASES:
        items = [e["phases"].get(ph, {}) for e in entries if e["phases"].get(ph, {}).get("seconds")]
        if not items:
            res["phases"][ph] = {"seconds": 0.0}
            continue
        res["phases"][ph] = {k: round(float(np.median([i[k] for i in items])), 4) for k in ("seconds", "share", "lum", "sat")}
        res["phases"][ph]["hue"] = np.mean([i["hue"] for i in items], axis=0).round(4).tolist()
        res["phases"][ph]["extent"] = np.median([i["extent"] for i in items], axis=0).round(3).tolist()
        res["phases"][ph]["rgb"] = items[len(items) // 2]["rgb"]
    return res


def cmd_bar(args, opts):
    if len(args) < 2:
        return out("fail", "bar: needs <style> <clip>", "lune run kit vfx bar ultimate assets/effects/refs/<set>/clip/<file>.mp4 [--from s --to s]")
    style, clip = args[0], args[1]
    if not re.fullmatch(r"[a-z0-9_]{1,40}", style):
        return out("fail", f"bar: style {style!r}", "lowercase letters, digits, _ (ultimate, impact, aura, projectile)")
    if not os.path.isfile(clip):
        return out("fail", f"bar: no clip {clip}", "the owner names the clip; download it with the vetted yt-dlp under assets/effects/refs/")
    d = os.path.join(BARS, style)
    os.makedirs(d, exist_ok=True)
    label = opts.get("--label") or re.sub(r"[^a-z0-9_]+", "_", os.path.splitext(os.path.basename(clip))[0].lower())[:40]
    existing = [p for p in glob.glob(os.path.join(d, "*.json")) if os.path.basename(p)[:-5] != label]
    if len(existing) >= 3:
        return out("fail", f"bar {style}: already 3 clips ({', '.join(os.path.basename(p)[:-5] for p in existing)})",
                   "a style holds <= 3 clips: the owner picks which one to drop")
    start, end = float(opts.get("--from", 0)), (float(opts["--to"]) if "--to" in opts else None)
    m = measure_clip(clip, start, end)
    m.update({"style": style, "label": label, "clip": clip.replace(os.sep, "/"), "window": [start, end],
              "approved": "--approved" in sys.argv, "about": "numbers only (the clip stays private, git-ignored); approved = the owner's yes"})
    dest = os.path.join(d, f"{label}.json")
    json.dump(m, open(dest, "w", encoding="utf-8", newline="\n"), indent=1)
    ph = m["phases"]
    return out("pass" if m["approved"] else "warn",
               f"bar {style}/{label}: {m['seconds']} s - anticipation {ph['anticipation']['seconds']} s, climax {ph['climax']['seconds']} s, tail {ph['tail']['seconds']} s"
               + ("" if m["approved"] else " - NOT owner-approved yet"),
               ("" if m["approved"] else "the owner's yes for this clip as the bar, then re-run with --approved; ") + f"lune run kit vfx measure <effect> --vs-bar {style}",
               bar=dest.replace(os.sep, "/"))


def newest_recording(name):
    # mission 02-vfx v2: the player's recording only (a Studio booth capture is not the effect the owner judges)
    recs = [p for p in glob.glob(os.path.join("build", "vfx", "booth", f"{name}_play_hero.mp4"))]
    return max(recs, key=os.path.getmtime) if recs else None


def cmd_measure(args, opts):
    if not args or "--vs-bar" not in opts:
        return out("fail", "measure: needs <effect> --vs-bar <style>", "lune run kit vfx measure <effect> --vs-bar ultimate [--recording <mp4>]")
    name, style = args[0], opts["--vs-bar"]
    entries = [json.load(open(p, encoding="utf-8")) for p in sorted(glob.glob(os.path.join(BARS, style, "*.json")))]
    if not entries:
        return out("fail", f"measure: no bar clips for style {style}", f"lune run kit vfx bar {style} <clip> (the owner names the clip)")
    rec = opts.get("--recording") or newest_recording(name)
    if not rec or not os.path.isfile(rec):
        return out("fail", f"measure {name}: no recording", f"lune run kit vfx play {name} --record, or pass --recording <mp4>")
    mine = measure_clip(rec, float(opts.get("--from", 0)), float(opts["--to"]) if "--to" in opts else None)
    bar = median_bar(entries)
    per_phase = []
    for ph in PHASES:
        gaps = diffs(ph, mine["phases"].get(ph, {}), bar["phases"].get(ph, {}), mine["seconds"], bar["seconds"])
        if gaps:
            size, words, edit = gaps[0]
            per_phase.append({"phase": ph, "difference": words, "edit": edit})
    unapproved = [e["label"] for e in entries if not e.get("approved")]
    lines = [f"{p['phase']}: {p['difference']} -> {p['edit']}" for p in per_phase]
    return out("warn" if unapproved else "pass",
               f"measure {name} vs bar {style} ({len(entries)} clip(s)): " + " | ".join(lines)
               + (f" - bar clip(s) NOT owner-approved: {', '.join(unapproved)}" if unapproved else ""),
               "make ONE of these edits (the climax first), re-record, measure again; the owner's eye decides",
               recording=rec.replace(os.sep, "/"), phases=per_phase, effect=mine["phases"], bar=bar["phases"])


def main(argv):
    sub = argv[0] if argv else ""
    rest = argv[1:]
    opts, args, i = {}, [], 0
    while i < len(rest):
        if rest[i] == "--approved":
            i += 1
        elif rest[i].startswith("--") and i + 1 < len(rest):
            opts[rest[i]] = rest[i + 1]
            i += 2
        else:
            args.append(rest[i])
            i += 1
    if sub == "bar":
        return cmd_bar(args, opts)
    if sub == "measure":
        return cmd_measure(args, opts)
    return out("fail", f"bar.py: unknown subcommand {sub!r}", "bar <style> <clip> | measure <effect> --vs-bar <style>")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
