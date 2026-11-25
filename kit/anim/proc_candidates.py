"""proc_candidates.py — OUR candidates for one action (mission 04-anim 5.4): the move's dossier build keys varied by the
four Laban EFFORT sliders (each -1 .. +1), every one gated, the owner picks (kit anim picks), the next round breeds
from the picks only. Never a catalog clip: a candidate's lineage holds only the dossier and earlier candidates.
  time    sudden (+) / sustained (-): the strike window and the recovery shorter / longer
  weight  strong (+) / light (-): a deeper wind-up and dip, a higher kick, a deeper lean, a bigger arm swing back
  space   direct (-) / indirect (+): how far the hips spin THROUGH past contact
  flow    free (+) / bound (-): the springs' follow-through (overlap, drag) loosened / tightened
  arms    (a choice, not a slider) 'habit:H:<whip>' = one of the four loved ARM HABITS (r6_vocab) + the kick-side
          arm's whip; also 'technique' (the dossier's arm keys), 'vocab:<whip>' (the mean directions), 'prior:N' (the
          combat pose prior's N-th mode). The Thai arm checks are not held to the non-technique arms: reported as
          warnings in the manifest
Gates (each candidate must pass ALL; they filter, never rank): the engine's motion gates (clip.metrics), the procedural
gates (proc_gates, incl. style_band + copy_floor), the dossier's numeric checks, MuJoCo plausibility.
The SHEET (gallery tuning, 2026-11-08 - kit/anim/anim_gallery.py): about 2.5 x n gate-clean candidates are built and n
chosen - with the owner's picks and rejections on earlier rounds, likely-good beside informative (the model's best
guesses and where it knows least), else spread; always spaced apart by their MOTION (the owner's "cousins"). The
manifest records each one's role and the evidence (`gallery`).
The RANGE (efforts mapping 2, 2026-11-09 - EFFORTS): the sliders above are the first mapping, kept for its rounds. A new
round's efforts move the whole body (apply_sliders_v2), each as far as the move's own checks allow (reach_of: probed
per move), and a blade's cut is also turned into other planes (lines_of: the passing LINES, each its share of the
sheet). The manifest records `efforts`, `reach` and `lines`; zero efforts are the dossier's own build under every one.
    python kit/anim/proc_candidates.py <Name> --dossier <move> [--n 8] [--round K --parents <id>,<id>]
      -> build/candidates/<Name>/round_<K>/<id>.clip.json + assets/animations/candidates/<Name>/round_<K>.json"""
import copy
import json
import math
import os
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import proc_dossier as DS  # noqa: E402
import proc_gates as GT  # noqa: E402
import proc_kick as PK  # noqa: E402
import proc_react as PRX  # noqa: E402
import proc_strike as PST  # noqa: E402
import proc_blade as PB  # noqa: E402
import anim_gallery as AG  # noqa: E402  (gallery tuning: the owner's picks + rejections choose the sheet)

SLIDERS = ("time", "weight", "space", "flow")
BUILDERS = {"proc_kick": PK, "proc_react": PRX}
# the owner's own KEYED blocks (a strike-route move file, builder "strike"): proc_strike (2026-11-04)
STRIKE_BUILDERS = ("strike",)
# a WEAPON move (builder "fp_weapon" / "proc_blade"): proc_blade - the director -> gestures -> springs route (the
# governor's re-plan 2026-11-05: weapon moves had gone round the procedural engine through proc_strike's key poses)
BLADE_BUILDERS = ("fp_weapon", "proc_blade")
MANIFESTS = os.path.join("assets", "animations", "candidates")
CLIPS = os.path.join("build", "candidates")
POOL_GENOMES = 6  # settings in the pool per sheet slot (the build stops once anim_gallery.POOL x n are gate-clean)
# the EFFORTS MAPPING a new round uses, per builder (anim-range, 2026-11-09; a builder not named: its first mapping, 1).
# 1 = the first mapping: each effort moved a few keys a little - a round's gate-clean pool differed by 1-3 deg of joint
# rotation (kick, reactions), the owner's "cousins" (2026-11-04), and used little of its dossier's check ranges (most of
# the roundhouse's 2-28 %, none past 64 %). 2 = each effort moves the WHOLE body as far as the move's own dossier checks
# allow (measured one parameter at a time against every gate). A round records its mapping; a bred round keeps its
# parents' (the owner picked what that mapping made); emit rebuilds a pick with its round's mapping. Zero efforts are the
# dossier's own build under every mapping (mapping 1 kept its 0.06 s floor on a reaction's push length: a dossier
# asking for less, katana_hit_light's 0.05, builds 0.06 there - its shipped clips were made that way).
EFFORTS = {"proc_kick": 2, "proc_react": 2, "proc_blade": 2}


ARMS = ("technique", "habit:0:across", "habit:1:down_back", "habit:2:across", "habit:3:up")
# 'technique' = the dossier's own arm keys - since footage2026 MEASURED from real kicks (the lead arm's counter-swing
# at toe-off, the kick arm still low when the foot lands), not the hand-set clump round 0 showed. Every arm choice is
# held to the dossier's footage arm checks (lead_counter / kick_arm_out / kick_arm_low): a habit borrowed from other
# moves that contradicts the real move's arms fails. Only these two a PRIOR upper body is not held to (reported, never
# hidden): the Thai kick-side arm swung down-back and the guard hand at the face - loved R6 combat keeps both arms in play.
TECHNIQUE_ARM_CHECKS = ("arm_swing", "guard_up")
# the R6 VOCABULARY gate (owner 2026-10-16 round 1: 'the left leg doesnt just stay there... the arms awkward'): a limb
# frozen below the loved MINIMUM on both slide and turn fails; every measure under the loved p10 is a manifest WARNING
VOCAB_MEASURES = ("slide_p95", "slide_range", "rot_range")


def apply_arms(keys, arms, seed=0):
    if not arms or arms == "technique":
        return keys
    if arms.startswith("vocab") or arms.startswith("habit"):
        # the loved leg-strike arms (r6_vocab): 'vocab:<whip>' = the mean directions, 'habit:<h>:<whip>' = one of the
        # four ARM HABITS (k-means over loved clips' whole arm choreographies) + the kick-side arm's whip direction
        parts = arms.split(":")
        habit = int(parts[1]) if parts[0] == "habit" else None
        whip = parts[-1] if len(parts) > (2 if habit is not None else 1) else "down_back"
        for k in keys:
            k["arms"] = "vocab"
            k["arm_habit"] = habit
            k["whip_kick_arm"] = [whip, 45]
        return keys
    rank = int(arms.split(":")[1])
    for k in keys:
        k["prior"] = {"rank": rank, "tau": 0.25, "seed": seed}
    return keys


