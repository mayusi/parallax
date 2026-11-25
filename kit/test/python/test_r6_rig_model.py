"""the owner's R6 rig as mathematics (kit/anim/r6_rig_model.py): the behaviours measured on the rig itself
(kit/anim/rig_study.py, rig_model_check.py: 300 random poses within 0.0003 studs) held as equations"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import r6_rig_model as M  # noqa: E402

IK = {"SoftIK.L": {"loc": [2, 0, 0], "FK": False}, "SoftIK.R": {"loc": [-2, 0, 0], "FK": False}}


def q(axis, deg):
    a = math.radians(deg) / 2
    x, y, z = axis
    return [math.cos(a), x * math.sin(a), y * math.sin(a), z * math.sin(a)]


def leg_axis(D, side=-1):
    top, bot = D @ np.array([0.5 * side, 0, 2, 1.0]), D @ np.array([0.5 * side, 0, 0, 1.0])
    return (top - bot)[:3] / 2.0, bot[:3]


def test_rest_is_rest():
    for part, D in M.parts({}).items():
        assert np.allclose(D, np.eye(4), atol=1e-9), part


def test_ik_crouch_leaves_the_legs_where_they_stand():
    # Body local y is world up: lowering it 1.2 drops the torso; the IK legs stay vertical, their tops sink into it
    P = M.parts({**IK, "Body": {"loc": [0, -1.2, 0]}})
    assert np.allclose(P["Torso"][:3, 3], [0, 0, -1.2])
    axis, sole = leg_axis(P["Left Leg"])
    assert np.allclose(sole, [-0.5, 0, 0], atol=1e-6)
    assert axis[2] > 0.99                                       # within ~5 degrees of vertical


def test_fk_crouch_takes_the_legs_through_the_floor():
    P = M.parts({"Body": {"loc": [0, -1.2, 0]}})               # as shipped: FK box on, slider 0
    _, sole = leg_axis(P["Left Leg"])
    assert abs(sole[2] + 1.2) < 1e-6


def test_ik_foot_forward_leans_the_leg_and_pins_the_sole():
    P = M.parts({**IK, "Foot.L": {"loc": [0, 1.0, 0]}})         # Foot local y = world forward
    axis, sole = leg_axis(P["Left Leg"])
    assert np.allclose(sole, [-0.5, 1.0, 0], atol=1e-6)
    lean = math.degrees(math.atan2(axis[1], axis[2]))
    assert -28 < lean < -24                                     # top behind the foot: ~26 degrees


def test_feet_cannot_go_below_the_floor():
    P = M.parts({**IK, "Foot.L": {"loc": [0, 0, -0.5]}})
    _, sole = leg_axis(P["Left Leg"])
    assert sole[2] >= -1e-9


def test_head_keeps_its_world_facing_when_the_body_or_root_turns():
    for ctrl in ("Body", "Main Controller"):
        P = M.parts({ctrl: {"quat": q((0, 1, 0), 90)}})         # local y = world up for both
        assert np.allclose(P["Head"][:3, :3], np.eye(3), atol=1e-9), ctrl
        assert not np.allclose(P["Torso"][:3, :3], np.eye(3))


def test_head_pivot_rides_the_body_neck_point():
    P = M.parts({"Body": {"quat": q((1, 0, 0), 30)}})
    piv = P["Head"] @ np.array([0, 0, 4.0, 1.0])
    assert np.allclose(piv[:3], (P["Torso"] @ np.array([0, 0, 4.0, 1.0]))[:3], atol=1e-9)


def test_softik_slider_blends_fk_into_ik_linearly_in_angle():
    leans = []
    for s in (0.0, 1.0, 2.0):
        P = M.parts({"FKLeg.L": {"euler": [math.radians(40), 0, 0]}, "Foot.L": {"loc": [0, -1.0, 0]},
                     "SoftIK.L": {"loc": [s, 0, 0], "FK": True}})
        axis, _ = leg_axis(P["Left Leg"])
        leans.append(math.degrees(math.atan2(axis[1], axis[2])))
    assert abs(leans[0] + 40) < 0.5 and abs(leans[2] - 25.7) < 0.5
    assert abs(leans[1] - (leans[0] + leans[2]) / 2) < 1.0


def test_knee_pole_only_tilts_the_aim_a_few_degrees():
    base = leg_axis(M.parts({**IK, "Body": {"loc": [0, -0.35, 0]}})["Left Leg"])[0]
    for dx in (-2.0, 2.0):
        a = leg_axis(M.parts({**IK, "Body": {"loc": [0, -0.35, 0]}, "Knee.L": {"loc": [dx, 0, 0]}})["Left Leg"])[0]
        assert math.degrees(math.acos(min(1.0, float(np.dot(base, a))))) < 5.0
