"""CMA-ES must solve the standard hard test functions within budget, honour bounds and be deterministic per seed."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
from cmaes import CMAES, minimize  # noqa: E402


def sphere(x):
    return float(np.sum(np.asarray(x) ** 2))


def rosenbrock(x):
    x = np.asarray(x)
    return float(np.sum(100 * (x[1:] - x[:-1] ** 2) ** 2 + (1 - x[:-1]) ** 2))


def make_rotated_ellipsoid(n, cond=1e4, seed=3):
    q, _ = np.linalg.qr(np.random.default_rng(seed).standard_normal((n, n)))
    scales = cond ** (np.arange(n) / (n - 1))

    def f(x):
        y = q @ (np.asarray(x) - 0.5)
        return float(np.sum(scales * y * y))
    return f


class TestCMAES(unittest.TestCase):
    def test_sphere_5d(self):
        x, f, evals = minimize(sphere, [1.0] * 5, 0.5, seed=1, max_evals=6000)
        self.assertLess(f, 1e-9, f"sphere 5-d: {f} after {evals} evals")

    def test_rosenbrock_5d(self):
        x, f, evals = minimize(rosenbrock, [0.0] * 5, 0.5, seed=2, max_evals=30000)
        self.assertLess(f, 1e-6, f"rosenbrock 5-d: {f} after {evals} evals")
        np.testing.assert_allclose(x, np.ones(5), atol=1e-2)

    def test_rotated_ellipsoid_5d(self):
        f_ = make_rotated_ellipsoid(5)
        x, f, evals = minimize(f_, [0.0] * 5, 0.3, seed=4, max_evals=20000)
        self.assertLess(f, 1e-8, f"rotated ellipsoid 5-d (condition 1e4): {f} after {evals} evals")

    def test_bounds_hold_and_optimum_on_bound(self):
        """the true optimum (-1, -1) is outside [0, 2]^2: every candidate stays inside, the best sits on the bound"""
        seen = []

        def f(x):
            seen.append(np.array(x))
            return float(np.sum((np.asarray(x) + 1) ** 2))
        x, val, _ = minimize(f, [1.5, 1.5], 0.8, lo=[0, 0], hi=[2, 2], seed=5, max_evals=3000)
        pts = np.array(seen)
        self.assertTrue((pts >= 0).all() and (pts <= 2).all(), "a candidate left the bounds")
        np.testing.assert_allclose(x, [0, 0], atol=1e-3)

    def test_deterministic_per_seed(self):
        a = minimize(rosenbrock, [0.0] * 3, 0.5, seed=7, max_evals=2000)
        b = minimize(rosenbrock, [0.0] * 3, 0.5, seed=7, max_evals=2000)
        self.assertEqual(a[1], b[1])
        np.testing.assert_array_equal(a[0], b[0])

    def test_tell_checks_population(self):
        es = CMAES([0.0, 0.0], 0.5)
        with self.assertRaises(ValueError):
            es.tell(es.ask()[:2], [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
