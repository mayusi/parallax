"""judge_pair.py — PAIRWISE judging: two builds of one model side by side, at the same camera and light, view by view
and region by region. The judges say which is better; the kit never asks them for a number.

    python kit/blender/judge_pair.py pair <asset> [[A] B] [--judges N] [--seed S]
        build/judge/<asset>/pair/judge_<n>/ for each of N judges (default 3): views.png (the reference + six standard
        views of both), game_<camera>.png (the brief's game camera), r<i>_<region>.png (the reference crop | both,
        close up) and PROMPT.md. Which build is #1 (left) is shuffled item by item and judge by judge; the KEY is in
        build/judge/<asset>/pairkeys/<round>.json, never in a packet.
    python kit/blender/judge_pair.py tally <asset> [answer.json ...]
        the judges' answers (default: build/judge/<asset>/pair/judge_*/answer*.json) -> per item win / loss / tie
        counts for shape and for surface, where the judges disagree, the defects a majority saw ->
        build/judge/<asset>/pairwise.json + "pairwise" in the verdict (assets/models/<asset>.judge.json)

A and B: current (the last build), accepted (kit accept), judged (the last recorded verdict's build), previous (the
newest kept build before the current one), i<N> (iteration N) or a build id (4+ of its first characters). One version
named: the current build against it. None: current against accepted, or against previous when the accepted build
has no kept views. Every full build keeps its
views in build/judge/<asset>/builds/<build id>/ (rbx_judgeviews.py), the newest 30 plus the accepted and judged ones.

Why: a PAIR is judged far more reliably than an absolute 0-100 score; six RGB views judge as well as denser multi-view
or depth / normal inputs; single views and cheap proxies (silhouette IoU, CLIP) agree with people 20-40% less; several
independent judges, each blind to the others and to which side is which, cancel one judge's bias and every judge's
left-first bias. AI judges are weakest on texture, so the surface is asked apart from the shape. The judges are the
same model the owner runs (several fresh contexts), never another model family. Plain Python + Pillow.
"""

import datetime
import glob
import json
import os
import random
import re
import secrets
import shutil
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from judge import _fit, _font  # noqa: E402 — (the absolute judge's image helpers)

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REPO = os.path.dirname(KIT)
VIEWS = (("front", "FRONT"), ("back", "BACK"), ("left", "LEFT SIDE"), ("right", "RIGHT SIDE"), ("top", "TOP"),
         ("three_quarter", "THREE-QUARTER"))
# 3D-DefectBench's nine categories: (key, family, what it means)
DEFECTS = (
    ("broken_missing", "geometry", "broken or missing parts"),
    ("floating_intersecting", "geometry", "floating or intersecting parts"),
    ("distorted_proportions", "geometry", "distorted proportions"),
    ("surface_holes", "geometry", "surface artifacts or holes"),
    ("wrong_shape", "geometry", "wrong topology or shape"),
    ("blur_low_detail", "texture", "blurry or low-detail texture"),
    ("wrong_colour_material", "texture", "wrong colours or material"),
    ("seams_stretching", "texture", "seams or stretching"),
    ("baked_lighting", "texture", "baked-in lighting or inconsistent shading"),
)
SURFACE = (
    ("roughness", "its roughness varies believably, not one plastic sheen"),
    ("wear", "edge wear and grime sit where use would put them, and nowhere else"),
    ("colour", "its colours and materials match the reference"),
)
PICKS = ("1", "2", "same")
BG = (24, 24, 26)
INK = (255, 210, 90)
W = 1600  # every packet image: vision models shrink anything wider, so the sheets are built at native size


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


def _jdir(asset):
    return os.path.join(REPO, "build", "judge", asset)


def stored(asset):
    """the builds whose views are kept -> [meta (+ "_dir")], oldest first"""
    out = []
    for path in glob.glob(os.path.join(_jdir(asset), "builds", "*", "meta.json")):
        m = _json(path)
        if isinstance(m, dict) and m.get("build"):
            out.append({**m, "_dir": os.path.dirname(path)})
    return sorted(out, key=lambda m: (str(m.get("at") or ""), m["build"]))


