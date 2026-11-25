"""kit/tools/sheet.py — `lune run kit sheet <asset>`: the MODEL SHEET, the one page the owner approves BEFORE any shape.

Why (the owner, 2026-11-11: "A concept sheet we really need"): a studio's modeller builds from a sheet the art
director signed — the orthographic views, a large callout of every detail that matters, the colours, the scale. The
kit went from a brief straight to a build script, so a hero's wolf head was modelled from a 282 x 125 px crop nobody
had looked at, and the first time the owner saw what was being made was a finished, baked build. The sheet is made
from what the gather stage already has — nothing is drawn by hand:

    VIEWS          every traced view's own picture, cropped to the object, the brief's hero features boxed and numbered
    HERO FEATURES  one large callout per hero feature of the brief (`<feature> | <route> | <what> | <picture>
                   x0,y0,x1,y1 | <size> mm`): its box from its picture, its route, its size, its pixels per mm
    COLOUR PLAN    the colours measured for the pack (kit pack <asset> colours), else sampled from the side picture -
                   each with its SHARE of the object and its ROLE (main / second / accent), and the object read in
                   THREE GREYS: which value family leads, and the notes the numbers earn (kit/tools/colour_plan.py)
    SCALE          the real length against a person, when the pack has a sourced length
    PARTS PLAN     the brief's parts plan: each part's stack of modules, its data, its surface

A sheet with a hero feature that cannot be modelled from its pictures is REFUSED, each one named with its fix: no
picture, no box in it, a picture that is not a file, no size (nor a scaled view to read it from), under 2 px per mm.

    python kit/tools/sheet.py <asset> [--root <project>]   -> assets/models/<asset>.sheet.png + .sheet.json
    python kit/tools/sheet.py <asset> --check              no drawing: is there a sheet, is it still true (its id is a
                                                           hash of everything it shows), has it problems
    python kit/tools/sheet.py <asset> --out <file.png>     draw it somewhere else (a trial: the asset's own sheet
                                                           and its approval are untouched)

The owner's yes is recorded with `lune run kit approve 3d <asset> "<their words>" --by owner --stage sheet`; it holds
for the sheet's id: a sheet that changed needs their word again. `kit asset` refuses a new complex / hero / aaa piece
without it (kit/lib/lanelocks.luau), and every later build pairs these same boxes with the model
(kit/blender/rbx_judgeviews.py). Pure python + Pillow; one JSON result line last.
"""

import hashlib
import json
import os
import re
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
for _p in ("blender", "refs", "tools"):
    sys.path.insert(0, os.path.join(ROOT, "kit", _p))
import numpy as np  # noqa: E402

import colour_plan as CP  # noqa: E402  (the sheet's colour plan: roles, shares, the three-grey read)
import coverage as COV  # noqa: E402  (kit/refs/coverage.py: the brief, the traces, px/mm per feature)
import pack as PK  # noqa: E402
import rbx_judgeviews as JV  # noqa: E402  (where a picture box lies on the model: the rule the builds pair by)
import rbx_plan as P  # noqa: E402

SHEET_VERSION = 1
MIN_PX_PER_MM = P.MIN_PX_PER_MM
NEEDS_APPROVAL = ("complex", "hero", "aaa")  # the tiers whose sheet the owner approves before any build
WANT_VIEWS = {"prop": ("side",), "complex": ("side",), "hero": ("side", "front", "top"), "aaa": ("side", "front", "top")}
PERSON_MM = 1750.0  # the figure the scale row draws beside the object
GREY_GROUND = (24, 62, 78)  # what the three-grey read stands on: a colour, so every grey reads against it
W = 2400  # the sheet's width in pixels
BG, PANEL, INK, DIM, BAD, GOOD, LINE = (22, 23, 26), (38, 40, 45), (236, 236, 232), (150, 152, 158), (255, 96, 88), \
    (120, 214, 140), (255, 196, 64)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def tier_of(brief):
    """the brief's quality answer -> "aaa" | "hero" | "complex" | "prop", or None while it is unanswered / missing
    (kit/lib/lanelocks.luau briefTier reads the same line the same way)"""
    said = str((((brief or {}).get("answers") or {}).get("quality")) or "").lower()
    if not said.strip() or "<answer>" in said:
        return None
    return next((t for t in ("aaa", "hero", "complex") if t in said), "prop")


def resolve_picture(path, root):
    """a picture a brief or a trace names -> its full path, or None: beside the piece's models, under its project,
    under the kit's home, then as given (briefs write all of these; the piece's own folders first, so a path that
    also exists somewhere else never picks the other picture)"""
    if not path:
        return None
    p = str(path)
    for cand in (os.path.join(root, "assets", "models", p), os.path.join(root, p), os.path.join(ROOT, p), p):
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    return None


def _sha_file(path):
    h = hashlib.sha1()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return "missing"
    return h.hexdigest()[:16]


def _hex(colour):
    """a pack colour row's sRGB ("#rrggbb", [r, g, b] 0-255 or 0-1) -> (r, g, b) 0-255, or None"""
    v = colour.get("srgb") if isinstance(colour, dict) else colour
    if isinstance(v, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}", v.strip()):
        s = v.strip().lstrip("#")
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        try:
            nums = [float(x) for x in v[:3]]
        except (TypeError, ValueError):
            return None
        scale = 255.0 if max(nums) <= 1.0 else 1.0
        return tuple(max(0, min(255, int(round(x * scale)))) for x in nums)
    return None


