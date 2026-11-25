"""Gates that reject the owner's rejected verdicts: Fault 1 (primitive-only generators), Fault 2 (the terrain route:
land made without rivers or real elevation, SampleRegion_terrain_v1).
Tests call design_lint / terrain_route in kit/world/worldcheck.py directly; the terrain tests make tiny terrains with
the real kit/world/terrain.py (17 x 17 samples, about a second each).
Graveyard refs: showcase_worlds_x5 2026-10-14, SampleRegion_terrain_v1 2026-10-14.
"""

import importlib.util
import json
import os
import tempfile
import unittest

# Load worldcheck the same way test_world_check.py does (avoids sys.path pollution).
_spec = importlib.util.spec_from_file_location(
    "kit_world_check_design",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "world", "worldcheck.py"),
)
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


# ---------------------------------------------------------------------------
# Fault 1 — design_lint
# ---------------------------------------------------------------------------

def _write_bp(tmp_dir, name, bp_dict):
    """Write a blueprint to <tmp_dir>/assets/worlds/<name>.json. Return fake world_path."""
    assets = os.path.join(tmp_dir, "assets", "worlds")
    os.makedirs(assets, exist_ok=True)
    bp_path = os.path.join(assets, f"{name}.json")
    with open(bp_path, "w", encoding="utf-8") as fh:
        json.dump(bp_dict, fh)
    # Fake world_path: <tmp>/build/worlds/<name>.json  (design_lint walks up two dirs from build/worlds/)
    build = os.path.join(tmp_dir, "build", "worlds")
    os.makedirs(build, exist_ok=True)
    world_path = os.path.join(build, f"{name}.json")
    with open(world_path, "w", encoding="utf-8") as fh:
        json.dump({"name": name, "parts": [], "terrain": {}}, fh)
    return world_path

