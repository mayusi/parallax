"""kit/world/townplan.py - the town plan page (`kit world town <Name>`): the record a "town" step leaves in the compiled
world, drawn from above so a layout can be READ before anything is dressed. The page's geometry (north up, a lot's
door on its own front, the landmark the one warm colour) and its words (every gate's walk, the kit of house types).
Run: python kit/test/python/run.py -k world_townplan"""

import contextlib
import importlib.util
import io
import json
import math
import os
import tempfile
import unittest

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
# (loaded by path under its own name: the lanes' tools share module names - kit/test/python/run.py's note)
_spec = importlib.util.spec_from_file_location("kit_world_townplan", os.path.join(ROOT, "kit", "world", "townplan.py"))
TP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TP)


def rect(x0, z0, x1, z1):
    return {"x0": x0, "x1": x1, "z0": z0, "z1": z1}


def town():
    """a hand-made record: a 200 x 100 town, a square in the middle, one main street to the S gate, three lots"""
    return {
        "name": "Old Town", "seed": 9,
        "area": rect(-100, -50, 100, 50),
        "square": rect(-20, -10, 20, 10),
        "streets": [
            {"name": "South street", "rank": "main", "axis": "z", "at": 0, "from": 10, "to": 50, "width": 32},
            {"name": "Lane 1", "rank": "lane", "axis": "x", "at": -30, "from": -100, "to": 100, "width": 12},
        ],
        "blocks": [rect(-90, -20, -24, 40)],
        "lots": [
            {"name": "House 1.1", "rect": rect(-90, -20, -70, 4), "front": "N", "rank": 2, "floors": 2, "height": 28, "type": "20x24_2f14"},
            {"name": "House 1.2", "rect": rect(-70, -20, -50, 4), "front": "N", "rank": 2, "floors": 4, "height": 56, "type": "20x24_4f14"},
            {"name": "Landmark", "rect": rect(-48, -20, -24, 20), "front": "E", "rank": 4, "floors": 6, "height": 84, "landmark": True, "type": "landmark_40x24_6f14"},
        ],
        "types": [{"type": f"16x24_{k}f14", "count": 40 - k} for k in range(2, 40)],
        "gates": ["S"], "mainGate": "S", "view": {"from": "S", "at": [0, -10]},
        "nodes": [
            {"x": 0, "z": 50, "kind": "gate", "name": "S gate", "degree": 1},
            {"x": 0, "z": -30, "kind": "junction", "degree": 3},
            {"x": 60, "z": -30, "kind": "junction", "degree": 4},
            {"x": -100, "z": -30, "kind": "deadend", "degree": 1},
        ],
        "measures": {
            "lots": 3, "blocks": 1, "loops": 2, "deadEnds": 1, "tees": 1, "crossings": 1, "squareClosed": 0.8,
            "walks": [{"gate": "S gate", "studs": 80, "seconds": 5}], "farthestSeconds": 9.4,
            "vista": {"length": 200, "street": "Lane 1", "closed": True}, "frontageBuilt": 0.92, "cutOff": 2,
            "streets": {"main": {"count": 1, "length": 40}, "lane": {"count": 1, "length": 200}},
        },
        "summary": "3 house(s) of 3 type(s) in 1 block(s)",
    }


