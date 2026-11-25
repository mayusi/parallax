"""Unit tests of the cloth bake (kit/vfx/cloth.py) and the solver under it (kit/vfx/pbd.py).
Run: python -m pytest kit/test/python/test_vfx_cloth.py -q"""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import cloth as C  # noqa: E402
import methods as M  # noqa: E402
import pbd  # noqa: E402


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = C.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def args(**over):
    a = {"size": [6.0, 4.0], "wind": [0.0, 0.0, 14.0], "pin": "top", "start": "hang", "loop": False, "gust": 0.5, "gravity": 30.0, "frames": 12,
         "fps": 24, "cols": 8, "rows": 5, "seed": 1.0, "drag": 0.6, "damp": 0.6}
    a.update(over)
    return a


def as_file(a, frames):
    unit = max(a["size"])
    return {"recipe": "cloth", "args": a, "cols": a["cols"], "rows": a["rows"], "frames": [[round(float(x) / unit, 4) for x in f.reshape(-1)] for f in frames]}


class TheSolver(unittest.TestCase):
    def test_no_point_is_twice_in_a_set_and_no_link_is_lost(self):
        links = C.links(6, 4, 3.0, 2.0)
        sets = pbd.groups(links, 35)
        self.assertEqual(sum(len(s[0]) for s in sets), len(links))
        for a, b, _, _ in sets:
            both = list(a) + list(b)
            self.assertEqual(len(both), len(set(both)))

    def test_a_stretched_link_comes_back_and_a_held_point_stays(self):
        pos = np.array([[0.0, 0, 0], [3.0, 0, 0]])
        sets = pbd.groups([(0, 1, 1.0, 1.0)], 2)
        pbd.solve(pos, np.array([0.0, 1.0]), sets, 1)
        self.assertEqual(pos[0].tolist(), [0, 0, 0])
        self.assertAlmostEqual(pos[1][0], 1.0)
        pos = np.array([[0.0, 0, 0], [3.0, 0, 0]])
        pbd.solve(pos, np.array([1.0, 1.0]), sets, 1)                        # both free: each gives half
        self.assertAlmostEqual(pos[0][0], 1.0)
        self.assertAlmostEqual(pos[1][0], 2.0)

    def test_a_point_keeps_going_and_slows_by_the_damping(self):
        pos, prev = np.array([[1.0, 0, 0]]), np.array([[0.0, 0, 0]])
        self.assertAlmostEqual(pbd.step(pos, prev, np.zeros((1, 3)), 0.1, 0.0)[0][0], 2.0)
        self.assertAlmostEqual(pbd.step(pos, prev, np.zeros((1, 3)), 0.1, 5.0)[0][0], 1.5)
        self.assertAlmostEqual(pbd.step(pos, prev, np.array([[0.0, -10, 0]]), 0.1, 0.0)[0][1], -0.1)


