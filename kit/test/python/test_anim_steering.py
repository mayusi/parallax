"""STEERED motion matching (the owner's limitations list 2026-11-15, A-R02: "motion matching continues current motion
without steering intent"): every row of a motion set carries where its clip is going, the game hands in where the
player wants to go, and the search counts the miss beside the pose - so a start, a stop and a change of direction
pick the clip that GOES there. Also: the clips the game allows now, the search's row budget, and the same asks put to
the blend route. Kit gaits generated in memory (read only); the game's matcher is held to the build's."""
import copy
import json
import math
import os
import shutil
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
sys.path.insert(0, HERE)
import gait_r6 as G                      # noqa: E402
import match_tables as MT                # noqa: E402
import test_anim_match_tables as T       # noqa: E402  (its helpers: ask, pose_of, travelling, loved)


def gaits():
    """a locomotion set out of the kit's own R6 gaits: Idle, Walk (8 studs a second), Run (16) and Back - the walk's
    very poses played the other way round, which only its travel tells from the walk"""
    idle = G.generate({"name": "Idle", "kind": "idle"})
    n = len(idle["times"])
    if n % 2 == 0:                                               # (a loop keeps an odd count)
        n -= 1
    idle["times"] = idle["times"][:n]
    for j in idle["joints"].values():
        j["frames"] = j["frames"][:n]
    walk, run = G.generate({"name": "Walk", "kind": "walk"}), G.generate({"name": "Run", "kind": "run"})
    back = copy.deepcopy(walk)
    back["name"] = "Back"
    for j in back["joints"].values():
        j["frames"] = j["frames"][::-1]
    back.pop("locomotion")
    return {"Idle": idle, "Walk": walk, "Run": run, "Back": back}


SET = {"clips": ["Idle", "Walk", "Run", "Back"], "rest": "Idle", "travel": {"Back": [0, 6]}}


def built(tmp_path, clips=None):
    d = tmp_path / "clips"
    d.mkdir(exist_ok=True)
    for n, c in (clips or gaits()).items():
        (d / f"{n}.clip.json").write_text(json.dumps(c), encoding="utf-8")
    return str(d)


def at(db, clips, name, frame, want=None, only=None, dt=1 / 30):
    """one look of the game's loop while `name` plays at `frame`: the body is where that clip has it"""
    c = clips[name]
    n = len(c["times"])
    return MT.motion_step(db, T.pose_of(c, (frame - 1) % (n - 1)), T.pose_of(c, frame), dt, [name, frame], want, only)


# ---------------------------------------------------------------- where a clip is going
def test_where_a_clip_is_going_is_read_off_the_clip_or_said_by_the_set():
    clips = gaits()
    assert MT.travel(clips["Walk"])[3] == [0.0, -8.0, 0.0] and MT.travel(clips["Run"])[0] == [0.0, -16.0, 0.0]
    assert MT.travel(clips["Idle"])[5] == [0.0, 0.0, 0.0]        # it stands
    assert MT.travel(clips["Back"], [0, 6])[0] == [0.0, 6.0, 0.0]
    assert MT.travel(clips["Back"], [1, 2, 90])[2] == pytest.approx([1.0, 2.0, math.pi / 2])
    # a clip that travels: its own root over the next 0.3 s, in the body's own frame
    kesa = T.travelling(T.loved("Katana1Kesa"), studs=4.0)
    going = MT.travel(kesa)
    n, fps = len(kesa["times"]), kesa["fps"]
    ahead = round(0.3 * fps)
    assert len(going) == n
    assert going[0] == pytest.approx([0.0, (kesa["root"][ahead][6] - kesa["root"][0][6]) / (ahead / fps), 0.0])
    assert going[0][1] < -5 and abs(going[n - 2][1]) < abs(going[0][1])     # it eases to its stop
    assert going[n - 1] == going[n - 2]                                    # the last frame has nothing after it
    # a body that has turned a quarter turn to the left and goes on the way it then faces: still "ahead" to it
    turned = copy.deepcopy(kesa)
    h = math.pi / 4
    for i, r in enumerate(turned["root"]):
        z = r[6]
        turned["root"][i] = [0, math.sin(h), 0, math.cos(h), z, 0, 0]       # faces -X, travels along -X
    g = MT.travel(turned)[0]
    assert g[0] == pytest.approx(0.0, abs=1e-9) and g[1] == pytest.approx(going[0][1]) and g[2] == 0.0
    # a body that turns as it goes
    spin = copy.deepcopy(kesa)
    for i in range(n):
        a = math.radians(2.0 * i) / 2
        spin["root"][i] = [0, math.sin(a), 0, math.cos(a), 0, 0, 0]
    assert MT.travel(spin)[0][2] == pytest.approx(math.radians(2.0) * fps)  # 2 degrees a frame, to the left
    for bad in ([1], [1, 2, 3, 4], "ahead", [0, float("nan")], [True, 0], {"x": 1}):
        with pytest.raises(ValueError, match="its \"travel\" is"):
            MT.travel(clips["Walk"], bad)


