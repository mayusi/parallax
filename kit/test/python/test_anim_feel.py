"""the feel pass (kit/anim/feel.py): holds, snaps and retimes a finished R6 clip around its Hits"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C      # noqa: E402
import feel as F      # noqa: E402
import strike as S    # noqa: E402

MOVE = {"name": "FeelProbe", "kind": "strike", "fps": 30, "rig": "R6", "sword": {"length": 4.6, "grip": 0.75, "grip_pitch": 0},
        "events": [{"name": "Hit", "t": 0.2}],
        "keys": [{"t": 0.0, "pitch": -10, "yaw": 20, "grip": [0.6, 1.2, 0.4], "dir": [0.3, 0.9, -0.3], "ease": "InOut"},
                 {"t": 0.13, "pitch": -25, "yaw": 50, "grip": [0.9, 1.8, 0.6], "dir": [0.5, 0.8, 0.3], "ease": "InOut"},
                 {"t": 0.2, "pitch": 15, "yaw": -40, "grip": [0.2, 0.2, -1.2], "dir": [-0.4, -0.5, -0.8], "ease": "InOut"},
                 {"t": 0.6, "pitch": 0, "yaw": 0, "grip": [0.6, 1.0, 0.4], "dir": [0.0, 1.0, -0.2], "ease": "InOut"}]}
SPEC = {"name": "FeelProbeFeel", "from": "FeelProbe", "hits": "auto", "anticipation": 1.5, "snap": 0.55, "hitstop": 3,
        "overshoot": 0.18, "settle": 4, "recovery": 1.15, "lag": {"Head": 1}}


def _src():
    clip, _ = S.generate(json.loads(json.dumps(MOVE)))
    return clip


def test_warp_holds_the_hit_and_snaps_into_it():
    out_t, shown = F.warp([i / 30 for i in range(21)], [0.2], 30, 1.5, 0.55, 3, 1.15)
    assert len(out_t) == len(shown) and abs(out_t[1] - out_t[0] - 1 / 30) < 1e-5
    holds = [k for k, s in enumerate(shown) if abs(s - 0.2) < 1e-9]
    assert len(holds) == 4                                  # the hit frame + 3 hitstop frames
    k = holds[0]
    assert shown[k] - shown[k - 1] > 1.5 / 30 * 0.9          # the last step INTO the hit is a snap (> 1 source frame)
    assert shown[k - 1] - shown[k - 2] < 1 / 30               # right after the anticipation's slow frames
    assert all(0 < shown[i + 1] - shown[i] < 0.9 / 30 for i in range(0, 4))   # the anticipation runs slower than real time


def test_apply_retimes_hits_and_keeps_the_body_clean():
    src = _src()
    rig = C.load_rig("r6")
    clip, info = F.apply(src, SPEC, rig)
    assert clip["rig"] == "R6" and len(clip["times"]) > len(src["times"])
    hits = [e for e in clip["events"] if e["name"] == "Hit"]
    assert len(hits) == 1 and abs(hits[0]["t"] - info["hit_out"][0]) < 1e-6
    k = int(round(hits[0]["t"] * 30))
    tor = clip["joints"]["Torso"]["frames"]
    assert tor[k] == tor[k + 1] == tor[k + 2] == tor[k + 3]   # the hit pose is held
    assert len(clip["sword"]["tip"]) == len(clip["times"])     # the blade path is retimed with the body
    assert clip["gate"]["pop_deg"] >= 130                     # the snap into the hit is allowed to be a one-frame turn
    m = C.metrics(clip, rig, {**clip["gate"], "penetration": 0.5, "foot_slide": 1.0, "foot_skate": 1.0, "loop_seam_deg": 360, "hit_before": 999, "hit_after": 999})
    assert not m["problems"], m["problems"]


def test_apply_overshoots_past_the_hit_then_settles():
    src = _src()
    rig = C.load_rig("r6")
    clip, info = F.apply(src, SPEC, rig)
    k = int(round(info["hit_out"][0] * 30)) + 3                # the last held frame
    tor = clip["joints"]["Torso"]["frames"]
    import numpy as np
    def ang(a, b):
        d = abs(float(np.dot(np.array(a[:4]), np.array(b[:4]))))
        return 2 * np.degrees(np.arccos(min(1.0, d)))
    held = tor[k]
    after = tor[k + 1]
    assert ang(held, after) > 0.5                              # the pose keeps moving right after the hold (the overshoot)
    assert ang(tor[k + 4], tor[k + 5]) < ang(held, after) * 3  # and settles rather than snapping back


def test_feel_retimes_a_weapon_grip_track_and_the_markers_with_the_arms():
    """a pose clip's weapon track ("grip", one frame per source frame) and its non-hit markers move with the retime
    (copied through unchanged, the gun drifted out of the hand and a Shot fired at the wrong moment)"""
    src = _src()
    n = len(src["times"])
    src["grip"] = [[0.0, 0.0, 0.0, 1.0, 0.0, float(i), 0.0] for i in range(n)]      # y = the source frame number
    src["events"] = list(src.get("events") or []) + [{"name": "Shot", "t": src["times"][n // 2]}]
    clip, info = F.apply(src, {"name": "FeelGrip", "hits": "auto", "lag": {}}, C.load_rig("r6"))
    assert len(clip["grip"]) == len(clip["times"])
    # the grip at each output frame is the source grip at that frame's source time: it follows the same warp as a joint
    rj = list(clip["joints"].keys())[0]
    for k in (0, len(clip["times"]) // 3, len(clip["times"]) - 1):
        src_frame = clip["grip"][k][5]
        want = F.frame_at(src["joints"][rj]["frames"], src["times"], src["times"][0] + src_frame / (n - 1) * (src["times"][-1] - src["times"][0]))
        assert abs(want[0] - clip["joints"][rj]["frames"][k][0]) < 1e-6
    shot = [e for e in clip["events"] if e["name"] == "Shot"]
    assert shot and 0.0 < shot[0]["t"] <= clip["times"][-1]


def test_feel_retimes_every_per_frame_weapon_track():
    """the weapon's edge and rotation tracks are resampled with its tip and grip path (left at the source's frame count,
    the dossier's grip-roll measure could not read the retimed clip)"""
    src = _src()
    n = len(src["times"])
    sw = src["sword"]
    sw["edge"] = [[0.0, 1.0, 0.0] for _ in range(n)]
    sw["grip_rot"] = [[0.0, 0.0, 0.0, 1.0] for _ in range(n)]
    clip, _ = F.apply(src, {"name": "FeelTracks", "hits": "auto", "lag": {}}, C.load_rig("r6"))
    m = len(clip["times"])
    for name in ("tip", "grip_path", "edge", "grip_rot"):
        if name in clip["sword"]:
            assert len(clip["sword"][name]) == m, name
    assert all(abs(q[3] - 1.0) < 1e-6 for q in clip["sword"]["grip_rot"])


