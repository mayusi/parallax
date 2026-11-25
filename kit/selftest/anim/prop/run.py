"""run.py — the prop rig's selftest cases (kit selftest; kit/anim/prop_rig.py and the build's motion gates,
kit/anim/metrics.py). The prop is a chest made up here (a base, a hinged lid, a sliding tray, a fixed handle); its rig
is written into this run's own folder, never into kit/anim/rigs.

    python kit/selftest/anim/prop/run.py good   the chest's prop file becomes a rig; the kit's own FK opens the lid
                                                about its hinge (the hinge line does not move) and slides the tray;
                                                a clip inside the joints passes the motion gates
    python kit/selftest/anim/prop/run.py torn   the lid swung to 140 degrees on a hinge that stops at 110: the motion
                                                gates must fail and name the part (this case FAILS, naming it)
    python kit/selftest/anim/prop/run.py whole  THE WHOLE WAY (kit/anim/prop_rig.py go): the chest's prop file and a
                                                keyframe spec that opens the lid 90 degrees go through the kit's own
                                                compiler to the KeyframeSequence model the game plays, the clip held
                                                to the joints in between
    python kit/selftest/anim/prop/run.py spec   the same, with a spec that opens the lid 140 degrees: NO model may
                                                be left (this case FAILS, naming the part)
    python kit/selftest/anim/prop/run.py model  A PROP THE 3D LANE BUILT: a built model's manifest (a gate: an arm
                                                on a hinge, a bolt sliding on the arm) gives the rig of the model
                                                the game spawns from it, and a spec that swings the arm 90 degrees
                                                goes the whole way; the model's pose is the joint's own turn
    python kit/selftest/anim/prop/run.py carried the same manifest with the bolt hung on the post, a part that does
                                                not move (2026-11-17, V3 Stage D: the game spawns it so - the post welded
                                                to the root, the bolt's Motor6D on the post): built, the bolt slides on the
                                                still post, and the model's pose tree runs Root -> post -> bolt
    python kit/selftest/anim/prop/run.py orphan the same manifest with the bolt hung on a part the model does not have:
                                                refused, named (this case FAILS) - before 2026-11-17 the refused case was
                                                the post above ("hung"), a ban V3 Stage D lifted

Prints one JSON line {schema, status, summary, next_action}; everything is written under build/selftest/ in a folder
of this run's own, removed at the end.
"""
import contextlib
import io
import json
import math
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C  # noqa: E402
import metrics as MT  # noqa: E402
import prop_rig as PR  # noqa: E402

CHEST = {"name": "SelftestChest", "root": "Base",
         "parts": {"Base": {"size": [4, 2, 3], "at": [0, 1, 0]},
                   "Lid": {"size": [4, 0.5, 3], "at": [0, 2.25, 0], "parent": "Base", "joint": "Hinge",
                           "pivot": [0, 2, 1.5], "hinge": {"axis": [1, 0, 0], "min": 0, "max": 110}},
                   "Tray": {"size": [3, 0.3, 2], "at": [0, 1.2, 0], "parent": "Base", "joint": "Runner",
                            "pivot": [0, 1.2, 0], "slide": {"axis": [0, 0, -1], "min": 0, "max": 1.8}},
                   "Handle": {"size": [1, 0.2, 0.2], "at": [0, 2.6, -1.4], "parent": "Lid", "pivot": [0, 2.5, -1.4]}}}


GATE = {"asset": "SelftestGate", "build_id": "selftest",
        "groups": {"main": {"size_studs": [4, 0.4, 0.4], "center": [0, 0.2, 0]},
                   "post": {"size_studs": [0.4, 4, 0.4], "center": [0, 2.4, 0]},
                   "arm": {"size_studs": [3, 0.3, 0.3], "center": [1.5, 4.2, 0]},
                   "bolt": {"size_studs": [0.6, 0.1, 0.1], "center": [2.9, 4.2, 0.2]}},
        "joints": {"Swing": {"group": "arm", "kind": "hinge", "parent": "main", "axis": [0, 0, 1], "pivot": [0, 4.2, 0],
                             "min": 0, "max": 90},
                   "Throw": {"group": "bolt", "kind": "slide", "parent": "arm", "axis": [1, 0, 0], "pivot": [2.9, 4.2, 0.2],
                             "min": 0, "max": 0.3}}}


