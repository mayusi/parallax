"""kit/anim/contact.py - when a strike meets its target, from the geometry, with a confidence (the owner's limitations
list 2026-11-15, A-R06). The labelled examples are the cuts the owner loved whose move files AUTHOR their Hit; the
delayed and the multiple impacts are those cuts and a rejected one. Generated in memory, read only."""
import copy
import glob
import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C         # noqa: E402
import contact as K      # noqa: E402
import pose_sheet as PS  # noqa: E402
import strike as S       # noqa: E402

FAULTS = os.path.join(ROOT, "kit", "selftest", "anim", "faults")
AUTHORED = ("GsCombo2SideRight", "GsCombo3Overhead", "GsCombo4Underhip", "Katana2GyakuKesa", "Katana3Makko")
INFERRED = ("GsCombo1SideLeft", "Katana1Kesa")


def move(kind, name):
    with open(os.path.join(FAULTS, kind, f"{name}.move.json"), encoding="utf-8") as fh:
        return json.load(fh)


def made(kind, name, **more):
    return S.generate({**move(kind, name), **more})[0]


def hit_frame(c):
    return round(next(e["t"] for e in c["events"] if e["name"] == "Hit") * c["fps"])


def top_speed_frame(c):
    tip = PS.paths(c, C.world_frames(c, C.load_rig("r6")))["BladeTip"]
    return int(np.argmax(np.linalg.norm(np.diff(tip, axis=0), axis=1))) + 1


# ---------------------------------------------------------------- the labelled examples
def test_the_fixtures_are_what_the_tests_take_them_for():
    for name in AUTHORED:
        assert any(e.get("name") == "Hit" for e in move("loved", name).get("events") or []), name
    for name in INFERRED:
        assert not (move("loved", name).get("events") or []), name


def test_on_the_authored_hits_the_geometry_is_within_two_frames_where_the_speed_peak_is_up_to_eight_off():
    off_geometry, off_speed = {}, {}
    for name in AUTHORED:
        c = made("loved", name)
        assert "hit_inferred" not in c                           # the author placed it: the builder says nothing
        r = K.read(c)
        h = r["hits"][0]
        assert h["frame"] == hit_frame(c) and h["backed"] is True and h["inferred"] is False, K.words(r, name)
        # the Hit's own confidence is the geometry and the speed behind it (its own event is no evidence for itself);
        # the CONTACT there has all three kinds of evidence
        assert h["confidence"] == 0.75
        assert [x["confidence"] for x in r["contacts"] if x["frame"] == h["nearest"]] == [1.0]
        off_geometry[name] = h["off_frames"]
        off_speed[name] = top_speed_frame(c) - hit_frame(c)
        # with the events taken away, the geometry still finds that frame: what a builder may now place
        found = K.infer(c)
        assert len(found) == 1 and abs(found[0][0] - hit_frame(c)) <= 2 and found[0][1] == 0.75
        assert found[0][2] == ["geometry", "speed"]
    assert all(abs(v) <= 2 for v in off_geometry.values()), off_geometry
    # MEASURED: the blade is fastest well before it arrives on three of the five (a delayed impact)
    assert off_speed["GsCombo3Overhead"] <= -6 and off_speed["GsCombo4Underhip"] <= -6 and off_speed["Katana3Makko"] <= -4, off_speed
    assert off_speed["GsCombo2SideRight"] == 0 and off_speed["Katana2GyakuKesa"] == 0


def test_a_hit_the_build_inferred_is_marked_and_the_geometry_backs_it_on_the_loved_cuts():
    for name in INFERRED:
        c = made("loved", name)
        assert c["hit_inferred"] == [e["t"] for e in c["events"] if e["name"] == "Hit"]       # WHICH Hit the build placed
        r = K.read(c)
        h = r["hits"][0]
        assert h["backed"] is True and h["off_frames"] == 0 and h["confidence"] == 0.75 and h["inferred"] is True
        assert all("authored" not in x["evidence"] for x in r["contacts"])                      # nobody authored it
        assert K.gate(c) == (K.gate(c)[0], None) and K.gate(c)[0]["inferred"] is True
        assert r["ambiguous"] == []
    # the move's own word for its target and its meant contacts rides on the clip
    c = made("loved", "Katana1Kesa", target=[0, 0, -3.5], contact=[{"a": "weapon", "b": "Torso"}])
    assert c["target"] == [0, 0, -3.5] and c["contact"] == [{"a": "weapon", "b": "Torso"}]
    assert K.read(c)["target"] == [0.0, 0.0, -3.5]


