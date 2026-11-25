"""kit/anim/intent.py + proc_candidates' intent input (the owner, 2026-11-10: "there's aggressive, there's calm, there is
proper ... this is just a calm roundhouse kick"): the loved strikes' tempo thirds are ordered, a strike reads as the third
its tempo falls in, a kick's keys are aimed at an intent (a shorter strike window, the hips leading), each intent samples
its own efforts, and the roundhouse built as the dossier measured it reads CALM while the same kick aimed at aggressive
(strong, bound) reads AGGRESSIVE"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
os.chdir(ROOT)
import intent as I              # noqa: E402
import proc_candidates as PCD   # noqa: E402
import proc_dossier as DS       # noqa: E402
import proc_kick as PK          # noqa: E402

_KICK = {}


def keys():
    return PK.carry(DS.require("roundhouse_kick")["build"]["keys"])


def kick(intent, s):
    k = (intent, tuple(sorted(s.items())))
    if k not in _KICK:
        d = DS.require("roundhouse_kick")
        ks = PCD.apply_arms(PCD.aim_intent(PCD.apply_sliders(keys(), s, 2), intent, s), "technique", seed=0)
        dk = PCD.kick_dossier(d, s, 2)
        _KICK[k] = PK.build(dk, keys=ks, follow=PCD.follow_of(s, 2), name="intent_test", rng=PK.slide_ranges())
    return _KICK[k]


def test_the_loved_tempo_thirds_are_ordered():
    cal = I.cal()
    lo, hi = cal["tempo_cuts_deg_s"]
    assert 0 < lo < hi
    med = [cal["intents"][x]["tempo_deg_s"]["p50"] for x in I.INTENTS]
    assert med[0] < lo < med[1] < hi < med[2]
    # faster tempo = a shorter snap: the thirds' snaps fall calm > proper > aggressive
    snaps = [cal["intents"][x]["snap_frames"]["p50"] for x in I.INTENTS]
    assert snaps[0] > snaps[1] > snaps[2]


def test_a_strike_reads_as_the_third_its_tempo_falls_in():
    lo, hi = I.cal()["tempo_cuts_deg_s"]
    one = {"amp_deg": 120.0}
    assert I.classify({**one, "snap_frames": int(120 / (lo * 0.5) * 60)}) == "calm"
    assert I.classify({**one, "snap_frames": max(1, round(120 / ((lo + hi) / 2) * 60))}) == "proper"
    assert I.classify({"amp_deg": 200.0, "snap_frames": 3}) == "aggressive"


def test_a_kick_is_aimed_by_its_strike_window_and_its_hips():
    if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "dossiers", "roundhouse_kick.json")):
        import pytest; pytest.skip("the author's assets/animations/dossiers/roundhouse_kick.json is not shipped with the kit")
    base = keys()
    assert PCD.aim_intent(base, "calm", {"time": 0.0}) == base
    aimed = PCD.aim_intent(base, "aggressive", {"time": 0.0})
    names = [k["name"] for k in base]
    a, ci, z = names.index("toe_off"), names.index("contact"), names.index("through")
    span = lambda ks: ks[z]["t"] - ks[a]["t"]  # noqa: E731
    assert 0.34 < span(aimed) / span(base) < 0.46                  # the strike window x k
    for i in range(1, len(base)):                                  # every other segment keeps its length
        if not (a < i <= z):
            assert abs((aimed[i]["t"] - aimed[i - 1]["t"]) - (base[i]["t"] - base[i - 1]["t"])) < 1e-3
    lead = (aimed[a]["yaw"] - base[a]["yaw"]) / (base[ci]["yaw"] - base[a]["yaw"])
    assert 0.29 < lead < 0.51                                      # the hips already turning at toe-off
    sudden = PCD.aim_intent(base, "aggressive", {"time": 1.0})
    assert span(sudden) < span(aimed)                              # sudden = the short end of the window


def test_each_intent_samples_its_own_efforts():
    g = {"time": 0.1, "weight": -1.0, "space": 0.3, "flow": 1.0}
    a = PCD.intent_genome(g, "aggressive")
    assert a["weight"] == 0.4 and a["flow"] == -0.4 and a["time"] == 0.1 and a["space"] == 0.3
    assert PCD.intent_genome(g, "calm") == g
    bred = PCD.intent_genome({"weight": 0.2, "flow": 0.5}, "aggressive", fresh=False)
    assert bred["weight"] == 0.4 and bred["flow"] == -0.4


def test_the_measured_kick_reads_calm_and_the_aimed_kick_reads_aggressive():
    if not os.path.isfile(os.path.join(ROOT, "assets", "animations", "dossiers", "roundhouse_kick.json")):
        import pytest; pytest.skip("the author's assets/animations/dossiers/roundhouse_kick.json is not shipped with the kit")
    s0 = {"time": 0.0, "weight": 0.0, "space": 0.0, "flow": 0.0}
    c, _ = kick("calm", s0)
    assert I.read(c)["intent"] == "calm"                           # the owner's own reading of round 5
    s = {"time": 0.0, "weight": 0.8, "space": 0.0, "flow": -0.8}
    c, _ = kick("aggressive", s)
    r = I.read(c)
    assert r["intent"] == "aggressive", r
    assert r["snap_frames"] <= 6
