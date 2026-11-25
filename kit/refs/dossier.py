"""dossier.py — what we KNOW about a real object, and how sure we are: the INPUT every build of it starts from.

A build is only as good as its data. The Glock 17 (2026-10-08) was built from one side photo, a 3D scan 7% short and
an "official" 204 mm that was really the Gen4's length (Glock's own manual: Gen4 204 mm, Gen5 202 mm). A dossier
gathers what is known about ONE real object — compiled once, reused by every asset of it — and grades every piece:

  identity   what it is, its maker (whose own pages are PRIMARY sources), its family and siblings, and the TELLS that
             set this variant apart from its siblings (a Gen5 has no finger grooves; a Gen4 has them)
  facts      sizes: the kit/real_specs rows of this object (`kit refs dims`), graded A-D from their sources
  anatomy    every part: its number and name in the maker's parts list, what it does, what it joins, what moves
  evidence   pictures, drawings and reference models, each measured by script and reviewed by a model
  reviews    each reviewer's verdicts (who, when, blind or not)
  approval   the owner's yes to the reference sheet (stale as soon as anything graded changes)

A fact's grade:  A  the maker, a patent office or the owner's own measurement says it
                 B  two independent websites agree (within 0.75 %, at least 0.6 mm) — one site is one vote: an
                    archived copy is its original, Wikidata and Wikipedia are one (Wikidata copies it)
                 C  one source only, or sources nobody confirmed — usable, shown as unsourced
                 D  the best sources disagree (their extremes, not their median), or the cited source does not say it
A number a MODEL typed counts only once a script found it in the cited source (`--quote`: the words around it,
verbatim, as whole words — 25 is not 25,5 — naming the part and the dim it measures, the number in its unit) or two
reviewers confirmed it (one of them blind): a model's memory is not a
source, and `fact` refuses a quote the source does not hold. Rows the kit read from Wikimedia's API itself (kit refs
dims wikipedia / wikidata) count as read; they are still secondary, and often describe the FAMILY rather than the
variant. A file path is no source anyone can check; the owner's own measurement is `--source owner --as owner`.

Pictures and models: scripts measure what numbers can (resolution, plain background, sharpness, px per mm, the
proportions against the A/B facts — the 7%-short scan fails here — and duplicates); reviewers judge what only eyes can
(the right object and variant, stock or modified, which view and how square, what each is good for). TWO KEYS: an item
counts once two different reviewers accepted it, one of them blind (`review --blind`: the packet leaves out the claims,
the earlier verdicts and whatever depends on the claimed view) and one of them not the one who added it — the adder
is never the blind key, and a reviewer who saw an item in an open packet never answers it blind; answers are taken only
for the items of the reviewer's own packet, unaltered (every packet is recorded in the dossier). One reject drops an item, but the next reviewer still
gets it: an accept makes it disputed (a third decides); two rejects are final. The owner's own photos (`add --scope owner --as owner --note ..`) need one review.
Evidence from a blocked, suspect or unknown page, a changed file or measurement, or a duplicate counts for nothing.
The owner's approval binds the sheet they saw (`--sheet <id>`): its inputs AND its outcomes — a fact re-graded by a
blocked site or a changed page makes it stale too.

    python kit/refs/dossier.py new "<object>" --category pistol [--maker "<maker>"] [--maker-domain glock.com]...
                                [--alias "g17 gen5"]... [--family "glock 17"]... [--sibling "glock 17 gen4"]... [--private]
    python kit/refs/dossier.py <object>                      status: score, grades, what is missing, the next step
    python kit/refs/dossier.py source <object> --url <url> --kind <kind> [--title ".."] [--fetch]
    python kit/refs/dossier.py fact <object> --part slide --dim length --mm 186 --source <url> --quote "<verbatim>"
    python kit/refs/dossier.py fact <object> --dim "width without slide stop levers" --mm 31.8 --from e31
                                [--measure refs/<name>_cut.measure.json]   (measured ON a confirmed reference model,
                                or on its re-measurement with a part left out — kit refs measure --cut; B at most: two
                                independent sites agreeing, and the row's meaning needs two keys)
    python kit/refs/dossier.py part <object> --name slide [--no 1] [--function ".."] [--moves ".."] [--joins a,b]
                                [--material ".."] [--finish ".."] [--interior] --source <url> [--quote "<verbatim>"]
    python kit/refs/dossier.py tell <object> --text ".." --vs "<sibling>" --source <url> [--quote ".."]
    python kit/refs/dossier.py marking <object> --text ".." --where ".." --source <url> [--quote ".."]
    python kit/refs/dossier.py add <object> (--file <path> | --url <picture url>) --scope measure-only|ship-ok|owner
                                [--kind picture|drawing] [--page <url>] [--licence ..] [--view side-left]
                                [--parts a,b] [--box x0,y0,x1,y1] [--rotate 90|180|270] [--of <part>]
    python kit/refs/dossier.py add <object> --kind model --measure refs/<name>.measure.json [--scope ..] [--page ..]
    python kit/refs/dossier.py withdraw <object> <id> --why ".."   any item (e / p / t / m / row:<id>) added wrong:
                                                              its record and reason stay, it counts for nothing
    python kit/refs/dossier.py images <page url>             the pictures a page shows, to add the right ones
    python kit/refs/dossier.py check <object> [--offline | --refetch]   grade, measure, cover, score ->
                                                              build/dossier/<slug>/ (--refetch: every cited page again)
    python kit/refs/dossier.py review <object> --as <model@harness> [--blind]    the packet + its contact sheet
    python kit/refs/dossier.py review <object> --apply <answers.json> --as <model@harness>
    python kit/refs/dossier.py sheet <object>                build/dossier/<slug>/sheet.html: the reference sheet
    python kit/refs/dossier.py approve <object> --as owner --sheet <the id on the sheet> --note "<what the owner said>"

Where things live: a dossier in kit/knowledge/<slug>.json (committed: every project gets it), a --private one in
~/.cache/roblox-kit/knowledge/ (never in a repo); every downloaded picture and document in
~/.cache/roblox-kit/evidence/<slug>/ (never in a repo: a measure-only picture is not ours to ship); the category
templates (what a pistol's dossier must hold, where to look) in kit/knowledge/categories/; what each website is worth
(primary, secondary, content farm) in kit/knowledge/sources.json — it grows as reviewers find bad ones.
One JSON verdict line last.
"""

import datetime
import hashlib
import html as htmllib
import io
import json
import os
import re
import shutil
import statistics
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dims  # noqa: E402  (the kit/real_specs store: facts stay rows there)

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
KNOW = os.path.join(REPO, "kit", "knowledge")
CACHE = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit")
PRIVATE = os.path.join(CACHE, "knowledge")
EVIDENCE = os.path.join(CACHE, "evidence")
UA = "Mozilla/5.0 (compatible; roblox-kit-refs/1.0; reference research for a Roblox content kit)"
MAX_BYTES = 60 * 1024 * 1024
SCHEMA = 1

SOURCE_KINDS = ("manufacturer", "manual", "patent", "drawing", "encyclopedia", "retailer", "press", "forum", "owner",
                "model", "other")
SCOPES = ("measure-only", "ship-ok", "owner")
VIEWS = ("side-left", "side-right", "top", "bottom", "front", "rear", "three-quarter", "detail", "other")
VERDICTS = ("accept", "limited", "reject")
GOOD_FOR = ("silhouette", "outline", "colour", "markings", "texture", "mechanism", "section", "proportions",
            "parts", "scale")
# a view -> (the frame facts its box is measured against: width over height of the box, then the box width's fact)
VIEW_FRAME = {"side-left": ("length", "height", "length"), "side-right": ("length", "height", "length"),
              "top": ("length", "width", "length"), "bottom": ("length", "width", "length"),
              "front": ("width", "height", "width"), "rear": ("width", "height", "width")}
PROPORTION_TOL = 0.03  # a picture or model whose proportions are off by more is flagged (the Glock scan: 7%)
GRADE_VALUE = {"A": 1.0, "B": 0.85, "C": 0.3, "D": 0.0, None: 0.0}


# ------------------------------------------------------------------------------------------------------ the basics
_ROWS = []


def say(line):
    """a line for the console: the kit prints every row of the verdict (python prints them inside its JSON)"""
    _ROWS.append(line)


def emit(status, summary, next_action, **extra):
    if _ROWS and "rows" not in extra:
        extra["rows"] = list(_ROWS)
    _ROWS.clear()
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra},
                     ensure_ascii=True))
    return 0 if status == "pass" else 1


def _arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def _args(argv, flag):
    return [argv[i + 1] for i, a in enumerate(argv) if a == flag and i + 1 < len(argv)]


def _today():
    return datetime.date.today().isoformat()


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slug(name):
    return dims.slug(name)


def _build_dir(s):
    path = os.path.join(os.getcwd(), os.environ.get("KIT_BUILD", "build"), "dossier", s)
    os.makedirs(path, exist_ok=True)
    return path


def _json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


class Missing(Exception):
    pass


class Broken(ValueError):
    """a dossier file that exists but cannot be read as one (said, never taken for 'no dossier')"""


def _validate(d):
    """what is wrong with a hand-edited dossier -> problems (empty: fine)"""
    out = []
    for key in ("sources", "parts", "markings", "evidence", "reviews"):
        v = d.get(key) or []
        if not isinstance(v, list):
            out.append(f"{key} is not a list")
            continue
        for i, it in enumerate(v):
            if not isinstance(it, dict):
                out.append(f"{key}[{i}] is not an object")
            elif key == "reviews" and not (it.get("by") and isinstance(it.get("items"), dict)):
                out.append(f"reviews[{i}] needs by + items")
            elif key != "reviews" and not it.get("id"):
                out.append(f"{key}[{i}] has no id")
    ident = d.get("identity")
    if ident is not None and not isinstance(ident, dict):
        out.append("identity is not an object")
    elif isinstance(ident, dict):
        for i, t in enumerate(ident.get("tells") or []):
            if not (isinstance(t, dict) and t.get("id")):
                out.append(f"identity.tells[{i}] has no id")
    return out


# ---------------------------------------------------------------------------------------------- dossier storage
def path_of(name):
    """the dossier file for a name or slug (public kit/knowledge first, then the private store) -> path or None"""
    s = slug(name)
    for folder in (KNOW, PRIVATE):
        p = os.path.join(folder, f"{s}.json")
        if os.path.isfile(p):
            return p
    # an alias: any dossier that names it
    for folder in (KNOW, PRIVATE):
        if not os.path.isdir(folder):
            continue
        for f in sorted(os.listdir(folder)):
            d = _json(os.path.join(folder, f)) if f.endswith(".json") else None
            if isinstance(d, dict) and d.get("schema") and s in {slug(a) for a in names(d)}:
                return os.path.join(folder, f)
    return None


DOSSIER_KEYS = {"schema", "object", "slug", "sources", "parts", "evidence", "identity", "markings", "reviews"}


def _broken_files():
    out = []
    for folder in (KNOW, PRIVATE):
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder)):
                if f.endswith(".json") and f != "sources.json":
                    d = _json(os.path.join(folder, f))
                    if isinstance(d, dict) and d and not set(d) & DOSSIER_KEYS:  # (an empty {} is still broken)
                        continue  # (another department's knowledge file — sfx_taste.json — never a dossier: every
                        #            prop's plan said "cannot be read" over it)
                    if not (isinstance(d, dict) and d.get("schema") and d.get("object") and d.get("slug")):
                        out.append(os.path.join(folder, f))
    return out


def load(name):
    p = path_of(name)
    if not p:
        raise Missing(f"no dossier for '{name}'")
    d = _json(p)
    if not isinstance(d, dict) or "object" not in d or "slug" not in d:
        raise Broken(f"{p} is not a readable dossier (broken JSON, or no object / slug): fix it or move it away")
    problems = _validate(d)
    if problems:
        raise Broken(f"{p}: " + "; ".join(problems[:4]))
    d["_path"] = p
    return d


def save(d):
    p = d.pop("_path", None) or os.path.join(PRIVATE if d.get("private") else KNOW, f"{d['slug']}.json")
    d["updated"] = _today()
    _write(p, d)
    d["_path"] = p
    return p


def names(d):
    """the object's own names (its rows in kit/real_specs carry one of these)"""
    return [d["object"]] + [a for a in (d.get("identity") or {}).get("aliases") or []]


def category(name):
    cat = _json(os.path.join(KNOW, "categories", f"{name}.json"))
    if not isinstance(cat, dict):
        cat = _json(os.path.join(KNOW, "categories", "generic.json"), {}) or {}
    return cat


def registry():
    return _json(os.path.join(KNOW, "sources.json"), {}) or {}


def _next_id(items, prefix):
    n = 1 + max([int(m.group(1)) for i in items for m in [re.fullmatch(prefix + r"(\d+)", str(i.get("id", "")))] if m]
                or [0])
    return f"{prefix}{n}"


# ------------------------------------------------------------------------------------------------ websites: tiers
# sites that copy one another count as ONE (Wikidata's numbers are mostly Wikipedia's: the two together never make B)
SAME_SITE = {"wikidata.org": "wikipedia.org", "wikimedia.org": "wikipedia.org"}


def _inner(url):
    """an archived copy is its original: web.archive.org/web/<when>/<url> -> <url>"""
    m = re.match(r"(?i)^https?://(?:web\.|wayback\.)?archive\.org/web/(?:\d+[a-z_]*/)?(.+)$", str(url))
    if not m:
        return url
    inner = m.group(1)
    return inner if re.match(r"(?i)^https?://", inner) else "http://" + inner


def host(url):
    u = unicodedata.normalize("NFKC", str(_inner(url))).replace("\u3002", ".").replace("\uff61", ".")
    h = (urllib.parse.urlparse(u).hostname or "").lower().rstrip(".")
    return h[4:] if h.startswith("www.") else h


def site(url):
    """the registrable domain (eu.glock.com -> glock.com; www.bbc.co.uk -> bbc.co.uk; an archived copy -> its
    original's): one site, one vote"""
    h = host(url)
    parts = [x for x in h.split(".") if x]
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in ("co", "com", "org", "net", "ac", "gov", "edu"):
        s = ".".join(parts[-3:])
    else:
        s = ".".join(parts[-2:]) if len(parts) >= 2 else h
    return SAME_SITE.get(s, s)


def _on(url, entry):
    """a maker / registry entry matches a url: a domain (and its subdomains), or a url prefix (with a slash: a CDN
    folder that is the maker's own, e.g. its asset stack)"""
    entry = entry.lower().strip()
    if "/" in entry:
        bare = re.sub(r"^https?://(www\.)?", "", _inner(url).lower())
        bare = re.sub(r"^([^/]*?)\.(/|$)", r"\1\2", bare)  # (a host's trailing dot)
        return bare.startswith(entry)
    h = host(url)
    return h == entry or h.endswith("." + entry)


def is_local(src):
    return not re.match(r"(?i)^https?://", str(src or ""))


COUNTS = ("owner", "primary", "secondary")  # the tiers whose sources count at all


def tier_of(url, d, reg=None):
    """how far a source is trusted for THIS object: owner (the source "owner": the owner measured or said it) | primary
    (the maker's own site, a patent office) | secondary | blocked (a content farm) | suspect (looks like one: add its
    site to sources.json's domains once a reviewer vouched for it) | local (a file path: nobody else can check it)"""
    if str(url or "").strip().lower() == "owner":
        return "owner"
    if is_local(url):
        return "local"
    if not site(url):
        return "unknown"  # (no host: no site anyone can check)
    reg = reg if reg is not None else registry()
    for b in (reg.get("blocked") or {}):
        if _on(url, b):
            return "blocked"
    for m in ((d.get("identity") or {}).get("maker_domains") or []):
        if _on(url, m):
            return "primary"
    for dom, row in (reg.get("domains") or {}).items():
        if _on(url, dom):
            return row.get("tier", "secondary")
    for pat in reg.get("suspect_patterns") or []:
        if re.search(pat.get("re", "$^"), url):
            return "suspect"
    return "secondary"


