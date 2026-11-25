"""preview.py — the kit's eyes for UI: lay out compiled ScreenGuis (Rojo .model.json) with Roblox's rules and
draw them at phone / tablet / desktop sizes.

    python kit/ui/preview.py --models src/ui --out build/ui [Name ...]

Per screen: build/ui/<Name>.png — desktop 1920x1080 (shown at 50%), phone 844x390 and tablet 1024x768 (60%).
The Roblox top bar zone (menu/chat buttons) is tinted red so you can see what it covers.
Layout follows the engine: UDim2 size/position against the parent's content box (after UIPadding), AnchorPoint,
UIAspectRatioConstraint (fit within), UIListLayout (direction, padding, cross-axis alignment), UIGridLayout
(cell size, padding, wrapping, centred rows), ScrollingFrame clipping, Visible, tree order = draw order.
Fonts are approximated with system fonts (Gotham -> Segoe UI / Arial). Drawn like the engine: UIGradient on
backgrounds/text/strokes (colour + transparency), UIStroke (thickness, transparency; Contextual = text outline),
Rotation, CanvasGroup GroupTransparency, kit art images ("art:<name>" -> build/ui/art/<name>.png, tinted by
ImageColor3, 9-slice), other images as labelled placeholders.

Measured per viewport (warnings, named in next_action): text that overflows its box, controls partly off
screen, controls under the Roblox top bar, touch targets under 44 px on the phone.
Prints one JSON line: {status, summary, next_action, screens:[{name, file, checks}]}.
"""

import argparse
import copy
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

