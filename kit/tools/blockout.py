"""kit/tools/blockout.py — `lune run kit blockout <asset>`: the BLOCKOUT sheet, the proportions the owner approves
before any detail, texture or bake is paid for.

Why (the owner, 2026-11-11: "block[out] approval"): a studio signs the big shapes off while changing them costs
seconds. The kit's first picture of a hero piece was a finished, baked build — a wrong proportion was found after
its details were modelled on top of it, and every fix was a full rebuild. `kit blockout` runs the shape round's
build (`kit asset <asset> --geo --blockout`: no bake, no export) and lays what it made out on one page:

    PER TRACED VIEW   the reference's object box | the model in clay from that picture's own camera, at the picture's
                      scale | the build's overlap picture (red: the reference has shape there, blue: the model sticks
                      out) with the overlap number against its bar
    SIX CLAY VIEWS    front, back, left, right, top, three-quarter in ONE matte colour: form, nothing to flatter it
    SCALE             the model beside an R6 character (5 studs tall), and its size in studs

    python kit/tools/blockout.py <asset> [--root <project>] [--build <its build folder>]
                                 -> assets/models/<asset>.blockout.png + .blockout.json
    python kit/tools/blockout.py <asset> --check     is there a blockout, and is it of the model sheet as it is now

The owner's yes: `lune run kit approve 3d <asset> "<their words>" --by owner --stage blockout`. `kit asset` refuses
the baked build of a new complex / hero / aaa piece without it (kit/lib/lanelocks.luau); a shape round stays free.
The approval is of THESE proportions: drawing the blockout again makes a new one that needs his word again, and a
later build whose size moved more than 5% from the approved blockout says so (`blockout_drift`).
Pure python + Pillow; one JSON result line last.
"""

import hashlib
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheet as SH  # noqa: E402  (the model sheet: the views, the drawing helpers)

BLOCKOUT_VERSION = 1
W = SH.W
LOW = 0.75  # a traced view overlapping less than this is called out in red on the sheet (the build's own floor)


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def paths(asset, root):
    base = os.path.join(root, "assets", "models", asset)
    return base + ".blockout.png", base + ".blockout.json"