class GeometryTest(unittest.TestCase):
    def test_the_area_sits_inside_the_box_centred_north_up(self):
        t = town()
        k, ox, oy = TP.fit(t["area"])
        x0, y0 = TP.to_px(k, ox, oy, -100, -50)  # the north-west corner
        x1, y1 = TP.to_px(k, ox, oy, 100, 50)
        box = TP.PLAN_BOX
        self.assertGreaterEqual(x0, box[0] - 1e-6)
        self.assertLessEqual(x1, box[2] + 1e-6)
        self.assertGreaterEqual(y0, box[1] - 1e-6)
        self.assertLessEqual(y1, box[3] + 1e-6)
        self.assertLess(y0, y1)  # north (-Z) is up
        self.assertAlmostEqual(x0 - box[0], box[2] - x1, places=6)  # centred across
        self.assertAlmostEqual(y0 - box[1], box[3] - y1, places=6)  # and down
        self.assertAlmostEqual((x1 - x0) / 200, (y1 - y0) / 100, places=6)  # one scale both ways: no squashed town

    def test_a_streets_strip_follows_its_axis(self):
        self.assertEqual(TP.strip({"axis": "z", "at": 0, "from": 10, "to": 50, "width": 32}), (-16, 10, 16, 50))
        self.assertEqual(TP.strip({"axis": "x", "at": -30, "from": -100, "to": 100, "width": 12}), (-100, -36, 100, -24))

    def test_a_door_is_marked_on_the_lots_own_front(self):
        k, ox, oy = 2.0, 0.0, 0.0
        for front, fixed, axis in (("N", -20, 1), ("S", 4, 1), ("W", -90, 0), ("E", -70, 0)):
            a, b = TP.door_mark({"rect": rect(-90, -20, -70, 4), "front": front}, k, ox, oy)
            self.assertEqual(a[axis], fixed * k)
            self.assertEqual(b[axis], fixed * k)
            other = 1 - axis
            self.assertAlmostEqual(abs(b[other] - a[other]), 5 * k)  # a door's width of line
            mid = (a[other] + b[other]) / 2
            centre = (-80 if other == 0 else -8) * k
            self.assertAlmostEqual(mid, centre)  # in the middle of the front

    def test_taller_is_lighter_and_the_landmark_is_the_one_warm_colour(self):
        two, four = TP.lot_colour({"floors": 2}), TP.lot_colour({"floors": 4})
        self.assertLess(sum(two), sum(four))
        self.assertEqual(TP.lot_colour({"floors": 9}), TP.FLOORS[4])
        lm = TP.lot_colour({"floors": 6, "landmark": True})
        self.assertEqual(lm, TP.LANDMARK)
        self.assertGreater(lm[0] - lm[2], 100)  # warm
        for c in TP.FLOORS.values():
            self.assertLess(abs(c[0] - c[2]), 40)  # every house a cool grey


class WordsTest(unittest.TestCase):
    def test_the_numbers_a_layout_is_read_by(self):
        text = "\n".join(line for line, _ in TP.rows(town()))
        for needle in ("3 houses in 1 blocks, 2 streets", "main: 1 - 40 studs", "loops a walker can make: 2; dead ends: 1",
                       "T-junctions (a house front ends the view): 1; crossings: 1", "walled along 80% of its edge",
                       "S gate to the square: 5 s on foot (80 studs)", "farthest corner from the square: 9 s",
                       "longest straight view: 200 studs (Lane 1, ends inside the town)", "92% of the street fronts are built",
                       "2 junction(s) no street joins to the square", "The kit of houses: 38 types"):
            self.assertIn(needle, text)

    def test_a_town_made_of_modules_says_how_many_in_place_of_how_many_house_meshes(self):
        t = town()
        self.assertNotIn("modules", "\n".join(line for line, _ in TP.rows(t)))
        t["modules"] = 13
        text = "\n".join(line for line, _ in TP.rows(t))
        self.assertIn("Made of 13 modules by a facade grammar (in place of 38 whole-house meshes)", text)
        self.assertIn("The kit of houses: 38 types", text)

    def test_a_long_kit_is_cut_to_the_pages_room_and_says_what_it_left_out(self):
        lines = TP.rows(town())
        self.assertLessEqual(len(lines), 31)
        last = lines[-1][0]
        self.assertIn("more types", last)
        shown = [line for line, _ in lines if " x  16x24_" in line]
        left = 38 - len(shown)
        self.assertIn(f"and {left} more types", last)
        # the houses it left out are counted, not dropped
        self.assertIn(f"({sum(40 - k for k in range(2 + len(shown), 40))} houses)", last)

    def test_a_view_that_runs_out_of_a_gate_is_said(self):
        t = town()
        t["measures"]["vista"]["closed"] = False
        self.assertIn("runs out of a gate", "\n".join(line for line, _ in TP.rows(t)))


class PageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_page_shows_the_square_the_lots_and_the_landmark_where_they_stand(self):
        t = town()
        path = os.path.join(self.tmp.name, "plan.png")
        drew = TP.draw(t, "World", path)
        self.assertEqual(drew["lots"], 3)
        img = Image.open(path).convert("RGB")
        self.assertEqual(img.size, TP.PAGE)
        k, ox, oy = TP.fit(t["area"])

        def at(x, z):
            px, py = TP.to_px(k, ox, oy, x, z)
            return img.getpixel((int(px), int(py)))

        self.assertEqual(at(15, 6), TP.SQUARE)  # a corner of the square, clear of its name
        self.assertEqual(at(-85, -14), TP.FLOORS[2])  # the 2-storey house
        self.assertEqual(at(-55, -14), TP.FLOORS[4])  # the 4-storey house beside it
        self.assertEqual(at(-44, -16), TP.LANDMARK)  # the landmark's corner, clear of its name
        self.assertEqual(at(-60, 30), TP.BLOCK)  # the block's yard behind them
        self.assertEqual(at(-60, -40), TP.STREET["alley"])  # open ground north of the lane
        self.assertEqual(at(60, -27), TP.STREET["lane"])  # the lane
        self.assertEqual(at(12, 30), TP.STREET["main"])  # the main street, off its centre line (the view's dashes)

    def test_main_draws_a_page_a_town_and_tells_where_to_look(self):
        world = os.path.join(self.tmp.name, "World.json")
        with open(world, "w", encoding="utf-8") as f:
            json.dump({"name": "World", "towns": [town()]}, f)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = TP.main([world, "--out", os.path.join(self.tmp.name, "pages")])
        r = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(r["status"], "pass")
        self.assertEqual(len(r["pages"]), 1)
        self.assertTrue(os.path.isfile(r["pages"][0]))
        self.assertTrue(r["pages"][0].endswith("World_Old Town.png"))
        self.assertTrue(r["next_action"].startswith("LOOK: "))
        self.assertIn("3 house(s)", r["summary"])

    def test_two_towns_of_one_name_keep_a_page_each(self):
        world = os.path.join(self.tmp.name, "Twin.json")
        with open(world, "w", encoding="utf-8") as f:
            json.dump({"name": "Twin", "towns": [town(), town()]}, f)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            TP.main([world, "--out", os.path.join(self.tmp.name, "twin")])
        pages = json.loads(out.getvalue())["pages"]
        self.assertEqual(len(set(pages)), 2)
        self.assertTrue(all(os.path.isfile(p) for p in pages))

    def test_a_world_with_no_town_is_a_failure_that_says_what_to_add(self):
        world = os.path.join(self.tmp.name, "Plain.json")
        with open(world, "w", encoding="utf-8") as f:
            json.dump({"name": "Plain", "parts": []}, f)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = TP.main([world])
        r = json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(r["status"], "fail")
        self.assertIn('no "town" step', r["summary"])
        self.assertIn("town", r["next_action"])


def turned(x, z, cx, cz, deg):
    """a point turned about (cx, cz) the way the compiler turns one (CFrame.Angles(0, yaw, 0))"""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    dx, dz = x - cx, z - cz
    return [cx + c * dx + s * dz, cz - s * dx + c * dz]


