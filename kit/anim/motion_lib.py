"""motion_lib.py — the SEARCHABLE R6 MOTION LIBRARY (owner-approved 2026-10-12: "animate ANYTHING on R6" - the model
directs in words, real human-made motion performs; step 1 of the plan = every clip described in words + retrieval).

Every native R6 clip of the library (_artifacts/r6lib/index.json) gets:
  - MEASURED tags from its own motion on the R6 rig (which hand works, the strike's direction and speed, two-handed,
    kicks, steps / lunges, jumps, crouches, spins, twists, holds, loops, tempo) - never guessed from the name alone
  - a CAPTION in plain words built from those tags + its name / pack / kind
  - a LICENCE tag: "game" (Creator Store: usable in Roblox experiences; DevForum posts whose terms say free use) or
    "study" (no licence text, help threads, non-commercial) - search shows game-safe clips by default
  - the owner's verdict (assets/animations/library/owner_picks.json: love / ok / bad / laggy / unrated)

    python kit/anim/motion_lib.py build                       -> _artifacts/r6lib/catalog.json (+ a check line)
    python kit/anim/motion_lib.py find "heavy two handed overhead slam" [--k 12] [--all] [--kind attack]
    python kit/anim/motion_lib.py show <id>
    python kit/anim/motion_lib.py adapt <id> --as <Name> [--mirror] [--tempo 1.2] [--amp 1.1] [--hitstop 5]
                                    [--trim a:b] [--slide 2.5] [--render]
                                    -> _artifacts/r6lib/adapted/<Name>.clip.json (+ a gif on the owner's rig)
Measurement frame: the character's HumanoidRootPart at the origin, Roblox axes (+Y up, -Z forward, +X right)."""
import copy
import json
import math
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
_KIT = os.path.abspath(os.path.join(HERE, ".."))
if _KIT not in sys.path:
    sys.path.insert(0, _KIT)
import clip as C  # noqa: E402
from blender_path import find_blender  # noqa: E402

LIB = os.path.join("_artifacts", "r6lib")
CATALOG = os.path.join(LIB, "catalog.json")
PICKS = os.path.join("assets", "animations", "library", "owner_picks.json")
BLENDER = find_blender() or "blender"

# DevForum topics whose post states free use (VETLOG rows 94, 99); every other DevForum file is study-only until its
# terms are read and added here with the quote
DEVFORUM_GAME = {"d1595359": "'Basic run, free for use, R6' (azazinchic): 'free for use'",
                 "d4555875": "'Free Friday! (29)' (KingAlijahforever): 'Entirely FREE'",
                 "d2480548": "'Black And White Fighting Module' (d5v): 'No credit is required'"}

SYN = {"greatsword": "sword heavy twohanded", "claymore": "sword heavy twohanded", "zweihander": "sword heavy twohanded",
       "katana": "sword slash", "blade": "sword slash", "sword": "sword slash swing", "axe": "heavy downward swing",
       "hammer": "heavy downward slam", "scythe": "swing horizontal", "spear": "thrust stab", "stab": "thrust",
       "punch": "punch m1 combo thrust", "jab": "punch thrust fast", "hook": "punch horizontal", "fist": "punch",
       "uppercut": "upward punch", "kick": "kick", "slam": "downward slam", "smash": "downward slam",
       "overhead": "downward raised", "chop": "downward", "sweep": "horizontal", "cleave": "downward heavy",
       "spin": "spin", "whirl": "spin", "twirl": "spin", "dodge": "dash", "roll": "dash", "evade": "dash",
       "block": "defence", "parry": "defence", "guard": "defence idle", "hurt": "reaction", "stagger": "reaction",
       "knockback": "reaction", "flinch": "reaction", "die": "reaction", "death": "reaction",
       "sprint": "run", "jog": "run", "leap": "jump airborne", "jump": "jump airborne", "crouch": "crouch",
       "heavy": "heavy slow", "light": "fast", "quick": "fast", "fast": "fast", "slow": "slow", "big": "heavy",
       "dance": "dance emote loop", "emote": "emote", "wave": "emote wave", "throw": "throw thrust",
       "two": "twohanded", "both": "twohanded", "lunge": "lunge forward", "dash": "dash lunge"}
STOP = {"a", "an", "the", "of", "with", "and", "to", "in", "on", "r6", "anim", "animation", "animations", "by", "for"}


def words(text):
    t = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(text or ""))
    return [w for w in re.findall(r"[a-z]+|\d+", t.lower()) if w not in STOP]


