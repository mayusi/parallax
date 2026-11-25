"""kit/anim/cleanup.py op_gaps - frames the capture did not see are re-made and said, a contact is never invented
(the owner's limitations list 2026-11-15, A-R07). A cut the owner loved (generated in memory, read only) with frames
taken away on purpose: an occluded head, dropped frames, and what must be refused."""
import copy
import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import cleanup as CL     # noqa: E402
import clip as C         # noqa: E402
import derive as D       # noqa: E402
import strike as S       # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")


@pytest.fixture(scope="module")
def kesa():
    with open(LOVED, encoding="utf-8") as fh:
        return S.generate(json.load(fh))[0]


def off(a, b):
    """degrees between two frames' turns"""
    x, y = np.array(a[:4], float), np.array(b[:4], float)
    d = abs(float(np.dot(x, y))) / (np.linalg.norm(x) * np.linalg.norm(y))
    return float(np.degrees(2.0 * np.arccos(min(1.0, d))))


def occluded(clip, joint, first, last):
    """the joint's frames first..last replaced by a wrong pose, and the capture's own confidence saying so"""
    c = copy.deepcopy(clip)
    n = len(c["times"])
    for i in range(first, last + 1):
        c["joints"][joint]["frames"][i] = [0.6, 0.0, 0.0, 0.8, 0.0, 0.0, 0.0]
    c["confidence"] = {joint: [0.1 if first <= i <= last else 0.95 for i in range(n)]}
    return c


def test_an_occluded_stretch_is_re_made_between_its_neighbours_and_listed_for_review(kesa):
    bad = occluded(kesa, "Head", 8, 12)
    assert max(off(bad["joints"]["Head"]["frames"][i], kesa["joints"]["Head"]["frames"][i]) for i in range(8, 13)) > 30
    fixed = copy.deepcopy(bad)
    log = CL.op_gaps(fixed)
    assert "1 run(s) re-made" in log and "Head 8-12" in log and "REVIEW" in log
    assert fixed["gaps_filled"] == [["Head", 8, 12]]
    # each re-made frame is near what the clip really had (a head turns smoothly over 5 frames), and the known
    # frames, every other joint, the blade and the events are untouched
    assert max(off(fixed["joints"]["Head"]["frames"][i], kesa["joints"]["Head"]["frames"][i]) for i in range(8, 13)) < 8.0   # MEASURED: 6.0 degrees at worst (a line between two poses of a head that curves)
    for i in (7, 13, 30):
        assert fixed["joints"]["Head"]["frames"][i] == bad["joints"]["Head"]["frames"][i]
    for j in kesa["joints"]:
        if j != "Head":
            assert fixed["joints"][j]["frames"] == kesa["joints"][j]["frames"]
    assert fixed["sword"] == kesa["sword"] and fixed["events"] == kesa["events"] and fixed["times"] == kesa["times"]
    # one confidence list for every joint: read the same way
    one = [1.0] * len(kesa["times"])
    one[9] = 0.2
    assert all(v[9] and v.sum() == 1 for v in CL.unknown_frames(dict(kesa, confidence=one))[0].values())
    # a clip with every frame known is left as it is
    same = copy.deepcopy(kesa)
    assert "nothing re-made" in CL.op_gaps(same) and same == kesa


def test_dropped_frames_are_read_as_repeats_with_motion_either_side_and_a_held_pose_is_not(kesa):
    c = copy.deepcopy(kesa)
    c.pop("sword")                                               # (a body re-made under a blade that was not: refused, below)
    c2 = copy.deepcopy(c)
    for j in c2["joints"]:                                       # frames 16 and 17 never arrived: 15 was played three times
        for i in (16, 17):
            c2["joints"][j]["frames"][i] = list(c2["joints"][j]["frames"][15])
    assert CL.unknown_frames(c2)[1] == [] and "nothing re-made" in CL.op_gaps(copy.deepcopy(c2))      # only when asked
    unknown, drops = CL.unknown_frames(c2, dropped=True)
    assert drops == [16, 17] and all(unknown[j][16] and unknown[j][17] and unknown[j].sum() == 2 for j in unknown)
    log = CL.op_gaps(c2, dropped=True)
    assert "2 dropped frame(s) read as repeats (16, 17)" in log
    for j in c["joints"]:
        for i in (16, 17):
            assert off(c2["joints"][j]["frames"][i], c["joints"][j]["frames"][i]) < 4.0, (j, i)
        assert c2["joints"][j]["frames"][15] == c["joints"][j]["frames"][15]
    # a pose the clip HOLDS (longer than a dropped frame can be, or at its start or end) is the clip's own
    held = copy.deepcopy(c)
    for j in held["joints"]:
        for i in range(16, 30):
            held["joints"][j]["frames"][i] = list(held["joints"][j]["frames"][15])
    assert CL.unknown_frames(held, dropped=True)[1] == []
    assert CL.unknown_frames(c, dropped=True)[1] == []           # the loved cut itself has none
    # a repeat BESIDE AN EVENT is the clip's own (a hit-stop): never read as dropped, never a reason to fail
    hit = round(next(e["t"] for e in c["events"] if e["name"] == "Hit") * c["fps"])
    stop = copy.deepcopy(c)
    for j in stop["joints"]:
        stop["joints"][j]["frames"][hit + 1] = list(stop["joints"][j]["frames"][hit])
    assert CL.unknown_frames(stop, dropped=True)[1] == [] and "nothing re-made" in CL.op_gaps(stop, dropped=True)
    # a frame whose turns repeat while a part SLIDES is not a repeat
    slid = copy.deepcopy(c2)
    for i in (16, 17):
        slid["joints"]["Torso"]["frames"][i][5] += 0.05 * (i - 15)
    assert CL.unknown_frames(slid, dropped=True)[1] == []
    # with the sword still on (its own track arrived whole): the body is re-made under it and the hands are still on it
    armed = copy.deepcopy(kesa)
    for j in armed["joints"]:
        for i in (16, 17):
            armed["joints"][j]["frames"][i] = list(armed["joints"][j]["frames"][15])
    assert "2 dropped frame(s)" in CL.op_gaps(armed, dropped=True) and armed["sword"] == kesa["sword"]
    for j in kesa["joints"]:
        assert off(armed["joints"][j]["frames"][16], kesa["joints"][j]["frames"][16]) < 4.0


