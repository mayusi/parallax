"""kit/anim/prop_rig.py - a prop's rig from data and its clips held to its joints (the owner's method lists 2026-11-13:
object animation). The prop is a chest made up here: a base, a hinged lid, a sliding tray, a fixed handle."""
import copy
import json
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C            # noqa: E402
import metrics as MT        # noqa: E402
import prop_rig as PR       # noqa: E402

CHEST = {"name": "Chest", "root": "Base",
         "parts": {"Base": {"size": [4, 2, 3], "at": [0, 1, 0]},
                   "Lid": {"size": [4, 0.5, 3], "at": [0, 2.25, 0], "parent": "Base", "joint": "Hinge",
                           "pivot": [0, 2, 1.5], "hinge": {"axis": [1, 0, 0], "min": 0, "max": 110}},
                   "Tray": {"size": [3, 0.3, 2], "at": [0, 1.2, 0], "parent": "Base", "joint": "Runner",
                            "pivot": [0, 1.2, 0], "slide": {"axis": [0, 0, -1], "min": 0, "max": 1.8}},
                   "Handle": {"size": [1, 0.2, 0.2], "at": [0, 2.6, -1.4], "parent": "Lid", "pivot": [0, 2.5, -1.4]}}}
IDENT = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]


def quat(axis, deg):
    a = math.radians(deg) / 2
    return [axis[0] * math.sin(a), axis[1] * math.sin(a), axis[2] * math.sin(a), math.cos(a)]


def clip_of(lid=(0, 90), tray=(0.0, 1.5), n=31, lid_axis=(1, 0, 0), extra=None):
    frames = {"Lid": [], "Tray": []}
    for i in range(n):
        u = i / (n - 1)
        frames["Lid"].append(quat(lid_axis, lid[0] + (lid[1] - lid[0]) * u) + [0.0, 0.0, 0.0])
        d = tray[0] + (tray[1] - tray[0]) * u
        frames["Tray"].append([0.0, 0.0, 0.0, 1.0, 0.0, 0.0, -d])
    c = {"name": "ChestOpen", "rig": "Chest", "fps": 30, "times": [round(i / 30, 6) for i in range(n)], "events": [],
         "joints": {k: {"frames": v} for k, v in frames.items()}}
    for part, fr in (extra or {}).items():
        c["joints"][part] = {"frames": fr}
    return c


def test_a_prop_file_becomes_a_rig_in_the_kits_own_format():
    rig = PR.build(CHEST, today="2026-11-14")
    r6 = C.load_rig("r6", ROOT)
    assert set(r6) <= set(rig) | {"source"} and rig["kind"] == "prop" and rig["rig"] == "Chest" and rig["root"] == "Base"
    assert rig["order"] == ["Lid", "Tray", "Handle"]                       # parents before their children
    assert rig["joints"]["Lid"] == {"c0": [0, 1, 1.5, 1, 0, 0, 0, 1, 0, 0, 0, 1], "c1": [0, -0.25, 1.5, 1, 0, 0, 0, 1, 0, 0, 0, 1],
                                    "joint": "Hinge", "parent": "Base"}
    assert rig["rest"]["Lid"][:3] == [0, 1.25, 0] and rig["rest"]["Base"][:3] == [0, 0, 0]
    assert rig["limits"] == {"Lid": {"kind": "hinge", "axis": [1.0, 0.0, 0.0], "min": 0.0, "max": 110.0},
                             "Tray": {"kind": "slide", "axis": [0.0, 0.0, -1.0], "min": 0.0, "max": 1.8},
                             "Handle": {"kind": "fixed"}}


def test_the_kits_own_fk_opens_the_lid_about_its_hinge_and_carries_the_handle():
    rig = PR.build(CHEST)
    c = clip_of()
    W = C.world_frames(c, rig)
    rest = C.fk(rig)
    for part in ("Lid", "Tray", "Handle"):                                 # at rest: where the prop file put it
        assert np.allclose(rest[part][:3, 3], rig["rest"][part][:3], atol=1e-6)
    hinge_local = np.array([0.0, -0.25, 1.5, 1.0])                         # the hinge line, in the lid's own frame
    front_local = np.array([0.0, -0.25, -1.5, 1.0])
    for i in (0, 15, 30):
        assert np.allclose((W[i]["Lid"] @ hinge_local)[:3], [0, 1, 1.5], atol=1e-5)      # the hinge does not move
    opened = (W[30]["Lid"] @ front_local)[:3]
    assert abs(opened[1] - 4.0) < 1e-4                                                  # +90 about +x: the front edge swings UP
    assert abs(opened[2] - 1.5) < 1e-4
    assert np.linalg.norm(W[30]["Handle"][:3, 3] - W[0]["Handle"][:3, 3]) > 2.0          # the handle rides the lid
    assert np.allclose(W[30]["Tray"][:3, 3] - W[0]["Tray"][:3, 3], [0, 0, -1.5], atol=1e-5)


def test_a_clip_inside_its_joints_passes():
    rig = PR.build(CHEST)
    assert PR.check_clip(clip_of(), rig) == [] and PR.gate(clip_of(), rig) == ({"faults": []}, None)
    assert PR.gate(clip_of(), {"rig": "R6"}) == (None, None)               # not a prop: nothing to hold


@pytest.mark.parametrize("kw, part, said", [
    ({"lid": (0, 140)}, "Lid", "turns to 140 deg; its hinge runs 0 to 110"),
    ({"lid": (-20, 90)}, "Lid", "turns to -20 deg"),
    ({"lid_axis": (0, 1, 0)}, "Lid", "off its hinge"),
    ({"tray": (0.0, 2.5)}, "Tray", "slides to 2.50 studs; its runner goes 0 to 1.8"),
    ({"tray": (-0.5, 1.0)}, "Tray", "slides to -0.50 studs"),
])
def test_a_part_that_moves_as_its_joint_does_not_allow_is_named(kw, part, said):
    rig = PR.build(CHEST)
    faults = PR.check_clip(clip_of(**kw), rig)
    assert faults and faults[0]["part"] == part and said in faults[0]["what"]
    held, problem = PR.gate(clip_of(**kw), rig)
    assert problem.startswith(f"{part} ") and "at frame" in problem and "as its joint allows" in problem


