"""dailies_page.py — the DAILIES picture of one beat (kit vfx dailies): the reference scene's consecutive frames
above our effect's frames at the same times, every frame large, and the two timing curves over each other. Drawing
only (Pillow + numpy): it is handed frames and curves, it reads no file and measures nothing (kit/vfx/dense.py does).

A director watches dailies at the size and speed the audience will; a session read contact sheets of thumbnails and
never the motion (the VFX studio-route plan, V0). So each frame here is at least 640 px wide, a held drawing is
marked on the frame that repeats it, the hit frame is ringed, and the page is cut into rows a reader zooms into.
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont

PAGE, PANEL, INK, DIM = (16, 17, 20), (28, 30, 35), (232, 232, 238), (150, 152, 160)
SCENE, OURS, HITC, HELDC = (255, 176, 64), (96, 196, 255), (255, 72, 72), (120, 220, 140)
GAP = 10


def _font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def tile(frame, width, label, colour, hit=False, held=False):
    """one frame at `width` px with its label; the hit ringed, a held drawing marked"""
    im = Image.fromarray(np.asarray(frame, dtype=np.uint8)).convert("RGB")
    height = max(1, int(round(im.height * width / float(im.width))))
    im = im.resize((width, height), Image.LANCZOS)
    cell = Image.new("RGB", (width, height + 30), PANEL)
    cell.paste(im, (0, 30))
    d = ImageDraw.Draw(cell)
    d.text((8, 5), label, fill=colour, font=_font(18))
    if held:
        d.text((width - 76, 5), "HELD", fill=HELDC, font=_font(18))
    if hit:
        d.rectangle([1, 31, width - 2, height + 28], outline=HITC, width=5)
        d.text((width - (156 if held else 60), 5), "HIT", fill=HITC, font=_font(18))
    return cell


def blank(width, height, text):
    """a tile-sized panel that says why there is no frame (our recording does not reach that moment)"""
    cell = Image.new("RGB", (width, height), PANEL)
    ImageDraw.Draw(cell).text((8, 5), text, fill=DIM, font=_font(18))
    return cell


def strips(scene_tiles, our_tiles, per=2):
    """the pictures a session reads at FULL size: `per` consecutive frames each, the scene's above ours (a reader's
    picture is shrunk past about 1500 px wide, so a whole page of 640 px frames arrives as thumbnails; two frames a
    picture arrive as they are) -> [PIL image]"""
    count = max(len(scene_tiles or []), len(our_tiles or []))
    out = []
    for a in range(0, count, per):
        bands = [rows(side[a:a + per], per) for side in (scene_tiles, our_tiles) if side and side[a:a + per]]
        w = max(b.width for b in bands)
        im = Image.new("RGB", (w, sum(b.height for b in bands) + GAP * (len(bands) - 1)), PAGE)
        y = 0
        for b in bands:
            im.paste(b, (0, y))
            y += b.height + GAP
        out.append(im)
    return out


def rows(tiles, per_row):
    """tiles laid left to right, `per_row` a row -> one picture"""
    if not tiles:
        return Image.new("RGB", (8, 8), PAGE)
    w, h = tiles[0].size
    n = (len(tiles) + per_row - 1) // per_row
    out = Image.new("RGB", (per_row * w + (per_row - 1) * GAP, n * h + (n - 1) * GAP), PAGE)
    for i, t in enumerate(tiles):
        out.paste(t, ((i % per_row) * (w + GAP), (i // per_row) * (h + GAP)))
    return out


def curve_panel(scene, ours, width, height=300):
    """the light on screen over time, each side as a share of its own hit, the two hits laid on one moment (0 s).
    scene / ours: {"seconds": [...] (0 at its hit), "energy": [...], "name": str} or None"""
    im = Image.new("RGB", (width, height), PANEL)
    d = ImageDraw.Draw(im)
    left, right, top, bottom = 70, width - 20, 34, height - 38
    sides = [s for s in (scene, ours) if s and len(s["seconds"])]
    if not sides:
        d.text((left, top), "no light measured on either side", fill=DIM, font=_font(20))
        return im
    t0 = min(min(s["seconds"]) for s in sides)
    t1 = max(max(s["seconds"]) for s in sides)
    span = max(t1 - t0, 1e-6)

    def x_of(t):
        return left + (t - t0) / span * (right - left)

    d.line([(left, bottom), (right, bottom)], fill=DIM, width=1)
    d.line([(x_of(0.0), top), (x_of(0.0), bottom)], fill=HITC, width=2)
    d.text((x_of(0.0) + 6, top - 4), "hit", fill=HITC, font=_font(16))
    step = 0.1 if span <= 1.6 else 0.25 if span <= 4 else 0.5
    t = np.ceil(t0 / step) * step
    while t <= t1 + 1e-9:
        d.line([(x_of(t), bottom), (x_of(t), bottom + 6)], fill=DIM, width=1)
        d.text((x_of(t) - 18, bottom + 9), f"{t:+.2f}s", fill=DIM, font=_font(14))
        t += step
    for side, colour in ((scene, SCENE), (ours, OURS)):
        if not side or not len(side["seconds"]):
            continue
        e = np.asarray(side["energy"], dtype=np.float64)
        e = e / max(float(e.max()), 1e-12)
        pts = [(x_of(float(s)), bottom - float(v) * (bottom - top)) for s, v in zip(side["seconds"], e)]
        # a stepped line: a frame's light lasts until the next frame (a held drawing is a flat run)
        stepped = []
        for i, p in enumerate(pts):
            if i:
                stepped.append((p[0], pts[i - 1][1]))
            stepped.append(p)
        d.line(stepped, fill=colour, width=3)
    d.text((left, 6), "light on screen (each as a share of its own hit); a flat run = a drawing held", fill=INK,
           font=_font(16))
    if scene:
        d.text((right - 420, 6), scene.get("name", "the scene"), fill=SCENE, font=_font(16))
    if ours:
        d.text((right - 200, 6), ours.get("name", "ours"), fill=OURS, font=_font(16))
    return im


def page(title, lines, scene_tiles, our_tiles, scene_curve, our_curve, per_row=6):
    """the whole dailies picture of one beat: the title and what was measured (lines), the scene's frames, ours
    under them, the curves -> a PIL image. A side with no tiles (None or []) is left out: the scene alone is a
    breakdown's dense read, ours alone an effect with no scene clip on this machine."""
    bands = [(name, colour, rows(side, per_row)) for name, colour, side in (
        ("THE SCENE, frame by frame", SCENE, scene_tiles), ("OURS, at the same moments from the hit", OURS, our_tiles))
        if side]
    width = max([b.width for _, _, b in bands] + [1280])
    curves = curve_panel(scene_curve, our_curve, width)
    head_h = 44 + 26 * len(lines)
    out = Image.new("RGB", (width, head_h + sum(34 + b.height for _, _, b in bands) + GAP + curves.height + GAP), PAGE)
    d = ImageDraw.Draw(out)
    d.text((10, 8), title, fill=INK, font=_font(26))
    for i, line in enumerate(lines):
        d.text((10, 44 + 26 * i), line, fill=DIM, font=_font(18))
    y = head_h
    for name, colour, band in bands:
        d.text((10, y + 4), name, fill=colour, font=_font(20))
        out.paste(band, (0, y + 34))
        y += 34 + band.height
    out.paste(curves, (0, y + GAP))
    return out
