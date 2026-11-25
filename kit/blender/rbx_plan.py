"""rbx_plan.py — the ORDER OF WORK, read from the owner's brief and the references. Pure python (no bpy): unit-tested.

Why: hero builds spent their effort on hidden mechanisms while the features players SEE stayed weak, detail work
started before the outline was right in every view, and small ornaments were modelled from ~145 px of picture with
nobody asking for a close-up. Professional order: blockout (silhouette, primary forms) -> secondary forms -> detail.

  brief      assets/models/<name>.brief.md read into facts later tools use: how players see it (view), what they
             notice first (hero features, ranked, each with its ROUTE: how it gets made), the quality bar, the
             style, the moving parts gameplay needs. Read forgivingly: `- question: answer` lines, a numbered list
             under `- hero features:`, fields split by `|` (or ` — `), help in `  (...)` left over is ignored.
  routes     a hero feature with no route, or a sculpted / organic one built as `code` (boxes look like a
             blockout there) is named.
  coverage   pixels per mm for each hero feature in each picture that shows it (a traced view's own scale, or a
             box in a close-up beside the feature's size): under 2 px/mm at best, nobody can model it from that.
  stage      while a traced view's silhouette is below its bar the build is a BLOCKOUT: the outline is the next
             step, and detail-level problems wait (deferred) instead of piling up.
"""

import glob
import json
import os
import re

ROUTES = ("code", "sculpt", "generated", "relief", "projected", "procedural")
# a whole field that names a route another way (a field, never a word inside a description)
ROUTE_ALIASES = {"kit gen": "generated", "gen": "generated", "generate": "generated", "trellis": "generated",
                 "decal": "projected", "projection": "projected", "texture": "projected", "scan": "procedural",
                 "scanned": "procedural", "material": "procedural", "kit vision relief": "relief",
                 "normals": "relief", "modelled": "code", "modeled": "code", "shapes": "code", "geometry": "code",
                 "sculpted": "sculpt", "sculpting": "sculpt", "a.sculpt": "sculpt", "clay": "sculpt", "sdf": "sculpt"}
# words that mark a form as sculpted / organic: built from boxes it reads as a blockout
ORGANIC = re.compile(r"\b(sculpt\w*|organic|ornate|ornament\w*|figur\w*|filigree|floral|flower\w*|foliage|leaf|leaves|"
                     r"vine\w*|creature\w*|animal\w*|skull\w*|feather\w*|fur|hair|cloth|fabric|statue\w*|bust)\b",
                     re.IGNORECASE)
PICTURE = re.compile(r"([\w./\\-]+\.(?:png|jpe?g|webp|bmp|tga|tiff?))(?:\s*[@:]?\s*[(\[]?\s*(\d+(?:\.\d+)?)\s*,\s*"
                     r"(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*[)\]]?)?", re.IGNORECASE)
SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(mm|cm)\b", re.IGNORECASE)
MIN_PX_PER_MM = 2.0  # under this at best, a hero feature cannot be read off any picture: ask for a close-up
# failing checks that are DETAIL work: while the silhouette is below its bar they are deferred, not piled up
DETAIL_CHECKS = frozenset({
    "part_review", "texel_density", "texel_bar", "colour_match", "palette", "material_values", "detail", "wood_grooves",
    "tiny_cuts", "marking_placement", "fastener_support", "plate_support", "slivers", "attach_gaps",
    "spec_undocumented", "see_through", "quality",
})
VIEW_OF_SUFFIX = {"side": "side", "top": "top", "bottom": "top", "front": "front", "frontview": "front",
                  "back": "back", "backview": "back"}  # (the rule of kit/refs/views.py load_views)

QUESTIONS = ("what", "end_goal", "quality", "quality_bar", "style", "view", "function", "moving_parts", "extras",
             "references", "ownership", "hero_features")  # (kit/templates/asset.brief.md)
OPTIONAL_QUESTIONS = ("parts_plan", "draft", "reference_models")  # (the template's, with no <answer>: kit/tools/plan.py reads them)
_ITEM = re.compile(r"^[-*]\s+([A-Za-z][A-Za-z ]{0,30}?)\s*:(.*)$")
_SUB = re.compile(r"^\s*(?:\d+\s*[.)]|[-*])\s+(.*)$")


def _check(name, ok, value, limit, fix, severity="error"):
    """the shape of every kit check (rbx_critic._check), without Blender"""
    return {"name": name, "ok": bool(ok), "severity": severity, "value": value, "limit": limit,
            "fix": "" if ok else fix}


def _key(text):
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _norm_path(p):
    return os.path.normcase(os.path.normpath(str(p))).replace("\\", "/")


# ==================================================================== the brief
def brief_path(name, script_path=None, root=None):
    """<name>.brief.md beside the build script (assets/models/ when there is none)"""
    folder = (os.path.dirname(os.path.abspath(script_path)) if script_path
              else os.path.join(root or os.getcwd(), "assets", "models"))
    return os.path.join(folder, f"{name}.brief.md")


def unanswered_count(text):
    """the `<answer>` placeholders left — the intro's own mention of it (in backticks) is not a question"""
    return str(text).replace("`<answer>`", "").count("<answer>")


def _strip_help(text):
    """'answer  (help...' -> ('answer', open parentheses left): help is two spaces then a parenthesis"""
    s = text.strip()
    if s.startswith("("):
        return "", max(0, s.count("(") - s.count(")"))
    m = re.search(r"\s{2,}\(", text)
    if not m:
        return s, 0
    rest = text[m.start():]
    return text[:m.start()].strip(), max(0, rest.count("(") - rest.count(")"))


