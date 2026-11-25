"""kit/anim/collide_repair.py - what passes through the body is MOVED CLEAR, inside bounds, or refused by name (the
owner's limitations list 2026-11-15, A-R05: the check was built, the repair was not). On a cut the owner loved
(generated in memory, read only), broken on purpose the way kit/test/python/test_anim_collide.py breaks it."""
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
sys.path.insert(0, HERE)
import clip as C                 # noqa: E402
import collide as K              # noqa: E402
import collide_repair as R       # noqa: E402
import grip as GR                # noqa: E402
import in_hand as IH             # noqa: E402
import test_anim_collide as T    # noqa: E402


@pytest.fixture(scope="module")
def kesa():
    return T.made("loved", "Katana1Kesa")


def one_handed(clip):
    """the cut with its left arm let go: the right hand alone holds the weapon"""
    c = copy.deepcopy(clip)
    for i in range(len(c["times"])):
        c["joints"]["Left Arm"]["frames"][i] = [0, 0, 0, 1, 0, 0, 0]
    return c


def blade_toward_chest(clip, share, frames=T.BLOCK):
    """a one-handed blade turned `share` of the way toward the chest on some frames (it goes into its own forearm)"""
    c = one_handed(clip)
    for i in frames:
        g = np.array(c["sword"]["grip_path"][i], float)
        d = np.array(c["sword"]["tip"][i], float) - g
        to = T.torso_at(c, i) - g
        v = d / np.linalg.norm(d) * (1 - share) + to / np.linalg.norm(to) * share
        c["sword"]["tip"][i] = (g + c["sword"]["length"] * v / np.linalg.norm(v)).tolist()
    return c


def left_arm_into_chest(clip, deg=65, frames=T.BLOCK):
    """the cut, unarmed, with its LEFT arm swung across into the chest on some frames"""
    c = copy.deepcopy(clip)
    c.pop("sword", None)
    h = math.radians(deg) / 2
    for i in frames:
        c["joints"]["Left Arm"]["frames"][i] = [0, 0, math.sin(h), math.cos(h), 0, 0, 0]
        c["joints"]["Right Arm"]["frames"][i] = [0, 0, 0, 1, 0, 0, 0]
    return c


def legs_crossed(clip, deg=-40, frames=T.BLOCK):
    c = copy.deepcopy(clip)
    h = math.radians(deg) / 2
    for i in frames:
        c["joints"]["Right Leg"]["frames"][i] = [0, 0, math.sin(h), math.cos(h), 0, 0, 0]
    return c


def turned(a, b):
    """degrees between two joint frames' turns"""
    return C.quat_angle(np.array(a[:4], float), np.array(b[:4], float))


def test_a_clip_with_nothing_through_the_body_is_given_back_untouched(kesa):
    fixed, done = R.repair(kesa)
    assert fixed is kesa and done == [] and R.words(done) == "nothing passes through the body: nothing moved"


def test_a_hand_in_the_chest_is_moved_out_by_the_least_that_does_it(kesa):
    bad = T.arm_into_chest(kesa, -65)
    before = copy.deepcopy(bad)
    assert [k for k, _ in K.over(K.read(bad))] == ["hand_torso"]
    fixed, done = R.repair(bad)
    assert bad == before                                         # the clip given is never changed
    r = K.read(fixed)
    assert K.over(r) == [] and r["worst"]["hand_torso"]["depth"] < K.BARS["hand_torso"]
    assert [d["what"] for d in done] == ["Right Arm"] and done[0]["out_of"] == "Torso" and done[0]["was"] > 0.4
    assert 0 < done[0]["deg"] <= R.MAX_DEG and done[0]["slide"] <= R.MAX_SLIDE
    f = done[0]["frame"]
    # eased: the fault's frame moved the most, frames past EASE not at all, no other joint touched
    A, B = bad["joints"]["Right Arm"]["frames"], fixed["joints"]["Right Arm"]["frames"]
    assert turned(A[f], B[f]) == pytest.approx(done[0]["deg"], abs=0.01)
    assert 0 < turned(A[f + 3], B[f + 3]) < turned(A[f], B[f])
    for k in range(len(A)):
        if abs(k - f) > R.EASE:
            assert A[k] == pytest.approx(B[k], abs=1e-9)
    for j in bad["joints"]:
        if j != "Right Arm":
            assert bad["joints"][j] == fixed["joints"][j]
    assert R.words(done).startswith("the Right Arm turned ")


