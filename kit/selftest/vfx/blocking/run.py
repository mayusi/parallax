#!/usr/bin/env python3
"""The self-test of SOLID BLOCKING FOR THE ANIMATIC (kit/vfx/blocking.py + kit/vfx/animatic.py; the owner's limitations
file, F-R07; the VFX methods audit, stage 29).

    python kit/selftest/vfx/blocking/run.py good     a made chart with a pillar and a slab at one moment and a card
                                                     after them, through the animatic's own plan: both solids are
                                                     reported from the hero and combat angles and a made flank angle (in the picture,
                                                     covering it, on the ground, touching each other); a ball straight
                                                     ahead of a made camera covers what a pinhole camera says (to
                                                     0.003 of the picture); the blocking preset has the solids as real
                                                     shapes in the effect's place and the kit's own preset rules take
                                                     it; the same chart with no solids has the id it always had
    python kit/selftest/vfx/blocking/run.py hidden   a ball standing behind a wide pillar at the same moment, from the
                                                     angle that looks along them: the plan must refuse it, saying
                                                     "is hidden behind"
    python kit/selftest/vfx/blocking/run.py outside  a solid 400 studs off to the side: the plan must refuse it,
                                                     saying none of it is "in the picture"

    python kit/selftest/vfx/blocking/run.py flow     a ball that runs across in front of the pillar: looked at at its
                                                     start, middle and end from three angles, the way it crosses the
                                                     picture, its layer going its way, the sheet and the film drawn
    python kit/selftest/vfx/blocking/run.py leaves   a solid that flies 400 studs away: the plan must refuse it, saying
                                                     at which moment ("at its")

NOT run here: the animatic's whole command with a solid beat (its recording, the read-back of a solid's light from
that recording, the side-by-side video) - that needs the player in a browser: ../animatic/whole.py runs it. Nothing
is played in Roblox.
"""
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import animatic  # noqa: E402
import blocking  # noqa: E402

BEATS = [{"beat": "strike", "t": 0.2, "len": 0.6, "key": True, "solid": {"form": "pillar", "size": 14}},
         {"beat": "crater", "t": 0.2, "len": 0.8, "solid": {"form": "slab", "size": 16}},
         {"beat": "spark", "t": 0.9, "len": 0.3}]


