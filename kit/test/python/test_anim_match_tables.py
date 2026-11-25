"""kit/anim/match_tables.py + src/kit/AnimMatch.luau - pose matching, distance matching and motion matching (the
owner's method lists 2026-11-13): the tables baked from clips, what is refused, and the GAME's matcher held to the
build's on the same tables. The clips are cuts the owner loved, generated in memory (read only)."""
import copy
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C            # noqa: E402
import match_tables as MT   # noqa: E402
import strike as S          # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved")


def loved(name, **more):
    with open(os.path.join(LOVED, f"{name}.move.json"), encoding="utf-8") as fh:
        return S.generate({**json.load(fh), **more})[0]


def hit_frame(c):
    return round(next(e["t"] for e in c["events"] if e["name"] == "Hit") * c["fps"])


def pose_of(c, i):
    return {j: c["joints"][j]["frames"][i][:4] for j in c["joints"]}


def angle_cost(c, i, pose):
    """the same measure worked from rotation MATRICES (no quaternion dot): mean over joints of angle / 180 degrees"""
    tot = 0.0
    for j in c["joints"]:
        A, B = C.quat_mat(np.array(c["joints"][j]["frames"][i][:4], float)), C.quat_mat(np.array(pose[j], float))
        ang = np.arccos(np.clip((np.trace(A.T @ B) - 1) / 2, -1, 1))
        tot += ang / np.pi
    return tot / len(c["joints"])


def travelling(c, studs=4.0, back=0.0):
    """the clip given a body that travels forward (-Z) and eases to a stop, optionally stepping back mid-way"""
    c = copy.deepcopy(c)
    n = len(c["times"])
    root = []
    for i in range(n):
        u = i / (n - 1)
        z = -studs * (1 - (1 - u) ** 2)
        if back and 0.4 < u < 0.6:
            z += back * np.sin((u - 0.4) / 0.2 * np.pi)
        root.append([0, 0, 0, 1, 0, 0.3 * np.sin(u * np.pi), z])
    c["root"] = root
    return c


# ---------------------------------------------------------------- pose matching
def test_a_clip_is_entered_at_the_frame_nearest_the_pose_and_only_before_its_hit():
    kesa = loved("Katana1Kesa")
    t = MT.pose_table(kesa)
    assert t["kind"] == "pose" and t["joints"] == list(kesa["joints"]) and len(t["rows"]) == hit_frame(kesa)   # frames 0 .. Hit - 1
    for i in (0, 7, 15, len(t["rows"]) - 1):
        assert MT.pose_match(t, pose_of(kesa, i)) == i
    rng = np.random.default_rng(2)
    other = loved("Katana2GyakuKesa")
    for i in (0, 10, 20, len(other["times"]) - 1):
        pose = pose_of(other, i)
        for j in pose:                                           # a pose that is no frame of this clip, shaken a little
            q = np.array(pose[j]) + rng.normal(size=4) * 0.02
            pose[j] = (q / np.linalg.norm(q) * (1 if i % 2 else -1)).tolist()     # either quaternion of the same turn
        costs = [angle_cost(kesa, f, pose) for f in range(len(t["rows"]))]
        assert MT.pose_match(t, pose) == int(np.argmin(costs))
    after_hit = pose_of(kesa, len(kesa["times"]) - 1)
    assert MT.pose_match(t, after_hit) < hit_frame(kesa)         # never entered past the Hit, whatever the pose
    one = {"Torso": kesa["joints"]["Torso"]["frames"][9][:4]}                 # a pose of one joint: the torso alone decides
    T = [C.quat_mat(np.array(kesa["joints"]["Torso"]["frames"][f][:4], float)) for f in range(len(t["rows"]))]
    assert MT.pose_match(t, one) == int(np.argmin([np.arccos(np.clip((np.trace(M.T @ T[9]) - 1) / 2, -1, 1)) for M in T]))
    big = {j: (np.array(q) * 7.0).tolist() for j, q in pose_of(kesa, 15).items()}
    assert MT.pose_match(t, big) == 15                               # a pose that is not at unit length is the same pose


def test_where_a_clip_may_be_entered():
    kesa = loved("Katana1Kesa")
    assert MT.enter_frames(kesa) == hit_frame(kesa) - 1
    loop = dict(copy.deepcopy(kesa), loop=True)
    assert MT.enter_frames(loop) == len(kesa["times"]) - 1
    plain = dict(copy.deepcopy(kesa), events=[])
    assert MT.enter_frames(plain) == (len(kesa["times"]) - 1) // 2
    early = copy.deepcopy(kesa)
    early["events"] = [{"name": "Hit", "t": 1 / 60}]
    with pytest.raises(ValueError, match="fewer than 2 frames it may be entered at"):
        MT.pose_table(early)
    short = copy.deepcopy(kesa)
    short["joints"]["Head"]["frames"] = short["joints"]["Head"]["frames"][:10]
    with pytest.raises(ValueError, match="Head carries 10 frames"):
        MT.pose_table(short)


