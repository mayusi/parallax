"""kit/tools/plan.py — `lune run kit plan <asset>`: the 3D PIPELINE for one asset, stage by stage, from its files.

Why: the kit has the whole arsenal (reference search, reference models, sourced sizes, local generators, vision
models, CAD, scanned materials, engraving, decals, projection, relief, auto-fitting, take-apart, judges) but nothing
said which to use WHEN, so every model fell into one narrow loop (trace one photo -> CAD -> rebuild ~30 times; the
Glock 17, 2026-10-08: none of the generators, vision or surface tools used, the floor 85, fresh judges 49). This
reads what an asset already has and prints the ten stages of ONE planned pass (kit/skills/parallax-3d/SKILL.md, "The
pipeline at a glance") — done / partly done / to do, what was found, what is missing — and the exact commands of the
first stage that is not done.

  0 brief      the owner's answers; hero features AND a parts plan: each part's STACK of modules
  1 gather     traced pictures of every side players see, 1-2+ reference models, sizes with sources, >= 2 px/mm on
               every hero feature, colours measured
  2 sheet      the MODEL SHEET the owner approved (kit sheet): the views, a callout per hero feature, the palette —
               a complex / hero / aaa piece made after 2026-11-11; a prop needs none
  3 draft      a generated 3D draft (kit gen views / gen / gen parts), or the brief's reason for none
  4 blockout   the BLOCKOUT the owner approved (kit blockout): the big shapes in clay against the sheet, before any
               detail or bake — the same pieces as the sheet
  5 shape      the last build's shape checks clean, every traced view at its bar, fitted proportions
  6 surface    a full (baked) build's surface checks clean, every material from data, markings
  7 mechanism  the brief's moving parts jointed, the take-apart declared and clear
  8 look       a full build newer than the script, hero / aaa: a judges' verdict on it
  9 present    the showcase rendered from the last full build

Pure python (no Blender): reads assets/models/build_<asset>.py (as text), its brief, traces, parts answers, the
reference files it cites, the generator records, and the last verdicts in .verify/. One JSON verdict line last.
"""

import glob
import json
import math
import os
import re
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_plan as P  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pack as PK  # noqa: E402  (the asset's pack: kit/tools/pack.py)

STAGES = (("brief", "Brief"), ("gather", "Gather"), ("sheet", "Model sheet"), ("draft", "3D draft"),
          ("blockout", "Blockout"), ("shape", "Shape"), ("surface", "Surface"), ("mechanism", "Mechanism"),
          ("look", "Look and judge"), ("present", "Present"))
# the stages whose artefact the OWNER approves one by one (kit approve 3d <asset> "<words>" --by owner --stage <key>):
# the tool that makes it and answers `state(asset, root)` (kit/tools/<key>.py)
APPROVED_STAGES = ("sheet", "blockout")
DONE, PARTIAL, TODO, NOT_NEEDED, OPTIONAL = "done", "partial", "to do", "not needed", "optional"

# failing checks of the build verdict, by the stage that fixes them (a name with a trailing _ is a prefix)
SHAPE_CHECKS = ("stage", "cad_solid", "cad_volume", "sculpt_detail", "floating_parts", "part_visibility", "faceting",
                "slivers", "sharp_edges", "section_match", "part_match_", "reference_", "view_gaps_", "ref_sizes",
                "lines_", "size_vs_target", "size_plausible", "inside_out", "spec_", "plate_support", "attach_gaps", "see_through", "cut_through",
                "tiny_cuts", "expect:", "symmetry", "hidden_parts", "degenerate_parts", "open_parts", "learned_")
SURFACE_CHECKS = ("colour_match", "roughness_variation", "pbr_values", "material_values", "palette", "dark_finishes",
                  "texel_density", "pattern_resolution",
                  "projection_", "texture_coverage", "marking_placement", "texture_from")
MECHANISM_CHECKS = ("mechanism", "disassembly", "fastener_seat", "fastener_support", "clear:")
MESH = re.compile(r"\b[\w-]+\.(manifold|tris|degenerate_faces|open_edges|uv|loose_verts|wire_edges|materials)=")
# a reference MODEL's outline: kit refs measure's mask (build/refs/<name>_<view>_mask.png) — a downloaded photo lives in
# a search's own folder (build/refs/<search>/...), never at the top with that ending
MODEL_MASK = re.compile(r"^build/(refs/[^/]+_mask\.png|library/.+)$")  # (or a dissected model's part render)
SIDE_OF = {"front": "front", "back": "back", "rear": "back", "top": "top", "left": "side", "right": "side",
           "side": "side", "bottom": "top", "underside": "top"}


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _rel(root, path):
    return os.path.relpath(path, root).replace("\\", "/")


def _family(name):
    """'part_match_side' -> its stage by the check lists above (None: a look / review check)"""
    for stage, names in (("shape", SHAPE_CHECKS), ("surface", SURFACE_CHECKS), ("mechanism", MECHANISM_CHECKS)):
        if any(name == n or (n.endswith(("_", ":")) and name.startswith(n)) for n in names):
            return stage
    return None


def _verdict(root, chain):
    """the asset step's result of .verify/<chain>.json and when it was written -> (result | None, mtime | None)"""
    path = os.path.join(root, ".verify", f"{chain}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None, None
    for step in d.get("steps") or []:
        r = step.get("result")
        if isinstance(r, dict) and ("design" in r or "facts" in r):
            return r, _mtime(path)
    return None, _mtime(path)


def _strip_prose(text):
    """the script without its docstrings and comments (a fallback for a script that does not parse)"""
    text = re.sub(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'', "", text)
    return re.sub(r"(?m)#.*$", "", text)


def read_script(text):
    """facts the build script states — its CODE, parsed (ast), never run: the template's docstring lists the API
    (`a.import_mesh(...)`, `a.param(...)`), and prose is never a call. A script that does not parse (mid-edit) is read
    as text with its docstrings and comments taken out."""
    import ast  # noqa: PLC0415

    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return _read_script_text(_strip_prose(text))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]

    def name_of(c):
        f = c.func
        return f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None

    def of(name):
        return [c for c in calls if name_of(c) == name]

    def s(node):
        return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None

    def kw(c, key):
        return next((k.value for k in c.keywords if k.arg == key), None)

    def arg(c, i, key):
        return c.args[i] if len(c.args) > i else kw(c, key)

    asset = next(iter(of("Asset")), None)
    tier = s(kw(asset, "quality")) if asset is not None else None
    traces = [(s(arg(c, 0, "trace")), s(kw(c, "view")) or "side") for c in of("trace_match") if s(arg(c, 0, "trace"))]
    mats, from_data, worn = [], [], []
    for c in of("material"):
        n = s(arg(c, 0, "name"))
        if not n:
            continue
        mats.append(n)
        spread = [k.value for k in c.keywords if k.arg is None]  # **rbx.finish(...) / **rbx.real(...) / **rbx.look
        if kw(c, "scan") is not None or any(isinstance(v, ast.Call) and name_of(v) in ("finish", "real", "look")
                                            for v in spread):
            from_data.append(n)
        if any(k.arg in ("life", "wear", "grime", "chip", "burnish", "rub", "smudge") for k in c.keywords) or any(
                isinstance(v, ast.Call) and any(k.arg == "life" for k in v.keywords) for v in spread):
            worn.append(n)   # (its life: life= / a wear key, on a.material or the finish it spreads)
    texts = of("text")
    inside_cuts = {id(n) for c in of("cut") for a in c.args for n in ast.walk(a) if isinstance(n, ast.Call)}
    engraved = [t for t in texts if id(t) in inside_cuts or "engrav" in str(s(arg(t, 3, "mat")) or "")]
    return {
        "tier": tier if tier in ("prop", "hero", "aaa") else "prop",
        "master": s(kw(asset, "stage")) == "master" if asset is not None else False,
        "private": (isinstance(kw(asset, "private"), ast.Constant) and kw(asset, "private").value is True)
        if asset is not None else False,
        "traces": traces,
        "params": len(of("param")),
        "cad": len(of("cad")),
        "sculpts": len(of("sculpt")),
        "imports": [p for p in (s(arg(c, 1, "path")) for c in of("import_mesh")) if p],
        "materials": mats,
        "materials_from_data": from_data,
        "materials_worn": worn,
        "patterns": sum(1 for c in of("material") if kw(c, "pattern") is not None),
        "markings": len(texts),
        "engraved": len(engraved),
        "surface_tools": {k: len(of(k)) for k in ("decal", "project", "relief", "displace", "texture_from", "zone")},
        "albedo": any(kw(c, "albedo") is not None for c in of("trace_match")),
        "joints": len(of("joint")),
        "disassembly": len(of("disassembly")),
        "spec": bool(of("spec")),
        "section_match": len(of("section_match")),
        "learned_from": len(of("learned_from")),
        "pack": len(of("pack")),
    }


def _read_script_text(text):
    """read_script's fallback: the same facts by text patterns (the script's prose already taken out)"""
    def count(pat):
        return len(re.findall(pat, text))

    tier = re.search(r"\bquality\s*=\s*[\"'](prop|hero|aaa)[\"']", text)
    traces = []
    for m in re.finditer(r"\.trace_match\(\s*[\"']([\w./-]+)[\"']([^)]*)", text):
        view = re.search(r"\bview\s*=\s*[\"'](\w+)[\"']", m.group(2))
        traces.append((m.group(1), view.group(1) if view else "side"))
    mats = re.findall(r"\.material\(\s*[\"']([\w-]+)[\"'](.*)", text)
    from_data = [n for n, rest in mats if re.search(r"\b(finish|real|look)\(|\bscan\s*=", rest)]
    worn = [n for n, rest in mats if re.search(r"\b(life|wear|grime|chip|burnish|rub|smudge)\s*=", rest)]
    return {
        "tier": tier.group(1) if tier else "prop",
        "master": bool(re.search(r"\bstage\s*=\s*[\"']master[\"']", text)),
        "private": bool(re.search(r"\bprivate\s*=\s*True", text)),
        "traces": traces,
        "params": count(r"\.param\("),
        "cad": count(r"\.cad\("),
        "sculpts": count(r"\.sculpt\("),
        "imports": re.findall(r"\.import_mesh\([^)]*?[\"']([\w./\\-]+\.(?:glb|gltf|obj|fbx))[\"']", text),
        "materials": [n for n, _ in mats],
        "materials_from_data": from_data,
        "materials_worn": worn,
        "patterns": count(r"\bpattern\s*=\s*[\"']"),
        "markings": count(r"\.text\("),
        "engraved": count(r"[\"']engraving[\"']") + count(r"\.cut\([^\n]*\.text\("),
        "surface_tools": {k: count(rf"\.{k}\(") for k in ("decal", "project", "relief", "displace", "texture_from",
                                                         "zone")},
        "albedo": bool(re.search(r"\balbedo\s*=", text)),
        "joints": count(r"\.joint\("),
        "disassembly": count(r"\.disassembly\("),
        "spec": bool(re.search(r"\.spec\(", text)),
        "section_match": count(r"\.section_match\("),
        "learned_from": count(r"\.learned_from\("),
        "pack": count(r"\.pack\("),
    }


def reference_models(root, texts):
    """the reference MODELS an asset's files cite: refs/[private/]<x>.measure.json | .inspect.json, and
    rbx_trace.measure("<x>") / loft_stations(... measure("<x>") ...) -> sorted names (only those on disk)"""
    names = set()
    for t in texts:
        names.update(m.group(1) for m in re.finditer(r"refs/(?:private/[\w-]+/|private/)?([\w.-]+?)\.(?:measure|"
                                                      r"inspect)\.json", t))
        names.update(m.group(1) for m in re.finditer(r"\bmeasure\(\s*[\"']([\w.-]+)[\"']", t))
        names.update(m.group(1) for m in re.finditer(r"build/library/([\w.-]+)/", t))  # a part answer's tile
    found = []
    for n in sorted(names):
        hits = glob.glob(os.path.join(root, "refs", "**", f"{n}.measure.json"), recursive=True)
        hits += glob.glob(os.path.join(root, "refs", "**", f"{n}.inspect.json"), recursive=True)
        if hits:
            found.append(n)
    return found


