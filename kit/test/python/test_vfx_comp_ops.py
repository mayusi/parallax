"""kit/vfx/comp.py's ops of the V3 doc's compositor (VFX stage D.1): voronoi CELLS that tile, a noise read in POLAR
form (a pan turns it round or runs it outward), a TWIRL that turns the lookups round a point, a hot RIM on the
alpha's border that rides an erosion front, a glow mask allowed beside a comp sheet - and the doc's speed bar: a
64-frame sheet of 8 x 8 cells, 1024 px a side, in under ten seconds.
Run: python -m pytest kit/test/python/test_vfx_comp_ops.py -q"""
import os
import sys
import time
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import comp as C  # noqa: E402

RAMP = [[0, [40, 6, 2]], [0.5, [255, 96, 20]], [1, [255, 240, 200]]]


def spec(comp, frames=16, grid=4, cell=128, post=None):
    return {"engine": "fx", "recipe": "comp", "frames": frames, "grid": grid, "cell": cell, "comp": comp,
            "post": {**C.POST, **(post or {})}}


def bake(comp, **kw):
    return C.frames_of(C.checked(spec(comp, **kw)))


def refused(comp, words, **kw):
    try:
        C.checked(spec(comp, **kw))
    except ValueError as e:
        assert words in str(e), str(e)
        return
    raise AssertionError(f"not refused: {comp}")


class Voronoi(unittest.TestCase):
    def test_cells_tile_and_are_zero_on_their_points(self):
        v = C.voronoi(96, 4, 3)
        self.assertAlmostEqual(float(v.min()), 0.0, places=6)
        self.assertAlmostEqual(float(v.max()), 1.0, places=6)
        inside = float(np.abs(v[:, 1:] - v[:, :-1]).mean())
        self.assertLess(float(np.abs(v[:, 0] - v[:, -1]).mean()), 2.5 * inside)   # it wraps: no seam
        self.assertLess(float(np.abs(v[0] - v[-1]).mean()), 2.5 * inside)
        self.assertTrue(np.array_equal(v, C.voronoi(96, 4, 3)))                     # a seed is a seed
        self.assertFalse(np.array_equal(v, C.voronoi(96, 4, 4)))

    def test_the_noise_block_takes_it_and_refuses_an_unknown_kind(self):
        f = bake({"tile": True, "noise": {"kind": "voronoi", "scale": 4, "octaves": 1, "pan": [1, 0]}, "ramp": RAMP})
        self.assertEqual(len(f), 16)
        refused({"tile": True, "noise": {"kind": "worley"}}, "noise.kind")


class Polar(unittest.TestCase):
    def test_a_pan_across_turns_it_round_the_middle(self):
        o = C.checked(spec({"shape": {"sdf": "disc", "radius": 0.45, "soft": 0.01},
                            "noise": {"scale": 3, "octaves": 2, "polar": True, "pan": [1, 0], "seed": 5, "contrast": 2}}, frames=4, grid=2))
        f = C.frames_of(o)
        a0, a1 = f[0][..., 3], f[1][..., 3]
        # a quarter of a loop later the picture is the first one turned a quarter round the middle
        self.assertLess(float(np.abs(np.rot90(a0, -1) - a1).mean()), 0.25 * float(np.abs(a0 - a1).mean()) + 0.01)

    def test_a_pan_out_moves_the_rings_outward_and_a_tile_is_refused(self):
        o = C.checked(spec({"shape": {"sdf": "disc", "radius": 0.45, "soft": 0.01},
                            "noise": {"scale": 6, "octaves": 1, "polar": True, "pan": [0, 1], "seed": 2}}, frames=16, grid=4))
        f = C.frames_of(o)
        n = o["cell"]
        yy, xx = np.mgrid[0:n, 0:n]
        r = np.hypot(xx + 0.5 - n / 2, yy + 0.5 - n / 2)
        ring = (r > 20) & (r < 40)
        self.assertGreater(float(np.abs(f[0][..., 3][ring] - f[2][..., 3][ring]).mean()), 0.02)  # it moves
        refused({"tile": True, "noise": {"polar": True}}, "not on a")


