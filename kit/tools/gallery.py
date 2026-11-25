"""gallery.py — GALLERY TUNING (rung 4 of the learning ladder; proposal 10 of
board/plans/archive/2026-11-08-pipeline-rag-learning-research.md, the owner: "Yes, build it"): the owner's taste over a
generator's SETTINGS, learned only from what the owner did on its pick sheets, and the next sheet chosen with it.

Evidence, and nothing else: a PICK says the picked candidate beat every other candidate shown in its round; an
"All bad" (or a low score naming candidates) says those candidates sat below what the owner wants. An agent's pick or
a model-guessed verdict is never the owner's taste - callers pass only the owner's own.

The model is a Gaussian-process PREFERENCE model (Chu & Ghahramani 2005; Brochu, de Freitas & Ghosh 2010 tuned
procedural animation settings this way): a latent utility f over the settings with a GP prior, a probit likelihood per
comparison (f_pick > f_other) and per rejection (f < 0), fitted by Laplace's method. For any settings it gives the
expected utility (`mean`: likely good) and how unsure it is whether they beat the best candidate shown (`std`: not
learned yet - an informative thing to show).

Settings are dicts. NUMBERS are scaled to about -1..1 (an RBF kernel of length LENGTH); CHOICES are strings such as
"habit:1:out", split at ':' into parts, and each part that differs multiplies the kernel by RHO.

`select` makes a sheet: LIKELY candidates (highest mean) beside LEARN candidates (highest std), spaced apart by the
caller's distance. For animation that distance is the candidates' MOTION, not their sliders. The only renders that
survive (2026-11-08) are 24 candidates of 3 blade rounds (DTDrillSpin r2 + r3, SwordTrickCut r2; 84 pairs; no kick or
reaction): slider distance did not predict how different two of them look (Spearman against SigLIP look distance -0.13
on the middle frame, +0.08 on a 6-frame mean; per round -0.11 to +0.49), joint-rotation distance did, weakly (+0.47 /
+0.36 pooled; per round +0.16 to +0.65, SwordTrickCut the strongest).
"""

import math

import numpy as np
from scipy.special import log_ndtr

LENGTH = 0.6  # the RBF length over a -1..1 setting (a bred child moves sigma 0.25 from its parent)
RHO = 0.5  # each differing part of a choice multiplies the kernel by this
NOISE = 0.5  # the probit noise: how sure one pick or one rejection is (smaller = surer)
JITTER = 1e-6
LOG_SQRT_2PI = 0.5 * math.log(2 * math.pi)


class Space:
    """which keys of a settings dict are NUMBERS (with an optional transform to about -1..1) and which are CHOICES"""

    def __init__(self, numbers, choices=(), transform=None):
        self.numbers = tuple(numbers)
        self.choices = tuple(choices)
        self.transform = dict(transform or {})

    def numeric(self, settings):
        out = np.zeros((len(settings), len(self.numbers)))
        for i, s in enumerate(settings):
            for j, k in enumerate(self.numbers):
                v = s.get(k)
                v = 0.0 if v is None else float(v)
                out[i, j] = self.transform[k](v) if k in self.transform else v
        return out

    def parts(self, s):
        out = []
        for k in self.choices:
            v = s.get(k)
            out.append(tuple(str(v).split(":")) if v is not None else ())
        return out


def kernel(space, a, b):
    """the GP kernel between two lists of settings -> (len(a), len(b)): RBF over the numbers x RHO per differing part"""
    xa, xb = space.numeric(a), space.numeric(b)
    d2 = ((xa[:, None, :] - xb[None, :, :]) ** 2).sum(-1)
    k = np.exp(-d2 / (2 * LENGTH**2))
    if space.choices:
        pa, pb = [space.parts(s) for s in a], [space.parts(s) for s in b]
        diff = np.zeros((len(a), len(b)))
        for c in range(len(space.choices)):
            width = max([len(p[c]) for p in pa + pb] or [0])
            for pos in range(width):
                va = [p[c][pos] if pos < len(p[c]) else None for p in pa]
                vb = [p[c][pos] if pos < len(p[c]) else None for p in pb]
                codes = {v: n for n, v in enumerate(sorted(set(va + vb), key=str))}
                ca = np.asarray([codes[v] for v in va])
                cb = np.asarray([codes[v] for v in vb])
                diff += ca[:, None] != cb[None, :]
        k = k * RHO**diff
    return k


