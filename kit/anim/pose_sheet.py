"""pose_sheet.py - LOOKING AT A MOVE: its key poses LARGE, beside their reference, and its motion as strips (the
animation studio route's sprint A0, board/plans/archive/2026-11-11-anim-studio-route-plan.md). Before it a session judged a
pose from 360 x 450 views framed on a sphere round the whole clip (the body a third of the picture, the blade out of
it, a flash ball on the tip at the Hit) and never saw the move's own reference beside it.

Three steps, run by `lune run kit anim sheet <Name>` and at the end of every named build (kit/cmd/anim.luau):

    python kit/anim/pose_sheet.py plan <Name> --out <dir> [--clip <clip.json>] [--move <move.json>] [--dossier <move>]
        -> <dir>/plan.json: the key poses (thumbs.key_times), 12 frames a second for the strips, each key's phase and
           the dossier's reference frame of that phase (proc_dossier.reference_for)
    blender -b assets/rigs/R6_IK.blend ... -P kit/anim/look_r6.py -- <Name>.r6 --clip <clip.json> --out <dir> --sheet <dir>/plan.json
        -> <dir>/frames/*.png + <dir>/render.json: the OWNER'S rig at those frames (the one renderer the lane has),
           every picture framed on what it shows (camera_fit) and its camera written down
    python -I kit/anim/pose_sheet.py pages <dir>
        -> <dir>/pose_sheet.png   every key pose (a row): its reference frame | the player's camera | the side | above,
                                  768 px each; drawn on them: the blade tip's path through the keys (numbered), the
                                  centre of mass dropped to the floor, the feet's support under it
           <dir>/keys/*.png       the same panes two at a time: what a session opens at full size
           <dir>/strip_<view>.png the motion at 12 frames a second, 512 px a frame, one camera for the whole strip, the
                                  hands', feet's and blade tip's paths with a dot per strip frame (gaps = speed)
           <dir>/strips/*.png     the strips three frames a page
           <dir>/look.json        what every file shows + the LOOK: line the build ends with

Nothing here judges: it is the picture a session and the owner look at. (pages runs isolated: it reads downloaded
footage; the kit modules are found from this file's own folder.)"""
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C            # noqa: E402
import pose_appeal as PA    # noqa: E402
import thumbs as T          # noqa: E402

KEY_SIZE = 768              # a key pose's pane, each view (the plan: "768 px each"; the looks were 360 x 450)
STRIP_SIZE = 512            # a strip frame's width (they were about 420 px, two views)
STRIP_RATE = 12             # strip frames a second
# the views, as directions FROM the character TO the camera in the rig file's axes (Blender: x = its right, y = the
# way it faces, z = up). "player" and "side" are look_r6's "game" and "side" (it reads them from here)
VIEW_DIRS = {"player": (0.18, -0.85, 0.5), "side": (1.0, 0.0, 0.12), "top": (0.0, 0.0, 1.0), "front": (0.0, 1.0, 0.15)}
VIEW_TITLE = {"player": "PLAYER'S CAMERA (behind and above)", "side": "SIDE (it faces right)",
              "top": "ABOVE (it faces up the picture)", "front": "FRONT (its right arm on your left)"}
VIEW_ORTHO = ("top",)       # a plan view has no perspective: the centre of mass stands exactly over its floor point
KEY_VIEWS = ("player", "side", "top")
KEY_ASPECT = (1.0, 1.6)     # a key pose's pane is KEY_SIZE high and, per view, as wide as its WIDEST pose needs: a
#                             blade held out sideways in a square pane left the body 250 px tall (looked at 2026-11-12)
STRIP_VIEWS = ("player", "side")
STRIP_ASPECT = (0.8, 1.6)   # a strip frame is STRIP_SIZE high and as wide as its motion, within these
STRIP_HOLD = (4.0, 2.5)     # ... and holds of the paths what lies within this many body heights across and up (a
#                             4.8-stud blade's whole sweep in a 512 px frame left the body 165 px tall: looked at
#                             2026-11-12; held this way the body is never under 190 px and that sweep still fits)
# drawn colours: the strip's own arcs (kit/anim/strip.py ARC) so a strip and a sheet read the same limbs
PATH_COLOUR = {"RightHand": (255, 110, 100), "LeftHand": (255, 190, 110), "RightFoot": (110, 230, 160),
               "LeftFoot": (190, 160, 255), "BladeTip": (255, 214, 40)}
PATH_NAME = {"RightHand": "right hand", "LeftHand": "left hand", "RightFoot": "right foot", "LeftFoot": "left foot",
             "BladeTip": "blade tip"}
PAGE_WIDTH = 2400           # what a page holds: about the width a picture this high is still read at full size
#                             (1,950 x 814 came through unshrunk, 3,084 x 5,022 at half: looked at 2026-11-12)
INK, PAPER, BAR = (16, 17, 21), (236, 237, 241), (30, 32, 38)
GOOD, OFF = (70, 205, 120), (255, 150, 45)
OVERLAY_TOLERANCE = 0.15    # studs between the kit's FK and the rig's meshes past which nothing is drawn on a render


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


# ---------------------------------------------------------------- cameras (pure: Blender and the pages share them)
def unit(v):
    v = np.asarray(v, float)
    return v / max(float(np.linalg.norm(v)), 1e-12)


def camera_basis(direction):
    """(right, up, back) of a camera that sits along `direction` from what it looks at, world z up; straight down, the
    picture's right is world +x and its top world +y (the way the rig faces)"""
    d = unit(direction)
    r = np.cross(-d, [0.0, 0.0, 1.0])
    r = np.array([1.0, 0.0, 0.0]) if float(np.linalg.norm(r)) < 1e-6 else unit(r)
    return r, np.cross(r, -d), d


def camera_fit(direction, points, aspect=1.0, margin=1.12, sweep=2.6, ortho=False):
    """a camera along `direction` that frames `points` as LARGE as a picture of `aspect` (width / height) allows: their
    box in the picture's own plane, centred, with a margin. (look.camera_for frames a sphere round the whole clip:
    a body 5.5 studs tall came out a third of the picture's height.) The distance keeps look.py's perspective (2.6
    half-extents back); `ortho` is a plan view, no perspective at all.
    -> {loc, right, up, back, tan: [half-width, half-height] at depth 1 (ortho: in studs), ortho}"""
    P = np.asarray(points, float).reshape(-1, 3)
    r, u, d = camera_basis(direction)
    c = (P.min(0) + P.max(0)) / 2
    x, y, z = (P - c) @ r, (P - c) @ u, (P - c) @ d
    half = max(float(x.max() - x.min()) / 2, float(y.max() - y.min()) / 2, 0.5)
    dist = half * sweep + float(z.max() - z.min()) / 2
    loc = c + r * float(x.max() + x.min()) / 2 + u * float(y.max() + y.min()) / 2 + d * dist
    if ortho:
        tw, th = float(x.max() - x.min()) / 2 * margin, float(y.max() - y.min()) / 2 * margin
        tw, th = max(tw, th * aspect, 1e-4), max(th, tw / aspect, 1e-4)
        return {"loc": loc.tolist(), "right": r.tolist(), "up": u.tolist(), "back": d.tolist(), "tan": [tw, th], "ortho": True}
    for _ in range(8):                                # perspective: the near points weigh more; centre what is SEEN
        q = P - loc
        depth = -(q @ d)
        uu, vv = (q @ r) / depth, (q @ u) / depth
        du, dv = float(uu.max() + uu.min()) / 2, float(vv.max() + vv.min()) / 2
        if abs(du) + abs(dv) < 1e-6:
            break
        loc = loc + (r * du + u * dv) * dist
    q = P - loc
    depth = -(q @ d)
    uu, vv = (q @ r) / depth, (q @ u) / depth
    tw, th = float(uu.max() - uu.min()) / 2 * margin, float(vv.max() - vv.min()) / 2 * margin
    tw, th = max(tw, th * aspect, 1e-4), max(th, tw / aspect, 1e-4)
    return {"loc": loc.tolist(), "right": r.tolist(), "up": u.tolist(), "back": d.tolist(), "tan": [tw, th], "ortho": False}