class Twirl(unittest.TestCase):
    def test_it_bends_inside_its_radius_and_nothing_beyond(self):
        plain = {"shape": {"sdf": "star", "inner": 0.15, "outer": 0.4, "points": 6, "soft": 0.01}}
        a = bake(plain, frames=1, grid=1)[0][..., 3]
        b = bake({**plain, "twirl": {"amount": 3, "radius": 0.3}}, frames=1, grid=1)[0][..., 3]
        n = a.shape[0]
        yy, xx = np.mgrid[0:n, 0:n]
        r = np.hypot(xx + 0.5 - n / 2, yy + 0.5 - n / 2) / n
        self.assertGreater(float(np.abs(a - b)[r < 0.25].mean()), 0.05)       # inside: turned
        self.assertLess(float(np.abs(a - b)[r > 0.31].max()), 1e-6)           # beyond the radius: untouched

    def test_nothing_turned_and_a_tile_are_refused(self):
        refused({"shape": {"sdf": "disc", "radius": 0.3}, "twirl": {"amount": 0}}, "no twirl")
        refused({"tile": True, "noise": {}, "twirl": {"amount": 2}}, "not on a")
        refused({"graph": {}, "twirl": {"amount": 2}}, "twirl")


class Rim(unittest.TestCase):
    def test_the_edge_takes_the_rim_colour_and_the_middle_keeps_its_own(self):
        f = bake({"shape": {"sdf": "disc", "radius": 0.35, "soft": 0.0}, "ramp": [[0, [255, 0, 0]], [1, [255, 0, 0]]],
                  "rim": {"width": 0.03, "color": [0, 255, 0]}}, frames=1, grid=1)[0]
        n = f.shape[0]
        yy, xx = np.mgrid[0:n, 0:n]
        r = np.hypot(xx + 0.5 - n / 2, yy + 0.5 - n / 2) / n
        edge = (r > 0.335) & (r < 0.345)
        mid = r < 0.25
        self.assertGreater(float(f[..., 1][edge].mean()), 0.7)                # green at the border
        self.assertLess(float(f[..., 1][mid].max()), 1e-6)                    # red inside
        self.assertTrue(np.array_equal(f[..., 3], bake({"shape": {"sdf": "disc", "radius": 0.35, "soft": 0.0}}, frames=1, grid=1)[0][..., 3]))

    def test_it_rides_an_erosion_front(self):
        f = bake({"loop": False, "shape": {"sdf": "disc", "radius": 0.4, "soft": 0.01, "falloff": 0.4},
                  "noise": {"scale": 4, "octaves": 2, "seed": 3}, "erode": {"from": 0.1, "to": 1, "soft": 0.04},
                  "ramp": [[0, [80, 0, 0]], [1, [80, 0, 0]]], "rim": {"width": 0.02, "color": [255, 255, 255]}}, frames=8, grid=[4, 2])
        for fr in f[1:-1]:
            a = fr[..., 3]
            hot = (fr[..., 1] > 0.6) & (a > 0.05)                              # where the rim's white shows
            self.assertGreater(int(hot.sum()), 10)
            inner = a > 0.95
            self.assertLess(float(fr[..., 1][inner].mean()) if inner.any() else 0.0, 0.6)

    def test_under_a_pixel_is_refused(self):
        refused({"shape": {"sdf": "disc", "radius": 0.3}, "rim": {"width": 0.002}}, "under a pixel", cell=128)


class Post(unittest.TestCase):
    def test_a_glow_mask_may_sit_beside_a_comp_sheet(self):
        C.checked(spec({"shape": {"sdf": "disc", "radius": 0.3}}, post={"emissive": True}))
        refused({"shape": {"sdf": "disc", "radius": 0.3}}, "emissive", post={"tonemap": True})


class Speed(unittest.TestCase):
    def test_sixty_four_frames_eight_by_eight_1024_px_in_under_ten_seconds(self):
        # the V3 doc's bar for the compositor (stage D.1): 64 frames, 8 x 8 cells, a 1024 px sheet, < 10 s
        o = C.checked(spec({"shape": {"sdf": "ring", "radius": 0.32, "width": 0.08, "soft": 0.02, "falloff": 0.05},
                            "noise": {"kind": "voronoi", "scale": 4, "octaves": 2, "polar": True, "pan": [0, 1], "seed": 2},
                            "warp": {"scale": 3, "amount": 0.03, "pan": [1, 0]}, "twirl": {"amount": 2, "radius": 0.45},
                            "ramp": RAMP, "rim": {"width": 0.015}}, frames=64, grid=8, cell=128))
        t0 = time.perf_counter()
        frames = C.frames_of(o)
        took = time.perf_counter() - t0
        self.assertEqual(len(frames), 64)
        self.assertLess(took, 10.0, f"{took:.1f} s")


if __name__ == "__main__":
    unittest.main()
