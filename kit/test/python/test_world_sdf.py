"""test_world_sdf.py - LAND AS A SIGNED DISTANCE (kit/world/sdf.py; the owner's method list: "Signed distance field / SDF
terrain"). Each shape is held to plain geometry (a ball's surface is its radius from its centre), joining and cutting
to what they mean, and the whole to ONE TABLE OF POINTS that the game's own copy of the rules
(src/kit/SdfRules.luau, kit/test/spec/worldsdf.spec.luau) is held to as well: the walk check and the game read the
same land.
Not claimed here: that a cave or an arch made this way looks like rock. That is a built world, looked at."""
import importlib.util
import math
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_world_sdf", os.path.join(HERE, "..", "..", "world", "sdf.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

# one land of five shapes and 48 points with the land's distance and the cut's at each (the same table stands in
# kit/test/spec/worldsdf.spec.luau; written by one script from one run)
SPEC = {'material': 'Rock', 'shapes': [{'box': {'center': [0, 20, 0], 'size': [80, 40, 24], 'round': 6}}, {'ball': {'center': [50, 30, 0], 'radius': 22}, 'blend': 10}, {'capsule': {'from': [-20, 12, -30], 'to': [10, 16, 30], 'radius': 9}, 'cut': True, 'blend': 4}, {'ball': {'center': [-30, 40, 0], 'radius': 14}, 'cut': True}, {'capsule': {'from': [0, 45, 0], 'to': [0, 70, 0], 'radius': 5}}]}
ROWS = [
    [-18.66, 16.92, -20.83, 8.829999999999998, -3.7394524107385942],
    [19.31, 26.33, -22.1, 9.679088856877495, 25.13308656818763],
    [15.89, 2.7, -3.32, -2.6999999999999993, 14.296803667371023],
    [-39.82, 38.19, 7.84, 1.4036545030140344, -1.3045638121409944],
    [-30.14, 16.07, 6.37, -5.63, 10.763711353510807],
    [68.73, 41.55, -5.17, 0.6040770658746446, 63.97624989606432],
    [-1.59, 24.51, 23.53, 11.530000000000001, 2.812223218365629],
    [-27.69, 8.48, -9.58, -2.42, 7.60284612821339],
    [52.94, 13.01, 4.08, -4.281362919231061, 41.07392862724592],
    [-33.06, 41.15, -10.49, 3.0124525029468003, -3.0124525029468003],
    [-37.85, 14.83, 9.02, -1.106851729203374, 13.865961314837143],
    [6.31, 22.62, 4.28, -2.5104078908609786, 2.5104078908609786],
    [-11.21, 20.88, 1.97, -0.4559375575879656, 0.4559375575879656],
    [-15.71, 41.36, 1.26, 1.3599999999999994, 0.40976405080943756],
    [60.02, 52.52, -10.6, 4.831153534650728, 64.11710529919745],
    [-39.17, 38.03, 6.17, 2.773304137013419, -2.773304137013419],
    [-26.76, 35.21, -23.04, 11.082906661338402, 9.754647966240206],
    [35.19, 55.05, 3.65, 7.202514535433577, 43.484529581104816],
    [1.79, 20.19, 24.79, 12.79, -2.142807478089088],
    [24.59, 32.85, 17.0, 4.009291444060401, 16.476592443519902],
    [68.36, 34.14, 8.21, -1.4662886939550042, 55.88261169219378],
    [-25.16, 43.53, 11.83, 5.171830646765105, -0.7397058856147538],
    [53.63, 20.49, -5.71, -10.328620475710679, 46.24121005871529],
    [35.24, 1.62, -1.92, -1.4478576472170825, 30.186232307789822],
    [-24.15, 2.09, -13.48, 2.4402902793683587, 6.390687949327905],
    [-29.48, 17.83, -5.45, -6.55, 8.835976002789987],
    [59.57, 5.8, -2.54, 4.147208263981071, 50.69387559033003],
    [-20.8, 47.66, 8.74, 7.932092448731451, 0.8223884714981047],
    [-11.59, 29.9, -7.06, -4.835928177669666, 7.6495934139638955],
    [61.1, 68.96, -17.45, 22.108889126796193, 77.0144440282447],
    [-21.15, 6.3, -19.79, 7.789999999999999, -0.6468354649138259],
    [25.69, 18.92, -24.8, 11.05796817687888, 29.919364146657884],
    [5.27, 26.59, 3.32, -5.328899250012758, 5.35759520377384],
    [-25.43, 40.37, 2.82, 8.617231195750648, -8.617231195750648],
    [36.14, 3.89, 19.98, 7.765810606306739, 21.50167372456797],
    [48.6, 62.96, 14.89, 14.194387686490842, 53.63795734217392],
    [-10.65, 4.05, -3.23, -1.1730170409418008, 1.2653314491471885],
    [-37.53, 4.85, -14.56, 3.3304340735037634, 14.794756262627995],
    [-25.52, 24.48, -22.37, 10.370000000000001, 5.782408802656535],
    [-38.37, 30.44, -3.27, 0.879657016678264, -0.879657016678264],
    [-41.94, 62.95, 5.7, 24.01909558930782, 12.490679492983944],
    [-27.17, 18.16, -7.63, -4.368313310962939, 8.205722720399358],
    [-18.13, 21.83, 3.68, -6.262170330195694, 6.581945040619697],
    [10.92, 34.84, -20.71, 8.733964164473864, 22.83975689498862],
    [-32.74, 24.67, -11.76, -0.2400000000000002, 5.514458742173709],
    [-38.13, 28.55, 10.82, 0.3473852884475219, 3.727712768431239],
    [18.39, 10.56, 2.16, -9.46362900067849, 11.386036677302581],
    [-41.75, 38.02, 23.93, 13.942612667351288, 12.732523262872139],
]


