"""kit/anim/clip_beats.py and the procedural builders (the owner's V3 list, anim stage A.2; card j6x7): a builder writes
the beats it built from into the clip - {phase: [t0, t1]} - so a candidate's sheet poses its own moments instead of
guessing them from where the motion nearly stops. Before: proc_blade / proc_kick / proc_strike / proc_react clips
carried their Hit and no beats."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
os.chdir(ROOT)
import clip_beats as CB      # noqa: E402


def spans_ok(c):
    end = float(c["times"][-1])
    b = c.get("beats") or {}
    assert b, "the builder wrote no beats"
    for name, (t0, t1) in b.items():
        assert 0.0 <= t0 <= t1 <= end + 1e-6, (name, t0, t1, end)
    starts = [v[0] for v in b.values()]
    assert starts == sorted(starts)                       # in the clip's own order
    return b


def test_keys_become_spans_one_per_run_of_a_name():
    b = CB.from_keys([(0.3, "cut"), (0.0, "guard"), (0.1, "wind"), (0.2, "wind"), (0.5, None), (0.6, "guard")], 0.9)
    assert b == {"guard": [0.0, 0.1], "wind": [0.1, 0.3], "cut": [0.3, 0.6], "guard_2": [0.6, 0.9]}
    assert CB.from_keys([(0.1, None), (0.2, "")], 1.0) == {}
    assert CB.from_keys([(1.2, "hold")], 1.0) == {"hold": [1.2, 1.2]}          # (a key past the end: an instant)


def test_a_blade_candidate_carries_its_gestures_beats_and_its_sheet_poses_them():
    if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "gestures", "blade_lunge_cut.json")):
        import pytest; pytest.skip("the author's assets/animations/gestures/blade_lunge_cut.json is not shipped with the kit")
    import proc_blade as PB
    import thumbs as T
    d = {"name": "greatsword", "build": {"builder": "fp_weapon", "gestures": {"TestCut*": "blade_lunge_cut"},
                                        "sword": {"length": 5.03, "grip": 1.23}}}
    c, _ = PB.build(d, {}, "TestCut_r0_beats")
    b = spans_ok(c)
    g = PB.gesture_for(d, "TestCut_r0_beats")
    assert set(b) <= {bb["name"] for bb in g["beats"]} | {f"{bb['name']}_{k}" for bb in g["beats"] for k in (2, 3, 4)}
    assert any(bb.get("phase") == "strike" and bb["name"] in b for bb in g["beats"])
    # the sheet's moments (no move file: what the clip marks) are now its beats' borders, not every 0.1 s
    ts = T.key_times(c)
    borders = {round(v, 3) for span in b.values() for v in span}
    assert sum(1 for t in ts if round(t, 3) in borders) >= 3


def test_a_kick_candidate_carries_its_keys_as_beats():
    if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "dossiers", "roundhouse_kick.json")):
        import pytest; pytest.skip("the author's assets/animations/dossiers/roundhouse_kick.json is not shipped with the kit")
    import proc_dossier as DS
    import proc_kick as PK
    d = DS.require("roundhouse_kick")
    c, b_used = PK.build(d, name="t")
    b = spans_ok(c)
    assert "contact" in b and set(b) <= {k["name"] for k in b_used["keys"]} | {f"{k['name']}_2" for k in b_used["keys"]}


def test_a_reaction_carries_the_blow_and_the_settle():
    if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "dossiers", "head_hook_reaction.json")):
        import pytest; pytest.skip("the author's assets/animations/dossiers/head_hook_reaction.json is not shipped with the kit")
    import proc_dossier as DS
    import proc_react as PR
    import pytest
    d = DS.require("head_hook_reaction")
    if not os.path.isfile(os.path.join("build", "animations", f"{d['build']['base']}.clip.json")):
        pytest.skip(f"its base idle is not built here (lune run kit anim {d['build']['base']})")
    c, _ = PR.build(d)
    b = spans_ok(c)
    hit = next(e["t"] for e in c["events"] if e["name"] == "Hit")
    assert b["hit"][0] == round(hit, 6) and b["recover"][1] == round(float(c["times"][-1]), 6)


def test_a_strike_candidate_names_its_keys_by_the_dossiers_phases(tmp_path, monkeypatch):
    import proc_strike as PS
    move = {"name": "StrikeProbe", "fps": 60, "weapon": "sword",
            "keys": [{"t": 0.0, "torso": {"yaw": 0}, "arms": "guard"}, {"t": 0.15, "torso": {"yaw": -30}, "arms": "cocked"},
                     {"t": 0.3, "torso": {"yaw": 40}, "arms": "extended"}, {"t": 0.6, "torso": {"yaw": 0}, "arms": "guard"}],
            "events": [{"name": "Hit", "t": 0.3}]}
    monkeypatch.chdir(tmp_path)
    os.makedirs(os.path.join("assets", "animations"))
    json.dump(move, open(os.path.join("assets", "animations", "StrikeProbe.move.json"), "w"))
    d = {"name": "probe", "category": "combat", "build": {"builder": "fp_weapon"},
         "phases": [{"name": "guard", "game_s": [0.0, 0.0]}, {"name": "wind", "game_s": [0.0, 0.15]},
                    {"name": "cut", "game_s": [0.15, 0.3]}, {"name": "recovery", "game_s": [0.3, 0.6]}]}
    c, _ = PS.build(d, {"time": 0, "weight": 0, "space": 0, "flow": 0}, "StrikeProbe_r0_c0")
    b = spans_ok(c)
    assert set(b) <= {"guard", "wind", "cut", "recovery"} and "cut" in b
