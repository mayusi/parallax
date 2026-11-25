"""rectify.py — a PHOTO's trace laid onto a CALIBRATED outline of the same object and view: a maker's turntable hull
(kit refs hull), a measured model's square view (kit refs measure --views), a dimensioned drawing.

A photo carries its camera's perspective: GLOCK 17 Gen 5's 35 px/mm side photo, traced, came out 2.4% too tall
against GLOCK's own sizes, its dust cover 1.9 mm thin and its grip 1.6 mm long against GLOCK's calibrated turntable — and
a model built from it inherited every millimetre. The perspective of a flat-on photo is ONE projective map of the
picture plane: it is found by laying the photo's outline (and its holes) onto the calibrated one (the overlap made as
large as it goes), then taken out of every traced outline, hole, part and curve — the photo keeps its detail, the
calibrated outline gives the proportions.

    python kit/refs/rectify.py <photo trace> --to <calibrated trace> [--name <out>] [--model projective|affine]
        [--level <part>]   (turn the result so that part's top edge is level: the calibrated outline's own tilt — a
                            turntable's pitch of a few tenths of a degree — is not the object's)
    (lune run kit refs rectify ...)
  -> assets/models/<out>.trace.json (default: <photo>_rect): the same trace with every point mapped and renormalised
     (back to front u 0..1, v up from 0); "rectified": {to, model, H, iou_before, iou_after}; the pixel "frame" and the
     "perspective" verdict of the picture are dropped (the picture no longer maps onto it by a frame). Then: kit refs
     profiles <out> --anchor <part> --length-mm <its published length> gives its millimetre profiles.
Both traces must be the same VIEW of the same object (back to front, bottom at v = 0). A map that moves the outline
by more than a few percent is said (a wrong pairing, not a perspective). One JSON verdict line last.
"""

import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
MAX_MOVE = 0.06  # a perspective moves an outline point by a few percent of the length; more is a wrong pairing


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra},
                     ensure_ascii=True))
    return 0 if status == "pass" else 1


def _path(name, root=None):
    root = root or ROOT
    if name.endswith(".trace.json") or os.path.isfile(name):
        return name if os.path.isabs(name) else os.path.join(root, name)
    return os.path.join(root, "assets", "models", f"{name}.trace.json")


def _arg(argv, key, default=None):
    return argv[argv.index(key) + 1] if key in argv and argv.index(key) + 1 < len(argv) else default


def mask(outline, holes, hr, px):
    """the outline (filled) less its holes, (u, v) in the frame u 0..1, v 0..hr (v up) -> bool picture px wide"""
    w, h = px + 2, int(np.ceil(hr * px)) + 3
    img = Image.new("1", (w, h), 0)
    dr = ImageDraw.Draw(img)

    def pix(ring):
        return [(1 + float(u) * (px - 1), 1 + (hr - float(v)) * (px - 1)) for u, v in ring]
    if len(outline) >= 3:
        dr.polygon(pix(outline), fill=1)
    for ring in holes or []:
        if len(ring) >= 3:
            dr.polygon(pix(ring), fill=0)
    return np.asarray(img, dtype=bool)


def to_h(p, model="projective"):
    a, b, c, d, e, f = p[:6]
    g, k = (p[6], p[7]) if model == "projective" else (0.0, 0.0)
    return np.array([[1 + a, b, c], [d, 1 + e, f], [g, k, 1.0]])


def apply(H, pts):
    """projective map of (u, v) points -> (u', v')"""
    P = np.asarray(pts, dtype=float).reshape(-1, 2)
    q = np.c_[P, np.ones(len(P))] @ H.T
    return q[:, :2] / q[:, 2:3]


def iou(a, b):
    hh, ww = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    a_, b_ = a[:hh, :ww], b[:hh, :ww]
    u = np.logical_or(a_, b_).sum() + (a.sum() - a_.sum()) + (b.sum() - b_.sum())
    return float(np.logical_and(a_, b_).sum() / u) if u else 0.0


def _dense(rings, step=0.002):
    """points every `step` along closed rings (u, v)"""
    out = []
    for r in rings:
        r = np.asarray(r, float)
        if len(r) < 2:
            continue
        for a_, b_ in zip(r, np.roll(r, -1, 0)):
            n_ = max(1, int(np.ceil(np.hypot(*(b_ - a_)) / step)))
            out.append(a_ + (b_ - a_) * (np.arange(n_)[:, None] / n_))
    return np.concatenate(out) if out else np.zeros((0, 2))


CAP = 0.01  # (an edge further than 1% of the length from the other outline is a DIFFERENCE — a sight, a lever — not
#            a perspective: it may not pull the map)


