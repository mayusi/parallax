"""motion warping (kit/anim/warp.py): time warp, amplitude scale, additive spline offsets, transplant on the stride"""
import copy
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "anim"))
import clip as C  # noqa: E402
import warp as W  # noqa: E402

JOINTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]


def _q(ax, deg):
    a = math.radians(deg) / 2
    v = [0.0, 0.0, 0.0]
    v[ax] = math.sin(a)
    return v + [math.cos(a)]


def _cycle(n=41, period=40, shift=0, amp=40.0):
    """a 60 fps looping run-like clip: legs swing about X in opposition, arms counter-swing"""
    frames = {j: [] for j in JOINTS}
    for i in range(n):
        ph = 2 * math.pi * ((i + shift) % period) / period
        s = math.sin(ph)
        frames["Right Leg"].append(_q(0, amp * s) + [0, 0, 0])
        frames["Left Leg"].append(_q(0, -amp * s) + [0, 0, 0])
        frames["Right Arm"].append(_q(0, -amp * s) + [0, 0, 0])
        frames["Left Arm"].append(_q(0, amp * s) + [0, 0, 0])
        frames["Torso"].append(_q(1, 8 * s) + [0, 0.1 * abs(s), 0])
        frames["Head"].append(_q(1, -4 * s) + [0, 0, 0])
    return {"name": "t", "rig": "R6", "fps": 60, "loop": True, "times": [i / 60 for i in range(n)],
            "joints": {j: {"frames": f} for j, f in frames.items()}}


def _angle(a, b):
    return C.quat_angle(a[:4], b[:4])


def test_time_warp_changes_duration_and_keeps_the_motion():
    c = _cycle()
    w = W.time_warp(copy.deepcopy(c), factor=0.9)
    assert abs(w["times"][-1] - c["times"][-1] * 0.9) < 1 / 60 + 1e-9
    assert w["fps"] == 60 and np.allclose(np.diff(w["times"]), 1 / 60, atol=1e-5)
    # the frame at the warped time of the old peak is the old peak
    i_old = 10
    i_new = int(round(i_old * 0.9))
    assert _angle(w["joints"]["Right Leg"]["frames"][i_new], c["joints"]["Right Leg"]["frames"][i_old]) < 3.0
    same = W.time_warp(copy.deepcopy(c), factor=1.0)
    assert max(_angle(a, b) for a, b in zip(same["joints"]["Right Leg"]["frames"], c["joints"]["Right Leg"]["frames"])) < 1e-3


def test_amp_scale_grows_one_axis_about_the_mean():
    c = _cycle()
    big = W.amp_scale(copy.deepcopy(c), "Right Leg", "X", 1.5)
    r0 = max(_angle(f, [0, 0, 0, 1]) for f in c["joints"]["Right Leg"]["frames"])
    r1 = max(_angle(f, [0, 0, 0, 1]) for f in big["joints"]["Right Leg"]["frames"])
    assert abs(r1 / r0 - 1.5) < 0.05
    same = W.amp_scale(copy.deepcopy(c), "Right Leg", "Y", 3.0)       # the leg does not move on Y: nothing changes
    assert max(_angle(a, b) for a, b in zip(same["joints"]["Right Leg"]["frames"], c["joints"]["Right Leg"]["frames"])) < 0.5


def test_additive_offsets_ride_on_the_dense_base_and_keep_the_loop_closed():
    c = _cycle()
    off = W.additive(copy.deepcopy(c), "Right Arm", [{"t": 0.0, "rot": [0, 0, 20]}, {"t": 0.33, "rot": [0, 0, 5]}])
    F, G = off["joints"]["Right Arm"]["frames"], c["joints"]["Right Arm"]["frames"]
    assert abs(_angle(F[0], G[0]) - 20) < 0.5                       # the key is hit
    assert _angle(F[0], F[-1]) < 0.5                                # periodic spline: the seam stays closed
    # the dense base still shows through: the per-frame motion is kept
    assert abs(_angle(F[5], F[6]) - _angle(G[5], G[6])) < 1.0


def test_transplant_lines_the_donor_up_on_the_base_stride():
    base = _cycle(n=41, period=40)
    donor = _cycle(n=49, period=48, shift=12, amp=25.0)              # slower cycle, a quarter-cycle out of phase
    out, info = W.transplant(base, donor, ["Right Arm"])
    assert abs(info["scale"] - 1.2) < 1e-3
    assert info["swing_corr"] > 0.99
    # after the warp the donor arm swings in time with the base: compare against the base arm scaled to 25/40
    a = W.leg_swing({"joints": {"x": out["joints"]["Right Arm"]}}, "x")
    b = W.leg_swing({"joints": {"x": base["joints"]["Right Arm"]}}, "x") * 25 / 40
    assert np.max(np.abs(a - b)) < 2.0
    assert out["joints"]["Right Leg"] == base["joints"]["Right Leg"]


