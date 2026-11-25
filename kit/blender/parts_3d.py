"""parts_3d.py - the 3D lane's adapter for the parts libraries (kit/tools/parts.py; board/plans/
2026-11-09-parts-libraries-plan.md, P0). A 3D part has kinds on four axes - its FORM (turned, copies round a circle,
extruded, hollow, cut holes...), its ROLE (hub, spoke, rim, lip, fastener, grip...), its FINISH (machined, cast, wood...)
and its JOIN (welded, pinned, bolted, press fit) - and the code that made it. P0 files, each card with its kinds:
  - every builder's named part families (assets/models/build_*.py, games/*/assets/models/build_*.py): the call that
    makes each (a.cad / a.cylinder / a.tube / P.bolts ...) with the loop around it, so a stave loop placing copies by
    angle reads as "copies round a circle" from the code itself (the know-how that sits in code, not in lessons);
  - every row of the parts reviews (*.parts.md): what the part really is, what holds it, what it does; a session's
    ok / fix on it is correctness, never the owner's taste;
  - every row of a brief's parts plan (*.brief.md): how each part of a past piece was planned to be made;
  - the helper libraries (kit/blender/rbx.py's Asset methods, rbx_parts.py, rbx_lathe.py): the helpers that already
    do a job (rivet_ring, knurl, bolts ...).
Only builds the owner approved lend GEOMETRY (his rule, 2026-10-08); every other build lends its recipe as knowledge,
shown as unjudged. Materials and scans are the look and stay hidden unless the owner allowed it.
"""

import glob
import os
import re

LANE = "3d"
# a 3D piece's parts are answered in its study's Parts section (kit study <asset> --new; the lock) or a stand-alone sheet
SHEET_GLOBS = ["*.parts-sheet.md", "*.study.md"]
CALL = re.compile(r"""\b(?:a|asset)\.(\w+)\(\s*f?["']([^"'{}\n]*(?:\{[^}]*\}[^"'\n]*)*)["']""")
PCALL = re.compile(r"""\b(?:P|Pt|parts|rp)\.(\w+)\(\s*a\s*,\s*f?["']([^"'\n]+)["']""")
CAD = re.compile(r"""^\s*cad\(\s*f?["']([^"'\n]+)["']""")
SKIP_METHODS = {"material", "param", "floaters", "pack", "export", "render", "group", "joint", "expect", "reference",
                "inspect", "texture_from", "zone", "look", "check", "save", "log", "note", "kit_part", "select",
                # (not parts: a reference point, wear, normal-map stamps, checks - their first word is a kind or a name
                #  of a place, never a part the parts review lists)
                "anchor", "contact", "stamp", "not_reference", "trace_match", "form_match", "maker", "disassembly",
                "clear_path"}
# a call name's f-string field, as a parts review spells it: an index, or a side
FIELD = r"(?:\d+|Left|Right|Top|Bottom|Front|Rear|Back|Upper|Lower|Inner|Outer|In|Out|L|R|U|D)"
SUFFIX = re.compile(rf"(?:{FIELD})+")
ROW = re.compile(r"^- (\S+) \[([0-9a-f]+)\]: (.*)$")
DEF = re.compile(r"^(\s*)def (\w+)\(([^)]*)\)")
HELPERS = ("kit/blender/rbx.py", "kit/blender/rbx_parts.py", "kit/blender/rbx_lathe.py")


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _folders(root):
    return [os.path.join(root, "assets", "models")] + sorted(glob.glob(os.path.join(root, "games", "*", "assets",
                                                                                  "models")))


def _skip(stem):
    return stem.startswith("_") or stem.startswith("probe")


def sources(root):
    pats = [os.path.join(root, h) for h in HELPERS]
    for f in _folders(root):
        pats += [os.path.join(f, "build_*.py"), os.path.join(f, "*.parts.md"), os.path.join(f, "*.brief.md")]
    return pats


def homes(root):
    return _folders(root)