def _items(text):
    """-> {question key: {"text": answer, "list": [numbered lines under it]}} in file order"""
    items, cur, depth, gap = {}, None, 0, False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            gap = True
            continue
        after_gap, gap = gap, False
        if line.lstrip().startswith("#"):
            cur, depth = None, 0
            continue
        m = _ITEM.match(line)
        key = m.group(1).strip().lower().replace(" ", "_") if m else None
        # (right under `hero features`, `- wolf head: relief` is a feature, not a question the brief never asked)
        in_hero = cur is not None and cur is items.get("hero_features") and not after_gap
        if m and not raw[:1].isspace() and not (in_hero and key not in QUESTIONS + OPTIONAL_QUESTIONS):
            answer, depth = _strip_help(m.group(2))
            cur = items.setdefault(key, {"text": "", "list": []})
            cur["text"] = answer
            continue
        if cur is None:
            continue
        if depth:  # help running on from the question's line
            depth = max(0, depth + line.count("(") - line.count(")"))
            continue
        sm = _SUB.match(line)
        if sm:  # a numbered / bulleted line under the question (indented or not)
            answer, depth = _strip_help(sm.group(1))
            if answer:
                cur["list"].append(answer)
        elif raw[:1].isspace():
            answer, depth = _strip_help(line)
            if answer:
                cur["text"] = (cur["text"] + " " + answer).strip()
    return items


def parse_route(text):
    """a field that IS a route ('relief', 'route: kit gen') -> the route, else None"""
    s = re.sub(r"^route\s*[:=]\s*", "", str(text).strip().lower()).strip(" .`'\"()[]")
    if s in ROUTES:
        return s
    return ROUTE_ALIASES.get(s)


def parse_feature(text, rank):
    """one hero feature line -> {rank, name, route, what, picture, box, size_mm, organic}. Forgiving:
    'wolf head | relief | the sculpted wolf | refs/side.png 410,120,470,170 | 30 mm', 'wolf head (relief)',
    'wolf head: relief — the pommel's wolf @ refs/side.png 410,120,470,170, 30 mm'"""
    s = re.sub(r"^\s*(?:\d+\s*[.)]|[-*])\s+", "", str(text).strip())
    picture, box = None, None
    pm = PICTURE.search(s)
    if pm:
        picture = pm.group(1).replace("\\", "/")
        if pm.group(2):
            box = [float(pm.group(k)) for k in range(2, 6)]
            box = [int(v) if v.is_integer() else v for v in box]
        s = (s[:pm.start()] + s[pm.end():]).replace("@", " ")
    if "|" in s:
        fields = s.split("|")
    else:
        fields = re.split(r"\s+[—–-]\s+|;", s)
        if ":" in fields[0]:
            head, tail = fields[0].split(":", 1)
            fields = [head, tail, *fields[1:]]
    fields = [f.strip(" ,.") for f in fields]
    fields = [f for f in fields if f]
    # its size: a field that is only a size ('30 mm') wins over a size inside a description
    size_mm = None
    order = list(range(1, len(fields)))
    idx = next((i for i in order if SIZE.fullmatch(fields[i])), None)
    if idx is None:  # inside a description, else beside the name ('wolf head (relief) 30 mm')
        idx = next((i for i in order + [0] if fields and SIZE.search(fields[i])), None)
    if idx is not None:
        sm = SIZE.search(fields[idx])
        size_mm = float(sm.group(1)) * (10.0 if sm.group(2).lower() == "cm" else 1.0)
        fields[idx] = (fields[idx][:sm.start()] + fields[idx][sm.end():]).strip(" ,.")
        fields = [f for f in fields if f]
    name = fields[0] if fields else f"feature {rank}"
    inline = re.search(r"\(([^)]*)\)", name)  # 'wolf head (relief)'
    rest = fields[1:] + ([inline.group(1)] if inline else [])
    name = re.sub(r"\s*\([^)]*\)", "", name).strip() or name
    route, what = None, []
    explicit = re.search(r"\broute\s*[:=]\s*([a-z ]+)", " ".join(rest), re.IGNORECASE)
    if explicit:
        route = parse_route(explicit.group(1).split(",")[0])
    for f in rest:
        r = parse_route(f)
        if r and route is None:
            route = r
        elif not r and not re.match(r"^route\s*[:=]", f, re.IGNORECASE):
            what.append(f)
    if route is None:  # a route word anywhere after the name ('the wolf, generated from the picture')
        words = re.findall(r"\b(" + "|".join(ROUTES) + r")\b", " ".join(rest).lower())
        route = words[0] if words else None
    what_text = "; ".join(what)
    organic = ORGANIC.search(f"{name} {what_text}")
    return {"rank": rank, "name": name, "route": route, "what": what_text, "picture": picture, "box": box,
            "size_mm": size_mm, "organic": organic.group(1).lower() if organic else None}


def _modes(text):
    t = text.lower()
    out = []
    for mode, pat in (("first person", r"first[- ]person|\bfps\b|1st[- ]person"),
                      ("third person", r"third[- ]person|3rd[- ]person|over[- ]the[- ]shoulder"),
                      ("world prop", r"world|\bprop\b|on the ground|in the level|scenery")):
        if re.search(pat, t):
            out.append(mode)
    return out


def parse_brief(text):
    """the brief's text -> the design facts (answers by question, plus the new questions read into data)"""
    items = _items(text)
    unanswered = [k for k, v in items.items() if "<answer>" in v["text"] or any("<answer>" in x for x in v["list"])]
    answers = {k: v["text"] for k, v in items.items() if "<answer>" not in v["text"]}
    out = {"answered": unanswered_count(text) == 0, "unanswered": unanswered, "answers": answers}
    view = answers.get("view")
    if view:
        sides = sorted({w for w in re.findall(r"\b(front|back|left|right|top|bottom|underside)\b", view.lower())})
        size = next((c.strip() for c in re.split(r"[;,]", view)
                     if re.search(r"screen|pixel|\bpx\b|%|width|hand|fist|thumb", c, re.IGNORECASE)), None)
        out["view"] = {"text": view, "modes": _modes(view), "on_screen": size, "sides": sides}
    style = (answers.get("style") or "").lower()
    if style:
        out["style"] = ("stylised" if re.search(r"styli[sz]ed|cartoon|toon|low[- ]poly|hand[- ]painted", style)
                        else "realistic PBR" if re.search(r"realis|pbr|photo", style) else answers["style"])
    moving = answers.get("moving_parts")
    if moving is not None and "moving_parts" not in unanswered:
        none = re.fullmatch(r"\s*(none|no|nothing|static|n/?a|-)\s*\.?\s*", moving.lower())
        out["moving_parts"] = [] if none or not moving.strip() else [
            p.strip(" .") for p in re.split(r"[;,]", moving) if p.strip(" .")]
    bar = answers.get("quality_bar")
    if bar:
        links = re.findall(r"https?://\S+", bar) + [m.group(1) for m in PICTURE.finditer(bar)]
        out["quality_bar"] = [x.rstrip(",;") for x in links] or [bar]
    hero = items.get("hero_features")
    if hero is not None:
        lines = [x for x in hero["list"] if "<answer>" not in x]
        if not lines and hero["text"] and "<answer>" not in hero["text"]:
            lines = [x for x in re.split(r";|\s+\d+[.)]\s+", hero["text"]) if x.strip()]
        out["hero_features"] = [parse_feature(x, i + 1) for i, x in enumerate(lines)]
    return out


