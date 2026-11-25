"""run.py - the comp's selftest cases (kit selftest): a surface look baked by the real command into a made project
folder.

    python kit/selftest/vfx/comp/run.py good    a ring whose noise pans and whose lookup is warped, through a colour
                                                ramp: 16 frames in under 5 s; the ring is where its radius says (its
                                                covered pixels sit at 0.34 of the cell from the centre, within the
                                                warp); the loop comes back to its first frame; every colour is on the
                                                ramp; nothing touches the cell's edge; the kit's packer packs and
                                                passes it; untouched, the build step bakes nothing, and with its spec
                                                changed it bakes again
    python kit/selftest/vfx/comp/run.py still   the same ring with nothing that pans: sixteen copies of one picture,
                                                NOT a look that moves - this case fails, naming "two frames show the
                                                same picture", and leaves no frames behind

What each part does when it is wrong is proven part by part in kit/test/python/test_vfx_comp.py.
Prints one JSON line {schema, status, summary, next_action}; everything is written to a folder of this run's own
under build/selftest/, removed at the end.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import comp  # noqa: E402
import fxfinish  # noqa: E402

RAMP = [[0, [60, 8, 4]], [0.5, [255, 110, 20]], [1, [255, 245, 210]]]
RING = {"loop": True, "shape": {"sdf": "ring", "radius": 0.34, "width": 0.09, "soft": 0.02, "falloff": 0.03},
        "noise": {"scale": 5, "octaves": 3, "pan": [1, 0], "seed": 3, "contrast": 1.6, "mix": 0.8},
        "warp": {"scale": 3, "amount": 0.03, "pan": [0, 1], "seed": 11},
        "erode": {"at": 0.2, "soft": 0.05}, "ramp": RAMP}


def call(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = comp.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def on_ramp(rgb):
    """how far each colour is from the ramp's polyline (the worst pixel)"""
    pts = np.array([s[1] for s in RAMP], dtype=np.float64) / 255.0
    best = np.full(rgb.shape[0], np.inf)
    for a, b in zip(pts[:-1], pts[1:]):
        ab = b - a
        t = np.clip(((rgb - a) @ ab) / float(ab @ ab), 0, 1)
        best = np.minimum(best, np.linalg.norm(rgb - (a + t[:, None] * ab), axis=1))
    return float(best.max())