def home(root, piece):
    for f in _folders(root):
        if any(os.path.isfile(os.path.join(f, n)) for n in (f"build_{piece}.py", f"{piece}.brief.md")):
            return f
    game = os.environ.get("KIT_GAME")
    if game and os.path.isdir(os.path.join(root, "games", game, "assets", "models")):
        return os.path.join(root, "games", game, "assets", "models")
    return os.path.join(root, "assets", "models")


def spaced(name):
    """CamelCase -> words: FiringPin -> Firing Pin"""
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", name or "")


def family(name):
    """a part family from a call's name: f"Stave{k:02d}" -> Stave, "Bolt_3" -> Bolt"""
    n = re.sub(r"\{[^}]*\}", "", name)
    n = re.sub(r"[_\-. ]*\d+$", "", n).strip("_-. ")
    return n or name


def _comments_above(lines, i, n=4):
    out = []
    j = i - 1
    while j >= 0 and len(out) < n:
        s = lines[j].strip()
        if s.startswith("#"):
            out.insert(0, s.lstrip("#").strip())
        elif s:
            break
        j -= 1
    return " ".join(out)


def builder_docs(root, path, piece):
    lines = _read(path).splitlines()
    rel = _rel(root, path)
    fams = {}
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        hits = [(m.group(1), m.group(2)) for m in CALL.finditer(line) if m.group(1) not in SKIP_METHODS]
        hits += [(f"P.{m.group(1)}", m.group(2)) for m in PCALL.finditer(line)]
        m = CAD.match(line)
        if m:
            hits.append(("cad", m.group(1)))
        for method, name in hits:
            fam = family(name)
            if not re.match(r"[A-Za-z]", fam):
                continue
            f = fams.setdefault(fam, {"line": i + 1, "methods": [], "calls": 0, "code": [], "notes": [], "kw": {},
                                      "names": []})
            f["calls"] += 1
            if name not in f["names"] and len(f["names"]) < 8:
                f["names"].append(name)  # (the call's own name template: f"Round{k:02d}" - what its rows are named)
            if method not in f["methods"]:
                f["methods"].append(method)
            if len(f["code"]) < 3:  # (the call with the loop around it: an angle loop reads as copies round a circle)
                f["code"].append("\n".join(lines[max(0, i - 6):i + 3]))
            if "snippet" not in f:  # (what a reader sees: the loop it sits in, if any, then the call itself)
                loops = [s.strip() for s in lines[max(0, i - 6):i] if re.match(r"\s*(for|while)\b", s)]
                f["snippet"] = " ".join(" ".join(loops[-1:] + [s.strip() for s in lines[i:i + 3]]).split())[:420]
            note = _comments_above(lines, i)
            if note and note not in f["notes"]:
                f["notes"].append(note)
            for k, v in re.findall(r"\b(bevel|segments|radius|wall|shell|depth|length|width|height|count|n)\s*=\s*"
                                   r"([\d.]+)", line):
                f["kw"].setdefault(k, v)
    docs = []
    for fam, f in fams.items():
        mats = re.findall(r"""scan\s*=\s*["'](\w+)""", "\n".join(f["code"]))
        docs.append({"id": f"3d/recipe/{piece}/{fam}", "type": "recipe", "piece": piece,
                     "title": f"{piece}: {fam} via {', '.join(f['methods'][:3])}" + (f" x{f['calls']}" if f["calls"] > 1
                                                                                      else ""),
                     "text": f"{spaced(fam)} made with {' '.join(f['methods'])}. "
                             + " ".join(f["notes"][:3]),
                     "code": "\n".join(f["code"]), "src": f"{rel}:{f['line']}",
                     "snippet": f.get("snippet", ""), "names": f["names"],
                     "mech": dict({"made with": "/".join(f["methods"][:3]), "copies": f["calls"]}, **f["kw"]),
                     "look": {"scan": ",".join(sorted(set(mats)))} if mats else None})
    return docs


