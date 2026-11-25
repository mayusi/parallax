"""saliency.py — WHERE THE EYE LANDS FIRST (LIMITATIONS_FIXES_V4 UI-X 6.4 step 4 / 13.6: the UEyes / UIGaze saliency
gate). A screen's "focus" must be where a player's FIRST fixation lands, measured, not judged: in >= 85% of simulated
first looks it lands on the focus node (or within ~1 degree of it).

The model is bottom-up and blur+contrast, because that is what the first second of looking is. UEyes (Jiang et al.,
CHI '23, 62 people x 1,980 UIs, CC-BY-4.0) found a TOP-LEFT location bias on every UI type and that text draws the eye
before images; UIGaze (arXiv:2604.26352, MIT) found vision-language models match LATER, semantic attention and NOT the
first, salience-driven fixations. So:
  * the first-fixation gate is this map: centre-surround luminance + colour-opponent contrast + an edge (text) energy
    channel, squinted (blurred by ~1% of the width, like kit/ui/hier.py's squint), times a location prior (a centre
    Gaussian mixed with UEyes' top-left one); N simulated viewers (each their own squint, prior strength and noise)
    take their first look at the map's peak; the share landing on the focus is the score;
  * `calibrate` fits the weights to UEyes' own 1-second fixation maps (saliency_maps/fixmaps_1s + heatmaps_1s) and
    writes kit/ui/saliency_calib.json (until it runs, the weights are the UEyes-informed defaults below: said);
  * `gaze` is the UIGaze protocol: gaze points (from the kit's local VLM, kit/vision/vlm.py, or a JSON file) become a
    Gaussian map scored against ours (CC, NSS, KLD) - a second opinion on LATER attention, never the gate.

    python kit/ui/saliency.py <Screen> [--ui build/ui] [--specs assets/ui] [--out build/judge/ui] [--min 0.85]
    python kit/ui/saliency.py check --frame <png> --boxes <boxes.json> --focus <path> [--min 0.85]
    python kit/ui/saliency.py calibrate --ueyes <UEyes folder> [--limit 300]
    python kit/ui/saliency.py gaze <Screen> (--points <points.json> | --vlm) [--n 8]
"""
import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CALIB = os.path.join(HERE, "saliency_calib.json")
WORK_W = 320  # the map is computed at this width (a glance does not resolve finer)
MIN_MATCH = 0.85
# defaults until `calibrate` runs on UEyes: equal channels, a 1% squint (hier.py), a mild prior whose peak sits a
# third of the way toward UEyes' top-left bias
DEFAULTS = {
    "w_lum": 1.0,
    "w_color": 1.0,
    "w_edge": 1.0,
    "squint": 0.01,
    "prior": 0.35,
    "topleft": 0.35,
    "viewers": 24,
    "pad": 0.02,
    "source": "defaults (UEyes-informed: top-left bias, text draws the eye) - not yet calibrated on UEyes",
}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}, ensure_ascii=False))
    return 0 if status == "pass" else 1


def weights():
    w = dict(DEFAULTS)
    if os.path.isfile(CALIB):
        try:
            with open(CALIB, encoding="utf-8") as fh:
                got = json.load(fh)
            w.update({k: v for k, v in (got.get("weights") or {}).items() if k in DEFAULTS})
            w["source"] = got.get("source") or "kit/ui/saliency_calib.json"
        except (OSError, ValueError):
            pass
    return w


# ------------------------------------------------------------------ the map
def _gauss1d(sigma):
    r = max(1, int(math.ceil(sigma * 3)))
    x = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-(x * x) / (2 * sigma * sigma))
    return k / k.sum()


def blur(a, sigma):
    """separable Gaussian blur of a 2-D float array (edges: reflected)"""
    if sigma <= 0.3:
        return a
    try:
        from scipy.ndimage import gaussian_filter
        return gaussian_filter(a, sigma, mode="reflect", truncate=3.0)
    except ImportError:
        pass
    k = _gauss1d(sigma)
    r = len(k) // 2
    p = np.pad(a, ((r, r), (0, 0)), mode="reflect")
    a = np.apply_along_axis(lambda c: np.convolve(c, k, mode="valid"), 0, p)
    p = np.pad(a, ((0, 0), (r, r)), mode="reflect")
    return np.apply_along_axis(lambda c: np.convolve(c, k, mode="valid"), 1, p)


