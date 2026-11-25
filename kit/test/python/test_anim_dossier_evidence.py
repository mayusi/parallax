"""kit/anim/dossier_evidence.py - what each phase of a move rests on (the owner's older list, AN-06): measured,
inferred or told by the owner, phase by phase; a strike's contact and anticipation resting on inference are named;
a new dossier (schema 3) must say it. Made-up dossiers only; the project's own are read, never changed."""
import copy
import glob
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import dossier_evidence as DE    # noqa: E402
import proc_dossier as PD        # noqa: E402


def dossier(schema=3):
    return {
        "schema": schema, "name": "probe", "move": "a made-up cut", "category": "combat",
        "sources": [
            {"id": "footage", "cite": "a clip", "url": "x", "took": "the timings", "measured": "wind 0.21 s, cut 0.09 s at 60 fps"},
            {"id": "coach", "cite": "a page", "url": "y", "took": "the cues"},
            {"id": "owner", "cite": "the owner, 2026-11-01", "url": "z", "took": "'hold the end longer'"},
        ],
        "phases": [
            {"name": "guard", "real_s": [0.0, 0.0], "game_s": [0.0, 0.0], "body": "stands"},
            {"name": "wind", "real_s": [0.0, 0.21], "game_s": [0.0, 0.2], "source": "footage", "body": "the blade goes up",
             "evidence": {"basis": "measured", "from": "footage"}},
            {"name": "cut", "real_s": [0.21, 0.30], "game_s": [0.2, 0.3], "real_s_from": "footage frames 13-18 at 60 fps",
             "body": "the blade comes down", "evidence": {"basis": "measured", "from": "footage"}},
            {"name": "hold", "real_s": None, "game_s": [0.3, 0.7], "source": "owner", "body": "the end is held",
             "evidence": {"basis": "told", "from": "owner", "note": "hold the end longer"}},
            {"name": "return", "real_s": None, "game_s": [0.7, 1.0], "source": "coach", "body": "back to guard",
             "evidence": {"basis": "inferred", "from": "the coaching page's words, no timing"}},
        ],
        "reference_frames": [{"phase": "wind", "video": "a.mp4", "t": 0.1, "view": "side"},
                             {"phase": "cut", "video": "a.mp4", "t": 0.25, "view": "player"}],
    }


def test_each_phase_is_read_and_the_strikes_critical_phases_are_named():
    r = DE.read(dossier())
    by = {p["name"]: p for p in r["phases"]}
    assert [by[n]["basis"] for n in ("guard", "wind", "cut", "hold", "return")] == ["still", "measured", "measured", "told", "inferred"]
    assert r["critical"] == ["wind", "cut"] and by["wind"]["critical"] and by["cut"]["critical"] and not by["return"]["critical"]
    assert r["counts"] == {"measured": 2, "inferred": 1, "told": 1, "still": 1}
    assert r["unsupported"] == []
    # seen from: the wind only from the side, the cut from the player's camera, the hold from nowhere
    assert by["wind"]["seen_from"] == ["side"] and "none from the player's camera" in by["wind"]["note"]
    assert by["cut"]["note"] is None
    assert by["hold"]["note"] == "no reference frame kept for it" and by["guard"]["note"] is None


def test_an_older_dossier_that_says_nothing_is_worked_out_and_never_refused():
    d = dossier(schema=2)
    for p in d["phases"]:
        p.pop("evidence", None)
    r = DE.read(d)
    by = {p["name"]: p for p in r["phases"]}
    assert by["wind"]["basis"] == "measured" and by["wind"]["why"] == "source footage" and not by["wind"]["said"]
    assert by["cut"]["basis"] == "measured" and "frames 13-18" in by["cut"]["why"]
    assert by["hold"]["basis"] == "told" and by["return"]["basis"] == "inferred"
    assert DE.missing(d) == [] and DE.missing({"schema": 1, "phases": d["phases"]}) == [] and DE.missing({"schema": "x"}) == []
    # a timing with nowhere it was measured is not a measurement
    d["phases"][1].pop("source")
    assert DE.basis(d, d["phases"][1])[:2] == ("inferred", "its timing names nowhere it was measured")
    # ... nor is a source whose `measured` holds no number
    d["phases"][1]["source"] = "coach"
    assert DE.basis(d, d["phases"][1])[0] == "inferred"