# ---------------------------------------------------------------- distance matching
def test_the_frame_for_a_distance_left_is_the_frame_that_far_from_the_stop():
    c = travelling(loved("Katana1Kesa"))
    t = MT.distance_table(c)
    n = len(c["times"])
    assert t["to"] == "end" and len(t["remaining"]) == n and abs(t["remaining"][0] - 4.0) < 1e-3 and t["remaining"][-1] == 0
    z = np.array(c["root"])[:, 6]
    for i in (0, 5, 20, 40):
        left = abs(z[-1] - z[i])                                 # how far frame i is from the stop, off the track itself
        assert abs(MT.distance_match(t, left) - i) < 0.02
    mid = (abs(z[-1] - z[10]) + abs(z[-1] - z[11])) / 2
    assert 10.3 < MT.distance_match(t, mid) < 10.7               # between two frames
    assert MT.distance_match(t, 99) == 0.0
    held = {"remaining": [4, 3, 3, 2, 1, 0, 0, 0, 0]}            # a body that pauses, and stands at the stop for four frames
    assert MT.distance_match(held, 0) == 5.0 and MT.distance_match(held, -1e-9) == 5.0 and MT.distance_match(held, -3) == 5.0
    assert MT.distance_match(held, 3) == 1.0 and MT.distance_match(held, 2.5) == 2.5 and MT.distance_match(held, 3.5) == 0.5
    hit = MT.distance_table(c, to="Hit")
    assert len(hit["remaining"]) == hit_frame(c) + 1 and abs(hit["remaining"][0] - abs(z[hit_frame(c)] - z[0])) < 1e-3
    assert all(a >= b for a, b in zip(t["remaining"], t["remaining"][1:]))


def test_a_clip_that_cannot_give_a_distance_table_is_refused():
    kesa = loved("Katana1Kesa")
    with pytest.raises(ValueError, match="does not travel .it carries no root track"):
        MT.distance_table(kesa)
    with pytest.raises(ValueError, match="travels 0.20 studs before its end"):
        MT.distance_table(travelling(kesa, studs=0.2))
    with pytest.raises(ValueError, match=r"travels back 0\.\d\d studs on the way"):
        MT.distance_table(travelling(kesa, back=1.2))
    assert MT.distance_table(travelling(kesa, back=0.02))["remaining"][0] > 3.9      # a wobble under 0.05 studs is not a step back
    with pytest.raises(ValueError, match="no event Land"):
        MT.distance_table(travelling(kesa), to="Land")
    up = copy.deepcopy(kesa)
    up["root"] = [[0, 0, 0, 1, 0, 3.0 * i / 51, 0] for i in range(len(up["times"]))]
    with pytest.raises(ValueError, match="travels 0.00 studs"):          # a jump straight up travels nowhere along the ground
        MT.distance_table(up)


# ---------------------------------------------------------------- motion matching
def db3():
    clips = [loved("Katana1Kesa"), loved("Katana2GyakuKesa"), loved("Katana3Makko")]
    return MT.motion_db(clips), clips


def play(db, clip, start, ticks, source=None):
    """the game's own loop: the frame on screen is read (its pose, how it turned since the frame before) and the
    matcher is asked what to play next -> the frames played. source: the clip the BODY really follows (default: the
    clip being played)"""
    cur, played = [clip["name"], start], []
    by_name = {clip["name"]: clip, **({source["name"]: source} if source else {})}
    for _ in range(ticks):
        body = source if source is not None and cur[0] == clip["name"] and source is not clip else by_name[cur[0]]
        pose, vel = MT.query_at(db, body, cur[1])
        cur = MT.motion_match(db, pose, vel, cur)
        played.append(list(cur))
    return played


def test_played_as_a_game_plays_it_a_clip_runs_straight_through_and_holds_its_last_offered_frame():
    db, clips = db3()
    assert db["kind"] == "motion" and len(db["rows"]) == sum(len(c["times"]) - MT.TAIL for c in clips) == len(db["index"])
    assert len(db["rows"][0]) == 7 * len(db["joints"])
    for c in clips:
        last = db["clips"][c["name"]]["frames"] - 1
        played = play(db, c, 0, last + 4)
        assert played[:last] == [[c["name"], f] for f in range(1, last + 1)]      # 1, 2, 3 ... every frame, in order
        assert played[last:] == [[c["name"], last]] * 4                           # nothing follows: it holds
    for c in clips:                                              # with no clip playing, a frame's pose gives the frame after it
        for f in (0, 9, 25):
            pose, vel = MT.query_at(db, c, f)
            assert MT.motion_match(db, pose, vel) == [c["name"], f + 1]
    pose, vel = MT.query_at(db, clips[2], 12)                    # the body is doing the makko: it leaves the kesa for it
    assert MT.motion_match(db, pose, vel, ["Katana1Kesa", 30]) == ["Katana3Makko", 13]
    assert MT.motion_match(db, pose, vel, ["Katana3Makko", 12.7]) == ["Katana3Makko", 13]     # a frame read off a clock
    assert MT.motion_match(db, pose, vel, ["Katana3Makko", float("nan")]) == ["Katana3Makko", 13]
    assert MT.motion_match(db, pose, vel, ["Katana3Makko", -4]) == ["Katana3Makko", 13]


