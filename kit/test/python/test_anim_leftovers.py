"""Leftovers of the animation stages' reviews (card r66z), each a small rule with its test: a motion-warp window written
backwards is refused where the move is made; a clip that carries no fps is read at the rate its own times say; two
parts of a prop cannot share one joint's name. The clips are cuts the owner loved, generated in memory (read only)."""
import copy
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import prop_rig as PR       # noqa: E402
import strike as S          # noqa: E402
import timing_chart as TC   # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")


def move(**more):
    with open(LOVED, encoding="utf-8") as fh:
        return {**json.load(fh), **more}


def travelling_move(**more):
    """the loved cut made to travel (a root key at its last key), so the build gives it a warp window"""
    m = move(**more)
    keys = copy.deepcopy(m["keys"])
    for i, k in enumerate(keys):
        k["root"] = [0, 0, -3.0 * i / (len(keys) - 1)]
    m["keys"] = keys
    return m


def test_a_warp_window_written_backwards_is_refused_where_the_move_is_made():
    base = S.generate(travelling_move())[0]
    if "warp" not in base:
        pytest.skip("this fixture cannot be made to travel by a root key: the rule is covered by the runtime spec")
    hit = base["warp"]["to"]
    assert base["warp"]["from"] == 0.0 and hit > 0
    ok = S.generate(travelling_move(warp={"from": 0.1, "to": hit}))[0]
    assert ok["warp"] == {"from": 0.1, "to": hit}
    same = S.generate(travelling_move(warp={"from": hit}))[0]            # a window of no length is a window
    assert same["warp"] == {"from": hit, "to": hit}
    for bad in ({"from": hit + 0.2}, {"from": 0.3, "to": 0.1}, {"from": -0.1}, {"from": float("nan")}, {"from": 0, "to": 99}):
        with pytest.raises(ValueError, match="warp: its window runs from"):
            S.generate(travelling_move(warp=bad))
    for junk in (5, {"from": None}, {"from": "soon"}):
        with pytest.raises(ValueError, match="warp: it is"):
            S.generate(travelling_move(warp=junk))


def test_a_move_that_cannot_be_made_is_a_named_failure_not_a_traceback(tmp_path, capsys):
    p = tmp_path / "Lunge.move.json"
    p.write_text(json.dumps(travelling_move(warp={"from": 0.3, "to": 0.1})), encoding="utf-8")
    assert S.main([str(p), "--out", str(tmp_path / "Lunge.clip.json")]) == 1
    v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert v["status"] == "fail" and "warp: its window runs from 0.3 s to 0.1 s" in v["summary"]
    assert not (tmp_path / "Lunge.clip.json").exists()


def test_a_clip_with_no_fps_is_read_at_the_rate_its_times_say():
    c = S.generate(move())[0]
    assert c["fps"] == 60 and TC.clip_fps(c) == 60
    said = TC.read(c, move())
    bare = copy.deepcopy(c)
    del bare["fps"]
    again = TC.read(bare, move())
    assert TC.clip_fps(bare) == pytest.approx(60) and again["fps"] == pytest.approx(60)
    assert said["keys"] > 2 and said["key_frames"] == again["key_frames"] and said["key_gaps_fr"] == again["key_gaps_fr"]
    for k in said:                                                    # the same chart in every number, not one read at half the rate
        assert again[k] == pytest.approx(said[k]) if isinstance(said[k], float) else again[k] == said[k], k
    # the build's own Hit gate counts a Hit's lateness in the clip's own frames
    import clip as C
    rig = C.load_rig("r6")
    ev = lambda m: [(e["name"], e.get("delta_frames")) for e in m["events"]]   # noqa: E731
    assert ev(C.metrics(bare, rig)) == ev(C.metrics(c, rig)) and any(d is not None for _, d in ev(C.metrics(c, rig)))
    for junk in (0, -5, True, "sixty", float("nan")):
        assert TC.clip_fps(dict(bare, fps=junk)) == pytest.approx(60)
    assert TC.clip_fps({"times": [0.0]}) == 30.0 and TC.clip_fps({}) == 30.0


CHEST = {"name": "Chest", "root": "Base",
         "parts": {"Base": {"size": [4, 2, 3], "at": [0, 1, 0]},
                   "Lid": {"size": [4, 0.5, 3], "at": [0, 2.25, 0], "parent": "Base", "joint": "Hinge",
                           "pivot": [0, 2, 1.5], "hinge": {"axis": [1, 0, 0], "min": 0, "max": 110}},
                   "Tray": {"size": [3, 0.3, 2], "at": [0, 1.2, 0], "parent": "Base", "joint": "Runner",
                            "pivot": [0, 1.2, 0], "slide": {"axis": [0, 0, -1], "min": 0, "max": 1.8}}}}


def test_two_parts_of_a_prop_cannot_share_one_joints_name():
    assert PR.problems(CHEST) == []
    twin = copy.deepcopy(CHEST)
    twin["parts"]["Tray"]["joint"] = "Hinge"
    assert any("its joint is named Hinge, as Lid's is" in p for p in PR.problems(twin))
    with pytest.raises(ValueError, match="one joint, one name"):
        PR.build(twin)
    own = copy.deepcopy(CHEST)                                        # a joint with no name takes its part's: also a name
    del own["parts"]["Lid"]["joint"]
    own["parts"]["Tray"]["joint"] = "Lid"
    assert any("its joint is named Lid" in p for p in PR.problems(own))


def test_a_moves_ask_for_an_upper_body_version_rides_on_its_clip_and_changes_nothing_else():
    plain = S.generate(move())[0]
    asked = S.generate(move(upper=True))[0]
    assert "upper" not in plain and asked["upper"] is True
    assert asked["joints"] == plain["joints"] and "Left Leg" in asked["joints"]      # the move itself keeps its legs
    masked = S.generate(move(mask="upper"))[0]                                      # the strike builder's own mask: no legs at all
    assert "Left Leg" not in masked["joints"] and "Right Leg" not in masked["joints"] and masked["mask"] == "upper"
    assert {j for j in plain["joints"]} - {j for j in masked["joints"]} == {"Left Leg", "Right Leg"}
