"""strike.py resolve_feel + kit/anim/feel_presets.json - TIERED FEEL (AAA plan #7)"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.abspath(os.path.join(HERE, "..", "..", "..")), "kit", "anim"))
import strike as S    # noqa: E402


def test_tiers_resolve_and_override():
    assert S.resolve_feel("medium") == {"hitstop": 0.07, "impact_frames": 2, "camera_shake": 0.45, "tier": "medium"}
    h = S.resolve_feel({"tier": "heavy", "camera_shake": 0.5})
    assert h["hitstop"] >= 0.1 and h["camera_shake"] == 0.5 and h["tier"] == "heavy"
    assert S.resolve_feel("light")["hitstop"] < S.resolve_feel("medium")["hitstop"] < S.resolve_feel("heavy")["hitstop"]


def test_plain_feel_passes_through_and_unknown_tier_fails():
    raw = {"hitstop": 0.06, "impact_frames": 1}
    assert S.resolve_feel(raw) is raw and S.resolve_feel(None) is None
    with pytest.raises(SystemExit):
        S.resolve_feel("enormous")