def apply_sliders(keys, s, v=1):
    """the base keys (carried, complete) -> a candidate's keys. Named phases the sliders act on: wind / wind_hold
    (anticipation), toe_off / contact / through / through_hold (the strike), recoil / land / settle (recovery).
    v: the efforts mapping (EFFORTS); 1 = the first one, kept exactly so its rounds and picks rebuild as they were"""
    if v >= 2:
        return apply_sliders_v2(keys, s)
    ks = copy.deepcopy(keys)
    by = {k["name"]: k for k in ks}
    t, w, sp = s["time"], s["weight"], s["space"]
    for n in ("wind", "wind_hold"):
        if n in by:
            by[n]["yaw"] -= 10 * w                                 # a deeper counter-turn
            by[n]["dip"] = max(0.0, by[n]["dip"] * (1 + 0.4 * w))
    for n in ("contact", "through", "through_hold"):
        if n in by:
            by[n]["lean"] *= 1 + 0.15 * w
            by[n]["kick"] = [by[n]["kick"][0] + 6 * w, by[n]["kick"][1]]
            fwd, across = by[n]["rear_arm"]
            by[n]["rear_arm"] = [fwd - 10 * w, across]              # the kicking-side arm flung further back
    for n, amt in (("contact", 4), ("through", 14), ("through_hold", 14)):
        if n in by:
            by[n]["yaw"] += amt * sp
    # timing: the strike window (wind_hold .. through_hold) and the recovery after it scale; keys stay ordered
    names = [k["name"] for k in ks]
    a = names.index("wind_hold") if "wind_hold" in names else 0
    z = names.index("through_hold") if "through_hold" in names else len(ks) - 1
    fs, fr = 1 - 0.18 * t, 1 - 0.12 * t
    old = [k["t"] for k in ks]
    new = old[:]
    for i in range(a + 1, len(ks)):
        f = fs if i <= z else fr
        new[i] = new[i - 1] + (old[i] - old[i - 1]) * f
    for k, tt in zip(ks, new):
        k["t"] = round(tt, 4)
    return ks


def apply_sliders_v2(keys, s):
    """EFFORTS 2 on a kick: each effort moves the WHOLE body, each part within the room the dossier's checks gave it
    when pushed alone (_scratch/anim-range/kick_lab.py, 2026-11-09: the kick's height passed -30..+15 deg, the lean
    +-10, the kick-side arm -40..+20, the landing turn +-20, the head +-30, the rise -0.07..+0.25 studs, the recovery
    -35..+60 % and the wind-up -30..+80 % of their time; the strike window's own timing failed the snap gates at +-25 %)
      weight  strong (+) / light (-): the kick higher (12 deg) with the lean deeper (5) - a head kick vs a body kick -,
              up on the ball of the foot (0.1 studs), the kick-side arm flung further back (24 deg), a deeper coil + dip
      space   indirect (+) / direct (-): the body carried round past the target into the landing (14 deg), the support
              foot turning further with the hips, the head turning with the body (+ only: direct keeps the eyes on the
              target), the arms opening wide (direct: tucked to the midline)
      time    sudden (+) / sustained (-): the wind-up (20 %) and the recovery (30 %) shorter / longer, the strike window
              itself 12 %
      flow    free (+) / bound (-): the springs looser (follow_of), the guard hand dropping (bound: held up), the head
              loose, a bigger counter-swing of the lead arm"""
    ks = copy.deepcopy(keys)
    by = {k["name"]: k for k in ks}
    t, w, sp, f = (float(s.get(k, 0.0)) for k in SLIDERS)
    for n in ("wind", "wind_hold"):
        if n in by:
            # a deeper counter-turn when strong only: a shallower one than the dossier's let the foot lead the hips
            # (light kicks failed hip_leads / snap_hips in 14 of 26 rejections, 2026-11-09)
            by[n]["yaw"] -= 10 * max(w, 0.0)
            by[n]["dip"] = max(0.0, by[n]["dip"] * (1 + 0.4 * w))
    for n in ("contact", "through", "through_hold"):
        if n in by:
            by[n]["kick"] = [by[n]["kick"][0] + 12 * w, by[n]["kick"][1]]
            by[n]["lean"] = by[n]["lean"] + 5 * w
            fwd, across = by[n]["rear_arm"]
            by[n]["rear_arm"] = [fwd - 24 * w, across - 20 * sp]
    for n in ("toe_off", "contact", "through", "through_hold", "recoil"):
        if n in by:
            by[n]["toe"] = max(0.0, by[n]["toe"] + 0.1 * w)
            if sp > 0 or f:
                hp, hy, hr = by[n].get("head", (0.0, 0.0, 0.0))
                by[n]["head"] = [hp, hy + 24 * max(sp, 0.0), hr + 8 * f]
    # (not at contact: the hips' turn there is the hips_over check's, which indirect + sudden pushed past 106 deg)
    for n, amt in (("through", 6), ("through_hold", 6), ("recoil", 14), ("land", 14)):
        if n in by:
            by[n]["yaw"] += amt * sp
    for n in ("contact", "through", "through_hold", "recoil"):
        if n in by:
            fwd, across = by[n]["lead_arm"]
            by[n]["lead_arm"] = [fwd - 10 * f, across - 30 * sp]
    for n in ("wind_hold", "toe_off"):
        if n in by:
            fwd, across = by[n]["lead_arm"]
            by[n]["lead_arm"] = [fwd + 15 * f, across]
    names = [k["name"] for k in ks]
    a = names.index("wind_hold") if "wind_hold" in names else 0
    z = names.index("through_hold") if "through_hold" in names else len(ks) - 1
    fw, fs, fr = 1 - 0.2 * t, 1 - 0.12 * t, 1 - 0.3 * t
    old = [k["t"] for k in ks]
    new = old[:]
    for i in range(1, len(ks)):
        new[i] = new[i - 1] + (old[i] - old[i - 1]) * (fw if i <= a else fs if i <= z else fr)
    for k, tt in zip(ks, new):
        k["t"] = round(tt, 4)
    return ks


def kick_dossier(d, s, v=1):
    """the dossier a kick candidate is built with: EFFORTS 2 also turns the support foot further with the hips when
    indirect (pivot_share +-0.08: the lab passed -0.1 .. +0.25; the pivot check floors at 60 deg)"""
    if v < 2 or not s.get("space"):
        return d
    share = float(np.clip(float(d["build"].get("pivot_share", 1.0)) + 0.08 * float(s["space"]), 0.3, 1.0))
    return {**d, "build": {**d["build"], "pivot_share": round(share, 3)}}


# INTENT, a first-class input (the owner, 2026-11-10, loving the roundhouse round 5: "there's aggressive, there's calm,
# there is proper, and from what I'm looking at, this is just a calm roundhouse kick"): kit/anim/intent.py reads a
# strike's intent from the loved R6 strikes' own tempo thirds (his calm round read calm on 20 of 20). A kick is AIMED at
# one by its strike window (toe_off -> through) x k and its hips already turned `lead` of the way to contact at toe-off
# (an aggressive kick is driven by the hips: compressing the window alone left the leg arriving before them); each
# intent samples the efforts that let it pass every gate. Lab 2026-11-10 (_scratch/anim-intent/kick_lab*.py, the
# roundhouse): x1.0 read calm (670-800 deg/s), x0.6 proper, x0.35-0.45 aggressive (2,080-3,550); the aggressive kicks
# passed hips-lead with a 0.3-0.5 lead and the physics snaps gate only strong + bound (24 of 30 loved aggressive clips
# pass that gate - the jerk was ours, not the gate's). Calm = the dossier's own measured fight pace, untouched.
INTENT_KICK = {"calm": None,
               "proper": {"k": (0.55, 0.65), "lead": (0.15, 0.3)},
               "aggressive": {"k": (0.35, 0.45), "lead": (0.3, 0.5)}}