def bent_town(deg=20.0):
    """the hand-made town with its block (and the three lots on it) turned `deg` about the block's middle, as a bent
    town's record carries it: a "quad" on every lot and block (NW, NE, SE, SW of its rect), a "line" on every street"""
    t = town()
    b = t["blocks"][0]
    cx, cz = (b["x0"] + b["x1"]) / 2, (b["z0"] + b["z1"]) / 2

    def quad(r):
        return [turned(x, z, cx, cz, deg) for x, z in ((r["x0"], r["z0"]), (r["x1"], r["z0"]), (r["x1"], r["z1"]), (r["x0"], r["z1"]))]

    b["quad"] = quad(b)
    for lot in t["lots"]:
        lot["quad"] = quad(lot["rect"])
        lot["turn"] = deg
    t["streets"][0]["line"] = [[0, 10], [2, 30], [6, 50]]
    t["streets"][1]["line"] = [[-100, -30], [0, -34], [100, -30]]
    t["bend"] = 8
    t["measures"]["bend"] = 8
    t["measures"]["wider"] = {"mean": 0.46, "most": 6.2}
    t["measures"]["landmarkSeen"] = {"fromGate": True, "share": 0.9}
    return t


class BentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_bent_lots_door_is_marked_on_its_own_turned_front(self):
        t = bent_town(20.0)
        k, ox, oy = 2.0, 0.0, 0.0
        for lot in t["lots"]:
            q = TP.lot_quad(lot)
            i, j = {"N": (0, 1), "E": (1, 2), "S": (2, 3), "W": (3, 0)}[lot["front"]]
            a, b = TP.door_mark(lot, k, ox, oy)
            mid = ((a[0] + b[0]) / 2 / k, (a[1] + b[1]) / 2 / k)
            self.assertAlmostEqual(mid[0], (q[i][0] + q[j][0]) / 2, places=6)  # the middle of the front as it stands
            self.assertAlmostEqual(mid[1], (q[i][1] + q[j][1]) / 2, places=6)
            self.assertAlmostEqual(math.hypot(b[0] - a[0], b[1] - a[1]), 5 * k, places=6)  # a door's width of line
            # ... and it lies ALONG that front (not along a world axis)
            ex, ez = q[j][0] - q[i][0], q[j][1] - q[i][1]
            self.assertAlmostEqual(abs((b[0] - a[0]) * ez - (b[1] - a[1]) * ex), 0.0, places=6)
        # a straight town's lot has no quad: its corners are its rect's, in the same order
        plain = town()["lots"][0]
        self.assertEqual(TP.lot_quad(plain), [(-90, -20), (-70, -20), (-70, 4), (-90, 4)])
        self.assertEqual(TP.quad_centre(TP.lot_quad(plain)), (-80, -8))

    def test_the_page_paints_a_bent_town_where_it_stands(self):
        t = bent_town(20.0)
        path = os.path.join(self.tmp.name, "bent.png")
        TP.draw(t, "World", path)
        img = Image.open(path).convert("RGB")
        k, ox, oy = TP.fit(t["area"])

        def at(x, z):
            px, py = TP.to_px(k, ox, oy, x, z)
            return img.getpixel((int(px), int(py)))

        b = t["blocks"][0]
        cx, cz = (b["x0"] + b["x1"]) / 2, (b["z0"] + b["z1"]) / 2
        # each lot's colour is at its TURNED middle (a little off it for the landmark: its name is written there)
        self.assertEqual(at(*turned(-85, -14, cx, cz, 20.0)), TP.FLOORS[2])
        self.assertEqual(at(*turned(-55, -14, cx, cz, 20.0)), TP.FLOORS[4])
        self.assertEqual(at(*turned(-44, -16, cx, cz, 20.0)), TP.LANDMARK)
        # the block's yard is turned with them; a corner the straight block covered is street now
        self.assertEqual(at(*turned(-60, 30, cx, cz, 20.0)), TP.BLOCK)
        self.assertNotEqual(at(-88, 38), TP.BLOCK)
        # the main street is a band along its bent middle line: on the line near its far end, not where it ran straight
        self.assertEqual(at(10, 36), TP.STREET["main"])
        self.assertEqual(at(-15, 36), TP.STREET["alley"])  # (straight, x -15 at z 36 was inside the 32-wide street)

    def test_a_bent_towns_numbers_say_the_bend_and_what_it_cost_the_streets(self):
        text = "\n".join(line for line, _ in TP.rows(bent_town()))
        self.assertIn("streets bent 8 degrees: each block turned as one piece", text)
        self.assertIn("a street at its narrowest: as planned +0.5 studs on average, +6.2 at most", text)
        self.assertIn("the landmark is seen from the main gate, and from 90% of its street", text)
        hidden = bent_town()
        hidden["measures"]["landmarkSeen"] = {"fromGate": False, "share": 0.25}
        self.assertIn("the landmark is NOT seen from the main gate, and from 25% of its street", "\n".join(line for line, _ in TP.rows(hidden)))
        # every line of the numbers fits the page: its text starts at x 1290 on a page 1920 wide
        from PIL import ImageDraw as _D, Image as _I

        d = _D.Draw(_I.new("RGB", (10, 10)))
        for t in (bent_town(), hidden):
            t["measures"]["bend"] = 7.5
            for line, kind in TP.rows(t):
                size = 24 if kind == "h" else (14 if kind == "d" else 19)
                self.assertLessEqual(1290 + d.textlength(line, font=TP.font(size, kind == "h")), TP.PAGE[0] - 8, line)
        # a straight town says nothing of a bend
        self.assertNotIn("bent", "\n".join(line for line, _ in TP.rows(town())))


