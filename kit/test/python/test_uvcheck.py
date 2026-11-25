"""A baked map's UVs CHECKED (kit/blender/rbx_uvcheck.py; the owner's method lists, 2026-11-13: "UV overlap ...
stretching checks"; the 3D methods audit, M7): faces lying on one piece of the map by accident are found, a copy
laid exactly on its original is not; a texel pulled long over the surface is measured."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_uvcheck as U  # noqa: E402


def mesh(polys, fan=None):
    """polygons (lists of (u, v)) -> uv, start, total, tri, tri_poly; fan[i]: the corner polygon i is fanned from"""
    uv, start, total, tri, tri_poly = [], [], [], [], []
    for i, p in enumerate(polys):
        s, k = len(uv), len(p)
        uv += [tuple(c) for c in p]
        start.append(s)
        total.append(k)
        f = (fan or {}).get(i, 0)
        for j in range(1, k - 1):
            tri.append((s + f, s + (f + j) % k, s + (f + j + 1) % k))
            tri_poly.append(i)
    return (np.array(uv, float), np.array(start), np.array(total), np.array(tri), np.array(tri_poly))


def square(x, y, w=0.1, h=None):
    h = w if h is None else h
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def moved(p, dx=0.0, dy=0.0):
    return [(u + dx, v + dy) for u, v in p]


def probe():
    """kit/selftest/blender/check_repair_cases.py run once in Blender -> its answers (None without Blender)"""
    import json  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
    import cad_check  # noqa: PLC0415

    blender = cad_check.blender()
    if not blender or not os.path.isfile(blender):
        return None
    if not hasattr(probe, "answers"):
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_repair"))
        r = subprocess.run([blender, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(ROOT, "kit", "selftest", "blender", "check_repair_cases.py"), "--",
                            "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=900, env=e,
                           encoding="utf-8", errors="replace")
        line = next((x for x in r.stdout.splitlines() if x.startswith("REPAIR_CASES ")), None)
        assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
        probe.answers = json.loads(line.split(" ", 1)[1])
    return probe.answers


class Overlap(unittest.TestCase):
    def test_neighbours_only_touch(self):
        row = [square(0.1 * i, 0.2) for i in range(5)] + [square(0.1 * i, 0.3) for i in range(5)]
        r = U.overlap(*mesh(row))
        self.assertEqual((r["polys"], r["texels"], r["stacked"], r["share"]), (0, 0, 0, 0.0))
        # (a fan round one corner, every triangle its own polygon)
        c, n = (0.5, 0.5), 12
        rim = [(0.5 + 0.2 * np.cos(2 * np.pi * i / n), 0.5 + 0.2 * np.sin(2 * np.pi * i / n)) for i in range(n)]
        fan = [[c, rim[i], rim[(i + 1) % n]] for i in range(n)]
        self.assertEqual(U.overlap(*mesh(fan))["texels"], 0)

    def test_two_faces_on_one_piece_of_the_map_are_found(self):
        r = U.overlap(*mesh([square(0.1, 0.1), square(0.15, 0.15), square(0.6, 0.6)]))
        self.assertEqual(r["polys"], 2)
        self.assertTrue(np.array_equal(r["mask"], [True, True, False]))
        self.assertAlmostEqual(r["share"], 0.0025 / 0.0275, delta=0.006)  # the texels painted twice, of those painted
        self.assertAlmostEqual(r["texels"], 0.0025 * 2048 * 2048, delta=600)   # (less the rim one texel wide)
        u, v, texels = r["at"][0]
        self.assertTrue(0.12 < u < 0.22 and 0.12 < v < 0.22, r["at"])     # where to look on the map
        self.assertGreater(texels, 9000)

    def test_only_the_builders_own_copies_are_meant(self):
        a = square(0.2, 0.2)
        pile = [a, a, [a[0], a[3], a[2], a[1]]]                            # the same place three times
        said = U.overlap(*mesh(pile))                                      # nobody said they are copies: an accident
        self.assertEqual(said["polys"], 3)
        self.assertGreater(said["share"], 0.9)
        self.assertEqual(said["stacked"], 0)
        meant = U.overlap(*mesh(pile), meant=[False, True, True])          # the builder laid two on the first
        self.assertEqual((meant["polys"], meant["texels"], meant["stacked"]), (0, 0, 2))
        half = U.overlap(*mesh(pile), meant=[False, True, False])          # ... one of them, not the other
        self.assertEqual((half["polys"], half["stacked"]), (2, 1))

    def test_a_copy_only_NEARLY_on_its_original_is_an_accident(self):
        a = square(0.2, 0.2)
        r = U.overlap(*mesh([a, moved(a, 0.004, 0.0)]))                    # four texels off at 1024
        self.assertEqual(r["polys"], 2)
        self.assertGreater(r["share"], 0.9)

    def test_an_unwrap_folded_over_itself_is_found(self):
        strip = [square(0.1, 0.1), square(0.2, 0.1), [(0.3, 0.1), (0.22, 0.1), (0.22, 0.2), (0.3, 0.2)]]
        r = U.overlap(*mesh(strip))                                        # the third quad folds back onto the second
        self.assertEqual(r["polys"], 2)
        self.assertTrue(np.array_equal(r["mask"], [False, True, True]))

    def test_only_an_overlap_wide_enough_to_show_counts(self):
        # two faces lying 0.004 into each other: one texel of a 256 map (nobody sees it), four of a 1024 map
        a, b = square(0.1, 0.1, 0.104, 0.1), square(0.2, 0.1)
        self.assertEqual(U.overlap(*mesh([a, b]), res=256)["texels"], 0)
        seen = U.overlap(*mesh([a, b]), res=1024)
        self.assertGreater(seen["texels"], 150)
        self.assertEqual(seen["polys"], 2)
        # (a face with a hair of its neighbour folded over it, everywhere: a cloth's map - nothing shows)
        cloth = [square(0.01 * i, 0.01 * j, 0.0104) for i in range(40) for j in range(40)]
        self.assertEqual(U.overlap(*mesh(cloth))["texels"], 0)

    def test_what_is_counted_is_the_inside_of_the_patch(self):
        # a strip 8 grid texels wide and 600 long counts its inside: 6 x 598 of 8 x 600
        a, b = square(0.25, 0.25, 0.25 + 8 / 2048, 600 / 2048), square(0.5, 0.25, 0.3, 600 / 2048)
        r = U.overlap(*mesh([a, b]))
        self.assertAlmostEqual(r["texels"], 6 * 598, delta=700)
        self.assertLess(r["texels"], 8 * 600)

    def test_a_big_face_over_many_small_ones(self):
        small = [square(0.02 * i + 0.1, 0.02 * j + 0.1, 0.02) for i in range(20) for j in range(20)]
        big = [(0.0, 0.0), (0.9, 0.05), (0.05, 0.9)]
        r = U.overlap(*mesh(small + [big]))
        inside = sum(1 for p in small if all(u + v < 0.94 for u, v in p))
        self.assertGreaterEqual(r["polys"], inside + 1)
        self.assertTrue(r["mask"][-1])

    def test_a_face_with_no_room_on_the_map_crosses_nothing(self):
        r = U.overlap(*mesh([square(0.1, 0.1), [(0.15, 0.15), (0.15, 0.15), (0.15, 0.15)]]))
        self.assertEqual(r["polys"], 0)

    def test_a_place_off_the_map_or_not_a_number_does_not_stop_it(self):
        bad = [square(0.1, 0.1), square(1.4, -0.3), [(float("nan"), 0.2), (0.3, 0.2), (0.3, 0.3)]]
        self.assertEqual(U.overlap(*mesh(bad))["polys"], 0)

    def test_long_slivers_cost_what_the_map_costs(self):
        # a many-sided face cut into slivers from one corner, beside 19,000 small faces: seconds, not minutes
        import time  # noqa: PLC0415

        n = 1500
        rim = [(0.5 + 0.45 * np.cos(np.pi * i / n), 0.02 + 0.45 * np.sin(np.pi * i / n)) for i in range(n + 1)]
        slivers = [[(0.5, 0.02), rim[i], rim[i + 1]] for i in range(n)]
        small = [square(0.005 * i + 0.01, 0.005 * j + 0.5, 0.005) for i in range(196) for j in range(98)]
        t = time.time()
        r = U.overlap(*mesh(slivers + small))
        self.assertLess(time.time() - t, 20)
        self.assertEqual(r["texels"], 0)


class Runs(unittest.TestCase):
    def grid(self, tris, n):
        which, row, c0, c1 = U.runs(np.array(tris, float), n)
        g = np.zeros((n, n), int)
        for r, a, b in zip(row, c0, c1, strict=True):
            g[r, a:b] += 1
        return g

    def test_a_face_fills_the_texel_centres_inside_it(self):
        g = self.grid([[(0, 0), (1, 0), (1, 1)], [(0, 0), (1, 1), (0, 1)]], 8)   # the whole map, as two triangles
        self.assertTrue((g == 1).all())
        g = self.grid([[(0.25, 0.25), (0.75, 0.25), (0.75, 0.75)], [(0.25, 0.25), (0.75, 0.75), (0.25, 0.75)]], 8)
        self.assertEqual(int(g.sum()), 16)
        self.assertTrue((g[2:6, 2:6] == 1).all())

    def test_an_edge_two_faces_share_is_painted_once(self):
        # the shared edge lies exactly ON a column of texel centres (x = 2.5 / 8)
        a = [[(0.125, 0.0), (0.3125, 0.0), (0.3125, 1.0)], [(0.125, 0.0), (0.3125, 1.0), (0.125, 1.0)]]
        b = [[(0.3125, 0.0), (0.5, 0.0), (0.5, 1.0)], [(0.3125, 0.0), (0.5, 1.0), (0.3125, 1.0)]]
        g = self.grid(a + b, 8)
        self.assertEqual(int(g.max()), 1)
        self.assertTrue((g[:, 1:4] == 1).all())

    def test_a_face_thinner_than_a_texel_between_two_centres_paints_nothing(self):
        g = self.grid([[(0.01, 0.01), (0.9, 0.012), (0.9, 0.02)]], 8)
        self.assertEqual(int(g.sum()), 0)


class Stretch(unittest.TestCase):
    def quad(self, w, h, uw=0.5, uh=0.5, shear=0.0):
        uv = np.array([[(0, 0), (uw, 0), (uw, uh)], [(0, 0), (uw, uh), (0, uh)]], float)
        p = np.array([[(0, 0, 0), (w, 0, 0), (w + shear, h, 0)], [(0, 0, 0), (w + shear, h, 0), (shear, h, 0)]], float)
        return uv, p

    def test_a_square_on_a_square_is_one(self):
        r = U.stretch(*self.quad(2, 2))
        self.assertEqual((r["p50"], r["p90"], r["max"], r["share"], r["crushed"]), (1.0, 1.0, 1.0, 0.0, 0.0))

    def test_a_long_face_on_a_square_piece_of_map(self):
        r = U.stretch(*self.quad(6, 2))
        self.assertAlmostEqual(r["max"], 3.0, places=3)
        self.assertEqual(r["share"], 1.0)
        self.assertAlmostEqual(r["at"][0][2], 3.0, places=2)
        self.assertEqual(U.stretch(*self.quad(3, 2))["share"], 0.0)      # 1.5: under the limit of 2

    def test_the_maps_own_shape_does_not_matter_only_the_ratio(self):
        self.assertAlmostEqual(U.stretch(*self.quad(6, 2, uw=0.6, uh=0.2))["max"], 1.0, places=6)
        self.assertAlmostEqual(U.stretch(*self.quad(2, 2, uw=0.8, uh=0.1))["max"], 8.0, places=4)

    def test_a_sheared_face_is_stretched_too(self):
        r = U.stretch(*self.quad(2, 2, shear=3.0))
        self.assertGreater(r["max"], 3.0)

    def test_it_is_weighed_by_surface(self):
        uv1, p1 = self.quad(6, 2)                                          # 12 of surface, stretched
        uv2, p2 = self.quad(6, 6)                                          # 36 of surface, square
        r = U.stretch(np.concatenate([uv1, uv2]), np.concatenate([p1, p2 + (0, 10, 0)]))
        self.assertAlmostEqual(r["share"], 0.25, places=4)
        self.assertEqual(r["p50"], 1.0)

    def test_a_face_with_no_room_on_the_map_is_crushed(self):
        uv, p = self.quad(2, 2)
        uv[1] = (0.3, 0.3)                                                 # the second triangle: one point
        r = U.stretch(uv, p)
        self.assertAlmostEqual(r["crushed"], 0.5, places=4)
        self.assertEqual(r["share"], 0.0)                                  # ... said there, not twice
        self.assertTrue(np.isinf(r["ratio"][1]))

    def test_nothing_to_measure(self):
        r = U.stretch(np.zeros((0, 3, 2)), np.zeros((0, 3, 3)))
        self.assertEqual((r["share"], r["max"]), (0.0, 1.0))


class Build(unittest.TestCase):
    # (both checks are ERRORS since 2026-11-17 - the owner's limitations review: "promote all 3 to blocking errors")
    """the builder's own check of a part's map (rbx.Asset._uv_check), on faces given their places by hand"""

    def setUp(self):
        got = probe()
        if got is None:
            self.skipTest("Blender not found")
        self.uv = got["uv"]

    def test_faces_apart_on_the_map_pass(self):
        got = self.uv["Apart"]
        self.assertEqual((got["facts"]["overlap"], got["facts"]["overlap_faces"]), (0.0, 0))
        self.assertEqual(got["checks"], {"uv_overlap": [True, "error"], "uv_stretch": [True, "error"]})

    def test_two_faces_on_one_piece_of_the_map_are_said(self):
        got = self.uv["Crossed"]
        self.assertAlmostEqual(got["facts"]["overlap"], 0.015 / 0.065, delta=0.01)
        self.assertEqual(got["facts"]["overlap_faces"], 2)
        self.assertEqual(got["checks"]["uv_overlap"], [False, "error"])

    def test_a_copy_the_builder_laid_on_its_original_is_not(self):
        got = self.uv["Stacked"]                                           # (its record says the second is a copy)
        self.assertEqual((got["facts"]["overlap"], got["facts"]["stacked"]), (0.0, 1))
        self.assertEqual(got["checks"]["uv_overlap"], [True, "error"])

    def test_two_faces_on_the_very_same_place_that_are_no_copies_are_said(self):
        got = self.uv["Piled"]                                             # a front laid on its back: no record
        self.assertGreater(got["facts"]["overlap"], 0.9)
        self.assertEqual((got["facts"]["stacked"], got["checks"]["uv_overlap"]), (0, [False, "error"]))

    def test_a_long_face_on_a_square_piece_of_the_map_is_stretched(self):
        got = self.uv["Long"]
        self.assertEqual((got["facts"]["stretch_p50"], got["facts"]["stretched"]), (4.0, 1.0))
        self.assertEqual(got["checks"]["uv_stretch"], [False, "error"])


if __name__ == "__main__":
    unittest.main()
