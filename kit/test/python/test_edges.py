"""kit refs edges (kit/refs/edges.py) — how round every edge is, measured: a sharp step reads ~1 px, a ramp its 10-90%
width; wider ramps read rounder radii; a picture's edges split into sharp / soft / round shares; the Blender
calibration (kit/tools/edge_calibrate.py -> kit/refs/edges_cal.json) orders 0..4 mm rounds right and is within its
stated error (pure: no Blender here)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "refs"))
import edges as E  # noqa: E402


def step_image(ramp, size=200):
    x = np.arange(size, dtype=np.float32)
    if ramp <= 0:
        row = np.where(x >= size / 2, 200.0, 40.0)
    else:
        row = np.clip((x - size / 2) / ramp + 0.5, 0, 1) * 160 + 40
    return np.tile(row, (120, 1)).astype(np.uint8)


class Widths(unittest.TestCase):
    def test_a_step_is_narrow_and_a_ramp_its_width(self):
        got = {}
        for ramp in (0, 4, 8, 16):
            w, _m = E.edge_widths(step_image(ramp))
            v = w[~np.isnan(w)]
            self.assertGreater(len(v), 5, ramp)
            got[ramp] = float(np.median(v))
        self.assertLess(got[0], 1.5)
        for ramp in (4, 8, 16):                              # (a linear ramp's 10-90% rise: 0.8 of it)
            self.assertAlmostEqual(got[ramp], 0.8 * ramp, delta=0.25 * ramp)
        self.assertLess(got[4], got[8])
        self.assertLess(got[8], got[16])

    def test_radius_grows_with_width_and_shares_add_up(self):
        self.assertLess(E.radius_mm(2, 0.1), E.radius_mm(10, 0.1))
        w, m = E.edge_widths(step_image(8))
        s = E.summarise(w, np.ones(w.shape, bool), 0.15)
        self.assertAlmostEqual(s["sharp"] + s["soft"] + s["round"], 1.0, places=1)


class Calibration(unittest.TestCase):
    def test_the_blender_calibration_orders_the_rounds(self):
        path = os.path.join(HERE, "..", "..", "refs", "edges_cal.json")
        if not os.path.isfile(path):
            self.skipTest("kit/refs/edges_cal.json not made (python kit/tools/edge_calibrate.py)")
        cal = json.load(open(path))
        self.assertLessEqual(cal["err_mm"], 1.0)
        for scale in {p["mm_per_px"] for p in cal["points"]}:
            pts = sorted((p for p in cal["points"] if p["mm_per_px"] == scale and p["width_mm"]),
                         key=lambda p: p["round_mm"])
            ws = [p["width_mm"] for p in pts]
            self.assertLess(ws[0], ws[-1])                  # (0 mm reads narrower than 4 mm at every scale)
            self.assertGreaterEqual(sum(b >= a for a, b in zip(ws, ws[1:])), len(ws) - 2)


class Cli(unittest.TestCase):
    def test_refs_edges_writes_the_parts_and_a_heat_map(self):
        from PIL import Image  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as t:
            pic = os.path.join(t, "pic.png")
            im = np.full((200, 300), 20, np.uint8)
            im[50:150, 40:140] = 210                          # (a sharp-edged square ...)
            import cv2  # noqa: PLC0415

            soft = np.full((200, 300), 20, np.uint8)
            soft[50:150, 170:270] = 210
            soft = cv2.GaussianBlur(soft, (0, 0), 4)          # (... and a soft one)
            im[:, 160:] = soft[:, 160:]
            Image.fromarray(im).save(pic)
            parts = os.path.join(t, "parts.json")
            mpp = 0.1
            with open(parts, "w") as fh:  # (part outlines in mm: x from the left, y up from the bottom)
                json.dump({"parts": {"sharp": [[4, 5], [14, 5], [14, 15], [4, 15]],
                                     "soft": [[17, 5], [27, 5], [27, 15], [17, 15]]}}, fh)
            out = os.path.join(t, "x.edges.json")
            p = subprocess.run([sys.executable, os.path.join(HERE, "..", "..", "refs", "edges.py"), pic, "--name", "x",
                                "--mm-per-px", str(mpp), "--parts", parts, "--out", out], capture_output=True,
                               text=True, env={**os.environ, "KIT_BUILD": t})
            res = json.loads(p.stdout.strip().splitlines()[-1])
            self.assertEqual(res["status"], "pass", p.stdout + p.stderr)
            d = json.load(open(out))["parts"]
            self.assertLess(d["sharp"]["radius_mm"], d["soft"]["radius_mm"])
            self.assertTrue(os.path.isfile(os.path.join(t, "refs", "x_edges.png")))


if __name__ == "__main__":
    unittest.main()
