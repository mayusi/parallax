"""kit/vfx/fracture.py - a slab cut into the pieces it breaks into - on slabs whose answer is known. What is proven is
what a plan is trusted for: the pieces tile the slab exactly and are convex, they are smaller where the blow lands,
each is pushed away from the blow and up, slower and later the further out it sits, the same seed gives the same
plan, each check catches the fault it is named for, and a plan that fails is not written."""

import contextlib
import io
import json
import math
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import fracture as F  # noqa: E402


def made(**kw):
    o = F.checked(dict({"size": [12, 8, 0.6], "pieces": 14, "impact": [-2, 1]}, **kw))
    return o, F.plan(o)


def named(checks):
    return {c["name"]: c for c in checks}


class TestGeometry(unittest.TestCase):
    def test_area_and_centroid(self):
        square = [[0, 0], [2, 0], [2, 2], [0, 2]]
        self.assertEqual(F.area(square), 4.0)
        self.assertEqual(F.area(square[::-1]), -4.0)
        self.assertEqual(F.centroid(square), [1.0, 1.0])
        tri = [[0, 0], [3, 0], [0, 3]]
        self.assertTrue(np.allclose(F.centroid(tri), [1.0, 1.0]))
        self.assertEqual(F.area([[0, 0], [1, 1]]), 0.0)

    def test_a_clip_keeps_the_near_side(self):
        square = [[0, 0], [2, 0], [2, 2], [0, 2]]
        left = F.clip(square, [1, 0], [1, 0])                        # keep what is not past x = 1
        self.assertAlmostEqual(F.area(left), 2.0)
        self.assertTrue(all(p[0] <= 1 + 1e-9 for p in left))
        self.assertEqual(F.clip(square, [5, 0], [1, 0]), square)      # the line misses it: all kept
        self.assertEqual(F.clip(square, [-5, 0], [1, 0]), [])         # all of it is past the line
        corner = F.clip(square, [2, 2], [1, 1])                       # a line through a corner cuts nothing off
        self.assertAlmostEqual(F.area(corner), 4.0)

    def test_the_cut_is_a_voronoi_cut(self):
        rim = F.outline("slab", 4, 4)
        pieces = F.cut(rim, [[-1, 0], [1, 0]])
        self.assertAlmostEqual(F.area(pieces[0]), 8.0)
        self.assertAlmostEqual(F.area(pieces[1]), 8.0)
        self.assertTrue(all(p[0] <= 1e-9 for p in pieces[0]))
        # every point of a piece is nearer to its own seed than to any other
        rng = np.random.default_rng(2)
        seeds = [[float(rng.uniform(-2, 2)), float(rng.uniform(-2, 2))] for _ in range(9)]
        for i, poly in enumerate(F.cut(rim, seeds)):
            c = F.centroid(poly)
            d = [math.hypot(c[0] - s[0], c[1] - s[1]) for s in seeds]
            self.assertEqual(int(np.argmin(d)), i)

    def test_length_and_width(self):
        ln, wd = F.measure([[0, 0], [4, 0], [4, 1], [0, 1]])
        self.assertAlmostEqual(ln, math.hypot(4, 1), delta=0.05)     # its longest extent is its diagonal
        self.assertAlmostEqual(wd, 1.0, delta=0.02)                  # its narrowest is its short side, whichever way it lies
        ln, wd = F.measure([[0, 0], [3, 3], [2.5, 3.5], [-0.5, 0.5]])  # the same kind of splinter, lying at 45 degrees
        self.assertLess(wd / ln, 0.2)


