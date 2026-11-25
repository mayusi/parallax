"""The game's settings of a mesh through REAL builds (kit/selftest/blender/build_fidelity.py): the manifest carries
each group's collision shape and level of detail (what the model file and the spawner read), a doorway in a thin
wall and parts that overlap are read right, a declared shape that shuts a doorway fails, and a shape-only round
(--geo) with a declaration does not stop."""

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
OUT = os.path.join("build", "_test_fidelity_build")


def build(script, *args):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview", *args],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = build("build_fidelity.py")
        with open(os.path.join(ROOT, OUT, "models", "_selftest_fidelity.manifest.json"), encoding="utf-8") as fh:
            cls.groups = json.load(fh)["groups"]

    def test_the_manifest_carries_each_meshs_collision_shape(self):
        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])
        got = {g: v.get("collision_fidelity") for g, v in self.groups.items()}
        self.assertEqual(got, {"main": "Box", "ball": "Hull", "bowl": "Default",
                               "arch": "PreciseConvexDecomposition",
                               "gate": "PreciseConvexDecomposition",     # (a wall half a stud thick)
                               "pile": "Box"})                           # (two blocks that overlap: solid)

    def test_the_manifest_carries_each_meshs_level_of_detail(self):
        self.assertEqual({v.get("render_fidelity") for v in self.groups.values()}, {"Automatic"})
        facts = self.v["facts"]["fidelity"]
        self.assertIn("triangles", facts["bowl"]["render_why"])           # (28 triangles: nothing to reduce)
        self.assertLess(facts["ball"]["render_px"]["lod1"], 1.5)

    def test_the_facts_say_why(self):
        facts = self.v["facts"]["fidelity"]
        self.assertTrue(facts["arch"]["doorway"] and facts["gate"]["doorway"])
        self.assertFalse(facts["pile"]["doorway"] or facts["bowl"]["doorway"])
        self.assertAlmostEqual(facts["bowl"]["gap_hull"], 2.0, delta=0.5)
        self.assertEqual(facts["pile"]["gap_box"], 0.0)

    def test_a_hull_declared_over_the_doorway_fails_by_name_and_is_what_the_manifest_would_carry(self):
        v = build("build_fidelity_closed.py")
        self.assertEqual(v["status"], "fail")
        self.assertIn("arch.collision=Hull", v["summary"])
        self.assertIn("declared", v["facts"]["fidelity"]["arch"]["collision_why"])

    def test_a_shape_only_round_with_a_declaration_does_not_stop(self):
        v = build("build_fidelity_closed.py", "--geo")
        self.assertIn(v["status"], ("pass", "fail"))                      # (it reaches its verdict: no error raised)
        self.assertNotIn("no group named", json.dumps(v))


if __name__ == "__main__":
    unittest.main()
