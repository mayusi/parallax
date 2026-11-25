"""kit/refs/rectify.py — a photo's trace laid onto a calibrated outline of the same view: a known perspective (the
camera a little below and in front) put onto a pistol-like outline with a hole and a traced part is found and taken out
again; a wrong pairing (another shape) is refused, not forced."""

import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "refs"))
import rectify as R  # noqa: E402

# a pistol-ish side outline (u 0..1 back to front, v up): grip at the back, slide over it, a guard opening (hole)
OUTLINE = [[0.0, 0.05], [0.16, 0.0], [0.30, 0.0], [0.36, 0.38], [0.62, 0.38], [0.64, 0.46], [1.0, 0.46], [1.0, 0.68],
           [0.06, 0.68], [0.04, 0.50]]
HOLE = [[0.40, 0.40], [0.56, 0.40], [0.56, 0.45], [0.40, 0.45]]
PART = [[0.70, 0.47], [0.86, 0.47], [0.86, 0.55], [0.70, 0.55]]
H0 = np.array([[0.985, 0.012, 0.004], [-0.008, 1.03, -0.006], [0.025, -0.04, 1.0]])   # a mild perspective


def trace(outline, holes, parts):
    pts = np.asarray(outline, float)
    u0, v0, s = pts[:, 0].min(), pts[:, 1].min(), np.ptp(pts[:, 0])

    def norm(r):
        return [[round((u - u0) / s, 6), round((v - v0) / s, 6)] for u, v in r]
    return {"name": "x", "outline": norm(outline), "holes": [norm(h) for h in holes],
            "parts": {k: norm(v) for k, v in parts.items()}, "height_ratio": round(np.ptp(pts[:, 1]) / s, 6),
            "frame": {"x0": 0, "y1": 0, "length_px": 1}}


class TestRectify(unittest.TestCase):
    def setUp(self):
        self.ref = trace(OUTLINE, [HOLE], {"slide": PART})
        inv = np.linalg.inv(H0)
        self.photo = trace(R.apply(inv, OUTLINE).tolist(), [R.apply(inv, HOLE).tolist()],
                           {"slide": R.apply(inv, PART).tolist()})

    def test_a_known_perspective_is_found_and_taken_out_of_every_part(self):
        t, rep = R.rectify(self.photo, self.ref)
        self.assertLess(rep["iou_before"], 0.97)
        self.assertGreater(rep["iou_after"], 0.995)
        got = np.asarray(t["parts"]["slide"])
        want = np.asarray(self.ref["parts"]["slide"])
        self.assertLess(float(np.abs(got - want).max()), 0.002)   # (the part lands where the reference has it)
        self.assertAlmostEqual(t["height_ratio"], self.ref["height_ratio"], delta=0.003)
        self.assertNotIn("frame", t)   # (the picture no longer maps onto it by a frame)

    def test_the_command_writes_the_rectified_trace_and_refuses_a_wrong_pairing(self):
        tmp = tempfile.mkdtemp()
        old = R.ROOT
        try:
            R.ROOT = tmp
            os.makedirs(os.path.join(tmp, "assets", "models"))
            for name, t in (("p", self.photo), ("r", self.ref)):
                with open(os.path.join(tmp, "assets", "models", f"{name}.trace.json"), "w") as fh:
                    json.dump(t, fh)
            import contextlib
            import io

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = R.main(["p", "--to", "r"])
            self.assertEqual(code, 0, out.getvalue())
            with open(os.path.join(tmp, "assets", "models", "p_rect.trace.json")) as fh:
                t = json.load(fh)
            self.assertEqual(t["rectified"]["to"], "assets/models/r.trace.json")
            # another object entirely (a long bar): no perspective maps one onto the other
            bar = trace([[0, 0], [1, 0], [1, 0.1], [0, 0.1]], [], {})
            with open(os.path.join(tmp, "assets", "models", "bar.trace.json"), "w") as fh:
                json.dump(bar, fh)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = R.main(["p", "--to", "bar"])
            self.assertEqual(code, 1, out.getvalue())
        finally:
            R.ROOT = old
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
