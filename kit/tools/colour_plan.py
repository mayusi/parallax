"""kit/tools/colour_plan.py — THE COLOUR PLAN of a model sheet: colour as a design step, read off the object's own
picture before anything is built (numpy + Pillow; kit/tools/sheet.py draws it and keeps it in <asset>.sheet.json).

What a concept artist checks before a piece is modelled, measured instead of eyeballed:

    ROLES    each palette colour's SHARE of the object and the role that gives it: MAIN (the largest), SECOND (every
             other colour that covers a real part of it), ACCENT (small and standing out from the main: where the
             eye goes), minor (the rest). The designer's rule of thumb is about 60 / 30 / 10; the plan says the
             numbers and leaves the judgement to the owner. Roles are given to MEASURED part colours only (kit
             pack <asset> colours): colours sampled off a picture are bands of its shading, not parts.
    VALUES   the object in THREE GREYS - its own dark, middle and light families (the squint test: detail gone, only
             the big value shapes left). One family should lead (half the object or more); near-equal families
             pull against each other, and colours that differ only in hue fall into ONE grey - parts that separate
             by hue alone do not separate at a distance, in fog or for a colour-blind player. An object of two
             values has an EMPTY family: said as "none", never filled in.

Nothing here refuses a sheet: these are NOTES beside the palette, for the owner's yes.

WHERE THE OBJECT IS: inside the view's traced outline when the sheet gives one (kit trace: the object's own
silhouette); else the opaque part of a cut-out; else what is away from the picture's ground - and then the plan
says so when that ground is not plain (its corners disagree, or its border reads as object): the shares are unsure.

WHICH COLOUR A PIXEL IS: the palette colour whose SHADE it is nearest to. A lit picture shows every colour in many
brightnesses: each palette colour is taken as a line of shades (its linear colour times 0.2 .. 1.2), and a pixel
goes to the colour with the nearest shade (CIELAB), a shade far from the colour's own costing a little (SHADE_COST:
between a black part and the shadow of a grey one, the black part wins). What is near no colour's shades is
"other". What this cannot know: a white highlight on a dark part counts toward the nearest light colour, or other.

    plan = colour_plan.plan(picture_path, [{"name": "body", "rgb": [46, 48, 56]}, ...], polygon=[(x, y), ...])
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blender"))
import rbx_colour  # noqa: E402  (srgb_to_lab: the kit's own, unit-tested)

LONGEST = 1024       # a picture is measured at this longest side at most (shares are ratios of areas)
SECOND_MIN = 0.12    # a second colour covers at least this much of the object
ACCENT_MAX = 0.12    # an accent covers less than this ...
ACCENT_APART = 25.0  # ... and stands this far (CIELAB) from the main colour
EDGE = 0.01          # a share within this of the line between accent and second: said
MAIN_LEADS = 0.40    # under this the largest colour does not lead: said
OTHER_SAID = 0.20    # more of the object than this near no palette colour: said
SHADES = (0.2, 0.27, 0.36, 0.48, 0.62, 0.78, 0.9, 1.0, 1.1, 1.2)   # a colour as the light leaves it
SHADE_COST = 6.0     # what a shade costs per e-fold of brightness away from the colour's own
FAR = 20.0           # a pixel further than this (CIELAB) from every palette colour's shades is "other"
SAME_COLOUR = 3.0    # two palette colours closer than this (CIELAB) are one colour
SAME_GREY_FROM = 0.10  # two colours of this share or more in ONE value family, or closer than SAME_VALUE: said
SAME_VALUE = 8.0     # two colours closer than this (L*) are one grey whatever families they fell in
FAMILY_LEADS = 0.50  # a value family under this share does not lead
ONE_VALUE = 20.0     # the lightest and darkest families closer than this (L*): the piece is one value
BACKDROP = 60        # a pixel within this (sum of |RGB| steps) of the picture's ground is ground
BORDER_OBJECT = 0.10  # more of the picture's border than this reading as object: its ground is not plain


def lab(rgb255):
    """sRGB 0..255 (... x 3) -> CIELAB"""
    return rbx_colour.srgb_to_lab(np.asarray(rgb255, np.float64) / 255.0)


def read(path, box=None, polygon=None, holes=(), longest=LONGEST):
    """the picture and its OBJECT -> {"rgb": (H, W, 3) uint8 (scaled to `longest` at most), "mask": (H, W) bool,
    "px": (N, 3) uint8 the object's pixels, "scale", "by": how the object was found (outline | cut-out | ground),
    "unsure": None or why the shares are unsure}.
    polygon / holes: the traced outline and its holes in the picture's own pixels; box: (x0, y0, x1, y1) the traced
    object's box - only pixels inside it count."""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    with Image.open(path) as im:
        cut = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
        rgba = im.convert("RGBA")
    s = min(1.0, float(longest) / max(rgba.size))
    if s < 1.0:
        rgba = rgba.resize((max(1, int(round(rgba.width * s))), max(1, int(round(rgba.height * s)))), Image.BOX)
    arr = np.asarray(rgba)
    rgb, alpha = arr[..., :3], arr[..., 3]
    h, w = rgb.shape[:2]
    unsure = None
    if polygon is not None and len(polygon) >= 3:
        # (drawn four times as large and averaged down: a pixel is the object's when the outline covers more than
        # half of it - a polygon drawn at the picture's own size takes every pixel its line touches, a border one
        # pixel wide all round that is not the object)
        up = 4
        m = Image.new("L", (w * up, h * up), 0)
        d = ImageDraw.Draw(m)
        d.polygon([(float(x) * s * up, float(y) * s * up) for x, y in polygon], fill=255)
        for hole in holes or ():
            if len(hole) >= 3:
                d.polygon([(float(x) * s * up, float(y) * s * up) for x, y in hole], fill=0)
        m = m.reduce(up)
        mask, by = (np.asarray(m) > 127) & (alpha > 200), "outline"
    elif cut and (alpha < 200).any():
        mask, by = alpha > 200, "cut-out"
    else:
        ring = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]).astype(np.int32)
        ground = np.median(ring, axis=0)
        mask, by = np.abs(rgb.astype(np.int32) - ground).sum(axis=-1) > BACKDROP, "ground"
        on_border = float((np.abs(ring - ground).sum(axis=-1) > BACKDROP).mean())
        corners = rgb[[0, 0, -1, -1], [0, -1, 0, -1]].astype(np.int32)
        apart = int(np.abs(corners[:, None, :] - corners[None, :, :]).sum(axis=-1).max())
        if on_border > BORDER_OBJECT or apart > BACKDROP:
            unsure = (f"the picture's ground is not plain ({on_border:.0%} of its border reads as object): the shares "
                      "are unsure - trace the view (lune run kit trace) or cut the object out")
    if box is not None:
        x0, y0, x1, y1 = (int(round(float(v) * s)) for v in box)
        inside = np.zeros(mask.shape, bool)
        inside[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
        mask = mask & inside
    return {"rgb": rgb, "mask": mask, "px": rgb[mask], "scale": s, "by": by, "unsure": unsure}


def object_pixels(path, box=None, polygon=None, holes=()):
    """the picture's OBJECT pixels -> (rgb (N, 3) uint8, mask (H, W) bool, the RGB picture) (read())"""
    a = read(path, box, polygon, holes)
    return a["px"], a["mask"], a["rgb"]


def sample(px, n=6):
    """the object's n most common colours (median cut over its OWN pixels) -> [{"name", "rgb"}], most common first:
    a hint where nothing is measured - bands of the picture's shading, not parts"""
    from PIL import Image  # noqa: PLC0415

    if not len(px):
        return []
    flat = Image.fromarray(np.ascontiguousarray(px, np.uint8).reshape(1, -1, 3), "RGB")
    q = flat.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:n * 3]
    counts = sorted(q.getcolors() or [], reverse=True)
    return [{"name": f"sampled {i + 1}", "rgb": pal[idx * 3:idx * 3 + 3]} for i, (_, idx) in enumerate(counts[:n])]


