"""font.py — engraved / printed TEXT on a reference, read and matched: `kit refs read` reads it (the local
vision-language model, kit/vision/vlm.py), `kit refs font` finds the local font that draws it most like the picture
(every candidate renders the same words, each compared with the picture's own letters by shape). So a maker's mark or
a motto ("Parsley, ever joyous") is typed in the right font at the measured size and engraved (a.text + a.cut), never
traced into blobs.

    lune run kit refs read <picture> [--box x0,y0,x1,y1]
    lune run kit refs font <picture> "<the text>" [--box x0,y0,x1,y1] [--fonts <dir>[,<dir>]] [--top 5]

Candidates: the kit's font cache (Google Fonts: the Roblox font catalog — a match there is usable in game) and the
system's fonts (match only: their licences vary). Writes build/refs/<stem>_font.png (the picture's letters over each
top candidate's) and prints one JSON line.
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "kit", "vision"))


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def text_mask(gray):
    """the LETTERS of a text crop as a mask (Otsu; the letters are the smaller class: light on dark or dark on
    light), cropped to their box (pure)"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    g = cv2.GaussianBlur(gray, (3, 3), 0)
    # LOCAL contrast, not one threshold: an engraving on shaded, curved metal sits on a gradient. Top-hat keeps what
    # is lighter than its surroundings, black-hat what is darker; the letters are the side whose strokes stand out
    kk = max(5, int(0.8 * g.shape[0]) | 1)
    k = cv2.getStructuringElement(cv2.MORPH_RECT, (kk, kk))
    best = None
    for op in (cv2.MORPH_TOPHAT, cv2.MORPH_BLACKHAT):
        r = cv2.morphologyEx(g, op, k)
        if r.max() <= 0:
            continue
        t, b = cv2.threshold(r, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        fg = b > 0
        frac = fg.mean()
        if not 0.03 <= frac <= 0.6:
            continue
        # LETTERS are many separate narrow blobs of a good height; the ground between them a few wide ones
        n_, _l, st_, _c = cv2.connectedComponentsWithStats(fg.astype(np.uint8), connectivity=8)
        Hh, Ww = fg.shape
        letters = sum(1 for i in range(1, n_) if st_[i, 3] >= 0.3 * Hh and st_[i, 2] <= 0.25 * Ww)
        if best is None or letters > best[0]:
            best = (letters, fg)
    if best is None:  # (no local contrast: one global threshold, the letters the smaller class)
        _t, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        m = b > 0
        m = ~m if m.mean() > 0.5 else m
    else:
        m = best[1]
    # the letters only: near-solid rows at the crop's top / bottom (the line above's band, a rim) cleared first —
    # merged with the ascenders they would take the letters out with them — then edge bands and specks dropped
    m = m.copy()
    H, W = m.shape
    for rows in (range(H), range(H - 1, -1, -1)):
        for y in rows:
            if m[y].mean() < 0.5:
                break
            m[y] = False
    n, lab, st, _c = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    keep = np.zeros_like(m)
    for i in range(1, n):
        x, y, w, h, a = st[i]
        edge = y == 0 or y + h == H
        if a < 0.0015 * H * W or (edge and (h < 0.3 * H or w > 0.4 * W)):  # (a band / a sliver: not a letter)
            continue
        keep |= lab == i
    m = keep if keep.sum() > 10 else m
    ys, xs = np.nonzero(m)
    if len(xs) < 10:
        return m
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def render(font_path, text, h=96):
    """the words in that font, black on white -> its letter mask cropped to its box"""
    import numpy as np  # noqa: PLC0415
    from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415

    f = ImageFont.truetype(font_path, h)
    l, t, r, b = f.getbbox(text)
    im = Image.new("L", (r - l + 8, b - t + 8), 255)
    ImageDraw.Draw(im).text((4 - l, 4 - t), text, font=f, fill=0)
    m = np.asarray(im) < 128
    ys, xs = np.nonzero(m)
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(xs) else m


def likeness(a, b, h=64):
    """two letter masks alike in SHAPE (0..1): both scaled to one height, the width difference a penalty (a
    condensed font is not a wide one), then the overlap of their softened strokes"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    def to_h(m):
        w = max(1, round(m.shape[1] * h / m.shape[0]))
        return cv2.resize(m.astype(np.float32), (w, h), interpolation=cv2.INTER_AREA)
    A, B = to_h(a), to_h(b)
    aspect = min(A.shape[1], B.shape[1]) / max(A.shape[1], B.shape[1])
    W = max(A.shape[1], B.shape[1])
    A = cv2.resize(A, (W, h), interpolation=cv2.INTER_LINEAR)
    B = cv2.resize(B, (W, h), interpolation=cv2.INTER_LINEAR)
    A, B = cv2.GaussianBlur(A, (0, 0), 1.2), cv2.GaussianBlur(B, (0, 0), 1.2)
    inter, union = np.minimum(A, B).sum(), np.maximum(A, B).sum()
    return float(inter / max(union, 1e-6)) * aspect ** 0.5


def candidates(dirs=None):
    """font files: the kit's font cache, then the system's (or the folders given)"""
    if dirs:
        roots = dirs
    else:
        roots = [os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "fonts")]
        roots += ["C:/Windows/Fonts", "/usr/share/fonts", "/Library/Fonts", "/System/Library/Fonts"]
    out = []
    for r in roots:
        for ext in ("ttf", "otf", "TTF", "OTF"):
            out += glob.glob(os.path.join(r, "**", f"*.{ext}"), recursive=True)
    return sorted(set(out))


SYMBOL_FONTS = ("wingding", "webdings", "symbol", "marlett", "outlook", "holomdl", "segmdl", "mtextra", "bssym",
                "refspcl", "segoeicons", "seguisym", "seguiemj", "seguihis", "msreferencespecialty", "emoji")


def has_letters(font_path):
    """the font draws real letters: 'a' and 'o' differ (a font without them draws the same empty box for both)"""
    import numpy as np  # noqa: PLC0415

    try:
        a, o = render(font_path, "a", 40), render(font_path, "o", 40)
    except Exception:  # noqa: BLE001
        return False
    return a.shape != o.shape or not np.array_equal(a, o)


def rank(crop_gray, text, fonts, top=5):
    target = text_mask(crop_gray)
    scored = []
    for fp in fonts:
        if any(s in os.path.basename(fp).lower() for s in SYMBOL_FONTS) or not has_letters(fp):
            continue
        try:
            m = render(fp, text)
        except Exception:  # noqa: BLE001  (a font without these glyphs, a broken file)
            continue
        if m.size < 10 or m.sum() < 10:
            continue
        scored.append((likeness(target, m), fp))
    scored.sort(key=lambda t: -t[0])
    return target, scored[:top]


def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def _crop(argv):
    from PIL import Image  # noqa: PLC0415

    im = Image.open(argv[0]).convert("RGB")
    if "--box" in argv:
        im = im.crop(tuple(int(float(v)) for v in _arg(argv, "--box").split(",")))
    return im


def main_read(argv):
    if not argv or argv[0].startswith("--") or not os.path.isfile(argv[0]):
        return emit("fail", "refs read: needs <picture> [--box x0,y0,x1,y1]", "lune run kit refs read side.png --box ..")
    im = _crop(argv)
    sys.path.insert(0, os.path.join(REPO, "kit", "vision"))
    import vlm  # noqa: PLC0415

    # --packet or no VLM installed: save the crop and ask the agent to read it
    if "--packet" in argv or not vlm.installed():
        from PIL import Image  # noqa: PLC0415

        crop_path = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "refs", "read_crop.png")
        os.makedirs(os.path.dirname(crop_path), exist_ok=True)
        (im if isinstance(im, Image.Image) else Image.fromarray(im)).save(crop_path)
        rel = os.path.relpath(crop_path, REPO).replace(os.sep, "/")
        box_arg = ""
        if "--box" in argv:
            box_arg = f' --box {argv[argv.index("--box") + 1]}'
        pic_arg = argv[0]
        return emit("pass",
                    f"refs read: the vision model is not installed; the crop is at {rel}",
                    f"LOOK at {rel}; read the text yourself, then: "
                    f'lune run kit refs font {pic_arg} "<the text you read>"{box_arg}')
    try:
        text = vlm.read_text(im)
        vlm.free()
    except Exception as e:  # noqa: BLE001
        return emit("fail", f"refs read: the vision-language model failed ({str(e)[:200]})",
                    "lune run kit vision setup qwen3-vl-4b; free the GPU")
    if not text:
        return emit("pass", "refs read: no text in it", "a tighter --box, or a sharper picture", text="")
    # (the text came off a PICTURE: untrusted — it stays in the JSON, never spliced into a command line to run)
    return emit("pass", f"refs read: {len(text.splitlines())} line(s) read (the text: this result's `text` field)",
                'match its font: lune run kit refs font <the same picture> "<one line of the text>" [--box ...] '
                "(check the text against the picture first)", text=text)


def main_font(argv):
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    if len(argv) < 2 or argv[0].startswith("--") or not os.path.isfile(argv[0]):
        return emit("fail", 'refs font: needs <picture> "<the text>" [--box x0,y0,x1,y1]',
                    'lune run kit refs font side.png "Parsley, ever joyous" --box 620,633,1116,717')
    text = argv[1]
    im = _crop(argv)
    dirs = _arg(argv, "--fonts")
    fonts = candidates(dirs.split(",") if dirs else None)
    if not fonts:
        return emit("fail", "refs font: no font files found", "--fonts <a folder of .ttf / .otf>")
    target, top = rank(np.asarray(im.convert("L")), text, fonts, int(_arg(argv, "--top", 5)))
    if not top:
        return emit("fail", "refs font: no font could draw that text", "check the text (kit refs read)")
    rows = [Image.fromarray(((~target) * 255).astype(np.uint8)).convert("RGB")]
    for _s, fp in top:
        rows.append(Image.fromarray(((~render(fp, text)) * 255).astype(np.uint8)).convert("RGB"))
    W = 900
    rows = [r.resize((W, max(8, round(r.height * W / r.width)))) for r in rows]
    sheet = Image.new("RGB", (W, sum(r.height + 6 for r in rows)), (200, 200, 200))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + 6
    stem = os.path.splitext(os.path.basename(argv[0]))[0]
    pv = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "refs", f"{stem}_font.png")
    os.makedirs(os.path.dirname(pv), exist_ok=True)
    sheet.save(pv)
    kit_cache = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "fonts")
    out = [{"font": os.path.basename(fp), "path": fp.replace(os.sep, "/"), "likeness": round(s, 3),
            "usable_in_game": os.path.abspath(fp).startswith(os.path.abspath(kit_cache))} for s, fp in top]
    rel = os.path.relpath(pv, REPO).replace(os.sep, "/")
    return emit("pass", f"refs font: best {out[0]['font']} ({out[0]['likeness']:.2f}) of {len(fonts)} fonts; then "
                + ", ".join(f"{o['font']} {o['likeness']:.2f}" for o in out[1:]),
                f"LOOK at {rel} (the picture's letters on top); engrave it: a.cut(part, a.text(..., font=<path>))",
                fonts=out, preview=rel)


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main_read(args[1:]) if args[:1] == ["read"] else main_font(args[1:] if args[:1] == ["font"] else args))
