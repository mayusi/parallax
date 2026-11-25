"""whole.py — the animatic's WHOLE command with solid beats, through the real player (a headless browser): the one
thing the made-project cases (run.py, ../blocking/run.py) cannot run. Not in the kit selftest table: it needs a
browser and takes a minute or two. Run from the project's root:

    python kit/selftest/vfx/animatic/whole.py [--keep]

It writes a made set (`kitfixture_solid`: the made scene clip of ../dailies/clips.py, a chart of a standing pillar on
the hit and a ball that runs across on the going) into build/vfx/kitfixture/ - never into assets/ - and runs
`kit vfx animatic kitfixture_solid --effects build/vfx/kitfixture/effects --angles combat,cine` as a user would: the
plan, the solids' check from every angle, the preset, the RECORDING by the player, the read-back of that recording
against the plan, the side-by-side video, the beat pages, the solids' sheet and film. Passes only when the command
passes and every file it names is there. Prints one JSON line {schema, status, summary, next_action, files}; with
--keep what it made stays in build/ to be looked at (else its set's files are removed).
"""

import contextlib
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "dailies"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import animatic  # noqa: E402
import clips  # noqa: E402

SET = "kitfixture_solid"
ROOT = os.path.join("build", "vfx", "kitfixture")
BEATS = """# kitfixture_solid (a made set: the kit's own proof, not a piece)

| beat | scene | what happens |
|---|---|---|
| 0 the hit | 0.2 - 0.9 | the fire arrives |
| 1 the going | 0.2 - 0.9 | it goes |
"""


def say(status, summary, next_action, **more):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action, **more}))
    return 0 if status == "pass" else 1


def made_set():
    effects = os.path.join(ROOT, "effects")
    measured = os.path.join(effects, "refs_measured")
    shutil.rmtree(ROOT, ignore_errors=True)
    os.makedirs(measured)
    scene = clips.write(os.path.join(ROOT, "scene.mp4"), clips.scene_frames(), 24)
    json.dump({"set": SET, "clip": scene.replace(os.sep, "/"), "clip_fps": 24.0, "cuts": []},
              open(os.path.join(measured, f"{SET}.breakdown.json"), "w"))
    json.dump({"schema": 1, "duration": 1.2, "beats": [
        {"beat": "0 the hit", "scene": [0.2, 0.9], "t": 0.0, "len": 0.5, "hold": 0.0, "key": True,
         "solid": {"form": "pillar", "size": 14}},
        {"beat": "1 the going", "scene": [0.2, 0.9], "t": 0.5, "len": 0.7, "hold": 0.0, "key": False,
         "solid": {"form": "ball", "size": 5, "at": [-10, 6], "to": [12, 6]}}]},
        open(os.path.join(measured, f"{SET}.chart.json"), "w"))
    json.dump({"hue": [5.0, 55.0]}, open(os.path.join(measured, f"{SET}_scene.json"), "w"))
    open(os.path.join(measured, f"{SET}.beats.md"), "w", encoding="utf-8", newline="\n").write(BEATS)
    return effects


def main(argv):
    if not os.path.isdir("kit") or not os.path.isfile(os.path.join("kit", "vfx", "animatic.py")):
        return say("fail", "animatic (whole command): run it from the project's root", "cd to the folder kit/ is in")
    effects = made_set()
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = animatic.main([SET, "--effects", effects, "--angles", "combat,cine"])
    lines = [ln for ln in said.getvalue().strip().splitlines() if ln.strip()]
    try:
        got = json.loads(lines[-1])
    except (IndexError, ValueError):
        got = {"summary": " ".join(lines[-3:])[-400:]}
    out = os.path.join("build", "vfx", "animatic")
    names = [f"{SET}.json", f"{SET}.plan.json", f"{SET}_side.mp4", f"{SET}_blocking.png", f"{SET}_angles.mp4"]
    files = [os.path.join(out, n).replace(os.sep, "/") for n in names]
    files.append(os.path.join("build", "vfx", "booth", f"{SET}_animatic_play_hero.mp4").replace(os.sep, "/"))
    missing = [f for f in files if not os.path.isfile(f)]
    wrong = []
    if code != 0:
        wrong.append(f"the command did not pass: {got.get('summary')}")
    elif missing:
        wrong.append("not made: " + ", ".join(missing))
    else:
        preset = json.load(open(files[0], encoding="utf-8"))
        solids = [la for la in preset.get("layers") or [] if la.get("kind") == "mesh"]
        if len(solids) < 2:
            wrong.append(f"the recorded preset holds {len(solids)} solid(s), not the chart's two")
    if "--keep" not in argv:
        shutil.rmtree(ROOT, ignore_errors=True)
        for f in files:
            if os.path.isfile(f):
                os.remove(f)
        for extra in (os.path.join(out, f"{SET}.recorded.json"), ):
            if os.path.isfile(extra):
                os.remove(extra)
        shutil.rmtree(os.path.join("build", "vfx", "dailies", f"{SET}_animatic"), ignore_errors=True)
    if wrong:
        return say("fail", "animatic (whole command, solid beats): " + "; ".join(wrong), "kit/vfx/animatic.py (make)",
                   said=got.get("summary"))
    return say("pass", "animatic (whole command, solid beats): planned, checked from three angles, recorded by the "
               "player, read back against its plan, and every file it names is there - " + str(got.get("summary"))[:300],
               "none", files=files)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
