"""kit/anim/fast_turns.py - a joint that turns faster than the frames can carry (over 90 degrees between two frames):
found by the clip budget; the pop gate does not see two big steps side by side. The owner's loved cuts (generated in
memory, read only) stay far under it."""
import copy
import glob
import json
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
sys.path.insert(0, HERE)
import clip as C                 # noqa: E402
import fast_turns as FT          # noqa: E402
import metrics as MT             # noqa: E402
import test_anim_collide as T    # noqa: E402


def quat(deg):
    a = math.radians(deg) / 2
    return [math.sin(a), 0.0, 0.0, math.cos(a)]


def clip(steps, fps=60, part="Right Arm"):
    """an R6 clip whose one joint turns by `steps` degrees, frame after frame"""
    total, frames = 0.0, [quat(0) + [0.0, 0.0, 0.0]]
    for d in steps:
        total += d
        frames.append(quat(total) + [0.0, 0.0, 0.0])
    n = len(frames)
    joints = {p: {"frames": [quat(0) + [0.0, 0.0, 0.0] for _ in range(n)]} for p in ("Torso", "Head", "Left Arm", "Right Leg", "Left Leg")}
    joints[part] = {"frames": frames}
    return {"schema": 1, "name": "Made", "rig": "R6", "fps": fps, "loop": False, "times": [round(i / fps, 6) for i in range(n)],
            "events": [], "joints": joints}


def test_the_loved_cuts_never_turn_a_joint_a_third_of_the_limit_and_the_rejected_fixtures_neither():
    for kind in ("loved", "rejected"):
        for p in sorted(glob.glob(os.path.join(ROOT, "kit", "selftest", "anim", "faults", kind, "*.move.json"))):
            r = FT.read(T.made(kind, os.path.basename(p)[:-len(".move.json")]))
            assert not r["over"] and r["worst"]["deg"] < 40, (kind, p, r["worst"])


def test_a_swing_of_two_big_steps_is_caught_where_the_pop_gate_sees_nothing():
    c = clip([5, 10, 85, 176, 20, 5, 2])
    r = FT.read(c)
    assert [o["frame"] for o in r["over"]] == [4] and r["over"][0]["joint"] == "Right Arm" and 170 < r["over"][0]["deg"] <= 180
    m = C.metrics(c, C.load_rig("r6"))
    assert not any("pop" in p for p in m["problems"])        # (the pop gate wants calm frames either side)
    g, bad = FT.gate(c, listed=False)
    assert bad and "Right Arm turns" in bad and "frames 3 and 4" in bad and g["worst"]["frame"] == 4
    # just under the limit passes; a whole clip of quick frames under it passes
    assert FT.gate(clip([30, 60, 89, 60, 30]), listed=False)[1] is None
    # the weapon's own joint counts
    w = clip([5, 5, 5])
    w["grip"] = [quat(0) + [0, 0, 0], quat(120) + [0, 0, 0], quat(125) + [0, 0, 0], quat(130) + [0, 0, 0]]
    assert "the weapon turns" in FT.gate(w, listed=False)[1]


def test_a_declared_step_is_not_judged_and_things_that_are_no_clip_are_not_read():
    c = clip([0, 0, 0, 120, 0, 0, 0, 0])
    assert FT.gate(c, listed=False)[1]
    c["stepped"] = [[0.0, 6 / 60, 4]]                         # holds of four frames from 0 to 0.1 s: frame 4 jumps on purpose
    assert 4 in C.step_frames(c) and FT.gate(c, listed=False)[1] is None
    assert FT.gate("x") == (None, None) and FT.gate({"prop": True, "joints": {}}) == (None, None)
    g, bad = FT.gate({"name": "Odd", "joints": {"Head": {"frames": "none"}}})
    assert bad is None and g["worst"] is None
    g, bad = FT.gate({"name": "Odd", "joints": 3})
    assert bad is None and "error" in g
    nan = clip([5, 5])
    nan["joints"]["Head"]["frames"][1] = [float("nan")] * 4 + [0, 0, 0]
    assert FT.gate(nan, listed=False)[1] is None


