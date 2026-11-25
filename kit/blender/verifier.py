"""verifier.py — `kit judge <asset>`: a VERIFIER, not a judge (mission 01-3d §5.10). A judge scores; the score never
predicted the owner (r 0.60, -30 points on the two successes) and the builder optimised it. A verifier DESCRIBES:
per traced view the SAME crop of the reference and of the render side by side (the object's own box in both, at one
size, a mm scale bar), the worst places of that view at 1:1 beside the reference's same places, the owner's anchor
and words FIRST — and asks for ONE described difference per image and ONE edit. No score anywhere. Ten rounds per
attempt, then STOP: the owner looks (VIGA, arXiv 2601.11109: a verifier that looks at target vs render and returns a
difference + one edit beat one-shot editing by 35% on BlenderGym).

    python kit/blender/verifier.py packet <asset>            -> build/judge/<asset>/verify/{<view>.png, <view>_R<n>.png,
                                                                PROMPT.md}
    python kit/blender/verifier.py record <asset> [file ...]  -> one round in assets/models/<asset>.verify.json
"""
import datetime
import glob
import json
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REPO = os.path.dirname(KIT)
MAX_ROUNDS = 10          # per attempt (the clock's), then the owner looks
PAIR_W, PAIR_H = 760, 560   # one side of a pair: two side by side = 1520 x 560 (inside a vision model's limits)
CROP_PX = 360            # a worst place shown at its own pixels (never shrunk): 360 x 360 each side
NO_SCORE_KEYS = ("score", "scores", "criteria", "total", "rating", "grade")


def _out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _rel(p):
    return os.path.relpath(p, REPO).replace("\\", "/")


def _font(size):
    for f in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ------------------------------------------------------------------------------------------- what the build has
def manifest(asset):
    return _json(os.path.join(REPO, "build", "models", f"{asset}.manifest.json"))


def traces_by_view(asset):
    """the build script's a.trace_match(<trace>, view=...) -> {view: trace name} (kit/tools/plan.py reads it)"""
    sys.path.insert(0, os.path.join(KIT, "tools"))
    import plan  # noqa: PLC0415

    try:
        with open(os.path.join(REPO, "assets", "models", f"build_{asset}.py"), encoding="utf-8") as fh:
            s = plan.read_script(fh.read())
    except OSError:
        return {}
    return {view: name for name, view in s["traces"]}


