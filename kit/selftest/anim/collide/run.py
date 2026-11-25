"""run.py — the pass-through check's selftest cases (kit selftest; kit/anim/collide.py through the build's motion
gates, kit/anim/metrics.py), on a cut the owner loved (kit/selftest/anim/faults/loved/Katana1Kesa.move.json, read only;
the changed clips are copies in this run's own folder).

    python kit/selftest/anim/collide/run.py good      the loved kesa passes the motion gates with nothing through its
                                                      body; the same clip, unarmed, with its right arm swung into the
                                                      chest for frames 10-14 AND that contact declared passes too
    python kit/selftest/anim/collide/run.py through   the arm swung into the chest with no contact declared: the
                                                      motion gates must fail and name the part and the frame (this
                                                      case FAILS, naming them)
    python kit/selftest/anim/collide/run.py table     what every loved and rejected cut measures (read only)

Prints one JSON line {schema, status, summary, next_action}; everything is written under build/selftest/ in a folder
of this run's own, removed at the end.
"""
import contextlib
import copy
import glob
import io
import json
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import collide as K  # noqa: E402
import metrics as MT  # noqa: E402
import strike as S  # noqa: E402

FAULTS = os.path.join(ROOT, "kit", "selftest", "anim", "faults")
LOVED = os.path.join(FAULTS, "loved", "Katana1Kesa.move.json")


def gates(path):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = MT.main([path])
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def table():
    rows = []
    for kind in ("loved", "rejected"):
        for path in sorted(glob.glob(os.path.join(FAULTS, kind, "*.move.json"))):
            with open(path, encoding="utf-8") as fh:
                c = S.generate(json.load(fh))[0]
            r = K.read(c)
            rows.append(f"{kind} {c['name']}: " + ", ".join(f"{k} {v['depth']:.2f}" for k, v in r["worst"].items()))
    return out("pass", "pass-through, studs inside a block (bars: " + ", ".join(f"{k} {v:g}" for k, v in K.BARS.items()) + ") - "
               + "; ".join(rows), "none")


def main(case):
    if case == "table":
        return table()
    run = os.path.join(os.environ.get("KIT_BUILD", os.path.join(ROOT, "build")), "selftest", f"anim_collide_{os.getpid()}")
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(run)
    try:
        with open(LOVED, encoding="utf-8") as fh:
            clip = S.generate(json.load(fh))[0]
        clip["source"] = {"kind": "move", "file": os.path.join(run, "anims", "SelftestCollide.move.json")}   # (no frozen list there)
        into = copy.deepcopy(clip)
        into.pop("sword", None)
        h = math.radians(-90) / 2
        for i in range(10, 15):
            into["joints"]["Right Arm"]["frames"][i] = [0, 0, math.sin(h), math.cos(h), 0, 0, 0]
            into["joints"]["Left Arm"]["frames"][i] = [0, 0, 0, 1, 0, 0, 0]
        meant = copy.deepcopy(into)
        meant["contact"] = [{"a": "Right Arm", "b": "Torso", "from": 9 / clip["fps"], "to": 15 / clip["fps"]}]
        paths = {}
        for tag, c in (("clear", clip), ("into", into), ("meant", meant)):
            c["name"] = f"SelftestCollide{tag.capitalize()}"
            paths[tag] = os.path.join(run, f"{c['name']}.clip.json")
            with open(paths[tag], "w", encoding="utf-8") as fh:
                json.dump(c, fh)
        if case == "through":
            code, v = gates(paths["into"])
            with open(paths["into"][:-len(".clip.json")] + ".metrics.json", encoding="utf-8") as fh:
                m = json.load(fh)
            hit = [p for p in m.get("problems", []) if "goes into the Torso" in p]
            # (the broken arm trips other gates too - a pop where it snaps in: the case is about THIS gate's words)
            return out("pass" if code == 0 or not hit else "fail", hit[0] if hit else v["summary"], v.get("next_action") or "none")
        wrong = []
        for tag in ("clear", "meant"):
            gates(paths[tag])
            with open(paths[tag][:-len(".clip.json")] + ".metrics.json", encoding="utf-8") as fh:
                m = json.load(fh)
            if "collide" not in m:
                wrong.append(f"the {tag} clip was not read")
            if any("goes into" in p or "passes through" in p for p in m.get("problems", [])):
                wrong.append(f"the {tag} clip was failed for passing through ({m['problems']})")
        code, v = gates(paths["clear"])
        if code != 0:
            wrong.append(f"the loved clip failed the motion gates ({v['summary']})")
        if wrong:
            return out("fail", "pass-through selftest: " + "; ".join(wrong), "kit/anim/collide.py")
        return out("pass", "pass-through selftest: nothing goes through the loved kesa's body; the same clip with an arm in "
                           "the chest for frames 10-14 and that contact declared is not failed for it", "none - proceed")
    finally:
        shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("good", "through", "table"):
        print(__doc__)
        sys.exit(2)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1]))
