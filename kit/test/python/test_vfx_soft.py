"""Unit tests of the soft-body bake (kit/vfx/soft.py).
Run: python -m pytest kit/test/python/test_vfx_soft.py -q"""
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
import soft as S  # noqa: E402


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = S.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def args(**over):
    a = {"size": 4.0, "drop": 6.0, "throw": [0.0, 0.0, 0.0], "soft": 0.6, "squash": 0.7, "gravity": 60.0, "frames": 32, "fps": 24, "cols": 12, "rows": 8,
         "damp": 1.5}
    a.update(over)
    return a


def as_file(a, frames):
    return {"recipe": "soft", "args": a, "cols": a["cols"], "rows": a["rows"], "frames": [[round(float(x) / a["size"], 4) for x in f.reshape(-1)] for f in frames]}


def grid(a, f):
    return f.reshape(a["rows"] + 1, a["cols"] + 1, 3)


class TheBall(unittest.TestCase):
    def test_the_skin_is_a_closed_ball_of_the_grids_size(self):
        pts = S.skin(12, 8)
        self.assertEqual(len(pts), 2 + 12 * 7)
        self.assertTrue(np.allclose(np.linalg.norm(pts, axis=1), 1))
        order = S.grid_of(12, 8).reshape(9, 13)
        self.assertTrue((order[0] == 0).all() and (order[-1] == len(pts) - 1).all())       # each pole a whole row
        self.assertTrue((order[:, 0] == order[:, -1]).all())                               # the seam column twice
        self.assertEqual(sorted(set(order.reshape(-1).tolist())), list(range(len(pts))))   # every point is on the grid
        self.assertAlmostEqual(S.volume(pts[order.reshape(-1)].reshape(9, 13, 3)), 4 / 3 * math.pi, delta=0.35)

    def test_it_falls_as_a_thing_falls_until_it_lands(self):
        a = args()
        fr = S.simulate(a)
        for f in (0, 4, 8):                                                              # before it lands: a rigid ball in free fall
            t = f / 24
            self.assertAlmostEqual(float(fr[f][:, 1].min()), 6 - 0.5 * 60 * t * t, delta=0.25)
            self.assertAlmostEqual(float(np.ptp(fr[f][:, 1])), 4.0, delta=0.05)

    def test_it_squashes_wider_when_it_lands_and_never_goes_under_the_floor(self):
        a = args()
        fr = S.simulate(a)
        tall = [float(np.ptp(f[:, 1])) for f in fr]
        k = int(np.argmin(tall))
        self.assertLess(tall[k], 3.4)
        self.assertGreater(float(np.ptp(fr[k][:, 0])), 4.2)                               # what its height lost its width gained
        self.assertGreaterEqual(min(float(f[:, 1].min()) for f in fr), 0.0)
        v = [S.volume(grid(a, f)) for f in fr]
        self.assertGreater(min(v) / v[0], 0.9)

    def test_a_softer_ball_squashes_more(self):
        low = [min(float(np.ptp(f[:, 1])) for f in S.simulate(args(soft=s, drop=3.0))) for s in (0.1, 0.5, 0.8)]
        self.assertGreater(low[0], low[1])
        self.assertGreater(low[1], low[2])

    def test_a_ball_dropped_straight_stays_straight(self):
        a = args(frames=48)
        fr = S.simulate(a)
        top = grid(a, fr[-1])[-1, 0]
        mid = fr[-1].mean(0)
        self.assertLess(abs(float(top[2] - mid[2])), 1e-6)                                # it has not rolled over
        self.assertLess(abs(float(mid[2])), 1e-6)
        low = grid(a, fr[-1])[0, 0]
        self.assertLess(abs(float(top[0] - low[0])), 1e-6)                                # nor leant over the other way
        self.assertLess(abs(float(top[0])), 1e-6)

    def test_it_is_the_same_ball_at_another_frame_rate(self):
        low = []
        for fps in (12, 24, 60):
            fr = S.simulate(args(fps=fps, frames=fps * 2))
            low.append(min(float(np.ptp(f[:, 1])) for f in fr) / 4.0)
        self.assertLess(max(low) - min(low), 0.12, low)

    def test_the_floor_grips_a_thrown_ball(self):
        a = args(throw=[14.0, 0.0, 0.0], frames=48)
        far = float(S.simulate(a)[-1][:, 0].mean())
        self.assertLess(far, 14.0 * 47 / 24 * 0.8)                                        # it does not slide on as if on ice
        turned = grid(a, S.simulate(a)[-1])[-1, 0] - S.simulate(a)[-1].mean(0)
        self.assertGreater(abs(float(turned[0])), 0.3)                                    # and it has turned: its top pole is off its middle

    def test_a_thrown_ball_goes_the_way_it_was_thrown(self):
        a = args(throw=[14.0, 0.0, 0.0])
        fr = S.simulate(a)
        self.assertGreater(float(fr[-1][:, 0].mean()), 6.0)
        self.assertLess(abs(float(fr[-1][:, 2].mean())), 1e-6)

    def test_the_same_asks_give_the_same_frames(self):
        self.assertTrue(all(np.array_equal(x, y) for x, y in zip(S.simulate(args()), S.simulate(args()))))


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

    def test_a_good_bake_passes(self):
        self.assertEqual(self.failed(self.file), [])

    def test_a_rigid_ball_is_no_soft_body(self):
        first = np.array(self.file["frames"][0]).reshape(-1, 3)

        def rigid(d):
            d["frames"] = [(first - [0, 0.04 * k, 0]).reshape(-1).tolist() for k in range(20)]
        self.assertEqual(self.spoilt(rigid), ["it is soft"])

    def test_one_frame_out_of_shape_is_a_glitch(self):
        first = np.array(self.file["frames"][0]).reshape(-1, 3)

        def glitch(d):
            fr = [(first - [0, 0.04 * k, 0]) for k in range(20)]
            fr[9] = fr[9] * [1.1, 0.8, 1.1]
            d["frames"] = [f.reshape(-1).tolist() for f in fr]
        self.assertIn("it is soft", self.spoilt(glitch))

    def test_a_ball_that_sits_still(self):
        self.assertIn("the ball moves", self.spoilt(lambda d: d.update(frames=[d["frames"][0]] * 12)))

    def test_a_ball_that_shrinks(self):
        def shrink(d):
            pts = np.array(d["frames"][-1]).reshape(-1, 3)
            pts[:, [0, 2]] *= 0.6
            d["frames"][-1] = pts.reshape(-1).tolist()
        self.assertIn("it keeps its volume", self.spoilt(shrink))

    def test_a_puddle(self):
        def puddle(d):
            pts = np.array(d["frames"][-1]).reshape(-1, 3)
            pts[:, 1] *= 0.1
            pts[:, [0, 2]] *= 3.2
            d["frames"][-1] = pts.reshape(-1).tolist()
        self.assertIn("it is not crushed flat", self.spoilt(puddle))

    def test_a_point_under_the_floor(self):
        self.assertIn("it stays on the floor", self.spoilt(lambda d: d["frames"][-1].__setitem__(1, -0.2)))

    def test_a_seam_that_opened(self):
        k = (4 * 13 + 12) * 3                                                             # row 4's last column: the seam's twin
        self.assertIn("its skin is closed", self.spoilt(lambda d: d["frames"][5].__setitem__(k, d["frames"][5][k] + 0.05)))

    def test_a_jump_in_the_skin(self):
        def jump(d):
            for i in (0, 12):
                d["frames"][7][(4 * 13 + i) * 3 + 2] += 0.5                                # both of the seam's columns: the skin stays closed
        self.assertEqual(self.spoilt(jump), ["no jump in its skin"])

    def test_a_layer_that_loops_it(self):
        self.assertEqual(self.failed(self.file, loop=True), ["it is played once"])

    def test_what_is_no_soft_bake_is_said_so(self):
        for spoil in (lambda d: d.update(recipe="cloth"), lambda d: d.update(frames=d["frames"][:1]), lambda d: d["frames"][3].pop(), lambda d: d.update(rows=True),
                      lambda d: d["frames"][2].__setitem__(4, float("inf")), lambda d: d.update(cols=2)):
            self.assertEqual(self.spoilt(spoil), ["a soft-body bake"])


