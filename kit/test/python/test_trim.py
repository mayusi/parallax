"""Trim sheets and a kit of modules (kit/blender/rbx_trim.py; the owner's method lists: trim sheets, trim sheet UV
mapping, seamless / tileable textures, modular asset construction, modular snapping; the 3D methods audit, S2):
where the bands lie, a face laid into a band, a map made to repeat, a module held to its grid."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_trim as T  # noqa: E402

BANDS = [{"name": "plank", "height": 2.0}, {"name": "edge", "height": 0.5}, {"name": "rivets", "height": 0.5}]


class Layout(unittest.TestCase):
    def test_bands_lie_top_to_bottom_by_their_heights_with_a_gutter_between(self):
        lay = T.layout(BANDS, 1024, 4.0)                                         # a sheet 4 studs wide (and tall)
        g = 4 / 1024
        self.assertAlmostEqual(lay["plank"]["v1"], 1 - g, places=5)
        spans = {n: b["v1"] - b["v0"] for n, b in lay.items()}
        self.assertAlmostEqual(spans["plank"], 2.0 / 4.0, places=5)                  # ONE scale: 2 studs of 4
        self.assertAlmostEqual(spans["edge"], 0.5 / 4.0, places=5)
        self.assertGreater(lay["rivets"]["v0"], 0.2)                                 # (the rest of the sheet is free)
        self.assertAlmostEqual(lay["plank"]["v0"] - lay["edge"]["v1"], 2 * g, places=5)   # a gutter each side
        self.assertEqual(lay["plank"]["height"], 2.0)

    def test_a_sheet_that_cannot_be_laid_out_says_why(self):
        for bad in ([], [{"name": "a", "height": 1}, {"name": "a", "height": 1}], [{"name": "a", "height": 0}]):
            with self.assertRaises(ValueError):
                T.layout(bad, 1024, 8.0)
        with self.assertRaises(ValueError) as e:
            T.layout(BANDS, 1024, 2.9)                                               # 3 studs of bands on 2.9
        self.assertIn("studs more than the sheet", str(e.exception))
        T.layout(BANDS, 1024, 3.1)                                                   # ... and they fit 3.1


def box(lo, hi):
    """a box's 8 points and 6 faces, wound outward"""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    pts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5)]
    return np.array(pts, float), faces                       # -z, +z, -y, +y, -x, +x


