"""frames.py — `kit refs frames`: a VIDEO as reference pictures — a turntable, a model viewer, a gameplay inspect, an
unboxing: every side at one light, often sharper than any still online. ffmpeg pulls frames, then the blurred ones
(motion, focus: a low Laplacian variance against the clip's own sharp frames) and the near-duplicates (a perceptual
hash within a few bits: the camera held still) are dropped, so what is left is a set of DIFFERENT sharp views.

    lune run kit refs frames <video> --name <name> [--fps 2] [--start s] [--end s] [--max 60] [--blur 0.45]
        [--dup 6] [--out <folder>]

Writes <folder> (default refs/<name>_frames/; refs/private/... for a private source — say so with --out) with
<name>_f<seconds>.png, a contact sheet build/refs/<name>_frames.png, and prints one JSON line. A video's licence is
the video's: measure-only for anything not free (the owner's rule), never shipped.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def sharpness(gray):
    """variance of the Laplacian (a sharp frame has strong fine edges)"""
    import cv2  # noqa: PLC0415

    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def dhash(gray, size=8):
    """a 64-bit difference hash: the picture's coarse structure (survives small shifts, compression, exposure)"""
    import cv2  # noqa: PLC0415

    s = cv2.resize(gray, (size + 1, size), interpolation=cv2.INTER_AREA)
    bits = (s[:, 1:] > s[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2) if bits.size else 0


def select(grays, blur=0.45, dup=6, max_keep=60):
    """indices of the frames to keep (pure): sharp ones (>= blur x the clip's 80th-percentile sharpness), then each
    kept only if its hash differs by > dup bits from every frame kept so far (the sharpest first), in time order"""
    import numpy as np  # noqa: PLC0415

    if not grays:
        return [], []
    sh = [sharpness(g) for g in grays]
    ref = float(np.percentile(sh, 80)) or 1e-9
    sharp = [i for i, s in enumerate(sh) if s >= blur * ref]
    hashes = {i: dhash(grays[i]) for i in sharp}
    kept = []
    for i in sorted(sharp, key=lambda k: -sh[k]):
        if all(bin(hashes[i] ^ hashes[j]).count("1") > dup for j in kept):
            kept.append(i)
        if len(kept) >= max_keep:
            break
    return sorted(kept), sh


def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv):
    import cv2  # noqa: PLC0415

    if not argv or argv[0].startswith("--") or "--name" not in argv:
        return emit("fail", "refs frames: needs <video> --name <name>",
                    "lune run kit refs frames turntable.mp4 --name x --fps 2")
    video, name = argv[0], _arg(argv, "--name")
    if not os.path.isfile(video):
        return emit("fail", f"refs frames: {video} not found", "give the video's path")
    ff = shutil.which("ffmpeg")
    if not ff:
        return emit("fail", "refs frames: ffmpeg is not installed", "winget install Gyan.FFmpeg (vet it first)")
    fps = float(_arg(argv, "--fps", 2))
    out = _arg(argv, "--out") or os.path.join(REPO, "refs", f"{name}_frames")
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [ff, "-hide_banner", "-loglevel", "error"]
        if "--start" in argv:
            cmd += ["-ss", _arg(argv, "--start")]
        if "--end" in argv:
            cmd += ["-to", _arg(argv, "--end")]
        cmd += ["-i", video, "-vf", f"fps={fps}", os.path.join(tmp, "f_%05d.png")]
        r = subprocess.run(cmd, capture_output=True, text=True)
        files = sorted(f for f in os.listdir(tmp) if f.endswith(".png"))
        if r.returncode != 0 or not files:
            return emit("fail", f"refs frames: ffmpeg found no frames ({(r.stderr or '').strip()[:160]})",
                        "check the video plays; --start / --end in seconds")
        grays = [cv2.imread(os.path.join(tmp, f), cv2.IMREAD_GRAYSCALE) for f in files]
        kept, sh = select(grays, float(_arg(argv, "--blur", 0.45)), int(_arg(argv, "--dup", 6)),
                          int(_arg(argv, "--max", 60)))
        os.makedirs(out, exist_ok=True)
        t0 = float(_arg(argv, "--start", 0) or 0)
        saved = []
        for i in kept:
            dst = os.path.join(out, f"{name}_f{t0 + i / fps:07.2f}.png")
            shutil.copyfile(os.path.join(tmp, files[i]), dst)
            saved.append(dst)
    sheet = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "refs", f"{name}_frames.png")
    _contact(saved, sheet)
    rel = lambda p: os.path.relpath(p, REPO).replace(os.sep, "/")  # noqa: E731
    return emit("pass", f"refs frames {name}: {len(files)} frames at {fps:g}/s -> {len(saved)} kept (sharp + "
                f"different) in {rel(out)}", f"LOOK at {rel(sheet)}; trace / inventory the best views "
                f"(lune run kit refs inventory <frame> --name {name})", kept=len(saved), pulled=len(files),
                folder=rel(out), sheet=rel(sheet))


def _contact(paths, dest, cell=220, cols=6):
    from PIL import Image, ImageDraw  # noqa: PLC0415

    if not paths:
        return
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 16)), (24, 24, 28))
    dr = ImageDraw.Draw(sheet)
    for k, p in enumerate(paths):
        im = Image.open(p).convert("RGB")
        im.thumbnail((cell, cell))
        x, y = (k % cols) * cell, (k // cols) * (cell + 16)
        sheet.paste(im, (x, y))
        dr.text((x + 2, y + cell + 2), os.path.basename(p)[-14:], fill=(220, 220, 220))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    sheet.save(dest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
