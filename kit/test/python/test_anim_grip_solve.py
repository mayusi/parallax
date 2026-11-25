"""kit/anim/grip_solve.py - the hands a clip says hold its weapon are PUT ONTO it (the owner's limitations list
2026-11-15, A-R08: the check existed, a solve for any route did not). On the cuts the owner loved (generated in
memory, read only), with an arm let go or drifted on purpose."""
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
import derive as D               # noqa: E402
import grip as GR                # noqa: E402
import grip_solve as G           # noqa: E402
import in_hand as IH             # noqa: E402
import test_anim_collide as T    # noqa: E402

RIG = C.load_rig("r6")


def loved(name="Katana1Kesa"):
    return GR.add_grip(T.made("loved", name))


def let_go(clip, arm="Left Arm"):
    c = copy.deepcopy(clip)
    for i in range(len(c["times"])):
        c["joints"][arm]["frames"][i] = [0, 0, 0, 1, 0, 0, 0]
    return GR.add_grip(c)


def hand(clip, arm, i):
    return (C.fk(RIG, C.character_transforms(clip, RIG, i))[arm] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]


def along(clip, arm, i):
    """where along the weapon's line the hand is (studs from the grip point), and how far off the line"""
    g, t = np.array(clip["sword"]["grip_path"][i]), np.array(clip["sword"]["tip"][i])
    ax = (t - g) / np.linalg.norm(t - g)
    h = hand(clip, arm, i)
    a = float(np.dot(h - g, ax))
    return a, float(np.linalg.norm(h - (g + a * ax)))


@pytest.mark.parametrize("name", ["Katana1Kesa", "GsCombo4Underhip", "Katana3Makko"])
def test_a_clip_whose_hands_hold_the_weapon_is_not_moved(name):
    c = loved(name)
    solved, r = G.solve(c, "two")
    assert r["moved"] == 0 and r["worst_before"] == 0.0 and G.words(r) == "both hands already hold the weapon at every frame: nothing moved"
    for arm in ("Right Arm", "Left Arm"):
        for a, b in zip(c["joints"][arm]["frames"], solved["joints"][arm]["frames"]):
            assert C.quat_angle(a, b) < 0.01 and np.allclose(a[4:7], b[4:7], atol=1e-4)
    assert solved is not c and solved["hands"] == "two" and "hands" not in c


@pytest.mark.parametrize("name", ["Katana1Kesa", "GsCombo4Underhip", "Katana3Makko"])
def test_an_arm_that_let_go_is_put_back_where_the_loved_cut_holds_it(name):
    """WHAT THIS PROVES: the solve reaches its place, at every frame, with the weapon and the other arm untouched.
    The place itself - half the grip spacing behind the grip point - is where the strike builder puts a loved cut's
    left hand, so "back where the loved cut holds it" is true of the HAND, by construction; it is not true of the
    arm's roll (the block is turned 24 to 40 degrees otherwise than the loved arm: the one review, 2026-11-15)"""
    c = loved(name)
    bad = let_go(c)
    before = copy.deepcopy(bad)
    assert IH.read(dict(bad, hands="two"))["worst"] > 2.5 and IH.gate(dict(bad, hands="two"))[1] is not None
    solved, r = G.solve(bad, "two")
    assert bad == before                                         # the clip given is never changed
    assert r["worst_after"] == 0.0 and r["moved"] == len(c["times"]) and r["worst_before"] > 2.5
    # the left hand is back where the loved cut's own left hand is, at every frame - the weapon and the right arm untouched
    for i in range(len(c["times"])):
        assert np.linalg.norm(hand(solved, "Left Arm", i) - hand(c, "Left Arm", i)) < 1e-3
    assert solved["sword"] == bad["sword"] and solved["joints"]["Right Arm"] == bad["joints"]["Right Arm"]
    assert solved["grip"] == bad["grip"]                         # the weapon's own joint track: the right arm did not move
    # no jump: the solved arm turns, frame to frame, within POP of what the loved arm itself does there
    grew = G._turns(solved["joints"]["Left Arm"]["frames"]) - G._turns(c["joints"]["Left Arm"]["frames"])
    assert float(grew.max()) < G.POP
    assert solved["hands"] == "two" and IH.gate(solved)[1] is None      # it SAYS its hands, and the gate holds it to them
    assert "the furthest a hand was off the weapon" in G.words(r) and ", now 0.00;" in G.words(r)


