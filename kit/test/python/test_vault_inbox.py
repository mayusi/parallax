"""test_vault_inbox.py — the owner's Obsidian inbox and the store-scoped sync (kit/scripts/vault_migrate.py).

Everything runs on a COPY of the vault (KIT_VAULT_ROOT) in a temp folder, with a temp working directory for the lane
stores, so no test verdict ever lands in the real record.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SCRIPT = os.path.join(ROOT, "kit", "scripts", "vault_migrate.py")
VAULT = os.path.join(ROOT, "kit", "knowledge", "vault")

INBOX = """# Verdict inbox

## New
- ui FieldHudTest 8 loved the dial, the needle has weight
- asset "test crate" 25 the planks read as plastic
- vfx broken line without a score
- banana thing 5 unknown kind

## Filed
- 2026-10-01 ui OldScreen 7/10 — an older filed line
"""


def run(cwd, vault, *args):
    env = dict(os.environ, KIT_VAULT_ROOT=vault)
    p = subprocess.run([sys.executable, "-I", SCRIPT, *args], cwd=cwd, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-800:]
    return json.loads([l for l in p.stdout.splitlines() if l.startswith("{")][-1])


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(os.path.isdir(VAULT), "no vault in this project")
class TestInbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, "vault")
        shutil.copytree(VAULT, self.vault)
        with open(os.path.join(self.vault, "inbox.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(INBOX)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_inbox_files_readable_lines_and_keeps_the_rest(self):
        counts = run(self.tmp, self.vault, "--only", "inbox")
        self.assertEqual(counts["inbox"], 2)
        text = read(os.path.join(self.vault, "inbox.md"))
        new, _, filed = text.partition("## Filed")
        # the two readable lines moved to Filed with a link; the old filed line kept below them
        self.assertNotIn("FieldHudTest", new)
        self.assertIn("ui FieldHudTest 8.0/10", filed)
        self.assertIn("3d test crate 2.5/10", filed)
        self.assertIn("[[ui/verdicts/fieldhudtest--", filed)
        self.assertIn("OldScreen", filed)
        # unreadable lines stay under New, each saying why
        self.assertIn("vfx broken line without a score  <- not filed:", new)
        self.assertIn("banana thing 5 unknown kind  <- not filed: unknown kind", new)
        # notes + golden / graveyard rows
        ui_notes = os.listdir(os.path.join(self.vault, "ui", "verdicts"))
        self.assertTrue(any(n.startswith("fieldhudtest--") for n in ui_notes))
        self.assertIn("FieldHudTest", read(os.path.join(self.vault, "ui", "golden.md")))
        self.assertIn("test crate", read(os.path.join(self.vault, "3d", "graveyard.md")))

    def test_inbox_is_idempotent(self):
        run(self.tmp, self.vault, "--only", "inbox")
        first = read(os.path.join(self.vault, "inbox.md"))
        counts = run(self.tmp, self.vault, "--only", "inbox")
        self.assertEqual(counts.get("inbox", 0), 0)
        self.assertEqual(read(os.path.join(self.vault, "inbox.md")), first)

    def test_store_scoped_sync_files_a_lane_verdict_and_stamps_it(self):
        lib = os.path.join(self.tmp, "library", "vfx")
        os.makedirs(lib)
        with open(os.path.join(lib, "verdicts.json"), "w", encoding="utf-8") as f:
            json.dump({"test_burst": [{"date": "2026-10-17", "words": "the flash reads", "score": 8}]}, f)
        counts = run(self.tmp, self.vault, "--only", "vfx")
        self.assertEqual(counts["stores"], ["vfx"])
        self.assertEqual(counts["verdicts"], 1)
        notes = os.listdir(os.path.join(self.vault, "vfx", "verdicts"))
        self.assertTrue(any(n.startswith("test-burst--2026-10-17") for n in notes))
        stamps = json.loads(read(os.path.join(self.tmp, ".verify", "vault_sync.json")))
        self.assertEqual(list(stamps), ["vfx"])

    def test_board_decisions_are_filed_once_under_their_department(self):
        d = os.path.join(self.tmp, "board", "decisions")
        os.makedirs(d)
        with open(os.path.join(d, "2026-10-17T0900Z-locomotion-rig-test.md"), "w", encoding="utf-8") as f:
            f.write("# Locomotion rig test\n\n- date: 2026-10-17\n- by: tester\n\n## Decision\nuse the R6 rig\n\n## Why\nbecause\n")
        counts = run(self.tmp, self.vault, "--only", "decisions")
        self.assertEqual(counts.get("decisions"), 1)
        notes = os.listdir(os.path.join(self.vault, "anim", "decisions"))
        self.assertTrue(any(n.startswith("2026-10-17-locomotion-rig-test") for n in notes))
        again = run(self.tmp, self.vault, "--only", "decisions")
        self.assertEqual(again.get("decisions", 0), 0)

    def test_unknown_store_is_refused(self):
        env = dict(os.environ, KIT_VAULT_ROOT=self.vault)
        p = subprocess.run([sys.executable, "-I", SCRIPT, "--only", "nope"], cwd=self.tmp, env=env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
