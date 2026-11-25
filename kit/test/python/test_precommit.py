"""test_precommit.py — the commit gate (kit/scripts/precommit.py) refuses a staged file that would turn the shared tree
red and lets a clean one through. Runs in a throwaway git repository; only the Python check is exercised here (the
stylua / selene checks need the project's tool configs and are proven by hand in the kit lane's handoff)."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.abspath(os.path.join(HERE, "..", "..", "scripts", "precommit.py"))


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@unittest.skipUnless(shutil.which("git"), "git not on PATH")
class TestPrecommit(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        git(self.repo, "init", "-q")

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def gate(self, name, text):
        with open(os.path.join(self.repo, name), "w", encoding="utf-8") as f:
            f.write(text)
        git(self.repo, "add", name)
        return subprocess.run([sys.executable, SCRIPT], cwd=self.repo, capture_output=True, text=True)

    def test_clean_python_passes(self):
        self.assertEqual(self.gate("ok.py", "x = 1\n").returncode, 0)

    def test_broken_python_is_refused_with_the_file_named(self):
        p = self.gate("bad.py", "def x(:\n")
        self.assertEqual(p.returncode, 1)
        self.assertIn("bad.py", p.stdout)
        self.assertIn("never --no-verify", p.stdout)


if __name__ == "__main__":
    unittest.main()