def own_reference_models(asset, root):
    """reference models measured / inspected UNDER the asset's own name (kit refs measure / library inspect --name
    <asset>_scan ...): refs/**/<asset>*.measure.json | .inspect.json"""
    out = set()
    for kind in ("measure", "inspect"):
        for p in glob.glob(os.path.join(root, "refs", "**", f"{asset}*.{kind}.json"), recursive=True):
            name = os.path.basename(p)[:-len(f".{kind}.json")]
            if not name.endswith("_build"):  # (an inspection of the asset's OWN build is no reference)
                out.add(name)
    return out


def reference_sources(names, root):
    """{reference model name: what `kit refs sections --ref` takes} — its library id (a measure / inspect json's
    `source` under .../library/<id>/), else the model file it was measured from; names whose source is unknown left out"""
    out = {}
    for n in names:
        for kind in ("measure", "inspect"):
            for path in glob.glob(os.path.join(root, "refs", "**", f"{n}.{kind}.json"), recursive=True):
                try:
                    with open(path, encoding="utf-8") as fh:
                        src = str(json.load(fh).get("source") or "")
                except (OSError, ValueError, AttributeError):
                    continue
                m = re.search(r"library[/\\]([0-9a-f]{32})[/\\]", src)
                if m:
                    out.setdefault(n, m.group(1))
                elif src.lower().endswith((".glb", ".gltf", ".obj", ".fbx")):   # (a source path is the json's own:
                    # relative to its folder — said relative to the project, as the command runs from there)
                    full = os.path.normpath(os.path.join(os.path.dirname(path), src))
                    out.setdefault(n, os.path.relpath(full, root).replace("\\", "/"))
    return out


def sections_report(asset, root):
    """kit refs sections' saved comparison (build/refs/<asset>_sections.json) -> {ref, stations, worst_p90, over,
    t} or None"""
    path = os.path.join(root, "build", "refs", f"{asset}_sections.json")
    try:
        d = _d(json.loads(_read(path))) if _read(path) else {}
    except ValueError:
        d = {}
    if not d:
        return None
    rows = [r for r in d.get("rows") or [] if isinstance(r, dict) and r.get("p90") is not None]
    return {"ref": d.get("ref"), "stations": len(rows), "worst_p90": max((r["p90"] for r in rows), default=None),
            "over": sum(1 for r in rows if r["p90"] > 1.5), "t": _mtime(path)}


def traced_views(asset, root, registered, pictures=None):
    """{view: sorted sources} of every traced outline of the asset: assets/models/<asset>_*.trace.json by its own
    `view` or its name's last word (glock17_photo_side -> side), and the traces the build registers. Source = 'model'
    for an outline measured off a reference model (kit refs measure: no camera error), else 'photo'. pictures: a dict
    filled with {view: the traced PHOTO's path} (a registered trace's first)."""
    views = {}
    reg_paths = {os.path.normpath(os.path.join(root, p)) for p in registered.values()}
    paths = set(glob.glob(os.path.join(root, "assets", "models", f"{asset}_*.trace.json")))
    paths |= {os.path.join(root, p) for p in registered.values()}
    for path in sorted(paths):
        try:
            with open(path, encoding="utf-8") as fh:
                t = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(t, dict):
            continue
        stem = os.path.basename(path)[:-len(".trace.json")]
        words = stem.split("_")
        view = (t.get("view") or P.VIEW_OF_SUFFIX.get(stem[len(asset) + 1:]) or P.VIEW_OF_SUFFIX.get(words[-1])
                or next((v for v, p in registered.items() if os.path.join(root, p) == path), None))
        if not t.get("view") and words[-1] == "left" and len(words) > 1 and P.VIEW_OF_SUFFIX.get(words[-2]) == "side":
            view = "side"  # (an unlabelled <asset>_side_left: the other flank, a side view)
        if not view:
            continue
        pic = str(t.get("source") or t.get("image") or "").replace("\\", "/")
        src = "model" if MODEL_MASK.match(pic) else "photo"
        views.setdefault(view, set()).add(src)
        if pictures is not None and pic and src == "photo" and (
                view not in pictures or os.path.normpath(path) in reg_paths):
            pictures[view] = pic
    return {v: sorted(s) for v, s in views.items()}


def parts_plan(text):
    """the brief's `- parts plan:` lines `<part> | <shape modules> | <data> | <surface>` -> [{name, routes, shape,
    data, surface, organic, ...}]: each part's STACK. `routes` = the route words of its SHAPE field only (a stack may
    name several: code + generated) — a surface field's "projected detail" is no shape"""
    items = P._items(text)
    plan = items.get("parts_plan")
    if plan is None:
        return None
    out = []
    for i, x in enumerate(plan["list"]):
        if "<answer>" in x:
            continue
        part = P.parse_feature(x, i + 1)
        fields = [f.strip() for f in x.split("|")]
        part["shape"], part["data"], part["surface"] = (fields + ["", "", "", ""])[1:4]
        # a route's own word, its endings too ("sculpted", "procedurally") — never an alias inside a description: the
        # aliases name a whole field ("the draft's texture" is no projection)
        part["routes"] = sorted(set(re.findall(r"\b(" + "|".join(P.ROUTES) + r")\w*\b", part["shape"].lower())))
        part["line"] = x
        out.append(part)
    return out


# ============================================================================== THE GRAVEYARD (routes the owner rejected)
# (the ENFORCED rules; the vault's graveyard.md is its owner-facing record, written by kit verdict / kit lesson)
GRAVEYARD = os.path.join("kit", "knowledge", "vault", "3d", "routes.md")
OWNER_ALLOWS = re.compile(r"""(?i)\bowner\s*(?:says|said|allows?|ok)?\s*:\s*["“]([^"”]{4,})["”]""")


def _cells(row):
    """a markdown table row -> its cells ('\\|' inside a cell is a literal |: the regex columns use it)"""
    cells = re.split(r"(?<!\\)\|", row.strip().strip("|"))
    return [c.strip().replace("\\|", "|") for c in cells]


def graveyard(root=ROOT):
    """kit/knowledge/vault/3d/routes.md, its `## Graveyard rules` table -> [{id, tiers, part, routes, text, unless,
    words, source, why}]"""
    rows, cols = [], None
    text = _read(os.path.join(root, GRAVEYARD)) or _read(os.path.join(ROOT, GRAVEYARD))  # (the project's, else the kit's)
    inside = False
    for line in text.splitlines():
        if line.startswith("#"):
            inside = line.lower().lstrip("# ").startswith("graveyard rules")
            continue
        if not inside or not line.lstrip().startswith("|"):
            continue
        cells = _cells(line)
        if cols is None:
            cols = [c.lower() for c in cells]
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        r = dict(zip(cols, cells))
        rows.append({"id": r.get("id", "?"), "tiers": r.get("tiers", "*"), "part": r.get("part", "*"),
                     "routes": r.get("routes", "*"), "text": r.get("text", "*"), "unless": r.get("unless", "*"),
                     "words": r.get("owner's words", ""), "source": r.get("source", ""),
                     "why": r.get("do not retry because", "")})
    return rows


def _rx(pattern, text):
    if pattern in ("", "*"):
        return True
    try:
        return re.search(pattern, text, re.IGNORECASE) is not None
    except re.error:
        return False  # (a broken row never refuses a build: kit plan names it below)


def graveyard_hits(plan, tier, rows):
    """parts-plan lines on a graveyarded route -> [(part, row, allowed_words or None)]"""
    out = []
    for p in plan or []:
        line = p.get("line") or ""
        routes = "+".join(p.get("routes") or [])
        for g in rows:
            tiers = {t.strip() for t in g["tiers"].split(",")}
            if "*" not in tiers and tier not in tiers:
                continue
            want = {w.strip() for w in g["routes"].split("|")} if g["routes"] not in ("", "*") else None
            if want is not None and routes not in want:
                continue
            # (`part` reads the part's NAME only — "small" / "surface" in a data column is no part family)
            if not (_rx(g["part"], p.get("name") or "") and _rx(g["text"], line)):
                continue
            if g["unless"] not in ("", "*") and _rx(g["unless"], line):
                continue
            ok = OWNER_ALLOWS.search(line)
            out.append((p["name"], g, ok.group(1) if ok else None))
    return out


def stack_problems(plan):
    """parts whose stack names no shape module, no data or no surface, or builds a sculpted / organic part from code
    ALONE"""
    out = []
    for p in plan:
        if not p["routes"]:
            out.append((p["name"], "no shape modules (the 2nd field: code · sculpt · generated · relief · projected · "
                                   "procedural)"))
        elif p["routes"] == ["code"] and p.get("organic"):
            out.append((p["name"], f"code alone, but it is {p['organic']}"))
        if not p.get("data"):
            out.append((p["name"], "no data (the 3rd field: its pictures, reference model, sourced sizes)"))
        if not p.get("surface"):
            out.append((p["name"], "no surface (the 4th field: finish, scan, pattern, markings)"))
    return out


def moving_parts(text):
    """the brief's moving parts — ONE predictable rule, said back by `kit plan` ('moving parts read as: ...'):
    NONE when the answer opens with a none-phrase standing alone (none · no · n/a · nothing [moves | at all] · [it has]
    no moving parts [at all] · [it] doesn't move · static · a dash — then the end, or punctuation not before a number)
    and the rest names no exception (except · only · but · apart from · other than · besides) and no measured motion
    in brackets ('(pulls 5 mm)'); else the parts, split at the top level only (commas INSIDE parentheses are a part's own
    words). Write the parts, never 'no: trigger, hammer' — that reads as none."""
    t = re.sub(r"[*_`]+", "", str(text or "")).strip()  # (markdown emphasis: **none** is none)
    head = NONE_HEAD.match(t)
    if head:
        rest = t[head.end():]
        ex = EXCEPTION.search(rest)
        if ex:
            t = rest[ex.end():].strip(" :,;—–-")  # ('none, except the lid (opens)': the lid is the part)
        elif not re.search(r"\([^)]*\d", rest):
            return []
    parts, depth, cur = [], 0, ""
    for ch in t:
        depth += (ch == "(") - (ch == ")")
        if ch in ",;" and depth <= 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip(" .") for p in parts if p.strip(" .")]


NONE_HEAD = re.compile(r"(?i)\W*(it has no moving parts?( at all)?|no moving parts?( at all)?|nothing moves|nothing at all|"
                       r"(it )?(does ?n[o'’]t|doesn['’]t) move|none( at all| needed)?|nothing|n/a|na|no|"
                       r"static( prop| object| piece| model)?|[-—–]+)"
                       r"(?=\s*(?:$|[.,;:!—–()\-](?!\s*\d)))")
EXCEPTION = re.compile(r"(?i)\b(except|apart from|other than|save for|aside from)\b")
# (unambiguous only: 'none — this is only a display piece', 'None, but it must look heavy', 'static — besides, it hangs
#  on a wall' name no part; write an exception as 'none except the trigger (pulls 5 mm)')


def _d(x):
    """x when it is a dict, else {} (a hand-edited pack can hold anything)"""
    return x if isinstance(x, dict) else {}


def _raw_answer(q, text):
    """the question's answer exactly as written after its colon (the brief's reader files an answer opening with "("
    as help: '(none — it is a solid prop)' is still an answer)"""
    m = re.search(rf"(?mi)^[-*]\s+{re.escape(q.replace('_', ' '))}\s*:(.*)$", text or "")
    said = m.group(1).strip() if m else ""
    if "<answer>" in said:
        return ""  # (unanswered)
    help_text = TEMPLATE_HELP.get(q, "") if "TEMPLATE_HELP" in globals() else ""
    if help_text and said.startswith(help_text[:25]):
        return ""  # (only the template's help: blank)
    cut = re.search(r"\s{2,}\(", said[1:])  # (the answer, then "  (" and the template's help)
    return said[:cut.start() + 1].strip() if cut else said


