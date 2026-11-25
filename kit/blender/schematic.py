"""schematic.py — drawing sheets from a mechanism build (rbx_mech.renders). Plain Python + numpy + Pillow.

    python kit/blender/schematic.py <asset>
      -> build/renders/<asset>_schematic.png   TECHNICAL DRAWING (third-angle): top / side / end views at one scale,
                                               section A-A hatched, dimension chains with arrows, bore centre line,
                                               cutting plane, balloons + leaders, parts list, title block
      -> build/renders/<asset>_mechanism.png   exploded view with balloons, every joint at full travel, joint table
      -> build/renders/<asset>_sheet.png       MODEL SHEET (presentation): product shots, the removable part on its
                                               own, spec block — a concept-art style sheet
Line work follows ISO 128 conventions: visible lines thick, hidden lines thin + dashed, centre lines dash-dot,
dimension lines thin with arrowheads and extension lines, sections hatched at 45 degrees.
"""

import datetime
import json
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

KIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REPO = os.path.dirname(KIT)
BLUE = (18, 46, 92)
GRID = (28, 60, 112)
LINE = (236, 242, 255)
THIN = (170, 192, 230)
ACCENT = (255, 204, 86)
W, H = 3200, 2260


def _font(size, bold=False):
    for f in (("consolab.ttf", "arialbd.ttf") if bold else ("consola.ttf", "arial.ttf")) + ("DejaVuSansMono.ttf",):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _out(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _title(name):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name).replace("_", " ").strip().capitalize()


def _mm(studs, mm):
    return f"{studs * mm:.1f}" if mm else f"{studs:.3f} st"


