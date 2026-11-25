"""the learning pipeline (2026-10-11): native-rate import, snaps, key reduction, derive operations, movesets, the book"""
import copy
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import book as BK          # noqa: E402
import derive as D         # noqa: E402
import keyreduce as KR     # noqa: E402
import kfs_import as KI    # noqa: E402
import moveset as MS       # noqa: E402
import snaps as SN         # noqa: E402

from test_anim_profile import cycle, sine  # noqa: E402


def err(a, b):
    return max(KR.qang(np.array(x[:4]), np.array(y[:4])) + 30 * float(np.linalg.norm(np.subtract(x[4:7], y[4:7])))
               for j in a["joints"] for x, y in zip(a["joints"][j]["frames"], b["joints"][j]["frames"]))


def test_native_fps_is_never_downsampled():
    kfs = [{"t": i / 60.0} for i in range(10)]
    assert KI.native_fps(kfs) == 60
    assert KI.native_fps([{"t": i / 30.0} for i in range(10)]) == 30
    assert KI.native_fps([{"t": 0.0}, {"t": 0.5}, {"t": 1.2}]) in (24, 30, 60)


def spiked():
    c = cycle(sine(40), sine(40, 0.5), sine(30, 0.5), sine(30))
    F = c["joints"]["Right Leg"]["frames"]
    # where the leg swings fastest (the sine's zero crossing), one frame jumps two frames ahead along the path
    F[20] = list(F[22])
    return c


def test_snaps_are_found_and_respaced_without_moving_the_path():
    c = spiked()
    hits = SN.find(c)
    assert "Right Leg" in hits and not any(j != "Right Leg" for j in hits)
    fixed, n = SN.fix(c)
    assert not SN.find(fixed) and n["Right Leg"] >= 1
    # the ends of the window are untouched: the joint arrives where it did
    assert err({"joints": {"x": {"frames": [c["joints"]["Right Leg"]["frames"][30]]}}},
               {"joints": {"x": {"frames": [fixed["joints"]["Right Leg"]["frames"][30]]}}}) < 1e-3
    smooth = cycle(sine(40), sine(40, 0.5), sine(30, 0.5), sine(30))
    assert not SN.find(smooth)                                   # a sine has no snap


def test_key_reduction_reproduces_within_tolerance():
    c = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40))
    F = c["joints"]["Right Leg"]["frames"]
    keys = KR.reduce_track(F, 2.0)
    assert 2 < len(keys) < len(F)
    for i in range(len(F)):                                      # rebuild by slerp between kept keys
        a = max(k for k in keys if k <= i)
        b = min(k for k in keys if k >= i)
        w = 0 if a == b else (i - a) / (b - a)
        assert KR.qang(KR.slerp(F[a][:4], F[b][:4], w), np.array(F[i][:4])) <= 2.0 + 1e-6


def test_derive_operations_are_exact():
    c = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40))
    assert err(c, D.op_amplify(copy.deepcopy(c), list(c["joints"]), 1.0)) < 1e-3
    assert err(c, D.op_mirror(D.op_mirror(copy.deepcopy(c)))) < 1e-3
    big = D.op_amplify(copy.deepcopy(c), ["Right Leg"], 1.5)
    amp = lambda cl: max(KR.qang(np.array([0, 0, 0, 1.0]), np.array(f[:4])) for f in cl["joints"]["Right Leg"]["frames"])
    assert abs(amp(big) / amp(c) - 1.5) < 0.05
    r = D.op_retime(copy.deepcopy(c), duration=1.0)
    assert len(r["times"]) == 61 and abs(r["times"][-1] - 1.0) < 1e-9
    s = D.op_shift(copy.deepcopy(c), ["Right Arm"], 4)
    assert err({"joints": {"x": {"frames": [s["joints"]["Right Arm"]["frames"][4]]}}},
               {"joints": {"x": {"frames": [c["joints"]["Right Arm"]["frames"][0]]}}}) < 1e-3


def test_hold_still_and_concat_keep_time_consistent():
    c = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40))
    n = len(c["times"])
    h = D.op_hold(copy.deepcopy(c), 0.1, 5)
    assert len(h["times"]) == n + 5 and all(len(d["frames"]) == n + 5 for d in h["joints"].values())
    st = D.op_still(copy.deepcopy(c), 3, 1.0)
    assert len(st["times"]) == 61 and len({tuple(f) for f in st["joints"]["Right Leg"]["frames"]}) == 1
    cc = D.op_concat(copy.deepcopy(c), copy.deepcopy(c))
    assert len(cc["times"]) == 2 * n - 1 and cc["loop"] is False


