"""rbx_sculpt's MESHING (OpenVDB, bundled with Blender 5.x — run in Blender): a sculpt always comes out as one closed,
manifold surface at the right size — a ball within 1% of its volume, a ring with its hole, two balls blended into one
piece, an earlier mesh taken in as clay — and fast enough to sculpt with (a 200 mm head at 0.5 mm in seconds)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

KIT = os.path.abspath(os.path.join(HERE, "..", ".."))
BLENDER = cad_check.blender()

PROBE = r'''
import json, math, os, sys, time
sys.path.insert(0, os.path.join(sys.argv[sys.argv.index("--") + 1], "blender"))
import numpy as np
import rbx_sculpt as S


def topo(verts, faces):
    edges = {}
    for f in faces:
        for a, b in zip(f, f[1:] + f[:1]):
            e = (min(a, b), max(a, b))
            edges[e] = edges.get(e, 0) + 1
    vol = 0.0
    for f in faces:
        a = verts[f[0]]
        for i in range(1, len(f) - 1):
            vol += float(np.dot(a, np.cross(verts[f[i]], verts[f[i + 1]]))) / 6.0
    # pieces: union-find over the faces' vertices
    parent = list(range(len(verts)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for f in faces:
        for v in f[1:]:
            ra, rb = find(f[0]), find(v)
            if ra != rb:
                parent[ra] = rb
    pieces = len({find(v) for f in faces for v in f})
    return {"open": sum(1 for c in edges.values() if c == 1), "nonmanifold": sum(1 for c in edges.values() if c > 2),
            "euler": len(verts) - len(edges) + len(faces), "volume": abs(vol), "pieces": pieces, "faces": len(faces)}


out = {}
v, f = S.Canvas(voxel=0.5).ball((0, 0, 0), 20).mesh()
out["ball"] = topo(v, f)
out["ball"]["radius_spread"] = float(np.ptp(np.linalg.norm(v, axis=1)))
v, f = S.Canvas(voxel=0.5).torus((0, 0, 0), 20, 5).mesh()
out["torus"] = topo(v, f)
v, f = S.Canvas(voxel=0.5).ball((-10, 0, 0), 8).ball((10, 0, 0), 8, blend=10).mesh()
out["blend"] = topo(v, f)
v, f = S.Canvas(voxel=0.5).ball((-12, 0, 0), 8).ball((12, 0, 0), 8).mesh()
out["apart"] = topo(v, f)
# an earlier mesh as clay: the ball's own surface, re-sculpted with a box carved off — still closed
bv, bf = S.Canvas(voxel=0.5).ball((0, 0, 0), 20).mesh()
tris = [x for x in bf if len(x) in (3, 4)]
c = S.Canvas(voxel=0.5).add(S.from_mesh(bv, tris, 0.5))
c.box((0, 25, 0), (60, 30, 60), carve=True)
v, f = c.mesh()
out["from_mesh"] = topo(v, f)
out["from_mesh"]["top"] = float(v[:, 1].max())
out["from_mesh"]["clay_ratio"] = S.from_mesh(bv, tris, 0.5).clay_ratio
open_cube = [x for x in tris][: len(tris) * 5 // 6]   # (a sixth of the ball's faces gone: an open mesh)
out["from_mesh"]["open_ratio"] = S.from_mesh(bv, open_cube, 0.5).clay_ratio
c = S.Canvas(voxel=2.0).ball((0, 0, 0), 60).noise(4.0, (6.0, 40.0, 6.0), kind="ridged", seed=5)
v, f = c.mesh(adaptivity=0.1)
out["noisy"] = topo(v, f)
out["noisy"]["specks"] = c.stats.get("specks")
coarse = S.Canvas(voxel=2.5).ball((0, 0, 0), 20)
v, f = coarse.mesh()
out["coarse"] = {"spread": float(np.ptp(np.linalg.norm(v, axis=1)))}
v, f = S.Canvas(voxel=2.5).ball((0, 0, 0), 20).mesh(smooth=8)
out["coarse"]["smoothed_spread"] = float(np.ptp(np.linalg.norm(v, axis=1)))
out["coarse"]["smoothed_mean"] = float(np.linalg.norm(v, axis=1).mean())
t = time.time()
s = S.Canvas(voxel=0.5, mirror="x")
s.ellipsoid((0, 100, 0), (70, 90, 80)).ellipsoid((0, 50, 40), (45, 40, 45), blend=20)
s.stroke([(15, 125, 60), (40, 130, 45), (60, 120, 20)], [10, 8, 5], blend=6)
s.ball((30, 105, 62), 12, carve=True, blend=4)
s.crease([(10, 70, 82), (30, 62, 74)], 2.0)
s.noise(0.8, 6.0, kind="ridged", where=S.Ball((0, 160, 0), 60), falloff=20)
v, f = s.mesh(adaptivity=0.2)
out["head"] = topo(v, f)
out["head"]["seconds"] = time.time() - t
print("RESULT " + json.dumps(out))
'''


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class SculptMesh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp(prefix="kit_sculpt_")
        script = os.path.join(tmp, "probe.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(PROBE)
        p = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", KIT],
                           capture_output=True, text=True, timeout=600)
        line = [x for x in p.stdout.splitlines() if x.startswith("RESULT ")]
        if not line:
            raise AssertionError("no result:\n" + (p.stdout + p.stderr)[-3000:])
        cls.r = json.loads(line[-1][7:])

    def _closed(self, t):
        self.assertEqual((t["open"], t["nonmanifold"]), (0, 0), t)

    def test_a_ball_is_round_closed_and_its_volume(self):
        b = self.r["ball"]
        self._closed(b)
        self.assertEqual(b["euler"], 2)
        self.assertLess(abs(b["volume"] - 4 / 3 * 3.141592653589793 * 20 ** 3) / (4 / 3 * 3.141592653589793 * 20 ** 3),
                        0.01)
        self.assertLess(b["radius_spread"], 0.05)   # (every vertex 20 mm out, to a twentieth of a millimetre)

    def test_a_ring_keeps_its_hole(self):
        self._closed(self.r["torus"])
        self.assertEqual(self.r["torus"]["euler"], 0)   # (genus 1)

    def test_blended_is_one_piece_apart_is_two(self):
        self._closed(self.r["blend"])
        self.assertEqual(self.r["blend"]["pieces"], 1)
        self.assertEqual(self.r["apart"]["pieces"], 2)

    def test_an_earlier_mesh_becomes_clay(self):
        t = self.r["from_mesh"]
        self._closed(t)
        self.assertEqual(t["pieces"], 1)
        self.assertLess(t["top"], 10.6)   # (the carved box's floor at y 10: the ball's top is gone)
        self.assertAlmostEqual(t["clay_ratio"], 1.0, delta=0.05)   # (a closed mesh: all of it became clay)
        self.assertFalse(0.75 <= t["open_ratio"] <= 1.25, t)        # (an open one says so)

    def test_fine_relief_leaves_no_specks(self):
        t = self.r["noisy"]   # (ridged relief at ~3 voxels pinches off pockets the meshing cannot resolve)
        self._closed(t)
        self.assertEqual(t["pieces"], 1, t)

    def test_smoothing_relaxes_the_voxels_stair_steps(self):
        c = self.r["coarse"]   # (a 20 mm ball at 2.5 mm voxels)
        self.assertLess(c["smoothed_spread"], c["spread"], c)
        self.assertAlmostEqual(c["smoothed_mean"], 20.0, delta=0.5)   # (and keeps its size)

    def test_a_head_sized_sculpt_is_quick(self):
        t = self.r["head"]
        self._closed(t)
        self.assertEqual(t["pieces"], 1)
        self.assertLess(t["seconds"], 30.0, t)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class SculptedHull(unittest.TestCase):
    """kit make's sculpted_hull candidate: two traced views -> a closed hull at length 1, the views' proportions"""

    def test_a_box_from_its_two_views(self):
        tmp = tempfile.mkdtemp(prefix="kit_shull_")
        side = {"outline": [[0, 0], [1, 0], [1, 0.5], [0, 0.5]], "holes": [], "height_ratio": 0.5}
        front = {"outline": [[0, 0], [1, 0], [1, 1], [0, 1]], "holes": [], "height_ratio": 1.0}
        paths = []
        for name, t in (("side", side), ("front", front)):
            paths.append(os.path.join(tmp, f"{name}.trace.json"))
            with open(paths[-1], "w", encoding="utf-8") as fh:
                json.dump(t, fh)
        out = os.path.join(tmp, "hull.glb")
        p = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", os.path.join(KIT, "blender", "make_sculpt_hull.py"),
                            "--", *paths, out], capture_output=True, text=True, timeout=300)
        said = json.loads([x for x in p.stdout.splitlines() if x.startswith("{")][-1])
        self.assertEqual(said["status"], "pass", said)
        self.assertTrue(os.path.isfile(out))
        w, ln, h = said["size"]   # (x width, y length, z height) at length 1
        self.assertAlmostEqual(ln, 1.0, delta=0.02)
        self.assertAlmostEqual(h, 0.5, delta=0.02)
        self.assertAlmostEqual(w, 0.5, delta=0.02)   # (the front's height seen as 0.5: its width 0.5)


if __name__ == "__main__":
    unittest.main()
