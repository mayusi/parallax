"""track.py - FOLLOW THE CAMERA inside a shot (motion tracking, matchmoving in two dimensions).

    lune run kit vfx track <set> [--beat N] [--window a,b] [--width 960]
    python kit/vfx/track.py --frames <dir of .png> --fps 24 --out <dir> [--hue lo,hi]

Why: every reading the kit takes off a scene - the timing read (which frames are held), the trace (which frames are
one drawing) - compares a frame with the one before it. When the CAMERA moves inside the shot, every frame differs
from the last, and the reading says "everything changed on every frame": a pan reads as an effect on ones. This tool
measures the camera: it follows points of the BACKGROUND (everything that is not the effect's colour) from frame to
frame, fits the move they share (a shift, a zoom, a turn: the effect and anything else that moves on its own are
outvoted), and gives every frame's place in the FIRST frame's picture. `stabilise` then lays the frames over each
other so that the background stands still: what still changes is the effect.

`lune run kit vfx trace <set> --beat N` measures this itself: a beat whose camera moves is REFUSED without `--track`
(its trace would read every frame as a new drawing), and with `--track` it is traced from the stabilised frames, inside
the window every frame covers.

Its own checks: a frame pair is FOLLOWED when 12 or more background points agree on one move (half of all the points
or more) to within a pixel; a shot is followed when 4 in 5 of its pairs are. A shot that cannot be followed (a flat
background, a cut, a flash) is said to be so: nothing is guessed.
Writes build/vfx/track/<set>/beat<k>.json (every frame's move, the pan and zoom in plain numbers) and
beat<k>_track.png: the first, middle and last frame as the clip has them (top) and stabilised (bottom), a grid of
lines over both - on the bottom row the background sits under the same lines in all three. OPEN it.
Prints one JSON line {schema, status, summary, next_action, ...}.

Limits, said plainly: it follows a FLAT picture (a shift, a zoom, a turn). A camera that travels through depth makes
near things slide past far ones: the far background is followed, the near slides. It reads the picture's own frames:
a clip already cropped or reframed by an uploader is followed as it is.
"""

import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dense  # noqa: E402

MEASURED = os.path.join("assets", "effects", "refs_measured")
BUILD = os.path.join("build", "vfx", "track")
POINTS = 12        # a frame pair is followed by this many agreeing background points or more
AGREE = 0.5        # ... that are this share of all the points tried
RESIDUAL = 1.0     # px: ... and that fit the shared move this well, on average
FOLLOWED = 0.8     # a shot is followed when this share of its frame pairs are
STILL = 0.00055    # of the frame's width, a frame (0.35 px at 640): a steady pan under this is no pan
DRIFT = 0.0047     # of the frame's width (3 px at 640): the furthest ANY frame of a standing camera sits from the first
ZOOM = 0.01        # the most any frame of a standing camera is larger or smaller than the first
TURN = 0.3         # degrees: the most any frame of a standing camera is turned against the first
SPREAD = 3         # the agreeing points must lie in this many of the frame's four quarters (one moving thing is not the camera)


def out(status, summary, next_action, **extra):
    print(json.dumps(dict({"schema": 1, "status": status, "summary": summary, "next_action": next_action}, **extra)))
    return 0 if status in ("pass", "warn") else 1


def grey(frame):
    """the frame in grey, its grain smoothed away: points are followed on what is IN the picture (an edge, a light),
    never on film grain or compression noise, which is new on every frame and reads as a camera that trembles"""
    return cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY), (0, 0), 1.6)


def background(frames, hue):
    """per frame, where points may be followed: everything that is NOT the effect (by its measured colour), a few
    pixels clear of it. With no hue every pixel may be: what moves on its own is outvoted when the move is fitted"""
    if hue is None:
        return [None] * len(frames)
    masks, _ = dense.effect_mask(frames, hue)
    kernel = np.ones((9, 9), np.uint8)
    return [(cv2.dilate(m.astype(np.uint8), kernel) == 0).astype(np.uint8) * 255 for m in masks]


