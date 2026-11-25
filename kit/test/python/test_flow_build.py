"""EDGE FLOW, MOVED through a REAL build (kit/selftest/blender/build_flow.py): bunched loops on a panel and a rod are
spread by a.flow, the shape held exactly, the panel's mirrored copy follows, a part of nothing but corners is
refused, and the model still builds."""

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


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_flow_build"))
        cls.r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                                os.path.join(ROOT, "kit", "selftest", "blender", "build_flow.py"), "--", "--no-preview"],
                               cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                               errors="replace")
        line = next((x for x in cls.r.stdout.splitlines() if x.startswith("FLOW ")), None)
        cls.got = json.loads(line[5:]) if line else None

    def test_it_built(self):
        self.assertEqual(self.r.returncode, 0, (self.r.stderr or self.r.stdout)[-1500:])
        self.assertIsNotNone(self.got, self.r.stdout[-1500:])

    def test_bunched_loops_spread_and_the_shape_holds(self):
        for part in ("Panel", "Rod"):
            g = self.got[part]
            self.assertGreater(g["moved"], 0, part)
            self.assertLess(g["spread_after"], g["spread_before"] * 0.5, (part, g))
            self.assertLess(g["off_mm"], 0.01, (part, g))            # (every vertex on the surface it started on)
            self.assertLess(g["box_moved"], 1e-5, (part, g))         # (its outline: a rod's rim never slid round)

    def test_the_mirrored_copy_moves_the_mirrored_way_vertex_by_vertex(self):
        self.assertLess(self.got["copy_off"], 1e-5)                  # (the rod: free vertices on the copy too)

    def test_a_ring_a_hair_from_its_cap_never_collapses_onto_it(self):
        # (review 2026-11-17: at 2 passes the ring's vertices were laid on the end cap - each "on the surface";
        # the faces then turn ~90 degrees. Each vertex now keeps to its own smooth region)
        g = self.got["Ring"]
        self.assertLess(g["face_turn_deg"], 15.0, g)
        self.assertLess(g["box_moved"], 1e-5, g)
        self.assertEqual(self.got["Panel"]["face_turn_deg"], 0.0)   # (a flat panel's faces never turn)

    def test_corners_only_and_a_cad_part_are_refused(self):
        self.assertIn("every vertex", self.got["Plain"])
        self.assertIn("CAD part", self.got["Cad"])


if __name__ == "__main__":
    unittest.main()