class DesignLint(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_forest_without_meshes_errors_for_new_blueprint(self):
        """A new blueprint with a 'forest' step and no 'meshes' field must ERROR."""
        bp = {"name": "NewMap", "build": [
            {"forest": {"name": "F", "center": [0, 0, 0], "area": [60, 60], "count": 5, "seed": 1}},
            {"spawn": {"pos": [0, 1, 0], "mat": "spawn"}},
        ]}
        wp = _write_bp(self._tmpdir, "NewMap", bp)
        errs, warns, _ = C.design_lint(wp, "NewMap")
        self.assertTrue(len(errs) >= 1, f"expected error, got errs={errs}")
        self.assertTrue(any('"forest"' in e for e in errs), errs)

    def test_tree_without_mesh_errors_for_new_blueprint(self):
        """A new blueprint with a 'tree' step and no 'mesh' field must ERROR."""
        bp = {"name": "TreeMap", "build": [
            {"tree": {"name": "T", "pos": [10, 0, 10], "height": 20}},
            {"spawn": {"pos": [0, 1, 0], "mat": "spawn"}},
        ]}
        wp = _write_bp(self._tmpdir, "TreeMap", bp)
        errs, warns, _ = C.design_lint(wp, "TreeMap")
        self.assertTrue(any('"tree"' in e for e in errs), errs)

    def test_building_errors_unless_it_wears_a_skin(self):
        """A new blueprint's box-and-wall building errors; the same building wearing a whole-building mesh ("skin")
        does not - the mesh is what is seen (its walls stay as invisible collision)."""
        b = {"name": "H", "center": [0, 0, 0], "size": [22, 30], "floors": 4, "mat": "stone"}
        bp = {"name": "SkinMap", "build": [{"building": dict(b)}, {"spawn": {"pos": [0, 1, 40], "mat": "spawn"}}]}
        errs, _, _ = C.design_lint(_write_bp(self._tmpdir, "SkinMap", bp), "SkinMap")
        self.assertTrue(any('primitive box-and-wall' in e for e in errs), errs)
        bp["build"][0]["building"]["skin"] = "gc_house_a"
        errs, _, _ = C.design_lint(_write_bp(self._tmpdir, "SkinMap", bp), "SkinMap")
        self.assertFalse(any('primitive box-and-wall' in e for e in errs), errs)
        # ... and so does one put together from facade modules ("facade": the prefix of their names) - a NAME:
        # true, a number or an empty word puts no module on it, and is no way round the gate
        del bp["build"][0]["building"]["skin"]
        bp["build"][0]["building"]["facade"] = "gc"
        errs, _, _ = C.design_lint(_write_bp(self._tmpdir, "SkinMap", bp), "SkinMap")
        self.assertFalse(any('primitive box-and-wall' in e for e in errs), errs)
        for not_a_name in (True, 1, "", "  ", ["gc"]):
            bp["build"][0]["building"]["facade"] = not_a_name
            errs, _, _ = C.design_lint(_write_bp(self._tmpdir, "SkinMap", bp), "SkinMap")
            self.assertTrue(any('primitive box-and-wall' in e for e in errs), (not_a_name, errs))

    def test_a_town_is_a_plan_of_buildings_and_errors_unless_its_houses_wear_skins(self):
        """A "town" step (kit/lib/worldtown.luau) expands into building steps the blueprint never names: the gate reads
        the town itself, so a generated town is held to the rule a typed street of buildings is held to."""
        town = {"name": "Old Town", "area": [256, 224], "gates": ["S"], "mats": {"street": "a", "wall": "b", "roof": "c"}}
        bp = {"name": "TownMap", "build": [{"town": dict(town)}, {"spawn": {"pos": [0, 1, 100], "mat": "spawn"}}]}
        errs, warns, _ = C.design_lint(_write_bp(self._tmpdir, "TownMap", bp), "TownMap")
        self.assertEqual(len(errs), 1, errs)
        self.assertIn('"town" step "Old Town"', errs[0])
        self.assertIn("primitive box-and-wall", errs[0])
        self.assertIn('"skins"', errs[0])
        self.assertEqual(warns, [])
        bp["build"][0]["town"]["skins"] = "gh"
        errs, warns, _ = C.design_lint(_write_bp(self._tmpdir, "TownMap", bp), "TownMap")
        self.assertEqual((errs, warns), ([], []))
        # "skins" is a name: anything else skins no house in the compiler, and is no way round the gate
        for not_a_name in (True, 1, ["gh"], "", "   "):
            bp["build"][0]["town"]["skins"] = not_a_name
            errs, _, _ = C.design_lint(_write_bp(self._tmpdir, "TownMap", bp), "TownMap")
            self.assertEqual(len(errs), 1, (not_a_name, errs))
        # a world that existed before the gate keeps its fault as a warning, as its buildings do
        bp = {"name": "SelftestTrap", "build": [{"town": dict(town)}]}
        errs, warns, _ = C.design_lint(_write_bp(self._tmpdir, "SelftestTrap", bp), "SelftestTrap")
        self.assertEqual(errs, [])
        self.assertTrue(any('"town" step' in w for w in warns), warns)

    def test_a_city_grid_is_primitive_boxes_and_points_at_the_town_plan(self):
        """A "city" step makes its blocks out of boxes and window bands: the look the gate rules out, by a generator
        the gate never read (the way round it that "town" was, closed 2026-11-13)."""
        city = {"name": "Blocks", "center": [0, 0, 0], "area": [240, 240], "mat": "a", "glass": "b"}
        bp = {"name": "GridMap", "build": [{"city": dict(city)}]}
        errs, warns, _ = C.design_lint(_write_bp(self._tmpdir, "GridMap", bp), "GridMap")
        self.assertEqual(len(errs), 1, errs)
        self.assertIn('"city" step "Blocks"', errs[0])
        self.assertIn('"town" step', errs[0])
        self.assertEqual(warns, [])
        # an unnamed one is named by its place; a city typed as nonsense is still a city step
        for spec, label in (({"center": [8, 0, 9]}, "city at [8, 0, 9]"), ({}, "city at ?"), (True, "city at ?")):
            errs, _, _ = C.design_lint(_write_bp(self._tmpdir, "GridMap", {"name": "GridMap", "build": [{"city": spec}]}), "GridMap")
            self.assertEqual(len(errs), 1, (spec, errs))
            self.assertIn(label, errs[0])
        # no city step, no fault; a world on the grandfather list (a selftest fixture) keeps its city as a warning
        errs, warns, _ = C.design_lint(_write_bp(self._tmpdir, "GridMap", {"name": "GridMap", "build": [{"spawn": {"pos": [0, 0, 0]}}]}), "GridMap")
        self.assertEqual((errs, warns), ([], []))
        errs, warns, _ = C.design_lint(_write_bp(self._tmpdir, "SelftestTrap", {"name": "SelftestTrap", "build": [{"city": dict(city)}]}), "SelftestTrap")
        self.assertEqual(errs, [])
        self.assertTrue(any('"city" step' in w for w in warns), warns)

    def test_rocks_without_meshes_errors_for_new_blueprint(self):
        """A new blueprint with a 'rocks' step and no 'meshes' field must ERROR."""
        bp = {"name": "RockMap", "build": [
            {"rocks": {"name": "R", "center": [0, 0, 20], "area": [30, 30], "count": 5, "seed": 2}},
            {"spawn": {"pos": [0, 1, 0], "mat": "spawn"}},
        ]}
        wp = _write_bp(self._tmpdir, "RockMap", bp)
        errs, warns, _ = C.design_lint(wp, "RockMap")
        self.assertTrue(any('"rocks"' in e for e in errs), errs)

    def test_building_always_errors_for_new_blueprint(self):
        """A new blueprint with a 'building' step (no mesh path exists) must ERROR."""
        bp = {"name": "BuildMap", "build": [
            {"building": {"name": "HQ", "center": [0, 0, 0], "size": [20, 20], "floors": 2}},
            {"spawn": {"pos": [0, 1, 0], "mat": "spawn"}},
        ]}
        wp = _write_bp(self._tmpdir, "BuildMap", bp)
        errs, warns, _ = C.design_lint(wp, "BuildMap")
        self.assertTrue(any('"building"' in e for e in errs), errs)

    def test_forest_with_meshes_passes(self):
        """A 'forest' step WITH 'meshes' must NOT be flagged."""
        bp = {"name": "GoodForest", "build": [
            {"forest": {"name": "F", "center": [0, 0, 0], "area": [60, 60], "count": 5, "seed": 1,
                        "meshes": ["tree_oak_a", "tree_pine_a"]}},
            {"spawn": {"pos": [0, 1, 0], "mat": "spawn"}},
        ]}
        wp = _write_bp(self._tmpdir, "GoodForest", bp)
        errs, warns, _ = C.design_lint(wp, "GoodForest")
        self.assertEqual(errs, [], errs)
        self.assertEqual(warns, [], warns)

    def test_tree_with_mesh_passes(self):
        """A 'tree' step WITH 'mesh' must NOT be flagged."""
        bp = {"name": "GoodTree", "build": [
            {"tree": {"name": "T", "pos": [10, 0, 10], "height": 20, "mesh": "tree_oak_a"}},
            {"spawn": {"pos": [0, 1, 0], "mat": "spawn"}},
        ]}
        wp = _write_bp(self._tmpdir, "GoodTree", bp)
        errs, warns, _ = C.design_lint(wp, "GoodTree")
        self.assertEqual(errs, [], errs)
        self.assertEqual(warns, [], warns)

    def test_grandfathered_blueprint_warns_not_errors(self):
        """A GRANDFATHERED blueprint with primitive generators must WARN, never ERROR."""
        bp = {"name": "SelftestTrap", "build": [
            {"forest": {"name": "F", "center": [0, 0, 0], "area": [60, 60], "count": 3, "seed": 1}},
            {"spawn": {"pos": [0, 1, 0], "mat": "spawn"}},
        ]}
        wp = _write_bp(self._tmpdir, "SelftestTrap", bp)
        errs, warns, _ = C.design_lint(wp, "SelftestTrap")
        self.assertEqual(errs, [], f"grandfathered blueprint should not error; errs={errs}")
        self.assertTrue(len(warns) >= 1, f"grandfathered blueprint should warn; warns={warns}")
        self.assertTrue(any('"forest"' in w for w in warns), warns)

    def test_no_blueprint_found_is_silent(self):
        """If the blueprint file cannot be found, design_lint returns ([], [], {})."""
        # world_path with no assets/worlds/<Name>.json anywhere above it
        wp = _write_bp(self._tmpdir, "GhostMap", {})
        # Remove the blueprint so _find_blueprint fails
        os.remove(os.path.join(self._tmpdir, "assets", "worlds", "GhostMap.json"))
        errs, warns, stats = C.design_lint(wp, "GhostMap")
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])
        self.assertEqual(stats, {})

    def test_selftest_primitive_fixture_errors(self):
        """The committed _selftest_primitive.json fixture must trigger design errors (not warns)."""
        # The compiled path would live at build/worlds/SelftestPrimitive.json.
        # design_lint walks up from build/worlds/ to find assets/worlds/SelftestPrimitive.json.
        # We need a world_path under <repo>/build/worlds/ so the walker finds <repo>/assets/worlds/.
        repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        world_path = os.path.join(repo, "build", "worlds", "SelftestPrimitive.json")
        errs, warns, stats = C.design_lint(world_path, "SelftestPrimitive")
        self.assertTrue(len(errs) >= 1, f"SelftestPrimitive must have errors; errs={errs} warns={warns}")

    def test_selftest_primitive_fixed_fixture_passes(self):
        """The committed _selftest_primitive_fixed.json fixture must pass (no errors, no warns)."""
        repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        world_path = os.path.join(repo, "build", "worlds", "SelftestPrimitiveFixed.json")
        errs, warns, stats = C.design_lint(world_path, "SelftestPrimitiveFixed")
        self.assertEqual(errs, [], f"SelftestPrimitiveFixed must have no errors; errs={errs}")
        self.assertEqual(warns, [], f"SelftestPrimitiveFixed must have no warns; warns={warns}")


