"""fold_loss.py — WHAT A RIG CHANGE LOSES, AS NUMBERS (the owner's older list, AN-19 and AN-21: "report before /
after residuals and reject conversions that exceed the action's contact / reach tolerance", "compare source and
folded action at contact and silhouette-critical frames; record the unavoidable loss").

A move made on the R15 (an import, a mocap, a generated motion) is FOLDED onto the R6 (kit/lib/anim.luau
Anim.foldToR6): fifteen parts become six, an arm with an elbow becomes one block. The fold AIMS each R6 limb at the
source's hand or foot (the shortest turn from the limb's rest line to its line now), then corrects the feet for
the floor. It said what it could not map (its issue list) and nothing about how far the result is from the source.

    python kit/anim/fold_loss.py <Name>.clip.json <Name>.r6.clip.json      one move: source against fold
    python kit/anim/fold_loss.py table <folder of built clips>             every pair in a folder, worst first

PER LIMB (two hands, two feet), frame by frame: an arm in its torso's axes, a leg in the character's space. A limb's REACH is from its joint
(shoulder, hip) to its end (the hand's centre; the sole; the R6 block's far end). Each rig's reach is taken as its
MOVE FROM REST, the source's scaled by the two rigs' limb lengths:
  residual      how far the R6's end is from where it would be, had it moved as the source's did (studs)
  unavoidable   the part no R6 pose could close: that place is nearer the joint (a bent elbow or knee) or further
                than a rigid block's end can be
  avoidable     the rest: the limb points the wrong way
THE PELVIS: how high the body rides above its standing height, source (scaled by the legs' lengths) against fold.
WHERE IT MATTERS: the Hit (the hand or foot of the SOURCE that moves fastest there) and, in a move that is no loop,
the frames a source foot stands (its sole within STAND of its lowest and slower than SLOW).

THE BAR (a conversion is refused over it; `problems` in the report): the striking limb at the Hit, avoidable over
REACH studs; a number that is not finite anywhere. A standing foot's miss is REPORTED (`stands`, `over` = frames
past PLANT studs), not failed: the R6 clip's own feet gates hold its feet.
What it cannot keep is RECORDED, not failed: `unavoidable` per limb at the Hit and over the move.
THE GATE (kit/anim/metrics.py, on every <Name>.r6.clip.json whose R15 source <Name>.clip.json lies beside it): the
reading goes into the metrics as `fold`; a fold over the bar FAILS the build.
NOT DONE: the weapon's path through a fold (no R15 source in the kit carries a sword: it is given to the R6 clip,
and kit/anim/in_hand.py holds it there); the pelvis is read, not gated; fingers, a spine's bend; a loop's standing
feet (a loop plays in place: its feet never stand still in the character's space).
A REPAIR WAS BUILT AND TAKEN OUT (the one review, 2026-11-15): the first cut measured against a line of its own,
found losses that were not there (the fold already aims each arm at the source's wrist), and its repair moved
hands up to 0.94 studs AWAY from the source.
THE STRIKER is the source's fastest hand or foot at the Hit: on a two-handed move it can be the off hand."""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

REACH = 0.6          # studs: the striking limb's avoidable residual at the Hit
PLANT = 0.6          # studs: a standing foot's avoidable residual
PLANT_SHARE = 0.25   # ... over this share of the frames it stands
STAND, SLOW = 0.15, 2.0   # a source foot stands: its sole within STAND studs of its lowest and under SLOW studs a second
LIMBS = {
    "RightHand": (("RightUpperArm", "RightHand", None), ("Right Arm", (0.0, -1.0, 0.0))),
    "LeftHand": (("LeftUpperArm", "LeftHand", None), ("Left Arm", (0.0, -1.0, 0.0))),
    "RightFoot": (("RightUpperLeg", "RightFoot", "sole"), ("Right Leg", (0.0, -1.0, 0.0))),
    "LeftFoot": (("LeftUpperLeg", "LeftFoot", "sole"), ("Left Leg", (0.0, -1.0, 0.0))),
}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _pt(M, p):
    M = np.asarray(M, float)
    return M[:3, :3] @ np.asarray(p, float) + M[:3, 3]