class Shapes(unittest.TestCase):
    def test_a_ball_is_its_radius_from_its_centre(self):
        ball = {"ball": {"center": [10, 20, 30], "radius": 5}}
        self.assertAlmostEqual(S.shape(ball, 10, 20, 30), -5)
        self.assertAlmostEqual(S.shape(ball, 15, 20, 30), 0)
        self.assertAlmostEqual(S.shape(ball, 10, 28, 30), 3)
        self.assertAlmostEqual(S.shape(ball, 13, 24, 30), 0)  # (3, 4, 5)

    def test_a_box_by_its_faces_edges_and_corners_round_or_sharp(self):
        box = {"box": {"center": [0, 0, 0], "size": [20, 10, 8]}}
        self.assertAlmostEqual(S.shape(box, 0, 0, 0), -4)  # (its nearest face is 4 away)
        self.assertAlmostEqual(S.shape(box, 10, 0, 0), 0)
        self.assertAlmostEqual(S.shape(box, 13, 0, 0), 3)
        self.assertAlmostEqual(S.shape(box, 13, 9, 0), 5)  # (off an edge: 3 and 4)
        self.assertAlmostEqual(S.shape(box, 12, 7, 8), math.sqrt(4 + 4 + 16))  # (off a corner)
        self.assertAlmostEqual(S.shape(box, 9, 0, 0), -1)
        rounded = {"box": {"center": [0, 0, 0], "size": [20, 10, 8], "round": 2}}
        self.assertAlmostEqual(S.shape(rounded, 10, 0, 0), 0)  # (a face stays where it was)
        self.assertAlmostEqual(S.shape(rounded, 13, 0, 0), 3)
        # ... and its corner is cut back: the sharp corner's own point is outside the rounded box
        self.assertAlmostEqual(S.shape(box, 10, 5, 4), 0)
        self.assertAlmostEqual(S.shape(rounded, 10, 5, 4), math.sqrt(12) - 2)

    def test_a_capsule_is_its_radius_from_its_line(self):
        cap = {"capsule": {"from": [0, 0, 0], "to": [10, 0, 0], "radius": 3}}
        self.assertAlmostEqual(S.shape(cap, 5, 0, 0), -3)
        self.assertAlmostEqual(S.shape(cap, 5, 3, 0), 0)
        self.assertAlmostEqual(S.shape(cap, 5, 0, 7), 4)
        self.assertAlmostEqual(S.shape(cap, -3, 0, 0), 0)  # (round ends)
        self.assertAlmostEqual(S.shape(cap, 13, 4, 0), 2)  # (3, 4, 5 from its far end)
        dot = {"capsule": {"from": [1, 2, 3], "to": [1, 2, 3], "radius": 3}}  # (no length: a ball)
        self.assertAlmostEqual(S.shape(dot, 1, 7, 3), 2)


