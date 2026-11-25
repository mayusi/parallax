"""Unit tests of the point cloud's rule and tool (kit/vfx/points.py).
Run: python -m pytest kit/test/python/test_vfx_points.py -q"""
import contextlib
import io
import json
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))
import methods as M  # noqa: E402
import points as P  # noqa: E402


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = P.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


def fly(d, v, w, dt, seconds):
    path = [d]
    for _ in range(int(seconds / dt)):
        v = P.pull(d, v, w, dt)
        d += v * dt
        path.append(d)
    return path


class TheRule(unittest.TestCase):
    def test_a_particle_comes_to_its_point_and_never_passes_it(self):
        for dt in (1 / 144, 1 / 60, 1 / 30, 1 / 15):
            path = fly(5.0, 0.0, 8.0, dt, 3.0)
            self.assertGreaterEqual(min(path), 0.0, dt)
            self.assertLess(path[-1], 1e-3, dt)
            self.assertTrue(all(b <= a + 1e-12 for a, b in zip(path, path[1:])), dt)   # always nearer

    def test_a_harder_pull_is_there_sooner(self):
        at = [next(k for k, d in enumerate(fly(5.0, 0.0, w, 1 / 60, 20.0)) if d < 0.05) for w in (2.0, 8.0, 30.0)]
        self.assertGreater(at[0], at[1])
        self.assertGreater(at[1], at[2])

    def test_no_pull_changes_nothing_and_no_step_goes_nowhere(self):
        self.assertEqual(P.pull(5.0, 2.0, 0.0, 1 / 60), 2.0)
        self.assertEqual(P.pull(5.0, 2.0, 8.0, 0.0), 2.0)

    def test_a_stalled_frame_throws_nothing(self):
        for dt in (0.5, 1.0, 10.0):
            v = P.pull(5.0, 0.0, 30.0, dt)
            self.assertLess(abs(v * dt), 5.0)                                          # it does not reach, let alone pass, its point
            self.assertLess(v, 0)

    def test_thrown_at_its_point_it_passes_once_and_comes_back(self):
        path = fly(0.5, -8.0, 8.0, 1 / 60, 4.0)
        self.assertLess(min(path), 0)                                                   # (what the page says: only from rest does it never pass)
        self.assertGreater(min(path), -0.2)
        self.assertLess(abs(path[-1]), 1e-3)

    def test_a_curve_is_read_as_the_runtime_reads_it(self):
        self.assertEqual(P.at_curve(None, 0.3, 8.0), 8.0)
        self.assertEqual(P.at_curve(5, 0.3, 8.0), 5.0)
        self.assertAlmostEqual(P.at_curve([[0, 0], [0.4, 10], [1, 10]], 0.2, 8.0), 5.0)
        self.assertAlmostEqual(P.at_curve([[0, 0, 0.3], [1, 4, 0.3]], 0.5, 8.0), 2.0)
        self.assertEqual(P.at_curve([[0.2, 3], [1, 9]], 0.0, 8.0), 3.0)
        self.assertEqual(P.at_curve([[0, 3], [0.5, 9]], 1.0, 8.0), 9.0)

    def test_a_particle_flying_past_is_caught(self):
        path = fly(0.0, 40.0, 8.0, 1 / 60, 4.0)                                         # on its point, thrown away from it
        self.assertLess(max(path), 40.0 / 8.0)                                          # it goes no further than a free one would in 1 / w
        self.assertLess(abs(path[-1]), 1e-3)