# ------------------------------------------------------------------------------------- source text + quote check
def _norm(s):
    s = unicodedata.normalize("NFKC", str(s)).lower()
    s = re.sub(r"[‐-―−]", "-", s)
    s = re.sub(r"[‘’‚‛]", "'", s)
    s = re.sub(r"[“”„‟]", '"', s)
    return re.sub(r"\s+", " ", s).strip()


def _html_text(raw):
    raw = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", raw)
    return htmllib.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))


def _pdf_text(data):
    from pypdf import PdfReader  # noqa: PLC0415

    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)


def _fetch(url, cap=MAX_BYTES):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as r:
        ctype = (r.headers.get("Content-Type") or "").lower()
        buf, n = io.BytesIO(), 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            n += len(chunk)
            if n > cap:
                raise ValueError(f"over the {cap >> 20} MB cap")
            buf.write(chunk)
    return buf.getvalue(), ctype


def _text_of(data, ctype, name=""):
    if data[:5] == b"%PDF-" or "pdf" in ctype or name.lower().endswith(".pdf"):
        return _pdf_text(data)
    text = data.decode("utf-8", errors="replace")
    if "html" in ctype or re.search(r"(?i)<html|<body|<div", text[:4000]):
        return _html_text(text)
    return text


def source_text(src, offline=False, refresh=False):
    """a source's words for the quote check -> (status, text): status ok | unreachable (<why>) | offline. Fetched once
    and kept (evidence/_sources/<sha1 of the url>.txt); a local file (the owner's, or one already downloaded) is read."""
    if is_local(src):
        p = src if os.path.isabs(src) else os.path.join(REPO, src)
        if not os.path.isfile(p):
            return "unreachable (no such file)", ""
        with open(p, "rb") as fh:
            data = fh.read()
        try:
            return "ok", _text_of(data, "", p)
        except Exception as e:  # noqa: BLE001 — a broken file is said, never fatal
            return f"unreachable ({type(e).__name__})", ""
    key = hashlib.sha1(src.encode()).hexdigest()[:16]
    cached = os.path.join(EVIDENCE, "_sources", f"{key}.txt")
    if os.path.isfile(cached) and not refresh:
        with open(cached, encoding="utf-8") as fh:
            return "ok", fh.read()
    if offline:
        return "offline", ""
    try:
        data, ctype = _fetch(src)
        text = _text_of(data, ctype, urllib.parse.urlparse(src).path)
    except (urllib.error.URLError, OSError, ValueError) as e:
        why = f"HTTP {e.code}" if isinstance(e, urllib.error.HTTPError) else type(e).__name__
        return f"unreachable ({why})", ""
    except Exception as e:  # noqa: BLE001 — a PDF pypdf cannot read
        return f"unreachable ({type(e).__name__})", ""
    os.makedirs(os.path.dirname(cached), exist_ok=True)
    with open(cached, "w", encoding="utf-8") as fh:
        fh.write(text)
    _write(cached[:-4] + ".json", {"url": src, "fetched": _now(), "sha256": hashlib.sha256(data).hexdigest(),
                                   "bytes": len(data)})
    return "ok", text


def numbers_in(text):
    """every number in a quote ("25,5 mm" is 25.5; "1,000" is 1000)"""
    out = []
    for m in re.finditer(r"\d[\d,.]*", text):
        t = m.group(0).rstrip(".,")
        if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", t):
            t = t.replace(",", "")
        elif re.fullmatch(r"\d+,\d{1,2}", t):
            t = t.replace(",", ".")
        try:
            out.append(float(t))
        except ValueError:
            continue
    return out


# a number's own unit in a quote -> how a row's value (mm or kg) reads in it; a number with ANOTHER unit (202 g for a
# length) is not the row's number; a bare number (a table without units) may be
_UNITS = {"mm": ("mm", 1.0), "cm": ("mm", 10.0), "m": ("mm", 1000.0), "in": ("mm", 25.4), "in.": ("mm", 25.4),
          "inch": ("mm", 25.4), "inches": ("mm", 25.4), '"': ("mm", 25.4), "kg": ("kg", 1.0), "g": ("kg", 0.001),
          "lb": ("kg", 0.45359237), "lbs": ("kg", 0.45359237), "oz": ("kg", 0.028349523)}


def value_in(value, unit, quote):
    """the quote holds the row's number, in any unit it may be written in (202 mm is also 7.95 in / 20.2 cm) — and
    not as a number of another quantity (202 g is no length)"""
    v, unit = float(value), ("kg" if unit == "kg" else "mm")
    q = _norm(quote)
    found = list(re.finditer(r"(\d[\d,.]*)\s*(mm|cm|inches|inch|in\.|in\b|lbs|lb|kg|oz|g\b|m\b|\")?", q))
    # (a quote that writes its units holds the number WITH one: the bare "2" of "7.95 inch 2 SLIDE" is a list index)
    united = any(m.group(2) and _UNITS.get(m.group(2).strip(), (None,))[0] == unit for m in found)
    for m in found:
        nums = numbers_in(m.group(1))
        if not nums:
            continue
        n, u = nums[0], m.group(2)
        if u:
            kind, f = _UNITS.get(u.strip(), (None, None))
            if kind != unit:
                continue
            if abs(n * f - v) <= max(0.0025 * abs(v), 0.011 * f):
                return True
            continue
        if united:
            continue
        cands = (v, v * 1000.0, v / 0.45359237, v / 0.028349523) if unit == "kg" else (v, v / 25.4, v / 10.0,
                                                                                         v / 1000.0)
        if any(abs(n - c) <= max(0.0025 * abs(c), 0.011) for c in cands if c):
            return True
    return False


MIN_QUOTE = 6


def quote_in(quote, text):
    """the quote stands in the source as whole words ("length 20" is not in "length 202"), and is long enough to
    prove something (6+ characters with a word of 3+ letters: "mm" proves nothing)"""
    q, t = _norm(quote), _norm(text)
    if len(q) < MIN_QUOTE or not re.search(r"[a-z]{3,}", q):
        return False, "too short to prove anything (6+ characters, with a word)"
    pat = r"(?<![a-z0-9])(?<!\d[.,])" + re.escape(q) + r"(?![a-z0-9])(?![.,]\d)"
    return (re.search(pat, t) is not None), "the quote is not in the source"


def _words(s, least=4):
    return set(re.findall(r"[a-z]{%d,}" % least, _norm(s)))


def _shares(quote, about):
    """the quote is about the item: it shares two of its words (all of them when it has fewer)"""
    mine = _words(about) or _words(about, 3)
    have = _words(quote) | _words(quote, 3)
    return len(mine & have) >= min(2, len(mine)) if mine else False


_SYNONYMS = {"mass": ("weight", "weighs"), "length": ("long",), "height": ("high", "tall"), "width": ("wide",),
             "diameter": ("dia", "bore", "calibre", "caliber"), "incl": ("with", "including", "inc"),
             "with": ("incl", "including", "inc")}
_STOP = {"the", "of", "and", "a", "an", "for", "to", "at"}


def _stem_in(word, words):
    """a word stands in a label: itself, the same 5-letter stem (sights / sight), or a 3-letter abbreviation of it
    (MAG. for magazine) — never a shorter real word ("with" is no "without")"""
    return any(x == word or (len(x) >= 5 and len(word) >= 5 and x[:5] == word[:5])
               or (len(x) == 3 and word.startswith(x)) for x in words)


def _label_words(label):
    t = re.sub(r"\bw/o\b", " without ", _norm(label))
    t = re.sub(r"\bw/", " with ", t)
    return set(re.findall(r"[a-z]{2,}", t))


def _label_ok(label, part, dim, others=()):
    """the words before a number name what it measures: EVERY word of the dim (or its synonym: weight for mass, with
    for incl) and EVERY word of the part — "Sight Radius STEEL 163 mm" is no polymer sight radius, "Weight with
    magazine" no mass without magazine, "REAR SIGHT HEIGHT" no front sight's; the whole object's size (part overall)
    names no other part unless it says overall / total — "BARREL LENGTH 114 mm" is no overall length"""
    have = _label_words(label)
    dim_words = [x for x in re.findall(r"[a-z]{2,}", _norm(dim)) if x not in _STOP]
    for w in dim_words:
        if not any(_stem_in(a, have) for a in (w, *_SYNONYMS.get(w, ()))):
            return False
    pw = [x for x in re.findall(r"[a-z]{2,}", _norm(part)) if x not in _STOP | {"overall"}]
    if pw:
        return all(_stem_in(w, have) for w in pw)
    if have & {"overall", "total"}:
        return True
    near = set(dim_words) | {a for w in dim_words for a in _SYNONYMS.get(w, ())}
    return not any(_stem_in(o, have) for o in others if len(o) >= 3 and not _stem_in(o, near))


def value_labelled(value, unit, quote, part, dim, others=()):
    """the quote holds the number (in its unit) right after its own label: "HEIGHT INCL. MAG. 139 mm" for the height
    including the magazine — not "LENGTH 202 mm | 7.95 inch HEIGHT" for a height of 202"""
    q = _norm(quote)
    found = list(re.finditer(r"(\d[\d,.]*)\s*(mm|cm|inches|inch|in\.|in\b|lbs|lb|kg|oz|g\b|m\b|\")?", q))
    kind = "kg" if unit == "kg" else "mm"
    united = any(m.group(2) and _UNITS.get(m.group(2).strip(), (None,))[0] == kind for m in found)
    prev = 0
    for m in found:
        label = q[prev:m.start()]
        prev = m.end()
        if not _label_ok(label, part, dim, others):
            continue
        if m.group(2):
            if value_in(value, unit, q[m.start():m.end()]):
                return True
            continue
        if united:
            continue  # (a bare number in a quote that writes its units elsewhere is a list index, never the value)
        # (a bare number reads in the unit its label names — "Weight (oz) 22.04" is ounces; no unit, no size)
        named = re.findall(r"(?<![a-z])(mm|cm|inches|inch|in|lbs|lb|kg|oz|g)(?![a-z])", label)
        if named and value_in(value, unit, f"{m.group(1)} {named[-1]}"):
            return True
    return False


def fact_named(part, dim, quote):
    """a size's quote names what it measures: one of the dim's words (or a synonym: weight for mass) and, unless the
    part is the whole object, one of the part's — "SLIDE LENGTH 186 mm" proves no barrel length"""
    have = _words(quote, 3)
    dims_ = _words(dim, 3) - {"incl", "with", "without", "the"}
    alts = set(dims_) | {a for w in dims_ for a in _SYNONYMS.get(w, ())}
    if alts and not any(_stem_in(w, have) for w in alts):
        return False
    parts_ = _words(part, 3) - {"overall", "the"}
    return not parts_ or any(_stem_in(w, have) for w in parts_)


def _name_key(name):
    """one name, however written: "Slide.", "the slide", "SLIDE" are one part"""
    words = re.findall(r"[a-z0-9]+", _norm(name))
    while words and words[0] in ("the", "a", "an"):
        words = words[1:]
    return " ".join(words)


def _name_in(name, quote, no=None):
    """a parts list names the part in full (with its number when given): "26 Trigger with trigger bar" — never a
    trigger bar read out of "25 Trigger spring" (it names no trigger bar)"""
    text = f" {' '.join(re.findall(r'[a-z0-9]+', _norm(quote)))} "
    nm, nr = _name_key(name), _name_key(no or "")
    if not nm:
        return False
    return any(f" {ph} " in text for ph in ((f"{nr} {nm}", f"{nm} {nr}") if nr else (nm,)))


def check_quote(src, quote, value=None, unit="mm", offline=False, about=None, fact=None, names=None):
    """-> verified | failed (<why>) | unreachable (<why>) | offline | unquoted. about: the item's own words (a part's
    name, a tell's text) — the quote must share one of them, so a true quote about something else proves nothing"""
    if not quote:
        return "unquoted"
    if about is not None and not _shares(quote, about):
        return "failed (the quote does not share two words with what it should prove)"
    if fact is not None and not fact_named(fact[0], fact[1], quote):
        return f"failed (the quote does not name {fact[0]} {fact[1]})"
    if names is not None and not _name_in(names[0], quote, names[1]):
        return f"failed (the quote does not hold the name '{(names[1] + ' ') if names[1] else ''}{names[0]}')"
    status, text = source_text(src, offline)
    if status != "ok":
        return status
    found, why = quote_in(quote, text)
    if not found:
        return f"failed ({why})"
    if value is not None and fact is not None and not value_labelled(value, unit, quote, fact[0], fact[1],
                                                                       fact[2] if len(fact) > 2 else ()):
        return "failed (the number, in its unit, does not follow its own label in the quote)"
    if value is not None and fact is None and not value_in(value, unit, quote):
        return "failed (the quote does not hold the number in its unit)"
    return "verified"


# -------------------------------------------------------------------------------------------------- the reviews
def latest_verdicts(d, item_id):
    """each reviewer's LAST verdict on an item -> {by: (verdict dict, blind)}"""
    out = {}
    for r in d.get("reviews") or []:
        v = (r.get("items") or {}).get(item_id)
        if isinstance(v, dict):
            out[r.get("by", "?")] = (v, bool(r.get("blind")))
    return out


def item_status(d, item_id, adder=None, need=2, views=False):
    """two keys: confirmed (need distinct reviewers accepted, one blind, one not the adder; pictures: the same view) |
    rejected (a reject and no accept; or outvoted with 3+ reviewers) | disputed | pending"""
    got = latest_verdicts(d, item_id)
    acc = [(by, v, b) for by, (v, b) in got.items() if v.get("verdict") in ("accept", "limited")]
    rej = [(by, v, b) for by, (v, b) in got.items() if v.get("verdict") == "reject"]
    if rej and not acc:
        return "rejected"
    if rej:
        if len(got) >= 3 and len(rej) > len(acc):
            return "rejected"
        if not (len(got) >= 3 and len(acc) > len(rej)):
            return "disputed"
    if len(acc) < need:
        return "pending"
    if need >= 2 and not any(b and by != adder for by, _, b in acc):
        return "pending"  # (two keys, but nobody looked without being told what to see — the adder never can)
    if adder and not any(by != adder for by, _, _ in acc):
        return "pending"
    if views and len({v.get("view") for _, v, _ in acc if v.get("view")}) > 1:
        return "disputed"
    return "confirmed"


def agreed(d, item_id, key):
    """what the accepting reviewers agree on (a view, good-for uses)"""
    vals = [v.get(key) for v, _ in latest_verdicts(d, item_id).values() if v.get("verdict") in ("accept", "limited")]
    if key == "good_for":
        lists = [set(x or []) for x in vals]
        return sorted(set.intersection(*lists)) if lists else []
    if not vals or any(x in (None, "") for x in vals):
        return None  # (a key nobody, or only one of the reviewers, stated is not agreed)
    return vals[0] if all(x == vals[0] for x in vals) else None


def variant_state(d, item_id):
    """the accepting reviewers on the variant: wrong (anyone said so) | ok (all said ok) | unsure"""
    vals = [v.get("variant") for v, _ in latest_verdicts(d, item_id).values() if v.get("verdict") in ("accept",
                                                                                                        "limited")]
    if any(x == "wrong" for x in vals):
        return "wrong"
    return "ok" if vals and all(x == "ok" for x in vals) else "unsure"


# --------------------------------------------------------------------------------------------------- the facts
def _agree(a, b, unit):
    a, b = float(a), float(b)
    if unit == "kg":
        return abs(a - b) <= max(0.02 * max(abs(a), abs(b)), 0.005)
    return abs(a - b) <= max(0.0075 * max(abs(a), abs(b)), 0.6)


