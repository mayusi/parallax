"""the learning tools: phase-aligned composition (learn_compose.warp) and the critic (craft.critic)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "anim"))
import craft as CR  # noqa: E402
import learn_compose as LC  # noqa: E402


def test_warp_maps_each_phase_onto_the_other_and_stays_monotone():
    src, dst = [0.0, 0.2, 0.3, 0.4, 1.0], [0.0, 0.5, 0.6, 0.8, 1.5]
    for a, b in zip(src, dst):
        assert abs(LC.warp(src, dst, b) - a) < 1e-9          # the strike lands on the strike
    ts = [LC.warp(src, dst, t / 100) for t in range(0, 151)]
    assert all(b >= a - 1e-12 for a, b in zip(ts, ts[1:]))


def test_critic_tolerates_rounding_and_skips_density_on_authored_moves():
    rules = {"lean_max": {"loved_p20": 20.0, "loved_p80": 60.0, "bad_median": 19.0, "separation": 0.6},
             "key_gap_med": {"loved_p20": 0.017, "loved_p80": 0.05, "bad_median": 0.033, "separation": 0.9},
             "arc": {"loved_p20": 1.2, "loved_p80": 3.0, "bad_median": 2.0, "separation": 0.1}}
    fixes, _ = CR.critic({"lean_max": 19.9, "key_gap_med": 0.0167, "arc": 9.0}, rules)
    assert fixes == []                                        # 19.9 ~ 20 (tolerance); density skipped; arc is no rule
    fixes, _ = CR.critic({"lean_max": 14.0}, rules)
    assert [f["feature"] for f in fixes] == ["lean_max"]      # the rejected from-scratch M1's lean is caught