def _reach15(rig, Wf, limb):
    """the source limb's reach: from its joint (shoulder, hip) to its end (the hand's centre, the sole). An ARM's in
    the axes of the UpperTorso it hangs from (a body that leans or rolls is the same body); a LEG's in the
    character's space (the fold puts a foot where the source's is over the FLOOR, whatever the waist does)"""
    (upper, end, sole), _ = LIMBS[limb]
    a = _pt(Wf[upper], rig["joints"][upper]["c1"][:3])
    b = _pt(Wf[end], (0.0, -rig["sizes"][end][1] / 2, 0.0) if sole else (0.0, 0.0, 0.0))
    if sole:
        return b - a                                         # (a leg: where the foot is under the hip, in the character's space)
    par = np.asarray(Wf[rig["joints"][upper]["parent"]], float)[:3, :3]
    return par.T @ (b - a)


def _reach6(rig, Wf, limb):
    """the R6 limb's reach: an ARM's in the Torso's axes, from its joint to the centre of the block's far end; a
    LEG's in the character's space, from its hip to the point of the block's far end straight under the hip (the
    R6's hip sits at the block's corner: measured to the far end's centre, a body lying on its side read a stud off)"""
    _, (part, tip) = LIMBS[limb]
    c1 = rig["joints"][part]["c1"][:3]
    if limb.endswith("Foot"):
        return _pt(Wf[part], (c1[0], -rig["sizes"][part][1] / 2, c1[2])) - _pt(Wf[part], c1)
    par = np.asarray(Wf[rig["joints"][part]["parent"]], float)[:3, :3]
    return par.T @ (_pt(Wf[part], tip) - _pt(Wf[part], c1))


def lengths(rig15, rig6):
    """each limb's reach on the two rigs at rest -> {limb: (R15, R6)}"""
    import clip as C
    r15, r6 = C.fk(rig15), C.fk(rig6)
    return {limb: (float(np.linalg.norm(_reach15(rig15, r15, limb))), float(np.linalg.norm(_reach6(rig6, r6, limb))))
            for limb in LIMBS}


