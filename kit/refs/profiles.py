"""profiles.py — a trace's PARTS as millimetre profiles to build from (kit refs profiles).

    python kit/refs/profiles.py <name>.trace.json --anchor <part> --length-mm <mm> [--top-mm <h>] [--out <file.json>]
                                [--tolerance-mm 0.3]

The data a model is built FROM, not drawn from memory: every part `kit trace` segmented in a picture (--part-box /
--part-text / --part-point) and the whole outline with its holes, in millimetres. One part of known size anchors the
scale and the frame: `--anchor slide --length-mm 190.8` puts f = 0 at the anchor's rear end (u = its smallest) and
scales its length to 190.8 mm; `--top-mm 14` puts the anchor's top (its middle 60 %'s 98th percentile: a sight on it
does not count) at h = 14 — the build script's own coordinates (f forward, h up; a.cad / a.extrude profiles).
Each ring is lightly smoothed (a 3-point running mean, corners kept where the turn is sharp) and simplified to
--tolerance-mm (Douglas-Peucker), so a profile is clean enough to extrude yet within a fraction of a millimetre of the
traced mask. One JSON verdict line; the profiles go to --out (default: assets/models/<trace>.profiles.json).
"""

import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "blender"))


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _arg(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def smooth(ring, corner_deg=55.0):
    """a 3-point running mean along a closed ring, a vertex kept where the ring turns sharper than corner_deg"""
    n = len(ring)
    if n < 5:
        return [tuple(p) for p in ring]
    out = []
    for i in range(n):
        (ax, ay), (bx, by), (cx, cy) = ring[i - 1], ring[i], ring[(i + 1) % n]
        v1, v2 = (bx - ax, by - ay), (cx - bx, cy - by)
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        turn = math.degrees(math.acos(max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2))))) if l1 and l2 else 0.0
        out.append((bx, by) if turn > corner_deg else ((ax + bx + cx) / 3, (ay + by + cy) / 3))
    return out


def simplify(ring, tol):
    """Douglas-Peucker on a closed ring (split at its two farthest points)"""
    if len(ring) < 4:
        return ring

    def dp(pts):
        if len(pts) < 3:
            return pts
        (x0, y0), (x1, y1) = pts[0], pts[-1]
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy) or 1e-12
        far, idx = -1.0, 0
        for i in range(1, len(pts) - 1):
            d = abs(dy * (pts[i][0] - x0) - dx * (pts[i][1] - y0)) / ln
            if d > far:
                far, idx = d, i
        if far <= tol:
            return [pts[0], pts[-1]]
        return dp(pts[: idx + 1])[:-1] + dp(pts[idx:])

    i0 = 0
    i1 = max(range(len(ring)), key=lambda i: math.hypot(ring[i][0] - ring[0][0], ring[i][1] - ring[0][1]))
    a = dp(ring[i0 : i1 + 1])
    b = dp(ring[i1:] + ring[:1])
    return a[:-1] + b[:-1]


def main(argv):
    if not argv or not argv[0].endswith(".trace.json"):
        return emit("fail", "refs profiles: needs a <name>.trace.json",
                    "lune run kit refs profiles assets/models/<name>.trace.json --anchor <part> --length-mm <mm>")
    path, anchor = argv[0], _arg(argv, "--anchor")
    length_mm, top_mm = _arg(argv, "--length-mm"), _arg(argv, "--top-mm")
    tol = float(_arg(argv, "--tolerance-mm", "0.3"))
    with open(path, encoding="utf-8") as fh:
        t = json.load(fh)
    parts = t.get("parts") or {}
    if not anchor or anchor not in parts or not length_mm:
        return emit("fail", f"refs profiles: --anchor must name a traced part ({', '.join(sorted(parts)) or 'none'}) "
                    "and --length-mm its real length", "e.g. --anchor slide --length-mm 190.8 --top-mm 14")
    a = parts[anchor]
    u0, u1 = min(p[0] for p in a), max(p[0] for p in a)
    k = float(length_mm) / max(u1 - u0, 1e-9)  # mm per trace unit
    mid = sorted(p[1] for p in a if u0 + 0.2 * (u1 - u0) < p[0] < u0 + 0.8 * (u1 - u0))
    v_top = mid[min(len(mid) - 1, int(0.98 * len(mid)))] if mid else max(p[1] for p in a)
    h0 = float(top_mm) if top_mm is not None else 0.0

    def mm(ring):
        pts = [((u - u0) * k, (v - v_top) * k + h0) for u, v in ring]
        return [[round(x, 2), round(y, 2)] for x, y in simplify(smooth(pts), tol)]

    out = {"source": t.get("source") or os.path.basename(path), "trace": path.replace("\\", "/"),
           "anchor": anchor, "length_mm": float(length_mm), "top_mm": h0, "mm_per_unit": round(k, 4),
           "frame": "f = mm forward of the anchor's rear end, h = mm up (the anchor's top at top_mm)",
           "outline": mm(t["outline"]), "holes": [mm(h) for h in t.get("holes", [])],
           "parts": {name: mm(ring) for name, ring in parts.items()},
           "part_quality": t.get("part_quality") or {}, "part_scores": t.get("part_scores") or {}}
    ext = {name: [round(min(p[0] for p in r), 1), round(max(p[0] for p in r), 1),
                  round(min(p[1] for p in r), 1), round(max(p[1] for p in r), 1)] for name, r in out["parts"].items()}
    out["extents"] = ext  # [f0, f1, h0, h1] per part
    dest = _arg(argv, "--out") or path.replace(".trace.json", ".profiles.json")
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    said = ", ".join(f"{n} f {e[0]}..{e[1]} h {e[2]}..{e[3]}" for n, e in list(ext.items())[:6])
    return emit("pass", f"refs profiles: {len(out['parts'])} part profile(s) in mm -> {dest.replace(chr(92), '/')} "
                f"({said})", "build each part FROM its profile (a.cad / a.extrude), then a.trace_match(parts=...) "
                "proves it", profiles=dest.replace("\\", "/"), extents=ext)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