def test_slips_turns_of_a_slide_and_a_fixed_part_are_named():
    rig = PR.build(CHEST)
    n = 31
    slip = clip_of()
    slip["joints"]["Lid"]["frames"][10][4:7] = [0.0, 0.3, 0.0]             # the lid lifts off its hinge
    assert any(f["part"] == "Lid" and "slides 0.30 studs off its hinge" in f["what"] and f["frame"] == 10 for f in PR.check_clip(slip, rig))
    side = clip_of()
    side["joints"]["Tray"]["frames"][20][4] = 0.4                          # the tray leaves its runner sideways
    assert any(f["part"] == "Tray" and "leaves its runner by 0.40" in f["what"] for f in PR.check_clip(side, rig))
    turn = clip_of()
    turn["joints"]["Tray"]["frames"][5][:4] = quat((0, 1, 0), 15)
    assert any(f["part"] == "Tray" and "a sliding part does not turn" in f["what"] for f in PR.check_clip(turn, rig))
    fixed = clip_of(extra={"Handle": [quat((0, 0, 1), 30) + [0, 0, 0]] * n})
    assert any(f["part"] == "Handle" and "it is fixed to its parent" in f["what"] for f in PR.check_clip(fixed, rig))
    base = clip_of(extra={"Base": [[0, 0, 0, 1, 0, 0.5, 0]] * n})
    assert any(f["part"] == "Base" and "moves 0.50 studs" in f["what"] for f in PR.check_clip(base, rig))
    ghost = clip_of(extra={"Wheel": [IDENT] * n})
    assert any(f["part"] == "Wheel" and "is not a part of this prop" in f["what"] for f in PR.check_clip(ghost, rig))
    short = clip_of()
    short["joints"]["Lid"]["frames"] = short["joints"]["Lid"]["frames"][:5]
    assert any("has 5 frame(s) and the clip 31" in f["what"] for f in PR.check_clip(short, rig))
    assert PR.check_clip(clip_of(lid=(0, 110.3)), rig) == []               # (a solver's rounding past the stop is not a swing through it)


def edit(path, value):
    d = copy.deepcopy(CHEST)
    cur = d
    for k in path[:-1]:
        cur = cur[k]
    if value is None:
        cur.pop(path[-1], None)
    else:
        cur[path[-1]] = value
    return d


@pytest.mark.parametrize("spec, why", [
    (edit(["root"], "Nothing"), "its root 'Nothing' is not one of its parts"),
    (edit(["name"], "a chest"), "the prop has no name"),
    (edit(["parts", "Lid", "parent"], "Roof"), "its parent 'Roof' is not another part"),
    (edit(["parts", "Lid", "pivot"], [0, 6, 0]), "its pivot is"),
    (edit(["parts", "Lid", "pivot"], None), "it has no pivot"),
    (edit(["parts", "Lid", "size"], [4, 0, 3]), "a part has a size"),
    (edit(["parts", "Lid", "slide"], {"axis": [0, 0, 1], "min": 0, "max": 1}), "not both"),
    (edit(["parts", "Lid", "hinge"], {"axis": [0, 0, 0], "min": 0, "max": 90}), "its hinge is"),
    (edit(["parts", "Lid", "hinge"], {"axis": [1, 0, 0], "min": 90, "max": 90}), "its hinge is"),
    (edit(["parts", "Lid", "hinge"], {"axis": [1, 0, 0], "min": 90, "max": 10}), "its hinge is"),
    (edit(["parts", "Base", "parent"], "Lid"), "the root stands still"),
    (edit(["name"], "R6"), "that is a character rig's name"),
    (edit(["root"], ["Base"]), "is not one of its parts"),
    (edit(["parts", "Lid", "parent"], ["Base"]), "is not another part"),
    (edit(["parts", "Lid", "hinge"], None) | {"parts": {**CHEST["parts"], "Lid": {**CHEST["parts"]["Lid"], "hinge": None}}}, "its hinge is"),
    (edit(["parts", "Lid", "hinge"], {"axis": [1, 0, 0], "min": 0, "max": 3601}), "inside -3600 to 3600"),
    (edit(["parts", "Lid", "hinge"], {"axis": [1, 0, 0], "min": 0, "max": float("inf")}), "its hinge is"),
    ({"name": "X"}, "a prop file is"),
])
def test_what_cannot_be_a_prop_is_refused(spec, why):
    assert any(why in p for p in PR.problems(spec))
    with pytest.raises(ValueError, match=why.split("'")[0].strip()[:20]):
        PR.build(spec)


def test_a_loop_of_parents_is_refused():
    loop = copy.deepcopy(CHEST)
    loop["parts"]["Lid"]["parent"] = "Handle"
    loop["parts"]["Lid"]["pivot"] = [0, 2.5, -1.4]
    assert any("does not lead back to the root" in p for p in PR.problems(loop))


def test_make_and_clip_as_commands_and_the_builds_motion_gates(tmp_path, capsys, monkeypatch):
    spec, rig_path, cp = tmp_path / "chest.json", tmp_path / "rigs" / "chest.json", tmp_path / "ChestOpen.clip.json"
    spec.write_text(json.dumps(CHEST), encoding="utf-8")
    assert PR.main(["make", str(spec), "--out", str(rig_path)]) == 0
    v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "4 part(s), 1 hinge(s), 1 slide(s), 1 fixed" in v["summary"] and json.load(open(str(rig_path)))["kind"] == "prop"
    cp.write_text(json.dumps(clip_of()), encoding="utf-8")
    assert PR.main(["clip", str(cp), "--rig", str(rig_path)]) == 0
    capsys.readouterr()
    cp.write_text(json.dumps(clip_of(lid=(0, 140))), encoding="utf-8")
    assert PR.main(["clip", str(cp), "--rig", str(rig_path)]) == 1
    assert "Lid turns to 140 deg" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(edit(["parts", "Lid", "pivot"], [0, 6, 0])), encoding="utf-8")
    assert PR.main(["make", str(bad), "--out", str(tmp_path / "x.json")]) == 1 and not (tmp_path / "x.json").exists()
    assert "is not a prop" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    r6 = tmp_path / "r6.json"
    r6.write_text(json.dumps(C.load_rig("r6", ROOT)), encoding="utf-8")
    assert PR.main(["clip", str(cp), "--rig", str(r6)]) == 1
    assert "is not a prop's rig" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]


def test_the_builds_motion_gates_hold_a_props_clip_to_its_joints(tmp_path, capsys, monkeypatch):
    rig = PR.build(CHEST)
    real = C.load_rig
    monkeypatch.setattr(C, "load_rig", lambda name, root=".": rig if name == "Chest" else real(name, root))
    good, bad = tmp_path / "ChestOpen.clip.json", tmp_path / "ChestTorn.clip.json"
    good.write_text(json.dumps(clip_of()), encoding="utf-8")
    bad.write_text(json.dumps(dict(clip_of(lid=(0, 140)), name="ChestTorn")), encoding="utf-8")
    assert MT.main([str(good)]) == 0
    assert json.load(open(str(tmp_path / "ChestOpen.metrics.json")))["prop"] == {"faults": []}
    capsys.readouterr()
    assert MT.main([str(bad)]) == 1
    v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "ChestTorn: Lid turns to 140 deg; its hinge runs 0 to 110" in v["summary"]


