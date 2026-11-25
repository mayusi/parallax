"""grip_solve.py — THE HANDS PUT ONTO THE WEAPON (the owner's limitations list 2026-11-15, A-R08 / AN-13: "props are
contracts, not grip solving ... specialized grip solves need a general prop contract"). kit/anim/in_hand.py CHECKS
that the hands a clip says hold its weapon are on it; the strike builder solves its own grip from a move's keys. A
clip from any other route (an import, a hand-posed file, a feel pass, a blend) whose hand has drifted off the weapon
had nothing: this moves the said hands onto the weapon's line, on the R6 clip, whatever built it.

    {"op": "grip", "hands": "two"}                       in a derive recipe run by `python kit/anim/derive.py`
    {"op": "grip", "hands": "two", "at": {"right": 0.3, "left": -0.4}, "max_slide": 2.5}
    python kit/anim/grip_solve.py <clip.json> --hands two|right|left [--out <file>]
NOT YET THROUGH `lune run kit anim derive`: that command rebuilds its clip from reduced body keys (pose_from.py),
which carry no weapon path and no hands - the solve would be thrown away there (card r66z).

THE WEAPON STAYS WHERE IT IS (its path is the swing: the clip's "sword" tracks are not touched); the ARMS go to it.
Each frame, for each hand the grip names:
  where on the weapon   a hand that is near the weapon (a drift): the point of the weapon's line nearest it, anywhere
                        from BEHIND studs behind the grip point to the tip (a hand along the blade is holding it:
                        it is not dragged to the hilt). A hand that is FAR from it (let go, never put on): the place
                        the loved two-handed cuts hold - half the weapon's own grip spacing ahead of its grip point
                        for the right hand, behind it for the left (the seven loved cuts: +-0.25 on a katana,
                        +-0.375 on a greatsword, at every frame). Between NEAR and FAR studs off the line the two
                        are blended, so a hand drifting away does not jump. With two hands a left hand being PUT
                        ON goes APART studs behind the right at least (the loved order); one that already holds
                        keeps its own place.
                        "at": studs along the line from the grip point (+ toward the tip), per hand - a staff or a
                        spear held off its hilt, a reversed grip - instead.
  the arm               an R6 arm is one block: it is TURNED about its shoulder until the hand points at that
                        place, then SLID along itself to reach it (the loved R6 sword clips slide their arms 0.9 to
                        2.4 studs), until it is max_slide studs out of its shoulder at most.
                        The turn is the shortest one from where the arm IS - or, for an arm that is far off (more
                        than CHAIN degrees), from where the solve left it the frame before: a let-go arm is carried
                        along frame to frame instead of being thrown onto the weapon afresh each frame (the short
                        way round flips its roll when the turn nears half a circle).
The weapon's own joint track (kit/anim/grip.py) is made again when the right arm moved: the weapon rides it.
A stretch the clip says the weapon is out of the hands (Toss .. Catch: kit/anim/in_hand.py's windows) is not solved -
but for EASE frames at an end that has the weapon in the hands beyond it, where the solve fades out and in: the hand
leaves the weapon and comes back to it INSIDE the stretch. An end that is the clip's own first or last frame (a
draw, a throw that is never caught) has nothing beyond it and is not solved at all.
Only the frames of an arm whose hand is off its place are written: every other frame stays as it was, to the digit.

WHAT IT REFUSES (ValueError; the clip is left as it was):
  no hands said (in the op, or the clip's own "hands"); a clip with no weapon path, or one whose tip / grip / edge
  track is not the clip's length (the weapon's joint track could not follow the arm); a clip that is not R6;
  a hand that still does not reach (the weapon further than the arm and its slide: named with the frame and the gap);
  a solve that makes an arm JUMP - its turn from one frame to the next more than POP degrees above what that stretch
  asks for (the clip's own turn there, or how fast the weapon's place swings round the shoulder): a hand far off
  for a few frames is the move's to re-key, not a solve's to snap;
  a solve after which a moved arm, or the weapon in it, goes THROUGH the body where it did not, or deeper than it
  did (kit/anim/collide.py's own readings, every pair of the moved arm).
The solved clip SAYS its hands ("hands"), so the build's weapon-in-hand gate holds it to them from then on.
WHAT IT DOES NOT GIVE BACK: the arm's ROLL. The hand is on its place; the block may be turned about the line from
shoulder to hand otherwise than the move's maker had it (measured against the loved cuts: 24 to 40 degrees).
NOT DONE: a second weapon (a pair of guns: the left weapon is its own track, kit/anim/grip.py grip_left, aimed, not
gripped); a shield strapped to the forearm (no line to hold); the wrist - an R6 hand is the end of a block, it cannot
turn on the hilt."""
import copy
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