def fit(photo, ref, model="projective", log=None):
    """-> (H, iou_before, iou_after): the projective (or affine) map taking the photo trace's (u, v) onto the reference
    trace's frame — first by the filled outlines' overlap (holes cut), then edge to edge (each outline's points to the
    other's nearest, both ways, each distance capped at CAP: a real difference cannot pull it)"""
    from scipy.optimize import minimize  # noqa: PLC0415
    from scipy.spatial import cKDTree  # noqa: PLC0415

    hr = float(ref.get("height_ratio") or max(v for _u, v in ref["outline"]))
    out, holes = np.asarray(photo["outline"], float), [np.asarray(r, float) for r in photo.get("holes") or []]
    n = 8 if model == "projective" else 6
    p = np.zeros(n)

    def ok(q):
        return not (model == "projective" and (abs(q[6]) > 0.5 or abs(q[7]) > 0.5))

    def overlap(q, ref_m, px):
        try:
            return iou(mask(apply(to_h(q, model), out), [apply(to_h(q, model), r) for r in holes], hr, px), ref_m)
        except (ValueError, OverflowError):
            return 0.0
    ref_lo = mask(ref["outline"], ref.get("holes"), hr, 300)
    before_lo = overlap(p, ref_lo, 300)
    res = minimize(lambda q: 2.0 if not ok(q) else 1.0 - overlap(q, ref_lo, 300), p, method="Powell",
                   options={"xtol": 1e-5, "ftol": 1e-6, "maxfev": 3000})
    p = res.x
    if log:
        log(f"rectify, by overlap (300 px): IoU {before_lo:.4f} -> {1.0 - res.fun:.4f}")
    # edge to edge
    ref_pts = _dense([ref["outline"]] + list(ref.get("holes") or []))
    pho_pts = _dense([out] + holes)
    ref_tree = cKDTree(ref_pts)

    def edges(q):
        if not ok(q):
            return 1.0
        try:
            m_ = apply(to_h(q, model), pho_pts)
        except (ValueError, OverflowError):
            return 1.0
        if not np.isfinite(m_).all():
            return 1.0
        d1 = np.minimum(ref_tree.query(m_)[0], CAP)
        d2 = np.minimum(cKDTree(m_).query(ref_pts)[0], CAP)
        return float(np.mean(d1 * d1) + np.mean(d2 * d2))
    for _ in range(3):
        res = minimize(edges, p, method="Powell", options={"xtol": 1e-7, "ftol": 1e-10, "maxfev": 6000})
        if np.allclose(res.x, p, atol=1e-7):
            break
        p = res.x
    ref_hi = mask(ref["outline"], ref.get("holes"), hr, 900)
    before, after = overlap(np.zeros(n), ref_hi, 900), overlap(p, ref_hi, 900)
    if log:
        log(f"rectify, edge to edge: IoU (900 px) {before:.4f} -> {after:.4f}")
    return to_h(p, model), before, after


def _map_any(H, obj):
    """every [u, v] pair inside a trace's geometry (rings, part dicts, curve segments) mapped"""
    if isinstance(obj, dict):
        return {k: _map_any(H, v) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) == 2 and all(isinstance(x, (int, float)) for x in obj):
            q = apply(H, [obj])[0]
            return [float(q[0]), float(q[1])]
        return [_map_any(H, x) for x in obj]
    return obj


def _renorm(obj, u0, v0, scale):
    if isinstance(obj, dict):
        return {k: _renorm(v, u0, v0, scale) for k, v in obj.items()}
    if isinstance(obj, list):
        if len(obj) == 2 and all(isinstance(x, (int, float)) for x in obj):
            return [round((obj[0] - u0) / scale, 6), round((obj[1] - v0) / scale, 6)]
        return [_renorm(x, u0, v0, scale) for x in obj]
    return obj


def level_angle(part):
    """the slope (radians) of a part's TOP edge (its middle 80%: the highest point in each 1% of its length) — a slide's
    top flat, a receiver's top"""
    p_ = np.asarray(part, float)
    u0, u1 = p_[:, 0].min(), p_[:, 0].max()
    us, vs = [], []
    for k in range(10, 90):
        a_, b_ = u0 + (u1 - u0) * k / 100, u0 + (u1 - u0) * (k + 1) / 100
        sel = (p_[:, 0] >= a_) & (p_[:, 0] < b_)
        if sel.any():
            us.append((a_ + b_) / 2)
            vs.append(p_[sel, 1].max())
    if len(us) < 5:
        return 0.0
    # (a robust line: the median of the top edge's heights; points more than 0.3% under it are a notch, a sight base)
    us, vs = np.asarray(us), np.asarray(vs)
    keep = vs >= np.median(vs) - 0.003
    k_, _c = np.polyfit(us[keep], vs[keep], 1)
    return float(np.arctan(k_))


