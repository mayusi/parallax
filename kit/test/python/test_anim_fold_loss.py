"""kit/anim/fold_loss.py - what a rig change loses (the owner's older list, AN-19 / AN-21): an R6 fold read against
its R15 source at the hands, the feet and the pelvis; what no R6 can keep (a bent elbow) is recorded, a limb pointing
the wrong way at the Hit is refused.
The folds here are the KIT'S OWN (kit/lib/anim.luau Anim.foldToR6), made once from `source()` below by
kit/selftest/anim/fold/fold.luau and kept beside it - the first cut of this test folded by hand, pinned a model of
the fold that was false, and passed."""
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
import clip as C                 # noqa: E402
import fold_loss as FL           # noqa: E402
import metrics as MT             # noqa: E402

R15, R6 = C.load_rig("r15"), C.load_rig("r6")
N, FPS = 31, 30
FIX = os.path.join(ROOT, "kit", "selftest", "anim", "fold")


def quat(axis, deg):
    a = math.radians(deg) / 2
    return [axis[0] * math.sin(a), axis[1] * math.sin(a), axis[2] * math.sin(a), math.cos(a)]


def blank(rig, name):
    return {"schema": 1, "name": name, "rig": rig["rig"], "fps": FPS, "loop": False, "priority": "Action",
            "times": [round(i / FPS, 6) for i in range(N)], "events": [{"name": "Hit", "t": 15 / FPS}],
            "joints": {p: {"frames": [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0] for _ in range(N)]} for p in rig["joints"]}}


def source(upper=0.0, elbow=0.0):
    """an R15 move: the right upper arm swings `upper` degrees ahead by the Hit, its elbow bending `elbow`"""
    src = blank(R15, "Made")
    for i in range(N):
        u = math.sin(math.pi * i / (N - 1))                  # 0 .. 1 at the Hit .. 0
        src["joints"]["RightUpperArm"]["frames"][i] = quat((1, 0, 0), upper * u) + [0.0, 0.0, 0.0]
        src["joints"]["RightLowerArm"]["frames"][i] = quat((1, 0, 0), elbow * u) + [0.0, 0.0, 0.0]
    return src


def fixture(name):
    with open(os.path.join(FIX, f"{name}.clip.json"), encoding="utf-8") as fh:
        a = json.load(fh)
    with open(os.path.join(FIX, f"{name}.r6.clip.json"), encoding="utf-8") as fh:
        return a, json.load(fh)


def turned(fold, part, axis, deg, frames=None):
    """the fold with one limb turned further (somebody changed the R6 clip after the fold)"""
    c = copy.deepcopy(fold)
    for i in (frames or range(N)):
        f = c["joints"][part]["frames"][i]
        R = C.quat_mat(quat(axis, deg)) @ C.quat_mat(f[:4])
        c["joints"][part]["frames"][i] = [float(v) for v in C.mat_quat(R)] + f[4:7]
    return c


def test_the_fixtures_are_this_tests_own_sources_folded_by_the_kit():
    for name, (u, e) in {"straight": (80, 0), "bent": (80, 90)}.items():
        a, b = fixture(name)
        want = source(u, e)
        for part, j in want["joints"].items():
            assert np.allclose(a["joints"][part]["frames"], j["frames"], atol=1e-9), (name, part)
        assert b["rig"] == "R6" and len(b["times"]) == N


def test_two_rest_poses_lose_nothing():
    r = FL.read(blank(R15, "Rest"), blank(R6, "Rest"))
    for limb, d in r["limbs"].items():
        assert d["residual"]["max"] < 1e-6, limb
    assert r["pelvis"]["max"] < 1e-6 and not r["problems"]


def test_the_kits_fold_of_a_straight_arm_keeps_the_hand():
    a, b = fixture("straight")
    r = FL.read(a, b)
    h = r["hits"][0]
    assert h["striker"] == "RightHand" and h["frame"] == 15
    assert h["residual"] < 0.05 and not r["problems"]


def test_the_kits_fold_of_a_bent_arm_loses_only_what_no_r6_can_keep():
    a, b = fixture("bent")
    r = FL.read(a, b)
    h = r["hits"][0]
    assert h["unavoidable"] > 0.3                             # the hand is nearer the shoulder than a block's end can be
    assert h["avoidable"] < 0.05                              # ... and the fold points the arm at it (its own rule)
    assert abs(h["residual"] - h["unavoidable"] - h["avoidable"]) < 2e-3
    assert not r["problems"]


