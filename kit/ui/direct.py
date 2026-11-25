"""direct.py — the UI CREATIVE DIRECTOR (v8; the owner, 2026-10-24: "take my bullshit prompting and turn it into
something out of this world"). Craft is no longer the weak link; deciding WHAT a screen is, is. The director turns a
rough ask into a small set of genuinely different DIRECTIONS, each one an object of the game's own world with its own
verb and one signature moment, shows them as sketch frames on the game's own world shot, and lets the owner pick one
before any identity is built. The ideas are the author's; this tool is the discipline and the memory around them.

    python kit/ui/direct.py new <name> --ask "<the owner's words, verbatim>" [--game G] [--screens hud,menu:shop]
        a brief scaffold (assets/ui/directions/<name>.json, or the game's): the ask VERBATIM; how each of the owner's
        loaded words has read before (kit/ui/direct_lexicon.json, from real verdicts); the objects of the game's
        world (candidates for "the UI is a ___"); the identities to stay away from; empty direction slots
    python kit/ui/direct.py check <name>     the brief is a design, not a wish (see CHECKS below)
    python kit/ui/direct.py board <name>     a SKETCH frame per direction drawn on the game's own world shot + one
                                             HTML board (palette, real type, a plate in its shape language, the
                                             signature beats, sources) -> build/ui/directions/<name>/
    python kit/ui/direct.py pick <name> <key> "<the owner's words>" --by owner [--identity <id>]
                                             records the owner's pick and drafts assets/ui/identities/<id>.json from
                                             it (tokens, fonts, shape, motion, bans, the sources still to gather)
    python kit/ui/direct.py learn            the UI taste profile (golden / graveyard / orders / lexicon)
                                             -> kit/knowledge/vault/ui/director.md; every new brief carries it
    python kit/ui/direct.py status <name>    where a brief stands (checked? picked?) — used by the identity lock

CHECKS (a direction is refused when it is a wish):
- the ask is kept verbatim, and every loaded word the lexicon knows in it has a reading in the brief;
- 3-5 directions; each has a BIG IDEA that is a metaphor ("the HUD IS a ...") naming an object of the world, free of
  wish-words (sleek, modern, clean, futuristic, epic...), a signature moment of >= 3 timed beats, an `only_here`
  tied to this game, >= 3 sources with >= 1 from outside games, a palette of >= 4 real colours with its reason, a
  type voice from the Roblox catalogue, the Roblox technique per element, a risk, >= 2 "it is NOT" lines;
- the directions DIVERGE: every pair differs on >= 2 of the four axes (space, volume, material, voice), their
  palettes sit apart (CIE Lab), their display faces differ;
- none re-skins an existing identity (its ground AND accent both near one identity's).
Every tool prints one JSON line: status / summary / next_action.
"""
import argparse
import base64
import html
import io
import json
import math
import os
import re
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

LEXICON = os.path.join(HERE, "direct_lexicon.json")
VAULT = os.path.join("kit", "knowledge", "vault", "ui")
AXES = {
    "space": ("screen", "diegetic", "hybrid"),
    "volume": ("quiet", "loud"),
    "material": ("paper", "ink", "metal", "light", "glass", "cloth", "stone", "pixels", "wood", "bone", "plastic",
                 "liquid", "smoke", "signage", "film", "sand", "sound", "shadow", "leather", "water", "fire", "ice",
                 "plant"),
    "voice": ("world", "character", "observer", "enemy", "system"),
}
# words that describe a wish, not a thing: a big idea built on them is not a direction
WISH = ("sleek", "modern", "clean", "futuristic", "minimal", "minimalist", "cyberpunk", "glassmorphism", "high-tech",
        "hi-tech", "cool", "epic", "awesome", "stylish", "premium", "polished", "dynamic", "immersive", "vibrant",
        "eye-catching", "user-friendly", "intuitive", "next-gen", "aaa", "unique", "amazing", "beautiful", "sick")
NON_GAME = ("film", "movie", "anime", "manga", "print", "poster", "signage", "sign", "broadcast", "tv", "news",
            "architecture", "fashion", "ritual", "shrine", "temple", "station", "map", "museum", "packaging", "album",
            "magazine", "comic", "photo", "street", "graffiti", "typography", "calligraphy", "craft", "textile",
            "instrument", "machine", "dashboard", "cockpit", "manual", "ledger", "document", "book", "theatre",
            "kabuki", "painting", "woodblock", "ukiyo-e", "emergency", "transit", "metro", "railway", "talisman",
            "art", "installation", "sculpture", "music", "nature", "science", "medical", "military", "sport", "toy")
FIELDS = ("key", "title", "big_idea", "world_object", "axes", "feeling", "medium", "verb", "signature_moment", "only_here",
          "type_voice", "palette", "shape", "screens", "roblox", "sources", "risk", "not", "frame")
