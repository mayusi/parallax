"""kit/anim/set_design.py (the animation studio route's A1): a string of attacks designed as ONE page before any of
them is posed - the design whole, two attacks too alike named cousins (by design, and by measure once their keys
exist), the keys held to the design, the owner's yes to the design as it is on the page he saw, and the lock on a new
move of the set. The moves are the kit's own fixtures (cuts the owner loved, read only); designs, pages and records
go to temp folders."""
import copy
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import set_design as SD     # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved")
KESA, GYAKU, MAKKO = (os.path.join(LOVED, f"{n}.move.json") for n in ("Katana1Kesa", "Katana2GyakuKesa", "Katana3Makko"))
DAY = "2026-11-13"
NONE = {"approved": None, "history": []}


def attack(name, cut, height="mid", body="plant", nxt=(), move=None, frames=(26, 1, 24), intent="proper"):
    a = {"name": name, "cut": cut, "height": height, "body": body, "intent": intent,
         "frames": {"windup": frames[0], "active": frames[1], "recovery": frames[2]},
         "ends": "the blade low on the far side, the weight forward", "next": list(nxt)}
    if move:
        a["move"] = move
    return a


def trio(moves=True):
    """the loved katana string as a design (its cuts as its keys measure them)"""
    return {"schema": 1, "set": "Probe", "weapon": "katana", "links": "pose",
            "attacks": [attack("Katana1Kesa", "left", body="step_in", nxt=["Katana2GyakuKesa"], move=KESA if moves else None),
                        attack("Katana2GyakuKesa", "right", nxt=["Katana3Makko"], move=GYAKU if moves else None, frames=(24, 1, 24)),
                        attack("Katana3Makko", "down", body="lunge", move=MAKKO if moves else None, frames=(28, 1, 21),
                               intent="aggressive")]}


def remade(tmp_path, yaw=8.0, shift=0.2, name="Reskin.move.json", lift=0.0):
    """the loved kesa with every key turned and its grip moved (lift: the whole cut raised or lowered): the same cut again"""
    with open(KESA, encoding="utf-8") as fh:
        m = json.load(fh)
    for k in m["keys"]:
        k["yaw"] = float(k.get("yaw", 0.0)) + yaw
        if "grip" in k:
            k["grip"] = [k["grip"][0] + shift, k["grip"][1] + shift + lift, k["grip"][2]]
    path = str(tmp_path / name)
    with open(path, "w") as fh:
        json.dump(m, fh)
    return path


def write(tmp_path, d, name="Probe"):
    designs = str(tmp_path / "designs")
    SD.save_json(SD.design_path(designs, name), d)
    return designs


def say_yes(tmp_path, d, rec=None, words="yes, that string", name="page.png"):
    """the page drawn, then his yes to it (what --approve does)"""
    r = SD.check(d)
    png = SD.page(d, r, rec or copy.deepcopy(NONE), str(tmp_path / name))
    return SD.approve(d, rec or copy.deepcopy(NONE), words, "owner", r["id"], today=DAY, result=r, page_png=png)


# ---------------------------------------------------------------- the design against itself
def test_a_new_design_is_a_draft_until_every_todo_is_gone():
    d = SD.template("Probe", 3, "katana")
    r = SD.check(d)
    assert not r["whole"] and len(r["problems"]) == 4 and all("still has TODO in" in p for p in r["problems"])
    assert r["problems"][0] == "the design still has TODO in links"
    assert d["attacks"][0]["next"] == ["Probe2"] and d["attacks"][2]["next"] == []
    st = SD.state_of(d, copy.deepcopy(NONE), r)
    assert st["state"] == "draft" and "not whole" in st["words"]
    with pytest.raises(ValueError, match="not whole cannot be approved"):
        SD.approve(d, copy.deepcopy(NONE), "yes", "owner", r["id"])
    named = trio(moves=False)
    named["attacks"][0]["name"] = "TODOroki"                  # a word that only contains the letters is not a TODO
    assert not any("TODO" in p for p in SD.check(named)["problems"])


def test_a_whole_design_with_no_keys_yet_passes_and_waits_for_him():
    d = trio(moves=False)
    r = SD.check(d)
    assert r["whole"] and r["problems"] == [] and r["measured"] == {}
    assert SD.state_of(d, copy.deepcopy(NONE), r)["state"] == "waiting"