def test_a_foot_in_the_other_leg_is_moved_out(kesa):
    bad = legs_crossed(kesa)
    assert [k for k, _ in K.over(K.read(bad))] == ["foot"]
    fixed, done = R.repair(bad)
    assert K.over(K.read(fixed)) == [] and {d["what"] for d in done} == {"Right Leg"}
    assert all(d["slide"] == 0.0 for d in done)                  # a leg is turned, never slid
    for a, b in zip(bad["joints"]["Right Leg"]["frames"], fixed["joints"]["Right Leg"]["frames"]):
        assert a[4:7] == pytest.approx(b[4:7], abs=1e-9)


def test_a_one_handed_blade_is_turned_about_its_grip_and_the_hand_stays_on_it(kesa):
    bad = blade_toward_chest(kesa, 0.455)
    GR.add_grip(bad)
    r = K.read(bad)
    assert [k for k, _ in K.over(r)] == ["weapon"] and r["worst"]["weapon"]["b"] == "Right Arm"   # into its own forearm
    fixed, done = R.repair(bad)
    assert K.over(K.read(fixed)) == [] and {d["what"] for d in done} == {"weapon"}
    assert all(0 < d["deg"] <= R.BLADE_DEG for d in done)
    sw0, sw1 = bad["sword"], fixed["sword"]
    for i in range(len(sw1["tip"])):                             # the blade keeps its length
        g0, g1 = np.array(sw0["grip_path"][i]), np.array(sw1["grip_path"][i])
        assert np.linalg.norm(np.array(sw1["tip"][i]) - g1) == pytest.approx(np.linalg.norm(np.array(sw0["tip"][i]) - g0), abs=1e-6)
    assert bad["joints"] == fixed["joints"]                      # no limb was moved for it
    assert fixed["grip"] != bad["grip"] and len(fixed["grip"]) == len(fixed["times"])     # its own joint track made again
    assert GR.round_trip_error(fixed) < 1e-3                     # ... and it puts the blade where the clip's path says
    # under its bar BY ROOM on the swept reading, not only at the fault's own frame
    assert K.read(fixed)["pairs"].get("weapon|Right Arm", 0.0) <= K.BARS["weapon"] - R.ROOM + 1e-6
    # turned ABOUT THE POINT THE HAND IS ON: the hand is no further from the weapon's line than it was, at any frame (turned
    # about the grip point, a hand a quarter stud along the hilt comes 0.1 studs off it at 24 degrees)
    was, now = IH.read(dict(bad, hands="right")), IH.read(dict(fixed, hands="right"))
    assert (np.array(now["free"]) <= np.array(was["free"]) + 1e-6).all()      # never further off it than it was
    f = done[0]["frame"]
    assert np.linalg.norm(np.array(sw1["grip_path"][f]) - np.array(sw0["grip_path"][f])) > 0.02


@pytest.mark.parametrize("make, why", [
    (lambda k: T.arm_into_chest(k, -150), "no turn of 30 degrees with a slide of 0.45 studs takes it out"),
    (lambda k: T.blade_through(k), r"held in both hands, and no turn of 25 degrees about the hands with the hands kept on it"),
    (lambda k: legs_crossed(k, frames=range(len(k["times"]))), "that foot stands on the floor"),
    (lambda k: dict(left_arm_into_chest(k), grip_left=[[0, 0, 0, 1, 0, 0, 0]] * len(k["times"])), "carries the second weapon"),
    (lambda k: blade_toward_chest(k, 0.6), "held in the right hand, and no turn of 25 degrees about the hands"),
])
def test_what_it_must_not_or_cannot_move_is_refused_by_name_and_left_as_it_was(kesa, make, why):
    bad = make(kesa)
    before = copy.deepcopy(bad)
    with pytest.raises(ValueError, match=why):
        R.repair(bad)
    assert bad == before


