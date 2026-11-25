"""cleanup.py — CLEAN-UP of a captured or imported clip (the owner's method lists 2026-11-13: motion capture cleanup
- "cleanup is a floor fit and a despike only"; the audit: board/plans/archive/2026-11-13-anim-methods-audit.md). One more op
for a `kit anim derive` recipe (kit/anim/derive.py), beside {"op": "despike"} (single-frame jolts, kit/anim/snaps.py)
and the curve filter (shake, kit/anim/curves.py):

  {"op": "plant", "max_shift": 1.5, "travel": false}
      FEET THAT SKATE ARE PLANTED. A foot that stands (its sole within 0.04 studs of the floor: the build's own
      measure, kit/anim/clip.py) and still drifts along the ground is held still, by moving the BODY over it: an R6
      leg is one rigid block, so the foot is not re-posed - from each frame to the next the clip's root track takes
      the opposite of what the standing feet moved (their mean when both stand). Where no foot stands, and on the
      frame a foot lands or lifts, the correction is carried, so nothing pops. When both feet stand and drift
      DIFFERENTLY the body can only take the mean: each foot keeps half the difference (a foot that held still then
      moves a little), and the slide that is left is said. Every joint, the blade, the events and the clip's length
      stay as they were.
      It is for clips that FAIL the build's foot-slide bar (0.1 studs a frame): a clip that passes is left untouched.

WHAT IT REFUSES, the clip left as it was:
  - a LOOP and an in-place locomotion clip (their planted feet are meant to move back at the ground speed: the
    build judges them as skate against that speed, not as slide);
  - a STEPPED clip (its feet are judged per held pose);
  - a correction that at any moment is more than `max_shift` studs from where the body was (that is the body
    travelling, not a foot skating: key the travel as a root track instead, or say a larger max_shift);
  - a clip that had NO root track, unless the recipe says "travel": true. WHY: a root track that travels more than
    0.05 studs is played by the game as the character's own travel (src/kit/Anim applyRoot sets the body's place
    every frame of the move: the player cannot walk during it, and a `warp` the move carries wakes up). An in-place
    move must not become that unasked;
  - a correction the game would never get (the root ends up travelling 0.05 studs or less, which the build does
    not write into the game's data, AND the feet need it: with the body standing still they would still fail the bar);
  - a root track that does not carry one row a frame; a clip whose feet never stand;
  - a correction that leaves the worst slide no better (the two feet drift apart: key the legs).

  {"op": "gaps", "min": 0.5, "max_gap": 0.1, "dropped": false}
      FRAMES THE CAPTURE DID NOT SEE ARE RE-MADE, AND SAID (the owner's limitations list 2026-11-15, A-R07: "confidence
      masks, dropped-frame detection and occlusion reconstruction were not found"). A frame of a joint is UNKNOWN
      when the clip's own confidence for it is under `min` ("confidence": {"<joint>": [0..1 a frame]}, or one list
      for every joint - what a tracker hands over), or - only when the recipe says "dropped": true - when the whole
      pose (turns and slides) is an exact repeat of the frame before while the body is moving round it and no event
      is beside it (a dropped frame is played as a repeat; so is a hit-stop the clip MEANS, which is why it is asked
      for and never read next to an event). Each run of unknown
      frames is re-made between the known frames either side of it (the turn the short way, the slide in a line)
      and the op's log lists every run it filled, joint and frames, so it can be reviewed.
      IT NEVER INVENTS A CONTACT, AND NEVER MOVES ONE: the events stay where they are, and a run that covers the
      first or last frame or an event (a Hit), or in which a foot LANDS or LIFTS, is REFUSED - nothing either side
      of such a moment says when it was (a foot that stands on both sides of the gap stood through it). A run longer than `max_gap` seconds is refused too (that is
      a missing motion, not a missing frame). A STEPPED clip is refused (its repeats are its holds).
      CHECKED AGAINST THE CLIP AS IT WAS, after every run is re-made: no hand further from the weapon (the blade's
      own track is not re-made: a re-made torso or arm that leaves it is refused), and no foot that stood lifted,
      landed or moved along the ground. Refused, the clip is as it was."""
