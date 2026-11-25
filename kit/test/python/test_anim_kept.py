"""kit/anim/blocking.py `kept` (the animation studio route's A4): the FINISHED clip held to the poses the owner
approved, each at its own moment. On the loved kesa (the kit's fixture, read only): a clip rebuilt from the approved
keys keeps every pose to 0.0 degrees; the same move with ONE key turned 15 degrees is named (the pose, what is off,
how far); a clip retimed, slowed, cut short, or with its blade turned or moved in the hand is no longer it; a stepped
build and a 30-a-second copy of the same motion still are; a move with no approved blocking has nothing to be held to."""
import copy
import json
import math
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import blocking as B        # noqa: E402
import strike as S          # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")


def loved():
    with open(LOVED, encoding="utf-8") as fh:
        return json.load(fh)


def clip_of(move):
    move = copy.deepcopy(move)
    move.pop("step", None)
    return S.generate(move)[0]


def turned(deg, key=2):
    m = loved()
    m["keys"][key]["yaw"] = float(m["keys"][key].get("yaw", 0.0)) + deg
    return m


@pytest.fixture()
def approved(tmp_path):
    """the loved kesa's blocking with the owner's yes -> (the record, the anims folder, the manifest)"""
    anims, out = str(tmp_path / "anims"), str(tmp_path / "out")
    move = str(tmp_path / "Kesa.move.json")
    with open(move, "w") as fh:
        json.dump(loved(), fh)
    m = B.make("Kesa", out, anims, from_move=move)
    rec = B.approve(B.load_record(anims, "Kesa"), "yes, those poses", m["poses"], by="owner",
                    timing={"duration": m["duration"], "hit": m["hit"]}, source=m["source"])
    assert m["source"] == "move"
    B.save_record(anims, "Kesa", rec)
    return rec, anims, m


def test_a_clip_rebuilt_from_the_approved_keys_keeps_every_pose(approved):
    rec, _, m = approved
    r = B.kept(clip_of(loved()), rec)
    assert r["state"] == "kept" and r["lost"] == [] and r["id"] == m["id"]
    assert [x["pose"] for x in r["rows"]] == [1, 2, 3, 4, 5, 6]
    assert max(x["deg"] for x in r["rows"]) == 0.0 and max(x["studs"] for x in r["rows"]) == 0.0
    assert [x["nearest_t"] for x in r["rows"]] == [p["t"] for p in m["poses"]]      # each found at its own moment
    assert max(x["blade_deg"] for x in r["rows"]) == 0.0 and max(x["tip"] for x in r["rows"]) == 0.0


def test_a_key_turned_fifteen_degrees_after_his_yes_is_named_with_its_limb(approved):
    rec, _, _ = approved
    r = B.kept(clip_of(turned(15.0)), rec)
    assert r["state"] == "drifted" and [x["pose"] for x in r["lost"]] == [3] and r["length"] is None
    lost = r["lost"][0]
    assert lost["joint"] in B.JOINTS and 14.0 < lost["deg"] < 18.0     # (the nearest moment within the window: 15 of the 16.6)
    words = B.lost_words(lost)
    assert words.startswith("pose 3 (approved at 0.32 s, nearest in the clip at 0.3") and "deg from the pose he approved (10 allowed)" in words
    by_pose = {x["pose"]: x for x in r["rows"]}
    assert by_pose[4]["kept"] and by_pose[5]["kept"] and 0 < by_pose[5]["deg"] < 10      # carried along, inside the bar
    assert by_pose[1]["deg"] == 0.0


def test_the_bar_sits_between_an_unchanged_build_and_a_changed_key(approved):
    rec, _, _ = approved
    assert B.kept(clip_of(turned(8.0)), rec)["state"] == "kept"         # under the bar here (the blocking itself is stale:
    assert B.kept(clip_of(turned(8.0)), rec, tol_deg=5.0)["state"] == "drifted"     # kit anim block --state says so)
    assert B.kept(clip_of(turned(15.0)), rec, tol_deg=20.0)["state"] == "kept"


