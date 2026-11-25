"""match_tables.py — the TABLES the game matches against (the owner's method lists 2026-11-13: pose matching, distance
matching, motion matching - "MISSING at runtime"; the audit: board/plans/archive/2026-11-13-anim-methods-audit.md). Baked
from built clips; read in the game by src/kit/AnimMatch.luau (pure maths, the same answers: kit/anim/match_run.luau
asks it, the tests compare the two).

    python kit/anim/match_tables.py pose <clip.json> --out <table.json>
        POSE MATCHING: where to ENTER this clip from the pose the character is in. One row a frame it may be entered
        at (each keyed joint's turn), so the game starts the clip at the frame nearest the current pose instead of
        always at 0. A clip is entered only BEFORE its first Hit (entered later, the hit never lands); a loop
        anywhere; a clip with no Hit in its first half.
    python kit/anim/match_tables.py distance <clip.json> [--to <Event>] --out <table.json>
        DISTANCE MATCHING: how far the body still travels from each frame to the clip's end (or to the event): the
        game plays the frame whose remaining distance is the distance left to the stop / the landing / the target,
        so the feet arrive with the body. Needs a clip that travels (a `root` track).
    python kit/anim/match_tables.py motion <clip.json> <clip.json>... --out <db.json>
        MOTION MATCHING: every frame of several clips as a row [pose | how each joint has just been turning], so the
        game can pick, a few times a second, the frame of ANY of them that best continues what the body is doing.
        The game hands in the pose it is in NOW and how each joint turned since the frame before (all it can
        know); the answer is the frame to play NEXT: the one after the row that fits (the one after the frame it
        is playing, unless another row fits better by `stay`). A clip that does not loop holds its last offered
        frame until another motion fits better; a loop's last frame (the same pose as its first) is not offered.

    python kit/anim/match_tables.py for <clip.json> --out <tables.json>
        THE BUILD'S WAY IN (`lune run kit anim`, for every clip that asks): a move or a keyframe spec says
            "match": {"pose": true, "distance": true | "<Event>"}
        and the build bakes the tables it names into the game's animation data (Meta.<Clip>.match), where
        src/kit/Anim.play reads them ({enter = "pose"} / {distance = studs}). Both tables list only the frames the
        clip may be ENTERED at (before its first Hit); the pose table at 30 rows a second at most, the distance table at the clip's own rate. A clip that asks for a table it cannot
        give FAILS the build, named: the game is never handed a clip that says it can be entered by pose and cannot.

    python kit/anim/match_tables.py set <Set.motion.json> --clips <folder of built clips> --out <db.json>
        THE BUILD'S WAY IN FOR MOTION MATCHING (`lune run kit anim`, for every set): a MOTION SET is a file
            assets/animations/motion/<Set>.motion.json = {"clips": ["<Clip>", "<Clip>", ...], "rest": "<Clip>"}
        and the build bakes its database into the game (ReplicatedStorage.KitAnimations.Motion.<Set>), where
        src/kit/Anim.motion(owner, "<Set>") plays from it. Rows are kept at 30 a second at most.
        rest: the LOOPING clip of the set the body goes back to when a clip that does not loop has played out
        (without one the body would freeze there). A clip that does not loop is never left during its last frames
        (its recovery plays out), and no clip is ever scrubbed within itself: the set only moves BETWEEN clips.
        A set FAILS the build, named, when it names a clip the build did not make, has no looping rest among its
        clips, holds a loop of an even number of frames at 60 a second (it cannot be halved: its closing frame
        would be lost), or its clips cannot share a database.
        STEERING (the owner's limitations list 2026-11-15, A-R02): every row also carries WHERE ITS CLIP IS GOING -
        the travel (studs a second, in the body's own frame, -Z ahead) and the turn (radians a second) - read off
        the clip itself: a gait's speed and direction, a travelling clip's root over the next 0.3 s, else standing.
        A set may say it for a clip: "travel": {"<Clip>": [vx, vz] | [vx, vz, turn in degrees a second]}. The game
        hands in where the PLAYER wants to go (src/kit/AnimMatch.wanted) and the search chooses FIRST by where a
        row goes (a new clip: the least miss; the clip being played is kept while it is within 0.08 of that), then
        by the pose among those; it may also name the clips the game allows now ("only"). Without a wanted travel the search is the
        one it was: it only continues motion. A set of more than 3000 rows FAILS (the search reads every row).
        A MOVE IN FLIGHT IS NOT STEERED (a clip that does not loop keeps the search it had: pushing a direction
        does not cut a swing), and STEERING NEVER STARTS A MOVE (under an ask a clip that does not loop is offered
        only when the game names it in "only"). NOT BUILT: a start or a stop clip chosen by where it ENDS UP (a
        row's travel is its next 0.3 s: a stop still travels there, so the idle wins).

WHAT THEY REFUSE (a table that cannot work in the game is not written):
  pose      a clip with fewer than 2 frames it may be entered at (its Hit is on its first frames)
  distance  a clip that does not travel 0.5 studs before the target; a body that travels BACK on the way by more
            than 0.05 studs (one distance would mean two frames)
  motion    fewer than 2 clips; clips that do not key the same joints or do not share one frame rate; a clip named
            twice
  any       a clip with a number that is not a number in it (a table the game cannot read)
A turn is compared by the ANGLE between the two, as a share of a half turn (the same pose is 0 whichever of its two
quaternions says it; 30 degrees off on every joint is 0.17). MEASURED on the three loved katana cuts (2026-11-14):
a body that follows its clip fits the frame on screen to under 0.002 (rounding), and the nearest frame of ANOTHER
cut is 0.05 to 0.3 away; `stay` 0.05 is how much better another row must fit before the clip is left (about 9
degrees a joint). Three cuts are a small sample: the margin is a number to tune in a game."""
import json
import math
import os
import sys

