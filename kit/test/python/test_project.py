"""kit/blender/rbx_project.py: the arithmetic behind a.project / a.decal — which way each picture's camera looks, the
trace frame <-> picture pixels, the depth test, picture sampling and its outline, whether a picture is where its trace
says, the perspective straightening of a decal, and how pictures blend. Plain numpy (the Blender side is proven by the
project_ok / project_misaligned fixtures)."""

import json
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_project as P  # noqa: E402


def box_trace(hr=0.25, front="right", x0=40.0, y1=115.0, length=360.0):
    return {"front": front, "height_ratio": hr, "holes": [], "outline": [[0, 0], [1, 0], [1, hr], [0, hr]],
            "frame": {"x0": x0, "y1": y1, "length_px": length}}


def layer(**kw):
    out = {"kind": "project", "feather": 3.0, "flatten": 0.0, "mix": 1.0, "facing": (0.25, 0.6), "mirror": False,
           "view": "side", "front": "right"}
    out.update(kw)
    return out


class TestCameras(unittest.TestCase):
    def test_every_camera_is_right_handed(self):
        for (view, front) in P._BASIS:
            d, r, u = P.basis(view, front)
            np.testing.assert_allclose(np.cross(r, u), d, atol=1e-12)

    def test_a_side_picture_with_the_front_on_the_right_sees_the_right_side(self):
        d, r, u = P.basis("side", "right")
        np.testing.assert_array_equal(d, (1, 0, 0))  # from +X (Roblox right)
        np.testing.assert_array_equal(r, (0, 1, 0))  # the picture's right = Blender +Y = Roblox front (-Z)
        d, r, _u = P.basis("side", "left")
        np.testing.assert_array_equal(d, (-1, 0, 0))  # the left side, its front on the picture's left
        np.testing.assert_array_equal(r, (0, -1, 0))

    def test_from_above_with_the_front_right_the_models_left_is_up(self):
        d, r, u = P.basis("top", "right")
        np.testing.assert_array_equal(d, (0, 0, 1))
        np.testing.assert_array_equal(u, (-1, 0, 0))

    def test_a_front_picture_ignores_its_traces_front_flag(self):
        for a, b in zip(P.basis("front", "left"), P.basis("front", "right")):
            np.testing.assert_array_equal(a, b)

    def test_an_unknown_view_is_refused(self):
        with self.assertRaises(ValueError):
            P.basis("bottom")


class TestFrame(unittest.TestCase):
    def test_frame_round_trip(self):
        fr = P.frame(box_trace())
        X, Y = P.to_picture(np.array([0.0, 1.0, 0.5]), np.array([0.0, 1.0, 0.5]), fr)
        np.testing.assert_allclose(X, [40, 400, 220])
        np.testing.assert_allclose(Y, [115, 25, 70])
        a, b = P.from_picture(X, Y, fr)
        np.testing.assert_allclose(a, [0, 1, 0.5])
        np.testing.assert_allclose(b, [0, 1, 0.5])

    def test_a_trace_without_a_frame_cannot_be_projected(self):
        t = box_trace()
        t["frame"] = None
        with self.assertRaises(ValueError):
            P.frame(t)

    def test_design_units_turn_with_the_front(self):
        self.assertEqual(P.design_to_ab(0.2, 0.1, "right", 0.25), (0.2, 0.4))
        self.assertEqual(P.design_to_ab(0.2, 0.1, "left", 0.25), (0.8, 0.4))

    def test_the_silhouette_box_is_the_frame(self):
        bas = P.basis("side", "right")
        pts = np.array([[0, -2, 0], [0, 2, 1], [0.3, 0, 0.5]], float)  # Blender: y = length, z = up
        ext = P.extents(pts, bas)
        a, b = P.to_ab(pts, bas, ext)
        np.testing.assert_allclose(a, [0, 1, 0.5])
        np.testing.assert_allclose(b, [0, 1, 0.5])


