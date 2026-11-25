"""kit sharpen's fold step (kit/gen/sharpen_part.py) in Blender, on the fixture of
kit/selftest/blender/check_sharpen_fold.py (a head with two wings, one closed skin with its own atlas).

--faces thins a part and leaves it ONE CLOSED SKIN: a GLB splits its vertices along every UV seam, and a collapse run
on it as it is read moves the two sides of each seam apart (the launcher's second wolf: 38,201 open edges, refused by
its build's closed-surface gate 11 minutes later). The fold step welds the seams first and counts the open edges
before and after; the same collapse without the weld must still open the fixture, or it proves nothing.

--drop cuts a box of the part away and caps the cut: a stray piece the generator added (the launcher's heel wolf came
out with a thin rod along its top). The rod is gone, the skin still closed, its UV map kept; a box that holds nothing
of the part is refused and writes nothing."""

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
OUT = None


def result():
    global OUT
    if OUT is None:
        script = os.path.join(REPO, "kit", "selftest", "blender", "check_sharpen_fold.py")
        run = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "--python", script],
                             cwd=REPO, capture_output=True, text=True, timeout=900)
        line = next((ln for ln in run.stdout.splitlines() if ln.startswith("SHARPEN_FOLD ")), None)
        assert line, (run.stderr or run.stdout)[-1200:]
        OUT = json.loads(line[len("SHARPEN_FOLD "):])
    return OUT


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class SharpenThin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = result()

    def test_the_fixture_is_one_closed_skin_with_more_than_the_budget(self):
        self.assertEqual((self.out["open_in"], self.out["pinched_in"]), (0, 0), self.out)
        self.assertGreater(self.out["tris_in"], self.out["budget"] * 2, self.out)

    def test_thinned_to_the_budget_with_its_uv_map(self):
        self.assertEqual(self.out["status"], "pass", self.out)
        self.assertLessEqual(self.out["tris_out"], self.out["budget"] * 1.02, self.out)
        self.assertGreater(self.out["tris_out"], self.out["budget"] * 0.5, self.out)
        self.assertTrue(self.out["uv_out"], self.out)
        self.assertIn("thinned", self.out["summary"])

    def test_still_one_closed_skin(self):
        self.assertEqual((self.out["open_out"], self.out["pinched_out"]), (0, 0), self.out)

    def test_the_same_collapse_without_the_weld_opens_it(self):
        self.assertGreater(self.out["open_thinned_as_read"], 100, self.out)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class SharpenDrop(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = result()

    def test_the_fixture_has_the_rod_on_a_closed_skin(self):
        self.assertEqual(self.out["rod_open_in"], 0, self.out)
        self.assertGreater(self.out["rod_faces_in"], 50, self.out)

    def test_the_rod_is_cut_away(self):
        self.assertEqual(self.out["drop_status"], "pass", self.out)
        self.assertEqual(self.out["rod_faces_out"], 0, self.out)
        self.assertIn("cut away", self.out["drop_summary"])

    def test_the_cut_is_capped_and_the_uv_map_kept(self):
        self.assertEqual((self.out["drop_open_out"], self.out["drop_pinched_out"]), (0, 0), self.out)
        self.assertTrue(self.out["drop_uv_out"], self.out)

    def test_a_box_that_holds_nothing_is_refused(self):
        self.assertEqual(self.out["nothing_status"], "fail", self.out)
        self.assertIn("holds no face", self.out["nothing_summary"])
        self.assertFalse(self.out["nothing_written"], self.out)


if __name__ == "__main__":
    unittest.main()