def test_the_measures_behind_the_margin_and_what_the_turning_counts_for():
    db, clips = db3()
    kesa = clips[0]
    k = len(db["joints"])
    # the frame on screen fits its own row (rounding apart); the nearest frame of ANOTHER cut is far outside the margin's reach
    own, other = [], []
    for c in clips:
        span = db["clips"][c["name"]]
        for f in range(1, span["frames"]):
            pose, vel = MT.query_at(db, c, f)
            own.append(MT.motion_cost(db, db["rows"][span["first"] + f], pose, vel))
            other.append(min(MT.motion_cost(db, row, pose, vel) for i, row in enumerate(db["rows"]) if db["index"][i][0] != c["name"]))
    assert max(own) < 2e-3 and min(other) > 0.04
    pose, vel = MT.query_at(db, kesa, 20)
    assert MT.motion_cost(db, db["rows"][20], pose, vel) < 2e-3 and MT.motion_cost(db, db["rows"][20], pose, [0.0] * (3 * k)) > 0.01
    assert abs(MT.pose_cost(db["rows"][20][: 4 * k], (np.array(pose) * 3).tolist()) - MT.pose_cost(db["rows"][20][: 4 * k], pose)) < 1e-9
    # 30 degrees off on every joint is a sixth of a half turn
    q30 = [np.sin(np.radians(15)), 0, 0, np.cos(np.radians(15))] * 2
    assert abs(MT.pose_cost([0, 0, 0, 1] * 2, q30) - 1 / 6) < 1e-6
    # the velocity is the turn FROM THE FRAME BEFORE: half-turns a second about the right axis
    Q = MT._quats(kesa, db["joints"])
    V = MT._velocity(Q, db["fps"])
    j = db["joints"].index("Torso")
    D = C.quat_mat(Q[20, j]) @ C.quat_mat(Q[19, j]).T
    ang = np.arccos(np.clip((np.trace(D) - 1) / 2, -1, 1))
    axis = np.array([D[2, 1] - D[1, 2], D[0, 2] - D[2, 0], D[1, 0] - D[0, 1]])
    axis /= np.linalg.norm(axis)
    assert np.allclose(V[20, j], axis * np.sin(ang / 2) * 2 * db["fps"] / np.pi, atol=1e-6) and np.allclose(V[0], V[1])
    near = dict(db, stay=0.0)
    assert MT.motion_match(near, pose, vel, ["Katana1Kesa", 5]) == ["Katana1Kesa", 21]     # no margin: the row that fits wins
    wide = dict(db, stay=99.0)
    assert MT.motion_match(wide, pose, vel, ["Katana1Kesa", 5]) == ["Katana1Kesa", 6]      # a huge margin: it never leaves
    assert MT.motion_match(wide, pose, vel, ["Unknown", 3]) == ["Katana1Kesa", 21]


def test_a_database_that_cannot_work_is_refused():
    db, clips = db3()
    with pytest.raises(ValueError, match="needs 2 clips or more"):
        MT.motion_db(clips[:1])
    with pytest.raises(ValueError, match="its own name"):
        MT.motion_db([clips[0], clips[0]])
    fewer = copy.deepcopy(clips[1])
    del fewer["joints"]["Head"]
    with pytest.raises(ValueError, match="does not key the joints"):
        MT.motion_db([clips[0], fewer])
    slow = copy.deepcopy(clips[1])
    slow["times"] = [t * 2 for t in slow["times"]]
    with pytest.raises(ValueError, match="one database, one frame rate"):
        MT.motion_db([clips[0], slow])
    tiny = copy.deepcopy(clips[1])
    tiny["times"] = tiny["times"][:5]
    for j in tiny["joints"]:
        tiny["joints"][j]["frames"] = tiny["joints"][j]["frames"][:5]
    with pytest.raises(ValueError, match="too short"):
        MT.motion_db([clips[0], tiny])
    loop = dict(copy.deepcopy(clips[1]), loop=True)
    d = MT.motion_db([clips[0], loop])
    n = len(loop["times"])
    assert d["clips"][loop["name"]] == {"first": len(clips[0]["times"]) - MT.TAIL, "frames": n - 1, "loop": True}
    wide = dict(d, stay=99.0)
    pose, vel = MT.query_at(d, clips[0], 4)
    assert MT.motion_match(wide, pose, vel, [loop["name"], n - 2]) == [loop["name"], 0]    # a loop's last offered frame is followed by its first
    shuffled = copy.deepcopy(clips[1])
    shuffled["joints"] = dict(reversed(list(shuffled["joints"].items())))                  # the same joints in another order: the same rows
    assert MT.motion_db([clips[0], shuffled])["rows"] == MT.motion_db([clips[0], clips[1]])["rows"]
    nan = copy.deepcopy(clips[1])
    nan["joints"]["Head"]["frames"][3][0] = float("nan")
    for make in (lambda: MT.motion_db([clips[0], nan]), lambda: MT.pose_table(nan)):
        with pytest.raises(ValueError, match="Head carries a number that is not a number"):
            make()