def feature_rows(brief, cov, traces, root, scales=None):
    """each hero feature of the brief as the sheet shows it -> [{rank, name, route, what, picture, file, box,
    size_mm, size_from, px_per_mm, view, problems, notes}]. problems: why nobody can model it from its pictures yet
    (the sheet is refused while one is left); notes: what the owner should know but does not hold the sheet"""
    best = {P._key(f["name"]): f for f in (cov or {}).get("features", [])}
    scales = scales or {}  # (rbx_plan.picture_scales: each traced picture's own px per mm)
    rows = []
    for f in (brief or {}).get("hero_features") or []:
        name = f.get("name") or f"feature {f.get('rank')}"
        row = {"rank": f.get("rank"), "name": name, "route": f.get("route"), "what": f.get("what") or "",
               "picture": f.get("picture"), "file": None, "box": f.get("box"), "size_mm": f.get("size_mm"),
               "size_from": "the brief" if f.get("size_mm") else None, "px_per_mm": None, "view": None,
               "problems": [], "notes": []}
        b = best.get(P._key(name)) or {}
        row["px_per_mm"] = b.get("best_px_per_mm")
        if not f.get("route"):
            row["problems"].append("no route (code / sculpt / generated / relief / projected / procedural)")
        if not f.get("picture"):
            row["problems"].append("no picture: name the picture that shows it and its box there "
                                   "(`<picture> x0,y0,x1,y1`), or ask the owner for one")
        else:
            row["file"] = resolve_picture(f["picture"], root)
            view, t = JV.trace_of_picture(f["picture"], traces)
            if t is not None and not row["file"]:
                row["file"] = resolve_picture(t.get("source"), root)
            row["view"] = view
            if not row["file"]:
                row["problems"].append(f"its picture {f['picture']} is not a file in this project")
            if not f.get("box"):
                row["problems"].append(f"no box in {os.path.basename(str(f['picture']))}: add `x0,y0,x1,y1` (its "
                                       "pixels there) after the picture's name")
            elif row["file"]:
                where = JV.feature_frame(f, traces)
                if "why" in where:  # (a close-up that is not a traced view: fine to model from, never paired)
                    row["notes"].append("builds cannot put the model beside it: " + where["why"].split(": ", 1)[-1])
        if f.get("picture") and f.get("box") and row["px_per_mm"] is None:
            row["problems"].append("no scale: give its size in mm on its line (`30 mm`), or a scaled view "
                                   "(lune run kit refs views)")
        elif row["px_per_mm"] is not None and row["px_per_mm"] < MIN_PX_PER_MM:
            row["problems"].append(f"only {row['px_per_mm']:.1f} px per mm (under {MIN_PX_PER_MM:g}: nobody can "
                                   "model it from this picture) — ask the owner for a close-up")
        if row["size_mm"] is None and f.get("box") and f.get("picture"):
            sc = scales.get(P._norm_path(f["picture"]))
            if sc is None and row["view"] and traces.get(row["view"], {}).get("source"):
                sc = scales.get(P._norm_path(traces[row["view"]]["source"]))
            if sc:
                x0, y0, x1, y1 = f["box"]
                row["size_mm"] = round(max(abs(x1 - x0), abs(y1 - y0)) / sc["px_per_mm"], 1)
                row["size_from"] = f"its box at the {sc['view']} view's scale"
        rows.append(row)
    return rows


def gather(asset, root=ROOT):
    """everything the sheet shows, from the asset's own files"""
    brief, cov, traces = COV.measure(asset, root)
    pack = PK.load(asset, root) if os.path.isfile(PK.pack_path(asset, root)) else {}
    pack = pack if isinstance(pack, dict) else {}  # (a pack edited by hand: the sheet never crashes on it)
    tier = tier_of(brief)
    # each traced picture's own scale (as coverage.measure reads it: refs/<asset>.views.json, the spec's length)
    spec = COV._read(os.path.join(root, "refs", f"{asset}.spec.json"))
    vjson = COV._read(os.path.join(root, (spec or {}).get("views") or f"refs/{asset}.views.json"))
    scales = P.picture_scales(traces, vjson, (spec or {}).get("length_mm"))
    views = []
    for view, t in sorted(traces.items()):
        fr = t.get("frame") if isinstance(t.get("frame"), dict) else None
        views.append({"view": view, "source": t.get("source"), "file": resolve_picture(t.get("source"), root),
                      "frame": fr, "height_ratio": t.get("height_ratio"), "front": t.get("front", "right"),
                      "px_per_mm": (scales.get(P._norm_path(t.get("source") or "")) or {}).get("px_per_mm")})
    obj = pack.get("object") if isinstance(pack.get("object"), dict) else {}
    try:
        length_mm = float(obj.get("length_mm")) if obj.get("length_mm") else None
    except (TypeError, ValueError):
        length_mm = None
    palette = []
    colours = pack.get("colours") if isinstance(pack.get("colours"), dict) else {}
    for part, row in sorted(colours.items()):
        rgb = _hex(row)
        if rgb:
            palette.append({"name": part, "rgb": list(rgb), "how": "measured (kit pack colours)"})
    brief_text = ""
    bp = P.brief_path(asset, root=root)
    if os.path.isfile(bp):
        with open(bp, encoding="utf-8") as fh:
            brief_text = fh.read()
    plan = []
    try:
        import plan as PL  # noqa: PLC0415  (kit/tools/plan.py: the parts plan's reader)

        plan = PL.parts_plan(brief_text) or []
    except Exception:  # noqa: BLE001 — the sheet draws without a parts plan; the brief stage is what demands one
        plan = []
    return {"asset": asset, "root": root, "brief": brief, "tier": tier, "views": views, "traces": traces,
            "features": feature_rows(brief, cov, traces, root, scales), "palette": palette, "length_mm": length_mm,
            "object": obj.get("name"), "parts_plan": plan, "brief_path": bp if brief_text else None}


