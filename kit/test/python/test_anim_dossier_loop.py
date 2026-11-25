"""THE LOOP (owner 2026-10-18: 'i need you to start enfcorcig this type of proper loop so you dont mess up as much'):
a schema-2 dossier needs measured evidence; an owner rejection blocks the rebuild until the dossier answers it; a
strike clip that misses its own dossier checks is not built"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import proc_dossier as PD    # noqa: E402

PHASES = [{"name": "kamae", "real_s": [0, 0], "game_s": [0.0, 0.0]},
          {"name": "cut", "real_s": [0.2, 0.4], "game_s": [0.1, 0.3]}]


def test_schema2_needs_measured_evidence():
    d = {"schema": 2, "sources": [{"id": "a", "took": "text only"}], "phases": PHASES}
    assert any("measured" in m for m in PD.evidence_missing(d))
    d["sources"][0]["measured"] = "13 cycles: pause 0.29-0.71 s"
    assert PD.evidence_missing(d) == []
    d["phases"] = PHASES[:1] + [{"name": "cut", "real_s": None, "game_s": [0.1, 0.3]}]
    assert any("real_s" in m for m in PD.evidence_missing(d))
    assert PD.evidence_missing({"schema": 1, "sources": [], "phases": d["phases"]}) == []    # written before the rule


def test_rejection_blocks_until_answered(tmp_path, monkeypatch):
    v = tmp_path / "verdicts.json"
    v.write_text(json.dumps({"verdicts": {"Probe": [{"verdict": "bad", "date": "2026-10-18", "note": "the swing looks weird man"},
                                                    {"verdict": "loved", "date": "2026-10-18", "note": "great"}]}}))
    monkeypatch.setattr(PD, "VERDICTS", str(v))
    d = {"schema": 2}
    out = PD.rejection_missing(d, ["Probe"])
    assert len(out) == 1 and "the swing looks weird" in out[0]
    d["owner_rejections"] = [{"date": "2026-10-18", "quote": "the swing looks weird man", "changed": ""}]
    assert PD.rejection_missing(d, ["Probe"])                              # quoted but nothing changed: still blocked
    d["owner_rejections"][0]["changed"] = "the wind-up removed (footage: hands stay in front)"
    assert PD.rejection_missing(d, ["Probe"]) == []
    assert any("schema 2" in m for m in PD.rejection_missing({"schema": 1}, ["Probe"]))


def test_a_clip_failing_its_dossier_is_not_built(tmp_path):
    move = {"name": "GateProbe", "kind": "strike", "fps": 30, "rig": "R6", "arm_slide": 2.4,
            "sword": {"length": 3.6, "grip": 0.5},
            "keys": [{"t": 0.0, "grip": [0.4, 0.2, -1.4], "dir": [0.2, 0.7, -0.7], "ease": "InOut"},
                     {"t": 0.3, "grip": [-0.3, -0.4, -2.0], "dir": [-0.5, -0.3, -0.8], "ease": "Out"},
                     {"t": 0.6, "grip": [-0.4, -0.5, -1.6], "dir": [-0.3, -0.4, -0.87], "ease": "InOut"}]}
    p = tmp_path / "GateProbe.move.json"
    p.write_text(json.dumps(move))
    ok = {"build": {"builder": "strike"}, "checks": [{"id": "length", "measure": "clip_seconds", "range": [0.5, 1.0], "why": "t"}]}
    bad = {"build": {"builder": "strike"}, "checks": [{"id": "length", "measure": "clip_seconds", "range": [2.0, 3.0], "why": "t"}]}
    assert PD.build_failing(ok, str(p)) == []
    assert PD.build_failing(bad, str(p)) and "length" in PD.build_failing(bad, str(p))[0]


def test_a_frame_note_is_a_rejection_that_quotes_its_frame(tmp_path, monkeypatch):
    """kit anim note (AAA plan #8): the owner's words about ONE frame -> a verdict with the frame -> the gate quotes it"""
    import book as BK
    monkeypatch.chdir(tmp_path)
    (tmp_path / "assets" / "animations").mkdir(parents=True)
    BK.record("Probe", "bad", "the blade dips here", frame=18)
    v = json.load(open(tmp_path / "assets" / "animations" / "verdicts.json"))["verdicts"]["Probe"][0]
    assert v["frame"] == 18 and abs(v["t"] - 0.3) < 1e-9
    monkeypatch.setattr(PD, "VERDICTS", str(tmp_path / "assets" / "animations" / "verdicts.json"))
    out = PD.rejection_missing({"schema": 2}, ["Probe"])
    assert out and "at frame 18" in out[0]


def _r6_clip(leg_quat=(0.0, 0.0, 0.0, 1.0)):
    rest = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    joints = {p: {"frames": [rest, rest]} for p in ("Torso", "Head", "Right Arm", "Left Arm", "Left Leg")}
    joints["Right Leg"] = {"frames": [list(leg_quat) + [0.0, 0.0, 0.0]] * 2}
    return {"rig": "R6", "fps": 60, "times": [0.0, 1 / 60], "duration": 1 / 60, "joints": joints}


def test_body_pose_measures_read_the_legs_and_the_floor():
    """the movement set's measures (Sample Game, 2026-10-27): at rest every leg hangs straight at full length on the
    floor; the right leg turned 45 deg forward reads 45 deg of pitch and lifts its foot"""
    import math
    f = PD.body_pose_fns(_r6_clip())
    assert abs(f["leg_pitch_deg"]({"leg": "R"})) < 0.5 and abs(f["leg_slide_studs"]({"leg": "L"})) < 0.01
    assert abs(f["torso_lean_deg"]({})) < 0.5 and abs(f["lowest_part_studs"]({"stat": "min"})) < 0.01
    s = math.sin(math.radians(22.5))
    f = PD.body_pose_fns(_r6_clip((s, 0.0, 0.0, math.cos(math.radians(22.5)))))
    assert abs(f["leg_pitch_deg"]({"leg": "R", "stat": "at", "t": "end"}) - 45) < 1
    assert abs(f["leg_pitch_deg"]({"leg": "L"})) < 0.5
    assert f["lowest_part_studs"]({"stat": "min"}) < 0.01          # the left foot still on the floor
