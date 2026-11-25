"""kit/anim/camera_read.py - the strike as the player's camera sees it, over time and from three camera angles (the
owner's older list, AN-36). A READING, not a gate: on the cuts the owner loved and rejected (generated in memory,
read only) it does not tell them apart, and that is pinned here so nobody makes a gate of it."""
import copy
import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
sys.path.insert(0, HERE)
import camera_read as CR         # noqa: E402
import clip as C                 # noqa: E402
import metrics as MT             # noqa: E402
import test_anim_collide as T    # noqa: E402

LOVED = ("GsCombo1SideLeft", "GsCombo2SideRight", "GsCombo3Overhead", "GsCombo4Underhip", "Katana1Kesa",
         "Katana2GyakuKesa", "Katana3Makko")
REJECTED = ("DTDrillSpin4", "GreatswordSideCut_v1", "SwordTrickArmsWide")


@pytest.fixture(scope="module")
def kesa():
    return T.made("loved", "Katana1Kesa")


@pytest.fixture(scope="module")
def table():
    return {n: CR.read(T.made(k, n)) for k, names in (("loved", LOVED), ("rejected", REJECTED)) for n in names}


def test_every_loved_and_rejected_cut_is_read_from_three_cameras(table):
    for name, r in table.items():
        assert r["striker"] == "BladeTip", name
        a, b = r["window"]
        assert 0 <= a < b, name
        assert set(r["cams"]) == {"behind", "left", "right"}
        for c in r["cams"].values():
            assert 0.0 <= c["seen"] <= 1.0 and 0.0 <= c["across"] <= 1.0
            assert abs(c["read"] - c["seen"] * c["across"]) < 2e-3
        assert r["read"] == min(c["read"] for c in r["cams"].values())
        assert CR.problem(r) is None, name


def test_it_does_not_tell_the_loved_from_the_rejected_so_it_is_no_gate(table):
    loved = [table[n]["read"] for n in LOVED]
    rejected = [table[n]["read"] for n in REJECTED]
    # (the rejected cuts read as well as the loved ones or better: no bar on `read` keeps one and drops the other)
    assert min(rejected) > min(loved)
    assert max(loved) > min(rejected)


def test_an_overhead_cut_goes_along_the_camera_from_behind_and_across_it_from_the_side(table):
    for name in ("GsCombo3Overhead", "Katana3Makko"):
        c = table[name]["cams"]
        assert max(c["left"]["across"], c["right"]["across"]) > c["behind"]["across"] + 0.15, name


def test_the_strike_holds_its_hit_on_every_cut_and_a_spin_is_not_all_strike(table):
    for kind, names in (("loved", LOVED), ("rejected", REJECTED)):
        for name in names:
            c = T.made(kind, name)
            fps = C.clip_fps(c)
            hit = int(round(next(e["t"] for e in c["events"] if e["name"] == "Hit") * fps))
            a, b = table[name]["window"]
            assert a <= hit <= b, (name, a, hit, b)          # (the first cut: 3 of the 7 loved cuts' windows missed it)
            assert hit - a <= round(CR.BEFORE * fps) and b - hit <= round(CR.AFTER * fps), name


def test_the_window_on_made_up_speeds():
    fps = 60
    path = np.zeros((120, 3))
    path[:, 0] = np.cumsum(np.r_[np.zeros(20), np.full(80, 0.5), np.zeros(20)])      # 80 frames at one speed
    clip = {"events": [{"name": "Hit", "t": 99 / fps}]}
    a, b = CR.strike_window(clip, path, fps)
    assert b - a <= round((CR.BEFORE + CR.AFTER) * fps) and a <= 99 <= b
    for t in (0.0, 119 / fps, 500.0):                                                # a Hit at an end, or past it
        a, b = CR.strike_window({"events": [{"name": "Hit", "t": t}]}, path, fps)
        assert 0 <= a < b <= 119
    a, b = CR.strike_window({"events": []}, path, fps)
    assert 0 <= a < b <= 119


def test_an_unarmed_strike_is_read_and_a_fist_in_front_of_the_chest_is_hidden_from_behind(kesa):
    c = copy.deepcopy(kesa)
    c.pop("sword", None)
    c.pop("grip", None)
    r = CR.read(c)
    assert r["striker"] in ("RightHand", "LeftHand", "RightFoot", "LeftFoot")
    assert all(0.0 <= v["seen"] <= 1.0 for v in r["cams"].values())
    M = np.eye(4)                                            # a torso at the origin, the camera 9 studs behind it
    import proc_dossier as PD
    fist, cam = np.array([0.0, 0.0, -0.6]), np.array([0.0, 0.0, 9.0])
    assert PD._segment_hits_box(M, [2.0, 2.0, 1.0], cam, fist)
    assert not CR._inside(M, [2.0, 2.0, 1.0], fist, part="Torso")
    assert CR._inside(M, [1.0, 2.0, 1.0], fist, part="Left Arm")


def test_a_sword_that_is_no_table_is_said_and_breaks_nothing(kesa):
    c = copy.deepcopy(kesa)
    c["sword"] = "none"
    g, bad = CR.gate(c)
    assert bad is None and (g is None or "error" in g or "cams" in g)
    assert CR.gate("nothing") == (None, None)


