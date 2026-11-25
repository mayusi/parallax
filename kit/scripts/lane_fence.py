"""lane_fence.py — refuse a commit that changes two lanes' own files (or links a missing verdict note).

The checkout is shared by several sessions, one per department ("lane"). `kit/knowledge/lanes.json` lists each
lane's EXCLUSIVE paths; a commit that touches two or more of them is usually a session reaching into another lane's
work, unless its message says `cross` on purpose. Everything not listed there is shared.

Run from the project root:
  python kit/scripts/lane_fence.py --commit-msg .git/COMMIT_EDITMSG   # git commit-msg hook (GIT_INDEX_FILE is inherited)
  python kit/scripts/lane_fence.py --replay 80                        # what the last 80 commits would have done

Mode lives in lanes.json: "warn" prints only, "enforce" exits 1 on a refusal.
"""

import argparse
import json
import re
import subprocess
import sys

GAME_PREFIX = re.compile(r"^games/[^/]+/")
CROSS_WORD = re.compile(r"\bcross\b", re.IGNORECASE)
# [[dept/verdicts/note]] or [[dept/verdicts/note|shown text]] (an Obsidian alias is not part of the note's name)
ROW_LINK = re.compile(r"\[\[([^/\]|]+)/verdicts/([^\]|\n]+)(?:\|[^\]]*)?\]\]")


def load_lanes(path="kit/knowledge/lanes.json"):
    """The parsed lanes.json: {"about": ..., "mode": ..., "lanes": {lane: [prefix, ...]}}."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _lane_map(lanes):
    """The {lane: prefixes} mapping; accept either the whole config or just its "lanes" part."""
    if isinstance(lanes, dict) and isinstance(lanes.get("lanes"), dict):
        return lanes["lanes"]
    return lanes


def _together(lanes):
    """The together groups from a whole config; a bare lane map has none."""
    if isinstance(lanes, dict) and "lanes" in lanes:
        return lanes.get("together", [])
    return []


def _group_key(lane, together):
    """A lane's group key: its together members sorted and +-joined, else the lane itself."""
    for group in together:
        if lane in group:
            return "+".join(sorted(group))
    return lane


def lane_of(path, lanes):
    """The lane owning `path`, or None when it is shared or a placeholder (.gitkeep)."""
    path = path.replace("\\", "/")
    path = GAME_PREFIX.sub("", path, count=1)
    if path.rsplit("/", 1)[-1] == ".gitkeep":
        return None
    for lane, prefixes in _lane_map(lanes).items():
        if any(path.startswith(prefix) for prefix in prefixes):
            return lane
    return None


def check(files, message, lanes):
    """(ok, reasons): a commit touching two or more lane groups needs the whole word `cross` in its message."""
    together = _together(lanes)
    groups = sorted(
        {
            _group_key(lane, together)
            for lane in (lane_of(f, lanes) for f in files)
            if lane is not None
        }
    )
    if len(groups) >= 2 and not CROSS_WORD.search(message):
        reason = (
            f"touches the own files of {len(groups)} lanes ({', '.join(groups)}) - split the commit, "
            "or put the word cross in the message if it is meant"
        )
        return False, [reason]
    return True, []


def check_rows(added_lines, present):
    """Reasons for golden/graveyard rows linking a verdict note missing from both the commit and the tree."""
    reasons = []
    for line in added_lines:
        for dept, note in ROW_LINK.findall(line):
            if not present(f"kit/knowledge/vault/{dept}/verdicts/{note}.md"):
                reasons.append(
                    f"a golden/graveyard row links {dept}/verdicts/{note}, which is not in the commit or the tree "
                    "- commit the verdict note with it"
                )
    return reasons


def _git(*args):
    """Run git without a shell; a commit-msg hook's GIT_INDEX_FILE is inherited from the environment."""
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def _git_lines(*args):
    return [line for line in _git(*args).stdout.splitlines() if line]


def first_commit():
    """A repository with no commit at all yet: the commit being made is the project's first - its install (`kit
    install` copies every lane's files in at once), which the fence does not split. Any commit anywhere (another
    branch, an orphan branch's sibling) means it is not: `git checkout --orphan` is no way round the fence."""
    r = _git("rev-list", "-n", "1", "--all")
    return r.returncode == 0 and r.stdout.strip() == ""


def commit_hook(commit_msg, lanes):
    """The hook path: staged files, the message without comment lines, and golden/graveyard row links."""
    if first_commit():
        print("lane fence: the project's first commit (its install) spans every lane - not fenced; the fence starts now")
        return 0
    files = _git_lines("diff", "--cached", "--name-only")
    with open(commit_msg, encoding="utf-8") as fh:
        message = "\n".join(line for line in fh.read().splitlines() if not line.startswith("#"))
    diff = _git(
        "diff",
        "--cached",
        "-U0",
        "--",
        "kit/knowledge/vault/*/golden.md",
        "kit/knowledge/vault/*/graveyard.md",
    )
    added = [
        line
        for line in diff.stdout.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]

    def present(path):
        return subprocess.run(["git", "cat-file", "-e", f":{path}"], capture_output=True).returncode == 0

    ok, reasons = check(files, message, lanes)
    reasons += check_rows(added, present)
    mode = lanes.get("mode", "warn")
    for reason in reasons:
        if mode == "enforce":
            print(f"lane fence: {reason}")
        else:
            print(f"lane fence (warn mode, not refused): {reason}")
    return 1 if reasons and mode == "enforce" else 0


def replay(n, lanes):
    """Print what the last N commits would do; warn-only, and always exit 0."""
    shas = _git_lines("log", f"-{n}", "--format=%H")
    refused = 0
    for sha in shas:
        files = _git_lines("show", "--name-only", "--format=", sha)
        message = _git("log", "-1", "--format=%B", sha).stdout
        ok, reasons = check(files, message, lanes)
        if not ok:
            refused += 1
            first = message.splitlines()[0][:70] if message.splitlines() else ""
            print(f"{sha[:7]} {first} -> {reasons[0]}")
    print(f"replay: {refused} of {len(shas)} commit(s) would be refused")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Refuse a commit that mixes two lanes' exclusive files.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--commit-msg", metavar="FILE", help="hook mode: the commit message file to inspect")
    group.add_argument("--replay", type=int, metavar="N", help="warn-only replay of the last N commits")
    args = parser.parse_args(argv)

    lanes = load_lanes()
    if args.commit_msg is not None:
        return commit_hook(args.commit_msg, lanes)
    return replay(args.replay, lanes)


if __name__ == "__main__":
    sys.exit(main())
