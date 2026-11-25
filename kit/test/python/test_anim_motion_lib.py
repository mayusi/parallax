"""the searchable motion library (kit/anim/motion_lib.py): measured tags, licence tags, word search"""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "anim"))
import clip as C  # noqa: E402
import motion_lib as M  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
REST = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]


def _clip(n, arm_angle, loop=False, fps=60):
    """an R6 clip whose right shoulder turns by arm_angle(i) radians about its own X axis; everything else at rest"""
    def q(a):
        return [math.sin(a / 2), 0.0, 0.0, math.cos(a / 2), 0.0, 0.0, 0.0]
    joints = {j: {"frames": [list(REST) for _ in range(n)]} for j in ("Torso", "Head", "Left Arm", "Right Leg", "Left Leg")}
    joints["Right Arm"] = {"frames": [q(arm_angle(i)) for i in range(n)]}
    return {"schema": 1, "name": "t", "rig": "R6", "fps": fps, "loop": loop, "times": [i / fps for i in range(n)], "joints": joints}


def test_a_fast_one_arm_swing_reads_as_a_right_handed_strike_and_a_still_loop_does_not():
    rig = C.load_rig("r6", root=ROOT)
    swing = M.measure(_clip(40, lambda i: 0.0 if i < 15 else min(2.6, (i - 15) * 0.6)), rig)
    assert "strike" in swing["tags"] and "righthand" in swing["tags"]
    assert swing["facts"]["strike"]["hand"] == "right"
    assert 0.2 < swing["facts"]["strike"]["at_s"] < 0.4        # the swing starts at frame 15 (0.25 s), not the first frame
    still = M.measure(_clip(60, lambda i: 0.0, loop=True), rig)
    assert "strike" not in still["tags"] and "loop" in still["tags"] and "holds" in still["tags"]


def test_licence_tags_creator_store_and_only_the_devforum_posts_with_free_use_terms():
    assert M.licence_of({"id": "s123_1", "source": "Creator Store"})[0] == "game"
    assert M.licence_of({"id": "d1595359_0_1", "source": "DevForum"})[0] == "game"        # 'free for use'
    assert M.licence_of({"id": "d2448914_2_1", "source": "DevForum"})[0] == "study"       # no licence text


def test_find_ranks_by_words_and_tags_prefers_loved_hides_study_and_demotes_dances():
    def row(i, name, kind, tags, verdict="unrated", lic="game"):
        return {"id": i, "name": name, "kind": kind, "pack": "", "tags": tags, "verdict": verdict, "licence": lic}
    cat = [row("a", "Slam", "attack", ["strike", "downward", "twohanded"], "bad"),
           row("b", "Heavy Chop", "attack", ["strike", "downward", "twohanded", "heavy"], "love"),
           row("c", "Overhead", "attack", ["strike", "downward"], "love", lic="study"),
           row("d", "RickRoll", "dance", ["loop"], "love"),
           row("e", "Roll", "dash", ["spin", "crouch"], "ok")]
    ids = [r["id"] for _, r in M.find("heavy overhead slam", cat=cat)]
    assert ids[0] == "b" and "c" not in ids                    # loved + heavy beats the bad exact name; study hidden
    assert "c" in [r["id"] for _, r in M.find("overhead", cat=cat, game_only=False)]
    assert [r["id"] for _, r in M.find("dodge roll", cat=cat)][0] == "e"


def test_vocab_cuts_a_swing_into_windup_strike_and_a_still_loop_into_one_cycle():
    import motion_vocab as V
    rig = C.load_rig("r6", root=ROOT)
    # still - slow raise (the wind-up) - a fast swing - still: the cut points fall where the body slows down
    def ang(i):
        if i < 12:
            return 0.0
        if i < 40:
            return -0.9 * (i - 12) / 28
        if i < 48:
            return -0.9 + 3.2 * (i - 40) / 8
        return 2.3
    segs = V.segment(_clip(80, ang), rig)
    labels = [s[2] for s in segs]
    assert "strike" in labels
    si = labels.index("strike")
    assert si > 0 and labels[si - 1] in ("windup", "hold")
    assert segs[si][0] <= 44 <= segs[si][1]                    # the fast swing (frames 40-48) is inside the strike
    assert [s[2] for s in V.segment(_clip(60, lambda i: 0.0, loop=True), rig)] == ["cycle"]


def test_op_turn_turns_the_whole_body_about_the_vertical():
    import motion_vocab as V
    c = _clip(5, lambda i: 0.5)
    c["joints"]["Torso"]["frames"] = [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]] * 5
    V.op_turn(c, 90)
    assert abs(V.torso_yaw(c["joints"]["Torso"]["frames"][0]) - 90) < 1e-3     # frames are stored to 6 decimals


def test_the_critic_sees_a_keyframing_bot_in_the_curve_texture():
    import numpy as np
    import motion_critic as MC
    rng = np.random.default_rng(0)
    # a hand-made-like swing: dense, slightly irregular curve
    human = _clip(60, lambda i: 1.2 * math.sin(i / 9) + 0.08 * math.sin(i * 1.7) + 0.05 * math.sin(i * 2.9))
    bot = MC.machineize(human, rng)                            # the same motion as a few eased keys
    th, tb = MC.texture(human), MC.texture(bot)
    assert tb["detail"] < th["detail"]                        # the bot's curve lost its fine detail


def test_cutscene_facing_math_and_hitstop_holds_every_actor():
    import cutscene as CS
    assert abs(CS.yaw_to([0, 0], [0, -5])) < 1e-9             # yaw 0 faces -Z
    assert abs(CS.yaw_to([0, 0], [5, 0]) + 90) < 1e-9          # +X is a quarter turn clockwise from above
    f = CS.fwd(CS.yaw_to([1, 2], [4, 6]))
    assert abs(f[0] - 0.6) < 1e-9 and abs(f[1] - 0.8) < 1e-9

    class A:
        pass
    a = A()
    a.poses, a.root, a.visible = list(range(10)), [[i, 0, 0, 0] for i in range(10)], [True] * 10
    fx, hits, shots = [{"frame": 7}], [{"frame": 4, "hold": 3}], [{"from": 0, "to": 9}]
    total = CS.apply_hitstop({"a": a}, fx, hits, shots, 10)
    assert total == 13 and a.poses[4:8] == [4, 4, 4, 4] and fx[0]["frame"] == 10
