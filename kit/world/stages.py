"""stages.py - a world's two ROUTE STAGES the owner approves (LIMITATIONS_FIXES_V3.md stage A.2-A.3: W1 "World Bible &
Walked Greybox ... Require Studio R6 walk + --stage greybox before meshes"; W2 "drive ONE 40x40 corner ... to
--stage corner (>= 7/10) before scaling any full street"). Each stage's artefact, as it is now, answered as the 3D
stages answer (kit/lib/lanelocks.luau stageState reads this line):
  greybox  the world's bible passing (kit/world/bible.py) and its greybox renders (kit world greybox: the world with
           no mesh - every skin, facade and mesh a plain grey box - at the stations, the R6 rig in each frame) in
           build/worlds/look/<Name>.greybox/; its id is the hash of the blueprint and the bible
  corner   the corner's renders (kit world corner <Name> --at <station>: a 40 x 40 stud corner of the world at full
           size) in build/worlds/corner/<Name>/; its id is the hash of the blueprint and the corner it is of
python kit/world/stages.py <Name> --stage greybox|corner --check [--root <project>] [--build <build/worlds>]
-> {exists, stale, problems, id, png}. The owner's yes is `kit approve world <Name> "<words>" --by owner --stage <s>`;
the corner's is his 7 or more out of 10 (V3), recorded with his words."""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bible  # noqa: E402


def _hash(*paths, extra=""):
    h = hashlib.sha1()
    for p in paths:
        if os.path.isfile(p):
            with open(p, "rb") as f:
                h.update(f.read().replace(b"\r\n", b"\n"))
        h.update(b"\0")
    h.update(extra.encode("utf-8"))
    return h.hexdigest()[:16]


def _pngs(d):
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".png")) if os.path.isdir(d) else []


def check(name, stage, root=".", build=None):
    worlds = os.path.join(root, "assets", "worlds")
    build = build or os.path.join(root, "build", "worlds")
    bp = os.path.join(worlds, f"{name}.json")
    bib = os.path.join(worlds, "bible", f"{name}.json")
    if not os.path.isfile(bp):
        return {"exists": False, "problems": [f"no blueprint {bp}"]}
    if stage == "greybox":
        shots = _pngs(os.path.join(build, "look", f"{name}.greybox"))
        res = bible.main([name, "--worlds", worlds, "--build", build])
        out = {"exists": bool(shots) and os.path.isfile(bib), "id": _hash(bp, bib),
               "problems": res.get("problems") or ([] if res["status"] == "pass" else [res["summary"]]),
               "png": shots[0] if shots else None}
        newest = max((os.path.getmtime(p) for p in (bp, bib) if os.path.isfile(p)), default=0)
        out["stale"] = bool(shots) and min(os.path.getmtime(s) for s in shots) < newest
        return out
    if stage == "corner":
        d = os.path.join(build, "corner", name)
        meta = os.path.join(d, "corner.json")
        shots = _pngs(d)
        at = ""
        if os.path.isfile(meta):
            with open(meta, encoding="utf-8") as f:
                at = str((json.load(f) or {}).get("at") or "")
        out = {"exists": bool(shots) and bool(at), "id": _hash(bp, extra=f"corner:{at}"), "problems": [],
               "png": shots[0] if shots else None, "at": at}
        out["stale"] = bool(shots) and min(os.path.getmtime(s) for s in shots) < os.path.getmtime(bp)
        return out
    return {"exists": False, "problems": [f"no world stage {stage!r} (greybox | corner)"]}


if __name__ == "__main__":
    a = sys.argv[1:]
    name = a[0]
    stage = a[a.index("--stage") + 1] if "--stage" in a else "greybox"
    root = a[a.index("--root") + 1] if "--root" in a else "."
    build = a[a.index("--build") + 1] if "--build" in a else None
    print(json.dumps(check(name, stage, root, build)))