def test_every_word_comes_from_its_list_and_the_string_names_its_own_attacks():
    d = trio(moves=False)
    d["attacks"][0]["cut"] = "sideways"
    d["attacks"][0]["frames"]["windup"] = 0
    d["attacks"][1]["next"] = ["Katana2GyakuKesa", "Nobody"]
    d["attacks"][2]["ends"] = "low"
    d["attacks"][2]["intent"] = "angry"
    p = SD.check(d)["problems"]
    assert any("its cut is 'sideways'" in x for x in p)
    assert any("attack 1 (Katana1Kesa): its frames are windup / active / recovery" in x for x in p)
    assert any("it names itself as what follows it" in x for x in p)
    assert any("followed by 'Nobody', which is not an attack of this set" in x for x in p)
    assert any("attack 3 (Katana3Makko): 'ends' says in words" in x for x in p)
    assert any("its intent is 'angry'" in x for x in p)
    one = {"set": "Probe", "attacks": [attack("A", "left")]}
    assert any("a set is two attacks or more" in x for x in SD.check(one)["problems"])
    twins = {"set": "Probe", "attacks": [attack("A", "left"), attack("A", "right")]}
    assert any("two attacks share this name" in x for x in SD.check(twins)["problems"])
    frac = trio(moves=False)
    frac["attacks"][0]["frames"]["active"] = 1.5
    assert any("whole number of frames" in x for x in SD.check(frac)["problems"])


def test_what_is_not_an_attack_is_said_and_keeps_every_attacks_place():
    d = trio()
    d["attacks"].insert(0, "not an attack")
    d["attacks"].insert(1, dict(attack("X", "left"), name=["A"]))        # a name that is a list
    d["attacks"][4]["cut"] = "up"                                        # the Makko, now the FIFTH entry of the file
    p = SD.check(d)["problems"]
    assert "attack 1 is not an attack" in p and any(x.startswith("attack 2 has no name") for x in p)
    assert any(x.startswith("attack 5 (Katana3Makko) is designed as a up cut and its keys cut the other way") for x in p)


def test_two_attacks_with_one_cut_height_and_body_are_cousins_by_design():
    d = trio(moves=False)
    d["attacks"][2].update(cut="left", height="mid", body="step_in")
    p = SD.check(d)["problems"]
    assert p == ["attack 1 (Katana1Kesa) and attack 3 (Katana3Makko) are COUSINS by design: both left / mid / step_in"]
    d["attacks"][2]["height"] = "high"                         # the same cut at another height is another attack
    assert SD.check(d)["problems"] == []


def test_the_id_is_the_design_and_nothing_else():
    d = trio(moves=False)
    base = SD.design_id(d)
    noted = copy.deepcopy(d)
    noted["attacks"][0]["note"] = "a remark"
    noted["attacks"][0]["move"] = "somewhere/else.move.json"
    noted["about"] = "words"
    assert SD.design_id(noted) == base
    for change in (lambda x: x["attacks"][0].update(cut="down_left"), lambda x: x["attacks"][1]["frames"].update(windup=30),
                   lambda x: x["attacks"][2].update(ends="another pose entirely, on one knee"), lambda x: x["attacks"].reverse(),
                   lambda x: x.update(weapon="greatsword")):
        other = copy.deepcopy(d)
        change(other)
        assert SD.design_id(other) != base


def test_a_design_is_filed_under_its_sets_name(tmp_path):
    designs = write(tmp_path, dict(trio(moves=False), set="OtherName"), name="Probe")
    d = SD.load(designs, "Probe")
    assert any("names its set 'OtherName'" in p for p in SD.check(d)["problems"])
    SD.save_json(SD.design_path(designs, "Probe"), d)          # (the loader's own mark is never written back)
    assert "_file" not in json.load(open(SD.design_path(designs, "Probe")))


# ---------------------------------------------------------------- the design against the moves' keys
def test_a_cut_is_read_as_the_player_sees_it():
    left = SD.wheel_of([0.7, 0.0, -0.7], [-0.7, 0.0, -0.7], [-1.0, 0.0, 0.0])        # the blade swept right to left
    assert left[0] == "left" and abs(left[1] - 180.0) < 1.0 and left[2] is True
    down = SD.wheel_of([0.0, 0.9, -0.44], [0.0, -0.44, -0.9], [0.0, -1.0, 0.0])
    assert down[0] == "down" and down[2] is True
    thrust = SD.wheel_of([0.0, 0.0, -1.0], [0.05, 0.0, -1.0], [0.0, 0.0, -1.0])       # the blade keeps its line and runs along it
    assert thrust == ("thrust", None, True)
    depth = SD.wheel_of([0.0, 0.3, 0.95], [0.0, 0.0, -1.0], [0.0, -0.3, -0.95])       # from behind the head straight at the target
    assert depth[0] == "down" and depth[2] is False                                   # ... reads down, but mostly in depth


def test_the_loved_katana_cuts_measure_as_what_they_are():
    with open(KESA, encoding="utf-8") as fh:
        kesa = SD.measure(json.load(fh))
    with open(GYAKU, encoding="utf-8") as fh:
        gyaku = SD.measure(json.load(fh))
    assert kesa["cut"] == "left" and kesa["cut_sure"] and gyaku["cut"] == "right" and gyaku["cut_sure"]
    assert kesa["hit_frame"] == 26 and kesa["frames"] == 51 and kesa["path"].shape == (SD.SAMPLES, 3)
    path, cut = SD.pair_distance(kesa, gyaku)
    assert path > SD.LOVED_PATH and cut > 150                 # mirrored cuts: far apart
    assert SD.pair_distance(kesa, kesa) == (0.0, 0.0)
    with pytest.raises(ValueError, match="not a strike move's key list"):
        SD.measure({"keys": [{"t": 0}]})