class Joining(unittest.TestCase):
    def test_joined_is_the_least_and_a_blend_rounds_the_seam_inward(self):
        self.assertEqual(S.smin(3, 5, 0), 3)
        self.assertEqual(S.smin(5, 3, 0), 3)
        self.assertEqual(S.smin(3, 5, 1), 3)  # (farther apart than the blend: the least, untouched)
        self.assertAlmostEqual(S.smin(3, 3, 4), 2)  # (at the seam itself: a quarter of the blend deeper)
        self.assertAlmostEqual(S.smin(3, 4, 4), 3 - (3 / 4) ** 2)
        self.assertEqual(S.smin(3, 4, 4), S.smin(4, 3, 4))
        two = {"shapes": [{"ball": {"center": [0, 0, 0], "radius": 10}}, {"ball": {"center": [16, 0, 0], "radius": 10}}]}
        self.assertTrue(S.at(two, 8, 5, 0)[0] < 0)  # (in both)
        self.assertTrue(S.at(two, 8, 7, 0)[0] > 0)  # (in the notch between them, above their seam)
        two["shapes"][1]["blend"] = 8
        self.assertTrue(S.at(two, 8, 7, 0)[0] < 0)  # (the blend fills the notch)
        self.assertAlmostEqual(S.at(two, -10, 0, 0)[0], 0)  # (far from the seam nothing moves)

    def test_a_cut_takes_out_of_the_land_and_of_what_was_there(self):
        hill = {"shapes": [{"ball": {"center": [0, 0, 0], "radius": 20}},
                           {"capsule": {"from": [-30, 0, 0], "to": [30, 0, 0], "radius": 5}, "cut": True}]}
        d, cut = S.at(hill, 0, 0, 0)
        self.assertAlmostEqual(d, 5)  # (in the tunnel: 5 from its wall, outside the land)
        self.assertAlmostEqual(cut, -5)
        d, cut = S.at(hill, 0, 10, 0)
        self.assertAlmostEqual(d, -5)  # (in the rock over the tunnel: 5 from the tunnel's wall)
        self.assertAlmostEqual(cut, 5)
        d, cut = S.at(hill, 25, 0, 0)  # (in the tunnel's mouth, outside the hill: cut all the same)
        self.assertTrue(d > 0 and cut < 0)
        self.assertEqual(S.solid(hill, 0, 0, 0), (False, True))
        self.assertEqual(S.solid(hill, 0, 10, 0), (True, False))
        self.assertEqual(S.solid(hill, 0, 40, 0), (False, False))
        # the order is read: a shape added AFTER the cut fills it again where it stands
        hill["shapes"].append({"ball": {"center": [0, 0, 0], "radius": 3}})
        self.assertEqual(S.solid(hill, 0, 0, 0), (True, False))
        self.assertEqual(S.solid(hill, 0, 4, 0), (False, True))  # (beside the plug the tunnel is still open)
        # ... and a later cut through that plug opens it again: what the first cut took out of the old land stays out
        hill["shapes"].append({"ball": {"center": [3, 0, 0], "radius": 4}, "cut": True, "blend": 3})
        for p in ((2, 0, 0), (0.5, 0, 0), (-1, 0, 0), (0, 2.5, 0)):
            d, cut = S.at(hill, *p)
            self.assertFalse(d >= 0 and cut >= 0, p)  # (never "not land, and not cut": old rock would float there)
        self.assertEqual(S.solid(hill, 2, 0, 0), (False, True))
        # two cuts that meet: the seam between them is rounded by the later one's blend - also in the land before
        two = {"shapes": [{"ball": {"center": [0, 0, 0], "radius": 10}, "cut": True},
                          {"ball": {"center": [16, 0, 0], "radius": 10}, "cut": True}]}
        self.assertTrue(S.at(two, 8, 7, 0)[1] > 0)  # (in the notch between the two holes: rock)
        two["shapes"][1]["blend"] = 8
        self.assertTrue(S.at(two, 8, 7, 0)[1] < 0)  # (the blend opens the notch)
        self.assertAlmostEqual(S.at(two, -10, 0, 0)[1], 0)
        # one cut alone is as wide with a blend as without: the land before the op has no seam to round
        for k in (0, 16):
            one = {"shapes": [{"capsule": {"from": [-30, 0, 0], "to": [30, 0, 0], "radius": 5}, "cut": True, "blend": k}]}
            self.assertAlmostEqual(S.at(one, 0, 6, 0)[1], 1)
        # a cut alone makes no land, and still cuts
        self.assertEqual(S.solid({"shapes": [{"ball": {"center": [0, 0, 0], "radius": 8}, "cut": True}]}, 1, 1, 1), (False, True))

    def test_the_box_the_shapes_lie_in(self):
        lo, hi = S.bounds({"shapes": [{"ball": {"center": [0, 10, 0], "radius": 5}}]})
        self.assertEqual((lo, hi), ([-9, 1, -9], [9, 19, 9]))  # (the ball and a cell)
        lo, hi = S.bounds({"shapes": [{"ball": {"center": [0, 10, 0], "radius": 5}, "blend": 6},
                                      {"box": {"center": [40, 0, 0], "size": [10, 20, 30]}},
                                      {"capsule": {"from": [0, 0, -50], "to": [0, 30, 0], "radius": 2}, "cut": True}]})
        self.assertEqual(lo, [-15, -14, -56])
        self.assertEqual(hi, [49, 36, 19])
        # nothing of the land lies outside its box
        lo, hi = S.bounds(SPEC)
        for x, y, z, d, cut in ROWS:
            if d < 0 or cut < 0:
                self.assertTrue(all(lo[i] <= p <= hi[i] for i, p in enumerate((x, y, z))))

    def test_what_a_cell_becomes(self):
        self.assertEqual(S.cell(-2, S.FAR), (1.0, 0.0))  # (half a cell inside: full)
        self.assertEqual(S.cell(2, S.FAR), (0.0, 0.0))
        self.assertEqual(S.cell(0, S.FAR), (0.5, 0.0))  # (on the surface: half)
        self.assertEqual(S.cell(1, S.FAR), (0.25, 0.0))
        self.assertEqual(S.cell(5, -2), (0.0, 1.0))  # (in a cut: cleared)
        self.assertEqual(S.cell(5, 0), (0.0, 0.5))
        self.assertEqual(S.cell(5, 2), (0.0, 0.0))
        self.assertEqual(S.cell(-1, S.FAR), (0.75, 0.0))  # (a quarter of the way in: three quarters full)
        self.assertEqual(S.cell(5, -1), (0.0, 0.75))
        self.assertEqual(S.cell(5, 1), (0.0, 0.25))


