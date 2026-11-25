"""refkit.py — gather references at scale, UNDERSTAND them as numbers, and hold a render up against them.

    lune run kit vfx refs wiki <preset> <wiki:Page | page URL>... [--only <regex>] [--skip <regex>] [--width 800]
    lune run kit vfx refs rank <preset> [--hue 35-70 | --grey] [--top 40]
    lune run kit vfx refs measure <preset> [--hue 35-70 | --grey] [--top 16]
    lune run kit vfx refs compare <preset> [--effect <name>] [--views hero,cine] [--times 2.5,4]
    lune run kit vfx refs timing <effect> [--view hero]   (the phase rules: anticipation dip, snappy climax, short tail)
    lune run kit vfx refs lore <set> <wiki:Page | URL>... [--search "<words>" --wiki <fandom>]   (TEXT: what it IS — lore.py)
    lune run kit vfx refs brief <set>   (the text facts + the measured palette/shape on one page; read before building)

wiki     every image on MediaWiki pages (fandom "dragonball:Super_Saiyan" or a full https://…/wiki/Page URL) through the
         wiki's own API (no scraping), thumbnails at --width, deduplicated, logged in SOURCES.md, into the git-ignored
         assets/effects/refs/<preset>/ (copyrighted frames stay private, measure-only). Logos / icons / SVGs skipped.
rank     scores every still by how much of the frame is the EFFECT's colour (bright pixels in the hue band; the band is
         found automatically when --hue is not given) -> ranks.json + a numbered contact sheet of the best (LOOK at it).
         --grey: an ACHROMATIC effect (dust, smoke, steam, concrete - real footage of a phenomenon is often grey): no hue;
         the effect = pale unsaturated pixels BRIGHTER than the scene before it (the set's first still: ONE locked-off
         clip's breakdown frames, not mixed stills); compare uses each recording's own first frame
measure  the effect pixels of the best stills as numbers: luminance bands (share of pixels + median colour each),
         saturation quartiles, hue -> assets/effects/refs_measured/<preset>.json (committed: numbers, no pictures).
compare  a COLOUR score (0-100) plus SHAPE numbers beside the reference's (jag, streak, solid; reported, not scored —
         framing differs too much to score them blind): the same measurement on a RECORDED render (build/vfx/booth/<effect>_play_<view>.mp4) -> a match score
         0-100 against the reference numbers (band shares, band colours, saturation) + the render beside the best
         references (build/vfx/refs/<effect>_compare.png). Show the owner nothing that has not been compared.
Each prints one JSON line {schema, status, summary, next_action, ...}.
"""

import ast
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image, ImageDraw

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"
REFS = os.path.join("assets", "effects", "refs")
MEASURED = os.path.join("assets", "effects", "refs_measured")
SHEETS = os.path.join("build", "vfx", "refs")
SKIP = r"logo|\.svg|icon|favicon|button|btn |badge|banner|signature|wiki\.png|placeholder"
BANDS = [(70, 140), (140, 175), (175, 200), (200, 225), (225, 256)]  # mean-RGB luminance bands of effect pixels (deep reds sit low)


def has_lore(preset):
    """The set's lore exists - a breakdown's frames live in <set>_scene, its lore in <set>.lore.json (either name counts)."""
    names = {preset, preset[:-6]} if preset.endswith("_scene") else {preset}
    return any(os.path.isfile(os.path.join(MEASURED, f"{n}.lore.json")) for n in names)


def out(status, summary, next_action, **kw):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **kw}))
    return 0 if status == "pass" else 1


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:60] or "ref"


IMAGE_HOSTS = ("static.wikia.nocookie.net", "vignette.wikia.nocookie.net", "upload.wikimedia.org")


def safe_image_url(url, api):
    """only http(s) images from the wiki's own host or the known wiki image CDNs (an API answer is not trusted blindly)"""
    u = urllib.parse.urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme not in ("http", "https") or not host:
        return False
    api_host = (urllib.parse.urlparse(api).hostname or "").lower()
    return host == api_host or host in IMAGE_HOSTS or host.endswith((".wikia.nocookie.net", ".wikimedia.org"))


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def api_and_page(spec):
    """'dragonball:Super_Saiyan' | 'https://x.fandom.com/wiki/Page' | 'https://en.wikipedia.org/wiki/Page' -> (api, title)"""
    if "://" in spec:
        u = urllib.parse.urlparse(spec)
        title = urllib.parse.unquote(u.path.split("/wiki/", 1)[1]) if "/wiki/" in u.path else u.path.strip("/")
        base = f"{u.scheme}://{u.netloc}"
        return [base + "/api.php", base + "/w/api.php"], title
    wiki, title = spec.split(":", 1)
    return [f"https://{wiki}.fandom.com/api.php"], title


def wiki_images(spec):
    apis, title = api_and_page(spec)
    for api in apis:
        try:
            names, cont = [], {}
            while True:
                q = {"action": "query", "titles": title, "prop": "images", "imlimit": "500", "redirects": "1", "format": "json", **cont}
                d = get_json(api + "?" + urllib.parse.urlencode(q))
                for p in d.get("query", {}).get("pages", {}).values():
                    names += [im["title"] for im in p.get("images", [])]
                if "continue" not in d:
                    return api, names
                cont = d["continue"]
        except Exception:  # noqa: BLE001 — try the next API path
            continue
    return None, []