def owner_anchor(asset):
    """the owner's own verdicts FIRST: this asset's latest (kit/knowledge/vault/3d/verdicts), then the 3D golden set's
    best -> [(name, score, date, words)]"""
    rows = []
    for p in glob.glob(os.path.join(KIT, "knowledge", "vault", "3d", "verdicts", "*.md")):
        try:
            with open(p, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        m = re.match(r"(?s)^---\n(.*?)\n---\n(.*)$", text)
        if not m:
            continue
        front = dict(re.findall(r"(?m)^(\w+):\s*(.*)$", m.group(1)))
        if front.get("by", "owner") != "owner":
            continue
        try:
            score = float(front.get("score")) if front.get("score") not in (None, "", "null") else None
        except ValueError:
            score = None
        rows.append((front.get("name", "?").strip('"'), score, front.get("date", ""), m.group(2).strip()))
    mine = sorted((r for r in rows if r[0] == asset), key=lambda r: r[2], reverse=True)[:2]
    golden = sorted((r for r in rows if r[0] != asset and (r[1] or 0) >= 7), key=lambda r: (r[1], r[2]),
                    reverse=True)[:2]
    return mine, golden


# ------------------------------------------------------------------------------------------- the same crop
def _trace(name):
    return _json(os.path.join(REPO, "assets", "models", f"{name}.trace.json"))


def _picture(trace):
    pic = str((trace or {}).get("source") or "")
    return pic if os.path.isabs(pic) else os.path.join(REPO, pic)


def is_mask(path):
    """a silhouette / hull mask, not a picture of the object: (nearly) two tones — nothing to compare a surface with"""
    try:
        im = Image.open(path).convert("L")
    except OSError:
        return True
    im.thumbnail((256, 256), Image.NEAREST)   # (no smoothing: a mask's edge must not invent in-between tones)
    hist = np.bincount((np.asarray(im) // 8).ravel(), minlength=32).astype(float)
    return float(np.sort(hist)[-3:].sum() / max(hist.sum(), 1.0)) > 0.97   # (three tones cover it: a mask)


def view_of(stem):
    for w in reversed(stem.split("_")):
        if w in ("side", "front", "back", "top", "left", "right"):
            return "side" if w in ("left", "right") else w
    return None


def photo_trace(view, registered):
    """the trace to show for a view: the registered one when its picture is a photo, else another trace of the same
    family (glock17_hull_side -> glock17_photo_side) whose picture is -> (name, trace) or (registered, its trace)"""
    t = _trace(registered)
    if t is not None and (t.get("frame") or {}).get("length_px") and os.path.isfile(_picture(t)) \
            and not is_mask(_picture(t)):
        return registered, t
    family = registered.rsplit("_", 2)[0] if registered.count("_") >= 2 else registered.split("_")[0]
    for p in sorted(glob.glob(os.path.join(REPO, "assets", "models", f"{family}_*.trace.json"))):
        name = os.path.basename(p)[:-len(".trace.json")]
        other = _json(p)
        if name == registered or not isinstance(other, dict) or not (other.get("frame") or {}).get("length_px"):
            continue
        v = other.get("view") or view_of(name)
        if (v == view or (view.startswith("side") and v == "side")) and os.path.isfile(_picture(other)) \
                and not is_mask(_picture(other)):
            return name, other
    return registered, t


def ref_crop(trace):
    """the trace's picture cut to the object's box (its frame: x0, y1, length_px, height_ratio) -> RGB Image"""
    pic = trace.get("source") or ""
    path = pic if os.path.isabs(pic) else os.path.join(REPO, pic)
    fr = trace.get("frame") or {}
    if not os.path.isfile(path) or not {"x0", "y1", "length_px"} <= set(fr):
        return None
    x0, y1, L = float(fr["x0"]), float(fr["y1"]), float(fr["length_px"])
    hr = float(trace.get("height_ratio") or 0.3)
    im = Image.open(path)
    rgba = im.convert("RGBA")
    if im.mode in ("RGBA", "LA") or "transparency" in im.info:   # (a cut-out: on the same grey as the render)
        bg = Image.new("RGBA", rgba.size, (60, 60, 64, 255))
        rgba = Image.alpha_composite(bg, rgba)
    return rgba.convert("RGB").crop((int(round(x0)), int(round(y1 - hr * L)), int(round(x0 + L)), int(round(y1))))


def render_crop(path):
    """a transparent orthographic render cut to the model's own silhouette box -> (RGB Image on grey, alpha mask)"""
    if not os.path.isfile(path):
        return None, None
    im = Image.open(path).convert("RGBA")
    a = np.asarray(im)[..., 3] > 8
    ys, xs = np.nonzero(a)
    if not len(xs):
        return None, None
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    bg = Image.new("RGBA", im.size, (60, 60, 64, 255))
    out = Image.alpha_composite(bg, im).convert("RGB").crop(box)
    return out, a[box[1]:box[3], box[0]:box[2]]


def _outline_mask(trace, w, h):
    """the trace outline rasterised in the box (w x h) -> bool mask (its front as the picture shows it)"""
    hr = float(trace.get("height_ratio") or 0.3)
    front = trace.get("front", "right")
    pts = [((1 - u if front == "left" else u) * w, h - (hh / hr) * h) for u, hh in trace.get("outline") or []]
    im = Image.new("L", (w, h), 0)
    if len(pts) >= 3:
        ImageDraw.Draw(im).polygon(pts, fill=255)
    return np.asarray(im) > 0


def _iou(a, b):
    return float((a & b).sum()) / max(1.0, float((a | b).sum()))


def oriented(trace, render, mask, w=200):
    """the render turned to lie like the trace (a side view's front can face either way): the flip with the better
    silhouette overlap -> (render, flipped?, iou)"""
    h = max(1, int(round(w * mask.shape[0] / max(1, mask.shape[1]))))
    m = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize((w, h))) > 127
    t = _outline_mask(trace, w, h)
    straight, flipped = _iou(m, t), _iou(m[:, ::-1], t)
    if flipped > straight + 0.02:
        return render.transpose(Image.FLIP_LEFT_RIGHT), True, round(flipped, 3)
    return render, False, round(straight, 3)


def _fit(img, w, h, bg=(60, 60, 64)):
    s = min(w / img.width, h / img.height)
    im = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.LANCZOS)
    out = Image.new("RGB", (w, h), bg)
    out.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return out, s


def _scale_bar(d, x, y, px_per_mm, f):
    """a 10 / 20 / 50 mm bar that fits ~120 px"""
    for mm in (5, 10, 20, 50, 100, 200):
        if mm * px_per_mm >= 60:
            break
    length = int(mm * px_per_mm)
    d.rectangle((x, y, x + length, y + 4), fill=(255, 210, 90))
    d.text((x + length + 6, y - 7), f"{mm} mm", font=f, fill=(255, 210, 90))


def pair_image(ref, render, title, mm_long=None):
    """[REFERENCE | MODEL], the same object box in both, one size -> Image"""
    lab = 34
    out = Image.new("RGB", (2 * PAIR_W + 12, PAIR_H + lab), (24, 24, 26))
    d = ImageDraw.Draw(out)
    f = _font(20)
    a, sa = _fit(ref, PAIR_W, PAIR_H)
    b, sb = _fit(render, PAIR_W, PAIR_H)
    out.paste(a, (0, lab))
    out.paste(b, (PAIR_W + 12, lab))
    d.text((8, 7), f"{title}: REFERENCE", font=f, fill=(255, 210, 90))
    d.text((PAIR_W + 20, 7), "MODEL (same box, same size)", font=f, fill=(255, 210, 90))
    if mm_long:
        px_per_mm = min(PAIR_W / max(ref.width, 1) * ref.width, PAIR_W) / float(mm_long)
        _scale_bar(d, 12, PAIR_H + lab - 16, px_per_mm, f)
    return out


PLACES = {"top left": (0, 0), "top centre": (1, 0), "top right": (2, 0), "middle left": (0, 1), "centre": (1, 1),
          "middle centre": (1, 1), "middle right": (2, 1), "bottom left": (0, 2), "bottom centre": (1, 2),
          "bottom right": (2, 2)}


def worst_places(ref_facts, n=2):
    """the view's worst windows (rbx_gaps: mm of outline missing / extra per 3 x 3 window) -> [(place, mm, kind)]"""
    wins = ((ref_facts or {}).get("gaps") or {}).get("windows") or []
    scored = []
    for w in wins:
        if not isinstance(w, dict) or w.get("place") not in PLACES:
            continue
        miss, extra = float(w.get("missing") or 0), float(w.get("extra") or 0)
        scored.append((max(miss, extra), w["place"], "missing" if miss >= extra else "extra"))
    scored.sort(reverse=True)
    return [(p, round(mm, 1), k) for mm, p, k in scored[:n] if mm > 0]


def place_crops(ref, render, place):
    """the same 3 x 3 window of both crops, each at its own pixels (up to CROP_PX) -> [REFERENCE | MODEL] Image"""
    cx, cy = PLACES[place]
    tiles = []
    for img in (ref, render):
        w, h = img.width / 3.0, img.height / 3.0
        box = (int(cx * w), int(cy * h), int((cx + 1) * w), int((cy + 1) * h))
        tile = img.crop(box)
        if max(tile.size) > CROP_PX:
            tile.thumbnail((CROP_PX, CROP_PX), Image.LANCZOS)
        tiles.append(tile)
    lab = 30
    W = max(t.width for t in tiles)
    H = max(t.height for t in tiles)
    out = Image.new("RGB", (2 * W + 12, H + lab), (24, 24, 26))
    d = ImageDraw.Draw(out)
    f = _font(18)
    d.text((6, 5), f"{place}: REFERENCE", font=f, fill=(255, 210, 90))
    d.text((W + 18, 5), "MODEL", font=f, fill=(255, 210, 90))
    out.paste(tiles[0], (0, lab))
    out.paste(tiles[1], (W + 12, lab))
    return out


# ------------------------------------------------------------------------------------------- rounds
def history(asset):
    return (_json(os.path.join(REPO, "assets", "models", f"{asset}.verify.json")) or {}).get("rounds") or []


def attempt(asset):
    """the clock's attempt (kit plan --restart makes a new one): rounds count per attempt"""
    c = _json(os.path.join(REPO, "assets", "models", f"{asset}.clock.json")) or {}
    try:
        return int(c.get("attempt") or 1)
    except (TypeError, ValueError):
        return 1


def rounds_now(asset):
    a = attempt(asset)
    return [r for r in history(asset) if int(r.get("attempt") or 1) == a]


# ------------------------------------------------------------------------------------------- packet
def packet(asset):
    m = manifest(asset)
    if m is None:
        return _out("fail", f"verify: {asset} has no build", f"build it first: lune run kit asset {asset}")
    done = rounds_now(asset)
    if len(done) >= MAX_ROUNDS:
        return _out("fail", f"verify: {asset} STOP — {len(done)} verifier rounds this attempt (cap {MAX_ROUNDS}): the "
                    "owner looks now", f"show the owner build/renders/{asset}.png beside its references "
                    f"(board/plans/missions/pending/3d.md); a new attempt only with their words: lune run kit plan "
                    f"{asset} --restart \"<their words>\"")
    pdir = os.path.join(REPO, "build", "judge", asset, "verify")
    os.makedirs(pdir, exist_ok=True)
    for old in glob.glob(os.path.join(pdir, "*.png")):
        os.remove(old)
    refs = {r.get("view"): r for r in (m.get("facts") or {}).get("references") or [] if isinstance(r, dict)}
    images = []   # [(path, what)]
    skipped = []
    for view, name in sorted(traces_by_view(asset).items()):
        name, t = photo_trace(view, name)
        shaded = os.path.join(REPO, "build", "renders", f"{asset}_ref_{view}_shaded.png")
        if t is None:
            skipped.append(f"{view}: no trace {name}")
            continue
        ref = ref_crop(t)
        render, mask = render_crop(shaded)
        if ref is None or render is None:
            skipped.append(f"{view}: " + ("the trace has no picture frame" if ref is None else
                                          f"no shaded render (build/renders/{asset}_ref_{view}_shaded.png)"))
            continue
        render, flipped, iou = oriented(t, render, mask)
        if flipped:
            mask = mask[:, ::-1]
        facts = refs.get(view) or {}
        mm_long = ((facts.get("gaps") or {}).get("view_size")) or None
        p = os.path.join(pdir, f"{view}.png")
        pair_image(ref, render, f"{view} ({name})", mm_long).save(p)
        images.append((p, f"{view}: the reference photo and the model in the SAME box at one size"
                          + (f" (scale bar in mm; the view is {mm_long:g} mm across)" if mm_long else "")))
        for k, (place, mm, kind) in enumerate(worst_places(facts), 1):
            q = os.path.join(pdir, f"{view}_R{k}.png")
            place_crops(ref, render, place).save(q)
            images.append((q, f"{view}, {place} at its own pixels — the outline is {mm} mm {kind} there"))
    if not images:
        ref = m.get("reference_image")
        hero = os.path.join(REPO, "build", "renders", f"{asset}.png")
        if not ref or not os.path.isfile(os.path.join(REPO, ref)) or not os.path.isfile(hero):
            return _out("fail", f"verify: {asset} has no traced view with a render to compare"
                        + (f" ({'; '.join(skipped)})" if skipped else ""),
                        f"trace each view (kit trace <picture> --name {asset}_<view>), register it "
                        f"(a.trace_match), rebuild (kit asset {asset})")
        sheet = Image.open(hero).convert("RGB")
        tile = sheet.crop((0, 0, sheet.width // 3, sheet.height // 2))
        p = os.path.join(pdir, "reference.png")
        pair_image(Image.open(os.path.join(REPO, ref)).convert("RGB"), tile, "NOT the same camera").save(p)
        images.append((p, "the reference picture beside the model's hero view — NOT the same camera (no traced view): "
                          "compare forms and surfaces, never positions"))
    mine, golden = owner_anchor(asset)
    anchor = ["## The owner first (their verdicts are the only quality signal)"]
    for name, score, date, words in mine:
        anchor.append(f"- THIS asset, {date}: {'%g/10' % score if score is not None else 'no number'} — \"{words[:300]}\"")
    for name, score, date, words in golden:
        anchor.append(f"- loved ({name}, {date}, {score:g}/10): \"{words[:200]}\"")
    if len(anchor) == 1:
        anchor.append("- (no owner verdict yet on this asset or the golden set)")
    prev = done[-1] if done else None
    if prev:
        anchor.append(f"- the LAST round's edit (round {len(done)}): {prev['edit'].get('where')}: "
                      f"{prev['edit'].get('change')} — check it landed")
    rnd = len(done) + 1
    out = os.path.join(pdir, "verify_<n>.json")
    example = {"build": m.get("build_id"), "verifier": "<model>@<harness>, fresh context",
               "differences": [{"image": os.path.basename(p), "difference": "what the REFERENCE shows that the MODEL "
                                "does not (or the reverse), where, how big in mm"} for p, _ in images[:2]],
               "edit": {"where": "the part + side + place a builder can find", "change": "the ONE concrete change "
                        "that closes the biggest difference", "why": "which difference it closes"}}
    prompt = f"""# Verify: {asset} — build {m.get('build_id')} — round {rnd} of {MAX_ROUNDS}

You are a VERIFIER, not a judge: you never score. You did not build this model. For every image below, compare the
MODEL side against the REFERENCE side (they show the same box at the same size) and write ONE difference — the most
important one in that image: what the reference has that the model lacks, or has wrong, where (part + side +
place), and how big (the scale bar is in mm). Then choose ONE edit for the whole model: the single change that
closes the biggest difference. Not a list — one. A difference you cannot see in the images is not there.

{chr(10).join(anchor)}

## The images (each once, in this order)
{chr(10).join(f"{i + 1}. `{_rel(p)}` — {what}" for i, (p, what) in enumerate(images))}
{("(not compared: " + "; ".join(skipped) + ")") if skipped else ""}

## Write `{_rel(out)}` (`<n>` = your verifier number, 1 if alone) — JSON, no score of any kind
```json
{json.dumps(example, indent=2)}
```
One `differences` row per image (its file name in `image`), exactly one `edit`. Then the builder runs:
`lune run kit judge {asset} --record`, makes that one edit, rebuilds, and asks for round {rnd + 1}.
"""
    with open(os.path.join(pdir, "PROMPT.md"), "w", encoding="utf-8") as fh:
        fh.write(prompt)
    return _out("pass", f"verify packet for {asset} (build {m.get('build_id')}), round {rnd}/{MAX_ROUNDS}: "
                f"{len(images)} image(s) — the same crop of reference and model per view, the worst places at 1:1",
                f"hand {_rel(os.path.join(pdir, 'PROMPT.md'))} to a FRESH verifier (never the builder); it writes "
                f"{_rel(out)}; then: lune run kit judge {asset} --record",
                packet=_rel(pdir), images=[_rel(p) for p, _ in images], round=rnd, skipped=skipped)


# ------------------------------------------------------------------------------------------- record
def check(v, build, images):
    """-> problems with one verifier's answer (empty: fine)"""
    out = []
    if not isinstance(v, dict):
        return ["not a JSON object"]
    bad = [k for k in v if str(k).lower() in NO_SCORE_KEYS]
    if bad:
        out.append(f"a verifier never scores: remove {', '.join(bad)}")
    if v.get("build") != build:
        out.append(f"it is for build {v.get('build')}, not the current {build} (make a new packet)")
    diffs = v.get("differences")
    if not isinstance(diffs, list) or not diffs:
        out.append("no differences (one per image)")
    else:
        named = {str(d.get("image")) for d in diffs if isinstance(d, dict) and str(d.get("difference") or "").strip()}
        lacking = [os.path.basename(i) for i in images if os.path.basename(i) not in named]
        if lacking:
            out.append(f"no difference for: {', '.join(lacking[:4])}")
        for d in diffs:
            if isinstance(d, dict) and any(str(k).lower() in NO_SCORE_KEYS for k in d):
                out.append("a difference row carries a score: a verifier describes, never scores")
                break
    e = v.get("edit")
    if isinstance(e, list):
        out.append("one edit, not a list")
    elif not (isinstance(e, dict) and str(e.get("where") or "").strip() and str(e.get("change") or "").strip()):
        out.append("no edit {where, change}")
    return out


def record(asset, files=None):
    m = manifest(asset)
    if m is None:
        return _out("fail", f"verify: {asset} has no build", f"lune run kit asset {asset}")
    pdir = os.path.join(REPO, "build", "judge", asset, "verify")
    files = files or sorted(glob.glob(os.path.join(pdir, "verify_*.json")))
    if not files:
        return _out("fail", f"verify: no answer in {_rel(pdir)}", f"hand {_rel(os.path.join(pdir, 'PROMPT.md'))} to a "
                    "fresh verifier first")
    images = [p for p in glob.glob(os.path.join(pdir, "*.png"))]
    answers, problems = [], []
    for f in files:
        v = _json(f)
        bad = check(v, m.get("build_id"), images)
        if bad:
            problems.append(f"{os.path.basename(f)}: {'; '.join(bad)}")
        else:
            answers.append((f, v))
    if problems and not answers:
        return _out("fail", f"verify: {asset} — the answer is not usable: {problems[0]}", "fix it (or ask again) and "
                    f"run: lune run kit judge {asset} --record", problems=problems)
    done = rounds_now(asset)
    if len(done) >= MAX_ROUNDS:
        return _out("fail", f"verify: {asset} STOP — {MAX_ROUNDS} rounds this attempt", "show the owner")
    f, v = answers[0]   # (one verifier's edit is the round's: several are kept as their differences)
    row = {"round": len(done) + 1, "attempt": attempt(asset), "build": m.get("build_id"),
           "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "verifier": v.get("verifier"),
           "edit": v["edit"], "differences": [d for _f, a in answers for d in a.get("differences") or []]}
    path = os.path.join(REPO, "assets", "models", f"{asset}.verify.json")
    data = _json(path) or {"asset": asset, "rounds": []}
    data.setdefault("rounds", []).append(row)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    for f, _v in answers:   # (an answer is used once: the next round's packet asks again)
        os.replace(f, os.path.join(pdir, f"used_r{row['round']}_{os.path.basename(f)}"))
    e = row["edit"]
    left = MAX_ROUNDS - row["round"]
    return _out("pass", f"verify round {row['round']}/{MAX_ROUNDS} for {asset}: edit — {e['where']}: {e['change']}"[:300],
                (f"make that ONE edit, rebuild (lune run kit asset {asset}), then lune run kit judge {asset} for round "
                 f"{row['round'] + 1}" if left else f"STOP: {MAX_ROUNDS} rounds — show the owner the render beside the "
                 "references"), round=row["round"], edit=e, problems=problems)


def main(argv):
    if len(argv) < 2 or argv[0] not in ("packet", "record"):
        return _out("fail", "verifier: packet|record <asset> [answer.json ...]", "lune run kit judge <asset>")
    return packet(argv[1]) if argv[0] == "packet" else record(argv[1], argv[2:] or None)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