def blockout_id(sheet_id, meta):
    """16 hex over what the owner is shown: the sheet it is a blockout OF, the script that made it, its size, each
    traced view's overlap"""
    refs = sorted([r.get("view"), r.get("iou")] for r in meta.get("references") or [])
    blob = json.dumps([BLOCKOUT_VERSION, sheet_id, meta.get("script_sha"), meta.get("size"), refs], sort_keys=True,
                      default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def state(asset, root=ROOT):
    """for the locks and kit plan (no drawing): {exists, id, current, stale, problems, notes, png}. A blockout is
    stale when the model sheet it was made against has changed: a new target needs a new blockout. It does NOT go
    stale as the shape is detailed — the owner approved these proportions; the builds watch them (blockout_drift)."""
    png, meta = paths(asset, root)
    kept = None
    if os.path.isfile(meta) and os.path.isfile(png):
        try:
            with open(meta, encoding="utf-8") as fh:
                kept = json.load(fh)
        except (OSError, ValueError):
            kept = None
    exists = isinstance(kept, dict)
    sheet = SH.state(asset, root)
    target = sheet["id"] if sheet["exists"] else None
    return {"exists": exists, "id": (kept or {}).get("id"), "current": (kept or {}).get("id"),
            "stale": bool(exists and kept.get("sheet") != target), "problems": [],
            "notes": (kept or {}).get("notes") or [], "sheet": target,
            "png": os.path.relpath(png, root).replace("\\", "/")}


def geo_meta(asset, build):
    """the shape round's own record (build/judge/<asset>/geo/meta.json) -> (meta, its folder) or (None, why)"""
    folder = os.path.join(build, "judge", asset, "geo")
    try:
        with open(os.path.join(folder, "meta.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        return None, f"no shape round of {asset} has kept its pictures"
    if not isinstance(meta, dict) or not isinstance(meta.get("clay"), dict):
        return None, f"the last shape round of {asset} kept no clay views (it was not a blockout round)"
    return meta, folder


def notes_of(meta, views):
    """what the owner should know on reading the sheet"""
    out = []
    bars = meta.get("bars") or {}
    for r in sorted(meta.get("references") or [], key=lambda x: str(x.get("view"))):
        iou, bar = r.get("iou"), bars.get(r.get("view"))
        if iou is not None and iou < max(LOW, float(bar or 0)):
            out.append(f"the {r.get('view')} view overlaps its reference {iou:.2f}"
                       + (f" (its bar: {float(bar):g})" if bar else "") + ": the outline there is not the reference's yet")
    if not meta.get("references"):
        out.append("no traced view is measured against this model: the overlap rows are missing")
    traced = {v["view"] for v in views}
    for v in sorted(traced - set((meta.get("clay") or {}).get("refs") or {})):
        out.append(f"the {v} view has no plain picture frame: no clay view beside it")
    return out


def overlap_picture(path, view):
    """the build's overlap picture of a traced view, cut to what it shows and turned to lie like the reference: the
    build measures every side / top view with its front on the RIGHT (a trace runs back -> front), so a picture
    whose front is on the left is mirrored back"""
    from PIL import Image, ImageOps  # noqa: PLC0415

    im = SH._open(path)
    box = im.point(lambda p: 255 if p > 24 else 0).convert("L").getbbox()  # (its ground is black)
    if box:
        pad = int(0.04 * max(box[2] - box[0], box[3] - box[1]))
        im = im.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(im.width, box[2] + pad),
                      min(im.height, box[3] + pad)))
    if view.get("front") == "left" and view.get("view") in ("side", "side_left", "top"):
        im = ImageOps.mirror(im)
    return im if im.width and im.height else Image.new("RGB", (8, 8), SH.PANEL)


def draw(asset, meta, folder, views, sheet_id, bid, notes, out_png, tier=None):
    from PIL import Image, ImageDraw  # noqa: PLC0415

    pad, rows = 30, []
    f_title, f_h, f_b, f_s = SH._font(54), SH._font(34), SH._font(26), SH._font(22)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    clay = meta["clay"]
    refs = {r.get("view"): r for r in meta.get("references") or []}
    bars = meta.get("bars") or {}
    cw = (W - pad * 4) // 3

    def title(im, d, y):
        d.text((pad, y + 14), f"BLOCKOUT — {asset}", font=f_title, fill=SH.INK)
        d.text((pad, y + 84), f"{(tier or meta.get('tier') or '').upper()}  ·  the big shapes only: no detail, no "
               "texture, no bake — approve the proportions before any detail is paid for", font=f_b, fill=SH.DIM)
        right = f"blockout {bid}  ·  of sheet {sheet_id or '(none)'}  ·  {time.strftime('%Y-%m-%d')}"
        d.text((W - pad - d.textlength(right, font=f_b), y + 30), right, font=f_b, fill=SH.DIM)
    rows.append((150, title))

    # ---- each traced view: the reference | the model in clay, same camera, same scale | the overlap
    shown = [v for v in views if v["view"] in (clay.get("refs") or {}) and v["file"]]
    for k, v in enumerate(shown):
        pic = SH._open(v["file"])
        box = SH._object_box(v, pic.size)
        ph = max(240, min(700, int(cw * (box[3] - box[1]) / max(1, box[2] - box[0]))))

        def row(im, d, y, v=v, pic=pic, box=box, ph=ph, first=(k == 0)):
            top = y + (56 if first else 0)
            if first:
                d.text((pad, y), "AGAINST THE SHEET — reference | the model in clay, the same camera and scale | "
                       "the overlap", font=f_h, fill=SH.INK)
            tiles = [SH._fit(pic.crop(box), cw, ph)[0]]
            cpath = os.path.join(folder, clay["refs"][v["view"]]["file"])
            tiles.append(SH._fit(Image.open(cpath).convert("RGB"), cw, ph)[0] if os.path.isfile(cpath)
                         else Image.new("RGB", (cw, ph), SH.PANEL))
            r = refs.get(v["view"]) or {}
            dpath = os.path.join(ROOT, str(r.get("diff") or "")) if r.get("diff") else None
            tiles.append(SH._fit(overlap_picture(dpath, v), cw, ph)[0] if dpath and os.path.isfile(dpath)
                         else Image.new("RGB", (cw, ph), SH.PANEL))
            for i, tile in enumerate(tiles):
                im.paste(tile, (pad + i * (cw + pad), top))
            labels = [f"{v['view'].upper()} — the reference", "the model, clay",
                      "overlap ?" if r.get("iou") is None else f"overlap {r['iou']:.2f}"
                      + (f"  (bar {float(bars[v['view']]):g})" if bars.get(v["view"]) else "")]
            low = r.get("iou") is not None and r["iou"] < max(LOW, float(bars.get(v["view"]) or 0))
            for i, text in enumerate(labels):
                d.text((pad + i * (cw + pad) + 6, top + ph + 6), text, font=f_b,
                       fill=(SH.BAD if low else SH.GOOD) if i == 2 and r.get("iou") is not None else SH.DIM)
        rows.append(((56 if k == 0 else 0) + ph + 56, row))

    # ---- the six clay views
    files = [f for f in clay.get("views") or [] if os.path.isfile(os.path.join(folder, f))]
    vh = int(cw * 3 / 4)
    for start in range(0, len(files), 3):
        chunk = files[start:start + 3]

        def six(im, d, y, chunk=chunk, first=(start == 0)):
            top = y + (56 if first else 0)
            if first:
                d.text((pad, y), "SIX VIEWS IN CLAY — form only", font=f_h, fill=SH.INK)
            for i, f in enumerate(chunk):
                tile = SH._fit(Image.open(os.path.join(folder, f)).convert("RGB"), cw, vh)[0]
                im.paste(tile, (pad + i * (cw + pad), top))
                d.text((pad + i * (cw + pad) + 6, top + vh + 4), f[5:-4].replace("_", " ").upper(), font=f_s, fill=SH.DIM)
        rows.append(((56 if start == 0 else 0) + vh + 44, six))

    # ---- scale
    spath = os.path.join(folder, str(clay.get("scale") or ""))
    size = meta.get("size") or []

    def scale(im, d, y):
        d.text((pad, y), "SCALE — beside an R6 character (5 studs tall)", font=f_h, fill=SH.INK)
        if clay.get("scale") and os.path.isfile(spath):
            im.paste(SH._fit(Image.open(spath).convert("RGB"), cw, vh)[0], (pad, y + 56))
        if len(size) == 3:
            lines = [f"width  {size[0]:.2f} studs", f"height {size[1]:.2f} studs", f"length {size[2]:.2f} studs"]
            for i, line in enumerate(lines):
                d.text((pad * 2 + cw, y + 70 + 40 * i), line, font=f_h, fill=SH.INK)
    rows.append((56 + vh + pad, scale))

    foot = [("note: " + n, SH.BAD) for n in notes]
    foot.append((f'the owner\'s yes: lune run kit approve 3d {asset} "<their words>" --by owner --stage blockout',
                 SH.GOOD))
    lines = [(ln, colour) for text, colour in foot for ln in SH._wrap(probe, text, f_s, W - pad * 2)]

    def footer(im, d, y):
        for i, (ln, colour) in enumerate(lines):
            d.text((pad, y + 6 + 30 * i), ln, font=f_s, fill=colour)
    rows.append((30 * len(lines) + 30, footer))

    height = sum(h for h, _ in rows) + pad
    im = Image.new("RGB", (W, height), SH.BG)
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
        return emit("fail", "blockout: needs an asset name", "lune run kit blockout <asset>")
    asset, root = argv[0], ROOT

    def opt(flag):
        if flag not in argv:
            return None
        i = argv.index(flag)
        return argv[i + 1] if i + 1 < len(argv) else ""

    if opt("--root"):
        root = os.path.abspath(opt("--root"))
    if "--check" in argv:
        st = state(asset, root)
        ok = st["exists"] and not st["stale"]
        why = ("no blockout yet" if not st["exists"] else "the model sheet changed since this blockout was made"
               if st["stale"] else "the blockout is of the sheet as it is now")
        return emit("pass" if ok else "fail", f"blockout {asset}: {why}",
                    "none — proceed" if ok else f"lune run kit blockout {asset}", **st)
    build = os.path.abspath(opt("--build")) if opt("--build") else os.path.join(root, os.environ.get("KIT_BUILD", "build"))
    meta, folder = geo_meta(asset, build)
    if meta is None:
        return emit("fail", f"blockout {asset}: {folder}", f"lune run kit blockout {asset}   (it runs the shape round first)")
    data = SH.gather(asset, root)
    sheet = SH.state(asset, root)
    sheet_id = sheet["id"] if sheet["exists"] else None
    bid = blockout_id(sheet_id, meta)
    notes = notes_of(meta, data["views"])
    png, meta_path = paths(asset, root)
    if opt("--out"):
        png = os.path.abspath(opt("--out"))
        meta_path = png[:-4] + ".json"
    rel = png.replace("\\", "/") if opt("--out") else os.path.relpath(png, root).replace("\\", "/")
    size = draw(asset, meta, folder, data["views"], sheet_id, bid, notes, png, data["tier"])
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump({"schema": 1, "asset": asset, "id": bid, "made": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "sheet": sheet_id, "script_sha": meta.get("script_sha"), "size": meta.get("size"),
                   "references": [{k: r.get(k) for k in ("view", "iou")} for r in meta.get("references") or []],
                   "bars": meta.get("bars") or {}, "notes": notes, "picture": list(size)}, fh, indent=1)
    refs = ", ".join(f"{r.get('view')} {r['iou']:.2f}" for r in meta.get("references") or [] if r.get("iou") is not None)
    print(f"blockout {asset}: id {bid} -> {rel} ({size[0]} x {size[1]}); overlap: {refs or 'no traced view measured'}; "
          f"size {' x '.join(f'{v:.2f}' for v in meta.get('size') or [])} studs")
    for n in notes:
        print(f"  note: {n}")
    return emit("pass", f"blockout {asset}: drawn -> {rel}" + (f" ({len(notes)} note(s): {notes[0]})" if notes else ""),
                f'LOOK at {rel} yourself (fix what is off first: a shape round costs seconds), then SHOW it to the '
                f'owner; their yes: lune run kit approve 3d {asset} "<their words>" --by owner --stage blockout',
                id=bid, png=rel, notes=notes, sheet=sheet_id)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
