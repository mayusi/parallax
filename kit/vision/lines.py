"""lines.py — the INTERNAL LINES check: the reference photo's lines vs the model's, inside the silhouette.

    python kit/vision/lines.py build/renders/<asset>_ref_<view>_lines.json

A silhouette cannot see what is INSIDE the outline: the seam between two receivers, a magwell plate's slanted edge,
a row of slots, a panel line. Here ONE edge detector (TEED, kit/vision) reads both the reference photo and a shaded
render of the model, put in the same frame (the trace's own cut of the photo: box, rotation, exclusions, front), and
every line of the reference must have a model line within a few pixels — and the other way round. Scored in windows
along the length; the worst are named by where they are.
-> build/renders/<asset>_lines_<view>.png (photo, model, diff: red = a line the reference has and the model does not,
   blue = a model line the reference does not show, grey = in both) + one JSON verdict line.
"""

import importlib.util
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import run as V  # noqa: E402  (the vetted models, offline)

_spec = importlib.util.spec_from_file_location("kit_trace", os.path.join(KIT, "blender", "trace.py"))
T = importlib.util.module_from_spec(_spec)  # (python has its own "trace" module: load the kit's by path)
_spec.loader.exec_module(T)
REPO = T.REPO

COLS, ROWS = 24, 2


def _on_white(rgba):
    a = rgba[..., 3:4].astype(np.float32) / 255
    return (rgba[..., :3].astype(np.float32) * a + 255 * (1 - a)).astype(np.uint8)


def photo_frame(info):
    """the reference photo cut exactly as its trace was: -> (RGB on white, object mask), front on the right"""
    src = Image.open(os.path.join(REPO, info["photo"]))
    has_alpha = src.mode in ("RGBA", "LA", "PA") or "transparency" in src.info
    rgba = src.convert("RGBA")
    rot = float(info.get("rotate") or 0)
    if rot:
        rgba = rgba.rotate(rot, resample=Image.BICUBIC, expand=True, fillcolor=rgba.getpixel((2, 2)))
    full = np.asarray(rgba)
    if str(info.get("mask") or "").startswith("BiRefNet"):  # cut exactly as the trace was
        whole = V.cutout(rgba) > 0.5
    else:
        whole, _how = T._object_mask(full[..., :3].astype(np.float32), full[..., 3] if has_alpha else None,
                                     info.get("bg") or "auto", float(info.get("threshold") or 28.0))
    shape0 = (src.size[1], src.size[0])
    ex = T._rotate_mask(T._boxes_mask(shape0, info.get("exclude") or []), rot)
    keep = T._rotate_mask(T._boxes_mask(shape0, info.get("protect") or []), rot)
    box = info.get("box")
    sl = (slice(box[1], box[3]), slice(box[0], box[2])) if box else (slice(None), slice(None))
    m = (whole & ~(whole & ex & ~keep))[sl]
    crop = full[sl]
    if info.get("open"):
        m = T._dilate(T._erode(m, int(info["open"])), int(info["open"]))
    m = T._erode(T._dilate(m, 2), 2)  # (close hairline gaps — in the trace's own order: box, open, close, then warp)
    st = info.get("straighten") or {}
    if st.get("homography") and st.get("size"):  # (a straightened trace: the same warp the trace applied)
        hm, size = np.asarray(st["homography"], float).reshape(3, 3), (int(st["size"][0]), int(st["size"][1]))
        crop = np.asarray(T._warp(Image.fromarray(np.ascontiguousarray(crop)), hm, size))
        m = T._warp_mask(m, hm, size)
    body = T._largest(m)
    if body is None:
        raise ValueError(f"no object found in {info['photo']}")
    lab, _sizes = T._components(~body)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])).tolist())
    filled = body | (~np.isin(lab, list(edge)) & (lab > 0))
    ys, xs = np.nonzero(filled)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgb = _on_white(crop)[y0:y1, x0:x1]
    mask = filled[y0:y1, x0:x1]
    if info.get("front") == "left":
        rgb, mask = rgb[:, ::-1], mask[:, ::-1]
    return np.ascontiguousarray(rgb), np.ascontiguousarray(mask)


def model_frame(path):
    """the shaded render cut to the model's silhouette -> (RGB on white, mask)"""
    rgba = np.asarray(Image.open(path).convert("RGBA"))
    mask = rgba[..., 3] > 127
    ys, xs = np.nonzero(mask)
    sl = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
    return _on_white(rgba[sl]), mask[sl]


