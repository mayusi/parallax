"""kit/anim/proc_strike.py - the strike builder for `kit anim candidates` (2026-11-04: weapon moves had no candidates;
the owner: 'USE THE PIPELIE PROPERLY'): the four effort sliders vary a strike move's own keys, the markers move with
the keys, the crouch stays within R-anim-6, and every candidate carries the vocabulary gate"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import proc_strike as PS  # noqa: E402

MOVE = {"name": "StrikeProbe", "fps": 60, "arm_slide": 2.4, "lag": 0.03, "sword": {"length": 5.0, "grip": 0.75},
        "events": [{"name": "Hit", "t": 0.2}], "block_keys": [0.0, 0.2],
        "keys": [{"t": 0.0, "grip": [1.3, -0.4, -0.4], "dir": [0.2, -0.32, 0.92], "yaw": 0, "crouch": 0.3, "pitch": -10},
                 {"t": 0.2, "grip": [0.4, 0.5, -2.3], "dir": [-0.1, 0.0, -1.0], "yaw": 30, "crouch": 0.4, "pitch": -12, "overshoot": 0.05},
                 {"t": 0.5, "grip": [-1.5, 1.0, -1.5], "dir": [-0.8, 0.3, -0.5], "yaw": 60, "crouch": 0.45, "pitch": -6}]}


def test_sudden_shortens_the_move_and_the_markers_follow():
    m = PS.apply_sliders(MOVE, {"time": 1.0, "weight": 0, "space": 0, "flow": 0})
    assert abs(m["keys"][-1]["t"] - 0.5 * 0.85) < 1e-6
    assert abs(m["events"][0]["t"] - 0.2 * 0.85) < 1e-6 and abs(m["block_keys"][1] - 0.2 * 0.85) < 1e-6
    ts = [k["t"] for k in m["keys"]]
    assert ts == sorted(ts)


def test_weight_deepens_within_the_crouch_limit_space_turns_past_the_hit_flow_loosens():
    m = PS.apply_sliders(MOVE, {"time": 0, "weight": 1.0, "space": 1.0, "flow": 1.0})
    assert all(k["crouch"] <= PS.CROUCH_MAX for k in m["keys"])
    assert m["keys"][2]["crouch"] > MOVE["keys"][2]["crouch"] and m["keys"][0]["pitch"] < MOVE["keys"][0]["pitch"]
    assert m["keys"][2]["yaw"] == 70 and m["keys"][0]["yaw"] == 0          # (only after the Hit)
    assert m["lag"] > MOVE["lag"] and m["keys"][1]["overshoot"] > 0.05
    assert MOVE["keys"][2]["crouch"] == 0.45                                # (the base untouched)


def test_build_generates_a_clip_with_the_vocab_gate(tmp_path, monkeypatch):
    import json
    monkeypatch.chdir(tmp_path)
    os.makedirs(os.path.join("assets", "animations"))
    json.dump(MOVE, open(os.path.join("assets", "animations", "StrikeProbe.move.json"), "w"))
    c, b = PS.build({"build": {"builder": "fp_weapon"}}, {"time": 0, "weight": 0, "space": 0, "flow": 0}, "StrikeProbe_r0_c0")
    assert b["slides"] == "r6_vocab" and c["sword"]["tip"] and any(e["name"] == "Hit" for e in c["events"])


def test_a_moves_variants_share_the_sheet(tmp_path, monkeypatch):
    """the owner 2026-11-04 'All bad': 8 cousins of one base. A move with variants deals its lines across the 8 - each
    at most its share while others still pass (round 1 of the rebuild had 5 of 8 drills on one entry)"""
    import json
    import proc_candidates as PC
    monkeypatch.chdir(tmp_path)
    os.makedirs(os.path.join("assets", "animations"))
    m = dict(MOVE, variants=[{"name": "b", "keys": MOVE["keys"]}, {"name": "c", "keys": MOVE["keys"]}, {"name": "d", "keys": MOVE["keys"]}])
    json.dump(m, open(os.path.join("assets", "animations", "StrikeProbe.move.json"), "w"))
    d = {"build": {"builder": "strike"}, "category": "combat"}   # keyed blocks (fp_weapon is proc_blade's since 11-05)
    monkeypatch.setattr(PC.DS, "require", lambda name: d)
    monkeypatch.setattr(PC.PK, "slide_ranges", lambda: None)
    monkeypatch.setattr(PC.PST, "build", lambda d, s, name: ({"events": [{"name": "Hit", "t": 0.2}], "times": [0.0, 0.5], "v": s["variant"]}, {}))
    # variant 0 always passes (it would fill the sheet alone); the others pass sometimes
    seen = {}

    def gate(c, d, b, arms):
        seen[c["v"]] = seen.get(c["v"], 0) + 1
        return (c["v"] == 0 or seen[c["v"]] % 2 == 0), ["x"], []
    monkeypatch.setattr(PC, "gate", gate)
    man = PC.make("StrikeProbe", "probe", n=8, fresh=True, change="variants")
    per = [sum(1 for c in man["candidates"] if c["sliders"]["variant"] == v) for v in range(4)]
    assert len(man["candidates"]) == 8 and per == [2, 2, 2, 2]
