"""kit/anim/collide.py - nothing passes through the body (the owner's limitations list 2026-11-15, A-R05): the weapon,
the hands and the feet against the body's blocks, SWEPT between frames, with declared contacts left out, as a gate of
every build. On the cuts the owner loved and rejected (generated in memory, read only) and on those cuts broken on
purpose."""
import copy
import glob
import json
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C         # noqa: E402
import collide as K      # noqa: E402
import strike as S       # noqa: E402

FAULTS = os.path.join(ROOT, "kit", "selftest", "anim", "faults")
BLOCK = range(10, 15)    # the frames a test breaks


def made(kind, name):
    with open(os.path.join(FAULTS, kind, f"{name}.move.json"), encoding="utf-8") as fh:
        return S.generate(json.load(fh))[0]


@pytest.fixture(scope="module")
def kesa():
    return made("loved", "Katana1Kesa")


def torso_at(clip, i):
    return C.world_frames(clip, C.load_rig("r6"))[i]["Torso"][:3, 3]


def blade_through(clip, frames=BLOCK):
    """the cut with its blade pointed back through the chest on some frames (the hands stay where they are)"""
    c = copy.deepcopy(clip)
    for i in frames:
        g = np.array(c["sword"]["grip_path"][i], float)
        to = torso_at(c, i) - g
        c["sword"]["tip"][i] = (g + c["sword"]["length"] * to / np.linalg.norm(to)).tolist()
    return c


def arm_into_chest(clip, deg=-90, frames=BLOCK):
    """the cut, unarmed, with its right arm swung across into the chest on some frames"""
    c = copy.deepcopy(clip)
    c.pop("sword", None)
    h = math.radians(deg) / 2
    for i in frames:
        c["joints"]["Right Arm"]["frames"][i] = [0, 0, math.sin(h), math.cos(h), 0, 0, 0]
        c["joints"]["Left Arm"]["frames"][i] = [0, 0, 0, 1, 0, 0, 0]
    return c


# ---------------------------------------------------------------- the loved and the rejected
def test_the_loved_cuts_pass_with_room_and_the_rejected_ones_were_not_rejected_for_this():
    worst = {k: 0.0 for k in K.BARS}
    for path in sorted(glob.glob(os.path.join(FAULTS, "loved", "*.move.json"))):
        name = os.path.basename(path)[:-len(".move.json")]
        r = K.read(made("loved", name))
        assert K.over(r) == [], K.words(r, name)
        assert r["weapon"] is True and r["worst"]["weapon"]["depth"] == 0.0     # no loved blade touches its own body
        for k in K.BARS:
            worst[k] = max(worst[k], r["worst"][k]["depth"])
    # the bars stand above what the loved cuts measure, by a margin - and below a point at a block's middle (0.5)
    for k, bar in K.BARS.items():
        assert worst[k] + 0.1 <= bar < 0.5, (k, worst[k], bar)
    assert worst["hand_torso"] == pytest.approx(0.222, abs=0.01) and worst["hand"] == pytest.approx(0.219, abs=0.01)
    # two hands on one hilt sit inside each other's arm block: not judged while both arms hold the weapon; the same
    # pose with no weapon reads it (0.35 to 0.47: under its bar, which only the block's very middle passes)
    gyaku = made("loved", "Katana2GyakuKesa")
    assert K.read(gyaku)["worst"]["hand_arm"]["depth"] == 0.0
    bare = dict(gyaku)
    bare.pop("sword")
    r = K.read(bare)
    assert 0.3 < r["worst"]["hand_arm"]["depth"] <= 0.5 and r["worst"]["hand_arm"]["b"] in ("Right Arm", "Left Arm")
    # the rejected cuts read clean: this check does not tell loved from rejected (it was never why they were rejected)
    for path in sorted(glob.glob(os.path.join(FAULTS, "rejected", "*.move.json"))):
        r = K.read(made("rejected", os.path.basename(path)[:-len(".move.json")]))
        assert K.over(r) == []


# ---------------------------------------------------------------- broken on purpose
def test_a_blade_through_the_chest_is_caught_with_its_frame(kesa):
    bad = blade_through(kesa)
    r = K.read(bad)
    w = r["worst"]["weapon"]
    assert [k for k, _ in K.over(r)] == ["weapon"]
    assert w["a"] == "weapon" and w["depth"] > 0.4 and w["frame"] in range(9, 15)
    assert r["pairs"]["weapon|Torso"] > 0.4
    said = K.words(r, "Kesa")
    assert f"the weapon passes through the {w['b']} by" in said and f"at frame {w['frame']}" in said and "at most 0.2" in said
    # the arm that holds it is judged too, past the stretch that is in its hand: turned back, the blade runs up the
    # wielder's own forearm (the one review, 2026-11-15) - while the loved cut's own blade touches neither arm
    assert any(k.startswith("weapon|") and "Arm" in k for k in r["pairs"])
    assert not any(k.startswith("weapon|") for k in K.read(kesa)["pairs"])