# ---------------------------------------------------------------------------
# Fault 2 — terrain_route (SampleRegion_terrain_v1: noise + thermal erosion alone)
# ---------------------------------------------------------------------------

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
TERRAIN_PY = os.path.join(REPO, "kit", "world", "terrain.py")
V1_HEIGHTS_SHA1 = "55424b30af488479d8754e345d1a6b1ecc553dc4"  # SampleRegion.hm.json at 7d4e0796, the terrain rejected


def _make_terrain(out, *flags):
    """a tiny terrain (64 studs, 17 x 17) made by the real kit/world/terrain.py"""
    import subprocess
    import sys

    base = ["--size", "64", "--step", "4", "--seed", "3", "--relief", "20", "--erosion", "300", "--thermal", "5"]
    r = subprocess.run([sys.executable, TERRAIN_PY, out] + base + list(flags) + ["--no-paint"], capture_output=True, text=True)
    assert r.returncode == 0 and os.path.isfile(out), r.stderr[-400:]
    with open(out, encoding="utf-8") as fh:
        return json.load(fh)


def _terrain_world(tmp_dir, name, hm_path):
    """a blueprint using the heightmap (absolute source) + its fake compiled path -> (world_path, blueprint_path)"""
    bp = {"name": name, "terrain": [{"heightmap": {"center": [0, 0, 0], "size": [64, 64], "source": hm_path}}], "build": []}
    bp_path = os.path.join(tmp_dir, f"{name}.json")
    with open(bp_path, "w", encoding="utf-8") as fh:
        json.dump(bp, fh)
    return os.path.join(tmp_dir, "build", "worlds", f"{name}.json"), bp_path