def test_the_loved_string_has_no_cousins_and_its_keys_are_its_design():
    r = SD.check(trio())
    assert r["problems"] == [] and sorted(r["measured"]) == ["Katana1Kesa", "Katana2GyakuKesa", "Katana3Makko"]
    assert any("ends 4 deg from where Katana2GyakuKesa starts" in n for n in r["notes"])       # the string's links, said
    assert any("attack 3 (Katana3Makko): its keys cut mostly in depth" in n for n in r["notes"])


def test_a_cut_in_depth_is_still_held_against_its_opposite():
    d = trio()
    d["attacks"][2]["cut"] = "up"                              # the makko's keys chop DOWN, mostly in depth
    p = SD.check(d)["problems"]
    assert len(p) == 1 and p[0].startswith("attack 3 (Katana3Makko) is designed as a up cut and its keys cut the other way (down")
    d["attacks"][2]["cut"] = "down_left"                       # one step off the keys' own: a note, as before
    assert SD.check(d)["problems"] == []


def test_a_cut_made_again_is_named_a_cousin(tmp_path):
    d = dict(trio(), links="blend")
    d["attacks"][2] = attack("Reskin", "left", height="low", body="lunge", move=remade(tmp_path))
    d["attacks"][1]["next"] = ["Reskin"]
    r = SD.check(d)
    cousins = [p for p in r["problems"] if "COUSINS" in p]            # (designed "low", but its blade is where the kesa's
    assert len(cousins) == 1                                          # is: a designed height alone excuses nothing)
    assert cousins[0].startswith("attack 1 (Katana1Kesa) and attack 3 (Reskin) are COUSINS: their blades run 0.2 studs")
    assert "the closest two attacks of a set he loved are 6.1 apart" in cousins[0]


def test_the_same_cut_at_the_head_and_at_the_hips_is_two_attacks(tmp_path):
    d = trio()
    d["attacks"][0] = attack("High", "left", height="high", body="step_in", nxt=["Low"],
                             move=remade(tmp_path, 0, 0, "High.move.json", 1.5))
    d["attacks"][1] = attack("Low", "left", height="low", nxt=["Katana3Makko"], move=remade(tmp_path, 0, 0, "Low.move.json", -1.0),
                             frames=(26, 1, 24))
    r = SD.check(d)
    assert not [p for p in r["problems"] if "COUSINS" in p]
    apart = [n for n in r["notes"] if "the same cut at two heights" in n]
    assert len(apart) == 1 and "attack 1 (High) and attack 2 (Low) run 2." in apart[0]          # under the bar, and said
    d["attacks"][1]["height"] = "high"                         # ... designed at ONE height they are cousins again
    assert [p for p in SD.check(d)["problems"] if "COUSINS" in p]


def test_the_bar_sits_between_a_cut_made_again_and_the_loved_sets(tmp_path):
    import numpy as np
    assert SD.RESKIN_PATH < SD.COUSIN_PATH < 4.2 < SD.LOVED_PATH and SD.COUSIN_PATH == 2.8
    with open(KESA, encoding="utf-8") as fh:
        base = json.load(fh)
    kesa = SD.measure(base)
    for yaw, shift in ((3, 0.0), (15, 0.0), (0, 0.4), (25, 0.5)):
        with open(remade(tmp_path, yaw, shift), encoding="utf-8") as fh:
            assert SD.pair_distance(kesa, SD.measure(json.load(fh)))[0] < 0.6                    # only the yaw and the grip
    loved = {}
    for f in sorted(os.listdir(LOVED)):
        with open(os.path.join(LOVED, f), encoding="utf-8") as fh:
            loved[f] = SD.measure(json.load(fh))
    names = sorted(loved)
    inside = [SD.pair_distance(loved[a], loved[b])[0] for i, a in enumerate(names) for b in names[i + 1:] if a[:2] == b[:2]]
    assert len(inside) == 9 and round(min(inside), 2) == SD.LOVED_PATH        # the number in the words is the measured one
    across = [SD.pair_distance(loved[a], loved[b])[0] for i, a in enumerate(names) for b in names[i + 1:] if a[:2] != b[:2]]
    assert round(max(x for x in across if x < SD.COUSIN_PATH), 2) == 1.27     # the same cut on the other weapon
    rng = np.random.default_rng(7)                             # every key's yaw, pitch and roll, the grip on each axis
    worst = 0.0
    for _ in range(12):
        m = copy.deepcopy(base)
        for k in m["keys"]:
            for ax in ("yaw", "pitch", "roll"):
                k[ax] = float(k.get(ax, 0.0)) + float(rng.uniform(-25, 25))
            if "grip" in k:
                k["grip"] = [float(v) + float(rng.uniform(-0.5, 0.5)) for v in k["grip"]]
        worst = max(worst, SD.pair_distance(kesa, SD.measure(m))[0])
    assert worst < SD.COUSIN_PATH                              # a re-made cut never clears the bar


