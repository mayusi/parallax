"""The hybrid route (LIMITATIONS_FIXES_V4 3D-X, 13.2; kit/gen/hybrid_fabricate.py, retopo_part.py, hulls.py,
kit/blender/rbx_hybrid.py, a.import_mesh(high=)). The pure hull judge first; then, where the tools are on this machine:
CoACD on an L, the retopology of a generator-like crust (Instant Meshes, and Blender's QuadriFlow when its binary is
missing), the route's fixture BUILT both ways (a retopologised part with its high: no generated_topology; the same
part as decimated soup: named), and its built game mesh cut into convex hulls."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
COACD_PY = os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "envs", "coacd", "Scripts", "python.exe")
sys.path.insert(0, os.path.join(ROOT, "kit", "gen"))
import hulls as H  # noqa: E402

TEST_BUILD = os.path.join("build", "_test_hybrid")


def prism(outline, z0, z1):
    """a closed prism from an outline (counter-clockwise, every point seen from the first: fanned) -> (verts, tris)"""
    n = len(outline)
    v = [(x, y, z0) for x, y in outline] + [(x, y, z1) for x, y in outline]
    t = [(0, k + 1, k) for k in range(1, n - 1)] + [(n, n + k, n + k + 1) for k in range(1, n - 1)]
    for k in range(n):
        a, b = k, (k + 1) % n
        t += [(a, b, n + b), (a, n + b, n + a)]
    return np.array(v, float), np.array(t, np.int64)


L_OUTLINE = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]


class Judge(unittest.TestCase):
    def setUp(self):
        self.v, self.t = prism(L_OUTLINE, 0.0, 1.0)

    def test_the_l_is_closed_and_outward(self):
        self.assertAlmostEqual(H.volume(self.v, self.t), 3.0, places=9)

    def test_two_boxes_cover_it_with_nothing_spare(self):
        a = prism([(0, 0), (2, 0), (2, 1), (0, 1)], 0, 1)
        b = prism([(0, 1), (1, 1), (1, 2), (0, 2)], 0, 1)
        f = H.judge(self.v, self.t, [a, b])
        self.assertTrue(f["ok"], f)
        self.assertGreaterEqual(f["coverage"], 0.999)
        self.assertAlmostEqual(f["excess"], 0.0, places=6)

    def test_one_hull_closes_the_corner(self):
        hull = prism([(0, 0), (2, 0), (2, 1), (1, 2), (0, 2)], 0, 1)   # (the L's convex hull: 3.5 for 3)
        f = H.judge(self.v, self.t, [hull])
        self.assertGreaterEqual(f["coverage"], 0.999)
        self.assertGreater(f["excess"], 0.15)
        self.assertAlmostEqual(f["excess"], 0.5 / 3.0, places=3)   # (rounded to 4 places)

    def test_a_missing_piece_leaves_a_hole(self):
        a = prism([(0, 0), (2, 0), (2, 1), (0, 1)], 0, 1)
        f = H.judge(self.v, self.t, [a])
        self.assertLess(f["coverage"], H.COVER_BAR)
        self.assertFalse(f["ok"])

    def test_only_an_open_mesh_is_remeshed_first(self):
        # (CoACD's voxel pre-remesh fattened the H9 blade, 8 mm thick, into one hull 8.5x its volume: a closed mesh
        #  is cut as it is)
        self.assertTrue(H.is_closed(self.t))
        self.assertFalse(H.is_closed(self.t[:-2]))           # (a side's two triangles gone: an open rim)
        self.assertFalse(H.is_closed(np.vstack([self.t, self.t[:1]])))   # (a face twice: pinched edges)

    def test_obj_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "l.obj")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("".join(f"v {x} {y} {z}\n" for x, y, z in self.v))
                fh.write("".join(f"f {a + 1} {b + 1} {c + 1}\n" for a, b, c in self.t))
            v, t = H.read_obj(p)
        self.assertEqual(len(v), len(self.v))
        self.assertAlmostEqual(H.volume(v, t), 3.0, places=6)


@unittest.skipUnless(os.path.isfile(COACD_PY), "CoACD's env not installed (VETLOG coacd 1.0.14)")
class CoACD(unittest.TestCase):
    def test_coacd_cuts_the_l_into_pieces_that_cover_it(self):
        v, t = prism(L_OUTLINE, 0.0, 1.0)
        with tempfile.TemporaryDirectory() as d:
            p, out = os.path.join(d, "l.obj"), os.path.join(d, "l.json")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("".join(f"v {x} {y} {z}\n" for x, y, z in v))
                fh.write("".join(f"f {a + 1} {b + 1} {c + 1}\n" for a, b, c in t))
            r = subprocess.run([COACD_PY, os.path.join(ROOT, "kit", "gen", "hulls.py"), p, out, "--threshold",
                                "0.03"], capture_output=True, text=True, timeout=600)
            said = json.loads(r.stdout.strip().splitlines()[-1])
            with open(out, encoding="utf-8") as fh:
                facts = json.load(fh)
        self.assertEqual(said["status"], "pass", said)
        self.assertGreaterEqual(facts["hull_count"], 2)        # (one hull would close the corner)
        self.assertGreaterEqual(facts["coverage"], H.COVER_BAR)
        self.assertLessEqual(facts["excess"], 0.1)


def blender(script, *args, env=None):
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", *args],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=env, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith('{"schema"')), None)
    return r, (json.loads(line) if line else None)


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender not found")
class Retopo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="kit_retopo_")
        cls.gen = os.path.join(cls.dir, "gen_part.glb")
        r, _ = blender(os.path.join(ROOT, "kit", "selftest", "blender", "make_gen_part.py"), cls.gen)
        assert r.returncode == 0 and os.path.isfile(cls.gen), r.stdout[-500:]

    def test_the_crust_is_soup_and_its_retopology_is_quads(self):
        sys.path.insert(0, os.path.join(ROOT, "kit", "gen"))
        import hybrid_fabricate as F  # noqa: PLC0415

        env_build = os.path.join(self.dir, "build")
        os.environ["KIT_BUILD"] = env_build
        F.BUILD = env_build
        try:
            path = F.fabricate_hybrid(None, {"asset": "_test_hilt", "root": ROOT,
                                             "parts": {"Pommel": {"gen_glb": self.gen, "quads": 2000}}},
                                      {"Pommel": "ai_part", "Grip": "cad", "Scroll": "ornament"})
        finally:
            os.environ.pop("KIT_BUILD", None)
        with open(path, encoding="utf-8") as fh:
            man = json.load(fh)
        p = man["parts"]["Pommel"]
        self.assertEqual(p["route"], "ai_part")
        self.assertEqual(man["parts"]["Grip"], {"route": "cad"})
        self.assertEqual(man["parts"]["Scroll"], {"route": "ornament"})
        rt = p["retopo"]
        self.assertEqual(rt["remesher"], "instant_meshes" if os.path.isfile(
            os.path.join(os.path.expanduser("~"), ".cache", "roblox-kit", "src", "instant-meshes", "build", "Release",
                         "Instant Meshes.exe")) else "quadriflow")
        self.assertEqual(rt["quad_share"], 1.0)               # (every face of the low four-sided)
        self.assertEqual(rt["open_edges"], 0)
        self.assertLess(rt["distance"]["low_to_high"]["p95"], 0.01)   # (within 1% of its size of the high)
        self.assertTrue(os.path.isfile(p["low"]) and os.path.isfile(p["high"]))
        self.assertLessEqual(rt["polygons"], 2000 * 1.25)

    def test_quadriflow_when_instant_meshes_is_missing(self):
        out = os.path.join(self.dir, "qf.glb")
        env = dict(os.environ, KIT_INSTANT_MESHES=os.path.join(self.dir, "no_such.exe"))
        r, said = blender(os.path.join(ROOT, "kit", "gen", "retopo_part.py"), self.gen, out, "--quads", "1500",
                          "--size", "512", env=env)
        self.assertEqual(r.returncode, 0, r.stdout[-500:])
        self.assertEqual(said["remesher"], "quadriflow")
        self.assertIn("QuadriFlow instead", said["said"])
        self.assertGreater(said["quad_share"], 0.95)


def build(how):
    env = dict(os.environ, KIT_GAME="none", KIT_BUILD=TEST_BUILD)
    r, said = blender(os.path.join(ROOT, "kit", "selftest", "blender", f"build_hybrid_{how}.py"), "--no-preview",
                      env=env)
    assert r.returncode == 0 and said, (r.stderr or r.stdout)[-800:]
    return said


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender not found")
class Built(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ok, cls.soup = build("ok"), build("soup")

    def test_a_retopologised_part_with_its_high_is_not_named(self):
        self.assertNotIn("generated_topology", self.ok["summary"])
        imp = {r["part"]: r for r in self.ok["facts"]["imported"]}
        self.assertEqual(imp["Pommel~high"]["role"], "high")
        self.assertTrue(imp["Pommel"]["high"].endswith("Pommel_high.glb"))
        self.assertGreaterEqual(imp["Pommel"]["topology"]["quad_share"], 0.8)
        g = self.ok["facts"]["low"]["groups"]["pommel"]
        self.assertGreater(g["high_tris"], 10 * g["low_tris"])   # (its relief baked from the dense skin)
        self.assertLessEqual(g["bake_misses"]["missed"], 0.002)

    def test_the_cad_parts_are_cast_and_engraved(self):
        f = self.ok["facts"]
        casts = f.get("casts") or []
        self.assertTrue(any("CAD route" in str(c.get("route")) for c in casts), casts)   # (one fused OCC solid)
        stamps = f.get("stamps") or {}
        self.assertTrue(stamps, list(f)[:40])

    def test_the_same_part_as_soup_is_named(self):
        self.assertIn("generated_topology", self.soup["summary"])
        imp = {r["part"]: r for r in self.soup["facts"]["imported"]}
        self.assertLess(imp["Pommel"]["topology"]["quad_share"], 0.5)

    @unittest.skipUnless(os.path.isfile(COACD_PY), "CoACD's env not installed")
    def test_its_game_mesh_cut_into_convex_hulls(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "gen", "hybrid_fabricate.py"),
                            "_selftest_hybrid_ok", "--hulls", "--threshold", "0.08", "--max", "8"],
                           cwd=ROOT, capture_output=True, text=True, timeout=1800,
                           env=dict(os.environ, KIT_BUILD=TEST_BUILD))
        said = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(said["status"], "pass", said)
        with open(os.path.join(ROOT, TEST_BUILD, "hybrid", "_selftest_hybrid_ok", "hybrid.json"),
                  encoding="utf-8") as fh:
            man = json.load(fh)
        for g in ("hilt", "pommel"):
            self.assertGreaterEqual(man["hulls"][g]["coverage"], H.COVER_BAR)


if __name__ == "__main__":
    unittest.main()
