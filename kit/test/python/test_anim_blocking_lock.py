"""kit/anim/blocking.py lock - POSES FIRST, MOTION AFTER (the owner, 2026-11-13: every method "enforced in the terms of
being used"; the studio route's A2): a move made after the rule, on a route whose key poses can be shown before any
motion exists, is not made at any build unless the owner's yes stands for its key poses as they are now. Made before
the rule = named in <anims>/blocks/_before_blocking.json. The move is a small strike generated in memory; the records
and the list are in temp folders."""
import copy
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import blocking as B        # noqa: E402

KEY = {"grip": [0.4, -0.4, -1.6], "dir": [0.2, 0.7, -0.7], "pos": [0, -0.6, 0], "right": [0.55, 0, 1.0],
       "left": [-0.57, 0, -0.7], "ease": "InOut"}
MOVE = {"name": "LockProbe", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4, "leg_slide": 1.3,
        "sword": {"length": 3.6, "grip": 0.5, "kind": "katana"},
        "keys": [dict(KEY, t=0.0, yaw=0), dict(KEY, t=0.2, yaw=20, grip=[0.9, 0.6, -0.6], dir=[0.3, 0.6, 0.75]),
                 dict(KEY, t=0.4, yaw=-20, grip=[-0.3, -0.6, -2.0], dir=[-0.5, -0.3, -0.8]),
                 dict(KEY, t=0.7, yaw=-10, grip=[-0.2, -0.5, -1.8], dir=[-0.4, -0.2, -0.85])]}
DAY = "2026-11-13"
NAME = "LockProbe"


def setup(tmp_path, move=None):
    anims, out = str(tmp_path / "anims"), str(tmp_path / "out")
    os.makedirs(anims, exist_ok=True)
    path = str(tmp_path / f"{NAME}.move.json")
    with open(path, "w") as fh:
        json.dump(move or MOVE, fh)
    return anims, out, path


def say_yes(anims, out, path, source="move"):
    m = B.make(NAME, out, anims, from_move=path, today=DAY)
    rec = B.approve(B.load_record(anims, NAME), "yes, those poses", m["poses"], by="owner", today=DAY, source=source)
    B.save_record(anims, NAME, rec)
    return m


def turn_pose_3(path):
    changed = copy.deepcopy(MOVE)
    changed["keys"][2]["yaw"] = 10                           # pose 3 turned 30 degrees
    with open(path, "w") as fh:
        json.dump(changed, fh)


def held(anims, path, kind="move", where=None, gesture=None, name=NAME):
    r = B.lock([(name, kind, path if where is None else where, gesture)], anims)
    return r["held"].get(name), r["free"].get(name)


# ---------------------------------------------------------------- made before the rule, made after it
def test_a_move_nobody_showed_him_is_held(tmp_path):
    anims, _, path = setup(tmp_path)
    why, free = held(anims, path)
    assert free is None and "has not been shown its key poses" in why


def test_a_move_made_before_the_rule_is_never_asked(tmp_path):
    anims, _, path = setup(tmp_path)
    for f, ext in (("Old", ".move.json"), ("OldPick", ".dossier.json"), ("_private", ".move.json"), ("Posed", ".pose.json")):
        open(os.path.join(anims, f + ext), "w").write("{}")
    listed, names = B.freeze(anims, today=DAY)
    assert names == ["Old", "OldPick"]                        # the strike moves and the picks; never a posed file
    assert json.load(open(listed))["frozen"] == DAY
    r = B.lock([("Old", "move", str(tmp_path / "gone.move.json"), None), (NAME, "move", path, None)], anims)
    assert "made before the rule" in r["free"]["Old"] and NAME in r["held"]       # ... even with its file unreadable
    with pytest.raises(ValueError, match="frozen once and never extended"):
        B.freeze(anims)


def test_a_built_model_frees_nothing(tmp_path):
    anims, _, path = setup(tmp_path)
    os.makedirs(str(tmp_path / "models"))
    open(str(tmp_path / "models" / f"{NAME}.model.json"), "w").write("{}")      # (the first rule: a file anybody can make)
    assert held(anims, path)[0] is not None


