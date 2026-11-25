"""kit/anim/curves.py - the curve tools of a `kit anim derive` recipe (the owner's method lists 2026-11-13: Graph Editor
editing - a signal filter and tangent handles), and what they refuse. The clip is a cut the owner loved, generated in
memory (read only)."""
import copy
import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import curves as CV         # noqa: E402
import strike as S          # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")


def kesa(**more):
    with open(LOVED, encoding="utf-8") as fh:
        return S.generate({**json.load(fh), **more})[0]


def noisy(c, joints=("Head",), deg=1.5, seed=3):
    rng = np.random.default_rng(seed)
    c = copy.deepcopy(c)
    for j in joints:
        F = np.array(c["joints"][j]["frames"])
        for i in range(len(F)):
            F[i, :3] += rng.normal(size=3) * np.sin(np.radians(deg) / 2)
            F[i, :4] /= np.linalg.norm(F[i, :4])
        c["joints"][j]["frames"] = F.tolist()
    return c


def frame(c, j, i):
    return np.array(c["joints"][j]["frames"][i])


def apart(a, b, j="Head"):
    return float(np.mean([np.linalg.norm(frame(a, j, i)[:4] - frame(b, j, i)[:4]) for i in range(len(a["times"]))]))


def hit_frame(c):
    return round(next(e["t"] for e in c["events"] if e["name"] == "Hit") * c["fps"])


def test_a_filter_brings_a_shaking_joint_back_toward_the_clean_one_and_keeps_the_hit_and_both_ends():
    c = kesa()
    n = noisy(c)
    assert CV.roughness(n, "Head") > 1.5 * CV.roughness(c, "Head")
    f = copy.deepcopy(n)
    said = CV.op_filter(f, 8, ["Head"])
    assert apart(f, c) < 0.75 * apart(n, c)                    # NEARER the clean clip, not merely smoother
    assert CV.roughness(f, "Head") < CV.roughness(n, "Head")
    last = len(c["times"]) - 1
    for i in (0, hit_frame(c), last):
        assert np.allclose(frame(f, "Head", i), frame(n, "Head", i), atol=1e-5)
    for j in ("Torso", "Right Arm", "Left Arm"):
        assert f["joints"][j]["frames"] == n["joints"][j]["frames"]            # a joint not named is not touched
    assert f["sword"] == n["sword"]                                           # the blade is never filtered
    assert f"frames 0, {hit_frame(c)}, {last}" in said and "taken out of Head" in said
    assert all(abs(np.linalg.norm(np.array(q[:4])) - 1.0) < 1e-5 for q in f["joints"]["Head"]["frames"])


def test_a_moment_named_in_keep_is_exact_too():
    n = noisy(kesa())
    f = copy.deepcopy(n)
    CV.op_filter(f, 8, ["Head"], keep=[0.2])
    assert np.allclose(frame(f, "Head", 12), frame(n, "Head", 12), atol=1e-5)
    g = copy.deepcopy(n)
    CV.op_filter(g, 8, ["Head"])
    assert not np.allclose(frame(g, "Head", 12), frame(n, "Head", 12), atol=1e-4)        # (without it that frame is filtered)


@pytest.mark.parametrize("joints", [None, ["Torso"], ["Right Arm"], ["Left Arm"]])
def test_a_filter_that_takes_a_hand_off_the_weapon_is_refused_and_changes_nothing(joints):
    c = kesa()
    before = copy.deepcopy(c)
    with pytest.raises(ValueError, match="hand .* studs off the weapon"):
        CV.op_filter(c, 8, joints)
    assert c == before


def test_a_filter_that_takes_the_motion_itself_is_refused_unless_it_is_asked_to_soften():
    c = kesa()
    before = copy.deepcopy(c)
    with pytest.raises(ValueError, match="Head's reach from .* that is the motion, not shake"):
        CV.op_filter(c, 1, ["Head"])
    assert c == before
    assert "taken out of Head" in CV.op_filter(c, 1, ["Head"], soften=True)
    legs = kesa()
    assert "Right Leg, Left Leg" in CV.op_filter(legs, 8, ["Right Leg", "Left Leg"])     # the legs carry no weapon


def test_a_stepped_clip_is_not_filtered():
    stepped = kesa(step={"on": 3, "beats": "all"})
    assert stepped.get("stepped")
    with pytest.raises(ValueError, match="STEPPED"):
        CV.op_filter(stepped, 8, ["Head"])


def test_the_filters_cutoff_is_what_it_says():
    c = kesa()
    c["events"] = []
    n = len(c["times"])
    for hz, lo, hi in ((4, 0.75, 1.0), (8, 0.4, 0.6), (20, 0.0, 0.15)):       # at the cutoff (8): half gets through
        w = copy.deepcopy(c)
        base = np.array([[0.0, 0.0, 0.0, 1.0, 0, 0, 0]] * n)
        wob = base.copy()
        wob[:, 0] = np.sin(np.radians(2.0) / 2) * np.sin(2 * np.pi * hz * np.arange(n) / 60.0)
        wob[:, :4] /= np.linalg.norm(wob[:, :4], axis=1, keepdims=True)
        w["joints"]["Head"]["frames"] = wob.tolist()
        CV.op_filter(w, 8, ["Head"], ease=0.0, soften=True)
        mid = slice(12, n - 12)
        gain = float(np.abs(np.array(w["joints"]["Head"]["frames"])[mid, 0]).max() / np.abs(wob[mid, 0]).max())
        assert lo <= gain <= hi, (hz, gain)