def licence_of(row):
    if row.get("source") == "Creator Store":
        return "game", "Creator Store asset: usable in Roblox experiences (re-upload under the game's owner)"
    topic = row["id"].split("_")[0]
    if topic in DEVFORUM_GAME:
        return "game", DEVFORUM_GAME[topic]
    return "study", "no free-use terms recorded for this DevForum post"


# ---------------------------------------------------------------- measuring
def _unwrap_deg(a):
    return np.degrees(np.unwrap(np.radians(a)))


def measure(c, rig):
    """motion tags of one R6 clip, measured on the rig"""
    W = C.world_frames(c, rig)
    t = np.asarray(c["times"], float)
    n = len(W)
    if n < 3:
        return None

    def pt(part, local):
        return np.array([(np.asarray(w[part]) @ np.array([*local, 1.0]))[:3] for w in W])

    hand = {"right": pt("Right Arm", (0, -1, 0)), "left": pt("Left Arm", (0, -1, 0))}
    foot = {"right": pt("Right Leg", (0, -1, 0)), "left": pt("Left Leg", (0, -1, 0))}
    torso = np.array([np.asarray(w["Torso"])[:3, 3] for w in W])
    fwd = np.array([-np.asarray(w["Torso"])[:3, 2] for w in W])
    yaw = _unwrap_deg(np.degrees(np.arctan2(-fwd[:, 0], -fwd[:, 2])))
    pitch = np.degrees(np.arcsin(np.clip(fwd[:, 1], -1, 1)))
    dt = np.maximum(np.diff(t), 1e-3)

    def speed(P):
        return np.linalg.norm(np.diff(P, axis=0), axis=1) / dt

    sp = {k: speed(v) for k, v in hand.items()}
    travel = {k: float(np.sum(np.linalg.norm(np.diff(v, axis=0), axis=1))) for k, v in hand.items()}
    peak = {k: float(np.percentile(v, 98)) for k, v in sp.items()}
    tags, facts = [], {}
    dur = float(t[-1] - t[0])
    loop = bool(c.get("loop"))
    facts.update(duration=round(dur, 3), loop=loop)
    if loop:
        tags.append("loop")

    # which hands work
    big = max(travel.values())
    if big < 0.5:
        active = []
    else:
        active = [k for k in ("right", "left") if travel[k] >= 0.55 * big]
    gap = np.linalg.norm(hand["right"] - hand["left"], axis=1)
    together = float(np.mean(gap < 1.3))
    two_handed = together > 0.6 and len(active) == 2
    if two_handed:
        tags.append("twohanded")
    elif len(active) == 1:
        tags.append(active[0] + "hand")
    elif len(active) == 2:
        tags.append("botharms")
    facts.update(hand_travel={k: round(v, 2) for k, v in travel.items()}, hands_together=round(together, 2))

    # the strike: the fastest moment of the working hand (one-shots only)
    lead = max(peak, key=peak.get)
    pk = peak[lead]
    facts["peak_hand_speed"] = round(pk, 1)
    if pk > 26:
        tags.append("fast")
    elif pk < 9:
        tags.append("slow")
    raised = float(np.max([(np.linalg.inv(np.asarray(w["Torso"])) @ np.array([*hand[lead][i], 1.0]))[1] for i, w in enumerate(W)]))
    if raised > 1.6:
        tags.append("raised")
    if not loop and pk > 14:
        # the strike = the peak of the working hand's SMOOTHED speed, away from the clip's first / last frames (a clip
        # that starts in a far pose snaps there in one frame - that is not the hit); its direction = the hand's travel
        # over a few frames around the peak, in the torso's own facing (so a twisted swing still reads right)
        s_ = np.convolve(sp[lead], np.ones(3) / 3, mode="same")
        lo, hi = (2, len(s_) - 2) if len(s_) > 6 else (0, len(s_))
        i = lo + int(np.argmax(s_[lo:hi]))
        a, b = max(0, i - 2), min(n - 1, i + 3)
        v = hand[lead][b] - hand[lead][a]
        v = v / max(np.linalg.norm(v), 1e-9)
        R = np.asarray(W[i]["Torso"])[:3, :3]
        right_h, fwd_h = R[:, 0] * [1, 0, 1], -R[:, 2] * [1, 0, 1]
        right_h /= max(np.linalg.norm(right_h), 1e-9)
        fwd_h /= max(np.linalg.norm(fwd_h), 1e-9)
        x, f_ = float(v @ right_h), float(v @ fwd_h)
        if v[1] < -0.6:
            d = "downward"
        elif v[1] > 0.6:
            d = "upward"
        elif f_ > 0.6:
            d = "thrust"
        elif abs(x) > 0.6:
            d = "horizontal"
        else:
            d = "diagonal"
        tags += ["strike", d]
        facts["strike"] = {"hand": lead, "dir": d, "at_s": round(float(t[i] - t[0]), 3), "at_frac": round(float((t[i] - t[0]) / max(dur, 1e-6)), 2),
                           "side": "right-to-left" if x < -0.4 else "left-to-right" if x > 0.4 else "centre"}
        if facts["strike"]["at_frac"] > 0.45:
            tags.append("windup")

    # legs: a foot lifted high (kicks, but also dash / jump tucks: on 15 clips named kick the lifted foot's speed did
    # not separate kicks from the rest, so the tag says only what was measured - "kick" comes from the name) - one foot lifted well above the planted one (the ground = the lower foot that frame) and swung away
    # from the body (any direction: front, roundhouse, side) for a few frames; measured on 15 clips named kick
    ground = np.minimum(foot["right"][:, 1], foot["left"][:, 1])
    for k, P in foot.items():
        up = P[:, 1] - ground
        away = np.linalg.norm((P - torso)[:, [0, 2]], axis=1)
        lifted = (up > 1.6) | ((up > 1.1) & (away > 1.3))
        if not loop and int(np.sum(lifted)) >= 2:
            fs = speed(P)
            fast_foot = float(np.max(fs[lifted[1:]])) if np.any(lifted[1:]) else 0.0
            tags.append("legup")
            facts["leg_up"] = {"leg": k, "foot_speed": round(fast_foot, 1)}
            break
    if loop and max(float(np.ptp(foot[k][:, 2])) for k in foot) > 1.2:
        tags.append("stride")

    # the body: travel, height, turns, lean, holds
    disp = torso - torso[0]
    horiz = disp[:, [0, 2]]
    far = int(np.argmax(np.linalg.norm(horiz, axis=1)))
    hd = float(np.linalg.norm(horiz[far]))
    if hd > 0.8 and not loop:
        tags.append("lunge" if -horiz[far][1] > 0.5 * hd else "backstep" if horiz[far][1] > 0.5 * hd else "sidestep")
    rise = float(disp[:, 1].max())
    drop = float(-disp[:, 1].min())
    if rise > 1.0:
        tags += ["airborne", "jump"]
    if drop > 0.7:
        tags.append("crouch")
    turn_total = float(np.ptp(yaw))
    if turn_total > 270:
        tags.append("spin")
    elif turn_total > 60:
        tags.append("twist")
    lean = float(np.max(np.abs(pitch - pitch[0])))
    if lean > 30:
        tags.append("lean")
    allsp = sum(sp.values()) + speed(foot["right"]) + speed(foot["left"])
    still = float(np.mean(allsp < 0.6))
    if still > 0.35:
        tags.append("holds")
    if pk > 14 and "heavy" not in tags and facts.get("strike", {}).get("at_frac", 0) > 0.35 and dur > 0.7:
        tags.append("heavy")
    facts.update(travel=round(hd, 2), rise=round(rise, 2), drop=round(drop, 2), turn=round(turn_total, 1), lean=round(lean, 1), still=round(still, 2))
    return {"tags": sorted(set(tags)), "facts": facts}