class TheSameAsTheGame(unittest.TestCase):
    def test_the_table_of_points(self):
        inside = cut = 0
        for x, y, z, d, c in ROWS:
            got_d, got_c = S.at(SPEC, x, y, z)
            self.assertAlmostEqual(got_d, d, places=9)
            self.assertAlmostEqual(got_c, c if c < 1e8 else S.FAR, places=9)
            inside += d < 0
            cut += c < 0
        self.assertTrue(inside >= 10 and cut >= 5 and len(ROWS) - inside >= 10)  # (the table reaches all three)


class ManyAtOnce(unittest.TestCase):
    def test_many_points_at_once_come_to_the_same_numbers(self):
        import numpy as np

        pts = np.array([[x, y, z] for x, y, z, _, _ in ROWS], dtype=float)
        d, cut = S.at_many(SPEC, pts)
        for i, (x, y, z, want_d, want_c) in enumerate(ROWS):
            self.assertAlmostEqual(d[i], want_d, places=9)
            self.assertAlmostEqual(cut[i], want_c if want_c < 1e8 else S.FAR, places=9)
        # a capsule of no length, a sharp and a blended cut, shapes in another order
        other = {"shapes": [{"capsule": {"from": [1, 2, 3], "to": [1, 2, 3], "radius": 6}},
                            {"box": {"center": [4, 2, 3], "size": [6, 6, 6]}, "cut": True, "blend": 3},
                            {"ball": {"center": [-2, 2, 3], "radius": 3}, "cut": True},
                            {"ball": {"center": [5, 2, 3], "radius": 2}, "blend": 2}]}
        pts = np.array([[x * 0.7 - 6, y * 0.9 - 2, 3 + (x - y) * 0.3] for x in range(18) for y in range(9)], dtype=float)
        d, cut = S.at_many(other, pts)
        for i, p in enumerate(pts):
            one_d, one_c = S.at(other, *p)
            self.assertAlmostEqual(d[i], one_d, places=9)
            self.assertAlmostEqual(cut[i], one_c, places=9)


    def test_many_at_once_a_shape_added_after_a_cut_fills_it(self):
        import numpy as np

        hill = {"shapes": [{"ball": {"center": [0, 0, 0], "radius": 20}},
                           {"capsule": {"from": [-30, 0, 0], "to": [30, 0, 0], "radius": 5}, "cut": True},
                           {"ball": {"center": [0, 0, 0], "radius": 3}}]}
        pts = np.array([[0, 0, 0], [0, 4, 0], [0, 10, 0], [25, 0, 0], [0, 40, 0], [1, 1, 1]], dtype=float)
        d, cut = S.at_many(hill, pts)
        for i, p in enumerate(pts):
            one_d, one_c = S.at(hill, *p)
            self.assertAlmostEqual(d[i], one_d, places=9)
            self.assertAlmostEqual(cut[i], one_c, places=9)
        self.assertTrue(d[0] < 0 and cut[0] < 0)  # (in the plug: land, inside the cut it fills)
        self.assertTrue(d[1] > 0 and cut[1] < 0)  # (beside it, in the tunnel)
        two = {"shapes": [{"ball": {"center": [0, 0, 0], "radius": 10}, "cut": True},
                          {"ball": {"center": [16, 0, 0], "radius": 10}, "cut": True, "blend": 8}]}
        pts = np.array([[8, 7, 0], [8, 9, 0], [0, 0, 0], [16, 12, 0], [8, 0, 0]], dtype=float)
        d, cut = S.at_many(two, pts)
        for i, p in enumerate(pts):
            self.assertAlmostEqual(cut[i], S.at(two, *p)[1], places=9)
        self.assertTrue(cut[0] < 0)  # (the notch between the two holes, opened by the blend)


