"""test_vault_steering.py — the owner's three steering lines in the Obsidian inbox (kit/scripts/vault_migrate.py):
`- rule <dept> <words>` files a standing order, `- never <dept> <words>` a graveyard row, `- retire <words>` marks
the one lesson holding those words as superseded. Runs on a COPY of the vault (KIT_VAULT_ROOT) in a temp folder.
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

LESSON = """---
kind: lesson
area: sfx
date: 2026-10-01
---

zz-steering-test: a whoosh needs a pitch drop under 200 ms or it reads as wind
"""

INBOX = """# Verdict inbox

## New
- rule vfx zz-order: show ONE test frame before any reinterpretation
- never ui zz-grave: a HUD typed from flat rectangles
- retire zz-steering-test whoosh pitch drop
- retire the
- rule nowhere zz-bad department

## Filed
"""


def run(cwd, vault, *args):
    env = dict(os.environ, KIT_VAULT_ROOT=vault)
    p = subprocess.run([sys.executable, "-I", SCRIPT, *args], cwd=cwd, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-800:]
    return json.loads([line for line in p.stdout.splitlines() if line.startswith("{")][-1])


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


@unittest.skipUnless(os.path.isdir(VAULT), "no vault in this project")
class TestSteering(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = os.path.join(self.tmp, "vault")
        shutil.copytree(VAULT, self.vault)
        os.makedirs(os.path.join(self.vault, "sfx", "lessons"), exist_ok=True)
        self.lesson = os.path.join(self.vault, "sfx", "lessons", "2026-10-01-zz-steering-test.md")
        with open(self.lesson, "w", encoding="utf-8", newline="\n") as f:
            f.write(LESSON)
        with open(os.path.join(self.vault, "inbox.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(INBOX)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_each_steering_line_is_filed_where_it_belongs(self):
        counts = run(self.tmp, self.vault, "--only", "inbox")
        self.assertEqual(counts["inbox"], 3)
        # a standing order, made on first use, with the owner and the date
        orders = read(os.path.join(self.vault, "vfx", "orders.md"))
        self.assertIn("kind: orders", orders)
        self.assertIn("- zz-order: show ONE test frame before any reinterpretation (the owner,", orders)
        # a graveyard row in the owner's words
        self.assertIn("zz-grave: a HUD typed from flat rectangles", read(os.path.join(self.vault, "ui", "graveyard.md")))
        # the one matching lesson is superseded, its text kept
        lesson = read(self.lesson)
        self.assertIn('superseded_by: "the owner (inbox.md,', lesson)
        self.assertIn("a whoosh needs a pitch drop", lesson)
        # what could not be filed stays under New, each saying why
        new = read(os.path.join(self.vault, "inbox.md")).partition("## Filed")[0]
        self.assertIn("- retire the  <- not filed:", new)
        self.assertIn("lessons match - add words", new)
        self.assertIn("- rule nowhere zz-bad department  <- not filed: unknown department", new)

    def test_the_same_order_twice_is_one_order(self):
        run(self.tmp, self.vault, "--only", "inbox")
        with open(os.path.join(self.vault, "inbox.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("# Verdict inbox\n\n## New\n- rule vfx zz-order: show ONE test frame before any reinterpretation\n\n## Filed\n")
        run(self.tmp, self.vault, "--only", "inbox")
        orders = read(os.path.join(self.vault, "vfx", "orders.md"))
        self.assertEqual(orders.count("zz-order: show ONE test frame"), 1)


if __name__ == "__main__":
    unittest.main()
