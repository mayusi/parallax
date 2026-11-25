"""diff.py - VERSION DIFF DAILIES (AAA gaps v2 A5; board/plans/archive/2026-10-22-anim-aaa-gaps-v2.md): pros review each round
against the LAST one ("what changed since yesterday"), not only against the reference. Two clips (two versions of a
move, or a move and its reference) -> per R6 part the largest and mean turn between them (at the same time), when
each part differs most, the Hit's shift, and one picture: both versions' blade-tip (or right-hand) ARCS from the side
and from above, with spacing ticks, A in grey and B in colour.

    python kit/anim/diff.py <A> <B> [--out build/animations/<A>__vs__<B>.diff.png]
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip as C  # noqa: E402

PARTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status != "fail" else 1


def load(name, build):
    for p in (os.path.join(build, "animations", f"{name}.clip.json"), os.path.join(build, "animations", f"{name}.r6.clip.json")):
        if os.path.isfile(p):
            return json.load(open(p, encoding="utf-8"))
    raise FileNotFoundError(f"no built clip {name} (lune run kit anim {name})")


def at(clip, part, t):
    """the part's character-space rotation at time t (nearest frame)"""
    times = clip["times"]
    i = min(len(times) - 1, max(0, int(round(t / max(times[1] - times[0], 1e-6)))))
    f = clip["joints"].get(part, {}).get("frames")
    if not f:
        return np.eye(3)
    q = np.asarray(f[min(i, len(f) - 1)][:4], float)
    return np.array(C.quat_mat(q / np.linalg.norm(q)))   # stored rounded to 1e-6: unnormalised, R^T R read 0.2 deg off


def path(clip, rig):
    """the blade tip per frame (character space, root carried) - else the right hand"""
    sw = clip.get("sword") or {}
    W = C.world_frames(clip, rig)
    if sw.get("tip") and len(sw["tip"]) == len(W):
        root = clip.get("root")
        out = []
        for i, p in enumerate(sw["tip"]):
            if root and len(root) == len(W):
                R = np.array(C.quat_mat(root[i][:4]))
                out.append(R @ np.asarray(p, float) + np.asarray(root[i][4:7], float))
            else:
                out.append(np.asarray(p, float))
        return np.array(out), "blade tip"
    return np.array([(w["Right Arm"] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3] for w in W]), "right hand"


def hit_of(clip):
    return next((float(e["t"]) for e in clip.get("events") or [] if e.get("name") == "Hit"), None)


def compare(a, b):
    T = min(a["times"][-1], b["times"][-1])
    ts = np.linspace(0, T, max(2, int(T * 60) + 1))
    rows = {}
    for part in PARTS:
        d = [math.degrees(math.acos(np.clip((np.trace(at(a, part, t).T @ at(b, part, t)) - 1) / 2, -1, 1))) for t in ts]
        k = int(np.argmax(d))
        rows[part] = {"max_deg": round(float(d[k]), 1), "mean_deg": round(float(np.mean(d)), 1), "at_s": round(float(ts[k]), 3)}
    ha, hb = hit_of(a), hit_of(b)
    return rows, (round(hb - ha, 3) if ha is not None and hb is not None else None), round(float(T), 3)


def picture(a, b, out, names):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rig = C.load_rig("r6")
    pa, la = path(a, rig)
    pb, lb = path(b, rig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2), facecolor="#14151b")
    for ax, (i, j, title) in zip(axes, ((2, 1, "side (forward = left)"), (0, 2, "above (forward = down)"))):
        ax.set_facecolor("#14151b")
        for P, col, lab in ((pa, "#8a8f9c", f"{names[0]} ({la})"), (pb, "#4fb3ff", f"{names[1]} ({lb})")):
            ax.plot(P[:, i], P[:, j], color=col, lw=1.6, label=lab)
            ax.scatter(P[::2, i], P[::2, j], s=6, color=col)             # spacing ticks (every 2nd frame)
        ax.set_title(title, color="#dfe3ea")
        ax.set_aspect("equal")
        ax.tick_params(colors="#9aa0ad")
        for s in ax.spines.values():
            s.set_color("#333744")
    axes[0].legend(facecolor="#1d1f27", labelcolor="#dfe3ea", fontsize=8)
    fig.suptitle(f"{names[0]} vs {names[1]} - arcs + spacing (dots every 2 frames: wide gaps = fast)", color="#dfe3ea")
    fig.tight_layout()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fig.savefig(out, dpi=110)
    plt.close(fig)


def main(argv):
    if len(argv) < 2:
        return emit("fail", "diff: needs <A> <B>", "lune run kit anim diff Katana4Kiriage Katana4KiriageEdit")
    na, nb = argv[0], argv[1]
    build = os.environ.get("KIT_BUILD", "build")
    try:
        a, b = load(na, build), load(nb, build)
    except FileNotFoundError as exc:
        return emit("fail", f"diff: {exc}", "build both clips first")
    rows, hit_shift, T = compare(a, b)
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(build, "animations", f"{na}__vs__{nb}.diff.png")
    picture(a, b, out, (na, nb))
    top = max(rows.items(), key=lambda kv: kv[1]["max_deg"])
    summ = (f"diff {na} -> {nb}: biggest change {top[0]} {top[1]['max_deg']} deg at {top[1]['at_s']} s"
            + (f", the Hit {'+' if hit_shift >= 0 else ''}{hit_shift} s" if hit_shift is not None else "")
            + f" -> {out.replace(os.sep, '/')}")
    return emit("pass", summ, "LOOK at the arcs picture beside both looks; send the owner the round WITH this diff", parts=rows,
                hit_shift_s=hit_shift, compared_s=T, picture=out.replace(os.sep, "/"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
