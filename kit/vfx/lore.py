"""lore.py — what the attack IS, in words (owner 2026-10-14: "vision alone isnt working out u need both vision and
detailed text"). The frames say how an effect looks; the articles say its scale, its power, how it moves, what it does
to the world and how its variants differ (a Bankai Getsuga is not a Shikai one). Both go into the build.

    lune run kit vfx refs lore <set> <wiki:Page | page URL>... [--search "<words>" --wiki <fandom>] [--pages 4] [--about "<words>"]
    lune run kit vfx refs brief <set> [--per 6]

lore   every page's article text through the wiki's own API (MediaWiki action=parse; fandom, Wikipedia) or, for any
       other https page, its visible text; --search digs the wiki's own search for more pages on the technique.
       Templates, references and markup stripped, TABLES kept as one sentence per row (the variant tables hold the
       visual facts: "Ichigo's basic Getsuga Tenshō is gold in colour..."); trivia / navigation / other-media sections
       skipped; on a page not about the subject (--about, default the --search words) only sentences naming it. Every
       sentence that carries a VISUAL fact is kept, tagged (colour, shape, scale, power, motion, sound, variant), quoted,
       with its page -> assets/effects/refs_measured/<set>.lore.json (committed: short quoted facts + sources) and the
       whole cleaned text -> assets/effects/refs/<set>/LORE.md (git-ignored, private).
brief  the text facts per tag beside the measured palette and shape (refs measure) on one page ->
       assets/effects/refs_measured/<set>.brief.md. READ it before building; the generator's docstring cites it.
`refs measure` warns while a set has no lore: a measured palette alone has never been enough.
"""

import html
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request

from refkit import MEASURED, REFS, UA, api_and_page, get_json, out

TAGS = {
    "colour": r"\b(black|white|red|crimson|scarlet|blue|cyan|azure|purple|violet|golden|gold|yellow|orange|green|silver|dark|darkness|bright|vivid|pale|glow\w*|shin\w*|colou?r\w*|hue)\b",
    "shape": r"\b(crescent\w*|arc|waves?|beams?|ball|sphere|orb|pillar|column|spiral|vortex|rings?|blades?|slash\w*|spikes?|spiky|flames?|lightning|bolts?|shaped?|outline\w*|edges?|cross|cupped|palms?|single point|point|bulbous|thin\w*|thick\w*|barriers?|shields?|walls?|circles?|seals?|runes?|glyphs?)\b",
    "scale": r"\b(huge|massive|enormous|giant|gigantic|large|larger|vast|immense|small|smaller|tiny|size|scale|wide|width|tall|height|kilomet\w+|meters?|metres?|buildings?|city|mountains?|sky|horizon|entire)\b",
    "power": r"\b(powerful|power|strength|strong\w*|destructive|destroy\w*|devastat\w+|obliterat\w+|overwhelm\w*|force|intens\w+|concentrat\w+|condens\w+|dense|density|pressure|reiatsu|reiryoku|ki|chakra|cursed energy|energy|magnif\w+|amplif\w+|damage)\b",
    "motion": r"\b(fl(y|ies|ying|ew)|fires?|fired|launch\w*|travel\w*|speed\w*|fast|instant\w*|rush\w*|surg\w+|spread\w*|expand\w*|explod\w+|explosion|burst\w*|swirl\w*|spin\w*|charg\w+|gather\w*|releas\w+|unleash\w*|discharg\w+|swing\w*|thrust\w*|projectile|drawn|draws?|pull\w*|push\w*|stream\w*|pierc\w+|shoots?|shot|deploy\w*|succession)\b",
    "sound": r"\b(sound\w*|roar\w*|boom\w*|crack\w*|thunder\w*|rumbl\w+|silen\w+|screech\w*|hum)\b",
    "variant": r"\b(bankai|shikai|final|ultimate|stronger|weaker|version|variant|mode|upgrade\w*|evolv\w+|improv\w+|enhanced|hollowfied|true)\b",
}
VISUAL = ("colour", "shape", "scale")
GAME = re.compile(r"\b(DMG|STA|Ki Blast Supers?|skill tree|level \d+|Xenoverse|Dragon Ball (Online|Heroes|Legends|Fusions|Fighters?)|Budokai|Raging Blast|"
                  r"Tenkaichi|Sparking|Kakarot|Dokkan|card|Ace\b|unlock\w*|purchas\w*|TP Medal|Shop|Super Attack|Ultimate Skill|"
                  r"video games?|team attack|Partner Customization)\b", re.I)
