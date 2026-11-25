"""kit/anim/drivers.py - a driver as an op of a `kit anim derive` recipe (the owner's method lists 2026-11-13: driver /
expression-driven animation), and what it refuses. The clip is a cut the owner loved, generated in memory (read only)."""
import copy
import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C            # noqa: E402
import drivers as DR        # noqa: E402
import strike as S          # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")


def kesa(**more):
    with open(LOVED, encoding="utf-8") as fh:
        return S.generate({**json.load(fh), **more})[0]


def R(c, j, i):
    return C.quat_mat(np.array(c["joints"][j]["frames"][i][:4], float))


def turn_deg(M):
    return float(np.degrees(np.arccos(np.clip((np.trace(M) - 1) / 2, -1, 1))))


def given(new, old, j, i):
    """the turn the driver put on top of the joint's own at frame i (a matrix, worked out without drivers.py)"""
    return R(new, j, i) @ R(old, j, i).T


def test_the_quaternion_product_is_the_matrix_product():
    rng = np.random.default_rng(1)
    for _ in range(20):
        a, b = (q / np.linalg.norm(q) for q in rng.normal(size=(2, 4)))
        assert np.allclose(C.quat_mat(DR._mul(a, b)), C.quat_mat(a) @ C.quat_mat(b), atol=1e-9)
        assert np.allclose(C.quat_mat(DR._power(a, 2.0)), C.quat_mat(DR._unit(a)) @ C.quat_mat(DR._unit(a)), atol=1e-9)
        assert np.allclose(C.quat_mat(DR._inv(a)), C.quat_mat(a).T, atol=1e-9)


def test_the_head_is_given_half_the_turn_the_torso_has_made_and_nothing_else_moves():
    c = kesa()
    d = copy.deepcopy(c)
    said = DR.op_drive(d, "Head", "Torso", 0.5)
    assert "Head follows Torso (0.5 of its turn" in said
    assert d["joints"]["Head"]["frames"][0] == c["joints"]["Head"]["frames"][0]
    checked = 0
    for i in range(1, len(c["times"])):
        torso = R(c, "Torso", i) @ R(c, "Torso", 0).T          # the torso's turn since the first frame, in its parent's axes
        g = given(d, c, "Head", i)
        assert abs(turn_deg(g) - 0.5 * turn_deg(torso)) < 0.05
        if turn_deg(torso) > 5:
            assert np.allclose(g @ g, torso, atol=2e-3)       # twice the half IS the torso's turn: the same axis, the same way
            checked += 1
    assert checked > 10
    for j in c["joints"]:
        if j != "Head":
            assert d["joints"][j] == c["joints"][j]
    assert d["sword"] == c["sword"] and d["events"] == c["events"] and d["times"] == c["times"]
    assert all(np.allclose(a[4:7], b[4:7]) for a, b in zip(d["joints"]["Head"]["frames"], c["joints"]["Head"]["frames"]))


def test_a_negative_weight_turns_the_other_way_and_a_delay_arrives_late():
    c = kesa()
    a, b, late = copy.deepcopy(c), copy.deepcopy(c), copy.deepcopy(c)
    DR.op_drive(a, "Head", "Torso", 0.5)
    DR.op_drive(b, "Head", "Torso", -0.5)
    k = 6
    DR.op_drive(late, "Head", "Torso", 0.5, delay=k / c["fps"])
    for i in range(1, len(c["times"])):
        assert np.allclose(given(a, c, "Head", i) @ given(b, c, "Head", i), np.eye(3), atol=1e-4)
        if i <= k:
            assert np.allclose(given(late, c, "Head", i), np.eye(3), atol=1e-5)   # the torso's turn has not arrived yet
        else:
            assert np.allclose(given(late, c, "Head", i), given(a, c, "Head", i - k), atol=1e-4)


def test_an_axis_takes_only_the_drivers_turn_about_it():
    c = kesa()
    d = copy.deepcopy(c)
    DR.op_drive(d, "Head", "Torso", 1.0, axis=[0, 2, 0])
    seen = 0
    for i in range(1, len(c["times"])):
        g = given(d, c, "Head", i)
        assert np.allclose(g @ np.array([0, 1.0, 0]), [0, 1, 0], atol=1e-4)      # a turn about Y leaves Y where it is
        torso = R(c, "Torso", i) @ R(c, "Torso", 0).T
        heading = np.degrees(np.arctan2(torso[0, 2], torso[2, 2]))
        if turn_deg(g) > 3 and abs(torso[1, 1]) > 0.9:          # (the torso nearly upright: its heading is its twist)
            assert abs(np.degrees(np.arctan2(g[0, 2], g[2, 2])) - heading) < 6
            seen += 1
    assert seen > 5


