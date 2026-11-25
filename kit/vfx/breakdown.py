"""breakdown.py — the scene breakdown (mission 02-vfx 5.1): no frames, no build.

    lune run kit vfx breakdown <set> --clip <file> [--fps 2] [--from 0] [--to <s>] [--cut 0.35] [--cols 6]

A reference clip (private, measure-only, under the git-ignored assets/effects/refs/) becomes:
  * the frames in order at --fps   -> assets/effects/refs/<set>_scene/f_<mm.ss>.png  (the measure step reads them)
  * the HARD CUTS, found at the clip's full frame rate by a content detector (HSV histogram distance between
    consecutive frames, the same idea as PySceneDetect's ContentDetector; numpy only, nothing installed)
  * a numbered contact sheet with the time and a cut mark on every frame -> build/vfx/breakdown/<set>.png (LOOK at it)
  * a beat-sheet SKELETON, one row per shot between cuts -> assets/effects/refs_measured/<set>.beats.md (never
    overwritten: an existing sheet gets <set>.beats.skeleton.md beside it). The skeleton's "on screen" and "text"
    cells are blank: YOU fill them from the frames + the lore brief; the preset gate counts rows with a scene time.
Prints one JSON line {schema, status, summary, next_action, ...}.

    lune run kit vfx breakdown <set> --dense [--beat <#>] [--scene-window a,b] [--frames 12] [--tile 640]

The scene's TIMING, read frame by frame (the VFX studio-route plan, V0): 2 frames a second shows what is on screen,
never how it moves, and anime effects are timed frame by frame. After a breakdown, --dense reads every beat's shots
at the clip's FULL frame rate (kit/vfx/denseclip.py + dense.py): per frame how much of the screen the effect covers,
how bright it is, how much of its shape is new; from that, per shot, how the light ARRIVES (in one frame, or over
how many), how long it STAYS, how it GOES, any FREEZE, and the drawing rhythm (on ones, twos, threes).
  * the numbers -> assets/effects/refs_measured/<set>.timing.json + <set>.timing.md (beside the beat sheet)
  * per beat, its main shot's consecutive frames round the arrival, each 640 px or more, the arrival ringed, a held
    drawing marked, the light curve under them -> build/vfx/breakdown/<set>_dense/beat<k>_page.png, and the same
    frames two a picture (beat<k>_<nn>.png: what a session reads at full size). The frames stay private (build/).
--beat reads one beat again (the others keep their numbers); with it, --scene-window a,b reads that stretch of the
clip as ONE shot (when a flash was taken for a cut, or the main shot is not the one meant).
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

REFS = os.path.join("assets", "effects", "refs")
MEASURED = os.path.join("assets", "effects", "refs_measured")
BUILD = os.path.join("build", "vfx", "breakdown")


def out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def probe(clip):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate:format=duration",
                        "-of", "json", clip], capture_output=True, text=True, timeout=60)
    d = json.loads(r.stdout or "{}")
    num, den = (d.get("streams") or [{}])[0].get("r_frame_rate", "30/1").split("/")
    return float(num) / float(den or 1), float((d.get("format") or {}).get("duration") or 0)


def extract(clip, fps, start, end, dest, width):
    os.makedirs(dest, exist_ok=True)
    args = ["ffmpeg", "-v", "error", "-y", "-ss", str(start)] + (["-to", str(end)] if end else []) + \
           ["-i", clip, "-vf", f"fps={fps},scale={width}:-2", os.path.join(dest, "%05d.png")]
    subprocess.run(args, check=True, timeout=1800)
    return sorted(f for f in os.listdir(dest) if f.endswith(".png"))


def hsv_hist(path):
    """a 16x4x4 HSV histogram, normalised — what a content cut detector compares"""
    hsv = np.asarray(Image.open(path).convert("HSV"), np.float32)
    h, _ = np.histogramdd(hsv.reshape(-1, 3), bins=(16, 4, 4), range=((0, 256), (0, 256), (0, 256)))
    return h.ravel() / max(1.0, h.sum())


def find_cuts(frames_dir, names, fps, threshold):
    """times (s, from the clip window's start) where consecutive frames differ by > threshold (half the L1 distance
    of their HSV histograms: 0 = identical, 1 = nothing in common) AND their pixels moved a lot (mean |RGB change|
    >= 20 / 255: a slow fade that drifts across a histogram bin edge is not a cut); >= 0.25 s since the last cut"""
    cuts, prev, prev_px, last = [], None, None, -1e9
    for i, n in enumerate(names):
        path = os.path.join(frames_dir, n)
        h = hsv_hist(path)
        px = np.asarray(Image.open(path).convert("RGB").resize((32, 18)), np.float32)
        if prev is not None:
            d = 0.5 * float(np.abs(h - prev).sum())
            moved = float(np.abs(px - prev_px).mean())
            t = i / fps
            if d > threshold and moved >= 20 and t - last >= 0.25:
                cuts.append((round(t, 2), round(d, 3)))
                last = t
        prev, prev_px = h, px
    return cuts


def contact_sheet(frames, times, cut_set, cols, path):
    tw = 320
    ims = [Image.open(f).convert("RGB") for f in frames]
    th = round(ims[0].height * tw / ims[0].width)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 18)), (18, 18, 22))
    d = ImageDraw.Draw(sheet)
    for i, (im, t) in enumerate(zip(ims, times)):
        x, y = (i % cols) * tw, (i // cols) * (th + 18)
        sheet.paste(im.resize((tw, th)), (x, y + 18))
        cut = t in cut_set
        d.rectangle([x, y, x + tw - 1, y + 17], fill=(170, 30, 30) if cut else (40, 40, 48))
        d.text((x + 4, y + 3), f"#{i:02d}  {t:6.2f} s" + ("   CUT" if cut else ""), fill=(255, 255, 255))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.save(path, quality=90)


def skeleton(name, clip, fps, start, length, shots, frames_rel):
    rows = []
    for k, (a, b) in enumerate(shots):
        rows.append(f"| {k} | {start + a:.1f}-{start + b:.1f} s |  |  |  |  |  |  |")
    return "\n".join([
        f"# {name} — scene beat sheet (vision + text)",
        "",
        f"Source (private, measure-only, git-ignored): {clip.replace(os.sep, '/')} — window {start:.1f}-{start + length:.1f} s,",
        f"studied at {fps:g} fps ({frames_rel}/, contact sheet build/vfx/breakdown/{name}.png). One row per SHOT between",
        "detected hard cuts: merge rows that are one beat, split a shot that holds two. Fill every blank from the frames",
        f"and the lore brief ({name}.brief.md); measure the colours of the key frames: lune run kit vfx refs measure {name}_scene.",
        "",
        "| Beat | Scene time | What is on screen (vision) | Shape | Colour | Size vs the body | Motion / hold | Text |",
        "|---|---|---|---|---|---|---|---|",
        *rows,
        "",
    ])


def beat_rows(name):
    """the set's beats with their scene times: the chart's (the plan the owner approved) when there is one, else
    the beat sheet's rows -> [(label, t0, t1, is the key beat)]"""
    try:
        chart = json.load(open(os.path.join(MEASURED, f"{name}.chart.json"), encoding="utf-8"))
        rows = [(str(b.get("beat")), float(b["scene"][0]), float(b["scene"][1]), bool(b.get("key")))
                for b in chart.get("beats", []) if isinstance(b.get("scene"), list) and len(b["scene"]) == 2]
        if rows:
            return rows
    except (OSError, ValueError, KeyError, TypeError):
        pass
    sheet = os.path.join(MEASURED, f"{name}.beats.md")
    if not os.path.isfile(sheet):
        return []
    import chart as chart_tool
    return [(b["label"], b["t0"], b["t1"], "key" in b["label"].lower().split()) for b in chart_tool.parse_beats(sheet)]


