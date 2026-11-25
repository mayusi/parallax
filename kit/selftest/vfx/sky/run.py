"""run.py — the per-sky calibration selftest cases (kit selftest; LIMITATIONS_FIXES_V4 13.3.1: calibrate "across Daylight /
Overcast / Sunset / Night").

    python kit/selftest/vfx/sky/run.py good   a booth job and player metrics both recorded under "day": the REAL
                                              calibrate.py takes them as a day measurement (no sky problem)
    python kit/selftest/vfx/sky/run.py bad    night recordings asked for as "day", and a player recording that does not
                                              say its sky: calibrate.py --sky refuses, naming both, and writes nothing

Prints one JSON line {schema, status, summary, next_action}; works in a folder under build/selftest/, removed at the end.
"""

import contextlib
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import calibrate  # noqa: E402


def say(status, summary, nxt="none"):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": nxt}))
    return 0 if status == "pass" else 1


def lay(booth_dir, booth_sky, play_sky):
    os.makedirs(booth_dir, exist_ok=True)
    with open(os.path.join(booth_dir, "st_fx.job.json"), "w", encoding="utf-8") as fh:
        json.dump({"name": "st_fx", "sky": booth_sky}, fh)
    with open(os.path.join(booth_dir, "st_fx_play.metrics.json"), "w", encoding="utf-8") as fh:
        json.dump({"frames": []} if play_sky is None else {"frames": [], "sky": play_sky}, fh)


def main(argv):
    case = argv[0] if argv else "good"
    root = os.path.abspath(os.path.join("build", "selftest", f"vfx_sky_{os.getpid()}"))
    shutil.rmtree(root, ignore_errors=True)
    booth = os.path.join(root, "build", "vfx", "booth")
    try:
        if case == "good":
            lay(booth, "day", "day")
            wrong = calibrate.sky_problems("st_fx", "day", booth)
            if wrong:
                return say("fail", "vfx sky: day recordings refused as day - " + "; ".join(wrong), "kit/vfx/calibrate.py")
            return say("pass", "vfx sky: a booth job and player metrics both under day are taken as a day measurement")
        lay(booth, "night", None)
        old = os.getcwd()
        os.chdir(root)
        try:
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                code = calibrate.main(["st_fx", "--sky", "day"])
        finally:
            os.chdir(old)
        line = json.loads(said.getvalue().strip().splitlines()[-1])
        if code == 0 or os.path.exists(os.path.join(booth, "st_fx_calibration_day.json")):
            return say("pass", "vfx sky bad: night recordings were calibrated as day (nothing caught)")
        return say("fail", "vfx sky bad: " + line["summary"], "none: this case must fail")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
