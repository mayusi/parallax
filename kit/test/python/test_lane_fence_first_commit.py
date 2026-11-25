"""The lane fence (kit/scripts/lane_fence.py) and a project's FIRST commit: `kit install` copies every lane's files in at
once, so the commit a new project starts with (no HEAD yet) is not fenced; every commit after it is - two lanes' own
files in one commit are refused unless the message says `cross`."""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "scripts"))

import lane_fence  # noqa: E402

LANES = {"mode": "enforce", "lanes": {"3d": ["assets/models/"], "vfx": ["assets/effects/"]}, "together": []}


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd,
                          capture_output=True, text=True, check=False)


class FirstCommitIsNotFenced(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        git(self.tmp, "init", "-q")
        for rel in ("assets/models/a.py", "assets/effects/b.json"):
            os.makedirs(os.path.join(self.tmp, os.path.dirname(rel)), exist_ok=True)
            with open(os.path.join(self.tmp, rel), "w", encoding="utf-8") as fh:
                fh.write("x\n")
        git(self.tmp, "add", "-A")
        self.msg = os.path.join(self.tmp, "MSG")
        with open(self.msg, "w", encoding="utf-8") as fh:
            fh.write("Start from Parallax\n")
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.cwd)

    def test_the_first_commit_passes_and_the_next_two_lane_commit_is_refused(self):
        self.assertTrue(lane_fence.first_commit())
        self.assertEqual(lane_fence.commit_hook(self.msg, LANES), 0)
        git(self.tmp, "commit", "-q", "--no-verify", "-m", "Start from Parallax")
        self.assertFalse(lane_fence.first_commit())
        for rel in ("assets/models/a.py", "assets/effects/b.json"):
            with open(os.path.join(self.tmp, rel), "a", encoding="utf-8") as fh:
                fh.write("y\n")
        git(self.tmp, "add", "-A")
        self.assertEqual(lane_fence.commit_hook(self.msg, LANES), 1)  # (two lanes, no `cross`)

    def test_an_orphan_branch_is_no_first_commit(self):
        git(self.tmp, "commit", "-q", "--no-verify", "-m", "Start from Parallax")
        git(self.tmp, "checkout", "-q", "--orphan", "fresh-start")  # (an unborn HEAD in a repository with history)
        for rel in ("assets/models/a.py", "assets/effects/b.json"):
            with open(os.path.join(self.tmp, rel), "a", encoding="utf-8") as fh:
                fh.write("z\n")
        git(self.tmp, "add", "-A")
        self.assertFalse(lane_fence.first_commit())
        self.assertEqual(lane_fence.commit_hook(self.msg, LANES), 1)


if __name__ == "__main__":
    unittest.main()
