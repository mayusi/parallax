"""pose_appeal.py - the POSE APPEAL checks pros run by eye, in numbers (AAA gaps v2 B3 / B4 / B5;
board/plans/archive/2026-10-22-anim-aaa-gaps-v2.md). The owner's recurring complaint is "the poses are not appealing"
(vault: anim-correct-not-nice) - mechanics right, poses stiff. Per KEY POSE of a strike (its move's key times):
  line of action  the lean of the head -> support-foot line from vertical (a pose with no lean reads stiff / upright)
  twinning        arms (or legs) mirroring each other (symmetry reads as a 3D model, not a pose - "solid drawing")
  silhouette      the R6's projected area from the PLAYER's camera (behind and above), in % of the frame
  camera cheat    (B5) the upper-body yaw within +-max deg that opens the silhouette most - written as key_edits
                  (kit/anim/strike.py apply_key_edits), so the blade stays solved with the arms
and on every frame
  balance         (B4) the centre of mass outside the grounded feet's support, on near-still frames (a held pose off
                  balance reads wrong; a fast move may pass through it)

    python kit/anim/pose_appeal.py <Name> [--move assets/animations/<Name>.move.json] [--cheat [--max 10]]
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clip as C  # noqa: E402

GROUND = -3.0                       # the clip frame has the HumanoidRootPart at the origin; R6 feet 3 studs below
MASS = {"Torso": 4.0, "Head": 2.0, "Right Arm": 2.0, "Left Arm": 2.0, "Right Leg": 2.0, "Left Leg": 2.0}
UPPER = ("Torso", "Head", "Right Arm", "Left Arm")
CAMERA = {"dir": [0.0, -0.35, -1.0]}   # the player's view: from behind (+Z) and above, looking the way the R6 faces (-Z)
GAME_CAM = (2.2, 0.9, 9.0)              # Sample Game's Config.ThirdPerson.Offset from the eye (look_r6 --tp)
# OFF-MODEL (AAA gaps v2 E5): a key pose's distance from the LEARNED SPACE of loved R6 poses (kit/anim/pose_space.py,
# mean degrees per joint). Measured 2026-10-22: the loved bank's 1190 key poses p50 2.3 / p99 11.1 / max 19.5; the
# owner's loved katana set max 13.6, his 9/10 GreatswordSideCut 23.85 -> warn past that + 10 %
OFF_MODEL_DEG = 26.2
_BANK_D = None


def space_of(clip, i):
    """(distance from the loved pose space, its percentile among the loved bank's key poses) or (None, None) when the
    space is not built here (python kit/anim/pose_space.py build)"""
    global _BANK_D
    try:
        import pose_space as PS
        PS.load()
    except (ImportError, OSError):
        return None, None
    d = PS.distance({j: clip["joints"][j]["frames"][i] for j in clip["joints"] if j in PS.JOINTS})
    if _BANK_D is None:
        try:
            bank = json.load(open(os.path.join(PS.LIB, "pose_bank.json"), encoding="utf-8"))["poses"]
            _BANK_D = np.sort([PS.distance({j: v for j, v in b["joints"].items() if j in PS.JOINTS}) for b in bank])
        except (OSError, KeyError, ValueError):
            _BANK_D = np.array([])
    pct = round(100.0 * float(np.searchsorted(_BANK_D, d)) / len(_BANK_D), 1) if len(_BANK_D) else None
    return round(float(d), 2), pct


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status != "fail" else 1


def corners(W, rig, part):
    sx, sy, sz = (v / 2 for v in rig["sizes"][part])
    M = W[part]
    return np.array([(M @ np.array([x, y, z, 1.0]))[:3] for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)])


def camera_basis(d):
    f = np.asarray(d, float)
    f /= np.linalg.norm(f)
    right = np.cross(f, [0.0, 1.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, f)
    return right, up


def silhouette(W, rig, cam=CAMERA, res=96):
    """the R6's projected area (orthographic, the player's view direction) in % of its square bounding frame"""
    r, u = camera_basis(cam["dir"])
    polys = []
    for part in MASS:
        P = corners(W, rig, part)
        polys.append(np.stack([P @ r, P @ u], axis=1))
    allp = np.concatenate(polys)
    lo, hi = allp.min(0), allp.max(0)
    span = float(max(hi - lo)) + 1e-6
    grid = np.zeros((res, res), bool)
    ys, xs = np.mgrid[0:res, 0:res]
    pts = np.stack([lo[0] + (xs + 0.5) / res * span, lo[1] + (ys + 0.5) / res * span], axis=-1)
    for P in polys:
        hull = convex_hull(P)
        inside = np.ones((res, res), bool)
        for a, b in zip(hull, np.roll(hull, -1, axis=0)):
            e = b - a
            inside &= (e[0] * (pts[..., 1] - a[1]) - e[1] * (pts[..., 0] - a[0])) >= 0
        grid |= inside
    return float(grid.mean() * 100.0), span


def blade_visible(W, rig, grip, tip, cam=CAMERA, res=96, samples=16):
    """how much of the BLADE the player's camera sees (%): its points from 15 % to 100 % along it, projected the way
    silhouette() projects the body, count where they fall outside the body - or in front of the part that covers them
    (depth along the view, each part by its centre). A cut swung in front of the chest is BEHIND the torso from the
    game camera (the KatanaKaeshi riposte vanished there, 2026-10-24); a parry held up clear of the head reads.
    REPORTED, not gated: the owner's loved cuts hide the blade near the Hit too (the 9/10 Katana4Kiriage 12.5 % at one
    key, the 9/10 GreatswordSideCut 31 %; their setup / hold keys 69-100 %) - it tells a pose that must READ (a parry,
    a guard, a held finish) whether it does"""
    r, u = camera_basis(cam["dir"])
    f = np.asarray(cam["dir"], float)
    f = f / np.linalg.norm(f)
    g, t = np.asarray(grip, float), np.asarray(tip, float)
    if np.linalg.norm(np.cross(t - g, f)) < np.sin(np.radians(20.0)) * np.linalg.norm(t - g):
        return 0.0                                  # END-ON to the camera: a dot on screen, not a blade (2026-11-04)
    pts = np.array([g + k * (t - g) for k in np.linspace(0.15, 1.0, samples)])
    polys, depth = [], []
    for part in MASS:
        P = corners(W, rig, part)
        polys.append(np.stack([P @ r, P @ u], axis=1))
        depth.append(float((P @ f).mean()))
    bp = np.stack([pts @ r, pts @ u], axis=1)
    seen = 0
    for q, dq in zip(bp, pts @ f):
        covered = False
        for P, dp in zip(polys, depth):
            hull = convex_hull(P)
            inside = all((b[0] - a[0]) * (q[1] - a[1]) - (b[1] - a[1]) * (q[0] - a[0]) >= 0
                         for a, b in zip(hull, np.roll(hull, -1, axis=0)))
            if inside and dq > dp - 0.25:                 # behind (or level with) the part that covers it
                covered = True
                break
        seen += 0 if covered else 1
    return 100.0 * seen / samples


def convex_hull(P):
    P = sorted(map(tuple, P))
    if len(P) <= 2:
        return np.array(P)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in P:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(P):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def limb_dir(W, part):
    return -W[part][:3, 1]                         # a limb points down its own -Y


def twinning(W):
    """the angle between the right limb and the MIRRORED left one (x -> -x); small = twins"""
    out = {}
    for a, b in (("Right Arm", "Left Arm"), ("Right Leg", "Left Leg")):
        da, db = limb_dir(W, a), limb_dir(W, b) * np.array([-1.0, 1.0, 1.0])
        out[a.split()[1].lower() + "s"] = float(np.degrees(np.arccos(np.clip(da @ db, -1, 1))))
    return out


def feet(W):
    return {s: (W[f"{s} Leg"] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3] for s in ("Right", "Left")}


def line_of_action(W):
    """the head -> support line's lean from vertical, degrees: the support = the midpoint of the grounded feet (both
    down), else the lower foot (a stance foot half a stud off-centre read 6 deg of lean on a plain rest pose)"""
    head = W["Head"][:3, 3]
    fs = list(feet(W).values())
    down = [p for p in fs if p[1] < GROUND + 0.3]
    ft = sum(down) / len(down) if len(down) == 2 else min(fs, key=lambda p: p[1])
    v = head - ft
    return float(np.degrees(np.arccos(np.clip(v[1] / max(np.linalg.norm(v), 1e-9), -1, 1))))


def com(W):
    tot = sum(MASS.values())
    return sum(W[p][:3, 3] * m for p, m in MASS.items()) / tot


def off_balance(W):
    """how far (studs) the centre of mass falls outside the grounded feet's support in the ground plane; None airborne"""
    fs = [p for p in feet(W).values() if p[1] < GROUND + 0.3]
    if not fs:
        return None
    c = com(W)[[0, 2]]
    pts = [p[[0, 2]] for p in fs]
    if len(pts) == 1:
        d = float(np.linalg.norm(c - pts[0]))
    else:
        a, b = pts
        ab = b - a
        t = float(np.clip((c - a) @ ab / max(ab @ ab, 1e-9), 0, 1))
        d = float(np.linalg.norm(c - (a + ab * t)))
    return max(0.0, d - 0.5)                        # a foot is a stud long: half of it either side is still support