def _all_agree(values, unit):
    """every value agrees with every other (the extremes within tolerance — a median would hide 202 vs 204)"""
    return not values or _agree(min(values), max(values), unit)


def _key(part, dim):
    return f"{str(part).strip().lower()}.{str(dim).strip().lower()}"


def _rows_of(d, family=False):
    want = {_norm(n) for n in ((d.get("identity") or {}).get("family") or [])} if family else \
        {_norm(n) for n in names(d)}
    return [r for r in dims.load_all() if _norm(r.get("object", "")) in want]


def part_words(d):
    """the words naming the object's parts (its anatomy, the category's facts): an overall size's label must name
    none of them"""
    names_ = [p.get("name", "") for p in live(d.get("parts"))]
    for want in category(d.get("category", "")).get("facts") or []:
        for k in (want if isinstance(want, list) else [want]):
            names_.append(str(k).split(".")[0])
    out = set()
    for n in names_:
        out |= {w for w in re.findall(r"[a-z]{3,}", _norm(n)) if w not in _STOP | {"overall", "total", "with"}}
    return out


_AXIS = {"width": 0, "height": 1, "length": 2}


def _same_file(a, b):
    """two paths (as a measurement records them: relative to the repo, or absolute) name one file"""
    if not (a and b):
        return False
    norm = lambda x: os.path.normcase(os.path.abspath(x if os.path.isabs(x) else os.path.join(os.getcwd(), x)))  # noqa: E731
    return norm(str(a)) == norm(str(b))


def measured_on(d, r, reg=None):
    """a fact MEASURED ON evidence (kind derived, source evidence:<id>): the evidence must be confirmed by two keys and
    its own measurement must hold the number -> (quote_check, tier, site). Never above secondary: it is our reading
    of a source, not the source's word (B needs two independent sites agreeing). A row may cite a RE-measurement of
    the same model with a part left out (r["measure"]: kit refs measure --cut, pinned by r["measure_sha256"]) — a
    published size over a protrusion (GLOCK's 34 mm over the slide stop levers) against the model without it. The
    script checks the number; what the number MEANS (its dim's words) needs the row's own two keys."""
    eid = str(r.get("source", ""))[len("evidence:"):].split("#")[0]
    e = next((x for x in live_evidence(d) if x.get("id") == eid), None)
    if e is None:
        return "failed (no such evidence, or withdrawn)", "local", f"evidence:{eid}"
    page = e.get("page") or e.get("url")
    page = page if page and re.match(r"(?i)^https?://", str(page)) else None
    tier = tier_of(page, d, reg) if page else "unknown"
    tier = "secondary" if tier == "primary" else tier
    where = site(page) if page else f"evidence:{eid}"
    axis = next((_AXIS[w] for w in re.findall(r"[a-z]+", _norm(r.get("dim", ""))) if w in _AXIS), None)
    if e.get("kind") != "model" or axis is None:
        return "failed (only a model's width / height / length can be cited)", tier, where
    if str(r.get("part") or "overall").strip().lower() != "overall":
        return "failed (a model's measurement is the WHOLE object's: cite it as an overall size)", tier, where
    mp = e.get("measure") or ""
    mfile = mp if os.path.isabs(mp) else os.path.join(os.getcwd(), mp)
    m = _json(mfile, {})
    pin = e.get("measure_sha256")
    if r.get("measure"):
        own = m if isinstance(m, dict) else {}
        if pin and (not os.path.isfile(mfile) or _file_sha(mfile) != pin):
            return "failed (the evidence's own measurement changed since it was reviewed)", tier, where
        rp = str(r["measure"])
        mfile = rp if os.path.isabs(rp) else os.path.join(os.getcwd(), rp)
        m, pin = _json(mfile, {}), r.get("measure_sha256")
        if not pin:
            return "failed (the re-measurement is not pinned: add the fact again with --measure)", tier, where
        if not os.path.isfile(mfile) or _file_sha(mfile) != pin:
            return "failed (the re-measurement changed since the row cited it)", tier, where
        if not (isinstance(m, dict) and m.get("cut")):
            return "failed (a re-measurement must say what it left out: kit refs measure --cut)", tier, where
        if not _same_file(m.get("source"), own.get("obj") or own.get("source")):
            return "failed (the re-measurement is of another model than the evidence's)", tier, where
        unc, whole = m.get("size_uncut_mm"), own.get("size_mm")
        if not (isinstance(unc, list) and isinstance(whole, list) and len(unc) == 3 == len(whole)
                and all(_agree(x, y, "mm") for x, y in zip(unc, whole))):
            return ("failed (the re-measurement's whole model is not the evidence's: another scale, front or "
                    "--skip — re-measure it with the evidence's own options and --cut)"), tier, where
    size = m.get("size_mm") if isinstance(m, dict) else None
    if not (isinstance(size, list) and len(size) == 3):
        return "failed (the evidence has no measurement)", tier, where
    if pin and _file_sha(mfile) != pin:
        return "failed (the evidence's measurement changed)", tier, where
    if not _agree(r.get("value", 0), size[axis], "mm"):
        return f"failed (the evidence measures {float(size[axis]):.1f} mm)", tier, where
    st = item_status(d, e["id"], e.get("by"), need=1 if e.get("scope") == "owner" else 2)
    if st == "rejected":
        return "failed (the evidence was rejected in review)", tier, where
    if st != "confirmed":
        return f"pending (the evidence is {st}: two keys first)", tier, where
    vs = variant_state(d, e["id"])
    if vs == "wrong":
        return "failed (the reviewers say the evidence is another variant)", tier, where
    if vs != "ok":
        return "pending (the reviewers are not sure the evidence is this variant)", tier, where
    return "measured", tier, where


_SHA_SEEN = {}


def _sha_once(path):
    """a file's sha256, once per (path, size, time) in this process — a hull's OBJ is tens of megabytes"""
    try:
        st = os.stat(path)
    except OSError:
        return None
    k = (os.path.normcase(os.path.abspath(path)), st.st_size, st.st_mtime)
    if k not in _SHA_SEEN:
        _SHA_SEEN[k] = _file_sha(path)
    return _SHA_SEEN[k]


def _model_keys(e):
    """every name of WHICH model a model evidence is: its model file's path and bytes, a hull's photo folder, its
    measurement's bytes — two evidences sharing any one are ONE model (the same file from two sites, one turntable
    carved twice), whatever page each was added under"""
    keys = set()
    mp = str(e.get("measure") or "")
    m = _json(mp, {}) if mp and os.path.isfile(mp) else {}
    for k in ("source", "obj"):
        v = m.get(k) if isinstance(m, dict) else None
        if not v:
            continue
        p = str(v) if os.path.isabs(str(v)) else os.path.join(os.getcwd(), str(v))
        keys.add("path:" + os.path.normcase(os.path.abspath(p)))
        if os.path.isfile(p):
            h = _sha_once(p)
            if h:
                keys.add("sha:" + h)
    if mp and os.path.isfile(mp):
        keys.add("sha:" + (_sha_once(mp) or ""))
    if e.get("measure_sha256"):
        keys.add("sha:" + str(e["measure_sha256"]))
    return keys or {"id:" + str(e.get("id"))}


def _one_model(seen, keys, value):
    """seen {key: value}: the value already given to any of these keys (the same model), else this one -> value"""
    have = next((seen[k] for k in keys if k in seen), None)
    out = value if have is None else have
    for k in keys:
        seen.setdefault(k, out)
    return out


def annotate_rows(d, offline=False, reg=None, quotes=None):
    """each row of this object with its tier, site and how it was confirmed"""
    reg = reg if reg is not None else registry()
    others = part_words(d)
    out = []
    gone = d.get("withdrawn_rows") or {}
    model_site = {}  # (one model is one site, whatever page it was added under)
    ev_by_id = {e["id"]: e for e in live_evidence(d)}
    for r in _rows_of(d):
        src = str(r.get("source", ""))
        kind = r.get("kind")
        if r.get("id") in gone:  # (withdrawn by whoever added it wrong: still shown, never counted)
            out.append({**r, "tier": "withdrawn", "site": site(src) if re.match(r"(?i)^https?://", src) else src,
                        "quote_check": f"withdrawn ({gone[r['id']].get('why', '')})", "review": "withdrawn",
                        "confirmed": False, "usable": False})
            continue
        if kind == "derived" and src.startswith("evidence:"):
            q, tier, where = measured_on(d, r, reg)
            ev = ev_by_id.get(src[len("evidence:"):].split("#")[0])
            if ev is not None:
                where = _one_model(model_site, _model_keys(ev), where)
            st = item_status(d, f"row:{r['id']}", r.get("by"))
            # (the number is the script's key; its MEANING — the dim's words — needs two keys: a model's box can hold
            #  what the words leave out — the Glock hull's 'width without the levers' was a lever and the magwell)
            out.append({**r, "tier": tier, "site": where, "quote_check": q, "review": st,
                        "confirmed": q == "measured" and st == "confirmed",
                        "usable": tier in COUNTS and not q.startswith("failed") and st != "rejected"})
            continue
        tier = "model" if kind == "model" else tier_of(src, d, reg)
        if tier == "owner" and not (kind == "measured" and r.get("by") == "owner"):
            tier = "local"  # (only the owner's own word is the owner's: `kit dossier fact --source owner --as owner`)
        if kind in ("wikipedia", "wikidata") and site(src) == "wikipedia.org" and r.get("read_by") == "kit":
            q = "read"  # (the kit read Wikimedia's API itself: no model's memory; still secondary)
        elif tier == "owner":
            q = "owner"
        elif quotes is not None and r["id"] in quotes:
            q = quotes[r["id"]]
        else:
            q = check_quote(src, r.get("quote"), r.get("value"), r.get("unit", "mm"), offline,
                            fact=(r.get("part", "overall"), r.get("dim", ""), others))
        st = item_status(d, f"row:{r['id']}", r.get("by"))
        confirmed = (q in ("verified", "read", "owner") or st == "confirmed") and st != "rejected"
        where = "owner" if tier == "owner" else (site(src) if not is_local(src) else f"local:{src}")
        out.append({**r, "tier": tier, "site": where, "quote_check": q, "review": st, "confirmed": confirmed,
                    "usable": tier in COUNTS and not q.startswith("failed") and st != "rejected"})
    return out


def _windows(rows, unit):
    """every run of values that agree END TO END (sorted, extremes within tolerance)"""
    vals = sorted(rows, key=lambda r: r["value"])
    return [vals[i:j + 1] for i in range(len(vals)) for j in range(i, len(vals))
            if _agree(vals[i]["value"], vals[j]["value"], unit)]


def _cluster(rows, unit):
    """the values most distinct sites agree on, end to end -> (value, its rows, distinct sites, best rival's distinct
    sites); two different runs as strong as each other (202 | 203.2 | 204) make the rival as strong: a disagreement"""
    def sites(w):
        return len({x["site"] for x in w})

    wins = _windows(rows, unit)
    n = max(sites(w) for w in wins)
    tops = [w for w in wins if sites(w) == n]
    sets = [{id(x) for x in w} for w in tops]
    maximal = [w for w, sw in zip(tops, sets) if not any(sw < other for other in sets)]
    distinct = {frozenset(id(x) for x in w) for w in maximal}
    best = maximal[0]
    rivals = [x for x in rows if id(x) not in {id(y) for y in best}]
    rival_n = max([sites(w) for w in _windows(rivals, unit)] or [0])
    if len(distinct) > 1:
        rival_n = n
    return statistics.median(x["value"] for x in best), best, n, rival_n


def grade_facts(d, rows):
    """the rows grouped by part.dim and graded -> {key: {value, unit, grade, why, rows, notes}}"""
    groups = {}
    for r in rows:
        groups.setdefault(_key(r.get("part", "overall"), r.get("dim", "")), []).append(r)
    family = {}
    for r in _rows_of(d, family=True):
        family.setdefault(_key(r.get("part", "overall"), r.get("dim", "")), []).append(r)
    out = {}
    for key, rs in sorted(groups.items()):
        unit = rs[0].get("unit", "mm")
        usable = [r for r in rs if r["usable"]]
        conf = [r for r in usable if r["confirmed"]]
        owner = [r for r in conf if r["tier"] == "owner"]
        prim = [r for r in conf if r["tier"] == "primary"]
        sec = [r for r in conf if r["tier"] == "secondary"]
        notes = []
        if owner or prim:
            base = owner or prim
            value = statistics.median(r["value"] for r in base)
            grade = "A" if _all_agree([r["value"] for r in base], unit) else "D"
            why = ("the owner measured it" if owner else
                   f"the maker / a patent office ({', '.join(sorted({r['site'] for r in base}))})")
            if grade == "D":
                why = "PRIMARY SOURCES DISAGREE: " + ", ".join(f"{r['value']:g} ({r['site']})" for r in base)
        elif sec and len({r["site"] for r in sec}) >= 2:
            value, mates, n, rival = _cluster(sec, unit)
            grade = "B" if n >= 2 and rival < n else "D"
            why = (f"{n} independent sites agree" if grade == "B" else
                   "sources disagree: " + ", ".join(f"{r['value']:g} ({r['site']})" for r in sec))
        elif usable:
            value = statistics.median(r["value"] for r in usable)
            grade = "C" if _all_agree([r["value"] for r in usable], unit) else "D"
            unconf = [r for r in usable if not r["confirmed"]]
            why = ("one source" if len({r["site"] for r in usable}) == 1 else "sources nobody confirmed") + (
                f" ({len(unconf)} row(s) unconfirmed: the quote not found yet or unquoted)" if unconf else "")
            if grade == "D":
                why = "sources disagree: " + ", ".join(f"{r['value']:g} ({r['site']})" for r in usable)
        else:
            value, grade = None, None
            why = "no usable row (" + "; ".join(sorted({r["quote_check"] if r["quote_check"].startswith("failed")
                                                         else r["tier"] for r in rs})) + ")"
        if value is not None:
            for r in rs:
                if not r["usable"]:
                    reason = ("rejected in review" if r["review"] == "rejected" else r["quote_check"]
                              if r["quote_check"].startswith("failed") else f"a {r['tier']} source")
                    notes.append(f"dropped {r['value']:g} {unit} ({r['site']}: {reason})")
                elif not _agree(r["value"], value, unit) and grade != "D":
                    notes.append(f"outvoted {r['value']:g} {unit} ({r['site']}, {r['tier']})")
            for f in family.get(key, []):
                if not _agree(f["value"], value, f.get("unit", unit)):
                    notes.append(f"the family '{f['object']}' says {f['value']:g} {unit} ({site(str(f['source']))}) — "
                                 "another variant's")
        out[key] = {"value": value, "unit": unit, "grade": grade, "why": why, "notes": notes,
                    "rows": [{k: r.get(k) for k in ("id", "value", "source", "kind", "tier", "site", "quote_check",
                                                     "review", "confirmed", "usable")} for r in rs]}
    return out


def frame_facts(d, facts):
    """the object's length / height / width from the graded facts (the category's frame, or the dossier's own)"""
    frame = (d.get("identity") or {}).get("frame") or category(d.get("category", "")).get("frame") or {
        "length": "overall.length", "height": "overall.height", "width": "overall.width"}
    out = {}
    for k, keys in frame.items():
        alts = []
        for key in (keys if isinstance(keys, list) else [keys]):
            f = facts.get(str(key).lower())
            if f and f["grade"] in ("A", "B") and f["value"]:
                alts.append({"mm": float(f["value"]), "grade": f["grade"], "key": str(key).lower()})
        if alts:  # (the first is preferred — px per mm; a proportion may match ANY meaning: a published width over the
            #  levers, or the body's own — a silhouette loses a 1 mm lever tip, a scan keeps it)
            out[k] = {**alts[0], "alts": alts}
    return out


