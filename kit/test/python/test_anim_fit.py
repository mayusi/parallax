"""kit/anim/measure.py + fit_r6.py: a clip measures to the curves it was built from, two different gaits are far
apart, and a fit from the kind's defaults recovers a clip generated with other parameters (the generator can
reproduce its own vocabulary). Run: python -m pytest -q kit/test/python/test_anim_fit.py"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import fit_r6 as F        # noqa: E402
import gait_r6 as G       # noqa: E402
import measure as M       # noqa: E402


def test_measure_reads_the_generator_back():
    clip = G.generate({"name": "T", "kind": "run", "fps": 30, "lean": 14.0, "twist": 15.0})
    rec, cv = M.describe(clip)
    assert abs(rec["relations"]["torso_lean_mean"] + 14.0) < 1.0
    assert rec["relations"]["head_yaw_vs_torso_yaw"] < -0.95
    assert rec["relations"]["right_arm_vs_right_leg"] < -0.6
    assert rec["joints"]["Right Leg"]["pitch"][1] > 50


def test_distance_is_zero_to_itself_and_large_between_kinds():
    a = G.generate({"name": "A", "kind": "run", "fps": 30})
    b = G.generate({"name": "B", "kind": "walk", "fps": 30})
    cva, _ = M.curves(a)
    cvb, _ = M.curves(b)
    assert M.distance(cva, cva)["total"] < 0.01
    assert M.distance(cva, cvb)["total"] > 8.0


def test_fit_recovers_a_generated_target():
    target = G.generate({"name": "Target", "kind": "run", "fps": 30, "amp_fwd": 58.0, "amp_back": 80.0, "lean": 18.0,
                         "twist": 12.0, "knee": 0.7, "reach": 1.2, "arm_fwd": 130.0, "arm_back": 30.0, "drop": 0.15})
    spec = {"name": "Fit", "kind": "run", "fps": 30, "speed": 16.0}
    p, best, d, _ = F.fit(spec, target, rounds=6)
    assert best < 6.0, (best, d)
    assert abs(p["lean"] - 18.0) < 4.0
    assert abs(p["amp_back"] - 80.0) < 15.0