def test_a_stepped_build_of_the_same_keys_still_keeps_them(approved):
    """(the review: `step {"on": 2}` with no beats steps NOTHING, so the first version of this test proved nothing - and
    a really stepped build failed: around a key the kesa turns 12 to 19 degrees a frame, and a pose held on twos shows
    the frame before. A stepped clip is read on its smooth motion: steps are presentation)"""
    rec, _, _ = approved
    for on in (2, 3, 4):
        stepped = loved()
        stepped["step"] = {"on": on, "beats": "all"}
        clip = S.generate(stepped)[0]
        assert clip.get("stepped") and clip["joints"]["Torso"]["frames"] != clip_of(loved())["joints"]["Torso"]["frames"]
        r = B.kept(clip, rec)
        assert r["state"] == "kept", (on, [(x["pose"], x["deg"]) for x in r["rows"]])


def test_a_thirty_a_second_copy_of_the_same_motion_is_found_between_its_frames(approved):
    rec, _, _ = approved
    c = clip_of(loved())
    idx = list(range(0, len(c["times"]), 2))                  # the approved keys sit on odd frames: between these samples
    half = copy.deepcopy(c)
    half["fps"] = 30
    half["times"] = [c["times"][i] for i in idx]
    for j in half["joints"]:
        half["joints"][j]["frames"] = [c["joints"][j]["frames"][i] for i in idx]
    for k in ("tip", "grip_path", "edge"):
        half["sword"][k] = [c["sword"][k][i] for i in idx]
    r = B.kept(half, rec)
    assert r["state"] == "kept" and max(x["deg"] for x in r["rows"]) < 8.0


def test_a_retimed_a_slowed_or_a_shortened_clip_is_not_the_blocking_he_approved(approved):
    """(the review: the first version stretched any clip onto the approved one - a copy three times slower passed with
    0.0 degrees. His yes was to the poses AT their timing)"""
    rec, _, _ = approved
    c = clip_of(loved())
    n = len(c["times"])

    def resampled(pick, count):
        out = copy.deepcopy(c)
        out["times"] = [i / 60 for i in range(count)]
        for j in out["joints"]:
            out["joints"][j]["frames"] = [c["joints"][j]["frames"][pick(i)] for i in range(count)]
        for k in ("tip", "grip_path", "edge"):
            out["sword"][k] = [c["sword"][k][pick(i)] for i in range(count)]
        return out
    slow = B.kept(resampled(lambda i: i // 3, (n - 1) * 3 + 1), rec)   # every pose is still in it, three times as late
    assert slow["state"] == "drifted" and slow["length"] == {"clip_s": 2.55, "approved_s": 0.85} and len(slow["lost"]) >= 4
    cut = B.kept(resampled(lambda i: i, int(n * 0.6)), rec)             # the clip is over before the finish
    assert cut["state"] == "drifted" and cut["rows"][-1]["past_end"] == 0.5 and cut["rows"][-1]["kept"] is False
    assert "the clip ends at 0.50 s, before this pose" in B.lost_words(cut["rows"][-1])
    assert all(x["kept"] for x in cut["rows"][:4])                      # what it does show, it shows where he approved it
    later = loved()
    for k in later["keys"]:
        k["t"] = round(k["t"] * 1.5, 4)
    for b in later.get("beats", {}):
        later["beats"][b] = [round(x * 1.5, 4) for x in later["beats"][b]]
    retimed = B.kept(clip_of(later), rec)                               # the same keys, every time half as long again
    assert retimed["state"] == "drifted" and retimed["length"]["approved_s"] == 0.85 and len(retimed["lost"]) >= 3
    tail = resampled(lambda i: min(i, n - 1), n + 30)                   # the same motion with half a second added on
    longer = B.kept(tail, rec)
    assert longer["state"] == "drifted" and longer["lost"] == [] and longer["length"]["clip_s"] > 1.3


def test_the_blade_is_part_of_the_pose_he_approved(approved):
    """(the review: only the joints and whether a blade exists were checked - a blade turned 20 degrees in the key, or
    its whole track moved 3.5 studs with the joints untouched, passed)"""
    rec, _, _ = approved
    c = clip_of(loved())
    moved = copy.deepcopy(c)
    moved["sword"]["tip"] = [[p[0] + 2.0, p[1] + 2.0, p[2] + 2.0] for p in moved["sword"]["tip"]]
    r = B.kept(moved, rec)
    assert r["state"] == "drifted" and len(r["lost"]) == 6
    assert r["rows"][0]["deg"] == 0.0 and r["rows"][0]["tip"] > 3.4 and r["rows"][0]["blade_deg"] > 10      # the joints never moved
    words = B.lost_words(r["rows"][0])
    assert "the blade points" in words and "the blade's tip is 3.46 studs away (1.25 allowed)" in words
    assert B.lost_bits(r["rows"][0])[0][0] == "the blade"
    aimed = loved()
    v, a = aimed["keys"][2]["dir"], math.radians(20.0)
    aimed["keys"][2]["dir"] = [v[0] * math.cos(a) - v[2] * math.sin(a), v[1], v[0] * math.sin(a) + v[2] * math.cos(a)]
    r = B.kept(clip_of(aimed), rec)
    assert r["state"] == "drifted" and any(x["blade_deg"] > 10 for x in r["lost"])
    assert B.kept(moved, rec, tol_tip=5.0, tol_deg=90.0)["state"] == "kept"      # the bars are what decides


def test_the_blade_the_game_plays_is_held_too(approved):
    """(the owner's V3 list, anim stage B.2; card r66z): the game keys the weapon by the clip's GRIP track (the Handle
    joint, kit/anim/grip.py) - a pass that turned only that track 30 degrees left the designed sword paths as they were
    and the kept check, which read only those, said kept"""
    import grip as GR
    import numpy as np
    rec, _, _ = approved
    c = GR.add_grip(clip_of(loved()))                                             # (the build adds it: kit anim)
    assert c.get("grip") and B.kept(c, rec)["state"] == "kept"                     # as built: both blades agree
    played = GR.played_sword(c)
    assert max(float(np.linalg.norm(np.subtract(a, b))) for a, b in zip(played["tip"], c["sword"]["tip"])) < 0.01
    turned_grip = copy.deepcopy(c)
    a = math.radians(30.0)
    R = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])   # about the Handle's X
    import clip as C
    for row in turned_grip["grip"]:
        q = C.mat_quat(np.array(C.quat_mat(row[:4])) @ R)
        row[:4] = [float(v) for v in q]
    r = B.kept(turned_grip, rec)
    assert r["state"] == "drifted" and r["lost"] and any(x["played"] for x in r["lost"])
    assert any("as the game plays it (its grip track)" in B.lost_words(x) for x in r["lost"])


