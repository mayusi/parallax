"""proc_dossier.py — MOVE DOSSIERS: the research behind one specific animation, REQUIRED before it is built (owner
2026-10-14: "get more data on said animation ur building ... more details so u understand to make it better").
A dossier (assets/animations/dossiers/<move>.json) holds what the move IS: sources (and what was taken from each), the
phases with their real and game timings, per-phase body mechanics, the cues that make it read, the classic mistakes,
how it translates to R6 (no knee / elbow), the build parameters, and numeric CHECKS measured on the finished clip.
    require(name)            -> the dossier, or an error naming what is missing (a builder calls this first)
    check(clip, dossier)     -> {check id: {value, range, pass, why}} + events (guard / toe_off / contact / land)
    python kit/anim/proc_dossier.py new <move> [--category combat] | check <move> | measure <move> <clip.json>
                                   | gate <source>=<move> ...      (kit anim dossier ... / kit anim compile run these)"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import proc_director as DR  # noqa: E402
import proc_r6 as P  # noqa: E402
import shape_ref as SR  # noqa: E402

DIR = os.path.join("assets", "animations", "dossiers")
J = P.JOINTS
REQUIRED = {"move": str, "sources": list, "phases": list, "reading_cues": list, "mistakes": list, "r6_translation": dict,
            "build": dict, "checks": list}
MIN = {"sources": 3, "phases": 3, "reading_cues": 3, "mistakes": 3, "checks": 5}


def require(name):
    """load a dossier and refuse an incomplete one: every section present, enough sources / phases / cues / mistakes /
    checks, every source says what was TAKEN from it, every check names its measure, range and why"""
    path = os.path.join(DIR, f"{name}.json")
    if not os.path.exists(path):
        raise SystemExit(f"no dossier for '{name}': research the move first -> {path} (see roundhouse_kick.json)")
    d = json.load(open(path, encoding="utf-8"))
    missing = [k for k, t in REQUIRED.items() if not isinstance(d.get(k), t) or not d.get(k)]
    missing += [f"{k} (>= {n}, has {len(d.get(k) or [])})" for k, n in MIN.items() if len(d.get(k) or []) < n]
    missing += [f"source {s.get('id', i)}: 'took'" for i, s in enumerate(d.get("sources") or []) if not s.get("took") or not s.get("url")]
    missing += [f"check {c.get('id', i)}: measure/range/why" for i, c in enumerate(d.get("checks") or [])
                if not (c.get("measure") in MEASURES and len(c.get("range") or []) == 2 and c.get("why"))]
    todo = sorted({k for k in REQUIRED if "TODO" in json.dumps(d.get(k), ensure_ascii=False)})
    missing += [f"{k}: still has TODO placeholders" for k in todo]
    missing += evidence_missing(d, name)
    import dossier_evidence as DE                           # (what each phase rests on: a schema-3 dossier says it)
    missing += DE.missing(d)
    missing += direction_missing(d)
    if missing:
        raise SystemExit(f"dossier '{name}' incomplete: {missing}")
    return d


LOCKS = os.path.join("board", "locks.json")


def locked(name):
    """True when dossier `name` was made after the quality locks (2026-10-21: board/locks.json lists the older ones as
    grandfathered) and the OWNER has not waived its evidence step (kit approve anim <move> ... --by owner --waive
    evidence). Mirrors kit/lib/locks.luau: only a record whose `by` starts with "owner" (and `who`, if any, is owner)
    counts."""
    try:
        L = json.load(open(LOCKS, encoding="utf-8"))
    except (OSError, ValueError):
        L = {}
    old = {str(f).lower() for f in ((L.get("grandfathered") or {}).get("anim") or [])}
    if f"{DIR}/{name}.json".replace(os.sep, "/").lower() in old:  # case-insensitive, as Windows file names are
        return False
    w = ((L.get("waivers") or {}).get("anim") or {}).get(name)
    owner = (isinstance(w, dict) and str(w.get("who", "owner")).lower() == "owner"
             and str(w.get("by", w.get("who", ""))).strip().lower().startswith("owner"))
    return not (owner and (not isinstance(w.get("steps"), list) or "evidence" in w["steps"]))


def direction_missing(d):
    """the owner's order (2026-10-24, vault shared/orders): an ORIGINAL piece decides its creative direction before it is
    built. A dossier that names a `direction` (every dossier scaffolded from now on) needs that doc at least READY -
    assets/animations/direction/<Piece>.md checked by kit/direction.py (intent, the one idea, >= 6 references,
    3 pillars, bans, >= 3 directions each with a real frame). Older dossiers name none and pass"""
    piece = d.get("direction")
    if not piece:
        return []
    if not isinstance(piece, str) or "TODO" in piece:
        return ["direction: decide it first - lune run kit anim direction <Piece> --new, then name it in the dossier"]
    doc = os.path.join("assets", "animations", "direction", f"{piece}.md")
    if not os.path.isfile(doc):
        return [f"direction: {doc} does not exist (lune run kit anim direction {piece} --new)"]
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import direction as DIR
    status, probs, _ = DIR.check(doc, "anim")
    return [] if status in ("ready", "picked") else [f"direction {piece}: still a draft - {probs[0] if probs else ''}"]


def evidence_missing(d, name=None):
    """THE LOOP (owner 2026-10-18: 'i need you to start enfcorcig this type of proper loop so you dont mess up as much'
    - three keyed guesses at the katana underhip were rejected before a dossier with REAL footage showed what all three
    lacked). A schema-2 dossier needs MEASURED evidence, not only text: at least one source with `measured` (what was
    measured, with numbers - footage landmarks, a loved clip, a paper's table) and real timings on every phase that
    moves (real_s: [lo, hi] seconds; the still start may be [0, 0]). Schema-1 dossiers (written before the rule) pass
    until the owner rejects their clip - then rejection_missing sends them through the loop. A dossier made after the
    quality locks (`name` given and not grandfathered) is schema 2 from the start."""
    if int(d.get("schema", 1)) < 2:
        if name and locked(name):
            # (the lock: schema 2 at least - measured evidence; `kit anim dossier new` writes schema 3, which also says
            # each phase's basis: kit/anim/dossier_evidence.py)
            return [f"schema: dossier '{name}' was made after the quality locks (2026-10-21) - a new dossier is schema 2 "
                    "or later with measured evidence (kit anim dossier footage <move> <clip>); `kit anim dossier new` "
                    "writes schema 3, every phase's basis said"]
        return []
    out = []
    meas = [s for s in d.get("sources") or [] if isinstance(s.get("measured"), str) and any(ch.isdigit() for ch in s["measured"])]
    if not meas:
        out.append("evidence: no source with `measured` numbers (measure footage: kit anim dossier footage <move> <clip>;"
                   " or a loved clip's statistics) - text alone is a guess")
    for ph in d.get("phases") or []:
        r = ph.get("real_s")
        moving = ph.get("game_s") and float(ph["game_s"][1]) - float(ph["game_s"][0]) > 0
        # (a schema-3 phase that SAYS it is inferred or told has no measured timing to give: kit/anim/dossier_evidence.py
        # holds it to what it says instead)
        said = ph.get("evidence") if isinstance(ph.get("evidence"), dict) else {}
        if int(d.get("schema", 1)) >= 3 and said.get("basis") in ("inferred", "told"):
            continue
        if moving and not (isinstance(r, list) and len(r) == 2 and all(isinstance(x, (int, float)) for x in r)):
            out.append(f"evidence: phase {ph.get('name')} has no measured real_s [lo, hi]")
    return out


VERDICTS = os.path.join("assets", "animations", "verdicts.json")
REJECT = ("bad", "horrible")


def rejection_missing(d, clip_names):
    """every owner REJECTION (verdicts.json: bad / horrible) on a clip this dossier builds must be answered IN the
    dossier before the clip is built again: an `owner_rejections` entry quoting it (its date + the first words of its
    note) with `changed` - what the dossier now says differently. A rejected move's dossier must also be schema 2
    (measured evidence). So a 'no' is never answered by re-keying blind"""
    try:
        allv = json.load(open(VERDICTS, encoding="utf-8")).get("verdicts") or {}
    except (OSError, ValueError):
        return []
    names = set(clip_names) | set(d.get("clips") or [])
    answered = d.get("owner_rejections") or []
    out = []
    for n in sorted(names):
        for v in allv.get(n) or []:
            if str(v.get("verdict", "")).lower() not in REJECT:
                continue
            words = str(v.get("note", ""))[:40]
            key = words[:25].lower().strip()
            # an answer QUOTES the rejection: same date, its first words (an empty note is answered only by an
            # empty quote - "" is inside every quote)
            hit = any(str(a.get("date")) == str(v.get("date")) and a.get("changed")
                      and ((key and key in str(a.get("quote", "")).lower()) or (not key and not str(a.get("quote", "")).strip()))
                      for a in answered)
            if not hit:
                at = f" at frame {v['frame']} ({v.get('t')} s)" if v.get("frame") is not None else ""
                out.append(f"owner rejected {n}{at} ({v.get('date')}: '{words}...') - add it to owner_rejections "
                           "{date, quote, changed} after re-researching the dossier")
    if out and int(d.get("schema", 1)) < 2:
        out.append("a rejected move's dossier must be schema 2 (measured evidence: kit anim dossier footage)")
    return out


def build_failing(d, move_file):
    """a strike move's GENERATED clip must pass every check of its dossier - a clip that misses its own research is
    not built (the checks were a report nobody had to read)"""
    try:
        m = json.load(open(move_file, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if m.get("kind") != "strike":
        return []
    import strike as S
    m.pop("step", None)          # steps are presentation (limited animation): the research checks the exact motion
    c, _ = S.generate(m)
    r = check(c, d)
    return [f"check {k}: {v['value']} outside {v['range']} ({v['why']})" for k, v in r["checks"].items() if not v["pass"]]


LEGACY = os.path.join(DIR, "_legacy.json")


def snake(name):
    """RoundhouseKick -> roundhouse_kick (a clip source's default dossier name)"""
    import re
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name).lower()


def legacy():
    """clip sources made BEFORE the dossier rule (owner 2026-10-14): grandfathered, never extended"""
    try:
        return set(json.load(open(LEGACY, encoding="utf-8"))["sources"])
    except (OSError, ValueError, KeyError):
        return set()


def phase_at(d, t, eps=1e-6):
    """the phase a KEY POSE at game time t belongs to. A key pose is the pose a phase ARRIVES at (the cocked blade is
    the end of the wind, the stretched arm the end of the cut), so a time on a border goes to the phase that ENDS
    there; t on a zero-length phase (the still start) is that phase. None: before / past every phase's game_s"""
    spans = [(p.get("name"), float(p["game_s"][0]), float(p["game_s"][1])) for p in d.get("phases") or []
             if isinstance(p, dict) and isinstance(p.get("game_s"), (list, tuple)) and len(p["game_s"]) == 2]
    t = float(t)
    for name, lo, hi in spans:
        if abs(hi - lo) <= eps and abs(t - lo) <= eps:
            return name
    for name, lo, hi in spans:
        if lo + eps < t <= hi + eps:
            return name
    for name, lo, hi in spans:                     # the very start of a phase, with no still phase before it
        if abs(t - lo) <= eps:
            return name
    return None


HIT_WORDS = ("contact", "impact", "cut", "strike", "slash", "thrust", "hit", "kick", "punch", "extension", "swing",
             "blow", "stab", "chop", "fire")


def hit_phase(d):
    """the phase a strike's HIT ends: a zero-length phase after the start (a dossier's own 'contact'), else the last
    phase named for the blow (cut / strike / swing ...). None: the dossier names none (an idle, a walk)"""
    phases = [p for p in d.get("phases") or [] if isinstance(p, dict) and isinstance(p.get("name"), str)]
    for p in phases:
        gs = p.get("game_s")
        if isinstance(gs, (list, tuple)) and len(gs) == 2 and float(gs[0]) > 1e-6 and abs(float(gs[1]) - float(gs[0])) <= 1e-6:
            return p["name"]
    named = [p["name"] for p in phases if any(w in p["name"].lower() for w in HIT_WORDS)]
    return named[-1] if named else None


def phases_for(d, times, hit_t=None):
    """the phase of every key pose of ONE clip (its key moments `times`, ascending; its Hit at `hit_t`).
    BY TIME (phase_at) while the clip is timed like its dossier - its Hit falls in the dossier's hit phase, or one of
    the two is unknown. A clip that is NOT (a procedural candidate: the katana kesa's game_s puts the cut at 0.15-0.31
    s, its calm candidate hits at 0.53 s, so every pose after the wind read 'zanshin') gets its phases BY ORDER round
    the Hit: the pose at the Hit is the hit phase, the poses before it the phases before it counted back from the
    Hit, the poses after it the phases after it. -> ([phase or None per time], "time" | "order", why "order" or None)"""
    by_time = [phase_at(d, t) for t in times]
    hp = hit_phase(d)
    if hit_t is None or hp is None or not times:
        return by_time, "time", None
    at_hit = phase_at(d, hit_t)
    if at_hit == hp:
        return by_time, "time", None
    names = [p.get("name") for p in d.get("phases") or [] if isinstance(p, dict)]
    h = names.index(hp)
    k_hit = min(range(len(times)), key=lambda i: abs(float(times[i]) - float(hit_t)))
    out = [None] * len(times)
    out[k_hit] = hp
    for j, i in enumerate(range(k_hit - 1, -1, -1)):          # back from the Hit: the wind before it, then the guard
        out[i] = names[max(0, h - 1 - j)] if h > 0 else hp
    if k_hit > 0 and float(times[0]) <= 1e-6:
        out[0] = names[0]
    for j, i in enumerate(range(k_hit + 1, len(times))):       # on from the Hit: the hold, the recovery
        out[i] = names[min(len(names) - 1, h + 1 + j)]
    why = (f"the clip is not timed like its dossier (its Hit at {float(hit_t):.2f} s falls in the dossier's "
           f"'{at_hit}', not its '{hp}'): the poses' phases are counted in order round the Hit")
    return out, "order", why


REFERENCE_VIEWS = ("player", "side", "top", "front")     # the view of OURS a reference frame was filmed like


def reference_frames(d, root="."):
    """the dossier's REFERENCE FRAMES (`reference_frames`): the real move's own pictures, by phase - what a key pose is
    LOOKED AT beside (kit anim sheet, kit anim compare). Each entry: {phase, video + t (seconds into that clip) |
    image (a still picture), game_t (the moment of OUR clip it answers), note, source (a sources[] id), view (which of
    our views it was filmed like: player / side / top / front), crop ([x0, y0, x1, y1] in fractions of the frame: the
    performer, not the room), flip (mirror it: a left-handed take)}. Footage stays private (the git-ignored
    _artifacts/footage/<move>/), so a frame whose file is not on this machine is kept and SAYS so.
    -> [{..., path, missing: why it cannot be shown or None}]"""
    names = {p.get("name") for p in d.get("phases") or [] if isinstance(p, dict)}
    out = []
    for r in d.get("reference_frames") or []:
        if not isinstance(r, dict):
            continue
        e = dict(r)
        src = r.get("video") or r.get("image")
        e["path"] = os.path.join(root, src) if isinstance(src, str) and not os.path.isabs(src) else src
        why = None
        if not isinstance(src, str) or not src:
            why = "names no video and no image"
        elif r.get("video") and not isinstance(r.get("t"), (int, float)):
            why = "a video frame needs t (seconds into the clip)"
        elif not os.path.isfile(e["path"]):
            why = f"its file is not on this machine ({src})"
        elif r.get("phase") not in names:
            why = f"the dossier has no phase named {r.get('phase')!r}"
        elif r.get("view") is not None and r.get("view") not in REFERENCE_VIEWS:
            why = f"view is one of {' / '.join(REFERENCE_VIEWS)}, not {r.get('view')!r}"
        e["missing"] = why
        out.append(e)
    return out


def reference_for(d, t, root=".", refs=None, phase=False):
    """the reference frame a key pose at game time t is looked at beside: its PHASE's frame, the one whose game_t is
    nearest when the phase has several. `phase`: the pose's phase when the caller knows it (phases_for; a clip not
    timed like its dossier: the frame nearest the END of the phase, the pose it arrives at); left out: phase_at(d, t).
    -> (phase or None, the entry or None, why there is none or None)"""
    given = phase is not False
    phase = phase if given else phase_at(d, t)
    refs = reference_frames(d, root) if refs is None else refs
    if phase is None:
        return None, None, f"no phase of the dossier covers {float(t):.2f} s (its game_s)"
    mine = [r for r in refs if r.get("phase") == phase]
    if not mine:
        return phase, None, (f"the dossier names no reference frame for its phase '{phase}'" if refs
                             else "the dossier names no reference frames at all")
    at = float(t)
    if given:
        span = next((p.get("game_s") for p in d.get("phases") or [] if isinstance(p, dict) and p.get("name") == phase), None)
        if isinstance(span, (list, tuple)) and len(span) == 2 and phase_at(d, t) != phase:
            at = float(span[1])
    best = min(mine, key=lambda r: abs(float(r.get("game_t", at)) - at))
    return phase, best, best.get("missing")


def scaffold(name, category="combat", move=None):
    """a new dossier with every required section as a TODO and the RESEARCH LIST that fills it"""
    return {
        "schema": 3, "name": name, "move": move or f"TODO: what exactly is '{name}' (the variant, the side, the stance)",
        "direction": f"TODO: the piece's CREATIVE DIRECTION first (the owner, 2026-10-24) - lune run kit anim direction <Piece> --new, then put <Piece> here",
        "category": category,
        "research_list": [
            "biomechanics: a paper with phase timings + joint speeds of the real move (scholar / PubMed / PLOS)",
            "technique: two coaching sources - the cues a coach says, the classic mistakes",
            "real footage: describe 2+ clips frame by frame (phase starts in seconds; contacts; where the weight is)",
            "reference frames: KEEP the frames you looked at - `reference_frames`: [{phase, video + t | image, game_t, "
            "note, view, crop}] of the footage in _artifacts/footage/<move>/ (kit anim sheet shows each key pose beside "
            "its phase's frame, and says every gap)",
            "animation craft: how game animators stage it (anticipation, snap, hold, follow-through, silhouette)",
            "loved R6 data: kit/anim/strike_style.py / proc_calib numbers for this category (statistics only, no poses)",
            "R6 translation: no knee / elbow - what the torso, slides and the head do instead",
        ],
        "sources": [{"id": "TODO", "cite": "TODO", "url": "TODO", "took": "TODO: the numbers / cues taken from it",
                     "measured": "TODO: what YOU measured from it, with numbers (footage: kit anim dossier footage)"}],
        "phases": [{"name": "TODO", "real_s": "TODO: [lo, hi] seconds MEASURED on the footage", "game_s": [0.0, 0.0],
                    "body": "TODO: what every part does",
                    "evidence": {"basis": "TODO: measured | inferred | told - what THIS phase rests on (kit/anim/"
                                          "dossier_evidence.py)",
                                 "from": "TODO: the source id / real_s_from it was measured on; what it was inferred "
                                         "from; \"owner\" (and \"note\": the owner's words) when told"}}],
        "owner_rejections": [],
        "reading_cues": ["TODO: what makes it read as THIS move at a glance"],
        "mistakes": ["TODO: the classic mistakes (coaches + animators)"],
        "r6_translation": {"no_knee": "TODO", "no_elbow": "TODO"},
        "build": {"keys": [], "key_help": "TODO: the build parameters (see roundhouse_kick.json)"},
        "checks": [{"id": "TODO", "measure": "TODO", "range": [0, 0], "why": "TODO: which source says so"}],
    }


def gate_coverage(pairs, missing, load=None):
    """{source: catalog_coverage.line(its dossier's words)} for every '<source>=<dossier>=...' pair the gate passed;
    {} on a machine without the catalogue (load: the catalogue's loader, for a test)"""
    import catalog_coverage as CC
    try:
        table_ = CC.table((load or CC.load)())
    except Exception:                                        # noqa: BLE001 - no catalogue here: nothing is said
        return {}
    out = {}
    for pair in pairs:
        src, dos = (pair.split("=") + [""])[:2]
        if src and src not in missing:
            out[src] = CC.line((dos or src).replace("_", " "), table_)
    return out


def verdict(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))


