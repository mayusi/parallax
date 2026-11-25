"""kit/anim/proc_blade.py - the weapon builder on the procedural route (the governor's re-plan 2026-11-05, the owner:
"make sure ur using the procedural pipeline properly"): a weapon dossier routes to it (never proc_strike's key poses),
the blade is welded to the grip hand, the Hit sits on the tip's speed peak, the feet stay planted, candidates differ by
their efforts + free arm, a frozen clip fails the weapon vocabulary; proc_r6.key_curve takes a >180 deg sweep the short
way; footage_weapon measures a stroke and a spin"""
import json
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
os.chdir(ROOT)
import proc_blade as PB      # noqa: E402
import proc_r6 as P          # noqa: E402

_LUNGE = os.path.join(ROOT, "assets", "animations", "gestures", "blade_lunge_cut.json")
_DRILL = os.path.join(ROOT, "assets", "animations", "gestures", "blade_drill_spin.json")

D = {"name": "greatsword", "build": {"builder": "fp_weapon", "gestures": {"TestCut*": "blade_lunge_cut"},
                                    "sword": {"length": 5.03, "grip": 1.23}}}
_BUILT = {}


def built(key="base", s=None):
    if key not in _BUILT:
        _BUILT[key] = PB.build(D, s or {}, f"TestCut_r0_{key}")
    return _BUILT[key]


def test_a_weapon_dossier_routes_to_the_procedural_builder():
    if not os.path.isfile(_LUNGE):
        pytest.skip("the author's assets/animations/gestures/blade_lunge_cut.json is not shipped with the kit")
    import proc_candidates as PCD
    assert "fp_weapon" in PCD.BLADE_BUILDERS and "fp_weapon" not in PCD.STRIKE_BUILDERS
    assert PCD.STRIKE_BUILDERS == ("strike",)              # key poses only for the owner's own keyed blocks
    c, b = built()
    assert c["source"]["kind"] == "proc_blade" and b["slides"] == "weapon_vocab"


def test_the_blade_is_welded_to_the_grip_hand():
    if not os.path.isfile(_LUNGE):
        pytest.skip("the author's assets/animations/gestures/blade_lunge_cut.json is not shipped with the kit")
    c, _ = built()
    tip, grip = np.array(c["sword"]["tip"]), np.array(c["sword"]["grip_path"])
    assert np.allclose(np.linalg.norm(tip - grip, axis=1), 5.03, atol=1e-3)
    # the game's Handle joint (grip.py): a welded blade is the identity Transform on every frame
    g = np.array(c["grip"])
    assert np.allclose(np.abs(g[:, 3]), 1.0, atol=1e-3) and np.abs(g[:, 4:7]).max() < 1e-3


def test_the_hit_sits_on_the_tip_speed_peak():
    if not os.path.isfile(_LUNGE):
        pytest.skip("the author's assets/animations/gestures/blade_lunge_cut.json is not shipped with the kit")
    c, _ = built()
    tip = np.array(c["sword"]["tip"])
    sp = np.r_[np.linalg.norm(np.diff(tip, axis=0), axis=1) * 60, 0.0]
    hit = int(round(c["events"][0]["t"] * 60))
    assert c["events"][0]["name"] == "Hit" and c["events"][0]["by"] == "Blade"
    assert sp[hit] >= 0.8 * sp.max()                       # the cut is the clip's fastest motion, the Hit on it
    assert 0.1 <= c["events"][0]["t"] <= 0.4               # the game rule: contact within 0.1-0.4 s of the click


def test_the_planted_feet_never_skid():
    if not os.path.isfile(_LUNGE):
        pytest.skip("the author's assets/animations/gestures/blade_lunge_cut.json is not shipped with the kit")
    import clip as C
    c, _ = built()
    W = C.world_frames(c, C.load_rig("R6"))
    for leg in ("Right Leg", "Left Leg"):
        S = np.array([(w[leg] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3] for w in W])
        down = S[:, 1] < S[:, 1].min() + 0.03
        d = np.linalg.norm(np.diff(S[:, [0, 2]], axis=0), axis=1)
        assert all(d[i - 1] < 0.1 for i in range(1, len(S)) if down[i] and down[i - 1]), leg


