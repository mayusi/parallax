"""test_world_scale_v3.py - the r6 scale sheet's V3 entries (kit/world/worldcheck.py SCALE_SHEETS r6 + lamp_spacing;
LIMITATIONS_FIXES_V3.md stage A.2: "1 stud = 0.28 m - doors 5x8+ st, cottages 23+ st, main streets 29-43 st, r6
SCALE_SHEETS extended with exterior / lamp_spacing", and stage C's lamp spacing by place: "Avenues ~110 st
alternating; Lanes junctions / doors only; Squares corners only").
Held here: a cottage claim under 23 studs a side fails, one of 23 passes; a main street is MEASURED (29..43 between
its walls: a 26-stud one and a 50-stud one fail, a 34 passes); an avenue's lamps stand 90..130 apart along it and
alternate sides (40 apart fails, two on one side fail, 110 alternating passes); a lane's lamps stand at a junction
or a door it names (one mid-lane fails); a square's at its corners (one in the middle fails); a claim with no place,
or an avenue with one lamp, is said. Not claimed: that a street lit by these numbers looks right - looked at."""
import importlib.util
import math
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_world_check_scale_v3", os.path.join(HERE, "..", "..", "world", "worldcheck.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def part(name, x, y, z, size, **more):
    p = {"name": name, "pos": [x, y, z], "size": list(size), "rot": I3, "collide": True, "class": "Part"}
    p.update(more)
    return p


def lamp(x, z):
    """a street lamp's lit head, as the row generator writes it"""
    return part("LampHead", x, 11.4, z, (1, 0.5, 1), collide=False, children=[{"kind": "light", "range": 22}])


def scale(parts, fits, grid=False):
    ps = list(parts) + [part("Ground", 0, -1, 0, (300, 2, 300))]
    w = {"name": "T", "scale": "r6", "parts": ps, "fits": fits}
    g = None
    if grid:
        g = C.Grid([-80, -3, -80], [80, 20, 80], 1.0)
        for p in ps:
            if C.is_solid(p):
                g.fill_part(p)
    return [e for e in C.scale_check(w, g)[0] if e.startswith("scale:")]


class Exterior(unittest.TestCase):
    def test_a_cottage_is_23_studs_or_more_a_side(self):
        small = scale([], [{"kind": "exterior", "name": "Shed", "pos": [0, 0, 0], "size": [20, 14, 30]}])
        self.assertEqual(len(small), 1)
        self.assertIn("w 20", small[0])
        self.assertEqual(scale([], [{"kind": "exterior", "name": "Cottage", "pos": [0, 0, 0], "size": [23, 14, 26]}]), [])


class MainStreet(unittest.TestCase):
    def street(self, width):
        walls = [part("Wall", 0, 6, side * (width / 2 + 0.5), (120, 12, 1)) for side in (-1, 1)]
        fit = {"kind": "mainstreet", "name": "High St", "pos": [0, 0, 0], "from": [-40, 0], "to": [40, 0]}
        return scale(walls, [fit], grid=True)

    def test_measured_between_its_walls(self):
        self.assertEqual(self.street(34), [])
        self.assertEqual(len(self.street(26)), 1)  # (a lane, not a main street)
        self.assertEqual(len(self.street(50)), 1)  # (a square, not a main street)


class Lamps(unittest.TestCase):
    AVE = {"kind": "lamp_spacing", "name": "Avenue", "place": "avenue", "pos": [0, 0, 0], "from": [-120, 0], "to": [120, 0]}

    def test_an_avenue_lit_every_110_on_alternate_sides_passes(self):
        lamps = [lamp(-110, 8), lamp(0, -8), lamp(110, 8)]
        self.assertEqual(scale(lamps, [self.AVE]), [])

    def test_lamps_too_close_or_on_one_side_fail(self):
        close = scale([lamp(-40, 8), lamp(0, -8), lamp(40, 8)], [self.AVE])
        self.assertTrue(close and "40 studs apart" in close[0], close)
        one_side = scale([lamp(-110, 8), lamp(0, 8), lamp(110, -8)], [self.AVE])
        self.assertTrue(any("one side" in e for e in one_side), one_side)
        lone = scale([lamp(0, 8)], [self.AVE])
        self.assertTrue(lone and "1 found" in lone[0], lone)
        # (a lamp across the street on another avenue does not count on this one)
        self.assertEqual(scale([lamp(-110, 8), lamp(0, -8), lamp(110, 8), lamp(55, 60)], [self.AVE]), [])

    def test_a_lane_is_lit_at_its_junctions_and_doors_only(self):
        fit = {"kind": "lamp_spacing", "name": "Lane", "place": "lane", "pos": [0, 0, 0], "from": [-60, 0],
               "to": [60, 0], "at": [[-60, 0], [20, 4]]}
        self.assertEqual(scale([lamp(-58, 3), lamp(22, 5)], [fit]), [])
        mid = scale([lamp(-58, 3), lamp(-20, 3)], [fit])
        self.assertTrue(mid and "names no junction or door" in mid[0], mid)
        bare = dict(fit)
        del bare["at"]
        self.assertEqual(len(scale([lamp(-58, 3)], [bare])), 1)  # (a lane naming no junction or door: no lamp)

    def test_a_square_is_lit_at_its_corners(self):
        fit = {"kind": "lamp_spacing", "name": "Square", "place": "square", "pos": [0, 0, 0], "size": [80, 1, 60]}
        corners = [lamp(-36, -26), lamp(36, -26), lamp(36, 26), lamp(-36, 26)]
        self.assertEqual(scale(corners, [fit]), [])
        centre = scale(corners + [lamp(0, 0)], [fit])
        self.assertTrue(centre and "off the square's corners" in centre[0], centre)

    def test_a_claim_says_its_place(self):
        bad = dict(self.AVE)
        bad["place"] = "boulevard"
        self.assertTrue(any('"place"' in e for e in scale([lamp(0, 8)], [bad])))


if __name__ == "__main__":
    unittest.main()
