"""views.py — an asset's traced views on one millimetre scale: `lune run kit refs views <asset>`.

Every `kit trace` view (side, top, front, back) measures the object in its own units: its outline is normalised by
its own horizontal extent. Tied together — the side and top views share the object's length (the spec's length_mm),
the front and back views share the top view's width — they give ONE dimension table, and they CHECK each other: a
front view 30% taller than the side view means one of them is wrong (perspective, another pose, a cropped part), and
no model can match both. The side view's heights and the top view's widths, station by station, become cross-sections
in the format of a measured 3D reference (rbx_trace.loft_stations), and each named part traced in a view gets its
reference size in mm — so a build can be measured against the pictures instead of guessed.

    python kit/refs/views.py <asset> [--stations 48]  -> refs/<asset>.views.json + one JSON result line
"""

import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_trace as T  # noqa: E402

VIEW_OF_SUFFIX = {"side": "side", "top": "top", "bottom": "top", "front": "front", "frontview": "front",
                  "back": "back", "backview": "back"}
OK, WARN = 0.03, 0.10  # views agree within 3%: fine; within 10%: a warning; beyond: one of them is wrong


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status in ("pass", "warn") else 1  # (views that disagree are reported, not a crash)


def load_views(asset, root=ROOT):
    """{view: trace} for assets/models/<asset>_<view>.trace.json (a trace's own "view" field wins over its name)"""
    out = {}
    for path in sorted(glob.glob(os.path.join(root, "assets", "models", f"{asset}_*.trace.json"))):
        suffix = os.path.basename(path)[len(asset) + 1:-len(".trace.json")]
        with open(path, encoding="utf-8") as fh:
            t = json.load(fh)
        view = t.get("view") or VIEW_OF_SUFFIX.get(suffix)
        if view and view not in out:
            out[view] = t
    return out


def grade(a, b):
    r = abs(a / b - 1.0) if b else float("inf")
    return r, ("ok" if r <= OK else "warn" if r <= WARN else "bad")


def measure_views(views, length_mm, stations=48):
    """-> dict: size_mm [width, height, length], per-view scale, cross-view checks, stations, parts (mm)"""
    if "side" not in views:
        raise ValueError("no side view traced: lune run kit trace <side picture> --name <asset>_side")
    side, top = views["side"], views.get("top")
    L = float(length_mm)
    H = side["height_ratio"] * L
    W = top["height_ratio"] * L if top else None
    scale = {"side": {"mm_per_unit": L, "anchor": "the spec's length", "perspective_suspect":
                      bool((side.get("perspective") or {}).get("suspect"))}}
    if top:
        scale["top"] = {"mm_per_unit": L, "anchor": "the spec's length",
                        "perspective_suspect": bool((top.get("perspective") or {}).get("suspect"))}
    checks = []
    for v in ("front", "back"):
        t = views.get(v)
        if not t:
            continue
        if W:  # its width is the top view's: its height must match the side view's
            hv = t["height_ratio"] * W
            r, g = grade(hv, H)
            scale[v] = {"mm_per_unit": W, "anchor": "the top view's width",
                        "perspective_suspect": bool((t.get("perspective") or {}).get("suspect"))}
            checks.append({"what": f"height: {v} view vs side view", "mm": [round(hv, 1), round(H, 1)],
                           "off": round(r, 3), "grade": g})
        else:  # no top view: its height is the side view's, which gives the width
            scale[v] = {"mm_per_unit": H / t["height_ratio"], "anchor": "the side view's height",
                        "perspective_suspect": bool((t.get("perspective") or {}).get("suspect"))}
            W = W or H / t["height_ratio"]
    if top and "front" in views and "back" in views:
        hf, hb = views["front"]["height_ratio"] * W, views["back"]["height_ratio"] * W
        r, g = grade(hf, hb)
        checks.append({"what": "height: front view vs back view", "mm": [round(hf, 1), round(hb, 1)],
                       "off": round(r, 3), "grade": g})
    # stations: the side view's vertical extent and the top view's lateral extent at each position along the length
    # a side or top trace is stored back to front (u = 0 the back, 1 the front) whichever side its picture had the
    # front on: kit trace turns it (trace.py, design()) — it is never turned again here
    sp = side["outline"]
    tp = top["outline"] if top else None
    lo_h = min(h for _, h in sp)
    tw = [w for _, w in tp] if tp else []
    mid_w = (min(tw) + max(tw)) / 2 if tw else 0.0
    rows = []
    for k in range(stations):
        u = (k + 0.5) / stations
        hv = T.profile(sp, u)
        if not hv:
            continue
        wv = T.profile(tp, u) if tp else None
        ry = (hv[1] - hv[0]) / 2 * L
        rx = (wv[1] - wv[0]) / 2 * L if wv else None
        rows.append({"u": round(u, 4), "ry_mm": round(ry, 2), "rx_mm": None if rx is None else round(rx, 2),
                     "off_mm": [0.0 if not wv else round(((wv[0] + wv[1]) / 2 - mid_w) * L, 2),
                                round(((hv[0] + hv[1]) / 2 - lo_h) * L, 2)],
                     "squareness": 2.0})
    # each traced part's size in mm, in every view that traced it — with kit trace's judgement of its mask (a
    # doubtful mask: one that filled its box, ran into its neighbour, dropped a piece, or a plain box): a spec "ref"
    # to it is named by the ref_sizes_doubtful check
    parts = {}
    for v, t in views.items():
        unit = scale.get(v, {}).get("mm_per_unit")
        quality = t.get("part_quality") or {}
        for name, poly in (t.get("parts") or {}).items():
            if not unit or not poly:
                continue
            u0, h0, u1, h1 = T.bounds(poly)
            row = {"along_mm": [round(u0 * unit, 1), round(u1 * unit, 1)],
                   "across_mm": [round(h0 * unit, 1), round(h1 * unit, 1)],
                   "size_mm": [round((u1 - u0) * unit, 1), round((h1 - h0) * unit, 1)]}
            if name in quality:
                row["quality"] = {"ok": bool(quality[name].get("ok", True)), "prompt": quality[name].get("prompt"),
                                  "why": list(quality[name].get("why") or [])}
            parts.setdefault(name, {})[v] = row
    return {"size_mm": [None if W is None else round(W, 1), round(H, 1), round(L, 1)], "views": scale,
            "checks": checks, "stations": rows, "parts": parts,
            "note": "side view: length x height; top view: length x width; front/back: width x height. stations: "
                    "u = 0 the back, 1 the front; ry from the side view, rx from the top view; squareness is not "
                    "measured yet (2.0 = elliptic)."}