INTENT_EFFORTS = {"calm": {},
                  "proper": {"flow": (-1.0, 0.0)},
                  "aggressive": {"weight": (0.4, 1.0), "flow": (-1.0, -0.4)}}
# a blade's own (lab 2026-11-11, the katana kesa): the shorter stroke (proc_blade.INTENT_BLADE) does the reading; strong,
# sudden and bound efforts on top pushed the arms past the loved katana's arm speed (2,460 deg/s) - moderate ones stay in it
INTENT_EFFORTS_BLADE = {"calm": {"time": (-1.0, 0.0), "flow": (-0.2, 0.6)},
                        "proper": {"flow": (-1.0, 0.0)},
                        "aggressive": {"time": (0.0, 0.6), "weight": (0.2, 0.8), "flow": (-0.8, -0.3)}}


def aim_intent(keys, intent, s):
    """a kick's keys aimed at `intent`: the strike window x k (sudden = the short end) and the hips' lead at toe-off;
    calm (or keys with no toe_off / contact / through) unchanged"""
    aim = INTENT_KICK.get(intent or "calm")
    names = [k["name"] for k in keys]
    if not aim or not all(x in names for x in ("toe_off", "contact", "through")):
        return keys
    ks = copy.deepcopy(keys)
    a, ci, z = names.index("toe_off"), names.index("contact"), names.index("through")
    u = (float(np.clip(s.get("time", 0.0), -1, 1)) + 1) / 2
    k = aim["k"][1] - u * (aim["k"][1] - aim["k"][0])
    lead = aim["lead"][0] + u * (aim["lead"][1] - aim["lead"][0])
    ks[a]["yaw"] = ks[a]["yaw"] + lead * (ks[ci]["yaw"] - ks[a]["yaw"])
    old = [x["t"] for x in ks]
    new = old[:]
    for i in range(1, len(ks)):
        new[i] = new[i - 1] + (old[i] - old[i - 1]) * (k if a < i <= z else 1.0)
    for x, tt in zip(ks, new):
        x["t"] = round(tt, 4)
    return ks


def intent_genome(s, intent, fresh=True, blade=False):
    """a genome's efforts in the intent's own ranges: a fresh setting (-1..1) mapped into the range, a bred one kept inside"""
    out = dict(s)
    for e, (lo, hi) in (INTENT_EFFORTS_BLADE if blade else INTENT_EFFORTS).get(intent or "calm", {}).items():
        v = float(out.get(e, 0.0))
        out[e] = round(lo + (v + 1) / 2 * (hi - lo), 2) if fresh else round(float(np.clip(v, lo, hi)), 2)
    return out


REACH_LADDER = (1.5, 2.0, 2.5)  # how far past the first mapping's +-1 an effort may reach (EFFORTS 2, probed per move)

def scaled(s, reach):
    """a candidate's efforts (-1..1: what the taste model, the sheet and the manifest see) -> the efforts its builder
    gets, each stretched by how far THIS move reaches on that side (reach {slider: [neg, pos]}); no reach = as they are"""
    out = dict(s)
    for k in SLIDERS:
        x = float(s.get(k) or 0.0)
        r = (reach or {}).get(k) or [1.0, 1.0]
        out[k] = round(x * float(r[1] if x > 0 else r[0]), 4)
    return out


def range_sources(d, kind):
    """the files a move's reach and lines hang on - their cache key (review 2026-11-09: the builder alone left out the
    engine, the gates and the calibrations a probe passes or fails by): every kit/anim module (builders, engine, gates,
    checks, this mapping), kit/direction.py (the dossier's direction checks), every calibration, and a blade's mapped
    gestures / a reaction's base idle"""
    import glob
    files = sorted(glob.glob(os.path.join(HERE, "*.py"))) + [os.path.join(os.path.dirname(HERE), "direction.py")]
    files += sorted(glob.glob(os.path.join("assets", "animations", "calibration", "*.json")))
    b = d.get("build") or {}
    if kind == "blade":
        files += [os.path.join(PB.GESTURES, f"{g}.json") for g in sorted(set((b.get("gestures") or {}).values()))]
    if kind == "react" and b.get("base"):
        files += [os.path.join("build", "animations", f"{b['base']}{x}.clip.json") for x in ("", ".r6")]
    return files


def cached(name, what, d, files, settings, compute):
    """a per-move measurement kept in <CLIPS>/<name>/<what>.json, recomputed when the dossier, any of `files`
    (range_sources) or `settings` changed"""
    import hashlib
    h = hashlib.sha256(json.dumps([d, settings], sort_keys=True, default=str).encode())
    for f in files:
        if f and os.path.isfile(f):
            with open(f, "rb") as fh:
                h.update(fh.read())
    key = h.hexdigest()[:16]
    path = os.path.join(CLIPS, name, f"{what}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            got = json.load(fh)
        if got.get("key") == key:
            return got[what]
    except (OSError, ValueError, KeyError):
        pass
    out = compute()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"key": key, what: out}, fh, indent=1)
    return out


def reach_of(name, d, probe, files=(), intent=None):
    """EFFORTS 2: how far each effort goes on THIS move - pushed alone from the dossier's own build up REACH_LADDER, the
    furthest step every gate passes (never under the first mapping's 1) -> {slider: [neg, pos]}. Measured 2026-11-09:
    the drill passed weight and flow at +-2.5 and a slower spin at 2.5x, the lunge cut nothing past 1 but a freer flow;
    the hook's hit turned +-50 deg (the ladder's top), the uppercut's 30 one way and 50 the other; the roundhouse a
    lighter kick to 1.5 and a bound one to 2.5. Cached per move by its range_sources (an intent - the probe built aimed
    at it - in its own cache: reach_<intent>.json)"""
    def compute():
        out = {}
        for k in SLIDERS:
            out[k] = []
            for sign in (-1.0, 1.0):
                best = 1.0
                for x in REACH_LADDER:
                    if not probe({**{kk: 0.0 for kk in SLIDERS}, k: sign * x}):
                        break
                    best = x
                out[k].append(best)
        return out
    return cached(name, f"reach_{intent}" if intent else "reach", d, files, list(REACH_LADDER) + ([intent] if intent else []),
                  compute)


# blade LINES (anim-range 2026-11-09): a weapon move's cut in another plane - the gesture's sword reach + blade turned
# together from the wind-up through the finish, about one axis of the frame each beat gives its sword in (the stage's;
# a `heading` / `torso` sword: the body's): roll (the forward axis: a flatter / steeper cut), tilt (the side axis:
# aimed higher / lower), yaw (the vertical: carried further across / held back). Each is
# probed on the move at zero efforts; the passing ones, up to LINES_MAX chosen farthest apart by the blade tip's path,
# are the round's lines (each its share of the sheet, like a keyed move's variants; the taste model learns them as a
# choice). Measured on the lunge cut: 5 of 12 lines passed its checks, and those 6 lines with one free arm and no
# effort already looked as varied (SigLIP look spread 0.036) as the whole efforts-and-arms sheet (0.041)
LINE_TRANSFORMS = (("roll", -30), ("roll", -15), ("roll", 15), ("roll", 30), ("tilt", -25), ("tilt", -12), ("tilt", 12),
                   ("tilt", 25), ("yaw", -25), ("yaw", -12), ("yaw", 12), ("yaw", 25))
