"""judge.py — the packet a FRESH judge scores a UI screen from, and the verdict's validation.

    python kit/ui/judge.py packet --out build/judge/ui/<name> --ui build/ui --identities assets/ui/identities Screen...
    python kit/ui/judge.py record --packet build/judge/ui/<name> --verdict verdict.json --models src/ui --out assets/ui

A packet (one folder, ONE picture to look at — judges are models with an image budget):
    sheet.png       every named screen's desktop view stacked, labelled (the phone and tablet views beside it, smaller)
    motion.png      the screens' enter choreography strips stacked (kit ui --motion), or their reels' eight frames
    references.md   the identity's references: what each real screen does, measured values, the bans
    PROMPT.md       the rubric + the exact JSON the judge answers with
    packet.json     screens, their model.json sha256 (a verdict is tied to the build it saw), identity, quality

The rubric (0-20 each, 100 total): IDENTITY (looks like THIS game and no other; the references beside it),
HIERARCHY (the eye lands where it should; readable at a glance; phone too), CRAFT (alignment, spacing, edges,
texture, type — nothing crude, nothing default), MOTION (arrives in order, nothing pops at once, the timing fits
the world), FEEL (would a player of that genre believe it shipped). Plus the AI-tell count (each tell found is
named) and located GAPS (where + what to change). Bars: prop 55 / hero 75 / aaa 88 (kit judge's).
"""

import argparse
import hashlib
import json
import os
import sys
import time

from PIL import Image, ImageDraw, ImageFont

BARS = {"prop": 55, "hero": 75, "aaa": 88}
PARTS = ("identity", "hierarchy", "craft", "motion", "feel")

RUBRIC = """# UI judge — {names}

You are a FRESH judge. You have not seen this work being made. The red box at the top-left of every view is the
preview's marker for Roblox's own menu buttons (drawn by the tool, never part of the UI): ignore it. Look at `sheet.png` (and `motion.png` if present)
beside `references.md`. Score what you SEE, not what the spec intended. A green gate is not quality.

Scale: `sheet.png` draws the desktop view at 50% (a 24 px label is 12 px there), the phone and tablet views beside it at
about 60%. Every tile carries a ruler = 100 px of the real screen: judge sizes against the ruler and against the
references' measured numbers and scale floors in `references.md`, never in sheet pixels.

Identity: **{identity}** — {about}
Quality asked: **{quality}** (bar: prop 55 / hero 75 / aaa 88).
{refs_line}
## The designer's claims (check them, do not trust them)
{screen_notes}

## Score each screen, 0-20 per part (100 total)
- **identity** — does it look like THIS game's world and no other? Would it be mistaken for a generic template?
  Compare with the references' descriptions: type, palette, shape language, motifs.
- **hierarchy** — does the eye land where it should (the number, the name, the selected row)? Readable at a glance
  on desktop AND in the small phone view? Anything cramped, colliding, lost?
- **craft** — alignment, spacing rhythm, edges and corners, texture, letter-spacing, the art pieces (frames,
  caps, slots, icons): is anything crude, placeholder-looking, misaligned, blurry, or an engine default?
- **motion** (from motion.png — an enter strip or a reel's eight timed frames; 10 if none exists and the screen is a static menu) — does it arrive in order,
  is anything popping at the same instant, does the timing fit the world (slow and grave vs snappy)?
- **feel** — would a player of this genre believe this shipped in a real game? What breaks the illusion?

## Then
- **tells**: every "AI-generated UI" tell you can name (default fonts, uniform radii, centred-card-with-tiles,
  purple/indigo, flat rectangles, same hover on everything, placeholder glyphs...). An empty list is a claim.
- **gaps**: located — `where` is a node path on the sheet (e.g. `Hud.Slots.Item`), `what` is the change that
  would raise the score most. At least three per screen unless it is genuinely finished.

## Answer with EXACTLY this JSON (nothing else), scores as integers:
```json
{{
  "judge": "<model>@<harness>",
  "screens": {{
{screen_blocks}
  }},
  "overall": <0-100, your weighted view of the pack as one game's UI>,
  "verdict": "<one paragraph: what works, what does not, what to do first>"
}}
```
"""

