"""kit/anim/cleanup.py - the `plant` op of a `kit anim derive` recipe (the owner's method lists 2026-11-13: motion
capture cleanup): feet that skate are held still by moving the body over them, and what it refuses. Clips: cuts the
owner loved, generated in memory (read only), and made-up standing / walking bodies whose LEGS skate."""
import copy
import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import cleanup as CL        # noqa: E402
import clip as C            # noqa: E402
import strike as S          # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved")
RIG = C.load_rig("r6")
BAR = C.GATES["foot_slide"]
JOINTS = ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")


def loved(name="Katana1Kesa", **more):
    with open(os.path.join(LOVED, f"{name}.move.json"), encoding="utf-8") as fh:
        return S.generate({**json.load(fh), **more})[0]


def with_root(c, per_frame=0.0, lift=0.0):
    """the clip with a root track: its whole body drifting sideways (+X) that much every frame"""
    c = copy.deepcopy(c)
    n = len(c["times"])
    c["root"] = [[0, 0, 0, 1, per_frame * i, lift, 0] for i in range(n)]
    return c


def gate_slide(c):
    """the BUILD's own reading (kit/anim/clip.py metrics), not the op's"""
    return C.metrics(c, RIG)["feet"]["slide_max_studs_frame"]


def standing(n=40, root=True):
    """a body standing in its rest pose (with a still root track unless root=False)"""
    c = {"name": "Standing", "rig": "R6", "fps": 60, "times": [i / 60 for i in range(n)], "events": [],
         "joints": {j: {"frames": [[0, 0, 0, 1, 0, 0, 0] for _ in range(n)]} for j in JOINTS}}
    return with_root(c) if root else c


def walking(drift=0.15, apart=0.0, n=80):
    """a walk as a capture gives it: the right leg lifted on frames 0-19, both down 20-29, the left lifted 30-49, both
    down 50-59, the right lifted 60-79 - and every STANDING leg slipping `drift` studs a frame in its hip (+ `apart`:
    the two slipping away from each other while both stand)"""
    c = standing(n)
    gap = 0.0
    for i in range(n):
        right_up, left_up = i < 20 or i >= 60, 30 <= i < 50
        if i and not right_up and not left_up:
            gap += apart                                         # (it grows only while both stand: no foot ever teleports)
        c["joints"]["Right Leg"]["frames"][i][4] = drift * i + gap
        c["joints"]["Left Leg"]["frames"][i][4] = drift * i - gap
        c["joints"]["Right Leg"]["frames"][i][5] = 0.5 if right_up else 0.0
        c["joints"]["Left Leg"]["frames"][i][5] = 0.5 if left_up else 0.0
    return c


def test_a_body_given_a_skate_is_planted_back_and_only_the_root_moves():
    clean = loved()
    own = gate_slide(clean)
    c = with_root(clean, 0.05)
    assert own <= BAR < gate_slide(c)                            # the cut passes the build's bar; with the skate it fails it
    before = copy.deepcopy(c)
    said = CL.op_plant(c, max_shift=3.0)
    assert gate_slide(c) <= own + 0.003 and "now" in said        # back to the cut's own feet
    for k in ("joints", "sword", "events", "times", "fps"):
        assert c[k] == before[k]
    R0, R1 = np.array(before["root"]), np.array(c["root"])
    assert np.allclose(R0[:, :4], R1[:, :4]) and np.allclose(R0[:, 5], R1[:, 5])     # its turn and its height are untouched
    steps = np.linalg.norm(np.diff(R1[:, [4, 6]] - R0[:, [4, 6]], axis=0), axis=1)
    assert steps.max() < 0.15                                    # nothing pops: the correction moves a little a frame


def test_legs_that_slip_through_a_walk_are_held_through_every_hand_over():
    c = walking(0.15)
    assert gate_slide(c) > BAR
    said = CL.op_plant(c, max_shift=20)
    assert gate_slide(c) < 0.002                                 # every standing foot holds still, landings and lift-offs too
    R = np.array(c["root"])[:, [4, 6]]
    assert np.abs(np.diff(R, axis=0)).max() < 0.16 and "now 0.00" in said
    # the build's reading is what the op says, and the feet really stand where they stood
    soles = CL._soles(c, RIG)
    for pos, contact in soles.values():
        runs = np.flatnonzero(contact[1:] & contact[:-1])
        assert np.abs(pos[runs + 1][:, [0, 2]] - pos[runs][:, [0, 2]]).max() < 0.002


