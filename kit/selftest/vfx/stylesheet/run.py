"""run.py — the style sheet's selftest cases (kit selftest), on the made project of madeproject.py.

    python kit/selftest/vfx/stylesheet/run.py good    both beats come out as pairs a reader gets at full size, the
                                                      sheet has its id, --check says it exists and is not stale, and
                                                      after the preset is edited --check says STALE with another id
    python kit/selftest/vfx/stylesheet/run.py blank   a recording that shows nothing: NOT a sheet he can approve (this
                                                      case fails, naming "ours never lights up")

Prints one JSON line {schema, status, summary, next_action}; the made project is a folder of this run's own under build/selftest/, removed at the end.
"""

import contextlib
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import madeproject  # noqa: E402
import stylesheet  # noqa: E402

clips = madeproject.clips


def call(argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = stylesheet.main(argv)
    return code, said.getvalue().strip().splitlines()[-1]


def main(argv):
    case = argv[0] if argv else "good"
    # a folder of this run's own (two sessions running the selftest at once must not share one), removed at the end
    root = os.path.abspath(os.path.join("build", "selftest", f"vfx_stylesheet_{os.getpid()}", case))
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    madeproject.project(root, clips.blank_frames() if case == "blank" else clips.our_frames())
    here = os.getcwd()
    os.chdir(root)
    try:
        code, line = call(["fx", "--tile", "640"])
        if case != "good":
            print(line)
            return code
        got = json.loads(line)
        wrong = []
        if got.get("status") != "pass" or len(got.get("beats") or []) != 2:
            wrong.append(f"the sheet did not come out as two pairs ({got.get('summary')})")
        else:
            from PIL import Image
            width = Image.open(os.path.join("build", "vfx", "stylesheet", "fx", "beat0.png")).width
            if not 1280 <= width <= 1568:
                wrong.append(f"a pair is {width} px wide: two 640 px frames is what a reader gets at full size")
        check = json.loads(call(["fx", "--check"])[1])
        if not (check.get("exists") and not check.get("stale") and check.get("id") == got.get("id")):
            wrong.append(f"--check does not know the sheet it just drew: {check}")
        path = os.path.join("assets", "effects", "fx.json")
        preset = json.load(open(path))
        preset["layers"].append({"kind": "sprite", "name": "a_layer_added_after_his_yes"})
        json.dump(preset, open(path, "w"))
        after = json.loads(call(["fx", "--check"])[1])
        if not after.get("stale") or after.get("id") == got.get("id"):
            wrong.append(f"a preset edited after the sheet is not STALE with another id: {after}")
        if wrong:
            print(json.dumps({"schema": 1, "status": "fail", "summary": "vfx stylesheet (made project): " + "; ".join(wrong),
                              "next_action": "kit/vfx/stylesheet.py: find out why before touching what this case expects"}))
            return 1
        print(json.dumps({"schema": 1, "status": "pass", "summary": "vfx stylesheet (made project): two beats as pairs at full "
                          "size; its id holds for this preset and is another once the preset is edited", "next_action": "none"}))
        return 0
    finally:
        os.chdir(here)
        shutil.rmtree(os.path.dirname(root), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
