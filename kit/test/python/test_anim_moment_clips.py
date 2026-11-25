"""kit/anim/moment_clips.py - fixture clips for the moments between the movement loops (AN-28's clips: a start, a
stop, a pivot, a turn on the spot each way), made by rule from an idle and a walk loop. They are fixtures for the
wiring: these tests hold their SHAPE (where each begins and ends, that nothing jumps), never how they look."""
import json
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C                 # noqa: E402
import moment_clips as M         # noqa: E402

PARTS = ("Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg")


def quat(axis, deg):
    a = math.radians(deg) / 2
    return [axis[0] * math.sin(a), axis[1] * math.sin(a), axis[2] * math.sin(a), math.cos(a)]


def idle():
    return {"schema": 1, "name": "Idle", "rig": "R6", "fps": 30, "loop": True, "times": [0.0, 1.0],
            "joints": {p: {"frames": [quat((1, 0, 0), 2.0 if p == "Head" else 0.0) + [0.0, 0.0, 0.0]] * 2} for p in PARTS}}


def walk(n=20, cycle=0.6):
    """a loop: the legs and arms swing 30 degrees either way, out of step; its last frame is its first"""
    joints = {}
    for p in PARTS:
        frames = []
        for i in range(n + 1):
            ph = 2 * math.pi * i / n
            deg = {"Right Leg": 30, "Left Leg": -30, "Right Arm": -25, "Left Arm": 25}.get(p, 0) * math.sin(ph)
            bob = 0.1 * math.cos(2 * ph) if p == "Torso" else 0.0
            frames.append(quat((1, 0, 0), deg) + [0.0, bob, 0.0])
        joints[p] = {"frames": frames}
    return {"schema": 1, "name": "Walk", "rig": "R6", "fps": round(n / cycle), "loop": True,
            "times": [round(cycle * i / n, 6) for i in range(n + 1)], "joints": joints}


@pytest.fixture(scope="module")
def clips():
    return M.make(idle(), walk())


def same(a, b, deg=0.05):
    return C.quat_angle(a[:4], b[:4]) < deg and np.allclose(a[4:7], b[4:7], atol=1e-3)


def test_five_clips_of_the_said_lengths_that_say_what_they_are(clips):
    assert tuple(clips) == M.MOMENTS
    for moment, seconds in (("start", M.START), ("stop", M.STOP), ("pivot", M.PIVOT), ("turnLeft", M.TURN), ("turnRight", M.TURN)):
        c = clips[moment]
        assert c["rig"] == "R6" and c["loop"] is False and c["moment"] == moment and c["match"] == {"pose": True}
        assert c["priority"] == "Movement" and abs(c["duration"] - seconds) < 1e-6 and c["fps"] == 60
        assert set(c["joints"]) == set(PARTS) and all(len(j["frames"]) == len(c["times"]) for j in c["joints"].values())


def test_each_begins_and_ends_where_the_loop_beside_it_is(clips):
    i, w = idle(), walk()
    for p in PARTS:
        rest, first = i["joints"][p]["frames"][0], w["joints"][p]["frames"][0]
        # a start leaves the idle pose and ends ON the walk, at the phase it says
        s = clips["start"]["joints"][p]["frames"]
        assert same(s[0], rest) and same(s[-1], M._at(w, p, clips["start"]["leads_into"]["phase"]))
        # a stop leaves the walk's first frame and ends in the idle pose
        e = clips["stop"]["joints"][p]["frames"]
        assert same(e[0], first) and same(e[-1], rest)
        # a pivot: the walk, through the idle pose, onto the walk again
        v = clips["pivot"]["joints"][p]["frames"]
        assert same(v[0], first) and same(v[len(v) // 2], rest) and same(v[-1], M._at(w, p, clips["pivot"]["leads_into"]["phase"]))
        # a turn on the spot begins and ends in the idle pose
        for side in ("turnLeft", "turnRight"):
            t = clips[side]["joints"][p]["frames"]
            assert same(t[0], rest) and same(t[-1], rest)


def test_nothing_jumps_and_something_moves(clips):
    for moment, c in clips.items():
        deg, studs = M.step(c)
        assert 0.3 < deg < 12.0, (moment, deg)                # (a 30 degree swing over a 0.6 s cycle: about 5 a frame at most)
        assert studs < 0.05, (moment, studs)


def test_the_two_turns_lean_opposite_ways_and_lead_with_opposite_feet(clips):
    mid = len(clips["turnLeft"]["times"]) // 2
    left, right = clips["turnLeft"]["joints"], clips["turnRight"]["joints"]
    lz, rz = left["Torso"]["frames"][mid][2], right["Torso"]["frames"][mid][2]
    assert lz > 0.02 and rz < -0.02 and abs(lz + rz) < 1e-6           # a lean about Z, opposite
    ll, rl = left["Right Leg"]["frames"][mid // 2][0], right["Right Leg"]["frames"][mid // 2][0]
    assert ll * rl < 0                                               # the right leg goes the other way first
    # a turn is small: a third of the walk's swing at its most
    assert max(abs(f[0]) for f in left["Right Leg"]["frames"]) < 0.4 * math.sin(math.radians(15))


def test_what_it_refuses():
    r15 = idle()
    r15["rig"] = "R15"
    still = walk()
    still["loop"] = False
    other = idle()
    del other["joints"]["Head"]
    short = walk()
    short["times"] = short["times"][:1]
    for a, b in ((r15, walk()), (idle(), still), (other, walk()), (idle(), short), ([], walk())):
        with pytest.raises(ValueError):
            M.make(a, b)


def test_the_command_writes_them_and_the_kept_fixtures_are_its_own(tmp_path, capsys):
    a, b = tmp_path / "Idle.r6.clip.json", tmp_path / "Walk.r6.clip.json"
    a.write_text(json.dumps(idle()), encoding="utf-8")
    b.write_text(json.dumps(walk()), encoding="utf-8")
    assert M.main([str(a), str(b), "--out", str(tmp_path / "out")]) == 0
    assert "nobody has looked at them" in json.loads(capsys.readouterr().out)["next_action"]
    assert sorted(os.listdir(tmp_path / "out")) == ["MomentPivot.clip.json", "MomentStart.clip.json", "MomentStop.clip.json",
                                                    "MomentTurnLeft.clip.json", "MomentTurnRight.clip.json"]
    assert M.main([str(a), str(tmp_path / "none.json"), "--out", str(tmp_path / "x")]) == 1
    capsys.readouterr()
    # the kit's kept fixtures: five R6 clips that say they are moments, made by this tool
    kept = os.path.join(ROOT, "kit", "selftest", "anim", "moments")
    for name, moment in (("MomentStart", "start"), ("MomentStop", "stop"), ("MomentPivot", "pivot"),
                         ("MomentTurnLeft", "turnLeft"), ("MomentTurnRight", "turnRight")):
        with open(os.path.join(kept, name + ".clip.json"), encoding="utf-8") as fh:
            c = json.load(fh)
        assert c["rig"] == "R6" and c["moment"] == moment and c["source"]["tool"] == "kit/anim/moment_clips.py"
        deg, studs = M.step(c)
        assert deg < 15.0 and studs < 0.2, (name, deg, studs)
        # what the build's own motion checks say of them, pinned so it is not forgotten: the stop and the turns are
        # clean; the start and the pivot slide a planted foot a little over the bar (0.10 and 0.12 studs a frame)
        problems = C.metrics(c, C.load_rig("r6"))["problems"]
        if moment in ("start", "pivot"):
            assert all("foot slide" in p for p in problems) and len(problems) <= 1, (name, problems)
        else:
            assert problems == [], (name, problems)