def test_a_body_that_rolls_over_is_the_same_body_and_a_leg_is_measured_under_its_hip():
    # (nothing pinned the measure's axes: the whole file passed against the cut before)
    assert FL.lengths(R15, R6)["RightFoot"][1] == 2.0 and abs(FL.lengths(R15, R6)["RightHand"][1] - 1.5811) < 1e-3
    a, b = fixture("bent")
    upright = FL.read(a, b)["hits"][0]
    roll = quat((0, 0, 1), 85)
    src, fold = copy.deepcopy(a), copy.deepcopy(b)
    for i in range(N):
        for clip_, part in ((src, "LowerTorso"), (fold, "Torso")):
            f = clip_["joints"][part]["frames"][i]
            R = C.quat_mat(roll) @ C.quat_mat(f[:4])
            clip_["joints"][part]["frames"][i] = [float(v) for v in C.mat_quat(R)] + f[4:7]
    rolled = FL.read(src, fold)
    h = rolled["hits"][0]
    assert abs(h["avoidable"] - upright["avoidable"]) < 0.02 and abs(h["unavoidable"] - upright["unavoidable"]) < 0.02
    for limb in ("RightFoot", "LeftFoot"):                    # the legs ride with the pelvis on both rigs: no miss
        assert rolled["limbs"][limb]["residual"]["max"] < 0.05, limb
    assert not rolled["problems"]


def test_a_twist_about_the_arms_own_line_is_not_a_loss():
    # the source's upper arm twisted half round about its own length: its hand barely moves, and the fold (rest) is right
    src, fold = blank(R15, "Twist"), blank(R6, "Twist")
    line = FL._reach15(R15, C.fk(R15), "RightHand")
    line = line / np.linalg.norm(line)
    for i in range(N):
        src["joints"]["RightUpperArm"]["frames"][i] = quat(tuple(line), 180) + [0.0, 0.0, 0.0]
    r = FL.read(src, fold)
    assert r["limbs"]["RightHand"]["residual"]["max"] < 0.1 and not r["problems"]


def test_a_fold_changed_afterwards_so_the_striking_arm_points_away_is_refused():
    a, b = fixture("bent")
    bad = turned(b, "Right Arm", (0, 1, 0), 80)              # the arm swung 80 degrees round to the side
    r = FL.read(a, bad)
    h = r["hits"][0]
    assert h["avoidable"] > FL.REACH
    assert len(r["problems"]) == 1 and "the fold loses the strike" in r["problems"][0] and "frame 15" in r["problems"][0]
    # the same change away from the Hit only: reported over the move, not refused
    late = turned(b, "Right Arm", (0, 1, 0), 80, frames=range(26, N))
    r2 = FL.read(a, late)
    assert not r2["problems"] and r2["limbs"]["RightHand"]["avoidable"]["max"] > 0.2


def test_a_standing_foot_the_fold_moved_is_reported_not_refused():
    a, b = fixture("straight")
    r = FL.read(a, b)
    assert r["stands"]["LeftFoot"]["frames"] == N and r["stands"]["LeftFoot"]["over"] == 0     # (frame 0 is not special)
    moved = turned(b, "Left Leg", (1, 0, 0), 30)
    r2 = FL.read(a, moved)
    assert r2["stands"]["LeftFoot"]["over"] == N and r2["stands"]["LeftFoot"]["avoidable_max"] > FL.PLANT
    assert not r2["problems"]
    loop = copy.deepcopy(a)
    loop["loop"] = True
    assert FL.read(loop, moved)["stands"] == {}              # (a loop plays in place: its feet are not read as standing)


def test_the_pelvis_is_read_in_the_legs_ratio():
    src, fold = blank(R15, "Crouch"), blank(R6, "Crouch")
    k = FL.lengths(R15, R6)["RightFoot"]
    for i in range(N):
        src["joints"]["LowerTorso"]["frames"][i] = [0.0, 0.0, 0.0, 1.0, 0.0, -1.0, 0.0]
        fold["joints"]["Torso"]["frames"][i] = [0.0, 0.0, 0.0, 1.0, 0.0, -1.0 * k[1] / k[0], 0.0]
    assert FL.read(src, fold)["pelvis"]["max"] < 1e-3
    for i in range(N):
        fold["joints"]["Torso"]["frames"][i] = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    assert abs(FL.read(src, fold)["pelvis"]["max"] - k[1] / k[0]) < 1e-3


