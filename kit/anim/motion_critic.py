"""motion_critic.py — "does this look HUMAN-MADE?" (owner-approved "animate anything on R6" plan, step 6, 2026-10-12).

The old taste model (craft.taste) only ever saw human clips, so it could not judge machine-made ones: it scored my
rejected moves 0.80. This critic is trained on BOTH sides:
  human    - every loved / ok native R6 clip of the library (owner_picks.json)
  machine  - every move the pipeline made that the owner rejected (assets/animations/verdicts.json: horrible / bad, and
             their siblings of the same families: Craft*, GSCraft*, Claymore*, Gs M/Guard/Run, RigRun*), plus
             MACHINE-IZED copies of human clips: the same motion re-made the way a keyframing bot makes it (a few keys,
             eased in between) - the failure the owner keeps pointing at, now a counter-example by construction
Features: craft.features' motion numbers + curve texture (how often each joint's acceleration changes sign, how much
of the motion lives in fine detail, how many joints move in lockstep).

    python kit/anim/motion_critic.py train      -> _artifacts/r6lib/critic.json + a held-out check line
    python kit/anim/motion_critic.py score <clip.json> [...]  -> P(human-made) per clip"""
import copy
import glob
import json
import os
import pickle
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import clip as C  # noqa: E402
import craft as CR  # noqa: E402
import derive as D  # noqa: E402

LIB = os.path.join("_artifacts", "r6lib")
MODEL = os.path.join(LIB, "critic.json")         # the check numbers
MODEL_PKL = os.path.join(LIB, "critic.pkl")      # the trained trees (written by train() here, never downloaded)
# every move the pipeline itself made (owner 2026-10-12: "EVERYTHING UVE MADE SO FAR IS TRASH"), with their polished /
# preview variants; .src files are the loved sources some were derived from and stay out
MACHINE = re.compile(r"^(Craft|GSCraft|Claymore|RigRun|GsM[123]|GsGuardIdle|GsRun|Brawler)")
BASE_FEATS = ["accel_s", "decel_s", "asym", "hold_frac", "holds", "jerk", "overshoot", "arc", "turn_range", "lean_max",
              "arm_out", "head_lead", "lag_torso_arm", "lag_arm_head", "dead_still", "lockstep", "slide_R", "slide_L"]
TEX_FEATS = ["acc_flips", "detail", "sync"]
FEATS = BASE_FEATS + TEX_FEATS


def to60(c):
    if int(round(float(c.get("fps") or 30))) != 60:
        c = copy.deepcopy(c)
        D.op_retime(c, duration=float(c["times"][-1]), fps=60)
    return c


def texture(c):
    """curve texture from the joint rotations (60 fps): acc_flips = how often a joint's angular acceleration changes
    sign (hand-made dense curves keep adjusting; a few eased keys do not), detail = the share of angular speed that a
    0.15 s smoothing removes, sync = how many joints start moving at the same frame (lockstep onsets)"""
    flips, detail, onsets = [], [], []
    for j, tr in c["joints"].items():
        F = np.asarray(tr["frames"], float)
        if len(F) < 8:
            continue
        ang = np.array([C.quat_angle(F[i][:4], F[i + 1][:4]) for i in range(len(F) - 1)]) * 60
        if ang.max() < 5:
            continue
        acc = np.diff(ang)
        sig = np.sign(acc[np.abs(acc) > 2])
        flips.append(float(np.mean(sig[1:] != sig[:-1])) if len(sig) > 2 else 0.0)
        sm = np.convolve(ang, np.ones(9) / 9, mode="same")
        detail.append(float(np.sum(np.abs(ang - sm)) / max(np.sum(ang), 1e-6)))
        onsets.append(int(np.argmax(ang > 0.3 * ang.max())))
    if not flips:
        return {"acc_flips": 0.0, "detail": 0.0, "sync": 1.0}
    o = np.array(onsets)
    sync = float(np.mean([np.mean(np.abs(o - x) <= 1) for x in o]))
    return {"acc_flips": float(np.mean(flips)), "detail": float(np.mean(detail)), "sync": sync}


