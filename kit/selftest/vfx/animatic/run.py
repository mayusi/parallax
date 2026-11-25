"""run.py — the timing animatic's selftest cases (kit selftest), on the made project of madeanimatic.py.

    python kit/selftest/vfx/animatic/run.py good   the set's animatic is made from its chart and its scene (its
                                                   recording stands in the project already): passes only when the
                                                   animatic passes its own check - every beat hits where the plan
                                                   says, at the plan's share - the video and the beat pages are
                                                   there, --check knows it, an effect that hits where the animatic
                                                   does passes --drift, a re-timed chart makes it STALE, and the
                                                   recording of the old plan is then REFUSED by --no-record (never
                                                   given a new record; what was there is left as it was)
    python kit/selftest/vfx/animatic/run.py late   the built effect's first beat arrives three frames late against
                                                   the animatic: --drift must name it (this case FAILS, naming the
                                                   drift - a check that let it through would pass, and be caught)

Prints one JSON line {schema, status, summary, next_action}; the made project is a folder of this run's own under
build/selftest/, removed at the end.
"""

import contextlib
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import madeanimatic as M  # noqa: E402

animatic = M.animatic


def call(argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = animatic.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def main(argv):
    case = argv[0] if argv else "good"
    root = os.path.abspath(os.path.join("build", "selftest", f"vfx_animatic_{os.getpid()}", case))
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    here = os.getcwd()
    os.chdir(root)
    try:
        M.project(root, late={0: 3} if case == "late" else None)         # three frames of the recording
        code, made = call(["fire", "--no-record"])
        if code != 0:
            return out("fail" if case == "good" else "pass",
                       f"vfx animatic (made project): the animatic itself was not made ({made.get('summary')})",
                       "kit/vfx/animatic.py: find out why before touching what this case expects")
        code, drift = call(["fire", "--drift", "fx"])
        if case == "late":
            print(json.dumps({"schema": 1, "status": drift.get("status"), "summary": drift.get("summary"),
                              "next_action": drift.get("next_action")}))
            return code
        wrong = []
        if code != 0:
            wrong.append(f"an effect that hits where the animatic does was called drifting ({drift.get('summary')})")
        for name in ("fire.json", "fire.plan.json", "fire_side.mp4"):
            if not os.path.isfile(os.path.join("build", "vfx", "animatic", name)):
                wrong.append(f"no build/vfx/animatic/{name}")
        if not os.path.isfile(os.path.join("build", "vfx", "dailies", "fire_animatic", "beat0_page.png")):
            wrong.append("no beat page of the scene above the animatic")
        check = call(["fire", "--check"])[1]
        if not (check.get("exists") and not check.get("stale") and check.get("id") == made.get("id") and check.get("drawn")):
            wrong.append(f"--check does not know the animatic it just made: {check}")
        path = os.path.join("assets", "effects", "refs_measured", "fire.chart.json")
        chart = json.load(open(path))
        chart["beats"][0]["len"] = 0.3                                    # re-timed after it was made
        json.dump(chart, open(path, "w"))
        after = call(["fire", "--check"])[1]
        if not after.get("stale") or after.get("id") == made.get("id"):
            wrong.append(f"a chart re-timed after the animatic does not make it STALE with another id: {after}")
        # ... and the recording that is here is the OLD plan's: read again without recording, it must be refused
        code, again = call(["fire", "--no-record"])
        if code == 0 or "not of this plan" not in str(again.get("summary")):
            wrong.append(f"the old plan's recording was taken for the re-timed chart's: {again.get('summary')}")
        # ... and the animatic that was there is left as it was: still the OLD plan's record, reading out of date
        # (never the new plan's id over the old video - and never removed by a run that made nothing)
        left = call(["fire", "--check"])[1]
        kept = json.load(open(os.path.join("build", "vfx", "animatic", "fire.plan.json"), encoding="utf-8"))
        if not (left.get("exists") and left.get("stale")) or kept.get("id") != made.get("id"):
            wrong.append(f"a refused recording changed the animatic that was there: {left}")
        if wrong:
            return out("fail", "vfx animatic (made project): " + "; ".join(wrong),
                       "kit/vfx/animatic.py: find out why before touching what this case expects")
        return out("pass", "vfx animatic (made project): every beat hits where the plan says at the plan's share; the video "
                   "and the pages are there; an effect on its timing passes; its id is another once the chart is re-timed, "
                   "and the old plan's recording is refused", "none")
    finally:
        os.chdir(here)
        shutil.rmtree(os.path.dirname(root), ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