# ---------------------------------------------------------------- measuring a clip
def _world(c):
    q, p = DR.arrays(c)
    return q, p


def _yaw(qv):
    f = P.q_rot(qv, np.array([0.0, 0.0, -1.0]))
    return math.degrees(math.atan2(-f[0], -f[2]))


def _unwrap(a):
    return np.degrees(np.unwrap(np.radians(np.asarray(a))))


def _limb_end_world(q, p, t, limb):
    c0, v = DR.geom()[limb]
    k = J.index(limb)
    return p[t, 0] + P.q_rot(q[t, 0], c0 + p[t, k] + P.q_rot(q[t, k], v))


def _events(c, d, q, p):
    b = d["build"]
    K, S = b["kick_leg"], b["support_leg"]
    k = J.index(K)
    n = len(q)
    sole = np.array([P.sole_char(q[t, 0], p[t, 0], q[t, k], p[t, k], K) for t in range(n)])
    hit = next((e["t"] for e in c.get("events", []) if e.get("name") == "Hit"), None)
    fh = int(round(hit * 60)) if hit is not None else int(np.argmax(np.r_[0, np.linalg.norm(np.diff(sole, axis=0), axis=1)]))
    off = next((t for t in range(n) if sole[t, 1] > P.FLOOR + 0.1), fh)
    land = next((t for t in range(fh, n) if sole[t, 1] <= P.FLOOR + 0.06), n - 1)
    return {"guard": 0, "toe_off": off, "contact": min(fh, n - 1), "land": land}, sole