class Sheet:
    def __init__(self, title, bg=BLUE, grid=True):
        self.img = Image.new("RGB", (W, H), bg)
        self.d = ImageDraw.Draw(self.img)
        if grid:
            for x in range(0, W, 50):
                self.d.line((x, 0, x, H), fill=GRID)
            for y in range(0, H, 50):
                self.d.line((0, y, W, y), fill=GRID)
        self.d.rectangle((24, 24, W - 25, H - 25), outline=LINE, width=4)
        self.d.rectangle((36, 36, W - 37, H - 37), outline=LINE, width=1)
        self.d.text((70, 58), title, font=_font(56, True), fill=LINE)

    def lines(self, path, x, y, scale=1.0, color=LINE):
        """paste a line-art render (black lines on white) as `color` lines; grey (hidden) lines come out fainter.
        -> (w, h, bbox of the drawn object in sheet pixels)"""
        rgb = Image.open(path).convert("RGB")
        if scale != 1.0:
            rgb = rgb.resize((max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale))), Image.LANCZOS)
        src = rgb.convert("L")
        c = np.asarray(rgb, np.float32)
        a = np.asarray(src, np.float32)
        red = (c[..., 0] - c[..., 1]) > 60  # the moving part's lines (rbx_mech draws them red)
        alpha = np.clip((255 - a) * 1.15, 0, 255).astype(np.uint8)
        alpha[red] = 0
        tile = Image.new("RGBA", src.size, color + (0,))
        tile.putalpha(Image.fromarray(alpha))
        self.img.paste(tile, (int(x), int(y)), tile)
        if red.any():
            ra = np.clip((c[..., 0] - c[..., 1]) * 1.4, 0, 255).astype(np.uint8) * red
            rt = Image.new("RGBA", src.size, ACCENT + (0,))
            rt.putalpha(Image.fromarray(ra.astype(np.uint8)))
            self.img.paste(rt, (int(x), int(y)), rt)
        bb = Image.fromarray(alpha).point(lambda v: 255 if v > 90 else 0).getbbox()
        return src.width, src.height, (bb[0] + x, bb[1] + y, bb[2] + x, bb[3] + y) if bb else None

    def hatch(self, mask_path, x, y, scale=1.0, spacing=11):
        m = Image.open(mask_path).convert("RGB")
        if scale != 1.0:
            m = m.resize((max(1, int(m.width * scale)), max(1, int(m.height * scale))), Image.NEAREST)
        a = np.asarray(m, np.int16)
        cut = (a[..., 0] > 150) & (a[..., 1] < 90) & (a[..., 2] < 90)
        yy, xx = np.mgrid[0:cut.shape[0], 0:cut.shape[1]]
        stripes = ((xx + yy) % spacing) < 2
        pat = cut & stripes
        layer = Image.new("RGBA", m.size, THIN + (0,))
        layer.putalpha(Image.fromarray((pat * 230).astype(np.uint8)))
        fill = Image.new("RGBA", m.size, (60, 96, 160, 0))
        fill.putalpha(Image.fromarray((cut * 90).astype(np.uint8)))
        self.img.paste(fill, (int(x), int(y)), fill)
        self.img.paste(layer, (int(x), int(y)), layer)

    def arrow(self, x, y, dx, dy, size=16, color=ACCENT):
        n = math.hypot(dx, dy) or 1
        ux, uy = dx / n, dy / n
        px, py = -uy, ux
        self.d.polygon([(x, y), (x - ux * size + px * size * 0.35, y - uy * size + py * size * 0.35),
                        (x - ux * size - px * size * 0.35, y - uy * size - py * size * 0.35)], fill=color)

    def dim_h(self, x0, x1, y_obj0, y_obj1, y, text, color=ACCENT):
        """horizontal dimension at height y, extension lines from the object points (x0, y_obj0), (x1, y_obj1)"""
        f = _font(28)
        for x, yo in ((x0, y_obj0), (x1, y_obj1)):
            self.d.line((x, yo + (8 if y > yo else -8), x, y + (12 if y > yo else -12)), fill=color, width=2)
        self.d.line((x0, y, x1, y), fill=color, width=2)
        self.arrow(x0, y, -1, 0, color=color)
        self.arrow(x1, y, 1, 0, color=color)
        tw = self.d.textlength(text, font=f)
        self.d.rectangle(((x0 + x1) / 2 - tw / 2 - 8, y - 34, (x0 + x1) / 2 + tw / 2 + 8, y - 4), fill=BLUE)
        self.d.text(((x0 + x1) / 2 - tw / 2, y - 34), text, font=f, fill=color)

    def dim_v(self, y0, y1, x_obj, x, text, color=ACCENT):
        f = _font(28)
        for yy in (y0, y1):
            self.d.line((x_obj + 8, yy, x + 12, yy), fill=color, width=2)
        self.d.line((x, y0, x, y1), fill=color, width=2)
        self.arrow(x, y0, 0, -1, color=color)
        self.arrow(x, y1, 0, 1, color=color)
        txt = Image.new("RGBA", (int(self.d.textlength(text, font=f)) + 16, 36), BLUE + (255,))
        ImageDraw.Draw(txt).text((8, 2), text, font=f, fill=color)
        txt = txt.rotate(90, expand=True)
        self.img.paste(txt, (int(x - txt.width / 2), int((y0 + y1) / 2 - txt.height / 2)), txt)

    def centre(self, x0, y0, x1, y1, color=THIN):
        """dash-dot centre line"""
        L = math.hypot(x1 - x0, y1 - y0)
        if L <= 0:
            return
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        t = 0.0
        pattern = [(26, True), (6, False), (4, True), (6, False)]
        k = 0
        while t < L:
            seg, on = pattern[k % 4]
            t2 = min(L, t + seg)
            if on:
                self.d.line((x0 + ux * t, y0 + uy * t, x0 + ux * t2, y0 + uy * t2), fill=color, width=2)
            t, k = t2, k + 1

    def label(self, x, y, text, size=30, color=LINE, bold=True):
        self.d.text((x, y), text, font=_font(size, bold), fill=color)

    def save(self, path):
        self.img.save(path)


def _snap(alpha_img, x, y, box, r=60):
    """nearest drawn-line pixel to (x, y) inside box: a leader must end ON the part, not in empty space."""
    a = np.asarray(alpha_img)
    h, w = a.shape
    x0, y0, x1, y1 = [int(v) for v in box]
    best, bd = None, 1e9
    for yy in range(max(0, int(y) - r), min(h, int(y) + r)):
        for xx in range(max(0, int(x) - r), min(w, int(x) + r), 2):
            if a[yy, xx] > 150 and x0 - 2 <= xx <= x1 + 2 and y0 - 2 <= yy <= y1 + 2:
                d = (xx - x) ** 2 + (yy - y) ** 2
                if d < bd:
                    best, bd = (xx, yy), d
    return best or (x, y)


