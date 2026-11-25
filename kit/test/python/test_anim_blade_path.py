"""kit/anim/blade_path.py - A PATH DRAWN FOR THE BLADE (the owner's method lists 2026-11-13: motion path animation): a
move states the points its blade tip passes through, and the build's motion gates (kit/anim/metrics.py) fail a clip
whose tip misses one. The clip is a cut the owner loved, generated in memory (read only)."""
import copy
import json
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import blade_path as BP     # noqa: E402
import metrics as MT        # noqa: E402
import strike as S          # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")


def move():
    with open(LOVED, encoding="utf-8") as fh:
        return json.load(fh)


def kesa(m=None):
    return S.generate(copy.deepcopy(m or move()))[0]


def lifted():
    """the move with the grip of two keys raised one stud: the blade leaves the line drawn for it"""
    m = move()
    for k in m["keys"][2:4]:
        k["grip"] = [k["grip"][0], k["grip"][1] + 1.0, k["grip"][2]]
    return m


def test_a_clip_passes_through_points_taken_off_its_own_path():
    c = kesa()
    path = BP.draw(c, 0.1)
    assert len(path["points"]) == 10 and path["tol"] == BP.TOL and path["points"][0]["t"] == 0.0
    r = BP.read(c, path)
    assert r["missed"] == [] and max(x["studs"] for x in r["rows"]) == 0.0
    assert BP.words(r, "Kesa").startswith("the blade of Kesa passes through the 10 point(s) drawn for it")


def test_a_blade_pulled_off_the_drawn_line_is_named_with_its_point():
    path = BP.draw(kesa(), 0.1)
    r = BP.read(kesa(lifted()), path)
    assert 1 <= len(r["missed"]) <= 3 and 5 in [x["point"] for x in r["missed"]]
    worst = max(r["rows"], key=lambda x: x["studs"])
    assert worst["point"] == 5 and 0.9 < worst["studs"] < 1.2 and not worst["ok"]
    w = BP.words(r, "Kesa")
    assert w.startswith(f"the blade of Kesa MISSES {len(r['missed'])} of the 10 point(s) drawn for it - point ")
    assert "(0.5 allowed), at its moment" in w
    turned = move()
    turned["keys"][2]["yaw"] = float(turned["keys"][2].get("yaw", 0.0)) + 15.0
    assert BP.read(kesa(turned), path)["missed"] == []        # a turn of the body barely moves the blade: inside 0.5


def test_points_without_a_time_are_passed_in_order():
    c = kesa()
    pts = BP.draw(c, 0.1)["points"][2:7]
    free = {"points": [{"tip": p["tip"]} for p in pts]}
    r = BP.read(c, free)
    assert r["missed"] == [] and [x["at_s"] for x in r["rows"]] == sorted(x["at_s"] for x in r["rows"])
    assert all(x["studs"] <= 0.05 for x in r["rows"])
    back = {"points": [{"tip": p["tip"]} for p in pts[::-1]]}  # the same points the other way round: not this cut
    assert len(BP.read(c, back)["missed"]) >= 3


def test_a_timed_point_is_passed_at_its_own_moment():
    c = kesa()
    p = BP.draw(c, 0.1)["points"][4]
    assert BP.read(c, {"points": [p]})["missed"] == []
    late = {"points": [dict(p, t=p["t"] + 0.2)]}              # the right place at the wrong time
    r = BP.read(c, late)
    assert len(r["missed"]) == 1 and "at its moment 0.60 s" in BP.words(r, "Kesa")
    with pytest.raises(ValueError, match="1 at most"):       # a "path" 50 studs wide holds nothing
        BP.read(c, {"tol": 50.0, "points": [p]})
    assert "0.5 studs allowed" in BP.words(BP.read(c, {"points": [p]}), "Kesa")


def test_a_stepped_build_is_read_on_its_smooth_motion():
    path = BP.draw(kesa(), 0.1)
    stepped = move()
    stepped["step"] = {"on": 3, "beats": "all"}
    c = kesa(stepped)
    assert c.get("stepped") and BP.read(c, path)["missed"] == []


