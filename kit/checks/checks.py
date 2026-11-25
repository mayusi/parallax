"""kit checks - the owner's recurring words as CHECKS that run on the work, kept honest by the owner's verdicts.

The owner, 2026-11-08 ("Yes, sprint 2"): "your recurring words become checks, and the checks are tested against your
verdicts". Each lane keeps its checks in kit/knowledge/vault/<lane>/checks.json: the owner's words that made a check
(with the verdicts that said them), what it measures, when it fails, and its STATUS, set by evidence only:
  proposed  - from the owner's words, not proven yet: it reports, it never blocks
  validated - it caught >= MIN_CAUGHT pieces the owner rejected WITH these words and spared every one of >= MIN_SPARED
              pieces the owner loved, kept or picked (only then may a lane make it a gate, and only a stricter one)
  retired   - it flagged more loved pieces than it caught: the owner's criteria moved on (EvalGen's "criteria drift")
  built in  - the check already lives inside a lane command (listed so the owner's words map to it)
A check with no threshold yet only reports its number; `validate` proposes one when the owner's pieces split cleanly.

usage:
  python kit/checks/checks.py list <lane> [--root R]
  python kit/checks/checks.py run <lane> <target> [--root R]     (anim: <Move>/round_K; vfx: <effect>)
  python kit/checks/checks.py validate <lane> [--dry] [--quick] [--root R]   (--quick: no GPU measure)
Each prints one JSON line last ({"lines": [...], ...}). Only `validate` writes, and only checks.json (not with --dry).
"""

import copy
import datetime
import glob
import itertools
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIT_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(KIT_ROOT, "kit", "anim"))
import check_validate as CV  # noqa: E402  (round manifests, the owner's own verdict notes)

MIN_CAUGHT = 3
MIN_SPARED = 3
MIN_FIT = 2  # an automatic threshold needs at least two of the owner's rejections and two loved pieces to split
TARGET_KIND = {"anim": "round", "vfx": "effect"}


# ------------------------------------------------------------------ measures (a number, or None when not measurable)
def split_round(target):
    m = re.match(r"^(.+)/round_(\d+)$", target)
    if not m:
        raise ValueError(f"an anim target is <Move>/round_K (got {target})")
    return m.group(1), int(m.group(2))


