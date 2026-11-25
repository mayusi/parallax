"""kit/anim/blocking.py (the animation studio route's A2): a move's key poses HELD at its own timing, the owner's
notes kept with the pose he saw (answered when it changed, open while it did not), and his yes that goes stale when
any pose changes. The move here is a small strike generated in memory; the record goes to a temp folder (a real
move's record lives in assets/animations/blocks/); the sheet's pictures are the pose sheet test's fake render."""
import copy
import json
import os
import subprocess
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
sys.path.insert(0, HERE)
import blocking as B        # noqa: E402
import pose_sheet as PS     # noqa: E402
import strike as S          # noqa: E402

KEY = {"grip": [0.4, -0.4, -1.6], "dir": [0.2, 0.7, -0.7], "pos": [0, -0.6, 0], "right": [0.55, 0, 1.0],
       "left": [-0.57, 0, -0.7], "ease": "InOut"}
MOVE = {"name": "BlockProbe", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4, "leg_slide": 1.3,
        "sword": {"length": 3.6, "grip": 0.5, "kind": "katana"},
        "keys": [dict(KEY, t=0.0, yaw=0), dict(KEY, t=0.2, yaw=20, grip=[0.9, 0.6, -0.6], dir=[0.3, 0.6, 0.75]),
                 dict(KEY, t=0.4, yaw=-20, grip=[-0.3, -0.6, -2.0], dir=[-0.5, -0.3, -0.8]),
                 dict(KEY, t=0.7, yaw=-10, grip=[-0.2, -0.5, -1.8], dir=[-0.4, -0.2, -0.85])]}
DAY = "2026-11-13"


def write_move(tmp_path, move=None, name="BlockProbe.move.json"):
    path = str(tmp_path / name)
    with open(path, "w") as fh:
        json.dump(move or MOVE, fh)
    return path


def made(tmp_path, move=None, today=DAY):
    anims, out = str(tmp_path / "anims"), str(tmp_path / "out")
    return B.make("BlockProbe", out, anims, from_move=write_move(tmp_path, move), today=today), anims, out


def turned(key=1, yaw=45):
    m = copy.deepcopy(MOVE)
    m["keys"][key]["yaw"] = yaw
    return m


# ---------------------------------------------------------------- the held clip and its poses
def test_the_blocking_holds_each_key_pose_until_the_next_one():
    clip = S.generate(copy.deepcopy(MOVE))[0]
    frames = B.key_frames(clip, MOVE)
    assert frames == [0, 12, 24, 42]
    h = B.held(clip, frames, "BlockProbe")
    assert h["times"] == clip["times"] and h["events"] == clip["events"]          # the move's own length and Hit
    assert h["name"] == "BlockProbeBlocking" and h["source"] == {"kind": "blocking", "of": "BlockProbe", "frames": frames}
    for j in clip["joints"]:
        for i in range(len(clip["times"])):
            src = max(f for f in frames if f <= i)
            assert h["joints"][j]["frames"][i] == clip["joints"][j]["frames"][src]
    assert h["sword"]["tip"][23] == clip["sword"]["tip"][12] and h["sword"]["tip"][24] == clip["sword"]["tip"][24]
    assert h["sword"]["length"] == clip["sword"]["length"]                         # (a number is not a track)
    assert clip["joints"]["Torso"]["frames"][18] != clip["joints"]["Torso"]["frames"][12]   # the move itself moves there


def test_the_first_frame_is_always_a_pose_and_moments_two_frames_apart_are_one():
    clip = S.generate(copy.deepcopy(MOVE))[0]
    assert B.key_frames(clip, None, at=[0.2, 0.21, 0.4]) == [0, 12, 24]
    assert B.key_frames(clip, {"block_keys": [0.4, 0.7]}) == [0, 24, 42]              # a densely keyed move names its poses


def test_every_pose_says_how_long_it_is_held_and_names_its_shape():
    clip = S.generate(copy.deepcopy(MOVE))[0]
    poses = B.poses_of(clip, B.key_frames(clip, MOVE))
    assert [p["k"] for p in poses] == [1, 2, 3, 4]
    assert [p["hold_s"] for p in poses[:3]] == [0.2, 0.2, 0.3]
    assert abs(sum(p["hold_s"] for p in poses) - (clip["times"][-1] + 1 / 60)) < 1e-3   # the holds fill the whole move
    again = B.poses_of(S.generate(copy.deepcopy(MOVE))[0], B.key_frames(clip, MOVE))
    assert [p["id"] for p in again] == [p["id"] for p in poses]                      # a rebuild is the same blocking
    assert B.blocking_id(again) == B.blocking_id(poses)
    other = S.generate(turned())[0]
    theirs = B.poses_of(other, B.key_frames(other, MOVE))
    assert theirs[1]["id"] != poses[1]["id"] and theirs[0]["id"] == poses[0]["id"]
    assert B.blocking_id(theirs) != B.blocking_id(poses)