def test_feel_keeps_a_held_weapon_in_the_hand_through_the_snap_and_the_overshoot():
    """the weapon rides the arm (kit/anim/grip.py: Handle, Part0 = Right Arm): retimed, its tip and grip path are carried
    by the arm - resampled on their own in character space (a straight line between two source frames, no overshoot)
    the blade left the hand the source holds it in at every frame (ClaymoreComboBwFeel 0.62 studs off, 2026-11-19)"""
    import in_hand as IH
    src = _src()
    src["hands"] = "right"
    assert IH.read(src)["worst"] <= 0.01                     # the strike route puts the hilt in the hand
    clip, _ = F.apply(src, SPEC, C.load_rig("r6"))
    r = IH.read(clip)
    assert r["worst"] <= 0.01 and not r["loose"], r["loose"]
    assert len(clip["sword"]["tip"]) == len(clip["sword"]["grip_path"]) == len(clip["times"])


def test_feel_puts_a_two_handed_clips_off_hand_back_on_the_hilt_after_the_settle():
    """the overshoot's settle blends each arm on its own: on a two-handed clip whose arms turn fast at the hit the hands
    come apart (GreatswordSlash1Feel's left hand 0.72 studs off, 2026-11-19). The off hand is put back on the hilt by
    rearm's arm IK; the weapon and the Right Arm keep what the retime gave them"""
    import in_hand as IH
    move = json.loads(json.dumps(MOVE))
    move["keys"][2]["grip"] = [0.0, 0.6, -0.9]               # (the hit lands near the chest: the hilt in the arms' reach)
    src, _ = S.generate(move)
    src["hands"] = "two"
    assert IH.read(src)["worst"] <= 0.01                     # the strike route holds it in both hands
    rig = C.load_rig("r6")
    clip, info = F.apply(json.loads(json.dumps(src)), SPEC, rig)
    r = IH.read(clip)
    assert r["worst"] <= 0.01 and not r["loose"], r["loose"]  # (the retime alone: 0.23 studs off, frames 11-13)
    assert info.get("off_hand")                              # the frames it moved, said
    unseated = dict(src, hands="right")                      # (the same body, held in one hand: nothing is seated)
    one, _ = F.apply(json.loads(json.dumps(unseated)), SPEC, rig)
    assert one["joints"]["Right Arm"] == clip["joints"]["Right Arm"] and one["sword"] == clip["sword"]
    moved = {k for k, _, _ in info["off_hand"]}
    assert all(one["joints"]["Left Arm"]["frames"][k] == clip["joints"]["Left Arm"]["frames"][k]
               for k in range(len(clip["times"])) if k not in moved)


def test_feel_leaves_a_one_handed_clip_as_the_retime_made_it():
    """only a clip that says "two" hands has an off hand put back: a one-handed clip comes out byte for byte as before"""
    src = _src()
    rig = C.load_rig("r6")
    for hands in ("right", 1, None):
        s = json.loads(json.dumps(src))
        if hands is not None:
            s["hands"] = hands
        clip, info = F.apply(s, SPEC, rig)
        orig = F.seat_off_hand
        try:
            F.seat_off_hand = lambda c, r: []                # (the retime alone)
            bare, _ = F.apply(json.loads(json.dumps(s)), SPEC, rig)
        finally:
            F.seat_off_hand = orig
        assert json.dumps(clip, sort_keys=True) == json.dumps(bare, sort_keys=True) and "off_hand" not in info


def test_feel_moves_an_off_hand_it_cannot_reach_no_further_from_the_weapon():
    """where the hilt is out of the off arm's reach (rearm's IK turns an arm, it does not slide it) the frame is left
    as the retime made it - pointing at it would not bring the hand nearer: the in-hand gate says what is left"""
    import in_hand as IH
    src = _src()                                             # (its hit's hilt is past the left arm's reach)
    src["hands"] = "two"
    rig = C.load_rig("r6")
    clip, info = F.apply(json.loads(json.dumps(src)), SPEC, rig)
    orig = F.seat_off_hand
    try:
        F.seat_off_hand = lambda c, r: []
        bare, _ = F.apply(json.loads(json.dumps(src)), SPEC, rig)
    finally:
        F.seat_off_hand = orig
    got, was = IH.read(clip)["free"], IH.read(bare)["free"]
    assert all(g <= w + 1e-6 for g, w in zip(got, was))     # never further off than the retime left it
    assert all(off <= IH.LOOSE for _, _, off in info["off_hand"])
