"""font.py — a BITMAP FONT for any text: Roblox cannot upload a font, so player names, item names and dialogue fall back
to the engine's faces. This letters the whole printable alphabet in the identity's lettering (kit/ui/letter.py, its
style flags: fill, ink, outline, shadow, glow, widen, ...) and measures it, so the compiler and Ui.write can set ANY
text proportionally in that face — kerned, wrapped, aligned.

    python kit/ui/font.py <identity>/<set> --font <pinned face> [--size 120] [letter style flags...]

-> assets/ui/art/<identity>/<set>_<code>.png (one per glyph, letter's glyph-set cells: one baseline, one cell) +
   <set>.font.json: {"chars", "cell": [w, h], "ink": {code: [left, width]} (shares of the cell WIDTH), "space",
   "track", "kern": {"AV": k} (shares of the cell HEIGHT, from the face's own kerning)}
The atlas packs the glyphs into sheets (95 pictures, one or two uploads). A label uses it with "glyphs": "<identity>/<set>".
"""
import importlib.util
import json
import os
import sys

from PIL import Image, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_letter_for_font", os.path.join(HERE, "letter.py"))
letter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(letter)

CHARS = "".join(chr(c) for c in range(33, 127))  # printable ASCII without the space (the space is an advance, not a picture)
KERN_SET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,'"


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def measure(art_dir, ident, piece, chars):
    """each glyph's ink inside its cell: (left, width) as shares of the cell width"""
    ink, cell = {}, None
    for ch in chars:
        code = letter.glyph_code(ch)
        path = os.path.join(art_dir, ident, f"{piece}_{code}.png")
        if not os.path.isfile(path):
            continue
        with Image.open(path) as im:
            cell = im.size
            box = im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
        if box:
            ink[code] = [round(box[0] / cell[0], 4), round((box[2] - box[0]) / cell[0], 4)]
    return ink, cell


def kerning(face, size):
    """the face's OWN kerning for the pairs text meets (shares of the em): the 'kern' table, else GPOS pair adjustments
    (format 1 pairs and format 2 classes) — read with fontTools (PIL's basic layout applies none)"""
    path = letter.font_file(face)
    if not path:
        return {}
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return {}
    font = TTFont(path, lazy=True)
    upem = font["head"].unitsPerEm
    cmap = font.getBestCmap() or {}
    name_of = {ch: cmap.get(ord(ch)) for ch in KERN_SET}
    want = {n: ch for ch, n in name_of.items() if n}
    out = {}

    def put(ga, gb, v):
        a, b = want.get(ga), want.get(gb)
        if a and b and v and abs(v) / upem >= 0.01:
            out.setdefault(a + b, round(v / upem, 4))

    if "kern" in font:
        for sub in font["kern"].kernTables:
            for (ga, gb), v in getattr(sub, "kernTable", {}).items():
                put(ga, gb, v)
    if "GPOS" in font and font["GPOS"].table.LookupList:
        for lookup in font["GPOS"].table.LookupList.Lookup:
            subs = lookup.SubTable
            if lookup.LookupType == 9:  # (extension: unwrap)
                subs = [st.ExtSubTable for st in subs]
            for st in subs:
                if getattr(st, "LookupType", 2) != 2 and lookup.LookupType != 9:
                    continue
                cov = st.Coverage.glyphs if hasattr(st, "Coverage") else []
                if st.Format == 1:
                    for ga, ps in zip(cov, st.PairSet):
                        for rec in ps.PairValueRecord:
                            v = getattr(rec.Value1, "XAdvance", 0) if rec.Value1 else 0
                            put(ga, rec.SecondGlyph, v)
                elif st.Format == 2:
                    c1 = st.ClassDef1.classDefs if st.ClassDef1 else {}
                    c2 = st.ClassDef2.classDefs if st.ClassDef2 else {}
                    for ga in cov:
                        if ga not in want:
                            continue
                        row = st.Class1Record[c1.get(ga, 0)]
                        for gb in want:
                            rec = row.Class2Record[c2.get(gb, 0)]
                            v = getattr(rec.Value1, "XAdvance", 0) if rec.Value1 else 0
                            put(ga, gb, v)
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or "/" not in argv[0]:
        return emit("fail", "font: <identity>/<set> --font <face> [letter flags]", "python kit/ui/font.py riff/body --font bangers")
    target = argv[0]
    ident, piece = target.split("/", 1)
    rest = argv[1:]
    face = rest[rest.index("--font") + 1] if "--font" in rest else None
    if not face or not letter.font_file(face):
        return emit("fail", f"font: no pinned face '{face}'", "lune run kit ui fonts fetch (kit/ui/fonts.json lists the families)")
    size = int(rest[rest.index("--size") + 1]) if "--size" in rest else 120
    art_dir = rest[rest.index("--art") + 1] if "--art" in rest else os.path.join("assets", "ui", "art")
    flags = [x for x in rest]
    if "--size" not in flags:
        flags += ["--size", str(size)]
    rc = letter.main([target, "--text", "A", "--case-codes", "--glyphs", CHARS, "--shadow", "0", "--lean", "0"] + flags) if "--shadow" not in flags and "--lean" not in flags \
        else letter.main([target, "--text", "A", "--case-codes", "--glyphs", CHARS] + flags)
    if rc not in (0, None):
        return emit("fail", f"font: lettering {target} failed", "read the letter error above")
    letter.CASE_CODES = True  # (measure the same file names the glyph set wrote)
    ink, cell = measure(art_dir, ident, piece, CHARS)
    if not cell or len(ink) < 60:
        return emit("fail", f"font: only {len(ink)} glyphs measured", "check the face covers ASCII")
    f = ImageFont.truetype(letter.font_file(face), size)
    space = round(f.getlength(" ") / size, 4)
    meta = {"schema": 1, "kind": "font", "set": target, "face": face, "chars": CHARS, "cell": list(cell), "size": size,
            "codes": {ch: letter.glyph_code(ch) for ch in CHARS},
            "ink": ink, "space": max(space, 0.22), "track": 0.05, "kern": kerning(face, size)}
    out = os.path.join(art_dir, ident, f"{piece}.font.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(meta, fh, indent=1)
    return emit("pass", f"font: {target} - {len(ink)} glyphs in a {cell[0]}x{cell[1]} cell, {len(meta['kern'])} kerning pairs -> {out}",
                f'use it: {{"type": "label", "glyphs": "{target}", "text": "...", "size": [w, h]}} (lune run kit ui; kit upload --only {piece}_)')


if __name__ == "__main__":
    sys.exit(main())
