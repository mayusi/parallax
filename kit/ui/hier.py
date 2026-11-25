"""hier.py — the SQUINT TEST: does the screen's focus still win when the detail is gone? Designers squint (or blur) at a
layout to see its hierarchy; a judge model cannot fake this, it is measured.

    squint(frame, boxes, focus, n=3) -> (rank, ranking)   rank: the focus's place among the strongest regions (1 = wins)

frame: the desktop preview (PIL); boxes: {path: (x, y, w, h)}; focus: the spec's focus path (root-relative). The frame
is blurred by ~1% of its width (a squint), then every visible region is scored by how much it stands out from the
ring around it (its mean luminance against the ring's, plus its own contrast), weighted by its size. The focus's own
ancestors and descendants do not compete with it. A focus outside the top n warns: the eye lands elsewhere first.
"""
import numpy as np
from PIL import ImageFilter

SKIP = ("Shadow", "Plate", "Glow", "Gradient", "Band", "Grow", "KitPath", "KitPathOutline", "Field", "Ground", "Rays")


def _lum(img):
    a = np.asarray(img.convert("RGB"), dtype=np.float64) / 255.0
    a = np.where(a <= 0.03928, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def squint(frame, boxes, focus, n=3):
    W, H = frame.size
    blurred = frame.convert("RGB").filter(ImageFilter.GaussianBlur(max(2, W * 0.01)))
    L = _lum(blurred)
    area_all = float(W * H)
    scores = []
    for path, (x, y, w, h) in boxes.items():
        name = path.rsplit(".", 1)[-1]
        if name.startswith("Fx_") or name in SKIP:
            continue
        a = w * h / area_all
        if a < 0.001 or a > 0.25:
            continue
        x0, y0, x1, y1 = int(max(0, x)), int(max(0, y)), int(min(W, x + w)), int(min(H, y + h))
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        pad = int(max(8, 0.25 * max(w, h)))
        rx0, ry0, rx1, ry1 = max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad), min(H, y1 + pad)
        inner = L[y0:y1, x0:x1]
        outer = L[ry0:ry1, rx0:rx1]
        ring_sum = outer.sum() - inner.sum()
        ring_n = outer.size - inner.size
        if ring_n <= 0:
            continue
        ring_mean = ring_sum / ring_n
        score = (abs(inner.mean() - ring_mean) + 0.5 * inner.std()) * min(1.0, a / 0.02) ** 0.5
        scores.append((score, path))
    scores.sort(reverse=True)
    if not focus:
        return None, scores

    def related(p):
        return p == focus or p.startswith(focus + ".") or focus.startswith(p + ".")

    # a competitor counts ONCE: a region nested in (or holding) one already counted is the same thing to the eye
    counted = []
    for s, p in scores:
        if related(p):
            return len(counted) + 1, scores
        if not any(p == q or p.startswith(q + ".") or q.startswith(p + ".") for q in counted):
            counted.append(p)
    return None, scores
