"""chart.py — the BEAT CHART: what the owner approves before a whole version is built (mission 02-vfx 5.2).

    lune run kit vfx chart <set> [--duration 6] [--key <beat #>] [--test <png | mp4[@seconds]>] [--replan]

Pros plan an effect on a timing chart before building: keyframes and spacing on a time line, cheap to change there and
expensive after. The chart is drawn from the scene breakdown (refs_measured/<set>.beats.md + the scene frames + the
measured colours):
  * the PLAN: every beat placed on the EFFECT's clock -> refs_measured/<set>.chart.json (written once from the scene
    times scaled to --duration, then YOURS to edit: "t", "len", "hold" (s of hit-stop), "slow" (x slow motion), "key")
  * the time axis with every beat as a block in its own colour, hold / slow-mo marks
  * per beat: the scene frame, its dominant shape (the beat sheet's Shape cell, else measured from the frame: the
    biggest bright region as a streak / wall / disc / ring + its screen share), its colours (swatches), its words
  * per beat: its METHOD PLAN - which methods of the owner's list the beat is made with ("methods"), and any method
    its own words call for that the plan leaves out, with the reason ("not") - in his words (kit/vfx/methods.py)
  * the measured palette of the scene
  * ONE TEST FRAME of the key beat beside the key beat's scene frame (--test a png, or an mp4 recording + the second;
    by default the newest play recording of the preset built from this scene, at the key beat's time)
-> build/vfx/charts/<set>.png, and beside it <set>.drawn.json: WHAT that picture shows - the plan, the measured
   folder it was drawn from, whether it holds a test frame, whether its key beat was only guessed. A chart edited
   after its picture was drawn has a picture of another plan: kit review offers no approval of it until it is drawn
   again, nor of a picture with no test frame.
The owner approves it: lune run kit vfx chart <set> --approve "<his words>" --by owner (the scene gate reads that
record), or his click on the review page (lune run kit review <effect>), which also says which plan he looked at
(--expect-plan) and in which folder (--measured): a chart that is no longer that one is refused.
Prints one JSON line {schema, status, summary, next_action, ...}.
"""

import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import methods as METHODS  # noqa: E402  (the owner's method list and a chart's plan of it)
import gameroot  # noqa: E402

REFS = os.path.join("assets", "effects", "refs")
MEASURED = os.path.join("assets", "effects", "refs_measured")
EFFECTS = os.path.join("assets", "effects")
OUT = gameroot.build("vfx", "charts")  # the active game's build/vfx (card t6rx)
TIME = re.compile(r"^\s*([\d.]+)\s*(?:-\s*([\d.]+))?\s*s\s*$")
W = 1800


def out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status in ("pass", "warn") else 1


def font(size, bold=False):
    for f in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf", "DejaVuSans.ttf"):
        for d in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu"):
            try:
                return ImageFont.truetype(os.path.join(d, f), size)
            except OSError:
                continue
    return ImageFont.load_default()


def parse_beats(path):
    """the beat table: rows whose 2nd cell is a scene time -> [{label, t0, t1, cells{header: text}}]"""
    header, beats = None, []
    for line in open(path, encoding="utf-8"):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None and len(cells) >= 2 and not TIME.match(cells[1]):
            if not set("".join(cells)) <= set("-: "):
                header = cells
            continue
        if len(cells) >= 3 and TIME.match(cells[1]) and cells[2]:
            m = TIME.match(cells[1])
            t0 = float(m.group(1))
            t1 = float(m.group(2)) if m.group(2) else t0 + 0.5
            names = header or [f"c{i}" for i in range(len(cells))]
            beats.append({"label": cells[0], "t0": t0, "t1": max(t1, t0 + 0.1),
                          "cells": {names[i] if i < len(names) else f"c{i}": c for i, c in enumerate(cells)}})
    return beats


def scene_frames(set_name, colours):
    """{clip second: path} of the scene frames: the breakdown's f_mm.ss.png first, else any numbered frames"""
    found = {}
    for d in (f"{set_name}_scene", colours, set_name):
        for p in glob.glob(os.path.join(REFS, d, "f_*.png")):
            m = re.match(r"f_(\d+)\.([\d.]+)\.png$", os.path.basename(p))
            if m:
                found[int(m.group(1)) * 60 + float(m.group(2))] = p
        if found:
            return found
    return found