@pytest.mark.parametrize("spec, why", [
    ({}, "a blade_path is"),
    ({"points": []}, "a blade_path is"),
    ({"points": [{"tip": [0, 0]}]}, "point 1 of the blade_path has no tip"),
    ({"points": [{"tip": [0, 0, "x"]}]}, "point 1 of the blade_path has no tip"),
    ({"points": [{"tip": [0, 0, 0], "t": -1}]}, "its t is seconds"),
    ({"points": [{"tip": [0, 0, 0], "t": 0.5}, {"tip": [0, 0, 0], "t": 0.2}]}, "the points are in order"),
    ({"tol": 0, "points": [{"tip": [0, 0, 0]}]}, "tol is a positive number"),
    ({"tol": float("inf"), "points": [{"tip": [0, 0, 0]}]}, "tol is a positive number"),
    ({"points": [{"tip": [0, 0, 0], "t": float("nan")}]}, "its t is seconds"),
    ({"points": [{"tip": [0, float("nan"), 0]}]}, "has no tip"),
    ("a line", "a blade_path is"),
])
def test_a_path_that_is_not_one_is_refused(spec, why):
    with pytest.raises(ValueError, match=why):
        BP.read(kesa(), spec)


def write(tmp_path, name, clip, mv):
    mp = tmp_path / f"{name}.move.json"
    mp.write_text(json.dumps(mv), encoding="utf-8")
    clip = dict(clip, name=name, source={"kind": "move", "file": str(mp)})
    cp = tmp_path / f"{name}.clip.json"
    cp.write_text(json.dumps(clip), encoding="utf-8")
    return str(cp)


def test_the_builds_motion_gates_hold_a_clip_to_the_path_its_move_draws(tmp_path, capsys):
    path = BP.draw(kesa(), 0.1)
    good = write(tmp_path, "OnLine", kesa(), dict(move(), blade_path=path))
    off = write(tmp_path, "OffLine", kesa(lifted()), dict(lifted(), blade_path=path))
    none = write(tmp_path, "NoPath", kesa(lifted()), lifted())
    broken = write(tmp_path, "Broken", kesa(), dict(move(), blade_path={"points": [{"tip": [0, 0]}]}))
    assert MT.main([good]) == 0 and MT.main([none]) == 0      # a move that draws no path is held to nothing
    assert len(json.load(open(good[:-len(".clip.json")] + ".metrics.json"))["blade_path"]["rows"]) == 10
    assert "blade_path" not in json.load(open(none[:-len(".clip.json")] + ".metrics.json"))
    capsys.readouterr()
    assert MT.main([off]) == 1
    v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "the blade of OffLine MISSES" in v["summary"] and "never widen tol to pass" in v["next_action"]
    assert MT.main([broken]) == 1                             # a path that cannot be read is a problem, never a pass
    assert "cannot be held (point 1 of the blade_path has no tip" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]


def test_the_command_reads_a_path_from_the_move_given(tmp_path, capsys):
    path = BP.draw(kesa(), 0.1)
    cp = tmp_path / "c.clip.json"
    cp.write_text(json.dumps(kesa(lifted())), encoding="utf-8")
    mp = tmp_path / "m.move.json"
    mp.write_text(json.dumps(dict(move(), blade_path=path)), encoding="utf-8")
    assert BP.main([str(cp), "--move", str(mp)]) == 1
    assert "MISSES" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    assert BP.main([str(cp)]) == 0                            # (its own source draws none)
    assert "no path is drawn" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    assert BP.main(["draw", str(cp), "--every", "0.2"]) == 0
    assert len(json.loads(capsys.readouterr().out.strip().splitlines()[-1])["blade_path"]["points"]) == 6
    bad = tmp_path / "x.json"
    bad.write_text("{not json")
    assert BP.main([str(bad)]) == 1
    assert "could not be read" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    bare = kesa()
    bare.pop("sword")
    assert BP.gate(dict(bare, rig="R15")) == (None, None)
    with pytest.raises(ValueError, match="no blade tip"):
        BP.read(bare, path)


# ---- what the stage's review found (2026-11-14) ----
def test_a_point_timed_past_the_clips_end_is_a_miss():
    c = kesa()
    end = BP.draw(c, 0.1)["points"][-1]
    r = BP.read(c, {"points": [dict(end, t=5.0)]})
    assert len(r["missed"]) == 1 and "is past the clip's end (0.85 s)" in BP.words(r, "Kesa")
    half = move()
    for k in half["keys"]:
        k["t"] = round(float(k["t"]) / 2.0, 4)               # the move made twice as fast: its late points are never reached
    assert len(BP.read(kesa(half), BP.draw(c, 0.1))["missed"]) >= 4


def test_a_timed_point_cannot_be_passed_before_the_point_ahead_of_it():
    c = kesa()
    p = BP.draw(c, 0.1)["points"]
    r = BP.read(c, {"points": [{"tip": p[8]["tip"]}, dict(p[2])]})       # an untimed point met late, then one timed early
    assert [x["ok"] for x in r["rows"]] == [True, False] and "lies before point 1 was passed" in BP.words(r, "Kesa")


