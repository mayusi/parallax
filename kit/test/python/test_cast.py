"""S4 a.cast (his limitations review V3, 9.4: "OpenCASCADE BRepFilletAPI_MakeFillet first ... fall back to sdf ...
pitch <= min(0.25 mm, fillet_mm / 4) ... keep_sharp ... cast-iron/sand texture micro-noise"): parts poured as one with
a TRUE fillet of the asked radius where they meet - by the CAD route (the parts' own code fused, only the junction
filleted) or the distance-field route (rbx_sculpt.rmin: the round minimum) - on a post standing on a plate
(kit/selftest/blender/build_cast.py). The fillet is measured: the cast's radius round the post at heights over the
plate against a true 8 mm round's."""

import json
import math
import os
import subprocess
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_sculpt as S  # noqa: E402

BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
FIXTURE = os.path.join(ROOT, "kit", "selftest", "blender", "build_cast.py")
R_POST, FILLET = 0.06 * 280.0, 8.0


def true_round(h):
    """a true circular fillet of radius FILLET in a square corner: how far it stands out from the wall h mm up"""
    return FILLET - math.sqrt(max(0.0, FILLET ** 2 - (FILLET - h) ** 2)) if h < FILLET else 0.0


class RoundMinimum(unittest.TestCase):
    def test_a_square_corner_gets_a_circle_of_the_radius(self):
        # a floor (y < 0 solid: distance y) and a wall (x < 0 solid: distance x); the union's surface at height h
        r = 8.0
        for h in (1.0, 2.0, 4.0, 6.0):
            xs = np.linspace(0, r, 20001)
            d = S.rmin(np.full_like(xs, h), xs, r)
            x0 = float(xs[np.argmin(np.abs(d))])   # where the surface crosses at that height
            self.assertAlmostEqual(x0, true_round(h), delta=0.01)

    def test_zero_is_the_plain_minimum_and_far_away_nothing_changes(self):
        a, b = np.array([1.0, 3.0, -2.0]), np.array([2.0, 0.5, 4.0])
        self.assertTrue(np.array_equal(S.rmin(a, b, 0.0), np.minimum(a, b)))
        self.assertTrue(np.allclose(S.rmin(np.array([20.0]), np.array([30.0]), 8.0), [20.0]))
        self.assertIn("fillet", S.EDGES)


def build(how):
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", FIXTURE, "--", how],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    dec = json.JSONDecoder()
    i = out.stdout.rfind("CAST ")
    got = dec.raw_decode(out.stdout[i + 5:])[0] if i >= 0 else None
    k = out.stdout.find('{"schema"')
    status = dec.raw_decode(out.stdout[k:])[0] if k >= 0 else None
    return out.returncode, got, status, out.stdout[-1500:] + out.stderr[-1500:]


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class TheCast(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {h: build(h) for h in ("geo", "cad", "apart", "grain", "low", "cadlow")}

    def check_round(self, got, tol):
        rad = got["radius_mm"]
        for h in (1.0, 2.0, 4.0):
            self.assertAlmostEqual(rad[str(h)], R_POST + true_round(h), delta=tol, msg=(h, rad))
        for h in (8.0, 20.0, 60.0):
            self.assertAlmostEqual(rad[str(h)], R_POST, delta=tol, msg=(h, rad))

    def test_the_cad_route_is_exact(self):
        code, got, st, log = self.runs["cad"]
        self.assertEqual(code, 0, log)
        self.assertEqual(st["status"], "pass", st["summary"])
        c = got["casts"][0]
        self.assertEqual((c["mode"], c["route"]), ("cad", "geometry (an exact CAD solid)"))
        self.check_round(got, 0.05)
        self.assertLess(got["corner_mm"], 0.01)   # (the plate's machined corner exact)

    def test_the_distance_field_route_is_a_true_round_too(self):
        code, got, st, log = self.runs["geo"]
        self.assertEqual(code, 0, log)
        self.assertEqual(st["status"], "pass", st["summary"])
        c = got["casts"][0]
        self.assertEqual(c["mode"], "sdf")
        self.assertIn("not every part is a single a.cad part", c["not_cad"])
        self.assertLessEqual(c["voxel_mm"], FILLET / 4)
        self.check_round(got, 0.2)
        self.assertLess(got["corner_mm"], 0.3)    # (kept sharp: the corner snapped back onto its planes)
        self.assertGreater(c["bulge_mm"], 0.1 * FILLET)

    def test_parts_that_do_not_meet_fail_by_name(self):
        code, got, st, log = self.runs["apart"]
        self.assertEqual(code, 0, log)
        self.assertEqual(st["status"], "fail")
        bad = [c for c in st["design"] if c["name"] == "cast_fillet"]
        self.assertTrue(bad and not bad[0]["ok"] and bad[0]["severity"] == "error", bad)

    def test_the_sand_cast_skin(self):
        code, got, _st, log = self.runs["grain"]
        self.assertEqual(code, 0, log)
        _c, plain, _s, _l = self.runs["geo"]
        self.assertGreater(got["spread_mm"], 0.2)          # (round the post: the grain's relief)
        self.assertLess(plain["spread_mm"], 0.05)
        self.check_round(got, 0.5)                          # (the fillet still there under the grain)

    def test_the_high_and_low_route(self):
        """both routes make a game mesh and a bake source; the close-up fidelity of small sharp-edged lows is the
        route's own open question (card 3aan: a plain a.cad plate and post fail it too, worse), so not held here"""
        for how, mode in (("low", "sdf"), ("cadlow", "cad")):
            code, got, st, log = self.runs[how]
            self.assertEqual(code, 0, log)
            c = got["casts"][0]
            self.assertEqual(c["mode"], mode)
            self.assertTrue(c["route"].startswith("high and low"), c)
            g = st["facts"]["low"]["groups"]["cast"]
            self.assertGreater(g["high_tris"], g["low_tris"])
            self.assertLess(g["silhouette_mm"]["max_mm"], 0.5, g["silhouette_mm"])   # (the low is the cast's shape)


if __name__ == "__main__":
    unittest.main()