LINE_AXES = {"roll": (0.0, 0.0, -1.0), "tilt": (1.0, 0.0, 0.0), "yaw": (0.0, 1.0, 0.0)}
LINES_MAX = 4


def line_gesture(g, line):
    """the gesture with the sword's line turned (`line` {"kind", "deg"}; none or 0 deg = the gesture itself)"""
    if not line or not line.get("deg"):
        return g
    g = copy.deepcopy(g)
    k = np.asarray(LINE_AXES[line["kind"]], float)
    a = math.radians(float(line["deg"]))
    on = False
    for b in g["beats"]:
        ph = b.get("phase")
        if ph in ("windup", "strike", "after") or isinstance(ph, list):
            on = True
        elif on and ph == "rest":                                  # the settle after the finish: the designed rest
            break
        if on and isinstance(b.get("sword"), dict):
            for f in ("reach", "blade"):
                if f in b["sword"]:
                    v = np.asarray(b["sword"][f], float)          # Rodrigues: v turned `deg` about k
                    v = v * math.cos(a) + np.cross(k, v) * math.sin(a) + k * float(k @ v) * (1 - math.cos(a))
                    b["sword"][f] = [round(float(x), 4) for x in v]
    g["name"] = f"{g['name']}__{line['kind']}{int(line['deg']):+d}"
    return g


def line_dossier(d, g0, line, folder):
    """the dossier building gesture `g0` on `line`: proc_blade reads a move's gesture from the path its build.gestures
    names under assets/animations/gestures - a line's own file is named by its path from there (no line: d itself)"""
    if not line or not line.get("deg"):
        return d
    g = line_gesture(g0, line)
    path = os.path.join(folder, f"{g['name']}.json")
    os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(g, fh, indent=1)
    try:
        ref = os.path.relpath(path[:-5], PB.GESTURES)
    except ValueError:                                             # another drive: os.path.join keeps an absolute path
        ref = os.path.abspath(path[:-5])
    return {**d, "build": {**d["build"], "gestures": {"*": ref}}}


def lines_of(name, d, rnd, rng, files):
    """the move's lines: the gesture as designed first, then every LINE_TRANSFORM that passes every gate at zero efforts
    (the first free-arm habit), up to LINES_MAX chosen farthest apart by the blade tip's path -> [{"kind", "deg"}]"""
    g0 = PB.gesture_for(d, f"{name}_r{rnd}_probe")
    folder = os.path.join(CLIPS, name, "lines")

    def compute():
        tips, out = [], []
        for kind, deg in ((None, 0),) + LINE_TRANSFORMS:
            line = {"kind": kind, "deg": deg}
            dl = line_dossier(d, g0, line, folder)
            c, b = PB.build(dl, {"arms": PB.HABITS[0]}, f"{name}_r{rnd}_probe", rng=rng)
            if not gate(c, dl, b, "technique")[0]:
                if not deg:
                    return [line]                                  # the design itself fails: no lines past it
                continue
            tip = np.asarray(c["sword"]["tip"], float)
            tips.append(tip[np.round(np.linspace(0, len(tip) - 1, 40)).astype(int)])
            out.append(line)
        chosen = [0]
        while len(chosen) < min(LINES_MAX, len(out)):
            far = max((i for i in range(len(out)) if i not in chosen),
                      key=lambda i: min(float(np.mean(np.linalg.norm(tips[i] - tips[j], axis=1))) for j in chosen))
            chosen.append(far)
        return [out[i] for i in chosen]
    return cached(name, "lines", d, files, [list(LINE_TRANSFORMS), LINES_MAX], compute)


def react_genome(d, s, v=1, reach=None):
    """the four efforts on a REACTION (a proc_react dossier) -> (hit, body, sim) overrides: weight = how HARD (the head
    and body pushes, +-20 / 30 %), time = how SUDDEN (the push's length, shorter when sudden), space = WHERE it lands
    (the hook's angle turned +-20 deg about the vertical: wider / tighter), flow = how FREELY the body turns with it
    (the root's give). Every candidate is still held to the dossier's ranges - the efforts only spread them.
    v=2 (EFFORTS 2): each effort reaches as far as this move's checks allow (`reach`, probed per move: reach_of), flow
    also loosens the joints (free: the tracking 30 % softer, the body goes with the blow; bound: stiffer - the lab
    passed +-40 %), and space turns the BODY's own push with the head's (v1 left a dossier's body line where it was)"""
    b = d["build"]
    h, bh, sm = b["hit"], b.get("body_hit") or {}, b.get("sim") or {}
    if v >= 2:
        s = scaled(s, reach)
    w, t, sp, fl = s["weight"], s["time"], s["space"], s["flow"]
    a = math.radians(20 * sp)
    x, y, z = h["dir"]
    hit = {"speed": round(h["speed"] * (1 + 0.2 * w), 2),
           "dur": round(min(0.18, max(0.06, h.get("dur", 0.12) * (1 - 0.3 * t))), 3),
           "dir": [round(x * math.cos(a) + z * math.sin(a), 3), y, round(-x * math.sin(a) + z * math.cos(a), 3)]}
    body = {"speed": round(bh["speed"] * (1 + 0.3 * w), 2)} if bh.get("speed") else None
    give = sm.get("root_rot_give", 0.4)
    # (the floor never sits above the dossier's own calibrated give: the katana reaction's 0.1 was clamped to 0.2)
    sim = {"root_rot_give": round(min(0.7, max(min(0.2, give), give + 0.2 * fl)), 2)}
    if v >= 2:
        # the push's length clamped around the dossier's OWN length (mapping 1's 0.06 - 0.18 s turned katana_hit_light's
        # 0.05 into 0.06 at zero efforts; kept there for the clips already made that way)
        dur = float(h.get("dur", 0.12))
        hit["dur"] = round(min(max(0.18, dur), max(min(0.06, dur), dur * (1 - 0.3 * t))), 3)
        hit["w_joint"] = round(float(h.get("w_joint", 14.0)) * max(0.4, 1 - 0.3 * fl), 2)
        if body is not None and bh.get("dir"):
            bx, by_, bz = bh["dir"]
            body["dir"] = [round(bx * math.cos(a) + bz * math.sin(a), 3), by_, round(-bx * math.sin(a) + bz * math.cos(a), 3)]
    return hit, body, sim


# the REACTION MATRIX (AAA gaps v2 C3): a spec's `from` turns the dossier's hit about the vertical to the side the blow
# comes from (the dossier's hit is from the FRONT: [-0.55, -0.15, 1] drives the body back, +Z) and `scale` sizes its
# impulse (light / heavy). The names follow src/kit/AnimLayers.reactionName: <base><Side><Tier>
FROM_YAW = {"Front": 0.0, "Back": 180.0, "Left": 90.0, "Right": -90.0}


