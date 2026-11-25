"""lookpages.py - a world's look, ONE PAGE PER STATION, large and labelled (kit world look / kit world studio).

    python kit/world/lookpages.py <look_dir> <Name> [--refs DIR] [--studio DIR] [--studio-why "<words>"]
                                  [--out DIR] [--pane 1920x1080]

The owner on an unlabelled frame (GothicCourtyard, 2026-11-11): "I don't know what I'm exactly looking at"; and the
sheet a session judged from showed each station 520 px wide beside references it was never paired with. So every
station (kit/world/look_blender.py: stations.json) gets its own page of full-size panes, one above the other at the
same framing (16:9, the frame filled - the 3D lane's rule for a wide pair: the reference on top):
    the REFERENCE still it is judged beside     (the look we aim for; what the still shows, in plain words)
    OURS in Blender                             (the labelled shot; Blender's light is a stand-in)
    OURS in Roblox Studio  (with --studio)      (Roblox's own light; plain parts until meshes are uploaded) - or a
                                                pane that says NOT CAPTURED and why
The header names the station and what it shows (the labels the camera sees).

Which still goes with which station: <refs>/stations.json (optional)
    { "never": ["a_still_never_shown.jpg"],
      "stations": { "eye_1": { "ref": "source_2_plaza.jpg", "ref_shows": "behind the hunter, the spires ahead",
                               "ref_crop": [0, 0, 1, 0.9], "title": "...", "shows": "..." },
                    "view_inside": { "ref": "none", "ref_shows": "the look source has no interior frame" } } }
ref_crop takes a part of the still first (fractions left, top, right, bottom: a still's own HUD, or a part of it that
must not be shown). "ref": "none" says the stills hold nothing for this view, in words, instead of a false pair.
A station it does not name takes the next unused still in name order and its pane says so ("paired by order"); with
no such file only the first four stills are taken (a still named to sort last stays off every page, as on the sheet).
Prints one JSON line: {status, summary, next_action, pages, folder, look}.
"""

import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

BG, FG, DIM = (14, 15, 20), (240, 240, 245), (150, 156, 170)
TAGS = {"ref": (94, 200, 255), "blender": (255, 196, 110), "studio": (120, 226, 150)}
BANDS = {"ref": (22, 34, 46), "blender": (44, 36, 22), "studio": (20, 40, 28)}
FONTS = ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "DejaVuSans-Bold.ttf")
FONTS_PLAIN = ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf")
STILLS = (".png", ".jpg", ".jpeg", ".webp")
FIRST_STILLS = 4  # with no pairing file: the sheet's rule (kit world look showed the first four stills)
# what a Studio pane is, said on the pane: nothing is uploaded, so the plain blockout stands where each mesh will
STUDIO_SHOWS = "Roblox's own light on the plain blockout (no mesh is uploaded: no carving, no window openings)"
HOW = ("Read it top to bottom, the same frame each time: the reference (the look we aim for), ours in Blender "
       "(its light is a stand-in), ours in Roblox Studio (Roblox's own light).")
HOW_PAIR = "Read it top to bottom, the same frame each time: the reference (the look we aim for), then ours in Blender."


def font(size, bold=True):
    for f in (FONTS if bold else FONTS_PLAIN):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fit_text(draw, text, max_w, size, min_size=16, bold=True):
    """the text at the largest size from `size` down to `min_size` that fits max_w; still too long, it is cut with
    an ellipsis -> (text, font)"""
    s = size
    while s > min_size and draw.textlength(text, font=font(s, bold)) > max_w:
        s -= 2
    f = font(s, bold)
    if draw.textlength(text, font=f) > max_w:
        while len(text) > 4 and draw.textlength(text + "...", font=f) > max_w:
            text = text[:-1]
        text = text.rstrip(" ,;:") + "..."
    return text, f


def wrap(draw, text, f, max_w, max_lines):
    """the text on at most max_lines lines of max_w; what does not fit ends in an ellipsis -> [line]"""
    lines, cur = [], ""
    words = text.split()
    for i, word in enumerate(words):
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=f) <= max_w:
            cur = trial
            continue
        if len(lines) == max_lines - 1:
            rest = (cur + " " + " ".join(words[i:])).strip()
            while len(rest) > 4 and draw.textlength(rest + "...", font=f) > max_w:
                rest = rest[:-1]
            lines.append(rest.rstrip(" ,;:") + "...")
            return lines
        if cur:
            lines.append(cur)
        cur = word
    if cur:
        lines.append(cur)
    return lines


