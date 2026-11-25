"""icon.py — free ICONS for UI pieces: the game-icons.net set (4,239 SVGs, CC BY 3.0; vetted 2026-10-14, VETLOG; cached at
~/.cache/roblox-kit/icons/game-icons), found by name and made into styled pieces in an identity's colours.

    python kit/ui/icon.py find "<words>" [--top 12]
    python kit/ui/icon.py make <identity>/<piece> --icon <name | author/name> [--fill #hex] [--ink #hex] [--outline 6]
        [--glow #hex] [--size 512] [--art assets/ui/art]

make: the SVG (its black background square removed) rendered by Blender as a crisp mask (kit/ui/icon_blender.py), then
styled here: the fill, an ink outline `outline` px wide, an optional soft glow. Writes <piece>.png + <piece>.icon.json and
the CC BY credit into the identity's PROVENANCE.md (the licence asks for it). A 3D version: kit ui spin <identity>/<piece>.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageChops, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
_KIT = os.path.abspath(os.path.join(HERE, ".."))
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
from blender_path import find_blender  # noqa: E402

ICONS = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "icons", "game-icons")
AUTHORS = {"lorc": "Lorc", "delapouite": "Delapouite", "john-colburn": "John Colburn", "felbrigg": "Felbrigg", "john-redman": "John Redman",
           "carl-olsen": "Carl Olsen", "sbed": "Sbed", "priorblue": "PriorBlue", "willdabeast": "Willdabeast", "viscious-speed": "Viscious Speed",
           "lord-berandas": "Lord Berandas", "irongamer": "Irongamer", "heavenly-dog": "HeavenlyDog", "lucasms": "Lucas", "faithtoken": "Faithtoken",
           "skoll": "Skoll", "andymeneely": "Andy Meneely", "cathelineau": "Cathelineau", "darkzaitzev": "DarkZaitzev", "guard13007": "Guard13007",
           "spencerdub": "SpencerDub", "zeromancer": "Zeromancer", "sparker": "Sparker"}
CC0 = {"viscious-speed"}  # (the licence file marks these authors CC0)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def index():
    out = []
    if not os.path.isdir(ICONS):
        return out
    for author in sorted(os.listdir(ICONS)):
        d = os.path.join(ICONS, author)
        if os.path.isdir(d):
            out += [(author, f[:-4]) for f in os.listdir(d) if f.endswith(".svg")]
    return out


def find(words, top=12):
    """icons by NAME: every query word found in the name's words scores 2, a word found inside a name word 1"""
    q = [w for w in re.findall(r"[a-z0-9]+", words.lower()) if len(w) > 1]
    scored = []
    for author, name in index():
        parts = name.split("-")
        s = sum(2 if w in parts else 1 if any(w in p for p in parts) else 0 for w in q)
        if s:
            scored.append((-s, len(parts), author, name))
    scored.sort()  # (best score first, then the shortest name, then A-Z: ties no longer drop the a-k names)
    return [(a, n) for _s, _l, a, n in scored[:top]]


def locate(icon):
    if "/" in icon:
        author, name = icon.split("/", 1)
        p = os.path.join(ICONS, author, name + ".svg")
        return (author, name, p) if os.path.isfile(p) else None
    # a bare name: an artist's icon first — the "badges" set (another page size, a black disc behind the glyph) sorted
    # first and crown / shield / coins / fire came out as white discs (audit 2026-10-16); "badges/<name>" still asks for it
    hits = [(author, name) for author, name in index() if name == icon]
    hits.sort(key=lambda an: an[0] == "badges")
    if hits:
        author, name = hits[0]
        return author, name, os.path.join(ICONS, author, name + ".svg")
    return None


def blender():
    return find_blender()


