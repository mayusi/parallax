"""test_world_zceil.py - a CEILING's z-fighting is an error of `kit world check` too (kit/world/worldcheck.py zfight_lint;
card my7f, LIMITATIONS_FIXES_V4 5.1 "z-fighting misses ceilings"). Before, every face that faced down was left out, so a
plaster ceiling and the oak beam under it, their undersides in one plane, flickered over a player's head unflagged.
Held here: two undersides of two looks in one plane overlapping are an error when straight below them lies a floor
(a part's top, the land of a ground op, a terrain solid) at least 2 studs down; a foot on the land or on a slab, an
underside with nothing under it, a 1-stud gap and a beam lowered 0.08 are not. Not claimed: the depth precision of
Roblox's renderer (0.03 is the V3 band, 2 studs a chosen clearance)."""
import importlib.util
import os
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_worldcheck_zceil", os.path.join(HERE, "..", "..", "world", "worldcheck.py"))
WC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(WC)

PLASTER = ("SmoothPlastic", (200, 196, 186))
OAK = ("Wood", (90, 60, 40))


def part(name, pos, size, mat="Slate", color=(90, 90, 90), rot=None, transparency=0):
    return {"class": "Part", "name": name, "pos": list(pos), "size": list(size), "material": mat, "color": list(color),
            "rot": rot or [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "shape": "Block", "transparency": transparency}


def yaw(deg):
    a = np.radians(deg)
    c, s = float(np.cos(a)), float(np.sin(a))
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


FLOOR = part("Floor", (0, -0.5, 0), (40, 1, 40))
# a room's ceiling 10 studs up (its underside at y 10) and an oak beam whose underside is the SAME plane
CEIL = part("Ceiling", (0, 10.5, 0), (20, 1, 20), *PLASTER)
BEAM = part("Beam", (0, 11, 0), (2, 2, 18), *OAK)


def lint(*ps, terrain=None):
    w = {"parts": list(ps)}
    if terrain:
        w["terrain"] = terrain
    return WC.zfight_lint(w)


class Ceiling(unittest.TestCase):
    def test_a_beam_in_the_plane_of_the_ceiling_over_a_floor_is_an_error(self):
        e, p = lint(FLOOR, CEIL, BEAM)
        self.assertEqual(len(p), 1, p)
        self.assertTrue(p[0]["ceiling"])
        self.assertAlmostEqual(p[0]["area"], 36.0, places=3)  # (the beam's 2 x 18 underside)
        self.assertAlmostEqual(p[0]["at"][1], 10.0, places=1)
        self.assertEqual(len(e), 1)
        self.assertIn("underside", e[0])
        self.assertIn("ceilings", e[0])

    def test_the_beam_lowered_clear_passes(self):
        beam = part("Beam", (0, 10.92, 0), (2, 2, 18), *OAK)  # (its underside 0.08 under the ceiling's)
        self.assertEqual(lint(FLOOR, CEIL, beam)[1], [])

    def test_nothing_under_it_is_under_the_world(self):
        # (the same pair with no floor: nobody stands below to see it)
        self.assertEqual(lint(CEIL, BEAM)[1], [])

    def test_a_gap_a_head_cannot_get_under_is_left_out(self):
        floor = part("Floor", (0, 8.5, 0), (40, 1, 40))  # (its top at y 9: one stud under the undersides)
        self.assertEqual(lint(floor, CEIL, BEAM)[1], [])
        floor = part("Floor", (0, 7.5, 0), (40, 1, 40))  # (two studs: a ceiling again)
        self.assertEqual(len(lint(floor, CEIL, BEAM)[1]), 1)

    def test_a_foot_on_a_slab_is_not_a_ceiling(self):
        # a wall and a wooden post standing on the court, their feet in the court's top plane: buried in the court
        wall = part("Wall", (0, 5, 0), (20, 10, 1), "Brick", (140, 60, 50))
        post = part("Post", (0, 5, 0), (1, 10, 1), *OAK)
        self.assertEqual([x for x in lint(FLOOR, wall, post)[1] if x["ceiling"]], [])

    def test_over_the_land_of_a_ground_op(self):
        # no floor part: the land (a flat ground op at y 0) is what the player stands on
        ground = {"x0": -40, "z0": -40, "step": 8, "nx": 11, "nz": 11, "heights": [0.0] * 121}
        e, p = lint(CEIL, BEAM, terrain={"ground": [ground]})
        self.assertEqual(len(p), 1)
        self.assertTrue(p[0]["ceiling"])
        # and the land up to a stud under it: unseen
        ground = dict(ground, heights=[9.0] * 121)
        self.assertEqual(lint(CEIL, BEAM, terrain={"ground": [ground]})[1], [])

    def test_over_a_terrain_solid(self):
        solid = {"pos": [0, -2, 0], "size": [40, 4, 40]}
        self.assertEqual(len(lint(CEIL, BEAM, terrain={"solids": [solid]})[1]), 1)

    def test_a_turned_ceiling_is_measured(self):
        ceil = part("Ceiling", (0, 10.5, 0), (20, 1, 20), *PLASTER, rot=yaw(30))
        beam = part("Beam", (0, 11, 0), (2, 2, 18), *OAK, rot=yaw(30))
        e, p = lint(FLOOR, ceil, beam)
        self.assertEqual(len(p), 1)
        self.assertAlmostEqual(p[0]["area"], 36.0, places=3)

    def test_a_glass_floor_is_seen_through(self):
        # a see-through floor is not where the player stands looking up: the one under it is (12 studs down)
        glass = part("Glass", (0, 9.5, 0), (40, 1, 40), "Glass", (200, 220, 230), transparency=0.6)
        self.assertEqual(len(lint(FLOOR, glass, CEIL, BEAM)[1]), 1)


if __name__ == "__main__":
    unittest.main()