def load_round(root, target):
    move, rnd = split_round(target)
    path = os.path.join(root, "assets", "animations", "candidates", move, f"round_{rnd}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


SLIDER_RANGE = 2.0  # the Laban sliders run -1..1 (kit/anim/proc_picks.py draws them as (v + 1) / 2)


def slider_spread(root, target):
    """how far apart a round's candidates are in the generator's own settings: the mean pairwise distance of the sliders
    EVERY candidate has and that actually vary in the round (a slider that is the same for all - an "arms" habit fixed
    to one value - says nothing and must not dilute the others: the 2026-11-08 review), numbers scaled by the slider
    range, a categorical setting counting 1 when it differs; 0..1"""
    man = load_round(root, target)
    vecs = [c.get("sliders") or {} for c in (man or {}).get("candidates", [])]
    if len(vecs) < 2:
        return None
    keys = sorted(set.intersection(*(set(v) for v in vecs)))
    keys = [k for k in keys if len({json.dumps(v[k], sort_keys=True) for v in vecs}) > 1]
    if not keys:
        return 0.0
    num = [k for k in keys if all(isinstance(v[k], (int, float)) for v in vecs)]
    dists = []
    for a, b in itertools.combinations(vecs, 2):
        d = sum(((float(a[k]) - float(b[k])) / SLIDER_RANGE) ** 2 for k in num)
        d += sum(1.0 for k in keys if k not in num and str(a[k]) != str(b[k]))
        dists.append(math.sqrt(d / len(keys)))
    return round(sum(dists) / len(dists), 4)


def vision():
    """kit/vision/run.py loaded under its own name (a plain `import run` would take any module called run already
    loaded); its folder stays on the path for its own imports"""
    import importlib.util  # noqa: PLC0415

    if "kit_vision_run" in sys.modules:
        return sys.modules["kit_vision_run"]
    folder = os.path.join(KIT_ROOT, "kit", "vision")
    if folder not in sys.path:
        sys.path.insert(0, folder)
    spec = importlib.util.spec_from_file_location("kit_vision_run", os.path.join(folder, "run.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["kit_vision_run"] = mod
    spec.loader.exec_module(mod)
    return mod


def look_spread(root, target):
    """how different a round's candidates LOOK: 1 - the mean pairwise SigLIP 2 cosine of each pick-sheet gif's middle
    frame (the kit's own offline vision model, kit/vision/run.py). None when the round's gifs are gone."""
    move, rnd = split_round(target)
    gifs = sorted(glob.glob(os.path.join(root, "build", "candidates", move, f"round_{rnd}", "*.gif")))
    if len(gifs) < 2:
        return None
    from PIL import Image  # noqa: PLC0415

    frames = []
    for g in gifs:
        with Image.open(g) as im:
            if getattr(im, "is_animated", False):
                im.seek(im.n_frames // 2)
            frames.append(im.convert("RGB"))
    V = vision()

    e = V.embed(frames)
    sims = [float(e[i] @ e[j]) for i, j in itertools.combinations(range(len(frames)), 2)]
    return round(1 - sum(sims) / len(sims), 4)


def warned_share(root, target):
    """the share of a round's shown candidates that carry the kit's own warnings (a limb or the blade outside the
    loved clips' range)"""
    cands = (load_round(root, target) or {}).get("candidates", [])
    if not cands or not any("warnings" in c for c in cands):
        return None  # a round made before the kit wrote warnings: not measured, never "clean"
    return round(sum(1 for c in cands if c.get("warnings")) / len(cands), 4)


def vfx_recording(root, effect):
    for p in (os.path.join(root, "library", "vfx", "effects", effect, "previews", "hero.mp4"),
              os.path.join(root, "build", "vfx", "booth", f"{effect}_play_hero.mp4")):
        if os.path.isfile(p):
            return p
    return None


def motion_energy(root, target):
    """how much an effect MOVES on screen: the mean absolute change between consecutive frames of its hero recording -
    the library's (library/vfx/effects/<effect>/previews/hero.mp4), else the player's newest (build/vfx/booth/
    <effect>_play_hero.mp4, what `kit vfx play --record` writes) - grey, 160 px wide, 0..1"""
    path = vfx_recording(root, target)
    if not path:
        return None
    import cv2  # noqa: PLC0415

    cap = cv2.VideoCapture(path)
    prev, diffs = None, []
    while len(diffs) < 240:
        ok, frame = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = g.shape
        g = cv2.resize(g, (160, max(1, round(h * 160 / w))))
        if prev is not None:
            diffs.append(float(cv2.absdiff(g, prev).mean()) / 255.0)
        prev = g
    cap.release()
    return round(sum(diffs) / len(diffs), 5) if diffs else None


MEASURES = {
    "slider_spread": slider_spread,
    "look_spread": look_spread,
    "warned_share": warned_share,
    "motion_energy": motion_energy,
}


# ------------------------------------------------------------------ the owner's pieces, labelled per check
def polarity(front):
    try:
        s = float(front.get("score", ""))
        return 1 if s >= 7 else -1 if s <= 3 else 0
    except ValueError:
        return {"keep": 1, "redo": -1}.get(front.get("direction"))


def owner_notes(root, lane, guessed_too=False):
    """the owner's OWN verdict notes of a lane (a guessed number never counts): [(name, polarity, words, where)].
    guessed_too: also the notes whose number a model guessed from the owner's words - used ONLY to take evidence away
    (a pick the owner's words then ran down is not "spared"), never to add a rejection or a loved piece"""
    out = []
    for p in sorted(glob.glob(os.path.join(root, "kit", "knowledge", "vault", lane, "verdicts", "*.md"))):
        front, body = CV.front_and_body(p)
        if guessed_too or CV.owners_own(front):
            out.append((str(front.get("name", "")), polarity(front), " ".join(body.split()),
                        os.path.relpath(p, root).replace(os.sep, "/")))
    return out


def targets(root, lane):
    if lane == "anim":
        return [f"{r['move']}/round_{r['round']}" for r in CV.load_rounds(root)]
    if lane == "vfx":
        hits = glob.glob(os.path.join(root, "library", "vfx", "effects", "*", "previews", "hero.mp4"))
        names = {os.path.basename(os.path.dirname(os.path.dirname(p))) for p in hits}
        for p in glob.glob(os.path.join(root, "build", "vfx", "booth", "*_play_hero.mp4")):
            name = os.path.basename(p)[: -len("_play_hero.mp4")]
            if not name.startswith("_"):  # "_bf_..." are the player's own probes, not effects
                names.add(name)
        return sorted(names)
    return []


def known_target(root, lane, target):
    """does the target exist at all? (a mistyped name must never pass quietly)"""
    if lane == "anim":
        return load_round(root, target) is not None
    if lane == "vfx":
        return os.path.isdir(os.path.join(root, "library", "vfx", "effects", target)) or bool(vfx_recording(root, target))
    return False


NEGATION = re.compile(r"(?:\bnot|\bno|n't|\bnever|\bisnt|\bwasnt|\bdosent|\bdoesnt)\s+(?:[\w']+\s+){0,2}$")
NEGATION_AFTER = re.compile(r"^\W{0,4}(?:not|no)\b")
REJECT_WORDS = ("horrible", "bad", "trash", "scrap", "ugly", "awful", "garbage", "dumb", "lame", "worse", "hate")
PRAISE_WORDS = ("wow", "amazing", "love", "loved", "best", "splendid", "impressed", "beautiful", "perfect", "surprised")


def said(text, words):
    """the owner SAID one of the words: whole words only ("cousins", not "cousinship"), and never a negated one
    ("not static at all", "it doesnt look static", "static? not at all" are not the complaint)"""
    low = text.lower()
    for w in words:
        for m in re.finditer(r"(?<!\w)" + re.escape(w.lower()) + r"(?!\w)", low):
            if NEGATION.search(low[max(0, m.start() - 24):m.start()]):
                continue
            if NEGATION_AFTER.search(low[m.end():m.end() + 12]):
                continue
            return True
    return False


def measure(check, root, target):
    """the check's number for a target, or (None, why) - a measure that breaks is "not measurable", never a pass, and
    never stops the other checks"""
    try:
        return MEASURES[check["measure"]](root, target), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:80]}"


def labels(root, lane, check):
    """{target: ("positive" | "negative", where)}: positive = the owner rejected it saying the check's words (or, with
    no number, said them); negative = the owner loved, kept or picked it. Everything else is unknown, never counted."""
    words = check.get("words", [])
    out = {}
    if lane == "anim":
        rounds = CV.load_rounds(root)
        moves = {r["move"].lower(): r["move"] for r in rounds}
        # every owner verdict on a round or on one of its candidates ("<Move>/rK/cN" notes included)
        on, ran_down = {}, {}
        for name, pol, text, where in owner_notes(root, "anim"):
            for move, rnd, cand in CV.verdict_targets(name, text, moves):
                on.setdefault(f"{move}/round_{rnd}", []).append((pol, text, where, cand))
        for name, pol, text, _where in owner_notes(root, "anim", guessed_too=True):
            for move, rnd, cand in CV.verdict_targets(name, text, moves):
                if pol in (-1, 0):
                    ran_down.setdefault(f"{move}/round_{rnd}", []).append(cand)
        picked = {p for r in rounds for p in r["parents"] if isinstance(p, str) and "/r" in p}
        for r in rounds:
            t = f"{r['move']}/round_{r['round']}"
            notes = on.get(t, [])
            rejected = next((w for pol, text, w, _ in notes if pol == -1 and said(text, words)), None)
            if rejected:
                out[t] = ("positive", rejected)
                continue
            loved = next((w for pol, _text, w, _ in notes if pol == 1), None)
            if loved:
                out[t] = ("negative", loved)
                continue
            picks = {p.rsplit("/", 1)[-1] for p in picked if p.startswith(f"{r['move']}/r{r['round']}/")}
            # a pick the owner's later words ran down (6 or less, a Redo - even a number guessed from those words) was
            # the best of a bad lot, never "spared"
            overruled = any(cand is None or cand in picks for cand in ran_down.get(t, []))
            if picks and not overruled:
                out[t] = ("negative", "the owner picked from it")
    elif lane == "vfx":
        measurable = set(targets(root, "vfx"))
        rows = {}
        for name, pol, text, where in owner_notes(root, "vfx"):
            rows.setdefault(name, []).append((pol, text, where))
        lib = os.path.join(root, "library", "vfx", "verdicts.json")
        if os.path.isfile(lib):
            with open(lib, encoding="utf-8") as f:
                for name, items in json.load(f).items():
                    for it in items:
                        rows.setdefault(name, []).append((None, str(it.get("words", "")), "library/vfx/verdicts.json"))
        for name, items in rows.items():
            if name not in measurable:
                continue
            # a rejection: the owner's 3 or less / Redo saying the words, or no number but the words AND a plain
            # rejection ("horrible", "trash") - a 4-6, or praise that happens to use the word, never counts
            hit = next((where for pol, text, where in items
                        if said(text, words) and (pol == -1 or (pol is None and said(text, REJECT_WORDS)))), None)
            if hit:
                out[name] = ("positive", hit)
            else:
                # loved: 7+ / Keep, or no number and plain praise ("WOW", "amazing")
                loved = next((where for pol, text, where in items
                              if pol == 1 or (pol is None and said(text, PRAISE_WORDS) and not said(text, REJECT_WORDS))),
                             None)
                if loved:
                    out[name] = ("negative", loved)
    return out


# ------------------------------------------------------------------ checks.json
def checks_path(root, lane):
    return os.path.join(root, "kit", "knowledge", "vault", lane, "checks.json")


def load(root, lane):
    p = checks_path(root, lane)
    if not os.path.isfile(p):
        return {"lane": lane, "checks": []}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def fails(check, v):
    thr = check.get("threshold")
    if v is None or thr is None:
        return None
    return v <= thr if check.get("fails_when", "below") == "below" else v >= thr


def fmt(v):
    return "-" if v is None else f"{v:g}"


def do_list(root, lane, _args):
    data = load(root, lane)
    lines = []
    for c in data["checks"]:
        val = c.get("validation") or {}
        lines.append(f"  {c['id']} [{c.get('status', 'proposed')}] {c.get('measure')} "
                     f"{'fails ' + c.get('fails_when', 'below') + ' ' + fmt(c.get('threshold')) if c.get('threshold') is not None else 'reports only'}"
                     f" - from the owner's words: {', '.join(repr(w) for w in c.get('words', []))}"
                     + (f"; last validated {val.get('date')}: caught {val.get('caught')}, false alarms "
                        f"{val.get('false_alarms')}" if val else ""))
    return {"lines": lines, "lane": lane, "checks": len(data["checks"])}


def do_run(root, lane, args):
    if not args:
        raise ValueError("run needs a target (anim: <Move>/round_K; vfx: <effect>)")
    target = args[0]
    try:
        known = known_target(root, lane, target)
    except ValueError:
        known = False
    if not known:
        raise ValueError(f"unknown target {target} for {lane} (anim: <Move>/round_K with a manifest; vfx: an effect in "
                         "library/vfx/effects or with a player recording)")
    lines, failed, measured = [], [], 0
    for c in load(root, lane)["checks"]:
        if c.get("status") in ("retired", "built in") or c.get("target") != TARGET_KIND.get(lane):
            continue
        v, err = measure(c, root, target)
        f = fails(c, v)
        measured += 0 if v is None else 1
        state = (f"not measurable ({err})" if err else "not measurable") if v is None else (
            "reports" if f is None else ("FAIL" if f else "pass"))
        loved = (c.get("validation") or {}).get("loved_range")
        if f is None and v is not None and loved:
            state += f"; the owner's loved / picked measured {fmt(loved[0])}-{fmt(loved[1])}"
        if f:
            failed.append(c["id"])
        lines.append(f"  {c['id']} [{c.get('status', 'proposed')}]: {state} ({c['measure']} {fmt(v)}"
                     f"{', fails ' + c.get('fails_when', 'below') + ' ' + fmt(c.get('threshold')) if c.get('threshold') is not None else ''})"
                     f" - the owner: {', '.join(repr(w) for w in c.get('words', []))}")
    return {"lines": lines, "lane": lane, "target": target, "failed": failed, "measured": measured}


def validate_check(root, lane, check, today):
    labs = labels(root, lane, check)
    pos, neg = [], []
    for t, (kind, where) in sorted(labs.items()):
        v, _err = measure(check, root, t)
        if v is not None:
            (pos if kind == "positive" else neg).append({"target": t, "value": v, "where": where})
    below = check.get("fails_when", "below") == "below"
    proposed_now = False
    if check.get("threshold") is None and len(pos) >= MIN_FIT and len(neg) >= MIN_FIT:
        edge_pos = max(p["value"] for p in pos) if below else min(p["value"] for p in pos)
        edge_neg = min(n["value"] for n in neg) if below else max(n["value"] for n in neg)
        if (below and edge_pos < edge_neg) or (not below and edge_pos > edge_neg):
            check["threshold"] = round((edge_pos + edge_neg) / 2, 5)
            check["threshold_from"] = (f"auto {today}: halfway between the owner's rejection ({edge_pos:g}) and the "
                                       f"nearest loved / picked piece ({edge_neg:g})")
            check["fit_on"] = sorted({p["target"] for p in pos} | {n["target"] for n in neg})
            proposed_now = True
    # a threshold is never tested on the pieces it was fit on (that would be circular): those sit out
    fit = set(check.get("fit_on") or [])
    held_out = [x["target"] for x in pos + neg if x["target"] in fit]
    pos = [p for p in pos if p["target"] not in fit]
    neg = [n for n in neg if n["target"] not in fit]
    caught = [p["target"] for p in pos if fails(check, p["value"])]
    missed = [p["target"] for p in pos if not fails(check, p["value"])]
    alarms = [n["target"] for n in neg if fails(check, n["value"])]
    before = check.get("status", "proposed")
    status = before
    if before != "built in":
        if check.get("threshold") is not None and len(caught) >= MIN_CAUGHT and not alarms and len(neg) >= MIN_SPARED:
            status = "validated"
        elif len(neg) >= MIN_SPARED and len(alarms) > len(caught):
            status = "retired"
        elif before == "validated" and alarms:
            status = "proposed"  # the owner's later verdict proved it wrong on a loved piece: it stops blocking
        elif before != "retired":
            status = "proposed"
    check["status"] = status
    has_thr = check.get("threshold") is not None
    check["validation"] = {"date": today, "caught": len(caught) if has_thr else None,
                           "missed": len(missed) if has_thr else None,
                           "false_alarms": len(alarms) if has_thr else None,
                           # nothing is caught or spared without a threshold: those stay null, never a count
                           "spared": len(neg) - len(alarms) if check.get("threshold") is not None else None,
                           "rejections_measured": len(pos),
                           "loved_measured": len(neg), "caught_targets": caught, "alarm_targets": alarms,
                           "held_out_fit": held_out,
                           "loved_range": [min(n["value"] for n in neg), max(n["value"] for n in neg)] if neg else None,
                           "rejected_range": [min(p["value"] for p in pos), max(p["value"] for p in pos)] if pos else None}
    need = []
    if check.get("threshold") is None:
        need.append("a threshold (the owner's rejections and loved pieces do not split yet)")
    if len(pos) < MIN_CAUGHT:
        need.append(f"{MIN_CAUGHT - len(pos)} more rejection(s) with these words, measured")
    if len(neg) < MIN_SPARED:
        need.append(f"{MIN_SPARED - len(neg)} more loved / kept / picked piece(s), measured")
    said_words = ", ".join(repr(w) for w in check.get("words", []))
    line = (f"  {check['id']}: {before} -> {status} - "
            + (f"caught {len(caught)} of {len(pos)} new rejection(s) saying {said_words}; flagged {len(alarms)} of "
               f"{len(neg)} loved / picked" if check.get("threshold") is not None else
               f"measured {len(pos)} rejection(s) saying {said_words} and {len(neg)} loved / picked, no threshold yet")
            + (f"; threshold auto-proposed {check['threshold']:g} from {len(held_out)} of the owner's pieces"
               if proposed_now else "")
            + (f" ({len(held_out)} piece(s) its threshold was fit on sit out)" if held_out else "")
            + (f"; needs {'; '.join(need)}" if need and status != "validated" else ""))
    return line


HEAVY = {"look_spread"}  # loads a GPU model: skipped by --quick (the automatic re-test after each verdict)


def material(data):
    """the checks without their validation dates: a re-test that changed nothing else writes nothing (the automatic
    re-test runs after every verdict - a new date each day would be a churn line in git, and a hand-formatted file
    rewritten)"""
    d = copy.deepcopy(data)
    for c in d.get("checks", []):
        if isinstance(c.get("validation"), dict):
            c["validation"].pop("date", None)
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


def do_validate(root, lane, args):
    dry = "--dry" in args
    quick = "--quick" in args
    data = load(root, lane)
    before = material(data)
    today = datetime.date.today().isoformat()
    lines = []
    for c in data["checks"]:
        if c.get("status") == "built in" or c.get("measure") not in MEASURES:
            lines.append(f"  {c['id']}: {c.get('status')} - {c.get('builtin', 'no measure')}")
            continue
        if quick and c.get("measure") in HEAVY:
            lines.append(f"  {c['id']}: left as it was (--quick skips the GPU measure {c['measure']})")
            continue
        lines.append(validate_check(root, lane, c, today))
    changed = material(data) != before
    written = not dry and changed
    if written:
        with open(checks_path(root, lane), "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.write("\n")
    counts = {}
    for c in data["checks"]:
        counts[c.get("status", "proposed")] = counts.get(c.get("status", "proposed"), 0) + 1
    return {"lines": lines, "lane": lane, "status": counts, "written": written, "changed": changed}


def main(argv):
    root = argv[argv.index("--root") + 1] if "--root" in argv else "."
    args, skip = [], False
    for a in argv[1:]:
        if skip:
            skip = False
        elif a == "--root":
            skip = True
        else:
            args.append(a)
    if len(args) < 2 or args[0] not in ("list", "run", "validate"):
        print(json.dumps({"error": "usage: checks.py list|run|validate <lane> [target] [--dry] [--root R]"}))
        return 2
    sub, lane, rest = args[0], args[1], args[2:]
    try:
        res = {"list": do_list, "run": do_run, "validate": do_validate}[sub](root, lane, rest)
    except (ValueError, KeyError, OSError) as e:
        print(json.dumps({"error": str(e)}))
        return 1
    for line in res["lines"]:
        print(line)
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
