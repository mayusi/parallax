"""kit/anim/in_hand.py - THE WEAPON IN A HAND AT EVERY FRAME (the owner's method lists 2026-11-13: attachment sockets):
a built clip whose weapon is out of both hands with no toss declared by its own events is a problem of the clip, in
the build's motion gates (kit/anim/metrics.py). The clip is a cut the owner loved, generated in memory (read only)."""
import copy
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import in_hand as IH        # noqa: E402
import metrics as MT        # noqa: E402
import strike as S          # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")


def kesa():
    with open(LOVED, encoding="utf-8") as fh:
        return S.generate(json.load(fh))[0]


def thrown(c, a=10, b=14, far=1.0):
    """the weapon lifted `far` studs off the hands for frames a..b (its whole track: grip and tip)"""
    c = copy.deepcopy(c)
    for k in ("tip", "grip_path"):
        for i in range(a, b + 1):
            c["sword"][k][i] = [c["sword"][k][i][0], c["sword"][k][i][1] + far, c["sword"][k][i][2]]
    return c


def test_a_loved_cut_keeps_its_sword_in_the_hands_at_every_frame():
    r = IH.read(kesa())
    assert r["weapon"] and r["loose"] == [] and r["windows"] == [] and r["worst"] < 0.05
    assert IH.words(r, "Katana1Kesa") == "the weapon is in a hand at every frame of Katana1Kesa"


def test_a_weapon_out_of_both_hands_is_named_with_its_frames():
    r = IH.read(thrown(kesa()))
    (a, b, far, k), = r["loose"]
    assert (a, b) == (10, 14) and 0.7 < far <= 1.0 and a <= k <= b and r["worst"] == far     # (the gap to the weapon's LINE)
    w = IH.words(r, "Katana1Kesa")
    assert w.startswith(f"the weapon is in NO hand for 5 frame(s) of Katana1Kesa with no toss or draw declared: {far} studs")
    assert f"at frame {k} ({k / 60:.2f} s; frames 10-14)" in w
    assert IH.read(thrown(kesa(), far=0.08))["loose"] == [] and IH.LOOSE == 0.1                # inside the bar: in the hand
    assert IH.read(thrown(kesa(), far=0.29))["loose"]                         # (the first bar, 0.3, let this through)


def test_a_toss_the_clip_declares_is_meant():
    c = thrown(kesa())
    c["events"] = c["events"] + [{"name": "Toss", "t": 9 / 60}, {"name": "Catch", "t": 15 / 60}]
    r = IH.read(c)
    assert r["loose"] == [] and r["windows"] == [[9, 15]]
    assert "out of the hands by its own events for 1 stretch(es): frames 9-15" in IH.words(r, "Katana1Kesa")
    late = thrown(kesa())
    late["events"] = late["events"] + [{"name": "Toss", "t": 12 / 60}, {"name": "Catch", "t": 15 / 60}]
    assert [x[:2] for x in IH.read(late)["loose"]] == [[10, 11]]             # out of the hand BEFORE the toss it declares
    never = thrown(kesa(), 40, 51)
    never["events"] = never["events"] + [{"name": "SwordThrow", "t": 39 / 60}]
    assert IH.read(never)["loose"] == [] and IH.read(never)["windows"] == [[39, 51]]    # thrown and not caught: to the end


def test_a_draw_starts_with_the_weapon_out_of_the_hand():
    c = thrown(kesa(), 0, 7)
    c["events"] = c["events"] + [{"name": "GunsOut", "t": 8 / 60}]
    assert IH.read(c)["loose"] == [] and IH.read(c)["windows"] == [[0, 8]]
    hit_only = thrown(kesa(), 0, 7)                                           # a Hit says nothing about the weapon
    assert [x[:2] for x in IH.read(hit_only)["loose"]] == [[0, 7]]