@pytest.mark.parametrize("kw, why", [({"hz": 0}, "hz is how many"), ({"hz": 500}, "hz is how many"), ({"hz": True}, "hz is how many"),
                                     ({"joints": ["Tail"]}, "joints is a list"), ({"joints": "Torso"}, "joints is a list"),
                                     ({"joints": []}, "joints is a list"), ({"keep": 0.43}, "keep is a list"),
                                     ({"keep": ["x"]}, "keep is a list"), ({"ease": -1}, "ease is a time")])
def test_a_filter_that_cannot_be_what_was_asked_is_refused(kw, why):
    with pytest.raises(ValueError, match=why):
        CV.op_filter(kesa(), **{"hz": 8, "joints": ["Head"], **kw})


def blade(c, i):
    return float(np.linalg.norm(np.array(c["sword"]["tip"][i]) - np.array(c["sword"]["grip_path"][i])))


def test_handles_replay_a_stretch_and_keep_its_two_poses_the_length_and_the_blade():
    c = kesa()
    h = copy.deepcopy(c)
    said = CV.op_handles(h, 0.2, 0.4, [0.2, 1.0], [0.8, 0.0])                # away fast, a near hold, in fast
    assert h["times"] == c["times"]
    for i in list(range(0, 13)) + list(range(24, len(c["times"]))):          # outside the stretch: as it was
        assert np.allclose(frame(h, "Right Arm", i), frame(c, "Right Arm", i), atol=1e-5)
    assert not np.allclose(frame(h, "Right Arm", 15), frame(c, "Right Arm", 15), atol=1e-3)
    tip = lambda x, i: np.array(x["sword"]["tip"][i])                         # noqa: E731
    assert np.linalg.norm(tip(h, 14) - tip(h, 12)) > 1.5 * np.linalg.norm(tip(c, 14) - tip(c, 12))    # it leaves faster
    assert all(abs(blade(h, i) - blade(c, i)) < 0.02 for i in range(len(c["times"])))                  # the blade's length
    assert all(abs(np.linalg.norm(e) - 1.0) < 1e-4 for e in h["sword"]["edge"])
    assert "both poses and the length kept" in said
    same = copy.deepcopy(c)
    CV.op_handles(same, 0.2, 0.4)                              # the straight handles: nothing moves
    assert max(float(np.abs(frame(same, "Right Arm", k) - frame(c, "Right Arm", k)).max()) for k in range(len(c["times"]))) < 1e-5


def test_handles_that_break_the_cut_are_refused_and_change_nothing():
    c = kesa()
    before = copy.deepcopy(c)
    with pytest.raises(ValueError, match="the stretch holds a Hit"):
        CV.op_handles(c, 0.2, 0.6, [0.6, 0.0], [0.2, 1.0])
    with pytest.raises(ValueError, match="a hold, then a snap that pops"):
        CV.op_handles(c, 0.0, 0.42, [1.0, 0.0], [1.0, 0.0])    # held to the last moment, then all of it at once
    assert c == before


@pytest.mark.parametrize("args, why", [((0.4, 0.2), "two moments of the clip"), ((0.2, 0.21), "two moments of the clip"),
                                       ((0.2, 9.0), "two moments of the clip"), ((0.2, 0.4, [1.5, 0]), "`out` is"),
                                       ((0.2, 0.4, [0.3, 0.3], [0.5, -1]), "`in` is"), ((0.2, 0.4, "x"), "`out` is"),
                                       ((None, 0.4), "times in seconds"), ((0.2, "late"), "times in seconds")])
def test_handles_that_run_backwards_or_outside_the_clip_are_refused(args, why):
    with pytest.raises(ValueError, match=why):
        CV.op_handles(kesa(), *args)


def test_both_are_ops_of_a_derive_recipe(tmp_path, monkeypatch):
    import derive as D
    src = tmp_path / "Base.clip.json"
    src.write_text(json.dumps(noisy(kesa())), encoding="utf-8")
    monkeypatch.setattr(D, "load_clip", lambda name: json.load(open(str(src), encoding="utf-8")))
    out = D.derive({"name": "Cleaned", "from": "Base", "ops": [{"op": "filter", "hz": 8, "joints": ["Head"]},
                                                               {"op": "handles", "from": 0.2, "to": 0.4, "out": [0.2, 1], "in": [0.8, 0]}]})
    clip = out[0] if isinstance(out, tuple) else out
    assert clip["name"] == "Cleaned" and CV.roughness(clip, "Head") < CV.roughness(noisy(kesa()), "Head")
    for bad, why in (({"op": "filter", "hz": 0}, "hz is how many"), ({"op": "filter", "keep": 0.43}, "keep is a list"),
                     ({"op": "handles", "from": None, "to": 0.4}, "times in seconds"), ({"op": "handles", "to": 0.4}, "from")):
        with pytest.raises((ValueError, KeyError), match=why):
            D.derive({"name": "Bad", "from": "Base", "ops": [bad]})