SCREEN_BLOCK = """    "{name}": {{
      "identity": 0, "hierarchy": 0, "craft": 0, "motion": 0, "feel": 0,
      "tells": ["..."],
      "gaps": [{{"where": "{name}.<node>", "what": "..."}}],
      "score": 0
    }}"""


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def label_font(size):
    for name in ("seguisb.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        for base in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu"):
            try:
                return ImageFont.truetype(os.path.join(base, name), size)
            except OSError:
                continue
    return ImageFont.load_default()


def ruler(d, x, y, px, text):
    """a 100-px-of-the-real-screen bar: the judge reads sizes against it, not in sheet pixels"""
    d.rectangle([x, y, x + px, y + 6], fill=(255, 255, 255), outline=(0, 0, 0))
    d.rectangle([x, y, x + px / 2, y + 6], fill=(255, 60, 60))
    d.text((x, y + 8), text, fill=(255, 255, 255), font=label_font(12), stroke_width=2, stroke_fill=(0, 0, 0))


def stack(paths, out, crop=None, width=960, phone=None, desktop_scale=None, phone_scale=None, tablet=None):
    """stack images (optionally cropped to their desktop view) at one width, each labelled by its screen name;
    phone / tablet: {name: (x0, y0, x1, y1)} crops pasted beside in a side column, smaller (every judge pair asked
    where the tablet was); desktop_scale / phone_scale = the crop's pixels per real screen pixel (the sheet draws
    desktop at 50%): a ruler of 100 real px goes on every tile"""
    tiles = []
    for name, p in paths:
        im = Image.open(p).convert("RGB")
        if crop:
            im = im.crop(crop(im))
        scale = width / im.width
        tile = im.resize((width, int(im.height * scale)), Image.LANCZOS)
        d = ImageDraw.Draw(tile)
        if desktop_scale:
            ruler(d, 8, tile.height - 30, 100 * desktop_scale * scale, "100 px at 1080p")
        side = []
        if phone and name in phone:
            ph = Image.open(p).convert("RGB").crop(phone[name])
            ps = min(1.0, 300 / ph.width)
            ph = ph.resize((int(ph.width * ps), int(ph.height * ps)), Image.LANCZOS)
            if phone_scale:
                ruler(ImageDraw.Draw(ph), 6, ph.height - 28, 100 * phone_scale * ps, "100 px on the phone")
            ImageDraw.Draw(ph).text((6, 4), "phone", fill=(255, 255, 255), font=label_font(12))
            side.append(ph)
        if tablet and name in tablet:
            tb = Image.open(p).convert("RGB").crop(tablet[name])
            ts = min(1.0, 300 / tb.width)
            tb = tb.resize((int(tb.width * ts), int(tb.height * ts)), Image.LANCZOS)
            if phone_scale:
                ruler(ImageDraw.Draw(tb), 6, tb.height - 28, 100 * phone_scale * ts, "100 px on the tablet")
            ImageDraw.Draw(tb).text((6, 4), "tablet", fill=(255, 255, 255), font=label_font(12))
            side.append(tb)
        if side:
            sw = max(x.width for x in side)
            sh_ = sum(x.height for x in side) + 6 * (len(side) - 1)
            canvas = Image.new("RGB", (width + sw + 8, max(tile.height, sh_)), (40, 40, 44))
            canvas.paste(tile, (0, 0))
            y_ = 0
            for x in side:
                canvas.paste(x, (width + 8, y_))
                y_ += x.height + 6
            tile = canvas
        d = ImageDraw.Draw(tile)
        d.rectangle([0, 0, 220, 26], fill=(0, 0, 0))
        d.text((8, 5), name, fill=(255, 255, 255), font=label_font(16))
        tiles.append(tile)
    W = max(t.width for t in tiles)
    H = sum(t.height for t in tiles) + 8 * (len(tiles) - 1)
    sheet = Image.new("RGB", (W, H), (40, 40, 44))
    y = 0
    for t in tiles:
        sheet.paste(t, (0, y))
        y += t.height + 8
    sheet.save(out)
    return sheet.size