class LampsTest(unittest.TestCase):
    def test_the_towns_own_lamps_are_counted_by_reason_and_ringed_where_they_stand(self):
        t = town()
        self.assertNotIn("lamps", " | ".join(line for line, _ in TP.rows(t)))  # (a town that set none says nothing)
        t["lamps"] = [{"x": 60, "z": 30, "why": "gate"}, {"x": -10, "z": 30, "why": "mouth"}, {"x": 70, "z": -40, "why": "mouth"}]
        self.assertIn("3 lamps, each with a reason: 1 at a gate, 2 at mouths", " | ".join(line for line, _ in TP.rows(t)))
        # a lamp recorded with no reason still draws and is still counted (it raised a TypeError)
        odd = town()
        odd["lamps"] = [{"x": 60, "z": 30, "why": "gate"}, {"x": -10, "z": 30}]
        self.assertIn("2 lamps, each with a reason: 1 at a gate, 1 at a place", " | ".join(line for line, _ in TP.rows(odd)))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "lamps.png")
            TP.draw(t, "World", path)
            img = Image.open(path).convert("RGB")
        k, ox, oy = TP.fit(t["area"])
        for lamp in t["lamps"]:
            px, py = TP.to_px(k, ox, oy, lamp["x"], lamp["z"])
            self.assertEqual(img.getpixel((int(px) + 5, int(py))), TP.LAMP, lamp)  # on the ring
            self.assertNotEqual(img.getpixel((int(px), int(py))), TP.LAMP, lamp)  # a ring, not a blob


class SlopeTest(unittest.TestCase):
    def test_a_town_on_a_slope_says_so_on_the_page_and_a_level_one_says_nothing(self):
        t = town()
        self.assertNotIn("hillside", " | ".join(line for line, _ in TP.rows(t)))
        t["slope"] = {"rise": 4.5, "toward": "E", "drop": 18.0}
        self.assertIn("on a hillside: 4.5 studs up in 100 toward the east, 18 from edge to edge", [line for line, _ in TP.rows(t)])
        t["slope"] = {"rise": 6, "toward": "N", "drop": 19.2}
        self.assertIn("on a hillside: 6 studs up in 100 toward the north, 19 from edge to edge", [line for line, _ in TP.rows(t)])
        d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        for line, kind in TP.rows(t):
            size = 24 if kind == "h" else (14 if kind == "d" else 19)
            self.assertLessEqual(1290 + d.textlength(line, font=TP.font(size, kind == "h")), TP.PAGE[0] - 8, line)