JP_FONT = ("C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/msgothic.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}, ensure_ascii=False))
    return 0 if status == "pass" else 1


def read(p):
    try:
        with open(p, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def out_dir(d, kind="ui"):
    """the build folder of a brief: build/<ui|judge/ui>/directions/<game or project>/<name>"""
    base = ("build", "ui") if kind == "ui" else ("build", "judge", "ui")
    return os.path.join(*base, "directions", d.get("game") or "project", d.get("name") or "brief")


def ui_root(game):
    return os.path.join("games", game, "assets", "ui") if game else os.path.join("assets", "ui")


def brief_path(name, game=None):
    """the brief, wherever it lives (a game's ui folder first when --game is given, then the project's)"""
    cands = [os.path.join(ui_root(game), "directions", f"{name}.json")] if game else []
    cands.append(os.path.join("assets", "ui", "directions", f"{name}.json"))
    if os.path.isdir("games") and not game:
        for g in sorted(os.listdir("games")):
            cands.append(os.path.join("games", g, "assets", "ui", "directions", f"{name}.json"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return cands[0]


def load(name, game=None):
    p = brief_path(name, game)
    with open(p, encoding="utf-8") as fh:
        return p, json.load(fh)


def save(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(d, indent=1, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ reading the ask
def lexicon():
    with open(LEXICON, encoding="utf-8") as fh:
        return json.load(fh)["entries"]


def loaded_words(ask):
    """[(entry id, the words it matched, its proven reading, evidence)] — the owner's words the vault has seen before"""
    hits = []
    for e in lexicon():
        found = []
        for pat in e["match"]:
            flags = 0 if e.get("case") else re.I
            for m in re.finditer(pat if pat.startswith("(?i)") or flags == 0 else rf"\b{pat}\b", ask, flags):
                found.append(m.group(0))
        if found:
            hits.append({"id": e["id"], "words": sorted(set(found)), "reading": e["reading"], "evidence": e["evidence"]})
    return hits


def split_name(n):
    n = re.sub(r"[_\s]*\d+$", "", n)
    n = re.sub(r"([a-z])([A-Z])", r"\1 \2", n).strip().lower()
    n = re.sub(r"(\s[a-z]|_[a-z0-9]+)$", "", n).strip()
    return n.replace("_", " ")  # (GlyphA / Marker_3 are one thing: a glyph, a marker)


# mood words the vault may never have read: each still needs a reading in THIS brief ("magical" means what, here?)
EVALUATIVE = ("magical", "magic", "epic", "cool", "clean", "dark", "cute", "scary", "creepy", "cozy", "gritty", "juicy",
              "premium", "mysterious", "beautiful", "calm", "peaceful", "intense", "chaotic", "fun", "cinematic", "dreamy",
              "eerie", "elegant", "brutal", "wholesome", "vibes", "aesthetic", "insane", "badass", "unique", "ancient",
              "handmade", "crafted", "rustic", "organic", "tactile", "gritty", "lush", "haunting")


def mood_words(ask, known):
    """evaluative words in the ask that no lexicon entry matched -> [(word)]"""
    taken = {w.lower() for k in known for w in k["words"]}
    found = []
    for w in EVALUATIVE:
        if re.search(rf"\b{w}\b", ask, re.I) and not any(w in t for t in taken):
            found.append(w)
    return found


def world_objects(game):
    """the physical things of the game's world (its blueprint's named parts + the brief's pitch): what a UI can BE"""
    if not game:
        return [], ""
    objs = set()
    wdir = os.path.join("games", game, "assets", "worlds")
    if os.path.isdir(wdir):
        for f in os.listdir(wdir):
            if not f.endswith(".json"):
                continue
            try:
                with open(os.path.join(wdir, f), encoding="utf-8") as fh:
                    w = json.load(fh)
            except Exception:  # noqa: BLE001
                continue

            def walk(x):
                if isinstance(x, dict):
                    v = x.get("name")
                    if isinstance(v, str) and len(v) < 40:
                        objs.add(split_name(v))
                    for y in x.values():
                        walk(y)
                elif isinstance(x, list):
                    for y in x:
                        walk(y)
            walk(w)
    brief = read(os.path.join("games", game, "GAME.md"))
    take = []
    for head in ("## Pitch", "## Genre and source"):
        i = brief.find(head)
        if i >= 0:
            body = brief[i + len(head):].strip().split("\n## ", 1)[0].strip()
            take.append(body.split("\n\n", 1)[0])
    objs.discard(game.lower())
    return sorted(o for o in objs if o and o != split_name(game)), " ".join(take)


def identity_files():
    out = []
    roots = [os.path.join("assets", "ui", "identities")]
    if os.path.isdir("games"):
        roots += [os.path.join("games", g, "assets", "ui", "identities") for g in sorted(os.listdir("games"))]
    for r in roots:
        if os.path.isdir(r):
            out += [os.path.join(r, f) for f in sorted(os.listdir(r)) if f.endswith(".json")]
    return out


def identities():
    """[{name, ground, accent, display, about}] of every identity the project has (to stay away from)"""
    out = []
    for p in identity_files():
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:  # noqa: BLE001
            continue
        t, f = d.get("tokens") or {}, d.get("fonts") or {}
        dr = d.get("direction") if isinstance(d.get("direction"), dict) else {}
        out.append({"name": d.get("name") or os.path.basename(p)[:-5], "ground": t.get("bg"), "accent": t.get("accent"),
                    "display": f.get("titleFont") or f.get("font"), "about": str(d.get("about") or "")[:160],
                    "brief": dr.get("brief"), "brief_game": dr.get("game")})
    return out


# ------------------------------------------------------------------ colour
def hex_rgb(h):
    h = str(h or "").strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        return None
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lab(rgb):
    def lin(c):
        c /= 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def de(a, b):
    la, lb = lab(a), lab(b)
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(la, lb)))


def palette_colours(p):
    return [c for c in (hex_rgb(v) for k, v in (p or {}).items() if k != "why") if c]


def palette_gap(p1, p2):
    """mean distance from each colour of one palette to the nearest of the other (both ways)"""
    a, b = palette_colours(p1), palette_colours(p2)
    if not a or not b:
        return 0.0
    one = sum(min(de(x, y) for y in b) for x in a) / len(a)
    two = sum(min(de(y, x) for x in a) for y in b) / len(b)
    return (one + two) / 2


# ------------------------------------------------------------------ new
def template(key):
    return {
        "key": key, "title": "", "big_idea": "the <screen> IS <an object of this world>: ...",
        "world_object": "", "axes": {"space": "", "volume": "", "material": "", "voice": ""},
        "feeling": [], "medium": "", "verb": "how it MOVES (enters, hurts, celebrates)",
        "signature_moment": {"name": "", "beats": [["0.00", ""], ["0.10", ""], ["0.40", ""]]},
        "only_here": "why this could be in no other game",
        "type_voice": {"display": "", "body": "", "lettering": "", "why": ""},
        "palette": {"ground": "", "ink": "", "accent": "", "support": "", "why": "measured / taken from ..."},
        "shape": {"corner": 0, "chamfer": 0, "width": 2, "fill_alpha": 0.9},
        "screens": {}, "roblox": "", "sources": [{"what": "", "kind": "game|anime|film|print|signage|...", "look_for": ""}],
        "process": "the real physical process the animation performs (notch, stitch, quench, fog...)",
        "risk": "", "not": [], "frame": {"ground": "", "grade": {"darken": 0.25}, "elements": []},
    }


def cmd_new(a):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,40}", a.name):
        return emit("fail", f"direct new: '{a.name}' is not a brief name (lowercase, digits, - _)", "pick a short name: neon-hud")
    p = os.path.join(ui_root(a.game), "directions", f"{a.name}.json")
    if os.path.isfile(p):
        return emit("fail", f"direct new: {p} exists", f"edit it, then lune run kit ui direct check {a.name}")
    if a.game and not os.path.isdir(os.path.join("games", a.game)):
        return emit("fail", f"direct new: no game {a.game}", "lune run kit game list")
    words = loaded_words(a.ask)
    objs, pitch = world_objects(a.game)
    ground = ""
    if a.game:
        shots = os.path.join("games", a.game, "build", "worlds", "shots", a.game)
        if os.path.isdir(shots):
            pics = sorted(f for f in os.listdir(shots) if f.lower().endswith((".jpg", ".png")))
            pref = [f for f in pics if f.startswith("eye")] or pics
            if pref:
                ground = os.path.join(shots, pref[0]).replace(chr(92), "/")
    screens = [s for s in (a.screens or "hud").split(",") if s]
    d = {
        "schema": 1, "name": a.name, "game": a.game, "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ask": a.ask, "screens": screens,
        "context": {"pitch": pitch, "world_objects": objs, "world_shots": ground,
                    "stay_away_from": [{k: i[k] for k in ("name", "ground", "accent", "display")} for i in identities()],
                    "taste": os.path.join(VAULT, "director.md").replace(chr(92), "/"),
                    "source_names": [], "source_moves": []},
        "reading": {"fantasy": "", "player": "", "moment_of_use": "", "assumptions": [],
                    "words": [{"id": w["id"], "words": w["words"], "proven": w["reading"], "here": ""} for w in words]
                    + [{"id": f"mood:{m}", "words": [m], "proven": "(no verdict has read this word yet: say what it means for THIS piece, then let the owner's verdict confirm it)", "here": ""}
                       for m in mood_words(a.ask, words)]},
        "directions": [template(k) for k in "ABCD"],
        "recommendation": {"key": "", "why": ""},
        "pick": None,
    }
    if ground:
        for dd in d["directions"]:
            dd["frame"]["ground"] = ground
    save(p, d)
    lead = f"{len(words)} loaded word(s) the vault has read before ({', '.join(w['id'] for w in words)})" if words else "no loaded word the vault knows"
    return emit("pass", f"direct new {a.name}: brief -> {p.replace(chr(92), '/')}; {lead}; {len(objs)} world object(s)",
                f"write the reading + 3-5 directions (read {os.path.join(VAULT, 'director.md')} first), then lune run kit ui direct check {a.name}",
                brief=p.replace(chr(92), "/"), words=[w["id"] for w in words], world_objects=objs[:30])


# ------------------------------------------------------------------ check
def words_of(s):
    return set(re.findall(r"[a-z][a-z'-]+", str(s).lower()))


STOP = {"the", "and", "with", "from", "that", "this", "into", "over", "under", "your", "their", "its", "of", "a", "an",
        "is", "are", "for", "own", "each", "every", "what", "when", "where", "which", "who"}
TEMPLATE_ONLY_HERE = "why this could be in no other game"
PLACE_WORDS = {"screen", "across", "bottom", "left", "right", "side", "corner", "middle", "centre", "center", "edge", "edges",
               "beside", "behind", "front", "above", "below", "along"}


def content_words(s):
    """the meaning words of a text, plural-insensitive ('candles' and 'candle' are one word)"""
    out = set()
    for w in words_of(s):
        w = w.strip("'")
        if len(w) > 3 and w not in STOP:
            out.add(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def outside_games(src):
    """a source from outside games: its kind names a non-game field (whole words: 'design' is not 'sign'), and is not
    the template's placeholder"""
    kind = str(src.get("kind") or "").lower()
    if not kind or "|" in kind or kind.strip() == "game":
        return False
    return bool(set(re.findall(r"[a-z][a-z-]+", kind)) & set(NON_GAME))


def game_words(game):
    """the nouns of a game's world: its blueprint's named things + its pitch"""
    objs, pitch = world_objects(game)
    boiler = {"built", "kit's", "lane", "manner", "showcase", "first", "second", "third", "fourth", "fifth", "world"}
    return content_words(" ".join(objs) + " " + pitch) - boiler


def swappable(d, x):
    """the other game this direction would fit as well as its own (None when it belongs here)"""
    if not os.path.isdir("games") or not d.get("game"):
        return None
    idea = content_words(" ".join(str(x.get(k) or "") for k in ("big_idea", "world_object", "only_here")))
    own = len(idea & game_words(d["game"]))
    for g in sorted(os.listdir("games")):
        if g == d["game"] or not os.path.isfile(os.path.join("games", g, "GAME.md")):
            continue
        other = len(idea & game_words(g))
        if other >= 2 and other >= own:
            return g
    return None


def roblox_fonts():
    try:
        with open(os.path.join(HERE, "fonts.json"), encoding="utf-8") as fh:
            return set(json.load(fh)["fonts"])
    except Exception:  # noqa: BLE001
        return set()


def check_brief(d):
    """-> (errors, warnings) for a whole brief"""
    errs, warns = [], []
    if not str(d.get("ask") or "").strip():
        errs.append("the ask is empty: keep the owner's words VERBATIM")
    r = d.get("reading") or {}
    for k in ("fantasy", "player", "moment_of_use"):
        if len(str(r.get(k) or "").split()) < 4:
            errs.append(f"reading.{k}: say it in a sentence (what is the player's fantasy / who / when do they look)")
    for w in r.get("words") or []:
        if len(str(w.get("here") or "").split()) < 5:
            errs.append(f"reading: the owner's word(s) {w.get('words')} have a proven reading ({w.get('id')}); say how THIS piece reads them")
    known = {w.get("id") for w in r.get("words") or []}
    for m in mood_words(str(d.get("ask") or ""), loaded_words(str(d.get("ask") or ""))):
        if f"mood:{m}" not in known:
            errs.append(f"reading: the ask says '{m}' - no verdict has read that word yet; add {{\"id\": \"mood:{m}\", \"here\": \"what it means for this piece\"}}")
    # borrowed names (the blind critique, 2026-10-24: "黒閃 is literally JJK's Black Flash ... the serial numbers left
    # on"): 'like <a source>' takes its GRAMMAR, never the names it owns (characters, techniques, places it coined)
    names = [str(n) for n in (d.get("context") or {}).get("source_names") or [] if str(n).strip()]
    if any(w["id"] == "like-a-game" for w in loaded_words(str(d.get("ask") or ""))) and not names:
        errs.append("context.source_names: the ask names a source - list the names it OWNS (characters, techniques, coined words) so none ends up on screen")
    for x in [x for x in d.get("directions") or [] if str(x.get("title") or "").strip()]:
        shown = " ".join([str(x.get("big_idea") or ""), str(x.get("title") or "")] +
                         [str(el.get("text") or "") for el in (x.get("frame") or {}).get("elements") or [] if isinstance(el, dict)])
        for n in names:
            # a name is a proper noun: its own case or SHOUTED in caps ("your journey" is a word, "Journey" the game)
            hit = (n in shown) if not n.isascii() else any(re.search(rf"(?<!\w){re.escape(v)}(?!\w)", shown) for v in {n, n.upper()})
            if hit:
                errs.append(f"{x.get('key')}: shows the source's own name '{n}' - take its grammar, give the moment this game's own name")
    # borrowed MOVES (the SampleDunes critique, 2026-10-24: the 'cymatic call' was "Journey's shout ring" - no Journey
    # name on screen, but its signature move): a brief that names the source lists its signature moves too
    moves = [str(m) for m in (d.get("context") or {}).get("source_moves") or [] if str(m).strip()]
    if names and not moves:
        errs.append("context.source_moves: you listed the source's names - list its signature MOVES too (its call, its meter, its pickups) so no direction repeats one")
    for x in [x for x in d.get("directions") or [] if str(x.get("title") or "").strip()]:
        what = content_words(" ".join([str(x.get("big_idea") or ""), str(x.get("verb") or "")] +
                                      [str(b[1]) for b in (x.get("signature_moment") or {}).get("beats") or [] if len(b) > 1]))
        for m in moves:
            shared = (content_words(m) - PLACE_WORDS) & what  # ("across the top of the screen" is where, not what)
            if len(shared) >= 2:
                warns.append(f"{x.get('key')}: repeats the source's own move '{m}' ({', '.join(sorted(shared))}) - keep the input if you must, make the RESULT ours")
    for w in loaded_words(str(d.get("ask") or "")):
        if w["id"] not in known:
            errs.append(f"reading: the ask says {w['words']} but the brief has no reading for '{w['id']}'")
    dirs = [x for x in d.get("directions") or [] if str(x.get("title") or "").strip()]
    if not 3 <= len(dirs) <= 5:
        errs.append(f"{len(dirs)} direction(s): show the owner 3-5 genuinely different ones")
    fonts = roblox_fonts()
    objs = set(" ".join((d.get("context") or {}).get("world_objects") or []).split())
    ctx_words = words_of((d.get("context") or {}).get("pitch")) | objs | words_of(d.get("ask"))
    for x in dirs:
        k = x.get("key") or "?"
        big = str(x.get("big_idea") or "")
        # a metaphor: "is / becomes" AND the world object it names ("This is a HUD." is not one)
        named = content_words(x.get("world_object")) & content_words(big)
        if not re.search(r"\b(is|are|becomes|become|IS)\b", big) or "<" in big or not named:
            errs.append(f"{k}: the big idea is not a metaphor - write 'the <screen> IS <the world object>' (naming its world_object)")
        wish = sorted(words_of(big) & set(WISH))
        if wish:
            errs.append(f"{k}: {', '.join(wish)} in the big idea is a wish, not a direction - name the THING it is")
        if len(str(x.get("world_object") or "").split()) < 1:
            errs.append(f"{k}: world_object - which object of the game's world (or its source) the UI is")
        ax = x.get("axes") or {}
        for a_, allowed in AXES.items():
            if ax.get(a_) not in allowed:
                errs.append(f"{k}: axes.{a_} must be one of {'/'.join(allowed)}")
        beats = (x.get("signature_moment") or {}).get("beats") or []
        timed = [b for b in beats if isinstance(b, list) and len(b) == 2 and re.fullmatch(r"\d+(\.\d+)?", str(b[0])) and len(str(b[1]).split()) >= 3]
        if len(timed) < 3 or not str((x.get("signature_moment") or {}).get("name") or "").strip():
            errs.append(f"{k}: the signature moment needs a name and >= 3 timed beats (seconds, what happens)")
        only = str(x.get("only_here") or "")
        if len(only.split()) < 6 or only.strip() == TEMPLATE_ONLY_HERE:
            errs.append(f"{k}: only_here - why this could be in no other game (tie it to this world)")
        elif ctx_words and not (words_of(only) & ctx_words) and not (words_of(only) & words_of(" ".join(str(s.get("what")) for s in x.get("sources") or []))):
            warns.append(f"{k}: only_here names nothing of this game's world or sources")
        tv = x.get("type_voice") or {}
        for role in ("display", "body"):
            if tv.get(role) not in fonts:
                errs.append(f"{k}: type_voice.{role} '{tv.get(role)}' is not a Roblox font (kit/ui/fonts.json)")
        pal = x.get("palette") or {}
        if len(palette_colours(pal)) < 4 or len(str(pal.get("why") or "").split()) < 4:
            errs.append(f"{k}: palette - >= 4 real colours (#rrggbb) and WHY (where they come from)")
        src = [s for s in x.get("sources") or [] if len(str(s.get("what") or "").split()) >= 2]
        if len(src) < 3:
            errs.append(f"{k}: >= 3 sources (real things to gather stills of)")
        elif not any(outside_games(s) for s in src):
            errs.append(f"{k}: no source from outside games - pull one from print, signage, broadcast, ritual, architecture, film...")
        proc = str(x.get("process") or "")
        if len(proc.split()) < 4 or proc.startswith("the real physical process"):
            warns.append(f"{k}: no 'process' - the owner called the board whose animations ARE a real physical process (a stick notched and split, "
                         "a deed stitched, breath on glass) 'all amazing original ideas' (2026-10-25): name the process this moment performs")
        for f_ in ("medium", "verb", "roblox", "risk"):
            if len(str(x.get(f_) or "").split()) < 3:
                errs.append(f"{k}: {f_} is empty")
        if len([n for n in x.get("not") or [] if str(n).strip()]) < 2:
            errs.append(f"{k}: >= 2 'it is NOT' lines (what a lazy version would do)")
        for s in d.get("screens") or []:
            if len(str((x.get("screens") or {}).get(s) or "").split()) < 4:
                errs.append(f"{k}: what does the {s} become in this direction?")
        if not (x.get("frame") or {}).get("elements"):
            warns.append(f"{k}: no sketch frame elements - the board will show only the ground")
        elif not any(isinstance(el, dict) and any(t in el for t in ("t", "in", "wipe", "pulse")) for el in x["frame"]["elements"]):
            warns.append(f"{k}: the signature moment is a still - time its elements (t / in / wipe) and render it: kit ui direct reel")
    # the directions DIVERGE
    for i in range(len(dirs)):
        for j in range(i + 1, len(dirs)):
            a, b = dirs[i], dirs[j]
            same = [ax for ax in AXES if (a.get("axes") or {}).get(ax) == (b.get("axes") or {}).get(ax)]
            if len(same) > 2:
                errs.append(f"{a['key']} and {b['key']} share {', '.join(same)}: the same idea twice - move one on >= 2 axes")
            gap = palette_gap(a.get("palette"), b.get("palette"))
            if gap < 18:
                errs.append(f"{a['key']} and {b['key']} palettes are {gap:.0f} apart (Lab): too close to be two directions")
            if (a.get("type_voice") or {}).get("display") == (b.get("type_voice") or {}).get("display"):
                warns.append(f"{a['key']} and {b['key']} share the display face {(a.get('type_voice') or {}).get('display')}")
    # the SWAP test (a branding check): could this direction move to another of the owner's games unchanged? its
    # idea's nouns must belong to THIS world more than to any other game's
    for x in dirs:
        sw = swappable(d, x)
        if sw:
            warns.append(f"{x.get('key')}: it could move to {sw} unchanged (its idea's nouns are as much that world's) - tie it to this world's own things")
    # none re-skins an existing identity
    for x in dirs:
        pal = x.get("palette") or {}
        g, acc = hex_rgb(pal.get("ground")), hex_rgb(pal.get("accent"))
        if not g or not acc:
            continue
        for ident in identities():
            if ident.get("brief") == d.get("name") and ident.get("brief_game") == d.get("game"):
                continue  # (this brief's own drafted identity, after a pick, is not a re-skin of itself)
            ig, ia = hex_rgb(ident.get("ground")), hex_rgb(ident.get("accent"))
            if ig and ia and de(g, ig) < 12 and de(acc, ia) < 15:
                errs.append(f"{x['key']}: ground + accent sit on identity '{ident['name']}' ({ident['ground']} / {ident['accent']}): a re-skin, not a new look")
    rec = (d.get("recommendation") or {})
    if rec.get("key") not in {x.get("key") for x in dirs} or len(str(rec.get("why") or "").split()) < 6:
        errs.append("recommendation: which one you would build and why (the owner still picks)")
    return errs, warns


def cmd_check(a):
    try:
        p, d = load(a.name, a.game)
    except (OSError, json.JSONDecodeError) as e:
        return emit("fail", f"direct check: {e}", f"lune run kit ui direct new {a.name} --ask \"...\"")
    errs, warns = check_brief(d)
    d["checked"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "errors": len(errs), "warnings": len(warns)}
    save(p, d)
    if errs:
        return emit("fail", f"direct check {a.name}: {len(errs)} problem(s) - {errs[0]}", errs[0], errors=errs, warnings=warns)
    return emit("pass", f"direct check {a.name}: {len(d['directions'])} direction(s) are designs, not wishes"
                + (f" ({len(warns)} warning(s))" if warns else ""), f"lune run kit ui direct board {a.name}", warnings=warns)


# ------------------------------------------------------------------ board: sketch frames
W, H = 1920, 1080


def colour(pal, v, default="#ffffff"):
    if isinstance(v, str) and v.startswith("#"):
        return hex_rgb(v) or hex_rgb(default)
    return hex_rgb((pal or {}).get(v)) or hex_rgb(default)


def face(tv, which, size):
    import preview as P
    if which in ("jp", "kanji"):
        for f in JP_FONT:
            if os.path.isfile(f):
                return ImageFont.truetype(f, size)
    name = (tv or {}).get(which) or which
    return P.font(name, size)


_CMAPS = {}


def covers(font, text):
    """does this face have every glyph of the text? (a missing glyph draws an empty box: the sketch falls back)"""
    path = getattr(font, "path", None)
    if not path:
        return True
    if path not in _CMAPS:
        try:
            from fontTools.ttLib import TTFont
            tt = TTFont(path, fontNumber=0, lazy=True)
            _CMAPS[path] = set(tt.getBestCmap() or {})
        except Exception:  # noqa: BLE001
            _CMAPS[path] = None
    cmap = _CMAPS[path]
    return cmap is None or all(ord(ch) in cmap for ch in text if not ch.isspace())


def fallback(font, text, size):
    if covers(font, text):
        return font
    for f in JP_FONT:
        if os.path.isfile(f):
            return ImageFont.truetype(f, size)
    return font


def cover(im, w, h):
    k = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * k)), max(h, round(im.height * k))), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def chamfer_poly(box, ch, skew=0):
    x, y, w, h = box
    pts = [(x + ch, y), (x + w, y), (x + w, y + h - ch), (x + w - ch, y + h), (x, y + h), (x, y + ch)] if ch else \
        [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    if skew:
        pts = [(px + skew * (1 - (py - y) / max(h, 1)), py) for px, py in pts]
    return pts


def ground_image(direction, w=W, h=H):
    """the direction's world shot, graded (the frame's `grade`), as RGB at w x h"""
    fr = direction.get("frame") or {}
    pal = direction.get("palette") or {}
    base = None
    if fr.get("ground") and os.path.isfile(fr["ground"]):
        base = cover(Image.open(fr["ground"]).convert("RGB"), w, h)
    if base is None:
        base = Image.new("RGB", (w, h), colour(pal, "ground", "#202020"))
    g = fr.get("grade") or {}
    if g.get("desat"):
        base = ImageEnhance.Color(base).enhance(1 - float(g["desat"]))
    if g.get("tint"):
        base = Image.blend(base, Image.new("RGB", (w, h), colour(pal, g["tint"])), float(g.get("amount", 0.25)))
    if g.get("darken"):
        base = Image.blend(base, Image.new("RGB", (w, h), (0, 0, 0)), float(g["darken"]))
    if g.get("blur"):
        base = base.filter(ImageFilter.GaussianBlur(float(g["blur"]) * w / W))
    return base


def draw_frame(direction, out_png):
    fr = direction.get("frame") or {}
    pal = direction.get("palette") or {}
    tv = direction.get("type_voice") or {}
    base = ground_image(direction)
    im = base.convert("RGBA")
    skipped = []
    for n_, el in enumerate(fr.get("elements") or []):
        try:
            layer = draw_element(el, pal, tv)
        except Exception as e:  # noqa: BLE001  (one broken element never loses the whole frame)
            skipped.append(f"{direction.get('key')} element {n_ + 1} ({el.get('kind') if isinstance(el, dict) else el}): {type(e).__name__} {e}")
            continue
        im.alpha_composite(layer)
    return finish_frame(direction, im, out_png), skipped


def finish_frame(direction, im, out_png):
    d = ImageDraw.Draw(im)
    tag = f"SKETCH {direction.get('key')} - a direction test frame, not the art"
    d.text((W - 24, H - 20), tag, font=face({}, "RobotoMono", 22), fill=(255, 255, 255, 170), anchor="rd")
    im = im.convert("RGB").resize((1280, 720), Image.LANCZOS)
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    im.save(out_png, quality=88)
    return out_png


def draw_element(el, pal, tv):
    """one sketch element on its own layer"""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    k = el.get("kind")
    a = int(255 * float(el.get("alpha", 1)))
    if k in ("rect", "poly"):
        pts = [tuple(p) for p in el["points"]] if k == "poly" else chamfer_poly(el["box"], el.get("chamfer", 0), el.get("skew", 0))
        if el.get("fill"):
            d.polygon(pts, fill=colour(pal, el["fill"]) + (a,))
        if el.get("line"):
            d.line(pts + [pts[0]], fill=colour(pal, el["line"]) + (255,), width=int(el.get("width", 3)))
    elif k == "bar":
        x, y, w, h = el["box"]
        n = int(el.get("segments", 0))
        gap = el.get("gap", 4)
        v = float(el.get("value", 0.7))
        sk = el.get("skew", 0)
        if el.get("track"):
            d.polygon(chamfer_poly(el["box"], 0, sk), fill=colour(pal, el["track"]) + (int(255 * el.get("track_alpha", 0.6)),))
        if n:
            cw = (w - gap * (n - 1)) / n
            for i in range(n):
                if (i + 0.5) / n <= v:
                    d.polygon(chamfer_poly((x + i * (cw + gap), y, cw, h), 0, sk), fill=colour(pal, el.get("fill", "accent")) + (a,))
        else:
            d.polygon(chamfer_poly((x, y, w * v, h), 0, sk), fill=colour(pal, el.get("fill", "accent")) + (a,))
        if el.get("ghost"):
            gx = x + w * v
            d.polygon(chamfer_poly((gx, y, w * float(el["ghost"]), h), 0, sk), fill=colour(pal, el.get("ghost_color", "ink")) + (150,))
    elif k == "chladni":
        # a REAL Chladni figure (sand settles on the nodal lines of a vibrating plate): cos(n pi x)cos(m pi y) -
        # cos(m pi x)cos(n pi y) = 0, `skew` bends it toward a direction, laid on the ground (ry < r)
        cx, cy = el["center"]
        r, ry = el["r"], el.get("ry", el["r"])
        n_, m_ = el.get("n", 3), el.get("m", 5)
        sk = el.get("skew", 0.0)
        c = colour(pal, el.get("color", "ink")) + (a,)
        dot = el.get("dot", 2.2)
        steps = max(2, int(el.get("density", 220)))
        r = max(1e-6, r)
        for iy in range(steps):
            y = -1 + 2 * iy / (steps - 1)
            for ix in range(steps):
                x = -1 + 2 * ix / (steps - 1)
                if x * x + y * y > 1:
                    continue
                f = math.cos(n_ * math.pi * x) * math.cos(m_ * math.pi * y) - math.cos(m_ * math.pi * x) * math.cos(n_ * math.pi * y)
                f += sk * math.sin(math.pi * x) * (1 - y * y)
                if abs(f) < el.get("eps", 0.05):
                    px, py = cx + x * r, cy + y * ry
                    d.ellipse([px - dot, py - dot * ry / r * 1.6, px + dot, py + dot * ry / r * 1.6], fill=c)
    elif k == "branch":
        # a branching, tapering form (a fulgurite's tube, a crack in stone, a root, a bolt): a seeded random walk that
        # splits; `dir` in degrees (0 = right, 90 = down), `len` the trunk, `depth` the splits
        import random as _r
        rng = _r.Random(el.get("seed", 1))
        c = colour(pal, el.get("color", "accent")) + (a,)

        def grow(x, y, ang, length, width, depth):
            segs = max(3, int(length / 18))
            for _ in range(segs):
                ang += rng.uniform(-el.get("wander", 22), el.get("wander", 22))
                nx = x + math.cos(math.radians(ang)) * length / segs
                ny = y + math.sin(math.radians(ang)) * length / segs
                d.line([(x, y), (nx, ny)], fill=c, width=max(1, int(width)))
                x, y = nx, ny
                width *= 0.93
                if depth > 0 and rng.random() < el.get("split", 0.18):
                    grow(x, y, ang + rng.choice((-1, 1)) * rng.uniform(25, 55), length * 0.55, width * 0.7, depth - 1)
        grow(el["at"][0], el["at"][1], el.get("dir", 0), el.get("len", 400), el.get("width", 8), el.get("depth", 3))
    elif k == "ellipse":
        cx, cy = el["center"]
        r, ry = el["r"], el.get("ry", el["r"])
        d.ellipse([cx - r, cy - ry, cx + r, cy + ry], fill=colour(pal, el["fill"]) + (a,) if el.get("fill") else None,
                  outline=colour(pal, el["line"]) + (255,) if el.get("line") else None, width=int(el.get("width", 2)))
    elif k == "figure":
        # a fighter's silhouette standing on (x, y): scale and placement for a diegetic idea, nothing more
        x, y = el["at"]
        h = el.get("h", 300)
        c = colour(pal, el.get("color", "#050507")) + (a,)
        hr = h * 0.085
        d.ellipse([x - hr, y - h, x + hr, y - h + 2 * hr], fill=c)
        d.polygon([(x - h * 0.13, y - h + 2.2 * hr), (x + h * 0.13, y - h + 2.2 * hr), (x + h * 0.1, y - h * 0.48),
                   (x - h * 0.1, y - h * 0.48)], fill=c)
        d.polygon([(x - h * 0.1, y - h * 0.5), (x - h * 0.02, y - h * 0.5), (x - h * 0.1, y), (x - h * 0.19, y)], fill=c)
        d.polygon([(x + h * 0.02, y - h * 0.5), (x + h * 0.1, y - h * 0.5), (x + h * 0.2, y), (x + h * 0.11, y)], fill=c)
        f_ = el.get("facing", 1)
        d.polygon([(x + f_ * h * 0.1, y - h + 2.4 * hr), (x + f_ * h * 0.34, y - h * 0.62), (x + f_ * h * 0.3, y - h * 0.57),
                   (x + f_ * h * 0.07, y - h + 3.2 * hr)], fill=c)
        d.polygon([(x - f_ * h * 0.1, y - h + 2.4 * hr), (x - f_ * h * 0.2, y - h * 0.5), (x - f_ * h * 0.15, y - h * 0.48),
                   (x - f_ * h * 0.07, y - h + 3.2 * hr)], fill=c)
        if el.get("rim"):
            rim = colour(pal, el["rim"]) + (200,)
            d.line([(x + f_ * hr, y - h + hr), (x + f_ * h * 0.13, y - h + 2.4 * hr), (x + f_ * h * 0.1, y - h * 0.48),
                    (x + f_ * h * 0.19, y)], fill=rim, width=3)
    elif k == "vtext":
        # vertical writing (top to bottom), one glyph per line: talismans, shop signs
        size = int(el.get("size", 48))
        f = face(tv, el.get("font", "jp"), size)
        x, y = el["at"]
        for i, ch in enumerate(str(el.get("text", ""))):
            d.text((x, y + i * size * float(el.get("leading", 1.08))), ch, font=f, fill=colour(pal, el.get("color", "ink")) + (a,), anchor="mt")
    elif k == "ring":
        cx, cy = el["center"]
        r, wd = el["r"], int(el.get("width", 8))
        bb = [cx - r, cy - el.get("ry", r), cx + r, cy + el.get("ry", r)]
        if el.get("track"):
            d.arc(bb, 0, 360, fill=colour(pal, el["track"]) + (120,), width=wd)
        d.arc(bb, -90, -90 + 360 * float(el.get("value", 1)), fill=colour(pal, el.get("color", "accent")) + (a,), width=wd)
    elif k == "line":
        d.line([tuple(p) for p in el["points"]], fill=colour(pal, el.get("color", "ink")) + (a,), width=int(el.get("width", 3)))
    elif k == "dots":
        x, y, w, h = el["box"]
        pitch, r = el.get("pitch", 10), el.get("r", 2.5)
        c = colour(pal, el.get("color", "accent")) + (a,)
        for yy in range(int(y), int(y + h), int(pitch)):
            for xx in range(int(x), int(x + w), int(pitch)):
                d.ellipse([xx - r, yy - r, xx + r, yy + r], fill=c)
    elif k == "scan":
        x, y, w, h = el["box"]
        c = colour(pal, el.get("color", "ink")) + (a,)
        for yy in range(int(y), int(y + h), int(el.get("pitch", 4))):
            d.line([(x, yy), (x + w, yy)], fill=c, width=1)
    elif k == "glow":
        cx, cy = el["center"]
        r = el["r"]
        c = colour(pal, el.get("color", "accent"))
        g2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(g2).ellipse([cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5], fill=c + (a,))
        layer = g2.filter(ImageFilter.GaussianBlur(r * 0.35))
    elif k in ("text", "stamp"):
        size = int(el.get("size", 48))
        txt = str(el.get("text", ""))
        f = fallback(face(tv, el.get("font", "display"), size), txt, size)
        t = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        td = ImageDraw.Draw(t)
        c = colour(pal, el.get("color", "ink")) + (a,)
        cx, cy = el.get("at") or el.get("center")
        if k == "stamp":
            r = el.get("r", size)
            sq = el.get("square", False)
            bb = [cx - r, cy - r, cx + r, cy + r]
            (td.rectangle if sq else td.ellipse)(bb, outline=c, width=int(max(3, r // 10)))
            td.text((cx, cy), txt, font=f, fill=c, anchor="mm")
        else:
            sw = int(el.get("stroke", 0))
            td.text((cx, cy), txt, font=f, fill=c, anchor=el.get("anchor", "la"),
                    stroke_width=sw, stroke_fill=colour(pal, el.get("stroke_color", "ground")) + (255,))
        rot = float(el.get("rotate", 0))
        if rot:
            t = t.rotate(rot, center=(cx, cy), resample=Image.BICUBIC)
        layer = t
    return layer


def uri(path, w=None, fmt="JPEG"):
    im = Image.open(path).convert("RGBA" if fmt == "PNG" else "RGB")
    if w and im.width > w:
        im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, fmt, **({"quality": 86} if fmt == "JPEG" else {}))
    return f"data:image/{fmt.lower()};base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def specimen(tv, which, text, size, fg, bg):
    f = face(tv, which, size)
    w = min(1100, int(f.getlength(text)) + 28)
    im = Image.new("RGB", (max(w, 60), int(size * 1.45) + 10), bg)
    ImageDraw.Draw(im).text((14, 6), text, font=f, fill=fg)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def cover_html(out, d):
    """every direction's moment side by side at the top of the board: the owner compares them in one glance"""
    cells = []
    for x in [x for x in d.get("directions") or [] if str(x.get("title") or "").strip()]:
        pic = next((p for p in (os.path.join(out, f"{x['key']}.strip.jpg"), os.path.join(out, f"{x['key']}.jpg")) if os.path.isfile(p)), None)
        if not pic:
            continue
        cells.append(f'<a class=cell href="#d-{html.escape(x["key"])}"><img src="{uri(pic, 520)}"><b>{html.escape(x["key"])} · {html.escape(x["title"])}</b>'
                     f'<span>{html.escape(str((x.get("signature_moment") or {}).get("name") or ""))}</span></a>')
    return f"<div class=cover>{''.join(cells)}</div>" if cells else ""


def critique_html(d, key):
    """what the blind critics said about this direction (rank of n, the cliche they named, what stays, the stronger version)"""
    rows = []
    for c in d.get("critiques") or []:
        rank = c.get("ranking") or []
        if key not in rank:
            continue
        n = (c.get("notes") or {}).get(key) or {}
        rows.append(f"<li><b>#{rank.index(key) + 1} of {len(rank)}</b> ({html.escape(str(c.get('judge')))}) - cliché: "
                    f"<i>{html.escape(str(n.get('cliche', '')))}</i><br>remembered: {html.escape(str(n.get('remember', '')))}"
                    f"<br>stronger: {html.escape(str(n.get('stronger', '')))}</li>")
    return f"<h3>Blind critique</h3><ul class=crit>{''.join(rows)}</ul>" if rows else ""


def reel_html(out, key, still, brief_path=None):
    """the signature moment in motion when `kit ui direct reel` made it (a GIF), else the still sketch"""
    gif = os.path.join(out, f"{key}.reel.gif")
    stamp = os.path.getmtime(brief_path) if brief_path and os.path.isfile(brief_path) else 0
    if os.path.isfile(gif) and os.path.getmtime(gif) >= stamp:
        with open(gif, "rb") as fh:
            data = base64.b64encode(fh.read()).decode("ascii")
        return f'<img class=frame src="data:image/gif;base64,{data}"><p class=why>the signature moment, in motion (a sketch)</p>'
    return f'<img class=frame src="{uri(still, 1280)}">'


def plate(direction):
    import plates
    pal = direction.get("palette") or {}
    sh = {"line": pal.get("accent") or "#ffffff", "line2": pal.get("support") or pal.get("ink") or "#888888",
          "fill": pal.get("ground") or "#101010", "fill_alpha": 0.92, "width": 2, "corner": "none", "chamfer": 0}
    sh.update({k: v for k, v in (direction.get("shape") or {}).items() if k in ("width", "corner", "chamfer", "fill_alpha", "line", "line2", "fill")})
    for k in ("line", "line2", "fill"):
        if not str(sh[k]).startswith("#"):
            sh[k] = pal.get(sh[k]) or "#888888"
    im = plates.p_frame(sh, (360, 150))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def cmd_board(a):
    try:
        p, d = load(a.name, a.game)
    except (OSError, json.JSONDecodeError) as e:
        return emit("fail", f"direct board: {e}", f"lune run kit ui direct new {a.name} --ask \"...\"")
    errs, _ = check_brief(d)
    out = out_dir(d)
    os.makedirs(out, exist_ok=True)
    e = html.escape
    secs, frames, skipped = [], [], []
    for x in [x for x in d.get("directions") or [] if str(x.get("title") or "").strip()]:
        fp, bad = draw_frame(x, os.path.join(out, f"{x['key']}.jpg"))
        skipped += bad
        frames.append(fp)
        pal = x.get("palette") or {}
        tv = x.get("type_voice") or {}
        sw = "".join(f'<div class=sw><div class=chip style="background:{e(v)}"></div><code>{e(k)}<br>{e(v)}</code></div>'
                     for k, v in pal.items() if k != "why" and hex_rgb(v))
        fg, bg = colour(pal, "ink", "#ffffff"), colour(pal, "ground", "#000000")
        if de(fg, bg) < 30:
            fg = (255, 255, 255) if sum(bg) < 380 else (0, 0, 0)
        spec = (f'<img src="{specimen(tv, "display", x["title"].upper(), 56, fg, bg)}">'
                f'<img src="{specimen(tv, "body", "Round 3 - 1,250 - Hold to charge", 26, fg, bg)}">')
        beats = "".join(f"<li><b>{e(str(b[0]))} s</b> {e(str(b[1]))}</li>" for b in (x.get("signature_moment") or {}).get("beats") or []
                        if isinstance(b, (list, tuple)) and len(b) >= 2)
        srcs = "".join(f"<li><b>{e(str(s.get('what')))}</b> <small>({e(str(s.get('kind')))})</small> - {e(str(s.get('look_for') or ''))}</li>" for s in x.get("sources") or [])
        nots = "".join(f"<li>{e(str(n))}</li>" for n in x.get("not") or [])
        scr = "".join(f"<li><b>{e(k)}</b>: {e(str(v))}</li>" for k, v in (x.get("screens") or {}).items())
        ax = x.get("axes") or {}
        rec = " rec" if (d.get("recommendation") or {}).get("key") == x["key"] else ""
        secs.append(f"""<section class="dir{rec}" id="d-{e(x['key'])}"><h2><span class=k>{e(x['key'])}</span> {e(x['title'])}{' <em>recommended</em>' if rec else ''}</h2>
{reel_html(out, x["key"], fp, p)}<p class=big>{e(str(x.get('big_idea')))}</p>
<p class=axes>{' · '.join(f'{e(k)}: <b>{e(str(v))}</b>' for k, v in ax.items())} · medium: <b>{e(str(x.get('medium')))}</b></p>
<div class=cols><div><h3>How it moves</h3><p>{e(str(x.get('verb')))}</p><h3>Signature moment: {e(str((x.get('signature_moment') or {}).get('name')))}</h3><ol class=beats>{beats}</ol>
<h3>Only here</h3><p>{e(str(x.get('only_here')))}</p><h3>What each screen becomes</h3><ul>{scr}</ul></div>
<div><h3>Palette</h3><div class=sws>{sw}</div><p class=why>{e(str(pal.get('why')))}</p><h3>Type voice</h3>{spec}<p class=why>{e(str(tv.get('why')))}</p>
<h3>Shape language</h3><img src="{plate(x)}"></div></div>
<div class=cols><div><h3>Sources to gather (real stills)</h3><ul>{srcs}</ul></div><div><h3>It is NOT</h3><ul>{nots}</ul>
<h3>On Roblox</h3><p>{e(str(x.get('roblox')))}</p><h3>Risk</h3><p>{e(str(x.get('risk')))}</p></div></div>{critique_html(d, x['key'])}
<p class=pick>pick it: <code>lune run kit ui direct pick {e(a.name)} {e(x['key'])} "&lt;your words&gt;" --by owner</code></p></section>""")
    r = d.get("reading") or {}
    words = "".join(f"<li><b>{e(', '.join(w.get('words') or []))}</b> - before: <i>{e(str(w.get('proven')))}</i><br>here: {e(str(w.get('here')))}</li>" for w in r.get("words") or [])
    rec = d.get("recommendation") or {}
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(a.name)} directions</title><style>
body{{background:#0d0d10;color:#e9e9ee;font:15px/1.5 system-ui,sans-serif;margin:0 auto;padding:24px 16px;max-width:1320px}}
h1{{margin:0}} .ask{{font:italic 20px Georgia,serif;color:#fff;border-left:4px solid #888;padding:6px 14px;margin:14px 0}}
.read{{background:#17171c;padding:12px 16px;border-radius:8px}} .dir{{margin:36px 0;padding:18px;background:#141418;border-radius:10px;border:1px solid #26262e}}
.dir.rec{{border-color:#d9b44a}} .k{{display:inline-block;background:#fff;color:#000;padding:0 10px;border-radius:4px;margin-right:6px}}
em{{font-size:13px;color:#d9b44a;font-style:normal;margin-left:8px}} .frame{{width:100%;border-radius:6px}} .big{{font-size:19px;color:#fff;margin:12px 0 4px}}
.axes{{color:#aab}} .cols{{display:grid;grid-template-columns:1fr 1fr;gap:22px}} @media(max-width:860px){{.cols{{grid-template-columns:1fr}}}}
h3{{margin:14px 0 4px;color:#cfd2ff;font-size:14px;text-transform:uppercase;letter-spacing:.06em}} .sws{{display:flex;flex-wrap:wrap;gap:8px}}
.sw{{width:92px}} .chip{{height:40px;border-radius:4px;border:1px solid #333}} code{{color:#cde;font-size:12px}} .why{{color:#99a;font-size:13px}}
.beats li{{margin-bottom:4px}} .crit li{{margin-bottom:6px;color:#d8d8e8}} .cover{{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px;margin:14px 0}} .cell{{display:flex;flex-direction:column;background:#141418;border-radius:8px;padding:6px;color:#e9e9ee;text-decoration:none}} .cell span{{color:#99a;font-size:13px}} .pick{{background:#0b0b0e;padding:8px 12px;border-radius:6px}} img{{max-width:100%}}
</style></head><body><h1>{e(a.name)} - creative directions</h1><p class=ask>"{e(str(d.get('ask')))}"</p>
<div class=read><b>The fantasy:</b> {e(str(r.get('fantasy')))}<br><b>The player:</b> {e(str(r.get('player')))}<br><b>When they look:</b> {e(str(r.get('moment_of_use')))}
<ul>{words}</ul><b>Assumed (correct me):</b> {e('; '.join(r.get('assumptions') or []))}</div>
<p><b>Recommended: {e(str(rec.get('key')))}</b> - {e(str(rec.get('why')))}</p>{cover_html(out, d)}
{''.join(secs)}<p class=why>Every frame is a SKETCH of the direction on the game's own world shot, drawn by kit/ui/direct.py - the real pieces are made from the sources after the pick.</p></body></html>"""
    page = os.path.join(out, "board.html")
    with open(page, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(doc)
    # one contact sheet of every frame (for a quick look)
    if frames:
        tiles = [Image.open(f).resize((640, 360)) for f in frames]
        cols = 2
        rows = math.ceil(len(tiles) / cols)
        sheet = Image.new("RGB", (cols * 640, rows * 360), (10, 10, 12))
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % cols) * 640, (i // cols) * 360))
        sheet.save(os.path.join(out, "frames.jpg"), quality=88)
    note = f" ({len(errs)} check problem(s) - run kit ui direct check)" if errs else ""
    if skipped:
        note += f" ({len(skipped)} sketch element(s) skipped: {skipped[0]})"
    return emit("pass", f"direct board {a.name}: {len(frames)} sketch frame(s) + board -> {page.replace(chr(92), '/')}{note}",
                f"fix the skipped element(s) in the brief's frame: {skipped[0]}" if skipped else
                f"show the owner {page.replace(chr(92), '/')}; their pick: lune run kit ui direct pick {a.name} <key> \"<their words>\" --by owner",
                page=page.replace(chr(92), "/"), frames=[f.replace(chr(92), "/") for f in frames], skipped=skipped)


# ------------------------------------------------------------------ pick
def draft_identity(d, x, ident):
    pal = x.get("palette") or {}
    tv = x.get("type_voice") or {}
    ground, ink, accent = pal.get("ground"), pal.get("ink"), pal.get("accent")
    support = pal.get("support") or accent
    tokens = {"bg": ground, "panel": ground, "panel2": support, "line": ink, "line2": support, "accent": accent,
              "accent2": support, "text": ink, "muted": support, "danger": pal.get("danger") or accent,
              "good": pal.get("good") or support, "warn": pal.get("warn") or accent, "focus": accent, "shadow": "#000000"}
    for k, v in pal.items():
        if k not in ("why", "ground", "ink", "accent", "support") and hex_rgb(v):
            tokens[k] = v
    return {
        "name": ident, "direction": {"brief": d["name"], "key": x["key"], "game": d.get("game")},
        "about": f"{x.get('title')}: {x.get('big_idea')}",
        "world": (d.get("context") or {}).get("pitch") or "",
        "tokens": tokens,
        "fonts": {"font": tv.get("body"), "titleFont": tv.get("display"), "monoFont": "RobotoMono"},
        "radius": {"s": 0, "m": 0, "l": 0},
        "roles": {"title": {"size": 48, "font": "titleFont"}, "heading": {"size": 28, "font": "titleFont"},
                  "body": {"size": 20, "font": "font"}, "hint": {"size": 16, "font": "font", "color": "muted"},
                  "number": {"size": 40, "font": "titleFont"}},
        "minimums": {"text": 16, "button": 44, "icon": 30},
        "shape": {"line": "line", "line2": "line2", "fill": "panel", "fill_alpha": 0.92, "width": 2, "corner": "none",
                  "chamfer": 0, "glow": 0, **{k: v for k, v in (x.get("shape") or {}).items()}},
        "motion": {"enter": x.get("verb"), "signature": x.get("signature_moment")},
        "bans": list(x.get("not") or []),
        "references": [{"game": s.get("what"), "screen": s.get("kind"), "image": "", "take": f"TO GATHER: {s.get('look_for') or ''}"}
                       for s in x.get("sources") or []],
        "accent_evidence": f"TO MEASURE: {pal.get('why') or ''}",
    }


def cmd_pick(a):
    try:
        p, d = load(a.name, a.game)
    except (OSError, json.JSONDecodeError) as e:
        return emit("fail", f"direct pick: {e}", "name a brief: lune run kit ui direct new ...")
    x = next((x for x in d.get("directions") or [] if x.get("key") == a.key), None)
    if not x or not str(x.get("title") or "").strip():
        return emit("fail", f"direct pick: no direction {a.key} in {a.name}", f"lune run kit ui direct board {a.name}")
    errs, _ = check_brief(d)
    if errs:
        return emit("fail", f"direct pick: the brief fails its check ({errs[0]})", f"lune run kit ui direct check {a.name}")
    words = (a.words or "").strip()
    if a.by != "owner" or not words:
        d["proposal"] = {"key": a.key, "words": words, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        save(p, d)
        return emit("pass", f"direct pick {a.name} {a.key}: recorded as a PROPOSAL (not the owner's pick)",
                    f"show the owner the board; their pick: lune run kit ui direct pick {a.name} <key> \"<their words>\" --by owner")
    ident = a.identity or re.sub(r"[^a-z0-9]", "", (x.get("title") or a.name).lower())[:16] or a.name.replace("-", "")
    ip = os.path.join(ui_root(d.get("game")), "identities", f"{ident}.json")
    existing = None
    if os.path.isfile(ip):
        try:
            with open(ip, encoding="utf-8") as fh:
                existing = json.load(fh)
        except Exception:  # noqa: BLE001
            existing = {}
        if (existing.get("direction") or {}).get("brief") != d["name"]:
            return emit("fail", f"direct pick: {ip} is another identity (not drafted from {d['name']})",
                        f"name a new one: lune run kit ui direct pick {a.name} {a.key} \"<their words>\" --by owner --identity <new>")
    d["pick"] = {"key": a.key, "words": words, "by": "owner", "identity": ident, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    save(p, d)
    made = existing is None
    if made:
        save(ip, draft_identity(d, x, ident))
    elif (existing.get("direction") or {}).get("key") != a.key:
        save(ip, draft_identity(d, x, ident))  # (a re-pick: this brief's own draft follows the new direction)
        made = True
    if a.lune:
        subprocess.run([a.lune, "run", "kit", "approve", "ui", f"direction-{a.name}", words, "--by", "owner"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return emit("pass", f"direct pick {a.name}: the owner picked {a.key} ({x.get('title')})"
                + (f"; identity drafted -> {ip.replace(chr(92), '/')}" if made else f"; {ip} already exists (left as it is)"),
                f"gather the direction's sources as real stills: lune run kit ui refs {ident} \"<game>\" \"<screen words>\" (then measure, then the identity's tokens from the stills)",
                identity=ip.replace(chr(92), "/"))


EXEMPT = os.path.join(HERE, "direct_exempt.json")


def rel(path):
    return os.path.relpath(os.path.abspath(path)).replace(chr(92), "/")


def exempt(ident_path, locks="board/locks.json"):
    """an identity made before the director: its PATH (never its bare name - a new game identity may reuse an old
    name) is in the frozen list, or in the project's own grandfathered list (board/locks.json, as every lock reads)"""
    p = rel(ident_path)
    try:
        with open(EXEMPT, encoding="utf-8") as fh:
            if p in json.load(fh)["paths"]:
                return True
    except Exception:  # noqa: BLE001
        pass
    try:
        with open(locks, encoding="utf-8") as fh:
            return p in (((json.load(fh).get("grandfathered") or {}).get("ui")) or [])
    except Exception:  # noqa: BLE001
        return False


def owner_waived(ident_name, step="direction", locks="board/locks.json"):
    """the owner's waiver (kit approve ui <identity> "<words>" --by owner --waive direction), as kit/lib/locks reads it"""
    try:
        with open(locks, encoding="utf-8") as fh:
            rec = ((json.load(fh).get("waivers") or {}).get("ui") or {}).get(ident_name)
    except Exception:  # noqa: BLE001
        return False
    if not isinstance(rec, dict) or str(rec.get("by") or rec.get("who") or "").lower() != "owner":
        return False
    steps = rec.get("steps")
    return not isinstance(steps, list) or step in steps


def direction_lock(ident_name, ident_path):
    """(ok, detail, todo) for the lock refs_lock.py runs on every NEW screen: its identity was chosen as a direction"""
    if not ident_name or exempt(ident_path) or owner_waived(ident_name):
        return True, "", ""
    ok, why = direction_status(ident_path, ident_name)
    if ok:
        return True, why, ""
    return False, f"creative direction: {why}", \
        "an original look starts with a direction: lune run kit ui direct new <name> --ask \"<the owner's words>\" (then check, board, the owner's pick)"


def gather_plan(d, x, ident):
    """the picked direction's sources as the exact gather commands (kit ui refs): a game's own screens from its store
    page, everything else as freely licensed stills from Wikimedia Commons (a MediaWiki API, no scraping)"""
    cmds = []
    for s in x.get("sources") or []:
        what, look = str(s.get("what") or ""), str(s.get("look_for") or "")
        keep = content_words(look)
        ordered = dict.fromkeys(w.strip("'") for w in re.findall(r"[a-z][a-z'-]+", look.lower()) if w.strip("'") in keep)
        words = " ".join(list(ordered)[:4]) or what
        if str(s.get("kind") or "").lower().strip() == "game":
            cmds.append(f'lune run kit ui refs {ident} "{what}" "{words}"')
        else:
            cmds.append(f'lune run kit ui refs {ident} "{what}" "{words}" --wiki commons.wikimedia.org')
    cmds.append(f"lune run kit ui refs {ident} --index   (then --keep the stills that show it, --tag what each one is)")
    return cmds


def cmd_feedback(a):
    """the owner's words on a board (no score needed: a verdict without a number is still the only quality signal).
    `--liked` / `--disliked` name directions (keys) or `all`; `--by owner` only when the owner said it"""
    try:
        p, d = load(a.name, a.game)
    except (OSError, json.JSONDecodeError) as e:
        return emit("fail", f"direct feedback: {e}", "name a brief")
    if a.by != "owner" or not (a.words or "").strip():
        return emit("fail", "direct feedback: only the owner's own words, with --by owner", "quote the owner verbatim")
    keys = [x.get("key") for x in d.get("directions") or []]

    def parse(v):
        v = (v or "").strip()
        return keys if v == "all" else [k for k in (s.strip() for s in v.split(",")) if k in keys]
    entry = {"by": "owner", "words": a.words.strip(), "liked": parse(a.liked), "disliked": parse(a.disliked),
             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    d.setdefault("owner_feedback", []).append(entry)
    save(p, d)
    return emit("pass", f"direct feedback {a.name}: the owner's words recorded (liked {','.join(entry['liked']) or '-'}, disliked {','.join(entry['disliked']) or '-'})",
                "lune run kit ui direct learn (the taste profile reads it)")


def cmd_index(a):
    """every brief of every game on one page: the ask, where it stands, each moment, the blind ranking, the board"""
    e = html.escape
    rows, n_dirs = [], 0
    for bp in glob_briefs():
        try:
            with open(bp, encoding="utf-8") as fh:
                d = json.load(fh)
        except Exception:  # noqa: BLE001
            continue
        name = d.get("name") or os.path.basename(bp)[:-5]
        out = out_dir(dict(d, name=name))
        errs, _ = check_brief(d)
        pick = d.get("pick") or {}
        state = f"picked {pick.get('key')} by the owner" if pick.get("by") == "owner" else ("checked - awaiting the owner's pick" if not errs else f"draft ({len(errs)} problem(s))")
        crit = (d.get("critiques") or [])
        rank = " > ".join(crit[-1]["ranking"]) if crit else "no blind critique yet"
        rec = (d.get("recommendation") or {}).get("key")
        cells = []
        for x in [x for x in d.get("directions") or [] if str(x.get("title") or "").strip()]:
            n_dirs += 1
            pic = next((p for p in (os.path.join(out, f"{x['key']}.strip.jpg"), os.path.join(out, f"{x['key']}.jpg")) if os.path.isfile(p)), None)
            img = f'<img src="{uri(pic, 420)}">' if pic else '<div class=none>no sketch yet</div>'
            star = " ★" if x["key"] == rec else ""
            cells.append(f'<div class=cell>{img}<b>{e(x["key"])} · {e(x["title"])}{star}</b><span>{e(str((x.get("signature_moment") or {}).get("name") or ""))}</span></div>')
        board = f"{d.get('game') or 'project'}/{name}/board.html"
        rows.append(f"""<section><h2>{e(str(d.get('game') or 'project'))} · {e(name)}</h2><p class=ask>"{e(str(d.get('ask')))}"</p>
<p class=meta><b>{e(state)}</b> · blind ranking: {e(rank)} · <a href="{e(board)}">open the board</a></p><div class=grid>{''.join(cells)}</div></section>""")
    doc = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UI directions</title>
<style>body{{background:#0d0d10;color:#e9e9ee;font:15px/1.45 system-ui,sans-serif;margin:0 auto;padding:24px 16px;max-width:1400px}}
section{{background:#141418;border-radius:10px;padding:14px 16px;margin:18px 0}} h2{{margin:0}} .ask{{font:italic 18px Georgia,serif;color:#fff;margin:6px 0}}
.meta{{color:#aab}} a{{color:#9cf}} .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}}
.cell{{display:flex;flex-direction:column;background:#0d0d10;border-radius:8px;padding:6px}} .cell img{{width:100%;border-radius:4px}} .cell span{{color:#99a;font-size:13px}}
.none{{height:90px;display:flex;align-items:center;justify-content:center;color:#666}}</style></head><body>
<h1>UI creative directions</h1><p class=meta>Every brief the director has made, each with its moments; ★ = the director's recommendation. The owner picks:
<code>lune run kit ui direct pick &lt;brief&gt; &lt;key&gt; "&lt;your words&gt;" --by owner</code></p>{''.join(rows)}</body></html>"""
    path = os.path.join("build", "ui", "directions", "index.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(doc)
    return emit("pass", f"direct index: {len(rows)} brief(s), {n_dirs} direction(s) -> {path.replace(chr(92), '/')}",
                f"show the owner {path.replace(chr(92), '/')}", page=path.replace(chr(92), "/"))


def cmd_sources(a):
    try:
        p, d = load(a.name, a.game)
    except (OSError, json.JSONDecodeError) as e:
        return emit("fail", f"direct sources: {e}", "lune run kit ui direct new ...")
    pick = d.get("pick") or {}
    key = a.key or pick.get("key")
    x = next((x for x in d.get("directions") or [] if x.get("key") == key), None)
    if not x:
        return emit("fail", f"direct sources {a.name}: no picked direction yet (or no direction {key})",
                    f"the owner picks first: lune run kit ui direct pick {a.name} <key> \"<their words>\" --by owner")
    ident = pick.get("identity") if pick.get("key") == key else re.sub(r"[^a-z0-9]", "", x["title"].lower())[:16]
    cmds = gather_plan(d, x, ident)
    d["gather"] = {"key": key, "identity": ident, "commands": cmds}
    save(p, d)
    note = "" if pick.get("by") == "owner" and pick.get("key") == key else " (a PREVIEW: the owner has not picked this one)"
    return emit("pass", f"direct sources {a.name} {key}: {len(cmds) - 1} source(s) to gather as real stills{note}",
                "run them (downloads: with the owner's go-ahead), keep what shows the thing, then the identity's tokens come from the stills",
                commands=cmds)


def direction_status(ident_path, ident_name=None):
    """the identity lock: (ok, why) - an identity drafted from a direction needs that brief (of ITS game) checked and
    PICKED by the owner FOR this identity"""
    try:
        with open(ident_path, encoding="utf-8") as fh:
            ident = json.load(fh)
    except Exception as e:  # noqa: BLE001
        return False, f"unreadable identity: {e}"
    ident_name = ident_name or os.path.basename(ident_path)[:-5]
    dr = ident.get("direction")
    if not isinstance(dr, dict) or not dr.get("brief"):
        return False, "no creative direction: lune run kit ui direct new <name> --ask \"<the owner's words>\" first"
    p = os.path.join(ui_root(dr.get("game")), "directions", f"{dr['brief']}.json")
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:  # noqa: BLE001
        return False, f"its direction brief {p} is missing"
    if d.get("game") != dr.get("game"):
        return False, f"the brief {p} is for game {d.get('game')}, the identity says {dr.get('game')}"
    pick = d.get("pick") or {}
    if pick.get("by") != "owner":
        return False, f"direction {dr['brief']} has no owner pick yet (show the board: kit ui direct board {dr['brief']})"
    if pick.get("key") != dr.get("key"):
        return False, f"the owner picked {pick.get('key')}, this identity follows {dr.get('key')}"
    if pick.get("identity") != ident_name:
        return False, f"the owner's pick of {dr['brief']} {pick.get('key')} made identity '{pick.get('identity')}', not '{ident_name}'"
    return True, f"direction {dr['brief']} {dr['key']} picked by the owner ('{pick.get('words')}')"


def cmd_status(a):
    if a.identity:
        ok, why = direction_status(a.identity)
        return emit("pass" if ok else "fail", f"direct status: {why}", "none - proceed" if ok else why)
    if not a.name:
        return emit("fail", "direct status: which brief? (a name, or --identity <pack>)",
                    "lune run kit ui direct status <name>   (the briefs: lune run kit ui direct index)")
    try:
        _, d = load(a.name, a.game)
    except (OSError, json.JSONDecodeError) as e:
        return emit("fail", f"direct status: {e}", "lune run kit ui direct new ...")
    errs, _ = check_brief(d)
    pick = d.get("pick") or {}
    st = "picked" if pick.get("by") == "owner" else ("checked" if not errs else "draft")
    return emit("pass", f"direct status {a.name}: {st}" + (f" ({pick.get('key')}: '{pick.get('words')}')" if pick else ""),
                {"draft": f"lune run kit ui direct check {a.name}", "checked": f"show the owner: lune run kit ui direct board {a.name}",
                 "picked": "gather the picked direction's sources: kit ui refs"}[st], state=st)


# ------------------------------------------------------------------ learn
def glob_briefs():
    out = []
    roots = [os.path.join("assets", "ui", "directions")]
    if os.path.isdir("games"):
        roots += [os.path.join("games", g, "assets", "ui", "directions") for g in sorted(os.listdir("games"))]
    for r in roots:
        if os.path.isdir(r):
            out += [os.path.join(r, f) for f in sorted(os.listdir(r)) if f.endswith(".json")]
    return out


def md_rows(md):
    rows, lines = [], md.splitlines()
    for i, ln in enumerate(lines):
        if not ln.startswith("|") or re.match(r"^\|\s*:?-", ln):
            continue
        if i + 1 < len(lines) and re.match(r"^\|\s*:?-", lines[i + 1]):
            continue  # a header
        rows.append([c.strip() for c in ln.strip().strip("|").split("|")])
    return rows


def cmd_learn(a):
    golden = md_rows(read(os.path.join(VAULT, "golden.md")))
    grave = md_rows(read(os.path.join(VAULT, "graveyard.md")))
    orders = [ln[2:].strip() for ln in (read(os.path.join(VAULT, "orders.md")) + "\n" + read(os.path.join("kit", "knowledge", "vault", "shared", "orders.md"))).splitlines()
              if ln.startswith("- ") and not ln.startswith("- ~~")]
    # one line per piece: the rows that say what decided it win over the bare score rows of the same piece
    decided = [r for r in golden if len(r) >= 5 and r[4]]
    names = {r[0].split()[0] for r in decided}
    keep = decided + [r for r in golden if len(r) >= 5 and not r[4] and r[0].split()[0] not in names]
    loved = [f"- **{r[0]}** {r[1]} - \"{r[3][:150]}\"" + (f" -> decided by: {r[4][:220]}" if r[4] else "") for r in keep]
    dead = [f"- **{r[0]}** ({r[2][:40]}) - \"{r[3][:140]}\" -> {r[4][:200]}" for r in grave if len(r) >= 5]
    picks, critics, feedback = [], [], []
    for bp in glob_briefs():
        try:
            with open(bp, encoding="utf-8") as fh:
                bd = json.load(fh)
        except Exception:  # noqa: BLE001
            continue
        titles = {x.get("key"): x.get("title") for x in bd.get("directions") or []}
        for c in bd.get("critiques") or []:
            for k, nt in (c.get("notes") or {}).items():
                if nt.get("cliche"):
                    critics.append(f"- {bd.get('name')} / {titles.get(k)}: {str(nt['cliche'])[:230]} -> stronger: {str(nt.get('stronger', ''))[:200]}")
        for fbk in bd.get("owner_feedback") or []:
            liked = ", ".join(titles.get(k, k) for k in fbk.get("liked") or []) or "-"
            disliked = ", ".join(titles.get(k, k) for k in fbk.get("disliked") or []) or "-"
            feedback.append(f"- {bd.get('name')} ({bd.get('game')}): liked {liked}; not liked {disliked} - \"{str(fbk.get('words'))[:300]}\"")
        pk = bd.get("pick") or {}
        if pk.get("by") != "owner":
            continue
        dd = {x.get("key"): x for x in bd.get("directions") or []}
        won = dd.get(pk.get("key")) or {}
        lost = [x.get("title") for k, x in dd.items() if k != pk.get("key") and x.get("title")]
        ax = ", ".join(f"{k}: {v}" for k, v in (won.get("axes") or {}).items())
        picks.append(f"- **{won.get('title')}** ({bd.get('name')}; {ax}; {won.get('medium')}) over {', '.join(lost)} - \"{pk.get('words')}\"")

    def plain(e):  # (the entry's plain words, not its patterns)
        return ", ".join(m for m in e["match"] if not re.search(r"[()?|\[\\]", m)) or "like <a game>"

    lex = "\n".join(f"- **{e['id']}** ({plain(e)}) -> {e['reading']}  _(evidence: {'; '.join(e['evidence'])[:200]})_" for e in lexicon())
    doc = f"""# The creative director's taste profile (UI)

Distilled {time.strftime('%Y-%m-%d %H:%M')} by `kit ui direct learn` from golden.md, graveyard.md, the orders and
kit/ui/direct_lexicon.json - re-run after every verdict. Every new brief (`kit ui direct new`) starts here.

## How a director reads the owner's words (proven by verdicts)
{lex}

## What the owner LOVED - do more of what decided these
{chr(10).join(loved) or '- (none yet)'}

## What the owner REJECTED - never again
{chr(10).join(dead) or '- (none yet)'}

## What the OWNER said about boards (the only quality signal - weigh it above every critic)
{chr(10).join(feedback) or '- (no owner feedback yet)'}

## What blind critics keep naming (`kit ui direct critique`) - the clichés to steer clear of
{chr(10).join(critics) or '- (no critique yet)'}

## What the owner PICKED from a board (and over what)
{chr(10).join(picks) or '- (no pick yet: every pick lands here)'}

## Standing orders
{chr(10).join('- ' + o[:260] for o in orders)}

## The director's method (UI)
0. THE OWNER'S TASTE FIRST (2026-10-25): directions whose animation IS a real physical process - a tally stick notched and
   split, a deed stitched, breath fogging frosted glass, iron cooling with a hiss - were 'all amazing original ideas';
   the neon / broadcast / signage board was not liked. Lead with crafts and processes from the world's own materials;
   `spark` draws from the crafts catalogue in proportion to what the owner liked. Every direction names its `process`.
1. Keep the ask VERBATIM. Read every loaded word through the lexicon above; say what it means for THIS piece.
2. Name the fantasy, the player, and the moment they look at the screen (mid-fight glance? a calm menu?).
3. List the objects of the game's world: a pro UI is one of them (the health bar IS a guitar neck; the gauge IS a
   gunsmith's steel plate). A wish-word (sleek, modern, clean, epic) is never a direction.
4. Branch into 3-5 TERRITORIES that differ on the axes (screen / diegetic / hybrid; quiet / loud; the material; whose
   voice the UI speaks in) - one of them pulled from outside games (signage, broadcast, print, ritual, architecture).
5. Give each one verb (how it moves) and ONE signature moment, beat by beat, that only this game could have.
6. What blind critics remembered across three worlds (2026-10-24) - build these in from the start: a TRANSFORMATION of
   an object only this world has (rivals' roundels going NOT IN SERVICE, a talisman growing back longer); the
   PLAYER'S OWN input shaping it (the finger that draws the grid, the pitch of the hum - no two alike); and a MARK
   THAT STAYS (gold seams that stay lit, a crack scar until healed, tally halves that slot together later). What
   they forgot: centre-screen stamps and name cards, number walls, corner pip rows, strips that eat the screen, and
   any moment the sketch does not visibly SHOW.
7. Sketch each on the game's own world shot; recommend one; the OWNER picks. Then source-first as always: the
   picked direction's sources become real stills, measured, before a single token is set.
"""
    out = os.path.join(VAULT, "director.md")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(doc)
    return emit("pass", f"direct learn: {len(loved)} loved, {len(dead)} rejected, {len(lexicon())} owner words, {len(orders)} orders -> {out.replace(chr(92), '/')}",
                "every new brief carries it: lune run kit ui direct new <name> --ask \"<the owner's words>\"")


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    n = sub.add_parser("new")
    n.add_argument("name")
    n.add_argument("--ask", required=True)
    n.add_argument("--game", default=None)
    n.add_argument("--screens", default=None)
    for c in ("check", "board"):
        s = sub.add_parser(c)
        s.add_argument("name")
        s.add_argument("--game", default=None)
    pk = sub.add_parser("pick")
    pk.add_argument("name")
    pk.add_argument("key")
    pk.add_argument("words", nargs="?", default="")
    pk.add_argument("--by", default=None)
    pk.add_argument("--identity", default=None)
    pk.add_argument("--game", default=None)
    pk.add_argument("--lune", default="lune")
    stt = sub.add_parser("status")
    stt.add_argument("name", nargs="?", default="")
    stt.add_argument("--identity", default=None)
    stt.add_argument("--game", default=None)
    sub.add_parser("learn")
    sub.add_parser("index")
    fb = sub.add_parser("feedback")
    fb.add_argument("name")
    fb.add_argument("words")
    fb.add_argument("--liked", default="")
    fb.add_argument("--disliked", default="")
    fb.add_argument("--by", default=None)
    fb.add_argument("--game", default=None)
    so = sub.add_parser("sources")
    so.add_argument("name")
    so.add_argument("key", nargs="?", default=None)
    so.add_argument("--game", default=None)
    cr = sub.add_parser("critique")
    cr.add_argument("name")
    cr.add_argument("--game", default=None)
    cr.add_argument("--seed", type=int, default=5)
    cr.add_argument("--record", default=None)
    cr.add_argument("--judge", default="a fresh reviewer")
    cr.add_argument("--force", action="store_true")
    cr.add_argument("--round", default=None)
    sp = sub.add_parser("spark")
    sp.add_argument("name")
    sp.add_argument("--n", type=int, default=12)
    sp.add_argument("--seed", type=int, default=7)
    sp.add_argument("--game", default=None)
    rl = sub.add_parser("reel")
    rl.add_argument("name")
    rl.add_argument("keys", nargs="*")
    rl.add_argument("--game", default=None)
    rl.add_argument("--fps", type=int, default=None)
    rl.add_argument("--width", type=int, default=640)
    a = ap.parse_args(argv)
    if not a.cmd:
        return emit("fail", "direct: new | spark | check | board | reel | critique | pick | sources | status | learn | index", "lune run kit ui direct new <name> --ask \"<the owner's words>\"")
    if a.cmd == "critique":
        import direct_critique
        return direct_critique.main([a.name, "--seed", str(a.seed), "--judge", a.judge] + (["--game", a.game] if a.game else [])
                                    + (["--record", a.record] if a.record else []) + (["--force"] if a.force else []) + (["--round", a.round] if a.round else []))
    if a.cmd == "spark":
        import direct_spark
        return direct_spark.main([a.name, "--n", str(a.n), "--seed", str(a.seed)] + (["--game", a.game] if a.game else []))
    if a.cmd == "reel":
        import direct_reel
        return direct_reel.main([a.name, *a.keys] + (["--game", a.game] if a.game else []) + (["--fps", str(a.fps)] if a.fps else []) + ["--width", str(a.width)])
    return {"new": cmd_new, "check": cmd_check, "board": cmd_board, "pick": cmd_pick, "sources": cmd_sources, "index": cmd_index, "feedback": cmd_feedback, "status": cmd_status, "learn": cmd_learn}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
