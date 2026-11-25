"""letter.py — FLAT cut lettering as a UI piece (Persona's logo and shout words): real letterforms from the kit's
pinned fonts, every glyph optionally on its own scissor-cut card, a thick ink outline and a HARD offset shadow,
the whole word leaning. Paper on ink, or ink on paper — no chrome, no gradient, no bevel (those read as WordArt
on a cut-paper screen).

    python kit/ui/letter.py <identity>/<piece> --text "UMBRA" [--font bangers] [--size 360] [--fill #f0f0f0]
        [--ink #000000] [--outline 0.06] [--shadow 0.08] [--shadow-color #000000] [--lean -6] [--cards]
        [--card-color #000000] [--track 0.02] [--art assets/ui/art]

Sizes are in em of --size. Writes <art>/<identity>/<piece>.png (+ .letter.json: the recipe) — `kit ui` takes it in as
art:<identity>/<piece>. The glyphs are set 4x and downsampled: crisp at any UI scale.
"""
import argparse
import json
import math
import os
import random
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fonts as F  # noqa: E402  (the pinned font cache)

SS = 4


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def hex_rgb(s, default=(255, 255, 255)):
    if not isinstance(s, str) or not s.startswith("#") or len(s) != 7:
        return default
    return tuple(int(s[i:i + 2], 16) for i in (1, 3, 5))


def font_file(family):
    folder = os.path.join(F.fonts_dir(), family.lower().replace(" ", ""))
    if not os.path.isdir(folder):
        return None
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".ttf", ".otf")))
    # a static Regular / Bold first, then a variable file
    # (an upright face first: Name-Italic[wght].ttf sorts before Name[wght].ttf, and YOU DIED came out slanted)
    files.sort(key=lambda f: (("italic" in f.lower()), ("[" in f), ("bold" not in f.lower()), f))
    return os.path.join(folder, files[0]) if files else None


def cut_card(w, h, seed, depth):
    """a scissor-cut card polygon around a glyph box (long straight runs, sharp corners)"""
    rnd = random.Random(seed)
    pts = []
    corners = [(0, 0), (w, 0), (w, h), (0, h)]
    for i in range(4):
        (x0, y0), (x1, y1) = corners[i], corners[(i + 1) % 4]
        nx, ny = (y1 - y0), -(x1 - x0)
        ln = max(1e-6, math.hypot(nx, ny))
        nx, ny = nx / ln, ny / ln
        pts.append((x0 + nx * rnd.uniform(-0.3, 0.3) * depth, y0 + ny * rnd.uniform(-0.3, 0.3) * depth))
        t = rnd.uniform(0.3, 0.7)
        k = rnd.uniform(0.4, 1.0) * depth * rnd.choice((-1, 1))
        pts.append((x0 + (x1 - x0) * t + nx * k, y0 + (y1 - y0) * t + ny * k))
    return pts


# the persona style: every glyph from a different face of this pool (serif caps, condensed, rounded, wide, italic),
# heavy weight where the face has an axis — the mixed "ransom" lettering of Persona's menus and call-outs
PERSONA_POOL = [
    ("cinzel", "Cinzel[wght].ttf", 900),
    ("oswald", "Oswald[wght].ttf", 700),
    ("luckiestguy", "LuckiestGuy-Regular.ttf", None),
    ("ebgaramond", "EBGaramond[wght].ttf", 800),
    ("montserrat", "Montserrat-Italic[wght].ttf", 900),
    ("robotocondensed", "RobotoCondensed[wght].ttf", 900),
    ("michroma", "Michroma-Regular.ttf", None),
    ("montserrat", "Montserrat[wght].ttf", 900),
]


def persona_font(i, size):
    fam, file, weight = PERSONA_POOL[i % len(PERSONA_POOL)]
    path = os.path.join(F.fonts_dir(), fam, file)
    if not os.path.isfile(path):
        return None
    f = ImageFont.truetype(path, size)
    if weight:
        try:
            axes = f.get_variation_axes()
            f.set_variation_by_axes([max(a["minimum"], min(a["maximum"], weight)) if a["name"] in (b"Weight", "Weight") else a["default"] for a in axes])
        except Exception:  # noqa: BLE001
            pass
    return f


