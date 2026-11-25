"""anim_gallery.py — gallery tuning for the animation candidates (research proposal 10, kit/tools/gallery.py): what
the owner did on a move's pick sheets becomes a taste model over its SETTINGS (the four effort sliders, the arms
choice - habit and whip - and a keyed move's line), and the next round's sheet is chosen with it.

  evidence   every candidate shown in the move's earlier rounds BY THE SAME GENERATOR (another builder's sliders
             mean other motions); each PICK the owner made (a later round's parents, or the parents this round breeds
             from - a round that records another picker never counts) beat every other candidate of its round; each
             REJECTION is the owner's own verdict note (check_validate.owner_rejections: 3 or less or Redo; "All bad" =
             every candidate of the round). A model-guessed note never counts.
  proposals  with evidence, settings worth building: likely-good ones (the best guesses) and informative ones (where
             the model knows least) go to the front of the pool.
  the sheet  from a larger pool of gate-clean candidates, n chosen: likely beside learn (with no evidence: spread), each
             one as far as it can be from the others in MOTION. On the only renders that survive (24 candidates of 3
             blade rounds, 84 pairs, 2026-11-08) slider distance did not predict look distance and joint-rotation
             distance did, weakly (kit/tools/gallery.py has the numbers). A clip with no joint tracks is spaced by its
             settings.

    python kit/anim/anim_gallery.py <Move>       what the model has learned for one move (or every move with none)"""

import glob
import json
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)
import gallery as G  # noqa: E402

SPACE = G.Space(("time", "weight", "space", "flow"), ("arms", "variant"))
JOINTS = ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")
SAMPLES = 40
POOL = 2.5  # gate-clean candidates built per sheet slot, to choose the sheet from
SAMPLE = 400  # random settings the model scores for proposals
MANIFESTS = os.path.join("assets", "animations", "candidates")
ROUND_ID = re.compile(r"/r(\d+)/c\d+$")


def signature(clip):
    """a clip's motion: each joint's rotation (unit quaternion) at SAMPLES points of its own normalised time -> array
    (joints, SAMPLES, 4), or None when the clip has no joint tracks"""
    try:
        q = np.stack([np.asarray([f[:4] for f in clip["joints"][j]["frames"]], float) for j in JOINTS])
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    if q.ndim != 3 or q.shape[1] < 2 or q.shape[2] != 4:
        return None
    q = q[:, np.round(np.linspace(0, q.shape[1] - 1, SAMPLES)).astype(int)]
    return q / np.maximum(np.linalg.norm(q, axis=-1, keepdims=True), 1e-9)


def motion_distance(a, b):
    """the mean angle (radians) between two signatures' joint rotations, sample by sample"""
    return float(np.mean(2 * np.arccos(np.clip(np.abs(np.sum(a * b, axis=-1)), 0, 1))))


def settings_distance(a, b):
    xa, xb = SPACE.numeric([a])[0], SPACE.numeric([b])[0]
    return float(np.linalg.norm(xa - xb)) + 0.5 * sum(pa != pb for pa, pb in zip(SPACE.parts(a), SPACE.parts(b)))


def distance(a, b):
    """two built candidates ({"sliders", "sig"}): by motion when both have joint tracks, else by settings"""
    if a.get("sig") is not None and b.get("sig") is not None:
        return motion_distance(a["sig"], b["sig"])
    return settings_distance(a["sliders"], b["sliders"])


