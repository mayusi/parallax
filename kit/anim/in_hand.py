"""in_hand.py — THE WEAPON IN A HAND AT EVERY FRAME (the owner's method lists 2026-11-13, rigging: attachment bones and
sockets - "a check that the hand sits on the hilt"; the audit: board/plans/archive/2026-11-13-anim-methods-audit.md). In the
game the weapon rides the right arm on its own joint ("Handle"), so a clip whose designed weapon path leaves the hand
is exported with the weapon floating off it. This reads a built clip: at every frame the nearer hand's distance to
the WEAPON'S LINE (from 0.9 studs behind its grip point to its tip - a hand on the hilt, or along the blade as in a
half-sword block, is holding it), the root's travel carried.

    python kit/anim/in_hand.py <clip.json> [--before <list.json>]
    python kit/anim/in_hand.py freeze <built clips' folder> --out <list.json>

A weapon out of both hands is MEANT when the clip says so with its own events: it is free from an event whose name
says it leaves (Toss, Throw, Pass, Release, Drop, Sheathe, Holster, OnBack, Vanish - the WHOLE name, a weapon's name
may lead it: SwordToss) to the one that says it is back (Catch, Caught, Out, Draw, Appear; two tosses need two
catches; another weapon's event closes nothing) or to the clip's end, and from the clip's start to its last "back"
event when those come before anything leaves (a draw). Outside those windows a frame with the weapon more than LOOSE studs
from both hands FAILS, named with its frame and how far.

WHICH HAND (the owner's limitations list 2026-11-15, A-R08 / AN-13: "specialized grip solves need a general prop
contract ... handedness, two-hand reach"): a move or a clip may say which hands hold it -
    "hands": "two"      BOTH hands on the weapon at every frame (a greatsword, a katana, a staff, a rifle)
    "hands": "right"    the right hand holds it; the left is free          "hands": "left"   the other way round
(NOT "grip": a clip's "grip" is already the weapon's own joint track, written by kit/anim/grip.py.)
Said, it is HELD TO: the frame at which a hand the grip names is off the weapon fails, named with the hand. Unsaid,
the weapon is held by whichever hand is nearer, as before. The reading always says which hands were on it.
Measured 2026-11-15: on the seven loved two-handed cuts both hands read 0.00 studs at every frame; on two of the
three rejected cuts the left hand is 4.0 and 4.2 studs off (one-handed moves): said "two", they fail.

ON THE HILT, OR SAID TO BE ON THE BLADE (the owner's V3 list, anim stage C.2): a hand that holds the weapon holds its
HILT - from BEHIND studs behind the grip point to HILT_AHEAD ahead of it. A holding hand further up the line is ON
THE BLADE: a half-sword grip, a hand swap - or a weapon slid along its own axis through the fist, or flipped end for
end (its grip point is then at the far end): only what the clip SAYS is let through -
    "on_blade": {"right": [[from_s, to_s], ...] | true, "left": ...}      (a move's is carried into its clip)
Measured 2026-11-18 on the 352 built weapon clips (read only): every holding hand sat from 0.92 behind the grip
point to 0.66 ahead of it, but in 14 clips - the twelve SwordBlock half-sword blocks and SwordToRightHand (the right
hand 2.5 up the blade), GSCraftBlock (the left 1.78 up): those 14 are the clips made before this rule
(<anims>/blocks/_on_blade_before.json, frozen once by `freeze-blade`).
KNOWN LIMITS (card r66z): a weapon slid along its axis WITHIN its hilt reads as held; one weapon track is read (a
second gun of a pair is not).

Measured 2026-11-14 on the weapon clips built here (read only): a held weapon reads 0.00 studs; the tosses, passes,
draws and swaps declare themselves with those events. What still fails is listed in the frozen list (--before,
written once by `freeze`): clips made before the rule are said, never failed; the list is never extended."""
import datetime
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

BEFORE = "_weapon_loose_before.json"     # <anims>/blocks/: the clips made before the rule (frozen once)
GRIPS = ("two", "right", "left")


def hands_of(clip):
    """the hands the clip says hold its weapon ("hands": "two" | "right" | "left"), or None; ValueError on anything else"""
    said = clip.get("hands")
    # (the COUNT form the kit's own `kit anim rearm --hands` writes, and 21 clips carry: kit/anim/rearm.py puts the hilt
    #  in the right hand and solves a second hand onto it when 2 - so 1 is the right hand, 2 both. The committed-tree
    #  proof stopped on it 2026-11-19 once the Sample Game clip ahead of it was quarantined: ClaymoreComboBw "hands": 1)
    if isinstance(said, int) and not isinstance(said, bool) and said in (1, 2):
        said = "right" if said == 1 else "two"
    if said is not None and said not in GRIPS:
        raise ValueError(f"its \"hands\" is {said!r} - it is \"two\", \"right\" or \"left\" (or it is left out)")
    return said


