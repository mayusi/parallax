"""foliage_leaves.py — REAL leaves cut out of photos into one texture atlas, each with its own outline, tip and base
(the kit's foliage: the owner 2026-10-17 "make realistic vines very realistic"; graveyard G3 — foliage typed from
words never reaches the bar, so every leaf here is a photographed leaf).

    python kit/tools/foliage_leaves.py --out <dir> --photo <a.jpg> --labels <a.parts.png> [--min-score 0.65]
        [--photo <b.jpg> --cutout <b_cutout.png>] [--max 16] [--size 2048]

--labels: `kit vision parts <photo> --text leaf` (SAM 3: each leaf's id in its label image, scores in .parts.json);
--cutout: one whole leaf already cut out (`kit vision cutout`). Kept: whole leaves only (not cut by the frame), a
leaf's solidity (a lobed ivy leaf 0.6-0.95), size >= 2000 px. Writes <dir>/leaves.png (RGBA atlas, each leaf in its
own cell, its edge dilated so the bake never samples background) and <dir>/leaves.json:
    {"atlas": "leaves.png", "leaves": [{"uv_box": [u0, v0, u1, v1], "outline": [[x, y] ...] (leaf frame: base at
     (0, 0), tip at (0, 1), x across, in tip lengths), "aspect": width / length, "source": ..., "id": ...}]}
Prints one JSON line (summary / next_action).
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np


def leaf_masks(labels, scores, min_score=0.65, min_area=2000):
    """label image + {id: score} -> [(id, mask)] — whole, confident, leaf-shaped (not touching the frame)"""
    out = []
    h, w = labels.shape
    for lid, sc in scores.items():
        if sc < min_score:
            continue
        m = labels == lid
        area = int(m.sum())
        if area < min_area:
            continue
        ys, xs = np.nonzero(m)
        if xs.min() <= 1 or ys.min() <= 1 or xs.max() >= w - 2 or ys.max() >= h - 2:
            continue   # (cut by the frame: not a whole leaf)
        cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        c = max(cnts, key=cv2.contourArea)
        hull = cv2.convexHull(c)
        solidity = cv2.contourArea(c) / max(cv2.contourArea(hull), 1)
        if not 0.6 <= solidity <= 0.97:
            continue
        out.append((lid, m, float(sc)))
    return out


def tip_and_base(contour):
    """a leaf's outline (n, 2) px -> (tip, base): the tip = the outline point farthest from the centroid; the base =
    where the petiole joins — the outline point nearest the centroid on the far side from the tip (an ivy leaf's
    basal sinus)"""
    c = contour.mean(axis=0)
    d = np.linalg.norm(contour - c, axis=1)
    tip = contour[int(d.argmax())]
    axis = (tip - c) / max(np.linalg.norm(tip - c), 1e-9)
    behind = ((contour - c) @ axis) < -0.25 * d.max()
    if not behind.any():
        return tip, c - axis * d.max() * 0.6
    cand = contour[behind]
    # nearest the leaf's axis line (|perpendicular|) and nearest the centroid: the sinus
    perp = np.abs((cand - c) @ np.array([-axis[1], axis[0]]))
    k = int(np.argmin(perp + 0.5 * np.linalg.norm(cand - c, axis=1)))
    return tip, cand[k]


def leaf_frame(contour, tip, base, n=48):
    """outline px -> leaf frame (base at 0,0, tip at 0,1, x across in tip lengths), resampled to n points"""
    v = tip - base
    L = max(np.linalg.norm(v), 1e-9)
    ax = v / L
    across = np.array([ax[1], -ax[0]])
    rel = contour - base
    pts = np.column_stack([rel @ across, rel @ ax]) / L
    # resample by arc length
    seg = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    t = np.concatenate([[0], np.cumsum(seg)])
    s = np.linspace(0, t[-1], n, endpoint=False)
    closed = np.vstack([pts, pts[:1]])
    res = np.column_stack([np.interp(s, t, closed[:, 0]), np.interp(s, t, closed[:, 1])])
    return res, L


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--photo", action="append", default=[])
    ap.add_argument("--labels", action="append", default=[])
    ap.add_argument("--cutout", action="append", default=[])
    ap.add_argument("--min-score", type=float, default=0.65)
    ap.add_argument("--max", type=int, default=16)
    ap.add_argument("--size", type=int, default=2048)
    ap.add_argument("--tones", default="1.0", help="each leaf again at these values (a flora's 'pale green to dark "
                                                  "green': 1.0,0.72,0.52)")
    ap.add_argument("--match", default="", help="a photo of the plant in place: every leaf's colour matched to its "
                                               "green pixels (Lab mean / spread) — the cut leaves were young, sunlit")
    ap.add_argument("--erode", type=int, default=2, help="px off each mask's edge (the dark gaps between leaves)")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    found = []   # (rgba crop, contour px in crop, tip, base, source, id)
    lab_i = cut_i = 0
    for photo in a.photo:
        img = cv2.cvtColor(cv2.imread(photo, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        if lab_i < len(a.labels):
            lab_path = a.labels[lab_i]
            lab_i += 1
            labels = cv2.imread(lab_path, cv2.IMREAD_UNCHANGED)
            labels = labels[..., 0] if labels.ndim == 3 else labels
            with open(lab_path.replace(".png", ".json"), encoding="utf-8") as fh:
                parts = json.load(fh)["found"]
            scores = {p["id"]: p["score"] for v in parts.values() for p in v}
            masks = leaf_masks(labels.astype(np.int64), scores, a.min_score)
        elif cut_i < len(a.cutout):
            cut = cv2.imread(a.cutout[cut_i], cv2.IMREAD_UNCHANGED)
            cut_i += 1
            m = cut[..., 3] > 127 if cut.ndim == 3 and cut.shape[2] == 4 else cut > 127
            if m.shape != img.shape[:2]:
                m = cv2.resize(m.astype(np.uint8), (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
            masks = [(0, m, 1.0)]
        else:
            continue
        for lid, m, sc in masks:
            if a.erode > 0:   # (a mask's edge holds the dark gap between leaves: a black fringe on every leaf)
                m = cv2.erode(m.astype(np.uint8), np.ones((2 * a.erode + 1,) * 2, np.uint8)) > 0
            cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            c = max(cnts, key=cv2.contourArea)[:, 0, :].astype(np.float64)
            x, y, w, h = cv2.boundingRect(c.astype(np.int32))
            pad = 4
            x0, y0 = max(x - pad, 0), max(y - pad, 0)
            x1, y1 = min(x + w + pad, img.shape[1]), min(y + h + pad, img.shape[0])
            rgba = np.dstack([img[y0:y1, x0:x1], (m[y0:y1, x0:x1] * 255).astype(np.uint8)])
            tip, base = tip_and_base(c)
            found.append({"rgba": rgba, "contour": c - [x0, y0], "tip": tip - [x0, y0], "base": base - [x0, y0],
                          "source": os.path.relpath(photo).replace(os.sep, "/"), "id": int(lid), "score": sc,
                          "area": int(m.sum())})
    found.sort(key=lambda f: (-f["score"], -f["area"]))
    found = found[: a.max]
    # the colour of the plant IN PLACE: each leaf's Lab mean / spread moved onto the reference's green pixels (the cut
    # leaves were young, sunlit ground ivy: yellow-green; a wall's ivy is deep green — measured, not guessed)
    if a.match:
        ref = cv2.cvtColor(cv2.imread(a.match, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        hsv = cv2.cvtColor(ref, cv2.COLOR_RGB2HSV)
        green = (hsv[..., 0] >= 30) & (hsv[..., 0] <= 85) & (hsv[..., 1] >= 60) & (hsv[..., 2] >= 25)
        lab_ref = cv2.cvtColor(ref, cv2.COLOR_RGB2LAB).astype(np.float32)[green]
        # (the LIT faces only — the brighter half: a leaf's own colour; the shadows between leaves are the render's
        #  to make — matched to every green pixel, the wall came out olive-grey)
        lab_ref = lab_ref[lab_ref[:, 0] >= np.median(lab_ref[:, 0])]
        mu_r, sd_r = lab_ref.mean(axis=0), lab_ref.std(axis=0) + 1e-3
        for f in found:
            al = f["rgba"][..., 3] > 127
            lab = cv2.cvtColor(np.ascontiguousarray(f["rgba"][..., :3]), cv2.COLOR_RGB2LAB).astype(np.float32)
            mu, sd = lab[al].mean(axis=0), lab[al].std(axis=0) + 1e-3
            # (lightness: mean AND spread; the colour axes: the mean only — their spread scaled too threw purple patches)
            lab[..., 0] = (lab[..., 0] - mu[0]) / sd[0] * sd_r[0] + mu_r[0]
            lab[..., 1:] = lab[..., 1:] - mu[1:] + mu_r[1:]
            f["rgba"] = np.dstack([cv2.cvtColor(lab.clip(0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB),
                                   f["rgba"][..., 3]])
        match_facts = {"ref_lab_mean": [round(float(x), 1) for x in mu_r], "green_px": int(green.sum())}
    else:
        match_facts = {}
    # every leaf again at each darker tone: its value scaled, its hue kept (HSV), the photo's veins and texture kept
    tones = [float(t) for t in a.tones.split(",") if t.strip()]
    toned = []
    for t in tones:
        for f in found:
            g = dict(f)
            if abs(t - 1.0) > 1e-6:
                hsv = cv2.cvtColor(f["rgba"][..., :3], cv2.COLOR_RGB2HSV).astype(np.float32)
                hsv[..., 2] *= t
                hsv[..., 1] = np.clip(hsv[..., 1] * (1 + 0.25 * (1 - t)), 0, 255)   # (a darker leaf reads richer)
                g["rgba"] = np.dstack([cv2.cvtColor(hsv.clip(0, 255).astype(np.uint8), cv2.COLOR_HSV2RGB),
                                       f["rgba"][..., 3]])
            g["tone"] = t
            toned.append(g)
    found = toned
    if not found:
        print(json.dumps({"schema": 1, "status": "fail", "summary": "foliage leaves: no whole leaf found",
                          "next_action": "a photo with whole leaves (kit refs find), or lower --min-score"}))
        return 1
    # the atlas: a square grid of cells, each leaf scaled to fill its cell, its colour dilated past its edge
    n = len(found)
    cols = int(np.ceil(np.sqrt(n)))
    cell = a.size // cols
    atlas = np.zeros((a.size, a.size, 4), np.uint8)
    leaves = []
    for i, f in enumerate(found):
        r, c = divmod(i, cols)
        h, w = f["rgba"].shape[:2]
        k = (cell - 8) / max(h, w)
        nh, nw = max(int(h * k), 1), max(int(w * k), 1)
        im = cv2.resize(f["rgba"], (nw, nh), interpolation=cv2.INTER_AREA)
        rgb, al = im[..., :3].astype(np.float32), im[..., 3]
        # dilate the colour outward (the leaf's own edge colour fills the margin: a bake never sees black)
        inside = al > 127
        fill = rgb.copy()
        known = inside.copy()
        for _ in range(8):
            blur = cv2.blur(fill * known[..., None], (3, 3))
            cnt = cv2.blur(known.astype(np.float32), (3, 3))
            grow = (~known) & (cnt > 0)
            fill[grow] = (blur[grow] / cnt[grow, None])
            known |= grow
        ox, oy = c * cell + (cell - nw) // 2, r * cell + (cell - nh) // 2
        atlas[oy:oy + nh, ox:ox + nw, :3] = fill.clip(0, 255).astype(np.uint8)
        atlas[oy:oy + nh, ox:ox + nw, 3] = np.where(known, 255, 0).astype(np.uint8)
        frame, L = leaf_frame(f["contour"], f["tip"], f["base"])
        # each outline point's place in the atlas (UV: u right, v UP — glTF flips v, make_ivy writes it as it needs)
        to_px = lambda p: (ox + p[0] * k, oy + p[1] * k)  # noqa: E731
        v_ax = (f["tip"] - f["base"]) / max(np.linalg.norm(f["tip"] - f["base"]), 1e-9)
        across = np.array([v_ax[1], -v_ax[0]])
        uv = []
        for fx, fy in frame:
            p = f["base"] + (fx * across + fy * v_ax) * L
            px, py = to_px(p)
            uv.append([round(px / a.size, 5), round(1 - py / a.size, 5)])
        xs = frame[:, 0]
        leaves.append({"outline": [[round(float(x_), 4), round(float(y_), 4)] for x_, y_ in frame],
                       "uv": uv, "aspect": round(float(xs.max() - xs.min()), 3),
                       "source": f["source"], "id": f["id"], "score": round(f["score"], 3),
                       "tone": f.get("tone", 1.0)})
    cv2.imwrite(os.path.join(a.out, "leaves.png"), cv2.cvtColor(atlas, cv2.COLOR_RGBA2BGRA))
    # the veins as relief (a tangent-space normal map from each leaf's own photo): a vein is paler and sits a little
    # LOW in the blade, the blade between them puffs up — the light catches them, as on a real leaf
    lum = cv2.cvtColor(atlas[..., :3], cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    height = cv2.GaussianBlur(lum, (0, 0), 7.0) - cv2.GaussianBlur(lum, (0, 0), 2.2)   # (veins: high-pass, inverted;
    #                                                                       the photo's JPEG grain blurred away)
    height *= (atlas[..., 3] > 0)
    gx = cv2.Sobel(height, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(height, cv2.CV_32F, 0, 1, ksize=3)
    k = 4.0 * a.size / 2048.0
    nrm = np.dstack([-gx * k, gy * k, np.ones_like(gx)])   # (OpenGL / glTF: +y up in the picture's v)
    nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    cv2.imwrite(os.path.join(a.out, "leaves_normal.png"),
                cv2.cvtColor(((nrm * 0.5 + 0.5) * 255).clip(0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    with open(os.path.join(a.out, "leaves.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"atlas": "leaves.png", "normal": "leaves_normal.png", "match": match_facts, "leaves": leaves}, fh,
                  indent=1)
    print(json.dumps({"schema": 1, "status": "pass",
                      "summary": f"foliage leaves: {n} whole leaves from {len(a.photo)} photo(s) -> {a.out}/leaves.png",
                      "next_action": f"LOOK at {a.out}/leaves.png (every cell one whole real leaf)", "leaves": n}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