def load_brief(path, root=None):
    """the parsed brief, or None when there is none"""
    if not path or not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        brief = parse_brief(fh.read())
    brief["path"] = (os.path.relpath(path, root) if root else path).replace("\\", "/")
    return brief


# ==================================================================== routes
def route_problems(features):
    """-> [(feature name, what is wrong)] for features with no route, and sculpted / organic ones built as code"""
    out = []
    for f in features:
        if not f.get("route"):
            out.append((f["name"], "no route"))
        elif f["route"] == "code" and f.get("organic"):
            out.append((f["name"], f"route code, but it is {f['organic']}"))
    return out


def routes_check(brief, tier):
    """hero / aaa only: every hero feature has a route, and no sculpted / organic feature is built from boxes.
    None when there is nothing to judge (no brief, or its hero features are still unanswered: the brief check)"""
    if tier not in ("hero", "aaa") or not brief or "hero_features" in brief.get("unanswered", ()):
        return None
    feats = brief.get("hero_features") or []
    if not feats:
        return _check("routes", False, "the brief names no hero features", "every hero feature has a route",
                      "ask the owner what players notice first (most important first) and write it in the brief's "
                      "`hero features` (copy the question from kit/templates/asset.brief.md), each with its route: "
                      "code | sculpt | generated | relief | projected | procedural", "warn")
    bad = route_problems(feats)
    said = [f"{n}: {why}" for n, why in bad]
    fix = []
    if any(why.startswith("route code") for _, why in bad):
        fix.append("; ".join(f"{n}: {why}" for n, why in bad if why.startswith("route code"))
                   + " — boxes read as a blockout there: sculpt it (a.sculpt), make it generated (kit gen) or relief "
                   "(kit vision relief)")
    if any(why == "no route" for _, why in bad):
        fix.append(", ".join(n for n, why in bad if why == "no route") + ": no route — write how each gets made in "
                   "the brief's hero features (code | sculpt | generated | relief | projected | procedural)")
    return _check("routes", not bad, said[:6] or f"{len(feats)} hero feature(s), each with its route",
                  "every hero feature has a route; sculpted / organic ones are not code", "; ".join(fix), "warn")


def routes_table(features, cov=None):
    """the hero features as short table rows for the verdict: rank. name | route | picture | best px/mm"""
    best = {_key(f["name"]): f for f in (cov or {}).get("features", [])}
    rows = []
    for f in features:
        pic = "-"
        if f.get("picture"):
            pic = os.path.basename(f["picture"]) + (f" {','.join(str(v) for v in f['box'])}" if f.get("box") else "")
        b = best.get(_key(f["name"]))
        ppm = f"{b['best_px_per_mm']:.1f} px/mm" if b and b.get("best_px_per_mm") is not None else "px/mm ?"
        rows.append(f"{f['rank']}. {f['name']} | {f.get('route') or 'NO ROUTE'} | {pic} | {ppm}")
    return rows


# ==================================================================== coverage
def load_traces(asset, root, registered=None):
    """{view: trace} — assets/models/<asset>_<view>.trace.json, and the traces a build registered (a.trace_match:
    {view: path}), which win: they are what the build is measured against"""
    out = {}
    for path in sorted(glob.glob(os.path.join(root, "assets", "models", f"{asset}_*.trace.json"))):
        suffix = os.path.basename(path)[len(asset) + 1:-len(".trace.json")]
        try:
            with open(path, encoding="utf-8") as fh:
                t = json.load(fh)
        except (OSError, ValueError):
            continue
        view = t.get("view") or VIEW_OF_SUFFIX.get(suffix)
        if view and view not in out:
            out[view] = t
    for view, path in (registered or {}).items():
        p = path if os.path.isabs(path) else os.path.join(root, path)
        if str(p).endswith(".trace.json") and os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                out[view] = json.load(fh)
    return out


def picture_scales(traces, views=None, length_mm=None):
    """{picture: {"view", "px_per_mm"}} — a traced picture's own scale: its object length in pixels over the view's
    millimetres per design unit (refs/<asset>.views.json; the side / top views without it: the spec's length_mm)"""
    out = {}
    for view, t in traces.items():
        unit = (((views or {}).get("views") or {}).get(view) or {}).get("mm_per_unit")
        if not unit and view in ("side", "top") and length_mm:
            unit = float(length_mm)
        px = t.get("pixels_per_length") or (t.get("frame") or {}).get("length_px")
        src = t.get("source")
        if unit and px and src:
            out[_norm_path(src)] = {"picture": src, "view": view, "px_per_mm": float(px) / float(unit)}
    return out


def _bounds(poly):
    us, hs = [p[0] for p in poly], [p[1] for p in poly]
    return min(us), min(hs), max(us), max(hs)


def _find_scale(picture, scales):
    """the traced picture a brief's picture names (its path, or its file name when only one matches)"""
    hit = scales.get(_norm_path(picture))
    if hit:
        return hit
    same = [s for k, s in scales.items() if os.path.basename(k) == os.path.basename(_norm_path(picture))]
    return same[0] if len(same) == 1 else None