def model_case(run, case):
    man = json.loads(json.dumps(GATE))
    if case == "carried":
        man["joints"]["Throw"]["parent"] = "post"
    if case == "orphan":
        man["joints"]["Throw"]["parent"] = "ghost"
    mp, kp, game = os.path.join(run, "SelftestGate.manifest.json"), os.path.join(run, "SelftestGateOpen.json"), os.path.join(run, "game")
    with open(mp, "w", encoding="utf-8") as fh:
        json.dump(man, fh)
    keys = {"name": "SelftestGateOpen", "rig": "SelftestGate", "loop": False, "priority": "Action", "fps": 30,
            "keys": [{"t": 0, "ease": "Cubic", "dir": "InOut", "pose": {"arm": [0, 0, 0], "bolt": {"rot": [0, 0, 0], "pos": [0, 0, 0]}}},
                     {"t": 1.0, "ease": "Cubic", "dir": "InOut", "pose": {"arm": [0, 0, 90], "bolt": {"rot": [0, 0, 0], "pos": [0.3, 0, 0]}}}]}
    with open(kp, "w", encoding="utf-8") as fh:
        json.dump(keys, fh)
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        code = PR.main(["go", mp, kp, "--out", game])
    v = json.loads(said.getvalue().strip().splitlines()[-1])
    model = os.path.join(game, "SelftestGateOpen.model.json")
    if case == "carried":
        return carried_case(code, v, game, model)
    if case == "orphan":
        if code != 0 and os.path.isfile(model):
            return out("pass", "prop selftest: a model that cannot be animated left a clip's model behind", "kit/anim/prop_rig.py go")
        return out("pass" if code == 0 else "fail", v["summary"], v.get("next_action") or "none")
    wrong = []
    if code != 0 or not os.path.isfile(model):
        wrong.append(f"the spec did not reach the game's model ({v['summary']})")
    else:
        with open(os.path.join(game, "SelftestGateOpen.clip.json"), encoding="utf-8") as fh:
            made = json.load(fh)
        with open(os.path.join(game, "selftestgate.rig.json"), encoding="utf-8") as fh:
            rig = json.load(fh)
        W = C.world_frames(made, rig)
        if not np.allclose(W[-1]["arm"][:3, 3], [0, 5.7, 0], atol=1e-3):
            wrong.append("the compiled clip does not swing the arm 90 degrees about the hinge's own axis")
        if not np.allclose(W[-1]["bolt"][:3, 3], [0, 7.4, 0.2], atol=1e-3):
            wrong.append("the bolt does not ride the arm and slide 0.3 studs along its runner")
        with open(model, encoding="utf-8") as fh:
            frames = [k for k in json.load(fh)["Children"] if k["ClassName"] == "Keyframe"]
        top = frames[-1]["Children"]
        arm = top[0]["Children"][0] if len(top) == 1 and top[0]["Name"] == "Root" and top[0].get("Children") else None
        if not arm or arm["Name"] != "arm" or not np.allclose(arm["Properties"]["CFrame"]["CFrame"]["orientation"],
                                                             [[1, 0, 0], [0, 0, -1], [0, 1, 0]], atol=1e-4):
            wrong.append("the model's pose of the arm is not a 90 degree turn about the joint's own X under Root "
                         "(what the spawned model's Motor6D takes)")
        bolt = arm["Children"][0] if arm and arm.get("Children") else None
        if not bolt or bolt["Name"] != "bolt" or not np.allclose(bolt["Properties"]["CFrame"]["CFrame"]["position"], [0.3, 0, 0], atol=1e-4):
            wrong.append("the model's pose of the bolt is not a 0.3 stud slide along the joint's own X under the arm")
    if wrong:
        return out("fail", "prop selftest (a built model): " + "; ".join(wrong), "kit/anim/prop_rig.py from_model")
    return out("pass", "prop selftest (a built model): the gate's manifest gave the rig of the model the game spawns; its spec "
                       "went the whole way, the arm swings 90 degrees about its hinge, the bolt rides it, and the model's pose "
                       "is the joint's own turn", "none - proceed")


