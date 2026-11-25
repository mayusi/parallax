"""test_world_sky.py - A SKY OF THE KIT'S OWN, face by face (kit/world/sky.py; the owner's method list: "Skyboxes").
What needs no Blender is held here: the six faces as they were MEASURED in Roblox Studio (which way each looks, which
way its picture's top lies), that six such pictures are the six sides of one cube with no mirror among them, where a
direction falls in which picture, where the sun stands, the command's words.
The pictures themselves are rendered in Blender, and each run checks itself there (the sun's spot is where it was asked
for): the audit page says what was run and what was looked at. Nothing here or there is in a game: that is an upload."""
import importlib.util
import math
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_world_sky", os.path.join(HERE, "..", "..", "world", "sky.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)


class Faces(unittest.TestCase):
    def test_the_faces_as_measured_in_studio(self):
        # (2026-11-15, the kit's scratch place, built-in textures as the six faces)
        self.assertEqual(S.FACES["ft"], ((0, 0, -1), (0, 1, 0)))  # Ft is seen looking toward -Z, upright
        self.assertEqual(S.FACES["lf"], ((1, 0, 0), (0, 1, 0)))  # Lf is seen looking toward +X, upright
        self.assertEqual(S.FACES["up"], ((0, 1, 0), (1, 0, 0)))  # Up: its picture's top lies toward +X
        self.assertEqual(S.FACES["dn"], ((0, -1, 0), (-1, 0, 0)))  # Dn: its picture's top lies toward -X
        # (the two not looked at: by their names, the faces opposite)
        self.assertEqual(S.FACES["bk"], ((0, 0, 1), (0, 1, 0)))
        self.assertEqual(S.FACES["rt"], ((-1, 0, 0), (0, 1, 0)))
        self.assertEqual(sorted(S.PROPERTY.values()), ["SkyboxBk", "SkyboxDn", "SkyboxFt", "SkyboxLf", "SkyboxRt", "SkyboxUp"])
        self.assertEqual(S.PROPERTY, {"ft": "SkyboxFt", "bk": "SkyboxBk", "lf": "SkyboxLf", "rt": "SkyboxRt",
                                      "up": "SkyboxUp", "dn": "SkyboxDn"})

    def test_six_sides_of_one_cube_none_mirrored(self):
        looks = set()
        for face, (look, up) in S.FACES.items():
            self.assertEqual(S.dot(look, up), 0, face)  # (a picture's top lies across the way it is looked at)
            self.assertEqual(S.dot(look, look), 1)
            self.assertEqual(S.dot(up, up), 1)
            # seen from inside, not mirrored: right = look x up, a right hand
            r = S.right(face)
            self.assertEqual(S.cross(up, r), look)  # (up x right points the way it looks: a right hand)
            looks.add(look)
        self.assertEqual(len(looks), 6)  # (six different ways: every way out is in some picture)
        # as read off in Studio: looking up with the screen's top toward +Z the Up picture shows turned a quarter
        # clockwise - its right edge lies toward -Z; looking down with the top toward -Z the Dn picture's right
        # edge lies toward -Z too
        self.assertEqual(S.right("up"), (0, 0, -1))
        self.assertEqual(S.right("dn"), (0, 0, -1))
        self.assertEqual(S.right("ft"), (1, 0, 0))  # (looking north, east is to the right)
        self.assertEqual(S.right("lf"), (0, 0, 1))

    def test_where_a_direction_falls(self):
        self.assertEqual(S.falls((0, 0, -1)), ("ft", 0.5, 0.5))  # (a face's own way: the picture's middle)
        self.assertEqual(S.falls((1, 0, 0)), ("lf", 0.5, 0.5))
        self.assertEqual(S.falls((0, 1, 0)), ("up", 0.5, 0.5))
        face, u, v = S.falls((0, 1, -2))  # (north and up: in Ft, above its middle)
        self.assertEqual((face, u), ("ft", 0.5))
        self.assertAlmostEqual(v, 0.25)
        face, u, v = S.falls((1, 0, -2))  # (north and a little east: right of Ft's middle)
        self.assertEqual(face, "ft")
        self.assertAlmostEqual(u, 0.75)
        face, u, v = S.falls((0.5, 2, 0))  # (nearly straight up, leaning east: toward the Up picture's TOP)
        self.assertEqual(face, "up")
        self.assertAlmostEqual(v, 0.375)
        self.assertAlmostEqual(u, 0.5)
        face, u, v = S.falls((0, 2, -0.5))  # (leaning north: toward the Up picture's RIGHT)
        self.assertAlmostEqual(u, 0.625)
        face, u, v = S.falls((0.5, -2, 0))  # (straight down leaning east: toward the Dn picture's BOTTOM)
        self.assertEqual(face, "dn")
        self.assertAlmostEqual(v, 0.625)
        # ... and back: a place in a picture points where it fell from, for every face
        for d in ((0.3, 0.2, -1), (1, -0.4, 0.7), (-0.2, 1, 0.5), (-1, 0.1, -0.9), (0.6, -1, -0.3), (0.1, 0.2, 1)):
            face, u, v = S.falls(d)
            self.assertTrue(0 <= u <= 1 and 0 <= v <= 1)
            self.assertAlmostEqual(S.apart(S.direction(face, u, v), d), 0, places=5)
        self.assertAlmostEqual(S.apart((1, 0, 0), (0, 1, 0)), 90)
        self.assertAlmostEqual(S.apart((1, 0, 0), (2, 0, 0)), 0)

    def test_the_checks_own_suns_one_off_the_middle_of_each_face(self):
        suns = S.test_suns()
        self.assertEqual(sorted(suns), sorted(S.FACES))
        for face, vector in suns.items():
            got, u, v = S.falls(vector)
            self.assertEqual(got, face)
            self.assertAlmostEqual(u, 0.74)
            self.assertAlmostEqual(v, 0.31)
            # off the middle and off both diagonals: turned a quarter, a half, or mirrored it lands elsewhere
            for other in ((1 - u, v), (u, 1 - v), (1 - u, 1 - v), (v, u), (1 - v, u), (v, 1 - u), (1 - v, 1 - u)):
                self.assertGreater(abs(other[0] - u) + abs(other[1] - v), 0.1)

    def test_two_pictures_meet_along_their_shared_edge(self):
        # the top edge of Ft and an edge of Up are the same line of sky: a way on that line falls on both edges
        d = (0.4, 1, -1)  # (on the seam between north and up)
        self.assertAlmostEqual(S.apart(S.direction("ft", 0.7, 0.0), d), 0, places=5)
        self.assertAlmostEqual(S.apart(S.direction("up", 1.0, 0.3), d), 0, places=5)
        # Lf's right edge and Bk's left edge
        d = (1, 0.5, 1)
        self.assertAlmostEqual(S.apart(S.direction("lf", 1.0, 0.25), d), 0, places=5)
        self.assertAlmostEqual(S.apart(S.direction("bk", 0.0, 0.25), d), 0, places=5)

    def test_where_the_sun_stands(self):
        for elevation, azimuth, want in ((0, 0, (0, 0, -1)), (0, 90, (1, 0, 0)), (0, 180, (0, 0, 1)),
                                         (0, 270, (-1, 0, 0)), (90, 0, (0, 1, 0))):
            got = S.sun_vector(elevation, azimuth)
            for k in range(3):
                self.assertAlmostEqual(got[k], want[k])
        v = S.sun_vector(30, 90)
        self.assertAlmostEqual(v[1], 0.5)
        self.assertAlmostEqual(math.sqrt(sum(c * c for c in v)), 1)
        self.assertEqual(S.falls(S.sun_vector(10, 0))[0], "ft")
        self.assertEqual(S.falls(S.sun_vector(10, 90))[0], "lf")
        self.assertEqual(S.falls(S.sun_vector(80, 200))[0], "up")

    def test_the_cameras_for_blender(self):
        self.assertEqual(S.to_blender((1, 2, 3)), (1, -3, 2))
        for face, (look, up) in S.FACES.items():
            rows = S.camera_matrix(face)
            col = lambda k: tuple(rows[i][k] for i in range(3))
            self.assertEqual(col(0), S.to_blender(S.right(face)))
            self.assertEqual(col(1), S.to_blender(up))
            self.assertEqual(col(2), S.to_blender(tuple(-c for c in look)))  # (a Blender camera looks down its -z)
            # a true turn: right x up = back
            self.assertEqual(S.cross(col(0), col(1)), col(2))