def best_fact(facts, keys):
    """a fact asked for by one name or several (makers word the same size differently: "height" / "height incl.
    magazine") -> (the key, its graded fact) with the best grade, or (the first name, None)"""
    keys = [str(k).lower() for k in (keys if isinstance(keys, list) else [keys])]
    have = [(k, facts[k]) for k in keys if k in facts]
    if not have:
        return keys[0], None
    return min(have, key=lambda kf: "ABCD".find(kf[1]["grade"]) if kf[1]["grade"] else 9)


# ------------------------------------------------------------------------------------------- picture measurements
def picture_metrics(path, box=None):
    """what a script can see in a picture: size, a plain background, the object's box (from a plain background, or the
    given one), sharpness (variance of the Laplacian inside the box), a 64-bit difference hash"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    im = Image.open(path)
    im.load()
    w, h = im.size
    rgb = np.asarray(im.convert("RGB"), dtype=np.int16)
    k = max(2, min(w, h) // 200)
    border = np.concatenate([rgb[:k].reshape(-1, 3), rgb[-k:].reshape(-1, 3), rgb[:, :k].reshape(-1, 3),
                             rgb[:, -k:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    plain = float((np.abs(border - bg).max(1) < 24).mean()) >= 0.92
    out = {"w": w, "h": h, "plain_background": plain, "box": None, "box_from": None}
    alpha = None
    if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
        a = np.asarray(im.convert("RGBA"))[..., 3]
        edge = np.concatenate([a[:k].ravel(), a[-k:].ravel(), a[:, :k].ravel(), a[:, -k:].ravel()])
        if (edge < 16).mean() > 0.9 and (a > 16).any():
            alpha = a  # (a cut-out: transparent around, the object opaque — its colour hidden under the transparency)
    if alpha is not None:
        ys, xs = np.nonzero(alpha > 16)
        out["plain_background"] = True
        out["box"], out["box_from"] = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())], "alpha"
        if box:
            out["box_given_iou"] = round(_iou(out["box"], box), 3)
    elif box and not plain:
        out["box"], out["box_from"] = [int(round(v)) for v in box], "given"
    elif plain:
        diff = np.abs(rgb - bg).max(2) > 30
        rows = np.nonzero(diff.sum(1) > max(2, 0.002 * w))[0]
        cols = np.nonzero(diff.sum(0) > max(2, 0.002 * h))[0]
        if len(rows) and len(cols):
            out["box"], out["box_from"] = [int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])], "background"
            if box:
                out["box_given_iou"] = round(_iou(out["box"], box), 3)
        if out["box"] is None and box:
            out["box"], out["box_from"] = [int(round(v)) for v in box], "given"  # (nothing stood out: the given one)
    if out["box"]:
        x0, y0, x1, y1 = out["box"]
        out["cut_by_frame"] = bool(x0 <= 1 or y0 <= 1 or x1 >= w - 2 or y1 >= h - 2)
        g = rgb[max(0, y0):y1 + 1, max(0, x0):x1 + 1].mean(2)
        if g.shape[0] > 3 and g.shape[1] > 3:
            lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
            out["sharpness"] = round(float(lap.var()), 1)
    # how much fine detail survives halving the picture (information only: it depends on the content as much as on
    # an upscale — measured: a native soft close-up keeps 0.50, a 2x-upscaled sharp frame 0.53 — so no flag; take a
    # page's pictures at the size the page itself uses: GLOCK's resizer serves 2080 px of a 1040 px original)
    gray = Image.fromarray(np.asarray(im.convert("L")))
    if min(w, h) >= 64:
        half = gray.resize((max(1, w // 2), max(1, h // 2)), Image.BICUBIC).resize((w, h), Image.BICUBIC)

        def _lap_var(a):
            a = np.asarray(a, dtype=np.float32)
            return float((4 * a[1:-1, 1:-1] - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:]).var())

        full = _lap_var(gray)
        out["detail_kept_at_half"] = round(_lap_var(half) / full, 3) if full > 0 else None
    small = np.asarray(im.convert("L").resize((9, 8), Image.BILINEAR), dtype=np.int16)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    out["dhash"] = f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"
    return out


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / area if area > 0 else 0.0


def _hamming(a, b):
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _same_picture(pa, pb, size=48, tol=6.0, mirror=False, cache=None):
    """two files are ONE picture (a copy, resized or recompressed): their small grey thumbnails differ by under `tol`
    of 255 on average where either shows the object (not the shared background) — the 64-bit hash alone called
    GLOCK's front and rear frames (two dark slivers on white) one picture. mirror: b flipped left to right (a flipped
    copy is one picture too: a silhouette's rear view is its front view flipped)"""
    if not (pa and pb):
        return False
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    cache = {} if cache is None else cache
    try:
        for p in (pa, pb):
            if (p, size) not in cache:
                cache[(p, size)] = np.asarray(Image.open(p).convert("L").resize((size, size), Image.BILINEAR),
                                              dtype=np.float32)
    except OSError:
        return False
    ta, tb = cache[(pa, size)], cache[(pb, size)]
    if mirror:
        tb = tb[:, ::-1]

    def ground(t):
        return float(np.median(np.concatenate([t[0], t[-1], t[:, 0], t[:, -1]])))

    shown = (np.abs(ta - ground(ta)) > 25) | (np.abs(tb - ground(tb)) > 25)
    if shown.sum() < 20:
        shown = np.ones_like(shown)
    return float(np.abs(ta - tb)[shown].mean()) < tol


def part_frame(facts, part):
    """a picture that shows ONE part (a patent's slide, a close-up of the barrel): its frame from that part's graded
    sizes — <part>.length / .height / .width, A or B only"""
    out = {}
    for k in ("length", "height", "width"):
        f = facts.get(f"{str(part).lower()}.{k}")
        if f and f["grade"] in ("A", "B") and f["value"]:
            out[k] = {"mm": float(f["value"]), "grade": f["grade"], "key": f"{part}.{k}"}
    return out


def proportions(view, box, frame):
    """a picture's box against the facts: its width over height vs the object's, and px per mm"""
    spec = VIEW_FRAME.get(view or "")
    if not (spec and box):
        return {}
    a, b, across = spec
    bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
    out = {}
    if across in frame:
        out["px_per_mm"] = round(bw / frame[across]["mm"], 2)
    if a in frame and b in frame and bh > 0:
        want, against = _closest(bw / bh, frame[a], frame[b])
        out["aspect"] = round(bw / bh, 4)
        out["aspect_want"] = round(want, 4)
        out["aspect_off"] = round((bw / bh) / want - 1.0, 4)
        out["aspect_against"] = against
    return out


def _closest(ratio, fa, fb):
    """the published meaning a ratio is closest to -> (the wanted ratio, 'key / key')"""
    best = None
    for x in fa.get("alts") or [fa]:
        for y in fb.get("alts") or [fb]:
            want = x["mm"] / y["mm"]
            off = abs(ratio / want - 1.0)
            if best is None or off < best[0]:
                best = (off, want, f"{x['key']} / {y['key']}")
    return best[1], best[2]


def model_proportions(size_mm, frame):
    """a reference model's size [width, height, length] against the facts: length/height and length/width"""
    if not (isinstance(size_mm, list) and len(size_mm) == 3 and all(float(v) > 0 for v in size_mm)):
        return {}
    w, h, l_ = (float(v) for v in size_mm)
    out = {"size_mm": [w, h, l_]}
    for name, mine, a, b in (("length/height", l_ / h, "length", "height"), ("length/width", l_ / w, "length",
                                                                            "width")):
        if a in frame and b in frame:
            want, against = _closest(mine, frame[a], frame[b])
            out[name] = {"model": round(mine, 4), "want": round(want, 4), "off": round(mine / want - 1.0, 4),
                         "against": against}
    return out


# ------------------------------------------------------------------------------------------------- the check
def live_evidence(d):
    """the evidence still in play (a withdrawn item keeps its record and reason, and counts for nothing)"""
    return [e for e in d.get("evidence") or [] if not e.get("withdrawn")]


def live(items):
    return [i for i in items or [] if isinstance(i, dict) and not i.get("withdrawn")]


def _file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _evidence_file(d, e):
    p = e.get("file")
    if not p:
        return None
    p = p if os.path.isabs(p) else os.path.join(EVIDENCE, d["slug"], p)
    return p if os.path.isfile(p) else None


def check(d, offline=False, quotes=None):
    """grade the facts, measure the evidence, confirm the anatomy, cover the category's needs, score -> report"""
    reg = registry()
    cat = category(d.get("category", ""))
    rows = annotate_rows(d, offline, reg, quotes)
    facts = grade_facts(d, rows)
    frame = frame_facts(d, facts)
    problems, open_items = [], []

    # the evidence --------------------------------------------------------------------------------------------
    ev_out = []
    for e in live_evidence(d):
        is_model = e.get("kind") == "model"
        st = item_status(d, e["id"], e.get("by"), need=1 if e.get("scope") == "owner" else 2, views=not is_model)
        src = e.get("page") or e.get("url")
        src = src if src and re.match(r"(?i)^https?://", str(src)) else None
        row = {"id": e["id"], "kind": e.get("kind"), "scope": e.get("scope"), "status": st,
               "view": agreed(d, e["id"], "view") or (e.get("claimed") or {}).get("view"),
               "good_for": agreed(d, e["id"], "good_for"), "square": agreed(d, e["id"], "square"),
               "variant": variant_state(d, e["id"]), "of": e.get("of"), "flags": [], "counts": True,
               "source_tier": tier_of(src, d, reg) if src else ("owner" if e.get("scope") == "owner"
                                                                and e.get("by") == "owner" else "unknown")}
        if row["source_tier"] not in COUNTS:
            row["counts"] = False
            row["flags"].append({"blocked": "from a blocked site (kit/knowledge/sources.json)",
                                 "suspect": "from a page that looks like a content farm: add its site to "
                                            "kit/knowledge/sources.json's domains once a reviewer vouched for it",
                                 "unknown": "no page it came from (add it again with --page <url>)"}.get(
                                     row["source_tier"], f"its source counts for nothing ({row['source_tier']})"))
        if is_model:
            mp = e.get("measure") or ""
            mfile = mp if os.path.isabs(mp) else os.path.join(os.getcwd(), mp)
            m = _json(mfile, {})
            m = m if isinstance(m, dict) else {}
            if m and e.get("measure_sha256") and _file_sha(mfile) != e["measure_sha256"]:
                row["flags"].append("its measurement changed since it was added (not the one reviewed): add it again")
                m = {}
            row["metrics"] = model_proportions(m.get("size_mm"), frame)
            for name in ("length/height", "length/width"):
                pr = row["metrics"].get(name)
                if pr and abs(pr["off"]) > PROPORTION_TOL:
                    row["flags"].append(f"{name} off by {pr['off']:+.1%} against the facts (a scan short / long, "
                                        "another variant, or the facts mean something else)")
            if not m:
                row["flags"].append(f"no measurement ({e.get('measure')}): kit refs measure / kit library inspect")
            if not all(k in row["metrics"] for k in ("length/height", "length/width")):
                row["counts"] = False  # (true proportions unproven: the facts or its size are missing)
        else:
            f = _evidence_file(d, e)
            met = None
            if not f:
                row["flags"].append("the file is not on this machine (kit dossier add again from its url)")
            elif e.get("file_sha256") and _file_sha(f) != e["file_sha256"]:
                row["flags"].append("the file changed since it was added (not the picture reviewed): add it again")
            else:
                try:
                    met = picture_metrics(f, e.get("box"))
                except Exception as ex:  # noqa: BLE001 — one broken picture is said, the check goes on
                    row["flags"].append(f"unreadable picture ({type(ex).__name__})")
            if met is None:
                row["metrics"], row["counts"] = {}, False
            else:
                own = part_frame(facts, e["of"]) if e.get("of") else frame
                met.update(proportions(row["view"], met.get("box"), own))
                if e.get("of"):
                    met["measured_against"] = f"the {e['of']}'s own sizes"
                row["metrics"] = met
                if met.get("cut_by_frame"):
                    row["flags"].append("the object touches the picture's edge (cropped?)")
                if met.get("box_given_iou") is not None and met["box_given_iou"] < 0.9:
                    row["flags"].append(f"the given --box disagrees with the measured one (overlap "
                                        f"{met['box_given_iou']:.0%}): the measured one is used")
                if met.get("aspect_off") is not None and abs(met["aspect_off"]) > PROPORTION_TOL:
                    row["flags"].append(f"proportions off by {met['aspect_off']:+.1%} for a {row['view']} view "
                                        "(perspective, a different variant, a crop, or not square-on)")
                if not met.get("box") and row["view"] in VIEW_FRAME:
                    row["flags"].append("no object box (a busy background): add it again with --box x0,y0,x1,y1")
        if row["status"] == "confirmed" and row["view"] in VIEW_FRAME and row["square"] is None and not is_model:
            row["flags"].append("square-on: the reviewers did not agree (it covers no view)")
        ev_out.append(row)
    # duplicates (the same picture from two sites is one picture)
    def rank(r):  # (the original of copies: confirmed and counting first, never a stale or pending one before it)
        return (0 if r["status"] == "confirmed" and r.get("counts", True) else
                1 if r["status"] in ("pending", "disputed") and r.get("counts", True) else 2)

    pics = sorted((r for r in ev_out if (r.get("metrics") or {}).get("dhash")), key=rank)
    files = {e["id"]: _evidence_file(d, e) for e in live_evidence(d)}
    thumbs = {}
    for i, a in enumerate(pics):
        if a["status"] == "rejected" or a.get("duplicate_of"):
            continue  # (a rejected or duplicate picture takes no other's place)
        for b in pics[i + 1:]:
            if b.get("duplicate_of") or \
                    abs(a["metrics"]["w"] / a["metrics"]["h"] - b["metrics"]["w"] / b["metrics"]["h"]) >= 0.02:
                continue
            if _hamming(a["metrics"]["dhash"], b["metrics"]["dhash"]) <= 5 and \
                    _same_picture(files.get(a["id"]), files.get(b["id"]), cache=thumbs):
                b["flags"].append(f"the same picture as {a['id']}")
                b["duplicate_of"] = a["id"]
            elif _same_picture(files.get(a["id"]), files.get(b["id"]), mirror=True, cache=thumbs):
                b["flags"].append(f"the same picture as {a['id']}, mirrored (a flipped copy holds one view's "
                                  "information, not two: a silhouette's rear is its front flipped)")
                b["duplicate_of"] = a["id"]
    first_of = {}
    for r in sorted(ev_out, key=rank):
        e = next((x for x in live_evidence(d) if x["id"] == r["id"]), None)
        if r["kind"] != "model" or r["status"] == "rejected" or e is None:
            continue
        orig = _one_model(first_of, _model_keys(e), r["id"])
        if orig != r["id"]:
            r["flags"].append(f"the same model as {orig} (one model, whatever page it came from)")
            r["duplicate_of"] = orig
    for r in ev_out:
        if r["status"] in ("pending", "disputed"):
            open_items.append(f"{r['id']} ({r['kind']}, {r['status']})")

    # anatomy, tells, markings: a verified quote is a script's key; else two reviewers ---------------------------
    def confirm_items(items, prefix):
        out, seen = [], set()
        for it in live(items):
            what = it.get("name") or it.get("text") or ""
            how = {"names": (what, it.get("no"))} if prefix in ("part", "marking") else {"about": what}
            q = check_quote(it.get("source", ""), it.get("quote"), None, offline=offline, **how) \
                if it.get("quote") else "unquoted"
            st = item_status(d, it["id"], it.get("by"))
            tier = tier_of(it.get("source", ""), d, reg)
            ok = (q == "verified" or st == "confirmed") and st != "rejected" and tier in COUNTS
            key = _name_key(what)
            twice = key in seen
            seen.add(key)
            out.append({"id": it["id"], "what": what, "quote_check": q, "review": st, "tier": tier,
                        "confirmed": ok and not twice, **({"same_as_earlier": True} if twice else {})})
            if not ok and st != "rejected" and tier in COUNTS:
                open_items.append(f"{it['id']} ({prefix}: {q}, review {st})")
        return out

    parts = confirm_items(d.get("parts") or [], "part")
    tells = confirm_items((d.get("identity") or {}).get("tells") or [], "tell")
    marks = confirm_items(d.get("markings") or [], "marking")
    n_rows_open = 0
    for key, f in facts.items():
        if f["grade"] in ("C", None) and any(not r["confirmed"] and r["usable"] for r in f["rows"]):
            for r in f["rows"]:
                if not r["confirmed"] and r["usable"]:
                    open_items.append(f"row:{r['id']} ({key} {r['value']:g}: {r['quote_check']})")
                    n_rows_open += 1
        if f["grade"] == "D":
            problems.append(f"{key}: {f['why']}")

    # a size measured ON the references (not the maker's) that a picture's or model's proportions were checked
    # against is said: the owner sees which checks rest on the references agreeing with each other
    measured_keys = set()
    for k, f in facts.items():  # (the rows that SET the value: an outvoted published row does not)
        if f["grade"] not in ("A", "B") or f["value"] is None:
            continue
        setting = [x for x in f["rows"] if x["confirmed"] and _agree(x["value"], f["value"], f["unit"])]
        if setting and all(x.get("kind") == "derived" for x in setting):
            measured_keys.add(k)
    for r in ev_out:
        met = r.get("metrics") or {}
        against = [str(met.get("aspect_against") or "")] + [str(v.get("against") or "") for v in met.values()
                                                             if isinstance(v, dict)]
        named = {x.strip() for a in against for x in a.split(" / ") if x.strip()}
        via = sorted(measured_keys & named)
        if via:
            r["notes"] = [f"proportions checked against {', '.join(via)} (the closest meaning): a size measured ON "
                          "the reference models, not the maker's"]

    # coverage against the category -----------------------------------------------------------------------------
    min_px = float(cat.get("min_px_per_mm", 2.0))
    cov_facts = {}
    for want in cat.get("facts") or []:
        key, f = best_fact(facts, want)
        cov_facts[key] = (f or {}).get("grade")
    usable_ev = [r for r in ev_out if r["status"] == "confirmed" and r["counts"] and not r.get("duplicate_of")]
    cov_views = {}
    for v in cat.get("views") or []:
        best = [r for r in usable_ev if r["view"] == v and (r.get("metrics") or {}).get("px_per_mm", 0) >= min_px
                and not any("proportions off" in fl for fl in r["flags"]) and r.get("square") is True
                and (r.get("metrics") or {}).get("aspect_off") is not None
                and r.get("variant") == "ok" and not r.get("of")]
        cov_views[v] = [r["id"] for r in best]
    cov_close = {}
    for c in cat.get("closeups") or []:
        cid = c["id"] if isinstance(c, dict) else str(c)
        cov_close[cid] = [r["id"] for r in usable_ev if f"closeup:{cid}" in r["good_for"] and r.get("variant") == "ok"]
    models_ok = [r["id"] for r in usable_ev if r["kind"] == "model" and not r["flags"] and r.get("variant") == "ok"]
    candidates = {v: sum(1 for r in ev_out if r["view"] == v and r["status"] != "rejected") for v in cat.get("views")
                  or []}

    # the score ------------------------------------------------------------------------------------------------------
    w = cat.get("weights") or {"facts": 30, "views": 25, "closeups": 15, "anatomy": 10, "models": 10, "reviews": 10}
    part_min, tell_min, model_min = (int(cat.get("anatomy_min", 8)), int(cat.get("tells_min", 3)),
                                     int(cat.get("models_min", 2)))
    s_facts = (sum(GRADE_VALUE[g] for g in cov_facts.values()) / len(cov_facts)) if cov_facts else 1.0
    s_views = (sum(1 for v in cov_views.values() if v) / len(cov_views)) if cov_views else 1.0
    s_close = (sum(1 for v in cov_close.values() if v) / len(cov_close)) if cov_close else 1.0
    s_anat = 0.7 * min(1.0, sum(p["confirmed"] for p in parts) / max(1, part_min)) + \
        0.3 * min(1.0, sum(t["confirmed"] for t in tells) / max(1, tell_min))
    s_models = min(1.0, len(models_ok) / max(1, model_min)) if model_min else 1.0
    n_items = len(ev_out) + len(parts) + len(tells) + len(marks) + n_rows_open
    s_rev = 1.0 - len(open_items) / n_items if n_items else 0.0
    parts_score = {"facts": s_facts, "views": s_views, "closeups": s_close, "anatomy": s_anat, "models": s_models,
                   "reviews": s_rev}
    score = round(sum(w[k] * parts_score[k] for k in w) / max(1, sum(w.values())) * 100, 1)
    missing = []
    missing += [f"fact {k}: " + (f"grade {g}" if g else "none") for k, g in cov_facts.items() if g not in ("A", "B")]
    missing += [f"view {v}: no confirmed picture at {min_px:g}+ px/mm (candidates: {candidates.get(v, 0)})"
                for v, ids in cov_views.items() if not ids]
    missing += [f"close-up {c}" for c, ids in cov_close.items() if not ids]
    if sum(p["confirmed"] for p in parts) < part_min:
        missing.append(f"anatomy: {sum(p['confirmed'] for p in parts)} confirmed part(s) of {part_min}")
    if sum(t["confirmed"] for t in tells) < tell_min:
        missing.append(f"tells: {sum(t['confirmed'] for t in tells)} confirmed of {tell_min} (what sets this variant "
                       "apart from its siblings)")
    if len(models_ok) < model_min:
        missing.append(f"reference models: {len(models_ok)} confirmed with true proportions of {model_min}")
    report = {"object": d["object"], "slug": d["slug"], "checked": _now(), "score": score,
              "bar": float(cat.get("bar", 80)), "parts_score": {k: round(v, 3) for k, v in parts_score.items()},
              "facts": facts, "frame": frame, "evidence": ev_out, "parts": parts, "tells": tells, "markings": marks,
              "coverage": {"facts": cov_facts, "views": cov_views, "closeups": cov_close, "models": models_ok,
                           "candidates": candidates},
              "missing": missing, "problems": problems, "open": open_items, "sheet_sha": sheet_sha(d),
              "check_key": check_key(d),
              "withdrawn": [{"id": e["id"], **e["withdrawn"]} for e in d.get("evidence") or [] if e.get("withdrawn")],
              "approval": {}}
    report["approval"] = approval_state(d, report)
    _write(os.path.join(_build_dir(d["slug"]), "check.json"), report)
    return report


