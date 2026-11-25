"""test_world_gnscatter.py - THINGS SCATTERED OVER A MESH'S SURFACE (kit/world/gnscatter_blender.py; the owner's method
list: "Geometry Nodes scattering", "Surface-based scattering"). What needs no Blender is held here: the command's
words, the reading of a mesh copy, which faces take points. The scatter itself runs in Blender: the audit page says
what was run there and what came out (points on a real mesh, the gap between them measured)."""
import base64
import importlib.util
import json
import math
import os
import struct
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_world_gnscatter", os.path.join(HERE, "..", "..", "world", "gnscatter_blender.py"))
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)


class Words(unittest.TestCase):
    def test_what_it_is_told_is_read(self):
        s, why = G.arguments(["a.mesh.json", "out.json", "--gap", "3"])
        self.assertIsNone(why)
        self.assertEqual(s, {"source": "a.mesh.json", "out": "out.json", "gap": 3.0, "seed": 1, "facing": "any", "steep": 0.5, "most": 400})
        s, why = G.arguments(["a.mesh.json", "out.json", "--most", "50", "--facing", "side", "--steep", "0.8", "--seed", "9", "--gap", "0.5"])
        self.assertIsNone(why)
        self.assertEqual((s["gap"], s["seed"], s["facing"], s["steep"], s["most"]), (0.5, 9, "side", 0.8, 50))
        self.assertIsInstance(s["seed"], int)
        self.assertIsInstance(s["most"], int)

    def test_what_is_wrong_is_said(self):
        for argv, text in (
            ([], "usage:"),
            (["a.mesh.json"], "usage:"),
            (["a", "b"], "--gap says how many studs"),
            (["a", "b", "--gap", "0.4"], "--gap is 0.5 to 200"),
            (["a", "b", "--gap", "201"], "--gap is 0.5 to 200"),
            (["a", "b", "--gap", "wide"], "--gap is a number"),
            (["a", "b", "--gap", "nan"], "--gap is a number"),
            (["a", "b", "--gap", "inf"], "--gap is a number"),
            (["a", "b", "--gap"], "has no value"),
            (["a", "b", "--gap", "3", "--gaps", "3"], "--gaps is not a word"),
            (["a", "b", "--gap", "3", "--facing", "north"], "--facing is one of up, side, down, any"),
            (["a", "b", "--gap", "3", "--seed", "1.5"], "--seed is a whole number"),
            (["a", "b", "--gap", "3", "--seed", "-1"], "--seed is a whole number"),
            (["a", "b", "--gap", "3", "--seed", "65536"], "--seed is a whole number"),
            (["a", "b", "--gap", "3", "--steep", "1"], "--steep is 0"),
            (["a", "b", "--gap", "3", "--steep", "-0.1"], "--steep is 0"),
            (["a", "b", "--gap", "3", "--most", "0"], "--most is a whole number"),
            (["a", "b", "--gap", "3", "--most", "4001"], "--most is a whole number"),
            (["a", "b", "--gap", "3", "--most", "2.5"], "--most is a whole number"),
        ):
            s, why = G.arguments(argv)
            self.assertIsNone(s, argv)
            self.assertIn(text, why)


