"""kit/anim/timing_chart.py - the TIMING CHART (AAA plan #3): speeds of the blade tip and hands, the spacing per frame,
keys / Hit / stepped beats marked"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import strike as S          # noqa: E402
import timing_chart as TC   # noqa: E402

MOVE = {"name": "ChartProbe", "kind": "strike", "fps": 60, "rig": "R6", "arm_slide": 2.4,
        "sword": {"length": 3.6, "grip": 0.5},
        "keys": [{"t": 0.0, "grip": [0.4, 0.2, -1.4], "dir": [0.2, 0.7, -0.7], "ease": "InOut"},
                 {"t": 0.3, "grip": [-0.3, -0.4, -2.0], "dir": [-0.5, -0.3, -0.8], "ease": "Out"},
                 {"t": 0.6, "grip": [-0.4, -0.5, -1.6], "dir": [-0.3, -0.4, -0.87], "ease": "InOut"}]}


def test_series_and_chart(tmp_path):
    c, _ = S.generate(json.loads(json.dumps(MOVE)))
    s = TC.series(c)
    n = len(c["times"])
    assert all(len(s[k]) == n for k in ("right_hand", "left_hand", "tip", "tip_step"))
    assert s["tip"][0] == 0.0 and s["tip"].max() > 1.0
    assert np.allclose(s["tip_step"] * c["fps"], s["tip"])           # spacing per frame = speed / fps
    out = TC.chart(c, MOVE, str(tmp_path / "chart.png"))
    assert os.path.getsize(out) > 5000


# ---- the READING (the owner's method lists, 2026-11-13: the chart as a command and a page of every sheet) ----
LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")


def _loved():
    with open(LOVED, encoding="utf-8") as fh:
        move = json.load(fh)
    c, _ = S.generate(json.loads(json.dumps(move)))
    return c, move


def test_reading_counts_the_frames_of_a_loved_cut():
    c, move = _loved()
    r = TC.read(c, move)
    assert r["striker"] == "tip" and r["frames"] == len(c["times"])
    assert "mismatch" not in r
    assert sum(r["key_gaps_fr"]) == r["frames"] - 1            # the keys span the clip, frame for frame
    assert r["key_frames"][0] == 0 and r["keys"] == len(move["keys"])
    hit = next(e["t"] for e in c["events"] if e["name"] == "Hit")
    assert r["hit_frame"] == round(hit * c["fps"])
    assert 0 <= r["hit_after_peak_fr"] <= 1                    # the Hit lands on or a frame after the fastest frame
    assert r["rise_fr"] + r["fall_fr"] + 1 == r["cut_fr"]
    assert r["gather_fr"] >= 1 and r["quiet_after_fr"] >= 1 and r["strikes"] == [{k: r[k] for k in r["strikes"][0]}]
    assert r["widest_over_mean"] > 1.2                         # a cut is unevenly spaced
    s = TC.series(c)
    lo, up = max(0, r["hit_frame"] - int(0.4 * c["fps"])), r["hit_frame"] + int(0.15 * c["fps"]) + 1
    assert r["peak_frame"] == lo + int(np.argmax(s["tip"][lo:up]))      # the fastest frame of the strike at the Hit


def test_reading_in_words_names_the_hit_and_the_gaps():
    c, move = _loved()
    r = TC.read(c, move)
    w = TC.words(r)
    assert w.startswith("the blade tip gathers ")
    assert f"the Hit is at frame {r['hit_frame']}" in w
    assert "frames between keys " + " | ".join(str(g) for g in r["key_gaps_fr"]) in w


def test_a_move_that_is_not_the_clips_own_is_a_mismatch():
    c, move = _loved()
    longer = json.loads(json.dumps(move))
    for k in longer["keys"]:
        k["t"] = round(float(k["t"]) * 2.0, 4)                 # another move: twice as long
    r = TC.read(c, longer)
    assert "this clip was not built from this move file" in r["mismatch"]
    shorter = json.loads(json.dumps(move))
    shorter["keys"] = shorter["keys"][:3]                      # ends well before the clip does
    assert "the last key is at 0.32 s and the clip ends at 0.85 s" in TC.read(c, shorter)["mismatch"]
    nearly = json.loads(json.dumps(move))
    nearly["keys"][-1]["t"] = round(float(nearly["keys"][-1]["t"]) - 0.05, 4)      # three frames short of the clip's end
    assert TC.NOT_ITS_MOVE in TC.read(c, nearly)["mismatch"]
    other = json.loads(json.dumps(move))
    other["name"] = "AnotherMove"                              # the same keys under another move's name
    assert "the move file is AnotherMove's and the clip is Katana1Kesa" in TC.read(c, other)["mismatch"]
    for empty in ({"name": "Katana1Kesa", "keys": []}, {"name": "Katana1Kesa", "keys": [{"t": 0.0}]},
                  {"name": "Katana1Kesa", "keys": [{"grip": [0, 0, 0]}, {"grip": [0, 0, 0]}]}, {"name": "Katana1Kesa", "phases": []}):
        assert "not a move's key list" in TC.read(c, empty)["mismatch"]
    candidate = json.loads(json.dumps(c))
    candidate["name"] = "Katana1Kesa_r2_c3"                    # a round's candidate is its move's
    assert "mismatch" not in TC.read(candidate, move)
    scrambled = json.loads(json.dumps(move))
    scrambled["keys"][1]["t"], scrambled["keys"][2]["t"] = scrambled["keys"][2]["t"], scrambled["keys"][1]["t"]
    assert "not in time order" in TC.read(c, scrambled)["mismatch"]


def test_marks_are_never_a_mismatch():
    c, _ = _loved()
    r = TC.read(c, None, [0.1, 0.2])                           # a sheet's own key poses: they need not span the clip
    assert "mismatch" not in r and r["key_gaps_fr"] == [6] and r["keys"] == 2


def test_a_clip_with_no_blade_charts_its_fastest_limb():
    c, _ = _loved()
    bare = json.loads(json.dumps(c))
    bare.pop("sword")
    r = TC.read(bare)
    assert r["striker"] in ("RightHand", "LeftHand", "RightFoot", "LeftFoot")
    assert "hand" in TC.words(r) or "foot" in TC.words(r)


def test_a_sword_track_a_frame_short_is_not_charted_as_a_tip():
    c, _ = _loved()
    short = json.loads(json.dumps(c))
    short["sword"]["tip"] = short["sword"]["tip"][:-1]
    assert TC.read(short)["striker"] != "tip"                  # no crash, and no chart of a track that is not the clip's


def test_a_still_clip_says_so():
    c, _ = _loved()
    still = json.loads(json.dumps(c))
    still.pop("sword")
    for j in still["joints"].values():
        j["frames"] = [j["frames"][0]] * len(j["frames"])
    if isinstance(still.get("root"), dict) and still["root"].get("frames"):
        still["root"]["frames"] = [still["root"]["frames"][0]] * len(still["root"]["frames"])
    r = TC.read(still)
    assert "does not move" in r["still"] and "does not move" in TC.words(r)


def test_the_command_fails_on_a_wrong_move_and_draws_nothing(tmp_path, capsys):
    c, move = _loved()
    cp, mp, out = tmp_path / "c.clip.json", tmp_path / "m.move.json", tmp_path / "t.png"
    cp.write_text(json.dumps(c), encoding="utf-8")
    for k in move["keys"]:
        k["t"] = round(float(k["t"]) * 2.0, 4)
    mp.write_text(json.dumps(move), encoding="utf-8")
    assert TC.main([str(cp), "--move", str(mp), "--out", str(out)]) == 1
    v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert v["status"] == "fail" and "NOT drawn" in v["summary"] and not out.exists()
    assert TC.main([str(cp), "--out", str(out)]) == 0 and out.exists()
    v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert v["next_action"].startswith("look at ") and v["reading"]["cut_fr"] >= 1


def test_the_command_refuses_a_file_that_is_not_a_clip(tmp_path, capsys):
    p = tmp_path / "x.json"
    p.write_text("{not json", encoding="utf-8")
    assert TC.main([str(p)]) == 1
    assert "could not be read" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]
    p.write_text(json.dumps({"times": [0.0]}), encoding="utf-8")
    assert TC.main([str(p)]) == 1
    assert "is not a clip with frames" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])["summary"]


# ---- what the stage's review found (2026-11-13), each as a case ----
def test_a_stepped_clip_is_read_on_its_smooth_motion():
    c, move = _loved()
    stepped = json.loads(json.dumps(move))
    stepped["step"] = {"on": 2, "beats": "all"}
    cs, _ = S.generate(stepped)
    assert cs.get("stepped")                                   # (the fixture really is stepped)
    r, plain = TC.read(cs, stepped), TC.read(c, move)
    assert r["stepped"] is True and plain["stepped"] is False
    assert r["cut_fr"] >= 10 and r["widest_over_mean"] > 1.4   # read raw it was a 1-frame cut, 1.0x: the "robot" spacing
    assert abs(r["peak_studs_s"] - plain["peak_studs_s"]) < 0.15 * plain["peak_studs_s"]
    assert "(a stepped clip, read on its smooth motion)" in TC.words(r)


def test_a_blocking_has_no_spacing_and_says_so(tmp_path):
    import blocking as B
    c, move = _loved()
    held = B.held(c, B.key_frames(c, move), "Katana1Kesa")
    r = TC.read(held, None, [k["t"] for k in move["keys"]])
    assert "cut_fr" not in r and "widest_over_mean" not in r
    assert TC.words(r) == "held poses (a blocking): no in-betweens, so no spacing to read; frames between poses 11 | 8 | 6 | 7 | 19"
    assert os.path.getsize(TC.chart(held, [k["t"] for k in move["keys"]], str(tmp_path / "held.png"))) > 5000


def test_every_hit_is_read_in_time_order():
    c, _ = _loved()
    twice = json.loads(json.dumps(c))
    first = next(e["t"] for e in c["events"] if e["name"] == "Hit")
    twice["events"] = [{"name": "Hit", "t": 0.1}, {"name": "Hit", "t": first}][::-1]      # (listed out of order)
    r = TC.read(twice)
    assert [k["hit_frame"] for k in r["strikes"]] == [6, round(first * c["fps"])]
    assert r["hit_frame"] == 6 and r["strikes"][1]["hit_after_peak_fr"] == 0
    w = TC.words(r)
    assert "Hit 1 of 2 is at frame 6" in w and f"Hit 2 at frame {round(first * c['fps'])}, on the fastest frame" in w


def test_a_hit_outside_the_clip_is_said_not_read():
    c, _ = _loved()
    for t in (5.0, -1.0):
        off = json.loads(json.dumps(c))
        off["events"] = [{"name": "Hit", "t": t}]
        r = TC.read(off)
        assert r["hits_outside"] == 1 and r["hit_frame"] is None and r["peak_studs_s"] > 100      # the clip's own fastest frame
        assert "1 Hit marker(s) lie outside the clip and are not read" in TC.words(r) and "no Hit marker" in TC.words(r)


def test_an_r15_clip_is_refused_in_one_line(tmp_path, capsys):
    c, _ = _loved()
    r15 = json.loads(json.dumps(c))
    r15["rig"] = "R15"
    p = tmp_path / "r15.clip.json"
    p.write_text(json.dumps(r15), encoding="utf-8")
    assert TC.main([str(p), "--out", str(tmp_path / "x.png")]) == 1
    v = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert v["status"] == "fail" and "it is a R15 clip" in v["summary"] and not (tmp_path / "x.png").exists()


def test_a_two_frame_clip_that_moves_is_read():
    c, _ = _loved()
    two = json.loads(json.dumps(c))
    two["times"] = two["times"][:2]
    two["events"] = []
    for j in two["joints"].values():
        j["frames"] = [j["frames"][0], j["frames"][20]]
    for k in ("tip", "grip_path", "edge"):
        if two["sword"].get(k):
            two["sword"][k] = [two["sword"][k][0], two["sword"][k][20]]
    if isinstance(two.get("root"), list):
        two["root"] = two["root"][:2]
    r = TC.read(two)
    assert "still" not in r and r["cut_fr"] >= 1
