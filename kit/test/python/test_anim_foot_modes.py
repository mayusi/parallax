"""kit/anim/foot_modes.py - what each foot is doing (plant, pivot, slide, airborne) and the slides a move MEANS
(the owner's older list, AN-26): a said slide is not judged, an unsaid one fails at the ordinary bar, a said slide
that is not there is refused. On a cut the owner loved (generated in memory, read only), its feet moved on purpose."""
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
sys.path.insert(0, HERE)
import clip as C                 # noqa: E402
import foot_modes as FM          # noqa: E402
import metrics as MT             # noqa: E402
import strike as S               # noqa: E402
import test_anim_collide as T    # noqa: E402

RIG = C.load_rig("r6")


@pytest.fixture(scope="module")
def kesa():
    return T.made("loved", "Katana1Kesa")


def skidding(clip, a=20, b=30, studs=4.0, foot="Right Leg"):
    """the cut with one foot dragged `studs` along the floor over frames a..b (and left there). The leg's slide is in
    its parent's axes (the Torso's): the drag is level in the WORLD, so the foot stays on the floor"""
    c = copy.deepcopy(clip)
    for i in range(a, len(c["times"])):
        u = min(1.0, (i - a) / (b - a))
        Rt = C.fk(RIG, C.character_transforms(c, RIG, i))["Torso"][:3, :3]
        d = Rt.T @ np.array([0.0, 0.0, -studs * u])
        f = c["joints"][foot]["frames"][i]
        c["joints"][foot]["frames"][i] = f[:4] + [f[4] + float(d[0]), f[5] + float(d[1]), f[6] + float(d[2])]
    return c


def turning(clip, a=10, b=40, deg=60.0, foot="Left Leg"):
    """the cut with one leg turned on the spot about its own long axis over frames a..b"""
    import derive as D
    c = copy.deepcopy(clip)
    for i in range(a, len(c["times"])):
        u = min(1.0, (i - a) / (b - a))
        f = c["joints"][foot]["frames"][i]
        h = math.radians(deg * u) / 2
        c["joints"][foot]["frames"][i] = list(D.qmul(np.array(f[:4]), np.array([0, math.sin(h), 0, math.cos(h)]))) + list(f[4:7])
    return c


def problems(clip):
    return C.metrics(clip, RIG)["problems"]


def test_a_loved_cut_stands_on_planted_feet(kesa):
    r = FM.read(kesa)
    assert set(r["feet"]) == {"Right Leg", "Left Leg"} and r["bar"] == C.GATES["foot_slide"]
    for rows in r["feet"].values():
        assert [x["mode"] for x in rows] == ["plant"] and rows[0]["from"] == 0 and rows[0]["to"] == len(kesa["times"]) - 1
    assert FM.words(r, "Kesa").endswith("(0 pivot(s), 0 said slide(s))")


def test_a_dragged_foot_is_a_slide_with_its_stretch_and_an_unsaid_one_fails(kesa):
    bad = skidding(kesa)
    r = FM.read(bad)
    rows = r["feet"]["Right Leg"]
    assert [x["mode"] for x in rows] == ["plant", "slide", "plant"]
    slide = rows[1]
    assert slide["from"] in (19, 20) and slide["to"] in (30, 31) and 3.8 < slide["studs"] < 4.6
    assert slide["worst"] > r["bar"] and slide["said"] is False
    assert [x["mode"] for x in r["feet"]["Left Leg"]] == ["plant"]          # the other foot is not touched
    w = FM.words(r, "Kesa")
    assert "SLIDES UNSAID: the right foot moves 4." in w and " studs over frames" in w
    found = [p for p in problems(bad) if p.startswith("foot slide")]
    assert len(found) == 1 and '"slides"' in found[0] and "not passed by a higher bar" in found[0]