DIR_WORDS = {"downward": "chops / slams downward", "upward": "swings upward", "thrust": "thrusts forward",
             "horizontal": "sweeps sideways", "diagonal": "swings diagonally"}


def caption(row, m):
    f, tags = m["facts"], set(m["tags"])
    bits = []
    who = "two-handed" if "twohanded" in tags else "right-handed" if "righthand" in tags else "left-handed" if "lefthand" in tags else "both arms" if "botharms" in tags else "no arm work"
    if "strike" in f:
        s = f["strike"]
        bits.append(f"{who}: {DIR_WORDS[s['dir']]} ({s['side']}) at {s['at_s']:.2f} s, hand {f['peak_hand_speed']:.0f} studs/s")
    else:
        bits.append(f"{who}, hand up to {f['peak_hand_speed']:.0f} studs/s")
    for tg, words_ in (("legup", f"lifts the {f.get('leg_up', {}).get('leg')} leg high"), ("lunge", f"lunges forward {f['travel']:.1f} studs"),
                       ("backstep", f"steps back {f['travel']:.1f} studs"), ("sidestep", f"steps sideways {f['travel']:.1f} studs"),
                       ("airborne", f"leaves the ground ({f['rise']:.1f} studs)"), ("crouch", f"drops low ({f['drop']:.1f} studs)"),
                       ("spin", f"spins ({f['turn']:.0f} deg)"), ("twist", f"twists the body {f['turn']:.0f} deg"),
                       ("lean", f"leans {f['lean']:.0f} deg"), ("raised", "hand raised above the head"),
                       ("windup", "long wind-up"), ("holds", "holds poses"), ("stride", "walking / running stride"), ("loop", "loops")):
        if tg in tags:
            bits.append(words_)
    return f"{row.get('kind', 'other')} '{row['name']}' ({f['duration']:.2f} s): " + ", ".join(bits) + f". Pack '{row.get('pack', '')}' by {row.get('creator', '?')}."


