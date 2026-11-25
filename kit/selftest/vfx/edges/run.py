#!/usr/bin/env python3
"""The self-test of EDGE DETECTION on a texture (kit/vfx/fxfinish.py `post.edges`; the VFX methods audit, stage 9).

    python kit/selftest/vfx/edges/run.py good   a made disc of two tones (bright left half, dark right half), four
                                                frames growing, packed by the real packer with "edges": the sheet
                                                has a line ROUND the disc AND down the border between the two tones,
                                                none in the middle of either tone and none outside; with "keep": false
                                                the sheet is the lines alone; the packer's own checks pass
    python kit/selftest/vfx/edges/run.py soft   a made soft glow (no step anywhere) that asks for edges: the packer
                                                must refuse it, saying it "found no edge" (exit 1), and write no sheet

What each part does when it is wrong is proven in kit/test/python/test_vfx_edges.py. Everything is written to a
folder of this run's own under build/selftest/, removed at the end. Nothing here shows a sheet in Roblox.
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
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import fxfinish  # noqa: E402

N = 128
PASS = {"alpha": "coverage", "tonemap": False, "border": 0}
RADII = [22, 28, 34, 40]


def disc(radius):
    yy, xx = np.mgrid[0:N, 0:N]
    a = (np.hypot(xx - N / 2 + 0.5, yy - N / 2 + 0.5) < radius).astype(np.float32)
    tone = np.where(xx < N / 2, 0.9, 0.3).astype(np.float32)
    return np.dstack([tone * a] * 3 + [a])  # premultiplied, as the frames on disk are


def glow(radius):
    yy, xx = np.mgrid[0:N, 0:N]
    a = np.exp(-(np.hypot(xx - N / 2 + 0.5, yy - N / 2 + 0.5) / radius) ** 2).astype(np.float32)
    return np.dstack([a * a] * 3 + [a])


def pack(root, name, frames, post):
    """the real packer on made frames -> (exit code, its JSON line, the sheet or None)"""
    specs, fdir, out = os.path.join(root, "specs"), os.path.join(root, "frames", name), os.path.join(root, "out")
    for d in (specs, fdir, out):
        os.makedirs(d, exist_ok=True)
    for i, f in enumerate(frames):
        np.save(os.path.join(fdir, f"{i:03d}.npy"), f.astype(np.float16))
    with open(os.path.join(specs, f"{name}.json"), "w", encoding="utf-8") as fh:
        json.dump({"engine": "fx", "recipe": "made", "frames": len(frames), "grid": 2, "post": post}, fh)
    argv, buf = sys.argv, io.StringIO()
    sys.argv = ["fxfinish.py", "--specs", specs, "--frames", os.path.join(root, "frames"), "--out", out, "--registry", os.path.join(root, "none.json"), "--no-review", name]
    try:
        with contextlib.redirect_stdout(buf):
            code = fxfinish.main()
    finally:
        sys.argv = argv
    said = json.loads(buf.getvalue().strip().splitlines()[-1])
    png = os.path.join(out, f"{name}.png")
    return code, said, (np.asarray(Image.open(png).convert("RGBA")).astype(np.float64) / 255 if os.path.isfile(png) else None)


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def main(argv):
    case = argv[0] if argv else "good"
    root = os.path.join("build", "selftest", f"vfx_edges_{case}_{os.getpid()}")
    try:
        if case == "soft":
            code, said, sheet = pack(root, "made_glow", [glow(r) for r in RADII], dict(PASS, edges={"threshold": 0.08}))
            if code == 0 or sheet is not None:
                return say("pass", "edges soft: a soft glow that asks for edges was packed (a step that drew nothing went through)", "kit/vfx/fxfinish.py build")
            return say("fail", "edges soft: " + str(said.get("summary", ""))[:300], str(said.get("next_action", ""))[:200])
        problems = []
        ink = [0.0, 0.0, 0.0]
        code, said, sheet = pack(root, "made_disc", [disc(r) for r in RADII], dict(PASS, edges={"threshold": 0.12, "color": ink}))
        if code != 0 or sheet is None:
            return say("fail", "edges good: the packer refused the made disc: " + str(said.get("summary", ""))[:240], "kit/vfx/fxfinish.py")
        cell = sheet[N:, N:]  # the last frame (radius 40): the bottom right cell of the 2 x 2 sheet
        dark = lambda y, x: float(cell[y, x, :3].max()) < 0.15 and cell[y, x, 3] > 0.9  # noqa: E731  (an ink line)
        if not (dark(64, 24) and dark(64, 104) and dark(24, 64)):
            problems.append("no line round the disc")
        if not (dark(48, 64) or dark(48, 63)) or not (dark(80, 64) or dark(80, 63)):
            problems.append("no line down the border between the two tones (the silhouette alone is an outline, not edge detection)")
        if dark(64, 44) or dark(64, 84) or abs(cell[64, 44, 0] - 0.9) > 0.03 or abs(cell[64, 84, 0] - 0.3) > 0.03:
            problems.append("a line (or a changed tone) in the middle of a flat tone")
        if cell[6, 6, 3] > 0.01 or cell[120, 8, 3] > 0.01:
            problems.append("something drawn outside the disc")
        code, said, art = pack(root, "made_lines", [disc(r) for r in RADII], dict(PASS, edges={"threshold": 0.12, "color": [1.0, 1.0, 1.0], "keep": False}))
        if code != 0 or art is None:
            problems.append("line art (keep false) was refused: " + str(said.get("summary", ""))[:160])
        else:
            c = art[N:, N:]
            if not (c[64, 24, 3] > 0.9 and (c[48, 64, 3] > 0.9 or c[48, 63, 3] > 0.9) and c[64, 44, 3] < 0.01 and c[64, 84, 3] < 0.01):
                problems.append("line art is not the lines alone (the fill is still there, or a line is missing)")
            share = float((c[..., 3] > 0.5).mean())
            if not 0.01 < share < 0.2:
                problems.append(f"line art covers {share:.3f} of the cell (lines are a few percent of a picture)")
        if problems:
            return say("fail", "edges good: " + "; ".join(problems), "kit/vfx/fxfinish.py edge_lines / finish_frame")
        return say("pass", "edges good: a made two-tone disc packed with edges has a line round it AND down the border of its tones, none inside a flat tone, "
                   "none outside; with keep false the sheet is the lines alone", "none")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