def _resize(arr, w, h, nearest=False):
    im = Image.fromarray(arr.astype(np.uint8) * (255 if arr.dtype == bool else 1))
    out = np.asarray(im.resize((w, h), Image.NEAREST if nearest else Image.BILINEAR))
    return out > 127 if arr.dtype == bool else out


def _dist(m):
    """distance (px) from every pixel to the nearest True pixel of m"""
    from scipy.ndimage import distance_transform_edt  # noqa: PLC0415

    return distance_transform_edt(~m) if m.any() else np.full(m.shape, 1e9)


PAD = 24  # white paper (px) around each frame before the edge model: the outline then sits on paper, as in a photo


def _erode(m, r):
    """erosion with the OUTSIDE counted as background (trace.py's np.roll erosion wraps around the picture: a mask
    that fills its frame would erode to itself and the frame border would count as 'inside')"""
    from scipy.ndimage import binary_erosion  # noqa: PLC0415

    return binary_erosion(m, structure=np.ones((3, 3), bool), iterations=r, border_value=0) if r > 0 else m


def _lines(rgb):
    """the line mask of an RGB frame: TEED on white paper (PAD), its RAW output above a FIXED level (never per image)"""
    padded = np.pad(rgb, ((PAD, PAD), (PAD, PAD), (0, 0)), constant_values=255)
    return V.edges(Image.fromarray(padded))[PAD:-PAD, PAD:-PAD] > V.EDGE_LINE


def _trace_mask(info, w, h):
    """the trace's own outline (+ holes) filled at w x h, front on the right like the frames — None without a trace"""
    if not info.get("trace"):
        return None
    with open(os.path.join(REPO, info["trace"]), encoding="utf-8") as fh:
        t = json.load(fh)
    hr = float(t.get("height_ratio") or h / w)
    edges = []
    for ring in [t["outline"], *t.get("holes", [])]:
        pts = [(p[0] * w, (hr - p[1]) / hr * h) for p in ring]
        edges += [(pts[i - 1], pts[i]) for i in range(len(pts))]
    e = np.array(edges, float)
    x0, y0, x1, y1 = e[:, 0, 0], e[:, 0, 1], e[:, 1, 0], e[:, 1, 1]
    mask = np.zeros((h, w), bool)
    xs = np.arange(w) + 0.5
    for row in range(h):  # even-odd scanline fill
        yc = row + 0.5
        hit = (y0 <= yc) != (y1 <= yc)
        if hit.any():
            xc = np.sort(x0[hit] + (yc - y0[hit]) * (x1[hit] - x0[hit]) / (y1[hit] - y0[hit]))
            mask[row] = (np.searchsorted(xc, xs) % 2) == 1
    return mask


def _length_mm(info):
    """the object's real length (mm) in this view: the build's scale (mm per stud, Asset.real_scale) x the model's
    length there (studs) — None when either is missing (positions are then given as % of the length)"""
    try:
        mps, studs = float(info.get("mm_per_stud") or 0), float(info.get("length_studs") or 0)
    except (TypeError, ValueError):
        return None
    return mps * studs if mps > 0 and studs > 0 else None


