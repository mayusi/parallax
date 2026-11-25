"""dims.py — REAL DIMENSIONS with their sources, so a build is sized from facts: every row says what was measured,
by whom, and how far to trust it; two sources that disagree are shown side by side.

    python kit/refs/dims.py find "<object> [part]"                 every row whose object + part has all the words
    python kit/refs/dims.py add "<object>" --part <p> --dim <d> --mm <v> --source <url or file> [--kind published]
                                                                    [--note "..."]      (--kg for a mass)
                                                                    [--quote "<the source's own words>"]  (kit
                                                                    dossier finds them in the source: a number a
                                                                    model typed counts only then)
    python kit/refs/dims.py wikidata "<name | Q-id>" [--object "<name>"]       its length / height / width / mass
    python kit/refs/dims.py wikipedia "<page title>" [--object "<name>"]       its infobox: a weapon's length, barrel,
                                                                                width, height, weight; a cartridge's
                                                                                bullet, neck, base, rim, case and
                                                                                overall length (SAAMI, in inches)
    python kit/refs/dims.py fasteners                                       ISO 4762 screws + ISO 273 clearance holes
                                                                                (bd_warehouse's tables)
    python kit/refs/dims.py model <refs/<name>.inspect.json> --object "<name>"  every part's own size (long / mid /
                                                                                short) and its see-through openings,
                                                                                from a dissected reference model

Rows: kit/real_specs/<object>.json [{id, object, part, dim, value, unit (mm | kg), source, kind, trust, added, note}].
Trust: high = published / drawing / measured, medium = wikipedia / wikidata (one Wikidata entry gave a .45 calibre as
"45 mm"), low = model (an author's reading: a game model's checkering was 4x real). A part's review answer may cite a
row: `ref: dims:<id>` (kit/blender/review_refs.py).
"""

import datetime
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import library  # noqa: E402  (UA, polite retries, emit, _arg)

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
STORE = os.path.join(REPO, "kit", "real_specs")
TRUST = {"published": "high", "drawing": "high", "measured": "high", "wikipedia": "medium", "wikidata": "medium",
         "model": "low", "derived": "low"}
TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "inch": 25.4, "inches": 25.4, "ft": 304.8}
TO_KG = {"kg": 1.0, "g": 0.001, "lb": 0.45359237, "lbs": 0.45359237, "oz": 0.028349523}
# an infobox field -> (part, dim)
WEAPON = {"length": ("overall", "length"), "part_length": ("barrel", "length"), "width": ("overall", "width"),
          "height": ("overall", "height"), "weight": ("overall", "mass")}
CARTRIDGE = {"bullet": ("bullet", "diameter"), "neck": ("case", "neck diameter"), "base": ("case", "base diameter"),
             "rim_dia": ("case", "rim diameter"), "case_length": ("case", "length"), "length": ("overall", "length")}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:60] or "object"


def row_id(obj, part, dim, value, source):
    return hashlib.sha1(f"{obj}|{part}|{dim}|{value}|{source}".encode()).hexdigest()[:8]


def load_all():
    rows = []
    if os.path.isdir(STORE):
        for f in sorted(os.listdir(STORE)):
            if f.endswith(".json"):
                with open(os.path.join(STORE, f), encoding="utf-8") as fh:
                    rows += json.load(fh)
    return rows


def ids():
    return {r["id"] for r in load_all()}


def add_rows(new):
    """append rows (each {object, part, dim, value, unit, source, kind, note}); a row already there (same id) is kept
    once. -> the rows added"""
    added = []
    by_obj = {}
    for r in new:
        r = dict(r)
        r["object"] = r["object"].strip().lower()
        r["part"] = (r.get("part") or "overall").strip().lower()
        r["trust"] = TRUST.get(r.get("kind"), "medium")
        r["id"] = row_id(r["object"], r["part"], r["dim"], r["value"], r["source"])
        r.setdefault("added", datetime.date.today().isoformat())
        by_obj.setdefault(slug(r["object"]), []).append(r)
    os.makedirs(STORE, exist_ok=True)
    for name, rows in by_obj.items():
        path = os.path.join(STORE, f"{name}.json")
        have = []
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                have = json.load(fh)
        known = {r["id"]: r for r in have}
        for r in rows:
            if r["id"] not in known:
                have.append(r)
                known[r["id"]] = r
                added.append(r)
            elif r.get("quote") and known[r["id"]].get("quote") != r["quote"]:
                known[r["id"]]["quote"] = r["quote"]  # (the same row, with the source's own words as last given)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(have, fh, indent=1)
    return added