def test_candidates_differ_by_their_efforts_and_free_arm():
    if not os.path.isfile(_LUNGE):
        pytest.skip("the author's assets/animations/gestures/blade_lunge_cut.json is not shipped with the kit")
    a, _ = built()
    # an arm HABIT (r6_vocab.json, tracked) - not 'prior:*', whose pose_prior_combat.npz is untracked _artifacts data
    # (2026-11-05: a zeroed restore of it turned this test red for a reason that was not the code's)
    b, _ = built("strong", {"weight": 0.8, "time": 0.5, "arms": "habit:1:down_back"})
    ya, yb = a["joints"]["Torso"]["frames"][0][5], b["joints"]["Torso"]["frames"][0][5]
    assert yb < ya - 0.05                                  # weight: a deeper crouch (the cut's is capped at 0.75)
    assert b["times"][-1] < a["times"][-1]                 # time: sudden is shorter
    fa = np.array([f[:4] for f in a["joints"]["Left Arm"]["frames"][:30]])
    fb = np.array([f[:4] for f in b["joints"]["Left Arm"]["frames"][:30]])
    assert np.abs(np.abs(np.sum(fa * fb, axis=1)) - 1).max() > 0.01   # another free-arm choice
    assert b["source"]["arms"] == "habit:1:down_back"


def test_a_frozen_clip_fails_the_weapon_vocabulary():
    if not os.path.isfile(_LUNGE):
        pytest.skip("the author's assets/animations/gestures/blade_lunge_cut.json is not shipped with the kit")
    c, _ = built()
    still = json.loads(json.dumps(c))
    for j in still["joints"].values():
        j["frames"] = [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0] for _ in j["frames"]]
    fails, _, _ = PB.vocab_check(still)
    assert len(fails) == 4                                 # both arms and both legs frozen
    assert PB.vocab_check(c)[0] == []                      # the built cut is alive


def test_the_key_curve_takes_a_sweep_past_180_the_short_way():
    """a sword arm keyed at 0 -> 120 -> 240 deg about the vertical: the log-space curve wrapped at +-180 and swung the
    long way round for a frame (a 424 studs/s blade flip, 2026-11-05)"""
    keys = []
    for t, deg in ((0.0, 0.0), (0.2, 120.0), (0.4, 240.0)):
        q = np.tile([0.0, 0.0, 0.0, 1.0], (6, 1))
        q[2] = P.q_exp(np.array([0.0, math.radians(deg), 0.0]))
        keys.append({"q": q, "p": np.zeros((6, 3)), "t": t, "stiff": 1.0})
    curve = P.key_curve(keys, False, None)
    prev = None
    for i in range(25):
        q = curve(i / 60)[0][2]
        if prev is not None:
            step = math.degrees(2 * math.acos(min(1.0, abs(float(q @ prev)))))
            assert step < 20, (i, step)                     # 240 deg in 0.4 s: ~10 deg a frame, never a jump
        prev = q


def test_footage_weapon_measures_a_stroke_and_a_spin():
    import footage_weapon as FW
    fps, T = 30.0, 60
    frames = []
    for i in range(T):
        X = np.zeros((33, 3))
        a = 2 * math.pi * 3.0 * i / fps                     # the shoulders turning 3 turns a second
        X[FW.L_SH], X[FW.R_SH] = [-0.2 * math.cos(a), 1.4, 0.2 * math.sin(a)], [0.2 * math.cos(a), 1.4, -0.2 * math.sin(a)]
        X[FW.L_HIP], X[FW.R_HIP] = [-0.1, 0.9, 0.0], [0.1, 0.9, 0.0]
        X[FW.L_EL] = X[FW.L_SH] + [0, -0.3, 0]
        X[FW.L_KNEE], X[FW.R_KNEE] = [-0.1, 0.45, 0.0], [0.1, 0.45, 0.0]
        X[FW.L_ANK], X[FW.R_ANK] = [-0.1, 0.0, 0.0], [0.1, 0.0, 0.0]
        X[FW.L_WR] = X[FW.L_SH] + [0, -0.6, 0]
        X[FW.R_WR] = [0.6 * math.cos(a), 1.4, -0.6 * math.sin(a)]   # the blade hand out at arm's length
        X[FW.R_EL] = 0.5 * (X[FW.R_SH] + X[FW.R_WR])        # a straight arm
        frames.append(X.tolist())
    m = FW.spin(np.array(frames), fps)
    assert abs(m["turns_per_s"] - 3.0) < 0.3 and m["blade_hand"] == "right" and m["blade_reach"] > 0.8
    # one fast stroke of the right wrist in an otherwise still clip
    still = np.array(frames)
    still[:] = still[0]
    for i in range(20, 26):
        still[i, FW.R_WR] = still[19, FW.R_WR] + [0.0, 0.0, -0.25 * (i - 19)]
    still[26:, FW.R_WR] = still[25, FW.R_WR]
    w = FW.swing(still, fps)
    assert len(w["strokes"]) == 1 and w["hand"] == "right" and 0.1 <= w["strokes"][0]["stroke_s"] <= 0.4