class TheCommand(unittest.TestCase):
    def test_it_writes_the_sequence_and_a_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, said = run(["blob", "--frames", "32", "--cols", "12", "--rows", "8", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 0, said)
            d = json.load(open(os.path.join(tmp, "blob.json"), encoding="utf-8"))
            self.assertEqual((d["recipe"], d["cols"], d["rows"], len(d["frames"]), len(d["frames"][0])), ("soft", 12, 8, 32, 13 * 9 * 3))
            self.assertAlmostEqual(max(d["frames"][0][1::3]) - min(d["frames"][0][1::3]), 1.0, places=3)   # unit size: its width is 1
            self.assertTrue(os.path.isfile(os.path.join(tmp, "blob.png")))

    def test_a_refused_bake_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, said = run(["rock", "--drop", "0", "--gravity", "0", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 1)
            self.assertIn("sits still", said["summary"])
            code, said = run(["pud", "--soft", "0.95", "--drop", "60", "--gravity", "200", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 1)
            self.assertIn("crushed flat", said["summary"])
            self.assertEqual(os.listdir(tmp), [])

    def test_wrong_asks_are_said_in_words(self):
        for argv, word in ((["Blob"], "lowercase"), ([], "ONE"), (["s", "--soft", "2"], "--soft is a number"), (["s", "--throw", "1,2"], "--throw x,y,z"),
                           (["s", "--throw", "900,0,0"], "200 studs"), (["s", "--frames", "1"], "--frames is a whole number"), (["s", "--cols", "3"], "--cols"),
                           (["s", "--loop"], "not an option"), (["s", "--squash", "1"], "--squash is a number from 0 to 0.8"), (["s", "--size"], "no value"), (["s", "--size", "big"], "--size is a number")):
            code, said = run(argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, said["summary"], argv)


class TheRegister(unittest.TestCase):
    def test_soft_body_is_a_bake_that_is_there_and_passes(self):
        m = M.load()[1]["soft_body"]
        self.assertEqual(m["state"], "has")
        a = args()
        good = as_file(a, S.simulate(a))

        class Empty:
            def get(self, key):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "seq"))
            rigid = copy.deepcopy(good)
            first = np.array(good["frames"][0]).reshape(-1, 3)
            rigid["frames"] = [(first - [0, 0.04 * k, 0]).reshape(-1).tolist() for k in range(20)]
            for name, d in (("blob", good), ("rigid", rigid), ("sail", dict(good, recipe="cloth")), ("junk", [1, 2])):
                with open(os.path.join(tmp, "seq", f"{name}.json"), "w", encoding="utf-8") as fh:
                    json.dump(d, fh)

            def proved(layer):
                return M.proved(m, [dict({"kind": "mesh", "pivot": "origin", "life": 1}, **layer)], Empty(), tmp, "s") is not None

            self.assertTrue(proved({"shape": "seq", "params": {"seq": "blob"}}))
            self.assertFalse(proved({"shape": "seq", "pivot": None, "params": {"seq": "blob"}}))     # stage 26: not sitting by its own origin
            self.assertFalse(proved({"shape": "seq", "pivot": "base", "params": {"seq": "blob"}}))
            self.assertFalse(proved({"shape": "seq", "params": {"seq": "blob", "loop": True}}))
            self.assertFalse(proved({"shape": "orb", "params": {"seq": "blob"}}))
            self.assertFalse(proved({"shape": "seq", "life": 0.3, "params": {"seq": "blob"}}))   # gone before it lands
            self.assertFalse(proved({"shape": "seq", "life": 1, "params": {"seq": "blob", "fps": 6}}))
            for bad in ("rigid", "sail", "junk", "nothing"):
                self.assertFalse(proved({"shape": "seq", "params": {"seq": bad}}), bad)


if __name__ == "__main__":
    unittest.main()