# ---------------------------------------------------------------- the game's matcher gives the same answers
def ask(tmp_path, table, queries):
    tp, qp = tmp_path / "table.json", tmp_path / "queries.json"
    tp.write_text(json.dumps(table), encoding="utf-8")
    qp.write_text(json.dumps(queries), encoding="utf-8")
    r = subprocess.run(["lune", "run", os.path.join(ROOT, "kit", "anim", "match_run.luau"), str(tp), str(qp)], capture_output=True,
                       text=True, encoding="utf-8", cwd=ROOT)
    v = json.loads(r.stdout.strip().splitlines()[-1])
    assert v["status"] == "pass", r.stdout + r.stderr
    return v["answers"]


def test_the_games_matcher_answers_as_the_build_does(tmp_path):
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    rng = np.random.default_rng(5)
    kesa, other = loved("Katana1Kesa"), loved("GsCombo3Overhead")
    t = MT.pose_table(kesa)
    poses = [pose_of(kesa, 11), pose_of(other, 0), pose_of(other, 30), {"Torso": [0.1, 0.5, 0.0, -0.8]},
             {"Torso": [5e-13, 0, 0, 1e-13]}, {j: (np.array(q) * 4).tolist() for j, q in pose_of(kesa, 6).items()}]
    for _ in range(12):
        poses.append({j: (rng.normal(size=4)).tolist() for j in kesa["joints"]})
    assert ask(tmp_path, t, [{"pose": p} for p in poses]) == [MT.pose_match(t, p) for p in poses]
    d = MT.distance_table(travelling(kesa))
    dist = [99, 4.0, 3.3, 2.0, 1.234, 0.5, 0.01, 0, -1e-9, -1] + rng.uniform(0, 4, 10).tolist()
    held = {"kind": "distance", "fps": 60, "remaining": [4, 3, 3, 2, 1, 0, 0, 0, 0]}
    assert ask(tmp_path, held, [{"distance": x} for x in (0, -1e-9, -3, 3, 2.5)]) == [5, 5, 5, 1, 2.5]
    assert np.allclose(ask(tmp_path, d, [{"distance": x} for x in dist]), [MT.distance_match(d, x) for x in dist], atol=1e-6)
    db, clips = db3()
    qs = []
    for c, f, cur in ((clips[0], 20, None), (clips[0], 21, ["Katana1Kesa", 21]), (clips[2], 12, ["Katana1Kesa", 30]),
                      (clips[1], 5, ["Katana2GyakuKesa", db["clips"]["Katana2GyakuKesa"]["frames"] - 1]), (clips[1], 9, ["Unknown", 1]),
                      (clips[1], 9, ["Katana2GyakuKesa", 9.6]), (clips[1], 9, ["Katana2GyakuKesa", -3])):
        pose, vel = MT.query_at(db, c, f)
        qs.append({"pose": pose, "vel": vel, **({"current": cur} if cur else {})})
    for _ in range(10):
        pose = rng.normal(size=(len(db["joints"]), 4))
        pose /= np.linalg.norm(pose, axis=1, keepdims=True)
        qs.append({"pose": pose.reshape(-1).tolist(), "vel": rng.normal(size=3 * len(db["joints"])).tolist(),
                   "current": ["Katana3Makko", int(rng.integers(0, 40))]})
    assert ask(tmp_path, db, qs) == [MT.motion_match(db, q["pose"], q["vel"], q.get("current")) for q in qs]
    Q = MT._quats(kesa, db["joints"])
    V = MT._velocity(Q, db["fps"])
    got = ask(tmp_path, db, [{"a": Q[19, k].tolist(), "b": (-Q[20, k]).tolist(), "fps": db["fps"]} for k in range(len(db["joints"]))])
    assert np.allclose(got, V[20], atol=1e-6)                    # the game works a velocity out as the database's rows were
    # the game's own loop, on the game's matcher: pose now + the turn since the frame before -> straight through
    cur = ["Katana2GyakuKesa", 0]
    for _ in range(12):
        pose = Q2 = MT._quats(clips[1], db["joints"])[cur[1]].reshape(-1).tolist()
        before = MT._quats(clips[1], db["joints"])[max(cur[1] - 1, 0) if cur[1] else 1]
        now = MT._quats(clips[1], db["joints"])[cur[1] if cur[1] else 0]
        if cur[1] == 0:
            before, now = MT._quats(clips[1], db["joints"])[0], MT._quats(clips[1], db["joints"])[1]
        vel = ask(tmp_path, db, [{"a": before[k].tolist(), "b": now[k].tolist(), "fps": db["fps"]} for k in range(len(db["joints"]))])
        nxt = ask(tmp_path, db, [{"pose": pose, "vel": [v for row in vel for v in row], "current": cur}])[0]
        assert nxt == ["Katana2GyakuKesa", cur[1] + 1]
        cur = nxt


