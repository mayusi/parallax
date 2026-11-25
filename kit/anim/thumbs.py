"""thumbs.py - SILHOUETTE THUMBNAILS (AAA gaps v2 A1): pros judge key poses as black silhouettes from the game camera
before any polish ("a key pose stays readable when blacked out"; "if it is not clear in 3 frames it won't be in 30").
A move's key poses (its .move.json key times, else every 0.1 s) as solid black R6 silhouettes from the PLAYER's camera
(behind and above) and from the side, one cell per key, with its line of action and silhouette area (pose_appeal.py).

    python kit/anim/thumbs.py <Name> [--move <move.json>] [--out build/animations/<Name>.thumbs.png]
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip as C  # noqa: E402
import pose_appeal as PA  # noqa: E402

VIEWS = {"player": [0.0, -0.35, -1.0], "side": [-1.0, -0.1, 0.0]}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0


MAX_KEYS = 10       # a sheet's rows: more authored keys than this are thinned evenly (the first and last kept)


def key_times(clip, move=None, limit=MAX_KEYS):
    """the moments a move is JUDGED at, in seconds: its authored keys (a strike move's `keys`), else what the clip
    itself marks (the start, every beat's borders, every event, the end), else every 0.1 s. Two moments closer than
    two frames are one pose; more than `limit` are thinned evenly"""
    times = [float(t) for t in clip["times"]]
    end = times[-1]
    step = (times[1] - times[0]) if len(times) > 1 else 1.0 / 60
    ts = [float(k["t"]) for k in (move or {}).get("keys", []) if isinstance(k, dict) and "t" in k]
    if not ts:
        marks = [0.0, end] + [float(e["t"]) for e in clip.get("events") or [] if "t" in e]
        for span in (clip.get("beats") or {}).values():
            if isinstance(span, (list, tuple)) and len(span) == 2:
                marks += [float(span[0]), float(span[1])]
        ts = marks if len(set(round(m, 4) for m in marks)) >= 3 else list(np.arange(0, end + 1e-6, 0.1))
    hits = {round(float(e["t"]), 6) for e in clip.get("events") or []
            if "t" in e and str(e.get("name", "")).lower() in C.HIT_NAMES}
    out = []
    for t in sorted(min(max(t, 0.0), end) for t in ts):
        if not out or t - out[-1] > 2 * step - 1e-9:
            out.append(t)
        elif round(t, 6) in hits and round(out[-1], 6) not in hits:
            out[-1] = t                                   # of two marks a frame apart, the Hit is the pose looked at
    if len(out) > limit:
        out = [out[int(round(k * (len(out) - 1) / (limit - 1)))] for k in range(limit)]
    return out


def blade_line(clip, i):
    """(grip, tip, edge) of the sword at frame i in character space, the root's travel carried - None without a sword"""
    sw = clip.get("sword") or {}
    if not sw.get("tip") or i >= len(sw["tip"]) or not sw.get("grip_path") or i >= len(sw["grip_path"]):
        return None
    t, g = np.asarray(sw["tip"][i], float), np.asarray(sw["grip_path"][i], float)
    edges = sw.get("edge") or []
    e = np.asarray(edges[i] if i < len(edges) else [1, 0, 0], float)
    root = clip.get("root")
    if root and i < len(root):
        R = np.array(C.quat_mat(root[i][:4]))
        o = np.asarray(root[i][4:7], float)
        t, g, e = R @ t + o, R @ g + o, R @ e
    return g, t, e


def blade(clip, i):
    """the sword's 8 corners at frame i (character space, root carried) - None without a sword path
    (round 1, looked at: the thumbnails showed the body alone - for a sword attack the blade is half the silhouette)"""
    line = blade_line(clip, i)
    if line is None:
        return None
    g, t, e = line
    y = (t - g) / max(np.linalg.norm(t - g), 1e-9)
    x = e - y * float(e @ y)
    x = x / max(np.linalg.norm(x), 1e-9) * 0.09
    z = np.cross(x / 0.09, y) * 0.03
    base = g - y * 0.35
    return np.array([p + sx * x + sz * z for p in (base, t) for sx in (-1, 1) for sz in (-1, 1)])


def hulls(W, rig, d, extra=None):
    r, u = PA.camera_basis(d)
    polys = [PA.corners(W, rig, p) for p in PA.MASS] + ([extra] if extra is not None else [])
    return [PA.convex_hull(np.stack([P @ r, P @ u], axis=1)) for P in polys]


def main(argv):
    if not argv:
        return emit("fail", "thumbs: needs <Name>", "lune run kit anim thumbs Katana1Kesa")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    name = argv[0]
    build = os.environ.get("KIT_BUILD", "build")
    clip = json.load(open(os.path.join(build, "animations", f"{name}.clip.json"), encoding="utf-8"))
    mpath = argv[argv.index("--move") + 1] if "--move" in argv else os.path.join("assets", "animations", f"{name}.move.json")
    move = json.load(open(mpath, encoding="utf-8")) if os.path.isfile(mpath) else None
    fps = round(1.0 / (clip["times"][1] - clip["times"][0]))
    ts = [float(k["t"]) for k in (move or {}).get("keys", [])] or list(np.arange(0, clip["times"][-1] + 1e-6, 0.1))
    rig = C.load_rig("r6")
    W = C.world_frames(clip, rig)
    n = len(ts)
    # a cell is `--size` px wide (default 384; it was 209: "exists, small" - the studio route's A0). The poses LARGE,
    # on the owner's rig, beside their reference: lune run kit anim sheet <Name> (kit/anim/pose_sheet.py)
    cell = int(argv[argv.index("--size") + 1]) if "--size" in argv else 384
    fig, axes = plt.subplots(2, n, figsize=(max(4, cell / 110 * n), 2.42 * cell / 110), facecolor="white", squeeze=False)
    rep = PA.report(clip, move)
    for k, t in enumerate(ts):
        i = min(len(W) - 1, int(round(t * fps)))
        for row, (view, d) in enumerate(VIEWS.items()):
            ax = axes[row][k]
            hs = hulls(W[i], rig, d, blade(clip, i))
            for H in hs:
                ax.add_patch(Polygon(H, closed=True, color="black"))
            allp = np.concatenate(hs)
            c, span = allp.mean(0), float(max(allp.max(0) - allp.min(0))) * 0.6 + 0.5
            ax.set_xlim(c[0] - span, c[0] + span)
            ax.set_ylim(c[1] - span, c[1] + span)
            ax.set_aspect("equal")
            ax.axis("off")
            if row == 0:
                r = rep["keys"][k] if k < len(rep["keys"]) else {}
                ax.set_title(f"key {k}  {t:.2f}s\nlean {r.get('line_of_action_deg', 0):.0f}°  area {r.get('silhouette_pct', 0):.0f}%", fontsize=7)
        axes[0][0].text(-0.08, 0.5, "player", transform=axes[0][0].transAxes, rotation=90, va="center", fontsize=7)
        axes[1][0].text(-0.08, 0.5, "side", transform=axes[1][0].transAxes, rotation=90, va="center", fontsize=7)
    fig.suptitle(f"{name} - key poses as silhouettes (does each read in black?)", fontsize=9)
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(build, "animations", f"{name}.thumbs.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return emit("pass", f"thumbs {name}: {n} key poses as silhouettes -> {out.replace(os.sep, '/')}",
                "LOOK: every silhouette should read as its action (arms and blade clear of the body); send the owner the sheet before polishing",
                picture=out.replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