def resolve(token, kept, current=None, accepted=None, judged=None):
    """a version token -> (meta, None) or (None, why). kept: stored(); current: the manifest's build id; accepted:
    the accepted.json record; judged: the judge.json record."""
    t = str(token or "").strip().lower()
    by = {m["build"]: m for m in kept}
    newest = lambda ms: (ms[-1], None) if ms else (None, None)  # noqa: E731

    def build(b, label):
        if not b:
            return None, f"there is no {label} build"
        if b in by:
            return by[b], None
        return None, (f"the {label} build ({b}) has no kept views — only full builds with previews keep them "
                      f"(rebuild it, or pick another: {_choices(kept)})")

    if t in ("current", "now", "last", "latest"):
        return build(current, "current")
    if t == "judged":
        return build((judged or {}).get("build"), "last judged")
    if t == "accepted":
        acc = accepted or {}
        if not acc:
            return None, "there is no accepted build (the owner accepts one: lune run kit accept <asset>)"
        if acc.get("build") in by:
            return by[acc["build"]], None
        same = [m for m in kept if m.get("iteration") == acc.get("iteration") and acc.get("script_sha")
                and m.get("script_sha") == acc.get("script_sha")]
        if same:
            return newest(same)
        return None, (f"the accepted build (iteration {acc.get('iteration')}, build {acc.get('build')}) has no kept "
                      f"views — builds keep them from this kit on; pick another: {_choices(kept)}")
    if t in ("previous", "prev"):
        cur = by.get(current)
        older = [m for m in kept if m["build"] != current and (cur is None or str(m.get("at")) <= str(cur.get("at")))]
        return newest(older) if older else (None, "no kept build before the current one")
    m = re.fullmatch(r"(?:i|it|iter|iteration)[:=]?(\d+)|(\d{1,3})", t)
    if m:
        n = int(m.group(1) or m.group(2))
        hits = [x for x in kept if x.get("iteration") == n]
        return newest(hits) if hits else (None, f"no kept build of iteration {n} ({_choices(kept)})")
    if re.fullmatch(r"[0-9a-f]{4,40}", t):
        hits = [x for x in kept if x["build"].startswith(t)]
        if len(hits) == 1:
            return hits[0], None
        return None, (f"build {t}: {'more than one kept build starts so' if hits else 'not kept'} ({_choices(kept)})")
    return None, f"'{token}' is not a version: current, accepted, judged, previous, i<N> or a build id"


def _choices(kept):
    if not kept:
        return "no build has kept views yet"
    return "kept: " + ", ".join(f"i{m.get('iteration')}={m['build'][:6]}" for m in kept[-8:])


def _regions_spec(asset, m):
    """-> (the picture the region boxes are on, [regions]) from the build's region map"""
    spec = _json(os.path.join(REPO, m.get("regions_file") or f"refs/{asset}.regions.json")) or {}
    image = spec.get("image") or m.get("reference_image")
    return image, [r for r in spec.get("regions", []) if isinstance(r, dict) and r.get("name")]


def _open(path):
    try:
        return Image.open(path).convert("RGB") if path and os.path.isfile(path) else None
    except OSError:
        return None


def _tag(tile, text, size=24):
    d = ImageDraw.Draw(tile)
    f = _font(size)
    box = d.textbbox((0, 0), text, font=f)
    d.rectangle((0, 0, box[2] + 16, box[3] + 10), fill=(0, 0, 0))
    d.text((8, 4), text, font=f, fill=INK)
    return tile


