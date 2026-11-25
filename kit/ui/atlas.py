"""atlas.py — an identity's small pieces packed into SHEETS (the pros' texture atlas): one upload, one texture to
stream, one draw batch for many little pictures (icons, words, digits, pips). The compiler points a piece's image at
its sheet with ImageRectOffset / ImageRectSize once the sheet is uploaded; the preview keeps drawing the piece itself.

    pack(out_dir, meta) -> {sheet_name: [piece, ...]}   (called by plates.py for every identity, every run)

A piece goes in when it is small (both sides <= MAX_SIDE), not 9-sliced (SliceCenter would not follow the rect) and not
a glint / sheet itself. Shelf packing, tallest first, PAD px of clear border around every piece (no bleeding at any
scale); sheets of SHEET x SHEET: atlas_0, atlas_1, ... Each piece's manifest entry gains "atlas": [sheet, x, y, w, h].
"""
import os

from PIL import Image

SHEET = 1024
MAX_SIDE = 256
PAD = 2


def candidates(meta):
    out = []
    for name, m in meta.items():
        if name.startswith("atlas_") or m.get("slice") or m.get("glint_of"):
            continue
        size = m.get("size")
        w, h = (size, size) if isinstance(size, (int, float)) else (tuple(size) if size else (None, None))
        if not w or not h or w > MAX_SIDE or h > MAX_SIDE:
            continue
        out.append((name, int(w), int(h)))
    return sorted(out, key=lambda t: (-t[2], -t[1], t[0]))


def place(items):
    """shelf packing: [(name, w, h)] -> {name: (sheet_index, x, y)}"""
    spots, sheet, x, y, shelf = {}, 0, PAD, PAD, 0
    for name, w, h in items:
        if x + w + PAD > SHEET:
            x, y, shelf = PAD, y + shelf + PAD, 0
        if y + h + PAD > SHEET:
            sheet, x, y, shelf = sheet + 1, PAD, PAD, 0
        spots[name] = (sheet, x, y)
        x += w + PAD
        shelf = max(shelf, h)
    return spots


def pack(out_dir, meta, held=()):
    """pack the identity's small pieces (already drawn in out_dir) into atlas sheets; adds them + each piece's rect to
    meta. A HELD piece (assets/ui/upload.hold.json) never goes in: a sheet is uploaded whole"""
    for f in os.listdir(out_dir) if os.path.isdir(out_dir) else []:
        if f.startswith("atlas_") and f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))  # (sheets are remade every run: a stale one must never be uploaded)
    items = [(n, w, h) for n, w, h in candidates(meta) if n not in held and os.path.isfile(os.path.join(out_dir, f"{n}.png"))]
    if len(items) < 2:
        return {}
    spots = place(items)
    sheets = {}
    for name, w, h in items:
        s, x, y = spots[name]
        sheets.setdefault(s, Image.new("RGBA", (SHEET, SHEET), (0, 0, 0, 0)))
        with Image.open(os.path.join(out_dir, f"{name}.png")) as im:
            sheets[s].alpha_composite(im.convert("RGBA").resize((w, h), Image.LANCZOS) if im.size != (w, h) else im.convert("RGBA"), (x, y))
        meta[name]["atlas"] = [f"atlas_{s}", x, y, w, h]
    made = {}
    for s, im in sheets.items():
        nm = f"atlas_{s}"
        im.save(os.path.join(out_dir, f"{nm}.png"))
        meta[nm] = {"size": SHEET, "slice": None, "file": True, "atlas_sheet": True}
        made[nm] = [n for n, _, _ in items if spots[n][0] == s]
    return made