def test_hold_mean_moves_the_average_pose_and_keeps_the_motion():
    import derive as D
    c = _cycle()
    out = W.hold_mean(copy.deepcopy(c), "Right Arm", [-15, 0, 5])
    F = out["joints"]["Right Arm"]["frames"]
    mean = D.qmean([f[:4] for f in F])
    assert C.quat_angle(mean, C.mat_quat(C.euler_mat([-15, 0, 5]))) < 1.0
    G = c["joints"]["Right Arm"]["frames"]
    assert abs(_angle(F[3], F[9]) - _angle(G[3], G[9])) < 0.5     # frame-to-frame motion unchanged


def test_delay_shifts_a_loop_and_keeps_it_closed():
    c = _cycle()
    out = W.delay(copy.deepcopy(c), "Right Arm", 2)
    F, G = out["joints"]["Right Arm"]["frames"], c["joints"]["Right Arm"]["frames"]
    assert _angle(F[12], G[10]) < 1e-3 and _angle(F[0], F[-1]) < 1e-3


def test_counter_keeps_the_legs_world_turn_while_the_torso_leans():
    c = _cycle()
    rig = C.load_rig("r6", root=os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    before = C.world_frames(c, rig)
    out = W.additive(copy.deepcopy(c), "Torso", [{"t": 0.0, "rot": [-4, -5, -5]}], counter=("Right Leg", "Left Leg"))
    after = C.world_frames(out, rig)
    for i in (0, 7, 20):
        for leg in ("Right Leg", "Left Leg"):
            Ra, Rb = np.asarray(before[i][leg])[:3, :3], np.asarray(after[i][leg])[:3, :3]
            assert np.degrees(np.arccos(np.clip((np.trace(Ra.T @ Rb) - 1) / 2, -1, 1))) < 0.5
        Ta, Tb = np.asarray(before[i]["Torso"])[:3, :3], np.asarray(after[i]["Torso"])[:3, :3]
        assert np.degrees(np.arccos(np.clip((np.trace(Ta.T @ Tb) - 1) / 2, -1, 1))) > 5


def test_contact_mapping_lengthens_the_clip_and_stays_monotone():
    c = _cycle()
    mp, share = W.contact_mapping(c, 1.1, 1.25)
    mp = np.asarray(mp)
    assert abs(mp[-1, 0] - c["times"][-1] * 1.1) < 1e-9 and np.all(np.diff(mp[:, 0]) > 0)
    assert 0.0 <= share <= 1.0


def test_hold_from_copies_the_source_limb_pose_relative_to_the_ground():
    c, src = _cycle(), _cycle()
    for i, f in enumerate(src["joints"]["Right Arm"]["frames"]):
        src["joints"]["Right Arm"]["frames"][i] = C.mat_quat(C.euler_mat([30, 0, 40])) + [0, 0, 0]
    out = W.hold_from(copy.deepcopy(c), "Right Arm", src)
    a, b = W.world_mean(out, "Right Arm"), W.world_mean(src, "Right Arm")
    # within 2 deg: the clip's own +-40 deg swing rides on the held mean (mean of products != product of means)
    assert np.degrees(np.arccos(np.clip((np.trace(a.T @ b) - 1) / 2, -1, 1))) < 2.0


def test_inherit_twist_halves_the_limbs_yaw_swing():
    c = _cycle()
    out = W.inherit_twist(copy.deepcopy(c), "Right Arm", 0.5)
    def world_yaw(cc, i):
        R = C.quat_mat(cc["joints"]["Torso"]["frames"][i][:4]) @ C.quat_mat(cc["joints"]["Right Arm"]["frames"][i][:4])
        f = R @ np.array([1.0, 0.0, 0.0])
        return math.degrees(math.atan2(-f[2], f[0]))
    sw0 = max(world_yaw(c, i) for i in range(40)) - min(world_yaw(c, i) for i in range(40))
    sw1 = max(world_yaw(out, i) for i in range(40)) - min(world_yaw(out, i) for i in range(40))
    assert sw0 > 10 and abs(sw1 / sw0 - 0.5) < 0.15


def test_hybrid_fill_picks_slerp_for_short_gaps_and_crossfades_between():
    import motion_fill as MF
    assert MF.weight(20, 30, 45) == 0.0 and MF.weight(60, 30, 45) == 1.0
    assert abs(MF.weight(37.5, 30, 45) - 0.5) < 1e-9


def test_hybrid_fill_keeps_the_keys_and_falls_back_to_slerp_without_a_model():
    import motion_fill as MF
    c = _cycle(n=81, period=80)
    out, info = MF.fill(copy.deepcopy(c), [0, 40, 80], model="__no_such_model__", k=1, group="locomotion")
    assert info["model"] is None and info["warnings"] and "slerp" in info["warnings"][0]
    for k in (0, 40, 80):
        assert _angle(out["joints"]["Right Leg"]["frames"][k], c["joints"]["Right Leg"]["frames"][k]) < 1e-3