SKIP = r"trivia|reference|navigation|other media|other .*stories|gallery|external|see also|behind the scenes|quotes|appearances|notes|video game|merchandise|usage|history"


def table_rows(m):
    """a wikitable -> one sentence per row ('Variant: description (user).') — the variant tables hold the visual facts"""
    rows = []
    for row in re.split(r"^\|-.*$", m.group(0), flags=re.M):
        cells = []
        for line in row.splitlines():
            line = line.strip()
            if not line.startswith("|") or line.startswith(("{|", "|}")):
                continue
            for cell in re.split(r"\|\|", line[1:]):
                cell = re.sub(r"^[^\[|]*=\s*\"[^\"]*\"[^|\[]*\|", "", cell).strip()  # style="..."| text
                if cell and not re.fullmatch(r"\[\[(File|Image):[^\]]*\]\]", cell, flags=re.I):
                    cells.append(cell)
        if cells:
            rows.append(": ".join(cells[:2]) + (f" ({'; '.join(cells[2:])})" if len(cells) > 2 else "") + ".")
    return "\n" + "\n".join(rows) + "\n"


def clean(w):
    """wikitext -> plain prose (tables become one sentence per row)"""
    w = re.sub(r"<ref[^>/]*/>", "", w)
    w = re.sub(r"<ref[^>]*>.*?</ref>", "", w, flags=re.S)
    w = re.sub(r"<!--.*?-->", "", w, flags=re.S)
    w = w.replace("{{!}}", "|")
    for _ in range(8):  # nested {{templates}}
        w2 = re.sub(r"\{\{[^{}]*\}\}", "", w)
        if w2 == w:
            break
        w = w2
    w = re.sub(r"^\{\|.*?^\|\}", table_rows, w, flags=re.S | re.M)
    w = re.sub(r"<gallery[^>]*>.*?</gallery>", "", w, flags=re.S | re.I)
    w = re.sub(r"\[\[(File|Image|Category):[^\]]*\]\]", "", w, flags=re.I)
    w = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", w)
    w = re.sub(r"\[\[([^\]]*)\]\]", r"\1", w)
    w = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", w)
    w = re.sub(r"'{2,}", "", w)
    w = re.sub(r"<[^>]+>", "", w)
    return html.unescape(w)


def sections(text):
    """'==Title==' blocks -> [(title, body)]"""
    parts = re.split(r"^(={2,5})\s*(.*?)\s*\1\s*$", text, flags=re.M)
    res = [("Intro", parts[0])]
    for i in range(1, len(parts) - 2, 3):
        res.append((parts[i + 1], parts[i + 2]))
    return res