def main(argv):
    case = argv[0] if argv else "good"
    root = os.path.join("build", "selftest", f"vfx_comp_{case}_{os.getpid()}")
    built, specs, frames, look = (os.path.join(root, d) for d in ("textures", "specs", "fxlab", "look"))
    dirs = ["--textures-dir", built, "--specs-dir", specs, "--frames-dir", frames, "--look-dir", look]
    problems = []
    try:
        os.makedirs(specs, exist_ok=True)
        ring = json.loads(json.dumps(RING))
        if case == "still":
            ring["noise"]["pan"], ring["warp"]["pan"] = [0, 0], [0, 0]
        spec = {"engine": "fx", "recipe": "comp", "frames": 16, "grid": 4, "cell": 256, "comp": ring, "post": dict(comp.POST)}
        path = os.path.join(specs, "made_ring.json")
        json.dump(spec, open(path, "w", encoding="utf-8"), indent=1)
        t0 = time.perf_counter()
        code, verdict = call(["made_ring", *dirs])
        took = time.perf_counter() - t0
        if case == "still":
            left = os.path.isdir(os.path.join(frames, "made_ring"))
            if code == 0 or left:
                print(json.dumps({"schema": 1, "status": "pass", "summary": "comp still: sixteen copies of one picture were baked as a look that moves" + (" and frames were left behind" if left else ""),
                                  "next_action": "kit/vfx/comp.py: the `moves` check"}))
                return 0
            print(json.dumps({"schema": 1, "status": "fail", "summary": verdict["summary"], "next_action": verdict["next_action"]}))
            return 1
        if code != 0:
            problems.append(f"the good look was refused: {verdict['summary']}")
        else:
            if took > 5:
                problems.append(f"the look took {took:.1f} s (a look is tried in seconds)")
            files = sorted(f for f in os.listdir(os.path.join(frames, "made_ring")) if f.endswith(".npy"))
            cells = [np.load(os.path.join(frames, "made_ring", f)).astype(np.float64) for f in files]
            if len(cells) != 16:
                problems.append(f"{len(cells)} frames, not 16")
            n = cells[0].shape[0]
            yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
            r = np.sqrt((xx + 0.5 - n / 2) ** 2 + (yy + 0.5 - n / 2) ** 2) / n
            for k in (0, 8):
                a = cells[k][..., 3]
                mean = float((r * a).sum() / max(a.sum(), 1e-9))
                far = float(np.abs(r[a > 0.5] - 0.34).max()) if (a > 0.5).any() else 1.0
                if abs(mean - 0.34) > 0.02 or far > 0.045 + 0.03 + 0.03:  # (half its width, the warp, the soft edge)
                    problems.append(f"frame {k}: the ring is not where its radius says (mean {mean:.3f}, farthest {far:.3f} from 0.34)")
            steps = [float(np.abs(cells[i + 1] - cells[i]).mean()) for i in range(15)]
            seam = float(np.abs(cells[0] - cells[-1]).mean())
            if min(steps) < 1e-4:
                problems.append("two neighbouring frames are the same")
            if seam > 1.5 * max(steps):
                problems.append(f"the loop does not come back: its seam is {seam / max(steps):.2f} times its hardest step")
            a = cells[0][..., 3]
            solid = a > 0.5
            rgb = (cells[0][..., :3] / np.maximum(a[..., None], 1e-6))[solid]  # (frames are premultiplied)
            off = on_ramp(rgb)
            if off > 0.02:
                problems.append(f"a colour is {off:.3f} off the ramp")
            if float(rgb[:, 0].max() - rgb[:, 0].min()) < 0.1 and float(rgb[:, 1].max() - rgb[:, 1].min()) < 0.1:
                problems.append("the ramp is not used: one flat colour")
            edge = max(float(max(c[0, :, 3].max(), c[-1, :, 3].max(), c[:, 0, 3].max(), c[:, -1, 3].max())) for c in cells)
            if edge > 0.02:
                problems.append("a frame touches its cell's edge")
            img, grid, clipped, change, count = fxfinish.build("made_ring", spec, frames)
            failed = [c["name"] for c in fxfinish.check(img, grid, clipped, change, count, False, want=16) if not c["ok"] and c["severity"] == "error"]
            if failed or img.size != (1024, 1024) or tuple(grid) != (4, 4):
                problems.append(f"the packer: {failed or 'no failed check'}, size {img.size}, grid {tuple(grid)}")
            step = ["--specs", specs, "--out", frames, "--textures-dir", built]
            code, v = call(step)
            if code != 0 or v.get("baked"):
                problems.append(f"the build step baked a sheet that was current: {v['summary']}")
            spec["comp"]["shape"]["radius"] = 0.28
            time.sleep(0.05)
            json.dump(spec, open(path, "w", encoding="utf-8"), indent=1)
            os.utime(path, (time.time() + 2, time.time() + 2))
            code, v = call(step)
            again = np.load(os.path.join(frames, "made_ring", "000.npy")).astype(np.float64)
            mean = float((r * again[..., 3]).sum() / max(again[..., 3].sum(), 1e-9))
            if code != 0 or not v.get("baked") or abs(mean - 0.28) > 0.02:
                problems.append(f"with its spec changed the build step did not bake the new ring (mean radius {mean:.3f}): {v['summary']}")
            if not os.path.isfile(os.path.join(look, "made_ring_strip.png")):
                problems.append("no LOOK strip was written")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    if problems:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"comp {case}: " + "; ".join(problems), "next_action": "kit/vfx/comp.py"}))
        return 1
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"comp {case}: a warped, panning ring through a ramp in {took:.2f} s - where its radius says, looping, on the ramp, clear of its cell; packed 1024 px 4x4; baked again when its spec changed",
                      "next_action": "none"}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