def test_a_blade_that_is_on_one_side_at_one_frame_and_the_other_at_the_next_is_caught_on_its_way(kesa, monkeypatch):
    c = copy.deepcopy(kesa)
    i = 12
    for f, deg in ((i, 40.0), (i + 1, -40.0)):
        g = np.array(c["sword"]["grip_path"][f], float)
        to = torso_at(c, f) - g
        to[1] = 0.0
        a = math.radians(deg)
        side = np.array([to[0] * math.cos(a) + to[2] * math.sin(a), 0.0, -to[0] * math.sin(a) + to[2] * math.cos(a)])
        c["sword"]["tip"][f] = (g + c["sword"]["length"] * side / np.linalg.norm(side)).tolist()
    # (the grip is raised beside the head on these frames: level with it, the blade crosses the Head on its way round)
    swept = K.read(c)
    assert max(swept["pairs"].get("weapon|Head", 0.0), swept["pairs"].get("weapon|Torso", 0.0)) > K.BARS["weapon"]
    # read at the frames only, the same clip never has the blade in the head or the chest: the sweep is what catches it
    monkeypatch.setattr(K, "MAX_SUB", 1)
    still = K.read(c)["pairs"]
    assert "weapon|Head" not in still and "weapon|Torso" not in still


def test_a_hand_through_the_chest_and_a_foot_through_the_other_leg_are_caught(kesa):
    r = K.read(arm_into_chest(kesa))
    assert ("hand_torso", r["worst"]["hand_torso"]) in K.over(r)
    w = r["worst"]["hand_torso"]
    assert w["a"] == "Right Arm" and w["b"] == "Torso" and w["depth"] > 0.45 and w["frame"] in range(9, 15)
    assert "Right Arm: a hand goes into the Torso by" in K.words(r, "Kesa")
    # a hand that only folds toward the chest (45 degrees: 0.24 deep) is not failed
    assert "hand_torso" not in [k for k, _ in K.over(K.read(arm_into_chest(kesa, -45)))]
    legs = copy.deepcopy(kesa)
    h = math.radians(-40) / 2
    for i in BLOCK:
        legs["joints"]["Right Leg"]["frames"][i] = [0, 0, math.sin(h), math.cos(h), 0, 0, 0]
    r = K.read(legs)
    assert [k for k, _ in K.over(r)] == ["foot"] and r["worst"]["foot"]["a"] == "Right Leg" and r["worst"]["foot"]["b"] == "Left Leg"


# ---------------------------------------------------------------- a contact that is meant
def test_a_declared_contact_is_not_judged_and_one_that_cannot_be_read_is_refused(kesa):
    bad = arm_into_chest(kesa)
    fps = bad["fps"]
    meant = dict(bad, contact=[{"a": "Right Arm", "b": "Torso", "from": 9 / fps, "to": 15 / fps}])
    assert K.over(K.read(meant)) == []
    assert K.over(K.read(dict(bad, contact=[{"a": "Torso", "b": "Right Arm"}]))) == []     # either way round, the whole clip
    # a window that does not cover the frames excuses nothing; nor does another pair
    assert K.over(K.read(dict(bad, contact=[{"a": "Right Arm", "b": "Torso", "from": 0.0, "to": 5 / fps}])))
    assert K.over(K.read(dict(bad, contact=[{"a": "Left Arm", "b": "Torso"}])))
    blade = blade_through(kesa)
    through = [{"a": "weapon", "b": part} for part in ("Torso", "Right Arm", "Left Arm")]
    assert K.over(K.read(dict(blade, contact=through))) == []
    assert [w["b"] for _, w in K.over(K.read(dict(blade, contact=through[1:])))] == ["Torso"]
    for said, why in (("Torso", "is a list of"), ([{"a": "Right Arm"}], "names its two sides"), ([{"a": "Rihgt Arm", "b": "Torso"}], "names Rihgt Arm, which is no part"),
                      ([{"a": "weapon", "b": "Sheath"}], "names Sheath"), ([{"a": "Head", "b": "Torso", "from": 1, "to": 0.5}], "the end after the start"),
                      ([{"a": "Head", "b": "Torso", "from": "0"}], "are seconds"), ([7], "names its two sides")):
        with pytest.raises(ValueError, match=why):
            K.read(dict(bad, contact=said))


# ---------------------------------------------------------------- the gate
def test_the_gate_fails_a_clip_over_a_bar_and_says_a_clip_made_before_the_rule(kesa, tmp_path):
    good, bad = K.gate(kesa), K.gate(blade_through(kesa))
    assert good[1] is None and good[0]["bars"] == K.BARS and good[0]["worst"]["weapon"]["depth"] == 0.0
    assert "the weapon passes through the Torso" in bad[1] and "\"contact\"" in bad[1]
    # not a character's R6 clip: nothing to read
    assert K.gate(dict(kesa, rig="R15")) == (None, None) and K.gate(dict(kesa, prop="Chest")) == (None, None)
    # a contact that cannot be read is a problem of the clip, not a crash of the build
    out, why = K.gate(dict(kesa, contact="everything"))
    assert "error" in out and "could not be read" in why
    # made before the rule: said, never failed; the list is beside the clip's source
    anims = tmp_path / "anims"
    (anims / "blocks").mkdir(parents=True)
    src = {"file": str(anims / "Old.move.json")}
    old = dict(blade_through(kesa), name="Old", source=src)
    assert K.gate(old)[1] is not None
    (anims / "blocks" / K.BEFORE).write_text(json.dumps({"clips": ["Old"]}), encoding="utf-8")
    out, why = K.gate(old)
    assert why is None and out["made_before_the_rule"] is True
    assert K.gate(dict(old, name="New"))[1] is not None
    (anims / "blocks" / K.BEFORE).write_text("{not json", encoding="utf-8")
    assert "could not be read" in K.gate(old)[1]              # a list that cannot be read excuses nobody


