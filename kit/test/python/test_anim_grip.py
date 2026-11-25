"""kit/anim/grip.py - the sword as its own joint (board m39b): the Handle Motor6D's track reproduces the clip's own
blade path through the R6 arm, for a real strike (the katana kesa built by strike.py)"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import grip as GR    # noqa: E402
import strike as S   # noqa: E402

MOVE = {"name": "GripProbe", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4, "leg_slide": 1.3,
        "sword": {"length": 3.6, "grip": 0.5, "kind": "katana"},
        "keys": [{"t": 0.0, "yaw": 0, "grip": [0.4, -0.4, -1.6], "dir": [0.2, 0.7, -0.7], "pos": [0, -0.6, 0],
                  "right": [0.55, 0, 1.0], "left": [-0.57, 0, -0.7], "ease": "InOut"},
                 {"t": 0.2, "yaw": 20, "grip": [0.9, 0.6, -0.6], "dir": [0.3, 0.6, 0.75], "pos": [0, -0.6, 0],
                  "right": [0.55, 0, 1.0], "left": [-0.57, 0, -0.7], "ease": "InOut"},
                 {"t": 0.4, "yaw": -20, "grip": [-0.3, -0.6, -2.0], "dir": [-0.5, -0.3, -0.8], "pos": [0, -0.6, 0],
                  "right": [0.55, 0, 1.0], "left": [-0.57, 0, -0.7], "ease": "InOut"}]}


def test_grip_track_round_trips_the_blade():
    clip = S.generate(json.loads(json.dumps(MOVE)))[0]
    GR.add_grip(clip)
    assert len(clip["grip"]) == len(clip["times"])
    assert GR.round_trip_error(clip) < 1e-4                        # the joint puts the tip where the clip has it
    q = np.array([g[:4] for g in clip["grip"]])
    assert np.allclose(np.linalg.norm(q, axis=1), 1.0, atol=1e-5)   # unit quaternions


def test_handle_frame_axes():
    M = GR.handle_frame([0, 3, 0], [0, 0, 0], [1, 0, 0])
    assert np.allclose(M[:3, 1], [0, 1, 0])                         # +Y to the tip
    assert np.allclose(M[:3, 0], [-1, 0, 0])                        # -X toward the edge
    assert np.allclose(np.cross(M[:3, 0], M[:3, 1]), M[:3, 2])      # right-handed


def test_no_sword_no_track():
    clip = {"times": [0.0], "joints": {}, "rig": "R6"}
    assert GR.grip_track(clip) is None and "grip" not in GR.add_grip(clip)


# --- the LEFT hand's weapon (Sample Game's Onyx, 2026-10-26): a pose key's "left_gun" aims it ---

def _left_clip():
    clip = S.generate(json.loads(json.dumps(MOVE)))[0]
    fps = clip["fps"]
    n = len(clip["times"])
    last = round(clip["times"][-1] * fps)
    keys = [{"f": 0, "ease": "linear", "left_gun": {"blade": [0, 0, 1]}},                       # forward, upright
            {"f": last, "left_gun": {"blade": [1, 0, 0], "edge": [0, 0, -1]}}]                  # to the right, grip back
    return clip, keys, n


def test_left_gun_points_where_its_keys_say():
    clip, keys, n = _left_clip()
    GR.add_grip_left(clip, keys)
    assert len(clip["grip_left"]) == n
    barrels = np.array(GR.left_barrels(clip))
    assert np.allclose(barrels[0], [0, 0, -1], atol=1e-4)            # stage forward = character -Z
    assert np.allclose(barrels[-1], [1, 0, 0], atol=1e-4)
    q = np.array([g[:4] for g in clip["grip_left"]])
    assert np.allclose(np.linalg.norm(q, axis=1), 1.0, atol=1e-5)
    assert np.allclose(np.array([g[4:7] for g in clip["grip_left"]]), 0, atol=1e-6)   # the grip stays in the fist


def test_left_gun_turns_smoothly_between_keys():
    clip, keys, n = _left_clip()
    GR.add_grip_left(clip, keys)
    barrels = np.array(GR.left_barrels(clip))
    steps = [float(np.degrees(np.arccos(np.clip(np.dot(a, b), -1, 1)))) for a, b in zip(barrels, barrels[1:])]
    assert max(steps) < 90.0 / (n - 1) * 1.5 + 1e-6                  # a linear 90 deg turn: even steps, no jump


def test_no_left_gun_keys_no_track():
    clip = S.generate(json.loads(json.dumps(MOVE)))[0]
    assert GR.grip_left_track(clip, [{"f": 0}]) is None and "grip_left" not in GR.add_grip_left(clip, [{"f": 0}])


def test_left_c0_is_the_games_left_grip():
    # Config.DualWield.LeftGrip = CFrame.fromMatrix((0, -0.95, 0), X = (0, 0, -1), Y = (0, -1, 0)): an un-keyed clip
    # (identity Transform) must hold Onyx exactly where the game always did
    assert np.allclose(GR.LEFT_C0[:3, 0], [0, 0, -1]) and np.allclose(GR.LEFT_C0[:3, 1], [0, -1, 0])
    assert np.allclose(GR.LEFT_C0[:3, 3], [0, -0.95, 0])
    assert np.allclose(np.cross(GR.LEFT_C0[:3, 0], GR.LEFT_C0[:3, 1]), GR.LEFT_C0[:3, 2])


def test_left_gun_can_leave_the_fist_and_come_back():
    clip = S.generate(json.loads(json.dumps(MOVE)))[0]
    fps = clip["fps"]
    last = round(clip["times"][-1] * fps)
    mid = last // 2
    keys = [{"f": 0, "ease": "linear", "left_gun": {"blade": [0, 0, 1]}},                       # in the fist
            {"f": mid, "ease": "linear", "left_gun": {"blade": [0, 1, 0], "at": [-0.5, 6.0, 1.0]}},   # up in the air
            {"f": last, "left_gun": {"blade": [0, 0, 1]}}]                                       # caught again
    GR.add_grip_left(clip, keys)
    g = clip["grip_left"]
    assert np.allclose(g[0][4:7], 0, atol=1e-6) and np.allclose(g[-1][4:7], 0, atol=1e-6)   # in the fist at both ends
    rig = GR.C.load_rig("r6")
    A = GR.C.fk(rig, GR.C.character_transforms(clip, rig, mid))["Left Arm"]
    T = np.eye(4)
    T[:3, :3] = GR.C.quat_mat(g[mid][:4])
    T[:3, 3] = g[mid][4:7]
    assert np.allclose((A @ GR.LEFT_C0 @ T)[:3, 3], [-0.5, 3.0, -1.0], atol=1e-4)   # stage (-0.5, 6, 1) in char space


def test_left_gun_throw_flies_a_ballistic_arc_and_lands_in_the_fist():
    # Onyx thrown like Pearl (style v4, 2026-10-27): a "throw" key lets it go from the fist, it lands on the next key
    clip = S.generate(json.loads(json.dumps(MOVE)))[0]
    fps = clip["fps"]
    last = round(clip["times"][-1] * fps)
    keys = [{"f": 0, "ease": "linear", "left_gun": {"blade": [0, 0, 1], "throw": {"turns": 1, "g": 35.0}}},
            {"f": last, "left_gun": {"blade": [0, 0, 1]}}]
    GR.add_grip_left(clip, keys)
    g = clip["grip_left"]
    assert np.allclose(g[0][4:7], 0, atol=1e-4) and np.allclose(g[-1][4:7], 0, atol=1e-6)   # leaves and lands in the fist
    rig = GR.C.load_rig("r6")
    cen = []
    for i in range(len(g)):
        A = GR.C.fk(rig, GR.C.character_transforms(clip, rig, i))["Left Arm"]
        T = np.eye(4)
        T[:3, :3] = GR.C.quat_mat(g[i][:4])
        T[:3, 3] = g[i][4:7]
        cen.append((A @ GR.LEFT_C0 @ T @ np.array(list(GR.LEFT_PIVOT) + [1.0]))[:3])
    cen = np.array(cen)
    # the centre's height: a parabola under g (constant second difference g / fps^2 down) between the ends
    d2 = np.diff(cen[:-1, 1], 2) * fps * fps
    assert np.allclose(d2, -35.0, atol=0.5)
    # one whole turn on top of the (zero) turn between the keys: the barrel passes pointing backward mid-flight
    mid = len(g) // 2
    A = GR.C.fk(rig, GR.C.character_transforms(clip, rig, mid))["Left Arm"]
    T = np.eye(4)
    T[:3, :3] = GR.C.quat_mat(g[mid][:4])
    barrel = (A @ GR.LEFT_C0 @ T)[:3, 1]
    assert barrel[2] > 0.8                       # character space: -z is forward, so +z = pointing back


def test_left_gun_eases_like_blender():
    # a sine / quad key eases the left gun's turn as Blender eases the arm (Penner curves), not on a straight line
    assert abs(GR._alpha("quad_in", 0.5) - 0.25) < 1e-9 and abs(GR._alpha("quad_out", 0.5) - 0.75) < 1e-9
    assert abs(GR._alpha("sine_inout", 0.25) - (1 - np.cos(np.pi / 4)) / 2) < 1e-9
    assert abs(GR._alpha("cubic_in", 0.5) - 0.125) < 1e-9 and GR._alpha("linear", 0.3) == 0.3
    for e in ("sine_in", "quad_inout", "expo_out", "circ_in", "back_out", "bounce_out", "bezier"):
        assert abs(GR._alpha(e, 0.0)) < 1e-6 and abs(GR._alpha(e, 1.0) - 1.0) < 1e-6


def test_left_paths_follow_the_left_gun():
    # the look draws Onyx from these: the grip is the Handle's origin, the tip `length` down its barrel
    clip, keys, n = _left_clip()
    GR.add_grip_left(clip, keys)
    p = GR.left_paths(clip, 1.5)
    assert len(p["grip_path"]) == len(p["tip"]) == len(p["edge"]) == n and p["kind"] == "pistol"
    barrels = np.asarray(GR.left_barrels(clip))
    d = np.asarray(p["tip"]) - np.asarray(p["grip_path"])
    assert np.allclose(d, barrels * 1.5, atol=1e-6)
    assert np.allclose(np.einsum("ij,ij->i", np.asarray(p["edge"]), barrels), 0, atol=1e-5)   # the edge is square to it (tracks keep 6 decimals)
