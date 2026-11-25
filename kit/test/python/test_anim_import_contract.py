"""kit/anim/frame_contract.py's IMPORT ROUTE: a calibration skeleton built in Blender (kit/anim/import_calibration_blend.py)
and brought in by kit/anim/retarget.py must turn each part as written by hand, in Roblox's axes; centimetres and a
skeleton facing another way must not matter; a skeleton whose left / right labels lie must fail. Runs Blender (about
10 s); skipped on a machine without it."""
import copy
import json
import math
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
import clip as C                 # noqa: E402
import frame_contract as F       # noqa: E402

BLENDER = os.environ.get("KIT_BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")
blender = pytest.mark.skipif(not os.path.isfile(BLENDER), reason="Blender is not on this machine")


def test_the_turns_are_written_by_hand_in_roblox_axes():
    rig = C.load_rig("r15")
    rest = C.fk(rig)
    down = F._chain(rig, rest, "RightUpperArm", "RightHand")
    ahead = F._turned(*F.IMPORT_TURNS[1][2:], down)
    assert ahead[2] < -0.9 and abs(ahead[1]) < 1e-9          # the right arm's line, hanging -> ahead (-Z)
    left = F._turned(*F.IMPORT_TURNS[2][2:], F._chain(rig, rest, "LeftUpperArm", "LeftHand"))
    assert left[0] < -0.9                                     # the left arm out to its left (-X)
    assert F.IMPORT_LOOK[3] == (-1.0, 0.0, 0.0) and F.IMPORT_RISE == {4: 0.2}
    leg = F._turned(*F.IMPORT_TURNS[4][2:], F._chain(rig, rest, "RightUpperLeg", "RightFoot"))
    assert abs(leg[1] + math.sqrt(0.5)) < 0.05 and abs(leg[2] + math.sqrt(0.5)) < 0.05


def test_a_clip_that_is_not_the_calibrations_import_is_refused_not_passed():
    assert F.check_import({"rig": "R6", "times": [0] * 5})
    assert F.check_import({"rig": "R15", "times": [0, 1]})
    assert F.check_import("x")


@blender
def test_the_import_route_keeps_the_contract_and_a_lying_skeleton_does_not(tmp_path):
    clip = F.import_run(str(tmp_path / "ok"))
    assert clip["rig"] == "R15" and len(clip["times"]) == 5
    assert F.check_import(clip) == []
    assert clip["_route"]["status"] == "pass" and clip["_route"]["axes_disagree"] is False
    # the same check finds doctored copies: the right arm's turn reversed; the arm twisted about its own line (its
    # line is right, its turn is not: the first cut missed it); the left leg lifted in every pose
    def doctored(part, q):
        bad = copy.deepcopy(clip)
        n = len(bad["times"])                                 # (the route writes only the joints that move)
        bad["joints"].setdefault(part, {"frames": [[0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0] for _ in range(n)]})
        for i, f in enumerate(bad["joints"][part]["frames"]):
            R = C.quat_mat(q) @ C.quat_mat(f[:4])
            bad["joints"][part]["frames"][i] = [float(v) for v in C.mat_quat(R)] + f[4:]
        return F.check_import(bad)
    s, c = math.sin(math.radians(45)), math.cos(math.radians(45))
    assert any("RightUpperArm" in o for o in doctored("RightUpperArm", [0.0, 1.0, 0.0, 0.0]))       # 180 about Y
    assert any("RightUpperArm is turned" in o for o in doctored("RightUpperArm", [0.0, s, 0.0, c]))  # a twist
    assert any("LeftUpperLeg is turned" in o for o in doctored("LeftUpperLeg", [s / 1.5, 0.0, 0.0, math.sqrt(1 - (s / 1.5) ** 2)]))
    # centimetres, facing a quarter round, toe-out: the same clip
    for kw in ({"scale": 100.0}, {"turn": 90.0}, {"splay": 12.0}):
        other = F.import_run(str(tmp_path / "v"), **kw)
        assert F.check_import(other) == [] and other["_route"]["axes_disagree"] is False, kw
    # T-posed, with the route's own "auto" arms: its arms out at rest, then ahead
    t = F.import_run(str(tmp_path / "t"), tpose=True)
    assert F.check_import(t, whole=False) == [] and "T-posed" in t["_route"]["summary"]
    # labels that lie: refused by the calibration, and SAID by the route
    mirrored = F.import_run(str(tmp_path / "mirror"), mirror=True)
    off = F.check_import(mirrored)
    assert any("pose 1" in o for o in off) and any("pose 2" in o for o in off)
    assert mirrored["_route"]["axes_disagree"] is True and "hands and its toes disagree" in mirrored["_route"]["summary"]


@blender
def test_a_body_that_rises_is_not_read_as_a_taller_one(tmp_path):
    # (the calibration found it, 2026-11-16: the route took the clip's highest head over its lowest foot for the
    # body's height, so a body that rises came in smaller - a 0.2 m rise of a 1.73 m body 10% short; the height is
    # now read off the bones, and a body that never stands reads as tall as it is too)
    clip = F.import_run(str(tmp_path / "ok"))
    rig = C.load_rig("r15")
    W = C.world_frames({k: v for k, v in clip.items() if k != "root"}, rig)
    rise = float(np.asarray(W[4]["LowerTorso"])[1, 3] - np.asarray(W[0]["LowerTorso"])[1, 3])
    r15_height = ((rig["rest"]["Head"][1] + rig["sizes"]["Head"][1] / 2)
                  - (rig["rest"]["RightFoot"][1] - rig["sizes"]["RightFoot"][1] / 2))
    assert abs(rise - 0.2 * r15_height / F.SRC_HEIGHT) < 0.01
    assert abs(clip["_route"]["scale"] - r15_height / F.SRC_HEIGHT) < 0.01      # the height read off the bones: 1.73