class Ridges(unittest.TestCase):
    """far ranges painted into the sky (the owner's list: "Matte painting")"""

    def test_the_ranges_stand_one_behind_the_other(self):
        self.assertEqual(S.ridge_layers(0, 10), [])
        one = S.ridge_layers(1, 10)
        self.assertEqual(one, [{"top": 10.0, "low": 3.5, "air": 0.75, "scale": 2.2}])
        three = S.ridge_layers(3, 12)
        self.assertEqual(len(three), 3)
        self.assertEqual([r["top"] for r in three], [12.0, 9.0, 6.0])  # (the farthest first, and the highest)
        self.assertEqual([r["air"] for r in three], [0.75, 0.5, 0.25])  # (and the palest: the air between)
        self.assertEqual([r["scale"] for r in three], [2.2, 3.5, 4.8])  # (a nearer range's crests are closer set)
        for r in three:
            self.assertAlmostEqual(r["low"], r["top"] * 0.35, places=3)  # (no crest falls to the horizon)
        two = S.ridge_layers(2, 8)
        self.assertEqual([r["top"] for r in two], [8.0, 4.0])

    def test_a_ways_height_and_compass_side(self):
        self.assertAlmostEqual(S.elevation((0, 0, -1)), 0)
        self.assertAlmostEqual(S.elevation((0, 1, 0)), 90)
        self.assertAlmostEqual(S.elevation((0, -1, 0)), -90)
        self.assertAlmostEqual(S.elevation((3, 3 * math.sqrt(2), -3)), 45)  # (x and z both count as the ground)
        self.assertAlmostEqual(S.elevation((5, 5, 0)), 45)
        self.assertAlmostEqual(S.compass((0, 0, -1)), 0)  # (-Z)
        self.assertAlmostEqual(S.compass((1, 0, 0)), 90)  # (toward +X)
        self.assertAlmostEqual(S.compass((0, 0, 1)), 180)
        self.assertAlmostEqual(S.compass((-1, 0, 0)), 270)
        self.assertAlmostEqual(S.compass((-1, 5, -1)), 315)  # (height does not change the side)
        for e, a in ((0, 0), (10, 45), (30, 200), (-5, 359)):  # (and they are the sun's own two numbers)
            v = S.sun_vector(e, a)
            self.assertAlmostEqual(S.elevation(v), e, places=6)
            self.assertAlmostEqual(S.compass(v), a, places=6)

    def test_the_ridges_words(self):
        s, why = S.arguments(["out", "--name", "Day", "--ridges", "2"])
        self.assertIsNone(why)
        self.assertEqual((s["ridges"], s["ridge_height"]), (2, 8.0))  # (a height of its own when none is said)
        s, why = S.arguments(["out", "--name", "Day", "--ridges", "3", "--ridge-height", "25"])
        self.assertEqual((s["ridges"], s["ridge_height"]), (3, 25.0))
        s, why = S.arguments(["out", "--name", "Day", "--ridges", "1", "--ridge-height", "2"])
        self.assertEqual((s["ridges"], s["ridge_height"]), (1, 2.0))
        s, why = S.arguments(["out", "--name", "Day", "--ridges", "0"])
        self.assertEqual((s["ridges"], s["ridge_height"]), (0, None))
        for argv, text in (
            (["--ridges", "4"], "--ridges is how many ranges"),
            (["--ridges", "-1"], "--ridges is how many ranges"),
            (["--ridges", "1.5"], "--ridges is how many ranges"),
            (["--ridges", "2,3"], "--ridges is one number"),
            (["--ridges", "2", "--ridge-height", "1.9"], "--ridge-height is how many degrees"),
            (["--ridges", "2", "--ridge-height", "25.1"], "--ridge-height is how many degrees"),
            (["--ridge-height", "10"], "there are none"),
            (["--ridges", "0", "--ridge-height", "10"], "there are none"),
            (["--ridges", "2", "--ridges", "3"], "said twice"),
        ):
            s, why = S.arguments(["out", "--name", "Day"] + argv)
            self.assertIsNone(s, argv)
            self.assertIn(text, why, argv)


