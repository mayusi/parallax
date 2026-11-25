"""outline.py — a reference model's PARTS as exact outlines to build from (kit refs outline). The technique that took
the ODM swords from 4 to 9 (owner 2026-10-18): each part of a checked reference model projected on its flat side,
rasterized, traced — its outer outline and its real openings (a finger window, never a checker cell) in mm, with the
part's thickness range — then a.cad extrudes each over its own thickness, edges eased.

    lune run kit refs outline <model.glb|fbx|obj> --name <name> [--length-mm L | --scale <mm per unit>]
        [--plane auto|xy|xz|yz] [--skip a,b] [--only a,b] [--res 0.25] [--simplify 0.6] [--min-hole 25]

--length-mm: the model's longest extent in mm (its real size; else 1 unit = 1 mm). --plane: the flat plane the parts
are traced on (auto: the two longest axes; the thinnest is "through"). Parts far from the rest (a stray backdrop) are
left out and named. Writes assets/models/<name>.outline.json and build/refs/<name>_outline.png (each part drawn).
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
_KIT = os.path.abspath(os.path.join(HERE, ".."))
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
from blender_path import find_blender  # noqa: E402

AXES = {"x": 0, "y": 1, "z": 2}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def blender():
    return find_blender()


def auto_plane(points):
    """(n, 3) -> (u, v, w) axis indices: the flat plane = the two longest extents, w the thinnest (through)"""
    ext = np.ptp(points, axis=0)
    w = int(np.argmin(ext))
    u, v = [i for i in range(3) if i != w]
    return u, v, w


def plane_of(text, points):
    if text in (None, "", "auto"):
        return auto_plane(points)
    u, v = AXES[text[0]], AXES[text[1]]
    return u, v, 3 - u - v


def drop_strays(centres, sizes, factor=1.5):
    """a part whose centre lies outside the OTHER parts' box grown by `factor` x its size -> True (a stray backdrop,
    a far plane: the ODM handle's Plane.002 sat 8 m away)"""
    n = len(centres)
    out = np.zeros(n, bool)
    if n < 3:
        return out
    for i in range(n):
        others = np.delete(np.arange(n), i)
        lo = (centres[others] - sizes[others] / 2).min(axis=0)
        hi = (centres[others] + sizes[others] / 2).max(axis=0)
        span = hi - lo
        out[i] = bool(np.any(centres[i] < lo - factor * span) or np.any(centres[i] > hi + factor * span))
    return out


def outline_part(P2, T, res, min_area=10.0, min_hole=25.0, eps=0.6):
    """a part's triangles projected (n, 2) mm + (m, 3) -> [{pts, hole, area_mm2}]: its outer contours and real holes
    (a checker cell or a pixel gap between triangles is no hole: closed over, dropped by area)"""
    import cv2  # noqa: PLC0415

    lo = P2.min(axis=0)
    W = int(np.ceil(np.ptp(P2[:, 0]) / res)) + 8
    H = int(np.ceil(np.ptp(P2[:, 1]) / res)) + 8
    m = np.zeros((H, W), np.uint8)
    px = (P2 - lo) / res + 4
    cv2.fillPoly(m, list(px[T].round().astype(np.int32)), 255)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))   # (pixel gaps between triangles closed)
    cnts, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    polys = []
    for i, c in enumerate(cnts):
        hole = bool(hier[0][i][3] >= 0)
        area = float(cv2.contourArea(c)) * res * res
        if area < (min_hole if hole else min_area):
            continue
        pts = (c[:, 0, :].astype(np.float64) - 4) * res + lo
        simp = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2), eps, True)[:, 0, :]
        keep = [simp[0]]
        for p in simp[1:]:   # (no two points closer than 3 x eps: the raster's steps gave fillets nothing to hold)
            if np.linalg.norm(p - keep[-1]) >= 3 * eps:
                keep.append(p)
        if len(keep) < 3:
            continue
        polys.append({"pts": [[round(float(x), 2), round(float(y), 2)] for x, y in keep], "hole": hole,
                      "area_mm2": round(area, 1)})
    return polys


def outlines(npz, scale, plane="auto", skip=(), only=(), res=0.25, eps=0.6, min_hole=25.0):
    with np.load(npz, allow_pickle=False) as f:   # (closed at once: Windows keeps an open npz from being deleted)
        d = {k: f[k] for k in f.files}
    names = [str(n) for n in d["__names"]]
    keys = [f"p{i}" for i in range(len(names))]
    pick = [i for i, n in enumerate(names)
            if not any(s and s.lower() in n.lower() for s in skip) and (not only or any(o.lower() in n.lower() for o in only))]
    Vs = {i: d[keys[i] + "__V"].astype(np.float64) for i in pick}
    cen = np.array([(Vs[i].min(0) + Vs[i].max(0)) / 2 for i in pick])
    siz = np.array([np.ptp(Vs[i], axis=0) for i in pick])
    stray = drop_strays(cen, siz)
    dropped = [names[i] for i, s in zip(pick, stray) if s]
    pick = [i for i, s in zip(pick, stray) if not s]
    allv = np.concatenate([Vs[i] for i in pick])
    u, v, w = plane_of(plane, allv)
    lo = allv.min(axis=0)
    parts = {}
    for i in pick:
        V = (Vs[i] - lo) * scale
        T = d[keys[i] + "__T"]
        polys = outline_part(V[:, [u, v]], T, res, min_hole=min_hole, eps=eps)
        if not polys:
            continue
        parts[names[i]] = {"polys": polys, "z": [round(float(V[:, w].min()), 2), round(float(V[:, w].max()), 2)],
                           "box": [round(float(x), 1) for x in np.ptp(V, axis=0)]}
    return {"scale": scale, "plane": "xyz"[u] + "xyz"[v], "through": "xyz"[w],
            "extent_mm": [round(float(x), 1) for x in np.ptp(allv, axis=0) * scale], "parts": parts,
            "dropped": dropped}


