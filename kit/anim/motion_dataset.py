"""motion_dataset.py — the R6 MOTION DATASET for a learned motion model (data prep only; no training here).

    python kit/anim/motion_dataset.py build [--aug 2] [--seed 0]   -> _artifacts/r6data/
    python kit/anim/motion_dataset.py regroup                      -> labels get "group" + "group_rule" (groups.json)

Source: every unique native R6 clip of the catalog (_artifacts/r6lib/index.json; content-hash deduped), any verdict.
Per clip, at a unified 60 fps (slerp resample, kit/anim/warp.py):
    rot   [T, 6, 4]  joint rotations, character space (kit/anim/clip.py), quaternion xyzw, sign-continuous over time
    pos   [T, 6, 3]  joint offsets (studs; R6 animators SLIDE limbs - this is real signal, not noise)
    root_pos [T, 3]  the Torso joint's offset from the HumanoidRootPart (R6 clips carry the body's travel / bob / crouch
                     there; a clip never moves the HumanoidRootPart itself - the game's physics does)
    root_vel [T, 3]  its velocity (studs/s, central difference; a loop wraps)
    mask  [6]        1 = the clip keys that joint (0 = rest filled in)
Joint order: Torso, Head, Right Arm, Left Arm, Right Leg, Left Leg.

Augmentation (kit/anim/warp.py + derive.op_mirror): each clip -> original + mirror; each of those -> `aug` variants with
a random retime (duration x U[0.8, 1.25]) and amplitude (all joints about their mean, x U[0.85, 1.15]).
Labels (labels.jsonl): id, text (built from name / pack / kind / measured tags + the catalog caption), kind, tags,
owner_verdict (love / ok / bad / laggy / unrated - a SEPARATE field, never in the text), licence (game / study),
source, pack, creator, asset, loop, frames, augmentation.
Outputs: clips.npz (original), aug.npz (augmented), labels.jsonl, packs.json (licence + source per pack), report.json"""
import copy
import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import derive as D  # noqa: E402
import motion_lib as ML  # noqa: E402
import warp as W  # noqa: E402

LIB = os.path.join("_artifacts", "r6lib")
OUT = os.path.join("_artifacts", "r6data")
JOINTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
FPS = 60


def tensors(c):
    """a 60 fps clip -> (rot [T,6,4], pos [T,6,3], root_pos [T,3], root_vel [T,3], mask [6])"""
    T = len(c["times"])
    rot = np.zeros((T, 6, 4))
    rot[..., 3] = 1.0
    pos = np.zeros((T, 6, 3))
    mask = np.zeros(6)
    for k, j in enumerate(JOINTS):
        F = c["joints"].get(j, {}).get("frames")
        if not F:
            continue
        mask[k] = 1
        A = np.asarray(F, float)[:T]
        q = A[:, :4] / np.linalg.norm(A[:, :4], axis=1, keepdims=True)
        for i in range(1, len(q)):                      # sign-continuous: q and -q are the same rotation
            if np.dot(q[i], q[i - 1]) < 0:
                q[i] = -q[i]
        rot[: len(q), k] = q
        pos[: len(q), k] = A[:, 4:7]
    root = pos[:, 0].copy()
    if c.get("loop") and T > 2:
        vel = (np.roll(root, -1, 0) - np.roll(root, 1, 0)) * FPS / 2
    else:
        vel = np.gradient(root, 1.0 / FPS, axis=0) if T > 1 else np.zeros_like(root)
    return rot.astype(np.float32), pos.astype(np.float32), root.astype(np.float32), vel.astype(np.float32), mask.astype(np.float32)


PAIRS = {"Right Arm": "Left Arm", "Left Arm": "Right Arm", "Right Leg": "Left Leg", "Left Leg": "Right Leg"}


def mirror(c):
    """derive.op_mirror swaps left / right tracks: a clip that keys one side only gets the other side's REST first"""
    n = len(c["times"])
    for a, b in PAIRS.items():
        if a in c["joints"] and b not in c["joints"]:
            c["joints"][b] = {"frames": [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]] * n}
    return D.op_mirror(c)