def main(argv):
    if not argv:
        return emit("fail", "refs views: usage: views.py <asset> [--stations N]", "lune run kit refs views <asset>")
    asset = argv[0]
    n = int(argv[argv.index("--stations") + 1]) if "--stations" in argv else 48
    spec_path = os.path.join(ROOT, "refs", f"{asset}.spec.json")
    if not os.path.isfile(spec_path):
        return emit("fail", f"refs views: no refs/{asset}.spec.json (its length_mm anchors every view)",
                    "write the spec first (the parallax-3d skill: research -> spec -> trace -> model)")
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    views = load_views(asset)
    if "side" not in views:
        return emit("fail", f"refs views: no traced side view for {asset}",
                    f"lune run kit trace <side picture> --name {asset}_side --ortho")
    m = measure_views(views, spec["length_mm"], n)
    out = os.path.join(ROOT, "refs", f"{asset}.views.json")
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"asset": asset, **m}, fh, indent=1)
        fh.write("\n")
    W, H, L = m["size_mm"]
    bad = [c for c in m["checks"] if c["grade"] == "bad"]
    warn = [c for c in m["checks"] if c["grade"] == "warn"]
    persp = [v for v, s in m["views"].items() if s.get("perspective_suspect")]
    dims = f"{L:.0f} long x {H:.0f} tall" + (f" x {W:.0f} wide" if W else "") + " mm"
    told = "; ".join(f"{c['what']} {c['mm'][0]:.0f} vs {c['mm'][1]:.0f} mm ({c['off']:+.0%})" for c in bad + warn)
    summary = (f"refs views {asset}: {len(views)} view(s) -> {dims}; {len(m['stations'])} stations, "
               f"{len(m['parts'])} traced part(s)" + (f"; DISAGREE: {told}" if told else "; the views agree"))
    if persp:
        summary += f"; perspective suspected in: {', '.join(persp)}"
    doubtful = sorted(n for n, vs in m["parts"].items()
                      if any(not r.get("quality", {"ok": True})["ok"] for r in vs.values()))
    if doubtful:
        summary += f"; doubtful part mask(s): {', '.join(doubtful)}"
    nxt = ("decide which view is right for each disagreement (an orthographic chart beats a perspective render; a "
           "part posed differently explains a height), fix or retrace the wrong one, run again"
           if bad else f"build from refs/{asset}.views.json: rbx_trace.loft_stations(...) and each part's size in mm")
    if doubtful:
        nxt += (f" · retrace the doubtful part(s) {', '.join(doubtful)} (--part-point / --part-text; their 'why' is "
                "in the views file) before a spec \"ref\" links to them")
    return emit("warn" if bad else "pass", summary, nxt, out=out.replace("\\", "/"), checks=m["checks"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