def test_a_list_that_cannot_be_read_holds_everything_and_says_so(tmp_path):
    anims, _, path = setup(tmp_path)
    os.makedirs(os.path.join(anims, "blocks"))
    open(B.before_path(anims), "w").write("{not json")
    with pytest.raises(ValueError, match="never delete it"):
        B.lock([(NAME, "move", path, None)], anims)


# ---------------------------------------------------------------- his yes, as it stands now
def test_his_yes_to_the_poses_as_they_are_frees_it_at_every_build(tmp_path):
    anims, out, path = setup(tmp_path)
    say_yes(anims, out, path)
    for _ in range(2):                                        # the first build and every one after it
        why, free = held(anims, path)
        assert why is None and "approved by the owner" in free


def test_a_yes_to_poses_that_changed_since_is_no_yes(tmp_path):
    anims, out, path = setup(tmp_path)
    say_yes(anims, out, path)
    turn_pose_3(path)
    why, _ = held(anims, path)
    assert "was to another blocking" in why and "pose 3" in why


def test_a_note_without_a_yes_holds_it_and_quotes_the_note(tmp_path):
    anims, out, path = setup(tmp_path)
    m = B.make(NAME, out, anims, from_move=path, today=DAY)
    B.save_record(anims, NAME, B.add_note(B.load_record(anims, NAME), 2, "lower, wider", m["poses"], today=DAY))
    why, _ = held(anims, path)
    assert "lower, wider" in why and "not answered" in why


def test_a_yes_taken_on_a_clip_is_still_held_to_the_keys(tmp_path):
    anims, out, path = setup(tmp_path)
    say_yes(anims, out, path, source="clip")                 # (a clip built from these very keys: the same poses)
    assert held(anims, path)[0] is None
    turn_pose_3(path)                                        # the keys are no longer that clip's
    assert "pose 3" in held(anims, path)[0]


@pytest.mark.parametrize("approved, why", [
    ({"source": "clip"}, "not the owner's"),
    ({"source": "clip", "poses": [], "by": "owner"}, "holds no poses"),
    ({"by": "owner", "words": "yes", "id": "abc", "poses": [{"k": 1}]}, "holds no poses"),
    ({"by": "claude", "words": "yes"}, "not the owner's"),
])
def test_a_record_typed_by_hand_is_no_yes(tmp_path, approved, why):
    anims, _, path = setup(tmp_path)
    B.save_record(anims, NAME, {"schema": 1, "name": NAME, "notes": [], "history": [], "approved": approved})
    assert why in held(anims, path)[0]


def test_a_yes_whose_poses_were_edited_by_hand_is_no_yes(tmp_path):
    anims, out, path = setup(tmp_path)
    say_yes(anims, out, path)
    rec = B.load_record(anims, NAME)
    rec["approved"]["poses"][2]["frame"] += 3                # the stored poses no longer carry the id he approved
    B.save_record(anims, NAME, rec)
    assert "edited by hand" in held(anims, path)[0]


def test_a_move_or_a_record_that_cannot_be_read_is_held(tmp_path):
    anims, out, path = setup(tmp_path)
    say_yes(anims, out, path)
    open(path, "w").write("{not json")
    assert "could not be read" in held(anims, path)[0]
    json.dump(MOVE, open(path, "w"))
    open(B.record_path(anims, NAME), "w").write('"a string, not a record"')
    assert "could not be read" in held(anims, path)[0]
    bad = dict(MOVE, feel="no_such_tier")                    # (the builder refuses by exiting: still one held line)
    json.dump(bad, open(path, "w"))
    open(B.record_path(anims, NAME), "w").write(json.dumps({"approved": None, "notes": [], "history": []}))
    say = B.lock([(NAME, "move", path, None)], anims)
    assert NAME in say["held"]


# ---------------------------------------------------------------- dossiers: which routes have poses before motion
def dossier(monkeypatch, build):
    import proc_dossier as DS
    monkeypatch.setattr(DS, "require", lambda name: {"build": build})


def test_a_hit_reaction_is_free_and_says_why(tmp_path, monkeypatch):
    anims, _, _ = setup(tmp_path)
    dossier(monkeypatch, {"builder": "proc_react"})
    why, free = held(anims, None, "blade", "hit_probe", name="HitProbe")
    assert why is None and "simulated from an impulse" in free
    dossier(monkeypatch, {"builder": "proc_kick"})           # (a kick dossier with no keyed poses: nothing to show)
    why, free = held(anims, None, "blade", "kick_probe", name="KickProbe")
    assert why is None and "holds no keyed poses" in free