def read(src, fold):
    """-> the report (see the module's words). ValueError on a pair that cannot be compared"""
    import clip as C
    if not isinstance(src, dict) or not isinstance(fold, dict):
        raise ValueError("a clip is a JSON object")
    if src.get("rig") != "R15" or fold.get("rig") != "R6":
        raise ValueError(f"it compares an R15 source with its R6 fold (these are {src.get('rig')} and {fold.get('rig')})")
    n = len(src.get("times") or [])
    if n < 2 or n != len(fold.get("times") or []):
        raise ValueError(f"the source has {n} frames and the fold {len(fold.get('times') or [])}: a fold keeps the frames")
    rig15, rig6 = C.load_rig("r15"), C.load_rig("r6")
    # (the body's own space: the root's travel is the same track on both, and is left out of both)
    a, b = dict(src), dict(fold)
    a.pop("root", None)
    b.pop("root", None)
    W15, W6 = C.world_frames(a, rig15), C.world_frames(b, rig6)
    fps = C.clip_fps(src)
    L = lengths(rig15, rig6)
    rest15, rest6 = C.fk(rig15), C.fk(rig6)
    limbs, ends15 = {}, {}
    for limb in LIMBS:
        k = L[limb][1] / L[limb][0]
        r15, r6 = _reach15(rig15, rest15, limb), _reach6(rig6, rest6, limb)
        res, unav, avoid = np.zeros(n), np.zeros(n), np.zeros(n)
        e15 = np.zeros((n, 3))
        for i in range(n):
            v15, v6 = _reach15(rig15, W15[i], limb), _reach6(rig6, W6[i], limb)
            want = r6 + (v15 - r15) * k                      # where the R6's end would be, had it moved as the source's
            res[i] = float(np.linalg.norm(v6 - want))
            unav[i] = abs(float(np.linalg.norm(want)) - L[limb][1])
            avoid[i] = max(res[i] - unav[i], 0.0)
            (_, end, _), _ = LIMBS[limb]
            e15[i] = np.asarray(W15[i][end], float)[:3, 3]
        ends15[limb] = e15
        limbs[limb] = {"residual": res, "unavoidable": unav, "avoidable": avoid}
    hip = L["RightFoot"][1] / L["RightFoot"][0]              # (the body rides on its legs: their lengths' ratio)
    pelvis = np.array([abs((W6[i]["Torso"][1, 3] - rest6["Torso"][1, 3])
                           - (W15[i]["LowerTorso"][1, 3] - rest15["LowerTorso"][1, 3]) * hip) for i in range(n)])
    hits = []
    for e in src.get("events") or []:
        if isinstance(e, dict) and e.get("name") == "Hit" and isinstance(e.get("t"), (int, float)) and np.isfinite(e["t"]):
            hits.append(min(n - 1, max(0, int(round(float(e["t"]) * fps)))))
    out = {"frames": n, "fps": fps, "limbs": {}, "pelvis": {"mean": round(float(pelvis.mean()), 3), "max": round(float(pelvis.max()), 3)},
           "lengths": {k: [round(v[0], 3), round(v[1], 3)] for k, v in L.items()}, "hits": [], "stands": {}, "problems": []}
    for limb, d in limbs.items():
        out["limbs"][limb] = {k: {"mean": round(float(v.mean()), 3), "max": round(float(v.max()), 3)} for k, v in d.items()}
        if not all(np.isfinite(v).all() for v in d.values()):
            out["problems"].append(f"the {WORD[limb]} cannot be read: a number in the source or the fold is not finite")
    for h in hits:
        lo, hi = max(0, h - 2), min(n - 1, h + 2)
        speed = {limb: float(np.linalg.norm(ends15[limb][hi] - ends15[limb][lo])) for limb in LIMBS}
        striker = max(speed, key=speed.get)
        d = limbs[striker]
        row = {"frame": h, "striker": striker, "residual": round(float(d["residual"][h]), 3),
               "unavoidable": round(float(d["unavoidable"][h]), 3), "avoidable": round(float(d["avoidable"][h]), 3)}
        out["hits"].append(row)
        if row["avoidable"] > REACH:
            out["problems"].append(
                f"the fold loses the strike: at the Hit (frame {h}, {h / fps:.2f} s) the R6's {WORD[striker]} is "
                f"{row['residual']:.2f} studs from where the source's is, {row['avoidable']:.2f} of it by pointing the wrong "
                f"way (the bar: {REACH:g}; {row['unavoidable']:.2f} is the bent limb no R6 can make) - the R6 clip was "
                "changed after the fold, or the fold is broken: fold it again from its source")
    if not src.get("loop"):
        for limb in ("RightFoot", "LeftFoot"):
            e = ends15[limb]
            v = np.zeros(n)
            v[1:-1] = np.linalg.norm(e[2:] - e[:-2], axis=1) * fps / 2      # (each frame by the two round it)
            v[0], v[-1] = v[1], v[-2]
            stands = (e[:, 1] <= e[:, 1].min() + STAND) & (v < SLOW)
            k = int(stands.sum())
            if k == 0:
                continue
            av = limbs[limb]["avoidable"][stands]
            over = int((av > PLANT).sum())
            out["stands"][limb] = {"frames": k, "avoidable_mean": round(float(av.mean()), 3),
                                   "avoidable_max": round(float(av.max()), 3), "over": over}
    return out