class TheSheet(unittest.TestCase):
    def test_in_no_wind_it_hangs_straight_down_from_its_top(self):
        fr = C.simulate(args(wind=[0.0, 0, 0], gust=0.0))
        g = fr[-1].reshape(6, 9, 3)
        self.assertLess(np.abs(g[..., 2]).max(), 1e-6)                      # it never leaves its plane
        self.assertAlmostEqual(float(g[-1, :, 1].mean()), -4.0, delta=0.2)   # the free edge a sheet's height below
        self.assertEqual(g[0, :, 1].tolist(), [0.0] * 9)

    def test_the_wind_pushes_it_the_way_it_blows_and_more_wind_pushes_more(self):
        z = [float(np.mean([f.reshape(6, 9, 3)[-1, :, 2].mean() for f in C.simulate(args(wind=[0.0, 0, w], gust=0.0))])) for w in (6.0, 14.0, 30.0)]
        self.assertGreater(z[0], 0.05)
        self.assertLess(z[0], z[1])
        self.assertLess(z[1], z[2])
        back = C.simulate(args(wind=[0.0, 0, -14.0], gust=0.0))
        self.assertLess(float(back[-1].reshape(6, 9, 3)[-1, :, 2].mean()), -0.05)

    def test_the_held_points_are_the_ones_the_pin_names(self):
        self.assertEqual(len(C.held(8, 5, "top")), 9)
        self.assertEqual(len(C.held(8, 5, "left")), 6)
        self.assertEqual(C.held(8, 5, "corners"), [(0, 0), (8, 0)])
        for pin in C.PINS:
            fr = C.simulate(args(pin=pin))
            idx = [j * 9 + i for i, j in C.held(8, 5, pin)]
            for f in fr:
                self.assertTrue(np.array_equal(f[idx], fr[0][idx]), pin)

    def test_a_sheet_let_go_flat_starts_level_and_falls(self):
        fr = C.simulate(args(start="flat", wind=[0.0, 0, 0], frames=24))
        self.assertEqual(float(np.abs(fr[0][:, 1]).max()), 0.0)
        self.assertAlmostEqual(float(fr[0][:, 2].max()), 4.0)
        self.assertLess(float(fr[-1].reshape(6, 9, 3)[-1, :, 1].mean()), -1.0)

    def test_the_same_asks_give_the_same_frames_and_another_seed_others(self):
        a, b, c = C.simulate(args()), C.simulate(args()), C.simulate(args(seed=7.0))
        self.assertTrue(all(np.array_equal(x, y) for x, y in zip(a, b)))
        self.assertFalse(all(np.array_equal(x, y) for x, y in zip(a, c)))

    def test_a_loop_has_as_many_frames_as_asked_and_its_ends_meet(self):
        a = args(pin="left", wind=[16.0, 0, 3], loop=True, frames=24)
        fr = C.simulate(a)
        self.assertEqual(len(fr), 24)
        rows = {c["name"]: c for c in C.check(as_file(a, fr))}
        self.assertTrue(rows["the loop's seam"]["ok"], rows["the loop's seam"])
        self.assertTrue(rows["it is a sheet"]["ok"], rows["it is a sheet"])              # the blend does not shrink it
        steps = np.sqrt(((np.array(fr[1:]) - np.array(fr[:-1])) ** 2).sum(-1)).max(1)
        seam = float(np.sqrt(((fr[0] - fr[-1]) ** 2).sum(-1)).max())
        self.assertLess(seam, 2.5 * float(np.percentile(steps, 75)))                      # against a usual frame, not the blend's own


class TheChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = args(frames=16)
        cls.file = as_file(cls.a, C.simulate(cls.a))

    def failed(self, d, **kw):
        return [c["name"] for c in C.check(d, **kw) if not c["ok"]]

    def test_a_good_bake_passes(self):
        self.assertEqual(self.failed(self.file), [])

    def test_a_still_sheet(self):
        d = copy.deepcopy(self.file)
        d["frames"] = [d["frames"][0]] * 16
        self.assertEqual(self.failed(d), ["the sheet moves"])

    def test_what_is_not_this_sheet(self):
        d = copy.deepcopy(self.file)
        rng = np.random.default_rng(1)
        first = np.array(d["frames"][0])
        free = np.arange(len(first)) >= 27                                               # (the held top row is left where it is)
        d["frames"] = [np.where(free, first * 0.2 + rng.uniform(-0.005, 0.005, len(first)), first).round(4).tolist() for _ in range(16)]
        self.assertIn("it is a sheet", self.failed(d))                                   # every free point near one place, jittering

    def test_a_layer_that_plays_it_far_from_its_speed(self):
        self.assertEqual(self.failed(self.file, play=2), ["it is played at its own speed"])
        self.assertEqual(self.failed(self.file, play=100), ["it is played at its own speed"])
        self.assertEqual(self.failed(self.file, play=30), [])

    def test_a_bake_at_60_frames_a_second_moves_as_much_a_second(self):
        per = []
        for fps in (12, 24, 60):
            fr = np.array(C.simulate(args(fps=fps, frames=fps)))
            per.append(float(np.sqrt(((fr[1:] - fr[:-1]) ** 2).sum(-1)).mean()) * fps)
        self.assertLess(max(per) / min(per), 1.5)

    def test_a_stretched_frame(self):
        d = copy.deepcopy(self.file)
        d["frames"][5] = [x * 1.3 if k % 3 == 1 else x for k, x in enumerate(d["frames"][5])]   # pulled 30 % longer downward
        self.assertIn("the cloth does not stretch", self.failed(d))

    def test_a_held_point_that_moved(self):
        d = copy.deepcopy(self.file)
        d["frames"][5][2] += 0.01
        self.assertIn("the held edge stays", self.failed(d))

    def test_a_jump(self):
        d = copy.deepcopy(self.file)
        k = (5 * 9 + 4) * 3
        d["frames"][7][k] += 0.4
        self.assertIn("no jump between frames", self.failed(d))

    def test_a_layer_that_loops_a_bake_that_does_not(self):
        self.assertEqual(self.failed(self.file, loop=True), ["the loop's seam"])
        self.assertEqual(self.failed(self.file, loop=False), [])

    def test_what_is_no_cloth_bake_is_said_so(self):
        for spoil in (lambda d: d.update(recipe="billow"), lambda d: d.update(frames=d["frames"][:1]), lambda d: d["frames"][3].pop(),
                      lambda d: d["args"].update(pin="middle"), lambda d: d["args"].update(size=[6, 0]), lambda d: d.update(cols="8"),
                      lambda d: d["frames"][2].__setitem__(4, float("nan")), lambda d: d["frames"][2].__setitem__(4, "x"), lambda d: d.pop("args")):
            d = copy.deepcopy(self.file)
            spoil(d)
            self.assertEqual(self.failed(d), ["a cloth bake"])


