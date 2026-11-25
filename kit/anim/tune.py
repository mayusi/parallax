"""tune.py — AUTO-TUNE an authored move's NUMBERS to the learned rulebook (kit/anim/craft.py), keeping the author's poses
(2026-10-12: hand-chasing coupled cycle numbers - stride, arm amplitudes, timing - took many rebuilds per move).

    from tune import tune
    best, log = tune(build, x0, bounds, group="run", name="GsRun", budget=24)

`build(x)` -> a pose spec (the author's move with the numbers x); each candidate is baked on the owner's rig
(`kit anim <name>`), measured, and scored: for every rulebook feature of the group, the distance OUTSIDE the loved
p20-p80 band (in band widths; separating rules count double) + a small pull toward the loved median; a candidate whose
motion gates fail (pops, sliding feet, loop seams) scores +10. A (1+1) evolution strategy with a shrinking step,
started from the author's own numbers - so the result is the author's move, nudged into the loved band."""
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import craft as CR  # noqa: E402


def score(clip_path, group):
    rules = json.load(open(CR.RULES, encoding="utf-8"))["groups"][group]
    f = CR.features(json.load(open(clip_path, encoding="utf-8")))
    loss, off = 0.0, []
    for k, r in rules.items():
        if k not in f or k in CR.SKIP_AUTHORED:
            continue
        lo, hi, med = r["loved_p20"], r["loved_p80"], r["loved_median"]
        w = max(hi - lo, 1e-6)
        out = max(0.0, lo - f[k], f[k] - hi) / w
        weight = 2.0 if (r.get("separation") or 0) >= 0.5 else 1.0
        loss += weight * out + 0.1 * abs(f[k] - med) / w
        if out > 0:
            off.append(k)
    return loss, off, f


def evaluate(build, x, name, group, taste_weight=0.0, post=None):
    spec = build(x)
    path = os.path.join("assets", "animations", f"{name}.pose.json")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        json.dump(spec, fh, indent=1)
        fh.write(chr(10))
    p = subprocess.run(["lune", "run", "kit", "anim", name], capture_output=True, text=True, encoding="utf-8", errors="replace")
    gates_fail = any(line.startswith("[FAIL]") and name in line for line in p.stdout.splitlines())
    clip = os.path.join("build", "animations", f"{name}.clip.json")
    if post:                                                  # e.g. the learned polish, judged as it will ship
        c = json.load(open(clip, encoding="utf-8"))
        post(c)
        clip = os.path.join("build", "animations", f"{name}.tune.clip.json")
        json.dump(c, open(clip, "w", encoding="utf-8"))
    loss, off, f = score(clip, group)
    if taste_weight:
        p_, _, _ = CR.taste(json.load(open(clip, encoding="utf-8")))
        loss += taste_weight * (1.0 - p_) * 10
    return loss + (10.0 if gates_fail else 0.0), off, gates_fail


def tune(build, x0, bounds, group, name, budget=24, step=0.25, seed=7, taste_weight=0.0, post=None):
    rng = random.Random(seed)
    clamp = lambda x: [min(max(v, lo), hi) for v, (lo, hi) in zip(x, bounds)]
    best = clamp(list(x0))
    bl, boff, bg = evaluate(build, best, name, group, taste_weight, post)
    log = [(round(bl, 3), list(best), boff, bg)]
    for i in range(budget):
        cand = clamp([v + rng.gauss(0, step * (hi - lo)) for v, (lo, hi) in zip(best, bounds)])
        l, off, g = evaluate(build, cand, name, group, taste_weight, post)
        log.append((round(l, 3), cand, off, g))
        if l < bl:
            best, bl, boff, bg = cand, l, off, g
            step = min(step * 1.3, 0.4)
        else:
            step = max(step * 0.85, 0.03)
    evaluate(build, best, name, group, taste_weight, post)   # leave the best one built
    return best, bl, boff, log
