"""strike.py AAA gaps v2 wave 2: exaggeration push (B1), the impact dip (B8), moving holds (B2), mixed cadence (B7)"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C     # noqa: E402
import strike as S   # noqa: E402

KEY = {"grip": [0.4, -0.4, -1.6], "dir": [0.2, 0.7, -0.7], "pos": [0, -0.6, 0], "right": [0.55, 0, 1.0],
       "left": [-0.57, 0, -0.7], "ease": "InOut"}
MOVE = {"name": "AppealProbe", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4, "leg_slide": 1.3,
        "sword": {"length": 3.6, "grip": 0.5, "kind": "katana"},
        "keys": [dict(KEY, t=0.0, yaw=0), dict(KEY, t=0.2, yaw=20, grip=[0.9, 0.6, -0.6], dir=[0.3, 0.6, 0.75]),
                 dict(KEY, t=0.4, yaw=-20, grip=[-0.3, -0.6, -2.0], dir=[-0.5, -0.3, -0.8]),
                 dict(KEY, t=0.9, yaw=-20, grip=[-0.3, -0.6, -2.0], dir=[-0.5, -0.3, -0.8])]}


def gen(**kw):
    m = json.loads(json.dumps(MOVE))
    m.update(kw)
    return S.generate(m)[0]


def test_push_scales_offsets_from_the_guard_and_spares_owner_poses():
    keys = S.fill_keys(json.loads(json.dumps(MOVE["keys"])))
    out = S.apply_push(keys, {"push": 1.2})
    assert out[0] == keys[0] and abs(out[1]["yaw"] - 24.0) < 1e-6 and abs(out[2]["yaw"] + 24.0) < 1e-6
    keys[1]["arms_pose"] = {"Right Arm": [0, 0, 0, 1, 0, 0, 0]}
    assert S.apply_push(keys, {"push": 1.2})[1]["yaw"] == keys[1]["yaw"]
    assert S.apply_push(keys, {}) is keys


def test_impact_dip_lowers_its_key():
    keys = S.fill_keys(json.loads(json.dumps(MOVE["keys"])))
    out = S.apply_impact_dip(keys, {"impact_dip": {"key": 2, "dy": -0.12}})
    assert abs(out[2]["pos"][1] - (keys[2]["pos"][1] - 0.12)) < 1e-9 and out[1] == keys[1]


def test_moving_hold_breathes_a_frozen_hold_and_keeps_the_hands_on_the_hilt():
    plain = gen()
    held = gen(moving_hold={"min": 0.15, "drift": 2.0, "breath": 1.0})
    assert held.get("moving_holds"), "the 0.4-0.9 s hold was found"
    i = int(0.65 * 60)
    a = C.quat_angle(plain["joints"]["Torso"]["frames"][i][:4], held["joints"]["Torso"]["frames"][i][:4])
    assert 0.3 < a < 3.0                                           # the torso settles, a little
    rig = C.load_rig("r6")
    for clip in (plain, held):                                     # the sword stays in the hand the same way
        RA = C.world_frames(clip, rig)[i]["Right Arm"]
        g = np.linalg.inv(RA) @ np.append(clip["sword"]["grip_path"][i], 1.0)
        clip["_g"] = g[:3]
    assert np.linalg.norm(plain["_g"] - held["_g"]) < 1e-3


def test_arms_on_ones_keeps_the_blade_smooth_while_the_body_steps():
    c = gen(step={"on": 2, "beats": "all", "arms_on": 1})
    tips = np.array(c["sword"]["tip"])
    moves = np.linalg.norm(np.diff(tips[:25], axis=0), axis=1)     # the swing (0-0.4 s; the move holds still after)
    assert (moves[2:] > 1e-6).all()                                # the blade moves every frame (not held on twos)
    T = c["joints"]["Torso"]["frames"]
    assert any(T[i] == T[i + 1] for i in range(1, 20))             # the body holds


def test_marker_contract_warp_and_kick():
    """D11 / C5 / D9: every strike carries Swing <= ActiveStart <= Hit <= ActiveEnd, a camera kick at the Hit, and a
    warp window when it travels"""
    c = gen()
    t = {e["name"]: e["t"] for e in c["events"]}
    assert set(S.MARKERS) <= set(t)
    assert t["Swing"] <= t["ActiveStart"] <= t["Hit"] <= t["ActiveEnd"]
    k = c["camera_kick"]
    assert abs(k["t"] - t["Hit"]) < 1e-9 and abs(np.linalg.norm(k["dir"]) - 1) < 1e-3
    assert "warp" not in c                                          # it does not travel


def test_upper_mask_drops_the_legs():
    """D4: an upper-body move keys no leg, so locomotion keeps the legs in game"""
    c = gen(mask="upper")
    assert "Right Leg" not in c["joints"] and "Left Leg" not in c["joints"] and c["mask"] == "upper"
    assert "Right Arm" in c["joints"] and "Torso" in c["joints"]


def test_smear_marker_is_opt_in_and_sits_on_the_fastest_frames():
    """B6: no smear unless the move asks; asked, the Smear marker opens just before the blade's speed peak, at or
    before the Hit, naming its parts and seconds"""
    assert "Smear" not in {e["name"] for e in gen()["events"]}
    c = gen(smear={"parts": "Right Arm,Blade", "s": 0.05})
    sm = next(e for e in c["events"] if e["name"] == "Smear")
    hit = next(e["t"] for e in c["events"] if e["name"] == "Hit")
    assert sm["value"] == "Right Arm,Blade;0.05" and sm["t"] <= hit + 1e-9 and hit - sm["t"] < 0.3


def test_camera_track_keys_are_checked_and_carried():
    """D9: a finisher's camera keys are sorted, the FOV clamped, a degenerate key refused"""
    c = gen(camera=[{"t": 0.6, "loc": [4, 3, -6], "target": [0, 2, -3], "fov": 200},
                    {"t": 0.0, "loc": [0, 4, 8], "target": [0, 2, 0]}])
    assert [k["t"] for k in c["camera"]] == [0.0, 0.6] and c["camera"][1]["fov"] == 120.0
    try:
        S.camera_keys([{"t": 0, "loc": [1, 1, 1], "target": [1, 1, 1]}])
        raise AssertionError("a camera looking at itself was accepted")
    except ValueError:
        pass
