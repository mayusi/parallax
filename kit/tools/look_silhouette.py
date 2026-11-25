"""look_silhouette.py — `kit look silhouette`: the build's OUTLINE from one view against the reference's, in mm — so a
part that is too wide, too square or too thin shows as numbers per height, not as a feeling. The build is rendered
ORTHOGRAPHIC (kit/blender/look_ortho.py: front, back, top, bottom, side, left) and laid on the reference's view (a
box of a turnaround sheet) by ONE axis the build is known to have right (--scale-by height, the default: the frame's
up — a front / back view's height, a top / bottom view's LENGTH, the muzzle drawn up; length: across) — never by
both, which would stretch a wrong width into a right one. The reference's view may be turned (a turnaround's top view lies on its side): every quarter turn
and mirror is tried, the best overlap kept. Per row across the scale axis: the reference's width, the build's, their
difference (mm) and which side is off; the overlay shows the reference red, the build cyan, both grey.

    lune run kit look silhouette <asset> --part <word> --picture <path> --box x0,y0,x1,y1 --view front|back|top|bottom
        [--scale-by height|length] [--samples 16] [--mm-per-stud N]

Writes build/renders/<asset>_silhouette_<view>.png + .json; prints one JSON line.
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
EXPORTS = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "models")
RENDERS = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "renders")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _bbox(m):
    import numpy as np  # noqa: PLC0415

    ys, xs = np.nonzero(m)
    return float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)


def orientations(m):
    """the 8 ways a view can lie on a sheet (quarter turns x mirror): (tag, k, flip, mask)"""
    import numpy as np  # noqa: PLC0415

    out = []
    for k in range(4):
        r = np.rot90(m, k)
        out += [(f"rot{90 * k}", k, False, r), (f"rot{90 * k}+mirror", k, True, r[:, ::-1])]
    return out


def align(ref, ren, by="height", ref_body=None, ren_body=None):
    """the render's mask scaled by ONE axis (by="height": the bodies' heights equal, "length": their widths along
    the sheet's x) and centred on the reference's box (pure: test_look_silhouette.py) -> (render mask on the
    reference's grid, scale). ref_body / ren_body: the masks the boxes are taken from (look_details._body: thin
    parts opened away — a sight blade or a lanyard tab one side has and the other's crop cut off would stretch the
    scale ~13%: Scarborough Fair's front view, 2026-10-23); the whole render is what gets moved"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    rx0, ry0, rx1, ry1 = _bbox(ref if ref_body is None else ref_body)
    x0, y0, x1, y1 = _bbox(ren if ren_body is None else ren_body)
    s = (ry1 - ry0) / (y1 - y0) if by == "height" else (rx1 - rx0) / (x1 - x0)
    tx = (rx0 + rx1) / 2 - s * (x0 + x1) / 2
    ty = (ry0 + ry1) / 2 - s * (y0 + y1) / 2
    M = np.float32([[s, 0, tx], [0, s, ty]])
    w = cv2.warpAffine(ren.astype(np.float32), M, (ref.shape[1], ref.shape[0]), flags=cv2.INTER_LINEAR) > 0.5
    return w, s


def rows(ref, built, mm_per_px, by="height", step_mm=2.0):
    """per row across the scale axis (every step_mm): the reference's width, the build's, the difference and which
    edge is off (left / right: the build's edge past or short of the reference's, + = the build wider there)"""
    import numpy as np  # noqa: PLC0415

    a, b = (ref, built) if by == "height" else (ref.T, built.T)
    ys = np.nonzero(a.any(1) | b.any(1))[0]
    if not len(ys):
        return []
    out = []
    step = max(1, int(round(step_mm / mm_per_px)))
    for y in range(int(ys[0]), int(ys[-1]) + 1, step):
        ra, rb = np.nonzero(a[y])[0], np.nonzero(b[y])[0]
        wa = (ra[-1] - ra[0] + 1) * mm_per_px if len(ra) else 0.0
        wb = (rb[-1] - rb[0] + 1) * mm_per_px if len(rb) else 0.0
        left = (ra[0] - rb[0]) * mm_per_px if len(ra) and len(rb) else None    # (+: the build sticks out left)
        right = (rb[-1] - ra[-1]) * mm_per_px if len(ra) and len(rb) else None  # (+: the build sticks out right)
        out.append({"at_mm": round((y - ys[0]) * mm_per_px, 1), "ref_mm": round(wa, 2), "build_mm": round(wb, 2),
                    "diff_mm": round(wb - wa, 2), "left_mm": None if left is None else round(left, 2),
                    "right_mm": None if right is None else round(right, 2)})
    return out


def overlay(ref, built, path):
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    im = np.full(ref.shape + (3,), 18, np.uint8)
    im[ref & ~built] = (230, 60, 60)
    im[built & ~ref] = (60, 210, 230)
    im[ref & built] = (150, 150, 150)
    Image.fromarray(im).save(path)


def arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv):
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    import look  # noqa: PLC0415  (blender())
    import look_details  # noqa: PLC0415  (object_mask, _body)

    need = ("--part", "--picture", "--box", "--view")
    if not argv or argv[0].startswith("--") or any(n not in argv for n in need):
        return emit("fail", "look silhouette: needs <asset> --part <word> --picture <path> --box x0,y0,x1,y1 --view "
                    "front|back|top|bottom|side|left", "lune run kit look silhouette <asset> --part <word> --picture "
                    "<turnaround> --box <the view's box on it> --view front")
    asset, view = argv[0], arg(argv, "--view")
    # (look_ortho draws every view with the asset's long axis or its height UP the frame: a top / bottom view has the
    # muzzle up, so "height" is the length there — the axis the side-view trace already holds right)
    by = arg(argv, "--scale-by", "height")
    blend = os.path.join(EXPORTS, f"{asset}.blend")
    if not os.path.isfile(blend):
        return emit("fail", f"look silhouette: no build of {asset}", f"lune run kit asset {asset}")
    with open(os.path.join(EXPORTS, f"{asset}.manifest.json"), encoding="utf-8") as fh:
        man = json.load(fh)
    bounds = man.get("part_bounds") or {}
    words = [w for w in arg(argv, "--part").split(",") if w]
    hits = [n for n in bounds if any(w.lower() in n.lower() for w in words)]
    if not hits:
        return emit("fail", f"look silhouette: no part of {asset} matches {words}", "parts: " +
                    ", ".join(sorted(bounds)[:20]))
    lo = [min(bounds[n][0][i] for n in hits) for i in range(3)]
    hi = [max(bounds[n][1][i] for n in hits) for i in range(3)]
    x0, y0, x1, y1 = (int(float(v)) for v in arg(argv, "--box").split(","))
    pic = arg(argv, "--picture")
    ref_rgb = np.asarray(Image.open(pic).convert("RGB"))[y0:y1, x0:x1]
    ref_mask, _bg = look_details.object_mask(ref_rgb)
    if ref_mask.sum() < 100:
        return emit("fail", "look silhouette: no object in that box of the picture", "check --box on the picture")
    os.makedirs(RENDERS, exist_ok=True)
    path = os.path.join(RENDERS, f"{asset}_silhouette_{view}_render.png")
    p = subprocess.run([look.blender(), "-b", blend, "-P", os.path.join(REPO, "kit", "blender", "look_ortho.py"), "--",
                        path, ",".join(map(str, lo)), ",".join(map(str, hi)), "--view", view, "--samples",
                        arg(argv, "--samples", "16"), "--clay"], capture_output=True, text=True, timeout=1800)
    said = next((json.loads(ln.split(" ", 1)[1]) for ln in p.stdout.splitlines() if ln.startswith("LOOK_ORTHO ")), None)
    if said is None or not os.path.isfile(path):
        return emit("fail", f"look silhouette: the render failed: {(p.stderr or p.stdout)[-240:]}", "read the error")
    ren = np.asarray(Image.open(path).convert("RGBA"))[..., 3] > 127
    # only the parts' own box: the frame's padding can show a neighbour hanging below it (a chain, a charm)
    ax = {"front": (0, 2), "back": (0, 2), "top": (0, 1), "bottom": (0, 1), "side": (1, 2), "left": (1, 2)}[view]
    ppu = float(said["px_per_unit"])
    cw, ch = (hi[ax[0]] - lo[ax[0]]) * ppu, (hi[ax[1]] - lo[ax[1]]) * ppu
    H_, W_ = ren.shape
    keep = np.zeros_like(ren)
    ya, yb = int(max(0, (H_ - ch) / 2 - 2)), int(min(H_, (H_ + ch) / 2 + 2))
    xa, xb = int(max(0, (W_ - cw) / 2 - 2)), int(min(W_, (W_ + cw) / 2 + 2))
    keep[ya:yb, xa:xb] = True
    ren &= keep
    if ren.sum() < 100:
        return emit("fail", "look silhouette: the render is empty (the --part words framed nothing)", "check --part")
    cads = (man.get("facts") or {}).get("cad") or []
    mm_stud = float(arg(argv, "--mm-per-stud") or (cads[0].get("mm_per_stud") if cads else None) or 280.0)
    ren_mm_px = mm_stud / float(said["px_per_unit"])
    best = None
    ren_b = look_details._body(ren)
    for tag, k, flip, m in orientations(ref_mask):
        body = look_details._body(m)
        w, s = align(body, ren_b, by)
        iou = float((w & body).sum() / max(1, (w | body).sum()))
        if best is None or iou > best[0]:
            best = (iou, tag, m, s, body)
    iou, tag, refm, s, refb = best
    built, _s = align(refm, ren, by, ref_body=refb, ren_body=ren_b)
    mm_px = ren_mm_px / s
    rs = rows(refm, built, mm_px, by)
    off = sorted((r for r in rs if r["ref_mm"] > 0 and r["build_mm"] > 0), key=lambda r: -abs(r["diff_mm"]))
    out = os.path.join(RENDERS, f"{asset}_silhouette_{view}.png")
    overlay(refm, built, out)
    rel = lambda q: os.path.relpath(q, REPO).replace(os.sep, "/")  # noqa: E731
    mean_abs = float(np.mean([abs(r["diff_mm"]) for r in off])) if off else 0.0
    with open(out.replace(".png", ".json"), "w", encoding="utf-8") as fh:
        json.dump({"picture": pic, "box": [x0, y0, x1, y1], "view": view, "scale_by": by, "orientation": tag,
                   "iou": round(iou, 4), "mm_per_ref_px": round(mm_px, 4), "mean_abs_diff_mm": round(mean_abs, 2),
                   "rows": rs}, fh, indent=1)
    worst = ", ".join(f"{r['diff_mm']:+.1f} mm at {r['at_mm']:.0f}" for r in off[:4])
    return emit("pass", f"look silhouette {asset} {view} (the reference {tag}, scaled by its {by}): overlap {iou:.2f}, "
                f"widths off {mean_abs:.2f} mm on average; worst: {worst} (mm from the {'top' if by == 'height' else 'left'})",
                f"LOOK at {rel(out)} (red: the reference only, cyan: the build only) and the rows in "
                f"{rel(out.replace('.png', '.json'))}", overlay=rel(out), iou=round(iou, 4),
                mean_abs_diff_mm=round(mean_abs, 2))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
