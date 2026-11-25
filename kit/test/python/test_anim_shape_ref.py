"""kit/anim/shape_ref.py + proc_strike variants (the owner 2026-11-04, 'All bad' on both round-0 sets: stilts, arm-only
swings, a spin whose blade flopped, eight cousins of one base): a stilt clip and a crouched one read apart, a flat
spinning disc and a flopping blade read apart, a held finish is measured after the Hit, a move's variants build"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import proc_strike as PST  # noqa: E402
import shape_ref as SR     # noqa: E402

PARTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]


def clip(n=60, sink=0.0, yaw_turns=0.0, hit=0.2):
    """an R6 clip: the torso sunk `sink` with both legs slid as far INTO it (the feet stay down), turning yaw_turns"""
    def q(t):
        a = 2 * math.pi * yaw_turns * t / max(n - 1, 1)
        return [0.0, math.sin(a / 2), 0.0, math.cos(a / 2)]
    j = {p: {"frames": [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0] for _ in range(n)]} for p in PARTS}
    j["Torso"]["frames"] = [q(t) + [0.0, -sink, 0.0] for t in range(n)]
    for p in ("Right Leg", "Left Leg"):
        j[p]["frames"] = [[0.0, 0.0, 0.0, 1.0, 0.0, sink, 0.0] for _ in range(n)]
    return {"rig": "R6", "fps": 60, "times": [i / 60 for i in range(n)], "joints": j, "events": [{"name": "Hit", "t": hit}]}


def test_stilts_and_a_held_crouch_read_apart():
    tall, low = SR.measure(clip()), SR.measure(clip(sink=0.6))
    assert tall["crouch_hold_share"] == 0.0 and abs(tall["leg_slide_in_max"]) < 0.05
    assert low["crouch_hold_share"] == 1.0 and abs(low["crouch_max_studs"] - 0.6) < 0.05
    assert abs(low["leg_slide_in_max"] - 0.6) < 0.05
    # a still clip holds from the Hit to its end
    assert low["finish_hold_s"] >= 0.6


def _spin_with_blade(flop):
    n = 120
    c = clip(n=n, sink=0.6, yaw_turns=6.0)
    tip, grip = [], []
    for i in range(n):
        a = 2 * math.pi * 6.0 * i / (n - 1)
        out = [math.cos(a), 0.0, -math.sin(a)]
        g = [2.0 * out[0], 0.2, 2.0 * out[2]]
        el = math.radians(60 * math.sin(7 * a)) if flop else 0.0
        d = [out[0] * math.cos(el), math.sin(el), out[2] * math.cos(el)]
        grip.append(g)
        tip.append([g[k] + 5.4 * d[k] for k in range(3)])
    c["sword"] = {"tip": tip, "grip_path": grip}
    return SR.measure(c)


def test_a_flat_disc_and_a_flopping_blade_read_apart():
    disc, flop = _spin_with_blade(False), _spin_with_blade(True)
    assert disc["spin_turns_per_s"] > 2.5 and disc["blade_plane_dev_deg"] < 2 and disc["blade_plane_tilt_deg"] < 2
    assert abs(disc["blade_reach_studs"] - 2.0) < 0.1
    assert flop["blade_plane_dev_deg"] > 30


def test_a_moves_variants_build_with_their_own_keys():
    m = {"name": "X", "keys": [{"t": 0.0}], "events": [{"name": "Hit", "t": 0.1}],
         "variants": [{"name": "low", "keys": [{"t": 0.0}, {"t": 0.5}], "events": [{"name": "Hit", "t": 0.3}]}]}
    assert PST.with_variant(m, 0)["keys"] == [{"t": 0.0}] and "variants" not in PST.with_variant(m, 0)
    v = PST.with_variant(m, 1)
    assert len(v["keys"]) == 2 and v["events"][0]["t"] == 0.3 and v["variant"] == "low"
    assert PST.with_variant(m, 9)["keys"] == [{"t": 0.0}]          # out of range: the base


def test_the_picks_page_takes_its_loved_refs_by_kind():
    """the drill's 'nearest loved' was HeartRipOut by pose distance (the governor 2026-11-04): a dossier's loved_refs
    name the refs by kind for the clips they match; no match = the whole loved bank"""
    import proc_picks as PP
    d = {"build": {"loved_refs": {"DTDrillSpin*": ["spin_a", "spin_b"]}}}
    assert PP.refs_by_kind(d, "DTDrillSpin_r1_c3") == ["spin_a", "spin_b"]
    assert PP.refs_by_kind(d, "SwordTrickCut") is None and PP.refs_by_kind({"build": {}}, "X") is None


def test_the_longest_unseen_stretch_is_measured_for_the_gate():
    """the governor 2026-11-04: no candidate may hide the blade from the game camera > ~0.25 s - a blade aimed at the
    camera the whole clip is unseen the whole clip; the same blade across the view is never unseen"""
    import numpy as np
    import proc_dossier as PD
    cam = PD.FP_EYE + np.array([2.2, 0.9, 9.0])
    n = 60
    grip = np.array([1.4, 1.2, -0.7])
    for tip, want in ((grip + 3.6 * (cam - grip) / np.linalg.norm(cam - grip), (0.9, 1.1)), (grip + np.array([3.6, 0.0, 0.0]), (0.0, 0.0))):
        c = clip(n=n)
        c["sword"] = {"tip": [list(tip)] * n, "grip_path": [list(grip)] * n}
        v = PD.cut_measures(c, [2.2, 0.9, 9.0])["blade_unseen_max_s"]
        assert want[0] <= v <= want[1], v
