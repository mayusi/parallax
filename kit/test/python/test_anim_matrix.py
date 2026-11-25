"""kit/anim/proc_candidates.matrix_hit (AAA gaps v2 C3): a reaction spec's `from` turns the dossier's FRONT hit to the
side the blow comes from, `scale` sizes its impulse; the reaction's calibrated body give is no longer clamped up"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import proc_candidates as P  # noqa: E402

FRONT = {"dir": [-0.55, -0.15, 1.0], "speed": 11.0}


def test_sides_push_the_body_away_from_the_attacker():
    # R6 faces -Z, its right is +X: a blow from the front drives the body back (+Z), from the back forward (-Z), from
    # the left toward +X, from the right toward -X
    assert P.matrix_hit(FRONT, None, {"from": "Front"})[0]["dir"][2] > 0.9
    assert P.matrix_hit(FRONT, None, {"from": "Back"})[0]["dir"][2] < -0.9
    assert P.matrix_hit(FRONT, None, {"from": "Left"})[0]["dir"][0] > 0.9
    assert P.matrix_hit(FRONT, None, {"from": "Right"})[0]["dir"][0] < -0.9


def test_a_side_keeps_the_hit_size_and_scale_sizes_it():
    for side in ("Front", "Back", "Left", "Right"):
        h, _ = P.matrix_hit(FRONT, None, {"from": side})
        assert math.isclose(math.hypot(h["dir"][0], h["dir"][2]), math.hypot(-0.55, 1.0), rel_tol=1e-3)
        assert h["dir"][1] == -0.15 and h["speed"] == 11.0
    h, body = P.matrix_hit(FRONT, {"speed": 6.0}, {"from": "Front", "scale": 0.6})
    assert math.isclose(h["speed"], 6.6) and math.isclose(body["speed"], 3.6)


def test_calibrated_give_below_the_floor_survives():
    d = {"build": {"hit": dict(FRONT, dur=0.1), "sim": {"root_rot_give": 0.1}}}
    _, _, sim = P.react_genome(d, {"weight": 0.0, "time": 0.0, "space": 0.0, "flow": 0.0})
    assert sim["root_rot_give"] == 0.1