class MeshCopy(unittest.TestCase):
    def write(self, floats=None, text=None):
        fd, path = tempfile.mkstemp(suffix=".mesh.json")
        os.close(fd)
        self.addCleanup(os.remove, path)
        with open(path, "w", encoding="utf-8") as fh:
            if text is not None:
                fh.write(text)
            else:
                json.dump({"position": base64.b64encode(struct.pack(f"<{len(floats)}f", *floats)).decode()}, fh)
        return path

    def test_a_mesh_copy_is_read_three_points_a_triangle(self):
        tris, why = G.triangles(self.write([0, 0, 0, 4, 0, 0, 0, 0, 4, 1, 2, 3, 4, 5, 6, 7, 8, 9]))
        self.assertIsNone(why)
        self.assertEqual(len(tris), 6)
        self.assertEqual(tuple(tris[1]), (4.0, 0.0, 0.0))
        self.assertEqual(tuple(tris[5]), (7.0, 8.0, 9.0))

    def test_what_is_no_mesh_copy_is_said(self):
        for path in (self.write(text="not json"), self.write(text='{"tris": 4}'), self.write(text='{"position": 5}'),
                     os.path.join(HERE, "no_such.mesh.json")):
            tris, why = G.triangles(path)
            self.assertIsNone(tris)
            self.assertIn("is no mesh copy of kit world meshes", why)
        for floats in ([0, 0, 0, 4, 0, 0], [0.0] * 10, []):
            tris, why = G.triangles(self.write(floats))
            self.assertIsNone(tris)
            self.assertIn("holds no whole triangles", why)


class Facing(unittest.TestCase):
    def test_which_faces_take_points(self):
        up, down, east = (0, 1, 0), (0, -1, 0), (1, 0, 0)
        lean = lambda deg: (math.sin(math.radians(deg)), math.cos(math.radians(deg)), 0)  # (from straight up)
        for normal in (up, down, east, lean(45)):
            self.assertTrue(G.keeps(normal, "any", 0.5))
        self.assertTrue(G.keeps(up, "up", 0.5))
        self.assertFalse(G.keeps(down, "up", 0.5))
        self.assertFalse(G.keeps(east, "up", 0.5))
        self.assertTrue(G.keeps(lean(59), "up", 0.5))  # (0.5 = within 60 degrees of straight up)
        self.assertFalse(G.keeps(lean(61), "up", 0.5))
        self.assertTrue(G.keeps(lean(30), "up", 0.8))
        self.assertFalse(G.keeps(lean(45), "up", 0.8))
        self.assertTrue(G.keeps(down, "down", 0.5))
        self.assertFalse(G.keeps(up, "down", 0.5))
        self.assertTrue(G.keeps(lean(180 - 59), "down", 0.5))
        self.assertFalse(G.keeps(lean(180 - 61), "down", 0.5))
        self.assertTrue(G.keeps(east, "side", 0.5))
        self.assertFalse(G.keeps(up, "side", 0.5))
        self.assertFalse(G.keeps(down, "side", 0.5))
        self.assertTrue(G.keeps(lean(90 - 59), "side", 0.5))  # (a wall leaning back 59 degrees is still a side)
        self.assertFalse(G.keeps(lean(90 - 61), "side", 0.5))
        self.assertTrue(G.keeps(lean(90 + 59), "side", 0.5))  # (and one that overhangs as far)
        self.assertFalse(G.keeps(lean(90 + 61), "side", 0.5))
        self.assertTrue(G.keeps((0, 0.3, -0.954), "side", 0.5))  # (any compass way)


