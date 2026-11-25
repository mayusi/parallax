"""kit/anim/style_check.py - a game's animation style guide (AAA gaps v2 A6 / C1 / C2): the opener on the guard, every
cut linked to the last, startups within their tier's budget - each break caught on synthetic clips"""
import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import style_check as SC  # noqa: E402

PARTS = ["Torso", "Head", "Left Arm", "Right Arm", "Left Leg", "Right Leg"]


def q_x(deg):
    h = math.radians(deg) / 2
    return [math.sin(h), 0.0, 0.0, math.cos(h)]


def clip(name, start_deg, end_deg, hit, tier="medium"):
    frames = lambda d: q_x(d) + [0.0, 0.0, 0.0]  # noqa: E731
    return {"name": name, "rig": "R6", "times": [0.0, 0.5], "events": [{"name": "Hit", "t": hit}], "feel": {"tier": tier},
            "joints": {p: {"frames": [frames(start_deg if p == "Right Arm" else 0), frames(end_deg if p == "Right Arm" else 0)]}
                       for p in PARTS}}


def run(clips, **style_over):
    style = {"guard": {"clip": "A", "frame": 0, "tol_deg": 10}, "link_tol_deg": 6,
             "startup_s": {"light": 0.3, "medium": 0.5, "heavy": 1.1}, "sets": {"S": [c["name"] for c in clips]}}
    style.update(style_over)
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "animations"))
        for c in clips:
            json.dump(c, open(os.path.join(d, "animations", f"{c['name']}.clip.json"), "w"))
        return SC.check(style, "S", d)


def test_a_linked_set_passes():
    rows, problems = run([clip("A", 0, 40, 0.3), clip("B", 40, 80, 0.4), clip("C", 80, 10, 0.9, "heavy")])
    assert problems == [] and rows[1]["link_deg"] < 0.01 and rows[2]["return_deg"] > 9


def test_breaks_are_caught():
    _, p1 = run([clip("A", 0, 40, 0.3), clip("B", 60, 80, 0.4)])           # B starts 20 deg off A's end
    assert any("does not start where A ended" in p for p in p1)
    _, p2 = run([clip("A", 0, 40, 0.3), clip("B", 40, 80, 0.8)])           # a medium hitting at 0.8 s
    assert any("over the medium budget" in p for p in p2)
    _, p3 = run([clip("G", 0, 0, 0.1), clip("A", 30, 40, 0.3)], guard={"clip": "G", "frame": 0, "tol_deg": 10},
                sets={"S": ["A"]})                                          # the opener 30 deg off the guard
    assert any("off the guard pose" in p for p in p3)


def test_cancel_link_reported_from_the_game_moves(tmp_path, monkeypatch):
    """C2: with the game's move files present, the seam from the earliest cancel pose is measured"""
    monkeypatch.chdir(tmp_path)
    mdir = tmp_path / "games" / "SampleDojo" / "assets" / "moves"
    mdir.mkdir(parents=True)
    (mdir / "M1.json").write_text(json.dumps({"anim": "A", "cancel": {"from": 15, "to": 29}, "frames": "from_anim"}))
    clips = [clip("A", 0, 40, 0.3), clip("B", 40, 80, 0.4)]
    style = {"guard": {"clip": "A", "frame": 0, "tol_deg": 10}, "link_tol_deg": 6, "cancel_tol_deg": 60,
             "startup_s": {"medium": 0.5}, "sets": {"S": ["A", "B"]}}
    os.makedirs(tmp_path / "b" / "animations")
    for c in clips:
        json.dump(c, open(tmp_path / "b" / "animations" / f"{c['name']}.clip.json", "w"))
    rows, problems = SC.check(style, "S", str(tmp_path / "b"))
    assert "cancel_link_deg" in rows[1] and rows[1]["cancel_link_deg"] > 0 and problems == []