class TestDepth(unittest.TestCase):
    def setUp(self):
        self.bas = P.basis("side", "right")  # dir +X, right +Y, up +Z
        self.geom = P.view_geometry((-1.0, 1.0, 0.0, 1.0), (-1.0, 1.0), 200)
        g = self.geom
        jj, ii = np.meshgrid(np.arange(g["w"]) + 0.5, np.arange(g["h"]) + 0.5)
        y = g["r0"] + jj * g["px"]
        # a back wall at x = 0 everywhere, a front plate at x = 0.5 over y < 0
        self.depth = np.where(y < 0, 0.5, 0.0)
        self.hit = np.ones_like(self.depth, bool)

    def test_square_pixels_frame_the_box(self):
        g = self.geom
        self.assertLessEqual(g["r0"], -1.0)
        self.assertGreaterEqual(g["r0"] + g["w"] * g["px"], 1.0)
        self.assertLessEqual(g["u0"], 0.0)
        self.assertGreaterEqual(g["u0"] + g["h"] * g["px"], 1.0)
        self.assertEqual(max(g["w"], g["h"]), 200)

    def test_every_map_is_checked_at_twice_its_size(self):
        # (card a2ym: a 4096 map was checked at 1x - a fringe of the picture's colour along faces nobody sees)
        self.assertEqual([P.visibility_res(t) for t in (256, 512, 1024, 2048, 4096)], [1024, 1024, 2048, 4096, 8192])

    def test_what_is_behind_the_plate_is_not_seen(self):
        P_ = np.array([[0.0, -0.5, 0.5], [0.0, 0.5, 0.5], [0.5, -0.5, 0.5]])
        N = np.array([[1.0, 0, 0]] * 3)
        vis = P.visible(P_, N, self.bas, self.depth, self.hit, self.geom, tol=1e-4)
        self.assertEqual(vis.tolist(), [False, True, True])  # the wall behind it / the wall beside it / the plate

    def test_no_surface_there_means_seen(self):
        vis = P.visible(np.array([[0.0, 0.5, 0.5]]), np.array([[1.0, 0, 0]]), self.bas, self.depth,
                        np.zeros_like(self.hit), self.geom, tol=1e-4)
        self.assertTrue(vis[0])

    def test_facing_ramp(self):
        r = P.ramp(np.array([0.0, 0.25, 0.425, 0.6, 1.0]), 0.25, 0.6)
        np.testing.assert_allclose(r, [0, 0, 0.5, 1, 1], atol=1e-9)


class TestPictures(unittest.TestCase):
    def test_bilinear_reads_pixel_centres(self):
        img = np.arange(5, dtype=float)[None, :].repeat(3, 0)  # value = column
        np.testing.assert_allclose(P.bilinear(img, [0.5, 1.0, 2.5, 4.5], [1.5] * 4), [0, 0.5, 2, 4])
        np.testing.assert_allclose(P.bilinear(img, [-3, 99], [0, 0]), [0, 4])  # clamped

    def test_fill_rings_cuts_holes(self):
        m = P.fill_rings([[(0, 0), (10, 0), (10, 10), (0, 10)], [(3, 3), (7, 3), (7, 7), (3, 7)]], 12, 12)
        self.assertEqual(int(m.sum()), 100 - 16)
        self.assertFalse(m[5, 5])
        self.assertTrue(m[1, 1])

    def test_inside_distance(self):
        m = np.zeros((12, 12), bool)
        m[1:11, 1:11] = True
        d = P.inside_distance(m, 10)
        self.assertEqual(d[1, 1], 1)
        self.assertEqual(d[5, 5], 5)
        self.assertEqual(d[0, 0], 0)

    def test_fill_outside_takes_the_inside_colour(self):
        img = np.zeros((5, 5, 3), np.float32)
        m = np.zeros((5, 5), bool)
        m[2, 2] = True
        img[2, 2] = (1, 0.5, 0.25)
        out = P.fill_outside(img, m, steps=2)
        np.testing.assert_allclose(out[0, 0], (1, 0.5, 0.25))

    def test_object_mask_backdrop_and_alpha(self):
        pic = np.ones((20, 30, 4), np.float32)
        pic[5:15, 10:20, :3] = (0.2, 0.3, 0.9)
        self.assertEqual(int(P.object_mask(pic).sum()), 100)
        self.assertEqual(P.object_mask(pic, region=(5, 10, 10, 20)).shape, (5, 10))
        pic[..., 3] = 0
        pic[5:15, 10:20, 3] = 1
        self.assertEqual(int(P.object_mask(pic).sum()), 100)

    def test_flatten_takes_a_light_gradient_out(self):
        rgb = np.zeros((40, 200, 3))
        lin = np.linspace(0.1, 0.6, 200)[None, :, None] * np.array([0.8, 0.4, 0.2])
        rgb[:] = P.linear_to_srgb(lin)
        mask = np.ones((40, 200), bool)
        flat = P.flatten_light(rgb, mask, 1.0, 12)
        spread = lambda a: np.ptp(P.srgb_to_linear(a[20, 20:180, 0]))  # noqa: E731
        self.assertLess(spread(flat), 0.25 * spread(rgb))
        np.testing.assert_array_equal(P.flatten_light(rgb, mask, 0.0, 12), rgb)