VIEWPORTS = [("desktop", 1920, 1080, 0.5), ("phone", 844, 390, 0.6), ("tablet", 1024, 768, 0.6)]
TOPBAR = (0, 0, 260, 58)  # Roblox menu / chat / backpack buttons (top-left), drawn over IgnoreGuiInset GUIs
INTERACTIVE = {"TextButton", "ImageButton", "TextBox"}
TEXT = {"TextLabel", "TextButton", "TextBox"}
FONT_FILES = {
    "bold": ["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "black": ["seguibl.ttf", "ariblk.ttf", "segoeuib.ttf", "arialbd.ttf"],
    "regular": ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"],
    "mono": ["consola.ttf", "cour.ttf", "DejaVuSansMono.ttf"],
}
FONT_STYLE = {
    "GothamBold": "bold",
    "GothamBlack": "black",
    "GothamMedium": "bold",
    "Gotham": "regular",
    "SourceSansBold": "bold",
    "ArialBold": "bold",
    "RobotoMono": "mono",
    "FredokaOne": "black",
    "LuckiestGuy": "black",
    "Bangers": "black",
    "Michroma": "bold",
    "Arcade": "mono",
    "Oswald": "bold",
}
_font_cache = {}
FALLBACK_FACES = set()  # Roblox fonts drawn with a system face because their family is not fetched (reported)

def _load_sibling(name, file):
    """kit/ui/<file> under a private module name: the kit's tests run many `judge` / `preview` modules in one process"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, os.path.join(os.path.dirname(os.path.abspath(__file__)), file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


try:
    kitfonts = _load_sibling("kit_ui_fonts", "fonts.py")  # the real faces, fetched + pinned (kit ui fonts)
except (ImportError, OSError):  # pragma: no cover
    kitfonts = None


def _true_face(name, size):
    """the fetched Google Fonts face behind a Roblox font, at the manifest's weight (variable axes by name)"""
    r = kitfonts.resolve(name) if kitfonts else None
    if not r:
        return None
    try:
        f = ImageFont.truetype(r["path"], size)
    except OSError:
        return None
    if r.get("variable"):
        try:
            values = []
            for axis in f.get_variation_axes():
                tag = (axis.get("name") or b"").decode("latin-1").lower() if isinstance(axis.get("name"), bytes) else str(axis.get("name", "")).lower()
                if tag in ("weight", "wght"):
                    values.append(min(max(r["weight"], axis["minimum"]), axis["maximum"]))
                else:
                    values.append(axis["default"])
            f.set_variation_by_axes(values)
        except (OSError, ValueError):
            pass
    return f


def font(name, size):
    key = (name, size)
    if key not in _font_cache:
        f = _true_face(name, size)
        if f is None:
            FALLBACK_FACES.add(name)
            style = FONT_STYLE.get(name, "regular")
            for file in FONT_FILES[style]:
                for base in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu", "/System/Library/Fonts/Supplemental"):
                    try:
                        f = ImageFont.truetype(os.path.join(base, file), size)
                        break
                    except OSError:
                        continue
                if f:
                    break
        _font_cache[key] = f or ImageFont.load_default()
    return _font_cache[key]


def c3(v, default=(163, 162, 165)):
    if isinstance(v, dict) and "Color3" in v:
        return tuple(int(round(x * 255)) for x in v["Color3"])
    return default


def udim2(v, default=((0, 0), (0, 0))):
    if isinstance(v, dict) and "UDim2" in v:
        return v["UDim2"]
    return default


def udim(v):
    if isinstance(v, dict) and "UDim" in v:
        return v["UDim"]
    return (0, 0)


def kids(inst, cls):
    return [c for c in inst.get("Children") or [] if c.get("ClassName") == cls]


def one(inst, cls):
    k = kids(inst, cls)
    return k[0] if k else None


GUI = {"Frame", "TextLabel", "TextButton", "TextBox", "ImageLabel", "ImageButton", "ScrollingFrame", "CanvasGroup", "ViewportFrame"}
ART_DIR = None  # set in main(): build/ui/art
_art_cache = {}


GROUND_DIR = "assets/ui/grounds"  # the game frames identities are judged over (kit ui ground; never uploaded)
_ground_cache = {}


def ground_image(identity):
    """the identity's GAME FRAME (assets/ui/grounds/<identity>.png, kit ui ground), else its old art world.png, else None"""
    if identity not in _ground_cache:
        path = os.path.join(GROUND_DIR, f"{identity}.png")
        _ground_cache[identity] = Image.open(path).convert("RGBA") if os.path.isfile(path) else art_image(f"{identity}/world")
    return _ground_cache[identity]


def art_image(name):
    if not ART_DIR or not name:
        return None
    if name not in _art_cache:
        path = os.path.join(ART_DIR, f"{name}.png")
        _art_cache[name] = Image.open(path).convert("RGBA") if os.path.isfile(path) else None
    return _art_cache[name]


def attr(inst, key):
    a = (inst.get("Properties", {}).get("Attributes") or {}).get("Attributes") or {}
    v = a.get(key)
    if isinstance(v, dict):
        return next(iter(v.values()))
    return v


def seq_colors(grad):
    ks = ((grad.get("Properties", {}).get("Color") or {}).get("ColorSequence") or {}).get("keypoints")
    if not ks:
        return None
    return [(k["time"], tuple(int(round(c * 255)) for c in k["color"])) for k in ks]


def seq_alpha(grad):
    ks = ((grad.get("Properties", {}).get("Transparency") or {}).get("NumberSequence") or {}).get("keypoints")
    if not ks:
        return None
    return [(k["time"], k["value"]) for k in ks]


def sample(keys, t):
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            k = 0 if t1 == t0 else (t - t0) / (t1 - t0)
            if isinstance(v0, tuple):
                return tuple(int(a + (b - a) * k) for a, b in zip(v0, v1))
            return v0 + (v1 - v0) * k
    return keys[-1][1]


def gradient_layer(w, h, grad):
    """RGBA image (w x h): the gradient's colour (RGB) and 1-transparency (A), along its Rotation."""
    w, h = max(1, int(w)), max(1, int(h))
    cols, alps = seq_colors(grad), seq_alpha(grad)
    rot = math.radians(grad.get("Properties", {}).get("Rotation", 0) or 0)
    dx, dy = math.cos(rot), math.sin(rot)
    gw, gh = min(w, 64), min(h, 48)
    half = abs(dx) * w / 2 + abs(dy) * h / 2 or 1
    # Offset (scale of the box) slides the gradient along its axis: a shimmer band waits at -1 and sweeps to +1
    off = (grad.get("Properties", {}).get("Offset") or {}).get("Vector2") or [0, 0]
    shift = (float(off[0]) * w * dx + float(off[1]) * h * dy) / (2 * half)
    small = Image.new("RGBA", (gw, gh))
    px = small.load()
    for j in range(gh):
        for i in range(gw):
            xx, yy = (i + 0.5) * w / gw, (j + 0.5) * h / gh
            t = max(0.0, min(1.0, ((xx - w / 2) * dx + (yy - h / 2) * dy) / (2 * half) + 0.5 - shift))
            c = sample(cols, t) if cols else (255, 255, 255)
            a = 1 - sample(alps, t) if alps else 1
            px[i, j] = c + (int(255 * max(0, min(1, a))),)
    return small.resize((w, h), Image.BILINEAR)


def tint(img, color, transparency=0.0):
    r, g, b, a = img.split()
    if transparency:
        a = a.point(lambda v: int(v * (1 - transparency)))
    return Image.merge("RGBA", (r.point(lambda v: v * color[0] // 255), g.point(lambda v: v * color[1] // 255), b.point(lambda v: v * color[2] // 255), a))


def nine_slice(img, w, h, rect):
    (l, t), (r, b) = rect
    W, H = img.size
    w, h = max(1, int(w)), max(1, int(h))
    out = Image.new("RGBA", (w, h))
    xs_src = [0, l, r, W]
    ys_src = [0, t, b, H]
    xs_dst = [0, min(l, w // 2), max(w - (W - r), w // 2), w]
    ys_dst = [0, min(t, h // 2), max(h - (H - b), h // 2), h]
    for i in range(3):
        for j in range(3):
            sw, sh = xs_src[i + 1] - xs_src[i], ys_src[j + 1] - ys_src[j]
            dw, dh = xs_dst[i + 1] - xs_dst[i], ys_dst[j + 1] - ys_dst[j]
            if sw > 0 and sh > 0 and dw > 0 and dh > 0:
                piece = img.crop((xs_src[i], ys_src[j], xs_src[i + 1], ys_src[j + 1])).resize((dw, dh), Image.LANCZOS)
                out.paste(piece, (xs_dst[i], ys_dst[j]))
    return out


class Layout:
    """Computes absolute rects for every GuiObject: {id(inst): (x, y, w, h)}."""

    def __init__(self, sw, sh):
        self.rects = {}
        self.order = []  # (inst, rect, clip, path)
        self.sw, self.sh = sw, sh

    def paint_order(self):
        """the order the ENGINE paints (ZIndexBehavior Sibling): a parent before its children, siblings by ZIndex, ties in
        tree order — layout still runs in LayoutOrder (a soul layer at z 3 under a z 2 vessel was hidden in the preview)"""
        seq = {path: i for i, (_inst, _r, _c, path) in enumerate(self.order)}
        zs = {path: inst.get("Properties", {}).get("ZIndex", 1) for inst, _r, _c, path in self.order}  # (0 is a real layer, under 1)
        keys = {}

        def key(path):
            if path not in keys:
                parent = path.rsplit(".", 1)[0] if "." in path else None
                keys[path] = (key(parent) if parent in seq else []) + [(zs[path], seq[path])]
            return keys[path]

        return sorted(self.order, key=lambda e: key(e[3]))

    def size_of(self, inst, cw, ch):
        p = inst.get("Properties", {})
        (sx, ox), (sy, oy) = udim2(p.get("Size"), ((0, 100), (0, 100)))
        w, h = cw * sx + ox, ch * sy + oy
        auto = p.get("AutomaticSize")
        if auto in ("X", "Y", "XY") and inst.get("ClassName") in TEXT:
            # the engine grows the box to its text (tracked glyph labels are sized this way)
            size = int(p.get("TextSize", 14))
            fnt = font(p.get("Font", "GothamMedium"), size)
            text = p.get("Text", "")
            if auto in ("X", "XY") and text:
                w = max(w, fnt.getlength(text) + 1)  # (the engine fits TextBounds exactly)
            if auto in ("Y", "XY"):
                h = max(h, size * 1.2 + 4)
        asp = one(inst, "UIAspectRatioConstraint")
        if asp:
            r = asp.get("Properties", {}).get("AspectRatio", 1) or 1
            if w / max(h, 1e-6) > r:
                w = h * r
            else:
                h = w / r
        return w, h

    def content_box(self, inst, x, y, w, h):
        pad = one(inst, "UIPadding")
        if not pad:
            return x, y, w, h
        p = pad.get("Properties", {})
        t = udim(p.get("PaddingTop"))
        b = udim(p.get("PaddingBottom"))
        left = udim(p.get("PaddingLeft"))
        r = udim(p.get("PaddingRight"))
        pt, pb = h * t[0] + t[1], h * b[0] + b[1]
        pl, pr = w * left[0] + left[1], w * r[0] + r[1]
        return x + pl, y + pt, max(0, w - pl - pr), max(0, h - pt - pb)

    def place(self, inst, rect, clip, path):
        self.rects[id(inst)] = rect
        self.order.append((inst, rect, clip, path))
        x, y, w, h = rect
        if inst.get("ClassName") == "ScrollingFrame" or inst.get("Properties", {}).get("ClipsDescendants"):
            clip = rect if clip is None else intersect(clip, rect)
        cx, cy, cw, ch = self.content_box(inst, x, y, w, h)
        children = [c for c in inst.get("Children") or [] if c.get("ClassName") in GUI]
        children = [c for c in children if c.get("Properties", {}).get("Visible", True) is not False]
        children.sort(key=lambda c: c.get("Properties", {}).get("LayoutOrder", 0))
        grid = one(inst, "UIGridLayout")
        lst = one(inst, "UIListLayout")
        if grid:
            gp = grid.get("Properties", {})
            (csx, cox), (csy, coy) = udim2(gp.get("CellSize"), ((0, 100), (0, 100)))
            (psx, pox), (psy, poy) = udim2(gp.get("CellPadding"), ((0, 5), (0, 5)))
            cellw, cellh = cw * csx + cox, ch * csy + coy
            padx, pady = cw * psx + pox, ch * psy + poy
            per_row = max(1, int((cw + padx) // (cellw + padx))) if cellw + padx > 0 else 1
            for i, c in enumerate(children):
                row, col = divmod(i, per_row)
                in_row = min(per_row, len(children) - row * per_row)
                row_w = in_row * cellw + (in_row - 1) * padx
                off = (cw - row_w) / 2 if gp.get("HorizontalAlignment", "Center") == "Center" else 0
                self.place(c, (cx + off + col * (cellw + padx), cy + row * (cellh + pady), cellw, cellh), clip, f"{path}.{c['Name']}")
        elif lst:
            lp = lst.get("Properties", {})
            vertical = lp.get("FillDirection", "Vertical") == "Vertical"
            gap = udim(lp.get("Padding"))
            gap = (ch if vertical else cw) * gap[0] + gap[1]
            sizes = [self.size_of(c, cw, ch) for c in children]
            run = sum((h_ if vertical else w_) for w_, h_ in sizes) + gap * max(0, len(children) - 1)
            # where the run sits along the list's own axis (the engine's VerticalAlignment / HorizontalAlignment)
            if vertical:
                cursor = {"Top": 0.0, "Center": (ch - run) / 2, "Bottom": ch - run}.get(lp.get("VerticalAlignment", "Top"), 0.0)
            else:
                cursor = {"Left": 0.0, "Center": (cw - run) / 2, "Right": cw - run}.get(lp.get("HorizontalAlignment", "Left"), 0.0)
            for c, (w_, h_) in zip(children, sizes):
                if vertical:
                    al = lp.get("HorizontalAlignment", "Center")
                    xx = cx + {"Left": 0, "Center": (cw - w_) / 2, "Right": cw - w_}.get(al, 0)
                    self.place(c, (xx, cy + cursor, w_, h_), clip, f"{path}.{c['Name']}")
                    cursor += h_ + gap
                else:
                    al = lp.get("VerticalAlignment", "Center")
                    yy = cy + {"Top": 0, "Center": (ch - h_) / 2, "Bottom": ch - h_}.get(al, 0)
                    self.place(c, (cx + cursor, yy, w_, h_), clip, f"{path}.{c['Name']}")
                    cursor += w_ + gap
        else:
            for c in children:
                p = c.get("Properties", {})
                w_, h_ = self.size_of(c, cw, ch)
                (px, pox), (py, poy) = udim2(p.get("Position"), ((0, 0), (0, 0)))
                ax, ay = (p.get("AnchorPoint") or {}).get("Vector2", (0, 0))
                xx = cx + cw * px + pox - ax * w_
                yy = cy + ch * py + poy - ay * h_
                self.place(c, (xx, yy, w_, h_), clip, f"{path}.{c['Name']}")


def intersect(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return (x0, y0, max(0, x1 - x0), max(0, y1 - y0))


def overlaps(a, b):
    r = intersect(a, b)
    return r[2] > 0.5 and r[3] > 0.5


def wrap(text, fnt, width):
    lines = []
    for para in text.split("\n"):
        words = para.split(" ")
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if fnt.getlength(test) <= width or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def screen_attrs(model):
    return ((model.get("Properties") or {}).get("Attributes") or {}).get("Attributes") or {}


def world_backdrop(sw, sh, mood):
    """a faint game world so translucent panels read: a sky + ground, or a dark one for a dark identity"""
    img = Image.new("RGBA", (sw, sh), (58, 74, 92, 255))
    d0 = ImageDraw.Draw(img)
    for yy in range(sh):
        k = yy / sh
        if mood == "dark":
            col = (int(26 + 18 * k), int(24 + 14 * k), int(22 + 10 * k), 255) if k < 0.62 else (20, 18, 15, 255)
        elif mood == "sunny":
            # a toy world: a bright sky down to a green meadow
            if k < 0.62:
                col = (int(96 + 70 * k), int(176 + 40 * k), int(236 - 20 * k), 255)
            else:
                col = (int(104 - 30 * (k - 0.62)), int(186 - 40 * (k - 0.62)), 84, 255)
        else:
            col = (int(70 + 60 * k), int(96 + 50 * k), int(128 + 20 * k), 255) if k < 0.62 else (64, 88, 60, 255)
        d0.line([(0, yy), (sw, yy)], fill=col)
    return img


ALL_BOXES = {}  # the last drawn layout's EVERY node box, path -> (x, y, w, h) in screen px (the verifier crops by it)
LAST_BOXES = {}  # the last drawn layout's content boxes, path -> (x, y, w, h) as fractions of the screen


def squeezed(desk, small, label):
    """pieces that COLLIDE on a smaller viewport but stand apart on desktop: the layout was squeezed (a card over the
    list on a phone), not designed to overlap (an emblem on its card overlaps everywhere)"""
    def inter(a, b):
        w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
        h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
        return max(0.0, w) * max(0.0, h)
    out = []
    paths = sorted(p for p in small if p in desk)
    for i, pa in enumerate(paths):
        for pb in paths[i + 1:]:
            if pb.startswith(pa + ".") or pa.startswith(pb + "."):
                continue
            a, b = small[pa], small[pb]
            # (what a squeeze RUINS is reading: text against text, or text against a small picture — an icon, an
            # emblem; text over a ground — rays, a burst, a plate — is designed)
            if not (a[4] or b[4]):
                continue
            if not (a[4] and b[4]):
                txt, pic = (a, b) if a[4] else (b, a)
                if pic[2] * pic[3] > 2 * txt[2] * txt[3]:
                    continue
            least = min(a[2] * a[3], b[2] * b[3])
            if least <= 0:
                continue
            da, db = desk[pa], desk[pb]
            dleast = min(da[2] * da[3], db[2] * db[3]) or least
            if inter(a, b) > 0.15 * least and inter(da, db) <= 0.02 * dleast:
                out.append(("squeeze", pa, f"collides with {pb} on the {label} ({int(100 * inter(a, b) / least)}% of the smaller) but not on desktop — "
                                           f"the layout is squeezed: lower the {label} scale, move one (at.{label}.pos) or group them"))
    return out


def path_points(enc, smooth=True):
    """Kit_Path "x,y;..." (shares of the box) -> points, a smooth one sampled as the Catmull-Rom curve Ui.path draws"""
    pts = []
    for pair in str(enc or "").split(";"):
        if "," in pair:
            a, b = pair.split(",", 1)
            pts.append((float(a), float(b)))
    if not smooth or len(pts) < 3:
        return pts
    out = []
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = pts[max(0, i - 1)], pts[i], pts[i + 1], pts[min(len(pts) - 1, i + 2)]
        for s in range(12):
            t = s / 12
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * p1[k] + (p2[k] - p0[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (3 * p1[k] - p0[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    out.append(pts[-1])
    return out


def path_cut(pts, share):
    """the first `share` of a polyline's length"""
    if share >= 1 or len(pts) < 2:
        return pts
    segs = [math.dist(pts[i - 1], pts[i]) for i in range(1, len(pts))]
    want, run, out = sum(segs) * max(0.0, share), 0.0, [pts[0]]
    for i, sg in enumerate(segs, 1):
        if run + sg >= want:
            f = (want - run) / sg if sg else 0
            out.append((pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f))
            return out
        run += sg
        out.append(pts[i])
    return out


def path_layer(enc, w, h, thickness, hexcol, smooth, closed, share=1.0):
    """(RGBA image of the node's box + a margin, the margin) with its vector line drawn, or None"""
    pts = path_points(enc, smooth)
    if len(pts) < 2 or share <= 0:
        return None
    S = 4
    th = max(1.0, float(thickness))
    m = int(th) + 2
    big = Image.new("RGBA", (int((w + 2 * m) * S), int((h + 2 * m) * S)), (0, 0, 0, 0))
    px = [((m + p[0] * w) * S, (m + p[1] * h) * S) for p in path_cut(pts, share)]
    if closed:
        px.append(px[0])
    col = tuple(int(hexcol[i:i + 2], 16) for i in (1, 3, 5)) + (255,)
    dd = ImageDraw.Draw(big)
    dd.line(px, fill=col, width=max(1, int(th * S)), joint="curve")
    r_ = th * S / 2
    for q in (px[0], px[-1]):  # (round caps, like the engine's stroke ends)
        dd.ellipse([q[0] - r_, q[1] - r_, q[0] + r_, q[1] + r_], fill=col)
    return big.resize((int(w + 2 * m), int(h + 2 * m)), Image.LANCZOS), m


def wcag_lum(arr):
    """WCAG relative luminance of an (..., 3) 0..255 array"""
    import numpy as np
    c = np.asarray(arr, dtype=np.float64) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def ImageChops_subtract(a, b):
    from PIL import ImageChops
    return ImageChops.subtract(a, b)


def busy_contrast(img, layer, box, color, ring=None):
    """the text colour's contrast against the WORST 10% of what is behind its box (the composed screen so far + the
    node's own fill); None when the ground is calm (one colour: the compiler's contrast gate already measures it)"""
    import numpy as np
    x, y, w, h = (int(v) for v in box)
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(img.width, x + w), min(img.height, y + h)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    behind = Image.alpha_composite(img.crop((x0, y0, x1, y1)).convert("RGBA"), layer.crop((x0, y0, x1, y1)))
    lum = wcag_lum(np.asarray(behind)[..., :3])
    if ring is not None:  # (only the ground right around the glyphs' strokes: the glyph mask grown 4 px, minus itself)
        g = ring.crop((x0, y0, x1, y1))
        keep = np.asarray(ImageChops_subtract(g.filter(ImageFilter.MaxFilter(9)), g)) > 0
        if keep.sum() < 8:
            return None
        lum = lum[keep]
    if lum.std() < 0.04:
        return None
    t = float(wcag_lum(np.array(color[:3]).reshape(1, 3))[0])
    hi, lo = np.maximum(lum, t), np.minimum(lum, t)
    ratio = (hi + 0.05) / (lo + 0.05)
    return float(np.percentile(ratio, 10))


def layout_screen(model, sw, sh, inset_px=None):
    """the engine's layout of a compiled ScreenGui at sw x sh, nothing drawn -> Layout (lay.order: every node's box).
    draw_screen paints from it; kit/ui/align.py measures near-misses on it without the cost of a drawing"""
    attrs = screen_attrs(model)
    lay = Layout(sw, sh)
    # the safe area the screen laid itself out in: CoreUISafeInsets and TopbarSafeInsets keep clear of the Roblox
    # buttons (the top bar); DeviceSafeInsets / None cover the whole screen
    insets = (attrs.get("Kit_Insets") or {}).get("String", "DeviceSafeInsets")
    top = int(round(inset_px if inset_px is not None else TOPBAR[3]))
    side = int(round(TOPBAR[2] * top / TOPBAR[3]))  # the buttons' width, in this drawing's pixels
    if insets == "CoreUISafeInsets":
        ox0, oy0, lw, lh = 0, top, sw, sh - top
    elif insets == "TopbarSafeInsets":
        ox0, oy0, lw, lh = side, 0, sw - 2 * side, top  # the strip beside the Roblox buttons
    else:
        ox0, oy0, lw, lh = 0, 0, sw, sh
    roots = [c for c in model.get("Children") or [] if c.get("ClassName") in GUI]
    for r in roots:
        p = r.get("Properties", {})
        if p.get("Visible", True) is False:
            continue
        w, h = lay.size_of(r, lw, lh)
        (px, pox), (py, poy) = udim2(p.get("Position"), ((0, 0), (0, 0)))
        ax, ay = (p.get("AnchorPoint") or {}).get("Vector2", (0, 0))
        lay.place(r, (ox0 + lw * px + pox - ax * w, oy0 + lh * py + poy - ay * h, w, h), None, r["Name"])
    return lay


def desktop_boxes(model):
    """every node's box on the DESKTOP frame, exactly as the preview's <Screen>.boxes.json holds it (the desktop "at"
    overrides and the screen's desktop scale applied), with no drawing -> {path: (x, y, w, h)}; a world screen (a
    BillboardGui / SurfaceGui) at its canvas size, as world_sheet lays it out"""
    if model.get("ClassName") in ("BillboardGui", "SurfaceGui"):
        p = model.get("Properties") or {}
        if model.get("ClassName") == "SurfaceGui":
            cw, ch = (p.get("CanvasSize") or {}).get("Vector2") or [400, 200]
        else:
            (_, cw), (_, ch) = (p.get("Size") or {}).get("UDim2") or [[0, 200], [0, 60]]
        lay = layout_screen(model, max(1, int(cw)), max(1, int(ch)), inset_px=0)
        return {pth: tuple(round(v, 1) for v in bx) for _ins, bx, _c, pth in lay.order}
    label, sw, sh, _ = VIEWPORTS[0]
    m = with_at(model, label)
    s = viewport_scale(m, label)
    if abs(s - 1) < 1e-6:
        lay = layout_screen(m, sw, sh)
    else:
        lay = layout_screen(m, int(round(sw / s)), int(round(sh / s)), inset_px=TOPBAR[3] / s)
    return {pth: tuple(round(v, 1) for v in bx) for _ins, bx, _c, pth in lay.order}


def draw_screen(model, sw, sh, anim=None, inset_px=None, bare=False):
    """-> (PIL image, checks); anim(path, inst) -> {alpha, scale, dx, dy, text, wipe} at one instant (motion strips);
    inset_px: the top-bar inset in THIS drawing's pixels (a scaled viewport draws in a 1/s world: the engine's
    58 px stay 58 screen pixels, so the caller passes 58 / s)"""
    attrs = screen_attrs(model)
    bg_tok = (attrs.get("Kit_bg") or {}).get("String")
    mood = "dark" if bg_tok and sum(int(bg_tok[i:i + 2], 16) for i in (1, 3, 5)) < 120 else "light"
    # the identity's own words about its world win over the bg token (a candy-bright game with a navy scrim)
    world = ((attrs.get("Kit_World") or {}).get("String") or "").lower()
    if any(w in world for w in ("sunny", "bright", "day", "toy", "candy", "pastel", "cheerful")):
        mood = "sunny"
    elif any(w in world for w in ("dark", "night", "gloom", "ash", "ruin", "grim", "dusk")):
        mood = "dark"
    img = world_backdrop(sw, sh, mood) if not bare else Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    # the identity's own world picture (assets/ui/art/<identity>/world.png, a screenshot of the game) replaces the
    # painted gradient: the screen is judged over the game it ships in
    identity = (attrs.get("Kit_Identity") or {}).get("String")
    world_pic = ground_image(identity) if identity and not bare else None
    if world_pic is not None:
        k = max(sw / world_pic.width, sh / world_pic.height)
        fitted = world_pic.resize((max(1, int(world_pic.width * k)), max(1, int(world_pic.height * k))), Image.LANCZOS)
        img = Image.new("RGBA", (sw, sh), (0, 0, 0, 255))
        img.paste(fitted, ((sw - fitted.width) // 2, (sh - fitted.height) // 2))
    # a menu "backdrop" (v7.4): the world behind it blurred, darkened and drained of colour, as Ui.backdrop does in game
    bd = (attrs.get("Kit_Backdrop") or {}).get("String")
    if bd and not bare:
        v = {k: float(x) for k, x in (pair.split("=") for pair in bd.split(",") if "=" in pair)}
        from PIL import ImageEnhance
        base = img.convert("RGB").filter(ImageFilter.GaussianBlur(v.get("blur", 18) * 0.5 * sw / 1920))
        base = ImageEnhance.Color(base).enhance(max(0.0, 1 + v.get("sat", -0.4)))
        base = ImageEnhance.Brightness(base).enhance(max(0.0, 1 - v.get("darken", 0.35)))
        img = base.convert("RGBA")
    lay = layout_screen(model, sw, sh, inset_px)
    checks, gone = [], []
    LAST_BOXES.clear()
    canvas_alpha = {}
    for inst, _, _, path in lay.order:
        if inst.get("ClassName") == "CanvasGroup":
            canvas_alpha[path] = 1 - (inst.get("Properties", {}).get("GroupTransparency") or 0)

    def group_alpha(path):
        k = 1.0
        for cpath, a in canvas_alpha.items():
            if path == cpath or path.startswith(cpath + "."):
                k *= a
        return k

    # every node's box and rotation, for INHERITED rotation: the engine turns a rotated frame's children with it
    # (a leaning bar's fill leans too) — each layer turns about every rotated ancestor's centre, nearest first
    boxes = {pth: (bx, (ins.get("Properties", {}).get("Rotation") or 0)) for ins, bx, _c, pth in lay.order}
    ALL_BOXES.clear()
    ALL_BOXES.update({pth: tuple(round(v, 1) for v in bx) for pth, (bx, _r) in boxes.items()})
    for inst, (x, y, w, h), clip, path in lay.paint_order():
        cls = inst["ClassName"]
        p = inst.get("Properties", {})
        state = anim(path, inst) if anim else None
        if state:
            # one instant of a choreography: scale about the centre, slide, clip (wipe), partial text (typewriter)
            if state.get("alpha", 1) <= 0.001:
                continue
            s = state.get("scale", 1)
            if s != 1:
                cx_, cy_ = x + w / 2, y + h / 2
                w, h = w * s, h * s
                x, y = cx_ - w / 2, cy_ - h / 2
            x, y = x + state.get("dx", 0), y + state.get("dy", 0)
            if clip is not None and (state.get("cdx") or state.get("cdy")):
                # an ancestor slid: the clip it imposes slides with it (a sliding card keeps its trail inside)
                clip = (clip[0] + state.get("cdx", 0), clip[1] + state.get("cdy", 0), clip[2], clip[3])
            if state.get("wipe", 1) < 1:
                wrect = (x, y, w * state["wipe"], h)
                clip = wrect if clip is None else intersect(clip, wrect)
            if state.get("text") is not None:
                p = dict(p)
                p["Text"] = state["text"]
        layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        corner = one(inst, "UICorner")
        radius = 0
        if corner:
            s_, o_ = udim(corner.get("Properties", {}).get("CornerRadius"))
            radius = min(w, h) * s_ + o_
        radius = max(0, min(radius, min(w, h) / 2))
        box = [x, y, x + max(w, 1) - 1, y + max(h, 1) - 1]
        grad = one(inst, "UIGradient")
        bt = p.get("BackgroundTransparency", 0)
        if bt < 1 and w > 0 and h > 0:
            bg = c3(p.get("BackgroundColor3"))
            if grad:
                g = gradient_layer(w, h, grad)
                g = tint(g, bg, bt)
                mask = Image.new("L", (int(w), int(h)), 0)
                ImageDraw.Draw(mask).rounded_rectangle([0, 0, int(w) - 1, int(h) - 1], radius=radius, fill=255)
                ga = g.getchannel("A")
                g.putalpha(Image.composite(ga, mask, mask))
                layer.alpha_composite(g, (int(x), int(y)))
            else:
                d.rounded_rectangle(box, radius=radius, fill=bg + (int(255 * (1 - bt)),))
        stroke = None
        text_outline = None
        for st in kids(inst, "UIStroke"):
            if st.get("Properties", {}).get("ApplyStrokeMode") == "Contextual" and cls in TEXT:
                text_outline = st
            else:
                stroke = st
        if stroke and w > 0 and h > 0:
            sp = stroke.get("Properties", {})
            scol = c3(sp.get("Color"), (0, 0, 0))
            sgrad = one(stroke, "UIGradient")
            if sgrad:
                cs = seq_colors(sgrad)
                scol = cs[0][1] if cs else scol
            alpha = int(255 * (1 - (sp.get("Transparency") or 0)))
            th = max(1, round(sp.get("Thickness", 1)))
            d.rounded_rectangle([x - th / 2, y - th / 2, x + w + th / 2 - 1, y + h + th / 2 - 1], radius=radius + th / 2, outline=scol + (alpha,), width=th)
        # a VECTOR line (a "path" node: Kit_Path, the Path2D Ui.path builds) — drawn to Kit_PathT of its length (the reel's
        # draw-on), anti-aliased at 4x
        if attr(inst, "Kit_Path") and w > 0 and h > 0:
            share = attr(inst, "Kit_PathT")
            share = 1.0 if share is None else float(share)
            th_ = attr(inst, "Kit_PathThickness") or 4
            closed_ = bool(attr(inst, "Kit_PathClosed")) and share >= 1
            smooth_ = attr(inst, "Kit_PathSmooth") is not False
            strokes = []
            ol_ = attr(inst, "Kit_PathOutline")
            if ol_:  # (the darker, wider stroke under the line)
                oc_, _, opx_ = str(ol_).partition(",")
                strokes.append((th_ + 2 * float(opx_ or 2), oc_))
            strokes.append((th_, attr(inst, "Kit_PathColor") or "#ffffff"))
            for thk, colr in strokes:
                pl = path_layer(attr(inst, "Kit_Path"), w, h, thk, colr, smooth_, closed_, share)
                if pl is not None:
                    m_ = int(pl[1])
                    layer.alpha_composite(pl[0], (max(0, int(x) - m_), max(0, int(y) - m_)))
        if cls in ("ImageLabel", "ImageButton") and w > 0 and h > 0:
            art = art_image(attr(inst, "KitArt"))
            if art is not None:
                col = c3(p.get("ImageColor3"), (255, 255, 255))
                img_t = p.get("ImageTransparency", 0) or 0
                if p.get("ScaleType") == "Slice" and p.get("SliceCenter"):
                    pic = nine_slice(art, w, h, p["SliceCenter"]["Rect"])
                elif p.get("ScaleType") == "Fit":
                    # the engine's Fit keeps the art's aspect inside the box (a wide strip stays wide)
                    kf = min(w / max(1, art.width), h / max(1, art.height))
                    fw, fh = max(1, int(art.width * kf)), max(1, int(art.height * kf))
                    pic = Image.new("RGBA", (max(1, int(w)), max(1, int(h))))
                    pic.paste(art.resize((fw, fh), Image.LANCZOS), (int((w - fw) / 2), int((h - fh) / 2)))
                elif p.get("ScaleType") == "Tile":
                    (tsx, tox), (tsy, toy) = udim2(p.get("TileSize"), ((0, art.width), (0, art.height)))
                    tw, th = max(1, int(w * tsx + tox)), max(1, int(h * tsy + toy))
                    tile_im = art.resize((tw, th), Image.LANCZOS)
                    pic = Image.new("RGBA", (max(1, int(w)), max(1, int(h))))
                    for ty in range(0, int(h), th):
                        for tx in range(0, int(w), tw):
                            pic.paste(tile_im, (tx, ty))
                else:
                    pic = art.resize((max(1, int(w)), max(1, int(h))), Image.LANCZOS)
                pic = tint(pic, col, img_t)
                if grad and seq_alpha(grad):
                    ga = gradient_layer(w, h, grad).getchannel("A")
                    pa = pic.getchannel("A")
                    from PIL import ImageChops
                    pic.putalpha(ImageChops.multiply(pa, ga))
                layer.alpha_composite(pic, (int(x), int(y)))
            elif p.get("Image", None) != "":
                # an image the kit cannot show (an asset id): a labelled placeholder — a plate-backed imagebutton
                # (Image "") is drawn by its Plate child and gets none
                d.rounded_rectangle(box, radius=radius, outline=(200, 200, 210, 140), width=1)
                d.line([(x + 4, y + 4), (x + w - 4, y + h - 4)], fill=(200, 200, 210, 90))
                d.line([(x + 4, y + h - 4), (x + w - 4, y + 4)], fill=(200, 200, 210, 90))
        if cls == "ScrollingFrame" and h > 12:
            d.rectangle([x + w - 6, y + 2, x + w - 2, y + min(h - 2, max(20, h * 0.4))], fill=(200, 200, 200, 160))
        if cls in TEXT:
            text = p.get("Text", "")
            if p.get("RichText"):
                import re
                text = re.sub(r"<[^>]+>", "", text)
            placeholder = False
            if cls == "TextBox" and not text:
                text, placeholder = p.get("PlaceholderText", ""), True
            size = int(p.get("TextSize", 14))
            if p.get("TextScaled"):
                # the engine fits the text to its box; the compiler kept the asked size in Kit_TextSize
                size = int(attr(inst, "Kit_TextSize") or max(8, h / 1.2))
            fnt = font(p.get("Font", "GothamMedium"), size)
            color = (178, 178, 178) if placeholder else c3(p.get("TextColor3"), (27, 42, 53))
            text_a = int(255 * (1 - min(1.0, max(0.0, p.get("TextTransparency") or 0))))
            tgrad = None
            for g in kids(inst, "UIGradient"):
                if g.get("Name") == "TextGradient":
                    tgrad = g
            if tgrad and seq_colors(tgrad):
                color = seq_colors(tgrad)[0][1]
            lines = wrap(text, fnt, max(1, w - 4)) if p.get("TextWrapped") else [text]
            line_h = size * 1.2
            total = line_h * len(lines)
            ty = y + (h - total) / 2
            xalign = p.get("TextXAlignment", "Center")
            outline = None
            if text_outline:
                op = text_outline.get("Properties", {})
                outline = (c3(op.get("Color"), (0, 0, 0)) + (int(255 * (1 - (op.get("Transparency") or 0))),), max(1, round(op.get("Thickness", 1))))
            busy_ok = bool(text.strip() and not placeholder and text_a > 200 and w > 4 and h > 4 and not (outline and outline[1] >= 2)
                           and not str(inst.get("Name") or "").startswith("Fx_"))
            gmask = Image.new("L", (sw, sh), 0) if busy_ok else None  # (the glyphs alone: the busy-ground check measures around them)
            gmd = ImageDraw.Draw(gmask) if gmask is not None else None
            for ln in lines:
                lw = fnt.getlength(ln)
                tx = x + 2 if xalign == "Left" else (x + w - lw - 2 if xalign == "Right" else x + (w - lw) / 2)
                pos = (tx, ty + (line_h - size) / 2 - size * 0.12)
                if outline:
                    d.text(pos, ln, font=fnt, fill=color + (text_a,), stroke_width=outline[1], stroke_fill=(outline[0][:3] + (min(outline[0][3], text_a),)))
                else:
                    d.text(pos, ln, font=fnt, fill=color + (text_a,))
                if gmd is not None:
                    gmd.text(pos, ln, font=fnt, fill=255)
                ty += line_h
            # XAG 102: text over a BUSY ground (the world, a picture) is measured against the lowest-contrast part of
            # the ground right AROUND its strokes, not the box's average (a white word over a sky with one bright cloud
            # fails on the cloud; a dark letter on an amber diamond does not fail on the box corners outside it)
            if busy_ok and gmask is not None:
                worst = busy_contrast(img, layer, (x, y, w, h), color, gmask)
                bar = 3.0 if size >= 24 else 4.5  # (WCAG / XAG: large text, 24 px and up, needs 3:1; body text 4.5:1)
                if worst is not None and worst < bar:
                    checks.append(("busy_contrast", path, f"over its busy ground the text reaches only {worst:.1f}:1 (bar {bar:g}:1) at the worst 10% "
                                   "(XAG 102: measure against the lowest-contrast part) — give it a textOutline, a plate behind it, or a calmer spot"))
            # a transparency gradient on TEXT (an fx band, a burn-in wipe) fades the glyphs where it is clear
            band = next((g for g in kids(inst, "UIGradient") if g.get("Name") != "TextGradient" and seq_alpha(g)), None)
            if band is not None and w > 0 and h > 0:
                ga = Image.new("L", (sw, sh), 0)
                ga.paste(gradient_layer(w, h, band).getchannel("A"), (int(x), int(y)))
                from PIL import ImageChops
                layer.putalpha(ImageChops.multiply(layer.getchannel("A"), ga))
            if text and (total > h + 1 or any(fnt.getlength(ln) > w + 1 for ln in lines)):
                checks.append(("text_overflow", path, f"text needs {int(total)}px tall x {int(max(fnt.getlength(ln) for ln in lines))}px wide, box is {int(w)}x{int(h)} — enlarge the box, shorten the text or lower textSize"))
        # a native UIShadow (the engine's drop shadow, 2026): under the node — from the node's box (Mode Shape) or from
        # its drawn glyphs / picture (Mode Text on a text node; an image's own alpha): blurred by BlurRadius, moved by
        # Offset, grown by Spread, in Color at Transparency. (an approximation of the engine; the booth is the proof)
        for sh_ in kids(inst, "UIShadow"):
            sp_ = sh_.get("Properties", {})
            if sp_.get("Enabled") is False or w <= 0 or h <= 0:
                continue
            mode_ = sp_.get("Mode") or "Shape"
            if (mode_ == "Text" and cls in TEXT) or cls in ("ImageLabel", "ImageButton"):
                src_a = layer.getchannel("A")
            else:
                src_a = Image.new("L", (sw, sh), 0)
                ImageDraw.Draw(src_a).rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=radius, fill=255)
            br_ = (sp_.get("BlurRadius") or {}).get("UDim", [0, 6])
            blur_ = max(0.0, float(br_[1]) + float(br_[0]) * min(w, h))
            off_ = (sp_.get("Offset") or {}).get("UDim2", [[0, 0], [0, 4]])
            dx_s, dy_s = off_[0][1] + off_[0][0] * w, off_[1][1] + off_[1][0] * h
            spr_ = (sp_.get("Spread") or {}).get("UDim2", [[0, 0], [0, 0]])
            grow_ = int(max(spr_[0][1] + spr_[0][0] * w, spr_[1][1] + spr_[1][0] * h) / 2)
            if grow_ > 0:
                src_a = src_a.filter(ImageFilter.MaxFilter(2 * grow_ + 1))
            if blur_ > 0:
                src_a = src_a.filter(ImageFilter.GaussianBlur(blur_ / 2))
            k_ = 1 - (sp_.get("Transparency") or 0)
            src_a = src_a.point(lambda v, k_=k_: int(v * k_))
            shade = Image.new("RGBA", (sw, sh), c3(sp_.get("Color"), (0, 0, 0)) + (0,))
            shade.putalpha(src_a)
            under = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
            under.alpha_composite(shade, (int(round(dx_s)), int(round(dy_s))) if dx_s >= 0 and dy_s >= 0 else (0, 0))
            if dx_s < 0 or dy_s < 0:  # (alpha_composite takes no negative offsets: shift by cropping)
                under = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
                cut_ = shade.crop((max(0, int(-dx_s)), max(0, int(-dy_s)), sw, sh))
                under.alpha_composite(cut_, (max(0, int(dx_s)), max(0, int(dy_s))))
            under.alpha_composite(layer)
            layer = under
        rot = p.get("Rotation") or 0
        if rot and w > 0 and h > 0:
            cx_, cy_ = x + w / 2, y + h / 2
            layer = layer.rotate(-rot, center=(cx_, cy_), resample=Image.BICUBIC)
        fade = group_alpha(path) * (state.get("alpha", 1) if state else 1)
        if fade < 1:
            a_ = layer.getchannel("A").point(lambda v: int(v * fade))
            layer.putalpha(a_)
        if clip is not None:
            mask = Image.new("L", (sw, sh), 0)
            ImageDraw.Draw(mask).rectangle([clip[0], clip[1], clip[0] + clip[2], clip[1] + clip[3]], fill=255)
            alpha = layer.getchannel("A")
            layer.putalpha(Image.composite(alpha, mask, mask))
        # inherited rotation: every rotated ancestor's turn composed into ONE affine map, applied to the drawn box only
        M = None
        anc = path.rpartition(".")[0]
        while anc:
            info = boxes.get(anc)
            if info and info[1]:
                (ax, ay, aw, ah), arot = info
                t = math.radians(arot)
                cx_, cy_ = ax + aw / 2, ay + ah / 2
                c_, s_ = math.cos(t), math.sin(t)
                # clockwise on screen (y down): p' = c + R (p - c), R = [[c, -s], [s, c]]
                Ri = (c_, -s_, cx_ - c_ * cx_ + s_ * cy_, s_, c_, cy_ - s_ * cx_ - c_ * cy_)
                M = Ri if M is None else (
                    Ri[0] * M[0] + Ri[1] * M[3], Ri[0] * M[1] + Ri[1] * M[4], Ri[0] * M[2] + Ri[1] * M[5] + Ri[2],
                    Ri[3] * M[0] + Ri[4] * M[3], Ri[3] * M[1] + Ri[4] * M[4], Ri[3] * M[2] + Ri[4] * M[5] + Ri[5])
            anc = anc.rpartition(".")[0]
        if M is not None:
            bb = layer.getbbox()
            if bb:
                src = layer.crop(bb)
                corners = [(bb[0], bb[1]), (bb[2], bb[1]), (bb[0], bb[3]), (bb[2], bb[3])]
                mapped = [(M[0] * px + M[1] * py + M[2], M[3] * px + M[4] * py + M[5]) for px, py in corners]
                ox, oy = math.floor(min(q[0] for q in mapped)), math.floor(min(q[1] for q in mapped))
                ow = math.ceil(max(q[0] for q in mapped)) - ox
                oh = math.ceil(max(q[1] for q in mapped)) - oy
                det = M[0] * M[4] - M[1] * M[3]
                ia, ib, id_, ie = M[4] / det, -M[1] / det, -M[3] / det, M[0] / det
                # output (u, v) -> global (u + ox, v + oy) -> source global (inverse) -> source crop
                gx, gy = ox - M[2], oy - M[5]
                data = (ia, ib, ia * gx + ib * gy - bb[0], id_, ie, id_ * gx + ie * gy - bb[1])
                piece = src.transform((max(1, ow), max(1, oh)), Image.AFFINE, data, resample=Image.BICUBIC)
                # (off-screen parts cut away: alpha_composite takes no negative offsets)
                cut_x, cut_y = max(0, -ox), max(0, -oy)
                if cut_x < piece.width and cut_y < piece.height:
                    piece = piece.crop((cut_x, cut_y, piece.width, piece.height))
                    dx_, dy_ = ox + cut_x, oy + cut_y
                    if dx_ < sw and dy_ < sh:
                        piece = piece.crop((0, 0, min(piece.width, sw - dx_), min(piece.height, sh - dy_)))
                        img.alpha_composite(piece, (dx_, dy_))
        else:
            img.alpha_composite(layer)
        # measured layout checks
        hidden_parent = any(path.startswith(o + ".") for o in gone)
        # (only what SHOWS: text with words that is not transparent, a picture that has an image — an empty label or an
        # image-less container box collides with nothing a player sees)
        # (an fx layer — Fx_Shimmer, Fx_Ping... — is a copy of its own node: never a piece that collides)
        shows = not str(inst.get("Name") or "").startswith("Fx_") and bool((cls in TEXT and str(p.get("Text") or "").strip() and (p.get("TextTransparency") or 0) < 0.95) or (
            cls in ("ImageLabel", "ImageButton") and (p.get("Image") or (((p.get("Attributes") or {}).get("Attributes") or {}).get("KitArt")))))
        if shows and w > 0 and h > 0 and w * h < 0.6 * sw * sh:
            LAST_BOXES[path] = (x / sw, y / sh, w / sw, h / sh, cls in TEXT)  # (the squeeze check compares viewports in screen fractions)
        if w > 0 and h > 0 and not overlaps((x, y, w, h), (0, 0, sw, sh)):
            gone.append(path)
            if not hidden_parent:
                checks.append(("offscreen", path, f"entirely off the {sw}x{sh} screen at {int(x)},{int(y)} — invisible. Hugging an edge? pos [24, \"100%-24\"] + anchor \"bottomleft\""))
        elif cls in INTERACTIVE or cls in TEXT:
            if w > 0 and h > 0 and (x < -1 or y < -1 or x + w > sw + 1 or y + h > sh + 1):
                checks.append(("offscreen", path, f"{int(x)},{int(y)} {int(w)}x{int(h)} goes past the {sw}x{sh} screen — anchor it to the edge it hugs (pos + anchor) or use % sizes"))
        if cls in INTERACTIVE and clip is None and overlaps((x, y, w, h), TOPBAR):
            checks.append(("topbar", path, "sits under Roblox's menu/chat buttons (top-left 260x58) — move it down/right or anchor elsewhere"))
        # PHONE THUMB REACH (v7.11): held in landscape, the thumbs live in the bottom corners; the top middle is the
        # hardest reach — a control centred there is a stretch every time
        if cls in INTERACTIVE and sw < 900 and w > 0 and h > 0:
            cx_t, cy_t = x + w / 2, y + h / 2
            if cy_t < sh * 0.33 and sw * 0.3 < cx_t < sw * 0.7 and not str(inst.get("Name") or "").lower().startswith("close"):
                checks.append(("thumb_reach", path, "centred in the phone's hardest reach (the top middle, far from both thumbs) — "
                               "move the action toward a lower corner, or keep only rare actions up there"))
        # CONSOLE / TV (v7.11): a "console" screen keeps its text and controls inside the TV's title-safe 90% and its
        # words at least 24 px (read from 3 m away)
        if (screen_attrs(model).get("Kit_Console") or {}).get("Bool") and sw >= 1900 and w > 0 and h > 0 \
                and (cls in TEXT or cls in INTERACTIVE) and not str(inst.get("Name") or "").startswith("Fx_"):
            mx, my = sw * 0.05, sh * 0.05
            if x < mx or y < my or x + w > sw - mx or y + h > sh - my:
                checks.append(("title_safe", path, "outside the TV's title-safe area (the inner 90%) — overscan can cut it off: "
                               "move it inside a 5% margin"))
            if cls in TEXT and str(p.get("Text") or "").strip() and int(p.get("TextSize", 14)) < 24:
                checks.append(("tv_text", path, f"{int(p.get('TextSize', 14))}px text on a TV read from 3 m — use >= 24px"))
        if cls in INTERACTIVE and sw < 900 and 0 < h < 44:
            checks.append(("touch_target", path, f"only {int(h)}px tall on a phone — use ≥ 44px (fixed pixels, not a % of a small parent)"))
    # the empty-panel check (desktop only — phone reflows hide children on purpose): a panel with a visible ground
    # (a fill or a full-size plate) whose content covers under half of it is a judge's "dead cream": shrink it,
    # fill it, or make the content bigger. Full-size children (the plate, a texture, a backdrop) are not content.
    if sw >= 1900:
        placed = [(inst, box, path) for inst, box, _, path in lay.order]
        for inst, (x, y, w, h), path in placed:
            if inst.get("ClassName") != "Frame" or w * h < 160 * 120 or path in gone or w * h >= 0.9 * sw * sh:
                continue  # (a full-screen frame is a scrim or the root, not a panel)
            p = inst.get("Properties", {})
            grounded = (p.get("BackgroundTransparency") or 0) < 0.5 or any(
                c.get("ClassName") == "ImageLabel" and c.get("Name") in ("Plate", "Shadow") for c in inst.get("Children") or [])
            if not grounded:
                continue
            union = None
            for cinst, (cx, cy, cw, ch), cpath in placed:
                if not cpath.startswith(path + ".") or cw <= 0 or ch <= 0 or cinst.get("ClassName") not in GUI:
                    continue
                attrs_c = ((cinst.get("Properties", {}).get("Attributes") or {}).get("Attributes") or {})
                is_content = (attrs_c.get("Kit_Content") or {}).get("Bool") is True
                if cw * ch >= 0.85 * w * h and not is_content:
                    continue  # the plate / a texture / a scrim: ground, not content (a map / a picture says Kit_Content)
                if cinst.get("Properties", {}).get("Visible", True) is False:
                    continue
                bx0, by0 = max(cx, x), max(cy, y)
                bx1, by1 = min(cx + cw, x + w), min(cy + ch, y + h)
                if bx1 <= bx0 or by1 <= by0:
                    continue
                union = (bx0, by0, bx1, by1) if union is None else (min(union[0], bx0), min(union[1], by0), max(union[2], bx1), max(union[3], by1))
            if union is None:
                continue
            cover = (union[2] - union[0]) * (union[3] - union[1]) / float(w * h)
            if cover < 0.5:
                checks.append(("empty_panel", path, f"{int((1 - cover) * 100)}% of the panel is empty — shrink it to its content, fill it, or make the content bigger (judges call this dead space)"))
    if bare:  # (a world billboard / surface: no Roblox top bar over it)
        return img, [c for c in checks if c[0] != "topbar"]
    tb = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    ImageDraw.Draw(tb).rectangle([TOPBAR[0], TOPBAR[1], TOPBAR[2], TOPBAR[3]], fill=(255, 60, 60, 46), outline=(255, 90, 90, 150))
    img.alpha_composite(tb)
    return img, checks


def viewport_scale(model, label):
    """the screen's own scale for this viewport (spec "scale": {"phone": 0.72}): the runtime applies it as a UIScale"""
    v = screen_attrs(model).get(f"Kit_Scale_{label}")
    return float(v.get("Float64", 1)) if isinstance(v, dict) else 1.0


def parse_at(text):
    """the compiler's Kit_At_<viewport> attribute -> model property overrides"""
    out = {}
    for item in text.split("|"):
        if "=" not in item:
            continue
        key, val = item.split("=", 1)
        if key in ("Size", "Position"):
            nums = [float(v) for v in val.split(",")]
            if len(nums) == 4:
                out[key] = {"UDim2": [[nums[0], nums[1]], [nums[2], nums[3]]]}
        elif key == "TextSize":
            out["TextSize"] = float(val)
        elif key == "Visible":
            out["Visible"] = val == "true"
        elif key == "Anchor":
            nums = [float(v) for v in val.split(",")]
            if len(nums) == 2:
                out["AnchorPoint"] = {"Vector2": nums}
    return out


def with_at(model, label):
    """a copy of the model with every node's "at" override for this viewport applied (the phone reflow)"""
    import copy
    m = copy.deepcopy(model)

    def walk(inst):
        p = inst.setdefault("Properties", {})
        a = ((p.get("Attributes") or {}).get("Attributes") or {}).get(f"Kit_At_{label}")
        if isinstance(a, dict) and isinstance(a.get("String"), str):
            p.update(parse_at(a["String"]))
        for c in inst.get("Children") or []:
            walk(c)

    for c in m.get("Children") or []:
        walk(c)
    return m


def draw_viewport(model, sw, sh, label, anim=None):
    """draw at the viewport's size, honouring the screen's per-viewport scale (laid out in a 1/s world, shown at s)
    and every node's "at" override for that viewport"""
    model = with_at(model, label)
    s = viewport_scale(model, label)
    if abs(s - 1) < 1e-6:
        return draw_screen(model, sw, sh, anim)
    im, checks = draw_screen(model, int(round(sw / s)), int(round(sh / s)), anim, inset_px=TOPBAR[3] / s)
    if label == "phone":
        # the floors are pre-scale: a 16 px label at phone scale 0.5 draws at 8 px. Measure what the phone shows.
        def walk(inst, path):
            p = inst.get("Properties", {})
            if p.get("Visible", True) is False:
                return
            if inst.get("ClassName") in TEXT and (p.get("Text") or p.get("PlaceholderText")):
                drawn = (p.get("TextSize") or 14) * s
                if drawn < 11:
                    checks.append(("phone_text", path, f"draws at {drawn:.0f}px on the phone ({p.get('TextSize')}px x scale {s:g}) — raise the phone scale, the textSize, or set at.phone.textSize"))
            for c in inst.get("Children") or []:
                if c.get("ClassName") in GUI:
                    walk(c, f"{path}.{c['Name']}")
        for r in model.get("Children") or []:
            if r.get("ClassName") in GUI:
                walk(r, r["Name"])
    return im.resize((sw, sh), Image.LANCZOS), checks


def _desk_boxes(out, name):
    try:
        with open(os.path.join(out, f"{name}.boxes.json"), encoding="utf-8") as fh:
            return {k: tuple(v) for k, v in json.load(fh)["boxes"].items()}
    except (OSError, ValueError, KeyError):
        return {}


def focus_sheet(name, model, out, boxes):
    """<Screen>.focus.png: the desktop frame as a GAMEPAD player first sees it — the focus piece on firstFocus (the
    selection the pad lands on) and an arrow for every designed d-pad link (nav). None when the screen has neither."""
    sa = screen_attrs(model)
    first = (sa.get("Kit_FirstFocus") or {}).get("String")
    piece_name = (sa.get("Kit_FocusArtName") or {}).get("String")
    links = []

    def walk(inst, path):
        a = ((inst.get("Properties") or {}).get("Attributes") or {}).get("Attributes") or {}
        for d in ("Up", "Down", "Left", "Right"):
            to = (a.get("Kit_Nav" + d) or {}).get("String")
            if to:
                links.append((path, to, d))
        for c in inst.get("Children") or []:
            walk(c, f"{path}.{c.get('Name')}")

    for r in model.get("Children") or []:
        walk(r, r.get("Name"))
    if not first and not links:
        return None
    src = os.path.join(out, f"{name}.desktop.png")
    if not os.path.isfile(src):
        return None
    im = Image.open(src).convert("RGBA")
    d = ImageDraw.Draw(im)
    if first and first in boxes:
        x, y, w, h = boxes[first]
        pad = 7
        piece = art_image(piece_name) if piece_name else None
        sl = (sa.get("Kit_FocusSlice") or {}).get("String")
        if piece is not None:
            if sl:
                a_, b_, c_, d_ = (int(v) for v in sl.split(","))
                drawn = nine_slice(piece, w + 2 * pad, h + 2 * pad, ((a_, b_), (c_, d_)))
            else:
                drawn = piece.resize((max(1, int(w + 2 * pad)), max(1, int(h + 2 * pad))), Image.LANCZOS)
            im.alpha_composite(drawn, (max(0, int(x - pad)), max(0, int(y - pad))))
        else:  # (no focus piece: the engine's blue box, drawn so the sheet shows what the player would get)
            d.rectangle([x - 3, y - 3, x + w + 3, y + h + 3], outline=(0, 162, 255, 255), width=3)
        d.text((x, min(1080 - 20, y + h + pad + 4)), "PAD LANDS HERE", fill=(255, 255, 255, 255), font=font("GothamBold", 16), stroke_width=3, stroke_fill=(0, 0, 0, 255))
    for frm, to, dr in links:
        if frm in boxes and to in boxes:
            fx_, fy_, fw_, fh_ = boxes[frm]
            tx_, ty_, tw_, th_ = boxes[to]
            p0 = (fx_ + fw_ / 2, fy_ + fh_ / 2)
            p1 = (tx_ + tw_ / 2, ty_ + th_ / 2)
            d.line([p0, p1], fill=(255, 64, 160, 255), width=3)
            ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
            for side in (2.6, -2.6):
                d.line([p1, (p1[0] + 16 * math.cos(ang + side), p1[1] + 16 * math.sin(ang + side))], fill=(255, 64, 160, 255), width=3)
            d.text(((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2), dr.lower(), fill=(255, 255, 255, 255), font=font("GothamBold", 14), stroke_width=3, stroke_fill=(0, 0, 0, 255))
    path = os.path.join(out, f"{name}.focus.png")
    im.convert("RGB").save(path)
    return path.replace("\\", "/")


STATE_ORDER = ("hover", "pressed", "selected", "disabled", "locked", "new")


def state_overrides(inst, state):
    """a node's Kit_S_<state> ("prop=value;...") -> {prop: value}"""
    raw = attr(inst, f"Kit_S_{state}") or ""
    out = {}
    for pair in str(raw).split(";"):
        k, _, v = pair.partition("=")
        if k:
            out[k] = v
    return out


def apply_state(inst, state):
    """write one state's look into a model node (as Ui.setState does in game)"""
    o = state_overrides(inst, state)
    p = inst.setdefault("Properties", {})
    # a plate-backed control's picture is its Plate child (as in Ui.setState)
    pic = inst
    if inst.get("ClassName") not in ("ImageLabel", "ImageButton"):
        pic = next((c for c in inst.get("Children") or [] if c.get("Name") == "Plate" and c.get("ClassName") == "ImageLabel"), inst)
    pp = pic.setdefault("Properties", {})
    # ...and its words are its Label child when the button's own Text is empty
    wd = inst
    if inst.get("ClassName") in ("TextButton", "ImageButton") and not p.get("Text"):
        wd = next((c for c in inst.get("Children") or [] if c.get("Name") == "Label" and c.get("ClassName") == "TextLabel"), inst)
    wp = wd.setdefault("Properties", {})
    hx = lambda v: [int(v[i:i + 2], 16) / 255 for i in (1, 3, 5)]  # noqa: E731
    if "color" in o:
        p["BackgroundColor3"] = {"Color3": hx(o["color"])}
    if "textColor" in o:
        wp["TextColor3"] = {"Color3": hx(o["textColor"])}
    if "imageColor" in o:
        pp["ImageColor3"] = {"Color3": hx(o["imageColor"])}
    if "transparency" in o:
        p["BackgroundTransparency"] = float(o["transparency"])
    if "textAlpha" in o:
        wp["TextTransparency"] = float(o["textAlpha"])
    if "imageAlpha" in o:
        pp["ImageTransparency"] = float(o["imageAlpha"])
    if "text" in o:
        wp["Text"] = o["text"]
    if "art" in o:
        pp.setdefault("Attributes", {}).setdefault("Attributes", {})["KitArt"] = {"String": o["art"]}
    if "strokeColor" in o:
        for st in kids(inst, "UIStroke"):
            st.setdefault("Properties", {})["Color"] = {"Color3": hx(o["strokeColor"])}


def stated_nodes(model):
    """[(path, states)] for every node with designed states (Kit_States), in layout order"""
    out = []

    def walk(inst, path):
        st = attr(inst, "Kit_States")
        if st:
            out.append((path, [s for s in STATE_ORDER if s in str(st).split(",")]))
        for c in inst.get("Children") or []:
            walk(c, f"{path}.{c.get('Name')}")

    for r in model.get("Children") or []:
        walk(r, r.get("Name"))
    return out


def states_sheet(name, model, out, boxes):
    """<Screen>.states.png: every control with designed states, idle beside each of its states (one desktop render
    per state, every node switched at once) — the state sheet a pro screen ships with"""
    nodes = stated_nodes(model)
    nodes = [(pth, st) for pth, st in nodes if pth in boxes][:12]
    if not nodes:
        return None
    states = [s for s in STATE_ORDER if any(s in st for _, st in nodes)]
    frames = {"idle": draw_viewport(model, 1920, 1080, "desktop")[0]}
    for s in states:
        m = copy.deepcopy(model)

        def walk(inst, path, s=s):
            if path in dict(nodes) and s in dict(nodes)[path]:
                apply_state(inst, s)
            for c in inst.get("Children") or []:
                walk(c, f"{path}.{c.get('Name')}")

        for r in m.get("Children") or []:
            walk(r, r.get("Name"))
        frames[s] = draw_viewport(m, 1920, 1080, "desktop")[0]
    cols = ["idle"] + states
    cw, ch, lab = 240, 110, 18
    sheet_im = Image.new("RGB", (len(cols) * (cw + 6) + 6, lab + len(nodes) * (ch + lab + 6) + 6), (28, 28, 32))
    d = ImageDraw.Draw(sheet_im)
    f = font("GothamBold", 13)
    for j, c in enumerate(cols):
        d.text((6 + j * (cw + 6), 2), c, fill=(230, 230, 236), font=f)
    for i, (pth, st) in enumerate(nodes):
        x, y, w, h = boxes[pth]
        pad = 14
        box = (max(0, int(x - pad)), max(0, int(y - pad)), min(1920, int(x + w + pad)), min(1080, int(y + h + pad)))
        y0 = lab + i * (ch + lab + 6)
        d.text((6, y0), pth.split(".", 1)[-1][:60], fill=(160, 160, 170), font=f)
        for j, c in enumerate(cols):
            cell_x = 6 + j * (cw + 6)
            if c != "idle" and c not in st:
                d.text((cell_x + cw // 2 - 4, y0 + lab + ch // 2 - 8), "—", fill=(90, 90, 96), font=f)
                continue
            crop = frames[c].convert("RGB").crop(box)
            k = min(cw / max(1, crop.width), ch / max(1, crop.height))
            crop = crop.resize((max(1, int(crop.width * k)), max(1, int(crop.height * k))), Image.LANCZOS)
            sheet_im.paste(crop, (cell_x, y0 + lab))
    path = os.path.join(out, f"{name}.states.png")
    sheet_im.save(path)
    return path.replace("\\", "/")


def world_sheet(name, model, out):
    """a WORLD screen (a BillboardGui / SurfaceGui template): drawn at its canvas size, then shown over the world at
    near / mid / far (a billboard's "distance" scale) -> <Screen>.png (the sheet the library keeps), <Screen>.desktop.png
    + <Screen>.boxes.json (the canvas alone, for the verifier)"""
    p = model.get("Properties") or {}
    if model.get("ClassName") == "SurfaceGui":
        cw, ch = (p.get("CanvasSize") or {}).get("Vector2") or [400, 200]
    else:
        (_, cw), (_, ch) = (p.get("Size") or {}).get("UDim2") or [[0, 200], [0, 60]]
    cw, ch = max(1, int(cw)), max(1, int(ch))
    canvas, checks = draw_screen(model, cw, ch, inset_px=0, bare=True)
    canvas.save(os.path.join(out, f"{name}.desktop.png"))
    with open(os.path.join(out, f"{name}.boxes.json"), "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump({"schema": 1, "viewport": [cw, ch], "boxes": ALL_BOXES}, fh)
    sa = screen_attrs(model)
    low = float((sa.get("Kit_DistMin") or {}).get("Float64") or 1.0)
    mood_bg = world_backdrop(1280, 420, "dark")
    d = ImageDraw.Draw(mood_bg)
    f = font("GothamBold", 14)
    kind = "surface" if model.get("ClassName") == "SurfaceGui" else "billboard"
    for i, (label, k) in enumerate((("near", 1.0), ("mid", (1 + low) / 2), ("far", low))):
        k = k * min(1.0, 380 / cw, 300 / ch)
        im = canvas.resize((max(1, int(cw * k)), max(1, int(ch * k))), Image.LANCZOS)
        cx = 213 + i * 427
        mood_bg.alpha_composite(im, (int(cx - im.width / 2), int(200 - im.height / 2)))
        d.text((cx - 30, 392), f"{label} x{k:.2f}", fill=(230, 230, 236, 255), font=f)
    d.text((10, 8), f"{name} - world {kind}, canvas {cw}x{ch}", fill=(230, 230, 236, 255), font=f)
    path = os.path.join(out, f"{name}.png")
    mood_bg.convert("RGB").save(path)
    return {"name": name, "file": path.replace(chr(92), "/"),
            "checks": [{"name": kd, "viewport": "world", "path": pth, "severity": "warn", "fix": msg} for kd, pth, msg in checks]}


CVD = {  # Machado, Oliveira & Fernandes 2009, severity 1.0, applied in linear RGB
    "protanopia": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deuteranopia": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritanopia": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.146371), (0.004733, 0.691367, 0.303900)),
}


def simulate_cvd(im, kind):
    """the picture as a player with that colour vision deficiency sees it"""
    import numpy as np
    a = np.asarray(im.convert("RGB"), dtype=np.float64) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    out = np.clip(lin @ np.array(CVD[kind]).T, 0, 1)
    srgb = np.where(out <= 0.0031308, out * 12.92, 1.055 * out ** (1 / 2.4) - 0.055)
    return Image.fromarray((srgb * 255 + 0.5).astype(np.uint8), "RGB")


def cvd_sheet(name, out):
    """<Screen>.cvd.png: the desktop frame as typical, protanopia, deuteranopia and tritanopia players see it (XAG 103:
    nothing may be told by colour alone — a rarity, a state, an enemy marker must survive all three)"""
    src = os.path.join(out, f"{name}.desktop.png")
    if not os.path.isfile(src):
        return None
    base = Image.open(src).convert("RGB")
    w, h = base.width // 2, base.height // 2
    sheet_im = Image.new("RGB", (w * 2 + 6, h * 2 + 6), (28, 28, 32))
    d = ImageDraw.Draw(sheet_im)
    f = font("GothamBold", 16)
    for i, (label, im) in enumerate((("typical", base), ("protanopia", simulate_cvd(base, "protanopia")),
                                     ("deuteranopia", simulate_cvd(base, "deuteranopia")), ("tritanopia", simulate_cvd(base, "tritanopia")))):
        x, y = (i % 2) * (w + 6), (i // 2) * (h + 6)
        sheet_im.paste(im.resize((w, h), Image.LANCZOS), (x, y))
        d.text((x + 8, y + 6), label, fill=(255, 255, 255), font=f, stroke_width=3, stroke_fill=(0, 0, 0))
    path = os.path.join(out, f"{name}.cvd.png")
    sheet_im.save(path)
    return path.replace(chr(92), "/")


def sheet(name, model, out):
    shots, all_checks = [], []
    sa_ = screen_attrs(model)
    q_ = (sa_.get("Kit_Quality") or {}).get("String")
    id_ = (sa_.get("Kit_Identity") or {}).get("String")
    if q_ in ("hero", "aaa") and id_ and ground_image(id_) is None:
        all_checks.append({"name": "painted_ground", "viewport": "desktop", "path": name, "severity": "warn",
                           "fix": f"judged over a painted gradient, not the game: lune run kit ui ground {id_} --world <World> (or a picture without another game's HUD)"})
    desk_boxes = None
    for label, sw, sh, scale in VIEWPORTS:
        im, checks = draw_viewport(model, sw, sh, label)
        if desk_boxes is None:
            desk_boxes = dict(LAST_BOXES)
            # the desktop frame at full 1920x1080 + every node's box: the verifier crops the SAME piece from the
            # reference still and from this frame at one scale (kit ui verify)
            im.convert("RGB").save(os.path.join(out, f"{name}.desktop.png"))
            with open(os.path.join(out, f"{name}.boxes.json"), "w", encoding="utf-8", newline="\n") as fh:
                json.dump({"schema": 1, "viewport": [sw, sh], "boxes": ALL_BOXES}, fh)
            # the craft lints on the desktop frame (v7.2 / v7.3): alignment near-misses, then the squint test — does the
            # spec's focus still win when the detail is blurred away?
            import align as _align
            import hier as _hier
            for kd, pth, msg in _align.near_misses(dict(ALL_BOXES)):
                all_checks.append({"name": kd, "viewport": "desktop", "path": pth, "severity": "warn", "fix": msg})
            for kd, pth, msg in _align.palette(model, dict(ALL_BOXES)):
                all_checks.append({"name": kd, "viewport": "desktop", "path": pth, "severity": "warn", "fix": msg})
            focus_ = ((screen_attrs(model).get("Kit_Focus") or {}).get("String"))
            if focus_:
                rank_, scores_ = _hier.squint(im, dict(ALL_BOXES), focus_)
                if rank_ is not None and rank_ > 3:
                    wins_ = next((p_ for _, p_ in scores_ if not (p_ == focus_ or p_.startswith(focus_ + ".") or focus_.startswith(p_ + "."))), "?")
                    all_checks.append({"name": "squint", "viewport": "desktop", "path": focus_, "severity": "warn",
                                       "fix": f"squint test: the focus is only #{rank_} when the detail is blurred away ({wins_} wins) — "
                                              "make it bigger, brighter or set apart, or quiet what beats it"})
        else:
            checks = list(checks) + squeezed(desk_boxes, dict(LAST_BOXES), label)
        im = im.convert("RGB").resize((int(sw * scale), int(sh * scale)), Image.LANCZOS)
        ImageDraw.Draw(im).text((8, im.height - 18), f"{label} {sw}x{sh}", fill=(255, 255, 255), font=font("GothamBold", 13))
        shots.append(im)
        for kind, path, msg in checks:
            all_checks.append({"name": kind, "viewport": label, "path": path, "severity": "warn", "fix": msg})
    d, ph, tb = shots
    W = max(d.width, ph.width + tb.width + 8)
    H = d.height + 8 + max(ph.height, tb.height)
    canvas = Image.new("RGB", (W, H), (40, 40, 44))
    canvas.paste(d, (0, 0))
    canvas.paste(ph, (0, d.height + 8))
    canvas.paste(tb, (ph.width + 8, d.height + 8))
    path = os.path.join(out, f"{name}.png")
    canvas.save(path)
    # one entry per (check, element): the same problem on 3 viewports is one problem
    seen, checks = set(), []
    for c in all_checks:
        k = (c["name"], c["path"])
        if k not in seen:
            seen.add(k)
            checks.append(c)
    return {"name": name, "file": path.replace("\\", "/"), "checks": checks}


# ------------------------------------------------------------------ motion strips: the choreography as frames
def ease(kind, t):
    t = max(0.0, min(1.0, t))
    if kind == "linear":
        return t
    if kind == "sine":
        return math.sin(t * math.pi / 2)
    if kind == "back":
        c1, c3 = 1.70158, 2.70158
        return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2
    if kind == "expo":
        return 1 if t >= 1 else 1 - 2 ** (-10 * t)
    if kind == "elastic":
        if t in (0, 1):
            return t
        return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi / 3)) + 1
    return 1 - (1 - t) ** 2  # quad out


def enter_state(kind, k, text):
    """the look of an element at eased progress k of its enter (mirrors src/kit/Ui.luau)"""
    if kind == "fade":
        return {"alpha": k}
    if kind == "rise":
        return {"alpha": min(1, k * 1.5), "dy": (1 - k) * 24}
    if kind == "drop":
        return {"alpha": min(1, k * 1.5), "dy": -(1 - k) * 24}
    if kind == "sweep":
        return {"alpha": min(1, k * 1.5), "dx": -(1 - k) * 48}
    if kind == "pop":
        return {"alpha": min(1, k * 2), "scale": 0.85 + 0.15 * k}
    if kind == "bounce":
        return {"alpha": min(1, k * 2.5), "scale": 0.6 + 0.4 * k}
    if kind == "slam":
        return {"alpha": min(1, k * 1.6), "scale": 1.4 - 0.4 * k}
    if kind == "swell":
        return {"alpha": k, "scale": 0.96 + 0.08 * k}
    if kind == "wipe":
        return {"wipe": k}
    if kind == "typewriter":
        return {"text": text[: int(len(text) * k + 0.5)]}
    return {}


def motion_plan(model):
    """every element's enter: {path: (kind, delay, duration, ease, text)} with the container stagger applied in
    sibling order, exactly as Ui.show plays it"""
    plan = {}

    def walk(inst, path, stagger, index):
        p = inst.get("Properties", {})
        a = (p.get("Attributes") or {}).get("Attributes") or {}

        def num(key, default):
            v = a.get(key)
            return v.get("Float64", default) if isinstance(v, dict) else default

        kind = (a.get("Motion_enter") or {}).get("String")
        if kind:
            delay = num("Motion_enter_delay", 0) + stagger * index
            plan[path] = (kind, delay, num("Motion_enter_duration", 0.35), (a.get("Motion_enter_ease") or {}).get("String", "quad"), p.get("Text", ""))
        my_stagger = num("Motion_stagger", 0)
        i = 0
        kids = [c for c in inst.get("Children") or [] if c.get("ClassName") in GUI]
        kids.sort(key=lambda c: c.get("Properties", {}).get("LayoutOrder", 0))  # (the compiler numbers siblings)
        for c in kids:
            # as Ui.luau's playTree: only the children that ENTER take a stagger slot, in LayoutOrder
            c_attrs = ((c.get("Properties") or {}).get("Attributes") or {}).get("Attributes") or {}
            enters = c_attrs.get("Motion_enter") is not None
            walk(c, f"{path}.{c['Name']}", my_stagger, i if enters else 0)
            if my_stagger and enters:
                i += 1

    for r in model.get("Children") or []:
        if r.get("ClassName") in GUI:
            walk(r, r["Name"], 0, 0)
    return plan


def motion_sheet(name, model, out):
    plan = motion_plan(model)
    if not plan:
        return None
    ends = [d + dur for _, d, dur, _, _ in plan.values()]
    total = max(ends)
    times = [0.0, total * 0.15, total * 0.3, total * 0.5, total * 0.75, total]
    sw, sh, scale = 1920, 1080, 0.33
    frames = []
    for t in times:
        def anim(path, inst, t=t):
            hit = None
            # the nearest ancestor (or self) with an enter: children ride on it
            node = path
            while node:
                if node in plan:
                    hit = plan[node]
                    break
                node = node.rpartition(".")[0]
            if not hit:
                return None
            kind, delay, dur, ez, text = hit
            k = ease(ez, (t - delay) / max(dur, 1e-6)) if t >= delay else 0.0
            st = enter_state(kind, k, text if node == path else "")
            if node != path and "text" in st:
                st.pop("text")
            return st

        im, _ = draw_screen(model, sw, sh, anim)
        im = im.convert("RGB").resize((int(sw * scale), int(sh * scale)), Image.LANCZOS)
        ImageDraw.Draw(im).text((8, im.height - 18), f"t = {t:.2f} s", fill=(255, 255, 255), font=font("GothamBold", 13))
        frames.append(im)
    fw, fh = frames[0].size
    canvas = Image.new("RGB", (fw * 3 + 16, fh * 2 + 8), (40, 40, 44))
    for i, fr in enumerate(frames):
        canvas.paste(fr, ((i % 3) * (fw + 8), (i // 3) * (fh + 8)))
    path = os.path.join(out, f"{name}.motion.png")
    canvas.save(path)
    return {"file": path.replace("\\", "/"), "elements": len(plan), "settles_s": round(total, 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("names", nargs="*")
    ap.add_argument("--art", default=None)
    ap.add_argument("--motion", action="store_true", help="also draw each screen's enter choreography as 6 frames")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    global ART_DIR
    ART_DIR = a.art or os.path.join(a.out, "art")
    files = sorted(f for f in os.listdir(a.models) if f.endswith(".model.json")) if os.path.isdir(a.models) else []
    if a.names:
        files = [f for f in files if f[: -len(".model.json")] in a.names]
    results = []
    for f in files:
        with open(os.path.join(a.models, f), encoding="utf-8") as fh:
            model = json.load(fh)
        if model.get("ClassName") in ("BillboardGui", "SurfaceGui"):
            results.append(world_sheet(f[: -len(".model.json")], model, a.out))
            continue
        if model.get("ClassName") != "ScreenGui":
            continue
        r = sheet(f[: -len(".model.json")], model, a.out)
        if stated_nodes(model):
            r["states"] = states_sheet(r["name"], model, a.out, _desk_boxes(a.out, r["name"]))
        r["cvd"] = cvd_sheet(r["name"], a.out)
        fs = focus_sheet(r["name"], model, a.out, _desk_boxes(a.out, r["name"]))
        if fs:
            r["focus"] = fs
        if a.motion:
            r["motion"] = motion_sheet(r["name"], model, a.out)
        results.append(r)
    warns = [(r["name"], c) for r in results for c in r["checks"]]
    summary = f"{len(results)} screen preview(s) in {a.out}" + (f" ({len(warns)} layout warning(s): {', '.join(sorted({c['name'] for _, c in warns}))})" if warns else "")
    if FALLBACK_FACES:
        summary += f"; {len(FALLBACK_FACES)} font(s) drawn with a system face ({', '.join(sorted(FALLBACK_FACES))}): lune run kit ui fonts"
    if a.motion:
        strips = [r for r in results if r.get("motion")]
        summary += f"; {len(strips)} motion strip(s) (<Screen>.motion.png)"
    if warns:
        n, c = warns[0]
        nxt = f"improve {n} [{c['viewport']}] {c['path']}: {c['fix']}"
    elif results:
        nxt = f"look at {a.out}/<Screen>.png on all three sizes: hierarchy clear? thumb-reachable on phone? nothing cramped?"
        if a.motion:
            nxt += " — and <Screen>.motion.png: does it arrive in order, nothing popping all at once?"
    else:
        nxt = "none — no screens yet (lune run kit new screen <Name>)"
    print(json.dumps({"schema": 1, "status": "pass", "summary": summary, "next_action": nxt, "screens": results}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