def turn_upper(clip, i, deg):
    """frame i with the upper body (torso, so the arms and head ride it) turned `deg` about Y at the torso"""
    c = {"rig": clip["rig"], "times": [clip["times"][i]], "joints": {}}
    for j, v in clip["joints"].items():
        f = list(v["frames"][min(i, len(v["frames"]) - 1)])
        if j == "Torso" and deg:
            R = C.quat_mat(f[:4])
            a = math.radians(deg)
            Ry = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
            f = list(C.mat_quat(Ry @ R)) + f[4:7]
        c["joints"][j] = {"frames": [f]}
    return c


def game_camera_blade(clip, W, rig, tp_camera=GAME_CAM):
    """EVERY frame's share of the blade's outer half seen from the GAME camera (the governor 2026-11-04: appeal said
    "blade seen 81-100 %" from a behind-and-above direction at the key poses only, while the GIF's game view showed no
    blade for 0.2-0.4 s between them): perspective from Config.ThirdPerson.Offset, hidden = behind a part or end-on
    (proc_dossier.blade_seen). [] without a sword track"""
    import proc_dossier as PD
    sw = clip.get("sword") or {}
    if len(sw.get("tip") or []) != len(W) or len(sw.get("grip_path") or []) != len(W):
        return []
    return [float(np.mean(PD.blade_seen(W[i], rig, *PD._blade_view(clip, i, sw["grip_path"][i], sw["tip"][i], tp_camera))))
            for i in range(len(W))]


