"""silhouette_holes.py — where a traced view has the object and the model has NOTHING: a hole you can see through.

Why (the owner, 2026-11-11, on single_action_revolver build 4: "is some of the body not fully filled in?"): its side
view matched the photo's trace at IoU 0.936 - a pass at any bar - while a 141 mm2 wedge behind the trigger was open
(the frame's rear edge drawn slanting where the photo's is vertical, the walnut stopping short of it). One global IoU
hides a hole; a hole is found region by region.

    holes(ref, model, mm_per_px, erode_mm=0.75, min_area_mm2=20.0) -> [{"area_mm2", "x_mm", "y_mm"}] largest first
    openings(ref, model, skip=(), mm_per_px=None) -> {"iou", "reference", "model", "filled", "unit"} | None: the other
    way round - the SEE-THROUGH places each outline encloses (a trigger guard's window) compared by themselves (his
    V3 list, 3D stage A.3: cavities; kit fit weighs them)
ref / model: boolean masks on the same grid, row 0 at the BOTTOM (y up) and column 0 at the view's left; a region of
ref & ~model is first eroded by erode_mm (an outline drawn a little inside the photo's along an edge is not a hole) and
counted when what is left still covers min_area_mm2.

    python kit/tools/silhouette_holes.py --ref <ref.png> --model <model.png> --mm-per-px 0.25 [--min-area 20]
    python kit/tools/silhouette_holes.py --ref <ref.png> --model <ref.png> ...   (a view against itself: no hole)
PNG masks: white = the object, row 0 at the TOP as images are; prints one JSON verdict (fail when a hole is found).
"""

import json
import sys

import numpy as np


def _erode(m, n):
    m = m.copy()
    for _ in range(max(0, int(n))):
        m[1:, :] &= m[:-1, :]
        m[:-1, :] &= m[1:, :]
        m[:, 1:] &= m[:, :-1]
        m[:, :-1] &= m[:, 1:]
    return m


def _regions(mask):
    """4-connected regions of a boolean mask -> [(rows, cols)]"""
    seen = np.zeros(mask.shape, bool)
    h, w = mask.shape
    out = []
    for r0, c0 in zip(*np.nonzero(mask)):
        if seen[r0, c0]:
            continue
        stack, rows, cols = [(r0, c0)], [], []
        seen[r0, c0] = True
        while stack:
            r, c = stack.pop()
            rows.append(r)
            cols.append(c)
            for rr, cc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if 0 <= rr < h and 0 <= cc < w and mask[rr, cc] and not seen[rr, cc]:
                    seen[rr, cc] = True
                    stack.append((rr, cc))
        out.append((np.array(rows), np.array(cols)))
    return out


def holes(ref, model, mm_per_px, erode_mm=0.75, min_area_mm2=20.0):
    ref = np.asarray(ref, bool)
    model = np.asarray(model, bool)
    if ref.shape != model.shape:
        raise ValueError(f"silhouette_holes: masks differ in size {ref.shape} vs {model.shape}")
    k = int(round(erode_mm / mm_per_px))
    miss = _erode(ref & ~model, k)
    found = []
    for rows, cols in _regions(miss):
        area = len(rows) * mm_per_px * mm_per_px
        if area < min_area_mm2:
            continue
        found.append({"area_mm2": round(float(area), 1),
                      "x_mm": [round(float(cols.min() * mm_per_px), 1), round(float(cols.max() * mm_per_px), 1)],
                      "y_mm": [round(float(rows.min() * mm_per_px), 1), round(float(rows.max() * mm_per_px), 1)]})
    return sorted(found, key=lambda h: -h["area_mm2"])


def enclosed(mask):
    """the background the mask ENCLOSES (cannot reach the picture's border, 4-connected): its see-through openings"""
    ys, xs = np.nonzero(mask)
    out = np.zeros(mask.shape, bool)
    if not len(xs):
        return out
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub = np.pad(mask[y0:y1, x0:x1], 1)
    outside = np.zeros_like(sub)
    outside[0, :] = outside[-1, :] = outside[:, 0] = outside[:, -1] = True
    outside &= ~sub
    while True:  # grow the outside through the background
        grown = outside.copy()
        grown[1:] |= outside[:-1]
        grown[:-1] |= outside[1:]
        grown[:, 1:] |= outside[:, :-1]
        grown[:, :-1] |= outside[:, 1:]
        grown &= ~sub
        if (grown == outside).all():
            break
        outside = grown
    out[y0:y1, x0:x1] = (~outside & ~sub)[1:-1, 1:-1]
    return out


