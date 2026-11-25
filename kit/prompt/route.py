"""route.py - PROMPT-X stage 1 (LIMITATIONS_FIXES_V4 9.2 row 1): a raw prompt -> the lanes it needs, the entities it
names, how the lanes couple, and the repo grounding scoped to them (ERL arXiv:2603.24639 / ReasoningBank
arXiv:2509.25140: retrieve the few failures and successes that matter, not the whole history).

Grounding is read from the kit's own vault (kit/knowledge/vault/<lane>/{graveyard,golden}.md tables), the lane lessons
(kit/lessons/<lane>.md), the family playbooks (kit/knowledge/families.json) and each lane template's API and engine
facts. At most 5 graveyard bans, 3 golden mechanics and 5 lessons in all. A game's own folder (games/<Game>) is never
read here: the kit's home is the source, and a project's excluded games are never touched (docs.py reads only which
services a game's code calls, and never an excluded game's). The Roblox API comes from docs.py, the past parts from partsrag.py."""

import os
import re

try:
    from . import cases, docs, models, partsrag
except ImportError:  # run as a plain module (kit/prompt on sys.path)
    import cases
    import docs
    import models
    import partsrag

STOP = set(
    "a an the and or but to of in on for with at by from it its is are be was this that these those i me my we our you "
    "your he she they them make made makes do does did can could would should will just like really very so some any "
    "yo pls please basically kinda sorta thing stuff want wanna gonna need get got also too then than into out up as "
    "if all one more most much many not no never without dont don't what which who how when where why there here".split()
)
# a source the owner names -> the words its vault records use (so "tanjiro" finds the flame arc's rows: a record
# names the piece by its own name, never the source's)
SOURCES = {
    "demon slayer": ["flame_arc", "arc", "swordsman", "water", "breathing"],
    "tanjiro": ["flame_arc", "arc", "swordsman", "demon", "slayer"],
    "hinokami": ["flame_arc", "arc", "swordsman", "dance"],
    "fate": ["starblade"],
    "jjk": ["hollow", "purple", "gojo", "domain"],
    "jujutsu": ["hollow", "purple", "gojo", "domain"],
    "gojo": ["hollow", "purple", "infinity"],
    "naruto": ["rasengan", "chidori"],
    "rasengan": ["naruto", "spiral"],
    "dragon ball": ["saiyan", "ssj", "kamehameha", "aura"],
    "dbz": ["saiyan", "ssj", "kamehameha", "aura"],
    "saiyan": ["ssj", "aura", "flipbook"],
    "bleach": ["getsuga", "bankai"],
    "konosuba": ["explosion", "megumin"],
    "mha": ["delaware", "smash"],
    "my hero": ["delaware", "smash"],
}
WEAPONS = [
    "katana", "greatsword", "claymore", "sword", "dagger", "spear", "axe", "scythe", "hammer", "bow", "gun", "pistol",
    "rifle", "revolver", "shotgun", "fists", "fist", "staff", "shield",
]
# how lanes couple in one piece of work (XP: one clock, one game)
COMBAT = {"slash", "attack", "ultimate", "ult", "combo", "punch", "kick", "hit", "strike", "m1", "ability", "skill", "move"}
# replacing existing work ("scrap metal" is a material, "scrap it" is an order)
DESTRUCTIVE = [
    "delete", "remove all", "scrap it", "scrap the", "scrap all", "scrap everything", "scrap that", "start over",
    "redo everything", "rewrite", "replace all", "wipe", "reset", "throw away", "from scratch again",
]


