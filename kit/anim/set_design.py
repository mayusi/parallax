"""set_design.py — THE ATTACK SET'S DESIGN PAGE (the animation studio route's A1, board/plans/
2026-11-11-anim-studio-route-plan.md; the audit: board/plans/archive/2026-11-13-anim-methods-audit.md, rank 3). A studio designs
a string of attacks BEFORE anybody poses one: each attack's direction, its height, what the body does, its frame
budget, its intent, the pose it ends in and what may follow. The kit designed every move alone; "they are cousins" (the
owner, 2026-11-04) is what a set made that way looks like. Here the SET is one file and one page, and two attacks that
are too alike are named before a frame exists.

    new <Set> --attacks <n> [--weapon <word>] --designs <dir>      a design to fill in (every TODO must go)
    from-moves <Set> <move.json>... --designs <dir>                 a design of moves that exist: what can be measured
                                                                    is (direction, height, frames); the rest is TODO
    check <Set> --designs <dir>                                     the design against itself and against the keys of
                                                                    the moves it names (fails, naming every problem)
    page <Set> --designs <dir> [--out <png>]                        the design page (one row an attack, the string's
                                                                    rhythm as one bar, the problems on top)
    approve <Set> "<the owner's words>" --by owner --id <id> --designs <dir> [--page <the page's png>]
    state <Set> --designs <dir> [--need approved]
    lock <Name>... --designs <dir> [--anims <dir>] [--style <anim_style.json>]...

The design file, <designs>/<Set>.design.json:
    {"schema": 2, "set": "<Set>", "weapon": "katana", "links": "pose",
     "attacks": [{"name": "<Move>", "cut": "down_left", "height": "mid", "body": "step_in", "intent": "proper",
                  "frames": {"windup": 26, "active": 4, "recovery": 21}, "starts": "<the guard it starts from, in words>",
                  "ends": "<the pose it ends in, in words>",
                  "next": ["<Move>"], "move": "<its .move.json, once its keys exist>"}]}
  cut     the blade's travel as the PLAYER sees it (the camera behind): down, down_left, left, up_left, up, up_right,
          right, down_right, or thrust
  height  where it lands on the target: high (head and shoulders), mid, low (hips and legs)
  body    plant, step_in, step_back, side_step, spin, hop, lunge, drop
  frames  at 60 a second: windup = the start to the Hit, active, recovery
  starts / ends   the guard it starts from and the pose it ends in, in words (the owner's V3 list, anim stage B.1):
          in a set linked by "pose" an attack that follows another starts in the very pose that one ends in - the
          same words, said on the page before any key exists (the keys' own link is measured once they do)
  next    the attacks that may follow it ([] = the string ends here)
  links   (the set's) how the string holds together: "pose" = every attack ends in the pose the next one starts in
          (the two strings the owner loved link within 5 degrees; a game's style calls 6 linked); "blend" = the game
          blends from one to the next (strings played that way here end up to 180 degrees from the next start)

WHAT IS CHECKED (check), each named with its attack:
  - the design is whole: no TODO, every word from its list, frames counted, `next` names attacks of the set;
  - COUSINS BY DESIGN: two attacks with the same cut, height and body;
  - THE STRING'S LINKS, once two attacks that follow each other have keys: in a set linked by "pose", an attack that
    ends more than LINK_BAR (6) degrees from where the next starts BREAKS the string (named with the joint); in a set
    linked by "blend" the same number is a note. Which of the two a set is, is part of the design he approves;
  - against a move's KEYS (generated in memory - nothing is built, no clock starts): the cut's measured direction is
    within 45 degrees of the designed one (or both are thrusts; a cut that runs mostly in depth is held only against
    its OPPOSITE: an "up" whose keys chop down fails), its
    wind-up and its whole length are the designed frames (to 3 frames or a quarter; 4 frames or a fifth); where the
    blade is at the Hit against the designed height is a note;
  - COUSINS BY MEASURE: two attacks whose blades run less than COUSIN_PATH (2.8) studs apart on average (the tip's
    path against the body, start to Hit and Hit to end, sample for sample: a slower copy is the same path, and so is
    the same cut with a step added - the path is read in the body's own frame). Measured 2026-11-13: the two attacks
    closest to each other inside a set the owner loved (greatsword combo, katana combo) run 6.1 studs apart, and on
    the sets built here no two distinct numbered attacks of one set run closer than 4.2; one cut made again runs at
    most 1.6 studs from itself (every key's yaw, pitch and roll turned up to 25 degrees and its grip moved half a
    stud on each axis; 1.3 on the other weapon; 0.6 with only the yaw turned). The bar sits between. (The angle
    between two cuts does NOT tell cousins: two loved attacks of one set cut within 14 degrees of each other, 8.9
    studs apart. It is said, not used.)
    NOT cousins: the same cut designed at two heights whose blades measure a stud or more apart at the Hit (a cut at
    the head and one at the hips run about 2.5 studs apart): said as a note.
    A pair past the bar but closer than anything he loved is SAID (a note), never failed.
The owner's yes (approve) is to the design AS IT IS (its id) on the PAGE he saw: the page must be drawn, and what it
printed is stored with the yes (the picture's hash, its problems). A design that changes after it is stale. His yes
wins over a measure: the problems printed on that page are accepted exactly as they stood (one whose numbers move
later is a new problem and fails); a design that is not whole cannot be approved; a record without the page he saw
is no yes.

THE LOCK (lock; the owner 2026-11-13: every method "enforced in the terms of being used"): a move made after the rule
that a design names is not made, at any build, unless that design has his yes as it is now. A move made after the rule
that a game's style lists in a set (anim_style.json "sets") and no design names is not made either: a set starts with
its design page. Made before the rule = named in <anims>/blocks/_before_blocking.json (kit/anim/blocking.py freeze):
never asked. What cannot be read frees nothing: a design or style file that is broken holds every move asked about."""
import copy
import datetime
import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

CUTS = ("down", "down_left", "left", "up_left", "up", "up_right", "right", "down_right", "thrust")
WHEEL = {"right": 0.0, "up_right": 45.0, "up": 90.0, "up_left": 135.0, "left": 180.0, "down_left": 225.0, "down": 270.0,
         "down_right": 315.0}