OPENING_SPECK_PX = 2   # an opening that a 2 px erosion removes (in the 1024 px frame) is edge noise, not a window


def grow(mask, n):
    """the mask grown n px (4-connected)"""
    out = np.asarray(mask, bool).copy()
    for _ in range(max(0, int(n))):
        g = out.copy()
        g[1:] |= out[:-1]
        g[:-1] |= out[1:]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        out = g
    return out


def _speckless(mask, n=OPENING_SPECK_PX):
    """the mask without its specks: eroded n px, grown back n px inside itself (an opening's shape is kept)"""
    out = _erode(mask, n)
    for _ in range(int(n)):
        out = grow(out, 1) & mask
    return out


def openings(ref, model, skip=(), mm_per_px=None):
    """the SEE-THROUGH places each outline encloses (a trigger guard's window, the gap between a guard and the grip,
    a pierced ornament) compared by themselves (his V3 list, 3D stage A.3: cavities) -> {"iou", "reference",
    "model", "filled", "unit"} or None when neither encloses one. One silhouette IoU barely moves when the model closes
    an opening (a 30 mm2 window in a 9000 mm2 side view is 0.3% of it), so a fit never learned to keep one open.
    Only the picture's NAMED openings are compared: a model opening that meets none of them is left out, and with
    none named (or all skipped) the answer is None.
    ref / model: boolean masks on one grid; skip: slices or boolean masks left out of both (the don't-care boxes, a
    part traced "outlines only" whose openings differ on purpose); "filled": the share
    of the picture's openings the model covers solid; areas in mm2 with mm_per_px, else px"""
    ro, mo = enclosed(ref), enclosed(model)
    for sl in skip:
        ro[sl] = mo[sl] = False
    ro, mo = _speckless(ro), _speckless(mo)
    if not ro.any():   # (nothing named is left to compare - all skipped or specks: it says nothing of the model's)
        return None
    # only the model's openings that MEET one the trace names (each grown through the model's own opening): a
    # lightening cut the picture never names is not this measure's business (the review, 2026-11-18)
    keep = mo & grow(ro, OPENING_SPECK_PX)
    while True:
        more = grow(keep, 1) & mo
        if (more == keep).all():
            break
        keep = more
    mo = keep
    area = (mm_per_px ** 2) if mm_per_px else 1.0
    return {"iou": round(float((ro & mo).sum() / (ro | mo).sum()), 3),
            "reference": round(float(ro.sum()) * area, 1), "model": round(float(mo.sum()) * area, 1),
            "filled": round(float((ro & model).sum() / ro.sum()), 3) if ro.any() else 0.0,
            "unit": "mm2" if mm_per_px else "px"}


def said(found):
    return "; ".join(f"{h['area_mm2']:g} mm2 at x {h['x_mm'][0]:g}-{h['x_mm'][1]:g} mm, y {h['y_mm'][0]:g}-"
                     f"{h['y_mm'][1]:g} mm" for h in found[:3])


def _png(path):
    from PIL import Image  # noqa: PLC0415

    return np.asarray(Image.open(path).convert("L"))[::-1] > 127      # (row 0 at the bottom: y up)


def _arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def main(argv):
    ref, model = _png(_arg(argv, "--ref")), _png(_arg(argv, "--model"))
    mmpp = float(_arg(argv, "--mm-per-px", "0.25"))
    found = holes(ref, model, mmpp, float(_arg(argv, "--erode", "0.75")), float(_arg(argv, "--min-area", "20")))
    print(json.dumps({"schema": 1, "status": "fail" if found else "pass",
                      "summary": (f"silhouette_holes: {len(found)} hole(s) the reference has and the model leaves open: "
                                  f"{said(found)}") if found else "silhouette_holes: no hole",
                      "next_action": "fill each named place with the part the picture shows there" if found else "none",
                      "holes": found}))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
