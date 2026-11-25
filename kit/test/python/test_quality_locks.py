"""The quality locks' Python side (2026-10-21): a move dossier made after the locks is schema 2 from the start, unless the
OWNER waived its evidence step; dossiers in board/locks.json's grandfathered list keep the old schema-1 pass."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "anim"))
import proc_dossier as PD  # noqa: E402

OLD = {"schema": 1, "sources": [], "phases": []}


def write_locks(tmp_path, monkeypatch, waivers=None):
    path = tmp_path / "locks.json"
    path.write_text(json.dumps({
        "grandfathered": {"anim": ["assets/animations/dossiers/old_move.json"]},
        "waivers": {"anim": waivers or {}},
    }), encoding="utf-8")
    monkeypatch.setattr(PD, "LOCKS", str(path))


def test_grandfathered_schema1_passes(tmp_path, monkeypatch):
    write_locks(tmp_path, monkeypatch)
    assert PD.evidence_missing(OLD, "old_move") == []


def test_new_schema1_is_refused(tmp_path, monkeypatch):
    write_locks(tmp_path, monkeypatch)
    assert any("schema 2" in m for m in PD.evidence_missing(OLD, "new_move"))


def test_only_the_owners_waiver_counts(tmp_path, monkeypatch):
    write_locks(tmp_path, monkeypatch, {
        "owned": {"by": "owner", "steps": ["evidence"]},
        "model": {"who": "model", "by": "owner"},
        "other_step": {"by": "owner", "steps": ["verdict"]},
    })
    assert PD.evidence_missing(OLD, "owned") == []
    assert PD.evidence_missing(OLD, "model") != []
    assert PD.evidence_missing(OLD, "other_step") != []


def test_no_locks_file_locks_everything(tmp_path, monkeypatch):
    monkeypatch.setattr(PD, "LOCKS", str(tmp_path / "missing.json"))
    assert PD.evidence_missing(OLD, "old_move") != []