def _ratio(z):
    """phi(z) / Phi(z), stable far into the left tail"""
    return np.exp(-0.5 * z * z - LOG_SQRT_2PI - log_ndtr(z))


class Model:
    """the owner's taste over `space`, from `points` (every candidate shown) and the evidence on them: `prefs` (i, j)
    = point i was picked over point j; `bad` = points rejected; `good` = points the owner scored high"""

    def __init__(self, space, points, prefs=(), bad=(), good=()):
        self.space = space
        self.points = list(points)
        self.prefs = [(int(i), int(j)) for i, j in prefs if i != j]
        self.bad = sorted({int(i) for i in bad})
        self.good = sorted({int(i) for i in good})
        m = len(self.points)
        self.f = np.zeros(m)
        self.alpha = np.zeros(m)
        self.S = self.B = None
        if m == 0 or not self.evidence():
            return
        K = kernel(space, self.points, self.points) + JITTER * np.eye(m)
        f = np.zeros(m)
        psi = self._psi(f, K)
        for _ in range(100):
            g, W = self._grad_hess(f)
            step = K @ np.linalg.solve(np.eye(m) + W @ K, W @ f + g) - f
            t = 1.0
            while True:  # Newton with step halving: the log posterior never goes down
                nf = f + t * step
                npsi = self._psi(nf, K)
                if npsi >= psi - 1e-12 or t < 1e-4:
                    break
                t /= 2
            done = float(np.max(np.abs(nf - f))) < 1e-9
            f, psi = nf, npsi
            if done:
                break
        self.f = f
        self.alpha = np.linalg.solve(K, f)
        _, W = self._grad_hess(f)
        w, v = np.linalg.eigh((W + W.T) / 2)
        self.S = (v * np.sqrt(np.clip(w, 0, None))) @ v.T  # W^(1/2)
        self.B = np.eye(m) + self.S @ K @ self.S

    def evidence(self):
        return len(self.prefs) + len(self.bad) + len(self.good)

    def _loglik(self, f):
        c = 1 / (math.sqrt(2) * NOISE)
        out = sum(float(log_ndtr(c * (f[i] - f[j]))) for i, j in self.prefs)
        out += sum(float(log_ndtr(-f[i] / NOISE)) for i in self.bad)
        out += sum(float(log_ndtr(f[i] / NOISE)) for i in self.good)
        return out

    def _psi(self, f, K):
        return self._loglik(f) - 0.5 * float(f @ np.linalg.solve(K, f))

    def _grad_hess(self, f):
        """the gradient of the log likelihood and W = minus its Hessian (positive semi-definite for the probit)"""
        m = len(f)
        g, W = np.zeros(m), np.zeros((m, m))
        c = 1 / (math.sqrt(2) * NOISE)
        for i, j in self.prefs:
            z = c * (f[i] - f[j])
            r = float(_ratio(z))
            h = c * c * r * (z + r)
            g[i] += c * r
            g[j] -= c * r
            W[i, i] += h
            W[j, j] += h
            W[i, j] -= h
            W[j, i] -= h
        for sign, idx in ((-1.0, self.bad), (1.0, self.good)):
            for i in idx:
                z = sign * f[i] / NOISE
                r = float(_ratio(z))
                g[i] += sign * r / NOISE
                W[i, i] += r * (z + r) / NOISE**2
        return g, W

    def predict(self, settings):
        """-> (mean, std) arrays over `settings`: the expected utility (0 = no opinion) and how unsure it is whether
        those settings beat the BEST candidate shown (0 at the best itself, growing away from what was shown; 1
        everywhere with no evidence). A pick says only which of two was better - the level of the whole surface stays
        unknown - so the useful doubt is the one about beating the best, as preference optimisers measure it"""
        settings = list(settings)
        q = len(settings)
        if not q:
            return np.zeros(0), np.zeros(0)
        if self.S is None:
            return np.zeros(q), np.ones(q)
        ks = kernel(self.space, settings, self.points)
        mean = ks @ self.alpha
        best = int(np.argmax(self.f))
        kb = kernel(self.space, [self.points[best]], self.points)[0]
        kxb = kernel(self.space, settings, [self.points[best]])[:, 0]
        sk, skb = self.S @ ks.T, self.S @ kb
        binv_sk = np.linalg.solve(self.B, sk)
        var_x = 1.0 - np.sum(sk * binv_sk, axis=0)
        var_b = 1.0 - float(skb @ np.linalg.solve(self.B, skb))
        cov = kxb - skb @ binv_sk
        return mean, np.sqrt(np.clip(var_x + var_b - 2 * cov, 1e-12, None))