class R6Sheet(unittest.TestCase):
    """Fault 3 - the owner's 6/10 (2026-10-29, "some things are not ... to perfectly fit my R6 rig"): what the generators
    claim (building / room ceilings, doorways, bridge rails) is held to the r6 sheet. Minimums only for what they make:
    the owner wants it "big, bigger than the rigs"."""

    def errs(self, *fits):
        w = {"scale": "r6", "fits": [dict(f, pos=[0, 0, 0], name=f.get("name", "x")) for f in fits]}
        return C.scale_check(w, None)[0]

    def test_a_room_a_head_too_low_fails_and_a_big_hall_passes(self):
        bad = self.errs({"kind": "ceiling", "size": [20, 10, 20]})
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("does not fit the r6 rig", bad[0])
        self.assertIn("h 10", bad[0])
        self.assertEqual(self.errs({"kind": "ceiling", "size": [20, 13, 20]}), [])
        self.assertEqual(self.errs({"kind": "ceiling", "size": [60, 40, 90]}), [])  # (a nave: big is fine)

    def test_a_doorway_under_the_rig_fails_and_a_big_one_passes(self):
        bad = self.errs({"kind": "opening", "size": [4, 7, 1]})
        self.assertEqual(len(bad), 1, bad)
        self.assertIn("w 4", bad[0])
        self.assertIn("h 7", bad[0])
        self.assertEqual(self.errs({"kind": "opening", "size": [12, 20, 1]}), [])

    def test_a_claimed_house_door_keeps_its_stricter_range(self):
        self.assertEqual(len(self.errs({"kind": "door", "size": [7, 8, 1]})), 1)  # (a barn door, by a person's claim)

    def test_a_rail_at_the_knee_fails(self):
        bad = self.errs({"kind": "rail", "size": [30, 1.3, 1]})
        self.assertEqual(len(bad), 1, bad)
        self.assertEqual(self.errs({"kind": "rail", "size": [30, 3, 1]}), [])


def _lamp(x, z, name="LampHead", lit=True, mesh=None):
    p = {"name": name, "pos": [x, 10, z], "size": [1, 1, 1]}
    if lit:
        p["children"] = [{"kind": "light", "spec": {"range": 30}}]
    if mesh:
        p["mesh"] = mesh
    return p


