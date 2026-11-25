"""kit/scripts/vault_migrate.py --check / `pending`: the dry run's `pending` is everything a sync would file, --check
exits 1 while there is any, and a real run clears it - including an inbox `retire` line no lesson matches: the real run
marks it "not filed" for the owner, and from then on it is no longer pending (it used to keep CI red forever)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(HERE, "..", "..", "scripts", "vault_migrate.py"))


def run(cwd, vault, *args):
    env = dict(os.environ, KIT_VAULT_ROOT=vault)
    p = subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd, capture_output=True, text=True, timeout=300, env=env)
    lines = [json.loads(x) for x in p.stdout.strip().splitlines() if x.startswith("{")]
    return p.returncode, lines


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, "vault")
        os.makedirs(self.vault)
        with open(os.path.join(self.vault, "inbox.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("# Inbox\n\n## New\n\n- retire no lesson anywhere says these exact words zqxv\n\n## Filed\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_an_unfileable_retire_line_stops_being_pending_after_one_real_run(self):
        code, lines = run(self.tmp, self.vault, "--check", "--only", "inbox")
        self.assertEqual(code, 1)
        self.assertEqual(lines[0]["pending"], 1)
        code, lines = run(self.tmp, self.vault, "--only", "inbox")  # (the real run: marks it "not filed")
        self.assertEqual(code, 0)
        self.assertNotIn("pending", lines[0])  # (a real run reports what it filed, not "pending")
        with open(os.path.join(self.vault, "inbox.md"), encoding="utf-8") as fh:
            self.assertIn("<- not filed:", fh.read())
        code, lines = run(self.tmp, self.vault, "--check", "--only", "inbox")
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[0]["pending"], 0)
        code, lines = run(self.tmp, self.vault, "--dry-run", "--only", "inbox")
        self.assertEqual(code, 0)
        self.assertEqual(lines[0]["pending"], 0)


if __name__ == "__main__":
    unittest.main()
