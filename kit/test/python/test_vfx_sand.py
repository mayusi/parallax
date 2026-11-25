"""Unit tests of the sand bake (kit/vfx/sand.py).
Run: python -m pytest kit/test/python/test_vfx_sand.py -q"""
import contextlib
import copy
import io
import json
import math
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import methods as M  # noqa: E402
import sand as S  # noqa: E402


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = S.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def args(**over):
    a = {"mode": "slump", "size": 8.0, "height": 4.0, "width": 2.5, "repose": 34.0, "rate": 6.0, "frames": 24, "fps": 24, "cols": 16, "rows": 16, "settle": 0.8}
    a.update(over)
    return a


def as_file(a, heights):
    return {"recipe": "sand", "args": a, "cols": a["cols"], "rows": a["rows"],
            "frames": [[round(float(x), 4) for x in S.to_points(h / a["size"], 1.0).reshape(-1)] for h in heights]}


def steepest(h, a):
    return math.degrees(math.atan(max(np.abs(np.diff(h, axis=1)).max() / (a["size"] / a["cols"]), np.abs(np.diff(h, axis=0)).max() / (a["size"] / a["rows"]))))


class TheSand(unittest.TestCase):
    def test_a_pass_makes_and_loses_nothing_and_leaves_a_gentle_slope_alone(self):
        rng = np.random.default_rng(3)
        h = rng.uniform(0, 5, (9, 12))
        self.assertAlmostEqual(float(S.relax(h, (0.4, 0.4)).sum()), float(h.sum()), places=9)
        gentle = np.add.outer(np.arange(9) * 0.1, np.arange(12) * 0.1)
        self.assertTrue(np.array_equal(S.relax(gentle, (0.4, 0.4)), gentle))

    def test_a_pillar_ends_as_a_heap_at_its_angle_of_repose(self):
        for repose in (20.0, 34.0, 45.0):
            a = args(repose=repose)
            hs = S.simulate(a)
            self.assertAlmostEqual(float(hs[-1].sum()), float(hs[0].sum()), places=6)       # the pillar's sand, all of it
            self.assertLess(float(hs[-1].max()), float(hs[0].max()))
            self.assertLessEqual(steepest(hs[-1], a), repose + 2)
            self.assertGreater(steepest(hs[-1], a), repose - 8)                             # and not flatter than sand lies
            self.assertEqual(float(hs[0].max()), 4.0)

    def test_sand_that_holds_a_steeper_slope_stands_higher(self):
        top = [float(S.simulate(args(repose=r))[-1].max()) for r in (20.0, 34.0, 45.0)]
        self.assertLess(top[0], top[1])
        self.assertLess(top[1], top[2])

    def test_the_slide_takes_the_time_said_and_then_lies_still(self):
        hs = S.simulate(args(settle=0.5))
        self.assertTrue(np.array_equal(hs[12], hs[-1]))                                    # 0.5 s at 24 a second
        self.assertFalse(np.array_equal(hs[6], hs[-1]))
        moved = [float(np.abs(hs[k + 1] - hs[k]).sum()) for k in range(11)]
        self.assertGreater(moved[0], moved[-1])                                            # fast at first, slowing
        self.assertTrue(all(m > 0 for m in moved), moved)                                  # and it never stands still on the way
        self.assertLess(moved[0], 0.3 * sum(moved))                                        # nor falls half its way in one frame

    def test_a_pour_holds_what_was_poured_and_grows(self):
        a = args(mode="pour")
        hs = S.simulate(a)
        cell = (8 / 16) ** 2
        for f in (6, 12, 23):
            self.assertAlmostEqual(float(hs[f].sum()) * cell, 6.0 * f / 24, places=6)
        self.assertGreater(float(hs[-1].max()), float(hs[10].max()))
        self.assertEqual(np.unravel_index(int(hs[-1].argmax()), hs[-1].shape), (8, 8))      # under the spout

    def test_a_heap_is_as_wide_one_way_as_the_other(self):
        h = S.simulate(args())[-1]
        self.assertTrue(np.allclose(h, h.T, atol=1e-9))                                    # x and z are the same to it
        self.assertTrue(np.allclose(h, h[::-1, ::-1], atol=1e-9))
        ring = [float(h[8 + dj, 8 + di]) for dj, di in ((0, 5), (3, 4), (4, 3), (5, 0))]    # four places five cells from the middle
        self.assertLess(max(ring) - min(ring), 0.2 * float(h.max()))                        # a round heap, not a square one


class TheChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = args()
        cls.file = as_file(cls.a, S.simulate(cls.a))

    def failed(self, d, **kw):
        return [c["name"] for c in S.check(d, **kw) if not c["ok"]]

    def spoilt(self, fn):
        d = copy.deepcopy(self.file)
        fn(d)
        return self.failed(d)

    def heights(self, d, fn):
        g = np.array(d["frames"]).reshape(len(d["frames"]), 17, 17, 3)
        fn(g[..., 1])
        d["frames"] = [f.reshape(-1).tolist() for f in g]

    def test_a_good_bake_passes(self):
        self.assertEqual(self.failed(self.file), [])
        a = args(mode="pour")
        self.assertEqual(self.failed(as_file(a, S.simulate(a))), [])

    def test_sand_that_does_not_move(self):
        self.assertIn("the sand moves", self.spoilt(lambda d: d.update(frames=[d["frames"][-1]] * 12)))

    def test_sand_that_was_made(self):
        self.assertIn("no sand is made or lost", self.spoilt(lambda d: self.heights(d, lambda h: h[-1].__imul__(1.2))))

    def test_a_heap_left_steeper_than_its_sand(self):
        def frozen(d):
            d["frames"] = d["frames"][:3]                                                  # cut while it still slides
        self.assertIn("the heap holds no slope steeper than its sand", self.spoilt(frozen))

    def test_sand_at_the_edge_of_its_ground(self):
        def spilt(d):
            def move(h):
                h[:, 8, 0] += 0.05
                h[:, 8, 8] -= 0.05
            self.heights(d, move)
        self.assertIn("the sand stays on its ground", self.spoilt(spilt))

    def test_a_slide_cut_short(self):
        a = args(settle=0.9, frames=12)                                                  # (the command refuses this ask; a file may still hold it)
        self.assertIn("the heap has come to rest", self.failed(as_file(a, S.simulate(a))))

    def test_one_jump_and_then_nothing(self):
        self.assertIn("the sand keeps moving", self.spoilt(lambda d: d.update(frames=d["frames"][:1] + [d["frames"][-1]] * 23)))

    def test_frames_out_of_order(self):
        self.assertIn("sand only runs downhill", self.spoilt(lambda d: d.update(frames=d["frames"][:4] + d["frames"][10:16] + d["frames"][4:10] + d["frames"][16:])))

    def test_a_pyramid_steeper_across_its_corners(self):
        def pyramid(d):
            def shape(h):
                j, i = np.mgrid[0:17, 0:17]
                top = np.clip(0.3 - 0.78 * (np.abs(i - 8) + np.abs(j - 8)) / 16, 0, None)   # 38 degrees along the axes, 48 across
                for k in range(len(h)):
                    h[k] = h[k] * 0 + top * (0.5 + 0.5 * k / (len(h) - 1))
            self.heights(d, shape)
        self.assertIn("the heap has come to rest", self.spoilt(pyramid))

    def test_a_layer_that_loops_it(self):
        self.assertEqual(self.failed(self.file, loop=True), ["it is played once"])

    def test_what_is_no_sand_bake_is_said_so(self):
        for spoil in (lambda d: d.update(recipe="soft"), lambda d: d.update(frames=d["frames"][:1]), lambda d: d["frames"][3].pop(), lambda d: d.update(args=[]),
                      lambda d: d["args"].update(repose=80), lambda d: d["args"].update(mode="rain"), lambda d: d["args"].pop("size"),
                      lambda d: d["frames"][2].__setitem__(0, 0.3), lambda d: d["frames"][2].__setitem__(4, None), lambda d: d["args"].update(fps=0), lambda d: d.update(rows=8)):
            self.assertEqual(self.spoilt(spoil), ["a sand bake"])


