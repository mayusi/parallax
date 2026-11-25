"""expand.py — an IDEA becomes REAL NAMES, and real names become references: "suppressed pistol" -> the real guns of
that kind and their families, each with the sizes Wikidata knows and how many licensed 3D models Sketchfab has.

    python kit/refs/expand.py "<idea or object>" [--also "Walther PPK, AMT Hardballer"] [--n 16] [--fetch 3]

Sources (no account, no key): Wikidata (CC0 data — its search API: the idea's words, then each hit's FAMILY: what it
is based on / a subclass of, and the other models based on the same thing) and Sketchfab's search (downloadable, CC0
/ CC BY / BY-SA models only). The builder adds names of its own with --also (its knowledge of the field).
--fetch N downloads the most detailed licensed model of the N best-covered names (kit/refs/library.py: vetted,
references only).

  -> build/refs/expand/<slug>.json, and one row per name: its sizes (length / height / width mm, mass kg — Wikidata's,
     NOT checked: one entry gave a .45 calibre as "45 mm"; a second source must confirm a number before it is trusted),
     what it is based on, and its Sketchfab count with the best model's uid.
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import library  # noqa: E402  (Sketchfab search, download, licences)

WD = "https://www.wikidata.org/w/api.php"
PACE = 1.0  # seconds between two Sketchfab searches
SIZES = {"P2043": "length_mm", "P2048": "height_mm", "P2049": "width_mm", "P2067": "mass_kg"}
UNIT_MM = {"Q174789": 1.0, "Q11573": 1000.0, "Q174728": 10.0, "Q218593": 25.4, "Q3710": 304.8}  # mm, m, cm, in, ft
UNIT_KG = {"Q11570": 1.0, "Q41803": 0.001, "Q100995": 0.45359237, "Q48013": 0.028349523}       # kg, g, lb, oz
# not an object you could model, by what it IS (instance of): a human, a film, a TV series, an article, a video game,
# a family name, a given name, a disambiguation page
NOT_OBJECT_CLASSES = {"Q5", "Q11424", "Q5398426", "Q13442814", "Q7889", "Q101352", "Q202444", "Q4167410", "Q482994"}
# ... and by its description (the classes above miss some)
NOT_OBJECTS = re.compile(r"film|series|episode|article|album|song|novel|book|video game|character|human|person|band|"
                         r"journal|magazine issue|television|painting|musical|play by|disambiguation|family name|"
                         r"given name|wikimedia|scientific", re.I)


_CACHE = {}
CACHE_FILE = os.path.join(os.environ.get("KIT_BUILD", "build"), "refs", "expand", "_cache.json")


def _cached(key, fn):
    """an answer asked for once is kept (this run, and on disk for the next): the APIs are free and shared"""
    if not _CACHE and os.path.isfile(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding="utf-8") as fh:
                _CACHE.update(json.load(fh))
        except (OSError, ValueError):
            pass
    if key not in _CACHE:
        _CACHE[key] = fn()
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(_CACHE, fh)
    return _CACHE[key]


def _wd(params):
    url = WD + "?" + urllib.parse.urlencode({**params, "format": "json"})
    return _cached(url, lambda: _wd_get(url))


def _wd_get(url):
    def go():
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": library.UA}), timeout=60) as r:
            return json.load(r)

    return library.polite(go)


GENERIC = {"pistol", "pistols", "gun", "guns", "rifle", "rifles", "model", "series", "the", "of", "and", "firearm",
           "weapon", "handgun", "automatic", "semi", "type", "version", "mk", "mod"}


def distinctive(name):
    """the words of a name that pick it out ("Colt Delta Elite" -> colt, delta, elite; "Star S" -> star)"""
    return [t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(t) >= 2 and t not in GENERIC]


def _sketchfab(q, n=24):
    """the licensed models whose TITLE names the gun (Sketchfab's search is loose: "Star S" finds every star)"""
    words = distinctive(q)

    def go():
        time.sleep(PACE)  # one search at a time, spaced: a free API
        return library.search(q, n=n, pages_max=1)

    return [r for r in _cached("sketchfab:" + q, go) if names(r.get("title"), words)]


def names(title, words):
    """a model's title names the gun: at least half its distinctive words, one of them 4+ letters ("Hardballer .45"
    names the AMT Hardballer; "Totally different gun" does not)"""
    t = (title or "").lower()
    hit = [w for w in words if w in t]
    return bool(words) and len(hit) * 2 >= len(words) and any(len(w) >= 4 for w in hit)


def _entities(ids):
    out = {}
    ids = [i for i in dict.fromkeys(ids) if i]
    for k in range(0, len(ids), 50):
        out.update(_wd({"action": "wbgetentities", "ids": "|".join(ids[k:k + 50]), "props": "labels|descriptions|claims",
                        "languages": "en"}).get("entities", {}))
    return out


def _label(e):
    return ((e or {}).get("labels") or {}).get("en", {}).get("value")


def _claims(e, prop):
    out = []
    for c in ((e or {}).get("claims") or {}).get(prop, []):
        v = (c.get("mainsnak") or {}).get("datavalue", {}).get("value")
        if v is not None:
            out.append(v)
    return out


def _ids(e, prop):
    return [v["id"] for v in _claims(e, prop) if isinstance(v, dict) and "id" in v]


def sizes(e):
    """Wikidata's sizes of an item in mm / kg (unconverted units are left out)"""
    out = {}
    for prop, key in SIZES.items():
        for v in _claims(e, prop):
            unit = str(v.get("unit", "")).rsplit("/", 1)[-1]
            k = (UNIT_KG if key == "mass_kg" else UNIT_MM).get(unit)
            if k is not None:
                out[key] = round(float(v["amount"]) * k, 3)
                break
    return out


def is_object(e):
    desc = ((e.get("descriptions") or {}).get("en", {}) or {}).get("value", "")
    return bool(_label(e)) and not NOT_OBJECTS.search(desc) and not (set(_ids(e, "P31")) & NOT_OBJECT_CLASSES)


def is_model(e):
    """a real product (it has a manufacturer) — its family is worth expanding; a generic type ("single shot pistol")
    is not: its family is everything of that type"""
    return bool(_ids(e, "P176"))


def seeds(idea):
    """items for the idea's words: the entity search (names), then the text search (descriptions: "integrally
    suppressed semi-automatic pistol"), objects only"""
    hits = [x["id"] for x in _wd({"action": "wbsearchentities", "search": idea, "language": "en", "limit": 7})
            .get("search", [])]
    hits += [x["title"] for x in _wd({"action": "query", "list": "search", "srsearch": idea, "srlimit": 12,
                                      "srnamespace": 0}).get("query", {}).get("search", [])]
    return list(dict.fromkeys(h for h in hits if re.fullmatch(r"Q\d+", h)))


def family(qid, limit=24):
    """the models based on, or a subclass / instance of, this item"""
    out = []
    for prop in ("P144", "P279", "P31"):
        res = _wd({"action": "query", "list": "search", "srsearch": f"haswbstatement:{prop}={qid}", "srlimit": limit,
                   "srnamespace": 0}).get("query", {}).get("search", [])
        out += [x["title"] for x in res]
    return list(dict.fromkeys(out))


def expand(idea, also=(), n=16):
    """-> candidates [{name, qid, about, based_on, sizes, why, sketchfab: {count, best}}] (seeds, then their families)"""
    found = seeds(idea)
    named = {name: seeds(name)[:1] for name in also}
    for q in named.values():
        found += q
    ents = _entities(found)
    kept = [q for q in found if q in ents and is_object(ents[q])]
    why = {q: "matches the idea" for q in kept}
    for name, q in named.items():
        for x in q:
            if x in why:
                why[x] = f"named by the builder ({name})"
    ents.update(_entities([p for q in kept[:6] for p in (_ids(ents[q], "P144") + _ids(ents[q], "P279"))[:2]
                           if p not in ents]))  # the parents, for "same family as ..."
    fam = []
    for q in kept[:6]:  # each hit's family: the models based on it, and on its parents — real products only
        parents = [p for p in (_ids(ents[q], "P144") + _ids(ents[q], "P279"))[:2] if is_model(ents.get(p) or {})]
        for p in ([q] if is_model(ents[q]) else []) + parents:
            fam += [(f, f"same family as {_label(ents.get(p)) or p}") for f in family(p)]
    ents.update(_entities([f for f, _ in fam if f not in ents]))
    for f, reason in fam:
        e = ents.get(f)
        if f not in why and e and is_object(e):
            why[f] = reason
    parents_all = _entities([p for q in why for p in _ids(ents.get(q), "P144")[:1] if p not in ents])
    ents.update(parents_all)
    out = []
    for q, reason in list(why.items())[: n * 2]:
        e = ents[q]
        base = _ids(e, "P144")[:1]
        out.append({"name": _label(e), "qid": q, "about": ((e.get("descriptions") or {}).get("en", {}) or {}).get("value"),
                    "based_on": _label(ents.get(base[0])) if base else None, "sizes": sizes(e), "why": reason})
    for name in also:  # a builder's name Wikidata does not know is still searched for models
        if not any((c["name"] or "").lower() == name.lower() for c in out):
            out.append({"name": name, "qid": None, "about": None, "based_on": None, "sizes": {}, "why": "named by the builder"})
    for c in out[:n]:
        rows = _sketchfab(c["name"])
        best = max(rows, key=lambda r: r.get("faces") or 0) if rows else None
        c["sketchfab"] = {"count": len(rows), "best": {k: best[k] for k in ("uid", "title", "faces", "licence", "author")}
                          if best else None}
    out.sort(key=lambda c: (c["why"] != "matches the idea" and not c["why"].startswith("named"),
                            -(c.get("sketchfab") or {}).get("count", 0)))
    return out[:n]


def main(argv):
    if not argv or argv[0].startswith("--"):
        return library.emit("fail", "expand: give an idea", 'lune run kit refs expand "suppressed pistol"')
    idea = argv[0]
    also = [a.strip() for a in (library._arg(argv, "--also") or "").split(",") if a.strip()]
    n = int(library._arg(argv, "--n", "16"))
    fetch = int(library._arg(argv, "--fetch", "0"))
    try:
        cands = expand(idea, also, n)
    except Exception as e:  # noqa: BLE001 — the network said no: said plainly
        return library.emit("fail", f"expand: {type(e).__name__}: {str(e)[:160]}", "check the network; retry")
    slug = re.sub(r"[^a-z0-9]+", "_", idea.lower()).strip("_")[:40]
    folder = os.path.join(os.environ.get("KIT_BUILD", "build"), "refs", "expand")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{slug}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"idea": idea, "also": also, "candidates": cands}, fh, indent=1)
    rows = []
    for i, c in enumerate(cands):
        sz = c["sizes"]
        dims = " x ".join(f"{sz[k]:g}" for k in ("length_mm", "height_mm", "width_mm") if k in sz)
        sf = c.get("sketchfab") or {}
        best = sf.get("best") or {}
        rows.append(f"  {i + 1:>2}. {(c['name'] or '?')[:30]:<30} {c['qid'] or '-':<11} "
                    f"{(dims + ' mm') if dims else '':<20} {('mass ' + str(sz['mass_kg']) + ' kg') if 'mass_kg' in sz else '':<14} "
                    f"models {sf.get('count', 0):>2}" + (f" best {best['uid']} ({best['faces']} faces)" if best else "")
                    + f"  — {c['why']}")
    got = []
    for c in [c for c in cands if (c.get("sketchfab") or {}).get("best")][:fetch]:
        uid = c["sketchfab"]["best"]["uid"]
        res = library.main(["get", uid])
        got.append(uid if res == 0 else f"{uid} (failed)")
    return library.emit("pass", f"expand '{idea}': {len(cands)} real name(s), {sum(1 for c in cands if c['sizes'])} with "
                        f"sizes, {sum((c.get('sketchfab') or {}).get('count', 0) for c in cands)} licensed model(s)"
                        + (f"; fetched {', '.join(got)}" if got else ""),
                        "pick the closest real ones: lune run kit library get <uid> -> kit library inspect; photos: "
                        "kit refs find \"<name>\"; a size used for building needs a second source (Wikidata's are "
                        f"unchecked); the list: {path}", rows=rows, expand=path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