# ---------------------------------------------------------------------------------------------- negation
# One reader of "what the owner does NOT want", used everywhere a word is counted: the lane scores, the slots, the DSL,
# the FLUX positive substitution, the leak gate and evolve's gradient. A small token scanner (a regex could not hold
# the clause rules):
#   a TRIGGER ("no", "never", "without", "w/o", "lacks", "neither ... nor", "excluding", "instead of", "don't",
#   "shouldn't", ...) opens a span; fillers before the first content word ride along ("shouldn't HAVE ANY fire",
#   "don't ADD text", "never, EVER glowing"); then at most 4 content words, carried across "or" / "nor"; the span ends
#   at punctuation, a dash, "and", "with", "but" or a fresh instruction ("make", "just", "please" ...).
#   "nothing but fire", "not just X" and "not only X" are NOT negations; "glow: none" negates glow; "fire-free",
#   "non-glowing" and "smokeless" negate their own word. Bare "stop", "zero", "nothing", "none" never open a span
#   ("a stop-motion idle", "zero gravity", "nothing fancy, just a crate").
TRIG_WORDS = {
    "without", "never", "not", "no", "w/o", "avoid", "avoiding", "lacking", "lacks", "lack", "minus", "neither",
    "excluding", "except", "don't", "dont", "doesn't", "doesnt", "shouldn't", "shouldnt", "can't", "cant", "won't",
    "wont", "isn't", "isnt", "aren't", "arent", "mustn't", "mustnt", "needn't", "neednt", "wouldn't", "wouldnt",
}
TRIG_PHRASES = {("free", "of"), ("no", "more"), ("instead", "of"), ("rather", "than")}
NOT_NEGATION = {("nothing", "but"), ("not", "just"), ("not", "only"), ("no", "doubt"), ("not", "too")}
NEG_TRIGGERS = sorted(TRIG_WORDS | {" ".join(p) for p in TRIG_PHRASES} | {"nor"}, key=len, reverse=True)  # (the leak gate)
NEG_FILLER = {
    "ever", "at", "all", "any", "anything", "even", "have", "has", "had", "be", "being", "add", "adding", "use", "using",
    "show", "showing", "make", "making", "it", "its", "a", "an", "the", "some", "to", "want", "need", "include",
    "including", "put", "give", "look", "looking", "feel", "get", "too", "much", "really", "so", "very", "there",
    "contain", "containing", "with", "of", "any", "more",
}
NEG_END = {
    "and", "but", "with", "while", "plus", "then", "so", "make", "give", "just", "use", "build", "keep", "want",
    "need", "please", "i", "we", "because", "instead", "rather", "where", "when", "that", "which", "who",
}
NEG_CARRY = {"or", "nor"}
NEG_QUIET = {"on", "in", "of", "the", "a", "an", "its", "his", "her", "their", "my", "to", "at", "for", "from"}
NEG_POSTFIX = {"none", "zero", "nothing", "off", "no", "false"}  # "glow: none", "glowing: no", "glow = false"
NEG_MAX_CONTENT = 4
_LESS_ROOTS = "fire|flame|smoke|glow|blood|gore|text|logo|shadow|rust|blur|fog|spark|ember|colour|color|seam"
NEG_AFFIX = re.compile(rf"\b([a-z]+)-free\b|\bnon-([a-z]+)\b|\b({_LESS_ROOTS})less\b|\bno-([a-z]+)\b", re.I)
_TOKEN = re.compile(r"w/o|[A-Za-z0-9][A-Za-z0-9'\-]*|(?<=\s)-(?=\s)|[,.;:=!?()\[\]\"\n]")