def shade_points(palette_rgb255):
    """every palette colour as the light leaves it -> (K, S, 3) CIELAB: its linear colour times each of SHADES"""
    c = np.clip(np.asarray(palette_rgb255, np.float64).reshape(-1, 3) / 255.0, 0.0, 1.0)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    k = np.asarray(SHADES, np.float64)[None, :, None]
    shaded = np.clip(lin[:, None, :] * k, 0.0, 1.0)
    srgb = np.where(shaded <= 0.0031308, shaded * 12.92, 1.055 * np.power(shaded, 1 / 2.4) - 0.055)
    return rbx_colour.srgb_to_lab(srgb)


def shares(px_rgb255, palette_rgb255):
    """how much of the object each palette colour covers -> (shares (K,), other): every pixel goes to the palette
    colour whose shade it is nearest to (the module's words); one further than FAR from every shade is `other`"""
    px = np.asarray(px_rgb255).reshape(-1, 3)
    k = len(np.asarray(palette_rgb255).reshape(-1, 3))
    if not len(px) or not k:
        return np.zeros(k), (1.0 if len(px) and not k else 0.0)
    pts = shade_points(palette_rgb255)                              # (K, S, 3)
    cost = SHADE_COST * np.abs(np.log(np.asarray(SHADES, np.float64)))   # (S,)
    out = np.zeros(k)
    other = 0
    for s0 in range(0, len(px), 20_000):                            # (in blocks: K x S distances a pixel)
        p = lab(px[s0:s0 + 20_000])
        de = np.linalg.norm(p[:, None, None, :] - pts[None, :, :, :], axis=-1)   # (n, K, S)
        best_s = (de + cost[None, None, :]).argmin(axis=2)          # each colour's best shade for the pixel
        de_k = np.take_along_axis(de, best_s[..., None], axis=2)[..., 0]
        tot_k = de_k + cost[best_s]
        near = tot_k.argmin(axis=1)
        far = de_k[np.arange(len(near)), near] > FAR
        other += int(far.sum())
        out += np.bincount(near[~far], minlength=k)
    return out / len(px), other / len(px)