def lens_of(cam, sensor=36.0):
    """the Blender lens (mm, sensor fit AUTO: the sensor spans the picture's larger side) of a fitted camera; an
    ortho camera's scale is 2 * max(tan) the same way"""
    return sensor / (2.0 * max(cam["tan"]))


def strip_points(direction, body, drawn, hold=STRIP_HOLD):
    """what a strip's ONE camera frames: the body on every strip frame, and of the drawn paths what lies within
    `hold` body heights (across, up) of it in the picture's plane (a path point further out is pulled onto that
    border: the far end of a very long sweep leaves the picture, the body stays large)"""
    r, u, _ = camera_basis(direction)
    B = np.asarray(body, float).reshape(-1, 3)
    E = np.asarray(drawn, float).reshape(-1, 3)
    if not len(E):
        return B
    bx, by = B @ r, B @ u
    cx, cy = float(bx.max() + bx.min()) / 2, float(by.max() + by.min()) / 2
    tall = max(float(bx.max() - bx.min()), float(by.max() - by.min()))     # (seen from the side a body is 1 stud wide)
    hw, hh = tall * hold[0] / 2, tall * hold[1] / 2
    ex, ey = E @ r, E @ u
    E = E + np.outer(np.clip(ex, cx - hw, cx + hw) - ex, r) + np.outer(np.clip(ey, cy - hh, cy + hh) - ey, u)
    return np.concatenate([B, E])


def pane_size(direction, clouds, height, aspect):
    """a pane's [width, height] in px: `height` high, and as wide as the WIDEST of the point clouds it will show needs
    (each cloud's box in the picture's plane), within `aspect` (lowest, highest width / height)"""
    r, u, _ = camera_basis(direction)
    ratio = 0.0
    for cloud in clouds:
        P = np.asarray(cloud, float).reshape(-1, 3)
        ratio = max(ratio, float(np.ptp(P @ r)) / max(float(np.ptp(P @ u)), 1e-6))
    return [int(round(height * min(aspect[1], max(aspect[0], ratio)) / 2)) * 2, int(height)]


def strip_size(direction, points, height=STRIP_SIZE):
    """a strip frame's [width, height]: `height` px high, as wide as the motion it holds (STRIP_ASPECT)"""
    return pane_size(direction, [points], height, STRIP_ASPECT)


def project(cam, points, size):
    """world points -> (pixels [n, 2], depth [n]) in a picture of `size` (w, h); depth <= 0 is behind the camera"""
    q = np.asarray(points, float).reshape(-1, 3) - np.asarray(cam["loc"], float)
    depth = -(q @ np.asarray(cam["back"], float))
    safe = np.ones_like(depth) if cam.get("ortho") else np.where(np.abs(depth) < 1e-9, 1e-9, depth)
    x = (q @ np.asarray(cam["right"], float)) / safe / cam["tan"][0]
    y = (q @ np.asarray(cam["up"], float)) / safe / cam["tan"][1]
    return np.stack([size[0] / 2 * (1 + x), size[1] / 2 * (1 - y)], axis=1), depth


def to_blender(points, origin):
    """the kit's character space (x right, y up, -z forward; the root at the origin) -> the rig file's (x, -z, y),
    moved to where its HumanoidRootPart rests (look.bl + the look's origin)"""
    p = np.asarray(points, float)
    return np.stack([p[..., 0], -p[..., 2], p[..., 1]], axis=-1) + np.asarray(origin, float)


# ---------------------------------------------------------------- what is drawn (pure, from the clip's own FK)
def frame_of(clip, t):
    fps = float(clip.get("fps") or round(1.0 / (clip["times"][1] - clip["times"][0])))
    return int(min(len(clip["times"]) - 1, max(0, round(float(t) * fps))))


def strip_frames(clip, rate=STRIP_RATE):
    """the clip's frames at `rate` a second, from its first (a 60 fps clip: every 5th)"""
    fps = float(clip.get("fps") or round(1.0 / (clip["times"][1] - clip["times"][0])))
    n = len(clip["times"])
    out = []
    k = 0
    while True:
        i = int(round(k * fps / rate))
        if i > n - 1:
            break
        if not out or i != out[-1]:
            out.append(i)
        k += 1
    return out


def limb_end(W, part):
    """a one-piece R6 limb's far end (the hand, the sole's centre): a stud down its own axis"""
    return (W[part] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]


def paths(clip, frames):
    """{name: [n, 3]} over the whole clip, character space: the hands, the soles and (a sword clip) the blade's tip and
    grip, the root's travel carried"""
    out = {"RightHand": [limb_end(W, "Right Arm") for W in frames], "LeftHand": [limb_end(W, "Left Arm") for W in frames],
           "RightFoot": [limb_end(W, "Right Leg") for W in frames], "LeftFoot": [limb_end(W, "Left Leg") for W in frames]}
    lines = [T.blade_line(clip, i) for i in range(len(frames))]
    if lines and all(ln is not None for ln in lines):
        out["Grip"] = [ln[0] for ln in lines]
        out["BladeTip"] = [ln[1] for ln in lines]
    return {k: np.array(v, float) for k, v in out.items()}


def striker(pth, fps):
    """the path a pose sheet draws through the keys: the blade's tip, else the hand or foot that moves fastest"""
    if "BladeTip" in pth:
        return "BladeTip"
    best = max(("RightHand", "LeftHand", "RightFoot", "LeftFoot"),
               key=lambda k: float(np.linalg.norm(np.diff(pth[k], axis=0), axis=1).max()) if len(pth[k]) > 1 else 0.0)
    return best


def hull_gap(point, hull):
    """how far (studs) a floor point lies OUTSIDE a convex hull [[x, z] ...]; 0 inside. One sole is a hull too"""
    p = np.asarray(point, float)
    H = np.asarray(hull, float).reshape(-1, 2)
    if len(H) == 0:
        return None
    if len(H) >= 3:
        sign = 0
        inside = True
        for a, b in zip(H, np.roll(H, -1, axis=0)):
            cr = float((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]))
            if abs(cr) < 1e-12:
                continue
            if sign == 0:
                sign = 1 if cr > 0 else -1
            elif (cr > 0) != (sign > 0):
                inside = False
                break
        if inside:
            return 0.0
    best = 1e9
    for a, b in zip(H, np.roll(H, -1, axis=0)):
        ab = b - a
        t = float(np.clip((p - a) @ ab / max(float(ab @ ab), 1e-12), 0, 1))
        best = min(best, float(np.linalg.norm(p - (a + ab * t))))
    return best