# ------------------------------------------------------------------------------------------ the sheet's identity
def sheet_sha(d):
    """everything the owner approves: identity, sources, anatomy, evidence (not its measurements), reviews and the
    fact rows — any change makes an approval stale"""
    keep = {k: d.get(k) for k in ("object", "category", "identity", "sources", "parts", "markings", "reviews")}
    if d.get("withdrawn_rows"):
        keep["withdrawn_rows"] = d["withdrawn_rows"]
    keep["evidence"] = [{k: v for k, v in e.items() if k not in ("added",)} for e in d.get("evidence") or []]
    keep["rows"] = sorted((json.dumps(r, sort_keys=True, default=str) for r in _rows_of(d)))
    return hashlib.sha256(json.dumps(keep, sort_keys=True, ensure_ascii=True, default=str).encode()).hexdigest()[:16]


def check_key(d):
    """what a cached check depends on: the sheet, the site list, the category, this code, the evidence files"""
    h = hashlib.sha256(sheet_sha(d).encode())
    for path in (os.path.join(KNOW, "sources.json"), os.path.join(KNOW, "categories", f"{d.get('category')}.json"),
                 os.path.abspath(__file__)):
        try:
            with open(path, "rb") as fh:
                h.update(fh.read())
        except OSError:
            h.update(b"-")
    cited = {str(r.get("source")) for r in _rows_of(d)} | {str(i.get("source")) for i in
                                                          live(d.get("parts")) + live(d.get("markings")) +
                                                          live((d.get("identity") or {}).get("tells"))}
    for u in sorted(x for x in cited if not is_local(x)):
        c = os.path.join(EVIDENCE, "_sources", f"{hashlib.sha1(u.encode()).hexdigest()[:16]}.txt")
        h.update(f"{u}:{os.path.getsize(c) if os.path.isfile(c) else -1}:"
                 f"{os.path.getmtime(c) if os.path.isfile(c) else -1}".encode())
    for e in live_evidence(d):
        f = _evidence_file(d, e) or (e.get("measure") if os.path.isfile(str(e.get("measure") or "")) else None)
        h.update(f"{e['id']}:{os.path.getsize(f) if f else -1}:{os.path.getmtime(f) if f else -1}".encode())
    for r in _rows_of(d):
        if r.get("measure"):
            f = str(r["measure"]) if os.path.isabs(str(r["measure"])) else os.path.join(os.getcwd(), str(r["measure"]))
            ok = os.path.isfile(f)
            h.update(f"{r.get('id')}:{os.path.getsize(f) if ok else -1}:{os.path.getmtime(f) if ok else -1}".encode())
    return h.hexdigest()[:16]


def outcome_sha(rep):
    """what the owner saw graded: each fact's grade and value, each evidence item's status, the coverage, the confirmed
    anatomy — a re-graded fact (a site blocked, a page changed) makes an approval stale even when no input changed"""
    keep = {"facts": {k: (f["grade"], f["value"]) for k, f in rep["facts"].items()},
            "evidence": sorted((e["id"], e["status"], e.get("counts"), e.get("view")) for e in rep["evidence"]),
            "coverage": rep["coverage"], "parts": sorted(p["id"] for p in rep["parts"] if p["confirmed"]),
            "tells": sorted(t["id"] for t in rep["tells"] if t["confirmed"])}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()[:16]


def sheet_id(rep):
    """the id printed on a sheet: its inputs and its outcomes — the owner approves exactly what they saw"""
    return hashlib.sha256(f"{rep['sheet_sha']}:{outcome_sha(rep)}".encode()).hexdigest()[:16]


def approval_state(d, rep=None):
    a = d.get("approval") or None
    if not a:
        return {"approved": False, "stale": False}
    stale = a.get("sheet_sha") != sheet_sha(d) or (rep is not None and a.get("outcome_sha") != outcome_sha(rep))
    return {"approved": True, "stale": stale, "by": a.get("by"), "date": a.get("date"), "note": a.get("note")}


def summary_for(name, offline=True):
    """for kit plan / kit pack: None when no dossier, else {slug, score, bar, approved, stale, missing, open, path}"""
    try:
        d = load(name)
    except Missing:
        broken = _broken_files()
        if broken:
            raise Broken(f"no dossier names '{name}', and {', '.join(broken[:3])} cannot be read (it may be this "
                         "object's): fix it or move it away") from None
        return None
    rep = _json(os.path.join(_build_dir(d["slug"]), "check.json"))
    if not isinstance(rep, dict) or rep.get("check_key") != check_key(d):
        rep = check(d, offline=offline)
    return {"slug": d["slug"], "object": d["object"], "score": rep["score"], "bar": rep["bar"],
            "approved": approval_state(d, rep)["approved"], "stale": approval_state(d, rep)["stale"],
            "missing": rep["missing"], "open": rep["open"], "problems": rep["problems"], "facts": rep["facts"],
            "frame": rep["frame"], "path": d.get("_path")}


# ------------------------------------------------------------------------------------------------ the review packet
QUESTIONS = {
    "picture": {
        "verdict": "accept (use it) | limited (use it only for what good_for says) | reject",
        "object": "yes | no | unsure — is this the object at all?",
        "variant": "ok | wrong | unsure — check the dossier's tells: name the ones you SEE (tells_seen) and any it "
                   "contradicts (tells_against)",
        "stock": "true | false — no aftermarket parts, cuts, coatings, lights, optics",
        "view": " | ".join(VIEWS),
        "square": "true | false — square-on within ~5 degrees, no strong perspective (parallel edges stay parallel)",
        "good_for": "a list: " + ", ".join(GOOD_FOR) + ", closeup:<id> (the category's close-ups)",
        "why": "one line: what you saw that decided it"},
    "model": {
        "verdict": "accept | limited | reject",
        "object": "yes | no | unsure", "variant": "ok | wrong | unsure (tells_seen / tells_against)",
        "good_for": "a list: proportions, parts, section, mechanism, silhouette",
        "why": "one line — look at its parts sheet / renders; its proportions against the facts are in metrics"},
    "row": {"verdict": "accept (the source says exactly this number for this part and THIS variant) | reject",
            "why": "where in the source you found it (or did not)"},
    "tell": {"verdict": "accept (the source says it, and it really sets the variant apart) | reject", "why": "one line"},
    "part": {"verdict": "accept (the source lists this part as written) | reject", "why": "one line"},
    "marking": {"verdict": "accept | reject", "why": "one line"},
}


BLIND_METRICS = ("w", "h", "plain_background", "box", "box_from", "cut_by_frame", "sharpness", "detail_kept_at_half")


def seen_open(d, by, before=None):
    """the items a reviewer saw in an OPEN packet (claims and earlier verdicts shown): never blind for them again"""
    out = set()
    for pk in d.get("packets") or []:
        if pk.get("by") == by and not pk.get("blind") and pk.get("id") != before:
            out |= set(pk.get("items") or [])
    return out


def settled_open(d, item_id, status):
    """still worth a review: pending / disputed, or rejected by ONE reviewer only (one reject drops an item, but a
    second reviewer gets to look: an accept makes it disputed); two rejects are final"""
    if status != "rejected":
        return True
    return len(latest_verdicts(d, item_id)) < 2


