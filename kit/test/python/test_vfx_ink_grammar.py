"""kit/vfx/inkgrammar.py + ink.render_grammar - the five sakuga vector grammars (LIMITATIONS_FIXES_V4 §3.4 step 2,
§13.3.2). What is proven: each grammar's sheet is the size and grid the contract says, with a glow mask beside it; the
numbers DRIVE the drawing (the solidity and cut-out share measured back on the drawn cells hit the asked numbers, a
higher speed moves the drawing more); each grammar's defining feature is measured from the pixels and a drawing
without it is caught; the packing checks catch a drawing in the gutter and black see-through pixels; hostile numbers
are refused; and a REAL trace (the made flame through kit/vfx/shapetrace.py) gives numbers in range.
Run: python -m pytest kit/test/python/test_vfx_ink_grammar.py -q"""

import contextlib
import io
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
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "selftest", "vfx", "trace"))
import ink as I  # noqa: E402
import inkgrammar as G  # noqa: E402
import made  # noqa: E402
import shapetrace as T  # noqa: E402

M = {"area_frac": 0.35, "centroid_vel": 0.5, "cutout_ratio": 0.03}


def failed(checks):
    return {c["name"]: c["value"] for c in checks if not c["ok"]}


class Sheet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_contract_size_grid_glow(self):
        """the contract's defaults: 64 drawings, 8 x 8 cells of 128 px = a 1024 x 1024 RGBA sheet + its glow mask"""
        sheet, glow = I.render_grammar("flame_tongue", M, out_dir=self.tmp)
        im, gl = Image.open(sheet), Image.open(glow)
        self.assertEqual((im.size, im.mode), ((1024, 1024), "RGBA"))
        self.assertEqual(gl.size, (1024, 1024))
        a = np.asarray(im)[..., 3]
        for r in range(8):                                    # every cell drawn, its 2 px gutter empty
            for q in range(8):
                c = a[r * 128:(r + 1) * 128, q * 128:(q + 1) * 128]
                self.assertGreater(int((c > 127).sum()), 50)
                self.assertEqual(int(max(c[:2].max(), c[-2:].max(), c[:, :2].max(), c[:, -2:].max())), 0)
        rgb = np.asarray(im)[..., :3]
        self.assertEqual(int(((a == 0) & (rgb.sum(axis=2) == 0)).sum()), 0, "see-through pixels left black")
        g = np.asarray(gl.convert("L")).astype(np.float32)
        lum = (rgb @ np.array([0.2126, 0.7152, 0.0722])) * a / 255.0
        self.assertGreater(g[lum > 200].mean(), 200)         # the white core glows ...
        self.assertLess(g[(a > 0) & (lum < 110)].mean(), 30)  # ... the dark rim does not
        rep = json.load(open(os.path.join(self.tmp, "flame_tongue.grammar.json"), encoding="utf-8"))
        self.assertEqual(rep["play"], {"layout": [8, 8], "fps": 12.0, "mode": "Loop", "blend": False})
        self.assertFalse(failed(rep["checks"]))

    def test_every_grammar_passes_its_checks(self):
        for g in G.GRAMMARS:
            res = I.grammar_sheet(g, M, frames=32, grid=8)
            self.assertFalse(failed(res["checks"]), g)
            self.assertEqual(res["sheet"].shape, (512, 1024, 4), g)
            names = {c["name"] for c in res["checks"]}
            want = {"flame_tongue": {"s_wave", "embers"}, "slash_crescent": {"razor_lead", "jagged_wake"},
                    "sakuga_smoke": {"hard_shadow"}, "kanada_bolt": {"strobe", "mitered"},
                    "liquid_splash": {"drops", "rayleigh_plateau"}}[g]
            self.assertTrue(want <= names, (g, names))

    def test_area_and_cutout_are_driven(self):
        """the asked solidity and cut-out share come back, measured on the drawn cells"""
        lo = I.grammar_sheet("flame_tongue", {**M, "area_frac": 0.3, "cutout_ratio": 0.02}, frames=16, grid=4)
        hi = I.grammar_sheet("flame_tongue", {**M, "area_frac": 0.5, "cutout_ratio": 0.06}, frames=16, grid=4)
        self.assertAlmostEqual(lo["measured"]["area_frac"], 0.3, delta=G.TOL_AREA)
        self.assertAlmostEqual(hi["measured"]["area_frac"], 0.5, delta=G.TOL_AREA)
        self.assertAlmostEqual(lo["measured"]["cutout_ratio"], 0.02, delta=0.015)
        self.assertAlmostEqual(hi["measured"]["cutout_ratio"], 0.06, delta=0.015)
        self.assertGreater(hi["params"]["thick"], lo["params"]["thick"])

    def test_unreachable_numbers_are_said(self):
        res = I.grammar_sheet("kanada_bolt", {**M, "area_frac": 0.9, "cutout_ratio": 0.2}, frames=16, grid=4)
        said = " ".join(res["said"])
        self.assertIn("past what a kanada_bolt can be", said)
        self.assertIn("no cut-outs", said)

    def test_speed_drives_motion(self):
        """a faster trace: the flame's wave turns more often, the slash front-loads, the smoke rises further, the bolt's
        root drifts further, the splash launches faster - and the smoke's middle MEASURES further up the sheet"""
        slow, fast = {**M, "centroid_vel": 0.1}, {**M, "centroid_vel": 1.0}
        for g, key in (("flame_tongue", "cycles"), ("slash_crescent", "ease"), ("sakuga_smoke", "travel"),
                       ("kanada_bolt", "drift"), ("liquid_splash", "launch")):
            ps, _ = G.drive(g, slow, 64, 2)
            pf, _ = G.drive(g, fast, 64, 2)
            self.assertGreater(pf[key], ps[key], g)

        def rise(metrics):
            P, _ = G.drive("sakuga_smoke", metrics, 16, 2)
            P["thick"] = 1.0
            ys = []
            for k in (0, 15):
                a = G.raster(G.sakuga_smoke(k, 16, P, 1), 128)[0]
                ys.append(float(np.nonzero(a > 0.5)[0].mean()))
            return ys[0] - ys[1]
        self.assertGreater(rise(fast), rise(slow) + 3.0)

    def test_rayleigh_plateau_numbers(self):
        self.assertAlmostEqual(G.RP_WAVE, 9.01, places=2)
        self.assertAlmostEqual(G.RP_DROP, 1.89, places=2)
        d = G.liquid_splash(40, 64, {"thick": 1.0, "hole": 0.0, "launch": 0.8}, 1)
        self.assertAlmostEqual(d["meta"]["lam"] / d["meta"]["r"], 9.01, places=2)
        self.assertGreater(d["meta"]["drops"], 6)


