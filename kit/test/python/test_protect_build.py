"""A place the game version must keep, through REAL builds (kit/selftest/blender/build_protect.py and its twin;
his D-R08; the 3D methods audit, stage L): fine shallow grooves on a rippled plate, reduced to 1000 triangles -
kept where the decimator is steered by a.protect, lost (and said) where the place is only measured."""

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
OUT = os.path.join("build", "_test_protect_build")


def verdict(script, *more):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview", *more],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)   # (strict: the kit reads this line the same way)


def kept(name):
    with open(os.path.join(ROOT, OUT, "models", f"_selftest_protect_{name}_game.manifest.json"), encoding="utf-8") as f:
        return json.load(f)["protected"]["Grooves"]


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        GAME = ("--optimize", "--budget=1000")
        cls.master = verdict("build_protect.py")
        cls.good = verdict("build_protect.py", *GAME)
        verdict("build_protect_watched.py")
        cls.watched = verdict("build_protect_watched.py", *GAME)

    def test_the_master_is_not_held_to_a_place_only_a_reduction_can_lose(self):
        self.assertEqual(self.master["status"], "pass", self.master["summary"][:300])
        self.assertNotIn("protected:", self.master["summary"])

    def test_the_steered_reduction_keeps_the_grooves(self):
        self.assertEqual(self.good["status"], "pass", self.good["summary"][:300])
        self.assertIn("protected: 1 of 1 places kept", self.good["summary"])
        g = kept("good")
        self.assertGreater(g["points_spared"], 50)
        self.assertLessEqual(g["studs_off"], g["holds"])

    def test_the_same_budget_unsteered_loses_them_and_says_so(self):
        self.assertEqual(self.watched["status"], "fail")
        bad = {c["name"]: str(c.get("value")) for c in self.watched["design"] if c["severity"] == "error"}
        self.assertIn("Grooves: the game version lies", bad["protected"])
        w, g = kept("watched"), kept("good")
        self.assertEqual(w["points_spared"], 0)
        self.assertGreater(w["studs_off"], 2 * g["studs_off"])     # (steering is what made the difference)


if __name__ == "__main__":
    unittest.main()