def test_a_set_carries_where_each_row_is_going_and_one_that_cannot_is_refused(tmp_path, monkeypatch):
    clips = gaits()
    d = built(tmp_path, clips)
    db = MT.motion_set(SET, d)
    assert len(db["traj"]) == len(db["rows"]) == len(db["index"])
    assert db["speed"] == 16.0 and db["turn"] == 1.0 and db["traj_weight"] == MT.TRAJ_WEIGHT
    for name, going in (("Idle", [0, 0, 0]), ("Walk", [0, -8, 0]), ("Run", [0, -16, 0]), ("Back", [0, 6, 0])):
        span = db["clips"][name]
        assert all(db["traj"][span["first"] + i] == going for i in range(span["frames"]))
    # a 60-a-second clip is halved: where it is going is read at its own rate first (thinning drops the root)
    kesa = T.travelling(T.loved("Katana1Kesa"))
    d2 = built(tmp_path / "t" if (tmp_path / "t").mkdir() is None else tmp_path, {**clips, "Kesa": kesa})
    db2 = MT.motion_set({"clips": ["Idle", "Walk", "Kesa"], "rest": "Idle"}, d2)
    span = db2["clips"]["Kesa"]
    assert db2["fps"] == 30 and db2["traj"][span["first"] + 3] == pytest.approx(MT.travel(kesa)[6], abs=1e-4)
    for spec, why in (({**SET, "travel": {"Ghost": [0, 1]}}, "for clips of the set"), ({**SET, "travel": [0, 1]}, "for clips of the set"),
                      ({**SET, "travel": {"Back": [0]}}, "Back: its \"travel\" is")):
        with pytest.raises(ValueError, match=why):
            MT.motion_set(spec, d)
    monkeypatch.setattr(MT, "MAX_ROWS", 100)
    with pytest.raises(ValueError, match="rows and a set holds 100 at most"):
        MT.motion_set(SET, d)