def test_an_arm_that_holds_the_weapon_is_moved_with_it_or_refused_by_name(kesa):
    """(V3 anim stage C.1: a holding arm was refused outright; it is now moved WITH the weapon, the other hand put back
    on it - here the hands put back would go into the body, so it is refused, in the coupled move's own words)"""
    c = T.made("loved", "GsCombo4Underhip")                      # a loved cut whose holding hands fold 0.22 into the chest
    r = K.read(c)
    worst = r["worst"]["hand_torso"]
    # make the loved pose a fault by lowering its bar for this test only: the rule under test is WHO may be moved
    old = K.BARS["hand_torso"]
    K.BARS["hand_torso"] = max(worst["depth"] - 0.05, 0.01)
    try:
        assert worst["depth"] > 0.1
        with pytest.raises(ValueError, match=r"holds the weapon and its hand is 0\.\d+ studs into the Torso .* the weapon "
                                             r"carried with it"):
            R.repair(c)
    finally:
        K.BARS["hand_torso"] = old


def test_the_bounds_are_the_recipes_and_a_bound_that_is_not_one_is_refused(kesa):
    bad = T.arm_into_chest(kesa, -65)
    with pytest.raises(ValueError, match="no turn of 6 degrees with a slide of 0 studs takes it out"):
        R.repair(bad, max_deg=6, max_slide=0)
    fixed, done = R.repair(bad, max_deg=45)
    assert K.over(K.read(fixed)) == []
    for kw in ({"max_deg": -1}, {"max_slide": 2}, {"blade_deg": "a lot"}, {"max_deg": True}, {"max_deg": float("nan")}):
        with pytest.raises(ValueError, match="clear: .* is a number from 0 to"):
            R.repair(bad, **kw)


def test_a_declared_contact_is_not_a_fault_and_is_not_moved(kesa):
    meant = dict(T.arm_into_chest(kesa, -65), contact=[{"a": "Right Arm", "b": "Torso"}])
    fixed, done = R.repair(meant)
    assert fixed is meant and done == []


def test_a_looping_clips_move_wraps_round_its_seam(kesa):
    loop = T.arm_into_chest(kesa, -65, frames=range(0, 3))
    n = len(loop["times"])
    for i in range(n - 2, n):                                    # the same fault at the end: one pose across the seam
        loop["joints"]["Right Arm"]["frames"][i] = list(loop["joints"]["Right Arm"]["frames"][0])
        loop["joints"]["Left Arm"]["frames"][i] = list(loop["joints"]["Left Arm"]["frames"][0])
    loop["loop"] = True
    fixed, done = R.repair(loop)
    assert K.over(K.read(fixed)) == []
    F = fixed["joints"]["Right Arm"]["frames"]
    assert F[0] == pytest.approx(F[-1], abs=1e-9)                # the seam's two frames are still one pose
    assert turned(loop["joints"]["Right Arm"]["frames"][n - 3], F[n - 3]) > 0      # the move reached back across it


def test_it_is_an_op_of_a_derive_recipe_and_a_command(kesa, tmp_path, monkeypatch, capsys):
    import derive as D
    src = tmp_path / "Base.clip.json"
    src.write_text(json.dumps(T.arm_into_chest(kesa, -65)), encoding="utf-8")
    monkeypatch.setattr(D, "load_clip", lambda name: json.load(open(str(src), encoding="utf-8")))
    out = D.derive({"name": "Cleared", "from": "Base", "ops": [{"op": "clear"}]})
    clip = out[0] if isinstance(out, tuple) else out
    assert clip["name"] == "Cleared" and K.over(K.read(clip)) == []
    with pytest.raises(ValueError, match="no turn of 3 degrees"):
        D.derive({"name": "Bad", "from": "Base", "ops": [{"op": "clear", "max_deg": 3, "max_slide": 0}]})
    # the gate's own words lead to it
    _out, problem = K.gate(dict(T.arm_into_chest(kesa, -65), name="NewOne", source={"file": str(tmp_path / "NewOne.move.json")}))
    assert '{"op": "clear"}' in problem
    # the command: what it would do, then written
    capsys.readouterr()
    assert R.main([str(src)]) == 0
    said = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "the Right Arm turned" in said["summary"] and "nothing written: no --out" in said["summary"] and said["moves"]
    dst = tmp_path / "out.clip.json"
    assert R.main([str(src), "--out", str(dst)]) == 0 and K.over(K.read(json.load(open(str(dst), encoding="utf-8")))) == []
    far = tmp_path / "far.clip.json"
    far.write_text(json.dumps(T.arm_into_chest(kesa, -150)), encoding="utf-8")
    assert R.main([str(far), "--out", str(tmp_path / "no.json")]) == 1 and not (tmp_path / "no.json").exists()
    assert "not repaired" in capsys.readouterr().out