def spread(items, distance):
    """-> (min, mean) pairwise distance of a sheet (None, None for fewer than two)"""
    ds = [distance(a, b) for i, a in enumerate(items) for b in items[i + 1:]]
    return (round(min(ds), 4), round(float(np.mean(ds)), 4)) if ds else (None, None)


WIDEST_BUDGET = 200000  # search steps for the widest sheet; past them, the widest found so far (never below the turns')


def widest(D, chosen, share, budget=None):
    """the sheet whose CLOSEST pair is the widest the distance matrix `D` allows, with as many items of each share as
    `chosen` holds and chosen[0] kept -> its items in sheet order (chosen[0], then each the farthest from those before
    it). A bisection over the pool's distances, each step a depth-first search for a sheet with every pair at least
    that far apart; past `budget` steps it keeps the widest found so far - `chosen` itself is the floor."""
    m, n = len(D), len(chosen)
    chosen = [int(i) for i in chosen]  # (plain ints: the turns hand numpy ones)
    if n < 3:
        return chosen
    d = [[float(x) for x in row] for row in D]
    first = chosen[0]
    need = {}
    for i in chosen:
        need[share(i)] = need.get(share(i), 0) + 1

    def closest(sub):
        return min(d[a][b] for k, a in enumerate(sub) for b in sub[k + 1:])

    best, best_t = list(chosen), closest(chosen)
    steps = [WIDEST_BUDGET if budget is None else budget]

    class Spent(Exception):
        pass

    def sheet_at(t):
        left = dict(need)
        left[share(first)] -= 1
        pool = [i for i in range(m) if i != first and d[first][i] >= t and left.get(share(i), 0) > 0]
        picked = []

        def dfs(start):
            if not any(left.values()):
                return True
            steps[0] -= 1
            if steps[0] < 0:
                raise Spent
            if len(pool) - start < sum(left.values()):
                return False
            for k in range(start, len(pool)):
                i = pool[k]
                g = share(i)
                if left[g] <= 0 or any(d[i][p] < t for p in picked):
                    continue
                left[g] -= 1
                picked.append(i)
                if dfs(k + 1):
                    return True
                picked.pop()
                left[g] += 1
            return False

        return [first] + picked if dfs(0) else None

    ts = sorted({d[i][j] for i in range(m) for j in range(i + 1, m) if d[i][j] > best_t})
    lo, hi = 0, len(ts) - 1
    try:
        while lo <= hi:
            mid = (lo + hi) // 2
            got = sheet_at(ts[mid])
            if got is None:
                hi = mid - 1
            else:
                best, best_t = got, closest(got)
                lo = mid + 1
    except Spent:
        pass
    order, rest = [best[0]], list(best[1:])
    while rest:
        nxt = max(rest, key=lambda i: (min(d[i][c] for c in order), -i))
        order.append(nxt)
        rest.remove(nxt)
    return order