import numpy as np

ENTER_HALF = 0.5     # the share of a clip with no Hit it may be entered in
MIN_TRAVEL = 0.5     # studs a distance table's clip travels at least
BACK = 0.05          # studs the body may travel back on the way
VEL_WEIGHT = 0.05    # how much "how it is turning" (half-turns a second) counts beside "where it is" (share of a half turn)
STAY = 0.05          # a motion match stays on the clip it plays unless another row fits better by this much
TAIL = 6             # the last frames of a clip that does not loop are not offered (nothing follows them)
TRAJ_WEIGHT = 0.5    # (kept in a database for the ones baked before 2026-11-15; the search no longer sums it)
TRAJ_TOL = 0.08      # how much worse than the least miss the PLAYING clip's travel may be and still be kept (a share of the
                     # set's top speed: 1.3 studs a second at 16 - a walk at 8 is left for a jog at 10 once 9.7 is asked)
TRAJ_AHEAD = 0.3     # seconds ahead a travelling clip's own root is read for where it is going
MAX_ROWS = 3000      # the rows a motion set may hold: the game's search reads every one of them


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def _quats(clip, joints):
    """[n, len(joints), 4], each unit, w >= 0"""
    n = len(clip["times"])
    out = np.zeros((n, len(joints), 4))
    for k, j in enumerate(joints):
        F = np.array(clip["joints"][j]["frames"], float)[:, :4]
        if len(F) != n:
            raise ValueError(f"{clip.get('name')}: {j} carries {len(F)} frames and the clip {n} times")
        F = F / np.maximum(np.linalg.norm(F, axis=1, keepdims=True), 1e-12)
        F[F[:, 3] < 0] *= -1
        out[:, k] = F
    return out


def _joints(clip):
    js = [j for j, jd in clip.get("joints", {}).items() if isinstance(jd, dict) and jd.get("frames")]
    if not js:
        raise ValueError(f"{clip.get('name')}: the clip keys no joint")
    return js


def _fps(clip):
    n = len(clip["times"])
    return (n - 1) / float(clip["times"][-1]) if n > 1 and float(clip["times"][-1]) > 0 else float(clip.get("fps") or 60)


def _rows(Q):
    return [[round(float(v), 5) for v in f.reshape(-1)] for f in Q]


def pose_cost(row, pose):
    """how far a pose is from a row: the mean over joints of the angle between the two turns, as a share of a half
    turn (0 = the same pose, 1 = every joint a half turn away). The pose is taken at unit length"""
    a, b = np.asarray(row, float).reshape(-1, 4), np.asarray(pose, float).reshape(-1, 4)
    b = b / np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-12)
    # the angle from the DIFFERENCE of the two turns (its vector part against its scalar part): exact near 0, where
    # an angle taken from the dot alone loses a quarter of a degree to rounding
    dot = np.sum(a * b, axis=1)
    v = a[:, 3:4] * b[:, :3] - b[:, 3:4] * a[:, :3] - np.cross(a[:, :3], b[:, :3])
    return float(np.mean(2.0 * np.arctan2(np.linalg.norm(v, axis=1), np.abs(dot)) / math.pi))


