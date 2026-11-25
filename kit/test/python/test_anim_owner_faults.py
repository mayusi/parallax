"""kit/anim/owner_faults.py - the owner's NAMED faults (2026-11-10): every real clip he rejected for one fails it for
exactly that fault, every cut he loved passes all of them, each limit sits BETWEEN the two (never inside the loved
range), a spin is held to the spin faults and a cut to the cut faults, and the candidate generator refuses a weapon
candidate that shows one (proc_candidates.gate)"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "anim"))
os.chdir(ROOT)
import owner_faults as OF   # noqa: E402

FX = os.path.join("kit", "selftest", "anim", "faults")
REJECTED = {"DTDrillSpin4": {"blade flops", "legs twist"},          # 1/10 2026-11-04
            "GreatswordSideCut_v1": {"stilts", "arm-only"},          # 1/10 2026-10-17
            "SwordTrickArmsWide": {"stilts"}}                        # Swift v2, 2026-11-04 'leg work is horrible'
LOVED = ("GsCombo1SideLeft", "GsCombo2SideRight", "GsCombo3Overhead", "GsCombo4Underhip", "Katana1Kesa",
         "Katana2GyakuKesa", "Katana3Makko")
_M = {}


def measured(group, name):
    key = (group, name)
    if key not in _M:
        c = OF.load(os.path.join(FX, group, f"{name}.move.json"))
        _M[key] = (c, OF.measure(c))
    return _M[key]


def test_each_rejected_clip_fails_for_exactly_the_faults_he_named():
    for name, want in REJECTED.items():
        c, m = measured("rejected", name)
        got = {f["fault"] for f in OF.faults(c, m)}
        assert got == want, (name, got)


def test_every_cut_he_loved_passes_every_fault():
    for name in LOVED:
        c, m = measured("loved", name)
        assert m["kind"] == "cut", name
        assert OF.faults(c, m) == [], (name, OF.faults(c, m))


def test_each_limit_sits_between_his_rejections_and_his_loves():
    # the loved cuts' worst value on each cut measure is on the passing side, with room; the rejected one past it
    for fid in ("stilts", "arm-only"):
        key, side, lim, kind, _ = OF.LIMITS[fid]
        loved = [measured("loved", n)[1][key] for n in LOVED]
        bad = [measured("rejected", n)[1][key] for n, want in REJECTED.items() if fid in want]
        assert bad, fid
        if side == "below":
            assert min(loved) >= lim * 1.2 and max(bad) < lim, (fid, loved, bad)
        else:
            assert max(loved) <= lim / 1.2 and min(bad) > lim, (fid, loved, bad)
    # the spin measures: his rejected drill far past the line
    _, m = measured("rejected", "DTDrillSpin4")
    assert m["kind"] == "spin"
    assert m["blade_plane_dev_deg"] > 2 * OF.LIMITS["blade flops"][2]
    assert m["leg_twist_deg"] > 1.9 * OF.LIMITS["legs twist"][2]


def test_a_spin_is_held_to_the_spin_faults_and_a_cut_to_the_cut_faults():
    c, m = measured("rejected", "DTDrillSpin4")
    # a spin's arm stays out while the body turns: its torso-frame hand sweep is no arm-only cut
    assert {f["fault"] for f in OF.faults(c, {**m, "hand_sweep_studs": 0.5, "crouch_hold_share": 0.0})} == {"blade flops", "legs twist"}
    c, m = measured("loved", "Katana1Kesa")
    # a cut's legs face 48-55 deg off the torso (the stance) - never a spin's twist
    assert OF.faults(c, {**m, "leg_twist_deg": 170.0, "blade_plane_dev_deg": 60.0}) == []


def test_the_generator_refuses_a_weapon_candidate_with_a_named_fault():
    import proc_candidates as PCD
    c, _ = measured("rejected", "DTDrillSpin4")
    ok, why, _ = PCD.gate(c, {"name": "selftest", "checks": []}, {"builder": "fp_weapon", "slides": "weapon_vocab"})
    assert not ok
    assert any(w.startswith("owner fault: blade flops") for w in why), why
    assert any(w.startswith("owner fault: legs twist") for w in why), why


def test_the_owner_s_own_keyed_blocks_are_never_judged_by_it():
    # the strike route builds candidates from HIS keyed poses (R-anim-4: copied verbatim) - his pose is the bar
    import proc_candidates as PCD
    c, _ = measured("rejected", "DTDrillSpin4")
    _, why, _ = PCD.gate(c, {"name": "selftest", "checks": []}, {"builder": "strike"})
    assert not any(w.startswith("owner fault") for w in why), why
