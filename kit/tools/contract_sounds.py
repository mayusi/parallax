"""contract_sounds.py - the sound names a sounds folder MAKES (a recipe <name>.json, or a member of a set in sets/),
for `kit contract` (kit/cmd/contract.luau): a contract's sound event whose sound no recipe makes is refused by name.
The same reading as `kit sfx catalog` (kit/audio/catalog.py made_sounds) - one source of truth.

    python kit/tools/contract_sounds.py <sounds dir> [<sounds dir> ...]    (one call: the sets import takes ~15 s)
Prints one JSON line {status, summary, next_action, names} - every name any of the folders makes.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "audio"))
import catalog  # noqa: E402


def main(argv):
    missing = [d for d in argv if not os.path.isdir(d)]
    if not argv or missing:
        print(json.dumps({"status": "fail", "summary": f"contract sounds: no folder {missing[0] if missing else '(none)'}",
                          "next_action": "python kit/tools/contract_sounds.py <sounds dir> [<sounds dir> ...]"}))
        return 1
    names = set()
    for d in argv:
        try:
            names |= set(catalog.made_sounds(d))
        except (ValueError, OSError, json.JSONDecodeError) as e:
            print(json.dumps({"status": "fail", "summary": f"contract sounds: {d} could not be read: {e}",
                              "next_action": "lune run kit sfx catalog (fix the recipe or set it names)"}))
            return 1
    print(json.dumps({"status": "pass", "summary": f"{len(names)} sound(s) made in {', '.join(argv)}",
                      "next_action": "none", "names": sorted(names)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
