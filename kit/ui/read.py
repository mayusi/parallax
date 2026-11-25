"""read.py — REFERENCE UNDERSTANDING for UI: what a game still's interface IS, where each piece sits, how big it is
at 1080p and what colours it uses — read by the kit's local SigLIP 2 (kit/vision) instead of eyeballed.

    python kit/ui/read.py <still> [--vocab hud|menu|all] [--out <dir>]          -> <still>.read.json + <still>.read.png
    python kit/ui/read.py rank <folder> "<what you need>" [--top N] [--keep N --identity <id>]
                                                                                -> ranks.json + ranked contact sheet

read  slides windows (two scales) over the still at 1920x1080, scores every window against a UI vocabulary
      (minimap, ammo counter, health bar, compass, kill feed, crosshair, button prompt, objective marker, dialogue box,
      menu list, logo or title, character portrait, timer or score, inventory slots, skill icons) AND "plain game scene";
      neighbouring windows with the same winning label merge into one element; each element's box is tightened to the
      high-contrast pixels inside it; dominant colours sampled. The board draws every element with its label + box.
rank  orders reference candidates by how well each shows WHAT YOU NEED (SigLIP on the whole frame + on its edge bands,
      where a HUD lives) against what you do not (key art, a poster, a cinematic frame with no interface, an icon):
      a store page's marketing shots sink, real gameplay HUD stills rise. --keep N copies the top N into refs/<id>/.
A READING, not a measurement of truth: check the board before building from it; measure exact pixels with
kit ui measure when a number matters.
"""
import argparse
import io
import json
import math
import os
import re
import shutil
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "vision"))

VOCAB_HUD = {
    "minimap": "a square or round minimap of the level in a corner of a video game screen",
    "ammo counter": "an ammo counter: large numbers of bullets left with a weapon name, in a game HUD corner",
    "health bar": "a health bar or hit point meter in a video game HUD",
    "compass": "a horizontal compass strip with bearings and markers at the top of a game screen",
    "kill feed": "a kill feed: a short list of player names and small weapon icons in a game HUD",
    "crosshair": "a small crosshair or aiming reticle at the centre of a game screen",
    "button prompt": "a button prompt: a small key or controller button icon next to an action word",
    "objective marker": "an objective marker: a small diamond or icon with a distance in metres floating in the game world",
    "timer or score": "a match timer or score counter with large digits in a game HUD",
    "skill icons": "a row of ability or skill icons with cooldowns in a game HUD",
    "character portrait": "a small character portrait with a name and health in a game HUD",
}
VOCAB_MENU = {
    "logo or title": "a large stylised game logo or title text",
    "menu list": "a vertical list of menu options like new game, continue, options",
    "dialogue box": "a dialogue box with a character name and lines of text",
    "inventory slots": "a grid of inventory item slots with icons",
    "character portrait": "a character portrait or character art in a menu",
    "button prompt": "a button prompt: a small key or controller button icon next to an action word",
}
SCENE = "a part of a 3D video game scene with no interface, text or icons"


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _vision():
    import contextlib
    import io
    import warnings
    warnings.filterwarnings("ignore")
    with contextlib.redirect_stderr(io.StringIO()):
        import run as V  # noqa: PLC0415  (kit/vision/run.py: SigLIP 2, offline, pinned)
    return V


def logits(V, images, texts):
    """SigLIP logits (n_images, n_texts) — batched; the sigmoid of a logit is SigLIP's own probability"""
    model, _proc = V._siglip()
    out = []
    for i in range(0, len(images), 32):
        out.append(V.embed(images[i:i + 32]))
    img = np.concatenate(out, axis=0)
    txt = V.embed_text(texts)
    return img @ txt.T * float(model.logit_scale.exp().detach()) + float(model.logit_bias.detach())


def where(cx, cy):
    col = "l" if cx < 640 else ("c" if cx < 1280 else "r")
    row = "t" if cy < 360 else ("m" if cy < 720 else "b")
    return {"tl": "top-left", "tc": "top-centre", "tr": "top-right", "ml": "middle-left", "mc": "centre",
            "mr": "middle-right", "bl": "bottom-left", "bc": "bottom-centre", "br": "bottom-right"}[row + col]


def tighten(gray, box, pad=6):
    """the box shrunk to the high-contrast pixels inside it (UI strokes, text, frames)"""
    x0, y0, x1, y1 = box
    region = gray[y0:y1, x0:x1]
    if region.size == 0:
        return box
    gy, gx = np.gradient(region.astype(np.float32))
    mag = np.hypot(gx, gy)
    thr = max(18.0, np.percentile(mag, 92))
    ys, xs = np.where(mag > thr)
    if len(xs) < 20:
        return box
    # drop the sparse outskirts: the 2nd..98th percentile of the strong pixels
    lx, hx = np.percentile(xs, [2, 98])
    ly, hy = np.percentile(ys, [2, 98])
    return [int(max(0, x0 + lx - pad)), int(max(0, y0 + ly - pad)), int(min(gray.shape[1], x0 + hx + pad)), int(min(gray.shape[0], y0 + hy + pad))]


def colours(img, box, k=3):
    crop = img.crop(box).convert("RGB").resize((48, 48))
    q = crop.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: k * 3]
    counts = sorted(q.getcolors(), reverse=True)
    out = []
    for n, idx in counts[:k]:
        r, g, b = pal[idx * 3: idx * 3 + 3]
        out.append({"hex": "#%02x%02x%02x" % (r, g, b), "share": round(n / (48 * 48), 2)})
    return out


CATS = {"map": "a top-down map with roads and icons", "digits": "large white numbers", "text": "a line of small text",
        "bar": "a thin horizontal bar or meter", "icon": "a small flat icon", "panel": "a dark rectangular interface panel",
        "art": "a stylised logo, emblem or character illustration",
        "graphic": "bold stylised graphic lettering or numbers, a cut-out sticker of words",
        "scene": "a photo of a 3D game scene"}


# the genre picks the naming conventions; SigLIP's logits are absolute (a sigmoid), so a genre counts only above a
# floor (measured: GGST fight stills -0.6..-1.3, a CoD still -1.4 shooter; Persona's Tokyo walk -3.3, Witch Time -4.9)
GENRES = [("fighting", "a fighting game: two fighters face each other, a health bar for each across the top"),
          ("fighting", "a 2D fighting game screenshot like Street Fighter or Guilty Gear, two health bars and a round timer"),
          ("shooter", "a first-person or third-person shooter game with a gun on screen"),
          # (a combat scene in a 2D platformer read as a fighting game: Hollow Knight -1.98 platformer vs -4.14 fighting)
          ("platformer", "a 2D side-scrolling platformer or metroidvania game: a small character in a large painted level"),
          # (Need for Speed Heat's stills read 'other': a race HUD needs its own conventions — speedometer, minimap, position)
          ("racing", "a racing game screenshot: a car seen from behind on a road, a speedometer and a minimap on screen")]
GENRE_FLOOR = -2.5
GENRE_MARGIN = 0.5


