"""run.py — the weapon-in-hand check's selftest cases (kit selftest; kit/anim/in_hand.py through the build's motion
gates, kit/anim/metrics.py), on a cut the owner loved (kit/selftest/anim/faults/loved/Katana1Kesa.move.json, read only;
the changed clips are copies in this run's own folder).

    python kit/selftest/anim/hand/run.py good    the loved kesa passes the motion gates with its sword in the hands at
                                                 every frame; the same clip with the sword lifted off the hands for
                                                 frames 10-14 AND a Toss / Catch round them passes too (a toss the
                                                 clip declares is meant)
    python kit/selftest/anim/hand/run.py loose   the sword lifted off the hands for frames 10-14 with no toss
                                                 declared: the motion gates must fail and name the frames (this case
                                                 FAILS, naming them)

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
    run = os.path.join(os.environ.get("KIT_BUILD", os.path.join(ROOT, "build")), "selftest", f"anim_hand_{os.getpid()}")
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(run)
    try:
        with open(LOVED, encoding="utf-8") as fh:
            clip = S.generate(json.load(fh))[0]
        clip["source"] = {"kind": "move", "file": os.path.join(run, "anims", "SelftestHand.move.json")}   # (no frozen list there)
        lifted = copy.deepcopy(clip)
        for key in ("tip", "grip_path"):
            for i in range(10, 15):
                p = lifted["sword"][key][i]
                lifted["sword"][key][i] = [p[0], p[1] + 1.0, p[2]]
        tossed = copy.deepcopy(lifted)
        tossed["events"] = tossed["events"] + [{"name": "Toss", "t": 9 / 60}, {"name": "Catch", "t": 15 / 60}]
        paths = {}
        for tag, c in (("held", clip), ("lifted", lifted), ("tossed", tossed)):
            c["name"] = f"SelftestHand{tag.capitalize()}"
            paths[tag] = os.path.join(run, f"{c['name']}.clip.json")
            with open(paths[tag], "w", encoding="utf-8") as fh:
                json.dump(c, fh)
        if case == "loose":
            code, v = gates(paths["lifted"])
            return out("pass" if code == 0 else "fail", v["summary"], v.get("next_action") or "none")
        wrong = []
        for tag in ("held", "tossed"):
            code, v = gates(paths[tag])
            with open(paths[tag][:-len(".clip.json")] + ".metrics.json", encoding="utf-8") as fh:
                m = json.load(fh)
            if code != 0:
                wrong.append(f"the {tag} clip failed the motion gates ({v['summary']})")
            if "NO hand" in json.dumps(m.get("problems")) or m.get("in_hand", {}).get("loose"):
                wrong.append(f"the {tag} clip was failed for its weapon ({v['summary']})")
            if tag == "tossed" and m.get("in_hand", {}).get("windows") != [[9, 15]]:
                wrong.append(f"the declared toss was not read as frames 9-15 ({m.get('in_hand')})")
        if wrong:
            return out("fail", "in-hand selftest: " + "; ".join(wrong), "kit/anim/in_hand.py")
        return out("pass", "in-hand selftest: the loved kesa holds its sword at every frame; the same clip with the sword "
                           "off the hands for frames 10-14 between a Toss and a Catch is not failed for it", "none - proceed")
    finally:
        shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("good", "loose"):
        print(__doc__)
        sys.exit(2)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1]))
