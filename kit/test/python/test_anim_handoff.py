"""kit/anim/handoff.py - an object handed from one parent to another (Child Of phases) and tossed between them
(LIMITATIONS_FIXES_V3 Stage D item 2). The fixtures are made here: an R6 reload (a magazine in the gun's receiver,
taken by the left hand, carried down and back, re-latched) and a weapon tossed from the right hand to the left.
None is a judged clip."""
import copy
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C        # noqa: E402
import grip as GR       # noqa: E402
import handoff as H     # noqa: E402

FPS = 60
RIG = C.load_rig("r6", ROOT)


def quat(axis, deg):
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    h = math.radians(deg) / 2
    return [*(a * math.sin(h)), math.cos(h)]


def ease(a, b, u):
    u = u * u * (3 - 2 * u)
    return a + (b - a) * u


def reload_clip(back_deg=70.0):
    """0.85 s: the right arm holds the gun ahead; the left arm lifts to the magwell (0.15), drops to the hip (0.35)
    and comes back up (0.55) - to `back_deg` (70 = the same pose it took the magazine in)"""
    n = int(0.85 * FPS) + 1
    times = [i / FPS for i in range(n)]
    right, left = [], []
    for t in times:
        right.append(quat((1, 0, 0), 90) + [0, 0, 0])
        if t <= 0.15:
            d = ease(0, 70, t / 0.15)
        elif t <= 0.35:
            d = ease(70, 20, (t - 0.15) / 0.2)
        elif t <= 0.55:
            d = ease(20, back_deg, (t - 0.35) / 0.2)
        else:
            d = back_deg
        left.append(quat((1, 0, 0), d) + [0, 0, 0])
    return {"name": "FixReload", "rig": "R6", "fps": FPS, "times": times, "events": [],
            "joints": {"Right Arm": {"frames": right}, "Left Arm": {"frames": left}},
            "grip": [[0, 0, 0, 1, 0, 0, 0]] * n}


def frame_of(clip, t):
    return min(range(len(clip["times"])), key=lambda i: abs(clip["times"][i] - t))


def magwell_socket(clip):
    """the magazine's socket in the gun's space: where the left hand is when it takes it (0.15)"""
    P = H._parents(clip, RIG)[frame_of(clip, 0.15)]
    hand = P["Left Arm"] @ np.array([*H.HAND, 1.0])
    local = np.linalg.inv(P["Handle"]) @ hand
    return {"pos": [float(v) for v in local[:3]]}


def plan_for(clip, sock=None):
    sock = sock or magwell_socket(clip)
    return {"object": "Mag", "carrier": "Torso", "phases": [
        {"t": 0.0, "parent": "Handle", "at": sock},
        {"t": 0.15, "parent": "Left Arm"},
        {"t": 0.55, "parent": "Handle", "at": sock}]}


def test_the_magazine_rides_the_receiver_then_the_hand_then_is_latched_back():
    clip = reload_clip()
    r = H.solve(clip, plan_for(clip))
    assert r["faults"] == [] and r["reaches"][0]["studs"] < 1e-6 and r["seams"][0]["studs"] < 1e-6
    W, P = r["world"], H._parents(clip, RIG)
    i15, i35 = frame_of(clip, 0.15), frame_of(clip, 0.35)
    # carried rigidly: the same place in the left arm's space all the way from 0.15 to 0.55
    rel = [np.linalg.inv(P[i]["Left Arm"]) @ W[i] for i in range(i15, frame_of(clip, 0.55))]
    assert max(float(np.abs(m - rel[0]).max()) for m in rel) < 1e-9
    # it went down with the hand (0.35: the arm at 20 degrees, not 70) - not left floating at the gun
    assert W[i35][1, 3] < W[i15][1, 3] - 0.3
    # in the receiver it does not move with the gun's still frame (0 .. 0.15, 0.55 .. the end)
    assert np.allclose(W[0], W[i15 - 1]) and np.allclose(W[frame_of(clip, 0.55)], W[-1])