def problems_of(data):
    """why this sheet cannot be approved yet -> [sentence]; empty = it can be shown to the owner"""
    out = []
    if data["brief"] is None:
        return [f"no brief (assets/models/{data['asset']}.brief.md): lune run kit new asset {data['asset']}"]
    if data["tier"] is None:
        out.append("the brief's quality line is unanswered (prop / complex / hero / aaa): ask the owner")
    if not data["views"]:
        out.append("no traced view: a sheet shows the object's own pictures — lune run kit trace <picture> --name "
                   f"{data['asset']}_side --cutout")
    for v in data["views"]:
        if not v["file"]:
            out.append(f"the {v['view']} view's picture {v['source']} is not a file in this project")
    if data["tier"] in ("hero", "aaa") and not data["features"]:
        out.append("no hero features in the brief (what players notice first: one numbered line each)")
    for r in data["features"]:
        for p in r["problems"]:
            out.append(f"{r['name']}: {p}")
    return out


def notes_of(data):
    out = []
    have = {v["view"] for v in data["views"]}
    lacking = [v for v in WANT_VIEWS.get(data["tier"] or "prop", ("side",)) if v not in have]
    if lacking and data["views"]:
        out.append("no traced " + ", ".join(lacking) + " view: its proportions there will be guessed")
    if not data["palette"]:
        out.append("no measured colours (lune run kit pack <asset> colours): the palette is sampled from the picture")
    if not data["length_mm"]:
        out.append("no sourced real length in the pack: no scale row")
    for r in data["features"]:
        for n in r["notes"]:
            out.append(f"{r['name']}: {n}")
    return out


def colour_view(data):
    """the picture the colours are read on: the side view's, else the first traced one with a file -> the view row"""
    return next((v for v in data["views"] if v["view"] == "side" and v["file"]), None) or \
        next((v for v in data["views"] if v["file"]), None)


def outline_px(trace):
    """a trace's outline and holes in its picture's own pixels -> (polygon, holes) or (None, ()): the outline is
    kept in lengths of the object (u along it with the FRONT at u = 1, v up from its bottom), its frame says where
    that lies in the picture. None for a trace with no plain frame (rotated / straightened)."""
    fr = trace.get("frame") if isinstance(trace.get("frame"), dict) else None
    pts = trace.get("outline")
    if not fr or not {"x0", "y1", "length_px"} <= set(fr) or not isinstance(pts, list) or len(pts) < 3 \
            or float(trace.get("rotate") or 0.0) != 0.0:
        return None, ()
    x0, y1, length = float(fr["x0"]), float(fr["y1"]), float(fr["length_px"])
    front_left = str(trace.get("front", "right")).lower() == "left"

    def to_px(poly):
        return [(x0 + ((1.0 - float(u)) if front_left else float(u)) * length, y1 - float(v) * length)
                for u, v in poly]

    try:
        return to_px(pts), [to_px(h) for h in (trace.get("holes") or []) if len(h) >= 3]
    except (TypeError, ValueError):
        return None, ()


def colour_plan_of(data):
    """THE COLOUR PLAN (kit/tools/colour_plan.py) of what the sheet shows -> (the palette it shows, the plan or None,
    the picture's arrays or None). The palette is the pack's measured colours - then every colour has a role - else
    sampled off the OBJECT's own pixels and said so (no roles: bands of shading are not parts). The object is what
    lies inside the view's traced outline; without a plain frame, inside its box and off the picture's ground.
    Read off what the sheet's id already covers (the picture, its trace, the palette): a sheet approved before the
    plan was drawn is still that sheet - though the plan's own rules (colour_plan.py) are not part of the id."""
    from PIL import Image  # noqa: PLC0415

    view = colour_view(data)
    measured = [dict(c) for c in data["palette"]]
    if not view:
        return measured, None, None
    try:
        polygon, holes = outline_px((data.get("traces") or {}).get(view["view"]) or {})
        with Image.open(view["file"]) as im:
            box = _object_box(view, im.size)
        plan, arrays = CP.measure(view["file"], measured or None, box, polygon, holes, measured=bool(measured))
    except Exception as e:  # noqa: BLE001 — a picture that cannot be read never stops the sheet: it says so
        return measured, {"pixels": 0, "by": None, "measured": bool(measured), "rows": [], "other": 0.0,
                          "values": CP.families([]), "leads": None, "view": view["view"],
                          "palette_from": "measured (kit pack colours)" if measured else "none",
                          "notes": [f"the colours could not be read ({type(e).__name__}: {e})"]}, None
    plan["view"] = view["view"]
    plan["palette_from"] = "measured (kit pack colours)" if measured else f"sampled from the {view['view']} picture"
    shown = measured or [{"name": r["name"], "rgb": r["rgb"], "how": plan["palette_from"]} for r in plan["rows"]]
    return shown, plan, arrays