def test_the_tables_as_commands(tmp_path, capsys):
    kesa = loved("Katana1Kesa")
    paths = {}
    for name, c in (("kesa", kesa), ("travel", travelling(kesa)), ("gyaku", loved("Katana2GyakuKesa"))):
        paths[name] = str(tmp_path / f"{name}.clip.json")
        with open(paths[name], "w", encoding="utf-8") as fh:
            json.dump(c, fh)
    out = str(tmp_path / "t" / "table.json")
    assert MT.main(["pose", paths["kesa"], "--out", out]) == 0 and json.load(open(out))["kind"] == "pose"
    assert "may be entered at" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    assert MT.main(["distance", paths["travel"], "--to", "Hit", "--out", out]) == 0 and json.load(open(out))["to"] == "Hit"
    assert MT.main(["motion", paths["kesa"], paths["gyaku"], "--out", out]) == 0 and json.load(open(out))["kind"] == "motion"
    capsys.readouterr()
    os.remove(out)
    assert MT.main(["distance", paths["kesa"], "--out", out]) == 1 and not os.path.exists(out)      # refused: nothing written
    assert "no table - Katana1Kesa: the clip does not travel" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    assert MT.main(["motion", paths["kesa"], "--out", out]) == 1 and MT.main(["pose", str(tmp_path / "none.json"), "--out", out]) == 1
    assert MT.main(["pose", paths["kesa"]]) == 1 and MT.main(["other"]) == 2
    assert MT.main(["pose", paths["kesa"], "--to", "Hit", "--out", out]) == 1 and not os.path.exists(out)


# ---------------------------------------------------------------- the build's way in: a clip that says "match"
def test_a_clip_that_asks_gets_its_tables_and_one_that_cannot_have_them_is_refused(tmp_path, capsys):
    kesa = loved("Katana1Kesa", match={"pose": True})
    assert kesa["match"] == {"pose": True}                       # the move's ask rides on the clip the build compiles
    t = MT.tables_for(kesa)
    full = MT.pose_table(kesa)["rows"]                           # 60 rows a second: the game's data takes every 2nd
    assert set(t) == {"pose"} and "kind" not in t["pose"] and t["pose"]["fps"] == 30 and len(t["pose"]["rows"]) == (len(full) + 1) // 2
    assert np.allclose(t["pose"]["rows"], np.array(full)[::2], atol=1e-4)
    both = dict(travelling(kesa), match={"pose": True, "distance": "Hit"})
    t = MT.tables_for(both)
    assert set(t) == {"pose", "distance"} and t["distance"]["to"] == "Hit"
    # a distance table too lists only the frames BEFORE the Hit: entered later, the hit would never land
    # ... at the clip's OWN frame rate (the pose table is halved to 30 rows a second; a distance is one number a frame)
    assert t["distance"]["fps"] == 60 and t["pose"]["fps"] == 30
    assert len(t["distance"]["remaining"]) == 2 * len(t["pose"]["rows"]) and t["distance"]["remaining"][-1] > 0
    end = MT.tables_for(dict(travelling(kesa), match={"distance": True}))["distance"]
    assert len(end["remaining"]) == 2 * len(t["pose"]["rows"]) and end["remaining"][0] > 3.9
    # the one review, 2026-11-15: the ACCURACY the rate buys. A fast step (still, then 3 studs over 6 frames from frame
    # 10): the distance left at an ODD frame gives that frame back. Thinned to 30 rows a second and read between rows
    # it was 0.43 of a frame off (7.1e-3 s) - seen in Studio as 1.69 studs travelled for 1.5 asked
    z = [-3 * u * u * (3 - 2 * u) for u in (min(max((i - 10) / 6, 0), 1) for i in range(len(kesa["times"])))]
    fast = dict(kesa, root=[[0, 0, 0, 1, 0, 0, v] for v in z], match={"distance": True})
    ft = MT.tables_for(fast)["distance"]
    thin = {"remaining": ft["remaining"][::2]}
    for f in (11, 15):
        left = abs(z[-1] - z[f])
        assert abs(MT.distance_match(ft, left) / ft["fps"] - f / 60) < 1e-4
        assert abs(MT.distance_match(thin, left) / 30 - f / 60) > 5e-3       # (what the thinned table read)
    for ask, why in (({"distance": True}, "does not travel"), ({"pose": "yes"}, '"pose": true'), ({"motion": True}, '"match" is'),
                     ({}, '"match" is'), (True, '"match" is'), ({"distance": ""}, "an event's name"), ({"distance": 3}, "an event's name")):
        with pytest.raises(ValueError, match=why):
            MT.tables_for(dict(kesa, match=ask))
    with pytest.raises(ValueError, match="no event Land"):
        MT.tables_for(dict(travelling(kesa), match={"distance": "Land"}))
    cp, out = str(tmp_path / "c.json"), str(tmp_path / "m.json")
    with open(cp, "w", encoding="utf-8") as fh:
        json.dump(both, fh)
    assert MT.main(["for", cp, "--out", out]) == 0 and set(json.load(open(out))) == {"pose", "distance"}
    assert "entered by pose at" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    os.remove(out)
    with open(cp, "w", encoding="utf-8") as fh:
        json.dump(dict(kesa, match={"distance": True}), fh)
    assert MT.main(["for", cp, "--out", out]) == 1 and not os.path.exists(out)
    assert "does not travel" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]