def test_one_pass_does_not_count_for_two_points():
    c = kesa()
    p = BP.draw(c, 0.1)["points"][4]["tip"]
    r = BP.read(c, {"tol": 0.05, "points": [{"tip": p}, {"tip": p}]})    # drawn through one spot twice; the cut crosses it once
    assert [x["ok"] for x in r["rows"]] == [True, False]


def test_a_clip_built_from_another_clip_is_held_to_its_base_moves_path(tmp_path, capsys):
    path = BP.draw(kesa(), 0.1)
    (tmp_path / "Base.move.json").write_text(json.dumps(dict(move(), blade_path=path)), encoding="utf-8")
    (tmp_path / "BaseFeel.feel.json").write_text(json.dumps({"from": "Base", "snap": 1.0}), encoding="utf-8")
    off = dict(kesa(lifted()), name="BaseFeel", source={"kind": "feel", "file": str(tmp_path / "BaseFeel.feel.json"), "from": "Base"})
    held, problem = BP.gate(off)
    assert problem and "the blade of BaseFeel MISSES" in problem
    on = dict(kesa(), name="BaseFeel", source={"kind": "feel", "file": str(tmp_path / "BaseFeel.feel.json")})   # (from: in its file)
    held, problem = BP.gate(on)
    assert problem is None and len(held["rows"]) == 10


# ---------------------------------------------------------------- a path drawn for a hand or a foot (2026-11-15)
def test_a_hand_or_a_foot_passes_through_points_taken_off_its_own_path():
    c = kesa()
    for of in BP.EFFECTORS:
        path = BP.draw(c, 0.1, of)
        assert set(path["points"][0]) == {"t", "at"} and len(path["points"]) == 10
        r = BP.read(c, path, of)
        assert r["missed"] == [] and max(x["studs"] for x in r["rows"]) == 0.0
    assert BP.words(BP.read(c, BP.draw(c, 0.1, "LeftFoot"), "LeftFoot"), "Kesa", "LeftFoot").startswith(
        "the left foot of Kesa passes through the 10 point(s) drawn for it")


def test_a_hand_pulled_off_its_drawn_line_is_named():
    path = BP.draw(kesa(), 0.1, "RightHand")
    r = BP.read(kesa(lifted()), path, "RightHand")           # the grip of two keys raised one stud: the hand goes with it
    worst = max(r["rows"], key=lambda x: x["studs"])
    assert r["missed"] and 0.8 < worst["studs"] < 1.3 and not worst["ok"]
    w = BP.words(r, "Kesa", "RightHand")
    assert w.startswith(f"the right hand of Kesa MISSES {len(r['missed'])} of the 10 point(s) drawn for it - point ")
    assert ": it comes no nearer than " in w and "the tip" not in w
    # the feet did not move with the grip: their paths still hold
    assert BP.read(kesa(lifted()), BP.draw(kesa(), 0.1, "LeftFoot"), "LeftFoot")["missed"] == []


def test_a_foots_path_is_where_the_world_sees_it_with_the_clips_travel():
    c = kesa()
    n = len(c["times"])
    stepped = dict(c, root=[[0, 0, 0, 1, 0, 0, -2.0 * i / (n - 1)] for i in range(n)])      # a 2-stud step forward
    path = BP.draw(stepped, 0.1, "RightFoot")
    assert BP.read(stepped, path, "RightFoot")["missed"] == []
    r = BP.read(c, path, "RightFoot")                        # the same poses standing still: the foot never gets there
    assert r["missed"] and r["rows"][-1]["studs"] > 1.4
    assert abs(path["points"][-1]["at"][2] - BP.draw(c, 0.1, "RightFoot")["points"][-1]["at"][2] + 2.0) < 1e-3


@pytest.mark.parametrize("paths, why", [
    ({"Tail": {"points": [{"at": [0, 0, 0]}]}}, "is no hand or foot of the R6 body"),
    ({"RightFoot": {"points": [{"tip": [0, 0, 0]}]}}, "point 1 of the path of RightFoot has no at"),
    ({"RightFoot": {"points": []}}, "a path of RightFoot is"),
    ({"RightFoot": {"tol": 3, "points": [{"at": [0, 0, 0]}]}}, "tol is a positive number of studs, 1 at most"),
    ({}, '"paths" drawn in'),
    (["RightFoot"], '"paths" drawn in'),
])
def test_paths_that_are_not_paths_are_a_problem_never_a_pass(paths, why):
    out, problem = BP.gate_paths(kesa(), {"paths": paths})
    assert problem is not None and why in problem and out is not None


