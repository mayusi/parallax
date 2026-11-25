"""Unit tests of the hair bake (kit/vfx/hair.py) and the seq shape's strips (read from the two runtimes' text).
Run: python -m pytest kit/test/python/test_vfx_hair.py -q"""
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
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import hair as H  # noqa: E402
import methods as M  # noqa: E402


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = H.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def args(**over):
    a = {"root": "line", "move": "sway", "loop": False, "wind": [0.0, 0.0, 0.0], "strands": 6, "length": 3.0, "width": 0.25, "head": 1.2, "amount": 1.5,
         "gust": 0.5, "stiff": 0.15, "gravity": 40.0, "frames": 24, "fps": 24, "segments": 6, "drag": 1.5, "damp": 1.0}
    a.update(over)
    return a


def as_file(a):
    mids, where = H.simulate(a)
    return {"recipe": "hair", "args": a, "cols": 1, "rows": a["segments"], "strips": a["strands"],
            "frames": [[round(float(x) / a["length"], 4) for x in H.ribbons(m, a, w).reshape(-1)] for m, w in zip(mids, where)]}, mids


class TheStrands(unittest.TestCase):
    def test_roots_are_on_the_top_of_the_head_or_along_the_line(self):
        pos, out = H.roots(args(root="cap", strands=20))
        self.assertTrue(np.allclose(np.linalg.norm(pos, axis=1), 0.6))
        self.assertTrue((pos[:, 1] > 0).all())                                             # the top half
        self.assertTrue(np.allclose(np.linalg.norm(out, axis=1), 1))
        pos, out = H.roots(args(root="line", strands=5))
        self.assertTrue(np.allclose(pos[:, 0], [-0.48, -0.24, 0, 0.24, 0.48]))
        self.assertTrue((out == [0, -1, 0]).all())

    def test_a_strand_keeps_its_length_and_its_root(self):
        a = args()
        mids, where = H.simulate(a)
        for m, (angle, slide) in zip(mids, where):
            length = np.linalg.norm(m[:, 1:] - m[:, :-1], axis=-1).sum(-1)
            self.assertTrue((np.abs(length - 3.0) < 0.1).all())
            self.assertTrue(np.allclose(m[:, 0], H.placed(H.roots(a)[0], angle, slide)))

    def test_a_fringe_with_nothing_to_move_it_hangs_straight_down(self):
        mids, _ = H.simulate(args(move="none"))
        tip = mids[-1][:, -1] - mids[-1][:, 0]
        self.assertTrue(np.allclose(tip, [0, -3.0, 0], atol=0.03))

    def test_the_wind_carries_it_and_the_tips_overshoot_a_sway(self):
        mids, _ = H.simulate(args(move="none", wind=[0.0, 0.0, 10.0], gust=0.0))
        self.assertGreater(float(mids[-1][:, -1, 2].mean()), 0.3)
        mids, _ = H.simulate(args())
        m = np.array(mids)
        self.assertGreater(float(np.ptp(m[:, :, -1, 0].mean(1))), 1.05 * float(np.ptp(m[:, :, 0, 0].mean(1))))

    def test_hair_on_a_head_stays_out_of_it(self):
        mids, where = H.simulate(args(root="cap", move="toss", amount=0.8, strands=10))
        for m in mids:
            self.assertGreater(float(np.linalg.norm(m, axis=-1).min()), 0.6 * 0.97)

    def test_the_same_asks_give_the_same_frames(self):
        a, b = H.simulate(args())[0], H.simulate(args())[0]
        self.assertTrue(all(np.array_equal(x, y) for x, y in zip(a, b)))

    def test_it_swings_as_much_a_second_at_another_frame_rate(self):
        per = []
        for fps in (12, 24, 60):
            m = np.array(H.simulate(args(fps=fps, frames=fps * 2))[0])
            per.append(float(np.ptp(m[:, :, -1, 0].mean(1))))
        self.assertLess(max(per) / min(per), 1.03, per)
        low = [float(np.array(H.simulate(args(fps=fps, frames=fps))[0])[-1][:, -1, 1].mean()) for fps in (12, 25, 30, 60)]   # the same second, read at four rates
        self.assertLess(max(low) - min(low), 0.01, low)

    def test_no_ribbon_turns_over_where_a_side_worked_out_afresh_did(self):
        for over in ({"root": "cap", "move": "toss", "amount": 2.5, "strands": 10}, {"root": "cap", "move": "toss", "gravity": 0.0, "strands": 10},
                     {"move": "none", "wind": [0.0, 0.0, 80.0], "gravity": 10.0}):
            a = args(**over)
            mids, where = H.simulate(a)
            rib = np.array([H.ribbons(m, a, w) for m, w in zip(mids, where)]).reshape(len(mids), a["strands"], 7, 2, 3)
            across = rib[:, :, :, 1] - rib[:, :, :, 0]
            across = across / np.linalg.norm(across, axis=-1, keepdims=True)
            self.assertGreater(float((across[:, :, 1:] * across[:, :, :-1]).sum(-1).min()), 0, over)   # row to row
            self.assertGreater(float((across[1:] * across[:-1]).sum(-1).min()), 0, over)               # frame to frame

    def test_a_ribbon_is_two_points_a_row_about_the_strands_middle(self):
        a = args()
        mid = H.simulate(a)[0][3]
        rib = H.ribbons(mid, a, (0.0, 0.0)).reshape(6, 7, 2, 3)
        self.assertTrue(np.allclose(rib.mean(2), mid))
        width = np.linalg.norm(rib[:, :, 1] - rib[:, :, 0], axis=-1)
        self.assertTrue(np.allclose(width[:, 0], 0.25))
        self.assertTrue(np.allclose(width[:, -1], 0.25 * 0.15))


class TheChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.file, _ = as_file(args())

    def failed(self, d, **kw):
        return [c["name"] for c in H.check(d, **kw) if not c["ok"]]

    def shaped(self, fn):
        d = copy.deepcopy(self.file)
        g = np.array(d["frames"]).reshape(len(d["frames"]), 6, 7, 2, 3)
        fn(g)
        d["frames"] = [f.reshape(-1).tolist() for f in g]
        return self.failed(d)

    def test_a_good_bake_passes(self):
        self.assertEqual(self.failed(self.file), [])

    def test_still_hair(self):
        self.assertIn("the hair moves", self.shaped(lambda g: g.__setitem__(slice(None), g[0:1])))

    def test_a_strand_pulled_longer(self):
        def pull(g):
            g[5, 2, :, :, 1] *= 1.3
        self.assertIn("no strand stretches", self.shaped(pull))

    def test_a_root_that_left_its_body(self):
        def move(g):
            g[5:, 2, :, :, 0] += 0.2
        self.assertIn("the roots stay on one body", self.shaped(move))

    def test_hair_as_one_stiff_piece(self):
        def rigid(g):
            shift = g[:, :, 0:1].mean(3, keepdims=True) - g[0:1, :, 0:1].mean(3, keepdims=True)   # each strand's root's own travel
            g[:] = g[0:1] + shift
        self.assertEqual(self.shaped(rigid), ["the hair moves on its body"])

    def test_hair_tilted_as_one_piece_about_another_axis(self):
        def tilt(g):
            first = g[0].copy()
            for f in range(len(g)):
                t = 0.5 * math.sin(2 * math.pi * f / len(g))
                c, s = math.cos(t), math.sin(t)
                g[f] = np.stack([first[..., 0], first[..., 1] * c - first[..., 2] * s, first[..., 1] * s + first[..., 2] * c], -1)   # about x
        self.assertIn("the hair moves on its body", self.shaped(tilt))

    def test_a_ribbon_turned_over(self):
        def flip(g):
            g[6, 2, 3:] = g[6, 2, 3:, ::-1].copy()                                          # from row 3 on, left and right changed places
        self.assertIn("no ribbon turns over", self.shaped(flip))

    def test_a_jump(self):
        def jump(g):
            g[7, 1, -1, :, 2] += 0.6
        self.assertIn("no jump", self.shaped(jump))

    def test_a_layer_that_loops_a_bake_that_does_not_and_one_far_off_its_speed(self):
        self.assertEqual(self.failed(self.file, loop=True), ["the loop's seam"])
        self.assertEqual(self.failed(self.file, play=4), ["it is played at its own speed"])
        looped, _ = as_file(args(loop=True))
        self.assertEqual(self.failed(looped, loop=True), [])

    def test_what_is_no_hair_bake_is_said_so(self):
        for spoil in (lambda d: d.update(recipe="cloth"), lambda d: d.update(cols=2), lambda d: d.update(strips=5), lambda d: d.pop("strips"),
                      lambda d: d["frames"][3].pop(), lambda d: d.update(frames=d["frames"][:1]), lambda d: d["frames"][2].__setitem__(4, float("nan"))):
            d = copy.deepcopy(self.file)
            spoil(d)
            self.assertEqual(self.failed(d), ["a hair bake"])