HILT = 0.6           # studs of the weapon's line ahead of its grip point the loved place is kept within
APART = 0.35         # studs the left hand is kept behind the right at least (the loved cuts: 0.5 and 0.75)
MAX_SLIDE = 2.5      # studs an arm may end up slid out of its shoulder (the seven loved cuts: 0.92 to 2.40)
NEAR, FAR = 0.25, 0.75   # studs off the weapon's line: nearer, a hand keeps its own place along it; further, it takes the loved one
ON = 1e-3            # studs: a hand this near its place is on it (its frame is left as it was)
EASE = 6             # frames the solve fades over inside a stretch the weapon is out of the hands
CHAIN = 45.0         # degrees: an arm further than this from its place is carried on from the frame before
POP = 20.0           # degrees an arm's frame-to-frame turn may grow over the clip's own at that frame
ARM = {"right": "Right Arm", "left": "Left Arm"}


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _arc(a, b, share=1.0):
    """the 3x3 turn taking direction a to direction b the short way, `share` of it (straight back: about any side)"""
    a, b = a / max(float(np.linalg.norm(a)), 1e-12), b / max(float(np.linalg.norm(b)), 1e-12)
    axis = np.cross(a, b)
    s, c = float(np.linalg.norm(axis)), float(np.dot(a, b))
    if s < 1e-9:
        if c > 0:
            return np.eye(3)
        axis = np.cross(a, [1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.cross(a, [0.0, 1.0, 0.0])
        axis = axis / float(np.linalg.norm(axis))
        ang = math.pi * share
    else:
        axis = axis / s
        ang = math.atan2(s, c) * share
    x, y, z = axis
    k = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]], float)
    return np.eye(3) * math.cos(ang) + math.sin(ang) * k + (1 - math.cos(ang)) * np.outer(axis, axis)


def _shares(clip, n, fps):
    """per frame, how much of the solve applies: 1 outside every stretch the weapon is out of the hands; inside one
    it fades from 1 to 0 over EASE frames from an end that has held frames beyond it; an end that is the clip's own
    first or last frame has none (a draw, a throw never caught): 0 right up to it"""
    import in_hand as IH
    w = np.ones(n)
    for a, b in IH.windows(clip, n, fps):
        a, b = max(0, int(a)), min(n - 1, int(b))
        for i in range(a, b + 1):
            d = min(i - a if a > 0 else math.inf, b - i if b < n - 1 else math.inf)
            u = min(1.0, d / (EASE + 1.0))
            w[i] = min(w[i], 1.0 - u * u * (3 - 2 * u))
    return w


def _places(hands, at, proj, off, length, spacing):
    """where along the weapon's line (studs from its grip point) each named hand goes -> {"right": x, "left": x}.
    proj: where each hand is along the line now; off: how far each is from the line; spacing: the weapon's own grip
    spacing (clip["sword"]["grip"])"""
    import in_hand as IH
    lo = -IH.BEHIND
    loved = {"right": min(spacing / 2, HILT, length), "left": max(-spacing / 2, lo)}
    out = {}
    for side in (("right", "left") if hands == "two" else (hands,)):
        if at and side in at:
            out[side] = float(np.clip(at[side], lo, length))
            continue
        far = loved[side]
        if side == "left" and hands == "two":
            # (a left hand being PUT ON goes behind the right, APART at least, as the loved cuts hold - never crossed
            # over it; out of room at the pommel it stops there. A hand that already holds keeps its own place:
            # a hand up the blade, a reversed grip)
            far = max(lo, min(far, out["right"] - APART))
        u = min(1.0, max(0.0, (off[side] - NEAR) / (FAR - NEAR)))
        u = u * u * (3 - 2 * u)
        out[side] = float(np.clip(proj[side], lo, length)) * (1 - u) + far * u
    return out