def _norm(m):
    """Itti's N(): scale to [0, 1], then favour a map with a few strong peaks over one with many equal ones"""
    m = m - m.min()
    top = m.max()
    if top <= 1e-12:
        return m
    m = m / top
    return m * (1.0 - m.mean()) ** 2


def _work(img):
    img = img.convert("RGB")
    W, H = img.size
    h = max(8, round(H * WORK_W / W))
    return np.asarray(img.resize((WORK_W, h), Image.BILINEAR), dtype=np.float64) / 255.0


def prior_map(h, w, topleft):
    """the location prior: a centre Gaussian mixed with UEyes' top-left one (topleft = the top-left share)"""
    yy, xx = np.mgrid[0:h, 0:w]
    xx, yy = xx / max(w - 1, 1), yy / max(h - 1, 1)
    centre = np.exp(-(((xx - 0.5) / 0.3) ** 2 + ((yy - 0.5) / 0.3) ** 2) / 2)
    tl = np.exp(-(((xx - 0.25) / 0.25) ** 2 + ((yy - 0.25) / 0.25) ** 2) / 2)
    p = (1 - topleft) * centre + topleft * tl
    return p / p.max()


def channels(img, w):
    """the weighted feature sum before the squint and the prior (it does not change between simulated viewers)"""
    a = _work(img)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    L = 0.2126 * R + 0.7152 * G + 0.0722 * B
    RG = R - G
    BY = B - (R + G) / 2
    s = WORK_W / 320.0
    lum = np.zeros_like(L)
    col = np.zeros_like(L)
    for c, sr in ((1.0, 4.0), (2.0, 8.0), (4.0, 16.0)):
        lum += np.abs(blur(L, c * s) - blur(L, sr * s))
        col += np.abs(blur(RG, c * s) - blur(RG, sr * s)) + np.abs(blur(BY, c * s) - blur(BY, sr * s))
    gy, gx = np.gradient(L)
    edge = blur(np.hypot(gx, gy), 3.0 * s)
    return w["w_lum"] * _norm(lum) + w["w_color"] * _norm(col) + w["w_edge"] * _norm(edge)


def finish(S0, w):
    """squint + the location prior, scaled to max 1"""
    S = blur(S0, max(0.5, w["squint"] * WORK_W))
    h, ww = S.shape
    S = S * (1 - w["prior"] + w["prior"] * prior_map(h, ww, w["topleft"]))
    top = S.max()
    return S / top if top > 0 else S


def saliency_map(img, w=None):
    """-> (map HxW at WORK_W, float, max 1): bottom-up first-look salience of a PIL picture"""
    w = w or weights()
    return finish(channels(img, w), w)


def first_looks(img, w=None, viewers=None, seed=7):
    """-> [(x, y)] in the picture's own pixels: each simulated viewer's FIRST fixation (the peak of the map they see:
    their own squint 0.6-1.6x, prior strength +-50%, and a blurred noise field ~10% of the map)"""
    w = dict(w or weights())
    n = int(viewers or w["viewers"])
    rng = np.random.default_rng(seed)
    W, H = img.size
    out = []
    base_squint, base_prior = w["squint"], w["prior"]
    S0 = channels(img, w)
    for _ in range(n):
        w["squint"] = base_squint * rng.uniform(0.6, 1.6)
        w["prior"] = float(np.clip(base_prior * rng.uniform(0.5, 1.5), 0, 1))
        S = finish(S0, w)
        noise = blur(rng.normal(0, 1, S.shape), 4.0)
        noise = noise / (np.abs(noise).max() + 1e-12) * 0.1
        y, x = np.unravel_index(int(np.argmax(S + noise)), S.shape)
        out.append(((x + 0.5) * W / S.shape[1], (y + 0.5) * H / S.shape[0]))
    return out


def related(path, focus):
    return path == focus or path.startswith(focus + ".")


def lands_on(pt, boxes, focus, pad):
    """does a fixation land on the focus (or anything inside it), within pad pixels?"""
    x, y = pt
    for p, (bx, by, bw, bh) in boxes.items():
        if related(p, focus) and bx - pad <= x <= bx + bw + pad and by - pad <= y <= by + bh + pad:
            return True
    return False


def landed_on(pt, boxes, focus):
    """the smallest node a fixation landed on (what the eye took instead), or None"""
    x, y = pt
    best = None
    for p, (bx, by, bw, bh) in boxes.items():
        if bx <= x <= bx + bw and by <= y <= by + bh and bw * bh > 0:
            if best is None or bw * bh < best[1]:
                best = (p, bw * bh)
    return best[0] if best else None