def test_the_games_entry_reads_the_builds_tables(tmp_path):
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    kesa = dict(travelling(loved("Katana1Kesa")), match={"pose": True, "distance": True})
    meta = {"match": MT.tables_for(kesa)}                        # what the build writes into Meta.<clip>
    z = np.array(kesa["root"])[:, 6]
    last = (len(meta["match"]["pose"]["rows"]) - 1) / 30         # the last time it may be entered at, seconds
    qs = [{"enter": True, "pose": pose_of(kesa, 12)}, {"enter": True, "distance": float(abs(z[-1] - z[20]))},
          {"enter": True, "pose": pose_of(kesa, 12), "distance": float(abs(z[-1] - z[40]))}, {"enter": True}]
    got = ask(tmp_path, meta, qs)
    assert abs(got[0] - 12 / 60) < 1e-6                          # by pose: frame 12 of the 60-a-second clip, in seconds
    assert abs(got[1] - 20 / 60) < 1e-3                          # by distance: the frame that far from the stop
    last = (len(meta["match"]["distance"]["remaining"]) - 1) / 60       # (the distance table is at the clip's own 60 a second)
    assert abs(got[2] - last) < 1e-6 and last < 26 / 60          # a distance past the Hit: the last frame before it, never later
    assert got[3] == -1
    assert ask(tmp_path, {"match": {"pose": meta["match"]["pose"]}}, [{"enter": True, "distance": 2.0}]) == [-1]
    broken = {"match": {"pose": {"joints": ["Torso"], "rows": [[0, 0, 0, 1]]}, "distance": {"fps": 0, "remaining": [1, 0]}}}
    assert ask(tmp_path, broken, [{"enter": True, "pose": {"Torso": [0, 0, 0, 1]}}, {"enter": True, "distance": 0.5}]) == [-1, -1]


# ---------------------------------------------------------------- the build's way in for motion matching: a set
KATANAS = ("Katana1Kesa", "Katana2GyakuKesa", "Katana3Makko")


def resting(n=51):
    """the set's rest: a guard that sways a little and comes back to where it began (a loop, an odd number of frames)"""
    c = loved("Katana1Kesa")
    first = {j: c["joints"][j]["frames"][0] for j in c["joints"]}
    out = {"name": "Rest", "rig": "R6", "fps": 60, "loop": True, "events": [], "times": [i / 60 for i in range(n)], "joints": {}}
    for j, f in first.items():
        frames = []
        for i in range(n):
            a = np.radians(4 * np.sin(2 * np.pi * i / (n - 1))) / 2
            sway = np.array([0.0, np.sin(a), 0.0, np.cos(a)]) if j == "Torso" else np.array([0.0, 0.0, 0.0, 1.0])
            q = np.array(f[:4], float)
            x1, y1, z1, w1 = sway
            x2, y2, z2, w2 = q
            frames.append([w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                           w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, *f[4:7]])
        out["joints"][j] = {"frames": frames}
    return out


def clips60():
    return {**{n: loved(n) for n in KATANAS}, "Rest": resting()}


def built(tmp_path, clips=None):
    """a folder of built clips, as the build hands them over"""
    d = tmp_path / "clips"
    d.mkdir(exist_ok=True)
    for n, c in (clips or clips60()).items():
        (d / f"{n}.clip.json").write_text(json.dumps(c), encoding="utf-8")
    return str(d)


SET = {"clips": [*KATANAS, "Rest"], "rest": "Rest"}