def normalize(text):
    """curly quotes to straight ones (don't), unicode HYPHENS to '-' (step-by-step), unicode DASHES to a spaced ' - '
    (an unspaced em dash between two words is a break: "no fire\u2014bright blue glow" is two clauses)"""
    t = (text or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    t = re.sub("[\u2010\u2011]", "-", t)
    return re.sub("\\s*[\u2012\u2013\u2014\u2015]\\s*", " - ", t)


def negation_ranges(text):
    """-> [(start, end, negated_words)] over normalize(text): each span the owner said NO to"""
    t = normalize(text)
    toks = [(m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(t)]
    low = [x[0].lower() for x in toks]
    out, i = [], 0
    while i < len(toks):
        w = low[i]
        nxt = low[i + 1] if i + 1 < len(toks) else ""
        aff = NEG_AFFIX.fullmatch(toks[i][0])
        if aff:
            root = next(g for g in aff.groups() if g)
            out.append((toks[i][1], toks[i][2], [root.lower()]))
            i += 1
            continue
        if w in NEG_POSTFIX and i >= 2 and low[i - 1] in (":", "=") and toks[i - 2][0][0].isalnum():
            out.append((toks[i - 2][1], toks[i][2], [low[i - 2]]))  # "glow: none"
            i += 1
            continue
        if (w, nxt) in NOT_NEGATION:
            i += 2
            continue
        start = None
        if (w, nxt) in TRIG_PHRASES:
            start, j = toks[i][1], i + 2
        elif w in TRIG_WORDS:
            start, j = toks[i][1], i + 1
        if start is None:
            i += 1
            continue
        content, end = [], toks[j - 1][2]
        while j < len(toks):
            tok = low[j]
            if not content:
                # (":" "(" "[" and quotes before the first content word: "no: fire", "no (glowing) runes", "no 'glow'")
                if tok in (":", "(", "[", '"') or (tok == "," and j + 1 < len(toks) and low[j + 1] in ("ever", "at", "even")):
                    j += 1
                    continue
                if tok in NEG_FILLER:
                    end = toks[j][2]
                    j += 1
                    continue
            if not toks[j][0][0].isalnum() and tok != "w/o":
                break  # punctuation or a dash ends it
            if content and tok in NEG_END:
                break
            if tok in NEG_CARRY:
                j += 1
                continue
            if tok in TRIG_WORDS and content:
                break  # a fresh negation starts its own span
            if tok not in NEG_QUIET:
                if len(content) >= NEG_MAX_CONTENT:
                    break
                content.append(tok.strip("'"))
            end = toks[j][2]
            j += 1
        if content:
            out.append((start, end, content))
        i = max(j, i + 1)
    return out


def negated_spans(text):
    """the spans that say what is NOT wanted, as they appear in the (normalized) text"""
    t = normalize(text)
    return [t[a:b].strip(" ,") for a, b, _w in negation_ranges(text)]


def negated_words(text):
    out = set()
    for _a, _b, ws in negation_ranges(text):
        out.update(w for w in ws if w not in NEG_FILLER)
    return out


def strip_negated(text):
    """the text with every negated span cut out: what IS asked for"""
    t = normalize(text)
    for a, b, _w in sorted(negation_ranges(text), reverse=True):
        t = t[:a] + " " + t[b:]
    return t


def words(text):
    return re.findall(r"[a-z0-9][a-z0-9'\-]*", (text or "").lower())


def content_words(text):
    return [w for w in words(text) if w not in STOP and len(w) > 1]


def _has(raw_lower, needle):
    """a phrase with a space is a substring match; a single word must stand alone"""
    if " " in needle.strip() or not needle.strip().isalnum():
        return needle in raw_lower
    return re.search(rf"\b{re.escape(needle)}\b", raw_lower) is not None


def active_game(explicit=None):
    """--game, else KIT_GAME, else games/.active; 'none' (and an empty value) means no game"""
    g = explicit if explicit is not None else os.environ.get("KIT_GAME")
    if g is None:
        path = os.path.join(models.root(), "games", ".active")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                g = f.read().strip()
    if not g or g.lower() == "none":
        return None
    return g


# ---------------------------------------------------------------------------------------------- vault tables
def _table(path):
    """a vault page's markdown table -> list of {column: cell}"""
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f]
    head, rows = None, []
    for ln in lines:
        if not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if head is None:
            head = [c.lower() for c in cells]
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if len(cells) >= len(head):
            rows.append(dict(zip(head, cells)))
    return rows


def _lessons(lane):
    path = os.path.join(models.root(), "kit", "lessons", f"{lane}.md")
    if not os.path.isfile(path):
        return []
    out = []
    excluded = _exclusions()[1]
    with open(path, encoding="utf-8") as f:
        for ln in f:
            m = re.match(r"^- (\d{4}-\d{2}-\d{2}) \(([^)]*)\):\s*(.+)$", ln.strip())
            # a lesson written inside one of the project's excluded games ("(..., <Game>)") is that game's, never the
            # kit's (profiles.core.exclude_games)
            if m and m.group(2).rsplit(",", 1)[-1].replace(" ", "").lower() not in excluded:
                out.append({"date": m.group(1), "text": m.group(3)})
    return out


def _vault_dir(lane):
    return os.path.join(models.root(), "kit", "knowledge", "vault", models.VAULT_LANE.get(lane, lane))


def _raw_rows(path):
    """a vault page's table rows counted from its lines alone (no parser, no exclusions)"""
    if not os.path.isfile(path):
        return 0
    with open(path, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip().startswith("|")]
    sep = next((i for i, ln in enumerate(lines) if "-" in ln and set(ln.replace("|", "")) <= set("-: ")), None)
    return 0 if sep is None else len(lines) - sep - 1


def filed_records(lanes):
    """{"graveyard": [lane, ...], "golden": [...]}: the lanes whose vault pages hold rows - read from the files where the
    vault keeps them, not through _vault_dir / _table or the exclusions, so a hydration that loses every record (a
    parser, path or exclusion bug) still fails trap 4 (checks.missing_grounding)"""
    out = {"graveyard": [], "golden": []}
    for lane in lanes:
        d = os.path.join(models.root(), "kit", "knowledge", "vault", models.VAULT_LANE.get(lane, lane))
        for kind in out:
            if _raw_rows(os.path.join(d, f"{kind}.md")):
                out[kind].append(lane)
    return out


def filed_graveyard(lanes=models.LANES):
    """every graveyard record this project filed in these lanes ('tried', lower case; the exclusions applied)"""
    out = []
    for lane in lanes:
        for row in _table(os.path.join(_vault_dir(lane), "graveyard.md")):
            if not _excluded_record(row.get("tried", ""), " ".join(row.values())):
                out.append(row.get("tried", "").strip().lower())
    return out


def stem(w):
    """a light stemmer for matching records: running -> run, numbers -> number, poses -> pose"""
    for suf, keep in (("ning", 3), ("ing", 3), ("ies", 3), ("es", 4), ("ed", 3), ("s", 3)):
        if w.endswith(suf) and len(w) - len(suf) >= keep:
            return w[: -len(suf)] if suf != "ies" else w[:-3] + "y"
    return w


def record_words(text):
    """a record's words for matching: CamelCase and snake_case split (RigRun2 -> rig run, ActionHud_v1 -> action hud), stemmed"""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")
    spaced = re.sub(r"([A-Za-z])(\d)", r"\1 \2", spaced).replace("_", " ")
    joined = (text or "").replace("_", " ")  # (the joined form too: "SampleRegion" is "sampleregion" in a prompt)
    return {stem(w) for w in content_words(spaced)} | {stem(w) for w in content_words(joined)}


LANE_NAMES = {
    "vfx", "effect", "effects", "anim", "animation", "animations", "animate", "model", "models", "3d", "mesh", "ui", "gui",
    "sfx", "sound", "sounds", "audio", "world", "map", "level", "code", "system", "systems", "script", "scripts", "make",
    "build", "create", "new", "game", "roblox", "small", "big", "good", "cool", "nice",
}


def _score(text, query):
    tw = record_words(text)
    return sum(1 for w in {stem(q) for q in query} if w in tw)


# A project's own private pieces (a game it keeps out of the kit's gates, its private move sets, ...) are never handed to
# the kit's prompts: profiles.core.exclude_patterns (regexes, any case) and profiles.core.exclude_games (folders under
# games/) in parallax.config.json, else kit.config.json (the files kit/lib/config.luau reads). The kit ships both
# empty: nothing is excluded unless the project lists it.
_EXCLUDE = None


def _exclusions():
    """-> (compiled pattern or None, [excluded game folders, lower case]) from the project config, read once"""
    global _EXCLUDE
    if _EXCLUDE is None:
        core = models.core_profile()
        pats = [p for p in core.get("exclude_patterns") or [] if isinstance(p, str) and p.strip()]
        games = [g.lower() for g in core.get("exclude_games") or [] if isinstance(g, str) and g.strip()]
        good = []
        for p in pats:
            try:
                re.compile(p)
                good.append(f"(?:{p})")
            except re.error:
                pass  # a broken pattern excludes nothing rather than breaking every prompt
        _EXCLUDE = (re.compile("|".join(good), re.I) if good else None, games)
    return _EXCLUDE


def _excluded_record(name, body=""):
    """a vault row, lesson or part about one of the project's excluded pieces is never handed to the kit's prompts"""
    pat, _games = _exclusions()
    return bool(pat and pat.search(f"{name} {body}"))


def _short(text, n=220):
    text = re.sub(r"\[\[[^\]]*\]\]", "", text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def families(lane, query):
    t = models.template(lane)
    key = t.get("families_key")
    if not key:
        return []
    path = os.path.join(models.root(), "kit", "knowledge", "families.json")
    if not os.path.isfile(path):
        return []
    fam = models.load_json(path).get(key) or {}
    if not isinstance(fam, dict):
        return []
    hits = []
    for name, fwords in fam.items():
        n = sum(1 for w in fwords if w in query)
        if n:
            hits.append((n, name))
    hits.sort(key=lambda h: (-h[0], h[1]))
    return [name for _n, name in hits[:3]]


# Parts RAG (kit/tools/parts.py, P0-P8): each lane's past parts by kind. A project's excluded pieces are never handed
# over (an excluded game's folder, or a piece / id / title / text matching its exclude_patterns), and only MECHANICS:
# the engine hides look assets unless the owner allowed a look reuse (kit parts <lane> look-allow).
PARTS_LANE = {"systems": "code"}


def _parts_engine():
    return partsrag.engine()


def _excluded_doc(d):
    pat, games = _exclusions()
    src = str(d.get("src") or "").replace("\\", "/").lower()
    if any(f"games/{g}/" in src for g in games):
        return True
    return bool(pat and pat.search(" ".join(str(d.get(k) or "") for k in ("piece", "id", "title", "text"))))


def parts_lookup(lanes, raw, piece=None, lane_hint=None):
    """every routed lane's past parts by kind (partsrag.py: the lane's own library, the piece broken into parts, AVOID
    cards, know-how, mechanics only) -> {cards, libraries, note}; KIT_PROMPT_PARTS=0 turns the look-up off"""
    try:
        # (a refused word never looks a part up: "not floaty" asks for nothing floaty)
        return partsrag.lookup(lanes, strip_negated(raw), piece=piece, lane_hint=lane_hint, skip=_excluded_doc,
                               lane_score=lambda lane, text: lane_scores(text).get(lane, 0))
    except Exception as e:  # (the parts library is help, never a reason a prompt fails to compile)
        return {"cards": [], "libraries": [], "note": f"parts look-up unavailable: {type(e).__name__}: {_short(str(e), 100)}"}


def parts_hits(lanes, raw, piece=None, lane_hint=None):
    """the cards alone (kept for callers of the first PROMPT-X build)"""
    return parts_lookup(lanes, raw, piece, lane_hint)["cards"]


# the Roblox Engine API reference: kit/prompt/docs.py (Studio's own content/api_docs/en-us.json on this machine + the
# kit's type file, read locally) - names checked to exist and not to be deprecated, with their exact signatures, and the
# prompt's own words looked up inside each lane's scope
def _docs_index():
    return docs.index()


def api_docs(names):
    """-> (verified [{name, doc, signature, ...}], problems [str]); with no local reference every name is kept, marked
    unverified"""
    return docs.verify(names)


def grounding(lanes, raw, game=None, k_bans=5, k_golden=3, k_lessons=5, piece=None, lane_hint=None):
    """the few records that matter for this prompt in these lanes"""
    raw_lower = (raw or "").lower()
    # (a lane's own name says nothing about WHICH failure matters: "vfx" matched every vfx row through its link)
    query = set(content_words(strip_negated(raw))) - LANE_NAMES
    for src, extra in SOURCES.items():
        if _has(raw_lower, src):
            query.update(extra)
    fams = {lane: families(lane, query) for lane in lanes}
    for lane in lanes:
        for fname in fams[lane]:
            query.update(content_words(fname))
    bans, golden, lessons = [], [], []
    for rank, lane in enumerate(lanes):
        lane_w = 1.0 / (1 + rank)  # the lead lane's records first
        vd = _vault_dir(lane)
        for row in _table(os.path.join(vd, "graveyard.md")):
            if _excluded_record(row.get("tried", ""), " ".join(row.values())):
                continue
            body = " ".join(v for k, v in row.items() if k != "link")
            s = _score(body, query)
            rule = row.get("do not retry because", "") or row.get("result", "")
            if "owner's words above" in rule.lower() or not rule.strip():
                rule = f"the owner: {row.get('the owner' + chr(39) + 's words', '')} ({row.get('result', '')})"
            row = dict(row, **{"do not retry because": rule})
            bans.append(
                {
                    "lane": lane,
                    "tried": _short(row.get("tried", ""), 90),
                    "rule": _short(row.get("do not retry because", "") or row.get("result", ""), 260),
                    "owner": _short(row.get("the owner's words", ""), 140),
                    "score": s * lane_w + (0.01 * lane_w),
                    "matched": s,
                }
            )
        for row in _table(os.path.join(vd, "golden.md")):
            if _excluded_record(row.get("piece", ""), " ".join(row.values())):
                continue
            body = " ".join(v for k, v in row.items() if k != "link")
            try:
                owner_score = float(re.findall(r"[\d.]+", row.get("score", "0"))[0])
            except (IndexError, ValueError):
                owner_score = 0.0
            s = _score(body, query)
            # what DECIDED it is the useful part; a row with only the owner's praise says so and ranks below
            feature = row.get("the measurable feature that decided it", "").strip()
            mechanic = feature or f"no measurable feature recorded (the owner: '{_short(row.get('the owner' + chr(39) + 's words', ''), 70)}')"
            golden.append(
                {
                    "lane": lane,
                    "piece": _short(row.get("piece", ""), 60),
                    "score_10": owner_score,
                    "mechanic": _short(mechanic, 220),
                    "score": (s + owner_score / 20.0 + (0.6 if feature else 0.0)) * lane_w,
                    "matched": s,
                }
            )
        for item in _lessons(models.VAULT_LANE.get(lane, lane) if lane != "systems" else "code"):
            if _excluded_record("", item["text"]):
                continue
            s = _score(item["text"], query)
            if s:
                lessons.append({"lane": lane, "date": item["date"], "text": _short(item["text"], 260), "score": s * lane_w, "matched": s})

    def top(rows, k, key=lambda r: (-r["score"],)):
        seen, out = set(), []
        for r in sorted(rows, key=key):
            ident = (r["lane"], r.get("tried") or r.get("piece") or r.get("text"))
            same_rule = (r["lane"], (r.get("rule") or r.get("mechanic") or "")[:80])
            if ident in seen or (same_rule[1] and same_rule in seen):
                continue  # (two rows saying the same thing take one place)
            seen.add(ident)
            seen.add(same_rule)
            out.append({k2: v for k2, v in r.items() if k2 != "score"})
            if len(out) >= k:
                break
        return out

    # the lead lane keeps its own best two failures and its best success, however well another lane's records match;
    # the rest of the places go to whatever matches the prompt best, across the lanes
    lead = lanes[0] if lanes else None
    by_match = lambda r: (-r["matched"], -r["score"])  # noqa: E731
    lead_bans = top([b for b in bans if b["lane"] == lead], 2, key=by_match)
    bans_out = lead_bans + [b for b in top(bans, k_bans + 2, key=by_match) if b not in lead_bans][: k_bans - len(lead_bans)]
    lead_golden = top([r for r in golden if r["lane"] == lead], 1, key=by_match)
    golden_out = lead_golden + [r for r in top(golden, k_golden + 1, key=by_match) if r not in lead_golden][: k_golden - len(lead_golden)]
    lessons_out = top(lessons, k_lessons, key=lambda r: (-r["score"], r["date"]))
    caps = []
    for lane in lanes:
        caps += [{"lane": lane, "text": c} for c in models.template(lane).get("engine_caps", [])]
    fam_names = [f"{lane}:{f}" for lane in lanes for f in fams[lane]]
    scoped = docs.scoped(lanes, strip_negated(raw), fam_names, game)  # (a refused word never pulls an API in)
    api, api_problems = scoped["api"], scoped["problems"]
    parts = parts_lookup(lanes, raw, piece, lane_hint)
    return {
        "game": game,
        "families": fam_names,
        "lessons_top5": lessons_out,
        "golden_refs": golden_out,
        "graveyard_bans": bans_out,
        # the lanes whose vault pages hold records at all (a fresh project's hold few: the kit ships none of its
        # author's verdicts, only its 3D judge anchor) - checks.missing_grounding asks for records only there
        "filed": filed_records(lanes),
        "api_docs": [a["name"] for a in api],
        "api_detail": api,
        "api_problems": api_problems,
        "api_scope": scoped["scope"],
        "engine_caps": caps,
        "parts": parts["cards"],
        "parts_libraries": parts["libraries"],
        "parts_note": parts["note"],
    }


# ---------------------------------------------------------------------------------------------- routing
def lane_scores(raw):
    raw_lower = strip_negated(raw).lower()  # "don't touch the ui" never pulls the UI lane in
    scores = {}
    for lane in models.LANES:
        t = models.template(lane)
        s = 0
        for word, weight in t.get("keywords", {}).items():
            if _has(raw_lower, word):
                s += weight
        if s:
            scores[lane] = s
    return scores


def entities(raw):
    raw_lower = strip_negated(raw).lower()
    out = {"sources": [], "weapons": [], "destructive": []}
    for src in SOURCES:
        if _has(raw_lower, src):
            out["sources"].append(src)
    for w in WEAPONS:
        if _has(raw_lower, w) and not any(w in o for o in out["weapons"]):
            out["weapons"].append(w)
    for d in DESTRUCTIVE:
        if _has(raw_lower, d):
            out["destructive"].append(d)
    return out


def route_intent(raw_prompt, active_game_name=None, lane_hint=None, piece=None):
    """raw text -> {lanes[], scores, entities, xp_coupling, families, repo_grounding}; `piece`: the piece it is for (its
    brief / dossier / scene breakdown splits it into parts for the parts libraries; its own past parts are left out)"""
    if not (raw_prompt or "").strip():
        raise ValueError("an empty prompt: say what to make")
    scores = lane_scores(raw_prompt)
    if lane_hint:
        # (code / qa, and the kit's own lane - kit / parallax: the kit's code is systems work for PROMPT-X)
        hint = "systems" if lane_hint in ("code", "qa", "kit", "parallax") else lane_hint
        if hint in models.LANES:
            scores[hint] = scores.get(hint, 0) + 100  # kit start <lane> --prompt: that lane leads
    ranked = sorted(scores, key=lambda lane: (-scores[lane], models.LANES.index(lane)))
    # a lane leads on its own words; a stray noun (a katana in an animation ask) does not pull a whole lane in
    top_score = scores[ranked[0]] if ranked else 0
    lanes = [lane for lane in ranked if scores[lane] >= max(2, 0.4 * top_score)]
    if not lanes and ranked:
        lanes = ranked[:1]
    ents = entities(raw_prompt)
    coupling = []
    rw = set(words(strip_negated(raw_prompt)))
    combat = bool(rw & COMBAT) or bool(ents["weapons"])
    if combat and ("anim" in lanes or "vfx" in lanes):
        # a combat move is one clock: the hit frame drives the sound and the server's hit window
        for lane, why in (("sfx", "the hit sound lands within 1 frame of the hit"), ("systems", "the move's frames run on the one combat clock (Moves)")):
            if lane not in lanes:
                lanes.append(lane)
            coupling.append({"lane": lane, "why": why})
    game = active_game(active_game_name)
    # the CASE each routed lane is (PARALLAX spec §3.2: lane alone is not optimal - 3d:hybrid_hero vs 3d:static_prop)
    # and the lead lane's full Capability Menu (§3.3: the menu, not a rigid script, before the refs are seen)
    contracts = cases.contracts_for(lanes, raw_prompt, piece=piece)
    lead = lane_hint if lane_hint in cases.CASE_LANES else next(
        (cl for lane in lanes for cl in cases.case_lanes_for(lane, raw_prompt)), None)
    return {
        "raw_prompt": raw_prompt,
        "lanes": lanes,
        "scores": {lane: scores.get(lane, 0) for lane in lanes},
        "entities": ents,
        "xp_coupling": coupling,
        "repo_grounding": grounding(lanes, raw_prompt, game, piece=piece, lane_hint=lane_hint),
        "case_contracts": contracts,
        "capability_lane": lead,
        "capability_menu": cases.render_menu(lead) if lead else [],
    }
