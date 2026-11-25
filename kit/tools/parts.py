"""parts.py - the parts libraries' engine (board/plans/archive/2026-11-09-parts-libraries-plan.md, sprint P0; the owner, card
ned6: "each pipeline will kind of be different ... push this beyond the limits").

Every pipeline files its past PARTS under KINDS of part (a turned band, copies round a circle, a planted foot, a
shockwave ring, a health bar, a staircase, a transient), with the code and settings that made each, the lessons that
name it and the owner's verdicts and words on it. A new piece is broken into parts and each part is looked up BY KIND,
across objects - the car rim learns from the wine barrel's staves. One engine (this file), eight SEPARATE libraries:
a lane's kinds live in kit/knowledge/vault/<lane>/parts/kinds.json, its adapter next to its own tools (ADAPTERS), its
index in build/parts/<lane>/ (git-ignored). Departments never share a library.

    python kit/tools/parts.py <lane> kinds [--kind K]                 the vocabulary and the evidence each kind has
    python kit/tools/parts.py <lane> index                            rebuild the lane's index from what is on disk
    python kit/tools/parts.py <lane> find "<words>" [--kind K] [--type T] [--k N]
    python kit/tools/parts.py <lane> plan <piece> [--brief "<words>"] [--dry] [--check] [--k N] [--as WHO]
    python kit/tools/parts.py <lane> label [--merge WHO] [--pool N] [--rerank] [--disagreements]
    python kit/tools/parts.py <lane> eval [--k N] [--rerank]          every method on the labelled set, with its count
    python kit/tools/parts.py <lane> health                           upkeep: empty kinds, unkinded parts, dupes, stale
    python kit/tools/parts.py <lane> credit <piece>                   the owner's verdicts on a piece credit its sheet
    python kit/tools/parts.py <lane> look-allow <piece> --from <past piece> "<words>" [--by owner]

How a part is ranked (the plan's "engine"): words (BM25 over the part's text with its lane, piece and kinds written in
- contextual retrieval) + kind (the same kind scores most, a sibling kind less) + evidence (the owner's verdicts and
words only; a guessed number never counts; a session's ok/fix is correctness, not taste). At most one part from the
same past piece makes the top three. Cards hand over MECHANICS; the look (textures, palettes, frames, ornament, title
treatments) stays hidden unless the owner allowed that piece to reuse that past piece's look (look-allow).
"""

import glob
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import study  # noqa: E402  (the vault's notes and today's 3D matcher: study.retrieve)

LANES = ("3d", "anim", "vfx", "ui", "world", "sfx", "code", "qa")
# each lane's adapter, next to its own tools: it lists the lane's pieces and parts, pulls a part's recipe and media and
# breaks a new piece into parts (a lane without one indexes its lessons, rules and verdicts only, and says so)
ADAPTERS = {
    "3d": "kit/blender/parts_3d.py",
    "anim": "kit/anim/parts_anim.py",
    "vfx": "kit/vfx/parts_vfx.py",
    "ui": "kit/ui/parts_ui.py",
    "world": "kit/world/parts_world.py",
    "sfx": "kit/audio/parts_sfx.py",
    "code": "kit/systems/parts_code.py",
    "qa": "kit/qa/parts_qa.py",
}
W_WORDS, W_KIND, W_EVID = 0.5, 0.35, 0.15  # (the score's three terms; likeness joins per lane in its own sprint)
TOP_CAP = 3  # at most one part from the same past piece in the top three
MAX_PARTS = 8  # a sheet asks about at most this many parts (the owner's time budgets)
LOVED, REJECTED = 7, 3  # the golden set and the graveyard's lines (kit verdict)
POOL = 5  # each method's top answers pooled for the labellers (the P1 bar counts the top 5)
INDEX_VERSION = 1
SHEET_SUFFIX = ".parts-sheet.md"
MEASURABLE = 5  # a lane with fewer labelled questions is "not measurable yet"
# what a session can get today: kit start's first stage, every stage's lessons, the 3D study, the lane's library search
BASELINES = ("today", "today-all", "study", "today-lib")
GENERIC = set("""part piece thing model make made build built side top bottom front back left right small large big
little one two three four five six seven eight nine ten each every both other more less much very really good bad
like look looks looking need needs proper work still also just make sure""".split())


# ------------------------------------------------------------------------------------------------------- words
def toks(text):
    """the kit's words (study.words: lower case, camelCase and snake_case split, stop words dropped) with a plural
    folded for short words too (lips -> lip, legs -> leg: study.words keeps words of 4 letters whole)"""
    out = []
    for w in study.words(text or ""):
        if len(w) == 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def tstr(tokens):
    """a token string padded with spaces, so a phrase is found whole: ' round band ' in ' a round band '"""
    return " " + " ".join(tokens) + " "