class Caught(unittest.TestCase):
    """each defining feature and each packing rule: a drawing without it is caught"""

    def cells(self, g, frames=16):
        res = I.grammar_sheet(g, M, frames=frames, grid=G.COUNTS[frames][0])
        return res

    def test_no_strobe_caught(self):
        res = self.cells("kanada_bolt")
        flash_only = [res["cells"][k - k % 2] for k in range(16)]     # every drawing the flash: no off frame
        flash_only = [c * (1.0 + 0.001 * i) for i, c in enumerate(flash_only)]
        sig = failed(G.signature("kanada_bolt", flash_only, None, res["tones"], 128))
        self.assertIn("strobe", sig)

    def test_rounded_bolt_caught(self):
        import cv2
        res = self.cells("kanada_bolt")
        soft = []
        for c in res["cells"]:
            a = cv2.GaussianBlur(c[..., 3], (0, 0), 3.0)
            a = (a > 0.25).astype(np.float32)
            soft.append(np.dstack([c[..., :3], a]))
        self.assertIn("mitered", failed(G.signature("kanada_bolt", soft, None, res["tones"], 128)))

    def test_straight_flame_caught(self):
        """a straight cone (no S-bend) and no embers: both named"""
        P = {"thick": 0.8, "hole": 0.0, "cycles": 1}
        cells = []
        for k in range(16):
            s = np.linspace(0, 1, 40)
            line = np.stack([np.full(40, 0.5), 0.95 - 0.6 * s - 0.01 * k], 1)
            w = 0.15 * (1 - s) ** 0.85
            d = {"layers": [{"tone": 0, "items": G.ribbon(line, w)}, {"tone": 1, "items": G.ribbon(line, w * 0.6)}],
                 "cuts": [], "meta": {}}
            cells.append(G.mip_pad(G.paint(G.raster(d, 128), G.GREYS)))
        sig = failed(G.signature("flame_tongue", cells, None, G.GREYS, 128))
        self.assertIn("s_wave", sig)
        self.assertIn("embers", sig)

    def test_symmetric_slash_caught(self):
        """a crescent of even thickness (no razor lead): caught"""
        res = self.cells("slash_crescent")
        ds = []
        P = {"thick": 1.0, "hole": 0.0, "ease": 2.0}
        cells = []
        for k in range(16):
            d = G.slash_crescent(k, 16, P, 1)
            m = d["meta"]
            u = np.linspace(0, 1, 120)
            th = 0.05 * np.sin(np.pi * u)                        # thickest in the MIDDLE
            ang = m["tail"] + m["span"] * u
            cx, cy = m["centre_xy"]
            outer = np.stack([cx + (0.4 + th) * np.cos(ang), cy + (0.4 + th) * np.sin(ang)], 1)
            inner = np.stack([cx + (0.4 - th) * np.cos(ang), cy + (0.4 - th) * np.sin(ang)], 1)
            dd = {"layers": [{"tone": 0, "items": [(np.concatenate([outer, inner[::-1]]), [])]}], "cuts": [], "meta": m}
            ds.append(dd)
        win = G.window(ds)
        cells = [G.mip_pad(G.paint(G.raster(d, 128, win=win), G.GREYS)) for d in ds]
        sig = failed(G.signature("slash_crescent", cells, ds, G.GREYS, 128, win))
        self.assertIn("razor_lead", sig)
        self.assertIn("jagged_wake", sig)

    def test_soft_shadow_smoke_caught(self):
        """a puff with no shadow tone (all lit): caught"""
        res = self.cells("sakuga_smoke")
        lit = []
        for c in res["cells"]:
            x = c.copy()
            x[..., :3] = np.where(x[..., 3:4] > 0, np.asarray(res["tones"][1], np.float32) / 255.0, x[..., :3])
            lit.append(x)
        self.assertIn("hard_shadow", failed(G.signature("sakuga_smoke", lit, None, res["tones"], 128)))

    def test_merged_drops_caught(self):
        """drops twice the Rayleigh-Plateau size: caught"""
        import cv2
        res = I.grammar_sheet("liquid_splash", M, frames=32, grid=8)
        drawings = [G.liquid_splash(k, 32, {**res["params"]}, 1) for k in range(32)]
        fat = []
        for c in res["cells"]:
            a = cv2.dilate((c[..., 3] > 0.5).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(np.float32)
            fat.append(np.dstack([c[..., :3], a]))
        sig = failed(G.signature("liquid_splash", fat, drawings, res["tones"], 128, tuple(res["window"])))
        self.assertIn("rayleigh_plateau", sig)

    def test_gutter_and_padding_caught(self):
        res = self.cells("flame_tongue")
        cells = [c.copy() for c in res["cells"]]
        cells[3][0:1, 60:64, 3] = 1.0                          # a drawing in the gutter
        cells[5][..., :3] = np.where(cells[5][..., 3:4] == 0, 0.0, cells[5][..., :3])   # padding taken away
        checks, _, _ = I.sheet_checks(cells, res["tones"], 4, 4, 128)
        bad = failed(checks)
        self.assertIn("gutter", bad)
        self.assertIn("mip_padded", bad)
        self.assertIn("mip_clean", bad)
        good, _, level = I.sheet_checks(res["cells"], res["tones"], 4, 4, 128)
        self.assertFalse(failed(good))
        self.assertGreaterEqual(level, 1)

    def test_hostile_numbers_refused(self):
        for bad in ({**M, "area_frac": float("nan")}, {**M, "centroid_vel": -1}, {**M, "cutout_ratio": 2.0},
                    {"area_frac": 0.3}, {**M, "area_frac": True}, None):
            with self.assertRaises(ValueError):
                I.grammar_sheet("flame_tongue", bad, frames=16, grid=4)
        with self.assertRaises(ValueError):
            I.grammar_sheet("fire", M)
        with self.assertRaises(ValueError):
            I.grammar_sheet("flame_tongue", M, frames=48)
        with self.assertRaises(ValueError):
            I.grammar_sheet("flame_tongue", M, frames=64, grid=4)


class FromTrace(unittest.TestCase):
    def test_made_flame_trace(self):
        """the made flame through the REAL trace -> numbers in range, and area_frac means what the drawn cells
        measure: the made flame's own cut-out, measured the grammar's way, within 0.06 of it"""
        frames = made.scene()
        trace = T.trace_frames(np.asarray(frames), made.FPS, hue=made.HUE)
        data = T.to_json(trace)
        m = G.metrics_from_trace(data)
        self.assertTrue(0.2 < m["area_frac"] < 0.95, m)
        self.assertGreaterEqual(m["centroid_vel"], 0.0)
        self.assertTrue(0.0 <= m["cutout_ratio"] < 0.5, m)
        masks = [T.clean(x) for x in T.cut_out(np.asarray(frames), made.HUE)]
        pix = float(np.median([G.solidity(x.astype(np.float32)) for x in masks if x.any()]))
        self.assertAlmostEqual(m["area_frac"], pix, delta=0.06)

    def test_cli_from_trace(self):
        tmp = tempfile.mkdtemp()
        try:
            data = T.to_json(T.trace_frames(np.asarray(made.scene()), made.FPS, hue=made.HUE))
            path = os.path.join(tmp, "beat1.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            said = io.StringIO()
            with contextlib.redirect_stdout(said):
                code = I.main(["made_flame_g", "--grammar", "flame_tongue", "--from", path, "--frames", "16",
                               "--look-dir", tmp])
            line = json.loads(said.getvalue().strip().splitlines()[-1])
            self.assertEqual(code, 0, line["summary"])
            self.assertTrue(os.path.isfile(os.path.join(tmp, "made_flame_g.png")))
            self.assertTrue(os.path.isfile(os.path.join(tmp, "made_flame_g_glow.png")))
            rep = json.load(open(os.path.join(tmp, "made_flame_g.grammar.json"), encoding="utf-8"))
            self.assertEqual(rep["tones"], sorted(rep["tones"], key=lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(I.main(["x", "--grammar", "flame_tongue", "--metrics", "0.3,-1,0", "--look-dir", tmp]), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