def references_md(identity):
    lines = [f"# References — identity '{identity.get('name', '?')}'", "", identity.get("about", ""), ""]
    if identity.get("world"):
        lines += [f"World: {identity['world']}", ""]
    fonts = identity.get("fonts") or {}
    lines += [f"Type: {fonts.get('titleFont', '?')} (titles) / {fonts.get('font', '?')} (body). Tokens: "
              + ", ".join(f"{k} {v}" for k, v in (identity.get("tokens") or {}).items()), ""]
    if identity.get("minimums"):
        lines += ["Scale floors (measured from the references; under them is undersized): "
                  + ", ".join(f"{k} {v} px" for k, v in identity["minimums"].items()), ""]
    if identity.get("bans"):
        lines += ["## The identity's bans (a tell if present)"] + [f"- {b}" for b in identity["bans"]] + [""]
    lines.append("## What the real screens do")
    for r in identity.get("references") or []:
        lines += [f"### {r.get('game', '?')} — {r.get('screen', '?')}", r.get("take", ""), ""]
        if r.get("measured"):
            lines += ["Measured: " + ", ".join(f"{k} = {v}" for k, v in r["measured"].items()), ""]
        if r.get("source"):
            lines += [f"Source: {r['source']}", ""]
    return "\n".join(lines)


def look_path(specs, name):
    return os.path.join(specs, f"{name}.look.json")


def read_look(specs, name, model_sha, sheet_sha=None):
    """the look record of THIS build, or None (no look, or a look at an older build)"""
    path = look_path(specs, name)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        look = json.load(fh)
    if look.get("model_sha256") == model_sha:
        return look
    return look if sheet_sha and look.get("sheet_sha256") == sheet_sha else None


