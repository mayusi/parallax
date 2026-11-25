"""proc_air.py — JUMP / FALL / LAND made FROM SCRATCH (mission 2026-10-14; the earlier jump / fall re-animated loved
clips' own keys). Craft (research 2026-10-13): anticipation crouch -> takeoff STRETCH (arms flung up, head up) -> a
tuck in the air (asymmetric legs, no twinning) -> apex; a fall that never freezes (arms up and out, a slow alternating
flail, legs dangling, the head looking down for the ground); a land with an impact squash (drop + forward pitch, arms
out for balance) and a recovery. R6 has no knee: a crouch = the legs split + slid up, the torso dropped.
    from proc_air import jump_keys, fall_keys, land_keys"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import proc_director as DR  # noqa: E402

D2R = math.pi / 180


def body(lean=0.0, dy=0.0, head_pitch=0.0, legR=0.0, legL=0.0, liftR=0.0, liftL=0.0, armR=0.0, armL=0.0, outR=0.0,
         outL=0.0, roll=0.0):
    """a pose from body-language numbers (deg / studs): lean + = forward; arms + = forward/up; out + = away from body"""
    p = DR.rest()
    p = DR.turn(p, "Torso", [-lean * D2R, 0.0, roll * D2R])
    p["Torso"][5] += dy
    p = DR.turn(p, "Head", [(lean * 0.5 + head_pitch) * D2R, 0.0, 0.0])
    for leg, a, lift in (("Right Leg", legR, liftR), ("Left Leg", legL, liftL)):
        p = DR.turn(p, leg, [a * D2R, 0.0, 0.0])
        p[leg][5] += lift
    for arm, a, o, s in (("Right Arm", armR, outR, 1), ("Left Arm", armL, outL, -1)):
        p = DR.turn(p, arm, [a * D2R, 0.0, o * D2R * s])
    return p


def jump_keys():
    stand = body(lean=3, armR=4, armL=6, outR=4, outL=5)
    crouch = body(lean=14, dy=-0.32, head_pitch=-2, legR=18, legL=-14, liftR=0.14, liftL=0.12, armR=-38, armL=-34, outR=8, outL=8)
    stretch = body(lean=-12, dy=0.18, head_pitch=4, legR=-6, legL=-10, armR=150, armL=142, outR=14, outL=12)
    tuck = body(lean=6, dy=0.1, head_pitch=4, legR=38, legL=-6, liftR=0.38, liftL=0.12, armR=118, armL=124, outR=24, outL=20)
    apex = body(lean=4, dy=0.05, head_pitch=-2, legR=26, legL=8, liftR=0.28, liftL=0.18, armR=96, armL=104, outR=30, outL=26)
    # crouch + stretch are 0.1 s apart: stiff keys, or the torso's spring smooths the 26-deg lean swing to ~10 and the
    # arm fling reads as arms-only (the robot_arm gate)
    return [{"pose": stand, "t": 0.0}, {"pose": crouch, "t": 0.11, "stiff": 2.0}, {"pose": stretch, "t": 0.21, "stiff": 2.0},
            {"pose": tuck, "t": 0.38}, {"pose": apex, "t": 0.58}], 0.58


def fall_keys(period=0.9):
    a = body(lean=-4, head_pitch=-12, legR=14, legL=-4, liftR=0.15, liftL=0.05, armR=128, armL=112, outR=34, outL=40, roll=2)
    b = body(lean=-6, head_pitch=-9, legR=-2, legL=12, liftR=0.06, liftL=0.16, armR=110, armL=130, outR=40, outL=33, roll=-2)
    return [{"pose": a, "t": 0.0}, {"pose": b, "t": period / 2}, {"pose": a, "t": period}], period


def land_keys():
    air = body(lean=-4, head_pitch=-12, legR=14, legL=-4, liftR=0.15, liftL=0.05, armR=120, armL=118, outR=36, outL=36)
    impact = body(lean=18, dy=-0.36, head_pitch=4, legR=16, legL=-16, liftR=0.14, liftL=0.14, armR=34, armL=28, outR=34, outL=30)
    settle = body(lean=7, dy=-0.12, legR=6, legL=-6, liftR=0.05, liftL=0.05, armR=10, armL=12, outR=10, outL=12)
    stand = body(lean=3, armR=4, armL=6, outR=4, outL=5)
    return [{"pose": air, "t": 0.0}, {"pose": impact, "t": 0.07}, {"pose": settle, "t": 0.28}, {"pose": stand, "t": 0.55}], 0.55
