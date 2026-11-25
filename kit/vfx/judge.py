"""judge.py — the VERIFIER (mission 02-vfx 5.10): a fresh context holds the render up against the SCENE, beat by
beat, and names ONE difference and ONE edit per beat. No score: scoring judges plateau in noise (the kit's own
judge noise was +-1.5; UI judges underrated the owner by 30-45) and a number invites polishing the number. The
owner's words come first; the verifier only points at the next edit.

    python kit/vfx/judge.py packet --name <preset> --out build/judge/vfx/<preset> [--booth build/vfx/booth]
                                   [--effects assets/effects] [--refs assets/effects/refs]
        gathers the evidence: the OWNER'S ANCHOR (their latest words on this effect, library/vfx/verdicts.json), the
        PLAYER's recorded sheets <name>_play_<view>.png (mission 02-vfx v2: the player is the studio; Studio booth
        sheets are not evidence), and the BEATS: the preset's scene chart (refs_measured/<set>.chart.json: every beat's
        time on the effect clock) with the scene's own frame for each beat (the breakdown's frames), else the
        preset's hit-stops / hits as beats and the reference stills in assets/effects/refs/<preset>/. Every beat gets a
        DETAIL CROP (detail_beatNN.png: the player's frame at that time zoomed onto the effect) beside the scene's own
        (scene_detail_beatNN.png). Writes PROMPT.md.
    python kit/vfx/judge.py record --name <preset> --packet <dir> --verdict verdict.json [--effects assets/effects]
        validates the answer (every beat: where it is, the ONE difference seen, the ONE edit; no scores anywhere;
        the verifier's identity) and keeps it as assets/effects/judge/<preset>.json tied to the sheets it saw
        (hashes), so a later recording invalidates it.
Prints one JSON line: {status, summary, next_action, ...}.
"""

import glob
import hashlib
import json
import os
import re
import shutil
import sys
import time

