"""style.py — how close a model's LOOK and SILHOUETTE are to the STYLE it declares: rbx.Asset(style=[images]) —
pictures of OTHER objects in the wanted style (the kit's own starters, a CC0 pack, concept art), never of the object
itself (that is a reference):

    python kit/vision/style.py build/models/<asset>.manifest.json

  - look (SigLIP 2): the cosine of the model's hero view to each style image (mean, nearest three) — and of its bare
    outline in flat grey, so the report says how much the model's SURFACE carries the style beyond its shape;
  - silhouette: solidity (outline area / its convex hull: chunky or spindly), fill (outline area / its box) and aspect
    (long side / short side) of the model's cut-out against the style images' cut-outs (BiRefNet): where the model
    falls in the range the style's own objects span — measured on the model's view CLOSEST to the style's (a style
    photo is shot from any angle; the sheet has the hero and back 3/4 views and the orthographic front, side, top).
-> build/renders/<asset>_style.png (the model, its flat outline, its nearest style images) + one JSON line.
A REPORT, never a gate: a style is a direction, not a score (reference-free looks were measured NOT to track the owner;
similarity to a declared target is what SigLIP is good at).
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
MARGIN = 0.1  # a silhouette measure this far outside the range the style's images span is named
SHAPES = ("solidity", "fill", "aspect")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def hull_area(points):
    """area of the convex hull of (x, y) points (Andrew's monotone chain + the shoelace formula)"""
    pts = sorted(set(map(tuple, np.asarray(points, float).tolist())))
    if len(pts) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    n = len(hull)
    return 0.5 * abs(sum(hull[i][0] * hull[(i + 1) % n][1] - hull[(i + 1) % n][0] * hull[i][1] for i in range(n)))


def shape(mask):
    """the silhouette measures of a 0..1 mask (> 0.5 = the object) -> {solidity, fill, aspect}, or None (no object)"""
    m = np.asarray(mask) > 0.5
    if int(m.sum()) < 50:
        return None
    ys, xs = np.nonzero(m)
    h, w = int(ys.max() - ys.min() + 1), int(xs.max() - xs.min() + 1)
    order = np.lexsort((xs, ys))  # each row's outermost pixels (their outer corners) carry the hull
    ys_s, xs_s = ys[order], xs[order]
    first = np.r_[True, ys_s[1:] != ys_s[:-1]]
    last = np.r_[ys_s[1:] != ys_s[:-1], True]
    left = np.stack([xs_s[first], ys_s[first]], 1)
    right = np.stack([xs_s[last] + 1, ys_s[last]], 1)
    corners = np.concatenate([left, left + [0, 1], right, right + [0, 1]])
    area = float(m.sum())
    return {"solidity": round(area / max(hull_area(corners), area), 3), "fill": round(area / (w * h), 3),
            "aspect": round(max(w, h) / min(w, h), 3)}


def outside(model, refs, margin=MARGIN):
    """the silhouette measures of `model` outside the range `refs` span (widened by `margin` of the range's middle)
    -> [(measure, value, lo, hi)]"""
    out = []
    refs = [r for r in refs if r]
    if not model or not refs:
        return out
    for k in SHAPES:
        vals = [r[k] for r in refs]
        lo, hi = min(vals), max(vals)
        pad = margin * (lo + hi) / 2
        if model[k] < lo - pad or model[k] > hi + pad:
            out.append((k, model[k], lo, hi))
    return out


VIEWS = {0: "hero", 1: "back three-quarter", 3: "front", 4: "side", 5: "top"}  # sheet tiles (2: with the R6 figure)


def sheet_views(sheet_path):
    """the build sheet's views -> {name: tile} (3 columns x 2 rows of equal tiles: hero, back 3/4, with R6 / front,
    side, top — the tile with the R6 figure is left out: the figure is not the model)"""
    img = Image.open(sheet_path).convert("RGB")
    w, h = img.width // 3, img.height // 2
    return {name: img.crop(((i % 3) * w, (i // 3) * h, (i % 3 + 1) * w, (i // 3 + 1) * h)) for i, name in VIEWS.items()}


def hero_view(sheet_path):
    """the hero (3/4) tile of a build's render sheet — the view the judge packets and the owner's anchors show"""
    return sheet_views(sheet_path)["hero"]


def closest(shapes, refs):
    """the view whose silhouette sits closest to the middle of the style's range -> (name, shape), or (None, None).
    Each measure's distance is counted in units of the range's half-width (+5% of its middle, so a single style image
    still has a width)"""
    refs = [r for r in refs if r]
    best = (None, None, float("inf"))
    for name, sh in shapes.items():
        if not sh or not refs:
            continue
        d = 0.0
        for k in SHAPES:
            vals = [r[k] for r in refs]
            lo, hi = min(vals), max(vals)
            mid, half = (lo + hi) / 2, (hi - lo) / 2 + 0.05 * abs((lo + hi) / 2)
            d += abs(sh[k] - mid) / max(half, 1e-6)
        if d < best[2]:
            best = (name, sh, d)
    return best[0], best[1]


def _tile(img, h):
    s = h / img.height
    return img.resize((max(1, int(img.width * s)), h), Image.LANCZOS)


def main(argv):
    if not argv or not os.path.isfile(argv[0]):
        return emit("fail", "style: needs a build manifest", "python kit/vision/style.py build/models/<asset>.manifest.json")
    with open(argv[0], encoding="utf-8") as fh:
        manifest = json.load(fh)
    asset = manifest.get("asset", "?")
    refs = (manifest.get("facts") or {}).get("style_refs") or []
    if not refs:
        return emit("pass", f"style: {asset} declares no style", "declare one: rbx.Asset(..., style=[\"refs/style/x.png\"])")
    sheet = os.path.join(REPO, "build", "renders", f"{asset}.png")
    if not os.path.isfile(sheet):
        return emit("pass", f"style: skipped — {asset} has no render sheet (a --geo build)", "a full build renders it")
    paths = [r if os.path.isabs(r) else os.path.join(REPO, r) for r in refs]
    missing = [r for r, p in zip(refs, paths) if not os.path.isfile(p)]
    if missing:
        return emit("fail", f"style: {asset}'s style images are missing: {', '.join(missing)}",
                    "put them where the asset says (refs/style/...), or fix the paths in Asset(style=[...])")
    sys.path.insert(0, HERE)
    import run as V  # noqa: E402  (the vetted models, offline: only when there is something to look at)

    views = sheet_views(sheet)
    hero = views["hero"]
    masks = {name: V.cutout(img) for name, img in views.items()}
    m_mask = masks["hero"]
    flat = np.full((hero.height, hero.width, 3), 255, np.uint8)
    flat[m_mask > 0.5] = 128  # the bare outline in flat grey: the look with no surface at all
    imgs = [V._rgb(p) for p in paths]
    e = V.embed([hero, Image.fromarray(flat)] + imgs)
    sims, sims_flat = e[2:] @ e[0], e[2:] @ e[1]
    ref_shapes = [shape(V.cutout(im)) for im in imgs]
    view, model_shape = closest({name: shape(m) for name, m in masks.items()}, ref_shapes)
    off = outside(model_shape, ref_shapes)
    nearest = [int(i) for i in np.argsort(sims)[::-1][:3]]
    h = 300
    tiles = [(_tile(hero, h), "model"), (_tile(Image.fromarray(flat), h), "its bare outline")] + [
        (_tile(imgs[i], h), f"style {os.path.basename(refs[i])} {sims[i]:.2f}") for i in nearest]
    sheet_img = Image.new("RGB", (sum(t.width for t, _l in tiles) + 8 * len(tiles), h + 22), "white")
    x = 0
    for t, label in tiles:
        sheet_img.paste(t, (x, 22))
        ImageDraw.Draw(sheet_img).text((x + 4, 4), label, fill=(0, 0, 0))
        x += t.width + 8
    out = os.path.join(REPO, "build", "renders", f"{asset}_style.png")
    sheet_img.save(out)
    mean, mean_flat = float(sims.mean()), float(sims_flat.mean())
    ranges = {k: [min(r[k] for r in ref_shapes if r), max(r[k] for r in ref_shapes if r)]
              for k in SHAPES if any(ref_shapes)}
    said = "; ".join(f"{k} {v:.2f} (style {lo:.2f}-{hi:.2f})" for k, v, lo, hi in off)
    summary = (f"style: {asset} looks {mean:.2f} like its {len(refs)} style image(s) (nearest {sims[nearest[0]]:.2f}: "
               f"{os.path.basename(refs[nearest[0]])}); its bare outline alone {mean_flat:.2f} — the surface adds "
               f"{mean - mean_flat:+.2f}; silhouette (its {view} view, the closest to the style's) "
               + ("inside the style's range" if not off else f"OUTSIDE: {said}"))
    return emit("pass", summary,
                f"look at {os.path.relpath(out, REPO)}" + (f" — the outline leaves the style ({', '.join(k for k, *_ in off)})"
                                                          if off else ""),
                style={"asset": asset, "similarity": round(mean, 4), "outline_similarity": round(mean_flat, 4),
                       "surface_gain": round(mean - mean_flat, 4),
                       "nearest": [{"image": refs[i], "similarity": round(float(sims[i]), 4)} for i in nearest],
                       "silhouette": model_shape, "silhouette_view": view, "style_range": ranges,
                       "outside": [{"measure": k, "value": v, "lo": lo, "hi": hi} for k, v, lo, hi in off],
                       "image": os.path.relpath(out, REPO).replace(os.sep, "/")})


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