def pick_genre(gl):
    """the genre whose best prompt clears the floor AND beats every OTHER genre's best by the margin; else 'other' (a
    near tie applied fighting-game names to a platformer: Hollow Knight -1.81 fighting vs -1.98 platformer)"""
    best = {}
    for (g, _t), v in zip(GENRES, gl):
        best[g] = max(best.get(g, -1e9), float(v))
    order = sorted(best.items(), key=lambda kv: -kv[1])
    top, rest = order[0], order[1:]
    if top[1] <= GENRE_FLOOR or (rest and top[1] - rest[0][1] < GENRE_MARGIN):
        return "other"
    return top[0]
FIGHTING = {("bar", "top-left"): "P1 health bar", ("bar", "top-right"): "P2 health bar", ("bar", "top-centre"): "health bars",
            ("digits", "top-centre"): "round timer", ("art", "top-left"): "P1 portrait", ("art", "top-right"): "P2 portrait",
            ("bar", "bottom-left"): "P1 super / tension gauge", ("bar", "bottom-right"): "P2 super / tension gauge",
            ("text", "bottom-left"): "P1 super / tension gauge", ("text", "bottom-right"): "P2 super / tension gauge",
            ("graphic", "top-left"): "combo counter / callout", ("graphic", "top-right"): "combo counter / callout",
            ("panel", "top-left"): "combo counter / callout", ("panel", "top-right"): "combo counter / callout",
            ("graphic", "centre"): "round call (ROUND 1, FIGHT, KO)", ("graphic", "top-centre"): "round call (ROUND 1, FIGHT, KO)"}


# a TURN-BASED RPG battle (Persona, Final Fantasy, Dragon Quest) is NOT told from the frame: measured 2026-10-14, every
# rpg prompt that lifts a stylized anime RPG's battle stills (-1.6) also lifts Strive / Tekken (-0.1 .. -1.2) and steals 7 of 20 read
# stills — the folder's game is known when it is gathered, so the reader is TOLD: kit ui read <still> --genre rpg
RPG = {("graphic", "top-left"): "skill / action name", ("panel", "top-left"): "skill / action name", ("text", "top-left"): "skill / action name",
       ("graphic", "centre"): "hit callout (WEAK / CRITICAL)", ("graphic", "middle-right"): "hit callout (WEAK / CRITICAL)",
       ("digits", "centre"): "damage number", ("digits", "middle-right"): "damage number",
       ("panel", "middle-right"): "command menu", ("text", "middle-right"): "command menu", ("panel", "bottom-centre"): "command menu",
       ("art", "top-right"): "turn order / navigator", ("graphic", "top-right"): "turn order / navigator"}
# a RACING HUD: the speedometer / tach in a bottom corner (usually right), the minimap in the other, the race position
# and lap at the top, the nitro / boost gauge a low bar by the dial
RACING = {("art", "bottom-right"): "speedometer / tach dial", ("graphic", "bottom-right"): "speedometer / tach dial",
          ("digits", "bottom-right"): "speedometer / tach dial", ("panel", "bottom-right"): "speedometer / tach dial",
          ("map", "bottom-left"): "minimap", ("graphic", "bottom-left"): "minimap", ("panel", "bottom-left"): "minimap",
          ("art", "bottom-left"): "minimap", ("digits", "top-left"): "race position / lap", ("text", "top-left"): "race position / lap",
          ("graphic", "top-left"): "race position / lap", ("digits", "top-right"): "race timer", ("text", "top-right"): "race timer",
          ("bar", "bottom-right"): "nitro / boost gauge", ("bar", "bottom-centre"): "nitro / boost gauge"}
GENRE_NAMES = ("fighting", "shooter", "platformer", "rpg", "racing", "other")


def rpg_role(box):
    """an RPG battle's party block: the members' status (portrait, HP, SP) as a strip along the bottom — wide and low"""
    x0, y0, x1, y1 = box
    if y0 > 0.72 * 1080 and (x1 - x0) > 1.6 * (y1 - y0) and x1 > 0.55 * 1920:
        return "party status (portraits, HP / SP)"
    return None


def fight_role(box):
    """a fighting game's pieces are told apart by SHAPE and PLACE (its bars read as 'panels' to SigLIP): wide pieces in
    the top fifth are the health bars, wide pieces in the bottom fifth the super / tension gauges, P1 left, P2 right"""
    x0, y0, x1, y1 = box
    w, h, cx = x1 - x0, y1 - y0, (x0 + x1) / 2
    side = "P1 " if cx < 0.42 * 1920 else "P2 " if cx > 0.58 * 1920 else ""
    if w > 4 * h and y1 < 0.22 * 1080:
        return f"{side}health bar" if side else ("health bars" if w > 0.5 * 1920 else "round timer / centre")
    if w > 3 * h and y0 > 0.8 * 1080:
        return f"{side}super / tension gauge" if side else "super / tension gauges"
    return None


def role(cat, where_, w, h, genre=""):
    """a piece's job from WHAT it looks like + WHERE it sits (the conventions every HUD reference measured follows);
    the genre (read from the whole frame) picks the conventions: a fighting game's top bars are the two health bars and
    its bottom corners the super gauges, a shooter's bottom-right is the weapon block"""
    if genre == "fighting" and (cat, where_) in FIGHTING:
        return FIGHTING[(cat, where_)]
    if genre == "rpg" and (cat, where_) in RPG:
        return RPG[(cat, where_)]
    if genre == "racing" and (cat, where_) in RACING:
        return RACING[(cat, where_)]
    corner = where_ in ("top-left", "top-right", "bottom-left", "bottom-right")
    if where_ == "bottom-right" and cat in ("digits", "bar", "text", "icon", "panel") and w > 1.6 * h and genre not in ("fighting", "rpg"):
        return "weapon / ammo block"
    if cat == "map":
        return "minimap" if corner or where_.startswith("top") else "map"
    if cat == "digits":
        return {"bottom-right": "ammo / item count", "top-centre": "timer or score", "bottom-left": "health number"}.get(where_, "a counter")
    if cat == "bar":
        if where_ == "top-centre" and w > 3 * h:
            return "compass strip"
        return "health / progress bar" if where_.startswith("bottom") or where_.startswith("top") else "bar"
    if cat == "text":
        return {"top-right": "kill feed / notifications", "top-left": "objective / location text", "bottom-centre": "prompt or subtitle",
                "bottom-right": "weapon / item name", "centre": "world label"}.get(where_, "label text")
    if cat == "icon":
        return "button prompt / icon" if where_.startswith("bottom") else "icon"
    if cat == "panel":
        return "interface panel"
    if cat == "art":
        return "logo / emblem / portrait"
    if cat == "graphic":
        return {"top-left": "date / status card", "top-right": "status card", "top-centre": "title / callout",
                "centre": "callout"}.get(where_, "graphic lettering")
    return cat


