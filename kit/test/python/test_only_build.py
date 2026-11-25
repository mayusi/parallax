"""--geo --only <part words> (H3, his limitations review 2026-11-17: "skip unrelated parts ... < 30 s"): a shape round
of the parts whose names hold the words, alone, its whole-model checks said as warnings - on the kits fixture
(kit/selftest/blender/build_kits.py: Base, Knob, Puff, Wing)."""

import json
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
FIXTURE = os.path.join(ROOT, "kit", "selftest", "blender", "build_kits.py")
LENDER = os.path.join(ROOT, "kit", "selftest", "blender", "build_topology.py")
OUT = os.path.join("build", "_test_only_build")  # (its own build root, as test_kits_build's: never a project's build/models)


def run(*args, script=FIXTURE, timeout=600):
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", *args],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                         env=dict(os.environ, KIT_GAME="none", KIT_BUILD=OUT))
    lines = [ln for ln in out.stdout.splitlines() if ln.startswith("{") and '"status"' in ln]
    return out.returncode, (json.loads(lines[-1]) if lines else None), out.stdout + out.stderr


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class OnlyBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # the kits fixture kitbashes the drum of _selftest_topology_good: that build first, in this test's own root (as
        # test_kits_build does) - a fresh checkout has no build/ at all
        cls.lender = run("--no-preview", script=LENDER, timeout=1800)
        cls.whole = run("--no-preview", timeout=1800)  # (a whole build first: the fixture reads its manifest after a round)
        cls.only = run("--geo", "--only", "wing")
        cls.full = run("--geo")

    def test_one_part_is_kept_and_said(self):
        code, v, log = self.only
        self.assertEqual(code, 0, log[-2000:])
        self.assertIn("ONLY Wing (1 part)", v["summary"])
        self.assertEqual(v["status"], "pass", v["summary"])

    def test_the_whole_models_checks_are_warnings_there_and_errors_in_a_full_round(self):
        _c, v, _l = self.only
        size = [c for c in v["design"] if c["name"] == "size_vs_target"]
        self.assertTrue(size and size[0]["severity"] == "warn" and "--only" in size[0].get("note", ""), size)
        _c, full, _l = self.full
        self.assertNotIn("ONLY", full["summary"])
        self.assertTrue(all(c.get("severity", "error") != "warn" or c["name"] != "size_vs_target"
                            for c in full["design"]))

    def test_no_part_named_lists_the_parts(self):
        code, _v, log = run("--geo", "--only", "nosuch")
        self.assertNotEqual(code, 0)
        self.assertIn("the parts of this model: Base, Knob, Puff, Wing", log)

    def test_a_full_build_of_some_parts_is_refused(self):
        code, _v, log = run("--only", "wing")
        self.assertNotEqual(code, 0)
        self.assertIn("--only <part> is for a shape round", log)


if __name__ == "__main__":
    unittest.main()