def test_a_critical_phase_on_inference_is_unsupported_and_said_first():
    d = dossier()
    d["phases"][2] = {"name": "cut", "real_s": None, "game_s": [0.2, 0.3], "source": "coach", "body": "down",
                      "evidence": {"basis": "inferred", "from": "the coaching page"}}
    r = DE.read(d)
    assert r["unsupported"] == ["cut"]
    assert "UNSUPPORTED: cut" in DE.words("probe", r)
    refused = DE.missing(d)
    assert len(refused) == 1 and "phase cut is the move's contact and rests on inference" in refused[0]
    # the anticipation the same
    d2 = dossier()
    d2["phases"][1]["evidence"] = {"basis": "inferred", "from": "a guess from the cut's length"}
    assert "phase wind is the move's anticipation" in DE.missing(d2)[0]
    # it may stand, when the phase says why
    d["phases"][2]["accept"] = "no footage of this cut exists; the owner's verdict on the built clip is the check"
    assert DE.read(d)["unsupported"] == [] and DE.missing(d) == []
    # a recovery on inference is not critical
    assert DE.read(dossier())["phases"][4]["basis"] == "inferred" and DE.missing(dossier()) == []


def test_a_new_dossier_must_say_what_every_moving_phase_rests_on():
    d = dossier()
    del d["phases"][4]["evidence"]
    assert any("phase return does not say what it rests on" in m for m in DE.missing(d))
    d = dossier()
    d["phases"][1]["evidence"] = {"basis": "seen it once", "from": "memory"}
    assert any("phase wind does not say" in m for m in DE.missing(d))
    # a still phase needs none
    assert "evidence" not in dossier()["phases"][0] and DE.missing(dossier()) == []


def test_a_said_basis_is_held_to_what_the_dossier_holds():
    d = dossier()
    d["phases"][1]["real_s"] = None                           # says measured, has no timing
    assert any("phase wind says measured, but no real timing in numbers" in m for m in DE.missing(d))
    d = dossier()
    d["phases"][1]["source"] = "coach"                        # ... or a timing measured nowhere
    assert any("phase wind says measured, but its timing names nowhere" in m for m in DE.missing(d))
    d = dossier()
    d["phases"][3]["evidence"] = {"basis": "told", "from": "a forum"}
    assert any("phase hold says told" in m for m in DE.missing(d))
    d = dossier()
    d["phases"][3]["evidence"] = {"basis": "told", "from": "owner"}        # the words are missing
    assert any("phase hold says told" in m for m in DE.missing(d))
    d = dossier()
    d["phases"][4]["evidence"] = {"basis": "inferred"}
    assert any("phase return says inferred - from what?" in m for m in DE.missing(d))


def test_the_dossier_gate_asks_it_and_a_new_scaffold_is_schema_three(tmp_path, monkeypatch):
    s = PD.scaffold("probe")
    assert s["schema"] == DE.SCHEMA == 3 and "evidence" in s["phases"][0]
    src = open(os.path.join(ROOT, "kit", "anim", "proc_dossier.py"), encoding="utf-8").read()
    assert "missing += DE.missing(d)" in src
    # the scaffold as written is refused for its evidence too (its TODO is no basis) once it moves
    s["phases"][0]["game_s"] = [0.0, 0.3]
    assert any("does not say what it rests on" in m for m in DE.missing(s))