def test_chain_starts_and_ends_on_the_pose(tmp_path, monkeypatch):
    c = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40))
    guard = cycle(sine(5), sine(5, 0.5), sine(5, 0.5), sine(5))
    monkeypatch.setattr(D, "load_clip", lambda name: guard)
    ch = D.op_chain(copy.deepcopy(c), "G", 0, 6, 8)
    g0 = MS.frame(guard, 0)
    assert MS.pose_dist(MS.frame(ch, 0), g0) < 1e-3 and MS.pose_dist(MS.frame(ch, -1), g0) < 1e-3
    assert MS.pose_dist(MS.frame(ch, 20), MS.frame(c, 20)) < 1e-3   # the middle is the move itself


def test_breathe_keeps_a_loop_closed():
    c = D.op_still(cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40)), 0, 2.4)
    b = D.op_breathe(copy.deepcopy(c), 2.4, 2.0, 3.0, 0.04)
    assert MS.pose_dist(MS.frame(b, 0), MS.frame(b, -1)) < 0.05
    assert max(KR.qang(np.array(b["joints"]["Torso"]["frames"][0][:4]), np.array(f[:4])) for f in b["joints"]["Torso"]["frames"]) > 1.0


def test_book_calibrates_within_a_kind_only():
    rows = [{"name": f"r{i}", "verdict": v, "m": {"kind": k, "snap": s}} for i, (v, k, s) in enumerate(
        [("loved", "locomotion", 3.9), ("good", "locomotion", 3.7), ("bad", "locomotion", 2.9), ("horrible", "locomotion", 3.0),
         ("horrible", "action", 9.0), ("horrible", "action", 8.0)])]
    cal = BK.calibrate(rows)
    assert [c["kind"] for c in cal] == ["locomotion"]               # actions have no loved clips: no row
    assert cal[0]["metric"] == "snap" and cal[0]["loved/good"] > cal[0]["bad/horrible"]


def test_timing_transfer_keeps_the_path_and_takes_the_spacing(monkeypatch):
    c = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40))
    c["loop"] = False
    monkeypatch.setattr(D, "load_clip", lambda name: copy.deepcopy(c))
    same = D.op_timing(copy.deepcopy(c), "self")
    assert err(c, same) < 0.5                                   # its own timing: (nearly) itself
    # a reference that holds still for its first half, then moves: the copy must hold too, then catch up
    ref = copy.deepcopy(c)
    for j in ref["joints"]:
        F = ref["joints"][j]["frames"]
        ref["joints"][j]["frames"] = [F[0]] * 20 + F[: len(F) - 20]
    monkeypatch.setattr(D, "load_clip", lambda name: ref)
    t = D.op_timing(copy.deepcopy(c), "held")
    assert MS.pose_dist(MS.frame(t, 10), MS.frame(c, 0)) < 0.5   # holding where the reference holds
    assert MS.pose_dist(MS.frame(t, 0), MS.frame(c, 0)) < 1e-3 and MS.pose_dist(MS.frame(t, -1), MS.frame(c, -1)) < 1e-3


def test_overlap_lags_the_head_behind_a_turning_torso_and_leaves_a_still_body_alone():
    c = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40))
    # the torso turns 40 deg about y over the cycle; the head carries no motion of its own
    for i, f in enumerate(c["joints"]["Torso"]["frames"]):
        a = math.radians(40 * math.sin(2 * math.pi * i / 40)) / 2
        f[:4] = [0.0, math.sin(a), 0.0, math.cos(a)]
    c["joints"]["Head"] = {"frames": [list(f) for f in c["joints"]["Torso"]["frames"]]}
    o = D.op_overlap(copy.deepcopy(c), ("Head",), 0.05, 1.0)
    lag = [KR.qang(np.array(a[:4]), np.array(b[:4])) for a, b in zip(c["joints"]["Head"]["frames"], o["joints"]["Head"]["frames"])]
    assert 1.0 < max(lag) < 40.0
    still = D.op_still(copy.deepcopy(c), 0, 1.0)
    o2 = D.op_overlap(copy.deepcopy(still), ("Head",), 0.05, 1.0)
    assert err(still, o2) < 1e-3