class Words(unittest.TestCase):
    def test_what_it_is_told_is_read(self):
        s, why = S.arguments(["out", "--name", "Day"])
        self.assertIsNone(why)
        self.assertEqual(s, {"out": "out", "name": "Day", "sun": (35.0, 135.0), "clouds": 0.4, "seed": 1, "size": 512,
                             "ridges": 0, "ridge_height": None})
        s, why = S.arguments(["out", "--size", "1024", "--seed", "7", "--clouds", "0", "--sun", "-5,359.5", "--name", "Dusk_2"])
        self.assertIsNone(why)
        self.assertEqual((s["name"], s["sun"], s["clouds"], s["seed"], s["size"]), ("Dusk_2", (-5.0, 359.5), 0.0, 7, 1024))
        # the ends of every range are in it
        for more in (["--seed", "0"], ["--seed", "65535"], ["--clouds", "1"], ["--sun", "90,0"], ["--sun", "-10,0"],
                     ["--size", "256"]):
            s, why = S.arguments(["out", "--name", "Day"] + more)
            self.assertIsNone(why, more)

    def test_what_is_wrong_is_said(self):
        for argv, text in (
            ([], "usage:"),
            (["--name", "Day"], "usage:"),
            (["out"], "--name says what the sky is called"),
            (["out", "--name", "a b"], "--name is the sky's name"),
            (["out", "--name", "../x"], "--name is the sky's name"),
            (["out", "--name"], "has no value"),
            (["out", "--name", "Day", "--moon", "1"], "--moon is not a word"),
            (["out", "--name", "Day", "--sun", "35"], "--sun is <elevation"),
            (["out", "--name", "Day", "--sun", "91,0"], "--sun is <elevation"),
            (["out", "--name", "Day", "--sun", "-11,0"], "--sun is <elevation"),
            (["out", "--name", "Day", "--sun", "35,360"], "--sun is <elevation"),
            (["out", "--name", "Day", "--sun", "high,0"], "--sun is a number"),
            (["out", "--name", "Day", "--sun", "nan,0"], "--sun is a number"),
            (["out", "--name", "Day", "--clouds", "1.1"], "--clouds is 0"),
            (["out", "--name", "Day", "--clouds", "0.2,0.3"], "--clouds is one number"),
            (["out", "--name", "Day", "--seed", "1.5"], "--seed is a whole number"),
            (["out", "--name", "Day", "--seed", "65536"], "--seed is a whole number"),
            (["out", "--name", "Day", "--size", "300"], "--size is 256, 512 or 1024"),
            (["out", "--name", "Day", "--size", "2048"], "--size is 256, 512 or 1024"),
            (["out", "--name", "Day", "--seed", "-1"], "--seed is a whole number"),
            (["out", "--name", "Day", "--clouds", "-0.1"], "--clouds is 0"),
            (["out", "--name", "Day", "--sun", "35,-1"], "--sun is <elevation"),
            (["out", "--name", "-"], "--name is the sky's name"),
            (["out", "--name", "Day", "--name", "Dusk"], "--name is said twice"),
            (["out", "--name", "Day", "--seed", "1", "--seed", "2"], "--seed is said twice"),
        ):
            s, why = S.arguments(argv)
            self.assertIsNone(s, argv)
            self.assertIn(text, why)


if __name__ == "__main__":
    unittest.main()