def augment(c, rng, mirror_it):
    a = copy.deepcopy(c)
    if mirror_it:
        mirror(a)
    f = float(rng.uniform(0.8, 1.25))
    k = float(rng.uniform(0.85, 1.15))
    a = W.time_warp(a, factor=f)
    for j in a["joints"]:
        if len(a["joints"][j]["frames"]) > 2:
            W.amp_scale(a, j, "all", k)
    return a, {"mirror": mirror_it, "retime": round(f, 3), "amp": round(k, 3)}


def text_of(r, cat):
    words = [r["name"], r.get("pack", ""), r.get("kind", "")]
    if cat:
        words += cat.get("tags", [])
    base = " | ".join(w for w in words if w)
    return f"{base}. {cat['caption']}" if cat and cat.get("caption") else base


def pack_rows(rows):
    packs = {}
    for r in rows:
        key = r["pack"] or "(no pack)"
        p = packs.setdefault(key, {"pack": key, "source": r["source"], "creator": r["creator"], "asset": r["asset"],
                                   "licence": set(), "clips": 0, "frames": 0})
        p["licence"].add(r["licence"])
        p["clips"] += 1
        p["frames"] += r["frames"]
    for p in packs.values():
        p["licence"] = "/".join(sorted(p["licence"]))
    return sorted(packs.values(), key=lambda p: -p["frames"])


