"""Seams the author places, through REAL builds (kit/selftest/blender/build_seam_placed.py and its two twins; the
3D methods audit, S3b): a handle cut down its back and at its caps lies as one strip whose only cut is at the back;
a tube nobody cut open fails; a rule that cuts nothing stops the build."""

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


def run(script, out):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=out)
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                           os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                          cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                          errors="replace")


def verdict(r):
    return json.loads(next(x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x))


def line(r, word):
    got = next((x for x in r.stdout.splitlines() if x.startswith(word + " ")), None)
    assert got, (r.stderr or r.stdout)[-800:]
    return json.loads(got[len(word) + 1:])


def check(v, name, group="main"):
    return next(c for c in v["groups"][group]["checks"] if c["name"] == name)

OUT = os.path.join("build", "_test_seam_placed_build")


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = run("build_seam_placed.py", OUT)
        cls.v = verdict(cls.good)
        cls.again = verdict(run("build_seam_placed.py", OUT))        # (its maps from the bake's cache)
        cls.uncut = run("build_seam_placed_uncut.py", OUT)
        cls.nowhere = run("build_seam_placed_nowhere.py", OUT)

    def test_the_side_is_one_strip_cut_only_at_the_back(self):
        at = line(self.good, "SEAMS")
        self.assertEqual(at["front"], [1, 1])       # each vertex down the front: ONE place on the map
        self.assertEqual(at["back"], [2, 2])        # ... down the back: two - the cut
        self.assertEqual(self.v["status"], "pass", self.v["summary"][:300])

    def test_the_build_says_the_pieces_and_holds_them(self):
        f = self.v["facts"]["seams_placed"]["main"]["Handle"]
        self.assertEqual((f["pieces"], f["rings"]), (3, 0))           # the side, and the two caps: read off the map
        self.assertEqual(f["cut"], f["asked"])                        # cut where asked, nowhere else
        self.assertLessEqual(f["stretched"], 0.05)
        self.assertTrue(check(self.v, "seam_placed")["ok"])
        self.assertIn("placed seams: Handle 3 piece(s)", self.v["summary"])

    def test_a_build_taken_from_the_cache_says_the_same(self):
        self.assertEqual(self.again["facts"]["seams_placed"], self.v["facts"]["seams_placed"])
        self.assertEqual(self.again["status"], "pass")

    def test_a_tube_nobody_cut_open_fails(self):
        v = verdict(self.uncut)
        self.assertEqual(v["status"], "fail")
        c = check(v, "seam_placed")
        self.assertFalse(c["ok"])
        self.assertEqual(c["severity"], "error")
        self.assertIn("Handle:", c["fix"])
        self.assertEqual(line(self.uncut, "SEAMS")["back"], [1, 1])  # (nothing was cut down the back)

    def test_a_rule_that_cuts_no_edge_stops_the_build(self):
        self.assertNotEqual(self.nowhere.returncode, 0)
        self.assertIn('a.seams("Handle"): the rule cut no edge of the part', self.nowhere.stderr + self.nowhere.stdout)


if __name__ == "__main__":
    unittest.main()
