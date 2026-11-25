"""run.py - the tracker's selftest cases (kit selftest): a MADE shot whose camera pans and zooms by a known amount
(madepan.py: the made flame standing in a night world of small lights), read by the real commands.

    python kit/selftest/vfx/track/run.py good    `track` gives every frame's place in the first frame's picture to
                                                 under 0.3 px and says the camera pans right and up and zooms in; the
                                                 same world filmed by a standing camera is called standing; the flat
                                                 night of the trace's own fixture "could not be followed" (nothing
                                                 invented); and `trace --track` reads the flame as six drawings on
                                                 twos, each the size a standing camera gives
    python kit/selftest/vfx/track/run.py moving  the same moving shot traced WITHOUT --track: every frame would read
                                                 as a new drawing - this case fails, naming "the camera pans", and
                                                 writes no trace

What each part does when it is wrong is proven part by part in kit/test/python/test_vfx_track.py.
Prints one JSON line {schema, status, summary, next_action}; everything is written to a folder of this run's own
under build/selftest/, removed at the end.
"""

import contextlib
import io
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "trace"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import made  # noqa: E402
import madepan  # noqa: E402
import shapetrace  # noqa: E402
import track  # noqa: E402

CORNERS = np.array([[0, 0, 1], [640, 0, 1], [0, 360, 1], [640, 360, 1], [320, 180, 1]], dtype=np.float64).T
HUE = f"{made.HUE[0]},{made.HUE[1]}"


def call(tool, argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = tool.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def save(frames, folder):
    os.makedirs(folder, exist_ok=True)
    for i, f in enumerate(frames):
        Image.fromarray(f).save(os.path.join(folder, f"{i:03d}.png"))
    return folder


def main(argv):
    case = argv[0] if argv else "good"
    root = os.path.join("build", "selftest", f"vfx_track_{case}_{os.getpid()}")
    problems = []
    try:
        frames, truth = madepan.scene()
        pan = save(frames, os.path.join(root, "pan"))
        if case == "moving":
            out_dir = os.path.join(root, "trace")
            code, verdict = call(shapetrace, ["--frames", pan, "--fps", "24", "--hue", HUE, "--out", out_dir])
            wrote = os.path.isfile(os.path.join(out_dir, "trace.json"))
            if code == 0 or wrote:
                print(json.dumps({"schema": 1, "status": "pass", "summary": "track moving: a shot whose camera moves was traced as it is" + (" and its trace was written" if wrote else ""),
                                  "next_action": "kit/vfx/shapetrace.py: the camera check before the trace"}))
                return 0
            print(json.dumps({"schema": 1, "status": "fail", "summary": verdict["summary"], "next_action": verdict["next_action"]}))
            return 1
        code, v = call(track, ["--frames", pan, "--fps", "24", "--hue", HUE, "--out", os.path.join(root, "t")])
        if code != 0 or not v.get("moves"):
            problems.append(f"the moving shot was not followed: {v['summary']}")
        else:
            tr = json.load(open(os.path.join(root, "t", "track.json"), encoding="utf-8"))
            worst = max(float(np.linalg.norm((np.asarray(a) @ CORNERS - b @ CORNERS)[:2], axis=0).max()) for a, b in zip(tr["to_first"], truth))
            if worst > 0.3:
                problems.append(f"a frame's corner lands {worst:.2f} px from where it truly is in the first frame")
            for word in ("right and up", "zooms in"):
                if word not in v["summary"]:
                    problems.append(f'the camera\'s move is not said as it is ("{word}"): {v["summary"]}')
            if not os.path.isfile(os.path.join(root, "t", "track_track.png")):
                problems.append("no LOOK picture was written")
        still = save(madepan.scene(pan=(0, 0), zoom=0.0)[0], os.path.join(root, "still"))
        code, v = call(track, ["--frames", still, "--fps", "24", "--hue", HUE, "--out", os.path.join(root, "s")])
        if code != 0 or v.get("moves") or "stands still" not in v["summary"]:
            problems.append(f"a standing camera was not called standing: {v['summary']}")
        flat = save(made.scene(), os.path.join(root, "flat"))
        code, v = call(track, ["--frames", flat, "--fps", "24", "--hue", HUE, "--out", os.path.join(root, "f")])
        if code == 0 or v.get("known") or "could not be followed" not in v["summary"]:
            problems.append(f"a flat night with nothing to hold on to was 'followed': {v['summary']}")
        code, v = call(shapetrace, ["--frames", pan, "--fps", "24", "--hue", HUE, "--out", os.path.join(root, "tt"), "--track"])
        code0, v0 = call(shapetrace, ["--frames", still, "--fps", "24", "--hue", HUE, "--out", os.path.join(root, "st")])
        if code != 0 or (v.get("drawings"), v.get("on")) != (6, 2):
            problems.append(f"with --track the flame is not six drawings on twos: {v['summary']}")
        elif code0 != 0 or v0.get("drawings") != 6:
            problems.append(f"the standing shot's own trace failed: {v0['summary']}")
        else:
            a = json.load(open(os.path.join(root, "tt", "trace.json"), encoding="utf-8"))
            b = json.load(open(os.path.join(root, "st", "trace.json"), encoding="utf-8"))
            x0, y0, x1, y1 = a["tracked"]["window"]
            for k, (da, db) in enumerate(zip(a["drawings"], b["drawings"])):
                ratio = (da["cover"] * (x1 - x0) * (y1 - y0)) / (db["cover"] * 640 * 360)
                if abs(ratio - 1) > 0.04:
                    problems.append(f"drawing {k} is {ratio:.2f} times the size a standing camera gives")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    if problems:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"track {case}: " + "; ".join(problems), "next_action": "kit/vfx/track.py"}))
        return 1
    print(json.dumps({"schema": 1, "status": "pass", "summary": "track good: a pan and a zoom followed to under 0.3 px and said as they are; a standing camera standing; a flat night not guessed; with --track the flame is six drawings on twos, each the size a standing camera gives",
                      "next_action": "none"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
