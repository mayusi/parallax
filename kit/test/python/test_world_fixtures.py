"""test_world_fixtures.py - STREET FIXTURES (kit/world/worldcheck.py fixture_lint / footpath_lint; LIMITATIONS_FIXES_V3.md
stage C: "enforcing kit world check structural gates: 0 floating plinths, >= 7 st clear footpath").
Held here: a street fixture (a lamp's pole, a plinth, a bench, a bollard ...) that floats is an ERROR, other floaters
are not (a spawn pad, a rock); a road part keeps 7 studs clear across it past what stands ON it (half its footprint or
more) taller than a step - at any angle - and a wall or gate the road runs through is not a thing on it.
Not claimed: that a street with these numbers reads well - that is a built world, looked at."""
import importlib.util
import math
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_world_check_fixtures", os.path.join(HERE, "..", "..", "world", "worldcheck.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def part(name, size, pos, yaw=0.0, collide=True):
    """a block part as the compiler writes it (rot: 3 rows of 3, world = rot @ local; turned about y by yaw degrees)"""
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return {"class": "Part", "name": name, "size": list(size), "pos": list(pos), "rot": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
            "collide": collide, "material": "Slate", "color": [90, 90, 90], "transparency": 0, "shape": "Block"}


def world(*parts):
    return {"parts": [part("Floor", (200, 1, 200), (0, -0.5, 0))] + list(parts)}


class Fixtures(unittest.TestCase):
    def test_what_is_a_fixture(self):
        for n in ("LampPole", "Plinth", "Bench", "Bollard3", "StreetFountain", "TownPump", "Lamppost", "CellarHatch",
                  "WallLantern", "Fingerpost", "Well"):
            self.assertTrue(C.is_fixture(n), n)
        for n in ("Wall", "Spawn", "Rock", "Trunk", "Stairwell", "LampArm", "Floor", "Polearm"):
            self.assertFalse(C.is_fixture(n), n)

    def test_a_floating_fixture_is_an_error_and_other_floaters_are_not(self):
        w = world(part("LampPole", (0.5, 12, 0.5), (10, 12, 0)), part("Spawn", (6, 1, 6), (30, 6, 0)))
        out = {}
        C.look_lint(w, out)
        names = [n for n, _ in out["floaters"]]
        self.assertIn("LampPole", names)
        self.assertIn("Spawn", names)
        errs = C.fixture_lint(out)
        self.assertEqual(len(errs), 1)
        self.assertIn("fixture: 1 street fixture(s) float", errs[0])
        self.assertIn("LampPole", errs[0])
        # stood on the floor: no error
        out = {}
        C.look_lint(world(part("LampPole", (0.5, 12, 0.5), (10, 6, 0))), out)
        self.assertEqual(C.fixture_lint(out), [])
        # held by what it touches (a plinth under a statue, on the floor): no error
        out = {}
        C.look_lint(world(part("Plinth", (4, 1, 4), (0, 0.5, 0)), part("Statue", (2, 6, 2), (0, 4, 0))), out)
        self.assertEqual(C.fixture_lint(out), [])


class Footpath(unittest.TestCase):
    ROAD = ("Road", (60, 0.4, 10), (0, 0.0, 0))  # (top at y 0.2, 10 wide across z)

    def check(self, *things, yaw=0.0):
        road = part(*self.ROAD, yaw=yaw)
        errs, stats = C.footpath_lint(world(road, *things))
        return errs, stats

    def test_a_bench_in_the_middle_of_a_lane_leaves_too_little(self):
        errs, stats = self.check(part("Bench", (6, 2.4, 3), (0, 1.4, 0)))
        self.assertEqual(stats["footpath_narrow"], 1)
        self.assertIn("footpath:", errs[0])
        self.assertIn("leaves 3.5", errs[0])

    def test_at_the_edge_it_leaves_seven(self):
        errs, _ = self.check(part("Bench", (6, 2.4, 3), (0, 1.4, 3.6)))
        self.assertEqual(errs, [])
        errs, _ = self.check(part("Bench", (6, 2.4, 3), (0, 1.4, 3.4)))  # (6.9 clear: not enough)
        self.assertEqual(len(errs), 1)

    def test_two_things_side_by_side_add_up(self):
        # each alone leaves 7.5 of a 10-stud lane on one side; together, at the same place along it, 5 in the middle
        a = part("Bollard", (1, 3, 1), (0, 1.7, -2.75))
        b = part("Bollard", (1, 3, 1), (0, 1.7, 3.25))
        errs, _ = self.check(a)
        self.assertEqual(errs, [])
        errs, _ = self.check(a, b)
        self.assertEqual(len(errs), 1)
        self.assertIn("leaves 5.0", errs[0])
        # far apart along the lane: each leaves its own 7.5
        errs, _ = self.check(a, part("Bollard", (1, 3, 1), (20, 1.7, 3.25)))
        self.assertEqual(errs, [])

    def test_low_things_and_things_overhead_do_not_count(self):
        self.assertEqual(self.check(part("Grate", (4, 0.3, 6), (0, 0.35, 0)))[0], [])  # (walked over)
        self.assertEqual(self.check(part("Sign", (6, 1, 6), (0, 9, 0)))[0], [])  # (over the head)

    def test_a_turned_road(self):
        # the same lane turned 30 degrees, the bench turned with it in its middle
        c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
        errs, _ = self.check(part("Bench", (6, 2.4, 3), (0, 1.4, 0), yaw=30), yaw=30)
        self.assertEqual(len(errs), 1)
        # moved to the lane's edge along the lane's own across axis
        ax, az = s, c  # (the road's local z axis in the world, for a turn about y)
        errs, _ = self.check(part("Bench", (6, 2.4, 3), (3.6 * ax, 1.4, 3.6 * az), yaw=30), yaw=30)
        self.assertEqual(errs, [])

    def test_a_wall_the_road_runs_through_is_not_on_it(self):
        # a town wall across the road's end with a 6-stud gate: the wall lies mostly off the road
        left = part("Wall", (2, 10, 20), (30, 5.2, -13))
        right = part("Wall", (2, 10, 20), (30, 5.2, 13))
        self.assertEqual(self.check(left, right)[0], [])

    def test_no_road_no_check(self):
        errs, stats = C.footpath_lint(world(part("Bench", (6, 2.4, 3), (0, 1.4, 0))))
        self.assertEqual((errs, stats["footpath_roads"]), ([], 0))


if __name__ == "__main__":
    unittest.main()