def test_a_hand_that_drifted_keeps_its_own_place_along_the_hilt():
    c = loved()
    bad = copy.deepcopy(c)
    h = math.radians(6) / 2
    for i in range(12, 30):                                      # the left arm turned 6 degrees on some frames
        f = bad["joints"]["Left Arm"]["frames"][i]
        bad["joints"]["Left Arm"]["frames"][i] = list(D.qmul(np.array([0, 0, math.sin(h), math.cos(h)]), np.array(f[:4]))) + list(f[4:7])
    a0, off0 = along(bad, "Left Arm", 20)
    assert 0.1 < off0 < G.NEAR                                   # off the weapon by more than the gate allows, still near it
    solved, r = G.solve(bad, "two")
    a1, off1 = along(solved, "Left Arm", 20)
    assert off1 < 1e-3 and abs(a1 - max(a0, -IH.BEHIND)) < 1e-3  # onto the line at ITS OWN place along it, not the loved -0.25
    assert abs(a1 - (-0.25)) > 0.01
    assert r["moved"] == 18 and r["turned_deg"] < 12
    for i in list(range(0, 12)) + list(range(30, len(c["times"]))):
        assert C.quat_angle(solved["joints"]["Left Arm"]["frames"][i], bad["joints"]["Left Arm"]["frames"][i]) < 0.01


def test_one_hand_and_a_place_said_along_the_weapon():
    c = let_go(loved(), "Right Arm")
    solved, r = G.solve(c, "right")
    assert r["worst_after"] == 0.0 and solved["joints"]["Left Arm"] == c["joints"]["Left Arm"]
    a, off = along(solved, "Right Arm", 20)
    assert off < 1e-3 and abs(a - 0.25) < 1e-3                   # the loved place: half the weapon's grip spacing ahead
    assert solved["grip"] != c["grip"]                           # the weapon rides the right arm: its joint track made again
    assert GR.round_trip_error(solved) < 1e-3                    # ... and it puts the blade where the clip's path says
    for i in (0, 20, 40):                                        # ... and puts the weapon where its path says, to the stud
        A = C.fk(RIG, C.character_transforms(solved, RIG, i))["Right Arm"]
        Tm = np.eye(4)
        Tm[:3, :3] = C.quat_mat(solved["grip"][i][:4])
        Tm[:3, 3] = solved["grip"][i][4:7]
        assert np.allclose((A @ GR.GRIP_C0 @ Tm)[:3, 3], solved["sword"]["grip_path"][i], atol=1e-4)
    # a staff held off its hilt: both places said
    staff, r = G.solve(let_go(loved()), "two", at={"right": 0.5, "left": -0.8})
    assert abs(along(staff, "Left Arm", 20)[0] + 0.8) < 1e-3 and abs(along(staff, "Right Arm", 20)[0] - 0.5) < 1e-3
    assert IH.read(staff)["loose"] == []


def test_a_weapon_the_arm_cannot_reach_is_refused_with_the_frame_and_the_gap():
    c = let_go(loved())
    for i in range(20, 26):                                      # the weapon carried 6 studs off to the right
        for k in ("grip_path", "tip"):
            c["sword"][k][i] = [c["sword"][k][i][0] + 6.0] + c["sword"][k][i][1:]
    before = copy.deepcopy(c)
    with pytest.raises(ValueError, match=r"the left hand does not reach the weapon at frame 2\d .* studs short with the arm 2.5 studs out"):
        G.solve(c, "two")
    assert c == before
    with pytest.raises(ValueError, match="does not reach"):
        G.solve(let_go(loved()), "two", max_slide=0.5)           # a tighter bound is the recipe's to say


