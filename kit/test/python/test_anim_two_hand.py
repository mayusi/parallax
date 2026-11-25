"""proc_blade's TWO-HANDED weapons + intent on a blade (2026-11-11, the kit home's katana kesa on the procedural route):
both fists stay on the hilt every frame, the blade line passes through each beat's designed blade, a weapon's intent is
read on the blade's own sweep, the katana as designed reads calm, and an intent's aim retimes the cut while the clip
keeps its length"""
import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
os.chdir(ROOT)
import clip as C               # noqa: E402
import intent as I             # noqa: E402
import proc_blade as PB        # noqa: E402
import proc_dossier as DS      # noqa: E402

_B = {}
_KATANA_DOSSIER = os.path.join(ROOT, "assets", "animations", "dossiers", "katana_kesa.json")


def katana():
    d = DS.require("katana_kesa")
    sw = json.load(open(d["build"]["move_file"], encoding="utf-8"))["sword"]
    return {**d, "build": {**d["build"], "gestures": {"*": "katana_kesa_cut"}, "sword": sw}}


def built(intent=None, s=None):
    k = (intent, json.dumps(s or {}, sort_keys=True))
    if k not in _B:
        _B[k] = PB.build(katana(), {**(s or {}), "arms": PB.HABITS[0]}, "TwoHandTest", intent=intent)
    return _B[k]


def test_both_fists_stay_on_the_hilt_every_frame():
    if not os.path.isfile(_KATANA_DOSSIER):
        pytest.skip("the author's assets/animations/dossiers/katana_kesa.json is not shipped with the kit")
    c, _ = built()
    g = PB.gesture_for(katana(), "x")
    rig = C.load_rig("r6")
    for t in range(len(c["times"])):
        F = C.fk(rig, C.character_transforms(c, rig, t))
        hi = (F["Right Arm"] @ np.r_[0.0, -1.0, 0.0, 1.0])[:3]
        lo = (F["Left Arm"] @ np.r_[0.0, -1.0, 0.0, 1.0])[:3]
        assert abs(float(np.linalg.norm(hi - lo)) - g["grip_spacing"]) < 0.05, t


def test_the_blade_runs_along_the_hilt_from_the_lower_fist():
    if not os.path.isfile(_KATANA_DOSSIER):
        pytest.skip("the author's assets/animations/dossiers/katana_kesa.json is not shipped with the kit")
    c, _ = built()
    rig = C.load_rig("r6")
    F = C.fk(rig, C.character_transforms(c, rig, 20))
    hi = (F["Right Arm"] @ np.r_[0.0, -1.0, 0.0, 1.0])[:3]
    lo = (F["Left Arm"] @ np.r_[0.0, -1.0, 0.0, 1.0])[:3]
    tip, grip = np.asarray(c["sword"]["tip"][20]), np.asarray(c["sword"]["grip_path"][20])
    assert np.allclose(grip, 0.5 * (hi + lo), atol=1e-3)
    assert float(PB.unit(tip - grip) @ PB.unit(hi - lo)) > 0.999


def test_the_designed_blade_passes_through_each_beat():
    if not os.path.isfile(_KATANA_DOSSIER):
        pytest.skip("the author's assets/animations/dossiers/katana_kesa.json is not shipped with the kit")
    g = PB.gesture_for(katana(), "x")
    beats, _, _, _ = PB.effort(g, {"time": 0.0, "weight": 0.0, "space": 0.0, "flow": 0.0})
    n = int(round(beats[-1]["t"] * 60)) + 1
    line = PB.designed_blade(beats, n)
    for b in beats:
        if b.get("sword", {}).get("blade") is not None and b["t"] * 60 == int(b["t"] * 60):
            assert float(line[int(b["t"] * 60)] @ PB.unit(b["sword"]["blade"])) > 0.999, b["name"]


def test_a_weapon_reads_its_intent_on_the_blade_and_the_kesa_as_designed_is_calm():
    if not os.path.isfile(_KATANA_DOSSIER):
        pytest.skip("the author's assets/animations/dossiers/katana_kesa.json is not shipped with the kit")
    c, _ = built()
    x = I.main_strike(c)
    assert x["joint"] == "Blade"
    assert I.read(c)["intent"] == "calm"


def test_an_intent_retimes_the_cut_and_the_clip_keeps_its_length():
    if not os.path.isfile(_KATANA_DOSSIER):
        pytest.skip("the author's assets/animations/dossiers/katana_kesa.json is not shipped with the kit")
    g = PB.gesture_for(katana(), "x")
    s = {"time": 0.0, "weight": 0.0, "space": 0.0, "flow": 0.0}
    base = {b["name"]: b["t"] for b in PB.effort(g, s)[0]}
    calm = {b["name"]: b["t"] for b in PB.effort(g, s, "calm")[0]}
    aggr = {b["name"]: b["t"] for b in PB.effort(g, s, "aggressive")[0]}
    cut = lambda bt: bt["through"] - bt["furikaburi"]  # noqa: E731
    assert cut(calm) > cut(base) * 1.1 and cut(aggr) < cut(base) * 0.55
    for bt in (calm, aggr):                                  # the held zanshin pays the time back
        assert abs(bt["chudan_end"] - base["chudan_end"]) < 1e-3