def _finite(clip):
    for j, jd in (clip.get("joints") or {}).items():
        if isinstance(jd, dict) and jd.get("frames") and not np.all(np.isfinite(np.array(jd["frames"], float))):
            raise ValueError(f"{clip.get('name')}: {j} carries a number that is not a number")
    if isinstance(clip.get("root"), list) and not np.all(np.isfinite(np.array(clip["root"], float))):
        raise ValueError(f"{clip.get('name')}: its root track carries a number that is not a number")


def enter_frames(clip):
    """the frames a clip may be entered at -> the last one's index"""
    n = len(clip["times"])
    if clip.get("loop"):
        return n - 1
    hits = [float(e["t"]) for e in clip.get("events") or [] if isinstance(e, dict) and e.get("name") == "Hit"]
    if hits:
        return min(n - 1, int(round(min(hits) * _fps(clip))) - 1)
    return int((n - 1) * ENTER_HALF)


def pose_table(clip):
    _finite(clip)
    js = _joints(clip)
    last = enter_frames(clip)
    if last < 1:
        raise ValueError(f"{clip.get('name')}: fewer than 2 frames it may be entered at (its Hit is on its first frames)")
    Q = _quats(clip, js)
    return {"schema": 1, "kind": "pose", "clip": clip.get("name"), "fps": round(_fps(clip), 4), "joints": js,
            "rows": _rows(Q[:last + 1])}


def pose_match(table, pose):
    """pose: {joint: [x, y, z, w]} (a joint it does not name counts as the row's own) -> the frame to enter at"""
    best, at = None, 0
    for i, row in enumerate(table["rows"]):
        r = np.asarray(row, float).reshape(-1, 4)
        p = np.array([pose.get(j, r[k]) for k, j in enumerate(table["joints"])], float)
        p = p / np.maximum(np.linalg.norm(p, axis=1, keepdims=True), 1e-12)
        c = pose_cost(r, p)
        if best is None or c < best - 1e-12:
            best, at = c, i
    return at


def distance_table(clip, to=None):
    _finite(clip)
    root = clip.get("root")
    n = len(clip["times"])
    if not isinstance(root, list) or len(root) != n:
        raise ValueError(f"{clip.get('name')}: the clip does not travel (it carries no root track)")
    end = n - 1
    if to is not None:
        at = [float(e["t"]) for e in clip.get("events") or [] if isinstance(e, dict) and e.get("name") == to]
        if not at:
            raise ValueError(f"{clip.get('name')}: it has no event {to}")
        end = min(n - 1, int(round(min(at) * _fps(clip))))
    P = np.array(root, float)[: end + 1, 4:7]
    P[:, 1] = 0.0                                            # along the ground
    remaining = np.linalg.norm(P - P[-1], axis=1)
    if remaining[0] < MIN_TRAVEL:
        raise ValueError(f"{clip.get('name')}: it travels {remaining[0]:.2f} studs before {'its end' if to is None else to}: "
                         f"a distance table needs {MIN_TRAVEL:g}")
    back = float(np.max(np.maximum.accumulate(remaining[::-1])[::-1] - remaining))   # how far a later frame is further away
    worst = int(np.argmax(np.maximum.accumulate(remaining[::-1])[::-1] - remaining))
    if back > BACK:
        raise ValueError(f"{clip.get('name')}: the body travels back {back:.2f} studs on the way (round frame {worst}): one "
                         "distance would mean two frames")
    remaining = np.minimum.accumulate(remaining)             # (within BACK: made to never rise)
    return {"schema": 1, "kind": "distance", "clip": clip.get("name"), "fps": round(_fps(clip), 4),
            "to": to or "end", "remaining": [round(float(v), 4) for v in remaining]}


def distance_match(table, distance):
    """the frame (it may fall between two) at which `distance` studs are still to travel"""
    r = table["remaining"]
    distance = max(distance, r[-1])                          # (past the stop is AT the stop: the first frame that is there)
    if distance >= r[0]:
        return 0.0
    for i in range(1, len(r)):
        if distance >= r[i]:
            span = r[i - 1] - r[i]
            return float(i - 1 + ((r[i - 1] - distance) / span if span > 1e-9 else 1.0))
    return float(len(r) - 1)