def test_a_slide_the_move_says_is_not_judged_and_the_rest_of_the_clip_still_is(kesa):
    said = dict(skidding(kesa), slides=[{"foot": "Right Leg", "from": 19 / 60, "to": 31 / 60, "kind": "skid"}])
    assert not [p for p in problems(said) if "foot" in p or "feet" in p]
    m = C.metrics(said, RIG)["feet"]
    assert 3.8 < m["said_slide_studs"] < 4.6 and m["slide_max_studs_frame"] <= C.GATES["foot_slide"]
    r = FM.read(said)
    assert [x["said"] for x in r["feet"]["Right Leg"] if x["mode"] == "slide"] == [True]
    assert [x["mode"] for x in m["modes"]["Right Leg"]] == ["plant", "slide", "plant"]
    # the bar is not raised: a SECOND slide outside the said stretch, and the other foot's, still fail
    twice = dict(skidding(said, 40, 46, 3.0), slides=said["slides"])
    assert [p for p in problems(twice) if p.startswith("foot slide")]
    other = dict(skidding(kesa, foot="Left Leg"), slides=said["slides"])
    assert [p for p in problems(other) if p.startswith("foot slide")]
    both = dict(skidding(skidding(kesa), foot="Left Leg"), slides=[{"foot": "both", "from": 19 / 60, "to": 31 / 60, "kind": "drag"}])
    assert not [p for p in problems(both) if "foot" in p or "feet" in p]


def test_a_slide_that_is_said_and_not_there_is_refused(kesa):
    lazy = dict(kesa, slides=[{"foot": "both", "from": 0.0, "to": 0.8, "kind": "skid"}])       # "switch my feet off"
    found = [p for p in problems(lazy) if p.startswith("feet:")]
    assert len(found) == 2 and "is not there: on the floor the foot moves 0." in found[0] and "take it out" in found[0]
    late = dict(skidding(kesa), slides=[{"foot": "Right Leg", "from": 5.0, "to": 6.0, "kind": "skid"}])
    found = problems(late)
    assert any("covers no two frames of the clip" in p for p in found) and any(p.startswith("foot slide") for p in found)


@pytest.mark.parametrize("slides, why", [
    ("skid", '"slides" is a list of'),
    ([{"foot": "Tail", "from": 0, "to": 1, "kind": "skid"}], "a slide names its foot"),
    ([{"foot": "Right Leg", "from": 0, "to": 1, "kind": "moonwalk"}], "a slide says its kind"),
    ([{"foot": "Right Leg", "from": 0.4, "to": 0.2, "kind": "skid"}], "the end after the start"),
    ([{"foot": "Right Leg", "from": "soon", "to": 1, "kind": "skid"}], "seconds from the clip's start"),
    (["x"], '"slides" is a list of'),
])
def test_slides_that_cannot_be_read_are_a_problem_never_a_pass(kesa, slides, why):
    with pytest.raises(ValueError, match=why):
        FM.said(dict(kesa, slides=slides))
    found = [p for p in problems(dict(skidding(kesa), slides=slides)) if "cannot be read" in p]
    assert len(found) == 1 and why.strip('"')[:12] in found[0]
    assert [p for p in problems(dict(skidding(kesa), slides=slides)) if p.startswith("foot slide")]      # nothing is excused


def test_a_foot_that_turns_on_the_spot_is_a_pivot_and_a_lifted_one_is_airborne(kesa):
    r = FM.read(turning(kesa))
    modes = [x["mode"] for x in r["feet"]["Left Leg"]]
    assert "pivot" in modes and "slide" not in modes
    pivot = [x for x in r["feet"]["Left Leg"] if x["mode"] == "pivot"][0]
    assert pivot["turn_deg"] >= FM.PIVOT and pivot["worst"] <= r["bar"]
    assert not [p for p in problems(turning(kesa)) if p.startswith("foot slide")]            # a pivot is not a slide
    up = copy.deepcopy(kesa)
    for i in range(15, 30):
        f = up["joints"]["Right Leg"]["frames"][i]
        up["joints"]["Right Leg"]["frames"][i] = f[:4] + [f[4], f[5] + 0.5, f[6]]
    rows = FM.read(up)["feet"]["Right Leg"]
    assert [x["mode"] for x in rows] == ["plant", "airborne", "plant"] and rows[1]["from"] == 15 and rows[1]["to"] == 29


