"""run.py — the V5 sequence + B4 plate selftest cases (kit selftest; LIMITATIONS_FIXES_V4 §3.4 step 3).

    python kit/selftest/vfx/sequence/run.py good   a halftone plate baked by the REAL plate command, the V5 template
                                                   written by the REAL sequence command and pointed at it, checked by the
                                                   GAME's own rules (src/kit/VfxSequenceRules.luau): it passes, its
                                                   impact beat is found on its frame, and the timeline is drawn
    python kit/selftest/vfx/sequence/run.py bad    the same sequence with its impact beat's mood held 3 frames (not the
                                                   1-frame beat) and its reveal cut down to one shot: refused, naming the
                                                   missing "IMPACT beat"

Prints one JSON line {schema, status, summary, next_action}; everything is written under build/selftest/, removed at
the end.
"""

import contextlib
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import plates  # noqa: E402
import sequence  # noqa: E402


def call(tool, argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = tool.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


def say(status, summary, nxt="none"):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": nxt}))
    return 0 if status == "pass" else 1


def main(argv):
    case = argv[0] if argv else "good"
    root = os.path.abspath(os.path.join("build", "selftest", f"vfx_sequence_{os.getpid()}", case))
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    try:
        code, line = call(plates, ["st_burst", "--kind", "halftone", "--frames", "4", "--out", root, "--specs-dir", root,
                                   "--look-dir", root])
        if code != 0:
            return say("fail", "vfx sequence: the plate was not baked - " + line["summary"], "kit/vfx/plates.py")
        code, line = call(sequence, ["st_v5", "--new", "--dir", root])
        if code != 0:
            return say("fail", "vfx sequence: the template was not written - " + line["summary"])
        path = os.path.join(root, "st_v5.seq.json")
        with open(path, encoding="utf-8") as fh:
            seq = json.load(fh)
        seq["beats"][1]["impact_plate"]["plate"] = "st_burst"
        if case == "bad":
            seq["beats"][1]["mood_push"]["frames"] = 3
            del seq["beats"][3:]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(seq, fh)
        code, line = call(sequence, ["st_v5", "--dir", root, "--plates-dir", root, "--look-dir", root])
        if case == "bad":
            if code == 0:
                return say("pass", "vfx sequence bad: a sequence with no 1-frame impact beat and one reveal cut PASSED (nothing caught)")
            return say("fail", "vfx sequence bad: " + line["summary"], "none: this case must fail")
        if code != 0:
            return say("fail", "vfx sequence: the V5 template refused - " + line["summary"], "src/kit/VfxSequenceRules.luau")
        if "impact at frame 36" not in line["summary"] or not os.path.isfile(os.path.join(root, "st_v5_timeline.png")):
            return say("fail", "vfx sequence: the impact beat was not found on frame 36, or no timeline was drawn - " + line["summary"])
        return say("pass", "vfx sequence: a halftone plate baked, the V5 template pointed at it and checked by the game's "
                   "own rules - " + line["summary"])
    finally:
        shutil.rmtree(os.path.dirname(root), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
