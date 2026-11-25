"""test_vault_sync.py — the vault's migration / sync script (kit/scripts/vault_migrate.py) is idempotent and the
notes it reads back carry the frontmatter the kit expects (mission 00 5.1: a test on the note format).

Runs the script as a subprocess with --dry-run from the project root (the script is a command, not a module).
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SCRIPT = os.path.join(ROOT, "kit", "scripts", "vault_migrate.py")
VAULT = os.path.join(ROOT, "kit", "knowledge", "vault")


def parse_frontmatter(text):
    assert text.startswith("---\n"), "a note starts with ---"
    end = text.find("\n---\n", 4)
    assert end > 0, "frontmatter closes"
    front = {}
    for line in text[4:end].splitlines():
        key, _, value = line.partition(":")
        front[key.strip()] = value.strip()
    return front, text[end + 5:]


@unittest.skipUnless(os.path.isdir(VAULT), "no vault in this project")
class TestVaultSync(unittest.TestCase):
    def test_sync_is_idempotent(self):
        """a sync into a COPY of the vault, then a dry run on that copy: the second pass writes nothing. (The live
        vault is not asserted in step with the stores: a lane records a verdict in its own store at any moment and
        `kit vault sync` pulls it in later — that is the lanes' timing, not a kit defect.)"""
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            copy = os.path.join(tmp, "vault")
            shutil.copytree(VAULT, copy)
            env = dict(os.environ, KIT_VAULT_ROOT=copy)
            first = subprocess.run([sys.executable, "-I", SCRIPT], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr[-800:])
            second = subprocess.run(
                [sys.executable, "-I", SCRIPT, "--dry-run"], cwd=ROOT, env=env, capture_output=True, text=True
            )
            self.assertEqual(second.returncode, 0, second.stderr[-800:])
            counts = json.loads([l for l in second.stdout.splitlines() if l.startswith("{")][-1])
        self.assertTrue(counts["dry_run"])
        self.assertEqual(counts["verdicts"], 0, counts)
        self.assertEqual(counts["lessons"], 0, counts)
        self.assertEqual(counts["rows"], 0, counts)
        self.assertEqual(counts["files_before"], counts["files_after"], counts)

    def test_every_verdict_note_has_the_record_fields(self):
        n = 0
        for dept in os.listdir(VAULT):
            vdir = os.path.join(VAULT, dept, "verdicts")
            if not os.path.isdir(vdir):
                continue
            for fn in os.listdir(vdir):
                if not fn.endswith(".md"):
                    continue
                with open(os.path.join(vdir, fn), encoding="utf-8") as fh:
                    front, body = parse_frontmatter(fh.read())
                self.assertEqual(front.get("kind"), "verdict", fn)
                self.assertEqual(front.get("area"), dept, fn)
                self.assertIn("name", front, fn)
                self.assertRegex(front.get("date", ""), r"^\d{4}-\d{2}-\d{2}", fn)
                self.assertIn(front.get("source"), ("owner", "inferred", "quoted"), fn)
                if "score" in front:
                    score = float(front["score"])
                    self.assertTrue(0 <= score <= 10, (fn, score))
                n += 1
        self.assertGreater(n, 0)


if __name__ == "__main__":
    unittest.main()