def drip_mask(fill_mask, glyphs, margin, size, a, rnd):
    """INK DRIPS off the glyphs' bottoms (Splatoon's lettering): per glyph, with --drip-share odds, one drip from the
    lowest stretch of its fill — a stem of --drip em at most (times --drip-phase, so a flipbook can grow it) ending in a
    round bulb, its top buried in the fill so it flows out of the letter"""
    fm = np.asarray(fill_mask) > 127
    out = Image.new("L", fill_mask.size, 0)
    d = ImageDraw.Draw(out)
    for g in glyphs:
        if rnd.random() > a.drip_share:
            continue
        # (a stem FATTER than the ink outline — a thin one inside a thick outline reads as a pin, not ink)
        length, width_k, pick = rnd.uniform(0.45, 1.0), max(rnd.uniform(0.13, 0.19), 2.2 * a.outline), rnd.uniform(0.25, 0.75)
        x0, x1 = margin + g["x"], margin + g["x"] + g["w"]
        cols = [x for x in range(max(0, x0), min(fm.shape[1], x1)) if fm[:, x].any()]
        if not cols:
            continue
        bottoms = {x: int(np.nonzero(fm[:, x])[0].max()) for x in cols}
        low = max(bottoms.values())
        # (a drip leaves from a FLAT low run of the glyph, near where the ink would pool — not off a serif tip)
        run = [x for x in cols if bottoms[x] >= low - int(size * 0.04)]
        cx = run[min(len(run) - 1, int(pick * len(run)))]
        w = width_k * size
        top = bottoms[cx] - int(size * 0.06)
        L = a.drip * size * length * max(0.0, min(1.0, a.drip_phase))
        if L < w * 0.4:
            continue
        # a CAPSULE that swells a little toward its tip (ink gathering to fall), not a ball on a stick
        bulb = w * 0.58
        d.rounded_rectangle([cx - w / 2, top, cx + w / 2, bottoms[cx] + L], radius=w / 2, fill=255)
        d.ellipse([cx - bulb, bottoms[cx] + L - bulb * 2.0, cx + bulb, bottoms[cx] + L + bulb * 0.15], fill=255)
        # a wide fillet where it leaves the letter: the ink flows out in a curve, it does not start square
        d.ellipse([cx - w * 1.5, bottoms[cx] - w * 0.6, cx + w * 1.5, bottoms[cx] + w * 0.7], fill=255)
    return Image.fromarray(np.minimum(np.asarray(out), 255).astype(np.uint8))


def dilate(alpha, px):
    """the shape grown by px — a round outline (a distance transform: one pass, any width; MaxFilter is square and
    slow at the 4x supersample)"""
    if px <= 0:
        return alpha
    import numpy as np
    from scipy.ndimage import distance_transform_edt
    a = np.array(alpha) > 127
    dist = distance_transform_edt(~a)
    # a soft edge 1.5 px wide (at 4x: crisp after the downsample)
    v = np.clip((px + 0.75 - dist) / 1.5, 0, 1)
    return Image.fromarray((v * 255).astype(np.uint8), "L")


