"""test_vault_obsidian.py — the vault survives the owner using it in Obsidian (2026-10-18).

What Obsidian and its owner do to notes, applied to a COPY of the vault after a sync has brought it in step:
  - the properties panel re-serialises a note's whole frontmatter (block-style lists, wikilinks quoted, a new tag),
  - a remark typed under a verdict and under a lesson,
  - a verdict note renamed (Obsidian rewrites every link to it: alwaysUpdateLinks),
  - "New note" left empty and untitled inside a verdicts folder.
Then a dry-run sync must find NOTHING to file: before this test, one property edit made the next sync file the
verdict again (72 duplicate verdict notes and 13 duplicate golden/graveyard rows from one pass over the vault).
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SCRIPT = os.path.join(ROOT, "kit", "scripts", "vault_migrate.py")
VAULT = os.path.join(ROOT, "kit", "knowledge", "vault")


def obsidian_reserialise(text):
    """the frontmatter as Obsidian's property editor writes it back: one key per line, lists in block style with
    wikilinks quoted, strings with a colon quoted, and a `seen` tag added"""
    text = text.replace("\r\n", "\n")
    end = text.find("\n---\n", 4)
    out, has_tags = [], False
    for line in text[4:end].splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        if key == "tags":
            has_tags = True
        m = re.fullmatch(r"\[(.*)\]", value)
        if m:
            items = [x.strip().strip('"') for x in m.group(1).split(",") if x.strip()]
            if key == "tags":
                items.append("seen")
            out.append(f"{key}:")
            out += [f'  - "{x}"' if x.startswith("[[") else f"  - {x}" for x in items]
        else:
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = value[1:-1].replace('\\"', '"')
            out.append(f'{key}: "{value}"' if ":" in value or value[:1] in "[{#&*!|>%@`'" else f"{key}: {value}")
    if not has_tags:
        out += ["tags:", "  - seen"]
    return "---\n" + "\n".join(out) + "\n---\n" + text[end + 5:]


def sync(env, *args):
    r = subprocess.run([sys.executable, "-I", SCRIPT, *args], cwd=ROOT, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads([l for l in r.stdout.splitlines() if l.startswith("{")][-1])


@unittest.skipUnless(os.path.isdir(VAULT), "no vault in this project")
class TestVaultUnderObsidian(unittest.TestCase):
    def test_owner_edits_in_obsidian_are_never_filed_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = os.path.join(tmp, "vault")
            shutil.copytree(VAULT, copy)
            env = dict(os.environ, KIT_VAULT_ROOT=copy, KIT_VAULT_INBOX_SETTLE="0")
            sync(env)  # in step with every lane's store first
            notes = glob.glob(f"{copy}/*/verdicts/*.md") + glob.glob(f"{copy}/*/lessons/*.md")
            self.assertGreater(len(notes), 20)
            verdicts = sorted(glob.glob(f"{copy}/*/verdicts/*.md"))
            if len(verdicts) < 2:
                self.skipTest("the author's vault has fewer than 2 verdicts; not shipped with the kit")
            for p in notes:
                with open(p, encoding="utf-8") as f:
                    text = f.read()
                with open(p, "w", encoding="utf-8", newline="\n") as f:
                    f.write(obsidian_reserialise(text))
            verdicts = sorted(glob.glob(f"{copy}/*/verdicts/*.md"))
            lessons = sorted(glob.glob(f"{copy}/*/lessons/*.md"))
            for p in (verdicts[0], lessons[0]):
                with open(p, "a", encoding="utf-8", newline="\n") as f:
                    f.write("\nOwner remark: still true.\n")
            # rename one verdict and rewrite every link to it, as Obsidian does
            moved = verdicts[1]
            old = os.path.relpath(moved, copy)[:-3].replace("\\", "/")
            new = old.rsplit("/", 1)[0] + "/renamed by the owner"
            os.rename(moved, os.path.join(copy, new + ".md"))
            for p in glob.glob(f"{copy}/**/*.md", recursive=True):
                with open(p, encoding="utf-8") as f:
                    t = f.read()
                if f"[[{old}" in t:
                    with open(p, "w", encoding="utf-8", newline="\n") as f:
                        f.write(t.replace(f"[[{old}", f"[[{new}"))
            open(os.path.join(os.path.dirname(moved), "Untitled.md"), "w").close()
            counts = sync(env, "--dry-run")
            self.assertEqual(counts["verdicts"], 0, counts)
            self.assertEqual(counts["lessons"], 0, counts)
            self.assertEqual(counts["rows"], 0, counts)
            self.assertEqual(counts.get("refs", 0), 0, counts)
            with open(verdicts[0], encoding="utf-8") as f:
                self.assertIn("Owner remark", f.read())  # the owner's words are kept, never overwritten


if __name__ == "__main__":
    unittest.main()
