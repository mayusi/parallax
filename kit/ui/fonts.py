"""fonts.py — true type for the kit's UI preview: the real faces behind Roblox's Enum.Font, fetched (vetted, pinned)
from Google Fonts' repository, so a preview sheet shows the glyphs the player will see instead of Segoe UI.

    python kit/ui/fonts.py fetch [Family ...] [--ui assets/ui] [--models src/ui]   fetch the families the project's
                                                     screens use (specs + compiled models, so a skin's faces count too)
    python kit/ui/fonts.py status                    which families are cached, which are stand-ins, what is missing
    python kit/ui/fonts.py path <EnumFont>           the file + weight the preview uses for that Roblox font

kit/ui/fonts.json maps every Roblox Enum.Font to a family in github.com/google/fonts (its licence folder + family
folder), a weight, italic or not, and whether that family IS the engine's face (Michroma, Oswald, Fredoka...) or the
nearest free twin (Roblox's Gotham, Builder Sans, Bodoni, Garamond = the Guru face... have none): "approx": true.
Pins: kit/ui/fonts.lock.json (shipped with the kit, read-only here) + <cache>/fonts/fonts.lock.json (this machine's
first fetches) hold the sha256 + size of every file; a later fetch must match or it is refused. The licence is
checked FIRST (the family's METADATA.pb: OFL / Apache-2.0 / UFL only), before any font file is written. Font
files are data (TTF): FreeType rasterises them, nothing executes. A family whose pinned files are all present and
matching is not even listed again (no network). Cache: ~/.cache/roblox-kit/fonts/<family folder>/
(ROBLOX_KIT_CACHE overrides the root, as for the models).
"""

import hashlib
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "fonts.json")
LOCK = os.path.join(HERE, "fonts.lock.json")
REPO_RAW = "https://raw.githubusercontent.com/google/fonts/main"
REPO_API = "https://api.github.com/repos/google/fonts/contents"
ALLOWED_LICENCES = {"OFL", "APACHE2", "UFL"}
STATIC_WEIGHTS = {
    "Thin": 100, "ExtraLight": 200, "Light": 300, "Regular": 400, "Medium": 500, "SemiBold": 600,
    "Bold": 700, "ExtraBold": 800, "Black": 900,
}
META_FILES = ("METADATA.pb", "OFL.txt", "LICENSE.txt", "UFL.txt")


def cache_root():
    return os.environ.get("ROBLOX_KIT_CACHE") or os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit")


def fonts_dir():
    return os.path.join(cache_root(), "fonts")


def local_lock_path():
    return os.path.join(fonts_dir(), "fonts.lock.json")


def load_json(path, default):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
        fh.write("\n")


def manifest():
    return load_json(MANIFEST, {"families": {}, "fonts": {}})


def pins():
    """the kit's shipped pins win; this machine's first-fetch pins fill the rest"""
    merged = {}
    for src in (load_json(local_lock_path(), {}), load_json(LOCK, {})):
        for folder, files in src.items():
            merged.setdefault(folder, {}).update(files)
    return merged


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def family_of(enum_font):
    """Roblox Enum.Font name -> (family key, entry) or (None, None)."""
    m = manifest()
    entry = m["fonts"].get(enum_font)
    if not entry:
        return None, None
    return entry.get("family"), entry


def family_files(key):
    """the cached TTF files of a family: [(path, weight|None variable, italic)]"""
    m = manifest()
    fam = m["families"].get(key)
    if not fam:
        return []
    folder = os.path.join(fonts_dir(), fam["folder"])
    if not os.path.isdir(folder):
        return []
    out = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith((".ttf", ".otf")):
            continue
        base = os.path.splitext(name)[0]
        italic = "italic" in base.lower()
        if "[" in base:  # a variable font: one file, every weight
            out.append((os.path.join(folder, name), None, italic))
        else:
            style = base.split("-")[-1] if "-" in base else "Regular"
            style = style.replace("Italic", "") or "Regular"
            out.append((os.path.join(folder, name), STATIC_WEIGHTS.get(style, 400), italic))
    return out


