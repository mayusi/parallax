"""craft.py — WHAT MAKES GOOD R6 ANIMATION, measured from the owner's rated library (owner 2026-10-12: "use the catalog
as DATA - analyze it fully - and upgrade the pipeline so what you author comes out good").

    python kit/anim/craft.py features          -> _artifacts/r6lib/craft_features.json (every rated clip measured)
    python kit/anim/craft.py rulebook          -> assets/animations/library/craft_rulebook.json (+ a readable .md)
    python kit/anim/craft.py critic <clip.json> [--kind attack]   -> how a clip sits against the loved / bad ranges

FEATURES (one clip, R6, world space from kit/anim/clip.py's FK; "hands" = each arm's end, "feet" = each leg's end):
  timing    duration, wind (the wind-up extreme), strike (fastest hand), follow (the first stop after), wind_frac,
            recovery_frac (after follow / duration)
  spacing   peak hand speed; accel_s (10% -> peak), decel_s (peak -> 10%); asym (decel/accel); hold_frac (time under
            15% of peak); holds (count of >= 3-frame holds); overshoot (studs a hand passes its final rest pose and comes
            back); jerk (largest speed change per 1/60 s / peak)
  overlap   lag_torso_arm / lag_arm_head (frames the second part's speed peak trails the first's)
  arcs      arc (hand path length / chord over wind -> follow: 1 = straight, more = curved)
  footwork  step (largest foot travel, studs), step_t (foot speed peak - strike, s: < 0 steps before the hit), lift,
            width_guard / width_strike (stance), hip_drop (lowest torso vs guard), weight_shift (torso over the feet's
            midpoint, forward, at the strike)
  pose      turn_range, lean_max, arm_out (the striking arm's angle from hanging, deg, at the strike), head_lead (head
            yaw - torso yaw at the strike, deg)
  density   key_gap_med / key_gap_max (s), linear_share
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import pose_bank as PB  # noqa: E402

LIB = os.path.join("_artifacts", "r6lib")
PICKS = os.path.join("assets", "animations", "library", "owner_picks.json")
RULES = os.path.join("assets", "animations", "library", "craft_rulebook.json")
GROUPS = {"attack": ("attack", "m1/combo", "ability"), "dash": ("dash",), "idle": ("idle",), "run": ("run",), "walk": ("walk",),
          "reaction": ("reaction", "defence"), "jump": ("jump",)}
DOWN = np.array([0.0, -1.0, 0.0])


def ends(W, part):
    return np.array([np.asarray(w[part])[:3, :3] @ DOWN + np.asarray(w[part])[:3, 3] for w in W])


def speed(P, fps):
    v = np.linalg.norm(np.diff(P, axis=0), axis=1) * fps
    return np.concatenate([v[:1], v])


def yaw(m):
    f = np.asarray(m)[:3, :3] @ np.array([0.0, 0.0, -1.0])
    return math.degrees(math.atan2(-f[0], -f[2]))


def features(c, rig=None):
    rig = rig or C.load_rig("r6")
    W = C.world_frames(c, rig)
    fps = float(c.get("fps") or 30)
    n = len(W)
    if n < 4 or "Torso" not in W[0]:
        return None
    dur = float(c["times"][-1])
    f = {"duration": round(dur, 3), "fps": fps}
    arms = [p for p in ("Right Arm", "Left Arm") if p in W[0]]
    H = {p: ends(W, p) for p in arms}
    S = {p: speed(H[p], fps) for p in arms}
    hs = np.max([S[p] for p in arms], axis=0) if arms else np.zeros(n)
    striker = max(arms, key=lambda p: S[p].max()) if arms else None
    k = int(np.argmax(hs))
    peak = float(hs[k])
    f["peak"] = round(peak, 2)
    _, ph = PB.phases(c, rig)
    wind, follow = (ph["wind"], ph["follow"]) if ph else (0, n - 1)
    f.update({"wind_s": round(wind / fps, 3), "strike_s": round(k / fps, 3), "follow_s": round(follow / fps, 3),
              "wind_frac": round(wind / max(n - 1, 1), 3), "recovery_frac": round((n - 1 - follow) / max(n - 1, 1), 3)})
    if peak > 1e-6:
        lo = 0.1 * peak
        a = k
        while a > 0 and hs[a - 1] > lo:
            a -= 1
        b = k
        while b < n - 1 and hs[b + 1] > lo:
            b += 1
        f["accel_s"], f["decel_s"] = round((k - a) / fps, 3), round((b - k) / fps, 3)
        f["asym"] = round((b - k + 1) / (k - a + 1), 3)
        still = hs < 0.15 * peak
        f["hold_frac"] = round(float(still.mean()), 3)
        runs, cur = [], 0
        for s in still:
            cur = cur + 1 if s else 0
            if cur == 3:
                runs.append(1)
        f["holds"] = len(runs)
        f["jerk"] = round(float(np.abs(np.diff(hs)).max() / peak * (fps / 60)), 3)
    if striker:
        P = H[striker]
        rest = P[-1]
        dist = np.linalg.norm(P[k:] - rest, axis=1)
        f["overshoot"] = round(float(max(0.0, dist.max() - dist[0])) if len(dist) else 0.0, 3)
        seg = P[wind:follow + 1]
        if len(seg) > 2:
            path = float(np.linalg.norm(np.diff(seg, axis=0), axis=1).sum())
            chord = float(np.linalg.norm(seg[-1] - seg[0]))
            f["arc"] = round(path / max(chord, 0.05), 3)
    T = np.array([np.asarray(w["Torso"])[:3, 3] for w in W])
    ty = np.degrees(np.unwrap(np.radians([yaw(w["Torso"]) for w in W])))
    tsp = np.abs(np.diff(ty, prepend=ty[0])) * fps
    f["turn_range"] = round(float(ty.max() - ty.min()), 1)
    if striker:
        f["lag_torso_arm"] = int(np.argmax(S[striker]) - np.argmax(tsp))
    if "Head" in W[0]:
        hy = np.degrees(np.unwrap(np.radians([yaw(w["Head"]) for w in W])))
        hsp = np.abs(np.diff(hy, prepend=hy[0])) * fps
        f["lag_arm_head"] = int(np.argmax(hsp) - (np.argmax(S[striker]) if striker else 0))
        f["head_lead"] = round(float(((hy[k] - ty[k]) + 180) % 360 - 180), 1)
    lean = []
    for w in W:
        fw = np.asarray(w["Torso"])[:3, :3] @ np.array([0.0, 0.0, -1.0])
        lean.append(math.degrees(math.asin(max(-1.0, min(1.0, -fw[1])))))
    f["lean_max"] = round(float(max(lean)), 1)
    if striker:
        R = np.asarray(W[k][striker])[:3, :3]
        Rt = np.asarray(W[k]["Torso"])[:3, :3]
        d = Rt.T @ (R @ DOWN)
        f["arm_out"] = round(math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(d, DOWN)))))), 1)
    legs = [p for p in ("Right Leg", "Left Leg") if p in W[0]]
    if len(legs) == 2:
        Fr, Fl = ends(W, "Right Leg"), ends(W, "Left Leg")
        trav = [np.linalg.norm(F[:, [0, 2]] - F[0, [0, 2]], axis=1).max() for F in (Fr, Fl)]
        f["step"] = round(float(max(trav)), 3)
        mover = (Fr, Fl)[int(np.argmax(trav))]
        fs = speed(mover, fps)
        f["step_t"] = round((int(np.argmax(fs)) - k) / fps, 3)
        f["lift"] = round(float(max(Fr[:, 1].max() - Fr[:, 1].min(), Fl[:, 1].max() - Fl[:, 1].min())), 3)
        width = np.linalg.norm((Fr - Fl)[:, [0, 2]], axis=1)
        f["width_guard"], f["width_strike"] = round(float(width[0]), 3), round(float(width[k]), 3)
        mid = (Fr[k] + Fl[k]) / 2
        fw = np.asarray(W[k]["Torso"])[:3, :3] @ np.array([0.0, 0.0, -1.0])
        f["weight_shift"] = round(float(np.dot((T[k] - mid)[[0, 2]], fw[[0, 2]] / max(np.linalg.norm(fw[[0, 2]]), 1e-6))), 3)
    f["hip_drop"] = round(float(T[0, 1] - T[:, 1].min()), 3)
    # the R6 LANGUAGE features (found 2026-10-12 as the gap between every rejected authored move and the loved attacks;
    # adding them lifted the taste model 77% -> 81% on attacks): arm slides, never dead still, parts not in lockstep
    J = c["joints"]
    for j in ("Right Arm", "Left Arm"):
        if j in J:
            Pp = np.array([fr[4:7] for fr in J[j]["frames"]])
            f[f"slide_{'R' if j.startswith('Right') else 'L'}"] = round(float(np.linalg.norm(Pp - Pp[0], axis=1).max()), 3)
    qs = {j: np.array([fr[:4] for fr in J[j]["frames"]]) for j in J}
    angs = {j: np.degrees(2 * np.arccos(np.abs(np.sum(Q[1:] * Q[:-1], axis=1)).clip(0, 1))) * fps for j, Q in qs.items() if len(Q) > 2}
    if angs:
        f["dead_still"] = round(float(np.mean(np.all(np.array([v < 2 for v in angs.values()]), axis=0))), 3)
        pairs = [("Torso", "Right Arm"), ("Right Arm", "Left Arm"), ("Torso", "Head"), ("Right Arm", "Head")]
        cs = [np.corrcoef(angs[a], angs[b])[0, 1] for a, b in pairs if a in angs and b in angs and angs[a].std() > 1e-6 and angs[b].std() > 1e-6]
        if cs:
            f["lockstep"] = round(float(np.mean(cs)), 3)
    keys = [kk for j in c["joints"].values() for kk in (j.get("keys") or [])]
    if keys:
        ts = sorted({round(float(kk["t"]), 4) for kk in keys})
        gaps = [b2 - a2 for a2, b2 in zip(ts, ts[1:])] or [0]
        f["key_gap_med"], f["key_gap_max"] = round(float(np.median(gaps)), 4), round(float(max(gaps)), 4)
        f["linear_share"] = round(sum(1 for kk in keys if kk.get("ease", "Linear") == "Linear") / len(keys), 3)
    return f


TASTE_FEATS = ["accel_s", "decel_s", "asym", "hold_frac", "holds", "jerk", "overshoot", "arc", "turn_range", "lean_max", "arm_out",
               "head_lead", "lag_torso_arm", "lag_arm_head", "step", "step_t", "lift", "width_guard", "width_strike",
               "weight_shift", "hip_drop", "wind_frac", "recovery_frac", "duration", "peak", "slide_R", "slide_L", "dead_still", "lockstep"]


def shape_vector(c, rig=None):
    """each limb's direction in the torso's frame + the lean, at wind-up / strike / follow (the pose's silhouette)"""
    rig = rig or C.load_rig("r6")
    W, ph = PB.phases(c, rig)
    if not ph:
        return None
    v = []
    for p in ("wind", "strike", "follow"):
        w = W[ph[p]]
        Rt = np.asarray(w["Torso"])[:3, :3]
        for part in ("Right Arm", "Left Arm", "Right Leg", "Left Leg"):
            v += list(Rt.T @ (np.asarray(w[part])[:3, :3] @ DOWN)) if part in w else [0.0, -1.0, 0.0]
        fw = Rt @ np.array([0.0, 0.0, -1.0])
        v.append(float(-fw[1]))
    return np.array(v)


_TASTE_CACHE = {}


def taste(c, group="attack", l2=5.0):
    """P(the owner LOVES it): logistic regression on the rated library (motion features + pose shape), trained here on
    every loved / bad / laggy clip of the group. Validated 2026-10-12 by leave-one-out: attacks 77% vs 60% guessing
    (runs / walks / idles: no better than their simpler checks - use it for attacks only)"""
    rig = C.load_rig("r6")
    if (group, l2) in _TASTE_CACHE:
        w, b, med, sc = _TASTE_CACHE[(group, l2)]
        norm = lambda m: np.clip((np.where(np.isnan(m), med, m) - med) / sc, -4, 4)
        f = features(c, rig)
        fx = norm(np.array([[f.get(k, np.nan) for k in TASTE_FEATS]], float))[0]
        x = np.concatenate([fx, shape_vector(c, rig)])
        contrib = sorted(zip(TASTE_FEATS, fx * w[:len(TASTE_FEATS)]), key=lambda kv: kv[1])
        return float(1 / (1 + np.exp(-(x @ w + b)))), contrib[:3], contrib[-3:]
    rows = [r for r in json.load(open(os.path.join(LIB, "craft_features.json"), encoding="utf-8"))
            if r["group"] == group and r["label"] in ("love", "bad", "laggy")]
    M, S, y = [], [], []
    for r in rows:
        sv = shape_vector(json.load(open(os.path.join(LIB, "clips", f"{r['id']}.clip.json"), encoding="utf-8")), rig)
        if sv is None:
            continue
        M.append([r["f"].get(k, np.nan) for k in TASTE_FEATS])
        S.append(sv)
        y.append(1.0 if r["label"] == "love" else 0.0)
    M = np.array(M, float)
    med = np.nanmedian(M, 0)
    sc = np.maximum(np.nanpercentile(M, 75, 0) - np.nanpercentile(M, 25, 0), 1e-6)
    norm = lambda m: np.clip((np.where(np.isnan(m), med, m) - med) / sc, -4, 4)
    X = np.hstack([norm(M), np.array(S)])
    y = np.array(y)
    w, b = np.zeros(X.shape[1]), 0.0
    for _ in range(400):
        pr = 1 / (1 + np.exp(-(X @ w + b)))
        w -= 0.1 * (X.T @ (pr - y) / len(y) + l2 * w / len(y))
        b -= 0.1 * float(np.mean(pr - y))
    _TASTE_CACHE[(group, l2)] = (w, b, med, sc)
    f = features(c, rig)
    x = np.concatenate([norm(np.array([[f.get(k, np.nan) for k in TASTE_FEATS]], float))[0], shape_vector(c, rig)])
    contrib = sorted(zip(TASTE_FEATS, (norm(np.array([[f.get(k, np.nan) for k in TASTE_FEATS]], float))[0] * w[:len(TASTE_FEATS)])),
                     key=lambda kv: kv[1])
    return float(1 / (1 + np.exp(-(x @ w + b)))), contrib[:3], contrib[-3:]


_ENSEMBLE = {}


def taste_range(c, group="attack", l2=5.0, n=25, seed=1):
    """P(loved) with its UNCERTAINTY: n models trained on bootstrap resamples of the owner's ratings -> (mean, p10, p90).
    Two versions of a move whose ranges overlap are a TIE the owner's eye decides (2026-10-12: a 0.3 deg drift swung the
    single model 0.80 -> 0.60 - its fine-scale differences are noise)"""
    rig = C.load_rig("r6")
    if (group, l2) not in _ENSEMBLE:
        taste(c, group, l2)                                      # fills the normaliser in _TASTE_CACHE
        rows = [r for r in json.load(open(os.path.join(LIB, "craft_features.json"), encoding="utf-8"))
                if r["group"] == group and r["label"] in ("love", "bad", "laggy")]
        M, S, y = [], [], []
        for r in rows:
            sv = shape_vector(json.load(open(os.path.join(LIB, "clips", f"{r['id']}.clip.json"), encoding="utf-8")), rig)
            if sv is None:
                continue
            M.append([r["f"].get(k, np.nan) for k in TASTE_FEATS])
            S.append(sv)
            y.append(1.0 if r["label"] == "love" else 0.0)
        _, _, med, sc = _TASTE_CACHE[(group, l2)]
        norm = lambda m: np.clip((np.where(np.isnan(m), med, m) - med) / sc, -4, 4)
        X, y = np.hstack([norm(np.array(M, float)), np.array(S)]), np.array(y)
        rng = np.random.default_rng(seed)
        models = []
        for _ in range(n):
            idx = rng.integers(0, len(y), len(y))
            w, b = np.zeros(X.shape[1]), 0.0
            for _ in range(300):
                pr = 1 / (1 + np.exp(-(X[idx] @ w + b)))
                w -= 0.1 * (X[idx].T @ (pr - y[idx]) / len(idx) + l2 * w / len(idx))
                b -= 0.1 * float(np.mean(pr - y[idx]))
            models.append((w, b))
        _ENSEMBLE[(group, l2)] = (models, norm)
    models, norm = _ENSEMBLE[(group, l2)]
    f = features(c, rig)
    x = np.concatenate([norm(np.array([[f.get(k, np.nan) for k in TASTE_FEATS]], float))[0], shape_vector(c, rig)])
    ps = np.array([1 / (1 + np.exp(-(x @ w + b))) for w, b in models])
    return float(ps.mean()), float(np.percentile(ps, 10)), float(np.percentile(ps, 90))


def group_of(kind):
    for g, ks in GROUPS.items():
        if kind in ks:
            return g
    return None


def build_features():
    rig = C.load_rig("r6")
    picks = json.load(open(PICKS, encoding="utf-8"))["picks"]
    out = []
    for r in picks:
        g = group_of(r.get("kind"))
        if not g or not (r.get("verdict") or r.get("laggy")):
            continue
        p = os.path.join(LIB, "clips", f"{r['id']}.clip.json")
        if not os.path.isfile(p):
            continue
        try:
            f = features(json.load(open(p, encoding="utf-8")), rig)
        except Exception:
            continue
        if f:
            label = "laggy" if r.get("laggy") else r["verdict"]
            out.append({"id": r["id"], "group": g, "label": label, "name": r["name"], "f": f})
    json.dump(out, open(os.path.join(LIB, "craft_features.json"), "w", encoding="utf-8"), indent=0)
    return out


def rulebook(rows):
    """per group and feature: the LOVED range (p20-p80) and median, the BAD/laggy median, and how well the feature
    separates them (|loved median - bad median| / the loved spread) - only features that separate become RULES"""
    book = {}
    for g in GROUPS:
        L = [r["f"] for r in rows if r["group"] == g and r["label"] == "love"]
        Bd = [r["f"] for r in rows if r["group"] == g and r["label"] in ("bad", "laggy")]
        if len(L) < 5:
            continue
        feats = sorted({k for f in L for k in f if isinstance(f[k], (int, float)) and k != "fps"})
        rules = {}
        for k in feats:
            lv = np.array([f[k] for f in L if k in f], float)
            if len(lv) < 5:
                continue
            bv = np.array([f[k] for f in Bd if k in f], float)
            p20, p50, p80 = np.percentile(lv, [20, 50, 80])
            spread = max(p80 - p20, 1e-6)
            sep = float(abs(p50 - np.median(bv)) / spread) if len(bv) >= 3 else None
            rules[k] = {"loved_p20": round(float(p20), 3), "loved_median": round(float(p50), 3), "loved_p80": round(float(p80), 3),
                        "bad_median": round(float(np.median(bv)), 3) if len(bv) else None, "separation": round(sep, 2) if sep is not None else None,
                        "n_loved": int(len(lv)), "n_bad": int(len(bv))}
        book[g] = rules
    return book


SKIP_AUTHORED = ("key_gap_med", "key_gap_max", "linear_share")   # density: the kit bakes every frame, and loved attacks
                                                                     # hold keys for 0.3 s in holds (HQ) - not a rule for authored moves


def pose_check(c, kind_groups=("attack", "m1/combo", "ability"), k=5):
    """MY key poses vs the LOVED bank poses of the same phase: each limb's direction in the torso's frame at wind-up /
    strike / follow; the distance to the k nearest loved poses vs how far loved poses sit from each other, and the
    limb furthest from what loved animators do (with the loved direction to move it toward)"""
    rig = C.load_rig("r6")
    W, ph = PB.phases(c, rig)
    bank = [e for e in PB.load() if e["kind"] in kind_groups and e.get("has_legs")]
    parts = ("Right Arm", "Left Arm", "Right Leg", "Left Leg")
    out = {}
    for phase in ("wind", "strike", "follow"):
        w = W[ph[phase]]
        Rt = np.asarray(w["Torso"])[:3, :3]
        mine = {p: Rt.T @ (np.asarray(w[p])[:3, :3] @ DOWN) for p in parts if p in w}
        cand = []
        for e in bank:
            if e["phase"] != phase:
                continue
            dirs = e.get("dirs")
            if not dirs:
                continue
            d = sum(float(np.linalg.norm(np.array(dirs[p]) - mine[p])) for p in mine if p in dirs)
            cand.append((d, e))
        cand.sort(key=lambda x: x[0])
        near = cand[:k]
        if not near:
            continue
        typical = float(np.median([x[0] for x in cand[: max(k * 4, 20)]]))
        worst = max(mine, key=lambda p: np.mean([np.linalg.norm(np.array(e["dirs"][p]) - mine[p]) for _, e in near if p in e["dirs"]]))
        target = np.mean([e["dirs"][worst] for _, e in near if worst in e["dirs"]], axis=0)
        out[phase] = {"distance": round(near[0][0], 3), "typical": round(typical, 3), "worst_limb": worst,
                      "toward": [round(float(v), 3) for v in target / max(np.linalg.norm(target), 1e-6)],
                      "nearest": [f"{e['name']} ({e['pack'][:24] if e['pack'] else ''})" for _, e in near[:3]]}
    return out


def critic(f, rules):
    """each feature: where the clip sits vs the loved p20-p80 band; a RULE (separation >= 0.5) outside the band is a fix"""
    out = []
    for k, r in rules.items():
        if k not in f or k in SKIP_AUTHORED:
            continue
        v = f[k]
        tol = 0.05 * max(r["loved_p80"] - r["loved_p20"], 1e-6) + 1e-3   # rounding: 0.0167 is 0.017
        inside = r["loved_p20"] - tol <= v <= r["loved_p80"] + tol
        strong = (r.get("separation") or 0) >= 0.5
        out.append({"feature": k, "value": v, "loved": [r["loved_p20"], r["loved_p80"]], "bad_median": r["bad_median"],
                    "ok": inside, "rule": strong})
    fixes = [o for o in out if not o["ok"] and o["rule"]]
    return fixes, out


def main(argv):
    cmd = argv[0] if argv else "rulebook"
    if cmd == "features":
        rows = build_features()
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"craft: {len(rows)} rated clips measured", "next_action": "python kit/anim/craft.py rulebook"}))
        return 0
    if cmd == "rulebook":
        p = os.path.join(LIB, "craft_features.json")
        rows = json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else build_features()
        book = rulebook(rows)
        json.dump({"about": "measured from the owner's rated library by kit/anim/craft.py; loved p20-p80 = the target band; separation = |loved median - bad median| / loved spread (>= 0.5: a rule)",
                   "groups": book}, open(RULES, "w", encoding="utf-8", newline="\n"), indent=1)
        lines = []
        for g, rules in book.items():
            strong = sorted(((k, r) for k, r in rules.items() if (r.get("separation") or 0) >= 0.5), key=lambda kr: -(kr[1]["separation"] or 0))
            lines.append(f"{g}: {rules[next(iter(rules))]['n_loved']} loved / {rules[next(iter(rules))]['n_bad']} bad - rules: "
                         + "; ".join(f"{k} loved {r['loved_p20']}..{r['loved_p80']} (bad {r['bad_median']}, sep {r['separation']})" for k, r in strong[:8]))
        print("\n".join(lines))
        return 0
    if cmd == "taste":
        c = json.load(open(argv[1], encoding="utf-8"))
        p_, worst, best = taste(c)
        print(json.dumps({"schema": 1, "status": "pass" if p_ >= 0.5 else "fail",
                          "summary": f"taste {c.get('name')}: P(owner loves it) = {p_:.2f}; pulling it down: " + ", ".join(k for k, _ in worst)
                                     + "; holding it up: " + ", ".join(k for k, _ in best),
                          "next_action": "show the owner" if p_ >= 0.5 else "work on the features pulling it down", "p": round(p_, 3)}))
        return 0 if p_ >= 0.5 else 1
    if cmd == "critic":
        c = json.load(open(argv[1], encoding="utf-8"))
        g = argv[argv.index("--kind") + 1] if "--kind" in argv else "attack"
        rules = json.load(open(RULES, encoding="utf-8"))["groups"][g]
        fixes, all_ = critic(features(c), rules)
        poses = pose_check(c)
        far = {ph: v for ph, v in poses.items() if v["distance"] > 1.5 * v["typical"]}
        print(json.dumps({"schema": 1, "status": "pass" if not fixes else "fail",
                          "summary": f"critic {c.get('name')} ({g}): " + ("inside the loved band on every rule" if not fixes else
                                     "; ".join(f"{o['feature']} {o['value']} (loved {o['loved'][0]}..{o['loved'][1]}, bad ~{o['bad_median']})" for o in fixes)),
                          "next_action": "none - show the owner" if not fixes else "fix those features, then run the critic again", "checks": all_,
                          "poses": poses, "poses_unlike_loved": far}))
        return 0 if not fixes else 1
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