# ---------------------------------------------------------------- steering
def test_a_start_a_stop_and_a_change_of_direction_pick_the_clip_that_goes_there(tmp_path):
    clips = gaits()
    db = MT.motion_set(SET, built(tmp_path, clips))
    # NOTHING ASKED: the search is the one it was - a body in its clip stays in its clip
    for name in SET["clips"]:
        r = at(db, clips, name, 6)
        assert r["clip"] == name and r["jump"] is False
    # A START: standing, the player pushes forward - the pose alone would stay in the idle
    assert at(db, clips, "Idle", 6, want=[0, -8, 0])["clip"] == "Walk"
    assert at(db, clips, "Idle", 6, want=[0, -16, 0])["clip"] == "Run"
    assert at(db, clips, "Idle", 6, want=[0, 6, 0])["clip"] == "Back"
    assert at(db, clips, "Idle", 6, want=[0, 0, 0]) == {"clip": "Idle", "frame": 7, "jump": False}
    # A STOP: walking or running, the player lets go
    assert at(db, clips, "Walk", 6, want=[0, 0, 0])["clip"] == "Idle"
    assert at(db, clips, "Run", 6, want=[0, 0, 0])["clip"] == "Idle"
    # A CHANGE OF DIRECTION: forward to back (the two clips hold the very same poses: only the travel tells them apart)
    r = at(db, clips, "Walk", 6, want=[0, 6, 0])
    assert r["clip"] == "Back" and r["jump"] is True
    assert at(db, clips, "Back", 6, want=[0, -8, 0])["clip"] == "Walk"
    # faster / slower
    assert at(db, clips, "Walk", 6, want=[0, -16, 0])["clip"] == "Run"
    assert at(db, clips, "Run", 6, want=[0, -8, 0])["clip"] == "Walk"
    # going where it already goes: it stays, and that is no jump
    for name, want in (("Walk", [0, -8, 0]), ("Run", [0, -16, 0]), ("Back", [0, 6, 0])):
        r = at(db, clips, name, 6, want=want)
        assert r["clip"] == name and r["jump"] is False
    # WHERE IT GOES FIRST (the two asks the summed rule got wrong: it weighed the idle's pose against 6 studs a second)
    assert at(db, clips, "Idle", 6, want=[0, -6, 0])["clip"] == "Walk"
    assert at(db, clips, "Walk", 6, want=[0, -2, 0])["clip"] == "Idle"
    # a small miss does not leave the clip (a stick a little off its line): `stay` holds it
    assert at(db, clips, "Walk", 6, want=[0.5, -7.5, 0])["clip"] == "Walk"
    # a database baked before steering (no travel in it) ignores the ask instead of failing
    old = {k: v for k, v in db.items() if k not in ("traj", "traj_weight", "speed", "turn")}
    assert at(old, clips, "Idle", 6, want=[0, -8, 0])["clip"] == "Idle"


def test_the_clips_the_game_allows_now(tmp_path):
    clips = gaits()
    db = MT.motion_set(SET, built(tmp_path, clips))
    fwd = [0, -16, 0]
    assert at(db, clips, "Idle", 6, want=fwd, only={"Idle": True, "Walk": True})["clip"] == "Walk"      # no run: the walk
    assert at(db, clips, "Idle", 6, want=fwd, only={"Idle": True, "Back": True})["clip"] == "Idle"
    # the clip being played is no longer allowed: it gets no `stay`, the body leaves it
    r = at(db, clips, "Run", 6, want=fwd, only={"Idle": True, "Walk": True})
    assert r["clip"] == "Walk" and r["jump"] is True
    # nothing of the set is allowed: what plays goes on
    assert at(db, clips, "Walk", 6, want=fwd, only={}) == {"clip": "Walk", "frame": 7, "jump": False}
    assert at(db, clips, "Walk", 6, want=fwd, only={"Ghost": True})["clip"] == "Walk"
    # a clip that does not loop still plays its last frames out, whatever is asked or allowed
    kesa = T.loved("Katana1Kesa")
    d2 = built(tmp_path / "k" if (tmp_path / "k").mkdir() is None else tmp_path, {**clips, "Kesa": kesa})
    db2 = MT.motion_set({"clips": ["Idle", "Walk", "Kesa"], "rest": "Idle"}, d2)
    last = db2["clips"]["Kesa"]["frames"] - 1
    assert MT.motion_step(db2, None, T.pose_of(kesa, 40), 1 / 30, ["Kesa", last + 0.5], [0, -8, 0], {"Walk": True}) == {
        "clip": "Kesa", "frame": last, "jump": False}