HEIGHTS = ("high", "mid", "low")
BODY = ("plant", "step_in", "step_back", "side_step", "spin", "hop", "lunge", "drop")
INTENTS = ("calm", "proper", "aggressive")
SAMPLES = 24            # the blade's path: half its samples from the start to the Hit, half from the Hit to the end
# measured 2026-11-13 (kit/selftest/anim/faults/loved, _artifacts probe): see the docstring
LOVED_PATH = 6.08       # studs: the closest two attacks inside a set he loved (GsCombo1SideLeft, GsCombo4Underhip)
RESKIN_PATH = 1.6       # studs: the furthest a re-make of one loved cut got from it (every key's yaw, pitch and roll
#                         turned up to 25 degrees and its grip moved up to half a stud on each axis; the same cut on the
#                         other weapon: 1.27; only the yaw turned: 0.6)
COUSIN_PATH = 2.8       # studs: between the two. On the sets built here (read only) no two distinct numbered attacks of
#                         one set run closer than 4.2; every pair under the bar is a Run / Step / B variant of one cut
HEIGHT_APART = 1.0      # studs between two blades at the Hit for "designed at two heights" to be measured as two
LOVED_LINK = 5.0        # degrees: where an attack of a loved string ends against where the next starts (measured: 0.4-4.9)
LINK_BAR = 6.0          # degrees: a string linked by pose (the SampleDojo's style, measured off the loved katana string, calls
#                         6 linked; the loved strings' links are 0.1 to 4.9, the strings here that the game blends 86-180)
LINKS = ("pose", "blend")
CUT_OFF = 45.0          # a designed direction and the keys' own may differ by one step of the wheel
THRUST = 0.7            # a thrust travels along its own blade: the share of the tip's travel that runs along it
THRUST_SWEEP = 30.0     # ... and the blade keeps its direction: it turns less than this through the fast run
SCREEN_SHARE = 0.5      # a cut's direction is read off the screen when this share of the blade's turn shows on it
HIGH_Y, LOW_Y = 0.5, -1.0   # character space: the shoulders' line and the hips' (the torso's centre is 0, the floor -3)
FIELDS = ("name", "cut", "height", "body", "intent", "frames", "starts", "ends", "next")
FIELDS_1 = tuple(k for k in FIELDS if k != "starts")    # a schema-1 design (before 2026-11-18) said no start


def fields_of(d):
    """the fields every attack of this design must say: schema 2 (what kit anim design --new / --from write since
    2026-11-18) says the guard each attack starts from too"""
    return FIELDS if int(d.get("schema") or 1) >= 2 else FIELDS_1


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def design_path(designs, name):
    return os.path.join(designs, f"{name}.design.json")


def record_path(designs, name):
    return os.path.join(designs, f"{name}.design.record.json")


def load(designs, name):
    path = design_path(designs, name)
    if not os.path.isfile(path):
        raise ValueError(f"no design at {path.replace(os.sep, '/')}")
    with open(path, encoding="utf-8") as fh:
        try:
            d = json.load(fh)
        except ValueError as e:
            raise ValueError(f"{path.replace(os.sep, '/')} is not valid JSON ({e})") from e
    if not isinstance(d, dict) or not isinstance(d.get("attacks"), list):
        raise ValueError(f"{path.replace(os.sep, '/')} is not a design (no list of attacks)")
    d["_file"] = name                                        # (never saved: save_json drops it)
    return d


def load_record(designs, name):
    path = record_path(designs, name)
    if not os.path.isfile(path):
        return {"schema": 1, "set": name, "approved": None, "history": []}
    with open(path, encoding="utf-8") as fh:
        try:
            rec = json.load(fh)
        except ValueError as e:
            raise ValueError(f"{path.replace(os.sep, '/')} is not valid JSON ({e}): repair it by hand, never delete it "
                             "(it holds the owner's yes)") from e
    if not isinstance(rec, dict):
        raise ValueError(f"{path.replace(os.sep, '/')} is not a design record")
    rec.setdefault("approved", None)
    rec.setdefault("history", [])
    return rec