# ---------------------------------------------------------------- build
def build():
    index = json.load(open(os.path.join(LIB, "index.json"), encoding="utf-8"))
    picks = {}
    if os.path.isfile(PICKS):
        picks = {r["id"]: r for r in json.load(open(PICKS, encoding="utf-8"))["picks"]}
    rig = C.load_rig("r6")
    out, failed = [], 0
    for row in index:
        p = os.path.join(LIB, "clips", f"{row['id']}.clip.json")
        if not os.path.isfile(p):
            continue
        try:
            m = measure(json.load(open(p, encoding="utf-8")), rig)
        except Exception:
            m = None
        if m is None:
            failed += 1
            continue
        pk = picks.get(row["id"])
        verdict = "unrated" if pk is None else ("laggy" if pk.get("laggy") else pk["verdict"])
        lic, why = licence_of(row)
        out.append({"id": row["id"], "name": row["name"], "kind": row.get("kind", "other"), "pack": row.get("pack", ""),
                    "creator": row.get("creator", ""), "source": row.get("source", ""), "asset": row.get("asset"),
                    "licence": lic, "licence_note": why, "verdict": verdict, "gif": row.get("gif"),
                    "tags": m["tags"], "facts": m["facts"], "caption": caption(row, m)})
    json.dump({"schema": 1, "clips": out}, open(CATALOG, "w", encoding="utf-8"), indent=0)
    return out, failed


LIVE_PICKS = os.path.join(LIB, "picks.json")     # the picker's live file: every click on /find or / lands here


def live_verdicts():
    """{id: verdict} from the picker's live file (the FLYWHEEL: a rating on the search page counts at once)"""
    try:
        live = json.load(open(LIVE_PICKS, encoding="utf-8"))
    except Exception:
        return {}
    return {k: ("laggy" if v.get("laggy") else v.get("verdict")) for k, v in live.items() if v.get("verdict") or v.get("laggy")}


def load():
    cat = json.load(open(CATALOG, encoding="utf-8"))["clips"]
    live = live_verdicts()
    for r in cat:
        if r["id"] in live:
            r["verdict"] = live[r["id"]]
    return cat


# ---------------------------------------------------------------- search
# the owner's verdict scales the text match (a bad clip that matches every word still loses to a loved near-match)
VERDICT_WEIGHT = {"love": 1.4, "ok": 1.0, "unrated": 0.9, "bad": 0.45, "laggy": 0.35}


def expand(query):
    out = []
    for w in words(query):
        out.append(w)
        out += SYN.get(w, "").split()
        if w.endswith("s") and w[:-1] in SYN:
            out += [w[:-1]] + SYN[w[:-1]].split()
    return out


def doc_tokens(r):
    return words(r["name"]) * 2 + words(r["pack"]) + words(r["kind"].replace("/", " ")) * 2 + r["tags"] * 2


def find(query, k=12, game_only=True, kind=None, cat=None):
    cat = cat or load()
    docs = [(r, doc_tokens(r)) for r in cat if (not game_only or r["licence"] == "game") and (kind is None or r["kind"] == kind)]
    N = max(1, len(docs))
    df = {}
    for _, toks in docs:
        for w in set(toks):
            df[w] = df.get(w, 0) + 1
    q = expand(query)
    scored = []
    for r, toks in docs:
        s = 0.0
        tf = {}
        for w in toks:
            tf[w] = tf.get(w, 0) + 1
        for w in set(q):
            if w in tf:
                s += math.log(1 + N / df[w]) * (1 + math.log(tf[w]))
        if s <= 0:
            continue
        if r["kind"] in ("dance", "emote") and not ({"dance", "emote"} & set(q)):
            s *= 0.3                                        # 'roll' must not find 'RickRoll' before a dodge roll
        scored.append((s * VERDICT_WEIGHT.get(r["verdict"], 0.9), r))
    scored.sort(key=lambda x: -x[0])
    return [(round(s, 2), r) for s, r in scored[:k]]