class LampDensity(unittest.TestCase):
    """Fault 4 - the owner on the District (2026-10-28): "I hate the fact that you added a lamp everywhere"."""

    def test_a_lamp_every_24_studs_fails(self):
        w = {"parts": [_lamp(x, 0) for x in range(0, 240, 24)]}
        errs, _, stats = C.lamp_density(w, "NewStreet")
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("a lamp everywhere", errs[0])
        self.assertEqual(stats["lamps"], 10)

    def test_lamps_with_a_reason_pass(self):
        sparse = {"parts": [_lamp(x, 0) for x in range(0, 900, 90)]}
        self.assertEqual(C.lamp_density(sparse, "NewStreet")[0], [])
        few = {"parts": [_lamp(x, 0) for x in range(0, 60, 12)]}  # (5 lamps round a fountain: a few, with a reason)
        self.assertEqual(C.lamp_density(few, "NewStreet")[0], [])

    def test_a_lamp_is_counted_once_and_unlit_poles_are_not_lamps(self):
        parts = []
        for x in range(0, 900, 90):
            parts += [_lamp(x, 0, "LampPole", lit=False), _lamp(x, 0, "LampArm", lit=False), _lamp(x, 0),
                      _lamp(x, 0, "Skin", lit=False, mesh="gothic_lamp")]
        errs, _, stats = C.lamp_density({"parts": parts}, "NewStreet")
        self.assertEqual(errs, [])
        self.assertEqual(stats["lamps"], 10)

    def test_a_street_lit_on_both_sides_at_90_passes(self):
        """A pair across a street is one stop: each lamp has only its opposite within reach."""
        parts = [_lamp(x, z) for x in range(0, 900, 90) for z in (-12, 12)]
        errs, _, stats = C.lamp_density({"parts": parts}, "NewStreet")
        self.assertEqual(errs, [], errs)
        self.assertEqual(stats["lamps"], 20)
        self.assertEqual(stats["lamp_crowd_median"], 1)

    def test_a_lamp_head_on_an_arm_is_one_lamp_with_its_mesh(self):
        parts = []
        for x in range(0, 900, 90):  # (the mesh skin on the post, the lit head 1.6 studs out on the arm)
            parts += [_lamp(x, 0, "Skin", lit=False, mesh="gothic_lamp"), _lamp(x + 1.6, 0)]
        errs, _, stats = C.lamp_density({"parts": parts}, "NewStreet")
        self.assertEqual(errs, [])
        self.assertEqual(stats["lamps"], 10)

    def test_the_worlds_from_before_the_check_are_not_measured(self):
        w = {"parts": [_lamp(x, 0) for x in range(0, 240, 12)]}
        self.assertEqual(C.lamp_density(w, "SelftestTrap"), ([], [], {}))