# ---------------------------------------------------------------- the one review, 2026-11-15
def test_an_arm_that_carries_the_weapons_joint_takes_its_track_along(kesa):
    """the weapon's joint track is relative to the right arm: moved without it, the blade ended half a stud off its path"""
    c = copy.deepcopy(kesa)
    h = math.radians(-65) / 2
    for i in range(len(c["times"])):                             # the left hand alone holds; the right arm hangs ...
        c["joints"]["Right Arm"]["frames"][i] = [0, 0, 0, 1, 0, 0, 0]
    for i in T.BLOCK:                                            # ... and swings into the chest on some frames
        c["joints"]["Right Arm"]["frames"][i] = [0, 0, math.sin(h), math.cos(h), 0, 0, 0]
    GR.add_grip(c)
    assert GR.round_trip_error(c) < 1e-3 and "hand_torso" in [k for k, _ in K.over(K.read(c))]
    fixed, done = R.repair(c, max_deg=60)                        # (the hanging hand grazes its own leg too: room for both)
    assert {d["what"] for d in done} == {"Right Arm"} and K.over(K.read(fixed)) == []
    assert fixed["grip"] != c["grip"] and GR.round_trip_error(fixed) < 1e-3 and fixed["sword"] == c["sword"]


def test_a_hand_far_along_the_blade_holds_it(kesa):
    """a hand 2.5 studs up the weapon's line (a greatsword's block) read as "nobody holds": the blade through that
    arm was failed, and the repair turned it about the wrong point - 8 of 24 built clips came off the hand"""
    c = one_handed(kesa)
    for i in range(len(c["times"])):                             # the grip point moved 2.25 studs back along the line
        g, t = np.array(c["sword"]["grip_path"][i]), np.array(c["sword"]["tip"][i])
        c["sword"]["grip_path"][i] = (g - 2.25 * (t - g) / np.linalg.norm(t - g)).tolist()
    held = R._holders(c, C.load_rig("r6"), 12)
    assert list(held) == ["Right Arm"] and held["Right Arm"] == pytest.approx(2.5, abs=0.01)
    # (kept to one stud either side of the grip point, that hand read 1.5 studs off the line: no holder at all)


def test_an_arm_that_takes_the_weapon_a_few_frames_later_is_moved_with_it_or_refused_by_name(kesa):
    c = copy.deepcopy(kesa)
    h = math.radians(65) / 2
    for i in range(0, 13):                                       # the left hand free, in the chest at 10-12, on the hilt from 13
        c["joints"]["Left Arm"]["frames"][i] = [0, 0, 0, 1, 0, 0, 0]
    for i in range(10, 13):
        c["joints"]["Left Arm"]["frames"][i] = [0, 0, math.sin(h), math.cos(h), 0, 0, 0]
    r = K.read(c)
    if [k for k, _ in K.over(r)] and K.over(r)[0][1]["a"] == "Left Arm":
        with pytest.raises(ValueError, match=r"the Left Arm holds the weapon and its hand is 0\.\d+ studs into the Torso "
                                             r"round frame 1\d"):
            R.repair(c)
    else:                                                        # (the fixture must really put that hand in the chest)
        pytest.fail(K.words(r, "fixture"))


def test_a_fault_that_lives_between_two_frames_is_not_answered_with_blind_moves(kesa):
    c = one_handed(kesa)
    i = 12
    for f, deg in ((i, 40.0), (i + 1, -40.0)):                   # the blade on one side at one frame, the other at the next
        g = np.array(c["sword"]["grip_path"][f], float)
        to = T.torso_at(c, f) - g
        to[1] = 0.0
        a = math.radians(deg)
        side = np.array([to[0] * math.cos(a) + to[2] * math.sin(a), 0.0, -to[0] * math.sin(a) + to[2] * math.cos(a)])
        c["sword"]["tip"][f] = (g + c["sword"]["length"] * side / np.linalg.norm(side)).tolist()
    assert K.over(K.read(c))
    try:
        fixed, done = R.repair(c, blade_deg=90)
    except ValueError as e:                                      # refused for what it is - never 24 moves that each "passed"
        assert "still over a bar after" not in str(e)
    else:
        assert K.over(K.read(fixed)) == [] and len(done) < R.PASSES