def test_keys_that_are_not_the_design_are_named(tmp_path):
    d = trio()
    d["attacks"][0]["cut"] = "right"                           # the kesa's keys cut left
    d["attacks"][1]["frames"] = {"windup": 10, "active": 1, "recovery": 38}
    d["attacks"][2]["frames"] = {"windup": 28, "active": 1, "recovery": 60}
    d["attacks"][2]["height"] = "high"
    r = SD.check(d)
    assert any(p.startswith("attack 1 (Katana1Kesa) is designed as a right cut and its keys cut left (17") for p in r["problems"])
    assert any("its wind-up is designed as 10 frame(s) and its keys reach the Hit at frame 24" in p for p in r["problems"])
    assert any("it is designed as 89 frame(s) long and its keys run 50" in p for p in r["problems"])
    assert any("attack 3 (Katana3Makko) is designed high; at the Hit its blade is mid" in n for n in r["notes"])   # a note only
    d = trio()
    d["attacks"][0]["move"] = str(tmp_path / "gone.move.json")
    assert any("names a move file that is not there" in p for p in SD.check(d)["problems"])
    bad = tmp_path / "bad.move.json"
    bad.write_text("{not json")
    d["attacks"][0]["move"] = str(bad)
    assert any("its move file cannot be measured" in p for p in SD.check(d)["problems"])


# ---------------------------------------------------------------- the string's links
def test_a_set_says_how_its_string_holds_together():
    d = trio(moves=False)
    base = SD.design_id(d)
    d["links"] = "blend"
    assert SD.design_id(d) != base                            # it is part of the design he approves
    d["links"] = "chain"
    assert any("the design's links is 'chain'" in p for p in SD.check(d)["problems"])
    del d["links"]
    r = SD.check(d)
    assert not r["whole"] and any("the design's links is 'None'" in p for p in r["problems"])


def test_a_string_linked_by_pose_breaks_where_an_attack_does_not_end_on_the_next(tmp_path):
    loved = SD.check(trio())                                  # the loved string: every link under the bar
    assert loved["problems"] == [] and SD.LOVED_LINK < SD.LINK_BAR == 6.0
    d = trio()
    d["attacks"] = [d["attacks"][0], d["attacks"][2]]         # the kesa straight into the makko: nothing links them
    d["attacks"][0]["next"] = ["Katana3Makko"]
    p = SD.check(d)["problems"]
    assert len(p) == 1 and p[0].startswith("the string BREAKS: attack 1 (Katana1Kesa) ends 14")
    assert "from where Katana3Makko starts (Right Arm)" in p[0]
    assert "a set linked by pose links within 6" in p[0]
    d["links"] = "blend"                                      # the same string, played with a blend: said, not failed
    r = SD.check(d)
    assert r["problems"] == [] and any("the game blends across it" in n for n in r["notes"])


def test_a_design_from_moves_reads_how_they_link(tmp_path):
    assert SD.from_moves("Probe", [KESA, GYAKU, MAKKO])["links"] == "pose"
    said = SD.from_moves("Probe", [KESA, GYAKU, KESA])["links"]             # one pair links, the other does not: named
    assert said.startswith("TODO: pose / blend (measured: Katana2GyakuKesa ends 1") and "Katana1Kesa ends" not in said


def nudged(tmp_path, deg, name):
    """the loved gyaku-kesa with its FIRST key's blade turned `deg` degrees about the forward axis"""
    import math
    with open(GYAKU, encoding="utf-8") as fh:
        m = json.load(fh)
    x, y, z = m["keys"][0]["dir"]
    c, s_ = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    m["keys"][0]["dir"] = [x * c - y * s_, x * s_ + y * c, z]
    p = tmp_path / name
    p.write_text(json.dumps(m))
    return str(p)


def test_the_bar_is_held_just_under_and_just_over_it_and_the_blade_counts(tmp_path):
    with open(KESA, encoding="utf-8") as fh:
        kesa = SD.measure(json.load(fh))
    seen = {}
    for deg in (0, 1, 2, 3, 4, 6, 8, 12, 20, 40):
        with open(nudged(tmp_path, deg, f"n{deg}.move.json"), encoding="utf-8") as fh:
            seen[deg] = SD.link_deg(kesa, SD.measure(json.load(fh)))
    under = max((v[0], k) for k, v in seen.items() if v[0] <= SD.LINK_BAR)
    over = min((v[0], k) for k, v in seen.items() if v[0] > SD.LINK_BAR)
    assert under[0] > 3.0 and over[0] < 3 * SD.LINK_BAR                      # cases on both sides, near the bar
    for (link, turn), want in ((under, 0), (over, 1)):
        d = trio()
        d["attacks"][1]["move"] = nudged(tmp_path, turn, "second.move.json")
        breaks = [p for p in SD.check(d)["problems"] if "the string BREAKS: attack 1" in p]
        assert len(breaks) == want
    assert seen[40][0] > 30                                                  # a blade turned 40 degrees is no link