def test_a_slid_limb_and_a_missing_blade_are_drift_too(approved):
    rec, _, _ = approved
    clip = clip_of(loved())
    low = copy.deepcopy(clip)
    for row in low["joints"]["Torso"]["frames"]:
        row[5] -= 0.4                                                  # the whole body 0.4 studs lower than he approved
    r = B.kept(low, rec)
    assert r["state"] == "drifted" and len(r["lost"]) == 6 and r["lost"][0]["slide_joint"] == "Torso"
    assert "Torso sits 0.40 studs off (0.25 allowed)" in B.lost_words(r["lost"][0])
    bare = copy.deepcopy(clip)
    bare.pop("sword")
    r = B.kept(bare, rec)
    assert r["state"] == "drifted" and all(x["blade_gone"] for x in r["lost"])
    assert "the blade is there in one and not in the other" in B.lost_words(r["lost"][0])


def test_the_window_takes_up_a_late_limb_and_no_more(approved):
    rec, _, _ = approved
    clip = clip_of(loved())
    late = copy.deepcopy(clip)                                         # the whole move two frames late
    for j in late["joints"]:
        fr = late["joints"][j]["frames"]
        late["joints"][j]["frames"] = [fr[0], fr[0]] + fr[:-2]
    for k in ("tip", "grip_path", "edge"):
        tr = late["sword"][k]
        late["sword"][k] = [tr[0], tr[0]] + tr[:-2]
    r = B.kept(late, rec)
    assert r["state"] == "kept" and r["rows"][2]["nearest_t"] > r["rows"][2]["approved_t"]
    assert B.kept(late, rec, window_s=0.0)["state"] == "drifted"       # looked for only at its own frame: gone