def _has(text, word):
    """a query word is in a row's text: a word with digits (a size: m3, .45, 1911) whole — "m3" is not "m30"; a plain
    word as the start of one of the text's words ("safet" finds "safety")"""
    if re.search(r"\d", word):
        return re.search(r"(?<![a-z0-9.])" + re.escape(word) + r"(?![a-z0-9])", text) is not None
    return re.search(r"(?<![a-z0-9])" + re.escape(word), text) is not None


def find(query):
    """rows whose object + part carry every word of the query, grouped by (object, part, dim); a group whose values
    differ by more than 3% is a CONFLICT"""
    words = re.findall(r"[a-z0-9.]+", query.lower())
    rows = [r for r in load_all() if all(_has(f"{r['object']} {r['part']}", w) for w in words)]
    groups = {}
    for r in rows:
        groups.setdefault((r["object"], r["part"], r["dim"]), []).append(r)
    out = []
    for key, rs in sorted(groups.items()):
        vals = [r["value"] for r in rs]
        spread = (max(vals) - min(vals)) / max(abs(min(vals)), 1e-9) if len(vals) > 1 else 0.0
        out.append({"object": key[0], "part": key[1], "dim": key[2], "rows": rs, "conflict": spread > 0.03})
    return out


# ---------------------------------------------------------------- importers
def _wp_wikitext(title):
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "parse", "page": title, "prop": "wikitext", "section": 0, "format": "json", "redirects": 1})

    def go():
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": library.UA}), timeout=60) as r:
            return json.load(r)

    d = library.polite(go)
    return d["parse"]["wikitext"]["*"], d["parse"].get("title", title)


def infobox(wikitext):
    """-> (the infobox's name, {field: raw value}) — its braces matched, its fields split at the top level only"""
    i = wikitext.lower().find("{{infobox")
    if i < 0:
        return None, {}
    depth, j = 0, i
    while j < len(wikitext):
        if wikitext.startswith("{{", j) or wikitext.startswith("[[", j):
            depth += 1
            j += 2
        elif wikitext.startswith("}}", j) or wikitext.startswith("]]", j):
            depth -= 1
            j += 2
            if depth == 0:
                break
        else:
            j += 1
    body = wikitext[i + 2:j - 2]
    parts, depth, cur = [], 0, ""
    k = 0
    while k < len(body):
        two = body[k:k + 2]
        if two in ("{{", "[["):
            depth += 1
            cur += two
            k += 2
        elif two in ("}}", "]]"):
            depth -= 1
            cur += two
            k += 2
        elif body[k] == "|" and depth == 0:
            parts.append(cur)
            cur = ""
            k += 1
        else:
            cur += body[k]
            k += 1
    parts.append(cur)
    name = parts[0].strip().lower()
    fields = {}
    for p in parts[1:]:
        if "=" in p:
            key, val = p.split("=", 1)
            fields[key.strip().lower()] = val.strip()
    return name, fields


def quantity(raw, default_unit=None):
    """the FIRST quantity in an infobox value -> (number, unit): {{convert|8.25|in|mm}}, {{cvt|1.1|kg}}, "8.25 in",
    a bare number with default_unit (a cartridge infobox's sizes are inches)"""
    m = re.search(r"\{\{\s*(?:convert|cvt)\s*\|\s*([\d.]+)\s*\|\s*([a-z]+)", raw, re.I)
    if m:
        return float(m.group(1)), m.group(2).lower()
    m = re.search(r"([\d]*\.?[\d]+)\s*(mm|cm|m|in|inch|inches|ft|kg|g|lb|lbs|oz)\b", raw, re.I)
    if m:
        return float(m.group(1)), m.group(2).lower()
    m = re.match(r"\s*([\d]*\.?[\d]+)\s*$", re.sub(r"<!--.*?-->|<ref.*?</ref>|<ref[^>]*/>", "", raw, flags=re.S))
    if m and default_unit:
        return float(m.group(1)), default_unit
    return None


def _cartridge_unit(v, dim):
    """a cartridge infobox's BARE number: a US cartridge's are inches (.45 ACP: 1.275), a metric one's millimetres
    (5.56x45mm NATO: 57.4 — read as inches, every size came out x25.4). No cartridge size is under 1 mm or over
    8 in; between, a length is inches (a 2.26 in OAL), a diameter millimetres (a 5.70 mm bullet)"""
    if v < 1.0:
        return "in"
    if v >= 8.0:
        return "mm"
    return "in" if dim == "length" else "mm"


