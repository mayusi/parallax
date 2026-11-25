"""kit/refs/hull.py — a turntable's photos carved into a measured visual hull: the camera found from the photos alone
(distance, elevations, aim, which way it turns), the size from the published length, the height and widths measured.
A synthetic pistol-like block (a 200 x 30 x 25 mm slide over a 30 x 100 x 28 mm grip) photographed by a known camera
is recovered without being told the camera. Small pictures and coarse voxels: seconds, no GPU."""

import json
import math
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "refs"))
import hull as H  # noqa: E402


def solid(step=1.0):
    """the synthetic object's points (mm): the slide on top, the grip under its rear; front at +x"""
    xs = np.arange(-100, 100, step)
    pts = []
    for x in xs:
        for y in np.arange(20, 50, step):          # slide: 200 long, 30 high, 25 wide
            for z in np.arange(-12.5, 12.5, step):
                pts.append((x, y, z))
    for x in np.arange(-100, -70, step):          # grip: 30 long, 100 high, 28 wide
        for y in np.arange(-80, 20, step):
            for z in np.arange(-14, 14, step):
                pts.append((x, y, z))
    return np.array(pts, dtype=np.float32)


def photograph(folder, rig, pts, cols, rows, front_left=False):
    os.makedirs(folder, exist_ok=True)
    P = pts.copy()
    if front_left:
        P[:, 0] *= -1  # (the front at -x: in the side photo it points left)
        P[:, 2] *= -1
    from scipy import ndimage

    for r in range(rows):
        for c in range(cols):
            u, v = rig.project(P, r, c)
            m = np.zeros((int(rig.h), int(rig.w)), dtype=bool)
            ok = (u >= 0) & (u < rig.w) & (v >= 0) & (v < rig.h)
            m[np.round(v[ok]).astype(int).clip(0, int(rig.h) - 1), np.round(u[ok]).astype(int).clip(0, int(rig.w) - 1)] = True
            m = ndimage.binary_closing(m, iterations=2)
            img = np.where(m, 30, 250).astype(np.uint8)
            Image.fromarray(np.stack([img] * 3, -1)).save(os.path.join(folder, f"c{r * cols + c:03d}.png"))