def _tile(img, w, h, tag, missing="MISSING"):
    if img is None:
        tile = Image.new("RGB", (w, h), (40, 20, 22))
        ImageDraw.Draw(tile).text((14, h // 2 - 12), missing, font=_font(22), fill=(255, 110, 110))
        return _tag(tile, tag)
    return _tag(_fit(img, w, h, BG), tag)


def _sheet(rows, path):
    """rows: [(header or None, [(image, x)], height)] -> one PNG W wide"""
    head = 36
    H = sum(h + (head if t else 0) + 10 for t, _, h in rows)
    out = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(out)
    y = 0
    for title, tiles, h in rows:
        if title:
            d.text((6, y + 6), title, font=_font(24), fill=INK)
            y += head
        for img, x in tiles:
            out.paste(img, (x, y))
        y += h + 10
    out.save(path, optimize=True)
    return path


def _ident(token, meta):
    return {"token": token, "build": meta["build"], "iteration": meta.get("iteration"), "at": meta.get("at"),
            "score": meta.get("score")}


def _items(A, B, regions):
    """the items judged: overall, the game cameras both builds have, every region -> [(item, kind, payload)]"""
    out = [("overall", "views", None)]
    for kind in sorted(set(A.get("game") or {}) & set(B.get("game") or {})):
        out.append((f"game_{kind}", "game", kind))
    taken = {"overall"} | {i for i, _, _ in out}
    for i, r in enumerate(regions):
        name = str(r["name"])
        item = name if name not in taken and not name.startswith("game_") else f"region_{name}"
        taken.add(item)
        out.append((item, "region", (i, r)))
    return out


def _compose(jdir, first, A, B, ref_image, reg_image, items):
    """one judge's images -> {item: file}; first[item] = "a" | "b" (the build shown as #1, on the left)"""
    pick = lambda item: (A, B) if first[item] == "a" else (B, A)  # noqa: E731
    files = {}
    ref = _open(os.path.join(REPO, ref_image)) if ref_image else None
    reg_pic = _open(os.path.join(REPO, reg_image)) if reg_image else None
    for item, kind, payload in items:
        one, two = pick(item)
        if kind == "views":
            rows = []
            if ref is not None:
                rows.append(("REFERENCE", [(_fit(ref, W, 380, BG), 0)], 380))
            tw, th = 390, 292
            for k in range(0, len(VIEWS), 2):
                tiles = []
                for c, (view, title) in enumerate(VIEWS[k:k + 2]):
                    x = c * 820
                    tiles.append((_tile(_open(os.path.join(one["_dir"], f"{view}.png")), tw, th, f"#1 {title}"), x))
                    tiles.append((_tile(_open(os.path.join(two["_dir"], f"{view}.png")), tw, th, f"#2 {title}"),
                                  x + tw))
                rows.append((None, tiles, th))
            files[item] = _sheet(rows, os.path.join(jdir, "views.png"))
        elif kind == "game":
            name = f"game_{payload}.png"
            tiles = [(_tile(_open(os.path.join(one["_dir"], name)), 780, 439, "#1"), 0),
                     (_tile(_open(os.path.join(two["_dir"], name)), 780, 439, "#2"), 820)]
            files[item] = _sheet([(f"IN THE GAME: {payload.replace('_', ' ')}", tiles, 439)], os.path.join(jdir, name))
        else:
            i, r = payload
            tw, th = 520, 390
            crop = None
            if reg_pic is not None and isinstance(r.get("box"), (list, tuple)) and len(r["box"]) == 4:
                crop = reg_pic.crop(tuple(int(v) for v in r["box"]))
            tiles = [(_tile(crop, tw, th, "REFERENCE", "no reference crop"), 0)]
            for j, meta in enumerate((one, two)):
                f = (meta.get("regions") or {}).get(r["name"])
                tiles.append((_tile(_open(os.path.join(meta["_dir"], f)) if f else None, tw, th, f"#{j + 1}",
                                    "not on this version (no part of the region)"), (j + 1) * (tw + 20)))
            fname = f"r{i + 1}_{re.sub(r'[^A-Za-z0-9_-]+', '_', r['name'])}.png"
            files[item] = _sheet([(f"R{i + 1} {r['name']}: REFERENCE | #1 | #2", tiles, th)], os.path.join(jdir, fname))
    return files


def _example(items):
    one = {
        "shape": "1 | 2 | same", "shape_why": "one line: the difference you saw (what is better made, where)",
        "surface": "1 | 2 | same", "surface_why": "one line: whose surface is more believable, and why",
        "surface_checks": {t: {k: "yes | no" for k, _ in SURFACE} for t in ("1", "2")},
        "defects": {t: {c: "no | yes: <where>" for c, _, _ in DEFECTS} for t in ("1", "2")},
    }
    body = {items[0]: one}
    if len(items) > 1:
        body["..."] = "the same object for EVERY item: " + ", ".join(items[1:])
    return {"packet": "<packet>", "judge": "<model>@<harness>, fresh context", "items": body}


def _prompt(asset, packet, items, files, A, B, regions_by_item, answer_rel):
    lines = []
    for item, kind, payload in items:
        f = os.path.basename(files[item])
        if kind == "views":
            lines.append(f"- `{item}` — `{f}`: the reference on top (when there is one), then six standard views of "
                         "#1 and #2 (front, back, left side, right side, top: orthographic; three-quarter: "
                         "perspective).")
        elif kind == "game":
            title = (A.get("game") or {}).get(payload) or payload
            lines.append(f"- `{item}` — `{f}`: the model as a player sees it in the game ({title}). Judge what reads "
                         "at that size: the silhouette, the big shapes, the material read.")
        else:
            qs = regions_by_item.get(item) or []
            look = (" Look for: " + " · ".join(qs)) if qs else ""
            lines.append(f"- `{item}` — `{f}`: the REFERENCE crop | #1 | #2, close up.{look}")
    framed = ""
    if A.get("frame") and B.get("frame") and A["frame"] != B["frame"]:
        framed = ("\nThe two were framed differently (the model changed size a lot between them): compare shape and "
                  "finish, not size on screen.\n")
    defects = "\n".join(f"   - `{c}` ({fam}): {what}" for c, fam, what in DEFECTS)
    checks = " · ".join(f"`{k}` ({what})" for k, what in SURFACE)
    example = json.dumps({**_example([i for i, _, _ in items]), "packet": packet}, indent=2)
    return f"""# Pairwise judge: {asset} — packet {packet}

You compare two versions of one 3D model, shown as **#1** (left) and **#2** (right) at the same camera and the same
light. You do not know which is newer or which one the builder hopes wins, and which version is #1 changes from image
to image — judge every image on its own. You built neither and gain nothing from either winning. Other judges answer
the same packet independently: do not look for their answers, and look only at the files in this folder.
{framed}
## Items — one answer each
{chr(10).join(lines)}

## For every item
1. `shape`: `1`, `2` or `same` — which is closer to the reference and better made in FORM: silhouette, proportions,
   the parts and their detail, how cleanly they are built. `same` only when you truly cannot choose.
   `shape_why`: one line naming the difference you saw (what is better, where) — not "#1 is better".
2. `surface`: `1`, `2` or `same`, judged APART from the shape — whose SURFACE is more believable: roughness that
   varies (not one plastic sheen), edge wear and grime where hands and use would put them (and nowhere else), colours
   and materials that match the reference. `surface_why`: one line. Then, for #1 and for #2, `surface_checks` —
   `yes` or `no` each: {checks}. AI judges are weakest on texture: look closely at the surface before you answer.
3. `defects`: for #1 and for #2, each of the nine 3D-DefectBench categories — `no`, or `yes: <where>` (the part, the
   side, the position — e.g. `yes: the scope floats above the rail, top right`):
{defects}

## Write your answer as JSON to `{answer_rel}`
```json
{example}
```
Every item needs a full answer ({len(items)}: {", ".join(i for i, _, _ in items)}). Then the builder runs:
`lune run kit judge {asset} --tally`
"""


def _retire(pdir):
    """a new round: the last round's answers move to pair/old/ (still tallied by name: their keys are kept), its
    images go"""
    for path in glob.glob(os.path.join(pdir, "judge_*", "answer*.json")):
        os.makedirs(os.path.join(pdir, "old"), exist_ok=True)
        packet = str((_json(path) or {}).get("packet") or "unknown")
        dest = os.path.join(pdir, "old", f"{re.sub(r'[^A-Za-z0-9_-]+', '_', packet)}_{os.path.basename(path)}")
        if os.path.exists(dest):
            dest = dest[:-5] + f"_{int(os.path.getmtime(path))}.json"
        os.replace(path, dest)
    for d in glob.glob(os.path.join(pdir, "judge_*")):
        shutil.rmtree(d, ignore_errors=True)


def pair(asset, a_tok="current", b_tok=None, judges=3, seed=None):
    m = _json(os.path.join(REPO, "build", "models", f"{asset}.manifest.json"))
    if m is None:
        return _out("fail", f"judge pair: {asset} has no build", f"build it first: lune run kit asset {asset}")
    kept = stored(asset)
    accepted = _json(os.path.join(REPO, "assets", "models", f"{asset}.accepted.json"))
    judged = _json(os.path.join(REPO, "assets", "models", f"{asset}.judge.json"))
    ctx = {"current": m.get("build_id"), "accepted": accepted, "judged": judged}
    a_tok = a_tok or "current"
    A, why = resolve(a_tok, kept, **ctx)
    if A is None:
        return _out("fail", f"judge pair: A — {why}", f"lune run kit asset {asset} (a full build keeps its views), "
                    f"then: lune run kit judge {asset} --pair current accepted|previous|i<N>")
    if b_tok is None:
        B, b_tok = None, None
        for tok in ("accepted", "previous"):
            cand, _ = resolve(tok, kept, **ctx)
            if cand is not None and cand["build"] != A["build"]:
                B, b_tok = cand, tok
                break
        why = f"no kept build to compare with ({_choices(kept)})"
    else:
        B, why = resolve(b_tok, kept, **ctx)
    if B is None:
        return _out("fail", f"judge pair: B — {why}", f"build another version first (lune run kit asset {asset}), or "
                    f"name one: lune run kit judge {asset} --pair {a_tok} <accepted|previous|i<N>|build id>")
    if A["build"] == B["build"]:
        return _out("fail", f"judge pair: A and B are the same build ({A['build']})", "name two different versions")
    ref_image, regions = _regions_spec(asset, m)
    overall_ref = m.get("reference_image") or ref_image
    items = _items(A, B, regions)
    by_item = {item: [str(q) for q in p[1].get("questions", [])] for item, kind, p in items if kind == "region"}
    round_id = datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    rng = random.Random(seed if seed is not None else secrets.randbits(64))
    base = {item: rng.randint(0, 1) for item, _, _ in items}  # (judge n sees it flipped from judge n-1: balanced)
    pdir = os.path.join(_jdir(asset), "pair")
    _retire(pdir)
    key = {"round": round_id, "asset": asset, "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "a": _ident(a_tok, A), "b": _ident(b_tok, B), "items": [i for i, _, _ in items], "judges": {}}
    count, size = 0, 0
    judges = max(1, int(judges))
    for n in range(1, judges + 1):
        first = {item: "a" if (base[item] + n) % 2 == 0 else "b" for item, _, _ in items}
        jdir = os.path.join(pdir, f"judge_{n}")
        os.makedirs(jdir, exist_ok=True)
        files = _compose(jdir, first, A, B, overall_ref, ref_image, items)
        answer = os.path.join(jdir, "answer.json")
        with open(os.path.join(jdir, "PROMPT.md"), "w", encoding="utf-8") as fh:
            fh.write(_prompt(asset, f"{round_id}-{n}", items, files, A, B, by_item, _rel(answer)))
        key["judges"][str(n)] = first
        for f in os.listdir(jdir):
            count += 1
            size += os.path.getsize(os.path.join(jdir, f))
    kdir = os.path.join(_jdir(asset), "pairkeys")
    os.makedirs(kdir, exist_ok=True)
    with open(os.path.join(kdir, f"{round_id}.json"), "w", encoding="utf-8") as fh:
        json.dump(key, fh, indent=1)
    for old in sorted(glob.glob(os.path.join(kdir, "*.json")))[:-50]:  # (the 50 newest rounds' keys are kept)
        os.remove(old)
    desc = lambda tok, x: f"{tok} (iteration {x.get('iteration')}, build {x['build']})"  # noqa: E731
    return _out(
        "pass",
        f"judge pair {asset}: A {desc(a_tok, A)} vs B {desc(b_tok, B)} — {len(items)} items "
        f"({', '.join(i for i, _, _ in items)}) for {judges} judge(s): {count} files, {size // 1024} KB in "
        f"{_rel(pdir)}/judge_<n>/ (sides shuffled per item and judge; the key is outside the packets)",
        f"hand each {_rel(pdir)}/judge_<n>/PROMPT.md to its OWN fresh judge (a subagent or session of the model the "
        "owner runs — never the builder, never shown another judge's answer); each writes its answer.json; then: "
        f"lune run kit judge {asset} --tally",
        round=round_id, packets=[_rel(os.path.join(pdir, f"judge_{n}")) for n in range(1, judges + 1)],
        items=[i for i, _, _ in items], files=count, kb=size // 1024,
    )


# ---------------------------------------------------------------------------------------------- the tally
def _pick(v):
    s = str(v if v is not None else "").strip().lower().lstrip("#")
    return {"tie": "same", "equal": "same", "neither": "same", "both": "same"}.get(s, s)


def _yn(v):
    s = str(v if v is not None else "").strip().lower()
    return True if s in ("yes", "y", "true") else False if s in ("no", "n", "false") else None


def _defect(v):
    """'no' -> (False, ''); 'yes: where' -> (True, where); anything else (a yes with no place) -> None"""
    s = str(v if v is not None else "").strip()
    if s.lower() in ("no", "n", "none"):
        return False, ""
    m = re.match(r"(?is)^yes\b[\s:,;.\-–—]*(.*)$", s)
    if m and len(m.group(1).strip()) >= 3:
        return True, m.group(1).strip()
    return None


def check_answer(ans, items):
    """one judge's answer against its packet's items -> problems (empty = usable)"""
    problems = []
    if not isinstance(ans, dict):
        return ["not a JSON object"]
    who = str(ans.get("judge") or "")
    if not who.strip() or "<model>" in who:
        problems.append("say who judged (judge: model@harness, fresh context)")
    got = ans.get("items") if isinstance(ans.get("items"), dict) else {}
    for it in items:
        x = got.get(it)
        if not isinstance(x, dict):
            problems.append(f"{it}: no answer")
            continue
        for aspect in ("shape", "surface"):
            if _pick(x.get(aspect)) not in PICKS:
                problems.append(f"{it}: {aspect} must be 1, 2 or same")
            why = str(x.get(f"{aspect}_why") or "").strip()
            if not why or why.lower().startswith("one line"):
                problems.append(f"{it}: {aspect}_why — one line on the difference you saw")
        for t in ("1", "2"):
            sc = (x.get("surface_checks") or {}).get(t) if isinstance(x.get("surface_checks"), dict) else None
            if any(_yn((sc or {}).get(k)) is None for k, _ in SURFACE):
                problems.append(f"{it}: surface_checks #{t} — roughness, wear, colour: each yes or no")
            d = (x.get("defects") or {}).get(t) if isinstance(x.get("defects"), dict) else None
            bad = [c for c, _, _ in DEFECTS if _defect((d or {}).get(c)) is None]
            if bad:
                problems.append(f"{it}: defects #{t} {', '.join(bad[:3])} — each 'no' or 'yes: <where>'")
    return problems


def tally_answers(entries):
    """entries: [(first, answer)] — first: {item: "a" | "b"}, the build that judge saw as #1; answer: a checked one.
    -> {"judges", "items": {item: {"shape" / "surface": {"a", "b", "same", "winner", "split", "agree", "why"},
    "surface_checks": {a/b: {check: {yes, no}}}, "defects": {a/b: {category: {yes, of, where}}}}},
    "shape" / "surface": {"a_wins", "b_wins", "same", "split"}, "defects": {a/b: [majority defects]}}"""
    order = []
    for first, _ in entries:
        order += [it for it in first if it not in order]
    items = {}
    for it in order:
        rec = {asp: {"a": 0, "b": 0, "same": 0, "why": []} for asp in ("shape", "surface")}
        rec["surface_checks"] = {s: {k: {"yes": 0, "no": 0} for k, _ in SURFACE} for s in ("a", "b")}
        rec["defects"] = {s: {c: {"yes": 0, "of": 0, "where": []} for c, _, _ in DEFECTS} for s in ("a", "b")}
        for first, ans in entries:
            x = (ans.get("items") or {}).get(it)
            if it not in first or not isinstance(x, dict):
                continue
            tile = {"1": first[it], "2": "b" if first[it] == "a" else "a"}
            for asp in ("shape", "surface"):
                p = _pick(x.get(asp))
                who = "same" if p == "same" else tile[p]
                rec[asp][who] += 1
                rec[asp]["why"].append(f"{who.upper() if who != 'same' else 'same'} (#1 was {tile['1'].upper()}): "
                                       f"{str(x.get(f'{asp}_why') or '').strip()}")
            for t in ("1", "2"):
                side = tile[t]
                for k, _ in SURFACE:
                    rec["surface_checks"][side][k]["yes" if _yn(x["surface_checks"][t][k]) else "no"] += 1
                for c, _, _ in DEFECTS:
                    yes, where = _defect(x["defects"][t][c])
                    cell = rec["defects"][side][c]
                    cell["of"] += 1
                    if yes:
                        cell["yes"] += 1
                        cell["where"].append(where)
        for asp in ("shape", "surface"):
            r = rec[asp]
            n = r["a"] + r["b"] + r["same"]
            r["winner"] = "a" if r["a"] > r["b"] else "b" if r["b"] > r["a"] else "same"
            r["split"] = r["a"] > 0 and r["b"] > 0  # judges picked OPPOSITE builds
            r["agree"] = round(max(r["a"], r["b"], r["same"]) / n, 2) if n else None
        items[it] = rec
    out = {"judges": len(entries), "items": items}
    for asp in ("shape", "surface"):
        out[asp] = {"a_wins": [i for i, r in items.items() if r[asp]["winner"] == "a"],
                    "b_wins": [i for i, r in items.items() if r[asp]["winner"] == "b"],
                    "same": [i for i, r in items.items() if r[asp]["winner"] == "same"],
                    "split": [i for i, r in items.items() if r[asp]["split"]]}
    out["defects"] = {s: [{"item": i, "category": c, "votes": f"{cell['yes']}/{cell['of']}", "where": cell["where"][:3]}
                          for i, r in items.items() for c, cell in r["defects"][s].items()
                          if cell["of"] and cell["yes"] * 2 > cell["of"]] for s in ("a", "b")}
    return out


def _expand(files):
    """answer files as given (relative to here, else to the project), a pattern expanded (lune passes it as typed)"""
    out = []
    for f in files:
        if not os.path.isabs(f) and not glob.glob(f):
            f = os.path.join(REPO, f)
        out += sorted(glob.glob(f)) if any(ch in f for ch in "*?[") else [f]
    return out


def tally(asset, files=()):
    pdir = os.path.join(_jdir(asset), "pair")
    paths = _expand(files) if files else sorted(glob.glob(os.path.join(pdir, "judge_*", "answer*.json")))
    if not paths:
        return _out("fail", f"judge tally: no answers for {asset} in {_rel(pdir)}/judge_*/answer.json",
                    f"make a packet (lune run kit judge {asset} --pair) and let the judges answer it first")
    entries, rejected, ref, judges = [], [], None, []
    for path in paths:
        ans = _json(path)
        name = os.path.relpath(path, REPO).replace("\\", "/") if os.path.isabs(path) else path
        if not isinstance(ans, dict):
            rejected.append(f"{name}: unreadable JSON")
            continue
        round_id, _, n = str(ans.get("packet") or "").rpartition("-")
        key = _json(os.path.join(_jdir(asset), "pairkeys", f"{round_id}.json")) if round_id else None
        if not key or n not in (key.get("judges") or {}):
            rejected.append(f"{name}: packet '{ans.get('packet')}' has no key (an answer to another asset's or a "
                            "pruned round)")
            continue
        problems = check_answer(ans, key["items"])
        if problems:
            rejected.append(f"{name}: {problems[0]}" + (f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""))
            continue
        first = dict(key["judges"][n])
        pair_ids = (key["a"]["build"], key["b"]["build"])
        if ref is None:
            ref = key
        elif pair_ids == (ref["b"]["build"], ref["a"]["build"]):  # (a round that named them the other way round)
            first = {it: "b" if v == "a" else "a" for it, v in first.items()}
        elif pair_ids != (ref["a"]["build"], ref["b"]["build"]):
            rejected.append(f"{name}: about builds {pair_ids[0]} / {pair_ids[1]}, not the ones the first answer judged")
            continue
        entries.append((first, ans))
        judges.append(str(ans.get("judge")))
    if not entries:
        return _out("fail", f"judge tally: no usable answer — {rejected[0]}",
                    "the judge fixes its answer.json (every item: shape, surface, both why lines, surface_checks and "
                    "all nine defects for #1 and #2); then: " + "; ".join(rejected[1:3]), rejected=rejected)
    res = tally_answers(entries)
    A, B = ref["a"], ref["b"]
    who = {"a": f"A = {A['token']} (iteration {A.get('iteration')}, build {A['build']})",
           "b": f"B = {B['token']} (iteration {B.get('iteration')}, build {B['build']})"}
    report = {"asset": asset, "round": ref["round"], "a": A, "b": B, "judges": judges, "rejected": rejected,
              "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), **res}
    os.makedirs(_jdir(asset), exist_ok=True)
    with open(os.path.join(_jdir(asset), "pairwise.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    # the verdict keeps the latest pairwise result (kit judge --record keeps it too)
    vpath = os.path.join(REPO, "assets", "models", f"{asset}.judge.json")
    verdict = _json(vpath) if os.path.isfile(vpath) else {"asset": asset}
    if isinstance(verdict, dict):
        verdict["pairwise"] = {
            "round": ref["round"], "at": report["at"], "judges": len(entries),
            "a": {k: A.get(k) for k in ("token", "build", "iteration")},
            "b": {k: B.get(k) for k in ("token", "build", "iteration")},
            "shape": {"a": res["shape"]["a_wins"], "b": res["shape"]["b_wins"], "same": res["shape"]["same"]},
            "surface": {"a": res["surface"]["a_wins"], "b": res["surface"]["b_wins"], "same": res["surface"]["same"]},
            "split": sorted(set(res["shape"]["split"]) | set(res["surface"]["split"])),
            "defects": {"a": len(res["defects"]["a"]), "b": len(res["defects"]["b"])},
        }
        os.makedirs(os.path.dirname(vpath), exist_ok=True)
        with open(vpath, "w", encoding="utf-8") as fh:
            json.dump(verdict, fh, indent=2)

    def counts(asp):
        r = res[asp]
        b = f"B wins {len(r['b_wins'])}" + (f" ({', '.join(r['b_wins'][:4])})" if r["b_wins"] else "")
        return f"{asp}: A wins {len(r['a_wins'])}, {b}, same {len(r['same'])}"

    split = [f"{i} ({asp})" for asp in ("shape", "surface") for i in res[asp]["split"]]
    summary = (f"judge tally {asset}: {who['a']} vs {who['b']}, {len(entries)} judge(s) — {counts('shape')}; "
               f"{counts('surface')}" + (f"; judges disagree on {', '.join(split[:4])}" if split else "")
               + (f"; {len(rejected)} answer(s) rejected" if rejected else ""))
    steps = []
    b_any = [f"{i} ({asp})" for asp in ("shape", "surface") for i in res[asp]["b_wins"]]
    if b_any:
        steps.append(f"B is better at {', '.join(b_any[:5])} — read why in "
                     f"{_rel(os.path.join(_jdir(asset), 'pairwise.json'))} and bring that back before keeping A")
    if split:
        steps.append(f"the judges split on {', '.join(split[:3])}: look at those images yourself, or add a judge")
    if res["defects"]["a"]:
        d = res["defects"]["a"][0]
        steps.append(f"{len(res['defects']['a'])} defect(s) a majority saw on A, first: {d['item']} {d['category']} "
                     f"at {d['where'][0] if d['where'] else '?'}")
    if rejected:
        steps.append(f"rejected: {rejected[0]}")
    if not b_any and not split:
        steps.append("A is as good or better everywhere the judges looked — if the OWNER approves it: "
                     f"lune run kit accept {asset}")
    if len(entries) < 3:
        steps.append("a panel of 3 judges is steadier than " + str(len(entries)))
    return _out("pass", summary, "; ".join(steps), pairwise=_rel(os.path.join(_jdir(asset), "pairwise.json")),
                shape=res["shape"], surface=res["surface"])


def main(argv):
    if len(argv) >= 2 and argv[0] == "pair":
        rest, judges, seed = [], 3, None
        i = 2
        while i < len(argv):
            if argv[i] == "--judges" and i + 1 < len(argv):
                judges, i = int(argv[i + 1]), i + 2
            elif argv[i] == "--seed" and i + 1 < len(argv):
                seed, i = int(argv[i + 1]), i + 2
            else:
                rest.append(argv[i])
                i += 1
        if len(rest) == 1:  # (one version: the current build against it)
            rest = ["current", rest[0]]
        return pair(argv[1], rest[0] if rest else "current", rest[1] if len(rest) > 1 else None, judges, seed)
    if len(argv) >= 2 and argv[0] == "tally":
        return tally(argv[1], argv[2:])
    return _out("fail", "judge_pair: usage",
                "judge_pair.py pair <asset> [[A] B] [--judges N] | tally <asset> [answers.json ...]")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