def test_a_props_clip_is_given_back_as_it_is(kesa):
    prop = dict(T.arm_into_chest(kesa, -65), prop="Chest")
    fixed, done = R.repair(prop)
    assert fixed is prop and done == []



def two_handed_toward_chest(clip, share, frames=T.BLOCK):
    """the two-handed cut with its blade turned `share` of the way toward the chest on some frames (both hands still on
    the hilt: it goes into its own right forearm)"""
    c = copy.deepcopy(clip)
    for i in frames:
        g = np.array(c["sword"]["grip_path"][i], float)
        d = np.array(c["sword"]["tip"][i], float) - g
        to = T.torso_at(c, i) - g
        v = d / np.linalg.norm(d) * (1 - share) + to / np.linalg.norm(to) * share
        c["sword"]["tip"][i] = (g + c["sword"]["length"] * v / np.linalg.norm(v)).tolist()
    return c


def test_a_blade_held_in_two_hands_is_turned_with_both_hands_kept_on_it(kesa):
    """(V3 anim stage C.1: refused as "two hands hold it" before) the blade turned about the hands, the hands put back
    on the hilt, nothing deeper anywhere, no new snap"""
    bad = two_handed_toward_chest(kesa, 0.47)
    GR.add_grip(bad)
    r = K.read(bad)
    rig = C.load_rig("r6")
    assert [k for k, _ in K.over(r)] == ["weapon"] and len(R._holders(bad, rig, r["worst"]["weapon"]["frame"])) == 2
    fixed, done = R.repair(bad)
    assert K.over(K.read(fixed)) == [] and done[0]["what"] == "weapon" and done[0]["held"] == "two"
    assert 0 < done[0]["deg"] <= R.BLADE_DEG
    assert not IH.read(dict(fixed, hands="two"))["loose"]                           # both hands still on the hilt
    m0, m1 = C.metrics(bad, rig), C.metrics(fixed, rig)
    assert not [p for p in m1["problems"] if p.startswith("pops") and not any(q.startswith("pops") for q in m0["problems"])]
    assert len(fixed["grip"]) == len(fixed["times"]) and GR.round_trip_error(fixed) < 1e-3


def test_a_stepped_clip_is_repaired_on_its_smooth_motion_and_stepped_again(kesa):
    """(V3 anim stage C.1: "it is a stepped clip" was a refusal) the smooth motion repaired, the holds put back on the
    very windows: inside a window every frame is its step's sample"""
    bad = T.arm_into_chest(kesa, -65)
    bad["stepped"] = [[0.0, 0.2, 2]]
    fixed, done = R.repair(bad)
    assert done and K.over(K.read(fixed)) == [] and fixed["stepped"] == [[0.0, 0.2, 2]]
    for i in range(1, 13, 2):                                    # (60 a second: frames 0..12, a sample every 2)
        for j, tr in fixed["joints"].items():
            assert tr["frames"][i] == tr["frames"][i - 1], (j, i)
    assert bad["stepped"] == [[0.0, 0.2, 2]] and "Right Arm" in bad["joints"]      # (the clip given is not changed)


def _ends(clip, i):
    """each limb's end (a hand, a foot) at frame i, in the root's space"""
    W = C.fk(C.load_rig("r6"), C.character_transforms(clip, C.load_rig("r6"), i))
    return {p: (W[p] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3] for p in R.ARMS + R.LEGS}, W


