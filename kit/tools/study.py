"""study.py — `kit study <asset>`: the REFERENCE STUDY, the second half of stage 1 (the owner, 2026-10-28: "it didn't
deep analyze the references fully ... and use that to learn. And then from that, create its own version"). Gathering
pictures, models and sizes is not learning from them: a study READS each reference (its silhouette, its proportions in
numbers, its shape language, the decisions that make it look good, its surface, what is weak), names what every good
one shares (the rules of the type), decides OUR version (what we keep, what we change, our signature, our target
numbers) and names the vault lessons this build applies. Only then does the shape start.

    lune run kit study <asset> --new     write assets/models/<asset>.study.md: one section per gathered reference
                                         (the traced pictures, the reference models), the measured sizes from the pack,
                                         the vault lessons that match this object (retrieved by its words: the brief's
                                         what, hero features and parts plan) and the past cases (golden + graveyard rows
                                         of the same kind)
    lune run kit study <asset>           check it: every answer written and specific, numbers where numbers belong, as
                                         many references as the tier needs (prop 1, complex 2, hero / aaa 3), sources
                                         that exist, the lessons cited by id (kit study records them: the owner's later
                                         verdict credits each one — kit/lib/vault.luau's citations)
    [--root <project folder>]

kit plan's gather stage is done only when the study passes; kit asset refuses a new asset (made after the quality locks)
without one. A kit make prop is exempt: its brief is kit make's own and its gather / tournament stages measure the
references themselves. Pure python, no Blender. One JSON verdict line last.
"""

import ast
import functools
import glob
import json
import math
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

MIN_REFS = {"prop": 1, "complex": 2, "hero": 3, "aaa": 3}
# each reference's questions: (field, what it asks, the fewest words a real answer takes, numbers it must carry)
REF_FIELDS = (
    ("source", "the picture / model file, or its link", 1, 0),
    ("silhouette", "what the outline reads as at 32 px: the big masses and how they join", 6, 0),
    ("proportions", "MEASURED ratios: length to height, each part as % of the whole, angles", 4, 2),
    ("shape language", "round / square / blade / tube; edge treatment; the rhythm and spacing of the parts", 6, 0),
    ("why it looks good", "the 2-3 design decisions that make THIS one work, never 'it looks cool'", 12, 0),
    ("surface", "materials, finish, wear, where the detail sits and where it rests", 6, 0),
    ("weak", "what does not work or would read badly in game: what we avoid", 4, 0),
)
OURS_FIELDS = (
    ("keep", "the rules of the type we keep, from the common ground", 8, 0),
    ("change", "what we change so it is our own piece, never a re-skin of one reference", 10, 0),
    ("signature", "our one signature element players will remember: a shape, motif or detail", 5, 0),
    ("proportions", "our target numbers, each inside or argued against a measured range above", 4, 2),
)
HINTS = [ask for _k, ask, _w, _n in REF_FIELDS + OURS_FIELDS]
NONE_HINT = "no lesson matched: say why none applies"
STOP = set("""the a an and or of to in on at for with from by as is are be it its this that these those not no
into onto over under than then them they their there here when where what which who how why all any each every
one two three more most less much many some such only own same other very can will would should could must may
just also but if so do does did done has have had was were been being use used using make made our your his her
owner kit build built model asset part look looks real new now said answer —""".split())
MUST_ANSWER = 5  # (the best matches a study must answer one by one: applied, or skipped with why)
FAMILY_WORDS = 2  # (a lesson / case matches on at least this many of the object's words — see retrieve())


# -------------------------------------------------------------------------------------------------------- reading
def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _front(text):
    """a vault note's frontmatter (flat key: value lines) and its body"""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text.replace("\r\n", "\n"), re.DOTALL)
    if not m:
        return {}, text
    front = {}
    for line in m.group(1).split("\n"):
        k, sep, v = line.partition(":")
        if sep and not line.startswith(" "):
            front[k.strip()] = v.strip().strip('"')
    return front, m.group(2)


def lesson_id(rel):
    """kit/lib/vault.luau's Vault.lessonId: L-<dept>-<6 hex> of the file name (djb2), so ids agree across the kit"""
    base = rel.rsplit("/", 1)[-1]
    base = base[:-3] if base.endswith(".md") else base  # (a note's rel has no extension)
    h = 5381
    for ch in base.encode("utf-8"):
        h = (h * 33 + ch) % 4294967296
    return f"L-{rel.split('/', 1)[0]}-{h % 16777216:06x}"


def vault_dir(root):
    """the vault the asset's lessons live in: the root's own, else the nearest folder above it that holds one (a game's
    asset, --root games/<Name>, reads the kit home's vault: the game folder has none, and a study run there matched
    no lesson at all - 44 of the first 46 Sample Game studies, 2026-11); none within two folders up: the root's own (absent)"""
    here = os.path.abspath(root)
    for _ in range(3):  # (the root, its games/ folder and the project above it: never an unrelated vault higher up)
        cand = os.path.join(here, "kit", "knowledge", "vault")
        if os.path.isdir(cand):
            return cand
        up = os.path.dirname(here)
        if up == here:
            break
        here = up
    return os.path.join(os.path.abspath(root), "kit", "knowledge", "vault")