def test_a_hand_along_the_blade_is_holding_it():
    c = kesa()
    import numpy as np
    for i in range(len(c["sword"]["tip"])):                                   # the grip point slid 2 studs back along the
        g, t = np.array(c["sword"]["grip_path"][i]), np.array(c["sword"]["tip"][i])    # blade: the hands now sit ON the blade
        ax = (t - g) / np.linalg.norm(t - g)
        c["sword"]["grip_path"][i] = (g - 2.0 * ax).tolist()
    assert IH.read(c)["loose"] == []
    beyond = kesa()
    for i in range(len(beyond["sword"]["tip"])):                              # ... but not past its pommel
        g, t = np.array(beyond["sword"]["grip_path"][i]), np.array(beyond["sword"]["tip"][i])
        ax = (t - g) / np.linalg.norm(t - g)
        beyond["sword"]["grip_path"][i] = (g + 2.0 * ax).tolist()
    assert IH.read(beyond)["loose"]


def test_a_clip_with_no_weapon_has_nothing_to_hold_and_an_r15_clip_is_refused():
    c = kesa()
    c.pop("sword")
    assert IH.read(c)["weapon"] is False and "carries no weapon" in IH.words(IH.read(c), "Bare")
    assert IH.gate(c) == (None, None)
    r15 = kesa()
    r15["rig"] = "R15"
    with pytest.raises(ValueError, match="R15 clip"):
        IH.read(r15)
    assert IH.gate(r15) == (None, None)


def test_the_builds_motion_gates_fail_a_loose_weapon_and_say_how(tmp_path, capsys):
    good, bad = tmp_path / "Good.clip.json", tmp_path / "Loose.clip.json"
    good.write_text(json.dumps(kesa()), encoding="utf-8")
    loose = thrown(kesa())
    loose["name"] = "Loose"
    bad.write_text(json.dumps(loose), encoding="utf-8")
    assert MT.main([str(good)]) == 0
    assert json.load(open(str(tmp_path / "Good.metrics.json")))["in_hand"]["loose"] == []
    capsys.readouterr()
    assert MT.main([str(bad)]) == 1
    v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "the weapon is in NO hand for 5 frame(s) of Loose" in v["summary"] and "Toss / Pass ... Catch" in v["next_action"]


def test_a_clip_made_before_the_rule_is_said_not_failed(tmp_path, capsys):
    anims = tmp_path / "anims"
    (anims / "blocks").mkdir(parents=True)
    loose = thrown(kesa())
    loose["name"] = "OldLoose"
    loose["source"] = {"kind": "move", "file": str(anims / "OldLoose.move.json")}
    held, problem = IH.gate(loose)
    assert problem and held["loose"]
    (anims / "blocks" / IH.BEFORE).write_text(json.dumps({"frozen": "2026-11-13", "clips": ["OldLoose"]}))
    held, problem = IH.gate(loose)
    assert problem is None and held["made_before_the_rule"] is True
    p = tmp_path / "OldLoose.clip.json"
    p.write_text(json.dumps(loose), encoding="utf-8")
    assert IH.main([str(p), "--before", str(anims / "blocks" / IH.BEFORE)]) == 0
    assert "NOT HELD (a clip made before the rule)" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    assert IH.main([str(p)]) == 1                                             # with no list it fails, as a new clip does
    (anims / "blocks" / IH.BEFORE).write_text("{not json")
    with pytest.raises(ValueError, match="never delete it"):
        IH.before(str(anims / "blocks" / IH.BEFORE))
    held, problem = IH.gate(loose)                                           # a list that cannot be read excuses nobody
    assert problem and "could not be read" in problem


def test_freeze_lists_what_fails_today_once(tmp_path):
    built = tmp_path / "build"
    built.mkdir()
    for name, clip in (("Fine", kesa()), ("Loose", thrown(kesa())), ("Loose.polish", thrown(kesa()))):
        clip["name"] = name.split(".")[0]
        (built / f"{name}.clip.json").write_text(json.dumps(clip), encoding="utf-8")
    out = str(tmp_path / "blocks" / IH.BEFORE)
    assert IH.freeze(str(built), out, today="2026-11-13") == ["Loose"]         # (a preview or polish pass is not a move's clip)
    assert json.load(open(out))["clips"] == ["Loose"] and IH.before(out) == {"Loose"}
    with pytest.raises(ValueError, match="frozen once and never extended"):
        IH.freeze(str(built), out)


