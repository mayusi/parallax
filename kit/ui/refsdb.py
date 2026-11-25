"""refsdb.py — an identity's reference STILLS as data: every still's file, resolution, screen type and source, kept in
refs/<folder>/refs.json (the manifest `kit ui refs` writes; `--index` builds it for stills gathered before it existed).

The hero route's first lock reads it (kit/ui/plan.py): a hero screen's pieces wait until its identity has >= 2 real
stills of THAT screen type at >= 1080p (the five character-action gauges plateaued at 57-67 on a 760x940 sheet: the source is the
ceiling), or the owner's quoted waiver.

    kind   "hud" | "menu" — the spec's "kind" (the exact screen type a still shows); "art" (key art: a source
           picture for ink / trace, not a screen) and "world" (a HUD-less frame: a backdrop) never count for the lock
    screen optional finer type ("title", "results", "health"...) matched against the spec's "screen_type"
    typed  "tag" (a person said so: kit ui refs <id> --tag <file>=<kind>[:<screen>]) | "words" (read from the words
           the still was gathered or described with — check it) | null (unknown)
"""
import json
import os
import re

PICS = (".png", ".jpg", ".jpeg", ".webp")
KINDS = ("hud", "menu", "art", "world")
MIN_SHORT, MIN_LONG = 1080, 1920  # (>= 1080p: the short side 1080, or a full-width 1920 crop like a letterboxed 1920x950)
HUD_WORDS = r"\b(hud|gameplay|in-game|in game|fight|fighting|battle|combat|health|gauge|bars?|ammo|race|racing|minimap|compass|boss|round start|stamina|meter|crosshair)\b"
MENU_WORDS = r"\b(menu|title|select|selection|shop|store|results?|win|victory|versus|vs|card|pause|reward|boons?|inventory|settings|lobby|unlock|episode|level up|bonfire|death|you died|logo|codes|daily|rebirth)\b"


def is_1080(size):
    if not size or len(size) < 2:
        return False
    w, h = size[0], size[1]
    return min(w, h) >= MIN_SHORT or max(w, h) >= MIN_LONG


def kind_from_words(text):
    """'hud' / 'menu' from the words a still came with, or None when they say neither or both equally"""
    t = (text or "").lower()
    h, m = len(re.findall(HUD_WORDS, t)), len(re.findall(MENU_WORDS, t))
    if h > m:
        return "hud"
    if m > h:
        return "menu"
    return None


def folders(identity, refs_root, ident_json=None):
    """the identity's reference folders: refs/<identity> plus every folder its listed references live in (neon's
    stills are in refs/nfsheat, vessel's in refs/hollow)"""
    out = []
    own = os.path.join(refs_root, identity).replace("\\", "/")
    if os.path.isdir(own):
        out.append(own)
    for r in (ident_json or {}).get("references") or []:
        img = r.get("image") if isinstance(r, dict) else None
        if isinstance(img, str) and os.path.isfile(img):
            d = os.path.dirname(img).replace("\\", "/")
            if d not in out:
                out.append(d)
    return out


def load_manifest(folder):
    p = os.path.join(folder, "refs.json")
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:  # noqa: BLE001  (a broken manifest reads as empty; --index rebuilds it)
            pass
    return {"schema": 1, "stills": []}


