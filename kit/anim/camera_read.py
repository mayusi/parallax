"""camera_read.py — THE STRIKE AS THE PLAYER'S CAMERA SEES IT, OVER TIME (the owner's older list, AN-36: "temporal
evaluation should use the gameplay camera ... silhouette separation, weapon-path visibility, occlusion and spacing
analysis across time and camera angles ... a move remains readable in normal gameplay, not only in an isolated pose
sheet").

What the kit already read from the game camera: how much of the BLADE is seen, frame by frame, and where it is hidden
for a fifth of a second or more (kit/anim/pose_appeal.py game_camera_blade, hidden_runs), and one pose's silhouette.
What it did not: an UNARMED strike at all (a kick, a punch), how much of the strike's motion goes ACROSS the screen
(a thrust straight away from the camera is a dot that grows: it travels, and nothing is seen to move), and the camera
anywhere but straight behind (a player turns it).

    python kit/anim/camera_read.py <clip.json>           the reading, camera by camera
    python kit/anim/camera_read.py table <folder>        every clip of a folder of built clips, one line each

THE STRIKER: the blade's tip (a weapon clip), else the hand or foot that moves fastest (kit/anim/pose_sheet.py).
THE STRIKE: the stretch round the Hit in which it is at half its top speed or more - the Hit always in it, never
more than 0.3 s before it or 0.1 s after (a spin's whole flourish is not the strike). No Hit: round its top speed.
THE CAMERAS: the game's third-person camera (kit/anim/pose_appeal.py GAME_CAM, over the shoulder) straight behind,
and turned 45 degrees to either side about the body (left: the camera over the body's left) - the body's travel
followed along the floor, its facing taken where the move BEGINS (a player's camera does not spin with a spin).
PER CAMERA, over the strike:
  seen        the share of its frames the striker is not behind a block of the body (and, a blade, not end-on)
  across      the share of the striker's travel that goes ACROSS the screen (1: all of it; 0: straight along the
              camera's line - it moves and nothing is seen to move)
  on_screen   how far it travels on the screen, in body heights (the R6 is 5 studs tall at its own distance)
  change      how far the hands, the feet and the blade's tip are, on the screen, from where they were when the
              strike began, in body heights, at its end (a strike whose end looks like its start has no shape)
READ = seen x across: the share of the strike a player sees move. The report names the camera it reads worst from.

WHAT THIS IS: numbers for the eye to be pointed by, like the pose sheet's. It is NOT a gate: measured on the cuts
the owner loved and rejected (the table in kit/test/python/test_anim_camera_read.py), `read` does not tell them
apart - a loved overhead cut goes mostly along the camera's line. One thing is said plainly, because no camera
angle excuses it: a strike that is never seen from ANY of the three (`seen` 0 everywhere) - this command fails on
it; the BUILD does not (it carries the reading as `camera` in the clip's metrics, `never_seen` in it).
NOT DONE: competing effects (a slash's own VFX covering the blade is the VFX lane's to read), other players' cameras,
a first-person camera, a camera a game zooms or shakes."""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

CAMERAS = {"behind": 0.0, "left": -45.0, "right": 45.0}     # degrees the game camera is turned about the body
BEFORE, AFTER = 0.3, 0.1     # seconds: the strike is never read further than this before / after its Hit
HALF = 0.5           # the strike: the striker at this share of its top speed or more
BODY = 5.0           # studs: an R6's height
PARTS = ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _tracks(clip):
    """-> (world frames, {name: [n, 3]} the hands, the feet and - a weapon clip - the grip and the tip, the clip's
    travel carried, striker name)"""
    import clip as C
    import pose_sheet as PS
    rig = C.load_rig("r6")
    W = C.world_frames(clip, rig)
    p = PS.paths(clip, W)
    fps = C.clip_fps(clip)
    return rig, W, p, PS.striker(p, fps), fps


def strike_window(clip, path, fps):
    """the frames [first, last] of the strike: the stretch at HALF the striker's top speed or more that holds the Hit
    (no Hit: the top speed)"""
    n = len(path)
    if n < 3:
        return 0, max(n - 1, 0)
    v = np.r_[0.0, np.linalg.norm(np.diff(path, axis=0), axis=1)] * fps
    hit = next((int(round(float(e["t"]) * fps)) for e in clip.get("events") or []
                if isinstance(e, dict) and e.get("name") == "Hit" and isinstance(e.get("t"), (int, float))), None)
    peak = int(np.argmax(v))
    if hit is not None:
        lo, hi = max(1, hit - int(0.25 * fps)), min(n - 1, hit + int(0.05 * fps))
        peak = lo + int(np.argmax(v[lo:hi + 1])) if hi >= lo else peak
    top = float(v[peak])
    if top <= 1e-6:
        return 0, n - 1
    a = b = peak
    while a > 1 and v[a - 1] >= HALF * top:
        a -= 1
    while b < n - 1 and v[b + 1] >= HALF * top:
        b += 1
    a = max(a - 1, 0)                                        # (the frame it leaves from is part of the strike)
    if hit is not None:
        h = min(max(hit, 0), n - 1)
        a, b = max(a, h - int(round(BEFORE * fps))), min(b, h + int(round(AFTER * fps)))
        a, b = min(a, h), max(b, h)
        if b - a < 1:
            a = max(a - 1, 0)
            b = min(a + 1, n - 1)
    return a, b