def test_a_pose_and_its_negated_quaternions_are_the_same_pose():
    clip = S.generate(copy.deepcopy(MOVE))[0]
    a = B.snapshot(clip, 12)
    flipped = copy.deepcopy(clip)
    for j in flipped["joints"]:
        row = flipped["joints"][j]["frames"][12]
        row[:4] = [-v for v in row[:4]]
    b = B.snapshot(flipped, 12)
    assert B.pose_id(a) == B.pose_id(b)
    d = B.pose_delta(a, b)
    assert d["deg"] == 0 and d["studs"] == 0 and not B.changed(d) and B.delta_words(d) == "unchanged"


def test_pose_delta_names_the_joint_that_turned_and_the_one_that_slid():
    clip = S.generate(copy.deepcopy(MOVE))[0]
    a = B.snapshot(clip, 12)
    b = copy.deepcopy(a)
    half = np.sin(np.radians(15.0))                            # the right arm turned 30 degrees about its own x
    q = np.array(b["joints"]["Right Arm"][:4])
    r = np.array([half, 0.0, 0.0, np.cos(np.radians(15.0))])
    x1, y1, z1, w1 = q
    x2, y2, z2, w2 = r
    b["joints"]["Right Arm"][:4] = [w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                                    w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2]
    b["joints"]["Torso"][5] -= 0.31
    b["blade"]["tip"][0] += 0.8
    d = B.pose_delta(a, b)
    assert d["joint"] == "Right Arm" and abs(d["deg"] - 30.0) < 0.05
    assert d["slide_joint"] == "Torso" and abs(d["studs"] - 0.31) < 1e-3 and abs(d["tip"] - 0.8) < 1e-3
    words = B.delta_words(d)
    assert "Right Arm turned 30.0 deg" in words and "Torso slid 0.31 studs" in words and "blade tip moved 0.80" in words
    small = copy.deepcopy(a)
    small["joints"]["Torso"][5] -= 0.01                         # under the bar: a rebuild's rounding is no change
    assert not B.changed(B.pose_delta(a, small))


# ---------------------------------------------------------------- the owner's notes
def test_a_note_stays_open_while_its_pose_is_as_he_saw_it(tmp_path):
    m, anims, out = made(tmp_path)
    assert m["state"] == "waiting" and not os.path.exists(B.record_path(anims, "BlockProbe"))   # nothing said: no record
    rec = B.add_note(B.load_record(anims, "BlockProbe"), 2, "lower, wider", m["poses"], today=DAY)
    B.save_record(anims, "BlockProbe", rec)
    m2, _, _ = made(tmp_path)
    assert m2["state"] == "notes open" and m2["id"] == m["id"]
    assert "pose 2" in m2["state_words"] and "lower, wider" in m2["state_words"] and "as he saw it" in m2["state_words"]
    note = m2["notes"][0]
    assert {k: note[k] for k in ("pose", "pose_said", "words", "by", "date", "state", "answered", "carried", "unsure", "gone")} == {
        "pose": 2, "pose_said": 2, "words": "lower, wider", "by": "owner", "date": DAY, "state": "open", "answered": None,
        "carried": None, "unsure": None, "gone": None}
    assert note["text"].startswith("THE OWNER, 2026-11-13 - NOT ANSWERED (that pose is as he saw it;") and PS.note_text(note) == note["text"]
    assert B.next_words(m2).startswith("look at pose 2 (the owner: \"lower, wider\") and change that pose")