# ---- what the stage's review found (2026-11-14) ----
def test_a_prop_is_not_judged_by_a_characters_gates(tmp_path, capsys, monkeypatch):
    rig = PR.build(CHEST)
    real = C.load_rig
    monkeypatch.setattr(C, "load_rig", lambda name, root=".": rig if name == "Chest" else real(name, root))
    fast = clip_of(tray=(0.0, 1.8), n=11)                    # the tray slides its whole legal run in a third of a second
    assert PR.check_clip(fast, rig) == []
    p = tmp_path / "ChestFast.clip.json"
    p.write_text(json.dumps(dict(fast, name="ChestFast")), encoding="utf-8")
    assert MT.main([str(p)]) == 0                            # (a character's foot-slide gate called the tray a foot)
    m = json.load(open(str(tmp_path / "ChestFast.metrics.json")))
    assert m["problems"] == [] and m["prop"] == {"faults": []} and "character_gates_not_for_a_prop" in m


def test_a_part_that_spins_freely_is_held_to_its_axis_only():
    wheel = {"name": "Cart", "root": "Body", "parts": {"Body": {"size": [4, 1, 2], "at": [0, 1, 0]},
             "Wheel": {"size": [0.4, 1, 1], "at": [2.2, 0.5, 0], "parent": "Body", "pivot": [2.0, 0.5, 0],
                       "hinge": {"axis": [1, 0, 0], "min": -180, "max": 180}}}}
    rig = PR.build(wheel)
    n = 61
    spin = {"name": "CartRoll", "rig": "Cart", "fps": 30, "times": [round(i / 30, 6) for i in range(n)], "events": [],
            "joints": {"Wheel": {"frames": [quat((1, 0, 0), 24 * i) + [0, 0, 0] for i in range(n)]}}}      # four whole turns
    assert PR.check_clip(spin, rig) == []
    spin["joints"]["Wheel"]["frames"][7] = quat((0, 0, 1), 20) + [0, 0, 0]
    assert any("off its hinge" in f["what"] for f in PR.check_clip(spin, rig))


def test_frames_that_are_not_a_pose_another_rigs_clip_and_a_travelling_prop_are_named():
    rig = PR.build(CHEST)
    short = clip_of()
    short["joints"]["Lid"]["frames"][3] = [0, 0, 0, 1]
    assert any("is not a turn and a place" in f["what"] and f["frame"] == 3 for f in PR.check_clip(short, rig))
    big = clip_of()
    big["joints"]["Lid"]["frames"][4] = [3 * v for v in big["joints"]["Lid"]["frames"][4]]
    assert any("is not a turn and a place" in f["what"] for f in PR.check_clip(big, rig))
    assert "is made for the rig Door" in PR.check_clip(dict(clip_of(), rig="Door"), rig)[0]["what"]
    walk = dict(clip_of(), root=[[0, 0, 0, 1, 0.1 * i, 0, 0] for i in range(31)])
    assert any(f["part"] == "the whole prop" for f in PR.check_clip(walk, rig))
    base = clip_of(extra={"Base": [[0, 0, 0, 1, 0, 0.5, 0]] * 31})
    assert any("it is the prop's root" in f["what"] for f in PR.check_clip(base, rig))


def test_the_worst_fault_is_the_one_said_and_the_name_is_said_once(tmp_path, capsys):
    rig = PR.build(CHEST)
    c = clip_of(lid=(0, 140), tray=(0.0, 1.85))              # the tray 0.05 past its run, the lid 30 degrees through its stop
    held, problem = PR.gate(c, rig)
    assert problem.startswith("Lid turns to 140 deg") and "(+1 more fault(s))" in problem
    spec, out = tmp_path / "chest.json", tmp_path / "box.json"
    spec.write_text(json.dumps(CHEST), encoding="utf-8")
    assert PR.main(["make", str(spec), "--out", str(out)]) == 1 and not out.exists()
    assert "is the file chest.json" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]


# ---- the whole way: a prop's keyframe spec to the model the game plays (kit/anim/prop_rig.py go) ----
def spec_of(name="ChestOpen", lid=90, tray=-1.5):
    return {"name": name, "rig": "Chest", "loop": False, "priority": "Action", "fps": 30,
            "keys": [{"t": 0, "ease": "Cubic", "dir": "InOut", "pose": {"Lid": [0, 0, 0], "Tray": {"rot": [0, 0, 0], "pos": [0, 0, 0]}}},
                     {"t": 1.0, "ease": "Cubic", "dir": "InOut", "pose": {"Lid": [lid, 0, 0], "Tray": {"rot": [0, 0, 0], "pos": [0, 0, tray]}}}]}


def files(tmp_path, **specs):
    prop = tmp_path / "Chest.prop.json"
    prop.write_text(json.dumps(CHEST), encoding="utf-8")
    out = []
    for name, sp in specs.items():
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(sp), encoding="utf-8")
        out.append(str(p))
    return str(prop), out, str(tmp_path / "game")


def test_a_props_spec_goes_the_whole_way_to_the_model_the_game_plays(tmp_path):
    import shutil
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    prop, specs, out = files(tmp_path, ChestOpen=spec_of())
    m = PR.go(prop, specs, out)
    assert m["refused"] == [] and [b["name"] for b in m["built"]] == ["ChestOpen"]
    assert sorted(os.listdir(out)) == ["ChestOpen.clip.json", "ChestOpen.model.json", "chest.props.json", "chest.rig.json"]
    game, kept = str(tmp_path / "tree"), str(tmp_path / "kept")
    PR.go(prop, specs, game, keep=kept)
    assert os.listdir(game) == ["ChestOpen.model.json"]                        # the game's tree gets the model and nothing else
    assert sorted(os.listdir(kept)) == ["ChestOpen.clip.json", "chest.props.json", "chest.rig.json"]
    # the model itself: its poses nested as the prop's parts are, the last key the joint's own turn and slide
    rig0 = PR.build(CHEST)
    frames = [k for k in json.load(open(os.path.join(game, "ChestOpen.model.json")))["Children"] if k["ClassName"] == "Keyframe"]

    def walk(pose, parent, seen):
        seen[pose["Name"]] = (parent, pose["Properties"]["CFrame"]["CFrame"])
        for ch in pose.get("Children") or []:
            walk(ch, pose["Name"], seen)
    seen = {}
    for top in frames[-1]["Children"]:
        walk(top, None, seen)
    assert seen["Base"][0] is None and all(seen[p][0] == rig0["joints"][p]["parent"] for p in seen if p != "Base")
    lid, tray = seen["Lid"][1], seen["Tray"][1]
    assert np.allclose(lid["orientation"], [[1, 0, 0], [0, 0, -1], [0, 1, 0]], atol=1e-4) and np.allclose(lid["position"], [0, 0, 0], atol=1e-6)
    assert np.allclose(tray["position"], [0, 0, -1.5], atol=1e-4) and np.allclose(tray["orientation"], np.eye(3), atol=1e-6)
    model = json.load(open(os.path.join(out, "ChestOpen.model.json")))
    text = json.dumps(model)
    assert model["ClassName"] == "KeyframeSequence" and '"Name": "Lid"' in text and '"Name": "Tray"' in text
    clip = json.load(open(os.path.join(out, "ChestOpen.clip.json")))
    rig = json.load(open(os.path.join(out, "chest.rig.json")))
    assert clip["rig"] == "Chest" and PR.check_clip(clip, rig) == []
    last = clip["joints"]["Lid"]["frames"][-1]
    assert abs(PR._turn(last[:4], np.array([1.0, 0, 0]))[0] - 90.0) < 0.5      # the compiler's clip opens the lid 90 about its hinge
    W = C.world_frames(clip, rig)
    assert abs(float((W[-1]["Lid"] @ np.array([0.0, -0.25, -1.5, 1.0]))[1]) - 4.0) < 1e-3   # ... upward, as the prop file means


