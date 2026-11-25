"""kit/anim/finish.py - ONE finishing contract for every route (the owner's limitations list 2026-11-15, A-R09): the
same controls, in the same order, with the same things kept exact and the same numbers reported, whatever made the
clip. Three routes' clips, generated in memory (read only): a procedural move (a cut the owner loved), a kit gait,
and a dense clip as an import hands one over."""
import copy
import json
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import finish as F       # noqa: E402
import gait_r6 as G      # noqa: E402
import strike as S       # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")


def move_clip():
    with open(LOVED, encoding="utf-8") as fh:
        return S.generate(json.load(fh))[0]


def imported(n=61, fps=30):
    """a dense clip as an import hands one over: no weapon, a nod and an arm swing, a Hit two thirds in"""
    def q(axis, deg):
        h = math.radians(deg) / 2
        v = [0.0, 0.0, 0.0]
        v[axis] = math.sin(h)
        return [*v, math.cos(h), 0.0, 0.0, 0.0]
    u = [i / (n - 1) for i in range(n)]
    return {"schema": 1, "name": "Imported", "rig": "R6", "fps": fps, "loop": False, "times": [i / fps for i in range(n)],
            "events": [{"name": "Hit", "t": 40 / fps}],
            "joints": {"Head": {"frames": [q(0, 20 * math.sin(2 * math.pi * x)) for x in u]},
                       "Right Arm": {"frames": [q(0, 120 * (1 - math.cos(math.pi * min(1.0, x * 1.5))) / 2) for x in u]},
                       "Torso": {"frames": [q(1, 30 * x) for x in u]}}}


def shaken(clip, joint="Head", deg=1.5, seed=4):
    """the clip with its joint given `deg` degrees of noise a frame (a capture that chatters); the ends and the Hit kept"""
    c = copy.deepcopy(clip)
    rng = np.random.default_rng(seed)
    fps, n = c["fps"], len(c["times"])
    keep = {0, n - 1, *[round(e["t"] * fps) for e in c["events"] if e["name"] == "Hit"]}
    for i in range(n):
        if i in keep:
            continue
        f = np.array(c["joints"][joint]["frames"][i], float)
        ax = rng.normal(size=3)
        ax /= np.linalg.norm(ax)
        h = math.radians(deg * rng.normal()) / 2
        d = np.array([*(math.sin(h) * ax), math.cos(h)])
        x1, y1, z1, w1 = d
        x2, y2, z2, w2 = f[:4]
        f[:4] = [w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                 w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2, w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2]
        c["joints"][joint]["frames"][i] = f.tolist()
    return c


ROUTES = {"a procedural move": move_clip, "a gait": lambda: G.generate({"name": "Walk", "kind": "walk"}), "an import": imported}


# ---------------------------------------------------------------- one contract, every route
@pytest.mark.parametrize("route", list(ROUTES))
def test_the_same_finish_is_applied_the_same_way_whatever_made_the_clip(route):
    clip = ROUTES[route]()
    ask = {"filter": {"hz": 10, "joints": ["Head"]}, "velocity": {"max_deg_s": 5000}, "overshoot": {"max_deg": 60}}
    noisy = dict(shaken(clip), finish=ask)
    done = F.apply(noisy)
    assert done is not noisy and done["finished"] == F.stamp(ask) and len(done["finish_log"]) == 3
    assert [x.split(":")[0] for x in done["finish_log"]] == ["filter", "velocity", "overshoot"]      # always this order
    assert F.kept(noisy, done) is None
    # THE CONTRACT: its length, its events, and the pose at both ends and every Hit are the route's own
    assert done["times"] == noisy["times"] and done["events"] == noisy["events"]
    n, fps = len(clip["times"]), clip["fps"]
    for i in {0, n - 1, *[round(e["t"] * fps) for e in clip.get("events") or [] if e["name"] == "Hit"]}:
        for j in clip["joints"]:
            assert np.allclose(done["joints"][j]["frames"][i], noisy["joints"][j]["frames"][i], atol=1e-6), (j, i)
    # the filter did what it is for: the shaken head is smoother, nothing else was touched
    a, b = F.measure(noisy)["joints"], F.measure(done)["joints"]
    assert b["Head"]["roughness"] < 0.85 * a["Head"]["roughness"]      # (every event is a kept moment: nothing is smoothed there)
    for j in clip["joints"]:
        if j != "Head":
            assert done["joints"][j]["frames"] == noisy["joints"][j]["frames"]
    # THE SAME NUMBERS for every route's clip
    assert set(b["Head"]) == {"peak_deg_s", "peak_frame", "roughness", "overshoot_deg"}
    # finished once: the stamped clip is handed back as it is, and a changed ask cannot be laid over it
    assert F.apply(done) is done
    with pytest.raises(ValueError, match="finished for another \"finish\""):
        F.apply(dict(done, finish={"filter": {"hz": 6}}))


