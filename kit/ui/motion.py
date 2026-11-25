"""motion.py — reference understanding for MOTION: when and where things move in a reference clip (a GIF, an MP4 or a
folder of frames), so a reel copies real timing instead of guessing it.

    python kit/ui/read.py motion <clip> [--fps 30] [--out <dir>]      (lune run kit ui read motion <clip>)

Frame by frame: the change from the previous frame (pixels that moved by more than a step of grey). Bursts of change
become EVENTS (beats) — each with its start, peak and end (seconds), its duration, how much of the frame it touched, and
the box it touched at 1080p; a frame where half the picture changes at once is a CUT (or a flash). Runs of near-stillness
are HOLDS (a hit-stop, a beat to read the words). -> <clip>.motion.json + <clip>.motion.png (the energy over
time, events as bars). A GIF's own frame times are used when it has them; otherwise pass --fps.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time

import numpy as np
from PIL import Image, ImageDraw

W = 480  # frames are compared at this width (motion, not detail)


def load_frames(path, fps=None):
    """-> (grey frames as float arrays, the clip's size, seconds per frame)"""
    if os.path.isdir(path):
        files = sorted(f for f in os.listdir(path) if f.lower().endswith((".png", ".jpg", ".jpeg")))
        ims = [Image.open(os.path.join(path, f)) for f in files]
        return [grey(im) for im in ims], ims[0].size, 1.0 / (fps or 30)
    if path.lower().endswith(".gif"):
        g = Image.open(path)
        frames, durs = [], []
        for i in range(g.n_frames):
            g.seek(i)
            frames.append(grey(g.convert("RGB")))
            durs.append(g.info.get("duration"))
        known = [d for d in durs if d]
        dt = (np.median(known) / 1000.0) if known and not fps else 1.0 / (fps or 30)
        return frames, g.size, float(dt)
    # a video: ffmpeg writes its frames (the kit's vetted media tool)
    tmp = tempfile.mkdtemp(prefix="kit_motion_")
    try:
        rate = ["-r", str(fps)] if fps else []
        subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, *rate, os.path.join(tmp, "f_%05d.png")], check=True)
        if not fps:
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                                    "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
            num, _, den = probe.partition("/")
            fps = float(num) / float(den or 1) if num else 30.0
        files = sorted(os.listdir(tmp))
        size = Image.open(os.path.join(tmp, files[0])).size
        return [grey(Image.open(os.path.join(tmp, f))) for f in files], size, 1.0 / fps
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def grey(im):
    im = im.convert("L")
    h = max(1, round(im.height * W / im.width))
    return np.asarray(im.resize((W, h), Image.BILINEAR), dtype=np.float32)


def events_from(frames, dt, step=18.0, floor=0.004, cut_share=0.5):
    """the clip's BEATS: bursts of change found as prominence peaks of the changed share (a clip that never stops
    moving — a cutscene: the median frame changed 17% on the Persona baton touch — still has bursts on top of its
    motion), each spanning where it falls to half its prominence (never past the midpoint to the next beat): start / peak / end (s), its share of the frame,
    its box (a share of the frame), and whether it holds a CUT (a frame where more than `cut_share` changed at once).
    HOLDS are the runs of 3+ frames below the clip's quiet level (2x its 10th percentile): a hit-stop, a beat to read."""
    from scipy.signal import find_peaks, peak_widths
    n = len(frames)
    share = np.zeros(n)
    masks = [None] * n
    for i in range(1, n):
        m = np.abs(frames[i] - frames[i - 1]) > step
        masks[i] = m
        share[i] = float(m.mean())
    thr = max(floor, 2 * float(np.percentile(share[1:], 10))) if n > 1 else floor
    sm = np.convolve(share, [0.25, 0.5, 0.25], mode="same")
    sm[0] = 0
    # the bar a burst must clear is set by the biggest NON-cut change: one hard cut (94% of the frame) would otherwise hide
    # every smaller beat in the clip
    calm = sm[share <= cut_share]
    ref = float(calm.max()) if calm.size else float(sm.max())
    # (HUD beats are SMALL: a count digit and a sliver of bar moved 0.7% of the frame on the StriveCombo reel; video
    # compression noise sits at 0.1-0.15%)
    peaks, props = find_peaks(sm, prominence=max(0.003, 0.1 * ref), distance=3)
    widths = peak_widths(sm, peaks, rel_height=0.5)
    h, w = frames[0].shape
    evs = []
    for k, pk in enumerate(peaks):
        # a beat ends where its neighbour's begins: clamp to the midpoints between peaks (a big peak's width spans its
        # neighbours otherwise, and the beats overlap)
        lo = (peaks[k - 1] + pk) // 2 + 1 if k else 1
        hi = (pk + peaks[k + 1]) // 2 if k + 1 < len(peaks) else n - 1
        a = max(lo, int(np.floor(widths[2][k])))
        b = min(hi, int(np.ceil(widths[3][k])))
        union = np.zeros((h, w), bool)
        for j in range(a, b + 1):
            if masks[j] is not None:
                union |= masks[j]
        ys, xs = np.nonzero(union)
        top = a + int(np.argmax(share[a:b + 1]))
        evs.append({"start": round((a - 1) * dt, 3), "peak": round((top - 1) * dt, 3), "end": round(b * dt, 3),
                    "duration": round((b - a + 1) * dt, 3), "peak_share": round(float(share[top]), 3),
                    "box": [round(xs.min() / w, 3), round(ys.min() / h, 3), round((xs.max() + 1) / w, 3), round((ys.max() + 1) / h, 3)] if len(xs) else None,
                    "cut": bool(share[a:b + 1].max() > cut_share)})
    holds, i = [], 1
    while i < n:
        if share[i] >= thr:
            i += 1
            continue
        j = i
        while j + 1 < n and share[j + 1] < thr:
            j += 1
        if j - i + 1 >= 3:
            holds.append({"from": round((i - 1) * dt, 3), "to": round(j * dt, 3), "duration": round((j - i + 1) * dt, 3)})
        i = j + 1
    return evs, holds, share, thr


