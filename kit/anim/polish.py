"""polish.py - LAYERED POLISH, root outward (AAA gaps v2 A4; pros polish root -> hips -> spine -> arms -> head: "check the
COG / root arcs are clean before polishing the spine"; a fix on the arms is wasted while the root under them jerks).
Per layer of an R6 clip, in that order, how SMOOTH its motion is:
  root   the character's travel (the root track) + the torso's height       (a path)
  torso  the torso's turn                                                    (a rotation)
  hands  both hands' paths in the world                                     (paths)
  head   the head's turn relative to the torso                              (a rotation)
  blade  the blade tip's path                                                (a path, a sword clip)
measured as JERK (the third derivative, normalised by the layer's own speed so a fast move is not punished for being
fast) and SPIKES (frames whose jerk passes the loved clips' envelope: a pop / a snap). The first layer over its limit is the
one to polish next - stepped (limited-animation) windows and the Hit frames are intended snaps and are skipped.

    python kit/anim/polish.py <Name>
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip as C  # noqa: E402

# a frame SPIKES when its normalised jerk passes the LOVED envelope + 10 % (measured 2026-10-22 on the owner's 9/10
# Katana4Kiriage, GreatswordSideCut, GsComboChain, his 7/10 KatanaChain and the loved store pack's HqHit1 / BrHit1 /
# BrHit2: max torso 4.83, hands 4.74, head 5.24, blade 4.25, root 23.8 - the greatsword's lunge). A ratio to the
# layer's median (round 1) flagged every loved clip: a held pose's median is ~0
LIMITS = {"root": 26.2, "torso": 5.3, "hands": 5.2, "head": 5.8, "blade": 4.7}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status != "fail" else 1


def rotvec_series(Rs):
    """a rotation series -> per-frame angular velocity vectors (radians / frame)"""
    out = [np.zeros(3)]
    for a, b in zip(Rs, Rs[1:]):
        D = b @ a.T
        ang = np.arccos(np.clip((np.trace(D) - 1) / 2, -1, 1))
        if ang < 1e-9:
            out.append(np.zeros(3))
            continue
        ax = np.array([D[2, 1] - D[1, 2], D[0, 2] - D[2, 0], D[1, 0] - D[0, 1]]) / (2 * np.sin(ang))
        out.append(ax * ang)
    return np.array(out)


def jerk_of_velocity(V, fps):
    """V: per-frame velocity (units / frame) -> per-frame jerk magnitude, normalised by the mean speed"""
    V = np.asarray(V, float) * fps
    if len(V) < 4:
        return np.zeros(len(V)), 0.0
    J = np.diff(V, n=2, axis=0) * fps * fps
    mag = np.r_[0, np.linalg.norm(J, axis=1), 0]
    speed = float(np.mean(np.linalg.norm(V, axis=1))) + 1e-6
    return mag / (speed * fps * fps), speed


def layers(clip):
    rig = C.load_rig("r6")
    W = C.world_frames(clip, rig)
    out = {}
    out["root"] = np.diff(np.array([w["Torso"][:3, 3] for w in W]), axis=0, prepend=[W[0]["Torso"][:3, 3]])
    out["torso"] = rotvec_series([w["Torso"][:3, :3] for w in W])
    hands = np.array([np.r_[(w["Right Arm"] @ [0, -1, 0, 1])[:3], (w["Left Arm"] @ [0, -1, 0, 1])[:3]] for w in W])
    out["hands"] = np.diff(hands, axis=0, prepend=hands[:1])
    out["head"] = rotvec_series([w["Torso"][:3, :3].T @ w["Head"][:3, :3] for w in W])
    sw = clip.get("sword") or {}
    if sw.get("tip") and len(sw["tip"]) == len(W):
        T = np.asarray(sw["tip"], float)
        out["blade"] = np.diff(T, axis=0, prepend=T[:1])
    return out


def report(clip):
    fps = round(1.0 / (clip["times"][1] - clip["times"][0]))
    n = len(clip["times"])
    skip = np.zeros(n, bool)
    for t0, t1, *_ in clip.get("stepped") or []:
        skip[int(t0 * fps):int(t1 * fps) + 2] = True
    for e in clip.get("events") or []:
        if e.get("name") in ("Hit", "Vanish", "Appear"):
            i = int(round(float(e["t"]) * fps))
            skip[max(0, i - 2):i + 3] = True
    rows = []
    for name, V in layers(clip).items():
        j, speed = jerk_of_velocity(V, fps)
        j = j[:n]
        live = j[~skip[:len(j)]]
        if speed < 1e-3 or len(live) == 0:
            rows.append({"layer": name, "still": True})
            continue
        lim = LIMITS[name]
        spikes = [int(i) for i in np.where((j > lim) & ~skip[:len(j)])[0]]
        rows.append({"layer": name, "jerk_max": round(float(live.max()), 2), "limit": lim,
                     "spikes": len(spikes), "spike_frames": spikes[:8]})
    first = next((r for r in rows if not r.get("still") and r["spikes"] > 0), None)
    return rows, first


def main(argv):
    if not argv:
        return emit("fail", "polish: needs <Name>", "lune run kit anim polish Katana1Kesa")
    name = argv[0]
    build = os.environ.get("KIT_BUILD", "build")
    clip = json.load(open(os.path.join(build, "animations", f"{name}.clip.json"), encoding="utf-8"))
    rows, first = report(clip)
    order = " -> ".join(f"{r['layer']} {'still' if r.get('still') else str(r['spikes']) + ' spike(s)'}" for r in rows)
    if first:
        return emit("warn", f"polish {name}: polish {first['layer'].upper()} next ({first['spikes']} spike frames: {first['spike_frames']}) - {order}",
                    f"smooth the {first['layer']} first (root outward), then re-run: lune run kit anim polish {name}", layers=rows)
    return emit("pass", f"polish {name}: every layer smooth root outward - {order}", "none - proceed", layers=rows)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