def test_a_motion_sets_database_is_baked_at_30_rows_a_second_and_a_set_that_cannot_be_is_refused(tmp_path, capsys):
    d = built(tmp_path)
    db = MT.motion_set(SET, d)
    full = MT.motion_db([loved(n) for n in KATANAS])
    assert db["fps"] == 30 and list(db["clips"]) == [*KATANAS, "Rest"] and db["rest"] == "Rest"
    assert db["clips"]["Rest"] == {"first": sum(db["clips"][n]["frames"] for n in KATANAS), "frames": 25, "loop": True}   # 51 -> 26 kept, the closing one not offered
    assert sum(db["clips"][n]["frames"] for n in KATANAS) < 0.6 * len(full["rows"])
    kesa = loved("Katana1Kesa")
    Q = MT._quats(kesa, db["joints"])
    assert np.allclose(np.array(db["rows"][5][: 4 * len(db["joints"])]).reshape(-1, 4), Q[10], atol=1e-4)   # row 5 is frame 10
    # how it is turning: from the kept frame BEFORE (frame 8 to 10), at the database's own rate
    V = MT._velocity(Q[::2], 30.0)
    assert np.allclose(np.array(db["rows"][5][4 * len(db["joints"]):]).reshape(-1, 3), V[5], atol=1e-4)
    even = dict(clips60(), Rest=resting(52))
    notloop = dict(clips60(), Rest=dict(resting(), loop=False))
    for spec, folder, why in (
            ({"clips": ["Katana1Kesa"], "rest": "Katana1Kesa"}, d, "2 clips or more"), ({"clips": "Katana1Kesa"}, d, "2 clips or more"),
            ({}, d, "2 clips or more"), ({"clips": ["Rest", "Rest"], "rest": "Rest"}, d, "names each clip once"),
            ({"clips": ["Rest", "../Rest"], "rest": "Rest"}, d, "is not a clip's name"),
            ({"clips": list(KATANAS)}, d, "names its \"rest\""), ({"clips": list(KATANAS), "rest": "Rest"}, d, "names its \"rest\""),
            ({"clips": [*KATANAS, "Rest"], "rest": "Katana1Kesa"}, d, "its rest Katana1Kesa does not loop"),
            ({"clips": ["Rest", "Katana1Kesa", "Ghost"], "rest": "Rest"}, d, "names the clip Ghost, which this build did not make"),
            (SET, built(tmp_path / "e", even) if (tmp_path / "e").mkdir() is None else "", "Rest loops over 52 frames at 60 a second: an even count"),
            (SET, built(tmp_path / "n", notloop) if (tmp_path / "n").mkdir() is None else "", "its rest Rest does not loop")):
        with pytest.raises(ValueError, match=why):
            MT.motion_set(spec, folder)
    sp, out = tmp_path / "Blade.motion.json", str(tmp_path / "db.json")
    sp.write_text(json.dumps(SET), encoding="utf-8")
    assert MT.main(["set", str(sp), "--clips", d, "--out", out]) == 0
    made = json.load(open(out))
    assert made["set"] == "Blade" and made["rows"] == db["rows"] and made["rest"] == "Rest"
    assert "4 clips" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    os.remove(out)
    sp.write_text(json.dumps({"clips": ["Rest", "Katana1Kesa", "Ghost"], "rest": "Rest"}), encoding="utf-8")
    assert MT.main(["set", str(sp), "--clips", d, "--out", out]) == 1 and not os.path.exists(out)
    assert "Ghost, which this build did not make" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    assert MT.main(["set", str(sp), "--out", out]) == 1


def game(db, clips, start, seconds, every=0.1, body=None):
    """src/kit/Anim.motion, line for line, on a clock: 60 frames a second; the played track runs in real time (a loop
    wraps, a clip that does not loop stops at its end); a look is two frames in a row (the pose, then the pose a
    frame later) once `every` seconds have passed; a jump to ANOTHER clip is taken, the track set to its frame; a
    stopped track sends the body to the set's rest. The body's pose is the played track's (body(t): another pose,
    for a body that is pushed) -> [(time, clip)] at every change of clip, and the number of looks"""
    length = {n: c["times"][-1] for n, c in clips.items()}
    playing, t, alive = start, 0.0, True
    before, waited, looks, log = None, 0.0, 0, [(0.0, start)]

    def pose_now(now):
        if body is not None and body(now) is not None:
            return body(now)
        c = clips[playing]
        return pose_of(c, min(int(round(t * 60)), len(c["times"]) - 1))
    for tick in range(int(seconds * 60)):
        dt, now = 1 / 60, tick / 60
        t += dt                                                   # the Animator steps the track
        if t >= length[playing]:
            if db["clips"][playing]["loop"]:
                t -= length[playing]
            else:
                alive = False
        if not alive:                                             # (Stepped) a clip that does not loop has played out
            playing, t, alive = db["rest"], 0.0, True
            log.append((now, playing))
            before, waited = None, 0.0
            continue
        waited += dt
        if before is not None:
            r = MT.motion_step(db, before, pose_now(now), dt, [playing, t * db["fps"]])
            before, waited, looks = None, 0.0, looks + 1
            if r["jump"] and r["clip"] != playing:
                playing, t = r["clip"], r["frame"] / db["fps"]
                log.append((now, playing))
        elif waited >= every:
            before = pose_now(now)
    return log, looks