def test_what_cannot_be_read_is_refused_in_one_line(tmp_path, capsys):
    p = tmp_path / "x.json"
    p.write_text("{not json")
    assert IH.main([str(p)]) == 1
    assert "could not be read" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    short = kesa()
    short["sword"]["tip"] = short["sword"]["tip"][:5]                         # a weapon track shorter than the clip
    held, problem = IH.gate(short)                                            # a retime that left the weapon behind
    assert problem and "track has 5 frame(s) and the clip 52" in problem
    broken = kesa()
    broken["sword"]["tip"][3] = "not a point"
    held, problem = IH.gate(broken)
    assert problem and "could not be read" in problem and "error" in held


# ---- what the stage's review found (2026-11-14) ----
@pytest.mark.parametrize("name, t", [("Shout", 0.8), ("Timeout", 0.8), ("MagOut", 0.8), ("Withdraw", 0.8), ("CoinToss", 0.0),
                                     ("Bypass", 0.0), ("Passive", 0.0), ("Dropkick", 0.0), ("Catch", 9.0), ("Toss", -3.0)])
def test_an_event_that_only_sounds_like_a_toss_frees_nothing(name, t):
    c = thrown(kesa())
    c["events"] = c["events"] + [{"name": name, "t": t}]
    r = IH.read(c)
    assert r["windows"] == [] and [x[:2] for x in r["loose"]] == [[10, 14]]


def test_two_tosses_need_two_catches_and_another_weapons_event_closes_nothing():
    n, fps = 60, 60.0
    ev = lambda *pairs: {"events": [{"name": a, "t": f / fps} for a, f in pairs]}       # noqa: E731
    assert IH.windows(ev(("Toss", 14), ("Toss", 28), ("Catch", 38), ("Catch", 52)), n, fps) == [[14, 52]]
    assert IH.windows(ev(("GunsOut", 8), ("Catch", 34)), n, fps) == [[0, 34]]              # a draw: to the last "back"
    assert IH.windows(ev(("SwordThrow", 15), ("SwordOnBack", 50), ("GunsOut", 55)), n, fps) == [[15, 59]]
    assert IH.windows(ev(("SwordToss", 5), ("SwordCaught", 11)), n, fps) == [[5, 11]]
    assert IH.windows(ev(("Toss", 5), ("Catch", 11), ("Toss", 20), ("Catch", 30)), n, fps) == [[5, 11], [20, 30]]
    assert IH.windows(ev(("Catch", 11)), n, fps) == [[0, 11]] and IH.windows(ev(("Hit", 11)), n, fps) == []


# ---------------------------------------------------------------- which hand (the limitations list, A-R08, 2026-11-15)
FAULTS = os.path.join(ROOT, "kit", "selftest", "anim", "faults")


def made(kind, name, **more):
    with open(os.path.join(FAULTS, kind, f"{name}.move.json"), encoding="utf-8") as fh:
        return S.generate({**json.load(fh), **more})[0]