def test_a_stepped_or_a_30_a_second_move_links_as_the_game_plays_it():
    with open(KESA, encoding="utf-8") as fh:
        kesa = json.load(fh)
    with open(GYAKU, encoding="utf-8") as fh:
        gyaku = SD.measure(json.load(fh))
    plain = SD.link_deg(SD.measure(kesa), gyaku)[0]
    assert plain < 5.0
    assert abs(SD.link_deg(SD.measure(dict(kesa, fps=30)), gyaku)[0] - plain) < 0.5       # the same keys, the same link
    stepped = SD.link_deg(SD.measure(dict(kesa, step={"on": 2, "beats": "all"})), gyaku)[0]
    assert stepped > plain + 1.0                                             # it ends on a HELD pose: read as shipped


def test_a_link_nobody_measured_is_said():
    notes = SD.check(trio(moves=False))["notes"]
    assert len([n for n in notes if "is NOT measured yet" in n]) == 2
    assert not [n for n in SD.check(dict(trio(moves=False), links="blend"))["notes"] if "NOT measured" in n]


# ---------------------------------------------------------------- his yes
def test_only_the_owner_approves_the_design_on_the_page_he_saw(tmp_path):
    d = trio(moves=False)
    rec = copy.deepcopy(NONE)
    r = SD.check(d)
    now = r["id"]
    with pytest.raises(ValueError, match="only the owner"):
        SD.approve(d, rec, "fine", "claude", now)
    with pytest.raises(ValueError, match="needs the owner's words"):
        SD.approve(d, rec, " ", "owner", now)
    with pytest.raises(ValueError, match="name the design he said yes to"):
        SD.approve(d, rec, "yes", "owner", None)
    with pytest.raises(ValueError, match="show him the page as it is"):
        SD.approve(d, rec, "yes", "owner", "000000000000")
    with pytest.raises(ValueError, match="no page of this design was drawn"):
        SD.approve(d, rec, "yes", "owner", now, page_png=str(tmp_path / "never.png"))
    rec = say_yes(tmp_path, d)
    ap = rec["approved"]
    assert (ap["words"], ap["by"], ap["date"], ap["id"], ap["accepted"]) == ("yes, that string", "owner", DAY, now, [])
    assert ap["seen"]["id"] == now and len(ap["seen"]["page_sha256"]) == 64 and ap["seen"]["problems"] == []
    assert SD.state_of(d, rec)["state"] == "approved"
    d["attacks"][0]["cut"] = "down_left"                      # the design changed after his yes
    st = SD.state_of(d, rec)
    assert st["state"] == "stale" and now in st["words"] and "changed since" in st["words"]


@pytest.mark.parametrize("typed", [
    {"id": "ID", "words": "yes"},
    {"id": "ID", "by": "owner", "words": "x"},
    {"id": "ID", "by": "owner", "words": "x", "accepted": ["anything"]},
    {"id": "ID", "by": "owner", "words": "x", "seen": {"id": "ID", "page_sha256": "short", "problems": []}},
    {"id": "ID", "by": "owner", "words": "x", "accepted": ["a problem"], "seen": {"id": "ID", "page_sha256": "0" * 64, "problems": []}},
])
def test_a_record_typed_by_hand_is_no_yes(typed):
    d = trio(moves=False)
    now = SD.design_id(d)
    rec = {"approved": json.loads(json.dumps(typed).replace("ID", now)), "history": []}
    st = SD.state_of(d, rec)
    assert st["state"] == "waiting" and "recorded yes" in st["words"]


def test_the_page_he_saw_must_be_the_design_as_it_is(tmp_path):
    d = trio()
    r = SD.check(d)
    png = SD.page(d, r, copy.deepcopy(NONE), str(tmp_path / "page.png"))
    d["attacks"][2] = attack("Reskin", "down", body="lunge", move=remade(tmp_path), frames=(28, 1, 21), intent="aggressive")
    d["attacks"][1]["next"] = ["Reskin"]
    r2 = SD.check(d)
    with pytest.raises(ValueError, match="the page on disk is not this design's"):
        SD.approve(d, copy.deepcopy(NONE), "yes", "owner", r2["id"], result=r2, page_png=png)
    # the same design (same id), but a move's keys moved since the page was drawn: its problems are not the page's
    d = trio()
    r = SD.check(d)
    png = SD.page(d, r, copy.deepcopy(NONE), str(tmp_path / "page2.png"))
    d["attacks"][1]["move"] = remade(tmp_path, 3, 0.0, "Other.move.json")
    r2 = SD.check(d)
    assert r2["id"] == r["id"] and r2["problems"]
    with pytest.raises(ValueError, match="problems changed since the page was drawn"):
        SD.approve(d, copy.deepcopy(NONE), "yes", "owner", r2["id"], result=r2, page_png=png)


