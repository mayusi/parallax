"""The references solved together, through REAL builds (kit/selftest/blender/build_agree.py and its twins; his
D-R01; the 3D methods audit, stage L): statements that agree are said; one that does not fit the others fails the
build by name; a model built off what they agree on is flagged."""

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
OUT = os.path.join("build", "_test_agree_build")


def verdict(script):
    e = dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT)
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "blender", script), "--", "--no-preview"],
                       cwd=ROOT, capture_output=True, text=True, timeout=1800, env=e, encoding="utf-8",
                       errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)   # (strict: the kit reads this line the same way)


def named(v, name):
    return next((c for c in v["design"] if c["name"] == name), None)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = verdict("build_agree.py")
        cls.odd = verdict("build_agree_odd.py")
        cls.tall = verdict("build_agree_tall.py")

    def test_statements_that_agree_are_said_and_nothing_is_flagged(self):
        self.assertEqual(self.good["status"], "pass", self.good["summary"][:300])
        self.assertIn("references: 4 statements agree", self.good["summary"])
        self.assertIsNone(named(self.good, "reference_agree"))
        self.assertIsNone(named(self.good, "reference_fit"))

    def test_the_one_statement_that_does_not_fit_fails_the_build_and_only_it_is_named(self):
        self.assertEqual(self.odd["status"], "fail")
        c = named(self.odd, "reference_agree")
        self.assertEqual(c["severity"], "error")
        self.assertEqual(len(c["value"]), 1, c["value"])          # (the drawing and the first photo agree)
        self.assertTrue(c["value"][0].startswith("another side photo says height is 0.33 of the length; the "
                                                 "other references together say 0.25"), c["value"][0])

    def test_a_model_built_off_what_its_references_agree_on_is_flagged(self):
        c = named(self.tall, "reference_fit")
        self.assertEqual(c["severity"], "warn")
        self.assertEqual(c["value"], ["its height is 300 mm; the references agree on 250 (20% off)"])
        self.assertIsNone(named(self.tall, "reference_agree"))


if __name__ == "__main__":
    unittest.main()
