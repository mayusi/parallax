"""edge_calibrate.py — the calibration behind kit/refs/edges.py: how wide an edge's RAMP looks in a picture for a
known round. Builds kit/selftest/blender/build_edge_cal.py (six slabs rounded 0..4 mm), renders each slab from the
front with the kit's ortho studio light (kit/blender/look_ortho.py) composited on black — the way a game's
orthographic reference render looks — at two scales, measures the median ramp width of its outline's edges, and fits
width = alpha x radius + beta x mm_per_px + gamma. Writes kit/refs/edges_cal.json; prints one JSON line with every measured point.

    python kit/tools/edge_calibrate.py [--px 600,270]
"""

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "kit", "refs"))

ROUNDS = [0.0, 0.5, 1.0, 2.0, 3.0, 4.0]


def main(argv):
    import numpy as np  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    import edges as E  # noqa: PLC0415
    import look  # noqa: PLC0415

    bl = look.blender()
    r = subprocess.run([bl, "-b", "--factory-startup", "-P",
                        os.path.join(REPO, "kit", "selftest", "blender", "build_edge_cal.py"), "--", "--no-preview"],
                       cwd=REPO, capture_output=True, text=True, timeout=1800)
    blend = os.path.join(REPO, "build", "models", "_selftest_edge_cal.blend")
    man = os.path.join(REPO, "build", "models", "_selftest_edge_cal.manifest.json")
    if r.returncode != 0 or not os.path.isfile(blend):
        print(json.dumps({"status": "fail", "summary": "edge_calibrate: the slabs did not build",
                          "next_action": (r.stderr or r.stdout)[-300:]}))
        return 1
    with open(man, encoding="utf-8") as fh:
        bounds = json.load(fh)["part_bounds"]
    pxs = [int(v) for v in (argv[argv.index("--px") + 1] if "--px" in argv else "600,270").split(",")]
    pts = []
    out_dir = os.path.join(REPO, "build", "renders", "edge_cal")
    os.makedirs(out_dir, exist_ok=True)
    for px in pxs:
        for i, rad in enumerate(ROUNDS):
            lo, hi = bounds[f"Slab{i}"]
            pad = 10.0 / 280.0   # (10 mm of black round the slab: room to measure its outline's ramp)
            lo = [lo[0] - pad, lo[1], lo[2] - pad]
            hi = [hi[0] + pad, hi[1], hi[2] + pad]
            png = os.path.join(out_dir, f"slab{i}_{px}.png")
            p = subprocess.run([bl, "-b", blend, "-P", os.path.join(REPO, "kit", "blender", "look_ortho.py"), "--",
                                png, ",".join(map(str, lo)), ",".join(map(str, hi)), "--view", "front", "--px",
                                str(px), "--samples", "48"], capture_output=True, text=True, timeout=900)
            line = next((ln for ln in p.stdout.splitlines() if ln.startswith("LOOK_ORTHO ")), None)
            if not line:
                print(json.dumps({"status": "fail", "summary": f"edge_calibrate: render {png} failed",
                                  "next_action": (p.stderr or p.stdout)[-300:]}))
                return 1
            info = json.loads(line[len("LOOK_ORTHO "):])
            mm_per_px = 280.0 / info["px_per_unit"]
            rgba = np.asarray(Image.open(png).convert("RGBA")).astype(np.float32)
            a = rgba[..., 3:4] / 255.0
            gray = (rgba[..., :3] * a).mean(axis=2)                     # (composited on black)
            w, _m = E.edge_widths(gray.astype(np.uint8), reach=max(10, int(5.0 / mm_per_px)))
            v = w[~np.isnan(w)]
            pts.append({"round_mm": rad, "px": px, "mm_per_px": round(mm_per_px, 4),
                        "width_mm": round(float(np.median(v)) * mm_per_px, 3) if len(v) else None, "samples": len(v)})
    good = [q for q in pts if q["width_mm"] is not None]
    A = np.array([[q["round_mm"], q["mm_per_px"], 1.0] for q in good])
    y = np.array([q["width_mm"] for q in good])
    (al, be, ga), *_ = np.linalg.lstsq(A, y, rcond=None)   # width = alpha r + beta mm_per_px + gamma
    pred = (y - be * A[:, 1] - ga) / al
    err = float(np.max(np.abs(pred - A[:, 0])))
    cal = {"alpha": round(float(al), 4), "beta": round(float(be), 4), "gamma": round(float(ga), 4),
           "err_mm": round(err, 2),
           "source": "kit/tools/edge_calibrate.py (Blender slabs 0-4 mm, ortho studio light on black)", "points": pts}
    with open(os.path.join(REPO, "kit", "refs", "edges_cal.json"), "w", encoding="utf-8") as fh:
        json.dump(cal, fh, indent=1)
    print(json.dumps({"schema": 1, "status": "pass", "summary": f"edge calibration: width = {al:.3f} r + {be:.3f} "
                      f"mm/px + {ga:.3f} over {len(good)} renders, worst radius error {err:.2f} mm",
                      "next_action": "kit/refs/edges_cal.json written; kit refs edges / kit look edges use it",
                      "points": pts}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