def sheet_id(data):
    """16 hex over everything the sheet shows: what the piece is and its tier, the brief's features and parts plan,
    every view's picture, frame and scale, the palette, the object's name and length — the owner approves exactly
    this; any change makes an approval stale"""
    views = [[v["view"], v["source"], _sha_file(v["file"]) if v["file"] else None, v["frame"], v["height_ratio"],
              v["front"], v.get("px_per_mm")] for v in data["views"]]
    feats = [[r["rank"], r["name"], r["route"], r["what"], r["picture"], _sha_file(r["file"]) if r["file"] else None,
              r["box"], r["size_mm"]] for r in data["features"]]
    plan = [[p.get("name"), p.get("routes"), p.get("shape"), p.get("data"), p.get("surface")]
            for p in data["parts_plan"]]
    what = (((data["brief"] or {}).get("answers") or {}).get("what") or "").strip()
    blob = json.dumps([SHEET_VERSION, data["tier"], what, views, feats, data["palette"], data.get("object"),
                       data["length_mm"], plan], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def paths(asset, root):
    base = os.path.join(root, "assets", "models", asset)
    return base + ".sheet.png", base + ".sheet.json"


def state(asset, root=ROOT):
    """for the locks and kit plan (no drawing): {exists, id (the kept sheet's), current (what it would be now), stale,
    problems, notes, tier, png}"""
    data = gather(asset, root)
    png, meta = paths(asset, root)
    kept = None
    if os.path.isfile(meta) and os.path.isfile(png):
        try:
            with open(meta, encoding="utf-8") as fh:
                kept = json.load(fh)
        except (OSError, ValueError):
            kept = None
    current = sheet_id(data)
    return {"exists": isinstance(kept, dict), "id": (kept or {}).get("id"), "current": current,
            "stale": isinstance(kept, dict) and kept.get("id") != current, "problems": problems_of(data),
            "notes": notes_of(data), "tier": data["tier"], "png": os.path.relpath(png, root).replace("\\", "/")}


# ---------------------------------------------------------------------------------------------- drawing
def _font(size):
    from PIL import ImageFont  # noqa: PLC0415

    for f in ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(d, text, font, width):
    """text broken into lines no wider than `width` pixels"""
    lines, line = [], ""
    for word in str(text).split():
        trial = (line + " " + word).strip()
        if d.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def _fit(img, w, h):
    """img scaled to fit w x h (never past 4x its own pixels), centred on a panel"""
    from PIL import Image  # noqa: PLC0415

    s = min(w / img.width, h / img.height, 4.0)
    size = (max(1, int(img.width * s)), max(1, int(img.height * s)))
    out = Image.new("RGB", (w, h), PANEL)
    out.paste(img.resize(size, Image.LANCZOS), ((w - size[0]) // 2, (h - size[1]) // 2))
    return out, s, ((w - size[0]) // 2, (h - size[1]) // 2)


def _open(path):
    """a picture on a neutral ground (a cut-out's transparent part is not black)"""
    from PIL import Image  # noqa: PLC0415

    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        rgba = im.convert("RGBA")
        ground = Image.new("RGBA", rgba.size, (*PANEL, 255))
        return Image.alpha_composite(ground, rgba).convert("RGB")
    return im.convert("RGB")


def _object_box(view, size):
    """the traced object's box in its picture (x0, y0, x1, y1) with a 4% margin, kept inside it; the whole picture
    when the trace has no plain frame"""
    fr, hr = view.get("frame"), view.get("height_ratio")
    if not fr or not hr:
        return (0, 0, size[0], size[1])
    x0, y1, length = float(fr["x0"]), float(fr["y1"]), float(fr["length_px"])
    y0, x1 = y1 - float(hr) * length, x0 + length
    pad = 0.04 * max(x1 - x0, y1 - y0)
    return (max(0, int(x0 - pad)), max(0, int(y0 - pad)), min(size[0], int(x1 + pad)), min(size[1], int(y1 + pad)))


def _sample_palette(path, n=6):
    """the picture's n most common colours away from its backdrop (a hint, never a measurement)"""
    from PIL import Image  # noqa: PLC0415

    import numpy as np  # noqa: PLC0415

    im = Image.open(path).convert("RGBA")
    im.thumbnail((256, 256))
    arr = np.asarray(im).reshape(-1, 4).astype(np.int32)
    px = arr[arr[:, 3] > 200][:, :3]
    if not len(px):
        return []
    corner = np.asarray(im.convert("RGB").getpixel((1, 1)), np.int32)
    away = px[np.abs(px - corner).sum(axis=1) > 60]
    px = away if len(away) else px
    flat = Image.fromarray(px.astype(np.uint8).reshape(1, -1, 3), "RGB")
    q = flat.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[:n * 3]
    counts = sorted(q.getcolors() or [], reverse=True)
    return [{"name": f"sampled {i + 1}", "rgb": pal[idx * 3:idx * 3 + 3], "how": "sampled from the side picture"}
            for i, (_, idx) in enumerate(counts[:n])]


def draw(data, problems, notes, sid, out_png):
    """the sheet as one picture -> its size"""
    from PIL import Image, ImageDraw  # noqa: PLC0415

    pad, rows = 30, []  # rows: (height, painter(image, draw, y))
    f_title, f_h, f_b, f_s = _font(54), _font(34), _font(26), _font(22)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))

    # ---- title
    def title(im, d, y):
        d.text((pad, y + 14), f"MODEL SHEET — {data['asset']}", font=f_title, fill=INK)
        what = (((data["brief"] or {}).get("answers") or {}).get("what") or "").strip()
        tier = (data["tier"] or "tier unanswered").upper()
        d.text((pad, y + 84), f"{tier}  ·  {what[:130]}", font=f_b, fill=DIM)
        right = f"sheet {sid}  ·  {time.strftime('%Y-%m-%d')}"
        d.text((W - pad - d.textlength(right, font=f_b), y + 30), right, font=f_b, fill=DIM)
        state_ = "CANNOT BE APPROVED YET: " + str(len(problems)) + " problem(s)" if problems else \
            "to approve: the views, the hero features and the colours below are what gets built"
        d.text((W - pad - d.textlength(state_, font=f_b), y + 84), state_, font=f_b, fill=BAD if problems else GOOD)
    rows.append((150, title))

    # ---- views
    wanted = list(WANT_VIEWS.get(data["tier"] or "prop", ("side",)))
    order = [v for v in ("side", "side_left", "front", "back", "top") if any(x["view"] == v for x in data["views"])]
    order += [v for v in wanted if v not in order]
    order += [x["view"] for x in data["views"] if x["view"] not in order]
    n = max(1, min(4, len(order)))
    vw = (W - pad * (n + 1)) // n
    # the panels are as tall as the tallest view needs at that width (a long gun: a low band; a sword: a tall one)
    vh = 320
    for v in data["views"]:
        if v["file"] and v["view"] in order[:n]:
            with Image.open(v["file"]) as probe_im:
                bx = _object_box(v, probe_im.size)
            vh = max(vh, min(900, int(vw * (bx[3] - bx[1]) / max(1, bx[2] - bx[0]))))

    def views(im, d, y):
        d.text((pad, y), "VIEWS — each traced view's own picture; the numbered boxes are the hero features", font=f_h,
               fill=INK)
        for i, name in enumerate(order[:n]):
            x = pad + i * (vw + pad)
            v = next((q for q in data["views"] if q["view"] == name), None)
            panel = Image.new("RGB", (vw, vh), PANEL)
            if v is None or not v["file"]:
                pd = ImageDraw.Draw(panel)
                msg = f"NO {name.upper()} VIEW TRACED" if v is None else f"{name.upper()}: picture not found"
                pd.text(((vw - pd.textlength(msg, font=f_h)) // 2, vh // 2 - 20), msg, font=f_h, fill=BAD)
            else:
                pic = _open(v["file"])
                box = _object_box(v, pic.size)
                panel, s, (ox, oy) = _fit(pic.crop(box), vw, vh)
                pd = ImageDraw.Draw(panel)
                for r in data["features"]:
                    if r["view"] == name and r["box"] and r["file"] and os.path.normcase(r["file"]) == os.path.normcase(v["file"]):
                        bx0, bx1 = sorted((r["box"][0], r["box"][2]))
                        by0, by1 = sorted((r["box"][1], r["box"][3]))
                        q = (ox + (bx0 - box[0]) * s, oy + (by0 - box[1]) * s, ox + (bx1 - box[0]) * s, oy + (by1 - box[1]) * s)
                        pd.rectangle(q, outline=LINE, width=4)
                        tag = str(r["rank"])
                        tw = pd.textlength(tag, font=f_b) + 16
                        pd.rectangle((q[0], q[1] - 34, q[0] + tw, q[1]), fill=LINE)
                        pd.text((q[0] + 8, q[1] - 34), tag, font=f_b, fill=(20, 20, 20))
                if v.get("px_per_mm"):  # a scale bar: 100 mm (or the largest round length that fits a third of it)
                    mm = next((m for m in (500, 200, 100, 50, 20, 10) if m * v["px_per_mm"] * s <= vw / 3), 10)
                    bar = mm * v["px_per_mm"] * s
                    pd.rectangle((20, vh - 34, 20 + bar, vh - 26), fill=INK)
                    pd.text((28 + bar, vh - 46), f"{mm} mm", font=f_s, fill=INK)
            im.paste(panel, (x, y + 56))
            label = name.replace("_", " ").upper() + ("" if v is None else f"   {os.path.basename(str(v['source']))}")
            d.text((x + 6, y + 56 + vh + 6), label[:70], font=f_s, fill=DIM)
    rows.append((56 + vh + 50, views))

    # ---- hero features: three callouts a row
    cw, ch, per = (W - pad * 4) // 3, 480, 3
    feats = data["features"]
    text_w = cw - 24

    def card_height(r):
        lines = len(_wrap(probe, r["what"], f_s, text_w)[:3])
        lines += len(_wrap(probe, f"{r['rank']}. {r['name']}", f_b, text_w)[:2]) - 1  # (a long name: two lines)
        lines += sum(len(_wrap(probe, "! " + p, f_s, text_w)) for p in r["problems"])
        lines += sum(len(_wrap(probe, "note: " + nn, f_s, text_w)[:2]) for nn in r["notes"][:1])
        return ch + 96 + 30 * lines + 16

    for start in range(0, len(feats), per):
        chunk = feats[start:start + per]
        hh = max(card_height(r) for r in chunk)

        def cards(im, d, y, chunk=chunk, hh=hh, first=(start == 0)):
            if first:
                d.text((pad, y), "HERO FEATURES — what players notice first; every build is judged against these boxes",
                       font=f_h, fill=INK)
            top = y + (56 if first else 0)
            for i, r in enumerate(chunk):
                x = pad + i * (cw + pad)
                d.rectangle((x, top, x + cw, top + hh), fill=PANEL, outline=BAD if r["problems"] else (70, 72, 80), width=3)
                if r["file"] and r["box"]:
                    pic = _open(r["file"])
                    x0, y0, x1, y1 = JV.picture_box(r["box"])
                    crop = pic.crop((max(0, x0), max(0, y0), min(pic.width, x1), min(pic.height, y1)))
                    tile, _, _ = _fit(crop, cw - 6, ch)
                    im.paste(tile, (x + 3, top + 3))
                else:
                    msg = "NO PICTURE" if not r["picture"] else ("PICTURE NOT FOUND" if not r["file"] else "NO BOX")
                    d.text((x + (cw - d.textlength(msg, font=f_h)) // 2, top + ch // 2 - 20), msg, font=f_h, fill=BAD)
                ty = top + ch + 12
                names = _wrap(d, f"{r['rank']}. {r['name']}", f_b, text_w)[:2]
                for k, line in enumerate(names):
                    d.text((x + 12, ty + 34 * k), line, font=f_b, fill=INK)
                ty += 34 * (len(names) - 1)
                size = "size ?" if r["size_mm"] is None else f"{r['size_mm']:g} mm"
                ppm = "px/mm ?" if r["px_per_mm"] is None else f"{r['px_per_mm']:.1f} px/mm"
                low = r["px_per_mm"] is None or r["px_per_mm"] < MIN_PX_PER_MM
                d.text((x + 12, ty + 38), f"{r['route'] or 'NO ROUTE'}  ·  {size}", font=f_s, fill=LINE)
                d.text((x + cw - 12 - d.textlength(ppm, font=f_s), ty + 38), ppm, font=f_s, fill=BAD if low else GOOD)
                ly = ty + 74
                for line in _wrap(d, r["what"], f_s, text_w)[:3]:
                    d.text((x + 12, ly), line, font=f_s, fill=DIM)
                    ly += 30
                for p in r["problems"]:
                    for line in _wrap(d, "! " + p, f_s, text_w):
                        d.text((x + 12, ly), line, font=f_s, fill=BAD)
                        ly += 30
                for nn in r["notes"][:1]:
                    for line in _wrap(d, "note: " + nn, f_s, text_w)[:2]:
                        d.text((x + 12, ly), line, font=f_s, fill=DIM)
                        ly += 30
        rows.append(((56 if start == 0 else 0) + hh + pad, cards))

    # ---- the colour plan: EVERY palette colour with its share and role, the shares as one bar, the object in three
    # greys beside its picture, and what the numbers say
    palette, cplan, carr = data.get("palette_shown"), data.get("colour_plan"), data.get("colour_arrays")
    if palette is None:
        palette, cplan, carr = colour_plan_of(data)
    # (every colour the owner approves is drawn: one that is not in this picture says 0%, a twin names its twin)
    shown = (cplan["rows"] if cplan and cplan["rows"] else
             [{"name": c["name"], "rgb": c["rgb"], "share": None, "role": None} for c in palette])[:9]
    grey_h = 300 if cplan and cplan["rows"] and carr is not None and carr["mask"].any() else 0
    cnotes = [ln for nn in (cplan["notes"] if cplan else []) for ln in _wrap(probe, "note: " + nn, f_s, W - pad * 2)]

    def colours(im, d, y):
        how = (cplan or {}).get("palette_from") or (palette[0].get("how") if palette else None) or "no colours yet"
        d.text((pad, y), "COLOUR PLAN — " + how + (f"; shares read on the {cplan['view']} picture" if grey_h else ""),
               font=f_h, fill=INK)
        sw = min(260, (W - pad * 2) // max(1, len(shown)) - 16)
        for i, c in enumerate(shown):
            x = pad + i * (sw + 16)
            d.rectangle((x, y + 56, x + sw, y + 150), fill=tuple(int(v) for v in c["rgb"]), outline=(90, 92, 100), width=2)
            d.text((x, y + 156), f"{c['name']}"[:22], font=f_s, fill=INK)
            d.text((x, y + 184), "#%02x%02x%02x" % tuple(int(v) for v in c["rgb"]), font=f_s, fill=DIM)
            if c.get("same_as"):
                d.text((x, y + 212), f"= {c['same_as']}"[:22], font=f_s, fill=DIM)
            elif c.get("share") is not None:
                word = (c["role"].upper() + "  ") if c.get("role") else ""
                d.text((x, y + 212), f"{word}{c['share']:.0%}"[:22], font=f_s,
                       fill=GOOD if c.get("role") in ("main", "second") else LINE if c.get("role") == "accent" else DIM)
        ny = y + 250
        if grey_h:
            try:
                ny = values_panel(im, d, y + 256) + 12
            except Exception as e:  # noqa: BLE001 — the read in three greys never stops the sheet
                d.text((pad, y + 256), f"note: the three-grey read could not be drawn ({type(e).__name__})",
                       font=f_s, fill=LINE)
                ny = y + 256 + grey_h + 60
        for ln in cnotes:   # (drawn whether or not there is a read: a plan that could not be made says why HERE)
            d.text((pad, ny), ln, font=f_s, fill=LINE)
            ny += 30

    def values_panel(im, d, by):
        """the shares as ONE bar, then the picture beside itself in three greys and the families' shares -> the
        y under it"""
        from PIL import Image as _Image  # noqa: PLC0415

        x, full = pad, W - pad * 2
        for c in cplan["rows"]:   # (what 60 / 30 / 10 looks like on this object; what is near no colour: hatched)
            w = int(round(full * c["share"]))
            if w > 0:
                d.rectangle((x, by, min(x + w, pad + full), by + 34), fill=tuple(int(v) for v in c["rgb"]))
                x += w
        if x < pad + full:
            d.rectangle((x, by, pad + full, by + 34), fill=PANEL)
            for hx in range(x, pad + full, 12):
                d.line((hx, by + 34, min(hx + 34, pad + full), by), fill=DIM, width=1)
        d.rectangle((pad, by, pad + full, by + 34), outline=(90, 92, 100), width=2)
        rgb, mask = carr["rgb"], carr["mask"]
        ys, xs = np.nonzero(mask)
        crop = (slice(int(ys.min()), int(ys.max()) + 1), slice(int(xs.min()), int(xs.max()) + 1))
        ty, tw, th = by + 60, (W - pad * 3) // 2 - 260, grey_h - 70
        # (the greys on a ground that is no grey: a dark family on the sheet's dark panel could not be seen)
        pair = [_Image.fromarray(np.ascontiguousarray(rgb[crop])),
                _Image.fromarray(CP.three_grey(rgb[crop], mask[crop], cplan["values"], GREY_GROUND))]
        turned = pair[0].height > 1.5 * pair[0].width   # (a tall object lies on its side here: a 20 px sliver
        if turned:                                       # is no squint test)
            pair = [q.transpose(_Image.ROTATE_90) for q in pair]
        for k, q in enumerate(pair):
            thumb, _s, _at = _fit(q, tw, th)             # (a panel tw x th, the picture centred on it)
            im.paste(thumb, (pad + k * (tw + pad), ty))
        fam = cplan["values"]
        tx = pad + 2 * (tw + pad)
        d.text((tx, ty), "VALUES — in three greys" + (" (turned)" if turned else ""), font=f_b, fill=INK)
        for k, name in enumerate(("light", "mid", "dark")):
            if fam[name]["L"] is None:
                d.rectangle((tx, ty + 44 + k * 44, tx + 40, ty + 80 + k * 44), outline=(90, 92, 100))
                d.text((tx + 52, ty + 46 + k * 44), f"{name}: none", font=f_s, fill=DIM)
                continue
            v = int(round(CP._grey_of(fam[name]["L"])))
            d.rectangle((tx, ty + 44 + k * 44, tx + 40, ty + 80 + k * 44), fill=(v, v, v), outline=(90, 92, 100))
            d.text((tx + 52, ty + 46 + k * 44),
                   f"{name} {fam[name]['share']:.0%}" + ("  LEADS" if name == cplan["leads"] else ""),
                   font=f_s, fill=GOOD if name == cplan["leads"] else INK)
        return ty + th
    rows.append((250 + (60 + grey_h if grey_h else 0) + 30 * len(cnotes) + (12 if cnotes else 0), colours))

    # ---- scale
    if data["length_mm"]:
        def scale(im, d, y):
            d.text((pad, y), f"SCALE — real length {data['length_mm']:,.0f} mm"
                   + (f" ({data['object']})" if data["object"] else "") + f", beside a {PERSON_MM / 1000:g} m person",
                   font=f_h, fill=INK)
            unit = min((W - pad * 2 - 200) / max(data["length_mm"], PERSON_MM * 0.3), 150 / PERSON_MM)
            base = y + 56 + 150
            px = pad + 20
            d.rectangle((px + 14, base - PERSON_MM * unit * 0.86, px + 34, base), fill=DIM)  # a person: body, head
            d.ellipse((px + 12, base - PERSON_MM * unit, px + 36, base - PERSON_MM * unit * 0.86), fill=DIM)
            ox = px + 110
            d.rectangle((ox, base - 46, ox + data["length_mm"] * unit, base - 34), fill=LINE)
            d.text((ox, base - 30), f"{data['length_mm']:,.0f} mm", font=f_s, fill=INK)
        rows.append((56 + 150 + 30, scale))

    # ---- parts plan
    plan = data["parts_plan"]
    if plan:
        def parts(im, d, y):
            d.text((pad, y), f"PARTS PLAN — {len(plan)} part(s): how each one gets made", font=f_h, fill=INK)
            ly = y + 56
            for i, p in enumerate(plan[:24]):
                line = f"{i + 1}. {p.get('name', '?')}  |  {p.get('shape', '')}  |  {p.get('data', '')}  |  {p.get('surface', '')}"
                d.text((pad, ly), line[:190], font=f_s, fill=DIM)
                ly += 30
        rows.append((56 + 30 * min(len(plan), 24) + 20, parts))

    # ---- what holds it, what to know, how to approve
    foot = [("! " + p, BAD) for p in problems] + [("note: " + nn, DIM) for nn in notes]
    foot.append((f'the owner\'s yes: lune run kit approve 3d {data["asset"]} "<their words>" --by owner --stage sheet'
                 if not problems else "fix the problems above, then: lune run kit sheet " + data["asset"], GOOD if not problems else BAD))
    lines = [(ln, colour) for text, colour in foot for ln in _wrap(probe, text, f_s, W - pad * 2)]

    def footer(im, d, y):
        ly = y + 6
        for ln, colour in lines:
            d.text((pad, ly), ln, font=f_s, fill=colour)
            ly += 30
    rows.append((30 * len(lines) + 30, footer))

    height = sum(h for h, _ in rows) + pad
    im = Image.new("RGB", (W, height), BG)
    d = ImageDraw.Draw(im)
    y = 0
    for h, paint in rows:
        paint(im, d, y)
        y += h
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    tmp = out_png[:-4] + ".tmp.png"
    im.save(tmp, optimize=True)
    os.replace(tmp, out_png)
    return im.size


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    if not argv or argv[0].startswith("-"):
        return emit("fail", "sheet: needs an asset name", "lune run kit sheet <asset>")
    asset, root = argv[0], ROOT
    if "--root" in argv:
        i = argv.index("--root")
        if i + 1 >= len(argv):
            return emit("fail", "sheet: --root needs a folder", "lune run kit sheet <asset> [--root <project folder>]")
        root = os.path.abspath(argv[i + 1])
    if "--check" in argv:
        st = state(asset, root)
        ok = st["exists"] and not st["stale"] and not st["problems"]
        why = ("no model sheet yet" if not st["exists"] else "the sheet is older than what it shows (the brief, a "
               "picture or a trace changed)" if st["stale"] else f"{len(st['problems'])} problem(s): {st['problems'][0]}"
               if st["problems"] else "the sheet is current")
        return emit("pass" if ok else "fail", f"sheet {asset}: {why}",
                    "none — proceed" if ok else f"lune run kit sheet {asset}", **st)
    data = gather(asset, root)
    problems, notes = problems_of(data), notes_of(data)
    sid = sheet_id(data)
    png, meta = paths(asset, root)
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 >= len(argv) or not argv[i + 1].lower().endswith(".png"):
            return emit("fail", "sheet: --out needs a .png file", f"lune run kit sheet {asset} --out <file.png>")
        png = os.path.abspath(argv[i + 1])
        meta = png[:-4] + ".json"
    rel = os.path.relpath(png, root).replace("\\", "/") if "--out" not in argv else png.replace("\\", "/")
    if data["brief"] is None:
        return emit("fail", f"sheet {asset}: {problems[0]}", f"lune run kit new asset {asset}", problems=problems)
    data["palette_shown"], data["colour_plan"], data["colour_arrays"] = colour_plan_of(data)
    cplan = data["colour_plan"]
    size = draw(data, problems, notes, sid, png)
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump({"schema": 1, "asset": asset, "id": sid, "made": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "tier": data["tier"], "size": list(size), "views": [v["view"] for v in data["views"]],
                   "features": [{k: r[k] for k in ("rank", "name", "route", "picture", "box", "size_mm", "size_from",
                                                   "px_per_mm", "view", "problems", "notes")} for r in data["features"]],
                   "palette": data["palette"], "length_mm": data["length_mm"], "problems": problems, "notes": notes,
                   # (a SAMPLED palette's colours are a picture's content: the record keeps the plan's numbers and
                   # notes, not those colours - a private piece's record names no picture content)
                   "colour_plan": cplan if not cplan or cplan.get("measured") else {**cplan, "rows": []}},
                  fh, indent=1)
    print(f"sheet {asset} — {(data['tier'] or 'tier ?')}: {len(data['views'])} view(s), {len(data['features'])} hero "
          f"feature(s), id {sid} -> {rel} ({size[0]} x {size[1]})")
    for r in data["features"]:
        size_s = "size ?" if r["size_mm"] is None else f"{r['size_mm']:g} mm"
        ppm = "px/mm ?" if r["px_per_mm"] is None else f"{r['px_per_mm']:.1f} px/mm"
        print(f"  {r['rank']}. {r['name'][:44]:<44} {str(r['route'] or 'NO ROUTE'):<10} {size_s:<10} {ppm}")
    for p in problems:
        print(f"  ! {p}")
    for nn in notes:
        print(f"  note: {nn}")
    if cplan:
        print("  " + CP.said(cplan))
        for nn in cplan["notes"]:
            print(f"  colour note: {nn}")
    if problems:
        return emit("fail", f"sheet {asset}: {len(problems)} problem(s) — {problems[0]}",
                    f"fix them in assets/models/{asset}.brief.md (or gather the picture), then lune run kit sheet {asset}",
                    id=sid, png=rel, problems=problems, notes=notes)
    need = data["tier"] in NEEDS_APPROVAL
    return emit("pass", f"sheet {asset}: drawn ({len(data['features'])} hero feature(s), {len(data['views'])} view(s)) "
                f"-> {rel}" + (" · " + CP.said(cplan) if cplan else ""),
                (f'LOOK at {rel} yourself, then SHOW it to the owner; their yes: lune run kit approve 3d {asset} '
                 f'"<their words>" --by owner --stage sheet') if need else f"LOOK at {rel}; a prop needs no approval",
                id=sid, png=rel, problems=[], notes=notes, colour_plan=cplan)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