# ---------------------------------------------------------------- the game's matcher, and the blend route
def test_where_the_player_wants_to_go_in_the_bodys_own_frame(tmp_path):
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    r = math.sqrt(0.5)
    qs = [{"wanted": [0, -1, 0, -1, 16]},            # facing -Z, pushing -Z: ahead at full speed
          {"wanted": [1, 0, 0, -1, 16]},             # pushing +X: to the right
          {"wanted": [0, 1, 0, -1, 8]},              # pushing +Z: back
          {"wanted": [0, -1, 1, 0, 16]},             # facing +X, pushing -Z: that is to its LEFT
          {"wanted": [0, -0.5, 0, -3, 16]},          # half a push; a facing that is not unit length
          {"wanted": [0, 0, 0, -1, 16, 0.3]},        # no push: nothing wanted, no turn
          {"wanted": [-1, 0, 0, -1, 16, 0.5]},       # pushing to its left, to face that way in half a second
          {"wanted": [r, -r, 0, -1, 16, 0.25]},      # ahead and to the right
          {"wanted": [0, -1, 0, 0, 16]}]             # no facing: nothing can be said
    got = T.ask(tmp_path, {"kind": "motion"}, qs)
    want = [[0, -16, 0], [16, 0, 0], [0, 8, 0], [-16, 0, 0], [0, -8, 0], [0, 0, 0], [-16, 0, math.pi], [16 * r, -16 * r, -math.pi],
            [0, 0, 0]]
    assert np.allclose(got, want, atol=1e-9)


def test_the_games_steered_search_is_the_builds_and_agrees_with_the_blend_route(tmp_path):
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    clips = gaits()
    db = MT.motion_set(SET, built(tmp_path, clips))
    rng = np.random.default_rng(15)
    qs = []
    for name in SET["clips"]:
        c = clips[name]
        for want in (None, [0, -8, 0], [0, -16, 0], [0, 0, 0], [0, 6, 0], [3, -3, 0.5], [0, -6, 0], [0, -2, 0]):
            for only in (None, {"Idle": True, "Walk": True}, {}):
                q = {"step": True, "prev": T.pose_of(c, 5), "pose": T.pose_of(c, 6), "dt": 1 / 30, "current": [name, 6]}
                if want is not None:
                    q["want"] = want
                if only is not None:
                    q["only"] = only
                qs.append(q)
    for _ in range(12):
        a = {j: rng.normal(size=4).tolist() for j in db["joints"]}
        b = {j: rng.normal(size=4).tolist() for j in db["joints"]}
        qs.append({"step": True, "prev": a, "pose": b, "dt": float(rng.uniform(0.01, 0.2)),
                   "current": [str(rng.choice(SET["clips"])), float(rng.uniform(0, 15))],
                   "want": rng.uniform(-16, 16, 3).tolist(), "only": {str(rng.choice(SET["clips"])): True, "Idle": True}})
    build = [MT.motion_step(db, q.get("prev"), q["pose"], q["dt"], q.get("current"), q.get("want"), q.get("only")) for q in qs]
    # (an empty "only" reaches the game as an empty table, as it reaches the build as an empty set)
    assert T.ask(tmp_path, db, qs) == build
    # the raw search too
    pose, vel = MT.query_at(db, clips["Walk"], 6)
    raw = [{"pose": pose, "vel": vel, "current": ["Walk", 6], "want": w, **({"only": o} if o is not None else {})}
           for w in ([0, 6, 0], [0, -16, 0], [0, 0, 0]) for o in (None, {"Idle": True})]
    assert T.ask(tmp_path, db, raw) == [MT.motion_match(db, q["pose"], q["vel"], q["current"], q["want"], q.get("only")) for q in raw]
    # THE BLEND ROUTE on the same asks (src/kit/AnimBlend.weights): the clip it gives the most weight is the clip the
    # steered search goes to - a start, a stop, faster, back
    meta = {n: {"speed": (clips[n].get("locomotion") or {}).get("speed")} for n in SET["clips"]}
    meta["Back"]["speed"] = 6
    blend = {"idle": "Idle", "walk": "Walk", "run": "Run", "back": "Back"}
    asks = [("Idle", [0, -1], 8), ("Idle", [0, -1], 16), ("Walk", [0, 0], 0), ("Run", [0, -1], 0.2), ("Walk", [0, 1], 6),
            ("Walk", [0, -1], 16), ("Back", [0, -1], 8)]
    tops = T.ask(tmp_path, db, [{"blend": {"set": blend, "meta": meta, "move": m, "speed": s}} for _, m, s in asks])
    for (frm, move, speed), top in zip(asks, tops):
        want = [move[0] * speed, move[1] * speed, 0]
        assert at(db, clips, frm, 6, want=want)["clip"] == top, (frm, move, speed, top)


