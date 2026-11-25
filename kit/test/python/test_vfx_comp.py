"""kit/vfx/comp.py - surface looks baked from a short stack - on stacks whose answer is known. What is proven is what
a sheet is trusted for: a shape is where its distance says, a pan moves the noise by exactly that much and a loop
comes back to its first frame, a warp bends and does not lose the shape, an erosion only removes, a ramp gives the
ramp's colours, each check catches the fault it is named for, and a sheet that fails leaves no frames."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import comp as C  # noqa: E402
import fxfinish  # noqa: E402

RAMP = [[0, [40, 6, 2]], [0.5, [255, 96, 20]], [1, [255, 240, 200]]]


def spec(comp, frames=16, grid=4, cell=128):
    return {"engine": "fx", "recipe": "comp", "frames": frames, "grid": grid, "cell": cell, "comp": comp, "post": dict(C.POST)}


def grid_uv(n):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    return (xx + 0.5) / n, (yy + 0.5) / n


def named(checks):
    return {c["name"]: c for c in checks}


class TestFields(unittest.TestCase):
    def test_noise_tiles_and_is_the_same_for_a_seed(self):
        for field in (C.periodic(64, 4, 2), C.fbm(64, 3, 4, 2)):
            self.assertGreaterEqual(float(field.min()), 0.0)
            self.assertLessEqual(float(field.max()), 1.0)
            inside = float(np.abs(field[:, 1:] - field[:, :-1]).mean())
            self.assertLess(float(np.abs(field[:, 0] - field[:, -1]).mean()), 2.5 * inside)
            self.assertLess(float(np.abs(field[0, :] - field[-1, :]).mean()), 2.5 * inside)
        self.assertTrue(np.array_equal(C.periodic(64, 4, 2), C.periodic(64, 4, 2)))
        self.assertFalse(np.allclose(C.periodic(64, 4, 2), C.periodic(64, 4, 3)))

    def test_sampling_wraps_or_holds_its_edge(self):
        f = np.arange(16, dtype=np.float64).reshape(4, 4)
        yy, xx = np.mgrid[0:4, 0:4].astype(np.float64)
        self.assertTrue(np.array_equal(C.sample(f, xx, yy), f))
        self.assertTrue(np.array_equal(C.sample(f, xx + 1, yy), np.roll(f, -1, axis=1)))       # a whole pixel = a roll
        self.assertTrue(np.allclose(C.sample(f, xx + 0.5, yy), (f + np.roll(f, -1, axis=1)) / 2))  # half = the average
        held = C.sample(f, xx + 10, yy, wrap=False)
        self.assertTrue(np.array_equal(held, np.repeat(f[:, -1:], 4, axis=1)))

    def test_a_shape_is_where_its_distance_says(self):
        u, v = grid_uv(200)
        c = (100, 100)
        d = C.sdf({"sdf": "disc", "radius": 0.3}, u, v)
        self.assertAlmostEqual(float(d[c]), -0.3, delta=0.01)
        self.assertAlmostEqual(float(d[100, 160]), 0.0, delta=0.01)
        self.assertAlmostEqual(float((d < 0).mean()), np.pi * 0.09, delta=0.005)
        r = C.sdf({"sdf": "ring", "radius": 0.3, "width": 0.1}, u, v)
        self.assertGreater(float(r[c]), 0)                       # the hole
        self.assertAlmostEqual(float(r[100, 160]), -0.05, delta=0.01)
        b = C.sdf({"sdf": "box", "size": [0.6, 0.2], "round": 0.0}, u, v)
        self.assertAlmostEqual(float((b < 0).mean()), 0.12, delta=0.006)
        s = C.sdf({"sdf": "streak", "length": 0.5, "width": 0.1, "angle": 0.0}, u, v)
        self.assertLess(float(s[100, 140]), 0)
        self.assertGreater(float(s[140, 100]), 0)                # across it: outside
        turned = C.sdf({"sdf": "streak", "length": 0.5, "width": 0.1, "angle": 90.0}, u, v)
        self.assertLess(float(turned[60, 100]), 0)               # turned a quarter: along v now
        star = C.sdf({"sdf": "star", "points": 5, "inner": 0.1, "outer": 0.4, "sharp": 2.0, "angle": 0.0}, u, v)
        self.assertLess(float(star[100, 170]), 0)                # a point reaches out along +u
        self.assertGreater(float(star[100, 30]), 0)              # between two points, the other way: only the inner radius
        up = C.sdf({"sdf": "star", "points": 5, "inner": 0.1, "outer": 0.4, "sharp": 2.0, "angle": 90.0}, u, v)
        self.assertLess(float(up[30, 100]), 0)                   # turned a quarter: that point is UP the picture now
        self.assertGreater(float(up[100, 170]), 0)
        fat = C.sdf({"sdf": "box", "size": [0.2, 0.6], "round": 0.3}, u, v)   # a corner rounder than half a side: held to half
        self.assertAlmostEqual(float((fat < 0)[:, 100].mean()), 0.6, delta=0.02)
        with self.assertRaises(ValueError):
            C.sdf({"sdf": "cloud"}, u, v)

    def test_blobs_join_into_one_shape(self):
        u, v = grid_uv(160)
        shape = {"sdf": "blobs", "count": 5, "radius": 0.1, "spread": 0.2, "k": 0.05, "seed": 4}
        d = C.sdf(shape, u, v)
        self.assertLess(float(d.min()), -0.05)
        self.assertGreater(float((d < 0).mean()), np.pi * 0.01 * 0.36)  # more than one of its smallest discs
        tight = C.sdf(dict(shape, k=0.005), u, v)
        self.assertGreater(float((d < 0).mean()), float((tight < 0).mean()))  # a wider reach fills the gaps between them

    def test_branches_fork_and_thin(self):
        shape = {"sdf": "branches", "origin": [0.5, 0.9], "angle": 90.0, "length": 0.3, "width": 0.04, "depth": 4, "forks": 2,
                 "spread": 35.0, "shrink": 0.7, "seed": 3, "trunks": 1}
        segs = C.branch_segments(shape)
        self.assertEqual(len(segs), 1 + 2 + 4 + 8)                     # a trunk, then every end forks in two, four deep
        self.assertEqual((round(segs[0][0], 6), round(segs[0][1], 6)), (0.5, 0.9))
        self.assertAlmostEqual(segs[0][3], 0.6, places=6)               # the trunk runs UP the picture by its length
        widths = sorted({round(s[4], 6) for s in segs}, reverse=True)
        self.assertEqual(len(widths), 4)
        self.assertTrue(all(abs(widths[i + 1] / widths[i] - 0.7) < 1e-6 for i in range(3)))   # each fork thinner
        ends = {(round(s[2], 6), round(s[3], 6)) for s in segs}
        self.assertTrue(all((round(s[0], 6), round(s[1], 6)) in ends for s in segs[1:]))       # every child starts where a parent ends
        u, v = grid_uv(160)
        d = C.sdf(shape, u, v)
        self.assertLess(float(d[int(0.75 * 160), 80]), 0)               # on the trunk
        self.assertGreater(float(d[int(0.95 * 160), 20]), 0)            # a bottom corner: outside
        self.assertTrue(np.array_equal(C.sdf(shape, u, v), d))          # the same seed, the same tree
        self.assertFalse(np.array_equal(C.sdf(dict(shape, seed=4), u, v), d))
        cracks = C.branch_segments(dict(shape, trunks=5, origin=[0.5, 0.5], depth=1))
        angles = sorted(round(np.degrees(np.arctan2(-(s[3] - s[1]), s[2] - s[0])) % 360) for s in cracks)
        self.assertEqual(angles, [18, 90, 162, 234, 306])               # five trunks, evenly round the point
        with self.assertRaises(ValueError):
            C.checked(spec({"shape": dict(shape, trunks=16, forks=3, depth=6)}))

    def test_halftone_dots_cover_what_the_alpha_says(self):
        for level in (0.1, 0.3, 0.5, 0.7):
            dots = C.halftone(np.full((240, 240), level), 12, 45.0)
            self.assertAlmostEqual(float(dots.mean()), level, delta=0.035, msg=str(level))
            self.assertGreater(float(((dots < 0.05) | (dots > 0.95)).mean()), 0.6)   # dots or paper, little in between
        self.assertEqual(float(C.halftone(np.zeros((64, 64)), 8, 45.0).max()), 0.0)
        self.assertGreater(float(C.halftone(np.ones((64, 64)), 8, 45.0).mean()), 0.97)
        # the screen has the period it was given: along the turned axis the picture repeats every `dot` px
        flat = C.halftone(np.full((128, 128), 0.4), 8, 0.0)
        self.assertTrue(np.allclose(flat[:, 8:], flat[:, :-8], atol=1e-6))
        self.assertFalse(np.allclose(flat[:, 4:], flat[:, :-4], atol=0.05))
        o = C.checked(spec({"shape": {"sdf": "disc", "radius": 0.35, "falloff": 0.35}, "noise": {"scale": 4, "pan": [1, 0]}, "halftone": {"dot": 8, "angle": 45}}))
        f = C.frames_of(o)[0][..., 3]
        self.assertGreater(float(((f < 0.05) | (f > 0.95)).mean()), 0.8)
        with self.assertRaises(ValueError):
            C.checked(spec({"shape": {"sdf": "disc", "radius": 0.3}, "halftone": {"dot": 1}}))

    def test_a_ramp_gives_its_own_colours(self):
        paint = C.ramp_of([[0, [0, 0, 0]], [0.5, [1, 0, 0]], [1, [1, 1, 1]]])
        got = paint(np.array([[0.0, 0.25, 0.5, 0.75, 1.0, 7.0]]))[0]
        self.assertTrue(np.allclose(got, [[0, 0, 0], [0.5, 0, 0], [1, 0, 0], [1, 0.5, 0.5], [1, 1, 1], [1, 1, 1]]))
        steps = C.ramp_of([[0, [0, 0, 0]], [1, [1, 1, 1]]], bands=3)(np.linspace(0, 1, 300)[None, :])[0, :, 0]
        self.assertEqual(sorted(set(np.round(steps, 6).tolist())), [0.0, 0.5, 1.0])


class TestSpec(unittest.TestCase):
    def test_a_good_spec_is_read(self):
        o = C.checked(spec(C.TEMPLATES["ring"]))
        self.assertEqual((o["frames"], o["cell"], o["loop"], o["tile"]), (16, 128, True, False))
        self.assertEqual(o["ramp"][0][1], [1.0, 1.0, 1.0])
        for kind in C.TEMPLATES:
            if kind != "map":
                C.checked(spec(C.TEMPLATES[kind]))

    def test_what_is_wrong_is_said(self):
        ring = {"sdf": "ring", "radius": 0.3, "width": 0.1}
        noise = {"scale": 4, "pan": [1, 0]}
        for comp, word in (
            ({"shape": ring, "glow": 1}, "does not read glow"),
            ({"shape": ring, "noise": {"scale": 4, "pan": [0.5, 0]}}, "WHOLE patterns"),
            ({"shape": ring, "erode": {"from": 0.1, "to": 0.9}}, '"loop": false'),
            ({"tile": True, "shape": ring, "noise": noise}, "has no shape"),
            ({"shape": ring, "source": {"texture": "x"}}, "not both"),
            ({"shape": {"sdf": "cloud"}}, "sdf"),
            ({"shape": {"sdf": "ring", "radius": 0.3}}, "shape.width"),
            ({"shape": ring, "ramp": [[0.5, [1, 1, 1]], [0.2, [0, 0, 0]]]}, "must rise"),
            ({"shape": ring, "ramp": [[0, [1, 1, 1]]]}, "two stops"),
            ({"shape": ring, "ramp": [[0, [1, 1]], [1, [0, 0, 0]]]}, "[r, g, b]"),
            ({"warp": {"scale": 3, "amount": 0.1, "pan": [1, 0]}}, "something to show"),
            ({"tile": True}, "something to show"),
            ({"source": {"texture": "../x"}}, "built texture key"),
            ({"shape": ring, "noise": {"scale": 400}}, "noise.scale"),
            ({"shape": ring, "noise": {"scale": float("nan")}}, "noise.scale"),
            ({"shape": dict(ring, sofft=0.1)}, '"shape" does not read sofft'),
            ({"shape": ring, "noise": {"scale": 4, "octave": 3}}, '"noise" does not read octave'),
            ({"shape": ring, "erode": {"start": 0.4, "end": 0.9}}, '"erode" does not read end, start'),
            ({"shape": ring, "halftone": {"size": 8}}, '"halftone" does not read size'),
            ({"loop": False, "shape": ring, "erode": {"at": 0.2, "from": 0.1, "to": 0.9}}, "not both"),
            ({"loop": False, "shape": ring, "erode": {"from": 0.9, "to": 0.2}}, '"to" must be above "from"'),
            ({"shape": ring, "bands": 3}, "there is no ramp"),
            ({"loop": "false", "shape": ring}, '"loop" is true or false'),
            ({"tile": 1, "noise": {"scale": 4}}, '"tile" is true or false'),
            ({"shape": {"sdf": "box", "size": [-0.2, 0.3]}}, "shape.size"),
            ({"tile": True, "noise": {"scale": 4, "pan": [1, 0]}, "halftone": {"dot": 8, "angle": 45}}, "stands square"),
            ({"tile": True, "noise": {"scale": 4, "pan": [1, 0]}, "halftone": {"dot": 7, "angle": 0}}, "stands square"),
        ):
            with self.assertRaises(ValueError, msg=str(comp)) as e:
                C.checked(spec(comp))
            self.assertIn(word, str(e.exception), comp)
        for bad in (spec({"shape": ring}, frames=12), spec({"shape": ring}, cell=100), spec({"shape": ring}, frames=64, grid=8, cell=256), {"comp": "x"}, "x",
                    spec({"shape": ring}, frames=9, grid=3), spec({"shape": ring}, frames=6, grid=[3, 2]), spec({"shape": ring}, frames=25, grid=5, cell=128)):
            with self.assertRaises(ValueError):
                C.checked(bad)
        # the finish is the pass-through, or the strip would not be the sheet
        for post in (None, {}, {"alpha": "coverage"}, {"alpha": "coverage", "tonemap": False, "border": 0.03}, {"alpha": "coverage", "tonemap": True, "border": 0}):
            bad = spec({"shape": ring})
            if post is None:
                bad.pop("post")
            else:
                bad["post"] = post
            with self.assertRaises(ValueError) as e:
                C.checked(bad)
            self.assertIn('its "post" must be', str(e.exception))
        # ... plus the looks drawn on a finished cell (a review leftover, stage 9: a comp sheet could not ask for edges)
        C.checked(dict(spec({"shape": ring}), post=dict(C.POST, edges={"threshold": 0.05}, aberration={"amount": 0.02})))
        with self.assertRaises(ValueError):
            C.checked(dict(spec({"shape": ring}), post=dict(C.POST, edges={}, border=0.05)))
        C.checked(spec({"tile": True, "noise": {"scale": 4, "pan": [1, 0]}, "halftone": {"dot": 8, "angle": 90}}))   # a square screen that fits
        # colours are 0-255, as everywhere in the kit's specs: [1, 1, 1] is near black, never white
        self.assertEqual(C.colour([255, 0, 0], "c"), [1.0, 0.0, 0.0])
        self.assertAlmostEqual(C.colour([1, 1, 1], "c")[0], 1 / 255.0)
        self.assertAlmostEqual(C.colour([2, 2, 2], "c")[0], 2 / 255.0)
        C.checked(spec({"shape": ring}, frames=8, grid=[4, 2]))
        C.checked(spec({"loop": False, "shape": ring, "noise": {"scale": 4, "pan": [0.5, 0]}}))  # a one-shot may pan by a part


class TestStack(unittest.TestCase):
    def test_a_pan_moves_the_noise_by_exactly_that_much(self):
        o = C.checked(spec({"tile": True, "noise": {"scale": 4, "octaves": 2, "pan": [1, 0], "seed": 3}}, frames=4, grid=2, cell=64))
        f = C.frames_of(o)
        for k in range(4):
            self.assertTrue(np.allclose(f[k][..., 3], np.roll(f[0][..., 3], k * 16, axis=1), atol=1e-9), k)
        up = C.frames_of(C.checked(spec({"tile": True, "noise": {"scale": 4, "octaves": 2, "pan": [0, 2], "seed": 3}}, frames=4, grid=2, cell=64)))
        self.assertTrue(np.allclose(up[1][..., 3], np.roll(up[0][..., 3], 32, axis=0), atol=1e-9))

    def test_a_loop_comes_back_to_its_first_frame(self):
        comp = dict(C.TEMPLATES["ring"])
        o = C.checked(spec(comp))
        f = C.frames_of(o)
        steps = [float(np.abs(f[i + 1] - f[i]).mean()) for i in range(15)]
        self.assertLess(float(np.abs(f[0] - f[-1]).mean()), 1.5 * float(np.median(steps)))
        again = C.frames_of(C.checked(spec(comp, frames=64, grid=8, cell=128)))
        self.assertTrue(np.allclose(again[0], f[0]))             # frame 0 does not depend on how many frames there are

    def test_a_warp_bends_the_shape_and_keeps_it(self):
        ring = {"sdf": "ring", "radius": 0.3, "width": 0.1, "soft": 0.0}
        plain = C.frames_of(C.checked(spec({"shape": ring, "warp": {"scale": 3, "amount": 0.0, "pan": [1, 0]}}, frames=4, grid=2)))
        bent = C.frames_of(C.checked(spec({"shape": ring, "warp": {"scale": 3, "amount": 0.04, "pan": [1, 0]}}, frames=4, grid=2)))
        self.assertTrue(np.array_equal(plain[0], plain[1]))      # no amount: no distortion, nothing moves
        self.assertGreater(float(np.abs(bent[0][..., 3] - plain[0][..., 3]).mean()), 0.01)
        self.assertGreater(float(np.abs(bent[1][..., 3] - bent[0][..., 3]).mean()), 0.005)
        area = float(plain[0][..., 3].mean())
        self.assertAlmostEqual(float(bent[0][..., 3].mean()), area, delta=0.15 * area)

    def test_an_erosion_only_removes_and_ends_empty(self):
        comp = {"loop": False, "shape": {"sdf": "disc", "radius": 0.35, "soft": 0.0},
                "noise": {"scale": 5, "octaves": 2, "pan": [0, 0], "seed": 2}, "erode": {"from": 0.0, "to": 1, "soft": 0.0}}
        f = C.frames_of(C.checked(spec(comp)))
        cover = [float((x[..., 3] > 0.02).mean()) for x in f]
        self.assertTrue(all(cover[i + 1] <= cover[i] + 1e-9 for i in range(15)), cover)
        self.assertGreater(cover[0], 0.3)
        self.assertEqual(cover[-1], 0.0)
        self.assertGreater(cover[-2], 0.0)   # 1 = just clears: the frame before the last still holds some
        soft = C.frames_of(C.checked(spec(dict(comp, noise=dict(comp["noise"], pan=[0.7, 0.3]), erode={"from": 0.0, "to": 1, "soft": 0.1}))))
        self.assertEqual(float(soft[-1][..., 3].max()), 0.0)     # ... with a soft front and a noise that pans, too
        self.assertGreater(float(soft[-2][..., 3].max()), 0.0)
        self.assertTrue(all(float((f[i + 1][..., 3] - f[i][..., 3]).max()) <= 1e-9 for i in range(15)))  # no pixel comes back

    def test_an_erosion_removes_even_shares_of_the_area_and_the_packer_takes_every_one_shot(self):
        """(a review, 2026-11-13: measured against the value, a one-shot's last frames held a few pixels and 27 of 86
        sheets that passed here were refused by the packer as "not moving")"""
        ring = {"sdf": "ring", "radius": 0.3, "width": 0.1, "soft": 0.02}
        for shape, tile in ((ring, False), ({"sdf": "blobs", "radius": 0.12, "count": 6, "spread": 0.18, "falloff": 0.1}, False), (None, True)):
            for frames, grid, cell in ((16, 4, 128), (64, 8, 128)):
                for start in (0.0, 0.15, 0.5):
                    for soft in (0.0, 0.04, 0.1):
                        comp = {"loop": False, "tile": tile, "noise": {"scale": 5, "pan": [0.5, 0.25], "seed": 3}, "erode": {"from": start, "to": 1, "soft": soft}}
                        if shape:
                            comp["shape"] = shape
                        o = C.checked(spec(comp, frames=frames, grid=grid, cell=cell))
                        f = C.frames_of(o)
                        what = (shape and shape["sdf"], frames, start, soft)
                        self.assertEqual(float(f[-1][..., 3].max()), 0.0, what)
                        if [c["name"] for c in C.check(f, o) if not c["ok"]]:
                            continue                                    # (refused HERE, with a reason: never by the packer later)
                        change = min(float(np.abs(f[i + 1][..., 3] - f[i][..., 3]).mean()) for i in range(frames - 1))
                        self.assertGreater(change, 0.0008, what)       # the packer's own limit, on every pair
                        cover = [float((x[..., 3] > 0.5).mean()) for x in f]
                        self.assertGreater(cover[-2], 0.0, what)       # the frame before the last still holds its share
        # the shares are even: with a hard cut each frame removes (to - from) / (frames - 1) of the covered area
        o = C.checked(spec({"loop": False, "tile": True, "noise": {"scale": 5, "pan": [0, 0], "seed": 3}, "erode": {"from": 0.0, "to": 1, "soft": 0.0}}))
        cover = [float((x[..., 3] > 0.5).mean()) for x in C.frames_of(o)]
        steps = [cover[i] - cover[i + 1] for i in range(15)]
        self.assertAlmostEqual(min(steps), 1 / 15, delta=0.004)
        self.assertAlmostEqual(max(steps), 1 / 15, delta=0.004)
        # a fixed share: "at": 0.3 cuts the faintest 30 % of the look away, in every frame of the loop
        o = C.checked(spec({"tile": True, "noise": {"scale": 5, "pan": [1, 0], "seed": 3}, "erode": {"at": 0.3, "soft": 0.0}}))
        for x in C.frames_of(o)[::5]:
            self.assertAlmostEqual(float((x[..., 3] > 0.5).mean()), 0.7, delta=0.01)

    def test_a_branching_shape_is_measured_once(self):
        import time
        shape = {"sdf": "branches", "length": 0.2, "width": 0.03, "depth": 6, "forks": 2, "trunks": 2, "origin": [0.5, 0.5]}
        o = C.checked(spec({"shape": shape, "warp": {"scale": 3, "amount": 0.01, "pan": [1, 0]}}, cell=256))
        t0 = time.perf_counter()
        f = C.frames_of(o)
        self.assertLess(time.perf_counter() - t0, 3.0)                  # (it took 7 s when every frame measured it again)
        self.assertGreater(float(np.abs(f[1][..., 3] - f[0][..., 3]).mean()), 0.0005)
        with self.assertRaises(ValueError) as e:
            C.checked(spec({"shape": dict(shape, depth=6, forks=3, trunks=2)}))
        self.assertIn("segments", str(e.exception))

    def test_the_colours_are_the_ramps(self):
        comp = {"shape": {"sdf": "disc", "radius": 0.35, "soft": 0.0, "falloff": 0.35}, "ramp": RAMP}
        f = C.frames_of(C.checked(spec(comp, frames=1, grid=1)))[0]
        self.assertTrue(np.allclose(f[64, 64, :3], np.array(RAMP[2][1]) / 255.0, atol=0.03))   # the centre: the ramp's top
        edge = f[64, 64 + 43]                                                                    # near the rim: its bottom
        self.assertTrue(np.allclose(edge[:3], np.array(RAMP[0][1]) / 255.0, atol=0.12), edge)
        banded = C.frames_of(C.checked(spec(dict(comp, bands=3), frames=1, grid=1)))[0]
        inside = banded[..., 3] > 0.02
        colours = {tuple(np.round(c, 3)) for c in banded[..., :3][inside]}
        self.assertEqual(len(colours), 3)                         # three flat steps, each one of the ramp's stops
        for c in colours:
            self.assertTrue(any(np.allclose(c, np.array(s[1]) / 255.0, atol=0.01) for s in RAMP), c)

    def test_a_source_is_mapped_through_the_ramp(self):
        grey = np.zeros((128, 128))
        grey[:, 64:] = 1.0
        o = C.checked(spec({"tile": True, "source": {"texture": "g"}, "ramp": [[0, [0, 0, 255]], [1, [255, 0, 0]]]}, frames=1, grid=1))
        f = C.frames_of(o, grey)[0]
        self.assertTrue(np.allclose(f[10, 100, :3], [1, 0, 0]))
        self.assertTrue(np.allclose(f[10, 20, :3], [0, 0, 1]))
        self.assertEqual((float(f[10, 100, 3]), float(f[10, 20, 3])), (1.0, 0.0))


class TestChecks(unittest.TestCase):
    def failed(self, comp, **kw):
        o = C.checked(spec(comp, **kw))
        return [c["name"] for c in C.check(C.frames_of(o), o) if not c["ok"]]

    def test_the_starters_pass(self):
        for kind in ("ring", "skin", "blobs", "branches"):
            self.assertEqual(self.failed(C.TEMPLATES[kind]), [], kind)

    def test_each_check_catches_its_fault(self):
        ring = {"sdf": "ring", "radius": 0.3, "width": 0.1}
        self.assertEqual(self.failed({"shape": {"sdf": "disc", "radius": 0.02}, "noise": {"scale": 4, "pan": [1, 0]}}), ["fills", "packs"])
        self.assertIn("moves", self.failed({"shape": ring, "noise": {"scale": 4, "pan": [0, 0]}}))
        self.assertIn("clear", self.failed({"shape": {"sdf": "disc", "radius": 0.6}, "noise": {"scale": 4, "pan": [1, 0]}}))
        self.assertIn("ends", self.failed({"loop": False, "shape": ring, "noise": {"scale": 4, "pan": [0.3, 0]}, "erode": {"from": 0.0, "to": 0.3}}))
        # a shape of ONE value has no faintest part to cut first: its erosion would be one pop, and is refused
        self.assertIn("moves", self.failed({"loop": False, "shape": dict(ring, soft=0.0), "erode": {"from": 0.0, "to": 1}}))
        # colours that move under an alpha that does not: the packer reads alpha alone and would refuse the sheet
        lava = {"tile": True, "noise": {"scale": 4, "pan": [1, 0], "contrast": 0.3, "mix": 0.3}, "ramp": RAMP}
        o = C.checked(spec(lava))
        frames = [np.dstack([f[..., :3], np.ones(f.shape[:2])]) for f in C.frames_of(o)]   # (the same look, fully opaque)
        got = {c["name"]: c["ok"] for c in C.check(frames, o)}
        self.assertEqual((got["moves"], got["packs"]), (True, False))
        self.assertIn("ONE frame scrolled by its layer", next(c["fix"] for c in C.check(frames, o) if c["name"] == "packs"))
        # a loop that does not come back, and a tile that does not wrap: hand-made frames through check()
        o = C.checked(spec(C.TEMPLATES["skin"]))
        f = C.frames_of(o)
        self.assertNotIn("loops", [c["name"] for c in C.check(f, o) if not c["ok"]])
        # a loop stopped half way round does not come back (told on a look that changes slowly: when every frame is
        # already a new picture, the seam is no harder than any step and there is no pop to tell)
        slow = C.checked(spec({"tile": True, "noise": {"scale": 2, "octaves": 1, "pan": [1, 0], "seed": 4}}, frames=64, grid=8, cell=128))
        g = C.frames_of(slow)
        self.assertNotIn("loops", [c["name"] for c in C.check(g, slow) if not c["ok"]])
        self.assertIn("loops", [c["name"] for c in C.check(g[:33], slow) if not c["ok"]])
        ramp = np.linspace(0, 1, 128)[None, :].repeat(128, 0)
        wipe = [np.dstack([np.ones((128, 128, 3)), np.roll(ramp, 0, axis=1) * (0.5 + 0.03 * k)]) for k in range(16)]
        self.assertIn("tiles", [c["name"] for c in C.check(wipe, o) if not c["ok"]])
        # a seam under fine grain (a review: grain steps as hard between any two columns as a 23 % jump at the seam,
        # and the check, read off the raw frames, passed it): read low-passed, the jump shows
        rng = np.random.default_rng(3)
        grainy = [np.dstack([np.ones((128, 128, 3)), np.clip(0.75 * rng.random((128, 128)) + 0.25 * ramp + 0.002 * k, 0, 1)]) for k in range(16)]
        self.assertIn("tiles", [c["name"] for c in C.check(grainy, o) if not c["ok"]])
        # ... and colours that do not wrap under an alpha that does
        tinted = [np.dstack([ramp, ramp, ramp, np.full((128, 128), 0.5 + 0.01 * k)]) for k in range(16)]
        self.assertIn("tiles", [c["name"] for c in C.check(tinted, o) if not c["ok"]])


class TestCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kit_comp_")
        self.built, self.specs, self.frames, self.look = (os.path.join(self.tmp, d) for d in ("built", "specs", "frames", "look"))
        self.dirs = ["--textures-dir", self.built, "--specs-dir", self.specs, "--frames-dir", self.frames, "--look-dir", self.look]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_tool(self, *argv, dirs=True):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = C.main(list(argv) + (self.dirs if dirs else []))
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1, lines)
        return code, json.loads(lines[0])

    def write(self, key, comp, **kw):
        os.makedirs(self.specs, exist_ok=True)
        json.dump(spec(comp, **kw), open(os.path.join(self.specs, f"{key}.json"), "w"))

    def test_a_starter_is_written_baked_and_never_written_over(self):
        code, v = self.run_tool("ring_a", "--new", "ring")
        self.assertEqual(code, 0, v)
        self.assertLess(v["seconds"], 5)                          # "in seconds"
        self.assertEqual(len([f for f in os.listdir(os.path.join(self.frames, "ring_a")) if f.endswith(".npy")]), 16)
        self.assertTrue(os.path.isfile(os.path.join(self.look, "ring_a_strip.png")))
        made = json.load(open(os.path.join(self.specs, "ring_a.json"), encoding="utf-8"))
        self.assertEqual((made["recipe"], made["post"]), ("comp", C.POST))
        self.assertTrue(all(s[1] == [255, 255, 255] for s in made["comp"]["ramp"]))   # a starter brings no look of its own
        code, v = self.run_tool("ring_a", "--new", "skin")
        self.assertEqual(code, 1)
        self.assertIn("there already", v["summary"])
        self.assertEqual(json.load(open(os.path.join(self.specs, "ring_a.json"), encoding="utf-8")), made)
        code, v = self.run_tool("m", "--new", "map")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.isdir(os.path.join(self.frames, "m")))   # a map waits for its source to be named

    def test_the_packer_takes_a_shape_and_a_tile(self):
        self.write("burn", {"loop": False, "shape": {"sdf": "ring", "radius": 0.3, "width": 0.1, "falloff": 0.03},
                            "noise": {"scale": 5, "pan": [0.5, 0], "seed": 3}, "erode": {"from": 0.1, "to": 1}, "ramp": RAMP})
        self.write("skin", dict(C.TEMPLATES["skin"], ramp=RAMP))
        for key, size in (("burn", (512, 512)), ("skin", (512, 512))):
            code, v = self.run_tool(key)
            self.assertEqual(code, 0, v)
            made = json.load(open(os.path.join(self.specs, f"{key}.json"), encoding="utf-8"))
            img, grid, clipped, change, n = fxfinish.build(key, made, self.frames)
            failed = [c["name"] for c in fxfinish.check(img, grid, clipped, change, n, False, want=16) if not c["ok"] and c["severity"] == "error"]
            self.assertEqual((failed, img.size, tuple(grid)), ([], size, (4, 4)), key)
        # the packed colours are the ramp's (straight, not darkened by their own alpha)
        sheet = np.asarray(img, dtype=np.float64) / 255.0
        first = sheet[:128, :128]
        solid = first[..., 3] > 0.9
        self.assertTrue(solid.any())
        lo, hi = np.array(RAMP[0][1]) / 255.0, np.array(RAMP[2][1]) / 255.0
        self.assertTrue(np.all(first[..., 0][solid] >= lo[0] - 0.03))
        self.assertTrue(np.all(first[..., 0][solid] <= hi[0] + 0.03))

    def test_a_sheet_that_fails_leaves_no_frames(self):
        self.write("still", {"shape": {"sdf": "ring", "radius": 0.3, "width": 0.1}, "noise": {"scale": 4, "pan": [0, 0]}})
        code, v = self.run_tool("still")
        self.assertEqual(code, 1)
        self.assertIn("two frames show the same picture", v["summary"])
        self.assertFalse(os.path.isdir(os.path.join(self.frames, "still")))
        self.assertTrue(os.path.isfile(os.path.join(self.look, "still_strip.png")))   # the look is still shown

    def test_the_command_never_throws(self):
        self.write("odd", {"shape": {"sdf": "ring", "radius": 0.3, "width": 0.1}, "glow": 2})
        os.makedirs(self.specs, exist_ok=True)
        open(os.path.join(self.specs, "broken.json"), "w").write("{")
        json.dump({"engine": "fx", "recipe": "import"}, open(os.path.join(self.specs, "other.json"), "w"))
        self.write("lost", {"tile": True, "source": {"texture": "not_built"}, "ramp": RAMP})
        json.dump({"engine": "blender", "recipe": "volume"}, open(os.path.join(self.specs, "vol.json"), "w"))
        self.write("of_vol", {"tile": True, "source": {"texture": "vol"}, "ramp": RAMP})
        json.dump({"engine": "fx", "recipe": "dissolve"}, open(os.path.join(self.specs, "dz.json"), "w"))
        self.write("of_dz", {"tile": True, "source": {"texture": "dz"}, "ramp": RAMP})
        for argv in ([], ["--new", "ring"], ["Bad-Key"], ["nothing_here"], ["x", "--new"], ["x", "--new", "cloud"], ["x", "--bogus", "1"],
                     ["odd"], ["broken"], ["other"], ["lost"], ["of_vol"], ["of_dz"]):
            code, v = self.run_tool(*argv)
            self.assertEqual((code, v["status"]), (1, "fail"), argv)

    def test_the_chain_in_its_order(self):
        """kit vfx: comp (plain) -> the packer's general pass -> comp (mapped, packs its own) -> dissolve (packs its
        own): a plain skin, a skin mapped from it, and that one breaking up - all three from ONE run"""
        import subprocess
        sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
        import dissolve as D
        finish = os.path.join(HERE, "..", "..", "vfx", "fxfinish.py")
        registry = os.path.join(self.tmp, "_textures.json")
        json.dump({"_help": "test"}, open(registry, "w"))
        self.write("skin", C.TEMPLATES["skin"], cell=256)
        self.write("hot", {"tile": True, "source": {"texture": "skin"}, "warp": {"scale": 3, "amount": 0.03, "pan": [1, 0]}, "ramp": RAMP}, cell=256)
        os.makedirs(self.specs, exist_ok=True)
        json.dump({"engine": "fx", "recipe": "dissolve", "frames": 16, "grid": 4, "cell": 256, "from": "hot",
                   "dissolve": {"pattern": "patches", "soft": 0.08, "density": 0.35, "curve": 1.0, "seed": 7, "scale": 5.0}, "post": dict(C.POST)},
                  open(os.path.join(self.specs, "hot_dz.json"), "w"))
        base = ["--specs", self.specs, "--out", self.frames, "--textures-dir", self.built]

        def tool(mod, *argv):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = mod.main(list(argv))
            return code, json.loads(buf.getvalue().strip().splitlines()[-1])

        code, v = tool(C, *base, "--plain")
        self.assertEqual((code, len(v["baked"])), (0, 1), v)
        r = subprocess.run([sys.executable, finish, "--specs", self.specs, "--frames", self.frames, "--out", self.built, "--registry", registry, "--skip-derived"],
                           capture_output=True, text=True, check=False)
        general = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual((general["status"], [t["name"] for t in general["textures"]]), ("pass", ["skin"]), general["summary"])
        code, v = tool(C, *base, "--mapped", "--registry", registry, "--pack", finish)
        self.assertEqual((code, v["packed"]), (0, ["hot"]), v)
        code, v = tool(D, *base, "--registry", registry, "--pack", finish)
        self.assertEqual((code, v["packed"]), (0, ["hot_dz"]), v)
        reg = json.load(open(registry, encoding="utf-8"))
        self.assertEqual(sorted(k for k in reg if not k.startswith("_")), ["hot", "hot_dz", "skin"])
        hot = np.asarray(Image.open(os.path.join(self.built, "hot.png")).convert("RGBA"), dtype=np.float64)[:256, :256] / 255.0
        dz = np.asarray(Image.open(os.path.join(self.built, "hot_dz.png")).convert("RGBA"), dtype=np.float64)[:256, :256] / 255.0
        self.assertLess(float(np.abs(dz[..., 3] - hot[..., 3]).max()), 0.03)     # the dissolve's first cell IS this run's mapped skin
        # a second run with nothing changed bakes nothing and still packs
        self.assertEqual(tool(C, *base, "--plain")[1]["baked"], [])
        self.assertEqual(tool(C, *base, "--mapped", "--registry", registry, "--pack", finish)[1]["baked"], [])
        self.assertEqual(tool(D, *base, "--registry", registry, "--pack", finish)[1]["baked"], [])

    def test_the_build_step(self):
        self.write("a", C.TEMPLATES["ring"])
        from PIL import Image as I
        os.makedirs(self.built)
        grey = np.zeros((64, 64, 4), dtype=np.uint8)   # a grey wave that TILES (a tile's source must)
        grey[..., :3] = (127.5 + 127.5 * np.cos(2 * np.pi * (np.arange(64) + 0.5) / 64))[None, :, None].astype(np.uint8)
        grey[..., 3] = 255
        I.fromarray(grey, "RGBA").save(os.path.join(self.built, "g.png"))
        self.write("b", {"tile": True, "source": {"texture": "g"}, "warp": {"scale": 3, "amount": 0.05, "pan": [1, 0]}, "ramp": RAMP})
        step = ["--specs", self.specs, "--out", self.frames, "--textures-dir", self.built]
        # the plain stacks are baked before the packer, the mapped ones after it: each step takes its own
        code, v = self.run_tool(*step, "--plain", dirs=False)
        self.assertEqual((code, len(v["baked"])), (0, 1), v)
        self.assertTrue(os.path.isdir(os.path.join(self.frames, "a")) and not os.path.isdir(os.path.join(self.frames, "b")))
        code, v = self.run_tool(*step, "--mapped", dirs=False)
        self.assertEqual((code, len(v["baked"])), (0, 1), v)
        shutil.rmtree(os.path.join(self.frames, "a"))
        shutil.rmtree(os.path.join(self.frames, "b"))
        code, v = self.run_tool(*step, dirs=False)
        self.assertEqual((code, len(v["baked"])), (0, 2), v)
        code, v = self.run_tool(*step, dirs=False)
        self.assertEqual((code, v["baked"]), (0, []))
        first = np.load(os.path.join(self.frames, "b", "000.npy"))
        grey[..., :3] = 255 - grey[..., :3]
        I.fromarray(grey, "RGBA").save(os.path.join(self.built, "g.png"))    # the source texture changed
        code, v = self.run_tool(*step, dirs=False)
        self.assertEqual((code, len(v["baked"])), (0, 1))
        self.assertFalse(np.array_equal(first, np.load(os.path.join(self.frames, "b", "000.npy"))))
        # the mapped step packs its own sheets (the general pass of the packer leaves them alone)
        finish = os.path.join(HERE, "..", "..", "vfx", "fxfinish.py")
        registry = os.path.join(self.tmp, "_textures.json")
        json.dump({"_help": "test"}, open(registry, "w"))
        code, v = self.run_tool(*step, "--mapped", "--registry", registry, "--pack", finish, dirs=False)
        self.assertEqual((code, v["packed"]), (0, ["b"]), v)
        self.assertTrue(os.path.isfile(os.path.join(self.built, "b.png")))
        self.assertEqual(json.load(open(registry, encoding="utf-8"))["b"]["grid"], 4)
        self.assertTrue(fxfinish.derived(json.load(open(os.path.join(self.specs, "b.json"), encoding="utf-8"))))
        self.assertFalse(fxfinish.derived(json.load(open(os.path.join(self.specs, "a.json"), encoding="utf-8"))))
        self.write("c", {"shape": {"sdf": "ring", "radius": 0.3, "width": 0.1}, "glow": 2})
        code, v = self.run_tool(*step, dirs=False)
        self.assertEqual(code, 1)
        self.assertIn("does not read glow", v["summary"])


if __name__ == "__main__":
    unittest.main()
