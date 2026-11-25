"""run.py — the drawn blade path's selftest cases (kit selftest; kit/anim/blade_path.py through the build's motion
gates, kit/anim/metrics.py), on a cut the owner loved (kit/selftest/anim/faults/loved/Katana1Kesa.move.json, read only;
the changed move is a copy in this run's own folder).

    python kit/selftest/anim/path/run.py good   the loved kesa, its move drawing ten points off its own blade path:
                                                the motion gates pass and the reading says every point is passed;
                                                the same clip with no path drawn is held to nothing
    python kit/selftest/anim/path/run.py off    the same ten points, and the clip of the move with the grip of two
                                                keys raised one stud: the blade leaves the drawn line - the motion
                                                gates must fail and name the point (this case FAILS, naming it)

Prints one JSON line {schema, status, summary, next_action}; everything is written under build/selftest/ in a folder
of this run's own, removed at the end.
"""
import contextlib
import copy
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import blade_path as BP  # noqa: E402
import metrics as MT  # noqa: E402
import strike as S  # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")


def gates(path):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = MT.main([path])
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def main(case):
    run = os.path.join(os.environ.get("KIT_BUILD", os.path.join(ROOT, "build")), "selftest", f"anim_path_{os.getpid()}")
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(run)

    def write(name, clip, move):
        mp = os.path.join(run, f"{name}.move.json")
        with open(mp, "w", encoding="utf-8") as fh:
            json.dump(move, fh)
        cp = os.path.join(run, f"{name}.clip.json")
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump(dict(clip, name=name, source={"kind": "move", "file": mp}), fh)
        return cp
    try:
        with open(LOVED, encoding="utf-8") as fh:
            move = json.load(fh)
        clip = S.generate(copy.deepcopy(move))[0]
        path = BP.draw(clip, 0.1)
        raised = copy.deepcopy(move)
        for k in raised["keys"][2:4]:
            k["grip"] = [k["grip"][0], k["grip"][1] + 1.0, k["grip"][2]]
        if case == "off":
            code, v = gates(write("SelftestPathOff", S.generate(copy.deepcopy(raised))[0], dict(raised, blade_path=path)))
            return out("pass" if code == 0 else "fail", v["summary"], v.get("next_action") or "none")
        wrong = []
        on = write("SelftestPathOn", clip, dict(move, blade_path=path))
        code, v = gates(on)
        with open(on[:-len(".clip.json")] + ".metrics.json", encoding="utf-8") as fh:
            rows = (json.load(fh).get("blade_path") or {}).get("rows") or []
        if code != 0 or "MISSES" in v["summary"] or len(rows) != 10 or any(not r["ok"] or r["studs"] > 0.01 for r in rows):
            wrong.append(f"the clip did not pass through the ten points off its own path ({v['summary']})")
        free = write("SelftestPathNone", S.generate(copy.deepcopy(raised))[0], raised)
        code, v = gates(free)
        with open(free[:-len(".clip.json")] + ".metrics.json", encoding="utf-8") as fh:
            if "blade_path" in json.load(fh) or "MISSES" in v["summary"]:
                wrong.append("a move that draws no path was held to one")
        if wrong:
            return out("fail", "path selftest: " + "; ".join(wrong), "kit/anim/blade_path.py")
        return out("pass", "path selftest: the loved kesa passes through the ten points drawn off its own blade path at "
                           "0.00 studs; a move that draws no path is held to nothing", "none - proceed")
    finally:
        shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("good", "off"):
        print(__doc__)
        sys.exit(2)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1]))