def coverage(features, traces=None, views=None, length_mm=None, min_px_per_mm=MIN_PX_PER_MM):
    """pixels per mm for each feature in each picture that shows it.
    features: the brief's hero features; traces: {view: trace} (their pictures, scales and traced parts);
    views: refs/<asset>.views.json (mm per unit per view, each traced part's size in mm).
    -> {"rows": [{feature, hero, picture, view, px_per_mm, feature_px, how}], "features": [{name, hero, rank,
       best_px_per_mm, best_picture, low}], "low": [the hero features under min_px_per_mm at best], "min_px_per_mm"}"""
    traces = traces or {}
    scales = picture_scales(traces, views, length_mm)
    vparts = (views or {}).get("parts") or {}
    rows, by_feature = [], {}

    def part_size_mm(name):
        """a traced part's largest size in mm, in any view (views.json), else None"""
        sizes = [max(v["size_mm"]) for k, pv in vparts.items() if _key(k) == _key(name) for v in pv.values()
                 if v.get("size_mm")]
        return max(sizes) if sizes else None

    def add(name, hero, rank, row):
        rows.append({"feature": name, "hero": hero, **row})
        by_feature.setdefault(_key(name), {"name": name, "hero": hero, "rank": rank, "rows": []})["rows"].append(row)

    hero_keys = set()
    for f in features or []:
        hero_keys.add(_key(f["name"]))
        size = f.get("size_mm") or part_size_mm(f["name"])
        if f.get("picture"):
            sc = _find_scale(f["picture"], scales)
            bw = bh = None
            if f.get("box"):
                x0, y0, x1, y1 = f["box"]
                bw, bh = abs(x1 - x0), abs(y1 - y0)
            if sc:  # a traced picture: its own scale
                fpx = max(bw, bh) if bw is not None else (size * sc["px_per_mm"] if size else None)
                add(f["name"], True, f["rank"], {"picture": f["picture"], "view": sc["view"],
                                                 "px_per_mm": round(sc["px_per_mm"], 2),
                                                 "feature_px": None if fpx is None else round(fpx),
                                                 "how": f"the traced {sc['view']} view's scale"})
            elif bw is not None and size:  # a close-up: the box against the feature's size
                ppm = max(bw, bh) / size
                add(f["name"], True, f["rank"], {"picture": f["picture"], "view": None, "px_per_mm": round(ppm, 2),
                                                 "feature_px": round(max(bw, bh)),
                                                 "how": f"its box over its size ({size:g} mm)"})
            else:
                add(f["name"], True, f["rank"], {
                    "picture": f["picture"], "view": None, "px_per_mm": None,
                    "feature_px": None if bw is None else round(max(bw, bh)),
                    "how": "unmeasured: give its box in the picture and its size in mm (`30 mm`) in the brief"
                    if bw is None else "unmeasured: give its size in mm (`30 mm`) in the brief"})
        else:
            by_feature.setdefault(_key(f["name"]), {"name": f["name"], "hero": True, "rank": f["rank"], "rows": []})
    # every traced part, in every view whose picture has a scale (a hero feature of the same name gains the picture)
    for view, t in traces.items():
        src = t.get("source")
        sc = scales.get(_norm_path(src)) if src else None
        for pname, poly in (t.get("parts") or {}).items():
            if not poly:
                continue
            u0, h0, u1, h1 = _bounds(poly)
            ppl = t.get("pixels_per_length") or (t.get("frame") or {}).get("length_px")
            fpx = max(u1 - u0, h1 - h0) * float(ppl) if ppl else None
            hero = _key(pname) in hero_keys
            name = next((f["name"] for f in features or [] if _key(f["name"]) == _key(pname)), pname)
            rank = next((f["rank"] for f in features or [] if _key(f["name"]) == _key(pname)), None)
            add(name, hero, rank, {"picture": src, "view": view,
                                   "px_per_mm": round(sc["px_per_mm"], 2) if sc else None,
                                   "feature_px": None if fpx is None else round(fpx),
                                   "how": f"traced part ({view} view)" if sc else
                                   f"traced part ({view} view): no mm scale — run lune run kit refs views"})
    feats, low = [], []
    for k, info in by_feature.items():
        measured = [r for r in info["rows"] if r.get("px_per_mm") is not None]
        best = max(measured, key=lambda r: r["px_per_mm"]) if measured else None
        item = {"name": info["name"], "hero": info["hero"], "rank": info["rank"],
                "best_px_per_mm": best["px_per_mm"] if best else None,
                "best_picture": best["picture"] if best else None,
                "low": bool(info["hero"] and best and best["px_per_mm"] < min_px_per_mm)}
        feats.append(item)
        if item["low"]:
            low.append(item)
    feats.sort(key=lambda f: (f["rank"] is None, f["rank"] or 0, f["name"]))
    low.sort(key=lambda f: f["rank"] or 0)
    return {"rows": rows, "features": feats, "low": low, "min_px_per_mm": min_px_per_mm}


def low_text(item):
    """'wolf head: 1.4 px/mm at best (side_profile.png)'"""
    return f"{item['name']}: {item['best_px_per_mm']:.1f} px/mm at best ({os.path.basename(item['best_picture'])})"


def coverage_check(cov, tier, asset="<asset>"):
    """a hero feature under 2 px/mm in its best picture: a warning on a prop, an error on hero / aaa.
    None when no hero feature could be measured (nothing to judge)"""
    if not cov or not any(f["hero"] and f["best_px_per_mm"] is not None for f in cov["features"]):
        return None
    low = cov["low"]
    said = [low_text(f) for f in low]
    return _check(
        "coverage", not low, said[:6] or "every hero feature has a picture that shows it at "
        f">= {cov['min_px_per_mm']:g} px/mm", f">= {cov['min_px_per_mm']:g} px/mm in its best picture",
        "; ".join(said[:4]) + " — ask the owner for a close-up picture, or make a clean view (low trust) — but FIRST "
        "find sharper ones yourself: lune run kit refs find \"<the real object> <the part>\" (and refs patent, "
        "cross-sections, field strips; per part, per side), the owner only for what they alone have (a game's "
        "design); then add "
        f"it to the feature's line in the brief (`<picture> x0,y0,x1,y1`, its size in mm). Table: lune run kit refs "
        f"coverage {asset}", "error" if tier in ("hero", "aaa") else "warn")