def roles(rows, measured=True):
    """rows: [{"name", "rgb", "share"}] -> the same rows, largest first (ties by name), each with its "role":
    main | second | accent | minor - or None for every row when the palette is not MEASURED (the module's words).
    A row that is another row's twin (`same_as`) has the role "same"."""
    rows = sorted((dict(r) for r in rows), key=lambda r: (-r["share"], str(r["name"])))
    live = [r for r in rows if not r.get("same_as")]
    for r in rows:
        r["role"] = "same" if r.get("same_as") else None
    if not measured:
        return rows
    if not live or live[0]["share"] <= 0:
        for r in live:
            r["role"] = "minor"
        return rows
    main_lab = lab(live[0]["rgb"])
    for i, r in enumerate(live):
        if i == 0:
            r["role"] = "main"
        elif r["share"] >= SECOND_MIN:
            r["role"] = "second"
        elif 0 < r["share"] < ACCENT_MAX and float(np.linalg.norm(lab(r["rgb"]) - main_lab)) >= ACCENT_APART:
            r["role"] = "accent"
        else:
            r["role"] = "minor"
    return rows


def families(L):
    """the object's THREE VALUE FAMILIES from its pixels' lightness -> {"cuts": [a, b], "dark" / "mid" / "light":
    {"share", "L"}}: three groups by 1-D k-means on L* (started at the ends and the middle of its lightness range,
    the 5th and 95th percentiles: the same every time - started at percentiles of the pixel COUNT two seeds fell on
    one grey whenever one value covered most of the object), so they are the object's OWN dark, middle and light:
    a black gun has three families too. A family no pixel falls in has share 0 and L None (an object of two
    values). An object of ONE flat value is one family: the one its lightness is in on the plain scale (thirds of
    L*) - never "light" because it is all there is."""
    L = np.asarray(L, np.float64)
    names = ("dark", "mid", "light")
    if not len(L):
        return {"cuts": [33.3, 66.7], **{k: {"share": 0.0, "L": None} for k in names}}
    lo, hi = (float(v) for v in np.percentile(L, [5.0, 95.0]))
    if hi - lo < 1.0:
        one = int(np.digitize(float(np.median(L)), [33.3, 66.7]))
        return {"cuts": [33.3, 66.7], **{k: ({"share": 1.0, "L": round(float(L.mean()), 1)} if i == one
                                           else {"share": 0.0, "L": None}) for i, k in enumerate(names)}}
    c = np.array([lo, (lo + hi) / 2, hi], np.float64)
    for _ in range(100):
        cuts = [(c[0] + c[1]) / 2, (c[1] + c[2]) / 2]
        g = np.digitize(L, cuts)
        new = np.array([L[g == k].mean() if (g == k).any() else c[k] for k in range(3)])
        if np.allclose(new, c, atol=0.01):
            break
        c = new
    cuts = [(c[0] + c[1]) / 2, (c[1] + c[2]) / 2]
    g = np.digitize(L, cuts)
    out = {"cuts": [round(float(v), 1) for v in cuts]}
    for k, name in enumerate(names):
        share = float((g == k).mean())
        out[name] = {"share": round(share, 4), "L": round(float(c[k]), 1) if share > 0 else None}
    return out