def style(mask, fill, ink=None, outline=0, glow=None):
    """the mask's alpha -> a piece: the fill colour, an ink rim `outline` px outside it, a soft glow under all"""
    a = mask.getchannel("A")
    size = mask.size
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    if glow:
        g = a.filter(ImageFilter.MaxFilter(max(3, (outline * 2 + 1) | 1))).filter(ImageFilter.GaussianBlur(max(6, size[0] // 40)))
        layer = Image.new("RGBA", size, glow)
        layer.putalpha(g.point(lambda v: int(v * 0.85)))
        out.alpha_composite(layer)
    if ink and outline > 0:
        k = outline * 2 + 1
        rim = a.filter(ImageFilter.MaxFilter(k if k % 2 else k + 1))
        layer = Image.new("RGBA", size, ink)
        layer.putalpha(rim)
        out.alpha_composite(layer)
    face = Image.new("RGBA", size, fill)
    face.putalpha(a)
    out.alpha_composite(face)
    return out


def hexrgb(h):
    """#rgb or #rrggbb -> RGBA; ValueError (reported as a verdict) for anything else"""
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
        raise ValueError(f"not a colour: #{h} (use #rrggbb)")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


def credit_line(author, name, piece):
    who = AUTHORS.get(author, author.replace("-", " ").title())
    lic = "CC0" if author in CC0 else "CC BY 3.0"
    return f"| {piece} | game-icons.net '{name}' by {who} ({lic}; game-icons/icons @ 82d9488), styled by kit ui icon |"


def write_credit(prov, ident, piece, line):
    """the CC BY credit for `piece`, REPLACING any older row for it (a piece remade from another icon, or a piece that
    was generated art before, must carry the credit of what it is now), padded to the file's own column count"""
    text = open(prov, encoding="utf-8").read() if os.path.isfile(prov) else f"# {ident} — provenance\n\n| piece | what it is |\n|---|---|\n"
    lines = text.splitlines()
    header = next((ln for ln in lines if ln.startswith("|") and "---" not in ln), "| piece | what it is |")
    cols = max(2, header.count("|") - 1)
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    cells += [""] * (cols - len(cells))
    row = "| " + " | ".join(cells[:cols]) + " |"
    kept = [ln for ln in lines if not ln.startswith(f"| {piece} |")]
    with open(prov, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(kept + [row]) + "\n")


def cmd_make(a):
    if "/" not in a.target:
        return emit("fail", "icon: name the piece as <identity>/<piece>", "lune run kit ui icon make strive/ic_swords --icon crossed-swords")
    ident, piece = a.target.split("/", 1)
    hit = locate(a.icon)
    if not hit:
        sug = ", ".join(f"{x}/{y}" for x, y in find(a.icon, 5))
        return emit("fail", f"icon: no icon '{a.icon}'" + (f" (close: {sug})" if sug else ""), "lune run kit ui icon find \"<words>\"")
    author, name, svg = hit
    exe = blender()
    if not exe:
        return emit("fail", "icon: Blender not found", "lune run kit doctor")
    t0 = time.time()
    work = os.path.join(ROOT, "build", "ui", "icons")
    os.makedirs(work, exist_ok=True)
    clean = os.path.join(work, f"{author}_{name}.svg")
    s = open(svg, encoding="utf-8").read()
    s = re.sub(r'<path d="M0 0h512v512H0z"\s*/>', "", s)  # (the black background square every icon carries)
    open(clean, "w", encoding="utf-8").write(s)
    mask_path = os.path.join(work, f"{author}_{name}_{a.size}.png")
    r = subprocess.run([exe, "-b", "--factory-startup", "--python-exit-code", "2", "-P", os.path.join(HERE, "icon_blender.py"), "--",
                        "--svg", clean, "--out", mask_path, "--size", str(a.size)], capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0 or "ICON_DONE" not in r.stdout:
        return emit("fail", f"icon: Blender failed: {(r.stdout + r.stderr)[-300:]}", "read the Blender output above")
    mask = Image.open(mask_path).convert("RGBA")
    pad = a.outline + 4 * max(6, a.size // 40) if a.glow else a.outline  # (the glow reaches ~3-4 blur radii past the rim)
    if pad:
        big = Image.new("RGBA", (a.size + 2 * pad, a.size + 2 * pad), (0, 0, 0, 0))
        big.paste(mask, (pad, pad))
        mask = big
    try:
        piece_img = style(mask, hexrgb(a.fill), hexrgb(a.ink) if a.ink else None, a.outline, hexrgb(a.glow) if a.glow else None)
    except ValueError as err:
        return emit("fail", f"icon: {err}", "pass colours as #rrggbb")
    d = os.path.join(a.art, ident)
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, f"{piece}.png")
    piece_img.save(out)
    side = {"schema": 1, "kind": "icon", "source": f"game-icons.net/{author}/{name}", "licence": "CC0" if author in CC0 else "CC BY 3.0",
            "author": AUTHORS.get(author, author), "fill": a.fill, "ink": a.ink, "outline": a.outline, "glow": a.glow, "size": list(piece_img.size),
            "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(os.path.join(d, f"{piece}.icon.json"), "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump(side, fh, indent=1)
    write_credit(os.path.join(d, "PROVENANCE.md"), ident, piece, credit_line(author, name, piece))
    return emit("pass", f"icon: {ident}/{piece} <- game-icons '{name}' by {AUTHORS.get(author, author)} ({side['licence']}, credited in PROVENANCE) "
                f"{piece_img.size[0]} px ({time.time() - t0:.0f}s)",
                f"use it as art:{ident}/{piece}; in 3D: lune run kit ui spin {ident}/{piece}", piece=out)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["find", "make"])
    ap.add_argument("target", nargs="+", help="find: the words (quotes optional); make: <identity>/<piece>")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--icon", default=None)
    ap.add_argument("--fill", default="#ffffff")
    ap.add_argument("--ink", default="#000000")
    ap.add_argument("--outline", type=int, default=6)
    ap.add_argument("--glow", default=None)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--art", default="assets/ui/art")
    ap.add_argument("--ui", default="assets/ui")  # (passed by the CLI; unused)
    a = ap.parse_args(argv)
    a.target = " ".join(a.target) if a.cmd == "find" else a.target[0]
    if not os.path.isdir(ICONS):
        return emit("fail", f"icon: the icon set is not in {ICONS}", "it is vetted (VETLOG 2026-10-14): fetch game-icons/icons @ 82d9488 there")
    if a.cmd == "find":
        hits = find(a.target, a.top)
        if not hits:
            return emit("fail", f"icon: nothing named like '{a.target}' in {len(index())} icons", "try other words (sword, skull, heart, shield...)")
        return emit("pass", f"icon: {len(hits)} for '{a.target}': " + ", ".join(f"{x}/{y}" for x, y in hits),
                    f"lune run kit ui icon make <identity>/<piece> --icon {hits[0][0]}/{hits[0][1]}", icons=[f"{x}/{y}" for x, y in hits])
    if not a.icon:
        return emit("fail", "icon make needs --icon <name>", "lune run kit ui icon find \"<words>\"")
    return cmd_make(a)


if __name__ == "__main__":
    sys.exit(main())