def _velocity(Q, fps, loop=False):
    """how each joint HAS JUST BEEN turning at every frame: the rotation vector from the frame BEFORE to this one (what
    the game can measure), in half-turns a second -> [n, joints, 3]. Frame 0 takes frame 1's (a loop: the turn from
    its last-but-one frame, the last being the first again)"""
    n = len(Q)
    out = np.zeros((n, Q.shape[1], 3))

    def turn(a, b):
        w = np.sum(a * b, axis=1)
        b = np.where(w[:, None] < 0, -b, b)
        # d = b * inverse(a), its vector part = sin(half the angle) times the axis
        av, aw, bv, bw = -a[:, :3], a[:, 3:4], b[:, :3], b[:, 3:4]
        return (bw * av + aw * bv + np.cross(bv, av)) * 2.0 * fps / math.pi
    for i in range(1, n):
        out[i] = turn(Q[i - 1], Q[i])
    if n > 1:
        out[0] = turn(Q[n - 2], Q[0]) if loop and n > 2 else out[1]
    return out


def travel(clip, said=None):
    """WHERE A CLIP IS GOING at each of its frames -> [[vx, vz, turn], ...]: studs a second in the body's own frame
    (-Z ahead, +X right) and radians a second (+ = to the left). said: the set's own word for this clip ([vx, vz] or
    [vx, vz, degrees a second]); else a gait's speed and direction; else its root over the next TRAJ_AHEAD seconds;
    else it stands."""
    n = len(clip["times"])
    if said is not None:
        if (not isinstance(said, list) or len(said) not in (2, 3)
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) < 1e6 for v in said)):
            raise ValueError(f"{clip.get('name')}: its \"travel\" is [vx, vz] or [vx, vz, turn] (studs a second in the body's own "
                             "frame, -Z ahead; degrees a second, + = to the left)")
        row = [float(said[0]), float(said[1]), math.radians(float(said[2])) if len(said) == 3 else 0.0]
        return [list(row) for _ in range(n)]
    loco = clip.get("locomotion")
    if isinstance(loco, dict) and isinstance(loco.get("speed"), (int, float)):
        d = loco.get("direction") if isinstance(loco.get("direction"), list) and len(loco["direction"]) == 3 else [0.0, 0.0, -1.0]
        v = float(loco["speed"])
        return [[v * float(d[0]), v * float(d[2]), 0.0] for _ in range(n)]
    root = clip.get("root")
    if isinstance(root, list) and root and len(root) != n:
        raise ValueError(f"{clip.get('name')}: its root track has {len(root)} frame(s) and the clip {n}")
    if isinstance(root, list) and len(root) == n and n > 1 and all(isinstance(r, list) and len(r) == 7 for r in root):
        fps = _fps(clip)
        ahead = max(1, int(round(TRAJ_AHEAD * fps)))
        yaw = [2.0 * math.atan2(r[1], r[3]) for r in root]
        for i in range(1, n):                                    # (carried on past a whole turn: a spin is not folded back)
            yaw[i] = yaw[i - 1] + ((yaw[i] - yaw[i - 1] + math.pi) % (2.0 * math.pi) - math.pi)
        out = []
        for i in range(n):
            j = min(n - 1, i + ahead)
            if j == i:
                out.append(list(out[-1]) if out else [0.0, 0.0, 0.0])
                continue
            dt = (j - i) / fps
            wx, wz = root[j][4] - root[i][4], root[j][6] - root[i][6]
            c, s_ = math.cos(yaw[i]), math.sin(yaw[i])
            turn = yaw[j] - yaw[i]
            out.append([(wx * c - wz * s_) / dt, (wx * s_ + wz * c) / dt, turn / dt])
        return out
    return [[0.0, 0.0, 0.0] for _ in range(n)]