def test_a_stretch_the_weapon_is_out_of_the_hands_is_not_solved():
    c = let_go(loved())
    c["events"] = c["events"] + [{"name": "Toss", "t": 10 / 60}, {"name": "Catch", "t": 40 / 60}]
    solved, r = G.solve(c, "two")
    for i in range(18, 33):                                      # well inside it: the arm as it was, to the digit
        assert solved["joints"]["Left Arm"]["frames"][i] == c["joints"]["Left Arm"]["frames"][i]
    # outside it the hand is fully on the weapon at every frame (the gate holds it there) ...
    for i in list(range(0, 11)) + list(range(40, len(c["times"]))):
        assert along(solved, "Left Arm", i)[1] < 1e-3
    assert IH.read(solved)["loose"] == []
    # ... and it leaves and comes back INSIDE the stretch, over EASE frames: no jump at the toss or the catch
    off = [along(solved, "Left Arm", i)[1] for i in (10, 12, 14, 17)]
    assert off[0] < 1e-3 and off[0] < off[1] < off[2] < off[3] and off[3] > 2.0
    back = [along(solved, "Left Arm", i)[1] for i in (33, 36, 38, 40)]
    assert back[0] > back[1] > back[2] > back[3] and back[3] < 1e-3


def test_a_hand_put_through_the_body_is_refused(monkeypatch):
    c = let_go(loved("GsCombo4Underhip"))                        # the loved hold folds 0.22 studs into the chest
    monkeypatch.setitem(K.BARS, "hand_torso", 0.1)               # (the rule under test: a NEW pass-through of a moved arm)
    with pytest.raises(ValueError, match=r"put on the weapon, the Left Arm's hand goes 0.2\d studs into the Torso .*before the solve 0.00"):
        G.solve(c, "two")
    # (every pair of the moved arm is read, not the worst reading of its kind)
    with pytest.raises(ValueError, match="the Left Arm's hand goes"):
        G.solve(c, "left")


@pytest.mark.parametrize("change, kw, why", [
    (lambda c: c, {}, "say which hands hold the weapon"),
    (lambda c: c, {"hands": "both"}, "say which hands hold the weapon"),
    (lambda c: {k: v for k, v in c.items() if k != "sword"}, {"hands": "two"}, "carries no weapon path"),
    (lambda c: dict(c, rig="R15"), {"hands": "two"}, "it is a R15 clip"),
    (lambda c: {k: v for k, v in c.items() if k != "rig"}, {"hands": "two"}, "it is a None clip"),
    (lambda c: dict(c, sword=dict(c["sword"], edge=c["sword"]["edge"][:-1])), {"hands": "right"},
     "the weapon's edge track has 51 frame.s. and the clip 52"),
    (lambda c: c, {"hands": "right", "at": {"left": 0.2}}, 'names a hand the grip "right" does not use'),
    (lambda c: c, {"hands": "two", "at": {"left": "low"}}, '"at" is'),
    (lambda c: c, {"hands": "two", "at": []}, '"at" is'),
    (lambda c: c, {"hands": "two", "max_slide": 9}, "max_slide is studs, from 0 to 3.2"),
])
def test_what_cannot_be_solved_is_refused_by_name(change, kw, why):
    with pytest.raises(ValueError, match=why):
        G.solve(change(loved()), **kw)


def test_the_clips_own_hands_are_used_when_the_op_says_none():
    c = dict(let_go(loved()), hands="two")
    solved, r = G.solve(c)
    assert r["hands"] == "two" and r["worst_after"] == 0.0