def test_a_spec_that_breaks_a_joint_leaves_no_model_and_removes_an_older_one(tmp_path):
    import shutil
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    prop, specs, out = files(tmp_path, ChestOpen=spec_of())
    assert PR.go(prop, specs, out)["refused"] == [] and os.path.isfile(os.path.join(out, "ChestOpen.model.json"))
    prop, specs, out = files(tmp_path, ChestOpen=spec_of(lid=140), ChestSlide=spec_of("ChestSlide", lid=30))
    m = PR.go(prop, specs, out)
    assert [b["name"] for b in m["built"]] == ["ChestSlide"] and len(m["refused"]) == 1
    assert "ChestOpen: Lid turns to 140 deg; its hinge runs 0 to 110" in m["refused"][0]["why"]
    assert not os.path.exists(os.path.join(out, "ChestOpen.model.json"))       # the model of the earlier, good build is gone
    assert os.path.isfile(os.path.join(out, "ChestSlide.model.json"))
    assert json.load(open(os.path.join(out, "chest.props.json")))["refused"][0]["spec"].endswith("ChestOpen.json")
    # a spec renamed, one that no longer parses, two of one name: nothing of the last build is left standing
    (tmp_path / "ChestSlide.json").write_text("{not json", encoding="utf-8")
    twin_a, twin_b = tmp_path / "TwinA.json", tmp_path / "TwinB.json"
    twin_a.write_text(json.dumps(spec_of("Twin", lid=20)), encoding="utf-8")
    twin_b.write_text(json.dumps(spec_of("Twin", lid=40)), encoding="utf-8")
    m = PR.go(prop, [str(tmp_path / "ChestSlide.json"), str(twin_a), str(twin_b)], out)
    assert m["built"] == [] and len(m["refused"]) == 3 and sum("2 specs carry this name" in r["why"] for r in m["refused"]) == 2
    assert [f for f in os.listdir(out) if f.endswith((".model.json", ".clip.json"))] == []
    keep_me = tmp_path / "game" / "notes.txt"
    keep_me.write_text("mine")
    PR.go(prop, [str(twin_a)], out)
    assert keep_me.read_text() == "mine" and os.path.isfile(prop)             # nothing but its own outputs is ever removed


def test_go_as_a_command_and_what_it_refuses(tmp_path, capsys):
    import shutil
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    prop, specs, out = files(tmp_path, ChestOpen=spec_of(), Wrong=dict(spec_of("Wrong"), rig="R6"),
                             Ghost=dict(spec_of("Ghost"), keys=[{"t": 0, "pose": {"Wheel": [0, 0, 0]}}, {"t": 1, "pose": {"Wheel": [9, 0, 0]}}]))
    assert PR.main(["go", prop, *specs, "--out", out]) == 1
    v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "2 of 3 clip(s) NOT built" in v["summary"] and [b["name"] for b in v["built"]] == ["ChestOpen"]
    why = " | ".join(r["why"] for r in v["refused"])
    assert "is not a prop's rig" in why and "Wheel" in why
    assert PR.main(["go", prop, specs[0], "--out", out]) == 0
    assert "its rig and 1 clip(s) built" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    bad = tmp_path / "Bad.prop.json"
    bad.write_text(json.dumps(edit(["parts", "Lid", "pivot"], [0, 6, 0])), encoding="utf-8")
    assert PR.main(["go", str(bad), specs[0], "--out", out]) == 1
    assert "is not a prop the kit can rig" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    assert PR.main(["go", prop, "--out", out]) == 1
    capsys.readouterr()
    assert PR.main(["go", prop, specs[0], "--out", out, "--lune", "no_such_lune_here"]) == 1
    assert "is not on this machine's path" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]


# ---- a prop the 3D lane built: its rig from the built model's manifest (the joints src/kit/Models.luau spawns) ----
GATE = {"asset": "Gate", "build_id": "abc123",
        "groups": {"main": {"size_studs": [4, 0.4, 0.4], "center": [0, 0.2, 0]},
                   "post": {"size_studs": [0.4, 4, 0.4], "center": [0, 2.4, 0]},
                   "arm": {"size_studs": [3, 0.3, 0.3], "center": [1.5, 4.2, 0]},
                   "bolt": {"size_studs": [0.6, 0.1, 0.1], "center": [2.9, 4.2, 0.2]},
                   "sign": {"size_studs": [1, 1, 0.1], "center": [0, 1, 0.3]}},
        "joints": {"Swing": {"group": "arm", "kind": "hinge", "parent": "main", "axis": [0, 0, 1], "pivot": [0, 4.2, 0],
                             "min": 0, "max": 90},
                   "Throw": {"group": "bolt", "kind": "slide", "parent": "arm", "axis": [1, 0, 0], "pivot": [2.9, 4.2, 0.2],
                             "min": 0, "max": 0.3},
                   "Plate": {"group": "sign", "kind": "fixed", "parent": "main", "axis": [0, 0, 1], "pivot": [0, 1, 0.3],
                             "min": 0, "max": 0}}}


def luau_frame(axis):
    """src/kit/Models.luau, line for line: CFrame.fromMatrix(pivot, axis, z:Cross(axis).Unit, z)"""
    x = np.array(axis, float) / np.linalg.norm(axis)
    up = np.array([0, 1.0, 0]) if abs(x[1]) < 0.95 else np.array([1.0, 0, 0])
    z = np.cross(x, up) / np.linalg.norm(np.cross(x, up))
    y = np.cross(z, x) / np.linalg.norm(np.cross(z, x))
    return np.stack([x, y, z], axis=1)