def resolve(enum_font):
    """-> {path, weight, italic, variable, approx, family} for the preview, or None when nothing is cached."""
    key, entry = family_of(enum_font)
    if not entry:
        return None
    if entry.get("system"):
        for base in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/msttcorefonts", "/Library/Fonts"):
            p = os.path.join(base, entry["system"])
            if os.path.isfile(p):
                return {"path": p, "weight": entry.get("weight", 400), "italic": False, "variable": False,
                        "approx": False, "family": key}
        return None
    want_w, want_i = entry.get("weight", 400), bool(entry.get("italic"))
    files = family_files(key)
    if not files:
        return None
    same_italic = [f for f in files if f[2] == want_i] or files
    variable = [f for f in same_italic if f[1] is None]
    if variable:
        path = variable[0][0]
        return {"path": path, "weight": want_w, "italic": want_i, "variable": True,
                "approx": bool(entry.get("approx")), "family": key}
    best = min(same_italic, key=lambda f: abs((f[1] or 400) - want_w))
    return {"path": best[0], "weight": best[1], "italic": want_i, "variable": False,
            "approx": bool(entry.get("approx")), "family": key}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "roblox-kit-fonts/1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def _listing(fam):
    data = json.loads(_get(f"{REPO_API}/{fam['licence']}/{fam['folder']}").decode("utf-8"))
    return {e["name"]: e for e in data if e.get("type") == "file"}


def licence_of(text):
    for line in text.splitlines():
        if line.strip().startswith("license:"):
            return line.split(":", 1)[1].strip().strip('"')
    return None


def wanted_files(listing):
    """which TTFs to fetch from a family folder: the variable files, else the static Regular/Bold/Italic set"""
    ttf = [n for n in listing if n.lower().endswith(".ttf")]
    variable = [n for n in ttf if "[" in n]
    if variable:
        return variable
    keep = []
    for n in ttf:
        style = os.path.splitext(n)[0].split("-")[-1]
        if style in ("Regular", "Bold", "Italic", "BoldItalic", "Medium", "SemiBold", "Light", "Black", "ExtraBold"):
            keep.append(n)
    return keep or ttf[:2]


def _pinned_and_present(folder, pinned):
    """every pinned file of the family exists here with its pinned sha (so nothing to fetch, no network)"""
    fonts = [n for n in pinned if n.lower().endswith((".ttf", ".otf"))]
    if not fonts:
        return False
    for name, pin in pinned.items():
        p = os.path.join(folder, name)
        if not os.path.isfile(p) or sha256_of(p) != pin["sha256"]:
            return False
    return True


def _fetch_one(fam, name, listing, folder, pinned, report, key):
    """download one file of a family against its pin (or pin it); -> bytes written, or None when refused / offline"""
    dest = os.path.join(folder, name)
    if os.path.isfile(dest) and name in pinned and pinned[name]["sha256"] == sha256_of(dest):
        return b""
    url = f"{REPO_RAW}/{fam['licence']}/{fam['folder']}/{urllib.request.quote(name)}"
    try:
        data = _get(url)
    except Exception as e:  # a drop mid-fetch is reported, never a traceback
        report.append(f"{key}/{name}: cannot fetch ({e})")
        return None
    digest = hashlib.sha256(data).hexdigest()
    if name in pinned and pinned[name]["sha256"] != digest:
        report.append(f"{key}/{name}: REFUSED — sha256 {digest[:12]} != pinned {pinned[name]['sha256'][:12]}")
        return None
    size = listing.get(name, {}).get("size")
    if size not in (None, len(data)):
        report.append(f"{key}/{name}: REFUSED — {len(data)} B != the listing's {size} B")
        return None
    with open(dest, "wb") as fh:
        fh.write(data)
    pinned[name] = {"sha256": digest, "size": len(data)}
    return data