def from_wikipedia(title, obj=None, wikitext=None):
    """-> rows from a page's infobox (a weapon's or a cartridge's)"""
    if wikitext is None:
        wikitext, title = _wp_wikitext(title)
    name, fields = infobox(wikitext)
    if not name:
        return []
    table, unit = (CARTRIDGE, "bare") if "cartridge" in name else (WEAPON, None)
    rows = []
    src = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
    for field, (part, dim) in table.items():
        if field not in fields:
            continue
        q = quantity(fields[field], unit)
        if q is None:
            continue
        v, u = q
        if u == "bare":
            u = _cartridge_unit(v, dim)
        if dim == "mass":
            if u not in TO_KG:
                continue
            rows.append({"part": part, "dim": dim, "value": round(v * TO_KG[u], 4), "unit": "kg"})
        else:
            if u not in TO_MM:
                continue
            rows.append({"part": part, "dim": dim, "value": round(v * TO_MM[u], 3), "unit": "mm"})
    for r in rows:
        r.update({"object": obj or title, "source": src, "kind": "wikipedia", "read_by": "kit",
                  "note": f"infobox '{name}' (first value given)"})
    return rows


def from_wikidata(name_or_q, obj=None):
    import expand  # noqa: PLC0415  (its Wikidata access + unit handling)

    q = name_or_q if re.fullmatch(r"Q\d+", name_or_q) else (expand.seeds(name_or_q) or [None])[0]
    if not q:
        return []
    e = expand._entities([q]).get(q)
    label = expand._label(e) or name_or_q
    rows = []
    for key, v in expand.sizes(e).items():
        dim, unit = key.rsplit("_", 1)
        rows.append({"object": obj or label, "part": "overall", "dim": dim, "value": v, "unit": unit,
                     "source": f"https://www.wikidata.org/wiki/{q}", "kind": "wikidata", "note": "unchecked",
                     "read_by": "kit"})
    return rows


def from_model(path, obj):
    """every part's own size and see-through openings from a dissected reference model (trust: low)"""
    import learn  # noqa: PLC0415  (a part's role from its name)

    with open(path, encoding="utf-8") as fh:
        ins = json.load(fh)
    src = ins.get("source") or path
    rows = []
    for p in ins.get("parts", []):
        part = learn.role(p["name"]) or p["name"]
        label = f"{part} ({p['name'][:40]})" if learn.role(p["name"]) else p["name"][:60]
        for dim, v in zip(("long", "mid", "short"), p.get("own_mm") or []):
            rows.append({"object": obj, "part": label, "dim": dim, "value": v, "unit": "mm", "source": src,
                         "kind": "model", "note": f"dissected {ins['name']} (own axes)"})
        for k, o in enumerate(p.get("see_through") or []):
            rows.append({"object": obj, "part": label, "dim": f"opening {k + 1} diameter", "value": o["d_mm"],
                         "unit": "mm", "source": src, "kind": "model", "note": f"dissected {ins['name']} (seen through)"})
    return rows


def _warehouse_data():
    """bd_warehouse's ISO / ASME tables, in the kit's cad environment (kit tools setup cad)"""
    env = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "envs", "cad")
    for sp in (os.path.join(env, "Lib", "site-packages"), *[os.path.join(env, "lib", d, "site-packages")
                                                           for d in (os.listdir(os.path.join(env, "lib"))
                                                                     if os.path.isdir(os.path.join(env, "lib")) else [])]):
        d = os.path.join(sp, "bd_warehouse", "data")
        if os.path.isdir(d):
            return d
    return None