def coverage_table(cov):
    """the coverage as printable rows (kit refs coverage)"""
    rows = [f"{'feature':<26} {'picture':<30} {'px/mm':>7} {'feat px':>8}  how"]
    for r in sorted(cov["rows"], key=lambda r: (not r["hero"], r["feature"])):
        ppm = "?" if r["px_per_mm"] is None else f"{r['px_per_mm']:.2f}"
        fpx = "?" if r["feature_px"] is None else str(r["feature_px"])
        star = " *" if r["hero"] else ""
        rows.append(f"{(r['feature'] + star)[:26]:<26} {os.path.basename(str(r['picture']))[:30]:<30} {ppm:>7} "
                    f"{fpx:>8}  {r['how']}")
    for f in cov["features"]:
        if f["hero"] and not any(_key(r["feature"]) == _key(f["name"]) for r in cov["rows"]):
            rows.append(f"{(f['name'] + ' *')[:26]:<26} {'-':<30} {'?':>7} {'?':>8}  no picture named: add "
                        "`<picture> x0,y0,x1,y1` and its size in mm to its line in the brief")
    return rows


# ==================================================================== the stage of work
def stage_of(references, ref_options, gate):
    """where the work is: "blockout" while any registered trace view (a.trace_match) is below its bar, "detail"
    once every one reaches it, "unmeasured" with none registered (or none that could be measured: "registered"
    names those). Under an enforced gate an unmeasured build FAILS (apply_gate).
    references: facts["references"] ([{"view", "iou", ...}]); ref_options: {view: {"bar"}}; gate: is it enforced"""
    by_view = {r.get("view"): r for r in references or []}
    views = []
    for view, opts in (ref_options or {}).items():
        r = by_view.get(view)
        if r is None or r.get("iou") is None:
            continue
        bar = float(opts.get("bar", 0.9))
        views.append({"view": view, "iou": float(r["iou"]), "bar": bar, "worst": r.get("worst"),
                      "diff": r.get("diff")})
    below = [v for v in views if v["iou"] < v["bar"]]
    stage = "unmeasured" if not views else "blockout" if below else "detail"
    out = {"stage": stage, "gate": bool(gate), "views": views, "below": below}
    if stage == "unmeasured":
        out["registered"] = sorted(ref_options or {})
        out["note"] = ("no traced view registered (a.trace_match): the silhouette is not measured"
                       + (" - under the gate that fails the build" if gate else ", detail is not held back"))
    return out


BLOCKOUT_DRIFT = 0.05  # a size that moved this share from the approved blockout's is said by the build


def approved_stage(locks_path, asset, step):
    """the id of the artefact the OWNER approved for a 3D stage (board/locks.json stages: kit approve ... --stage),
    read by kit/lib/locks.luau's own rule (Locks.isOwner) -> the id, or None"""
    try:
        with open(locks_path, encoding="utf-8") as fh:
            rec = ((((json.load(fh) or {}).get("stages") or {}).get("3d") or {}).get(asset) or {}).get(step)
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(rec, dict):
        return None
    who = rec.get("who")
    if who is not None and (not isinstance(who, str) or who.lower() != "owner"):
        return None
    by = rec.get("by") if rec.get("by") is not None else who
    if not (isinstance(by, str) and by.strip().lower().startswith("owner")):
        return None
    return rec.get("id")


def blockout_drift(path, size, asset="<asset>", approved=None):
    """the model's size (studs: across, up, along) against the blockout the owner APPROVED (<asset>.blockout.json,
    written by kit blockout: "size"; `approved` = the id his yes is recorded for) -> a check, failing as a WARNING
    when a side moved more than BLOCKOUT_DRIFT from it: he said yes to those proportions. None when the blockout on
    disk is not the one he approved (drawn again and not yet shown), or there is none, or no size to compare."""
    try:
        with open(path, encoding="utf-8") as fh:
            kept = json.load(fh) or {}
        old = kept.get("size")
    except (OSError, ValueError, AttributeError):
        return None
    if not approved or kept.get("id") != approved:
        return None
    if not (isinstance(old, list) and len(old) == 3 and size is not None and len(size) == 3):
        return None
    moved = []
    for axis, a, b in zip(("width", "height", "length"), old, size):
        try:
            a, b = float(a), float(b)
        except (TypeError, ValueError):
            return None
        if a > 0 and abs(b - a) / a > BLOCKOUT_DRIFT:
            moved.append(f"{axis} {a:.3g} -> {b:.3g} studs ({(b - a) / a:+.0%})")
    return _check("blockout_drift", not moved, moved or "the size of the approved blockout",
                  f"every side within {BLOCKOUT_DRIFT:.0%} of the blockout the owner approved",
                  "the proportions moved since the owner approved the blockout: " + "; ".join(moved)
                  + f" — meant: lune run kit blockout {asset} --again and show them; not meant: undo it", "warn")


def below_text(stage):
    """'side IoU 0.81 < 0.9, top IoU 0.85 < 0.9'"""
    return ", ".join(f"{v['view']} IoU {v['iou']:.2f} < {v['bar']:g}" for v in stage["below"])


def defer(design):
    """-> (design without the failing detail-level checks, [their names]) — held back while the outline is wrong"""
    kept, deferred = [], []
    for c in design:
        if not c["ok"] and c["name"] in DETAIL_CHECKS:
            if c["name"] not in deferred:
                deferred.append(c["name"])
        else:
            kept.append(c)
    return kept, deferred


def gate_check(stage, deferred=()):
    """the one error a blockout build fails with: the silhouette first"""
    where = "; ".join(
        f"{v['view']}: most off at {v['worst']}" + (f", diff {v['diff']}" if v.get("diff") else "")
        for v in stage["below"] if v.get("worst"))
    fix = (f"silhouette first: {below_text(stage)} — fix the outline before detail work"
           + (f" ({where}; red = the reference has shape there, blue = the model sticks out)" if where else "")
           + (f"; held back until then: {', '.join(deferred)}" if deferred else "")
           + " — let the references set the proportions: make the off ones a.param() and run lune run kit fit "
             "<asset> --write (never nudged by hand build after build); a sculpted part that will not match: generate "
             "it (kit gen views / kit gen, the draft stage of lune run kit plan <asset>)")
    return _check("stage", False, f"blockout: {below_text(stage)}", "every traced view at its bar before detail work",
                  fix, "error")


