"""film_keys.py - FILM YOURSELF (AAA gaps v2 A2; board/plans/archive/2026-10-22-anim-aaa-gaps-v2.md): pros shoot their own
reference of a move, then block from it. A phone video of the move (the owner, anyone) -> MediaPipe's world landmarks
(kit/anim/footage_landmarks.py, VETLOG 2026-10-16) -> the KEY FRAMES (where the hands pause, plus the fastest moment:
the strike) -> each fitted to an R6 pose by the pose-by-pointing fitter (kit/anim/roto.py): the landmarks are the
clicks, and MediaPipe's own depth decides each limb's toward / away (the one thing a single picture cannot tell).
Writes assets/animations/poses/<Move>_k<i>.roto.json per key (clip format + arms_pose) + <Move>.film.json (the key
times, so a strike's keys can take them as they are).

    python kit/anim/film_keys.py <video.mp4> --as <Move> [--start s] [--end s] [--keys 6]
    python kit/anim/film_keys.py --landmarks <x.landmarks.json> --as <Move>      (already extracted)
The video and its landmarks stay private in _artifacts/ (measure-only); only the poses are written.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import roto as R  # noqa: E402

# MediaPipe Pose (33 landmarks): nose 0, shoulders L 11 / R 12, wrists L 15 / R 16, hips L 23 / R 24, ankles L 27 / R 28
# ("left" = the person's left = the character's left)
MP = {"head": [0], "neck": [11, 12], "pelvis": [23, 24], "r_shoulder": [12], "r_hand": [16], "l_shoulder": [11],
      "l_hand": [15], "r_hip": [24], "r_foot": [28], "l_hip": [23], "l_foot": [27]}
LIMB_MP = {"Right Arm": (12, 16), "Left Arm": (11, 15), "Right Leg": (24, 28), "Left Leg": (23, 27)}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status != "fail" else 1


def clicks_of(frame):
    """world landmarks (x right, y up, z toward the camera negative) -> the fitter's clicks (an orthographic front view)"""
    P = np.asarray(frame, float)
    return {k: tuple(P[idx][:, :2].mean(0)) for k, idx in MP.items()}


def flips_of(frame):
    """each limb toward (+1) or away (-1) from the camera, from MediaPipe's depth (z smaller = nearer) - only where the
    depth is real: a limb within ~15 % of its length of the picture plane (a straight leg) is left to the fitter
    (MediaPipe's sign there is noise, and forcing it bent the fit)"""
    P = np.asarray(frame, float)
    out = {}
    for limb, (a, b) in LIMB_MP.items():
        d = P[b] - P[a]
        L = float(np.linalg.norm(d))
        if L > 1e-6 and abs(d[2]) > 0.15 * L:
            out[limb] = 1 if d[2] < 0 else -1
    return out


def key_frames(frames, fps, n_keys=6):
    """the frames where the hands pause (speed minima) + the fastest one (the strike), first and last always kept"""
    idx = [i for i, f in enumerate(frames) if f]
    if len(idx) < 3:
        return idx
    hands = np.array([np.asarray(frames[i], float)[[15, 16]].mean(0) for i in idx])
    sp = np.r_[0, np.linalg.norm(np.diff(hands, axis=0), axis=1) * fps]
    k = max(1, int(round(0.05 * fps)))                       # a 0.05 s smooth (MediaPipe jitters)
    sp = np.convolve(sp, np.ones(2 * k + 1) / (2 * k + 1), mode="same")
    picks = {0, len(idx) - 1, int(np.argmax(sp))}
    minima = [j for j in range(1, len(sp) - 1) if sp[j] <= sp[j - 1] and sp[j] <= sp[j + 1]]
    minima.sort(key=lambda j: sp[j])
    for j in minima:
        if len(picks) >= n_keys:
            break
        if all(abs(j - p) >= max(2, int(0.25 * fps)) for p in picks):   # (2 frames apart read as one pose twice)
            picks.add(j)
    return [idx[j] for j in sorted(picks)]


def from_landmarks(data, name, n_keys=6):
    frames, fps = data["frames"], float(data.get("fps") or 30)
    keys = key_frames(frames, fps, n_keys)
    out = []
    for k, i in enumerate(keys):
        clicks = clicks_of(frames[i])
        best, _ = R.fit(clicks, flips_of(frames[i]))
        rec = R.pose_record(best["params"], clicks, data.get("source", "video"), f"{name}_k{k}", best["error"])
        rec["film"] = {"frame": i, "t": round(i / fps + float(data.get("start_s", 0)), 3)}
        out.append(rec)
    return out, [round(i / fps, 3) for i in keys]


def main(argv):
    if "--as" not in argv:
        return emit("fail", "film: needs <video.mp4> --as <Move> (or --landmarks <file>)", "lune run kit anim film <video.mp4> --as KickFilm")
    name = argv[argv.index("--as") + 1]
    if not R.NAME_OK.match(name):
        return emit("fail", f"film: name {name!r}: letters, digits, _ and - only", "pick a plain name")
    n_keys = int(argv[argv.index("--keys") + 1]) if "--keys" in argv else 6
    if "--landmarks" in argv:
        data = json.load(open(argv[argv.index("--landmarks") + 1], encoding="utf-8"))
    else:
        import footage_landmarks as FL
        start = float(argv[argv.index("--start") + 1]) if "--start" in argv else 0.0
        end = float(argv[argv.index("--end") + 1]) if "--end" in argv else None
        data = FL.extract(argv[0], start, end)
        os.makedirs(os.path.join("_artifacts", "footage"), exist_ok=True)       # private, measure-only
        json.dump(data, open(os.path.join("_artifacts", "footage", f"{name}.landmarks.json"), "w"), separators=(",", ":"))
    if sum(1 for f in data["frames"] if f) < 3:
        return emit("fail", f"film {name}: MediaPipe found a body in fewer than 3 frames", "film the whole body, side-on or three-quarter, in good light")
    recs, times = from_landmarks(data, name, n_keys)
    paths = [R.write(r["name"], r) for r in recs]
    film = {"name": name, "source": data.get("source"), "key_times": times, "poses": paths,
            "errors": [r["reprojection_error_image_heights"] for r in recs],
            "loved_space_deg": [r.get("loved_space_deg") for r in recs],
            "use": "a strike's keys at these times can take each pose's arms_pose (kit/anim/strike.py) - the owner's own motion, our timing"}
    fp = os.path.join(R.POSES, f"{name}.film.json")
    json.dump(film, open(fp, "w", encoding="utf-8", newline="\n"), indent=1)
    worst = max(film["errors"]) if film["errors"] else 0
    sp = [d for d in film["loved_space_deg"] if d is not None]
    near = f"; {min(sp):.1f}-{max(sp):.1f} deg/joint from the loved pose space" if sp else ""
    return emit("pass", f"film {name}: {len(recs)} key poses at {times} s (fit error <= {worst * 100:.1f} % of the body's size{near}) -> {fp.replace(os.sep, '/')}",
                f"LOOK: lune run kit anim thumbs-style check by building a strike from these keys; or open one in the roto page to flip a limb",
                film=fp.replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