@pytest.mark.parametrize("joint", ["Right Arm", "Left Arm", "Torso"])
def test_a_driver_that_takes_a_hand_off_the_weapon_is_refused_and_changes_nothing(joint):
    c = kesa()
    before = copy.deepcopy(c)
    with pytest.raises(ValueError, match="takes a hand off the weapon"):
        DR.op_drive(c, joint, "Head" if joint == "Torso" else "Torso", 1.0)
    assert c == before


def test_a_loop_that_would_not_close_and_a_delay_on_a_stepped_clip_are_refused():
    c = kesa()
    c["loop"] = True
    before = copy.deepcopy(c)
    with pytest.raises(ValueError, match="LOOPS and Torso's turn leaves Head's last frame .* degrees off its first"):
        DR.op_drive(c, "Head", "Torso", 0.5)
    assert c == before
    closed = kesa()
    closed["loop"] = True
    closed["joints"]["Torso"]["frames"][-1] = list(closed["joints"]["Torso"]["frames"][0])
    assert "the last is turned 0.0 degrees" in DR.op_drive(closed, "Head", "Torso", 0.5)
    stepped = kesa(step={"on": 3, "beats": "all"})
    assert stepped.get("stepped")
    with pytest.raises(ValueError, match="STEPPED"):
        DR.op_drive(stepped, "Head", "Torso", 0.5, delay=0.05)
    held = copy.deepcopy(stepped)
    DR.op_drive(held, "Head", "Torso", 0.5)                    # with it, not late: a held torso holds the head
    same = [i for i in range(1, len(stepped["times"])) if stepped["joints"]["Torso"]["frames"][i] == stepped["joints"]["Torso"]["frames"][i - 1]
            and stepped["joints"]["Head"]["frames"][i] == stepped["joints"]["Head"]["frames"][i - 1]]
    assert len(same) > 5 and all(held["joints"]["Head"]["frames"][i] == held["joints"]["Head"]["frames"][i - 1] for i in same)


def yaw(deg):
    a = np.radians(deg) / 2
    return np.array([0.0, np.sin(a), 0.0, np.cos(a)])


def bare(n=61, torso=lambda u: yaw(300 * u), first=None):
    """a clip with no weapon: the torso turned by a rule (on top of `first`), the head still"""
    first = np.array([0.0, 0.0, 0.0, 1.0]) if first is None else first
    T = [[*DR._norm(DR._mul(torso(i / (n - 1)), first)), 0, 0, 0] for i in range(n)]
    return {"name": "Bare", "rig": "R6", "fps": 60, "times": [i / 60 for i in range(n)], "events": [],
            "joints": {"Torso": {"frames": T}, "Head": {"frames": [[0, 0, 0, 1, 0, 0, 0] for _ in range(n)]}}}


def test_a_driver_that_turns_past_half_a_turn_is_followed_all_the_way_round_with_no_jump():
    c = bare()
    said = DR.op_drive(c, "Head", "Torso", 0.5)
    H = [C.quat_mat(np.array(f[:4])) for f in c["joints"]["Head"]["frames"]]
    steps = [turn_deg(H[i] @ H[i - 1].T) for i in range(1, len(H))]
    assert max(steps) < 3.0 and abs(steps[30] - 2.5) < 0.05     # 300 degrees over 60 frames, half of it: 2.5 a frame, every frame
    assert np.allclose(H[-1], C.quat_mat(yaw(150)), atol=1e-5) and "at most 150.0 degrees added" in said
    spin = bare(torso=lambda u: yaw(360 * u))
    spin["loop"] = True                                         # the torso closes; half of a whole turn does not
    with pytest.raises(ValueError, match="180 degrees off its first"):
        DR.op_drive(spin, "Head", "Torso", 0.5)
    assert "the last is turned 0.0 degrees" in DR.op_drive(spin, "Head", "Torso", 1.0)
    with pytest.raises(ValueError, match="LOOPS: a delayed driver"):
        DR.op_drive(spin, "Head", "Torso", 1.0, delay=0.05)