class TestHull(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kit_hull_")
        cls.pts = solid(1.5)
        cls.runs = {}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def recover(self, turn, front_left, name):
        if name in self.runs:  # (one reconstruction serves every test that reads it)
            return self.runs[name]
        cols, rows = 12, 3
        true = H.Rig(360, 330, cols, rows, side_col=3, k=1.3, D=900.0, elev=[2.0, 18.0, 38.0], du=6.0,
                     dv=[-4.0, -2.0, 3.0], turn=turn)
        folder = os.path.join(self.tmp, name)
        photograph(folder, true, self.pts, cols, rows, front_left)
        rec = H.run(folder, 200.0, name, cols=cols, rows=rows, pattern="c{i:03d}.png", side_col=3,
                    front="left" if front_left else "right", voxel=2.0, out=os.path.join(self.tmp, "out"),
                    views_out=os.path.join(self.tmp, "views"), ortho_px=2.0, calib_scale=0.6, calib_every=1,
                    maxfev=80, log=lambda s: None)
        self.runs[name] = (rec, true)
        return rec, true

    def test_the_camera_and_the_size_come_from_the_photos(self):
        rec, true = self.recover(360.0 / 12, False, "fwd")
        w, h, l_ = rec["size_mm"]
        self.assertAlmostEqual(l_, 200.0, delta=0.5)        # (pinned to the published length)
        self.assertAlmostEqual(h, 130.0, delta=130 * 0.04)  # measured: 30 slide + 100 grip
        self.assertAlmostEqual(w, 28.0, delta=28 * 0.12)    # measured: the grip's 28
        self.assertGreater(rec["coverage"]["mean"], 0.95)
        self.assertEqual(math.copysign(1, rec["camera"]["turn_deg"]), 1.0)
        el = rec["camera"]["elevation_deg"]
        self.assertTrue(el[0] < el[1] < el[2], el)

    def test_a_turntable_turning_the_other_way_is_found(self):
        rec, _ = self.recover(-360.0 / 12, True, "rev")
        self.assertEqual(math.copysign(1, rec["camera"]["turn_deg"]), -1.0)
        self.assertGreater(rec["coverage"]["mean"], 0.95)
        self.assertAlmostEqual(rec["size_mm"][1], 130.0, delta=130 * 0.05)

    def test_the_outputs_are_a_mesh_and_square_views_front_right(self):
        rec, _ = self.recover(-360.0 / 12, True, "rev")
        with open(rec["obj"]) as fh:
            text = fh.read()
        self.assertGreater(text.count("\nv "), 8)
        self.assertGreater(text.count("\nf "), 6)
        side = np.asarray(Image.open(rec["views"]["side"]).convert("L")) < 128
        ys, xs = np.nonzero(side)
        mid = (xs.min() + xs.max()) / 2
        grip = side[:, xs.min():int(mid)].sum(0).max(), side[:, int(mid):xs.max()].sum(0).max()
        self.assertGreater(grip[0], grip[1])  # (the grip hangs at the REAR: the left half; the front points right)
        top = np.asarray(Image.open(rec["views"]["top"]).convert("L")) < 128
        self.assertGreater(top.sum(), 0)
        with open(rec["path"]) as fh:
            self.assertEqual(json.load(fh)["size_mm"], rec["size_mm"])

    def test_too_few_photos_are_said(self):
        folder = os.path.join(self.tmp, "empty")
        os.makedirs(folder, exist_ok=True)
        with self.assertRaises(ValueError):
            H.run(folder, 200.0, "none", cols=12, rows=3, pattern="c{i:03d}.png", log=lambda s: None)



def with_sights(step=1.0):
    """the same block with two 4 mm sights on the slide's top, 180 mm apart (the gap a coarse camera fills)"""
    pts = [solid(step)]
    for x0 in (-92.0, 86.0):
        g = np.mgrid[x0:x0 + 6:step, 50:54:step, -2:2:step].reshape(3, -1).T
        pts.append(g.astype(np.float32))
    return np.concatenate(pts)


class TestThinFeatures(unittest.TestCase):
    """a tilted tripod (roll) and a turntable whose zero is off by 3 degrees: the hull comes out straight, and the
    4 mm sights stand above a carved slide top (GLOCK's FS turntable gave a flat top at sight height before the fine
    calibration)"""

    def test_sights_are_carved_apart_and_the_hull_is_straight(self):
        tmp = tempfile.mkdtemp(prefix="kit_hull_sights_")
        try:
            true = H.Rig(420, 340, 12, 3, side_col=3, k=1.6, D=900.0, elev=[2.0, 18.0, 38.0], du=4.0,
                         dv=[-6.0, -2.0, 4.0], turn=30.0, a0=3.0, roll=0.8)
            folder = os.path.join(tmp, "p")
            photograph(folder, true, with_sights(1.0), 12, 3)
            rec = H.run(folder, 200.0, "sights", cols=12, rows=3, pattern="c{i:03d}.png", side_col=3, front="right",
                        voxel=1.0, out=os.path.join(tmp, "o"), views_out=os.path.join(tmp, "v"), ortho_px=4.0,
                        calib_scale=0.6, calib_every=1, maxfev=80, log=lambda s: None)
            side = np.asarray(Image.open(rec["views"]["side"]).convert("L")) < 128
            cols = np.nonzero(side.any(0))[0]
            top = np.array([np.nonzero(side[:, c])[0].min() for c in cols])
            px = 4.0
            mid = top[len(top) // 3: 2 * len(top) // 3]
            self.assertGreater((mid.min() - top.min()) / px, 2.5)  # (the slide's top sits below the sights)
            topv = np.asarray(Image.open(rec["views"]["top"]).convert("L")) < 128
            tcols = np.nonzero(topv.any(0))[0]
            w = topv.sum(0)[tcols] / px
            # (a visual hull only ever errs WIDE: no photo sees the slide's 25 mm alone — the end views see the 28 mm
            #  grip behind it — so the slide's width is an upper bound, never under the truth)
            slide = float(np.median(w[len(w) // 2: -len(w) // 10]))
            self.assertGreaterEqual(slide, 24.0)
            self.assertLessEqual(slide, 29.5)
            centre = [np.nonzero(topv[:, c])[0].mean() for c in tcols[len(tcols) // 10: -len(tcols) // 10]]
            self.assertLess((max(centre) - min(centre)) / px, 2.0)  # (straight: the centre line drifts < 2 voxels)
            self.assertLess(abs(rec["camera"]["roll_deg"] - 0.8), 0.4)
            self.assertAlmostEqual(rec["size_mm"][0], 28.0, delta=2.0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)



class TestHandedness(unittest.TestCase):
    """the OBJ was MIRRORED (2026-10-08 review): a bump on the object's LEFT side must come out on its left — at -z in a
    right-handed OBJ (front +x, up +y, right +z) and at the top of the top view (front to the right). In the side
    photo the front points right, so the camera sees the RIGHT side and the photo's depth (+z) runs to the left"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kit_hull_hand_")
        pts = [p for p in solid(1.5) if p[1] >= 20]  # (the slide alone: no grip)
        for x in np.arange(-10, 30, 1.5):              # the bump: 40 long, 12 high, 8 out on the LEFT (+z here)
            for y in np.arange(26, 38, 1.5):
                for z in np.arange(12.5, 20.5, 1.5):
                    pts.append((x, y, z))
        cols, rows = 12, 3
        rig = H.Rig(360, 330, cols, rows, side_col=3, k=1.3, D=900.0, elev=[2.0, 18.0, 38.0], du=6.0,
                    dv=[-4.0, -2.0, 3.0], turn=30.0)
        folder = os.path.join(cls.tmp, "photos")
        photograph(folder, rig, np.array(pts, dtype=np.float32), cols, rows)
        cls.rec = H.run(folder, 200.0, "hand", cols=cols, rows=rows, pattern="c{i:03d}.png", side_col=3,
                        front="right", voxel=2.0, out=os.path.join(cls.tmp, "out"),
                        views_out=os.path.join(cls.tmp, "views"), ortho_px=2.0, calib_scale=0.6, calib_every=1,
                        maxfev=80, log=lambda s: None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_the_left_side_is_on_the_left_in_the_obj_and_the_top_view(self):
        self.assertEqual(self.rec["status"], "pass", self.rec.get("problems"))
        V = np.array([[float(v) for v in line.split()[1:4]] for line in open(self.rec["obj"], encoding="utf-8")
                      if line.startswith("v ")])
        x, z = V[:, 0], V[:, 2]
        mid = (z.min() + z.max()) / 2
        at = (x > 0.45 * x.max()) & (x < 0.6 * x.max())  # (the bump's stretch of the length: 90..130 of 200 mm)
        away = x < 0.25 * x.max()
        # the bump sticks out on -z (the left, right-handed) where it is, and nowhere else
        self.assertLess(z[at].min(), z[away].min() - 4.0)
        self.assertAlmostEqual(z[at].max(), z[away].max(), delta=2.5)
        self.assertLess(z[at].min(), mid)
        top = np.asarray(Image.open(self.rec["views"]["top"]).convert("L")) < 128
        rows_ = np.nonzero(top.any(1))[0]
        cols_ = np.nonzero(top[:, int(0.52 * top.shape[1])])[0]   # (a column through the bump)
        far = np.nonzero(top[:, int(0.15 * top.shape[1])])[0]     # (a column away from it)
        self.assertLess(cols_.min(), far.min() - 3)                # (the bump at the TOP: the left side up)
        self.assertGreater(len(rows_), 0)

    def test_a_failed_run_says_so(self):
        from unittest import mock

        bad = {**self.rec, "status": "fail", "problems": ["the hull touches its carving box along its height"]}
        with mock.patch.object(H, "run", return_value=bad):
            import contextlib
            import io

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = H.main([self.tmp, "--length-mm", "200", "--name", "x"])
        self.assertEqual(code, 1)
        self.assertIn("touches its carving box", out.getvalue())

    def test_a_hull_touching_its_box_is_clipped(self):
        occ = np.zeros((10, 8, 6), dtype=bool)
        occ[2:8, 2:6, 2:4] = True
        self.assertEqual(H.clipped(occ), [])
        occ[2:8, 0:6, 2:4] = True
        self.assertEqual(H.clipped(occ), [1])



class TestHandednessFrontLeft(TestHandedness):
    """the same object turned round on the turntable (its side photo has the front to the LEFT, kit refs hull
    --front left: GLOCK's): its left side still comes out on its left"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="kit_hull_handl_")
        pts = list(solid(1.5))  # (with its grip: a slide alone reads the same turned round, so no camera is found)
        for x in np.arange(-10, 30, 1.5):
            for y in np.arange(26, 38, 1.5):
                for z in np.arange(12.5, 20.5, 1.5):
                    pts.append((x, y, z))
        cols, rows = 12, 3
        rig = H.Rig(360, 330, cols, rows, side_col=3, k=1.3, D=900.0, elev=[2.0, 18.0, 38.0], du=6.0,
                    dv=[-4.0, -2.0, 3.0], turn=30.0)
        folder = os.path.join(cls.tmp, "photos")
        photograph(folder, rig, np.array(pts, dtype=np.float32), cols, rows, front_left=True)
        cls.rec = H.run(folder, 200.0, "handl", cols=cols, rows=rows, pattern="c{i:03d}.png", side_col=3,
                        front="left", voxel=2.0, out=os.path.join(cls.tmp, "out"),
                        views_out=os.path.join(cls.tmp, "views"), ortho_px=2.0, calib_scale=0.6, calib_every=1,
                        maxfev=80, log=lambda s: None)


if __name__ == "__main__":
    unittest.main()