REACT_MEASURES = ("head_peak_deg", "head_to_peak_s", "head_speed_deg_s", "torso_peak_deg", "torso_shove_studs",
                  "torso_lag_s", "head_nod_up_share")


def react_measures(c, d):
    """a HIT REACTION's numbers (react_measure.py: the head relative to the torso, the torso's turn / shove from the
    snap's onset) - the same numbers the loved R6 reactions are measured with"""
    import react_measure as RM
    m = RM.measure(c)
    fns = {k: (lambda ck, k=k: float("nan") if m.get(k) is None else float(m[k])) for k in REACT_MEASURES}
    hit = next((e["t"] for e in c.get("events", []) if e.get("name") == "Hit"), 0.0)
    return fns, {"hit": int(round(hit * 60))}


SWORD_MEASURES = ("torso_yaw_range_deg", "arm_slide_max_studs", "main_arm_hold_s", "arm_peak_dps", "leg_twist_max_deg",
                  "blade_path_off_deg", "clip_seconds", "hands_side_max_studs", "bottom_pause_s", "finish_hands_over_shoulders_studs", "edge_up_at_start", "edge_up_at_hit",
                  "stamp_lead_s", "body_drive_studs", "guard_hands_min_height_studs", "arm_sink_max", "hit_time_s")


def sword_measures(c, d):
    """a SWORD swing's numbers (strike.py clips, `sword.tip` carried): the torso's turn across the swing, how far the
    one-piece arms SLIDE, how long the main arm HOLDS its extreme, its peak speed, how much the legs twist against the
    torso, the blade tip's path direction at the Hit vs a wanted one (check 'dir', character space) - the measures the
    owner's loved R6 slashes were read with (2026-10-17)"""
    import clip as C
    import proc_calib as PCAL
    import r6_vocab as RV
    import strike_style as SS
    q = PCAL.rot_arrays(c)
    w = PCAL.ang_speed(q)
    fps = float(c.get("fps", 60))
    qq, _ = DR.arrays(c)
    f = np.array([P.q_rot(x, np.array([0.0, 0.0, -1.0])) for x in qq[:, 0]])
    yaw = np.degrees(np.unwrap(np.arctan2(-f[:, 0], -f[:, 2])))
    rv = RV.measures(c)
    st = [x for x in SS.strikes(q) if J[x["joint"]] in ("Right Arm", "Left Arm")]
    main = max(st, key=lambda x: x.get("amp_deg", 0)) if st else {}
    hit = next((e["t"] for e in c.get("events", []) if e.get("name") == "Hit"), None)
    tips = np.asarray((c.get("sword") or {}).get("tip") or [], float)

    def blade_off(ck):
        if hit is None or len(tips) < 3:
            return float("nan")
        i = min(len(tips) - 2, max(1, int(round(hit * fps)) - 1))
        v = tips[i + 1] - tips[i - 1]
        wnt = np.asarray(ck.get("dir") or [0, 0, -1], float)
        cos = float(v @ wnt / max(1e-9, np.linalg.norm(v) * np.linalg.norm(wnt)))
        return math.degrees(math.acos(max(-1.0, min(1.0, cos))))

    vals = {"torso_yaw_range_deg": float(yaw.max() - yaw.min()),
            "arm_slide_max_studs": float(max(rv["Right Arm"]["slide_p95"], rv["Left Arm"]["slide_p95"])),
            "main_arm_hold_s": float(main.get("hold_frames", 0)) / fps if main else float("nan"),
            "arm_peak_dps": float(max(w[:, J.index("Right Arm")].max(), w[:, J.index("Left Arm")].max())),
            "leg_twist_max_deg": float(max(rv["kick_leg"]["rot_range"], rv["support_leg"]["rot_range"])),
            "clip_seconds": len(q) / fps}
    # the HANDS in the torso frame (the katana underhip dossier, 2026-10-18, measured on real down-cut / up-cut
    # footage): how far they leave the front of the body before the Hit, how long they PAUSE at the bottom, how high
    # they finish over the shoulders; and the EDGE (strike.py sword.edge): facing down at the start, up at the Hit
    sw = c.get("sword") or {}
    grips = np.asarray(sw.get("grip_path") or [], float)
    tor = ((c.get("joints") or {}).get("Torso") or {}).get("frames") or []
    hit_i = int(round((hit or 0) * fps))
    if len(grips) and len(tor) == len(grips):
        loc = np.array([C.quat_mat(f[:4]).T @ (g - np.asarray(f[4:7], float)) for f, g in zip(tor, grips)])
        pre = loc[:max(1, hit_i)]
        lo = float(pre[:, 1].min())
        low = np.where(pre[:, 1] < lo + 0.15)[0]
        vals["hands_side_max_studs"] = float(np.abs(pre[:, 0]).max())
        vals["bottom_pause_s"] = float((low.max() - low.min() + 1) / fps) if len(low) else 0.0
        vals["finish_hands_over_shoulders_studs"] = float(loc[-1, 1] - 0.5)
    edges = np.asarray(sw.get("edge") or [], float)
    if len(edges):
        vals["edge_up_at_start"] = float(edges[0, 1])
        vals["edge_up_at_hit"] = float(edges[min(len(edges) - 1, hit_i), 1])
    # a PARRY-RIPOSTE (the KatanaKaeshi direction, 2026-10-24): at the "Parry" marker how UPRIGHT the blade stands
    # (it must read in one frame from the game camera), how long the hands HOLD there (the beat the player feels; the
    # loved BlockingHitReaction1 absorbs a hit in 0.133 s), and the RIPOSTE: blade start -> Hit (scoring kendo cuts
    # land 0.09-0.15 s after the blade starts, Ogle & O'Donoghue 2015)
    parry = next((e["t"] for e in c.get("events", []) if e.get("name") == "Parry"), None)
    if parry is not None and len(tips) and len(grips) and hit is not None:
        pi = min(len(tips) - 1, int(round(parry * fps)))
        bd = tips[pi] - grips[pi]
        vals["parry_blade_up_deg"] = math.degrees(math.acos(max(-1.0, min(1.0, float(bd[1] / max(1e-9, np.linalg.norm(bd)))))))
        spd = np.r_[0, np.linalg.norm(np.diff(tips, axis=0), axis=1)] * fps
        # the hold starts once the blade has ARRIVED (the marker may sit on its last approach frames: review 2026-10-24)
        hs = pi
        dpk = float(spd[:pi + 1].max()) if pi > 0 else 0.0
        stop = min(len(spd) - 1, int(round((hit or 0) * fps)) - 1)  # (never past the Hit: a deflect flowing into the cut)
        while hs < stop and spd[hs] > 0.25 * dpk:
            hs += 1
        moved = np.where(np.linalg.norm(grips[hs:] - grips[hs], axis=1) > 0.25)[0]
        hold = int(moved[0]) if len(moved) else len(grips) - hs
        vals["parry_hold_s"] = float(hold / fps)
        hi_ = min(len(tips) - 1, hit_i)
        if hi_ > hs + 1:
            pk = hs + int(np.argmax(spd[hs:hi_ + 1]))
            # the riposte's FIRST movement (as the kendo timing is read): the tip leaves the hold's own drift - a fixed
            # share of the peak read the onset 1-2 frames late (0.083 s where it began ~0.10 s before the Hit)
            base = float(np.median(spd[hs:hs + max(2, hold)]))
            st = pk
            while st > hs and spd[st - 1] > max(2.0 * base, 0.05 * spd[pk]):
                st -= 1
            vals["riposte_s"] = float((hi_ - st) / fps)
    # an UNARMED BODY BLOW (strike.py `unarmed`, the IronMountain direction, 2026-10-25): when the Hit lands, where the
    # STEPPING foot landed (the stamp leads the blow: karate coaching puts contact at the front foot's landing), how far
    # the whole body travelled forward (root motion included), how high the hands stay in the torso frame (the guard:
    # chin height ~0.8) and the arms' worst sink into the body over the clip (the loved R6 combo: p90 0.12, max 0.16-0.20)
    if not sw:
        import strike as SK
        n = len(q)
        hi_ = min(n - 1, hit_i)
        root = np.asarray(c.get("root") or [[0, 0, 0, 1, 0, 0, 0]] * n, float)

        def world(t, v):
            return root[t, 4:7] + P.q_rot(root[t, :4], v)
        pp = DR.arrays(c)[1]
        soles = {leg: np.array([world(t, P.sole_char(qq[t, 0], pp[t, 0], qq[t, J.index(leg)], pp[t, J.index(leg)], leg))
                                for t in range(n)]) for leg in ("Right Leg", "Left Leg")}
        step = max(soles, key=lambda lg: float(np.linalg.norm(soles[lg][hi_, [0, 2]] - soles[lg][0, [0, 2]])))
        s = soles[step]
        up = int(np.argmax(s[:hi_ + 1, 1])) if hi_ > 0 else 0
        land = next((t for t in range(up, n) if s[t, 1] <= s[0, 1] + 0.06), n - 1)
        # (a foot that never LEAVES the floor is a skate, not a stamp: no landing to lead the blow)
        vals["stamp_lead_s"] = float((hi_ - land) / fps) if s[up, 1] > s[0, 1] + 0.1 else float("nan")
        vals["body_drive_studs"] = float(-(world(hi_, pp[hi_, 0])[2] - world(0, pp[0, 0])[2]))
        pose = {j: list(qq[hi_, k]) + list(pp[hi_, k]) for k, j in enumerate(J)}
        vals["guard_hands_min_height_studs"] = float(min(DR.end(pose, a)[1] for a in ("Right Arm", "Left Arm")))
        rep = SK.arm_sink_report(c, C.load_rig("r6"), 0.0)
        vals["arm_sink_max"] = float(rep["worst"]) if rep else 0.0
        vals["hit_time_s"] = float(hi_ / fps)
    fns = {k: (lambda ck, k=k: vals.get(k, float("nan"))) for k in vals}
    fns["blade_path_off_deg"] = blade_off
    fns.update(body_pose_fns(c))
    return fns, {"hit": int(round((hit or 0) * fps))}