def carried_case(code, v, game, model):
    """the bolt on the still post: built; it slides 0.3 along X while the post stays; the pose tree goes through the post"""
    wrong = []
    if code != 0 or not os.path.isfile(model):
        return out("fail", f"prop selftest (carried): the bolt on the fixed post was not built ({v['summary']})",
                   "kit/anim/prop_rig.py from_model")
    with open(os.path.join(game, "SelftestGateOpen.clip.json"), encoding="utf-8") as fh:
        made = json.load(fh)
    with open(os.path.join(game, "selftestgate.rig.json"), encoding="utf-8") as fh:
        rig = json.load(fh)
    j = rig["joints"].get("post") or {}
    if j.get("parent") != "Root" or not j.get("welded") or rig["limits"].get("post", {}).get("kind") != "fixed":
        wrong.append("the rig does not carry the post as a fixed part welded to the root")
    if (rig["joints"].get("bolt") or {}).get("parent") != "post":
        wrong.append("the bolt does not hang on the post in the rig")
    W = C.world_frames(made, rig)
    if not np.allclose(W[-1]["post"][:3, 3], W[0]["post"][:3, 3], atol=1e-6):
        wrong.append("the post moved")
    if not np.allclose(W[-1]["bolt"][:3, 3] - W[0]["bolt"][:3, 3], [0.3, 0, 0], atol=1e-3):
        wrong.append("the bolt did not slide 0.3 studs along its runner on the still post")
    with open(model, encoding="utf-8") as fh:
        frames = [k for k in json.load(fh)["Children"] if k["ClassName"] == "Keyframe"]
    top = frames[-1]["Children"][0] if frames and frames[-1].get("Children") else {}
    post = next((p for p in top.get("Children") or [] if p["Name"] == "post"), None)
    bolt = (post or {}).get("Children") or []
    if top.get("Name") != "Root" or not post or post["Properties"]["Weight"] != 0 or [p["Name"] for p in bolt] != ["bolt"]:
        wrong.append("the model's pose tree does not run Root -> post (not moved) -> bolt, as the game's joints do")
    if wrong:
        return out("fail", "prop selftest (carried): " + "; ".join(wrong), "kit/anim/prop_rig.py from_model")
    return out("pass", "prop selftest (carried): the bolt hung on the fixed post is built; it slides 0.3 studs on the still "
                       "post and the model's pose tree runs Root -> post -> bolt", "none - proceed")


def clip_of(name, lid_to, n=31):
    lid, tray = [], []
    for i in range(n):
        a = math.radians(lid_to * i / (n - 1)) / 2
        lid.append([math.sin(a), 0.0, 0.0, math.cos(a), 0.0, 0.0, 0.0])
        tray.append([0.0, 0.0, 0.0, 1.0, 0.0, 0.0, -1.5 * i / (n - 1)])
    return {"name": name, "rig": "SelftestChest", "fps": 30, "times": [round(i / 30, 6) for i in range(n)], "events": [],
            "joints": {"Lid": {"frames": lid}, "Tray": {"frames": tray}}}


def out(status, summary, next_action):
    print(json.dumps({"schema": 1, "status": status, "summary": summary, "next_action": next_action}))
    return 0 if status == "pass" else 1


