"""release_archive.py - the two release files `lune run parallax upgrade` downloads from a GitHub release:

    parallax-v<version>.tar.gz          `git archive` of the tag, one top folder parallax-<version>/
    parallax-v<version>.tar.gz.sha256   its SHA-256 in sha256sum's form: "<digest>  <file name>"

Run in the kit's home (kit/.source) on a version tag whose kit/VERSION says that version. Nothing is uploaded: the
maintainer attaches both files to the GitHub release through their own account (CONTRIBUTING.md, "Releasing").

    python kit/scripts/release_archive.py v3.1.0 [--out <folder>]     (default: the folder above the repository)
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys


def emit(status, summary, next_action, **extra):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **extra}))
    return 0 if status == "pass" else 1


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=False)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("tag", help="the version tag, e.g. v3.1.0")
    ap.add_argument("--out", help="the folder to write the two files to (default: the one above the repository)")
    a = ap.parse_args(argv)
    m = re.fullmatch(r"v(\d+\.\d+\.\d+)", a.tag)
    if not m:
        return emit("fail", f"release archive: {a.tag!r} is not a version tag (vX.Y.Z)", "git tag -a vX.Y.Z")
    version = m.group(1)
    top = git(os.getcwd(), "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        return emit("fail", "release archive: not inside a git repository", "run it in the kit's home")
    root = top.stdout.strip()
    if not os.path.isfile(os.path.join(root, "kit", ".source")):
        return emit("fail", "release archive: this is not the kit's home (no kit/.source)", "run it in the kit's home")
    if git(root, "rev-parse", "--verify", "--quiet", f"refs/tags/{a.tag}").returncode != 0:
        return emit("fail", f"release archive: no tag {a.tag}", f'git tag -a {a.tag} -m "Parallax {a.tag}"')
    shipped = git(root, "show", f"{a.tag}:kit/VERSION")
    if shipped.returncode != 0 or shipped.stdout.strip() != version:
        return emit("fail", f"release archive: kit/VERSION at {a.tag} says {shipped.stdout.strip()!r}, not {version}",
                    "bump kit/VERSION, commit, and tag that commit")
    out = os.path.abspath(a.out or os.path.dirname(root))
    os.makedirs(out, exist_ok=True)
    name = f"parallax-v{version}.tar.gz"
    path = os.path.join(out, name)
    made = git(root, "archive", "--format=tar.gz", f"--prefix=parallax-{version}/", "-o", path, a.tag)
    if made.returncode != 0:
        return emit("fail", f"release archive: git archive failed: {made.stderr.strip()}", "check the tag")
    with open(path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    with open(path + ".sha256", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{digest}  {name}\n")
    return emit("pass", f"release archive: {name} ({os.path.getsize(path):,} bytes) and its .sha256 in {out}",
                f"attach both files to the GitHub release {a.tag} (through your own account)", sha256=digest,
                files=[path, path + ".sha256"])


if __name__ == "__main__":
    sys.exit(main())