# ---------------------------------------------------------------- delayed, multiple, none
def test_a_delayed_impact_an_inferred_hit_at_the_speed_peak_fails_and_an_authored_one_is_said():
    c = made("loved", "GsCombo3Overhead")
    peak = top_speed_frame(c)
    assert hit_frame(c) - peak >= 6
    early = copy.deepcopy(c)
    early["events"] = [{"name": "Hit", "t": peak / c["fps"]}]
    early["hit_inferred"] = True                                 # what the old inference did: the Hit at the fastest frame
    out, why = K.gate(early)
    h = out["hits"][0]
    assert h["backed"] is False and h["frame"] == peak and h["off_frames"] <= -5
    assert f"Hit is at frame {peak} and the weapon meets the target at frame {h['nearest']}" in why
    assert "frame(s) later" in why and "author it" in why and "\"target\"" in why
    # the same Hit placed by the AUTHOR: the author's word stands, the reading says the geometry does not back it
    authored = dict(early)
    authored.pop("hit_inferred")
    out, why = K.gate(authored)
    assert why is None and out["hits"][0]["backed"] is False and out["inferred"] is False
    # an authored event is evidence only when the author placed it: an inferred Hit never backs itself
    r = K.read(early)
    assert all("authored" not in x["evidence"] for x in r["contacts"])


def test_several_impacts_are_each_a_contact_and_a_pass_with_no_event_is_said():
    spin = made("rejected", "DTDrillSpin4")
    r = K.read(spin)
    met = [x for x in r["contacts"] if "geometry" in x["evidence"]]
    assert len(met) == 4 and len(r["hits"]) == 1
    assert all(b["frame"] - a["frame"] >= 10 for a, b in zip(met, met[1:]))      # one a turn of the spin
    assert any("4 contacts" in a and "1 Hit event(s)" in a for a in r["ambiguous"])
    assert r["hits"][0]["backed"] is False                        # its one Hit is not at any of them
    assert [f for f, _, _ in K.infer(spin)] == [x["frame"] for x in met]


def test_a_strike_that_never_reaches_its_target_is_a_speed_peak_and_says_so():
    c = made("loved", "Katana1Kesa", target=[0, 0, -12])
    r = K.read(c)
    assert all(x["evidence"] == ["speed"] and x["confidence"] == 0.25 for x in r["contacts"]) and r["contacts"]
    assert r["hits"][0]["nearest"] is None and r["hits"][0]["confidence"] == 0.0
    assert any("never comes within 1.2 studs of the target's chest" in a for a in r["ambiguous"])
    assert any("a speed peak, not a contact" in a for a in r["ambiguous"])
    # a WEAPON's Hit the build placed, with no contact at all, fails: fastest somewhere, never at the target
    assert c["hit_inferred"] and "never arrives within 1.2 studs" in K.gate(c)[1]
    said = dict(c)
    said.pop("hit_inferred")
    assert K.gate(said)[1] is None                                # the same Hit AUTHORED: the author's word stands
    bare = dict(c)
    bare.pop("sword")
    assert K.gate(bare)[1] is None                                # unarmed: a limb's target is not known well enough to fail on
    assert K.infer(c)[0][2] == ["speed"]                          # the old method is what is left, said as such
    # a blade resting in its guard, pointed at a target that stands in it, is no hit: nothing strikes there
    guard = made("loved", "GsCombo4Underhip")
    assert all(x["frame"] > 10 for x in K.read(guard)["contacts"] if "geometry" in x["evidence"])
    for bad in ("ahead", [0, 0], [0, 0, float("nan")], [True, 0, 0]):
        with pytest.raises(ValueError, match="\"target\" is \\[x, y, z\\]"):
            K.read(dict(c, target=bad))


