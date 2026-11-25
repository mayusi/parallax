"""kit/anim/pose_appeal.py (AAA gaps v2 B3 / B4 / B5): an upright mirrored rest pose is flagged (no line of action,
twins), a body shifted past its feet is off balance, a real strike passes, the cheat stays within its limit"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import pose_appeal as PA  # noqa: E402
import strike as S        # noqa: E402

PARTS = ["Torso", "Head", "Right Arm", "Left Arm", "Right Leg", "Left Leg"]


def rest_clip(n=10, torso_pos=(0.0, 0.0, 0.0)):
    f = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    joints = {p: {"frames": [list(f) for _ in range(n)]} for p in PARTS}
    joints["Torso"]["frames"] = [[0.0, 0.0, 0.0, 1.0, *torso_pos] for _ in range(n)]
    return {"rig": "R6", "times": [i / 60 for i in range(n)], "joints": joints, "events": [{"name": "Hit", "t": 0.05}]}


def test_upright_mirrored_rest_is_flagged():
    """mirrored limbs are a problem; standing upright is only a NOTE (the owner's 9/10 GreatswordSideCut keys stand at
    0-2 deg - the rule was recalibrated against loved data 2026-10-22)"""
    r = PA.report(rest_clip())
    assert r["keys"][0]["line_of_action_deg"] < 5 and min(r["keys"][0]["twin_deg"].values()) < 1
    assert any("mirrors" in p for p in r["problems"]) and not any("upright" in p for p in r["problems"])
    assert any("upright" in n for n in r["notes"])


def test_off_model_keys_are_flagged_against_the_loved_space(monkeypatch):
    """E5: a key further than OFF_MODEL_DEG from the loved pose space is a problem; a near one is not"""
    monkeypatch.setattr(PA, "space_of", lambda clip, i: (PA.OFF_MODEL_DEG + 5, 100.0))
    r = PA.report(rest_clip())
    assert r["keys"][0]["space_deg"] > PA.OFF_MODEL_DEG and any("OFF-MODEL" in p for p in r["problems"])
    monkeypatch.setattr(PA, "space_of", lambda clip, i: (3.0, 40.0))
    assert not any("OFF-MODEL" in p for p in PA.report(rest_clip())["problems"])


def test_balance_off_when_the_body_hangs_past_the_feet():
    # the torso slid a stud and a half forward with the legs left behind (feet stay under, the mass does not)
    c = rest_clip()
    for p in ("Right Leg", "Left Leg"):
        c["joints"][p]["frames"] = [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.6] for _ in range(10)]
    c["joints"]["Torso"]["frames"] = [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, -1.6] for _ in range(10)]
    r = PA.report(c)
    assert r["balance"]["off_balance_frames"] > 0


def test_a_strike_passes_and_the_cheat_stays_in_its_limit():
    key = {"grip": [0.4, -0.4, -1.6], "dir": [0.2, 0.7, -0.7], "pos": [0, -0.6, 0], "right": [0.55, 0, 1.0],
           "left": [-0.57, 0, -0.7], "ease": "InOut"}
    move = {"name": "AppealStrike", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4, "leg_slide": 1.3,
            "sword": {"length": 3.6, "grip": 0.5, "kind": "katana"},
            "keys": [dict(key, t=0.0, yaw=0, pitch=-10), dict(key, t=0.2, yaw=25, grip=[0.9, 0.6, -0.6], dir=[0.3, 0.6, 0.75]),
                     dict(key, t=0.4, yaw=-25, pitch=15, grip=[-0.3, -0.6, -2.0], dir=[-0.5, -0.3, -0.8])]}
    clip = S.generate(json.loads(json.dumps(move)))[0]
    r = PA.report(clip, move, cheat_max=8)
    assert len(r["keys"]) == 3
    for k in r["keys"]:
        assert abs(k.get("cheat_yaw", 0.0)) <= 8 + 1e-9 and 0 < k["silhouette_pct"] < 100


def test_blade_visibility_from_the_game_camera():
    """a blade held out to the side is seen whole; one held straight down the back of the torso's line, in front of
    the chest, hides behind the body from the camera behind the character"""
    c = rest_clip()
    W = PA.C.world_frames(c, PA.C.load_rig("r6"))[0]
    side = PA.blade_visible(W, PA.C.load_rig("r6"), [2.0, 0.0, -0.5], [5.0, 0.0, -0.5])
    hidden = PA.blade_visible(W, PA.C.load_rig("r6"), [0.0, 0.2, -0.9], [0.0, 0.6, -2.0])
    assert side == 100.0 and hidden < 50.0


def test_a_blade_end_on_to_the_game_camera_is_not_seen():
    """the governor 2026-11-04: SwordTrickCut's shoulder rest pointed the blade straight back at the over-the-shoulder
    camera - nothing covered it, so appeal and the dossier counted it seen, while the game view showed no blade. A
    blade aimed at the camera is a dot; the same blade turned across the view is seen"""
    import proc_dossier as PD
    rig = PA.C.load_rig("r6")
    c = rest_clip()
    W = PA.C.world_frames(c, rig)[0]
    cam = PD.FP_EYE + np.asarray(PA.GAME_CAM)
    grip = np.array([1.4, 1.2, -0.7])
    end_on = grip + 3.6 * (cam - grip) / np.linalg.norm(cam - grip)
    across = grip + np.array([3.6, 0.0, 0.0])
    assert not any(PD.blade_seen(W, rig, cam, grip, end_on))
    assert all(PD.blade_seen(W, rig, cam, grip, across))
    # appeal measures EVERY frame from the game camera, not only the key poses from a behind-and-above direction
    n = len(c["times"])
    c["sword"] = {"tip": [list(end_on)] * n, "grip_path": [list(grip)] * n}
    r = PA.report(c)
    assert r["blade_game"]["share"] == 0.0 and r["blade_game"]["hidden_runs"]
    assert r["keys"][0]["blade_seen_game_pct"] == 0.0
    assert any("unseen from the GAME camera" in p for p in r["problems"]) is False   # 0.17 s: under the 0.2 s flag


def test_blade_visibility_follows_the_root_travel():
    """a root-local blade in front of the chest stays HIDDEN on a body that travelled 5 studs (the sword was measured
    against the moved body without moving the blade: a lunge's hidden cut read as seen)"""
    c = rest_clip()
    n = len(c["times"])
    c["root"] = [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, -5.0] for _ in range(n)]
    c["sword"] = {"tip": [[0.0, 0.6, -2.0] for _ in range(n)], "grip_path": [[0.0, 0.2, -0.9] for _ in range(n)]}
    assert PA.report(c)["keys"][0]["blade_visible_pct"] < 50.0