class InTheWalkCheck(unittest.TestCase):
    """the walk check's own grid of solid cells (kit/world/worldcheck.py Grid): land filled, then an sdf op"""

    def grid(self):
        import numpy as np

        spec = importlib.util.spec_from_file_location("kit_worldcheck", os.path.join(HERE, "..", "..", "world", "worldcheck.py"))
        wc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wc)
        g = wc.Grid(np.array([-60.0, -4.0, -40.0]), np.array([60.0, 60.0, 40.0]), 1.0)
        # a ridge of land across the grid: x -20..20, up to y 40
        g.fill_solid({"kind": "block", "spec": {"center": [0, 18, 0], "size": [40, 44, 80]}})
        return g, np

    def solid(self, g, x, y, z):
        i = g.index([x, y, z])
        return bool(g.occ[i[0], i[1], i[2]])

    def test_a_cut_takes_a_tunnel_out_of_the_land_that_was_there(self):
        g, np = self.grid()
        self.assertTrue(self.solid(g, 0.5, 6.5, 0.5))
        before = int(g.occ.sum())
        g.fill_solid({"kind": "sdf", "spec": {"material": "Rock", "shapes": [
            {"capsule": {"from": [-30, 7, 0], "to": [30, 7, 0], "radius": 7}, "cut": True}]}})
        for x in (-19.5, -10.5, 0.5, 10.5, 19.5):
            self.assertFalse(self.solid(g, x, 6.5, 0.5), x)  # (the tunnel's middle, all the way through)
            self.assertFalse(self.solid(g, x, 2.5, 3.5), x)
            self.assertTrue(self.solid(g, x, 6.5, 8.5), x)  # (beside the tunnel: rock)
            self.assertTrue(self.solid(g, x, 16.5, 0.5), x)  # (over it: rock)
            self.assertTrue(self.solid(g, x, 30.5, 30.5), x)
        # to the cell: the last cell inside the tunnel's wall is open, the first outside it is rock, both sides
        self.assertFalse(self.solid(g, 0.5, 7.5, 6.5))
        self.assertTrue(self.solid(g, 0.5, 7.5, 7.5))
        self.assertFalse(self.solid(g, 0.5, 7.5, -6.5))
        self.assertTrue(self.solid(g, 0.5, 7.5, -7.5))
        self.assertFalse(self.solid(g, 0.5, 13.5, 0.5))
        self.assertTrue(self.solid(g, 0.5, 14.5, 0.5))
        # what was taken out is the tunnel inside the ridge: about a cylinder 40 long of radius 7 (less its part
        # under the ridge's foot at y -4)
        gone = before - int(g.occ.sum())
        self.assertTrue(40 * math.pi * 49 * 0.9 < gone < 40 * math.pi * 49 * 1.02, gone)

    def test_an_arch_is_land_where_there_was_none_and_open_under_it(self):
        g, np = self.grid()
        g.fill_solid({"kind": "sdf", "spec": {"material": "Rock", "shapes": [
            {"box": {"center": [40, 12, 0], "size": [12, 24, 40]}},
            {"capsule": {"from": [30, 0, 0], "to": [50, 0, 0], "radius": 12}, "cut": True}]}})
        self.assertTrue(self.solid(g, 40.5, 20.5, 0.5))  # (the arch's crown)
        self.assertTrue(self.solid(g, 40.5, 4.5, 16.5))  # (its leg)
        self.assertFalse(self.solid(g, 40.5, 4.5, 0.5))  # (open under it)
        self.assertFalse(self.solid(g, 40.5, 30.5, 0.5))  # (air over it)
        self.assertFalse(self.solid(g, 55.5, 4.5, 16.5))  # (and beside it)
        # the ridge beside it is as it was
        self.assertTrue(self.solid(g, 0.5, 6.5, 0.5))

    def test_land_added_after_a_cut_stands_in_the_grid_and_a_later_cut_opens_it(self):
        g, np = self.grid()
        shapes = [{"capsule": {"from": [-30, 7, 0], "to": [30, 7, 0], "radius": 7}, "cut": True},
                  {"ball": {"center": [0, 7, 0], "radius": 5}}]
        g.fill_solid({"kind": "sdf", "spec": {"material": "Rock", "shapes": shapes}})
        self.assertTrue(self.solid(g, 0.5, 7.5, 0.5))  # (the plug in the tunnel)
        self.assertFalse(self.solid(g, 10.5, 7.5, 0.5))  # (the tunnel beside it)
        g, np = self.grid()
        shapes.append({"ball": {"center": [0, 7, 0], "radius": 4}, "cut": True, "blend": 3})
        g.fill_solid({"kind": "sdf", "spec": {"material": "Rock", "shapes": shapes}})
        for x in (-6.5, -3.5, 0.5, 3.5, 6.5):
            for y in (2.5, 7.5, 11.5):
                self.assertFalse(self.solid(g, x, y, 0.5), (x, y))  # (no rock of the old ridge left in the tunnel)

    def test_land_at_the_grids_high_edge_is_filled(self):
        g, np = self.grid()
        g.fill_solid({"kind": "sdf", "spec": {"material": "Rock", "shapes": [
            {"box": {"center": [50, 50, 30], "size": [16, 24, 16]}}]}})
        self.assertTrue(self.solid(g, 50.5, 59.5, 30.5))  # (the grid's last layer: y 59..60)
        self.assertTrue(self.solid(g, 57.5, 59.5, 37.5))
        self.assertFalse(self.solid(g, 59.5, 59.5, 39.5))

    def test_a_slanted_lane_beside_sdf_land_does_not_crash(self):
        spec = importlib.util.spec_from_file_location("kit_worldcheck2", os.path.join(HERE, "..", "..", "world", "worldcheck.py"))
        wc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wc)
        lane = wc.Lane([], terrain_solids=[
            {"kind": "sdf", "spec": {"material": "Rock", "shapes": [{"ball": {"center": [0, 0, 0], "radius": 10}}]}},
            {"kind": "block", "spec": {"center": [0, 5, 0], "size": [4, 10, 4]}}])
        self.assertEqual(len(lane.boxes), 1)  # (the block; the sdf has no box of its own)

    def test_an_op_off_the_grid_changes_nothing(self):
        g, np = self.grid()
        before = g.occ.copy()
        g.fill_solid({"kind": "sdf", "spec": {"material": "Rock", "shapes": [{"ball": {"center": [500, 0, 0], "radius": 10}}]}})
        self.assertTrue((g.occ == before).all())


if __name__ == "__main__":
    unittest.main()