def test_a_counter_tilt_turns_the_torso_and_keeps_the_hands_and_the_feet(kesa):
    """V4 4.4 / 13.4.2: the torso (and the head on it) turned about the hips; every hand stays where it was (the arm
    re-aimed from its moved shoulder and slid the difference), every foot too (a lean through the hips leaves them),
    the weapon untouched - the hands on it are where they were"""
    rig = C.load_rig("r6")
    f = 12
    for ax, pivot in (((1, 0, 0), "hips"), ((0, 1, 0), "hips"), ((0, 0, 1), "Left Leg")):
        trial, slid = R._counter_tilt(kesa, rig, f, 12.0, ax, pivot, {}, R.MAX_SLIDE)
        for k in range(len(kesa["times"])):
            e0, W0 = _ends(kesa, k)
            e1, W1 = _ends(trial, k)
            for arm in R.ARMS:
                assert np.linalg.norm(e1[arm] - e0[arm]) < 1e-4, (ax, k, arm)
            if ax == (1, 0, 0):                                  # (a lean through the hips: both hips stay)
                for leg in R.LEGS:
                    assert np.linalg.norm(e1[leg] - e0[leg]) < 1e-4, (k, leg)
            w = R._span(kesa, f).get(k, 0.0)
            if w == 0.0:                                         # eased: none of it past EASE - the frame untouched
                assert trial["joints"]["Torso"]["frames"][k] == kesa["joints"]["Torso"]["frames"][k]
            else:                                                # ... and all of it at f
                turn = C.quat_angle(np.array(kesa["joints"]["Torso"]["frames"][k][:4], float),
                                    np.array(trial["joints"]["Torso"]["frames"][k][:4], float))
                assert turn == pytest.approx(12.0 * w, abs=0.01)
        assert trial["sword"] == kesa["sword"] and 0 < slid <= R.MAX_SLIDE
    # an arm that would have to slide past its bound to keep its hand: no such tilt
    with pytest.raises(ValueError, match="would slide"):
        R._counter_tilt(kesa, rig, f, 40.0, (1, 0, 0), "hips", {}, 0.05)


def test_a_fault_the_arm_cannot_clear_alone_is_cleared_by_a_counter_tilt_with_it(kesa):
    """a hand 0.46 studs in the chest and an arm bound to 3 degrees: refused before (the arm alone cannot); the torso
    tilted away and the arm's own 3 degrees take it out - the hand where it was at the tilt, the feet standing"""
    bad = T.arm_into_chest(kesa, -65)
    with pytest.raises(ValueError, match="nor does a counter-tilt"):
        R.repair(bad, max_deg=0.0)
    fixed, done = R.repair(bad, max_deg=3.0)
    assert K.over(K.read(fixed)) == []
    tilt = [d for d in done if d["what"] == "Torso"]
    assert tilt and tilt[0]["how"].startswith("counter-tilt") and tilt[0]["deg"] <= R.TILT_DEG
    assert "counter-tilt" in R.words(done)
    rig = C.load_rig("r6")
    low = {leg: np.array([C.lowest(rig, leg, w[leg]) for w in C.world_frames(bad, rig)]) for leg in R.LEGS}
    low2 = {leg: np.array([C.lowest(rig, leg, w[leg]) for w in C.world_frames(fixed, rig)]) for leg in R.LEGS}
    for leg in R.LEGS:                                            # a foot on the floor stays on it
        on = low[leg] <= low[leg].min() + 0.1
        assert np.all(np.abs(low2[leg][on] - low[leg][on]) <= R.FOOT_DRIFT + 1e-6)
    # its bound is the recipe's
    with pytest.raises(ValueError, match="tilt_deg is a number"):
        R.repair(bad, tilt_deg=90)


def test_crossed_legs_in_the_air_are_stepped_apart_and_a_standing_foot_never_is(kesa):
    """the step (V4 4.4: 'root step-pivot'): a foot in the other leg, both legs turned apart, mirrored, by the least
    that takes it out - when neither foot stands on the floor at the frames the move touches"""
    bad = copy.deepcopy(legs_crossed(kesa))
    rig = C.load_rig("r6")
    n = len(bad["times"])
    off = {leg: np.zeros(n, bool) for leg in R.LEGS}               # (neither foot standing)
    on = {leg: np.ones(n, bool) for leg in R.LEGS}                 # (both standing)
    got = R._step_apart(bad, rig, "Right Leg", "Left Leg", 12, 30.0, off)
    assert got and {d["what"] for d in got} == {"Right Leg", "Left Leg"} and all(d["how"] == "stepped apart" for d in got)
    assert got[0]["deg"] == got[1]["deg"] <= 30.0
    assert R._pairs(bad, 12).get("Right Leg|Left Leg", 0.0) <= K.BARS["foot"] - R.ROOM + 1e-9
    fresh = copy.deepcopy(legs_crossed(kesa))
    assert R._step_apart(fresh, rig, "Right Leg", "Left Leg", 12, 30.0, on) is None and fresh == legs_crossed(kesa)