def motion_db(clips):
    if len(clips) < 2:
        raise ValueError("a motion database needs 2 clips or more (one clip is just that clip)")
    names = [c.get("name") for c in clips]
    if len(set(names)) != len(names) or not all(isinstance(x, str) and x for x in names):
        raise ValueError("every clip of a motion database has its own name")
    js = _joints(clips[0])
    fps = _fps(clips[0])
    rows, index, spans, traj = [], [], {}, []
    for c in clips:
        _finite(c)
        going = c.get("travel")
        if not (isinstance(going, list) and len(going) == len(c["times"]) and all(
                isinstance(g, list) and len(g) == 3 and all(isinstance(v, (int, float)) and v == v for v in g) for g in going)):
            going = travel(c)
        if set(_joints(c)) != set(js):
            raise ValueError(f"{c.get('name')}: it does not key the joints {names[0]} keys ({', '.join(js)})")
        if abs(_fps(c) - fps) > 0.01:
            raise ValueError(f"{c.get('name')}: {_fps(c):g} frames a second and {names[0]} {fps:g}: one database, one frame rate")
        Q = _quats(c, js)
        V = _velocity(Q, fps, bool(c.get("loop")))
        last = len(Q) - 2 if c.get("loop") else len(Q) - 1 - TAIL     # (a loop's last frame IS its first: not offered twice)
        if last < 1:
            raise ValueError(f"{c.get('name')}: too short for a motion database ({len(Q)} frames)")
        spans[c["name"]] = {"first": len(rows), "frames": last + 1, "loop": bool(c.get("loop"))}
        for i in range(last + 1):
            rows.append([round(float(v), 5) for v in Q[i].reshape(-1)] + [round(float(v), 5) for v in V[i].reshape(-1)])
            index.append([c["name"], i])
            traj.append([round(float(v), 4) for v in going[i]])
    # (the scales the miss is counted in: the top speed and top turn of the set's LOOPS - what the player steers
    # between - never under 1; a dash or a lunge in the set does not make every walk look the same as standing)
    loops = [t for t, (name, _) in zip(traj, index) if spans[name]["loop"]] or traj
    speed = max([1.0] + [math.hypot(t[0], t[1]) for t in loops])
    turn = max([1.0] + [abs(t[2]) for t in loops])
    return {"schema": 1, "kind": "motion", "fps": round(fps, 4), "joints": js, "vel_weight": VEL_WEIGHT, "stay": STAY,
            "clips": spans, "index": index, "rows": rows,
            "traj": traj, "traj_weight": TRAJ_WEIGHT, "traj_tol": TRAJ_TOL, "speed": round(speed, 4), "turn": round(turn, 4)}


def motion_cost(db, row, pose, vel):
    k = len(db["joints"])
    r = np.asarray(row, float)
    return pose_cost(r[: 4 * k], pose) + db["vel_weight"] * float(np.mean(np.linalg.norm(
        r[4 * k:].reshape(-1, 3) - np.asarray(vel, float).reshape(-1, 3), axis=1)))


def traj_cost(db, i, want):
    """what row i's own travel and turn miss the WANTED ones by ([vx, vz, turn]; None: nothing is wanted), in the
    pose cost's unit: the travel as a share of the set's top speed, the turn as a share of its top turn"""
    if want is None or not isinstance(db.get("traj"), list):
        return 0.0
    t = db["traj"][i]
    return (math.hypot(t[0] - want[0], t[1] - want[1]) / db["speed"]
            + abs(t[2] - (want[2] if len(want) > 2 else 0.0)) / db["turn"])


