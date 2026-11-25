"""silhouette.py — an R6 clip as flat SILHOUETTES and ARCS, side by side with a reference: the poses, without textures.

    python kit/anim/silhouette.py <clip.json> [--vs <reference clip.json>] [--frames 8] [--out <png>]

Why: the craft judges a pose by its silhouette first ("readability"), and a cycle by the paths its hands and feet trace
("arcs, never straight lines"). A textured render hides both behind labels and shading. This draws the clip's real part
boxes (the rig's sizes, every frame through kit/anim/clip.py) orthographically:
- row 1, SIDE (from the character's right; forward is to the right): the right limbs warm, the left limbs cool, the
  far side darker; the floor line at the clip's lowest point; the frame number and its share of the cycle
- row 2, FRONT: the same frames from the front (forward is toward you)
- the last column, ARCS: every frame's hand and foot tips, side view, as dotted paths (a straight or kinked path is a
  spacing / arc fault; a figure 8 is a healthy overlap)
- the last row, CURVES: each limb's speed over the cycle (degrees-equivalent per 60th of a second, kit/anim/snaps.py),
  the clip solid, the reference dashed, every SNAP circled - a spike is a jolt the eye catches even when the poses
  are right
With --vs, the reference gets the same rows underneath, at the same scale and the same cycle shares, so pose N of
both is the same moment. No Blender: seconds, and nothing under build/ is touched unless --out says so."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import snaps as SN  # noqa: E402

PARTS = ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")
COLOR = {"Torso": "#7a7a7a", "Head": "#a0a0a0", "Right Arm": "#e8743b", "Right Leg": "#c0392b",
         "Left Arm": "#4aa3df", "Left Leg": "#2a5f9e"}
TIPS = {"Right Arm": "#e8743b", "Left Arm": "#4aa3df", "Right Leg": "#c0392b", "Left Leg": "#2a5f9e"}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def hull(pts):
    """the 2D convex hull (monotone chain) of a box's projected corners"""
    pts = sorted(map(tuple, np.round(pts, 6)))
    if len(pts) < 3:
        return np.array(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    return np.array(lo[:-1] + hi[:-1])


# a view: (screen x of a world point, screen y, depth toward the camera)
VIEWS = {"side": lambda p: (-p[:, 2], p[:, 1], p[:, 0]),      # from the right: forward (-z) to the right
         "front": lambda p: (-p[:, 0], p[:, 1], -p[:, 2])}    # from the front: the character's right on the left


def load(path):
    with open(path, encoding="utf-8") as fh:
        clip = json.load(fh)
    rig = C.load_rig("r6")
    loop = bool(clip.get("loop"))
    frames = C.world_frames(clip, rig)
    n = len(frames) - (1 if loop and len(frames) > 2 else 0)
    return clip, rig, frames[:n], loop


def pick(n, count, loop):
    """`count` frames at even shares of the cycle (a loop never repeats its seam frame)"""
    if loop:
        return [int(round(i * n / count)) % n for i in range(count)]
    return [int(round(i * (n - 1) / max(count - 1, 1))) for i in range(count)]


def tip(rig, part, m):
    """a limb's far end (the hand / sole centre)"""
    h = rig["sizes"][part][1] / 2.0
    return (m @ np.array([0, -h, 0, 1.0]))[:3]


def draw_pose(ax, rig, f, view, floor):
    proj = VIEWS[view]
    items = []
    for part in PARTS:
        if part not in f:
            continue
        X, Y, Z = proj(C.corners(rig, part, f[part]))
        items.append((float(Z.mean()), part, np.stack([X, Y], 1)))
    near = max(z for z, _, _ in items)
    for z, part, pts in sorted(items):
        far = z < near - 0.6 and part not in ("Torso", "Head")
        ax.fill(*hull(pts).T, color=COLOR[part], alpha=0.55 if far else 0.95, ec="black", lw=0.6, zorder=2)
    ax.axhline(floor, color="black", lw=0.8, zorder=1)


def sheet(rows, count, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    nrows = sum(2 for _ in rows)
    fig = plt.figure(figsize=(1.35 * (count + 1), 1.75 * nrows + 1.6))
    gs = fig.add_gridspec(nrows + 1, count + 1, height_ratios=[1.0] * nrows + [0.95])
    axes = [[fig.add_subplot(gs[r, c]) for c in range(count + 1)] for r in range(nrows)]
    r = 0
    for name, (clip, rig, frames, loop) in rows:
        idx = pick(len(frames), count, loop)
        floor = min(min(C.lowest(rig, p, f[p]) for p in ("Right Leg", "Left Leg") if p in f) for f in frames)
        for view in ("side", "front"):
            for c, i in enumerate(idx):
                ax = axes[r][c]
                draw_pose(ax, rig, frames[i], view, floor)
                ax.set_title(f"{i} ({i / len(frames):.2f})" if loop else f"{i}", fontsize=6, pad=1)
            # the arcs: every frame's hand and foot tips (side view only; the front row shows the lateral paths)
            ax = axes[r][count]
            proj = VIEWS[view]
            for part, col in TIPS.items():
                if part not in frames[0]:
                    continue
                P = np.array([tip(rig, part, f[part]) for f in frames])
                X, Y, _ = proj(P)
                if loop:
                    X, Y = np.append(X, X[0]), np.append(Y, Y[0])
                ax.plot(X, Y, ".-", color=col, ms=2, lw=0.7)
            ax.axhline(floor, color="black", lw=0.8)
            ax.set_title("arcs", fontsize=6, pad=1)
            axes[r][0].set_ylabel(f"{name}\n{view}", fontsize=7)
            r += 1
    limbs = ("Right Leg", "Left Leg", "Right Arm", "Left Arm")
    span = max(1, (count + 1) // 4)
    for li, part in enumerate(limbs):
        ax = fig.add_subplot(gs[nrows, li * span:(li + 1) * span if li < 3 else count + 1])
        for ri, (name, (clip, rig, frames, loop)) in enumerate(rows):
            if part not in clip["joints"]:
                continue
            sp = SN.speeds(clip["joints"][part]["frames"], float(clip.get("fps") or 30), loop)
            x = np.linspace(0, 1, len(sp), endpoint=False)
            ax.plot(x, sp, "-" if ri == 0 else "--", color=COLOR[part] if ri == 0 else "#555555", lw=1.0)
            for i, v, _m in SN.find(clip).get(part, []):
                ax.plot([x[i]], [v], "o", mfc="none", mec="red", ms=7)
        ax.set_title(f"{part} speed", fontsize=6, pad=1)
        ax.tick_params(labelsize=5)
    for row in axes:
        for ax in row:
            ax.set_aspect("equal")
            ax.set_xlim(-4.2, 4.2)
            ax.set_ylim(-3.8, 3.2)
            ax.set_xticks([])
            ax.set_yticks([])
    fig.subplots_adjust(left=0.04, right=0.995, top=0.96, bottom=0.01, wspace=0.03, hspace=0.18)
    fig.savefig(out, dpi=110)
    plt.close(fig)


def main(argv):
    if not argv:
        return emit("fail", "silhouette: needs <clip.json> [--vs <ref clip.json>]", "lune run kit anim sil <Name> --vs <Ref>")
    count = int(argv[argv.index("--frames") + 1]) if "--frames" in argv else 8
    rows = []
    for path in [argv[0]] + ([argv[argv.index("--vs") + 1]] if "--vs" in argv else []):
        clip, rig, frames, loop = load(path)
        if clip.get("rig") not in (None, "R6"):
            return emit("fail", f"silhouette: {path} is not an R6 clip", "fold it to R6 first")
        rows.append((clip.get("name") or os.path.basename(path), (clip, rig, frames, loop)))
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.splitext(argv[0])[0].replace(".clip", "") + ".sil.png"
    sheet(rows, count, out)
    return emit("pass", f"silhouette {rows[0][0]}: {count} poses at even cycle shares, side + front + arcs"
                + (f", vs {rows[1][0]} underneath" if len(rows) > 1 else "") + f" -> {out}",
                f"LOOK at {out}: does each side pose read as a run at a glance (legs under the body, arms pumping, a clear lean)? do the arcs loop smoothly?",
                out=out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