def main(case):
    run = os.path.join(os.environ.get("KIT_BUILD", os.path.join(ROOT, "build")), "selftest", f"anim_prop_{os.getpid()}")
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(run)
    try:
        spec, rig_path = os.path.join(run, "chest.json"), os.path.join(run, "rigs", "selftestchest.json")
        with open(spec, "w", encoding="utf-8") as fh:
            json.dump(CHEST, fh)
        if case in ("model", "carried", "orphan"):
            return model_case(run, case)
        if case in ("whole", "spec"):
            lid = 140 if case == "spec" else 90
            keys = {"name": "SelftestChestOpen", "rig": "SelftestChest", "loop": False, "priority": "Action", "fps": 30,
                    "keys": [{"t": 0, "ease": "Cubic", "dir": "InOut", "pose": {"Lid": [0, 0, 0], "Tray": {"rot": [0, 0, 0], "pos": [0, 0, 0]}}},
                             {"t": 1.0, "ease": "Cubic", "dir": "InOut",
                              "pose": {"Lid": [lid, 0, 0], "Tray": {"rot": [0, 0, 0], "pos": [0, 0, -1.5]}}}]}
            kp, game = os.path.join(run, "SelftestChestOpen.json"), os.path.join(run, "game")
            with open(kp, "w", encoding="utf-8") as fh:
                json.dump(keys, fh)
            if case == "spec":                                 # an earlier, good build stands there first
                good = dict(keys, keys=[keys["keys"][0], {**keys["keys"][1], "pose": {**keys["keys"][1]["pose"], "Lid": [90, 0, 0]}}])
                with open(kp, "w", encoding="utf-8") as fh:
                    json.dump(good, fh)
                with contextlib.redirect_stdout(io.StringIO()):
                    first = PR.main(["go", spec, kp, "--out", game])
                if first != 0 or not os.path.isfile(os.path.join(game, "SelftestChestOpen.model.json")):
                    return out("pass", "prop selftest: the good build that should stand first was not made", "kit/anim/prop_rig.py go")
                with open(kp, "w", encoding="utf-8") as fh:
                    json.dump(keys, fh)
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                code = PR.main(["go", spec, kp, "--out", game])
            v = json.loads(said.getvalue().strip().splitlines()[-1])
            model = os.path.join(game, "SelftestChestOpen.model.json")
            if case == "spec":
                if code != 0 and os.path.isfile(model):
                    return out("pass", "prop selftest: a clip that breaks a joint left its model behind", "kit/anim/prop_rig.py go")
                return out("pass" if code == 0 else "fail", v["summary"], v.get("next_action") or "none")
            wrong = []
            if code != 0 or not os.path.isfile(model):
                wrong.append(f"the spec did not reach the game's model ({v['summary']})")
            else:
                with open(model, encoding="utf-8") as fh:
                    text = fh.read()
                if '"KeyframeSequence"' not in text or '"Name": "Lid"' not in text and '"Name":"Lid"' not in text:
                    wrong.append("the model is not a KeyframeSequence that poses the lid")
                with open(os.path.join(game, "SelftestChestOpen.clip.json"), encoding="utf-8") as fh:
                    made = json.load(fh)
                with open(os.path.join(game, "selftestchest.rig.json"), encoding="utf-8") as fh:
                    made_rig = json.load(fh)
                W = C.world_frames(made, made_rig)
                if abs(float((W[-1]["Lid"] @ np.array([0.0, -0.25, -1.5, 1.0]))[1]) - 4.0) > 1e-3:
                    wrong.append("the compiled clip does not open the lid 90 degrees upward about its hinge")
            if wrong:
                return out("fail", "prop selftest (the whole way): " + "; ".join(wrong), "kit/anim/prop_rig.py go")
            return out("pass", "prop selftest (the whole way): the chest's prop file and its keyframe spec went through the "
                               "kit's compiler to a KeyframeSequence model; the compiled clip opens the lid 90 degrees upward "
                               "about its hinge and stays inside every joint", "none - proceed")
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            made = PR.main(["make", spec, "--out", rig_path])
        if made != 0:
            return out("fail", f"prop selftest: the chest's rig was not made ({said.getvalue().strip()[-200:]})", "kit/anim/prop_rig.py make")
        with open(rig_path, encoding="utf-8") as fh:
            rig = json.load(fh)
        real = C.load_rig
        C.load_rig = lambda name, root=".": rig if name == "SelftestChest" else real(name, root)     # (the run's own rig)
        name = "SelftestChestTorn" if case == "torn" else "SelftestChestOpen"
        cp = os.path.join(run, f"{name}.clip.json")
        clip = clip_of(name, 140 if case == "torn" else 90)
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump(clip, fh)
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            code = MT.main([cp])
        v = json.loads(said.getvalue().strip().splitlines()[-1])
        if case == "torn":
            return out("pass" if code == 0 else "fail", v["summary"], v.get("next_action") or "none")
        wrong = []
        if code != 0:
            wrong.append(f"a clip inside its joints failed the motion gates ({v['summary']})")
        W = C.world_frames(clip, rig)
        hinge = [(W[i]["Lid"] @ np.array([0.0, -0.25, 1.5, 1.0]))[:3] for i in (0, 15, 30)]
        if max(float(np.linalg.norm(h - np.array([0.0, 1.0, 1.5]))) for h in hinge) > 1e-4:
            wrong.append("the lid's hinge line moved as it opened")
        if abs(float((W[30]["Lid"] @ np.array([0.0, -0.25, -1.5, 1.0]))[1]) - 4.0) > 1e-4:
            wrong.append("the lid's front edge did not swing UP (3 studs) as it opened")
        if float(np.linalg.norm(W[30]["Handle"][:3, 3] - W[0]["Handle"][:3, 3])) < 2.0:
            wrong.append("the handle did not ride the lid")
        if not np.allclose(W[30]["Tray"][:3, 3] - W[0]["Tray"][:3, 3], [0, 0, -1.5], atol=1e-4):
            wrong.append("the tray did not slide along its runner")
        if wrong:
            return out("fail", "prop selftest: " + "; ".join(wrong), "kit/anim/prop_rig.py")
        return out("pass", "prop selftest: the chest's rig is made from its prop file; the kit's FK opens the lid about its "
                           "hinge, carries the handle and slides the tray; a clip inside the joints passes the motion gates",
                   "none - proceed")
    finally:
        shutil.rmtree(run, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("good", "torn", "whole", "spec", "model", "carried", "orphan"):
        print(__doc__)
        sys.exit(2)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1]))