class TestAlignment(unittest.TestCase):
    def test_best_shift_finds_a_known_shift(self):
        outline = np.zeros((120, 400), bool)
        outline[30:90, 40:300] = True
        obj = P._shifted(outline, -5, 17)
        dx, dy, best, now = P.best_shift(outline, obj, 80)
        self.assertEqual((dx, dy), (17, -5))
        self.assertAlmostEqual(best, 1.0)
        self.assertLess(now, 0.95)

    def test_alignment_reports_the_backdrop_share(self):
        outline = np.zeros((100, 400), bool)
        outline[20:80, 20:380] = True
        ok = P.alignment(outline, outline.copy(), 60)
        self.assertEqual(ok["outline_on_backdrop_pct"], 0.0)
        self.assertEqual(ok["shift_px"], [0, 0])
        off = P.alignment(outline, P._shifted(outline, 0, 40), 80)
        self.assertGreater(off["outline_on_backdrop_pct"], 9.0)
        self.assertEqual(off["shift_px"], [40, 0])

    def test_prepare_picture_samples_inside_the_outline(self):
        pic = np.ones((140, 440, 4), np.float32)
        pic[25:115, 40:400, :3] = (0.9, 0.1, 0.1)
        pic[25:115, 40, :3] = (0.95, 0.55, 0.55)  # an anti-aliased edge column: half backdrop
        p = P.prepare_picture(pic, box_trace(), layer())
        ox, oy = p["off"]
        self.assertEqual(p["align"]["outline_on_backdrop_pct"], 0.0)
        for x in (40.0, 41.5, 220.0, 399.9):  # whole up to the outline (the silhouette's edge lands ON it)
            self.assertAlmostEqual(float(P.bilinear(p["soft"], [x - ox], [70 - oy])[0]), 1.0)
        self.assertAlmostEqual(float(P.bilinear(p["soft"], [20 - ox], [70 - oy])[0]), 0.0)
        # the backdrop outside and the untrusted edge band take the colour from just inside
        for x in (39.6, 40.5, 41.0):
            np.testing.assert_allclose(P.bilinear(p["img"][..., :3], [x - ox], [70 - oy])[0], (0.9, 0.1, 0.1),
                                       atol=1e-5)

    def test_a_picture_moved_since_its_trace_is_measured(self):
        pic = np.ones((140, 480, 4), np.float32)
        pic[25:115, 80:440, :3] = (0.9, 0.1, 0.1)
        p = P.prepare_picture(pic, box_trace(), layer())
        self.assertGreater(p["align"]["outline_on_backdrop_pct"], 9.0)
        self.assertEqual(p["align"]["shift_px"], [40, 0])
        self.assertTrue(P.misplaced(p["align"], 360))

    def test_a_highlight_as_white_as_the_backdrop_is_not_a_misplaced_picture(self):
        pic = np.ones((140, 440, 4), np.float32)
        pic[25:115, 40:400, :3] = (0.6, 0.6, 0.62)
        pic[50:80, 100:250, :3] = 1.0  # a polished blade's glint: backdrop-white, inside the object
        p = P.prepare_picture(pic, box_trace(), layer())
        self.assertGreater(p["align"]["outline_on_backdrop_pct"], 10.0)  # (the share alone would cry wolf)
        self.assertFalse(P.misplaced(p["align"], 360))
        self.assertFalse(P.misplaced({"note": "not measured"}, 360))