def test_a_hand_that_never_reaches_it_and_a_relatch_that_misses_the_magwell_are_named():
    clip = reload_clip()
    sock = magwell_socket(clip)
    far = dict(sock, pos=[sock["pos"][0], sock["pos"][1] - 0.6, sock["pos"][2]])      # the magwell 0.6 lower
    r = H.solve(clip, plan_for(clip, far))
    assert any(f["phase"] == 1 and "takes it 0.60 studs" in f["what"] for f in r["faults"])
    off = reload_clip(back_deg=60.0)                                                   # comes back 10 deg short
    r = H.solve(off, plan_for(off, magwell_socket(off)))
    assert [f["phase"] for f in r["faults"]] == [2] and "off its socket on Handle (from Left Arm)" in r["faults"][0]["what"]
    assert r["seams"][0]["studs"] > 0.1


def test_the_track_the_game_plays_puts_it_on_the_carrier_where_it_was_solved():
    clip = reload_clip()
    plan = plan_for(clip)
    r = H.write(clip, plan)
    prop = clip["props"]["Mag"]
    assert prop["carrier"] == "Torso" and len(prop["frames"]) == len(clip["times"])
    for i in (0, 20, 40, len(clip["times"]) - 1):
        T = np.eye(4)
        T[:3, :3] = C.quat_mat(prop["frames"][i][:4])
        T[:3, 3] = prop["frames"][i][4:7]
        torso = C.fk(RIG, C.character_transforms(clip, RIG, i))["Torso"]
        assert np.allclose(torso @ H._at({}) @ T, r["world"][i], atol=1e-5)
    assert clip["handoff_read"]["faults"] == []


def toss_clip():
    """1.0 s: the right arm holds a weapon ahead, lets it go at 0.3, the left arm is up to catch it at 0.7"""
    n = FPS + 1
    times = [i / FPS for i in range(n)]
    right = [quat((1, 0, 0), 90) + [0, 0, 0] for _ in times]
    left = [quat((1, 0, 0), ease(0, 90, min(t / 0.6, 1.0))) + [0, 0, 0] for t in times]
    return {"name": "FixToss", "rig": "R6", "fps": FPS, "times": times, "events": [],
            "joints": {"Right Arm": {"frames": right}, "Left Arm": {"frames": left}}}


def test_a_toss_flies_a_parabola_under_g_and_lands_in_the_catching_hand_exactly():
    clip = toss_clip()
    plan = {"object": "Handle", "carrier": "Right Arm", "phases": [
        {"t": 0.0, "parent": "Right Arm", "at": {"pos": [0, -1, 0], "rot": [-90, 0, 0]}},
        {"t": 0.3, "toss": {"g": 35, "turns": 1, "axis": [1, 0, 0]}},
        {"t": 0.7, "parent": "Left Arm", "at": {"pos": [0, -1, 0], "rot": [-90, 0, 0]}}]}
    r = H.write(clip, plan)
    assert r["faults"] == [] and len(r["tosses"]) == 1
    W = r["world"]
    a, b = frame_of(clip, 0.3), frame_of(clip, 0.7)
    dt = 1 / FPS
    ys = [W[i][1, 3] for i in range(a, b + 1)]
    second = [ys[i + 1] - 2 * ys[i] + ys[i - 1] for i in range(1, len(ys) - 2)]     # (the last step lands in the hand)
    assert max(abs(s + 35 * dt * dt) for s in second) < 1e-9                         # y'' = -g all the way
    xs = [W[i][0, 3] for i in range(a, b)]
    assert max(abs(xs[i + 1] - 2 * xs[i] + xs[i - 1]) for i in range(1, len(xs) - 1)) < 1e-9   # straight sideways
    P = H._parents(clip, RIG)
    catch = P[b]["Left Arm"] @ H._at({"pos": [0, -1, 0], "rot": [-90, 0, 0]})
    assert np.allclose(W[b], catch, atol=1e-9)                                        # the 0.00 st catch seam
    rel = np.linalg.inv(catch) @ W[b - 1]                                             # one frame before: still flying
    assert np.linalg.norm(rel[:3, 3]) > 0.01
    t = r["tosses"][0]
    assert t["g"] == 35 and t["rises"] > 0 and abs(t["launch"][1] - (ys[-1] - ys[0] + 0.5 * 35 * 0.4 ** 2) / 0.4) < 1e-3
    # it plays as the weapon's own joint: clip["grip"] on the Right Arm (grip.py's C0)
    assert len(clip["grip"]) == len(clip["times"]) and np.allclose(clip["grip"][0], [0, 0, 0, 1, 0, 0, 0], atol=1e-6)
    Pw = H._parents(clip, RIG)
    assert all(np.allclose(Pw[i]["Handle"], W[i], atol=1e-5) for i in (0, a + 5, b, len(W) - 1))