def test_the_target_of_a_move_that_travels_stands_ahead_of_where_the_body_gets_to():
    c = made("loved", "Katana1Kesa")
    n = len(c["times"])
    assert K.target_of(c).tolist() == [0.0, 0.0, -3.0]
    lunge = dict(c, root=[[0, 0, 0, 1, 0, 0, -4.0 * i / (n - 1)] for i in range(n)])
    # only the travel UP TO the strike counts (the body runs on after its Hit at frame 26 of 51)
    assert K.target_of(lunge).tolist() == pytest.approx([0.0, 0.0, -4.0 * hit_frame(c) / (n - 1) - 3.0])
    assert K.target_of(dict(lunge, events=[])).tolist() == pytest.approx([0.0, 0.0, -7.0])      # no strike named: all of it
    assert K.target_of(dict(lunge, warp={"from": 0.0, "to": 10 / c["fps"]})).tolist() == pytest.approx([0.0, 0.0, -4.0 * 10 / (n - 1) - 3.0])
    back = dict(c, root=[[0, 0, 0, 1, 0, 0, (-2.0 if i <= hit_frame(c) else 6.0) * min(1.0, i / hit_frame(c))] for i in range(n)])
    assert K.target_of(back).tolist() == pytest.approx([0.0, 0.0, -5.0])                         # a leap back after the Hit is not where the target stood
    with pytest.raises(ValueError, match="its root track has 3 frame"):
        K.read(dict(c, root=[[0, 0, 0, 1, 0, 0, 0]] * 3))
    h = np.pi / 4                                                # a body that ends turned a quarter turn to the left
    turned = dict(c, events=[], root=[[0, np.sin(h), 0, np.cos(h), -2.0 * i / (n - 1), 0, 0] for i in range(n)])
    assert K.target_of(turned).tolist() == pytest.approx([-5.0, 0.0, 0.0], abs=1e-9)
    assert K.target_of(dict(lunge, target=[1, 2, 3])).tolist() == [1.0, 2.0, 3.0]


def test_an_unarmed_strike_is_read_on_the_limb_that_strikes():
    c = made("loved", "Katana1Kesa")
    bare = copy.deepcopy(c)
    bare.pop("sword")
    r = K.read(bare)
    assert r["striker"] in K.LIMBS
    assert K.read(bare, "Left Leg")["striker"] == "Left Leg"
    named = dict(bare, events=[{"name": "Kick", "t": 0.4, "by": "Right Leg"}])
    assert K.read(named)["striker"] == "Right Leg"
    with pytest.raises(ValueError, match="is no limb of this body"):
        K.read(bare, "Tail")
    with pytest.raises(ValueError, match="R15 clip"):
        K.read(dict(c, rig="R15"))


# ---------------------------------------------------------------- the gate
def test_the_gate_reads_a_characters_one_shot_with_a_hit_and_says_a_clip_made_before_the_rule(tmp_path, capsys):
    c = made("loved", "GsCombo3Overhead")
    for skipped in (dict(c, rig="R15"), dict(c, prop="Chest"), dict(c, loop=True), dict(c, events=[]), dict(c, events=[{"name": "Swing", "t": 0.1}])):
        assert K.gate(skipped) == (None, None)
    out, why = K.gate(dict(c, target="there"))
    assert "error" in out and "could not be read" in why
    early = dict(copy.deepcopy(c), events=[{"name": "Hit", "t": top_speed_frame(c) / c["fps"]}], hit_inferred=True, name="Old")
    anims = tmp_path / "anims"
    (anims / "blocks").mkdir(parents=True)
    early["source"] = {"file": str(anims / "Old.move.json")}
    assert K.gate(early)[1] is not None
    (anims / "blocks" / K.BEFORE).write_text(json.dumps({"clips": ["Old"]}), encoding="utf-8")
    out, why = K.gate(early)
    assert why is None and out["made_before_the_rule"] is True
    (anims / "blocks" / K.BEFORE).write_text("[]", encoding="utf-8")
    assert "could not be read" in K.gate(early)[1]
    # the freeze counts every Hit as maybe inferred (the clips built before the builders said which they placed)
    built = tmp_path / "built"
    built.mkdir()
    unmarked = dict(early, name="Unmarked")
    unmarked.pop("hit_inferred")
    for name, clip in (("Fine", c), ("Unmarked", unmarked), ("Unmarked.tune", unmarked)):
        (built / f"{name}.clip.json").write_text(json.dumps(dict(clip, name=name)), encoding="utf-8")
    lst = tmp_path / "out" / K.BEFORE
    assert K.main(["freeze", str(built), "--out", str(lst)]) == 0
    assert json.loads(lst.read_text(encoding="utf-8"))["clips"] == ["Unmarked"]
    assert K.main(["freeze", str(built), "--out", str(lst)]) == 1 and "frozen once" in capsys.readouterr().out
    p = tmp_path / "one.clip.json"
    p.write_text(json.dumps(early), encoding="utf-8")
    assert K.main([str(p)]) == 1
    v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert v["status"] == "fail" and "meets the target at frame" in v["summary"] and v["reading"]["striker"] == "weapon"