def _balloons(sheet, view, origin, scale, parts, numbers, render_path, band_top, band_bottom=None, right_x=None):
    """balloons outside the view, leaders snapped onto each part's own lines: parts in the upper half get a band
    above (sorted left-right), the rest a column on the right (sorted top-down) or a band below. No crossings."""
    src = Image.open(render_path).convert("L")
    if scale != 1.0:
        src = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))), Image.LANCZOS)
    alpha = src.point(lambda v: 255 - v)
    ox, oy = origin
    items = []
    for c in view["callouts"]:
        if c["name"] not in parts:
            continue
        tw, th = src.width, src.height
        box = (c["box"][0] * tw, c["box"][1] * th, c["box"][2] * tw, c["box"][3] * th)
        px, py = _snap(alpha, c["u"] * tw, c["v"] * th, box)
        items.append((c["name"], ox + px, oy + py))
    mid = oy + src.height * 0.42
    upper = sorted([i for i in items if i[2] < mid], key=lambda t: t[1])
    lower = sorted([i for i in items if i[2] >= mid], key=lambda t: t[2] if right_x is not None else t[1])
    f = _font(28, True)

    def balloon(name, tx, ty, bx, by):
        n = numbers[name]
        sheet.d.line((bx, by, tx, ty), fill=ACCENT, width=2)
        sheet.d.ellipse((tx - 5, ty - 5, tx + 5, ty + 5), fill=ACCENT)
        sheet.d.ellipse((bx - 24, by - 24, bx + 24, by + 24), fill=BLUE, outline=ACCENT, width=3)
        tw_ = sheet.d.textlength(str(n), font=f)
        sheet.d.text((bx - tw_ / 2, by - 16), str(n), font=f, fill=ACCENT)

    if upper:
        xs = [g[1] for g in upper]
        for i in range(1, len(xs)):
            xs[i] = max(xs[i], xs[i - 1] + 72)
        for (name, tx, ty), bx in zip(upper, xs):
            balloon(name, tx, ty, bx, band_top)
    if lower:
        if right_x is not None:
            ys = [g[2] for g in lower]
            for i in range(1, len(ys)):
                ys[i] = max(ys[i], ys[i - 1] + 72)
            for (name, tx, ty), by in zip(lower, ys):
                balloon(name, tx, ty, right_x, by)
        else:
            xs = [g[1] for g in lower]
            for i in range(1, len(xs)):
                xs[i] = max(xs[i], xs[i - 1] + 72)
            for (name, tx, ty), bx in zip(lower, xs):
                balloon(name, tx, ty, bx, band_bottom)


def _part_name(g, joints):
    j = next((jj for jj in joints.values() if jj["group"] == g), None)
    if g == "main":
        return "Frame assembly"
    return _title(j["name"]) if j else _title(g)


def _motion(j, mm):
    if j["kind"] == "fixed":
        return "fixed"
    if j["kind"] == "hinge":
        return f"pivot {j['min']:g}..{j['max']:g} deg"
    return f"slide {_mm(j['max'] - j['min'], mm)}" + (" mm" if mm else "")


