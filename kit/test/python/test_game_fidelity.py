"""kit optimize's game version: the transfer's cage rule (rbx_transfer.cage: max(2 mm, 1.5 x the 99th percentile
deviation), rays reach 3 x) and the game_fidelity metric (game_fidelity.compare: |delta luma| median <= 8 / p95 <= 25,
shading-normal angle median <= 4 / p95 <= 20 degrees, over pixels both silhouettes cover)."""

import ast
import os
import types
import unittest

import numpy as np

BLENDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender")


def _lift(module, names):
    """the pure functions / constants `names` of a Blender module (it imports bpy), run as a body in a namespace"""
    tree = ast.parse(open(os.path.join(BLENDER, module), encoding="utf-8").read())
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names)
             or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in names for t in n.targets))]
    ns = {"np": np, "__builtins__": __builtins__}
    types.FunctionType(compile(ast.Module(nodes, []), module, "exec"), ns)()
    return ns


T = _lift("rbx_transfer.py", {"cage", "CAGE_FLOOR_MM", "MM_PER_STUD", "REACH"})
F = _lift("game_fidelity.py", {"compare", "VIEWS", "LIMITS", "verdict"})


def _views(albedo, normal, alpha=1.0):
    """6 identical views: an RGBA albedo picture (0-255) and an RGBA normal picture (n * 0.5 + 0.5)"""
    a = np.zeros((8, 8, 4), np.float32)
    a[..., :3], a[..., 3] = albedo, 255 * alpha
    n = np.zeros((8, 8, 4), np.float32)
    n[..., :3], n[..., 3] = np.asarray(normal, np.float32) * 0.5 + 0.5, alpha
    return {v: (a.copy(), n.copy()) for v in F["VIEWS"]}


class TestCage(unittest.TestCase):
    def test_a_tight_cut_gets_the_2mm_floor(self):
        self.assertAlmostEqual(T["cage"](0.0001), 2.0 / 280.0)
        self.assertAlmostEqual(T["cage"](0.0001, 100.0), 2.0 / 100.0)  # (an asset's own scale)

    def test_a_loose_cut_gets_one_and_a_half_times_its_p99(self):
        self.assertAlmostEqual(T["cage"](0.01), 0.015)
        self.assertEqual(T["REACH"], 3.0)


class TestCompare(unittest.TestCase):
    def test_a_version_against_itself_is_zero_and_passes(self):
        m = _views(120, (0, 0, 1))
        r = F["compare"](m, _views(120, (0, 0, 1)))
        self.assertEqual((r["albedo"]["median"], r["normal"]["median"]), (0.0, 0.0))
        self.assertTrue(r["albedo"]["pass"] and r["normal"]["pass"])

    def test_a_darker_game_albedo_fails(self):
        r = F["compare"](_views(170, (0, 0, 1)), _views(110, (0, 0, 1)))   # (the old re-derived bake: ~54 darker)
        self.assertFalse(r["albedo"]["pass"])
        self.assertTrue(r["normal"]["pass"])

    def test_small_albedo_drift_passes(self):
        self.assertTrue(F["compare"](_views(170, (0, 0, 1)), _views(165, (0, 0, 1)))["albedo"]["pass"])

    def test_tilted_normals_fail(self):
        t = np.radians(30)
        r = F["compare"](_views(120, (0, 0, 1)), _views(120, (np.sin(t), 0, np.cos(t))))
        self.assertAlmostEqual(r["normal"]["median"], 30.0, places=1)
        self.assertFalse(r["normal"]["pass"])

    def test_only_pixels_both_cover_count_and_none_is_a_failure(self):
        r = F["compare"](_views(120, (0, 0, 1)), _views(0, (1, 0, 0), alpha=0.0))
        self.assertEqual(r["albedo"]["pixels"], 0)
        self.assertFalse(r["albedo"]["pass"] or r["normal"]["pass"])


