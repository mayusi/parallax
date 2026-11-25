"""collide.py — THE BODY AND THE WEAPON DO NOT PASS THROUGH THE BODY (the owner's limitations list 2026-11-15, A-R05 /
AN-24: "comprehensive swept self / body / weapon collision repair was not found in the animation gate routes").

    python kit/anim/collide.py <clip.json>            the reading: how deep, where, at which frame
    python kit/anim/collide.py freeze <built clips folder> --out <anims>/blocks/_collide_before.json

WHAT IS MEASURED, on the R6 clip, SWEPT (between two frames the parts are carried in small steps, so a blade that is
on one side of the torso at one frame and on the other at the next is caught on its way through):
  the weapon    points along its line, from past the hands to the tip, against every body block: Torso, Head, both
                legs, and an arm that does not hold it. Depth = how far inside the block the point is (studs).
  the hands     the hand end of each arm against Torso, Head and the legs (and, said but never judged, the other arm).
  the feet      the foot end of each leg against the other leg and the Torso.
An R6 body is six blocks that overlap at their joints by construction, and a two-handed grip folds both arms into the
chest: SOME depth is the rig, not a fault. THE BARS are set from what the owner's loved cuts measure (the table in
kit/selftest/anim/collide/run.py prints it) - they catch a blade or a hand that goes THROUGH the body, they do not
ask for a body that never touches itself.

INTENTIONAL CONTACT (a hand on the chest, a blade sheathed at the hip, a kick caught on the other shin): the clip says
it and the pair is not judged there -
    "contact": [{"a": "weapon" | "<part>", "b": "<part>", "from": seconds, "to": seconds}]      (from / to optional)
A contact that names a part the rig does not have is a problem (a typo would excuse nothing and say nothing).

THE GATE (kit/anim/metrics.py, in every build): a clip over a bar FAILS, named, with the frame; a clip made before
the rule (frozen once: <anims>/blocks/_collide_before.json) is said, never failed.
REPAIR: kit/anim/collide_repair.py ({"op": "clear"} in a derive recipe) moves a hand, a foot or a one-handed blade
out, inside bounds, and refuses what it must not touch (an arm that holds the weapon, a two-handed blade).
NOT JUDGED: the weapon behind its grip (a pommel, a spear's butt), a loop's seam, and the body's blocks between two
frames are turned about their own middles (not about their joints: a limb's swept path is a little inside the true one)."""
import datetime
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

BEFORE = "_collide_before.json"
STEP = 0.25          # studs the fastest point may move between two swept samples
MAX_SUB = 64         # swept samples between two frames at most (a tip at 6 studs a frame needs 24)
PAST_HANDS = 0.6     # studs of the weapon's line past its grip that are in the hands (not judged)
EVERY = 0.2          # studs between the judged points of the weapon's line
HOLD = 0.35          # studs from a hand to the weapon's line for that arm to be holding it
HANDLE = 1.0         # studs of the weapon's line BEHIND its grip point a holding hand can be on (ahead: up to the tip)
NEAR_HAND = 0.6      # studs of the weapon's line either side of a holding hand that are IN that hand (not judged)
END = 0.9            # studs from an arm's / a leg's joint centre to its hand / foot end (the block is 2 long)
BODY = ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")
# THE BARS (studs inside a block; a block is 1 stud thin, so a point at its very middle reads 0.5: the most there is).
# Measured 2026-11-15 on the seven loved cuts (kit/selftest/anim/faults/loved): the weapon's worst depth in any block
# 0.00; a hand's worst in the Torso 0.22 (GsCombo4Underhip), in the Head 0.22 (GsCombo3Overhead: the hands pass the
# head), in a leg 0.11; a foot's 0.00. (Two hands on one weapon sit INSIDE each other's arm block, 0.19 to 0.47 on
# every loved cut: a hand in the OTHER ARM is not judged while both arms hold the weapon.) A bar is the loved worst
# plus room. The three REJECTED cuts read 0.00 everywhere: they were rejected for other faults - this check does not
# tell loved from rejected, it catches a kind of fault none of the ten has.
# hand_arm: a hand in the other arm - not judged at all while both arms hold one weapon (the grip itself); else only
# near the block's very middle (clasped hands, a clap and an unarmed copy of a two-handed pose read up to 0.35)
BARS = {"weapon": 0.2, "hand_torso": 0.35, "hand": 0.35, "foot": 0.25, "hand_arm": 0.45}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _depth(points, M, half, inv=None):
    """how far inside the block (4x4 M, half sizes) each world point is: 0 outside, else the distance to its nearest
    face -> [n]. `inv`: M's inverse when the caller already has it (read() inverts each block once per sample: the
    repair's search calls read() thousands of times, and inverting each block for every point set was a third of it)"""
    if inv is None:
        inv = np.linalg.inv(M)
    local = (inv[:3, :3] @ points.T).T + inv[:3, 3]
    room = np.asarray(half)[None, :] - np.abs(local)
    return np.where((room > 0).all(axis=1), room.min(axis=1), 0.0)