def test_a_built_models_manifest_becomes_the_rig_the_game_spawns():
    rig = PR.from_model(GATE, today="2026-11-14")
    assert rig["rig"] == "Gate" and rig["kind"] == "prop" and rig["root"] == "Root" and rig["order"] == ["arm", "bolt"]
    assert set(rig["sizes"]) == {"Root", "arm", "bolt"}                        # main, post and the fixed sign are welded: no part of it
    assert rig["joints"]["arm"]["parent"] == "Root" and rig["joints"]["arm"]["joint"] == "Swing"
    assert rig["joints"]["bolt"]["parent"] == "arm" and rig["source"]["build_id"] == "abc123"
    for g, par, piv in (("arm", [0, 0, 0], [0, 4.2, 0]), ("bolt", [1.5, 4.2, 0], [2.9, 4.2, 0.2])):
        j, R = rig["joints"][g], luau_frame(GATE["joints"][rig["joints"][g]["joint"]]["axis"])
        # Roblox: C0 = parent.CFrame:ToObjectSpace(frame), C1 = part.CFrame:ToObjectSpace(frame), the parts unturned
        assert np.allclose(j["c0"][:3], np.array(piv) - np.array(par)) and np.allclose(np.array(j["c0"][3:]).reshape(3, 3), R)
        assert np.allclose(j["c1"][:3], np.array(piv) - np.array(GATE["groups"][g]["center"]))
        assert np.allclose(np.array(j["c1"][3:]).reshape(3, 3), R) and abs(np.linalg.det(R) - 1) < 1e-9
        assert rig["limits"][g]["axis"] == GATE["joints"][j["joint"]]["axis"]  # a clip's frames: the parent's space at rest
        # ... and the kit's own conversion makes that the joint's own X: what Motor6D.Transform (Models.pose) turns about
        Rj, pj = C.joint_space(rig, g, C.quat_mat(quat(GATE["joints"][j["joint"]]["axis"], 90)), np.array(GATE["joints"][j["joint"]]["axis"], float))
        assert np.allclose(Rj, [[1, 0, 0], [0, 0, -1], [0, 1, 0]], atol=1e-9) and np.allclose(pj, [1, 0, 0], atol=1e-9)
    assert np.allclose(luau_frame([0, 1, 0])[:, 0], [0, 1, 0]) and np.allclose(PR._joint_frame([0, 1, 0]), luau_frame([0, 1, 0]))
    assert np.allclose(PR._joint_frame([0.3, -0.9, 0.2]), luau_frame([0.3, -0.9, 0.2]))


def model_clip(arm=90.0, bolt=0.3, n=31, arm_axis=(0, 0, 1)):
    joints = {"arm": {"frames": []}, "bolt": {"frames": []}}
    for i in range(n):
        u = i / (n - 1)
        joints["arm"]["frames"].append(quat(arm_axis, arm * u) + [0, 0, 0])
        joints["bolt"]["frames"].append([0, 0, 0, 1, bolt * u, 0, 0])
    return {"name": "GateOpen", "rig": "Gate", "fps": 30, "times": [i / 30 for i in range(n)], "joints": joints}


def test_the_kits_fk_swings_the_built_models_arm_about_its_own_axis_and_carries_the_bolt():
    rig = PR.from_model(GATE)
    W = C.world_frames(model_clip(), rig)
    assert np.allclose(W[0]["arm"][:3, 3], [1.5, 4.2, 0], atol=1e-6) and np.allclose(W[0]["bolt"][:3, 3], [2.9, 4.2, 0.2], atol=1e-6)
    # +90 degrees about world +Z through the pivot (0, 4.2, 0): the arm's centre goes from +X of the pivot to +Y of it
    assert np.allclose(W[-1]["arm"][:3, 3], [0, 5.7, 0], atol=1e-5)
    # the bolt rides the arm and has slid 0.3 along its own runner, which now points up
    assert np.allclose(W[-1]["bolt"][:3, 3], [0, 4.2 + 2.9 + 0.3, 0.2], atol=1e-5)
    assert PR.check_clip(model_clip(), rig) == []
    said = PR.check_clip(model_clip(arm=120), rig)
    assert len(said) == 1 and said[0]["part"] == "arm" and "turns to 120 deg; its hinge runs 0 to 90" in said[0]["what"]
    said = PR.check_clip(model_clip(arm=40, arm_axis=(1, 0, 0)), rig)          # turned about X: the hinge's axis is Z
    assert any("twists" in f["what"] for f in said)
    assert any("slides to 0.50 studs" in f["what"] for f in PR.check_clip(model_clip(bolt=0.5), rig))


def medit(path, value):
    m = copy.deepcopy(GATE)
    cur = m
    for k in path[:-1]:
        cur = cur[k]
    if value is None:
        del cur[path[-1]]
    else:
        cur[path[-1]] = value
    return m


@pytest.mark.parametrize("m, why", [
    (medit(["joints"], {"Plate": GATE["joints"]["Plate"]}), "has no moving part"),
    (medit(["asset"], "R6"), "character rig's name"),
    (medit(["asset"], "my gate"), "has no name"),
    (medit(["groups", "Root"], {"size_studs": [1, 1, 1], "center": [0, 0, 0]}), "named Root"),
    (medit(["joints", "Throw", "parent"], "ghost"), "hangs on 'ghost', which is not a part of the model"),
    (medit(["joints", "Swing", "group"], "ghost"), "moves a group the model does not have"),
    (medit(["joints", "Swing", "axis"], [0, 0, 0]), "needs an axis, a pivot and a range"),
    (medit(["joints", "Swing", "min"], 90), "needs an axis, a pivot and a range"),
    (medit(["joints", "Swing", "max"], 3601), "inside -3600 to 3600"),
    (medit(["joints", "Second"], dict(GATE["joints"]["Swing"], axis=[1, 0, 0])), "2 joints move this one part"),
    (medit(["joints", "Swing", "parent"], "bolt"), "run in a loop"),
    (medit(["joints", "Swing", "kind"], "ball"), "hinge | slide | fixed"),
])
def test_a_built_model_that_cannot_be_animated_is_refused(m, why):
    assert any(why in p for p in PR.model_problems(m)), PR.model_problems(m)
    with pytest.raises(ValueError):
        PR.from_model(m)


def test_a_prop_file_and_a_manifest_are_told_apart():
    assert PR.is_model(GATE) and not PR.is_model(CHEST) and not PR.is_model({"groups": {}}) and not PR.is_model([])
    assert PR.model_problems(CHEST)[0].startswith("a built model's manifest is")
    assert PR.model_problems(GATE) == [] and PR.problems(CHEST) == []


