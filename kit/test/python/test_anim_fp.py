"""first-person weapon measures (kit/anim/proc_dossier.py fp_measures; Sample Game's R6 arms, 2026-10-25): the screen
projection, the crosshair ray against an arm box, and the clip numbers on synthetic weapon paths"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "anim"))
import proc_dossier as PD  # noqa: E402


def test_screen_centre_and_edges():
    sx, sy = PD.fp_screen([0.0, 1.5, -2.0])            # straight ahead of the eye
    assert abs(sx) < 1e-9 and abs(sy) < 1e-9
    d = 2.0
    _, sy = PD.fp_screen([0.0, 1.5 - d * math.tan(math.radians(35)), -d])   # the bottom edge of a 70 deg view
    assert abs(sy + 1.0) < 1e-6
    assert PD.fp_screen([0.0, 1.5, 0.5]) is None       # behind the eye


def test_ray_hits_box():
    eye, fwd = np.array([0.0, 1.5, 0.0]), np.array([0.0, 0.0, -1.0])
    M = np.eye(4)
    M[:3, 3] = [0.0, 1.5, -2.0]
    assert PD._ray_hits_box(M, (1.0, 2.0, 1.0), eye, fwd)            # a box on the line
    M[:3, 3] = [2.0, 1.5, -2.0]
    assert not PD._ray_hits_box(M, (1.0, 2.0, 1.0), eye, fwd)        # beside it
    M[:3, 3] = [0.0, 1.5, 2.0]
    assert not PD._ray_hits_box(M, (1.0, 2.0, 1.0), eye, fwd)        # behind the eye


def _clip(pitches_deg, grip=(0.4, 0.9, -1.4)):
    g = np.array(grip)
    tips = [list(g + 1.1 * np.array([0.0, math.sin(math.radians(p)), -math.cos(math.radians(p))])) for p in pitches_deg]
    n = len(pitches_deg)
    return {"name": "FpTest", "rig": "R6", "fps": 60, "times": [i / 60 for i in range(n)], "joints": {}, "events": [],
            "sword": {"tip": tips, "grip_path": [list(g)] * n}}


def test_recoil_rise_and_peak():
    fns, _ = PD.fp_measures(_clip([0, 6, 12, 15, 10, 4, 0, 0]), {"build": {}})
    assert abs(fns["muzzle_rise_deg"]({}) - 15.0) < 1e-6
    assert abs(fns["muzzle_peak_s"]({}) - 3 / 60) < 1e-9
    assert fns["fp_weapon_in_view_share"]({}) == 1.0
    assert fns["fp_center_blocked_share"]({}) == 0.0       # the rest arms hang at the sides: the centre is clear
    assert abs(fns["clip_seconds"]({}) - 7 / 60) < 1e-9     # 8 frames span 7 frame steps (the played duration)


def test_grip_roll():
    c = _clip([0, 0, 0])
    c["sword"]["edge"] = [[0.0, -1.0, 0.0], [-0.7071, -0.7071, 0.0], [-1.0, 0.0, 0.0]]   # 0, 45, 90 deg about the barrel
    fns, _ = PD.fp_measures(c, {"build": {}})
    assert abs(fns["grip_roll_max_deg"]({}) - 90.0) < 1e-3


def test_weapon_off_screen_counts():
    c = _clip([0, 0, 0, 0])
    c["sword"]["grip_path"][2] = [0.4, -3.0, -1.4]          # one frame the grip falls far below the screen
    fns, _ = PD.fp_measures(c, {"build": {}})
    assert abs(fns["fp_weapon_in_view_share"]({}) - 0.75) < 1e-9


def test_measures_registered():
    for m in ("fp_weapon_in_view_share", "fp_weapon_low_y", "fp_center_blocked_share", "muzzle_rise_deg", "muzzle_peak_s"):
        assert m in PD.MEASURES