def test_a_full_set_is_searched_within_the_time_a_look_has(tmp_path):
    """the search's cost, MEASURED on this machine's own interpreter (not in Roblox): a set at its row budget, one
    steered look. The budget is what keeps this bounded; what it costs in a game is Studio's to measure"""
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    import time
    clips = gaits()
    db = MT.motion_set(SET, built(tmp_path, clips))
    reps = MT.MAX_ROWS // len(db["rows"])
    big = dict(db, rows=db["rows"] * reps, index=db["index"] * reps, traj=db["traj"] * reps)
    assert MT.MAX_ROWS - len(db["rows"]) < len(big["rows"]) <= MT.MAX_ROWS
    pose, vel = MT.query_at(db, clips["Walk"], 6)
    q = {"pose": pose, "vel": vel, "current": ["Walk", 6], "want": [0, -8, 0]}
    t0 = time.perf_counter()
    T.ask(tmp_path, big, [q])
    one = time.perf_counter() - t0
    t0 = time.perf_counter()
    T.ask(tmp_path, big, [q] * 21)
    many = time.perf_counter() - t0
    per_look = max(0.0, many - one) / 20
    print(f"steered search over {len(big['rows'])} rows: {per_look * 1000:.2f} ms a look (lune, this machine)")
    assert per_look < 0.05            # under 50 ms: a look happens every 100 ms by default


# ---------------------------------------------------------------- what the one review found (2026-11-15)
def test_a_move_in_flight_is_not_steered_and_steering_never_starts_one(tmp_path):
    if not shutil.which("lune"):
        pytest.skip("lune is not on this machine's path")
    clips = gaits()
    kesa = T.loved("Katana1Kesa")
    dash = dict(T.travelling(T.loved("Katana3Makko"), studs=30.0), name="Dash")
    d = built(tmp_path, {**clips, "Kesa": kesa, "Dash": dash})
    db = MT.motion_set({"clips": ["Idle", "Walk", "Run", "Kesa", "Dash"], "rest": "Idle"}, d)
    # the scales are the LOOPS' (16 studs a second, the run), not the dash's 50-odd: steering still works beside it
    assert db["speed"] == 16.0 and max(math.hypot(t[0], t[1]) for t in db["traj"]) > 40
    assert at(db, clips, "Idle", 6, want=[0, -8, 0])["clip"] == "Walk"
    assert at(db, clips, "Walk", 6, want=[0, 0, 0])["clip"] == "Idle"
    # A MOVE IN FLIGHT: the kesa plays, the player holds forward - the swing goes on (it was cut before the fix)
    qs = []
    for f in (4, 8, 12, 16):
        q = {"step": True, "prev": T.pose_of(kesa, 2 * f - 2), "pose": T.pose_of(kesa, 2 * f), "dt": 1 / 30, "current": ["Kesa", f]}
        plain = MT.motion_step(db, q["prev"], q["pose"], q["dt"], q["current"])
        for want in ([0, -16, 0], [0, 6, 0], [0, 0, 0]):
            steered = MT.motion_step(db, q["prev"], q["pose"], q["dt"], q["current"], want)
            assert steered == plain and steered["clip"] == "Kesa"
            qs.append({**q, "want": want})
    # STEERING NEVER STARTS A MOVE: an ask that fits the dash (ahead, very fast) goes to the run, not the dash ...
    fast = [0, -50, 0]
    assert at(db, clips, "Idle", 6, want=fast)["clip"] == "Run"
    # ... unless the game names it
    named = at(db, clips, "Idle", 6, want=fast, only={"Idle": True, "Run": True, "Dash": True})
    assert named["clip"] == "Dash"
    # an allowed map's FALSE is not allowed, on both sides; a number that is not one is no ask
    assert at(db, clips, "Idle", 6, want=[0, -16, 0], only={"Idle": True, "Walk": True, "Run": False})["clip"] == "Walk"
    assert at(db, clips, "Walk", 6, want=[float("nan"), 0, 0], only={"Walk": True, "Run": True}) == at(
        db, clips, "Walk", 6, only={"Walk": True, "Run": True})
    for name, want, only in (("Idle", fast, None), ("Idle", fast, {"Idle": True, "Run": True, "Dash": True}),
                             ("Idle", [0, -16, 0], {"Idle": True, "Walk": True, "Run": False})):
        c = clips[name]
        qs.append({"step": True, "prev": T.pose_of(c, 5), "pose": T.pose_of(c, 6), "dt": 1 / 30, "current": [name, 6], "want": want,
                   **({"only": only} if only is not None else {})})
    assert T.ask(tmp_path, db, qs) == [MT.motion_step(db, q["prev"], q["pose"], q["dt"], q["current"], q["want"], q.get("only")) for q in qs]