def test_it_is_an_op_of_a_derive_recipe_and_a_command(tmp_path, monkeypatch, capsys):
    src = tmp_path / "Base.clip.json"
    src.write_text(json.dumps(let_go(loved())), encoding="utf-8")
    monkeypatch.setattr(D, "load_clip", lambda name: json.load(open(str(src), encoding="utf-8")))
    out = D.derive({"name": "Held", "from": "Base", "ops": [{"op": "grip", "hands": "two"}]})
    clip = out[0] if isinstance(out, tuple) else out
    assert clip["name"] == "Held" and clip["hands"] == "two" and IH.read(clip)["loose"] == []
    with pytest.raises(ValueError, match="say which hands hold the weapon"):
        D.derive({"name": "Bad", "from": "Base", "ops": [{"op": "grip"}]})
    capsys.readouterr()
    assert G.main([str(src), "--hands", "two"]) == 0
    said = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "nothing written: no --out" in said["summary"] and said["report"]["worst_after"] == 0.0
    dst = tmp_path / "held.clip.json"
    assert G.main([str(src), "--hands", "two", "--out", str(dst)]) == 0
    assert IH.read(json.load(open(str(dst), encoding="utf-8")))["loose"] == []
    assert G.main([str(src)]) == 1 and "not solved" in capsys.readouterr().out


# ---------------------------------------------------------------- the one review, 2026-11-15
def test_a_weapon_track_of_another_length_is_refused_before_anything_moves():
    """two built clips had an edge track shorter than the clip: the right arm was solved, the weapon's joint track
    could not be made again and the OLD one stayed - the blade exported 1.2 and 4.2 studs off the hand, unsaid"""
    c = let_go(loved(), "Right Arm")
    c["sword"]["edge"] = c["sword"]["edge"][:-3]
    before = copy.deepcopy(c)
    with pytest.raises(ValueError, match="the weapon's edge track has 49 frame.s. and the clip 52"):
        G.solve(c, "right")
    assert c == before


def test_a_throw_never_caught_and_a_draw_are_not_solved_at_the_clips_own_end():
    c = let_go(loved())
    n = len(c["times"])
    thrown = copy.deepcopy(c)
    thrown["events"] = thrown["events"] + [{"name": "Throw", "t": 30 / 60}]
    for i in range(31, n):                                       # the weapon flies off: nobody could reach it
        for k in ("grip_path", "tip"):
            thrown["sword"][k][i] = [thrown["sword"][k][i][0], thrown["sword"][k][i][1], thrown["sword"][k][i][2] - 0.4 * (i - 30)]
    solved, r = G.solve(thrown, "two")                           # (was refused: "does not reach ... frame 51")
    for i in range(38, n):
        assert solved["joints"]["Left Arm"]["frames"][i] == thrown["joints"]["Left Arm"]["frames"][i]
    assert along(solved, "Left Arm", 20)[1] < 1e-3 and IH.read(solved)["loose"] == []
    drawn = copy.deepcopy(c)
    drawn["events"] = drawn["events"] + [{"name": "Draw", "t": 10 / 60}]
    solved, r = G.solve(drawn, "two")
    for i in range(0, 4):                                        # before the draw the hand is not on the weapon: left alone
        assert solved["joints"]["Left Arm"]["frames"][i] == drawn["joints"]["Left Arm"]["frames"][i]
    assert along(solved, "Left Arm", 20)[1] < 1e-3


def test_an_arm_thrown_half_a_circle_off_does_not_pop_and_a_solve_that_would_is_refused():
    """the short way round flips an arm's roll when the turn nears half a circle: +133 degrees a frame was measured"""
    worst, refused = 0.0, 0
    for name in ("Katana1Kesa", "GsCombo1SideLeft", "GsCombo3Overhead", "Katana3Makko"):
        c = loved(name)
        for arm in ("Left Arm", "Right Arm"):
            bad = copy.deepcopy(c)
            h = math.radians(150) / 2
            for i in range(len(bad["times"])):
                f = bad["joints"][arm]["frames"][i]
                bad["joints"][arm]["frames"][i] = list(D.qmul(np.array([0, math.sin(h), 0, math.cos(h)]), np.array(f[:4]))) + list(f[4:7])
            GR.add_grip(bad)
            try:
                solved, r = G.solve(bad, "two")
            except ValueError as e:
                refused += 1
                assert "would jump" in str(e) or "does not reach" in str(e) or "studs into" in str(e), str(e)
                continue
            grew = G._turns(solved["joints"][arm]["frames"]) - G._turns(c["joints"][arm]["frames"])
            worst = max(worst, float(grew.max()))
    assert worst < G.POP and refused < 8                         # some solve, none of them jumps