def test_played_as_the_game_plays_a_set_each_cut_runs_to_its_end_then_the_body_rests(tmp_path):
    clips = clips60()
    db = MT.motion_set(SET, built(tmp_path, clips))
    for name in KATANAS:
        for every in (0.1, 0.03, 0.3):
            log, looks = game(db, clips, name, 3.0, every)
            # one change only: to the rest, when the cut has played out (its last frames too) - and it stays there
            assert [c for _, c in log] == [name, "Rest"] and looks >= 5
            assert abs(log[1][0] - clips[name]["times"][-1]) < 0.05
    log, looks = game(db, clips, "Rest", 4.0)                    # a body at rest stays at rest, through every wrap of the loop
    assert log == [(0.0, "Rest")] and looks >= 25


def test_a_body_that_is_pushed_into_another_cuts_motion_is_sent_to_that_cut(tmp_path):
    clips = clips60()
    db = MT.motion_set(SET, built(tmp_path, clips))
    makko = clips["Katana3Makko"]

    def pushed(now):                                             # from 0.5 s on the body does the makko, whatever plays
        return pose_of(makko, min(int(round((now - 0.5) * 60)) + 8, len(makko["times"]) - 1)) if now >= 0.5 else None
    log, _ = game(db, clips, "Rest", 2.5, body=pushed)
    assert [c for _, c in log][:2] == ["Rest", "Katana3Makko"] and 0.5 <= log[1][0] <= 0.75
    # a clip is never scrubbed within itself, and its last frames are never left
    r = MT.motion_step(db, pose_of(makko, 20), pose_of(makko, 21), 1 / 60, ["Katana1Kesa", 3.0])
    assert r["clip"] == "Katana3Makko" and r["jump"] is True and abs(r["frame"] - 11) <= 1
    last = db["clips"]["Katana1Kesa"]["frames"] - 1
    for at in (last, last + 0.4, last + 5.0):
        assert MT.motion_step(db, pose_of(makko, 20), pose_of(makko, 21), 1 / 60, ["Katana1Kesa", at]) == {
            "clip": "Katana1Kesa", "frame": last, "jump": False}
    first = MT.motion_step(db, None, pose_of(clips["Katana2GyakuKesa"], 20), 0.05, None)
    assert first["clip"] == "Katana2GyakuKesa" and first["jump"] is True and abs(first["frame"] - 11) <= 1


def test_the_games_step_is_the_builds(tmp_path):
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    clips = clips60()
    db = MT.motion_set(SET, built(tmp_path, clips))
    rng = np.random.default_rng(9)
    kesa, makko, rest = clips["Katana1Kesa"], clips["Katana3Makko"], clips["Rest"]
    last = db["clips"]["Katana1Kesa"]["frames"] - 1
    qs = [{"step": True, "prev": pose_of(kesa, 12), "pose": pose_of(kesa, 13), "dt": 1 / 60, "current": ["Katana1Kesa", 6.5]},
          {"step": True, "pose": pose_of(makko, 20), "dt": 0.05},
          {"step": True, "prev": pose_of(makko, 19), "pose": pose_of(makko, 20), "dt": 1 / 60, "current": ["Katana1Kesa", 9]},
          {"step": True, "prev": pose_of(kesa, 12), "pose": pose_of(kesa, 13), "dt": 0, "current": ["Katana1Kesa", 6.5]},
          {"step": True, "prev": pose_of(makko, 19), "pose": pose_of(makko, 20), "dt": 1 / 60, "current": ["Katana1Kesa", last + 0.5]},
          {"step": True, "prev": pose_of(rest, 48), "pose": pose_of(rest, 49), "dt": 1 / 60, "current": ["Rest", 24.5]},
          {"step": True, "prev": pose_of(rest, 0), "pose": pose_of(rest, 1), "dt": 1 / 60, "current": ["Rest", 0.5]},
          {"step": True, "prev": {"Torso": [0, 0, 0, 2]}, "pose": {"Torso": [0, 0.3, 0, 0.9]}, "dt": 0.1, "current": ["Ghost", 2]}]
    for _ in range(8):
        a = {j: rng.normal(size=4).tolist() for j in db["joints"]}
        b = {j: rng.normal(size=4).tolist() for j in db["joints"]}
        qs.append({"step": True, "prev": a, "pose": b, "dt": float(rng.uniform(0.01, 0.2)),
                   "current": [str(rng.choice(["Katana2GyakuKesa", "Rest"])), float(rng.uniform(0, 30))]})
    want = [MT.motion_step(db, q.get("prev"), q["pose"], q["dt"], q.get("current")) for q in qs]
    assert ask(tmp_path, db, qs) == want
    assert want[5]["clip"] == "Rest" and want[5]["jump"] is False        # a loop's last offered row is followed by its first