class Space(unittest.TestCase):
    def test_roblox_to_blender_and_back_is_a_quarter_turn_no_mirror(self):
        self.assertEqual(G.to_blender((1, 2, 3)), (1, -3, 2))  # (Roblox up is Blender's z; Roblox +z is Blender's -y)
        self.assertEqual(G.to_roblox((1, -3, 2)), (1, 2, 3))
        for p in ((0, 1, 0), (0, 0, 1), (1, 0, 0), (0.3, -2, 7.5)):
            self.assertEqual(G.to_roblox(G.to_blender(p)), p)
        self.assertEqual(G.to_blender((0, 1, 0)), (0, 0, 1))
        self.assertEqual(G.to_roblox((0, 1, 0)), (0, 0, -1))
        # a turn keeps a triangle's winding: the normal of the turned triangle is the turned normal
        a, b, c = (0, 0, 0), (4, 0, 0), (0, 0, -3)
        n, _ = G.face(a, b, c)
        nb, _ = G.face(G.to_blender(a), G.to_blender(b), G.to_blender(c))
        self.assertEqual(tuple(round(v, 9) for v in G.to_blender(n)), tuple(round(v, 9) for v in nb))

    def test_a_triangles_normal_and_area(self):
        n, area = G.face((0, 0, 0), (4, 0, 0), (0, 0, -3))  # (counter-clockwise seen from above: it faces up)
        self.assertEqual(n, (0.0, 1.0, 0.0))
        self.assertEqual(area, 6.0)
        n, area = G.face((0, 0, 0), (0, 0, -3), (4, 0, 0))
        self.assertEqual(n, (0.0, -1.0, 0.0))
        n, area = G.face((0, 0, 0), (1, 1, 1), (2, 2, 2))  # (no area)
        self.assertEqual((n, area), ((0.0, 0.0, 0.0), 0.0))

    def test_the_mesh_as_the_scatter_needs_it(self):
        top = [(0, 5, 0), (10, 5, 0), (0, 5, -10)]  # (faces up, 50 sq studs)
        wall = [(0, 0, 0), (10, 0, 0), (0, 4, 0)]  # (faces +z, 20 sq studs)
        sliver = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        tris = top + wall + sliver
        seen = G.survey(tris, "up", 0.5)
        self.assertEqual(seen["keep"], [True, False, False])
        self.assertEqual(seen["area"], 50.0)
        self.assertEqual((seen["min"], seen["size"]), ([0, 0, -10], [10, 5, 12]))  # (the box of ALL its triangles)
        seen = G.survey(tris, "side", 0.5)
        self.assertEqual((seen["keep"], seen["area"]), ([False, True, False], 20.0))
        seen = G.survey(tris, "any", 0.5)
        self.assertEqual((seen["keep"], seen["area"]), ([True, True, False], 70.0))  # (a face of no area takes none)
        self.assertEqual(G.survey(tris, "down", 0.5)["area"], 0.0)


class Counts(unittest.TestCase):
    def settings(self, **more):
        s = {"gap": 4.0, "most": 400, "facing": "up", "steep": 0.5}
        s.update(more)
        return s

    def test_a_mesh_that_would_take_far_too_many_is_refused_before_anything_is_spread(self):
        self.assertAlmostEqual(G.expected(1600, 4), 60)  # (0.6 a gap squared)
        self.assertIsNone(G.too_many(16000, self.settings()))  # (about 600: within one and a half times the most)
        self.assertIsNone(G.too_many(16000 - 1, self.settings()))
        why = G.too_many(16100, self.settings())
        self.assertIn("about 603 points at a gap of 4 on 16100 sq studs of faces that face up", why)
        self.assertIn("far over the most asked (400)", why)
        self.assertIsNone(G.too_many(16100, self.settings(gap=8.0)))
        self.assertIsNotNone(G.too_many(400, self.settings(gap=0.5, most=100)))

    def test_what_a_runs_count_comes_to(self):
        self.assertIsNone(G.judged(400, self.settings()))
        self.assertIsNone(G.judged(1, self.settings()))
        self.assertIn("401 points, over the most asked (400)", G.judged(401, self.settings()))
        self.assertIn("no point - no face of this mesh faces up within --steep 0.5", G.judged(0, self.settings()))

    def test_a_failed_run_removes_the_earlier_points_and_says_so(self):
        import contextlib
        import io as _io

        fd, path = tempfile.mkstemp(suffix=".on.moss.json")
        os.close(fd)
        out = _io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as stop:
            G.fail("scatter-on: too many", path)
        self.assertEqual(stop.exception.code, 1)
        self.assertFalse(os.path.exists(path))
        said = json.loads(out.getvalue())
        self.assertEqual(said["status"], "fail")
        self.assertIn("scatter-on: too many (the earlier points in", said["summary"])
        self.assertIn("were removed)", said["summary"])
        out = _io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            G.fail("scatter-on: no mesh", path)  # (nothing there to remove: nothing said of it)
        self.assertEqual(json.loads(out.getvalue())["summary"], "scatter-on: no mesh")


if __name__ == "__main__":
    unittest.main()