def hidden_runs(seen, fps, below=0.34, min_s=0.1):
    """[(start s, end s)] where the blade is (nearly) unseen for at least min_s"""
    out, i = [], 0
    while i < len(seen):
        if seen[i] < below:
            j = i
            while j + 1 < len(seen) and seen[j + 1] < below:
                j += 1
            if (j - i + 1) / fps >= min_s:
                out.append((round(i / fps, 2), round(j / fps, 2)))
            i = j + 1
        else:
            i += 1
    return out


def report(clip, move=None, cheat_max=None):
    rig = C.load_rig("r6")
    W = C.world_frames(clip, rig)
    fps = round(1.0 / (clip["times"][1] - clip["times"][0]))
    key_ts = [float(k["t"]) for k in (move or {}).get("keys", [])] or [float(e["t"]) for e in clip.get("events", []) if e.get("name") == "Hit"]
    rows, cheats = [], {}
    blade_game = game_camera_blade(clip, W, rig)
    for ki, t in enumerate(key_ts):
        i = min(len(W) - 1, int(round(t * fps)))
        w = W[i]
        area, _ = silhouette(w, rig)
        row = {"key": ki, "t": t, "line_of_action_deg": round(line_of_action(w), 1),
               "twin_deg": {k: round(v, 1) for k, v in twinning(w).items()}, "silhouette_pct": round(area, 1)}
        sw = clip.get("sword") or {}
        if len(sw.get("tip") or []) == len(W) and len(sw.get("grip_path") or []) == len(W):
            # the sword is ROOT-local (strike.py solves in the root's frame) and W carries the root: move the blade too
            g, tp = np.asarray(sw["grip_path"][i], float), np.asarray(sw["tip"][i], float)
            root = clip.get("root")
            if isinstance(root, list) and len(root) == len(W):
                R, o = C.quat_mat(root[i][:4]), np.asarray(root[i][4:7], float)
                g, tp = R @ g + o, R @ tp + o
            row["blade_visible_pct"] = round(blade_visible(w, rig, g, tp), 1)
            row["blade_seen_game_pct"] = round(100.0 * blade_game[i], 1)
        if cheat_max:
            best = (area, 0.0)
            for d in np.linspace(-cheat_max, cheat_max, 9):
                a2, _ = silhouette(C.world_frames(turn_upper(clip, i, float(d)), rig)[0], rig)
                if a2 > best[0] + 1.0:                       # a real gain, not noise (round 1: every key hit the limit)
                    best = (a2, float(d))
            if best[1]:
                row["cheat_yaw"] = round(best[1], 1)
                row["cheat_silhouette_pct"] = round(best[0], 1)
                cheats[str(ki)] = {"yaw": round(best[1], 1)}
        sd, pct = space_of(clip, i)
        if sd is not None:
            row["space_deg"] = sd
            row["loved_pct"] = pct
        rows.append(row)
    # balance on near-still frames (a held pose off balance reads wrong; a fast move may pass through it)
    speed = [0.0] + [float(np.linalg.norm(com(W[i]) - com(W[i - 1]))) * fps for i in range(1, len(W))]
    offs = [(i, off_balance(W[i])) for i in range(len(W)) if speed[i] < 1.0]
    bad = [(i, d) for i, d in offs if d is not None and d > 0.25]
    problems = []
    notes = []
    if rows and all(r["line_of_action_deg"] < 5 for r in rows):
        # a NOTE, not a problem: the owner's 9/10 GreatswordSideCut keys stand at 0-2 deg (calibrated 2026-10-22: the
        # rule flagged a loved clip, so it only reports)
        notes.append("every key pose stands upright (line of action < 5 deg) - the loved GreatswordSideCut does too")
    # TWINNED = arms AND legs both mirrored (the whole body symmetric): the owner's 9/10 GreatswordSideCut plants its legs
    # square (0-3 deg) with the arms apart, and a two-handed grip mirrors the arms - one pair alone is not stiff
    # (recalibrated against the loved clips 2026-10-22)
    twins = [r["key"] for r in rows if max(r["twin_deg"].values()) < 10]
    if rows and len(twins) == len(rows):
        problems.append(f"every key pose mirrors its arms AND legs (twinning < 10 deg): keys {twins}")
    off = [r["key"] for r in rows if r.get("space_deg", 0) > OFF_MODEL_DEG]
    if off:
        problems.append(f"key(s) {off} sit OFF-MODEL: further than {OFF_MODEL_DEG} deg/joint from every loved R6 pose (kit/anim/pose_space.py)")
    runs = hidden_runs(blade_game, fps)
    long_runs = [r for r in runs if r[1] - r[0] >= 0.2]
    if long_runs:
        problems.append(f"the blade is unseen from the GAME camera (behind the body or end-on) for {', '.join(f'{a:.2f}-{b:.2f}' for a, b in long_runs)} s")
    if bad:
        problems.append(f"{len(bad)} near-still frame(s) off balance (worst {max(d for _, d in bad):.2f} studs past the feet, frame {max(bad, key=lambda x: x[1])[0]})")
    return {"keys": rows, "balance": {"still_frames": len(offs), "off_balance_frames": len(bad),
                                      "worst": round(max([d for _, d in bad], default=0.0), 3)},
            "blade_game": {"share": round(float(np.mean(blade_game)), 3), "hidden_runs": runs} if blade_game else None,
            "problems": problems, "notes": notes, "cheat_edits": {"keys": cheats} if cheats else None}