def test_a_grip_that_is_said_is_held_to_and_the_reading_says_which_hands_were_on_the_weapon():
    import glob
    # every loved cut is two-handed: said so, both hands are on the weapon at every frame
    for path in sorted(glob.glob(os.path.join(FAULTS, "loved", "*.move.json"))):
        name = os.path.basename(path)[:-len(".move.json")]
        c = made("loved", name, hands="two")
        assert c["hands"] == "two"                                # the move's word rides on the clip
        r = IH.read(c)
        assert r["loose"] == [] and r["worst"] < 0.05 and r["on"] == {"right": r["frames"], "left": r["frames"]}, name
        assert IH.gate(c)[1] is None and IH.gate(c)[0]["hands"] == "two"
    # a one-handed move (a cut the owner rejected: the left hand is 4 studs off the hilt)
    spin = made("rejected", "DTDrillSpin4")
    assert "hands" not in spin and IH.read(spin)["loose"] == []    # unsaid: the nearer hand holds it, as before
    assert IH.read(spin)["on"]["left"] < IH.read(spin)["frames"]  # ... and the reading says the left was not on it
    two = dict(spin, hands="two", source=None)
    out, why = IH.gate(two)
    assert 'says its hands are "two" and both hands are not on the weapon' in why and "the left hand is" in why
    assert "studs off at frame" in why and 'say the hands it really has ("hands")' in why
    assert IH.gate(dict(spin, hands="right", source=None))[1] is None
    assert 'says its hands are "left" and the left hand is not on the weapon' in IH.gate(dict(spin, hands="left", source=None))[1]
    # a grip that is not one is a problem of the clip, not a crash of the build
    out, why = IH.gate(dict(spin, hands="both"))
    assert "error" in out and '"two", "right" or "left"' in why
    # a toss the clip declares is still meant, whatever the grip
    c = thrown(dict(kesa(), hands="two"))
    assert IH.gate(dict(c, source=None))[1] is not None
    c["events"] = c["events"] + [{"name": "Toss", "t": 9 / 60}, {"name": "Catch", "t": 15 / 60}]
    assert IH.gate(dict(c, source=None))[1] is None


def test_the_hands_a_clip_says_do_not_touch_the_weapons_own_joint_track(tmp_path):
    """the one review, 2026-11-15: a built weapon clip carries "grip" - the Handle joint's track, a list of frames
    (kit/anim/grip.py). The first cut of this stage used that key: 287 of 391 built armed clips could not be read"""
    import grip as GR
    c = made("loved", "Katana1Kesa", hands="two")
    GR.add_grip(c)
    assert isinstance(c["grip"], list) and len(c["grip"]) == len(c["times"]) and c["hands"] == "two"
    out, why = IH.gate(c)
    assert why is None and "error" not in out and out["hands"] == "two"
    plain = made("loved", "Katana1Kesa")
    GR.add_grip(plain)
    assert IH.gate(plain)[1] is None and IH.gate(plain)[0]["hands"] is None
    # the hand a failure names is the hand the clip says holds it
    spin = made("rejected", "DTDrillSpin4", hands="right")
    out, why = IH.gate(dict(thrown(spin), source=None))
    assert "the right hand is not on the weapon" in why and "the right hand is" in why and "the left hand is" not in why
    # frames truly on the weapon: a declared toss is not contact
    tossed = thrown(dict(kesa(), hands="two"))
    tossed["events"] = tossed["events"] + [{"name": "Toss", "t": 9 / 60}, {"name": "Catch", "t": 15 / 60}]
    r = IH.read(tossed)
    assert r["loose"] == [] and r["on"]["right"] == r["frames"] - 5
    # said on a clip with no weapon: said, not ignored; a word that is not one: a problem, not a crash
    bare = dict(kesa(), hands="two")
    bare.pop("sword")
    assert "carries no weapon to hold" in IH.gate(bare)[1]
    assert "its hands could not be read" in IH.gate(dict(bare, hands=["x"]))[1]
    # a clip on the frozen list that now SAYS its hands is held to them
    anims = tmp_path / "anims"
    (anims / "blocks").mkdir(parents=True)
    (anims / "blocks" / IH.BEFORE).write_text(json.dumps({"clips": ["DTDrillSpin4"]}), encoding="utf-8")
    src = {"file": str(anims / "DTDrillSpin4.move.json")}
    old = dict(thrown(made("rejected", "DTDrillSpin4")), source=src)
    assert IH.gate(old)[1] is None and IH.gate(old)[0]["made_before_the_rule"] is True
    assert IH.gate(dict(old, hands="two"))[1] is not None


def slid(c, studs=1.5):
    """the whole weapon slid `studs` back along its own axis through the fists (the hands end up the blade)"""
    import numpy as np
    c = copy.deepcopy(c)
    for i in range(len(c["times"])):
        g, t = np.array(c["sword"]["grip_path"][i], float), np.array(c["sword"]["tip"][i], float)
        ax = (t - g) / np.linalg.norm(t - g)
        c["sword"]["grip_path"][i], c["sword"]["tip"][i] = (g - studs * ax).tolist(), (t - studs * ax).tolist()
    return c


