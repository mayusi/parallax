"""2026-10-25 (IronMountain, the first unarmed body blow): a step's lift (`left_lift` / `right_lift` on a feet key) arcs
the foot over ITS segment only - held like the other fields, every later segment lifted the landed foot again and the
lead foot hovered 0.2 studs through the whole hold; and a foot that never leaves the floor is a skate, not a stamp
(proc_dossier stamp_lead_s is NaN, so the check fails)."""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import clip as C  # noqa: E402
import proc_dossier as D  # noqa: E402
import strike as S  # noqa: E402

GUARD = {"rhand": [0.5, 0.6, -1.2], "lhand": [-0.8, 0.7, -1.3]}


def probe(lift):
    feet = [{"t": 0.0, "right": [0.6, 0, 0.8], "left": [-0.5, 0, -0.7]},
            {"t": 0.1, "right": [0.6, 0, 0.8], "left": [-0.5, 0, -0.7], "left_lift": lift},
            {"t": 0.25, "right": [0.6, 0, 0.8], "left": [-0.5, 0, -1.5]},
            {"t": 0.6, "right": [0.6, 0, 0.5], "left": [-0.5, 0, -1.5]}]
    keys = [dict(GUARD, t=0.0, pos=[0, -0.4, 0]), dict(GUARD, t=0.25, pos=[0, -0.5, -0.3]),
            dict(GUARD, t=0.6, pos=[0, -0.5, -0.3])]
    move = {"name": "ProbeStep", "unarmed": True, "strike_hand": "left", "fps": 60, "arm_slide": 1.5, "leg_slide": 1.3,
            "pelvis_drop_max": 0.35, "lag": 0.0, "keys": keys, "feet": feet,
            "events": [{"name": "Hit", "t": 0.27}]}
    clip, _ = S.generate(move)
    return clip


def lowest(clip, t, leg="Left Leg"):
    w = C.world_frames(clip, C.load_rig("r6"))[int(round(t * 60))][leg]
    return min(float((w @ np.array([x, -1.0, z, 1.0]))[1]) for x in (-0.5, 0.5) for z in (-0.5, 0.5))


def test_a_step_lift_arcs_its_own_segment_and_the_landed_foot_stays_down():
    clip = probe(0.3)
    floor = lowest(clip, 0.0)
    assert lowest(clip, 0.175) > floor + 0.1                     # mid-step: in the air
    for t in (0.35, 0.45, 0.55):                                 # the next segment (the rear foot moves): planted
        assert lowest(clip, t) < floor + 0.03, (t, lowest(clip, t), floor)


def test_a_foot_that_never_lifts_is_no_stamp():
    d = {"build": {"builder": "strike"}, "checks": [
        {"id": "stamp", "measure": "stamp_lead_s", "range": [0.0, 0.083], "why": "the stamp leads the blow"}]}
    skate = D.check(probe(0.0), d)["checks"]["stamp"]
    assert not skate["pass"] and skate["value"] != skate["value"]          # NaN
    stamp = D.check(probe(0.3), d)["checks"]["stamp"]
    assert stamp["pass"], stamp
