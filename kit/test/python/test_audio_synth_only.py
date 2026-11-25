"""Synth-only gate (owner verdict 2026-10-13: 'real recordings are the next quality step;
pure synth is audio slop').  kit/audio/synth_only.py check_synth_only():
  - a synth-only set that is NOT grandfathered and NOT waived -> level 'error', message names synth-only
  - a set with >= 1 recorded layer -> level 'pass'
  - a synth-only set whose path is in board/locks.json grandfathered.sfx -> level 'warn' only
  - a synth-only set with a valid owner waiver in board/locks.json waivers.sfx -> level 'pass'
  - the bad selftest fixture fails; the control fixture passes
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "audio"))
import synth_only as SO  # noqa: E402

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

SYNTH_ONLY_SPEC = {
    "dna": {
        "ring": {"role": "tail", "source": "modal", "modes": [[1240, 0.9, 1.0]], "gain": 0.4},
        "crack": {"role": "transient", "source": "click",
                  "env": {"attack": 0.0003, "decay": 0.006, "sustain": 0, "release": 0.002}},
    },
    "members": {
        "sword_hit_synth": {"class": "hit", "duration": 0.6, "use": ["crack", "ring"], "weights": [0.5]},
    },
}

RECORDED_SPEC = {
    "dna": {
        "ring": {"role": "tail", "source": "modal", "modes": [[1240, 0.9, 1.0]], "gain": 0.4},
    },
    "members": {
        "sword_hit_sampled": {
            "class": "hit", "duration": 0.6, "use": ["ring"],
            "layers": [{"role": "body", "sample": "lib:some_recording", "gain": 0.5}],
            "weights": [0.5],
        },
    },
}

SYNTH_PATH = "assets/sounds/sets/new_synth_set.json"
RECORDED_PATH = "assets/sounds/sets/recorded_set.json"
GF_PATH = "assets/sounds/sets/katana_steel.json"  # in real locks.json grandfathered.sfx


def _write_locks(tmp_path, grandfathered_sfx=None, waivers_sfx=None):
    data = {
        "grandfathered": {"sfx": grandfathered_sfx or []},
        "waivers": {"sfx": waivers_sfx or {}},
    }
    p = tmp_path / "locks.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# the bad selftest fixture fails (and names synth-only in the message)
# ---------------------------------------------------------------------------

def test_selftest_fixture_fails(tmp_path, monkeypatch):
    fixture = os.path.join(
        os.path.dirname(__file__), "..", "..", "selftest", "audio", "synth_only",
        "_selftest_synth_only_set.json",
    )
    assert os.path.isfile(fixture), f"fixture missing: {fixture}"
    with open(fixture, encoding="utf-8") as fh:
        spec = json.load(fh)
    # point locks at an empty file so it is NOT grandfathered
    locks_path = _write_locks(tmp_path)
    monkeypatch.setattr(SO, "LOCKS_PATH", locks_path)
    result = SO.check_synth_only("_selftest_synth_only_set", spec,
                                 "kit/selftest/audio/synth_only/_selftest_synth_only_set.json")
    assert result["level"] == "error", f"expected error, got {result}"
    assert "synth" in result["msg"].lower(), f"message should name synth-only: {result['msg']}"


# ---------------------------------------------------------------------------
# the good control fixture passes (has a sample layer)
# ---------------------------------------------------------------------------

def test_control_fixture_passes(tmp_path, monkeypatch):
    fixture = os.path.join(
        os.path.dirname(__file__), "..", "..", "selftest", "audio", "synth_only",
        "_selftest_synth_only_control.json",
    )
    assert os.path.isfile(fixture), f"fixture missing: {fixture}"
    with open(fixture, encoding="utf-8") as fh:
        spec = json.load(fh)
    locks_path = _write_locks(tmp_path)
    monkeypatch.setattr(SO, "LOCKS_PATH", locks_path)
    result = SO.check_synth_only("_selftest_synth_only_control", spec,
                                 "kit/selftest/audio/synth_only/_selftest_synth_only_control.json")
    assert result["level"] == "pass", f"control should pass, got {result}"


# ---------------------------------------------------------------------------
# a set with a recorded layer in dna passes
# ---------------------------------------------------------------------------

def test_recorded_dna_layer_passes(tmp_path, monkeypatch):
    spec = {
        "dna": {"body": {"role": "body", "sample": "lib:thud", "gain": 1.0}},
        "members": {"hit": {"duration": 0.5, "use": ["body"], "weights": [0.5]}},
    }
    locks_path = _write_locks(tmp_path)
    monkeypatch.setattr(SO, "LOCKS_PATH", locks_path)
    result = SO.check_synth_only("hit_set", spec, "assets/sounds/sets/hit_set.json")
    assert result["level"] == "pass"


# ---------------------------------------------------------------------------
# pure synth + not grandfathered -> error (message names synth-only)
# ---------------------------------------------------------------------------

def test_synth_only_new_set_errors(tmp_path, monkeypatch):
    locks_path = _write_locks(tmp_path)
    monkeypatch.setattr(SO, "LOCKS_PATH", locks_path)
    result = SO.check_synth_only("new_synth_set", SYNTH_ONLY_SPEC, SYNTH_PATH)
    assert result["level"] == "error"
    assert "synth" in result["msg"].lower()


# ---------------------------------------------------------------------------
# pure synth + grandfathered path -> warn only (never error)
# ---------------------------------------------------------------------------

def test_synth_only_grandfathered_warns_not_errors(tmp_path, monkeypatch):
    locks_path = _write_locks(tmp_path, grandfathered_sfx=[GF_PATH])
    monkeypatch.setattr(SO, "LOCKS_PATH", locks_path)
    result = SO.check_synth_only("katana_steel", SYNTH_ONLY_SPEC, GF_PATH)
    assert result["level"] == "warn", f"grandfathered should only warn, got {result}"
    assert "synth" in result["msg"].lower()


# ---------------------------------------------------------------------------
# pure synth + owner waiver with "synth-only" step -> pass
# ---------------------------------------------------------------------------

def test_owner_waiver_synth_only_step_passes(tmp_path, monkeypatch):
    locks_path = _write_locks(tmp_path, waivers_sfx={
        "new_synth_set": {"by": "owner", "steps": ["synth-only"], "words": "owner approved this one"},
    })
    monkeypatch.setattr(SO, "LOCKS_PATH", locks_path)
    result = SO.check_synth_only("new_synth_set", SYNTH_ONLY_SPEC, SYNTH_PATH)
    assert result["level"] == "pass", f"waived set should pass, got {result}"


# ---------------------------------------------------------------------------
# owner waiver with no steps list (blanket waiver) -> pass
# ---------------------------------------------------------------------------

def test_owner_blanket_waiver_passes(tmp_path, monkeypatch):
    locks_path = _write_locks(tmp_path, waivers_sfx={
        "new_synth_set": {"by": "owner", "words": "owner blanket"},
    })
    monkeypatch.setattr(SO, "LOCKS_PATH", locks_path)
    result = SO.check_synth_only("new_synth_set", SYNTH_ONLY_SPEC, SYNTH_PATH)
    assert result["level"] == "pass"


# ---------------------------------------------------------------------------
# a Claude-written waiver does NOT count -> still errors
# ---------------------------------------------------------------------------

def test_non_owner_waiver_still_errors(tmp_path, monkeypatch):
    locks_path = _write_locks(tmp_path, waivers_sfx={
        "new_synth_set": {"by": "claude", "steps": ["synth-only"], "words": "claude said ok"},
    })
    monkeypatch.setattr(SO, "LOCKS_PATH", locks_path)
    result = SO.check_synth_only("new_synth_set", SYNTH_ONLY_SPEC, SYNTH_PATH)
    assert result["level"] == "error", "a non-owner waiver must not clear the gate"


# ---------------------------------------------------------------------------
# a waiver for the wrong step does NOT count -> still errors
# ---------------------------------------------------------------------------

def test_wrong_step_waiver_still_errors(tmp_path, monkeypatch):
    locks_path = _write_locks(tmp_path, waivers_sfx={
        "new_synth_set": {"by": "owner", "steps": ["verdict"], "words": "only verdict waived"},
    })
    monkeypatch.setattr(SO, "LOCKS_PATH", locks_path)
    result = SO.check_synth_only("new_synth_set", SYNTH_ONLY_SPEC, SYNTH_PATH)
    assert result["level"] == "error", "a waiver for a different step must not clear the synth-only gate"