def detect(gray, close=14, min_area=900, max_frac=0.22):
    """interface pieces as blocks of STRONG edges: the top few percent of the gradient, closed so glyphs join into
    words and words into blocks, split into connected components, filtered by size"""
    from scipy import ndimage as ndi
    g = gray.astype(np.float32)
    mag = np.hypot(ndi.sobel(g, 0), ndi.sobel(g, 1))
    thr = np.percentile(mag, 96.5)
    m = mag > thr
    m = ndi.binary_closing(m, structure=np.ones((close, close)))
    m = ndi.binary_opening(m, structure=np.ones((3, 3)))
    lab, n = ndi.label(m)
    boxes = []
    for sl in ndi.find_objects(lab):
        if sl is None:
            continue
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        w, h = x1 - x0, y1 - y0
        if w * h < min_area or w * h > max_frac * gray.size or w < 12 or h < 10:
            continue
        boxes.append([x0, y0, x1, y1])
    return boxes


def straighten(gray, box, run=0.45):
    """snap a box to the STRAIGHT borders inside it: a HUD panel's edge is a line of strong gradient across most of its
    width (or height); a scene (sand, foliage) never makes one. Keeps the box when no such lines exist."""
    x0, y0, x1, y1 = box
    r = gray[y0:y1, x0:x1].astype(np.float32)
    if r.shape[0] < 24 or r.shape[1] < 24:
        return box
    gy = np.abs(np.diff(r, axis=0))
    gx = np.abs(np.diff(r, axis=1))
    thr = max(14.0, np.percentile(np.concatenate([gy.ravel(), gx.ravel()]), 90))
    fr, fc = (gy > thr).mean(axis=1), (gx > thr).mean(axis=0)
    # near-complete lines first (a panel's border runs its whole length), else the looser run
    rows = np.where(fr > 0.85)[0] if (fr > 0.85).sum() >= 2 else np.where(fr > run)[0]
    cols = np.where(fc > 0.85)[0] if (fc > 0.85).sum() >= 2 else np.where(fc > run)[0]
    nx0, nx1, ny0, ny1 = x0, x1, y0, y1
    if len(rows) >= 2 and rows.max() - rows.min() > 24:
        ny0, ny1 = y0 + int(rows.min()), y0 + int(rows.max()) + 2
    if len(cols) >= 2 and cols.max() - cols.min() > 24:
        nx0, nx1 = x0 + int(cols.min()), x0 + int(cols.max()) + 2
    return [nx0, ny0, nx1, ny1]


def split_bands(gray, box, min_h=28):
    """a block that stacks parts divided by full-width lines (a map over its caption) -> one box per part"""
    x0, y0, x1, y1 = box
    r = gray[y0:y1, x0:x1].astype(np.float32)
    if r.shape[0] < 2 * min_h:
        return [box]
    gy = np.abs(np.diff(r, axis=0))
    thr = max(14.0, np.percentile(gy, 90))
    lines = np.where((gy > thr).mean(axis=1) > 0.85)[0]
    cuts = [0]
    for ln in lines:
        if ln - cuts[-1] >= min_h:
            cuts.append(int(ln))
    if r.shape[0] - cuts[-1] >= min_h:
        cuts.append(r.shape[0])
    else:
        cuts[-1] = r.shape[0]
    if len(cuts) <= 2:
        return [box]
    return [[x0, y0 + a, x1, y0 + b] for a, b in zip(cuts, cuts[1:]) if b - a >= min_h]


def heat_regions(V, img, gray, thr=0.8, size=192, stride=96):
    """WHERE the interface is: SigLIP's interface-vs-scene score on sliding windows (a heat map: on a sunlit frame the
    minimap corner scored ~2.2, the ammo corner ~1.3, sand below 0), hot cells joined into regions, each region's box
    tightened to its strong-contrast pixels"""
    from scipy import ndimage as ndi
    # two kinds of interface: the quiet HUD (text, numbers, a map, bars) and the GRAPHIC one (Persona's date card,
    # stylised words and logos printed over the picture); the stronger of the two vs the scene
    q = ["interface graphics overlaid on a game screen: text, numbers, icons, a map or bars",
         "bold stylised graphic text, a logo or a cut-out sticker printed over a picture",
         "a photo of a 3D game scene"]
    xs = list(range(0, 1920 - size + 1, stride))
    ys = list(range(0, 1080 - size + 1, stride))
    crops = [img.crop((x, y, x + size, y + size)) for y in ys for x in xs]
    L = logits(V, crops, q)
    heat = (np.maximum(L[:, 0], L[:, 1]) - L[:, 2]).reshape(len(ys), len(xs))
    # one interface piece can read hot-cool-hot across its cells (a minimap's busy middle): join diagonal neighbours and
    # close one-cell gaps before labelling, or a minimap splits into pieces
    hot = ndi.binary_closing(heat > thr, structure=np.ones((3, 3)), border_value=0) | (heat > thr)
    lab, n = ndi.label(hot, structure=np.ones((3, 3)))
    boxes = []
    for k in range(1, n + 1):
        cells = np.argwhere(lab == k)
        y0, x0 = cells.min(axis=0)
        y1, x1 = cells.max(axis=0)
        box = [xs[x0], ys[y0], xs[x1] + size, ys[y1] + size]
        snapped = straighten(gray, box)
        boxes.append(snapped if snapped != box else tighten(gray, box, pad=4))
    return boxes


def edge_strips(V, img, gray, boxes, thr=0.8, w=384, h=96, stride=192):
    """the THIN pieces along the top and bottom edges (a fighting game's health bars, a super gauge, a compass): a
    192 px square window there is mostly scene and scores cool, so score 384x96 strips along both edges too; a hot run
    of strips becomes a box, kept only where no window-found piece already sits"""
    q = ["interface graphics overlaid on a game screen: text, numbers, icons, a map or bars",
         "bold stylised graphic text, a logo or a cut-out sticker printed over a picture",
         "a photo of a 3D game scene"]
    xs = list(range(0, 1920 - w + 1, stride))
    rows = [0, 1080 - h]
    crops = [img.crop((x, y, x + w, y + h)) for y in rows for x in xs]
    L = logits(V, crops, q)
    heat = (np.maximum(L[:, 0], L[:, 1]) - L[:, 2]).reshape(len(rows), len(xs))
    found = []
    for r, y in enumerate(rows):
        i = 0
        while i < len(xs):
            if heat[r, i] <= thr:
                i += 1
                continue
            j = i
            while j + 1 < len(xs) and heat[r, j + 1] > thr:
                j += 1
            box = tighten(gray, [xs[i], y, xs[j] + w, y + h], pad=4)
            area = max(1, (box[2] - box[0]) * (box[3] - box[1]))
            covered = sum(max(0, min(box[2], b[2]) - max(box[0], b[0])) * max(0, min(box[3], b[3]) - max(box[1], b[1])) for b in boxes)
            if covered < 0.3 * area:
                found.append(box)
            i = j + 1
    return found