def unmeasured_check(stage):
    """the one error a build under the gate fails with when its outline is measured against NOTHING (the owner,
    2026-11-12: "Yes, make it fail"). The gate used to bite only while a registered view was below its bar: a build
    that registered none went straight on to detail. The Gjallarhorn's never registered one, and its lower rear
    stayed misread for 7 rounds - the stock's thumbhole built as a trigger guard with a pistol grip behind it; the
    same check, registered later against its chart's side view, failed that frame at once (IoU 0.878, windows down
    to 0.36, up to 97 mm off)."""
    registered = stage.get("registered") or []
    said = ("no traced view registered" if not registered
            else f"registered ({', '.join(registered)}) but none could be measured")
    fix = ("silhouette first, and this build's is measured against nothing: " + said + ". Trace the reference's "
           "side view - lune run kit trace <picture> --name <asset>_side --front left|right (--cutout for a pale "
           "object or a photo: a plain trace takes ivory for backdrop) - and LOOK at its preview: a hero build matches "
           "assets/models/<asset>_<view>.trace.json by itself, any other trace is named with a.trace_match(\"<trace>\", "
           "view=\"side\"); one per view the references show (side, top, front). An original with no picture: its "
           "model sheet's side view (lune run kit sheet <asset>) is the reference. Its other findings stand: nothing "
           "is held back")
    return _check("stage", False, f"unmeasured: {said}", "at least one traced view registered and measured before "
                  "detail work", fix, "error")


def apply_gate(design, stage):
    """a blockout under an enforced gate -> (design, the gate's check): the failing reference_<view> checks it
    carries are folded into it (never reported twice), detail-level failures deferred (stage["deferred"]).
    An UNMEASURED build under an enforced gate -> (design with the gate's error first, that check): nothing is
    deferred, its other findings stand (unmeasured_check). Anything else -> (design, None)"""
    if stage.get("gate") and stage.get("stage") == "unmeasured":
        stage["deferred"] = []
        gate = unmeasured_check(stage)
        return [gate, *design], gate
    if not stage.get("gate") or stage.get("stage") != "blockout":
        return design, None
    carried = {f"reference_{v['view']}" for v in stage["below"]}
    design = [c for c in design if c["ok"] or c["name"] not in carried]
    design, deferred = defer(design)
    stage["deferred"] = deferred
    gate = gate_check(stage, deferred)
    return [gate, *design], gate


# ============================================================================== THE METHODS LOCK
# The owner, 2026-11-13: "every method i mentioned ... implmented into each pipeline and enforced in the terms of
# being used". A method the builder HAS and no session reaches for changes nothing he sees: so a new piece's parts
# plan names, for every part made in code, the builder call(s) it is made with; parts that are many alike, or long
# and curved, must name a method that fits; and the build is held to what its plan named (rbx.Asset.build).
CALL = re.compile(r"\ba\.([a-z_]+)\b")
# a call a plan line DENIES ("a.box each; no a.repeat", "without a.scatter", "instead of a.sweep"): not named by it
# (card 988z: the line was not read for sense - a denial counted as naming the call)
DENIED = re.compile(r"\b(?:no|not|never|without|nor|instead\s+of|rather\s+than)\s+(?:by\s+|with\s+)?"
                    r"(?:an?\s+|the\s+|any\s+)?a\.([a-z_]+)\b", re.IGNORECASE)


def named_calls(text):
    """the builder calls a plan line NAMES: every a.<call> in it but the ones it only denies"""
    said = CALL.findall(text or "")
    denied = DENIED.findall(text or "")
    out = []
    for c in said:
        if c in denied:
            denied.remove(c)   # (each denial takes away one mention)
            continue
        out.append(c)
    return out
METHOD_OF = {"repeat": "repeat", "scatter": "scatter", "bend": "deform", "twist": "deform", "taper": "deform",
             "conform": "deform", "sweep": "sweep", "loop": "box modelling", "inset": "box modelling",
             "push": "box modelling", "round": "box modelling", "smooth": "smooth",
             # (the calls a plan line may name in their place: the build is held to those the same way)
             "stamp": "stamp", "ornament": "ornament", "moulding": "sweep", "cast": "cast", "scatter_relief": "scatter_relief", "mirror": "mirror", "tube": "tube",
             "loft": "loft", "cad": "cad", "cage": "cage", "import_mesh": "import_mesh", "card": "card"}
COUNTED = ("repeat", "scatter")          # (a plan line's "x12" is held against these: so many really made)
SHARED = frozenset({"mirror"})           # (one block of these serves several parts: only "used at all" is held)
MANY_WORDS = frozenset("teeth spokes links slats rivets studs bolts screws fins vents rungs treads scales shingles "
                       "tiles spikes beads pickets posts bars serrations grooves ribs pegs".split())
MANY_PHRASE = re.compile(r"\b(rows?|rings?|array|field|grid) of\b", re.IGNORECASE)
COUNT = re.compile(r"(?:\bx|×)\s?(\d{1,4})\s*$", re.IGNORECASE)
MANY_CALLS = frozenset({"repeat", "scatter", "stamp", "scatter_relief"})
LONG_WORDS = frozenset("horn horns hook hooks tusk tusks fang fangs claw claws tentacle tentacles cable cables "
                       "hose hoses rope ropes rail rails strap straps belt belts whip whips tail tails chain "
                       "chains".split())
LONG_CALLS = frozenset({"sweep", "moulding", "bend", "taper", "twist", "conform", "loft", "tube", "cad", "cage", "import_mesh",
                        "card"})
METHODS_LANE = "3d-methods"
_IN_SCOPE = re.compile(r"^(games/[^/]+/)?assets/models/build_[^/]+\.py$")