import copy
import math

import numpy as np

GAME_ROOT = 0.05     # studs a root track must travel before the build writes it into the game's data (kit/cmd/anim.luau)


def _soles(clip, rig):
    """each foot's sole in the world at every frame, and whether it stands -> {foot: ([n, 3], [n] bool)}"""
    import clip as C
    feet = C.feet_of(rig)
    frames = C.world_frames(clip, rig)
    n = len(frames)
    out, bottoms = {}, {}
    for f in feet:
        sole = np.array([0.0, -rig["sizes"][f][1] / 2, 0.0, 1.0])
        pos = np.array([(frames[i][f] @ sole)[:3] for i in range(n)])
        out[f] = pos
        bottoms[f] = pos[:, 1]
    ground = C.rest_ground(rig, feet)
    if ground is None:
        ground = min(float(b.min()) for b in bottoms.values())
    return {f: (out[f], bottoms[f] < ground + C.CONTACT) for f in feet}


def slide(clip, rig):
    """the most a planted foot moves along the ground in one frame, studs (the build's foot-slide reading)"""
    worst = 0.0
    for pos, contact in _soles(clip, rig).values():
        for i in range(len(pos) - 1):
            if contact[i] and contact[i + 1]:
                worst = max(worst, float(math.hypot(pos[i + 1][0] - pos[i][0], pos[i + 1][2] - pos[i][2])))
    return worst


def op_plant(c, max_shift=1.5, travel=False, rig=None):
    """-> what it did, in words. Raises ValueError (the clip left as it was) for a clip it is not for"""
    import clip as C
    if isinstance(max_shift, bool) or not isinstance(max_shift, (int, float)) or not math.isfinite(max_shift) or max_shift <= 0:
        raise ValueError("plant: max_shift is how far the body may be moved, in studs (above 0)")
    if not isinstance(travel, bool):
        raise ValueError("plant: travel is true or false (may a clip that stood in place be given a root track?)")
    if c.get("loop") or (isinstance(c.get("locomotion"), dict) and c["locomotion"].get("speed")):
        raise ValueError("plant: this clip loops or walks in place: its planted feet are meant to move back at the ground "
                         "speed (the build judges that as skate, not slide)")
    if c.get("stepped"):
        raise ValueError("plant: this clip is STEPPED (poses held on 2s or 3s): plant its feet before its steps are made")
    n = len(c["times"])
    had = isinstance(c.get("root"), list)
    if had and len(c["root"]) != n:
        raise ValueError(f"plant: the clip's root track carries {len(c['root'])} rows and the clip {n} frames")
    rig = rig or C.load_rig(str(c.get("rig") or "r6").lower())
    soles = _soles(c, rig)
    if not soles or not any(bool(contact.any()) for _, contact in soles.values()):
        raise ValueError("plant: no foot of this clip ever stands on the floor")
    bar = float(C.GATES["foot_slide"])
    before = slide(c, rig)
    if before <= bar:
        return (f"plant: the planted feet slide {before:.3f} studs a frame at most, inside the build's bar ({bar:g}): "
                "nothing changed")
    if not had and not travel:
        raise ValueError("plant: this clip stands in place (no root track) and planting its feet would give it one: the "
                         "game then moves the character itself for the whole move - say \"travel\": true if that is meant")
    # the body's correction: from each frame to the next it takes back what the feet standing on BOTH frames moved
    # (their mean); carried where none does. The build's own reading counts exactly those frame pairs
    corr = np.zeros((n, 2))
    for i in range(1, n):
        moved = [pos[i, [0, 2]] - pos[i - 1, [0, 2]] for pos, contact in soles.values() if contact[i - 1] and contact[i]]
        corr[i] = corr[i - 1] - (np.mean(moved, axis=0) if moved else 0.0)
    total = float(np.max(np.linalg.norm(corr, axis=1)))
    if total > max_shift:
        raise ValueError(f"plant: holding the feet would move the body {total:.2f} studs (max_shift {max_shift:g}): that is "
                         "travel, not skate - key the travel as a root track, or raise max_shift")
    was = copy.deepcopy(c["root"]) if had else None
    root = np.array(c["root"], float) if had else np.tile(np.array([0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]), (n, 1))
    # (the correction is in the world; the root's own turn does not change where its origin sits)
    root[:, 4] += corr[:, 0]
    root[:, 6] += corr[:, 1]

    def undo():
        if had:
            c["root"] = was
        else:
            c.pop("root", None)
    c["root"] = [[round(float(v), 6) for v in r] for r in root]
    after = slide(c, rig)
    far = float(np.max(np.hypot(root[:, 4] - root[0, 4], root[:, 6] - root[0, 6])))
    if after >= before - 1e-3:
        undo()
        raise ValueError(f"plant: the feet slide {after:.3f} studs a frame after it and {before:.3f} before: the two feet "
                         "drift apart, which moving the body cannot mend - key the legs")
    small = ""
    if far <= GAME_ROOT:
        # the build writes no root track this small into the game: there the body stays put. Is that the same?
        still = copy.deepcopy(c)
        still["root"] = [[0.0, 0.0, 0.0, 1.0, 0.0, r[5], 0.0] for r in c["root"]]
        in_game = slide(still, rig)
        if in_game > bar:
            undo()
            raise ValueError(f"plant: the root track would travel {far:.3f} studs at most: the build writes none that "
                             f"travels {GAME_ROOT:g} studs or less into the game, where the feet would still slide {in_game:.3f}")
        small = (f"; what is left of the root track travels {far:.3f} studs, too little for the build to hand to the game: "
                 f"there the body stands still and the feet slide {in_game:.3f}, inside the bar")
    return (f"plant: planted feet slid {before:.3f} studs a frame at most, now {after:.3f}"
            f"{' (still over the bar of ' + format(bar, 'g') + ': the feet drift apart, key the legs for the rest)' if after > bar else ''}"
            f"; the body is moved {total:.2f} studs at most over them (the root track{'' if had else ' is new: the game now moves the character through this move'}){small}")


