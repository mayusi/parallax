"""run.py — the trace's selftest cases (kit selftest), on the made scene of made.py, through the real command.

    python kit/selftest/vfx/trace/run.py good    the made flame's six drawings come back as curves: on twos, two flat
                                                 tones with the scene's colours, the ONE cut-out and the ONE sharp tip in
                                                 every drawing, each drawn again within a few px of the outline the frames
                                                 were made from; the pictures a reader gets at full size; and the stored
                                                 trace holds numbers only
    python kit/selftest/vfx/trace/run.py flood   the same flame in front of a wall in the fire's hue band: the cut-out is
                                                 the wall. NOT a drawing - this case fails, naming "not a drawing"

Prints one JSON line {schema, status, summary, next_action}; the frames are written to a folder of this run's own
under build/selftest/, removed at the end.
"""

import contextlib
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import made  # noqa: E402
import shapetrace  # noqa: E402


def call(argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = shapetrace.main(argv)
    return code, said.getvalue().strip().splitlines()[-1]


def main(argv):
    import numpy as np
    from PIL import Image
    case = argv[0] if argv else "good"
    root = os.path.abspath(os.path.join("build", "selftest", f"vfx_trace_{os.getpid()}", case))
    shutil.rmtree(root, ignore_errors=True)
    frames_dir, out_dir = os.path.join(root, "frames"), os.path.join(root, "out")
    os.makedirs(frames_dir)
    try:
        for i, f in enumerate(made.flood() if case == "flood" else made.scene()):
            Image.fromarray(f).save(os.path.join(frames_dir, f"f_{i:03d}.png"))
        code, line = call(["--frames", frames_dir, "--fps", str(made.FPS), "--out", out_dir,
                           "--hue", f"{made.HUE[0]},{made.HUE[1]}"])
        if case != "good":
            print(line)
            return code
        got = json.loads(line)
        wrong = []
        if got.get("status") != "pass":
            wrong.append(f"the made flame was not traced ({got.get('summary')})")
        else:
            data = json.load(open(os.path.join(out_dir, "trace.json"), encoding="utf-8"))
            ds = data["drawings"]
            if len(ds) != made.DRAWINGS or any(d["hold"] != made.HOLD for d in ds) or data["on"] != 2:
                wrong.append(f"six drawings on twos came back as {[d['hold'] for d in ds]} (on {data['on']})")
            tones = data["tones"]
            near = lambda a, b: max(abs(x - y) for x, y in zip(a, b)) <= 10  # noqa: E731
            if len(tones) != 2 or not near(tones[0], made.BODY) or not near(tones[1], made.CORE):
                wrong.append(f"two flat tones {made.BODY} and {made.CORE} came back as {tones}")
            trace = shapetrace.from_json(data)
            for k, d in enumerate(trace["drawings"][:made.DRAWINGS]):
                body, core = made.truth(k)
                again = shapetrace.fill(d["layers"][0]["shapes"], (made.W, made.H)) > 0.5
                iou = (again & body).sum() / float((again | body).sum())
                if iou < 0.97:
                    wrong.append(f"drawing {k + 1}: its curves cover {iou * 100:.1f} % of the TRUE flame (97 or more)")
                if len(d["layers"]) != 2:
                    wrong.append(f"drawing {k + 1}: {len(d['layers'])} tone layer(s), the flame has a body and a core")
                else:
                    inner = shapetrace.fill(d["layers"][1]["shapes"], (made.W, made.H)) > 0.5
                    if (inner & core).sum() / float((inner | core).sum()) < 0.90:
                        wrong.append(f"drawing {k + 1}: the core's curves miss the true core")
                if d["holes"] != 1 or d["pieces"] != 1:
                    wrong.append(f"drawing {k + 1}: {d['pieces']} piece(s) and {d['holes']} cut-out(s), the flame is one piece with one")
                sharp = np.concatenate([p[f] for s in d["layers"][0]["shapes"] for p, f in [s["outer"]] + s["holes"]])
                tip = np.array(made.outline(k)[3])
                if len(sharp) != 1 or np.hypot(*(sharp[0] - tip)) > 2.5:
                    wrong.append(f"drawing {k + 1}: {len(sharp)} sharp point(s); the flame has ONE, its tip at {tip.round(1).tolist()}")
                edge = sum(len(p) for s in d["layers"][0]["shapes"] for p, _ in [s["outer"]] + s["holes"])
                if edge > 160:
                    wrong.append(f"drawing {k + 1}: {edge} points on its outline: a pixel chain, not a curve")
            files = got.get("files") or []
            if len(files) != made.DRAWINGS or Image.open(files[0]).width < 3 * 640:
                wrong.append("the LOOK pictures are not three 640 px panes a drawing")
            text = open(os.path.join(out_dir, "trace.json"), encoding="utf-8").read()
            if len(text) > 40000 or "png" in text.lower():
                wrong.append("the stored trace is not small numbers only")
        if wrong:
            print(json.dumps({"schema": 1, "status": "fail", "summary": "vfx trace (made scene): " + "; ".join(wrong[:4]),
                              "next_action": "kit/vfx/shapetrace.py: find out why before touching what this case expects"}))
            return 1
        print(json.dumps({"schema": 1, "status": "pass", "summary": "vfx trace (made scene): six drawings on twos, two flat "
                          "tones, the cut-out and the one sharp tip of every drawing, each within 3 % of the true outline",
                          "next_action": "none"}))
        return 0
    finally:
        shutil.rmtree(os.path.dirname(root), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