def test_a_move_says_its_slides_and_the_clip_carries_them():
    with open(os.path.join(T.FAULTS, "loved", "Katana1Kesa.move.json"), encoding="utf-8") as fh:
        move = json.load(fh)
    move["slides"] = [{"foot": "Right Leg", "from": 0.3, "to": 0.5, "kind": "skid"}]
    clip = S.generate(move)[0]
    assert clip["slides"] == move["slides"]
    assert "slides" not in S.generate({k: v for k, v in move.items() if k != "slides"})[0]


def test_the_command_and_the_survey(kesa, tmp_path, capsys):
    good, bad, said = tmp_path / "good.clip.json", tmp_path / "bad.clip.json", tmp_path / "said.clip.json"
    good.write_text(json.dumps(kesa), encoding="utf-8")
    bad.write_text(json.dumps(skidding(kesa)), encoding="utf-8")
    said.write_text(json.dumps(dict(skidding(kesa), gate={"foot_slide": 10, "why_foot_slide": "it skids"}, name="Raised")), encoding="utf-8")
    capsys.readouterr()
    assert FM.main([str(good)]) == 0
    assert FM.main([str(bad)]) == 1
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "SLIDES UNSAID" in out["summary"] and '"slides"' in out["next_action"] and out["feet"]["Right Leg"][1]["mode"] == "slide"
    assert FM.main(["survey", str(tmp_path)]) == 0
    s = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    # (the loved cut itself carries a raised bar - 0.227, "loved R6 sword slashes" - so all three raise it; one is off)
    assert s["clips"] == 3 and s["raise_the_bar"] == 3 and s["to_a_stud_or_more"] == 1 and s["with_a_reason"] == 3 and s["say_their_slides"] == 0
    # the build's motion gates (kit/anim/metrics.py) carry it
    ok = tmp_path / "ok.clip.json"
    ok.write_text(json.dumps(dict(skidding(kesa), slides=[{"foot": "Right Leg", "from": 19 / 60, "to": 31 / 60, "kind": "skid"}])), encoding="utf-8")
    assert MT.main([str(ok)]) == 0 and MT.main([str(bad)]) == 1


# ---------------------------------------------------------------- the one review, 2026-11-15
def test_a_stretch_wider_than_its_slide_is_refused_one_slide_does_not_excuse_a_second(kesa):
    n = len(kesa["times"])
    whole = [{"foot": "Right Leg", "from": 0.0, "to": (n - 1) / 60, "kind": "skid"}]
    wide = [p for p in problems(dict(skidding(kesa), slides=whole)) if p.startswith("feet:")]
    assert len(wide) == 1 and "is wider than the slide: the foot slides over frames 20-30" in wide[0] and "say that stretch" in wide[0]
    twice = skidding(skidding(kesa), 40, 46, 3.0)                # the same foot slides twice; one stretch said over both
    found = [p for p in problems(dict(twice, slides=[{"foot": "Right Leg", "from": 20 / 60, "to": 46 / 60, "kind": "skid"}])) if p.startswith("feet:")]
    assert len(found) == 1 and "frame(s) in between where it does not" in found[0] and "one slide a row" in found[0]
    two = [{"foot": "Right Leg", "from": 20 / 60, "to": 30 / 60, "kind": "skid"}, {"foot": "Right Leg", "from": 40 / 60, "to": 46 / 60, "kind": "drag"}]
    assert not [p for p in problems(dict(twice, slides=two)) if "foot" in p or "feet" in p]


def test_a_foot_in_the_air_is_not_sliding(kesa):
    up = copy.deepcopy(kesa)
    for i in range(15, 30):                                      # lifted half a stud and carried 4 studs forward in the air
        Rt = C.fk(RIG, C.character_transforms(up, RIG, i))["Torso"][:3, :3]
        d = Rt.T @ np.array([0.0, 0.5, -4.0 * (i - 15) / 14])
        f = up["joints"]["Right Leg"]["frames"][i]
        up["joints"]["Right Leg"]["frames"][i] = f[:4] + [f[4] + float(d[0]), f[5] + float(d[1]), f[6] + float(d[2])]
    found = FM.stale(dict(up, slides=[{"foot": "Right Leg", "from": 15 / 60, "to": 29 / 60, "kind": "skid"}]))
    assert len(found) == 1 and "is not there: on the floor the foot moves" in found[0]