def packet(d, by, blind=False, report=None):
    """the items still waiting for a key from THIS reviewer -> the packet (and a contact sheet of its pictures)"""
    report = report or check(d, offline=True)
    items = []
    done_by_me = lambda iid: by in latest_verdicts(d, iid)  # noqa: E731
    seen = seen_open(d, by) if blind else set()
    ev_rep = {r["id"]: r for r in report["evidence"]}
    for e in live_evidence(d):
        r = ev_rep.get(e["id"], {})
        if r.get("status") == "confirmed" or done_by_me(e["id"]) or not settled_open(d, e["id"], r.get("status")) \
                or (blind and e["id"] in seen):
            continue
        metrics = {k: v for k, v in (r.get("metrics") or {}).items() if k != "dhash"}
        flags = list(r.get("flags") or [])
        if blind and e.get("kind") != "model":
            # (what depends on the CLAIMED view — px/mm, the proportions for that view — would tell the view)
            metrics = {k: v for k, v in metrics.items() if k in BLIND_METRICS}
            flags = [f for f in flags if not re.search(r"view|proportions|square", f)]
        it = {"id": e["id"], "type": "model" if e.get("kind") == "model" else "picture",
              "file": _evidence_file(d, e), "url": e.get("url"), "page": e.get("page"), "scope": e.get("scope"),
              "metrics": metrics, "flags": flags}
        if e.get("kind") == "model":
            it["measure"] = e.get("measure")
            it["sheets"] = e.get("sheets") or []
        if not blind:
            it["claimed"] = e.get("claimed")
            it["earlier"] = {k: v for k, (v, _b) in latest_verdicts(d, e["id"]).items()}
        items.append(it)
    for key, f in report["facts"].items():
        if f["grade"] not in ("C", None):
            continue  # (a fact already graded A / B gains nothing from confirming its weaker rows)
        for r in f["rows"]:
            if r["usable"] and not r["confirmed"] and not done_by_me(f"row:{r['id']}") and \
                    not (blind and f"row:{r['id']}" in seen):
                row = next((x for x in _rows_of(d) if x["id"] == r["id"]), {})
                items.append({"id": f"row:{r['id']}", "type": "row", "fact": key, "value": r["value"],
                              "unit": f["unit"], "source": r["source"], "quote": row.get("quote"),
                              "quote_check": r["quote_check"],
                              **({k: row[k] for k in ("measure", "note") if row.get(k)}
                                 if row.get("kind") == "derived" else {})})
    for kind, src_items, rep_items in (("part", d.get("parts") or [], report["parts"]),
                                       ("tell", (d.get("identity") or {}).get("tells") or [], report["tells"]),
                                       ("marking", d.get("markings") or [], report["markings"])):
        st = {x["id"]: x for x in rep_items}
        for it in live(src_items):
            if it["id"] not in st or st[it["id"]].get("confirmed") or done_by_me(it["id"]) or \
                    st[it["id"]].get("tier") not in COUNTS or not settled_open(d, it["id"], st[it["id"]]["review"]) \
                    or (blind and it["id"] in seen):
                continue
            items.append({"id": it["id"], "type": kind, **{k: it.get(k) for k in (
                "name", "no", "text", "vs", "where", "function", "moves", "joins", "source", "quote") if it.get(k)}})
    body = {"object": d["object"], "slug": d["slug"], "by": by, "blind": blind, "made": _now(),
            "identity": {k: (live(v) if k == "tells" else v) for k, v in (d.get("identity") or {}).items()
                         if k != "tells" or not blind},
            "facts": {k: {"value": f["value"], "unit": f["unit"], "grade": f["grade"]}
                      for k, f in report["facts"].items() if f["grade"] in ("A", "B")},
            "closeups": category(d.get("category", "")).get("closeups") or [],
            "questions": {t: QUESTIONS[t] for t in sorted({i["type"] for i in items})}, "items": items}
    if blind:
        # (blind: the reviewer gets the tells' TEXT to check against, never the earlier verdicts or the claims)
        body["identity"]["tells"] = [{"id": t["id"], "text": t.get("text")} for t in
                                     live((d.get("identity") or {}).get("tells") or [])]
    sha = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:12]
    body["packet"] = sha
    folder = os.path.join(_build_dir(d["slug"]), "packets")
    _write(os.path.join(folder, f"{sha}.json"), body)
    # (recorded in the dossier itself: who saw what openly outlives the build folder)
    d.setdefault("packets", []).append({"id": sha, "by": by, "blind": blind, "made": body["made"],
                                        "items": [i["id"] for i in items]})
    template = {"packet": sha, "by": by, "items": {
        i["id"]: ({"verdict": "?", "object": "?", "variant": "?", "tells_seen": [], "tells_against": [],
                   "stock": None, "view": "?", "square": None, "good_for": [], "why": ""}
                  if i["type"] == "picture" else
                  {"verdict": "?", "object": "?", "variant": "?", "good_for": [], "why": ""} if i["type"] == "model"
                  else {"verdict": "?", "why": ""}) for i in items}}
    _write(os.path.join(folder, f"{sha}.answers.json"), template)
    contact = _contact_sheet([i for i in items if i.get("file") and i["type"] == "picture"],
                             os.path.join(folder, f"{sha}.contact.jpg"))
    return body, os.path.join(folder, f"{sha}.json"), os.path.join(folder, f"{sha}.answers.json"), contact


