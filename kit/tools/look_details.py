"""look_details.py — `kit look details`: every DETAIL of the shot list (kit refs inventory) side by side — the
reference's crop beside the SAME crop of the build — so a wrong gem surround, a square edge or a missing screw shows
in seconds, not after the owner finds it. The build is rendered ORTHOGRAPHIC from the reference's side
(kit/blender/look_ortho.py), registered onto the picture by its silhouette (scale + shift, mirrored if that fits
better), and cropped where each detail is. Two numbers per detail only POINT at what to look at first (never a score
to chase): `alike` (structural similarity, 0..1) and `edges` (the build's fine-edge share over the reference's: over
1.3 = the build's edges are sharper / squarer than the art, under 0.75 = softer / blurred).

    lune run kit look details <asset> --part <word> [--picture <path>] [--details <file>] [--view side|left]
        [--samples 48]

Writes build/renders/<asset>_details.png (worst first) + .json; prints one JSON line.
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


def object_mask(rgb, tol=30.0):
    """a reference render's object: pixels away from its border colour (a studio backdrop), the largest blob"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]]).astype(np.float32)
    bgc = np.median(border, axis=0)
    m = (np.linalg.norm(rgb.astype(np.float32) - bgc, axis=2) > tol).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, st, _c = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n <= 1:
        return m.astype(bool), bgc
    keep = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    big = st[keep, cv2.CC_STAT_AREA]
    out = np.zeros_like(m, bool)
    for k in range(1, n):  # (the object, and anything at least 2% of it: a chain off the grip)
        if st[k, cv2.CC_STAT_AREA] >= 0.02 * big:
            out |= lab == k
    return out, bgc


def _bbox(m):
    import numpy as np  # noqa: PLC0415

    ys, xs = np.nonzero(m)
    return float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)


def _body(m, frac=0.012):
    """the silhouette without its thin parts (a hanging chain, a lanyard, a sight blade): opened by a disc ~1.2% of
    the object's size — those differ between art and build and would bend the scale"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    x0, y0, x1, y1 = _bbox(m)
    r = max(1, int(frac * max(x1 - x0, y1 - y0)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    b = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, k).astype(bool)
    return b if b.sum() > 0.5 * m.sum() else m


def register(ref_mask, ren_mask, flips=(False, True)):
    """the similarity (scale s, shift tx, ty, mirrored or not) that lays the render's silhouette on the reference's
    (pure: test_look_details.py): the BODIES' bounding boxes (thin parts opened away) give the scale and a first
    shift, an ECC fit of the blurred bodies (scale + shift only) the last pixels; the mirror with the better overlap
    wins. -> {"s", "tx", "ty", "flip", "iou"}"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    H, W = ref_mask.shape
    ref_b = _body(ref_mask)
    rx0, ry0, rx1, ry1 = _bbox(ref_b)
    sig = max(2.0, 0.004 * max(W, H))
    ref_f = cv2.GaussianBlur(ref_b.astype(np.float32), (0, 0), sig)
    best = None
    for flip in flips:
        m = ren_mask[:, ::-1] if flip else ren_mask
        b = _body(m)
        x0, y0, x1, y1 = _bbox(b)
        s = ((rx1 - rx0) / (x1 - x0) + (ry1 - ry0) / (y1 - y0)) / 2
        tx, ty = rx0 - s * x0, ry0 - s * y0
        # ECC on the body at the reference's size: an affine started from the boxes, kept a similarity (no shear)
        M0 = np.float32([[s, 0, tx], [0, s, ty]])
        mov = cv2.GaussianBlur(cv2.warpAffine(b.astype(np.float32), M0, (W, H)), (0, 0), sig)
        warp = np.eye(2, 3, dtype=np.float32)
        try:
            _cc, warp = cv2.findTransformECC(ref_f, mov, warp, cv2.MOTION_AFFINE,
                                             (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), None, 5)
            # warp maps reference px -> moved px: invert it, keep its mean scale and shift (a similarity)
            A = np.vstack([warp, [0, 0, 1]])
            Ai = np.linalg.inv(A)
            k = float(np.sqrt(abs(np.linalg.det(Ai[:2, :2]))))
            if 0.8 < k < 1.25:
                s, tx, ty = s * k, k * tx + Ai[0, 2], k * ty + Ai[1, 2]
        except cv2.error:
            pass
        M = np.float32([[s, 0, tx], [0, s, ty]])
        w = cv2.warpAffine(m.astype(np.float32), M, (W, H), flags=cv2.INTER_LINEAR) > 0.5
        iou = float((w & ref_mask).sum() / max(1, (w | ref_mask).sum()))
        if best is None or iou > best["iou"]:
            best = {"s": float(s), "tx": float(tx), "ty": float(ty), "flip": flip, "iou": round(iou, 4)}
    return best