class TestOwnColour(unittest.TestCase):
    """--master-own-colour (the high-and-low route: the master is the HIGH in its own colour): the albedo's median
    gates, its p95 is reported only - the low's baked crevice shadow lives there (the car rim, S1: 0.33 / 32)"""

    @staticmethod
    def _shadowed(base, dark, px):
        views = _views(base, (0, 0, 1))
        for v in F["VIEWS"]:
            views[v][0].reshape(-1, 4)[:px, :3] = dark
        return views

    def test_a_baked_shadow_tail_passes_against_the_high_only(self):
        r = F["compare"](_views(128, (0, 0, 1)), self._shadowed(128, 60, 6))   # 6 of 64 pixels in a crevice
        self.assertEqual((r["albedo"]["median"], r["albedo"]["p95"]), (0.0, 68.0))
        self.assertEqual(F["verdict"](r, own_colour=True), (True, []))
        self.assertEqual(F["verdict"](r), (False, ["albedo"]))   # (against a baked master the p95 gates, as ever)

    def test_a_wrong_colour_map_fails_against_the_high(self):
        r = F["compare"](_views(128, (0, 0, 1)), _views(23, (0, 0, 1)))   # (the rim with another map: median 105)
        self.assertEqual(F["verdict"](r, own_colour=True), (False, ["albedo"]))

    def test_the_normals_still_gate_against_the_high(self):
        t = np.radians(30)
        r = F["compare"](_views(128, (0, 0, 1)), _views(128, (np.sin(t), 0, np.cos(t))))
        self.assertEqual(F["verdict"](r, own_colour=True), (False, ["normal"]))

    def test_no_pixels_fails_against_the_high(self):
        r = F["compare"](_views(120, (0, 0, 1)), _views(0, (1, 0, 0), alpha=0.0))
        self.assertFalse(F["verdict"](r, own_colour=True)[0])


C = _lift("game_fidelity.py", {"compare_close", "_erode", "close_verdict", "WIN", "ERODE", "SAME_MM", "ANG_BAD",
                               "GEO_MM", "MIN_PX", "FRAC_S", "FRAC_G", "MAX_FAULTS", "CLOSE_RES", "DEPTH_K",
                               "DEPTH_SPAN"})
SIZE = 2.8  # studs framed (the rim: ~1.67 studs across x 1.12, rounded)
STEP = 1 / (SIZE * C["DEPTH_SPAN"] * 280.0)  # one millimetre of depth, in depth units
K = C["DEPTH_K"]


def _close(n=(0, 0, 1), px=128):
    """one close-up view of a flat surface facing the camera: (shading normal RGBA, split depth RGBA)"""
    nrm = np.zeros((px, px, 4), np.float32)
    nrm[..., :3], nrm[..., 3] = np.asarray(n, np.float32) * 0.5 + 0.5, 1.0
    dep = np.zeros((px, px, 4), np.float32)
    dep[..., 3] = 1.0
    _depth(dep, np.full((px, px), 0.5))
    return nrm, dep


def _depth(dep, t):
    dep[..., 0], dep[..., 1] = np.floor(t * K) / K, t * K - np.floor(t * K)


def _move(view, rows, mm):
    """the view's surface over `rows` moved mm further along the camera"""
    dep = view[1]
    t = dep[..., 0].astype(np.float64) + dep[..., 1] / K
    t[rows] += mm * STEP
    _depth(dep, t)


def _cmp(m, g):
    return C["compare_close"](m, g, SIZE, 280.0, (0.0, 0.0, -1.0))