def body_pose_fns(c):
    """the BODY's pose in the root's frame (Sample Game movement set, 2026-10-27: an air pose, a slide, a dash and a wall
    run are POSES held at speed, measured on footage as hip / knee angles): per frame, each leg's pitch (the hip ->
    foot line off straight down; + = the foot forward), splay (the leg's sideways angle off its own length, + = out), slide (how far the rigid leg's top sits into
    the torso: R6's bent knee), the torso's lean (+ = forward) and roll (+ = the right shoulder down), the torso's drop
    (studs under rest) and the lowest point of any part over the floor (rest root = 3 over it). A check picks a
    statistic: {"leg": "R"|"L", "stat": "mean"|"min"|"max"|"range"|"at", "t": s (with "at"; "end" = the last frame)}"""
    import clip as C
    rig = C.load_rig("R6")
    W = C.world_frames(c, rig)
    n = len(W)
    rows = {k: np.zeros(n) for k in ("pitchR", "pitchL", "splayR", "splayL", "slideR", "slideL", "lean", "roll",
                                     "drop", "lowest")}
    for i, fr in enumerate(W):
        T = fr["Torso"]
        up = T[:3, :3] @ np.array([0.0, 1.0, 0.0])
        rows["lean"][i] = math.degrees(math.atan2(-up[2], up[1]))
        rows["roll"][i] = math.degrees(math.atan2(up[0], up[1]))
        rows["drop"][i] = -float(T[1, 3])
        rows["lowest"][i] = min(C.lowest(rig, p, fr[p]) for p in fr if p in rig["sizes"] and p != rig["root"]) + 3.0
        for side, part, hx in (("R", "Right Leg", 0.5), ("L", "Left Leg", -0.5)):
            m = fr[part]
            top = (m @ np.array([0.0, 1.0, 0.0, 1.0]))[:3]
            foot = (m @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]
            hip = (T @ np.array([hx, -1.0, 0.0, 1.0]))[:3]
            d = foot - top
            rows["pitch" + side][i] = math.degrees(math.atan2(-d[2], -d[1]))
            rows["splay" + side][i] = math.degrees(math.asin(max(-1.0, min(1.0, d[0] * (1 if side == "R" else -1)
                                                                    / max(1e-9, float(np.linalg.norm(d)))))))
            rows["slide" + side][i] = float((top - hip) @ (T[:3, :3] @ np.array([0.0, 1.0, 0.0])))
    fps = float(c.get("fps", 60))

    def stat(key):
        def f(ck):
            v = rows[key + str(ck.get("leg", ""))] if key in ("pitch", "splay", "slide") else rows[key]
            s = ck.get("stat", "mean")
            if s == "at":
                t = ck.get("t", 0)
                i = n - 1 if t == "end" else min(n - 1, max(0, int(round(float(t) * fps))))
                return float(v[i])
            return float({"mean": v.mean(), "min": v.min(), "max": v.max(), "range": v.max() - v.min()}[s])
        return f
    return {"leg_pitch_deg": stat("pitch"), "leg_splay_deg": stat("splay"), "leg_slide_studs": stat("slide"),
            "torso_lean_deg": stat("lean"), "torso_roll_deg": stat("roll"), "torso_drop_studs": stat("drop"),
            "lowest_part_studs": stat("lowest")}


FP_EYE = np.array([0.0, 1.5, 0.0])          # the first-person camera: the head's centre (root + 1.5), looking -z
FP_TAN_Y = math.tan(math.radians(35.0))       # Roblox's FieldOfView 70 is VERTICAL
FP_TAN_X = FP_TAN_Y * 16.0 / 9.0


def fp_screen(p):
    """a character-space point -> (sx, sy) in [-1, 1] on a 16:9 first-person screen, None when behind the eye"""
    v = np.asarray(p, float) - FP_EYE
    depth = -v[2]
    if depth < 0.1:
        return None
    return v[0] / depth / FP_TAN_X, v[1] / depth / FP_TAN_Y


def _ray_hits_box(M, size, origin, direction):
    """does the ray hit the oriented box (4x4 M, full size)? (the slab test in the box's own frame)"""
    R, t = M[:3, :3], M[:3, 3]
    o, dv = R.T @ (origin - t), R.T @ direction
    h = np.asarray(size, float) / 2
    lo, hi = -1e9, 1e9
    for k in range(3):
        if abs(dv[k]) < 1e-12:
            if abs(o[k]) > h[k]:
                return False
            continue
        a, b = (-h[k] - o[k]) / dv[k], (h[k] - o[k]) / dv[k]
        lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
    return hi >= max(lo, 0.0)


