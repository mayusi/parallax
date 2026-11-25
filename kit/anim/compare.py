"""compare.py — the REFERENCE BESIDE THE RESULT (AAA plan #6, board/plans/archive/2026-10-18-aaa-anim-gaps.md): the dossier
turns footage into numbers, but no one SAW the reference next to our clip. For each of the dossier's
`reference_frames` ({phase, video, t, game_t, note}) this puts the footage frame (left) beside our clip's look frame at
the same phase (right) -> build/animations/<Name>.compare.png (private: footage frames stay out of git).

    python -I kit/anim/compare.py <Name> [--dossier <move>] [--view three-quarter|game]
(run isolated: it reads downloaded footage; the kit modules are found from this file's own folder)"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

BUILD = os.path.join(os.environ.get("KIT_BUILD", "build"), "animations")


def footage_frame(video, t, h=320):
    import cv2
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
    ok, f = cap.read()
    cap.release()
    if not ok:
        return None
    if h:                                                  # h = None: the frame at its own size (kit anim sheet)
        s = h / f.shape[0]
        f = cv2.resize(f, (int(f.shape[1] * s), h))
    return f[:, :, ::-1]                                   # BGR -> RGB


def ours_frame(name, t, view, fps, h=320):
    from PIL import Image
    d = os.path.join(BUILD, f"{name}.r6.look")
    frames = sorted(glob.glob(os.path.join(d, f"{view}_*.png")))
    if not frames:
        return None
    idx = [int(os.path.basename(f).split("_")[-1].split(".")[0]) for f in frames]
    want = min(range(len(frames)), key=lambda k: abs(idx[k] - idx[0] - round(t * fps)))
    im = Image.open(frames[want]).convert("RGB")
    return im.resize((int(im.width * h / im.height), h))


def sheet(name, dossier=None, view="three-quarter"):
    import numpy as np
    from PIL import Image, ImageDraw
    import proc_dossier as PD
    clip = json.load(open(os.path.join(BUILD, f"{name}.clip.json"), encoding="utf-8"))
    if dossier is None:
        mv = os.path.join("assets", "animations", f"{name}.move.json")
        dossier = json.load(open(mv, encoding="utf-8")).get("dossier") if os.path.exists(mv) else PD.snake(name)
    d = json.load(open(os.path.join(PD.DIR, f"{dossier}.json"), encoding="utf-8"))
    refs = d.get("reference_frames") or []
    if not refs:
        raise SystemExit(f"dossier {dossier} has no reference_frames ({{phase, video, t, game_t}}) - add the footage moments")
    fps = float(clip.get("fps") or 60)
    rows = []
    for r in refs:
        a = footage_frame(r["video"], r["t"])
        b = ours_frame(name, float(r.get("game_t", 0.0)), view, fps)
        if a is None or b is None:
            continue
        a = Image.fromarray(np.ascontiguousarray(a))
        row = Image.new("RGB", (a.width + b.width + 12, max(a.height, b.height) + 26), "white")
        row.paste(a, (0, 26))
        row.paste(b, (a.width + 12, 26))
        ImageDraw.Draw(row).text((6, 6), f"{r['phase']}: footage {r['t']:.2f} s  |  ours {r.get('game_t', 0):.2f} s  -  {r.get('note', '')}",
                                 fill=(20, 20, 20))
        rows.append(row)
    if not rows:
        raise SystemExit("no frames: render the look first (kit anim look <Name> --rig R6) and check the footage path")
    W = max(r.width for r in rows)
    out = Image.new("RGB", (W, sum(r.height for r in rows)), "white")
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height
    path = os.path.join(BUILD, f"{name}.compare.png")
    out.save(path)
    return path, len(rows)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    dossier = argv[argv.index("--dossier") + 1] if "--dossier" in argv else None
    view = argv[argv.index("--view") + 1] if "--view" in argv else "three-quarter"
    path, n = sheet(argv[0], dossier, view)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"compare {argv[0]}: {n} phase(s) footage | ours -> {path}",
                      "next_action": f"LOOK at {path}: does each phase read like the footage?"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