LOOSE = 0.1          # studs from the nearer hand to the weapon's line for it to be out of the hand. Measured on the
#                      309 built weapon clips that declare no toss: 301 read under 0.05 (a held weapon reads 0.00),
#                      the next one 0.26 - the bar sits in that gap
BEHIND = 0.9         # studs of the weapon's line behind its grip point (the pommel end of a two-handed hilt)
HILT_AHEAD = 0.75    # studs of the line AHEAD of the grip point that are still the hilt (measured: 0.66 the furthest a
#                      holding hand sat on 338 built clips; the next, a half-sword block's hand, 1.78)
BLADE_BEFORE = "_on_blade_before.json"   # <anims>/blocks/: the clips with a hand up the blade made before that rule
# an event says the weapon leaves or is back by its WHOLE name (a weapon's name may lead it: SwordToss, GunsOut);
# a name that only contains such a word (Shout, Bypass, CoinToss, MagOut) says nothing about the weapon
WHOSE = r"(Sword|Blade|Katana|Gun|Guns|Pistol|Pistols|Weapon)?"
LEAVES = re.compile(r"^" + WHOSE + r"(Toss|Throw|Thrown|Pass|Release|Drop|Sheathe|Sheathed|Holster|Holstered|OnBack|Vanish)$")
BACK = re.compile(r"^" + WHOSE + r"(Catch|Caught|Out|Draw|Drawn|Appear)$")


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def windows(clip, n, fps):
    """the frames the clip itself says the weapon is out of the hands -> [[first, last]]. Events inside the clip only.
    A draw: when the first weapon event says "back", the weapon is free from frame 0 to the LAST "back" event before
    anything leaves. After that every "leaves" opens (two tosses need two catches) and a "back" closes one - but only
    a "back" of the same weapon, or one that names none (SwordOnBack is not closed by GunsOut). What is still open at
    the end stays open to the end (thrown, stowed)"""
    last = (n - 1) / fps
    marks = []
    for e in clip.get("events") or []:
        if not isinstance(e, dict) or isinstance(e.get("t"), bool) or not isinstance(e.get("t"), (int, float)):
            continue
        name, t = str(e.get("name") or ""), float(e["t"])
        if t < -0.5 / fps or t > last + 0.5 / fps:           # (an event outside the clip declares nothing in it)
            continue
        for what, rx in (("leaves", LEAVES), ("back", BACK)):
            m = rx.match(name)
            if m:
                marks.append((min(n - 1, max(0, int(round(t * fps)))), what, m.group(1) or ""))
    marks.sort(key=lambda x: x[0])
    out, k = [], 0
    if marks and marks[0][1] == "back":
        while k < len(marks) and marks[k][1] == "back":
            k += 1
        out.append([0, marks[k - 1][0]])
    opened = []                                              # [(frame, whose)] still out of the hands
    start = None
    for f, what, whose in marks[k:]:
        if what == "leaves":
            if not opened:
                start = f
            opened.append(whose)
        elif opened:
            same = [i for i, w in enumerate(opened) if w == whose or not w or not whose]
            if same:
                opened.pop(same[-1])
                if not opened:
                    out.append([start, f])
                    start = None
    if opened:
        out.append([start, n - 1])
    return out


def on_blade_said(clip, n, fps):
    """{hand: bool per frame} where the clip says that hand may be ON THE BLADE ("on_blade"); ValueError on a shape
    that is not one"""
    said = clip.get("on_blade")
    out = {h: np.zeros(n, bool) for h in ("RightHand", "LeftHand")}
    if said is None:
        return out
    if not isinstance(said, dict) or any(k not in ("right", "left") for k in said):
        raise ValueError('"on_blade" is {"right": [[from, to], ...] | true, "left": ...} (seconds)')
    for k, v in said.items():
        hand = "RightHand" if k == "right" else "LeftHand"
        if v is True:
            out[hand][:] = True
            continue
        if not isinstance(v, list) or any(not isinstance(w, (list, tuple)) or len(w) != 2
                                          or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in w) for w in v):
            raise ValueError(f'"on_blade".{k} is true or a list of [from, to] in seconds')
        for a, b in v:
            out[hand][max(0, int(round(float(a) * fps))):min(n, int(round(float(b) * fps)) + 1)] = True
    return out