def plan_parts(text):
    """the brief's `- parts plan:` lines `<part> | <shape modules> | <data> | <surface>` -> [{name, shape, routes}]"""
    plan = _items(text or "").get("parts_plan")
    out = []
    for x in (plan or {}).get("list") or []:
        if "<answer>" in x:
            continue
        fields = [f.strip() for f in x.split("|")]
        shape = (fields + [""])[1]
        out.append({"name": re.sub(r"^\s*\d+\s*[.)]\s*", "", fields[0]).strip(), "shape": shape,
                    "routes": sorted(set(re.findall(r"\b(" + "|".join(ROUTES) + r")\w*\b", shape.lower())))})
    return out


def _bare(name):
    return re.sub(r"\([^)]*\)", " ", str(name)).strip()


def head_noun(name):
    """the part's OWN noun: the last word of its name, its count and anything in brackets left off ("Teeth x12"
    -> teeth, "Hook plate" -> plate, "Lanyard hook" -> hook). The words before it only say which one."""
    words = re.findall(r"[A-Za-z]+", COUNT.sub("", _bare(name)))
    return words[-1].lower() if words else ""


def many_of(name):
    """-> (the count the name ends with, or None; the word that says "many alike", or None): a count of three
    or more ("x12"), a plural the kit knows as a row of the same thing (teeth, rivets, bars), "a ring of ..."."""
    bare = _bare(name)
    m = COUNT.search(bare)
    n = int(m.group(1)) if m else None
    head = head_noun(name)
    phrase = MANY_PHRASE.search(bare)
    word = f"x{n}" if n is not None and n >= 3 else head if head in MANY_WORDS else \
        phrase.group(0) if phrase else None
    return n, word


def method_problems(plan):
    """-> [(part, what is wrong)]: a part made in code whose line names no builder call; many alike with no
    repeat / scatter / stamp (a mirror for four or fewer); a long curved form with no sweep / deform / loft /
    tube. A part is made in code when its line says so OR names a builder call (whatever route word it uses)."""
    out = []
    for p in plan:
        routes = set(p.get("routes") or ())
        calls = set(named_calls(p["shape"]))
        if "code" not in routes and not calls:
            continue
        if not calls:
            out.append((p["name"], "code, but no METHOD: name the builder call(s) it is made with (a.box, a.cad, "
                                   "a.sweep, a.repeat ...) - parallax-3d reference/06, 'Which method for which part'"))
            continue
        n, word = many_of(p["name"])
        fits = calls & MANY_CALLS or ("mirror" in calls and (n is None or n <= 4))
        if word and not fits and not routes & {"relief", "projected"}:
            out.append((p["name"], f'many alike ("{word}"): model ONE and a.repeat / a.scatter it (a.mirror for a '
                                   "pair or four) - or a.stamp / a relief when it only has to READ - never typed "
                                   "one by one"))
        head = head_noun(p["name"])
        if head in LONG_WORDS and not calls & LONG_CALLS and not routes & {"sculpt", "generated"}:
            out.append((p["name"], f'long and curved ("{head}"): a.sweep it, or build it straight and a.taper / '
                                   "a.bend it (a.loft, a.tube, a.cad, a.cage also count) - a box reads as a "
                                   "blockout"))
    return out


def _is_owner(rec):
    """kit/lib/locks.luau Locks.isOwner, word for word (kit/tools/plan.py _owner is the same rule)"""
    if not isinstance(rec, dict):
        return False
    who = rec.get("who")
    if who is not None and (not isinstance(who, str) or who.lower() != "owner"):
        return False
    by = rec.get("by") if rec.get("by") is not None else who
    return isinstance(by, str) and by.strip().lower().startswith("owner")