def _between(A, B, u, q=None):
    """a block carried the share u from frame A to frame B (4x4 each): the turn the short way, the place in a line.
    `q`: the two frames' quaternions when the caller has them (read() takes them once per frame pair, not once per
    swept sample)"""
    import clip as C
    qa, qb = q if q is not None else (C.mat_quat(A[:3, :3]), C.mat_quat(B[:3, :3]))
    M = np.eye(4)
    M[:3, :3] = C.quat_mat(C.slerp(qa, qb, u))
    M[:3, 3] = A[:3, 3] * (1 - u) + B[:3, 3] * u
    return M


def contacts(clip, parts):
    """the clip's declared contacts -> [(a, b, from, to)], raising ValueError on one that cannot be read"""
    said = clip.get("contact")
    if said is None:
        return []
    if not isinstance(said, list):
        raise ValueError("\"contact\" is a list of {\"a\": \"weapon\" | \"<part>\", \"b\": \"<part>\", \"from\": s, \"to\": s}")
    out = []
    for c in said:
        if not isinstance(c, dict) or not isinstance(c.get("a"), str) or not isinstance(c.get("b"), str):
            raise ValueError("a contact names its two sides: {\"a\": \"weapon\" | \"<part>\", \"b\": \"<part>\"}")
        for side in (c["a"], c["b"]):
            if side != "weapon" and side not in parts:
                raise ValueError(f"a contact names {side}, which is no part of this body ({', '.join(parts)}) and not \"weapon\"")
        a, b = c.get("from", -math.inf), c.get("to", math.inf)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v == v for v in (a, b)) or b < a:
            raise ValueError(f"the contact {c['a']} - {c['b']}: \"from\" and \"to\" are seconds, the end after the start")
        out.append((c["a"], c["b"], float(a), float(b)))
    return out


def _meant(said, a, b, t):
    return any(({x, y} == {a, b}) and f <= t <= to for x, y, f, to in said)