class YardsTest(unittest.TestCase):
    def test_the_yards_things_are_counted_on_the_page_and_drawn_where_they_stand(self):
        t = town()
        self.assertNotIn("in the yards", " | ".join(line for line, _ in TP.rows(t)))  # (a town with none says nothing)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bare.png")
            TP.draw(t, "World", path)
            bare = Image.open(path).convert("RGB")
        t["yardThings"] = [
            {"kind": "pile", "x": 12, "z": 6, "turn": 4.0, "alongX": True},
            {"kind": "pile", "x": 30, "z": 20, "alongX": False},
            {"kind": "line", "x": 44, "z": 6, "turn": 0.0, "alongX": True, "span": 12},
        ]
        self.assertIn("in the yards with a gate: 2 woodpiles, 1 wash lines", [line for line, _ in TP.rows(t)])
        self.assertNotIn("shut yards opened", " | ".join(line for line, _ in TP.rows(t)))
        t["yardWays"] = [{"yard": 1, "block": 1, "front": "S", "gate": {"x": -40, "z": 44}}, {"yard": 2, "block": 2, "front": "W", "gate": {"x": 52, "z": -30}}]
        self.assertIn("2 shut yards opened: a court and a gate in place of one house", [line for line, _ in TP.rows(t)])
        one = dict(t, yardWays=t["yardWays"][:1])
        self.assertIn("1 shut yard opened: a court and a gate in place of one house", [line for line, _ in TP.rows(one)])
        d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        for line, kind in TP.rows(t):
            size = 24 if kind == "h" else (14 if kind == "d" else 19)
            self.assertLessEqual(1290 + d.textlength(line, font=TP.font(size, kind == "h")), TP.PAGE[0] - 8, line)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "yards.png")
            TP.draw(t, "World", path)
            img = Image.open(path).convert("RGB")
        k, ox, oy = TP.fit(t["area"])
        for th in t["yardThings"]:
            px, py = TP.to_px(k, ox, oy, th["x"], th["z"])
            at = (int(px), int(py))
            self.assertEqual(img.getpixel(at), TP.STALL, th)  # a pile's box, a line's stroke, at its middle
            self.assertNotEqual(bare.getpixel(at), TP.STALL, th)
        for way in t["yardWays"]:
            px, py = TP.to_px(k, ox, oy, way["gate"]["x"], way["gate"]["z"])
            self.assertEqual(img.getpixel((int(px), int(py))), TP.GATE, way)  # the way's gate, a green mark
            self.assertNotEqual(bare.getpixel((int(px), int(py))), TP.GATE, way)


class MarketTest(unittest.TestCase):
    def test_a_market_is_counted_on_the_page_and_each_stall_drawn_where_it_stands(self):
        t = town()
        self.assertNotIn("market", " | ".join(line for line, _ in TP.rows(t)))  # (a town with none says nothing)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bare.png")
            TP.draw(t, "World", path)
            bare = Image.open(path).convert("RGB")
        t["stalls"] = [{"x": 12, "z": 6, "turn": 4.0}, {"x": 26, "z": 6, "turn": -5.0}, {"x": 12, "z": 22}]
        lines = [line for line, _ in TP.rows(t)]
        self.assertIn("a market of 3 stalls on the square (the gate view kept clear)", lines)
        d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        for line, kind in TP.rows(t):  # the market's line fits the page (it ran off the right edge once)
            size = 24 if kind == "h" else (14 if kind == "d" else 19)
            self.assertLessEqual(1290 + d.textlength(line, font=TP.font(size, kind == "h")), TP.PAGE[0] - 8, line)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "market.png")
            TP.draw(t, "World", path)
            img = Image.open(path).convert("RGB")
        k, ox, oy = TP.fit(t["area"])
        for stall in t["stalls"]:
            px, py = TP.to_px(k, ox, oy, stall["x"], stall["z"])
            at = (int(px), int(py))
            self.assertEqual(img.getpixel(at), TP.STALL, stall)  # the stall's box, at its middle
            self.assertNotEqual(bare.getpixel(at), TP.STALL, stall)  # ... which a town with no market does not draw


if __name__ == "__main__":
    unittest.main()