def test_a_spin_turns_the_way_it_turns_and_a_root_of_another_length_is_refused():
    kesa = T.loved("Katana1Kesa")
    n, fps = len(kesa["times"]), kesa["fps"]
    spin = copy.deepcopy(kesa)
    spin["root"] = []
    for i in range(n):
        a = math.radians(15.0 * i) / 2                           # 900 degrees a second, to the left
        spin["root"].append([0, math.sin(a), 0, math.cos(a), 0, 0, 0])
    going = MT.travel(spin)
    assert all(g[2] == pytest.approx(math.radians(15.0) * fps, rel=1e-6) for g in going[: n - 1])
    short = copy.deepcopy(spin)
    short["root"] = short["root"][:-3]
    with pytest.raises(ValueError, match="its root track has"):
        MT.travel(short)
    # a clip's own "travel" that is not one is worked out again, not trusted
    bad = dict(G.generate({"name": "Walk", "kind": "walk"}))
    bad["travel"] = [[0, 1]] * len(bad["times"])
    db = MT.motion_db([bad, G.generate({"name": "Run", "kind": "run"})])
    assert db["traj"][0] == [0.0, -8.0, 0.0]


def test_a_new_clip_is_the_one_that_misses_least_and_the_playing_one_is_kept_inside_the_bar(tmp_path):
    # walk 8, a jog at exactly 10 (the walk's poses, its travel said by the set), run 16
    clips = gaits()
    jog = dict(copy.deepcopy(clips["Walk"]), name="Jog")
    jog.pop("locomotion")
    clips["Jog"] = jog
    d = built(tmp_path, clips)
    db = MT.motion_set({"clips": ["Idle", "Walk", "Jog", "Run"], "rest": "Idle", "travel": {"Jog": [0, -10]}}, d)
    # from the idle, an ask of 10 enters the JOG (inside a fixed bar the walk, 2 studs a second off, won on its pose)
    assert at(db, clips, "Idle", 6, want=[0, -10, 0])["clip"] == "Jog"
    assert at(db, clips, "Idle", 6, want=[0, -8.5, 0])["clip"] == "Walk"
    # the clip being played is kept while it is within the bar of the least miss (0.08 of 16 = 1.28 studs a second) ...
    assert at(db, clips, "Walk", 6, want=[0, -9.5, 0])["clip"] == "Walk"       # the walk is 1.5 off, the jog 0.5: 1.0 apart
    # ... and left when it is further off than that
    assert at(db, clips, "Walk", 6, want=[0, -10, 0])["clip"] == "Jog"          # 2.0 apart
    assert at(db, clips, "Jog", 6, want=[0, -9, 0])["clip"] == "Jog" and at(db, clips, "Jog", 6, want=[0, -8.2, 0])["clip"] == "Walk"
    assert at(db, clips, "Run", 6, want=[0, -10, 0])["clip"] == "Jog"