def test_a_built_models_spec_goes_the_whole_way(tmp_path, capsys):
    import shutil
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    man = tmp_path / "Gate.manifest.json"
    man.write_text(json.dumps(GATE), encoding="utf-8")

    def spec(name, arm, bolt=0.3):
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps({"name": name, "rig": "Gate", "loop": False, "priority": "Action", "fps": 30, "keys": [
            {"t": 0, "ease": "Cubic", "dir": "InOut", "pose": {"arm": [0, 0, 0], "bolt": {"rot": [0, 0, 0], "pos": [0, 0, 0]}}},
            {"t": 1.0, "ease": "Cubic", "dir": "InOut", "pose": {"arm": [0, 0, arm], "bolt": {"rot": [0, 0, 0], "pos": [bolt, 0, 0]}}}]}),
            encoding="utf-8")
        return str(p)
    game, kept = str(tmp_path / "tree"), str(tmp_path / "kept")
    m = PR.go(str(man), [spec("GateOpen", 90)], game, keep=kept)
    assert m["refused"] == [] and os.listdir(game) == ["GateOpen.model.json"]
    rig = json.load(open(os.path.join(kept, "gate.rig.json")))
    clip = json.load(open(os.path.join(kept, "GateOpen.clip.json")))
    W = C.world_frames(clip, rig)
    assert np.allclose(W[-1]["arm"][:3, 3], [0, 5.7, 0], atol=1e-3) and np.allclose(W[-1]["bolt"][:3, 3], [0, 7.4, 0.2], atol=1e-3)
    frames = [k for k in json.load(open(os.path.join(game, "GateOpen.model.json")))["Children"] if k["ClassName"] == "Keyframe"]
    top = frames[-1]["Children"]
    assert [p["Name"] for p in top] == ["Root"] and [p["Name"] for p in top[0]["Children"]] == ["arm"]
    arm = top[0]["Children"][0]
    assert [p["Name"] for p in arm["Children"]] == ["bolt"]
    # the pose IS Models.pose's Transform: CFrame.Angles(rad(90), 0, 0) for the hinge, CFrame.new(0.3, 0, 0) for the slide
    assert np.allclose(arm["Properties"]["CFrame"]["CFrame"]["orientation"], [[1, 0, 0], [0, 0, -1], [0, 1, 0]], atol=1e-4)
    assert np.allclose(arm["Children"][0]["Properties"]["CFrame"]["CFrame"]["position"], [0.3, 0, 0], atol=1e-4)
    m = PR.go(str(man), [spec("GateOpen", 120)], game, keep=kept)
    assert "arm turns to 120 deg; its hinge runs 0 to 90" in m["refused"][0]["why"] and os.listdir(game) == []
    bad = tmp_path / "Bad.manifest.json"
    bad.write_text(json.dumps(medit(["joints", "Throw", "parent"], "ghost")), encoding="utf-8")
    assert PR.main(["go", str(bad), spec("GateOpen", 90), "--out", game]) == 1
    assert "hangs on 'ghost'" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    # a moving part on a part that does not move (the bolt on the fixed post): built, its pose tree through the post,
    # as the game's joints run (Models.spawn: the post welded to the root, the bolt's Motor6D on the post)
    on_post = tmp_path / "OnPost.manifest.json"
    on_post.write_text(json.dumps(medit(["joints", "Throw", "parent"], "post")), encoding="utf-8")
    capsys.readouterr()
    assert PR.main(["go", str(on_post), spec("GateOpen", 90), "--out", game, "--keep", kept]) == 0
    top = [k for k in json.load(open(os.path.join(game, "GateOpen.model.json")))["Children"]
           if k["ClassName"] == "Keyframe"][-1]["Children"][0]
    assert sorted(p["Name"] for p in top["Children"]) == ["arm", "post"]
    post = next(p for p in top["Children"] if p["Name"] == "post")
    assert post["Properties"]["Weight"] == 0 and [p["Name"] for p in post["Children"]] == ["bolt"]


def test_the_joints_frame_is_the_one_the_game_builds_said_in_numbers_and_read_off_the_games_own_code():
    # worked by hand from src/kit/Models.luau: X = the axis, up = Y (or X when the axis is within 0.95 of Y),
    # Z = X x up, Y = Z x X; the rig stores the columns [X Y Z] row by row
    assert np.allclose(PR._joint_frame([0, 0, 1]), np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]]), atol=1e-7)
    assert np.allclose(PR._joint_frame([0, 5, 0]), np.array([[0, 1, 0], [1, 0, 0], [0, 0, -1]]), atol=1e-7)
    assert np.allclose(PR._joint_frame([1, 0, 0]), np.eye(3), atol=1e-7)
    assert np.allclose(PR._joint_frame([0, -1, 0]), np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]]), atol=1e-7)
    rig = PR.from_model(GATE)
    assert np.allclose(np.array(rig["joints"]["arm"]["c0"][3:]).reshape(3, 3), [[0, 0, -1], [0, 1, 0], [1, 0, 0]], atol=1e-7)
    code = open(os.path.join(ROOT, "src", "kit", "Models.luau"), encoding="utf-8").read()
    for line in ('root.Name = "Root"', 'root.Name = "Handle"', "local up = if math.abs(axis.Y) < 0.95 then Vector3.yAxis else Vector3.xAxis",
                 "local z = axis:Cross(up).Unit", "local frame = CFrame.fromMatrix(pivot, axis, z:Cross(axis).Unit, z)",
                 "motor.C0 = parent.CFrame:ToObjectSpace(frame)", "motor.C1 = p.CFrame:ToObjectSpace(frame)",
                 "motor.Transform = CFrame.Angles(math.rad(value), 0, 0)", "motor.Transform = CFrame.new(value, 0, 0)",
                 "p.Name = group.Name", "p.CFrame = CFrame.new(center)"):
        assert line in code, f"src/kit/Models.luau no longer says `{line}`: kit/anim/prop_rig.py from_model mirrors it"


def test_a_tools_root_is_handle_a_wrong_name_and_a_parent_that_is_no_name_are_refused(tmp_path):
    rig = PR.from_model(GATE, root="Handle")
    assert rig["root"] == "Handle" and rig["joints"]["arm"]["parent"] == "Handle" and "Root" not in rig["sizes"]
    with pytest.raises(ValueError, match="Root .Models.spawn. or Handle"):
        PR.from_model(GATE, root="Base")
    with pytest.raises(ValueError, match="a group is named Handle"):
        PR.from_model(medit(["groups", "Handle"], {"size_studs": [1, 1, 1], "center": [0, 0, 0]}), root="Handle")
    assert any("its parent is a group's name" in p for p in PR.model_problems(medit(["joints", "Throw", "parent"], ["arm"])))
    assert PR.joints_hash(rig) != PR.joints_hash(PR.from_model(GATE))


def test_clips_built_on_other_joints_are_stale(tmp_path, capsys):
    import shutil
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    man = tmp_path / "Gate.manifest.json"
    man.write_text(json.dumps(GATE), encoding="utf-8")
    sp = tmp_path / "GateOpen.json"
    sp.write_text(json.dumps({"name": "GateOpen", "rig": "Gate", "loop": False, "priority": "Action", "fps": 30, "keys": [
        {"t": 0, "pose": {"arm": [0, 0, 0]}}, {"t": 1.0, "pose": {"arm": [0, 0, 60]}}]}), encoding="utf-8")
    out = str(tmp_path / "game")
    with pytest.raises(ValueError, match="is the prop Gate, not Fence"):
        PR.go(str(man), [str(sp)], out, name="Fence")
    assert PR.go(str(man), [str(sp)], out, name="Gate")["refused"] == []
    props = os.path.join(out, "gate.props.json")
    assert PR.stale(str(man), props) is None and PR.main(["stale", str(man), "--props", props]) == 0
    man.write_text(json.dumps(dict(GATE, build_id="another build, the same joints")), encoding="utf-8")
    assert PR.stale(str(man), props) is None                                   # a rebuild that changed no joint is not stale
    for path, value in ((["joints", "Swing", "axis"], [0, 0, -1]), (["joints", "Swing", "max"], 45),
                        (["joints", "Throw", "parent"], "main")):
        man.write_text(json.dumps(medit(path, value)), encoding="utf-8")
        assert "are not the ones its 1 clip(s) were built on" in PR.stale(str(man), props)
    capsys.readouterr()
    assert PR.main(["stale", str(man), "--props", props]) == 1
    assert "build the clips again" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    assert PR.main(["stale", str(man), "--props", str(tmp_path / "none.json")]) == 0
    tool = str(tmp_path / "tool")
    man.write_text(json.dumps(GATE), encoding="utf-8")
    assert PR.main(["go", str(man), str(sp), "--out", tool, "--tool"]) == 0
    top = [k for k in json.load(open(os.path.join(tool, "GateOpen.model.json")))["Children"] if k["ClassName"] == "Keyframe"][-1]["Children"]
    assert [p["Name"] for p in top] == ["Handle"] and PR.stale(str(man), os.path.join(tool, "gate.props.json")) is None