def move(prev, cur, mask=None):
    """the move the background shares between two frames -> (M: a 3x3 matrix taking a point of `cur` to where it was
    in `prev`, {"points", "agree", "residual", "followed"}). Not followed: M is the identity"""
    a, b = grey(prev), grey(cur)
    info = {"points": 0, "agree": 0.0, "residual": None, "followed": False}
    eye = np.eye(3)
    pts = cv2.goodFeaturesToTrack(a, maxCorners=600, qualityLevel=0.01, minDistance=7, mask=mask, blockSize=7)
    if pts is None or len(pts) < POINTS:
        info["points"] = 0 if pts is None else int(len(pts))
        return eye, info
    nxt, ok, _ = cv2.calcOpticalFlowPyrLK(a, b, pts, None, winSize=(21, 21), maxLevel=3,
                                          criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
    back, ok2, _ = cv2.calcOpticalFlowPyrLK(b, a, nxt, None, winSize=(21, 21), maxLevel=3,
                                            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
    good = (ok.ravel() == 1) & (ok2.ravel() == 1) & (np.linalg.norm((back - pts).reshape(-1, 2), axis=1) < 0.7)
    p0, p1 = pts.reshape(-1, 2)[good], nxt.reshape(-1, 2)[good]
    info["points"] = int(len(p0))
    if len(p0) < POINTS:
        return eye, info
    m, inl = cv2.estimateAffinePartial2D(p1, p0, method=cv2.RANSAC, ransacReprojThreshold=1.5, maxIters=2000, confidence=0.995)
    if m is None or inl is None:
        return eye, info
    inl = inl.ravel() == 1
    agree = float(inl.mean())
    fitted = (np.hstack([p1[inl], np.ones((int(inl.sum()), 1))]) @ m.T) if inl.any() else np.zeros((0, 2))
    residual = float(np.linalg.norm(fitted - p0[inl], axis=1).mean()) if inl.any() else None
    info.update(agree=round(agree, 3), residual=None if residual is None else round(residual, 3))
    h, w = a.shape[:2]
    quarters = {(int(x >= w / 2.0), int(y >= h / 2.0)) for x, y in p0[inl]}
    info["quarters"] = len(quarters)
    if int(inl.sum()) < POINTS or agree < AGREE or residual is None or residual > RESIDUAL or len(quarters) < SPREAD:
        return eye, info
    info["followed"] = True
    return np.vstack([m, [0, 0, 1]]), info


def parts(m):
    """a move in plain numbers: (shift x, shift y in px, zoom, turn in degrees)"""
    zoom = math.hypot(m[0, 0], m[1, 0])
    return float(m[0, 2]), float(m[1, 2]), float(zoom), float(math.degrees(math.atan2(m[1, 0], m[0, 0])))


def track(frames, hue=None):
    """every frame's place in the first frame's picture -> {"frames", "size", "steps": [per frame pair], "to_first":
    [3x3 per frame], "followed": share of pairs, "known", "moves", "pan": px a frame, "drift": px in all, "zoom"}"""
    n = len(frames)
    masks = background(frames, hue)
    to_first, steps = [np.eye(3)], []
    h, w = frames[0].shape[:2]
    mid = np.array([w / 2.0, h / 2.0, 1.0])
    for i in range(1, n):
        m, info = move(frames[i - 1], frames[i], masks[i - 1])
        _, _, zoom, turn = parts(m)
        at = m @ mid  # a step's shift is read at the picture's CENTRE: a zoom or a turn leaves that point where it is
        steps.append(dict(info, shift=[round(float(at[0] - mid[0]), 3), round(float(at[1] - mid[1]), 3)], zoom=round(zoom, 5), turn=round(turn, 4)))
        to_first.append(to_first[-1] @ m)
    followed = float(np.mean([s["followed"] for s in steps])) if steps else 0.0
    known = bool(steps) and followed >= FOLLOWED
    # the pan is the shift the steps SHARE (the median of their vectors): a tremble that points a new way on every
    # frame shares none, a pan points one way
    vectors = np.array([s["shift"] for s in steps if s["followed"]], dtype=np.float64)
    pan = float(np.hypot(*np.median(vectors, axis=0))) if len(vectors) else 0.0
    dx, dy, zoom, turn = parts(to_first[-1])
    # the picture's centre is where a zoom or a turn leaves a point: measure the drift there, not at the corner
    centre = to_first[-1] @ mid
    dx, dy = float(centre[0] - mid[0]), float(centre[1] - mid[1])
    drift = float(math.hypot(dx, dy))
    # the camera MOVES when ANY frame sits away from the first: a shake that ends where it began, a pan there and
    # back, a roll, a zoom in and out all leave the last frame on the first (a review, 2026-11-14: read at the last
    # frame only, an impact shake was "standing" and every frame traced as a new drawing)
    far, big, tilt = 0.0, 0.0, 0.0
    for t in to_first:
        c = t @ mid
        _, _, z, a = parts(t)
        far, big, tilt = max(far, math.hypot(c[0] - mid[0], c[1] - mid[1])), max(big, abs(z - 1)), max(tilt, abs(a))
    moves = known and (pan > STILL * w or far > DRIFT * w or big > ZOOM or tilt > TURN)
    return {"frames": n, "size": [int(w), int(h)], "steps": steps, "to_first": [t.tolist() for t in to_first],
            "followed": round(followed, 3), "known": known, "moves": bool(moves), "pan": round(pan, 3), "drift": round(drift, 2),
            "far": round(far, 2), "zoom": round(zoom, 4), "turn": round(turn, 3), "tilt": round(tilt, 3), "swell": round(big, 4),
            "direction": [round(dx, 2), round(dy, 2)]}


def window(tr):
    """the part of the first frame's picture that EVERY frame covers -> (x0, y0, x1, y1) in px, or None when there is
    none. The largest upright box inside the common cover, found by shrinking from its bounds"""
    w, h = tr["size"]
    cover = np.ones((h, w), np.uint8)
    for t in tr["to_first"]:
        cover &= cv2.warpAffine(np.ones((h, w), np.uint8), np.asarray(t)[:2], (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
    if not cover.any():
        return None
    ys, xs = np.where(cover > 0)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    while x1 - x0 > 8 and y1 - y0 > 8 and not cover[y0:y1, x0:x1].all():
        # take a line off the side that has the most uncovered pixels in it
        sides = {"l": (cover[y0:y1, x0] == 0).mean(), "r": (cover[y0:y1, x1 - 1] == 0).mean(),
                 "t": (cover[y0, x0:x1] == 0).mean(), "b": (cover[y1 - 1, x0:x1] == 0).mean()}
        worst = max(sides, key=sides.get)
        if worst == "l":
            x0 += 1
        elif worst == "r":
            x1 -= 1
        elif worst == "t":
            y0 += 1
        else:
            y1 -= 1
    return (x0, y0, x1, y1) if cover[y0:y1, x0:x1].all() else None


def stabilise(frames, tr, crop=True):
    """the frames laid into the first frame's picture (the background stands still) -> (frames, window). With crop,
    cut to the window every frame covers; (None, None) when the frames share no window"""
    w, h = tr["size"]
    laid = [cv2.warpAffine(f, np.asarray(t)[:2], (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            for f, t in zip(frames, tr["to_first"])]
    win = window(tr)
    if win is None:
        return None, None
    if crop:
        x0, y0, x1, y1 = win
        laid = [f[y0:y1, x0:x1] for f in laid]
    return np.stack(laid), win


def says(tr):
    """the camera in plain words"""
    if not tr["known"]:
        return (f"the camera could not be followed ({tr['followed']:.0%} of the frame pairs: too little background detail, a cut or a flash)")
    if not tr["moves"]:
        return f"the camera stands still (no frame further than {tr.get('far', tr['drift']):g} px from the first)"
    dx, dy = tr["direction"]
    way = []
    # (a later frame's centre lies to the RIGHT in the first frame's picture when the camera has moved right)
    if abs(dx) > 1:
        way.append("right" if dx > 0 else "left")
    if abs(dy) > 1:
        way.append("down" if dy > 0 else "up")
    bits = []
    w = tr["size"][0]
    if tr["pan"] > STILL * w or tr["drift"] > DRIFT * w:
        bits.append(f"pans {tr['pan']:g} px a frame" + (f" ({' and '.join(way)})" if way else "") + f", {tr['drift']:g} px in all")
    if not bits and tr.get("far", 0) > DRIFT * w:
        bits.append(f"shakes or moves and comes back: up to {tr['far']:g} px from where it began")
    if abs(tr["zoom"] - 1) <= ZOOM and tr.get("swell", 0) > ZOOM:
        bits.append(f"zooms and comes back (up to x{1 + tr['swell']:.3f})")
    if abs(tr["turn"]) <= 0.5 and tr.get("tilt", 0) > TURN:
        bits.append(f"rolls up to {tr['tilt']:.1f} degrees")
    if abs(tr["zoom"] - 1) > ZOOM:
        bits.append(f"zooms {'in' if tr['zoom'] < 1 else 'out'} x{max(tr['zoom'], 1 / tr['zoom']):.3f}")
    if abs(tr["turn"]) > 0.5:
        bits.append(f"turns {abs(tr['turn']):.1f} degrees")
    return "the camera " + ", ".join(bits) + f" (followed on {tr['followed']:.0%} of the frame pairs)"


def look(frames, tr, path, tile=420):
    """the LOOK picture: first, middle, last frame as the clip has them (top) and stabilised, uncropped (bottom), the
    same grid of lines over all six - on the bottom row the background sits under the same lines"""
    n = len(frames)
    pick = [0, n // 2, n - 1]
    laid, win = stabilise(frames, tr, crop=False)
    w, h = tr["size"]
    th = int(round(tile * h / float(w)))
    page = Image.new("RGB", (3 * (tile + 6) + 6, 2 * (th + 24) + 6), (20, 20, 24))
    pen = ImageDraw.Draw(page)
    for row, src, name in ((0, frames, "as the clip has it"), (1, laid if laid is not None else frames, "stabilised")):
        for col, k in enumerate(pick):
            x, y = 6 + col * (tile + 6), 6 + row * (th + 24)
            pen.text((x + 2, y + 3), f"frame {k} - {name}", fill=(225, 225, 225))
            im = Image.fromarray(np.asarray(src[k])).resize((tile, th), Image.LANCZOS)
            page.paste(im, (x, y + 20))
            for g in range(1, 6):
                pen.line([x + g * tile // 6, y + 20, x + g * tile // 6, y + 20 + th], fill=(0, 255, 255), width=1)
            for g in range(1, 4):
                pen.line([x, y + 20 + g * th // 4, x + tile, y + 20 + g * th // 4], fill=(0, 255, 255), width=1)
            if row == 1 and win is not None:
                x0, y0, x1, y1 = [v * tile / float(w) for v in win]
                pen.rectangle([x + x0, y + 20 + y0, x + x1 - 1, y + 20 + y1 - 1], outline=(255, 215, 80), width=2)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    page.save(path)


def _opts(argv):
    opts, names, i = {}, [], 0
    while i < len(argv):
        if argv[i].startswith("--"):
            if i + 1 >= len(argv):
                raise ValueError(f"{argv[i]} needs a value")
            opts[argv[i]] = argv[i + 1]
            i += 1
        else:
            names.append(argv[i])
        i += 1
    return opts, names


def _main(argv):
    opts, names = _opts(argv)
    usage = "lune run kit vfx track <set> [--beat N] [--window a,b]"
    hue = tuple(float(x) for x in opts["--hue"].split(",")) if "--hue" in opts else None
    if hue is not None and len(hue) != 2:
        return out("fail", "track: --hue is lo,hi", usage)
    if "--frames" in opts:
        folder = opts["--frames"]
        files = sorted(f for f in os.listdir(folder) if f.lower().endswith((".png", ".jpg"))) if os.path.isdir(folder) else []
        if len(files) < 2:
            return out("fail", f"track: fewer than two pictures in {folder}", "--frames <a folder of .png frames in order>")
        pictures = [np.asarray(Image.open(os.path.join(folder, f)).convert("RGB")) for f in files]
        if len({p.shape for p in pictures}) > 1:
            return out("fail", f"track: the pictures in {folder} are not all one size", "frames of ONE shot, as the clip gave them")
        frames = np.stack(pictures)
        out_dir, stem, what = opts.get("--out", os.path.join(BUILD, "frames")), "track", f"track {folder}"
    else:
        if not names:
            return out("fail", "track: needs a scene set", usage)
        name = names[0]
        import breakdown
        import denseclip as DC
        try:
            meta = json.load(open(os.path.join(MEASURED, f"{name}.breakdown.json"), encoding="utf-8"))
        except (OSError, ValueError):
            return out("fail", f"track {name}: no breakdown to read from", f"lune run kit vfx breakdown {name} --clip <file> first")
        clip = opts.get("--clip") or meta.get("clip")
        if not clip or not os.path.isfile(clip):
            return out("fail", f"track {name}: the scene's clip is not on this machine ({clip})",
                       f"put the owner-approved clip back under assets/effects/refs/{name}/clip/ or pass --clip <file>")
        beats = breakdown.beat_rows(name)
        if not beats:
            return out("fail", f"track {name}: no beat with a scene time", f"fill assets/effects/refs_measured/{name}.beats.md first")
        k = int(opts.get("--beat", next((i for i, b in enumerate(beats) if b[3]), 0)))
        if not 0 <= k < len(beats):
            return out("fail", f"track {name}: no beat {k} (there are {len(beats)})", "name a beat, from 0")
        label, t0, t1, _ = beats[k]
        hue = hue or DC.measured_hue(MEASURED, f"{name}_scene", name)
        info = DC.probe(clip)
        if "--window" in opts:
            a, b = [float(x) for x in opts["--window"].split(",")]
        else:
            read = DC.read_beat(clip, t0, t1, [c["t"] for c in meta.get("cuts", [])], hue, info)
            if read["main"] is None:
                return out("fail", f"track {name} beat {k}: no shot of this beat could be read", f"name the stretch: --window a,b (clip seconds)")
            a, b = read["shots"][read["main"]]["from"], read["shots"][read["main"]]["to"]
        b = min(b, a + 6.0)
        frames = DC.frames(clip, a, b, max(320, int(opts.get("--width", 960))), info)
        out_dir, stem, what = os.path.join(BUILD, name), f"beat{k}", f"track {name} beat {k} ({label}, {a:.2f}-{b:.2f} s)"
        if len(frames) < 2:
            return out("fail", f"{what}: fewer than two frames", "check the window")
    tr = track(frames, hue)
    os.makedirs(out_dir, exist_ok=True)
    store = os.path.join(out_dir, f"{stem}.json")
    with open(store, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(tr, fh, separators=(",", ":"))
    picture = os.path.join(out_dir, f"{stem}_track.png")
    look(frames, tr, picture)
    numbers = {k: tr[k] for k in ("frames", "followed", "known", "moves", "pan", "drift", "zoom", "turn")}
    numbers.update(track=store.replace(os.sep, "/"), look=picture.replace(os.sep, "/"), window=window(tr))
    if not tr["known"]:
        return out("fail", f"{what}: {says(tr)}", "a shot with too little standing background cannot be followed: trace a beat whose background shows, or box the effect (--box) on a stretch where the camera holds",
                   **numbers)
    nxt = (f"OPEN {numbers['look']}: on the bottom row the background sits under the same lines in all three. Then: lune run kit vfx trace <set> --beat N --track"
           if tr["moves"] else "nothing to stabilise: trace it as it is (lune run kit vfx trace <set> --beat N)")
    return out("pass", f"{what}: {says(tr)}", nxt, **numbers)


def main(argv):
    try:
        return _main(argv)
    except Exception as e:  # noqa: BLE001 - a command answers in one line, never with a traceback
        return out("fail", f"track: could not be run ({type(e).__name__}: {str(e)[:200]})", "lune run kit vfx track <set> [--beat N] [--window a,b]")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