class Faces(unittest.TestCase):
    BAND = {"v0": 0.25, "v1": 0.75, "height": 4.0}

    def setUp(self):
        # a wall 8 long (x), 4 tall (y), 1 thick (z), on a sheet 8 studs wide
        self.pts, self.faces = box((0, 0, 0), (8, 4, 1))
        self.uvs, self.sides = T.lay(self.pts, self.faces, self.BAND, 8.0, along=(1, 0, 0))

    def at(self, face, point):
        return self.uvs[face][list(self.faces[face]).index(point)]

    def test_the_finish_is_the_same_way_up_on_the_front_and_on_the_back(self):
        # the review's find: the back of every wall was upside down
        for face in (0, 1):                                              # the -z side and the +z side
            for i, point in enumerate(self.faces[face]):
                y = self.pts[point][1]
                self.assertAlmostEqual(self.uvs[face][i][1], 0.25 + 0.5 * y / 4.0, msg=(face, point))
        self.assertAlmostEqual(self.at(0, 3)[1], 0.75)                    # the top edge: the band's top, both sides
        self.assertAlmostEqual(self.at(1, 7)[1], 0.75)

    def test_u_runs_along_the_band_on_both_sides_from_the_parts_own_end(self):
        for face in (0, 1):
            for i, point in enumerate(self.faces[face]):
                self.assertAlmostEqual(self.uvs[face][i][0], self.pts[point][0] / 8.0, msg=(face, point))

    def test_a_side_split_into_several_faces_carries_one_run_of_the_finish(self):
        # the review's find: every polygon started the finish again. The front as three quads and two triangles:
        pts = np.array([(0, 0, 0), (3, 0, 0), (8, 0, 0), (0, 4, 0), (3, 4, 0), (8, 4, 0), (0, 2, 0), (3, 2, 0)], float)
        faces = [(0, 6, 7, 1), (6, 3, 4, 7), (1, 4, 5), (1, 5, 2)]       # (wound to face -z)
        uvs, sides = T.lay(pts, faces, self.BAND, 8.0, along=(1, 0, 0))
        self.assertEqual(len(sides), 1)
        for f, uv in zip(faces, uvs):
            for point, (u, v) in zip(f, uv):
                self.assertAlmostEqual(u, pts[point][0] / 8.0, msg=point)
                self.assertAlmostEqual(v, 0.25 + 0.5 * pts[point][1] / 4.0, msg=point)

    def test_a_top_runs_along_the_band_and_fills_it_across_the_parts_depth(self):
        top = 3                                                           # the +y face
        us = sorted({round(float(u), 6) for u, _v in self.uvs[top]})
        vs = sorted({round(float(v), 6) for _u, v in self.uvs[top]})
        self.assertEqual(us, [0.0, 1.0])                                  # 8 studs along x: once round the sheet
        self.assertEqual(vs, [0.25, 0.75])                                # its 1 stud of depth fills the band

    def test_an_end_cap_is_laid_level_and_the_right_way_up(self):
        for face in (4, 5):                                               # the -x end and the +x end
            for i, point in enumerate(self.faces[face]):
                self.assertAlmostEqual(self.uvs[face][i][1], 0.25 + 0.5 * self.pts[point][1] / 4.0)
            us = sorted({round(float(u), 6) for u, _v in self.uvs[face]})
            self.assertAlmostEqual(us[-1] - us[0], 1.0 / 8.0)             # 1 stud thick on an 8-stud sheet

    def test_with_no_direction_given_the_band_runs_along_the_parts_longest_side(self):
        pts, faces = box((0, 0, 0), (1, 4, 6))                            # longest along z
        uvs, _sides = T.lay(pts, faces, self.BAND, 8.0)
        side = 5                                                          # the +x face: in the y-z plane
        us = sorted({round(float(u), 6) for u, _v in uvs[side]})
        self.assertEqual(us, [0.0, 0.75])                                 # 6 studs along z
        self.assertTrue(np.allclose(T.longest_axis(pts), (0, 0, 1)))

    def test_where_along_the_band_a_part_begins(self):
        uvs, _ = T.lay(self.pts, self.faces, self.BAND, 8.0, along=(1, 0, 0), start=3.0)
        us = sorted({round(float(u), 6) for u, _v in uvs[0]})
        self.assertEqual(us, [0.375, 1.375])

    def test_a_thin_strip_between_two_sides_takes_a_thin_slice_of_the_band_not_all_of_it(self):
        # a chamfer along the wall's top front edge: the review found every such strip carried the whole band
        pts = np.array([(0, 0, 0), (8, 0, 0), (8, 3.9, 0), (0, 3.9, 0), (0, 4, 0.1), (8, 4, 0.1)], float)
        faces = [(0, 3, 2, 1), (3, 4, 5, 2)]                              # the front, and the strip above it
        uvs, sides = T.lay(pts, faces, self.BAND, 8.0, along=(1, 0, 0))
        strip = uvs[1][:, 1]
        self.assertLess(strip.max() - strip.min(), 0.05)                  # a sliver of the band's 0.5
        self.assertGreater(strip.min(), 0.6)                              # ... near its top, where the strip is

    def test_every_broad_side_is_held_to_the_band_and_a_sliver_is_not(self):
        self.assertIsNone(T.fit_problem("Wall", self.sides, "planks", self.BAND))    # 4 tall on a 4-tall band
        low = {"v0": 0.0, "v1": 0.1, "height": 0.5}
        said = T.fit_problem("Wall", self.sides, "rivets", low)
        self.assertIn("pulled tall 8.0x", said)
        self.assertIn('"rivets"', said)
        # (the wall's narrow top - 1 stud across a 4-stud band - is not judged: under a quarter of its surface)
        pts, faces = box((0, 0, 0), (8, 0.5, 4))                          # a slab: its top IS its broad side
        _uvs, sides = T.lay(pts, faces, self.BAND, 8.0, along=(1, 0, 0))
        self.assertIsNone(T.fit_problem("Slab", sides, "planks", self.BAND))
        self.assertIn("squeezed", T.fit_problem("Slab", sides, "planks", {"v0": 0, "v1": 1, "height": 40.0}))
        sliver = [{"area": 100.0, "across": 4.0, "n": [0, 0, 1]}, {"area": 1.0, "across": 0.05, "n": [0, 1, 0]}]
        self.assertIsNone(T.fit_problem("Wall", sliver, "planks", self.BAND))        # 1% of the surface: not judged

    def test_a_face_with_no_area_gets_the_bands_corner_and_stops_nothing(self):
        pts = np.array([(0, 0, 0), (1, 0, 0), (2, 0, 0)], float)
        uvs, sides = T.lay(pts, [(0, 1, 2)], self.BAND, 8.0, along=(1, 0, 0))
        self.assertEqual(sides, [])
        self.assertTrue(np.allclose(uvs[0], [(0.0, 0.25)] * 3))