def flipped(c, a=10, b=14):
    """the weapon turned end for end on frames a..b: its tip where its grip was, its grip at the far end"""
    c = copy.deepcopy(c)
    for i in range(a, b + 1):
        c["sword"]["grip_path"][i], c["sword"]["tip"][i] = c["sword"]["tip"][i], c["sword"]["grip_path"][i]
    return c


def test_a_weapon_slid_through_the_fist_or_turned_end_for_end_is_not_held_by_its_hilt():
    """(the owner's V3 list, anim stage C.2; the old KNOWN LIMIT: the hand was measured to the weapon's LINE, so both
    of these read as held) - a holding hand past the hilt is on the BLADE, failed unless the clip says so"""
    ok = IH.read(kesa())
    assert ok["blade"] == [] and IH.gate(kesa())[1] is None
    for bad, frames in ((slid(kesa()), None), (flipped(kesa()), (10, 14))):
        bad["name"] = "Probe"
        r = IH.read(bad)
        assert r["loose"] == [] and r["blade"]                         # on the line: held, by the old reading
        if frames:
            assert {(x[0], x[1]) for x in r["blade"]} <= {(a, b) for a in range(frames[0], frames[1] + 1)
                                                         for b in range(frames[0], frames[1] + 1)}
        assert all(x[2] > IH.HILT_AHEAD for x in r["blade"])
        held, problem = IH.gate(bad)
        assert problem and "past the hilt" in problem and held["on_blade"]


def test_a_half_sword_grip_the_clip_says_is_held_and_one_made_before_the_rule_is_said(tmp_path):
    bad = slid(kesa())
    bad["name"] = "HalfSword"
    said = dict(bad, on_blade={"right": True, "left": [[0.0, 10.0]]})
    assert IH.read(said)["blade"] == [] and IH.gate(said)[1] is None
    part = dict(bad, on_blade={"right": True})                          # the left hand not said: still failed
    assert {x[4] for x in IH.read(part)["blade"]} == {"left"}
    with pytest.raises(ValueError, match='"on_blade"'):
        IH.read(dict(bad, on_blade={"both": True}))
    anims = tmp_path / "anims"
    (anims / "blocks").mkdir(parents=True)
    bad["source"] = {"kind": "move", "file": str(anims / "HalfSword.move.json")}
    assert IH.gate(bad)[1]
    (anims / "blocks" / IH.BLADE_BEFORE).write_text(json.dumps({"frozen": "2026-11-18", "clips": ["HalfSword"]}))
    held, problem = IH.gate(bad)
    assert problem is None and held["made_before_the_hilt_rule"] is True


def test_the_frozen_list_is_written_once_from_what_the_rule_fails(tmp_path):
    built = tmp_path / "built"
    built.mkdir()
    bad = slid(kesa())
    bad["name"] = "SlidOld"
    (built / "SlidOld.clip.json").write_text(json.dumps(bad), encoding="utf-8")
    (built / "Good.clip.json").write_text(json.dumps(kesa()), encoding="utf-8")
    out = tmp_path / "blocks" / IH.BLADE_BEFORE
    assert IH.freeze_blade(str(built), str(out)) == ["SlidOld"]
    with pytest.raises(ValueError, match="frozen once"):
        IH.freeze_blade(str(built), str(out))


def test_the_count_form_kit_anim_rearm_writes_is_read_as_its_hands():
    # (kit anim rearm --hands writes a COUNT: the hilt in the right hand, a second hand solved on at 2 - kit/anim/rearm.py.
    #  21 clips carry it; the gate refused it as unreadable and stopped the committed-tree bake, 2026-11-19)
    assert IH.hands_of({"hands": 2}) == "two"
    assert IH.hands_of({"hands": 1}) == "right"
    assert IH.hands_of({}) is None
    for bad in (0, 3, True, 1.5, "2"):
        try:
            IH.hands_of({"hands": bad})
        except ValueError:
            continue
        raise AssertionError(f"hands={bad!r} must stay unreadable")