class TestPlan(unittest.TestCase):
    def test_the_pieces_tile_the_slab_and_are_convex(self):
        for kw in ({}, {"shape": "disc", "size": [10, 10, 0.5], "impact": [0, 0], "pieces": 18}, {"pieces": 4}, {"pieces": 48, "size": [20, 20, 1], "impact": [3, -4]},
                   {"focus": 0.0}, {"focus": 1.0, "seed": 9}):
            o, p = made(**kw)
            total = sum(pc["area"] for pc in p["pieces"])
            self.assertAlmostEqual(total, p["area"], delta=0.001 * p["area"], msg=str(kw))
            got = named(F.check(p, o))
            self.assertTrue(got["tiles"]["ok"] and got["convex"]["ok"] and got["outward"]["ok"], kw)
            for pc in p["pieces"]:
                self.assertGreater(F.area(pc["points"]), 0)           # counter-clockwise, about its own centre
                self.assertTrue(np.allclose(F.centroid(pc["points"]), [0, 0], atol=2e-3), kw)
        disc = made(shape="disc", size=[10, 10, 0.5], impact=[0, 0])[1]
        self.assertAlmostEqual(disc["area"], math.pi * 25, delta=0.02 * math.pi * 25)   # (a 40-sided disc)

    def test_small_at_the_blow_large_at_the_rim(self):
        nearer = []
        for seed in range(12):
            o, p = made(seed=seed, focus=0.8, pieces=20, size=[16, 16, 0.8], impact=[0, 0])
            far = sorted(p["pieces"], key=lambda pc: math.hypot(*pc["centre"]))
            nearer.append(np.median([pc["area"] for pc in far[:10]]) < np.median([pc["area"] for pc in far[10:]]))
        self.assertGreaterEqual(sum(nearer), 10)                      # with a focus, nearly every seed
        even = [named(F.check(*reversed(made(seed=s, focus=0.0))))["slivers"]["ok"] for s in range(8)]
        self.assertGreaterEqual(sum(even), 6)

    def test_every_piece_is_pushed_away_and_up_slower_and_later_further_out(self):
        o, p = made(size=[20, 20, 1], impact=[0, 0], pieces=24, seed=6)
        dist = [math.hypot(*pc["centre"]) for pc in p["pieces"]]
        speed = [math.hypot(*pc["vel"]) for pc in p["pieces"]]
        delay = [pc["delay"] for pc in p["pieces"]]
        for pc, far in zip(p["pieces"], dist):
            self.assertGreater(pc["vel"][1], 0)
            if far > 1e-3:
                self.assertGreater(pc["vel"][0] * pc["centre"][0] + pc["vel"][2] * pc["centre"][1], 0)
            self.assertAlmostEqual(pc["delay"], far / o["wave"], places=3)
        self.assertEqual(delay, sorted(delay))                         # in the order the break reaches them
        self.assertLess(np.corrcoef(dist, speed)[0, 1], -0.6)          # further out, slower
        flat = made(lift=0.0)[1]
        self.assertTrue(all(pc["vel"][1] > 0 for pc in flat["pieces"]))   # even a flat push leaves the ground
        up = made(lift=1.0)[1]
        self.assertTrue(all(abs(pc["vel"][0]) < 1e-3 and abs(pc["vel"][2]) < 1e-3 for pc in up["pieces"]))

    def test_the_same_seed_is_the_same_plan(self):
        self.assertEqual(made(seed=5)[1], made(seed=5)[1])
        self.assertNotEqual(made(seed=5)[1]["pieces"][0], made(seed=6)[1]["pieces"][0])

    def test_the_flight_is_the_debris_layers(self):
        piece = {"centre": [1.0, 2.0], "vel": [4.0, 12.0, 0.0], "delay": 0.1}
        self.assertEqual(F.fly(piece, 0.05, thick=1.0), (1.0, 0.5, 2.0))             # the break has not reached it
        x, y, z = F.fly(piece, 0.2, thick=1.0)                                        # 0.1 s of flight
        self.assertAlmostEqual(x, 1.4, delta=0.01)
        self.assertAlmostEqual(y, 0.5 + 12 * 0.1 - 0.5 * 120 * 0.01, delta=0.03)
        x, y, z = F.fly(piece, 3.0, thick=1.0)                                        # long after: at rest on the ground
        self.assertAlmostEqual(y, 0.5, delta=0.02)
        self.assertGreater(x, 1.4)


class TestChecks(unittest.TestCase):
    def test_each_check_catches_its_fault(self):
        o, p = made()
        self.assertEqual([c["name"] for c in F.check(p, o) if not c["ok"]], [])
        import copy
        q = copy.deepcopy(p)
        q["pieces"].pop()
        got = named(F.check(q, o))
        self.assertFalse(got["count"]["ok"])
        self.assertFalse(got["tiles"]["ok"])                           # a piece missing: the slab is not made up
        q = copy.deepcopy(p)
        pts = q["pieces"][0]["points"]
        pts.insert(1, [(pts[0][0] + pts[1][0]) / 2 * 0.2, (pts[0][1] + pts[1][1]) / 2 * 0.2])   # an edge pushed inward: a dent
        self.assertFalse(named(F.check(q, o))["convex"]["ok"])
        q = copy.deepcopy(p)
        q["pieces"][3]["width"] = q["pieces"][3]["length"] * 0.05
        self.assertFalse(named(F.check(q, o))["slivers"]["ok"])
        q = copy.deepcopy(p)
        q["pieces"][3]["area"] *= 0.01
        self.assertFalse(named(F.check(q, o))["slivers"]["ok"])
        q = copy.deepcopy(p)
        far = max(q["pieces"], key=lambda pc: math.hypot(pc["centre"][0] - p["impact"][0], pc["centre"][1] - p["impact"][1]))
        far["vel"] = [-far["vel"][0], far["vel"][1], -far["vel"][2]]
        self.assertFalse(named(F.check(q, o))["outward"]["ok"])
        q = copy.deepcopy(p)
        q["pieces"][0]["vel"][1] = -1.0
        self.assertFalse(named(F.check(q, o))["outward"]["ok"])
        o2, p2 = made(size=[16, 16, 0.8], impact=[0, 0], pieces=20, focus=0.8, seed=1)
        q = copy.deepcopy(p2)
        order = sorted(q["pieces"], key=lambda pc: math.hypot(*pc["centre"]))
        areas = sorted(pc["area"] for pc in order)
        for pc, a in zip(order, areas[::-1]):                          # the largest pieces put at the blow
            pc["area"] = a
        self.assertFalse(named(F.check(q, o2))["focus"]["ok"])

    def test_options_are_refused_in_plain_words(self):
        for bad in ({}, {"size": [10]}, {"size": [0, 5]}, {"size": [10, 10], "shape": "ball"}, {"size": [10, 10], "pieces": 2}, {"size": [10, 10], "pieces": 200},
                    {"size": [10, 10], "impact": [30, 0]}, {"size": [10, 10], "impact": [1]}, {"size": [10, 10], "focus": 3}, {"size": [10, 10], "lift": -1},
                    {"size": [10, 10], "speed": float("nan")}, {"size": [10, 10, 0]}):
            with self.assertRaises(ValueError, msg=str(bad)):
                F.checked(bad)
        self.assertEqual(F.checked({"size": [10, 4]})["size"], [10.0, 4.0, 0.4])      # a tenth of the smaller side
        self.assertEqual(F.checked({"size": [10, 4], "shape": "disc"})["size"][:2], [10.0, 10.0])


class TestCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kit_fracture_")
        self.dirs = ["--out-dir", os.path.join(self.tmp, "plans"), "--look-dir", os.path.join(self.tmp, "look")]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_tool(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = F.main(list(argv) + self.dirs)
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1, lines)
        return code, json.loads(lines[0])

    def test_a_plan_is_written_and_drawn(self):
        code, v = self.run_tool("slab_a", "--size", "12,8,0.6", "--pieces", "14", "--impact", "-2,1")
        self.assertEqual(code, 0, v)
        p = json.load(open(os.path.join(self.tmp, "plans", "slab_a.json"), encoding="utf-8"))
        self.assertEqual((len(p["pieces"]), p["size"], p["impact"]), (14, [12.0, 8.0, 0.6], [-2.0, 1.0]))
        self.assertEqual(p["made"]["seed"], 3)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "look", "slab_a.png")))
        self.assertIn('"pieces": "slab_a"', v["summary"])

    def test_a_plan_that_fails_is_not_written_and_an_older_one_stays(self):
        bad = next(s for s in range(200) if any(not c["ok"] for c in F.check(*reversed(made(seed=s, pieces=40, focus=1.0)))))
        code, v = self.run_tool("slab_b", "--size", "12,8,0.6", "--pieces", "40", "--impact", "-2,1", "--focus", "1", "--seed", str(bad))
        self.assertEqual(code, 1)
        self.assertIn("nothing written", v["summary"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "plans", "slab_b.json")))
        self.run_tool("slab_b", "--size", "12,8,0.6")
        before = open(os.path.join(self.tmp, "plans", "slab_b.json"), encoding="utf-8").read()
        code, v = self.run_tool("slab_b", "--size", "12,8,0.6", "--pieces", "40", "--impact", "-2,1", "--focus", "1", "--seed", str(bad))
        self.assertIn("stays as it was", v["summary"])
        self.assertEqual(open(os.path.join(self.tmp, "plans", "slab_b.json"), encoding="utf-8").read(), before)

    def test_the_command_never_throws(self):
        for argv in ([], ["--size", "4,4"], ["Bad-Name", "--size", "4,4"], ["x"], ["x", "--size"], ["x", "--size", "big"], ["x", "--size", "4,4", "--bogus", "1"],
                     ["x", "--size", "4,4", "--pieces", "many"], ["x", "--size", "4,4", "--impact", "9,9"], ["x", "--size", "4,4", "--shape", "ball"]):
            code, v = self.run_tool(*argv)
            self.assertEqual((code, v["status"]), (1, "fail"), argv)


class AfterTheReview(unittest.TestCase):
    def test_a_plank_is_cut_into_a_few_pieces(self):
        # a piece as wide as the plank is no splinter, however long it is
        o = F.checked({"size": [20, 1], "pieces": 4, "seed": 3})
        p = F.plan(o)
        self.assertTrue(next(c for c in F.check(p, o) if c["name"] == "slivers")["ok"])

    def test_a_refused_cut_leaves_plan_and_picture_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = ["--out-dir", os.path.join(tmp, "plans"), "--look-dir", os.path.join(tmp, "look")]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(F.main(["slab", "--size", "10,10", "--pieces", "14"] + args), 0)
            plan, picture = os.path.join(tmp, "plans", "slab.json"), os.path.join(tmp, "look", "slab.png")
            before = (open(plan, "rb").read(), open(picture, "rb").read())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertNotEqual(F.main(["slab", "--size", "10,10", "--pieces", "14", "--impact", "40,0"] + args), 0)
            self.assertEqual(before, (open(plan, "rb").read(), open(picture, "rb").read()))


if __name__ == "__main__":
    unittest.main()