def camera_at(clip, i, yaw_deg):
    """the game camera's place and its aim at frame i, turned yaw_deg about the body, following the body's travel"""
    import pose_appeal as PA
    import proc_dossier as PD
    off = PD.FP_EYE + np.asarray(PA.GAME_CAM, float)
    a = math.radians(yaw_deg) + _facing(clip)
    R = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    cam, aim = R @ off, np.array([0.0, float(PD.FP_EYE[1]) - 1.0, 0.0])
    root = clip.get("root")
    if isinstance(root, list) and i < len(root):
        o = np.asarray(root[i][4:7], float)
        shift = np.array([o[0], 0.0, o[2]])
        return cam + shift, aim + shift
    return cam, aim


def _facing(clip):
    """the body's turn about the vertical where the move begins (radians; 0 with no root)"""
    root = clip.get("root")
    if not (isinstance(root, list) and root and len(root[0]) >= 4):
        return 0.0
    x, y, z, w = (float(v) for v in root[0][:4])
    return math.atan2(2.0 * (w * y + x * z), 1.0 - 2.0 * (y * y + x * x))


def screen(cam, aim, p):
    """a world point on the camera's screen -> (x, y) in body heights at the body's own distance, its depth"""
    f = aim - cam
    dist = float(np.linalg.norm(f))
    f = f / max(dist, 1e-9)
    r = np.cross(f, [0.0, 1.0, 0.0])
    r = r / max(float(np.linalg.norm(r)), 1e-9)
    u = np.cross(r, f)
    d = np.asarray(p, float) - cam
    depth = max(float(d @ f), 1e-6)
    return np.array([float(d @ r), float(d @ u)]) / depth * dist / BODY, depth


def read(clip):
    """-> {"striker", "window": [first, last], "fps", "cams": {name: {seen, across, on_screen, change, read}},
    "worst": camera name, "read": the worst camera's read}. ValueError on a clip that cannot be read"""
    import proc_dossier as PD
    if clip.get("rig") != "R6":
        raise ValueError(f"it is a {clip.get('rig')} clip - the camera reads the R6 clip")
    rig, W, p, striker, fps = _tracks(clip)
    n = len(W)
    if n < 3:
        raise ValueError("it has fewer than three frames")
    path = p[striker]
    first, last = strike_window(clip, path, fps)
    armed = striker == "BladeTip"
    ends = [k for k in ("RightHand", "LeftHand", "RightFoot", "LeftFoot", "BladeTip") if k in p]
    cams = {}
    for name, yaw in CAMERAS.items():
        seen, across_num, across_den, on_screen = 0, 0.0, 0.0, 0.0
        prev = None
        for i in range(first, last + 1):
            cam, aim = camera_at(clip, i, yaw)
            if armed:
                vis = bool(np.mean(PD.blade_seen(W[i], rig, cam, p["Grip"][i], p["BladeTip"][i])) >= 0.5)
            else:
                vis = not any(PD._segment_hits_box(W[i][part], rig["sizes"][part], cam, path[i]) for part in PARTS
                              if part in W[i] and not _owns(part, striker) and not _inside(W[i][part], rig["sizes"][part], path[i], part=part))
            seen += 1 if vis else 0
            s, depth = screen(cam, aim, path[i])
            if prev is not None:
                step3 = float(np.linalg.norm(path[i] - path[i - 1]))
                step2 = float(np.linalg.norm(s - prev[0])) * BODY * depth / max(float(np.linalg.norm(aim - cam)), 1e-9)
                across_num += min(step2, step3)
                across_den += step3
                on_screen += float(np.linalg.norm(s - prev[0]))
            prev = (s, depth)
        frames = last - first + 1
        cam0, aim0 = camera_at(clip, first, yaw)
        cam1, aim1 = camera_at(clip, last, yaw)
        change = float(np.mean([np.linalg.norm(screen(cam1, aim1, p[k][last])[0] - screen(cam0, aim0, p[k][first])[0]) for k in ends]))
        share_seen = seen / max(frames, 1)
        across = across_num / across_den if across_den > 1e-9 else 0.0
        cams[name] = {"seen": round(share_seen, 3), "across": round(across, 3), "on_screen": round(on_screen, 3),
                      "change": round(change, 3), "read": round(share_seen * across, 3)}
    worst = min(cams, key=lambda k: cams[k]["read"])
    return {"striker": striker, "window": [int(first), int(last)], "fps": fps, "cams": cams, "worst": worst,
            "read": cams[worst]["read"]}