def fp_measures(c, d):
    """a FIRST-PERSON weapon clip's numbers (Sample Game's R6 arms, 2026-10-25: the camera sits in the head and shows
    only the arms + the weapon): the share of frames the weapon's grip AND muzzle/tip are on screen (inside 92% of the
    half-extents), the share of frames an ARM covers the crosshair (the screen's centre: the player must see what they
    shoot), how far the barrel rises over the clip (recoil) and when it peaks, how low the weapon sits on screen at its
    lowest, and the clip's length"""
    import clip as C
    sw = c.get("sword") or {}
    tips, grips = np.asarray(sw.get("tip") or [], float), np.asarray(sw.get("grip_path") or [], float)
    fps = float(c.get("fps", 60))
    times = c.get("times") or []
    n = len(times)
    # the clip's real length (n frames span (n - 1) / fps): the duration the engine plays
    vals = {"clip_seconds": float(c.get("duration", times[-1] if n else float("nan")))}
    if len(tips) and len(tips) == len(grips):
        seen, low = 0, float("nan")
        for tp, gp in zip(tips, grips):
            pts = [fp_screen(tp), fp_screen(gp)]
            if all(s is not None and abs(s[0]) <= 0.92 and abs(s[1]) <= 0.92 for s in pts):
                seen += 1
            ys = [s[1] for s in pts if s is not None]
            if ys:
                low = min(ys) if math.isnan(low) else min(low, *ys)
        vals["fp_weapon_in_view_share"] = seen / len(tips)
        vals["fp_weapon_low_y"] = low
        # the ROLL: how far the weapon's edge (a pistol's grip-down side) turns away from where it starts, at most
        # (a reload's 'magwell toward the support side' is a roll; the barrel's pitch alone does not show it)
        edges = np.asarray(sw.get("edge") or [], float)
        if len(edges) == len(tips):
            e0 = edges[0] / max(np.linalg.norm(edges[0]), 1e-9)
            cos = np.clip(edges @ e0 / np.maximum(np.linalg.norm(edges, axis=1), 1e-9), -1, 1)
            vals["grip_roll_max_deg"] = float(np.degrees(np.arccos(cos)).max())
        dirs = tips - grips
        pitch = np.degrees(np.arcsin(np.clip(dirs[:, 1] / np.maximum(np.linalg.norm(dirs, axis=1), 1e-9), -1, 1)))
        vals["muzzle_rise_deg"] = float(pitch.max() - pitch[0])
        vals["muzzle_peak_s"] = float(int(np.argmax(pitch)) / fps)
    # THE SHOOTING GUN (Sample Game's two guns, 2026-10-26 - the owner: Onyx was never done "as proper as the silver"):
    # the clip's "Shot" event names its gun ("value": "L" = Onyx, the left hand's Handle track; else Pearl). Measured
    # on THAT gun: how far off the line of fire (character -Z) it points on the shot frame, how far its muzzle rises
    # after it (the kick) and when, and the most it turns away from its shot direction (a twirl turns ~180)
    shot = next((e for e in c.get("events", []) if e.get("name") == "Shot"), None)
    if shot is not None and n:
        import grip as G
        barrels = None
        if str(shot.get("value", "")).upper() == "L":
            if c.get("grip_left"):
                barrels = np.asarray(G.left_barrels(c), float)
        elif len(tips) and len(tips) == len(grips):
            barrels = tips - grips
        if barrels is not None and len(barrels):
            barrels = barrels / np.maximum(np.linalg.norm(barrels, axis=1, keepdims=True), 1e-9)
            i0 = min(len(barrels) - 1, max(0, int(round(float(shot.get("t", 0.0)) * fps))))
            b0 = barrels[i0]
            vals["shot_aim_err_deg"] = float(np.degrees(np.arccos(np.clip(np.dot(b0, [0.0, 0.0, -1.0]), -1, 1))))
            pitch = np.degrees(np.arcsin(np.clip(barrels[i0:, 1], -1, 1)))
            vals["shot_gun_rise_deg"] = float(pitch.max() - pitch[0])
            vals["shot_gun_peak_s"] = float(int(np.argmax(pitch)) / fps)
            vals["shot_gun_turn_max_deg"] = float(np.degrees(np.arccos(np.clip(barrels[i0:] @ b0, -1, 1))).max())
    # THE JUGGLES (Sample Game style v4, owner 2026-10-27: "he starts throwing them around, while shooting them"): a
    # clip with several "Shot" events (each names its gun) and "Toss" / "Catch" events (a gun leaves the hand / is
    # back; the game can't fire it between them). Measured: the WORST aim over every shot, how many shots go off while
    # the other gun is in the air, a shot from a gun that is itself in the air (the game refuses it: must be 0), and
    # each toss's flight time
    evs = sorted(c.get("events", []), key=lambda e: float(e.get("t", 0.0)))
    shots = [e for e in evs if e.get("name") == "Shot"]
    # a MELEE contact inside a weapon clip (Sample Game's Greatsword, 2026-10-27): the Hit marker's time (the game's
    # contact is 0.10 s after the click) and the blade tip's speed on that frame against its fastest (a cut that peaks
    # before or after its contact reads wrong - the kit's motion gate "Hit vs the fastest frame")
    # the blade tip's lowest point over the floor (tips are root-relative; the rest root stands 3 over the floor): a
    # longer blade swung through "straight down" cuts into the ground (Greatsword at 4.0 studs, 2026-10-27)
    if len(tips):
        vals["tip_floor_min_studs"] = float(tips[:, 1].min() + 3.0)
    hit = next((e for e in evs if e.get("name") == "Hit"), None)
    if hit is not None:
        vals["hit_time_s"] = float(hit.get("t", 0.0))
        if len(tips) > 2:
            sp = np.linalg.norm(np.diff(tips, axis=0), axis=1)
            ih = min(len(sp) - 1, max(0, int(round(float(hit.get("t", 0.0)) * fps)) - 1))   # the frame arriving at the Hit
            vals["hit_tip_speed_share"] = float(sp[ih] / max(sp.max(), 1e-9))
    # the tosses (a draw tosses with no shot at all): each gun's Toss -> its Catch
    flights, air = [], {}
    for e in evs:
        side = "L" if str(e.get("value", "")).upper() == "L" else "R"
        if e.get("name") == "Toss":
            air[side] = float(e.get("t", 0.0))
        elif e.get("name") == "Catch" and side in air:
            flights.append((side, air.pop(side), float(e.get("t", 0.0))))
    flights += [(s, t0, float("inf")) for s, t0 in air.items()]          # never caught: in the air to the end
    if flights:
        vals["toss_flight_min_s"] = min(b - a for _, a, b in flights)
        vals["toss_flight_max_s"] = max(b - a for _, a, b in flights)
    if shots and n:
        import grip as G
        bars = {}
        if c.get("grip_left"):
            bars["L"] = np.asarray(G.left_barrels(c), float)
        if len(tips) and len(tips) == len(grips):
            bars["R"] = tips - grips
        errs = []
        for e in shots:
            b = bars.get("L" if str(e.get("value", "")).upper() == "L" else "R")
            if b is None or not len(b):
                continue
            i0 = min(len(b) - 1, max(0, int(round(float(e.get("t", 0.0)) * fps))))
            v = b[i0] / max(np.linalg.norm(b[i0]), 1e-9)
            errs.append(float(np.degrees(np.arccos(np.clip(np.dot(v, [0.0, 0.0, -1.0]), -1, 1)))))
        vals["shot_count"] = float(len(shots))
        if errs:
            vals["shots_aim_err_max_deg"] = max(errs)

        def up(side, t):
            return any(s == side and a < t < b for s, a, b in flights)
        vals["shots_while_other_up"] = float(sum(
            1 for e in shots if up("R" if str(e.get("value", "")).upper() == "L" else "L", float(e.get("t", 0.0)))))
        vals["shots_from_a_gun_in_the_air"] = float(sum(
            1 for e in shots if up("L" if str(e.get("value", "")).upper() == "L" else "R", float(e.get("t", 0.0)))))
    if n:
        rig = C.load_rig("r6")
        blocked = 0
        for i in range(n):
            W = C.fk(rig, C.character_transforms(c, rig, i))
            if any(_ray_hits_box(W[a], (1.0, 2.0, 1.0), FP_EYE, np.array([0.0, 0.0, -1.0])) for a in ("Right Arm", "Left Arm") if a in W):
                blocked += 1
        vals["fp_center_blocked_share"] = blocked / n
        # THIRD PERSON (Sample Game over the right shoulder since 2026-10-26): the crosshair's ray starts at the game's
        # camera - the dossier's build "tp_camera": [right, up, back] studs from the eye, its view parallel to the eye's -
        # and the arms must not cover it (the first-person ray from the head is not what the player sees any more)
        tp = (d.get("build") or {}).get("tp_camera")
        if isinstance(tp, list) and len(tp) == 3:
            cam = FP_EYE + np.array([float(tp[0]), float(tp[1]), float(tp[2])])
            hit = 0
            for i in range(n):
                W = C.fk(rig, C.character_transforms(c, rig, i))
                if any(_ray_hits_box(W[a], (1.0, 2.0, 1.0), cam, np.array([0.0, 0.0, -1.0])) for a in ("Right Arm", "Left Arm") if a in W):
                    hit += 1
            vals["tp_center_blocked_share"] = hit / n
    fns = {k: (lambda ck, k=k: vals.get(k, float("nan"))) for k in vals}
    return fns, {"hit": int(round(float(next((e["t"] for e in c.get("events", []) if e.get("name") == "Hit"), 0.0)) * fps))}


CUT_MEASURES = ("cut_fast_frames", "cut_fast_share", "cut_front_share", "cut_arm_drive", "stance_split_hit_studs",
                "step_near_hit_s", "leg_angle_max_deg", "cut_visible_share", "blade_visible_share", "blade_visible_at_burst",
                "blade_unseen_max_s")


def _segment_hits_box(M, size, a, b):
    """is the segment a -> b blocked by the oriented box (4x4 M, full size) before it reaches b?"""
    R, t = M[:3, :3], M[:3, 3]
    o, dv = R.T @ (a - t), R.T @ (b - a)
    h = np.asarray(size, float) / 2
    lo, hi = 0.0, 0.98
    for k in range(3):
        if abs(dv[k]) < 1e-12:
            if abs(o[k]) > h[k]:
                return False
            continue
        t0, t1 = sorted(((-h[k] - o[k]) / dv[k], (h[k] - o[k]) / dv[k]))
        lo, hi = max(lo, t0), min(hi, t1)
        if lo > hi:
            return False
    return True


EDGE_ON_DEG = 20.0      # a blade within this of the camera's line of sight shows < 1/3 of its length: a dot, not a blade


