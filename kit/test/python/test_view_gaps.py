"""kit/blender/rbx_gaps.py: where a view's two silhouettes (the model's, the reference's — both in reference_match's
normalised frame) disagree EDGE TO EDGE, in mm, per 3 x 3 window and per region, with direction words. Synthetic
masks with known gaps."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_gaps as G  # noqa: E402

N = 512


def rect(y0, y1, x0, x1, n=N):
    m = np.zeros((n, n), bool)
    m[y0:y1, x0:x1] = True
    return m


class TestNearest(unittest.TestCase):
    def test_the_distance_is_exact_euclidean(self):
        rng = np.random.default_rng(7)
        feat = rng.random((70, 90)) < 0.01
        ys, xs = rng.integers(0, 70, 300), rng.integers(0, 90, 300)
        d, qy, qx = G.nearest(feat, ys, xs)
        fy, fx = np.nonzero(feat)
        brute = np.sqrt(((ys[:, None] - fy[None]) ** 2 + (xs[:, None] - fx[None]) ** 2).min(1))
        np.testing.assert_allclose(d, brute)
        np.testing.assert_allclose(np.hypot(qy - ys, qx - xs), d)  # the point it names IS that far
        self.assertTrue(feat[qy, qx].all())

    def test_an_edge_is_the_outer_ring(self):
        e = G.edge(rect(10, 20, 10, 30, 40))
        self.assertEqual(int(e.sum()), 2 * 20 + 2 * 8)


class TestEdgeGaps(unittest.TestCase):
    def test_the_same_silhouette_has_no_gap(self):
        m = rect(0, N, 150, 360)
        g, marks = G.edge_gaps(m, m, 0.4, "mm", view="front")
        self.assertEqual(g["worst"], [])
        self.assertEqual(g["max"], 0.0)
        self.assertEqual(marks, [])

    def test_a_front_view_25_percent_too_wide_is_said_where_and_how_much(self):
        # both N tall (the longer side), the reference 200 px wide, the model 250: 25 px too wide on each side
        ref, model = rect(0, N, 156, 356), rect(0, N, 131, 381)
        per_px = 0.4  # mm: the model is 204.8 mm tall, 100 mm wide
        g, marks = G.edge_gaps(model, ref, per_px, "mm", view="front")
        self.assertEqual(g["tolerance"], 4.1)  # 2% of the view's 204.8 mm (> 3 mm)
        self.assertEqual(len(g["worst"]), 2)  # the whole left and the whole right column, each said once
        for w in g["worst"]:
            self.assertIn("too wide at the", w)
            self.assertIn("(top to bottom)", w)
        self.assertTrue(any("left" in w for w in g["worst"]) and any("right" in w for w in g["worst"]))
        self.assertAlmostEqual(g["max"], 25 * per_px, delta=0.5)
        self.assertEqual(len(marks), 2)
        # the windows in the middle column agree
        mid = [w for w in g["windows"] if w["place"] in ("top centre", "centre", "bottom centre")]
        self.assertTrue(all(w["extra"] == 0 and w["missing"] == 0 for w in mid))

    def test_a_dropped_claw_is_the_reference_having_more(self):
        # side view: a 1000 mm body; the reference has a 60 px claw up at the front the model lacks
        body = rect(200, 310, 0, N)
        ref = body.copy()
        ref[150:200, 450:458] = True
        per_px = 1000 / N
        g, _ = G.edge_gaps(body, ref, per_px, "mm", view="side")
        self.assertEqual(len(g["worst"]), 1)
        self.assertIn("the reference has", g["worst"][0])
        self.assertIn("at the top front", g["worst"][0])
        self.assertIn("too short there", g["worst"][0])
        top_front = [w for w in g["windows"] if w["place"] == "top front"][0]
        self.assertAlmostEqual(top_front["missing"], 50 * per_px, delta=2 * per_px)

    def test_a_fin_the_reference_lacks_is_the_model_sticking_out(self):
        ref = rect(200, 310, 0, N)
        model = ref.copy()
        model[310:360, 40:100] = True  # 50 px below the back
        g, _ = G.edge_gaps(model, ref, 1.0, "mm", view="side")
        self.assertTrue(g["worst"][0].startswith("the model is 50 mm too tall at the bottom back"), g["worst"])

    def test_without_a_scale_it_speaks_studs_and_two_percent(self):
        ref, model = rect(0, N, 156, 356), rect(0, N, 131, 381)
        g, _ = G.edge_gaps(model, ref, 2.0 / N, "studs", view="front")
        self.assertEqual(g["unit"], "studs")
        self.assertAlmostEqual(g["tolerance"], 0.04, places=3)  # 2% of 2 studs, no 3 mm floor
        self.assertIn("studs too wide", g["worst"][0])

    def test_a_region_gets_its_own_gap(self):
        body = rect(200, 310, 0, N)
        ref = body.copy()
        ref[150:200, 450:458] = True
        regions = [{"name": "crown", "box": [140, 430, 320, N]}, {"name": "stock", "box": [190, 0, 320, 150]}]
        g, _ = G.edge_gaps(body, ref, 1.0, "mm", view="side", regions=regions)
        rows = {r["region"]: r for r in g["regions"]}
        self.assertFalse(rows["crown"]["ok"])
        self.assertIn("region 'crown'", rows["crown"]["how"][0])
        self.assertTrue(rows["stock"]["ok"])

    def test_the_diff_picture_is_annotated(self):
        ref, model = rect(0, N, 156, 356), rect(0, N, 131, 381)
        g, marks = G.edge_gaps(model, ref, 0.4, "mm", view="front")
        diff = np.zeros((N, N, 4), np.float32)
        G.annotate(diff, marks, box=(0, N, 131, 381))
        yellow = (diff[..., 0] == 1.0) & (diff[..., 1] == np.float32(0.85))
        self.assertGreater(int(yellow.sum()), 1000)  # the two flagged columns framed, the gaps drawn
        self.assertGreater(int((diff[..., 0] == np.float32(0.42)).sum()), 100)  # the 3 x 3 grid


class TestRegionsInFrame(unittest.TestCase):
    def test_a_picture_box_lands_on_the_traced_frame(self):
        # a trace 400 px long in its picture (x0 = 100, the foot at y1 = 300), height 0.25 of its length
        t = {"source": "refs/p.png", "front": "right", "height_ratio": 0.25,
             "frame": {"x0": 100.0, "y1": 300.0, "length_px": 400.0}}
        regs = {"image": "refs/p.png", "regions": [{"name": "front half", "box": [300, 200, 500, 300]}]}
        px = 2048
        # trace_mask(px) fills cols 1 .. 1 + px and rows 1 .. 1 + 512: normalised to n = 1024 it is scaled 0.5
        xf = (1, 1, 0.5, (1024 - 256) // 2, 0)
        boxes, note = G.regions_in_frame(t, regs, xf, px)
        self.assertIsNone(note)
        r0, c0, r1, c1 = boxes[0]["box"]
        self.assertAlmostEqual(c0, 512, delta=2)  # u 0.5 -> half way along
        self.assertAlmostEqual(c1, 1024, delta=2)
        self.assertAlmostEqual(r0, 384, delta=2)  # the top of the trace (h 0.25) -> the top of the content
        self.assertAlmostEqual(r1, 640, delta=2)

    def test_regions_on_another_picture_are_refused(self):
        t = {"source": "refs/a.png", "frame": {"x0": 0, "y1": 0, "length_px": 1}}
        boxes, note = G.regions_in_frame(t, {"image": "refs/b.png", "regions": []}, (0, 0, 1.0, 0, 0))
        self.assertEqual(boxes, [])
        self.assertIn("not one picture", note)


    def test_a_seam_slit_through_one_silhouette_is_not_a_long_gap(self):
        # a 2-pixel seam right through the model (two parts meeting) where the reference is solid: closed first, so
        # it never reads as a gap to the far outline (on the Gjallarhorn a 3 mm seam had read as 100 mm)
        ref = np.zeros((200, 400), bool)
        ref[60:140, 20:380] = True
        model = ref.copy()
        model[99:101, 60:340] = False
        gaps, _ = G.edge_gaps(model, ref, per_px=1.0, unit="mm", view="side")
        self.assertLess(gaps["max"], 3.0)

    def test_an_opening_is_counted_as_an_opening_not_an_outline_gap(self):
        ref = np.zeros((200, 400), bool)
        ref[40:160, 20:380] = True
        model = ref.copy()
        model[80:120, 150:250] = False  # a 40 x 100 pixel window the reference does not have
        gaps, _ = G.edge_gaps(model, ref, per_px=1.0, unit="mm", view="side")
        self.assertLess(gaps["max"], 3.0)  # the outlines agree
        self.assertAlmostEqual(sum(o["extra_area"] for o in gaps["openings"]), 4000.0, delta=50)
        self.assertEqual(sum(o["missing_area"] for o in gaps["openings"]), 0.0)


if __name__ == "__main__":
    unittest.main()