def motion_match(db, pose, vel, current=None, want=None, only=None):
    """pose [joints x 4]: the pose the body is in NOW; vel [joints x 3]: how each joint turned since the frame before
    (the database's joint order, half-turns a second); current: [clip, frame] being played -> [clip, frame] to play
    NEXT: the frame after the row that fits - the one being played unless another row fits better by `stay`.
    want: [vx, vz, turn] the player asks for (STEERING: the miss counts beside the pose); only: the clips the game
    allows now (a list; a clip not in it is never chosen and gets no `stay` - when it allows none of the set's, the
    clip being played simply goes on)"""
    allowed = None if only is None else ({k for k, v in only.items() if v} if isinstance(only, dict) else set(only))
    if want is not None and not all(isinstance(v, (int, float)) and math.isfinite(v) for v in want):
        want = None                                              # (an ask that is not numbers is no ask)
    playing = db["clips"].get(current[0]) if current is not None and isinstance(current[0], str) else None
    if playing is not None and not playing["loop"]:
        want = None      # A MOVE IN FLIGHT IS NOT STEERED: a clip that does not loop (an attack) keeps the search it had
    # WHERE IT GOES FIRST, THEN HOW IT FITS (seen in Studio 2026-11-15: summed, a far gait's pose cost and its travel
    # could be too close to call): a NEW clip is entered only among the rows whose travel misses the ask LEAST (a jog
    # at exactly the asked speed beats a walk 2 studs a second off); among those the pose and its turning choose.
    # The clip being played is kept while its own travel is within traj_tol of that least miss (a stick that wavers
    # does not flip the gait). Nothing asked: every offered row is in the running.
    offered = []
    for i in range(len(db["rows"])):
        name = db["index"][i][0]
        if allowed is not None and name not in allowed:
            continue
        if want is not None and not db["clips"][name]["loop"] and (allowed is None or name not in allowed):
            continue     # STEERING NEVER STARTS A MOVE: under an ask, a clip that does not loop is offered only when the game names it
        offered.append(i)
    least = min(traj_cost(db, i, want) for i in offered) if offered else 0.0
    bar = least + float(db.get("traj_tol", TRAJ_TOL))
    best, at = None, None
    for i in offered:
        if traj_cost(db, i, want) > least + 1e-9:
            continue
        c = motion_cost(db, db["rows"][i], pose, vel)
        if best is None or c < best - 1e-12:
            best, at = c, i
    if at is None:
        # nothing is allowed: what plays goes on (or the set's first row when nothing plays)
        best, at, allowed, bar = math.inf, 0, None, math.inf
    if (current is not None and current[0] in db["clips"] and isinstance(current[1], (int, float)) and current[1] == current[1]
            and abs(current[1]) < 1e9 and (allowed is None or current[0] in allowed)):
        # the frame being played may lie BETWEEN two rows (the game reads a clock): the nearer-fitting of the two stands
        # for it
        span = db["clips"][current[0]]
        f = int(math.floor(current[1]))
        own = None
        for g in ((f, f + 1) if current[1] > f else (f,)):
            # (the clip being played keeps its `stay` only while it still goes where asked)
            if 0 <= g < span["frames"] and traj_cost(db, span["first"] + g, want) <= bar + 1e-12:
                c = motion_cost(db, db["rows"][span["first"] + g], pose, vel)
                if own is None or c < own[0] - 1e-12:
                    own = (c, g)
        if own is not None and own[0] <= best + db["stay"]:
            at = span["first"] + own[1]
    name, f = db["index"][at]
    span = db["clips"][name]
    nxt = f + 1
    if span["loop"]:
        nxt %= span["frames"]
    return [name, min(nxt, span["frames"] - 1)]


def query_at(db, clip, frame):
    """the pose of one frame of a clip and how it turned since the frame before, as the game would hand them in while
    that frame is on screen -> (pose, vel)"""
    js = db["joints"]
    Q = _quats(clip, js)
    V = _velocity(Q, db["fps"], bool(clip.get("loop")))
    return Q[frame].reshape(-1).tolist(), V[frame].reshape(-1).tolist()


def thinned(clip):
    """the clip at 30 frames a second at most (every 2nd frame of a 60-a-second clip): what the game's database holds"""
    fps = _fps(clip)
    if fps < 50:
        return clip
    out = dict(clip)
    n = len(clip["times"])
    keep = list(range(0, n, 2))
    out["times"] = [clip["times"][i] for i in keep]
    out["fps"] = fps / 2
    out["joints"] = {j: ({**jd, "frames": [jd["frames"][i] for i in keep]} if isinstance(jd, dict) and jd.get("frames") else jd)
                     for j, jd in clip["joints"].items()}
    if isinstance(clip.get("travel"), list) and len(clip["travel"]) == n:
        out["travel"] = [clip["travel"][i] for i in keep]
    out.pop("root", None)
    return out


