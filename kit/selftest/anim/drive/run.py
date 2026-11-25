"""kit/selftest/anim/drive/run.py — the DRIVER op of a `kit anim derive` recipe (kit/anim/drivers.py; the owner's
method lists 2026-11-13: driver / expression-driven animation), on a cut the owner loved, generated in memory.

    python kit/selftest/anim/drive/run.py good   the head is given half the turn the torso has made: at every frame
                                                 twice what was added IS the torso's turn; the first frame, every
                                                 other joint and the blade are as they were
    python kit/selftest/anim/drive/run.py arm    the sword arm driven by the torso: it would take the hand off the
                                                 weapon - refused, the clip left as it was (this case FAILS)

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
        base = S.generate(json.load(fh))[0]
    D.load_clip = lambda name: copy.deepcopy(base)            # the recipe's source: the clip in memory
    op = ({"op": "drive", "joint": "Head", "by": "Torso", "weight": 0.5} if case == "good"
          else {"op": "drive", "joint": "Right Arm", "by": "Torso", "weight": 1.0})
    try:
        made = D.derive({"name": "SelftestDriven", "from": "Base", "ops": [op]})
    except ValueError as e:
        return out("fail", str(e), "drive a joint that does not hold the weapon (the head, a leg), or key the arm itself")
    made = made[0] if isinstance(made, tuple) else made
    if case == "arm":
        return out("pass", "drive selftest: the sword arm was driven and nothing refused it", "kit/anim/drivers.py")

    def R(c, j, i):
        return C.quat_mat(np.array(c["joints"][j]["frames"][i][:4], float))
    wrong = []
    if made["joints"]["Head"]["frames"][0] != base["joints"]["Head"]["frames"][0]:
        wrong.append("the first frame moved")
    worst = 0.0
    for i in range(1, len(base["times"])):
        g = R(made, "Head", i) @ R(base, "Head", i).T
        worst = max(worst, float(np.abs(g @ g - R(base, "Torso", i) @ R(base, "Torso", 0).T).max()))
    if worst > 5e-3:
        wrong.append(f"twice what the head was given is not the torso's turn (off by {worst:.3f})")
    if any(made["joints"][j] != base["joints"][j] for j in base["joints"] if j != "Head") or made.get("sword") != base.get("sword"):
        wrong.append("another joint or the blade moved")
    if wrong:
        return out("fail", "drive selftest: " + "; ".join(wrong), "kit/anim/drivers.py")
    return out("pass", "drive selftest: the head is given half the turn the torso has made at every frame of the loved "
                       "cut; the first frame, every other joint and the blade are as they were", "none - proceed")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("good", "arm"):
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