def test_feet_that_drift_apart_are_mended_as_far_as_the_body_can_and_the_rest_is_said():
    c = walking(0.15, apart=0.04)
    s0 = gate_slide(c)
    said = CL.op_plant(c, max_shift=20)
    s1 = gate_slide(c)
    assert s1 < 0.5 * s0 and abs(s1 - 0.04) < 0.01 and f"now {s1:.3f}" in said     # each foot keeps half the 0.08 they part by
    R = np.array(c["root"])[:, [4, 6]]
    assert np.abs(np.diff(R, axis=0)).max() < 0.2                # no jump when one of the two lifts
    only = standing()                                            # the two legs slide straight away from each other: nothing to gain
    for i in range(len(only["times"])):
        only["joints"]["Left Leg"]["frames"][i][4] = 0.15 * i
        only["joints"]["Right Leg"]["frames"][i][4] = -0.15 * i
    before = copy.deepcopy(only)
    with pytest.raises(ValueError, match="drift apart, which moving the body cannot mend"):
        CL.op_plant(only, max_shift=20)
    assert only == before


def test_a_clip_that_passes_the_builds_bar_is_left_untouched():
    for name in sorted(f[:-10] for f in os.listdir(LOVED) if f.endswith(".move.json")):
        c = loved(name)
        before = copy.deepcopy(c)
        assert gate_slide(c) <= BAR
        assert "nothing changed" in CL.op_plant(c) and c == before     # every loved cut: not one number of it moves
    small = with_root(loved(), 0.004)
    before = copy.deepcopy(small)
    assert "inside the build's bar" in CL.op_plant(small) and small == before


def test_a_clip_that_stood_in_place_is_not_given_travel_unasked():
    c = walking(0.15)
    del c["root"]
    before = copy.deepcopy(c)
    with pytest.raises(ValueError, match="stands in place .no root track."):
        CL.op_plant(c, max_shift=20)
    assert c == before
    said = CL.op_plant(c, max_shift=20, travel=True)
    assert "the root track is new: the game now moves the character" in said and len(c["root"]) == len(c["times"])
    none = walking(0.15)
    none["root"] = None                                          # a key that is there and empty stays exactly that
    with pytest.raises(ValueError, match="stands in place"):
        CL.op_plant(none, max_shift=20)
    assert "root" in none and none["root"] is None


@pytest.mark.parametrize("change, why", [
    (lambda c: c.update(loop=True), "loops or walks in place"),
    (lambda c: c.update(locomotion={"speed": 16}), "loops or walks in place"),
    (lambda c: c.update(stepped={"on": 3}), "STEPPED"),
    (lambda c: c.update(root=c["root"][:30]), "root track carries 30 rows and the clip 80 frames"),
])
def test_clips_it_is_not_for_are_refused(change, why):
    c = walking(0.15)
    change(c)
    before = copy.deepcopy(c)
    with pytest.raises(ValueError, match=why):
        CL.op_plant(c, max_shift=20)
    assert c == before


def test_travel_is_not_skate_and_feet_that_never_stand_are_refused():
    c = walking(0.15)                                            # 12 studs in all: with the usual limit that is travel
    before = copy.deepcopy(c)
    with pytest.raises(ValueError, match="that is travel, not skate"):
        CL.op_plant(c)
    assert c == before
    air = with_root(loved(), 0.2, lift=2.0)
    with pytest.raises(ValueError, match="no foot of this clip ever stands"):
        CL.op_plant(air)
    for bad in (0, -1, True, "far", float("nan")):
        with pytest.raises(ValueError, match="max_shift is how far"):
            CL.op_plant(walking(0.15), max_shift=bad)
    with pytest.raises(ValueError, match="travel is true or false"):
        CL.op_plant(walking(0.15), max_shift=20, travel="yes")


def test_it_is_an_op_of_a_derive_recipe(tmp_path, monkeypatch):
    import derive as D
    src = tmp_path / "Base.clip.json"
    src.write_text(json.dumps(walking(0.15)), encoding="utf-8")
    monkeypatch.setattr(D, "load_clip", lambda name: json.load(open(str(src), encoding="utf-8")))
    out = D.derive({"name": "Planted", "from": "Base", "ops": [{"op": "plant", "max_shift": 20}]})
    clip = out[0] if isinstance(out, tuple) else out
    assert clip["name"] == "Planted" and gate_slide(clip) < 0.002
    with pytest.raises(ValueError, match="max_shift"):
        D.derive({"name": "Bad", "from": "Base", "ops": [{"op": "plant", "max_shift": 0}]})
    with pytest.raises(ValueError, match="travel is true or false"):
        D.derive({"name": "Bad", "from": "Base", "ops": [{"op": "plant", "travel": 1}]})
