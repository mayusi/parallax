"""R6 clothes to the game's standard (kit/blender/rbx_r6wear.py, a.r6_wear; LIMITATIONS_FIXES_V4 3D-X: "< 4k quad-loft
shell, 0.035 st rectangular clearance + 0.022 corner"). The pure checks, then the build: a shell made by
rbx_r6wear.shell passes all four; the Hero way (a round, dense, soup tube round the square torso) is named."""

import json
import math
import os
import subprocess
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_r6wear as W  # noqa: E402


def volume(verts, faces):
    v = np.asarray(verts, float)
    tot = 0.0
    for f in faces:
        for k in range(1, len(f) - 1):
            tot += np.dot(v[f[0]], np.cross(v[f[k]], v[f[k + 1]])) / 6.0
    return tot


class Standard(unittest.TestCase):
    def test_a_shell_on_every_block_meets_the_standard(self):
        for on, (c, h) in W.BLOCKS.items():
            v, f = W.loft(on, c[1] - h[1], c[1] + h[1])
            j = W.judge(v, f, on, samples=W.face_middles(v, f))
            self.assertTrue(all(j["ok"].values()), (on, j))
            self.assertLessEqual(j["tris"], W.TRI_BUDGET)
            self.assertGreater(volume(v, f), 0)   # (closed and facing out)

    def test_its_faces_stand_the_clearance_off_and_its_corners_the_corner(self):
        on = "Torso"
        c, h = W.BLOCKS[on]
        v, f = W.loft(on, c[1] - h[1], c[1] + h[1], thickness=0.02)
        d = W.box_distance(v, on)
        self.assertAlmostEqual(float(d.min()), W.CORNER, places=4)        # the rounded corners come nearest
        # a point on the front face's middle: exactly the clearance off
        front = np.array(v)[np.abs(np.array(v)[:, 0] - c[0]) < 0.05]
        self.assertAlmostEqual(float(W.box_distance(front, on).min()), W.CLEARANCE, places=4)

    def test_the_corner_radius(self):
        r = W.corner_radius(0.035, 0.022)
        # the arc's point on the diagonal: sqrt(2) (clearance - r) + r from the block's edge
        self.assertAlmostEqual(math.sqrt(2) * (0.035 - r) + r, 0.022, places=9)

    def test_a_flare_gives_room_and_keeps_quads(self):
        on = "LeftLeg"
        v, f = W.loft(on, 0.0, 2.0, flare=[(0.0, 0.3), (1.0, 0.0)])
        j = W.judge(v, f, on)
        self.assertTrue(all(j["ok"].values()), j)
        bottom = np.array(v)[np.abs(np.array(v)[:, 1]) < 1e-9]
        self.assertGreater(float(W.box_distance(bottom, on).min()), 0.3)

    def test_an_open_shell_is_not_watertight(self):
        v, f = W.loft("Torso", 2.0, 4.0)
        half = len(v) // 2   # (the inner wall's points first, the outer's after: a rim face has both)
        walls = [q for q in f if not (min(q) < half <= max(q))]
        self.assertLess(len(walls), len(f))
        j = W.judge(v, walls, "Torso")
        self.assertFalse(j["ok"]["r6_closed"], j)
        self.assertGreater(j["open_edges"], 0)

    def test_a_round_tube_round_the_square_block_pokes(self):
        verts, faces = [], []
        U, V = 64, 8
        for i in range(V + 1):
            for j in range(U):
                t = 2 * math.pi * j / U
                verts.append((1.05 * math.cos(t), 2.0 + 2.0 * i / V, 0.6 * math.sin(t)))
        for i in range(V):
            for j in range(U):
                faces.append((i * U + j, i * U + (j + 1) % U, (i + 1) * U + (j + 1) % U, (i + 1) * U + j))
        j = W.judge(verts, faces, "Torso", samples=W.face_middles(verts, faces))
        self.assertFalse(j["ok"]["r6_clearance"], j)
        self.assertGreater(j["inside"], 0)

    def test_over_budget(self):
        v, f = W.loft("Torso", 2.0, 4.0, edge=0.05)
        j = W.judge(v, f, "Torso")
        self.assertGreater(j["tris"], W.TRI_BUDGET)
        self.assertFalse(j["ok"]["r6_tris"])

    def test_an_unknown_block_is_refused(self):
        with self.assertRaises(ValueError):
            W.block("Tail")


def build(how):
    env = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_r6wear"))
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", f"build_r6wear_{how}.py"), "--",
                        "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=1200, env=env,
                       encoding="utf-8", errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith('{"schema"')), None)
    assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender not found")
class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ok, cls.soup = build("ok"), build("soup")

    def test_the_shell_passes_the_standard(self):
        s = self.ok["summary"]
        for name in ("r6_tris", "r6_quads", "r6_closed", "r6_clearance"):
            self.assertNotIn(name, s)
        f = self.ok["facts"]["design"]["r6_wear"]["shirt"] if "design" in self.ok["facts"] else None
        f = f or self.ok["facts"].get("r6_wear", {}).get("shirt")
        self.assertIsNotNone(f, list(self.ok["facts"])[:40])
        self.assertLessEqual(f["tris"], W.TRI_BUDGET)
        self.assertGreaterEqual(f["quad_share"], W.QUAD_BAR)
        self.assertGreaterEqual(f["nearest"], W.CORNER - 1e-3)

    def test_the_hero_way_is_named(self):
        s = self.soup["summary"]
        for name in ("r6_tris", "r6_quads", "r6_clearance"):
            self.assertIn(name, s)
        self.assertEqual(self.soup["status"], "fail")


if __name__ == "__main__":
    unittest.main()
