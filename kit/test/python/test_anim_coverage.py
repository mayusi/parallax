"""kit/anim/catalog_coverage.py - what the catalogue covers and what it does not (the owner's older list, AN-08): clips
placed on the axes by their measured tags and words, a request placed by its words, familiar / thin / unseen, an
unsupported request named with what is missing, the owner's verdicts split by the family's standing. A made-up
catalogue only (the real one lives outside git)."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import catalog_coverage as CV    # noqa: E402
import motion_lib as ML          # noqa: E402


def clip(name, kind, tags, verdict="love", licence="game", pack=""):
    return {"id": name, "name": name, "pack": pack, "kind": kind, "tags": list(tags), "verdict": verdict, "licence": licence}


def catalog():
    rows = []
    for i in range(12):                                      # a familiar family: sword cuts across, both arms
        rows.append(clip(f"Sword Slash {i}", "attack", ["strike", "horizontal", "botharms", "fast"]))
    for i in range(3):                                       # a thin one: sword thrusts
        rows.append(clip(f"Sword Stab {i}", "attack", ["strike", "thrust", "righthand"]))
    for i in range(11):                                      # kicks: no weapon in their words, a leg up
        rows.append(clip(f"M{i}", "m1/combo", ["strike", "upward", "legup", "airborne"]))
    rows.append(clip("Greatsword Overhead", "attack", ["strike", "downward", "twohanded"], verdict="bad"))
    rows.append(clip("Greatsword Smash", "attack", ["strike", "downward", "twohanded"], licence="study"))
    rows.append(clip("Hit Victim Grab", "other", ["botharms"]))
    rows.append(clip("Block", "defence", ["botharms", "holds"]))
    rows.append(clip("Walk", "walk", ["stride", "loop"], verdict="unrated"))
    return rows


@pytest.fixture(scope="module")
def t():
    return CV.table(catalog())


def test_a_clip_is_placed_by_its_tags_and_its_words():
    p = CV.place(clip("Sword Slash", "attack", ["strike", "horizontal", "botharms"]))
    assert p == {"kind": "attack", "weapon": "sword", "hands": "botharms", "direction": "horizontal", "state": ("grounded",),
                 "interaction": "solo"}
    assert CV.place(clip("M1", "m1/combo", ["strike", "upward", "legup", "airborne"]))["weapon"] == "unarmed"
    assert CV.place(clip("M1", "m1/combo", ["strike", "upward"]))["weapon"] == "unsaid"          # a strike with no word and no kick
    assert CV.place(clip("Claymore Heavy", "attack", ["strike", "downward", "twohanded"]))["weapon"] == "greatsword"
    assert CV.place(clip("Hit", "reaction", []))["interaction"] == "reaction"
    assert CV.place(clip("Throw Victim", "other", []))["interaction"] == "paired"
    assert CV.place({"name": None, "kind": None})["kind"] == "other"
    assert CV.place(clip("Odd", "attack", "strike"))["direction"] == "none"                      # (tags that are no list)


def test_what_the_one_review_found_in_the_placing_stays_fixed():
    # a dance's fast arm is measured as a "strike": it is no strike, and its leg up makes it no kick
    d = CV.place(clip("Kazotsky", "dance", ["strike", "upward", "legup", "airborne"]))
    assert d["direction"] == "none" and d["weapon"] == "unsaid"
    assert CV.place(clip("Cartoony Run", "run", ["strike", "horizontal", "legup"]))["weapon"] == "unsaid"
    # a sword pack's walk is not a sword move; its attack is
    assert CV.place(clip("Walk", "walk", ["stride"], pack="Sword Fox anims"))["weapon"] == "unsaid"
    assert CV.place(clip("Attack 2", "attack", ["strike", "diagonal"], pack="Sword Fox anims"))["weapon"] == "sword"
    # the clip's own name before its pack's
    assert CV.place(clip("Kick Finisher", "attack", ["strike"], pack="Sword Fox anims"))["weapon"] == "unarmed"
    # "GreatSword" is a greatsword, "slash" names no weapon (a claw slash, BackSlash)
    assert CV.place(clip("Heavy 1", "attack", ["strike", "downward"], pack="GreatSword anims R6"))["weapon"] == "greatsword"
    assert CV.place(clip("sukuna claw slash thing", "attack", ["strike", "horizontal"]))["weapon"] == "unsaid"
    # every state a clip has is counted (airborne used to hide crouch, spin and lunge)
    p = CV.place(clip("Spin Kick", "attack", ["strike", "spin", "crouch", "airborne"]))
    assert p["state"] == ("airborne", "crouch", "spin")
    t = CV.table([clip("Spin Kick", "attack", ["strike", "spin", "crouch", "airborne"])])
    assert all(t["axes"]["state"][v]["counted"] == 1 for v in ("airborne", "crouch", "spin")) and "grounded" not in t["axes"]["state"]
    assert CV.ask(t, "crouch kick")["all"] == 1 and CV.ask(t, "spin kick")["all"] == 1
    # words: an acronym in front of a word, a letter-and-number token, plurals
    assert CV._words("GSCraftDiagonal") == ["gs", "craft", "diagonal"]
    assert CV._words("DTDrillSpin4") == ["dt", "drill", "spin", "4"]
    assert CV._words("HqM1a") == ["hq", "m1", "a"] and CV._words("Katana1Kesa") == ["katana", "1", "kesa"]
    assert CV._words("kicks punches swords") == ["kick", "punch", "sword"]
    assert CV._weapon_in(CV._words("GSCraftDiagonal")) == "greatsword" and CV._weapon_in(CV._words("KatanaKesa")) == "katana"


def test_only_a_loved_clip_a_game_may_use_counts(t):
    assert t["clips"] == len(catalog()) and t["counted"] == 12 + 3 + 11 + 1 + 1
    gs = t["axes"]["weapon"]["greatsword"]
    assert gs["n"] == 2 and gs["loved"] == 1 and gs["counted"] == 0 and gs["status"] == "unseen"   # one bad, one study-only
    assert t["axes"]["weapon"]["sword"]["status"] == "familiar" and t["axes"]["weapon"]["sword"]["counted"] == 15
    assert t["axes"]["direction"]["thrust"]["status"] == "thin"
    assert t["axes"]["kind"]["walk"]["counted"] == 0
    assert CV.status(10) == "familiar" and CV.status(9) == "thin" and CV.status(0) == "unseen"


def test_the_strikes_by_weapon_and_direction_name_the_empty_and_the_thin(t):
    cells = {(c["weapon"], c["direction"]): c for c in CV.strikes(t)}
    assert cells[("sword", "horizontal")]["status"] == "familiar"
    assert cells[("sword", "thrust")] == {"weapon": "sword", "direction": "thrust", "counted": 3, "status": "thin"}
    assert cells[("sword", "downward")]["status"] == "unseen"
    assert cells[("greatsword", "downward")]["counted"] == 0                      # (the bad and the study-only do not count)
    assert cells[("unarmed", "upward")]["counted"] == 11
    assert CV.strikes(t)[0]["counted"] == 0                                       # the empty first


def test_a_request_is_placed_by_what_it_says_and_only_that():
    w = CV.wanted("a sword thrust")
    assert w["weapon"] == "sword" and w["direction"] == "thrust"
    w = CV.wanted("two handed overhead greatsword slam")
    assert w["weapon"] == "greatsword" and w["hands"] == "twohanded" and w["direction"] == "downward"
    w = CV.wanted("left handed kick in the air")
    assert w == {"weapon": "unarmed", "hands": "lefthand", "state": "airborne", "kind": "attack"}
    assert CV.wanted("a happy little wave") == {}
    assert "weapon" not in CV.wanted("an overhead slam")                          # (what it does not say is not held against it)
    # what the one review's requests showed
    assert CV.wanted("kicks")["weapon"] == "unarmed" and CV.wanted("dual pistols fire")["weapon"] == "gun"
    assert "weapon" not in CV.wanted("heavy two handed horizontal swing")         # ("heavy" is a weight, not a hammer)
    assert CV.wanted("heavy two handed horizontal swing")["hands"] == "twohanded"
    assert "hands" not in CV.wanted("hit reaction from the left")                 # (where the blow comes from)
    assert CV.wanted("hit reaction from the left")["kind"] == "reaction"
    assert CV.wanted("dance") == {"kind": "dance"}
    assert "direction" not in CV.wanted("grab and throw") and CV.wanted("grab and throw")["interaction"] == "paired"
    assert CV.wanted("punch combo")["kind"] == "m1/combo" and CV.wanted("M1")["kind"] == "m1/combo"
    assert CV.wanted("left hand jab")["hands"] == "lefthand"


def test_familiar_thin_unseen_and_unsupported_with_what_is_missing(t):
    a = CV.ask(t, "sword slash across")
    assert a["verdict"] == "familiar" and a["all"] >= 12
    a = CV.ask(t, "sword stab")
    assert a["verdict"] == "thin" and a["all"] == 3
    a = CV.ask(t, "greatsword overhead slam")
    assert a["verdict"] == "unsupported" and a["all"] == 0
    assert "weapon = greatsword" in a["missing"]
    # each word is covered, the two together are not: the pairing is named
    a = CV.ask(t, "sword uppercut swing upward")
    assert a["verdict"] == "unsupported" and a["all"] == 0
    assert "weapon = sword" in a["missing"] and "direction = upward" in a["missing"] and "none that is both" in a["missing"]
    a = CV.ask(t, "something nice")
    assert a["verdict"] == "unplaced" and a["all"] is None
    # a familiar value with few clips that have ALL of it: the count of those decides
    a = CV.ask(t, "sword thrust right hand")
    assert a["verdict"] == "thin"


def test_the_owners_verdicts_are_split_by_the_familys_standing(t):
    book = {"verdicts": {
        "SwordSlashWide": [{"verdict": "bad"}, {"verdict": "loved"}],            # the last verdict stands
        "SwordSlashAgain": [{"verdict": "horrible"}],
        "GreatswordOverhead": [{"verdict": "horrible"}],
        "SwordStab": [{"verdict": "ok"}],
        "Mystery": [{"verdict": "good"}],
        "Broken": [], "Odd": [{"verdict": "meh"}], "Worse": "x",
    }}
    v = CV.verdicts(t, book)
    assert v["familiar"]["n"] == 2 and v["familiar"]["mean"] == 0.5
    assert v["unsupported"] == {"n": 1, "mean": 0.0, "clips": [["GreatswordOverhead", "horrible"]]}
    assert v["thin"]["mean"] == 0.5 and v["unplaced"]["clips"] == [["Mystery", "good"]]
    assert sum(g["n"] for g in v.values()) == 5


def test_the_command_line_and_a_machine_without_the_catalogue(tmp_path, monkeypatch, capsys):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"schema": 1, "clips": catalog()}), encoding="utf-8")
    monkeypatch.setattr(ML, "CATALOG", str(path))
    monkeypatch.setattr(ML, "LIVE_PICKS", str(tmp_path / "none.json"))
    assert CV.main(["report"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "sword downward" in out["strikes_empty"] and "sword thrust (3)" in out["strikes_thin"]
    assert out["axes"]["weapon"]["greatsword"]["status"] == "unseen"
    assert CV.main(["ask", "greatsword", "overhead", "slam"]) == 1
    assert "UNSUPPORTED" in json.loads(capsys.readouterr().out)["summary"]
    assert CV.main(["ask", "sword slash across"]) == 0
    capsys.readouterr()
    assert CV.main(["ask", "a happy little wave"]) == 1
    capsys.readouterr()
    # the one sentence the dossier commands end with (kit anim dossier new / check)
    assert CV.line("greatsword overhead").startswith("catalogue: UNSUPPORTED") and "weapon = greatsword" in CV.line("greatsword overhead")
    assert CV.line("sword slash").startswith("catalogue: familiar")
    assert "says no weapon" in CV.line("mystery")
    src = open(os.path.join(ROOT, "kit", "anim", "proc_dossier.py"), encoding="utf-8").read()
    assert 'CC.line(name.replace("_", " "))' in src and 'line(a[1].replace("_", " "))' in src
    monkeypatch.setattr(ML, "CATALOG", str(tmp_path / "missing.json"))
    assert CV.line("sword slash").startswith("catalogue: not read")          # (a machine without it: said, never raised)
    assert CV.main(["report"]) == 1
    assert "is not on this machine" in json.loads(capsys.readouterr().out)["summary"]


def test_the_build_is_told_what_the_catalogue_has_of_each_move():
    """V3 anim stage A.2: the dossier gate that every named build runs says, for each move it passed, what the loved
    catalogue has of its like - an UNSUPPORTED move is no longer built in silence; a refused move is not read; a
    machine without the catalogue says nothing (it never fails the gate)"""
    import proc_dossier as PD
    pairs = ["GsThrustNew=greatsword_thrust=", "SwordCutNew=sword_slash_across=", "Refused=whatever="]
    cov = PD.gate_coverage(pairs, {"Refused": "no dossier"}, load=catalog)
    assert set(cov) == {"GsThrustNew", "SwordCutNew"}
    assert "UNSUPPORTED" in cov["GsThrustNew"]
    assert "UNSUPPORTED" not in cov["SwordCutNew"] and "familiar" in cov["SwordCutNew"]

    def gone():
        raise FileNotFoundError("_artifacts/r6lib/catalog.json is not on this machine")
    assert PD.gate_coverage(pairs, {}, load=gone) == {}