def test_a_note_is_answered_when_its_pose_changed_and_only_then(tmp_path):
    m, anims, _ = made(tmp_path)
    rec = B.load_record(anims, "BlockProbe")
    B.add_note(rec, 2, "lower, wider", m["poses"], today=DAY)
    B.add_note(rec, 3, "the blade higher", m["poses"], today=DAY)
    B.save_record(anims, "BlockProbe", rec)
    m2, _, _ = made(tmp_path, turned(key=1, yaw=45), today="2026-11-14")           # pose 2 changed, pose 3 did not
    by_pose = {n["pose"]: n for n in m2["notes"]}
    assert by_pose[2]["state"] == "answered" and by_pose[2]["answered"]["date"] == "2026-11-14"
    assert "turned" in by_pose[2]["answered"]["changed"]
    assert by_pose[3]["state"] == "open"
    assert m2["state"] == "notes open" and "pose 3" in m2["state_words"]
    saved = json.load(open(B.record_path(anims, "BlockProbe")))                     # the answer is in the tracked record
    assert [n["state"] for n in saved["notes"]] == ["answered", "open"]


def test_a_pose_carried_along_by_another_poses_change_does_not_answer_its_note(tmp_path):
    """the loved kesa (the kit's fixture, read only): turning pose 3's key 15 degrees also moves poses 4 and 5 (the
    generator's overlap) - a note on pose 5 is NOT answered by that; it is when pose 5's own key is changed"""
    loved = json.load(open(os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")))
    m, anims, _ = made(tmp_path, loved)
    assert len(m["poses"]) == 6 and all(p["key"] for p in m["poses"])
    rec = B.add_note(B.load_record(anims, "BlockProbe"), 5, "the finish is too high", m["poses"], today=DAY)
    B.save_record(anims, "BlockProbe", rec)
    other = copy.deepcopy(loved)
    other["keys"][2]["yaw"] += 15.0
    m2, _, _ = made(tmp_path, other)
    assert B.changed(B.pose_delta(m["poses"][4], m2["poses"][4]))                 # pose 5 did move ...
    assert m2["poses"][4]["key"] == m["poses"][4]["key"] and m2["poses"][2]["key"] != m["poses"][2]["key"]
    assert m2["notes"][0]["state"] == "open" and "turned" in m2["notes"][0]["carried"]   # ... and that answers nothing
    assert "only changed with its neighbours" in m2["state_words"] and "only changed with its neighbours" in PS.note_text(m2["notes"][0])
    assert "if that is the answer, show him the sheet" in B.next_words(m2)
    other["keys"][4]["note"] = "tidied"                       # words on its own key change no pose: still not answered
    m2b, _, _ = made(tmp_path, other)
    assert m2b["poses"][4]["key"] == m["poses"][4]["key"] and m2b["notes"][0]["state"] == "open"
    other["keys"][4]["pitch"] = float(other["keys"][4].get("pitch", 0.0)) - 12.0
    m3, _, _ = made(tmp_path, other)
    assert m3["notes"][0]["state"] == "answered" and m3["notes"][0]["carried"] is None


def test_a_note_follows_its_pose_when_poses_are_added_or_dropped_before_it(tmp_path):
    """(the review, 2026-11-13: a key inserted before a noted pose made 'pose 3' another pose, and the note was
    reported answered with a change nobody made)"""
    m, anims, _ = made(tmp_path)
    rec = B.add_note(B.load_record(anims, "BlockProbe"), 3, "the blade higher", m["poses"], today=DAY)
    B.save_record(anims, "BlockProbe", rec)
    more = copy.deepcopy(MOVE)
    more["keys"].insert(1, dict(KEY, t=0.1, yaw=10, grip=[0.6, 0.1, -1.1], dir=[0.25, 0.65, 0.0]))
    m2, _, _ = made(tmp_path, more)
    note = m2["notes"][0]
    assert len(m2["poses"]) == 5 and note["state"] == "open" and note["pose"] == 4 and note["pose_said"] == 3
    assert m2["poses"][3]["key"] == m["poses"][2]["key"]                           # the same authored key, renumbered
    assert "pose 4" in m2["state_words"] and B.next_words(m2).startswith("look at pose 4 ")
    fewer = copy.deepcopy(MOVE)
    del fewer["keys"][1]
    m3, _, _ = made(tmp_path, fewer)
    assert len(m3["poses"]) == 3 and m3["notes"][0]["state"] == "open" and m3["notes"][0]["pose"] == 2
    back, _, _ = made(tmp_path)
    assert back["notes"][0]["pose"] == 3 and back["notes"][0]["state"] == "open"


def test_on_a_clip_a_changed_pose_is_shown_but_never_called_answered(tmp_path):
    """a clip has no authored keys: the kit cannot tell a pose that was corrected from one carried along by another's
    change, so it reports the change and leaves the note to his yes"""
    loved = json.load(open(os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")))
    anims, out, path = str(tmp_path / "anims"), str(tmp_path / "out"), str(tmp_path / "kesa.clip.json")
    at = [k["t"] for k in loved["keys"]]
    json.dump(S.generate(copy.deepcopy(loved))[0], open(path, "w"))
    m = B.make("BlockProbe", out, anims, clip_path=path, at=at, today=DAY)
    assert len(m["poses"]) == 6 and all(p["key"] is None for p in m["poses"])
    rec = B.load_record(anims, "BlockProbe")
    for k in (3, 5):
        B.add_note(rec, k, f"note on {k}", m["poses"], today=DAY)
    B.save_record(anims, "BlockProbe", rec)
    other = copy.deepcopy(loved)
    other["keys"][2]["yaw"] += 15.0
    json.dump(S.generate(other)[0], open(path, "w"))
    m2 = B.make("BlockProbe", out, anims, clip_path=path, at=at, today=DAY)
    assert [n["state"] for n in m2["notes"]] == ["open", "open"]
    assert all(n["unsure"] and n["carried"] is None for n in m2["notes"])
    assert "a clip has no keys to tell a correction from a pose carried along" in m2["state_words"]
    assert "NOT ANSWERED" in m2["notes"][1]["text"] and "his yes" in m2["notes"][1]["text"]


def test_a_longer_hold_is_shown_on_the_note_and_left_to_his_yes(tmp_path):
    """'hold this one longer' is answered by moving the NEXT pose: this pose's own key is untouched, so the kit shows
    the new hold and does not send the session to re-key the pose"""
    m, anims, _ = made(tmp_path)
    rec = B.add_note(B.load_record(anims, "BlockProbe"), 2, "hold this one longer", m["poses"], today=DAY)
    B.save_record(anims, "BlockProbe", rec)
    later = copy.deepcopy(MOVE)
    later["keys"][2]["t"] = 0.5
    m2, _, _ = made(tmp_path, later)
    note = m2["notes"][0]
    assert note["state"] == "open" and note["carried"] == "held 0.30 s (it was 0.20 s)"
    nxt = B.next_words(m2)
    assert "held 0.30 s (it was 0.20 s)" in nxt and "if that is the answer, show him the sheet (his yes closes the note)" in nxt



def test_a_note_about_timing_is_answered_by_a_retimed_pose(tmp_path):
    m, anims, _ = made(tmp_path)
    rec = B.add_note(B.load_record(anims, "BlockProbe"), 3, "hold the wind-up longer", m["poses"], today=DAY)
    B.save_record(anims, "BlockProbe", rec)
    later = copy.deepcopy(MOVE)
    later["keys"][2]["t"] = 0.5                                 # pose 3 arrives later: pose 2 is held longer
    m2, _, _ = made(tmp_path, later)
    assert m2["notes"][0]["state"] == "answered" and "moved from 0.40 s to 0.50 s" in m2["notes"][0]["answered"]["changed"]
    assert m2["state"] == "answered" and "his yes is not given yet" in m2["state_words"]


def test_a_note_needs_a_pose_that_exists_and_his_words(tmp_path):
    m, anims, _ = made(tmp_path)
    rec = B.load_record(anims, "BlockProbe")
    with pytest.raises(ValueError, match="no pose 9"):
        B.add_note(rec, 9, "lower", m["poses"])
    with pytest.raises(ValueError, match="needs the owner's words"):
        B.add_note(rec, 2, "  ", m["poses"])
    assert rec["notes"] == []


def test_a_note_whose_pose_is_gone_stays_open(tmp_path):
    m, anims, _ = made(tmp_path)
    rec = B.add_note(B.load_record(anims, "BlockProbe"), 4, "the finish is limp", m["poses"], today=DAY)
    B.save_record(anims, "BlockProbe", rec)
    short = copy.deepcopy(MOVE)
    short["keys"] = short["keys"][:3]                           # the fourth pose was dropped, not corrected
    m2, _, _ = made(tmp_path, short)
    note = m2["notes"][0]
    assert len(m2["poses"]) == 3 and note["state"] == "open" and m2["state"] == "notes open"
    assert note["pose"] is None and note["pose_said"] == 4 and note["gone"] is True
    assert "a pose that is gone" in m2["state_words"] and "as he saw it" not in m2["state_words"]
    assert "no longer in the blocking (it was pose 4 at 0.70 s" in m2["state_words"] and "no longer in the blocking" in note["text"]
    assert B.next_words(m2).startswith("look at the poses as they are now against his note on a pose that is gone")
    clip = json.load(open(m2["clip"]))
    pl = PS.plan("BlockProbe", clip, json.load(open(m2["move"])), clip_path=m2["clip"], blocking=m2)
    assert [n["words"] for n in pl["blocking"]["orphans"]] == ["the finish is limp"]      # said at the top of the sheet
    assert all(k["notes"] == [] for k in pl["keys"])
    back, _, _ = made(tmp_path)                                  # the pose is back as he saw it: the note is on it again
    assert back["notes"][0]["pose"] == 4 and back["notes"][0]["gone"] is None


# ---------------------------------------------------------------- his yes
def test_only_the_owner_approves_and_with_words(tmp_path):
    m, anims, _ = made(tmp_path)
    rec = B.load_record(anims, "BlockProbe")
    with pytest.raises(ValueError, match="only the owner"):
        B.approve(rec, "looks right", m["poses"], by="claude")
    with pytest.raises(ValueError, match="only the owner"):
        B.approve(rec, "looks right", m["poses"], by="")
    with pytest.raises(ValueError, match="needs the owner's words"):
        B.approve(rec, "", m["poses"], by="owner")
    assert rec["approved"] is None


def test_his_yes_holds_while_the_poses_do_and_goes_stale_when_one_changes(tmp_path):
    m, anims, _ = made(tmp_path)
    rec = B.approve(B.load_record(anims, "BlockProbe"), "yes, those poses", m["poses"], by="owner", today=DAY)
    B.save_record(anims, "BlockProbe", rec)
    assert rec["approved"]["id"] == m["id"] and len(rec["approved"]["poses"]) == 4
    m2, _, _ = made(tmp_path)
    assert m2["state"] == "approved" and "yes, those poses" in m2["state_words"] and m2["approved"]["id"] == m["id"]
    assert B.next_words(m2).startswith("none")
    m3, _, _ = made(tmp_path, turned(key=2, yaw=10))             # pose 3's torso turned 30 degrees after his yes
    assert m3["state"] == "stale" and m3["drift"] and m3["drift"][0].startswith("pose 3: ")
    assert "turned" in m3["drift"][0] and "another blocking" in m3["state_words"]
    assert B.next_words(m3).startswith("look at what changed after his yes (pose 3: ")
    more = copy.deepcopy(MOVE)
    more["keys"].insert(3, dict(KEY, t=0.55, yaw=-15, grip=[-0.25, -0.55, -1.9], dir=[-0.45, -0.25, -0.82]))
    m4, _, _ = made(tmp_path, more)                              # a pose was added
    assert m4["state"] == "stale" and "he approved 4 pose(s), there are 5 now" in m4["drift"][0]


def test_his_yes_closes_open_notes_and_a_later_note_reopens_the_blocking(tmp_path):
    m, anims, _ = made(tmp_path)
    rec = B.add_note(B.load_record(anims, "BlockProbe"), 2, "lower", m["poses"], today=DAY)
    rec = B.approve(rec, "fine as it is", m["poses"], by="owner", today=DAY)
    assert rec["notes"][0]["state"] == "closed" and B.state_of(rec, m["poses"])["state"] == "approved"
    rec = B.add_note(rec, 3, "actually, the blade higher", m["poses"], today="2026-11-14")
    assert rec["approved"] is None and rec["history"][0]["words"] == "fine as it is" and rec["history"][0]["why"] == "a note on pose 3"
    assert B.state_of(rec, m["poses"])["state"] == "notes open"


# ---------------------------------------------------------------- the command line
def run_cli(*args):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "anim", "blocking.py"), *args], capture_output=True,
                       text=True, encoding="utf-8", cwd=ROOT)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


def test_make_note_approve_and_state_as_commands(tmp_path):
    anims, out, move = str(tmp_path / "anims"), str(tmp_path / "out"), write_move(tmp_path)
    where = ["--out", out, "--anims", anims]
    code, v = run_cli("state", "BlockProbe", *where)
    assert code == 1 and "no blocking was made yet" in v["summary"]
    code, v = run_cli("make", "BlockProbe", "--from-move", move, *where)
    assert code == 0 and v["state"] == "waiting" and "4 key pose(s) held" in v["summary"]
    assert v["next_action"].startswith("look at ") and "--note <pose>" in v["next_action"]
    for name in ("blocking.clip.json", "blocking.move.json", "blocking.json"):
        assert os.path.isfile(os.path.join(out, name))
    assert [k["t"] for k in json.load(open(os.path.join(out, "blocking.move.json")))["keys"]] == [0.0, 0.2, 0.4, 0.7]
    code, v = run_cli("state", "BlockProbe", "--need", "approved", *where)
    assert code == 1 and v["state"] == "waiting"                                   # what a lock would ask
    code, v = run_cli("note", "BlockProbe", "9", "lower", *where)
    assert code == 1 and "no pose 9" in v["summary"]
    code, v = run_cli("note", "BlockProbe", "2", "lower, wider", *where)
    assert code == 0 and "pose 2" in v["summary"] and os.path.isfile(v["record"])
    code, v = run_cli("approve", "BlockProbe", "yes", *where)                      # nobody said it was the owner
    assert code == 1 and "only the owner" in v["summary"]
    code, v = run_cli("approve", "BlockProbe", "yes, block it like that", "--by", "owner", *where)
    assert code == 1 and "name the blocking he said yes to" in v["summary"]        # WHICH blocking did he see?
    code, v = run_cli("approve", "BlockProbe", "yes, block it like that", "--by", "owner", "--id", "0123456789ab", *where)
    assert code == 1 and "the blocking made last is another one" in v["summary"]
    made_id = json.load(open(os.path.join(out, "blocking.json")))["id"]
    code, v = run_cli("approve", "BlockProbe", "yes, block it like that", "--by", "owner", "--id", made_id, *where)
    assert code == 0 and "the owner's yes" in v["summary"]
    code, v = run_cli("state", "BlockProbe", "--need", "approved", *where)
    assert code == 0 and v["state"] == "approved"
    code, v = run_cli("make", "BlockProbe", "--from-move", write_move(tmp_path, turned(key=3, yaw=40)), *where)
    assert code == 0 and v["state"] == "stale"
    code, v = run_cli("state", "BlockProbe", "--need", "approved", *where)
    assert code == 1 and v["state"] == "stale" and v["drift"][0].startswith("pose 4: ")


def test_a_blocking_older_than_its_move_takes_no_note_no_yes_and_tells_no_state(tmp_path):
    """(the review: `state --need approved` said APPROVED after every key of the move was turned, because it read the
    poses of the last make; and a yes was recorded against whatever make ran last)"""
    anims, out, move = str(tmp_path / "anims"), str(tmp_path / "out"), write_move(tmp_path)
    where = ["--out", out, "--anims", anims]
    code, v = run_cli("make", "BlockProbe", "--from-move", move, *where)
    code, v = run_cli("approve", "BlockProbe", "yes", "--by", "owner", "--id", v["id"], *where)
    assert code == 0
    write_move(tmp_path, turned(key=1, yaw=60))                 # the move file changes; nobody re-made the blocking
    for args in (("state", "BlockProbe", "--need", "approved"), ("state", "BlockProbe"), ("note", "BlockProbe", "2", "lower"),
                 ("approve", "BlockProbe", "yes again", "--by", "owner", "--id", v.get("id", "x"))):
        code, r = run_cli(*args, *where)
        assert code == 1 and "OUT OF DATE" in r["summary"] and "the move changed since it was made" in r["summary"], args
        assert "--sheet" in r["next_action"]
    assert len(json.load(open(B.record_path(anims, "BlockProbe")))["notes"]) == 0  # nothing was taken on the old one
    code, v = run_cli("make", "BlockProbe", "--from-move", move, *where)
    assert code == 0 and v["state"] == "stale"
    os.remove(move)
    code, r = run_cli("state", "BlockProbe", *where)
    assert code == 1 and "a file it was made from is gone" in r["summary"]


def test_what_cannot_be_read_is_refused_in_one_line_never_a_traceback(tmp_path):
    anims, out, move = str(tmp_path / "anims"), str(tmp_path / "out"), write_move(tmp_path)
    where = ["--out", out, "--anims", anims]

    def refused(*args):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "anim", "blocking.py"), *args], capture_output=True,
                           text=True, encoding="utf-8", cwd=ROOT)
        v = json.loads(r.stdout.strip().splitlines()[-1])
        assert r.returncode == 1 and v["status"] == "fail" and "Traceback" not in r.stderr, (args, r.stderr[-300:])
        return v
    assert "could not be read or made" in refused("make", "BlockProbe", "--from-move", move, "--at", "abc", *where)["summary"]
    clip = S.generate(copy.deepcopy(MOVE))[0]
    clip["sword"]["tip"] = clip["sword"]["tip"][:-5]            # a blade track five frames short of the clip
    short = str(tmp_path / "short.clip.json")
    json.dump(clip, open(short, "w"))
    assert "could not be read or made" in refused("make", "BlockProbe", "--clip", short, "--at", "0.2,0.7", *where)["summary"]
    code, v = run_cli("make", "BlockProbe", "--from-move", move, *where)
    assert code == 0
    assert "names its pose by its number on the sheet (1 to 4)" in refused("note", "BlockProbe", "two", "lower", *where)["summary"]
    os.makedirs(os.path.join(anims, "blocks"), exist_ok=True)
    with open(B.record_path(anims, "BlockProbe"), "w") as fh:
        fh.write("{ not json")                                  # a record a person broke by hand
    for args in (("state", "BlockProbe"), ("note", "BlockProbe", "2", "lower"), ("make", "BlockProbe", "--from-move", move)):
        said = refused(*args, *where)["summary"]
        assert "BlockProbe.blocking.json is not valid JSON" in said and "repair it by hand, never delete it" in said
    with open(os.path.join(out, "blocking.json"), "w") as fh:
        fh.write("[")
    assert "blocking.json is not valid JSON" in refused("state", "BlockProbe", *where)["summary"]


