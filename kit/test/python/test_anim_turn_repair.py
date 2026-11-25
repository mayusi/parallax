"""kit/anim/turn_repair.py - the repair for a joint that turns faster than the frames can carry (fast_turns.py's
NOT DONE; card gtut). The fixtures are made here (an arm swung with one snap in it); no judged clip is changed."""
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C           # noqa: E402
import fast_turns as FT    # noqa: E402
import turn_repair as TR   # noqa: E402


def quat(axis, deg):
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    h = math.radians(deg) / 2
    return [*(a * math.sin(h)), math.cos(h)]


def swing(fps=60, steps=None, n=21):
    """the Right Arm turned about X by the given degrees a frame (default 20 each, one 150 at frame 10)"""
    steps = steps or {10: 150.0}
    ang, frames = 0.0, []
    for i in range(n):
        if i:
            ang += steps.get(i, 20.0)
        frames.append(quat((1, 0, 0), ang) + [0, 0, 0])
    times = [round(i / fps, 6) for i in range(n)]
    return {"name": "FixSwing", "rig": "R6", "fps": fps, "times": times, "duration": times[-1],
            "events": [{"name": "Start", "t": 0.0}, {"name": "Hit", "t": times[12]}],
            "beats": {"follow": [times[11], times[15]]},
            "joints": {"Right Arm": {"frames": frames}, "Torso": {"frames": [[0, 0, 0, 1, 0, 0, 0]] * n}}}


def same(a, b):
    return C.quat_angle(a[:4], b[:4]) < 1e-4


def test_a_snap_is_eased_over_more_frames_every_pose_kept_and_time_after_it_moved_on():
    clip = swing()
    assert FT.read(clip)["over"]
    fixed, r = TR.repair(clip)
    assert FT.read(fixed)["over"] == [] and r["after"]["deg"] <= TR.TARGET and r["over_after"] == 0
    assert r["eased"] == [{"frame": 10, "t": round(10 / 60, 4), "joint": "Right Arm", "deg": 150.0, "frames": 2}]
    old, new = clip["joints"]["Right Arm"]["frames"], fixed["joints"]["Right Arm"]["frames"]
    assert len(new) == len(old) + 1
    assert all(same(old[i], new[i]) for i in range(10)) and all(same(old[i], new[i + 1]) for i in range(10, len(old)))
    assert abs(C.quat_angle(new[9][:4], new[10][:4]) - 75) < 1e-3                   # half the snap a frame, the same way
    assert r["longer_by"] == pytest.approx(1 / 60, abs=1e-6) and fixed["duration"] == pytest.approx(clip["duration"] + 1 / 60, abs=1e-6)
    assert fixed["events"][0]["t"] == 0 and fixed["events"][1]["t"] == pytest.approx(clip["events"][1]["t"] + 1 / 60, abs=1e-6)
    assert fixed["beats"]["follow"] == pytest.approx([b + 1 / 60 for b in clip["beats"]["follow"]], abs=1e-6)
    assert len(fixed["joints"]["Torso"]["frames"]) == len(new) and len(fixed["times"]) == len(new)
    assert fixed["source"]["turn_repair"]["eased"] and r["long_way"] == []


def test_a_near_half_turn_goes_the_way_the_joint_was_turning_and_says_so():
    # forward 40 a frame, then a step of 200 forward: stored, that is 160 BACK the short way
    clip = swing(steps={**{i: 40.0 for i in range(1, 21)}, 10: 200.0})
    fixed, r = TR.repair(clip)
    assert r["long_way"] and r["long_way"][0]["joint"] == "Right Arm"
    fr = fixed["joints"]["Right Arm"]["frames"]
    e = r["eased"][0]
    k = e["frames"]
    assert e["deg"] == pytest.approx(200.0, abs=1e-3) and k == 3
    for j in range(9, 9 + k):                                                     # each in-between turns forward
        d = TR._rotvec(fr[j][:4], fr[j + 1][:4])
        assert d[0] > 0 and math.degrees(np.linalg.norm(d)) == pytest.approx(200 / 3, abs=1e-3)
    assert FT.read(fixed)["over"] == []


def test_a_clip_kept_at_30_a_second_is_given_frames_between_its_time_unchanged():
    clip = swing(fps=30, steps={10: 100.0})
    fixed, r = TR.repair(clip)
    assert r["upsampled"] and r["longer_by"] == 0 and fixed["fps"] == 60
    assert len(fixed["times"]) == 2 * len(clip["times"]) - 1 and fixed["times"][-1] == clip["times"][-1]
    old, new = clip["joints"]["Right Arm"]["frames"], fixed["joints"]["Right Arm"]["frames"]
    assert all(same(old[i], new[2 * i]) for i in range(len(old)))
    assert r["after"]["deg"] == pytest.approx(50, abs=1e-3) and FT.read(fixed)["over"] == []
    assert fixed["events"] == clip["events"]


