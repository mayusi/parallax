"""kit/anim/pose_from.py - what a clip says rides through `kit anim derive` (the owner's V3 list, anim stage C.2;
card r66z): the derive command rebuilds its clip from reduced body keys (pose_from -> pose_r6 in Blender), which
carried no weapon and none of the clip's own fields - a grip solve, a said slide, a beat or a Hit was thrown away.
Measured once through the owner's rig (card a77q): the loved kesa's weapon comes back within 2 degrees (median) of
its source, its hands within 0.1 studs."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
os.chdir(ROOT)
import grip as GR            # noqa: E402
import numpy as np           # noqa: E402
import pose_from as PF       # noqa: E402
import strike as S           # noqa: E402

LOVED = os.path.join(ROOT, "kit", "selftest", "anim", "faults", "loved", "Katana1Kesa.move.json")


def kesa():
    with open(LOVED, encoding="utf-8") as fh:
        c = S.generate(json.load(fh))[0]
    GR.add_grip(c)
    return c


def test_the_weapon_and_what_the_clip_says_are_written_into_the_pose_file():
    c = kesa()
    c.update(hands="two", beats={"wind": [0.0, 0.2], "cut": [0.2, 0.4]}, slides={"Right Leg": [[0.1, 0.3]]},
             match={"pose": True}, on_blade={"left": [[0.5, 0.6]]})
    spec = PF.pose_from(c, "Probe", reduce=2.0)
    for k in ("events", "beats", "hands", "slides", "match", "on_blade"):
        assert spec[k] == c[k], k
    sw = spec["sword"]
    assert sw["grip"] == "animated" and sw["kind"] == "katana" and sw["spacing"] == c["sword"]["grip"]
    reach = float(np.median([np.linalg.norm(np.subtract(t, g)) for t, g in zip(c["sword"]["tip"], c["sword"]["grip_path"])]))
    assert abs(sw["blade"] + 0.36 + sw["spacing"] / 2 - reach) < 1e-3      # the bake puts the tip where the source has it
    arms = [k["right_arm"] for k in spec["keys"] if "right_arm" in k]
    assert arms and all("blade" in a and "edge" in a for a in arms)
    # each key's blade is the source's direction at that frame, in stage axes (x right, y up, z forward)
    k0 = next(k for k in spec["keys"] if "right_arm" in k)
    i = int(round(k0["f"] / 60.0 * float(c.get("fps") or 60)))
    d = np.subtract(c["sword"]["tip"][i], c["sword"]["grip_path"][i])
    d = d / np.linalg.norm(d)
    assert np.allclose(k0["right_arm"]["blade"], [d[0], d[1], -d[2]], atol=1e-3)
    # the left arm (on the hilt) is keyed wherever the right arm is: the hilt moves with it
    right = {k["f"] for k in spec["keys"] if "right_arm" in k}
    left = {k["f"] for k in spec["keys"] if "left_arm" in k}
    assert right <= left


def test_a_clip_with_no_weapon_and_nothing_said_writes_neither():
    c = kesa()
    for k in ("sword", "grip"):
        c.pop(k, None)
    spec = PF.pose_from(c, "Probe", reduce=2.0)
    assert "sword" not in spec and not any("blade" in (k.get("right_arm") or {}) for k in spec["keys"])
    assert "hands" not in spec and spec.get("beats") == c.get("beats") and spec["events"] == c["events"]


def test_the_wrist_plane_lock_names_every_frame_s_blade_and_the_left_hand_on_the_line():
    """V4 4.4 / 13.4.2: the pose file names the blade, its edge and the left hand's place along it at EVERY reference
    frame, for the bake to key the weapon's turn in the fist frame by frame - measured through the owner's rig with the
    bake's half (pose_r6.lock_grip, held: it re-stales every pose-route clip) on the loved Katana1Kesa / Katana3Makko /
    GsCombo3Overhead: blade 15.6 deg -> 0.006 deg at worst, left hand 0.14 -> 0.0001 studs off the line"""
    import clip as C
    c = kesa()
    spec = PF.pose_from(c, "Probe", reduce=2.0)
    lock = spec["sword"]["lock"]
    n = len(c["times"])
    assert len(lock) == n and all(e["f"] == round(float(t) * 60.0, 3) for e, t in zip(lock, c["times"]))
    rig = C.load_rig("r6")
    W = C.world_frames(c, rig)
    on = 0
    for i, e in enumerate(lock):
        d = np.subtract(c["sword"]["tip"][i], c["sword"]["grip_path"][i])
        d = d / np.linalg.norm(d)
        assert np.allclose(e["blade"], [d[0], d[1], -d[2]], atol=1e-3)
        assert len(e["edge"]) == 3
        hr = (W[i]["Right Arm"] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]
        hl = (W[i]["Left Arm"] @ np.array([0.0, -1.0, 0.0, 1.0]))[:3]
        g = np.array(c["sword"]["grip_path"][i], float)
        off = float(np.linalg.norm(hl - (g + float(np.dot(hl - g, d)) * d)))
        if off <= PF.ON_LINE:
            on += 1
            assert abs(e["left"] - float(np.dot(hl - hr, d))) < 1e-3     # where along the blade from the right fist
        else:
            assert "left" not in e                                       # a hand off the weapon is left to its keys
    assert on == n                                                       # (the kesa is two-handed throughout)


def test_a_one_handed_reference_locks_the_blade_and_leaves_the_left_arm_to_its_keys():
    c = kesa()
    for i in range(len(c["times"])):                                     # the left hand taken well off the weapon
        f = c["joints"]["Left Arm"]["frames"][i]
        c["joints"]["Left Arm"]["frames"][i] = [0.0, 0.0, 0.0, 1.0, *f[4:7]]
    spec = PF.pose_from(c, "Probe", reduce=2.0)
    assert spec["sword"]["lock"] and not any("left" in e for e in spec["sword"]["lock"])
