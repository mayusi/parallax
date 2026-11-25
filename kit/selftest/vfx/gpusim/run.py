"""run.py — the gpusim hero-profile selftest cases (kit selftest; LIMITATIONS_FIXES_V4 3.4 step 4: "Raise gpusim.py to
256^3-384^3 (vorticity >= 2)").

    python kit/selftest/vfx/gpusim/run.py good   a NEW sim's spec written by the REAL command (--new): the hero profile,
                                                 a 256 x 256 x 320 grid and vorticity 2 once resolved; a spec with no
                                                 profile keeps its own params untouched (old bakes stay byte for byte)
    python kit/selftest/vfx/gpusim/run.py bad    a "hero" spec whose own params take it back to 128 cells and vorticity
                                                 0.7: the real command refuses it BEFORE anything is simulated

Prints one JSON line {schema, status, summary, next_action}; writes under build/selftest/, removed at the end.
"""

import contextlib
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "vfx"))
import gpusim  # noqa: E402


def say(status, summary, nxt="none"):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": nxt}))
    return 0 if status == "pass" else 1


def call(argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = gpusim.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


def main(argv):
    case = argv[0] if argv else "good"
    root = os.path.abspath(os.path.join("build", "selftest", f"vfx_gpusim_{os.getpid()}"))
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    try:
        if case == "good":
            code, line = call(["--specs", root, "--new", "st_hero"])
            if code != 0:
                return say("fail", "vfx gpusim: --new refused - " + line["summary"], "kit/vfx/gpusim.py")
            with open(os.path.join(root, "st_hero.json"), encoding="utf-8") as fh:
                spec = json.load(fh)
            p = gpusim.params_of(spec)
            old = {"params": {"res": [128, 128, 176]}}
            if (spec.get("profile") != "hero" or gpusim.profile_problems(spec) or min(p["res"]) < 256 or p["vorticity"] < 2
                    or gpusim.params_of(old) is not old["params"]):
                return say("fail", f"vfx gpusim: the new spec is not a hero sim ({p.get('res')}, vorticity {p.get('vorticity')})",
                           "kit/vfx/gpusim.py PROFILES")
            return say("pass", f"vfx gpusim: --new writes a hero sim (res {p['res']}, vorticity {p['vorticity']}); "
                               "a spec with no profile keeps its own params")
        with open(os.path.join(root, "st_small.json"), "w", encoding="utf-8") as fh:
            json.dump({"engine": "fx", "recipe": "gpu_smoke", "profile": "hero", "frames": 4,
                       "params": {"res": [128, 128, 160], "vorticity": 0.7}}, fh)
        code, line = call(["--specs", root, "--out", os.path.join(root, "out"), "--force"])
        if code == 0 or os.path.isdir(os.path.join(root, "out", "st_small")):
            return say("pass", "vfx gpusim bad: a hero sim at 128 cells / vorticity 0.7 PASSED (nothing caught)")
        return say("fail", "vfx gpusim bad: " + line["summary"], "none: this case must fail")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