def timing_sheet(name, meta, hue, rows):
    """the numbers as a table a session reads beside the beat sheet"""
    import dense
    lines = [
        f"# {name} - the scene's timing, read frame by frame",
        "",
        f"Generated by `lune run kit vfx breakdown {name} --dense` (do not edit: run it again). Read at the clip's own",
        f"{meta['clip_fps']:g} frames a second; the effect is " + (
            f"what lies in the set's measured hue band ({hue[0]:g}-{hue[1]:g} deg), coloured and lit, or white-hot."
            if hue else "what is brighter than the shot's quiet picture (no measured colours for this set)."),
        "One row per SHOT the beat covers; **bold** = the beat's main shot (its light rises the most over its own",
        "floor). \"At least\" and \"not seen\" mean a cut hid it: the shot opened on the effect or ended while it was lit.",
        "Look at the frames themselves: build/vfx/breakdown/" + name + "_dense/ (private, not in git).",
        "",
        "| Beat | Shot (clip s) | The light arrives | Stays (most of its light) | Goes | Freeze | Drawn | Not read |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        for i, shot in enumerate(row["shots"]):
            w = dense.words(shot["timing"], shot["from"])
            cells = [row["beat"], f"{shot['from']:.2f}-{shot['to']:.2f}", w["arrives"], w["stays"], w["goes"], w["freeze"],
                     w["drawn"], shot.get("note", "")]
            if i == row["main"]:
                cells[:2] = [f"**{cells[0]}**", f"**{cells[1]}**"]
            lines.append("| " + " | ".join(cells) + " |")
        if not row["shots"]:
            lines.append(f"| {row['beat']} | - | no shot of the clip to read in {row['scene'][0]:g}-{row['scene'][1]:g} s | | | | | |")
    return "\n".join(lines) + "\n"


def dense_read(name, rest):
    """lune run kit vfx breakdown <set> --dense: see the head"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import dailies
    import denseclip as DC
    opts = {rest[i]: rest[i + 1] for i in range(0, len(rest) - 1, 2) if rest[i].startswith("--")}
    meta_path = os.path.join(MEASURED, f"{name}.breakdown.json")
    try:
        meta = json.load(open(meta_path, encoding="utf-8"))
    except (OSError, ValueError):
        return out("fail", f"breakdown {name} --dense: no breakdown to read from ({meta_path.replace(os.sep, '/')})",
                   f"lune run kit vfx breakdown {name} --clip <file> first (it finds the cuts the dense read needs)")
    clip = opts.get("--clip") or meta.get("clip")
    if not clip or not os.path.isfile(clip):
        return out("fail", f"breakdown {name} --dense: the scene's clip is not on this machine ({clip})",
                   f"put the owner-approved clip back under assets/effects/refs/{name}/clip/ or pass --clip <file>")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return out("fail", "breakdown --dense: ffmpeg / ffprobe not on PATH", "install ffmpeg (vetted) or put it on PATH")
    beats = beat_rows(name)
    if not beats:
        return out("fail", f"breakdown {name} --dense: no beat with a scene time (no chart, no filled beat sheet)",
                   f"fill assets/effects/refs_measured/{name}.beats.md from the frames, then run this again")
    only = int(opts["--beat"]) if "--beat" in opts else None
    if only is not None and not 0 <= only < len(beats):
        return out("fail", f"breakdown {name} --dense: no beat {only} (there are {len(beats)})", "name a beat, from 0")
    width, cap = max(320, int(opts.get("--tile", 640))), max(4, int(opts.get("--frames", 12)))
    hue = DC.measured_hue(MEASURED, f"{name}_scene", name)
    info = DC.probe(clip)
    cuts = [c["t"] for c in meta.get("cuts", [])]
    out_dir = os.path.join(BUILD, f"{name}_dense")
    os.makedirs(out_dir, exist_ok=True)
    store = os.path.join(MEASURED, f"{name}.timing.json")
    rows = []
    if only is not None and os.path.isfile(store):          # one beat again: the others keep their numbers
        try:
            rows = json.load(open(store, encoding="utf-8")).get("beats", [])
        except (OSError, ValueError):
            rows = []
    if len(rows) != len(beats):
        rows = [None] * len(beats)
    for k, (label, t0, t1, _) in enumerate(beats):          # a stored row is kept only for the beat it was read for
        kept = rows[k]
        if kept is not None and (kept.get("beat") != label or kept.get("scene") != [t0, t1]):
            rows[k] = None
    for k, (label, t0, t1, is_key) in enumerate(beats):
        if only is not None and k != only and rows[k] is not None:
            continue
        for f in os.listdir(out_dir):                        # this beat's earlier pictures
            if f.startswith(f"beat{k}_") and f.endswith(".png"):
                os.remove(os.path.join(out_dir, f))
        if only == k and "--scene-window" in opts:
            a, b = dailies.pair(opts["--scene-window"])
            one = DC.read(clip, a, b, hue, info)
            read = {"shots": [one] if one else [], "main": 0 if one else None}
        else:
            read = DC.read_beat(clip, t0, t1, cuts, hue, info)
        row = {"beat": label, "scene": [t0, t1], "key": is_key, "main": read["main"],
               "shots": [DC.numbers(sh) for sh in read["shots"]], "files": []}
        if read["main"] is not None:
            shot = read["shots"][read["main"]]
            side = {"clip": clip, "info": info, "shot": shot,
                    "name": f"shot {shot['from']:.2f}-{shot['to']:.2f} s at {info[0]:g} fps"}
            row["files"] = dailies.beat(f"{name} - the scene's beat {label}, frame by frame", f"beat{k}", out_dir, side,
                                        None, width, cap)["files"]
        rows[k] = row
    meta_out = {"schema": 1, "set": name, "clip": clip.replace(os.sep, "/"), "clip_fps": round(info[0], 3),
                "hue": list(hue) if hue else None, "beats": rows}
    DC.dump(meta_out, store)
    open(os.path.join(MEASURED, f"{name}.timing.md"), "w", encoding="utf-8", newline="\n").write(
        timing_sheet(name, meta_out, hue, rows))
    look = out_dir.replace(os.sep, "/") + "/"
    shots = sum(len(r["shots"]) for r in rows)
    blind = [r["beat"] for r in rows if r["main"] is None or not r["shots"][r["main"]]["timing"]]
    key = next((r for r in rows if r["key"] and r["main"] is not None), next((r for r in rows if r["main"] is not None), None))
    if key is None:
        return out("fail", f"breakdown {name} --dense: nothing lit up in any beat's shots - this read sees light and the "
                   f"set's colours, not a dark effect. LOOK: {look}",
                   f"check the beats' scene times against build/vfx/breakdown/{name}.png, or read one by hand: --beat <#> --scene-window a,b")
    said = key["shots"][key["main"]]["says"]
    return out("pass", f"breakdown {name} --dense: {len(rows)} beat(s), {shots} shot(s) read at {info[0]:g} frames a second"
               + (f"; not read: {', '.join(blind)}" if blind else "") + f". {key['beat']}: {said}. LOOK: {look}",
               f"open {look}{key['files'][1] if len(key['files']) > 1 else key['files'][0]} onward at full size (two "
               f"consecutive frames a picture), read assets/effects/refs_measured/{name}.timing.md, and time the effect's "
               f"beats from it (the chart's len / hold); then lune run kit vfx dailies <effect> puts ours beside it",
               look=look, timing=store.replace(os.sep, "/"), beats=rows)


def main(argv):
    if not argv or argv[0].startswith("--"):
        return out("fail", "breakdown: needs a set name", "lune run kit vfx breakdown <set> --clip <file> [--fps 2]")
    if "--dense" in argv:
        return dense_read(argv[0], [a for a in argv[1:] if a != "--dense"])
    name = argv[0]
    opts = dict(zip(argv[1::2], argv[2::2]))
    clip = opts.get("--clip")
    if not clip or not os.path.isfile(clip):
        return out("fail", f"breakdown {name}: no clip {clip!r}",
                   f"put the owner-approved clip under assets/effects/refs/{name}/clip/ (vetted yt-dlp, private) and pass --clip <file>")
    if not shutil.which("ffmpeg"):
        return out("fail", "breakdown: ffmpeg not on PATH", "install ffmpeg (vetted) or put it on PATH")
    fps = float(opts.get("--fps", 2))
    start, end = float(opts.get("--from", 0)), (float(opts["--to"]) if "--to" in opts else None)
    threshold, cols = float(opts.get("--cut", 0.35)), int(opts.get("--cols", 6))
    clip_fps, duration = probe(clip)
    length = (end or duration) - start
    if length <= 0:
        return out("fail", f"breakdown {name}: empty window {start}-{end} (clip {duration:.1f} s)", "check --from / --to")
    with tempfile.TemporaryDirectory(prefix="kit_breakdown_") as tmp:
        full = extract(clip, clip_fps, start, end, os.path.join(tmp, "full"), 192)
        cuts = find_cuts(os.path.join(tmp, "full"), full, clip_fps, threshold)
    frames_dir = os.path.join(REFS, f"{name}_scene")
    os.makedirs(frames_dir, exist_ok=True)
    for f in os.listdir(frames_dir):
        if f.startswith("f_") and f.endswith(".png"):
            os.remove(os.path.join(frames_dir, f))  # our own frames from an earlier breakdown (never the owner's)
    with tempfile.TemporaryDirectory(prefix="kit_breakdown_") as tmp:
        names = extract(clip, fps, start, end, tmp, 960)
        times = [round(i / fps, 2) for i in range(len(names))]
        kept = []
        for n, t in zip(names, times):
            m, s = divmod(start + t, 60)
            dest = os.path.join(frames_dir, f"f_{int(m):02d}.{s:05.2f}.png")
            shutil.move(os.path.join(tmp, n), dest)
            kept.append(dest)
    # a sampled frame is a cut frame when a cut falls inside its sampling interval
    cut_set = {t for t in times if any(t - 0.5 / fps < c <= t + 0.5 / fps for c, _ in cuts)}
    sheet = os.path.join(BUILD, f"{name}.png")
    contact_sheet(kept, times, cut_set, cols, sheet)
    bounds = [0.0] + [c for c, _ in cuts] + [round(length, 2)]
    shots = [(a, b) for a, b in zip(bounds, bounds[1:]) if b - a >= 0.05]
    os.makedirs(MEASURED, exist_ok=True)
    beats = os.path.join(MEASURED, f"{name}.beats.md")
    target = beats if not os.path.isfile(beats) else os.path.join(MEASURED, f"{name}.beats.skeleton.md")
    open(target, "w", encoding="utf-8", newline="\n").write(skeleton(name, clip, fps, start, length, shots, frames_dir.replace(os.sep, "/")))
    meta = {"set": name, "clip": clip.replace(os.sep, "/"), "clip_fps": round(clip_fps, 3), "window": [start, round(start + length, 2)],
            "fps": fps, "frames": len(kept), "cuts": [{"t": round(start + c, 2), "distance": d} for c, d in cuts], "threshold": threshold}
    json.dump(meta, open(os.path.join(MEASURED, f"{name}.breakdown.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    return out("pass", f"breakdown {name}: {len(kept)} frames at {fps:g} fps, {len(cuts)} hard cut(s) -> {len(shots)} shot row(s) in "
               f"{target.replace(os.sep, '/')}",
               f"LOOK at {sheet.replace(os.sep, '/')}, fill the beat rows from the frames + {name}.brief.md, then "
               f"lune run kit vfx refs measure {name}_scene and declare \"scene\": {{\"set\": \"{name}\", \"colours\": \"{name}_scene\"}} in the preset",
               sheet=sheet.replace(os.sep, "/"), beats=target.replace(os.sep, "/"), cuts=meta["cuts"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
