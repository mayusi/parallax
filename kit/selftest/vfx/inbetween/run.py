#!/usr/bin/env python3
"""The self-test of MOTION VECTORS on a texture (kit/vfx/fxfinish.py `post.inbetween`; the VFX methods audit, stage 20).

    python kit/selftest/vfx/inbetween/run.py good   a made soft-edged disc that crosses its cell in four frames (10 px
                                                    a frame), packed by the real packer with "inbetween": true on a
                                                    4 x 2 grid: all EIGHT cells hold the disc (no cell is empty); the
                                                    first cell is the first frame and the last the last, untouched;
                                                    each cell's disc has its middle where that cell's moment puts it
                                                    (to 1.5 px), and a cell between two frames is at least four times
                                                    nearer the true disc of that moment than a cross-fade of the two;
                                                    with "loop" a disc going round in eight frames fills sixteen cells
                                                    and the last cell is half way from the last frame to the first; the
                                                    packer's own checks pass (frames_count is the grid's)
    python kit/selftest/vfx/inbetween/run.py fade   a made disc that stands still and only fades: the packer must
                                                    refuse it, saying "over the whole sheet" the vectors do not account
                                                    for the change (exit 1), and write no sheet
    python kit/selftest/vfx/inbetween/run.py far    a large disc that drifts and a small spark beside it that jumps 44
                                                    px a frame: the packer must refuse it, saying "a part of the picture
                                                    is not followed" (the spark would be drawn twice)

Everything is written to a folder of this run's own under build/selftest/, removed at the end. Nothing here shows a
sheet in Roblox or in the browser player.
"""
import contextlib
import io
import json
import math
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


def disc(cx, cy, radius=20.0, light=1.0):
    yy, xx = np.mgrid[0:N, 0:N]
    a = np.clip((radius - np.hypot(xx - cx, yy - cy)) / 3 + 0.5, 0, 1).astype(np.float32) * light
    return np.dstack([0.9 * a, 0.6 * a, 0.3 * a, a])  # premultiplied, as the frames on disk are


def pack(root, name, frames, post, grid):
    """the real packer on made frames -> (exit code, its JSON line, the sheet or None)"""
    specs, fdir, out = os.path.join(root, "specs"), os.path.join(root, "frames", name), os.path.join(root, "out")
    for d in (specs, fdir, out):
        os.makedirs(d, exist_ok=True)
    for i, f in enumerate(frames):
        np.save(os.path.join(fdir, f"{i:03d}.npy"), f.astype(np.float16))
    with open(os.path.join(specs, f"{name}.json"), "w", encoding="utf-8") as fh:
        json.dump({"engine": "fx", "recipe": "made", "frames": len(frames), "grid": grid, "post": post}, fh)
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


def cell(sheet, k, cols):
    r, c = divmod(k, cols)
    return sheet[r * N:(r + 1) * N, c * N:(c + 1) * N]


def middle(c):
    a = c[..., 3]
    yy, xx = np.mgrid[0:N, 0:N]
    return float((xx * a).sum() / a.sum()), float((yy * a).sum() / a.sum())


def straight(p):
    a = p[..., 3:]
    return np.dstack([np.where(a > 1e-4, p[..., :3] / np.maximum(a, 1e-4), 0), a])


def off(a, b):
    """how far two cells are apart, as light (premultiplied)"""
    return float(np.abs(a[..., :3] * a[..., 3:] - b[..., :3] * b[..., 3:]).mean() + np.abs(a[..., 3] - b[..., 3]).mean())


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def both(frames):
    out = frames[0].copy()
    for f in frames[1:]:
        out = out + f * (1 - out[..., 3:])
    return out