def warp_render(ren_rgba, reg, shape, bg):
    """the render laid onto the reference's frame (its backdrop colour behind it)"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    im = ren_rgba[:, ::-1] if reg["flip"] else ren_rgba
    M = np.float32([[reg["s"], 0, reg["tx"]], [0, reg["s"], reg["ty"]]])
    H, W = shape
    w = cv2.warpAffine(im.astype(np.float32), M, (W, H), flags=cv2.INTER_AREA if reg["s"] < 1 else cv2.INTER_CUBIC)
    a = np.clip(w[..., 3:4] / 255.0, 0, 1)
    return (w[..., :3] * a + np.asarray(bg, np.float32) * (1 - a)).clip(0, 255).astype(np.uint8)


def edge_share(gray):
    """the share of FINE edges: Laplacian energy at a fine scale over a coarse one — a crisp square edge keeps it
    high, a rounded (soft-highlight) edge lower (pure)"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    g = gray.astype(np.float32)
    fine = np.abs(cv2.Laplacian(cv2.GaussianBlur(g, (0, 0), 0.7), cv2.CV_32F)).mean()
    coarse = np.abs(cv2.Laplacian(cv2.GaussianBlur(g, (0, 0), 2.5), cv2.CV_32F)).mean()
    return float(fine / (coarse + 1e-6))


def ssim(a, b):
    """structural similarity of two same-size grey crops (0..1)"""
    import cv2  # noqa: PLC0415
    import numpy as np  # noqa: PLC0415

    a, b = a.astype(np.float32), b.astype(np.float32)
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    mu_a, mu_b = cv2.GaussianBlur(a, (0, 0), 1.5), cv2.GaussianBlur(b, (0, 0), 1.5)
    va = cv2.GaussianBlur(a * a, (0, 0), 1.5) - mu_a ** 2
    vb = cv2.GaussianBlur(b * b, (0, 0), 1.5) - mu_b ** 2
    cov = cv2.GaussianBlur(a * b, (0, 0), 1.5) - mu_a * mu_b
    m = ((2 * mu_a * mu_b + C1) * (2 * cov + C2)) / ((mu_a ** 2 + mu_b ** 2 + C1) * (va + vb + C2))
    return float(np.clip(m.mean(), 0, 1))


def compare(ref, built, rows, pad=0.2, size=160):
    """per detail row ({"label", "box"} in the reference's px): its two crops and the two numbers (pure)"""
    import cv2  # noqa: PLC0415

    out = []
    H, W = ref.shape[:2]
    for r in rows:
        x0, y0, x1, y1 = r["box"]
        p = pad * max(x1 - x0, y1 - y0)
        X0, Y0, X1, Y1 = int(max(0, x0 - p)), int(max(0, y0 - p)), int(min(W, x1 + p)), int(min(H, y1 + p))
        if X1 - X0 < 4 or Y1 - Y0 < 4:
            continue
        a, b = ref[Y0:Y1, X0:X1], built[Y0:Y1, X0:X1]
        k = size / max(a.shape[:2])
        dim = (max(4, round(a.shape[1] * k)), max(4, round(a.shape[0] * k)))
        a2, b2 = cv2.resize(a, dim, interpolation=cv2.INTER_AREA), cv2.resize(b, dim, interpolation=cv2.INTER_AREA)
        ga, gb = cv2.cvtColor(a2, cv2.COLOR_RGB2GRAY), cv2.cvtColor(b2, cv2.COLOR_RGB2GRAY)
        ea, eb = edge_share(ga), edge_share(gb)
        ratio = eb / (ea + 1e-6)
        flag = "sharper than the art" if ratio > 1.3 else ("softer than the art" if ratio < 0.75 else "")
        out.append({"label": r["label"], "kind": r.get("kind", ""), "box": [X0, Y0, X1, Y1],
                    "alike": round(ssim(ga, gb), 3), "edges": round(ratio, 2), "flag": flag, "_a": a2, "_b": b2})
    return out


def sheet(items, path, cell=170):
    from PIL import Image, ImageDraw  # noqa: PLC0415

    cols = 3
    rows = (len(items) + cols - 1) // cols
    W = cols * (2 * cell + 20)
    im = Image.new("RGB", (W, rows * (cell + 34) + 4), (22, 22, 26))
    dr = ImageDraw.Draw(im)
    for k, it in enumerate(items):
        x, y = (k % cols) * (2 * cell + 20) + 4, (k // cols) * (cell + 34) + 4
        im.paste(Image.fromarray(it["_a"]), (x, y))
        im.paste(Image.fromarray(it["_b"]), (x + cell + 4, y))
        col = (240, 90, 80) if it["alike"] < 0.45 or it["flag"] else (200, 200, 200)
        dr.text((x, y + cell + 3), f"{k + 1}. {it['label'][:22]}  alike {it['alike']:.2f}  edges x{it['edges']:.2f}",
                fill=col)
        if it["flag"]:
            dr.text((x, y + cell + 17), it["flag"], fill=(240, 160, 60))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)


def arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv):
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    import look  # noqa: PLC0415  (frame(), blender())

    if not argv or argv[0].startswith("--") or "--part" not in argv:
        return emit("fail", "look details: needs <asset> --part <word>",
                    "lune run kit look details <asset> --part <the object's part-name prefix>")
    asset = argv[0]
    blend = os.path.join(EXPORTS, f"{asset}.blend")
    if not os.path.isfile(blend):
        return emit("fail", f"look details: no build of {asset}", f"lune run kit asset {asset}")
    det = arg(argv, "--details") or os.path.join(REPO, "assets", "models", f"{asset}.details.json")
    if not os.path.isfile(det):
        return emit("fail", f"look details: no shot list for {asset}", "lune run kit refs inventory <picture> --name "
                    f"{asset} (or --details <file>)")
    with open(det, encoding="utf-8") as fh:
        doc = json.load(fh)
    want = (arg(argv, "--picture") or next(iter(doc["pictures"]))).replace(os.sep, "/")
    pic = next((k for k in doc["pictures"] if k == want or os.path.normcase(os.path.abspath(k)) ==
                os.path.normcase(os.path.abspath(want))), None)
    if pic is None:
        return emit("fail", f"look details: {want} is not in the shot list", "pictures in it: " +
                    ", ".join(doc["pictures"]))
    rows = doc["pictures"][pic]["details"]
    with open(os.path.join(EXPORTS, f"{asset}.manifest.json"), encoding="utf-8") as fh:
        bounds = json.load(fh).get("part_bounds") or {}
    words = [w for w in arg(argv, "--part").split(",") if w]
    hits = [n for n in bounds if any(w.lower() in n.lower() for w in words)]
    if not hits:
        return emit("fail", f"look details: no part of {asset} matches {words}", "parts: " + ", ".join(sorted(bounds)[:20]))
    lo = [min(bounds[n][0][i] for n in hits) for i in range(3)]
    hi = [max(bounds[n][1][i] for n in hits) for i in range(3)]
    view = arg(argv, "--view", "side")
    os.makedirs(RENDERS, exist_ok=True)

    def render(v):
        path = os.path.join(RENDERS, f"{asset}_ortho_{v}.png")
        p = subprocess.run([look.blender(), "-b", blend, "-P", os.path.join(REPO, "kit", "blender", "look_ortho.py"),
                            "--", path, ",".join(map(str, lo)), ",".join(map(str, hi)), "--view", v, "--samples",
                            arg(argv, "--samples", "48")], capture_output=True, text=True, timeout=1800)
        if "LOOK_ORTHO" not in p.stdout or not os.path.isfile(path):
            raise RuntimeError((p.stderr or p.stdout)[-240:])
        return np.asarray(Image.open(path).convert("RGBA"))
    ref = np.asarray(Image.open(pic).convert("RGB"))
    ref_mask, bgc = object_mask(ref)
    if ref_mask.sum() < 100:
        return emit("fail", "look details: no object found on the picture's backdrop", "a picture on a plain backdrop")
    try:
        rgba = render(view)
        if (rgba[..., 3] > 127).sum() < 100:
            raise RuntimeError("the render is empty (the --part words framed nothing visible)")
        reg = register(ref_mask, rgba[..., 3] > 127)
        other = {"side": "left", "left": "side", "front": "back", "back": "front"}.get(view)
        if reg["flip"] and other and "--view" not in argv:
            # mirrored fits better: the picture shows the OTHER side — its decoration differs, so render that side
            rgba2 = render(other)
            reg2 = register(ref_mask, rgba2[..., 3] > 127, flips=(False,))
            if reg2["iou"] >= reg["iou"] - 0.05:
                rgba, reg, view = rgba2, reg2, other
    except RuntimeError as e:
        return emit("fail", f"look details: the render failed: {e}", "read the error above")
    built = warp_render(rgba, reg, ref.shape[:2], bgc)
    items = sorted(compare(ref, built, rows), key=lambda it: it["alike"])
    out = os.path.join(RENDERS, f"{asset}_details.png")
    sheet(items, out)
    Image.fromarray(np.concatenate([ref, built], axis=1)).save(os.path.join(RENDERS, f"{asset}_details_overlay.png"))
    with open(out.replace(".png", ".json"), "w", encoding="utf-8") as fh:
        json.dump({"picture": pic, "registration": reg,
                   "details": [{k: v for k, v in it.items() if not k.startswith("_")} for it in items]}, fh, indent=1)
    rel = lambda q: os.path.relpath(q, REPO).replace(os.sep, "/")  # noqa: E731
    sharp = [it["label"] for it in items if it["flag"] == "sharper than the art"]
    return emit("pass" if reg["iou"] >= 0.6 else "fail",
                f"look details {asset}: {len(items)} details side by side (silhouette overlap {reg['iou']:.2f}"
                f"{', mirrored' if reg['flip'] else ''}); worst alike: " +
                ", ".join(f"{it['label']} {it['alike']:.2f}" for it in items[:4]) +
                (f"; edges sharper than the art: {', '.join(sharp[:5])}" if sharp else ""),
                f"LOOK at {rel(out)} (reference left, build right; worst first)" if reg["iou"] >= 0.6 else
                "the silhouettes did not line up: --view left / the right --part / a side view picture",
                sheet=rel(out), iou=reg["iou"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