def test_a_kick_keyed_in_its_dossier_is_held_until_his_yes_to_those_poses(tmp_path):
    """(read only: the kit home's own kick dossier - its eleven keyed poses, built in memory)"""
    if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "dossiers", "roundhouse_kick.json")):
        pytest.skip("this project has no roundhouse_kick dossier")
    anims, out = str(tmp_path / "anims"), str(tmp_path / "out")
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        r = B.lock([("KickNew", "blade", "roundhouse_kick", None)], anims)
        assert "has not been shown its key poses" in r["held"]["KickNew"] and r["how"]["KickNew"] == ["blade", "roundhouse_kick", None]
        m = B.make("KickNew", out, anims, dossier="roundhouse_kick", today=DAY)
        assert m["source"] == "gesture" and len(m["poses"]) == 11 and m["poses"][0]["key"]        # its dossier's own keys
        assert m["made_from"] == ["assets/animations/dossiers/roundhouse_kick.json"]
        rec = B.approve(B.load_record(anims, "KickNew"), "yes", m["poses"], by="owner", today=DAY, source=m["source"])
        B.save_record(anims, "KickNew", rec)
        assert B.lock([("KickNew", "blade", "roundhouse_kick", None)], anims)["held"] == {}
        # (a COMMITTED hit-reaction dossier: uppercut_reaction.json was only ever a local, untracked file - on the
        # committed tree it is missing and the "no dossier" refusal fired first, 2026-11-17)
        with pytest.raises(ValueError, match="makes a hit reaction"):
            B.source_clip("HitNew", dossier="head_hook_reaction")
    finally:
        os.chdir(cwd)


def test_a_dossier_built_on_a_strike_move_file_is_held_to_that_files_keys(tmp_path, monkeypatch):
    anims, out, path = setup(tmp_path)
    dossier(monkeypatch, {"builder": "strike", "move_file": path})
    r = B.lock([(NAME, "blade", "its_dossier", None)], anims)
    assert NAME in r["held"] and r["how"][NAME] == ["move", path, None]         # shown from the move file, said so
    say_yes(anims, out, path)
    assert B.lock([(NAME, "blade", "its_dossier", None)], anims)["held"] == {}
    turn_pose_3(path)
    assert "pose 3" in B.lock([(NAME, "blade", "its_dossier", None)], anims)["held"][NAME]


def test_a_sword_gesture_is_held_until_his_yes_to_its_poses_as_they_are(tmp_path, monkeypatch):
    import proc_blade as PB
    anims, out, path = setup(tmp_path)
    dossier(monkeypatch, {"builder": "proc_blade"})
    monkeypatch.setattr(PB, "gesture_for", lambda d, name: {"name": "a_gesture"})
    r = B.lock([(NAME, "blade", "", None)], anims)           # no dossier named: the snake_case of the name
    assert NAME in r["held"] and r["how"][NAME] == ["blade", "lock_probe", None]
    say_yes(anims, out, path, source="gesture")
    seen, real = {}, B.poses_now

    def gesture_poses(name, from_move=None, dossier=None, gesture=None):
        seen["args"] = (name, from_move, dossier, gesture)
        return real(name, path)                              # (the gesture's poses: this test's strike stands in)
    monkeypatch.setattr(B, "poses_now", gesture_poses)
    assert B.lock([(NAME, "blade", "", None)], anims)["held"] == {} and seen["args"] == (NAME, None, "lock_probe", None)
    assert B.lock([(NAME, "blade", "its_dossier", "a_gesture")], anims)["held"] == {}
    assert seen["args"] == (NAME, None, "its_dossier", "a_gesture")
    # his later yes on a PICK's own poses supersedes the record's yes, not the gesture's: the gesture yes still stands
    rec = B.load_record(anims, NAME)
    m = B.make(NAME, out, anims, from_move=path, today=DAY)
    B.save_record(anims, NAME, B.approve(rec, "and this pick", m["poses"], by="owner", today=DAY, source="clip"))
    assert B.lock([(NAME, "blade", "", None)], anims)["held"] == {}
    # ... but a clip yes alone is not the yes that comes before any motion
    only_clip = B.load_record(anims, NAME)
    only_clip["history"] = []
    B.save_record(anims, NAME, only_clip)
    assert "the yes that comes before any motion is to its gesture's key poses" in B.lock([(NAME, "blade", "", None)], anims)["held"][NAME]


