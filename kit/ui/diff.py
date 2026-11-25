"""diff.py — VISUAL REGRESSION: every screen against its GOLDEN (the frame the owner approved). A pipeline change, a
re-lettered piece or a moved node shows up here before anyone has to notice it by eye.

    python kit/ui/diff.py [<Screen> ...] [--approve] [--build build/ui] [--library library/ui] [--tolerance 0.004]

- --approve: the screen's current desktop frame becomes its golden (library/ui/<identity>/screens/<Screen>/golden.png +
  golden.json: the model sha it was made from). Do it when the OWNER rates the screen (>= 7) — a golden is a look the
  owner accepted, never one the pipeline liked.
- otherwise: each screen with a golden is diffed (a slight blur absorbs anti-aliasing noise; a pixel counts when its
  colour moved > 24/255); above the tolerance (a share of the frame) it is reported with the changed regions, and
  build/ui/diff/<Screen>.png shows golden | now | the changes boxed in red.
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def package(library, screen):
    hits = glob.glob(os.path.join(library, "*", "screens", screen))
    return hits[0] if hits else None


def changed(a, b, thr=24):
    """per-pixel change mask between two frames (blurred a little: anti-aliasing is not a change)"""
    if a.size != b.size:
        b = b.resize(a.size)
    x = np.asarray(a.convert("RGB").filter(ImageFilter.GaussianBlur(1.2)), dtype=np.int16)
    y = np.asarray(b.convert("RGB").filter(ImageFilter.GaussianBlur(1.2)), dtype=np.int16)
    return np.abs(x - y).max(-1) > thr


def regions(mask, n=6):
    import cv2
    m = cv2.dilate(mask.astype(np.uint8), np.ones((15, 15), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(m)
    boxes = [tuple(int(v) for v in stats[i][:4]) for i in range(1, count) if stats[i][4] >= 30]
    boxes.sort(key=lambda b: -b[2] * b[3])
    return boxes[:n]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("screens", nargs="*")
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--build", default=os.path.join("build", "ui"))
    ap.add_argument("--library", default=os.path.join("library", "ui"))
    ap.add_argument("--models", default=os.path.join("src", "ui"))
    ap.add_argument("--tolerance", type=float, default=0.004)
    ap.add_argument("--note", default=None, help="why this golden (kept in golden.json)")
    a = ap.parse_args(argv)
    names = a.screens or sorted(os.path.basename(p)[: -len(".desktop.png")] for p in glob.glob(os.path.join(a.build, "*.desktop.png")))
    if a.approve:
        if not a.screens:
            return emit("fail", "diff --approve: name the screen(s) the owner approved", "lune run kit ui diff <Screen> --approve")
        done = []
        for s in names:
            pkg, now = package(a.library, s), os.path.join(a.build, f"{s}.desktop.png")
            if not pkg or not os.path.isfile(now):
                return emit("fail", f"diff --approve: {s} has no package or no desktop frame", "lune run kit ui (then kit ui vault)")
            Image.open(now).convert("RGB").save(os.path.join(pkg, "golden.png"))
            mp = os.path.join(a.models, f"{s}.model.json")
            sha = hashlib.sha256(open(mp, "rb").read()).hexdigest() if os.path.isfile(mp) else None
            with open(os.path.join(pkg, "golden.json"), "w", encoding="utf-8", newline="\n") as fh:
                json.dump({"schema": 1, "screen": s, "model_sha256": sha, "approved": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "note": a.note}, fh, indent=1)
            done.append(s)
        return emit("pass", f"diff: golden saved for {', '.join(done)}", "lune run kit ui diff (later builds are compared with it)")
    report, checked = [], 0
    os.makedirs(os.path.join(a.build, "diff"), exist_ok=True)
    for s in names:
        pkg = package(a.library, s)
        gold = pkg and os.path.join(pkg, "golden.png")
        now = os.path.join(a.build, f"{s}.desktop.png")
        if not gold or not os.path.isfile(gold) or not os.path.isfile(now):
            continue
        checked += 1
        g, n = Image.open(gold).convert("RGB"), Image.open(now).convert("RGB")
        mask = changed(g, n)
        share = float(mask.mean())
        if share <= a.tolerance:
            continue
        boxes = regions(mask)
        sheet = Image.new("RGB", (g.width * 2 + 10, g.height), (30, 30, 34))
        sheet.paste(g, (0, 0))
        marked = n.copy()
        d = ImageDraw.Draw(marked)
        for x, y, w, h in boxes:
            d.rectangle([x, y, x + w, y + h], outline=(255, 40, 40), width=4)
        sheet.paste(marked, (g.width + 10, 0))
        out = os.path.join(a.build, "diff", f"{s}.png")
        sheet.resize((sheet.width // 2, sheet.height // 2)).save(out)
        report.append({"screen": s, "changed": round(share, 4), "regions": boxes, "sheet": out.replace(chr(92), "/")})
    with open(os.path.join(a.build, "diff", "report.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"schema": 1, "checked": checked, "changed": report}, fh, indent=1)
    if not checked:
        return emit("pass", "diff: no screen has a golden yet", "when the owner rates a screen >= 7: lune run kit ui diff <Screen> --approve")
    if report:
        r = report[0]
        return emit("pass", f"diff: {len(report)} of {checked} screen(s) changed against their golden ({', '.join(x['screen'] for x in report[:5])})",
                    f"LOOK at {r['sheet']}: meant? then re-approve with the owner; not meant? undo it")
    return emit("pass", f"diff: {checked} screen(s) match their golden", "none - proceed")


if __name__ == "__main__":
    sys.exit(main())