def test_a_procedural_dossier_that_does_not_exist_is_refused_in_one_line(tmp_path):
    code, v = run_cli("make", "BlockProbe", "--dossier", "no_such_dossier_of_the_test", "--out", str(tmp_path / "out"),
                      "--anims", str(tmp_path / "anims"))
    assert code == 1 and v["status"] == "fail" and "no dossier for 'no_such_dossier_of_the_test'" in v["summary"]


def test_a_blade_track_one_frame_short_is_held_with_its_pose():
    clip = S.generate(copy.deepcopy(MOVE))[0]
    clip["sword"]["edge"] = clip["sword"]["edge"][:-1]
    h = B.held(clip, [0, 12, 24, 42], "BlockProbe")
    assert len(h["sword"]["edge"]) == len(clip["times"]) and h["sword"]["edge"][23] == clip["sword"]["edge"][12]


def test_a_source_must_be_named_and_an_r15_clip_is_refused(tmp_path):
    where = ["--out", str(tmp_path / "out"), "--anims", str(tmp_path / "anims")]
    code, v = run_cli("make", "BlockProbe", *where)
    assert code == 1 and "name the poses' source" in v["summary"]
    clip = S.generate(copy.deepcopy(MOVE))[0]
    clip["rig"] = "R15"
    path = str(tmp_path / "r15.clip.json")
    json.dump(clip, open(path, "w"))
    code, v = run_cli("make", "BlockProbe", "--clip", path, *where)
    assert code == 1 and "R15 clip" in v["summary"]