def _title_block(s, meta, sheet_no, sheets, x0=2140, y0=1830):
    mm = meta.get("real_mm_per_stud")
    x1, y1 = W - 60, H - 60
    d = s.d
    d.rectangle((x0, y0, x1, y1), outline=LINE, width=3)
    rows = [("TITLE", _title(meta["asset"]).upper()), ("DRAWING NO", f"KIT-{meta['asset'].upper()}-{sheet_no:02d}"),
            ("SCALE", f"1 stud = {mm:.1f} mm" if mm else "studs"), ("UNITS", "mm" if mm else "studs"),
            ("DATE", datetime.date.today().isoformat()), ("SHEET", f"{sheet_no} / {sheets}")]
    rh = (y1 - y0) / len(rows)
    for i, (k, v) in enumerate(rows):
        yy = y0 + i * rh
        if i:
            d.line((x0, yy, x1, yy), fill=LINE, width=1)
        d.text((x0 + 16, yy + rh / 2 - 13), k, font=_font(22), fill=THIN)
        d.text((x0 + 210, yy + rh / 2 - 17), v, font=_font(30, True), fill=LINE)
    d.line((x0 + 196, y0, x0 + 196, y1), fill=LINE, width=1)
    # third-angle projection symbol (a truncated cone: end view circles on the RIGHT of the side view)
    sx, sy = x0 - 210, y1 - 90
    d.polygon([(sx, sy - 22), (sx + 70, sy - 38), (sx + 70, sy + 38), (sx, sy + 22)], outline=LINE, width=2)
    d.ellipse((sx + 100, sy - 38, sx + 176, sy + 38), outline=LINE, width=2)
    d.ellipse((sx + 116, sy - 22, sx + 160, sy + 22), outline=LINE, width=2)
    d.text((sx - 10, sy + 48), "THIRD ANGLE", font=_font(20), fill=THIN)


