"""run.py — the dailies' selftest cases (kit selftest): the made clips of clips.py through the real command.

    python kit/selftest/vfx/dailies/run.py good    ours beside the scene: must pass AND say each known difference
                                                   (one frame against 0.07 s, "at least", the freeze, twos against
                                                   ones), end with LOOK: <folder>, and make strips a reader gets 1:1
    python kit/selftest/vfx/dailies/run.py blank   a recording that shows nothing: the dailies FAIL ("never lights up")

Prints one JSON line {schema, status, summary, next_action}; the pictures go to build/selftest/vfx_dailies/<case>/
(git-ignored; a folder of this run's own, removed at the end).
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
import clips  # noqa: E402
import dailies  # noqa: E402

SAYS = ["it arrives: the scene in one frame, ours over 0.07 s",
        "it stays: the scene at least 0.67 s (its shot ends while it is lit), ours 0.23 s",
        "a freeze while it stays: the scene none in the 0.67 s its shot shows, ours 0.13 s (4 of its frames)",
        "the scene is drawn on twos, ours on ones"]


def main(argv):
    case = argv[0] if argv else "good"
    # a folder of this run's own (two sessions running the selftest at once must not share one), removed at the end
    out = os.path.join("build", "selftest", f"vfx_dailies_{os.getpid()}", case)
    os.makedirs(out, exist_ok=True)
    scene = clips.write(os.path.join(out, "scene.mp4"), clips.scene_frames(), 24)
    ours = clips.write(os.path.join(out, "ours.mp4"), clips.blank_frames() if case == "blank" else clips.our_frames(), 30)
    look = os.path.join(out, "look")
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = dailies.main([f"selftest_{case}", "--ours", ours, "--scene-clip", scene, "--hue", "5,55", "--out", look])
    line = said.getvalue().strip().splitlines()[-1]
    kept = True
    if case == "good":                       # (read before the folder goes)
        from PIL import Image
        strip = os.path.join(look, "beat0_01.png")
        kept = Image.open(strip).width if os.path.isfile(strip) else None
    shutil.rmtree(os.path.dirname(out), ignore_errors=True)
    if case != "good":
        print(line)
        return code
    got = json.loads(line)
    wrong = [s for s in SAYS if s not in got.get("summary", "")]
    if got.get("status") != "pass":
        wrong.append("the dailies did not pass")
    if not got.get("summary", "").endswith("LOOK: " + look.replace(os.sep, "/") + "/"):
        wrong.append("the summary does not end with LOOK: <folder>")
    if kept is None:
        wrong.append("no strip beat0_01.png")
    elif not 1280 <= kept <= 1568:
        wrong.append(f"a strip is {kept} px wide: two 640 px frames a picture is what a reader gets at full size")
    if wrong:
        print(json.dumps({"schema": 1, "status": "fail", "summary": "vfx dailies (made clips): " + "; ".join(
            f"missing: {w}" if w in SAYS else w for w in wrong), "next_action": "kit/vfx/dense.py, denseclip.py, dailies.py: "
            "the read of clips.py's frames changed - find out why before touching the expected sentences"}))
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
