"""pose_prior.py — STYLE-BASED POSING for procedural R6 (plan: board/plans/archive/2026-10-13-proc-from-scratch-plan.md, step 4;
Grochow et al. 2004 'Style-based IK' with a Gaussian mixture instead of a GP). Few constraints in ("the left hand
HERE"), a whole natural upper-body pose out, in the loved style. The loved clips are only DATA FOR A DENSITY: no pose is
looked up or copied (the copy floor in proc_gates.py checks the result).
  features   per joint (Torso, Head, Right Arm, Left Arm): the rotation as a rotation vector about that joint's mean
             (12) + the torso's slide (3) + both hand tips in the torso frame (6) = 21. Legs are left to the foot IK.
  data       every 4th frame of the loved, game-licensed, NON-combat clips (+ mirrors): the 'upright' category
  model      a full-covariance Gaussian mixture, K by BIC on a split by clip, a variance floor
  solve      condition on the constraint (a hand tip, tolerance R) -> the MOST LIKELY component only (the mixture mean
             would average two modes into a pose nobody makes) -> its conditional mean + temperature x its conditional
             spread (tau 0.4: not bland) -> the arm re-aimed so the hand lands exactly on the target
  nudge      keep the designed torso, take the head + arms from the prior's rank-th mode given it (combat prior)
    python kit/anim/pose_prior.py build [combat]   -> _artifacts/r6lib/pose_prior[_combat].npz
    from pose_prior import solve, nudge, nll"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import proc_calib as PC  # noqa: E402
import proc_r6 as P  # noqa: E402

OUT = os.path.join("_artifacts", "r6lib", "pose_prior.npz")
OUTS = {"upright": OUT, "combat": os.path.join("_artifacts", "r6lib", "pose_prior_combat.npz")}
UPPER = ["Torso", "Head", "Right Arm", "Left Arm"]
HAND = {"Right Arm": slice(15, 18), "Left Arm": slice(18, 21)}
_M = {}


def _geom():
    import proc_director as DR
    return DR.geom()


def features(pose, mean):
    """pose {joint: [q, p]} -> 21 numbers"""
    f = []
    for k, j in enumerate(UPPER):
        f += list(P.q_log(P.q_mul(np.array(pose[j][:4]), P.q_inv(mean[k]))))
    f += list(pose["Torso"][4:7])
    G = _geom()
    for arm in ("Right Arm", "Left Arm"):
        c0, v = G[arm]
        f += list(c0 + np.array(pose[arm][4:7]) + P.q_rot(np.array(pose[arm][:4]), v))
    return np.array(f, float)


def decode(x, mean, base):
    """21 numbers -> a pose (legs and limb slides from `base`)"""
    import copy
    p = copy.deepcopy(base)
    for k, j in enumerate(UPPER):
        p[j][:4] = list(map(float, P.q_mul(P.q_exp(x[3 * k:3 * k + 3]), mean[k])))
    p["Torso"][4:7] = list(map(float, x[12:15]))
    return p


def build(group="upright"):
    """group 'upright': the loved NON-combat clips (idles, emotes, locomotion); 'combat': the loved combat clips - the
    upper body loved R6 animators give a fighting torso (2026-10-16: the roundhouse extremes were a clump)"""
    from sklearn.mixture import GaussianMixture
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "..", "diagnostics"))
    import derive as D
    import translate_test as TT
    poses, clip_of = [], []
    for lb in TT.labels():
        if lb["owner_verdict"] != "love" or lb["licence"] != "game" or re.search(r"victim|knocked", lb["text"] or "", re.I):
            continue
        if (lb["group"] == "combat") != (group == "combat"):
            continue
        c = TT.loved_clip(lb["id"])[0]
        if not all(j in c["joints"] for j in UPPER):
            continue
        m = D.copy.deepcopy(c)
        D.op_mirror(m)
        for cc in (c, m):
            for f in range(0, len(cc["times"]), 4):
                poses.append({j: cc["joints"][j]["frames"][f] if j in cc["joints"] else [0, 0, 0, 1, 0, 0, 0] for j in P.JOINTS})
                clip_of.append(lb["id"])
    mean = np.array([PC_mean([np.array(p[j][:4]) for p in poses]) for j in UPPER])
    X = np.array([features(p, mean) for p in poses])
    clip_of = np.array(clip_of)
    ids = np.unique(clip_of)
    rs = np.random.default_rng(0)
    held = set(rs.choice(ids, size=max(5, len(ids) // 8), replace=False))
    tr = np.array([c not in held for c in clip_of])
    best = None
    for K in (8, 16, 24, 32):
        g = GaussianMixture(K, covariance_type="full", reg_covar=1e-3, random_state=0, max_iter=300).fit(X[tr])
        bic = g.bic(X[~tr])
        if best is None or bic < best[0]:
            best = (bic, K, g)
    _, K, g = best
    g = GaussianMixture(K, covariance_type="full", reg_covar=1e-3, random_state=0, max_iter=300).fit(X)
    held_ll = g.score_samples(X[~tr])
    np.savez(OUTS[group], mean=mean, w=g.weights_, mu=g.means_, cov=g.covariances_, K=K, n=len(X),
             nll_p50=float(np.percentile(-held_ll, 50)), nll_p90=float(np.percentile(-held_ll, 90)))
    return K, len(X), float(np.percentile(-held_ll, 50)), float(np.percentile(-held_ll, 90))


def PC_mean(Q):
    Q = np.array(Q, float)
    Q = np.where((Q @ Q[0])[:, None] < 0, -Q, Q)
    m = Q.mean(0)
    return m / np.linalg.norm(m)


def load(group="upright"):
    if group not in _M:
        d = np.load(OUTS[group])
        _M[group] = {k: d[k] for k in d.files}
    return _M[group]


def _logpdf(x, mu, cov):
    d = len(x)
    L = np.linalg.cholesky(cov)
    z = np.linalg.solve(L, x - mu)
    return -0.5 * (z @ z) - np.log(np.diag(L)).sum() - 0.5 * d * np.log(2 * np.pi)


def nll(pose, group="upright"):
    m = load(group)
    x = features(pose, m["mean"])
    ll = [np.log(w) + _logpdf(x, mu, cov) for w, mu, cov in zip(m["w"], m["mu"], m["cov"])]
    mx = max(ll)
    return float(-(mx + np.log(np.sum(np.exp(np.array(ll) - mx)))))


def solve(base, arm, hand_target, tol=0.05, tau=0.4, seed=0, keep_hand_exact=True, other_hand=None, other_tol=0.25):
    """the most likely upper-body pose with `arm`'s hand at `hand_target` (torso frame). other_hand: where the OTHER
    hand should be (e.g. hanging at the side) - without it the prior's dominant mode (both hands up in front: dances,
    guards) lifted the other arm too"""
    m = load()
    other = "Left Arm" if arm == "Right Arm" else "Right Arm"
    c_idx = np.arange(21)[HAND[arm]]
    c = np.asarray(hand_target, float)
    tols = [tol] * 3
    if other_hand is not None:
        c_idx = np.r_[c_idx, np.arange(21)[HAND[other]]]
        c = np.r_[c, np.asarray(other_hand, float)]
        tols += [other_tol] * 3
    R_tol = np.diag(np.array(tols) ** 2)
    u_idx = np.array([i for i in range(15)])                 # rotations + torso slide (the hands follow from them)
    best = None
    for k, (w, mu, cov) in enumerate(zip(m["w"], m["mu"], m["cov"])):
        Scc = cov[np.ix_(c_idx, c_idx)] + R_tol
        r = np.log(w) + _logpdf(c, mu[c_idx], Scc)
        if best is None or r > best[0]:
            best = (r, k)
    k = best[1]
    mu, cov = m["mu"][k], m["cov"][k]
    Scc = cov[np.ix_(c_idx, c_idx)] + R_tol
    Suc = cov[np.ix_(u_idx, c_idx)]
    Suu = cov[np.ix_(u_idx, u_idx)]
    gain = Suc @ np.linalg.inv(Scc)
    um = mu[u_idx] + gain @ (c - mu[c_idx])
    uc = Suu - gain @ Suc.T
    rs = np.random.default_rng(seed)
    L = np.linalg.cholesky(uc + 1e-9 * np.eye(len(u_idx)))
    u = um + tau * L @ rs.standard_normal(len(u_idx))
    x = np.zeros(21)
    x[u_idx] = u
    pose = decode(x, m["mean"], base)
    if keep_hand_exact:
        import proc_director as DR
        c0, v = DR.geom()[arm]
        pose = DR.aim(pose, arm, c[:3] - c0 - np.array(pose[arm][4:7]))
    return pose, {"component": int(k), "nll": round(nll(pose), 2)}


def nudge(pose, group="combat", rank=0, tau=0.3, seed=0, tol=0.05):
    """keep the DESIGNED torso (the dossier's mechanics: lean, hip turn) and take the head + arms from the prior: the
    `rank`-th most likely mixture component given that torso, its conditional mean + tau x its spread. rank 0, 1, 2
    = the prior's MODES (different upper bodies loved animators give that torso) - candidates differ by them.
    -> (pose, info). Legs, slides and the torso stay as designed."""
    m = load(group)
    x0 = features(pose, m["mean"])
    c_idx = np.arange(0, 3)
    u_idx = np.arange(3, 12)
    c = x0[c_idx]
    R_tol = np.eye(3) * tol ** 2
    scored = sorted(((np.log(w) + _logpdf(c, mu[c_idx], cov[np.ix_(c_idx, c_idx)] + R_tol), k)
                     for k, (w, mu, cov) in enumerate(zip(m["w"], m["mu"], m["cov"]))), reverse=True)
    k = scored[min(rank, len(scored) - 1)][1]
    mu, cov = m["mu"][k], m["cov"][k]
    Scc = cov[np.ix_(c_idx, c_idx)] + R_tol
    Suc = cov[np.ix_(u_idx, c_idx)]
    gain = Suc @ np.linalg.inv(Scc)
    um = mu[u_idx] + gain @ (c - mu[c_idx])
    uc = cov[np.ix_(u_idx, u_idx)] - gain @ Suc.T
    rs = np.random.default_rng(seed)
    u = um + tau * np.linalg.cholesky(uc + 1e-9 * np.eye(len(u_idx))) @ rs.standard_normal(len(u_idx))
    x = x0.copy()
    x[u_idx] = u
    out = decode(x, m["mean"], pose)
    return out, {"component": int(k), "rank": rank, "nll": round(nll(out, group), 2)}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:3] == ["build", "combat"]:
        K, n, p50, p90 = build("combat")
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"combat pose prior: GMM K={K} on {n} loved combat poses (+mirrors); held-out NLL p50 {p50:.1f}, p90 {p90:.1f} -> {OUTS['combat']}"}))
    elif sys.argv[1:2] == ["build"]:
        K, n, p50, p90 = build()
        print(json.dumps({"schema": 1, "status": "pass", "summary": f"pose prior: GMM K={K} on {n} upright loved poses (+mirrors); held-out NLL p50 {p50:.1f}, p90 {p90:.1f} -> {OUT}"}))
