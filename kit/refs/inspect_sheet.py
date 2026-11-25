"""inspect_sheet.py — the labelled sheets of a reference model's inspection (system python + PIL; Blender has none).

    python kit/refs/inspect_sheet.py refs/<name>.inspect.json

  -> build/library/<name>/parts_sheet.png   every part alone, numbered: name, its own size (mm), kind, through-holes,
     a swatch of its material colour with its metal / roughness
  -> build/library/<name>/part_<part>_sheet.png   (inspect --part) the part from four sides on a 10 mm grid
Prints one JSON line: {status, summary, next_action, rows} — rows = one line per part for the console.
"""

import json
import os
import sys

from collections import deque

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blender"))
import labels  # noqa: E402  (the kit's font + safe save)

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BG, STRIP, INK, DIM = (124, 126, 132), (38, 40, 46), (236, 236, 240), (170, 172, 180)


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) if h and len(h) == 7 else None


def _mm(v):
    return "x".join(f"{x:.0f}" if x >= 10 else f"{x:.1f}" for x in v)


def openings(tile_png, mm_per_px, min_px=6):
    """the openings you can SEE THROUGH a part from its broadest side (a pin hole, a guard's opening, a window): the
    see-through pixels its outline encloses — from the picture, so an open game mesh (holes: null) still has them.
    -> [{d_mm (as round), w_mm, h_mm, at_mm: [x right, y up] from the picture's centre}], biggest first"""
    a = np.asarray(Image.open(tile_png).convert("RGBA"))[:, :, 3] < 128
    h, w = a.shape
    reach = np.zeros_like(a)
    reach[0, :], reach[-1, :], reach[:, 0], reach[:, -1] = a[0, :], a[-1, :], a[:, 0], a[:, -1]
    while True:  # see-through pixels joined to the border: outside, not an opening
        grow = reach.copy()
        grow[1:, :] |= reach[:-1, :]
        grow[:-1, :] |= reach[1:, :]
        grow[:, 1:] |= reach[:, :-1]
        grow[:, :-1] |= reach[:, 1:]
        grow &= a
        if (grow == reach).all():
            break
        reach = grow
    inside = a & ~reach
    seen = np.zeros_like(inside)
    out = []
    for y0, x0 in zip(*np.nonzero(inside)):
        if seen[y0, x0]:
            continue
        q, pts = deque([(y0, x0)]), []
        seen[y0, x0] = True
        while q:
            y, x = q.popleft()
            pts.append((y, x))
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < h and 0 <= xx < w and inside[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True
                    q.append((yy, xx))
        if len(pts) < min_px:
            continue
        ys, xs = np.array([p[0] for p in pts]), np.array([p[1] for p in pts])
        out.append({"d_mm": round(2 * (len(pts) / np.pi) ** 0.5 * mm_per_px, 1),
                    "w_mm": round((np.ptp(xs) + 1) * mm_per_px, 1), "h_mm": round((np.ptp(ys) + 1) * mm_per_px, 1),
                    "at_mm": [round((xs.mean() - w / 2) * mm_per_px, 1), round((h / 2 - ys.mean()) * mm_per_px, 1)]})
    return sorted(out, key=lambda o: -o["d_mm"])


def parts_sheet(data, out, tile=230, cols=8):
    parts = data["parts"]
    rows = (len(parts) + cols - 1) // cols
    lab = 58
    sheet = Image.new("RGB", (cols * tile, 40 + rows * (tile + lab)), STRIP)
    d = ImageDraw.Draw(sheet)
    f_t, f_n, f_s = labels.font(20), labels.font(14), labels.font(12)
    d.text((10, 8), f"{data['name']}: {len(parts)} parts, {_mm([data['size_mm'][2], data['size_mm'][0], data['size_mm'][1]])} mm "
           f"(length x width x height); each part alone, own sizes long x mid x short", fill=INK, font=f_t)
    for i, p in enumerate(parts):
        x, y = (i % cols) * tile, 40 + (i // cols) * (tile + lab)
        d.rectangle([x + 1, y + 1, x + tile - 2, y + tile - 2], fill=BG)
        src = os.path.join(REPO, p["tile"]) if p.get("tile") else None
        if src and os.path.isfile(src):
            im = Image.open(src).convert("RGBA")
            im.thumbnail((tile - 8, tile - 8))
            sheet.paste(im, (x + (tile - im.width) // 2, y + (tile - im.height) // 2), im)
        mat = (p.get("material") or [{}])[0]
        sw = _rgb(mat.get("base_srgb"))
        n_open = len(p.get("see_through") or [])
        line2 = f"{_mm(p['own_mm'])} mm  {p['kind']}" + (f"  {n_open} opening{'s' if n_open != 1 else ''}" if n_open
                                                         else "")
        d.text((x + 6, y + tile + 2), f"{i + 1}. {p['name'][:28]}", fill=INK, font=f_n)
        d.text((x + 6, y + tile + 20), line2, fill=DIM, font=f_s)
        if sw:
            d.rectangle([x + 6, y + tile + 38, x + 20, y + tile + 52], fill=sw, outline=DIM)
        mr = " ".join(f"{k[:5]} {mat[k]:.2f}" for k in ("metallic", "roughness") if isinstance(mat.get(k), (int, float)))
        d.text((x + 26, y + tile + 38), (mat.get("base_srgb") or "") + ("  " + mr if mr else ""), fill=DIM, font=f_s)
    labels.save(sheet, out)


def closeup_sheet(data, part, shots, out, size=520):
    f_t, f_s = labels.font(20), labels.font(14)
    sheet = Image.new("RGB", (len(shots) * size, size + 70), STRIP)
    d = ImageDraw.Draw(sheet)
    p = next((q for q in data["parts"] if q["name"] == part), {})
    d.text((10, 8), f"{part}: own {_mm(p.get('own_mm', []))} mm, {p.get('kind', '?')}, see-through openings "
           f"{len(p.get('see_through') or [])}, "
           f"touches {', '.join(p.get('touches', [])[:4])}", fill=INK, font=f_t)
    for i, s in enumerate(shots):
        im = Image.open(os.path.join(REPO, s["image"])).convert("RGBA")
        k = size / im.width
        im = im.resize((size, int(im.height * k)))
        x0, y0 = i * size, 40
        d.rectangle([x0, y0, x0 + size - 1, y0 + size - 1], fill=BG)
        step = 10.0 / (s["mm_per_px"] / k)  # 10 mm in sheet pixels
        if step >= 6:
            for gx in range(0, int(size / step) + 1):
                d.line([x0 + gx * step, y0, x0 + gx * step, y0 + size], fill=(112, 114, 120))
            for gy in range(0, int(size / step) + 1):
                d.line([x0, y0 + gy * step, x0 + size, y0 + gy * step], fill=(112, 114, 120))
        sheet.paste(im, (x0, y0), im)
        d.text((x0 + 8, y0 + size + 6), f"{s['view']}  (grid 10 mm)", fill=DIM, font=f_s)
    labels.save(sheet, out)


def main(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    folder = os.path.join(REPO, os.path.dirname(data["renders"]["assembled"]))
    for p in data["parts"]:  # what can be seen through each part -> back into the inspection
        if p.get("tile") and os.path.isfile(os.path.join(REPO, p["tile"])):
            p["see_through"] = openings(os.path.join(REPO, p["tile"]), p["tile_mm_per_px"])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    out = os.path.join(folder, "parts_sheet.png")
    parts_sheet(data, out)
    sheets = [os.path.relpath(out, REPO).replace("\\", "/")]
    by_part = {}
    for s in data.get("closeups") or []:
        by_part.setdefault(s["part"], []).append(s)
    for part, shots in by_part.items():
        cp = os.path.join(folder, f"part_{''.join(c if c.isalnum() else '_' for c in part.lower())[:40]}_sheet.png")
        closeup_sheet(data, part, shots, cp)
        sheets.append(os.path.relpath(cp, REPO).replace("\\", "/"))
    rows = []
    for i, p in enumerate(data["parts"]):
        mat = (p.get("material") or [{}])[0]
        mv = p.get("motion") or {}
        way = mv.get("goes_out_toward") or mv.get("comes_in_from")
        op = p.get("see_through") or []
        ops = (f"  openings {len(op)} (" + ", ".join(f"{o['d_mm']:g}" for o in op[:4]) + (" ..." if len(op) > 4 else "")
               + " mm)") if op else ""
        rows.append(f"  {i + 1:>3}. {p['name'][:34]:<34} {_mm(p['own_mm']):>15} mm  {p['kind']:<6} "
                    f"touches {len(p['touches']):>2}  {mat.get('base_srgb', '')}{ops}" + (f"  moves: {way}" if way else ""))
    m = data.get("motion") or {}
    if m.get("takeapart_order"):
        rows.append(f"  take-apart order (from {m['takeapart_from']}): " + " -> ".join(m["takeapart_order"][:24])
                    + (" ..." if len(m["takeapart_order"]) > 24 else ""))
    print(json.dumps({"status": "pass", "summary": f"inspect sheets: {', '.join(sheets)}",
                      "next_action": f"LOOK at {sheets[0]} and {data['renders'].get('exploded')}; then use the numbers "
                                     f"(refs/{data['name']}.inspect.json) as each part's reference",
                      "rows": rows, "sheets": sheets}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