def good_crop(crop):
    """a still's crop as the pairing file may give it: four numbers, fractions left, top, right, bottom of a real
    part of the picture -> [l, t, r, b], or None for anything else (a hand-written file: a typo there must cost one
    crop, never the whole page set)"""
    if not isinstance(crop, (list, tuple)) or len(crop) != 4:
        return None
    try:
        l, t, r, b = [min(1.0, max(0.0, float(v))) for v in crop]
    except (TypeError, ValueError):
        return None
    return [l, t, r, b] if r - l > 0.02 and b - t > 0.02 else None


def cover(img, w, h, crop=None):
    """the picture filling a w x h pane (centre crop, no letterbox: the same framing in every pane); `crop` first
    takes a part of it (fractions l, t, r, b)"""
    img = img.convert("RGB")
    crop = good_crop(crop)
    if crop:
        iw, ih = img.size
        l, t, r, b = crop
        box = (int(l * iw), int(t * ih), int(r * iw), int(b * ih))
        if box[2] - box[0] >= 1 and box[3] - box[1] >= 1:  # (a 1 x 1 still has no part to take)
            img = img.crop(box)
    s = max(w / img.width, h / img.height)
    img = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
    x0, y0 = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x0, y0, x0 + w, y0 + h))


def list_stills(refs_dir):
    if not refs_dir or not os.path.isdir(refs_dir):
        return []
    return sorted(f for f in os.listdir(refs_dir) if f.lower().endswith(STILLS))


def load_pairing(refs_dir):
    """<refs>/stations.json -> (the stations' own entries, the stills never shown - their names in lower case: a
    Windows folder does not tell Z.JPG from z.jpg - and whether the file exists); the never set is None when the
    file is there and cannot be read"""
    named, never, has_file, _ = read_pairing(refs_dir)
    return named, never, has_file


def read_pairing(refs_dir):
    """the same, with what is wrong with the file in words (None: nothing). A file that cannot be read pairs nothing
    by name AND shows no still at all: its "never" list cannot be read either, and a still it meant to keep off the
    pages must not get onto one through a typo."""
    path = os.path.join(refs_dir or "", "stations.json")
    if not refs_dir or not os.path.isfile(path):
        return {}, set(), False, None
    try:
        with open(path, encoding="utf-8-sig") as fh:
            spec = json.load(fh)
        if not isinstance(spec, dict):
            raise ValueError('it must be an object: { "never": [...], "stations": { ... } }')
    except (OSError, ValueError) as exc:
        return {}, None, True, f"{path.replace(os.sep, '/')} cannot be read ({exc})"
    named = spec.get("stations") if isinstance(spec.get("stations"), dict) else {}
    never = spec.get("never")
    return named, {str(n).lower() for n in (never if isinstance(never, list) else [])}, True, None


def pair_refs(station_names, refs_dir):
    """which reference still each station is judged beside -> {station: {"file", "path", "shows", "crop", "how"}}
    how: "named" (the pairing file chose it), "order" (the next unused still in name order: the pane says so),
    "none" (the world has no still to show)."""
    named, never, has_file = load_pairing(refs_dir)
    if never is None:  # (the pairing file is there and cannot be read: no still is safe to show - read_pairing)
        return {name: {"file": None, "path": None, "shows": "", "crop": None, "how": "none"} for name in station_names}
    stills = [f for f in list_stills(refs_dir) if f.lower() not in never]
    pool = stills if has_file else stills[:FIRST_STILLS]
    out, used = {}, set()
    for name in station_names:
        e = named.get(name) if isinstance(named.get(name), dict) else {}
        f = e.get("ref")
        if f is False or (isinstance(f, str) and f.lower() == "none"):
            # the world's stills hold nothing this view can be judged beside (an interior, a look source of streets):
            # said in words - a still that shows something else beside it would be a false pair
            out[name] = {"file": None, "path": None, "shows": str(e.get("ref_shows") or ""), "crop": None, "how": "none"}
        elif isinstance(f, str) and f and f.lower() not in never and os.path.isfile(os.path.join(refs_dir, f)):
            out[name] = {"file": f, "path": os.path.join(refs_dir, f), "shows": str(e.get("ref_shows") or ""),
                         "crop": good_crop(e.get("ref_crop")), "how": "named"}
            used.add(f)
    k = 0
    for name in station_names:
        if name in out:
            continue
        free = [f for f in pool if f not in used] or pool
        if not free:
            out[name] = {"file": None, "path": None, "shows": "", "crop": None, "how": "none"}
            continue
        if free is pool:  # (more stations than stills: the stills go round again)
            f = pool[k % len(pool)]
            k += 1
        else:
            f = free[0]
        used.add(f)
        out[name] = {"file": f, "path": os.path.join(refs_dir, f), "shows": "", "crop": None, "how": "order"}
    return out