MEASURED = os.path.join("assets", "effects", "refs_measured")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def out_json(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def opts_of(argv, defaults):
    o = dict(defaults)
    i = 0
    while i < len(argv):
        if argv[i].startswith("--") and i + 1 < len(argv):
            o[argv[i]] = argv[i + 1]
            i += 2
        else:
            i += 1
    return o


def owner_anchor(name):
    """the owner's latest words on this effect (or its family), newest first"""
    try:
        v = json.load(open(os.path.join("library", "vfx", "verdicts.json"), encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for key in (name, re.sub(r"_(v\d+|present\w*|surface)$", "", name)):
        entries = v.get(key)
        if entries:
            last = entries[-1] if isinstance(entries, list) else entries
            return {"effect": key, "date": last.get("date"), "words": last.get("words"), "score": last.get("score")}
    return None


def scene_beats(preset):
    """[(label, effect_t, scene_frame_path or None, scene words)] from the preset's scene chart; else hit-stops / hits"""
    scene = preset.get("scene") if isinstance(preset.get("scene"), dict) else None
    if scene and scene.get("set"):
        st = scene["set"]
        plan_path = os.path.join(MEASURED, f"{st}.chart.json")
        if os.path.isfile(plan_path):
            plan = json.load(open(plan_path, encoding="utf-8"))
            frames = {}
            for d in (f"{st}_scene", scene.get("colours") or st, st):
                for p in glob.glob(os.path.join("assets", "effects", "refs", d, "f_*.png")):
                    m = re.match(r"f_(\d+)\.([\d.]+)\.png$", os.path.basename(p))
                    if m:
                        frames[int(m.group(1)) * 60 + float(m.group(2))] = p
                if frames:
                    break
            out = []
            for b in plan.get("beats", []):
                mid = sum(b["scene"]) / 2
                f = frames[min(frames, key=lambda k: abs(k - mid))] if frames else None
                out.append((b["beat"], round(b["t"] + b["len"] / 2, 2), f, f"scene {b['scene'][0]:g}-{b['scene'][1]:g} s" + (" - KEY" if b.get("key") else "")))
            return out, f"the scene chart {plan_path.replace(os.sep, '/')}"
    beats = []
    for h in preset.get("hitstop") or []:
        if isinstance(h.get("at"), (int, float)):
            beats.append((f"hit-stop at {h['at']:g} s", float(h["at"]), None, "a hit-stop"))
    for h in preset.get("hits") or []:
        t = h if isinstance(h, (int, float)) else (h.get("t") if isinstance(h, dict) else None)
        if isinstance(t, (int, float)):
            beats.append((f"hit at {t:g} s", float(t), None, "a hit"))
    merged = []  # a hit-stop and a hit at the same moment are one beat
    for b in sorted(beats, key=lambda x: x[1]):
        if merged and abs(merged[-1][1] - b[1]) < 0.05:
            continue
        merged.append(b)
    beats = merged
    if not beats:
        d = float(preset.get("duration") or 2)
        beats = [("build", round(d * 0.2, 2), None, ""), ("peak", round(d * 0.45, 2), None, ""), ("tail", round(d * 0.8, 2), None, "")]
    return beats, "no scene chart: the preset's hit-stops / hits (declare \"scene\" and run kit vfx chart for scene frames per beat)"


PLAYER_FPS = 24  # kit vfx play --record: frames <view>_NNN.jpg, 1-based, 24 per second


def player_frames(booth, name):
    """the newest player recording's frames for the preferred view (hero, then cine, then any): ([paths], view)"""
    d = os.path.join(booth, f"{name}_play")
    if not os.path.isdir(d):
        return [], None
    by_view = {}
    for f in sorted(os.listdir(d)):
        m = re.fullmatch(r"([a-z0-9]+)_(\d+)\.(jpg|png)", f)
        if m:
            by_view.setdefault(m.group(1), []).append(os.path.join(d, f))
    for v in ("hero", "cine", *sorted(by_view)):
        if by_view.get(v):
            return by_view[v], v
    return [], None


def detail_crop(src, dst, size=768):
    """zoom onto the effect: the bounding box of its bright / saturated pixels (2-98 % quantiles, so a stray spark
    does not widen it) plus a margin, scaled to `size` on the long side. Returns the file name or None."""
    try:
        from PIL import Image
    except ImportError:
        return None
    im = Image.open(src).convert("RGB")
    w, h = im.size
    small = im.resize((w // 4, h // 4))
    hsv = small.convert("HSV")
    vals = sorted(p[2] for p in hsv.getdata())
    floor = max(90, vals[len(vals) // 2] + 60)  # brighter than the frame's median: the effect, not the ground
    xs, ys = [], []
    sw = small.width
    for i, (_, s, v) in enumerate(hsv.getdata()):
        if v >= floor and (s >= 90 or v >= 200):
            xs.append(i % sw)
            ys.append(i // sw)
    if len(xs) < 12:
        box = (0, 0, w, h)
    else:
        xs.sort()
        ys.sort()
        q = lambda a, f: a[min(len(a) - 1, int(f * len(a)))] * 4
        x0, x1, y0, y1 = q(xs, 0.02), q(xs, 0.98) + 4, q(ys, 0.02), q(ys, 0.98) + 4
        mx, my = max(24, (x1 - x0) // 8), max(24, (y1 - y0) // 8)
        x0, y0, x1, y1 = max(0, x0 - mx), max(0, y0 - my), min(w, x1 + mx), min(h, y1 + my)
        if x1 - x0 < w // 5:  # never zoom past 5x: the crop must still show the shape around the detail
            c = (x0 + x1) // 2
            x0, x1 = max(0, c - w // 10), min(w, c + w // 10)
        if y1 - y0 < h // 5:
            c = (y0 + y1) // 2
            y0, y1 = max(0, c - h // 10), min(h, c + h // 10)
        box = (x0, y0, x1, y1)
    crop = im.crop(box)
    k = size / max(crop.size)
    crop = crop.resize((max(1, round(crop.width * k)), max(1, round(crop.height * k))), Image.LANCZOS)
    crop.save(dst)
    return os.path.basename(dst)


def details_board(out, beats, details, cell=560):
    """ONE picture of every beat's details: a row per beat, the render's detail crop left, the scene's right, each
    row labelled - so a verifier on an image budget reads one file instead of two per beat. Returns its name."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    rows = [(b, d) for b, d in zip(beats, details) if d[0] or d[1]]
    if not rows:
        return None
    rh, lab = round(cell * 9 / 16), 22
    img = Image.new("RGB", (cell * 2 + 12, len(rows) * (rh + lab + 6)), (14, 14, 16))
    dr = ImageDraw.Draw(img)
    for i, ((label, t, _, _), (a, b)) in enumerate(rows):
        y = i * (rh + lab + 6)
        dr.text((6, y + 4), f"{label} - t = {t:g} s   |   left: the render (player)   right: the scene", fill=(235, 235, 235))
        for j, f in enumerate((a, b)):
            if not f:
                continue
            im = Image.open(os.path.join(out, f)).convert("RGB")
            k = min(cell / im.width, rh / im.height)
            im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))))
            img.paste(im, (j * (cell + 12) + (cell - im.width) // 2, y + lab + (rh - im.height) // 2))
    img.save(os.path.join(out, "details.png"))
    return "details.png"


def packet(argv):
    o = opts_of(argv, {"--booth": "build/vfx/booth", "--effects": "assets/effects", "--refs": "assets/effects/refs", "--out": None, "--name": None})
    name = o["--name"]
    if not name:
        return out_json("fail", "vfx judge: name the preset", "lune run kit vfx judge <name>")
    out = o["--out"] or os.path.join("build", "judge", "vfx", name)
    preset_path = os.path.join(o["--effects"], f"{name}.json")
    if not os.path.isfile(preset_path):
        return out_json("fail", f"vfx judge: no preset {preset_path}", "lune run kit new vfx <name>")
    with open(preset_path, encoding="utf-8") as fh:
        preset = json.load(fh)
    # a sheet recorded BEFORE the preset's (or a part's) last edit shows another effect: it is stale, not evidence
    edited = os.path.getmtime(preset_path)
    parts_dir = os.path.join(o["--effects"], "parts")
    if os.path.isdir(parts_dir):
        edited = max([edited] + [os.path.getmtime(os.path.join(parts_dir, f)) for f in os.listdir(parts_dir)])
    # mission 02-vfx v2: the PLAYER is the studio - only its recordings are evidence (a Studio booth sheet is not)
    sheets, stale = [], []
    for f in sorted(glob.glob(os.path.join(o["--booth"], f"{name}_play_*.png"))):
        if not re.fullmatch(rf"{re.escape(name)}_play_([a-z0-9]+)\.png", os.path.basename(f)):
            continue
        (sheets if os.path.getmtime(f) >= edited else stale).append((f, "player"))
    if not sheets:
        return out_json("fail", f"vfx judge: no player recording of {name} newer than its last edit ({len(stale)} stale) in {o['--booth']}",
                        f"record it first: lune run kit vfx play {name} --record")
    beats, beats_from = scene_beats(preset)
    os.makedirs(out, exist_ok=True)
    for f in glob.glob(os.path.join(out, "*")):
        if os.path.isfile(f):
            os.remove(f)
    copied, hashes = [], {}
    for f, source in sheets:
        dst = os.path.join(out, f"sheet_{source}_{os.path.basename(f)}")
        shutil.copyfile(f, dst)
        copied.append((dst, source))
        hashes[os.path.basename(f)] = sha(f)
    scene_copies, details = [], []
    frames, view = player_frames(o["--booth"], name)
    for i, (label, t, frame, words) in enumerate(beats):
        if frame:
            dst = os.path.join(out, f"scene_beat{i:02d}{os.path.splitext(frame)[1].lower()}")
            shutil.copyfile(frame, dst)
            scene_copies.append(os.path.basename(dst))
        else:
            scene_copies.append(None)
        # DETAILS FIRST (v2 direction 3): the effect at full resolution, zoomed, beside the scene's own detail
        d_render = d_scene = None
        if frames:
            src = frames[min(len(frames) - 1, max(0, round(t * PLAYER_FPS)))]
            d_render = detail_crop(src, os.path.join(out, f"detail_beat{i:02d}.png"))
        if frame:
            d_scene = detail_crop(frame, os.path.join(out, f"scene_detail_beat{i:02d}.png"))
        details.append((d_render, d_scene))
    board = details_board(out, beats, details)
    refs = []
    for ext in ("png", "jpg", "jpeg", "webp"):
        refs += sorted(glob.glob(os.path.join(o["--refs"], name, f"*.{ext}")))
    ref_copies = []
    for i, f in enumerate(refs[:8]):
        dst = os.path.join(out, f"ref_{i + 1:02d}{os.path.splitext(f)[1].lower()}")
        shutil.copyfile(f, dst)
        ref_copies.append(os.path.basename(dst))
    anchor = owner_anchor(name)
    lines = [
        f"# VFX verifier packet — {name}",
        "",
        "You are a FRESH verifier. You did not build this. Do NOT score it. For every beat below, hold the render's",
        "frame at that time up against the scene's own frame for the same beat and name the ONE most visible",
        "difference and the ONE concrete edit to the preset / texture that closes it. Located, specific, no praise.",
        "",
        "## The owner's anchor (their words decide; you only point at the next edit)",
        (f"- {anchor['effect']} ({anchor['date']}): \"{anchor['words']}\"" if anchor else "- no owner verdict on this effect yet"),
        "",
        "## The effect's intent",
        f"- about: {preset.get('about', '-')}",
        f"- duration {preset.get('duration', '-')} s, {len(preset.get('layers', []))} layers; hit-stop: {preset.get('hitstop', '-')}",
        "",
        "## Evidence (time runs left to right, top to bottom; each frame prints its time)",
    ]
    for dst, source in copied:
        lines.append(f"- `{os.path.basename(dst)}` — the browser player's recording: the effect alone, as the owner sees it")
    if stale:
        lines.append(f"- NOT included: {len(stale)} sheet(s) older than the preset's last edit")
    lines += ["", f"## Beats ({beats_from})",
              "Each beat has a DETAIL CROP: the player's frame at that time, zoomed onto the effect - and the scene's own",
              "detail beside it. The owner's complaint is the SMALL details (edges, sparks, embers, bands, ink): name the",
              "difference you see in the detail crops, not only the silhouette."
              + (f" All of them on one picture: `{board}` (a row per beat, render left, scene right) - start there." if board else "")]
    for (label, t, _, words), sc, (dr, ds) in zip(beats, scene_copies, details):
        lines.append(f"- **{label}** — the render at t = {t:g} s" + (f"; the scene's frame: `{sc}`" if sc else "") + (f" ({words})" if words else "")
                     + (f"; detail: `{dr}`" if dr else "") + (f" beside the scene's detail `{ds}`" if ds else ""))
    if ref_copies:
        lines += ["", "## Reference stills (the look-target): " + ", ".join(f"`{r}`" for r in ref_copies)]
    lines += [
        "",
        "## Answer — exactly this JSON (then `lune run kit vfx judge " + name + " --record <file>`)",
        "```json",
        json.dumps({
            "verifier": "<model@harness>",
            "beats": [{"beat": label, "t": t, "difference": "<the one most visible difference, seen in which sheet / frame>",
                       "edit": "<the one concrete change: layer / texture / timing / colour>"} for label, t, _, _ in beats],
            "first": "<which beat's edit to make first, and why (the owner's anchor decides ties)>",
        }, indent=1),
        "```",
        "No scores, no 'overall', no grades: a number here is a bug. One difference and one edit per beat.",
    ]
    with open(os.path.join(out, "PROMPT.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(os.path.join(out, "packet.json"), "w", encoding="utf-8") as fh:
        json.dump({"name": name, "sheets": hashes, "beats": [{"beat": b[0], "t": b[1]} for b in beats], "anchor": anchor,
                   "made": time.strftime("%Y-%m-%d %H:%M")}, fh, indent=1)
    return out_json("pass", f"vfx verifier packet: {len(copied)} player sheet(s), {len(beats)} beat(s) ({sum(1 for s in scene_copies if s)} with the scene's frame, "
                    f"{sum(1 for d in details if d[0])} with a detail crop from the {view or '-'} view), owner anchor {'yes' if anchor else 'none'} -> {out}",
                    f"hand {out}/PROMPT.md + its images to a FRESH verifier (a subagent); then: lune run kit vfx judge {name} --record <answer.json>",
                    packet=out, sheets=[os.path.basename(d) for d, _ in copied], beats=len(beats))


def has_number_grade(v):
    """a score smuggled in: any key named like a grade, or a 'n/100' / 'n/10' in the words"""
    text = json.dumps(v).lower()
    keys = re.findall(r'"(\w+)"\s*:', text)
    if any(k in ("score", "scores", "overall", "grade", "rating", "weighted") for k in keys):
        return True
    return re.search(r"\b\d{1,3}\s*/\s*(10|100)\b", text) is not None


def record(argv):
    o = opts_of(argv, {"--effects": "assets/effects", "--packet": None, "--verdict": None, "--name": None})
    name, pk, vp = o["--name"], o["--packet"], o["--verdict"]
    if not (name and pk and vp):
        return out_json("fail", "vfx judge record: needs --name, --packet and --verdict", "lune run kit vfx judge <name> --record answer.json")
    if not os.path.isfile(vp):
        return out_json("fail", f"vfx judge record: no answer file {vp}", "write the verifier's JSON answer to a file first")
    meta_path = os.path.join(pk, "packet.json")
    if not os.path.isfile(meta_path):
        return out_json("fail", f"vfx judge record: no packet at {pk}", f"lune run kit vfx judge {name}")
    meta = json.load(open(meta_path, encoding="utf-8"))
    try:
        v = json.load(open(vp, encoding="utf-8"))
    except json.JSONDecodeError as e:
        return out_json("fail", f"vfx judge record: the answer is not JSON ({e})", "answer with the JSON block from PROMPT.md")
    problems = []
    if has_number_grade(v):
        problems.append("a score / grade is in the answer: the verifier names differences and edits, never a number")
    want = [b["beat"] for b in meta.get("beats", [])]
    got = v.get("beats") if isinstance(v.get("beats"), list) else []

    def filled(x):
        return isinstance(x, str) and x.strip() and not x.strip().startswith("<")

    done = {b.get("beat") for b in got if isinstance(b, dict) and filled(b.get("difference")) and filled(b.get("edit"))}
    missing = [b for b in want if b not in done]
    if missing:
        problems.append(f"beats without a difference + an edit: {', '.join(missing)}")
    if not filled(v.get("verifier")):
        problems.append("verifier: who looked (model@harness)")
    if problems:
        return out_json("fail", f"vfx judge record: {'; '.join(problems)}", "complete the answer (every beat: difference + edit; no numbers)")
    stale = []
    booth = os.path.join("build", "vfx", "booth")
    for base, h in meta.get("sheets", {}).items():
        f = os.path.join(booth, base)
        if not os.path.isfile(f) or sha(f) != h:
            stale.append(base)
    if stale:
        return out_json("fail", f"vfx judge record: the recording changed since the packet ({', '.join(stale)})", f"re-run the packet: lune run kit vfx judge {name}")
    rec = {"name": name, "kind": "verifier", "verifier": v["verifier"], "date": time.strftime("%Y-%m-%d %H:%M"),
           "sheets": meta.get("sheets", {}), "anchor": meta.get("anchor"),
           "beats": [b for b in got if isinstance(b, dict) and b.get("beat") in want], "first": v.get("first", "")}
    os.makedirs(os.path.join(o["--effects"], "judge"), exist_ok=True)
    dst = os.path.join(o["--effects"], "judge", f"{name}.json").replace(os.sep, "/")
    # every earlier round is KEPT (a fresh verifier flips on some asks round to round - band widths, spark shapes - and
    # repeats others; only an ask repeated across rounds is a real signal, and a record that overwrote itself hid that)
    history = []
    if os.path.isfile(dst):
        try:
            prev = json.load(open(dst, encoding="utf-8"))
            history = prev.pop("history", []) + [{k: prev.get(k) for k in ("verifier", "date", "beats", "first")}]
        except (OSError, json.JSONDecodeError):
            history = []
    rec["history"] = history[-30:]
    with open(dst, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, indent=1)
        fh.write("\n")
    first = rec["first"] or (rec["beats"][0]["edit"] if rec["beats"] else "")
    return out_json("pass", f"vfx verifier: {name} - {len(rec['beats'])} beat(s), each one difference + one edit, by {v['verifier']} -> {dst}",
                    f"make ONE edit (first: {first}), re-record in the player (kit vfx play {name} --record), verify again", record=rec)


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] not in ("packet", "record"):
        print(__doc__)
        return 2
    return packet(argv[1:]) if argv[0] == "packet" else record(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