def test_a_joint_that_turns_too_fast_is_brought_under_the_cap_or_the_finish_is_refused():
    clip = shaken(imported(), "Head", 4.0)
    was = F.measure(clip)["joints"]["Head"]["peak_deg_s"]
    cap = 0.6 * was
    done = F.apply(dict(clip, finish={"velocity": {"max_deg_s": cap, "joints": ["Head"]}}))
    assert F.measure(done)["joints"]["Head"]["peak_deg_s"] <= cap < was
    assert "filtered down to" in done["finish_log"][0] and done["joints"]["Torso"] == clip["joints"]["Torso"]
    # nothing over the cap: nothing is filtered
    calm = F.apply(dict(imported(), finish={"velocity": {"max_deg_s": 5000}}))
    assert "(none was)" in calm["finish_log"][0] and calm["joints"] == imported()["joints"]
    # a cap no filter can reach: refused, with the joint, its speed and its frame
    with pytest.raises(ValueError, match=r"velocity: Right Arm still turns \d+ degrees a second at frame \d+ \(at most 5\)"):
        F.apply(dict(imported(), finish={"velocity": {"max_deg_s": 5, "joints": ["Right Arm"]}}))
    with pytest.raises(ValueError, match="names Tail, which this clip does not key"):
        F.apply(dict(imported(), finish={"velocity": {"max_deg_s": 500, "joints": ["Tail"]}}))


def test_the_overshoot_envelope_and_what_the_curve_tools_refuse_still_stand():
    kesa = move_clip()
    most = F.measure(kesa)["overshoot_deg"]
    assert most > 5                                               # the loved cut settles with some swing back
    assert "overshoot: within" in F.apply(dict(kesa, finish={"overshoot": {"max_deg": most + 1}}))["finish_log"][0]
    with pytest.raises(ValueError, match=r"overshoot: \w[\w ]* swings back out [\d.]+ degrees from where it settles"):
        F.apply(dict(kesa, finish={"overshoot": {"max_deg": most - 1}}))
    # a filter that takes a hand off the weapon, a stretch with the Hit inside it: the tools' own refusals
    with pytest.raises(ValueError, match="off the weapon"):
        F.apply(dict(kesa, finish={"filter": {"hz": 6, "joints": ["Right Arm"]}}))
    hit = next(e["t"] for e in kesa["events"] if e["name"] == "Hit")
    with pytest.raises(ValueError, match="Hit"):
        F.apply(dict(kesa, finish={"handles": [{"from": hit - 0.1, "to": hit + 0.1}]}))
    # handles on a stretch before the Hit: the spacing changes, the contract holds
    done = F.apply(dict(kesa, finish={"handles": [{"from": 0.05, "to": 0.3, "out": [0.5, 0.0], "in": [0.4, 1.0]}]}))
    assert F.kept(kesa, done) is None and done["joints"]["Torso"]["frames"][10] != kesa["joints"]["Torso"]["frames"][10]
    with pytest.raises(ValueError, match="a prop's clip is not finished"):
        F.apply(dict(imported(), prop="Chest", finish={"filter": {"hz": 10}}))