def weight(W, rig):
    """where the body's weight is on one frame: its centre of mass (pose_appeal.com: the parts' masses), the SUPPORT
    under it (the hull of the grounded soles on the floor; a sole is grounded within 0.3 studs, as pose_appeal has
    it) and how far the centre of mass stands outside that support (0 = over the feet, None = airborne)"""
    com = PA.com(W)
    down, corners = [], []
    for side in ("Right", "Left"):
        part = f"{side} Leg"
        if limb_end(W, part)[1] < PA.GROUND + 0.3:
            down.append(side)
            sx, sy, sz = (v / 2 for v in rig["sizes"][part])
            corners += [(W[part] @ np.array([x, -sy, z, 1.0]))[:3] for x in (-sx, sx) for z in (-sz, sz)]
    hull = PA.convex_hull(np.array([[c[0], c[2]] for c in corners])) if corners else np.zeros((0, 2))
    gap = hull_gap(com[[0, 2]], hull)
    return {"com": com, "down": down, "support": [[float(x), PA.GROUND, float(z)] for x, z in hull],
            "outside": None if gap is None else round(float(gap), 3)}


def weight_words(w):
    if w["outside"] is None:
        return "weight: airborne (no sole on the floor)"
    feet = " + ".join(s.lower() for s in w["down"]) + (" feet" if len(w["down"]) > 1 else " foot")
    if w["outside"] <= 0.05:
        return f"weight: over the {feet}"
    return f"weight: {w['outside']:.2f} studs OUTSIDE the {feet}"


# ---------------------------------------------------------------- the plan
def dossier_of(name, move, anims, explicit=None, clip=None):
    """the move dossier a clip is looked at beside: named, else its move's / its own (a candidate clip names its
    dossier) / its game spec's `dossier`, else its own name in snake case when such a dossier exists
    -> (dossier name or None, the dossier or None)"""
    import proc_dossier as PD
    cand = explicit or (move or {}).get("dossier") or (clip or {}).get("dossier")
    if not cand:
        spec = os.path.join(anims, f"{name}.dossier.json")
        if os.path.isfile(spec):
            try:
                cand = json.load(open(spec, encoding="utf-8")).get("dossier")
            except (OSError, ValueError):
                cand = None
    cand = cand or PD.snake(name)
    path = os.path.join(anims, "dossiers", f"{cand}.json")
    if not os.path.isfile(path):
        return (cand if explicit else None), None
    try:
        return cand, json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return cand, None