def test_trim_and_crossfaded_concat():
    c = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40))
    c["loop"] = False
    t = D.op_trim(copy.deepcopy(c), 0.1, 0.3)
    assert len(t["times"]) == 13 and MS.pose_dist(MS.frame(t, 0), MS.frame(c, 6)) < 1e-3
    b = D.op_mirror(copy.deepcopy(c))
    x = D.op_concat(copy.deepcopy(c), b, crossfade=6)
    n = len(c["times"])
    assert len(x["times"]) == 2 * n - 6
    # no frame-to-frame jump at the join bigger than the clips' own biggest step
    own = max(float(SN.speeds(c["joints"][j]["frames"], 60, False).max()) for j in c["joints"])
    joined = max(float(SN.speeds(x["joints"][j]["frames"], 60, False).max()) for j in x["joints"])
    assert joined <= own * 2.5


def test_tempo_lengthens_the_wind_up_and_shortens_the_recovery_around_an_untouched_strike():
    c = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40))
    c["loop"] = False
    k = D.strike_index(c)
    t = D.op_tempo(copy.deepcopy(c), 2.0, 0.5, 0.05)
    k2 = D.strike_index(t)
    assert abs(k2 - 2 * (k - 3) - 3) <= 2                          # the strike moved later by the stretched wind-up
    assert MS.pose_dist(MS.frame(t, 0), MS.frame(c, 0)) < 1e-3 and MS.pose_dist(MS.frame(t, -1), MS.frame(c, -1)) < 1e-3
    assert abs(len(t["times"]) - (2 * (k - 3) + 7 + 0.5 * (len(c["times"]) - 1 - (k + 4)))) <= 2


import clipping as CL  # noqa: E402


def test_clipping_finds_an_arm_through_the_torso_and_declip_turns_it_out():
    c = cycle(sine(5), sine(5, 0.5), sine(5, 0.5), sine(5))
    c["loop"] = False
    # the right arm swung across the chest: 90 deg about the forward axis, its far end sunk into the torso
    for f in c["joints"]["Right Arm"]["frames"]:
        a = math.radians(90) / 2
        f[:4] = [0.0, 0.0, math.sin(a), math.cos(a)]
        f[4:7] = [-0.7, 0.0, 0.0]
    assert CL.find(c), "the arm across the chest must be found"
    d = D.op_declip(copy.deepcopy(c), ("Right Arm",), 0.2, 90)
    assert not CL.find(d)
    assert not CL.find(cycle(sine(40), sine(40, 0.5), sine(30, 0.5), sine(30)))   # a plain swing never clips


import strike_r6 as ST  # noqa: E402


def test_every_authored_strike_starts_and_ends_on_the_guard_with_the_hit_on_its_beat():
    for kind in ST.KINDS:
        spec = ST.build(kind, "T")
        k = spec["keys"]
        assert k[0]["body"] == k[-1]["body"] == ST.GUARD_BODY
        assert k[0]["right_arm"] == k[-1]["right_arm"] == ST.GUARD_R and k[0]["left_arm"] == k[-1]["left_arm"] == ST.GUARD_L
        assert spec["events"][0]["f"] == ST.KINDS[kind]["frames"][ST.KINDS[kind].get("event_beat", 3)]
        turns = [kk["body"]["turn"] for kk in k]
        assert max(turns) - min(turns) <= 55          # R6 has no waist: ~45-52 deg judged well; the 76 deg version snapped


def test_every_weapon_move_starts_and_ends_on_the_two_handed_guard():
    for kind, K in ST.WEAPON_KINDS.items():
        spec = ST.build_weapon(kind, "T")
        k = spec["keys"]
        assert k[0]["body"] == ST.GS_GUARD["body"] and k[-1]["body"]["turn"] == ST.GS_GUARD["body"]["turn"], kind
        assert k[0]["right_arm"]["hand"] == k[-1]["right_arm"]["hand"] and k[0]["right_arm"]["blade"] == k[-1]["right_arm"]["blade"], kind
        held = [kk["left_arm"] for kk in k if "left_arm" in kk]                    # a key leaves it out = held
        assert held[0] == "hilt" and held[-1] == "hilt", kind                     # back on the hilt for the next move
        assert spec["events"][0]["f"] == K["frames"][K.get("event_beat", 3)] + K.get("event_shift", 0), kind
        assert len(K["body"]) == len(K["hand_local"]) == len(K["blade"]) == len(K["frames"]), kind


def test_a_block_braces_the_off_hand_on_the_blade():
    spec = ST.build_weapon("gs_block", "T")
    braced = [k for k in spec["keys"] if isinstance(k.get("left_arm"), dict) and "on_blade" in k["left_arm"]]
    assert braced and spec["events"][0]["name"] == "Block"
    assert all(1.0 <= k["left_arm"]["on_blade"] <= 2.0 for k in braced)   # up the flat, within an R6 arm's reach
