"""run.py — the B4 "drawn" plate selftest cases (kit selftest; LIMITATIONS_FIXES_V4 13.3.4: "pre-bake ScreenGui halftone /
kanji / drawn impact sheets").

    python kit/selftest/vfx/drawn/run.py good   a drawn plate baked by the REAL plate command: every check passes
                                                (boil: the same burst drawn again each cell; taper: brush strokes)
    python kit/selftest/vfx/drawn/run.py bad    the same plate's first cell HELD for every cell, and one-width ruled
                                                spokes: the real checks refuse them, naming "boil" and "taper"

Prints one JSON line {schema, status, summary, next_action}; writes under build/selftest/, removed at the end.
"""

import contextlib
import io
import json
import os
import shutil
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import plates  # noqa: E402


def say(status, summary, nxt="none"):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": nxt}))
    return 0 if status == "pass" else 1


def main(argv):
    case = argv[0] if argv else "good"
    root = os.path.abspath(os.path.join("build", "selftest", f"vfx_drawn_{os.getpid()}"))
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    try:
        if case == "good":
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                code = plates.main(["st_drawn", "--kind", "drawn", "--frames", "16", "--out", root, "--specs-dir", root,
                                    "--look-dir", root])
            line = json.loads(said.getvalue().strip().splitlines()[-1])
            names = {c["name"] for c in line.get("checks", [])}
            if code != 0 or not {"boil", "taper", "clear", "cover"} <= names:
                return say("fail", "vfx drawn: the drawn plate was refused or not checked - " + line["summary"], "kit/vfx/plates.py")
            return say("pass", "vfx drawn: " + line["summary"])
        spec = plates.checked({"kind": "drawn", "frames": 4, "seed": 5})
        cells, _, _ = plates.bake(spec)
        held = [c["name"] for c in plates.checks(spec, [cells[0]] * 4) if not c["ok"]]
        n = spec["cell"]
        ruled = []
        for k in range(4):
            img = np.zeros((n, n), np.uint8)
            for i in range(24):
                a = i / 24 * 2 * np.pi + k * 0.01
                cv2.line(img, (int(n / 2 + 0.2 * n * np.cos(a)), int(n / 2 + 0.2 * n * np.sin(a))),
                         (int(n / 2 + 0.48 * n * np.cos(a)), int(n / 2 + 0.48 * n * np.sin(a))), 255, 6)
            ruled.append(img.astype(np.float32) / 255.0)
        flat = [c["name"] for c in plates.checks(spec, ruled) if not c["ok"]]
        if "boil" not in held or "taper" not in flat:
            return say("pass", "vfx drawn bad: a held plate / ruled spokes PASSED (nothing caught)")
        return say("fail", f"vfx drawn bad: refused - held: {', '.join(held)} (boil); ruled: {', '.join(flat)} (taper)",
                   "none: this case must fail")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
