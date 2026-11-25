"""2026-10-25: strike.py warns when a move's arms sink into the body past its own arm_clearance (the owner on
KatanaKaeshi: 'the hands are kind of messed up' - both arms sat 23-27 % inside the chest at the follow-through while
the solver silently kept its best try)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import clip as C  # noqa: E402
import strike as S  # noqa: E402

JOINTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]
REST = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]


def clip_with_right_arm(offset, n=10):
    frames = {j: {"frames": [list(REST) for _ in range(n)]} for j in JOINTS}
    for i in range(n // 2, n):                            # the second half: the arm pushed in toward the chest
        frames["Right Arm"]["frames"][i] = [0.0, 0.0, 0.0, 1.0] + list(offset)
    return {"name": "Probe", "rig": "R6", "fps": 60, "times": [i / 60 for i in range(n)], "joints": frames}


def test_a_rest_pose_is_clear_and_an_arm_in_the_chest_is_reported_with_its_frames():
    rig = C.load_rig("r6")
    assert S.arm_sink_report(clip_with_right_arm([0.0, 0.0, 0.0]), rig, 0.15) is None
    rep = S.arm_sink_report(clip_with_right_arm([-1.2, 0.0, 0.0]), rig, 0.15)
    assert rep is not None and rep["worst"] > 0.5
    assert abs(rep["from"] - 5 / 60) < 1e-3 and abs(rep["to"] - 9 / 60) < 1e-3
    assert S.arm_sink_report(clip_with_right_arm([-1.2, 0.0, 0.0]), rig, 0.95) is None   # (within a loose limit)


def test_unarmed_hands_each_reach_their_own_target_and_the_fist_times_the_hit():
    """2026-10-25 strike.py `unarmed`: each hand its own target (rhand / lhand); the striking fist is what the Hit is
    timed on; no sword in the clip. A proper guard (face height, as the loved R6 M1 combo holds it) needs no push."""
    import numpy as np
    # (no arm_clearance: reaching the target is the point here; a forward-pointing R6 arm swings its top into the torso
    # box, so a face-height guard sits at ~0.15 - the loved M1 combo's own guards measure p90 0.12, max 0.16-0.20)
    move = {"name": "ProbeJab", "unarmed": True, "strike_hand": "left", "fps": 60, "arm_slide": 1.5, "lag": 0.0,
            "keys": [{"t": 0.0, "rhand": [0.5, 1.1, -1.2], "lhand": [-0.45, 1.15, -1.3]},
                     {"t": 0.12, "rhand": [0.5, 1.1, -1.2], "lhand": [-0.55, 1.1, -0.9]},
                     {"t": 0.22, "rhand": [0.45, 1.1, -1.25], "lhand": [-0.4, 1.0, -2.3], "ease": "Out"},
                     {"t": 0.5, "rhand": [0.5, 1.1, -1.2], "lhand": [-0.45, 1.15, -1.3]}]}
    clip, _ = S.generate(move)
    rig = C.load_rig("r6")
    W = C.world_frames(clip, rig)
    for arm, want in (("Right Arm", [0.5, 1.1, -1.2]), ("Left Arm", [-0.45, 1.15, -1.3])):
        hand = (W[0][arm] @ np.array([0, -1.0, 0, 1]))[:3]
        assert np.linalg.norm(hand - np.array(want)) < 0.05, (arm, hand)
    assert "sword" not in clip
    hit = next(e["t"] for e in clip["events"] if e["name"] == "Hit")
    assert 0.12 < hit <= 0.25                                   # (on the jabbing left fist's fastest stretch)


def test_fists_keyed_in_the_torso_frame_ride_a_turned_leaning_torso():
    """2026-10-25 `hands_frame: "torso"`: an unarmed guard is keyed where the fists sit ON the body, so a turned,
    leaning, sinking torso carries them (IronMountain's side-on drive) - each fist lands at torso * its offset."""
    import numpy as np
    off = {"Right Arm": [0.35, 0.82, -1.05], "Left Arm": [-0.85, 0.9, -1.3]}
    move = {"name": "ProbeGuard", "unarmed": True, "hands_frame": "torso", "fps": 60, "arm_slide": 1.5, "lag": 0.0,
            "keys": [{"t": 0.0, "rhand": off["Right Arm"], "lhand": off["Left Arm"]},
                     {"t": 0.3, "rhand": off["Right Arm"], "lhand": off["Left Arm"], "yaw": -60, "pitch": -15,
                      "pos": [0, -0.4, 0]}]}
    clip, _ = S.generate(move)
    W = C.world_frames(clip, C.load_rig("r6"))[-1]
    for arm, o in off.items():
        hand = (W[arm] @ np.array([0, -1.0, 0, 1]))[:3]
        want = (W["Torso"] @ np.array(o + [1.0]))[:3]
        assert np.linalg.norm(hand - want) < 0.05, (arm, hand, want)


def test_a_one_handed_sword_keeps_the_fist_on_the_hilt_and_the_off_hand_on_the_body():
    """2026-10-31 `arms: "one_hand"` (the owner's Swift ask): the right fist alone holds the hilt wherever the blade
    turns about it (a twirl), so the tip is grip + dir * (length - spacing / 2); the off hand rides the torso."""
    import numpy as np
    lh = [-1.4, 0.6, -0.2]
    keys = [{"t": 0.0, "arms": "one_hand", "grip": [1.2, 0.2, -1.2], "dir": [0.0, 1.0, 0.0], "lhand": lh},
            {"t": 0.3, "arms": "one_hand", "grip": [1.2, 0.2, -1.2], "dir": [0.0, -1.0, -0.2], "lhand": lh,
             "yaw": -40, "pitch": -10}]
    move = {"name": "ProbeTwirl", "fps": 60, "arm_slide": 1.5, "lag": 0.0, "keys": keys,
            "sword": {"length": 5.4, "grip": 0.75}, "events": [{"name": "Hit", "t": 0.15}]}
    clip, _ = S.generate(move)
    W = C.world_frames(clip, C.load_rig("r6"))
    sw = clip["sword"]
    for i in (0, len(W) - 1):
        fist = (W[i]["Right Arm"] @ np.array([0, -1.0, 0, 1]))[:3]
        tip, grip = np.array(sw["tip"][i]), np.array(sw["grip_path"][i])
        d = (tip - grip) / np.linalg.norm(tip - grip)
        assert np.linalg.norm(fist - (grip + d * 0.375)) < 0.08, (i, fist, grip)
        off = (W[i]["Left Arm"] @ np.array([0, -1.0, 0, 1]))[:3]
        assert np.linalg.norm(off - (W[i]["Torso"] @ np.array(lh + [1.0]))[:3]) < 0.08, (i, off)


def test_a_one_handed_clip_with_no_hit_gets_one_on_the_fastest_frame():
    """2026-11-01 (the Spin Drill's DTEnd): the one-hand branch's reach length shadowed the frame count, so a clip
    with no authored Hit crashed placing its own."""
    lh = [-1.4, 0.6, -0.2]
    keys = [{"t": 0.0, "arms": "one_hand", "grip": [1.2, 0.2, -1.2], "dir": [0.0, 1.0, 0.0], "lhand": lh},
            {"t": 0.3, "arms": "one_hand", "grip": [1.2, 0.2, -1.2], "dir": [0.0, -1.0, -0.2], "lhand": lh}]
    move = {"name": "ProbeNoHit", "fps": 60, "arm_slide": 1.5, "lag": 0.0, "keys": keys,
            "sword": {"length": 5.4, "grip": 0.75}}
    clip, _ = S.generate(move)
    hits = [e["t"] for e in clip["events"] if e["name"] == "Hit"]
    assert len(hits) == 1 and 0.0 < hits[0] <= 0.3, clip["events"]


def test_a_pool_cut_starts_and_ends_on_the_same_blade_edge():
    """2026-10-31 `edge_end_at` (with `edge_start`): a pool of cuts that all start and end on one guard must start and
    end on ONE edge too - left free, the blade's roll at the end differed from the start by up to 161 deg (a flip at
    every chained seam). A cut whose motion rolls the edge still lands on the given edge at both ends."""
    import numpy as np
    E = [0.0, -0.942, -0.335]
    keys = [{"t": 0.0, "grip": [1.3, -0.4, -0.4], "dir": [0.2, -0.32, 0.92]},
            {"t": 0.1, "grip": [2.0, 0.3, -1.0], "dir": [0.93, 0.05, -0.36]},
            {"t": 0.16, "grip": [0.3, 0.5, -2.3], "dir": [-0.1, 0.0, -1.0]},
            {"t": 0.3, "grip": [-1.6, 1.3, -1.2], "dir": [-0.8, 0.4, 0.42]},
            {"t": 0.6, "grip": [1.3, -0.4, -0.4], "dir": [0.2, -0.32, 0.92]},
            {"t": 0.7, "grip": [1.3, -0.4, -0.4], "dir": [0.2, -0.32, 0.92]}]
    move = {"name": "ProbePool", "fps": 60, "arm_slide": 2.4, "lag": 0.0, "keys": keys, "events": [{"name": "Hit", "t": 0.16}],
            "sword": {"length": 5.4, "grip": 0.75}, "edge_start": E, "edge_end_at": E}
    clip, _ = S.generate(move)
    sw = clip["sword"]
    for i in (0, len(sw["edge"]) - 1):
        d = np.array(sw["tip"][i]) - np.array(sw["grip_path"][i])
        d /= np.linalg.norm(d)
        want = np.array(E) - (np.array(E) @ d) * d
        want /= np.linalg.norm(want)
        assert float(np.array(sw["edge"][i]) @ want) > 0.999, (i, sw["edge"][i], want)
    move.pop("edge_end_at")
    free, _ = S.generate(move)
    e0, e1 = np.array(free["sword"]["edge"][0]), np.array(free["sword"]["edge"][-1])
    assert float(e0 @ e1) < 0.99            # (without it this cut does NOT come home on its first edge)


def test_a_weapon_dossier_tells_a_cut_on_moving_legs_from_a_twirl_on_a_straddle():
    """2026-11-04 (the owner on the Swift set v2: "the leg work is horrible and some of them the sword isnt even
    attacking properly"): the dossier measures whether the fast part IS the cut (not a twirl as fast after it) and
    whether the feet stand staggered at the Hit"""
    import proc_dossier as PD
    D = {"build": {"builder": "fp_weapon"}, "checks": []}
    hang = {"grip": [1.3, -0.4, -0.4], "dir": [0.2, -0.32, 0.92]}
    cut = [{"t": 0.0, **hang}, {"t": 0.1, "grip": [2.0, 0.3, -1.0], "dir": [0.93, 0.05, -0.36]},
           {"t": 0.16, "grip": [0.3, 0.5, -2.3], "dir": [-0.1, 0.0, -1.0], "ease": "Out"},
           {"t": 0.3, "grip": [-1.6, 0.6, -1.4], "dir": [-0.8, 0.2, -0.5]}]
    base = {"fps": 60, "arm_slide": 2.4, "lag": 0.0, "events": [{"name": "Hit", "t": 0.1667}],
            "sword": {"length": 5.4, "grip": 0.75}}
    stagger = [{"t": 0.0, "right": [0.5, 0, 0.1], "left": [-0.5, 0, -0.1], "left_lift": 0.3},
               {"t": 0.16, "right": [0.5, 0, 0.6], "left": [-0.4, 0, -0.9]}, {"t": 0.6, "right": [0.5, 0, 0.6], "left": [-0.4, 0, -0.9]}]
    square = [{"t": 0.0, "right": [0.5, 0, 0.1], "left": [-0.5, 0, -0.1]}, {"t": 0.16, "right": [0.9, 0, 0.0], "left": [-0.9, 0, -0.1]},
              {"t": 0.6, "right": [0.9, 0, 0.0], "left": [-0.9, 0, -0.1]}]
    good, _ = S.generate(dict(base, name="ProbeCut", keys=cut + [{"t": 0.6, **hang}], feet=stagger))
    twirl = cut + [{"t": 0.36, "grip": [-1.6, 0.6, -1.4], "dir": [0.8, 0.2, 0.5]}, {"t": 0.42, "grip": [-1.6, 0.6, -1.4], "dir": [-0.8, -0.2, -0.5]},
                   {"t": 0.48, "grip": [-1.6, 0.6, -1.4], "dir": [0.8, 0.2, 0.5]}, {"t": 0.6, **hang}]
    bad, _ = S.generate(dict(base, name="ProbeTwirl", keys=twirl, feet=square))
    fg, _ = PD.measures(good, D)
    fb, _ = PD.measures(bad, D)
    assert fg["cut_fast_share"]({}) >= 0.5 and fg["cut_fast_frames"]({}) >= 3, fg["cut_fast_share"]({})
    assert fb["cut_fast_share"]({}) < 0.5, fb["cut_fast_share"]({})          # (the twirl after it is as fast)
    assert fg["stance_split_hit_studs"]({}) >= 0.9 > fb["stance_split_hit_studs"]({})
    assert fg["step_near_hit_s"]({}) > 0.05


def test_a_weapon_dossier_measures_a_strike_clips_turn_and_arms():
    """2026-10-31: the Greatsword dossier (builder fp_weapon) measured its strike-route swings without the body's own
    numbers - a check on the torso's turn or the arms in the body read NaN and could never pass"""
    import math
    import proc_dossier as PD
    keys = [{"t": 0.0, "grip": [1.3, -0.4, -0.4], "dir": [0.2, -0.32, 0.92]},
            {"t": 0.2, "grip": [-1.0, 0.6, -2.0], "dir": [-0.8, 0.2, -0.5], "yaw": 60}]
    clip, _ = S.generate({"name": "ProbeTurn", "fps": 60, "arm_slide": 2.4, "lag": 0.0, "keys": keys,
                          "events": [{"name": "Hit", "t": 0.1}], "sword": {"length": 5.4, "grip": 0.75}})
    fns, _ = PD.measures(clip, {"build": {"builder": "fp_weapon"}, "checks": []})
    turn, sink = fns["torso_yaw_range_deg"]({}), fns["arm_sink_max"]({})
    assert not math.isnan(turn) and turn > 40, turn
    assert not math.isnan(sink) and 0.0 <= sink <= 1.0, sink