# ---------------------------------------------------------------- the sheet of a blocking
def test_the_sheet_shows_every_blocking_pose_with_its_hold_and_its_notes(tmp_path):
    dense = copy.deepcopy(MOVE)                                 # 13 poses: more than a sheet's ten
    dense["keys"] = [dict(KEY, t=round(0.1 * i, 2), yaw=5 * i) for i in range(13)]
    m, anims, out = made(tmp_path, dense)
    assert len(m["poses"]) == 13
    rec = B.add_note(B.load_record(anims, "BlockProbe"), 12, "the twelfth is stiff", m["poses"], today=DAY)
    B.save_record(anims, "BlockProbe", rec)
    m, _, _ = made(tmp_path, dense)
    clip = json.load(open(m["clip"]))
    pl = PS.plan("BlockProbe", clip, json.load(open(m["move"])), clip_path=m["clip"], blocking=m)
    assert [k["k"] for k in pl["keys"]] == list(range(1, 14))                       # never thinned: he approves all of it
    assert [k["frame"] for k in pl["keys"]] == [p["frame"] for p in m["poses"]]
    assert all(k["hold_s"] == p["hold_s"] for k, p in zip(pl["keys"], m["poses"]))
    assert [n["words"] for n in pl["keys"][11]["notes"]] == ["the twelfth is stiff"] and pl["keys"][10]["notes"] == []
    assert pl["blocking"] == {"of": "BlockProbe", "id": m["id"], "state": "notes open", "state_words": m["state_words"],
                              "poses": 13, "orphans": []}
    assert set(p["frame"] for p in m["poses"]) <= set(pl["strip_frames"])            # every pose's own frame is rendered
    plain = PS.plan("BlockProbe", clip, json.load(open(m["move"])), clip_path=m["clip"])
    assert plain["blocking"] is None and len(plain["keys"]) == 10 and "hold_s" not in plain["keys"][0]