def _lock_record(root, home):
    """-> (the project's lock record, the folder its paths are said from): the project's own board/locks.json,
    else the kit home's when the project is a folder inside it (a game: one file for the home and its games)"""
    bases = [root]
    if home:
        try:
            inside = os.path.commonpath([os.path.normcase(os.path.abspath(root)),
                                         os.path.normcase(os.path.abspath(home))]) == \
                os.path.normcase(os.path.abspath(home))
        except ValueError:   # (another drive)
            inside = False
        if inside and os.path.normcase(os.path.abspath(home)) != os.path.normcase(os.path.abspath(root)):
            bases.append(home)
    for base in bases:
        try:
            with open(os.path.join(base, "board", "locks.json"), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return data, base
    return None, root


def methods_locked(script, root, home=None):
    """is this build script held to the methods lock: the project switched it on (board/locks.json
    grandfathered["3d-methods"] exists: frozen by kit new / kit plan / kit asset the first time one ran with the
    lock), the script is a piece's own (assets/models/build_<name>.py, a game's too), it is not on that list of
    pieces that existed before, and the owner did not waive it. root: the project (a game's folder: its record
    is the kit home's, `home`). KIT_METHODS_LOCK=1 / 0 forces it (the kit's own tests)."""
    forced = os.environ.get("KIT_METHODS_LOCK")
    if forced in ("0", "1"):
        return forced == "1"
    locks, base = _lock_record(root, home)
    if locks is None:
        return False
    lists = locks.get("grandfathered")
    old = lists.get(METHODS_LANE) if isinstance(lists, dict) else None
    if isinstance(old, dict) and not old:
        old = []   # (Lune's serde writes an EMPTY list as {}: a project with no piece yet froze exactly that)
    if not isinstance(old, list):
        return False
    try:
        rel = os.path.relpath(os.path.abspath(script), os.path.abspath(base)).replace("\\", "/").lower()
    except ValueError:
        return False
    if not _IN_SCOPE.match(rel) or rel in (str(x).replace("\\", "/").lower() for x in old):
        return False
    asset = os.path.basename(rel)[len("build_"):-len(".py")]
    waivers = locks.get("waivers")
    mine = waivers.get("3d") if isinstance(waivers, dict) else None
    rec = mine.get(asset) if isinstance(mine, dict) else None
    if rec is None and isinstance(mine, dict):   # (the record is kept under the name as it was typed)
        rec = next((v for k, v in mine.items() if str(k).lower() == asset), None)
    if _is_owner(rec) and (not isinstance(rec.get("steps"), list) or "methods" in rec["steps"]):
        return False
    return True


def lock_forced_off(script):
    """the methods lock switched OFF from the environment (KIT_METHODS_LOCK=0, the kit's own tests) on a script that
    is NOT one of the kit's fixtures -> what to say, or None (card 988z: it switched the lock off with no record;
    only the owner waives it - the build now says so on every piece it was switched off for)"""
    if os.environ.get("KIT_METHODS_LOCK") != "0":
        return None
    where = os.path.abspath(str(script)).replace("\\", "/").lower()
    if "/kit/selftest/" in where or os.path.basename(where).startswith("build__selftest"):
        return None
    return ("the methods lock is switched OFF by KIT_METHODS_LOCK=0 in the environment (the kit's own tests' "
            "switch) - only the owner waives the lock, on the record (kit approve / waiver): unset it")


SINGULAR = {"teeth": "tooth", "feet": "foot", "leaves": "leaf", "knives": "knife", "halves": "half"}


def part_key(name):
    """a part's name as the methods check pairs a plan line with a part the build made: its words, lower case and
    singular, its count, copy suffix, numbers and brackets left off ("Teeth x12" -> {tooth}, "Bolt~3" -> {bolt},
    "FencePost2" -> {fence, post})"""
    s = COUNT.sub("", _bare(str(name).split("~")[0]))
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    out = set()
    for w in re.findall(r"[A-Za-z]+", s):
        w = w.lower()
        out.add(SINGULAR.get(w, w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w))
    return frozenset(out)


def _use(entry):
    """one recorded use of a method -> (the part names it was used on, or (); how many pieces it made): an int (the
    count alone), a (name, count) pair, or a (names, count) pair"""
    if isinstance(entry, (tuple, list)) and len(entry) == 2:
        names, n = entry
        names = (names,) if isinstance(names, str) else tuple(x for x in (names or ()) if x)
        return names, int(n or 0)
    return (), int(entry or 0)


def _pair_by_name(parts, uses):
    """planned parts -> the ONE recorded use each names, when its name matches exactly one use's part and that use
    no other planned part: {planned index: use index}. Nothing is guessed: an unnamed use, or a name that fits two,
    is left to the counts."""
    pairs = {}
    for i, (name, _n) in enumerate(parts):
        key = part_key(name)
        hits = [j for j, (names, _c) in enumerate(uses)
                if key and any((k := part_key(x)) and (key <= k or k <= key) for x in names)]
        if len(hits) == 1:
            pairs[i] = hits[0]
    taken = [j for j in pairs.values()]
    return {i: j for i, j in pairs.items() if taken.count(j) == 1}


def methods_check(plan, used, typed):
    """the BUILD against its plan -> a check. plan: plan_parts(); used: {method: [each use: how many pieces it made,
    or (the part(s) it was used on, how many)]} as the build recorded it (a.repeat on Tooth made 12 -> {"repeat":
    [("Tooth", 12)]}; a set of names is read as one use each); typed: groups of part names that are one shape made one by one. A method the plan names on
    three parts is used on three; a line that says x12 by a.repeat has a repeat that makes twelve. None when
    there is nothing to hold it to."""
    if not plan and not typed:
        return None
    if not isinstance(used, dict):
        used = {m: [1] for m in used or ()}
    bad, want = [], {}
    for p in plan or []:
        named = sorted({METHOD_OF[c] for c in named_calls(p["shape"]) if c in METHOD_OF})
        n, _word = many_of(p["name"])
        one_count = sum(1 for m in named if m in COUNTED) == 1
        for m in named:
            want.setdefault(m, []).append((p["name"], n if one_count and m in COUNTED and n and n >= 3 else None))
    for m in sorted(want):
        parts, uses = want[m], [_use(x) for x in used.get(m) or []]
        if not uses:
            bad += [f"{name}: its plan names {m} and the build used none of it" for name, _n in parts]
            continue
        # (by NAME where the build says which part a use was on - card 988z: by counts alone it could not say which
        #  planned part was not made by it, and paired the largest count with the largest use whatever they were)
        pairs = _pair_by_name(parts, uses)
        if len(parts) > len(uses) and m not in SHARED:
            missing = [name for i, (name, _n) in enumerate(parts) if i not in pairs]
            named_all = len(pairs) == len(uses)
            bad.append(f'{len(parts)} planned parts name {m} ({", ".join(name for name, _n in parts[:4])}) and '
                       f"the build used it on {len(uses)}"
                       + (f' - not made by it: {", ".join(missing[:4])}' if named_all and missing else ""))
        for i, j in sorted(pairs.items()):
            name, n = parts[i]
            if n and uses[j][1] < n:
                bad.append(f"{name}: its plan says x{n} by {m} and the build's {m} on {uses[j][0][0]} makes "
                           f"{uses[j][1]}")
        counted = sorted(((n, name) for i, (name, n) in enumerate(parts) if n and i not in pairs), reverse=True)
        have = sorted((c for j, (_w, c) in enumerate(uses) if j not in pairs.values()), reverse=True)
        for (n, name), got in zip(counted, have, strict=False):
            if got < n:
                bad.append(f"{name}: its plan says x{n} by {m} and the build's {m} makes {got}")
    for names in typed or []:
        more = f" and {len(names) - 3} more" if len(names) > 3 else ""
        bad.append(f'{len(names)} parts are ONE shape typed {len(names)} times ({", ".join(names[:3])}{more})')
    return _check("methods", not bad, bad[:6] or f"{len(plan or [])} planned part(s) built as planned",
                  "every method the plan names is used, on as many parts and for as many pieces as it says; "
                  "nothing alike is typed one by one",
                  "build each part by the call its plan line names (a.repeat, a.scatter, a.sweep, a.taper / a.bend, "
                  "a.loop / a.inset / a.push, a.smooth) - or change the plan line and say why; model ONE of what is "
                  "alike inside `with a.repeat(...)` / `with a.scatter(...)`", "error")