def read(clip):
    """-> {weapon, frames, fps, free: [per frame, studs from the nearer hand], windows, loose: [[first, last, worst
    studs, its frame]], worst}. weapon False = the clip carries none (nothing to hold)"""
    import clip as C
    import pose_sheet as PS
    if clip.get("rig") not in (None, "R6"):
        raise ValueError(f"it is a {clip.get('rig')} clip - the weapon is read on the R6 clip")
    rig = C.load_rig("r6")
    W = C.world_frames(clip, rig)
    p = PS.paths(clip, W)
    fps = float(clip.get("fps") or 30)
    n = len(W)
    track = clip.get("sword") if isinstance(clip.get("sword"), dict) else {}
    for k in ("tip", "grip_path"):
        if isinstance(track.get(k), list) and track[k] and len(track[k]) != n:
            raise ValueError(f"the weapon's {k} track has {len(track[k])} frame(s) and the clip {n}")
    if "Grip" not in p:
        return {"weapon": False, "frames": n, "fps": fps, "free": [], "windows": [], "loose": [], "worst": 0.0}
    sw = clip.get("sword") or {}
    short = [k for k in ("tip", "grip_path") if isinstance(sw.get(k), list) and len(sw[k]) != n]
    if short:                                                # (a retimed clip whose weapon track was left behind)
        raise ValueError(f"the weapon's {short[0]} track has {len(sw[short[0]])} frame(s) and the clip {n}")
    g, t = p["Grip"], p["BladeTip"]
    length = np.linalg.norm(t - g, axis=1)
    ax = (t - g) / np.maximum(length[:, None], 1e-9)
    grip = hands_of(clip)
    each, place = {}, {}
    for hand in ("RightHand", "LeftHand"):
        h = p[hand]
        place[hand] = np.einsum("ij,ij->i", h - g, ax)
        along = np.clip(place[hand], -BEHIND, length)
        each[hand] = np.linalg.norm(h - (g + along[:, None] * ax), axis=1)
    # the distance the grip is held to: both hands (the further one), the hand it names, or - unsaid - the nearer
    near = (np.maximum(each["RightHand"], each["LeftHand"]) if grip == "two" else each["RightHand"] if grip == "right"
            else each["LeftHand"] if grip == "left" else np.minimum(each["RightHand"], each["LeftHand"]))
    win = windows(clip, n, fps)
    meant = np.zeros(n, bool)
    for a, b in win:
        meant[a:b + 1] = True
    out_of = (near > LOOSE) & ~meant
    loose, i = [], 0
    while i < n:
        if out_of[i]:
            j = i
            while j + 1 < n and out_of[j + 1]:
                j += 1
            k = i + int(np.argmax(near[i:j + 1]))
            loose.append([i, j, round(float(near[k]), 2), k])
            i = j + 1
        else:
            i += 1
    on = {hand: int((d <= LOOSE).sum()) for hand, d in each.items()}       # (frames truly on it: a toss is not contact)
    # a holding hand past the hilt, where the clip does not say it may be: [[first, last, studs up the line, frame, hand]]
    said_blade = on_blade_said(clip, n, fps)
    blade = []
    for hand in ("RightHand", "LeftHand"):
        up = (each[hand] <= LOOSE) & ~meant & (place[hand] > HILT_AHEAD) & ~said_blade[hand]
        i = 0
        while i < n:
            if up[i]:
                j = i
                while j + 1 < n and up[j + 1]:
                    j += 1
                k = i + int(np.argmax(place[hand][i:j + 1]))
                blade.append([i, j, round(float(place[hand][k]), 2), k, {"RightHand": "right", "LeftHand": "left"}[hand]])
                i = j + 1
            else:
                i += 1
    # the hand a failure names: the one the clip says holds it; for "two" (or unsaid) the hand further off at the worst
    # frame of the worst stretch
    if grip in ("right", "left"):
        far = "RightHand" if grip == "right" else "LeftHand"
    else:
        k = max(loose, key=lambda x: x[2])[3] if loose else int(np.argmax(near))
        far = max(each, key=lambda hand: float(each[hand][k]))
    return {"weapon": True, "frames": n, "fps": fps, "free": [round(float(x), 3) for x in near], "windows": win,
            "loose": loose, "worst": round(float(near[~meant].max()) if (~meant).any() else 0.0, 2),
            "grip": grip, "on": {"right": on["RightHand"], "left": on["LeftHand"]}, "blade": blade,
            "off_hand": {"RightHand": "right", "LeftHand": "left"}[far]}