MIN_CONF = 0.5       # a frame of a joint the capture trusts less than this is unknown
MAX_GAP_S = 0.1      # seconds of one joint that may be re-made in one run
STILL_DEG = 1e-4     # two poses this close on every joint are the same pose (a repeat)
MOVING_DEG = 0.5     # ... and the body moves round a repeat when a neighbour turns a joint this much


def unknown_frames(c, min_conf=MIN_CONF, dropped=False, max_gap=MAX_GAP_S):
    """the frames of each joint the capture did not see -> {joint: [n] bool}, and the frames read as dropped"""
    import clip as C
    n = len(c["times"])
    joints = [j for j, jd in c["joints"].items() if jd.get("frames") and len(jd["frames"]) == n]
    unknown = {j: np.zeros(n, bool) for j in joints}
    conf = c.get("confidence")
    if conf is not None:
        per = conf if isinstance(conf, dict) else {j: conf for j in joints}
        for j, track in per.items():
            if j not in unknown:
                raise ValueError(f"gaps: \"confidence\" names {j}, which this clip does not key")
            if (not isinstance(track, list) or len(track) != n
                    or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0.0 <= v <= 1.0 for v in track)):
                raise ValueError(f"gaps: the confidence of {j} is one number (0..1) a frame ({n} frames)")
            unknown[j] |= np.array(track, float) < float(min_conf)
    drops = []
    if dropped and n > 2 and joints:
        Q = {j: np.array([f[:4] for f in c["joints"][j]["frames"]], float) for j in joints}
        fps = C.clip_fps(c)
        beside = set()                                           # (a repeat beside an event is the clip's own: a hit-stop)
        for e in c.get("events") or []:
            if isinstance(e, dict) and isinstance(e.get("t"), (int, float)):
                f = int(round(float(e["t"]) * fps))
                beside |= {f - 1, f, f + 1}
        turn = np.zeros(n)                                       # the largest change of any joint from the frame before
        for j in joints:                                         # (its slide too: 100 degrees stands for a stud)
            P = np.array([f[4:7] for f in c["joints"][j]["frames"]], float)
            turn[1:] = np.maximum(turn[1:], np.linalg.norm(np.diff(P, axis=0), axis=1) * 100.0)
        for j in joints:
            q = Q[j] / np.maximum(np.linalg.norm(Q[j], axis=1, keepdims=True), 1e-12)
            d = np.degrees(2.0 * np.arccos(np.clip(np.abs(np.sum(q[1:] * q[:-1], axis=1)), 0.0, 1.0)))
            turn[1:] = np.maximum(turn[1:], d)
        i = 1
        while i < n:
            if turn[i] <= STILL_DEG:
                k = i
                while k + 1 < n and turn[k + 1] <= STILL_DEG:
                    k += 1
                # a repeat with motion on BOTH sides of it is a dropped frame; a pose that is simply held (the
                # clip's start, its end, a long hold) is the clip's own
                before = turn[i - 1] if i - 1 >= 1 else 0.0
                after = turn[k + 1] if k + 1 < n else 0.0
                moving = MOVING_DEG * 60.0 / fps                  # (the same turning speed at any frame rate)
                if (before >= moving and after >= moving and (k - i + 1) <= max(1, int(round(float(max_gap) * fps)))
                        and not any(f in beside for f in range(i, k + 1))):
                    drops += list(range(i, k + 1))
                i = k + 1
            else:
                i += 1
        for j in joints:
            unknown[j][drops] = True
    return unknown, drops