def find_described(V, img, gray, words, sizes=(160, 240, 360)):
    """WHERE the thing you describe is ('a round soul vessel and a row of mask icons'): square windows scored by SigLIP
    against 'part of a game scene'; the 8 best are grouped where they overlap and the group with the highest TOTAL wins
    (a lone glowing light scored highest on Hollow Knight; three windows on the real HUD outweighed it) -> (box, score)"""
    q = [words, "part of a video game scene with no interface"]
    boxes = []
    for size in sizes:
        st = size // 2
        boxes += [[x, y, x + size, y + size] for y in range(0, 1080 - size + 1, st) for x in range(0, 1920 - size + 1, st)]
    L = logits(V, [img.crop(b) for b in boxes], q)
    sc = L[:, 0] - L[:, 1]
    top = [int(i) for i in np.argsort(-sc)[:8] if sc[i] > 0]
    if not top:  # (nothing reads as what was described: say so, never box a lone negative window)
        return None, float(sc.max())
    groups = [{"boxes": [boxes[i]], "scores": [float(sc[i])]} for i in top]
    merged = True
    while merged:  # (join every pair of groups whose windows overlap — a bridging window once split a chain in two)
        merged = False
        for g1 in groups:
            for g2 in groups:
                if g1 is not g2 and any(b[0] < o[2] and o[0] < b[2] and b[1] < o[3] and o[1] < b[3] for b in g1["boxes"] for o in g2["boxes"]):
                    g1["boxes"] += g2["boxes"]
                    g1["scores"] += g2["scores"]
                    groups.remove(g2)
                    merged = True
                    break
            if merged:
                break
    best = max(groups, key=lambda g: sum(g["scores"]))
    bb = [min(b[0] for b in best["boxes"]), min(b[1] for b in best["boxes"]), max(b[2] for b in best["boxes"]), max(b[3] for b in best["boxes"])]
    # (confidence on the SAME scale as the other pieces' margins: the mean window score, not a sum of up to 8)
    return tighten(gray, bb, pad=6), round(float(np.mean(best["scores"])), 2)


def card_rows(gray, pct=96, min_frac=0.004, max_frac=0.25):
    """a MENU's cards and list rows: regions enclosed by strong borders (the top 4% of the gradient), rectangular (they
    fill 75%+ of their box), card-sized — kept only when they REPEAT (2+ with the same width at the same left edge: a
    list, a choice of cards), so a scene's random enclosed patches never count. Hades' boon list: three 899x158 rows,
    168 px apart. -> [(box, index, count)]"""
    from scipy import ndimage as ndi
    g = gray.astype(np.float32)
    mag = np.hypot(ndi.sobel(g, 0), ndi.sobel(g, 1))
    edges = ndi.binary_dilation(mag > np.percentile(mag, pct), iterations=2)
    lab, _ = ndi.label(~edges)
    H, W = gray.shape
    cands = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        if sl is None:
            continue
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if not (min_frac * W * H <= w * h <= max_frac * W * H) or w < 120 or h < 40:
            continue
        if (lab[sl] == i).sum() / (w * h) < 0.75:
            continue
        cands.append([sl[1].start, sl[0].start, sl[1].stop, sl[0].stop])
    rows = []
    used = set()
    for i, b in enumerate(cands):
        if i in used:
            continue
        # (every member is compared with THIS card and none is reused: a chain of near-matches once split one list in two)
        group = [j for j, c in enumerate(cands) if j not in used and abs(c[0] - b[0]) <= 12 and abs((c[2] - c[0]) - (b[2] - b[0])) <= 0.03 * (b[2] - b[0])]
        if len(group) >= 2:
            group.sort(key=lambda j: cands[j][1])
            for k, j in enumerate(group):
                used.add(j)
                rows.append((cands[j], k + 1, len(group)))
    return rows


def big_graphics(V, img, gray, boxes, thr=1.5, size=432, stride=216):
    """the BIG graphic pieces a 192 px window cannot hold (a title logo, a COUNTER / KO callout): graphic-lettering vs
    scene AND vs the quiet-HUD prompt on 432 px windows, a stricter bar; a hot run becomes a box only where no smaller
    piece already sits (a second scale merged into the small one swallowed the minimap: this one only adds)"""
    from scipy import ndimage as ndi
    q = ["bold stylised graphic text, a logo or a cut-out sticker printed over a picture",
         "interface graphics overlaid on a game screen: small text, numbers, icons, a map or bars",
         "a photo of a 3D game scene"]
    xs = list(range(0, 1920 - size + 1, stride))
    ys = list(range(0, 1080 - size + 1, stride))
    if xs[-1] != 1920 - size:
        xs.append(1920 - size)
    if ys[-1] != 1080 - size:
        ys.append(1080 - size)
    crops = [img.crop((x, y, x + size, y + size)) for y in ys for x in xs]
    L = logits(V, crops, q)
    heat = (L[:, 0] - np.maximum(L[:, 1], L[:, 2])).reshape(len(ys), len(xs))
    lab, n = ndi.label(heat > thr, structure=np.ones((3, 3)))
    found = []
    for k in range(1, n + 1):
        # the region's CORE: a title screen reads hot across a whole half (logo + menu); the logo is its peak
        core = (lab == k) & (heat >= 0.75 * heat[lab == k].max())
        cells = np.argwhere(core)
        y0, x0 = cells.min(axis=0)
        y1, x1 = cells.max(axis=0)
        box = tighten(gray, [xs[x0], ys[y0], xs[x1] + size, ys[y1] + size], pad=4)
        area = max(1, (box[2] - box[0]) * (box[3] - box[1]))
        covered = sum(max(0, min(box[2], b[2]) - max(box[0], b[0])) * max(0, min(box[3], b[3]) - max(box[1], b[1])) for b in boxes)
        if covered < 0.3 * area:
            found.append(box)
    return found


def merge(boxes, gap=22):
    """join boxes closer than gap (a text line's words, a block's lines)"""
    boxes = [list(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        out = []
        while boxes:
            b = boxes.pop()
            for o in boxes:
                if b[0] - gap < o[2] and o[0] - gap < b[2] and b[1] - gap < o[3] and o[1] - gap < b[3]:
                    o[0], o[1], o[2], o[3] = min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3])
                    changed = True
                    break
            else:
                out.append(b)
        boxes = out
    return boxes