def test_a_hit_reaction_is_not_read(kesa):
    c = copy.deepcopy(kesa)
    c["name"] = "KatanaHitReactionLeftHeavy"
    assert CR.gate(c) == (None, None)


def test_a_striker_that_only_moves_along_the_cameras_line_is_seen_to_move_nothing():
    cam, aim = np.array([0.0, 2.0, 9.0]), np.array([0.0, 2.0, 0.0])
    a, da = CR.screen(cam, aim, [1.0, 2.0, 0.0])
    b, db = CR.screen(cam, aim, [1.0 * (9 - 4) / 9, 2.0, 4.0])       # on the same line of sight, nearer
    assert np.linalg.norm(a - b) < 1e-9 and db < da
    c, _ = CR.screen(cam, aim, [3.5, 2.0, 0.0])                      # 2.5 studs across at the body: half a body height
    assert abs(np.linalg.norm(c - a) - 0.5) < 1e-9


def test_the_camera_turns_about_the_body_and_follows_its_travel(kesa):
    c = copy.deepcopy(kesa)
    behind, aim = CR.camera_at(c, 0, 0.0)
    left, _ = CR.camera_at(c, 0, CR.CAMERAS["left"])
    right, _ = CR.camera_at(c, 0, CR.CAMERAS["right"])
    assert left[0] < 0 < right[0]                            # (+X is the body's right: the first cut had them swapped)
    assert abs(np.linalg.norm(behind[[0, 2]]) - np.linalg.norm(left[[0, 2]])) < 1e-9
    assert abs(behind[1] - left[1]) < 1e-9 and not np.allclose(behind, left)
    root = [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0] for _ in c["times"]]
    root[5] = [0.0, 0.0, 0.0, 1.0, 3.0, 1.5, -7.0]
    c["root"] = root
    moved, aim2 = CR.camera_at(c, 5, 0.0)
    assert np.allclose(moved - behind, [3.0, 0.0, -7.0]) and np.allclose(aim2 - aim, [3.0, 0.0, -7.0])
    # a body that BEGINS turned half round has the camera behind it there (its facing where the move begins)
    half = [[0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0] for _ in c["times"]]
    c["root"] = half
    turned, _ = CR.camera_at(c, 0, 0.0)
    assert np.allclose(turned[[0, 2]], -behind[[0, 2]], atol=1e-6)


def test_touching_a_block_is_not_being_hidden_behind_it():
    M = np.eye(4)
    assert CR._inside(M, [2.0, 2.0, 1.0], [0.9, 0.0, 0.55])
    assert not CR._inside(M, [2.0, 2.0, 1.0], [0.0, 0.0, 1.0])
    assert CR._owns("Right Arm", "RightHand") and not CR._owns("Torso", "RightHand")


def test_a_strike_never_seen_is_said_and_the_build_does_not_fail_on_it(kesa, monkeypatch):
    import proc_dossier as PD
    monkeypatch.setattr(PD, "blade_seen", lambda *a, **k: [False] * 6)
    r = CR.read(kesa)
    assert all(c["seen"] == 0 for c in r["cams"].values())
    said = CR.problem(r)
    assert said and "never seen" in said and f"{r['window'][0]}-{r['window'][1]}" in said
    g, bad = CR.gate(kesa)
    assert g["never_seen"] is True and bad is None


def test_a_clip_that_is_no_strike_is_not_read(kesa):
    c = copy.deepcopy(kesa)
    c["events"] = [e for e in c["events"] if e["name"] != "Hit"]
    assert CR.gate(c) == (None, None)
    c = copy.deepcopy(kesa)
    c["loop"] = True
    assert CR.gate(c) == (None, None)
    c = copy.deepcopy(kesa)
    c["rig"] = "R15"
    assert CR.gate(c) == (None, None)
    with pytest.raises(ValueError):
        CR.read(c)


def test_the_builds_motion_gates_carry_the_reading(kesa, tmp_path, capsys):
    p = tmp_path / "Kesa.clip.json"
    p.write_text(json.dumps(kesa), encoding="utf-8")
    MT.main([str(p)])
    capsys.readouterr()
    m = json.loads((tmp_path / "Kesa.metrics.json").read_text(encoding="utf-8"))
    assert m["camera"]["striker"] == "BladeTip" and m["camera"]["never_seen"] is False
    assert not any("never seen" in x for x in m["problems"])


def test_the_command_line_reads_a_clip_and_a_folder(kesa, tmp_path, capsys):
    p = tmp_path / "Kesa.clip.json"
    p.write_text(json.dumps(kesa), encoding="utf-8")
    assert CR.main([str(p)]) == 0
    one = json.loads(capsys.readouterr().out)
    assert one["status"] == "pass" and "from behind" in one["summary"]
    (tmp_path / "Kesa.preview.clip.json").write_text(json.dumps(kesa), encoding="utf-8")   # a working file: not read
    assert CR.main(["table", str(tmp_path)]) == 0
    rows = json.loads(capsys.readouterr().out)["rows"]
    assert len(rows) == 1 and rows[0]["name"] == kesa.get("name")
    assert CR.main([str(tmp_path / "none.json")]) == 1
