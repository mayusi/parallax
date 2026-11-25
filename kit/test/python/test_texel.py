"""rbx_optimize.density_stats — texel density (AAA-8): px per metre of every face from its share of the map and its
surface, weighted by surface; spread = p90 / p10 (even unwrap: 1.0)."""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
for _m in ("bpy", "mathutils", "mathutils.bvhtree"):   # (rbx_optimize imports Blender at the top: stubs for the pure part)
    sys.modules.setdefault(_m, types.ModuleType(_m))
sys.modules["mathutils.bvhtree"].BVHTree = object
import rbx_optimize as O  # noqa: E402


class Density(unittest.TestCase):
    def test_one_stud_square_on_a_quarter_of_a_1024_map(self):
        # a 1 x 1 stud face (0.28 m) taking a quarter of a 1024 map: 512 px over 0.28 m
        d = O.density_stats([0.25], [1.0], 1024)
        self.assertAlmostEqual(d["px_per_m"], 512 / 0.28, delta=1.0)
        self.assertAlmostEqual(d["px_per_stud"], 512, delta=0.5)
        self.assertEqual(d["spread"], 1.0)

    def test_spread_sees_a_blurred_part(self):
        # 85% of the surface even, 15% (a part) at a quarter of the density: the area-weighted p10 lands in it
        uv = [0.05] * 17 + [0.05 / 16] * 3
        wa = [1.0] * 20
        d = O.density_stats(uv, wa, 1024)
        self.assertGreater(d["spread"], 3.5)

    def test_even_layout_scale_free(self):
        d = O.density_stats([0.1, 0.4], [1.0, 4.0], 2048)
        self.assertEqual(d["spread"], 1.0)

    def test_coverage_is_the_maps_share_the_faces_use(self):
        d = O.density_stats([0.1, 0.2, 0.05], [1.0, 2.0, 0.5], 1024)
        self.assertAlmostEqual(d["coverage"], 0.35)

    def test_empty_is_zero(self):
        self.assertEqual(O.density_stats([], [], 1024)["px_per_m"], 0.0)

    def test_detail_map_fits_its_smallest_detail(self):
        # 12 small parts, 0.02 studs the smallest, 0.05 studs^2 of surface: 8 texels / 0.02 x sqrt(0.07) = 106 -> 128
        self.assertEqual(O.detail_map_size([0.02, 0.05], 0.05), 128)
        self.assertEqual(O.detail_map_size([0.005], 0.5), 1024)       # (tiny lettering over a big area: the cap)
        self.assertEqual(O.detail_map_size([0.01], 0.2, cap=512), 512)
        self.assertEqual(O.detail_map_size([], 0.1), 128)

    def test_roblox_guidance(self):
        self.assertAlmostEqual(O.ROBLOX_PX_PER_STUD, 256 / 5)


class MapByNeed(unittest.TestCase):
    """the map's size from the need (the 3D studio route's H3): one texel a screen pixel where the piece is judged"""

    def test_the_bar_is_the_screen_at_the_tiers_distance(self):
        # 1080 lines over 2 x 0.75 m x tan(35 deg) of view: 1028.3 px a metre; at 3 m a quarter of it
        self.assertAlmostEqual(O.screen_px_per_m(0.75), 1028.27, places=1)
        self.assertEqual(O.texel_bar("hero"), 1028.3)
        self.assertEqual(O.texel_bar("aaa"), 1028.3)
        self.assertEqual(O.texel_bar("prop"), 257.1)
        self.assertEqual(O.texel_bar("no such tier"), 257.1)       # (an unknown tier is held to the prop's)
        self.assertAlmostEqual(O.screen_px_per_m(1.5) * 2, O.screen_px_per_m(0.75))

    def test_a_small_piece_keeps_1024_and_a_large_one_gets_more(self):
        bar = O.texel_bar("hero")
        self.assertEqual(O.map_for_area(0.05, bar), 1024)           # a pistol: 325 px would do - never under the floor
        self.assertEqual(O.map_for_area(1.2, bar), 2048)            # a launcher's body: 1593 px needed
        self.assertEqual(O.map_for_area(5.0, bar), 4096)            # a coat, a vehicle panel: 3252
        self.assertEqual(O.map_for_area(40.0, bar), 4096)           # never above what Roblox shows
        self.assertEqual(O.map_for_area(0.0, bar), 1024)
        self.assertEqual(O.map_for_area(0.49, bar), 1024)           # half the map used (MAP_MARGIN): 1018 px
        self.assertEqual(O.map_for_area(0.50, bar), 2048)           # 1028.3 px: one over
        self.assertEqual(O.map_for_area(1.2, bar, floor=2048), 2048)
        self.assertEqual(O.map_for_area(5.0, bar, cap=2048), 2048)
        self.assertEqual(O.ROBLOX_MAX_TEX, 4096)                     # what Roblox says it shows: a master's limit
        # what the kit has SEEN Roblox keep: a game map's limit. 4096 since the test upload of 2026-11-12 (the
        # owner's "Yes, one upload", card v57z: a 4096 chart showed its one-texel stripes in Studio). Change it in
        # rbx_optimize only with a look at a real upload, never to make a build pass.
        self.assertEqual(O.GAME_MAP_CAP, 4096)
        self.assertEqual(O.map_for_area(5.0, bar, cap=O.GAME_MAP_CAP), 4096)
        self.assertEqual(O.map_for_area(5.0, bar, cap=1024), 1024)  # a lower cap still holds a map down

    def test_a_measured_group_under_the_bar_is_told_its_size(self):
        bar = O.texel_bar("hero")
        # coat_hero's coat in game: 273.2 px a metre at 1024 - 2048 is still short, 4096 reaches
        self.assertEqual(O.map_to_reach(273.2, 1024, bar), {"tex": 4096, "px_per_m": 1092.8, "reaches": True})
        self.assertEqual(O.map_to_reach(541.0, 2048, bar), {"tex": 4096, "px_per_m": 1082.0, "reaches": True})
        self.assertEqual(O.map_to_reach(600.0, 1024, bar), {"tex": 2048, "px_per_m": 1200.0, "reaches": True})
        # no size reaches: the group wants maps of its own
        self.assertEqual(O.map_to_reach(100.0, 1024, bar), {"tex": 4096, "px_per_m": 400.0, "reaches": False})
        self.assertEqual(O.map_to_reach(900.0, 4096, bar), {"tex": 4096, "px_per_m": 900.0, "reaches": False})
        self.assertIsNone(O.map_to_reach(1100.0, 1024, bar))        # sharp enough
        self.assertIsNone(O.map_to_reach(bar, 1024, bar))
        self.assertIsNone(O.map_to_reach(0.0, 1024, bar))           # (no UVs measured: nothing to say)
        self.assertIsNone(O.map_to_reach(273.2, 1024, O.texel_bar("prop")))   # the same coat as a prop at 3 m


if __name__ == "__main__":
    unittest.main()
