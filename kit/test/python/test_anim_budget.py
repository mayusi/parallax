"""kit/anim/budget.py - what a clip costs (the owner's older list, AN-40): export bytes, the keys a bounded-error
curve would keep (the kit's own rule, src/kit/AnimCurve, run through lune), what the engine's 30-a-second curve
playback would lose, and that a marker's frame does not move. Made-up clips only."""
import json
import math
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import budget as B               # noqa: E402

lune = pytest.mark.skipif(shutil.which("lune") is None, reason="lune is not on this machine")


def clip(fps=60, seconds=1.0, swing=90.0, wobble=0.0, still=("Left Leg",)):
    """an R6 clip: the right arm swings `swing` degrees about X at a steady rate (a straight line: every key between
    the ends is one a curve can drop), plus a `wobble` degrees zig-zag every frame (keys a curve must keep)"""
    n = int(round(fps * seconds)) + 1
    times = [round(i / fps, 6) for i in range(n)]
    joints = {}
    for part in ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"):
        frames = []
        for i in range(n):
            deg = 0.0
            if part == "Right Arm":
                deg = swing * i / (n - 1) + (wobble if i % 2 else 0.0)
            a = math.radians(deg) / 2
            frames.append([math.sin(a), 0.0, 0.0, math.cos(a), 0.0, 0.0, 0.0])
        joints[part] = {"frames": frames}
    return {"schema": 1, "name": "Made", "rig": "R6", "fps": fps, "loop": False, "times": times,
            "events": [{"name": "Hit", "t": times[n // 2]}], "joints": joints}


def write(tmp_path, c, name="Made", rbxm=None):
    p = tmp_path / f"{name}.clip.json"
    p.write_text(json.dumps(c), encoding="utf-8")
    if rbxm is not None:
        (tmp_path / f"{name}.rbxm").write_bytes(b"x" * rbxm)
    return str(p)


@lune
def test_a_steady_swing_keeps_its_two_ends_and_a_curve_is_free_of_loss(tmp_path):
    p = write(tmp_path, clip(), rbxm=20_000)
    r = B.row_for(p, B.curves([p])[p])
    assert r["tracks"] == 6 and r["moving"] == 1 and r["keys"] == 6 * 2 * 61
    assert r["kept"] == 6 * 2 * 2                              # every track: its first and its last key
    assert r["lost_deg"] < 0.01 and r["curve_is_free"] is True
    assert r["bytes"] == 20_000 and r["bytes_per_s"] == 20_000 and r["seconds"] == 1.0
    assert "the saving is free" in B.words(r)


@lune
def test_a_sixty_a_second_wobble_is_what_the_engine_would_lose(tmp_path):
    # every odd frame 4 degrees off the line: a 30-a-second playback drops exactly those
    p = write(tmp_path, clip(wobble=4.0))
    r = B.row_for(p, B.curves([p])[p])
    assert 3.9 < r["lost_deg"] < 4.1 and r["curve_is_free"] is False
    assert r["kept"] > 6 * 2 * 2 + 50                          # the wobbling track keeps its keys
    assert r["bytes"] is None and "no export beside it" in B.words(r) and "stays a KeyframeSequence" in B.words(r)
    # the same wobble on a 30-a-second clip: every key is on the engine's grid, nothing is lost
    q = write(tmp_path, clip(fps=30, wobble=4.0), name="Thirty")
    assert B.row_for(q, B.curves([q])[q])["lost_deg"] < 0.01


@lune
def test_a_markers_frame_is_read_as_the_engine_would_play_it(tmp_path):
    # (the one review: the first cut compared a dropped key with the curve's own line - true by the rule, always)
    c = clip(wobble=0.2)                                      # under the 0.25 degrees: the curve may drop those keys
    c["events"] = [{"name": "Hit", "t": c["times"][30]}]      # an EVEN frame of a 60-a-second clip: on the engine's grid
    p = write(tmp_path, c)
    r = B.row_for(p, B.curves([p])[p])
    assert r["kept"] < r["keys"] and r["event_deg"] <= B.ROT_TOL + 1e-6
    # a Hit on an ODD frame with a 4 degree wobble: the engine's 30-a-second playback does not play that key
    c = clip(wobble=4.0)
    c["events"] = [{"name": "Hit", "t": c["times"][31]}]
    q = write(tmp_path, c, name="Odd")
    r = B.row_for(q, B.curves([q])[q])
    assert 3.5 < r["event_deg"] < 4.5 and r["curve_is_free"] is False
    assert "degrees at a marker's frame" in B.words(r)


@lune
def test_the_weapons_joint_is_counted_a_broken_frame_is_named_and_a_held_pose_does_not_move(tmp_path):
    c = clip()
    c["grip"] = [list(f) for f in c["joints"]["Right Arm"]["frames"]]     # the Handle joint: written and thinned too
    p = write(tmp_path, c)
    r = B.row_for(p, B.curves([p])[p])
    assert r["tracks"] == 7 and r["keys"] == 7 * 2 * 61 and r["moving"] == 2
    # a joint that turns 170 degrees in one frame: a pop, its "loss" counted apart from the curve's price
    c = clip()
    a = math.radians(170) / 2
    c["joints"]["Left Arm"]["frames"][31] = [math.sin(a), 0.0, 0.0, math.cos(a), 0.0, 0.0, 0.0]
    q = write(tmp_path, c, name="Pop")
    r = B.row_for(q, B.curves([q])[q])
    assert r["pops"] == 2 and r["lost_deg"] < 0.01 and r["pop_lost_deg"] > 80
    assert "faster than frames can carry" in B.named([r])[0]["Made"]
    # float noise on a held pose is no motion
    c = clip(swing=0.0)
    a = math.radians(0.004) / 2
    for i in range(0, 61, 2):
        c["joints"]["Head"]["frames"][i] = [math.sin(a), 0.0, 0.0, math.cos(a), 0.0, 0.0, 0.0]
    h = write(tmp_path, c, name="Held")
    assert B.row_for(h, B.curves([h])[h])["moving"] == 0


def test_a_one_frame_pose_has_no_rate_and_an_old_export_is_said(tmp_path):
    c = clip()
    c["times"] = c["times"][:1]
    for j in c["joints"].values():
        j["frames"] = j["frames"][:1]
    p = write(tmp_path, c, name="Pose", rbxm=900)
    curve = {"frames": 1, "tracks": 6, "moving": 0, "keys": 12, "kept": 12, "lostDeg": 0, "lostStuds": 0, "eventDeg": 0, "eventStuds": 0}
    r = B.row_for(p, curve)
    assert r["bytes"] == 900 and r["bytes_per_s"] is None
    q = write(tmp_path, clip(), name="Old", rbxm=5000)
    old = os.path.getmtime(q) - 3600
    os.utime(str(tmp_path / "Old.rbxm"), (old, old))
    curve = {"frames": 61, "tracks": 6, "moving": 1, "keys": 732, "kept": 24, "lostDeg": 0, "lostStuds": 0, "eventDeg": 0, "eventStuds": 0}
    r = B.row_for(q, curve)
    assert r["export_stale"] is True and "older than the clip" in B.named([r])[0]["Made"]


def test_without_lune_it_says_so(tmp_path, capsys, monkeypatch):
    p = write(tmp_path, clip())
    monkeypatch.setattr(B.shutil, "which", lambda name: None)
    assert B.main([p]) == 1
    out = json.loads(capsys.readouterr().out)
    assert "lune is not on this machine" in out["summary"] and "install lune" in out["next_action"]


@lune
def test_a_file_that_is_no_clip_is_left_out_and_the_table_reads_a_folder(tmp_path, capsys):
    write(tmp_path, clip(), name="A", rbxm=10_000)
    write(tmp_path, clip(seconds=0.5), name="B", rbxm=200_000)
    (tmp_path / "C.clip.json").write_text("{}", encoding="utf-8")
    (tmp_path / "A.preview.clip.json").write_text(json.dumps(clip()), encoding="utf-8")      # a working file: not read
    assert B.main(["table", str(tmp_path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [r["name"] for r in out["rows"]] == ["Made", "Made"] and len(out["rows"]) == 2
    assert out["rows"][0]["bytes"] == 200_000                  # the costliest first
    assert len(out["named"]) == 1 and "200 KB exported" in list(out["named"].values())[0]
    assert B.main([str(tmp_path / "C.clip.json")]) == 1
    capsys.readouterr()
    assert B.main(["table", str(tmp_path / "nowhere")]) == 1


def test_the_bars_name_a_clip_and_fail_none():
    def row(name, size, per_s, ev=0.0):
        return {"name": name, "bytes": size, "bytes_per_s": per_s, "event_deg": ev, "event_studs": 0.0}
    rows = [row("a", 10_000, 10_000), row("b", 12_000, 11_000), row("c", 9_000, 12_000), row("big", 160_000, 13_000),
            row("dense", 40_000, 50_000), row("unsized", None, None), dict(row("popped", 8_000, 9_000), pops=3),
            dict(row("old", 8_000, 9_500), export_stale=True)]
    named, mid = B.named(rows)
    assert mid == 11_000                                      # (the middle of seven: the true median)
    assert set(named) == {"big", "dense", "popped", "old"}
    assert "160 KB exported" in named["big"] and "times the middle clip" in named["dense"]
    assert "3 frame(s)" in named["popped"] and "older than the clip" in named["old"]
    assert B.named([row("only", None, None)]) == ({}, None)


def test_the_tolerances_said_here_are_the_curve_rules_own():
    src = open(os.path.join(ROOT, "src", "kit", "AnimCurve.luau"), encoding="utf-8").read()
    assert f"AnimCurve.ROT_TOL = {B.ROT_TOL:g}" in src and f"AnimCurve.POS_TOL = {B.POS_TOL:g}" in src
    lua = open(os.path.join(ROOT, "kit", "anim", "budget_curve.luau"), encoding="utf-8").read()
    assert "AnimCurve.thin(times, rots, AnimCurve.ROT_TOL, slerp, angle)" in lua and "AnimCurve.lost(times, rots, slerp, angle)" in lua
