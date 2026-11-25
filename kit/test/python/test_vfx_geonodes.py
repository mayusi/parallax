"""Unit tests of the Geometry Nodes bake (kit/vfx/geonodes.py; the tree runs in Blender through geonodes_bake.py).
The tests that bake are SKIPPED where there is no Blender; the checks of a file are tested on made files everywhere.
Run: python -m pytest kit/test/python/test_vfx_geonodes.py -q"""
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
import geonodes as G  # noqa: E402
import methods as M  # noqa: E402

BLENDER = G.blender()


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = G.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def ripple_file(frames=16, n=12, waves=3.0, speed=1.5, amount=0.08, fps=24, loop=False):
    """a ripple as the tree makes it, made here from its formula (no Blender)"""
    xs = np.linspace(-0.5, 0.5, n + 1)
    x, z = np.meshgrid(xs, xs[::-1])
    r = np.hypot(x, z)
    out = []
    for f in range(frames):
        t = (f + 1) / fps
        y = amount * np.sin(2 * math.pi * (r * waves - t * speed)) * np.maximum(1 - 2 * r, 0)
        out.append(np.stack([x, y, z], -1).round(4).reshape(-1).tolist())
    return {"recipe": "geonodes", "args": {"recipe": "ripple", "fps": fps, "loop": loop, "waves": waves, "speed": speed, "amount": amount},
            "blender": "made", "nodes": ["GeometryNodeMeshGrid", "GeometryNodeSetPosition"], "cols": n, "rows": n, "frames": out}


def scatter_file(frames=24, count=12, size=0.08, speed=0.6, rise=0.2, spin=2.0, fps=24):
    rng = np.random.default_rng(4)
    rad, ang = 0.45 * np.sqrt(rng.uniform(0, 1, count)), rng.uniform(0, 2 * math.pi, count)
    cx, cz = rad * np.cos(ang), rad * np.sin(ang)
    out = []
    for f in range(frames):
        t = (f + 1) / fps
        s = size * np.clip((t * speed - rad) / rise, 0.02, 1) / 2
        a = t * spin + np.arange(count) * 2.399963
        quad = []
        for dx, dz in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            quad.append(np.stack([cx + s * (dx * np.cos(a) - dz * np.sin(a)), np.zeros(count), cz + s * (dx * np.sin(a) + dz * np.cos(a))], -1))
        out.append(np.stack(quad, 1).round(4).reshape(-1).tolist())
    return {"recipe": "geonodes", "args": {"recipe": "scatter", "fps": fps, "loop": False}, "blender": "made",
            "nodes": ["GeometryNodeInstanceOnPoints"], "cols": 1, "rows": 1, "strips": count, "frames": out}


def failed(d, **kw):
    return [c["name"] for c in G.check(d, **kw) if not c["ok"]]