def cmd_read(a):
    if not os.path.isfile(a.still):
        return emit("fail", f"read: no still at {a.still}", "point at a game screenshot")
    t0 = time.time()
    V = _vision()
    src = Image.open(a.still).convert("RGB")
    img = src.resize((1920, 1080), Image.LANCZOS)  # read at 1080p: every box is in the kit's design pixels
    gray = np.array(img.convert("L"))
    # (192 px windows find HUD pieces and cards; a title logo bigger than a window is found by big_graphics, a 432 px pass
    # that only ADDS where nothing sits — merged into the 192 px heat, a second scale once swallowed the minimap)
    boxes = heat_regions(V, img, gray, a.heat)
    boxes = merge(boxes, a.gap)
    # a box over a quarter of the frame is not a piece (a title screen reads hot almost everywhere): drop those BEFORE
    # the passes that only fill gaps, or one giant box hides the logo it sits on
    boxes = [b for b in boxes if (b[2] - b[0]) * (b[3] - b[1]) <= 0.25 * 1920 * 1080]
    boxes += edge_strips(V, img, gray, boxes, a.heat)
    big = [b for b in big_graphics(V, img, gray, boxes) if (b[2] - b[0]) * (b[3] - b[1]) <= 0.45 * 1920 * 1080]
    gl = logits(V, [img], [t for _, t in GENRES])[0]
    genre = a.genre or pick_genre(gl)  # (told, or read from the frame)
    boxes = [part for b in boxes for part in split_bands(gray, b)] + big
    big_set = {tuple(b) for b in big}
    # a menu's repeated cards / list rows (a screen that is nearly ALL interface reads as one hot block above)
    row_of = {}
    for b, k, n in card_rows(gray):
        area = (b[2] - b[0]) * (b[3] - b[1])
        covered = sum(max(0, min(b[2], o[2]) - max(b[0], o[0])) * max(0, min(b[3], o[3]) - max(b[1], o[1])) for o in boxes)
        if covered < 0.5 * area:
            boxes.append(b)
            row_of[tuple(b)] = (k, n)
    if not boxes:
        return emit("fail", "read: no interface-like blocks found", "the still may have no interface; try kit ui read on a gameplay still")
    cats = list(CATS)
    L = logits(V, [img.crop(b) for b in boxes], [CATS[c] for c in cats])
    out = []
    for b, row in zip(boxes, L):
        j = int(np.argmax(row[:-1]))
        margin = float(row[j] - row[-1])  # vs "a 3D game scene"
        if margin < a.margin:
            continue
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        wh = where(cx, cy)
        label = (fight_role(b) if genre == "fighting" else rpg_role(b) if genre == "rpg" else None) or role(cats[j], wh, b[2] - b[0], b[3] - b[1], genre)
        if tuple(b) in big_set:  # found only by the big-window pass: a title logo or a screen-filling callout
            label = "title logo / big callout"
        if tuple(b) in row_of:  # one of a menu's repeated cards
            label = f"card / list row {row_of[tuple(b)][0]} of {row_of[tuple(b)][1]}"
        out.append({"label": label, "looks_like": cats[j], "where": wh, "box_1080": b,
                    "size_1080": [b[2] - b[0], b[3] - b[1]], "confidence": round(margin, 2), "colours": colours(img, b)})
    if getattr(a, "find", None):  # what the user DESCRIBED, found where it is
        fb, fs = find_described(V, img, gray, a.find)
        if fb is None:
            print(f"read: nothing in the frame reads as '{a.find}' (best window {fs:.2f})", file=sys.stderr)
        else:
            fcx, fcy = (fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2
            out.append({"label": f"found: {a.find}", "looks_like": "described", "where": where(fcx, fcy), "box_1080": fb,
                        "size_1080": [fb[2] - fb[0], fb[3] - fb[1]], "confidence": fs, "colours": colours(img, fb)})
    out.sort(key=lambda e: -e["confidence"])
    # the WORDS: one OCR pass (RapidOCR, vetted 2026-10-14, local ONNX) — each piece gets the words inside it, and the
    # words sharpen its name (TENSION / BURST, a rarity, a 2-3 digit number top-centre = the round timer)
    lines = ocr_lines(img)
    for e in out:
        x0, y0, x1, y1 = e["box_1080"]
        inside = [ln for ln in lines if x0 - 4 <= ln["centre"][0] <= x1 + 4 and y0 - 4 <= ln["centre"][1] <= y1 + 4]
        if inside:
            e["words"] = [ln["text"] for ln in sorted(inside, key=lambda ln: (ln["centre"][1], ln["centre"][0]))]
            named = role_from_words(e["words"], e["where"], genre)
            rarity = re.search(r"(?<![\w-])(LEGENDARY|HEROIC|EPIC|RARE|UNCOMMON|COMMON|DUO|MYTHIC)(?![\w-])", " ".join(e["words"]).upper())
            if e["label"].startswith("card / list row") and rarity:
                e["label"] += f" ({rarity.group(1).lower()})"   # (a row keeps its place in the list and gains its rarity)
            elif named and e["label"].split(" ")[0] in GENERIC_FIRST:
                e["label"] = named                               # (words only rename a GENERIC piece: 'P1 ...' stays P1)
    out = out[: a.max]
    board = img.copy()
    d = ImageDraw.Draw(board)
    palette = [(255, 214, 64), (64, 220, 255), (255, 96, 160), (140, 255, 120), (200, 140, 255), (255, 160, 64)]
    for i, e in enumerate(out):
        c = palette[i % len(palette)]
        d.rectangle(e["box_1080"], outline=c, width=4)
        tag = f"{e['label']} {e['size_1080'][0]}x{e['size_1080'][1]}"
        tx, ty = e["box_1080"][0], max(0, e["box_1080"][1] - 30)
        d.rectangle([tx, ty, tx + 11 * len(tag) + 12, ty + 28], fill=(0, 0, 0))
        d.text((tx + 6, ty + 4), tag, fill=c, font=_font(20))
    out_dir = a.out or os.path.dirname(a.still)
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(a.still))[0]
    board_path = os.path.join(out_dir, f"{stem}.read.png")
    board.resize((960, 540), Image.LANCZOS).save(board_path)
    json_path = os.path.join(out_dir, f"{stem}.read.json")
    with open(json_path, "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump({"schema": 1, "still": a.still, "frame": list(src.size), "read_at": [1920, 1080], "genre": genre, "elements": out,
                   "candidates": len(boxes), "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, fh, indent=1)
    if a.crops:  # each piece as its own picture (at the still's own resolution): the input of trace / ink --from
        cdir = os.path.join(out_dir, f"{stem}_pieces")
        os.makedirs(cdir, exist_ok=True)
        sx, sy = src.size[0] / 1920, src.size[1] / 1080
        seen = {}
        for e in out:
            base = pascal(e["label"])
            seen[base] = seen.get(base, 0) + 1
            nm = base if seen[base] == 1 else f"{base}{seen[base]}"
            x0, y0, x1, y1 = e["box_1080"]
            src.crop((round(x0 * sx), round(y0 * sy), round(x1 * sx), round(y1 * sy))).save(os.path.join(cdir, f"{nm}.png"))
            e["crop"] = os.path.join(cdir, f"{nm}.png").replace(os.sep, "/")
        with open(json_path, "w", encoding="utf-8", newline=chr(10)) as fh:
            json.dump({"schema": 1, "still": a.still, "frame": list(src.size), "read_at": [1920, 1080], "genre": genre, "elements": out,
                       "candidates": len(boxes), "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, fh, indent=1)
    if a.draft:
        if not a.identity:
            return emit("fail", "read --draft needs --identity <name> (the look the draft starts in)", "lune run kit ui read <still> --draft <Screen> --identity <name>")
        dpath = os.path.join(a.ui, f"{a.draft}.json")
        if os.path.exists(dpath):
            return emit("fail", f"read: {dpath} exists; a draft never overwrites a screen", "pick a new --draft name")
        with open(dpath, "w", encoding="utf-8", newline=chr(10)) as fh:
            json.dump(draft_spec(a.draft, a.identity, out, a.still), fh, indent=1)
    names = "; ".join(f"{e['label']} ({e['looks_like']}) {e['where']} {e['box_1080']}" for e in out[:8])
    return emit("pass", f"read: {len(out)} interface piece(s) of {len(boxes)} block(s) in {os.path.basename(a.still)} ({genre}; {time.time() - t0:.0f}s): {names}",
                (f"lune run kit ui (the draft {a.draft} compiles with the reference's layout), then replace its placeholders" if a.draft
                 else f"LOOK at {board_path} (each piece boxed and named); exact pixels: kit ui measure; a starting screen: --draft <Screen> --identity <name>"),
                read=json_path, board=board_path)


def pascal(words):
    return "".join(w[:1].upper() + w[1:] for w in re.findall(r"[A-Za-z0-9]+", words)) or "Piece"


def place(box):
    """a box at 1080p -> (pos, anchor) tied to its NEAREST edge or the centre, the way a designer anchors a HUD piece
    (a corner piece stays in its corner on every screen shape)"""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ax = 0 if cx < 1920 * 0.36 else 1 if cx > 1920 * 0.64 else 0.5
    ay = 0 if cy < 1080 * 0.36 else 1 if cy > 1080 * 0.64 else 0.5

    def axis(a, lo, hi, c, full):
        if a == 0:
            return round(lo)
        if a == 1:
            return f"100%-{round(full - hi)}" if full - hi else "100%"
        off = round(c - full / 2)
        return "50%" if off == 0 else f"50%+{off}" if off > 0 else f"50%-{-off}"

    names = {(0, 0): "topleft", (0.5, 0): "top", (1, 0): "topright", (0, 0.5): "left", (0.5, 0.5): "center",
             (1, 0.5): "right", (0, 1): "bottomleft", (0.5, 1): "bottom", (1, 1): "bottomright"}
    return [axis(ax, x0, x1, cx, 1920), axis(ay, y0, y1, cy, 1080)], names[(ax, ay)]


def ocr_lines(img):
    """every line of text in the frame (1080p coordinates): RapidOCR's bundled PP-OCRv6 models, local; [] when the
    package is missing (read works without it)"""
    try:
        import contextlib
        import logging
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            from rapidocr import RapidOCR  # noqa: PLC0415
            logging.getLogger("RapidOCR").setLevel(logging.ERROR)
            if "ocr" not in _OCR:
                _OCR["ocr"] = RapidOCR()
            # (no orientation guess: HUD text is never upside down, and the classifier read a timer's '99' as '66')
            r = _OCR["ocr"](np.array(img), use_cls=False)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for box, txt, sc in zip(r.boxes if r.boxes is not None else [], r.txts or [], r.scores or []):
        if float(sc) < 0.6 or not str(txt).strip():
            continue
        b = np.array(box, dtype=float)
        out.append({"text": str(txt).strip(), "score": round(float(sc), 2), "centre": [round(float(b[:, 0].mean())), round(float(b[:, 1].mean()))],
                    "box_1080": [round(float(b[:, 0].min())), round(float(b[:, 1].min())), round(float(b[:, 0].max())), round(float(b[:, 1].max()))]})
    return out


GENERIC_FIRST = {"interface", "label", "icon", "bar", "graphic", "panel", "logo", "a"}
# (order matters: the first match names the piece — HP before HIT so 'HIT POINTS' is health, COMBO before the gauge words;
# a word is bounded by anything but a letter, digit or hyphen, so 'EX-MACHINA' is not the EX gauge)
_W = r"(?<![\w-])({})(?![\w-])"
WORD_ROLES = [(_W.format(r"WEAK|CRITICAL|RESIST|TECHNICAL|NULL|REPEL|MISS"), "hit callout (WEAK / CRITICAL)"),
              (_W.format(r"HP|HIT POINTS|HEALTH|VITALITY|LIFE"), "health"),
              (_W.format(r"COUNTER|COMBO|HITS?|CHAIN"), "combo counter / callout"),
              (_W.format(r"TENSION|BURST|SUPER|DRIVE|EX"), "super / tension gauge"),
              (_W.format(r"LEGENDARY|HEROIC|EPIC|RARE|UNCOMMON|COMMON|DUO|MYTHIC"), "card with rarity"),
              (_W.format(r"AMMO|MAG|RELOAD"), "weapon / ammo block"),
              (_W.format(r"VICTORY|DEFEAT|K\.?O\.?|PERFECT|ROUND|FIGHT"), "round call / result"),
              (_W.format(r"MAP|MINIMAP|OBJECTIVE|QUEST"), "objective / location text")]
_OCR = {}


def role_from_words(words, where_, genre=""):
    """a piece's job from the WORDS in it (the reference says what it is); None when the words do not decide — the
    battle callouts (WEAK, CRITICAL, MISS...) only in a told rpg: elsewhere 'CRITICAL HEALTH' is health, 'MISS' a word"""
    text = " ".join(words).upper()
    for pat, name in WORD_ROLES:
        if name.startswith("hit callout") and genre != "rpg":
            continue
        if re.search(pat, text):
            return name
    if where_ == "top-centre" and re.fullmatch(r"\d{2,3}\.?", text.strip()):
        return "round timer"
    return None


def draft_spec(name, identity, elements, still):
    """a STARTING screen spec from a read reference: every piece found becomes a named placeholder at its measured place
    and size (panels tinted with the piece's own main colour, text pieces as labels) — the layout is the reference's,
    the look is still to make (pieces by route: ink, letter, render, spin...)"""
    kids, seen = [], {}
    for i, e in enumerate(elements):
        base = pascal(e["label"])
        seen[base] = seen.get(base, 0) + 1
        nm = base if seen[base] == 1 else f"{base}{seen[base]}"
        pos, anchor = place(e["box_1080"])
        w, h = e["size_1080"]
        if e["looks_like"] in ("text", "digits"):
            kids.append({"type": "label", "name": nm, "text": " ".join(e.get("words") or [e["label"].upper()])[:60], "role": "body", "size": [w, h], "pos": pos,
                         "anchor": anchor, "z": 2 + i})
        else:
            col = (e.get("colours") or [{"hex": "#808080"}])[0]["hex"]
            kids.append({"type": "panel", "name": nm, "size": [w, h], "pos": pos, "anchor": anchor, "color": col,
                         "transparency": 0.35, "z": 2 + i})
    # (insets core: a top-left minimap would sit under Roblox's own top bar; phone / tablet scale like every kit HUD)
    return {"name": name, "identity": identity, "kind": "hud", "enabled": False, "insets": "core", "scale": {"phone": 0.55, "tablet": 0.8},
            "about": f"DRAFT from kit ui read {os.path.basename(still)}: the reference's layout, placeholders named by their job; "
                     "replace each placeholder with a real piece",
            "root": {"type": "panel", "name": "Hud", "size": ["100%", "100%"], "children": kids}}


def _font(size):
    try:
        from PIL import ImageFont
        p = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "fonts", "robotocondensed", "RobotoCondensed[wght].ttf")
        return ImageFont.truetype(p, size)
    except Exception:  # noqa: BLE001
        from PIL import ImageFont
        return ImageFont.load_default()


def edge_bands(img):
    """where a HUD lives: the four edge bands and the corners of a 16:9 frame"""
    w, h = img.size
    bw, bh = int(w * 0.3), int(h * 0.3)
    return [img.crop((0, 0, bw, bh)), img.crop((w - bw, 0, w, bh)), img.crop((0, h - bh, bw, h)), img.crop((w - bw, h - bh, w, h)),
            img.crop((int(w * 0.3), 0, int(w * 0.7), int(h * 0.18))), img.crop((int(w * 0.3), int(h * 0.82), int(w * 0.7), h))]


COLLAGE_Q = ["two different screenshots placed side by side in one picture", "one single video game screen with a menu panel or frame"]


def is_half(folder, f):
    """a collage's half (<name>_L / _R) whose parent collage is beside it: never listed, never re-cut"""
    m = re.match(r"(.+)_[LR](\.[A-Za-z]+)$", f)
    return bool(m and os.path.isfile(os.path.join(folder, m.group(1) + m.group(2))))


def asked_genre(want):
    """the genre a ranking request names, if any ('a fighting game HUD' -> fighting); whole words only ('a gunfight
    shooter', 'a dogfight flight sim' are not fighting games), a versus SCREEN is"""
    if re.search(r"\bfight(ing|er|ers)?\b|\bversus\b|\bvs\.? screen|\bbrawl(er|ers|ing)?\b|street fighter|tekken|guilty gear", want, re.I):
        return "fighting"
    if re.search(r"\brac(e|er|ing)\b|\bspeedometer\b|\bdrift(ing)?\b|need for speed|forza|gran turismo", want, re.I):
        return "racing"
    if re.search(r"\bshoot(er|ing)?\b|\bfps\b|\bguns?\b|\bgunfight|\bammo\b|call of duty|battlefield", want, re.I):
        return "shooter"
    return None


def collage_seam(img, jump=12, share=0.8):
    """a collage (two screens pasted SIDE BY SIDE) has a hard vertical seam crossing the whole picture between 15% and
    85% of its width; a game screen almost never does (GGST: collages jump on 0.88-0.96 of the rows there, fight screens
    0.47-0.49). Horizontal lines are NOT checked: full-width HUD bars, letterboxes and floors have them. -> x (0..1) or None"""
    g = np.asarray(img.convert("L").resize((480, 270)), dtype=np.float32)
    d = np.abs(g[:, 2:] - g[:, :-2])  # the jump across two pixels (a seam blurs over one when the picture is shrunk)
    frac = (d > jump).mean(axis=0)
    lo, hi = int(frac.size * 0.15), int(frac.size * 0.85)
    k = int(np.argmax(frac[lo:hi])) + lo
    return round(k / frac.size, 3) if frac[k] >= share else None


def cmd_rank(a):
    folder = a.still
    if not os.path.isdir(folder):
        return emit("fail", f"rank: no folder {folder}", "lune run kit ui refs <id> \"<game>\" \"<words>\" first")
    t0 = time.time()
    V = _vision()
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
                   and not f.startswith(("contact", "ranked")) and ".read." not in f
                   and not is_half(folder, f))  # (a collage's halves: cut again from it below)
    neg = ["promotional key art or a poster with a logo", "a cinematic video game screenshot with no interface, text or icons",
           "a single icon, logo or emblem on a plain background", "a photograph of a person or a product"]
    want = a.what
    # wikis and stores hand back collages (two screens side by side) and menu / lobby pages that SigLIP rates as
    # "a game screen with bars": name them as negatives, the menu one only when a menu is not what was asked for
    neg.append("a collage of two or more different screenshots side by side")
    if not re.search(r"menu|lobby|store|shop|news|title|select|inventory|pause|settings", want, re.I):
        neg.append("a game menu, lobby, store or news page")
    edge_q = "part of a video game interface: numbers, text, icons, bars or a map overlaid on the game"
    edge_neg = "part of a 3D video game scene with no interface, text or icons"
    asked = asked_genre(want)
    def score_of(img):
        L = logits(V, [img], [want] + neg)[0]
        whole = float(L[0] - L[1:].max())
        bands = edge_bands(img)
        E = logits(V, bands, [edge_q, edge_neg])
        ui = float(np.sort(E[:, 0] - E[:, 1])[-2:].mean())  # the two most interface-like bands
        seam = collage_seam(img)
        if seam is not None:
            # a straight full-height edge is a collage only if the picture also READS as two screens: Hades' framed side
            # panels have the same edge (single screens scored -0.73..-1.95 here, the GGST collages +0.40 / +0.59)
            C = logits(V, [img], COLLAGE_Q)[0]
            if float(C[0] - C[1]) <= 0:
                seam = None
        score = whole + 0.6 * ui - (3.0 if seam is not None else 0.0)  # (a collage is two half-references at best)
        if img.width < 480 or img.height < 270:
            # too small to MEASURE from (wikis hand back item renders 81..232 px that match the words best: Hollow
            # Knight's mask and soul-vessel art ranked above every real HUD screenshot)
            score -= 3.0
        genre = None
        if asked:  # the request names a genre: a candidate whose frame reads as another genre loses 2
            gl = logits(V, [img], [t for _, t in GENRES])[0]
            genre = pick_genre(gl)
            if genre not in (asked, "other"):  # (an AMBIGUOUS frame is not the wrong genre: only a confident other genre pays)
                score -= 2.0
        return {"score": round(score, 2), "whole": round(whole, 2), "interface": round(ui, 2), "collage": seam, "genre": genre,
                "size": list(img.size)}

    rows = []
    for f in files:
        try:
            img = Image.open(os.path.join(folder, f)).convert("RGB")
        except Exception:  # noqa: BLE001
            continue
        r = {"file": f, **score_of(img)}
        rows.append(r)
        if r["collage"] is not None and not is_half(folder, f):
            # a collage is cut at its seam: each half is a candidate of its own (the GGST lobby collage held a clean
            # menu), saved beside it as <name>_L / <name>_R so keep can promote it
            x = round(r["collage"] * img.width)
            stem, ext = os.path.splitext(f)
            for tag, half in (("L", img.crop((0, 0, x, img.height))), ("R", img.crop((x, 0, img.width, img.height)))):
                if half.width < 0.2 * img.width:
                    continue
                hf = f"{stem}_{tag}{ext}"
                half.save(os.path.join(folder, hf))
                rows.append({"file": hf, "half_of": f, **score_of(half)})
    rows.sort(key=lambda r: -r["score"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    json.dump({"schema": 1, "what": want, "ranked": rows, "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
              open(os.path.join(folder, "ranks.json"), "w", encoding="utf-8", newline="\n"), indent=1)
    top = rows[: a.top]
    cols, w, h = 3, 400, 225
    sheet = Image.new("RGB", (cols * w, h * max(1, (len(top) + cols - 1) // cols)), (0, 0, 0))
    d = ImageDraw.Draw(sheet)
    for j, r in enumerate(top):
        im = Image.open(os.path.join(folder, r["file"])).convert("RGB")
        im.thumbnail((w, h))
        sheet.paste(im, ((j % cols) * w, (j // cols) * h))
        tag = f"#{r['rank']} {r['file']}  score {r['score']}  ui {r['interface']}" + (f"  {r['genre']}" if r.get("genre") else "") + ("  COLLAGE" if r.get("collage") is not None else "")
        d.rectangle([(j % cols) * w, (j // cols) * h, (j % cols) * w + 7 * len(tag) + 8, (j // cols) * h + 18], fill=(0, 0, 0))
        d.text(((j % cols) * w + 4, (j // cols) * h + 3), tag, fill=(255, 255, 0))
    sheet_path = os.path.join(folder, "ranked.png")
    sheet.save(sheet_path)
    kept = []
    # (a store page can hold only marketing renders: every candidate scored below 0 and showed no interface — say so,
    # and keep none of them as references)
    no_ui = bool(rows) and rows[0]["score"] < 0 and max(r["interface"] for r in rows) < 0
    if a.keep and a.identity and not no_ui:
        dst = os.path.join(a.refs, a.identity)
        os.makedirs(dst, exist_ok=True)
        # (named by the candidate itself, not its rank: a second --keep overwrote <id>_ranked_01 and wrote its REFS.md
        # line twice — audit 2026-10-16; an identical file already kept is skipped)
        import hashlib
        have = set()
        for f in os.listdir(dst):
            fp = os.path.join(dst, f)
            if os.path.isfile(fp) and f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                with open(fp, "rb") as fh:
                    have.add(hashlib.sha256(fh.read()).hexdigest())
        lines = []
        for r in rows[: a.keep]:
            src = os.path.join(folder, r["file"])
            with open(src, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            if digest in have:
                continue
            stem = re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(os.path.basename(r["file"]))[0])[:40]
            name = f"{a.identity}_ranked_{stem}{os.path.splitext(r['file'])[1]}"
            shutil.copyfile(src, os.path.join(dst, name))
            have.add(digest)
            kept.append(name)
            lines.append(f"- {name} — ranked #{r['rank']} for \"{want}\" by kit ui read rank (SigLIP); from {folder}")
        if lines:
            with open(os.path.join(dst, "REFS.md"), "a", encoding="utf-8", newline="\n") as fh:
                fh.write("\n" + "\n".join(lines) + "\n")
    best = ", ".join(f"#{r['rank']} {r['file']} ({r['score']})" for r in rows[:4])
    if no_ui:
        return emit("pass", f"rank: {len(rows)} candidate(s) for \"{want}\" — NONE shows the interface (best score {rows[0]['score']}, "
                    f"every interface score below 0: marketing renders); best {best}",
                    "gather gameplay stills instead: kit ui refs <id> \"<game>\" \"<words>\" --wiki <fandom> (or --drop a folder of your own screenshots)",
                    ranked=[r["file"] for r in rows], no_interface=True)
    return emit("pass", f"rank: {len(rows)} candidate(s) for \"{want}\" ({time.time() - t0:.0f}s): best {best}" + (f"; kept {len(kept)}" if kept else ""),
                f"LOOK at {sheet_path} (best first); then read the best: lune run kit ui read <still>", ranked=[r["file"] for r in rows])


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    argv = sys.argv[1:]
    ap = argparse.ArgumentParser()
    if argv and argv[0] == "motion":  # MOTION understanding: when and where a reference clip moves (kit/ui/motion.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import motion  # noqa: PLC0415
        ap.add_argument("cmd")
        ap.add_argument("clip")
        ap.add_argument("--fps", type=float, default=None, help="frames per second when the clip does not say (a GIF without frame times)")
        ap.add_argument("--pieces", default=None, help="a <still>.read.json of one of its frames: the beats PER PIECE (which piece moved when)")
        ap.add_argument("--out", default=None)
        ap.add_argument("--ui", default="assets/ui")  # (passed by the CLI; unused here)
        return motion.cmd_motion(ap.parse_args(argv))
    if argv and argv[0] == "type":  # TYPE understanding: the lettering in a crop measured (kit/ui/typemeasure.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import typemeasure  # noqa: PLC0415
        ap.add_argument("cmd")
        ap.add_argument("crop")
        ap.add_argument("--ui", default="assets/ui")  # (passed by the CLI; unused here)
        return typemeasure.cmd_type(ap.parse_args(argv))
    if argv and argv[0] == "prior":  # LAYOUT KNOWLEDGE across games of one genre (kit/ui/priors.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import priors  # noqa: PLC0415
        ap.add_argument("cmd")
        ap.add_argument("genre")
        ap.add_argument("--refs", default=None, help="default: <ui>/refs (the active game's)")
        ap.add_argument("--out", default=None, help="default: <ui>/priors")
        ap.add_argument("--draft", default=None, help="also write assets/ui/<Draft>.json laid out by the genre's measured layout")
        ap.add_argument("--identity", default=None)
        ap.add_argument("--ui", default="assets/ui")
        return priors.cmd_prior(ap.parse_args(argv))
    if argv and argv[0] == "rank":
        ap.add_argument("cmd")
        ap.add_argument("still")
        ap.add_argument("what")
        ap.add_argument("--top", type=int, default=9)
        ap.add_argument("--keep", type=int, default=0)
        ap.add_argument("--identity", default=None)
        ap.add_argument("--refs", default="assets/ui/refs")
        a = ap.parse_args(argv)
        return cmd_rank(a)
    ap.add_argument("still")
    ap.add_argument("--margin", type=float, default=0.0, help="how far a piece's best category must beat 'a 3D game scene' (SigLIP logits)")
    ap.add_argument("--gap", type=int, default=22, help="join blocks closer than this (px at 1080p)")
    ap.add_argument("--heat", type=float, default=0.8, help="interface-vs-scene score a window needs (SigLIP logits)")
    ap.add_argument("--max", type=int, default=10)
    ap.add_argument("--out", default=None)
    ap.add_argument("--draft", default=None, help="also write assets/ui/<Draft>.json: a starting screen with the reference's layout")
    ap.add_argument("--identity", default=None, help="the identity a --draft starts in")
    ap.add_argument("--find", default=None, help="also find what you DESCRIBE ('a round soul vessel and a row of mask icons') and box it")
    ap.add_argument("--crops", action="store_true", help="save each piece as its own picture (<still>_pieces/<Role>.png): trace / ink --from it")
    ap.add_argument("--genre", default=None, choices=GENRE_NAMES,
                    help="the still's genre when you KNOW it (a turn-based rpg battle is not told from the frame)")
    ap.add_argument("--ui", default="assets/ui")
    a = ap.parse_args(argv)
    return cmd_read(a)


if __name__ == "__main__":
    raise SystemExit(main())