class Tiling(unittest.TestCase):
    def test_a_map_that_does_not_repeat_is_measured_and_made_to(self):
        ramp = np.linspace(0.2, 0.8, 256)[None, :, None] * np.ones((32, 1, 3))        # dark on the left, light right
        self.assertGreater(T.tile_step(ramp)["step"], 0.5)
        self.assertEqual(T.tile_step(ramp)["share"], 1.0)
        made = T.tileable_u(ramp)
        self.assertLess(T.tile_step(made)["step"], T.TILE_SEEN)
        self.assertEqual(T.tile_step(made)["share"], 0.0)
        self.assertTrue(np.allclose(made[:, 64:192], ramp[:, 64:192]))                # the middle is not touched
        self.assertEqual(made.shape, ramp.shape)

    def test_a_map_that_already_repeats_reads_as_repeating(self):
        x = np.arange(256) / 256.0
        wave = (0.5 + 0.3 * np.sin(2 * np.pi * 3 * x))[None, :, None] * np.ones((16, 1, 3))
        self.assertLess(T.tile_step(wave)["step"], T.TILE_SEEN)
        # (so the build leaves it alone: tileable_u is for a map that does NOT repeat - it would still repeat
        # after, but with a strip of the finish swapped for another)
        self.assertLess(T.tile_step(T.tileable_u(wave))["step"], T.TILE_SEEN)


class Modules(unittest.TestCase):
    def test_a_wall_of_whole_cells_built_from_a_grid_point_snaps(self):
        self.assertIsNone(T.module_problem((0, 0, 0), (8, 12, 1), (4, 4, 0)))         # 2 x 3 cells, depth left free
        self.assertIsNone(T.module_problem((-4, 0, -4), (4, 8, 4), 4))
        self.assertEqual(T.cells((0, 0, 0), (8, 12, 1), (4, 4, 0)), [2, 3, 0])

    def test_a_size_off_the_grid_and_a_start_off_the_grid_are_each_named(self):
        said = T.module_problem((0, 0, 0), (7.5, 12, 1), (4, 4, 0))
        self.assertIn("7.5 studs along x is 1.88 cells of 4", said)
        said = T.module_problem((1, 0, 0), (9, 12, 1), (4, 4, 0))
        self.assertIn("it starts at x = 1, off the grid of 4", said)
        self.assertIsNotNone(T.module_problem((0, 0, 0), (0.01, 4, 4), 4))            # under one cell
        self.assertIsNone(T.module_problem((0, 0, 0), (8.01, 12, 1), (4, 4, 0)))      # within the tolerance


if __name__ == "__main__":
    unittest.main()
