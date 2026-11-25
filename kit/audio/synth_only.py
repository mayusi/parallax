"""synth_only.py — the SYNTH-ONLY gate for a sound set.

Owner's verdict (graveyard, 2026-10-13, booth 6->5->4):
  "real recordings are the next quality step; pure synth is audio slop"

A set whose every member has NO recorded layer (dna + member layers) fails this check.
A recorded layer is one with a "sample" key (a path, list, or ref) or "source": "sample".

GRANDFATHER  — sets that existed on 2026-11-10 (frozen in board/locks.json "grandfathered" "sfx")
  only warn, never fail.  Selftest fixtures and sets created after today fail.

WAIVER — board/locks.json "waivers" "sfx" {"<set_name>": {"by": "owner...", "steps": ["synth-only"]}}
  skips the error (the owner explicitly cleared it).  Only a record whose `by` starts with
  "owner" (case-insensitive) counts; a Claude-written waiver is refused.

Usage (called by run_set in sets.py, before render):
    result = check_synth_only(set_name, spec, set_path)
    # result is None (pass), a warning string, or raises SystemExit — no, it returns a dict:
    #   {"level": "error"|"warn"|"pass", "msg": str}
"""

import json
import os

LOCKS_PATH = os.path.join("board", "locks.json")


def _load_locks():
    try:
        with open(LOCKS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _layer_is_recorded(layer):
    """True when this layer dict uses a real recording (sample key present, or source == 'sample')."""
    if not isinstance(layer, dict):
        return False
    return "sample" in layer or layer.get("source") == "sample"


def set_has_recorded_layer(spec):
    """True when ANY layer in dna or any member's own layers is a recording."""
    dna = spec.get("dna") or {}
    for layer in dna.values():
        if _layer_is_recorded(layer):
            return True
    for m in (spec.get("members") or {}).values():
        if isinstance(m, dict):
            for layer in m.get("layers") or []:
                if _layer_is_recorded(layer):
                    return True
    return False


def _is_grandfathered(set_path, locks):
    """True when the set's repo-relative path is in board/locks.json grandfathered.sfx."""
    gf_sfx = (locks.get("grandfathered") or {}).get("sfx") or []
    # normalise to forward-slash, lower-case (Windows filenames are case-insensitive)
    norm = set_path.replace(os.sep, "/").lower()
    for entry in gf_sfx:
        if str(entry).replace("\\", "/").lower() == norm:
            return True
    return False


def _is_waived(set_name, locks):
    """True when the OWNER has waived the synth-only step for this set name."""
    waivers_sfx = (locks.get("waivers") or {}).get("sfx") or {}
    w = waivers_sfx.get(set_name)
    if not isinstance(w, dict):
        return False
    by = str(w.get("by", "")).strip().lower()
    if not by.startswith("owner"):
        return False
    steps = w.get("steps")
    # a waiver that names steps must include "synth-only"; one with no steps list waives everything
    if isinstance(steps, list) and "synth-only" not in steps:
        return False
    return True


def check_synth_only(set_name, spec, set_path):
    """Return {"level": "error"|"warn"|"pass", "msg": str}.

    "error"  — synth-only, not grandfathered, not waived: the gate must fail.
    "warn"   — synth-only but grandfathered (existed on 2026-11-10): the gate only warns.
    "pass"   — has at least one recorded layer, or waived.
    """
    if set_has_recorded_layer(spec):
        return {"level": "pass", "msg": ""}

    locks = _load_locks()

    if _is_waived(set_name, locks):
        return {"level": "pass", "msg": f"{set_name}: synth-only waived by the owner"}

    if _is_grandfathered(set_path, locks):
        return {
            "level": "warn",
            "msg": (
                f"{set_name}: pure synth — no recorded layer in any member "
                f"(owner verdict 2026-10-13: 'pure synth is audio slop'; "
                f"grandfathered set, only warning — add a sample layer to remove this)"
            ),
        }

    return {
        "level": "error",
        "msg": (
            f"{set_name}: pure synth — no recorded layer in any member "
            f"(owner verdict 2026-10-13: 'real recordings are the next quality step; "
            f"pure synth is audio slop'); add a \"sample\" layer "
            f"(kit sfx find <keyword>) or the owner must waive it"
        ),
    }
