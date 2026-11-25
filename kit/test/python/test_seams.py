"""Does the map meet itself across its seams? (kit/blender/rbx_seams.py; the owner's method lists, 2026-11-13:
"texture seam checks"; the 3D methods audit, G4): the seams found from the mesh, both places of each read from the
map, the step of colour measured."""

import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_seams as S  # noqa: E402

# a strip of two squares (vertices 0..5), folded along the edge 1-4. In the map the left square lies on the left
# half; the right square is laid APART from it, on the right half - so the edge 1-4 is a seam.
#   3 - 4 - 5
#   | / | / |
#   0 - 1 - 2
TV = np.array([(0, 1, 4), (0, 4, 3), (1, 2, 5), (1, 5, 4)])
LEFT = {0: (0.1, 0.1), 1: (0.4, 0.1), 4: (0.4, 0.9), 3: (0.1, 0.9)}
RIGHT = {1: (0.6, 0.1), 2: (0.9, 0.1), 5: (0.9, 0.9), 4: (0.6, 0.9)}
UV = np.array([[LEFT[v] for v in TV[0]], [LEFT[v] for v in TV[1]],
               [RIGHT[v] for v in TV[2]], [RIGHT[v] for v in TV[3]]], float)
JOINED = np.array([[LEFT[v] for v in TV[0]], [LEFT[v] for v in TV[1]],
                   [{1: (0.4, 0.1), 2: (0.7, 0.1), 5: (0.7, 0.9), 4: (0.4, 0.9)}[v] for v in TV[2]],
                   [{1: (0.4, 0.1), 2: (0.7, 0.1), 5: (0.7, 0.9), 4: (0.4, 0.9)}[v] for v in TV[3]]], float)


def flat(colour, n=64):
    return np.tile(np.asarray(colour, float), (n, n, 1))


class Seams(unittest.TestCase):
    def test_the_edge_laid_in_two_places_is_the_seam_and_the_diagonals_are_not(self):
        s = S.seam_edges(TV, UV)
        self.assertEqual(s["verts"].tolist(), [[1, 4]])
        self.assertTrue(np.allclose(s["a"][0, :2], [(0.4, 0.1), (0.4, 0.9)]))    # the edge on the left island
        self.assertTrue(np.allclose(s["b"][0, :2], [(0.6, 0.1), (0.6, 0.9)]))    # ... on the right island
        self.assertTrue(np.allclose(s["a"][0, 2], (0.1, 0.1)) or np.allclose(s["a"][0, 2], (0.1, 0.9)))

    def test_a_strip_laid_in_one_piece_has_no_seam(self):
        self.assertEqual(len(S.seam_edges(TV, JOINED)["a"]), 0)
        self.assertEqual(S.measure(flat((0.5, 0.5, 0.5)), S.seam_edges(TV, JOINED))["edges"], 0)

    def test_an_edge_of_one_triangle_only_is_a_border_not_a_seam(self):
        self.assertEqual(len(S.seam_edges(TV[:2], UV[:2])["a"]), 0)


class Reading(unittest.TestCase):
    def test_the_map_is_read_between_its_texels(self):
        img = np.zeros((2, 2, 3))
        img[0, 1] = 1.0                                                   # the texel at u 0.75, v 0.25
        got = S.read(img, np.array([(0.75, 0.25), (0.5, 0.25), (0.25, 0.75)]))
        self.assertTrue(np.allclose(got[:, 0], [1.0, 0.5, 0.0]))