def compose(asset):
    renders = os.path.join(REPO, "build", "renders")
    meta_path = os.path.join(renders, f"{asset}_schematic.json")
    if not os.path.isfile(meta_path):
        return _out("fail", f"schematic: {asset} has no line-art views (a build renders them only when asked)",
                    f"give the build a.joint(...) (moving parts) and render them: lune run kit asset {asset} --schematic")
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    if meta.get("stale"):  # (rbx_mech.views_waiting: a later build changed what these views show)
        return _out("fail", f"schematic: {asset}'s line-art views show an OLDER build (stale since {meta['stale']})",
                    f"render them for the model as it is now: lune run kit asset {asset} --schematic")
    mm = meta.get("real_mm_per_stud")
    views, joints = meta["views"], meta["joints"]
    parts = meta.get("parts") or meta["groups"]
    numbers = {g: i + 1 for i, g in enumerate(parts)}
    R = lambda v: os.path.join(renders, views[v]["file"])  # noqa: E731

    # ================= sheet 1: technical drawing (third angle: END | SIDE | SECTION in a row, TOP above SIDE)
    s = Sheet(f"{_title(asset).upper()} — GENERAL ARRANGEMENT")
    side = Image.open(R("side"))
    top_ = Image.open(R("top"))
    end = Image.open(R("front"))
    sec = Image.open(R("section"))
    gap, gap_r = 120, 300  # the gap right of the side view holds the lower balloons
    k = min((W - 160 - gap - gap_r) / (end.width + side.width + sec.width),
            (1760 - 170 - 150 - 230) / (top_.height + side.height))
    ex0 = 80
    sx0 = ex0 + int(end.width * k) + gap
    cx0 = sx0 + int(side.width * k) + gap_r
    ty0 = 200
    sy0 = ty0 + int(top_.height * k) + 150
    _, _, tbb = s.lines(R("top"), sx0, ty0, k)
    _, _, sbb = s.lines(R("side"), sx0, sy0, k)
    _, _, ebb = s.lines(R("front"), ex0, sy0 + (side.height - end.height) * k / 2, k)
    s.hatch(os.path.join(renders, views["section"]["mask"]), cx0, sy0, k)
    _, _, cbb = s.lines(R("section"), cx0, sy0, k)
    s.label(sx0, ty0 - 46, "TOP VIEW", 30)
    s.label(sx0, sy0 - 120, "SIDE VIEW (LEFT)", 30)
    s.label(ex0, sy0 - 120, "END VIEW", 30)
    s.label(cx0, sy0 - 120, "SECTION A-A", 30)
    pps = views["side"]["pps"] * k
    barrel = next((c for c in views["side"]["callouts"] if c["name"] == "barrel"), None)
    if barrel and sbb:
        yb = sy0 + (barrel["box"][1] + barrel["box"][3]) / 2 * side.height * k
        s.centre(sbb[0] - 40, yb, sbb[2] + 40, yb)
        if cbb:
            s.centre(cbb[0] - 40, yb, cbb[2] + 40, yb)
    if tbb:  # the cutting plane A-A on the top view (the centre plane), with view arrows
        yt = (tbb[1] + tbb[3]) / 2
        s.centre(tbb[0] - 60, yt, tbb[2] + 60, yt, color=ACCENT)
        for xx in (tbb[0] - 60, tbb[2] + 60):
            s.d.line((xx, yt, xx, yt + 40), fill=ACCENT, width=3)
            s.arrow(xx, yt + 40, 0, 1, color=ACCENT)
            s.label(xx - 10, yt + 48, "A", 30, ACCENT)
    # dimensions: all BELOW the side view (balloons live above / right): overall, slide, barrel; height left
    if sbb:
        L = (sbb[2] - sbb[0]) / pps
        Hh = (sbb[3] - sbb[1]) / pps
        chain = sbb[3] + 80
        s.dim_h(sbb[0], sbb[2], sbb[3], sbb[3], chain, f"OVERALL {_mm(L, mm)}")
        chain += 70
        for g in ("slide", "barrel"):
            c = next((c for c in views["side"]["callouts"] if c["name"] == g), None)
            if c:
                x0 = sx0 + c["box"][0] * side.width * k
                x1 = sx0 + c["box"][2] * side.width * k
                yo = sy0 + c["box"][3] * side.height * k
                s.dim_h(x0, x1, yo, yo, chain, f"{_title(g).upper()} {_mm((x1 - x0) / pps, mm)}")
                chain += 70
        s.dim_v(sbb[1], sbb[3], sbb[0], sbb[0] - 60, f"{_mm(Hh, mm)}")
    if ebb:
        s.dim_h(ebb[0], ebb[2], ebb[3], ebb[3], ebb[3] + 80, f"{_mm((ebb[2] - ebb[0]) / pps, mm)}")
    _balloons(s, views["side"], (sx0, sy0), k, parts, numbers, R("side"), sy0 - 60, None,
              right_x=sx0 + side.width * k + 150)
    # bottom band: parts list | notes | title block
    px0, py0 = 80, 1800
    s.d.rectangle((px0, py0, 1250, H - 60), outline=LINE, width=3)
    s.label(px0 + 16, py0 + 12, "ITEM  PART                    MOTION", 26)
    s.d.line((px0, py0 + 52, 1250, py0 + 52), fill=LINE, width=2)
    rh = min(44, (H - 60 - py0 - 64) / max(1, len(parts)))
    for g in parts:
        yy = py0 + 60 + (numbers[g] - 1) * rh
        j = next((jj for jj in joints.values() if jj["group"] == g), None)
        s.d.text((px0 + 30, yy), f"{numbers[g]:>2}", font=_font(26, True), fill=ACCENT)
        s.d.text((px0 + 100, yy), _part_name(g, joints), font=_font(26), fill=LINE)
        s.d.text((px0 + 820, yy), _motion(j, mm) if j else "fixed", font=_font(24), fill=THIN)
    nx = 1300
    notes = ["NOTES", "1. Hidden edges dashed; section A-A on the centre plane.",
             "2. Every moving part is its own mesh + Motor6D joint.",
             "3. All travel ranges interference-checked at build.",
             f"4. Overall {_mm(meta['size_studs'][2], mm)} x {_mm(meta['size_studs'][1], mm)} x "
             f"{_mm(meta['size_studs'][0], mm)}{' mm' if mm else ''} (L x H x W)."]
    for i, n in enumerate(notes):
        s.label(nx, py0 + i * 44, n, 26 if i else 30, LINE if i == 0 else THIN, bold=(i == 0))
    _title_block(s, meta, 1, 3, x0=2140, y0=1800)
    out1 = os.path.join(renders, f"{asset}_schematic.png")
    s.save(out1)

    # ================= sheet 2: mechanism
    s = Sheet(f"{_title(asset).upper()} — MECHANISM: EXPLODED + MOTION")
    ex = Image.open(R("exploded"))
    k2 = min(1.0, (W - 200) / ex.width, 900 / ex.height)
    s.lines(R("exploded"), (W - ex.width * k2) / 2, 220, k2)
    s.label(100, 150, "EXPLODED VIEW — each moving part along its joint", 30)
    _balloons(s, views["exploded"], ((W - ex.width * k2) / 2, 220), k2, parts, numbers, R("exploded"), 200,
              220 + ex.height * k2 + 40)
    motions = [v for v in views if v.startswith("motion_")]
    cols = 3
    cw, ch = (W - 200) / cols, 340
    for i, v in enumerate(motions[:6]):
        im = Image.open(R(v))
        kk = min((cw - 40) / im.width, (ch - 60) / im.height)
        x = 100 + (i % cols) * cw
        y = 1230 + (i // cols) * (ch + 30)
        s.d.rectangle((x - 10, y - 50, x + cw - 30, y + ch - 20), outline=THIN, width=1)
        jn = v[len("motion_"):]
        j = next((jj for jj in joints.values() if jj["name"] == jn), None)
        s.label(x, y - 44, f"{_title(jn).upper()} — {_motion(j, mm) if j else ''} (full travel)", 26)
        s.lines(R(v), x, y, kk)
    _title_block(s, meta, 2, 3, x0=2140, y0=H - 330)
    out2 = os.path.join(renders, f"{asset}_mechanism.png")
    s.save(out2)

    # ================= sheet 3: model sheet (presentation, concept-sheet style)
    p = meta.get("present") or {}
    s = Sheet("", bg=(30, 31, 35), grid=False)

    def crop(path, margin=24):
        im = Image.open(path).convert("RGB")
        arr = np.asarray(im, np.int16)
        bg = arr[2, 2]
        diff = np.abs(arr - bg).sum(-1) > 18
        ys, xs = np.nonzero(diff)
        if len(xs) == 0:
            return im
        return im.crop((max(0, xs.min() - margin), max(0, ys.min() - margin), min(im.width, xs.max() + margin), min(im.height, ys.max() + margin)))

    def panel(im, x, y, w, h):
        kk = min(w / im.width, h / im.height)
        im2 = im.resize((max(1, int(im.width * kk)), max(1, int(im.height * kk))), Image.LANCZOS)
        s.d.rectangle((x, y, x + w, y + h), fill=tuple(int(v) for v in np.asarray(im)[2, 2]))
        s.img.paste(im2, (int(x + (w - im2.width) / 2), int(y + (h - im2.height) / 2)))

    if p.get("side"):
        panel(crop(os.path.join(renders, p["side"])), 70, 70, W - 140, 1010)
    row = [k_ for k_ in ("three_quarter", "rear_quarter", "part") if p.get(k_)]
    widths = {"three_quarter": 1.0, "rear_quarter": 1.0, "part": 0.62}
    total = sum(widths[k_] for k_ in row) or 1
    x = 70
    for k_ in row:
        w_ = (W - 140 - 30 * (len(row) - 1)) * widths[k_] / total
        panel(crop(os.path.join(renders, p[k_])), x, 1110, w_, 820)
        x += w_ + 30
    sz = meta["size_studs"]
    s.d.text((70, 1975), _title(asset).upper(), font=_font(64, True), fill=(238, 238, 240))
    specs = (f"LENGTH {_mm(sz[2], mm)}   HEIGHT {_mm(sz[1], mm)}   WIDTH {_mm(sz[0], mm)}{' mm' if mm else ''}   ·   "
             f"{len(parts)} PARTS   ·   {sum(1 for j in joints.values() if j['kind'] != 'fixed')} WORKING JOINTS")
    s.d.text((70, 2065), specs, font=_font(30), fill=(170, 174, 184))
    s.d.text((70, 2115), "MODEL SHEET · kit-built · every moving part is its own mesh + Motor6D", font=_font(26), fill=(120, 124, 134))
    s.d.line((70, 1960, W - 70, 1960), fill=(90, 92, 100), width=2)
    out3 = os.path.join(renders, f"{asset}_sheet.png")
    s.save(out3)
    rel = lambda q: os.path.relpath(q, REPO).replace("\\", "/")  # noqa: E731
    return _out("pass", f"schematic: {rel(out1)} + {rel(out2)} + {rel(out3)} ({len(parts)} parts, {len(joints)} joints)",
                "look at all three: proportions, clearances, the hatched section (internals), every joint's travel",
                sheets=[rel(out1), rel(out2), rel(out3)])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(_out("fail", "schematic: usage", "python kit/blender/schematic.py <asset>"))
    sys.exit(compose(sys.argv[1]))