def matrix_hit(hit, body, spec):
    a = math.radians(FROM_YAW.get(spec.get("from") or "Front", 0.0))
    k = float(spec.get("scale", 1.0))
    x, y, z = hit["dir"]
    hit = {**hit, "dir": [round(x * math.cos(a) + z * math.sin(a), 3), y, round(-x * math.sin(a) + z * math.cos(a), 3)],
           "speed": round(hit["speed"] * k, 2)}
    if body and body.get("speed"):
        body = {**body, "speed": round(body["speed"] * k, 2)}
    return hit, body


def follow_of(s, v=1):
    f = s["flow"]
    return {j: float(np.clip(v_ * (1 + (0.8 if v >= 2 else 0.6) * f), 0.05, 0.9)) for j, v_ in PK.FOLLOW.items()}


def genomes_round0(n, seed):
    """n genomes spread over the slider cube (a shuffled Latin hypercube) - candidates that DIFFER"""
    rs = np.random.default_rng(seed)
    cols = [rs.permutation((np.arange(n) + rs.uniform(0.2, 0.8, n)) / n) * 2 - 1 for _ in SLIDERS]
    return [{**{k: round(float(cols[i][j]), 2) for i, k in enumerate(SLIDERS)}, "arms": "technique"} for j in range(n)]