def _answer_text(q, text, line):
    """the question's line PLUS its own wrapped lines (indented, before any list item, blank line or next question) —
    read from the brief itself: its reader files a list item's wrapped tail, and a wrapped line opening with "(", as
    the question's text or help"""
    lines = (text or "").splitlines()
    pat = re.compile(rf"(?i)^[-*]\s+{re.escape(q.replace('_', ' '))}\s*:")
    at = next((i for i, x in enumerate(lines) if pat.match(x)), None)
    if at is None or not line:
        return line
    out = [line]
    for x in lines[at + 1:]:
        if not x.strip() or not x[:1].isspace() or re.match(r"^\s*(\d+\s*[.)]|[-*])\s", x):
            break
        if TEMPLATE_HELP.get(q) and x.strip().startswith(TEMPLATE_HELP[q][:25]):
            break
        out.append(x.strip())
    return " ".join(out)


def _template_help():
    """{question: the help the brief template puts after its <answer>} (kit/templates/asset.brief.md)"""
    out = {}
    try:
        with open(os.path.join(ROOT, "kit", "templates", "asset.brief.md"), encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^[-*]\s+([A-Za-z][A-Za-z ]*?)\s*:\s*<answer>\s*(.*)$", line.rstrip())
                if m and m.group(2).strip():
                    out[m.group(1).strip().lower().replace(" ", "_")] = m.group(2).strip()
    except OSError:
        pass
    return out


TEMPLATE_HELP = _template_help()


def _blank_line(q, text):
    """the question's line holds nothing — or only the template's own help, its <answer> deleted"""
    words = re.escape(q.replace("_", " "))
    m = re.search(rf"(?mi)^[-*]\s+{words}\s*:(.*)$", text or "")
    if not m:
        return False
    said = m.group(1).strip()
    help_text = TEMPLATE_HELP.get(q, "")
    return not said or bool(help_text) and said.startswith(help_text[:25])


def facts(asset, root=ROOT):
    """everything the stages are decided from"""
    models = os.path.join(root, "assets", "models")
    script_path = os.path.join(models, f"build_{asset}.py")
    script = _read(script_path)
    brief_path = os.path.join(models, f"{asset}.brief.md")
    brief_text = _read(brief_path)
    brief = P.parse_brief(brief_text) if brief_text else None
    s = read_script(script)
    registered = {view: os.path.join("assets", "models", f"{name}.trace.json") for name, view in s["traces"]}
    pictures = {}
    views = traced_views(asset, root, registered, pictures)
    parts_md = _read(os.path.join(models, f"{asset}.parts.md"))
    spec_path = os.path.join(root, "refs", f"{asset}.spec.json")
    spec_text = _read(spec_path)
    texts = [script, brief_text, parts_md, spec_text]
    drafts = sorted(set(_rel(root, p) for pat in (f"{asset}*.gen.json", f"{asset}*.parts.json")
                        for p in glob.glob(os.path.join(models, pat))))
    drafts += [p for p in s["imports"] if p not in drafts]
    geo, geo_t = _verdict(root, f"asset-geo-{asset}")
    full, full_t = _verdict(root, f"asset-{asset}")
    answers = re.findall(r"^- .+?\|.*$", parts_md, re.MULTILINE)
    return {
        "asset": asset,
        "root": root,
        "params_fitted": os.path.isfile(os.path.join(models, f"{asset}.params.json")),
        "script": script_path if script else None,
        "script_t": _mtime(script_path),
        "s": s,
        "brief": brief,
        "brief_path": brief_path if brief_text else None,
        "brief_text": brief_text,
        "brief_items": P._items(brief_text) if brief_text else {},
        "parts_plan": parts_plan(brief_text) if brief_text else None,
        "draft_answer": ((brief or {}).get("answers") or {}).get("draft", ""),
        "views": views,
        "trace_pictures": pictures,  # {view: the traced photo} (any trace naming: <asset>_photo_side, _rifle_side ...)
        "registered": sorted(registered),
        "ref_models": sorted(set(reference_models(root, texts)) | own_reference_models(asset, root)),
        "ref_sources": reference_sources(sorted(set(reference_models(root, texts)) | own_reference_models(asset, root)),
                                         root),
        "sections": sections_report(asset, root),
        "dims": sorted(set(re.findall(r"\bdims:([\w.-]+)", "\n".join(texts)))),
        "spec": bool(spec_text) or s["spec"],
        "drafts": drafts,
        "geo": geo, "geo_t": geo_t, "full": full, "full_t": full_t,
        "judge_t": max(_mtime(os.path.join(models, f"{asset}.judge.json")) or 0,
                       _mtime(os.path.join(models, f"{asset}.verify.json")) or 0) or None,  # (the verifier's round)
        "review": os.path.isfile(os.path.join(models, f"{asset}.review.md")),
        "showcase_t": _mtime(os.path.join(root, "build", "showcase", asset, "poster.png")),
        "part_answers": len(answers),
        "part_fixes": len(re.findall(r"verdict:\s*fix", parts_md)),
        "pack": PK.load(asset, root) if os.path.isfile(PK.pack_path(asset, root)) else None,
    }


def study_gate(f):
    """the reference study (kit/tools/study.py) -> None when this asset needs none (it predates the study lock:
    board/locks.json grandfathered["3d-study"]; the owner waived it; a kit make prop), else (problems, facts)"""
    root, a = f["root"], f["asset"]
    try:
        with open(os.path.join(root, "board", "locks.json"), encoding="utf-8") as fh:
            locks = json.load(fh)
    except (OSError, ValueError):
        locks = {}
    old = ((locks.get("grandfathered") or {}).get("3d-study")) if isinstance(locks, dict) else None
    if isinstance(old, list):
        script = f"assets/models/build_{a}.py".lower()
        if script in (str(x).lower() for x in old):
            return None
    rec = (((locks.get("waivers") or {}).get("3d") or {}).get(a)) if isinstance(locks, dict) else None
    if isinstance(rec, dict) and str(rec.get("by", "")).lower().startswith("owner") and             (not isinstance(rec.get("steps"), list) or "study" in rec["steps"]):
        return None
    import study as ST  # noqa: PLC0415  (kit/tools/study.py: it imports this module back, so imported here)

    return ST.gate(a, root)


def _locks(root):
    """the project's lock record (board/locks.json: the kit home's — one file for the home and its games), read the
    way kit/lib/locks.luau reads it; {} when there is none (a test's own folder)"""
    try:  # (inside the kit's home: a game folder — never a sibling folder whose name merely starts the same)
        inside = os.path.commonpath([os.path.normcase(os.path.abspath(root)), os.path.normcase(ROOT)]) == \
            os.path.normcase(ROOT)
    except ValueError:  # (another drive)
        inside = False
    for base in ([root, ROOT] if inside else [root]):
        try:
            with open(os.path.join(base, "board", "locks.json"), encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except (OSError, ValueError):
            continue
    return {}


def _owner(rec):
    """an approval record counts only when it is the OWNER's — the rule of kit/lib/locks.luau Locks.isOwner, word
    for word: `who`, when given, must be the word owner; `by` (else `who`) must be a string that starts with it"""
    if not isinstance(rec, dict):
        return False
    who = rec.get("who")
    if who is not None and (not isinstance(who, str) or who.lower() != "owner"):
        return False
    by = rec.get("by") if rec.get("by") is not None else who
    return isinstance(by, str) and by.strip().lower().startswith("owner")


def stage_gate(f, step):
    """one of the owner's STAGE approvals (the model sheet, the blockout) as the lock reads it (kit/lib/lanelocks.luau)
    -> None when this asset needs none (a prop; a script that predates the stage approvals: board/locks.json
    grandfathered["3d"] / ["3d-stages"]; the owner waived the step), else {"state": the tool's own (exists, id,
    stale, problems, notes, png), "approved": their yes holds for the artefact as it is now, "changed": they
    approved an earlier one, "date"}"""
    a, root = f["asset"], f["root"]
    import importlib  # noqa: PLC0415  (kit/tools/sheet.py, kit/tools/blockout.py: they import this module back)

    # (the tier as the LOCK reads the brief's quality line — kit/lib/lanelocks.luau briefTier, kit/tools/sheet.py
    #  tier_of: aaa, hero or complex anywhere in it — never the clock's reading: the plan and the lock must agree)
    if importlib.import_module("sheet").tier_of(f.get("brief")) not in ("complex", "hero", "aaa"):
        return None
    locks = _locks(root)
    path = os.path.join(root, "assets", "models", f"build_{a}.py")
    try:
        script = os.path.relpath(path, ROOT).replace("\\", "/").lower()
    except ValueError:  # (a project on another drive than the kit's home)
        script = os.path.abspath(path).replace("\\", "/").lower()
    lists = locks.get("grandfathered") if isinstance(locks.get("grandfathered"), dict) else {}
    for lane in ("3d", "3d-stages"):
        if script in (str(x).replace("\\", "/").lower() for x in lists.get(lane) or []):
            return None
    waived = ((locks.get("waivers") or {}).get("3d") or {}).get(a)
    if _owner(waived) and (not isinstance(waived.get("steps"), list) or step in waived["steps"]):
        return None
    try:
        tool = importlib.import_module(step)
    except ImportError:
        return None
    st = tool.state(a, root)
    rec = (((locks.get("stages") or {}).get("3d") or {}).get(a) or {}).get(step)
    same = _owner(rec) and st["exists"] and not st["stale"] and rec.get("id") == st["id"]
    return {"state": st, "approved": bool(same), "changed": bool(_owner(rec) and not same),
            "date": (rec or {}).get("date") if isinstance(rec, dict) else None}


def dossier_summary(name):
    """the dossier of a real object (kit/refs/dossier.py): None when it has none; {error} when it cannot be read"""
    try:
        sys.path.insert(0, os.path.join(ROOT, "kit", "refs"))
        import dossier  # noqa: PLC0415

        return dossier.summary_for(name, offline=True)
    except Exception as e:  # noqa: BLE001 — a broken dossier is said in the plan, never a crash
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def _problems(r, stage, warnings=False):
    """failing checks of a verdict that stage fixes (errors; warnings too for the surface, whose colour / roughness /
    projection checks only ever WARN) -> [name, ...]"""
    out = []
    for c in (r or {}).get("design") or []:
        sev_ok = c.get("severity") == "error" or (warnings and c.get("severity") == "warn")
        if sev_ok and _family(str(c.get("name"))) == stage:
            out.append(str(c.get("name")))
    out += [f"{n} (held back by the blockout)" for n in _deferred(r) if _family(n) == stage and n not in out]
    if stage == "shape":
        out += sorted({m.group(0).rstrip("=") for m in MESH.finditer(str((r or {}).get("summary") or ""))})
        st = ((r or {}).get("facts") or {}).get("stage") or {}
        if isinstance(st, dict) and st.get("stage") == "blockout":
            out = [n for n in out if n != "stage"]
            out.insert(0, "stage: blockout (a traced view below its bar)")
    return out


def _deferred(r):
    """the detail checks a blockout build FAILED but held back (facts.stage.deferred: the outline comes first) — still
    failing, so never 'done'"""
    st = ((r or {}).get("facts") or {}).get("stage") or {}
    return [str(n) for n in (st.get("deferred") or [])] if isinstance(st, dict) else []


def _other_errors(r):
    out = [str(c.get("name")) for c in (r or {}).get("design") or []
           if c.get("severity") == "error" and _family(str(c.get("name"))) is None]
    return out + [f"{n} (held back by the blockout)" for n in _deferred(r) if _family(n) is None and n not in out]


MODEL_NUMBER = re.compile(r"\b[A-Z][\w-]*\s+[A-Z]{0,3}-?\d+[A-Za-z]{0,3}\b|\b[A-Z]{1,4}-?\d{1,5}[A-Za-z]?\b")


def is_named(name, category=None):
    """a REAL named product (a make and its model number: "Glock 17 Gen5", "AK-47", "M1911") or a pistol / rifle —
    its dossier gates Gather at every tier; "a 55-gallon oil drum", "a 2x4 plank", "a 1950s fridge" are generic"""
    return str(category or "") in ("pistol", "rifle") or bool(MODEL_NUMBER.search(str(name or "")))


def asset_traces(f):
    """the asset's traces: registered by a.trace_match + every assets/models/<asset>[_*].trace.json"""
    models = os.path.join(f["root"], "assets", "models")
    a = f["asset"]
    # (another asset named <asset>_<more> owns its own traces: arp's gate never takes arp_lib_* / arp_saint_*)
    others = {os.path.basename(p)[len("build_"):-len(".py")] for p in glob.glob(os.path.join(models, f"build_{a}_*.py"))}
    others |= {os.path.basename(p)[:-len(".brief.md")] for p in glob.glob(os.path.join(models, f"{a}_*.brief.md"))}
    names = {n for n, _ in f["s"]["traces"]}
    found = glob.glob(os.path.join(models, f"{a}_*.trace.json")) + glob.glob(os.path.join(models, f"{a}.trace.json"))
    for p in found:
        n = os.path.basename(p)[:-len(".trace.json")]
        if not any(n == o or n.startswith(o + "_") for o in others):
            names.add(n)
    return sorted(n for n in names if os.path.isfile(os.path.join(models, f"{n}.trace.json")))


def unlooked_traces(f):
    """traces with no `kit pack <asset> looked <trace> ok|retraced`, or changed since that look (its sha)"""
    looked = _d(_d(f.get("pack")).get("looked"))
    out = []
    for n in asset_traces(f):
        row = _d(looked.get(n))
        sha = PK.file_sha(os.path.join(f["root"], "assets", "models", f"{n}.trace.json"))
        if row.get("verdict") not in ("ok", "retraced") or row.get("sha") != sha:  # (no sha: never proven current)
            out.append(n)
    return out


def assess(f):
    """-> [{key, title, status, found, missing, commands}] for the ten stages"""
    a, s, brief = f["asset"], f["s"], f["brief"]
    tier = s["tier"]
    big = tier in ("hero", "aaa")
    what = ((brief or {}).get("answers") or {}).get("what") or a.replace("_", " ")
    obj = re.split(r"[(,;—]| - ", what)[0].strip() or a
    out = []

    def stage(key, status, found=(), missing=(), commands=()):
        title = dict(STAGES)[key]
        out.append({"key": key, "title": title, "status": status, "found": list(found), "missing": list(missing),
                    "commands": list(commands)})

    # 0 brief ----------------------------------------------------------------------------------------------------
    found, missing, cmds = [], [], []
    if brief is None:
        missing.append(f"no brief (assets/models/{a}.brief.md)")
        cmds.append(f"lune run kit new asset {a}" if not f["script"] else
                    f"copy kit/templates/asset.brief.md to assets/models/{a}.brief.md, then ASK THE OWNER its "
                    "questions")
    else:
        if brief["unanswered"]:
            missing.append("unanswered: " + ", ".join(brief["unanswered"]))
            cmds.append(f"ASK THE OWNER the open questions in assets/models/{a}.brief.md and write their answers")
        absent = [q for q in P.QUESTIONS if q not in brief["answers"] and q not in brief["unanswered"]
                  and not (q == "hero_features" and brief.get("hero_features"))]
        # (literally nothing after the question and no list under it — an answer that opens with "(" or is a
        #  numbered list IS an answer, however the brief's reader files it)
        blank = [q for q in P.QUESTIONS if q != "hero_features" and q in brief["answers"]
                 and not str(brief["answers"][q]).strip() and not (f["brief_items"].get(q) or {}).get("list")
                 and _blank_line(q, f["brief_text"])]
        if blank:
            missing.append("left blank: " + ", ".join(blank))
            cmds.append(f"ASK THE OWNER: {', '.join(blank)} (assets/models/{a}.brief.md)")
        if absent:
            missing.append("questions the brief does not have: " + ", ".join(absent))
            cmds.append(f"add them from kit/templates/asset.brief.md to assets/models/{a}.brief.md and ASK THE OWNER")
        heroes = brief.get("hero_features") or []
        found.append(f"{len(heroes)} hero feature(s)")
        if big and not heroes and "hero_features" not in absent:
            missing.append("no hero features (what players notice first, each with its stack)")
        plan = f["parts_plan"] or []
        bad = P.route_problems(heroes) + stack_problems(plan)
        if bad:
            missing.append("stacks: " + "; ".join(f"{n}: {why}" for n, why in bad[:4]))
            cmds.append("give every hero feature and part its STACK — several modules, never one alone; sculpted / "
                        "organic forms are never code alone (parallax-3d skill, 'Which stack for which part')")
        # THE METHODS LOCK (the owner, 2026-11-13): a new piece's plan names the builder call each coded part is
        # made with - many alike are repeated or scattered, long curved forms swept or bent - and the build is
        # held to it (rbx_plan.methods_check). Pieces that existed before are exempt (board/locks.json).
        if plan and P.methods_locked(os.path.join(f["root"], "assets", "models", f"build_{a}.py"), f["root"],
                                     ROOT):
            how = P.method_problems(plan)
            if how:
                missing.append("methods: " + "; ".join(f"{n}: {why}" for n, why in how[:4]))
                cmds.append("name each coded part's METHOD in its parts plan line (the builder calls: a.repeat, "
                            "a.scatter, a.sweep, a.taper / a.twist / a.bend / a.conform, a.loop / a.inset / a.push "
                            "/ a.round, a.smooth, a.cad, a.loft ...) - parallax-3d reference/06, 'Which method for "
                            "which part'; the build is held to what the line names")
            else:
                found.append("methods: every coded part's line names how it is made")
        if plan:
            found.append(f"parts plan: {len(plan)} part(s), "
                         f"{sum(1 for p in plan if len(p['routes']) > 1)} with a multi-module shape")
            # THE GRAVEYARD: a route the owner's verdicts rejected is refused unless the line quotes them allowing it
            for name, g, words in graveyard_hits(plan, budget_tier(f), graveyard(f["root"])):
                if words:
                    found.append(f"{name}: graveyard {g['id']} route, the owner allowed it: \"{words[:60]}\"")
                else:
                    missing.append(f"graveyarded route — {name}: {g['id']} ({g['why'][:110]}; the owner: "
                                   f"{g['words'][:80]})")
                    cmds.append(f"change {name}'s route (kit/knowledge/vault/3d/routes.md {g['id']}: the method "
                                f"that worked) — or quote the owner on its line: | owner: \"<their words>\"")
        else:  # (every tier: the route per part is decided before any reference is gathered — 5.1)
            missing.append("no parts plan")
            cmds.append(f"write the parts plan in assets/models/{a}.brief.md: `- parts plan:` then one numbered line "
                        "per part — `<part> | <shape modules> | <data> | <surface>`: its STACK (parallax-3d skill, "
                        "'Which stack for which part')")
    stage("brief", DONE if not missing else (PARTIAL if brief else TODO), found, missing, cmds)

    # 1 gather ---------------------------------------------------------------------------------------------------
    found, missing, advised, cmds = [], [], [], []
    want = {"side"} | ({"front", "top"} if big else set())
    for w in ((brief or {}).get("view") or {}).get("sides") or []:
        if SIDE_OF.get(w):
            want.add(SIDE_OF[w])
    have = set(f["views"])
    found.append("traced views: " + (", ".join(f"{v} ({' + '.join(src)})" for v, src in sorted(f["views"].items()))
                                     or "none"))
    lacking = sorted(want - have)
    model_only = sorted(v for v in want & have if f["views"][v] == ["model"])
    if big and model_only and len(f["ref_models"]) < 2:
        # (one reference model is one author's reading — the Glock 17's scan was 7% short and nothing caught it: a
        #  view only it shows needs a photo, or a second model, to check it)
        missing.append("only ONE reference model shows: " + ", ".join(model_only) + " — trace a photo of each "
                       "(or measure a second model)")
        for v in model_only:
            cmds.append(f'lune run kit refs find "{obj} {v} view"  -> lune run kit trace <picture> --name {a}_photo_{v}'
                        f" --cutout")
    if lacking:
        (missing if big else advised).append("no traced " + ", ".join(lacking) + " view")
        for v in lacking:
            cmds.append(f'lune run kit refs find "{obj} {v} view"  -> kit refs rank / pick --as {a}_{v} -> '
                        f"lune run kit trace <the picked picture> --name {a}_{v} --cutout (+ --part-box per part)")
    found.append(f"reference models: {len(f['ref_models'])}" + (f" ({', '.join(f['ref_models'])})"
                                                                  if f["ref_models"] else ""))
    no_models = (((brief or {}).get("answers") or {}).get("reference_models") or "").strip()
    if big and len(f["ref_models"]) < 2 and not re.match(r"(?i)none\b", no_models):
        if not f["ref_models"]:
            missing.append("no reference model measured / inspected (or the brief's `- reference models: none — "
                           "<why>`)")
        else:
            advised.append("a second reference model to cross-check the first (one model can be wrong: a scan 7% "
                           "short)")
        cmds.append(f'lune run kit library find "{obj}"  -> kit library get <uid> -> lune run kit library inspect '
                    f"<uid> --name <ref> --length-mm <real length> -> lune run kit learn <ref> --category <kind>")
    pk = _d(f.get("pack"))
    pk_sizes, pk_colours = _d(pk.get("sizes")), _d(pk.get("colours"))
    obj_row = _d(pk.get("object"))
    try:
        length = float(obj_row.get("length_mm") or 0) or None
    except (TypeError, ValueError):
        length = None  # (a hand-edited pack: '186 mm' is no number)
    length_sourced = bool(length) and obj_row.get("trust") != "unsourced" and obj_row.get("source") not in (None, "",
                                                                                                          "given")
    sourced = {k: v for k, v in pk_sizes.items()
               if _d(v).get("trust") != "unsourced" and _d(v).get("source") not in (None, "", "given")}
    found.append(f"sourced sizes: {len(f['dims'])} cited, {len(sourced)} in the pack"
                 + (f" ({len(pk_sizes) - len(sourced)} UNSOURCED)" if len(pk_sizes) > len(sourced) else "")
                 + (f"; real length {length:g} mm" + ("" if length_sourced else " (UNSOURCED)") if length else ""))
    if not (f["dims"] or sourced or length_sourced):  # (every tier: a generic prop is sized from a source too — 5.2)
        missing.append("no sourced size (a dims:<id> cited, a size or the real length in the pack)")
        cmds.append(f'lune run kit refs dims find "{obj}"  -> lune run kit pack {a} object "{obj}" --length dims:<id> '
                    f"-> lune run kit pack {a} size <part.dim> dims:<id>")
    elif big and not length:
        advised.append("the pack has no real length (the scale every size hangs on)")
        cmds.append(f'lune run kit pack {a} object "{obj}" --length dims:<id> --category <kind>')
    # the DOSSIER: a real object's knowledge, graded and reviewed, approved by the owner before any shape (the Glock
    # 17's 204 mm was the Gen4's; its scan was 7% short; one side photo — nothing checked the input)
    real = str(obj_row.get("name") or "").strip()
    if real:
        ds = dossier_summary(real)
        named = is_named(real, obj_row.get("category"))
        if ds is None:
            (missing if big or named else advised).append(f"no dossier for '{real}': what is known about it, graded from its "
                                                 "sources and reviewed (kit dossier)")
            cmds.append(f'lune run kit dossier new "{real}" --category <pistol | rifle | generic> --maker-domain '
                        "<the maker's site>   then follow its research list")
        elif ds.get("error"):
            missing.append(f"the dossier for '{real}' could not be read: {ds['error']}")
        else:
            state = ("approved" + (" but STALE (changed since)" if ds["stale"] else "")) if ds["approved"] else \
                "not approved"
            found.append(f"dossier {ds['slug']}: {ds['score']:g}/100 (bar {ds['bar']:g}), {state}, "
                         f"{len(ds['open'])} open")
            if ds["problems"]:
                missing.append(f"the dossier's sources disagree: {ds['problems'][0]}")
            if not ds["approved"] or ds["stale"]:
                (missing if big or named else advised).append("the owner has not approved the dossier's reference sheet"
                                                              + (" (it changed since)" if ds["stale"] else ""))
                cmds.append(f'lune run kit dossier "{real}"   (its next step; when it is ready: kit dossier sheet, '
                            "the owner's yes, kit dossier approve)")
    cov = ((f["full"] or f["geo"] or {}).get("facts") or {}).get("coverage") or {}
    feats = [x for x in cov.get("features") or [] if x.get("hero", True)]
    low = [x.get("name", "?") for x in feats if x.get("low")]
    unmeasured = [x.get("name", "?") for x in feats if not x.get("low") and x.get("best_px_per_mm") is None]
    if low:
        missing.append(f"{len(low)} hero feature(s) under 2 px/mm: " + "; ".join(n[:40] for n in low[:3]))
    if big and unmeasured:
        missing.append(f"{len(unmeasured)} hero feature(s) with NO measured picture (px/mm unknown — the brief's "
                       f"feature line names no picture + box): " + "; ".join(n[:40] for n in unmeasured[:3]))
    if low or (big and unmeasured):
        cmds.append(f"lune run kit refs coverage {a} --parts --fetch 3   (each hero feature line: its picture + box; "
                    f"or ask the owner for close-ups)")
    if pk_colours:
        found.append(f"measured colours: {len(pk_colours)} part(s)")
    if big and not s["albedo"] and not pk_colours:
        missing.append("colours not measured (no part colours in the pack, no albedo= in a.trace_match)")
        pic = next((p for p in f["trace_pictures"].values() if p), f"refs/{a}_side.png")
        cmds.append(f"lune run kit vision albedo {pic} -o assets/models/{a}.albedo.npz   then   "
                    f"lune run kit pack {a} colours --trace <its trace>")
    if big and not f["spec"]:
        advised.append(f"no spec (refs/{a}.spec.json: the parts, what each is, what it attaches to)")
    # EVERY TRACE LOOKED AT (5.4): SAM leaks into neighbours, a whole-object mask stands in for a part, a 3/4 photo
    # traces "fine" — a trace is data only once someone looked at its sheet and said so in the pack
    unlooked = unlooked_traces(f)
    if unlooked:
        missing.append(f"{len(unlooked)} trace(s) never looked at: " + ", ".join(unlooked[:5]))
        for t in unlooked[:1]:  # (first in the list: the five-command cap must never drop a gate's own command)
            cmds.insert(0, f"LOOK at build/renders/{t}_trace.png (and its part crops), then lune run kit pack {a} looked "
                        f"{t} ok   (or: kit trace again, then looked {t} retraced)")
    # THE STUDY (the owner, 2026-10-28: gathered references were never deep-read): every reference read, our own
    # version decided, the vault lessons it applies cited — after everything above, so its command comes last
    sg = study_gate(f)
    if sg is not None:
        sprobs, sfacts = sg
        if sprobs:
            missing.append("reference study: " + sprobs[0])
            cmds.append(f"lune run kit study {a} --new   (once the references above are in)   then OPEN each one, write "
                        f"assets/models/{a}.study.md, lune run kit study {a}" if sprobs[0].startswith("no reference study")
                        else f"lune run kit study {a}   (fix: {sprobs[0][:120]})")
        else:
            found.append(f"study: {sfacts.get('refs', 0)} reference(s) read, {len(sfacts.get('lessons') or [])} "
                         "lesson(s) applied")
    # (advised gaps are shown and their commands given, but only the required ones hold the next stage back: an
    #  object can have no reference model anywhere)
    status = DONE if not missing else (PARTIAL if (have or f["ref_models"]) else TODO)
    stage("gather", status, found, missing + [f"(advised) {x}" for x in advised], cmds)

    # 2 sheet ----------------------------------------------------------------------------------------------------
    # THE MODEL SHEET (the owner, 2026-11-11: "A concept sheet we really need"): the views, a callout per hero
    # feature, the palette — what he approves before any shape, and what every later build is judged against
    sg2 = stage_gate(f, "sheet")
    if sg2 is None:
        stage("sheet", NOT_NEEDED, ["a prop, a piece started before the model sheet, or the owner waived it"])
    else:
        st, found, missing, cmds = sg2["state"], [], [], []
        if not st["exists"]:
            missing.append("no model sheet (the views, a callout per hero feature, the palette: what the owner "
                           "approves before any shape)")
            cmds.append(f"lune run kit sheet {a}   then LOOK at {st['png']} yourself and SHOW it to the owner")
        else:
            found.append(f"sheet {st['id']}")
            if st["stale"]:
                missing.append("the sheet is older than what it shows (the brief, a picture or a trace changed)")
                cmds.append(f"lune run kit sheet {a}   then show the owner again")
        if st["problems"]:
            missing.append(f"{len(st['problems'])} problem(s) hold the sheet: {st['problems'][0][:150]}")
            cmds.append(f"fix them in assets/models/{a}.brief.md (a picture + its box + its size per hero feature; "
                        f"a close-up where one is under 2 px/mm), then lune run kit sheet {a}")
        if st["exists"] and not st["stale"] and not st["problems"]:
            if sg2["approved"]:
                found.append(f"approved by the owner ({sg2['date']})")
            else:
                missing.append("the owner has not approved the model sheet"
                               + (" as it is now (it changed since their yes)" if sg2["changed"] else ""))
                cmds.append(f'SHOW {st["png"]} to the owner; their yes: lune run kit approve 3d {a} '
                            f'"<their words>" --by owner --stage sheet')
        found += [f"note: {n[:100]}" for n in st["notes"][:2]]
        stage("sheet", DONE if not missing else (PARTIAL if st["exists"] else TODO), found, missing, cmds)

    # 3 draft ----------------------------------------------------------------------------------------------------
    declared = f["draft_answer"].strip()
    if f["drafts"]:
        stage("draft", DONE, ["generated: " + ", ".join(f["drafts"][:4])])
    elif re.match(r"(?i)none\b", declared):
        stage("draft", DONE, [f"none, the brief says why: {declared[:80]}"])
    else:
        side = f["trace_pictures"].get("side") or f"refs/{a}_side.png"
        cmds = [f"lune run kit vision cutout <each view's picture> --rgba   then   lune run kit gen views {a}_draft "
                f"--view side=<side_rgba.png> --view front=<front_rgba.png> [--view top=...] [--ortho]",
                f"or from one big 3/4 picture: lune run kit gen {a}_draft --image <picture>   (sculpted parts: "
                f"lune run kit gen parts {a}_parts --image <picture> --parts <n>)",
                f"LOOK at it beside the references (kit vision similar <render> {side}); or write `- draft: none — "
                f"<why>` in the brief"]
        stage("draft", TODO if big else OPTIONAL, missing=["no generated 3D draft"], commands=cmds)

    # 4 blockout -------------------------------------------------------------------------------------------------
    # THE BLOCKOUT (the owner, 2026-11-11: "block[out] approval"): the big shapes in clay against the sheet — he
    # approves the proportions while changing them costs seconds; no detail, texture or bake before it
    bg = stage_gate(f, "blockout")
    if bg is None:
        stage("blockout", NOT_NEEDED, ["a prop, a piece started before the blockout approval, or the owner waived it"])
    else:
        st, found, missing, cmds = bg["state"], [], [], []
        if not f["script"]:
            missing.append(f"no build script (assets/models/build_{a}.py): the big shapes first — each part as its "
                           "simplest solid at the sheet's proportions, no detail")
            cmds.append(f"write assets/models/build_{a}.py as a BLOCKOUT (primitives / plain extrusions, one "
                        f"a.trace_match per traced view), then lune run kit blockout {a}")
        elif not st["exists"]:
            missing.append("no blockout sheet (the model in clay against the sheet's views: what the owner approves "
                           "before any detail)")
            cmds.append(f"lune run kit blockout {a}   (the shape round + its clay views: seconds), LOOK at "
                        f"{st['png']}, fix what is off, then SHOW it to the owner")
        else:
            found.append(f"blockout {st['id']}")
            if st["stale"]:
                missing.append("the model sheet changed since this blockout: a new target needs a new blockout")
                cmds.append(f"lune run kit blockout {a} --again   then show the owner")
            elif bg["approved"]:
                found.append(f"approved by the owner ({bg['date']})")
            else:
                missing.append("the owner has not approved the blockout"
                               + (" as it is now (it was drawn again since their yes)" if bg["changed"] else ""))
                cmds.append(f'SHOW {st["png"]} to the owner; their yes: lune run kit approve 3d {a} '
                            f'"<their words>" --by owner --stage blockout')
            found += [f"note: {n[:100]}" for n in st["notes"][:2]]
        stage("blockout", DONE if not missing else (PARTIAL if st["exists"] else TODO), found, missing, cmds)

    # 5 shape ----------------------------------------------------------------------------------------------------
    latest = max(((f["geo"], f["geo_t"]), (f["full"], f["full_t"])), key=lambda x: x[1] or 0)
    r, rt = latest
    found, missing, cmds = [], [], []
    if not f["script"]:
        stage("shape", TODO, missing=[f"no build script (assets/models/build_{a}.py)"],
              commands=[f"lune run kit new asset {a}"])
    elif r is None:
        if s["cad"]:
            cmds.append(f"lune run kit cad check {a}   (every a.cad part in seconds, no Blender)")
        cmds.append(f"lune run kit watch {a} --geo   (a persistent Blender: seconds on a light asset, minutes on a "
                    f"CAD-heavy hero — its CAD parts alone: kit cad check {a} --only <Part>)")
        stage("shape", TODO, [f"{s['cad']} a.cad call(s), {s.get('sculpts', 0)} sculpt(s), {len(s['imports'])} "
                              f"imported mesh(es)"],
              ["no build yet"], cmds)
    else:
        made = f"{s['cad']} a.cad call(s), {s.get('sculpts', 0)} sculpt(s), {len(s['imports'])} imported mesh(es)"
        found.append(f"{made}, {s['params']} a.param proportion(s) ({'fitted' if f['params_fitted'] else 'not fitted'})"
                     if s["params"] else f"{made}, no a.param proportions")
        views = (((r.get("facts") or {}).get("stage") or {}) or {}).get("views") or []
        if isinstance(views, list) and views:
            found.append("views: " + ", ".join(f"{v.get('view')} IoU {v.get('iou')}" for v in views))
            # (a hero's build holds detail back below the bar itself; a COMPLEX object — no script tier of its own —
            #  is held here: every traced view at its bar, or a.not_reference(<trace>, why=...) — 5.7)
            low = [v for v in views if isinstance(v, dict) and v.get("iou") is not None
                   and float(v["iou"]) < float(v.get("bar") or 0.9)]
            if budget_tier(f) == "complex" and low:
                missing.append("views below their bar: " + ", ".join(
                    f"{v.get('view')} IoU {float(v['iou']):.2f} < {float(v.get('bar') or 0.9):g}" for v in low))
                cmds.append(f"lune run kit fit {a} --write   (the references set the proportions) — or "
                            f"a.not_reference(\"<trace>\", why=\"...\") for a view that must not be matched")
        probs = _problems(r, "shape")
        if probs:
            missing.append("failing: " + ", ".join(probs[:8]))
            cmds.append(f"fix them in seconds: lune run kit cad check {a} / lune run kit watch {a} --geo — the "
                        f"verdict's next_action: {str(r.get('next_action') or '')[:160]}")
        read = (((r.get("facts") or {}).get("pack") or {}).get(a) or {}) if isinstance(r.get("facts"), dict) else {}
        if read.get("read"):
            found.append(f"reads {read['read']} value(s) from the pack ({', '.join(read.get('kinds') or [])})"
                         + (f", unsourced: {', '.join(read['unsourced'][:4])}" if read.get("unsourced") else ""))
        pk_file = _d(f.get("pack"))
        if pk_file and PK.inputs_sha(pk_file) != pk_file.get("inputs_sha"):
            missing.append(f"the pack was edited by hand since `kit pack` saved it: its checksum (part of the build's "
                           f"identity) is stale — lune run kit pack {a}")
            cmds.append(f"lune run kit pack {a}")
        pk = _d(f.get("pack"))
        if (pk.get("sizes") or pk.get("colours")) and not s["pack"]:
            missing.append("(advised) the pack has sizes / colours the build never reads (typed numbers instead)")
            cmds.append(f'pk = a.pack() in build_{a}.py: pk.size("<part.dim>"), pk.profile("<part>"), '
                        f'pk.colour("<part>") — never a number typed from memory')
        if big and not f["registered"]:
            missing.append("no traced view registered (a.trace_match): the outline is not measured")
            names = sorted(os.path.basename(p)[:-len(".trace.json")] for p in glob.glob(os.path.join(
                f["root"], "assets", "models", f"{a}_*.trace.json")))
            cmds.append(f'a.trace_match("<trace>", parts={{...}}) per traced view in build_{a}.py — its traces: '
                        + (", ".join(names[:6]) or "none yet (kit trace)"))
        # THE SHELL CHECK: a reference MODEL sliced beside the build, station by station (kit refs sections). The
        # Glock's frame read right from every side for days and was a SOLID extrusion where the real one is a U-shell
        # (the owner, 2026-10-10) — only its cross-sections showed it; they took it to 85/100
        sec, srcs = f.get("sections"), f.get("ref_sources") or {}
        if sec:
            found.append(f"cross-sections vs {sec['ref']}: {sec['stations']} stations"
                         + (f", worst p90 {sec['worst_p90']} mm" if sec["worst_p90"] is not None else
                            " (none measured: the cut found no overlap)")
                         + (f", {sec['over']} over 1.5 mm" if sec["over"] else ""))
            if sec["over"]:
                missing.append(f"(advised) {sec['over']} cross-section station(s) over 1.5 mm from the reference model")
                cmds.append(f"LOOK at build/refs/{a}_sections.png (red the reference, blue ours): fix that part's "
                            f"shape, then lune run kit refs sections {a} --ref {sec['ref']}")
            if rt and sec["t"] and rt > sec["t"]:
                missing.append("(advised) the cross-sections are older than the last build")
                cmds.append(f"lune run kit refs sections {a} --ref {sec['ref']}")
        elif big and srcs:
            name, src = sorted(srcs.items())[0]
            missing.append(f"never cut beside its reference model ({name}): a part solid where the real one is a "
                           f"shell, a lip or a groove missing, reads right from outside")
            cmds.append(f"lune run kit refs sections {a} --ref {src}   (add --flip if the model faces the other way; "
                        "--ref-hide <object> for an accessory on it)")
        if s["params"] and not f["params_fitted"]:
            missing.append(f"{s['params']} a.param() proportion(s) never fitted")
            sec = float((f["geo"] or {}).get("seconds") or 0)
            if sec > 60:  # one fit evaluation = one --geo build: 120 of them on a slow build is hours
                cmds.append(f"lune run kit fit {a} --only <the 2-4 proportions that matter> --evals 24 --write   (one "
                            f"--geo build takes {sec:.0f} s here: the default 120 evaluations would take "
                            f"{120 * sec / 3600:.1f} h)")
            else:
                cmds.append(f"lune run kit fit {a} --write   (the references decide them, not hand nudges)")
        if f["script_t"] and rt and f["script_t"] > rt:
            missing.append("the script changed since the last build")
            cmds.append(f"lune run kit watch {a} --geo")
        real = [m for m in missing if not m.startswith("(advised)")]
        stage("shape", DONE if not real else PARTIAL, found, missing, cmds)

    # 6 surface --------------------------------------------------------------------------------------------------
    found, missing, cmds = [], [], []
    mats, data = s["materials"], s["materials_from_data"]
    found.append(f"materials: {len(mats)} ({len(data)} from data: finish / real / scan), {s['patterns']} pattern(s), "
                 f"{s['markings']} marking(s) ({s['engraved']} engraved)")
    tools = [f"{k} {n}" for k, n in s["surface_tools"].items() if n]
    if tools:
        found.append("surface tools: " + ", ".join(tools))
    plain = [m for m in mats if m not in data]
    if big and plain:
        missing.append("(advised) materials not from data: " + ", ".join(plain[:6]))
        cmds.append("give each its real recipe: **rbx.look(\"...\") (a whole surface: values, scan, pattern, "
                    "variation — lune run kit materials --looks) / **rbx.finish(\"...\") / **rbx.real(\"...\") / "
                    "scan=, at the colour kit vision albedo + kit refs colour measured")
    if big and mats and not s.get("materials_worn"):
        missing.append("(advised) no material has a life: every surface as it left the factory")
        cmds.append("a.material(..., life=\"used\") (new · light · used · heavy: the wear its class gets — edges "
                    "burnished on a dark finish, chips on paint, dirt and handling on wood; the owner rated the "
                    "Glock's \"used\")")
    if big and not s["markings"]:
        missing.append("(advised) no markings")
        cmds.append("engrave each marking at its measured place: a.cut(<part>, a.text(..., \"engraving\", depth=...))")
    if f["full"] is None:
        missing.append("no full (baked) build yet: the surface is not measured")
        cmds.append(f"lune run kit asset {a}")
        stage("surface", TODO if not mats else PARTIAL, found, missing, cmds)
    else:
        probs = _problems(f["full"], "surface", warnings=True)
        if probs:
            missing.append("failing: " + ", ".join(probs[:8]))
        if f["script_t"] and f["full_t"] and f["script_t"] > f["full_t"]:
            missing.append("the script changed since the last full build")
            cmds.append(f"lune run kit asset {a}")
        real = [m for m in missing if not m.startswith("(advised)")]
        stage("surface", DONE if not real else PARTIAL, found, missing, cmds)

    # 7 mechanism ------------------------------------------------------------------------------------------------
    answers = (brief or {}).get("answers") or {}
    listed = [x for x in ((f["brief_items"].get("moving_parts") or {}).get("list") or []) if x.strip()]
    line = _raw_answer("moving_parts", f["brief_text"])  # (the question's own line, help cut)
    answer = _answer_text("moving_parts", f["brief_text"], line)  # (that line + its own wrapped lines)
    lead_in = not line or line.rstrip().endswith(":") or (
        not re.search(r"[(),;]", line) and len(line.split()) <= 4 and bool(listed))  # ('see below', 'yes')
    if line and moving_parts(line) == []:
        moving = []  # ('- moving parts: none' — anything listed under it is a note)
    elif listed and lead_in:
        # one part per item (an item's own commas, a wrapped tail are its own); a lone 'none' item is none
        moving = [] if len(listed) == 1 and moving_parts(listed[0]) == [] else listed
    else:
        moving = moving_parts(answer) if answer else None  # (bullets under an answer that names parts are notes)
    function = (answers.get("function") or "").lower()
    if re.match(r"\W*static\b", function) and not re.search(r"\bmov|\bworks?\b|take[- ]?apart", function):
        moving = []  # (the brief's FUNCTION — a fixed choice: static · the main parts move · everything works)
    takeapart = bool(re.search(r"take[- ]?apart|disassembl|field[- ]?strip|comes? apart", function))
    r = f["full"] if (f["full_t"] or 0) >= (f["geo_t"] or 0) else f["geo"]
    mech = ((r or {}).get("facts") or {}).get("mechanism")
    built = sorted({str(k).split("@")[0] for k in mech}) if isinstance(mech, dict) and mech else None
    joints = len(built) if built is not None else s["joints"]
    said = f"{len(built)} jointed part(s) in the last build" if built is not None else f"{s['joints']} a.joint call(s)"
    found = [f"{said}, take-apart: {'declared' if s['disassembly'] else 'none'}",
             "moving parts read as: " + ("not said" if moving is None else "none" if not moving else
                                         f"{len(moving)}: " + "; ".join(m[:40] for m in moving[:8])
                                         + (f" (+{len(moving) - 8} more)" if len(moving) > 8 else ""))]
    missing, cmds = [], []
    if (moving == [] or (brief is None and not big)) and not takeapart and not s["joints"]:
        stage("mechanism", NOT_NEEDED, ["the brief: no moving parts" if brief else "no brief, no joints (a prop)"])
    else:
        if moving and not joints:
            # (a FACT, not a count: the brief says something moves and the build has no joint at all)
            missing.append(f"the brief names moving parts and the build has no joint: " + "; ".join(moving[:5]))
            cmds.append('a.joint("<Part>", "<group>", "slide" | "hinge", axis=..., max=...) for each moving part')
        elif moving and joints < len(moving):
            # (ADVISED: a count read from free text is a hint, never a gate — 'read as' above says how it was read)
            missing.append(f"(advised) the brief names {len(moving)} moving part(s), {said} — check the parts "
                           f"'read as' above: " + "; ".join(moving[:5]))
            cmds.append('a.joint("<Part>", "<group>", "slide" | "hinge", axis=..., max=...) for each moving part')
        if takeapart and not s["disassembly"]:
            missing.append("the brief wants it to come apart: no a.disassembly")
            cmds.append("a.disassembly([...]) down to the screws (parallax-3d skill, the mechanism stage)")
        probs = _problems(r, "mechanism")
        if probs:
            missing.append("failing: " + ", ".join(probs))
        if moving is None and not s["joints"] and not takeapart:
            missing.append("the brief does not say what moves")
        rt = f["full_t"] if (f["full_t"] or 0) >= (f["geo_t"] or 0) else f["geo_t"]
        if r is not None and f["script_t"] and rt and f["script_t"] > rt:
            missing.append("the script changed since the last build: the joints above are the old build's")
        real = [m for m in missing if not m.startswith("(advised)")]
        status = DONE if not real else (PARTIAL if s["joints"] or s["disassembly"] else TODO)
        if status != DONE:
            cmds.append(f"lune run kit watch {a} --geo   then   lune run kit asset {a} --schematic   and   "
                        f"lune run kit schematic {a}")
        stage("mechanism", status, found, missing, cmds)

    # 8 look and judge -------------------------------------------------------------------------------------------
    found, missing, cmds = [], [], []
    full, ft = f["full"], f["full_t"]
    if full is None:
        stage("look", TODO, missing=["no full build to look at"],
              commands=[f"lune run kit asset {a}   then LOOK at build/renders/{a}.png beside the references"])
    else:
        found.append(f"last full build: {str(full.get('status'))} — {str(full.get('summary') or '')[:90]}")
        if f["script_t"] and ft and f["script_t"] > ft:
            missing.append("the script changed since the last full build")
        others = _other_errors(full)
        if others:
            missing.append("failing: " + ", ".join(others[:8]))
        if f["part_fixes"]:
            missing.append(f"{f['part_fixes']} part answer(s) say `verdict: fix`")
        if big:
            if not (f["judge_t"] and ft and f["judge_t"] >= ft):
                missing.append("no verifier round on this build")
                cmds.append(f"lune run kit judge {a}   -> a FRESH verifier (never the builder): one difference per "
                            f"view, ONE edit -> lune run kit judge {a} --record")
            if not f["review"]:
                missing.append(f"no review (assets/models/{a}.review.md)")
        cmds.insert(0, f"LOOK at build/renders/{a}.png beside the reference pictures (and lune run kit vision differ "
                       f"<render> <photo>) — the score counts parts, never the look")
        stage("look", DONE if not missing else PARTIAL, found, missing, cmds)

    # 9 present --------------------------------------------------------------------------------------------------
    if f["showcase_t"] and ft and f["showcase_t"] >= ft:
        stage("present", DONE, ["build/showcase/" + a + "/poster.png"])
    else:
        stage("present", TODO if big else OPTIONAL, missing=["no showcase of the last full build"],
              commands=[f"lune run kit showcase {a}"])
    return out


# ============================================================================== THE CLOCK AND THE LOCKS
# the owner's hard budgets (2026-10-09, "NO MORE 10 HOUR MODELS"): 10 minutes a prop, 30 a complex object, 60 a hero —
# at the budget the kit STOPS: render, look, show the owner; only the owner's words extend it
BUDGET_MIN = {"prop": 10, "complex": 30, "hero": 60, "aaa": 60}
MAX_EXTEND_MIN = 120  # (one extension: the owner says how long; never an open-ended clock)
MAX_COMMANDS = 5  # per stage: a long menu is the measured failure mode (tool-selection accuracy collapses with count)


def budget_tier(f):
    """the tier the clock runs on: the brief's quality answer names it (prop / complex / hero / aaa), else the
    script's quality="""
    said = str((((f.get("brief") or {}).get("answers") or {}).get("quality")) or "").lower()
    m = re.search(r"\b(prop|complex|hero|aaa)\b", said)
    return m.group(1) if m else f["s"]["tier"]


def _minutes(v):
    """an extension's minutes, or 0 when it is no finite number in 0..MAX_EXTEND_MIN (a hand-edited NaN / inf would
    switch the budget off for good)"""
    try:
        m = float(v)
    except (TypeError, ValueError):
        return 0.0
    return m if math.isfinite(m) and 0 < m <= MAX_EXTEND_MIN else 0.0


def clock_path(asset, root):
    return os.path.join(root, "assets", "models", f"{asset}.clock.json")


def read_clock(f, now=None):
    """the asset's clock (assets/models/<asset>.clock.json, started by its first `kit plan`) -> {started, tier,
    budget_min, extended_min, elapsed_min, left_min, over, extensions} or None when it never started"""
    c = _read(clock_path(f["asset"], f["root"]))
    try:
        c = json.loads(c) if c else None
    except ValueError:
        c = None
    if not isinstance(c, dict) or not isinstance(c.get("started"), (int, float)):
        return None
    # (the tier the attempt STARTED on: a brief edited mid-attempt - prop to aaa - never lifts its STOP)
    tier = c.get("tier") if c.get("tier") in BUDGET_MIN else budget_tier(f)
    ext = [e for e in c.get("extensions") or [] if isinstance(e, dict)]
    extra = sum(m for m in (_minutes(e.get("minutes")) for e in ext))
    budget = BUDGET_MIN.get(tier, 10)
    t = now or time.time()
    start = float(c["started"])
    deadline = clock_deadline(start, budget, ext)
    return {"started": start, "tier": tier, "budget_min": budget, "extended_min": extra,
            "elapsed_min": round(max(0.0, (t - start) / 60.0), 1), "left_min": round((deadline - t) / 60.0, 1),
            "over": t > deadline, "extensions": ext, "attempt": int(c.get("attempt") or 1)}


def clock_deadline(start, budget_min, extensions):
    """when the budget runs out: the tier's minutes from the first build, then each of the owner's extensions in the
    order he gave them - added to the deadline when given before it, counted FROM the moment he gives it when the clock
    had already run out (his "30 more minutes" after a wait for his verdict is 30 minutes of building, never minutes the
    wait already spent - the owner's budgets are build time; 2026-11-11, the revolver's extension was eaten by the wait)"""
    deadline = start + budget_min * 60.0
    timed = sorted((e for e in extensions if isinstance(e, dict)), key=lambda e: float(e.get("at") or 0))
    for e in timed:
        at = e.get("at")
        base = max(deadline, float(at)) if isinstance(at, (int, float)) else deadline
        deadline = base + _minutes(e.get("minutes")) * 60.0
    return deadline


def write_clock(f, extend=None, words=None, restart=False, now=None):
    """start the clock (first plan), extend it (the owner's minutes + words) or restart it (a new attempt: a new
    build id, the owner's words) -> the clock"""
    path = clock_path(f["asset"], f["root"])
    old = _read(path)
    try:
        c = json.loads(old) if old else {}
    except ValueError:
        c = {}
    now = now or time.time()
    if not isinstance(c, dict) or not isinstance(c.get("started"), (int, float)):
        c = {"started": now, "attempt": 1, "extensions": []}
    if restart:
        c = {"started": now, "attempt": int(c.get("attempt") or 1) + 1, "extensions": [],
             "restarted": {"words": words, "at": now}}
    if extend:
        c.setdefault("extensions", []).append({"minutes": float(extend), "words": words, "at": now})
    if restart or c.get("tier") not in BUDGET_MIN:  # (frozen for the attempt: set when it starts, kept by an extension)
        c["tier"] = budget_tier(f)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(c, fh, indent=1)
        fh.write("\n")
    return read_clock(f, now)


def stop_commands(a):
    return [f"lune run kit look sheet {a}   (render what there is - kit asset builds nothing past the budget)",
            f"LOOK at build/renders/{a}.png beside the references",
            f"show the owner: add it to board/plans/missions/pending/3d.md (render, references, the clock, "
            f"'0-10 and words?')",
            f'only the owner extends it: lune run kit plan {a} --extend <minutes> "<their words>"']


BUILD_CLOCK_FROM = 1794312699  # (2026-11-10 16:11 AST: the budget reaches kit asset; an attempt older than this that
#  ran out gets ONE fresh attempt at its next build - 50 clocks were past their budgets the day it shipped)
CARD_STOP = {"the", "and", "for", "with", "old", "new", "set", "kit", "one", "two", "big", "small"}


def open_cards(asset, root, limit=6):
    """the board's open cards about this piece (its name, or two of its words, in a card's title or goal) ->
    [(id, status, title)]; a one-word name matches only itself"""
    name = asset.lower()
    keys = [w for w in re.split(r"[_\W]+", name) if len(w) >= 3 and w not in CARD_STOP]
    out = []
    for fn in sorted(glob.glob(os.path.join(root, "board", "tasks", "*.md"))):
        text = _read(fn) or ""
        head = text[:3000]
        st = re.search(r"(?m)^status:\s*(\S+)", head)
        status = st.group(1).strip().strip('"') if st else "?"
        if status in ("done", "dropped", "closed"):
            continue
        title = re.search(r'(?m)^title:\s*"?(.*?)"?\s*$', head)
        goal = re.search(r"(?s)## Goal\s*(.*?)(?=\n## |\Z)", text)
        hay = " ".join(x.group(1) for x in (title, goal) if x).lower()
        hits = sum(1 for w in keys if re.search(rf"\b{re.escape(w)}\b", hay))
        named = any(re.search(rf"\b{re.escape(n)}\b", hay) for n in {name, name.replace("_", " ")})
        if named or (len(keys) >= 2 and hits >= 2):
            tid = re.search(r"(?m)^id:\s*(\S+)", head)
            out.append((tid.group(1) if tid else os.path.basename(fn)[:4], status, (title.group(1) if title else "")))
    return out[:limit]


def prebuild_facts(asset, root):
    """the little the pre-build check needs - the brief's quality and the script's tier - never the whole facts()"""
    models = os.path.join(root, "assets", "models")
    script, brief_text = _read(os.path.join(models, f"build_{asset}.py")), _read(os.path.join(models, f"{asset}.brief.md"))
    try:
        brief = P.parse_brief(brief_text) if brief_text else None
    except Exception:  # noqa: BLE001  (a brief that does not parse: the script's tier decides)
        brief = None
    try:
        s = read_script(script or "")
    except Exception:  # noqa: BLE001
        s = {"tier": "prop"}
    return {"asset": asset, "root": root, "brief": brief, "s": s}


def prebuild(f, now=None, use_clock=True):
    """`kit asset` / `kit optimize` ask this before every build -> (stop, summary, next_action, lines). No build past the
    piece's time budget (the owner, 2026-11-10: the car rim's rework ran 26 builds in 4.5 hours on a 10-minute clock
    that only kit plan read - the budget stops the BUILD now), and none on a route its study's lessons were not
    answered for (kit/tools/study.py route_gate)"""
    import study as ST  # noqa: PLC0415  (it imports this module back)

    a, root = f["asset"], f["root"]
    now = now or time.time()
    # THE METHODS LOCK holds a new piece's build to its parts plan (rbx_plan.methods_check): with no brief, or a brief
    # with no parts plan, there was nothing to hold it to and only the typed-alike check ran at build (card 988z, the
    # lock's review: "kit plan says the plan is missing, the pre-build step does not block on it"). First, so a
    # refused build starts no clock.
    script = os.path.join(root, "assets", "models", f"build_{a}.py")
    if P.methods_locked(script, root, ROOT):
        brief_path = os.path.join(root, "assets", "models", f"{a}.brief.md")
        brief_text = _read(brief_path)
        if not brief_text or not parts_plan(brief_text):
            what = "no brief" if not brief_text else "a brief with no parts plan"
            lines = [f"STOP — METHODS: {a} is a new piece with {what}: the methods lock holds its build to the plan "
                     "that names each coded part's builder call",
                     f"  write the parts plan in assets/models/{a}.brief.md (`- parts plan:` then one numbered line a "
                     "part: `<part> | <shape modules + the builder call> | <data> | <surface>`), then lune run kit "
                     f"plan {a}",
                     f'  only the owner waives it: lune run kit approve 3d {a} "<their words>" --by owner --waive methods']
            return (True, f"asset {a}: STOP — METHODS: a new piece with {what}, so nothing holds its build to a plan",
                    f"write its parts plan in assets/models/{a}.brief.md (parallax-3d reference/06, 'Which method for "
                    f"which part'), then lune run kit plan {a}", lines)
    # (use_clock False: kit asset all - a maintenance rebuild of every piece, no way to work one piece over and over:
    # it reads no clock, starts none, spends no fresh attempt; the route check still holds)
    clock, note = (read_clock(f, now) if use_clock else None), []
    ran_out = (clock["started"] + (clock["budget_min"] + clock["extended_min"]) * 60) if clock else None
    try:
        if not use_clock:
            pass
        elif clock is None:  # (no kit plan ran: the clock starts at the first build - never an unclocked piece)
            clock = write_clock(f, now=now)
            note.append(f"clock started: {clock['budget_min']:g} min ({clock['tier']})")
        elif clock["over"] and ran_out < BUILD_CLOCK_FROM:
            # (an attempt that RAN OUT before the budget reached the build: one fresh attempt, never a wall on day one;
            # the old clock - the owner's minutes and words - kept under "previous")
            try:
                old = json.loads(_read(clock_path(a, root)) or "{}")
            except ValueError:
                old = {}
            with open(clock_path(a, root), "w", encoding="utf-8") as fh:
                json.dump({"started": now, "attempt": clock["attempt"] + 1, "extensions": [],
                           "fresh": {"at": now, "why": "the budget reached kit asset (2026-11-10): one fresh attempt "
                                     "for a piece whose last ran out before it"}, "tier": clock["tier"],
                           "previous": old}, fh, indent=1)
                fh.write("\n")
            clock = read_clock(f, now)
            note.append(f"a fresh attempt {clock['attempt']}: {clock['budget_min']:g} min ({clock['tier']}) - its last "
                        "ran out before the budget reached the build")
    except OSError as e:  # (a locked clock file is no reason to refuse a build: it is tried again at the next one)
        note.append(f"its clock could not be written ({type(e).__name__}): the next build tries again")
    if clock and clock["over"]:
        spent = (f"{clock['elapsed_min']:g} of {clock['budget_min']:g}"
                 + (f"+{clock['extended_min']:g}" if clock["extended_min"] else "")
                 + f" min ({clock['tier']}, attempt {clock['attempt']})")
        lines = [f"STOP — BUDGET: {spent}: no build of {a} past its budget", "what there is (show the owner):"]
        have = [p for p in (f"build/models/{a}.blend", f"build/renders/{a}.png") if os.path.isfile(os.path.join(root, p))]
        lines += [f"  - {p}" + ("  (open it in Blender for him: Material Preview)" if p.endswith(".blend") else "")
                  for p in have] or ["  - no build yet: say so"]
        cards = open_cards(a, root)
        lines.append("still open about it:")
        lines += [f"  - {i} ({s}): {t[:100]}" for i, s, t in cards] or ["  - no open card names it"]
        lines += ["only his words reopen it:",
                  f'  - more time on this attempt: lune run kit plan {a} --extend <minutes> "<his words>"',
                  f'  - a new attempt: lune run kit plan {a} --restart "<his words>"']
        return (True, f"asset {a}: STOP — BUDGET: {spent}: no build past the budget",
                "show the owner what there is and what is still open (listed above); only his words reopen it: "
                f'lune run kit plan {a} --extend <minutes> "<his words>" (or --restart "<his words>": a new attempt)',
                lines)
    changed = ST.route_gate(a, root)
    if changed:
        was, nowr = (ST.route_text(r) for r in changed)
        lines = [f"STOP — ROUTE: {a} is built a new way ({was} -> {nowr}) since its study's lessons were answered",
                 "  its answers were written for the old route: each matched lesson is asked again, for the new one",
                 f"  lune run kit study {a} --reroute   (the old answers kept to read; copying one does not count)"]
        return (True, f"asset {a}: STOP — ROUTE changed ({was} -> {nowr}) since its lessons were answered",
                f"lune run kit study {a} --reroute, answer each lesson for the new route, then build", lines)
    study = _read(ST.study_path(a, root)) or ""
    stubs = "<answer>" in "\n".join(ST._section(study, "lessons applied") or [])
    if re.search(r"(?im)^##\s+earlier answers", study) or stubs:
        # (rerouted: its new route's lessons must be ANSWERED before a build - kit optimize, a grandfathered or waived
        # piece have no quality lock to ask it)
        owed = [p for p in ST.check(a, root)[0] if p.startswith("lessons applied")]
        if owed:
            return (True, f"asset {a}: STOP — its new route's lessons are not answered yet: {owed[0]}",
                    f"answer each lesson under Lessons applied for the new route, then lune run kit study {a}",
                    [f"STOP — {p}" for p in owed])
    try:
        ST.stamp_route(a, root)  # (an unstamped study takes the route it passed with: a later change is caught)
    except OSError as e:  # (a locked study is no reason to refuse a build: the stamp waits for the next one)
        note.append(f"its study could not be stamped with its route ({type(e).__name__}): the next build tries again")
    left = (f"{clock['left_min']:g} min left of its budget" if clock else
            "no clock read (a maintenance rebuild)" if not use_clock else "its clock unread")
    return False, f"asset {a}: {left}, its lessons answered for its route", "build", note


EXTERIOR_FIRST = ("brief", "gather", "sheet", "draft", "blockout", "shape", "surface", "look", "mechanism", "present")


def lock(stages, clock=None, exterior_first=False):
    """stage locks: every stage after the first one not done is LOCKED by it (one planned pass: a later stage's work
    on a missing earlier artifact is the rebuild loop); past the budget everything is locked but the look — render,
    look, show the owner. exterior_first (a hero): the mechanism waits for the look — the outside passes the owner's
    eye before any internal (the Glock's effort went where nobody looks; 5.9). Marks st['locked'] (why) in place;
    -> the stop reason or None"""
    blocker = None
    by_key = {st["key"]: (i, st) for i, st in enumerate(stages)}
    order = [by_key[k] for k in EXTERIOR_FIRST if k in by_key] if exterior_first else list(enumerate(stages))
    for i, st in order:
        if blocker is not None:
            st["locked"] = blocker
        elif st["status"] in (TODO, PARTIAL):
            first = next((m for m in st["missing"] if not m.startswith("(advised)")), None) or \
                (st["missing"][0] if st["missing"] else st["status"])
            blocker = f"stage {i} {st['title'].lower()} is not done: {first}"
            if exterior_first and st["key"] == "mechanism":
                blocker = f"stage {i} mechanism is not done (exterior first: after the look): {first}"
    if clock and clock["over"]:
        why = (f"BUDGET: {clock['elapsed_min']:g} of {clock['budget_min']:g}"
               + (f"+{clock['extended_min']:g}" if clock["extended_min"] else "")
               + f" min ({clock['tier']}) — the kit stops: render, look, show the owner")
        for st in stages:
            if st["key"] != "look":
                st["locked"] = why
            else:
                st.pop("locked", None)  # (the look is the one stage open at the budget: render, look, show the owner)
        return why
    return None


def next_stage(stages):
    """the first stage not done that no earlier stage locks (a hero's look comes before its mechanism)"""
    return next((st for st in stages if st["status"] in (TODO, PARTIAL) and not st.get("locked")), None)


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(json.dumps({"schema": 1, "status": "fail", "summary": "plan: needs an asset name",
                          "next_action": "lune run kit plan <asset>"}))
        return 2
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # (the dashes and arrows print on a Windows console too)
    except (AttributeError, ValueError):
        pass
    asset = argv[0]
    root = ROOT
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv):
            print(json.dumps({"schema": 1, "status": "fail", "summary": "plan: --root needs a folder",
                              "next_action": "lune run kit plan <asset> [--root <project folder>]"}))
            return 2
        root = os.path.abspath(argv[i + 1])
    if "--prebuild" in argv:  # (kit asset / kit optimize, before every build: the clock, then the route)
        stop, summary, action, lines = prebuild(prebuild_facts(asset, root), use_clock="--no-clock" not in argv)
        for ln in lines:
            print(ln)
        print(json.dumps({"schema": 1, "status": "fail" if stop else "pass", "summary": summary, "next_action": action}))
        return 1 if stop else 0
    f = facts(asset, root)
    if not f["script"] and not f["brief"]:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"plan: no asset '{asset}' (no build script, "
                          "no brief)", "next_action": f"lune run kit new asset {asset}"}))
        return 1
    def opt(flag):
        if flag not in argv:
            return None
        k = argv.index(flag)
        return argv[k + 1] if k + 1 < len(argv) and not argv[k + 1].startswith("--") else ""

    def fail(summary, action, code=1, **extra):
        print(json.dumps({"schema": 1, "status": "fail", "summary": summary, "next_action": action, **extra}))
        return code


    extend, restart, want = opt("--extend"), opt("--restart"), opt("--stage")
    # the owner's words: ONLY the argument right after --extend's minutes (never another flag's value)
    k = argv.index("--extend") if "--extend" in argv else -1
    words = argv[k + 2] if k >= 0 and k + 2 < len(argv) and not argv[k + 2].startswith("--") else None
    if extend is not None or restart is not None:
        # (only the owner moves the clock: their words are kept beside it — assets/models/<asset>.clock.json)
        said = (restart if restart is not None else words) or ""
        mins = None
        if extend is not None:
            try:
                mins = float(extend)
            except ValueError:
                mins = 0.0
            if not (math.isfinite(mins) and 0 < mins <= MAX_EXTEND_MIN) or not words:
                return fail(f"plan --extend: needs the minutes (over 0, at most {MAX_EXTEND_MIN}) and the owner's words",
                            f'lune run kit plan {asset} --extend 10 "<the owner words>"', 2)
        if restart is not None and not said:
            return fail("plan --restart: needs the owner's words (a new attempt is a new build id)",
                        f'lune run kit plan {asset} --restart "<the owner words>"', 2)
        write_clock(f, extend=mins, words=said, restart=restart is not None)
    stages = assess(f)
    clock = read_clock(f)
    if clock is None and stages[0]["status"] == DONE:
        clock = write_clock(f)  # (the clock starts once the brief is done: the owner's answering time is not the build's)
    stop = lock(stages, clock, exterior_first=budget_tier(f) in ("hero", "aaa"))
    for st in stages:
        st["more_commands"] = max(0, len(st["commands"]) - MAX_COMMANDS)
        st["commands"] = st["commands"][:MAX_COMMANDS]
    s = f["s"]
    ck = ("clock not started (it starts when the brief is done)" if clock is None else
          f"clock {clock['elapsed_min']:g} / {clock['budget_min']:g}"
          + (f"+{clock['extended_min']:g}" if clock["extended_min"] else "") + f" min ({clock['tier']}"
          + (f", attempt {clock['attempt']}" if clock["attempt"] > 1 else "") + ")")
    print(f"plan {asset} — {s['tier']}{' master' if s['master'] else ''}{' private' if s['private'] else ''}"
          f"  {ck}  (the 10 stages: kit/skills/parallax-3d/SKILL.md)")
    for i, st in enumerate(stages):
        mark = "  LOCKED" if st.get("locked") and st["status"] in (TODO, PARTIAL) else ""
        print(f"  {i} {st['title']:<15} {st['status'].upper():<11}{mark} {'; '.join(st['found'])}")
        for m in st["missing"]:
            print(f"  {'':<28}- {m}")
    keys = [st["key"] for st in stages]
    if want is not None:
        # `kit plan <asset> --stage <key>`: the one way into a stage — refused while an earlier one is not done
        if want not in keys:
            return fail(f"plan {asset}: no stage '{want}'", "one of: " + " ".join(keys), 2, clock=clock)
        st = stages[keys.index(want)]
        if st.get("locked"):
            blocker = next((x for x in stages if x["status"] in (TODO, PARTIAL) and not x.get("locked")), None)
            cmds = stop_commands(asset) if stop else (blocker or {}).get("commands") or []
            print(f"\nREFUSED — stage {keys.index(want)} {st['title']} is LOCKED: {st['locked']}")
            for c in cmds[:MAX_COMMANDS]:
                print(f"  {c}")
            return fail(f"plan {asset}: stage {want} refused — {st['locked']}",
                        (cmds[0] if cmds else st["locked"]), 1, stages=stages, clock=clock, locked=st["locked"],
                        commands=cmds[:MAX_COMMANDS])
        print(f"\nstage {keys.index(want)} {st['title']} ({st['status']}):")
        cmds = (stop_commands(asset) if stop else st["commands"]) or ["(nothing to do: it is done)"]
        for c in cmds:
            print(f"  {c}")
        return emit_pass(f"plan {asset}: stage {want} open ({st['status']}); {ck}", cmds[0], stages, clock,
                         open=want, commands=cmds)
    if stop:
        print(f"\nSTOP — {stop}:")
        for c in stop_commands(asset):
            print(f"  {c}")
        return emit_pass(f"plan {asset}: STOP — {stop}", stop_commands(asset)[0] + " | " + stop_commands(asset)[2],
                         stages, clock, stop=stop, commands=stop_commands(asset))
    nxt = next_stage(stages)
    if nxt is None:
        summary = f"plan {asset}: every stage done"
        action = f"LOOK at build/showcase/{asset}/poster.png with the owner; the game version only when they ask"
    else:
        i = stages.index(nxt)
        summary = (f"plan {asset}: next is stage {i} {nxt['title'].lower()} ({nxt['status']}); {ck}; "
                   + ", ".join(f"{st['key']} {st['status']}" for st in stages))
        print(f"\nnext — stage {i} {nxt['title']}  ({ck}; later stages LOCKED until it is done):")
        for c in nxt["commands"] or ["(see the stage in the parallax-3d skill)"]:
            print(f"  {c}")
        action = f"stage {i} {nxt['title'].lower()}: " + " | ".join(nxt["commands"][:3] or [nxt["missing"][0]])
    return emit_pass(summary, action, stages, clock, commands=(nxt or {}).get("commands") or [])


def emit_pass(summary, action, stages, clock, **extra):
    print(json.dumps({"schema": 1, "status": "pass", "summary": summary, "next_action": action, "stages": stages,
                      "clock": clock, **extra}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