class Measure(unittest.TestCase):
    def test_one_colour_on_both_sides_shows_no_step(self):
        m = S.measure(flat((0.3, 0.5, 0.7)), S.seam_edges(TV, UV))
        self.assertEqual((m["edges"], m["seen_px"], m["share"], m["worst"]), (1, 0.0, 0.0, []))
        self.assertAlmostEqual(m["length_px"], 0.8 * 64, delta=0.5)

    def test_two_colours_show_the_whole_seam_and_name_its_edge(self):
        img = flat((0.3, 0.3, 0.3))
        img[:, 32:] = (0.5, 0.3, 0.3)                                     # the right island a step redder
        m = S.measure(img, S.seam_edges(TV, UV))
        self.assertAlmostEqual(m["share"], 1.0)
        self.assertAlmostEqual(m["p95"], 0.2, places=3)
        self.assertEqual(m["worst"], [(1, 4, 0.2)])

    def test_a_step_too_small_to_see_is_not_counted(self):
        img = flat((0.3, 0.3, 0.3))
        img[:, 32:] = (0.3 + 6 / 255, 0.3, 0.3)
        self.assertEqual(S.measure(img, S.seam_edges(TV, UV))["share"], 0.0)

    def test_a_margin_that_did_not_reach_on_half_an_edge_shows_on_that_half(self):
        # the left island's colour stops short of its edge on the lower half: black shows through there. The edge
        # is judged window by window: the lower windows show the step, the upper ones none
        img = flat((0.6, 0.6, 0.6))
        img[:32, 24:27] = 0.0                                             # u 0.375 .. 0.42, v under 0.5
        m = S.measure(img, S.seam_edges(TV, UV))
        self.assertAlmostEqual(m["share"], 0.5, delta=0.2)
        self.assertGreater(m["worst"][0][2], 0.3)

    def test_a_step_that_turns_over_along_the_edge_does_not_cancel(self):
        # the review's find: redder below, bluer above - the mean along the whole edge was zero
        img = flat((0.5, 0.5, 0.5))
        img[:32, 32:] = (0.7, 0.5, 0.5)
        img[32:, 32:] = (0.3, 0.5, 0.5)
        # (three windows on this edge: the two ends show it, the middle one straddles the turn)
        self.assertGreater(S.measure(img, S.seam_edges(TV, UV))["share"], 0.6)

    def test_a_short_bright_line_on_a_long_edge_is_seen(self):
        img = flat((0.3, 0.3, 0.3), n=512)
        img[200:240, 256:] = 1.0                                          # 40 texels of a 410-texel edge
        m = S.measure(img, S.seam_edges(TV, UV))
        self.assertAlmostEqual(m["share"], 40 / 410, delta=0.07)
        self.assertEqual(m["floor"], 0.0)

    def test_a_colour_that_runs_on_through_the_seam_is_the_texture_not_a_seam(self):
        # the review's null test: the surface darkens steadily toward the seam on one island and goes on darkening
        # on the other - side against side that is a step of 0.075; the seam itself adds nothing
        n, k = 256, 0.05 / 4                                              # 0.0125 a texel (texels 4x finer here)
        img = np.zeros((n, n, 3))
        cols = np.arange(n) + 0.5
        left = 0.5 - k * (0.4 * n - cols)                                 # falls toward its edge at u 0.4 ...
        right = 0.5 + k * (cols - 0.6 * n)                                # ... and goes on from the edge at u 0.6
        img[:, : n // 2] = left[: n // 2, None][None].repeat(n, 0)
        img[:, n // 2:] = right[n // 2:, None][None].repeat(n, 0)
        self.assertEqual(S.measure(img, S.seam_edges(TV, UV))["share"], 0.0)
        img[:, n // 2:] += 0.2                                            # the same run, with a real step on top
        self.assertEqual(S.measure(img, S.seam_edges(TV, UV))["share"], 1.0)

    def test_the_first_reading_sits_inside_the_island_never_on_the_line(self):
        # only the LEFT island's margin is dark (beyond its edge at u 0.4): read inside, nothing shows; read on
        # the line itself, the margin bleeds into the reading
        img = flat((0.5, 0.5, 0.5))
        img[:, 26:31] = 0.0                                               # u 0.406 .. 0.484: the gap, left part
        seams = S.seam_edges(TV, UV)
        self.assertEqual(S.measure(img, seams)["share"], 0.0)
        self.assertGreater(S.measure(img, seams, inset=0.0)["share"], 0.5)

    def test_what_was_not_judged_is_counted(self):
        seams = S.seam_edges(TV, UV)
        m = S.measure(flat((0.5, 0.5, 0.5)), seams, np.array([False]))
        self.assertEqual((m["edges"], m["length_px"]), (0, 0.0))
        self.assertAlmostEqual(m["of_px"], 0.8 * 64, delta=0.5)
        self.assertEqual(seams["crowded"], 0)
        fin = np.vstack([TV, [(1, 4, 0)]])                                # a third triangle on the edge 1-4
        self.assertEqual(S.seam_edges(fin, np.vstack([UV, UV[:1]]))["crowded"], 2)

    def test_a_map_wider_than_tall_is_read_in_its_own_texels(self):
        img = np.tile(np.array([0.3, 0.3, 0.3]), (32, 128, 1))
        img[:, 64:] = (0.5, 0.3, 0.3)
        m = S.measure(img, S.seam_edges(TV, UV))
        self.assertAlmostEqual(m["length_px"], 0.8 * 32, delta=0.5)       # the edge runs up the map: its HEIGHT
        self.assertEqual(m["share"], 1.0)

    def test_grain_that_differs_texel_to_texel_is_not_a_seam(self):
        # both islands carry the same fine grain, their texels not lined up: texel against texel differs, the
        # mean along the edge does not
        rng = np.random.default_rng(3)
        img = 0.5 + (rng.random((256, 256, 1)) - 0.5) * 0.1 * np.ones((1, 1, 3))
        m = S.measure(img, S.seam_edges(TV, UV))
        self.assertLessEqual(m["share"], 0.1)
        # ... and a HARSH grain shows as much inside an island as across the seam: nothing beyond the floor
        img = 0.5 + (rng.random((256, 256, 1)) - 0.5) * 0.5 * np.ones((1, 1, 3))
        m = S.measure(img, S.seam_edges(TV, UV))
        self.assertGreater(m["floor"], 0.2)
        self.assertLessEqual(m["beyond"], 0.2)
        img[:, 128:] += 0.2                                               # a real step under the same grain
        self.assertGreater(S.measure(img, S.seam_edges(TV, UV))["beyond"], 0.3)

    def test_a_seam_on_a_sharp_edge_is_not_judged_and_a_short_edge_neither(self):
        seams = S.seam_edges(TV, UV)
        flat_strip = np.array([[(0, 0, 0), (1, 0, 0), (1, 1, 0)], [(0, 0, 0), (1, 1, 0), (0, 1, 0)],
                               [(1, 0, 0), (2, 0, 0), (2, 1, 0)], [(1, 0, 0), (2, 1, 0), (1, 1, 0)]], float)
        folded = flat_strip.copy()
        folded[2:, :, 2] = folded[2:, :, 0] - 1.0                         # the right square turned down 45 degrees
        self.assertEqual(S.smooth(seams, flat_strip).tolist(), [True])
        turned = flat_strip.copy()                                        # exactly 30 degrees: a 12-sided cylinder
        ang = np.radians(30.0)
        x = turned[2:, :, 0] - 1.0
        turned[2:, :, 0], turned[2:, :, 2] = 1.0 + x * np.cos(ang), -x * np.sin(ang)
        self.assertEqual(S.smooth(seams, turned).tolist(), [True])
        self.assertEqual(S.smooth(seams, folded).tolist(), [False])
        img = flat((0.3, 0.3, 0.3))
        img[:, 32:] = (0.6, 0.3, 0.3)
        self.assertEqual(S.measure(img, seams, S.smooth(seams, folded))["edges"], 0)
        self.assertEqual(S.measure(img, seams, S.smooth(seams, flat_strip))["share"], 1.0)
        tiny = flat((0.3, 0.3, 0.3), n=2)                                 # the edge is 1.6 texels long here
        self.assertEqual(S.measure(tiny, seams)["edges"], 0)

    def test_the_reading_is_taken_inside_each_island_not_on_the_line(self):
        # each island is its own colour right up to its edge, the gap between them is black: no step is read
        # from the gap
        img = np.zeros((64, 64, 3))
        img[:, :26] = 0.5                                                 # the left island, to u 0.406
        img[:, 38:] = 0.5                                                 # the right island, from u 0.594
        self.assertEqual(S.measure(img, S.seam_edges(TV, UV))["share"], 0.0)


if __name__ == "__main__":
    unittest.main()
