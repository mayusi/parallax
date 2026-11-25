"""proc_strike.py — the STRIKE builder for `kit anim candidates` (the governor 2026-11-04, the owner: "keep going AND USE
THE PIPELIE PROPERLY": weapon moves had no candidates - proc_candidates knew only kicks and reactions, so every sword /
trick clip reached the owner one hand-built version at a time). A weapon move's base is its strike-route move file
(assets/animations/<Name>.move.json, keyed by craft; the owner's BLOCKING edits ride on it as key_edits); a candidate
is that move varied by the four Laban EFFORT sliders, then gated exactly like a kick (proc_candidates.gate: the motion
gates, the proc gates, the R6 VOCABULARY gate - no frozen legs - the dossier checks, MuJoCo):
  time    sudden (+) / sustained (-): every key interval shorter / longer (to 15 %); the markers move with the keys
  weight  strong (+) / light (-): the crouch deeper (capped at R-anim-6's 0.55) and the bend forward stronger
  space   indirect (+) / direct (-): the torso carried further round past the contact (the keys after the Hit)
  flow    free (+) / bound (-): the blade's lag and momentum loosened / tightened, the keys' overshoot with them
The sliders only spread the move; the dossier still holds every candidate to its checks.
VARIANTS (the governor 2026-11-04, the owner 'All bad' on both round-0 sets: the 8 were COUSINS - one base, eight
slider nudges, the same mid-move): a move file may carry `variants`: [{"name", "keys", "feet"?, "events"?, "beats"?,
"line"?}, ...] - other cut lines / heights / spin entries of the same move, each keyed by craft. The base keys are
variant 0; a genome's "variant" picks one (round 0 deals them out in turn; a bred child keeps its parent's).
    build(d, s, name)  -> (clip, build) for proc_candidates.make / emit"""
import copy
import json
import os

ANIM = os.path.join("assets", "animations")
CROUCH_MAX = 0.55                    # R-anim-6: a crouch never slides a leg ~0.3-0.45 studs into the torso past this


def move_path(d, name):
    """the base move: the dossier's own build.move_file (a one-move dossier) or the candidates' own name's move file
    (a family dossier like spin_drill covers many clips)"""
    p = d["build"].get("move_file")
    base = name.split("_r")[0]
    own = os.path.join(ANIM, f"{base}.move.json")
    return own if os.path.isfile(own) else p


def variant_count(d, name):
    return 1 + len(base_move(d, name).get("variants") or [])


def with_variant(m, v):
    """the move with variant v's fields over the base (0 = the base itself)"""
    vs = m.get("variants") or []
    m = {k: x for k, x in m.items() if k != "variants"}
    if v and 0 < int(v) <= len(vs):
        m.update({k: copy.deepcopy(x) for k, x in vs[int(v) - 1].items() if k != "name"})
        m["variant"] = vs[int(v) - 1].get("name", f"v{v}")
    return m


def base_move(d, name):
    p = move_path(d, name)
    if not p or not os.path.isfile(p):
        raise SystemExit(f"proc_strike: no strike move file for {name} (assets/animations/{name}.move.json or the dossier's build.move_file)")
    m = json.load(open(p, encoding="utf-8"))
    edits = os.path.join(ANIM, "blocks", f"{m['name']}.edits.json")
    if os.path.isfile(edits):                               # the owner's blocking changes ride on every candidate
        m["key_edits"] = json.load(open(edits, encoding="utf-8")).get("keys", {})
    return m


def retime(t, old, new):
    """a time through the keys' old -> new times (piecewise linear; past the end it shifts with the last key)"""
    if t <= old[0]:
        return t
    for a0, a1, b0, b1 in zip(old, old[1:], new, new[1:]):
        if t <= a1:
            return b0 + (t - a0) * (b1 - b0) / max(a1 - a0, 1e-9)
    return t - old[-1] + new[-1]


def apply_sliders(m, s):
    m = copy.deepcopy(m)
    t, w, sp, fl = (float(s.get(k, 0.0)) for k in ("time", "weight", "space", "flow"))
    keys = sorted(m["keys"], key=lambda k: float(k["t"]))
    hit = next((float(e["t"]) for e in m.get("events", []) if e.get("name") == "Hit"), None)
    # time: every interval scaled (the keys stay ordered); the markers, beats and block keys go with them
    f = 1.0 - 0.15 * t
    old = [float(k["t"]) for k in keys]
    new = [old[0]]
    for a, b in zip(old, old[1:]):
        new.append(new[-1] + (b - a) * f)
    for k, nt in zip(keys, new):
        k["t"] = round(nt, 4)
    for e in m.get("events", []):
        e["t"] = round(retime(float(e["t"]), old, new), 4)
    for side in ("feet",):
        for fk in m.get(side) or []:
            fk["t"] = round(retime(float(fk["t"]), old, new), 4)
    if m.get("block_keys"):
        m["block_keys"] = [round(retime(float(x), old, new), 4) for x in m["block_keys"]]
    if isinstance(m.get("beats"), dict):
        m["beats"] = {n: [round(retime(float(a), old, new), 4), round(retime(float(b), old, new), 4)] for n, (a, b) in m["beats"].items()}
    hit_new = retime(hit, old, new) if hit is not None else None
    for k in keys:
        # weight: deeper / shallower, a stronger / lighter bend
        if "crouch" in k:
            k["crouch"] = round(min(CROUCH_MAX, max(0.0, float(k["crouch"]) * (1 + 0.25 * w))), 3)
        if "pitch" in k and float(k["pitch"]) < 0:
            k["pitch"] = round(float(k["pitch"]) * (1 + 0.2 * w), 2)
        # space: the torso carried further round past the contact
        if hit_new is not None and float(k["t"]) > hit_new and "yaw" in k:
            k["yaw"] = round(float(k["yaw"]) + 10 * sp, 2)
        # flow: the follow-through
        if k.get("overshoot"):
            k["overshoot"] = round(max(0.0, float(k["overshoot"]) * (1 + 0.6 * fl)), 3)
    m["keys"] = keys
    m["lag"] = round(max(0.0, float(m.get("lag", 0.03)) * (1 + 0.6 * fl)), 4)
    if m.get("inertia"):
        m["inertia"] = round(max(0.0, float(m["inertia"]) * (1 + 0.6 * fl)), 4)
    return m


def build(d, s, name):
    """(clip, build) - the candidate's clip from the move + its sliders; the build carries the vocabulary gate"""
    import strike as S
    m = apply_sliders(with_variant(base_move(d, name), s.get("variant", 0)), s)
    m["name"] = name
    c, _ = S.generate(m)
    if not c.get("beats"):                                   # (its own beats in the clip: the sheet poses them, j6x7)
        import clip_beats as CB
        hit = next((float(e["t"]) for e in c.get("events") or [] if e.get("name") == "Hit"), None)
        c["beats"] = CB.by_dossier(d, [float(k["t"]) for k in m["keys"]], hit, float(c["times"][-1])) or None
    return c, {**d["build"], "slides": "r6_vocab"}