def motion_set(spec, clips_dir):
    """a motion set's file and the folder of built clips -> its database. Raises ValueError naming what is wrong"""
    names = spec.get("clips") if isinstance(spec, dict) else None
    if not isinstance(names, list) or len(names) < 2 or not all(isinstance(x, str) and x for x in names):
        raise ValueError("a motion set is {\"clips\": [\"<Clip>\", \"<Clip>\", ...], \"rest\": \"<Clip>\"} - 2 clips or more")
    if len(set(names)) != len(names):
        raise ValueError("a motion set names each clip once")
    bad = [x for x in names if any(ch in x for ch in "/\\:") or x.startswith(".")]
    if bad:
        raise ValueError(f"{bad[0]} is not a clip's name")
    rest = spec.get("rest")
    if not isinstance(rest, str) or rest not in names:
        raise ValueError("a motion set names its \"rest\": the looping clip of the set the body goes back to when a clip "
                         "that does not loop has played out")
    said = spec.get("travel")
    if said is not None and (not isinstance(said, dict) or any(k not in names for k in said)):
        raise ValueError("a motion set's \"travel\" is {\"<Clip>\": [vx, vz] | [vx, vz, turn]} for clips of the set")
    clips = []
    for name in names:
        path = os.path.join(clips_dir, f"{name}.clip.json")
        if not os.path.isfile(path):
            raise ValueError(f"it names the clip {name}, which this build did not make (no {name}.clip.json: not built, held "
                             "back by a gate, or stale) - build it, or take it out of the set")
        with open(path, encoding="utf-8") as fh:
            c = json.load(fh)
        c["name"] = name
        if c.get("loop") and _fps(c) >= 50 and len(c["times"]) % 2 == 0:
            raise ValueError(f"{name} loops over {len(c['times'])} frames at {_fps(c):g} a second: an even count cannot be halved "
                             "to the database's 30 a second (its closing frame would be lost) - give it an odd number of frames")
        # (where the clip is going, read at its own frame rate BEFORE it is thinned: thinning drops the root)
        c["travel"] = travel(c, (said or {}).get(name))
        clips.append(thinned(c) if _fps(c) >= 50 else c)
    if not clips[names.index(rest)].get("loop"):
        raise ValueError(f"its rest {rest} does not loop: the rest is what the body stays in")
    db = motion_db(clips)
    if len(db["rows"]) > MAX_ROWS:
        raise ValueError(f"it holds {len(db['rows'])} rows and a set holds {MAX_ROWS} at most (the game's search reads every "
                         "row, several times a second, for every body that plays the set) - take clips out, or make two sets")
    for row in db["rows"]:
        row[:] = [round(v, 4) for v in row]
    db["rest"] = rest
    return db


def motion_step(db, prev, pose, dt, current=None, want=None, only=None):
    """ONE STEP OF THE GAME'S LOOP (src/kit/AnimMatch.motionStep is this): prev / pose = {joint: [x, y, z, w]} a moment
    apart (dt seconds; prev None on the first step), current = [clip, frame] being played (the frame may be a
    fraction) -> {"clip", "frame", "jump"}: what to play next, and whether that is anything but the next frame of
    the clip being played (the game then cross-fades to it). want / only: motion_match's (steering, allowed clips)"""
    js = db["joints"]
    if current is not None and current[0] in db["clips"] and isinstance(current[1], (int, float)) and current[1] == current[1]:
        span = db["clips"][current[0]]
        if not span["loop"] and current[1] >= span["frames"] - 1:
            # a clip that does not loop is in its last frames (they are not offered: nothing follows them): it
            # plays out - the game goes to the set's rest when it has ended
            return {"clip": current[0], "frame": span["frames"] - 1, "jump": False}
    flat, vel = [], []
    for j in js:
        q = pose.get(j, [0.0, 0.0, 0.0, 1.0])
        flat += list(q)
        p = prev.get(j) if isinstance(prev, dict) else None
        if p is None or not dt or dt <= 0 or dt != dt:
            vel += [0.0, 0.0, 0.0]
        else:
            a, b = np.array(p, float), np.array(q, float)
            a, b = a / max(np.linalg.norm(a), 1e-12), b / max(np.linalg.norm(b), 1e-12)
            if float(np.dot(a, b)) < 0:
                b = -b
            av, aw, bv, bw = -a[:3], a[3], b[:3], b[3]
            vel += list((bw * av + aw * bv + np.cross(bv, av)) * 2.0 / (dt * math.pi))
    name, frame = motion_match(db, flat, vel, current, want, only)
    jump = True
    if current is not None and current[0] == name and isinstance(current[1], (int, float)) and current[1] == current[1]:
        # not a jump: the answer is where the clip being played is about to be anyway (within a row of its next frame;
        # a loop's last frame is followed by its first; a clip that does not loop holds its last offered frame)
        span = db["clips"][name]
        ahead = frame - current[1]
        if span["loop"] and ahead < -span["frames"] / 2:
            ahead += span["frames"]
        jump = not (0 <= ahead <= 2 or (not span["loop"] and frame == span["frames"] - 1 and current[1] >= frame - 1))
    return {"clip": name, "frame": frame, "jump": jump}