def test_the_builds_own_check_names_every_prop_whose_model_changed(tmp_path, capsys):
    import shutil
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    models, keep, game = tmp_path / "models", tmp_path / "props", tmp_path / "game"
    models.mkdir()
    sp = tmp_path / "GateOpen.json"
    sp.write_text(json.dumps({"name": "GateOpen", "rig": "Gate", "loop": False, "priority": "Action", "fps": 30, "keys": [
        {"t": 0, "pose": {"arm": [0, 0, 0]}}, {"t": 1.0, "pose": {"arm": [0, 0, 60]}}]}), encoding="utf-8")
    man = models / "Gate.manifest.json"
    man.write_text(json.dumps(GATE), encoding="utf-8")
    assert PR.stale_all(str(keep), str(models)) == []                           # nothing built yet
    assert PR.go(str(man), [str(sp)], str(game / "Gate"), keep=str(keep / "Gate"), name="Gate")["from_model"] is True
    chest = tmp_path / "Chest.prop.json"                                       # a prop typed as a file has no model to change
    chest.write_text(json.dumps(CHEST), encoding="utf-8")
    cs = tmp_path / "ChestOpen.json"
    cs.write_text(json.dumps(spec_of()), encoding="utf-8")
    assert PR.go(str(chest), [str(cs)], str(game / "Chest"), keep=str(keep / "Chest"))["from_model"] is False
    assert PR.stale_all(str(keep), str(models)) == [] and PR.main(["stale-all", str(keep), str(models)]) == 0
    man.write_text(json.dumps(medit(["joints", "Swing", "axis"], [0, 0, -1])), encoding="utf-8")
    bad = PR.stale_all(str(keep), str(models))
    assert len(bad) == 1 and bad[0].startswith("Gate: the model's joints are not the ones its 1 clip(s) were built on")
    capsys.readouterr()
    assert PR.main(["stale-all", str(keep), str(models)]) == 1
    assert "1 prop(s) carry clips built on other joints - Gate" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    os.remove(man)
    assert "a model that is no longer built" in PR.stale_all(str(keep), str(models))[0]
    man.write_text("{not json", encoding="utf-8")
    assert "cannot be checked against the model" in PR.stale_all(str(keep), str(models))[0]
    code = open(os.path.join(ROOT, "kit", "cmd", "anim.luau"), encoding="utf-8").read()
    assert "AnimCmd.propsStale()" in code and '"stale-all"' in code, "the animation build no longer runs the props' check"


def test_what_the_lifted_bans_allow_a_range_off_rest_and_a_hinge_past_a_half_turn():
    # (LIMITATIONS_FIXES_V3 Stage D: "lift arbitrary bans (non-root fixed parents, non-0-spanning ranges ...)")
    off = edit(["parts", "Lid", "hinge"], {"axis": [1, 0, 0], "min": 10, "max": 90})
    rig = PR.build(off)
    assert rig["limits"]["Lid"]["min"] == 10 and PR.check_clip(clip_of(lid=(10, 90)), rig) == []
    # a clip that holds the lid at rest (0, outside 10..90) is told so: the range is held, not the rest
    said = PR.check_clip(clip_of(lid=(0, 60)), rig)
    assert any(f["part"] == "Lid" and "turns to 0 deg; its hinge runs 10 to 90" in f["what"] for f in said)
    assert PR.build(edit(["parts", "Tray", "slide"], {"axis": [0, 0, -1], "min": 0.5, "max": 1.8}))["limits"]["Tray"]["min"] == 0.5
    two = edit(["parts", "Lid", "hinge"], {"axis": [1, 0, 0], "min": 0, "max": 720})
    assert PR.problems(two) == []


def test_a_hinge_past_a_half_turn_is_read_unwrapped_and_its_turn_track_held_to_its_frames():
    winch = {"name": "Winch", "root": "Base", "parts": {"Base": {"size": [4, 2, 3], "at": [0, 1, 0]},
             "Drum": {"size": [1, 1, 1], "at": [0, 2.5, 0], "parent": "Base", "pivot": [0, 2, 0],
                      "hinge": {"axis": [1, 0, 0], "min": 0, "max": 720}}}}
    rig = PR.build(winch)
    n = 61

    def spin(total, told=False):
        c = {"name": "WinchSpin", "rig": "Winch", "fps": 30, "times": [round(i / 30, 6) for i in range(n)], "events": [],
             "joints": {"Drum": {"frames": [quat((1, 0, 0), total * i / (n - 1)) + [0, 0, 0] for i in range(n)]}}}
        if told:
            c["joints"]["Drum"]["turn"] = [total * i / (n - 1) for i in range(n)]
        return c
    assert PR.check_clip(spin(720), rig) == []                                   # two whole turns, unwrapped
    said = PR.check_clip(spin(800), rig)
    assert len(said) == 1 and "turns to 800 deg; its hinge runs 0 to 720" in said[0]["what"]
    assert PR.check_clip(spin(720, told=True), rig) == []
    bad = spin(720, told=True)
    bad["joints"]["Drum"]["turn"][9] += 30                                       # the track lies about one frame
    said = PR.check_clip(bad, rig)
    assert len(said) == 1 and said[0]["frame"] == 9 and "its turn track" in said[0]["what"]
    bad = spin(720, told=True)
    bad["joints"]["Drum"]["turn"] = bad["joints"]["Drum"]["turn"][:5]
    assert "not one number of degrees a frame" in PR.check_clip(bad, rig)[0]["what"]
    # a half turn or more between two stored frames cannot be said: the engine would take the short way round
    fast = {"name": "WinchSpin", "rig": "Winch", "fps": 30, "times": [0, 1 / 30, 2 / 30], "events": [],
            "joints": {"Drum": {"frames": [quat((1, 0, 0), a) + [0, 0, 0] for a in (0, 200, 400)],
                                "turn": [0, 200, 400]}}}
    assert any("between two frames" in f["what"] for f in PR.check_clip(fast, rig))


