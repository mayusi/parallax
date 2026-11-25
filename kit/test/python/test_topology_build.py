"""The topology of a built model, through REAL builds (kit/selftest/blender/build_topology.py and its three twins;
the 3D methods audit, stage T): faces no eye can reach are taken out and nothing seen goes with them; left in,
they are said; a shading asked and not on the mesh fails; triangles spent on nothing, needles and poles are said."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join("build", "_test_topology_build")


def run(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)


def check(v, name):
    return next(c for c in v["groups"]["main"]["checks"] if c["name"] == name)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = run("build_topology.py")
        cls.again = run("build_topology.py")           # (its maps from the bake's cache)
        cls.kept = run("build_topology_kept.py")
        cls.round = run("build_topology_round.py")
        cls.poor = run("build_topology_poor.py")

    def test_the_faces_no_eye_can_reach_go_and_nothing_seen_goes_with_them(self):
        self.assertEqual(self.good["status"], "pass", self.good["summary"][:300])
        # slab top, block bottom, drum bottom, and the six faces of each of the two cores inside the block
        self.assertEqual(self.good["facts"]["hidden_dropped"], {"main": 15})
        t = self.good["facts"]["topology"]["main"]
        # 12 + 12 + 60 + 24 triangles built; 2 + 2 + 14 + 24 dropped. The block's top - half under the drum - stays
        self.assertEqual((self.kept["facts"]["topology"]["main"]["tris"], t["tris"]), (108, 66))
        self.assertEqual(t["never_seen"], 0.0)
        self.assertTrue(check(self.good, "hidden_faces")["ok"])
        self.assertTrue(check(self.good, "manifold")["ok"])                   # (the rims it left are meant)
        self.assertIn("hidden faces dropped: main 15", self.good["summary"])

    def test_a_cached_build_drops_the_same(self):
        self.assertEqual(self.again["status"], "pass")
        self.assertEqual(self.again["facts"]["hidden_dropped"], {"main": 15})
        self.assertEqual(self.again["facts"]["topology"], self.good["facts"]["topology"])

    def test_left_in_they_are_said(self):
        self.assertEqual(self.kept["status"], "pass")
        c = check(self.kept, "hidden_faces")
        self.assertFalse(c["ok"])
        self.assertEqual(c["severity"], "warn")
        self.assertAlmostEqual(self.kept["facts"]["topology"]["main"]["never_seen"], 42 / 108, places=3)
        self.assertIn("a.drop_hidden()", c["fix"])
        self.assertNotIn("hidden_dropped", self.kept["facts"])

    def test_the_shading_asked_is_read_off_the_mesh(self):
        self.assertEqual(self.good["facts"]["topology"]["main"]["shading"]["Drum"]["flat"], 1.0)
        self.assertTrue(check(self.good, "shading")["ok"])
        self.assertEqual(self.round["status"], "fail")
        c = check(self.round, "shading")
        self.assertFalse(c["ok"])
        self.assertIn("Drum: asked flat", c["fix"])

    def test_triangles_spent_on_nothing_needles_and_poles_are_said(self):
        t = self.poor["facts"]["topology"]["main"]
        self.assertAlmostEqual(t["spent_on_nothing"], 98 / 224, places=3)     # the 49 points inside the top grid
        self.assertEqual(t["poles"], 1)                                        # the cone's tip: 24 edges
        self.assertGreater(t["needles"], 0.005)                                # the shim's sides
        for name, word in (("polygon_waste", "spent on nothing"), ("poles", "edges meet"), ("needles", "needles")):
            c = check(self.poor, name)
            self.assertFalse(c["ok"], name)
            self.assertEqual(c["severity"], "warn")
            self.assertIn(word, c["fix"])
        # (its cone sunk in its slab hides 14% of it: under the bar - a fact, not a warning)
        self.assertTrue(check(self.poor, "hidden_faces")["ok"])
        self.assertGreater(t["never_seen"], 0.1)
        # ... and the good model has none of the three
        for name in ("polygon_waste", "poles", "needles"):
            self.assertTrue(check(self.good, name)["ok"], name)


if __name__ == "__main__":
    unittest.main()