def test_his_yes_wins_over_a_measure_but_not_over_a_new_problem(tmp_path):
    d = dict(trio(), links="blend")
    d["attacks"][2] = attack("Reskin", "left", height="low", body="lunge", move=remade(tmp_path))
    d["attacks"][1]["next"] = ["Reskin"]
    rec = say_yes(tmp_path, d, words="I want both of those")
    assert len(rec["approved"]["accepted"]) == 1 and "COUSINS" in rec["approved"]["accepted"][0]
    st = SD.state_of(d, rec, SD.check(d))
    assert st["state"] == "approved" and st["failing"] == [] and "1 problem(s) were on the page he approved" in st["words"]
    d["attacks"][1]["move"] = remade(tmp_path, 3, 0.0, "Other.move.json")      # (not the design: the id is unchanged)
    st = SD.state_of(d, rec, SD.check(d))
    assert st["state"] == "approved" and len(st["failing"]) >= 1               # keys that came after his yes: failing


# ---------------------------------------------------------------- the lock
def before(tmp_path, names):
    os.makedirs(str(tmp_path / "blocks"), exist_ok=True)
    with open(str(tmp_path / "blocks" / "_before_blocking.json"), "w") as fh:
        json.dump({"frozen": DAY, "moves": names}, fh)
    return str(tmp_path)


def test_the_lock_holds_a_new_move_of_a_set_until_the_design_has_his_yes(tmp_path):
    d = trio(moves=False)
    designs, anims = write(tmp_path, d), before(tmp_path, ["Katana1Kesa"])
    r = SD.lock(["Katana1Kesa", "Katana2GyakuKesa", "Alone"], designs, anims)
    assert "made before the rule" in r["free"]["Katana1Kesa"]
    assert "no design names it" in r["free"]["Alone"]
    assert "its set Probe has no yes from the owner to its design" in r["held"]["Katana2GyakuKesa"]
    SD.save_json(SD.record_path(designs, "Probe"), say_yes(tmp_path, d))
    assert SD.lock(["Katana2GyakuKesa"], designs, anims)["held"] == {}
    d["attacks"][1]["body"] = "spin"                          # the design changed since his yes: held again
    SD.save_json(SD.design_path(designs, "Probe"), d)
    assert "was to design" in SD.lock(["Katana2GyakuKesa"], designs, anims)["held"]["Katana2GyakuKesa"]


def test_the_lock_holds_a_move_whose_keys_became_a_problem_after_his_yes(tmp_path):
    d = trio(moves=False)
    designs, anims = write(tmp_path, d), str(tmp_path)
    SD.save_json(SD.record_path(designs, "Probe"), say_yes(tmp_path, d))
    d["attacks"][0]["move"], d["attacks"][1]["move"] = KESA, remade(tmp_path)   # attack 2's keys: the kesa again
    SD.save_json(SD.design_path(designs, "Probe"), d)
    held = SD.lock(["Katana2GyakuKesa"], designs, anims)["held"]["Katana2GyakuKesa"]
    assert "a problem that was not on the page he approved" in held


def test_what_cannot_be_read_frees_nothing(tmp_path):
    d = trio(moves=False)
    designs, anims = write(tmp_path, d), before(tmp_path, ["Old"])
    SD.save_json(SD.record_path(designs, "Probe"), say_yes(tmp_path, d))
    assert SD.lock(["Katana2GyakuKesa", "NewCut"], designs, anims)["held"] == {}
    with open(SD.design_path(designs, "Broken"), "w") as fh:
        fh.write('{"set": "Broken", "attacks": [{"name": "NewCut"')              # a design cut short: it may name anything
    r = SD.lock(["Katana2GyakuKesa", "NewCut", "Old"], designs, anims)
    assert sorted(r["held"]) == ["Katana2GyakuKesa", "NewCut"] and "Broken.design.json" in r["held"]["NewCut"]
    assert "made before the rule" in r["free"]["Old"]          # (a move made before the rule is still never asked)
    os.remove(SD.design_path(designs, "Broken"))
    SD.save_json(SD.design_path(designs, "Odd"), {"set": "Odd", "attacks": {"name": "NewCut"}})   # attacks: not a list
    assert "Odd.design.json" in SD.lock(["NewCut"], designs, anims)["held"]["NewCut"]
    os.remove(SD.design_path(designs, "Odd"))
    style = tmp_path / "anim_style.json"
    style.write_text("{not json")
    assert "anim_style.json" in SD.lock(["NewCut"], designs, anims, [str(style)])["held"]["NewCut"]
    style.write_text(json.dumps({"sets": {"Bad": "NewCut"}}))                     # a set that is not a list of moves
    assert "anim_style.json" in SD.lock(["NewCut"], designs, anims, [str(style)])["held"]["NewCut"]
    with open(SD.record_path(designs, "Probe"), "w") as fh:
        fh.write("[1, 2]")                                                         # a record that is not a record
    assert "cannot be read" in SD.lock(["Katana2GyakuKesa"], designs, anims)["held"]["Katana2GyakuKesa"]