def test_the_builds_motion_gates_hold_a_clip_to_the_paths_its_move_draws(tmp_path, capsys):
    c = kesa()
    drawn = {"RightHand": BP.draw(c, 0.1, "RightHand"), "LeftFoot": BP.draw(c, 0.1, "LeftFoot")}
    mp = tmp_path / "Foot.move.json"
    mp.write_text(json.dumps(dict(move(), paths=drawn)), encoding="utf-8")
    src = {"kind": "move", "file": str(mp)}
    held, problem = BP.gate_paths(dict(c, name="Foot", source=src))
    assert problem is None and sorted(held) == ["LeftFoot", "RightHand"] and len(held["LeftFoot"]["rows"]) == 10
    held, problem = BP.gate_paths(dict(kesa(lifted()), name="Foot", source=src))
    assert "the right hand of Foot MISSES" in problem and "bring the right hand back onto the drawn line" in problem
    assert "left foot" not in problem and "never widen tol to pass" in problem
    # a clip built from it (a feel pass) is held to its base move's paths; one whose source draws none, to nothing
    feel = {"kind": "feel", "file": str(tmp_path / "FootFeel.feel.json"), "from": "Foot"}
    assert "the right hand of FootFeel MISSES" in BP.gate_paths(dict(kesa(lifted()), name="FootFeel", source=feel))[1]
    assert BP.gate_paths(dict(c, name="Bare", source={"kind": "move", "file": LOVED})) == (None, None)
    assert BP.gate_paths(dict(c, rig="R15", source=src)) == (None, None)
    # the whole gate (kit/anim/metrics.py) and the command
    good, off = tmp_path / "good.clip.json", tmp_path / "off.clip.json"
    good.write_text(json.dumps(dict(c, name="Foot", source=src)), encoding="utf-8")
    off.write_text(json.dumps(dict(kesa(lifted()), name="Foot", source=src)), encoding="utf-8")
    capsys.readouterr()
    assert MT.main([str(good)]) == 0
    assert MT.main([str(off)]) == 1
    assert "the right hand of Foot MISSES" in capsys.readouterr().out
    assert BP.main([str(good)]) == 0
    assert "passes through the path(s) drawn for LeftFoot, RightHand" in capsys.readouterr().out
    assert BP.main([str(off)]) == 1
    assert BP.main(["draw", str(good), "--of", "RightFoot"]) == 0
    assert '"paths": {"RightFoot"' in capsys.readouterr().out.replace("\\", "")


def test_the_command_says_the_blade_and_the_limbs_together(tmp_path, capsys):
    """the one review, 2026-11-15: with a blade_path AND paths the command dropped the limbs' result on a pass and hid
    the blade's miss behind a hand's"""
    c = kesa()
    m = dict(move(), blade_path=BP.draw(c, 0.1), paths={"RightHand": BP.draw(c, 0.1, "RightHand")})
    mp = tmp_path / "Both.move.json"
    mp.write_text(json.dumps(m), encoding="utf-8")
    good, off = tmp_path / "good.clip.json", tmp_path / "off.clip.json"
    good.write_text(json.dumps(dict(c, name="Both")), encoding="utf-8")
    off.write_text(json.dumps(dict(kesa(lifted()), name="Both")), encoding="utf-8")
    capsys.readouterr()
    assert BP.main([str(good), "--move", str(mp)]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "the blade of Both passes through" in out["summary"] and "path(s) drawn for RightHand" in out["summary"]
    assert len(out["rows"]) == 10 and len(out["paths"]["RightHand"]["rows"]) == 10
    assert BP.main([str(off), "--move", str(mp)]) == 1
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "the blade of Both MISSES" in out["summary"] and "the right hand of Both MISSES" in out["summary"]
    # a wrong name with a wrong shape: the name is what is said
    _held, problem = BP.gate_paths(c, {"paths": {"Tail": {"points": "x"}}})
    assert "is no hand or foot of the R6 body" in problem


def test_a_turning_clip_carries_its_turn_into_a_foots_path():
    c = kesa()
    h = math.sin(math.radians(45) / 2), math.cos(math.radians(45) / 2)
    turned = dict(c, root=[[0, h[0], 0, h[1], 0, 0, 0] for _ in c["times"]])      # the whole clip turned 45 degrees
    a, b = BP.draw(c, 0.1, "RightFoot")["points"][0]["at"], BP.draw(turned, 0.1, "RightFoot")["points"][0]["at"]
    assert abs(a[1] - b[1]) < 1e-6 and abs(math.hypot(a[0], a[2]) - math.hypot(b[0], b[2])) < 1e-3
    assert math.hypot(a[0] - b[0], a[2] - b[2]) > 0.3
    assert BP.read(turned, BP.draw(turned, 0.1, "RightFoot"), "RightFoot")["missed"] == []

