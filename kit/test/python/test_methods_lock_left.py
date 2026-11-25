"""What the methods lock's review left (card 988z): a plan line is read for sense - a call it only DENIES ("a.box
each; no a.repeat") is not one it names; the lock switched off from the environment on a real piece is said."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_plan as P  # noqa: E402


class Sense(unittest.TestCase):
    def test_a_denial_names_nothing(self):
        self.assertEqual(P.named_calls("a.box each; no a.repeat"), ["box"])
        self.assertEqual(P.named_calls("a.sweep, not a.tube"), ["sweep"])
        self.assertEqual(P.named_calls("instead of a.loft: a.sweep"), ["sweep"])
        self.assertEqual(P.named_calls("without a.scatter, not by a.repeat"), [])
        self.assertEqual(P.named_calls("Teeth x12 by a.repeat"), ["repeat"])
        self.assertEqual(P.named_calls("a.repeat, no a.repeat of the cap"), ["repeat"])   # (one denial, one mention)

    def test_the_check_holds_only_what_is_named(self):
        plan = [{"name": "Serrations x9", "shape": "a.box each; no a.repeat", "routes": ["code"]}]
        c = P.methods_check(plan, {}, [])
        self.assertTrue(c["ok"], c)          # (the plan never asked for a repeat: none is missing)
        plan = [{"name": "Serrations x9", "shape": "a.box in a.repeat", "routes": ["code"]}]
        self.assertFalse(P.methods_check(plan, {}, [])["ok"])


class Off(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("KIT_METHODS_LOCK", None)

    def test_switched_off_on_a_piece_is_said_and_on_a_fixture_not(self):
        os.environ["KIT_METHODS_LOCK"] = "0"
        piece = os.path.join(ROOT, "assets", "models", "build_anything.py")
        fixture = os.path.join(ROOT, "kit", "selftest", "blender", "build_cast.py")
        self.assertIn("KIT_METHODS_LOCK=0", P.lock_forced_off(piece))
        self.assertIsNone(P.lock_forced_off(fixture))
        os.environ.pop("KIT_METHODS_LOCK")
        self.assertIsNone(P.lock_forced_off(piece))


BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class Blockout(unittest.TestCase):
    def test_a_geo_blockout_round_is_not_held_and_a_geo_round_is(self):
        """card 988z (8): "a --geo --blockout round is now skipped by the build check: no test builds one" - the
        typed-bolts fixture, locked: a blockout round names no methods fault, a plain --geo round does"""
        env = dict(os.environ, KIT_METHODS_LOCK="1")
        fix = os.path.join(ROOT, "kit", "selftest", "blender", "build_lock_typed.py")

        def names(*args):
            out = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", fix, "--", *args], cwd=ROOT,
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                                 env=env)
            k = out.stdout.find('{"schema"')
            st = json.JSONDecoder().raw_decode(out.stdout[k:])[0]
            return {c["name"] for c in st["design"] if not c["ok"]}
        self.assertNotIn("methods", names("--geo", "--blockout"))
        self.assertIn("methods", names("--geo"))


if __name__ == "__main__":
    unittest.main()