def featurize(c, rig):
    c = to60(c)
    f = CR.features(c, rig) or {}
    f.update(texture(c))
    return [f.get(k, np.nan) for k in FEATS]


def machineize(c, rng):
    """the same motion re-made the way a keyframing bot makes it: 4-8 key frames kept, eased curves between them"""
    c = to60(copy.deepcopy(c))
    n = len(c["times"])
    k = int(rng.integers(4, 9))
    keys = sorted(set([0, n - 1] + list(rng.choice(np.arange(1, n - 1), size=min(k, n - 2), replace=False))))
    for j in c["joints"]:
        F = np.asarray(c["joints"][j]["frames"], float)
        out = []
        for a, b in zip(keys, keys[1:]):
            for i in range(a, b):
                u = (i - a) / (b - a)
                w = u * u * (3 - 2 * u)
                out.append(np.concatenate([C.slerp(F[a][:4], F[b][:4], w), F[a][4:7] * (1 - w) + F[b][4:7] * w]))
        out.append(F[-1])
        D.set_frames(c, j, out)
    return c


def dataset(rig, synth_per=1, seed=7):
    rng = np.random.default_rng(seed)
    picks = json.load(open(os.path.join("assets", "animations", "library", "owner_picks.json"), encoding="utf-8"))["picks"]
    X, y, src = [], [], []
    for r in picks:
        if r["verdict"] not in ("love", "ok") or r["laggy"] or r["kind"] == "dance":
            continue
        p = os.path.join(LIB, "clips", f"{r['id']}.clip.json")
        if not os.path.isfile(p):
            continue
        c = json.load(open(p, encoding="utf-8"))
        if len(c["times"]) < 8 or "Torso" not in c["joints"]:
            continue
        X.append(featurize(c, rig))
        y.append(1)
        src.append(("human", r["id"]))
        for s in range(synth_per):
            X.append(featurize(machineize(c, rng), rig))
            y.append(0)
            src.append(("synth", r["id"]))
    for p in sorted(glob.glob(os.path.join("build", "animations", "*.clip.json"))):
        name = os.path.basename(p)[: -len(".clip.json")]
        if name.endswith(".src") or not MACHINE.match(name):
            continue
        c = json.load(open(p, encoding="utf-8"))
        if c.get("rig") != "R6" or len(c["times"]) < 8:
            continue
        X.append(featurize(c, rig))
        y.append(0)
        src.append(("made", name.split(".")[0]))
    return np.array(X, float), np.array(y, float), src


def fit(X, y, w=None):
    """gradient-boosted trees (sklearn, missing numbers allowed), classes balanced; the logistic below was the first
    version: held-out 69% / 75% / 67% (human / machine-ized / owner-rejected), linear in the features"""
    from sklearn.ensemble import HistGradientBoostingClassifier
    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=8,
                                       l2_regularization=1.0, class_weight="balanced", random_state=0)
    m.fit(X, y, sample_weight=w)
    return m


def predict(m, X):
    return m.predict_proba(X)[:, 1]


def fit_logistic(X, y, l2=3.0, it=600):
    med = np.nanmedian(X, 0)
    sc = np.maximum(np.nanpercentile(X, 75, 0) - np.nanpercentile(X, 25, 0), 1e-6)
    Z = np.clip((np.where(np.isnan(X), med, X) - med) / sc, -4, 4)
    wpos = 0.5 / max(y.mean(), 1e-6)
    wneg = 0.5 / max(1 - y.mean(), 1e-6)
    sw = np.where(y > 0.5, wpos, wneg)
    w, b = np.zeros(Z.shape[1]), 0.0
    for _ in range(it):
        pr = 1 / (1 + np.exp(-(Z @ w + b)))
        g = sw * (pr - y)
        w -= 0.2 * (Z.T @ g / len(y) + l2 * w / len(y))
        b -= 0.2 * float(np.mean(g))
    return {"w": w.tolist(), "b": b, "med": med.tolist(), "sc": sc.tolist(), "feats": FEATS}