class TheCommand(unittest.TestCase):
    def test_it_writes_the_sequence_and_a_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, said = run(["dune", "--frames", "24", "--cols", "16", "--rows", "16", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 0, said)
            d = json.load(open(os.path.join(tmp, "dune.json"), encoding="utf-8"))
            self.assertEqual((d["recipe"], d["cols"], d["rows"], len(d["frames"]), len(d["frames"][0])), ("sand", 16, 16, 24, 17 * 17 * 3))
            self.assertEqual((min(d["frames"][0][0::3]), max(d["frames"][0][0::3])), (-0.5, 0.5))   # unit size: its ground is 1 wide
            self.assertAlmostEqual(max(d["frames"][0][1::3]), 0.5)                                  # a 4-stud pillar on 8 studs of ground
            self.assertTrue(os.path.isfile(os.path.join(tmp, "dune.png")))

    def test_a_refused_bake_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            for argv, word in ((["low", "--height", "0.3", "--width", "6"], "the sand moves"), (["big", "--height", "12", "--width", "4"], "stays on its ground")):
                code, said = run(argv + ["--out-dir", tmp, "--look-dir", tmp])
                self.assertEqual(code, 1, argv)
                self.assertIn(word, said["summary"])
            self.assertEqual(os.listdir(tmp), [])

    def test_wrong_asks_are_said_in_words(self):
        for argv, word in ((["Dune"], "lowercase"), (["s", "--mode", "rain"], "--mode is one of"), (["s", "--repose", "80"], "--repose is a number"),
                           (["s", "--width", "0.5"], "too thin"), (["s", "--wind", "1"], "not an option"), (["s", "--size"], "no value"),
                           (["s", "--settle", "0"], "--settle is a number"), (["s", "--settle", "3"], "longer than the sequence"), (["s", "--cols", "9.5"], "--cols is a whole number"),
                           (["s", "--cols", "24", "--rows", "12"], "the same number")):
            code, said = run(argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, said["summary"], argv)


class TheRegister(unittest.TestCase):
    def test_sand_is_a_bake_that_is_there_and_passes(self):
        m = M.load()[1]["granular"]
        self.assertEqual(m["state"], "has")
        good = as_file(args(), S.simulate(args()))

        class Empty:
            def get(self, key):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "seq"))
            for name, d in (("dune", good), ("still", dict(good, frames=[good["frames"][-1]] * 12)), ("blob", dict(good, recipe="soft"))):
                with open(os.path.join(tmp, "seq", f"{name}.json"), "w", encoding="utf-8") as fh:
                    json.dump(d, fh)

            def proved(layer):
                return M.proved(m, [dict({"kind": "mesh", "pivot": "origin", "life": 1}, **layer)], Empty(), tmp, "s") is not None

            self.assertTrue(proved({"shape": "seq", "params": {"seq": "dune"}}))
            self.assertFalse(proved({"shape": "seq", "pivot": None, "params": {"seq": "dune"}}))     # stage 26: not sitting by its own origin
            self.assertFalse(proved({"shape": "seq", "pivot": "base", "params": {"seq": "dune"}}))
            self.assertFalse(proved({"shape": "seq", "params": {"seq": "dune", "loop": True}}))
            for bad in ("still", "blob", "nothing"):
                self.assertFalse(proved({"shape": "seq", "params": {"seq": bad}}), bad)
            self.assertFalse(proved({"shape": "disc"}))


if __name__ == "__main__":
    unittest.main()