def save_json(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    if isinstance(data, dict) and "_file" in data:
        data = {k: v for k, v in data.items() if k != "_file"}
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def design_id(d):
    """the design AS IT IS: its attacks' design fields in order (a note, a comment or a move file's path is not it)"""
    rows = [{k: a.get(k) for k in FIELDS} for a in d.get("attacks") or [] if isinstance(a, dict)]
    blob = json.dumps({"set": d.get("set"), "weapon": d.get("weapon"), "links": d.get("links"), "attacks": rows},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def label(i, a):
    name = a.get("name") if isinstance(a, dict) else None
    return f"attack {i + 1} ({name if isinstance(name, str) and name else 'no name'})"


# ---------------------------------------------------------------- the design against itself
def is_todo(v):
    """a field still to fill in: the template's "TODO..." (a word that only CONTAINS those letters is not one)"""
    if isinstance(v, str):
        t = v.strip()
        return t == "TODO" or t.startswith("TODO:") or t.startswith("TODO ")
    if isinstance(v, dict):
        return any(is_todo(x) for x in v.values())
    if isinstance(v, list):
        return any(is_todo(x) for x in v)
    return False


def field_problems(d):
    """what makes the design not whole -> [words]"""
    out = []
    attacks = d.get("attacks") or []
    if not isinstance(d.get("set"), str) or not d.get("set"):
        out.append("the design does not name its set")
    elif d.get("_file") and d["set"] != d["_file"]:
        out.append(f"the design in {d['_file']}.design.json names its set '{d['set']}': a design is filed under its set's name")
    if len(attacks) < 2:
        out.append(f"a set is two attacks or more (this one has {len(attacks)})")
    if is_todo(d.get("links")):
        out.append("the design still has TODO in links")
    elif d.get("links") not in LINKS:
        out.append(f"the design's links is '{d.get('links')}' - pose (every attack ends where the next starts) or blend (the "
                   "game blends from one to the next)")
    names = [a.get("name") for a in attacks if isinstance(a, dict) and isinstance(a.get("name"), str)]
    for i, a in enumerate(attacks):
        if not isinstance(a, dict):
            out.append(f"attack {i + 1} is not an attack")
            continue
        who = label(i, a)
        todo = [k for k in fields_of(d) if is_todo(a.get(k))]
        if todo:
            out.append(f"{who} still has TODO in " + ", ".join(todo))
            continue
        if not isinstance(a.get("name"), str) or not a.get("name"):
            out.append(f"attack {i + 1} has no name (a name is one word, the move's)")
        elif names.count(a["name"]) > 1:
            out.append(f"{who}: two attacks share this name")
        for key, words in (("cut", CUTS), ("height", HEIGHTS), ("body", BODY), ("intent", INTENTS)):
            if a.get(key) not in words:
                out.append(f"{who}: its {key} is '{a.get(key)}' - one of {', '.join(words)}")
        fr = a.get("frames")
        if not isinstance(fr, dict) or any(not isinstance(fr.get(k), int) or isinstance(fr.get(k), bool) or fr.get(k) < 1
                                           for k in ("windup", "active", "recovery")):
            out.append(f"{who}: its frames are windup / active / recovery, each a whole number of frames at 60 a second")
        for key, what in (("starts", "the guard it starts from"), ("ends", "the pose it ends in"))[
                0 if "starts" in fields_of(d) else 1:]:
            if not isinstance(a.get(key), str) or len(a.get(key).strip()) < 8:
                out.append(f"{who}: '{key}' says in words {what}")
        nxt = a.get("next")
        if not isinstance(nxt, list) or any(not isinstance(n, str) for n in nxt):
            out.append(f"{who}: 'next' is the list of the attacks that may follow it ([] = the string ends here)")
        else:
            for n in nxt:
                if n == a.get("name"):
                    out.append(f"{who}: it names itself as what follows it")
                elif n not in names:
                    out.append(f"{who}: it is followed by '{n}', which is not an attack of this set")
    if d.get("links") == "pose":
        # a string linked by pose: each attack starts in the pose the one before it ends in - said the same way
        by = {a["name"]: a for a in attacks if isinstance(a, dict) and isinstance(a.get("name"), str)}
        for i, a in enumerate(attacks):
            if not isinstance(a, dict) or not isinstance(a.get("next"), list) or not isinstance(a.get("ends"), str):
                continue
            for n in a["next"]:
                b = by.get(n) if isinstance(n, str) else None
                if (isinstance(b, dict) and isinstance(b.get("starts"), str) and not is_todo(b.get("starts"))
                        and not is_todo(a.get("ends")) and _words(b["starts"]) != _words(a["ends"])):
                    out.append(f"{label(i, a)} ends in '{a['ends'].strip()}' but {n}, which follows it, starts from "
                               f"'{b['starts'].strip()}': a string linked by pose starts each attack where the one before ends")
    return out


def _words(text):
    """a pose said in words, for comparing two sayings of it (case, spacing and the end stop do not count)"""
    return " ".join(str(text).lower().replace(".", " ").split())


def design_cousins(d):
    """two attacks with the same cut, height and body -> [words]"""
    out = []
    attacks = [a for a in d.get("attacks") or [] if isinstance(a, dict)]
    for i, a in enumerate(attacks):
        for j in range(i + 1, len(attacks)):
            b = attacks[j]
            if all(a.get(k) in v and a.get(k) == b.get(k) for k, v in (("cut", CUTS), ("height", HEIGHTS), ("body", BODY))):
                out.append(f"{label(i, a)} and {label(j, b)} are COUSINS by design: both {a['cut']} / {a['height']} / {a['body']}")
    return out


# ---------------------------------------------------------------- the design against the moves' keys
def wheel_of(b0, b1, chord):
    """the cut's direction as the player sees it (the camera behind: x right, y up; -z, forward, is depth) from the
    blade's direction where its fast run starts (b0) and ends (b1) and the tip's travel between them (chord, a unit)
    -> (its name, its angle or None, sure). A THRUST: the blade keeps its direction (it turns under THRUST_SWEEP
    degrees) and travels along itself. A cut: the way the blade's direction CHANGED, seen from behind. sure = False
    when that change runs mostly in depth (a rising or falling cut straight at the target): its screen direction is
    then not held against the design"""
    b0, b1, chord = (np.asarray(v, float) for v in (b0, b1, chord))
    sweep = math.degrees(math.acos(float(np.clip(np.dot(b0, b1), -1.0, 1.0))))
    if sweep < THRUST_SWEEP and abs(float(np.dot(chord, (b0 + b1) / max(float(np.linalg.norm(b0 + b1)), 1e-9)))) >= THRUST:
        return "thrust", None, True
    turn = b1 - b0
    n = float(np.linalg.norm(turn))
    if n < 1e-9:
        return "thrust", None, False
    ang = math.degrees(math.atan2(turn[1], turn[0])) % 360.0
    name = min(WHEEL, key=lambda k: min(abs(ang - WHEEL[k]), 360.0 - abs(ang - WHEEL[k])))
    return name, ang, float(np.linalg.norm(turn[:2])) / n >= SCREEN_SHARE


def height_of(y):
    return "high" if y >= HIGH_Y else "low" if y <= LOW_Y else "mid"


def measure(move):
    """a strike move's keys -> what the design is held against (the clip is generated in memory: nothing is built)"""
    import clip as C
    import strike as S
    if not isinstance(move, dict) or not isinstance(move.get("keys"), list) or len(move["keys"]) < 2:
        raise ValueError("it is not a strike move's key list")
    gen = copy.deepcopy(move)
    gen.pop("step", None)
    c, _ = S.generate(gen)
    sw = c.get("sword") or {}
    if not sw.get("tip") or not sw.get("grip_path"):
        raise ValueError("its keys give no blade to measure")
    fps = float(c.get("fps") or 60)
    tip, grip = np.array(sw["tip"], float), np.array(sw["grip_path"], float)
    last = len(tip) - 1
    speed = np.r_[0.0, np.linalg.norm(np.diff(tip, axis=0), axis=1)]
    hit = next((float(e["t"]) for e in c.get("events") or [] if e.get("name") == "Hit"), None)
    if hit is None:
        raise ValueError("its keys give no Hit: not an attack to measure")
    hi = int(round(hit * fps))
    hi = max(1, min(last - 1, hi)) if last >= 2 else 0
    lo, up = max(0, hi - int(0.4 * fps)), min(last, hi + int(0.15 * fps))
    pk = lo + int(np.argmax(speed[lo:up + 1]))
    a = pk
    while a > 0 and speed[a - 1] >= 0.5 * speed[pk]:
        a -= 1
    b = pk
    while b < last and speed[b + 1] >= 0.5 * speed[pk]:
        b += 1
    a0 = max(a - 1, 0)
    chord = tip[b] - tip[a0]                                 # the cut: where the blade's fast run starts to where it ends
    chord = chord / max(float(np.linalg.norm(chord)), 1e-9)
    blade0 = (tip[a0] - grip[a0]) / max(float(np.linalg.norm(tip[a0] - grip[a0])), 1e-9)
    blade1 = (tip[b] - grip[b]) / max(float(np.linalg.norm(tip[b] - grip[b])), 1e-9)
    cut, ang, sure = wheel_of(blade0, blade1, chord)
    idx = [int(round(x)) for x in np.r_[np.linspace(0, hi, SAMPLES // 2, endpoint=False), np.linspace(hi, last, SAMPLES - SAMPLES // 2)]]
    rig = C.load_rig("r6")
    W = C.world_frames(c, rig)
    return {"frames": last, "fps": fps, "hit_frame": hi, "cut": cut, "cut_deg": None if ang is None else round(ang, 1),
            "cut_sure": bool(sure), "chord": chord.tolist(),
            "height": height_of(float((tip[hi][1] + grip[hi][1]) / 2.0)), "height_y": round(float((tip[hi][1] + grip[hi][1]) / 2.0), 2),
            "path": np.array([tip[i] for i in idx]),
            **link_ends(move, c, W),
            "clip": c, "marks": {"windup": a0, "hit": hi, "end": last}}


def pair_distance(a, b):
    """-> (the blades' mean distance in studs: what tells cousins; the angle between the two cuts in degrees: said)"""
    path = float(np.linalg.norm(a["path"] - b["path"], axis=1).mean())
    dot = float(np.clip(np.dot(a["chord"], b["chord"]), -1.0, 1.0))
    return path, math.degrees(math.acos(dot))


def wheel_gap(designed, m):
    """degrees between the designed direction and the keys' own (0 when both are thrusts; None = one is a thrust)"""
    if designed == "thrust" or m["cut"] == "thrust":
        return 0.0 if designed == m["cut"] else None
    d = abs(WHEEL[designed] - m["cut_deg"]) % 360.0
    return min(d, 360.0 - d)


def link_ends(move, c, W):
    """the poses a string links on: the move's FIRST and LAST frame as the game plays it - with its `step` block (a
    stepped clip ends on a held pose) and at 60 frames a second (at 30 the same keys end elsewhere: two loved strings
    read 7 to 22 degrees apart) - and the blade's direction at both"""
    import clip as C
    import strike as S
    if move.get("step") or float(c.get("fps") or 60) != 60.0:
        c = S.generate({**copy.deepcopy(move), "fps": 60})[0]
        W = C.world_frames(c, C.load_rig("r6"))
    sw, n = c.get("sword") or {}, len(W) - 1

    def blade(i):
        t = np.array(sw["tip"][min(i, len(sw["tip"]) - 1)], float)
        g = np.array(sw["grip_path"][min(i, len(sw["grip_path"]) - 1)], float)
        return (t - g) / max(float(np.linalg.norm(t - g)), 1e-9)
    has = bool(sw.get("tip")) and bool(sw.get("grip_path"))
    return {"first": {j: W[0][j][:3, :3] for j in W[0]}, "final": {j: W[n][j][:3, :3] for j in W[n]},
            "blade_first": blade(0) if has else None, "blade_final": blade(n) if has else None}


def link_deg(a, b):
    """what is furthest apart between where one attack ends and the next starts: a joint, or the blade's direction
    (a blade can point 40 degrees off with the arms 12 apart) -> (degrees, its name)"""
    worst = (0.0, None)
    for j, A in a["final"].items():
        B = b["first"].get(j)
        if B is None:
            continue
        deg = math.degrees(math.acos(max(-1.0, min(1.0, (float(np.trace(A.T @ B)) - 1.0) / 2.0))))
        if deg > worst[0]:
            worst = (deg, j)
    if a.get("blade_final") is not None and b.get("blade_first") is not None:
        deg = math.degrees(math.acos(float(np.clip(np.dot(a["blade_final"], b["blade_first"]), -1.0, 1.0))))
        if deg > worst[0]:
            worst = (deg, "the blade")
    return worst


def check(d, base="."):
    """-> {id, problems: [words], notes: [words], measured: {name: {...}}, whole: bool}. problems fail the design"""
    fields = field_problems(d)
    problems = list(fields) + design_cousins(d)
    notes, measured = [], {}
    # (an attack keeps its place in the FILE in every sentence; one that is not an attack, or has no name, is said
    # by field_problems and measured against nothing)
    attacks = [a if isinstance(a, dict) and isinstance(a.get("name"), str) and a.get("name") else {} for a in d.get("attacks") or []]
    for i, a in enumerate(attacks):
        mp = a.get("move")
        if not mp or not isinstance(mp, str):
            continue
        who = label(i, a)
        path = mp if os.path.isabs(mp) else os.path.join(base, mp)
        if not os.path.isfile(path):
            problems.append(f"{who} names a move file that is not there ({mp})")
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                m = measure(json.load(fh))
        except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
            problems.append(f"{who}: its move file cannot be measured ({mp}: {e})")
            continue
        measured[a["name"]] = m
        if a.get("cut") in CUTS:
            gap = wheel_gap(a["cut"], m)
            if not m["cut_sure"] and gap is not None and gap > 90.0:
                # mostly in depth, but the blade still turns the OTHER way on the screen (an "up" whose keys chop down)
                problems.append(f"{who} is designed as a {a['cut']} cut and its keys cut the other way ({m['cut']}, "
                                f"{gap:.0f} deg off, mostly in depth)")
            elif not m["cut_sure"]:
                notes.append(f"{who}: its keys cut mostly in depth (toward the target), so the {a['cut']} of the design is "
                             "held only against its opposite")
            elif gap is None or gap > CUT_OFF:
                problems.append(f"{who} is designed as a {a['cut']} cut and its keys cut {m['cut']}"
                                + (f" ({gap:.0f} deg off)" if gap is not None else ""))
        if a.get("height") in HEIGHTS and a["height"] != m["height"]:
            # (a height is where it lands on the TARGET; the keys only say where the blade is at the Hit: said, never failed)
            notes.append(f"{who} is designed {a['height']}; at the Hit its blade is {m['height']} (y {m['height_y']})")
        fr = a.get("frames")
        if isinstance(fr, dict) and all(isinstance(fr.get(k), int) for k in ("windup", "active", "recovery")):
            if abs(fr["windup"] - m["hit_frame"]) > max(3, 0.25 * fr["windup"]):
                problems.append(f"{who}: its wind-up is designed as {fr['windup']} frame(s) and its keys reach the Hit at frame {m['hit_frame']}")
            total = fr["windup"] + fr["active"] + fr["recovery"]
            if abs(total - m["frames"]) > max(4, 0.2 * total):
                problems.append(f"{who}: it is designed as {total} frame(s) long and its keys run {m['frames']}")
    names = [a.get("name") for a in attacks]
    for i in range(len(attacks)):
        for j in range(i + 1, len(attacks)):
            a, b = measured.get(names[i]), measured.get(names[j])
            if a is None or b is None:
                continue
            path, cut = pair_distance(a, b)
            ha, hb = attacks[i].get("height"), attacks[j].get("height")
            if (path < COUSIN_PATH and ha in HEIGHTS and hb in HEIGHTS and ha != hb
                    and abs(a["height_y"] - b["height_y"]) >= HEIGHT_APART):
                # designed at two heights AND measured at two heights: the same cut at the head and at the hips is two
                # attacks (the blades of a high and a low horizontal cut run about 2.5 studs apart) - said, not failed
                notes.append(f"{label(i, attacks[i])} and {label(j, attacks[j])} run {path:.1f} studs apart: the same cut at two "
                             f"heights ({ha} at y {a['height_y']}, {hb} at y {b['height_y']})")
            elif path < COUSIN_PATH:
                problems.append(f"{label(i, attacks[i])} and {label(j, attacks[j])} are COUSINS: their blades run {path:.1f} studs "
                                f"apart on average, cutting within {cut:.0f} deg of each other (one cut made again measures up to "
                                f"{RESKIN_PATH:.1f} studs from itself; the closest two attacks of a set he loved are {LOVED_PATH:.1f} apart)")
            elif path < LOVED_PATH:
                notes.append(f"{label(i, attacks[i])} and {label(j, attacks[j])} are closer than any two attacks of a set he loved "
                             f"({path:.1f} studs apart; the loved sets' closest pair: {LOVED_PATH:.1f})")
    for i, a in enumerate(attacks):
        for n in a.get("next") or [] if isinstance(a.get("next"), list) else []:
            if isinstance(n, str) and d.get("links") == "pose" and not (a.get("name") in measured and n in measured):
                notes.append(f"the link from {label(i, a)} to {n} is NOT measured yet (no keys for both): linked by pose "
                             "is a claim until they exist")
            if isinstance(n, str) and a.get("name") in measured and n in measured:
                deg, joint = link_deg(measured[a["name"]], measured[n])
                said = f"{label(i, a)} ends {deg:.0f} deg from where {n} starts ({joint or 'no joint'})"
                if d.get("links") == "pose" and deg > LINK_BAR:
                    problems.append(f"the string BREAKS: {said} - a set linked by pose links within {LINK_BAR:.0f} (every link of "
                                    f"the two strings he loved is under {LOVED_LINK:.0f})")
                elif d.get("links") == "blend":
                    notes.append(f"{said}: the game blends across it (the set is linked by blend)")
                else:
                    notes.append(f"{said}: the string's link"
                                 + (f" - every link of the two strings he loved is under {LOVED_LINK:.0f} deg" if deg > LOVED_LINK else ""))
    return {"id": design_id(d), "problems": problems, "notes": notes, "measured": measured, "whole": not fields}


def seen_path(png):
    return png + ".json"


def his_yes(ap):
    """a recorded approval counts only as the owner's own, in his words, to a PAGE that was drawn (its picture's hash
    and the problems printed on it) -> why not ('' = it counts). A record typed by hand without them is no yes"""
    if not isinstance(ap, dict):
        return "no yes is recorded"
    if ap.get("by") != "owner" or not str(ap.get("words") or "").strip():
        return "the recorded yes is not the owner's own, in his words"
    seen = ap.get("seen")
    if (not isinstance(seen, dict) or not isinstance(seen.get("page_sha256"), str) or len(seen["page_sha256"]) != 64
            or not isinstance(seen.get("problems"), list) or seen.get("id") != ap.get("id")):
        return "the recorded yes names no page he saw: it was not made by --approve on a drawn page"
    if list(ap.get("accepted") or []) != list(seen["problems"]):
        return "the recorded yes accepts problems that were not the ones on the page he saw: it was edited by hand"
    return ""


def state_of(d, rec, result=None):
    """-> {state, words, failing: [problems not accepted by his yes]}. draft = not whole; waiting; approved; stale"""
    result = result or check(d)
    ap = rec.get("approved") if isinstance(rec, dict) else None
    typed = his_yes(ap) if ap else ""
    if typed:
        ap = None
    now = result["id"]
    if ap and ap.get("id") == now:
        accepted = set(ap.get("accepted") or [])
        failing = [p for p in result["problems"] if p not in accepted]
        words = f"approved by the owner {ap.get('date')}: \"{ap.get('words')}\" (design {now})"
        if ap.get("accepted"):
            words += f"; {len(ap['accepted'])} problem(s) were on the page he approved"
        return {"state": "approved", "words": words, "failing": failing}
    if ap:
        return {"state": "stale", "failing": result["problems"],
                "words": f"the owner's yes ({ap.get('date')}: \"{ap.get('words')}\") was to design {ap.get('id')}; it is now {now}: "
                         "the design changed since"}
    if not result["whole"]:
        return {"state": "draft", "failing": result["problems"], "words": "the design is not whole yet: " + result["problems"][0]}
    return {"state": "waiting", "failing": result["problems"],
            "words": "the owner has not seen or approved this design yet" + (f" ({typed})" if typed else "")}


def approve(d, rec, words, by, saw, today=None, result=None, page_png=None):
    """his yes to the design as it is, on the PAGE he saw: the page must be drawn, be of this very design, and carry
    the problems the design has now (what he accepts is what was printed on it)"""
    if by != "owner":
        raise ValueError("only the owner approves a design (--by owner, with his words)")
    if not words or not words.strip():
        raise ValueError("an approval needs the owner's words")
    result = result or check(d)
    if not result["whole"]:
        raise ValueError("a design that is not whole cannot be approved: " + field_problems(d)[0])
    if not saw:
        raise ValueError("name the design he said yes to: --id <the id on the page he saw>")
    if saw != result["id"]:
        raise ValueError(f"his yes was to design {saw} and the design is now {result['id']}: show him the page as it is")
    if not page_png or not os.path.isfile(page_png) or not os.path.isfile(seen_path(page_png)):
        raise ValueError("no page of this design was drawn: draw it (lune run kit anim design <Set>), show him THAT page")
    with open(seen_path(page_png), encoding="utf-8") as fh:
        seen = json.load(fh)
    with open(page_png, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    if seen.get("id") != result["id"] or seen.get("page_sha256") != sha:
        raise ValueError("the page on disk is not this design's: draw it again and show him that one")
    if list(seen.get("problems") or []) != list(result["problems"]):
        raise ValueError("the design's problems changed since the page was drawn (its moves' keys moved): draw it again "
                         "and show him that one")
    if rec.get("approved"):
        rec["history"].append({**rec["approved"], "why": "a new yes"})
    rec["approved"] = {"words": words.strip(), "by": "owner", "date": today or datetime.date.today().isoformat(),
                       "id": result["id"], "accepted": list(result["problems"]),
                       "seen": {"id": result["id"], "page_sha256": sha, "problems": list(result["problems"])}}
    return rec


# ---------------------------------------------------------------- the lock
def designs_in(designs):
    """every design of the folder -> ([(set, design)], [the files that cannot be read, with why])"""
    out, broken = [], []
    if not os.path.isdir(designs):
        return out, broken
    for f in sorted(os.listdir(designs)):
        if not f.endswith(".design.json"):
            continue
        try:
            out.append((f[:-len(".design.json")], load(designs, f[:-len(".design.json")])))
        except (ValueError, OSError) as e:
            broken.append(f"{f} ({e})")
    return out, broken


def style_sets(style_paths):
    """the games' styles -> ({set: [moves]}, [the style files that cannot be read])"""
    sets, broken = {}, []
    for path in style_paths or []:
        if not path or not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                st = json.load(fh)
            listed = st.get("sets") if isinstance(st, dict) else None
            if listed is None:
                continue
            if not isinstance(listed, dict) or any(not isinstance(v, list) for v in listed.values()):
                raise ValueError("its \"sets\" is not {set: [moves]}")
        except (OSError, ValueError) as e:
            broken.append(f"{path.replace(os.sep, '/')} ({e})")
            continue
        for k, v in listed.items():
            sets.setdefault(k, []).extend(n for n in v if isinstance(n, str))
    return sets, broken


def lock(names, designs, anims, style_paths=None):
    """-> {"held": {name: words}, "free": {name: words}}. What cannot be read frees nothing: a design or a style file
    that is broken holds every move asked about (it may be the one that names it)"""
    import blocking as B
    out = {"held": {}, "free": {}}
    if isinstance(style_paths, str):
        style_paths = [style_paths]
    sets, bad_styles = style_sets(style_paths)
    every, bad_designs = designs_in(designs)
    before = B.before_rule(anims)
    for name in names:
        if name in before:
            out["free"][name] = "it was made before the rule (blocks/_before_blocking.json): never asked"
            continue
        if bad_designs or bad_styles:
            out["held"][name] = ("a design or style file cannot be read, so nobody can say whether it names this move: "
                                 + "; ".join(bad_designs + bad_styles))
            continue
        named = [(sn, d) for sn, d in every if any(isinstance(a, dict) and a.get("name") == name for a in d["attacks"])]
        if not named:
            in_set = next((sn for sn, moves in sets.items() if name in moves), None)
            if in_set:
                out["held"][name] = (f"it is an attack of the set {in_set} (the game's style) and no design page names it: "
                                     "a set starts with its design")
            else:
                out["free"][name] = "no design names it and no set of the game's style lists it: a move on its own"
            continue
        for set_name, d in named:
            try:
                st = state_of(d, load_record(designs, set_name), check(d))
            except (ValueError, TypeError, KeyError, AttributeError) as e:
                out["held"][name] = f"its set's design or its record cannot be read ({e})"
                break
            if st["state"] != "approved":
                out["held"][name] = f"its set {set_name} has no yes from the owner to its design: {st['words']}"
                break
            if st["failing"]:
                out["held"][name] = (f"its set {set_name}'s design has a problem that was not on the page he approved: "
                                     f"{st['failing'][0]}")
                break
        else:
            out["free"][name] = "its set's design has the owner's yes as it is now: " + ", ".join(sn for sn, _ in named)
    return out


# ---------------------------------------------------------------- the page
def _wheel(size, cut, measured=None):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (size, size), (250, 250, 252))
    dr = ImageDraw.Draw(im)
    c, r = size / 2.0, size * 0.40
    dr.ellipse([c - r, c - r, c + r, c + r], outline=(150, 152, 160), width=2)
    for ang in WHEEL.values():
        x, y = c + r * math.cos(math.radians(ang)), c - r * math.sin(math.radians(ang))
        dr.line([c, c, x, y], fill=(214, 216, 222), width=1)

    def arrow(ang, colour, width, reach=1.0):
        # the blade TRAVELS this way: the arrow runs through the centre, its head where the cut ends
        dx, dy = math.cos(math.radians(ang)), -math.sin(math.radians(ang))
        x0, y0, x1, y1 = c - dx * r * reach, c - dy * r * reach, c + dx * r * reach, c + dy * r * reach
        dr.line([x0, y0, x1, y1], fill=colour, width=width)
        for turn in (150, -150):
            a2 = math.radians(ang + turn)
            dr.line([x1, y1, x1 + math.cos(a2) * r * 0.28, y1 - math.sin(a2) * r * 0.28], fill=colour, width=width)
    if measured is not None and measured.get("cut_deg") is not None:
        arrow(measured["cut_deg"], (40, 120, 200), 3, 0.8)          # the keys' own cut, under the designed one
    if cut in WHEEL:
        arrow(WHEEL[cut], (200, 40, 40), 6)
    elif cut == "thrust":
        dr.ellipse([c - r * 0.25, c - r * 0.25, c + r * 0.25, c + r * 0.25], fill=(200, 40, 40))
        dr.ellipse([c - r * 0.6, c - r * 0.6, c + r * 0.6, c + r * 0.6], outline=(200, 40, 40), width=4)
    return im


def _budget(width, height, fr, scale, measured=None):
    """windup | active | recovery as one bar, `scale` px a frame; the keys' own Hit and end marked under it"""
    from PIL import Image, ImageDraw
    import pose_sheet as PS
    im = Image.new("RGB", (width, height), (250, 250, 252))
    dr = ImageDraw.Draw(im)
    fnt = PS.font(18, True)
    x, top, bot = 8, 34, height - 44
    if isinstance(fr, dict) and all(isinstance(fr.get(k), int) for k in ("windup", "active", "recovery")):
        dr.text((x, top - 28), f"wind-up {fr['windup']}  |  active {fr['active']}  |  recovery {fr['recovery']}   (frames)",
                font=fnt, fill=(40, 42, 50))
        for key, colour in (("windup", (120, 150, 200)), ("active", (210, 60, 50)), ("recovery", (160, 164, 172))):
            w = max(2, int(round(fr[key] * scale)))
            dr.rectangle([x, top, x + w, bot], fill=colour)
            x += w
        if measured is not None:
            hx, ex = 8 + measured["hit_frame"] * scale, 8 + measured["frames"] * scale
            dr.line([hx, bot + 4, hx, bot + 30], fill=(40, 120, 200), width=4)
            dr.line([ex, bot + 4, ex, bot + 30], fill=(40, 120, 200), width=4)
            dr.text((hx + 6, bot + 8), f"the keys: Hit at {measured['hit_frame']}, {measured['frames']} long", font=PS.font(16),
                    fill=(40, 120, 200))
    else:
        dr.text((8, top), "frames: TODO", font=fnt, fill=(200, 40, 40))
    return im


def _silhouettes(m, cell):
    """the attack's wind-up, Hit and end as silhouettes from the player's camera (kit/anim/thumbs.py): ONE scale for
    the three (the body keeps its size from cell to cell), each centred on its own box, the blade in red (black on a
    black body it was not there)"""
    from PIL import Image, ImageDraw
    import clip as C
    import pose_sheet as PS
    import thumbs as T
    rig = C.load_rig("r6")
    W = C.world_frames(m["clip"], rig)
    shots = []
    for tag in ("windup", "hit", "end"):
        i = m["marks"][tag]
        blade = T.blade(m["clip"], i)
        hs = T.hulls(W[i], rig, T.VIEWS["player"], blade)
        pts = np.concatenate(hs)
        lo, hi = pts.min(0), pts.max(0)
        shots.append((tag, hs, blade is not None, (lo + hi) / 2.0, float(max(hi - lo))))
    span = max(sh[4] for sh in shots) * 0.55 + 0.4
    cells = []
    for tag, hs, has_blade, ctr, _ in shots:
        im = Image.new("RGB", (cell, cell), (250, 250, 252))
        dr = ImageDraw.Draw(im)
        for k, H in enumerate(hs):
            px = [((p[0] - ctr[0]) / span * cell / 2 + cell / 2, cell / 2 - (p[1] - ctr[1]) / span * cell / 2) for p in H]
            if len(px) >= 3:
                is_blade = has_blade and k == len(hs) - 1
                dr.polygon(px, fill=(200, 40, 40) if is_blade else (12, 12, 14), outline=(200, 40, 40) if is_blade else None)
        dr.text((6, 4), {"windup": "wind-up", "hit": "HIT", "end": "end"}[tag], font=PS.font(16, True), fill=(200, 40, 40))
        cells.append(im)
    return cells


def page(d, result, rec, out):
    """the design page -> out (png)"""
    from PIL import Image, ImageDraw
    import pose_sheet as PS
    attacks = [a for a in d.get("attacks") or [] if isinstance(a, dict)]
    st = state_of(d, rec, result)
    cell, text_w, budget_w = 220, 420, 620
    longest = max([sum(a["frames"].get(k, 0) for k in ("windup", "active", "recovery")) for a in attacks
                   if isinstance(a.get("frames"), dict) and all(isinstance(a["frames"].get(k), int) for k in ("windup", "active", "recovery"))]
                  + [max([m["frames"] for m in result["measured"].values()] + [1])])
    scale = (budget_w - 20) / float(max(longest, 1))
    rows = []
    for i, a in enumerate(attacks):
        m = result["measured"].get(a.get("name")) if isinstance(a.get("name"), str) else None
        words = Image.new("RGB", (text_w, cell * 4), (250, 250, 252))
        dr = ImageDraw.Draw(words)
        y = 8
        for line, bold, ink in ((f"{i + 1}. {a.get('name')}", True, (16, 17, 21)),
                                (f"{a.get('cut')}  /  {a.get('height')}  /  {a.get('body')}", True, (200, 40, 40)),
                                (f"intent: {a.get('intent')}", False, (40, 42, 50)),
                                (f"starts: {a.get('starts')}", False, (40, 42, 50)),
                                (f"ends: {a.get('ends')}", False, (40, 42, 50)),
                                ("then: " + (", ".join(str(n) for n in a.get("next") or []) if isinstance(a.get("next"), list)
                                             and a.get("next") else "the string ends here"), False, (40, 42, 50)),
                                ((f"its keys: {m['cut']}" + (f" ({m['cut_deg']:.0f} deg)" if m["cut_deg"] is not None else "")
                                  + f", {m['height']}") if m else "no keys yet: nothing measured", False, (40, 120, 200))):
            fnt = PS.font(22 if bold else 18, bold)
            for part in PS.wrap(str(line), fnt, text_w - 16)[:8]:
                dr.text((8, y), part, font=fnt, fill=ink)
                y += int(fnt.size * 1.3)
        words = words.crop((0, 0, text_w, max(cell, min(y + 8, cell * 4))))     # (the row is as tall as its words)
        panes = [words, _wheel(cell, a.get("cut"), m), _budget(budget_w, cell, a.get("frames"), scale, m)]
        if m:
            panes += _silhouettes(m, cell)
        rows.append(PS.row_of(panes))
    width = max(r.width for r in rows) if rows else 1200
    head = [PS.bar(width, f"DESIGN of the set {d.get('set')} (id {result['id']}) - {len(attacks)} attack(s)"
                          + (f", {d.get('weapon')}" if d.get("weapon") else "")
                          + (f", linked by {d.get('links')}" if d.get("links") in LINKS else "")
                          + ": is this the string, before anything is posed?", height=58, size=28, fill=(30, 44, 74)),
            PS.bar(width, f"{st['state'].upper()}: {st['words']}", height=40, size=19, bold=False,
                   fill=PS.NOTE_FILL["answered"][0] if st["state"] == "approved" else PS.NOTE_FILL["open"][0],
                   ink=PS.NOTE_FILL["answered"][1] if st["state"] == "approved" else PS.NOTE_FILL["open"][1]),
            PS.bar(width, "red arrow = the designed cut as the player sees it (the camera behind)  |  blue = what the move's "
                          "keys measure  |  the bar = wind-up, active, recovery at 60 frames a second, one scale for the set",
                   height=38, size=18, bold=False, fill=(46, 48, 56))]
    for p in result["problems"]:
        head.append(PS.bar(width, "PROBLEM: " + p, height=40, size=19, fill=(110, 28, 28), ink=(255, 220, 214)))
    for n in result["notes"]:
        head.append(PS.bar(width, "note: " + n, height=36, size=17, bold=False, fill=(52, 54, 62), ink=(214, 216, 224)))
    # the string's rhythm: every attack's budget in its order on one bar
    total = sum(sum(a["frames"].get(k, 0) for k in ("windup", "active", "recovery")) for a in attacks
                if isinstance(a.get("frames"), dict) and all(isinstance(a["frames"].get(k), int) for k in ("windup", "active", "recovery")))
    rhythm = Image.new("RGB", (width, 96), (250, 250, 252))
    dr = ImageDraw.Draw(rhythm)
    dr.text((8, 4), f"the string's rhythm, one bar ({total} frames = {total / 60.0:.2f} s if every attack ran whole)", font=PS.font(18, True),
            fill=(40, 42, 50))
    x, k = 8.0, (width - 16) / float(max(total, 1))
    for i, a in enumerate(attacks):
        fr = a.get("frames")
        if not (isinstance(fr, dict) and all(isinstance(fr.get(key), int) for key in ("windup", "active", "recovery"))):
            continue
        dr.text((x + 2, 30), str(i + 1), font=PS.font(16, True), fill=(40, 42, 50))
        for key, colour in (("windup", (120, 150, 200)), ("active", (210, 60, 50)), ("recovery", (160, 164, 172))):
            w = fr[key] * k
            dr.rectangle([x, 52, x + w, 88], fill=colour, outline=(250, 250, 252))
            x += w
    sheet = PS.stack(head + [rhythm] + rows, gap=6)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sheet.save(out)
    # what this page showed (approve reads it: his yes is to THIS picture and the problems printed on it)
    with open(out, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    with open(seen_path(out), "w", encoding="utf-8") as fh:
        json.dump({"id": result["id"], "page_sha256": sha, "problems": list(result["problems"])}, fh, indent=1)
    return out


# ---------------------------------------------------------------- making a design
def template(name, n, weapon=None):
    return {"schema": 2, "set": name, "weapon": weapon or "TODO",
            "links": "TODO: pose (every attack ends where the next starts) / blend (the game blends between them)",
            "attacks": [{"name": f"{name}{i + 1}", "cut": "TODO: one of " + ", ".join(CUTS),
                         "height": "TODO: " + " / ".join(HEIGHTS), "body": "TODO: one of " + ", ".join(BODY),
                         "intent": "TODO: " + " / ".join(INTENTS), "frames": {"windup": "TODO", "active": "TODO", "recovery": "TODO"},
                         "starts": "TODO: the guard it starts from, in words", "ends": "TODO: the pose it ends in, in words",
                         "next": [f"{name}{i + 2}"] if i + 1 < n else []} for i in range(n)]}


def from_moves(name, paths, weapon=None):
    """a design of moves that exist: what the keys measure is filled in, the rest is TODO"""
    attacks, measured = [], []
    stems = [os.path.basename(p).split(".")[0] for p in paths]
    for i, p in enumerate(paths):
        with open(p, encoding="utf-8") as fh:
            move = json.load(fh)
        m = measure(move)
        measured.append(m)
        attacks.append({"name": stems[i], "cut": m["cut"], "height": m["height"], "body": "TODO: one of " + ", ".join(BODY),
                        "intent": "TODO: " + " / ".join(INTENTS),
                        "frames": {"windup": int(m["hit_frame"]), "active": 1, "recovery": max(1, int(m["frames"] - m["hit_frame"] - 1))},
                        "starts": "TODO: the guard it starts from, in words", "ends": "TODO: the pose it ends in, in words",
                        "next": [stems[i + 1]] if i + 1 < len(stems) else [],
                        "move": p.replace(os.sep, "/")})
    far = [(link_deg(a, b)[0], i) for i, (a, b) in enumerate(zip(measured, measured[1:]))]
    broken = [f"{stems[i]} ends {deg:.0f} deg from where {stems[i + 1]} starts" for deg, i in far if deg > LINK_BAR]
    return {"schema": 2, "set": name, "weapon": weapon or "TODO",
            "links": "pose" if not broken else "TODO: pose / blend (measured: " + "; ".join(broken) + ")",
            "attacks": attacks}


def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def next_words(name, st, result):
    if st["state"] == "draft":
        return f"improve the design: fill it in ({design_path('<designs>', name)}), then lune run kit anim design {name}"
    if st["failing"]:
        return (f"improve the design: {st['failing'][0][:160]} - change the attack (its cut, height or body, or its keys), "
                f"then lune run kit anim design {name}")
    if st["state"] == "approved":
        return "none - the set's moves may be made: each new one starts with its blocking (lune run kit anim block <Move> --sheet)"
    if st["state"] == "stale":
        return f"look at the page as it is now and show the owner that one: lune run kit anim design {name}"
    return (f"look at the page yourself, then show the owner: his yes is lune run kit anim design {name} --approve "
            f"\"<his words>\" --by owner --id {result['id']}")


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        return _main(argv)
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, ZeroDivisionError) as e:
        what = f"{argv[1]} " if len(argv) > 1 else ""
        return emit("fail", f"anim design {what}: it could not be read or made ({type(e).__name__}: {e})",
                    "check the design file and the arguments, then lune run kit anim design <Set>")


def _main(argv):
    cmd = argv[0] if argv else "help"
    if cmd not in ("new", "from-moves", "check", "page", "approve", "state", "lock") or len(argv) < 2:
        print(__doc__)
        return 1
    designs = flag(argv, "--designs", os.path.join("assets", "animations", "designs"))
    if cmd == "lock":
        names = []
        for a in argv[1:]:
            if a.startswith("--"):
                break
            names.append(a)
        styles = [argv[k + 1] for k, a in enumerate(argv) if a == "--style" and k + 1 < len(argv)]
        r = lock(names, designs, flag(argv, "--anims", os.path.dirname(os.path.normpath(designs))), styles)
        if not r["held"]:
            return emit("pass", f"anim design lock: {len(names)} move(s) free to be made", "none - proceed", **r)
        first = next(n for n in names if n in r["held"])
        return emit("fail", f"anim {first}: STOP - a NEW move of a set whose design does not have the owner's yes: {r['held'][first]}. "
                            "The set first, then its moves (his method lists; the studio route's design page)"
                            + (f" - held: {', '.join(sorted(r['held']))}" if len(r["held"]) > 1 else ""),
                    "lune run kit anim design <Set>   (a new one: --new --attacks <n>) -> show the owner design.png -> his yes: "
                    "lune run kit anim design <Set> --approve \"<his words>\" --by owner --id <the id on the page he saw>", **r)
    name = argv[1]
    path = design_path(designs, name)
    if cmd == "new":
        if os.path.exists(path):
            return emit("fail", f"anim design {name}: {path.replace(os.sep, '/')} exists already", f"lune run kit anim design {name}")
        asked = flag(argv, "--attacks", "0")
        n = int(asked) if str(asked).isdigit() else 0
        if n < 2:
            return emit("fail", "anim design: a set is two attacks or more (--attacks <n>)", f"lune run kit anim design {name} --new --attacks 5")
        save_json(path, template(name, n, flag(argv, "--weapon")))
        return emit("pass", f"anim design {name}: {path.replace(os.sep, '/')} - {n} attack(s) to design (every TODO must go)",
                    f"improve the design: fill in each attack's cut, height, body, intent, frames, the pose it ends in and what "
                    f"follows it, then lune run kit anim design {name}", design=path.replace(os.sep, "/"))
    if cmd == "from-moves":
        if os.path.exists(path):
            return emit("fail", f"anim design {name}: {path.replace(os.sep, '/')} exists already", f"lune run kit anim design {name}")
        paths = []
        for a in argv[2:]:
            if a.startswith("--"):
                break
            paths.append(a)
        if len(paths) < 2:
            return emit("fail", "anim design: name two move files or more", f"lune run kit anim design {name} --from <a.move.json>,<b.move.json>")
        save_json(path, from_moves(name, paths, flag(argv, "--weapon")))
        return emit("pass", f"anim design {name}: {path.replace(os.sep, '/')} - {len(paths)} attack(s) measured from their keys "
                            "(direction, height, frames); body, intent and the end pose are still TODO",
                    f"improve the design: fill in what the keys cannot say, then lune run kit anim design {name}",
                    design=path.replace(os.sep, "/"))
    d = load(designs, name)
    rec = load_record(designs, name)
    result = check(d)
    st = state_of(d, rec, result)
    slim = {"id": result["id"], "state": st["state"], "problems": result["problems"], "notes": result["notes"]}
    if cmd == "approve":
        by = flag(argv, "--by", "")
        words = argv[2] if len(argv) > 2 and not argv[2].startswith("--") else ""
        try:
            rec = approve(d, rec, words, by, flag(argv, "--id"), result=result,
                          page_png=flag(argv, "--page", os.path.join(os.environ.get("KIT_BUILD", "build"), "animations",
                                                                     f"{name}.design.png")))
        except ValueError as e:
            return emit("fail", f"anim design {name}: {e}",
                        f"lune run kit anim design {name} --approve \"<his words>\" --by owner --id <the id on the page he saw>", **slim)
        save_json(record_path(designs, name), rec)
        kept = f" ({len(rec['approved']['accepted'])} problem(s) on the page are accepted with it)" if rec["approved"]["accepted"] else ""
        return emit("pass", f"anim design {name}: the owner's yes to design {result['id']} is recorded: \"{rec['approved']['words']}\"{kept}",
                    "none - the set's moves may be made: each new one starts with its blocking (lune run kit anim block <Move> --sheet)",
                    record=record_path(designs, name).replace(os.sep, "/"))
    if cmd == "state":
        need = flag(argv, "--need")
        # (approved AND failing is not "approved" for anything that waits on it: the lock holds such a set's moves)
        ok = need is None or (st["state"] == need and not (need == "approved" and st["failing"]))
        if need == "approved" and st["state"] == "approved" and st["failing"]:
            return emit("fail", f"anim design {name} ({result['id']}): approved, but it has a problem that was not on the page "
                                f"he approved - {st['failing'][0]}", next_words(name, st, result), **slim)
        return emit("pass" if ok else "fail", f"anim design {name} ({result['id']}): {st['state']} - {st['words']}",
                    next_words(name, st, result), **slim)
    made = None
    if cmd == "page":
        made = page(d, result, rec, flag(argv, "--out", os.path.join(os.environ.get("KIT_BUILD", "build"), "animations",
                                                                     f"{name}.design.png"))).replace(os.sep, "/")
    n = len(d["attacks"])
    where = f" -> {made}" if made else ""
    if st["failing"]:
        more = f" (+{len(st['failing']) - 1} more)" if len(st["failing"]) > 1 else ""
        return emit("fail", f"anim design {name} ({result['id']}): {len(st['failing'])} problem(s) in {n} attack(s) - "
                            f"{st['failing'][0]}{more}{where}", next_words(name, st, result), page=made, **slim)
    said = f"; {len(result['notes'])} note(s): {result['notes'][0]}" if result["notes"] else ""
    return emit("pass", f"anim design {name} ({result['id']}): {n} attack(s), no two of them cousins - {st['state']}: "
                        f"{st['words']}{said}{where}", next_words(name, st, result), page=made, **slim)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