def _contact_sheet(items, out, tw=360, th=260, cols=4):
    if not items:
        return None
    from PIL import Image, ImageDraw  # noqa: PLC0415

    rows_n = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows_n * (th + 24)), (250, 250, 250))
    dr = ImageDraw.Draw(sheet)
    for k, it in enumerate(items):
        try:
            im = Image.open(it["file"]).convert("RGB")
        except OSError:
            continue
        im.thumbnail((tw - 8, th - 8))
        x, y = (k % cols) * tw, (k // cols) * (th + 24)
        sheet.paste(im, (x + (tw - im.width) // 2, y + 4))
        dr.text((x + 6, y + th + 4), f"{it['id']}  {it['metrics'].get('w', '?')}x{it['metrics'].get('h', '?')}",
                fill=(180, 0, 0))
    sheet.save(out, quality=88)
    return out


def apply_answers(d, answers, by):
    """record a reviewer's answers (validated) -> (n recorded, problems)"""
    if not isinstance(answers, dict) or not isinstance(answers.get("items"), dict):
        return 0, ["the answers file needs {\"packet\": <sha>, \"items\": {<id>: {...}}}"]
    pid = str(answers.get("packet") or "")
    if not re.fullmatch(r"[0-9a-f]{12}", pid):
        return 0, ["the answers must name their packet (its 12-character id: kit dossier review ... --as <you>)"]
    pk = _json(os.path.join(_build_dir(d["slug"]), "packets", f"{pid}.json"))
    if not isinstance(pk, dict):
        return 0, [f"no packet {pid} for {d['slug']}: make one (kit dossier review \"{d['object']}\" --as {by})"]
    body = {k: v for k, v in pk.items() if k != "packet"}
    if hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:12] != pid or \
            pk.get("slug") != d["slug"]:
        return 0, [f"packet {pid} was changed after it was made (or is another dossier's): make a new one"]
    if pk.get("by") != by:
        return 0, [f"packet {pid} was made for {pk.get('by')}, not {by}"]
    if pid not in {x.get("id") for x in d.get("packets") or [] if x.get("by") == by}:
        return 0, [f"packet {pid} is not recorded in this dossier for {by} (make it with kit dossier review)"]
    in_packet = {i.get("id") for i in pk.get("items") or []}
    if pk.get("blind"):
        seen = seen_open(d, by, before=pid)
        if in_packet & seen:
            return 0, [f"{', '.join(sorted(in_packet & seen))}: {by} saw these in an open packet — a blind answer from "
                       "them is not blind (a fresh reviewer answers blind)"]
    known = {e["id"]: ("model" if e.get("kind") == "model" else "picture") for e in live_evidence(d)}
    known.update({p["id"]: "part" for p in live(d.get("parts"))})
    known.update({t["id"]: "tell" for t in live((d.get("identity") or {}).get("tells"))})
    known.update({m["id"]: "marking" for m in live(d.get("markings"))})
    known.update({f"row:{r['id']}": "row" for r in _rows_of(d)})
    closeups = {(c["id"] if isinstance(c, dict) else str(c)) for c in
                category(d.get("category", "")).get("closeups") or []}
    good, problems = {}, []
    for iid, v in answers["items"].items():
        if iid not in known:
            problems.append(f"{iid}: no such item")
            continue
        if iid not in in_packet:
            if isinstance(v, dict) and v.get("verdict") in ("?", None, ""):
                continue
            problems.append(f"{iid}: not in packet {pid} (answer only what your packet asks)")
            continue
        if not isinstance(v, dict) or v.get("verdict") not in VERDICTS:
            if isinstance(v, dict) and v.get("verdict") in ("?", None, ""):
                continue  # (left unanswered: skipped)
            problems.append(f"{iid}: verdict must be one of {', '.join(VERDICTS)}")
            continue
        if not str(v.get("why") or "").strip():
            problems.append(f"{iid}: say why (one line: what you saw)")
            continue
        typed = {"view": str, "square": bool, "variant": str, "object": str, "stock": bool, "good_for": list,
                 "tells_seen": list, "tells_against": list, "why": str}
        wrong = [k for k, t in typed.items() if v.get(k) is not None and not isinstance(v.get(k), t)]
        if wrong or (v.get("view") is not None and v["view"] not in VIEWS):
            problems.append(f"{iid}: wrong kind of answer for {', '.join(wrong) or 'view'}")
            continue
        if v.get("variant") not in (None, "ok", "wrong", "unsure") or v.get("object") not in (None, "yes", "no",
                                                                                                "unsure"):
            problems.append(f"{iid}: object is yes | no | unsure, variant ok | wrong | unsure")
            continue
        if known[iid] in ("picture", "model") and v["verdict"] != "reject":
            if v.get("variant") == "wrong" and v["verdict"] == "accept":
                problems.append(f"{iid}: the wrong variant can only be 'limited' (say what it is still good for) "
                                "or 'reject'")
                continue
            if v.get("object") == "no":
                problems.append(f"{iid}: not the object at all is a 'reject'")
                continue
        if known[iid] in ("picture", "model") and v["verdict"] != "reject":
            if known[iid] == "picture" and v.get("view") not in VIEWS:
                problems.append(f"{iid}: view must be one of {', '.join(VIEWS)}")
                continue
            if known[iid] == "picture" and not isinstance(v.get("square"), bool):
                problems.append(f"{iid}: square must be true or false")
                continue
            if not isinstance(v.get("good_for") or [], list) or not all(isinstance(g, str) for g in
                                                                         v.get("good_for") or []):
                problems.append(f"{iid}: good_for is a list of words")
                continue
            bad = [g for g in v.get("good_for") or [] if g not in GOOD_FOR and
                   not (g.startswith("closeup:") and g[8:] in closeups) and not g.startswith("outline:")]
            if bad:
                problems.append(f"{iid}: unknown good_for {bad} (use {', '.join(GOOD_FOR)}, outline:<part>, "
                                f"closeup:<{'|'.join(sorted(closeups)) or 'id'}>)")
                continue
        good[iid] = {k: v[k] for k in v if k in ("verdict", "object", "variant", "tells_seen", "tells_against",
                                                  "stock", "view", "square", "good_for", "why")}
    if good:
        d.setdefault("reviews", []).append({"id": _next_id(d.get("reviews") or [], "r"), "by": by, "date": _now(),
                                            "blind": bool(pk.get("blind")), "packet": pid,
                                            "items": good})
    return len(good), problems


# --------------------------------------------------------------------------------------------------- the sheet
def sheet_html(d, rep):
    import base64  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    def esc(s):
        return htmllib.escape(str(s if s is not None else ""))

    def thumb(e):
        f = _evidence_file(d, e)
        if not f:
            return ""
        try:
            im = Image.open(f).convert("RGB")
        except OSError:
            return ""
        im.thumbnail((420, 300))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
        return f'<img alt="{esc(e["id"])}" src="data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}">'

    ev = {e["id"]: e for e in d.get("evidence") or []}
    ident = d.get("identity") or {}
    ap = rep["approval"]
    state = ("APPROVED" + (" — STALE (changed since)" if ap.get("stale") else "")) if ap["approved"] else \
        "waiting for the owner"
    fact_rows = ""
    for k, f in rep["facts"].items():
        value = "-" if f["value"] is None else f"{f['value']:g}"
        grade = f["grade"] or "-"
        fact_rows += (f"<tr><td>{esc(k)}</td><td class=n>{esc(value)} {esc(f['unit'])}</td>"
                      f"<td><b class='g g{esc(f['grade'] or 'x')}'>{esc(grade)}</b></td><td>{esc(f['why'])}"
                      + "".join(f"<br><small>{esc(n)}</small>" for n in f["notes"]) + "</td></tr>")
    tells = "".join(f"<li>{esc(t.get('text'))} <small>(vs {esc(t.get('vs'))}; "
                    f"{'confirmed' if next((x for x in rep['tells'] if x['id'] == t['id']), {}).get('confirmed') else 'NOT confirmed'})</small></li>"
                    for t in ident.get("tells") or [])
    parts = "".join(f"<tr><td class=n>{esc(p.get('no'))}</td><td>{esc(p.get('name'))}</td><td>{esc(p.get('function'))}"
                    f"</td><td>{esc(p.get('moves'))}</td><td>{'yes' if next((x for x in rep['parts'] if x['id'] == p['id']), {}).get('confirmed') else 'no'}</td></tr>"
                    for p in d.get("parts") or [])
    cards = []
    for r in rep["evidence"]:
        e = ev.get(r["id"], {})
        m = r.get("metrics") or {}
        bits = [f"{r['view'] or '?'}", r["status"], r["scope"] or ""]
        if m.get("px_per_mm"):
            bits.append(f"{m['px_per_mm']} px/mm")
        if m.get("aspect_off") is not None:
            bits.append(f"proportions {m['aspect_off']:+.1%}")
        cards.append(f"<figure class='{esc(r['status'])}'>{thumb(e) if e.get('kind') != 'model' else ''}"
                     f"<figcaption><b>{esc(r['id'])}</b> {esc(' · '.join(bits))}"
                     + (f"<br>good for: {esc(', '.join(r['good_for']))}" if r["good_for"] else "")
                     + "".join(f"<br><span class=flag>{esc(fl)}</span>" for fl in r["flags"])
                     + "".join(f"<br><small>{esc(n)}</small>" for n in r.get("notes") or [])
                     + f"<br><small>{esc(e.get('page') or e.get('url') or e.get('measure') or '')}</small>"
                     + "</figcaption></figure>")
    cov = rep["coverage"]
    cov_rows = "".join(f"<tr><td>view {esc(v)}</td><td>{esc(', '.join(ids) or 'MISSING')}</td></tr>"
                       for v, ids in cov["views"].items()) + \
        "".join(f"<tr><td>close-up {esc(c)}</td><td>{esc(', '.join(ids) or 'MISSING')}</td></tr>"
                for c, ids in cov["closeups"].items())
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(d['object'])} dossier</title><style>
:root{{--bg:#f6f5f1;--fg:#1d1c1a;--mut:#6b675f;--line:#d9d5cc;--card:#fff;--a:#1f7a3a;--b:#3d6fb5;--c:#b07a12;--d:#b3261e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151513;--fg:#ebe8e1;--mut:#a29d92;--line:#36342f;--card:#1f1e1b;--a:#5fc57d;--b:#7fa6e8;--c:#e0ac45;--d:#f07a70;color-scheme:dark}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif;margin:0;padding:24px 16px}}
main{{max-width:1180px;margin:auto}} h1{{margin:0 0 4px}} .mut,small{{color:var(--mut)}}
table{{border-collapse:collapse;width:100%;margin:8px 0 20px}} td,th{{border-bottom:1px solid var(--line);padding:5px 8px;vertical-align:top;text-align:left}}
.n{{font-variant-numeric:tabular-nums;white-space:nowrap}} .g{{padding:1px 7px;border-radius:4px;color:#fff}}
.gA{{background:var(--a)}} .gB{{background:var(--b)}} .gC{{background:var(--c)}} .gD,.gx{{background:var(--d)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}}
figure{{margin:0;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:8px}} figure img{{width:100%;display:block}}
figure.rejected{{opacity:.45}} .flag{{color:var(--d)}} .wrap{{overflow-x:auto}}
.score{{font-size:28px;font-weight:700}}</style></head><body><main>
<h1>{esc(d['object'])}</h1><div class=mut>{esc(d.get('category'))} · maker {esc(ident.get('maker'))} · dossier {esc(d['slug'])} · sheet <b>{esc(sheet_id(rep))}</b> · {esc(state)}</div>
<p><span class=score>{rep['score']:g}/100</span> <span class=mut>(bar {rep['bar']:g})</span></p>
<h2>What is still missing</h2><ul>{''.join(f'<li>{esc(x)}</li>' for x in rep['missing']) or '<li>nothing</li>'}</ul>
{('<h2>Problems</h2><ul>' + ''.join(f'<li class=flag>{esc(x)}</li>' for x in rep['problems']) + '</ul>') if rep['problems'] else ''}
<h2>Tells (this variant, not its siblings)</h2><ul>{tells or '<li>none yet</li>'}</ul>
<h2>Facts</h2><div class=wrap><table><tr><th>fact</th><th>value</th><th>grade</th><th>why</th></tr>{fact_rows}</table></div>
<h2>Coverage</h2><div class=wrap><table>{cov_rows}</table></div>
<h2>Evidence</h2><div class=grid>{''.join(cards)}</div>
<h2>Anatomy</h2><div class=wrap><table><tr><th>no</th><th>part</th><th>does</th><th>moves</th><th>confirmed</th></tr>{parts}</table></div>
<p class=mut>Pictures marked measure-only are measuring references for a private asset: never shipped, never committed.</p>
</main></body></html>"""


# ------------------------------------------------------------------------------------------------------- adding
def _new_source(d, url, kind=None, title=None, by=None):
    for s in d.setdefault("sources", []):
        if s.get("url") == url:
            return s
    s = {"id": _next_id(d["sources"], "s"), "url": url, "kind": kind or "other", "title": title or "",
         "site": site(url) if not is_local(url) else "owner", "added": _today(), "by": by}
    d["sources"].append(s)
    return s


def _resolve_source(d, src, by=None):
    """--source s3 -> its url; a url is registered as a source on the way; "owner" only from the owner (--as owner);
    a file path is no source (nobody else can check it: put the page's url, or the owner's own word)"""
    if str(src or "").strip().lower() == "owner":
        if by != "owner":
            raise ValueError("--source owner is the owner's own measurement or word: only --as owner records it")
        return "owner"
    if src and is_local(src) and not re.fullmatch(r"s\d+", str(src)):
        raise ValueError(f"{src}: a file path is no source anyone can check — give the page's url (or s<n>)")
    if re.fullmatch(r"s\d+", str(src or "")):
        s = next((x for x in d.get("sources") or [] if x["id"] == src), None)
        if not s:
            raise ValueError(f"no source {src} in the dossier")
        if not re.match(r"(?i)^https?://", str(s.get("url"))):
            raise ValueError(f"{src} is no web address ({s.get('url')}): cite the page, or --source owner --as owner")
        return s["url"]
    if not src:
        raise ValueError("needs --source <url | s<n>>: where this comes from")
    return src


def _refuse_blocked(d, url):
    if not is_local(url) and tier_of(url, d) == "blocked":
        raise ValueError(f"{site(url)} is a blocked source (kit/knowledge/sources.json: "
                         f"{(registry().get('blocked') or {}).get(site(url), 'a content farm')})")


def add_evidence(d, argv, by):
    kind = _arg(argv, "--kind", "picture")
    if kind not in ("picture", "drawing", "model"):
        raise ValueError("--kind is picture | drawing | model")
    scope = _arg(argv, "--scope")
    if scope not in SCOPES:
        raise ValueError(f"--scope must be one of {', '.join(SCOPES)} (measure-only: a picture that is not ours to "
                         "ship — a private asset's measuring reference)")
    page, url = _arg(argv, "--page"), _arg(argv, "--url")
    if scope == "owner" and (page or url or kind == "model" or not _arg(argv, "--file")):
        raise ValueError("--scope owner is the owner's OWN photo: --file <path>, no --url / --page")
    if scope == "owner" and (by != "owner" or not _arg(argv, "--note")):
        raise ValueError("--scope owner is recorded for the owner: --as owner --note \"<when / how they gave it>\"")
    for u in (page, url):
        if u and not re.match(r"(?i)^https?://", u):
            raise ValueError(f"{u}: --page / --url is a web address (http / https)")
    if scope != "owner" and not (page or url):
        raise ValueError("where did it come from? --page <the page that shows it> (or --url <the picture>)")
    for u in (page, url):
        if u and tier_of(u, d) in ("blocked", "local"):
            raise ValueError(f"{u}: a {tier_of(u, d)} source (kit/knowledge/sources.json) — not evidence")
    for u in (page, url):
        if u:
            _refuse_blocked(d, u)
    claimed = {}
    if _arg(argv, "--view"):
        if _arg(argv, "--view") not in VIEWS:
            raise ValueError(f"--view must be one of {', '.join(VIEWS)}")
        claimed["view"] = _arg(argv, "--view")
    if _arg(argv, "--parts"):
        claimed["parts"] = [p.strip() for p in _arg(argv, "--parts").split(",") if p.strip()]
    e = {"id": _next_id(d.get("evidence") or [], "e"), "kind": kind, "scope": scope, "licence": _arg(argv, "--licence"),
         "page": page, "url": url, "claimed": claimed, "added": _today(), "by": by}
    if _arg(argv, "--of"):
        e["of"] = _arg(argv, "--of").strip().lower()  # (it shows that part alone: measured against the part's sizes)
    if _arg(argv, "--box"):
        import math  # noqa: PLC0415

        try:
            e["box"] = [float(v) for v in _arg(argv, "--box").split(",")]
        except ValueError:
            e["box"] = []
        if len(e["box"]) != 4 or not all(math.isfinite(v) and v >= 0 for v in e["box"]) or \
                not (e["box"][2] > e["box"][0] and e["box"][3] > e["box"][1]):
            raise ValueError("--box needs x0,y0,x1,y1 in pixels, inside the picture (x1 > x0, y1 > y0)")
    if kind == "model":
        m = _arg(argv, "--measure")
        if not m or not os.path.isfile(m):
            raise ValueError("a model needs --measure refs/<name>.measure.json (kit refs measure / kit library "
                             "inspect gives it)")
        mj = _json(m, {})
        if isinstance(mj, dict) and mj.get("status") == "fail":
            raise ValueError("that measurement FAILED (" + "; ".join(mj.get("problems") or ["no reason given"])
                             + "): fix the run first")
        if isinstance(mj, dict) and mj.get("cut"):
            raise ValueError("a --cut re-measurement is cited by a fact row (fact --from <the model's id> --measure "
                             "<it>), never added as a model of its own")
        e["measure"] = os.path.abspath(m).replace("\\", "/")
        e["measure_sha256"] = _file_sha(m)
        e["sheets"] = _args(argv, "--sheet")
    else:
        folder = os.path.join(EVIDENCE, d["slug"], "pictures")
        os.makedirs(folder, exist_ok=True)
        if _arg(argv, "--file"):
            src = _arg(argv, "--file")
            with open(src, "rb") as fh:
                data = fh.read()
            e["original"] = os.path.basename(src)
        elif url:
            data, _ctype = _fetch(url, 40 * 1024 * 1024)
        else:
            raise ValueError("needs --file <path> or --url <picture url>")
        from PIL import Image  # noqa: PLC0415

        try:
            im = Image.open(io.BytesIO(data))
            im.verify()
        except Exception as ex:  # noqa: BLE001
            raise ValueError(f"not a picture ({type(ex).__name__})") from ex
        if e.get("box"):
            bw, bh = Image.open(io.BytesIO(data)).size
            if e["box"][2] > bw or e["box"][3] > bh:
                raise ValueError(f"--box reaches outside the {bw}x{bh} picture")
        sha = hashlib.sha256(data).hexdigest()
        for old in live_evidence(d):
            if old.get("sha256") == sha:
                raise ValueError(f"already in the dossier as {old['id']}")
        ext = "." + (im.format or "jpg").lower().replace("jpeg", "jpg")
        turn = int(_arg(argv, "--rotate", "0")) % 360
        if turn:
            # (a patent sheet draws its long views on end: stored turned so the object lies as its view expects — the
            #  sha stays the ORIGINAL's, so the same download is still recognised)
            if turn not in (90, 180, 270):
                raise ValueError("--rotate takes 90, 180 or 270 (degrees counter-clockwise)")
            buf = io.BytesIO()
            Image.open(io.BytesIO(data)).rotate(turn, expand=True).save(buf, "PNG")
            data, ext = buf.getvalue(), ".png"
            e["rotated"] = turn
        name = f"{sha[:12]}{ext}"
        with open(os.path.join(folder, name), "wb") as fh:
            fh.write(data)
        e["file_sha256"] = hashlib.sha256(data).hexdigest()  # (the exact bytes reviewed: a changed file is said)
        e["file"] = f"pictures/{name}"
        e["sha256"] = sha
    if page or url:
        _new_source(d, page or url, "owner" if scope == "owner" else None, by=by)
    d.setdefault("evidence", []).append(e)
    return e


def page_images(url):
    """the pictures a page shows (img src / srcset's biggest / data-src / og:image / linked image files)"""
    data, _ = _fetch(url, 20 * 1024 * 1024)
    raw = data.decode("utf-8", errors="replace")
    found = []

    def keep(u, how):
        u = htmllib.unescape(u.strip())
        if not u or u.startswith("data:"):
            return
        full = urllib.parse.urljoin(url, u)
        if full not in [f[0] for f in found]:
            found.append((full, how))

    for m in re.finditer(r'(?is)<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', raw):
        keep(m.group(1), "og:image")
    for m in re.finditer(r'(?is)\ssrcset=["\']([^"\']+)["\']', raw):
        best, best_w = None, -1.0
        for part in m.group(1).split(","):
            bits = part.strip().split()
            if not bits:
                continue
            wv = re.match(r"(\d+(?:\.\d+)?)([wx])", bits[1]) if len(bits) > 1 else None
            size = float(wv.group(1)) * (1 if not wv or wv.group(2) == "w" else 1000) if wv else 0.0
            if size > best_w:
                best, best_w = bits[0], size
        if best:
            keep(best, "srcset")
    for m in re.finditer(r'(?is)<img[^>]+?\s(?:data-src|data-original|src)=["\']([^"\']+)', raw):
        keep(m.group(1), "img")
    for m in re.finditer(r'(?is)href=["\']([^"\']+\.(?:jpe?g|png|webp)(?:\?[^"\']*)?)["\']', raw):
        keep(m.group(1), "link")
    return [f for f in found if not re.search(r"(?i)(favicon|logo|icon|sprite|spinner|pixel|\.svg)", f[0])]


# ----------------------------------------------------------------------------------------------------------- CLI
def _status_line(rep):
    grades = {}
    for f in rep["facts"].values():
        grades[f["grade"] or "-"] = grades.get(f["grade"] or "-", 0) + 1
    ap = rep["approval"]
    return (f"{rep['object']}: {rep['score']:g}/100 (bar {rep['bar']:g}); facts "
            + " ".join(f"{g}{n}" for g, n in sorted(grades.items())) + f"; evidence {len(rep['evidence'])} ("
            + f"{sum(1 for e in rep['evidence'] if e['status'] == 'confirmed')} confirmed); "
            + f"{len(rep['open'])} open; " + ("approved" + (" BUT STALE" if ap["stale"] else "") if ap["approved"]
                                               else "not approved"))


def _next(d, rep):
    s = d["object"]
    if rep["problems"]:
        return f"settle the disagreements first (a primary source, or the owner measures): {rep['problems'][0]}"
    # (research first, review in one batch after: reviewing a half-gathered dossier twice costs two passes)
    waiting = any(e["status"] in ("pending", "disputed") for e in rep["evidence"])
    research = [m for m in rep["missing"] if "(candidates: 0)" in m or m.startswith(("fact ", "anatomy", "tells",
                                                                                    "reference models"))
                or (m.startswith("close-up") and not waiting)]
    if research and rep["open"]:
        return (f"research what is missing ({research[0]}; `lune run kit dossier \"{s}\"` lists where to look), "
                f"then review the {len(rep['open'])} open item(s) in ONE batch: lune run kit dossier review \"{s}\" "
                "--as <you> (a FRESH reviewer: --blind)")
    if research:
        return (f"research what is missing ({research[0]}; `lune run kit dossier \"{s}\"` lists where to look) — "
                "add it with source / fact / part / tell / add, every number with --quote")
    if rep["open"]:
        return (f"review: lune run kit dossier review \"{s}\" --as <you> (then a FRESH reviewer: --blind) — "
                f"{len(rep['open'])} item(s) wait for their keys")
    if rep["missing"]:
        return f"research what is missing ({rep['missing'][0]}; `lune run kit dossier \"{s}\"` lists where to look) " \
               "— add it with source / fact / part / tell / add"
    if not rep["approval"]["approved"] or rep["approval"]["stale"]:
        return (f"show the owner build/dossier/{d['slug']}/sheet.html (lune run kit dossier sheet \"{s}\"); on "
                f"their yes: lune run kit dossier approve \"{s}\" --as owner --note \"<what they said>\"")
    return "none — the data is ready: lune run kit pack <asset> object \"" + s + "\" --length dossier"


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    cmds = ("new", "source", "fact", "part", "tell", "marking", "add", "withdraw", "images", "check", "review", "sheet",
            "approve")
    if not argv:
        return emit("fail", "dossier: needs a command or an object", 'lune run kit dossier new "<object>" --category '
                    "pistol   (kit dossier \"<object>\": its status)")
    cmd = argv[0] if argv[0] in cmds else "status"
    rest = argv[1:] if cmd != "status" else argv
    by = _arg(rest, "--as") or os.environ.get("KIT_AS") or "unknown"
    who = rest[0] if rest else "<object>"
    try:
        if cmd == "images":
            if not rest:
                return emit("fail", "dossier images: needs a page url", "lune run kit dossier images <page url>")
            found = page_images(rest[0])
            for u, how in found[:80]:
                say(f"  [{how}] {u}")
            return emit("pass", f"dossier images: {len(found)} picture(s) on {site(rest[0])}",
                        'add the right ones: lune run kit dossier add "<object>" --url <picture> --page '
                        f"{rest[0]} --scope measure-only --view <view>", images=[u for u, _ in found[:80]])
        if not rest or rest[0].startswith("-"):
            return emit("fail", f"dossier {cmd}: needs the object's name", f'lune run kit dossier {cmd} "<object>" ...')
        name = rest[0]
        if cmd == "new":
            if path_of(name):
                return emit("fail", f"dossier new: '{name}' already has one ({path_of(name)})",
                            f'lune run kit dossier "{name}"')
            catname = _arg(rest, "--category", "generic")
            cat = category(catname)
            d = {"schema": SCHEMA, "object": _norm(name), "slug": slug(name), "category": catname,
                 "private": "--private" in rest, "created": _today(), "updated": _today(),
                 "identity": {"maker": _arg(rest, "--maker"), "maker_domains": _args(rest, "--maker-domain"),
                              "aliases": [_norm(a) for a in _args(rest, "--alias")],
                              "family": [_norm(a) for a in _args(rest, "--family")],
                              "siblings": [_norm(a) for a in _args(rest, "--sibling")], "tells": []},
                 "sources": [], "parts": [], "markings": [], "evidence": [], "reviews": [], "approval": None}
            p = save(d)
            for line in cat.get("research") or []:
                say(f"  - {line}")
            return emit("pass", f"dossier new: {d['object']} ({catname}{', private' if d['private'] else ''}) -> {p}",
                        "research it — the category's list above, in order: the maker's spec page and manual first "
                        f'(lune run kit dossier source "{name}" --url <url> --kind manual --fetch), then facts / '
                        "parts / tells with --quote, pictures and models with add", dossier=p)
        d = load(name)
        if cmd == "status":
            rep = check(d, offline=True)
            for m in rep["missing"][:12]:
                say(f"  missing: {m}")
            for p in rep["problems"][:6]:
                say(f"  PROBLEM: {p}")
            for line in (category(d.get("category", "")).get("research") or []) if rep["missing"] else []:
                say(f"  where to look: {line}")
            return emit("pass", "dossier " + _status_line(rep), _next(d, rep), score=rep["score"])
        if cmd == "source":
            url = _arg(rest, "--url")
            if not url:
                return emit("fail", "dossier source: needs --url", f'lune run kit dossier source "{name}" --url <url> '
                            "--kind manual --fetch")
            kind = _arg(rest, "--kind", "other")
            if not re.match(r"(?i)^https?://", url):
                return emit("fail", "dossier source: --url is a web address (http / https)", "fix --url")
            if kind not in SOURCE_KINDS:
                return emit("fail", f"dossier source: --kind must be one of {', '.join(SOURCE_KINDS)}", "fix --kind")
            _refuse_blocked(d, url)
            s = _new_source(d, url, kind, _arg(rest, "--title"), by)
            said = f"{s['id']} {site(url)} ({tier_of(url, d)})"
            if "--fetch" in rest:
                status, text = source_text(url)
                said += f"; fetched: {status}" + (f", {len(text)} characters" if status == "ok" else "")
            save(d)
            return emit("pass", f"dossier source: {said}", "cite it: --source " + s["id"] + " (facts, parts, tells "
                        "with --quote \"<the words, verbatim>\")", source=s)
        if cmd == "fact":
            part, dim = _arg(rest, "--part", "overall"), _arg(rest, "--dim")
            mm, kg = _arg(rest, "--mm"), _arg(rest, "--kg")
            if not dim or not (mm or kg):
                return emit("fail", "dossier fact: needs --dim and --mm (or --kg)", f'lune run kit dossier fact "{name}" '
                            "--part slide --dim length --mm 186 --source <url> --quote \"<verbatim>\"")
            if _arg(rest, "--from"):
                # (measured on a confirmed reference: our reading, B at most, the number checked against it)
                eid = _arg(rest, "--from")
                value, unit = float(mm or kg), "mm" if mm else "kg"
                row = {"object": d["object"], "part": part, "dim": dim, "value": value, "unit": unit,
                       "source": f"evidence:{eid}", "kind": "derived", "by": by,
                       "note": _arg(rest, "--note", f"measured on {eid}")}
                if _arg(rest, "--measure"):  # (the same model re-measured with a part left out: --cut)
                    mp = _arg(rest, "--measure")
                    mf = mp if os.path.isabs(mp) else os.path.join(os.getcwd(), mp)
                    row["measure"] = mp.replace("\\", "/")
                    row["measure_sha256"] = _file_sha(mf) if os.path.isfile(mf) else None
                    if row["measure_sha256"]:  # (another cut file is another row, never 'already there')
                        row["source"] = f"evidence:{eid}#cut:{row['measure_sha256'][:12]}"
                q, _t, _w = measured_on(d, row)
                if q.startswith("failed"):
                    return emit("fail", f"dossier fact: {part}.{dim} = {value:g} {unit} NOT added — {q}",
                                "cite a model whose own measurement holds the number (kit dossier check lists them)",
                                quote_check=q)
                added = dims.add_rows([row])
                save(d)
                rid = dims.row_id(d["object"], part.strip().lower(), dim, value, row["source"])
                return emit("pass", f"dossier fact: {part}.{dim} = {value:g} {unit} measured on {eid} (dims:{rid}"
                            f"{'' if added else ', already there'}; {q})",
                            f'lune run kit dossier "{name}"   (two independent sites agreeing make it B)',
                            row=rid, quote_check=q)
            src = _resolve_source(d, _arg(rest, "--source"), by)
            _refuse_blocked(d, src)
            if src == "owner" and not _arg(rest, "--note"):
                return emit("fail", "dossier fact: the owner's measurement needs --note \"<how and when it was "
                            "measured>\"", "add --note")
            kind = _arg(rest, "--kind") or ("measured" if src == "owner" else "published")
            if kind not in ("published", "drawing", "measured") or (kind == "measured") != (src == "owner"):
                return emit("fail", "dossier fact: --kind is published | drawing (measured is the owner's own: "
                            "--source owner --as owner)", "fix --kind")
            quote = _arg(rest, "--quote")
            value, unit = float(mm or kg), "mm" if mm else "kg"
            q = check_quote(src, quote, value, unit, fact=(part, dim, part_words(d))) if quote else "unquoted"
            if q.startswith("failed"):
                # (never stored: a number its own source does not say is how bad data gets in)
                return emit("fail", f"dossier fact: {part}.{dim} = {value:g} {unit} NOT added — quote {q}",
                            "copy the source's own words: its label for THIS part and size, then the number with its "
                            "unit (or fix --part / --dim / the number); a table whose label sits in a header row: "
                            "add it without --quote and let two reviewers confirm it (kit dossier review)",
                            quote_check=q)
            row = {"object": d["object"], "part": part, "dim": dim, "value": value, "unit": unit, "source": src,
                   "kind": kind, "note": _arg(rest, "--note", ""), "by": by}
            if quote:
                row["quote"] = quote
            added = dims.add_rows([row])
            if not is_local(src):
                _new_source(d, src, by=by)
            save(d)
            rid = dims.row_id(d["object"], part.strip().lower(), dim, value, src)
            return emit("pass", f"dossier fact: {part}.{dim} = {value:g} {unit} (dims:{rid}"
                        f"{'' if added else ', already there'}; quote {q})",
                        f'lune run kit dossier "{name}"   (grades it)' if q == "verified" else
                        "it counts once two reviewers confirmed it (kit dossier review), or add --quote with the "
                        "source's own words", row=rid, quote_check=q)
        if cmd in ("part", "tell", "marking"):
            src = _resolve_source(d, _arg(rest, "--source"), by)
            _refuse_blocked(d, src)
            quote = _arg(rest, "--quote")
            if cmd == "part":
                if not _arg(rest, "--name"):
                    return emit("fail", "dossier part: needs --name", f'lune run kit dossier part "{name}" --name slide '
                                "--no 1 --source <url> --quote \"1 Slide\"")
                same = [x for x in live(d["parts"]) if _name_key(x.get("name", "")) == _name_key(_arg(rest, "--name"))]
                if same:
                    return emit("fail", f"dossier part: {same[0]['id']} is already {same[0].get('name')}",
                                f"withdraw it first to replace it: kit dossier withdraw \"{name}\" {same[0]['id']} "
                                "--why ..")
                it = {"id": _next_id(d["parts"], "p"), "name": _arg(rest, "--name"), "no": _arg(rest, "--no"),
                      "function": _arg(rest, "--function"), "moves": _arg(rest, "--moves"),
                      "joins": [j.strip() for j in (_arg(rest, "--joins") or "").split(",") if j.strip()],
                      "material": _arg(rest, "--material"), "finish": _arg(rest, "--finish"),
                      "exterior": "--interior" not in rest}
                bucket = d["parts"]
            elif cmd == "tell":
                if not _arg(rest, "--text"):
                    return emit("fail", "dossier tell: needs --text", f'lune run kit dossier tell "{name}" --text '
                                "\"no finger grooves\" --vs \"glock 17 gen4\" --source <url>")
                bucket = d["identity"].setdefault("tells", [])
                it = {"id": _next_id(bucket, "t"), "text": _arg(rest, "--text"), "vs": _arg(rest, "--vs")}
            else:
                if not _arg(rest, "--text"):
                    return emit("fail", "dossier marking: needs --text", f'lune run kit dossier marking "{name}" --text '
                                "\"GLOCK\" --where \"slide, left, rear\" --source <url>")
                bucket = d["markings"]
                it = {"id": _next_id(bucket, "m"), "text": _arg(rest, "--text"), "where": _arg(rest, "--where")}
            it.update({"source": src, "quote": quote, "added": _today(), "by": by})
            it = {k: v for k, v in it.items() if v not in (None, "", [])} | {"id": it["id"]}
            how = {"names": (it.get("name") or it.get("text"), it.get("no"))} if cmd in ("part", "marking") else \
                {"about": it.get("text")}
            q = check_quote(src, quote, **how) if quote else "unquoted"
            if q.startswith("failed"):
                # (never stored: an item its own quote does not prove would sit in the dossier unprovable)
                return emit("fail", f"dossier {cmd}: NOT added — quote {q}", "copy the source's own words about IT, "
                            "verbatim (6+ characters, sharing a word with the name / text)", quote_check=q)
            bucket.append(it)
            if not is_local(src):
                _new_source(d, src, by=by)
            save(d)
            return emit("pass", f"dossier {cmd}: {it['id']} {it.get('name') or it.get('text')} (quote {q})",
                        "confirmed by its quote" if q == "verified" else
                        f"two reviewers must confirm it: lune run kit dossier review \"{name}\" --as <you>",
                        item=it["id"], quote_check=q)
        if cmd == "add":
            e = add_evidence(d, rest, by)
            save(d)
            met = {}
            if e.get("file"):
                met = picture_metrics(_evidence_file(d, e), e.get("box"))
            return emit("pass", f"dossier add: {e['id']} {e['kind']} ({e['scope']})"
                        + (f" {met.get('w')}x{met.get('h')}" if met else "")
                        + ("" if not met or met.get("box") or (e.get("claimed") or {}).get("view") not in VIEW_FRAME
                           else " — no object box found (busy background): --box x0,y0,x1,y1"),
                        f'lune run kit dossier check "{name}"   then review it', evidence=e["id"])
        if cmd == "withdraw":
            if len(rest) > 1 and rest[1].startswith("row:"):
                rid = rest[1][len("row:"):]
                row = next((r for r in _rows_of(d) if r["id"] == rid), None)
                if not _arg(rest, "--why") or row is None or rid in (d.get("withdrawn_rows") or {}):
                    return emit("fail", f"dossier withdraw: {rest[1]} is no live fact row of {name}, or no --why",
                                f'lune run kit dossier check "{name}"   (lists each fact\'s rows)')
                if by not in (row.get("by"), "owner"):
                    return emit("fail", f"dossier withdraw: only who added row:{rid} ({row.get('by')}) or the owner "
                                "withdraws it — a reviewer rejects it instead",
                                f'lune run kit dossier review "{name}" --as {by}')
                d.setdefault("withdrawn_rows", {})[rid] = {"why": _arg(rest, "--why"), "by": by, "date": _now()}
                save(d)
                return emit("pass", f"dossier withdraw: row:{rid} withdrawn ({_arg(rest, '--why')}) — its record stays",
                            f'lune run kit dossier check "{name}"')
            pool = (d.get("evidence") or []) + (d.get("parts") or []) + (d.get("markings") or []) + \
                ((d.get("identity") or {}).get("tells") or [])
            e = next((x for x in pool if len(rest) > 1 and x.get("id") == rest[1] and not x.get("withdrawn")), None)
            if not e or not _arg(rest, "--why"):
                return emit("fail", "dossier withdraw: needs an item id (e / p / t / m) and --why",
                            f'lune run kit dossier withdraw "{name}" e3 --why "added with the wrong view"')
            e["withdrawn"] = {"why": _arg(rest, "--why"), "by": by, "date": _now()}
            save(d)
            return emit("pass", f"dossier withdraw: {e['id']} withdrawn ({e['withdrawn']['why']}) — its record stays",
                        f'lune run kit dossier check "{name}"')
        if cmd == "check":
            if "--refetch" in rest:
                urls = {str(r.get("source")) for r in _rows_of(d)} | {str(i.get("source")) for i in
                                                                      live(d.get("parts")) + live(d.get("markings"))
                                                                      + live((d.get("identity") or {}).get("tells"))}
                for u in sorted(x for x in urls if not is_local(x)):
                    say(f"  refetched {u[:90]}: {source_text(u, refresh=True)[0]}")
            rep = check(d, offline="--offline" in rest)
            for k, f in rep["facts"].items():
                say(f"  {f['grade'] or '-'}  {k:<34} {('%g' % f['value']) if f['value'] is not None else '-':>8} "
                      f"{f['unit']:<3} {f['why']}")
                for n in f["notes"]:
                    say(f"       {n}")
            for e in rep["evidence"]:
                m = e.get("metrics") or {}
                say(f"  {e['id']:<4} {e['kind'] or '':<8} {e['status']:<10} {e['view'] or '?':<12} "
                      + (f"{m.get('px_per_mm')} px/mm " if m.get("px_per_mm") else "")
                      + (f"proportions {m['aspect_off']:+.1%} " if m.get("aspect_off") is not None else "")
                      + "; ".join(e["flags"] + (e.get("notes") or [])))
            for m in rep["missing"]:
                say(f"  missing: {m}")
            return emit("pass", "dossier check " + _status_line(rep), _next(d, rep), score=rep["score"],
                        report=os.path.join(_build_dir(d["slug"]), "check.json").replace("\\", "/"))
        if cmd == "review":
            if "--apply" in rest:
                if not _arg(rest, "--apply") or not os.path.isfile(_arg(rest, "--apply")):
                    return emit("fail", "dossier review --apply: needs the answers file the packet came with",
                                f'lune run kit dossier review "{name}" --apply <answers.json> --as <you>')
                answers = _json(_arg(rest, "--apply"))
                if by == "unknown":
                    return emit("fail", "dossier review: say who you are: --as <model@harness>", "add --as")
                n, problems = apply_answers(d, answers, by)
                for p in problems:
                    say(f"  refused: {p}")
                if n:
                    save(d)
                rep = check(d, offline=True)
                return emit("pass" if n and not problems else "fail",
                            f"dossier review: {n} verdict(s) recorded from {by}"
                            + (f", {len(problems)} refused" if problems else "") + " — " + _status_line(rep),
                            "fix the refused answers and apply again" if problems else _next(d, rep))
            if by == "unknown":
                return emit("fail", "dossier review: say who you are: --as <model@harness>", "add --as")
            body, pk_path, ans_path, contact = packet(d, by, blind="--blind" in rest)
            save(d)
            return emit("pass", f"dossier review: {len(body['items'])} item(s) for {by}"
                        + (" (BLIND: no claims, no earlier verdicts)" if body["blind"] else ""),
                        (f"LOOK at {contact} (and each picture's file when it decides), " if contact else "")
                        + f"read {pk_path}, fill {ans_path}, then: lune run kit dossier review \"{name}\" --apply "
                        f"{ans_path} --as {by}" if body["items"] else "nothing waits for you",
                        packet=pk_path.replace("\\", "/"), answers=ans_path.replace("\\", "/"),
                        contact=(contact or "").replace("\\", "/"))
        if cmd == "sheet":
            rep = check(d, offline="--offline" in rest)
            out = os.path.join(_build_dir(d["slug"]), "sheet.html")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(sheet_html(d, rep))
            return emit("pass", f"dossier sheet: {out} — " + _status_line(rep),
                        "show it to the owner; on their yes: lune run kit dossier approve \"" + name + "\" --as owner "
                        f"--sheet {sheet_id(rep)} --note \"<what they said, when>\"", sheet=out.replace("\\", "/"),
                        sheet_id=sheet_id(rep))
        if cmd == "approve":
            if by != "owner" or not _arg(rest, "--note"):
                return emit("fail", "dossier approve: only the owner approves: --as owner --note \"<what they said, "
                            "and when>\"", "show the owner the sheet first (kit dossier sheet)")
            rep = check(d, offline=True)
            if _arg(rest, "--sheet") != sheet_id(rep):
                return emit("fail", f"dossier approve: give --sheet <the id printed on the sheet the owner saw>; the "
                            f"dossier now is sheet {sheet_id(rep)}", "show the owner the current sheet (kit dossier "
                            "sheet), then approve with its id")
            d["approval"] = {"by": "owner", "date": _now(), "note": _arg(rest, "--note"), "sheet_sha": rep["sheet_sha"],
                             "outcome_sha": outcome_sha(rep),
                             "score": rep["score"], "open": len(rep["open"]), "missing": rep["missing"]}
            save(d)
            return emit("pass", f"dossier approve: {d['object']} approved at {rep['score']:g}/100 (sheet "
                        f"{rep['sheet_sha']}; {len(rep['missing'])} gap(s) accepted)",
                        f'lune run kit pack <asset> object "{d["object"]}" --length dossier')
    except Missing as e:
        return emit("fail", f"dossier: {e}", f'lune run kit dossier new "{who}" --category <pistol | rifle | generic>')
    except (ValueError, OSError, urllib.error.URLError) as e:
        return emit("fail", f"dossier {cmd}: {type(e).__name__}: {str(e)[:220]}", "fix it and run the command again")
    return emit("fail", f"dossier: unknown command {cmd}", "lune run kit dossier")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
