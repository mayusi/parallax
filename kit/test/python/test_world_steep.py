"""test_world_steep.py - STEEP LAND WITH NO ROCK (kit/world/worldcheck.py steep_lint; LIMITATIONS_FIXES_V3.md stage
E.3: "auto-scatter biome-graded photoscan rock / cliff skirts wherever terrain slope > 42 deg").
Held here: a new world whose play land is steeper than 42 deg over more than 1 % of it with no rock there FAILS
("steep:"); rocks standing on the steep band cover it and it passes; a gentle land passes; the land's outer rim is
not counted (the cliffs step leaves it alone too); a world built before this gate warns "improve:" instead.
Not claimed: that the rocks placed look right - that is the built world, looked at."""
import importlib.util
import os
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_world_check_steep", os.path.join(HERE, "..", "..", "world", "worldcheck.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

N, STEP = 101, 2.0  # (a 200-stud land, a sample every 2 studs)
X0 = -100.0


def ground(slope_deg, band=(-20.0, 20.0)):
    """flat land with one ridge face across x in `band` rising at `slope_deg` (the rest flat)"""
    xs = X0 + np.arange(N) * STEP
    rise = np.tan(np.radians(slope_deg))
    h = np.clip(xs - band[0], 0, band[1] - band[0]) * rise
    H = np.repeat(h[:, None], N, axis=1)
    return {"x0": X0, "z0": X0, "step": STEP, "nx": N, "nz": N, "heights": H.ravel().tolist()}


def world(slope_deg, parts=(), band=(-20.0, 20.0)):
    return {"terrain": {"ground": [ground(slope_deg, band)]}, "parts": list(parts)}


def rock(x, z, size=12.0, name="Rock"):
    return {"name": name, "pos": [x, 0, z], "size": [size, size, size]}


class Steep(unittest.TestCase):
    def test_a_bare_cliff_fails_a_new_world(self):
        errs, warns, stats = C.steep_lint(world(60), "NewTown")
        self.assertEqual(len(errs), 1)
        self.assertTrue(errs[0].startswith("steep:"))
        self.assertIn("cliffs", errs[0])
        self.assertGreater(stats["steep_bare"], 0)
        self.assertEqual(warns, [])

    def test_a_gentle_land_passes(self):
        self.assertEqual(C.steep_lint(world(30), "NewTown")[0], [])
        self.assertEqual(C.steep_lint(world(40), "NewTown")[0], [])

    def test_rocks_on_the_steep_band_cover_it(self):
        # a rock face every 12 studs along the ridge (z), standing on the band
        rocks = [rock(x, z) for x in (-14.0, 0.0, 14.0) for z in np.arange(-100.0, 101.0, 12.0)]
        errs, _, stats = C.steep_lint(world(60, rocks), "NewTown")
        self.assertEqual(errs, [])
        self.assertEqual(stats["steep_bare"], 0)
        # a mesh placeholder named for a cliff covers it too
        faces = [{"name": "KitMesh", "mesh": "ph_rockface", "pos": [x, 0, z], "size": [12, 20, 12]}
                 for x in (-14.0, 0.0, 14.0) for z in np.arange(-100.0, 101.0, 12.0)]
        self.assertEqual(C.steep_lint(world(60, faces), "NewTown")[0], [])
        # half the ridge covered: still more than 1 % bare
        half = [r for r in rocks if r["pos"][2] < 0]
        self.assertEqual(len(C.steep_lint(world(60, half), "NewTown")[0]), 1)

    def test_a_spire_is_no_rock(self):
        # (a church's spire, or a part named "Surface...", stood for a rock face: a fresh review, 2026-11-19)
        spires = [rock(x, z, name=n) for x in (-14.0, 0.0, 14.0) for z in range(-100, 101, 12)
                  for n in ("Spire",)] + [{"name": "KitMesh", "mesh": "gc_spire", "pos": [0, 0, 0], "size": [12, 60, 12]}]
        self.assertEqual(len(C.steep_lint(world(60, spires), "NewTown")[0]), 1)

    def test_the_rim_is_not_counted(self):
        # the steep band within the outer 48 studs only
        self.assertEqual(C.steep_lint(world(60, band=(-100.0, -60.0)), "NewTown")[0], [])

    def test_the_worlds_built_before_warn(self):
        errs, warns, _ = C.steep_lint(world(60), "SelftestValley")
        self.assertEqual(errs, [])
        self.assertTrue(warns and warns[0].startswith("improve:"))

    def test_no_terrain_no_check(self):
        self.assertEqual(C.steep_lint({"parts": []}, "NewTown"), ([], [], {}))


if __name__ == "__main__":
    unittest.main()
