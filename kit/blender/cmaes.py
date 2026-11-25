"""cmaes.py — CMA-ES (covariance matrix adaptation evolution strategy), from scratch in numpy: the kit's optimiser for
FITTING — a camera to a photo (render, compare, adjust), a part's parameters to its reference outlines (build --geo,
compare, adjust). No bpy import: runs in Blender's python and in system python alike.

    es = CMAES(x0=[0.2, 1.5], sigma=0.3, lo=[0, 1], hi=[1, 3], seed=1)
    while not es.done():
        xs = es.ask()
        es.tell(xs, [loss(x) for x in xs])
    es.best_x, es.best_f

Black-box and derivative-free: it needs only a loss per candidate, so the loss can be a rendered silhouette's IoU, a
line-recall, anything measurable. Bounds are honoured by sampling inside them (each candidate is mirrored back into
[lo, hi]); the mean and covariance adapt from the ranked candidates (Hansen, "The CMA Evolution Strategy: A Tutorial",
2016 — default population, weights and learning rates). Deterministic for a given seed.
"""

import math

import numpy as np


class CMAES:
    def __init__(self, x0, sigma, lo=None, hi=None, popsize=None, seed=0, max_evals=None, tol_f=1e-12, tol_x=1e-11):
        self.n = n = len(x0)
        self.mean = np.array(x0, dtype=float)
        self.sigma = float(sigma)
        self.lo = None if lo is None else np.array(lo, dtype=float)
        self.hi = None if hi is None else np.array(hi, dtype=float)
        if self.lo is not None and self.hi is not None and np.any(self.hi <= self.lo):
            raise ValueError("cmaes: every hi must be above its lo")
        self.rng = np.random.default_rng(seed)
        self.lam = popsize or 4 + int(3 * math.log(n))
        self.mu = self.lam // 2
        w = math.log(self.mu + 0.5) - np.log(np.arange(1, self.mu + 1))
        self.w = w / w.sum()
        self.mueff = 1.0 / (self.w ** 2).sum()
        # learning rates (tutorial defaults)
        self.cc = (4 + self.mueff / n) / (n + 4 + 2 * self.mueff / n)
        self.cs = (self.mueff + 2) / (n + self.mueff + 5)
        self.c1 = 2 / ((n + 1.3) ** 2 + self.mueff)
        self.cmu = min(1 - self.c1, 2 * (self.mueff - 2 + 1 / self.mueff) / ((n + 2) ** 2 + self.mueff))
        self.damps = 1 + 2 * max(0.0, math.sqrt((self.mueff - 1) / (n + 1)) - 1) + self.cs
        self.chin = math.sqrt(n) * (1 - 1 / (4 * n) + 1 / (21 * n * n))
        self.pc = np.zeros(n)
        self.ps = np.zeros(n)
        self.B = np.eye(n)
        self.D = np.ones(n)
        self.C = np.eye(n)
        self.invsqrtC = np.eye(n)
        self.eigen_at = 0
        self.evals = 0
        self.gen = 0
        self.max_evals = max_evals or 1000 * n * n
        self.tol_f, self.tol_x = tol_f, tol_x
        self.best_x, self.best_f = self.mean.copy(), float("inf")
        self.history = []  # best loss per generation (for reports)
        self._ys = None
        self._spread = []

    def _mirror(self, x):
        """fold a candidate back into [lo, hi] (reflection keeps the distribution's shape near a bound)"""
        if self.lo is None or self.hi is None:
            return x
        span = self.hi - self.lo
        t = np.mod(x - self.lo, 2 * span)
        return self.lo + np.where(t > span, 2 * span - t, t)

    def ask(self):
        z = self.rng.standard_normal((self.lam, self.n))
        self._ys = z @ (self.B * self.D).T  # y ~ N(0, C)
        return [self._mirror(self.mean + self.sigma * y) for y in self._ys]

    def tell(self, xs, fs):
        fs = np.asarray(fs, dtype=float)
        if len(fs) != self.lam:
            raise ValueError(f"cmaes: tell() needs {self.lam} losses, got {len(fs)}")
        self.evals += len(fs)
        self.gen += 1
        order = np.argsort(fs)
        if fs[order[0]] < self.best_f:
            self.best_f, self.best_x = float(fs[order[0]]), np.array(xs[order[0]], dtype=float)
        self.history.append(float(fs[order[0]]))
        self._spread.append(float(fs[order[-1]] - fs[order[0]]))
        # the steps actually taken (a mirrored candidate counts where it landed)
        ys = np.array([(np.asarray(xs[i]) - self.mean) / self.sigma for i in order[: self.mu]])
        old = self.mean.copy()
        ymean = self.w @ ys
        self.mean = old + self.sigma * ymean
        # step-size path, covariance path
        self.ps = (1 - self.cs) * self.ps + math.sqrt(self.cs * (2 - self.cs) * self.mueff) * (self.invsqrtC @ ymean)
        hsig = (np.linalg.norm(self.ps) / math.sqrt(1 - (1 - self.cs) ** (2 * self.gen)) / self.chin) < 1.4 + 2 / (self.n + 1)
        self.pc = (1 - self.cc) * self.pc + hsig * math.sqrt(self.cc * (2 - self.cc) * self.mueff) * ymean
        rank_mu = (ys.T * self.w) @ ys
        self.C = ((1 - self.c1 - self.cmu) * self.C
                  + self.c1 * (np.outer(self.pc, self.pc) + (not hsig) * self.cc * (2 - self.cc) * self.C)
                  + self.cmu * rank_mu)
        self.sigma *= math.exp((self.cs / self.damps) * (np.linalg.norm(self.ps) / self.chin - 1))
        # decompose C now and then (O(n^3): not every generation)
        if self.evals - self.eigen_at > self.lam / (self.c1 + self.cmu) / self.n / 10:
            self.eigen_at = self.evals
            self.C = np.triu(self.C) + np.triu(self.C, 1).T
            d2, self.B = np.linalg.eigh(self.C)
            self.D = np.sqrt(np.maximum(d2, 1e-20))
            self.invsqrtC = (self.B / self.D) @ self.B.T

    def done(self):
        """stop: budget spent, the losses flat, or the search collapsed to a point"""
        if self.evals >= self.max_evals:
            return True
        if len(self._spread) >= 10 and max(self._spread[-10:]) < self.tol_f:
            return True
        return self.gen > 0 and self.sigma * float(self.D.max()) < self.tol_x

    def run(self, loss, verbose=False):
        """minimise loss(x) -> (best x, best loss)"""
        while not self.done():
            xs = self.ask()
            self.tell(xs, [loss(x) for x in xs])
            if verbose:
                print(f"gen {self.gen:4d} evals {self.evals:6d} best {self.best_f:.6g} sigma {self.sigma:.3g}")
        return self.best_x, self.best_f


def minimize(loss, x0, sigma, lo=None, hi=None, seed=0, max_evals=None, popsize=None):
    """one call: CMA-ES from x0 -> (best x, best loss, evaluations used)"""
    es = CMAES(x0, sigma, lo=lo, hi=hi, seed=seed, max_evals=max_evals, popsize=popsize)
    x, f = es.run(loss)
    return x, f, es.evals