def test_the_pages_say_it_is_a_blocking_and_carry_his_note_and_the_gif_plays_in_real_time(tmp_path):
    from PIL import Image
    from test_anim_pose_sheet import fake_render
    m, anims, out = made(tmp_path)
    clip = json.load(open(m["clip"]))

    def sheet(manifest):
        pl = PS.plan("BlockProbe", clip, json.load(open(manifest["move"])), clip_path=manifest["clip"], blocking=manifest)
        json.dump(pl, open(os.path.join(out, "plan.json"), "w"))
        fake_render(out, pl, clip)
        return PS.pages(out), Image.open(os.path.join(out, "pose_sheet.png")).size
    look, size = sheet(m)
    assert look["blocking"]["state"] == "waiting" and look["keys"][1]["hold_s"] == 0.2 and look["keys"][1]["notes"] == []
    assert look["look"].startswith(f"LOOK: {look['folder']}/ - BLOCKING {m['id']} of BlockProbe: its 4 key pose(s) HELD")
    assert "pose_sheet.png" in look["look"] and "(waiting: " in look["look"]
    rec = B.add_note(B.load_record(anims, "BlockProbe"), 2, "lower, wider", m["poses"], today=DAY)
    B.save_record(anims, "BlockProbe", rec)
    m2, _, _ = made(tmp_path)
    look2, size2 = sheet(m2)
    assert size2[0] == size[0] and 30 < size2[1] - size[1] < 120                    # one note = one bar on the sheet
    assert Image.open(os.path.join(out, look2["keys"][1]["pages"][0])).size[1] > Image.open(
        os.path.join(out, look2["keys"][0]["pages"][0])).size[1]                    # ... and on that pose's own page
    assert look2["keys"][1]["notes"][0]["state"] == "open" and "(notes open: " in look2["look"]
    assert "NOT ANSWERED" in PS.note_text(look2["keys"][1]["notes"][0])
    assert "ANSWERED 2026-11-14: Torso turned" in PS.note_text(
        {"date": DAY, "words": "lower", "state": "answered", "answered": {"date": "2026-11-14", "changed": "Torso turned 25.0 deg"}})
    path = B.gif(out)
    g = Image.open(path)
    durs = []
    for i in range(g.n_frames):
        g.seek(i)
        durs.append(g.info["duration"])
    assert g.n_frames == len(m2["poses"]) == 4 and g.size[0] <= B.GIF_WIDTH         # EVERY pose is in it, one frame each
    assert durs[:3] == [200, 200, 300]                                              # ... for as long as it is held
    assert abs(sum(durs) - (sum(p["hold_s"] for p in m2["poses"]) * 1000 + B.GIF_PAUSE_MS)) <= 10    # real time, then a pause