def test_a_sword_dossier_that_names_no_gesture_is_free(tmp_path, monkeypatch):
    import proc_blade as PB
    anims, _, _ = setup(tmp_path)
    dossier(monkeypatch, {"builder": "fp_weapon"})

    def none(d, name):
        raise SystemExit("proc_blade: no gesture")
    monkeypatch.setattr(PB, "gesture_for", none)
    why, free = held(anims, None, "blade", "gun_fire", name="GunNew")
    assert why is None and "names no sword gesture" in free


def test_the_real_sword_route_reads_a_real_gesture(tmp_path):
    """(read only: the kit home's own sword dossier and its gesture, no stand-ins)"""
    if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "dossiers", "greatsword.json")):
        pytest.skip("this project has no greatsword dossier")
    anims = str(tmp_path / "anims")
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        r = B.lock([("SwordTrickCutNew", "blade", "greatsword", None)], anims)
        assert "has not been shown its key poses" in r["held"]["SwordTrickCutNew"]
        poses = B.poses_now("SwordTrickCutNew", None, "greatsword", None)
        assert len(poses) >= 6
        rec = B.approve(B.load_record(anims, "SwordTrickCutNew"), "yes", poses, by="owner", today=DAY, source="gesture")
        B.save_record(anims, "SwordTrickCutNew", rec)
        assert B.lock([("SwordTrickCutNew", "blade", "greatsword", None)], anims)["held"] == {}
    finally:
        os.chdir(cwd)


# ---------------------------------------------------------------- the command
def run_cli(*args):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "anim", "blocking.py"), *args], capture_output=True,
                       text=True, encoding="utf-8", cwd=ROOT)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


def test_the_lock_as_a_command_stops_and_says_how_to_show_him(tmp_path):
    anims, out, path = setup(tmp_path)
    code, v = run_cli("lock", f"{NAME}=move={path}", "--anims", anims)
    assert code == 1 and v["status"] == "fail"
    assert v["summary"].startswith(f"anim {NAME}: STOP - a NEW move, and its key poses do not have the owner's yes")
    assert "Poses first, motion after" in v["summary"]
    assert v["next_action"].startswith(f"lune run kit anim block {NAME} --sheet --move {path}")
    assert "--approve" in v["next_action"] and "--by owner --id" in v["next_action"]
    say_yes(anims, out, path)
    code, v = run_cli("lock", f"{NAME}=move={path}", "--anims", anims)
    assert code == 0 and v["status"] == "pass" and v["free"][NAME].startswith("approved by the owner")


def test_several_moves_name_every_one_that_is_held_and_a_path_may_hold_an_equals_sign(tmp_path):
    anims, out, path = setup(tmp_path)
    odd = tmp_path / "a=b"
    odd.mkdir()
    other = str(odd / "Other.move.json")
    with open(other, "w") as fh:
        json.dump(dict(MOVE, name="Other"), fh)
    code, v = run_cli("lock", f"{NAME}=move={path}", f"Other=move={other}", "--anims", anims)
    assert code == 1 and sorted(v["held"]) == [NAME, "Other"] and f"held: {NAME}, Other" in v["summary"]
    assert "has not been shown" in v["held"]["Other"]         # (read through the folder named a=b, not cut at the "=")
    code, v = run_cli("lock", f"{NAME}:{path}", "--anims", anims)
    assert code == 1 and "is not <Name>=move=<move.json>" in v["summary"]


def test_freeze_as_a_command(tmp_path):
    anims, _, _ = setup(tmp_path)
    open(os.path.join(anims, "Old.move.json"), "w").write("{}")
    code, v = run_cli("freeze", "--anims", anims)
    assert code == 0 and "1 move(s) made before the rule" in v["summary"]
    code, v = run_cli("freeze", "--anims", anims)
    assert code == 1 and "frozen once" in v["summary"]
