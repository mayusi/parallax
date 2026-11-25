"""kit/anim/block.py + strike.py key_edits - the BLOCKING PASS (AAA plan #1): the owner's key-pose changes are read as
per-key deltas and ride on the keys through every rebuild"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import block as BL    # noqa: E402
import strike as S    # noqa: E402

MOVE = {"name": "BlockProbe", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4, "leg_slide": 1.3,
        "sword": {"length": 3.6, "grip": 0.5, "kind": "katana"},
        "keys": [{"t": 0.0, "yaw": 0, "grip": [0.4, -0.4, -1.6], "dir": [0.2, 0.7, -0.7], "pos": [0, -0.6, 0],
                  "right": [0.55, 0, 1.0], "left": [-0.57, 0, -0.7], "ease": "InOut"},
                 {"t": 0.2, "yaw": 20, "grip": [0.9, 0.6, -0.6], "dir": [0.3, 0.6, 0.75], "pos": [0, -0.6, 0],
                  "right": [0.55, 0, 1.0], "left": [-0.57, 0, -0.7], "ease": "InOut"},
                 {"t": 0.4, "yaw": -20, "grip": [-0.3, -0.6, -2.0], "dir": [-0.5, -0.3, -0.8], "pos": [0, -0.6, 0],
                  "right": [0.55, 0, 1.0], "left": [-0.57, 0, -0.7], "ease": "InOut"}]}


def _gen(**kw):
    m = json.loads(json.dumps(MOVE))
    m.update(kw)
    return S.generate(m)[0], m


def test_no_edits_is_unchanged():
    a, _ = _gen()
    b, _ = _gen(key_edits={"keys": {}})
    assert a == b
    assert S.apply_key_edits(MOVE["keys"], None) is MOVE["keys"]


def test_edits_read_back_what_changed_and_apply_reproduces_it():
    a, m = _gen()
    ed = {"keys": {"1": {"yaw": 10.0}, "2": {"right": [0.3, 0.0]}}}
    b, _ = _gen(key_edits=ed)
    got = BL.edits(a, b, m)["keys"]
    assert set(got) == {"1", "2"}                                        # only the edited keys
    assert abs(got["1"]["yaw"] - 10.0) < 1.5                           # the turn, its sign right
    assert abs(got["2"]["right"][0] - 0.3) < 0.06 and abs(got["2"]["right"][1]) < 0.06
    same = BL.edits(a, a, m)
    assert same["keys"] == {} and "hip_offset" not in same             # the identity round trip


def test_apply_key_edits_moves_the_fields():
    k = S.apply_key_edits(MOVE["keys"], {"keys": {"0": {"grip": [0.1, 0.0, -0.2], "pitch": 5, "pos_y": -0.1,
                                                         "left": [0.0, 0.2], "dir": [0.0, 0.1, 0.0]}}})
    assert k[0]["grip"] == [0.5, -0.4, -1.8] and k[0]["pitch"] == 5 and abs(k[0]["pos"][1] + 0.7) < 1e-9
    assert k[0]["left"] == [-0.57, 0, -0.5]
    assert abs(np.linalg.norm(k[0]["dir"]) - 1.0) < 1e-3
    assert MOVE["keys"][0]["grip"] == [0.4, -0.4, -1.6]                  # the authored keys are never mutated


def test_review_fixes_euler_readback_merge_and_sparse_keys():
    """review 2026-10-18: a yaw on a pitched key read back with a fake roll; a second round replaced the first; an edit
    on a key that inherits its field was read as absolute / dropped"""
    m = json.loads(json.dumps(MOVE))
    m["keys"][1]["pitch"] = -18
    a = S.generate(json.loads(json.dumps(m)))[0]
    b = S.generate(dict(json.loads(json.dumps(m)), key_edits={"keys": {"1": {"yaw": 15.0}}}))[0]
    got = BL.edits(a, b, m)["keys"]["1"]
    assert abs(got["yaw"] - 15.0) < 1.0 and abs(got.get("roll", 0.0)) < 1.0 and abs(got.get("pitch", 0.0)) < 1.0
    one = {"keys": {"1": {"yaw": 5.0, "grip": [0.1, 0, 0]}}, "hip_offset": {"left": [0, 0.2, 0]}}
    two = {"keys": {"1": {"yaw": 2.0}, "2": {"pitch": 3.0}}, "hip_offset": {"left": [0, 0.1, -0.1]}}
    mg = BL.merge(one, two)
    assert mg["keys"]["1"] == {"yaw": 7.0, "grip": [0.1, 0, 0]} and mg["keys"]["2"] == {"pitch": 3.0}
    assert mg["hip_offset"]["left"] == [0.0, 0.3, -0.1]
    sparse = [{"t": 0.0, "yaw": 20, "grip": [0.4, 0.2, -1.4]}, {"t": 0.3}]
    k = S.apply_key_edits(sparse, {"keys": {"1": {"yaw": 5.0, "grip": [0.1, 0.0, 0.0]}}})
    assert k[1]["yaw"] == 25.0 and k[1]["grip"] == [0.5, 0.2, -1.4]     # on the INHERITED values


def test_owner_arm_poses_replace_the_solved_arms_and_blend_out():
    """strike.py apply_arm_poses (owner 2026-10-19: 'THE ARMS ... ITS THE POSES'): a key's arms_pose is reproduced
    exactly at that key; a key without one blends back to the solved arms; no poses = unchanged"""
    import clip as C
    base = S.generate(json.loads(json.dumps(MOVE)))[0]
    pose = {"Right Arm": [0.2, 0.3, 0.1, 0.926, 0.1, 0.0, 0.0], "Left Arm": [0.0, 0.1, -0.2, 0.975, 0.0, 0.1, 0.0],
            "grip_local": [0.0, -1.25, 0.0], "tip_local": [0.0, -1.25, -3.3]}
    m = json.loads(json.dumps(MOVE))
    m["keys"][1]["arms_pose"] = pose
    c = S.generate(m)[0]
    f = int(round(m["keys"][1]["t"] * 60))
    q = np.array(c["joints"]["Right Arm"]["frames"][f][:4])
    want = np.array(pose["Right Arm"][:4]) / np.linalg.norm(pose["Right Arm"][:4])
    assert abs(abs(float(q @ want)) - 1.0) < 1e-4                       # his pose AT his key
    assert c["joints"]["Right Arm"]["frames"][0] == base["joints"]["Right Arm"]["frames"][0]   # the start solved
    rig = C.load_rig("r6")
    RA = C.world_frames(c, rig)[f]["Right Arm"]
    g = (RA @ np.array([0.0, -1.25, 0.0, 1.0]))[:3]
    assert np.linalg.norm(g - np.array(c["sword"]["grip_path"][f])) < 1e-3   # the sword in his hand
    assert S.generate(json.loads(json.dumps(MOVE)))[0] == base


def test_block_keys_name_the_poses_a_dense_move_is_blocked_at():
    """2026-11-04 (a drill spin keyed every 30 deg for the solver): `block_keys` names the move's KEY POSES - the
    blocking holds only those, and the owner's edits are read only there"""
    m = json.loads(json.dumps(MOVE))
    assert BL.key_frames(m) == [0, 12, 24]
    m["block_keys"] = [0.0, 0.4]
    assert BL.key_frames(m) == [0, 24]
    c, _ = S.generate(json.loads(json.dumps(MOVE)))
    e = json.loads(json.dumps(c))
    for fr in e["sword"]["grip_path"][12:]:
        fr[1] += 0.3                                   # the owner raised the hilt from the middle key on
    res = BL.edits(c, e, m)
    assert 1 not in res["keys"] and "1" not in res["keys"], res["keys"].keys()   # (not a block key: not read)