def test_a_pose_held_for_one_frame_is_still_in_the_gif(tmp_path):
    """(the review: the loved kesa's finish pose, on the clip's last frame, fell between the strip's frames and was
    never played)"""
    from PIL import Image
    from test_anim_pose_sheet import fake_render
    loved = json.load(open(os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")))
    m, anims, out = made(tmp_path, loved)
    clip = json.load(open(m["clip"]))
    pl = PS.plan("BlockProbe", clip, json.load(open(m["move"])), clip_path=m["clip"], blocking=m)
    assert m["poses"][-1]["frame"] == len(clip["times"]) - 1 and m["poses"][-1]["frame"] in pl["strip_frames"]
    json.dump(pl, open(os.path.join(out, "plan.json"), "w"))
    fake_render(out, pl, clip)
    g = Image.open(B.gif(out))
    assert g.n_frames == 6
    g.seek(5)
    assert g.info["duration"] >= 20 + B.GIF_PAUSE_MS


def test_the_gif_needs_the_sheets_strips(tmp_path):
    m, anims, out = made(tmp_path)
    clip = json.load(open(m["clip"]))
    pl = PS.plan("BlockProbe", clip, json.load(open(m["move"])), strips=False, clip_path=m["clip"], blocking=m)
    json.dump(pl, open(os.path.join(out, "plan.json"), "w"))
    with pytest.raises(ValueError, match="without strips"):
        B.gif(out)