def test_the_weapon_calibration_is_statistics_of_loved_swings():
    v = PB.vocab()
    assert len(v["clips"]) >= 4 and len(v["leg_clips"]) >= 10
    assert {"sword_arm", "free_arm"} <= set(v["arm_habits"][0]) and v["torso_peak_deg_s"]["p50"] > 300
    assert 0.0 < v["pivot_share"]["p50"] < 1.0             # the rear foot pivots LESS than the hips


def test_the_picks_gif_plays_a_fast_move_at_30_fps_in_real_time():
    """the governor 2026-11-05: a 3.6 turns/s drill strobed at 15 fps; a fast cut or spin is drawn every 2nd frame and
    its stored delays (whole centiseconds) still add up to real time"""
    if not os.path.isfile(_LUNGE):
        pytest.skip("the author's assets/animations/gestures/blade_lunge_cut.json is not shipped with the kit")
    import proc_picks as PP
    c, _ = built()
    assert PP.frame_step(c) == 2                            # the cut's tip passes 90 studs/s
    slow = json.loads(json.dumps(c))
    slow.pop("sword")
    for j in slow["joints"].values():
        j["frames"] = [j["frames"][0] for _ in j["frames"]]
    assert PP.frame_step(slow) == PP.EVERY
    d = PP.real_time_ms(30, 2)
    assert all(x % 10 == 0 for x in d) and abs(sum(d) - 30 * 2000 / 60) <= 10


def test_a_game_with_its_own_camera_is_judged_from_it():
    """2026-11-05: the picks' generic 'game' view (Roblox's high chase camera) showed SwordTrickCut's Hit end-on while
    Sample Game's over-the-shoulder camera - the one the dossier's checks use - sees the blade across"""
    _dir_a = os.path.join(ROOT, "assets", "animations", "direction", "SwordTrickCut.md")
    _dir_b = os.path.join(ROOT, "assets", "animations", "direction", "DTDrillSpin.md")
    if not os.path.isfile(_dir_a) or not os.path.isfile(_dir_b):
        pytest.skip("the author's assets/animations/direction/ files are not shipped with the kit")
    import proc_picks as PP
    cam, views = PP.views_for({"build": {"tp_camera": [2.2, 0.9, 9.0]}})
    assert "--tp" in cam and views == ("three-quarter", "tp")
    assert PP.views_for({"build": {}})[1] == ("three-quarter", "game")
    # the sheet says which direction the round was built from (the governor's default, the owner's pick still open)
    assert PP.direction_pick("SwordTrickCut").startswith("B - governor default, owner pick open")
    assert PP.direction_pick("DTDrillSpin").startswith("A - governor default, owner pick open")
    assert PP.direction_pick("NoSuchMove") is None
    # a drill's blade disc is the move: its dossier frames the still cameras on the root + the reach
    assert "--frame-reach" not in cam
    assert "--frame-reach" in PP.views_for({"build": {"tp_camera": [2.2, 0.9, 9.0], "look_reach": True}})[0]


DRILL = {"name": "spin_drill", "build": {"builder": "fp_weapon", "gestures": {"TestDrill*": "blade_drill_spin"},
                                            "sword": {"length": 5.4, "grip": 0.75}}}


def test_a_spin_is_its_own_layer_and_stops_dead():
    """five turns keyed as joint rotations broke the log-space curve (a 6,000 deg/s whip at the stop): the spin is a
    yaw layer - it turns the body >= 4.5 times at 3-4.5 turns a second, then the body is still on the burst"""
    if not os.path.isfile(_DRILL):
        pytest.skip("the author's assets/animations/gestures/blade_drill_spin.json is not shipped with the kit")
    import shape_ref as SR
    c, _ = PB.build(DRILL, {}, "TestDrill_r0_c0")
    m = SR.measure(c)
    assert m["spin_turns"] >= 4.5 and 3.0 <= m["spin_turns_per_s"] <= 4.5
    burst = next(e["t"] for e in c["events"] if e["name"] == "Burst")
    q = np.array([f[:4] for f in c["joints"]["Torso"]["frames"]])
    w = np.degrees(2 * np.arccos(np.clip(np.abs(np.sum(q[1:] * q[:-1], axis=1)), -1, 1))) * 60
    after = w[int(round(burst * 60)) + 6:]
    assert after.max() < 60                                 # the dead stop: the body still after the burst
    assert w.max() < 3000                                   # and never a whip


