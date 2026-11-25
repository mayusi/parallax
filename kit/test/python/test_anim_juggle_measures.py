"""Sample Game style v4 (owner 2026-10-27: "he starts throwing them around, while shooting them"): a juggle clip's
several "Shot" events are each measured on their own gun, its "Toss" / "Catch" events give the flight times and which
shots go off while the other gun is up, and a dossier check can hold for some of a family's clips only ("for")"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import grip as GR            # noqa: E402
import proc_dossier as PD    # noqa: E402
import strike as S           # noqa: E402
from test_anim_grip import MOVE   # noqa: E402

FP = {"build": {"builder": "fp_weapon"}}


def _clip(events):
    clip = S.generate(json.loads(json.dumps(MOVE)))[0]
    last = round(clip["times"][-1] * clip["fps"])
    GR.add_grip_left(clip, [{"f": 0, "ease": "linear", "left_gun": {"blade": [0, 0, 1]}},     # Onyx forward all along
                            {"f": last, "left_gun": {"blade": [0, 0, 1]}}])
    clip["events"] = events
    return clip


def _vals(c):
    fns, _ = PD.fp_measures(c, FP)
    return {k: f(None) for k, f in fns.items()}


def test_every_shot_is_measured_on_its_own_gun():
    c = _clip([{"name": "Shot", "t": 0.0, "value": "L"}, {"name": "Shot", "t": 0.2, "value": "L"}])
    v = _vals(c)
    assert v["shot_count"] == 2
    assert v["shots_aim_err_max_deg"] < 1e-3          # Onyx points straight down the line of fire on both shots
    c["events"].append({"name": "Shot", "t": 0.2, "value": "R"})   # Pearl follows the strike's sword: off the line
    assert _vals(c)["shots_aim_err_max_deg"] > 10


def test_tosses_flights_and_shots_in_the_air():
    c = _clip([{"name": "Shot", "t": 0.0, "value": "L"}, {"name": "Toss", "t": 0.05, "value": "R"},
               {"name": "Shot", "t": 0.2, "value": "L"}, {"name": "Shot", "t": 0.25, "value": "R"},
               {"name": "Catch", "t": 0.35, "value": "R"}, {"name": "Shot", "t": 0.38, "value": "R"}])
    v = _vals(c)
    assert abs(v["toss_flight_min_s"] - 0.3) < 1e-9 and abs(v["toss_flight_max_s"] - 0.3) < 1e-9
    assert v["shots_while_other_up"] == 1             # Onyx's second shot, Pearl up
    assert v["shots_from_a_gun_in_the_air"] == 1      # Pearl "fired" in the air: the game refuses that one


def test_a_check_can_hold_for_some_clips_only():
    ck = {"id": "x", "measure": "shot_count", "range": [2, 9], "why": "w", "for": ["GunJuggle*"]}
    assert PD.applies(ck, "GunJuggleUpR") and not PD.applies(ck, "GunTwirlR")
    assert PD.applies({"id": "y"}, "Anything")
    c = _clip([{"name": "Shot", "t": 0.0, "value": "L"}])
    c["name"] = "GunTwirlL"
    d = dict(FP, checks=[ck, {"id": "len", "measure": "clip_seconds", "range": [0, 9], "why": "w"}])
    r = PD.check(c, d)
    assert set(r["checks"]) == {"len"} and r["pass"]


def test_third_person_crosshair_ray_starts_at_the_camera():
    # Sample Game plays over the right shoulder: the crosshair's ray starts at the camera, 2.2 right / 0.9 up / 9 back
    c = _clip([{"name": "Shot", "t": 0.0, "value": "L"}])
    v = PD.fp_measures(c, {"build": {"builder": "fp_weapon", "tp_camera": [2.2, 0.9, 9.0]}})[0]
    assert 0.0 <= v["tp_center_blocked_share"](None) <= 1.0
    on_arm = PD.fp_measures(c, {"build": {"builder": "fp_weapon", "tp_camera": [1.5, -1.5, 9.0]}})[0]   # through the arm
    assert on_arm["tp_center_blocked_share"](None) > v["tp_center_blocked_share"](None)
    assert "tp_center_blocked_share" not in PD.fp_measures(c, FP)[0]          # no camera named: no measure


def test_a_toss_with_no_shot_is_measured():
    # the hip draw tosses both guns up and catches them, firing nothing
    c = _clip([{"name": "Toss", "t": 0.1, "value": "R"}, {"name": "Toss", "t": 0.1, "value": "L"},
               {"name": "Catch", "t": 0.45, "value": "R"}, {"name": "Catch", "t": 0.5, "value": "L"}])
    v = _vals(c)
    assert abs(v["toss_flight_min_s"] - 0.35) < 1e-9 and abs(v["toss_flight_max_s"] - 0.4) < 1e-9
    assert "shot_count" not in v


def test_a_melee_hit_in_a_weapon_clip_is_timed_and_its_speed_compared():
    # Greatsword's cuts: the Hit marker's time, and the blade tip's speed arriving at it vs its fastest frame
    c = _clip([{"name": "Hit", "t": 0.1}])
    v = _vals(c)
    assert abs(v["hit_time_s"] - 0.1) < 1e-9
    assert 0.0 < v["hit_tip_speed_share"] <= 1.0


def test_the_blade_tip_is_measured_over_the_floor():
    # a 4-stud Greatsword swung through straight down cuts into the ground: the tip's lowest point over the floor
    c = _clip([])
    v = _vals(c)
    tips = c["sword"]["tip"]
    assert abs(v["tip_floor_min_studs"] - (min(t[1] for t in tips) + 3.0)) < 1e-9
    c["sword"]["tip"] = [list(t) for t in tips]
    c["sword"]["tip"][0][1] = -3.5                                 # half a stud into the floor
    assert abs(_vals(c)["tip_floor_min_studs"] + 0.5) < 1e-9