class TheChecks(unittest.TestCase):
    def test_made_files_of_both_recipes_pass(self):
        self.assertEqual(failed(ripple_file()), [])
        self.assertEqual(failed(scatter_file()), [])

    def spoilt(self, d, fn):
        d = copy.deepcopy(d)
        fn(d)
        return failed(d)

    def test_a_ripple_that_is_wrong(self):
        r = ripple_file()
        self.assertIn("the mesh moves", self.spoilt(r, lambda d: d.update(frames=[d["frames"][0]] * 16)))
        self.assertIn("the grid stays where it is", self.spoilt(r, lambda d: d["frames"][5].__setitem__(0, d["frames"][5][0] + 0.05)))
        self.assertIn("the grid stays where it is", self.spoilt(r, lambda d: d.update(frames=[[x * 2 for x in f] for f in d["frames"]])))   # a ground 2 wide
        flat = ripple_file(amount=0.002)
        self.assertIn("rings that die at the rim", failed(flat))

        def lift_rim(d):
            for f in d["frames"]:
                f[1] = 0.05                                                                 # the first point is a corner of the ground
        self.assertIn("rings that die at the rim", self.spoilt(r, lift_rim))
        self.assertIn("no jump", self.spoilt(r, lambda d: d["frames"][5].__setitem__(13 * 6 * 3 + 1, 0.6)))
        self.assertIn("the rings run out", self.spoilt(r, lambda d: d.update(frames=d["frames"][::-1])))             # played backwards: they run in

        def dome(d):                                                                        # a bump that never goes under the ground
            for f in d["frames"]:
                for k in range(1, len(f), 3):
                    f[k] = abs(f[k])
        self.assertIn("rings that die at the rim", self.spoilt(r, dome))

    def test_a_ripples_loop(self):
        self.assertEqual(failed(ripple_file(frames=16, speed=1.5, loop=True), loop=True), [])       # 1.5 a second for 16 / 24 s: one whole ring
        self.assertEqual(failed(ripple_file(frames=16, speed=1.2, loop=True), loop=True), ["the loop's seam"])
        self.assertEqual(failed(ripple_file(), loop=True), ["the loop's seam"])                     # baked without --loop

    def test_a_scatter_that_is_wrong(self):
        s = scatter_file()

        def shape(fn):
            def go(d):
                q = np.array(d["frames"]).reshape(24, 12, 4, 3)
                fn(q)
                d["frames"] = [f.reshape(-1).tolist() for f in q]
            return go

        self.assertIn("every strip is a square on the ground", self.spoilt(s, shape(lambda q: q[20, 3, 1].__iadd__([0.02, 0, 0]))))
        self.assertIn("every strip is a square on the ground", self.spoilt(s, shape(lambda q: q[:, :, :, 1].__iadd__(0.05))))
        self.assertIn("the instances keep their places", self.spoilt(s, shape(lambda q: q[10:, 4].__iadd__([0.03, 0, 0.01]))))
        self.assertIn("a front that runs out", self.spoilt(s, lambda d: d.update(frames=d["frames"][::-1])))          # played backwards: they shrink
        self.assertIn("a front that runs out", failed(scatter_file(frames=6)))                                        # cut off before it comes
        self.assertEqual(failed(s, loop=True), ["it is played once"])
        self.assertEqual(failed(s, play=4), ["it is played at its own speed"])

    def test_what_is_no_geometry_nodes_bake_is_said_so(self):
        r = ripple_file()
        for spoil in (lambda d: d.update(recipe="cloth"), lambda d: d["args"].update(recipe="spiral"), lambda d: d.update(nodes=["ShaderNodeMath"]),
                      lambda d: d.pop("nodes"), lambda d: d["frames"][3].pop(), lambda d: d.update(frames=d["frames"][:1]), lambda d: d.update(strips=3),
                      lambda d: d["frames"][2].__setitem__(4, float("nan")), lambda d: d.update(cols=True)):
            self.assertEqual(self.spoilt(r, spoil), ["a geometry-nodes bake"])
        self.assertEqual(self.spoilt(scatter_file(), lambda d: d.update(cols=2)), ["a geometry-nodes bake"])


class TheCommand(unittest.TestCase):
    def test_wrong_asks_are_said_in_words_before_blender_is_asked(self):
        for argv, word in ((["Ring"], "lowercase"), (["s", "--recipe", "spiral"], "--recipe is one of"), (["s", "--waves", "40"], "--waves is a number"),
                           (["s", "--recipe", "scatter", "--loop"], "--loop is for a ripple"), (["s", "--recipe", "scatter", "--count", "200"], "--count"), (["s", "--recipe", "scatter", "--count", "4"], "--count"),
                           (["s", "--speed", "20"], "quarter of a ring a frame"), (["s", "--waves", "12"], "under 5 points a ring"),
                           (["s", "--loop", "--speed", "0.1", "--fps", "60", "--frames", "64"], "far from the 0.1 asked"),
                           (["s", "--blender", "C:/nope/blender.exe"], "no Blender at C:/nope/blender.exe"),
                           (["s", "--glow", "1"], "not an option"), (["s", "--frames"], "no value"), (["s", "--frames", "1"], "--frames is a whole number")):
            code, said = run(argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, said["summary"], argv)

    def test_no_blender_is_said(self):
        old, G.blender = G.blender, lambda asked=None: None
        try:
            code, said = run(["ring"])
        finally:
            G.blender = old
        self.assertEqual(code, 1)
        self.assertIn("no Blender", said["summary"])

    def test_a_loop_makes_the_rings_come_round_a_whole_number_of_times(self):
        a = G.arguments({"--recipe": "ripple", "--frames": "32", "--fps": "24", "--cols": "20", "--rows": "20", "--waves": "3", "--speed": "1.4", "--amount": "0.08",
                         "--loop": True})
        self.assertAlmostEqual(a["speed"] * 32 / 24, round(a["speed"] * 32 / 24))
        self.assertAlmostEqual(a["speed"], 1.5)


