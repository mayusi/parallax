"""kit/selftest/anim/cleanup/run.py — the PLANT op of a `kit anim derive` recipe (kit/anim/cleanup.py; the owner's
method lists 2026-11-13: motion capture cleanup), on a cut the owner loved given a skate it did not have.

    python kit/selftest/anim/cleanup/run.py good    the body drifts 0.05 studs a frame, so every planted foot skates:
                                                    after the op the BUILD's own foot-slide reading is back at the
                                                    cut's own, and only the root track changed
    python kit/selftest/anim/cleanup/run.py travel  the body drifts 0.2 studs a frame (10 studs): that is travel,
                                                    not skate - refused, the clip left as it was (this case FAILS)

Prints one JSON line {schema, status, summary, next_action}. Nothing is written."""
import copy
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C  # noqa: E402
import derive as D  # noqa: E402
import strike as S  # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def main(case):
    with open(LOVED, encoding="utf-8") as fh:
        clean = S.generate(json.load(fh))[0]
    rig = C.load_rig("r6")
    n = len(clean["times"])
    base = copy.deepcopy(clean)
    per = 0.05 if case == "good" else 0.2
    base["root"] = [[0, 0, 0, 1, per * i, 0, 0] for i in range(n)]
    D.load_clip = lambda name: copy.deepcopy(base)            # the recipe's source: the clip in memory
    try:
        made = D.derive({"name": "SelftestPlanted", "from": "Base", "ops": [{"op": "plant", "max_shift": 3.0}]})
    except ValueError as e:
        return out("fail", str(e), "key the travel as a root track (or say max_shift if the body is meant to be moved that far)")
    made = made[0] if isinstance(made, tuple) else made
    if case == "travel":
        return out("pass", "cleanup selftest: ten studs of travel were taken for a skate and removed", "kit/anim/cleanup.py")
    read = lambda c: C.metrics(c, rig)["feet"]["slide_max_studs_frame"]  # noqa: E731  (the build's own reading)
    own, skated, after = read(clean), read(base), read(made)
    wrong = []
    if skated <= 0.1:
        wrong.append(f"the fixture does not fail the build's foot-slide bar ({skated}; the cut's own {own})")
    if after > own + 0.003:
        wrong.append(f"planted feet still slide {after} studs a frame (the cut's own: {own})")
    if any(made[k] != base[k] for k in ("joints", "sword", "events", "times")):
        wrong.append("something other than the root track changed")
    if not np.allclose(np.array(made["root"])[:, :4], np.array(base["root"])[:, :4]):
        wrong.append("the root's turn changed")
    if wrong:
        return out("fail", "cleanup selftest: " + "; ".join(wrong), "kit/anim/cleanup.py")
    return out("pass", f"cleanup selftest: a loved cut given a skate (the build reads {skated} studs a frame) is planted back to its "
                       f"own feet ({after}; the cut's own {own}); only the root track changed", "none - proceed")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("good", "travel"):
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