def read(clip):
    """-> {"frames", "fps", "weapon": bool, "worst": {kind: {"depth", "frame", "a", "b"}}, "pairs": {"a|b": depth}}
    kind: weapon / hand_torso / hand / foot. Raises ValueError on a clip that cannot be read"""
    import clip as C
    import pose_sheet as PS
    if clip.get("rig") != "R6":
        raise ValueError(f"it is a {clip.get('rig')} clip - the body is read on the R6 clip")
    rig = C.load_rig("r6")
    W = C.world_frames(clip, rig)
    n = len(W)
    root = clip.get("root")
    if isinstance(root, list) and root and len(root) != n:       # (the body would be read without it, the blade with it)
        raise ValueError(f"its root track has {len(root)} frame(s) and the clip {n}")
    fps = C.clip_fps(clip)
    times = clip.get("times") if isinstance(clip.get("times"), list) and len(clip["times"]) == n else [i / fps for i in range(n)]
    half = {p: np.array(rig["sizes"][p], float) / 2 for p in BODY}
    said = contacts(clip, BODY)
    paths = PS.paths(clip, W)
    armed = "Grip" in paths and "BladeTip" in paths
    worst = {k: {"depth": 0.0, "frame": 0, "a": None, "b": None} for k in BARS}
    pairs = {}

    def note(kind, a, b, depth, frame):
        if depth > pairs.get(f"{a}|{b}", 0.0):
            pairs[f"{a}|{b}"] = depth
        if depth > worst[kind]["depth"]:
            worst[kind] = {"depth": depth, "frame": frame, "a": a, "b": b}

    def ends(M, part):                                           # the hand / foot end of a limb's block, in the world
        return (M[part] @ np.array([0.0, -END, 0.0, 1.0]))[:3]

    for i in range(n):
        j = min(i + 1, n - 1)
        # how many swept samples this frame pair needs: the fastest judged point moves STEP at most between two
        move = 0.0
        if armed and j != i:
            move = max(move, float(np.linalg.norm(paths["BladeTip"][j] - paths["BladeTip"][i])))
        for limb in ("Right Arm", "Left Arm", "Right Leg", "Left Leg"):
            if j != i:
                move = max(move, float(np.linalg.norm(ends(W[j], limb) - ends(W[i], limb))))
        subs = 1 if j == i else int(min(MAX_SUB, max(1, math.ceil(move / STEP))))
        # (each block's two quaternions, once per frame pair: every swept sample between them slerps the same two)
        quats = {p: (C.mat_quat(W[i][p][:3, :3]), C.mat_quat(W[j][p][:3, :3])) for p in BODY} if subs > 1 else {}
        for k in range(subs):
            u = k / subs
            t = times[i] + u * (times[j] - times[i])
            M = W[i] if k == 0 else {p: _between(W[i][p], W[j][p], u, quats[p]) for p in BODY}
            Minv = {}

            def depth(points, part):                       # (each block inverted once per sample)
                if part not in Minv:
                    Minv[part] = np.linalg.inv(M[part])
                return _depth(points, M[part], half[part], Minv[part])

            holding = set()
            if armed:
                g = paths["Grip"][i] * (1 - u) + paths["Grip"][j] * u
                # the blade is carried ROUND between the two frames (its direction turned the short way, its length
                # eased): moved in a straight line, a tip that swings half a turn would pass through the grip
                d0, d1 = paths["BladeTip"][i] - paths["Grip"][i], paths["BladeTip"][j] - paths["Grip"][j]
                l0, l1 = float(np.linalg.norm(d0)), float(np.linalg.norm(d1))
                length = l0 * (1 - u) + l1 * u
                if length > PAST_HANDS + 1e-6 and l0 > 1e-9 and l1 > 1e-9:
                    a0, a1 = d0 / l0, d1 / l1
                    w = float(np.arccos(np.clip(np.dot(a0, a1), -1.0, 1.0)))
                    if w < 1e-6 or abs(w - math.pi) < 1e-6:
                        ax = a0 * (1 - u) + a1 * u
                    else:
                        ax = (math.sin((1 - u) * w) * a0 + math.sin(u * w) * a1) / math.sin(w)
                    ax = ax / max(float(np.linalg.norm(ax)), 1e-9)
                    along = np.arange(PAST_HANDS, length + 1e-9, EVERY)
                    pts = g[None, :] + along[:, None] * ax[None, :]
                    held = {}                                    # a holding arm -> where along the line its hand is
                    for arm, hand in (("Right Arm", "RightHand"), ("Left Arm", "LeftHand")):
                        h = paths[hand][i] * (1 - u) + paths[hand][j] * u
                        # (anywhere from HANDLE behind the grip point to the TIP: a hand along the blade - a half-sword
                        # block, a hand 2.5 studs up a greatsword - holds it. Kept to HANDLE either side until the one
                        # review of the repair, 2026-11-15: such a hand read "nobody holds" and the blade through its
                        # own arm was failed)
                        at = float(np.clip(np.dot(h - g, ax), -HANDLE, length))
                        if float(np.linalg.norm(h - (g + at * ax))) <= HOLD:
                            held[arm] = at
                    holding = set(held)
                    for part in BODY:
                        if _meant(said, "weapon", part, t):
                            continue
                        # (the arm that holds it: only the stretch of the line IN that hand is left out - the rest
                        # of the blade through its own forearm is judged like any other block)
                        judged = pts[np.abs(along - held[part]) > NEAR_HAND] if part in held else pts
                        if len(judged):
                            note("weapon", "weapon", part, float(depth(judged, part).max()), i)
            for arm, other in (("Right Arm", "Left Arm"), ("Left Arm", "Right Arm")):
                p = ends(M, arm)[None, :]
                for part in ("Torso", "Head", "Right Leg", "Left Leg", other):
                    if part == other and len(holding) == 2:      # (two hands on one weapon: the grip itself)
                        continue
                    if not _meant(said, arm, part, t):
                        kind = "hand_arm" if part == other else "hand_torso" if part == "Torso" else "hand"
                        note(kind, arm, part, float(depth(p, part)[0]), i)
            for leg, other in (("Right Leg", "Left Leg"), ("Left Leg", "Right Leg")):
                p = ends(M, leg)[None, :]
                for part in ("Torso", other):
                    if not _meant(said, leg, part, t):
                        note("foot", leg, part, float(depth(p, part)[0]), i)
    for w in worst.values():
        w["depth"] = round(w["depth"], 3)
    return {"frames": n, "fps": fps, "weapon": armed, "worst": worst, "pairs": {k: round(v, 3) for k, v in sorted(pairs.items()) if v > 0}}