def test_pairs_that_cannot_be_compared_are_refused_and_numbers_that_are_not_finite_are_a_problem():
    a, b = fixture("straight")
    with pytest.raises(ValueError):
        FL.read(b, b)
    short = copy.deepcopy(b)
    short["times"] = short["times"][:-3]
    with pytest.raises(ValueError):
        FL.read(a, short)
    with pytest.raises(ValueError):
        FL.read([], b)
    nan = copy.deepcopy(b)
    nan["joints"]["Right Arm"]["frames"][15] = [float("nan")] * 4 + [0.0, 0.0, 0.0]
    assert any("not finite" in p for p in FL.read(a, nan)["problems"])
    odd = copy.deepcopy(a)
    odd["events"] = [{"name": "Hit", "t": float("inf")}, {"name": "Hit", "t": float("nan")}, {"name": "Hit", "t": "0.5"}, 7]
    assert FL.read(odd, b)["hits"] == []


def write(tmp_path, src, fold):
    a, b = tmp_path / "Made.clip.json", tmp_path / "Made.r6.clip.json"
    a.write_text(json.dumps(src), encoding="utf-8")
    b.write_text(json.dumps(fold), encoding="utf-8")
    return str(a), str(b)


def test_the_build_carries_the_reading_and_fails_a_fold_over_the_bar(tmp_path, capsys):
    a, b = fixture("bent")
    pa, pb = write(tmp_path, a, b)
    g, bad = FL.gate(b, pb)
    assert bad is None and g["hits"][0]["unavoidable"] > 0.3 and "problems" not in g
    MT.main([pb])
    capsys.readouterr()
    m = json.loads((tmp_path / "Made.r6.metrics.json").read_text(encoding="utf-8"))
    assert m["fold"]["hits"][0]["striker"] == "RightHand" and not any("the fold loses" in x for x in m["problems"])
    wrong = turned(b, "Right Arm", (0, 1, 0), 80)
    pa, pb = write(tmp_path, a, wrong)
    g, bad = FL.gate(wrong, pb)
    assert bad and "the fold loses the strike" in bad
    assert MT.main([pb]) == 1
    capsys.readouterr()
    m = json.loads((tmp_path / "Made.r6.metrics.json").read_text(encoding="utf-8"))
    assert any("the fold loses the strike" in x for x in m["problems"])


def test_the_gate_reads_only_a_fold_with_its_source_beside_it_and_nothing_in_it_breaks_a_build(tmp_path):
    a, b = fixture("straight")
    pa, pb = write(tmp_path, a, b)
    assert FL.gate(b, str(tmp_path / "Other.r6.clip.json")) == (None, None)          # no source beside it
    assert FL.gate(b, pa) == (None, None)                                            # not a fold's path
    assert FL.gate(a, pb) == (None, None)                                            # not an R6 clip
    assert FL.gate("nothing", pb) == (None, None)
    for text in ("[]", "{", json.dumps(b)):                  # a list, broken JSON, an R6-native clip beside its own copy
        with open(pa, "w", encoding="utf-8") as fh:
            fh.write(text)
        g, bad = FL.gate(b, pb)
        assert bad is None and (g is None or "error" in g)
    broken = copy.deepcopy(a)
    broken["joints"] = []
    with open(pa, "w", encoding="utf-8") as fh:
        json.dump(broken, fh)
    g, bad = FL.gate(b, pb)
    assert bad is None and "error" in g                      # (said in the reading; the build goes on)
    retimed = copy.deepcopy(b)
    retimed["times"] = retimed["times"][:-5]
    with open(pa, "w", encoding="utf-8") as fh:
        json.dump(a, fh)
    g, bad = FL.gate(retimed, pb)
    assert bad is None and "a fold keeps the frames" in g["error"]


def test_the_command_line_reads_one_and_lists_a_folder(tmp_path, capsys):
    a, b = fixture("bent")
    pa, pb = write(tmp_path, a, b)
    assert FL.main([pa, pb]) == 0
    assert "unavoidable" in json.loads(capsys.readouterr().out)["summary"]
    wrong = turned(b, "Right Arm", (0, 1, 0), 80)
    with open(pb, "w", encoding="utf-8") as fh:
        json.dump(wrong, fh)
    assert FL.main([pa, pb]) == 1
    capsys.readouterr()
    assert FL.main(["table", str(tmp_path)]) == 0
    rows = json.loads(capsys.readouterr().out)["rows"]
    assert len(rows) == 1 and rows[0]["problems"] == 1
    assert FL.main([pa, str(tmp_path / "none.json")]) == 1


def test_no_repair_is_offered():
    assert not hasattr(FL, "repair")
    text = open(os.path.join(ROOT, "kit", "anim", "derive.py"), encoding="utf-8").read()
    assert '"refold"' not in text