def genomes_bred(parents, n, seed, arms=ARMS):
    """children of the PICKED candidates only: their mean (or one of them) + a mutation of sigma 0.25"""
    rs = np.random.default_rng(seed)
    out = []
    for i in range(n):
        base = parents[(i // 2) % len(parents)]["sliders"] if i % 2 else {k: float(np.mean([p["sliders"][k] for p in parents])) for k in SLIDERS}
        child = {k: round(float(np.clip(base[k] + rs.normal(0, 0.25), -1, 1)), 2) for k in SLIDERS}
        child["arms"] = arms[i % len(arms)]                        # every upper-body choice on the sheet
        out.append(child)
    return out


def gate(c, d, b, arms="technique"):
    """-> (ok, the first failing number per gate family)"""
    import proc_physics as PH
    why = []
    skip = TECHNIQUE_ARM_CHECKS if arms and arms != "technique" else ()
    m = C.metrics(c, C.load_rig("r6"))
    why += [f"engine: {p[:80]}" for p in (m.get("problems") or [])]
    g = GT.check(c, "combat")
    why += [f"proc: {k}" for k, v in g.items() if isinstance(v, dict) and not v.get("pass", True)]
    warn = []
    if b.get("slides") == "weapon_vocab":
        # a weapon move against the loved WEAPON vocabulary (proc_blade.vocab_check): FAIL = a limb frozen below the
        # loved minimum on slide and swing; WARN = a number outside the loved p10-p90
        f, w, _ = PB.vocab_check(c)
        why += f
        warn += [f"vocab: {x}" for x in w]
    if b.get("slides") == "r6_vocab":
        # FAIL: a limb below the loved MINIMUM on both slide and turn (frozen; no loved clip can fail it - a p10 line on
        # any one measure failed 35 of the 72 loved clips it came from, review 2026-10-16). WARN: each measure under p10
        import json as _json
        import r6_vocab as RV
        cal = _json.load(open(RV.OUT, encoding="utf-8"))["roles"]
        m = RV.measures(c)
        for role in ("kick_leg", "support_leg", "Right Arm", "Left Arm"):
            if (m[role]["slide_p95"] < cal[role]["slide_p95"].get("min", 0) and m[role]["rot_range"] < cal[role]["rot_range"].get("min", 0)):
                why.append(f"vocab: {role} frozen (slide {m[role]['slide_p95']}, turn {m[role]['rot_range']} below the loved minimum)")
        warn += [f"{role} {mm} {v} < loved p10 {lo}" for role, mm, v, lo, _, _, where in RV.compare(c)
                 if mm in VOCAB_MEASURES and where == "below loved p10"]
    if c.get("sword") and b.get("slides") == "weapon_vocab":
        # the owner's NAMED faults (kit/anim/owner_faults.py, 2026-11-10): stilts, an arm-only cut, a flopping blade,
        # legs wrung round under a spin - each line drawn between a real clip he rejected for it and the ones he loved,
        # so no weapon move the generator designs (proc_blade) reaches him with one again, whatever its dossier
        # remembered to check. The strike route's candidates are the owner's OWN keyed blocks: never judged by it
        import owner_faults as OF
        why += [f"owner fault: {x['fault']} ({x['measure']} {x['value']} {'<' if x['side'] == 'below' else '>'} {x['limit']})"
                for x in OF.faults(c)]
    ds = DS.check(c, {**d, "build": b})
    why += [f"dossier: {k} {v['value']} outside {v['range']}" for k, v in ds["checks"].items() if not v["pass"] and k not in skip]
    # the checks a choice is not held to are REPORTED in the manifest, never silently dropped (review 2026-10-16)
    warn += [f"dossier (not held to with {arms} arms): {k} {v['value']} outside {v['range']}" for k, v in ds["checks"].items()
             if not v["pass"] and k in skip]
    try:
        ph = PH.check(c, "combat")
        if not ph["pass"]:
            why.append(f"physics: snaps {list(ph['snaps'])}" if ph["snaps"] else f"physics: balance {ph['balance_outside']}")
    except ImportError:
        pass                                                     # MuJoCo missing: the other gates still filter
    return not why, why, warn


def next_round(name):
    """the first round id with no manifest yet (a fresh round after a rejection goes there, never over a picked one)"""
    r = 0
    while os.path.isfile(os.path.join(MANIFESTS, name, f"round_{r}.json")):
        r += 1
    return r


def make(name, dossier, n=8, rnd=0, parents=(), seed=None, max_tries=None, fresh=False, change=None, overwrite=False,
         picked_by="owner", intent=None, blade_gesture=None):
    """fresh: a NEW round after the owner rejected the last one - no parents (never breed without a pick), the slider
    cube spread again, and `change` must say what is structurally different (mission 04-anim: a candidate set is a new
    round id with a stated change). intent: calm / proper / aggressive (kit/anim/intent.py) - a kick aimed at it
    (aim_intent), the efforts sampled in its ranges, and a candidate that READS as another intent refused"""
    if intent is not None and intent not in INTENT_KICK:
        raise SystemExit(f"--intent {intent}: one of {', '.join(INTENT_KICK)}")
    d = DS.require(dossier)                                       # no dossier, no candidates
    if blade_gesture:
        # the dossier's move made on the PROCEDURAL weapon route from a craft gesture (kit anim candidates --blade <g>,
        # 2026-11-11 - the kit home's katana): its own research and checks (measured as its builder measures them),
        # proc_blade the maker, the sword its move file's; candidates only - its game clip is untouched
        mf = d["build"].get("move_file")
        sw = d["build"].get("sword") or (json.load(open(mf, encoding="utf-8")).get("sword") if mf else None) or {}
        d = {**d, "build": {**d["build"], "gestures": {"*": blade_gesture}, "sword": sw}}
    strike = d["build"].get("builder") in STRIKE_BUILDERS and not blade_gesture
    blade = d["build"].get("builder") in BLADE_BUILDERS or bool(blade_gesture)
    builder = PST if strike else PB if blade else BUILDERS[d["build"].get("builder", "proc_kick")]
    react = d["build"].get("builder") == "proc_react"
    base = None if (react or strike or blade) else PK.carry(d["build"]["keys"])
    prev = []
    if fresh and not change:
        raise SystemExit("a fresh round needs --change '<what is structurally different from the rejected round>'")
    if not overwrite and os.path.isfile(os.path.join(MANIFESTS, name, f"round_{rnd}.json")):
        raise SystemExit(f"round {rnd} of {name} already exists (its picks and verdicts point at it) - "
                         f"a new round is --round {next_round(name)} with --parents <the owner's picks> (or --fresh "
                         f"--change '<what is different>' after a rejection); --overwrite only to rebuild it on purpose")
    eff, reach, lines = EFFORTS.get(builder.__name__, 1), None, None   # a new spread: the builder's newest mapping
    if rnd > 0 and not fresh:
        man = json.load(open(os.path.join(MANIFESTS, name, f"round_{rnd - 1}.json"), encoding="utf-8"))
        prev = [c for c in man["candidates"] if c["id"] in parents]
        if not prev:
            raise SystemExit(f"round {rnd}: none of {list(parents)} is a candidate of round {rnd - 1} - breed only from picks")
        # children of a pick: the mapping, reach and lines their parents were made by - the owner picked those motions
        eff, reach, lines = int(man.get("efforts", 1)), man.get("reach"), man.get("lines")
    seed = (zlib.crc32(name.encode()) % 10000 + 97 * rnd) if seed is None else seed
    rng = PK.slide_ranges()
    out_dir = os.path.join(CLIPS, name, f"round_{rnd}")
    os.makedirs(out_dir, exist_ok=True)
    kept, rejected, i = [], [], 0
    # the arm sources this move allows: the dossier may name them (build.arm_choices) when its evidence rules the rest
    # out - roundhouse: 0 of 19 habit-arm candidates passed the footage arm checks
    arms = ((None,) if react else ("technique",) if strike else PB.HABITS if blade
            else tuple(d["build"].get("arm_choices") or ARMS))   # (keyed blocks: their own arms; a blade: habit + whip)
    if eff >= 2 and reach is None and not strike:
        # how far each effort reaches on THIS move (EFFORTS 2): pushed alone up REACH_LADDER from the dossier's own
        # build, the furthest step every gate passes; cached per move by its sources (the mapping lives in this file)
        def probe(s):
            if blade:
                c, b = PB.build(d, {**s, "arms": PB.HABITS[0]}, f"{name}_r{rnd}_probe", rng=rng, **({"intent": intent} if intent else {}))
                return gate(c, d, b, "technique")[0]
            if react:
                c, b = PRX.build(d, *react_genome(d, s, eff), name=f"{name}_probe")
                return gate(c, d, b, "technique")[0]
            dk = kick_dossier(d, s, eff)
            c, b = builder.build(dk, keys=apply_arms(aim_intent(apply_sliders(base, s, eff), intent, s), arms[0], seed=0),
                                 follow=follow_of(s, eff), name=f"{name}_probe", rng=rng)
            return gate(c, dk, b, arms[0])[0]
        files = range_sources(d, "blade" if blade else "react" if react else "kick")
        # (an intent's reach is its own: an aggressive kick's room is not a calm one's - its own cache)
        reach = (reach_of(name, d, probe, files, intent) if intent not in (None, "calm")
                 else reach_of(name, d, probe, files))
        if blade and (rnd == 0 or fresh):
            lines = lines_of(name, d, rnd, rng, files)             # the cut in other planes (EFFORTS 2)
    lines = lines if lines and len(lines) > 1 else None        # one line = the gesture as designed: no lines
    g0 = PB.gesture_for(d, f"{name}_r{rnd}_probe") if blade else None
    # a pool to choose the sheet from (gallery tuning, 2026-11-08): POOL_GENOMES settings per slot, built until
    # AG.POOL x n are gate-clean
    pool = (genomes_round0(n * POOL_GENOMES, seed) if (rnd == 0 or fresh)
            else genomes_bred(prev, n * POOL_GENOMES, seed, arms))
    if intent and (blade or intent != "calm") and not (react or strike):   # (a kick's calm = its dossier's own pace)
        pool = [intent_genome(g, intent, fresh=(rnd == 0 or fresh), blade=blade) for g in pool]   # the intent's own effort ranges
    if fresh or (blade and rnd == 0):                          # every upper-body choice on the sheet
        for gi, g in enumerate(pool):
            g["arms"] = arms[gi % len(arms)]
    nv, cap = 1, n
    if strike:                                                 # a weapon move's VARIANTS (other lines / entries)
        nv = PST.variant_count(d, name)
        if nv > 1 and (rnd == 0 or fresh):
            # each line gets its share of the sheet (round 1 of the rebuild: 5 of 8 drills were one entry) and slider
            # sets enough to find it: 6 per candidate, a line's passes past its share kept as SPARES for any gap
            pool = genomes_round0(n * 6, seed)
            cap = -(-n // nv)
        for gi, g in enumerate(pool):
            g["variant"] = (gi % nv) if (rnd == 0 or fresh) else int(prev[(gi // 2) % len(prev)]["sliders"].get("variant", 0))
    elif blade and lines and len(lines) > 1:                   # a blade's LINES: each its share of the sheet
        nv = len(lines)
        if rnd == 0 or fresh:
            cap = -(-n // nv)
        for gi, g in enumerate(pool):
            # (stepped against the arm habits, so every habit meets every line)
            g["variant"] = ((gi + gi // len(arms)) % nv) if (rnd == 0 or fresh) else int(prev[(gi // 2) % len(prev)]["sliders"].get("variant", 0))
    # GALLERY TUNING (kit/anim/anim_gallery.py, research proposal 10): the owner's picks and rejections on this move's
    # earlier rounds are a taste model over the settings; with any, likely-good and informative settings are built
    # first. The sheet is then chosen from the gate-clean pool: likely beside learn (nothing learned yet: spread),
    # spaced apart by MOTION - the owner's "cousins" (2026-11-04: eight candidates too alike)
    # (only rounds of the same generator, efforts mapping, reach and lines: under another the same settings are other
    # motions - review 2026-11-09)
    model, ev = AG.model_for(name, MANIFESTS, parents=[p["id"] for p in prev], before=rnd, builder=builder.__name__,
                             picked_by=picked_by, efforts=eff, setup=AG.setup_of({"reach": reach, "lines": lines}))
    grouped = (strike or blade) and nv > 1 and cap < n         # a move's lines: each its share of the sheet
    props = AG.proposals(model, n, ("technique",) if strike else tuple(a for a in arms if a is not None), nv, seed)
    tries = [(p, True) for p in props] + [(g, False) for g in pool]
    passed, target = [], math.ceil(AG.POOL * n)
    for s, proposed in tries[: (max_tries or len(tries))]:
        cid = f"{name}/r{rnd}/c{i}"
        i += 1
        if react:                                              # a reaction: the efforts move the hit's physics
            hit, body, sim = react_genome(d, s, eff, reach)
            c, b = builder.build(d, hit=hit, body=body, sim=sim, name=f"{name}_r{rnd}_c{i - 1}")
            ok, why, warn = gate(c, d, b, "technique")
        elif blade:                                            # a weapon move: the gesture's beats through the efforts
            # (EFFORTS 2: each effort stretched as far as this move reaches - the manifest keeps the -1..1 settings -
            # and the cut on its line)
            dl = line_dossier(d, g0, (lines or [{}])[int(s.get("variant", 0)) % len(lines or [{}])],
                              os.path.join(CLIPS, name, "lines"))
            c, b = PB.build(dl, scaled(s, reach) if eff >= 2 else s, f"{name}_r{rnd}_c{i - 1}", rng=rng,
                            **({"intent": intent} if intent else {}))   # (no intent: the call it always was)
            ok, why, warn = gate(c, dl, b, "technique")
        elif strike:                                           # keyed blocks: their own keys, the efforts on them
            s["arms"] = "technique"
            c, b = PST.build(d, s, name=f"{name}_r{rnd}_c{i - 1}")
            ok, why, warn = gate(c, d, b, "technique")
        else:
            ss = scaled(s, reach) if eff >= 2 else s           # (EFFORTS 2: as far as this move reaches)
            keys = apply_arms(aim_intent(apply_sliders(base, ss, eff), intent, ss), s.get("arms"), seed=i)
            dk = kick_dossier(d, ss, eff)
            c, b = builder.build(dk, keys=keys, follow=follow_of(ss, eff), name=f"{name}_r{rnd}_c{i - 1}", rng=rng)
            ok, why, warn = gate(c, dk, b, s.get("arms"))
        lineage = [f"dossier:{dossier}"] + [p["id"] for p in prev]
        read = None
        if ok and intent:
            # the INTENT gate: a candidate that reads as another intent is not this round's (it would be the wrong move)
            import intent as INT
            read = INT.read(c)
            if read["intent"] != intent:
                ok, why = False, [f"intent: reads {read['intent']} ({read.get('tempo_deg_s')} deg/s), asked {intent}"]
        if not ok:
            rejected.append({"id": cid, "sliders": s, "why": why[:3]})
            continue
        path = os.path.join(out_dir, f"c{i - 1}.clip.json")
        c["candidate"] = {"id": cid, "sliders": s, "lineage": lineage}
        json.dump(c, open(path, "w", encoding="utf-8"))
        row = {"id": cid, "sliders": s, "lineage": lineage, "clip": path.replace(os.sep, "/"),
               "hit_t": next((e["t"] for e in c["events"] if e.get("name") == "Hit"), c["events"][0]["t"] if c["events"] else None), "seconds": round(c["times"][-1], 2), "warnings": warn,
               **({"intent_read": {k: read.get(k) for k in ("intent", "tempo_deg_s", "snap_frames", "amp_deg")}} if read else {})}
        passed.append({**row, "proposed": proposed, "sig": AG.signature(c)})
        # enough to choose from - and with lines, until each line has its share (or the pool runs out): a line that
        # rarely passes the gates still gets its place on the sheet (review 2026-11-08)
        if len(passed) >= target and (not grouped or all(
                sum(1 for p in passed if p["sliders"].get("variant", 0) == v) >= cap for v in range(nv))):
            break
    kept, report = AG.sheet(passed, n, model if model.evidence() else None,
                            (lambda r: r["sliders"].get("variant", 0)) if grouped else None, cap if grouped else None,
                            ev["counts"])
    kept = [{**{k: v for k, v in r.items() if k not in ("sig", "proposed")}, "gallery": {**r["gallery"], "proposed": r["proposed"]}}
            for r in kept]
    man = {"schema": 1, "name": name, "dossier": dossier, "round": rnd, "seed": seed, "builder": builder.__name__,
           "efforts": eff, **({"reach": reach} if reach else {}), **({"lines": lines} if lines and len(lines) > 1 else {}),
           **({"intent": intent} if intent else {}), **({"gesture": blade_gesture} if blade_gesture else {}),
           "change": change if fresh else "round 0: the dossier's keys spread over the four effort sliders" if rnd == 0
           else f"bred from the owner's picks {list(parents)} (their sliders + sigma 0.25); the UPPER BODY now a choice: the dossier's Thai technique arms or a mode of the combat pose prior (loved R6 combat poses as a density) - owner round {rnd - 1}: 'correct but not a nice animation' (the poses)",
           "parents": list(parents), **({"picked_by": picked_by} if parents else {}), "candidates": kept, "rejected": rejected,
           "gallery": {**report, "evidence": ev["counts"], "unshown": len(passed) - len(kept)}}
    os.makedirs(os.path.join(MANIFESTS, name), exist_ok=True)
    json.dump(man, open(os.path.join(MANIFESTS, name, f"round_{rnd}.json"), "w", encoding="utf-8", newline=""), indent=1)
    return man


def round_of(spec):
    """the manifest of the round a spec's `from_candidate` came from (None: no candidate named); a named one that is
    missing stops the build - its sliders' mapping would be a guess"""
    cand = spec.get("from_candidate")
    if not cand:
        return None
    move, _, rest = str(cand).partition("/r")
    path = os.path.join(MANIFESTS, move, f"round_{rest.split('/')[0]}.json")
    if not os.path.isfile(path):
        raise SystemExit(f"emit: {cand} names no round manifest ({path}) - its sliders' mapping is unknown; "
                         "add 'efforts' (and 'reach', 'line') to the spec from the round it was picked in")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def pick_setup(spec, strike=False):
    """-> (sliders, efforts mapping, reach, blade line, arms) a game clip's spec builds with - a pick rebuilt as the
    owner saw it (review 2026-11-09: never a guessed mapping, reach or line):
      - a spec naming its candidate (`from_candidate`): that round's mapping, reach and lines (the spec's own 'efforts' /
        'reach' / 'line' win where given); the spec's efforts must be the candidate's, its variant and arms taken from
        the candidate where the spec has none - a spec with other settings is not that pick: refused
      - no candidate named: zero efforts = the dossier's own build (every mapping); other efforts need the spec's own
        'efforts' (and 'reach' / 'line' where they apply)
      - a keyed-strike spec: as it is (that builder has one mapping)"""
    raw = spec.get("sliders") or {}
    s = {**{k: 0.0 for k in SLIDERS}, **raw}
    arms = spec.get("arms")
    if strike:
        return s, 1, None, None, arms
    man = round_of(spec)                                       # (a named round that is gone: refused there)
    if man is None:
        moved = [k for k in SLIDERS if abs(float(s.get(k) or 0.0)) > 1e-9]
        if moved and not spec.get("efforts"):
            raise SystemExit(f"emit: {spec.get('name')} sets efforts {moved} but names no candidate - add 'from_candidate' "
                             "(the pick) or 'efforts' (the mapping those numbers mean)")
        return s, int(spec.get("efforts") or 1), spec.get("reach"), spec.get("line"), arms
    cand = next((c for c in man.get("candidates") or [] if c.get("id") == spec["from_candidate"]), None)
    if cand is None:
        raise SystemExit(f"emit: {spec['from_candidate']} is not a candidate of its round's manifest")
    cs = cand.get("sliders") or {}
    if "variant" not in raw and "variant" in cs:
        s["variant"] = cs["variant"]
    if arms is None:
        arms = cs.get("arms")
    off = [k for k in SLIDERS if abs(float(s.get(k) or 0.0) - float(cs.get(k) or 0.0)) > 1e-6]
    off += [k for k, a, b in (("variant", s.get("variant", 0), cs.get("variant", 0)), ("arms", arms, cs.get("arms")))
            if (a or 0) != (b or 0)]
    if off:
        raise SystemExit(f"emit: the spec's {off} are not {spec['from_candidate']}'s - copy the candidate's settings, or "
                         "drop from_candidate and give 'efforts' for settings of your own")
    lines = man.get("lines") or []
    line = spec.get("line") or (lines[int(s.get("variant", 0) or 0) % len(lines)] if lines else None)
    reach = spec["reach"] if spec.get("reach") is not None else man.get("reach")
    return s, int(spec.get("efforts") or man.get("efforts", 1)), reach, line, arms


def emit(spec_path, out):
    """<Name>.dossier.json ({"name", "dossier", "sliders": {time, weight, space, flow}, "arms", "from_candidate"}) ->
    the GAME clip, rebuilt from tracked data by `kit anim` (a candidate's clip lives in git-ignored build/; this is how
    one becomes an animation the game plays - the same builder and the same efforts mapping as `kit anim candidates`:
    pick_setup finds the mapping, reach and line the candidate's round used)"""
    import strike as S
    spec = json.load(open(spec_path, encoding="utf-8"))
    d = DS.require(spec["dossier"])
    s, eff, reach, ln, arms = pick_setup(spec, strike=d["build"].get("builder") in STRIKE_BUILDERS)
    if d["build"].get("builder") == "proc_react":
        hit, body, sim = react_genome(d, s, eff, reach)
        if spec.get("from") or spec.get("scale"):
            hit, body = matrix_hit(hit, body or ({"speed": d["build"]["body_hit"]["speed"]} if d["build"].get("body_hit") else None), spec)
        if isinstance(spec.get("hit"), dict):              # a side's own tuning (e.g. its spin), on top of the matrix
            hit = {**hit, **spec["hit"]}
        c, b = PRX.build(d, hit=hit, body=body, sim=sim, name=spec["name"])
    elif d["build"].get("builder") in BLADE_BUILDERS:
        # (a pick cut on one of its round's lines: that line)
        dl = line_dossier(d, PB.gesture_for(d, spec["name"]), ln, os.path.join(CLIPS, spec["name"], "lines"))
        c, b = PB.build(dl, {**(scaled(s, reach) if eff >= 2 else s), "arms": arms}, spec["name"])
        if ln and ln.get("deg"):
            c["line"] = ln
        d = dl
    elif d["build"].get("builder") in STRIKE_BUILDERS:
        c, b = PST.build(d, s, name=spec.get("base") or spec["name"])
    else:
        ss = scaled(s, reach) if eff >= 2 else s
        keys = apply_arms(apply_sliders(PK.carry(d["build"]["keys"]), ss, eff), arms, seed=0)
        dk = kick_dossier(d, ss, eff)
        c, b = PK.build(dk, keys=keys, follow=follow_of(ss, eff), name=spec["name"], rng=PK.slide_ranges())
    c["name"] = spec["name"]
    c["duration"] = float(c["times"][-1])                     # its OWN length (a reaction's base idle carried 2.8 s)
    c["source"] = {"kind": "dossier", "file": spec_path, "dossier": spec["dossier"], "sliders": s,
                   "efforts": eff, **({"reach": reach} if reach else {}),
                   "from": spec.get("from"), "scale": spec.get("scale"), "hit": spec.get("hit"),
                   "from_candidate": spec.get("from_candidate"), "sha256": S.sha256_of(spec_path),
                   "tool_sha256": S.sha256_of_many([__file__, C.__file__]), "rig_sha256": S.sha256_of(C.rig_path("r6"))}
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    json.dump(c, open(out, "w", encoding="utf-8"))
    r = DS.check(c, {**d, "build": b})
    fails = [k for k, v in r["checks"].items() if not v["pass"]]
    print(json.dumps({"schema": 1, "status": "pass" if not fails else "fail",
                      "summary": f"{spec['name']}: built from the dossier {spec['dossier']} "
                                 + ("(every check passes)" if not fails else f"- dossier fails {fails}"),
                      "next_action": "none - proceed" if not fails else f"python kit/anim/dossier_verify.py {out} --dossier {spec['dossier']}"}))
    return not fails


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if a[:1] == ["emit"]:
        sys.exit(0 if emit(a[1], a[a.index("--out") + 1]) else 6)
    name = a[0]
    opt = lambda k, dv: a[a.index(k) + 1] if k in a else dv  # noqa: E731
    fresh = "--fresh" in a                                    # a fresh round with no --round: the next free one
    rnd = int(opt("--round", next_round(name) if fresh else 0))
    man = make(name, opt("--dossier", None) or DS.snake(name), n=int(opt("--n", 8)), rnd=rnd,
               parents=[p for p in opt("--parents", "").split(",") if p], fresh=fresh, change=opt("--change", None),
               overwrite="--overwrite" in a, picked_by=opt("--by", "owner"), intent=opt("--intent", None),
               blade_gesture=opt("--blade", None))
    k, r = len(man["candidates"]), len(man["rejected"])
    import proc_calib as PCAL
    dd = DS.require(man["dossier"])
    cov, _ = PCAL.coverage(dd.get("category", "combat"), dd["build"].get("kind"))
    gal = man["gallery"]
    roles = ", ".join(f"{v} {kk}" for kk, v in sorted(gal["roles"].items()))
    spaced = (f"spaced by {gal['measure']}: closest pair {gal['sheet'][0]} vs {gal['first_built'][0]} for the first {k} built"
              if gal["sheet"][0] is not None and gal["first_built"][0] is not None else f"spaced by {gal['measure']}")
    print(json.dumps({"schema": 1, "status": "pass" if k >= 4 else "fail",
                      "summary": f"{name} round {man['round']}: {k} gate-clean candidate(s), {r} rejected by the gates | {cov}"
                                 + f" | gallery: {roles} chosen from {gal['pool']} gate-clean, {spaced}; {gal['model']}",
                      "next_action": (f"look at them: lune run kit anim picks {name} --round {man['round']}" if k >= 4
                                      else f"fewer than 4 passed - read the rejections in {MANIFESTS}/{name}/round_{man['round']}.json"),
                      # the line this build ends with (kit/cmd/anim.luau prints it last - the studio route's A0): the
                      # round's clips are not pictures yet, so it names the two commands that make them
                      "look": (f"LOOK: {CLIPS}/{name}/round_{man['round']}/ - {k} candidate clip(s), NOT rendered yet: "
                               f"lune run kit anim picks {name} --round {man['round']} (each as a real-time gif on the "
                               f"owner's rig, the pick sheet); one candidate's key poses large, beside the dossier's "
                               f"reference frames: lune run kit anim sheet {name} --clip {CLIPS}/{name}/round_"
                               f"{man['round']}/<id>.clip.json --dossier {man['dossier']}").replace(os.sep, "/"),
                      "rejected_why": [x["why"][0] for x in man["rejected"][:5]]}))
    sys.exit(0 if k >= 4 else 1)