def station_words(station, look_dir, named):
    """a station's title and what it shows, in plain words: the pairing file's own words win; else the renderer's
    (stations.json) and the labels its camera sees (<station>.labels.json) -> (title, shows, in_view)"""
    e = named.get(station["name"]) if isinstance(named.get(station["name"]), dict) else {}
    title = str(e.get("title") or station.get("title") or station["name"])
    shows = str(e.get("shows") or station.get("about") or "")
    in_view = []
    lp = os.path.join(look_dir, station["name"] + ".labels.json")
    if os.path.isfile(lp):
        with open(lp, encoding="utf-8") as fh:
            for lb in json.load(fh).get("labels", []):
                if lb.get("seen") and lb.get("text") and lb["text"] not in in_view:
                    in_view.append(lb["text"])
    return title, shows, in_view


def placeholder(w, h, headline, lines, tag):
    """a pane with no picture: says so in words (never a blank or a stand-in picture)"""
    im = Image.new("RGB", (w, h), (24, 26, 33))
    d = ImageDraw.Draw(im)
    for x in range(-h, w, 64):  # (hatched: at a glance, not a dark render)
        d.line([(x, h), (x + h, 0)], fill=(31, 34, 43), width=3)
    head, f = fit_text(d, headline, w - 200, max(40, w // 22))
    d.text((w / 2, h * 0.36), head, font=f, fill=TAGS[tag], anchor="mm")
    y = h * 0.36 + f.size * 1.5
    fb = font(max(22, w // 60), bold=False)
    for line in lines:
        for row in wrap(d, line, fb, w - 240, 3):
            d.text((w / 2, y), row, font=fb, fill=FG, anchor="mm")
            y += fb.size * 1.45
        y += fb.size * 0.4
    return im


def caption(d, x, y, w, band_h, kind, tag_text, text):
    d.rectangle([x, y, x + w, y + band_h], fill=BANDS[kind])
    ft = font(int(band_h * 0.42))
    tw = d.textlength(tag_text, font=ft)
    d.rounded_rectangle([x + 14, y + band_h * 0.18, x + 14 + tw + 28, y + band_h * 0.82], radius=8, fill=TAGS[kind])
    d.text((x + 28, y + band_h / 2), tag_text, font=ft, fill=(10, 12, 16), anchor="lm")
    body, fb = fit_text(d, text, w - (tw + 28 + 14 + 22) - 18, int(band_h * 0.42), min_size=18)
    d.text((x + 14 + tw + 28 + 22, y + band_h / 2), body, font=fb, fill=FG, anchor="lm")


def page(world, k, n, station, words, ref, blender_path, studio, pane, out_path):
    """one station's page -> its size. studio: None (a pair) | {"path": <png or None>, "why": "...", "note": "..."}"""
    pw, ph = pane
    M, HEAD, BAND, GAP, FOOT = 24, 196, 68, 18, 54
    panes = 2 + (1 if studio is not None else 0)
    W = pw + 2 * M
    H = HEAD + panes * (BAND + ph + GAP) + FOOT
    sheet = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(sheet)
    title, shows, in_view = words
    head, f1 = fit_text(d, f"{world}  -  station {k} of {n}: {title}", W - 2 * M, 54, min_size=30)
    d.text((M, 20), head, font=f1, fill=FG)
    f2 = font(30, bold=False)
    y = 20 + f1.size + 18
    line2 = (shows[:1].upper() + shows[1:]) if shows else station["name"]
    for row in wrap(d, line2, f2, W - 2 * M, 1):
        d.text((M, y), row, font=f2, fill=FG)
    y += f2.size + 12
    seen = "In view: " + "; ".join(in_view) if in_view else "No labels in this view (name what it shows: the blueprint's \"labels\")."
    for row in wrap(d, seen, f2, W - 2 * M, 1):
        d.text((M, y), row, font=f2, fill=(255, 214, 140))
    y = HEAD
    # the reference
    if ref.get("path"):
        said = ref.get("shows") or ""
        if ref["how"] == "order":
            text = f"{ref['file']} - paired by order, not chosen for this view (name its still in the refs folder's stations.json)"
        else:
            text = (said + f"  ({ref['file']})") if said else ref["file"]
        caption(d, M, y, pw, BAND, "ref", "REFERENCE", text)
        with Image.open(ref["path"]) as im:
            sheet.paste(cover(im, pw, ph, ref.get("crop")), (M, y + BAND))
    elif ref.get("shows"):  # (the pairing file says this view has no still, and why)
        caption(d, M, y, pw, BAND, "ref", "REFERENCE", "none for this view")
        sheet.paste(placeholder(pw, ph, "NO REFERENCE STILL FOR THIS VIEW", [
            "Why: " + ref["shows"],
            "Until it has one, this view is judged on its own: find a real frame for it, or drop the view."], "ref"),
            (M, y + BAND))
    elif ref.get("problem"):  # (the pairing file cannot be read: no still is shown until it can)
        caption(d, M, y, pw, BAND, "ref", "REFERENCE", "none shown: the pairing file cannot be read")
        sheet.paste(placeholder(pw, ph, "NO REFERENCE STILL SHOWN", [
            "Why: " + ref["problem"],
            "It also says which stills must never be shown, so none is shown until it reads again."], "ref"),
            (M, y + BAND))
    else:
        caption(d, M, y, pw, BAND, "ref", "REFERENCE", "none: this world has no reference still to show")
        sheet.paste(placeholder(pw, ph, "NO REFERENCE STILL", [
            "Put the look source's real frames in the world's refs folder, then: lune run kit world refs " + world,
            "Words make generic maps: a world is judged beside its references."], "ref"), (M, y + BAND))
    y += BAND + ph + GAP
    # ours in Blender (the labelled shot)
    caption(d, M, y, pw, BAND, "blender", "OURS in Blender",
            "the same view, labelled - Blender's light is a stand-in for Roblox's; real meshes shown")
    if blender_path and os.path.isfile(blender_path):
        with Image.open(blender_path) as im:
            sheet.paste(cover(im, pw, ph), (M, y + BAND))
    else:
        sheet.paste(placeholder(pw, ph, "NOT RENDERED", ["lune run kit world look " + world], "blender"), (M, y + BAND))
    y += BAND + ph + GAP
    # ours in Roblox Studio
    if studio is not None:
        if studio.get("path") and os.path.isfile(studio["path"]):
            caption(d, M, y, pw, BAND, "studio", "OURS in Roblox Studio",
                    studio.get("note") or STUDIO_SHOWS)
            with Image.open(studio["path"]) as im:
                sheet.paste(cover(im, pw, ph), (M, y + BAND))
        else:
            caption(d, M, y, pw, BAND, "studio", "OURS in Roblox Studio", "NOT CAPTURED")
            sheet.paste(placeholder(pw, ph, "NOT CAPTURED IN ROBLOX STUDIO", [
                "Why: " + (studio.get("why") or "no capture was made"),
                "To capture: open the kit's scratch place in Studio, then lune run kit world studio " + world + " --capture"],
                "studio"), (M, y + BAND))
        y += BAND + ph + GAP
    foot, ff = fit_text(d, HOW if studio is not None else HOW_PAIR, W - 2 * M, 26, min_size=16, bold=False)
    d.text((M, y + 6), foot, font=ff, fill=DIM)
    sheet.save(out_path)
    return sheet.size


def look_line(folder, pages, pane, studio, captured=0):
    """the one line a world build ends with: where the pictures are and what is in them"""
    folder = folder.replace(os.sep, "/").rstrip("/") + "/"
    stack = "its reference still, ours in Blender (labelled)"
    if studio:
        stack += f", ours in Roblox Studio ({captured} of {len(pages)} captured)"
    names = ", ".join(os.path.basename(p) for p in pages[:3]) + (f" ... (+{len(pages) - 3})" if len(pages) > 3 else "")
    return (f"LOOK: {folder} - {len(pages)} station page(s), each {pane[0]} x {pane[1]} panes one above the other: "
            f"{stack}; open every one at full size ({names})")


def build(look_dir, name, refs_dir=None, studio_dir=None, studio_why=None, out_dir=None, pane=(1920, 1080)):
    sp = os.path.join(look_dir, "stations.json")
    if not os.path.isfile(sp):
        return {"status": "fail", "summary": f"no stations in {look_dir} (stations.json)",
                "next_action": f"render them: lune run kit world look {name}"}
    with open(sp, encoding="utf-8") as fh:
        stations = [s for s in json.load(fh).get("stations", []) if isinstance(s, dict) and s.get("name")]
    if not stations:
        return {"status": "fail", "summary": f"{sp} names no station", "next_action": f"lune run kit world look {name}"}
    named, _, _, pairing_problem = read_pairing(refs_dir)
    refs = pair_refs([s["name"] for s in stations], refs_dir)
    three = studio_dir is not None
    out_dir = out_dir or os.path.join(studio_dir if three else look_dir, "pages")
    os.makedirs(out_dir, exist_ok=True)
    for f in os.listdir(out_dir):  # (a last run's pages: a station that is gone must not stay on show)
        if f.endswith(".png"):
            os.remove(os.path.join(out_dir, f))
    meta = {}
    if three and os.path.isfile(os.path.join(studio_dir, "shots", "capture.json")):
        with open(os.path.join(studio_dir, "shots", "capture.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
    pages, captured, rows = [], 0, []
    for i, s in enumerate(stations):
        studio = None
        if three:
            shot = os.path.join(studio_dir, "shots", s["name"] + ".png")
            got = (meta.get("stations") or {}).get(s["name"]) or {}
            if os.path.isfile(shot):
                captured += 1
                native = got.get("native")
                note = STUDIO_SHOWS
                if native:
                    note += f" - captured at {native[0]} x {native[1]}"
                studio = {"path": shot, "note": note}
            else:
                studio = {"path": None, "why": studio_why or meta.get("why") or "no capture was made"}
        out = os.path.join(out_dir, f"{i + 1:02d}_{s['name']}.png")
        words = station_words(s, look_dir, named)
        ref = dict(refs[s["name"]], problem=pairing_problem) if pairing_problem else refs[s["name"]]
        page(name, i + 1, len(stations), s, words, ref, os.path.join(look_dir, s["name"] + ".png"),
             studio, pane, out)
        pages.append(out.replace(os.sep, "/"))
        rows.append({"station": s["name"], "title": words[0], "page": pages[-1], "reference": refs[s["name"]]["file"],
                     "paired": refs[s["name"]]["how"], "studio": bool(studio and studio.get("path"))})
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"world": name, "pane": list(pane), "pages": rows}, fh, indent=1)
    by_order = [r["station"] for r in rows if r["paired"] == "order"]
    no_ref = [r["station"] for r in rows if r["paired"] == "none"]
    line = look_line(out_dir, pages, pane, three, captured)
    summary = f"{len(pages)} station page(s) at {pane[0]} x {pane[1]} a pane"
    if three:
        summary += f", {captured} of {len(pages)} captured in Roblox Studio"
    if pairing_problem:
        summary += f"; NO reference still shown: {pairing_problem}"
    elif no_ref:
        summary += f"; NO reference still for {len(no_ref)}"
    elif by_order:
        summary += f"; {len(by_order)} paired with a still by order only ({', '.join(by_order[:3])})"
    return {"status": "pass", "summary": summary, "next_action": line, "pages": pages,
            "folder": out_dir.replace(os.sep, "/"), "look": line, "captured": captured, "by_order": by_order,
            "no_reference": no_ref, "pairing_problem": pairing_problem}


def main(argv):
    if len(argv) < 2:
        print(json.dumps({"status": "fail", "summary": "usage: lookpages.py <look_dir> <Name> [--refs DIR] [--studio DIR]",
                          "next_action": "lune run kit world look <Name>"}))
        return 1

    def opt(flag):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None

    pane = (1920, 1080)
    if opt("--pane"):
        w, h = opt("--pane").split("x")
        pane = (int(w), int(h))
    r = build(argv[0], argv[1], refs_dir=opt("--refs"), studio_dir=opt("--studio"), studio_why=opt("--studio-why"),
              out_dir=opt("--out"), pane=pane)
    print(json.dumps(r))
    return 0 if r["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