def test_a_contact_is_never_invented_and_a_missing_motion_is_not_a_missing_frame(kesa):
    n, fps = len(kesa["times"]), kesa["fps"]
    hit = round(next(e["t"] for e in kesa["events"] if e["name"] == "Hit") * fps)
    for first, last, why in ((hit, hit, "which is the (Hit|ActiveStart|ActiveEnd|Swing) event"), (0, 2, "which is the first frame"),
                             (n - 3, n - 1, "which is the last frame")):
        bad = occluded(kesa, "Head", first, last)
        before = copy.deepcopy(bad)
        with pytest.raises(ValueError, match=why):
            CL.op_gaps(bad)
        assert bad == before                                     # refused: the clip is as it was
    with pytest.raises(ValueError, match=r"Head is unknown for 12 frames \(8-19; at most 6: 0.1 s\) - that is a missing motion"):
        CL.op_gaps(occluded(kesa, "Head", 8, 19))
    assert "Head 8-19" in CL.op_gaps(occluded(kesa, "Head", 8, 19), max_gap=0.25)      # the recipe may allow more
    # a foot that LANDS or LIFTS inside the gap: nobody saw the contact. (The loved cut stands on both feet throughout:
    # the right leg is lifted for frames 30..40 to make a step.)
    bare = copy.deepcopy(kesa)
    bare.pop("sword")
    for i in range(36, 46):
        bare["joints"]["Right Leg"]["frames"][i][5] += 0.6
    on = CL._soles(bare, C.load_rig("r6"))["Right Leg"][1]
    assert on[34] and not on[37] and not on[43] and on[47]
    with pytest.raises(ValueError, match="Right Leg lands or lifts somewhere in frames 35-37, .* a contact is not invented"):
        CL.op_gaps(occluded(bare, "Right Leg", 35, 37))
    assert "Right Leg 39-41" in CL.op_gaps(occluded(bare, "Right Leg", 39, 41))        # in the air on both sides: re-made
    # a foot that stands on both sides stood through the gap: re-made, and it still stands where it stood
    through = occluded(bare, "Left Leg", 10, 11)
    assert "Left Leg 10-11" in CL.op_gaps(through)
    was, now = CL._soles(bare, C.load_rig("r6"))["Left Leg"], CL._soles(through, C.load_rig("r6"))["Left Leg"]
    assert (was[1] == now[1]).all() and float(np.abs(now[0] - was[0]).max()) < 0.04
    # the TORSO re-made under a blade that was not (the one review, 2026-11-15): it carries both hands and both legs,
    # so the fill is held to them - 3 frames keep the hands within the in-hand check's 0.1 studs and the feet standing
    torso = occluded(kesa, "Torso", 20, 22)
    assert "Torso 20-22" in CL.op_gaps(torso)
    import curves as CV
    d0, d1 = CV._hands_off_frames(kesa), CV._hands_off_frames(torso)
    assert all(float((d1[h] - d0[h]).max()) <= CV.HAND_OFF + 1e-6 for h in d0)
    r6 = C.load_rig("r6")
    assert all((CL._soles(kesa, r6)[f][1] == CL._soles(torso, r6)[f][1]).all() for f in ("Right Leg", "Left Leg"))
    # an arm that carries the weapon; a stepped clip; a confidence that cannot be read
    with pytest.raises(ValueError, match="studs from the weapon at frame"):
        CL.op_gaps(occluded(kesa, "Right Arm", 8, 10))
    for conf, why in (({"Tail": [1.0] * n}, "names Tail"), ({"Head": [1.0] * 3}, "one number \\(0..1\\) a frame"), ({"Head": "low"}, "one number"),
                      ({"Head": [95.0] * n}, "one number \\(0..1\\) a frame"), ({"Head": [float("inf")] * n}, "one number")):
        with pytest.raises(ValueError, match=why):
            CL.op_gaps(dict(copy.deepcopy(kesa), confidence=conf))


def test_it_is_an_op_of_a_derive_recipe(kesa, tmp_path, monkeypatch):
    src = tmp_path / "Occluded.clip.json"
    src.write_text(json.dumps(occluded(kesa, "Head", 8, 12)), encoding="utf-8")
    monkeypatch.setattr(D, "load_clip", lambda name: json.loads(src.read_text(encoding="utf-8")))
    out = D.derive({"name": "Cleaned", "from": "Occluded", "ops": [{"op": "gaps"}]})
    clip = out[0] if isinstance(out, tuple) else out
    assert clip["name"] == "Cleaned" and clip["gaps_filled"] == [["Head", 8, 12]]
    assert max(off(clip["joints"]["Head"]["frames"][i], kesa["joints"]["Head"]["frames"][i]) for i in range(8, 13)) < 8.0   # MEASURED: 6.0 degrees at worst (a line between two poses of a head that curves)


def test_the_recipes_own_words_are_checked(kesa):
    for more, why in (({"min_conf": 30}, "\"min\" is the confidence"), ({"max_gap": 0}, "\"max_gap\" is seconds"),
                      ({"dropped": "false"}, "\"dropped\" is true or false")):
        with pytest.raises(ValueError, match=why):
            CL.op_gaps(copy.deepcopy(kesa), **more)
