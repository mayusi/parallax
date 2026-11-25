"""run.py — the ink's selftest cases (kit selftest): the made flame (kit/selftest/vfx/trace/made.py) traced by the
real command, then inked by the real command into a made project folder.

    python kit/selftest/vfx/ink/run.py good    four drawings, one in-between each, looping -> 8 cells that FILL a
                                               4 x 2 sheet. Every DRAWING's cell shows the TRUE flame through the ink's
                                               own window; every in-between (the one back to the first too) has its
                                               area and its tip between its two drawings' and keeps the tip a point;
                                               the kit's sheet packer packs and passes it, and in the packed sheet the
                                               body is the body's colour, the core the core's, and a half-covered edge
                                               pixel is STILL the body's colour (no dark fringe); the spec says how to
                                               play it; with its frames gone the build step inks the same cells again;
                                               and from a trace that is not a kept one it makes a look and NO texture
    python kit/selftest/vfx/ink/run.py split   two drawings that are not the same pieces and barely overlap, with an
                                               in-between asked for: a blend, NOT a drawing - this case fails, naming
                                               "barely overlap", and leaves no spec and no frames behind

This is the route end to end. What each part does when it is wrong (an in-between that is not point to point, a
window that ignores --register, a check that catches nothing) is proven part by part in
kit/test/python/test_vfx_ink.py: on the made flame every way of in-betweening lands close.
Prints one JSON line {schema, status, summary, next_action}; everything is written to a folder of this run's own
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
sys.path.insert(0, os.path.join(HERE, "..", "trace"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import made  # noqa: E402
import madeink  # noqa: E402
import fxfinish  # noqa: E402
import ink  # noqa: E402
import shapetrace  # noqa: E402

DRAWINGS = 4


def call(tool, argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = tool.main(argv)
    return code, said.getvalue().strip().splitlines()[-1]


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def under(mask, top):
    """how wide a shape is 3 px under its top row: a point is narrow there"""
    return int(mask[top + 3].sum())


def main(argv):
    import cv2
    import numpy as np
    from PIL import Image
    case = argv[0] if argv else "good"
    root = os.path.abspath(os.path.join("build", "selftest", f"vfx_ink_{os.getpid()}", case))
    shutil.rmtree(root, ignore_errors=True)
    frames_dir, kept = os.path.join(root, "scene"), os.path.join(root, "assets", "effects", "refs_measured")
    specs, fxlab, look = (os.path.join(root, "assets", "textures"), os.path.join(root, "build", "fxlab"),
                          os.path.join(root, "look"))
    os.makedirs(frames_dir)
    try:
        for i, f in enumerate(madeink.split() if case == "split" else made.scene()):
            Image.fromarray(f).save(os.path.join(frames_dir, f"f_{i:03d}.png"))
        code, line = call(shapetrace, ["--frames", frames_dir, "--fps", str(made.FPS), "--out", kept,
                                       "--hue", f"{made.HUE[0]},{made.HUE[1]}"])
        if code != 0:
            print(json.dumps({"schema": 1, "status": "error", "summary": "vfx ink: the made scene was not traced: "
                              + json.loads(line)["summary"], "next_action": "kit/selftest/vfx/trace first"}))
            return 2
        trace_json = os.path.join(kept, "trace.json")
        dirs = ["--specs-dir", specs, "--frames-dir", fxlab, "--look-dir", look, "--kept-dir", kept]
        if case != "good":
            code, line = call(ink, ["flame_ink", "--from", trace_json, "--between", "1"] + dirs)
            left = os.path.isfile(os.path.join(specs, "flame_ink.json")) or os.path.isdir(os.path.join(fxlab, "flame_ink"))
            if code != 0 and left:
                print(json.dumps({"schema": 1, "status": "error", "summary": "vfx ink (split): refused, but it left a spec "
                                  "or frames behind", "next_action": "kit/vfx/ink.py run(): a refused sheet writes nothing"}))
                return 2
            print(line)
            return code
        code, line = call(ink, ["flame_ink", "--from", trace_json, "--drawings", f"1-{DRAWINGS}", "--between", "1", "--loop"] + dirs)
        got = json.loads(line)
        wrong = []
        if got.get("status") != "pass" or not got.get("spec"):
            wrong.append(f"the made flame was not inked into a texture ({got.get('summary')})")
        else:
            cells = [np.load(os.path.join(fxlab, "flame_ink", f"{i:03d}.npy")).astype(np.float32) for i in range(got["cells"])]
            if got["cells"] != 2 * DRAWINGS or got["grid"] != [4, 2] or got["cell"] != 256:
                wrong.append(f"four drawings + four in-betweens came out as {got['cells']} cells in {got['grid']} of {got['cell']} px")
            trace = shapetrace.from_json(load(trace_json))
            wins = ink.windows(trace["drawings"][:DRAWINGS], 256)
            alpha = [c[..., 3] > 0.5 for c in cells]
            tops = [int(np.nonzero(a.any(axis=1))[0].min()) for a in alpha]
            for k in range(DRAWINGS):
                true = madeink.truth_cell(k, wins[k][0], wins[k][1], 256)
                iou = (alpha[2 * k] & true).sum() / float((alpha[2 * k] | true).sum())
                if iou < 0.95:
                    wrong.append(f"drawing {k + 1}'s cell covers {iou * 100:.1f} % of the TRUE flame in its window (95 or more)")
            for k in range(DRAWINGS):                         # the in-between after drawing k leads to the next, the last to the first
                i, m, j = 2 * k, 2 * k + 1, (2 * k + 2) % (2 * DRAWINGS)
                want = (alpha[i].sum() + alpha[j].sum()) / 2.0
                if abs(alpha[m].sum() - want) > 0.03 * want:
                    wrong.append(f"in-between {k + 1}: its area is {alpha[m].sum()}, between its drawings is {want:.0f}")
                if not min(tops[i], tops[j]) <= tops[m] <= max(tops[i], tops[j]):
                    wrong.append(f"in-between {k + 1}: its tip is not between its drawings' tips")
                if under(alpha[m], tops[m]) > max(under(alpha[i], tops[i]), under(alpha[j], tops[j])) + 2:
                    wrong.append(f"in-between {k + 1}: its tip is blunt ({under(alpha[m], tops[m])} px wide 3 px under it)")
            spec = load(os.path.join(specs, "flame_ink.json"))
            if (spec.get("recipe"), spec.get("grid"), spec.get("frames")) != ("ink", [4, 2], 8) \
                    or spec.get("play") != {"mode": "Loop", "fps": 24.0, "blend": False}:
                wrong.append(f"the spec does not say what it is or how to play it: {spec.get('recipe')}, {spec.get('grid')}, {spec.get('play')}")
            # the kit's own sheet packer must take it as it takes every sheet - and keep the flame's colours: the
            # body the body's, the core the core's, and an edge pixel half covered STILL the body's (no dark fringe)
            img, grid, clipped, change, n = fxfinish.build("flame_ink", spec, fxlab)
            failed = [c["name"] for c in fxfinish.check(img, grid, clipped, change, n, False, want=spec["frames"]) if not c["ok"]]
            if failed or img.size != (1024, 512):
                wrong.append(f"the sheet packer does not pass it: {failed}, {img.size}")
            first = np.asarray(img).astype(int)[:256, :256]
            deep = np.ones((5, 5), np.uint8)
            body = madeink.truth_cell(0, wins[0][0], wins[0][1], 256)
            core = madeink.truth_core_cell(0, wins[0][0], wins[0][1], 256)
            in_core = cv2.erode(core.astype(np.uint8), deep).astype(bool)
            in_body = cv2.erode((body & ~cv2.dilate(core.astype(np.uint8), deep).astype(bool)).astype(np.uint8), deep).astype(bool)
            for name, where, tone in (("body", in_body, made.BODY), ("core", in_core, made.CORE)):
                off = np.abs(first[where][:, :3] - np.array(tone)).max()
                if not where.any() or off > 5:
                    wrong.append(f"inside the packed flame's {name} a pixel is {off} off the {name}'s colour {tone}")
            edge = (first[..., 3] > 64) & (first[..., 3] < 192) & ~cv2.dilate(core.astype(np.uint8), deep).astype(bool)
            if not edge.any() or np.abs(first[edge][:, :3] - np.array(made.BODY)).max() > 12:
                worst = first[edge][np.abs(first[edge][:, :3] - np.array(made.BODY)).max(axis=1).argmax()].tolist() if edge.any() else None
                wrong.append(f"a half-covered edge pixel of the packed flame is {worst}: darker than the body's {made.BODY} (a fringe)")
            if Image.open(got["look"]).width < 6 * 320:
                wrong.append("the LOOK strip's cells are under 320 px")
            # frames gone (a wiped build folder): the build step inks the same cells again from the spec
            shutil.rmtree(os.path.join(fxlab, "flame_ink"))
            code, line = call(ink, ["--specs", specs, "--out", fxlab, "--kept-dir", kept])
            again = os.path.join(fxlab, "flame_ink", "003.npy")
            if code != 0 or not os.path.isfile(again) or not np.array_equal(np.load(again).astype(np.float32), cells[3]):
                wrong.append(f"the build step did not ink the same cells again ({json.loads(line).get('summary')})")
            # a trace that is not a kept one: a look, never a texture
            loose_trace = os.path.join(root, "build", "trace.json")
            shutil.copyfile(trace_json, loose_trace)
            code, line = call(ink, ["look_only", "--from", loose_trace, "--drawings", "1-4"] + dirs)
            only = json.loads(line)
            if code != 0 or "A LOOK ONLY" not in only["summary"] or os.path.exists(os.path.join(specs, "look_only.json")) \
                    or os.path.exists(os.path.join(fxlab, "look_only")) or not os.path.isfile(only["look"]):
                wrong.append(f"a trace that is not kept did not give a look and no texture ({only['summary'][:160]})")
        if wrong:
            print(json.dumps({"schema": 1, "status": "fail", "summary": "vfx ink (made flame): " + "; ".join(wrong[:4]),
                              "next_action": "kit/vfx/ink.py: find out why before touching what this case expects"}))
            return 1
        print(json.dumps({"schema": 1, "status": "pass", "summary": "vfx ink (made flame): 8 cells fill a 4 x 2 sheet; every "
                          "drawing is the true flame in its window, every in-between lies between its drawings with its tip a "
                          "point; packed, the body, the core and the edge keep their colours; the build step inks it again; a "
                          "trace that is not kept gives a look and no texture", "next_action": "none"}))
        return 0
    finally:
        shutil.rmtree(os.path.dirname(root), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
