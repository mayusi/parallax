"""kit/anim/cycle_r6.py + kit/anim/silhouette.py + the profile's shape checks: a cycle learned from a clip keeps the
clip's measured poses, rebuilds a closed, mirrored loop, and the same-side arm / leg fault is caught"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "anim"))
import clip as C           # noqa: E402
import cycle_r6 as CY      # noqa: E402
import anim_profile as PR  # noqa: E402
import importlib.util       # noqa: E402

# kit/anim/silhouette.py is loaded under its OWN name: a bare `import silhouette` cached the anim module in the shared
# test process and kit/vfx/lore.py then got it instead of kit/vfx/silhouette.py (test_vfx_lore failed only in the full run)
_spec = importlib.util.spec_from_file_location("kit_anim_silhouette", os.path.join(HERE, "..", "..", "anim", "silhouette.py"))
SI = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SI)

from test_anim_profile import cycle, sine  # noqa: E402


def write(tmp_path, clip, name="T"):
    p = tmp_path / f"{name}.clip.json"
    p.write_text(json.dumps(clip), encoding="utf-8")
    return str(p)


def test_a_pure_swing_measures_no_slide():
    rig = C.load_rig("r6")
    c = cycle(sine(50), sine(50, 0.5), sine(30, 0.5), sine(30))
    fr = C.world_frames(c, rig)
    for i in (0, 7, 13):
        sw, sl = CY.leg_of(fr[i]["Torso"], fr[i]["Right Leg"])
        assert abs(abs(sw) - abs(50 * math.sin(2 * math.pi * i / 40))) < 0.5   # (the helper's joint sign is not world's)
        assert max(abs(v) for v in sl) < 1e-6          # the leg is where a clean swing about the hip puts it


def test_learn_reads_the_step_from_the_forward_reach(tmp_path):
    c = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40))
    p = CY.learn(write(tmp_path, c), phases=4)
    t = p["table"]
    assert len(t) == 4 and abs(p["cycle"] - 40) < 1e-6
    assert abs(t[0]["F_leg"]["swing"] - 60) < 1.5 and abs(t[0]["B_leg"]["swing"] + 60) < 1.5   # contact: F forward
    assert abs(t[2]["F_leg"]["swing"]) < 2 and abs(t[2]["B_leg"]["swing"]) < 2                  # passing: legs cross
    assert t[0]["B_hand"][2] > 0.5 > t[0]["F_hand"][2]        # the arm opposite the forward leg is forward


def test_build_closes_the_loop_and_mirrors_the_second_step(tmp_path):
    c = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40))
    presets = {"run": CY.learn(write(tmp_path, c), phases=4)}
    spec = CY.build("run", "X", {"asym": 1.0}, presets)
    k = spec["keys"]
    assert len(k) == 9 and k[-1]["f"] == spec["cycle"]["knobs"]["cycle"]
    assert {x: k[-1][x] for x in k[-1] if x != "f"} == {x: k[0][x] for x in k[0] if x != "f"}
    a, b = k[0], k[4]                                          # right contact vs left contact
    assert abs(a["right_leg"]["swing"] - b["left_leg"]["swing"]) < 1e-6
    assert abs(a["left_arm"]["hand"][0] + b["right_arm"]["hand"][0]) < 1e-6
    assert all(x["body"]["plant"] == "both" for x in k)


def test_scale_grows_the_swings_about_the_mean():
    t = [{"lean": 10, "turn": 5, "tilt": 0, "head_look": [0, 0, 1], "head_tilt": 0, "low": 0.1,
          "F_leg": {"swing": s, "slide": [0, 0, 0.4]}, "B_leg": {"swing": -s, "slide": [0, 0, 0.4]},
          "F_hand": [1.5, 2.3, -1.0], "B_hand": [-1.5, 2.3, 1.0]} for s in (60, 30, 0, -30)]
    presets = {"run": {"from": "T", "cycle": 40, "phases": 4, "table": t}}
    k1 = CY.build("run", "X", {"scale": 1.0}, presets)["keys"]
    k2 = CY.build("run", "X", {"scale": 1.2}, presets)["keys"]
    assert abs(k2[0]["right_leg"]["swing"] - 72) < 1e-6 and abs(k1[0]["right_leg"]["swing"] - 60) < 1e-6
    assert k2[0]["left_arm"]["hand"][2] > k1[0]["left_arm"]["hand"][2]


def test_unknown_knob_is_refused(capsys):
    assert CY.main(["run", "--as", "X", "--params", '{"nope": 1}', "--out", os.devnull]) == 1
    assert "unknown knob" in capsys.readouterr().out


def test_same_side_arm_and_leg_is_a_fault():
    bad = PR.profile(cycle(sine(60), sine(60, 0.5), sine(40), sine(40, 0.5)))
    good = PR.profile(cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40)))
    assert any("WITH its own leg" in f for f in bad.get("faults", []))
    assert not any("WITH its own leg" in f for f in good.get("faults", []))
    assert "forward hand from midline" in good and "heel kick" in good


def test_silhouette_sheet_renders(tmp_path):
    c = cycle(sine(60), sine(60, 0.5), sine(40, 0.5), sine(40))
    src = write(tmp_path, c)
    out = str(tmp_path / "T.sil.png")
    assert SI.main([src, "--vs", src, "--frames", "4", "--out", out]) == 0
    assert os.path.getsize(out) > 5000