def say(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


MADE = {"flank": {"pos": [40, 6, 0], "look": [0, 5, 0], "fov": 60},      # a made angle from the side of the effect's own place
        "along": {"pos": [0, 5, 60], "look": [0, 5, 0], "fov": 60}}       # and one looking along the z axis
#                                                                           (the kit's own `side` view frames a far target, not the origin)


def plan(beats, asked=None, view_name="hero"):
    rows = animatic.plan_rows(beats, [None] * len(beats), 2.0)
    old = animatic.view_of
    animatic.view_of = lambda name: MADE.get(name) or old(name)
    try:
        view = animatic.view_of(view_name)
        report, problems, names = animatic.block_solids(rows, view_name, view, asked)
    finally:
        animatic.view_of = old
    return rows, view, report, problems, names


def good():
    wrong = []
    rows, view, report, problems, names = plan(BEATS, ["combat", "flank"])
    if problems or names != ["hero", "combat", "flank"]:
        return say("fail", "blocking self-test: the made chart's solids were refused: " + "; ".join(problems)[:240], "kit/vfx/blocking.py, kit/vfx/animatic.py (block_solids)")
    for name in names:
        got = {r["beat"]: r for r in report.get(name, [])}
        if sorted(got) != ["crater", "strike"]:
            wrong.append(f"the {name} angle reports {sorted(got)}")
            continue
        for beat, r in got.items():
            if not (r["in_frame"] >= 0.5 and r["share"] >= blocking.SPECK and r["grounded"] and r["hidden"] <= blocking.HIDDEN):
                wrong.append(f"from {name}, {beat} is {r}")
        if got["strike"]["touches"] != ["crater"]:
            wrong.append(f"from {name} the pillar does not touch the slab it stands on")
    # a pinhole camera: a ball of radius 5, 40 studs straight ahead, fov 60
    cam = {"pos": [0, 5, 40], "look": [0, 5, 0], "fov": 60}
    ball = blocking.checked({"form": "ball", "size": 10})
    t = math.tan(math.radians(30))
    want = math.pi * math.tan(math.asin(5 / 40)) ** 2 / (2 * t * 2 * t * 16 / 9)
    got = blocking.seen(cam, ball)["share"]
    if abs(got - want) > 0.003:
        wrong.append(f"a ball straight ahead covers {got:.4f} of the picture, a pinhole camera says {want:.4f}")
    preset = animatic.preset_of("made", rows, "hero", view, 2.0, None, None, names)
    shapes = [el["shape"] for el in preset["layers"]]
    if shapes[:2] != ["Cylinder", "Block"] or "aim" in preset["layers"][0] or preset["layers"][0]["point"] != [0.0, 0.0, 0.0]:
        wrong.append(f"the solids are not real shapes in the effect's place: {shapes}, {preset['layers'][0].get('point')}")
    if preset["booth"]["views"] != names:
        wrong.append(f"the preset's views are {preset['booth']['views']}")
    root = tempfile.mkdtemp(prefix="kit_blocking_")
    try:
        path = os.path.join(root, "blocking.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(preset, fh)
        refused = animatic.refused(path)
        if refused:
            wrong.append("the kit's preset rules refuse the blocking preset: " + "; ".join(refused)[:200])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    flat = [{k: v for k, v in b.items() if k != "solid"} for b in BEATS]
    frows, fview, _, fproblems, fnames = plan(flat)
    core = [[r["beat"], r["t"], r["life"], r["hold"], r["slow"], r["arrive"], r["go"], r["on"], r.get("step"), r["share"], r["shape"], r["key"]] for r in frows]
    text = json.dumps([animatic.GENERATOR, "made", "hero", [fview["pos"], fview["look"], fview["fov"]], 2.0, core, None, None], sort_keys=True)
    if fproblems or fnames or animatic.plan_id("made", frows, "hero", 2.0, None, None, fview) != hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]:
        wrong.append("a chart with no solid beat is no longer the plan it was (its id changed)")
    if wrong:
        return say("fail", "blocking self-test: " + "; ".join(wrong), "kit/vfx/blocking.py, kit/vfx/animatic.py")
    return say("pass", "blocking self-test: a pillar and a slab are seen, on the ground and touching, from the hero, combat and a flank angle; a ball covers what a pinhole "
               "camera says; the blocking preset has them as real shapes and the kit's rules take it; a chart of cards keeps its id", "none")


def hidden():
    beats = [{"beat": "orb", "t": 0.2, "len": 0.6, "solid": {"form": "ball", "size": 8, "at": [0, -12]}},
             {"beat": "wall", "t": 0.2, "len": 0.6, "solid": {"form": "pillar", "size": 40, "at": [0, 12]}}]
    _, _, _, problems, _ = plan(beats, ["along"])
    if not problems:
        return say("pass", "blocking self-test: a ball behind a wide pillar, seen along them, was let through", "kit/vfx/blocking.py (angles)")
    return say("fail", "blocking: " + "; ".join(problems), "move one of them, or stagger their times")


def outside():
    _, _, _, problems, _ = plan([{"beat": "far", "t": 0.2, "len": 0.6, "solid": {"form": "ball", "size": 4, "at": [400, 0]}}])
    if not problems:
        return say("pass", "blocking self-test: a solid 400 studs off to the side was let through", "kit/vfx/blocking.py (angles)")
    return say("fail", "blocking: " + "; ".join(problems), "move its \"at\", or name another angle")


def flow():
    """a pillar on its slab, then a ball that runs across: every solid at eleven moments of its beat from three
    angles, the way it crosses each picture, its layer going its way, and all of it DRAWN (the sheet, the film)"""
    # (the wave comes after the pillar has gone: run across beside it, it passes BEHIND the pillar from the hero angle,
    # and the eleven looks refuse it - three looks did not see that)
    beats = BEATS + [{"beat": "wave", "t": 1.3, "len": 0.6, "solid": {"form": "ball", "size": 5, "at": [-10, 6], "to": [12, 6]}}]
    rows, view, report, problems, names = plan(beats, ["combat", "flank"])
    wrong = []
    if problems:
        return say("fail", "blocking self-test: the made chart's moving solid was refused: " + "; ".join(problems)[:240], "kit/vfx/blocking.py (angles)")
    for name in names:
        got = {r["beat"]: r for r in report[name]}
        f = got["wave"].get("flow")
        if not f or f["travel"] != 22.0 or len(f["looks"]) != 11 or [f["looks"][k]["at"] for k in (0, 5, 10)] != ["at its start", "at its middle", "at its end"]:
            wrong.append(f"from {name} the wave's flow is {f}")
        if "flow" not in got["strike"]:
            wrong.append(f"from {name} the pillar was not looked at three times beside the wave")
    cross = report["combat"][2]["flow"]
    if not (cross["from"][0] < 0 < cross["to"][0]):
        wrong.append(f"from the combat angle the wave does not cross the picture left to right: {cross['from']} -> {cross['to']}")
    preset = animatic.preset_of("made", rows, "hero", view, 2.0, None, None, names)
    move = preset["layers"][3]["move"]
    if not (move[0][1][0] == 0 and abs(move[-1][1][0] - 22.0) < 1e-3 and abs(move[-2][1][0] - 22.0) < 1e-3):
        wrong.append(f"the wave's layer does not go its 22 studs: {move[0]} .. {move[-1]}")
    root = tempfile.mkdtemp(prefix="kit_blocking_")
    try:
        path = os.path.join(root, "blocking.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(preset, fh)
        refused = animatic.refused(path)
        if refused:
            wrong.append("the kit's preset rules refuse the moving solid's preset: " + "; ".join(refused)[:200])
        views = {n: (view if n == "hero" else (MADE.get(n) or animatic.view_of(n))) for n in names}
        png = blocking.sheet(rows, views, os.path.join(root, "sheet.png"))
        from PIL import Image
        if not png or Image.open(png).size != (480 * 3, 270 * 3):   # (the film is smaller: 320 x 180 a camera)
            wrong.append("the sheet is not three solid beats by three angles")
        if shutil.which("ffmpeg") and not blocking.film(rows, views, os.path.join(root, "angles.mp4"), 2.0):
            wrong.append("the film of the angles was not written")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    if wrong:
        return say("fail", "blocking self-test: " + "; ".join(wrong), "kit/vfx/blocking.py, kit/vfx/animatic.py")
    return say("pass", "blocking self-test: a ball that runs across is looked at at eleven moments of its way from three angles and crosses the combat "
               "picture left to right; its layer goes its 22 studs and the kit's rules take the preset; the sheet and the film are drawn", "none")


def leaves():
    beats = [{"beat": "shot", "t": 0.2, "len": 0.8, "solid": {"form": "ball", "size": 4, "at": [0, 0], "to": [400, 0]}}]
    _, _, _, problems, _ = plan(beats)
    if not problems:
        return say("pass", "blocking self-test: a solid that flies 400 studs out of the picture was let through", "kit/vfx/blocking.py (angles)")
    return say("fail", "blocking: " + "; ".join(problems), "a shorter way (\"to\"), or name another angle")


def main(argv):
    cases = {"good": good, "hidden": hidden, "outside": outside, "flow": flow, "leaves": leaves}
    if len(argv) != 1 or argv[0] not in cases:
        return say("fail", "blocking self-test: name the case", "good | hidden | outside | flow | leaves")
    return cases[argv[0]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
