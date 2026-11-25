"""rbx_formmatch — the form-match teacher's plain numpy: the reference placed as a.import_mesh places it, the regions
named the model's way, the report's worst regions and hot spots (the BVH distance queries run in Blender builds)."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_formmatch as F  # noqa: E402


class Place(unittest.TestCase):
    def test_scaled_to_height_base_on_the_ground_centred(self):
        v = np.array([[0, 10, 0], [4, 30, 2], [2, 20, 6]], dtype=float)
        p = F.place(v, height=1.0)
        self.assertAlmostEqual(p[:, 1].min(), 0.0)
        self.assertAlmostEqual(p[:, 1].max(), 1.0)
        self.assertAlmostEqual(p[:, 0].min() + p[:, 0].max(), 0.0)
        self.assertAlmostEqual(p[:, 2].min() + p[:, 2].max(), 0.0)

    def test_turned_like_import_mesh(self):
        v = np.array([[0, 0, 1.0], [0, 1.0, 1.0], [0, 0, 0]])
        p = F.place(v, height=1.0, rot=(0, 180, 0))   # (a half turn about y: +z to -z)
        self.assertAlmostEqual(float(p[np.argmax(v[:, 2]), 2]), -0.5)


class Regions(unittest.TestCase):
    def test_named_the_models_way(self):
        lo, hi = np.zeros(3), np.ones(3) * 3
        r = F.region_of(np.array([[2.5, 0.5, 0.5], [0.5, 2.5, 2.5], [1.5, 1.5, 1.5]]), lo, hi)
        self.assertEqual([F.region_name(int(x)) for x in r],
                         ["front-low-right", "back-high-left", "middle-mid-centre"])


class Report(unittest.TestCase):
    def test_the_worst_regions_by_how_much_and_how_wide(self):
        extra = np.array([0.1, 0.2, 6.0, 6.0, 0.0])
        ereg = np.array([0, 0, 13, 13, 0])
        missing = np.array([2.0, 0.0, 0.0])
        mreg = np.array([4, 4, 4])
        rep = F.summary(extra, ereg, missing, mreg)
        self.assertEqual(rep["worst"][0]["region"], F.region_name(13))
        self.assertEqual(rep["worst"][0]["kind"], "extra")
        self.assertAlmostEqual(rep["worst"][0]["mean_mm"], 6.0)
        self.assertEqual({w["kind"] for w in rep["worst"]}, {"extra", "missing"})

    def test_hot_spots_cluster_where_the_clay_must_move(self):
        rng = np.random.default_rng(1)
        a = rng.normal((40, 110, -70), 2, (50, 3))     # a tight cluster 8 mm off
        b = rng.normal((-60, 90, 10), 2, (10, 3))      # a smaller one 5 mm off
        c = rng.normal((0, 0, 0), 30, (200, 3))        # the rest, on the surface
        pts = np.concatenate([a, b, c])
        gaps = np.concatenate([np.full(50, 8.0), np.full(10, 5.0), np.full(200, 0.2)])
        spots = F.hot_spots(pts, gaps)
        self.assertGreaterEqual(len(spots), 2)
        self.assertLess(np.linalg.norm(np.array(spots[0]["at"]) - (40, 110, -70)), 6)
        self.assertEqual(F.hot_spots(pts, np.zeros(len(pts))), [])


class Midline(unittest.TestCase):
    @staticmethod
    def face(open_lo, open_hi):
        """a face's midline points: the front at z -90, a nose OPENING (its front 15 mm deeper) between two heights"""
        pts = [(x, y + 0.5, -75.0 if open_lo <= y < open_hi else -90.0) for y in range(0, 140) for x in (-2.0, 2.0)]
        return pts + [(30.0, 50.0, -120.0)]   # (a point off the midline: never read)

    def test_the_profile_reads_the_front_along_the_midline(self):
        prof = F.midline_profile(self.face(81, 102))
        self.assertEqual(prof[48.0], -90.0)
        self.assertEqual(prof[90.0], -75.0)

    def test_a_landmark_too_high_is_named_with_its_heights(self):
        ref = F.midline_profile(self.face(81, 102))
        build = F.midline_profile(self.face(76, 108))          # (the opening too tall: 5 below, 6 above)
        gaps = F.profile_gaps(ref, build)
        self.assertEqual({g["y"] for g in gaps}, {(78.0, 81.0), (102.0, 108.0)})   # (3 mm bands: 75-78 still holds a closed point)
        self.assertTrue(all(g["mm"] == 15.0 for g in gaps))
        self.assertIn("BEHIND", gaps[0]["words"])
        self.assertEqual(F.profile_gaps(ref, ref), [])


class Crisp(unittest.TestCase):
    @staticmethod
    def cube():
        """a 40 mm cube's surface: points on its faces and the faces' own normals (sharp edges)"""
        rng = np.random.default_rng(0)
        axis, sign = rng.integers(0, 3, 30000), rng.choice([-1.0, 1.0], 30000)
        p = rng.uniform(-20, 20, (30000, 3))
        p[np.arange(30000), axis] = sign * 20
        n = np.zeros((30000, 3))
        n[np.arange(30000), axis] = sign
        return p, n

    @staticmethod
    def sphere():
        """a sphere 20 mm across its radius: no edge anywhere (a melted form)"""
        rng = np.random.default_rng(1)
        n = rng.normal(size=(30000, 3))
        n /= np.linalg.norm(n, axis=1, keepdims=True)
        return n * 20, n

    def test_sharp_edges_fold_a_melted_form_does_not(self):
        sharp, melted = F.crispness(*self.cube()), F.crispness(*self.sphere())
        self.assertGreater(sharp["fold_share"], 0.1)    # (the band along its 12 edges)
        self.assertLess(sharp["fold_share"], 0.4)
        self.assertLess(melted["fold_share"], 0.02)
        self.assertIn("SOFT", F.crisp_words(melted, sharp))
        self.assertEqual(F.crisp_words(sharp, sharp), "")

    def test_surface_samples_lie_on_the_mesh_with_its_normals(self):
        v = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype=float)
        p, n = F.surface_samples(v, np.array([[0, 1, 2]]), n=500)
        self.assertTrue(np.allclose(p[:, 2], 0.0))
        self.assertTrue((p[:, 0] + p[:, 1] <= 10.0 + 1e-9).all())
        self.assertTrue(np.allclose(np.abs(n[:, 2]), 1.0))


class Sections(unittest.TestCase):
    def test_a_reference_slice_in_pieces_is_named_not_compared(self):
        # a real skull's levels (kit refs measure): through the teeth its biggest island is a fragment
        lv = [{"h": h, "width_mm": w, "depth_mm": d} for h, w, d in (
            (0.1, 88.9, 68.8), (0.15, 100.5, 85.7), (0.2, 26.2, 46.6), (0.25, 18.5, 36.3), (0.3, 69.2, 55.7),
            (0.35, 66.7, 57.0), (0.4, 124.7, 83.0))]
        out = F.fragment_levels(lv)
        self.assertEqual(sorted(out), [0.2, 0.25])
        self.assertIn("100.5 x 85.7", out[0.2])
        self.assertIn("in pieces", out[0.2])
        # a grip that narrows smoothly is never a fragment; the ends (one side only) are never judged
        grip = [{"h": h / 10, "width_mm": 30 - h, "depth_mm": 50 - 2 * h} for h in range(1, 9)]
        self.assertEqual(F.fragment_levels(grip), {})


if __name__ == "__main__":
    unittest.main()