def test_what_it_will_not_repair_is_said():
    stepped = swing()
    stepped["stepped"] = [[0.1, 0.2, 2]]
    with pytest.raises(ValueError, match="stepped clip"):
        TR.repair(stepped)
    short = swing()
    short["grip"] = [[0, 0, 0, 1, 0, 0, 0]] * 5                                   # a weapon track that fell behind
    with pytest.raises(ValueError, match="grip has 5 frame"):
        TR.repair(short)
    with pytest.raises(ValueError):
        TR.repair({"times": [0]})
    calm = swing(steps={10: 20.0})
    fixed, r = TR.repair(calm)
    assert r["eased"] == [] and fixed["times"] == calm["times"]                   # nothing to repair: nothing changed


def test_the_tracks_that_ride_along_are_eased_with_the_joints():
    clip = swing()
    n = len(clip["times"])
    clip["grip"] = [quat((0, 1, 0), 5 * i) + [0, 0, 0] for i in range(n)]
    clip["sword"] = {"tip": [[0, -i * 0.1, 0] for i in range(n)]}
    fixed, _ = TR.repair(clip)
    assert len(fixed["grip"]) == n + 1 and len(fixed["sword"]["tip"]) == n + 1
    assert fixed["sword"]["tip"][10] == pytest.approx([0, -0.95, 0])               # half way between frames 9 and 10
    assert C.quat_angle(fixed["grip"][10][:4], quat((0, 1, 0), 47.5)) < 1e-3


def test_the_repaired_copy_is_held_to_every_other_gate_and_what_it_added_is_said(tmp_path):
    clip = swing()
    fixed, _ = TR.repair(clip)
    assert TR.held(clip, fixed) == []                                              # the fixture's repair adds nothing
    broken = TR.copy.deepcopy(fixed)
    broken["joints"]["Torso"]["frames"][15] = quat((0, 1, 0), 60) + [0, 0, 0]       # one frame turned, calm beside it
    added = TR.held(clip, broken)
    assert added and any("skid" in a for a in added) and any(a.startswith("Hit lands") for a in added), added
    before = set(os.listdir(tmp_path))
    p = tmp_path / "FixSwing.clip.json"
    p.write_text(TR.json.dumps(clip), encoding="utf-8")
    TR.gates(TR.C.load_clip(str(p)))
    assert set(os.listdir(tmp_path)) == before | {"FixSwing.clip.json"}            # nothing written beside the clip


def test_review_d2_the_long_way_only_near_a_half_turn_and_with_real_turns_beside_it():
    settle = swing(steps={**{i: 0.0 for i in range(1, 21)}, 9: 2.0, 10: 100.0, 11: -2.0})
    fixed, r = TR.repair(settle)                                  # 100 deg, the arm settling back 2 beside it: short
    assert r["long_way"] == [] and r["longer_by"] == pytest.approx(1 / 60, abs=1e-6)
    jitter = swing(steps={**{i: 0.0 for i in range(1, 21)}, 9: -0.001, 10: 170.0})
    _, r = TR.repair(jitter)                                      # a jitter does not say which way: short
    assert r["long_way"] == []


def test_review_d2_the_camera_kick_moves_grip_rot_is_slerped_one_vector_is_no_path_a_handoff_is_refused():
    clip = swing()
    n = len(clip["times"])
    clip["camera_kick"] = {"amp": 0.2, "t": clip["times"][12]}
    clip["sword"] = {"grip_rot": [quat((0, 0, 1), 3 * i) for i in range(n)], "dir_local": [0, 1, 0]}
    fixed, _ = TR.repair(clip)
    assert fixed["camera_kick"]["t"] == pytest.approx(clip["times"][12] + 1 / 60, abs=1e-6)
    gr = fixed["sword"]["grip_rot"]
    assert len(gr) == n + 1 and abs(np.linalg.norm(gr[10]) - 1) < 1e-6 and fixed["sword"]["dir_local"] == [0, 1, 0]
    handed = swing()
    handed["handoff"] = {"object": "Mag"}
    with pytest.raises(ValueError, match="solve its handoff again"):
        TR.repair(handed)


def test_review_d2_a_30_a_second_clips_weapon_paths_get_their_frames_between_too():
    clip = swing(fps=30, steps={10: 100.0})
    n = len(clip["times"])
    clip["sword"] = {"tip": [[0, -0.1 * i, 0] for i in range(n)], "dir_local": [0, 1, 0]}
    fixed, _ = TR.repair(clip)
    assert len(fixed["sword"]["tip"]) == len(fixed["times"]) == 2 * n - 1
    assert fixed["sword"]["tip"][1] == pytest.approx([0, -0.05, 0])