WORDS = {"weapon": "the weapon passes through", "hand_torso": "a hand goes into", "hand": "a hand goes into",
         "foot": "a foot goes into", "hand_arm": "a hand goes into"}


def over(r):
    """the readings over their bars -> [(kind, reading)]"""
    return [(k, w) for k, w in r["worst"].items() if w["depth"] > BARS[k]]


def words(r, name):
    bad = over(r)
    if not bad:
        return f"{name}: nothing passes through the body" + ("" if r["weapon"] else " (it carries no weapon)")
    said = []
    for kind, w in bad:
        who = "" if kind == "weapon" else f"{w['a']}: "
        said.append(f"{who}{WORDS[kind]} the {w['b']} by {w['depth']:.2f} studs at frame {w['frame']} "
                    f"({w['frame'] / r['fps']:.2f} s; at most {BARS[kind]:g})")
    return f"{name}: " + "; ".join(said)


def before(path):
    """the clips made before the rule (frozen; a project with no list has none) -> {names}"""
    if not path or not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        try:
            d = json.load(fh)
        except ValueError as e:
            raise ValueError(f"{path.replace(os.sep, '/')} is not valid JSON ({e}): repair it by hand, never delete it") from e
    clips = d.get("clips") if isinstance(d, dict) else None
    if not isinstance(clips, list):
        raise ValueError(f"{path.replace(os.sep, '/')} has no list of clips")
    return {c for c in clips if isinstance(c, str)}



def _no_list(anims, listed, tool):
    """a project that has never frozen this rule's list (the kit installed into a game that already has clips): the
    failure says how to freeze it once, so an OLD clip is not failed as if it were new"""
    path = os.path.join(anims or os.path.join("assets", "animations"), "blocks", BEFORE)
    if not listed or os.path.isfile(path):
        return ""
    return (f" [this project has no list of clips made before this rule. If THIS clip is an old one, freeze the list "
            f"ONCE - python kit/anim/{tool}.py freeze <the built clips folder> --out {path.replace(os.sep, '/')} - and "
            "read it: it takes every clip that fails today, so a NEW clip among them must be taken out of it by hand]")


