"""run.py — the G2 2-fighter scene selftest cases (kit selftest; LIMITATIONS_FIXES_V4 3.4 step 1 / 11 Phase 2).

    python kit/selftest/vfx/duel/run.py good   the kit's REAL scene file (kit/vfx/scenes/g2.json, what the browser
                                               player and the Studio booth build) passes the real checker
                                               (kit/vfx/duel.py), and a strike on its victim anchors passes as a preset
    python kit/selftest/vfx/duel/run.py bad    a 32-stud arena with the victim turned away and a camera that cuts a
                                               fighter out, and a preset naming an anchor the scene does not have: each refused,
                                               every fault named

Prints one JSON line {schema, status, summary, next_action}.
"""

import contextlib
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import duel  # noqa: E402


def call(argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = duel.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


def say(status, summary, nxt="none"):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": nxt}))
    return 0 if status == "pass" else 1


def main(argv):
    case = argv[0] if argv else "good"
    if case == "good":
        code, line = call(["check", "g2"])
        if code != 0:
            return say("fail", "vfx duel: the kit's G2 scene is refused - " + line["summary"], "kit/vfx/scenes/g2.json")
        code2, line2 = call(["preset", os.path.join(HERE, "preset_good.json")])
        if code2 != 0:
            return say("fail", "vfx duel: a strike on G2's anchors is refused - " + line2["summary"], "kit/vfx/duel.py")
        return say("pass", "vfx duel: " + line["summary"] + "; a strike on its victim anchors plays there")
    code, line = call(["check", os.path.join(HERE, "scene_bad.json")])
    code2, line2 = call(["preset", os.path.join(HERE, "preset_bad.json")])
    faults = (line.get("faults") or []) + (line2.get("faults") or [])
    if code == 0 or code2 == 0:
        return say("pass", "vfx duel: a broken 2-fighter scene / preset was let through ("
                   + ("scene" if code == 0 else "preset") + ")")
    return say("fail", "vfx duel: refused - " + " | ".join(faults), "fix the scene (kit/vfx/scenes/) or the preset's anchors")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