def piece_beats(frames, dt, elements, size):
    """motion PER PIECE: each element of a `kit ui read` (its box at 1080p) is cut out of every frame and its own beats
    found the same way as the whole clip's -> {label: [peak seconds]} (which piece moved on which beat)"""
    h, w = frames[0].shape
    out = {}
    for e in elements:
        x0, y0, x1, y1 = e["box_1080"]
        bx = (int(x0 / 1920 * w), int(y0 / 1080 * h), max(int(x0 / 1920 * w) + 2, int(x1 / 1920 * w)), max(int(y0 / 1080 * h) + 2, int(y1 / 1080 * h)))
        crops = [f[bx[1]:bx[3], bx[0]:bx[2]] for f in frames]
        if crops[0].size < 16:
            continue
        evs, _holds, _share, _thr = events_from(crops, dt)
        label, k = e["label"], 2
        while label in out:
            label, k = f"{e['label']} {k}", k + 1
        out[label] = [ev["peak"] for ev in evs]
    return out


def punch_track(evs, node="Hud.Call", prop="scale", lift=0.22, settle=0.18):
    """the clip's beats as a reel track to paste: a punch (up to 1 + lift, back in `settle` s) on every beat's PEAK"""
    keys = [[0, 1.0]]
    for e in evs:
        t = e["peak"]
        while len(keys) > 1 and keys[-1][0] >= t + 0.03:  # (beats closer than the settle: the next punch cuts the last short)
            keys.pop()
        if t - 0.001 > keys[-1][0]:
            keys.append([round(t - 0.001, 3), 1.0])
        keys += [[round(t + 0.03, 3), round(1 + lift, 3)], [round(t + settle, 3), 1.0]]
    return {"node": node, "prop": prop, "ease": "out", "keys": keys}


def strip(share, thr, evs, dt, path):
    """the energy over time (each frame a column), the threshold as a line, events as bars underneath"""
    n = len(share)
    cw = max(2, min(8, 1200 // max(1, n)))
    H, top = 180, 140
    im = Image.new("RGB", (n * cw + 20, H), (18, 16, 20))
    d = ImageDraw.Draw(im)
    peak = max(float(share.max()), thr * 2, 1e-6)
    for i, s in enumerate(share):
        v = int((top - 10) * min(1.0, s / peak))
        d.rectangle([10 + i * cw, top - v, 10 + i * cw + cw - 2, top], fill=(220, 200, 150))
    ty = top - int((top - 10) * thr / peak)
    d.line([10, ty, 10 + n * cw, ty], fill=(200, 60, 70))
    for e in evs:
        x0 = 10 + int((e["start"] / dt + 1) * cw)
        x1 = 10 + int((e["end"] / dt + 1) * cw)
        d.rectangle([x0, top + 12, max(x0 + 2, x1), top + 26], fill=(208, 48, 63) if e["cut"] else (169, 140, 255))
    im.save(path)


def cmd_motion(a):
    def emit(status, summary, next_action, **extra):
        print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
        return 0 if status == "pass" else 1

    if not os.path.exists(a.clip):
        return emit("fail", f"motion: no clip at {a.clip}", "a GIF, an MP4 or a folder of frames")
    t0 = time.time()
    frames, size, dt = load_frames(a.clip, a.fps)
    if len(frames) < 3:
        return emit("fail", f"motion: {len(frames)} frame(s) is not a clip", "a reference with motion in it")
    evs, holds, share, thr = events_from(frames, dt)
    pieces = None
    if getattr(a, "pieces", None):
        pieces = piece_beats(frames, dt, json.load(open(a.pieces, encoding="utf-8"))["elements"], size)
    for e in evs:
        if e["box"]:
            e["box_1080"] = [round(e["box"][0] * 1920), round(e["box"][1] * 1080), round(e["box"][2] * 1920), round(e["box"][3] * 1080)]
    out_dir = a.out or os.path.dirname(a.clip) or "."
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(a.clip.rstrip("/\\")))[0]
    json_path = os.path.join(out_dir, f"{stem}.motion.json")
    png_path = os.path.join(out_dir, f"{stem}.motion.png")
    with open(json_path, "w", encoding="utf-8", newline=chr(10)) as fh:
        json.dump({"schema": 1, "clip": a.clip, "frames": len(frames), "size": list(size), "seconds_per_frame": round(dt, 4),
                   "length": round(len(frames) * dt, 3), "threshold": round(thr, 4), "events": evs, "holds": holds,
                   "reel_track": punch_track(evs), "pieces": pieces,
                   "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, fh, indent=1)
    strip(share, thr, evs, dt, png_path)
    durs = sorted(e["duration"] for e in evs)
    cuts = sum(1 for e in evs if e["cut"])
    what = "; ".join(f"{e['start']:.2f}-{e['end']:.2f}s{' CUT' if e['cut'] else ''}" for e in evs[:8])
    return emit("pass", f"motion: {stem} — {len(frames)} frames, {len(frames) * dt:.2f}s; {len(evs)} event(s) ({cuts} with a cut), "
                f"median {durs[len(durs) // 2] if durs else 0:.2f}s, {len(holds)} hold(s) ({time.time() - t0:.0f}s): {what}",
                f"LOOK at {png_path}; paste its reel_track (a punch on every beat; rename the node) into a <Screen>.reel.json",
                motion=json_path, strip=png_path)