def _turns(frames):
    """an arm's turn from each frame to the next, degrees -> [n - 1]"""
    import clip as C
    return np.array([C.quat_angle(frames[i][:4], frames[i + 1][:4]) for i in range(len(frames) - 1)])


def solve(clip, hands=None, at=None, max_slide=MAX_SLIDE):
    """-> (the solved clip, a copy; the report {frames, moved, worst_before, worst_after, turned_deg, slid}).
    ValueError names what cannot be solved; the clip given is never changed"""
    import clip as C
    import collide as K
    import collide_repair as CR
    import grip as GR
    import in_hand as IH
    if clip.get("rig") != "R6":
        raise ValueError(f"it is a {clip.get('rig')} clip - a grip is solved on the R6 clip")
    said = hands if hands is not None else IH.hands_of(clip)
    if said not in IH.GRIPS:
        raise ValueError('grip: say which hands hold the weapon - "hands": "two", "right" or "left" (in the op or on the clip)')
    if isinstance(max_slide, bool) or not isinstance(max_slide, (int, float)) or not math.isfinite(max_slide) or not 0 <= max_slide <= 3.2:
        raise ValueError("grip: max_slide is studs, from 0 to 3.2 (the furthest a loved R6 sword clip slides an arm)")
    if at is not None:
        if (not isinstance(at, dict) or not at or any(k not in ARM for k in at)
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in at.values())):
            raise ValueError('grip: "at" is {"right": studs, "left": studs} along the weapon\'s line from its grip point')
        if any(k not in (("right", "left") if said == "two" else (said,)) for k in at):
            raise ValueError(f'grip: "at" names a hand the grip "{said}" does not use')
    sw = clip.get("sword") if isinstance(clip.get("sword"), dict) else {}
    n = len(clip.get("times") or [])
    if not sw.get("tip") or not sw.get("grip_path") or n < 1:
        raise ValueError("it carries no weapon path to put a hand on")
    for k in ("tip", "grip_path", "edge"):
        if not isinstance(sw.get(k), list) or len(sw[k]) != n:
            have = len(sw[k]) if isinstance(sw.get(k), list) else 0
            raise ValueError(f"the weapon's {k} track has {have} frame(s) and the clip {n}: its own joint track could not "
                             "follow a moved arm - build the clip again from its move first")
    rig = C.load_rig("r6")
    fps = float(clip.get("fps") or 30)
    spacing = sw.get("grip")
    spacing = float(spacing) if isinstance(spacing, (int, float)) and not isinstance(spacing, bool) and 0 < spacing <= 2 else 0.5
    was = IH.read(dict(clip, hands=said))
    through = K.read(clip)["pairs"]
    c = copy.deepcopy(clip)
    share = _shares(c, n, fps)
    sides = ("right", "left") if said == "two" else (said,)
    c1 = {s: C.cf(rig["joints"][ARM[s]]["c1"])[:, 3] for s in sides}
    F = {s: [np.array(f, float) for f in clip["joints"][ARM[s]]["frames"]] for s in sides}
    out = {s: {} for s in sides}                             # arm -> {frame: its new joint frame} (only what changed)
    last = {s: None for s in sides}                          # arm -> the joint frame the solve wrote the frame before
    aim = {s: [None] * n for s in sides}                     # arm -> per frame, the way from its shoulder to its place
    turned = slid = 0.0
    moved = 0
    short = None                                             # the worst gap an arm could not close: (studs, side, frame)

    def hand_of(W, s):
        return (W[ARM[s]] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]

    for i in range(n):
        if share[i] <= 0:
            last = {s: None for s in sides}
            continue
        T = C.character_transforms(c, rig, i)
        W = C.fk(rig, T)
        g, t = np.array(sw["grip_path"][i], float), np.array(sw["tip"][i], float)
        length = float(np.linalg.norm(t - g))
        if length < 1e-9:
            last = {s: None for s in sides}
            continue
        ax = (t - g) / length
        hand = {s: hand_of(W, s) for s in sides}
        proj = {s: float(np.dot(hand[s] - g, ax)) for s in sides}
        off = {s: float(np.linalg.norm(hand[s] - (g + float(np.clip(proj[s], -IH.BEHIND, length)) * ax))) for s in sides}
        place = _places(said, at, proj, off, length, spacing)
        Rp = W[rig["joints"]["Right Arm"]["parent"]][:3, :3]
        touched = False
        for s in sides:
            target = g + place[s] * ax
            f = F[s][i]
            if float(np.linalg.norm(target - hand[s])) < ON:
                last[s] = None                               # (it holds by itself here: nothing to carry on from)
                continue
            # where the turn starts: the arm as the clip has it - or, far off, as the solve left it the frame before
            start, W0 = f, W
            if last[s] is not None and share[i] >= 1:
                piv = (W[ARM[s]] @ c1[s])[:3]
                v0, v1 = hand[s] - piv, target - piv
                cosine = float(np.dot(v0, v1)) / max(float(np.linalg.norm(v0) * np.linalg.norm(v1)), 1e-12)
                if math.degrees(math.acos(float(np.clip(cosine, -1.0, 1.0)))) > CHAIN:
                    start = last[s]
                    T2 = dict(T)
                    T2[ARM[s]] = (C.quat_mat(start[:4]), np.array(start[4:7], float))
                    W0 = C.fk(rig, T2)
            pivot = (W0[ARM[s]] @ c1[s])[:3]
            v0, v1 = hand_of(W0, s) - pivot, target - pivot
            reach, need = float(np.linalg.norm(v0)), float(np.linalg.norm(v1))
            if need < 1e-9:
                continue
            if share[i] >= 1:
                aim[s][i] = v1 / need
            Rw = _arc(v0, v1, share[i])
            want = need - reach
            # (the bound is on how far the arm ends up out of its shoulder in all: the slide is cut back until it holds)
            give = want
            if float(np.linalg.norm(start[4:7] + Rp.T @ (v1 / need * want))) > max_slide:
                lo_g, hi_g = 0.0, want
                for _ in range(40):
                    give = (lo_g + hi_g) / 2
                    if float(np.linalg.norm(start[4:7] + Rp.T @ (v1 / need * give))) > max_slide:
                        hi_g = give
                    else:
                        lo_g = give
                give = lo_g
            left = abs(want - give)
            if left > IH.LOOSE and share[i] >= 1 and (short is None or left > short[0]):
                short = (left, s, i)
            R = Rp.T @ Rw @ Rp @ C.quat_mat(start[:4])
            p = start[4:7] + Rp.T @ (v1 / need * give * share[i])
            q = np.array(C.mat_quat(R), float)
            q = -q if float(np.dot(q, f[:4])) < 0 else q         # (the same side of the sphere as the frame it replaces)
            new = np.array([round(float(v), 6) for v in q] + [round(float(v), 5) for v in p])
            out[s][i] = new.tolist()
            last[s] = new
            turned = max(turned, C.quat_angle(q, f[:4]))
            slid = max(slid, abs(give) * share[i])
            touched = True
        moved += 1 if touched else 0
    if short is not None:
        gap, s, i = short
        raise ValueError(f"the {s} hand does not reach the weapon at frame {i} ({i / fps:.2f} s): {gap:.2f} studs short with the "
                         f"arm {max_slide:g} studs out of its shoulder - the weapon is too far from that shoulder: bring it "
                         "nearer in the move, or say a grip the body can hold")
    for s in sides:
        for i, f in out[s].items():
            c["joints"][ARM[s]]["frames"][i] = f
        # no jump: an arm's turn from a frame to the next may not be more than POP over what that stretch asks for -
        # the clip's own turn there, or how far the weapon's place swings round the shoulder (an arm that follows a
        # fast cut turns as fast as the cut). Frames where the solve is fading in or out are the hand travelling to
        # the weapon: not judged
        before, after = _turns(F[s]), _turns(c["joints"][ARM[s]]["frames"])
        if len(after):
            asks = before.copy()
            for i in range(len(after)):
                a0, a1 = aim[s][i], aim[s][i + 1]
                if a0 is None or a1 is None:
                    asks[i] = math.inf if (share[i] < 1 or share[i + 1] < 1) and (i in out[s] or i + 1 in out[s]) else asks[i]
                else:
                    asks[i] = max(asks[i], math.degrees(math.acos(float(np.clip(np.dot(a0, a1), -1.0, 1.0)))))
            grew = after - asks
            k = int(np.argmax(grew))
            if float(grew[k]) > POP:
                raise ValueError(f"put on the weapon, the {ARM[s]} would jump {after[k]:.0f} degrees between frames {k} and "
                                 f"{k + 1} (that stretch asks for {asks[k]:.0f}): a hand that far off is the move's to "
                                 "re-key, not a solve's to snap")
    if out.get("right"):                                     # (the weapon rides the right arm: its joint track made again)
        track = GR.grip_track(c)
        if track is None:
            raise ValueError("the weapon's own joint track could not be made again after the right arm moved")
        c["grip"] = track
    c["hands"] = said
    now = IH.read(c)
    if now["loose"]:
        raise ValueError("after the solve: " + IH.words(now, str(clip.get("name"))))
    arms = {ARM[s] for s in sides if out[s]}
    for key, depth in K.read(c)["pairs"].items():            # every pair a moved arm is in, the weapon in it too
        a, b = key.split("|")
        if a not in arms and b not in arms:
            continue
        bar, old = K.BARS[CR._kind(a, b)], through.get(key, 0.0)
        if depth > bar and (old <= bar or depth > old + 0.02):
            what = "the weapon" if a == "weapon" else f"the {a}'s hand"
            raise ValueError(f"put on the weapon, {what} goes {depth:.2f} studs into the {b} (at most {bar:g}; before the "
                             f"solve {old:.2f}): the weapon is held through the body there - that is the move's to change")
    return c, {"hands": said, "frames": n, "moved": moved, "worst_before": was["worst"], "worst_after": now["worst"],
               "turned_deg": round(turned, 2), "slid": round(slid, 3)}


