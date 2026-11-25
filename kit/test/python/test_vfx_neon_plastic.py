"""Selftest fixtures for the `untextured-neon-mesh` director taste rule (owner 2026-10-15).

Fault: Rasengan 2.0/10 — untextured Neon ribbons/meshes read as PLASTIC.
Rule: kit/knowledge/vault/vfx/director_rules.json `untextured-neon-mesh`
      type neon_untextured_mesh — fires when untextured Neon >= 20 % of meshes OR a
      volume shape (sphere, spikes, cone, spiral, flame, tongue, tube, crown, dome) is
      untextured Neon.  A few accent rings are fine (starblade 9.5, saiyan_ssj_3d 9.0).

Fixtures:
  bad_neon_share.json  — 5 of 7 meshes are untextured Neon rings/arcs (71 %)      → MUST fire
  bad_neon_volume.json — 1 untextured Neon sphere among 11 textured flame meshes   → MUST fire
  good_neon_accents.json — 1 untextured Neon accent ring among 11 textured meshes  → must NOT fire

Aura rule (fault 2: saiyan_ssj_mesh / saiyan_ascension_mesh 0.0/10):
  Those presets are caught by this same rule — they had 24-68 % untextured Neon at
  volume scale. A separate "all-mesh aura" rule cannot be made precise because there is
  no `category` or `aura` field in preset files; the distinction between the rejected
  all-mesh builds and the loved saiyan_ssj_3d (9.0, also all-mesh) is captured exactly
  by the untextured-neon-mesh share/volume check that is already calibrated.
  Therefore no additional fixture or rule is added for fault 2.
"""
import importlib.util
import json
import os
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
spec = importlib.util.spec_from_file_location("director", os.path.join(ROOT, "kit", "vfx", "director.py"))
director = importlib.util.module_from_spec(spec)
spec.loader.exec_module(director)

FIXTURE_DIR = os.path.join(ROOT, "kit", "selftest", "vfx", "neon_plastic")


def _load(name):
    return json.load(open(os.path.join(FIXTURE_DIR, name), encoding="utf-8"))


def _rule():
    rules = json.load(open(os.path.join(ROOT, director.RULES), encoding="utf-8"))["rules"]
    return next(r for r in rules if r["id"] == "untextured-neon-mesh")


class NeonPlasticFixtures(unittest.TestCase):
    """The untextured-neon-mesh rule must fire on every bad fixture and hold on the good one."""

    def test_bad_share_fixture_fires(self):
        """5 of 7 meshes are untextured Neon (71%) — the share threshold (>= 20%) must fire."""
        p = _load("bad_neon_share.json")
        findings = director.lint_neon_untextured_mesh(p, _rule())
        self.assertTrue(
            findings,
            "untextured-neon-mesh did NOT fire on bad_neon_share.json "
            "(71% untextured Neon — the rasengan-plastic pattern); rule or fixture is broken",
        )
        self.assertTrue(
            any("untextured Neon" in f for f in findings),
            f"finding did not name the share; got: {findings}",
        )

    def test_bad_volume_fixture_fires(self):
        """1 untextured Neon sphere among 11 textured meshes — a volume must fire regardless of share."""
        p = _load("bad_neon_volume.json")
        findings = director.lint_neon_untextured_mesh(p, _rule())
        self.assertTrue(
            findings,
            "untextured-neon-mesh did NOT fire on bad_neon_volume.json "
            "(untextured Neon sphere is a volume); rule or fixture is broken",
        )
        self.assertTrue(
            any("sphere" in f and "volume" in f for f in findings),
            f"finding did not name the volume sphere; got: {findings}",
        )

    def test_good_accents_fixture_holds(self):
        """1 untextured Neon ring among 11 textured meshes (< 20%, non-volume) — the rule must NOT fire."""
        p = _load("good_neon_accents.json")
        findings = director.lint_neon_untextured_mesh(p, _rule())
        self.assertFalse(
            findings,
            "untextured-neon-mesh FIRED on good_neon_accents.json "
            "(a single accent ring should be allowed — calibrated on starblade 9.5); "
            f"got: {findings}",
        )


if __name__ == "__main__":
    unittest.main()
