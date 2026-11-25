"""run.py — the contact check's selftest cases (kit selftest; kit/anim/contact.py through the build's motion gates,
kit/anim/metrics.py), on a cut the owner loved whose Hit his move file authors
(kit/selftest/anim/faults/loved/GsCombo3Overhead.move.json, read only; the changed clips are copies in this run's own
folder).

    python kit/selftest/anim/contact/run.py good    the loved overhead passes the motion gates and its authored Hit is
                                                    where the blade meets the target (within 3 frames, with the
                                                    geometry and the speed behind it); the same clip with its Hit moved to the blade's
                                                    fastest frame BY ITS AUTHOR is said, not failed
    python kit/selftest/anim/contact/run.py early   the Hit at the blade's fastest frame, placed by the BUILD (the old
                                                    inference): the motion gates must fail and name both frames (this
                                                    case FAILS, naming them)

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

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C  # noqa: E402
import metrics as MT  # noqa: E402
import pose_sheet as PS  # noqa: E402
import strike as S  # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "GsCombo3Overhead.move.json")


def gates(path):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = MT.main([path])
    with open(path[:-len(".clip.json")] + ".metrics.json", encoding="utf-8") as fh:
        return code, json.loads(said.getvalue().strip().splitlines()[-1]), json.load(fh)


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def main(case):
    run = os.path.join(os.environ.get("KIT_BUILD", os.path.join(ROOT, "build")), "selftest", f"anim_contact_{os.getpid()}")
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(run)
    try:
        with open(LOVED, encoding="utf-8") as fh:
            clip = S.generate(json.load(fh))[0]
        clip["source"] = {"kind": "move", "file": os.path.join(run, "anims", "SelftestContact.move.json")}   # (no frozen list there)
        tip = PS.paths(clip, C.world_frames(clip, C.load_rig("r6")))["BladeTip"]
        peak = int(np.argmax(np.linalg.norm(np.diff(tip, axis=0), axis=1))) + 1
        moved = copy.deepcopy(clip)
        moved["events"] = [{"name": "Hit", "t": peak / clip["fps"]}]
        built = copy.deepcopy(moved)
        built["hit_inferred"] = True
        paths = {}
        for tag, c in (("authored", clip), ("moved", moved), ("built", built)):
            c["name"] = f"SelftestContact{tag.capitalize()}"
            paths[tag] = os.path.join(run, f"{c['name']}.clip.json")
            with open(paths[tag], "w", encoding="utf-8") as fh:
                json.dump(c, fh)
        if case == "early":
            code, v, m = gates(paths["built"])
            hit = [p for p in m.get("problems", []) if "meets the target at frame" in p]
            return out("pass" if code == 0 or not hit else "fail", hit[0] if hit else v["summary"], v.get("next_action") or "none")
        wrong = []
        code, v, m = gates(paths["authored"])
        h = (m.get("contact") or {}).get("hits") or [{}]
        if code != 0:
            wrong.append(f"the loved clip failed the motion gates ({v['summary']})")
        if not h[0].get("backed") or h[0].get("confidence") != 0.75:
            wrong.append(f"the authored Hit was not read as where the blade meets the target ({h[0]})")
        _, v, m = gates(paths["moved"])
        h = (m.get("contact") or {}).get("hits") or [{}]
        if any("meets the target at frame" in p for p in m.get("problems", [])):
            wrong.append("an AUTHORED Hit was failed for the geometry (the author's word stands)")
        if h[0].get("backed") is not False:
            wrong.append(f"the moved Hit was not read as off the contact ({h[0]})")
        if wrong:
            return out("fail", "contact selftest: " + "; ".join(wrong), "kit/anim/contact.py")
        return out("pass", f"contact selftest: the loved overhead's authored Hit is where its blade meets the target; the same "
                           f"Hit moved by its author to the blade's fastest frame ({peak}) is said, not failed", "none - proceed")
    finally:
        shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("good", "early"):
        print(__doc__)
        sys.exit(2)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1]))