def test_an_orbiting_foot_rides_the_spin_off_the_floor():
    if not os.path.isfile(_DRILL):
        pytest.skip("the author's assets/animations/gestures/blade_drill_spin.json is not shipped with the kit")
    import clip as C
    c, _ = PB.build(DRILL, {}, "TestDrill_r0_c1")
    W = C.world_frames(c, C.load_rig("R6"))
    sole = {lg: np.array([(w[lg] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3] for w in W]) for lg in ("Right Leg", "Left Leg")}
    spin = range(int(0.6 * 60), int(1.6 * 60))
    floor = min(sole["Right Leg"][:, 1].min(), sole["Left Leg"][:, 1].min())
    assert min(sole["Left Leg"][i, 1] for i in spin) > floor + 0.15        # the free foot skims, never drags
    piv = sole["Right Leg"][list(spin)][:, [0, 2]]
    assert np.linalg.norm(piv - piv.mean(axis=0), axis=1).max() < 0.15  # the pivot foot turns on its spot


def test_the_key_curve_carries_whole_turns_about_one_axis():
    """keys every 75 deg for five turns about the vertical: every frame's step stays near the spin's own (the unwrap
    keeps counting turns). A STOP that tilts the axis 30 radians in cannot be carried by any log-space curve (a small
    tilt times 30 radians is a whole-turn whip) - that is why proc_blade spins as its own yaw layer (the test above)"""
    keys = []
    for i in range(25):
        q = np.tile([0.0, 0.0, 0.0, 1.0], (6, 1))
        q[0] = P.q_exp(np.array([0.0, math.radians(-75.0 * i), 0.0]))
        keys.append({"q": q, "p": np.zeros((6, 3)), "t": i * 0.058, "stiff": 1.0})
    for k0, k1 in zip(keys, keys[1:]):
        if np.dot(k0["q"][0], k1["q"][0]) < 0:
            k1["q"][0] = -k1["q"][0]
    curve = P.key_curve(keys, False, None)
    prev, turned = None, 0.0
    for f in range(int(keys[-1]["t"] * 60) + 1):
        q = curve(f / 60)[0][0]
        if prev is not None:
            step = math.degrees(2 * math.acos(min(1.0, abs(float(q @ prev)))))
            assert step < 40, f
            turned += step
        prev = q
    assert turned > 1700                                    # all five turns, none folded away


def test_the_arms_stay_on_their_shoulders_and_the_blade_out_of_the_body():
    """the owner on the drill's round 2 (2026-11-05): "OK BUT WHY IS THE SWORD AND HANDS WEIRD MAN" - the sword arm slid
    0.8 studs off its shoulder (loved arms slide out p90 0.67) and the free arm flopped into odd angles: every arm keeps
    to its socket (the loved outward median, + a spring's overshoot), the blade never enters the body, the free arm
    sinks into the torso no more than the loved strikes' worst"""
    if not os.path.isfile(_DRILL):
        pytest.skip("the author's assets/animations/gestures/blade_drill_spin.json is not shipped with the kit")
    import proc_dossier as DS
    c, _ = PB.build(DRILL, {"arms": "habit:2:across"}, "TestDrill_r0_c1")
    cap = PB.vocab()["slide_outward"]["sword_arm"]["p90"]
    m = DS.clear_measures(c)
    assert m["arm_socket_out_studs"] <= cap
    assert m["blade_body_max"] == 0.0
    import strike as SK
    import clip as CL
    sink = max(SK.arm_in_body("Left Arm", CL.quat_mat(f[:4]), f[4:7]) for f in c["joints"]["Left Arm"]["frames"])
    assert sink <= 0.22


def test_an_arm_slid_off_its_shoulder_is_put_back():
    """on_socket caps the sideways slide OUT of the socket; a slide up / forward is the arm's own (loved arms do it)"""
    p = {"Right Arm": [0.0, 0.0, 0.0, 1.0, 0.9, 0.4, -0.5], "Left Arm": [0.0, 0.0, 0.0, 1.0, -0.9, 0.0, 0.0]}
    PB.on_socket(p, "Right Arm", "sword_arm")
    PB.on_socket(p, "Left Arm", "free_arm")
    assert p["Right Arm"][4] == PB.vocab()["slide_outward"]["sword_arm"]["p50"] and p["Right Arm"][5:7] == [0.4, -0.5]
    assert p["Left Arm"][4] == -PB.vocab()["slide_outward"]["free_arm"]["p50"]