def test_what_breaks_the_contract_is_named():
    clip = imported()
    n = len(clip["times"])
    assert F.kept(clip, copy.deepcopy(clip)) is None
    moved = copy.deepcopy(clip)
    moved["events"][0]["t"] += 0.1
    assert F.kept(clip, moved) == "it moved or lost an event"
    for i, what in ((0, "first frame"), (n - 1, "last frame"), (40, "kept moment at frame 40")):
        bent = copy.deepcopy(clip)
        bent["joints"]["Head"]["frames"][i] = [0.1, 0, 0, math.sqrt(0.99), 0, 0, 0]
        assert F.kept(clip, bent) == f"it changed Head's pose at the {what}"
    flipped = copy.deepcopy(clip)                                 # the same turn said by its other quaternion: the same pose
    flipped["joints"]["Head"]["frames"][40] = [-v for v in clip["joints"]["Head"]["frames"][40][:4]] + [0.0, 0.0, 0.0]
    assert F.kept(clip, flipped) is None
    short = copy.deepcopy(clip)
    short["times"] = short["times"][:-1]
    assert F.kept(clip, short) == "it changed the clip's length or its frames' times"
    between = copy.deepcopy(clip)                                 # a frame that is no kept moment may change
    between["joints"]["Head"]["frames"][20] = [0.1, 0, 0, math.sqrt(0.99), 0, 0, 0]
    assert F.kept(clip, between) is None


def test_a_finish_that_cannot_be_read_is_refused():
    for ask, why in (("smooth", "\"finish\" is"), ({}, "\"finish\" is"), ({"polish": True}, "has no \"polish\""),
                     ({"filter": 8}, "\"filter\" is"), ({"velocity": {"max_deg_s": 0}}, "\"velocity\" is"),
                     ({"velocity": {"max_deg_s": True}}, "\"velocity\" is"), ({"handles": {"from": 0, "to": 1}}, "\"handles\" is a list"),
                     ({"handles": [{"from": 0}]}, "\"handles\" is a list"), ({"overshoot": {"max_deg": -1}}, "\"overshoot\" is"),
                     ({"overshoot": 12}, "\"overshoot\" is")):
        with pytest.raises(ValueError, match=why):
            F.apply(dict(imported(), finish=ask))
    assert F.stamp({"a": 1, "b": 2}) == F.stamp({"b": 2, "a": 1}) != F.stamp({"a": 1, "b": 3})


# ---------------------------------------------------------------- the gate and the commands
def test_a_clip_that_asks_for_a_finish_and_does_not_carry_it_fails_whatever_its_route(tmp_path, capsys):
    import metrics as MT
    ask = {"filter": {"hz": 10, "joints": ["Head"]}}
    for route, make in ROUTES.items():
        clip = make()
        out, why = F.gate(clip)
        assert why is None and out["applied"] is None and out["peak_deg_s"] > 0, route      # no ask: the numbers only
        out, why = F.gate(dict(clip, finish=ask))
        assert "asks for a finish" in why and "its route did not apply one" in why, route
        done = F.apply(dict(clip, finish=ask))
        out, why = F.gate(done)
        assert why is None and out["applied"] == done["finish_log"], route
        assert "finished for another ask" in F.gate(dict(done, finish={"filter": {"hz": 9}}))[1]
        assert "has no \"polish\"" in F.gate(dict(clip, finish={"polish": 1}))[1]
    assert F.gate(dict(imported(), prop="Chest")) == (None, None)
    # through the build's motion gates
    p = tmp_path / "Asks.clip.json"
    p.write_text(json.dumps(dict(imported(), name="Asks", finish=ask)), encoding="utf-8")
    assert MT.main([str(p)]) != 0
    capsys.readouterr()
    m = json.loads((tmp_path / "Asks.metrics.json").read_text(encoding="utf-8"))
    assert any("asks for a finish" in x for x in m["problems"]) and "finish" in m
    # the commands
    out = tmp_path / "out" / "Asks.finished.json"
    assert F.main(["apply", str(p), "--out", str(out)]) == 0
    v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert v["status"] == "pass" and "filter:" in v["summary"]
    assert json.loads(out.read_text(encoding="utf-8"))["finished"] == F.stamp(ask)
    assert F.main(["measure", str(out)]) == 0 and "fastest turn" in capsys.readouterr().out
    bad = tmp_path / "Bad.clip.json"
    bad.write_text(json.dumps(dict(imported(), finish={"overshoot": {"max_deg": 0}, "velocity": {"max_deg_s": 1}})), encoding="utf-8")
    assert F.main(["apply", str(bad), "--out", str(tmp_path / "x.json")]) == 1
    assert not (tmp_path / "x.json").exists() and "finish: velocity:" in capsys.readouterr().out