def preview(out, png, px_per_mm=4.0):
    """every part's outline drawn in its own colour, labelled — LOOK at it before building from it"""
    import cv2  # noqa: PLC0415

    allp = np.array([p for prt in out["parts"].values() for q in prt["polys"] for p in q["pts"]])
    lo, hi = allp.min(axis=0), allp.max(axis=0)
    W, H = int((hi[0] - lo[0]) * px_per_mm) + 80, int((hi[1] - lo[1]) * px_per_mm) + 80
    img = np.full((H, W, 3), 245, np.uint8)
    rng = np.random.default_rng(3)
    for name, prt in out["parts"].items():
        col = tuple(int(c) for c in rng.integers(40, 200, 3))
        for q in prt["polys"]:
            pts = ((np.array(q["pts"]) - lo) * px_per_mm + 40).astype(np.int32)
            pts[:, 1] = H - pts[:, 1]   # (y up on the sheet)
            cv2.polylines(img, [pts], True, (150, 150, 150) if q["hole"] else col, 2, cv2.LINE_AA)
        p0 = ((np.array(prt["polys"][0]["pts"]).mean(axis=0) - lo) * px_per_mm + 40).astype(int)
        cv2.putText(img, name[:18], (int(p0[0]), int(H - p0[1])), cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)
    os.makedirs(os.path.dirname(png), exist_ok=True)
    cv2.imwrite(png, img)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--name", required=True)
    ap.add_argument("--length-mm", type=float, default=0.0)
    ap.add_argument("--scale", type=float, default=0.0)
    ap.add_argument("--plane", default="auto")
    ap.add_argument("--skip", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--res", type=float, default=0.25)
    ap.add_argument("--simplify", type=float, default=0.6)
    ap.add_argument("--min-hole", type=float, default=25.0)
    a = ap.parse_args(argv)
    if not os.path.isfile(a.model):
        return emit("fail", f"refs outline: no model at {a.model}", "kit library get <uid> first, then its model.glb")
    exe = blender()
    if not exe:
        return emit("fail", "refs outline: Blender not found", "set BLENDER to blender's path")
    with tempfile.TemporaryDirectory() as tmp:
        npz = os.path.join(tmp, "parts.npz")
        p = subprocess.run([exe, "-b", "--factory-startup", "-P", os.path.join(HERE, "outline_dump.py"), "--",
                            a.model, npz], capture_output=True, text=True, timeout=600)
        if not os.path.isfile(npz):
            return emit("fail", f"refs outline: the dump failed: {(p.stderr or p.stdout)[-200:]}", "check the model opens")
        with np.load(npz) as f:
            allv = np.concatenate([f[k] for k in f.files if k.endswith("__V")])
        scale = a.scale or ((a.length_mm / float(np.ptp(allv, axis=0).max())) if a.length_mm else 1.0)
        out = outlines(npz, scale, a.plane, [s for s in a.skip.split(",") if s], [s for s in a.only.split(",") if s],
                       a.res, a.simplify, a.min_hole)
    if a.length_mm and out["dropped"]:   # (the length was read with the strays in: measure again without them)
        pass
    path = os.path.join(REPO, "assets", "models", f"{a.name}.outline.json")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"source": os.path.basename(a.model), **out}, fh, indent=1)
    png = os.path.join(REPO, "build", "refs", f"{a.name}_outline.png")
    preview(out, png)
    n_holes = sum(q["hole"] for p in out["parts"].values() for q in p["polys"])
    return emit("pass", f"refs outline {a.name}: {len(out['parts'])} part(s) traced on {out['plane']} "
                f"({out['extent_mm'][0]:.0f} x {out['extent_mm'][1]:.0f} x {out['extent_mm'][2]:.0f} mm), {n_holes} "
                f"opening(s)" + (f"; left out (strays): {', '.join(out['dropped'])}" if out["dropped"] else ""),
                f"LOOK at {os.path.relpath(png, REPO)}; build each part: a.cad extruding its outline over its 'z' range "
                f"(assets/models/{a.name}.outline.json)", parts=len(out["parts"]), dropped=out["dropped"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