class TestDecal(unittest.TestCase):
    def test_homography_maps_the_corners(self):
        src = [(0, 0), (10, 0), (10, 5), (0, 5)]
        dst = [(3, 4), (30, 8), (28, 30), (1, 22)]
        hm = P.homography(src, dst)
        for (x, y), (u, v) in zip(src, dst):
            p = hm @ (x, y, 1)
            self.assertAlmostEqual(p[0] / p[2], u, places=6)
            self.assertAlmostEqual(p[1] / p[2], v, places=6)

    def test_a_slanted_marking_comes_out_upright(self):
        # an upright 40 x 20 patch: left half red, right half blue; drawn into a picture through a perspective warp
        quad = [(50, 30), (140, 40), (135, 95), (45, 80)]
        hm = P.homography([(0, 0), (40, 0), (40, 20), (0, 20)], quad)  # patch -> picture
        inv = np.linalg.inv(hm)
        jj, ii = np.meshgrid(np.arange(200) + 0.5, np.arange(120) + 0.5)
        q = inv @ np.stack([jj.ravel(), ii.ravel(), np.ones(jj.size)])
        px, py = (q[0] / q[2]).reshape(jj.shape), (q[1] / q[2]).reshape(jj.shape)
        pic = np.ones((120, 200, 4))
        inside = (px >= 0) & (px < 40) & (py >= 0) & (py < 20)
        pic[inside & (px < 20), :3] = (1, 0, 0)
        pic[inside & (px >= 20), :3] = (0, 0, 1)
        patch = P.straighten(pic, quad)
        self.assertEqual(patch.shape[2], 4)
        h, w = patch.shape[:2]
        left, right = patch[h // 4: 3 * h // 4, 2: w // 2 - 3, :3], patch[h // 4: 3 * h // 4, w // 2 + 3: -2, :3]
        np.testing.assert_allclose(left.mean((0, 1)), (1, 0, 0), atol=0.05)
        np.testing.assert_allclose(right.mean((0, 1)), (0, 0, 1), atol=0.05)

    def test_a_decal_goes_where_its_box_is(self):
        pic = np.ones((140, 440, 4), np.float32)
        lay = layer(kind="decal", box=P.corners_of((220, 40, 256, 70)).tolist(), at=None, size=None)
        patch, rect = P.decal_patch(pic, box_trace(), lay)
        np.testing.assert_allclose(rect, (0.5, 0.6, (115 - 70) / 90, (115 - 40) / 90))
        self.assertEqual(patch.shape[:2], (30, 36))
        rgb, w = P.sample_decal(patch, rect, np.array([0.55, 0.7]), np.array([0.7, 0.7]), 2.0)
        self.assertEqual(w.tolist(), [1.0, 0.0])

    def test_at_and_size_are_design_units(self):
        pic = np.ones((50, 50, 4), np.float32)
        lay = layer(kind="decal", box=P.corners_of((0, 0, 10, 10)).tolist(), at=(0.3, 0.1), size=(0.1, 0.05),
                    front="left")
        _patch, rect = P.decal_patch(pic, box_trace(front="left"), lay)
        np.testing.assert_allclose(rect, (0.65, 0.75, 0.3, 0.5))


class TestBlend(unittest.TestCase):
    def test_one_picture_and_its_mix(self):
        base = np.zeros((2, 3))
        pic = np.ones((2, 3))
        out, alpha = P.blend(base, [(pic, np.array([1.0, 0.5]), np.array([1.0, 1.0]))])
        np.testing.assert_allclose(out[:, 0], [1.0, 0.5])
        np.testing.assert_allclose(alpha, [1.0, 0.5])

    def test_the_squarer_view_wins(self):
        base = np.zeros((2, 3))
        a, b = np.ones((2, 3)), np.zeros((2, 3))
        out, _ = P.blend(base, [(a, np.ones(2), np.array([0.707, 0.9])), (b, np.ones(2), np.array([0.707, 0.44]))])
        self.assertAlmostEqual(out[0, 0], 0.5, places=6)  # a 45-degree edge takes both
        self.assertGreater(out[1, 0], 0.98)

    def test_decals_paint_over_in_order(self):
        base = np.zeros((1, 3))
        out, alpha = P.blend(base, [(np.ones((1, 3)), np.ones(1), np.ones(1))],
                             [(np.full((1, 3), 0.25), np.ones(1))])
        np.testing.assert_allclose(out, [[0.25] * 3])
        self.assertEqual(alpha.tolist(), [1.0])

    def test_cells_compare(self):
        a = np.repeat(np.linspace(0.01, 0.99, 100), 100)
        b = np.tile(np.linspace(0.01, 0.99, 100), 100)
        model = np.zeros((a.size, 3)) + (0.8, 0.2, 0.1)
        cells = P.cells_compare(a, b, model, model.copy(), 4, 2)
        self.assertEqual(len(cells), 8)
        self.assertEqual(max(c["delta_e"] for c in cells), 0.0)
        other = model.copy()
        other[a > 0.75] = (0.1, 0.2, 0.8)
        worst = max(P.cells_compare(a, b, model, other, 4, 2), key=lambda c: c["delta_e"])
        self.assertEqual(worst["a"], [0.75, 1.0])
        self.assertGreater(worst["delta_e"], 30)


def lit_picture(lines_at=range(60, 380, 24), shadow=True):
    """a studio-lit block (x 40..400, y 25..115 of 440 x 140): grey under a light x0.25 .. x1.0, a big soft shadow,
    engraving lines at 30% albedo -> (rgb sRGB, mask, the line mask)"""
    H, W = 140, 440
    yy, xx = np.mgrid[0:H, 0:W] + 0.5
    mask = np.zeros((H, W), bool)
    mask[25:115, 40:400] = True
    lines = np.zeros((H, W), bool)
    for x in lines_at:
        lines[35:105, x:x + 2] = True
    alb = np.where(lines, 0.3 * 0.6, 0.6)
    light = 0.25 + 0.75 * np.clip((xx - 40) / 360, 0, 1)
    if shadow:
        light = light * (1 - 0.55 * np.clip((34 - np.hypot(xx - 300, yy - 72)) / 10, 0, 1))
    rgb = P.linear_to_srgb(np.repeat((alb * light)[..., None], 3, 2) * mask[..., None])
    return rgb, mask, lines


class TestDetail(unittest.TestCase):
    def test_radii_follow_the_texels(self):
        self.assertEqual(P.detail_radii(0.8), (0.0, 4.0))
        self.assertEqual(P.detail_radii(4.0), (2.0, 20.0))
        self.assertEqual(P.detail_radii(4.0, detail_px=8), (2.0, 8.0))
        r_lo, r_hi = P.detail_radii(10.0, detail_px=3)
        self.assertGreaterEqual(r_hi, r_lo + 2)

    def test_the_backdrop_never_leaks_into_a_masked_blur(self):
        a = np.zeros((20, 20))
        m = np.zeros((20, 20), bool)
        m[5:15, 5:15] = True
        a[m] = 3.0
        np.testing.assert_allclose(P.masked_blur(a, m, 3)[m], 3.0)

    def test_the_light_and_the_shadow_vanish_the_lines_stay(self):
        rgb, mask, lines = lit_picture()
        sig, scale = P.detail_signal(rgb, mask, 0.0, 4.0)
        inner = P.inside_distance(mask, 6) > 5
        flat = inner & (P.inside_distance(~lines, 4) > 3)  # between the lines
        yy, xx = np.mgrid[0:140, 0:440] + 0.5
        r = np.hypot(xx - 300, yy - 72)
        # between the lines the signal is ONE small offset (the re-centring that keeps each region's mean) — the same
        # in the dark (x 60..140), in the light (x 330..390, outside the shadow) and inside the shadow
        dark = sig[flat & (xx < 140)].mean()
        light = sig[flat & (xx > 340) & (r > 45)].mean()
        shade = sig[flat & (r < 18)].mean()
        self.assertLess(abs(dark - light), 0.03)
        self.assertLess(abs(dark - shade), 0.03)
        # the shadow's own effect (the same picture without it): its edge is a step, not a line — measured p99 0.08
        # (a line crossing the soft edge, a pixel or two)
        unshaded, _ = P.detail_signal(lit_picture(shadow=False)[0], mask, 0.0, 4.0)
        self.assertLess(float(np.percentile(np.abs(sig - unshaded)[inner], 99)), 0.1)
        on = lines & inner
        self.assertLess(float(sig[on].mean()), -0.6)
        # the same line in the dark (x 60) and in the light (x 348) gives the same signal: the light is taken out
        self.assertAlmostEqual(float(sig[40:100, 60:62].mean()), float(sig[40:100, 348:350].mean()), delta=0.03)
        self.assertAlmostEqual(scale, np.log(1 / 0.3), delta=0.1)  # its scale is the lines' own depth (30% albedo)

    def test_a_plain_picture_is_not_amplified(self):
        rgb, mask, _ = lit_picture(lines_at=(), shadow=False)
        noise = np.random.default_rng(1).normal(0, 0.003, rgb.shape)
        sig, scale = P.detail_signal(np.clip(rgb + noise * mask[..., None], 0, 1), mask, 0.0, 4.0)
        self.assertEqual(scale, P.DETAIL_FLOOR)
        self.assertLess(float(np.abs(sig[mask]).mean()), 0.15)

    def test_modulation_keeps_the_mean_in_linear_light(self):
        base = np.tile([[0.7, 0.5, 0.3]], (1000, 1))
        d = np.where(np.arange(1000) % 10 == 0, -0.45, 0.05)  # sparse dark lines, zero-mean
        out = P.modulate(base, d)
        np.testing.assert_allclose(P.srgb_to_linear(out).mean(0), P.srgb_to_linear(base[0]), rtol=1e-6)
        np.testing.assert_allclose(P.modulate(base[:3], np.zeros(3)), base[:3], atol=1e-9)

    def test_slope_never_crosses_a_seam(self):
        h = np.tile(np.arange(8, dtype=float), (4, 1))  # a ramp along U: slope 1
        ok = np.ones((4, 8), bool)
        pos = np.zeros((4, 8, 3))
        pos[..., 0] = np.arange(8) * 0.01
        pos[..., 1] = np.arange(4)[:, None] * 0.01
        pos[:, 4:, 2] = 5.0  # columns 4.. are another island: far away in the world
        gx, gy = P.texel_slope(h, ok, pos)
        np.testing.assert_allclose(gx[:, 1:3], 1.0)
        self.assertEqual(gx[0, 3], 1.0)  # one-sided at the island's edge, not (4 - 2) / 2 across the seam
        self.assertEqual(gx[0, 4], 1.0)
        np.testing.assert_allclose(gy, 0.0)

    def test_bump_tilts_away_from_the_rise(self):
        n = np.full((1, 2, 3), 0.5)
        n[..., 2] = 1.0
        out = P.apply_bump(n, np.array([[0.0, 0.5]]), np.zeros((1, 2)), 1.0)
        np.testing.assert_allclose(out[0, 0], n[0, 0], atol=1e-9)
        self.assertLess(out[0, 1, 0], 0.5)

    def test_pearson(self):
        a = np.arange(10.0)
        self.assertAlmostEqual(P.pearson(a, 2 * a + 1), 1.0)
        self.assertAlmostEqual(P.pearson(a, -a), -1.0)
        self.assertEqual(P.pearson(a, np.ones(10)), 0.0)

    def test_prepare_picture_makes_the_signal_only_in_detail_mode(self):
        rgb, mask, _ = lit_picture()
        pic = np.concatenate([rgb, np.ones(mask.shape + (1,))], 2).astype(np.float32)
        t = box_trace()
        self.assertIsNone(P.prepare_picture(pic, t, layer(detail=0.0), 0.8)["detail"])
        d = P.prepare_picture(pic, t, layer(detail=1.0, detail_px=None), 0.8)["detail"]
        self.assertEqual((d["r_lo"], d["r_hi"]), (0.0, 4.0))
        self.assertLess(float(d["signal"].min()), -0.6)
        self.assertIsNone(P.prepare_picture(pic, t, layer(detail=1.0, detail_px=None), None)["detail"])


class TestLayers(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.repo, "assets", "models"))
        with open(os.path.join(self.repo, "pic.png"), "wb") as fh:
            fh.write(b"not really a png: make_layer only hashes it")
        t = box_trace()
        t["source"] = "pic.png"
        with open(os.path.join(self.repo, "assets", "models", "thing_side.trace.json"), "w") as fh:
            json.dump(t, fh)

    def test_a_layer_is_checked_at_the_call(self):
        lay = P.make_layer("project", "thing_side", "thing_side", self.repo, "side", mix=0.5)
        self.assertEqual(lay["picture"], "pic.png")
        self.assertEqual(lay["trace"], "assets/models/thing_side.trace.json")
        self.assertEqual(len(lay["digest"]), 16)
        with self.assertRaises(ValueError):
            P.make_layer("project", "x", "thing_side", self.repo, "side", mix=1.5)
        with self.assertRaises(ValueError):
            P.make_layer("project", "x", "thing_side", self.repo, "top", mirror=True)
        with self.assertRaises(FileNotFoundError):
            P.make_layer("project", "x", "nothing", self.repo, "side")
        with self.assertRaises(ValueError):  # another picture: say where it goes
            P.make_layer("decal", "x", "thing_side", self.repo, "side", box=(0, 0, 4, 4), picture="pic.png")

    def test_detail_options_are_checked(self):
        lay = P.make_layer("project", "t", "thing_side", self.repo, "side", detail=1.0, bump=0.5, detail_px=6)
        self.assertEqual((lay["detail"], lay["bump"], lay["detail_px"]), (1.0, 0.5, 6.0))
        self.assertEqual(P.make_layer("project", "t", "thing_side", self.repo, "side")["detail"], 0.0)
        with self.assertRaises(ValueError):  # relief needs the detail it comes from
            P.make_layer("project", "t", "thing_side", self.repo, "side", bump=1.0)
        with self.assertRaises(ValueError):
            P.make_layer("project", "t", "thing_side", self.repo, "side", detail=3.0)
        with self.assertRaises(ValueError):
            P.make_layer("project", "t", "thing_side", self.repo, "side", detail=1.0, detail_px=0.5)

    def test_relief_is_the_colour_modes_relief(self):
        # a colour projection may also put the picture's fine structure into the normal map; detail mode has bump=
        lay = P.make_layer("project", "t", "thing_side", self.repo, "side", relief=1.5)
        self.assertEqual((lay["detail"], lay["relief"]), (0.0, 1.5))
        self.assertEqual(P.make_layer("project", "t", "thing_side", self.repo, "side")["relief"], 0.0)
        with self.assertRaises(ValueError):
            P.make_layer("project", "t", "thing_side", self.repo, "side", detail=1.0, relief=1.0)
        with self.assertRaises(ValueError):
            P.make_layer("project", "t", "thing_side", self.repo, "side", relief=5.0)

    def test_a_relief_map_rides_with_relief(self):
        rm = os.path.join(self.repo, "thing.relief.npz")
        h = np.zeros((40, 60), np.float32)
        h[10:30, 20:40] = 1.0   # (a raised panel)
        np.savez_compressed(rm, height=h, mask=np.ones_like(h, bool))
        lay = P.make_layer("project", "t", "thing_side", self.repo, "side", relief=1.0, relief_map=rm)
        self.assertTrue(lay["relief_map"].endswith("thing.relief.npz"))
        with self.assertRaises(ValueError):   # (its strength is relief=)
            P.make_layer("project", "t", "thing_side", self.repo, "side", relief_map=rm)
        with self.assertRaises(FileNotFoundError):
            P.make_layer("project", "t", "thing_side", self.repo, "side", relief=1.0, relief_map="nothing.npz")
        # the shape signal (a high-pass: what is wider than ~3 % of the length is form, the mesh has it): the panel's
        # border stands out — raised just inside its edge, lower just outside — and far from it nothing
        sig = P.relief_signal(rm, (120, 80), (0, 80, 0, 120), np.ones((80, 120), bool), 120)
        self.assertGreater(float(sig[20:60, 40:80].max()), 0.5)   # (the panel, scaled up 2x: rows 20-60, cols 40-80)
        self.assertLess(float(sig[16:20, 40:80].min()), -0.3)     # (just above it)
        self.assertLess(float(np.abs(sig[0:6, 0:6]).max()), 0.05)  # (a far corner)

    def test_outline_pull_brings_a_bulge_back_and_opens_a_hole(self):
        # an outline: the box with a square hole in it (a trigger guard's opening); hr 0.5 (twice as wide as tall)
        outer = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], float)
        hole = np.array([(0.4, 0.3), (0.6, 0.3), (0.6, 0.7), (0.4, 0.7)], float)
        rings = [np.array([(0, 0), (1, 0), (1, 0.8), (0.8, 0.8), (0.8, 1.0), (0, 1)], float), hole]   # (a notch)
        a = np.array([0.2, 0.9, 0.42, 0.45])
        b = np.array([0.5, 0.9, 0.5, 0.35])
        da, db = P.outline_pull(a, b, rings, 0.5)
        self.assertEqual((da[0], db[0]), (0.0, 0.0))                     # (inside: stays)
        self.assertGreater(abs(da[1]) + abs(db[1]), 0.05)                # (in the cut-out corner: pulled back)
        x, y = a[1] + da[1], b[1] + db[1]
        self.assertTrue(abs(x - 0.8) < 1e-6 or abs(y - 0.8) < 1e-6)      # (onto the notch's edge)
        self.assertAlmostEqual(a[2] + da[2], 0.4)                        # (in the hole: pushed to its nearest edge)
        self.assertAlmostEqual(b[3] + db[3], 0.3)
        far = P.outline_pull(np.array([1.5]), np.array([0.5]), [outer], 0.5)
        self.assertEqual(far[0][0], 0.0)                                 # (past max_move: a framing error, left)

    def test_a_generated_paint_is_matched_to_its_pictures(self):
        class M:
            def __init__(self, name):
                self.name = name

        rng = np.random.default_rng(2)
        n = 4000
        base = np.clip(0.5 + rng.normal(0, 0.02, (n, 3)), 0, 1)        # (a painter's pale grey)
        out = base.copy()
        alpha = np.zeros(n)
        alpha[:3000] = 1.0                                                 # (the photos cover 3/4 of it, black)
        out[:3000] = np.clip(0.08 + rng.normal(0, 0.02, (3000, 3)), 0, 1)
        midx = np.zeros(n, np.int64)
        real = np.ones(n, bool)
        new = P.match_to_pictures(base, out, alpha, midx, [M("gen_Body")], real, {"gen_Body"})
        self.assertLess(abs(float(new[3000:].mean()) - 0.08), 0.02)       # (the uncovered quarter follows the photos)
        self.assertIsNone(P.match_to_pictures(base, out, alpha, midx, [M("steel")], real, {"gen_Body"}))  # (designed)

    def test_the_digest_follows_the_options(self):
        a = P.make_layer("project", "t", "thing_side", self.repo, "side", mix=1.0)
        b = P.make_layer("project", "t", "thing_side", self.repo, "side", mix=0.9)
        self.assertNotEqual(a["digest"], b["digest"])

    def test_mirror_adds_the_other_side(self):
        self.assertEqual(P.passes(layer(mirror=True)), [(("side", "right"), False), (("side", "left"), True)])
        self.assertEqual(P.passes(layer(view="front", front="left")), [(("front", "right"), False)])


if __name__ == "__main__":
    unittest.main()