def test_a_left_hand_put_on_goes_behind_the_right_and_does_not_jump_as_the_right_slides():
    far = {"right": 0.0, "left": 1.0}                            # the right holds; the left is let go
    P = lambda right, left, off=far: G._places("two", None, {"right": right, "left": left}, off, 3.6, 0.5)
    last = None
    for k in range(0, 60):                                       # the right hand slides back along the hilt
        right = 0.4 - 0.025 * k
        got = P(right, 2.0)
        assert got["right"] == pytest.approx(max(right, -IH.BEHIND))
        assert got["left"] <= got["right"] - G.APART + 1e-9 or got["left"] == pytest.approx(-IH.BEHIND)
        if last is not None:
            assert abs(got["left"] - last["left"]) < 0.03
        last = got
    assert P(0.25, 2.0)["left"] == pytest.approx(-0.25)          # room enough: the loved place
    # a left hand that already HOLDS keeps its own place, ahead of the right or not - 0.54 and 0.56 alike (the first
    # cut threw it 0.69 studs across the right hand between those two)
    on = {"right": 0.0, "left": 0.0}
    assert P(0.2, 0.54, on)["left"] == pytest.approx(0.54) and P(0.2, 0.56, on)["left"] == pytest.approx(0.56)
    got = G._places("two", {"left": 0.9}, {"right": 0.2, "left": 0.0}, far, 3.6, 0.5)
    assert got == {"right": 0.2, "left": 0.9}                    # "at" says a place, whatever the order


def test_a_hand_that_holds_the_blade_is_not_dragged_to_the_hilt():
    c = let_go(loved())                                          # the left hand off; put it 0.9 studs up, past the hilt
    held, _ = G.solve(c, "two", at={"left": 0.9}, max_slide=3.2)
    assert abs(along(held, "Left Arm", 20)[0] - 0.9) < 1e-3 and 0.9 > G.HILT
    again, r = G.solve(held, "two", max_slide=3.2)               # it holds there, ahead of the right: nothing is moved
    assert r["moved"] == 0 and again["joints"]["Left Arm"] == held["joints"]["Left Arm"]


def test_the_arc_is_right_where_it_is_hard():
    x, y = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    assert np.allclose(G._arc(x, x), np.eye(3))
    tiny = np.array([1.0, 5e-9, 0])
    assert np.allclose(G._arc(x, tiny) @ x, x, atol=1e-6)        # (a turn of 5e-9 rad once came out as half a circle)
    assert np.allclose(G._arc(x, -x) @ x, -x, atol=1e-9)         # straight back: half a circle about some side
    near = np.array([-1.0, 1e-10, 0])
    assert np.allclose(G._arc(x, near) @ x, near / np.linalg.norm(near), atol=1e-6)
    assert np.allclose(G._arc(x, y, 0.5) @ x, np.array([1, 1, 0]) / math.sqrt(2), atol=1e-9)
    assert np.allclose(G._arc(x, -x, 0.5) @ x @ x, 0.0, atol=1e-9)        # half of half a circle: at right angles


def test_the_slide_bound_holds_whatever_the_arm_already_was():
    c = let_go(loved())
    for cap in (2.5, 2.0):
        try:
            solved, _ = G.solve(c, "two", max_slide=cap)
        except ValueError as e:
            assert "does not reach" in str(e)
            continue
        slid = max(float(np.linalg.norm(f[4:7])) for f in solved["joints"]["Left Arm"]["frames"])
        assert slid <= cap + 1e-4

