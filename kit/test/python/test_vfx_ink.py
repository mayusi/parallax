"""kit/vfx/ink.py - traced drawings into a sprite sheet - on shapes whose answer is known: squares and discs made here
and the made flame (kit/selftest/vfx/trace/made.py). What is proven is what a sheet is trusted for: the drawing sits
where its window says and fills its cell, an in-between is between (its area, its place) and keeps a drawn point a
point, drawings that are not the same pieces fall back to distance fields and are refused when they barely overlap,
each check catches the fault it is named for, and a sheet that fails leaves nothing behind."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "selftest", "vfx", "trace"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "selftest", "vfx", "ink"))
import ink as I  # noqa: E402
import made  # noqa: E402
import madeink  # noqa: E402
import shapetrace as T  # noqa: E402


def ring(points, corners=True):
    p = np.asarray(points, dtype=np.float64)
    return p, np.full(len(p), bool(corners))


def square(cx, cy, half):
    return ring([(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)])


def disc(cx, cy, r, n=48):
    return ring([(cx + r * np.cos(a), cy + r * np.sin(a)) for a in np.linspace(0, 2 * np.pi, n, endpoint=False)], False)


def drawing(shapes, hold=2, tone=0):
    pts = np.concatenate([s["outer"][0] for s in shapes])
    return {"hold": hold, "box": [pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()],
            "layers": [{"tone": tone, "shapes": shapes}]}


def dump(data, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def trace_of(drawings, fps=24.0):
    return {"fps": fps, "tones": np.array([[240, 120, 30], [254, 225, 90]], dtype=np.float32), "drawings": drawings}


def flame_trace():
    return T.from_json(json.loads(json.dumps(T.to_json(T.trace_frames(made.scene(), made.FPS, made.HUE)))))


class TestWindow(unittest.TestCase):
    def test_beat_keeps_the_scenes_motion_and_drawing_centres_each(self):
        ds = [drawing([{"outer": square(100, 100, 20), "holes": []}]), drawing([{"outer": square(180, 100, 20), "holes": []}])]
        beat = I.windows(ds, 256, "beat")
        self.assertEqual(beat[0], beat[1])                    # one window: the second square sits to the right of the first
        scale, off = beat[0]
        self.assertAlmostEqual((100 + off[0]) * scale + (180 + off[0]) * scale, 256.0, places=3)
        each = I.windows(ds, 256, "drawing")
        for d, (s, o) in zip(ds, each):
            self.assertAlmostEqual(((d["box"][0] + d["box"][2]) / 2 + o[0]) * s, 128.0, places=3)
        self.assertEqual(each[0][0], each[1][0])              # ONE scale: a small drawing stays small beside a large one

    def test_the_window_is_as_small_as_holds_the_drawings(self):
        ds = [drawing([{"outer": square(500, 300, 40), "holes": []}])]
        got = I.ink(trace_of(ds), 256)
        a = got["cells"][0][..., 3] > 0.5
        xs = np.nonzero(a.any(axis=0))[0]
        self.assertAlmostEqual(xs.min(), 256 * I.MARGIN, delta=2)             # the square reaches the margin, no further
        self.assertAlmostEqual(xs.max(), 256 * (1 - I.MARGIN), delta=2)
        self.assertGreater(got["fill"], 0.7)

    def test_a_sheet_is_a_power_of_two_and_at_most_1024(self):
        self.assertEqual(I.grid_for(6, 256), ((4, 2), 256))
        self.assertEqual(I.grid_for(11, 256), ((4, 4), 256))
        self.assertEqual(I.grid_for(16, 512), ((4, 4), 256))  # 4 x 512 is 2048: the cell is halved, and said
        self.assertEqual(I.grid_for(40, 256), ((8, 8), 128))
        self.assertIsNone(I.grid_for(65, 256))


class TestBetween(unittest.TestCase):
    def test_a_square_between_two_squares_is_a_square_of_the_area_between(self):
        a, b = square(100, 100, 20), square(100, 100, 40)
        A, B = I.pair_rings(a, b, 1.0, (0, 0), 1.0, (0, 0))
        cover, grow, needed = I.between_curves([(A, B, [])], 0.5, 256)
        self.assertAlmostEqual(needed, grow[0], places=6)     # two squares about one centre: nothing collapsed
        want = (40 * 40 + 80 * 80) / 2.0
        self.assertAlmostEqual(float(cover.sum()), want, delta=0.015 * want)
        side = np.sqrt(want)                                  # its corner is still a corner: filled right up to it
        self.assertGreater(float(cover[int(100 - side / 2 + 1.5), int(100 - side / 2 + 1.5)]), 0.9)
        self.assertLess(float(cover[int(100 - side / 2 - 1.5), int(100 - side / 2 - 1.5)]), 0.1)

    def test_a_point_meets_a_point_whichever_corner_the_outline_starts_at(self):
        a = square(100, 100, 30)
        b = (np.roll(square(104, 100, 30)[0], 2, axis=0), np.ones(4, dtype=bool))     # the same square, begun elsewhere
        A, B = I.pair_rings(a, b, 1.0, (0, 0), 1.0, (0, 0))
        self.assertEqual(len(A), len(B))
        self.assertLess(float(np.hypot(*(A - B).T).max()), 4.5)          # every point's partner is 4 px away, never across

    def test_round_shapes_are_turned_until_they_lie_closest(self):
        a = disc(100, 100, 30)
        b = (np.roll(disc(100, 100, 30)[0], 17, axis=0), np.zeros(48, dtype=bool))
        A, B = I.pair_rings(a, b, 1.0, (0, 0), 1.0, (0, 0))
        self.assertLess(float(np.hypot(*(A - B).T).max()), 2.0)

    def test_the_flames_in_between_keeps_its_tip_and_lies_between(self):
        got = I.ink(flame_trace(), 256, n_between=1, pick=(1, 4), loop=True)
        self.assertEqual(got["by_field"], 0)
        self.assertEqual(got["kinds"], ["drawing", "between"] * 4)             # the last in-between leads back to the first
        alpha = [c[..., 3] > 0.5 for c in got["cells"]]
        tops = [int(np.nonzero(a.any(axis=1))[0].min()) for a in alpha]
        for k in range(1, 8, 2):
            before, after = k - 1, (k + 1) % 8
            self.assertTrue(min(tops[before], tops[after]) <= tops[k] <= max(tops[before], tops[after]))
            self.assertLessEqual(int(alpha[k][tops[k] + 3].sum()),
                                 max(int(alpha[before][tops[before] + 3].sum()), int(alpha[after][tops[after] + 3].sum())) + 2)
        self.assertTrue(all(c["ok"] for c in got["checks"]), got["checks"])

    def test_without_the_alignment_the_tip_would_go_blunt(self):
        # what the point-to-point pairing is for: laid out from wherever each outline happens to start, the tip of
        # one drawing meets the side of the next and the in-between's tip is cut off
        tr = flame_trace()
        a, b = tr["drawings"][0]["layers"][0]["shapes"][0]["outer"], tr["drawings"][3]["layers"][0]["shapes"][0]["outer"]
        b = (np.roll(b[0], 10, axis=0), np.roll(b[1], 10))
        w = (1.0, (0.0, 0.0))
        A, B = I.pair_rings(a, b, *w, *w)
        good = I.between_curves([(A, B, [])], 0.5, 400)[0] > 0.5
        pa, pb = I._dense(a, *w)[0], I._dense(b, *w)[0]
        bad = I.between_curves([(I._lay(pa, 0, 0, 240), I._lay(pb, 0, 0, 240), [])], 0.5, 400)[0] > 0.5

        def tip_width(m):
            top = int(np.nonzero(m.any(axis=1))[0].min())
            return int(m[top + 3].sum())

        self.assertLessEqual(tip_width(good), 14)
        self.assertGreater(tip_width(bad), tip_width(good) + 6)
        self.assertLess(int(bad.sum()), 0.5 * int(good.sum()))                 # ... and it has lost most of its area

    def test_an_outline_drawn_the_other_way_round_is_turned_first(self):
        a = square(100, 100, 30)
        b = (square(104, 100, 30)[0][::-1].copy(), np.ones(4, dtype=bool))
        A, B = I.pair_rings(a, b, 1.0, (0, 0), 1.0, (0, 0))
        self.assertLess(float(np.hypot(*(A - B).T).max()), 4.5)

    def test_a_shape_that_turns_too_far_goes_by_distance_fields_not_to_nothing(self):
        # a teardrop and the same teardrop turned half round, tip to tip: point to point, every point crosses the
        # middle and the in-between collapses. It must be made from distance fields instead - and said
        tear = [(100 + 30 * np.sin(t) * np.sin(t / 2) ** 2, 100 - 45 * np.cos(t)) for t in np.linspace(0, 2 * np.pi, 60, endpoint=False)]
        turned = [(200 - x, 200 - y) for x, y in tear]
        tip = np.array([True] + [False] * 59)                 # the teardrop's point is a drawn point in both
        ds = [drawing([{"outer": (np.array(tear), tip), "holes": []}]), drawing([{"outer": (np.array(turned), tip), "holes": []}])]
        got = I.ink(trace_of(ds), 256, n_between=1, loop=True)
        self.assertIsNone(got["refused"])
        self.assertEqual(got["by_field"], 2)
        mid = got["cells"][1][..., 3]
        self.assertGreater(float(mid.sum()), 0.8 * float(got["cells"][0][..., 3].sum()))

    def test_distance_fields_give_the_area_between_and_one_piece(self):
        a = T.fill([{"outer": disc(128, 128, 30), "holes": []}], (256, 256))
        b = T.fill([{"outer": disc(128, 128, 60), "holes": []}], (256, 256))
        mid = I.between(a, b, 0.5)
        want = (a.sum() + b.sum()) / 2.0
        self.assertAlmostEqual(float(mid.sum()), float(want), delta=0.01 * float(want))
        self.assertEqual(float(I.between(np.zeros_like(a), np.zeros_like(a), 0.5).sum()), 0.0)

    def test_pieces_that_differ_are_not_paired(self):
        one = [{"outer": disc(100, 100, 30), "holes": []}]
        two = [{"outer": disc(80, 100, 20), "holes": []}, {"outer": disc(140, 100, 20), "holes": []}]
        holed = [{"outer": disc(100, 100, 30), "holes": [disc(100, 100, 8)]}]
        w = (1.0, (0.0, 0.0))
        self.assertIsNone(I.pair_shapes(one, two, w, w))
        self.assertIsNone(I.pair_shapes(one, holed, w, w))
        self.assertIsNotNone(I.pair_shapes(holed, holed, w, w))

    def test_drawings_that_are_not_the_same_pieces_and_barely_overlap_are_refused(self):
        trace = T.from_json(json.loads(json.dumps(T.to_json(T.trace_frames(madeink.split(), made.FPS, made.HUE)))))
        self.assertEqual(len(trace["drawings"]), 2)
        self.assertIn("barely overlap", I.ink(trace, 256, n_between=1)["refused"])
        self.assertIn("the trace holds 2", I.ink(trace, 256, pick=(1, 9))["refused"])
        self.assertIsNone(I.ink(trace, 256)["refused"])       # without an in-between the two drawings are a sheet


class TestCells(unittest.TestCase):
    def test_greys_keep_the_order_and_the_lightest_is_white(self):
        g = I.greys(np.array([[240, 120, 30], [254, 225, 90]], dtype=np.float32))
        self.assertAlmostEqual(float(g[1, 0]), 255.0, places=2)
        self.assertTrue(float(g[0, 0]) < 255.0 and g[0, 0] == g[0, 1] == g[0, 2])

    def test_a_line_is_drawn_inside_the_edge(self):
        cov = {0: T.fill([{"outer": disc(64, 64, 40), "holes": []}], (128, 128))}
        tones = np.array([[240, 120, 30]], dtype=np.float32)
        plain, lined = I.paint(cov, tones), I.paint(cov, tones, line=3)
        self.assertTrue(np.array_equal(plain[..., 3], lined[..., 3]))     # the silhouette is the same
        self.assertLess(float(lined[64, 64 - 38, 0]), 0.4)                 # 2 px inside the edge: ink
        self.assertAlmostEqual(float(lined[64, 64, 0]), 240 / 255.0, places=3)   # the middle: the tone

    def test_an_edge_pixel_keeps_its_tones_colour(self):
        # colour that already carried the coverage, multiplied by it again when packed, was a dark fringe on every edge
        cov = {0: T.fill([{"outer": disc(64, 64, 40), "holes": []}], (128, 128))}
        px = I.paint(cov, np.array([[240, 120, 30]], dtype=np.float32))
        edge = (px[..., 3] > 0.2) & (px[..., 3] < 0.8)
        self.assertTrue(edge.any())
        self.assertLess(float(np.abs(px[edge][:, :3] * 255.0 - np.array([240, 120, 30])).max()), 0.5)
        again = T.paint({"layers": [{"tone": 0, "shapes": [{"outer": disc(64, 64, 40), "holes": []}]}]},
                        np.array([[240, 120, 30]], dtype=np.float32), (128, 128))
        self.assertLess(float(np.abs(again[edge][:, :3] * 255.0 - np.array([240, 120, 30])).max()), 0.5)

    def test_the_cells_are_what_the_sheet_packer_reads(self):
        got = I.ink(flame_trace(), 256)
        px = I.premultiplied(got["cells"][0])
        self.assertEqual(px.shape, (256, 256, 4))
        outside = px[..., 3] == 0
        self.assertEqual(float(np.abs(px[outside][:, :3]).max()), 0.0)     # colour times coverage: nothing where it is clear


class TestChecks(unittest.TestCase):
    def cell(self, cover, colour=(240, 120, 30)):
        rgb = np.zeros(cover.shape + (3,), dtype=np.float32) + np.array(colour, dtype=np.float32) / 255.0
        return np.dstack([rgb, cover.astype(np.float32)])

    def failed(self, cells, kinds=None, areas=None):
        tones = np.array([[240, 120, 30]], dtype=np.float32)
        checks, _ = I.check(cells, kinds or ["drawing"] * len(cells), areas or [None] * len(cells), tones, cells[0].shape[0],
                            I.grid_for(len(cells), cells[0].shape[0])[0])
        return [c["name"] for c in checks if not c["ok"]]

    def test_a_drawn_disc_passes(self):
        a = T.fill([{"outer": disc(128, 128, 90), "holes": []}], (256, 256))
        b = T.fill([{"outer": disc(128, 128, 80), "holes": []}], (256, 256))
        self.assertEqual(self.failed([self.cell(a), self.cell(b)]), [])

    def test_each_check_catches_its_fault(self):
        good = T.fill([{"outer": disc(128, 128, 90), "holes": []}], (256, 256))
        speck = T.fill([{"outer": disc(128, 128, 14), "holes": []}], (256, 256))       # 0.9 % of the cell
        self.assertEqual(self.failed([self.cell(speck)]), ["fill"])
        cut = T.fill([{"outer": disc(128, 128, 140), "holes": []}], (256, 256))         # runs off the cell
        self.assertIn("clear", self.failed([self.cell(cut)]))
        yy, xx = np.mgrid[0:256, 0:256]
        soft = np.clip(1.2 - np.hypot(xx - 128, yy - 128) / 80.0, 0, 1)                 # a glow: a 60 px soft edge
        self.assertIn("hard", self.failed([self.cell(soft)]))
        self.assertIn("flat", self.failed([self.cell(good, colour=(40, 200, 220))]))    # not the trace's tone
        self.assertEqual(self.failed([self.cell(good), self.cell(good)]), ["moves"])    # a held drawing stored twice
        dot = T.fill([{"outer": disc(128, 128, 5), "holes": []}], (256, 256))           # 0.1 % of its cell
        self.assertEqual(self.failed([self.cell(good), self.cell(dot)]), ["empty"])
        b, c = (T.fill([{"outer": disc(128, 128, r), "holes": []}], (256, 256)) for r in (80, 70))
        self.assertEqual(self.failed([self.cell(good), self.cell(b), self.cell(c)]), ["full"])    # 3 cells in a sheet of 4
        other = T.fill([{"outer": disc(128, 128, 80), "holes": []}], (256, 256))
        self.assertIn("volume", self.failed([self.cell(good), self.cell(other), self.cell(good)],
                                            ["drawing", "between", "drawing"], [None, float(good.sum()), None]))


class TestCommand(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="kit_ink_")
        self.trace = os.path.join(self.root, "trace.json")
        dump(T.to_json(T.trace_frames(made.scene(), made.FPS, made.HUE)), self.trace)
        self.specs, self.frames = os.path.join(self.root, "specs"), os.path.join(self.root, "fxlab")
        self.dirs = ["--specs-dir", self.specs, "--frames-dir", self.frames, "--look-dir", os.path.join(self.root, "look"),
                     "--kept-dir", self.root]

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_ink(self, argv):
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            code = I.main(argv)
        return code, json.loads(said.getvalue().strip().splitlines()[-1])

    def test_a_sheet_says_how_to_play_it(self):
        code, got = self.run_ink(["flame", "--from", self.trace, "--drawings", "1-4"] + self.dirs)
        self.assertEqual(code, 0, got)
        self.assertEqual((got["cells"], got["grid"], got["fps"]), (4, [2, 2], 12.0))     # on twos at 24 = 12 drawings a second
        spec = load(os.path.join(self.specs, "flame.json"))
        self.assertEqual((spec["recipe"], spec["grid"], spec["frames"]), ("ink", 2, 4))
        self.assertEqual(spec["play"], {"mode": "Loop", "fps": 12.0, "blend": False})
        self.assertIn("Loop", got["next_action"])

    def test_a_sheet_with_empty_cells_is_not_a_sheet(self):
        code, got = self.run_ink(["flame", "--from", self.trace] + self.dirs)            # six drawings: a sheet of eight
        self.assertEqual(code, 1)
        self.assertIn("full", got["summary"])
        self.assertIn("blank", got["summary"])
        self.assertFalse(os.path.exists(os.path.join(self.specs, "flame.json")))

    def test_the_engines_thirty_a_second_is_said_when_it_cuts_the_rate(self):
        code, got = self.run_ink(["flame", "--from", self.trace, "--drawings", "1-4", "--between", "3", "--loop"] + self.dirs)
        self.assertEqual((code, got["cells"], got["fps"]), (0, 16, 30.0))
        self.assertIn("it would need 48", got["summary"])

    def test_a_trace_that_is_not_kept_gives_a_look_and_no_texture(self):
        code, got = self.run_ink(["flame", "--from", self.trace, "--drawings", "1-4"] + self.dirs[:-1] + [os.path.join(self.root, "elsewhere")])
        self.assertEqual(code, 0)
        self.assertIn("A LOOK ONLY", got["summary"])
        self.assertIsNone(got["spec"])
        self.assertTrue(os.path.isfile(got["look"]))
        self.assertFalse(os.path.exists(os.path.join(self.specs, "flame.json")))
        self.assertFalse(os.path.exists(os.path.join(self.frames, "flame")))

    def test_drawings_the_box_cut_are_said_to_be_cut(self):
        dump(T.to_json(T.trace_frames(made.scene(), made.FPS, made.HUE, box=(0.0, 0.0, 0.52, 1.0))), self.trace)
        code, got = self.run_ink(["flame", "--from", self.trace, "--drawings", "1-4"] + self.dirs)
        self.assertIn("CUT 4 of these drawings", got["summary"])

    def test_a_later_failure_says_the_earlier_sheet_is_unchanged(self):
        self.run_ink(["flame", "--from", self.trace, "--drawings", "1-4"] + self.dirs)
        code, got = self.run_ink(["flame", "--from", self.trace, "--drawings", "1-3"] + self.dirs)
        self.assertEqual(code, 1)
        self.assertIn("EARLIER sheet of this key", got["summary"])
        self.assertEqual(load(os.path.join(self.specs, "flame.json"))["frames"], 4)

    def test_some_of_the_drawings(self):
        code, got = self.run_ink(["flame", "--from", self.trace, "--drawings", "2-5"] + self.dirs)
        self.assertEqual((code, got["cells"], got["grid"]), (0, 4, [2, 2]))

    def test_a_sheet_that_fails_its_checks_leaves_nothing_behind(self):
        far = [drawing([{"outer": disc(40, 40, 6), "holes": []}]), drawing([{"outer": disc(900, 500, 6), "holes": []}])]
        data = {"schema": 1, "size": [960, 540], "fps": 24.0, "frames": 4, "on": 2, "tones": [[240, 120, 30]], "refused": [],
                "drawings": [{"frames": [2 * i, 2 * i + 1], "hold": 2, "at": 0, "cover": 0.001, "pieces": 1, "holes": 0, "points": 48,
                              "tips": 0, "fit": 1.0, "box": [d["box"][0] / 960, d["box"][1] / 540, d["box"][2] / 960, d["box"][3] / 540],
                              "layers": [{"tone": 0, "shapes": [{"outer": [[x / 960, y / 540, 0] for x, y in d["layers"][0]["shapes"][0]["outer"][0]],
                                                                  "holes": []}]}]} for i, d in enumerate(far)]}
        dump(data, self.trace)
        code, got = self.run_ink(["specks", "--from", self.trace] + self.dirs)
        self.assertEqual(code, 1)
        self.assertIn("fill", got["summary"])                 # two specks a screen apart in one window: almost no cell used
        self.assertFalse(os.path.exists(os.path.join(self.specs, "specks.json")))
        self.assertFalse(os.path.exists(os.path.join(self.frames, "specks")))

    def test_another_textures_spec_is_never_overwritten(self):
        os.makedirs(self.specs)
        dump({"engine": "fx", "recipe": "blast"}, os.path.join(self.specs, "flame.json"))
        code, got = self.run_ink(["flame", "--from", self.trace] + self.dirs)
        self.assertEqual(code, 1)
        self.assertIn("another texture", got["summary"])

    def test_bad_options_and_a_missing_trace_are_said_not_thrown(self):
        for bad in (["--cell", "300"], ["--between", "9"], ["--register", "left"], ["--drawings", "4-2"], ["--drawings", "3-100"],
                    ["--cell", "big"], ["--line"]):
            code, got = self.run_ink(["flame", "--from", self.trace] + bad + self.dirs)
            self.assertEqual((code, got["status"]), (1, "fail"), bad)
        code, got = self.run_ink(["flame", "--from", os.path.join(self.root, "none.json")] + self.dirs)
        self.assertEqual(code, 1)
        self.assertIn("its trace is not on this machine", got["summary"])
        code, got = self.run_ink(["Flame!", "--from", self.trace] + self.dirs)
        self.assertEqual(code, 1)

    def test_the_build_step_inks_a_stale_sheet_again_and_leaves_a_fresh_one(self):
        self.run_ink(["flame", "--from", self.trace, "--drawings", "1-4"] + self.dirs)
        step = ["--specs", self.specs, "--out", self.frames, "--kept-dir", self.root]
        first = os.path.join(self.frames, "flame", "000.npy")
        before = os.path.getmtime(first)
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            self.assertEqual(I.main(step), 0)
        self.assertEqual(os.path.getmtime(first), before)                     # fresh: untouched
        self.assertIn("current", said.getvalue())
        os.remove(os.path.join(self.frames, "flame", "frames.json"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(I.main(step), 0)
        self.assertTrue(os.path.isfile(os.path.join(self.frames, "flame", "frames.json")))
        data = load(self.trace)                                                # the trace made again: the sheet is stale
        data["tones"][0] = [10, 200, 90]
        dump(data, self.trace)
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            self.assertEqual(I.main(step), 0)
        self.assertIn("1 sheet(s) inked again", said.getvalue())
        os.remove(self.trace)                                                  # the trace gone: said, not thrown
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            self.assertEqual(I.main(step), 1)
        self.assertIn("its trace is not on this machine", said.getvalue())

    def test_a_broken_spec_is_said_and_does_not_stop_the_others(self):
        self.run_ink(["flame", "--from", self.trace, "--drawings", "1-4"] + self.dirs)
        good = load(os.path.join(self.specs, "flame.json"))
        for name, block in (("a_cell", {"cell": 300}), ("b_pick", {"drawings": [5]}), ("c_gray", {"gray": "no"}),
                            ("d_between", {"between": 5})):
            dump({**good, "ink": {**good["ink"], **block}}, os.path.join(self.specs, f"{name}.json"))
        shutil.rmtree(os.path.join(self.frames, "flame"))
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            code = I.main(["--specs", self.specs, "--out", self.frames, "--kept-dir", self.root])
        got = json.loads(said.getvalue().strip().splitlines()[-1])
        self.assertEqual(code, 1)
        for name in ("a_cell", "b_pick", "c_gray", "d_between"):
            self.assertIn(f"ink {name}: its spec's", got["summary"])
        self.assertEqual(len(got["inked"]), 1)                                 # the good one was still inked again
        self.assertTrue(os.path.isfile(os.path.join(self.frames, "flame", "frames.json")))

    def test_a_file_that_is_not_a_trace_is_said_not_thrown(self):
        for junk in ({}, [], {"fps": 24, "size": [10, 10], "tones": [], "drawings": []},
                     {"fps": 24, "size": [10, 10], "tones": [[1, 2, 3]], "drawings": [{"box": [0, 0, 1, 1], "layers": [{"tone": 7, "shapes": []}]}]},
                     {"size": [10, 10], "tones": [[1, 2, 3]], "drawings": []}):
            dump(junk, self.trace)
            code, got = self.run_ink(["flame", "--from", self.trace] + self.dirs)
            self.assertEqual((code, got["status"]), (1, "fail"), junk)


if __name__ == "__main__":
    unittest.main()
