"""The animation tests written pytest-style (plain test_ functions with tmp_path / monkeypatch / parametrize) were
never run by `kit verify`: kit/test/python/run.py discovers unittest TestCases only, so 11 files (~100 tests) passed
by never running (found 2026-10-15 in the anim audit). This case runs them through pytest from the repo root - the
way they were written - and fails with pytest's own report when any of them fails."""
import glob
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
HERE = os.path.dirname(os.path.abspath(__file__))


def pytest_style_files():
    out = []
    for f in sorted(glob.glob(os.path.join(HERE, "test_anim_*.py")) + [os.path.join(HERE, "test_r6_rig_model.py")]):
        if os.path.basename(f) == os.path.basename(__file__) or not os.path.exists(f):
            continue
        with open(f, encoding="utf-8") as fh:
            src = fh.read()
        if re.search(r"^def test_", src, re.M) and "TestCase" not in src:
            out.append(f)
    return out


class AnimPytestSuite(unittest.TestCase):
    def test_every_pytest_style_anim_test_passes(self):
        files = pytest_style_files()
        self.assertGreaterEqual(len(files), 10, "the pytest-style anim test files went missing")
        if os.environ.get("KIT_PY_RUN_EACH") == "1":
            # under kit/test/python/run.py (owner 2026-11-20: the verify speed-up, zero coverage lost): run.py runs EVERY
            # one of these files through pytest itself, each on its own; running them all again here only doubled the
            # lane (624 s). What this case still guards: each file is one run.py hands to pytest, never to unittest
            # (where a pytest-style file reports `Ran 0 tests` and passes by not running)
            fn = re.compile(r"^def test_", re.M)
            for f in files:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    src = fh.read()
                self.assertTrue(
                    fn.search(src) and "unittest" not in src,
                    f"{os.path.basename(f)} would run under unittest in run.py and pass by not running",
                )
            return
        try:
            import pytest  # noqa: F401
        except ImportError:
            self.fail("pytest is not installed - these anim tests cannot run (pip install pytest)")
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in (HERE, os.environ.get("PYTHONPATH", "")) if p))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *files], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
        tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-25:])
        self.assertEqual(r.returncode, 0, f"pytest-style anim tests failed:\n{tail}")
        self.assertIn("passed", tail)


if __name__ == "__main__":
    unittest.main()
