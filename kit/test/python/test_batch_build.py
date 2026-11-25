"""What a model costs to draw, through REAL builds (kit/selftest/blender/build_batch.py and its twin; the 3D methods
audit, stage O): solid groups that never move apart and see-through parts stacked deep are counted and said; a
plain model with one pane is not."""

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
OUT = os.path.join("build", "_test_batch_build")


def run(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)   # (strict: the kit reads this line the same way)


def design(v, name):
    return next(c for c in v["design"] if c["name"] == name)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.poor = run("build_batch.py")
        cls.fine = run("build_batch_fine.py")

    def test_solid_groups_that_never_move_apart_are_counted_and_said(self):
        b = self.poor["facts"]["batch"]
        self.assertEqual(b["draws"], 7)                                  # six blocks and the panes
        self.assertEqual(len(b["solid"]), 6)
        self.assertEqual(b["see_through"], ["glass"])
        c = design(self.poor, "draw_calls")
        self.assertFalse(c["ok"])
        self.assertEqual(c["severity"], "warn")
        self.assertIn("6 solid groups never move apart", c["fix"])

    def test_see_through_parts_stacked_deep_are_counted_and_said(self):
        seen = self.poor["facts"]["batch"]["layers"]
        self.assertEqual(seen["most"], 8)                                # eight panes, the face of each that faces the eye
        self.assertGreater(seen["p95"], 4)
        c = design(self.poor, "overdraw")
        self.assertFalse(c["ok"])
        self.assertIn("crosses up to 8 see-through layers", c["fix"])

    def test_a_plain_model_with_one_pane_is_not_said(self):
        b = self.fine["facts"]["batch"]
        self.assertEqual((b["draws"], b["solid"], b["see_through"]), (2, ["main"], ["glass"]))
        self.assertEqual(b["layers"]["most"], 1)
        # (the verdict lists the design checks that did NOT hold: neither is among them)
        self.assertEqual([c["name"] for c in self.fine["design"] if c["name"] in ("draw_calls", "overdraw")], [])


if __name__ == "__main__":
    unittest.main()