class TheClouds(unittest.TestCase):
    def test_every_starter_is_a_cloud_that_passes(self):
        for kind in P.STARTERS:
            for count in (8, 60, 150):
                pts = P.starter(kind, count, 1)
                self.assertEqual(len(pts), count)
                self.assertEqual([c["name"] for c in P.check(pts) if not c["ok"]], [], (kind, count))
                self.assertAlmostEqual(max(math.sqrt(sum(x * x for x in p)) for p in pts), 1.0, places=3)

    def test_a_ring_is_a_ring_and_a_sphere_a_sphere(self):
        self.assertTrue(all(abs(math.hypot(p[0], p[1]) - 1) < 1e-3 and p[2] == 0 for p in P.starter("ring", 40, 1)))
        self.assertTrue(all(abs(math.sqrt(sum(x * x for x in p)) - 1) < 0.02 for p in P.starter("sphere", 80, 1)))

    def test_a_picture_gives_points_on_its_figure(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            for name, ground, ink in (("glow", (0, 0, 0, 0), (255, 240, 200, 255)), ("print", (255, 255, 255, 255), (20, 20, 20, 255)),
                                      ("ink", (0, 0, 0, 0), (0, 0, 0, 255)), ("night", (10, 10, 20, 255), (250, 250, 250, 255))):
                img = Image.new("RGBA", (120, 120), ground)
                ImageDraw.Draw(img).rectangle([20, 50, 100, 70], fill=ink)               # a bar: 80 wide, 20 high
                path = os.path.join(tmp, f"{name}.png")
                img.save(path)
                pts = P.from_picture(path, 40, 1)
                wide = max(p[0] for p in pts) - min(p[0] for p in pts)
                high = max(p[1] for p in pts) - min(p[1] for p in pts)
                self.assertGreater(wide, 1.6, name)                                      # the bar's length, end to end
                self.assertLess(high, 0.6, name)
                self.assertEqual(P.from_picture(path, 40, 1), pts)                       # the same picks for the same seed
            thin = os.path.join(tmp, "thin.png")
            img = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
            img.putpixel((5, 5), (255, 255, 255, 255))
            img.save(thin)
            with self.assertRaisesRegex(ValueError, "bright pixels"):
                P.from_picture(thin, 40, 1)

    def test_what_is_wrong_with_a_file_is_said(self):
        good = P.starter("ring", 20, 1)
        for data, word in (([1, 2], "a cloud file is"), ({"points": good, "size": 3}, "does not read size"), ({"points": good[:3]}, "8 to 150 points"),
                           ({"points": good + [[0, 0]]}, "three numbers"), ({"points": good + [[0, 0, float("nan")]]}, "three numbers"),
                           ({"points": good + [[0, True, 0]]}, "three numbers")):
            with self.assertRaisesRegex(ValueError, word):
                P.checked(data)
        self.assertEqual(len(P.checked({"about": "x", "from": "ring", "points": good})), 20)

    def test_the_checks(self):
        def failed(pts):
            return [c["name"] for c in P.check(pts) if not c["ok"]]

        ring = P.starter("ring", 30, 1)
        self.assertIn("unit size", failed([[x * 4 for x in p] for p in ring]))
        self.assertIn("unit size", failed([[p[0] + 0.5, p[1], p[2]] for p in ring]))
        self.assertIn("a shape, not a clump", failed([[1.0, 0.0, 0.0]] + [[-1 + 0.001 * i, 0.0, 0.0] for i in range(1, 30)][:0] + [[1 - 2 * i / 29, 0.0, 0.0] for i in range(30)]))
        self.assertIn("no two particles on one point", failed(ring + [ring[0]]))
        self.assertIn("the points cover the shape evenly", failed([[0.05 * math.cos(i), 0.05 * math.sin(i), 0.0] for i in range(29)] + [[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]]))


class TheCommand(unittest.TestCase):
    def test_a_starter_is_written_once_and_read_after(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, said = run(["halo", "--new", "ring", "--count", "40", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 0, said)
            self.assertEqual(len(json.load(open(os.path.join(tmp, "halo.json"), encoding="utf-8"))["points"]), 40)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "halo.png")))
            self.assertIn('"cloud": {"name": "halo"', said["summary"])
            self.assertLess(said["gathered"], 8 / 8 + 0.2)
            code, said = run(["halo", "--new", "disc", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 1)
            self.assertIn("already there", said["summary"])
            code, said = run(["halo", "--pull", "20", "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 0)
            self.assertLess(said["gathered"], 8 / 20 + 0.2)

    def test_a_refused_cloud_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, said = run(["x", "--picture", os.path.join(tmp, "none.png"), "--out-dir", tmp, "--look-dir", tmp])
            self.assertEqual(code, 1)
            self.assertEqual(os.listdir(tmp), [])

    def test_wrong_asks_are_said_in_words(self):
        for argv, word in ((["Halo"], "lowercase"), (["a", "b"], "ONE"), (["s", "--new", "cube"], "--new is one of"), (["s", "--count", "4"], "--count is 8 to 150"),
                           (["s", "--count", "x"], "whole numbers"), (["s", "--pull", "0"], "--pull 0.5 to 60"), (["s", "--glow", "1"], "not an option"),
                           (["s", "--new"], "no value"), (["s", "--new", "ring", "--picture", "a.png"], "not both"), (["nothing_here"], "no cloud")):
            code, said = run(argv)
            self.assertEqual(code, 1, argv)
            self.assertIn(word, said["summary"], argv)


class TheRegister(unittest.TestCase):
    def test_a_point_cloud_is_a_swarm_that_gathers_into_one_that_is_there(self):
        m = M.load()[1]["point_cloud"]
        self.assertEqual(m["state"], "has")

        class Empty:
            def get(self, key):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "points"))
            for name, data in (("halo", {"points": P.starter("ring", 40, 1)}), ("knot", {"points": [[0.9 + 0.004 * i, 0.3, 0.0] for i in range(30)]}), ("junk", "x")):
                with open(os.path.join(tmp, "points", f"{name}.json"), "w", encoding="utf-8") as fh:
                    json.dump(data, fh)

            def proved(layer):
                return M.proved(m, [dict({"kind": "swarm", "life": 1}, **layer)], Empty(), tmp, "s") is not None

            self.assertTrue(proved({"cloud": {"name": "halo"}}))                           # 40 particles unless said
            self.assertTrue(proved({"count": 150, "life": 3, "lifetime": [2, 3], "cloud": {"name": "halo", "pull": [[0, 0], [0.5, 10], [1, 0]]}}))
            self.assertFalse(proved({"count": 150, "life": 1, "cloud": {"name": "halo", "pull": [[0, 0], [0.5, 10], [1, 0]]}}))   # over before it gathers
            self.assertFalse(proved({"count": 150, "life": 3, "lifetime": 0.2, "cloud": {"name": "halo", "pull": 10}}))          # dead before it arrives
            self.assertFalse(proved({"cloud": {"name": "halo", "pull": [[0, 0, 0.3], [1, 0, 0.3]]}}))   # 0 all its life (keys with envelopes)
            self.assertFalse(proved({"cloud": {"name": "halo", "size": 0.1}}))
            self.assertFalse(proved({"count": 30, "cloud": {"name": "halo"}}))             # the first 30 of 40 points: part of a ring
            self.assertFalse(proved({"cloud": {"name": "halo", "pull": 0}}))               # never pulled
            self.assertFalse(proved({"cloud": {"name": "halo", "pull": [[0, 0.1], [1, 0.2]]}}))
            for bad in ("knot", "junk", "nothing", "Halo"):
                self.assertFalse(proved({"cloud": {"name": bad}}), bad)
            self.assertFalse(proved({"cloud": "halo"}))
            self.assertFalse(proved({"attract": {"strength": 20}}))


if __name__ == "__main__":
    unittest.main()