def gate(clip, path):
    """what the build's motion gates add for a folded clip (kit/anim/metrics.py) -> (the reading or None, the problem
    or None). Only <Name>.r6.clip.json with its R15 source <Name>.clip.json beside it is read; a source that cannot
    be read, or frames that no longer match (the fold was retimed since), is said in the reading and fails nothing"""
    if not isinstance(clip, dict) or not isinstance(path, str) or not path.endswith(".r6.clip.json") or clip.get("rig") != "R6":
        return None, None
    src_path = path[:-len(".r6.clip.json")] + ".clip.json"
    if not os.path.isfile(src_path):
        return None, None
    try:
        with open(src_path, encoding="utf-8") as fh:
            src = json.load(fh)
        if not isinstance(src, dict) or src.get("rig") != "R15":
            return None, None
        r = read(src, clip)
    except Exception as e:                                   # noqa: BLE001 (a reading never breaks a build)
        return {"error": f"{type(e).__name__}: {e}"}, None
    out = {"limbs": r["limbs"], "hits": r["hits"], "stands": r["stands"], "pelvis": r["pelvis"],
           "bars": {"reach": REACH, "plant": PLANT, "plant_share": PLANT_SHARE}}
    if not r["problems"]:
        return out, None
    out["problems"] = r["problems"]
    return out, r["problems"][0]


WORD = {"RightHand": "right hand", "LeftHand": "left hand", "RightFoot": "right foot", "LeftFoot": "left foot"}


def words(r):
    worst = max(r["limbs"], key=lambda k: r["limbs"][k]["avoidable"]["max"])
    w = r["limbs"][worst]
    hit = (f"; at the Hit the {WORD[r['hits'][0]['striker']]} is {r['hits'][0]['residual']:.2f} studs off, "
           f"{r['hits'][0]['unavoidable']:.2f} of it unavoidable") if r["hits"] else "; no Hit"
    return (f"the fold's {WORD[worst]} is the furthest from its source: {w['residual']['max']:.2f} studs at its worst, "
            f"{w['avoidable']['max']:.2f} by pointing the wrong way{hit}; the body rides {r['pelvis']['max']:.2f} studs off at its worst")


def pairs(folder):
    for p in sorted(glob.glob(os.path.join(folder, "*.r6.clip.json"))):
        s = p[:-len(".r6.clip.json")] + ".clip.json"
        if os.path.isfile(s):
            yield s, p


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    try:
        if argv[0] == "table":
            rows = []
            for s, p in pairs(argv[1]):
                with open(s, encoding="utf-8") as fh:
                    a = json.load(fh)
                with open(p, encoding="utf-8") as fh:
                    b = json.load(fh)
                try:
                    r = read(a, b)
                except ValueError:
                    continue
                rows.append({"name": a.get("name"), "problems": len(r["problems"]),
                             "avoidable_max": max(v["avoidable"]["max"] for v in r["limbs"].values()),
                             "unavoidable_mean": round(float(np.mean([v["unavoidable"]["mean"] for v in r["limbs"].values()])), 3),
                             "hit": r["hits"][0] if r["hits"] else None, "pelvis_max": r["pelvis"]["max"]})
            rows.sort(key=lambda x: -x["avoidable_max"])
            bad = [x["name"] for x in rows if x["problems"]]
            return emit("pass", f"anim fold: {len(rows)} folded move(s) read against their source; over the bar: "
                        + (", ".join(bad) if bad else "none"), "python kit/anim/fold_loss.py <src> <fold> for one", rows=rows)
        with open(argv[0], encoding="utf-8") as fh:
            a = json.load(fh)
        with open(argv[1], encoding="utf-8") as fh:
            b = json.load(fh)
        r = read(a, b)
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, OverflowError) as e:
        return emit("fail", f"anim fold: it could not be read ({type(e).__name__}: {e})",
                    "python kit/anim/fold_loss.py <Name>.clip.json <Name>.r6.clip.json")
    if r["problems"]:
        return emit("fail", f"anim fold {a.get('name')}: {r['problems'][0]}"
                    + (f" (+{len(r['problems']) - 1} more)" if len(r["problems"]) > 1 else ""), r["problems"][0], **r)
    return emit("pass", f"anim fold {a.get('name')}: {words(r)}", "none - what a fold cannot keep is recorded, not failed", **r)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
