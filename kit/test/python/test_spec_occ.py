"""Specular occlusion (the owner, 2026-11-17, a board card: "New pieces only"): a new piece's crevices reflect less - rougher
and less metallic where the occlusion map is dark - and every piece built before that day bakes as before.
rbx_wear.spec_occlusion is the bake's own math (numpy only); rbx_wear.spec_occ_default decides on or off."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_wear as W  # noqa: E402

BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
FIXTURE = os.path.join(ROOT, "kit", "selftest", "blender", "build_spec_occ.py")


def bake(how):
    """build the slot fixture (kit/selftest/blender/build_spec_occ.py) -> (exit code, its SPECOCC map stats, the
    build's facts.spec_occlusion, the log)"""
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", FIXTURE, "--", how],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    stats = next((json.loads(ln[8:]) for ln in out.stdout.splitlines() if ln.startswith("SPECOCC ")), None)
    status = next((json.loads(ln) for ln in reversed(out.stdout.splitlines()) if ln.startswith("{") and '"status"' in ln),
                  None)
    facts = ((status or {}).get("facts") or {}).get("spec_occlusion")
    return out.returncode, stats, facts, out.stdout[-2000:] + out.stderr[-2000:]


def _maps(occ_values):
    occ = np.array(occ_values, np.float32).reshape(1, -1, 1)
    rough = np.full((1, occ.shape[1], 3), 0.4, np.float32)
    metal = np.full((1, occ.shape[1], 3), 1.0, np.float32)
    return rough, metal, occ


class TheMath(unittest.TestCase):
    def test_a_crevice_gets_rougher_and_less_metallic(self):
        rough, metal, occ = _maps([1.0, 0.85, 0.55, 0.25, 0.0])
        r, m, cav = W.spec_occlusion(rough, metal, occ, 1.0)
        self.assertTrue(np.allclose(r[0, :2], 0.4) and np.allclose(m[0, :2], 1.0), (r[0, :, 0], m[0, :, 0]))
        self.assertTrue(np.all(np.diff(r[0, :, 0]) >= 0) and np.all(np.diff(m[0, :, 0]) <= 0))
        self.assertAlmostEqual(float(r[0, 3, 0]), 0.4 + W.SPEC_OCC_ROUGH, places=5)   # full at OPEN - SPAN
        self.assertAlmostEqual(float(m[0, 3, 0]), 1.0 - W.SPEC_OCC_METAL, places=5)
        self.assertAlmostEqual(float(cav[0, 2, 0]), 0.5, places=5)

    def test_strength_scales_it_and_zero_changes_nothing(self):
        rough, metal, occ = _maps([0.25])
        r, m, _ = W.spec_occlusion(rough, metal, occ, 0.5)
        self.assertAlmostEqual(float(r[0, 0, 0]), 0.4 + W.SPEC_OCC_ROUGH * 0.5, places=5)
        r0, m0, cav0 = W.spec_occlusion(rough, metal, occ, 0.0)
        self.assertTrue(np.array_equal(r0, rough) and np.array_equal(m0, metal) and not cav0.any())

    def test_an_open_or_untrusted_occlusion_map_changes_nothing(self):
        rough, metal, occ = _maps([1.0] * 4)   # (an untrusted map is replaced by all 1 before this)
        r, m, cav = W.spec_occlusion(rough, metal, occ, 1.0)
        self.assertTrue(np.array_equal(r, rough) and np.array_equal(m, metal) and not cav.any())

    def test_never_outside_the_map_range(self):
        rough = np.full((1, 2, 3), 0.95, np.float32)
        metal = np.zeros((1, 2, 3), np.float32)
        r, m, _ = W.spec_occlusion(rough, metal, np.zeros((1, 2, 1), np.float32), 1.0)
        self.assertTrue(r.max() <= 1.0 and m.min() >= 0.0)


class OnlyNewPieces(unittest.TestCase):
    def test_the_frozen_list_is_there_and_names_the_pieces_built_before(self):
        with open(os.path.join(ROOT, "kit", "blender", "spec_occ_before.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(doc["date"], "2026-11-17")
        self.assertIn("New pieces only", doc["about"])
        self.assertGreaterEqual(len(doc["names"]), 7)
        self.assertIn("sword", doc["names"])   # (kit/starter/models/build_sword.py: a starter built before)

    def test_a_piece_built_before_is_off_and_its_game_version_follows(self):
        for name in ("sword", "sword_game"):
            strength, why = W.spec_occ_default(name, ROOT)
            self.assertEqual(strength, 0.0, name)
            self.assertIn("New pieces only", why)

    def test_kit_fixtures_are_off(self):
        self.assertEqual(W.spec_occ_default("_selftest_anything_new", ROOT)[0], 0.0)
        self.assertEqual(W.spec_occ_default("_probe_x", ROOT)[0], 0.0)

    def test_a_new_piece_is_on(self):
        strength, why = W.spec_occ_default("a_piece_nobody_has_built_yet", ROOT)
        self.assertEqual(strength, W.SPEC_OCC)
        self.assertIn("new piece", why)

    def test_a_missing_list_means_every_non_fixture_is_new(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(W.spec_occ_default("dragon_sword", d)[0], W.SPEC_OCC)


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class TheBake(unittest.TestCase):
    """a steel block with a deep slot, baked with it on and off: on, the slot reads rougher and less metallic and the
    facts say how much was touched; off, the maps are the material's own (one roughness, fully metallic)"""

    @classmethod
    def setUpClass(cls):
        cls.on, cls.off = bake("on"), bake("off")

    def test_on_the_slot_is_rougher_and_less_metallic(self):
        code, st, facts, log = self.on
        self.assertEqual(code, 0, log)
        self.assertGreater(st["rougher"], 0.1, st)
        self.assertGreater(st["less_metal"], 0.1, st)
        self.assertAlmostEqual(st["rough_max"], 0.35 + W.SPEC_OCC_ROUGH, delta=0.02)
        self.assertEqual(facts["strength"], 1.0)
        self.assertGreater(list(facts["touched"].values())[0], 0.1, facts)

    def test_off_changes_nothing(self):
        code, st, facts, log = self.off
        self.assertEqual(code, 0, log)
        self.assertEqual(st["rougher"], 0.0, st)
        self.assertLess(st["rough_max"], 0.36, st)
        self.assertEqual(facts["strength"], 0)
        self.assertNotIn("touched", facts)


if __name__ == "__main__":
    unittest.main()