def fetch_family(key, local_lock, report):
    m = manifest()
    fam = m["families"].get(key)
    if not fam:
        report.append(f"{key}: not in fonts.json")
        return False
    folder = os.path.join(fonts_dir(), fam["folder"])
    os.makedirs(folder, exist_ok=True)
    pinned = dict(pins().get(fam["folder"], {}))
    if _pinned_and_present(folder, pinned):
        return True
    try:
        listing = _listing(fam)
    except Exception as e:  # offline: use what is cached
        if family_files(key):
            report.append(f"{key}: offline, using the cached files")
            return True
        report.append(f"{key}: cannot list {fam['licence']}/{fam['folder']} ({e})")
        return False
    # the licence FIRST: METADATA.pb says what the family is published under; nothing else is written before
    if "METADATA.pb" not in listing:
        report.append(f"{key}: licence unknown (no METADATA.pb in the family folder) — not fetched")
        return False
    meta = _fetch_one(fam, "METADATA.pb", listing, folder, pinned, report, key)
    if meta is None:
        return False
    meta_text = meta.decode("utf-8", "replace") if meta else open(os.path.join(folder, "METADATA.pb"), encoding="utf-8", errors="replace").read()
    lic = licence_of(meta_text)
    if lic not in ALLOWED_LICENCES:
        report.append(f"{key}: licence {lic} is not OFL / Apache-2.0 / UFL — not fetched")
        os.remove(os.path.join(folder, "METADATA.pb"))
        return False
    names = wanted_files(listing) + [n for n in META_FILES if n in listing and n != "METADATA.pb"]
    for name in names:
        if _fetch_one(fam, name, listing, folder, pinned, report, key) is None:
            return False
    local_lock[fam["folder"]] = pinned
    return True


def families_in_use(ui_dir, models_dir=None):
    """the Roblox fonts the project's screens name (specs + identities) and the faces its compiled models carry
    (a skin's own faces appear only there) -> family keys"""
    m = manifest()
    used = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("font", "titleFont", "monoFont", "bodyFont", "Font") and isinstance(v, str) and v in m["fonts"]:
                    used.add(m["fonts"][v]["family"])
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for base in (ui_dir, models_dir):
        if not base or not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for f in files:
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(root, f), encoding="utf-8") as fh:
                            walk(json.load(fh))
                    except (OSError, ValueError):
                        pass
    if "GothamMedium" in m["fonts"]:  # the compiler's fallback face
        used.add(m["fonts"]["GothamMedium"]["family"])
    return sorted(k for k in used if k and not m["families"].get(k, {}).get("system"))


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def main(argv):
    if not argv:
        return emit("fail", "fonts: usage: fetch [Family ...] [--ui dir] [--models dir] | status | path <EnumFont>",
                    "python kit/ui/fonts.py status")
    cmd = argv[0]
    m = manifest()
    if cmd == "path":
        r = resolve(argv[1]) if len(argv) > 1 else None
        return emit("pass" if r else "fail", json.dumps(r) if r else f"{argv[1:]}: nothing cached",
                    "none" if r else "python kit/ui/fonts.py fetch")
    if cmd == "status":
        cached, missing, approx = [], [], []
        for key, fam in m["families"].items():
            if fam.get("system"):
                continue
            (cached if family_files(key) else missing).append(key)
        for name, e in m["fonts"].items():
            if e.get("approx"):
                approx.append(name)
        return emit("pass", f"{len(cached)} families cached, {len(missing)} not fetched; {len(approx)} Roblox fonts drawn "
                    f"with a stand-in (no free twin): {', '.join(sorted(approx)[:8])}...",
                    f"python kit/ui/fonts.py fetch {' '.join(missing[:6])}" if missing else "none", cached=cached, missing=missing)
    if cmd == "fetch":
        keys = list(argv[1:])
        ui_dir, models_dir = None, None
        for flag in ("--ui", "--models"):
            if flag in keys:
                i = keys.index(flag)
                val = keys[i + 1] if i + 1 < len(keys) else None
                keys = keys[:i] + keys[i + 2:]
                if flag == "--ui":
                    ui_dir = val
                else:
                    models_dir = val
        if not keys:
            keys = families_in_use(ui_dir or "assets/ui", models_dir or "src/ui")
        local_lock = load_json(local_lock_path(), {})
        report, done = [], []
        for key in keys:
            if fetch_family(key, local_lock, report):
                done.append(key)
        save_json(local_lock_path(), local_lock)
        bad = [r for r in report if "REFUSED" in r or "not in" in r or "licence" in r]
        offline = [r for r in report if "cannot" in r or "offline" in r]
        return emit("fail" if bad else "pass",
                    f"{len(done)} famil{'y' if len(done) == 1 else 'ies'} ready ({', '.join(done)})"
                    + (f"; {len(bad)} problem(s)" if bad else "") + (f"; {len(offline)} not fetched (offline?)" if offline else ""),
                    bad[0] if bad else (offline[0] + " — the preview draws a system face for it until fetched" if offline else "none — the preview draws these faces now"),
                    report=report)
    return emit("fail", f"fonts: unknown command {cmd}", "python kit/ui/fonts.py status")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
