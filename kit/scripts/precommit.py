"""precommit.py — the commit gate every session hits (git pre-commit hook, installed by `lune run kit harness`).

The committed tree is shared by several sessions; one commit with an unformatted or lint-failing file turns
`kit prove` red for every lane. So a commit is refused when a STAGED file fails the two cheap gates `kit verify`
runs on the whole tree: the format check (stylua) and selene for Luau, and a byte-compile for Python. Only the staged
files are checked (seconds, not minutes). A missing tool is skipped with a note, never a refusal.

    python kit/scripts/precommit.py          (the hook; GIT_INDEX_FILE is inherited from `git commit -- <paths>`)
"""

import os
import shutil
import subprocess
import sys


def staged():
    """the files this commit adds, copies, modifies or renames (paths with spaces kept whole)"""
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    return [f for f in out.split("\0") if f and os.path.isfile(f)]


def tool(name):
    """a tool on PATH, or in rokit's folder (where `rokit install` puts lune / stylua / selene)"""
    found = shutil.which(name)
    if found:
        return found
    home = os.path.expanduser("~")
    for ext in ("", ".exe"):
        p = os.path.join(home, ".rokit", "bin", name + ext)
        if os.path.isfile(p):
            return p
    return None


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout + p.stderr).strip()


def main():
    files = staged()
    luau = [f for f in files if f.endswith((".luau", ".lua"))]
    py = [f for f in files if f.endswith(".py")]
    problems = []
    if luau:
        stylua = tool("stylua")
        if stylua:
            code, out = run([stylua, "--check", "--respect-ignores", *luau])
            if code != 0:
                bad = sorted({line.split("Diff in ", 1)[1].rstrip(":") for line in out.splitlines() if line.startswith("Diff in ")})
                problems.append("not formatted: " + (", ".join(bad) or out[:300])
                                + "  -> fix: stylua " + " ".join(bad or luau))
        else:
            print("pre-commit: stylua not found - format check skipped (rokit install)")
        selene = tool("selene")
        if selene:
            code, out = run([selene, "--display-style", "quiet", *luau])
            if code != 0:
                lines = [line for line in out.splitlines() if ": warning[" in line or ": error[" in line][:8]
                problems.append("selene: " + ("; ".join(lines) or out[:400]) + "  -> fix the code (kit verify runs the same check)")
        else:
            print("pre-commit: selene not found - lint skipped (rokit install)")
    for f in py:
        try:  # compiled in memory: nothing is written (py_compile cannot target os.devnull on Windows)
            with open(f, "rb") as fh:
                compile(fh.read(), f, "exec")
        except (SyntaxError, ValueError) as e:
            problems.append(f"python does not compile: {f}: {str(e)[:200]}")
    # the Parallax backstop (PARALLAX spec §2.3 layer 4): the cases' anti-patterns on the staged pipeline files and
    # `parallax harness --check` (a connected client's stale config or hooks, an older kit's client files left behind)
    guard = os.path.join(os.path.dirname(os.path.abspath(__file__)), "parallax_guard.py")
    if os.path.isfile(guard):
        sys.path.insert(0, os.path.dirname(guard))
        import parallax_guard  # noqa: PLC0415

        if parallax_guard.pre_commit(sys.argv[1:]) != 0:
            problems.append("the Parallax pre-commit check refused (its reasons are printed above)")
    if problems:
        print("pre-commit: refused - this commit would turn the shared tree red:")
        for p in problems:
            print("  - " + p)
        print("  (only your staged files were checked; fix them, stage again, commit again - never --no-verify)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