# ---------------------------------------------------------------- adapt
def adapt(cid, name, mirror=False, tempo=1.0, amp=1.0, hitstop=0, trim=None, slide=0.0, render=False):
    import derive as D
    c = json.load(open(os.path.join(LIB, "clips", f"{cid}.clip.json"), encoding="utf-8"))
    c = copy.deepcopy(c)
    if int(round(float(c.get("fps") or 30))) != 60:
        D.op_retime(c, duration=float(c["times"][-1]), fps=60)
    if trim:
        a, b = trim
        D.op_trim(c, start=a, end=b)
    if mirror:
        D.op_mirror(c)
    if amp != 1.0:
        D.op_amplify(c, ["Torso", "Right Arm", "Left Arm"], amp)
    if tempo != 1.0:
        D.op_retime(c, duration=float(c["times"][-1]) * tempo, fps=60)
    if hitstop:
        D.op_hold(c, D.impact_index(c) / 60.0, int(hitstop))
    if slide:
        D.op_r6slide(c, slide, kind="attack")
    c["name"] = name
    c["adapted_from"] = {"id": cid, "mirror": mirror, "tempo": tempo, "amp": amp, "hitstop": hitstop, "trim": trim, "slide": slide}
    odir = os.path.join(LIB, "adapted")
    os.makedirs(odir, exist_ok=True)
    path = os.path.join(odir, f"{name}.clip.json")
    json.dump(c, open(path, "w", encoding="utf-8"))
    gif = None
    if render:
        look = f"{name}.r6"
        subprocess.run([BLENDER, "-b", os.environ.get("PARALLAX_R6_RIG") or "assets/rigs/R6_IK.blend", "--disable-autoexec", "--python-exit-code", "2", "-P",
                        "kit/anim/look_r6.py", "--", look, "--clip", path, "--out", odir, "--size", "300"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
        subprocess.run([sys.executable, "kit/anim/look_sheet.py", os.path.join(odir, f"{look}.look")], capture_output=True)
        g = os.path.join(odir, f"{look}.look.gif")
        gif = g if os.path.isfile(g) else None
    return path, gif


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}, ensure_ascii=False))


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "build":
        out, failed = build()
        tags = {}
        for r in out:
            for tg in r["tags"]:
                tags[tg] = tags.get(tg, 0) + 1
        lic = sum(1 for r in out if r["licence"] == "game")
        emit("pass" if out else "fail", f"catalog: {len(out)} clips described ({failed} unreadable), {lic} game-safe; tags {dict(sorted(tags.items(), key=lambda x: -x[1]))}",
             'python kit/anim/motion_lib.py find "<what you want>"')
        return 0
    if cmd == "find":
        k = int(argv[argv.index("--k") + 1]) if "--k" in argv else 12
        kind = argv[argv.index("--kind") + 1] if "--kind" in argv else None
        res = find(argv[1], k=k, game_only="--all" not in argv, kind=kind)
        for s, r in res:
            print(f"{s:6.2f}  {r['id']:<26} [{r['verdict']:<7}|{r['licence']}] {r['caption']}")
        emit("pass" if res else "warn", f"find '{argv[1]}': {len(res)} clips", "python kit/anim/motion_lib.py adapt <id> --as <Name> --render")
        return 0
    if cmd == "show":
        r = next((x for x in load() if x["id"] == argv[1]), None)
        print(json.dumps(r, indent=1, ensure_ascii=False))
        return 0 if r else 1
    if cmd == "adapt":
        def opt(k, d, cast=float):
            return cast(argv[argv.index(k) + 1]) if k in argv else d
        trim = None
        if "--trim" in argv:
            a, b = argv[argv.index("--trim") + 1].split(":")
            trim = (float(a or 0), float(b) if b else None)
        path, gif = adapt(argv[1], opt("--as", argv[1] + "_adapted", str), mirror="--mirror" in argv, tempo=opt("--tempo", 1.0),
                          amp=opt("--amp", 1.0), hitstop=opt("--hitstop", 0, int), trim=trim, slide=opt("--slide", 0.0), render="--render" in argv)
        emit("pass", f"adapted -> {path}" + (f", gif {gif}" if gif else ""), "look at the gif beside the source clip's gif")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")       # clip names carry emoji; a Windows console codec would crash
    sys.exit(main(sys.argv[1:]))