class TheCommand(unittest.TestCase):
    def test_it_writes_strips_and_a_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, said = run(["mane", "--root", "line", "--move", "sway", "--strands", "6", "--frames", "24", "--segments", "6", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 0, said)
            d = json.load(open(os.path.join(tmp, "mane.json"), encoding="utf-8"))
            self.assertEqual((d["recipe"], d["cols"], d["rows"], d["strips"], len(d["frames"]), len(d["frames"][0])), ("hair", 1, 6, 6, 24, 6 * 7 * 2 * 3))
            self.assertTrue(os.path.isfile(os.path.join(tmp, "mane.png")))

    def test_a_refused_bake_writes_nothing_and_keeps_an_older_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, said = run(["calm", "--move", "none", "--root", "line", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 1)
            self.assertEqual(os.listdir(tmp), [])
            self.assertEqual(run(["m", "--root", "line", "--strands", "4", "--frames", "24", "--out-dir", tmp, "--look-dir", tmp])[0], 0)
            before = open(os.path.join(tmp, "m.json"), encoding="utf-8").read()
            code, said = run(["m", "--root", "line", "--strands", "64", "--frames", "64", "--segments", "16", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 1)
            self.assertIn("KB of frames", said["summary"])
            self.assertEqual(open(os.path.join(tmp, "m.json"), encoding="utf-8").read(), before)

    def test_wrong_asks_are_said_in_words(self):
        for argv, word in ((["Mane"], "lowercase"), (["s", "--root", "tail"], "--root is one of"), (["s", "--move", "spin"], "--move is one of"),
                           (["s", "--width", "2", "--length", "3"], "0.45 of the --length"), (["s", "--width", "0.01", "--length", "100"], "0.45 of the --length"), (["s", "--strands", "1"], "--strands is a whole number"),
                           (["s", "--wind", "1,2"], "--wind x,y,z"), (["s", "--amount", "5"], "radians each way"), (["s", "--curl", "1"], "not an option"),
                           (["s", "--loop", "--frames", "12"], "at least a second"), (["s", "--stiff"], "no value")):
            code, said = run(argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, said["summary"], argv)


class TheStrips(unittest.TestCase):
    """the seq shape builds one grid a strip, in the frames' own order, in the game and in the player (their text)"""

    def test_both_runtimes_read_strips_the_same_way(self):
        lua = open(os.path.join(ROOT, "src", "kit", "VfxMesh.luau"), encoding="utf-8").read()
        js = open(os.path.join(ROOT, "kit", "vfx", "player", "player.js"), encoding="utf-8").read()
        self.assertIn("local per = w * (d.rows + 1) * 3", lua)
        self.assertIn("local k = s * per + (j * w + i) * 3", lua)
        self.assertIn("per = w * (d.rows + 1) * 3", js)
        self.assertIn("const k = s * per + (Math.round(v * d.rows) * w + Math.round(u * d.cols)) * 3", js)
        # the file's own order is that order: strand s, row j (root to tip), across i
        a = args()
        d, mids = as_file(a)
        per = 2 * 7 * 3
        for s, j, i in ((0, 0, 0), (2, 3, 1), (5, 6, 0)):
            k = s * per + (j * 2 + i) * 3
            want = np.array(d["frames"][4]).reshape(6, 7, 2, 3)[s, j, i]
            self.assertTrue(np.allclose(d["frames"][4][k:k + 3], want, atol=1e-4))


class TheRegister(unittest.TestCase):
    def test_hair_is_a_bake_that_is_there_and_passes(self):
        m = M.load()[1]["hair"]
        self.assertEqual(m["state"], "has")
        good, _ = as_file(args())

        class Empty:
            def get(self, key):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "seq"))
            for name, d in (("mane", good), ("still", dict(good, frames=[good["frames"][0]] * 24)), ("sail", dict(good, recipe="cloth"))):
                with open(os.path.join(tmp, "seq", f"{name}.json"), "w", encoding="utf-8") as fh:
                    json.dump(d, fh)

            def proved(layer):
                return M.proved(m, [dict({"kind": "mesh", "pivot": "origin", "life": 1}, **layer)], Empty(), tmp, "s") is not None

            self.assertTrue(proved({"shape": "seq", "params": {"seq": "mane"}}))
            self.assertFalse(proved({"shape": "seq", "pivot": None, "params": {"seq": "mane"}}))     # stage 26: not sitting by its own origin
            self.assertFalse(proved({"shape": "seq", "pivot": "base", "params": {"seq": "mane"}}))
            self.assertFalse(proved({"shape": "seq", "params": {"seq": "mane", "loop": True}}))
            self.assertFalse(proved({"shape": "seq", "life": 0.2, "params": {"seq": "mane"}}))
            for bad in ("still", "sail", "nothing"):
                self.assertFalse(proved({"shape": "seq", "params": {"seq": bad}}), bad)


if __name__ == "__main__":
    unittest.main()