def judge(img, boxes, focus, w=None, viewers=None, seed=7):
    """-> {match, looks, hits, elsewhere}: the share of simulated first looks on the focus"""
    w = w or weights()
    looks = first_looks(img, w, viewers, seed)
    pad = w["pad"] * img.size[0]
    hits = [lands_on(p, boxes, focus, pad) for p in looks]
    other = {}
    for p, h in zip(looks, hits):
        if not h:
            k = landed_on(p, boxes, focus) or "(the background)"
            other[k] = other.get(k, 0) + 1
    match = sum(hits) / max(1, len(hits))
    return {"match": round(match, 3), "looks": [[round(x, 1), round(y, 1)] for x, y in looks], "hits": hits,
            "elsewhere": sorted(other.items(), key=lambda kv: -kv[1])}


# ------------------------------------------------------------------ metrics (UEyes / UIGaze protocol)
def cc(a, b):
    a = (a - a.mean()) / (a.std() + 1e-12)
    b = (b - b.mean()) / (b.std() + 1e-12)
    return float((a * b).mean())


def nss(sal, fix):
    """normalised scanpath saliency: the map's z-score at the fixated pixels (fix: a same-size map, > 0 = fixated)"""
    z = (sal - sal.mean()) / (sal.std() + 1e-12)
    m = fix > 0
    return float(z[m].mean()) if m.any() else 0.0


def kld(sal, gt):
    p = gt / (gt.sum() + 1e-12)
    q = sal / (sal.sum() + 1e-12)
    return float((p * np.log(1e-12 + p / (q + 1e-12))).sum())


def points_to_map(points, h, w, sigma):
    """gaze points (x, y in map pixels) -> a Gaussian saliency map (UIGaze turns a VLM's points into one so)"""
    yy, xx = np.mgrid[0:h, 0:w]
    m = np.zeros((h, w))
    for x, y in points:
        m += np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma * sigma))
    return m / m.max() if m.max() > 0 else m


UIGAZE_PROMPT = (
    "You are watching a player look at this game screen for the first time. List the {n} places their eyes land, in "
    "the order they look, as a JSON list of [x, y] points on a 0-1000 scale of the picture (x right, y down). Answer "
    "ONLY the JSON list.")


def parse_points(text, width, height):
    """a VLM's answer -> [(x, y)] in picture pixels (Qwen3-VL answers on a 0-1000 scale); junk is skipped"""
    out = []
    for a, b in re.findall(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]", text or ""):
        x, y = float(a), float(b)
        if 0 <= x <= 1000 and 0 <= y <= 1000:
            out.append((x * width / 1000.0, y * height / 1000.0))
    return out


# ------------------------------------------------------------------ calibration on UEyes
def _find(folder, stem):
    if not os.path.isdir(folder):
        return None
    for ext in (".png", ".jpg", ".jpeg", ".bmp"):
        p = os.path.join(folder, stem + ext)
        if os.path.isfile(p):
            return p
    return None