def three_grey(rgb, mask, fam, ground=(38, 40, 45)):
    """the picture read in THREE GREYS -> an RGB uint8 picture (H, W, 3): every object pixel in the grey of its
    value family (the family's own lightness), the backdrop a plain ground"""
    out = np.empty(rgb.shape, np.uint8)
    out[...] = np.array(ground, np.uint8)
    if not mask.any():
        return out
    g = np.zeros(mask.shape, np.int64)
    g[mask] = np.digitize(lab(rgb[mask])[:, 0], fam["cuts"])
    for k, name in enumerate(("dark", "mid", "light")):
        if fam[name]["L"] is None:
            continue
        v = int(round(_grey_of(fam[name]["L"])))
        out[mask & (g == k)] = (v, v, v)
    return out


def _grey_of(L):
    """the sRGB grey (0..255) whose CIELAB lightness is L"""
    L = float(np.clip(L, 0.0, 100.0))
    f = (L + 16.0) / 116.0
    y = f ** 3 if f > 6 / 29 else 3 * (6 / 29) ** 2 * (f - 4 / 29)
    return 255.0 * (12.92 * y if y <= 0.0031308 else 1.055 * y ** (1 / 2.4) - 0.055)


def lead_of(fam):
    """the value family that covers most of the object -> its name"""
    return max(("dark", "mid", "light"), key=lambda k: fam[k]["share"])


def notes(rows, fam, other, measured=True, unsure=None):
    """what the plan's numbers say, in sentences for the sheet -> [str] (never a refusal: the owner judges)"""
    out = [unsure] if unsure else []
    live = [r for r in rows if not r.get("same_as")]
    if not measured:
        out.append("the colours are SAMPLED from the picture - bands of its shading, not parts: roles need the parts' "
                   "measured colours (lune run kit pack <asset> colours)")
    else:
        main = next((r for r in live if r["role"] == "main"), None)
        if main is None:
            return out + ["no colour of the palette is on the object"]
        if main["share"] < MAIN_LEADS:
            out.append(f"no colour leads: the largest ({main['name']}) covers {main['share']:.0%} of the object")
        if not any(r["role"] == "accent" for r in live):
            out.append("no accent: nothing small stands out from the main colour")
        for r in live:
            if r["role"] in ("second", "accent", "minor") and abs(r["share"] - SECOND_MIN) < EDGE:
                out.append(f"{r['name']} ({r['share']:.1%}) is at the line between an accent and a second colour "
                           f"({SECOND_MIN:.0%}): its role could be either")
        if other > OTHER_SAID:
            out.append(f"{other:.0%} of the object is near none of the palette's colours: the palette misses a colour")
    lit = [k for k in ("dark", "mid", "light") if fam[k]["L"] is not None]
    if lit:
        lead = lead_of(fam)
        spread = fam[lit[-1]]["L"] - fam[lit[0]]["L"]
        if spread < ONE_VALUE:
            out.append(f"it is ONE value: its lightest and darkest families are {spread:.0f} L* apart - its parts "
                       "will separate by hue and gloss alone")
        elif fam[lead]["share"] < FAMILY_LEADS:
            out.append("no value family leads (" + " / ".join(f"{k} {fam[k]['share']:.0%}" for k in
                                                                ("dark", "mid", "light")) + ")")
    if measured:
        big = [r for r in live if r["share"] >= SAME_GREY_FROM]
        pairs = [(a, b) for i, a in enumerate(big) for b in big[i + 1:]
                 if a.get("value") == b.get("value") or abs(a["L"] - b["L"]) < SAME_VALUE]
        for a, b in pairs[:3]:
            out.append(f"{a['name']} and {b['name']} are ONE grey in the three-value read ({abs(a['L'] - b['L']):.0f} "
                       "L* apart): only hue or gloss tells them apart")
    return out