def select(items, n, settings, distance, model=None, likely=0.5, group=None, cap=None):
    """a sheet of n from `items` (built candidates, in build order) -> (chosen indices in sheet order, info per chosen
    index {role, mean, std, spacing}).

    With the owner's evidence: ceil(n * likely) LIKELY turns (the item pool: the better half by mean) and the rest LEARN
    turns (the more uncertain half by std), alternating; with none, every turn is SPREAD (all items). Each turn takes,
    from its pool, the item farthest from those already chosen (the smallest distance to any of them is largest; ties
    go to the role's own score), so the sheet is spaced apart. The first turn takes the best by its score (with no
    evidence: the first item built). `group`/`cap`: at most `cap` items of one group while other groups still have
    items left (a move's lines share the sheet); past that, any item fills the sheet. With no evidence the turns'
    sheet is then widened (`widest`): the same count per group, the same first item, the widest closest pair the pool
    allows - the greedy turns alone can end closer than the pool needs."""
    m = len(items)
    if m == 0 or n <= 0:
        return [], {}
    sets = [settings(it) for it in items]
    learned = model is not None and model.evidence() > 0
    mean, std = model.predict(sets) if learned else (np.zeros(m), np.ones(m))
    order = np.arange(m)
    half = max(1, -(-m // 2))
    pools = {"likely": set(sorted(order, key=lambda i: (-mean[i], i))[:half]),
             "learn": set(sorted(order, key=lambda i: (-std[i], i))[:half]),
             "spread": set(order)}
    score = {"likely": mean, "learn": std, "spread": np.zeros(m)}
    if learned:
        n_likely = min(n, math.ceil(n * likely))
        turns = []
        a, b = n_likely, n - n_likely
        while a or b:  # alternate, the larger share first
            if a:
                turns.append("likely")
                a -= 1
            if b:
                turns.append("learn")
                b -= 1
    else:
        turns = ["spread"] * n
    D = np.full((m, m), np.inf)
    for i in range(m):
        for j in range(i + 1, m):
            D[i, j] = D[j, i] = float(distance(items[i], items[j]))
    chosen, roles, count = [], {}, {}

    def allowed(i, strict):
        if i in chosen:
            return False
        if strict and group is not None and cap is not None:
            return count.get(group(items[i]), 0) < cap
        return True

    for turn in turns:
        if len(chosen) >= min(n, m):
            break
        pick = None
        for strict in (True, False):
            for role in (turn, "learn" if turn == "likely" else "likely" if turn == "learn" else "spread", "spread"):
                cands = [i for i in pools[role] if allowed(i, strict)]
                if not cands:
                    continue
                if not chosen:
                    pick = min(cands, key=lambda i: (-score[role][i], i)) if learned else min(cands)
                else:
                    pick = max(cands, key=lambda i: (min(D[i, c] for c in chosen), score[role][i], -i))
                turn = role
                break
            if pick is not None:
                break
        if pick is None:
            break
        chosen.append(pick)
        roles[pick] = turn
        if group is not None:
            count[group(items[pick])] = count.get(group(items[pick]), 0) + 1

    if not learned:
        # Nothing learned: every turn only spreads, and the greedy turns can end with a closer pair than the pool
        # needs - a line's share makes its last picks sit next to its first (DTDrillSpin round 4, 2026-11-09: closest
        # pair 8.5 deg where the pool held 12.6, three items away; no single swap reached it). So the widest sheet.
        chosen = widest(D, chosen, (lambda i: group(items[i])) if group is not None else (lambda i: None))
        roles = {i: "spread" for i in chosen}
    info = {}
    for i in chosen:
        others = [D[i, c] for c in chosen if c != i]
        info[i] = {"role": roles[i], "mean": round(float(mean[i]), 3), "std": round(float(std[i]), 3),
                   "spacing": round(float(min(others)), 4) if others else None}
    return chosen, info


def propose(model, sample, k_likely, k_learn, distance=None):
    """settings worth BUILDING next, from a large random `sample`: k_likely among the best guesses (the top 5 % by
    mean, spread out so they are not one point) and k_learn where it knows least (the top quarter by std, spread wide).
    [] without evidence"""
    if model is None or not model.evidence() or not sample:
        return []
    mean, std = model.predict(sample)
    dist = distance or (lambda a, b: float(np.linalg.norm(model.space.numeric([a])[0] - model.space.numeric([b])[0])))
    out = []
    for score, k, share in ((mean, k_likely, 20), (std, k_learn, 4)):
        top = sorted(range(len(sample)), key=lambda i: (-score[i], i))[: max(2 * k, len(sample) // share)]
        picked = []
        for _ in range(min(k, len(top))):
            if not picked:
                picked.append(top[0])
                continue
            best = max((i for i in top if i not in picked), key=lambda i: (min(dist(sample[i], sample[p]) for p in picked), score[i]))
            picked.append(best)
        out += [sample[i] for i in picked]
    return out
