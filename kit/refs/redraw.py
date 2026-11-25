"""redraw.py — `kit refs redraw`: a traced outline (a `kit refs detail` piece, an inlay polygon, a trace part) REDRAWN
as true lines + arcs (kit/tools/primfit.py), written back for the build and drawn over the trace to LOOK at: the
redraw in cyan, the trace in red, every arc's radius printed on it. Near-equal radii are made equal (--equal 0.08);
--mirror x,<mm> fits one side of a symmetric part and mirrors it.

    lune run kit refs redraw <file.json> [--piece 0] [--key outline] [--tol 0.15] [--corner 35] [--mirror x,0]
        [--equal 0.08] [--name <name>] [--out <path>]

<file.json>: a .detail.json ({"pieces": [{"outline": [[x, y] mm ...]}]}), or any JSON with a list of points under
--key. Writes assets/models/<name>.redraw.json ({"prims": [...], "report": {...}}: in a.cad, add(redraw(prims))
or prims_face(prims)) and build/refs/<name>_redraw.png; prints one JSON line.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "kit", "tools"))

import primfit  # noqa: E402


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _arg(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def points_of(doc, piece=0, key="outline"):
    if isinstance(doc, dict) and "pieces" in doc:
        return doc["pieces"][piece][key]
    if isinstance(doc, dict) and key in doc:
        return doc[key]
    if isinstance(doc, list) and doc and isinstance(doc[0], (list, tuple)) and len(doc[0]) == 2:
        return doc
    raise ValueError(f"no points under '{key}' (piece {piece})")


def preview(pts, prims, path, px=1400):
    import numpy as np  # noqa: PLC0415
    from PIL import Image, ImageDraw  # noqa: PLC0415

    p = np.asarray(pts, float)
    s = primfit.sample(prims, 0.02)
    lo, hi = np.minimum(p.min(0), s.min(0)), np.maximum(p.max(0), s.max(0))
    k = (px - 80) / max(float((hi - lo).max()), 1e-9)
    H = int((hi[1] - lo[1]) * k) + 80

    def to(q):
        return [(40 + (x - lo[0]) * k, H - 40 - (y - lo[1]) * k) for x, y in q]
    im = Image.new("RGB", (px, H), (250, 250, 248))
    dr = ImageDraw.Draw(im)
    dr.line(to(np.vstack([p, p[:1]])), fill=(220, 40, 40), width=1)
    dr.line(to(np.vstack([s, s[:1]])), fill=(0, 150, 200), width=3)
    for q in prims:
        (x, y), = to([q["a"]])
        dr.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(20, 20, 20))
        if q["type"] == "arc":
            (mx, my), = to([q["m"]])
            dr.text((mx + 4, my + 2), f"R{q['r']:.2f}", fill=(0, 90, 140))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path)


def main(argv):
    if not argv or argv[0].startswith("--"):
        return emit("fail", "refs redraw: needs <file.json>", "lune run kit refs redraw assets/models/x_hammer.detail.json")
    src = argv[0]
    try:
        with open(src, encoding="utf-8") as fh:
            pts = points_of(json.load(fh), int(_arg(argv, "--piece", 0)), _arg(argv, "--key", "outline"))
    except (OSError, ValueError, KeyError, IndexError) as e:
        return emit("fail", f"refs redraw: {e}", "a .detail.json, or --key <the points' key>")
    tol, corner = float(_arg(argv, "--tol", 0.15)), float(_arg(argv, "--corner", 35))
    try:
        eq = float(_arg(argv, "--equal", 0.08))
        if "--mirror" in argv:
            ax, at = _arg(argv, "--mirror").split(",")
            prims = primfit.fit_mirrored(pts, ax, float(at), tol=tol, corner_deg=corner, equal=eq)
        else:
            prims = primfit.fit(pts, tol=tol, corner_deg=corner, equal=eq)
    except ValueError as e:
        return emit("fail", f"refs redraw: {e}", "check the outline / the mirror line")
    rep = primfit.report(pts, prims)
    base = os.path.basename(src)
    name = _arg(argv, "--name") or base.split(".")[0]
    dest = _arg(argv, "--out") or os.path.join(REPO, "assets", "models", f"{name}.redraw.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump({"source": src.replace(os.sep, "/"), "tol_mm": tol, "prims": prims, "report": rep}, fh, indent=1)
    pv = os.path.join(REPO, os.environ.get("KIT_BUILD", "build"), "refs", f"{name}_redraw.png")
    preview(pts, prims, pv)
    rel = lambda p: os.path.relpath(p, REPO).replace(os.sep, "/")  # noqa: E731
    return emit("pass", f"refs redraw {name}: {rep['lines']} lines + {rep['arcs']} arcs, within {rep['max_mm']} mm of "
                f"the trace (mean {rep['mean_mm']}); radii {rep['radii_mm'][:8]}",
                f"LOOK at {rel(pv)} (cyan redraw over the red trace); build it: add(redraw(P['prims'])) with "
                f"P = the redraw file's JSON, or prims_face(prims)", preview=rel(pv), redraw=rel(dest), **rep)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