def page_text(spec):
    """(title, url, [(section, body)]) through the MediaWiki API, or a plain page's visible text"""
    apis, title = api_and_page(spec)
    for api in apis:
        try:
            q = {"action": "parse", "page": title, "prop": "wikitext", "redirects": "1", "format": "json"}
            d = get_json(api + "?" + urllib.parse.urlencode(q))
        except Exception:  # noqa: BLE001 — try the other api path
            continue
        if "parse" in d:
            real = d["parse"]["title"]
            base = api.rsplit("/w/api.php", 1)[0] if api.endswith("/w/api.php") else api.rsplit("/api.php", 1)[0]
            return real, base + "/wiki/" + urllib.parse.quote(real.replace(" ", "_")), sections(clean(d["parse"]["wikitext"]["*"]))
    if spec.startswith("https://"):  # any other page: its visible text (scripts/styles dropped), one section
        req = urllib.request.Request(spec, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            if "html" not in r.headers.get("Content-Type", ""):
                return None
            raw = r.read(4_000_000).decode("utf-8", "replace")
        raw = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
        t = re.search(r"<title>(.*?)</title>", raw, re.S | re.I)
        body = html.unescape(re.sub(r"<[^>]+>", " ", raw))
        return (t.group(1).strip() if t else spec), spec, [("Page", body)]
    return None


def density(sent, sec):
    """how much a sentence SHOWS: concrete visual words (colour / shape / scale / motion hits, each counted) per length,
    a bonus for the technique's own Overview / Description / Appearance / Variations; plot recaps score low"""
    hits = sum(len(re.findall(TAGS[t], sent, re.I)) * (2 if t in VISUAL else 1) for t in ("colour", "shape", "scale", "motion"))
    bonus = 2 if re.search(r"intro|overview|description|appearance|variation|abilit", sec, re.I) else 0
    game = 4 if re.search(GAME, sent) else 0  # a video-game skill / card line shows nothing of the attack
    return round(hits * 40 / max(40, len(sent)) + bonus - game, 2)


def fold(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def search(wiki, words, n):
    api = f"https://{wiki}.fandom.com/api.php" if "://" not in wiki else wiki
    q = {"action": "query", "list": "search", "srsearch": words, "srlimit": str(n), "format": "json"}
    d = get_json(api + "?" + urllib.parse.urlencode(q))
    base = api.rsplit("/api.php", 1)[0]
    return [base + "/wiki/" + urllib.parse.quote(h["title"].replace(" ", "_")) for h in d.get("query", {}).get("search", [])]


def cmd_lore(preset, args, opts):
    specs = list(args)
    if "--search" in opts:
        if "--wiki" not in opts:
            return out("fail", "refs lore --search needs --wiki <fandom name or api url>", f"lune run kit vfx refs lore {preset} --search \"<words>\" --wiki bleach")
        specs += [u for u in search(opts["--wiki"], opts["--search"], int(opts.get("--pages", 4))) if u not in specs]
    if not specs:
        return out("fail", "refs lore: name pages (wiki:Page or URL) or --search", f"lune run kit vfx refs lore {preset} bleach:Getsuga_Tensho")
    skip = re.compile(opts.get("--skip-sections", SKIP), re.I)
    # the subject: on a page that is not about the technique itself (a character page), keep only sentences that name it
    phrase = opts.get("--about", opts.get("--search", "")).strip()
    subject = re.compile(r"\b" + r"\s+".join(map(re.escape, fold(phrase).split())) + r"\b", re.I) if phrase else None  # matched on folded text
    about = [w for w in re.findall(r"[a-z0-9]{4,}", fold(opts.get("--about", opts.get("--search", "")))) if w not in ("with", "from", "attack", "technique")]
    facts, sources, full, seen, seen_text = [], [], [], set(), set()
    for spec in specs:
        try:
            got = page_text(spec)
        except Exception as e:  # noqa: BLE001 — report, keep the other pages
            sources.append({"spec": spec, "ok": False, "error": str(e)[:120]})
            continue
        if not got:
            sources.append({"spec": spec, "ok": False})
            continue
        title, url, secs = got
        if url in seen:
            continue
        seen.add(url)
        n0 = len(facts)
        on_topic = not about or any(w in fold(title) for w in about)
        for sec, body in secs:
            if skip.search(sec):
                continue
            body = re.sub(r"\s+", " ", body).strip()
            if len(body) < 40:
                continue
            full.append(f"## {title} — {sec}\n{body}\n")
            for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", body):
                if not 30 <= len(sent) <= 450:
                    continue
                if not on_topic and not any(w in fold(sent) for w in about):
                    continue
                bare = re.sub(subject, " ", fold(sent)) if subject else sent  # "Black Flash" is a name, not a colour fact (accents folded both sides)
                tags = [t for t, rx in TAGS.items() if re.search(rx, bare, re.I)]
                if (len(tags) >= 2 or any(t in VISUAL for t in tags)) and sent not in seen_text:
                    seen_text.add(sent)
                    facts.append({"text": sent, "tags": tags, "section": sec, "page": title, "score": density(bare, sec)})
        sources.append({"spec": spec, "ok": True, "title": title, "url": url, "facts": len(facts) - n0})
    if not facts:
        return out("fail", f"refs lore {preset}: no visual facts in {len(specs)} page(s)", "the technique's own page, its 'Description'; or --search", sources=sources)
    counts = {t: sum(1 for f in facts if t in f["tags"]) for t in TAGS}
    os.makedirs(MEASURED, exist_ok=True)
    dest = os.path.join(MEASURED, f"{preset}.lore.json")
    json.dump({"preset": preset, "date": time.strftime("%Y-%m-%d"), "sources": sources, "tag_counts": counts, "facts": facts,
               "licence": "short quoted facts (fandom / Wikipedia text is CC BY-SA) with their page; measure-only"},
              open(dest, "w", encoding="utf-8", newline="\n"), indent=1, ensure_ascii=False)
    os.makedirs(os.path.join(REFS, preset), exist_ok=True)
    with open(os.path.join(REFS, preset, "LORE.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(full))
    ok = sum(1 for s in sources if s.get("ok"))
    return out("pass", f"refs lore {preset}: {len(facts)} visual facts from {ok}/{len(sources)} page(s) — " + ", ".join(f"{k} {v}" for k, v in counts.items() if v),
               f"READ: lune run kit vfx refs brief {preset} (full text: {REFS}/{preset}/LORE.md) BEFORE building", lore=dest.replace(os.sep, "/"), sources=sources)


def cmd_brief(preset, opts):
    lp, mp = os.path.join(MEASURED, f"{preset}.lore.json"), os.path.join(MEASURED, f"{preset}.json")
    if not os.path.isfile(lp):
        return out("fail", f"refs brief {preset}: no lore — the frames alone have never been enough (owner 2026-10-14)",
                   f"lune run kit vfx refs lore {preset} <wiki:Page>... | --search \"<words>\" --wiki <fandom>")
    lore = json.load(open(lp, encoding="utf-8"))
    per = int(opts.get("--per", 6))
    lines = [f"# {preset} — the brief: what it IS (text) + how it LOOKS (measured)", "",
             "Sources: " + "; ".join(f"{s['title']} <{s['url']}>" for s in lore["sources"] if s.get("ok")), ""]
    used = set()
    floor = float(opts.get("--min-score", 1.0))  # a plot recap or a game-shop line shows nothing: leave it out
    for tag in ("colour", "shape", "scale", "motion", "power", "variant", "sound"):
        fs = sorted((f for f in lore["facts"] if tag in f["tags"] and f["text"] not in used), key=lambda f: -f.get("score", 0))
        fs = [f for f in fs if f.get("score", floor) >= floor][:per]
        if fs:
            lines.append(f"## {tag}")
            for f in fs:
                used.add(f["text"])
                lines.append(f"- \"{f['text']}\" — {f['page']}, {f['section']}")
            lines.append("")
    if os.path.isfile(mp):
        m = json.load(open(mp, encoding="utf-8"))
        lines += ["## measured from the frames (refs measure)",
                  "- luminance bands: " + "; ".join(f"{b['rgb']} {b['share']:.0%}" for b in m["bands"] if b["rgb"]),
                  f"- saturation quartiles {m['saturation']}"]
        if m.get("shape"):
            lines.append(f"- shape {m['shape']}")
    else:
        lines.append("## measured: NONE yet — lune run kit vfx refs wiki/rank/measure " + preset)
    dest = os.path.join(MEASURED, f"{preset}.brief.md")
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return out("pass" if os.path.isfile(mp) else "warn", f"refs brief {preset}: {len(used)} facts" + (" + measurements" if os.path.isfile(mp) else ", NO measurements") + f" -> {dest}",
               "build to BOTH: the scale/power/behaviour the text describes AND the colours/shape the frames measure; cite the brief in the generator",
               brief=dest.replace(os.sep, "/"))