def blade_words(r, name):
    """the hand found up the blade, in a line ('' when none)"""
    if not r.get("blade"):
        return ""
    a, b, up, k, hand = max(r["blade"], key=lambda x: x[2])
    return (f"the {hand} hand of {name} holds the weapon {up} studs up its line at frame {k} ({k / r['fps']:.2f} s; frames "
            f"{a}-{b}) - past the hilt (it ends {HILT_AHEAD:g} ahead of the grip point): a weapon slid through the fist or "
            "turned end for end, or a half-sword grip the clip does not say (\"on_blade\")")


def words(r, name):
    if not r["weapon"]:
        return f"{name} carries no weapon: nothing to hold"
    said = (f" (out of the hands by its own events for {len(r['windows'])} stretch(es): frames "
            + ", ".join(f"{a}-{b}" for a, b in r["windows"]) + ")") if r["windows"] else ""
    if not r["loose"]:
        return f"the weapon is in a hand at every frame of {name}{said}"
    a, b, far, k = max(r["loose"], key=lambda x: x[2])
    frames = sum(y - x + 1 for x, y, _, _ in r["loose"])
    if r.get("grip"):
        which = "both hands" if r["grip"] == "two" else f"the {r['grip']} hand"
        return (f"{name} says its hands are \"{r['grip']}\" and {which} {'are' if r['grip'] == 'two' else 'is'} not on the weapon "
                f"for {frames} frame(s) with no toss or draw declared: the {r['off_hand']} hand is {far} studs off at frame {k} "
                f"({k / r['fps']:.2f} s; frames {a}-{b}"
                + (f", +{len(r['loose']) - 1} more stretch(es)" if len(r["loose"]) > 1 else "") + f"){said}")
    return (f"the weapon is in NO hand for {frames} frame(s) of {name} with no toss or draw declared: {far} studs from the "
            f"nearer hand at frame {k} ({k / r['fps']:.2f} s; frames {a}-{b}"
            + (f", +{len(r['loose']) - 1} more stretch(es)" if len(r["loose"]) > 1 else "") + f"){said}")


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


def freeze_blade(folder, out, today=None):
    """the built clips with a holding hand up the blade today -> the on-the-hilt rule's frozen list (refused when it
    exists)"""
    if os.path.exists(out):
        raise ValueError(f"{out.replace(os.sep, '/')} exists: the list is frozen once and never extended")
    names = []
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".clip.json"):
            continue
        stem = f[:-len(".clip.json")]
        if stem.endswith(".r6"):
            stem = stem[:-3]
        if "." in stem:
            continue
        try:
            with open(os.path.join(folder, f), encoding="utf-8") as fh:
                c = json.load(fh)
            if isinstance(c, dict) and c.get("rig") in (None, "R6") and isinstance(c.get("sword"), dict) and read(c).get("blade"):
                names.append(str(c.get("name") or stem))
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            continue
    names = sorted(set(names))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"about": "Clips made BEFORE the on-the-hilt rule (kit/anim/in_hand.py, the owner's V3 list anim stage "
                            "C.2) with a holding hand up the blade and no \"on_blade\" said. They are said, never failed; "
                            "the list is never extended.",
                   "frozen": today or datetime.date.today().isoformat(), "clips": names}, fh, indent=1)
        fh.write("\n")
    return names


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
        if isinstance(c, dict) and gate(dict(c, source=None))[1]:     # exactly what the gate fails, list or no list
            names.append(str(c.get("name") or stem))
    names = sorted(set(names))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"about": "Clips made BEFORE the weapon-in-hand check (kit/anim/in_hand.py; the owner 2026-11-13: every "
                            "method enforced in use) whose weapon leaves both hands with no toss or draw declared. They are "
                            "said, never failed. FROZEN: never add a name here to get a clip built - declare its toss with "
                            "an event (Toss ... Catch) or bring the hand back to the weapon.",
                   "frozen": today or datetime.date.today().isoformat(), "clips": names}, fh, indent=1)
        fh.write("\n")
    return names