def rectify(photo, ref, model="projective", log=None, level=None):
    """-> (the rectified trace dict, report). level=<part>: the result turned so that part's top edge is level (the
    calibrated outline's own small tilt — a turntable's pitch — is not the object's)"""
    H, before, after = fit(photo, ref, model, log)
    deg = 0.0
    if level:
        if level not in (photo.get("parts") or {}):
            raise ValueError(f"--level {level}: no such traced part ({', '.join(photo.get('parts') or {}) or 'none'})")
        th = -level_angle(apply(H, photo["parts"][level]))
        c_, s_ = np.cos(th), np.sin(th)
        H = np.array([[c_, -s_, 0.0], [s_, c_, 0.0], [0.0, 0.0, 1.0]]) @ H
        deg = float(np.degrees(th))
    out = apply(H, photo["outline"])
    moved = float(np.abs(out - np.asarray(photo["outline"], float)).max())
    u0, u1 = float(out[:, 0].min()), float(out[:, 0].max())
    v0, v1 = float(out[:, 1].min()), float(out[:, 1].max())
    scale = u1 - u0
    t = {k: v for k, v in photo.items() if k not in ("frame", "perspective")}
    for key in ("outline", "holes", "parts", "curves"):
        if key in photo:
            t[key] = _renorm(_map_any(H, photo[key]), u0, v0, scale) if key != "curves" else {
                k: (_renorm(_map_any(H, v), u0, v0, scale) if k != "tolerance_px" else v)
                for k, v in photo["curves"].items()}
    t["height_ratio"] = round((v1 - v0) / scale, 6)
    rep = {"model": model, "H": [[round(float(x), 8) for x in row] for row in H], "iou_before": round(before, 4),
           "iou_after": round(after, 4), "max_move": round(moved, 4), "renorm": [u0, v0, scale],
           **({"level": {"part": level, "turned_deg": round(deg, 4)}} if level else {})}
    return t, rep


def main(argv):
    if not argv or argv[0].startswith("-") or not _arg(argv, "--to"):
        return emit("fail", "refs rectify: needs the photo's trace and --to <the calibrated trace of the same view>",
                    "lune run kit refs rectify <photo trace> --to <hull / model view / drawing trace>")
    src, ref_p = _path(argv[0]), _path(_arg(argv, "--to"))
    for p_ in (src, ref_p):
        if not os.path.isfile(p_):
            return emit("fail", f"refs rectify: no trace {p_}", "lune run kit trace <picture> --name <name>")
    model = _arg(argv, "--model", "projective")
    if model not in ("projective", "affine"):
        return emit("fail", f"refs rectify: --model {model}: projective | affine", "--model projective")
    with open(src, encoding="utf-8") as fh:
        photo = json.load(fh)
    with open(ref_p, encoding="utf-8") as fh:
        ref = json.load(fh)
    name = _arg(argv, "--name", os.path.basename(src)[:-len(".trace.json")] + "_rect")
    try:
        t, rep = rectify(photo, ref, model, log=lambda s: print(s, file=sys.stderr), level=_arg(argv, "--level"))
    except ValueError as e:
        return emit("fail", f"refs rectify: {e}", "--level <a traced part with a straight top: slide, receiver>")
    t["name"] = name
    t["rectified"] = {"from": os.path.relpath(src, ROOT).replace("\\", "/"),
                      "to": os.path.relpath(ref_p, ROOT).replace("\\", "/"), **rep}
    if rep["max_move"] > MAX_MOVE:
        return emit("fail", f"refs rectify {name}: the map moves the outline {rep['max_move']:.1%} of its length — "
                    "more than a perspective does (another object or view, or another pose?)",
                    "check that both traces show the same view of the same object, back to front", **rep)
    out = os.path.join(ROOT, "assets", "models", f"{name}.trace.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(t, fh)
    return emit("pass", f"refs rectify {name}: the photo's outline on the calibrated one IoU {rep['iou_before']:.3f} "
                f"-> {rep['iou_after']:.3f} ({model}, the outline moved up to {rep['max_move']:.1%} of its length) -> "
                f"{os.path.relpath(out, ROOT)}",
                f"lune run kit refs profiles {name} --anchor <part> --length-mm <its published length>; build from "
                f"the rectified profiles and match a.trace_match('{name}', ...)", trace=os.path.relpath(out, ROOT), **rep)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
