"""2026-10-24: a cutscene's two-shot holds still through the attacker's teleport gap - the KatanaDuel render snapped to
the target alone for the 3 hidden frames of every strike and back (a jump cut that also lost the attacker)"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import cutscene as CS  # noqa: E402


class Stub:
    def __init__(self, n, yaw, hidden=()):
        self.visible = [i not in hidden for i in range(n)]
        self.root = [[0.0, 0.0, 0.0, yaw] for _ in range(n)]


def test_fight_shot_holds_through_a_hidden_attacker():
    n = 60
    actors = {"a": Stub(n, 0.0, hidden=range(20, 23)), "b": Stub(n, 180.0)}
    torso = {"a": np.tile([0.0, 1.0, -5.0], (n, 1)), "b": np.tile([0.0, 1.0, 0.0], (n, 1))}
    shots = [{"from": 0, "to": n, "kind": "fight", "a": "a", "b": "b", "side": 75.0}]
    cams = CS.camera(actors, shots, [], n, torso)
    locs = np.array([c["loc"] for c in cams])
    tgts = np.array([c["target"] for c in cams])
    step = np.linalg.norm(np.diff(locs, axis=0), axis=1)
    aim = np.linalg.norm(np.diff(tgts, axis=0), axis=1)
    assert step.max() < 0.2, f"the camera jumps {step.max():.2f} studs in one frame"   # (a slow push-in only)
    assert aim.max() < 1e-6                              # the aim stays between the two bodies
    assert abs(tgts[21][2] - (-2.5)) < 1e-6              # (the hidden attacker still counts in the middle)


def test_fight_shot_with_the_attacker_hidden_throughout_frames_the_target():
    n = 20
    actors = {"a": Stub(n, 0.0, hidden=range(n)), "b": Stub(n, 180.0)}
    torso = {"a": np.tile([0.0, 1.0, -5.0], (n, 1)), "b": np.tile([0.0, 1.0, 0.0], (n, 1))}
    cams = CS.camera(actors, [{"from": 0, "to": n, "kind": "fight", "a": "a", "b": "b"}], [], n, torso)
    assert abs(cams[5]["target"][2]) < 1e-6              # nothing of the attacker to frame: the target alone


def two_shots(side_a, side_b, n=80):
    actors = {"a": Stub(n, 0.0), "b": Stub(n, 180.0)}
    torso = {"a": np.tile([0.0, 1.0, -5.0], (n, 1)), "b": np.tile([0.0, 1.0, 0.0], (n, 1))}
    shots = [{"from": 0, "to": 40, "kind": "fight", "a": "a", "b": "b", "side": side_a},
             {"from": 40, "to": n, "kind": "fight", "a": "a", "b": "b", "side": side_b}]
    locs = np.array([c["loc"] for c in CS.camera(actors, shots, [], n, torso)])
    return np.linalg.norm(np.diff(locs, axis=0), axis=1)


def test_a_cut_under_30_degrees_eases_instead_of_jumping():
    step = two_shots(70.0, 60.0)                         # (the duel's strikes 1 -> 2)
    assert step.max() < 0.35, f"a {step.max():.2f}-stud lurch between two shots 10 deg apart"


def test_a_real_cut_stays_a_cut():
    step = two_shots(70.0, 150.0)                        # 80 deg: a cut, not a pan
    assert step[39] > 5.0


def test_a_similar_angle_on_another_subject_is_a_cut_not_a_fly_through():
    n = 80
    actors = {"a": Stub(n, 0.0), "b": Stub(n, 180.0), "c": Stub(n, 0.0), "d": Stub(n, 180.0)}
    torso = {"a": np.tile([0.0, 1.0, -5.0], (n, 1)), "b": np.tile([0.0, 1.0, 0.0], (n, 1)),
             "c": np.tile([40.0, 1.0, -5.0], (n, 1)), "d": np.tile([40.0, 1.0, 0.0], (n, 1))}
    shots = [{"from": 0, "to": 40, "kind": "fight", "a": "a", "b": "b", "side": 70.0},
             {"from": 40, "to": n, "kind": "fight", "a": "c", "b": "d", "side": 65.0}]
    locs = np.array([c["loc"] for c in CS.camera(actors, shots, [], n, torso)])
    step = np.linalg.norm(np.diff(locs, axis=0), axis=1)
    assert step[39] > 30.0                               # one cut across the arena
    assert step[40:].max() < 0.2                         # and then it holds


def test_a_short_shot_arrives_at_its_own_framing():
    n = 50
    actors = {"a": Stub(n, 0.0), "b": Stub(n, 180.0)}
    torso = {"a": np.tile([0.0, 1.0, -5.0], (n, 1)), "b": np.tile([0.0, 1.0, 0.0], (n, 1))}
    shots = [{"from": 0, "to": 40, "kind": "fight", "a": "a", "b": "b", "side": 70.0},
             {"from": 40, "to": n, "kind": "fight", "a": "a", "b": "b", "side": 60.0}]
    eased = CS.camera(actors, shots, [], n, torso)
    plain = CS.camera(actors, shots, [], n, torso, cut_deg=0.0)
    assert np.allclose(eased[n - 1]["loc"], plain[n - 1]["loc"])   # (10 frames: eased over 5, then its own)


def test_timeline_exports_plays_root_hidden_hits_and_camera(tmp_path):
    """the GAME timeline (src/kit/Cutscene plays it): plays in scene seconds, root rows "x y z yaw" with yaw in
    radians, hidden spans from the visibility, hit-stops sorted by time, camera keys every other frame at 60 fps"""
    import json
    import math
    n = 12
    clip = {"root": [CS.quat_y(180.0) + [1.0, 0.0, -2.0 - 0.1 * i] for i in range(n)]}
    p = tmp_path / "a.clip.json"
    p.write_text(json.dumps(clip), encoding="utf-8")
    vis = [True] * n
    vis[3] = vis[4] = False
    scene = {"fps": 60, "frames": n,
             "actors": {"a": {"clip": str(p), "look": "noob", "visible": vis,
                              "plays": [{"f": 0, "clip": "@idle"},
                                        {"f": 6, "clip": "Cut", "from": 0.2, "n": 6, "fade": 2, "kit": True}]}},
             "hits": [{"frame": 9, "hold": 3}, {"frame": 7, "hold": 6}],
             "camera": [{"loc": [0, 5, 10 + i], "target": [0, 0, 0]} for i in range(n)],
             "fx": [{"type": "impact", "frame": 7, "pos": [0, 1, 0]}, {"type": "afterimage", "frame": 1}]}
    tl = CS.timeline(scene)
    a = tl["actors"]["a"]
    assert tl["fps"] == 30.0 and tl["duration"] == round(n / 60, 4)
    assert a["plays"][0] == {"t": 0.0, "clip": "@idle"}
    assert a["plays"][1] == {"t": 0.1, "clip": "Cut", "from": 0.2, "len": 0.1, "fade": round(2 / 60, 4), "kit": True}
    assert len(a["root"]) == 6                                             # every other frame
    x, y, z, yaw = (float(v) for v in a["root"][1].split())
    assert (x, y, z) == (1.0, 0.0, -2.2) and abs(yaw - math.pi) < 1e-3       # frame 2; yaw 180 deg in radians
    assert a["hidden"] == [[round(3 / 60, 4), round(5 / 60, 4)]]
    assert [h["t"] for h in tl["hits"]] == sorted(h["t"] for h in tl["hits"]) and tl["hits"][0]["hold"] == 0.1
    assert len(tl["camera"]) == 6 and tl["camera"][1]["loc"] == [0, 5, 12]
    assert tl["events"] == [{"t": round(7 / 60, 4), "type": "impact", "pos": [0.0, 1.0, 0.0]}]  # (no afterimage)


def test_the_game_module_survives_a_long_string_closer_in_a_name(tmp_path, monkeypatch):
    """a name holding "]==]" cannot end the module's Luau long string early (security review 2026-10-24); a second
    cutscene keeps the first"""
    import re
    monkeypatch.setattr(CS, "timeline", lambda scene: {"name": scene["name"], "note": "a ]==] b ]===] c"})
    CS.write_game({"name": "One"}, str(tmp_path))
    path = CS.write_game({"name": "Two"}, str(tmp_path))
    text = open(path, encoding="utf-8").read()
    m = re.search(r"JSONDecode\(\[(=+)\[", text)
    closer = f"]{m.group(1)}]"
    body = text[m.end():text.rfind(closer)]
    assert closer not in body and len(m.group(1)) >= 4
    import json
    assert set(json.loads(body)) == {"One", "Two"}


def test_make_logs_what_each_actor_plays_for_the_game(monkeypatch):
    """the play log behind the game timeline (review 2026-10-24: untested): each strike's clip from its lead-in point,
    the reaction from its marker, a parry's attacker cut at the contact then held, the counter from its Hit - and a
    hit-stop moves every later play by its frames"""
    import copy
    REST = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]

    def clip(seconds, events):
        n = int(round(seconds * 60)) + 1
        return {"times": [i / 60 for i in range(n)], "fps": 60,
                "joints": {j: {"frames": [list(REST)] * n} for j in CS.JOINTS}, "events": events}

    clips = {"Cut": clip(1.0, [{"name": "Hit", "t": 0.5}]), "React": clip(0.8, [{"name": "Hit", "t": 0.3}]),
             "Guard": clip(1.0, [{"name": "Parry", "t": 0.15}, {"name": "Hit", "t": 0.47}])}

    def pick(say=None, cid=None, kind=None, kit=None):
        if kit:
            c = copy.deepcopy(clips[kit])
            hit = next((e["t"] for e in c["events"] if e["name"] == "Hit"), 0.4)
            return c, {"id": kit, "name": kit, "kit": True, "facts": {"strike": {"at_s": hit}}}
        return clip(1.0, []), {"id": "idle", "name": "Idle"}

    monkeypatch.setattr(CS, "pick", pick)
    script = {"actors": {"a": {"pos": [0, -5], "yaw": 0}, "b": {"pos": [0, 0], "yaw": 180}},
              "beats": [{"do": "idle", "seconds": 0.2},
                        {"do": "strike", "by": "a", "on": "b", "clip": "Cut", "teleport": False, "dist": 3.0,
                         "react_clip": "React", "react_from": "Hit", "hitstop": 4},
                        {"do": "strike", "by": "a", "on": "b", "clip": "Cut", "teleport": False, "dist": 3.0,
                         "react_clip": "Guard", "react_from": "Parry", "hitstop": 5,
                         "counter": {"react_clip": "React", "hitstop": 6}}]}
    actors, fx, hits, shots, total = CS.make(script)
    before = {k: copy.deepcopy(a.log) for k, a in actors.items()}
    CS.apply_hitstop(actors, fx, hits, shots, total)
    a, b = before["a"], before["b"]
    cuts = [e for e in a if e["clip"] == "Cut"]
    assert len(cuts) == 2 and all(abs(e["from"] - (0.5 - 0.22)) < 1e-6 and e["kit"] for e in cuts)
    assert [e["clip"] for e in b if not e["clip"].startswith("@")] == ["React", "Guard"]
    assert abs(next(e for e in b if e["clip"] == "React")["from"] - 0.3) < 1e-6        # from its Hit marker
    assert abs(next(e for e in b if e["clip"] == "Guard")["from"] - 0.15) < 1e-6       # from its Parry marker
    i2 = a.index(cuts[1])
    hit2 = cuts[1]["f"] + int(round(0.22 * 60))
    assert cuts[1]["n"] == hit2 + 1 - cuts[1]["f"]                                     # cut dead at the contact
    assert a[i2 + 1]["clip"] == "@hold" and a[i2 + 2]["clip"] == "React"
    assert abs(a[i2 + 2]["from"] - 0.3) < 1e-6                                          # the counter from its Hit
    after = actors["a"].log
    assert after[a.index(cuts[0])]["f"] == cuts[0]["f"]                                 # before any hit-stop
    assert after[i2]["f"] == cuts[1]["f"] + 4                                           # after the first (4 frames)