def test_a_moving_part_on_a_fixed_part_hangs_on_it_in_the_rig_as_the_game_spawns_it():
    for host, joint in (("post", "post"), ("sign", "Plate")):        # a plain group; a group on a fixed joint
        rig = PR.from_model(medit(["joints", "Throw", "parent"], host))
        assert rig["joints"]["bolt"]["parent"] == host and rig["limits"][host] == {"kind": "fixed"}
        assert rig["joints"][host]["welded"] is True and rig["joints"][host]["joint"] == joint
        assert rig["joints"][host]["parent"] == "Root" and rig["order"].index(host) < rig["order"].index("bolt")
        W = C.world_frames(model_clip(), rig)
        assert np.allclose(W[0][host][:3, 3], GATE["groups"][host]["center"], atol=1e-6)
        assert np.allclose(W[0]["bolt"][:3, 3], [2.9, 4.2, 0.2], atol=1e-6)        # at rest where it was built
        assert np.allclose(W[-1]["bolt"][:3, 3], [3.2, 4.2, 0.2], atol=1e-6)       # slid 0.3 along X, the host still
        assert np.allclose(W[-1][host][:3, 3], GATE["groups"][host]["center"], atol=1e-6)
        keyed = model_clip()
        keyed["joints"][host] = {"frames": [quat((0, 0, 1), 10) + [0, 0, 0]] * 31}
        assert any(f["part"] == host and "fixed to its parent" in f["what"] for f in PR.check_clip(keyed, rig))
    # the gate's own rig (nothing hangs on a fixed part) is as it was: no fixed part is added for nothing
    assert set(PR.from_model(GATE)["sizes"]) == {"Root", "arm", "bolt"}
    assert not any("run in a loop" in p for p in PR.model_problems(                # a sign fixed on the moving bolt
        medit(["joints", "Plate"], dict(GATE["joints"]["Plate"], parent="bolt"))))
    loop = medit(["joints", "Throw", "parent"], "sign")
    loop["joints"]["Plate"]["parent"] = "bolt"                               # the bolt on the sign on the bolt
    assert any("run in a loop" in p for p in PR.model_problems(loop))


def test_one_number_poses_a_hinge_about_its_own_axis_and_turns_it_in_degrees_the_whole_way(tmp_path):
    import shutil
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    prop = {"name": "Winch", "root": "Base", "parts": {"Base": {"size": [4, 2, 3], "at": [0, 1, 0]},
            "Drum": {"size": [1, 1, 1], "at": [0, 2.5, 0], "parent": "Base", "pivot": [0, 2, 0],
                     "hinge": {"axis": [1, 1, 0], "min": 0, "max": 720}},
            "Flap": {"size": [4, 0.2, 1], "at": [0, 2.1, 1.0], "parent": "Base", "pivot": [0, 2, 1.5],
                     "hinge": {"axis": [1, 0, 0], "min": 10, "max": 90}},
            "Tray": {"size": [3, 0.3, 2], "at": [0, 1.2, 0], "parent": "Base", "pivot": [0, 1.2, 0],
                     "slide": {"axis": [0, 0, -1], "min": 0, "max": 1.8}}}}
    pf = tmp_path / "winch.prop.json"
    pf.write_text(json.dumps(prop), encoding="utf-8")

    def spec(name, drum, flap=(10, 80), extra=None):
        p = tmp_path / f"{name}.json"
        keys = [{"t": 0, "ease": "Linear", "pose": {"Drum": drum[0], "Flap": flap[0], "Tray": 0}},
                {"t": 1.0, "ease": "Linear", "pose": {"Drum": drum[1], "Flap": flap[1], "Tray": 1.2}}]
        for k, v in (extra or {}).items():
            keys[1]["pose"][k] = v
        p.write_text(json.dumps({"name": name, "rig": "Winch", "fps": 30, "keys": keys}), encoding="utf-8")
        return str(p)
    game, kept = str(tmp_path / "tree"), str(tmp_path / "kept")
    m = PR.go(str(pf), [spec("WinchSpin", (0, 720))], game, keep=kept)
    assert m["refused"] == [], m
    clip = json.load(open(os.path.join(kept, "WinchSpin.clip.json")))
    rig = json.load(open(os.path.join(kept, "winch.rig.json")))
    turn = clip["joints"]["Drum"]["turn"]
    assert turn[0] == 0 and abs(turn[15] - 360) < 1e-6 and abs(turn[-1] - 720) < 1e-6 and len(turn) == len(clip["times"])
    W = C.world_frames(clip, rig)
    ax = np.array([1, 1, 0]) / math.sqrt(2)
    R = W[7]["Drum"][:3, :3]                                                     # 168 degrees about the diagonal
    assert np.allclose(R @ ax, ax, atol=1e-6) and abs(math.degrees(math.acos((np.trace(R) - 1) / 2)) - 168) < 1e-4
    assert np.allclose(W[15]["Drum"][:3, :3], np.eye(3), atol=1e-6)            # a whole turn: back at rest
    assert np.allclose(W[-1]["Tray"][:3, 3] - W[0]["Tray"][:3, 3], [0, 0, -1.2], atol=1e-6)
    frames = [k for k in json.load(open(os.path.join(game, "WinchSpin.model.json")))["Children"] if k["ClassName"] == "Keyframe"]
    assert len(frames) == len(clip["times"])                                     # frame by frame: the engine's short way
    # under a half turn key to key: the keys only (the engine's own easing), the same degrees in the clip
    m = PR.go(str(pf), [spec("WinchNudge", (0, 90))], game, keep=kept)
    assert m["refused"] == []
    frames = [k for k in json.load(open(os.path.join(game, "WinchNudge.model.json")))["Children"] if k["ClassName"] == "Keyframe"]
    assert len(frames) == 2
    # past its range, and a part posed by a number that is no hinge or slide, are refused
    m = PR.go(str(pf), [spec("WinchOver", (0, 800))], game, keep=kept)
    assert "turns to 800 deg; its hinge runs 0 to 720" in m["refused"][0]["why"]
    m = PR.go(str(pf), [spec("WinchBase", (0, 90), extra={"Base": 5})], game, keep=kept)
    assert m["refused"] and "posed by one number" in m["refused"][0]["why"]


def test_review_d1_a_range_away_from_rest_read_where_it_is_and_a_host_without_a_place_refused():
    # (the stage's review, 2026-11-17: a hinge running 200 to 300 posed at 250 read -110 and was refused; a fixed
    # host with no centre raised a KeyError instead of saying so)
    far = edit(["parts", "Lid", "hinge"], {"axis": [1, 0, 0], "min": 200, "max": 300})
    rig = PR.build(far)
    assert PR.check_clip(clip_of(lid=(250, 280)), rig) == []
    said = PR.check_clip(clip_of(lid=(250, 320)), rig)
    assert any("turns to 320 deg; its hinge runs 200 to 300" in f["what"] for f in said)
    m = medit(["joints", "Throw", "parent"], "post")
    del m["groups"]["post"]["center"]
    assert any("no size_studs and center" in p for p in PR.model_problems(m))
    with pytest.raises(ValueError):
        PR.from_model(m)
