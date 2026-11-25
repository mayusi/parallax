"""the pose maths of kit/anim/pose_r6.py (authoring on the owner's R6 rig): conventions, the arm solve, held keys"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import pose_r6 as P  # noqa: E402


def test_stage_axes_map_to_the_rig():
    # stage: x right, y up from the floor, z forward; the rig (Blender): x right, y forward, z up
    assert np.allclose(P.stage([1, 2, 3]), [1, 3, 2])


def test_body_conventions():
    fwd, up = np.array([0, 1.0, 0]), np.array([0, 0, 1.0])
    turned = P.body_rot({"turn": 90}) @ fwd
    assert np.allclose(turned, [1, 0, 0], atol=1e-9)            # turn + = toward the character's right
    leaned = P.body_rot({"lean": 90}) @ up
    assert np.allclose(leaned, [0, 1, 0], atol=1e-9)            # lean + = forward
    tilted = P.body_rot({"tilt": 90}) @ up
    assert np.allclose(tilted, [1, 0, 0], atol=1e-9)            # tilt + = right shoulder down (the top goes right)


def test_arm_reaches_a_hand_target_in_reach():
    D = np.eye(4)
    target = np.array([0.6, 1.0, 2.8])                          # in front of the chest (Blender axes), 1.28 away
    R, slide, _, gap = P.solve_arm("Right Arm", D, target)
    hand = P.PIVOT["Right Arm"] + slide + R @ (P.HAND["Right Arm"] - P.PIVOT["Right Arm"])
    assert gap == 0.0
    assert np.linalg.norm(slide) < 1e-9
    assert np.linalg.norm((hand - P.PIVOT["Right Arm"]) / np.linalg.norm(hand - P.PIVOT["Right Arm"])
                          - (target - P.PIVOT["Right Arm"]) / np.linalg.norm(target - P.PIVOT["Right Arm"])) < 1e-6


def test_arm_slides_toward_a_far_hand_target_at_most_the_stretch():
    target = P.PIVOT["Right Arm"] + np.array([0, 3.0, 0])      # 3 studs straight ahead: reach 1.58 + 0.5 slide
    R, slide, _, gap = P.solve_arm("Right Arm", np.eye(4), target)
    assert abs(np.linalg.norm(slide) - P.STRETCH) < 1e-9
    assert abs(gap - (3.0 - P.REACH - P.STRETCH)) < 1e-9


def test_blade_twist_hits_an_achievable_direction_exactly():
    # the arm straight forward: any blade direction perpendicular to it is achievable by the twist
    target = P.PIVOT["Right Arm"] + np.array([0, 1.4, 0])
    for want in ([0, 0, 1.0], [1.0, 0, 0], [0.6, 0, 0.8]):
        R, _, err, _ = P.solve_arm("Right Arm", np.eye(4), target, blade=np.array(want), grip_pitch=0.0)
        assert err < 0.01, (want, err)


def test_body_relative_arm_rotation():
    # the same world hand target with the body turned: the arm's torso-relative rotation differs, the world one not
    D = P.about(P.PIVOT["Torso"], P.body_rot({"turn": 40}))
    target = np.array([0.0, 1.3, 2.4])
    R_rel, _, _, _ = P.solve_arm("Right Arm", D, target)
    piv = (D @ np.append(P.PIVOT["Right Arm"], 1.0))[:3]
    hand_dir = D[:3, :3] @ R_rel @ (P.HAND["Right Arm"] - P.PIVOT["Right Arm"])
    assert np.allclose(hand_dir / np.linalg.norm(hand_dir), (target - piv) / np.linalg.norm(target - piv), atol=1e-6)


def test_keys_hold_what_they_leave_out():
    spec = {"keys": [{"f": 0, "body": {"turn": 20, "lean": 5}, "left_arm": "hilt"},
                     {"f": 10, "body": {"turn": -30}},
                     {"t": 0.5, "right_foot": {"at": [0.9, 0.2]}}]}
    keys = P.merged_keys(spec, 60)
    assert [k["f"] for k in keys] == [0, 10, 30]
    assert keys[1]["body"]["lean"] == 5 and keys[1]["body"]["turn"] == -30     # lean held, turn changed
    assert keys[2]["left_arm"] == "hilt"
    assert keys[2]["right_foot"]["at"] == [0.9, 0.2] and keys[2]["right_foot"]["lift"] == 0
    assert keys[0]["left_foot"]["at"] == [-0.5, 0]                              # the rest pose fills key 0


def test_check_spec_reports_every_key_without_blender():
    import json
    with open(os.path.join(HERE, "..", "..", "templates", "anim.pose.json"), encoding="utf-8") as fh:
        spec = json.loads(fh.read().replace("__NAME__", "T"))
    rows = P.check_spec(spec)
    assert len(rows) == len(spec["keys"])
    assert all(r["blade_err"] is not None and r["blade_err"] < 0.5 for r in rows)    # the blade lock is exact
    assert all("hilt_gap" in r for r in rows)


def test_arm_keys_hold_field_by_field():
    spec = {"sword": {"blade": 4.0, "grip_pitch": 60},
            "keys": [{"f": 0, "right_arm": {"hand": [0.2, 2.5, 1.0], "blade": [0, 0.4, 0.9]}},
                     {"f": 10, "right_arm": {"blade": [0.5, 0.1, 0.8]}},                 # only the blade: the hand is held
                     {"f": 20, "right_arm": {"aim": [0, 0, 1]}}]}                        # a new placement replaces the hand
    keys = P.merged_keys(spec, 60)
    assert keys[1]["right_arm"] == {"hand": [0.2, 2.5, 1.0], "blade": [0.5, 0.1, 0.8]}
    assert "hand" not in keys[2]["right_arm"] and keys[2]["right_arm"]["aim"] == [0, 0, 1]
    assert keys[2]["right_arm"]["blade"] == [0.5, 0.1, 0.8]
    assert all("right_arm_error" not in r for r in P.check_spec(spec))


def test_rest_arms_hang_at_the_r6_rest():
    k = P.merged_keys({"keys": [{"f": 0}]}, 60)[0]
    for side, arm in (("Right Arm", "right_arm"), ("Left Arm", "left_arm")):
        R, _, _, _ = P.solve_arm(side, np.eye(4), None, aim=P.stage(k[arm]["aim"]))
        assert np.allclose(R, np.eye(3), atol=1e-3)               # the rest key leaves the arm where the rig has it


def test_plant_and_clear_are_not_held():
    keys = P.merged_keys({"keys": [{"f": 0, "body": {"plant": "right", "lean": 10}},
                                   {"f": 10, "body": {"plant": "both", "clear": 0.2}},
                                   {"f": 20, "body": {"turn": 5}}]}, 60)
    assert keys[0]["body"]["plant"] == "right" and "clear" not in keys[0]["body"]
    assert keys[1]["body"]["clear"] == 0.2
    assert "plant" not in keys[2]["body"] and "clear" not in keys[2]["body"] and keys[2]["body"]["lean"] == 10


def test_limb_swing_conventions():
    down = np.array([0, 0, -1.0])
    for side in ("Right Arm", "Left Arm", "Right Leg", "Left Leg"):
        assert np.allclose(P.limb_rot(side, {"swing": 90}) @ down, [0, 1, 0], atol=1e-9)      # forward
        out = P.limb_rot(side, {"out": 90}) @ down
        assert np.sign(out[0]) == (1 if side.startswith("Right") else -1)                      # away from the body



def test_pose_from_decomposition_round_trips():
    import pose_from as PF
    rng = np.random.default_rng(3)
    for _ in range(50):
        for side in ("Right Arm", "Left Arm", "Right Leg", "Left Leg"):
            l = {"swing": float(rng.uniform(-80, 80)), "out": float(rng.uniform(-60, 60)), "twist": float(rng.uniform(-60, 60))}
            R_bl = P.limb_rot(side, l)
            R_rbx = PF.P3.T @ R_bl @ PF.P3
            got = PF.limb_params(R_rbx, side)
            assert np.allclose(P.limb_rot(side, got), R_bl, atol=1e-3)
        b = {"lean": float(rng.uniform(-60, 60)), "turn": float(rng.uniform(-80, 80)), "tilt": float(rng.uniform(-40, 40))}
        R_bl = P.body_rot(b)
        got = PF.body_params(PF.P3.T @ R_bl @ PF.P3)
        assert np.allclose(P.body_rot(got), R_bl, atol=1e-3)


def _pose(deg_z, at):
    a = np.radians(deg_z)
    M = np.eye(4)
    M[:3, :3] = [[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]]
    M[:3, 3] = at
    return M


def test_slerp_pose_ends_and_middle():
    A, B = _pose(0, [0, 0, 0]), _pose(90, [2, 0, 0])
    assert np.allclose(P._slerp_pose(A, B, 0.0), A, atol=1e-9)
    assert np.allclose(P._slerp_pose(A, B, 1.0), B, atol=1e-9)
    assert np.allclose(P._slerp_pose(A, B, 0.5), _pose(45, [1, 0, 0]), atol=1e-9)
    # the short way round: 0 -> 350 deg turns -10 deg, not +350
    assert np.allclose(P._slerp_pose(A, _pose(350, [0, 0, 0]), 0.5), _pose(355, [0, 0, 0]), atol=1e-9)


def test_quaternion_round_trip_every_branch():
    rng = np.random.default_rng(7)
    for R in [np.diag([1.0, -1, -1]), np.diag([-1.0, 1, -1]), np.diag([-1.0, -1, 1])] + [
            P._quat_matrix(q / np.linalg.norm(q)) for q in rng.normal(size=(20, 4))]:
        assert np.allclose(P._quat_matrix(P._quat(R)), R, atol=1e-9)


def test_ride_carries_the_weapon_with_the_fist():
    """the rhand mode (owner 2026-10-26: 'who's moving it? a ghost?'): a weapon held still in the fist's frame goes
    wherever the fist goes - a moving arm moves it, and nothing else does"""
    fist0, fist1 = _pose(0, [0, 0, 0]), _pose(30, [1, 2, 0])
    local = _pose(60, [0.5, 0, 0])
    A, B = fist0 @ local, fist1 @ local
    for u, fist_f in ((0.0, fist0), (1.0, fist1), (0.5, _pose(-40, [5, 5, 5]))):
        assert np.allclose(P.ride(fist_f, fist0, fist1, A, B, u), fist_f @ local, atol=1e-9)
    # a turn authored in the fist's frame (a spin) is interpolated there, then carried
    B2 = fist1 @ _pose(150, [0.5, 0, 0])
    mid = P.ride(fist1, fist0, fist1, A, B2, 0.5)
    assert np.allclose(np.linalg.inv(fist1) @ mid, _pose(105, [0.5, 0, 0]), atol=1e-9)


def test_rhand_is_a_weapon_mode():
    assert P.gun_mode({"f": 0, "gun": {"mode": "rhand"}}) == "rhand"
    assert P.gun_mode({"f": 0}) == "right"


def test_slerp_pose_keeps_a_scaled_weapon_scaled():
    """a weapon object scaled in Blender (the pistol at 0.85): the turn is read without the scale, the scale kept"""
    A, B = _pose(0, [0, 0, 0]), _pose(90, [2, 0, 0])
    A[:3, :3] *= 0.85
    B[:3, :3] *= 0.85
    mid = P._slerp_pose(A, B, 0.5)
    want = _pose(45, [1, 0, 0])
    want[:3, :3] *= 0.85
    assert np.allclose(mid, want, atol=1e-9)


def test_weapon_keys_hold_the_mode_through_arm_only_keys():
    """an arm-only key (the catching hand reaching) never ends a flight: only keys with a "gun" field count"""
    keys = [{"f": 0, "right_arm": {}}, {"f": 37, "gun": {"mode": "free"}}, {"f": 41, "gun": {"mode": "free", "at": [0, 0, 0]}},
            {"f": 43, "right_arm": {"hand": [0, 0, 0]}}, {"f": 44, "gun": {"mode": "right"}}]
    got = P.weapon_keys(keys)
    assert [k["f"] for k in got] == [0, 37, 41, 44]
    assert P.gun_mode(got[0]) == "right"


def test_weapon_keys_skip_a_held_repeat():
    """merged (held) keys repeat the last gun verbatim: a repeat is no new pose to hold the weapon at"""
    fly = {"mode": "free", "at": [1, 2, 3]}
    keys = [{"f": 0, "gun": {"mode": "right"}}, {"f": 41, "gun": dict(fly)}, {"f": 43, "gun": dict(fly), "right_arm": {}},
            {"f": 44, "gun": {"mode": "right"}}]
    assert [k["f"] for k in P.weapon_keys(keys)] == [0, 41, 44]


def test_weapon_keys_keep_an_authors_hold_and_the_hand_until_the_throw():
    hang = {"mode": "free", "at": [1, 2, 3]}
    # merged keys: "_set" says what the author set; a deliberate repeat of the same pose is a HOLD, kept
    keys = [{"f": 0, "gun": {"mode": "right"}, "_set": ["gun"]}, {"f": 10, "gun": dict(hang), "_set": ["gun"]},
            {"f": 15, "gun": dict(hang), "_set": ["right_arm"]}, {"f": 20, "gun": dict(hang), "_set": ["gun"]},
            {"f": 30, "gun": {"mode": "right"}, "_set": ["gun"]}]
    assert [k["f"] for k in P.weapon_keys(keys)] == [0, 10, 20, 30]
    # a straight hand -> posed flight: the hand holds the weapon up to the key before the throw
    keys = [{"f": 0, "gun": {"mode": "right"}, "_set": ["gun"]}, {"f": 30, "gun": {"mode": "right"}, "_set": ["right_arm"]},
            {"f": 37, "gun": dict(hang), "_set": ["gun"]}]
    got = P.weapon_keys(keys)
    assert [(k["f"], P.gun_mode(k)) for k in got] == [(0, "right"), (30, "right"), (37, "free")]


def test_throw_lands_on_both_ends_and_flies_a_gravity_arc():
    A, B = _pose(0, [0, 0, 0]), _pose(30, [1.5, 0, 0])
    T, g, cen = 0.25, 35.0, [0.0, 0.6, 0.2]
    assert np.allclose(P.throw_pose(A, B, 0.0, T, g, cen), A, atol=1e-9)
    assert np.allclose(P.throw_pose(A, B, 1.0, T, g, cen), B, atol=1e-9)
    # the centre: c(t) = cA + v0 t - g t^2 / 2 (up = +z), with v0 from throw_speeds
    v0, v1 = P.throw_speeds(A, B, T, g, cen)
    cA = A[:3, 3] + A[:3, :3] @ np.array(cen)
    for u in (0.25, 0.5, 0.75):
        M = P.throw_pose(A, B, u, T, g, cen)
        c = M[:3, 3] + M[:3, :3] @ np.array(cen)
        t = u * T
        assert np.allclose(c, cA + v0 * t + np.array([0, 0, -0.5 * g * t * t]), atol=1e-9)
    assert np.allclose(v1, v0 + np.array([0, 0, -g * T]), atol=1e-9)


def test_throw_extra_turns_keep_the_ends_and_spin_steadily():
    A, B = _pose(0, [0, 0, 0]), _pose(0, [1, 0, 0])
    with_turn = [P.throw_pose(A, B, u, 0.3, 35.0, [0, 0, 0], spin_axis=(1, 0, 0), turns=-1.0) for u in (0.0, 0.5, 1.0)]
    assert np.allclose(with_turn[0], A, atol=1e-9) and np.allclose(with_turn[2], B, atol=1e-9)
    # halfway through one full turn about x: upside down (y -> -y)
    assert np.allclose(with_turn[1][:3, :3] @ np.array([0, 1, 0]), [0, -1, 0], atol=1e-9)


def test_throw_spin_direction_and_frame_with_a_turned_start():
    """the spin is about the weapon's OWN axis, in the stated direction, steady, from a turned and scaled start"""
    A, B = _pose(90, [0, 0, 0]), _pose(90, [1, 0, 0])
    A[:3, :3] *= 0.85
    B[:3, :3] *= 0.85
    quarter = P.throw_pose(A, B, 0.25, 0.3, 35.0, [0, 0, 0], spin_axis=(1, 0, 0), turns=1.0)
    RA = A[:3, :3] / 0.85
    # a quarter of a +1 turn about the weapon's own x = RA @ rot_x(+90 deg); scale kept
    want = RA @ P._axis_rot((1, 0, 0), np.pi / 2)
    assert np.allclose(quarter[:3, :3] / 0.85, want, atol=1e-9)
    minus = P.throw_pose(A, B, 0.25, 0.3, 35.0, [0, 0, 0], spin_axis=(1, 0, 0), turns=-1.0)
    assert not np.allclose(minus[:3, :3], quarter[:3, :3], atol=1e-6)        # the sign matters


def test_grip_is_keyed_only_where_the_right_arm_is():
    """a left-arm-only key between two right-arm keys must not key the gun's turn in the hand (it held the old turn
    while the arm rolled, then snapped: GunSwitch's 90 deg wind-up roll)"""
    keys = [{"f": 0, "_set": ["right_arm", "left_arm"]}, {"f": 6, "_set": ["left_arm"]},
            {"f": 8, "_set": ["right_arm"]}, {"f": 10, "_set": ["gun"]}, {"f": 12, "_set": ["left_arm"]}]
    assert [P.grip_keyed(k, keys) for k in keys] == [True, False, True, True, True]
    assert P.grip_keyed({"f": 3}, [{"f": 0}, {"f": 3}, {"f": 9}])


def test_edge_twist_keeps_a_forward_held_pistol_arm_steady():
    """a pistol held straight out points almost along the arm: by the blade alone, a 2-degree change of aim turned the
    arm's twist by tens of degrees; fitted to the edge too, the twist barely moves and the grip-down side stays down"""
    D = np.eye(4)
    piv = P.PIVOT["Right Arm"]
    target = piv + P.stage([0.0, 0.1, 1.5])
    down = P.stage([0.0, -1.0, 0.0])

    def twist(blade, edge):
        R = P.solve_arm("Right Arm", D, target, P.stage(blade), 0.0, None, "hand", edge)[0]
        return R

    def ang(A, B):
        return np.degrees(np.arccos(np.clip((np.trace(A.T @ B) - 1) / 2, -1, 1)))

    a, b = [0.03, 0.08, 1.0], [-0.03, 0.06, 1.0]
    assert ang(twist(a, down), twist(b, down)) < 6.0
    assert ang(twist(a, None), twist(b, None)) > ang(twist(a, down), twist(b, down))
