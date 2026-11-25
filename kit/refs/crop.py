"""crop.py — LOOK at a trace's parts on their own picture, in millimetres (kit refs crop).

    python kit/refs/crop.py <name>.trace.json --f <f0>..<f1> --h <h0>..<h1> [--parts a,b,...] [--out <png>]
                            [--grid 5] [--size 900] [--px "f,h;f,h"]

A trace's preview shows the whole picture at its full size (thousands of pixels: unreadable as one image). This
crops ONE window of it — given in the build's own millimetres (the frame `kit refs profiles` wrote: f forward of the
anchor's rear end, h up, the anchor's top at top_mm) — draws a mm grid on it (every --grid mm, brighter every 2x) and
the outlines of the named traced parts, front on the RIGHT, scaled to --size px. That is how a wrong mask is SEEN:
a grip safety that swallowed the thumb safety beside it, a button traced with the shadow round it, a hammer the
perspective pushed forward. A part that is wrong there is RETRACED (kit trace --part-box / --part-point with clicks
on it and !clicks on what it swallowed) or a better picture is found — never modelled.
--px "f,h;f,h": the picture pixels of points given in mm (to write the clicks of a retrace: --part-point
"name=x,y;!x,y"). Needs <name>.profiles.json beside the trace (lune run kit refs profiles first).
One JSON verdict line.
"""

import json
import os
import sys


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def _range(text):
    a, b = text.split("..")
    return float(a), float(b)


def frame(trace, prof):
    """mm (f, h) -> the picture's pixels (x, y), the way kit refs profiles laid the mm frame on the trace"""
    fr, k = trace["frame"], prof["mm_per_unit"]
    a = trace["parts"][prof["anchor"]]
    u0, u1 = min(p[0] for p in a), max(p[0] for p in a)
    mid = sorted(p[1] for p in a if u0 + 0.2 * (u1 - u0) < p[0] < u0 + 0.8 * (u1 - u0))
    vt = mid[min(len(mid) - 1, int(0.98 * len(mid)))] if mid else max(p[1] for p in a)

    def px(f, h):
        u, v = u0 + f / k, vt + (h - prof["top_mm"]) / k
        x = fr["x0"] + ((1 - u) if trace.get("front") == "left" else u) * fr["length_px"]
        return x, fr["y1"] - v * fr["length_px"]
    return px


def main(argv):
    if not argv or not argv[0].endswith(".trace.json"):
        return emit("fail", "refs crop: needs a <name>.trace.json", 'lune run kit refs crop assets/models/<name>.trace.json '
                    '--f 0..60 --h -70..20 --parts grip,trigger')
    path = argv[0]
    prof_path = path.replace(".trace.json", ".profiles.json")
    if not os.path.isfile(prof_path):
        return emit("fail", f"refs crop: no {os.path.basename(prof_path)} (the mm frame)",
                    f"lune run kit refs profiles {path} --anchor <part> --length-mm <mm> [--top-mm <h>]")
    with open(path, encoding="utf-8") as fh:
        t = json.load(fh)
    with open(prof_path, encoding="utf-8") as fh:
        prof = json.load(fh)
    if not t.get("frame") or t.get("rotate") or t.get("straighten") or t.get("homography"):
        return emit("fail", "refs crop: this trace has no plain pixel frame (traced with --rotate / --straighten)",
                    "retrace without them for a crop, or crop the picture by hand")
    px = frame(t, prof)
    if _arg(argv, "--px"):
        pts = [tuple(float(v) for v in xy.split(",")) for xy in _arg(argv, "--px").split(";") if xy.strip()]
        got = [f"{round(px(f, h)[0])},{round(px(f, h)[1])}" for f, h in pts]
        return emit("pass", f"refs crop: picture pixels of {len(pts)} point(s): {';'.join(got)}",
                    'use them as clicks: --part-point "name=x,y;!x,y" (a ! for what is NOT the part)', pixels=got)
    if not _arg(argv, "--f") or not _arg(argv, "--h"):
        return emit("fail", "refs crop: give the window in mm: --f <f0>..<f1> --h <h0>..<h1>",
                    "the extents of each part are in the profiles file (extents: [f0, f1, h0, h1])")
    from PIL import Image, ImageDraw  # noqa: PLC0415

    f0, f1 = _range(_arg(argv, "--f"))
    h0, h1 = _range(_arg(argv, "--h"))
    grid = float(_arg(argv, "--grid", "5"))
    size = int(_arg(argv, "--size", "900"))
    names = [n for n in (_arg(argv, "--parts", "") or "").split(",") if n]
    lost = [n for n in names if n not in prof["parts"]]
    if lost:
        return emit("fail", f"refs crop: no traced part {', '.join(lost)} (it has: {', '.join(sorted(prof['parts']))})",
                    "name the parts as the trace has them")
    src = t.get("source") or ""
    if not os.path.isfile(src):
        return emit("fail", f"refs crop: the traced picture {src} is not here", "the trace's 'source' must exist")
    im = Image.open(src).convert("RGB")
    if t.get("rotate"):
        return emit("fail", "refs crop: a trace made with --rotate has no plain pixel frame", "crop the picture by hand")
    dr = ImageDraw.Draw(im)
    lw = max(1, round(max(im.size) / 1400))
    f = int(f0 // grid) * grid
    while f <= f1:
        bright = abs((f / grid) % 2) < 1e-6
        dr.line([px(f, h0), px(f, h1)], fill=(0, 200, 255) if bright else (0, 90, 160), width=lw)
        f += grid
    h = int(h0 // grid) * grid
    while h <= h1:
        bright = abs((h / grid) % 2) < 1e-6
        dr.line([px(f0, h), px(f1, h)], fill=(0, 200, 255) if bright else (0, 90, 160), width=lw)
        h += grid
    for n in names:
        ring = prof["parts"][n]
        dr.line([px(*p) for p in ring] + [px(*ring[0])], fill=(255, 0, 80), width=lw * 3)
    (xa, ya), (xb, yb) = px(f0, h1), px(f1, h0)
    box = (int(max(0, min(xa, xb))), int(max(0, min(ya, yb))), int(min(im.width, max(xa, xb))),
           int(min(im.height, max(ya, yb))))
    if box[2] - box[0] < 4 or box[3] - box[1] < 4:
        return emit("fail", "refs crop: that window is outside the picture", "check --f / --h against the extents")
    c = im.crop(box)
    if t.get("front") == "left":
        c = c.transpose(Image.FLIP_LEFT_RIGHT)  # (front on the right, like every plot and trace)
    s = size / max(c.size)
    c = c.resize((max(1, int(c.width * s)), max(1, int(c.height * s))), Image.LANCZOS)
    out = _arg(argv, "--out") or os.path.join("build", "refs", "crops",
                                              f"{t.get('name', 'trace')}_{f0:g}_{f1:g}_{h0:g}_{h1:g}.png")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    c.save(out)
    mm_px = (f1 - f0) / c.width
    return emit("pass", f"refs crop: {out.replace(chr(92), '/')} ({c.width} x {c.height} px, {1 / mm_px:.1f} px per mm; "
                f"grid {grid:g} mm; parts drawn: {', '.join(names) or 'none'})",
                f"LOOK at {out.replace(chr(92), '/')}: does each red outline hug its part? A wrong one: retrace it "
                "(kit trace --part-box/--part-point, !clicks on what it swallowed) or find a better picture",
                out=out.replace("\\", "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