class TerrainRoute(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.cache = os.path.join(self._tmpdir, "terrain_routes.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def route(self, name, hm_path, **kw):
        wp, bp = _terrain_world(self._tmpdir, name, hm_path)
        return C.terrain_route(wp, name, bp, cache_path=self.cache, **kw)

    def route_bp(self, name, terrain):
        """a blueprint with this terrain list (ground ops, missing sources ...)"""
        bp_path = os.path.join(self._tmpdir, f"{name}.json")
        with open(bp_path, "w", encoding="utf-8") as fh:
            json.dump({"name": name, "terrain": terrain, "build": []}, fh)
        return C.terrain_route(os.path.join(self._tmpdir, f"{name}.json"), name, bp_path, cache_path=self.cache)

    def dem(self, stem="elev", sidecar=True, png=False):
        """a little made-up hill as elevation (+ the sidecar kit world dem writes, when asked); its stem must differ from
        the world names below - on Windows Land.json (a blueprint) IS land.json (a sidecar)"""
        import numpy as np
        from PIL import Image

        xs = np.linspace(-1, 1, 17)
        hill = np.exp(-(xs[:, None] ** 2 + xs[None, :] ** 2) * 2.0)
        path = os.path.join(self._tmpdir, f"{stem}.{'png' if png else 'tif'}")
        if png:
            Image.fromarray((hill * 250).astype(np.uint8)).save(path)
        else:
            Image.fromarray((hill * 800.0).astype(np.float32)).save(path)  # (float32 -> a mode "F" image, metres)
        if sidecar:
            with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as fh:
                json.dump({"source": "USGS 3DEP ImageServer exportImage (test)", "bbox": [-120.1, 37.0, -120.0, 37.1],
                           "size": 17, "width_m": 8900.0, "height_m": 11100.0}, fh)
        return path

    def design(self, cfg, stem="Land"):
        path = os.path.join(self._tmpdir, f"{stem}.design.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        return path

    # -- the rejected terrain and the rejected recipe

    def test_the_actual_v1_heightmap_fails_the_route(self):
        """The committed selftest fixture IS the rejected SampleRegion v1 heightmap, and the gate fails it as a route."""
        bp = os.path.join(REPO, "kit", "selftest", "world", "_selftest_terrain_v1.json")
        hm_path = os.path.join(REPO, "kit", "selftest", "world", "terrain", "_selftest_terrain_v1.hm.json")
        with open(hm_path, encoding="utf-8") as fh:
            self.assertEqual(C._heights_hash(json.load(fh)), V1_HEIGHTS_SHA1, "the fixture must stay the actual v1 heightmap")
        errs, warns, stats = C.terrain_route(os.path.join(self._tmpdir, "SelftestTerrainV1.json"), "SelftestTerrainV1", bp,
                                             cache_path=self.cache)
        self.assertEqual(len(errs), 1, errs)
        for needle in ("design:", "without rivers or real elevation", "no rivers", "SampleRegion_terrain_v1",
                       "the look stays the owner's verdict"):
            self.assertIn(needle, errs[0])
        self.assertNotIn("missing", errs[0])  # (its recorded design is found beside it: the message is the route alone)
        self.assertEqual(warns, [])
        self.assertIsNone(stats["terrain_routes"][0]["route"])
        self.assertFalse(any(sha == V1_HEIGHTS_SHA1 for _, sha in C._TERRAIN_ROUTE_GRANDFATHERED))

    def test_no_rivers_and_no_real_land_fails(self):
        """The rejected recipe made today (noise + droplets + thermal, stream 0) fails as a route."""
        hm_path = os.path.join(self._tmpdir, "Noise.hm.json")
        _make_terrain(hm_path, "--stream", "0")
        errs, warns, _ = self.route("Noise", hm_path)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("without rivers or real elevation", errs[0])
        self.assertIn("noise + 300 erosion droplets + thermal erosion x5, no rivers", errs[0])

    # -- the river route: proved by re-making it, and the rivers must have carved

    def test_a_river_recipe_is_proved_by_remaking_it_and_passes(self):
        """stream > 0 recorded, terrain.py re-makes the same heights and its river step cuts: no error; the proof is
        cached, not made again."""
        hm_path = os.path.join(self._tmpdir, "Rivers.hm.json")
        _make_terrain(hm_path, "--stream", "20", "--streamK", "0.015")
        errs, warns, stats = self.route("Rivers", hm_path)
        self.assertEqual((errs, warns), ([], []))
        row = stats["terrain_routes"][0]
        self.assertEqual((row["route"], row["proved"], row["cached"]), ("rivers", True, False))
        self.assertLessEqual(row["max_dh"], C.ROUTE_TOLERANCE)
        self.assertGreaterEqual(row["effect"], C.RIVER_EFFECT_MIN)
        saved = C._remake
        C._remake = lambda *a, **k: (_ for _ in ()).throw(AssertionError("a cached proof must not re-make the terrain"))
        try:
            errs2, _, stats2 = self.route("Rivers", hm_path)
        finally:
            C._remake = saved
        self.assertEqual(errs2, [])
        self.assertTrue(stats2["terrain_routes"][0]["cached"])

    def test_the_default_recipe_takes_the_river_route(self):
        """kit world terrain with no --stream makes land on the river route (stream 80 / K 0.015), and the gate passes it."""
        hm_path = os.path.join(self._tmpdir, "Default.hm.json")
        hm = _make_terrain(hm_path)
        self.assertEqual((hm["options"].get("stream"), hm["options"].get("streamK")), (80, 0.015))
        errs, _, stats = self.route("Default", hm_path)
        self.assertEqual(errs, [], errs)
        self.assertEqual((stats["terrain_routes"][0]["route"], stats["terrain_routes"][0]["proved"]), ("rivers", True))

    def test_the_default_on_real_land_adds_no_synthetic_rivers(self):
        """A design with a kit world dem DEM and no --stream: no river pass (it over-carves real land); real land passes."""
        self.dem()
        design = self.design({"dem": {"file": "elev.tif", "relief": 30, "blur": 1.0}})
        hm_path = os.path.join(self._tmpdir, "Land.hm.json")
        hm = _make_terrain(hm_path, "--design", design)
        self.assertEqual(hm["options"].get("stream"), 0)
        errs, _, stats = self.route("Land", hm_path)
        self.assertEqual(errs, [], errs)
        self.assertEqual(stats["terrain_routes"][0]["route"], "real land")

    def test_a_token_stream_fails_even_though_it_re_makes(self):
        """--stream 1 is recorded honestly and re-makes exactly, but its river step barely cuts: not the river route."""
        hm_path = os.path.join(self._tmpdir, "Token.hm.json")
        _make_terrain(hm_path, "--stream", "1", "--streamK", "0.015")
        errs, _, stats = self.route("Token", hm_path)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("barely carved the land", errs[0])
        row = stats["terrain_routes"][0]
        self.assertEqual(row["max_dh"], 0.0)  # (it IS what its recipe makes)
        self.assertLess(row["effect"], C.RIVER_EFFECT_MIN)

    def test_a_river_flag_written_into_the_metadata_alone_fails(self):
        """A no-river terrain whose recipe was edited to claim stream > 0: terrain.py does not give its heights back."""
        hm_path = os.path.join(self._tmpdir, "Forged.hm.json")
        hm = _make_terrain(hm_path, "--stream", "0")
        hm["options"]["stream"], hm["options"]["streamK"] = 20.0, 0.015
        with open(hm_path, "w", encoding="utf-8") as fh:
            json.dump(hm, fh)
        errs, warns, stats = self.route("Forged", hm_path)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("claims the rivers route", errs[0])
        self.assertIn("do not come from that recipe", errs[0])
        self.assertFalse(stats["terrain_routes"][0]["proved"])

    def test_flats_from_the_command_line_are_recorded_and_re_made(self):
        """terrain.py records --flat pads with the recipe, so a terrain made with them is proved too."""
        hm_path = os.path.join(self._tmpdir, "Flat.hm.json")
        hm = _make_terrain(hm_path, "--stream", "20", "--flat", "0,0,12")
        self.assertEqual(hm["options"].get("flat"), [[0.0, 0.0, 12.0]])
        errs, _, stats = self.route("Flat", hm_path)
        self.assertEqual(errs, [])
        self.assertTrue(stats["terrain_routes"][0]["proved"])

    def test_route_cache_off_re_makes_every_time(self):
        """use_cache=False (a blueprint's "checks": {"route_cache": false}, the selftest fixtures) proves on every run."""
        hm_path = os.path.join(self._tmpdir, "Again.hm.json")
        _make_terrain(hm_path, "--stream", "20")
        calls = []
        saved = C._remake
        C._remake = lambda *a, **k: (calls.append(1), saved(*a, **k))[1]
        try:
            for _ in range(2):
                errs, _, stats = self.route("Again", hm_path, use_cache=False)
                self.assertEqual(errs, [])
                self.assertFalse(stats["terrain_routes"][0]["cached"])
        finally:
            C._remake = saved
        self.assertEqual(len(calls), 2)
        self.assertFalse(os.path.exists(self.cache))

    def test_a_heightmap_not_made_by_the_kit_cannot_prove_a_claimed_route(self):
        hm_path = os.path.join(self._tmpdir, "Hand.hm.json")
        with open(hm_path, "w", encoding="utf-8") as fh:
            json.dump({"nx": 2, "nz": 2, "step": 4, "heights": [0, 1, 2, 3], "options": {"stream": 80}}, fh)
        errs, _, _ = self.route("Hand", hm_path)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("cannot be proved", errs[0])
        self.assertIn("not made by kit world terrain", errs[0])

    # -- the real-land route: a kit world dem DEM, and the land must follow it

    def test_real_land_from_a_kit_dem_is_proved_and_passes(self):
        """A design "dem" fetched by kit world dem (its sidecar) and no rivers: re-made from the DEM, it passes."""
        self.dem()
        design = self.design({"dem": {"file": "elev.tif", "relief": 30, "blur": 1.0}})
        hm_path = os.path.join(self._tmpdir, "Land.hm.json")
        _make_terrain(hm_path, "--stream", "0", "--design", design)
        errs, warns, stats = self.route("Land", hm_path)
        self.assertEqual((errs, warns), ([], []))
        row = stats["terrain_routes"][0]
        self.assertEqual((row["route"], row["proved"]), ("real land", True))
        self.assertGreaterEqual(row["follow"], C.DEM_FOLLOW_MIN)

    def test_any_picture_without_the_kit_dem_sidecar_is_not_real_land(self):
        self.dem(sidecar=False)
        design = self.design({"dem": {"file": "elev.tif", "relief": 30, "blur": 1.0}})
        hm_path = os.path.join(self._tmpdir, "Land.hm.json")
        _make_terrain(hm_path, "--stream", "0", "--design", design)
        errs, _, _ = self.route("Land", hm_path)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("no kit world dem sidecar", errs[0])

    def test_a_token_dem_under_noise_is_not_real_land(self):
        """A real DEM at "relief": 0.001 with noise on top: the land does not follow the elevation."""
        self.dem()
        design = self.design({"dem": {"file": "elev.tif", "relief": 0.001}, "noise": {"relief": 30, "scale": 40}})
        hm_path = os.path.join(self._tmpdir, "Land.hm.json")
        _make_terrain(hm_path, "--stream", "0", "--design", design)
        errs, _, stats = self.route("Land", hm_path)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("follow the elevation by only", errs[0])
        self.assertLess(stats["terrain_routes"][0]["follow"], C.DEM_FOLLOW_MIN)

    def test_a_base_image_counts_as_real_land_only_with_the_kit_dem_sidecar(self):
        """--from <image>: real land with kit world dem's sidecar; without it, the recipe has no route."""
        img = self.dem(png=True)
        hm_path = os.path.join(self._tmpdir, "Img.hm.json")
        _make_terrain(hm_path, "--stream", "0", "--from", img)
        errs, _, stats = self.route("Img", hm_path)
        self.assertEqual(errs, [], errs)
        self.assertEqual(stats["terrain_routes"][0]["route"], "real land")
        os.remove(os.path.splitext(img)[0] + ".json")
        errs2, _, _ = self.route("Img", hm_path)
        self.assertEqual(len(errs2), 1, errs2)
        self.assertIn("without rivers or real elevation", errs2[0])
        self.assertIn("no kit world dem sidecar", errs2[0])

    # -- ground ops: noise relief or inline heights have no route

    def test_a_ground_making_relief_from_noise_fails_and_a_flat_ground_is_untouched(self):
        errs, _, stats = self.route_bp("Bumps", [{"ground": {"center": [0, 0, 0], "size": [200, 200],
                                                             "noise": {"amplitude": 12, "scale": 60}}}])
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("makes its relief from noise (amplitude 12)", errs[0])
        self.assertEqual(self.route_bp("Plain", [{"ground": {"center": [0, 0, 0], "size": [200, 200]}}])[:2], ([], []))

    def test_a_ground_carrying_its_own_heights_fails(self):
        errs, _, _ = self.route_bp("Inline", [{"ground": {"center": [0, 0, 0], "size": [8, 8],
                                                          "samples": {"nx": 2, "nz": 2, "heights": [0, 9, 3, 7]}}}])
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("carries its own heights", errs[0])

    def test_dojo_arenas_noise_ground_is_grandfathered_where_it_is(self):
        bp = os.path.join(REPO, "games", "SampleDojo", "assets", "worlds", "SampleArena.json")
        if not os.path.isfile(bp):
            self.skipTest("no games/SampleDojo in this project")
        errs, warns, _ = C.terrain_route(os.path.join(self._tmpdir, "SampleArena.json"), "SampleArena", bp, cache_path=self.cache)
        self.assertEqual(errs, [], errs)
        self.assertEqual(len(warns), 1, warns)
        self.assertIn("grandfathered by its content", warns[0])

    # -- sources, broken input, grandfathering by content where it is used

    def test_a_heightmap_that_cannot_be_found_fails_closed(self):
        errs, _, _ = self.route_bp("Lost", [{"heightmap": {"center": [0, 0, 0], "size": [64, 64], "source": "nowhere/X.hm.json"}}])
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("cannot be found", errs[0])

    def test_broken_input_never_crashes(self):
        bp_path = os.path.join(self._tmpdir, "Five.json")
        with open(bp_path, "w", encoding="utf-8") as fh:
            json.dump({"name": "Five", "terrain": 5}, fh)
        self.assertEqual(C.terrain_route(bp_path, "Five", bp_path, cache_path=self.cache), ([], [], {}))
        hm_path = os.path.join(self._tmpdir, "Words.hm.json")
        hm = _make_terrain(hm_path, "--stream", "20")
        hm["heights"][0] = "high"
        with open(hm_path, "w", encoding="utf-8") as fh:
            json.dump(hm, fh)
        errs, _, _ = self.route("Words", hm_path)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("not all numbers", errs[0])

    def test_grandfathered_by_content_where_it_is_used(self):
        """The valley made the old way WARNS in its own blueprint; the same heights in another world, or one sample
        changed, fail."""
        bp = os.path.join(REPO, "kit", "selftest", "world", "_selftest_valley.json")
        errs, warns, stats = C.terrain_route(os.path.join(self._tmpdir, "SelftestValley.json"), "SelftestValley", bp,
                                             cache_path=self.cache)
        self.assertEqual(errs, [], errs)
        self.assertEqual(len(warns), 1, warns)
        self.assertTrue(warns[0].startswith("improve: "), warns[0])
        self.assertIn("grandfathered by its heights' hash", warns[0])
        self.assertTrue(stats["terrain_routes"][0]["grandfathered"])
        valley = os.path.join(REPO, "kit", "selftest", "world", "terrain", "_selftest_valley.hm.json")
        errs2, warns2, _ = self.route("SelftestValley", valley)  # (the same heights, the same NAME, another blueprint)
        self.assertEqual(len(errs2), 1, errs2)
        self.assertEqual(warns2, [])
        with open(valley, encoding="utf-8") as fh:
            hm = json.load(fh)
        hm["heights"][0] = round(hm["heights"][0] + 0.01, 2)  # re-made (or touched): no longer the grandfathered land
        changed = os.path.join(self._tmpdir, "Valley.hm.json")
        with open(changed, "w", encoding="utf-8") as fh:
            json.dump(hm, fh)
        errs3, _, _ = self.route("SelftestValley", changed)
        self.assertEqual(len(errs3), 1, errs3)
        self.assertIn("without rivers or real elevation", errs3[0])

    def test_a_world_without_a_heightmap_is_untouched(self):
        wp = _write_bp(self._tmpdir, "Flatland", {"name": "Flatland", "build": [{"spawn": {"pos": [0, 1, 0]}}]})
        self.assertEqual(C.terrain_route(wp, "Flatland", cache_path=self.cache), ([], [], {}))


if __name__ == "__main__":
    unittest.main()
