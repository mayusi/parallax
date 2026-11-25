"""locks_grandfather.py — regenerate board/locks.json (the pieces that existed before the quality locks).

Run from the project root:  python kit/scripts/locks_grandfather.py   (kit install runs it once, when the file is
missing; once it exists, only with --again "<the owner's words>")

Every lane lists the project-relative, `/`-separated files that exist NOW, at the root and inside every
games/<Name>/. Files made before the locks (2026-10-21) are exempt from them (grandfathered). The owner's
`approvals`, `waivers` and the `proposals` are kept from the old file (written by `kit approve`), never regenerated.
"""

import json
import sys
from datetime import date
from pathlib import Path

OUT = Path("board/locks.json")  # per project: board/ is the project's own record

ABOUT = (
    "Pieces that existed before the quality locks (2026-10-21) are exempt from them (grandfathered). "
    "approvals: the owner's go-ahead for one piece (its chart, references or brief); waivers: the owner allowing one "
    "piece to skip a step. Both are written by `kit approve`, each {by: 'owner', words, date}. "
    "Regenerate the list only by running kit/scripts/locks_grandfather.py on purpose."
)

# each lane's files: (glob, drop names starting with "_"). The underscore rule is for the lane's top-level
# folder only (the SFX sets and the dossier folders are collections, not one-off pieces).
PATTERNS = {
    "ui": [
        ("assets/ui/*.json", False),
        ("games/*/assets/ui/*.json", False),
    ],
    "sfx": [
        ("assets/sounds/*.json", True),
        ("assets/sounds/sets/*.json", False),
        ("games/*/assets/sounds/*.json", True),
        ("games/*/assets/sounds/sets/*.json", False),
    ],
    "3d": [
        ("assets/models/*.py", False),
        ("games/*/assets/models/*.py", False),
    ],
    "world": [
        ("assets/worlds/*.json", False),
        ("games/*/assets/worlds/*.json", False),
    ],
    "anim": [
        ("assets/animations/dossiers/*.json", False),
        ("games/*/assets/animations/dossiers/*.json", False),
    ],
    "vfx": [
        ("assets/effects/*.json", True),
        ("games/*/assets/effects/*.json", True),
    ],
}


def old_record(key):
    """The approvals or waivers already in locks.json: only the owner's record, never regenerated."""
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(data, dict) and isinstance(data.get(key), dict):
        return data[key]
    return {}


def lane_files(lane):
    """Sorted, project-relative files for one lane that exist right now."""
    found = set()
    for pattern, drop_underscore in PATTERNS[lane]:
        for path in Path(".").glob(pattern):
            if path.is_file() and not (drop_underscore and path.name.startswith("_")):
                found.add(path.as_posix())
    return sorted(found)


def main():
    # re-running it would grandfather every piece made since the locks: only on purpose, with the owner's words
    if OUT.exists() and "--again" not in sys.argv:
        print(json.dumps({
            "status": "fail",
            "summary": f"locks: {OUT} exists - regenerating would exempt every piece made since the locks",
            "next_action": 'only when the owner asks: python kit/scripts/locks_grandfather.py --again "<their words>"',
        }))
        return 1
    grandfathered = {lane: lane_files(lane) for lane in PATTERNS}
    data = {
        "about": ABOUT,
        "date": date.today().isoformat(),
        "grandfathered": grandfathered,
        "approvals": old_record("approvals"),
        "proposals": old_record("proposals"),
        "waivers": old_record("waivers"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    total = sum(len(files) for files in grandfathered.values())
    lanes = sum(1 for files in grandfathered.values() if files)
    print(json.dumps({"status": "pass", "summary": f"locks: {total} piece(s) grandfathered across {lanes} lanes"}))


if __name__ == "__main__":
    sys.exit(main())
