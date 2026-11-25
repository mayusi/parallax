"""kit/tools/primfit.py — a trace redrawn as true lines + arcs: a noisy rounded rectangle comes back as its 4 lines and
4 arcs with the right radius, a circle as arcs only, a square as 4 lines, a symmetric part exactly symmetric, and
near-equal radii made equal (pure numpy)."""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
import primfit as F  # noqa: E402


def rounded_rect(w=40.0, h=20.0, r=5.0, noise=0.03, seed=1):
    rng = np.random.default_rng(seed)
    out = []
    for x in np.linspace(-w / 2 + r, w / 2 - r, 60, endpoint=False):
        out.append((x, -h / 2))
    for t in np.linspace(-math.pi / 2, 0, 20, endpoint=False):
        out.append((w / 2 - r + r * math.cos(t), -h / 2 + r + r * math.sin(t)))
    for y in np.linspace(-h / 2 + r, h / 2 - r, 30, endpoint=False):
        out.append((w / 2, y))
    for t in np.linspace(0, math.pi / 2, 20, endpoint=False):
        out.append((w / 2 - r + r * math.cos(t), h / 2 - r + r * math.sin(t)))
    for x in np.linspace(w / 2 - r, -w / 2 + r, 60, endpoint=False):
        out.append((x, h / 2))
    for t in np.linspace(math.pi / 2, math.pi, 20, endpoint=False):
        out.append((-w / 2 + r + r * math.cos(t), h / 2 - r + r * math.sin(t)))
    for y in np.linspace(h / 2 - r, -h / 2 + r, 30, endpoint=False):
        out.append((-w / 2, y))
    for t in np.linspace(math.pi, 1.5 * math.pi, 20, endpoint=False):
        out.append((-w / 2 + r + r * math.cos(t), -h / 2 + r + r * math.sin(t)))
    return np.array(out) + rng.normal(0, noise, (len(out), 2))


class Fit(unittest.TestCase):
    def test_a_rounded_rectangle_is_4_lines_and_4_arcs(self):
        p = rounded_rect()
        prims = F.fit(p, tol=0.12)
        rep = F.report(p, prims)
        self.assertEqual((rep["lines"], rep["arcs"]), (4, 4), rep)
        self.assertLess(rep["max_mm"], 0.15, rep)
        for r in rep["radii_mm"]:
            self.assertAlmostEqual(r, 5.0, delta=0.2)

    def test_the_chain_is_closed_end_to_end(self):
        prims = F.fit(rounded_rect(), tol=0.12)
        for a, b in zip(prims, prims[1:] + prims[:1]):
            self.assertLess(math.dist(a["b"], b["a"]), 1e-9)

    def test_a_circle_is_arcs_and_a_square_is_lines(self):
        rng = np.random.default_rng(2)
        c = np.array([[10 * math.cos(t), 10 * math.sin(t)] for t in np.linspace(0, 2 * math.pi, 300, endpoint=False)])
        rep = F.report(c, F.fit(c + rng.normal(0, 0.03, c.shape), tol=0.12))
        self.assertEqual(rep["lines"], 0, rep)
        self.assertTrue(all(abs(r - 10) < 0.3 for r in rep["radii_mm"]), rep)
        sq = [(0, 0), (30, 0), (30, 30), (0, 30)]
        rep = F.report(sq, F.fit(sq, tol=0.05))
        self.assertEqual((rep["lines"], rep["arcs"], rep["max_mm"]), (4, 0, 0.0))

    def test_a_mirrored_fit_is_exactly_symmetric(self):
        p = rounded_rect(seed=3)
        prims = F.fit_mirrored(p, "x", 0.0, tol=0.12)
        rep = F.report(p, prims)
        self.assertEqual((rep["lines"], rep["arcs"]), (4, 4), rep)   # (the top + bottom edges one line each)
        s = F.sample(prims, 0.05)
        m = s.copy()
        m[:, 0] *= -1
        d = max(np.min(np.hypot(*(s - q).T)) for q in m)
        self.assertLess(d, 0.06)                                      # (its mirror image lies on it)
        r = rep["radii_mm"]
        self.assertEqual(r[0::2], r[1::2], rep)                       # (each round's mirror twin has its radius)

    def test_near_equal_radii_snap_to_one(self):
        prims = F.snap_radii(F.fit(rounded_rect(noise=0.05, seed=4), tol=0.15))
        radii = {round(q["r"], 6) for q in prims if q["type"] == "arc"}
        self.assertEqual(len(radii), 1, radii)
        self.assertAlmostEqual(radii.pop(), 5.0, delta=0.2)