def test_a_stretch_said_by_its_frames_covers_its_end_frames(kesa):
    c = skidding(kesa)
    times = [round(i / 60, 6) for i in range(len(c["times"]))]   # (how a built clip stores its times)
    said = dict(c, times=times, slides=[{"foot": "Right Leg", "from": 20 / 60, "to": 30 / 60, "kind": "skid"}])
    cov = FM.meant(said, len(times), times)["Right Leg"]
    assert cov[20] and cov[30] and not cov[19] and not cov[31]
    assert not [p for p in problems(said) if "foot" in p or "feet" in p]
    assert [x["said"] for x in FM.read(said)["feet"]["Right Leg"] if x["mode"] == "slide"] == [True]


def test_a_walk_cycle_says_no_slides_and_cannot_switch_its_skate_check_off(kesa):
    walk = dict(skidding(kesa), locomotion={"speed": 8.0, "direction": [0, 0, -1]})
    plain = [p for p in problems(walk) if p.startswith("foot sk")]
    assert plain                                                 # its feet are held to the ground's speed
    n = len(kesa["times"])
    said = dict(walk, slides=[{"foot": "both", "from": 0.0, "to": (n - 1) / 60, "kind": "skid"}])
    found = problems(said)
    assert [p for p in found if p.startswith("foot sk")] == plain          # ... said or not
    assert any("it is an in-place locomotion clip" in p and "take them out" in p for p in found)
    modes = {x["mode"] for rows in FM.read(walk)["feet"].values() for x in rows}
    assert "slide" not in modes and "stance" in modes


def test_a_raised_bar_does_not_make_a_real_slide_not_there(kesa):
    raised = dict(skidding(kesa), gate={"foot_slide": 10}, slides=[{"foot": "Right Leg", "from": 20 / 60, "to": 30 / 60, "kind": "skid"}])
    assert FM.stale(raised, RIG, 10) == [] and FM.own_bar(raised) == C.GATES["foot_slide"]
    assert not [p for p in problems(raised) if p.startswith("feet:")]
    assert FM.own_bar(dict(kesa, gate={"foot_slide": 0.05})) == 0.05          # a LOWER bar of its own is its bar


def test_a_recipe_that_changes_time_drops_the_sources_slides_and_says_so(kesa, tmp_path, monkeypatch):
    import derive as D
    src = dict(skidding(kesa), slides=[{"foot": "Right Leg", "from": 20 / 60, "to": 30 / 60, "kind": "skid"}])
    monkeypatch.setattr(D, "load_clip", lambda name: copy.deepcopy(src))
    out = D.derive({"name": "Kept", "from": "Base", "ops": [{"op": "mirror"}]})
    kept = out[0] if isinstance(out, tuple) else out
    assert kept["slides"] == src["slides"]                       # nothing moved in time: they stand
    out = D.derive({"name": "Slow", "from": "Base", "ops": [{"op": "retime", "speed": 0.5}]})
    slow = out[0] if isinstance(out, tuple) else out
    assert "slides" not in slow
    again = [{"foot": "Right Leg", "from": 40 / 60, "to": 60 / 60, "kind": "skid"}]
    out = D.derive({"name": "Slow", "from": "Base", "slides": again, "ops": [{"op": "retime", "speed": 0.5}]})
    slow = out[0] if isinstance(out, tuple) else out
    assert slow["slides"] == again


def test_an_r15_clip_that_says_slides_is_told_where_they_are_read(kesa):
    r15 = C.load_rig("r15")
    note = "feet: the slides it says are read on the R6 clip (this one is R15)"
    clip = {"name": "X", "rig": "R15", "fps": 60, "times": [0.0, 1 / 60], "joints": {}, "events": [],
            "slides": [{"foot": "Right Leg", "from": 0, "to": 0.01, "kind": "skid"}]}
    assert note in C.metrics(clip, r15)["notes"]