class TheCommand(unittest.TestCase):
    def test_it_writes_the_sequence_the_seq_shape_reads_and_a_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, said = run(["sail", "--frames", "12", "--cols", "8", "--rows", "5", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 0, said)
            d = json.load(open(os.path.join(tmp, "sail.json"), encoding="utf-8"))
            self.assertEqual((d["recipe"], d["cols"], d["rows"], len(d["frames"]), len(d["frames"][0])), ("cloth", 8, 5, 12, 9 * 6 * 3))
            self.assertLessEqual(max(abs(x) for f in d["frames"] for x in f), 1.2)       # unit size: the layer's scale sizes it
            self.assertTrue(os.path.isfile(os.path.join(tmp, "sail.png")))
            self.assertIn('"seq": "sail", "fps": 24', said["summary"])

    def test_a_refused_bake_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, said = run(["calm", "--wind", "0,0,0", "--frames", "8", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 1)
            self.assertIn("hangs still", said["summary"])
            self.assertEqual(os.listdir(tmp), [])

    def test_wrong_asks_are_said_in_words(self):
        for argv, word in ((["Sail"], "lowercase"), (["a", "b"], "ONE"), (["s", "--pin", "middle"], "--pin is one of"), (["s", "--wind", "1,2"], "--wind x,y,z"),
                           (["s", "--size", "6"], "--size w,h"), (["s", "--size", "0,4"], "0.2 to 200"), (["s", "--frames", "900"], "--frames is a whole number"),
                           (["s", "--cols", "2.5"], "--cols is a whole number"), (["s", "--gust", "3"], "--gust is a number"), (["s", "--tear", "1"], "not an option"),
                           (["s", "--wind"], "no value"), (["s", "--loop", "--start", "flat"], "does not come back"), (["s", "--start", "up"], "--start is"),
                           (["s", "--wind", "0,0,500"], "at most 120"), (["s", "--wind", "nan,0,0"], "--wind x,y,z")):
            code, said = run(argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, said["summary"], argv)


class TheRegister(unittest.TestCase):
    def test_cloth_is_a_bake_that_is_there_and_passes(self):
        m = M.load()[1]["cloth"]
        self.assertEqual(m["state"], "has")
        a = args(frames=16)
        good = as_file(a, C.simulate(a))

        class Empty:
            def get(self, key):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "seq"))
            still = copy.deepcopy(good)
            still["frames"] = [still["frames"][0]] * 16
            for name, d in (("sail", good), ("still", still), ("puff", dict(good, recipe="billow")), ("junk", "not a bake")):
                with open(os.path.join(tmp, "seq", f"{name}.json"), "w", encoding="utf-8") as fh:
                    json.dump(d, fh)

            def proved(layer):
                return M.proved(m, [dict({"kind": "mesh", "pivot": "origin", "life": 1}, **layer)], Empty(), tmp, "s") is not None

            self.assertTrue(proved({"shape": "seq", "params": {"seq": "sail"}}))
            self.assertFalse(proved({"shape": "seq", "pivot": None, "params": {"seq": "sail"}}))     # stage 26: not sitting by its own origin
            self.assertFalse(proved({"shape": "seq", "pivot": "base", "params": {"seq": "sail"}}))
            self.assertFalse(proved({"shape": "seq", "params": {"seq": "sail", "loop": True}}))   # baked without --loop
            self.assertFalse(proved({"shape": "ring", "params": {"seq": "sail"}}))                # the file is not played
            self.assertFalse(proved({"shape": "seq", "params": {"seq": "sail", "fps": 2}}))       # a near-still sheet
            for bad in ("still", "puff", "junk", "nothing", "Sail"):
                self.assertFalse(proved({"shape": "seq", "params": {"seq": bad}}), bad)
            self.assertFalse(proved({"shape": "seq"}))
            self.assertIn("cloth bake", M.say(m["proof"][0]))


if __name__ == "__main__":
    unittest.main()