def test_the_build_fails_it_and_a_clip_made_before_the_rule_is_said(tmp_path, capsys):
    c = clip([5, 10, 85, 176, 20, 5, 2])
    anims = tmp_path / "anims"
    c["source"] = {"file": str(anims / "Made.move.json")}
    p = tmp_path / "Made.clip.json"
    p.write_text(json.dumps(c), encoding="utf-8")
    assert MT.main([str(p)]) == 1
    capsys.readouterr()
    m = json.loads((tmp_path / "Made.metrics.json").read_text(encoding="utf-8"))
    assert any("turns 17" in x and "between frames 3 and 4" in x for x in m["problems"]) and m["fast_turns"]["over"]
    out = str(anims / "blocks" / FT.BEFORE)
    assert FT.freeze(str(tmp_path), out, today="2026-11-15") == ["Made"]
    g, bad = FT.gate(c)
    assert bad is None and g["made_before_the_rule"] is True
    with pytest.raises(ValueError):
        FT.freeze(str(tmp_path), out)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("{")
    assert "could not be read" in FT.gate(c)[1]


def test_the_command_line_and_the_projects_own_frozen_list(tmp_path, capsys):
    if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "blocks", FT.BEFORE)):
        pytest.skip("the author's assets/animations/blocks/_fast_turn_before.json is not shipped with the kit")
    (tmp_path / "Fast.clip.json").write_text(json.dumps(clip([5, 100, 5])), encoding="utf-8")
    (tmp_path / "Calm.clip.json").write_text(json.dumps(clip([5, 20, 5])), encoding="utf-8")
    (tmp_path / "Fast.preview.clip.json").write_text(json.dumps(clip([5, 100, 5])), encoding="utf-8")
    assert FT.main([str(tmp_path / "Fast.clip.json")]) == 1 and FT.main([str(tmp_path / "Calm.clip.json")]) == 0
    capsys.readouterr()
    assert FT.main(["table", str(tmp_path)]) == 0
    rows = json.loads(capsys.readouterr().out)["rows"]
    assert len(rows) == 1 and rows[0]["deg"] == 100.0
    assert FT.main([str(tmp_path / "none.json")]) == 1
    capsys.readouterr()
    kept = os.path.join(ROOT, "assets", "animations", "blocks", FT.BEFORE)
    with open(kept, encoding="utf-8") as fh:
        d = json.load(fh)
    assert d["frozen"] == "2026-11-15" and len(d["clips"]) >= 40 and "DTCutCleave" in d["clips"]
    assert "Katana1Kesa" not in d["clips"]


def test_a_project_that_never_froze_a_list_is_told_how_and_one_that_did_is_not(tmp_path):
    if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "blocks", FT.BEFORE)):
        pytest.skip("the author's assets/animations/blocks/_fast_turn_before.json is not shipped with the kit")
    # (the kit installed into a game that already has clips: an old clip must not fail as if it were new)
    import collide as K
    import contact as CT
    c = clip([5, 10, 85, 176, 20, 5, 2])
    anims = tmp_path / "anims"
    c["source"] = {"file": str(anims / "Made.move.json")}
    bad = FT.gate(c)[1]
    assert "this project has no list of clips made before this rule" in bad and "fast_turns.py freeze" in bad
    assert "a NEW clip among them must be taken out of it by hand" in bad    # (the freeze takes every clip failing today)
    # (a source with no folder falls back to the project's own animations folder: this repo has that list, so no hint)
    assert FT._no_list("", True, "fast_turns") == ""
    assert str(anims).replace(os.sep, "/") in bad
    assert "has no list" not in FT.gate(c, listed=False)[1]          # (the freeze's own reading says nothing of lists)
    os.makedirs(anims / "blocks")
    (anims / "blocks" / FT.BEFORE).write_text(json.dumps({"clips": ["Other"]}), encoding="utf-8")
    assert "has no list" not in FT.gate(c)[1]                        # a project WITH a list: a new clip simply fails
    for mod, tool in ((K, "collide"), (CT, "contact")):
        assert tool + ".py freeze" in mod._no_list(str(tmp_path / "none"), True, tool)
        assert mod._no_list(str(tmp_path / "none"), False, tool) == ""