def _dir(q, at_end):
    """a primitive's unit direction at its start (at_end False) or end, along the chain"""
    a, b = np.array(q["a"]), np.array(q["b"])
    if q["type"] == "line":
        d = b - a
    else:
        c = np.array(q["c"])
        p = b if at_end else a
        v = p - c
        d = np.array([-v[1], v[0]])
        m = np.array(q["m"])
        # (the way round from a through m: flip the tangent if it points away from the arc's sweep)
        if np.dot(d, (m - a) if not at_end else (b - m)) < 0:
            d = -d
    return d / np.hypot(*d)


class Tangent(unittest.TestCase):
    """G1: a designer's smooth joints are TANGENT — what lets OpenCASCADE fillet a redrawn part"""

    def test_smooth_joints_are_tangent_and_every_joint_on_both_sides(self):
        prims = F.fit(rounded_rect(seed=5), tol=0.12, equal=0.08)
        for q, nxt in zip(prims, prims[1:] + prims[:1]):
            self.assertLess(math.dist(q["b"], nxt["a"]), 1e-9)
            if q["type"] == "arc":                                  # (its ends ON its circle)
                for p in (q["a"], q["b"]):
                    self.assertAlmostEqual(math.dist(p, q["c"]), q["r"], places=6)
            if q.get("g1_out"):
                ang = math.degrees(math.acos(min(1.0, abs(float(np.dot(_dir(q, True), _dir(nxt, False)))))))
                self.assertLess(ang, 0.5, (q, nxt))
        self.assertEqual(sum(bool(q.get("g1_out")) for q in prims), 8)     # (the 8 line-round joints)
        self.assertEqual(len({round(q["r"], 6) for q in prims if q["type"] == "arc"}), 1)   # (one radius)


class Robust(unittest.TestCase):
    """not a lucky seed (the fresh review, 2026-10-22: 35/40 and 30/40 before the pieces kept their points)"""

    def test_forty_noisy_traces(self):
        def good(p, prims):
            r = F.report(p, prims)
            return ((r["lines"], r["arcs"]) == (4, 4) and r["max_mm"] <= 0.12 * 1.35
                    and all(abs(x - 5) < 0.6 for x in r["radii_mm"]))
        fit = sum(good(p, F.fit(p, tol=0.12)) for p in (rounded_rect(seed=s) for s in range(1, 41)))
        mir = sum(good(p, F.fit_mirrored(p, "x", 0.0, tol=0.12)) for p in (rounded_rect(seed=s) for s in range(1, 41)))
        self.assertGreaterEqual(fit, 38)
        self.assertGreaterEqual(mir, 39)

    def test_every_primitive_has_both_ends(self):
        # a collinear "arc" (its three points on a line) comes back a line WITH its ends, never {'a': None}
        prims = F._finish([("arc", np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 0.0]])),
                           ("line", np.array([[3.0, 0.0], [3.0, 3.0]])), ("line", np.array([[3.0, 3.0], [0.0, 0.0]]))],
                          0.1)
        for q in prims:
            self.assertIsNotNone(q["a"])
            self.assertIsNotNone(q["b"])


class Cli(unittest.TestCase):
    def test_refs_redraw_writes_the_primitives_and_a_preview(self):
        import json  # noqa: PLC0415
        import subprocess  # noqa: PLC0415
        import tempfile  # noqa: PLC0415

        here = os.path.dirname(os.path.abspath(__file__))
        with tempfile.TemporaryDirectory() as t:
            src, out = os.path.join(t, "x.detail.json"), os.path.join(t, "x.redraw.json")
            with open(src, "w") as fh:
                json.dump({"pieces": [{"outline": rounded_rect().tolist(), "holes": []}]}, fh)
            p = subprocess.run([sys.executable, os.path.join(here, "..", "..", "refs", "redraw.py"), src, "--tol", "0.12",
                                "--out", out], capture_output=True, text=True, env={**os.environ, "KIT_BUILD": t})
            res = json.loads(p.stdout.strip().splitlines()[-1])
            self.assertEqual((res["status"], res["lines"], res["arcs"]), ("pass", 4, 4), p.stdout + p.stderr)
            self.assertEqual(len(json.load(open(out))["prims"]), 8)
            self.assertTrue(os.path.isfile(os.path.join(t, "refs", "x_redraw.png")))


if __name__ == "__main__":
    unittest.main()