def nearest(frames, t):
    return frames[min(frames, key=lambda k: abs(k - t))] if frames else None


def frame_read(path):
    """(dominant shape words, top colours, effect share) of a frame: the biggest bright region and its extent; the
    effect share (bright AND saturated pixels) picks the key beat - a washed-out grey impact frame is bright, not the effect"""
    im = Image.open(path).convert("RGB")
    im.thumbnail((320, 320))
    a = np.asarray(im, np.float32)
    lum = a @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    thr = max(150.0, float(np.percentile(lum, 85)))
    mask = lum >= thr
    share = float(mask.mean())
    mx, mn = a.max(axis=-1), a.min(axis=-1)
    energy = float(((lum >= 120) & ((mx - mn) / np.maximum(mx, 1) > 0.35)).mean())  # bright AND saturated = the effect
    cols = []
    if mask.any():
        px = a[mask].astype(np.int32) // 32
        keys, counts = np.unique(px[:, 0] * 64 + px[:, 1] * 8 + px[:, 2], return_counts=True)
        for k in keys[np.argsort(-counts)][:4]:
            cols.append(((k // 64) * 32 + 16, ((k // 8) % 8) * 32 + 16, (k % 8) * 32 + 16))
        cols.sort(key=lambda c: -(max(c) - min(c)))  # the most saturated first: the block colour on the axis
    shape = "nothing bright"
    if share > 0.002:
        from scipy import ndimage

        lab, n = ndimage.label(mask)  # the BIGGEST connected bright region, not every bright pixel's extent
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        big = lab == (int(np.argmax(sizes)) + 1)
        ys, xs = np.nonzero(big)
        w, h = (xs.max() - xs.min() + 1) / mask.shape[1], (ys.max() - ys.min() + 1) / mask.shape[0]
        region = float(big.mean())
        fill = region / max(1e-6, w * h)
        aspect = (max(w * mask.shape[1], h * mask.shape[0])) / max(1.0, min(w * mask.shape[1], h * mask.shape[0]))
        if region > 0.35:
            shape = "wall / fills the frame"
        elif aspect > 3:
            shape = "streak / beam"
        elif fill < 0.3:
            shape = "ring / burst (hollow)"
        else:
            shape = "disc / ball"
        shape += f", {region:.0%} of the frame" + (f" (+{n - 1} more bits)" if n > 1 else "")
    return shape, cols, energy


def same_folder(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def drawn_record(set_name):
    """what the picture on this machine shows (written when it was drawn), or None"""
    try:
        made = json.load(open(os.path.join(OUT, f"{set_name}.drawn.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return made if isinstance(made, dict) else None


def plan_key(P):
    """the chart's plan as one comparable line: the duration, then each beat's t, len, hold and key (the scene gate,
    kit/cmd/content.luau chartPlanKey, writes the same text to compare with what the owner approved)"""
    return f"{float(P.get('duration') or 0):.2f}|" + ";".join(
        f"{float(b.get('t') or 0):.2f},{float(b.get('len') or 0):.2f},{float(b.get('hold') or 0):.2f},{1 if b.get('key') else 0}"
        for b in P.get("beats", []) if isinstance(b, dict))


def plan(beats, duration, key):
    """the scene times scaled onto the effect's clock (long establishing shots squeezed: each beat >= 0.15 s)"""
    t_first, t_last = beats[0]["t0"], beats[-1]["t1"]
    span = max(0.1, t_last - t_first)
    rows = []
    for i, b in enumerate(beats):
        motion = " ".join(v for k, v in b["cells"].items() if "otion" in k or "hold" in k.lower() or k == "Beat").lower()
        rows.append({"beat": b["label"], "scene": [b["t0"], b["t1"]],
                     "t": round((b["t0"] - t_first) / span * duration, 2),
                     "len": round(max(0.15, (b["t1"] - b["t0"]) / span * duration), 2),
                     "hold": 0.1 if re.search(r"(?<!no )\b(hold|freeze|hit-?stop|impact frame)\b", motion) else 0.0,  # "no hold" is not a hold
                     "slow": 2.0 if re.search(r"\bslow", motion) else 1.0,
                     "key": i == key})
    return {"schema": 1, "duration": duration,
            "about": "the effect's clock per beat - EDIT these (t, len, hold s, slow x, key) and re-run kit vfx chart; the scene times stay the breakdown's",
            "beats": rows}


def test_frame(spec, set_name, key_t, tmp):
    """a png, or an mp4 at a second; default: the newest PLAYER recording of a preset built from this scene"""
    if spec:
        path, _, at = spec.partition("@")
        if path.lower().endswith((".png", ".jpg", ".jpeg")):
            return path if os.path.isfile(path) else None, path
        at = float(at) if at else key_t
    else:
        built = []
        for p in glob.glob(os.path.join(EFFECTS, "*.json")):
            try:
                d = json.load(open(p, encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(d, dict) and isinstance(d.get("scene"), dict) and d["scene"].get("set") == set_name:
                built.append(os.path.basename(p)[:-5])
        recs = [r for n in built for r in glob.glob(os.path.join("build", "vfx", "booth", f"{n}_play_hero.mp4"))]
        if not recs:
            return None, f"no recording of a preset built from {set_name}"
        path, at = max(recs, key=os.path.getmtime), key_t
    if not os.path.isfile(path):
        return None, path
    dest = os.path.join(tmp, "test.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", path, "-frames:v", "1", dest], timeout=120)
    return (dest if os.path.isfile(dest) else None), f"{path.replace(os.sep, '/')} @ {at:.2f} s"


def fit(im, w, h):
    im = im.copy()
    im.thumbnail((w, h))
    canvas = Image.new("RGB", (w, h), (12, 12, 16))
    canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return canvas


def method_lines(P, by, per_line):
    """per beat row of the plan: [(text, is a left-out method)] - what the beat is made with and what it leaves out,
    in the owner's words; a beat with no plan says so"""
    rows = []
    for row in P.get("beats", []):
        made = [by[m]["name"] if m in by else f"?? {m}" for m in METHODS.ids_of(row.get("methods"))]
        lines = [(ln, False) for ln in wrap("made with: " + (" · ".join(made) if made else "NO METHOD PLANNED"), per_line)]
        for mid, why in METHODS.nots_of(row.get("not")).items():
            lines += [(ln, True) for ln in wrap(f"NOT {by[mid]['name'] if mid in by else mid}: {why}", per_line)]
        rows.append(lines)
    return rows


def draw(set_name, beats, P, frames, reads, measured, test, test_src, dest, by=None):
    f_t, f_b, f_s = font(30, True), font(19, True), font(16)
    n = len(beats)
    col_w = (W - 40) // n
    th = round(col_w * 9 / 16)
    made = method_lines(P, by or {}, max(10, col_w // 9))
    band = 20 * max(len(m) for m in made) + 16  # the method plan's rows, under each beat's words: never cut short
    H = 980 + th + band
    img = Image.new("RGB", (W, H), (22, 22, 28))
    d = ImageDraw.Draw(img)
    dur = P["duration"]
    d.text((20, 14), f"BEAT CHART — {set_name}   ({n} beats, {dur:g} s on the effect's clock)", font=f_t, fill=(240, 240, 245))
    d.text((20, 54), "approve before building: lune run kit verdict vfx " + set_name + ' <0-10> "<words>" --tag chart', font=f_s, fill=(170, 170, 185))
    # the time axis
    x0, x1, ya = 20, W - 20, 120
    d.line([x0, ya + 40, x1, ya + 40], fill=(120, 120, 135), width=2)
    for s in range(int(dur) + 1):
        x = x0 + (x1 - x0) * s / dur
        d.line([x, ya + 34, x, ya + 46], fill=(150, 150, 165), width=2)
        d.text((x + 3, ya + 48), f"{s} s", font=f_s, fill=(150, 150, 165))
    for i, (b, row) in enumerate(zip(beats, P["beats"])):
        bx0 = x0 + (x1 - x0) * row["t"] / dur
        bx1 = x0 + (x1 - x0) * min(dur, row["t"] + row["len"]) / dur
        c = reads[i][1][0] if reads[i][1] else (90, 90, 100)
        d.rectangle([bx0, ya, max(bx0 + 4, bx1 - 2), ya + 32], fill=tuple(int(v) for v in c), outline=(255, 215, 80) if row.get("key") else (0, 0, 0), width=3 if row.get("key") else 1)
        d.text((bx0 + 4, ya + 6), str(i), font=f_b, fill=(0, 0, 0) if sum(c) > 380 else (255, 255, 255))
        if row.get("hold"):
            d.text((bx0, ya - 26), f"HOLD {row['hold']:g}s", font=f_s, fill=(255, 120, 120))
        if row.get("slow", 1) != 1:
            d.text((bx0, ya - 26 if not row.get("hold") else ya - 46), f"SLOW x{row['slow']:g}", font=f_s, fill=(120, 200, 255))
    # per beat columns
    yc = 210
    for i, b in enumerate(beats):
        x = 20 + i * col_w
        row = P["beats"][i]
        if frames[i]:
            img.paste(fit(Image.open(frames[i]).convert("RGB"), col_w - 8, th), (x, yc))
        d.rectangle([x, yc, x + col_w - 9, yc + th], outline=(255, 215, 80) if row.get("key") else (60, 60, 70), width=3 if row.get("key") else 1)
        yy = yc + th + 6
        label = re.sub(rf"^{i}\s+", "", b["label"])  # "0 awakening" -> "awakening" (the number is drawn already)
        d.text((x, yy), f"{i}  {label[:22]}", font=f_b, fill=(240, 240, 245))
        d.text((x, yy + 24), f"scene {b['t0']:g}-{b['t1']:g} s  ->  {row['t']:g} s (+{row['len']:g})", font=f_s, fill=(170, 170, 185))
        for k, c in enumerate(reads[i][1]):
            d.rectangle([x + k * 34, yy + 48, x + k * 34 + 30, yy + 70], fill=tuple(int(v) for v in c))
        written = next((v for k, v in b["cells"].items() if k.lower().startswith("shape") and v), None)
        per_line = max(10, col_w // 9)  # the beat sheet's Shape cell wins; a frame read is only a rough measure
        shape_lines = wrap(f"shape: {written}" if written else f"frame read: {reads[i][0]}", per_line)[:2]
        words = next((v for k, v in b["cells"].items() if "screen" in k.lower() or "vision" in k.lower()), "")
        lines = shape_lines + wrap(words, per_line)[:7]
        for k, ln in enumerate(lines):
            d.text((x, yy + 78 + k * 20), ln, font=f_s, fill=(255, 215, 80) if k < len(shape_lines) else (215, 215, 225))
        for k, (ln, left_out) in enumerate(made[i]):
            d.text((x, yc + th + 262 + k * 20), ln, font=f_s, fill=(255, 140, 120) if left_out else (140, 220, 160))
    # palette + test frame
    yp = yc + th + 260 + band
    d.text((20, yp), "scene palette (measured)", font=f_b, fill=(240, 240, 245))
    # (an empty luminance band has no colour - rgb None: a grey footage's measurement crashed the chart, 2026-11-10)
    for k, band in enumerate([b for b in (measured or {}).get("bands", []) if b.get("rgb")][:6]):
        c = tuple(band["rgb"])
        d.rectangle([20 + k * 110, yp + 30, 120 + k * 110, yp + 90], fill=c)
        d.text((20 + k * 110, yp + 94), f"{band['share']:.0%}", font=f_s, fill=(200, 200, 210))
    key = next((i for i, r in enumerate(P["beats"]) if r.get("key")), 0)
    tw, tht = 520, 293
    tx = W - 20 - 2 * tw - 20
    d.text((tx, yp), f"KEY BEAT {key}: the scene", font=f_b, fill=(255, 215, 80))
    d.text((tx + tw + 20, yp), "TEST FRAME (the effect)", font=f_b, fill=(255, 215, 80))
    if frames[key]:
        img.paste(fit(Image.open(frames[key]).convert("RGB"), tw, tht), (tx, yp + 30))
    if test:
        img.paste(fit(Image.open(test).convert("RGB"), tw, tht), (tx + tw + 20, yp + 30))
    else:
        d.rectangle([tx + tw + 20, yp + 30, tx + 2 * tw + 20, yp + 30 + tht], outline=(255, 90, 90), width=3)
        d.text((tx + tw + 40, yp + 120), "NO TEST FRAME YET", font=f_b, fill=(255, 90, 90))
        d.text((tx + tw + 40, yp + 150), "build ONLY the key beat, record it,", font=f_s, fill=(220, 220, 230))
        d.text((tx + tw + 40, yp + 172), "then: kit vfx chart <set> --test <mp4@s>", font=f_s, fill=(220, 220, 230))
    d.text((tx + tw + 20, yp + 36 + tht), (test_src or "")[:70], font=f_s, fill=(150, 150, 165))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    img.save(dest)


def wrap(text, n):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n and cur:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + ([cur] if cur else [])


def main(argv):
    if not argv or argv[0].startswith("--"):
        return out("fail", "chart: needs a set name", "lune run kit vfx chart <set> [--duration 6] [--key N] [--test <png|mp4@s>]")
    set_name = argv[0]
    opts = dict(zip(argv[1::2], argv[2::2]))
    # a game's own set lives in its folder (KIT_GAME / games/.active), the project's at the root - the scene gate
    # reads the chart beside the game's presets (kit verify: games/<Name>/assets/effects/refs_measured)
    global MEASURED, EFFECTS
    g = os.environ.get("KIT_GAME")
    if not g or g == "none":
        ap = os.path.join("games", ".active")
        g = open(ap, encoding="utf-8").read().strip() if os.path.isfile(ap) and g != "none" else ""
    gfx = os.path.join("games", g, "assets", "effects") if g and g != "none" else None
    if gfx and any(os.path.isfile(os.path.join(gfx, "refs_measured", f"{set_name}{ext}")) for ext in (".beats.md", ".chart.json")):
        MEASURED, EFFECTS = os.path.join(gfx, "refs_measured"), gfx
    if opts.get("--measured"):  # the folder the caller READ the chart in (kit review): the one it is approved in
        MEASURED = opts["--measured"]
        EFFECTS = os.path.dirname(os.path.normpath(MEASURED)) or "."  # (its presets stand beside it)
    if "--approve" in opts:  # the owner's approval of the chart: a build of a preset from this scene needs it
        plan_path = os.path.join(MEASURED, f"{set_name}.chart.json")
        if not os.path.isfile(plan_path):
            return out("fail", f"chart {set_name}: nothing to approve - no {plan_path}", f"lune run kit vfx chart {set_name}")
        words = opts["--approve"].strip()
        if not words:
            return out("fail", "chart --approve: the owner's words are the record", f"lune run kit vfx chart {set_name} --approve \"<the owner's words>\"")
        P = json.load(open(plan_path, encoding="utf-8"))
        # a yes is for the chart that was LOOKED AT: a caller that knows which plan that was says so (kit review), and
        # a chart re-timed between the look and this command is refused
        if "--expect-plan" in opts:
            if opts["--expect-plan"] != plan_key(P):
                return out("fail", f"chart {set_name}: not the chart that was looked at - its plan is now {plan_key(P)}",
                           f"draw it again (lune run kit vfx chart {set_name}), look, then approve")
            # ... and the PICTURE that was looked at is this chart's: of this plan, drawn from this folder
            made = drawn_record(set_name)
            if not made or made.get("plan") != plan_key(P) or not same_folder(str(made.get("measured") or ""), MEASURED):
                return out("fail", f"chart {set_name}: the picture on this machine is not of this chart as it is now "
                           f"({'no record of what it shows' if not made else 'it shows ' + str(made.get('plan')) + ' from ' + str(made.get('measured'))})",
                           f"draw it again (lune run kit vfx chart {set_name}), look, then approve")
        # only the OWNER approves (the quality locks): without --by owner the record is a model's proposal, which the
        # scene gate refuses
        by = opts.get("--by", "").strip()
        # exactly "owner" (2026-11-11): "owner blanket approval ..." was an agent's label on a chart he never saw, and the
        # old prefix rule counted it as his. The approval keeps the PLAN he saw (plan_key): a re-timed chart is another chart
        by = "owner" if by.lower() == "owner" else "model-proposed"
        # the METHOD PLAN is part of what he approves (2026-11-13): the approval keeps the plan he saw, and a chart
        # that carries a plan is approved only from a picture that shows that plan
        plan_seen = METHODS.snapshot(P)
        if plan_seen:
            made = drawn_record(set_name)
            if not made or made.get("methods") != plan_seen or not same_folder(str(made.get("measured") or ""), MEASURED):
                return out("fail", f"chart {set_name}: the picture on this machine does not show this chart's method plan "
                           f"({'no picture drawn here' if not made else 'it was drawn before the plan was as it is now'})",
                           f"draw it again (lune run kit vfx chart {set_name}), show it, then approve")
        P["approved"] = {"by": by, "date": time.strftime("%Y-%m-%d"), "words": words, "plan": plan_key(P)}
        if plan_seen and by == "owner":  # (only HIS approval holds a plan he saw: the method gate reads it as his)
            P["approved"]["methods"] = plan_seen
        if opts.get("--via"):  # how the record was made, when not typed (kit review's page: "review-page")
            P["approved"]["via"] = opts["--via"].strip()
        json.dump(P, open(plan_path, "w", encoding="utf-8", newline="\n"), indent=1)
        if by == "model-proposed":
            return out("pass", f"chart {set_name}: PROPOSED, not approved (the build refuses a model-proposed chart)",
                       f"show build/vfx/charts/{set_name}.png to the owner; their approval: lune run kit vfx chart {set_name} --approve \"<the owner's words>\" --by owner",
                       approved=P["approved"])
        return out("pass", f"chart {set_name}: approved by {P['approved']['by']} ({P['approved']['date']})",
                   "build the version from the chart: the preset declares \"scene\": {\"set\": \"" + set_name + "\"}", approved=P["approved"])
    beats_path = os.path.join(MEASURED, f"{set_name}.beats.md")
    if not os.path.isfile(beats_path):
        return out("fail", f"chart {set_name}: no beat sheet {beats_path}", f"lune run kit vfx breakdown {set_name} --clip <file>, then fill the beat rows")
    beats = parse_beats(beats_path)
    if len(beats) < 2:
        return out("fail", f"chart {set_name}: {len(beats)} filled beat row(s) in {beats_path}", "fill the 'on screen' cell of every beat row from the frames")
    # the measured colours: the preset built from this scene names them; else <set>_scene / <set>
    colours = None
    for p in glob.glob(os.path.join(EFFECTS, "*.json")):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(d, dict) and isinstance(d.get("scene"), dict) and d["scene"].get("set") == set_name:
            colours = d["scene"].get("colours") or set_name
    for c in (colours, f"{set_name}_scene", set_name):
        if c and os.path.isfile(os.path.join(MEASURED, f"{c}.json")):
            colours = c
            break
    measured = json.load(open(os.path.join(MEASURED, f"{colours}.json"), encoding="utf-8")) if colours and os.path.isfile(os.path.join(MEASURED, f"{colours}.json")) else None
    fr = scene_frames(set_name, colours)
    frames = [nearest(fr, (b["t0"] + b["t1"]) / 2) for b in beats]
    reads = [frame_read(f) if f else ("no scene frame", [], 0.0) for f in frames]
    plan_path = os.path.join(MEASURED, f"{set_name}.chart.json")
    guessed = False
    if os.path.isfile(plan_path) and "--replan" not in argv:
        P = json.load(open(plan_path, encoding="utf-8"))
        if len(P.get("beats", [])) != len(beats):
            return out("fail", f"chart {set_name}: the plan has {len(P.get('beats', []))} beats, the beat sheet {len(beats)}",
                       f"edit {plan_path} to match, or re-run with --replan (overwrites your timing edits)")
    else:
        marked = [i for i, b in enumerate(beats) if re.search(r"\bkey\b|★", b["label"], re.I)]
        key = int(opts["--key"]) if "--key" in opts else (marked[0] if marked else int(np.argmax([r[2] for r in reads])))
        guessed = "--key" not in opts and not marked
        P = plan(beats, float(opts.get("--duration", 6)), key)
        if os.path.isfile(plan_path):  # --replan: the timing is made again, each beat's METHOD PLAN is kept (by its number)
            try:
                before = METHODS.plan_of(json.load(open(plan_path, encoding="utf-8")))
            except (OSError, ValueError, AttributeError):
                before = {}
            for row in P["beats"]:
                kept = before.get(METHODS.beat_id(row.get("beat")))
                if kept and kept["methods"]:
                    row["methods"] = kept["methods"]
                if kept and kept["not"]:
                    row["not"] = kept["not"]
        json.dump(P, open(plan_path, "w", encoding="utf-8", newline="\n"), indent=1)
    if "--key" in opts:  # the author's pick of the key beat is part of the plan
        for i, r in enumerate(P["beats"]):
            r["key"] = i == int(opts["--key"])
        P.pop("approved", None)  # another key beat is another chart: it needs the owner's approval again
        json.dump(P, open(plan_path, "w", encoding="utf-8", newline="\n"), indent=1)
    key = next((i for i, r in enumerate(P["beats"]) if r.get("key")), 0)
    with tempfile.TemporaryDirectory(prefix="kit_chart_") as tmp:
        test, src = test_frame(opts.get("--test"), set_name, P["beats"][key]["t"] + P["beats"][key]["len"] / 2, tmp)
        dest = os.path.join(OUT, f"{set_name}.png")
        try:
            _, by_id = METHODS.load()
        except (OSError, ValueError):
            by_id = {}
        draw(set_name, beats, P, frames, reads, measured, test, src if test else None, dest, by_id)
        # what this picture shows: its plan (a chart edited afterwards has a picture of ANOTHER plan), the folder it
        # was drawn from (the picture's file is one per set NAME: a game's set of the same name draws over it), and
        # whether it is the picture he is asked to approve - with its test frame, its key beat not a guess
        try:
            where = os.path.relpath(MEASURED)
        except ValueError:  # (another drive than the project's: no relative form)
            where = os.path.abspath(MEASURED)
        json.dump({"plan": plan_key(P), "measured": where.replace(os.sep, "/"), "test": bool(test),
                   "guessed": bool(guessed), "methods": METHODS.snapshot(P)},
                  open(os.path.join(OUT, f"{set_name}.drawn.json"), "w", encoding="utf-8", newline="\n"))
    missing = sum(1 for f in frames if not f)
    # the method plan's open points: a build from this chart is refused on them (the method gate)
    open_plan = METHODS.plan_problems(by_id, METHODS.plan_of(P), METHODS.beat_words(beats_path), None, set_name) if by_id else []
    status = "pass" if test and not missing and not guessed and not open_plan else "warn"
    why = ([f"key beat GUESSED from the frames (mark it in the beat sheet or pass --key N)"] if guessed else [])         + (["no test frame of the key beat"] if not test else []) + ([f"the method plan has {len(open_plan)} open point(s) (lune run kit vfx methods --set {set_name})"] if open_plan else []) + ([f"{missing} beat(s) without a scene frame"] if missing else [])
    return out(status, f"chart {set_name}: {len(beats)} beats on {P['duration']:g} s, key beat {key} ({beats[key]['label']})"
               + (f" — {'; '.join(why)}" if why else ""),
               f"LOOK at {dest.replace(os.sep, '/')}; " + ("build ONLY the key beat and pass --test <mp4@s>, then " if not test else "")
               + f"show it to the owner (lune run kit review <the effect>); his yes: lune run kit vfx chart {set_name} "
               "--approve \"<his words>\" --by owner",
               chart=dest.replace(os.sep, "/"), plan=plan_path.replace(os.sep, "/"), test=src)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