# ---------------------------------------------------------------- what the one review found (2026-11-15)
def test_the_controls_together_never_take_a_hand_off_the_weapon_or_pass_the_cap():
    kesa = move_clip()
    peak = F.measure(kesa)["joints"]["Right Arm"]["peak_deg_s"]
    # a cap on the arm that carries the sword: every filter that reaches it takes the hand off the blade - refused
    # (laid rung on rung, each judged against the last, this was accepted with the hand 0.24 studs off)
    with pytest.raises(ValueError, match="off the weapon|still turns"):
        F.apply(dict(kesa, finish={"velocity": {"max_deg_s": 0.9 * peak, "joints": ["Right Arm"]}}))
    # handles that make a stretch faster than the cap the same finish names: refused after the handles
    top = F.measure(kesa)["peak_deg_s"]
    with pytest.raises(ValueError, match="after the handles .* turns \\d+ degrees a second|twice as fast"):
        F.apply(dict(kesa, finish={"velocity": {"max_deg_s": top + 1}, "handles": [{"from": 0.05, "to": 0.3, "out": [0.9, 0.0], "in": [0.9, 0.0]}]}))
    # every event is a kept moment, and so are the times the filter keeps and the edges of a meant contact
    clip = imported()
    clip["events"] = [{"name": "Swing", "t": 20 / 30}, {"name": "Hit", "t": 40 / 30}]
    clip["contact"] = [{"a": "Right Arm", "b": "Torso", "from": 10 / 30, "to": 12 / 30}]
    noisy = dict(shaken(clip, "Head", 2.0), finish={"filter": {"hz": 6, "joints": ["Head"], "keep": [50 / 30], "soften": True}})
    done = F.apply(noisy)
    for i in (0, 10, 12, 20, 40, 50, 60):
        assert np.allclose(done["joints"]["Head"]["frames"][i], noisy["joints"]["Head"]["frames"][i], atol=1e-6), i
    bent = copy.deepcopy(noisy)
    bent["joints"]["Head"]["frames"][20] = [0.1, 0, 0, math.sqrt(0.99), 0, 0, 0]
    assert F.kept(noisy, bent) == "it changed Head's pose at the kept moment at frame 20"
    # an empty list comes back from the build's own step as an empty map: read as "none named"
    assert "velocity" in F.apply(dict(imported(), finish={"velocity": {"max_deg_s": 5000, "joints": {}}}))["finish_log"][0]


def test_a_clip_made_from_a_finished_clip_does_not_inherit_its_stamp():
    here = os.path.join(ROOT, "kit", "anim")
    for tool, marks in (("rearm.py", '"style", "finish", "finished", "finish_log")}'), ("feel.py", '"finish", "finished", "finish_log")}'),
                        ("warp.py", 'for k in ("finish", "finished", "finish_log"):')):
        with open(os.path.join(here, tool), encoding="utf-8") as fh:
            assert marks in fh.read(), tool
