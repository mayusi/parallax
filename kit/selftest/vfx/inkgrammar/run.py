"""run.py — the sakuga grammars' selftest cases (kit selftest; LIMITATIONS_FIXES_V4 §3.4 step 2).

    python kit/selftest/vfx/inkgrammar/run.py good   the made flame (kit/selftest/vfx/trace/made.py) traced by the REAL
                                                     trace command, its numbers read by the grammar route, and every one
                                                     of the five grammars drawn from them by the REAL ink command: each
                                                     passes its checks; the flame (the contract's 64 drawings) is a
                                                     1024 x 1024 sheet whose every cell is drawn and whose 2 px gutters
                                                     are empty, with a glow mask that is white on the white core and
                                                     dark on the dark rim; the asked solidity is measured back
    python kit/selftest/vfx/inkgrammar/run.py bad    the same flame sheet, two of its cells spoiled the way a careless
                                                     sheet is (a drawing reaching into the gutter, the see-through
                                                     pixels left black): the packing checks must name "gutter"

Prints one JSON line {schema, status, summary, next_action}; everything is written under build/selftest/, removed at
the end.
"""

import contextlib
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "trace"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import made  # noqa: E402
import ink  # noqa: E402
import inkgrammar  # noqa: E402
import shapetrace  # noqa: E402


def call(tool, argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = tool.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


def say(status, summary, nxt="none"):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": nxt}))
    return 0 if status == "pass" else 1


def main(argv):
    import numpy as np
    from PIL import Image
    case = argv[0] if argv else "good"
    root = os.path.abspath(os.path.join("build", "selftest", f"vfx_inkgrammar_{os.getpid()}", case))
    shutil.rmtree(root, ignore_errors=True)
    scene, look = os.path.join(root, "scene"), os.path.join(root, "look")
    os.makedirs(scene)
    try:
        for i, f in enumerate(made.scene()):
            Image.fromarray(f).save(os.path.join(scene, f"f_{i:03d}.png"))
        code, line = call(shapetrace, ["--frames", scene, "--fps", str(made.FPS), "--out", os.path.join(root, "trace"),
                                       "--hue", f"{made.HUE[0]},{made.HUE[1]}"])
        if code != 0:
            return say("error", "vfx inkgrammar: the made scene was not traced: " + line["summary"], "kit/selftest/vfx/trace first")
        trace_path = [os.path.join(root, "trace", f) for f in os.listdir(os.path.join(root, "trace")) if f.endswith(".json")][0]
        with open(trace_path, encoding="utf-8") as fh:
            metrics = inkgrammar.metrics_from_trace(json.load(fh))
        if case == "bad":
            res = ink.grammar_sheet("flame_tongue", metrics, frames=16, grid=4)
            cells = [c.copy() for c in res["cells"]]
            cells[2][0:1, 50:70, 3] = 1.0
            cells[7][..., :3] = np.where(cells[7][..., 3:4] == 0, 0.0, cells[7][..., :3])
            checks, _, _ = ink.sheet_checks(cells, res["tones"], 4, 4, 128)
            bad = [c for c in checks if not c["ok"]]
            if not bad:
                return say("pass", "vfx inkgrammar bad: a spoiled sheet passed its packing checks (nothing caught)")
            return say("fail", "vfx inkgrammar bad: the packing checks refuse the spoiled sheet - "
                       + "; ".join(f"{c['name']} {c['value']} ({c['fix']})" for c in bad), "none: this case must fail")
        done = []
        for g in inkgrammar.GRAMMARS:
            frames = "64" if g == "flame_tongue" else "32"
            code, line = call(ink, [f"st_{g}", "--grammar", g, "--from", trace_path, "--frames", frames, "--look-dir", look])
            if code != 0:
                return say("fail", f"vfx inkgrammar: {g} from the made flame's numbers failed - {line['summary']}",
                           "kit/vfx/inkgrammar.py: the grammar named")
            done.append(g)
        im = np.asarray(Image.open(os.path.join(look, "st_flame_tongue.png")))
        if im.shape != (1024, 1024, 4):
            return say("fail", f"vfx inkgrammar: the flame sheet is {im.shape}, not 1024 x 1024 RGBA")
        a = im[..., 3]
        for r in range(8):
            for q in range(8):
                c = a[r * 128:(r + 1) * 128, q * 128:(q + 1) * 128]
                if int((c > 127).sum()) < 50:
                    return say("fail", f"vfx inkgrammar: the flame's cell {r * 8 + q + 1} is empty")
                if int(max(c[:2].max(), c[-2:].max(), c[:, :2].max(), c[:, -2:].max())) != 0:
                    return say("fail", f"vfx inkgrammar: the flame's cell {r * 8 + q + 1} reaches into its gutter")
        glow = np.asarray(Image.open(os.path.join(look, "st_flame_tongue_glow.png")).convert("L")).astype(np.float32)
        lum = (im[..., :3].astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], np.float32)) * a / 255.0
        hot, rim = glow[lum > 200].mean(), glow[(a > 0) & (lum < 110)].mean()
        if not (hot > 200 and rim < 30):
            return say("fail", f"vfx inkgrammar: the glow mask is {hot:.0f} on the core and {rim:.0f} on the rim (wants > 200, < 30)")
        with open(os.path.join(look, "st_flame_tongue.grammar.json"), encoding="utf-8") as fh:
            rep = json.load(fh)
        got = rep["measured"]["area_frac"]
        if abs(got - metrics["area_frac"]) > inkgrammar.TOL_AREA and not any("area_frac" in s for s in rep["said"]):
            return say("fail", f"vfx inkgrammar: the flame measures {got} solid, the trace asked {metrics['area_frac']}")
        return say("pass", f"vfx inkgrammar: the made flame's numbers (area {metrics['area_frac']}, speed {metrics['centroid_vel']}, "
                   f"cutout {metrics['cutout_ratio']}) drew all five grammars ({', '.join(done)}); the flame is 1024 x 1024, "
                   f"64 cells drawn inside 2 px gutters, glow {hot:.0f} on the core / {rim:.0f} on the rim, solidity {got} measured back")
    finally:
        shutil.rmtree(os.path.dirname(root), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