def test_the_drivers_turn_is_read_in_its_parents_axes_whatever_its_first_pose():
    bow = np.array([np.sin(np.pi / 4), 0.0, 0.0, np.cos(np.pi / 4)])       # the torso starts bowed 90 degrees forward
    c = bare(torso=lambda u: yaw(40 * u), first=bow)
    d = copy.deepcopy(c)
    DR.op_drive(d, "Head", "Torso", 1.0)
    assert np.allclose(C.quat_mat(np.array(d["joints"]["Head"]["frames"][-1][:4])), C.quat_mat(yaw(40)), atol=1e-5)   # a YAW, not a roll
    e = copy.deepcopy(c)
    assert "at most 40.0 degrees added" in DR.op_drive(e, "Head", "Torso", 1.0, axis=[0, 1, 0])
    f = copy.deepcopy(c)
    assert "at most 0.0 degrees added" in DR.op_drive(f, "Head", "Torso", 1.0, axis=[1, 0, 0])


def test_a_hand_that_lets_go_late_is_still_held_to_the_weapon_before_and_a_short_track_is_refused():
    c = kesa()
    n = len(c["times"])
    turn = np.array([0.0, 0.0, np.sin(np.radians(30)), np.cos(np.radians(30))])
    for i in range(n - 6, n):                                   # a one-hand follow-through: the left hand leaves the hilt
        f = c["joints"]["Left Arm"]["frames"][i]
        c["joints"]["Left Arm"]["frames"][i] = [*DR._norm(DR._mul(turn, np.array(f[:4]))), *f[4:7]]
    before = copy.deepcopy(c)
    with pytest.raises(ValueError, match="takes a hand off the weapon .LeftHand"):
        DR.op_drive(c, "Left Arm", "Head", 1.0)
    assert c == before
    short = kesa()
    short["joints"]["Torso"]["frames"] = short["joints"]["Torso"]["frames"][:30]
    with pytest.raises(ValueError, match="Torso carries 30 frames"):
        DR.op_drive(short, "Head", "Torso", 0.5)
    slow = kesa()
    slow.pop("fps", None)                                       # the delay is in the clip's own times, whatever fps says
    k = 6
    late, now = copy.deepcopy(slow), copy.deepcopy(slow)
    DR.op_drive(late, "Head", "Torso", 0.5, delay=k * slow["times"][1])
    DR.op_drive(now, "Head", "Torso", 0.5)
    assert np.allclose(given(late, slow, "Head", 20), given(now, slow, "Head", 20 - k), atol=1e-4)


@pytest.mark.parametrize("kw, why", [
    (dict(joint="Head", by="Head"), "cannot be driven by itself"),
    (dict(joint="Tail", by="Torso"), "`joint` is one of the clip's joints"),
    (dict(joint="Head", by="Wing"), "`by` is one of the clip's joints"),
    (dict(joint="Head", by="Torso", weight=0), "not 0, up to 2"),
    (dict(joint="Head", by="Torso", weight=2.5), "not 0, up to 2"),
    (dict(joint="Head", by="Torso", weight=True), "not 0, up to 2"),
    (dict(joint="Head", by="Torso", delay=-0.1), "delay is a time in seconds inside the clip"),
    (dict(joint="Head", by="Torso", delay=99), "delay is a time in seconds inside the clip"),
    (dict(joint="Head", by="Torso", axis=[0, 0, 0]), "axis is a direction"),
    (dict(joint="Head", by="Torso", axis="y"), "axis is a direction"),
])
def test_a_driver_that_cannot_be_what_was_asked_is_refused(kw, why):
    c = kesa()
    before = copy.deepcopy(c)
    with pytest.raises(ValueError, match=why):
        DR.op_drive(c, **kw)
    assert c == before


def test_it_is_an_op_of_a_derive_recipe(tmp_path, monkeypatch):
    import derive as D
    src = tmp_path / "Base.clip.json"
    src.write_text(json.dumps(kesa()), encoding="utf-8")
    monkeypatch.setattr(D, "load_clip", lambda name: json.load(open(str(src), encoding="utf-8")))
    out = D.derive({"name": "Driven", "from": "Base", "ops": [{"op": "drive", "joint": "Head", "by": "Torso", "weight": 0.5}]})
    clip = out[0] if isinstance(out, tuple) else out
    want = kesa()
    DR.op_drive(want, "Head", "Torso", 0.5)
    assert clip["name"] == "Driven" and clip["joints"]["Head"]["frames"] == want["joints"]["Head"]["frames"]
    for bad, why in (({"op": "drive", "joint": "Head"}, "by"), ({"op": "drive", "joint": "Head", "by": "Head"}, "by itself"),
                     ({"op": "drive", "joint": "Right Arm", "by": "Torso", "weight": 1}, "hand off the weapon")):
        with pytest.raises((ValueError, KeyError), match=why):
            D.derive({"name": "Bad", "from": "Base", "ops": [bad]})