@unittest.skipUnless(BLENDER, "no Blender on this machine: the tree was not run")
class TheTree(unittest.TestCase):
    def test_blender_bakes_what_the_made_files_are(self):
        """the tree's own frames are the formula's (so the made files above ARE what Blender gives)"""
        with tempfile.TemporaryDirectory() as tmp:
            code, said = run(["ring", "--recipe", "ripple", "--waves", "2", "--frames", "16", "--cols", "12", "--rows", "12", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 0, said)
            got = json.load(open(os.path.join(tmp, "ring.json"), encoding="utf-8"))
            want = ripple_file(waves=2.0)
            self.assertLess(float(np.abs(np.array(got["frames"]) - np.array(want["frames"])).max()), 0.002)       # every point, every frame, the same ORDER
            self.assertIn("GeometryNodeSetPosition", got["nodes"])
            self.assertTrue(os.path.isfile(os.path.join(tmp, "ring.png")))
            code, said = run(["shards", "--recipe", "scatter", "--frames", "24", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 0, said)
            got = json.load(open(os.path.join(tmp, "shards.json"), encoding="utf-8"))
            self.assertEqual(len(got["frames"][0]), got["strips"] * 12)
            self.assertEqual(failed(got), [])
            code, said = run(["soon", "--recipe", "scatter", "--frames", "4", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 1)
            self.assertFalse(os.path.exists(os.path.join(tmp, "soon.json")))


class TheRegister(unittest.TestCase):
    def test_geometry_nodes_is_a_bake_that_is_there_and_passes(self):
        m = M.load()[1]["geometry_nodes"]
        self.assertEqual(m["state"], "has")

        class Empty:
            def get(self, key):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "seq"))
            for name, d in (("ring", ripple_file()), ("shards", scatter_file()), ("still", dict(ripple_file(), frames=[ripple_file()["frames"][0]] * 16)),
                            ("mane", dict(ripple_file(), recipe="hair"))):
                with open(os.path.join(tmp, "seq", f"{name}.json"), "w", encoding="utf-8") as fh:
                    json.dump(d, fh)

            def proved(layer):
                return M.proved(m, [dict({"kind": "mesh", "pivot": "origin", "life": 1}, **layer)], Empty(), tmp, "s") is not None

            self.assertTrue(proved({"shape": "seq", "params": {"seq": "ring"}}))
            self.assertFalse(proved({"shape": "seq", "pivot": None, "params": {"seq": "ring"}}))     # stage 26: not sitting by its own origin
            self.assertFalse(proved({"shape": "seq", "pivot": "base", "params": {"seq": "ring"}}))
            self.assertTrue(proved({"shape": "seq", "params": {"seq": "shards"}}))
            self.assertFalse(proved({"shape": "seq", "params": {"seq": "shards", "loop": True}}))
            self.assertFalse(proved({"shape": "seq", "life": 0.1, "params": {"seq": "ring"}}))
            for bad in ("still", "mane", "nothing"):
                self.assertFalse(proved({"shape": "seq", "params": {"seq": bad}}), bad)


if __name__ == "__main__":
    unittest.main()