def test_a_set_of_a_games_style_starts_with_its_design(tmp_path):
    designs, anims = str(tmp_path / "designs"), str(tmp_path)
    style, other = tmp_path / "anim_style.json", tmp_path / "other_style.json"
    style.write_text(json.dumps({"sets": {"SpearSet": ["Spear1", "Spear2"]}}))
    other.write_text(json.dumps({"guard": {}, "sets": {"AxeSet": ["Axe1"]}}))
    r = SD.lock(["Spear2", "Axe1", "Alone"], designs, anims, [str(style), str(other)])       # every game's style
    assert "an attack of the set SpearSet (the game's style) and no design page names it" in r["held"]["Spear2"]
    assert "AxeSet" in r["held"]["Axe1"] and list(r["free"]) == ["Alone"]
    assert SD.lock(["Spear2"], designs, anims, [str(tmp_path / "none.json")])["held"] == {}   # no style: a move on its own


# ---------------------------------------------------------------- the page and the command
def test_the_page_shows_every_attack_and_says_what_it_showed(tmp_path):
    from PIL import Image
    import numpy as np
    d = trio()
    d["attacks"][0]["ends"] = "the blade low on the left, " * 6 + "the weight on the front foot"      # words that need more room
    r = SD.check(d)
    out = SD.page(d, r, copy.deepcopy(NONE), str(tmp_path / "design.png"))
    im = Image.open(out).convert("RGB")
    assert im.width >= 1900 and im.height >= 3 * 220 + 200
    seen = json.load(open(SD.seen_path(out)))
    assert seen["id"] == r["id"] and seen["problems"] == r["problems"] and len(seen["page_sha256"]) == 64
    px = np.asarray(im)
    red = (px[:, :, 0] == 200) & (px[:, :, 1] == 40) & (px[:, :, 2] == 40)
    black = (px[:, :, 0] == 12) & (px[:, :, 1] == 12) & (px[:, :, 2] == 14)
    right = im.width - 3 * 224                                   # the three silhouette cells of every row
    assert black[:, right:].sum() > 20000 and red[:, right:].sum() > 300          # the bodies, and the blades in red
    plain = SD.page(trio(), SD.check(trio()), copy.deepcopy(NONE), str(tmp_path / "plain.png"))
    assert im.height > Image.open(plain).height                  # the row grew with its words: nothing is cut off
    draft = SD.template("Probe", 2)
    SD.page(draft, SD.check(draft), copy.deepcopy(NONE), str(tmp_path / "draft.png"))   # a draft is drawn too
    assert Image.open(str(tmp_path / "draft.png")).height > 400


def run_cli(*args):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "anim", "set_design.py"), *args], capture_output=True,
                       text=True, encoding="utf-8", cwd=ROOT)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


def test_new_page_approve_state_and_lock_as_commands(tmp_path):
    designs, png = str(tmp_path / "designs"), str(tmp_path / "p.png")
    code, v = run_cli("new", "Probe", "--attacks", "3", "--weapon", "katana", "--designs", designs)
    assert code == 0 and v["next_action"].startswith("improve the design: fill in")
    assert run_cli("new", "Probe", "--attacks", "3", "--designs", designs)[1]["summary"].endswith("exists already")
    assert "two attacks or more" in run_cli("new", "Other", "--attacks", "x", "--designs", designs)[1]["summary"]
    code, v = run_cli("page", "Probe", "--designs", designs, "--out", png)
    assert code == 1 and "4 problem(s) in 3 attack(s)" in v["summary"] and os.path.isfile(png)
    assert v["next_action"].startswith("improve the design: fill it in")
    SD.save_json(SD.design_path(designs, "Probe"), trio())
    code, held = run_cli("lock", "Katana2GyakuKesa", "--designs", designs)
    assert code == 1 and held["summary"].startswith("anim Katana2GyakuKesa: STOP - a NEW move of a set whose design does not have the owner's yes")
    assert "The set first, then its moves" in held["summary"] and held["next_action"].startswith("lune run kit anim design <Set>")
    now = SD.design_id(trio())
    code, early = run_cli("approve", "Probe", "yes", "--by", "owner", "--id", now, "--designs", designs, "--page", png)
    assert code == 1 and "the page on disk is not this design's" in early["summary"]          # the page is the draft's
    code, v = run_cli("page", "Probe", "--designs", designs, "--out", png)
    assert code == 0 and "3 attack(s), no two of them cousins - waiting" in v["summary"] and v["next_action"].startswith("look at the page")
    assert run_cli("approve", "Probe", "yes", "--by", "claude", "--id", v["id"], "--designs", designs, "--page", png)[0] == 1
    code, ok = run_cli("approve", "Probe", "yes, that string", "--by", "owner", "--id", v["id"], "--designs", designs, "--page", png)
    assert code == 0 and "the owner's yes to design" in ok["summary"]
    code, st = run_cli("state", "Probe", "--need", "approved", "--designs", designs)
    assert code == 0 and st["state"] == "approved"
    assert run_cli("lock", "Katana2GyakuKesa", "--designs", designs)[0] == 0
    d = trio()
    d["attacks"][1]["move"] = remade(tmp_path, 3, 0.0, "Other.move.json")       # keys that came after his yes
    SD.save_json(SD.design_path(designs, "Probe"), d)
    code, st = run_cli("state", "Probe", "--need", "approved", "--designs", designs)
    assert code == 1 and "a problem that was not on the page he approved" in st["summary"]    # as the lock sees it
    assert run_cli("lock", "Katana2GyakuKesa", "--designs", designs)[0] == 1