def lessons(root, dept="3d"):
    """the department's live lessons: [{id, rel, text, stages}] (a superseded one is retired: never retrieved)"""
    base = vault_dir(root)
    notes, retired = [], set()
    for p in sorted(glob.glob(os.path.join(base, dept, "lessons", "*.md"))):
        rel = os.path.relpath(p, base).replace(os.sep, "/")
        front, body = _front(_read(p))
        if front.get("superseded_by"):
            retired.add(rel.lower())
        for t in re.findall(r"\[\[([^\]|#]+)", front.get("supersedes", "")):
            retired.add((t if t.endswith(".md") else t + ".md").lower())
        stages = re.findall(r"[\w-]+", front.get("stages", ""))
        date = front.get("date") or (re.match(r"\d{4}-\d{2}-\d{2}", os.path.basename(p)) or [""])[0]
        notes.append({"id": lesson_id(rel), "rel": rel, "text": " ".join(body.split()), "stages": stages,
                      "date": str(date)})
    return [n for n in notes if n["rel"].lower() not in retired]


# ---------------------------------------------------------------------------------- what a study owes (owner, 2026-11-10)
# A study owes the lessons it was SHOWN when it was written, plus every lesson written since that ranks among its top
# MUST_ANSWER now - never an older lesson that only moved up because new lessons changed the ranking (five new lessons
# put twelve finished Sample Game studies in debt to October lessons, 2026-11-09). The owner, asked: "which you
# recommend go ahead with especially for the future and wanting the best".
ANSWER_MARK = re.compile(r"<!--\s*ANSWER\s+(L-[A-Za-z0-9]+-[0-9a-f]+)")


def _inside(path, base):
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(base)]) == os.path.abspath(base)
    except ValueError:  # (another drive)
        return False


def _citation_rows(root):
    """the citation rows of the project and, for a game inside the kit home, the home's (where kit study records)"""
    rows, seen = [], set()
    for base in (root, ROOT) if _inside(root, ROOT) else (root,):
        path = os.path.join(base, "board", "citations.json")
        if os.path.isfile(path) and os.path.abspath(path) not in seen:
            seen.add(os.path.abspath(path))
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                rows += [r for r in data if isinstance(r, dict)]
            except (OSError, ValueError):
                pass
    return rows


def _first_added(path):
    """the day git first saw a file (YYYY-MM-DD), or None"""
    import subprocess  # noqa: PLC0415
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%ad", "--date=short", "--", path],
                             capture_output=True, text=True, timeout=20, cwd=ROOT).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return out[-1] if out else None


def study_record(asset, root, path, text):
    """-> (the ids its current text was shown, the day it last engaged with its lessons or None): the LATEST kit study
    --new served row (a re-run rewrites the study) and the study's own ANSWER marks; the day of its latest served or
    cited row (its answers recorded), else git's first commit of the study"""
    rows = [r for r in _citation_rows(root) if r.get("kind") == "asset" and r.get("name") == asset
            and r.get("dept", "3d") == "3d"]
    served = sorted((r for r in rows if r.get("served")), key=lambda r: r.get("at", 0))
    shown = list(served[-1].get("lessons") or [])[:MUST_ANSWER] if served else []
    shown += [i for i in ANSWER_MARK.findall(text or "") if i not in shown]
    dates = [str(r.get("date")) for r in rows if r.get("date")]
    written = max(dates) if dates else _first_added(path)
    return shown, written


