"""H4 ornament (his limitations review V3, 2026-11-17: "a.ornament ... 2.5-texel Nyquist gate"): a mask picture as
relief in the normal map - its edge from the EXACT distance to the ornament's border (rbx_stamps, numpy only), an .svg
drawn by Blender's importer, the thinnest stroke read by the bake's stamp_texels check - and a real bake on a steel
plate (kit/selftest/blender/build_ornament.py): upright, not mirrored, the hole left flat, the engraving darkened."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_stamps as S  # noqa: E402

BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
FIXTURE = os.path.join(ROOT, "kit", "selftest", "blender", "build_ornament.py")


def _brute(mask):
    """the exact inside distance by brute force (px, pixel centre to the nearest False pixel centre; outside False)"""
    m = np.pad(np.asarray(mask, bool), 1)
    off = np.argwhere(~m)
    out = np.zeros(m.shape)
    for y, x in np.argwhere(m):
        out[y, x] = np.sqrt(((off - (y, x)) ** 2).sum(1)).min()
    return out[1:-1, 1:-1]


def _npy(arr, d):
    p = os.path.join(d, "m.npy")
    np.save(p, np.asarray(arr, np.float32))
    return p


class Distance(unittest.TestCase):
    def test_exact_against_brute_force(self):
        rng = np.random.default_rng(3)
        m = rng.random((30, 41)) > 0.35
        self.assertTrue(np.allclose(S.inside_distance(m, 64), _brute(m), atol=1e-5))

    def test_capped(self):
        m = np.ones((50, 50), bool)
        self.assertEqual(float(S.inside_distance(m, 5).max()), 5.0)

    def test_stroke_widths(self):
        for w in (3, 9, 20):
            m = np.zeros((60, 80), bool)
            m[20:20 + w, 5:75] = True
            got = S.stroke_widths(m)[0]
            self.assertTrue(w - 1 <= got <= w, (w, got))   # (never wider than the stroke, at most a pixel under)


class Height(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        m = np.zeros((40, 60))
        m[10:30, 5:55] = 1
        self.mask = _npy(m, self.d)

    def test_round_v_flat_and_cut(self):
        kw = dict(mask=self.mask, depth_mm=0.5, edge_mm=0.8)   # (the band is 2 mm: full height 0.8 mm in)
        rnd = S.height("ornament", (6.0, 4.0), 10, profile="round", **kw)
        v = S.height("ornament", (6.0, 4.0), 10, profile="v", **kw)
        flat = S.height("ornament", (6.0, 4.0), 10, profile="flat", **kw)
        cut = S.height("ornament", (6.0, 4.0), 10, profile="v", cut=True, **kw)
        row = 20
        self.assertAlmostEqual(float(rnd.max()), 0.5, places=4)
        self.assertEqual(float(rnd[row, 0]), 0.0)                      # (outside: the surface)
        edge = rnd[row, 5:16]
        self.assertTrue(np.all(np.diff(edge) >= -1e-6))                 # (rises from the border inward)
        self.assertTrue(np.all(rnd[row, 5:16] >= v[row, 5:16] - 1e-6))  # (a round bead stands fuller than a chamfer)
        self.assertGreater(float(flat[row, 6]), 0.49)                   # (a sharp wall: full height a pixel in)
        self.assertTrue(np.allclose(cut, -v))

    def test_refusals(self):
        with self.assertRaises(ValueError):
            S.check("ornament", depth_mm=1.0)
        with self.assertRaises(ValueError):
            S.check("ornament", mask=self.mask, profile="ogee")
        with self.assertRaises(ValueError):
            S.check("ornament", mask=self.mask, size=3)
        with self.assertRaises(FileNotFoundError):
            S.height("ornament", (6.0, 4.0), 10, mask=os.path.join(self.d, "none.png"))

    def test_finest_mm_follows_the_size(self):
        small = S.finest_mm("ornament", (6.0, 4.0), px_per_mm=10, mask=self.mask)
        large = S.finest_mm("ornament", (12.0, 8.0), px_per_mm=10, mask=self.mask)
        self.assertAlmostEqual(large / small, 2.0, delta=0.15)


class Pictures(unittest.TestCase):
    def test_alpha_or_darkness_and_invert(self):
        from PIL import Image  # noqa: PLC0415

        d = tempfile.mkdtemp()
        rgba = np.zeros((10, 10, 4), np.uint8)
        rgba[2:5, :, 3] = 255                 # (solid where the ornament is, clear elsewhere: by alpha)
        Image.fromarray(rgba, "RGBA").save(os.path.join(d, "a.png"))
        ink = np.full((10, 10, 3), 255, np.uint8)
        ink[6:9] = 0                          # (dark lines on light paper: by darkness)
        Image.fromarray(ink, "RGB").save(os.path.join(d, "b.png"))
        a = S.read_mask(os.path.join(d, "a.png"))
        b = S.read_mask(os.path.join(d, "b.png"))
        self.assertTrue(a[3].min() == 1.0 and a[7].max() == 0.0)
        self.assertTrue(b[7].min() == 1.0 and b[3].max() == 0.0)
        inv = S.ornament_mask({"mask": os.path.join(d, "b.png"), "invert": True}, (10, 10))
        self.assertTrue(inv[3].all() and not inv[7].any())

    def test_triangles_drawn(self):
        sq = np.array([[[10, 10], [30, 10], [30, 20]], [[10, 10], [30, 20], [10, 20]]], float)
        m = S.raster_triangles(sq, 40, 40)
        self.assertEqual(int(m.sum()), 20 * 10)
        self.assertTrue(m[15, 20] and not m[25, 20] and not m[15, 35])

    def test_the_fixtures_are_there(self):
        for f in ("ornament_crest.svg", "ornament_scroll.png"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "kit", "selftest", "blender", f)), f)


def bake(how):
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", FIXTURE, "--", how],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    dec = json.JSONDecoder()   # (Blender's status line ends with no newline: a marker can follow it on that line)

    def after(mark):
        i = out.stdout.rfind(mark)
        return dec.raw_decode(out.stdout[i + len(mark):])[0] if i >= 0 else None

    got = after("ORNWRAP ") or after("STITCH ") or after("ORN ")
    at = out.stdout.rfind('{"schema"')
    status = dec.raw_decode(out.stdout[at:])[0] if at >= 0 else None
    return out.returncode, got, status, out.stdout[-2000:] + out.stderr[-2000:]


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class TheBake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good, cls.none, cls.fine = bake("good"), bake("none"), bake("fine")
        cls.wrap, cls.flat = bake("wrap"), bake("flat")
        cls.stitch = bake("stitch")

    def test_the_ornaments_read_in_the_normal_map(self):
        code, g, st, log = self.good
        self.assertEqual(code, 0, log)
        self.assertGreater(g["crest"], 0.03, g)
        self.assertGreater(g["scroll"], 0.08, g)
        self.assertEqual(g["plain"], 0.0, g)
        self.assertEqual(st["facts"]["stamps"], {"ornament": 2})
        self.assertEqual(st["facts"]["stamps_too_fine"], [])

    def test_upright_not_mirrored_and_the_hole_open(self):
        _c, g, _s, _l = self.good
        self.assertGreater(g["rim_up"], 0.15, g)
        self.assertEqual(g["rim_flipped"], 0.0, g)
        self.assertGreater(g["spiral_left_above"], 0.15, g)
        self.assertEqual(g["spiral_left_below"], 0.0, g)
        self.assertEqual(g["hole"], 0.0, g)

    def test_the_engraving_is_darkened(self):
        _c, g, _s, _l = self.good
        self.assertLess(g["scroll_dark"], 0.97, g)

    def test_no_ornament_reads_flat(self):
        code, n, _s, log = self.none
        self.assertEqual(code, 0, log)
        self.assertEqual((n["crest"], n["scroll"]), (0.0, 0.0), n)

    def test_too_fine_is_said(self):
        code, _f, st, log = self.fine
        self.assertEqual(code, 0, log)
        small = st["facts"]["stamps_too_fine"]
        self.assertTrue(small and small[0].startswith("ornament"), small)
        self.assertTrue(any(c["name"] == "stamp_texels" and not c["ok"] for c in st["design"]))

    def test_wrapped_round_a_cylinder(self):
        """the scroll's drawn arc is (300 - 20) / 320 of 0.8 stud = 0.7 stud on a 0.3 radius: +-67 degrees round
        the drum's front - it reads there and stops; projected flat it falls off the sides by 60 degrees"""
        code, w, _s, log = self.wrap
        self.assertEqual(code, 0, log)
        for deg in ("-60", "60", "-40", "40"):
            self.assertGreater(w[deg], 0.05, (deg, w))
        for deg in ("-90", "90", "-120", "120"):
            self.assertEqual(w[deg], 0.0, (deg, w))
        code, f, _s, log = self.flat
        self.assertEqual(code, 0, log)
        self.assertEqual((f["-60"], f["60"]), (0.0, 0.0), f)

    def test_a_seam_sewn_along_a_curve(self):
        """a.stitch_line on a half circle: each leg's stitches turned to run along it - the normal map turns on the
        arc and not beside it (card maah: "a seam that follows a curve")"""
        code, g, _s, log = self.stitch
        self.assertEqual(code, 0, log)
        self.assertGreater(g["on_arc"], 0.2, g)
        self.assertEqual(g["beside"], 0.0, g)

    def test_around_refusals(self):
        with self.assertRaises(ValueError):
            S.wrap_of(("W", (0, 0, 0)), (0, 0, -0.3))
        with self.assertRaises(ValueError):
            S.wrap_of(("Y", (0, 0, 0)), (0, 0.5, 0))   # (on the axis)
        w = S.wrap_of(("Y", (0, 0, 0)), (0, 0.2, -0.3))
        self.assertAlmostEqual(w["radius"], 0.3)
        self.assertEqual(w["out"], (0.0, 0.0, -1.0))
        self.assertAlmostEqual(w["along"], 0.2)


if __name__ == "__main__":
    unittest.main()