def gate(clip, listed=True):
    """what the build's motion gates add for this clip (kit/anim/metrics.py) -> (the reading for metrics.json, the
    problem or None). Only an R6 clip of a character is read; one made before the rule is said, never failed; a
    contact that cannot be read is a problem. listed=False: no list is read (the freeze: what fails, list or no list)"""
    if clip.get("rig") != "R6" or clip.get("prop"):
        return None, None
    name = str(clip.get("name"))
    try:
        r = read(clip)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        return {"error": f"{type(e).__name__}: {e}"}, f"what passes through the body could not be read ({e})"
    out = {"worst": r["worst"], "pairs": r["pairs"], "bars": BARS}
    if not over(r):
        return out, None
    src = (clip.get("source") or {}).get("file") if isinstance(clip.get("source"), dict) else None
    anims = os.path.dirname(src) if isinstance(src, str) and src else os.path.join("assets", "animations")
    try:
        old = before(os.path.join(anims, "blocks", BEFORE)) if listed else set()
    except (ValueError, OSError) as e:                       # (a list that cannot be read excuses nobody)
        return out, f"the list of clips made before the pass-through rule could not be read ({e})"
    if name in old:
        out["made_before_the_rule"] = True
        return out, None
    return out, (words(r, name) + " - move it clear (a derive recipe's {\"op\": \"clear\"} does it inside bounds, or "
                 "says why it will not), or, if it is meant (a hand on the chest, a blade at the hip), say so: "
                 "\"contact\": [{\"a\": \"weapon\" | \"<part>\", \"b\": \"<part>\", \"from\": s, \"to\": s}]"
                 + _no_list(anims, listed, "collide"))


def freeze(folder, out, today=None):
    """the built clips that fail today -> the frozen list (refused when it exists)"""
    if os.path.exists(out):
        raise ValueError(f"{out.replace(os.sep, '/')} exists: the list is frozen once and never extended")
    names = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".clip.json"):
            continue
        stem = f[:-len(".clip.json")]
        if stem.endswith(".r6"):
            stem = stem[:-3]
        if "." in stem:                                       # (a preview, a tune or a polish pass: not a move's clip)
            continue
        try:
            with open(os.path.join(folder, f), encoding="utf-8") as fh:
                c = json.load(fh)
        except (OSError, ValueError):
            continue
        if isinstance(c, dict) and gate(c, listed=False)[1]:          # exactly what the gate fails, list or no list
            names.append(str(c.get("name") or stem))
    names = sorted(set(names))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"about": "Clips made BEFORE the pass-through check (kit/anim/collide.py; the owner's limitations list "
                            "2026-11-15, A-R05) in which the weapon, a hand or a foot goes through the body. They are said, "
                            "never failed. FROZEN: never add a name here to get a clip built - move it clear, or declare "
                            "the contact it means (\"contact\").",
                   "frozen": today or datetime.date.today().isoformat(), "clips": names}, fh, indent=1)
        fh.write("\n")
    return names


def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    try:
        if argv[0] == "freeze":
            out = flag(argv, "--out")
            if len(argv) < 2 or not os.path.isdir(argv[1]) or not out:
                return emit("fail", "collide freeze: <built clips folder> --out <anims>/blocks/" + BEFORE, "python kit/anim/collide.py")
            names = freeze(argv[1], out)
            return emit("pass", f"collide freeze: {len(names)} clip(s) made before the rule -> {out}",
                        "none - commit the list with the gate", clips=names)
        with open(argv[0], encoding="utf-8") as fh:
            clip = json.load(fh)
        r = read(clip)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"collide: {e}", "fix what is named")
    name = str(clip.get("name"))
    bad = over(r)
    return emit("fail" if bad else "pass", words(r, name),
                "move it clear or declare the contact (\"contact\")" if bad else "none", reading=r)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