def main(argv):
    if not argv:
        return emit("fail", "appeal: needs <Name>", "lune run kit anim appeal Katana1Kesa [--cheat]")
    name = argv[0]
    build = os.environ.get("KIT_BUILD", "build")
    clip = json.load(open(os.path.join(build, "animations", f"{name}.clip.json"), encoding="utf-8"))
    mpath = argv[argv.index("--move") + 1] if "--move" in argv else os.path.join("assets", "animations", f"{name}.move.json")
    move = json.load(open(mpath, encoding="utf-8")) if os.path.isfile(mpath) else None
    cmax = float(argv[argv.index("--max") + 1]) if "--max" in argv else 10.0
    r = report(clip, move, cmax if "--cheat" in argv else None)
    extra = {}
    if "--cheat" in argv and r["cheat_edits"]:
        out = os.path.join("assets", "animations", "blocks", f"{name}.cheat.json")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        json.dump(dict(r["cheat_edits"], about="camera cheats (kit/anim/pose_appeal.py --cheat): per key the upper-body yaw that opens the silhouette to the player camera; merge into the move's key_edits to use"),
                  open(out, "w", encoding="utf-8", newline="\n"), indent=1)
        extra["cheat_file"] = out.replace(os.sep, "/")
    k = r["keys"]
    summ = (f"appeal {name}: {len(k)} key poses - line of action {min((x['line_of_action_deg'] for x in k), default=0):.0f}-"
            f"{max((x['line_of_action_deg'] for x in k), default=0):.0f} deg, silhouette {min((x['silhouette_pct'] for x in k), default=0):.0f}-"
            f"{max((x['silhouette_pct'] for x in k), default=0):.0f} %, {r['balance']['off_balance_frames']} still frame(s) off balance")
    if r.get("blade_game"):
        bg = r["blade_game"]
        bv = [x["blade_seen_game_pct"] for x in k if "blade_seen_game_pct" in x]
        summ += (f", blade seen from the game camera {bg['share']:.0%} of every frame" + (f" ({min(bv):.0f}-{max(bv):.0f} % at the keys)" if bv else "")
                 + (f", unseen {', '.join(f'{a:.2f}-{b:.2f}' for a, b in bg['hidden_runs'])} s" if bg["hidden_runs"] else ""))
    sp = [x["space_deg"] for x in k if "space_deg" in x]
    if sp:
        summ += f", {min(sp):.1f}-{max(sp):.1f} deg/joint from the loved pose space"
    if extra.get("cheat_file"):
        summ += f"; camera cheats for {len(r['cheat_edits']['keys'])} key(s) -> {extra['cheat_file']}"
    status = "warn" if r["problems"] else "pass"
    return emit(status, summ + (f" - {r['problems'][0]}" if r["problems"] else ""),
                "LOOK at the flagged keys on the owner's rig (kit anim look <Name> --rig R6); these numbers flag, the owner judges",
                **r, **extra)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
