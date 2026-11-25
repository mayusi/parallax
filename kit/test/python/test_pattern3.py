"""H6 / S3 patterns on the model (his limitations review V3: "lathe_rings, brushed, car_paint, radial_dust ... to
world_pos 3D coordinates"): rbx_wear.pattern3 - lathe rings round a real axis, car-paint flakes, brushed streaks
along a real direction - and rbx_layers' "radial" source (brake dust from a hub), measured on numpy fields and on
a real bake (kit/selftest/blender/build_pattern3.py)."""

import json
import os
import subprocess
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_layers as L  # noqa: E402
import rbx_wear as W  # noqa: E402

BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def disc(n=200):
    """a 100 mm disc in the XY plane as a texel grid (its places, which texels lie on it)"""
    ys, xs = np.mgrid[0:n, 0:n]
    p = np.stack([(xs - n / 2) * 1.0, (ys - n / 2) * 1.0, np.zeros_like(xs)], axis=2).astype(np.float32)
    return p, np.hypot(xs - n / 2, ys - n / 2) < n / 2 - 5


class Patterns(unittest.TestCase):
    def test_lathe_rings_round_the_axis(self):
        p, inside = disc()
        h = W.pattern3("lathe", p, inside, 5.0, ("Z", (0, 0, 0)))
        r = np.hypot(p[..., 0], p[..., 1])
        on = inside & (np.abs(r - 40.0) < 0.3)
        self.assertGreater(float(h[on].min()), 0.95)              # (a whole ring at 40 mm: 8 pitches out, a crest)
        off = inside & (np.abs(r - 42.5) < 0.3)
        self.assertLess(float(h[off].max()), 0.06)               # (half a pitch further: the groove, all round)

    def test_brushed_streaks_run_along_the_axis(self):
        p, inside = disc()
        h = W.pattern3("brushed", p, inside, 1.3, "X")
        along = float(np.abs(np.diff(h[100, 20:180])).mean())
        across = float(np.abs(np.diff(h[20:180, 100])).mean())
        self.assertGreater(across, 3 * along, (along, across))

    def test_flakes_each_tilted_their_own_way(self):
        p, inside = disc()
        h = W.pattern3("flake", p, inside, 3.0)
        self.assertAlmostEqual(float(h[inside].mean()), 0.5, delta=0.05)
        self.assertGreater(float(h[inside].std()), 0.2)
        self.assertTrue(np.array_equal(h, W.pattern3("flake", p, inside, 3.0)))

    def test_refusals(self):
        p, inside = disc(40)
        with self.assertRaises(ValueError):
            W.pattern3("spiral", p, inside, 1.0)
        with self.assertRaises(ValueError):
            W.axis_of("W")
        self.assertIn("lathe", W.PATTERNS3)


class Radial(unittest.TestCase):
    def test_most_at_the_axis(self):
        p, inside = disc()
        f = W.radial_field(p, inside, ("Z", (0, 0, 0)))
        self.assertGreater(float(f[100, 100]), 0.99)
        self.assertLess(float(f[100, 190]), 0.1)
        out = W.radial_field(p, inside, ("Z", (0, 0, 0)), outward=True)
        self.assertLess(float(out[100, 100]), 0.01)

    def test_a_layer_takes_an_axis_only_where_radial(self):
        lay = L.layer("soot", where="radial", axis=("Z", (0, 0, 0)))
        self.assertEqual(lay["axis"], ("Z", (0, 0, 0)))
        self.assertNotIn("axis", L.layer("soot", where="all"))   # (every other layer's dict unchanged)
        with self.assertRaises(ValueError):
            L.layer("soot", where="all", axis="Z")
        p, inside = disc(64)
        m = {"convex": np.zeros((64, 64, 1), np.float32), "places": (p, inside)}
        self.assertEqual(L.field("radial", m, ("Z", (0, 0, 0))).shape, (64, 64, 1))
        self.assertEqual(L.resolve([lay], "hub")[0]["where"], "radial")


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class TheBake(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                              os.path.join(ROOT, "kit", "selftest", "blender", "build_pattern3.py")],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
        dec = json.JSONDecoder()
        i = out.stdout.rfind("PAT3 ")
        cls.got = dec.raw_decode(out.stdout[i + 5:])[0] if i >= 0 else None
        k = out.stdout.find('{"schema"')
        cls.status = dec.raw_decode(out.stdout[k:])[0] if k >= 0 else None
        cls.code, cls.log = out.returncode, out.stdout[-1500:] + out.stderr[-1500:]

    def test_built_and_every_pattern_resolved_on_the_model(self):
        self.assertEqual(self.code, 0, self.log)
        self.assertEqual(self.status["status"], "pass", self.status["summary"])
        pats = {k: v for o in self.status["facts"]["patterns"].values() for k, v in o.items()}
        for k in ("lathe", "flake", "brushed"):
            self.assertTrue(pats[k]["on_the_model"] and pats[k]["resolved"], pats[k])

    def test_the_rings_the_streaks_the_flakes_the_dust(self):
        g = self.got
        self.assertGreater(g["disc_across_rings_deg"], 4 * g["disc_along_ring_deg"], g)
        self.assertGreater(g["brush_along_y_deg"], 10 * g["brush_along_x_deg"], g)
        self.assertGreater(g["flake_spread_deg"], 2.0, g)
        lum = g["hub_lum_out"]
        self.assertLess(lum[0], lum[-1] - 0.2, lum)          # (darkest at the hub, clean at the rim)


if __name__ == "__main__":
    unittest.main()