def review_docs(root, path, piece, recipes):
    rel = _rel(root, path)
    docs = []
    for line in _read(path).splitlines():
        m = ROW.match(line.strip())
        if not m:
            continue
        name, _fp, rest = m.groups()
        status = "todo" if rest.startswith("TODO") else ("fix" if "verdict: fix" in rest else
                                                          ("ok" if "verdict: ok" in rest else "todo"))
        body = re.sub(r"^TODO\s*(\(changed since:\s*)?", "", rest).rstrip(")")
        fields = {}
        for cell in body.split(" | "):
            k, sep, v = cell.partition(":")
            if sep:
                fields[k.strip().lower()] = v.strip()
        if not fields.get("real"):
            continue  # (an unanswered row is only a name: its builder's recipe card already carries it)
        text = (f"{spaced(name)}: {fields.get('real', '')}; works: {fields.get('works', '')}; held by: "
                f"{fields.get('attaches', '')}")
        doc = {"id": f"3d/part/{piece}/{name}", "type": "part", "piece": piece,
               "title": f"{name}: {fields.get('real', '')[:80]}", "text": text, "src": rel,
               "session": status, "mech": {"session review": status}}
        if status == "fix":
            doc["mech"]["session fix"] = fields.get("verdict", "")[4:80]
        rid = recipe_for(name, piece, recipes)
        if rid:
            doc["mech"]["recipe"] = rid
        docs.append(doc)
    return docs


def _template(raw):
    """a call's name as a pattern for the rows it makes: f-string fields -> an index or a side
    ('Round{k:02d}' -> Round(?:\\d+|L|R|...)) -> (pattern, indexed?)"""
    bits = re.split(r"\{[^}]*\}", raw)
    if len(bits) > 1 and len("".join(bits)) < 3:
        return r"(?!)", True  # (a name that is all fields - "{n}{k}" - says nothing: it never claims a row)
    out = []
    for i, b in enumerate(bits):
        out.append(re.escape(b))
        if i < len(bits) - 1:
            # (a leading field names the part itself - f"{n}Pin" over n = Trigger, Hammer: a capitalised word)
            out.append(r"[A-Z][A-Za-z]*?" if i == 0 and b == "" else FIELD)
    return "".join(out), len(bits) > 1


def recipe_for(name, piece, recipes):
    """the builder recipe a parts-review row comes from, read off the calls' own name templates (fresh review, P1):
    its exact family; else the call whose name template the row's name begins with - an indexed call (f"Round{k:02d}")
    owns its sub-parts too ('Round10Bullet'), a plain name only a side or number after it ('SlideStopRight' from
    f"SlideStop{side_}", never 'HammerPin' from 'Hammer': the pin is its own call). `recipes`: {recipe id: [the call's
    raw names]} (a set of ids works for exact families only). None when no call names it"""
    exact = f"3d/recipe/{piece}/{family(name)}"
    if exact in recipes:
        return exact
    if not isinstance(recipes, dict):
        return None
    prefix = f"3d/recipe/{piece}/"
    best = None
    for rid, raws in recipes.items():
        if not rid.startswith(prefix):
            continue
        for raw in raws or []:
            pattern, indexed = _template(raw)
            m = re.match(pattern, name)
            if not m:
                continue
            rest = name[m.end():]
            if rest and not SUFFIX.fullmatch(rest) and not (indexed and rest[:1].isupper()):
                continue
            if best is None or m.end() > best[0]:
                best = (m.end(), rid)
    return best[1] if best else None


def _brief_rows(text, key):
    """the numbered rows of a brief's `- <key>:` list ('1. PartName | recipe | refs | material')"""
    rows, on = [], False
    for line in (text or "").splitlines():
        s = line.strip()
        if s.lower().startswith(f"- {key}:"):
            on = True
            continue
        if on:
            m = re.match(r"^(\d+)\.\s+(.*)$", s)
            if m:
                rows.append(m.group(2))
            elif s.startswith("- ") or s.startswith("#"):
                break
    return rows