def load_rounds(name, manifests=None):
    out = []
    for path in glob.glob(os.path.join(manifests or MANIFESTS, name, "round_*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                man = json.load(f)
        except (OSError, ValueError):
            continue
        m = re.search(r"round_(\d+)\.json$", path)
        rnd = int(man.get("round", m.group(1) if m else -1))
        out.append({"move": name, "round": rnd, "candidates": man.get("candidates") or [], "parents": man.get("parents") or [],
                    "builder": man.get("builder"), "picked_by": man.get("picked_by"),
                    "efforts": int(man.get("efforts", 1)),    # (a round from before the field: the first mapping)
                    "setup": setup_of(man)})
    return sorted(out, key=lambda r: r["round"])


def setup_of(man):
    """what a round's settings MEAN beyond its builder and mapping: the reach its efforts were stretched by and the
    blade lines its `variant` indexes (proc_candidates, efforts mapping 2) - a round without them: None, None"""
    lines = man.get("lines")
    return {"reach": man.get("reach") or None, "lines": lines if lines and len(lines) > 1 else None}


def same_generator(recorded, builder):
    """did a round come from the generator making this one? Its sliders mean other motions under another builder (the
    11-04 keyed-pose rounds vs proc_blade, review 2026-11-08). A round that recorded no builder predates the field,
    which arrived with proc_blade (4d39b28a, 2026-11-05): it cannot be proc_blade's"""
    if builder is None:
        return True
    if recorded is None:
        return builder != "proc_blade"
    return recorded == builder


def evidence(name, manifests=None, root=".", parents=(), before=None, builder=None, picked_by="owner", efforts=None,
             setup=None):
    """the owner's evidence on a move's rounds (those before `before`, made by the same generator `builder` and, when
    given, the same efforts mapping `efforts` - proc_candidates.EFFORTS - and the same `setup` (setup_of: the reach the
    sliders were stretched by, the lines `variant` indexes): under another mapping, reach or line set the same settings
    are other motions) -> {"points", "ids", "prefs", "bad", "counts"}. A pick counts when the owner made it: a round's
    parents unless it records another picker (`picked_by`), and `parents` (this round's) when `picked_by` is the owner"""
    import check_validate as CV  # noqa: PLC0415  (the owner's rejections, owner-only)

    earlier = [r for r in load_rounds(name, manifests) if before is None or r["round"] < before]
    rounds = [r for r in earlier if same_generator(r["builder"], builder) and (efforts is None or r["efforts"] == efforts)
              and (setup is None or r["setup"] == setup)]
    points, ids, index, members = [], [], {}, {}
    for r in rounds:
        for c in r["candidates"]:
            if c.get("id") in index or not isinstance(c.get("sliders"), dict):
                continue
            index[c["id"]] = len(points)
            points.append(c["sliders"])
            ids.append(c["id"])
            members.setdefault(r["round"], []).append(c["id"])
    picks = {p for r in rounds if r["picked_by"] in (None, "owner") for p in r["parents"] if p in index}
    if picked_by == "owner":
        picks |= {p for p in parents if p in index}
    prefs = []
    for p in sorted(picks):
        m = ROUND_ID.search(p)
        for other in members.get(int(m.group(1)), []) if m else []:
            if other not in picks:
                prefs.append((index[p], index[other]))
    bad, all_bad = set(), 0
    for (move, rnd), rej in CV.owner_rejections(root, rounds).items():
        if move != name or rnd not in members:
            continue
        if rej["ids"] is None:
            all_bad += 1
            bad |= {index[c] for c in members[rnd]}
        else:
            bad |= {index[c] for c in members[rnd] if c.rsplit("/c", 1)[-1] in rej["ids"]}
    counts = {"rounds": len(rounds), "shown": len(points), "picks": len(picks), "pairs": len(prefs),
              "rejected": len(bad), "all_bad_rounds": all_bad, "other_generator": len(earlier) - len(rounds)}
    return {"points": points, "ids": ids, "prefs": prefs, "bad": sorted(bad), "counts": counts}


def model_for(name, manifests=None, root=".", parents=(), before=None, builder=None, picked_by="owner", efforts=None,
              setup=None):
    ev = evidence(name, manifests, root, parents, before, builder, picked_by, efforts, setup)
    return G.Model(SPACE, ev["points"], ev["prefs"], ev["bad"]), ev


def said(counts):
    """what the model learned from, in words"""
    c = counts
    other = (f"; {c['other_generator']} earlier round(s) by another generator left out" if c.get("other_generator") else "")
    if not (c["pairs"] or c["rejected"]):
        return f"nothing learned yet ({c['shown']} candidate(s) shown, no pick or rejection of the owner's on them{other})"
    bits = []
    if c["picks"]:
        bits.append(f"{c['picks']} pick(s) ({c['pairs']} comparisons)")
    if c["rejected"]:
        bits.append(f"{c['rejected']} rejected candidate(s)" + (f", {c['all_bad_rounds']} round(s) All bad" if c["all_bad_rounds"] else ""))
    return "learned from " + " and ".join(bits) + f" over {c['shown']} shown{other}"


def proposals(model, n, arms, nv, seed):
    """with evidence: about n settings to build first - half likely-good, half informative - from SAMPLE random ones"""
    if model is None or not model.evidence():
        return []
    rs = np.random.default_rng(seed + 7919)
    arms = tuple(arms) or (None,)
    sample = []
    for _ in range(SAMPLE):
        s = {k: round(float(rs.uniform(-1, 1)), 2) for k in SPACE.numbers}
        a = arms[int(rs.integers(len(arms)))]
        if a is not None:
            s["arms"] = a
        if nv > 1:
            s["variant"] = int(rs.integers(nv))
        sample.append(s)
    k = max(1, n // 2)
    return G.propose(model, sample, k, k)


def first_built(rows, n, group=None, cap=None):
    """the sheet the kit chose before gallery tuning: the first n gate-clean candidates built, a line's share kept
    while others pass, the spares filling any gap"""
    kept, spare = [], []
    for r in rows:
        if group is not None and cap is not None and sum(1 for k in kept if group(k) == group(r)) >= cap:
            spare.append(r)
            continue
        kept.append(r)
        if len(kept) >= n:
            break
    return kept + spare[: max(0, n - len(kept))]


def sheet(rows, n, model=None, group=None, cap=None, counts=None):
    """rows: gate-clean candidates in build order, each {"sliders", "sig", ...} -> (the sheet's rows in order, a
    report {"model", "pool", "measure", "sheet": [min, mean], "first_built": [min, mean], "roles"})"""
    chosen, info = G.select(rows, n, lambda r: r["sliders"], distance, model=model, group=group, cap=cap)
    out = []
    for i in chosen:
        out.append({**rows[i], "gallery": info[i]})
    old = first_built([r for r in rows if not r.get("proposed")], n, group, cap)  # what the kit showed before: no proposals
    measure = "motion" if all(r.get("sig") is not None for r in rows) else "settings"
    roles = {}
    for i in chosen:
        roles[info[i]["role"]] = roles.get(info[i]["role"], 0) + 1
    report = {"model": said(counts) if counts else "nothing learned yet", "pool": len(rows), "measure": measure,
              "sheet": list(G.spread(out, distance)), "first_built": list(G.spread(old, distance)), "roles": roles}
    return out, report


def label(s):
    """a candidate's settings as the pick sheet labels them: t+0.3 w-0.5 s+0.1 f+0.0 habit:1:out"""
    nums = " ".join(f"{k[0]}{float(s.get(k) or 0):+.1f}" for k in SPACE.numbers)
    return f"{nums} {s.get('arms') or ''}".strip()


def main(argv):
    names = argv[:1] or sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(MANIFESTS, "*", "round_0.json")))
    lines = []
    for name in names:
        # the move's generator now: its newest round's recorded builder (none recorded: every round counts) and its
        # efforts mapping
        rounds = load_rounds(name)
        builder = next((r["builder"] for r in reversed(rounds) if r["builder"]), None)
        model, ev = model_for(name, builder=builder, efforts=rounds[-1]["efforts"] if rounds else None,
                              setup=rounds[-1]["setup"] if rounds else None)
        line = f"{name}: {said(ev['counts'])}"
        if model.evidence():
            mean, _ = model.predict(ev["points"])
            best = sorted(range(len(mean)), key=lambda i: -mean[i])[:3]
            what = "best guesses among those shown" if ev["counts"]["picks"] else "the shown ones least like what the owner rejected"
            line += f"; {what}: " + ", ".join(f"{ev['ids'][i]} ({label(ev['points'][i])})" for i in best)
        lines.append(line)
        print(line)
    learned = sum(1 for ln in lines if ": learned from" in ln)
    print(json.dumps({"schema": 1, "status": "pass",
                      "summary": f"anim gallery: {learned} of {len(lines)} move(s) have the owner's picks or rejections to learn from",
                      "next_action": "the next round of a move uses them: lune run kit anim candidates <Move> --round K --parents <the owner's picks>"}))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