def op_gaps(c, min_conf=MIN_CONF, max_gap=MAX_GAP_S, dropped=False, rig=None):
    """re-make the frames the capture did not see (see the module's text) -> the log line. Raises ValueError naming
    what it refuses; the clip is changed only when every run could be filled"""
    import clip as C
    if C.step_frames(c):
        raise ValueError("gaps: a stepped clip is not re-made (its repeated frames are its holds)")
    n = len(c["times"])
    fps = C.clip_fps(c)
    if isinstance(min_conf, bool) or not isinstance(min_conf, (int, float)) or not 0.0 <= min_conf <= 1.0:
        raise ValueError("gaps: \"min\" is the confidence (0..1) under which a frame is unknown")
    if isinstance(max_gap, bool) or not isinstance(max_gap, (int, float)) or not max_gap > 0:
        raise ValueError("gaps: \"max_gap\" is seconds, above 0")
    if not isinstance(dropped, bool):
        raise ValueError("gaps: \"dropped\" is true or false")
    unknown, drops = unknown_frames(c, min_conf, dropped, max_gap)
    most = max(1, int(round(float(max_gap) * fps)))
    kept = {0: "the first frame", n - 1: "the last frame"}
    for e in c.get("events") or []:
        if isinstance(e, dict) and isinstance(e.get("t"), (int, float)):
            kept.setdefault(min(n - 1, max(0, int(round(float(e["t"]) * fps)))), f"the {e.get('name')} event")
    stands = {}
    if c.get("rig") == "R6":
        rig = rig or C.load_rig("r6")
        for foot, (_, on) in _soles(c, rig).items():
            stands[foot] = on
    runs = []
    for j, bad in unknown.items():
        i = 0
        while i < n:
            if not bad[i]:
                i += 1
                continue
            k = i
            while k + 1 < n and bad[k + 1]:
                k += 1
            for f in range(i, k + 1):
                if f in kept:
                    raise ValueError(f"gaps: {j} is unknown at frame {f}, which is {kept[f]} - a moment the clip is held to "
                                     "is not re-made from its neighbours (capture it again, or key that pose)")
            # a foot: re-made only when it stands at BOTH known frames either side (it stood through the gap: the
            # contact is kept, not invented) or at neither (it was in the air); a landing or a lift inside the gap
            # is a contact nobody saw
            if j in stands and bool(stands[j][i - 1]) != bool(stands[j][k + 1]):
                raise ValueError(f"gaps: {j} lands or lifts somewhere in frames {i}-{k}, which the capture did not see - a "
                                 "contact is not invented (capture it again, or key that pose)")
            if k - i + 1 > most:
                raise ValueError(f"gaps: {j} is unknown for {k - i + 1} frames ({i}-{k}; at most {most}: {max_gap:g} s) - that is "
                                 "a missing motion, not a missing frame")
            runs.append((j, i, k))
            i = k + 1
    if not runs:
        return "gaps: every frame is known - nothing re-made"
    was = c
    c = copy.deepcopy(was)                                       # (re-made on a copy: refused, the clip is as it was)
    for j, i, k in runs:
        F = c["joints"][j]["frames"]
        a, b = np.array(F[i - 1], float), np.array(F[k + 1], float)
        for f in range(i, k + 1):
            u = (f - (i - 1)) / (k + 1 - (i - 1))
            q = C.slerp(a[:4], b[:4], u)
            F[f] = [round(float(v), 6) for v in q] + [round(float(v), 6) for v in (a[4:7] * (1 - u) + b[4:7] * u)]
    # AGAINST THE CLIP AS IT WAS: no hand further from the weapon, no standing foot lifted, landed or moved
    if isinstance(was.get("sword"), dict) and was.get("rig") == "R6":
        import curves as CV
        # (the unknown frames had no pose to compare with: a hand is held to where it was at the known frame
        # before its gap, by the weapon-in-hand check's own 0.1 studs)
        now = CV._hands_off_frames(c)
        for hand, dist in now.items():
            for j, i, k in runs:
                for f in range(i, k + 1):
                    if dist[f] > dist[i - 1] + CV.HAND_OFF:
                        raise ValueError(f"gaps: re-made, the {hand} is {dist[f]:.2f} studs from the weapon at frame {f} (it was "
                                         f"{dist[i - 1]:.2f} before the gap) - the blade's own track is not re-made, and the "
                                         "body that carries it was unknown there (capture it again)")
    if was.get("rig") == "R6":
        old, new = _soles(was, rig), _soles(c, rig)
        for foot in old:
            # (the foot's OWN unknown frames had no pose to compare with: there it must do what it did either side
            # of the gap; everywhere else - a re-made torso carries the feet - it must be where it was)
            own = np.zeros(n, bool)
            want = old[foot][1].copy()
            for j, i, k in runs:
                if j in (foot, "Torso"):                         # (the torso carries the legs)
                    own[i:k + 1] = True
                    want[i:k + 1] = old[foot][1][i - 1]
            if (want != new[foot][1]).any():
                f = int(np.nonzero(want != new[foot][1])[0][0])
                raise ValueError(f"gaps: re-made, {foot} {'lifts' if want[f] else 'lands'} at frame {f} where it did not - "
                                 "a contact is not moved (capture it again, or key that pose)")
            held = old[foot][1] & ~own
            moved = np.linalg.norm((new[foot][0] - old[foot][0])[held][:, [0, 2]], axis=1) if held.any() else np.zeros(1)
            if float(moved.max()) > 0.04:
                raise ValueError(f"gaps: re-made, {foot} moves {float(moved.max()):.2f} studs along the ground while it stands - "
                                 "a contact is not moved (capture it again, or key that pose)")
    for j in was["joints"]:
        was["joints"][j] = c["joints"][j]
    c = was
    said = "; ".join(f"{j} {i}-{k}" if k > i else f"{j} {i}" for j, i, k in runs[:12]) + (f"; +{len(runs) - 12} more" if len(runs) > 12 else "")
    c["gaps_filled"] = [[j, i, k] for j, i, k in runs]
    return (f"gaps: {len(runs)} run(s) re-made between their known neighbours ({said})"
            + (f"; {len(drops)} dropped frame(s) read as repeats ({', '.join(str(x) for x in drops[:8])})" if drops else "")
            + " - REVIEW them: a re-made frame is a guess between two poses")

