"""kit/refs/views.py: an asset's traced views tied to one millimetre scale — the side and top views share the
length, the front and back views share the top view's width — so they give one size, CHECK each other, and turn
into cross-section stations and part sizes in mm. Synthetic box traces with known sizes."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "refs"))
import views as V  # noqa: E402


def box(w, h, u0=0.0):
    """a rectangle outline: w long (u), h tall, as a trace stores it (normalised by the view's own length)"""
    return [[u0, 0.0], [u0 + w, 0.0], [u0 + w, h], [u0, h]]


def trace(ratio, front="right", outline=None, parts=None, suspect=False):
    return {"front": front, "height_ratio": ratio, "outline": outline or box(1.0, ratio),
            "parts": parts or {}, "perspective": {"suspect": suspect}}


class TestViews(unittest.TestCase):
    def setUp(self):
        # a 1000 x 200 x 100 mm block: side 1000 x 200, top 1000 x 100, front/back 100 x 200
        self.views = {"side": trace(0.2), "top": trace(0.1), "front": trace(2.0), "back": trace(2.0)}

    def test_views_that_agree_give_one_size(self):
        m = V.measure_views(self.views, 1000, stations=10)
        self.assertEqual(m["size_mm"], [100.0, 200.0, 1000.0])
        self.assertTrue(all(c["grade"] == "ok" for c in m["checks"]))
        self.assertEqual(len(m["checks"]), 3)  # front vs side, back vs side, front vs back

    def test_a_front_view_30_percent_taller_is_called_out(self):
        self.views["front"] = trace(2.6)  # 260 mm tall against the side's 200
        m = V.measure_views(self.views, 1000, stations=10)
        bad = [c for c in m["checks"] if c["grade"] == "bad"]
        self.assertEqual({c["what"] for c in bad}, {"height: front view vs side view", "height: front view vs back view"})
        self.assertEqual(bad[0]["mm"], [260.0, 200.0])

    def test_stations_take_heights_from_the_side_and_widths_from_the_top(self):
        m = V.measure_views(self.views, 1000, stations=4)
        self.assertEqual(len(m["stations"]), 4)
        for s in m["stations"]:
            self.assertAlmostEqual(s["ry_mm"], 100.0)  # half the side's 200 mm
            self.assertAlmostEqual(s["rx_mm"], 50.0)   # half the top's 100 mm

    def test_a_trace_is_already_back_to_front_whichever_side_its_front_was_on(self):
        # a step: the front half is twice as tall. kit trace stores every outline with u = 0 at the back (trace.py
        # turns a picture whose front is on the LEFT), so the views must not turn it again: the front stays tall.
        # (This test used to turn it a second time — the Gjallarhorn's wolf then measured from the wrong end.)
        side = trace(0.4, front="left", outline=[[0, 0], [1, 0], [1, 0.4], [0.5, 0.4], [0.5, 0.2], [0, 0.2]])
        m = V.measure_views({"side": side}, 1000, stations=4)
        rys = [s["ry_mm"] for s in m["stations"]]
        self.assertLess(rys[0], rys[-1])  # back (u = 0) short, front (u = 1) tall
        side["parts"] = {"head": box(0.1, 0.05, u0=0.8)}  # a part near the front: measured from the back
        self.assertEqual(V.measure_views({"side": side}, 1000, stations=4)["parts"]["head"]["side"]["along_mm"],
                         [800.0, 900.0])

    def test_traced_parts_get_their_size_in_mm(self):
        self.views["side"]["parts"] = {"wolf": box(0.1, 0.05, u0=0.8)}
        m = V.measure_views(self.views, 1000, stations=4)
        self.assertEqual(m["parts"]["wolf"]["side"]["size_mm"], [100.0, 50.0])

    def test_no_top_view_takes_the_width_from_the_front_view(self):
        m = V.measure_views({"side": trace(0.2), "front": trace(2.0)}, 1000, stations=4)
        self.assertEqual(m["size_mm"][0], 100.0)

    def test_load_views_reads_the_asset_traces_by_name(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "assets", "models"))
            for suffix, t in (("side", trace(0.2)), ("frontview", trace(2.0)), ("bottom", trace(0.1))):
                with open(os.path.join(d, "assets", "models", f"thing_{suffix}.trace.json"), "w") as fh:
                    json.dump(t, fh)
            got = V.load_views("thing", root=d)
        self.assertEqual(sorted(got), ["front", "side", "top"])


if __name__ == "__main__":
    unittest.main()