def table_rows(path):
    """a golden / graveyard page's rows as lists of cells (header and rule rows dropped)"""
    rows = []
    for line in _read(path).splitlines():
        if line.startswith("|") and not re.match(r"^\|\s*-", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if cells and cells[0] not in ("piece", "tried"):
                rows.append(cells)
    return rows


# ------------------------------------------------------------------------------------------------------ retrieval
def words(text):
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")
    out = []
    for w in re.findall(r"[a-z][a-z0-9]{2,}", spaced.lower().replace("_", " ")):
        if w not in STOP:
            out.append(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def retrieve(query, docs, k=8, text_of=lambda d: d["text"], core=None):
    """TF-IDF cosine of the query against each doc; -> [(score, doc)] best first, only docs sharing >= FAMILY_WORDS
    distinct words with the query (a lesson that shares one word with the brief is noise, not knowledge)"""
    toks = [words(text_of(d)) for d in docs]
    n = len(docs) or 1
    df = {}
    for t in toks:
        for w in set(t):
            df[w] = df.get(w, 0) + 1
    idf = {w: math.log((n + 1) / (c + 0.5)) for w, c in df.items()}
    q = {}
    for w in words(query):
        q[w] = q.get(w, 0) + 1
    qv = {w: c * idf.get(w, math.log(n + 1)) for w, c in q.items()}
    qn = math.sqrt(sum(v * v for v in qv.values())) or 1
    out = []
    for d, t in zip(docs, toks):
        tf = {}
        for w in t:
            tf[w] = tf.get(w, 0) + 1
        dv = {w: c * idf[w] for w, c in tf.items()}
        dot = sum(qv[w] * dv[w] for w in qv if w in dv)
        if dot <= 0:
            continue
        if sum(1 for w in qv if w in dv) < FAMILY_WORDS:
            continue
        if core and not any(w in dv for w in core):
            continue  # (it must be about THIS kind of object: one of the words the object is named by)
        out.append((dot / (qn * (math.sqrt(sum(v * v for v in dv.values())) or 1)), d))
    out.sort(key=lambda x: -x[0])
    return out[:k]


# ---------------------------------------------------------------------------------------------------- the asset
def brief_of(asset, root):
    return _read(os.path.join(root, "assets", "models", f"{asset}.brief.md"))


def tier_of(brief_text):
    """the brief's quality line -> prop / complex / hero / aaa (kit/lib/lanelocks.luau's briefTier); unanswered -> prop"""
    m = re.search(r"(?im)^\s*-\s*quality:\s*(.*)$", brief_text or "")
    q = (m.group(1) if m else "").lower()
    if "<answer>" in q:
        return "prop"
    for t in ("aaa", "hero", "complex"):
        if t in q:
            return t
    return "prop"


def core_of(asset, brief_text):
    """the words naming the object itself: the asset name and the brief's what line (the owner's quoted words out:
    they say what they asked, not what the object is)"""
    m = re.search(r"(?im)^\s*-\s*what:\s*(.*)$", brief_text or "")
    what = m.group(1) if m and "<answer>" not in m.group(1) else ""
    what = re.sub(r"[\"“][^\"”]*[\"”]|'[^']*'|(?:the )?owner[^:;)]*:?", " ", what)
    return set(words(asset.replace("_", " ") + " " + what))


def query_of(asset, brief_text):
    """the words an asset is known by: its name, what it is, its hero features and its parts plan"""
    keep = [asset.replace("_", " ")]
    for key in ("what", "style", "function", "moving parts"):
        m = re.search(rf"(?im)^\s*-\s*{key}:\s*(.*)$", brief_text or "")
        if m and "<answer>" not in m.group(1):
            keep.append(m.group(1))
    keep = keep[:2] * 2 + keep[2:]  # (what the object IS weighs twice what its features mention)
    block = re.search(r"(?ims)^\s*-\s*hero features:.*?(?=^\s*-\s*\w[\w ]*:|\Z)", brief_text or "")
    if block:
        keep += [ln for ln in block.group(0).splitlines()[1:] if re.match(r"^\s*\d+\.", ln)]
    block = re.search(r"(?ims)^\s*-\s*parts plan:.*?(?=^\s*-\s*\w[\w ]*:|\Z)", brief_text or "")
    if block:
        keep += [ln.split("|")[0] for ln in block.group(0).splitlines()[1:] if re.match(r"^\s*\d+\.", ln)]
    return " ".join(keep)


def made_by_kit_make(brief_text):
    return (brief_text or "").lstrip().startswith("<!-- written by kit make")


def gathered(asset, root):
    """the references stage 1 gathered (kit/tools/plan.py's facts): traced pictures, reference models, measured sizes"""
    sys.path.insert(0, HERE)
    import plan as PL  # noqa: PLC0415  (pure python too; imported late: plan.py imports this module)

    f = PL.facts(asset, root)
    pics = sorted(set(p for p in f["trace_pictures"].values() if p))
    models = list(f["ref_models"])
    pk = f.get("pack") or {}
    sizes = []
    obj = pk.get("object") if isinstance(pk.get("object"), dict) else {}
    if obj.get("length_mm"):
        sizes.append(f"real length: {obj['length_mm']} mm ({obj.get('source') or 'unsourced'})")
    for k, v in sorted((pk.get("sizes") or {}).items()):
        if isinstance(v, dict):
            mm = v.get("mm") or v.get("value") or v.get("length_mm")
            sizes.append(f"{k}: {mm} mm ({v.get('source') or 'unsourced'})")
    return pics, models, sizes


# ------------------------------------------------------------------------------------------------------ the file
def study_path(asset, root):
    return os.path.join(root, "assets", "models", f"{asset}.study.md")


def script_path(asset, root):
    return os.path.join(root, "assets", "models", f"build_{asset}.py")


# ------------------------------------------------------------------------------------------------------ the route
# A study's answers hold for the ROUTE they were written for (the owner, 2026-11-10, after the car rim: round 5 learned
# that baked bevel normals made the sawtooth and the rim's study cited that lesson, yet its S1 game version baked every
# fillet into the normal map and the sawtooth came back - the lesson was answered once, for round 5, and nothing asked
# it again when the route changed). The route is the SWITCHES that move detail between geometry and maps - the
# game version, parts baked into it, rounds baked onto a sharp low, mesh bevels off - read from the build script's code
# (never its docstring or comments). A new part family is not a route change: it would ask the same lessons again for
# nothing. kit asset refuses a build on a route its study's lessons were not answered for (kit/tools/plan.py
# --prebuild) until `kit study <asset> --reroute` keeps the old answers as "Earlier answers" and every matched lesson is
# answered again, for the new route. (A script that builds through a helper module is not read: its switches live
# there.)
ROUTE_WORDS = {  # switch -> (its words in the lesson query: the lessons about THAT route rank in; its core words: they
    # pass the object filter too - a game-version lesson learned on the rim reaches a cupboard's game version)
    "low": ("game version low poly bake baked normal map triangles", "bake baked low"),
    "high-only parts": ("detail baked into the normal map threads", "bake baked"),
    "baked rounds": ("rounds fillets baked into the normal map sawtooth", "bake baked fillet"),
    "no bevel": ("bevel edge radius baked normal", "bevel"),
}
ROUTE_MARK = re.compile(r"<!--\s*ROUTE:\s*(.*?)\s*-->")
ROUTE_SWITCHES = ("low", "high-only parts", "baked rounds", "no bevel")
EARLIER = "earlier answers"  # (a Lessons applied answered for an earlier route: kept to read, never counted)


def route_of(script_text, follow=None):
    """a build script -> its route: the sorted switches its CODE sets (parsed: a docstring's example or a comment is
    never a route) - low = the high-and-low game version (Asset(low=...) on); high-only parts = a part baked into the
    low's maps (low=False on a part); baked rounds = the high's rounds baked onto a sharp low (low={"round": 0});
    no bevel = Asset(edge_radius=0). A wrapper that only runs another build script (runpy.run_path) is read through
    to it: follow(<the path's last part>) -> its text"""
    try:
        tree = ast.parse(script_text or "")
    except SyntaxError:
        return ()

    def name_of(call):
        f = call.func
        return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""

    def kw(call, key):
        return next((k.value for k in call.keywords if k.arg == key), None)

    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assets = [c for c in calls if name_of(c) == "Asset"]
    toks = set()
    for c in assets:
        low = kw(c, "low")
        if low is not None and not (isinstance(low, ast.Constant) and low.value in (None, False, 0)):
            toks.add("low")
        er = kw(c, "edge_radius")
        if isinstance(er, ast.Constant) and isinstance(er.value, (int, float)) and er.value == 0:
            toks.add("no bevel")
    if "low" in toks:
        for c in calls:
            low = kw(c, "low") if c not in assets else None
            if isinstance(low, ast.Constant) and low.value is False:
                toks.add("high-only parts")
            if isinstance(low, ast.Dict):
                for k, v in zip(low.keys, low.values):
                    if (isinstance(k, ast.Constant) and k.value == "round" and isinstance(v, ast.Constant)
                            and isinstance(v.value, (int, float)) and v.value == 0):
                        toks.add("baked rounds")
    if not assets and follow is not None:
        for c in calls:
            if name_of(c) == "run_path" and c.args:
                lits = [n.value for n in ast.walk(c.args[0]) if isinstance(n, ast.Constant) and isinstance(n.value, str)
                        and n.value.endswith(".py")]
                text = follow(lits[-1]) if lits else None
                if text:
                    return route_of(text)  # (one level: the script it runs)
    return tuple(sorted(toks))


def _follow(root):
    """a wrapper's target script, by the last part of the path it runs (in the asset folder)"""
    return lambda name: _read(os.path.join(root, "assets", "models", os.path.basename(name)))


def script_route(asset, root):
    """the route of the asset's build script now"""
    return route_of(_read(script_path(asset, root)), follow=_follow(root))


def route_text(route):
    return ", ".join(route) if route else "none"


def _section(text, name):
    """the raw lines (comments kept) of a study's '## <name>' section, or None"""
    out, cur = None, False
    for line in (text or "").replace("\r\n", "\n").split("\n"):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            if cur:
                break
            cur = m.group(1).strip().lower() == name
            if cur:
                out = []
            continue
        if cur:
            out.append(line)
    return out


def route_stamp(text):
    """the route a study's current answers were written for (the ROUTE mark in its Lessons applied), or None"""
    for ln in _section(text, "lessons applied") or []:
        m = ROUTE_MARK.search(ln)
        if m:
            # (only the switches count: a mark written while part families counted - 2026-11-10, a few hours - reads
            # as its switches, never as a change)
            return tuple(sorted(t.strip() for t in m.group(1).split(",") if t.strip() in ROUTE_SWITCHES))
    return None


UNKNOWN_ROUTE = ("?",)  # (git could not be asked: no stamp is written on it, no build refused on it)


@functools.lru_cache(maxsize=512)
def _route_at_birth(asset, root):
    """the route its build script had in the commit that first added the study - what an unstamped study's answers
    were written for - or None (no git; the study or the script not committed then)"""
    import subprocess  # noqa: PLC0415
    study = os.path.relpath(study_path(asset, root), root).replace(os.sep, "/")
    try:
        first = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H", "--", study], capture_output=True,
                               text=True, timeout=20, cwd=root).stdout.split()
        if not first:
            return None
        old = subprocess.run(["git", "show", f"{first[-1]}:./assets/models/build_{asset}.py"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=20, cwd=root)
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN_ROUTE
    return route_of(old.stdout, follow=_follow(root)) if old.returncode == 0 else None


def route_gate(asset, root):
    """kit asset's question before a build -> None, or (was, now): the build script's route differs from the one its
    study's lessons were answered for (its ROUTE mark; an unstamped study: the script's route when the study was first
    committed)"""
    text, script = _read(study_path(asset, root)), _read(script_path(asset, root))
    if not text or not script or made_by_kit_make(brief_of(asset, root)):
        return None
    now = script_route(asset, root)
    was = route_stamp(text)
    if was is None:
        was = _route_at_birth(asset, root)
    if was is None or was == UNKNOWN_ROUTE or tuple(was) == now:
        return None
    return tuple(was), now


def stamp_route(asset, root):
    """an unstamped study gets its build's route now (kit asset, once the route check passed): a later change is then
    caught -> True when written"""
    path = study_path(asset, root)
    text, script = _read(path), _read(script_path(asset, root))
    if not text or not script or route_stamp(text) is not None or _route_at_birth(asset, root) == UNKNOWN_ROUTE:
        return False  # (git could not say what it was written for: the next build asks again, never a stamp on a guess)
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    for i, ln in enumerate(lines):
        if re.match(r"^##\s+lessons applied\s*$", ln, re.IGNORECASE):
            lines.insert(i + 1, f"<!-- ROUTE: {route_text(script_route(asset, root))} -->")
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(nl.join(lines))
            return True
    return False


def lessons_lines(found, route):
    """the Lessons applied section: its route's mark, the matches (the first MUST_ANSWER to answer) and their stubs"""
    out = ["## Lessons applied", f"<!-- ROUTE: {route_text(route)} -->", "",
           "(the vault lessons below matched this object's words. Answer each of the first "
           f"{min(MUST_ANSWER, len(found))}: `- <id>: how this",
           "build applies it`, or `- skip <id>: why it does not apply`; cite any other lesson the same way. kit study",
           "records the applied ones on this piece: the owner's verdict on it credits or flags each)", ""]
    if found:
        for i, (score, d) in enumerate(found):
            tag = "ANSWER" if i < MUST_ANSWER else "optional"
            out.append(f"<!-- {tag} {d['id']} ({score:.2f}{', ' + '/'.join(d['stages']) if d['stages'] else ''}): "
                       f"{d['text'][:300]} -->")
        out.append("")
        out += [f"- {d['id']}: <answer>" for _s, d in found[:MUST_ANSWER]]
    else:
        out.append(f"- none: <answer>  ({NONE_HINT})")
    return out


def reroute(asset, root, today=None):
    """the route changed: its Lessons applied (answered for the route it had) is kept as 'Earlier answers (route: ..)'
    - its ANSWER marks muted, never counted - under a fresh Lessons applied for the build's route now (that route's
    words in the query, its ROUTE mark) -> (text, was, now, found)"""
    text = _read(study_path(asset, root)).replace("\r\n", "\n")
    now = script_route(asset, root)
    was = route_stamp(text)
    if was is None:
        was = _route_at_birth(asset, root) or ()
    _q, found, _g, _gr = matches(asset, root, now)
    fresh = lessons_lines(found, now)
    head = [f"## Earlier answers (route: {route_text(was)}, before {today or time.strftime('%Y-%m-%d')})", "",
            "(answered for the earlier route: kept to read, never counted - answer each lesson above for the new one)"]
    lines, out, i, done = text.split("\n"), [], 0, False
    while i < len(lines):
        if not done and re.match(r"^##\s+lessons applied\s*$", lines[i], re.IGNORECASE):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("## "):
                j += 1
            old = [re.sub(r"<!--\s*ROUTE:", "<!-- was route:", re.sub(r"<!--\s*ANSWER\s+", "<!-- earlier ", ln))
                   for ln in lines[i + 1:j]]
            out += fresh + [""] + head + old
            i, done = j, True
            continue
        out.append(lines[i])
        i += 1
    if not done:  # (no Lessons applied before: the header still marks it rerouted - the build asks for the answers)
        out += [""] + fresh + [""] + head + ["", "- (no Lessons applied before: nothing was answered)", ""]
    return "\n".join(out), tuple(was), now, found


def matches(asset, root, route=None):
    """-> (the query, the lessons, the golden rows, the graveyard rows) matching the asset's words and its route's"""
    brief_text = brief_of(asset, root)
    if route is None:
        route = script_route(asset, root)
    extra = [ROUTE_WORDS[t] for t in route if t in ROUTE_WORDS]
    q = " ".join([query_of(asset, brief_text)] + [w for w, _c in extra])
    core = core_of(asset, brief_text) | set(words(" ".join(c for _w, c in extra)))
    found = retrieve(q, lessons(root), core=core)
    base = vault_dir(root)
    golden = retrieve(q, table_rows(os.path.join(base, "3d", "golden.md")), k=4,
                      text_of=lambda r: " ".join(r[:1] + r[3:5]), core=core)
    grave = retrieve(q, table_rows(os.path.join(base, "3d", "graveyard.md")), k=4,
                     text_of=lambda r: " ".join(r[:1] + r[3:5]), core=core)
    return q, found, golden, grave


def scaffold(asset, root):
    pics, models, sizes = gathered(asset, root)
    q, found, golden, grave = matches(asset, root)
    tier = tier_of(brief_of(asset, root))
    refs = pics + [f"reference model: {m}" for m in models]
    while len(refs) < MIN_REFS[tier]:
        refs.append("<answer>")
    out = [f"# {asset} — reference study", "",
           "Read each reference as a designer would, then decide our own version. Write over every `<answer>`; a",
           "vague answer ('looks cool', 'nice shape') fails the check. `lune run kit study " + asset + "` checks it.",
           "", "## References", ""]
    for i, r in enumerate(refs, 1):
        out.append(f"### Reference {i}")
        for key, ask, _w, _n in REF_FIELDS:
            out.append(f"- {key}: {r if key == 'source' and r != '<answer>' else '<answer>'}  ({ask})")
        out.append("")
    out += ["## Measured", "", "(from the pack: what stage 1 sourced — the numbers the proportions answer against)"]
    out += [f"- {s}" for s in sizes] or ["- none in the pack yet (lune run kit plan " + asset + " shows the sizes to source)"]
    out += ["", "## Common ground", "",
            "(what EVERY good reference shares: the rules that make it read as this kind of object; >= 2 lines)",
            "- <answer>", "- <answer>", "",
            "## Our version", ""]
    for key, ask, _w, _n in OURS_FIELDS:
        out.append(f"- {key}: <answer>  ({ask})")
    out += ["", "## Parts", ""] + parts_section(asset, root)
    out += [""] + lessons_lines(found, script_route(asset, root))
    out += ["", "## Past cases", "", "(the owner's verdicts on pieces of this kind: the bar, and the routes never to retry)"]
    for _s, r in golden:
        out.append(f"- LOVED {r[0]} {r[1]}/10: {r[3][:160]}" + (f" — decided by: {r[4][:120]}" if len(r) > 4 and r[4] else ""))
    for _s, r in grave:
        out.append(f"- FAILED {r[0]}: {r[2][:80]} — do not retry: {(r[4] if len(r) > 4 else '')[:160]}")
    if not golden and not grave:
        out.append("- none of this kind yet")
    return "\n".join(out) + "\n", q, found


def parse(text):
    """-> {refs: [{field: answer}], common: [lines], ours: {field: answer}, lessons: [(id, how)], none: str|None}"""
    sections, cur = {}, None
    for line in text.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m and not line.startswith("###"):
            cur = m.group(1).strip().lower()
            sections[cur] = []
        elif cur is not None and not line.strip().startswith("<!--"):
            sections[cur].append(line)

    def fields(lines):
        out = {}
        for ln in lines:
            m = re.match(r"^\s*-\s*([a-z][a-z ]*?):\s*(.*)$", ln)
            if m:
                ans = m.group(2).strip()
                for hint in HINTS:  # (the template's own hint after the answer; an answer's own brackets stay)
                    if ans.endswith(f"({hint})"):
                        ans = ans[: -len(hint) - 2].strip()
                out[m.group(1).strip()] = ans
        return out

    refs, block = [], None
    for ln in sections.get("references", []):
        if ln.startswith("### "):
            block = []
            refs.append(block)
        elif block is not None:
            block.append(ln)
    common = [re.sub(r"^\s*-\s*", "", ln).strip() for ln in sections.get("common ground", [])
              if re.match(r"^\s*-\s*", ln)]
    les, skips, none = [], [], None
    for ln in sections.get("lessons applied", []):
        m = re.match(r"^\s*-\s*(L-[\w]+-[0-9a-f]{6})\s*:\s*(.*)$", ln)
        if m:
            les.append((m.group(1), m.group(2).strip()))
        m = re.match(r"^\s*-\s*skip\s+(L-[\w]+-[0-9a-f]{6})\s*:\s*(.*)$", ln, re.IGNORECASE)
        if m:
            skips.append((m.group(1), m.group(2).strip()))
        m = re.match(r"^\s*-\s*none\s*:\s*(.*)$", ln, re.IGNORECASE)
        if m:
            none = m.group(1).replace(f"({NONE_HINT})", "").strip()
    earlier = {}  # (the answers given for an earlier route, by lesson: a new route's answer may not copy one)
    for name, lines in sections.items():
        if name.startswith(EARLIER):
            for ln in lines:
                m = re.match(r"^\s*-\s*(?:skip\s+)?(L-[\w]+-[0-9a-f]{6})\s*:\s*(.*)$", ln, re.IGNORECASE)
                if m:
                    earlier.setdefault(m.group(1), set()).add(_norm(m.group(2)))
    return {"refs": [fields(b) for b in refs], "common": common, "ours": fields(sections.get("our version", [])),
            "lessons": les, "skips": skips, "none": none, "earlier": earlier, "sections": set(sections)}


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _numbers(text):
    return len(re.findall(r"\d+(?:\.\d+)?", text or ""))


def _vague(text, need_words):
    return text in ("", "<answer>") or "<answer>" in text or len(words(text)) < need_words


PARTS_MARK = re.compile(r"<!-- parts: (\d{4}-\d{2}-\d{2})")


def parts_section(asset, root):
    """the study's Parts section (the parts libraries, P1: board/plans/archive/2026-11-09-parts-libraries-plan.md): the brief's
    parts that matter (at most 8) each with the past parts, recipes, helpers and lessons of its KIND from the whole 3D
    library - across objects (a rim's spokes find the barrel's stave loop) - an AVOID line for what the owner rejected,
    and an answer line: the card it is built from, or `new` and why. Mechanics only: no look is handed over."""
    sys.path.insert(0, HERE)
    import parts as P  # noqa: PLC0415  (kit/tools/parts.py: the engine; its index is the kit home's whole 3D library)

    brief_text = brief_of(asset, root)
    if not brief_text.strip():
        return ["(no brief yet: this section is written from the brief's parts plan - write the brief, then --new)"]
    idx = P.load_index(P.ROOT, "3d")
    ad = P.adapter(P.ROOT, "3d")
    head, parts = P.breakdown(idx, ad, asset, brief_text)
    if not parts:
        return ["(the brief names no parts: add its `- parts plan:` rows, then --new)"]
    pools = [P.search(idx, p["words"], k=P.RERANK_POOL, kinds=p["kinds"], exclude=asset, context=head) for p in parts]
    results, how = [pool[:3] for pool in pools], "plain"
    if P.rerank_shown(P.ROOT, "3d"):  # (warm only: the study never waits on a model loading)
        got = P.rerank_rows([(f"{head}: {p['words']}", pool) for p, pool in zip(parts, pools)], 3, cold=False)
        results, how = (got, "re-ranked") if got else (results, f"plain - {P.rerank_hint('3d')}, then --new again")
    keep, rest = P.matters(parts, results)
    return ([f"<!-- parts: {time.strftime('%Y-%m-%d')} (kit parts 3d plan, look-up {how}) -->",
             "(the parts that matter, at most 8, each looked up by its KIND across every past object. "
             + P.ANSWER_HOW.format(lane="3d") + ")", ""]
            + P.part_lines(idx, asset, parts, results, keep, rest, heading="###"))


def parts_problems(text):
    """the Parts section's unanswered parts (a study written before the section existed has none to answer)"""
    m = re.search(r"(?ms)^## Parts\s*$(.*?)(?=^## |\Z)", text or "")
    if not m or not PARTS_MARK.search(m.group(1)):
        return []
    sys.path.insert(0, HERE)
    import parts as P  # noqa: PLC0415

    return [f"parts: {p}" for p in P.check_sheet(P.parse_sheet(m.group(1)))]


def check(asset, root):
    """-> (problems, facts): the study's problems, worst first; facts = {refs, lessons: [ids], tier}"""
    path = study_path(asset, root)
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    text = _read(path)
    if not text:
        return [f"no reference study ({rel}): read each gathered reference and decide our version — "
                f"lune run kit study {asset} --new"], {}
    tier = tier_of(brief_of(asset, root))
    s = parse(text)
    problems = []
    real = [r for r in s["refs"] if r.get("source") and "<answer>" not in r.get("source", "")]
    if len(real) < MIN_REFS[tier]:
        problems.append(f"{len(real)} reference(s) studied, a {tier} needs {MIN_REFS[tier]} (gather more: "
                        f"lune run kit plan {asset} --stage gather)")
    seen = {}
    for i, r in enumerate(s["refs"], 1):
        src = r.get("source", "")
        for key, ask, need, nums in REF_FIELDS[1:]:
            ans = r.get(key, "")
            if _vague(ans, need):
                problems.append(f"reference {i}: '{key}' is missing or too thin (>= {need} specific words: {ask})")
            elif nums and _numbers(ans) < nums:
                problems.append(f"reference {i}: '{key}' needs measured numbers (>= {nums}): {ask}")
            elif ans in seen.get(key, ()):
                problems.append(f"reference {i}: '{key}' repeats another reference's answer word for word (study each "
                                "one on its own)")
            seen.setdefault(key, set()).add(ans)
        path_like = src and "://" not in src and not src.lower().startswith("reference model:")
        if path_like and "<answer>" not in src and not os.path.exists(os.path.join(root, src)):
            problems.append(f"reference {i}: its source {src} does not exist")
    good_common = [c for c in s["common"] if not _vague(c, 5)]
    if len(good_common) < 2:
        problems.append("common ground: >= 2 specific lines (>= 5 words each) on what every good reference shares")
    for key, ask, need, nums in OURS_FIELDS:
        ans = s["ours"].get(key, "")
        if _vague(ans, need):
            problems.append(f"our version: '{key}' is missing or too thin (>= {need} specific words: {ask})")
        elif nums and _numbers(ans) < nums:
            problems.append(f"our version: '{key}' needs target numbers (>= {nums}): {ask}")
    # (the lessons its answers were written for: the route it was stamped with - or had when first committed - not
    # the script's now: a changed route is the BUILD's refusal (kit asset), never kit verify's)
    stamp = route_stamp(text)
    birth = _route_at_birth(asset, root) if stamp is None else None
    _q, found, _g, _gr = matches(asset, root, stamp if stamp is not None else
                                 (birth if birth != UNKNOWN_ROUTE else None))
    live = {d["id"] for d in lessons(root)}
    top = [d for _s, d in found[:MUST_ANSWER]]
    shown, written = study_record(asset, root, path, text)
    # (what the study itself answered - applied or skipped with why - it was shown: an older study with no record and
    # its ANSWER marks removed still owes nothing it already answered, nor anything it never saw that is not newer)
    shown += [lid for lid, _ in s["lessons"] + s["skips"] if lid not in shown]
    if not shown and not written:
        must = [d["id"] for d in top]  # (nothing on record of what it was shown, nor when: as strict as before)
    else:
        # never more than the top MUST_ANSWER of now: of them, what it engaged with and what is newer than that
        must = [d["id"] for d in top if d["id"] in shown or (written and d.get("date", "") >= written)]
    cited, answered = [], set()
    earlier = s.get("earlier") or {}
    copied = (f"repeats its answer for the earlier route word for word: say how the NEW route applies it (or skip it "
              "with why it no longer applies)")
    for lid, how in s["lessons"]:
        if lid not in live:
            problems.append(f"lessons applied: {lid} is no live 3D lesson (retired, or a typo)")
        elif _vague(how, 6):
            problems.append(f"lessons applied: {lid} needs how this build applies it (>= 6 words)")
        elif _norm(how) in earlier.get(lid, ()):
            problems.append(f"lessons applied: {lid} {copied}")
        else:
            cited.append(lid)
            answered.add(lid)
    for lid, why in s["skips"]:
        if _vague(why, 6):
            problems.append(f"lessons applied: skip {lid} needs why it does not apply to this object (>= 6 words)")
        elif _norm(why) in earlier.get(lid, ()):
            problems.append(f"lessons applied: skip {lid} {copied}")
        else:
            answered.add(lid)
    open_ids = [x for x in must if x not in answered]
    if open_ids:
        problems.append(f"lessons applied: {len(open_ids)} matched lesson(s) not answered ({', '.join(open_ids)}): "
                        f"read each and write `- <id>: how this build applies it` or `- skip <id>: why it does not "
                        f"apply` (the matches are listed in {rel})")
    if not must and not answered and not (s["none"] and not _vague(s["none"], 6)):
        problems.append("lessons applied: no lesson matched — write `- none: <why none applies>`")
    problems += parts_problems(text)
    return problems, {"refs": len(real), "lessons": cited, "tier": tier, "path": rel}


def gate(asset, root):
    """kit plan's view: None when no study is needed (a kit make prop), else (problems, facts)"""
    if made_by_kit_make(brief_of(asset, root)):
        return None
    return check(asset, root)


# ----------------------------------------------------------------------------------------------------------- cli
def emit(status, summary, action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": action, **extra}))
    return 0 if status == "pass" else 1


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if not argv or argv[0].startswith("-"):
        emit("fail", "study: needs an asset name", "lune run kit study <asset> [--new]")
        return 2
    asset, root = argv[0], ROOT
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv):
            emit("fail", "study: --root needs a folder", "lune run kit study <asset> --root <folder>")
            return 2
        root = os.path.abspath(argv[i + 1])
    models = os.path.join(root, "assets", "models")
    if not os.path.isfile(os.path.join(models, f"build_{asset}.py")) and not brief_of(asset, root):
        return emit("fail", f"study: no asset '{asset}' (no build script, no brief)", f"lune run kit new asset {asset}")
    path = study_path(asset, root)
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    if "--new" in argv:
        if os.path.isfile(path):
            return emit("fail", f"study: {rel} exists (kept: it holds the study)", f"lune run kit study {asset}")
        text, _q, found = scaffold(asset, root)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(text)
        return emit("pass", f"study: wrote {rel} ({text.count('### Reference')} reference(s), {len(found)} matching "
                    "lesson(s))", f"OPEN each reference picture / model and write {rel}, then lune run kit study {asset}",
                    path=rel, lessons_matched=[d["id"] for _s, d in found])
    if "--reroute" in argv:
        # the route changed (kit asset refused the build): the answers given for the old one are kept to read, and every
        # matched lesson is asked again for the new one
        if not os.path.isfile(path):
            return emit("fail", f"study: {rel} does not exist", f"lune run kit study {asset} --new")
        changed = route_gate(asset, root)
        if not changed:
            return emit("fail", f"study {asset}: its route ({route_text(script_route(asset, root))}) "
                        "is the one its lessons were answered for - nothing to answer again", f"lune run kit study {asset}")
        text, was, now, found = reroute(asset, root)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        n = min(MUST_ANSWER, len(found))
        return emit("pass", f"study: {rel} rerouted ({route_text(was)} -> {route_text(now)}): {n} lesson(s) to answer "
                    "again, for the new route", f"read each lesson under {rel}'s Lessons applied and write how the NEW "
                    f"route applies it (or skip it with why; the old answers are kept under Earlier answers and copying "
                    f"one does not count), then lune run kit study {asset}", path=rel,
                    lessons_matched=[d["id"] for _s, d in found], route=list(now))
    if made_by_kit_make(brief_of(asset, root)):
        return emit("pass", f"study: {asset} is a kit make prop (its gather and tournament measure the references)",
                    f"lune run kit plan {asset}", exempt=True)
    problems, facts = check(asset, root)
    changed = route_gate(asset, root) if "--no-route" not in argv else None
    if changed:  # (a note, never a problem here: kit verify reads this check; kit asset is what refuses the build)
        print(f"  note: its route changed since its lessons were answered ({route_text(changed[0])} -> "
              f"{route_text(changed[1])}): kit asset refuses the build until lune run kit study {asset} --reroute "
              "and each lesson is answered for the new route")
    for p in problems:
        print(f"  - {p}")
    if problems:
        return emit("fail", f"study {asset}: {len(problems)} problem(s): {problems[0]}", problems[0], problems=problems,
                    **facts)
    return emit("pass", f"study {asset}: {facts['refs']} reference(s) read, our version decided, "
                f"{len(facts['lessons'])} lesson(s) applied", f"lune run kit plan {asset}", **facts)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