def brief_docs(root, path, piece):
    text = _read(path)
    rel = _rel(root, path)
    docs = []
    for i, row in enumerate(_brief_rows(text, "parts plan")):
        cells = [c.strip() for c in row.split("|")]
        docs.append({"id": f"3d/plan/{piece}/{i + 1}", "type": "plan", "piece": piece,
                     "title": f"{piece} plan: {cells[0][:60]}",
                     "text": f"{cells[0]}: {cells[1] if len(cells) > 1 else ''}", "src": rel,
                     "look": {"material": cells[3][:60]} if len(cells) > 3 and cells[3] else None})
    return docs


def helper_docs(root):
    docs = []
    for rel in HELPERS:
        path = os.path.join(root, rel)
        lines = _read(path).splitlines()
        mod = os.path.splitext(os.path.basename(rel))[0]
        for i, line in enumerate(lines):
            m = DEF.match(line)
            if not m or m.group(2).startswith("_"):
                continue
            indent, name, args = m.groups()
            if rel.endswith("rbx.py") and len(indent) != 4:
                continue  # (rbx.py: the Asset methods only)
            doc = ""
            for j in range(i + 1, min(i + 4, len(lines))):
                s = lines[j].strip()
                if s.startswith(('"""', "'''")):
                    body = []
                    k = j
                    while k < len(lines) and len(body) < 8:
                        body.append(lines[k].strip().strip('"').strip("'"))
                        if k > j and ('"""' in lines[k] or "'''" in lines[k]):
                            break
                        if k == j and lines[k].strip().count('"""') == 2:
                            break
                        k += 1
                    doc = " ".join(b for b in body if b)
                    break
            if not doc:
                continue
            docs.append({"id": f"3d/helper/{mod}/{name}", "type": "helper", "piece": f"helper:{mod}",
                         "title": f"{mod}.{name}({args.replace('self, ', '')[:60]})", "text": f"{name}: {doc[:500]}",
                         "src": f"{rel}:{i + 1}", "code": "\n".join(lines[i:i + 30])})
    return docs


def collect(root):
    pieces, docs = [], []
    for folder in _folders(root):
        for p in sorted(glob.glob(os.path.join(folder, "build_*.py"))):
            piece = os.path.basename(p)[6:-3]
            if _skip(piece):
                continue
            pieces.append({"name": piece, "folder": _rel(root, folder)})
            docs += builder_docs(root, p, piece)
    recipes = {d["id"]: d.get("names") or [] for d in docs}  # (each recipe with its calls' name templates)
    for folder in _folders(root):
        for p in sorted(glob.glob(os.path.join(folder, "*.parts.md"))):
            piece = os.path.basename(p)[:-len(".parts.md")]
            if not _skip(piece):
                docs += review_docs(root, p, piece, recipes)
        for p in sorted(glob.glob(os.path.join(folder, "*.brief.md"))):
            piece = os.path.basename(p)[:-len(".brief.md")]
            if not _skip(piece):
                docs += brief_docs(root, p, piece)
    docs += helper_docs(root)
    return {"pieces": pieces, "docs": docs}


def _brief_path(root, piece):
    for f in _folders(root):
        p = os.path.join(f, f"{piece}.brief.md")
        if os.path.isfile(p):
            return p
    return None


def brief(root, piece):
    p = _brief_path(root, piece)
    return _read(p) if p else None


def breakdown(root, piece, text):
    """a brief with a parts plan: one part per row (the parts named in its hero features are the hero parts); with
    only hero features: one part per feature. None otherwise (the engine splits the words)"""
    plan = _brief_rows(text, "parts plan")
    hero = " ".join(_brief_rows(text, "hero features")).lower()
    if plan:
        parts = []
        for row in plan:
            cells = [c.strip() for c in row.split("|")]
            name = cells[0]
            words = f"{name}: {cells[1] if len(cells) > 1 else ''} {cells[3] if len(cells) > 3 else ''}"
            key = [w for w in re.findall(r"[a-z]{4,}", name.lower())]
            parts.append({"title": name[:90], "words": words, "hero": bool(key) and any(w in hero for w in key)})
        return parts
    feats = _brief_rows(text, "hero features")
    if feats:
        return [{"title": f.split("|")[0].strip()[:90], "words": f, "hero": True} for f in feats]
    return None
