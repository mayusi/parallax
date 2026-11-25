"""run.py — the hand-posed file's blocking and lock, selftest cases (kit selftest; kit/anim/blocking.py: source "pose",
lock kind "pose"). The clip "the owner's rig posed from the file" is a cut he loved, generated here (read only; the
rig's own part runs in kit/test/python/test_anim_blocking_posed.py where Blender is there).

    python kit/selftest/anim/posed/run.py good    a posed file keyed at four frames: its blocking holds those four
                                                  poses; the move is held until the owner's yes to that sheet, free
                                                  after it, and held again once one key of the file changed
    python kit/selftest/anim/posed/run.py locked  a hand-posed move made after the rule whose key poses nobody
                                                  showed the owner: it must not be built (this case FAILS)

Prints one JSON line {schema, status, summary, next_action}; everything is written under build/selftest/ in a folder
of this run's own, removed at the end.
"""
import contextlib
import io
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import blocking as B  # noqa: E402
import strike as S  # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")
NAME = "SelftestPosed"


def call(argv):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = B.main(argv)
    return code, json.loads(said.getvalue().strip().splitlines()[-1])


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def main(case):
    run = os.path.join(os.environ.get("KIT_BUILD", os.path.join(ROOT, "build")), "selftest", f"anim_posed_{os.getpid()}")
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(run)
    try:
        with open(LOVED, encoding="utf-8") as fh:
            clip = S.generate(json.load(fh))[0]
        cp, pp = os.path.join(run, "posed.clip.json"), os.path.join(run, f"{NAME}.pose.json")
        pose = {"name": NAME, "fps": 60, "keys": [{"f": f, "body": {"turn": 5 * i}} for i, f in enumerate((0, 12, 26, 51))]}
        with open(pp, "w", encoding="utf-8") as fh:
            json.dump(pose, fh)
        import hashlib
        with open(pp, "rb") as fh:                            # (the mark kit/anim/pose_r6.py leaves: posed from this file)
            clip["source"] = {"kind": "pose", "file": pp, "sha256": hashlib.sha256(fh.read()).hexdigest()}
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump(clip, fh)
        anims = os.path.join(run, "anims")
        where = ["--out", os.path.join(run, "out"), "--anims", anims]
        code0, first = call(["lock", f"{NAME}=pose={pp}", "--anims", anims])
        if case == "locked":
            return out("pass" if code0 == 0 else "fail", first["summary"], first["next_action"])
        code, m = call(["make", NAME, "--clip", cp, "--pose", pp, *where])
        wrong = []
        if code != 0 or "4 key pose(s) held" not in m["summary"]:
            wrong.append(f"the posed file's four keys were not held as four poses ({m['summary']})")
        call(["approve", NAME, "yes, those poses", "--by", "owner", "--id", m.get("id", ""), *where])
        code1, yes = call(["lock", f"{NAME}=pose={pp}", "--anims", anims])
        pose["keys"][2]["body"]["turn"] = 40
        with open(pp, "w", encoding="utf-8") as fh:
            json.dump(pose, fh)
        code2, late = call(["lock", f"{NAME}=pose={pp}", "--anims", anims])
        if code0 == 0:
            wrong.append("a posed move nobody showed him was free to be built")
        if code1 != 0:
            wrong.append(f"his yes to the sheet did not free the move ({yes['summary']})")
        if code2 == 0 or "the file changed since" not in late["summary"]:
            wrong.append(f"a key changed after his yes did not hold the move again ({late['summary']})")
        if wrong:
            return out("fail", "posed selftest: " + "; ".join(wrong), "kit/anim/blocking.py")
        return out("pass", "posed selftest: the posed file's four keys are held as four poses; the move was held until the "
                           "owner's yes to that sheet, free after it, held again once a key of the file changed",
                   "none - proceed")
    finally:
        shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("good", "locked"):
        print(__doc__)
        sys.exit(2)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1]))