def from_fasteners():
    """standard METRIC fasteners from bd_warehouse 0.3.0's tables (published standards: trust high): ISO 4762 socket
    head cap screws (head diameter, head height, hex socket, socket depth) and ISO 273 clearance holes"""
    import csv  # noqa: PLC0415

    d = _warehouse_data()
    if d is None:
        raise FileNotFoundError("bd_warehouse is not installed: lune run kit tools setup cad")
    rows = []
    src = "bd_warehouse 0.3.0 data tables (pypi.org/project/bd-warehouse)"
    with open(os.path.join(d, "socket_head_cap_parameters.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            r = {k.strip(): v for k, v in r.items()}
            for key, dim in (("iso4762:dk", "head diameter"), ("iso4762:k", "head height"),
                             ("iso4762:s", "hex socket"), ("iso4762:t", "socket depth")):
                if (r.get(key) or "").strip():
                    rows.append({"object": "iso 4762 socket head cap screw", "part": r["Size"], "dim": dim,
                                 "value": float(r[key]), "unit": "mm", "source": src + " socket_head_cap_parameters.csv",
                                 "kind": "published", "note": "ISO 4762"})
    with open(os.path.join(d, "clearance_hole_sizes.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not r.get("Size", "").startswith("M"):
                continue
            for fit in ("Close", "Normal", "Loose"):
                if (r.get(fit) or "").strip():
                    rows.append({"object": "iso 273 clearance hole", "part": r["Size"], "dim": f"{fit.lower()} diameter",
                                 "value": float(r[fit]), "unit": "mm", "source": src + " clearance_hole_sizes.csv",
                                 "kind": "published", "note": "ISO 273"})
    return rows


def main(argv):
    if not argv or argv[0] not in ("find", "add", "wikidata", "wikipedia", "model", "fasteners"):
        return library.emit("fail", "dims: needs find | add | wikidata | wikipedia | model | fasteners",
                            'lune run kit refs dims find "m1911 barrel"')
    cmd, rest = argv[0], argv[1:]
    if cmd == "fasteners":
        try:
            new = from_fasteners()
        except (OSError, ValueError) as e:
            return library.emit("fail", f"dims fasteners: {e}", "lune run kit tools setup cad")
        added = add_rows(new)
        return library.emit("pass", f"dims fasteners: {len(added)} new row(s) of {len(new)} (ISO 4762 screws, ISO 273 "
                            "clearance holes)", 'lune run kit refs dims find "iso 4762 m3"')
    if not rest:
        return library.emit("fail", f"dims {cmd}: needs a name", 'lune run kit refs dims find "m1911"')
    try:
        if cmd == "find":
            groups = find(rest[0])
            rows = []
            for g in groups:
                vals = ", ".join(f"{r['value']:g} {r['unit']} [{r['kind']}, {r['trust']}, dims:{r['id']}]" for r in g["rows"])
                rows.append(f"  {g['object'][:22]:<22} {g['part'][:30]:<30} {g['dim']:<22} {vals}"
                            + ("  << DISAGREE" if g["conflict"] else ""))
            n_conf = sum(1 for g in groups if g["conflict"])
            return library.emit("pass", f"dims '{rest[0]}': {len(groups)} measure(s), {n_conf} disagreement(s)",
                                "cite a row in a part's answer: ref: dims:<id>; a disagreement: find a third source "
                                "(a drawing, a manual) and add it" if groups else
                                "nothing yet: kit refs dims wikipedia \"<page>\" / wikidata \"<name>\" / add",
                                rows=rows, groups=len(groups))
        obj = library._arg(rest, "--object")
        if cmd == "add":
            dim, src = library._arg(rest, "--dim"), library._arg(rest, "--source")
            mm, kg = library._arg(rest, "--mm"), library._arg(rest, "--kg")
            if not (dim and src and (mm or kg)):
                return library.emit("fail", "dims add: needs --dim, --mm (or --kg) and --source",
                                    'kit refs dims add "colt m1911" --part slide --dim length --mm 190.5 --source <url>')
            new = [{"object": rest[0], "part": library._arg(rest, "--part", "overall"), "dim": dim,
                    "value": float(mm or kg), "unit": "mm" if mm else "kg", "source": src,
                    "kind": library._arg(rest, "--kind", "published"), "note": library._arg(rest, "--note", "")}]
            if new[0]["kind"] in ("wikipedia", "wikidata", "model"):
                return library.emit("fail", f"dims add: --kind {new[0]['kind']} is the kit's own readers' (dims "
                                    "wikipedia / wikidata / model) — a typed row is published or drawing",
                                    "use --kind published --quote \"<the page's words>\"")
            if library._arg(rest, "--quote"):
                new[0]["quote"] = library._arg(rest, "--quote")  # (the source's own words: kit dossier checks them)
        elif cmd == "wikipedia":
            new = from_wikipedia(rest[0], obj)
        elif cmd == "wikidata":
            new = from_wikidata(rest[0], obj)
        else:
            if not obj:
                return library.emit("fail", "dims model: needs --object \"<what the model is>\"",
                                    'kit refs dims model refs/colt1911_asm.inspect.json --object "colt m1911"')
            new = from_model(rest[0], obj)
    except Exception as e:  # noqa: BLE001 — said plainly
        return library.emit("fail", f"dims {cmd}: {type(e).__name__}: {str(e)[:160]}", "check the name / the network")
    added = add_rows(new)
    return library.emit("pass" if new else "fail", f"dims {cmd}: {len(added)} new row(s) of {len(new)} found",
                        f"lune run kit refs dims find \"{(obj or rest[0])[:40]}\"" if new else
                        "nothing found: another page / name, or add it by hand with its source",
                        rows=[f"  {r['part'][:30]:<30} {r['dim']:<22} {r['value']:g} {r['unit']}  dims:{r['id']}" for r in added])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