@pytest.mark.parametrize("plan, why", [
    ({"object": "Mag", "carrier": "Torso", "phases": []}, "a handoff is"),
    ({"object": "Mag", "carrier": "Torso", "phases": [{"t": 0, "parent": "Handle"}]}, "the first phase needs its `at`"),
    ({"object": "Mag", "carrier": "Torso", "phases": [{"t": 0, "parent": "Handle", "at": {}}, {"t": 0.3, "toss": {}}]},
     "the next phase must be carried, with its `at`"),
    ({"object": "Mag", "carrier": "Torso", "phases": [{"t": 0, "parent": "Handle", "at": {}}, {"t": 0.3, "toss": {"g": 0}},
                                                    {"t": 0.6, "parent": "Left Arm", "at": {}}]}, "g\": studs/s^2 above 0"),
    ({"object": "Mag", "carrier": "Torso", "phases": [{"t": 0.2, "parent": "Handle", "at": {}}, {"t": 0.2, "parent": "Left Arm"}]},
     "is not after the one before"),
    ({"object": "Mag", "carrier": "Torso", "phases": [{"t": 0, "parent": "Handle", "toss": {}, "at": {}}]}, "one of the two"),
])
def test_what_cannot_be_a_plan_is_refused(plan, why):
    assert any(why in p for p in H.problems(plan)), H.problems(plan)
    with pytest.raises(ValueError):
        H.solve(reload_clip(), plan)


def test_a_parent_the_clip_does_not_have_and_the_builds_gate():
    clip = reload_clip()
    plan = plan_for(clip)
    bad = copy.deepcopy(plan)
    bad["phases"][1]["parent"] = "Tail"
    with pytest.raises(ValueError, match="not a part of the rig"):
        H.solve(clip, bad)
    assert H.gate(clip) == (None, None)                                   # no plan: nothing said
    clip["handoff"] = plan
    _, problem = H.gate(clip)                                              # planned, never written: nothing plays it
    assert problem and "never written" in problem
    H.write(clip, plan)
    reading, problem = H.gate(clip)
    assert problem is None and reading["seams"][0]["studs"] < 1e-6 and reading["played_off"] < 1e-6
    # the arm re-baked after the plan was written: the game would play the old track, off the hand (the review)
    rebaked = copy.deepcopy(clip)
    for f in rebaked["joints"]["Left Arm"]["frames"][20:40]:
        f[:4] = quat((1, 0, 0), 5)
    _, problem = H.gate(rebaked)
    assert problem and "write it again" in problem
    off = reload_clip(back_deg=60.0)
    off["handoff"] = plan_for(off)
    H.write(off, off["handoff"])
    reading, problem = H.gate(off)
    assert problem and "Mag: phase 2" in problem and "off its socket" in problem
    del clip["grip"]                                                       # a Handle parent with no weapon joint
    _, problem = H.gate(clip)
    assert problem and "cannot be solved" in problem


def test_the_kits_compiler_writes_the_object_as_a_pose_under_its_carrier_every_frame(tmp_path):
    import json
    import shutil
    import subprocess
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    clip = reload_clip()
    H.write(clip, plan_for(clip))
    p = tmp_path / "FixReload.clip.json"
    p.write_text(json.dumps(clip), encoding="utf-8")
    out = subprocess.run(["lune", "run", "kit/selftest/anim/handoff_model.luau", str(p)], cwd=ROOT,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout.strip().splitlines()[-1])
    assert got["keyframes"] == len(clip["times"])                          # every frame, not the keys
    mag = got["objects"]["Mag"]
    assert mag["parent"] == "Torso" and len(mag["cfs"]) == len(clip["times"])
    for i in (0, 20, 40, len(clip["times"]) - 1):
        t, pos, rows = mag["cfs"][i]
        f = clip["props"]["Mag"]["frames"][i]
        assert abs(t - clip["times"][i]) < 1e-6 and np.allclose(pos, f[4:7], atol=1e-5)
        assert np.allclose(np.array(rows), C.quat_mat(f[:4]), atol=1e-5)


