"""The wood grain axis (rbx.grain_axis) must be the SAME every build: shuffled vertex order and float noise (what a
re-run of booleans gives) never change it — not at 45 degrees (sign ties), not on square planks or cubes."""

import ast
import itertools
import os
import unittest

import numpy as np

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender", "rbx.py")
_fn = next(n for n in ast.parse(open(SRC, encoding="utf-8").read()).body
           if isinstance(n, ast.FunctionDef) and n.name == "grain_axis")
_ns = {}
exec(compile(ast.Module([_fn], []), "grain_axis", "exec"), _ns)  # (rbx.py imports bpy: lift the pure function out)
grain_axis = _ns["grain_axis"]


def box(sx, sy, sz):
    return np.array(list(itertools.product((-sx / 2, sx / 2), (-sy / 2, sy / 2), (-sz / 2, sz / 2))), float)


def rotz(p, deg):
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return p @ np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]]).T


class TestGrainAxis(unittest.TestCase):
    def check(self, points, expect=None):
        rng = np.random.default_rng(1)
        outs = set()
        for _ in range(100):
            p = points[rng.permutation(len(points))] + rng.normal(0, 1e-9, points.shape)
            outs.add(tuple(np.round(grain_axis(p), 6) + 0.0))
        self.assertEqual(len(outs), 1, f"grain axis changed between runs: {outs}")
        if expect is not None:
            np.testing.assert_allclose(next(iter(outs)), expect, atol=1e-5)

    def test_plank(self):
        self.check(box(3, 0.3, 0.1), [1, 0, 0])

    def test_brace_45(self):
        self.check(rotz(box(3, 0.3, 0.1), 45), [0.707107, 0.707107, 0])

    def test_mirrored_brace(self):
        self.check(rotz(box(3, 0.3, 0.1), 45) * [-1, 1, 1], [0.707107, -0.707107, 0])

    def test_square_plank(self):
        self.check(box(1, 1, 0.1), [1, 0, 0])

    def test_square_plank_turned(self):
        self.check(rotz(box(1, 1, 0.1), 45))

    def test_cube(self):
        self.check(box(1, 1, 1), [1, 0, 0])


if __name__ == "__main__":
    unittest.main()