def measure(picture, palette, box=None, polygon=None, holes=(), measured=True):
    """the colour plan of one picture -> (plan, the arrays of read()). plan: {"pixels", "by", "measured", "rows":
    [{"name", "rgb", "share", "role", "L", "value"} + "same_as" for a twin], "other", "values": families(), "leads",
    "notes"}; palette: [{"name", "rgb": [r, g, b] 0..255}] - with palette=None the colours are SAMPLED off the
    object and the plan is not `measured` whatever was asked. EVERY palette colour is a row, largest first: one
    that is not in the picture has share 0, one that is another's twin (closer than SAME_COLOUR) names it."""
    a = read(picture, box, polygon, holes)
    px = a["px"]
    if palette is None:
        palette, measured = sample(px), False
    pal = [p for p in palette if p.get("rgb") is not None and len(p["rgb"]) == 3]
    fam = families(lab(px)[:, 0] if len(px) else [])
    if not len(px) or not pal:
        why = "no object pixels in the picture" if not len(px) else "no palette colours"
        return ({"pixels": int(len(px)), "by": a["by"], "measured": bool(measured), "rows": [], "other": 0.0,
                 "values": fam, "leads": lead_of(fam) if len(px) else None,
                 "notes": ([a["unsure"]] if a["unsure"] else []) + [why]}, a)
    own, twins = [], []
    for p in pal:   # (a colour within SAME_COLOUR of an earlier one is that colour: it keeps its swatch, no share)
        twin = next((q for q, _t in own if float(np.linalg.norm(lab(p["rgb"]) - lab(q["rgb"]))) < SAME_COLOUR), None)
        (twins if twin is not None else own).append((p, twin))
    sh, other = shares(px, [p["rgb"] for p, _t in own])
    rows = [{"name": p["name"], "rgb": [int(v) for v in p["rgb"]], "share": round(float(s), 4)}
            for (p, _t), s in zip(own, sh)]
    rows += [{"name": p["name"], "rgb": [int(v) for v in p["rgb"]], "share": 0.0, "same_as": t["name"]}
             for p, t in twins]
    rows = roles(rows, measured)
    for r in rows:
        r["L"] = round(float(lab(r["rgb"])[0]), 1)
        r["value"] = ("dark", "mid", "light")[int(np.digitize(r["L"], fam["cuts"]))]
    return ({"pixels": int(len(px)), "by": a["by"], "measured": bool(measured), "rows": rows,
             "other": round(float(other), 4), "values": fam, "leads": lead_of(fam),
             "notes": notes(rows, fam, float(other), measured, a["unsure"])}, a)


def plan(picture, palette, box=None, polygon=None, holes=(), measured=True):
    """measure() without the arrays"""
    return measure(picture, palette, box, polygon, holes, measured)[0]


def said(p):
    """a plan in one line, for the sheet's summary: `colours: main body 62%, second grip 21%, accent strip 3%;
    values: dark leads 71%` - on a sampled palette `colours: sampled (no roles); values: ...`"""
    if not p or not p.get("rows"):
        return "colours: none measured"
    if not p.get("measured"):
        head = "colours: sampled (no roles)"
    else:
        parts = [f"{r['role']} {r['name']} {r['share']:.0%}" for r in p["rows"]
                 if r["role"] in ("main", "second", "accent") and r["share"] > 0]
        head = "colours: " + (", ".join(parts) or "none of the palette on the object")
    fam = p["values"]
    return head + f"; values: {p['leads']} leads {fam[p['leads']]['share']:.0%}" + \
        (" (unsure: the picture's ground is not plain)" if any("ground is not plain" in n for n in p["notes"]) else "")