def test_a_design_from_moves_measures_what_the_keys_say(tmp_path):
    designs = str(tmp_path / "designs")
    code, v = run_cli("from-moves", "Probe", KESA, GYAKU, MAKKO, "--designs", designs, "--weapon", "katana")
    assert code == 0 and "3 attack(s) measured from their keys" in v["summary"]
    d = SD.load(designs, "Probe")
    assert [a["cut"] for a in d["attacks"]] == ["left", "right", "down"]
    assert d["attacks"][0]["frames"] == {"windup": 26, "active": 1, "recovery": 24}
    assert d["attacks"][0]["next"] == ["Katana2GyakuKesa"] and "TODO" in d["attacks"][0]["body"]
    assert SD.state_of(d, SD.load_record(designs, "Probe"))["state"] == "draft"


def test_what_cannot_be_read_is_refused_in_one_line(tmp_path):
    designs = str(tmp_path / "designs")
    code, v = run_cli("page", "Nothing", "--designs", designs)
    assert code == 1 and "no design at" in v["summary"]
    os.makedirs(designs)
    with open(SD.design_path(designs, "Broken"), "w") as fh:
        fh.write("{not json")
    code, v = run_cli("state", "Broken", "--designs", designs)
    assert code == 1 and "is not valid JSON" in v["summary"]
    os.remove(SD.design_path(designs, "Broken"))
    SD.save_json(SD.design_path(designs, "Probe"), trio(moves=False))
    with open(SD.record_path(designs, "Probe"), "w") as fh:
        fh.write("{not json")
    code, v = run_cli("state", "Probe", "--designs", designs)
    assert code == 1 and "never delete it" in v["summary"]
    code, v = run_cli("lock", "Katana1Kesa", "--designs", designs)
    assert code == 1 and "cannot be read" in v["held"]["Katana1Kesa"]                       # an unreadable yes is no yes


def test_a_new_design_says_the_guard_each_attack_starts_from_and_a_pose_string_links_by_it():
    """(the owner's V3 list, anim stage B.1: the design page had the pose each attack ENDS in, never the guard it
    starts from) - a design made now (schema 2) says both; in a set linked by pose an attack that follows another
    starts in the very pose that one ends in; a schema-1 design (made before) is read as it was"""
    t = SD.template("Probe", 2)
    assert t["schema"] == 2 and all(a["starts"].startswith("TODO") for a in t["attacks"])
    assert any("TODO in" in p and "starts" in p for p in SD.field_problems(t))
    d = {"schema": 2, "set": "Probe", "weapon": "katana", "links": "pose", "attacks": [
        {**attack("Probe1", "down_left", nxt=["Probe2"]), "starts": "high guard, blade over the right shoulder",
         "ends": "low left, edge down, weight on the front foot"},
        {**attack("Probe2", "up_right"), "starts": "Low left, edge down,  weight on the front foot.",
         "ends": "high guard, blade over the right shoulder"}]}
    assert not [p for p in SD.field_problems(d) if "starts" in p]                 # the same words: linked
    broken = copy.deepcopy(d)
    broken["attacks"][1]["starts"] = "middle guard, point at the eyes"
    said = [p for p in SD.field_problems(broken) if "starts from" in p]
    assert said and "Probe2" in said[0] and "linked by pose" in said[0]
    assert not [p for p in SD.field_problems(dict(broken, links="blend")) if "starts from" in p]   # the game blends
    missing = copy.deepcopy(d)
    missing["attacks"][0].pop("starts")
    assert any("'starts' says in words the guard it starts from" in p for p in SD.field_problems(missing))
    old = copy.deepcopy(missing)
    old["schema"] = 1
    assert not [p for p in SD.field_problems(old) if "starts" in p]