class TestCloseUp(unittest.TestCase):
    """the close-up pass (the owner, 2026-11-10: the car rim's S1 game version passed the 512 px numbers with a
    sawtoothed lip, a slit, a lumpy bore and painted threads - every fault a pixel or less at that size)"""

    def test_a_version_against_itself_has_no_fault(self):
        r = _cmp(_close(), _close())
        self.assertEqual((r["faults"], r["judged"]), (0, 16))

    def test_the_split_depth_keeps_a_hundredth_of_a_millimetre(self):
        # (EEVEE's film is half float: a whole position kept 0.26 mm on the rim, 1.2 mm on an 8-stud piece)
        g = _close()
        _move(g, slice(None), 0.01)
        dep = g[1].astype(np.float16).astype(np.float32)  # (what the film keeps)
        t = dep[..., 0].astype(np.float64) + dep[..., 1] / K
        self.assertLess(abs(float(t.mean()) - (0.5 + 0.01 * STEP)) * SIZE * 280, 0.01)
        self.assertEqual(_cmp(_close(), (g[0], dep))["faults"], 0)

    def test_a_stair_stepped_band_is_a_shading_fault_in_every_window_it_crosses(self):
        g = _close()
        t = np.radians(25)
        g[0][36:40, :, :3] = np.array((np.sin(t), 0, np.cos(t)), np.float32) * 0.5 + 0.5  # 4 px of 32: 12.5%
        r = _cmp(_close(), g)
        self.assertEqual((r["shading"], r["geometry"], r["faults"]), (4, 0, 4))
        self.assertEqual(sorted((w[0], w[2]) for w in r["windows"]), [(1, "shading")] * 4)

    def test_small_drift_and_a_one_pixel_line_are_no_fault(self):
        t = np.radians(5)
        self.assertEqual(_cmp(_close(), _close((np.sin(t), 0, np.cos(t))))["faults"], 0)
        g = _close()
        g[0][40, :, :3] = np.array((1, 0, 0), np.float32) * 0.5 + 0.5  # (1 px of 32: 3%)
        self.assertEqual(_cmp(_close(), g)["faults"], 0)

    def test_painted_on_detail_is_a_geometry_fault(self):
        g = _close()
        _move(g, slice(64, 96), 1.0)  # (the game's surface 1 mm off the master's over a whole window row)
        self.assertEqual((_cmp(_close(), g)["geometry"], _cmp(_close(), g)["shading"]), (4, 0))
        g = _close()
        _move(g, slice(64, 96), 0.3)  # (0.3 mm: a 60-sided lip's chord, a fine thread's facet - no fault)
        self.assertEqual(_cmp(_close(), g)["faults"], 0)

    def test_a_deep_hole_capped_flat_is_a_geometry_fault_a_thin_occlusion_edge_is_not(self):
        g = _close()
        _move(g, slice(64, 96), -12.0)  # (the low caps a 12 mm deep hole: its hit is far nearer than the master's)
        self.assertEqual(_cmp(_close(), g)["geometry"], 4)
        g = _close()
        _move(g, slice(64, 66), -12.0)  # (2 px of 32 along a part's edge: one hits the part, one what is behind)
        self.assertEqual(_cmp(_close(), g)["faults"], 0)

    def test_a_surface_only_one_of_them_has_is_a_geometry_fault(self):
        g = _close()
        g[0][64:96, :, 3] = 0.0
        g[1][64:96, :, 3] = 0.0  # (the game lacks it: a through-slot it never cut, read from the other side)
        self.assertEqual(_cmp(_close(), g)["geometry"], 4)
        m = _close()
        m[0][64:96, :, 3] = 0.0
        m[1][64:96, :, 3] = 0.0  # (the game has what the master lacks: a hole it capped)
        self.assertEqual(_cmp(m, _close())["geometry"], 4)

    def test_a_silhouette_a_pixel_apart_is_not_judged(self):
        m, g = _close(), _close()
        for pic in (m[0], m[1]):
            pic[:, 64:, 3] = 0.0  # (the master covers the left half)
        for pic in (g[0], g[1]):
            pic[:, 65:, 3] = 0.0  # (the game's edge one pixel further out, its normal turned there)
        g[0][:, 62:65, :3] = np.array((1, 0, 0), np.float32) * 0.5 + 0.5
        self.assertEqual(_cmp(m, g)["faults"], 0)

    def test_a_few_fault_windows_are_allowed_more_fail(self):
        views = {v: {"faults": 0} for v in F["VIEWS"]}
        views["front"]["faults"] = C["MAX_FAULTS"]
        self.assertTrue(C["close_verdict"](views)["pass"])
        views["q34"]["faults"] = 1
        self.assertFalse(C["close_verdict"](views)["pass"])

    def test_the_close_up_gates_the_high_and_low_route_only(self):
        r = F["compare"](_views(128, (0, 0, 1)), _views(128, (0, 0, 1)))
        r["close"] = {"pass": False, "faults": 40}
        self.assertEqual(F["verdict"](r, own_colour=True), (False, ["close-up"]))
        self.assertEqual(F["verdict"](r), (True, []))  # (an optimized game version's close-up pass is reported)


if __name__ == "__main__":
    unittest.main()