def persona(a, ident, piece):
    """Persona lettering: every glyph its own face (the pool), case mixed (the first letter up and big), each one
    resized, tilted and lifted off the baseline, the glyphs overlapping; each glyph keeps a thin ink edge so the
    overlaps read; then the WORD gets one thick ink outline and a thin paper rim outside it (the menu words of P5).
    --cards puts the word on one scissor-cut ink card instead of the paper rim."""
    rnd = random.Random(a.seed)
    size = a.size * SS
    fill, ink = hex_rgb(a.fill), hex_rgb(a.ink)
    paper = hex_rgb(a.rim_color) if a.rim_color else (240, 240, 240)
    accent = hex_rgb(a.accent) if a.accent else None
    glyphs = []
    x = 0
    for i, ch in enumerate(a.text):
        if ch == " ":
            x += int(size * 0.32)
            continue
        k = rnd.randrange(len(PERSONA_POOL)) if i else 0  # the first letter: the serif caps
        big = i == 0
        gs = int(size * (1.22 if big else rnd.uniform(0.78, 1.08)))
        f = persona_font(k, gs) or ImageFont.truetype(font_file("oswald"), gs)
        c = ch.upper() if (big or a.caps or rnd.random() < 0.62) else ch.lower()
        box = f.getbbox(c)
        gw, gh = box[2] - box[0], box[3] - box[1]
        pad = int(gs * 0.25)
        g = Image.new("RGBA", (gw + 2 * pad, gh + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(g)
        edge = max(2, int(gs * 0.022))
        colour = accent if (accent and rnd.random() < a.accent_share) else fill
        d.text((pad - box[0], pad - box[1]), c, font=f, fill=colour + (255,), stroke_width=edge, stroke_fill=ink + (255,))
        rot = rnd.uniform(-a.wobble, a.wobble) if a.wobble else 0.0
        if rot:
            g = g.rotate(rot, resample=Image.BICUBIC, expand=True)
        # spacing by INK, not by the face's box: crop to the drawn glyph, advance by its drawn width (faces differ
        # wildly in side bearings; box spacing left holes like "UMB r A")
        ib = g.getbbox()
        if ib:
            g = g.crop(ib)
        dy = int(rnd.uniform(-0.09, 0.09) * size) - (int(size * 0.12) if big else 0) + (int(gs * 0.25) if ib is None else ib[1] - int(gs * 0.25))
        glyphs.append((g, x, dy))
        x += int(g.width * (1.0 - a.overlap)) + int(size * a.track)
    if not glyphs:
        return emit("fail", "letter: no glyphs", "give --text")
    ol = int(a.outline * size)
    rim = int(a.rim_px * SS)
    margin = ol + rim + int(size * 0.4)
    W = x + max(g.width for g, _, _ in glyphs) + 2 * margin
    H = max(g.height for g, _, _ in glyphs) + 2 * margin + int(size * 0.3)
    word = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    base = margin + int(size * 0.15)
    # later glyphs UNDER earlier ones alternate, so the stack reads as cut and glued, not typed
    order = list(range(len(glyphs)))
    rnd.shuffle(order)
    for idx in order:
        g, gx, dy = glyphs[idx]
        word.alpha_composite(g, (margin + gx, base + dy))
    alpha = word.getchannel("A")
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if a.cards:
        grown = dilate(alpha, ol + int(size * 0.08))
        bb = grown.getbbox()
        card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dc = ImageDraw.Draw(card)
        pts = cut_card(bb[2] - bb[0], bb[3] - bb[1], a.seed * 7 + 3, depth=size * 0.12)
        dc.polygon([(bb[0] + px, bb[1] + py) for px, py in pts], fill=(hex_rgb(a.card_color) if a.card_color else ink) + (255,))
        out.alpha_composite(card)
    elif rim:
        rim_layer = Image.new("RGBA", (W, H), paper + (255,))
        rim_layer.putalpha(dilate(alpha, ol + rim))
        out.alpha_composite(rim_layer)
    ink_layer = Image.new("RGBA", (W, H), ink + (255,))
    ink_layer.putalpha(dilate(alpha, ol))
    out.alpha_composite(ink_layer)
    if a.shadow:
        sh = int(a.shadow * size)
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        s_layer = Image.new("RGBA", (W, H), (hex_rgb(a.shadow_color) if a.shadow_color else ink) + (255,))
        s_layer.putalpha(dilate(alpha, ol))
        shadow.alpha_composite(s_layer, (sh, sh))
        shadow.alpha_composite(out)
        out = shadow
    out.alpha_composite(word)
    if a.lean:
        out = out.rotate(a.lean, resample=Image.BICUBIC, expand=True)
    bbox = out.getbbox()
    out = out.crop((max(0, bbox[0] - 4), max(0, bbox[1] - 4), min(out.width, bbox[2] + 4), min(out.height, bbox[3] + 4)))
    out = out.resize((max(1, out.width // SS), max(1, out.height // SS)), Image.LANCZOS)
    out_dir = os.path.join(a.art, ident)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{piece}.png")
    out.save(out_path)
    side = {"schema": 1, "kind": "letter", "style": "persona", "text": a.text, "size": a.size, "fill": a.fill, "ink": a.ink,
            "accent": a.accent, "accent_share": a.accent_share, "outline": a.outline, "rim_px": a.rim_px, "shadow": a.shadow,
            "lean": a.lean, "wobble": a.wobble, "overlap": a.overlap, "cards": a.cards, "seed": a.seed, "out": [out.width, out.height],
            "pool": [p[0] for p in PERSONA_POOL],
            "about": f"persona lettering '{a.text}': a face per glyph, mixed case, tilted, overlapping, ink outline + paper rim",
            "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(os.path.join(out_dir, f"{piece}.letter.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(side, fh, indent=1)
    return emit("pass", f"letter: {ident}/{piece}.png {out.width}x{out.height} — persona '{a.text}' ({len(glyphs)} glyphs, faces mixed, outline {ol // SS}px, rim {rim // SS}px)",
                f"use it as art:{ident}/{piece}; LOOK at it on the field it sits on")


def parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--style", default="flat", choices=["flat", "persona"],
                    help="flat: one face, one outline; persona: a face per glyph, mixed case, tilted, overlapping, outline + rim")
    ap.add_argument("--overlap", type=float, default=0.12, help="persona: how much each glyph tucks under the next (share of its width)")
    ap.add_argument("--rim-px", type=float, default=5, help="persona: the paper rim outside the ink outline, output px")
    ap.add_argument("--rim-color", default=None)
    ap.add_argument("--accent", default=None, help="persona: an accent colour some glyphs take")
    ap.add_argument("--accent-share", type=float, default=0.0)
    ap.add_argument("--caps", action="store_true", help="persona: every glyph a capital (a logo)")
    ap.add_argument("--weight", type=int, default=None, help="flat: the weight of a variable face (Cinzel 400..900)")
    ap.add_argument("--text", required=True)
    ap.add_argument("--font", default="bangers")
    ap.add_argument("--size", type=int, default=360)
    ap.add_argument("--fill", default="#f0f0f0")
    ap.add_argument("--ink", default="#000000")
    ap.add_argument("--outline", type=float, default=0.06, help="ink outline, em")
    ap.add_argument("--shadow", type=float, default=0.08, help="hard offset shadow, em (0 = none)")
    ap.add_argument("--shadow-color", default=None, help="default: the ink")
    ap.add_argument("--lean", type=float, default=-6.0, help="the whole word's rotation, degrees")
    ap.add_argument("--widen", type=float, default=1.0, help="flat: an EXTENDED face, x scale (1.25 = a quarter wider; "
                    "a racing speedo's numerals are wider than tall — Michroma and Montserrat are not)")
    ap.add_argument("--shear", type=float, default=0.0, help="flat: an italic slant, x per y (0.2 leans right; kit ui read type measures it)")
    ap.add_argument("--cards", action="store_true", help="every glyph on its own scissor-cut card")
    ap.add_argument("--card-color", default=None, help="default: the ink (paper letters on ink cards)")
    ap.add_argument("--card-pad", type=float, default=0.12, help="card padding, em")
    ap.add_argument("--track", type=float, default=0.02, help="letter spacing, em")
    ap.add_argument("--wobble", type=float, default=0.0, help="per-glyph rotation range, degrees (ransom look)")
    ap.add_argument("--case-codes", action="store_true", help="a glyph set with BOTH cases (a font): lowercase files are l<letter>")
    ap.add_argument("--glyphs", default=None, help="flat: a DIGIT SET — each of these characters as its own picture "
                    "<piece>_<code>.png on one baseline in one cell (a 'number' node composes any number from them)")
    ap.add_argument("--no-crop", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--inline", default=None, help="flat: a thin highlight line inside every glyph's fill, this colour (#f8e8a8)")
    ap.add_argument("--inline-px", type=float, default=0.022, help="flat: the inline's width, em")
    ap.add_argument("--inline-gap", type=float, default=0.03, help="flat: how far inside the fill's edge the inline runs, em")
    ap.add_argument("--arc", type=float, default=0.0, help="flat: set the word on an arch, this many degrees of sweep (+ up, - sags)")
    ap.add_argument("--bounce", type=float, default=0.0, help="flat: each glyph hops off the baseline, alternating, up to this many em")
    ap.add_argument("--drip", type=float, default=0.0, help="flat: ink drips off the glyphs' bottoms, up to this many em long")
    ap.add_argument("--drip-share", type=float, default=0.45, help="flat: the odds a glyph drips")
    ap.add_argument("--drip-phase", type=float, default=1.0, help="flat: how far the drips have run, 0..1 (a flipbook grows them)")
    ap.add_argument("--glow", default=None, help="flat: a soft halo under the word, this colour (#ff2a1a) — a death word, a sign")
    ap.add_argument("--glow-px", type=float, default=0.12, help="flat: the halo's blur radius, em")
    ap.add_argument("--glow-alpha", type=float, default=0.7, help="flat: the halo's strength, 0..1")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--art", default="assets/ui/art")
    return ap


CASE_CODES = False  # (--case-codes: a lowercase letter's file is "l<letter>" — Windows names ignore case: a / A collide)


def glyph_code(ch):
    """a glyph's file code: letters and digits as themselves, anything else as u<codepoint> (':' -> u58); with
    --case-codes (a FONT with both cases) a lowercase letter is l<letter> ('a' -> la), so 'a' and 'A' stay two files"""
    if CASE_CODES and ch.isalpha() and ch.islower():
        return f"l{ch}"
    return ch if ch.isalnum() else f"u{ord(ch)}"


def glyph_set(argv, a, ident, piece):
    """every character of --glyphs drawn alone with the same recipe, uncropped (one baseline), then all cut to the
    union of their ink rows and centred in one monospace cell -> <piece>_<code>.png + <piece>.glyphs.json"""
    import tempfile
    base = [x for i, x in enumerate(argv) if not (x == "--glyphs" or x.startswith("--glyphs=") or (i > 0 and argv[i - 1] == "--glyphs"))]
    base = [x for x in base if x != a.target]
    pics = {}
    with tempfile.TemporaryDirectory() as tmp:
        for ch in a.glyphs:
            args = [f"g/{glyph_code(ch)}"] + [x for x in base] + ["--no-crop", "--art", tmp]
            ti = args.index("--text") if "--text" in args else -1
            if ti >= 0:
                args[ti + 1] = ch
            else:
                args += ["--text", ch]
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                main(args)
            with Image.open(os.path.join(tmp, "g", f"{glyph_code(ch)}.png")) as im:
                pics[ch] = im.convert("RGBA").copy()
    rows = [im.getchannel("A").getbbox() for im in pics.values() if im.getchannel("A").getbbox()]
    if not rows:
        return emit("fail", "letter: the glyph set drew nothing", "check --font and --glyphs")
    y0, y1 = min(r[1] for r in rows), max(r[3] for r in rows)
    cells = {}
    for ch, im in pics.items():
        bb = im.getchannel("A").getbbox() or (0, y0, 1, y1)
        cells[ch] = im.crop((bb[0], y0, bb[2], y1))
    cw = max(c.width for c in cells.values()) + 2
    ch_h = y1 - y0
    out_dir = os.path.join(a.art, ident)
    os.makedirs(out_dir, exist_ok=True)
    for ch, c in cells.items():
        cell = Image.new("RGBA", (cw, ch_h), (0, 0, 0, 0))
        cell.alpha_composite(c, ((cw - c.width) // 2, 0))
        cell.save(os.path.join(out_dir, f"{piece}_{glyph_code(ch)}.png"))
    aspect = round(cw / ch_h, 4)
    side = {"schema": 1, "kind": "glyphs", "chars": a.glyphs, "codes": {ch: glyph_code(ch) for ch in a.glyphs}, "cell": [cw, ch_h],
            "aspect": aspect, "font": a.font, "fill": a.fill, "ink": a.ink, "outline": a.outline, "shadow": a.shadow, "lean": a.lean,
            "inline": a.inline, "size": a.size, "weight": a.weight, "track": a.track, "shear": a.shear, "widen": a.widen, "glow": a.glow,
            "glow_px": a.glow_px, "glow_alpha": a.glow_alpha, "about": f"a digit set of {len(a.glyphs)} glyph(s) in {a.font}: one baseline, one {cw}x{ch_h} cell",
            "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(os.path.join(out_dir, f"{piece}.glyphs.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(side, fh, indent=1)
    return emit("pass", f"letter: {ident}/{piece} glyph set — {len(cells)} glyph(s), cell {cw}x{ch_h} (aspect {aspect})",
                f'use it: {{"type": "number", "digits": "{ident}/{piece}", "aspect": {aspect}, "text": "...", "size": [w, h]}}')


def main(argv=None):
    import sys as _sys
    argv = list(argv) if argv is not None else _sys.argv[1:]
    a = parser().parse_args(argv)
    global CASE_CODES
    CASE_CODES = bool(getattr(a, "case_codes", False))
    if a.glyphs and not a.glyphs.isascii():  # (Luau reads glyph codes byte-wise: keep the set ASCII)
        return emit("fail", "letter: --glyphs must be ASCII characters (the runtime names glyphs byte by byte)", "drop the non-ASCII glyphs")
    if a.glyphs and "/" in a.target and not a.no_crop:
        ident_, piece_ = a.target.split("/", 1)
        return glyph_set(argv, a, ident_, piece_)
    if "/" not in a.target:
        return emit("fail", "letter: name the piece as <identity>/<name>", 'lune run kit ui letter arcade5/logo_flat --text "UMBRA" --font bangers --cards')
    ident, piece = a.target.split("/", 1)
    if a.style == "persona":
        return persona(a, ident, piece)
    ff = font_file(a.font)
    if not ff:
        return emit("fail", f"letter: no pinned font '{a.font}' in {F.fonts_dir()}", "lune run kit ui fonts fetch (kit/ui/fonts.json lists the families)")
    size = a.size * SS
    font = ImageFont.truetype(ff, size)
    if a.weight:
        try:
            font.set_variation_by_axes([a.weight if ax["name"] in (b"Weight", "Weight") else ax["default"] for ax in font.get_variation_axes()])
        except Exception:  # noqa: BLE001  (a static face: its one weight)
            pass
    rnd = random.Random(a.seed)
    fill, ink = hex_rgb(a.fill), hex_rgb(a.ink)
    shadow_c = hex_rgb(a.shadow_color) if a.shadow_color else ink
    card_c = hex_rgb(a.card_color) if a.card_color else ink
    ol = int(a.outline * size)
    sh = int(a.shadow * size)
    pad = int(a.card_pad * size)
    track = int(a.track * size)
    # measure the glyphs
    glyphs = []
    x = 0
    for ch in a.text:
        if ch == " ":
            x += int(size * 0.3)
            continue
        box = font.getbbox(ch)
        gw = box[2] - box[0]
        rot = rnd.uniform(-a.wobble, a.wobble) if a.wobble else 0.0
        # (a BOUNCE lifts or drops each glyph off the baseline, alternating so the word hops — Splatoon's lettering)
        dy = int((1 if len(glyphs) % 2 else -1) * rnd.uniform(0.35, 1.0) * a.bounce * size) if a.bounce else 0
        glyphs.append({"ch": ch, "x": x, "box": box, "w": gw, "rot": rot, "dy": dy})
        x += gw + track
    total_w = x - track
    # an ARCH (a 1930s title card, a badge): the word set on a circle whose sweep is --arc degrees (+ arches up like a
    # rainbow, - sags like a smile); each glyph drops by its sagitta and turns to the circle's tangent
    arc_room = 0
    if a.arc and glyphs and total_w > 0:
        R = total_w / math.radians(a.arc)
        for g in glyphs:
            # (on the CIRCLE: arc length -> angle, the glyph's centre to R sin, down by the sagitta — a review found
            # x left at the arc length set the word on a cosine and over-turned the ends)
            off = g["x"] + g["w"] / 2 - total_w / 2
            th = off / R
            g["x"] += int(R * math.sin(th) - off)
            g["dy"] += int(R * (1 - math.cos(th)))
            g["rot"] += -math.degrees(th)
        arc_room = int(abs(R) * (1 - math.cos(min(abs(math.radians(a.arc)) / 2, math.pi / 2)))) + 1
    asc, desc = font.getmetrics()
    line_h = asc + desc
    glow_r = int(max(0.0, a.glow_px) * size) if a.glow else 0
    margin = ol + sh + pad + int(size * 0.25) + int(a.bounce * size) + arc_room + 2 * glow_r
    drip_room = int(a.drip * size * 1.3)
    W, H = total_w + 2 * margin, line_h + 2 * margin + drip_room
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # the cards first (under everything), then the shadow, then the letters
    if a.cards:
        d = ImageDraw.Draw(im)
        for i, g in enumerate(glyphs):
            gx0 = margin + g["x"] - pad
            gy0 = margin + g["box"][1] - pad
            gw, gh = g["w"] + 2 * pad, (g["box"][3] - g["box"][1]) + 2 * pad
            pts = cut_card(gw, gh, a.seed * 31 + i, depth=pad * 0.9)
            d.polygon([(gx0 + px, gy0 + py) for px, py in pts], fill=card_c + (255,))
    layer_shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    layer_text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fill_mask = Image.new("L", (W, H), 0)  # (the fill alone: where a drip may join a glyph without an outline across it)
    ds, dt, dm = ImageDraw.Draw(layer_shadow), ImageDraw.Draw(layer_text), ImageDraw.Draw(fill_mask)
    for g in glyphs:
        gx, gy = margin + g["x"] - g["box"][0], margin + g["dy"]
        if g["rot"]:
            rp = size // 4 if abs(g["rot"]) < 12 else size // 2  # (a steep turn swings the corners out: room for them)
            tmp = Image.new("RGBA", (g["w"] + 2 * ol + 2 * rp, line_h + 2 * ol + 2 * rp), (0, 0, 0, 0))
            tdraw = ImageDraw.Draw(tmp)
            ox, oy = ol + rp - g["box"][0], ol + rp
            tdraw.text((ox, oy), g["ch"], font=font, fill=fill + (255,), stroke_width=ol, stroke_fill=ink + (255,))
            tmp = tmp.rotate(g["rot"], resample=Image.BICUBIC, expand=False)
            layer_text.alpha_composite(tmp, (gx - ol - rp + g["box"][0], gy - ol - rp))
            tm = Image.new("L", tmp.size, 0)
            ImageDraw.Draw(tm).text((ox, oy), g["ch"], font=font, fill=255)
            fill_mask.paste(255, (gx - ol - rp + g["box"][0], gy - ol - rp), tm.rotate(g["rot"], resample=Image.BICUBIC, expand=False))
            if sh:
                tmp2 = Image.new("RGBA", tmp.size, (0, 0, 0, 0))
                ImageDraw.Draw(tmp2).text((ox, oy), g["ch"], font=font, fill=shadow_c + (255,), stroke_width=ol, stroke_fill=shadow_c + (255,))
                tmp2 = tmp2.rotate(g["rot"], resample=Image.BICUBIC, expand=False)
                layer_shadow.alpha_composite(tmp2, (gx - ol - rp + g["box"][0] + sh, gy - ol - rp + sh))
        else:
            if sh:
                ds.text((gx + sh, gy + sh), g["ch"], font=font, fill=shadow_c + (255,), stroke_width=ol, stroke_fill=shadow_c + (255,))
            dt.text((gx, gy), g["ch"], font=font, fill=fill + (255,), stroke_width=ol, stroke_fill=ink + (255,))
            dm.text((gx, gy), g["ch"], font=font, fill=255)
    extent = None  # (a drip flipbook's frames all crop to the FULL run, so every phase is the same size and place)
    if a.drip:
        drips = drip_mask(fill_mask, glyphs, margin, size, a, random.Random(a.seed * 101 + 7))
        # (phase 1 too: every frame's extent is the full run, whatever its phase)
        full = drip_mask(fill_mask, glyphs, margin, size, argparse.Namespace(**{**vars(a), "drip_phase": 1.0}), random.Random(a.seed * 101 + 7))
        if full.getbbox():
            extent = dilate(full, ol + 2 * sh)  # (the shadow sits sh down AND sh across: its corner reaches past ol + sh)
        if drips.getbbox() is None:  # (no drip drawn: an empty mask must not reach dilate — it paints a corner)
            drips = None
    if a.drip and drips is not None:
        if sh:  # (the drips cast the same hard shadow)
            s_l = Image.new("RGBA", (W, H), shadow_c + (255,))
            s_l.putalpha(dilate(drips, ol))
            layer_shadow.alpha_composite(s_l, (sh, sh))
        # the drip's ink edge only OUTSIDE the glyph's fill, then the drip's fill: the ink flows out of the letter
        edge = Image.fromarray((np.asarray(dilate(drips, ol), dtype=np.float32) * (1 - np.asarray(fill_mask, dtype=np.float32) / 255)).astype(np.uint8))
        e_l = Image.new("RGBA", (W, H), ink + (255,))
        e_l.putalpha(edge)
        layer_text.alpha_composite(e_l)
        f_l = Image.new("RGBA", (W, H), fill + (255,))
        f_l.putalpha(drips)
        layer_text.alpha_composite(f_l)
    if a.inline:  # an INLINE: a thin highlight line running inside every glyph's fill (1930s titles, sign painting)
        fm_ = np.asarray(fill_mask if not (a.drip and drips is not None) else Image.fromarray(np.maximum(np.asarray(fill_mask), np.asarray(drips))), dtype=np.uint8)
        inv = Image.fromarray((255 - fm_).astype(np.uint8))
        gap, wid = max(0, int(a.inline_gap * size)), max(1, int(a.inline_px * size))
        outer = 255 - np.asarray(dilate(inv, gap), dtype=np.int32)          # the fill eroded by the gap
        inner = 255 - np.asarray(dilate(inv, gap + wid), dtype=np.int32)    # eroded by gap + width
        band = np.clip(outer - inner, 0, 255).astype(np.uint8)
        # only where the FILL shows: a later glyph's outline over an earlier glyph's fill hides that part of the band
        lt = np.asarray(layer_text, dtype=np.int32)
        shows = (np.abs(lt[..., :3] - np.array(fill)).sum(-1) < 60) & (lt[..., 3] > 200)
        band = (band * shows).astype(np.uint8)
        il = Image.new("RGBA", (W, H), hex_rgb(a.inline) + (255,))
        il.putalpha(Image.fromarray(band))
        layer_text.alpha_composite(il)
    if glow_r:  # a SOFT halo under the word (a souls death word, a neon sign): the letters' alpha, blurred and tinted
        from PIL import ImageFilter
        halo_a = layer_text.getchannel("A").filter(ImageFilter.GaussianBlur(glow_r))
        halo_a = halo_a.point(lambda v: min(255, int(v * 1.6 * max(0.0, min(1.0, a.glow_alpha)))))
        halo = Image.new("RGBA", (W, H), hex_rgb(a.glow) + (255,))
        halo.putalpha(halo_a)
        im.alpha_composite(halo)
    im.alpha_composite(layer_shadow)
    im.alpha_composite(layer_text)
    # the crop's extent rides through the same slant and lean as the word
    ext = Image.new("L", im.size, 0)
    ext.paste(im.getchannel("A"), (0, 0))
    if extent is not None:
        ext = Image.fromarray(np.maximum(np.asarray(ext), np.asarray(extent)))
    if a.shear:  # an ITALIC slant (x per y; + leans right) — lean only rotates the whole word
        pad = int(abs(a.shear) * im.height) + 2
        wide = Image.new("RGBA", (im.width + pad, im.height), (0, 0, 0, 0))
        wide.paste(im, (0, 0))
        wext = Image.new("L", wide.size, 0)
        wext.paste(ext, (0, 0))
        # output x samples input x + shear*y + c: for a right lean the bottom stays and the top moves right by up to pad
        # (c = -shear*H); for a left lean the bottom moves right (c = 0) — the word always starts at x 0 (pasting it at
        # pad AND offsetting shifted a right lean twice and clipped its last glyph: review 2026-10-14)
        aff = (1, a.shear, -a.shear * wide.height if a.shear > 0 else 0, 0, 1, 0)
        im = wide.transform(wide.size, Image.AFFINE, aff, resample=Image.BICUBIC)
        ext = wext.transform(wext.size, Image.AFFINE, aff, resample=Image.BICUBIC)
    if a.widen and abs(a.widen - 1.0) > 1e-3:  # an EXTENDED face: the word scaled across (before the lean, like the slant)
        nw = max(1, int(round(im.width * a.widen)))
        im = im.resize((nw, im.height), Image.LANCZOS)
        ext = ext.resize((nw, ext.height), Image.BILINEAR)
    if a.lean:
        im = im.rotate(a.lean, resample=Image.BICUBIC, expand=True)
        ext = ext.rotate(a.lean, resample=Image.BICUBIC, expand=True)
    # crop to the ink (or a flipbook's full extent), downsample
    bbox = None if a.no_crop else ext.getbbox()
    if bbox:
        im = im.crop((max(0, bbox[0] - 4), max(0, bbox[1] - 4), min(im.width, bbox[2] + 4), min(im.height, bbox[3] + 4)))
    out = im.resize((max(1, im.width // SS), max(1, im.height // SS)), Image.LANCZOS)
    out_dir = os.path.join(a.art, ident)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{piece}.png")
    out.save(out_path)
    side = {"schema": 1, "kind": "letter", "text": a.text, "font": a.font, "font_file": os.path.basename(ff), "size": a.size,
            "fill": a.fill, "ink": a.ink, "outline": a.outline, "shadow": a.shadow, "lean": a.lean, "shear": a.shear, "widen": a.widen, "cards": a.cards,
            "card_color": a.card_color, "track": a.track, "wobble": a.wobble, "arc": a.arc, "inline": a.inline, "inline_px": a.inline_px, "inline_gap": a.inline_gap, "glow": a.glow, "glow_px": a.glow_px, "glow_alpha": a.glow_alpha, "bounce": a.bounce, "drip": a.drip,
            "drip_share": a.drip_share, "drip_phase": a.drip_phase, "seed": a.seed, "out": [out.width, out.height],
            "about": f"flat cut lettering '{a.text}' in {a.font} ({'glyph cards, ' if a.cards else ''}outline {a.outline} em, shadow {a.shadow} em, lean {a.lean})",
            "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(os.path.join(out_dir, f"{piece}.letter.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(side, fh, indent=1)
    return emit("pass", f"letter: {ident}/{piece}.png {out.width}x{out.height} — '{a.text}' in {a.font}, {'cards, ' if a.cards else ''}outline {ol // SS}px, shadow {sh // SS}px, lean {a.lean}",
                f"use it as art:{ident}/{piece} (size it by its 1080p box, never stretch); LOOK at it on the field it will sit on")


if __name__ == "__main__":
    raise SystemExit(main())