def main(argv):
    case = argv[0] if argv else "good"
    root = os.path.join("build", "selftest", f"vfx_inbetween_{case}_{os.getpid()}")
    try:
        if case == "fade":
            code, said, sheet = pack(root, "made_fade", [disc(64, 64, light=v) for v in (1.0, 0.75, 0.5, 0.25)], dict(PASS, inbetween=True), [4, 2])
            if code == 0 or sheet is not None:
                return say("pass", "inbetween fade: a picture that only fades was given cells between (they are cross-fades)", "kit/vfx/fxfinish.py inbetween")
            return say("fail", "inbetween fade: " + str(said.get("summary", ""))[:300], str(said.get("next_action", ""))[:200])
        if case == "far":
            frames = [both([disc(40 + 4 * k, 44, radius=22), disc(30 if k % 2 == 0 else 74, 108, radius=5)]) for k in range(4)]
            code, said, sheet = pack(root, "made_far", frames, dict(PASS, inbetween=True), [4, 2])
            if code == 0 or sheet is not None:
                return say("pass", "inbetween far: a spark that jumps beside a drifting disc was given cells between (it is drawn twice)", "kit/vfx/fxfinish.py inbetween")
            return say("fail", "inbetween far: " + str(said.get("summary", ""))[:300], str(said.get("next_action", ""))[:200])
        problems = []
        xs = [44, 54, 64, 74]
        frames = [disc(x, 64) for x in xs]
        code, said, sheet = pack(root, "made_cross", frames, dict(PASS, inbetween=True), [4, 2])
        if code != 0 or sheet is None:
            return say("fail", "inbetween good: the packer refused the made disc: " + str(said.get("summary", ""))[:240], "kit/vfx/fxfinish.py")
        if sheet.shape[:2] != (2 * N, 4 * N):
            problems.append(f"the sheet is {sheet.shape[1]} x {sheet.shape[0]}, not 4 x 2 cells")
        for k in range(8):
            got = cell(sheet, k, 4)
            if float(got[..., 3].max()) < 0.9:
                problems.append(f"cell {k + 1} is empty or faint ({got[..., 3].max():.2f}): Roblox plays every cell")
                continue
            want = 44 + 30 * k / 7
            mx, my = middle(got)
            if abs(mx - want) > 1.5 or abs(my - 64) > 1.5:
                problems.append(f"cell {k + 1} has its disc at ({mx:.1f}, {my:.1f}), its moment is ({want:.1f}, 64)")
        for k, f in ((0, 0), (7, 3)):
            if off(cell(sheet, k, 4), straight(frames[f])) > 0.004:
                problems.append(f"cell {k + 1} is not rendered frame {f + 1} as it was")
        for k in (1, 3, 4, 6):  # cells between two frames
            at = k * 3 / 7
            i, t = int(at), at - int(at)
            truth = straight(disc(44 + 10 * at, 64))
            fade = (1 - t) * frames[i] + t * frames[i + 1]  # a cross-fade of the two frames (premultiplied)
            d_mv = off(cell(sheet, k, 4), truth)
            d_fade = float(np.abs(fade[..., :3] - truth[..., :3] * truth[..., 3:]).mean() + np.abs(fade[..., 3] - truth[..., 3]).mean())
            if not d_mv * 4 <= d_fade:
                problems.append(f"cell {k + 1} is {d_mv:.4f} from the true disc of its moment, a cross-fade {d_fade:.4f} (it must be four times nearer)")
        result = (said.get("textures") or [{}])[0]
        failed = [c["name"] for c in result.get("checks", []) if not c.get("ok")]
        if failed or result.get("frames") != 8:
            problems.append(f"the packer's own checks fail ({', '.join(failed)}) or it counts {result.get('frames')} cells, not 8")
        ring = [disc(64 + 30 * math.cos(k * math.pi / 4), 64 + 30 * math.sin(k * math.pi / 4), radius=16) for k in range(8)]
        code, said, sheet = pack(root, "made_round", ring, dict(PASS, inbetween={"loop": True}), 4)
        if code != 0 or sheet is None:
            problems.append("a looping sheet was refused: " + str(said.get("summary", ""))[:160])
        else:
            if min(float(cell(sheet, k, 4)[..., 3].max()) for k in range(16)) < 0.9:
                problems.append("a cell of the looping sheet is empty or faint")
            mx, my = middle(cell(sheet, 15, 4))  # half way from the last frame to the first
            a = math.atan2(my - 64, mx - 64)
            if abs(a - (-math.pi / 8)) > 0.12 or abs(math.hypot(mx - 64, my - 64) - 30 * math.cos(math.pi / 8)) > 2.5:
                problems.append(f"the last cell of the loop is at ({mx:.1f}, {my:.1f}), not half way round from the last frame to the first")
        code, said, sheet = pack(root, "made_same", frames, dict(PASS, inbetween=True), 2)
        if code == 0 or "FEWER frames" not in str(said.get("summary", "")):
            problems.append("four frames on a grid of four cells were taken (there is no cell to draw)")
        if problems:
            return say("fail", "inbetween good: " + "; ".join(problems), "kit/vfx/fxfinish.py inbetween / moments / motion / moved")
        return say("pass", "inbetween good: four frames of a made disc fill an eight-cell grid - no cell empty, each cell ONE disc where its moment puts it (far "
                   "nearer the true disc than a cross-fade), the first and last cells the frames themselves; a looping sheet's last cell is half way back to its first", "none")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