def gate(clip):
    """what the build's motion gates add for this clip (kit/anim/metrics.py) -> (the reading for metrics.json, the
    problem or None). A clip with no weapon has nothing to hold; one made before the rule (the frozen list beside
    its source: <anims>/blocks/_weapon_loose_before.json) is said, never failed; a weapon track that cannot be read
    is a problem (it is exported to the game as it is)"""
    try:
        said = hands_of(clip)
    except ValueError as e:
        return {"error": str(e)}, f"its hands could not be read ({e})"
    if clip.get("rig") != "R6" or not isinstance(clip.get("sword"), dict):
        if said and clip.get("rig") == "R6":
            return {"hands": said}, f"it says its hands are \"{said}\" and carries no weapon to hold"
        return None, None
    name = str(clip.get("name"))
    try:
        r = read(clip)
    except (ValueError, KeyError, IndexError, TypeError) as e:
        return {"error": f"{type(e).__name__}: {e}"}, f"the weapon's path could not be read ({type(e).__name__}: {e})"
    out = {"worst_studs": r["worst"], "windows": r["windows"], "loose": r["loose"], "hands": r.get("grip"), "on": r.get("on"),
           "on_blade": r.get("blade") or []}
    src = (clip.get("source") or {}).get("file") if isinstance(clip.get("source"), dict) else None
    anims = os.path.dirname(src) if isinstance(src, str) and src else os.path.join("assets", "animations")
    if r["weapon"] and r.get("blade") and not r["loose"]:
        try:
            old_blade = before(os.path.join(anims, "blocks", BLADE_BEFORE))
        except (ValueError, OSError) as e:
            return out, f"the list of clips made before the on-the-hilt rule could not be read ({e})"
        if name in old_blade:
            out["made_before_the_hilt_rule"] = True
            return out, None
        return out, blade_words(r, name) + " - bring the hand back to the hilt, or say where it holds the blade"
    if not r["weapon"] or not r["loose"]:
        return out, None
    try:
        old = before(os.path.join(anims, "blocks", BEFORE))
    except (ValueError, OSError) as e:                       # (a list that cannot be read excuses nobody)
        return out, f"the list of clips made before the weapon-in-hand rule could not be read ({e})"
    if name in old and not r.get("grip"):                    # (a clip that SAYS its hands is held to them: said after the freeze)
        out["made_before_the_rule"] = True
        return out, None
    return out, (words(r, name) + " - if it is thrown or passed there, say so with the clip's events (Toss / Pass ... Catch); "
                 "if not, bring the hand back to the weapon (a feel or polish pass moved it off)"
                 + (", or say the hands it really has (\"hands\")" if r.get("grip") else ""))


def flag(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        print(__doc__)
        return 2
    try:
        if argv[0] == "freeze":
            if len(argv) < 2 or not flag(argv, "--out"):
                return emit("fail", "anim in-hand freeze: <the built clips' folder> --out <list.json>", "python kit/anim/in_hand.py")
            names = freeze(argv[1], flag(argv, "--out"))
            return emit("pass", f"anim in-hand freeze: {len(names)} clip(s) made before the rule -> {flag(argv, '--out')}",
                        "none - a clip made from now on keeps its weapon in a hand or declares its toss", clips=names)
        if argv[0] == "freeze-blade":
            if len(argv) < 2 or not flag(argv, "--out"):
                return emit("fail", "anim in-hand freeze-blade: <the built clips' folder> --out <list.json>",
                            "python kit/anim/in_hand.py")
            names = freeze_blade(argv[1], flag(argv, "--out"))
            return emit("pass", f"anim in-hand freeze-blade: {len(names)} clip(s) with a hand up the blade made before the "
                        f"rule -> {flag(argv, '--out')}", "none - a clip made from now on holds the hilt or says \"on_blade\"",
                        clips=names)
        with open(argv[0], encoding="utf-8") as fh:
            c = json.load(fh)
        if not isinstance(c, dict) or len(c.get("times") or []) < 2 or not isinstance(c.get("joints"), dict):
            return emit("fail", f"anim in-hand: {argv[0]} is not a clip with frames", "lune run kit anim <Name>")
        name = str(c.get("name") or os.path.basename(argv[0]).split(".")[0])
        r = read(c)
        old = before(flag(argv, "--before"))
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        return emit("fail", f"anim in-hand: the clip could not be read ({type(e).__name__}: {e})", "lune run kit anim <Name>")
    slim = {"loose": r["loose"], "windows": r["windows"], "worst": r["worst"]}
    if not r["loose"]:
        return emit("pass", f"anim in-hand: {words(r, name)}", "none - proceed", **slim)
    if name in old:
        return emit("pass", f"anim in-hand: NOT HELD (a clip made before the rule) - {words(r, name)}",
                    "improve the clip when it is next worked on: declare the toss (events Toss ... Catch) or bring the hand "
                    "back to the weapon", **slim)
    a, b, far, k = max(r["loose"], key=lambda x: x[2])
    return emit("fail", f"anim in-hand: {words(r, name)}",
                f"look at frame {k} of {name}: if the weapon is thrown or passed there, say so in the clip (events named "
                "Toss / Pass ... Catch, or a draw's first Catch); if not, the pass that moved the hand off the weapon is the "
                "fault (a feel or polish pass, a hand target that is not the grip) - never the 0.3 studs", **slim)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
