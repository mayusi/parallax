"""kit sharpen's new skin is SOLID (kit/gen/sharpen_part.py, new_skin), on the fixture of
kit/selftest/blender/check_sharpen_skin.py: a ball's shell 0.03 thick with a hole at its top - what a generator's
mesh is, a thin crust with an inner wall, and a gap that makes the two walls one surface. As the remesh leaves it the
skin is hollow (the fixture still shows the fault: the launcher's nose wolf, 446,224 triangles, 98.5% of them a double
wall, half its colour map on an inside nobody sees). The new skin sheds the inner wall, closes the gap and stays one
closed surface with its UV atlas. The cap is also tried on a rim that touches itself (two holes sharing a corner):
one fan through that corner pinched 12 edges on the real wolf."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import cad_check  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = cad_check.blender()


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class SharpenSolidSkin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = os.path.join(REPO, "kit", "selftest", "blender", "check_sharpen_skin.py")
        run = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "--python", script],
                             cwd=REPO, capture_output=True, text=True, timeout=900)
        line = next((ln for ln in run.stdout.splitlines() if ln.startswith("SHARPEN_SKIN ")), None)
        assert line, (run.stderr or run.stdout)[-1200:]
        out = json.loads(line[len("SHARPEN_SKIN "):])
        cls.left, cls.solid, cls.eight = out["as_remeshed"], out["solid"], out["figure_eight"]

    def test_a_rim_that_touches_itself_is_closed_ring_by_ring_without_a_pinched_edge(self):
        self.assertEqual(self.eight, {"closed": 2, "left": 0, "pinched": 0, "open": 0})

    def test_as_the_remesh_leaves_it_the_crust_is_hollow_and_says_so(self):
        self.assertGreater(self.left["thin"], 0.9, self.left)             # (measured by the fixture's own rays)
        self.assertGreater(self.left["said_hollow"], 0.9, self.left)      # (and by the kit's)
        self.assertEqual(self.left["removed"], 0, self.left)              # solid=False took nothing

    def test_the_new_skin_is_solid(self):
        self.assertLess(self.solid["thin"], 0.02, self.solid)
        self.assertGreater(self.solid["removed"], 10000, self.solid)
        self.assertLess(self.solid["said_after"], 0.02, self.solid)

    def test_it_is_one_closed_surface_with_its_atlas(self):
        self.assertEqual((self.solid["open"], self.solid["pinched"], self.solid["wound"]), (0, 0, 0), self.solid)
        self.assertTrue(self.solid["uv"], self.solid)

    def test_the_inside_no_longer_costs_triangles(self):
        self.assertLess(self.solid["triangles"], self.left["triangles"] * 0.65, (self.solid, self.left))
        self.assertGreater(self.solid["triangles"], self.left["triangles"] * 0.40, (self.solid, self.left))


if __name__ == "__main__":
    unittest.main()