def test_the_list_is_frozen_once_from_what_the_gate_fails(kesa, tmp_path, capsys):
    built = tmp_path / "built"
    built.mkdir()
    for name, c in (("Fine", kesa), ("Through", blade_through(kesa)), ("Through.tune", blade_through(kesa))):
        (built / f"{name}.clip.json").write_text(json.dumps(dict(c, name=name)), encoding="utf-8")
    (built / "Broken.clip.json").write_text("{", encoding="utf-8")
    out = tmp_path / "blocks" / K.BEFORE
    assert K.main(["freeze", str(built), "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["clips"] == ["Through"]
    assert K.main(["freeze", str(built), "--out", str(out)]) == 1 and "frozen once" in capsys.readouterr().out
    # the command on one clip
    p = tmp_path / "one.clip.json"
    p.write_text(json.dumps(blade_through(kesa)), encoding="utf-8")
    assert K.main([str(p)]) == 1
    v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert v["status"] == "fail" and "passes through the Torso" in v["summary"] and v["reading"]["worst"]["weapon"]["depth"] > 0.4


def test_the_builds_motion_gates_carry_it(kesa, tmp_path, capsys):
    import metrics as MT
    src = {"kind": "move", "file": str(tmp_path / "anims" / "X.move.json")}
    for name, c, code in (("Fine", kesa, 0), ("Through", arm_into_chest(kesa), 1)):
        p = tmp_path / f"{name}.clip.json"
        p.write_text(json.dumps(dict(c, name=name, source=src)), encoding="utf-8")
        got = MT.main([str(p)])
        v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        m = json.loads((tmp_path / f"{name}.metrics.json").read_text(encoding="utf-8"))
        assert "collide" in m and m["collide"]["bars"] == K.BARS
        hit = [x for x in m["problems"] if "goes into the Torso" in x]
        assert (got != 0 and len(hit) == 1) if code else (not hit), v["summary"]


# ---------------------------------------------------------------- what the one review found (2026-11-15)
def test_a_contact_declared_in_the_move_reaches_the_gate(kesa):
    with open(os.path.join(FAULTS, "loved", "Katana1Kesa.move.json"), encoding="utf-8") as fh:
        move = json.load(fh)
    said = [{"a": "Right Arm", "b": "Torso"}]
    built = S.generate({**move, "contact": said})[0]
    assert built["contact"] == said and "contact" not in kesa
    bad = arm_into_chest(built)
    bad["contact"] = built["contact"]
    assert K.gate(bad)[1] is None and K.gate(arm_into_chest(kesa))[1] is not None


def test_a_fast_blade_through_a_leg_is_caught_at_thirty_frames_a_second(kesa):
    # the blade swept 6 studs between two frames across the 1-stud left leg (8 samples read it 0.125 deep: missed)
    c = copy.deepcopy(kesa)
    W = C.world_frames(c, C.load_rig("r6"))
    i = 12
    leg = W[i]["Left Leg"][:3, 3]
    for f, side in ((i, -3.0), (i + 1, 3.0)):
        g = np.array(c["sword"]["grip_path"][f], float)
        c["sword"]["tip"][f] = (leg + np.array([side, 0.0, 0.0]) + (leg + np.array([side, 0.0, 0.0]) - g) * 0.2).tolist()
    r = K.read(c)
    assert r["pairs"].get("weapon|Left Leg", 0.0) > K.BARS["weapon"]


def test_times_are_the_clips_own_and_a_root_of_another_length_is_refused(kesa):
    bad = arm_into_chest(kesa)
    # a contact that ends at frame 14's own time covers frame 14, whatever the frame rate says
    slow = dict(bad, times=[t * 2 for t in bad["times"]])
    assert K.over(K.read(dict(slow, contact=[{"a": "Right Arm", "b": "Torso", "from": slow["times"][9], "to": slow["times"][15]}]))) == []
    with pytest.raises(ValueError, match="its root track has 3 frame"):
        K.read(dict(kesa, root=[[0, 0, 0, 1, 0, 0, 0]] * 3))


def test_the_kits_own_gaits_and_the_rest_pose_read_clean():
    import gait_r6 as G
    for kind in ("walk", "run", "idle"):
        r = K.read(G.generate({"name": kind, "kind": kind}))
        assert K.over(r) == [] and r["weapon"] is False, (kind, r["worst"])