def cmd_look(a):
    """record that a model LOOKED at the built sheet (desktop, phone, tablet, motion strip) and what it saw:
    the judge packet and promote refuse a build nobody looked at — the score is gameable, the eye is not"""
    sheet = os.path.join(a.ui, a.name + ".png")
    model = os.path.join(a.models, a.name + ".model.json")
    if not os.path.isfile(sheet) or not os.path.isfile(model):
        return emit("fail", f"{a.name}: no built sheet at {sheet}", f"lune run kit ui {a.name} --motion, then look at it")
    note = (a.note or "").strip()
    if len(note) < 40:
        return emit("fail", f"{a.name}: the look note is too short ({len(note)} chars)",
                    'say what you SAW and what you will change, in at least 40 characters: lune run kit ui look <Name> "..."')
    rec = {"schema": 1, "screen": a.name, "sheet_sha256": sha256_file(sheet), "model_sha256": sha256_file(model),
           "note": note, "by": a.by or "unknown", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(look_path(a.specs, a.name), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, indent=1)
    return emit("pass", f"{a.name}: look recorded ({a.by or 'unknown'})",
                f"fix what you saw, or judge it: lune run kit ui judge {a.name}")


def cmd_packet(a):
    os.makedirs(a.out, exist_ok=True)
    identities = {}
    if os.path.isdir(a.identities):
        for f in os.listdir(a.identities):
            if f.endswith(".json"):
                with open(os.path.join(a.identities, f), encoding="utf-8") as fh:
                    identities[f[:-5]] = json.load(fh)
    screens, identity_name, quality = [], None, "prop"
    for name in a.names:
        spec_path = os.path.join(a.specs, name + ".json")
        model_path = os.path.join(a.models, name + ".model.json")
        sheet_path = os.path.join(a.ui, name + ".png")
        if not os.path.isfile(sheet_path):
            return emit("fail", f"{name}: no preview sheet at {sheet_path}", "lune run kit ui --motion")
        spec = {}
        if os.path.isfile(spec_path):
            with open(spec_path, encoding="utf-8") as fh:
                spec = json.load(fh)
        identity_name = identity_name or spec.get("identity")
        if spec.get("quality") in BARS and BARS[spec["quality"]] > BARS.get(quality, 0):
            quality = spec["quality"]
        model_sha = sha256_file(model_path) if os.path.isfile(model_path) else None
        sheet_sha = sha256_file(sheet_path)
        look = read_look(a.specs, name, model_sha, sheet_sha)
        if look is None and not getattr(a, "unlooked", False):
            return emit("fail", f"{name}: nobody looked at this build — look at {sheet_path} (desktop, phone, tablet) and its motion ({name}.motion.png or reels/{name}.reel.png), then record what you saw",
                        f'lune run kit ui look {name} "<what you saw, what you will change>"   (then kit ui judge again)')
        # the motion evidence: the enter strip (kit ui --motion), else the REEL's eight frames (a reel IS the screen's
        # motion: a judge scored motion blind on every reel-only screen before)
        motion = os.path.join(a.ui, name + ".motion.png")
        if not os.path.isfile(motion) and os.path.isfile(os.path.join(a.ui, "reels", name + ".reel.png")):
            motion = os.path.join(a.ui, "reels", name + ".reel.png")
        screens.append({"name": name, "sheet": sheet_path, "motion": motion,
                        "model_sha256": model_sha, "sheet_sha256": sheet_sha, "quality": spec.get("quality", "prop"),
                        "focus": spec.get("focus"), "look": (look or {}).get("note")})
    identity = identities.get(identity_name or "", {"name": identity_name or "none"})
    # desktop view = the top band of the sheet (drawn at 50%: 960 x 540); phone view = bottom-left (506 x 234)
    def desktop_crop(im):
        return (0, 0, 960, 540)
    phone = {s["name"]: (0, 548, 506, 782) for s in screens}
    tablet = {s["name"]: (514, 548, 1128, 1008) for s in screens}   # the preview's tablet tile (1024x768 at 60%)
    sheet_size = stack([(s["name"], s["sheet"]) for s in screens], os.path.join(a.out, "sheet.png"), desktop_crop, 960, phone,
                       desktop_scale=0.5, phone_scale=0.6, tablet=tablet)
    strips = [(s["name"], s["motion"]) for s in screens if os.path.isfile(s["motion"])]
    if strips:
        stack(strips, os.path.join(a.out, "motion.png"))
    # the real screens, when the identity names pictures ("image": a path under the project): refs.png
    pictures = [(r.get("game", "?") + " — " + r.get("screen", "?"), r["image"]) for r in identity.get("references") or []
                if r.get("image") and os.path.isfile(r["image"])]
    refs_line = ""
    if pictures:
        stack(pictures, os.path.join(a.out, "refs.png"), None, 800)
        refs_line = ("Look at `refs.png` too: the REAL screens the identity was measured from, labelled. The pack must "
                     "read as the same family at the same scale; name every way it falls short of them.")
    # the owner's anchors: screens the owner rated in their own words (kit ui judge <Screen> --owner <score> "<words>");
    # a fresh judge places the new screen BETWEEN them — six judge pairs scored an owner-approved gauge 45-49
    anchors_line = ""
    anchors_path = os.path.join(a.specs, "anchors", "anchors.json")
    if os.path.isfile(anchors_path):
        try:
            with open(anchors_path, encoding="utf-8") as fh:
                anchors = [x for x in json.load(fh).get("anchors", []) if os.path.isfile(x.get("sheet", ""))]
        except Exception:  # noqa: BLE001
            anchors = []
        anchors = [x for x in anchors if x["screen"] not in {s["name"] for s in screens}][-4:]
        if anchors:
            labelled = [(f"OWNER {x['score']}/100 — {x['screen']}: {x['words'][:70]}", x["sheet"]) for x in anchors]
            stack(labelled, os.path.join(a.out, "anchors.png"), desktop_crop, 960)
            anchors_line = ("Owner anchors: `anchors.png` shows screens the OWNER already rated, with the owner's score and words on each tile. "
                            "The owner's eye outranks this rubric: place the new screen relative to those anchors (better than the 85? worse than the 50?) "
                            "and say which anchor it is closest to and why. " + "; ".join(f"{x['screen']} = {x['score']} ('{x['words'][:60]}')" for x in anchors))
    notes = []
    for s in screens:
        line = f"- **{s['name']}**: " + (f"the eye should land on `{s['focus']}`. " if s.get("focus") else "no focus named (a tell on a hero screen). ")
        line += f"The designer looked and said: \"{s['look']}\"" if s.get("look") else ""
        notes.append(line)
    with open(os.path.join(a.out, "references.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(references_md(identity))
    with open(os.path.join(a.out, "PROMPT.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(RUBRIC.format(names=", ".join(s["name"] for s in screens), identity=identity.get("name", "none"),
                               about=identity.get("about", "no identity: a skin-only screen"), quality=quality,
                               refs_line=(refs_line + ("\n\n" + anchors_line if anchors_line else "")), screen_notes="\n".join(notes),
                               screen_blocks=",\n".join(SCREEN_BLOCK.format(name=s["name"]) for s in screens)))
    with open(os.path.join(a.out, "packet.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"schema": 1, "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "identity": identity.get("name"),
                   "quality": quality, "bar": BARS[quality], "screens": screens, "sheet": sheet_size}, fh, indent=1)
    return emit("pass", f"judge packet for {len(screens)} screen(s) in {a.out} (sheet {sheet_size[0]}x{sheet_size[1]}" + (", motion strips" if strips else "") + ")",
                f"give a FRESH judge {a.out}/PROMPT.md (it names sheet.png + references.md); record its answer: lune run kit ui judge {' '.join(s['name'] for s in screens)} --record <verdict.json>")


def cmd_record(a):
    with open(os.path.join(a.packet, "packet.json"), encoding="utf-8") as fh:
        packet = json.load(fh)
    with open(a.verdict, encoding="utf-8") as fh:
        verdict = json.load(fh)
    verdict_sha = sha256_file(a.verdict)
    problems, recorded = [], []
    gaps_by_screen = {}
    judge_name = str(verdict.get("judge") or "").strip().lower()  # (one judge, one voice: "Opus@cc" = "opus@cc")
    if not judge_name:
        problems.append('verdict.judge: who judged? ("<model>@<harness>") — nothing recorded')
    for s in packet["screens"]:
        mine = []  # this screen's problems: any one of them means its verdict is NOT recorded
        v = (verdict.get("screens") or {}).get(s["name"])
        if not isinstance(v, dict):
            problems.append(f"{s['name']}: no verdict")
            continue
        total = 0
        for part in PARTS:
            x = v.get(part)
            if isinstance(x, bool) or not isinstance(x, int) or x < 0 or x > 20:
                mine.append(f"{s['name']}.{part}: must be an integer 0..20 (got {x!r})")
                x = 0
            total += x
        if v.get("score") != total:
            mine.append(f"{s['name']}.score: {v.get('score')} != the parts' sum {total} (score the parts, the sum is the score)")
        gaps = v.get("gaps") or []
        if not isinstance(gaps, list) or any(not isinstance(g, dict) or "where" not in g or "what" not in g for g in gaps):
            mine.append(f"{s['name']}.gaps: a list of {{where, what}}")
            gaps = []
        model_path = os.path.join(a.models, s["name"] + ".model.json")
        now_sha = sha256_file(model_path) if os.path.isfile(model_path) else None
        # the verdict is tied to what the judge SAW: the sheet's pixels. The model's sha also changes on every
        # upload (asset ids), which changes nothing a judge judges — so an unchanged sheet still records
        sheet_now = sha256_file(s["sheet"]) if s.get("sheet") and os.path.isfile(s["sheet"]) else None
        same_sheet = s.get("sheet_sha256") and sheet_now == s["sheet_sha256"]
        if s.get("model_sha256") and now_sha and now_sha != s["model_sha256"] and not same_sheet:
            mine.append(f"{s['name']}: the screen changed since the packet was made — make a new packet, judge again")
        if same_sheet and now_sha:
            s["model_sha256"] = now_sha  # (the record names the current build; the pixels are the same)
        if mine or not judge_name:
            problems.extend(mine)
            continue
        rec = {"schema": 1, "screen": s["name"], "judge": judge_name, "verdict_sha256": verdict_sha, "judged": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "model_sha256": s.get("model_sha256"), "quality": s.get("quality", "prop"), "bar": BARS.get(s.get("quality", "prop"), 55),
               "parts": {p: v.get(p, 0) for p in PARTS}, "score": total, "tells": v.get("tells") or [], "gaps": gaps,
               "verdict": verdict.get("verdict", "")}
        # several judges: every judge's LATEST verdict of this build is kept, the screen's score is their median
        out_path = os.path.join(a.out, s["name"] + ".judge.json")
        history, owner = [], None
        if os.path.isfile(out_path):
            with open(out_path, encoding="utf-8") as fh:
                prev = json.load(fh)
            history = prev.get("verdicts") or []
            owner = prev.get("owner")  # the owner's score (and the judges' gap from it) outlives a new judging round
        # two fresh judges on one model share a name ("claude-opus-5-5@..."): a judge is ONE verdict file, so only
        # re-recording the same verdict replaces it (keyed by the verdict's own content)
        history = [h for h in history if h.get("model_sha256") == s.get("model_sha256") and h.get("verdict_sha256") != verdict_sha]
        history.append(rec)
        scores = sorted(h["score"] for h in history)
        median = scores[len(scores) // 2] if len(scores) % 2 else (scores[len(scores) // 2 - 1] + scores[len(scores) // 2]) / 2
        out = {"schema": 1, "screen": s["name"], "model_sha256": s.get("model_sha256"), "quality": rec["quality"], "bar": rec["bar"],
               "score": median, "judges": len(history), "verdicts": history}
        if owner:
            out["owner"] = owner
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, indent=1)
        recorded.append(f"{s['name']} {total}/100 ({len(history)} judge(s), median {median}, bar {rec['bar']})")
        # agreed gaps: a `where` (its last two path parts) named by two or more judges of this build
        where_counts = {}
        for h in history:
            seen_here = set()
            for g in h.get("gaps") or []:
                key = ".".join(str(g.get("where", "")).split(".")[-2:]).lower()
                if key and key not in seen_here:
                    seen_here.add(key)
                    where_counts[key] = where_counts.get(key, 0) + 1
        agreed = [g for g in gaps if where_counts.get(".".join(str(g.get("where", "")).split(".")[-2:]).lower(), 0) >= 2]
        gaps_by_screen[s["name"]] = (median, agreed + [g for g in gaps if g not in agreed], len(agreed))
    status = "fail" if problems else "pass"
    # the next step is the lowest screen's located gaps, not its score (the score is reported, never chased)
    lowest = min(gaps_by_screen.items(), key=lambda kv: kv[1][0]) if gaps_by_screen else None
    todo = ("; ".join(f"{g['where']}: {g['what']}" for g in lowest[1][1][:3]) if lowest and lowest[1][1] else None)
    if lowest and lowest[1][2]:
        todo = f"({lowest[1][2]} gap(s) two judges AGREE on, first) " + (todo or "")
    return emit(status, "; ".join(recorded) if recorded else "nothing recorded",
                problems[0] if problems else (f"fix {lowest[0]} ({lowest[1][0]}/100) first — {todo}; then kit ui and a new packet (a verdict is tied to the build it saw)" if todo
                                              else "fix the located gaps, then kit ui and a new packet (a verdict is tied to the build it saw)"),
                problems=problems)


def cmd_owner(a):
    """the OWNER's rating of a built screen: the score and words go on the screen's judge record and into the anchors
    every later packet shows a fresh judge (the owner's eye outranks the rubric)"""
    import shutil
    sheet = os.path.join(a.ui, a.name + ".png")
    if not os.path.isfile(sheet):
        return emit("fail", f"{a.name}: no preview sheet at {sheet}", "lune run kit ui --motion")
    try:
        score = int(a.score)
    except ValueError:
        return emit("fail", "owner: the score is a number 0..100", 'lune run kit ui judge WitchGauge --owner 85 "genuinely impressed"')
    model_path = os.path.join(a.models, a.name + ".model.json")
    model_sha = sha256_file(model_path) if os.path.isfile(model_path) else None
    anchors_dir = os.path.join(a.specs, "anchors")
    os.makedirs(anchors_dir, exist_ok=True)
    kept = os.path.join(anchors_dir, a.name + ".png")
    shutil.copyfile(sheet, kept)
    apath = os.path.join(anchors_dir, "anchors.json")
    data = {"schema": 1, "anchors": []}
    if os.path.isfile(apath):
        with open(apath, encoding="utf-8") as fh:
            data = json.load(fh)
    data["anchors"] = [x for x in data.get("anchors", []) if x.get("screen") != a.name]
    entry = {"screen": a.name, "score": score, "words": a.words, "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "model_sha256": model_sha, "sheet": kept.replace("\\", "/")}
    data["anchors"].append(entry)
    with open(apath, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1)
    jpath = os.path.join(a.specs, a.name + ".judge.json")
    rec = {"schema": 1, "screen": a.name, "model_sha256": model_sha, "verdicts": []}
    if os.path.isfile(jpath):
        with open(jpath, encoding="utf-8") as fh:
            rec = json.load(fh)
    rec["owner"] = {"score": score, "words": a.words, "when": entry["when"], "model_sha256": model_sha}
    gap = None
    # the judges' median and the owner's score of the SAME build only (another build's judges measured other pixels)
    if rec.get("score") is not None and rec.get("model_sha256") == model_sha:
        gap = round(float(rec["score"]) - score, 1)
        # kept beside the owner's score (2026-11-08, sprint 4: printed, never stored): kit verdict trend reads every
        # screen's gap - how far the fresh judges sit from the owner's eye
        rec["owner"]["judges_median"] = rec["score"]
        rec["owner"]["gap"] = gap
    with open(jpath, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, indent=1)
    return emit("pass", f"{a.name}: the owner says {score}/100 — \"{a.words}\"" + (f" (fresh judges' median {rec.get('score')}: judges {('under' if gap < 0 else 'over')} the owner by {abs(gap)})" if gap is not None else "") + "; kept as an anchor for every later packet",
                "the owner's rating is the bar for this screen; the next packet shows it to the judges as an anchor")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("packet")
    p.add_argument("--out", required=True)
    p.add_argument("--ui", default="build/ui")
    p.add_argument("--specs", default="assets/ui")
    p.add_argument("--models", default="src/ui")
    p.add_argument("--identities", default="assets/ui/identities")
    p.add_argument("names", nargs="+")
    lk = sub.add_parser("look")
    lk.add_argument("name")
    lk.add_argument("--note", required=True)
    lk.add_argument("--by", default="unknown")
    lk.add_argument("--ui", default="build/ui")
    lk.add_argument("--specs", default="assets/ui")
    lk.add_argument("--models", default="src/ui")
    p.add_argument("--unlooked", action="store_true", help="(tests) make the packet without a look record")
    r = sub.add_parser("record")
    r.add_argument("--packet", required=True)
    r.add_argument("--verdict", required=True)
    r.add_argument("--models", default="src/ui")
    r.add_argument("--out", default="assets/ui")
    o = sub.add_parser("owner")
    o.add_argument("name")
    o.add_argument("--score", required=True)
    o.add_argument("--words", required=True)
    o.add_argument("--ui", default="build/ui")
    o.add_argument("--specs", default="assets/ui")
    o.add_argument("--models", default="src/ui")
    a = ap.parse_args()
    if a.cmd == "owner":
        return cmd_owner(a)
    return cmd_packet(a) if a.cmd == "packet" else (cmd_look(a) if a.cmd == "look" else cmd_record(a))


if __name__ == "__main__":
    sys.exit(main())