def build(aug=2, seed=0):
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(seed)
    index = json.load(open(os.path.join(LIB, "index.json"), encoding="utf-8"))
    cat = {r["id"]: r for r in ML.load()}
    picks = {}
    pp = os.path.join("assets", "animations", "library", "owner_picks.json")
    if os.path.isfile(pp):
        picks = {r["id"]: r for r in json.load(open(pp, encoding="utf-8"))["picks"]}
    live = ML.live_verdicts()
    orig, augd, labels, skipped = {}, {}, [], []
    for r in index:
        p = os.path.join(LIB, "clips", f"{r['id']}.clip.json")
        if not os.path.isfile(p):
            skipped.append((r["id"], "no clip file"))
            continue
        c = json.load(open(p, encoding="utf-8"))
        if c.get("rig") != "R6" or "Torso" not in c.get("joints", {}):
            skipped.append((r["id"], f"rig {c.get('rig')} / no Torso"))
            continue
        try:
            c = W.to60(c)
        except Exception as e:  # noqa: BLE001
            skipped.append((r["id"], f"resample: {e}"))
            continue
        if len(c["times"]) < 4:
            skipped.append((r["id"], "under 4 frames"))
            continue
        rot, pos, rp, rv, mask = tensors(c)
        orig[r["id"]] = (rot, pos, rp, rv, mask)
        pk = picks.get(r["id"])
        verdict = live.get(r["id"]) or ("unrated" if pk is None else ("laggy" if pk.get("laggy") else pk["verdict"]))
        kind = pk["kind"] if pk and pk.get("kind") else r.get("kind", "other")      # the owner's own kind when rated
        cr = cat.get(r["id"])
        lic, why = ML.licence_of(r)
        orig_row = {"id": r["id"], "text": text_of(r, cr), "kind": kind, "tags": (cr or {}).get("tags", []),
                       "owner_verdict": verdict, "licence": lic, "licence_note": why, "source": r.get("source"),
                       "pack": r.get("pack", ""), "creator": r.get("creator", ""), "asset": r.get("asset"),
                       "loop": bool(c.get("loop")), "frames": int(len(c["times"])), "augmentation": None}
        labels.append(orig_row)
        for m in (False, True):
            for v in range(aug + 1):
                if not m and v == 0:
                    continue                                  # the original is in clips.npz
                if v == 0:
                    a, info = copy.deepcopy(c), {"mirror": True, "retime": 1.0, "amp": 1.0}
                    mirror(a)
                else:
                    a, info = augment(c, rng, m)
                key = f"{r['id']}~{'m' if m else 'o'}{v}"
                augd[key] = tensors(a)
                labels.append({**orig_row, "id": key, "source_id": r["id"], "frames": int(len(a["times"])), "augmentation": info})

    def save(path, d):
        np.savez_compressed(path, **{f"{k}/{n}": v for k, t in d.items() for n, v in zip(("rot", "pos", "root_pos", "root_vel", "mask"), t)})
    save(os.path.join(OUT, "clips.npz"), orig)
    save(os.path.join(OUT, "aug.npz"), augd)
    with open(os.path.join(OUT, "labels.jsonl"), "w", encoding="utf-8") as fh:
        for l in labels:
            fh.write(json.dumps(l, ensure_ascii=False) + "\n")
    origs = [l for l in labels if l["augmentation"] is None]
    packs = pack_rows(origs)
    json.dump(packs, open(os.path.join(OUT, "packs.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    by_kind = {}
    for l in origs:
        k = by_kind.setdefault(l["kind"], {"clips": 0, "frames": 0, "loved": 0})
        k["clips"] += 1
        k["frames"] += l["frames"]
        k["loved"] += l["owner_verdict"] == "love"
    verdicts = {}
    for l in origs:
        verdicts[l["owner_verdict"]] = verdicts.get(l["owner_verdict"], 0) + 1
    lic = {}
    for l in origs:
        lic.setdefault(l["licence"], {"clips": 0, "frames": 0})
        lic[l["licence"]]["clips"] += 1
        lic[l["licence"]]["frames"] += l["frames"]
    f_orig = sum(l["frames"] for l in origs)
    f_aug = sum(l["frames"] for l in labels if l["augmentation"] is not None)
    report = {"fps": FPS, "clips": len(origs), "frames": f_orig, "minutes": round(f_orig / FPS / 60, 1),
              "augmented_clips": len(labels) - len(origs), "augmented_frames": f_aug,
              "total_clips": len(labels), "total_frames": f_orig + f_aug, "total_minutes": round((f_orig + f_aug) / FPS / 60, 1),
              "by_kind": dict(sorted(by_kind.items(), key=lambda kv: -kv[1]["frames"])), "verdicts": verdicts, "licence": lic,
              "packs": len(packs), "skipped": skipped,
              "bytes": {n: os.path.getsize(os.path.join(OUT, n)) for n in ("clips.npz", "aug.npz", "labels.jsonl")},
              "frame_lengths": {"min": min(l["frames"] for l in origs), "median": int(np.median([l["frames"] for l in origs])),
                                "max": max(l["frames"] for l in origs)}}
    json.dump(report, open(os.path.join(OUT, "report.json"), "w", encoding="utf-8"), indent=1)
    return report


# ---------------------------------------------------------------- groups (owner brief 2026-10-12: reclassify "other")
import re  # noqa: E402

KIND_GROUP = {"attack": "combat", "m1/combo": "combat", "ability": "combat", "dash": "combat", "defence": "combat",
              "reaction": "combat", "run": "locomotion", "walk": "locomotion", "jump": "locomotion", "idle": "idle",
              "dance": "dance_emote", "emote": "dance_emote"}
COMBAT_PACK = re.compile(r"jjk|combat|battle ?ground|fight|sword|katana|knife|mace|\baxe\b|gun|weapon|skill|kiraki|"
                         r"tachanka|npc ai|\bm1\b|brawl|martial|kick|punch|boxing|ninja|samurai|anime", re.I)
DANCE_PACK = re.compile(r"danc|emote|fnf|tiktok|friday night", re.I)
MOVE_PACK = re.compile(r"platformer|parkour|sky ?dive|movement|walk|run|locomotion", re.I)
MOVE_TAGS = {"lunge", "spin", "thrust", "downward", "upward", "horizontal", "diagonal"}


def group_of(label):
    """(group, rule): the clip's kind when it is known; for "other", the pack's name, then the measured tags"""
    kind = label.get("kind", "other")
    if kind in KIND_GROUP:
        return KIND_GROUP[kind], f"kind {kind}"
    pack, name, tags = label.get("pack", ""), label["text"].split(" | ")[0], set(label.get("tags", []))
    dur = label.get("frames", 0) / FPS
    if DANCE_PACK.search(pack) or DANCE_PACK.search(name):
        return "dance_emote", "pack/name: dance or emote"
    if COMBAT_PACK.search(pack) and not ("loop" in tags and "strike" not in tags):
        return "combat", "pack: combat"
    if "stride" in tags or (MOVE_PACK.search(pack) and "loop" in tags):
        return "locomotion", "tags: stride / movement pack loop"
    if "loop" in tags and ("holds" in tags or "slow" in tags) and "strike" not in tags:
        return "idle", "tags: loop + holds/slow"
    if "strike" in tags and ("fast" in tags or "heavy" in tags) and tags & MOVE_TAGS and "loop" not in tags and dur <= 3.0:
        return "combat", "tags: fast/heavy strike with a direction, one-shot <= 3 s"
    if "loop" in tags and dur >= 4.0:
        return "dance_emote", "tags: long loop"
    return "other", "no rule"


def regroup():
    path = os.path.join(OUT, "labels.jsonl")
    labels = [json.loads(s) for s in open(path, encoding="utf-8")]
    base = {}
    for l in labels:
        if l["augmentation"] is None:
            l["group"], l["group_rule"] = group_of(l)
            base[l["id"]] = l
    for l in labels:
        if l["augmentation"] is not None:
            l["group"], l["group_rule"] = base[l["source_id"]]["group"], base[l["source_id"]]["group_rule"]
    with open(path, "w", encoding="utf-8") as fh:
        for l in labels:
            fh.write(json.dumps(l, ensure_ascii=False) + "\n")
    origs = list(base.values())
    before, after, moved, rules = {}, {}, {}, {}
    for l in origs:
        b = KIND_GROUP.get(l["kind"], "other")
        before[b] = before.get(b, 0) + l["frames"]
        after[l["group"]] = after.get(l["group"], 0) + l["frames"]
        if l["kind"] == "other":
            moved[l["group"]] = moved.get(l["group"], 0) + 1
            rules[l["group_rule"]] = rules.get(l["group_rule"], 0) + 1
    game = {}
    for l in origs:
        if l["licence"] == "game":
            game[l["group"]] = game.get(l["group"], 0) + l["frames"]
    mins = lambda d: {k: round(v / FPS / 60, 1) for k, v in sorted(d.items(), key=lambda kv: -kv[1])}  # noqa: E731
    out = {"minutes_before": mins(before), "minutes_after": mins(after), "game_safe_minutes_after": mins(game),
           "other_reassigned_clips": moved, "rules_used": rules}
    json.dump(out, open(os.path.join(OUT, "groups.json"), "w", encoding="utf-8"), indent=1)
    return out


def main(argv):
    if argv[:1] == ["regroup"]:
        r = regroup()
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"groups (minutes) before {r['minutes_before']} -> after {r['minutes_after']}; "
                          f"game-safe {r['game_safe_minutes_after']}; 'other' reassigned {r['other_reassigned_clips']}", "next_action": "-",
                          "rules": r["rules_used"]}, ensure_ascii=False))
        return 0
    if argv[:1] != ["build"]:
        print(__doc__)
        return 2
    aug = int(argv[argv.index("--aug") + 1]) if "--aug" in argv else 2
    seed = int(argv[argv.index("--seed") + 1]) if "--seed" in argv else 0
    r = build(aug, seed)
    print(json.dumps({"schema": 1, "status": "pass",
                      "summary": f"R6 dataset: {r['clips']} clips / {r['frames']} frames ({r['minutes']} min) at 60 fps + {r['augmented_clips']} augmented "
                                 f"-> {r['total_clips']} clips / {r['total_frames']} frames ({r['total_minutes']} min); skipped {len(r['skipped'])}",
                      "next_action": "read _artifacts/r6data/report.json"}))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