def test_review_d2_a_toss_turns_whole_turns_flies_two_frames_or_more_and_a_take_is_by_a_hand():
    clip = toss_clip()

    def plan(turns=1, at=0.3, catch=0.7, mid=None):
        ph = [{"t": 0.0, "parent": "Right Arm", "at": {"pos": [0, -1, 0]}}, {"t": at, "toss": {"turns": turns}},
              {"t": catch, "parent": "Left Arm", "at": {"pos": [0, -1, 0]}}]
        return {"object": "Coin", "carrier": "Torso", "phases": ph if mid is None else mid}
    assert any("whole extra turns" in p for p in H.problems(plan(turns=0.5)))
    with pytest.raises(ValueError, match="in the air 1 frame"):
        H.solve(clip, plan(at=0.3, catch=0.3 + 1 / FPS))
    assert any("starts the clip" in p for p in H.problems(
        {"object": "Coin", "carrier": "Torso", "phases": [{"t": 0.1, "parent": "Torso", "at": {}}]}))
    r = H.solve(clip, plan(mid=[{"t": 0.0, "parent": "Right Arm", "at": {"pos": [0, -1, 0]}},
                                {"t": 0.4, "parent": "Torso"}]))           # the torso "takes" it where it is: refused
    assert any("is no hand" in f["what"] for f in r["faults"])


def test_review_d2_a_toss_falls_under_gravity_in_the_world_when_the_body_travels():
    clip = toss_clip()
    n = len(clip["times"])
    clip["root"] = [quat((0, 1, 0), 90 * t) + [0, 0, -10 * t] for t in clip["times"]]   # runs ahead, turning
    plan = {"object": "Coin", "carrier": "Torso", "phases": [
        {"t": 0.0, "parent": "Right Arm", "at": {"pos": [0, -1, 0]}}, {"t": 0.3, "toss": {"turns": 0}},
        {"t": 0.7, "parent": "Left Arm", "at": {"pos": [0, -1, 0]}}]}
    r = H.solve(clip, plan)
    a, b = frame_of(clip, 0.3), frame_of(clip, 0.7)
    Wp = [H._root(clip, i) @ r["world"][i] for i in range(a, b + 1)]
    dt = 1 / FPS
    for axis, acc in ((0, 0.0), (1, -35.0), (2, 0.0)):                      # in the WORLD: a straight-line throw + g
        x = [M[axis, 3] for M in Wp]
        assert max(abs(x[i + 1] - 2 * x[i] + x[i - 1] - acc * dt * dt) for i in range(1, len(x) - 2)) < 1e-9
    assert n == len(r["track"])


def test_review_d2_a_tossed_weapon_moves_its_paths_and_says_toss_and_catch():
    clip = toss_clip()
    n = len(clip["times"])
    clip["grip"] = [[0, 0, 0, 1, 0, 0, 0]] * n
    P = H._parents(clip, RIG)
    clip["sword"] = {"tip": [[float(v) for v in (P[i]["Handle"] @ np.array([0, 2, 0, 1.0]))[:3]] for i in range(n)],
                     "grip_path": [[float(v) for v in P[i]["Handle"][:3, 3]] for i in range(n)],
                     "edge": [[float(v) for v in -P[i]["Handle"][:3, 0]] for i in range(n)]}
    plan = {"object": "Handle", "carrier": "Right Arm", "phases": [
        {"t": 0.0, "parent": "Right Arm", "at": {"pos": [0, -1, 0], "rot": [-90, 0, 0]}},
        {"t": 0.3, "toss": {"turns": 1, "axis": [1, 0, 0]}},
        {"t": 0.7, "parent": "Left Arm", "at": {"pos": [0, -1, 0], "rot": [-90, 0, 0]}}]}
    r = H.write(clip, plan)
    for i in (0, frame_of(clip, 0.5), n - 1):
        W = r["world"][i]
        assert np.allclose(clip["sword"]["tip"][i], (W @ np.array([0, 2, 0, 1.0]))[:3], atol=1e-5)
        assert np.allclose(clip["sword"]["grip_path"][i], W[:3, 3], atol=1e-5)
        assert np.allclose(clip["sword"]["edge"][i], -W[:3, 0], atol=1e-5)
    names = [(e["name"], e["t"]) for e in clip["events"]]
    assert ("Toss", 0.3) in names and ("Catch", 0.7) in names