def blade_seen(Wf, rig, cam, g, t, us=np.linspace(0.5, 1.0, 6)):
    """[seen?] for points `us` along the blade grip g -> tip t from the camera position cam: not hidden behind a body
    part AND the blade not END-ON to the camera (the governor 2026-11-04: SwordTrickCut's shoulder rest pointed the
    blade straight back at the over-the-shoulder camera, 4-6 deg off its line of sight - nothing covered it, so it
    counted as 100 % seen, while the GIF showed no blade at all)"""
    g, t = np.asarray(g, float), np.asarray(t, float)
    m = g + 0.75 * (t - g)
    b, ray = t - g, m - np.asarray(cam, float)
    s = np.linalg.norm(np.cross(b, ray)) / max(np.linalg.norm(b) * np.linalg.norm(ray), 1e-9)
    if s < np.sin(np.radians(EDGE_ON_DEG)):
        return [False] * len(us)
    return [not any(_segment_hits_box(Wf[p], rig["sizes"][p], cam, g + u * (t - g)) for p in
                    ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg") if p in Wf) for u in us]


def _blade_view(c, i, g, t, tp_camera):
    """(camera, grip, tip) in the world of frame i: the sword is ROOT-local (strike.py solves in the root's frame) while
    world_frames composes the root track in, so the blade rides the root; the game camera follows the root along the
    floor (look_r6 --tp)"""
    import clip as C
    cam = FP_EYE + np.asarray(tp_camera, float)
    root = c.get("root")
    if isinstance(root, list) and i < len(root):
        R, o = C.quat_mat(root[i][:4]), np.asarray(root[i][4:7], float)
        return cam + np.array([o[0], 0.0, o[2]]), R @ np.asarray(g, float) + o, R @ np.asarray(t, float) + o
    return cam, g, t


def cut_measures(c, tp_camera=None):
    """IS IT A CUT, ON LEGS THAT MOVE (the owner on the Swift set v2, 2026-11-04: "the leg work is horrible and some
    of them the sword isnt even attacking properly"; measured: 11 of 12 stood in a side-by-side straddle with 0.04 s foot
    flicks, 9 of 12 had a flourish as fast as the cut or the Hit overhead / beside / knee-high). Of the frames with the
    blade tip at >= half its top speed: how many are the CUT (within 0.12 s of the Hit), their share of all of them (a
    twirl as fast reads as the attack), the share with a point 60 % up the blade in FRONT (2-6 studs ahead of the root,
    |x| <= 3, waist -1.2 .. head +2.0), and how much the ARM drives it (grip speed / tip speed: a propeller spins the
    blade about a still fist). The legs: the front-back split of the soles at the Hit, the longest step (a sole > 0.15
    over the floor) overlapping 0.15 s either side of the Hit, the legs' widest angle off vertical. SEEN: from the game's
    third-person camera (the dossier's build tp_camera) the share of the blade's outer half, over the cut's frames, not
    hidden behind the body (a waist-high cut straight ahead is in the body's shadow from over the shoulder - the
    rebuilt TwirlCut's blade could not be seen at all on its Hit, 2026-11-04)"""
    import clip as C
    out = {}
    sw = c.get("sword") or {}
    fps = float(c.get("fps", 60))
    hit = next((float(e["t"]) for e in c.get("events", []) if e.get("name") == "Hit"), None)
    if not sw.get("tip") or not sw.get("grip_path"):
        return out
    tip, grip = np.asarray(sw["tip"], float), np.asarray(sw["grip_path"], float)
    n = len(tip)
    if tp_camera is not None:
        # the WHOLE clip (a trick, a twirl: the blade IS the show - the governor 2026-11-04), every 3rd frame, Hit or not
        # (a toss has none); an arms-only clip's other parts at rest
        rig = C.load_rig("r6")
        full = dict(c, joints=dict(c["joints"]))
        for j in J:
            full["joints"].setdefault(j, {"frames": [[0, 0, 0, 1, 0, 0, 0]] * len(c["times"])})
        Wv = C.world_frames(full, rig)
        seen, run, worst = [], 0, 0
        for i in range(0, min(n, len(Wv)), 3):
            s = blade_seen(Wv[i], rig, *_blade_view(c, i, grip[i], tip[i], tp_camera))
            seen += s
            run = run + 1 if np.mean(s) < 0.34 else 0
            worst = max(worst, run)
        out["blade_visible_share"] = float(np.mean(seen))
        # the LONGEST stretch the blade is unseen (the governor 2026-11-04: no candidate may hide it for more than
        # ~0.25 s; appeal flagged it, now the gate holds it)
        out["blade_unseen_max_s"] = float(worst * 3 / fps)
        # AT the burst (the biggest beat must be the most visible - the governor 2026-11-04): the Burst marker's frame
        # (else the Hit's) and one either side
        t_b = next((float(e["t"]) for e in c.get("events", []) if e.get("name") == "Burst"), hit)
        if t_b is not None:
            bi = min(n - 1, int(round(t_b * fps)))
            seen = []
            for i in range(max(0, bi - 1), min(n, len(Wv), bi + 2)):
                seen += blade_seen(Wv[i], rig, *_blade_view(c, i, grip[i], tip[i], tp_camera))
            out["blade_visible_at_burst"] = float(np.mean(seen))
    if hit is None:
        # (a trick with no Hit - a toss: its legs' widest angle is still a whole-clip number)
        if all(lg in (c.get("joints") or {}) for lg in ("Right Leg", "Left Leg")):
            Wl = C.world_frames(c, C.load_rig("r6"))
            out["leg_angle_max_deg"] = float(max(np.degrees(np.arccos(np.clip(w[lg][1, 1] / max(np.linalg.norm(w[lg][:3, 1]), 1e-9), -1, 1)))
                                                 for w in Wl for lg in ("Right Leg", "Left Leg")))
        return out
    at = min(n - 1, int(round(hit * fps)))
    v = np.linalg.norm(np.diff(tip, axis=0), axis=1) * fps
    gv = np.linalg.norm(np.diff(grip, axis=0), axis=1) * fps
    mid = grip + 0.6 * (tip - grip)
    fast = set(int(i) + 1 for i in np.where(v >= 0.5 * v.max())[0])
    cut = [i for i in fast if abs(i - at) <= int(round(0.12 * fps))]
    out["cut_fast_frames"] = float(len(cut))
    out["cut_fast_share"] = len(cut) / max(len(fast), 1)

    def front(p):
        return 2.0 <= -p[2] <= 6.0 and abs(p[0]) <= 3.0 and -1.2 <= p[1] <= 2.0
    out["cut_front_share"] = float(np.mean([front(mid[i]) for i in cut])) if cut else 0.0
    out["cut_arm_drive"] = float(np.mean([gv[i - 1] / max(v[i - 1], 1e-9) for i in cut])) if cut else 0.0
    if all(lg in (c.get("joints") or {}) for lg in ("Right Leg", "Left Leg")):
        W = C.world_frames(c, C.load_rig("r6"))
        sole = {lg: np.array([(w[lg] @ np.array([0, -1.0, 0, 1]))[:3] for w in W]) for lg in ("Right Leg", "Left Leg")}
        out["stance_split_hit_studs"] = float(abs(sole["Right Leg"][at, 2] - sole["Left Leg"][at, 2]))
        floor = min(sole["Right Leg"][0, 1], sole["Left Leg"][0, 1])
        lo, hi = hit - 0.15, hit + 0.15
        best = 0.0
        for s in sole.values():
            up = s[:, 1] > floor + 0.15
            i = 0
            while i < len(up):
                if up[i]:
                    j = i
                    while j < len(up) and up[j]:
                        j += 1
                    if i / fps < hi and j / fps > lo:
                        best = max(best, (j - i) / fps)
                    i = j
                else:
                    i += 1
        out["step_near_hit_s"] = best
        ang = [np.degrees(np.arccos(np.clip(w[lg][1, 1] / max(np.linalg.norm(w[lg][:3, 1]), 1e-9), -1, 1)))
               for w in W for lg in ("Right Leg", "Left Leg")]
        out["leg_angle_max_deg"] = float(max(ang))
        if tp_camera is not None and cut:
            rig = C.load_rig("r6")
            seen = []
            for i in cut:
                seen += blade_seen(W[i], rig, *_blade_view(c, i, grip[i], tip[i], tp_camera))
            out["cut_visible_share"] = float(np.mean(seen))
    return out


CLEAR_MEASURES = ("blade_body_max", "arm_socket_out_studs")


def clear_measures(c):
    """THE SWORD AND THE HANDS ON THE BODY (the owner on the drill's round 2, 2026-11-05: "OK BUT WHY IS THE SWORD AND
    HANDS WEIRD MAN"; measured: the sword arm slid 0.8 studs out of its shoulder, a visible gap):
      blade_body_max        the most of the blade (20-100 % of grip -> tip) inside the torso, the head, the legs or the
                            free arm on any frame - a blade through the body
      arm_socket_out_studs  the most either arm slides sideways OUT of its shoulder (the loved R6 strikes: p50 0.31,
                            p90 0.67 - r6_vocab weapon slide_outward)"""
    import clip as C
    rig = C.load_rig("r6")
    W = C.world_frames(c, rig)
    out = {"arm_socket_out_studs": 0.0}
    for arm, s in (("Right Arm", 1.0), ("Left Arm", -1.0)):
        if arm in c.get("joints", {}):
            out["arm_socket_out_studs"] = max(out["arm_socket_out_studs"], max(s * f[4] for f in c["joints"][arm]["frames"]))
    sw = c.get("sword") if isinstance(c.get("sword"), dict) else None
    if sw and sw.get("tip") and sw.get("grip_path"):
        free = "Left Arm"                                # (proc_blade mirrors every weapon to the right hand)
        us = np.linspace(0.2, 1.0, 17)
        worst = 0.0
        for i, w in enumerate(W[: len(sw["tip"])]):
            g, t = np.asarray(sw["grip_path"][i], float), np.asarray(sw["tip"][i], float)
            bp = g[None] + us[:, None] * (t - g)[None]
            hit = np.zeros(len(bp), bool)
            for part in ("Torso", "Head", "Left Leg", "Right Leg", free):
                loc = (np.linalg.inv(w[part]) @ np.c_[bp, np.ones(len(bp))].T).T[:, :3]
                hit |= np.all(np.abs(loc) < np.asarray(rig["sizes"][part], float) / 2, axis=1)
            worst = max(worst, float(np.mean(hit)))
        out["blade_body_max"] = worst
    return out


POSE_MEASURES = ("climax_hold_s", "climax_reach_gain_studs", "climax_outline_gain", "climax_torso_rate_dps",
                 "climax_hand_rise_studs", "climax_extension_studs")


def pose_measures(c):
    """A POSE THAT READS (the owner on both Spin Drill activations, 2026-11-04: "NONE BOTH LOOK HORRIBLEE"; measured:
    held 3 frames vs the loved Hq pack's 16-22, the fist no further from the chest than at the start, the torso turning
    170-188 deg/s vs 1,180-1,660). The climax = the Burst marker (else the Hit): the longest run of frames with every
    part turning < 90 deg/s between 0.2 s before it and 0.4 s after (s), the hands' furthest reach from the chest there
    minus at the start (studs), the front outline (the parts' extents, x by y) there over the start's, and the torso's
    fastest turn in the 0.2 s up to it (deg/s)"""
    import math
    import clip as C
    out = {}
    evs = c.get("events", [])
    t_c = next((float(e["t"]) for e in evs if e.get("name") == "Burst"), None)
    if t_c is None:
        t_c = next((float(e["t"]) for e in evs if e.get("name") == "Hit"), None)
    if t_c is None or not c.get("joints"):
        return out
    rig = C.load_rig("r6")
    W = C.world_frames(c, rig)
    fps = float(c.get("fps", 60))
    n = len(W)
    ci = min(n - 1, int(round(t_c * fps)))
    parts = [p for p in ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg") if p in W[0]]

    def turn(a, b):
        r = a[:3, :3].T @ b[:3, :3]
        return math.degrees(math.acos(max(-1.0, min(1.0, (float(np.trace(r)) - 1) / 2))))
    sp = [max(turn(W[i][p], W[i + 1][p]) * fps for p in parts) for i in range(n - 1)]
    best = run = 0
    for i in range(max(0, ci - int(0.2 * fps)), min(n - 1, ci + int(0.4 * fps))):
        run = run + 1 if sp[i] < 90 else 0
        best = max(best, run)
    out["climax_hold_s"] = best / fps

    def reach(w):
        chest = (w["Torso"] @ np.array([0, 0.5, 0, 1]))[:3]
        return max(float(np.linalg.norm((w[a] @ np.array([0, -1.0, 0, 1]))[:3] - chest)) for a in ("Right Arm", "Left Arm") if a in w)
    out["climax_reach_gain_studs"] = reach(W[ci]) - reach(W[0])
    # the EXTENSION out of the coil: the climax's reach minus the closest the hands came in the 0.3 s before it (a pose
    # that reads is drawn in, then flung out)
    out["climax_extension_studs"] = reach(W[ci]) - min(reach(W[i]) for i in range(max(0, ci - int(0.3 * fps)), ci + 1))
    top = lambda w: max(float((w[a] @ np.array([0, -1.0, 0, 1]))[1]) for a in ("Right Arm", "Left Arm") if a in w)
    out["climax_hand_rise_studs"] = top(W[ci]) - top(W[0])        # (the highest hand: a fist thrown to the sky)

    def outline(w):
        pts = []
        for p in parts:
            h = np.array(rig["sizes"][p]) / 2
            pts += [(w[p] @ np.array([sx * h[0], sy * h[1], sz * h[2], 1]))[:3] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        pts = np.array(pts)
        return float(np.ptp(pts[:, 0]) * np.ptp(pts[:, 1]))
    out["climax_outline_gain"] = outline(W[ci]) / max(outline(W[0]), 1e-9)
    yaw = np.degrees(np.unwrap([math.atan2(-w["Torso"][0, 2], w["Torso"][2, 2]) for w in W]))
    lo = max(1, ci - int(0.2 * fps))
    out["climax_torso_rate_dps"] = float(max(abs(yaw[i] - yaw[i - 1]) * fps for i in range(lo, ci + 1))) if ci >= lo else 0.0
    return out


def measures(c, d):
    if d["build"].get("builder") == "proc_react":
        return react_measures(c, d)
    if d["build"].get("builder") in ("strike", "locomotion"):   # (a locomotion cycle: the same body measures)
        return sword_measures(c, d)
    if d["build"].get("builder") == "fp_weapon":
        fns, ev = fp_measures(c, d)
        if (c.get("sword") or {}).get("tip"):
            # a strike-route clip in a weapon dossier (Greatsword's swings, 2026-10-31): the body's own sword measures too
            # (the torso's turn, the arms in the body), solved only when a check asks for one
            cache = {}

            def sword(k):
                if k == "arm_sink_max":                  # (sword_measures keeps it for the unarmed blows)
                    import clip as C
                    import strike as SK
                    rep = SK.arm_sink_report(c, C.load_rig("r6"), 0.0)
                    return lambda ck: float(rep["worst"]) if rep else 0.0
                if "f" not in cache:
                    # a masked clip (a Run version: arms + torso only) has no leg joints - they sit at rest
                    full = dict(c, joints=dict(c["joints"]))
                    for j in J:
                        full["joints"].setdefault(j, {"frames": [[0, 0, 0, 1, 0, 0, 0]] * len(c["times"])})
                    cache["f"] = sword_measures(full, d)[0]
                return cache["f"][k]
            for k in ("torso_yaw_range_deg", "arm_sink_max"):
                fns.setdefault(k, lambda ck, k=k: sword(k)(ck))
            for k in CUT_MEASURES:
                fns.setdefault(k, lambda ck, k=k: cache.setdefault("cut", cut_measures(c, (d.get("build") or {}).get("tp_camera"))).get(k, float("nan")))
            for k in POSE_MEASURES:
                fns.setdefault(k, lambda ck, k=k: cache.setdefault("pose", pose_measures(c)).get(k, float("nan")))
            for k in CLEAR_MEASURES:
                fns.setdefault(k, lambda ck, k=k: cache.setdefault("clear", clear_measures(c)).get(k, float("nan")))
            for k in SR.SHAPE_MEASURES:
                fns.setdefault(k, lambda ck, k=k: cache.setdefault("shape", SR.measure(c)).get(k, float("nan")))
        return fns, ev
    q, p = _world(c)
    n = len(q)
    b = d["build"]
    K, S = b["kick_leg"], b["support_leg"]
    ks, ss = J.index(K), J.index(S)
    ev, ksole = _events(c, d, q, p)
    ssole = np.array([P.sole_char(q[t, 0], p[t, 0], q[t, ss], p[t, ss], S) for t in range(n)])
    tyaw = _unwrap([_yaw(q[t, 0]) for t in range(n)])
    syaw = _unwrap([_yaw(P.q_mul(q[t, 0], q[t, ss])) for t in range(n)])
    up = np.array([P.q_rot(q[t, 0], np.array([0.0, 1.0, 0.0])) for t in range(n)])
    side = 1.0 if K.startswith("Right") else -1.0
    target = np.asarray(b.get("target", [0, 0, -3]), float)
    kfoot = np.array([_limb_end_world(q, p, t, K) for t in range(n)])
    fs = np.r_[0, np.linalg.norm(np.diff(kfoot, axis=0), axis=1)] * 60
    ys = np.abs(np.r_[0, np.diff(tyaw)]) * 60
    fc = ev["contact"]
    lo, hi = max(0, ev["toe_off"] - 6), min(n, ev["land"] + 1)

    def at(name):
        return ev[name]

    def lean_away(t):
        # tilt of the torso's up axis, signed + when it tilts AWAY from the kicking leg (torso-local -X for a right kick)
        tilt = math.degrees(math.acos(float(np.clip(up[t, 1], -1, 1))))
        away = P.q_rot(q[t, 0], np.array([-side, 0.0, 0.0]))
        return tilt if float(up[t, [0, 2]] @ away[[0, 2]]) >= 0 else -tilt

    def shin_vs_torso(t):
        hipw = p[t, 0] + P.q_rot(q[t, 0], DR.geom()[K][0] + p[t, ks])
        shin = hipw + 0.7 * (kfoot[t] - hipw)
        return float(shin[1] - p[t, 0, 1])

    def hand_local(t, limb):
        return DR.end({j: list(q[t, i]) + list(p[t, i]) for i, j in enumerate(J)}, limb)          # torso frame

    def head_to_target(t):
        hq = P.q_mul(q[t, 0], q[t, 1])
        face = P.q_rot(hq, np.array([0.0, 0.0, -1.0]))
        head = p[t, 0] + P.q_rot(q[t, 0], np.array([0.0, 1.5, 0.0]))
        want = target - head
        face, want = face / np.linalg.norm(face), want / np.linalg.norm(want)
        return math.degrees(math.acos(float(np.clip(face @ want, -1, 1))))
    rear = f"{'Right' if side > 0 else 'Left'} Arm"
    lead = f"{'Left' if side > 0 else 'Right'} Arm"
    def off_target(t):
        """the kicking sole's bearing from the torso vs the target's, over the ground (deg; + = past it to the right
        of the line, - = swept past to the left): an over-turned torso sends the leg PAST the target"""
        v, g = ksole[t] - p[t, 0], target - p[t, 0]
        a = np.degrees(np.arctan2(v[0], -v[2]) - np.arctan2(g[0], -g[2]))
        return float((a + 180) % 360 - 180)

    def arm_off(t, limb, fa):
        """the arm's long axis (shoulder -> hand, torso frame) vs a measured direction given as proc_director.arm_dir
        [forward_deg, across_deg] (0 = hanging, 90 = forward; + across = to the midline), in degrees"""
        if fa is None:
            return float("nan")                                     # a check without its 'dir' fails, never crashes
        # the PIVOT -> HAND vector the builder aims (proc_director.aim / geom), not the part's -Y (18 deg apart)
        v = P.q_rot(np.asarray(q[t, J.index(limb)]), DR.geom()[limb][1])
        w = DR.arm_dir(limb.split()[0], float(fa[0]), float(fa[1]))
        return math.degrees(math.acos(float(np.clip(v @ w / (np.linalg.norm(v) * np.linalg.norm(w)), -1, 1))))

    out = {
        "support_foot_yaw_change_deg": lambda ck: float(syaw[at(ck.get("at", "contact"))] - syaw[at(ck.get("from", "guard"))]),
        "support_sole_drift_studs": lambda ck: float(np.linalg.norm((ssole[:, [0, 2]] - ssole[0, [0, 2]]), axis=1).max()),
        "torso_yaw_deg": lambda ck: float(tyaw[at(ck.get("at", "contact"))]),
        "torso_yaw_change_deg": lambda ck: float(tyaw[at(ck.get("at", "contact"))] - tyaw[at(ck.get("from", "guard"))]),
        "kick_foot_off_target_deg": lambda ck: off_target(at(ck.get("at", "contact"))),
        "kick_sole_end_offset_studs": lambda ck: float(np.linalg.norm((ksole[-1] - ksole[0])[[0, 2]])),
        "arm_dir_off_deg": lambda ck: arm_off(at(ck.get("at", "contact")), rear if ck.get("arm") == "kick" else lead, ck.get("dir")),
        "lead_time_s": lambda ck: float((lo + int(np.argmax(fs[lo:hi])) - (lo + int(np.argmax(ys[lo:hi])))) / 60),
        "torso_lean_away_deg": lambda ck: lean_away(at(ck.get("at", "contact"))),
        "kick_shin_height_vs_torso_studs": lambda ck: shin_vs_torso(at(ck.get("at", "contact"))),
        "torso_rise_studs": lambda ck: float(p[at(ck.get("at", "contact")), 0, 1] - p[0, 0, 1]),
        "kick_side_hand_behind_hip": lambda ck: float(hand_local(at(ck.get("at", "contact")), rear)[2]),
        "guard_hand_height_studs": lambda ck: float(hand_local(at(ck.get("at", "contact")), lead)[1]),
        "head_to_target_deg": lambda ck: head_to_target(at(ck.get("at", "contact"))),
        "toe_off_to_hit_s": lambda ck: (ev["contact"] - ev["toe_off"]) / 60,
        "torso_yaw_past_contact_deg": lambda ck: float(tyaw[fc:].max() - tyaw[fc]),
        "hit_to_land_s": lambda ck: (ev["land"] - ev["contact"]) / 60,
        "strike": lambda ck: strike_stat(c, ck, ev["contact"]),
    }
    return out, ev


def strike_stat(c, ck, hit_frame):
    """the pro-animator SHAPE of the main strike of `ck['joint']` (the strike nearest the Hit): strike_style's
    antic_ratio / antic_s / snap_frames / hold_frames / peak_at / overshoot, comparable with the loved percentiles"""
    import proc_calib as PC
    import strike_style as SS
    k = J.index(ck["joint"])
    ss = [x for x in SS.strikes(PC.rot_arrays(c)) if x["joint"] == k]
    if not ss:
        return float("nan")
    x = min(ss, key=lambda x: abs(x["frame"] - hit_frame))
    return float(x[ck["stat"]]) if x.get(ck["stat"]) is not None else float("nan")


MEASURES = {"head_peak_deg", "head_to_peak_s", "head_speed_deg_s", "torso_peak_deg", "torso_shove_studs", "torso_lag_s",
            "head_nod_up_share", "torso_yaw_range_deg", "arm_slide_max_studs", "main_arm_hold_s", "arm_peak_dps",
            "leg_twist_max_deg", "blade_path_off_deg", "clip_seconds", "hands_side_max_studs", "bottom_pause_s", "finish_hands_over_shoulders_studs", "edge_up_at_start", "edge_up_at_hit",
            "strike", "support_foot_yaw_change_deg", "support_sole_drift_studs", "torso_yaw_deg", "lead_time_s", "torso_lean_away_deg",
            "torso_yaw_change_deg", "kick_foot_off_target_deg", "arm_dir_off_deg", "kick_sole_end_offset_studs",
            "kick_shin_height_vs_torso_studs", "torso_rise_studs", "kick_side_hand_behind_hip", "guard_hand_height_studs",
            "head_to_target_deg", "toe_off_to_hit_s", "torso_yaw_past_contact_deg", "hit_to_land_s",
            "parry_blade_up_deg", "parry_hold_s", "riposte_s",
            "stamp_lead_s", "body_drive_studs", "guard_hands_min_height_studs", "arm_sink_max", "hit_time_s",
            "fp_weapon_in_view_share", "fp_weapon_low_y", "fp_center_blocked_share", "muzzle_rise_deg", "muzzle_peak_s",
            "grip_roll_max_deg", "shot_aim_err_deg", "shot_gun_rise_deg", "shot_gun_peak_s", "shot_gun_turn_max_deg",
            "shot_count", "shots_aim_err_max_deg", "toss_flight_min_s", "toss_flight_max_s", "shots_while_other_up",
            "shots_from_a_gun_in_the_air", "tp_center_blocked_share", "hit_tip_speed_share", "tip_floor_min_studs",
            "leg_pitch_deg", "leg_splay_deg", "leg_slide_studs", "torso_lean_deg", "torso_roll_deg", "torso_drop_studs",
            "lowest_part_studs"} | set(CUT_MEASURES) | set(POSE_MEASURES) | set(CLEAR_MEASURES) | set(SR.SHAPE_MEASURES)


def applies(ck, name):
    """a check with "for": [glob, ...] holds only for the clips whose name matches one (one dossier, a family of
    variants: Sample Game's single-gun tricks and its two-gun juggles share gun_dual_trick); no "for" = every clip"""
    import fnmatch
    pats = ck.get("for")
    return not pats or any(fnmatch.fnmatchcase(str(name or ""), str(p)) for p in pats)


def check(c, d, ranges=None):
    """ranges: {check id: [lo, hi]} - a persona's own ranges (a brawler OVERCOMMITS past the 'through' range on purpose).
    A STEPPED clip (limited animation) is measured on its smooth motion (clip.destep): the steps are presentation"""
    import clip as CL
    c = CL.destep(c)
    fns, ev = measures(c, d)
    res = {}
    for ck in d["checks"]:
        if not applies(ck, c.get("name")):
            continue
        v = fns.get(ck["measure"], lambda _ck: float("nan"))(ck)
        rg = (ranges or {}).get(ck["id"], ck["range"])
        lo, hi = rg
        res[ck["id"]] = {"value": round(v, 3), "range": rg, "pass": bool(lo <= v <= hi), "why": ck["why"]}
    return {"checks": res, "events_s": {k: round(v / 60, 3) for k, v in ev.items()},
            "pass": all(r["pass"] for r in res.values())}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    cmd = a[0] if a else "help"
    if cmd == "new":
        name = a[1]
        cat = a[a.index("--category") + 1] if "--category" in a else "combat"
        path = os.path.join(DIR, f"{name}.json")
        if os.path.exists(path) and "--force" not in a:
            verdict("fail", f"dossier {name} exists ({path})", f"edit {path}, then: lune run kit anim dossier check {name}")
            sys.exit(1)
        os.makedirs(DIR, exist_ok=True)
        json.dump(scaffold(name, cat), open(path, "w", encoding="utf-8", newline=""), indent=1)
        import catalog_coverage as CC                        # (what the catalogue has ever seen of its like: said up front)
        verdict("pass", f"dossier scaffold {path} - every TODO is research to do (research_list); " + CC.line(name.replace("_", " ")),
                f"improve: research {name} (its research_list), replace every TODO, then: lune run kit anim dossier check {name}")
    elif cmd == "check":
        try:
            d = require(a[1])
        except SystemExit as e:
            verdict("fail", str(e), f"fill the dossier: {os.path.join(DIR, a[1] + '.json')}")
            sys.exit(1)
        import dossier_evidence as DE
        ev = DE.read(d)
        verdict("pass", f"dossier {a[1]}: {len(d['sources'])} sources, {len(d['phases'])} phases, {len(d['checks'])} checks - complete; "
                + DE.words(a[1], ev).split(": ", 1)[1] + "; " + __import__("catalog_coverage").line(a[1].replace("_", " ")),
                "none - proceed" if not ev["unsupported"] else
                f"its {', '.join(ev['unsupported'])} rest(s) on inference: measure it (kit anim dossier footage) or have the owner say it",
                evidence=ev)
    elif cmd == "gate":
        # gate <source>=<dossier> ...: the authored clips that need a complete dossier (kit anim compile)
        missing = {}
        for pair in a[1:]:
            src, dos, *rest = pair.split("=")
            try:
                d = require(dos)
            except SystemExit as e:
                missing[src] = str(e)
                continue
            why = rejection_missing(d, [src])
            if not why and rest and rest[0]:
                why = build_failing(d, rest[0])
            if why:
                missing[src] = f"dossier '{dos}': {why}"
        # WHAT THE CATALOGUE HAS OF EACH MOVE, said on the build (the owner's V3 list, anim stage A.2: catalog_coverage
        # was read only by the dossier commands, so a move nothing loved stands behind was built in silence). Not a
        # refusal: a move's dossier must already be measured (the dossier lock); words cannot know the motion
        coverage = gate_coverage(a[1:], missing)
        if missing:
            first = next(iter(missing))
            verdict("fail", f"{len(missing)} clip(s) without a complete move dossier", f"{first}: {missing[first]}",
                    missing=missing, coverage=coverage)
            sys.exit(1)
        verdict("pass", f"{len(a) - 1} clip(s) have complete dossiers", "none - proceed", coverage=coverage)
    elif cmd == "measure":
        d = require(a[1])
        r = check(json.load(open(a[2], encoding="utf-8")), d)
        for k, v in r["checks"].items():
            print(f"  {'ok  ' if v['pass'] else 'FAIL'} {k:12s} {v['value']:>8} in {v['range']}  ({v['why']})")
        bad = [k for k, v in r["checks"].items() if not v["pass"]]
        verdict("pass" if not bad else "fail", f"{len(r['checks']) - len(bad)}/{len(r['checks'])} dossier checks pass",
                "none - proceed" if not bad else f"{bad[0]}: {r['checks'][bad[0]]['value']} outside {r['checks'][bad[0]]['range']} ({r['checks'][bad[0]]['why']})",
                events=r["events_s"])
        sys.exit(0 if not bad else 1)
    else:
        print(__doc__)
