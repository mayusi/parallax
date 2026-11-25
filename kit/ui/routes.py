"""routes.py — the PIECE ROUTE of every picture a screen shows: how it was made (trace / letter / ink / render / smear
/ digits / spin / icon / plate / concept / drawn / typed / unknown), read from its sidecar or its PROVENANCE.md row,
and the route's standing from kit/ui/routes.json (golden / ok / caution / graveyard: the owner's record on it).

Used by kit/ui/plan.py (the pieces stage names each piece's route and stops a hero piece on a graveyard route) and
kit/ui/vault.py (library/ui/ROUTES.md: the table + how many pieces each route made).

    python kit/ui/routes.py <Screen> [--specs assets/ui]        the screen's pieces by route
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SIDECARS = (("render.json", "render"), ("anchors.json", "render"), ("trace.json", "trace"), ("ink.json", "ink"),
            ("letter.json", "letter"), ("smear.json", "smear"), ("spin.json", "spin"))
PLATES = {"frame", "frame_line", "slot", "cap", "track", "divider", "band", "vignette", "grain", "highlight", "keycap", "glow", "ornament",
          "corner", "arrow", "ring", "ribbon", "bubble", "pill", "badge", "card", "banner", "track_chunky", "gloss", "burst", "close", "plus",
          "slant", "check", "torn", "torn_b", "torn_c", "torn_field", "torn_black", "halftone", "dots", "rays", "chevron"}


def table(path=None):
    with open(path or os.path.join(HERE, "routes.json"), encoding="utf-8") as fh:
        return json.load(fh)["routes"]


def _provenance(art_dir):
    sys.path.insert(0, HERE)
    import vault  # noqa: E402  (one PROVENANCE.md reader for the kit)
    return vault.provenance(art_dir)


def route_of(ident, piece, art_root, prov=None):
    """(route, why) for art:<ident>/<piece>"""
    d = os.path.join(art_root, ident)
    for ext, route in SIDECARS:
        if os.path.isfile(os.path.join(d, f"{piece}.{ext}")):
            if route == "ink":
                try:
                    mode = json.load(open(os.path.join(d, f"{piece}.{ext}"), encoding="utf-8")).get("mode")
                except Exception:  # noqa: BLE001
                    mode = None
                return "ink", f"{piece}.{ext}" + (f" (--mode {mode})" if mode else "")
            return route, f"{piece}.{ext}"
    m = re.match(r"^(.+)_([A-Za-z0-9]|u\d+)$", piece)
    if m and os.path.isfile(os.path.join(d, f"{m.group(1)}.glyphs.json")):
        return "digits", f"{m.group(1)}.glyphs.json"
    m = re.match(r"^(.+)_spin_(?:f\d+|sheet)$", piece)
    if m and os.path.isfile(os.path.join(d, f"{m.group(1)}_spin.spin.json")):
        return "spin", f"{m.group(1)}_spin.spin.json"
    if piece.endswith("_figure") and os.path.isfile(os.path.join(d, f"{piece[:-7]}.smear.json")):
        return "smear", f"{piece[:-7]}.smear.json"
    if piece.endswith("_cell") and os.path.isfile(os.path.join(d, f"{piece[:-5]}.trace.json")):
        return "trace", f"{piece[:-5]}.trace.json"
    prov = _provenance(d) if prov is None else prov
    row = prov.get(piece) or prov.get(re.sub(r"^(icon|backdrop)_", "", piece))
    if row:
        if re.search(r"game-icons|CC BY", row, re.I):
            return "icon", row[:80]
        if re.search(r"\b(flux|concept|generated|prompt)\b", row, re.I):
            return "concept", row[:80]
        # the file's intro may name the generator for its whole table (the sim pack: "FLUX.2 klein 4B via kit vision
        # concept" above a | file | subject | seed | table)
        pf = os.path.join(d, "PROVENANCE.md")
        head = ""
        if os.path.isfile(pf):
            with open(pf, encoding="utf-8", errors="replace") as fh:
                head = fh.read().split("|", 1)[0]
        if re.search(r"\b(flux|kit vision concept)\b", head, re.I):
            return "concept", f"{row[:60]} (PROVENANCE.md: a generator)"
        return "drawn", row[:80]
    # a STORED picture with no source is unknown, whatever its name (an unsourced badge_crest is not a plate); plates
    # are drawn at build time and live only in build/ui/art
    if os.path.isfile(os.path.join(d, f"{piece}.png")):
        return "unknown", "no sidecar, no PROVENANCE.md row"
    base = re.sub(r"_(accent|focus|good|danger|panel|r|l|\d+)$", "", piece)
    if piece in PLATES or base in PLATES or base.split("_")[0] in PLATES:
        return "plate", "the identity's shape language (kit ui plates)"
    return "unknown", "no sidecar, no PROVENANCE.md row"


def pieces_of(spec):
    """every art:<identity>/<piece> a spec shows, and every lettered word (art:<identity>/w_<slug>), with node paths"""
    ident = spec.get("identity")
    out = []

    def walk(n, path):
        if not isinstance(n, dict):
            return
        p = f"{path}.{n.get('name', '?')}" if path else str(n.get("name", "?"))
        for k in ("image", "art", "plate"):
            v = n.get(k)
            if isinstance(v, str) and v.startswith("art:") and "/" in v:
                idn, piece = v[4:].split("/", 1)
                out.append((p, idn, piece))
        if n.get("lettering") not in (None, False) and isinstance(n.get("text"), str) and ident:
            nm = n["lettering"].get("name") if isinstance(n["lettering"], dict) else None
            out.append((p, ident, nm or ("w_" + (re.sub(r"[^a-z0-9]+", "_", n["text"].lower()).strip("_")[:40] or "word"))))
        if n.get("type") == "number" and isinstance(n.get("digits"), str) and "/" in n["digits"]:
            idn, piece = n["digits"].split("/", 1)
            out.append((p, idn, f"{piece}_0"))
        if n.get("type") in ("label", "button") and isinstance(n.get("text"), str) and n.get("text").strip() and n.get("lettering") in (None, False):
            out.append((p, None, None))  # a typed text
        for c in n.get("children") or []:
            walk(c, p)
    walk(spec.get("root"), "")
    return out


def screen_routes(spec, art_root):
    """[(node path, piece or None, route, why)] for one spec"""
    provs = {}
    rows = []
    for path, idn, piece in pieces_of(spec):
        if piece is None:
            rows.append((path, None, "typed", "a font glyph"))
            continue
        if idn not in provs:
            provs[idn] = _provenance(os.path.join(art_root, idn))
        r, why = route_of(idn, piece, art_root, provs[idn])
        rows.append((path, f"{idn}/{piece}", r, why))
    return rows


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("screen")
    ap.add_argument("--specs", default="assets/ui")
    a = ap.parse_args()
    p = os.path.join(a.specs, f"{a.screen}.json")
    if not os.path.isfile(p):
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"routes: no {p}", "next_action": "name a screen in assets/ui"}))
        return 1
    spec = json.load(open(p, encoding="utf-8"))
    tab = table()
    rows = screen_routes(spec, os.path.join(a.specs, "art"))
    counts = {}
    for path, piece, r, why in rows:
        counts[r] = counts.get(r, 0) + 1
        print(f"  {r:8s} [{tab.get(r, {}).get('status', '?'):9s}] {path}  {piece or ''}  ({why})")
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"routes {a.screen}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])),
                      "next_action": f"lune run kit ui plan {a.screen}", "counts": counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