def test_the_builds_motion_gates_carry_it(tmp_path, capsys):
    import metrics as MT
    c = made("loved", "GsCombo3Overhead")
    src = {"kind": "move", "file": str(tmp_path / "anims" / "X.move.json")}
    early = dict(copy.deepcopy(c), events=[{"name": "Hit", "t": top_speed_frame(c) / c["fps"]}], hit_inferred=True)
    for name, clip, fails in (("Fine", c, False), ("Early", early, True)):
        p = tmp_path / f"{name}.clip.json"
        p.write_text(json.dumps(dict(clip, name=name, source=src)), encoding="utf-8")
        code = MT.main([str(p)])
        capsys.readouterr()
        m = json.loads((tmp_path / f"{name}.metrics.json").read_text(encoding="utf-8"))
        assert m["contact"]["striker"] == "weapon" and m["contact"]["inferred"] is fails
        hit = [x for x in m["problems"] if "meets the target at frame" in x]
        assert (code != 0 and len(hit) == 1) if fails else (not hit)


def test_every_fixture_can_be_read():
    for kind in ("loved", "rejected"):
        for path in sorted(glob.glob(os.path.join(FAULTS, kind, "*.move.json"))):
            r = K.read(made(kind, os.path.basename(path)[:-len(".move.json")]))
            assert r["contacts"] and all(0.0 <= x["confidence"] <= 1.0 for x in r["contacts"])


# ---------------------------------------------------------------- what the one review found (2026-11-15)
def test_a_contact_is_an_arrival_never_where_the_strike_starts_and_the_first_frame_of_a_hold():
    c = made("loved", "Katana1Kesa")
    r = K.read(c)
    at = next(x["frame"] for x in r["contacts"] if "geometry" in x["evidence"])
    # a hit-stop: the contact pose held for 6 frames - the contact is its FIRST frame (the arrival), not its last
    held = copy.deepcopy(c)
    n = len(c["times"])
    order = list(range(at + 1)) + [at] * 6 + list(range(at + 1, n))
    for j in held["joints"].values():
        j["frames"] = [j["frames"][i] for i in order]
    for k in ("tip", "grip_path", "edge"):
        held["sword"][k] = [held["sword"][k][i] for i in order]
    held["times"] = [i / c["fps"] for i in range(len(order))]
    assert [x["frame"] for x in K.read(held)["contacts"] if "geometry" in x["evidence"]] == [at]
    # a blade held out at the target from the first frame (a guard, a stab held): frame 0 is no arrival
    still = copy.deepcopy(c)
    for j in still["joints"].values():
        j["frames"] = [j["frames"][at]] * 5 + j["frames"][5:]
    for k in ("tip", "grip_path", "edge"):
        still["sword"][k] = [still["sword"][k][at]] * 5 + still["sword"][k][5:]
    assert all(x["frame"] != 0 for x in K.read(still)["contacts"])


def test_the_tolerances_are_times_not_frames_and_authorship_is_per_hit():
    c = made("loved", "GsCombo3Overhead")
    peak = top_speed_frame(c)
    geo = next(x["frame"] for x in K.read(c)["contacts"] if "geometry" in x["evidence"])
    # two Hits: the author's own (where the blade lands) and one the build placed at the speed peak - only the
    # placed one is judged, and only the author's is evidence
    both = dict(copy.deepcopy(c), events=[{"name": "Hit", "t": peak / c["fps"]}, {"name": "Hit", "t": geo / c["fps"]}],
                hit_inferred=[peak / c["fps"]])
    r = K.read(both)
    assert [h["inferred"] for h in r["hits"]] == [True, False]
    assert [h["frame"] for h in K.off(r)] == [peak] and "Hit is at frame" in K.gate(both)[1]
    assert "authored" in next(x for x in r["contacts"] if x["frame"] == geo)["evidence"]
    # the same clip at 30 frames a second: the same stretch of time is half the frames
    half = copy.deepcopy(c)
    keep = list(range(0, len(c["times"]), 2))
    half["fps"] = c["fps"] / 2
    half["times"] = [c["times"][i] for i in keep]
    for j in half["joints"].values():
        j["frames"] = [j["frames"][i] for i in keep]
    for k in ("tip", "grip_path", "edge"):
        half["sword"][k] = [half["sword"][k][i] for i in keep]
    h60 = dict(copy.deepcopy(c), events=[{"name": "Hit", "t": (geo - 4) / c["fps"]}], hit_inferred=True)
    h30 = dict(half, events=[{"name": "Hit", "t": (geo - 4) / c["fps"]}], hit_inferred=True)
    assert K.gate(h60)[1] is not None                             # 4 frames off at 60 a second: over the 3 allowed
    assert K.gate(h30)[1] is not None                             # the same time off at 30: 2 frames, and still over