def test_the_command_line_reads_one_and_a_folder(tmp_path, capsys):
    good, bad = dossier(), dossier()
    bad["phases"][2]["evidence"] = {"basis": "inferred", "from": "a guess"}
    (tmp_path / "good.json").write_text(json.dumps(good), encoding="utf-8")
    (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    (tmp_path / "_legacy.json").write_text("{}", encoding="utf-8")
    assert DE.main([str(tmp_path / "good.json")]) == 0
    assert "2 measured, 1 inferred, 1 told" in json.loads(capsys.readouterr().out)["summary"]
    assert DE.main([str(tmp_path / "bad.json")]) == 1
    assert "contact and rests on inference" in json.loads(capsys.readouterr().out)["summary"]
    assert DE.main(["table", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["rows"]) == 2 and out["unsupported"] == ["bad"]
    assert DE.main([str(tmp_path / "none.json")]) == 1


def test_only_a_strike_has_critical_phases_and_a_contact_may_be_said():
    # (the one review: the name words called a run's "swing through", a wall "kick-off" and a pistol's recoil contacts)
    run = {"category": "locomotion", "phases": [{"name": "push", "game_s": [0.0, 0.2]}, {"name": "swing through", "game_s": [0.2, 0.5]}]}
    assert DE.criticals(run) == [] and DE.read(run)["unsupported"] == []
    idle = {"category": "idle", "phases": [{"name": "breathe", "game_s": [0.0, 1.0]}, {"name": "seam", "game_s": [1.0, 1.0]}]}
    assert DE.criticals(idle) == []
    # a phase that SAYS it is the contact is one, whatever the category and whatever it is called
    gun = {"category": "gun", "phases": [{"name": "raise", "game_s": [0.0, 0.2]}, {"name": "shot", "game_s": [0.2, 0.25], "contact": True},
                                         {"name": "kick", "game_s": [0.25, 0.5]}]}
    assert DE.criticals(gun) == ["raise", "shot"]
    # a dossier of several clips starts its times again: the anticipation is not taken from the clip before
    two = {"category": "combat", "phases": [{"name": "first clip end", "game_s": [0.4, 0.9]}, {"name": "cut", "game_s": [0.0, 0.2]}]}
    assert DE.criticals(two) == ["cut"]
    # a still phase between the wind and a SAID contact is stepped over (unsaid, an instant after the start is the
    # dossier's own contact: proc_dossier.hit_phase's rule)
    held = {"category": "combat", "phases": [{"name": "wind", "game_s": [0.0, 0.2]}, {"name": "pause", "game_s": [0.2, 0.2]},
                                             {"name": "cut", "game_s": [0.2, 0.3], "contact": True}]}
    assert DE.criticals(held) == ["wind", "cut"]


def test_a_guns_blow_is_its_shot_and_blows_the_name_words_did_not_know_are_found():
    # (left on card r66z by the first review: "kick" read as a pistol's contact; "drive", "riposte", "shot" not seen)
    fire = {"category": "combat", "phases": [{"name": "break", "game_s": [0.0, 0.0]}, {"name": "kick", "game_s": [0.0, 0.033]},
                                             {"name": "recover", "game_s": [0.033, 0.2]}]}
    assert DE.criticals(fire) == ["break"]                    # the trigger's break is the shot; the "kick" after it the recoil
    # a combat dossier whose blow IS a kick keeps it (the review of this change: it had lost its contact)
    kick = {"category": "combat", "phases": [{"name": "chamber", "game_s": [0.0, 0.2]}, {"name": "Kick", "game_s": [0.2, 0.3]},
                                             {"name": "retract", "game_s": [0.3, 0.6]}]}
    assert DE.criticals(kick) == ["chamber", "Kick"]
    # whole words only: a pump is no shot, a kick-off no recoil
    pump = {"category": "gun", "phases": [{"name": "aim", "game_s": [0.0, 0.2]}, {"name": "shotgun pump", "game_s": [0.2, 0.5]}]}
    assert DE.criticals(pump) == []
    side = {"category": "gun", "phases": [{"name": "raise", "game_s": [0.0, 0.1]}, {"name": "shot", "game_s": [0.1, 0.13]},
                                          {"name": "kick", "game_s": [0.13, 0.3]}]}
    assert DE.criticals(side) == ["raise", "shot"]
    reload_ = {"category": "gun", "phases": [{"name": "drop", "game_s": [0.0, 0.3]}, {"name": "punch down + seat", "game_s": [0.3, 0.6]}]}
    assert DE.criticals(reload_) == []
    shoulder = {"category": "combat", "phases": [{"name": "guard", "game_s": [0.0, 0.0]}, {"name": "drive", "game_s": [0.0, 0.29]},
                                                 {"name": "hold", "game_s": [0.29, 0.8]}]}
    assert DE.criticals(shoulder) == ["drive"]
    kaeshi = {"category": "combat", "phases": [{"name": "hold", "game_s": [0.0, 0.2]}, {"name": "riposte", "game_s": [0.2, 0.35]}]}
    assert DE.criticals(kaeshi) == ["hold", "riposte"]
    # two clips in one dossier that both start at 0: the wind-up is not taken from the clip before
    two = {"category": "combat", "phases": [{"name": "end: falling away", "game_s": [0.0, 0.8]}, {"name": "cuts", "game_s": [0.0, 1.3]}]}
    assert DE.criticals(two) == ["cuts"]


def test_a_contact_that_is_an_instant_is_judged_not_skipped_as_still():
    d = dossier()
    d["phases"].insert(3, {"name": "contact", "real_s": None, "game_s": [0.3, 0.3], "body": "the edge meets"})
    r = DE.read(d)
    by = {p["name"]: p for p in r["phases"]}
    assert r["critical"] == ["cut", "contact"] and by["contact"]["basis"] == "inferred" and r["unsupported"] == ["contact"]
    assert any("phase contact does not say what it rests on" in m for m in DE.missing(d))
    d["phases"][3].update({"real_s": [0.30, 0.30], "real_s_from": "footage frame 18 at 60 fps",
                           "evidence": {"basis": "measured", "from": "footage"}})
    assert DE.read(d)["unsupported"] == [] and DE.missing(d) == []
    assert DE.basis(d, d["phases"][0])[0] == "still"         # (the start pose is still still)


def test_measured_and_told_cannot_be_claimed_with_nothing_behind_them():
    for bad in ([-5, -1], [0, 1e9], [True, 2], [0.3, 0.1], ["0", "1"], [0.1, float("nan")]):
        d = dossier()
        d["phases"][1]["real_s"] = bad
        assert any("phase wind says measured, but no real timing" in m for m in DE.missing(d)), bad
    for place in ("unknown, 2026-11-15", "n/a 0", "TODO 1"):
        d = dossier()
        d["phases"][2]["real_s_from"] = place
        assert any("phase cut says measured, but its timing names nowhere" in m for m in DE.missing(d)), place
    d = dossier()
    d["sources"][0]["measured"] = "guess 2026"
    assert any("phase wind says measured" in m for m in DE.missing(d))
    for ev in ({"basis": "told", "from": "ownership_doc", "note": "hold it"}, {"basis": "told", "from": "owner", "note": "."},
               {"basis": "told", "from": "owner", "note": "12"}):
        d = dossier()
        d["phases"][3]["evidence"] = ev
        assert any("phase hold says told" in m for m in DE.missing(d)), ev
    # an older dossier's owner source: "owner" or "owner_<what>", not a word that begins with it
    old = dossier(schema=2)
    for p in old["phases"]:
        p.pop("evidence", None)
    old["phases"][3]["source"] = "owner_mujoco_hook"
    assert DE.basis(old, old["phases"][3])[0] == "told"
    old["phases"][3]["source"] = "ownership_doc"
    assert DE.basis(old, old["phases"][3])[0] == "inferred"


def test_a_schema_three_phase_that_says_inferred_or_told_owes_no_measured_timing():
    # (the one review: the older rule still asked every moving phase for real_s, so nothing could be SAID inferred)
    d = dossier()
    assert d["phases"][3]["real_s"] is None and d["phases"][4]["real_s"] is None
    assert PD.evidence_missing(d) == [] and DE.missing(d) == []
    # ... a phase that says measured still owes it, and a schema-2 dossier is held as before
    d["phases"][1]["real_s"] = None
    assert any("phase wind has no measured real_s" in m for m in PD.evidence_missing(d))
    two = dossier(schema=2)
    assert any("phase hold has no measured real_s" in m for m in PD.evidence_missing(two))


def test_one_broken_file_does_not_end_the_table_and_an_empty_folder_is_said(tmp_path, capsys):
    (tmp_path / "good.json").write_text(json.dumps(dossier()), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    assert DE.main(["table", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert len(out["rows"]) == 1 and out["broken"] == ["broken.json: JSONDecodeError"] and "1 unreadable" in out["summary"]
    assert DE.main(["table", str(tmp_path / "nowhere")]) == 1
    assert "no dossier could be read" in json.loads(capsys.readouterr().out)["summary"]


def test_the_projects_own_dossiers_are_all_read_without_a_refusal():
    paths = [p for p in glob.glob(os.path.join(ROOT, "assets", "animations", "dossiers", "*.json"))
             if not os.path.basename(p).startswith("_")]
    if len(paths) < 10:
        pytest.skip("the author's assets/animations/dossiers/ (10+ dossiers) is not shipped with the kit")
    assert len(paths) >= 10
    for p in paths:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        r = DE.read(d)                                        # (read only: an older dossier is never refused)
        if int(d.get("schema", 1)) < DE.SCHEMA:               # (a schema-3 one in the making may be refused: its own business)
            assert DE.missing(copy.deepcopy(d)) == [], os.path.basename(p)
        assert sum(r["counts"].values()) == len(r["phases"])