def _inside(M, size, p, pad=0.15, part=None):
    """the point is in (or against) a LIMB's block: hands held together, a foot against the other leg - touching a
    limb is not being hidden behind it. Not the torso or the head: a fist in front of the chest is hidden from
    behind (the one review: 36 of 999 camera-frames read as seen that way)"""
    if part in ("Torso", "Head"):
        return False
    M = np.asarray(M, float)
    q = M[:3, :3].T @ (np.asarray(p, float) - M[:3, 3])
    return bool(np.all(np.abs(q) <= np.asarray(size, float) / 2 + pad))


def _owns(part, striker):
    """a limb does not hide its own end"""
    return {"RightHand": "Right Arm", "LeftHand": "Left Arm", "RightFoot": "Right Leg", "LeftFoot": "Left Leg"}.get(striker) == part


def problem(r):
    """the one thing no camera angle excuses -> words or None"""
    if all(c["seen"] == 0 for c in r["cams"].values()):
        a, b = r["window"]
        return (f"the strike is never seen: from the game camera behind the body and from 45 degrees to either side the "
                f"{'blade' if r['striker'] == 'BladeTip' else WORD.get(r['striker'], r['striker'])} is hidden for all of frames "
                f"{a}-{b} ({a / r['fps']:.2f}-{b / r['fps']:.2f} s) - open the pose to the camera, or move the strike out from "
                "behind the body")
    return None


WORD = {"RightHand": "right hand", "LeftHand": "left hand", "RightFoot": "right foot", "LeftFoot": "left foot"}


def words(r, name):
    c = r["cams"]
    a, b = r["window"]
    who = "the blade" if r["striker"] == "BladeTip" else "the " + WORD.get(r["striker"], r["striker"])
    return (f"{name}: {who} strikes over frames {a}-{b}; a player sees "
            + ", ".join(f"{int(round(100 * c[k]['read']))} in 100 of it move from {k}" for k in CAMERAS)
            + f" (worst from {r['worst']}: seen {int(round(100 * c[r['worst']]['seen']))} in 100 of its frames, "
            f"{int(round(100 * c[r['worst']]['across']))} in 100 of its travel across the screen)")


def gate(clip):
    """what the build's motion gates add (kit/anim/metrics.py) -> (the reading or None, None): the reading is for
    the eye and the build never fails on it (`never_seen` is said in it: on the built clips the ones it named were
    hit reactions and clips whose striker was picked wrong, not strikes a player cannot see). A clip that is no
    strike (no Hit, a loop, a prop) is not read"""
    if not isinstance(clip, dict) or clip.get("rig") != "R6" or clip.get("prop") or clip.get("loop"):
        return None, None
    if "Reaction" in str(clip.get("name") or ""):
        return None, None                                    # (a hit reaction is struck, it does not strike)
    if not any(isinstance(e, dict) and e.get("name") == "Hit" for e in clip.get("events") or []):
        return None, None
    try:
        r = read(clip)
    except Exception as e:                                   # noqa: BLE001 (a reading never breaks a build)
        return {"error": f"{type(e).__name__}: {e}"}, None   # (not a strike the camera can read: said, not failed)
    r["never_seen"] = problem(r) is not None
    return r, None


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    try:
        if argv[0] == "table":
            import glob
            rows = []
            for path in sorted(glob.glob(os.path.join(argv[1], "*.clip.json"))):
                if "." in os.path.basename(path)[:-len(".clip.json")]:
                    continue                                 # (a working file: <Name>.preview / .r6 / .learned ...)
                with open(path, encoding="utf-8") as fh:
                    c = json.load(fh)
                g, _ = gate(c)
                if g and "cams" in g:
                    rows.append({"name": c.get("name"), "striker": g["striker"], "read": g["read"], "worst": g["worst"],
                                 **{k: g["cams"][k]["read"] for k in CAMERAS}})
            rows.sort(key=lambda x: x["read"])
            return emit("pass", f"anim camera: {len(rows)} strike(s) read; the least seen to move: "
                        + ", ".join(f"{x['name']} {int(round(100 * x['read']))}" for x in rows[:5]), "look at those first", rows=rows)
        with open(argv[0], encoding="utf-8") as fh:
            c = json.load(fh)
        r = read(c)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"anim camera: it could not be read ({type(e).__name__}: {e})", "python kit/anim/camera_read.py <clip.json>")
    bad = problem(r)
    if bad:
        return emit("fail", f"anim camera {c.get('name')}: {bad}", "open the pose to the camera", **r)
    return emit("pass", f"anim camera: {words(r, str(c.get('name')))}", "none - a reading for the eye, not a verdict", **r)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