class Bm25:
    """Okapi BM25 over token lists (k1 1.2, b 0.75); a query is {term: weight}"""

    K1, B = 1.2, 0.75

    def __init__(self, token_lists):
        self.n = len(token_lists)
        self.lens = [len(t) for t in token_lists]
        self.avg = (sum(self.lens) / self.n) if self.n else 1.0
        self.post = {}
        for i, ts in enumerate(token_lists):
            tf = {}
            for t in ts:
                tf[t] = tf.get(t, 0) + 1
            for t, c in tf.items():
                self.post.setdefault(t, []).append((i, c))
        self.idf = {t: math.log(1.0 + (self.n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.post.items()}

    def scores(self, query):
        out = {}
        for t, wt in query.items():
            post = self.post.get(t)
            if not post:
                continue
            idf = self.idf[t] * wt
            for i, c in post:
                norm = c + self.K1 * (1.0 - self.B + self.B * self.lens[i] / (self.avg or 1.0))
                out[i] = out.get(i, 0.0) + idf * c * (self.K1 + 1.0) / norm
        return out


# ------------------------------------------------------------------------------------------------------- kinds
def kinds_path(root, lane):
    return os.path.join(study.vault_dir(root), lane, "parts", "kinds.json")


def load_kinds(root, lane):
    """the lane's vocabulary: {"axes": {...}, "kinds": [{id, axis, label, words, code, siblings, mechanics, look}],
    "look_fields": [...]}, compiled for matching (an absent file: no kinds, said so by `kinds`)"""
    path = kinds_path(root, lane)
    if not os.path.isfile(path):
        return {"lane": lane, "axes": {}, "kinds": [], "look_fields": [], "_missing": True}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return compile_kinds(data)


def compile_kinds(data):
    for k in data.get("kinds", []):
        phrases = set()
        for w in k.get("words", []) + [k.get("label", "")]:
            t = toks(w)
            if t:
                phrases.add(tstr(t))
        k["_phr"] = sorted(phrases, key=len, reverse=True)
        k["_code"] = [re.compile(p) for p in k.get("code", [])]
    data["_map"] = {k["id"]: k for k in data.get("kinds", [])}
    return data


def kind_hits(kinds, s, code=None):
    """{kind id: hits}: how often each kind's words appear in the token string s (and its code patterns in code)"""
    out = {}
    for k in kinds.get("kinds", []):
        n = sum(s.count(p) for p in k["_phr"])
        if code and k["_code"]:
            n += sum(len(r.findall(code)) for r in k["_code"])
        if n:
            out[k["id"]] = n
    return out


def strength(hits):
    """one mention 0.5, two 0.75, three or more 1.0 (a passing word is not the part's subject)"""
    return min(1.0, 0.5 + 0.25 * (hits - 1)) if hits > 0 else 0.0


def query_kinds(kinds, text):
    """the kinds a part's words ask for"""
    return sorted(kind_hits(kinds, tstr(toks(text))))


def kind_score(doc_kinds, q, kmap):
    """per axis the query names (form, role, finish / limb, phase / ...): the best of the doc's strength on an asked
    kind, or half its strength on a sibling kind; the axes averaged"""
    if not q:
        return 0.0
    axes = {}
    for qi in q:
        k = kmap.get(qi)
        if not k:
            continue
        best = doc_kinds.get(qi, 0.0)
        if not best:
            best = 0.5 * max((doc_kinds.get(s, 0.0) for s in k.get("siblings", [])), default=0.0)
        ax = k.get("axis", "kind")
        axes[ax] = max(axes.get(ax, 0.0), best)
    return sum(axes.values()) / len(axes) if axes else 0.0


# ------------------------------------------------------------------------------------------------------- vault
def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def verdicts(root, lane):
    """the OWNER's verdicts in the lane: [{name, score, direction, guessed, words, date, rel}] (a model's proposal or a
    row not by the owner is never taste)"""
    base = study.vault_dir(root)
    out = []
    for p in sorted(glob.glob(os.path.join(base, lane, "verdicts", "*.md"))):
        front, body = study._front(_read(p))
        if front.get("by") != "owner" or not front.get("name"):
            continue
        score = None
        try:
            score = float(front["score"]) if front.get("score") not in (None, "") else None
        except ValueError:
            score = None
        direction = front.get("direction") or None
        guessed = front.get("source") == "inferred" or front.get("inferred") == "true"
        words = " ".join(re.sub(r"\(scored .*?\)", "", body).split())
        # the order within a day: the note's time stamp, else its file number (x--D.md is the 1st, x--D-6.md the 6th:
        # sorted by name, "-6" comes BEFORE ".md" and a loved 9 read as older than the 2 it replaced - review, P0)
        m = re.search(r"--\d{4}-\d{2}-\d{2}(?:-(\d+))?\.md$", os.path.basename(p))
        seq = int(m.group(1)) if m and m.group(1) else 1
        try:
            stamp = int(front.get("time") or 0)
        except ValueError:
            stamp = 0
        out.append({"name": front["name"], "score": score, "direction": direction, "guessed": guessed,
                    "words": words, "date": front.get("date", ""), "time": stamp, "seq": seq,
                    "build": str(front.get("build") or ""),
                    "rel": os.path.relpath(p, base).replace(os.sep, "/")})
    return out


def judged_this_build(v, build_id, built_at):
    """is verdict `v` on the build that is there now? -> (True / False, why). A build the verdict names (its `build`
    holds the build_id) is; one written AFTER the verdict was not judged (card upjv: a lender rebuilt since his
    verdict still lent on its older score); one written before it is the build he saw"""
    import datetime  # noqa: PLC0415

    if build_id and build_id in (v.get("build") or ""):
        return True, f"his verdict names its build ({build_id})"
    at = float(v.get("time") or 0)
    if not at and v.get("date"):   # (an older note with no time: the END of its day - the benefit of the doubt)
        try:
            day = datetime.datetime.strptime(v["date"], "%Y-%m-%d")
            at = (day + datetime.timedelta(days=1)).timestamp()
        except ValueError:
            at = 0.0
    if at and built_at and float(built_at) > at + 1:
        stamp = datetime.datetime.fromtimestamp(float(built_at)).strftime("%Y-%m-%d %H:%M")
        return False, (f"it was rebuilt ({stamp}) after his verdict of {v.get('date')}"
                       + (f" - he judged build {v['build']}" if v.get("build") else "")
                       + (f", this is {build_id}" if build_id else ""))
    return True, "built before his verdict"


def when(v):
    """a verdict's place in time: its day, then its time stamp, then its number within the day"""
    return (v.get("date") or "", v.get("time") or 0, v.get("seq") or 1)


def verdict_value(v):
    """-1..1 from one verdict: a number (0-10) maps round 5; keep +1, redo -1 (kit/lib/vault.luau's directions);
    a guessed number never counts (None)"""
    if v.get("score") is not None and not v.get("guessed"):
        return max(-1.0, min(1.0, (v["score"] - 5.0) / 5.0))
    if v.get("direction") == "keep":
        return 1.0
    if v.get("direction") == "redo":
        return -1.0
    return None


def citations(root):
    path = os.path.join(root, "board", "citations.json")
    if not os.path.isfile(path):
        return []
    try:
        data = json.loads(_read(path))
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def table_docs(root, lane):
    """the lane's graveyard rows (routes that failed: always "avoid") and golden rows (loved pieces) as cards"""
    base = os.path.join(study.vault_dir(root), lane)
    out = []
    for page, kind in (("graveyard.md", "grave"), ("golden.md", "golden")):
        path = os.path.join(base, page)
        if not os.path.isfile(path):
            continue
        for i, cells in enumerate(study.table_rows(path)):
            if len(cells) < 2 or not cells[0]:
                continue
            title = re.sub(r"\[\[|\]\]", "", cells[0])
            text = " | ".join(c for c in cells[1:] if c and not c.startswith("[["))
            key = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:60]
            out.append({"id": f"{lane}/{kind}/{key}/{i}", "type": kind, "piece": title if len(title) < 40 else None,
                        "title": title, "text": text, "src": f"kit/knowledge/vault/{lane}/{page}",
                        "avoid": kind == "grave"})
    return out


def lesson_docs(root, lane):
    return [{"id": n["id"], "type": "lesson", "piece": None, "title": n["text"][:90], "text": n["text"],
             "src": "kit/knowledge/vault/" + n["rel"], "stages": n.get("stages", [])}
            for n in study.lessons(root, lane)]


def looks_path(root, lane):
    return os.path.join(study.vault_dir(root), lane, "parts", "looks.json")


def look_allows(root, lane):
    path = looks_path(root, lane)
    if not os.path.isfile(path):
        return []
    try:
        data = json.loads(_read(path))
    except ValueError:
        return []
    return [r for r in data if isinstance(r, dict)]


def look_allowed(allows, piece, past):
    """the owner's own record that `piece` may reuse `past`'s look (a model's proposal never counts); a record for a
    move covers its rounds and candidates ('DTDrillSpin' covers 'DTDrillSpin/r2/c6')"""
    chain = {_piece_key(c) for c in _chain(past)}
    for r in allows:
        if (r.get("by") == "owner" and _piece_key(r.get("piece")) == _piece_key(piece)
                and _piece_key(r.get("from")) in chain):
            return r
    return None


# ------------------------------------------------------------------------------------------------------- adapters
def adapter(root, lane):
    """the lane's adapter module (loaded by path: the lanes' tool folders share module names), or None"""
    rel = ADAPTERS.get(lane)
    path = os.path.join(root, rel) if rel else None
    if not path or not os.path.isfile(path):
        path = os.path.join(ROOT, rel) if rel else None  # (a game root reads the kit home's adapter)
    if not path or not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location(f"parts_adapter_{lane}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(path))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(os.path.dirname(path))
    return mod


def _sources(root, lane, ad):
    """every file whose change makes the lane's index stale"""
    base = study.vault_dir(root)
    pats = [os.path.join(base, lane, "lessons", "*.md"), os.path.join(base, lane, "verdicts", "*.md"),
            os.path.join(base, lane, "graveyard.md"), os.path.join(base, lane, "golden.md"),
            os.path.join(base, lane, "parts", "*.json"), os.path.join(root, "board", "citations.json"),
            os.path.join(HERE, "parts.py")]
    if ad is not None:
        pats.append(os.path.abspath(ad.__file__))
        pats += list(ad.sources(root)) if hasattr(ad, "sources") else []
        if hasattr(ad, "homes"):
            pats += [os.path.join(h, pat) for h in ad.homes(root) for pat in sheet_globs(ad)]
    pats.append(os.path.join(root, "build", "parts", lane, "sheets", "*" + SHEET_SUFFIX))
    files = set()
    for p in pats:
        files.update(glob.glob(p, recursive=True))
    return sorted(files)


def signature(files):
    h = hashlib.sha1()
    for p in files:
        try:
            st = os.stat(p)
        except OSError:
            continue
        h.update(f"{p}|{st.st_mtime_ns}|{st.st_size}\n".encode("utf-8", "replace"))
    return h.hexdigest()[:16]


# ------------------------------------------------------------------------------------------------------- sheets
SHEET_PART = re.compile(r"^#{2,3} (\d+)\. (.+)$")  # (## in a stand-alone sheet, ### in the 3D study's Parts section)
CARD_ID = re.compile(r"`([^`\s]+)`")
CARD_LIKE = re.compile(r"^(?:L-[\w]+-[0-9a-f]{6}|[\w]+/[\w]+/\S+)$")  # (a card id: a lesson's, or lane/type/...)


def parse_sheet(text):
    """a parts sheet: {piece, lane, date, parts: [{n, title, kinds, served: [ids], answer, used: [ids], new}]}"""
    front, body = study._front(text)
    mark = re.search(r"<!-- parts: (\d{4}-\d{2}-\d{2})", text)  # (a 3D study's Parts section carries its own date)
    out = {"piece": front.get("piece", ""), "lane": front.get("lane", ""),
           "date": front.get("date", "") or (mark.group(1) if mark else ""),
           "parts": []}
    cur = None
    for line in body.splitlines():
        m = SHEET_PART.match(line.strip())
        if m:
            cur = {"n": int(m.group(1)), "title": m.group(2).strip(), "kinds": [], "served": [], "answer": None,
                   "used": [], "unknown": [], "new": False}
            out["parts"].append(cur)
            continue
        if line.startswith("## "):
            cur = None
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("kinds:"):
            cur["kinds"] = [w for w in re.findall(r"[\w-]+", s[6:].split("(")[0]) if w]
        elif s.startswith("- ") and "`" in s:
            cur["served"] += CARD_ID.findall(s)[:1]
        elif s.lower().startswith("answer:"):
            ans = s[7:].strip()
            cur["answer"] = ans or None
            if ans:
                ticked = CARD_ID.findall(ans)
                named = list(dict.fromkeys(ticked + [w for w in re.findall(r"[\w./-]+", ans) if w in cur["served"]]))
                cur["new"] = bool(re.match(r"(?i)new\b", ans))
                # only a card this part was SHOWN is built from (and credited); `new` credits nothing
                cur["used"] = [] if cur["new"] else [i for i in named if i in cur["served"]]
                cur["unknown"] = [i for i in ticked if i not in cur["served"] and CARD_LIKE.match(i)]
    return out


def check_sheet(sheet):
    """the problems a sheet still has: every part asked must name a card it builds from (one it was shown) or say
    `new` with why (at least 3 words)"""
    problems = []
    for p in sheet["parts"]:
        ans = p.get("answer")
        if not ans:
            problems.append(f"part {p['n']} ({p['title'][:40]}): no answer")
        elif p["new"]:
            why = re.sub(r"(?i)^new\b[\s:,-]*", "", ans)
            if len(toks(why)) < 3:
                problems.append(f"part {p['n']} ({p['title'][:40]}): `new` needs why none of its cards fits")
        elif p.get("unknown"):
            problems.append(f"part {p['n']} ({p['title'][:40]}): the answer names a card this part was not shown "
                            f"({', '.join(p['unknown'][:3])}): build from its own cards, or say `new` and why")
        elif not p["used"]:
            problems.append(f"part {p['n']} ({p['title'][:40]}): the answer names no card it was shown "
                            "(name one by its id, or say `new` and why)")
    return problems


def sheet_globs(ad):
    """the files a lane's answered sheets live in: stand-alone sheets, and the lane's own documents that carry a parts
    section (3D: its studies)"""
    return list(getattr(ad, "SHEET_GLOBS", None) or ["*" + SHEET_SUFFIX])


def sheet_files(root, lane, ad):
    files = []
    if ad is not None and hasattr(ad, "homes"):
        for h in ad.homes(root):
            for pat in sheet_globs(ad):
                files += glob.glob(os.path.join(h, pat))
    files += glob.glob(os.path.join(root, "build", "parts", lane, "sheets", "*" + SHEET_SUFFIX))
    return sorted(set(files))


# ------------------------------------------------------------------------------------------------------- index
def index_path(root, lane):
    return os.path.join(root, "build", "parts", lane, "index.json")


def _piece_key(name):
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def build_index(root, lane, quiet=False):
    """every part, recipe, lesson and graveyard / golden row of the lane, with its kinds, its evidence (the owner's
    verdicts and words, the credit of the sheets that used it) and its context written in"""
    t0 = time.time()
    kinds = load_kinds(root, lane)
    ad = adapter(root, lane)
    files = _sources(root, lane, ad)
    pieces, docs = [], []
    if ad is not None:
        got = ad.collect(root)
        pieces, docs = list(got.get("pieces", [])), list(got.get("docs", []))
    docs += lesson_docs(root, lane)
    docs += table_docs(root, lane)
    seen = set()
    uniq = []
    for d in docs:
        if d["id"] in seen:
            continue
        seen.add(d["id"])
        uniq.append(d)
    docs = uniq
    vkey = getattr(ad, "verdict_key", None) if ad is not None else None
    # the owner's words reach a part by its name, or by a kind word on the lane's part axes ("the spokes are too thin"
    # -> the piece's spoke parts; 3D: the role axis, so "metal" or "edge" never names every part)
    part_axes = set(kinds.get("part_axes", []))
    # (a word that names no part on its own - "body", "band", "point", "frame of the scene" - never names one: the
    #  owner's "round-body + colour-band route" is about a route, not the barrel's hoops; fresh review, P1)
    loose = {t for w in kinds.get("name_words_ignore", []) for t in toks(w)}
    by_piece = {}
    for v in verdicts(root, lane):
        key = _piece_key(vkey(v["name"]) if vkey else v["name"])
        named = kind_hits(kinds, tstr([t for t in toks(v["words"]) if t not in loose])) if part_axes else {}
        v["kinds"] = {k for k in named if kinds["_map"][k].get("axis") in part_axes}
        by_piece.setdefault(key, []).append(v)
    # lessons: the owner's verdicts on the pieces each was cited on (served at half weight), as kit/lib/vault.luau
    lesson_ev = {}
    for c in citations(root):
        if c.get("dept") not in (None, lane) or not isinstance(c.get("lessons"), list):
            continue
        for v in by_piece.get(_piece_key(c.get("name")), []):
            if v["date"] < (c.get("date") or ""):
                continue
            val = verdict_value(v)
            if val is None:
                continue
            for lid in c["lessons"]:
                lesson_ev.setdefault(lid, []).append((val, 0.5 if c.get("served") else 1.0))
    credit = sheet_credit(root, lane, ad, by_piece)
    for d in docs:
        text = d.get("text", "") or ""
        code = d.get("code")
        hits = kind_hits(kinds, tstr(toks(f"{d.get('title', '')} {text}")), code)
        dk = {k: strength(n) for k, n in hits.items()}
        for k, s in (d.get("kinds") or {}).items():  # (an adapter's structured kinds: a layer's technique, a role)
            if k in kinds["_map"]:
                dk[k] = max(dk.get(k, 0.0), float(s))
        d["kinds"] = dict(sorted(dk.items()))
        labels = " ".join(kinds["_map"][k].get("label", k) for k in d["kinds"])
        d["toks"] = toks(f"{lane} {d.get('piece') or ''} {labels} {d.get('title', '')} {text}")
        d.pop("code", None)  # (the code itself stays in its file: the card points at it)
        evidence_for(d, by_piece, lesson_ev, credit)
        if len(text) > 700:
            d["text"] = text[:700] + " ..."
    index = {"version": INDEX_VERSION, "lane": lane, "built": time.strftime("%Y-%m-%d %H:%M:%S"),
             "sig": signature(files), "files": len(files), "adapter": ADAPTERS.get(lane) if ad else None,
             "pieces": pieces, "docs": docs, "seconds": round(time.time() - t0, 2)}
    path = index_path(root, lane)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # (atomic: several sessions share one checkout, and a reader never sees half an index)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f)
    os.replace(tmp, path)
    return index


def _chain(piece):
    """a piece and the pieces it belongs to, most specific first: 'Move/r0/c3' -> ['Move/r0/c3', 'Move/r0', 'Move']
    (a round's "All bad" reaches each of its candidates; a 3D piece has no parent)"""
    bits = [b for b in (piece or "").split("/") if b]
    return ["/".join(bits[:i]) for i in range(len(bits), 0, -1)]


def evidence_for(d, by_piece, lesson_ev, credit):
    """a card's evidence: the owner's verdicts on its piece (a part named in the owner's words, or a card that IS the
    whole piece - a candidate, a clip: full weight; another part of the piece: half; a verdict on the round or move it
    belongs to: halved again per level), the owner's own rating stored with it (a clip's love / bad), the owner's
    verdicts on the pieces a lesson was cited on, and the credit of the sheets that built from it. -1..1; "avoid" when
    the newest valued verdict at the most specific level is a rejection (or it is a graveyard row)"""
    rows, owner = [], []
    piece = d.get("piece")
    whole = bool(d.get("whole"))
    # (research - a dossier's measured phases, its mistakes - is knowledge, never judged by a verdict on a build)
    if piece and d["type"] not in ("lesson", "grave") and not d.get("research"):
        title_words = {w for w in toks(d.get("title", "")) if len(w) >= 4 and w not in GENERIC}
        for depth, name in enumerate(_chain(piece)):
            # the newest of the owner's verdicts weighs most, each older one half the next (a piece reworked until it
            # was loved reads as loved: Katana4Kiriage 2, 2, 2, 2, 2, then 9)
            valued_here = 0
            strong = {k for k, s in (d.get("kinds") or {}).items() if s >= 0.75}  # (its own kinds, not a passing word)
            for v in sorted(by_piece.get(_piece_key(name), []), key=when, reverse=True):
                val = verdict_value(v)
                named = (not whole and depth == 0 and d["type"] == "part"
                         and bool(title_words & set(toks(v["words"])) or (v.get("kinds") or set()) & strong))
                owner.append({"score": v["score"], "direction": v["direction"], "guessed": v["guessed"],
                              "words": v["words"][:240], "date": v["date"], "time": v.get("time", 0),
                              "seq": v.get("seq", 1), "part": named or (whole and depth == 0), "depth": depth,
                              "on": name})
                if val is not None:
                    rows.append((val, (1.0 if (named or whole) else 0.5) * (0.5 ** depth) * (0.5 ** valued_here)))
                    valued_here += 1
    for v in d.pop("verdicts", None) or []:  # (the adapter's: the owner's rating kept with the piece itself)
        val = verdict_value(v)
        owner.append({"score": v.get("score"), "direction": v.get("direction"), "guessed": bool(v.get("guessed")),
                      "words": (v.get("words") or "")[:240], "date": v.get("date", ""), "part": True, "depth": 0,
                      "on": piece})
        if val is not None:
            rows.append((val, 1.0))
    if d["type"] == "lesson":
        rows += lesson_ev.get(d["id"], [])
    c = credit.get(d["id"])
    if c:
        h, x = c["helpful"], c["harmful"]
        if h + x:
            rows.append(((h - x) / (h + x), min(1.0, (h + x) / 2.0)))
        d["credit"] = c
    wsum = sum(w for _v, w in rows)
    d["evidence"] = round(sum(v * w for v, w in rows) / wsum, 3) if wsum else 0.0
    valued = [o for o in owner if verdict_value(o) is not None]
    if valued:
        top = min(o["depth"] for o in valued)
        newest = sorted((o for o in valued if o["depth"] == top), key=when)[-1]
        if verdict_value(newest) <= (REJECTED - 5.0) / 5.0:
            d["avoid"] = True
    owner.sort(key=lambda o: (o["depth"],) + when(o))
    d["owner"] = [o for o in owner if o["depth"] == 0][-3:] or owner[:2]
    d.setdefault("avoid", False)


def sheet_credit(root, lane, ad, by_piece):
    """{card id: {helpful, harmful, pieces}}: a card a sheet BUILT FROM (its answer named it) gains a helpful count from
    the owner's later verdict >= 7 (or keep) on that piece and a harmful one from a verdict <= 3 (or redo); a guessed
    number never counts (ACE's helpful / harmful counters, from the owner's verdicts only)"""
    out = {}
    for path in sheet_files(root, lane, ad):
        text = _read(path)
        if path.endswith(".study.md"):  # (only its Parts section is a sheet; a study written before it has none)
            m = re.search(r"(?ms)^## Parts\s*$(.*?)(?=^## |\Z)", text)
            if not m or "<!-- parts:" not in m.group(1):
                continue
            text = m.group(1)
        sheet = parse_sheet(text)
        if not sheet["piece"]:
            sheet["piece"] = os.path.basename(path).split(".")[0]
        vs = sorted((v for v in by_piece.get(_piece_key(sheet["piece"]), []) if v["date"] >= (sheet["date"] or "")),
                    key=when)
        vals = [verdict_value(v) for v in vs]
        vals = [x for x in vals if x is not None]
        if not vals:
            continue
        final = vals[-1]
        for p in sheet["parts"]:
            for cid in p["used"]:
                c = out.setdefault(cid, {"helpful": 0, "harmful": 0, "pieces": []})
                if final >= (LOVED - 5.0) / 5.0:
                    c["helpful"] += 1
                elif final <= (REJECTED - 5.0) / 5.0:
                    c["harmful"] += 1
                c["pieces"].append(sheet["piece"])
    return out


class Index:
    """the lane's loaded index: its docs, the BM25 over their contextual words and the kinds"""

    def __init__(self, root, lane, data, kinds):
        self.root, self.lane, self.data, self.kinds = root, lane, data, kinds
        self.docs = data["docs"]
        self.bm = Bm25([d["toks"] for d in self.docs])
        self.by_kind = {}
        for i, d in enumerate(self.docs):
            for k in d["kinds"]:
                self.by_kind.setdefault(k, []).append(i)
        self.allows = look_allows(root, lane)


def load_index(root, lane, rebuild=False):
    """the lane's index, rebuilt when any of its sources changed (a look-up never reads a stale library)"""
    kinds = load_kinds(root, lane)
    path = index_path(root, lane)
    data = None
    if not rebuild and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except ValueError:
            data = None
        if data and (data.get("version") != INDEX_VERSION
                     or data.get("sig") != signature(_sources(root, lane, adapter(root, lane)))):
            data = None
    rebuilt = data is None
    if rebuilt:
        data = build_index(root, lane)
    idx = Index(root, lane, data, kinds)
    idx.rebuilt = rebuilt
    return idx


# ------------------------------------------------------------------------------------------------------- search
def search(idx, query, k=8, kinds=None, types=None, exclude=None, cap=True, context="", words_only=False):
    """the lane's best cards for one part: [(score, doc, parts)] best first. `query`: the part's words; `context`: the
    piece's own words (half weight); `kinds`: the kinds asked (default: the ones the words name); `exclude`: the
    piece being planned (never its own parts); `words_only`: BM25 alone (the ablation in eval)"""
    q = {}
    for t in toks(context):
        q[t] = max(q.get(t, 0.0), 0.5)
    for t in toks(query):
        q[t] = 1.0
    asked = [] if words_only else (kinds if kinds is not None else query_kinds(idx.kinds, f"{query}"))
    bm = idx.bm.scores(q)
    best = max(bm.values()) if bm else 0.0
    cand = set(bm)
    kmap = idx.kinds.get("_map", {})
    for qi in asked:
        cand.update(idx.by_kind.get(qi, []))
        for s in kmap.get(qi, {}).get("siblings", []):
            cand.update(idx.by_kind.get(s, []))
    ex = _piece_key(exclude) if exclude else None
    hidden = set(idx.kinds.get("look_types", []))  # (look assets - a texture, a mesh - are never handed over)
    scored = []
    for i in cand:
        d = idx.docs[i]
        if types and d["type"] not in types:
            continue
        if not types and d["type"] in hidden:
            continue
        # (never the piece's own cards - a move's candidates 'Move/r2/c6' included)
        if ex and ex in {_piece_key(c) for c in _chain(d.get("piece"))}:
            continue
        w = (bm.get(i, 0.0) / best) if best else 0.0
        ks = 0.0 if words_only else kind_score(d["kinds"], asked, kmap)
        if w <= 0.0 and ks <= 0.0:
            continue
        ev = 0.0 if words_only else d.get("evidence", 0.0)
        s = W_WORDS * w + W_KIND * ks + W_EVID * ev
        scored.append((s, i, {"words": round(w, 3), "kind": round(ks, 3), "evidence": ev}))
    scored.sort(key=lambda x: (-x[0], idx.docs[x[1]]["id"]))
    ranked = [(s, idx.docs[i], parts) for s, i, parts in scored]
    return diversify(ranked, k) if cap else ranked[:k]


def diversify(ranked, k, top=TOP_CAP):
    """at most one card from the same past piece in the top `top`; the rest keep their order after it"""
    head, rest, keys = [], [], set()
    for row in ranked:
        d = row[1]
        chain = _chain(d.get("piece"))
        key = _piece_key(chain[-1]) if chain else d["id"]  # (a move's candidates count as one past piece)
        if len(head) < top and key not in keys:
            head.append(row)
            keys.add(key)
        else:
            rest.append(row)
        if len(head) >= top and len(head) + len(rest) >= k:
            break
    return (head + rest)[:k]


def interleave(lists, k):
    """round-robin over per-part result lists, first seen wins, cut at k (a piece's answer at the same budget as a
    whole-piece search: the fair probe's rule)"""
    out, seen = [], set()
    depth = max((len(x) for x in lists), default=0)
    for r in range(depth):
        for lst in lists:
            if r < len(lst):
                d = lst[r][1]
                if d["id"] not in seen:
                    seen.add(d["id"])
                    out.append(lst[r])
                    if len(out) >= k:
                        return out
    return out


# ------------------------------------------------------------------------------------------------------- breakdown
def split_brief(text):
    """a brief's words split into part clauses: 'car wheel rim: a round alloy rim, five spokes from a centre hub ...'
    -> the head (the piece's own words) and one clause per comma / semicolon / sentence"""
    s = " ".join((text or "").split())
    head, sep, rest = s.partition(":")
    if sep and len(head.split()) <= 6 and rest.strip():
        body = rest
    else:
        head, body = "", s
    parts = []
    for c in re.split(r"[;\n]|(?<!\d)\.(?!\d)|,(?![^()]*\))", body):
        c = c.strip(" -*")
        if toks(c):
            parts.append({"title": c[:90], "words": c, "hero": False})
    return head.strip(), parts


def breakdown(idx, ad, piece, text):
    """the piece's parts: the lane's own breakdown when its adapter has one (a brief's parts list, a dossier's phases x
    limbs, a scene breakdown's layers ...), else the brief's clauses; each part with the kinds its words ask for"""
    head, parts = split_brief(text)
    if ad is not None and hasattr(ad, "breakdown"):
        got = ad.breakdown(idx.root, piece, text)
        if got:
            parts = got
    for p in parts:
        p["kinds"] = sorted(set(p.get("kinds") or []) | set(query_kinds(idx.kinds, p["words"])))
    return head or piece.replace("_", " "), parts


def piece_search(idx, ad, piece, text, k=POOL, types=None, words_only=False, per_part=None):
    """a whole piece looked up part by part, interleaved to k (the engine's answer in eval)"""
    head, parts = breakdown(idx, ad, piece, text)
    if not parts:
        return search(idx, text, k=k, types=types, exclude=piece, words_only=words_only)
    lists = [search(idx, p["words"], k=per_part or k, kinds=None if words_only else p["kinds"], types=types,
                    exclude=piece, context=head, words_only=words_only) for p in parts]
    return interleave(lists, k)


def matters(parts, results):
    """the parts a sheet asks about (at most MAX_PARTS): the hero parts first, then the parts whose cards hold an
    "avoid", then the rest in the brief's order; every other part keeps its suggested kinds and needs no answer"""
    order = []
    for i, p in enumerate(parts):
        avoid = any(row[1].get("avoid") for row in results[i])
        order.append((0 if p.get("hero") else (1 if avoid else 2), 0 if p["kinds"] else 1, i))
    order.sort()
    keep = sorted(i for *_x, i in order[:MAX_PARTS])
    return keep, sorted(i for *_x, i in order[MAX_PARTS:])


# ------------------------------------------------------------------------------------------------------- cards
def evidence_note(d):
    bits = []
    for o in d.get("owner", [])[-2:]:
        val = verdict_value(o)
        num = (f"{o['score']:g}/10" if o.get("score") is not None else (o.get("direction") or "words"))
        tag = " guessed" if o.get("guessed") else ""
        where = "this part" if o.get("part") else "its piece"
        words = f' "{o["words"][:90]}"' if o.get("words") else ""
        bits.append(f"owner on {where} {o['date']}: {num}{tag}{words}" if val is not None or o.get("words") else "")
    c = d.get("credit")
    if c:
        bits.append(f"built from on {len(c['pieces'])} piece(s): {c['helpful']} loved, {c['harmful']} rejected")
    bits = [b for b in bits if b]
    if not bits:
        return "unjudged" if d["type"] in ("part", "recipe") else ""
    return "; ".join(bits)


def card(idx, d, parts=None, for_piece=None, full=False):
    """one card as a line: type, id, what, where, evidence. Mechanics only, unless the owner allowed this piece to
    reuse that past piece's look"""
    kmap = idx.kinds.get("_map", {})
    ks = ", ".join(kmap[k].get("label", k) if full else k for k in d["kinds"]) or "no kind"
    lead = "AVOID " if d.get("avoid") else ""
    title = d.get("title", "")[:100]
    piece = f" [{d['piece']}]" if d.get("piece") and d["type"] in ("part", "recipe") else ""
    line = f"{lead}[{d['type']}] `{d['id']}`{piece} {title} - kinds: {ks}"
    allow = look_allowed(idx.allows, for_piece, d.get("piece")) if (for_piece and d.get("look")) else None
    src = d.get("src") or ""
    hidden = [str(v) for v in (d.get("look") or {}).values() if v and not isinstance(v, (int, float))]
    if src and not allow and any(h and (h in src or os.path.basename(h) in src) for h in hidden):
        src = os.path.dirname(src.split(" ")[0])  # (a path naming the look itself - an art file - would leak it)
    if src:
        line += f" - {src}"
    ev = evidence_note(d)
    if ev:
        line += f" - {ev}"
    mech = d.get("mech")
    if mech:
        line += " - mechanics: " + "; ".join(f"{k}={v}" for k, v in list(mech.items())[:6])
    if d.get("look"):
        if allow:
            line += (" - LOOK REUSE (the owner allowed it: \"" + allow.get("words", "")[:60] + "\"): " +
                     "; ".join(f"{k}={v}" for k, v in list(d["look"].items())[:4]))
        else:
            line += " - look hidden (mechanics only)"
    if parts:
        line += f" ({parts['words']:.2f} words, {parts['kind']:.2f} kind, {parts['evidence']:+.2f} evidence)"
    return line


# ------------------------------------------------------------------------------------------------------- plan
def sheet_path(root, lane, ad, piece):
    if ad is not None and hasattr(ad, "home"):
        h = ad.home(root, piece)
        if h:
            return os.path.join(h, piece + SHEET_SUFFIX)
    return os.path.join(root, "build", "parts", lane, "sheets", piece + SHEET_SUFFIX)


def write_sheet(idx, lane, piece, head, parts, results, keep, rest, by):
    lines = ["---", "kind: parts-sheet", f"lane: {lane}", f"piece: {piece}", f"date: {time.strftime('%Y-%m-%d')}",
             f"by: {by}", "---", "", f"# Parts sheet: {piece} ({lane})", "",
             f"Made by `kit parts {lane} plan {piece}` from the brief ({head}). " + ANSWER_HOW.format(lane=lane), ""]
    lines += part_lines(idx, piece, parts, results, keep, rest, heading="##")
    return "\n".join(lines)


ANSWER_HOW = ("Answer each part below: the card you build it from (its id in backticks), or `new` and why none fits. "
              "Cards hand over MECHANICS (how it was built, timing, sizes, what went wrong); the look is not reused "
              "unless the owner allowed it (`kit parts {lane} look-allow`). AVOID cards are what the owner rejected: "
              "read why before building. Know-how cards are the helpers and loved builds that already do that kind "
              "of part's job.")


def part_lines(idx, piece, parts, results, keep, rest, heading="##"):
    """the sheet's parts: each asked part with its kinds, its cards, its know-how and an answer line; the rest with
    their suggested kinds (the stand-alone sheet uses `##`, the 3D study's Parts section `###`)"""
    lines = []
    kmap = idx.kinds.get("_map", {})
    for n, i in enumerate(keep, 1):
        p = parts[i]
        ks = ", ".join(f"{k} ({kmap[k].get('axis', 'kind')})" for k in p["kinds"] if k in kmap) or "none named"
        lines += [f"{heading} {n}. {p['title']}", f"kinds: {ks}"]
        if not results[i]:
            lines.append("- (no card: nothing in the library matches these words or kinds yet)")
        shown = set()
        for _s, d, parts_ in results[i]:
            lines.append("- " + card(idx, d, parts_, for_piece=piece))
            shown.add(d["id"])
        for d in know_how(idx, p["kinds"], shown, exclude=piece):
            lines.append("- know-how: " + card(idx, d, for_piece=piece))
        lines += ["answer: ", ""]
    if rest:
        lines += [f"{heading} Other parts (no answer needed)"]
        for i in rest:
            lines.append(f"- {parts[i]['title']}: kinds {', '.join(parts[i]['kinds']) or 'none named'}")
        lines.append("")
    return lines


def know_how(idx, kinds, shown, exclude=None, n=2):
    """the helpers that already do this kind of part's job (the plan's know-how cards: copies round a circle ->
    rivet_ring, rbx_lathe.staves), ranked by the kind's own words - never one already shown. Loved builds' parts are
    not repeated here: their evidence already lifts them among the cards (a loved pistol's slide is no know-how for a
    lamp's plinth just because both are cast metal)"""
    axes = set(idx.kinds.get("knowhow_axes", []))  # (3D: form and role - a finish is no reason for a helper)
    kmap = idx.kinds.get("_map", {})
    kinds = [k for k in kinds if not axes or kmap.get(k, {}).get("axis") in axes]
    if not kinds:
        return []
    words = " ".join(kmap_labels(idx, kinds))
    rows = search(idx, words, k=n + 4, kinds=list(kinds), types=("helper",), exclude=exclude, cap=False)
    return [d for _s, d, _p in rows if d["id"] not in shown and d["kinds"].keys() & set(kinds)][:n]


def kmap_labels(idx, kinds):
    """a part's kinds in the kit's own words (their labels and words): what a helper's docstring says when it does
    that job"""
    kmap = idx.kinds.get("_map", {})
    out = []
    for k in kinds:
        if k in kmap:
            out.append(kmap[k].get("label", k))
            out += kmap[k].get("words", [])[:6]
    return out


# ------------------------------------------------------------------------------------------------------- labels
def questions_path(root, lane):
    return os.path.join(study.vault_dir(root), lane, "parts", "questions.json")


def labels_path(root, lane):
    return os.path.join(study.vault_dir(root), lane, "parts", "labels.json")


def eval_path(root, lane):
    return os.path.join(study.vault_dir(root), lane, "parts", "eval.json")


def rerank_hint(lane):
    """why the last look-up fell back to the plain order, and how to warm the re-ranker (kit/tools/parts_rerank.py)"""
    why = (sys.modules["parts_rerank"].LAST.get("why") if "parts_rerank" in sys.modules else "") or "it was not used"
    if "has not loaded" in why:
        how = f"warm it once: lune run kit parts {lane} find \"<words>\" --rerank (the worker loads it, ~20 s)"
    elif "failed" in why:
        how = "check it: lune run kit vision serve --status"
    else:
        how = "start one: lune run kit vision serve"
    return f"the replay showed the local re-ranker beats the plain look-up in {lane}, but {why}: {how}"


def use_rerank(root, lane, flags):
    """--rerank: always (loaded here if no worker runs); --plain: never; otherwise where the lane's replay showed the
    re-ranker beats the plain look-up (then only warm: a sheet never waits on a model loading)"""
    if flags.get("plain"):
        return False
    return bool(flags.get("rerank")) or rerank_shown(root, lane)


def rerank_shown(root, lane):
    """the lane's last full eval showed the local re-ranker beating the plain engine (under both readings): the choice
    `--rerank` makes"""
    rec = load_json(eval_path(root, lane), {})
    return "engine" in (rec.get("beats") or {}).get("engine + rerank", [])


def load_json(path, default):
    if not os.path.isfile(path):
        return default
    try:
        return json.loads(_read(path))
    except ValueError:
        return default


def save_json(path, data):
    """written whole or not at all (labels, look records: a reader never sees half a file)"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def kappa(pairs):
    """Cohen's kappa and raw agreement over [(a, b)] labels 0/1"""
    n = len(pairs)
    if not n:
        return None, None
    agree = sum(1 for a, b in pairs if a == b) / n
    pa = sum(a for a, _b in pairs) / n
    pb = sum(b for _a, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    k = (agree - pe) / (1 - pe) if pe < 1 else 1.0
    return round(k, 3), round(agree, 3)


def methods(root, lane, idx, ad, qs, k, rerank=False):
    """every method's top k for every question: {method: {qid: [ids]}}. "today" = the lane's lesson ranking as a
    session gets it (kit/lib/vault.luau Vault.rank, written to build/parts/<lane>/today.json by `kit parts`); "study"
    (3D) = the study step's matcher with its object filter; "words" = BM25 over the same cards without kinds or
    evidence (the ablation); "engine lessons" = the engine on lessons only; "engine" = the engine on every card"""
    today = load_json(os.path.join(root, "build", "parts", lane, "today.json"), {})
    out = {}
    for name in ("today", "today-all"):  # (kit/lib/parts.luau Parts.writeToday: kit start --for's own ranking)
        if isinstance(today.get(name), dict):
            out[name] = {q["id"]: list(today[name].get(q["id"], []))[:k] for q in qs}
    if ad is not None and hasattr(ad, "today_lib"):
        # the lane's own library search as a session types it: the question's keywords (written with the question)
        out["today-lib"] = {q["id"]: ad.today_lib(root, q.get("keywords") or " ".join(toks(q["brief"])), k)
                            for q in qs}
    if lane == "3d":
        # the study step as a session runs it (study.query_of / core_of), the question's brief as its `- what:` line:
        # real what-lines are that long (81 briefs, 2026-11-09: median 27 words, middle half 20-59 - "a cast-iron gas
        # lamp standard carrying a gothic lantern ..."), and the what-line also makes the study's object filter
        docs = study.lessons(root, "3d")
        out["study"] = {}
        for q in qs:
            brief_text = f"- what: {q['brief']}\n"
            hits = study.retrieve(study.query_of(q["piece"], brief_text), docs, k=k,
                                  core=study.core_of(q["piece"], brief_text))
            out["study"][q["id"]] = [d["id"] for _s, d in hits]
    out["words"] = {q["id"]: [d["id"] for _s, d, _p in piece_search(idx, ad, q["piece"], q["brief"], k=k,
                                                                      words_only=True)] for q in qs}
    out["engine lessons"] = {q["id"]: [d["id"] for _s, d, _p in piece_search(idx, ad, q["piece"], q["brief"], k=k,
                                                                               types=("lesson",))] for q in qs}
    out["engine"] = {q["id"]: [d["id"] for _s, d, _p in piece_search(idx, ad, q["piece"], q["brief"], k=k)]
                     for q in qs}
    if rerank:
        # exactly what a sheet serves (fresh review, P1): each part's own pool of RERANK_POOL re-ranked against that
        # part's words - one call for every question's parts - then the parts interleaved to k, as piece_search does
        jobs, owners = [], []
        for q in qs:
            head, parts = breakdown(idx, ad, q["piece"], q["brief"])
            for p in parts or [{"words": q["brief"], "kinds": query_kinds(idx.kinds, q["brief"])}]:
                jobs.append((f"{head}: {p['words']}", search(idx, p["words"], k=RERANK_POOL, kinds=p["kinds"],
                                                              exclude=q["piece"], context=head)))
                owners.append(q["id"])
        got = rerank_rows(jobs, k, cold=True)
        per_q = {}
        for qid, rows in zip(owners, got or []):
            per_q.setdefault(qid, []).append(rows)
        out["engine + rerank"] = {q["id"]: [d["id"] for _s, d, _p in interleave(per_q.get(q["id"], []), k)]
                                  for q in qs}
    return out


RERANK_POOL = 15  # the plain look-up's best this many per part go to the re-ranker


def rerank_rows(queries_rows, k, cold=True):
    """[(query, rows)] -> each list re-ordered by the local re-ranker (kit/tools/parts_rerank.py: one batched call for
    every list - a whole sheet at once, warm when the vision worker runs), the top-three cap kept, cut to k; None when
    no worker runs and `cold` is off"""
    import parts_rerank  # noqa: PLC0415  (the model loads only when asked, or answers warm from the worker)

    flat = [(qi, query, row) for qi, (query, rows) in enumerate(queries_rows) for row in rows]
    got = parts_rerank.scores_many([(query, card_text(row[1])) for _qi, query, row in flat], cold=cold)
    if got is None:
        return None
    out = []
    for qi, (_query, rows) in enumerate(queries_rows):
        mine = [(g, -i, row) for i, ((q2, _q, row), g) in enumerate((f, g) for f, g in zip(flat, got) if f[0] == qi)]
        mine.sort(key=lambda x: (-x[0], -x[1]))
        out.append(diversify([row for _g, _i, row in mine], k))
    return out


def card_text(d):
    """a card as a labeller or the re-ranker reads it: what it is, its words and, for code, the code itself"""
    code = f" Code: {d['snippet']}" if d.get("snippet") else ""
    return f"{d['type']}: {d.get('title', '')}. {d.get('text', '')[:420]}{code}"[:900]


def blind_sheet(idx, qs, runs, labels, who, seed=7):
    """the labeller's sheet: per question the brief and every pooled card not yet labelled by `who`, shuffled, no
    method named -> (markdown, key {qid: {n: id}})"""
    by_id = {d["id"]: d for d in idx.docs}
    md = [f"# Blind labels ({who}): is each card USEFUL for building this new piece?", "",
          "For each question, mark each numbered card 1 (useful: it says how to build, size, time or avoid something "
          "this piece really has) or 0 (not useful: off the point, or only shares a word). Judge the card alone; you "
          "are not told which search found it. Answer as JSON: {\"<question id>\": {\"<n>\": 0 or 1, ...}, ...}.", ""]
    key = {}
    for q in qs:
        pool = []
        for m in runs.values():
            for cid in m.get(q["id"], []):
                if cid not in pool:
                    pool.append(cid)
        done = labels.get(q["id"], {})
        pool = [c for c in pool if who not in done.get(c, {})]
        if not pool:
            continue
        rnd = random.Random(f"{seed}:{q['id']}:{who}")
        rnd.shuffle(pool)
        md += [f"## {q['id']}: {q['piece']}", f"brief: {q['brief']}", ""]
        key[q["id"]] = {}
        for n, cid in enumerate(pool, 1):
            d = by_id.get(cid)
            text = card_text(d) if d else f"(card {cid} is no longer in the library)"
            md.append(f"{n}. {' '.join(text.split())[:420]}")
            key[q["id"]][str(n)] = cid
        md.append("")
    return "\n".join(md), key


def score_runs(runs, labels, k):
    """per method: [(qid, strict hits, lenient hits, unjudged)] over the questions both labellers finished"""
    out = {}
    for m, per_q in runs.items():
        rows = []
        for qid, ids in per_q.items():
            lab = labels.get(qid)
            if not lab:
                continue
            strict = lenient = unjudged = 0
            for cid in ids[:k]:
                v = lab.get(cid)
                if not v or "a" not in v or "b" not in v:
                    unjudged += 1
                    continue
                strict += 1 if (v["a"] and v["b"]) else 0
                lenient += 1 if (v["a"] or v["b"]) else 0
            rows.append((qid, strict, lenient, unjudged, len(ids[:k])))
        out[m] = rows
    return out


# ------------------------------------------------------------------------------------------------------- health
def health(idx):
    """upkeep (SkillOps): kinds with no card, cards with no kind, duplicate texts, recipes whose file or line is gone,
    kinds with no owner evidence"""
    docs = idx.docs
    kmap = idx.kinds.get("_map", {})
    empty = [k for k in kmap if not idx.by_kind.get(k)]
    unkinded = [d for d in docs if not d["kinds"] and d["type"] in ("part", "recipe")]
    texts = {}
    for d in docs:
        t = " ".join(d.get("toks", [])[:60])
        if len(t) > 40:
            texts.setdefault(t, []).append(d["id"])
    dupes = [v for v in texts.values() if len(v) > 1]
    stale = []
    for d in docs:
        if d["type"] != "recipe" or not d.get("src"):
            continue
        path, _sep, line = d["src"].split(" ")[0].partition(":")  # ("file:line" or "file dna.heel" / "file layers[3]")
        full = os.path.join(idx.root, path)
        if not os.path.isfile(full):
            stale.append(d["id"])
        elif line.isdigit():
            with open(full, encoding="utf-8", errors="replace") as f:
                if sum(1 for _ in f) < int(line):
                    stale.append(d["id"])
    unevidenced = [k for k in kmap if idx.by_kind.get(k)
                   and not any(idx.docs[i].get("evidence") for i in idx.by_kind[k])]
    return {"empty": empty, "unkinded": unkinded, "dupes": dupes, "stale": stale, "unevidenced": unevidenced}


# ------------------------------------------------------------------------------------------------------- cli
def emit(status, summary, next_action, lines=None, **extra):
    print(json.dumps({"status": status, "summary": summary, "next_action": next_action, "lines": lines or [],
                      **extra}))
    return 0 if status == "pass" else 1


def parse_args(argv):
    args, flags = [], {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            name = a[2:]
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                flags[name] = argv[i + 1]
                i += 2
                continue
            flags[name] = True
        else:
            args.append(a)
        i += 1
    return args, flags


def cmd_kinds(root, lane, idx, flags):
    kinds = idx.kinds
    if kinds.get("_missing"):
        return emit("fail", f"parts {lane} kinds: no vocabulary yet ({kinds_path(root, lane)})",
                    f"write kit/knowledge/vault/{lane}/parts/kinds.json (P0 drafts every lane's from its code)")
    lines = []
    for ax, what in kinds.get("axes", {}).items():
        lines.append(f"{ax}: {what}")
    for k in kinds["kinds"]:
        if flags.get("kind") and k["id"] != flags["kind"]:
            continue
        ids = idx.by_kind.get(k["id"], [])
        ds = [idx.docs[i] for i in ids]
        types = {}
        for d in ds:
            types[d["type"]] = types.get(d["type"], 0) + 1
        loved = sum(1 for d in ds if d.get("evidence", 0) > 0.2)
        avoid = sum(1 for d in ds if d.get("avoid"))
        lines.append(f"{k['id']} ({k.get('axis', 'kind')}): {k.get('label', '')} - {len(ds)} card(s) "
                     f"{dict(sorted(types.items()))}, {loved} with the owner's good word, {avoid} avoid")
        if flags.get("kind"):
            lines.append("  words: " + ", ".join(k.get("words", [])))
            for i in ids[:12]:
                lines.append("  " + card(idx, idx.docs[i]))
    n = len(kinds["kinds"])
    return emit("pass", f"parts {lane} kinds: {n} kind(s) on {len(kinds.get('axes', {}))} axis(es), "
                f"{len(idx.docs)} card(s) indexed", f"lune run kit parts {lane} find \"<a part's words>\"", lines)


def cmd_index(root, lane, flags):
    data = build_index(root, lane)
    types = {}
    for d in data["docs"]:
        types[d["type"]] = types.get(d["type"], 0) + 1
    kinded = sum(1 for d in data["docs"] if d["kinds"])
    ad_note = f"adapter {data['adapter']}" if data.get("adapter") else "NO adapter yet (lessons, rows, verdicts only)"
    lines = [f"cards: {dict(sorted(types.items()))}", f"with a kind: {kinded}/{len(data['docs'])}",
             f"pieces: {len(data['pieces'])}; sources: {data['files']} file(s); {ad_note}"]
    return emit("pass", f"parts {lane} index: {len(data['docs'])} card(s) from {len(data['pieces'])} piece(s) in "
                f"{data['seconds']} s", f"lune run kit parts {lane} kinds", lines,
                cards=len(data["docs"]), pieces=len(data["pieces"]), seconds=data["seconds"])


def cmd_find(root, lane, idx, args, flags):
    words = " ".join(args)
    if not words:
        return emit("fail", f"parts {lane} find: say what the part is", f"lune run kit parts {lane} find \"<words>\"")
    k = int(flags.get("k", 8))
    types = tuple(flags["type"].split(",")) if isinstance(flags.get("type"), str) else None
    kinds = flags["kind"].split(",") if isinstance(flags.get("kind"), str) else None
    pool = search(idx, words, k=RERANK_POOL, kinds=kinds, types=types)
    rows, how = pool[:k], "plain"
    if use_rerank(root, lane, flags):
        got = rerank_rows([(words, pool)], k, cold=bool(flags.get("rerank")))
        rows, how = (got[0], "re-ranked") if got else (rows, "plain (fell back)")
    asked = kinds if kinds is not None else query_kinds(idx.kinds, words)
    lines = [f"kinds asked: {', '.join(asked) or 'none (words only)'}; look-up: {how}"]
    lines += [card(idx, d, parts) for _s, d, parts in rows]
    nxt = f"lune run kit parts {lane} plan <piece> (a whole piece, part by part, with its answer sheet)"
    if how == "plain (fell back)":
        nxt = rerank_hint(lane)
    return emit("pass", f"parts {lane} find: {len(rows)} card(s) for \"{words[:60]}\"", nxt, lines,
                ids=[d["id"] for _s, d, _p in rows])


def cmd_plan(root, lane, idx, args, flags):
    piece = args[0] if args else None
    if not piece:
        return emit("fail", f"parts {lane} plan: name the piece", f"lune run kit parts {lane} plan <piece>")
    ad = adapter(root, lane)
    path = sheet_path(root, lane, ad, piece)
    if flags.get("check"):
        if not os.path.isfile(path):
            return emit("fail", f"parts {lane} plan {piece}: no sheet yet", f"lune run kit parts {lane} plan {piece}")
        problems = check_sheet(parse_sheet(_read(path)))
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if problems:
            return emit("fail", f"parts {lane} plan {piece}: {len(problems)} part(s) unanswered in {rel}",
                        f"answer them in {rel}, then: lune run kit parts {lane} plan {piece} --check", problems)
        return emit("pass", f"parts {lane} plan {piece}: every part answered ({rel})",
                    "build from the cards named; the owner's verdict will credit them")
    text = flags.get("brief") if isinstance(flags.get("brief"), str) else None
    if not text and ad is not None and hasattr(ad, "brief"):
        text = ad.brief(root, piece)
    if not text:
        return emit("fail", f"parts {lane} plan {piece}: no brief to break down",
                    f"write the piece's brief first, or: lune run kit parts {lane} plan {piece} --brief \"<words>\"")
    k = int(flags.get("k", 3))
    head, parts = breakdown(idx, ad, piece, text)
    if not parts:
        return emit("fail", f"parts {lane} plan {piece}: the brief named no parts", "say what the piece is made of")
    pools = [search(idx, p["words"], k=RERANK_POOL, kinds=p["kinds"], exclude=piece, context=head) for p in parts]
    results, how = [pool[:k] for pool in pools], "plain"
    if use_rerank(root, lane, flags):
        # (warm by default where the replay showed the re-ranker wins; the model loads cold only on --rerank)
        got = rerank_rows([(f"{head}: {p['words']}", pool) for p, pool in zip(parts, pools)], k,
                          cold=bool(flags.get("rerank")))
        results, how = (got, "re-ranked") if got else (results, "plain (fell back)")
    keep, rest = matters(parts, results)
    md = write_sheet(idx, lane, piece, head, parts, results, keep, rest, flags.get("as") or "claude-code")
    lines = [f"{len(parts)} part(s); asked: {len(keep)} (at most {MAX_PARTS}); suggested kinds only: {len(rest)}; "
             f"look-up: {how}"]
    for n, i in enumerate(keep, 1):
        lines.append(f"{n}. {parts[i]['title'][:70]} - kinds {', '.join(parts[i]['kinds']) or 'none'} - "
                     f"{len(results[i])} card(s){' (an AVOID among them)' if any(r[1].get('avoid') for r in results[i]) else ''}")
    if flags.get("dry"):
        for line in md.splitlines():
            lines.append(line)
        return emit("pass", f"parts {lane} plan {piece}: {len(keep)} part(s) to answer (dry run: nothing written)",
                    f"lune run kit parts {lane} plan {piece} (writes the sheet)", lines)
    if os.path.isfile(path) and not flags.get("force"):
        old = parse_sheet(_read(path))
        if any(p.get("answer") for p in old["parts"]):
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            return emit("fail", f"parts {lane} plan {piece}: {rel} already holds answers (never overwritten)",
                        f"check it: lune run kit parts {lane} plan {piece} --check (or --force to start again)", lines)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(md + "\n")
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    hint = ""
    if how == "plain (fell back)":
        hint = f" ({rerank_hint(lane)}; then plan again with --force)"
    return emit("pass", f"parts {lane} plan {piece}: {len(keep)} part(s) to answer in {rel}",
                f"answer each part in {rel}, then: lune run kit parts {lane} plan {piece} --check{hint}", lines,
                sheet=rel)


def cmd_label(root, lane, idx, flags):
    qs = load_json(questions_path(root, lane), {}).get("questions", [])
    if not qs:
        return emit("fail", f"parts {lane} label: no questions yet ({questions_path(root, lane)})",
                    "write the lane's fixed questions (new pieces in a brief's words) first")
    store = load_json(labels_path(root, lane), {"lane": lane, "labellers": {}, "labels": {}})
    labels = store.setdefault("labels", {})
    work = os.path.join(root, "build", "parts", lane, "label")
    if isinstance(flags.get("merge"), str):
        who = flags["merge"]
        if who not in ("a", "b"):
            return emit("fail", "parts label --merge: a or b", f"lune run kit parts {lane} label --merge a")
        key = load_json(os.path.join(work, f"key-{who}.json"), {})
        answers = load_json(os.path.join(work, f"answers-{who}.json"), None)
        if not key or answers is None:
            return emit("fail", f"parts {lane} label --merge {who}: no key or no answers in {work}",
                        f"write {work}/answers-{who}.json from blind-{who}.md")
        n = 0
        missing = []
        strays = [f"{qid} #{num}" for qid, got in answers.items() for num in (got or {})
                  if str(num) not in key.get(qid, {})]
        if strays:  # (answers to cards this key never numbered: a sheet from another pool - never map them)
            return emit("fail", f"parts {lane} label --merge {who}: {len(strays)} answer(s) name cards the key does "
                        "not have (an older or newer sheet?) - nothing merged",
                        f"label build/parts/{lane}/label/blind-{who}.md again, then merge", strays[:30])
        for qid, nums in key.items():
            got = answers.get(qid, {})
            for num, cid in nums.items():
                if str(num) not in got:
                    missing.append(f"{qid} #{num}")
                    continue
                labels.setdefault(qid, {}).setdefault(cid, {})[who] = 1 if int(got[str(num)]) else 0
                n += 1
        if isinstance(flags.get("as"), str):
            store.setdefault("labellers", {})[who] = flags["as"]
        save_json(labels_path(root, lane), store)
        if not missing:  # (merged in full: set aside, so a new pool may renumber the cards)
            os.replace(os.path.join(work, f"answers-{who}.json"), os.path.join(work, f"answers-{who}.merged.json"))
        status = "pass" if not missing else "fail"
        return emit(status, f"parts {lane} label: {n} label(s) by {who} merged" +
                    (f", {len(missing)} card(s) left unanswered" if missing else ""),
                    f"lune run kit parts {lane} eval", missing[:30])
    if flags.get("disagreements"):
        rows = []
        by_id = {d["id"]: d for d in idx.docs}
        for qid, items in sorted(labels.items()):
            for cid, v in sorted(items.items()):
                if "a" in v and "b" in v and v["a"] != v["b"]:
                    d = by_id.get(cid)
                    rows.append(f"{qid} a={v['a']} b={v['b']} `{cid}` {(d or {}).get('title', '')[:80]}")
        return emit("pass", f"parts {lane} label: {len(rows)} disagreement(s)", f"lune run kit parts {lane} eval",
                    rows)
    pending = [who for who in ("a", "b") if os.path.isfile(os.path.join(work, f"answers-{who}.json"))]
    if pending:  # (a new pool renumbers the cards: answers not yet merged would land on the wrong ones)
        return emit("fail", f"parts {lane} label: answers by {', '.join(pending)} are not merged yet - a new pool "
                    "would renumber their cards", f"lune run kit parts {lane} label --merge {pending[0]} first")
    k = int(flags.get("pool", POOL))
    runs = methods(root, lane, idx, adapter(root, lane), qs, k, rerank=bool(flags.get("rerank")))
    save_json(os.path.join(work, "runs.json"), runs)
    lines = []
    for who in ("a", "b"):
        md, key = blind_sheet(idx, qs, runs, labels, who)
        with open(os.path.join(work, f"blind-{who}.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(md + "\n")
        save_json(os.path.join(work, f"key-{who}.json"), key)
        lines.append(f"{who}: {sum(len(v) for v in key.values())} card(s) to label in "
                     f"{os.path.relpath(os.path.join(work, f'blind-{who}.md'), root)}")
    return emit("pass", f"parts {lane} label: {len(qs)} question(s), methods {', '.join(runs)}; blind sheets written",
                f"each labeller answers alone, then: lune run kit parts {lane} label --merge a --as \"<who>\" "
                "(and b)", lines)


def cmd_eval(root, lane, idx, flags):
    qs = load_json(questions_path(root, lane), {}).get("questions", [])
    store = load_json(labels_path(root, lane), {"labels": {}})
    # a question counts once both labellers have answered its cards; a card one of them skipped shows as unjudged
    labels = {qid: items for qid, items in store.get("labels", {}).items()
              if any("a" in v and "b" in v for v in items.values())}
    k = int(flags.get("k", POOL))
    pairs = [(v["a"], v["b"]) for items in labels.values() for v in items.values() if "a" in v and "b" in v]
    kap, agree = kappa(pairs)
    n = len([q for q in qs if q["id"] in labels])
    if not n:
        return emit("fail", f"parts {lane} eval: no question has both labellers' labels yet ({len(qs)} question(s))",
                    f"lune run kit parts {lane} label")
    runs = methods(root, lane, idx, adapter(root, lane), [q for q in qs if q["id"] in labels], k,
                   rerank=bool(flags.get("rerank")))
    table = score_runs(runs, labels, k)
    dis = sum(1 for a, b in pairs if a != b)
    lines = [f"{n} labelled question(s) of {len(qs)}; labellers agree on {agree:.0%} of {len(pairs)} card(s) "
             f"(Cohen's kappa {kap}), {dis} disagreement(s): lune run kit parts {lane} label --disagreements",
             f"useful cards in the top {k} (both labellers / either), mean per question; unjudged = not in the pool:"]
    summary_rows = {}
    for m, rows in table.items():
        if not rows:
            continue
        s = sum(r[1] for r in rows) / len(rows)
        le = sum(r[2] for r in rows) / len(rows)
        un = sum(r[3] for r in rows) / len(rows)
        summary_rows[m] = {"strict": round(s, 2), "lenient": round(le, 2), "unjudged": round(un, 2), "n": len(rows)}
        lines.append(f"  {m:<16} {s:4.2f} / {le:4.2f}   unjudged {un:4.2f}   (n {len(rows)})")
    lines.append("per question (both / either):")
    for q in qs:
        if q["id"] not in labels:
            continue
        cells = []
        for m, rows in table.items():
            for r in rows:
                if r[0] == q["id"]:
                    cells.append(f"{m} {r[1]}/{r[2]}")
        lines.append(f"  {q['id']} {q['piece']}: " + ", ".join(cells))
    measurable = n >= MEASURABLE
    beats = {}
    # every baseline a session can get today (kit start's first stage, every stage, the 3D study, the lane's library
    # search), and the plain engine against its re-ranked self (the choice --rerank makes)
    bases = [b for b in BASELINES if table.get(b)]
    if table.get("engine") and table.get("engine + rerank"):
        bases.append("engine")
    for base in bases:
        lines.append(f"vs {base}, paired per question (mean gain, 95% bootstrap interval; wins/ties/losses on both "
                     "labellers' cards):")
        for m in table:
            if m == base or m in BASELINES or not table[m]:
                continue
            if base == "engine" and m != "engine + rerank":
                continue
            c = compare(table[base], table[m])
            if not c:
                continue
            won = measurable and c["strict"][1] > 0 and c["lenient"][1] > 0
            if won:
                beats.setdefault(m, []).append(base)
            lines.append(f"  {m:<16} both {c['strict'][0]:+.2f} [{c['strict'][1]:+.2f}, {c['strict'][2]:+.2f}], "
                         f"either {c['lenient'][0]:+.2f} [{c['lenient'][1]:+.2f}, {c['lenient'][2]:+.2f}]; "
                         f"{c['wins']}/{c['ties']}/{c['losses']} -> "
                         + ("BEATS it under both readings" if won else "not shown"))
    note = "" if measurable else f" - NOT MEASURABLE YET (under {MEASURABLE} labelled questions; never counts as done)"
    shown = "; ".join(f"{m} beats {', '.join(b)}" for m, b in beats.items()) or "no method shown to beat a baseline"
    if flags.get("rerank"):  # (every method ran: the lane's standing record, read by plan's --rerank hint)
        save_json(eval_path(root, lane), {"date": time.strftime("%Y-%m-%d"), "k": k, "n": n, "kappa": kap,
                                          "agreement": agree, "labellers": store.get("labellers", {}),
                                          "methods": summary_rows, "beats": beats, "measurable": measurable})
        lines.append(f"saved: {os.path.relpath(eval_path(root, lane), root)}")
    return emit("pass", f"parts {lane} eval: {n} question(s), agreement {agree:.0%} (kappa {kap}); {shown}{note}",
                "a method beats a baseline only when its gain holds under BOTH readings (both labellers / either) "
                "with a 95% interval above zero - the labellers' disagreement can't explain it away", lines,
                methods=summary_rows, n=n, kappa=kap, agreement=agree, measurable=measurable, beats=beats)


def compare(base_rows, rows, draws=4000, seed=11):
    """a method against a baseline, paired by question: the mean gain in useful cards (both labellers' and either's)
    with a 95% bootstrap interval over the questions, and its wins / ties / losses on both labellers' cards"""
    base = {r[0]: r for r in base_rows}
    pairs = [(r[1] - base[r[0]][1], r[2] - base[r[0]][2]) for r in rows if r[0] in base]
    if not pairs:
        return None
    rnd = random.Random(seed)
    out = {"wins": sum(1 for s, _l in pairs if s > 0), "ties": sum(1 for s, _l in pairs if s == 0),
           "losses": sum(1 for s, _l in pairs if s < 0)}
    for i, key in ((0, "strict"), (1, "lenient")):
        vals = [p[i] for p in pairs]
        means = sorted(sum(rnd.choice(vals) for _ in vals) / len(vals) for _ in range(draws))
        out[key] = (round(sum(vals) / len(vals), 2), round(means[int(0.025 * draws)], 2),
                    round(means[int(0.975 * draws) - 1], 2))
    return out


def cmd_health(root, lane, idx):
    h = health(idx)
    lines = [f"kinds with no card: {', '.join(h['empty']) or 'none'}",
             f"parts / recipes with no kind: {len(h['unkinded'])}" +
             (f" (e.g. {', '.join(d['id'] for d in h['unkinded'][:5])})" if h["unkinded"] else ""),
             f"duplicate cards: {len(h['dupes'])}" + (f" (e.g. {h['dupes'][0][:3]})" if h["dupes"] else ""),
             f"recipes whose file or line is gone: {len(h['stale'])}" +
             (f" (e.g. {', '.join(h['stale'][:5])})" if h["stale"] else ""),
             f"kinds with cards but no evidence from the owner yet: {len(h['unevidenced'])}"]
    return emit("pass", f"parts {lane} health: {len(h['empty'])} empty kind(s), {len(h['unkinded'])} unkinded, "
                f"{len(h['dupes'])} dupe(s), {len(h['stale'])} stale recipe(s)",
                "a report for upkeep, never a gate", lines)


def cmd_credit(root, lane, idx, args):
    piece = args[0] if args else None
    if not piece:
        return emit("fail", "parts credit: name the piece", f"lune run kit parts {lane} credit <piece>")
    ad = adapter(root, lane)
    vkey = getattr(ad, "verdict_key", None) if ad is not None else None
    key = _piece_key(vkey(piece) if vkey else piece)
    credited = [d for d in idx.docs if d.get("credit") and key in {_piece_key(p) for p in d["credit"]["pieces"]}]
    # the piece's own cards and, for a round or a move, every card under it (a round's "All bad" reaches each candidate)
    reached = [d for d in idx.docs if not d.get("research") and d["type"] not in ("lesson", "grave")
               and key in {_piece_key(c) for c in _chain(d.get("piece"))}]
    named = [d for d in reached if any(o.get("part") and not d.get("whole") for o in d.get("owner", []))]
    avoid = [d for d in reached if d.get("avoid")]
    lines = [f"credited from its sheet: {card(idx, d)}" for d in credited]
    lines += [f"the owner's words name this part: {d['title'][:60]} (`{d['id']}`)" for d in named]
    return emit("pass", f"parts {lane} credit {piece}: the verdict reached {len(reached)} card(s) ({len(avoid)} now "
                f"AVOID), {len(credited)} credited from its sheet, {len(named)} part(s) named in the owner's words",
                "nothing to do: the library learnt it", lines)


def cmd_look_allow(root, lane, args, flags):
    if len(args) < 2 or not isinstance(flags.get("from"), str):
        return emit("fail", "parts look-allow: <piece> --from <past piece> \"<the owner's words>\" --by owner",
                    f"lune run kit parts {lane} look-allow <piece> --from <past piece> \"<their words>\" --by owner")
    piece, words = args[0], " ".join(args[1:])
    by = "owner" if flags.get("by") == "owner" else "model-proposed"
    rows = look_allows(root, lane)
    rows.append({"piece": piece, "from": flags["from"], "words": words, "by": by,
                 "date": time.strftime("%Y-%m-%d"), "game": os.environ.get("KIT_GAME") or None})
    save_json(looks_path(root, lane), rows)
    if by != "owner":
        return emit("pass", f"parts {lane} look-allow: {piece} from {flags['from']} recorded as a PROPOSAL (no card "
                    "shows the look until the owner says so)",
                    "show the owner; record only their words with --by owner")
    return emit("pass", f"parts {lane} look-allow: {piece} may reuse {flags['from']}'s look (the owner: \"{words[:60]}\")",
                f"lune run kit parts {lane} plan {piece}")


def main(argv):
    args, flags = parse_args(argv)
    root = os.path.abspath(flags["root"]) if isinstance(flags.get("root"), str) else ROOT
    if len(args) < 2 or args[0] not in LANES:
        return emit("fail", "parts: <lane> <kinds|index|find|plan|label|eval|health|credit|look-allow> ...",
                    "lune run kit parts 3d kinds")
    lane, sub, rest = args[0], args[1], args[2:]
    t0 = time.time()
    if sub == "index":
        return cmd_index(root, lane, flags)
    if sub == "look-allow":
        return cmd_look_allow(root, lane, rest, flags)
    idx = load_index(root, lane)
    if sub == "kinds":
        return cmd_kinds(root, lane, idx, flags)
    if sub == "find":
        return cmd_find(root, lane, idx, rest, flags)
    if sub == "plan":
        code = cmd_plan(root, lane, idx, rest, flags)
        if not flags.get("check"):
            print(f"(plan took {time.time() - t0:.1f} s{', index rebuilt' if idx.rebuilt else ''})", file=sys.stderr)
        return code
    if sub == "label":
        return cmd_label(root, lane, idx, flags)
    if sub == "eval":
        return cmd_eval(root, lane, idx, flags)
    if sub == "health":
        return cmd_health(root, lane, idx)
    if sub == "credit":
        return cmd_credit(root, lane, idx, rest)
    return emit("fail", f"parts: unknown sub-command {sub}", "lune run kit parts 3d kinds")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