def save_manifest(folder, man):
    man["schema"] = 1
    man["stills"] = sorted(man.get("stills") or [], key=lambda s: s.get("file", ""))
    with open(os.path.join(folder, "refs.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(man, fh, indent=1)
        fh.write("\n")


def describe(folder, file, ident_json=None):
    """the words a still came with: its REFS.md line, and the identity reference that names it"""
    words = []
    md = os.path.join(folder, "REFS.md")
    stem = os.path.splitext(file)[0]
    # (the file name itself, or a long stem as a whole word: a stem like "a" or "hud" matched unrelated lines)
    pat = re.compile(r"(?<![\w.-])" + re.escape(stem) + r"(?![\w-])") if len(stem) >= 5 else None
    if os.path.isfile(md):
        with open(md, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if file in line or (pat and pat.search(line)):
                    words.append(line.strip())
    for r in (ident_json or {}).get("references") or []:
        if isinstance(r, dict) and isinstance(r.get("image"), str) and os.path.basename(r["image"]) == file:
            words.append(f"{r.get('screen', '')} {r.get('take', '')}")
    return " ".join(words)


def index(folder, ident_json=None):
    """(re)build a folder's manifest: every still's size; a type read from its words unless a person tagged it"""
    from PIL import Image

    man = load_manifest(folder)
    known = {s["file"]: s for s in man.get("stills") or [] if isinstance(s, dict) and s.get("file")}
    stills = []
    for f in sorted(os.listdir(folder)):
        if not f.lower().endswith(PICS) or ".read." in f or f.startswith("_"):
            continue
        try:
            with Image.open(os.path.join(folder, f)) as im:
                size = list(im.size)
        except Exception:  # noqa: BLE001
            continue
        s = dict(known.get(f) or {"file": f})
        s["size"] = size
        if s.get("typed") != "tag":
            k = kind_from_words(describe(folder, f, ident_json))
            s["kind"], s["typed"] = (k, "words") if k else (None, None)
        stills.append(s)
    man["stills"] = stills
    save_manifest(folder, man)
    return man


def stills(identity, refs_root, ident_json=None):
    """every still of the identity across its folders: {file, path, size, kind, screen, typed, folder}"""
    out = []
    for d in folders(identity, refs_root, ident_json):
        man = load_manifest(d)
        listed = {s.get("file"): s for s in man.get("stills") or [] if isinstance(s, dict)}
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(PICS) or ".read." in f or f.startswith("_"):
                continue
            s = dict(listed.get(f) or {"file": f, "size": None, "kind": None, "typed": None})
            s["path"], s["folder"] = f"{d}/{f}", d
            out.append(s)
    return out


def waiver(identity, refs_root, ident_json=None):
    """the owner's quoted waiver of the 1080p rule (refs.json "waiver": {"by": "owner", "words": "...", "date"})"""
    for d in folders(identity, refs_root, ident_json):
        w = load_manifest(d).get("waiver")
        if isinstance(w, dict) and w.get("by") == "owner" and str(w.get("words", "")).strip():
            return w
    return None


def gate(identity, refs_root, ident_json, kind, screen_type=None):
    """the refs lock for one screen: (ok, detail, todo) — >= 2 stills of this kind (and screen type) at >= 1080p"""
    if not identity:
        return False, "no identity", "set \"identity\" in the spec first"
    all_ = stills(identity, refs_root, ident_json)
    big = [s for s in all_ if is_1080(s.get("size"))]
    match = [s for s in big if s.get("kind") == kind and (not screen_type or s.get("screen") == screen_type)]
    unsized = [s for s in all_ if not s.get("size")]
    untyped = [s for s in big if not s.get("kind")]
    w = waiver(identity, refs_root, ident_json)
    want = f"{kind}" + (f":{screen_type}" if screen_type else "")
    detail = (f"{len(all_)} still(s), {len(big)} at >= 1080p, {len(match)} of this screen type ({want})"
              + (f"; {len(unsized)} not indexed" if unsized else "") + (f"; {len(untyped)} untyped" if untyped else ""))
    if len(match) >= 2:
        guessed = [s for s in match if s.get("typed") == "words"]
        return True, detail + (f" ({len(guessed)} typed from their words)" if guessed else ""), ""
    if w:
        return True, detail + f"; the OWNER waived the 1080p rule: \"{str(w['words'])[:80]}\"", ""
    if unsized:
        todo = f"lune run kit ui refs {identity} --index   (records every still's size and type)"
    elif untyped:
        todo = f"lune run kit ui refs {identity} --tag {untyped[0]['file']}={kind}   (say what each still shows: hud | menu[:<screen>])"
    else:
        todo = (f"lune run kit ui refs {identity} \"<the game>\" \"<{want} words>\" --rank \"<what the screen shows>\"   "
                f"(>= 2 real {want} stills at >= 1080p: Steam appdetails / a wiki's File URLs / the owner's --drop)")
    return False, detail, todo