def test_a_tolerance_is_a_positive_number(approved):
    rec, _, _ = approved
    for bad in ({"tol_deg": 0.0}, {"tol_studs": 0.0}, {"tol_tip": -1.0}, {"window_s": -0.1}):
        with pytest.raises(ValueError, match="a tolerance is a positive number"):
            B.kept(clip_of(loved()), rec, **bad)


def test_a_yes_to_a_gestures_neutral_blocking_is_said_but_is_no_gate(approved, tmp_path):
    """a procedural pick's efforts re-pose its gesture by design: a build must not fail against the neutral gesture he
    approved - the difference is said, with what to do (take his yes on the pick's own poses)"""
    rec, anims, _ = approved
    rec["approved"]["source"] = "gesture"
    B.save_record(anims, "Kesa", rec)
    bad = str(tmp_path / "pick.clip.json")
    json.dump(clip_of(turned(15.0)), open(bad, "w"))
    code, v = run_cli("kept", "Kesa", "--clip", bad, "--anims", anims)
    assert code == 0 and v["status"] == "pass" and v["state"] == "differs" and "NOT HELD AS A GATE" in v["summary"]
    assert "on 1 of 6 pose(s) - pose 3" in v["summary"] and v["next_action"].startswith("improve the record: show him THIS clip's own poses")
    good = str(tmp_path / "same.clip.json")
    json.dump(clip_of(loved()), open(good, "w"))
    code, v = run_cli("kept", "Kesa", "--clip", good, "--anims", anims)
    assert code == 0 and v["state"] == "kept"


def test_no_approved_blocking_is_nothing_to_hold_a_clip_to(tmp_path):
    rec = B.load_record(str(tmp_path / "anims"), "Kesa")
    assert B.kept(clip_of(loved()), rec) == {"state": "none", "rows": [], "lost": [], "length": None}
    B.add_note(rec, 1, "lower", B.poses_of(clip_of(loved()), [0]))     # notes alone are no approval
    assert B.kept(clip_of(loved()), rec)["state"] == "none"


def run_cli(*args):
    r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "anim", "blocking.py"), *args], capture_output=True,
                       text=True, encoding="utf-8", cwd=ROOT)
    return r.returncode, json.loads(r.stdout.strip().splitlines()[-1])


def test_kept_as_a_command(approved, tmp_path):
    _, anims, m = approved
    good, bad = str(tmp_path / "good.clip.json"), str(tmp_path / "bad.clip.json")
    json.dump(clip_of(loved()), open(good, "w"))
    json.dump(clip_of(turned(15.0)), open(bad, "w"))
    code, v = run_cli("kept", "Kesa", "--clip", good, "--anims", anims)
    assert code == 0 and v["state"] == "kept"
    assert f"keeps the 6 pose(s) the owner approved, each at its own moment (blocking {m['id']}" in v["summary"]
    assert max(x["deg"] for x in v["rows"]) == 0.0
    code, v = run_cli("kept", "Kesa", "--clip", bad, "--anims", anims)
    assert code == 1 and v["state"] == "drifted" and "DRIFTS from the blocking the owner approved" in v["summary"]
    assert "on 1 of 6 pose(s) - pose 3" in v["summary"] and "deg from the pose he approved (10 allowed)" in v["summary"]
    lost = next(x for x in v["rows"] if not x["kept"])
    assert v["next_action"].startswith(f"bring pose 3 back to what he approved (the pass that moved {lost['joint']})")
    code, v = run_cli("kept", "Kesa", "--clip", bad, "--anims", anims, "--tol-deg", "20")
    assert code == 0 and v["state"] == "kept"
    code, v = run_cli("kept", "Kesa", "--clip", bad, "--anims", anims, "--tol-deg", "0")      # (it was a ZeroDivisionError)
    assert code == 1 and v["status"] == "fail" and "a tolerance is a positive number" in v["summary"]
    code, v = run_cli("kept", "Other", "--clip", bad, "--anims", anims)             # a move with no blocking record
    assert code == 0 and v["state"] == "none" and "nothing to hold the clip to" in v["summary"]
    code, v = run_cli("kept", "Kesa", "--clip", str(tmp_path / "gone.clip.json"), "--anims", anims)
    assert code == 1 and "no finished clip" in v["summary"]
