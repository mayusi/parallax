"""owner_faults.py — the owner's NAMED faults as checks every generated weapon clip must pass before he sees it (card
xr8w, 2026-11-10; the owner: "The animation really needs a lot of work ... it's the one that I need to work amazingly
well"). A fault he named once must never reach him again: each is measured on the motion, its line drawn BETWEEN his
real rejected clip and the clips he loved (never a guess), and `kit selftest` proves every one still fails that
rejected clip (kit/selftest/anim/faults/) while the loved ones pass:
  stilts       a CUT whose crouch is a DIP, not a stance: the body at least half its lowest for under half the clip
               (crouch_hold_share < 0.5, the bound spin_drill's dt4_crouch_held already uses). His Swift swings
               v2 (2026-11-04: 'leg work is horrible'): 0.25-0.48 on 5 of the 6 cuts; GreatswordSideCut v1 (1/10): 0.00;
               the legs he loved (GsCombo1-4, Katana1-3: 'legs crouch + slide in like the loved HQ pack'): 1.00. The one
               loved piece it flags is GreatswordSideCut v2 (0.48), whose legs he set aside himself ('OBVIOUSLY ITS ONLY
               TORSO AND ARMS BUT WOW') and asked for next - the combo that fixed them is the one he loved with legs.
               Cuts only: the loved R6 store spins never crouch (0.00) and are loved
  arm-only     a CUT whose main hand sweeps under 3.0 studs in the TORSO frame (hand_sweep_studs): the arm swings in a
               box at the shoulder while the body does nothing. GreatswordSideCut v1 (1/10, 2026-10-17): 2.21; every cut
               he loved: 3.80-5.53 (the 10-18 breakthrough was exactly this number)
  blade flops  a SPIN whose blade leaves one plane by more than 20 deg (blade_plane_dev_deg): it dips to the floor and
               up behind the head. His rejected spins: DTDrillSpin4 42.3, the first DTDrillSpin 38.1, the Swift
               Pirouette 38.6 / RisingSpin 23.6; the drill cards since its dossier's flat-disc check: <= 14.8 (character-action's
               drill, his pick, a flat disc - the drill's own dossier keeps its stricter 15)
  legs twist   a SPIN whose legs face more than 90 deg off the torso while it turns (leg_twist_deg): the feet left
               behind as the body spins over them, the legs wrung round under it. DTDrillSpin4 ('THE LEGS LOOK HORRIBLE
               TOO') 178, the first DTDrillSpin 180, Pirouette 173, RisingSpin 171; the loved R6 spins 0-43, the drill
               cards since 5-7
A SPIN = the body turning one whole turn or more (spin_turns >= 1); a CUT = any other clip with a sword track.
Each line sits between his rejections and the clips he loved (measured 2026-11-10, _artifacts/anim-faults/).
    python kit/anim/owner_faults.py check <clip.json | Name.move.json> ...   -> a verdict (fail names each fault)
    python kit/anim/owner_faults.py measure <clip.json | Name.move.json> ... -> the numbers, one JSON row each"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

SPIN_TURNS = 1.0
# fault id -> (measure, "below" | "above", limit, applies to, the owner's words + the real rejected clip it fails)
LIMITS = {
    "stilts": ("crouch_hold_share", "below", 0.5, "cut",
               "the Swift swings v2 2026-11-04 'leg work is horrible' (held 0.25-0.48); the legs he loved held 1.00"),
    "arm-only": ("hand_sweep_studs", "below", 3.0, "cut",
                 "GreatswordSideCut v1 1/10 2026-10-17 (2.21 studs); the cuts he loved 3.80-5.53"),
    "blade flops": ("blade_plane_dev_deg", "above", 20.0, "spin",
                    "DTDrillSpin4 1/10 2026-11-04 'blade flops' (42.3 deg); character-action's drill a flat disc"),
    "legs twist": ("leg_twist_deg", "above", 90.0, "spin",
                   "DTDrillSpin4 1/10 2026-11-04 'THE LEGS LOOK HORRIBLE TOO' (178 deg); the loved R6 spins 0-43"),
}


def _yaw_of(R, axis=(0.0, 0.0, -1.0)):
    f = R[:3, :3] @ np.asarray(axis, float)
    return math.atan2(-f[0], -f[2])


def spin_frames(c, W):
    """the frames the body is SPINNING: turning at >= half its fastest sustained rate (0.25 s) over a short centred
    window, the longest run of them (shape_ref's spin window, so the two never disagree on what the spin is)"""
    n = len(W)
    fps = float(c.get("fps", 60))
    yaw = np.unwrap([_yaw_of(w["Torso"]) for w in W])
    w = max(1, int(round(0.25 * fps)))
    if n <= w:
        return np.arange(0), yaw
    rate = np.abs(yaw[w:] - yaw[:-w]) / (w / fps) / (2 * math.pi)
    h = max(1, int(round(0.05 * fps)))
    inst = np.array([abs(yaw[min(n - 1, i + h)] - yaw[max(0, i - h)]) / ((min(n - 1, i + h) - max(0, i - h)) / fps)
                     / (2 * math.pi) for i in range(n)])
    ok = (inst >= 0.5 * rate.max()) & (inst <= 2.0 * rate.max())
    runs, i0 = [], None
    for i, v in enumerate(list(ok) + [False]):
        if v and i0 is None:
            i0 = i
        elif not v and i0 is not None:
            runs.append((i0, i))
            i0 = None
    a, b = max(runs, key=lambda r: r[1] - r[0]) if runs else (0, 0)
    return np.arange(a, b), yaw


def leg_twist_deg(c, W=None):
    """over the spin's frames, the worst angle between a leg's facing and the torso's (about the vertical): a body
    spinning over feet that stay put twists its legs round under it (R6 has no hip turn - the legs go round with it)"""
    import clip as C
    W = W if W is not None else C.world_frames(c, C.load_rig("R6"))
    frames, _ = spin_frames(c, W)
    worst = 0.0
    for i in frames:
        ty = _yaw_of(W[i]["Torso"])
        for leg in ("Right Leg", "Left Leg"):
            d = (_yaw_of(W[i][leg]) - ty + math.pi) % (2 * math.pi) - math.pi
            worst = max(worst, abs(math.degrees(d)))
    return worst


def load(path):
    """a clip.json, or a strike move file (Name.move.json) generated the way the anim bake makes it (steps are
    presentation: measured on the smooth motion, as proc_dossier.build_failing does)"""
    d = json.load(open(path, encoding="utf-8"))
    if d.get("kind") == "strike" or path.endswith(".move.json"):
        import strike as S
        d.pop("step", None)
        d, _ = S.generate(d)
    return d


def measure(c):
    import clip as C
    import shape_ref as SR
    W = C.world_frames(c, C.load_rig("R6"))
    m = SR.measure(c)
    m["leg_twist_deg"] = round(leg_twist_deg(c, W), 2)
    m["kind"] = "spin" if float(m.get("spin_turns") or 0.0) >= SPIN_TURNS else ("cut" if c.get("sword") else "body")
    return m


def faults(c, m=None):
    """-> [{fault, measure, value, limit, why}] for every named fault this clip shows (none = it may be shown)"""
    m = m or measure(c)
    out = []
    for fid, (key, side, lim, kind, why) in LIMITS.items():
        if kind != "any" and kind != m["kind"]:
            continue
        v = m.get(key)
        if v is None or (isinstance(v, float) and v != v):
            continue
        if (side == "below" and v < lim) or (side == "above" and v > lim):
            out.append({"fault": fid, "measure": key, "value": round(float(v), 3), "limit": lim, "side": side, "why": why})
    return out


def verdict(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    cmd = a[0] if a else "help"
    files = [x for x in a[1:] if not x.startswith("--")]
    if cmd == "measure":
        for f in files:
            print(json.dumps({"clip": f, **measure(load(f))}))
    elif cmd == "check":
        found = {}
        for f in files:
            fs = faults(load(f))
            if fs:
                found[f] = fs
        if found:
            first = next(iter(found))
            words = "; ".join(f"{os.path.basename(k)}: " + ", ".join(
                f"{x['fault']} ({x['measure']} {x['value']} {'<' if x['side'] == 'below' else '>'} {x['limit']})" for x in v)
                for k, v in found.items())
            verdict("fail", f"owner faults: {words}",
                    f"{first}: {found[first][0]['fault']} - the owner rejected exactly this ({found[first][0]['why']})",
                    faults=found)
            sys.exit(1)
        verdict("pass", f"{len(files)} clip(s) free of the owner's named faults", "none - proceed")
    else:
        print(__doc__)
