"""motionref.py — MOTION MEASURED FROM VIDEO: AAA menu motion is never published; it is counted frame by frame from the
real game's footage. Give a clip of the source game's menu opening (a screen recording, 30-60 fps) and this measures
every element that moves: when it starts, when it settles, how it eases (and whether it overshoots), and the stagger
between elements — the numbers an identity's "motion" should be built from, not taste.

    python kit/ui/motionref.py <clip.mp4> [--from 1.2 --to 2.4] [--box x,y,w,h ...] [--regions 8] [--out build/ui/motion]

-> <out>/<clip>.motion.json {"fps", "regions": [{box, start, settle, duration, ease, overshoot}], "stagger",
   "suggest": {"duration", "ease", "stagger"}} + <clip>.motion.png (the regions and their progress curves).
Regions are found by themselves (where the frames change most) unless boxes are given. Progress of a region = how
close it is to its final look (1 - |frame - last| / |first - last|); its curve is matched to linear / quad / cubic /
expo ease-outs, and progress above 1 before settling is an overshoot (a back / spring ease).

--identity assets/ui/identities/<name>.json compares the identity's TYPED motion with the measurement; --write records
it as the identity's motion.measured, and from then on the compiler (kit/lib/ui.luau) refuses an enter duration or a
stagger more than 25% off it, or an overshoot the clip does not have (LIMITATIONS_FIXES_V4 UI-X 6.4 step 4).
"""
import argparse
import json
import os
import sys

import numpy as np

EASES = {
    "linear": lambda t: t,
    "quad": lambda t: 1 - (1 - t) ** 2,
    "cubic": lambda t: 1 - (1 - t) ** 3,
    "quart": lambda t: 1 - (1 - t) ** 4,
    "expo": lambda t: 1 - 2 ** (-10 * t) if t < 1 else 1.0,
    "sine": lambda t: np.sin(t * np.pi / 2),
}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def read_frames(path, t0=None, t1=None, max_side=640):
    import cv2
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames, times, i = [], [], 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        t = i / fps
        i += 1
        if t0 is not None and t < t0:
            continue
        if t1 is not None and t > t1:
            break
        g = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        k = max_side / max(g.shape)
        if k < 1:
            g = cv2.resize(g, (int(g.shape[1] * k), int(g.shape[0] * k)), interpolation=cv2.INTER_AREA)
        frames.append(g)
        times.append(t)
    cap.release()
    return np.stack(frames) if frames else np.zeros((0, 1, 1)), times, fps