def cmd_wiki(preset, args, opts):
    width = int(opts.get("--width", 800))
    only = re.compile(opts["--only"], re.I) if "--only" in opts else None
    skip = re.compile(SKIP + ("|" + opts["--skip"] if "--skip" in opts else ""), re.I)
    dest = os.path.join(REFS, preset)
    os.makedirs(dest, exist_ok=True)
    have = set(os.listdir(dest))
    got, failed, pages = [], [], []
    log = []
    for spec in args:
        api, names = wiki_images(spec)
        if not api:
            failed.append(f"{spec}: no MediaWiki API answered")
            continue
        if not names:  # a wrong title: say which pages the wiki has by that name
            try:
                q = {"action": "opensearch", "search": api_and_page(spec)[1].replace("_", " "), "limit": "6", "format": "json"}
                hits = get_json(api + "?" + urllib.parse.urlencode(q))[1]
            except Exception:  # noqa: BLE001
                hits = []
            failed.append(f"{spec}: no images — the wiki has: {', '.join(hits) or 'nothing by that name'}")
        names = sorted({n for n in names if not skip.search(n) and (only is None or only.search(n))})
        pages.append(f"{spec} ({len(names)})")
        for i in range(0, len(names), 40):
            q = {"action": "query", "titles": "|".join(names[i:i + 40]), "prop": "imageinfo", "iiprop": "url|size", "iiurlwidth": str(width), "format": "json"}
            try:
                d = get_json(api + "?" + urllib.parse.urlencode(q))
            except Exception as e:  # noqa: BLE001
                failed.append(f"imageinfo: {e}")
                continue
            for p in d.get("query", {}).get("pages", {}).values():
                ii = (p.get("imageinfo") or [None])[0]
                if not ii:
                    continue
                fn = slug(p["title"].split(":", 1)[-1]) + ".png"
                if fn in have:
                    continue
                url = ii.get("thumburl") or ii["url"]
                if not safe_image_url(url, api):
                    failed.append(f"{fn}: refused {url[:60]} (not the wiki's host or a wiki image CDN)")
                    continue
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": UA})
                    resp = urllib.request.urlopen(req, timeout=60)
                    if not safe_image_url(resp.geturl(), api):  # a redirect must stay on an allowed host too
                        failed.append(f"{fn}: refused redirect to {resp.geturl()[:60]}")
                        continue
                    data = resp.read()
                    Image.open(io.BytesIO(data)).convert("RGB").save(os.path.join(dest, fn))
                    have.add(fn)
                    got.append(fn)
                    log.append(f"| {time.strftime('%Y-%m-%d')} | {url} | {len(data):,} B | {fn} |")
                except Exception as e:  # noqa: BLE001
                    failed.append(f"{fn}: {type(e).__name__}")
                time.sleep(0.1)
    src_md = os.path.join(dest, "SOURCES.md")
    new = not os.path.isfile(src_md)
    with open(src_md, "a", encoding="utf-8", newline="\n") as fh:
        if new:
            fh.write(f"# Reference sources — {preset}\n\nPrivate, measure-only reference material (git-ignored; never redistributed).\n\n| date | source | size | became |\n|---|---|---|---|\n")
        fh.write("\n".join(log) + ("\n" if log else ""))
    return out("pass" if got or have else "fail", f"refs wiki {preset}: {len(got)} new still(s) from {', '.join(pages) or 'nothing'}" + (f"; {len(failed)} failed: {'; '.join(failed)[:400]}" if failed else ""),
               f"lune run kit vfx refs rank {preset}   (finds the stills that actually show the effect)", stills=len(have))


def stills(preset):
    d = os.path.join(REFS, preset)
    return [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))] if os.path.isdir(d) else []


def local_std(im):
    """luminance standard deviation over a 7x7 window: flat sky / walls ~0, energy (streaks, edges, glow falloff) > 0"""
    from scipy.ndimage import uniform_filter

    lum = np.asarray(im.convert("L")).astype(float)
    m = uniform_filter(lum, 7)
    return np.sqrt(np.maximum(uniform_filter(lum * lum, 7) - m * m, 0))


def hsv_of(img, size=(200, 150)):
    im = img.convert("RGB").resize(size)
    rgb = np.asarray(im).reshape(-1, 3).astype(float)
    hsv = np.asarray(im.convert("HSV")).reshape(-1, 3).astype(float)
    tex = local_std(im).reshape(-1)
    return rgb, hsv[:, 0] * 360 / 255, hsv[:, 1] / 255, hsv[:, 2] / 255, tex


FLAT = 2.5  # local std below this = a flat region (sky, a painted wall): never the effect
# an ACHROMATIC effect (2026-11-10: real footage of dust / smoke / steam / a concrete hit has no effect hue, so the
# measure found "no effect pixels" and the original route stalled on every grey phenomenon): rank / measure --grey
GREY = (-1.0, -1.0)


def effect_mask(h, s, v, hue, tex=None, base=None):
    lo, hi = hue
    if lo < 0:  # achromatic: pale, unsaturated and (given the scene before it) brighter than the wall it covers; no
        m = (v > 0.5) & (s < 0.2)  # texture test - a dust cloud IS smooth
        if base is not None:
            m &= v > base + 0.1
        return m
    inband = (h >= lo) & (h <= hi) if lo <= hi else (h >= lo) | (h <= hi)  # a band may wrap past red (e.g. 340-20)
    m = inband & (v > 0.55) & (s > 0.12)
    if tex is not None:  # a flat expanse of the right colour is a background (the blue sky that topped the UI ranking)
        m &= tex > FLAT
    return m