def predict_logistic(m, X):
    med, sc = np.asarray(m["med"]), np.asarray(m["sc"])
    Z = np.clip((np.where(np.isnan(X), med, X) - med) / sc, -4, 4)
    return 1 / (1 + np.exp(-(Z @ np.asarray(m["w"]) + m["b"])))


MADE_WEIGHT = 3.0     # the owner-rejected moves count 3x: 3-fold check 2026-10-12, made caught 71% -> 76%, humans 78% -> 76%


def family(name):
    """GsM1, GsM1Polish, GsM1P, BrawlerM2v3 ... -> one family (held out together)"""
    return re.sub(r"(Polish|P|Hold|v\d+|_.*|\d+[a-z]?)$", "", name)


def train(folds=3):
    rig = C.load_rig("r6")
    X, y, src = dataset(rig)
    w = np.where(np.array([s[0] == "made" for s in src]), MADE_WEIGHT, 1.0)
    fams = sorted({family(s[1]) for s in src if s[0] == "made"})
    humans = [s[1] for s in src if s[0] == "human"]
    kinds = {k: [] for k in ("human", "synth", "made")}
    for k in range(folds):
        # k-fold check: a held-out human clip leaves WITH its machine-ized twin, a made move with its whole family
        out_ids = {h for n, h in enumerate(humans) if n % folds == k}
        hold = np.array([(s[0] != "made" and s[1] in out_ids) or (s[0] == "made" and fams.index(family(s[1])) % folds == k) for s in src])
        m = fit(X[~hold], y[~hold], w[~hold])
        for pi, i in zip(predict(m, X[hold]), np.where(hold)[0]):
            kinds[src[i][0]].append((pi > 0.5) == (src[i][0] == "human"))
    check = {k: (round(float(np.mean(v)), 2), len(v)) for k, v in kinds.items()}
    m = fit(X, y, w)                                  # the shipped model sees everything
    info = {"check": check, "counts": {k: sum(1 for s in src if s[0] == k) for k in ("human", "synth", "made")}, "feats": FEATS,
            "made_weight": MADE_WEIGHT, "folds": folds}
    with open(MODEL_PKL, "wb") as fh:
        pickle.dump(m, fh)
    json.dump(info, open(MODEL, "w", encoding="utf-8"), indent=1)
    return info


_M = None


def score(c, rig=None):
    global _M
    if _M is None:
        with open(MODEL_PKL, "rb") as fh:
            _M = pickle.load(fh)
    return float(predict(_M, np.array([featurize(c, rig or C.load_rig("r6"))], float))[0])


def main(argv):
    if argv[:1] == ["train"]:
        m = train()
        ck = m["check"]
        print(json.dumps({"schema": 1, "status": "pass",
                          "summary": f"critic trained on {m['counts']}; k-fold held out: human called human {ck['human'][0]:.0%} (n={ck['human'][1]}), machine-ized called machine {ck['synth'][0]:.0%} (n={ck['synth'][1]}), owner-rejected pipeline moves called machine {ck['made'][0]:.0%} (n={ck['made'][1]})",
                          "next_action": "python kit/anim/motion_critic.py score <clip.json>"}))
        return 0
    if argv[:1] == ["score"]:
        rig = C.load_rig("r6")
        res = []
        for p in argv[1:]:
            v = score(json.load(open(p, encoding="utf-8")), rig)
            res.append((p, round(v, 2)))
            print(f"{v:.2f}  {p}")
        low = [p for p, v in res if v < 0.5]
        print(json.dumps({"schema": 1, "status": "pass" if not low else "warn",
                          "summary": f"P(human-made): {', '.join(f'{os.path.basename(p)} {v}' for p, v in res)}",
                          "next_action": "below 0.5 reads machine-made: rebuild it from real pieces (kit anim compose)" if low else "-"}))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")       # clip names carry emoji; a Windows console codec would crash
    sys.exit(main(sys.argv[1:]))