def tables_for(clip):
    """the tables a clip asks for (its "match") -> {"pose": table, "distance": table}; raises ValueError naming what
    it asks for and cannot have, or an ask that is not one"""
    ask = clip.get("match")
    if not isinstance(ask, dict) or not ask or any(k not in ("pose", "distance") for k in ask):
        raise ValueError(f"{clip.get('name')}: \"match\" is {{\"pose\": true, \"distance\": true | \"<Event>\"}}")
    out = {}
    if "pose" in ask:
        if ask["pose"] is not True:
            raise ValueError(f"{clip.get('name')}: \"match\": {{\"pose\": true}} (it is asked for or it is left out)")
        t = pose_table(clip)
        every = 2 if t["fps"] >= 50 else 1                    # (30 rows a second at most: the game's data stays small)
        rows = [[round(v, 4) for v in r] for r in t["rows"][::every]]
        if len(rows) < 2:
            raise ValueError(f"{clip.get('name')}: fewer than 2 frames it may be entered at")
        out["pose"] = {"fps": round(t["fps"] / every, 4), "joints": t["joints"], "rows": rows}
    if "distance" in ask:
        to = ask["distance"]
        if to is not True and not (isinstance(to, str) and to):
            raise ValueError(f"{clip.get('name')}: \"match\": {{\"distance\": true}} (to the clip's end) or an event's name")
        t = distance_table(clip, None if to is True else to)
        last = min(enter_frames(clip), len(t["remaining"]) - 1)      # entered only BEFORE its first Hit, as by pose
        # (at the clip's OWN frame rate: one number a frame is small, and a fast step - 3 studs in 0.1 s - read
        # between rows 1/30 s apart entered 0.19 studs off. Seen in Studio 2026-11-15: asked 1.5, travelled 1.69)
        left = t["remaining"][: last + 1]
        if len(left) < 2:
            raise ValueError(f"{clip.get('name')}: fewer than 2 frames it may be entered at")
        out["distance"] = {"fps": round(t["fps"], 4), "to": t["to"], "remaining": left}
    return out


def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv):
    if len(argv) < 2 or argv[0] not in ("pose", "distance", "motion", "for", "set"):
        print(__doc__)
        return 2
    out = flag(argv, "--out")
    paths = []
    for a in argv[1:]:
        if a.startswith("--"):
            break
        paths.append(a)
    if not out:
        return emit("fail", f"match {argv[0]}: --out <table.json>", "python kit/anim/match_tables.py")
    if "--to" in argv and argv[0] != "distance":
        return emit("fail", f"match {argv[0]}: --to belongs to a distance table (the event the body travels to)",
                    "python kit/anim/match_tables.py")
    try:
        clips = []
        for p in paths:
            with open(p, encoding="utf-8") as fh:
                clips.append(json.load(fh))
        if argv[0] == "set":
            folder = flag(argv, "--clips")
            if not folder or not os.path.isdir(folder):
                raise ValueError("--clips <the folder of built clips (<Clip>.clip.json)>")
            t = motion_set(clips[0], folder)
            said = f"{len(t['rows'])} frames of {len(t['clips'])} clips ({', '.join(t['clips'])}) at {t['fps']:g} a second"
        elif argv[0] == "for":
            t = tables_for(clips[0])
            said = f"{clips[0].get('name')}: " + ", ".join(
                f"entered by pose at {len(v['rows'])} frames" if k == "pose" else f"a frame for every distance left to {v['to']} ({v['remaining'][0]:.2f} studs)"
                for k, v in t.items())
        elif argv[0] == "pose":
            t = pose_table(clips[0])
            said = f"{t['clip']} may be entered at {len(t['rows'])} frames (0 to {len(t['rows']) - 1}), by the pose the character is in"
        elif argv[0] == "distance":
            t = distance_table(clips[0], flag(argv, "--to"))
            said = f"{t['clip']} travels {t['remaining'][0]:.2f} studs to {t['to']}: a frame for every distance left"
        else:
            t = motion_db(clips)
            said = f"{len(t['rows'])} frames of {len(t['clips'])} clips ({', '.join(t['clips'])}), each a pose and how it is turning"
    except (OSError, ValueError, KeyError, TypeError, IndexError) as e:
        return emit("fail", f"match {argv[0]}: no table - {e}", "fix the clip named (or choose another): a table that cannot work is not written")
    if argv[0] == "set":
        t["set"] = os.path.basename(paths[0]).split(".")[0]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(t, fh, separators=(",", ":"))
    os.replace(tmp, out)
    return emit("pass", f"match {argv[0]}: {said} -> {out}",
                "none - the game reads it with src/kit/AnimMatch.luau (not yet called by a game: a Studio session)", table=out)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