def ueyes_items(root, split=None, limit=None):
    """[(image, fixmap_1s, heatmap_1s | None, split)] from a UEyes folder (info.csv + images/ + saliency_maps/)"""
    info = os.path.join(root, "info.csv")
    if not os.path.isfile(info):
        return []
    items = []
    with open(info, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            low = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            name = low.get("image") or low.get("name") or low.get("image_name") or next(iter(low.values()), "")
            sp = next((v for k, v in low.items() if "train" in k or "split" in k or "set" in k), "")
            sp = "test" if "test" in sp.lower() else "train"
            if split and sp != split:
                continue
            stem = os.path.splitext(os.path.basename(name))[0]
            img = _find(os.path.join(root, "images"), stem)
            fix = _find(os.path.join(root, "saliency_maps", "fixmaps_1s"), stem)
            heat = _find(os.path.join(root, "saliency_maps", "heatmaps_1s"), stem)
            if img and fix:
                items.append((img, fix, heat, sp))
            if limit and len(items) >= limit:
                break
    return items


def _gray(path, shape):
    return np.asarray(Image.open(path).convert("L").resize((shape[1], shape[0]), Image.BILINEAR), dtype=np.float64)


def score(items, w):
    """mean NSS (1 s fixations) and CC (1 s heat map, where there is one) of the map over UEyes items"""
    n_s, c_s, n_c = 0.0, 0.0, 0
    for img, fix, heat, _ in items:
        S = saliency_map(Image.open(img), w)
        n_s += nss(S, _gray(fix, S.shape))
        if heat:
            c_s += cc(S, _gray(heat, S.shape))
            n_c += 1
    k = max(1, len(items))
    return n_s / k, (c_s / n_c if n_c else None)


GRID = {"prior": (0.0, 0.35, 0.7), "topleft": (0.0, 0.35, 0.7), "squint": (0.005, 0.01, 0.02),
        "w_edge": (0.5, 1.0, 2.0), "w_color": (0.5, 1.0, 2.0)}


def calibrate(root, limit=300, grid=None, write=True):
    """coordinate ascent over GRID on UEyes' train split (NSS on the 1-second fixations), reported on its test split"""
    train = ueyes_items(root, "train", limit)
    test = ueyes_items(root, "test", max(1, limit // 3) if limit else None)
    if not train:
        return None
    grid = grid or GRID
    w = {k: v for k, v in DEFAULTS.items() if k != "source"}
    best = score(train, w)[0]
    for _ in range(2):
        for k, vals in grid.items():
            for v in vals:
                t = dict(w, **{k: v})
                s = score(train, t)[0]
                if s > best + 1e-6:
                    best, w = s, t
    t_nss, t_cc = score(test or train, w)
    h = hashlib.sha1()
    with open(os.path.join(root, "info.csv"), "rb") as fh:
        h.update(fh.read())
    out = {"schema": 1, "weights": {k: w[k] for k in GRID},
           "source": f"calibrated on UEyes 1 s fixations ({len(train)} train / {len(test)} test UIs)",
           "train_nss": round(best, 4), "test_nss": round(t_nss, 4), "test_cc": None if t_cc is None else round(t_cc, 4),
           "info_sha1": h.hexdigest()}
    if write:
        with open(CALIB, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(out, fh, indent=1)
    return out


# ------------------------------------------------------------------ the CLI
def load_screen(S, ui, specs):
    frame_p = next((p for p in (os.path.join(ui, f"{S}.desktop.png"), os.path.join(ui, f"{S}.png")) if os.path.isfile(p)), None)
    if not frame_p:
        return None, None, None
    return frame_p, os.path.join(ui, f"{S}.boxes.json"), os.path.join(specs, f"{S}.json")


def read_boxes(path, frame_w):
    if not path or not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        bj = json.load(fh)
    vw = (bj.get("viewport") or [frame_w])[0] or frame_w
    k = frame_w / vw
    return {p: tuple(v * k for v in b) for p, b in (bj.get("boxes") or {}).items()}


def run_check(name, frame_p, boxes_p, focus, minimum, out):
    img = Image.open(frame_p).convert("RGB")
    boxes = read_boxes(boxes_p, img.size[0])
    if not focus:
        return emit("fail", f"saliency {name}: the spec names no \"focus\" - nothing to land on",
                    f"add \"focus\": \"<node path>\" to the spec (the one thing a glance must take)")
    if not any(related(p, focus) for p in boxes):
        return emit("fail", f"saliency {name}: the focus {focus} has no box in the preview",
                    f"lune run kit ui {name} (the preview writes {name}.boxes.json), or fix the focus path")
    w = weights()
    res = judge(img, boxes, focus, w)
    if out:
        os.makedirs(out, exist_ok=True)
        S = saliency_map(img, w)
        Image.fromarray((S * 255).astype(np.uint8)).resize(img.size, Image.BILINEAR).save(os.path.join(out, "map.png"))
        with open(os.path.join(out, "result.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(dict(res, focus=focus, min=minimum, weights=w["source"]), fh, indent=1)
    pct = round(res["match"] * 100)
    took = ", ".join(f"{k} {v}" for k, v in res["elsewhere"][:3])
    if res["match"] < minimum:
        return emit("fail", f"saliency {name}: {pct}% of first looks land on {focus} (under {round(minimum * 100)}%) - "
                            f"the eye took {took}",
                    f"make {focus} win the first look: more contrast against what is around it, bigger, or quiet "
                    f"what took the eye ({res['elsewhere'][0][0] if res['elsewhere'] else 'the background'})",
                    match=res["match"], focus=focus, elsewhere=res["elsewhere"][:5], weights=w["source"])
    return emit("pass", f"saliency {name}: {pct}% of first looks land on {focus}", "none - proceed",
                match=res["match"], focus=focus, elsewhere=res["elsewhere"][:5], weights=w["source"])


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = argv[0] if argv and argv[0] in ("check", "calibrate", "gaze") else "screen"
    if mode != "screen":
        argv = argv[1:]
    ap = argparse.ArgumentParser(prog=f"saliency.py {mode}")
    if mode in ("screen", "gaze"):
        ap.add_argument("screen")
    ap.add_argument("--ui", default="build/ui")
    ap.add_argument("--specs", default="assets/ui")
    ap.add_argument("--out", default="build/judge/ui")
    ap.add_argument("--min", type=float, default=MIN_MATCH)
    ap.add_argument("--frame")
    ap.add_argument("--boxes")
    ap.add_argument("--focus")
    ap.add_argument("--ueyes")
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--points")
    ap.add_argument("--vlm", action="store_true")
    ap.add_argument("--n", type=int, default=8)
    a = ap.parse_args(argv)

    if mode == "check":
        if not a.frame or not os.path.isfile(a.frame):
            return emit("fail", f"saliency check: no frame {a.frame!r}", "pass --frame <png> --boxes <json> --focus <path>")
        name = os.path.splitext(os.path.basename(a.frame))[0]
        return run_check(name, a.frame, a.boxes, a.focus, a.min, None)

    if mode == "calibrate":
        if not a.ueyes or not os.path.isfile(os.path.join(a.ueyes, "info.csv")):
            return emit("fail", "saliency calibrate: no UEyes folder (info.csv + images/ + saliency_maps/fixmaps_1s)",
                        "the owner downloads UEyes (Zenodo 8010312, CC-BY-4.0) after kit vet records it in VETLOG.md, "
                        "then: lune run kit ui saliency calibrate --ueyes <folder>")
        res = calibrate(a.ueyes, a.limit)
        if not res:
            return emit("fail", f"saliency calibrate: no UEyes image had a 1 s fixation map under {a.ueyes}",
                        "check saliency_maps/fixmaps_1s/<image>.png beside images/<image>.png")
        return emit("pass", f"saliency calibrate: {res['source']} - test NSS {res['test_nss']}, CC {res['test_cc']}",
                    "re-run kit ui saliency on the screens: the gate now uses these weights", **res)

    S = a.screen
    frame_p, boxes_p, spec_p = load_screen(S, a.ui, a.specs)
    if not frame_p:
        return emit("fail", f"saliency {S}: no preview frame", f"lune run kit ui {S}")
    spec = {}
    if spec_p and os.path.isfile(spec_p):
        with open(spec_p, encoding="utf-8") as fh:
            spec = json.load(fh)
    focus = a.focus or spec.get("focus")

    if mode == "gaze":
        img = Image.open(frame_p).convert("RGB")
        if a.points:
            with open(a.points, encoding="utf-8") as fh:
                pts = [tuple(p) for p in json.load(fh)]
        elif a.vlm:
            sys.path.insert(0, os.path.join(HERE, "..", "vision"))
            import vlm  # the kit's vetted local Qwen3-VL (kit/vision/models.json)
            pts = parse_points(vlm.ask(img, UIGAZE_PROMPT.format(n=a.n)), *img.size)
        else:
            return emit("fail", f"saliency gaze {S}: no gaze points", "pass --points <[[x, y], ...] picture px> or --vlm")
        if not pts:
            return emit("fail", f"saliency gaze {S}: no usable points", "check the points / the model's answer")
        S_map = saliency_map(img)
        h, w = S_map.shape
        k = w / img.size[0]
        G = points_to_map([(x * k, y * k) for x, y in pts], h, w, 0.03 * w)
        boxes = read_boxes(boxes_p, img.size[0])
        on = sum(1 for p in pts if focus and lands_on(p, boxes, focus, 0.02 * img.size[0]))
        res = {"cc": round(cc(S_map, G), 3), "kld": round(kld(S_map, G), 3), "points": len(pts),
               "on_focus": on, "first_on_focus": bool(focus and lands_on(pts[0], boxes, focus, 0.02 * img.size[0]))}
        return emit("pass", f"saliency gaze {S}: CC {res['cc']} between the first-look map and {len(pts)} gaze points; "
                            f"{on}/{len(pts)} on the focus (UIGaze: later, semantic attention - not the gate)",
                    "read it beside kit ui saliency (the first look)", **res)

    return run_check(S, frame_p, boxes_p, focus, a.min, os.path.join(a.out, S, "saliency"))


if __name__ == "__main__":
    sys.exit(main())