def words(r):
    if not r["moved"]:
        return f"the {r['hands']}-hand grip already holds the weapon at every frame: nothing moved" if r["hands"] != "two" else \
            "both hands already hold the weapon at every frame: nothing moved"
    return (f"hands \"{r['hands']}\": {r['moved']} of {r['frames']} frame(s) solved - the furthest a hand was off the weapon "
            f"{r['worst_before']:.2f} studs, now {r['worst_after']:.2f}; an arm turned {r['turned_deg']:g} degrees and slid "
            f"{r['slid']:g} studs at the most")


def op_grip(c, hands=None, at=None, max_slide=MAX_SLIDE):
    """the derive op: the clip solved in place -> the log line; ValueError (the recipe fails, named) when it cannot"""
    solved, r = solve(c, hands, at, max_slide)
    keep = dict(solved)
    c.clear()
    c.update(keep)
    return "grip: " + words(r)


def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    try:
        with open(argv[0], encoding="utf-8") as fh:
            c = json.load(fh)
        solved, r = solve(c, flag(argv, "--hands"))
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"anim grip: not solved - {e}", "bring the weapon nearer the shoulder in the move, or say the "
                    "grip the body can hold; the clip was left as it was")
    out = flag(argv, "--out")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(solved, fh)
    return emit("pass", f"anim grip {c.get('name')}: {words(r)}" + ("" if out else " (nothing written: no --out)"),
                "look at the frames it moved (kit anim sheet), then build", report=r)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