def auto_hue(paths):
    """the effect's hue: the most common hue among bright, saturated pixels over all stills (+-18 deg)"""
    hist = np.zeros(36)
    for p in paths[:200]:
        _, h, s, v, tex = hsv_of(Image.open(p), (80, 60))
        m = (v > 0.75) & (s > 0.35) & (tex > FLAT)
        hist += np.histogram(h[m], bins=36, range=(0, 360))[0]
    c = (int(np.argmax(hist)) + 0.5) * 10
    return ((c - 18) % 360, (c + 18) % 360)


def parse_hue(opts, paths):
    if "--grey" in opts:
        return GREY
    if "--hue" in opts:
        a, b = opts["--hue"].split("-")
        return (float(a), float(b))
    return auto_hue(paths)


def sheet(paths, dest, labels=None, cols=8, cell=(160, 120)):
    tiles = []
    for i, p in enumerate(paths):
        im = Image.open(p).convert("RGB") if isinstance(p, str) else p
        im.thumbnail(cell)
        t = Image.new("RGB", cell)
        t.paste(im, ((cell[0] - im.width) // 2, (cell[1] - im.height) // 2))
        ImageDraw.Draw(t).text((3, 2), str(labels[i] if labels else i), fill=(255, 40, 40))
        tiles.append(t)
    rows = (len(tiles) + cols - 1) // cols
    s = Image.new("RGB", (cols * cell[0], max(1, rows) * cell[1]))
    for i, t in enumerate(tiles):
        s.paste(t, ((i % cols) * cell[0], (i // cols) * cell[1]))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    s.save(dest)
    return dest


def cmd_rank(preset, opts):
    paths = stills(preset)
    if not paths:
        return out("fail", f"refs rank {preset}: no stills in {REFS}/{preset}", f"lune run kit vfx refs wiki {preset} <wiki:Page>...")
    hue = parse_hue(opts, paths)
    base = hsv_of(Image.open(paths[0]), (160, 120))[3] if hue[0] < 0 else None  # (grey: the scene before the effect)
    scored = []
    for p in paths:
        _, h, s, v, tex = hsv_of(Image.open(p), (160, 120))
        scored.append((float(effect_mask(h, s, v, hue, tex, base).mean()), os.path.basename(p)))
    scored.sort(reverse=True)
    top = int(opts.get("--top", 40))
    # FULL SHOTS: the effect's main piece is not cut by the picture's top / sides (its whole outline is in the frame) —
    # the stills that show its SHAPE; close-ups only show its colour and texture (silhouette.py)
    import silhouette

    # (--grey has no per-still base for the silhouette: full shots are not judged - review 2026-11-10)
    full = [] if hue[0] < 0 else [f for c, f in scored if c > 0.01 and silhouette.silhouette(Image.open(os.path.join(REFS, preset, f)), hue)]
    json.dump({"hue": hue, "ranks": scored, "full_shots": full}, open(os.path.join(REFS, preset, "ranks.json"), "w"), indent=0)
    dest = sheet([os.path.join(REFS, preset, f) for _, f in scored[:top]], os.path.join(SHEETS, f"{preset}_rank.png"))
    fdest = sheet([os.path.join(REFS, preset, f) for f in full[:top]], os.path.join(SHEETS, f"{preset}_full.png")) if full else None
    nxt = f"LOOK at {dest} (numbers = rank); then lune run kit vfx refs measure {preset}"
    if len(full) < 8:
        nxt += f". Only {len(full)} FULL shots (the whole effect in frame): gather wide shots before shaping meshes (refs wiki --only 'full|transform|wide|aura|charge')"
    hue_txt = "achromatic (--grey: pale pixels brighter than the first still)" if hue[0] < 0 else f"effect hue {hue[0]:.0f}-{hue[1]:.0f} deg"
    return out("pass", f"refs rank {preset}: {len(paths)} stills, {hue_txt}; best covers {scored[0][0]:.0%} of its frame; "
               f"{len(full)} full shots" + (f" ({fdest})" if fdest else ""), nxt, sheet=dest.replace(os.sep, "/"), hue=hue, full_shots=len(full))


def shape_of(img, hue, base_img=None):
    """framing-independent shape numbers of the effect in one picture: jag (outline length / the length a smooth blob of
    the same area would have: 1 = smooth, 3+ = spiky), streak (gradient energy across x vs across y inside the effect:
    > 1 = vertical streaks like an aura, < 1 = horizontal like a beam), solid (how much of its bounding box it fills)"""
    im = img.convert("RGB").resize((240, 180))
    hsv = np.asarray(im.convert("HSV")).astype(float)
    h, sat, v = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    bv = None
    if hue[0] < 0:  # achromatic: only against the scene before it (the same framing), else every pale pixel counts
        if base_img is None:
            return None
        bv = np.asarray(base_img.convert("RGB").resize((240, 180)).convert("HSV")).astype(float)[..., 2] / 255
    m = effect_mask(h, sat, v, hue, local_std(im), bv)
    area = int(m.sum())
    if area < 200:
        return None
    edge = (m[1:, :] != m[:-1, :]).sum() + (m[:, 1:] != m[:, :-1]).sum()
    jag = float(edge / (2 * np.sqrt(np.pi * area)))
    lum = np.asarray(im.convert("L")).astype(float)
    gx = np.abs(np.diff(lum, axis=1))[:-1, :] * m[:-1, :-1]
    gy = np.abs(np.diff(lum, axis=0))[:, :-1] * m[:-1, :-1]
    streak = float((gx.sum() + 1) / (gy.sum() + 1))
    ys, xs = np.nonzero(m)
    solid = float(area / max(1, (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)))
    return {"jag": round(jag, 2), "streak": round(streak, 2), "solid": round(solid, 2)}


def shape_summary(shapes):
    shapes = [x for x in shapes if x]
    if not shapes:
        return None
    return {k: round(float(np.median([x[k] for x in shapes])), 2) for k in ("jag", "streak", "solid")}


def measure_pixels(rgb_list):
    px = np.concatenate(rgb_list) if rgb_list else np.zeros((0, 3))
    if len(px) == 0:
        return None
    lum = px.mean(1)
    bands = []
    for lo, hi in BANDS:
        sel = px[(lum >= lo) & (lum < hi)]
        bands.append({"lum": [lo, hi], "share": round(len(sel) / len(px), 3), "rgb": np.median(sel, 0).round().astype(int).tolist() if len(sel) else None})
    sat = (px.max(1) - px.min(1)) / np.maximum(px.max(1), 1)
    return {"pixels": int(len(px)), "bands": bands, "saturation": np.percentile(sat, [25, 50, 75]).round(3).tolist(),
            "median_rgb": np.median(px, 0).round().astype(int).tolist()}


def cmd_measure(preset, opts):
    rk = os.path.join(REFS, preset, "ranks.json")
    if not os.path.isfile(rk):
        return out("fail", f"refs measure {preset}: no ranks yet", f"lune run kit vfx refs rank {preset}")
    r = json.load(open(rk))
    hue = GREY if "--grey" in opts else (parse_hue(opts, []) if "--hue" in opts else tuple(r["hue"]))
    picks = [f for _, f in r["ranks"][: int(opts.get("--top", 16))]]
    if "--pick" in opts:  # the owner's / my own choice from the contact sheet: --pick 0,1,4,9
        picks = [r["ranks"][int(i)][1] for i in opts["--pick"].split(",")]
    rgbs = []
    first = stills(preset)
    base = hsv_of(Image.open(first[0]))[3] if hue[0] < 0 and first else None  # (grey: the scene before the effect)
    for f in picks:
        rgb, h, s, v, tex = hsv_of(Image.open(os.path.join(REFS, preset, f)))
        rgbs.append(rgb[effect_mask(h, s, v, hue, tex, base)])
    m = measure_pixels(rgbs)
    if m is None:
        return out("fail", f"refs measure {preset}: no effect pixels in the picked stills", "check --hue against the rank sheet")
    first_im = Image.open(first[0]) if first else None
    m["shape"] = shape_summary([shape_of(Image.open(os.path.join(REFS, preset, f)), hue, first_im) for f in picks])
    m.update({"preset": preset, "hue": list(hue), "from": picks, "date": time.strftime("%Y-%m-%d")})
    os.makedirs(MEASURED, exist_ok=True)
    dest = os.path.join(MEASURED, f"{preset}.json")
    json.dump(m, open(dest, "w", encoding="utf-8", newline="\n"), indent=1)
    desc = ", ".join(f"{b['rgb']} {b['share']:.0%}" for b in m["bands"] if b["rgb"])
    if not has_lore(preset):  # vision alone is not enough (owner 2026-10-14)
        return out("warn", f"refs measure {preset}: measured ({desc}) but NO LORE: the frames say how it looks, not what it IS (scale, power, behaviour, variants)",
                   f"lune run kit vfx refs lore {preset} <wiki:Page>... (or --search \"<words>\" --wiki <fandom>), then refs brief {preset}", measured=dest.replace(os.sep, "/"))
    return out("pass", f"refs measure {preset}: {m['pixels']} effect px from {len(picks)} stills; bands {desc}; saturation median {m['saturation'][1]}",
               f"build to these numbers, record, then: lune run kit vfx refs compare {preset} --effect <name>", measured=dest.replace(os.sep, "/"))


def duration_of(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def frame_of(video, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", video, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                         capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(raw)).convert("RGB")


def score(ref, got):
    """0-100: band shares (40), band colours (40), saturation (20)"""
    share = sum(abs(a["share"] - b["share"]) for a, b in zip(ref["bands"], got["bands"])) / 2  # 0..1
    cols = []
    for a, b in zip(ref["bands"], got["bands"]):
        if a["rgb"] and b["rgb"]:
            cols.append(np.abs(np.array(a["rgb"]) - np.array(b["rgb"])).mean() / 255 * a["share"])
    col = sum(cols) / max(1e-6, sum(a["share"] for a in ref["bands"] if a["rgb"]))
    sat = abs(ref["saturation"][1] - got["saturation"][1])
    return round(float(100 * (0.4 * (1 - min(1, share)) + 0.4 * (1 - min(1, col * 4)) + 0.2 * (1 - min(1, sat * 2)))), 1), {"share_off": round(float(share), 3), "colour_off": round(float(col), 3), "sat_off": round(float(sat), 3)}


def cmd_compare(preset, opts):
    mp = os.path.join(MEASURED, f"{preset}.json")
    if not os.path.isfile(mp):
        return out("fail", f"refs compare {preset}: not measured yet", f"lune run kit vfx refs measure {preset}")
    ref = json.load(open(mp, encoding="utf-8"))
    effect = opts.get("--effect", preset)
    views = opts.get("--views", "hero,cine").split(",")
    times = [float(t) for t in opts["--times"].split(",")] if "--times" in opts else None  # default: 40 % and 65 % through each video
    hue = tuple(ref["hue"])
    rgbs, frames, shapes = [], [], []
    for v in views:
        vid = os.path.join("build", "vfx", "booth", f"{effect}_play_{v}.mp4")
        if not os.path.isfile(vid):
            continue
        d = duration_of(vid)
        if not times and d <= 0:
            return out("fail", f"refs compare: could not read the length of {vid} (is ffprobe on PATH?)", "pass --times explicitly")
        for t in (times or [round(d * 0.4, 2), round(d * 0.65, 2)]):
            if d and t > d - 0.05:  # past the end of this recording
                continue
            im = frame_of(vid, t)
            w, h0 = im.size
            crop = im.crop((int(w * 0.2), 0, int(w * 0.8), h0))
            frames.append(crop)
            rgb, h, s, vv, tex = hsv_of(crop)
            base_im = None
            if hue[0] < 0:  # achromatic: against this recording's own first frame (the booth before the effect)
                b = frame_of(vid, 0.0)
                base_im = b.crop((int(b.size[0] * 0.2), 0, int(b.size[0] * 0.8), b.size[1]))
            rgbs.append(rgb[effect_mask(h, s, vv, hue, tex, hsv_of(base_im)[3] if base_im is not None else None)])
            shapes.append(shape_of(crop, hue, base_im))
    if not frames:
        return out("fail", f"refs compare: no recording of {effect}", f"lune run kit vfx play {effect} --record --views {','.join(views)}")
    got = measure_pixels(rgbs)
    if got is None:
        return out("fail", f"refs compare {effect}: the render has NO pixels in the effect's colour band {hue[0]:.0f}-{hue[1]:.0f}", "the colour is wrong — rebuild toward the measured bands")
    sc, parts = score(ref, got)
    refs_top = [os.path.join(REFS, preset, f) for f in ref["from"][:4] if os.path.isfile(os.path.join(REFS, preset, f))]
    dest = sheet(frames + refs_top, os.path.join(SHEETS, f"{effect}_compare.png"), labels=[f"render {i}" for i in range(len(frames))] + [f"ref {i}" for i in range(len(refs_top))],
                 cols=max(4, len(frames)), cell=(240, 180))
    worst = []
    for a, b in zip(ref["bands"], got["bands"]):
        if a["rgb"] and b["rgb"]:
            worst.append(f"lum {a['lum'][0]}-{a['lum'][1]}: share {b['share']:.0%} vs ref {a['share']:.0%}, colour {b['rgb']} vs {a['rgb']}")
    status = "pass" if sc >= 70 else "warn"
    shp, rshp = shape_summary(shapes), ref.get("shape")
    shape_line = ""
    if shp and rshp:
        shape_line = "; shape " + ", ".join(f"{k} {shp[k]} vs ref {rshp[k]}" for k in ("jag", "streak", "solid"))
    return out(status, f"refs compare {effect}: match {sc}/100 against {preset} ({parts}); saturation {got['saturation'][1]} vs ref {ref['saturation'][1]}{shape_line}",
               f"LOOK at {dest}; " + ("close to the references" if sc >= 70 else "off: " + " | ".join(worst))
               + (" (shape: jag = how spiky the outline is, streak > 1 = vertical streaks, solid = how filled)" if shape_line else ""),
               score=sc, parts=parts, render=got, shape=shp, ref_shape=rshp, sheet=dest.replace(os.sep, "/"))


def lum_curve(video, fps=30):
    """mean luminance of every frame (downscaled) -> list"""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"fps={fps},scale=96:54,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True, check=True).stdout
    a = np.frombuffer(r, dtype=np.uint8).reshape(-1, 54 * 96).astype(float)
    return a.mean(1), a.std(1)


def cmd_timing(effect, opts):
    """the phase rules from the research (Riot style guide / realtimevfx critiques / 80.lv 'VFX staples'):
    anticipation — a short DARK beat right before the climax (<= 0.05-0.2 s); climax — the brightest, highest-contrast
    moment; dissipation — short and low-contrast (here: time from the climax back to near the start level)."""
    view = opts.get("--view", "hero")
    vid = os.path.join("build", "vfx", "booth", f"{effect}_play_{view}.mp4")
    if not os.path.isfile(vid):
        return out("fail", f"refs timing: no recording {vid}", f"python kit/vfx/autorec.py {effect} --views {view}")
    fps = 30
    lum, con = lum_curve(vid, fps)
    n = len(lum)
    if n < 10:
        return out("fail", f"refs timing: {vid} has {n} frames", "re-record it")
    base = float(np.median(lum[: max(3, n // 20)]))  # the empty start
    peak = int(np.argmax(lum))
    pk = float(lum[peak])
    # anticipation: the darkest frame in the 0.4 s before the climax, vs the level 0.5-1.0 s before it
    w0, w1 = max(0, peak - int(0.4 * fps)), peak
    pre = lum[max(0, peak - int(1.0 * fps)): max(1, peak - int(0.5 * fps))]
    dip_i = w0 + int(np.argmin(lum[w0:w1])) if w1 > w0 else peak
    dip = float(lum[dip_i]) if w1 > w0 else pk
    pre_level = float(np.mean(pre)) if len(pre) else base
    has_dip = dip < pre_level - 2.0
    # attack: from where the rise passes 25 % of the climax up to the climax
    rise_lo = base + 0.25 * (pk - base)
    k = peak
    while k > 0 and lum[k] > rise_lo:
        k -= 1
    attack = (peak - k) / fps
    # dissipation: from the climax until within 15 % of the way back to the start level
    end_level = base + 0.15 * (pk - base)
    j = peak
    while j < n - 1 and lum[j] > end_level:
        j += 1
    dissip = (j - peak) / fps
    total = n / fps
    rules = []
    rules.append(("anticipation dip before the climax", has_dip, f"{dip:.1f} at {dip_i / fps:.2f}s vs {pre_level:.1f} before" if w1 > w0 else "no lead-in"))
    rules.append(("snappy climax (attack <= 0.25 s)", attack <= 0.25, f"{attack:.2f}s"))
    rules.append(("dissipation <= 40 % of the effect", dissip <= 0.4 * total, f"{dissip:.2f}s of {total:.2f}s"))
    rules.append(("climax contrast (frame std >= 25)", float(con[peak]) >= 25, f"{con[peak]:.1f}"))
    passed = sum(1 for _, ok, _ in rules if ok)
    fix = {"anticipation dip before the climax": "add a 0.05-0.1 s darkening right before the release (a screen layer brightness dip or the aura snapping off)",
           "snappy climax (attack <= 0.25 s)": "make the release land in 1-3 frames (flash + scale pop), not a slow ramp",
           "dissipation <= 40 % of the effect": "shorten the tail: erode (kit erode / animepass) and end the lights sooner",
           "climax contrast (frame std >= 25)": "push the climax: a white-hot core against a dark body (an impact frame ONLY if the attack is truly massive)"}
    misses = [fix[n_] for n_, ok, _ in rules if not ok]
    return out("pass" if passed == len(rules) else "warn",
               f"refs timing {effect} ({view}): climax at {peak / fps:.2f}s; " + "; ".join(f"{n_}: {'yes' if ok else 'NO'} ({v})" for n_, ok, v in rules),
               "; ".join(misses) if misses else "the phases read (anticipation, climax, short dissipation)",
               rules=[{"rule": n_, "ok": bool(ok), "value": v} for n_, ok, v in rules], climax=round(peak / fps, 2))


def lore_citations(P):
    """(set, cited, facts) — how many facts from the set's TEXT research (refs lore) the effect's generator quotes.
    The generator is found from the preset's "about" path; its set from 'refs_measured/<set>' or a '<name>_set' word.
    Owner 2026-10-14: "ENFORCE ... GET TEXT DATA ON WHAT THE ATTACK IS" — an effect that quotes nothing was built blind."""
    m = re.search(r"assets/effects/generators/[\w./-]+\.py", P.get("about", ""))
    if not m or not os.path.isfile(m.group(0)):
        return None, 0, 0
    src = open(m.group(0), encoding="utf-8").read()
    sets = re.findall(r"refs_measured/(\w+?)\.(?:brief|lore|json)", src) + re.findall(r"\b(\w+_set)\b", src)
    for st in dict.fromkeys(sets):
        lp = os.path.join(MEASURED, f"{st}.lore.json")
        if not os.path.isfile(lp):
            continue
        facts = [re.sub(r"\W+", " ", f["text"]).strip().lower() for f in json.load(open(lp, encoding="utf-8"))["facts"]]
        # quotes live in the module DOCSTRING (not between code literals); they may wrap lines or use curly quotes
        try:
            doc = ast.get_docstring(ast.parse(src)) or ""
        except SyntaxError:
            doc = ""
        quotes = [re.sub(r"\W+", " ", q).strip().lower() for q in re.findall(r'["“]([^"“”]{14,}?)["”]', doc)]
        # a citation = a quote inside ONE fact of >= 8 words, or >= 6 words covering >= 40 % of it; each fact counts once
        # ("the kamehameha" x3 is not 3 citations)
        def cites(q, f):
            n = len(q.split())
            return q in f and (n >= 8 or (n >= 6 and n >= 0.4 * len(f.split())))

        cited = sum(1 for f in facts if any(cites(q, f) for q in quotes))
        return st, cited, len(facts)
    return (sets[0] if sets else None), 0, 0


def bare_mesh(el):
    """a mesh layer that will read as plastic: big (any scale axis > 2.5), untextured, no soft edges, mostly opaque at
    its peak. Small untextured cores / thin bolts and anything with a texture or a fade are fine."""
    if el.get("kind") != "mesh" or el.get("texture") or el.get("shape") in ("rock", "bolt", "corona"):  # line geometry reads as lines
        return False
    p = el.get("params") or {}
    if any(p.get(k) for k in ("fadeIn", "fadeOut", "fadeSides")):
        return False
    sc = el.get("scale", 1)
    vals = []
    for k in (sc if isinstance(sc, list) else [[0, sc]]):
        v = k[1] if isinstance(k, list) and len(k) == 2 else k
        vals += v if isinstance(v, list) else [v]
    big = max((abs(float(x)) for x in vals if isinstance(x, (int, float))), default=1) > 2.5
    tr = el.get("transparency", 0)
    peak = min(k[1] for k in tr) if isinstance(tr, list) and tr and isinstance(tr[0], list) else float(tr or 0)
    return big and peak < 0.4


def _textures(P):
    return {el["texture"] for el in P.get("layers", []) if isinstance(el, dict) and isinstance(el.get("texture"), str)}


def _colours(P):
    """every colour the preset draws with: palette entries + each layer's colour (palette names, rgb, keyframes)"""
    pal = {k: v for k, v in (P.get("palette") or {}).items() if isinstance(v, list) and len(v) == 3}
    found = [tuple(v) for v in pal.values()]

    def take(c):
        if isinstance(c, str) and c in pal:
            found.append(tuple(pal[c]))
        elif isinstance(c, list) and len(c) == 3 and all(isinstance(x, (int, float)) for x in c):
            found.append(tuple(c))
        elif isinstance(c, list):
            for k in c:
                if isinstance(k, list) and len(k) == 2:
                    take(k[1])

    for el in P.get("layers", []):
        if isinstance(el, dict):
            take(el.get("color"))
    return set(found)


def loved_effects(verdicts_path):
    """the owner's loved effects from the VFX library's verdicts: a score >= 7, or unscored words of plain praise"""
    try:
        v = json.load(open(verdicts_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    praise = re.compile(r"\b(best|amazing|love[ds]?|splendid|wow|times better|perfect)\b", re.I)
    loved = []
    for name, entries in (v.items() if isinstance(v, dict) else []):
        last = entries[-1] if isinstance(entries, list) and entries else entries
        if not isinstance(last, dict):
            continue
        score = last.get("score")
        try:
            score = float(score) if score not in (None, "None", "") else None
        except (TypeError, ValueError):
            score = None
        if (score is not None and score >= 7) or (score is None and praise.search(str(last.get("words", "")))):
            loved.append(name)
    return loved


def reskin(name, P, effects_dir, verdicts_path, measured_dir):
    """rule 7 (mission 02-vfx 5.12, the owner's originality rule): a preset that wears a LOVED effect's look - its
    distinctive textures (shared basics used across >= 3 other families, like a soft glow, don't count), helped by a
    matching palette - is named a RE-SKIN, unless its scene's beat sheet quotes the owner asking for it (a line with
    'owner', a date and a quote). Versions inside one family (same first name token: saiyan_*) are lineage, not
    re-skins. -> (ok, value)"""
    others = {}
    for p in os.listdir(effects_dir) if os.path.isdir(effects_dir) else []:
        if p.endswith(".json") and not p.startswith("_"):
            try:
                d = json.load(open(os.path.join(effects_dir, p), encoding="utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(d, dict) and isinstance(d.get("layers"), list):
                others[p[:-5]] = d
    fam = name.split("_")[0]
    fams = {}  # which effect families use each texture, the tested preset's own family left out (copies can't hide)
    for n, d in others.items():
        if n.split("_")[0] == fam:
            continue
        for t in _textures(d):
            fams.setdefault(t, set()).add(n.split("_")[0])
    mine_t, mine_c = _textures(P), _colours(P)
    hits = []
    for ln in loved_effects(verdicts_path):
        L = others.get(ln)
        if L is None or ln == name or ln.split("_")[0] == fam:
            continue
        # a shared basic (a soft glow) is used across >= 3 other families; the loved effect's own textures are not
        distinct = {t for t in _textures(L) if len(fams.get(t, set()) - {ln.split("_")[0]}) < 3}
        cov = len(mine_t & distinct) / len(distinct) if distinct else 0.0
        lc = _colours(L)
        pal = (sum(1 for c in mine_c if any(sum(abs(x - y) for x, y in zip(c, d)) <= 40 for d in lc)) / len(mine_c)) if mine_c else 0.0
        if cov >= 0.3 or (cov >= 0.15 and pal >= 0.7):
            hits.append(f"{ln} (its textures {cov:.0%}, palette {pal:.0%})")
    if not hits:
        return True, "own look"
    try:  # presets older than the route (frozen in kit/vfx/scene_gate.json) are reported, not judged
        old = set(json.load(open(os.path.join("kit", "vfx", "scene_gate.json"), encoding="utf-8"))["grandfathered"])
    except (OSError, json.JSONDecodeError, KeyError):
        old = set()
    if name in old and "scene" not in P:
        return True, "older than rule 7 (reported only): wears " + "; ".join(hits)
    scene = P.get("scene") if isinstance(P.get("scene"), dict) else {}
    beats = os.path.join(measured_dir, f"{scene.get('set')}.beats.md") if scene.get("set") else None
    if beats and os.path.isfile(beats):
        if re.search(r"owner[^\n]*\d{4}-\d{2}-\d{2}[^\n]*[\"'][^\"'\n]{6,}[\"']", open(beats, encoding="utf-8").read(), re.I):
            return True, "wears " + "; ".join(hits) + " - the owner asked for it (beats.md)"
    return False, "RE-SKIN of " + "; ".join(hits)


def cmd_norms(preset, opts):
    """a preset's layers against the measured Roblox pro norms (_roblox_pro_norms.json, from kit/vfx/study.luau over 232
    real effects): additive share, layer lifetimes, front-loaded transparency, orientation use. No recording needed."""
    np_ = os.path.join(MEASURED, "_roblox_pro_norms.json")
    effects_dir = opts.get("--effects", os.path.join("assets", "effects"))  # a fixture dir in the selftest
    path = os.path.join(effects_dir, f"{preset}.json")
    if not os.path.isfile(np_) or not os.path.isfile(path):
        return out("fail", f"refs norms: missing {np_ if not os.path.isfile(np_) else path}", "run kit/vfx/study.luau over a corpus / check the name")
    N = json.load(open(np_, encoding="utf-8"))
    P = json.load(open(path, encoding="utf-8"))
    layers = [el for el in P.get("layers", []) if el.get("kind") in ("sprite", "mesh")]
    if not layers:
        return out("warn", f"refs norms {preset}: no sprite or mesh layers", "nothing to compare")

    def additive(el):
        if el["kind"] == "mesh":
            return (el.get("material") or "Neon") in ("Neon", "ForceField")
        return (el.get("lightEmission") if el.get("lightEmission") is not None else 1) >= 0.5

    def life(el):
        if el["kind"] == "mesh":
            return float(el.get("life") or 1)
        lt = el.get("lifetime")
        return float((lt[0] + lt[1]) / 2) if isinstance(lt, list) else float(lt or 1)

    def front(el):
        tr = el.get("transparency")
        if not (isinstance(tr, list) and tr and isinstance(tr[0], list)):
            return True
        return min(tr, key=lambda k: k[1])[0] <= 0.35

    add_share = sum(additive(e) for e in layers) / len(layers)
    lives = sorted(life(e) for e in layers)
    med = lives[len(lives) // 2]
    front_share = sum(front(e) for e in layers) / len(layers)
    vp = sum(1 for e in layers if e.get("orientation") in ("VelocityParallel", "VelocityPerpendicular")) / len(layers)
    q = N["lifetime_quartiles_s"]
    rules = [
        ("non-additive layers for contrast (pros ~44 %)", add_share <= 0.85, f"{1 - add_share:.0%} non-additive"),
        (f"short lives (pros median {q[1]} s, most {q[0]}-{q[2]} s)", med <= 1.5, f"median {med:.2f} s"),
        (f"front-loaded curves (pros {N['front_loaded_share']:.0%})", front_share >= 0.6, f"{front_share:.0%}"),
        ("velocity-aligned streaks/discs used (pros 13 %)", vp > 0, f"{vp:.0%}"),
    ]
    st, cited, nf = lore_citations(P)
    rules.append(("built from the TEXT too (generator quotes >= 3 lore facts)", cited >= 3,
                  f"{cited} quoted from {st}.lore.json ({nf} facts)" if nf else (f"no lore for {st}" if st else "no reference set named in the generator")))
    # the details (owner 2026-10-15: the Rasengan's air blow-out "looks horrible" - two untextured solid Neon ribbons):
    # a BIG mesh with no texture, no soft edges and little transparency reads as plastic, never as energy / air / fire
    bare = [el["name"] for el in P.get("layers", []) if bare_mesh(el)]
    rules.append(("no bare solid meshes (big, untextured, hard-edged, opaque)", not bare, ", ".join(bare[:4]) + (" ..." if len(bare) > 4 else "") if bare else "none"))
    ok7, v7 = reskin(preset, P, effects_dir, opts.get("--verdicts", os.path.join("library", "vfx", "verdicts.json")),
                     opts.get("--measured", MEASURED))
    rules.append(("its OWN look, not a re-skin of a loved effect (rule 7)", ok7, v7))
    fixes = {0: "add NON-additive layers (lightEmission 0 / non-Neon): dark or solid shapes hold contrast and colour; black = dark normal-blended particles",
             1: "split long layers into short bursts (0.2-1 s) layered and re-emitted",
             2: "pop layers in at once and fade over the rest (least transparent in the first third)",
             3: "shards/sparks as VelocityParallel streaks, shock rings as VelocityPerpendicular discs",
             4: f"refs lore {st or '<set>'} <wiki pages> + refs brief, then build each fact and QUOTE it in the generator's docstring",
             6: "take the look from THIS effect's own scene frames (its textures, palette and title card), not the loved effect's; or quote the owner asking for it in the scene's beats.md",
             5: "give every big mesh a texture with detail (streaks / cells / flames: wind_streaks(_v), ki_wisp_streaks ...), soft edges (fadeIn / fadeOut / fadeSides) and an erode or fade - air and energy are never a solid surface"}
    misses = [fixes[i] for i, (_, ok, _) in enumerate(rules) if not ok]
    passed = sum(ok for _, ok, _ in rules)
    return out("pass" if passed == len(rules) else "warn",
               f"refs norms {preset}: {passed}/{len(rules)} — " + "; ".join(f"{n}: {'yes' if ok else 'NO'} ({v})" for n, ok, v in rules),
               "; ".join(misses) if misses else "built like the pros' effects", rules=[{"rule": n, "ok": bool(ok), "value": v} for n, ok, v in rules])


def main(argv):
    sub = argv[0]
    rest = argv[1:]
    if not rest:
        return out("fail", f"refs {sub}: needs a preset", f"lune run kit vfx refs {sub} <preset> ...")
    preset = rest[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", preset):
        return out("fail", f"bad preset name {preset!r}", "letters, digits, _ and - only")
    opts, args, i = {}, [], 1
    while i < len(rest):
        if rest[i] == "--grey":  # a flag (no value): an achromatic effect
            opts["--grey"] = True
            i += 1
        elif rest[i].startswith("--") and i + 1 < len(rest):
            opts[rest[i]] = rest[i + 1]
            i += 2
        else:
            args.append(rest[i])
            i += 1
    if sub == "wiki":
        return cmd_wiki(preset, args, opts)
    if sub == "rank":
        return cmd_rank(preset, opts)
    if sub == "measure":
        return cmd_measure(preset, opts)
    if sub == "compare":
        return cmd_compare(preset, opts)
    if sub == "timing":
        return cmd_timing(preset, opts)
    if sub == "norms":
        return cmd_norms(preset, opts)
    if sub == "silhouette":  # the outline as numbers -> mesh shape params (silhouette.py)
        import silhouette

        return silhouette.cmd_silhouette(preset, opts)
    if sub in ("lore", "brief"):  # the TEXT side: what the attack is (lore.py)
        import lore

        return lore.cmd_lore(preset, args, opts) if sub == "lore" else lore.cmd_brief(preset, opts)
    return out("fail", f"refs: unknown subcommand {sub}", "wiki | rank | measure | compare | timing | norms | lore | brief | silhouette")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