def compare(info, width=1600):
    p_rgb, p_mask = photo_frame(info)
    m_rgb, m_mask = model_frame(os.path.join(REPO, info["model"]))
    w = min(width, p_rgb.shape[1])
    h = max(32, int(round(w * p_rgb.shape[0] / p_rgb.shape[1])))
    p_rgb, p_mask = _resize(p_rgb, w, h), _resize(p_mask, w, h, True)
    m_rgb, m_mask = _resize(m_rgb, w, h), _resize(m_mask, w, h, True)  # both bbox-fitted, as the silhouette check
    base = {"view": info["view"]}
    # is the photo still cut like its trace? (an old trace without bg / threshold / open, a re-saved picture, a
    # changed --exclude): compare the trace's own outline with the photo's frame mask before trusting any line
    tm = _trace_mask(info, w, h)
    if tm is not None:
        base["frame_iou"] = round(float((tm & p_mask).sum() / max(1, (tm | p_mask).sum())), 3)
        if base["frame_iou"] < 0.9:
            return {**base, "mismatch": True}
    R, M = _lines(p_rgb), _lines(m_rgb)
    k = max(3, w // 200)  # the outline itself is the silhouette check's: compare well inside it
    inner = _erode(p_mask & m_mask, k)
    hr = info.get("height_ratio") or (p_mask.shape[0] / p_mask.shape[1])
    for u0, h0, u1, h1 in info.get("dont_care") or []:  # design units: u along the length, h up (as the trace)
        xa, xb = int(min(u0, u1) * w), int(max(u0, u1) * w) + 1
        ya, yb = int((hr - max(h0, h1)) / hr * h), int((hr - min(h0, h1)) / hr * h) + 1
        inner[max(0, ya):yb, max(0, xa):xb] = False
    ref, mod = R & inner, M & inner
    floor = max(200, int(0.005 * inner.sum()))
    if ref.sum() < floor:  # (a plain object, or dont_care over the lines): nothing to score
        return {**base, "na": True, "reference_line_px": int(ref.sum()), "floor": floor}
    tol = max(2.0, w / 300)
    ref_hit = ref & (_dist(M) <= tol)
    mod_hit = mod & (_dist(R) <= tol)
    recall = float(ref_hit.sum() / max(1, ref.sum()))
    precision = float(mod_hit.sum() / max(1, mod.sum()))
    f1 = 2 * recall * precision / max(1e-6, recall + precision)
    # windows along the length x upper / lower half of the interior — named in MILLIMETRES on the real object when
    # the build gave its scale (Asset.real_scale + the model's length in this view), else as % of the length
    length_mm = _length_mm(info)
    ys, _xs = np.nonzero(inner)
    ya0, ya1 = (int(ys.min()), int(ys.max()) + 1) if len(ys) else (0, h)
    windows = []
    for ci in range(COLS):
        xa, xb = ci * w // COLS, (ci + 1) * w // COLS
        for ri in range(ROWS):
            ya, yb = ya0 + ri * (ya1 - ya0) // ROWS, ya0 + (ri + 1) * (ya1 - ya0) // ROWS
            sl = (slice(ya, yb), slice(xa, xb))
            n_ref, n_mod = int(ref[sl].sum()), int(mod[sl].sum())
            area = int(inner[sl].sum())
            if area < (yb - ya) * (xb - xa) * 0.15:
                continue  # mostly outside the object
            r_w = ref_hit[sl].sum() / n_ref if n_ref else 1.0
            p_w = mod_hit[sl].sum() / n_mod if n_mod else 1.0
            where = f"{100 * ci // COLS}-{100 * (ci + 1) // COLS}% of the length (back->front), {'upper' if ri == 0 else 'lower'}"
            mm = None
            if length_mm:  # the frame is the object's own box: its width IS the length, its bottom the lowest point
                mm = [round(xa / w * length_mm), round(xb / w * length_mm), round((h - yb) / w * length_mm),
                      round((h - ya) / w * length_mm)]
                # (the frame's width is the model's length on a side view, its width on a front / back view; a top
                # view's height runs front to back)
                across = "from the back" if info.get("view", "side") == "side" else "across"
                up = "from the front" if info.get("view") == "top" else "up"
                where = (f"{mm[0]}-{mm[1]} mm {across}, {mm[2]}-{mm[3]} mm {up} "
                         f"({'upper' if ri == 0 else 'lower'} half)")
            extra = {"box": [xa, ya, xb, yb], **({"mm": mm} if mm else {})}
            if n_ref >= max(30, area * 0.01) and r_w < 0.5:
                windows.append({"kind": "missing", "where": where, "recall": round(float(r_w), 2), "px": n_ref, **extra})
            if n_mod >= max(30, area * 0.01) and p_w < 0.35:
                windows.append({"kind": "extra", "where": where, "precision": round(float(p_w), 2), "px": n_mod, **extra})
    windows.sort(key=lambda d: -d["px"])
    # evidence: photo / model / diff, the flagged windows boxed
    diff = np.full((h, w, 3), 255, np.uint8)
    diff[inner] = (238, 238, 242)
    diff[mod & ~mod_hit] = (40, 110, 255)
    diff[ref & ~ref_hit] = (230, 40, 30)
    diff[ref_hit | mod_hit] = (90, 90, 95)
    sheet = Image.new("RGB", (w, h * 3 + 8), "white")
    sheet.paste(Image.fromarray(p_rgb), (0, 0))
    sheet.paste(Image.fromarray(m_rgb), (0, h + 4))
    sheet.paste(Image.fromarray(diff), (0, 2 * h + 8))
    d = ImageDraw.Draw(sheet)
    for win in windows[:8]:
        xa, ya, xb, yb = win["box"]
        for off in (0, h + 4, 2 * h + 8):
            d.rectangle([xa, ya + off, xb - 1, yb - 1 + off], outline=(255, 150, 0) if win["kind"] == "missing" else (0, 160, 255), width=2)
    out = os.path.join(REPO, "build", "renders", f"{info['asset']}_lines_{info['view']}.png")
    sheet.save(out)
    return {**base, "recall": round(recall, 3), "precision": round(precision, 3), "f1": round(f1, 3),
            "length_mm": round(length_mm, 1) if length_mm else None,
            "reference_line_px": int(ref.sum()), "model_line_px": int(mod.sum()), "tolerance_px": round(tol, 1),
            "missing_windows": sum(1 for w_ in windows if w_["kind"] == "missing"),
            "extra_windows": sum(1 for w_ in windows if w_["kind"] == "extra"),
            "windows": windows[:12], "image": os.path.relpath(out, REPO).replace("\\", "/")}


BAR = 0.5  # hero / aaa: at least half of the reference's inside lines must be on the model


def main(argv):
    with open(argv[0], encoding="utf-8") as fh:
        info = json.load(fh)
    view = info["view"]
    strict = info.get("quality") in ("hero", "aaa")
    stale = os.path.join(REPO, "build", "renders", f"{info['asset']}_lines_{view}.png")
    if os.path.isfile(stale):
        os.remove(stale)  # a picture from an older build must never pass for this one's

    def emit(status, summary, next_action, **extra):
        print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
        return 0 if status == "pass" else 1

    if info.get("deferred"):  # a blockout (the build's stage gate): the lines inside the outline come after it
        return emit("pass", f"lines_{view}: deferred — {info['deferred']} (lines inside the outline come after it)",
                    "fix the silhouette first (the build's next_action), then rebuild: this check runs again")
    photo = info.get("photo")
    if not photo or not os.path.isfile(os.path.join(REPO, photo)):
        return emit("fail" if strict else "pass",
                    f"lines_{view}: the reference photo {photo} is missing — "
                    + (f"a {info.get('quality')} build needs it" if strict else "skipped"),
                    f"restore {photo} (refs/ are often untracked), or re-run kit trace on the picture you have")
    try:
        import torch  # noqa: F401, PLC0415 — the vision stack needs it in system python

        V.ensure("teed")
        if str(info.get("mask") or "").startswith("BiRefNet"):
            V.ensure("birefnet")  # this trace was cut with the learned cutout: the photo must be cut the same way
    except V.PinMismatch as e:  # never optional: a file that fails its pin is reported, whatever the tier
        return emit("fail", f"lines_{view}: {e}", "lune run kit vision setup   (re-fetches the pinned file)")
    except (V.ModelMissing, ImportError) as e:  # the vision stack is optional: say so, never block a build over it
        return emit("pass", f"lines_{view}: skipped — the vision models are not set up ({e})",
                    "lune run kit vision setup   (vetted, pinned downloads: then the internal-lines check runs on "
                    "every build)")
    r = compare(info)
    if r.get("mismatch"):
        return emit("fail" if strict else "pass",
                    f"lines_{view}: {'FAILED' if strict else 'skipped'} — the photo no longer cuts like its trace "
                    f"(frame IoU {r['frame_iou']:.2f})",
                    f"re-run kit trace for {info.get('trace')} (it records how the photo is cut: --bg / --threshold / "
                    "--open), then rebuild", lines=r)
    if r.get("na"):
        return emit("pass", f"lines_{view}: n/a — the reference shows almost no lines inside the outline "
                    f"({r['reference_line_px']} px < {r['floor']})",
                    "nothing to compare (a plain object, or dont_care boxes cover its lines)", lines=r)
    miss, extra = r["missing_windows"], r["extra_windows"]
    summary = (f"lines_{view}: {r['recall']:.0%} of the reference's inside lines are on the model, "
               f"{r['precision']:.0%} of the model's are in the reference (f1 {r['f1']:.2f})"
               + (f"; {miss} window(s) missing lines" if miss else "")
               + (f"; {extra} window(s) with extra lines" if extra else ""))
    worst = r["windows"][0] if r["windows"] else None
    nxt = (f"look at {r['image']} (red = the reference's line the model lacks): "
           + (f"{worst['kind']} lines at {worst['where']}" if worst else "nothing flagged")
           + " — model the seam / plate edge / slot the photo shows there (or put a dont_care box on a reflection)")
    ok = not strict or r["recall"] >= BAR
    if not ok:
        summary += f" — below the {info.get('quality')} bar ({BAR:.0%} of the reference's lines)"
    return emit("pass" if ok else "fail", summary, nxt, lines=r)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