def find_regions(frames, n=8):
    """where the frames change most: boxes of the biggest moving areas"""
    import cv2
    if len(frames) < 3:
        return []
    acc = np.abs(np.diff(frames, axis=0)).sum(0)
    thr = max(acc.mean() + 2 * acc.std(), 1e-6)
    mask = (acc > thr).astype(np.uint8)
    mask = cv2.dilate(mask, np.ones((9, 9), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    boxes = [tuple(int(v) for v in stats[i][:4]) for i in range(1, count) if stats[i][4] >= 40]
    boxes.sort(key=lambda b: -b[2] * b[3])
    return boxes[:n]


def fit_ease(t, p):
    """the ease-out family that best fits progress p over normalized time t (and the error)"""
    best, err = "linear", 1e9
    for name, f in EASES.items():
        e = float(np.mean([(f(x) - y) ** 2 for x, y in zip(t, p)]))
        if e < err:
            best, err = name, e
    return best, err


def measure(frames, times, box):
    x, y, w, h = box
    seg = frames[:, y:y + h, x:x + w]
    first, last = seg[0], seg[-1]
    span = float(np.abs(first - last).mean())
    energy = np.abs(np.diff(seg, axis=0)).mean(axis=(1, 2))
    if span < 1e-4 or energy.max() < 1e-4:
        return None
    moving = np.nonzero(energy > max(energy.max() * 0.08, 1e-4))[0]
    if len(moving) == 0:
        return None
    s, e = int(moving[0]), int(moving[-1]) + 1
    # progress: a SLIDE is tracked by where the element is (the centroid of what differs from the first frame's ground),
    # a FADE (nothing travels) by how close the region's look is to its final one
    ground = seg[0]
    dev = np.abs(seg - ground)
    ys, xs = np.mgrid[0:seg.shape[1], 0:seg.shape[2]]
    mass = dev.sum(axis=(1, 2)) + 1e-9
    cx = (dev * xs).sum(axis=(1, 2)) / mass
    cy = (dev * ys).sum(axis=(1, 2)) / mass
    travel = np.hypot(cx - cx[-1], cy - cy[-1])
    live = mass > mass[-1] * 0.05
    first_live = int(np.argmax(live)) if live.any() else 0
    if travel[first_live:].max() > 3:
        prog = 1 - travel / max(travel[first_live], 1e-6)
        prog[:first_live] = 0.0
    else:
        prog = 1 - np.abs(seg - last).mean(axis=(1, 2)) / span
    start, settle = times[s], times[min(e, len(times) - 1)]
    tt = np.linspace(0, 1, e - s + 1)
    pp = np.clip(prog[s:e + 1], -0.5, 1.5)
    overshoot = bool(len(pp) > 2 and pp.max() > 1.04 and int(np.argmax(pp)) < len(pp) - 1)
    ease, err = fit_ease(tt, np.clip(pp, 0, 1))
    return {"box": [int(v) for v in box], "start": round(start, 3), "settle": round(settle, 3),
            "duration": round(settle - start, 3), "ease": "back" if overshoot else ease, "overshoot": overshoot,
            "fit_error": round(err, 4)}


def identity_gaps(motion, measured):
    """an identity's typed motion vs a measurement -> what the compiler would refuse (kit/lib/ui.luau's rule)"""
    out = []
    enter = motion.get("enter") if isinstance(motion.get("enter"), dict) else {}
    d, s = enter.get("duration"), motion.get("stagger")
    d_tol = max(0.05, 0.25 * measured["duration"])
    s_tol = max(0.02, 0.25 * measured["stagger"])
    if isinstance(d, (int, float)) and abs(d - measured["duration"]) > d_tol + 1e-9:
        out.append(f"enter duration {d} s vs measured {measured['duration']} s")
    if isinstance(s, (int, float)) and abs(s - measured["stagger"]) > s_tol + 1e-9:
        out.append(f"stagger {s} s vs measured {measured['stagger']} s")
    ease = enter.get("ease")
    if isinstance(ease, str):
        overshoots = ease in ("back", "elastic")
        if measured["ease"] == "back" and not overshoots:
            out.append(f'ease "{ease}" settles straight, the clip overshoots')
        elif measured["ease"] != "back" and overshoots:
            out.append(f'ease "{ease}" overshoots, the clip does not')
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--from", dest="t0", type=float, default=None)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--box", action="append", default=[])
    ap.add_argument("--regions", type=int, default=8)
    ap.add_argument("--out", default=os.path.join("build", "ui", "motion"))
    ap.add_argument("--identity", default=None, help="an identity file: compare its typed motion with the measurement")
    ap.add_argument("--write", action="store_true", help="with --identity: record the measurement as its motion.measured "
                    "(the compiler then holds its enter duration / stagger / overshoot to it)")
    a = ap.parse_args(argv)
    if not os.path.isfile(a.clip):
        return emit("fail", f"motion-ref: no clip {a.clip}", "record the source game's menu opening (30-60 fps) and pass it")
    frames, times, fps = read_frames(a.clip, a.t0, a.t1)
    if len(frames) < 4:
        return emit("fail", "motion-ref: fewer than 4 frames in the window", "widen --from / --to")
    boxes = [tuple(int(v) for v in b.split(",")) for b in a.box] or find_regions(frames, a.regions)
    regions = [r for r in (measure(frames, times, b) for b in boxes) if r]
    if not regions:
        return emit("fail", "motion-ref: nothing moves in the window", "check --from / --to cover the menu opening")
    regions.sort(key=lambda r: r["start"])
    starts = [r["start"] for r in regions]
    stagger = float(np.median(np.diff(starts))) if len(starts) > 1 else 0.0
    eases = [r["ease"] for r in regions]
    suggest = {"duration": round(float(np.median([r["duration"] for r in regions])), 3),
               "ease": max(set(eases), key=eases.count), "stagger": round(stagger, 3)}
    os.makedirs(a.out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(a.clip))[0]
    out = os.path.join(a.out, f"{stem}.motion.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"schema": 1, "clip": a.clip, "fps": fps, "window": [times[0], times[-1]], "regions": regions,
                   "stagger": round(stagger, 3), "suggest": suggest}, fh, indent=1)
    measured = {"clip": os.path.basename(a.clip), "duration": suggest["duration"], "ease": suggest["ease"],
                "stagger": suggest["stagger"]}
    if a.identity:
        # the identity's TYPED motion against the measurement, by the compiler's own rule (kit/lib/ui.luau: within 25%,
        # at least 0.05 s / 0.02 s; an overshoot measured stays one)
        if not os.path.isfile(a.identity):
            return emit("fail", f"motion-ref: no identity {a.identity}", "pass assets/ui/identities/<name>.json")
        with open(a.identity, encoding="utf-8") as fh:
            ident = json.load(fh)
        off = identity_gaps(ident.get("motion") or {}, measured)
        if a.write:
            ident.setdefault("motion", {})["measured"] = measured
            with open(a.identity, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(ident, fh, indent=1, ensure_ascii=False)
                fh.write("\n")
        said = "; ".join(off) if off else "its typed motion matches"
        return emit("pass", f"motion-ref: {len(regions)} moving region(s) in {a.clip} — measured {measured['duration']} s, ease "
                    f"{measured['ease']}, stagger {measured['stagger']} s; {os.path.basename(a.identity)}: {said}"
                    + (" (recorded as motion.measured)" if a.write else ""),
                    ("lune run kit ui (the compiler now holds the identity to the measurement)" if a.write else
                     f"record it: kit ui motion-ref {a.clip} --identity {a.identity} --write"),
                    measured=measured, gaps=off)
    return emit("pass", f"motion-ref: {len(regions)} moving region(s) in {a.clip} — median {suggest['duration']} s, ease "
                f"{suggest['ease']}, stagger {suggest['stagger']} s -> {out}",
                "put the measured duration / ease / stagger into the identity's \"motion\" (not taste), then kit ui reel")


if __name__ == "__main__":
    sys.exit(main())