def inputs_hash(paths):
    """one sha256 over the files' bytes in order (kit/cmd/anim.luau sha256Of reads it back: a sheet is FRESH while
    what it was made from - the clip, its move, its dossier, the two kit files that draw it - is unchanged)"""
    import hashlib
    h = hashlib.sha256()
    for p in paths:
        with open(p, "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()


def extremes(clip, frames=None, below=0.35, apart=0.1):
    """the moments a motion nearly STOPS between its fast stretches - the top of a wind-up, the end of a follow-through:
    the poses a move without authored keys is judged at. The mean speed of the hands, the soles and the blade's tip,
    smoothed over 5 frames; its local minima under `below` of its peak, `apart` seconds from each other -> [seconds]"""
    if frames is None:
        frames = C.world_frames(clip, C.load_rig("r6"))
    pth = paths(clip, frames)
    n = len(frames)
    if n < 7:
        return []
    fps = float(clip.get("fps") or round(1.0 / (clip["times"][1] - clip["times"][0])))
    speed = np.zeros(n)
    used = [k for k in PATH_COLOUR if k in pth]
    for k in used:
        speed[1:] += np.linalg.norm(np.diff(pth[k], axis=0), axis=1) * fps / len(used)
    speed[0] = speed[1]
    smooth = np.convolve(np.pad(speed, 2, mode="edge"), np.ones(5) / 5, mode="valid")
    peak = float(smooth.max())
    if peak < 1e-6:
        return []
    out = []
    for i in range(1, n - 1):
        if smooth[i] <= smooth[i - 1] and smooth[i] < smooth[i + 1] and smooth[i] < below * peak:
            t = float(clip["times"][i])
            if not out or t - out[-1] >= apart:
                out.append(t)
    return out


def key_moments(clip, move=None, frames=None):
    """the moments a move's poses are looked at: its authored keys (thumbs.key_times); a move with none - a procedural
    candidate carries its Hit and nothing else - also at its extremes, so its wind-up and its finish are on the sheet"""
    ts = T.key_times(clip, move)
    if any(isinstance(k, dict) and "t" in k for k in (move or {}).get("keys", [])):
        return ts
    for t in extremes(clip, frames):
        if all(abs(t - have) >= 0.1 - 1e-9 for have in ts):      # (an extreme beside a mark is that mark's pose)
            ts.append(t)
    ts.sort()
    if len(ts) > T.MAX_KEYS:
        ts = [ts[int(round(k * (len(ts) - 1) / (T.MAX_KEYS - 1)))] for k in range(T.MAX_KEYS)]
    return ts


def plan(name, clip, move=None, dossier_name=None, dossier=None, strips=True, clip_path=None, inputs=None, blocking=None):
    """which frames of a clip are looked at, and beside what. Pure: the clip, its move and its dossier in -> the plan.
    `blocking`: the manifest of a BLOCKING (kit/anim/blocking.py make) when the clip is one - each pose then carries how
    long it is held and the owner's notes on it, and the sheet says where his answer stands"""
    import proc_dossier as PD
    refs = PD.reference_frames(dossier) if dossier else []
    phases = {p.get("name"): p for p in (dossier or {}).get("phases") or [] if isinstance(p, dict)}
    hits = [float(e["t"]) for e in clip.get("events") or [] if str(e.get("name", "")).lower() in C.HIT_NAMES]
    moments, seen = [], set()
    # (a blocking shows EVERY one of its poses, numbered as its manifest numbers them: never thinned to a sheet's ten)
    for t in ([float(p["t"]) for p in blocking.get("poses") or []] if blocking else key_moments(clip, move)):
        i = frame_of(clip, t)
        if i not in seen:
            seen.add(i)
            moments.append((float(t), i))
    # each pose's phase: by the dossier's game timing, or - a clip not timed like its dossier - in order round the Hit
    named, phase_by, phase_note = (PD.phases_for(dossier, [t for t, _ in moments], hits[0] if hits else None)
                                   if dossier else ([None] * len(moments), None, None))
    keys = []
    for (t, i), its_phase in zip(moments, named):
        row = {"k": len(keys) + 1, "t": round(float(t), 4), "frame": i, "phase": None, "phase_body": None,
               "reference": None, "reference_gap": None}
        if dossier:
            phase, ref, why = PD.reference_for(dossier, t, refs=refs, phase=its_phase)
            row["phase"] = phase
            row["phase_body"] = (phases.get(phase) or {}).get("body")
            if ref is not None:                          # (named, on this machine or not: the sheet goes stale when it arrives)
                row["reference_file"] = ref.get("video") or ref.get("image")
            if ref is not None and not why:
                row["reference"] = {k: ref.get(k) for k in ("phase", "video", "image", "t", "game_t", "note", "source",
                                                             "view", "crop", "flip", "path")}
            else:
                row["reference_gap"] = why
        else:
            row["reference_gap"] = (f"no dossier named {dossier_name} in assets/animations/dossiers" if dossier_name
                                    else "this clip has no move dossier (a library clip, or one made before the rule)")
        keys.append(row)
    blk = None
    if blocking:
        held = {int(p["frame"]): p for p in blocking.get("poses") or []}
        for row in keys:
            p = held.get(int(row["frame"]))
            if p is not None:                               # the sheet's rows ARE the blocking's poses, numbered alike
                row["hold_s"] = p["hold_s"]
                row["notes"] = [n for n in blocking.get("notes") or []
                                if n.get("pose") is not None and int(n["pose"]) == int(p["k"])]
        blk = {"of": blocking.get("name"), "id": blocking.get("id"), "state": blocking.get("state"),
               "state_words": blocking.get("state_words"), "poses": len(blocking.get("poses") or []),
               # an open note whose pose is no longer in the blocking has no row: it is said at the top of the sheet
               "orphans": [n for n in blocking.get("notes") or [] if n.get("pose") is None and n.get("state") == "open"]}
    front = any((k["reference"] or {}).get("view") == "front" for k in keys)
    return {"schema": 1, "name": name, "clip": clip_path, "rig": clip.get("rig"), "inputs": list(inputs or []),
            "blocking": blk,
            "phase_by": phase_by, "phase_note": phase_note,
            "fps": float(clip.get("fps") or round(1.0 / (clip["times"][1] - clip["times"][0]))),
            "duration": float(clip["times"][-1]), "dossier": dossier_name if dossier else None, "hits": hits,
            "keys": keys, "key_views": list(KEY_VIEWS) + (["front"] if front else []), "key_height": KEY_SIZE,
            "strip_views": list(STRIP_VIEWS) if strips else [], "strip_height": STRIP_SIZE, "strip_rate": STRIP_RATE,
            # (a blocking's strip also holds every pose's OWN frame: a pose held under 1/12 s is rendered too)
            "strip_frames": (sorted(set(strip_frames(clip)) | ({int(p["frame"]) for p in blocking.get("poses") or []}
                                                               if blocking else set())) if strips else [])}


# ---------------------------------------------------------------- drawing (PIL: the system python, never Blender's)
_FONTS = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in _FONTS:
        from PIL import ImageFont
        names = (("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
                 if bold else ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        f = None
        for n in names:
            try:
                f = ImageFont.truetype(n, size)
                break
            except OSError:
                continue
        _FONTS[key] = f or ImageFont.load_default(size)
    return _FONTS[key]


def wrap(text, fnt, width):
    lines, line = [], ""
    for word in str(text).split():
        trial = (line + " " + word).strip()
        if fnt.getlength(trial) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def stroke(draw, pts, colour, width=3, alpha=255):
    """a line that reads on a grey floor and a light sky: dark under it, the colour on top"""
    pts = [(float(x), float(y)) for x, y in pts]
    if len(pts) < 2:
        return
    draw.line(pts, fill=INK + (min(alpha, 230),), width=width + 3, joint="curve")
    draw.line(pts, fill=tuple(colour) + (alpha,), width=width, joint="curve")


def dot(draw, xy, r, fill, rim=INK, rim_w=2):
    x, y = float(xy[0]), float(xy[1])
    draw.ellipse([x - r, y - r, x + r, y + r], fill=tuple(fill) + (255,), outline=tuple(rim) + (255,), width=rim_w)


def label(draw, xy, text, fnt, fill=(255, 255, 255), pad=6, box=BAR, alpha=215):
    """text on its own dark plate (a caption inside a render)"""
    x, y = xy
    w, h = fnt.getlength(text), fnt.size
    draw.rectangle([x, y, x + w + 2 * pad, y + h + 2 * pad], fill=tuple(box) + (alpha,))
    draw.text((x + pad, y + pad - 2), text, font=fnt, fill=tuple(fill) + (255,))
    return y + h + 2 * pad


def seen(pix, depth):
    """the run of projected points in front of the camera"""
    return [tuple(p) for p, dz in zip(pix, depth) if dz > 0.05]


def draw_weight(draw, cam, size, w, origin):
    """the support patch on the floor, the centre of mass, and the line that drops it to the floor"""
    if w["support"]:
        pix, depth = project(cam, to_blender(np.array(w["support"]), origin), size)
        poly = seen(pix, depth)
        col = GOOD if (w["outside"] is not None and w["outside"] <= 0.05) else OFF
        if len(poly) >= 3:
            draw.polygon(poly, fill=col + (70,), outline=col + (255,))
            draw.line(poly + [poly[0]], fill=col + (255,), width=3)
        elif len(poly) == 2:
            draw.line(poly, fill=col + (255,), width=5)
    com = np.asarray(w["com"], float)
    floor = np.array([com[0], PA.GROUND, com[2]])
    pix, depth = project(cam, to_blender(np.stack([com, floor]), origin), size)
    if depth[0] <= 0.05 or depth[1] <= 0.05:
        return
    a, b = pix[0], pix[1]
    n = max(2, int(float(np.linalg.norm(b - a)) // 12))
    for k in range(0, n, 2):                               # a dashed drop
        p, q = a + (b - a) * k / n, a + (b - a) * min(k + 1, n) / n
        draw.line([tuple(p), tuple(q)], fill=INK + (255,), width=5)
        draw.line([tuple(p), tuple(q)], fill=(255, 255, 255, 255), width=3)
    r = 7
    draw.line([b[0] - r, b[1] - r, b[0] + r, b[1] + r], fill=INK + (255,), width=5)
    draw.line([b[0] - r, b[1] + r, b[0] + r, b[1] - r], fill=INK + (255,), width=5)
    draw.line([b[0] - r, b[1] - r, b[0] + r, b[1] + r], fill=(255, 255, 255, 255), width=2)
    draw.line([b[0] - r, b[1] + r, b[0] + r, b[1] - r], fill=(255, 255, 255, 255), width=2)
    dot(draw, a, 9, (255, 255, 255), rim_w=3)
    dot(draw, a, 3, INK, rim_w=0)


def draw_key_path(draw, cam, size, path, key_frames, here, origin, colour):
    """the striker's path over the whole clip, a numbered dot where each key pose holds it; this pose's dot is white"""
    pix, depth = project(cam, to_blender(path, origin), size)
    run = []
    for p, dz in zip(pix, depth):
        if dz > 0.05:
            run.append(tuple(p))
        else:
            stroke(draw, run, colour, 4, 235)
            run = []
    stroke(draw, run, colour, 4, 235)
    fnt = font(17, True)
    for n, i in enumerate(key_frames):
        if depth[i] <= 0.05:
            continue
        mine = n == here
        r = 15 if mine else 11
        dot(draw, pix[i], r, (255, 255, 255) if mine else colour, rim_w=3 if mine else 2)
        s = str(n + 1)
        draw.text((float(pix[i][0]) - fnt.getlength(s) / 2, float(pix[i][1]) - fnt.size / 2 - 3), s, font=fnt, fill=INK + (255,))


def draw_strip_paths(draw, cam, size, pth, ticks, here, origin):
    """every path over the whole clip, a small dot on each strip frame (their gaps are the speed), a large one now;
    the blade itself as a line from the grip to the tip (light steel on a grey floor was hard to find at this size)"""
    if "Grip" in pth and "BladeTip" in pth:
        pix, depth = project(cam, to_blender(np.stack([pth["Grip"][here], pth["BladeTip"][here]]), origin), size)
        if depth[0] > 0.05 and depth[1] > 0.05:
            stroke(draw, [tuple(pix[0]), tuple(pix[1])], (250, 250, 252), 2, 255)
    for name, colour in PATH_COLOUR.items():
        if name not in pth:
            continue
        pix, depth = project(cam, to_blender(pth[name], origin), size)
        stroke(draw, seen(pix, depth), colour, 2, 170)
        for i in ticks:
            if depth[i] > 0.05:
                dot(draw, pix[i], 3, colour, rim_w=1)
        if depth[here] > 0.05:
            dot(draw, pix[here], 7, colour, rim=(255, 255, 255), rim_w=2)


def overlay(render_path, painter):
    from PIL import Image, ImageDraw
    im = Image.open(render_path).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    painter(ImageDraw.Draw(ov), im.size)
    return Image.alpha_composite(im, ov).convert("RGB")


def reference_image(ref):
    """the reference frame itself: a video's frame at t (cv2, as compare.footage_frame reads it) or a still; cropped to
    `crop` and mirrored on `flip` -> a PIL image, or None when it cannot be read"""
    from PIL import Image, ImageOps
    path = ref.get("path") or ref.get("video") or ref.get("image")
    try:
        if ref.get("video"):
            import compare as CP
            arr = CP.footage_frame(path, float(ref.get("t", 0.0)), h=None)
            if arr is None:
                return None
            im = Image.fromarray(np.ascontiguousarray(arr))
        else:
            im = Image.open(path).convert("RGB")
    except (OSError, ValueError, ImportError):
        return None
    crop = ref.get("crop")
    if isinstance(crop, (list, tuple)) and len(crop) == 4:
        x0, y0, x1, y1 = (min(max(float(v), 0.0), 1.0) for v in crop)
        if x1 - x0 > 0.01 and y1 - y0 > 0.01:
            im = im.crop((int(x0 * im.width), int(y0 * im.height), int(x1 * im.width), int(y1 * im.height)))
    if ref.get("flip"):
        im = ImageOps.mirror(im)
    return im


def reference_pane(key, dossier_name, size=KEY_SIZE):
    """the pane a key pose is looked at beside: its phase's reference frame, as large as the pane holds - or, with
    none, the gap SAID (why, the dossier's own words for the phase, how one is added) so a thin source is seen"""
    from PIL import Image, ImageDraw
    pane = Image.new("RGB", (size, size), (24, 25, 30))
    d = ImageDraw.Draw(pane, "RGBA")
    ref, im = key.get("reference"), None
    if ref:
        im = reference_image(ref)
    if im is not None:
        room = size - 2 * 44
        k = min(size / im.width, room / im.height)
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))))
        pane.paste(im, ((size - im.width) // 2, 44 + (room - im.height) // 2))
        head = "REFERENCE"
        if ref.get("source"):
            head += f"  {ref['source']}"
        if ref.get("video"):
            head += f"  at {float(ref.get('t', 0.0)):.2f} s"
        label(d, (0, 0), head, font(20, True), fill=(255, 226, 150))
        note = ref.get("note")
        if note:
            y = size - 40
            for line in wrap(note, font(18), size - 20)[:1]:
                label(d, (0, y), line, font(18))
        return pane, True
    f_big, f = font(52, True), font(26)                       # (large: on the whole sheet this pane is a quarter its size)
    d.text((28, 30), "NO REFERENCE", font=f_big, fill=(255, 150, 45, 255))
    d.text((28, 92), "FRAME", font=f_big, fill=(255, 150, 45, 255))
    y = 180
    why = key.get("reference_gap") or ("the frame could not be read" if ref else "none")
    lines = [("why", why)]
    if key.get("phase"):
        lines.append((f"the dossier's words for '{key['phase']}'", key.get("phase_body") or "(none)"))
    if dossier_name:
        lines.append(("add one", f"assets/animations/dossiers/{dossier_name}.json -> reference_frames: "
                                 "[{phase, video, t, game_t, note}] (or image: a still); the footage: "
                                 f"lune run kit anim dossier footage {dossier_name} <clip.mp4>"))
    for head, text in lines:
        d.text((28, y), head.upper(), font=font(18, True), fill=(150, 156, 172, 255))
        y += 30
        for line in wrap(text, f, size - 56)[:6]:
            d.text((28, y), line, font=f, fill=(226, 228, 234, 255))
            y += 35
        y += 18
    return pane, False


def type_scale(width):
    """how much larger the type of a picture `width` px wide is set: a page is read at its own size, the whole sheet
    (4,000 px and more) is first seen fitted to a screen, where 22 px type would be 5 px tall"""
    return min(2.2, max(1.0, width / 2000.0))


def bar(width, text, height=46, size=22, bold=True, fill=BAR, ink=(240, 241, 245)):
    """a title bar across a picture: its type grows with the picture (type_scale), a line too long is wrapped onto the
    next (never cut: the gap, the phases' note and the legend are what the reader must not lose)"""
    from PIL import Image, ImageDraw
    k = type_scale(width)
    fnt = font(int(round(size * k)), bold)
    lines = wrap(text, fnt, width - int(24 * k)) or [""]
    step = int(round(fnt.size * 1.32))
    high = max(int(round(height * k)), step * len(lines) + int(round(12 * k)))
    im = Image.new("RGB", (width, high), fill)
    d = ImageDraw.Draw(im)
    y = (high - step * len(lines)) // 2
    for line in lines:
        d.text((int(12 * k), y), line, font=fnt, fill=ink)
        y += step
    return im


def columns_bar(columns, gap=4, fill=(46, 48, 56)):
    """the sheet's column heads, each over its own column: [(width, title, ink)] -> one bar"""
    from PIL import Image, ImageDraw
    total = sum(w for w, _, _ in columns) + gap * (len(columns) - 1)
    k = type_scale(total)
    fnt = font(int(round(24 * k)), True)
    im = Image.new("RGB", (total, int(round(50 * k))), fill)
    d = ImageDraw.Draw(im)
    x = 0
    for w, title, ink in columns:
        t = title
        while fnt.getlength(t) > w - int(24 * k) and len(t) > 6:
            t = t[:-1]
        d.text((x + int(12 * k), (im.height - int(fnt.size * 1.32)) // 2), t, font=fnt, fill=ink)
        x += w + gap
    return im


def row_of(panes, gap=4, fill=PAPER):
    from PIL import Image
    h = max(p.height for p in panes)
    out = Image.new("RGB", (sum(p.width for p in panes) + gap * (len(panes) - 1), h), fill)
    x = 0
    for p in panes:
        out.paste(p, (x, 0))
        x += p.width + gap
    return out


def stack(rows, gap=0, fill=PAPER):
    from PIL import Image
    w = max(r.width for r in rows)
    out = Image.new("RGB", (w, sum(r.height for r in rows) + gap * (len(rows) - 1)), fill)
    y = 0
    for r in rows:
        out.paste(r, (0, y))
        y += r.height + gap
    return out


NOTE_FILL = {"open": ((92, 52, 16), (255, 214, 150)), "answered": ((28, 70, 46), (190, 240, 205)),
             "closed": ((52, 54, 62), (200, 203, 214))}


def note_text(note):
    """one of the owner's notes on a blocking pose, as the sheet says it: his words, and whether the pose changed"""
    if note.get("text"):                                    # (kit/anim/blocking.py note_words: said once, there)
        return note["text"]
    who = f"THE OWNER, {note.get('date')}"
    if note.get("state") == "open" and note.get("carried"):
        return (f"{who} - NOT ANSWERED (this pose only moved with another one - {note['carried']} - its own key is as he "
                f"saw it): \"{note.get('words')}\"")
    if note.get("state") == "open":
        return f"{who} - NOT ANSWERED (this pose is as he saw it): \"{note.get('words')}\""
    if note.get("state") == "answered":
        a = note.get("answered") or {}
        return f"{who}: \"{note.get('words')}\" - ANSWERED {a.get('date')}: {a.get('changed')}"
    return f"{who}: \"{note.get('words')}\" - closed by his yes"


def note_bars(key, width):
    """the bars under a blocking pose's title: every note the owner gave on that pose (none = no bar)"""
    out = []
    for note in key.get("notes") or []:
        fill, ink = NOTE_FILL.get(note.get("state"), NOTE_FILL["closed"])
        out.append(bar(width, note_text(note), height=40, size=19, bold=note.get("state") == "open", fill=fill, ink=ink))
    return out


def key_title(key, n, w, facts, hits):
    bits = [f"KEY {key['k']} of {n}", f"t = {key['t']:.2f} s (frame {key['frame']})"]
    if key.get("hold_s") is not None:                       # a blocking: the pose is HELD this long (its rhythm)
        bits[0] = f"POSE {key['k']} of {n}"
        bits.append(f"held {key['hold_s']:.2f} s")
    if key.get("phase"):
        bits.append(f"phase: {key['phase']}")
    if any(abs(h - key["t"]) < 0.026 for h in hits):
        bits.append("the HIT")
    bits.append(weight_words(w))
    if facts.get("blade_seen_game_pct") is not None:
        bits.append(f"blade seen from the game camera {facts['blade_seen_game_pct']:.0f} %")
    return "   |   ".join(bits)


# ---------------------------------------------------------------- the pages
def look_line(m):
    """one line for a build's summary: where its pictures are and what must be looked at (the 3D lane's
    rbx_judgeviews.say, for a move)"""
    if not m:
        return ""
    n, have = len(m.get("keys") or []), int((m.get("reference") or {}).get("have", 0))
    text = (f"LOOK: {m['folder']}/ - pose_sheet.png ({n} key pose(s) from {', '.join(m.get('key_views') or [])}, "
            f"{m.get('key_size', KEY_SIZE)} px each")
    if m.get("dossier"):
        text += f", beside {have} of {n} reference frame(s) of dossier {m['dossier']}"
    else:
        text += "; no move dossier, so nothing to look at them beside"
    text += ")"
    if m.get("strips"):
        text += (f" + {', '.join(s['file'] for s in m['strips'])} ({m.get('strip_rate', STRIP_RATE)} frames a second, "
                 f"{m.get('strip_height', STRIP_SIZE)} px a frame, the paths drawn)")
    text += "; open keys/key_*.png for every pose at full size"
    tm = m.get("timing")
    if tm and tm.get("file"):
        text += f"; {tm['file']} = the timing chart ({tm.get('words')})"
    elif tm:
        text += f"; NO timing chart: {tm.get('words')}"
    if m.get("blocking"):
        b = m["blocking"]
        text = (f"LOOK: {m['folder']}/ - BLOCKING {b.get('id')} of {b.get('of')}: its {n} key pose(s) HELD at the move's own "
                f"timing, no in-betweens ({b.get('state')}: {b.get('state_words')}) - " + text[len(f"LOOK: {m['folder']}/ - "):])
    gaps = (m.get("reference") or {}).get("gaps") or []
    if gaps:
        text += f"; NO reference frame beside {len(gaps)} key pose(s): {gaps[0]}"
    if m.get("overlays") is False:
        text += f"; nothing is drawn on the renders ({m.get('overlays_why')})"
    elif m.get("overlay_error_studs") is not None:
        text += f"; {fidelity_words(m['overlay_error_studs'])}"
    if m.get("phase_by") == "order":
        text += "; the poses' phases are counted in order round the Hit (the clip is not timed like its dossier)"
    return text


def pages(folder):
    """plan.json + render.json + frames/ -> the sheets and look.json; -> the manifest"""
    from PIL import Image, ImageDraw
    pl = json.load(open(os.path.join(folder, "plan.json"), encoding="utf-8"))
    rn = json.load(open(os.path.join(folder, "render.json"), encoding="utf-8"))
    clip = json.load(open(pl["clip"], encoding="utf-8"))
    rig = C.load_rig("r6")
    frames = C.world_frames(clip, rig)
    origin = rn["origin"]
    pth = paths(clip, frames)
    fps = pl["fps"]
    who = striker(pth, fps)
    off = rn.get("overlay_error_studs")
    draw_on = off is not None and off <= OVERLAY_TOLERANCE
    why_not = None if draw_on else (f"the kit's FK and the rig's meshes differ by {off} studs: a hand-posed file"
                                    if off is not None else "the render gave no FK check")
    keys = pl["keys"]
    n = len(keys)
    key_frames = [k["frame"] for k in keys]
    high = int(pl.get("key_height", KEY_SIZE))            # every key pane's height; its width is its view's own
    appeal = {}
    try:
        rep = PA.report(clip, {"keys": [{"t": k["t"]} for k in keys]})
        appeal = {i: r for i, r in enumerate(rep.get("keys") or [])}
    except Exception:                                   # the appeal numbers are a caption, never a reason to fail a look
        appeal = {}
    fdir = os.path.join(folder, "frames")
    os.makedirs(os.path.join(folder, "keys"), exist_ok=True)
    rows, page_list, key_rows, gaps = [], [], [], []
    have = 0
    with_ref = bool(pl.get("dossier"))
    for ki, key in enumerate(keys):
        i = key["frame"]
        w = weight(frames[i], rig)
        cells = {}
        for view in pl["key_views"]:
            cam = rn["key"]["cams"][view][str(i)]

            def paint(d, size, cam=cam, w=w, ki=ki):
                if draw_on:
                    draw_weight(d, cam, size, w, origin)
                    draw_key_path(d, cam, size, pth[who], key_frames, ki, origin, PATH_COLOUR.get(who, (255, 214, 40)))
                label(d, (0, 0), VIEW_TITLE[view], font(20, True))

            cells[view] = overlay(os.path.join(fdir, f"key_{view}_{i:04d}.png"), paint)
        # a move WITH a dossier is looked at beside its reference (or beside the gap, said); a clip with no dossier
        # at all (a library clip) has nothing to stand beside: no empty column
        ref_pane, shown = (reference_pane(key, pl.get("dossier"), high) if with_ref else (None, False))
        if shown:
            have += 1
        elif with_ref:
            gaps.append(f"key {key['k']} ({key.get('phase') or 'no phase'}): {key.get('reference_gap') or 'the frame could not be read'}")
        title = key_title(key, n, w, appeal.get(ki, {}), pl.get("hits") or [])
        panes = ([ref_pane] if with_ref else []) + [cells[v] for v in pl["key_views"]]
        full = row_of(panes)
        rows.append(stack([bar(full.width, title)] + note_bars(key, full.width) + [full]))
        # the same panes a few at a time: what a session opens at full size. The reference stays BESIDE the view it
        # was filmed like (the player's camera unless its frame says); the other views share a page while two fit
        # in the width a picture is read at without being shrunk
        beside = (key.get("reference") or {}).get("view") or "player"
        if beside not in cells:
            beside = "player"
        stem = f"key_{key['k']:02d}_{key['t']:.2f}s".replace(".", "p")
        groups, group = ([["reference", beside]], []) if with_ref else ([], [beside])
        for v in [v for v in pl["key_views"] if v != beside]:
            if group and sum(cells[g].width + 4 for g in group) + cells[v].width > PAGE_WIDTH:
                groups.append(group)
                group = []
            group.append(v)
        if group:
            groups.append(group)
        made = []
        for g in groups:
            body = row_of([ref_pane if v == "reference" else cells[v] for v in g])
            g_name = f"keys/{stem}_{'_'.join(g)}.png"
            stack([bar(body.width, title)] + note_bars(key, body.width) + [body]).save(os.path.join(folder, g_name))
            made.append({"file": g_name, "shows": f"key {key['k']} at {key['t']:.2f} s: "
                                                  + " | ".join("its reference frame" if v == "reference" else v for v in g)})
        page_list += made
        key_rows.append({"k": key["k"], "t": key["t"], "frame": i, "phase": key.get("phase"), "reference": bool(shown),
                         **({"hold_s": key["hold_s"], "notes": key.get("notes") or []} if key.get("hold_s") is not None else {}),
                         "reference_gap": None if (shown or not with_ref) else (key.get("reference_gap") or "the frame could not be read"),
                         "weight_outside_studs": w["outside"], "feet_down": w["down"], "pages": [p["file"] for p in made],
                         **{k2: appeal.get(ki, {}).get(k2) for k2 in ("line_of_action_deg", "blade_seen_game_pct", "silhouette_pct")
                            if appeal.get(ki, {}).get(k2) is not None}})
    width = rows[0].width if rows else 4 * high
    head = [bar(width, (f"{pl['name']} - its key poses, large, beside the reference (dossier {pl['dossier']}: {have} of {n} "
                        "key poses have a reference frame)" if with_ref else
                        f"{pl['name']} - its key poses, large (a clip with no move dossier: nothing to look at it beside)"),
                height=58, size=28),
            bar(width, (f"drawn on the renders: the {PATH_NAME.get(who, who)}'s path through the keys (a numbered dot per key, "
                        "this pose's in white)  |  the white dot = the centre of mass, dropped to the floor (x)  |  the patch = "
                        "the feet's support: green = the weight over it, orange = outside it" if draw_on
                        else f"NOTHING is drawn on the renders: {why_not}"),
                height=38, size=18, bold=False, fill=(46, 48, 56))]
    blk = pl.get("blocking")
    if blk:                                                 # a BLOCKING: say so first, then where the owner's answer stands
        head.insert(0, bar(width, f"BLOCKING of {blk.get('of')} (id {blk.get('id')}) - its {n} key poses HELD at the move's "
                                  "own timing, NO in-betweens: are these the right poses, in the right rhythm?", height=58, size=28,
                           fill=(30, 44, 74)))
        fill, ink = {"approved": NOTE_FILL["answered"], "notes open": NOTE_FILL["open"],
                     "stale": NOTE_FILL["open"]}.get(blk.get("state"), NOTE_FILL["closed"])
        head.insert(1, bar(width, f"{str(blk.get('state')).upper()}: {blk.get('state_words')}", height=40, size=19, bold=False,
                           fill=fill, ink=ink))
        for at, note in enumerate(blk.get("orphans") or []):
            head.insert(2 + at, bar(width, note_text(note), height=40, size=19, bold=True, fill=NOTE_FILL["open"][0],
                                    ink=NOTE_FILL["open"][1]))
    if pl.get("phase_note"):
        head.append(bar(width, f"PHASES: {pl['phase_note']}", height=38, size=18, bold=False, fill=(70, 52, 30), ink=(255, 226, 170)))
    if keys:                                                # each column named over itself, large: the panes' own labels
        cols = ([(high, "ITS REFERENCE", (255, 226, 150))] if with_ref else [])                                 # are small
        cols += [(rn["key"]["size"][v][0], VIEW_TITLE[v], (232, 233, 238)) for v in pl["key_views"]]
        head.append(columns_bar(cols))
    sheet = stack(head + rows, gap=6)
    sheet.save(os.path.join(folder, "pose_sheet.png"))
    # the strips: one camera per view for the whole strip, 12 frames a second
    strips = []
    sframes = pl.get("strip_frames") or []
    if sframes and pl.get("strip_views") and rn.get("strip"):
        os.makedirs(os.path.join(folder, "strips"), exist_ok=True)
        hit_at = {min(sframes, key=lambda f: abs(f / fps - h)) for h in pl.get("hits") or []}
        legend = "  |  ".join(PATH_NAME[k] for k in PATH_COLOUR if k in pth)
        for view in pl["strip_views"]:
            ssize = tuple(rn["strip"]["size"][view])
            cells = []
            for i in sframes:
                cam = rn["strip"]["cams"][view][str(i)]

                def paint(d, size, cam=cam, i=i):
                    if draw_on:
                        draw_strip_paths(d, cam, size, pth, sframes, i, origin)
                    tag = f"{i / fps:.2f} s"
                    ks = [str(k["k"]) for k in keys if abs(k["frame"] - i) <= max(1, int(round(fps / STRIP_RATE / 2)))]
                    if ks:
                        tag += "  key " + ",".join(ks)
                    if i in hit_at:
                        tag += "  HIT"
                    label(d, (0, 0), tag, font(18, True), fill=(255, 226, 150) if i in hit_at else (255, 255, 255))

                cells.append(overlay(os.path.join(fdir, f"strip_{view}_{i:04d}.png"), paint))
            per = max(1, (2 * PAGE_WIDTH) // (ssize[0] + 4))    # the whole strip: rows about two pages wide
            body = stack([row_of(cells[j:j + per]) for j in range(0, len(cells), per)], gap=4)
            top = bar(body.width, f"{pl['name']} - {VIEW_TITLE[view]} - {pl['strip_rate']} frames a second, "
                                  f"one camera" + (" (a blocking: plus every pose's own frame)" if pl.get("blocking") else ""),
                      height=44)
            key_bar = _legend(body.width, [k for k in PATH_COLOUR if k in pth], draw_on, why_not, off)
            name = f"strip_{view}.png"
            stack([top, key_bar, body]).save(os.path.join(folder, name))
            pg = []
            each = max(1, PAGE_WIDTH // (ssize[0] + 4))         # a page: the frames that stay full size when opened
            for p, j in enumerate(range(0, len(cells), each)):
                part = row_of(cells[j:j + each])
                pname = f"strips/strip_{view}_{p + 1:02d}.png"
                stack([bar(part.width, f"{pl['name']} - {view} - {sframes[j] / fps:.2f} s to "
                                       f"{sframes[min(j + each - 1, len(sframes) - 1)] / fps:.2f} s  ({legend})", height=36, size=17),
                       part]).save(os.path.join(folder, pname))
                pg.append(pname)
            strips.append({"file": name, "view": view, "frames": len(cells), "frame_size": list(ssize), "pages": pg})
    # the TIMING CHART (kit/anim/timing_chart.py): the spacing of the striker frame by frame with this sheet's key
    # poses and the Hit marked, and its reading in words - on every sheet, so no look is taken without it
    timing = None
    chart_png = os.path.join(folder, "timing.png")
    try:
        import timing_chart as TC
        marks = [float(k["t"]) for k in keys]
        reading = TC.read(clip, None, marks)
        if not reading.get("still"):
            TC.chart(clip, marks, chart_png)
            timing = {"file": "timing.png", "words": TC.words(reading), "reading": reading}
        else:
            timing = {"file": None, "words": reading["still"], "reading": reading}
    except Exception as e:                              # said, never silent: a sheet without its chart names why
        timing = {"file": None, "words": f"the timing chart could not be drawn ({type(e).__name__}: {e})", "reading": None}
    if timing["file"] is None and os.path.isfile(chart_png):
        os.remove(chart_png)                            # (never an older run's chart beside a sheet that has none)
    m = {"schema": 1, "name": pl["name"], "folder": folder.replace(os.sep, "/"), "dossier": pl.get("dossier"),
         "timing": timing,
         "sheet": "pose_sheet.png", "sheet_size": list(sheet.size), "key_views": pl["key_views"], "key_size": high,
         "key_panes": {v: list(rn["key"]["size"][v]) for v in pl["key_views"]},
         "keys": key_rows, "pages": page_list, "strips": strips, "strip_rate": pl.get("strip_rate"),
         "strip_height": pl.get("strip_height"), "striker": who, "overlays": bool(draw_on), "overlays_why": why_not,
         "overlay_error_studs": off, "projection_error_px": rn.get("projection_error_px"),
         "fidelity": rn.get("fidelity"), "reference": {"have": have, "of": n, "gaps": gaps},
         "phase_by": pl.get("phase_by"), "phase_note": pl.get("phase_note"), "blocking": pl.get("blocking"),
         "how_to_read": "pose_sheet.png is the whole move on one sheet (the owner's); keys/ holds its panes two at a "
                        "time and strips/ the strips three frames a page: those are opened at full size"}
    m["look"] = look_line(m)
    # what this sheet was made from: an input that changes makes it stale (kit/cmd/anim.luau AnimCmd.sheetState)
    made_from = [p for p in pl.get("inputs") or [] if os.path.isfile(p)]
    if made_from:
        m["inputs"], m["inputs_sha256"] = made_from, inputs_hash(made_from)
    m["reference_files"] = {k["reference_file"]: os.path.isfile(k["reference_file"]) for k in keys
                            if isinstance(k.get("reference_file"), str)}
    with open(os.path.join(folder, "look.json"), "w", encoding="utf-8") as fh:
        json.dump(m, fh, indent=1)
    return m


def fidelity_words(off):
    """how far the rig drawn is from the clip measured (the kit's FK against the rig's meshes, studs) - the sheet's
    fidelity line (the owner's V3 list, anim stage A.3; card 6wyz): what a reader trusts the drawn paths to"""
    if off is None:
        return "the rig drawn was not measured against the clip"
    return f"the rig drawn = the clip within {float(off):.3f} studs"


def _legend(width, names, draw_on, why_not, off=None):
    """a strip's key: each path's colour and name, set as large as the strip's own type (type_scale), and how faithful
    the rig drawn is to the clip"""
    from PIL import Image, ImageDraw
    if not draw_on:
        return bar(width, f"NOTHING is drawn on the renders: {why_not}", height=36, size=18, bold=False,
                   fill=(46, 48, 56), ink=(255, 150, 45))
    k = type_scale(width)
    f = font(int(round(18 * k)))
    im = Image.new("RGB", (width, int(round(36 * k))), (46, 48, 56))
    d = ImageDraw.Draw(im)
    x, r, y = int(12 * k), int(7 * k), (im.height - int(f.size * 1.32)) // 2
    for name in names:
        d.ellipse([x, im.height // 2 - r, x + 2 * r, im.height // 2 + r], fill=PATH_COLOUR[name], outline=INK)
        d.text((x + 2 * r + int(6 * k), y), PATH_NAME[name], font=f, fill=(232, 233, 238))
        x += 2 * r + int(6 * k) + int(f.getlength(PATH_NAME[name])) + int(26 * k)
    d.text((x, y), "- a path over the whole clip; a small dot on every strip frame (wide gaps = fast); the large dot = now"
           f" | {fidelity_words(off)}", font=f, fill=(170, 174, 188))
    return im


# ---------------------------------------------------------------- the command line
def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) < 2 or argv[0] not in ("plan", "pages"):
        return emit("fail", "pose_sheet: plan <Name> --out <dir> | pages <dir>", "lune run kit anim sheet <Name>")
    if argv[0] == "plan":
        name = argv[1]
        build = os.path.join(os.environ.get("KIT_BUILD", "build"), "animations")
        anims = flag(argv, "--anims", os.path.join("assets", "animations"))
        out = flag(argv, "--out", os.path.join(build, f"{name}.sheet"))
        clip_path = flag(argv, "--clip")
        if not clip_path:
            r6 = os.path.join(build, f"{name}.r6.clip.json")
            clip_path = r6 if os.path.isfile(r6) else os.path.join(build, f"{name}.clip.json")
        if not os.path.isfile(clip_path):
            return emit("fail", f"anim sheet {name}: no built clip ({clip_path})", f"lune run kit anim {name}")
        clip = json.load(open(clip_path, encoding="utf-8"))
        if clip.get("rig") != "R6":
            return emit("fail", f"anim sheet {name}: {clip_path} is a {clip.get('rig')} clip - the sheet is rendered on the owner's R6 rig",
                        f"lune run kit anim {name}   (it writes the R6 fold: {name}.r6.clip.json)")
        if len(clip.get("times") or []) < 2:
            return emit("fail", f"anim sheet {name}: the clip has no frames", f"lune run kit anim {name}")
        move_path = flag(argv, "--move", os.path.join(anims, f"{name}.move.json"))
        move = None
        if os.path.isfile(move_path):
            try:
                move = json.load(open(move_path, encoding="utf-8"))
            except ValueError:
                move = None
        dname, dossier = dossier_of(name, move, anims, flag(argv, "--dossier"), clip)
        made_from = [clip_path] + ([move_path] if move is not None else [])
        if dossier is not None:
            made_from.append(os.path.join(anims, "dossiers", f"{dname}.json"))
        made_from += [os.path.join("kit", "anim", "pose_sheet.py"), os.path.join("kit", "anim", "look_r6.py"),
                      os.path.join("kit", "anim", "timing_chart.py")]
        blocking = None
        if flag(argv, "--blocking"):                         # a blocking's manifest (kit/anim/blocking.py make)
            try:
                with open(flag(argv, "--blocking"), encoding="utf-8") as fh:
                    blocking = json.load(fh)
            except (OSError, ValueError) as e:
                return emit("fail", f"anim sheet {name}: the blocking manifest could not be read ({e})",
                            f"lune run kit anim block {name} --sheet")
            made_from.append(flag(argv, "--blocking"))
        pl = plan(name, clip, move, dname, dossier, strips="--no-strips" not in argv, clip_path=clip_path.replace(os.sep, "/"),
                  inputs=[p.replace(os.sep, "/") for p in made_from if os.path.isfile(p)], blocking=blocking)
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "plan.json"), "w", encoding="utf-8") as fh:
            json.dump(pl, fh, indent=1)
        refs = sum(1 for k in pl["keys"] if k["reference"])
        return emit("pass", f"anim sheet {name}: {len(pl['keys'])} key pose(s), {len(pl['strip_frames'])} strip frame(s), "
                            f"{refs} reference frame(s) of dossier {pl['dossier']}" if pl["dossier"] else
                            f"anim sheet {name}: {len(pl['keys'])} key pose(s), {len(pl['strip_frames'])} strip frame(s), no move dossier",
                    "the owner's rig is rendered next (kit/anim/look_r6.py --sheet)", plan=os.path.join(out, "plan.json").replace(os.sep, "/"))
    folder = argv[1]
    for need in ("plan.json", "render.json"):
        if not os.path.isfile(os.path.join(folder, need)):
            return emit("fail", f"anim sheet: no {need} in {folder}", "lune run kit anim sheet <Name>")
    t0 = time.time()
    m = pages(folder)
    return emit("pass", f"anim sheet {m['name']}: {len(m['keys'])} key pose(s) x {len(m['key_views'])} view(s) at {m['key_size']} px"
                        f" + {len(m['strips'])} strip(s) in {time.time() - t0:.1f} s - {m['look']}",
                f"look at {m['folder']}/pose_sheet.png, then every keys/key_*.png at full size: does each pose read as its "
                "phase's reference, is the weight over the feet, does the path run clean through the keys?",
                look=m["look"], folder=m["folder"], sheet=f"{m['folder']}/pose_sheet.png",
                reference=m["reference"], pages=len(m["pages"]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
