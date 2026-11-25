"""depth_ref.py — a traced reference photo's RELATIVE DEPTH, cut exactly as its trace was, made once and kept: what a
build's depth check (kit/tools/depth_relief.py, inside Blender: no torch there) compares the model's relief to (his
V3 list, 3D stage A.3: "depth cavities" - a recess, a step, a fuller that no outline and no opening shows).

    python kit/vision/depth_ref.py assets/models/<name>.trace.json [--width 1400]
-> build/vision/depth/<name>.npz: near (float16, larger = nearer), mask (the object, holes filled as the trace's
   frame is), front on the RIGHT like every trace, source (which model); stamp: the photo's and the trace's bytes
   (sha1), so a re-cut trace or a changed photo makes it again.
The relief comes from MoGe-2 normals + Depth Anything 3 depth, integrated (`kit vision relief`, kit/gen/vision2.py in
the TRELLIS.2 environment: vetted phase B, offline) - on the Glock's side photo it shows the serrations, the slide
stop, the pins and the grip's texture, where Depth Anything V2 Small (the fallback when that environment is missing:
kit/vision run.depth) sees only the big steps.
Prints one JSON verdict line (schema 1).
"""

import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lines as L  # noqa: E402  (photo_frame: the trace's own cut of the photo)

REPO = L.REPO


def out_path(trace_path, build=None):
    name = os.path.basename(trace_path)[: -len(".trace.json")]
    root = build or os.environ.get("KIT_BUILD") or os.path.join(REPO, "build")
    return os.path.join(root, "vision", "depth", f"{name}.npz")


def stamp(trace_path):
    with open(trace_path, "rb") as fh:
        tb = fh.read()
    t = json.loads(tb.decode("utf-8"))
    src = os.path.join(REPO, t.get("source") or "")
    h = hashlib.sha1(tb)
    if os.path.isfile(src):
        with open(src, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def fresh(trace_path, build=None):
    """the kept depth when it is still this trace's and this photo's -> its path, else None"""
    p = out_path(trace_path, build)
    if not os.path.isfile(p):
        return None
    try:
        with np.load(p) as z:
            return p if str(z["stamp"]) == stamp(trace_path) else None
    except (OSError, KeyError, ValueError):
        return None


def _env_python(name):
    """a kit tool environment's python (Run.tool's rule: the <NAME> variable, else ~/.cache/roblox-kit/envs/<name>)"""
    env = os.environ.get(name.upper())
    if env:
        return env
    home = os.path.expanduser("~")
    for c in (os.path.join(home, ".cache", "roblox-kit", "envs", name, "Scripts", "python.exe"),
              os.path.join(home, ".cache", "roblox-kit", "envs", name, "bin", "python")):
        if os.path.isfile(c):
            return c
    return None


def _moge_relief(rgba, p):
    """the relief by MoGe-2 + Depth Anything 3 (kit/gen/vision2.py relief) -> height (H, W) or None"""
    import subprocess  # noqa: PLC0415

    py = _env_python("trellis2")
    if not py:
        return None
    cut = p[:-4] + "_cut.png"
    rgba.save(cut)
    out = p[:-4] + "_moge.npz"
    run = subprocess.run([py, os.path.join(REPO, "kit", "gen", "vision2.py"), "relief", cut, "-o", out],
                         capture_output=True, text=True, timeout=900, cwd=REPO)
    if run.returncode != 0 or not os.path.isfile(out):
        return None
    with np.load(out) as z:
        return z["height"].astype(np.float32)


def make(trace_path, width=1400, build=None):
    with open(trace_path, encoding="utf-8") as fh:
        t = json.load(fh)
    if not t.get("source"):
        raise ValueError(f"{os.path.basename(trace_path)}: no source photo")
    info = dict(t, photo=t["source"])
    rgb, mask = L.photo_frame(info)
    im = Image.fromarray(rgb)
    if im.width > width:
        im = im.resize((width, max(16, round(width * im.height / im.width))), Image.BICUBIC)
    m = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize(im.size, Image.NEAREST)) > 127
    p = out_path(trace_path, build)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    rgba = Image.fromarray(np.dstack([np.asarray(im), (m * 255).astype(np.uint8)]), "RGBA")
    near, source = _moge_relief(rgba, p), "moge-2-vitl-normal + da3-mono-large (relief)"
    if near is None or near.shape != m.shape:
        import run as V  # noqa: PLC0415  (the vetted models, offline: torch only here)

        near, source = V.depth(im), "depth-anything-v2-small (relative depth; the TRELLIS.2 environment is missing)"
    np.savez_compressed(p, near=near.astype(np.float16), mask=m, stamp=np.array(stamp(trace_path)),
                        source=np.array(source))
    return p, im.size, source


def main(argv):
    if not argv or not argv[0].endswith(".trace.json"):
        print(json.dumps({"schema": 1, "status": "fail", "summary": "depth_ref: needs a .trace.json",
                          "next_action": "python kit/vision/depth_ref.py assets/models/<name>.trace.json"}))
        return 1
    width = int(argv[argv.index("--width") + 1]) if "--width" in argv else 1400
    kept = fresh(argv[0])
    if kept and "--force" not in argv:
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"depth_ref: kept {kept} (same trace, same photo)",
                          "next_action": "none", "depth": kept.replace(chr(92), "/")}))
        return 0
    try:
        p, size, source = make(argv[0], width)
    except (OSError, ValueError) as e:
        print(json.dumps({"schema": 1, "status": "fail", "summary": f"depth_ref: {e}",
                          "next_action": "kit vision setup (the depth model), or re-trace the view"}))
        return 1
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"depth_ref: {p} ({size[0]} x {size[1]}, {source})",
                      "next_action": "a build with a.trace_match(..., depth=True) compares its relief to it",
                      "depth": p.replace(chr(92), "/")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
