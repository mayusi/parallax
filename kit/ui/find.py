"""find.py — the piece bank: every proven UI piece across identities and the example library, found by words,
with how it was made — so a new screen starts from proven art before any generator is asked.

    python kit/ui/find.py "<words>" [--art assets/ui/art] [--starter kit/starter/ui/art] [--max 12]

A piece = a PNG in assets/ui/art/<identity>/ or kit/starter/ui/art/<identity>/, scored by its name, its sidecar
(.render.json "about", .ink.json "from", .trace.json "from") and its PROVENANCE.md row. Prints the best matches as
`art:<identity>/<piece>` with the source and the size.
"""
import argparse
import glob
import json
import os
import re
import sys

from PIL import Image


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def provenance_rows(folder):
    rows = {}
    p = os.path.join(folder, "PROVENANCE.md")
    if os.path.isfile(p):
        for line in open(p, encoding="utf-8", errors="replace"):
            m = re.match(r"\|\s*([^|]+?)\s*\|\s*(.+?)\s*\|", line)
            if m and m.group(1).lower() not in ("file", "---"):
                for name in re.split(r"[,/]\s*", m.group(1)):
                    rows[name.strip().replace("`", "")] = m.group(2).strip()
    return rows


def pieces(root, sub=""):
    """root/<identity>/[sub/]<piece>.png — the live art (sub ""), or the vault's saved pieces (sub "pieces")"""
    out = []
    for ident_dir in sorted(glob.glob(os.path.join(root, "*"))):
        if not os.path.isdir(ident_dir):
            continue
        ident = os.path.basename(ident_dir)
        if sub:
            ident_dir = os.path.join(ident_dir, sub)
            if not os.path.isdir(ident_dir):
                continue
        rows = provenance_rows(ident_dir)
        for png in sorted(glob.glob(os.path.join(ident_dir, "*.png"))):
            name = os.path.splitext(os.path.basename(png))[0]
            if name.endswith("_cell") or name == "world":
                continue
            about = ""
            source = "unknown"
            for ext, kind in (("render.json", "render"), ("ink.json", "ink"), ("trace.json", "trace"), ("letter.json", "letter"), ("smear.json", "smear"), ("spin.json", "spin")):
                sp = os.path.join(ident_dir, f"{name}.{ext}")
                if os.path.isfile(sp):
                    try:
                        side = json.load(open(sp, encoding="utf-8"))
                    except Exception:  # noqa: BLE001
                        side = {}
                    source = f"{kind}: " + (side.get("about") or side.get("from") or "")
                    about = side.get("about", "") or side.get("from", "")
                    break
            if source == "unknown":
                # one resolver for every provenance form (table rows, ## sections, traced cells): the vault's
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import vault as V
                # (from the art root being searched — the active game's, not always the root project's: audit
                # 2026-10-16; its build art sits at <project>/build/ui/art beside <project>/assets/ui/art)
                if sub:
                    found = V.provenance(ident_dir).get(name) or "unknown"
                else:
                    built = os.path.normpath(os.path.join(root, "..", "..", "..", "build", "ui", "art"))
                    found = V.source_of(ident, name, root, built)
                if not found.startswith("unknown"):
                    source = found[:160]
                    about = found
            out.append({"identity": ident, "piece": name, "path": png, "about": about, "source": source})
    return out


def score(piece, words):
    hay = f"{piece['piece']} {piece['about']} {piece['identity']}".lower()
    s = 0
    for w in words:
        if w in piece["piece"].lower():
            s += 3
        if w in hay:
            s += 1
    return s


def main():
    try:
        import sys
        sys.stdout.reconfigure(encoding="utf-8")  # (Windows consoles default to cp1252; the kit reads utf-8)
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("words")
    ap.add_argument("--art", default="assets/ui/art")
    ap.add_argument("--starter", default="kit/starter/ui/art")
    ap.add_argument("--max", type=int, default=12)
    ap.add_argument("--vault", default="library/ui", help="the UI library: every piece ever made, even retired ones")
    a = ap.parse_args()
    words = [w for w in re.split(r"[\s,]+", a.words.lower()) if w]
    seen = set()
    found = []
    for root, sub in ((a.art, ""), (a.starter, ""), (a.vault, "pieces")):
        if os.path.isdir(root):
            for p in pieces(root, sub):
                key = (p["identity"], p["piece"])
                if key in seen:
                    continue
                seen.add(key)
                sc = score(p, words)
                if sc > 0:
                    try:
                        p["size"] = list(Image.open(p["path"]).size)
                    except Exception:  # noqa: BLE001
                        p["size"] = None
                    p["score"] = sc
                    found.append(p)
    found.sort(key=lambda p: (-p["score"], p["identity"], p["piece"]))
    found = found[: a.max]
    for p in found:
        print(f"  art:{p['identity']}/{p['piece']}  {p['size']}  — {p['source'][:120]}")
    if not found:
        return emit("fail", f"find: no proven piece matches '{a.words}'", "make it by the hero route (a real picture: kit ui ink; a logotype: kit ui render; a replica: kit ui trace) and give it a provenance row")
    best = found[0]
    return emit("pass", f"find: {len(found)} piece(s) for '{a.words}' — best art:{best['identity']}/{best['piece']} ({best['source'][:80]})",
                f"reuse it: copy assets/ui/art/{best['identity']}/{best['piece']}.png (+ its sidecar) into your identity's art folder, or reference the identity's own", found=found)


if __name__ == "__main__":
    raise SystemExit(main())
