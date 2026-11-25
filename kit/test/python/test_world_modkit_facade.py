"""kit/world/modkit_facade.py - the W3 KIT CUT AS THE COMPILER'S FACADE MODULES (kind "gothic_module", "kit": "w3";
the owner, 2026-11-23: "keep rolling straight through W3 GothicCourtyard swap"). Held here, on the geometry alone (no
Blender): every module of a court's kit builds on the two shared trim sheets only, each face at the kit's density and
inside its strip; an opening IS the building's gap (its jambs the gap's sides, its crown the gap's top, its sill the
gap's sill) so what you see is what you walk through - and a doorway has NO leaves in it; the wall under a sill and
over a crown is whole, front and back; every face a player looks at is drawn to the side he stands on (Roblox draws
one); the roof covers its box with a ridge along its depth; the quoin closes the corner the walls leave open; a
recipe whose gap is not its width is refused. The sheets' PNGs are written without PIL (Blender's Python has none).
Not claimed: how it reads in Roblox (the meshes and the sheets are uploaded by the orchestrator), the look (the
owner's). Run: python kit/test/python/run.py -k world_modkit_facade"""
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(HERE, "..", "..", "world")
sys.path.insert(0, WORLD)
import modkit as M  # noqa: E402
import modkit_facade as F  # noqa: E402
import trims as T  # noqa: E402

TH = 1.2
WIN = {"width": 3.4, "height": 10.5, "sill": 3.5}  # GothicCourtyard's: sill 3.5 + a 7-stud window
DOOR = {"width": 5.0, "height": 9.0, "sill": 0.0}


def recipe(module, **more):
    r = {"name": "m", "kind": "gothic_module", "kit": "w3", "module": module, "floorHeight": 14, "thickness": TH}
    r["size"] = {"wall": [4, 14, TH], "window": [3.4, 14, TH], "windowb": [3.4, 14, TH], "door": [5, 14, TH],
                 "oriel": [3.4, 14, TH + 2], "band": [8, 0.7, 0.6], "roof": [20, 14, 24], "chimney": [2.4, 7, 2.4],
                 "quoin": [2.75, 14, 2.75]}[module]
    if module in ("window", "windowb", "oriel"):
        r["gap"] = dict(WIN)
    if module == "door":
        r["gap"] = dict(DOOR)
    r.update(more)
    return r


def polys(cut, sheet=None):
    """every triangle of the module (all its parts, or one sheet's) in Roblox axes"""
    out = []
    for p in cut["parts"]:
        if sheet and p["sheet"] != sheet:
            continue
        out += [[tuple(p["verts"][i]) for i in f] for f in p["faces"]]
    return out


def normal(tri):
    a, b, c = (np.array(q) for q in tri)
    return np.cross(b - a, c - a)


def hit(tris, eye, target):
    """the first triangle a look from eye toward target meets (to 1.05 of the way): True = its drawn side is to the
    eye, False = its back is (Roblox shows nothing there), None = nothing"""
    eye, d = np.array(eye, float), np.array(target, float) - np.array(eye, float)
    best = None
    for tri in tris:
        a, b, c = (np.array(q, float) for q in tri)
        e1, e2 = b - a, c - a
        h = np.cross(d, e2)
        det = e1 @ h
        if abs(det) < 1e-12:
            continue
        s = eye - a
        u = (s @ h) / det
        q = np.cross(s, e1)
        v = (d @ q) / det
        t = (e2 @ q) / det
        if u < -1e-9 or v < -1e-9 or u + v > 1 + 1e-9 or t <= 1e-9 or t > 1.05:
            continue
        if best is None or t < best[0] - 1e-9:
            best = (t, bool(normal(tri) @ d < 0))
    return None if best is None else best[1]


def through(tris, x, y, z0=-3.0, z1=3.0):
    """does anything stand between the street and the room at (x, y)? (a look straight through the wall)"""
    return hit(tris, (x, y, z1), (x, y, z0)) is not None


class SheetsTest(unittest.TestCase):
    def test_every_module_is_on_the_two_shared_sheets_at_the_kit_s_density_inside_its_strips(self):
        for module in F.MODULES:
            cut = F.module(recipe(module))
            self.assertTrue(cut["parts"], module)
            sheets = [p["sheet"] for p in cut["parts"]]
            self.assertEqual(len(sheets), len(set(sheets)), module)  # (one part a sheet: one SurfaceAppearance each)
            self.assertTrue(set(sheets) <= set(T.SHEETS), module)
            for part in cut["parts"]:
                mesh = M.Mesh()
                mesh.v, mesh.f, mesh.uv = part["verts"], part["faces"], part["uvs"]
                for wa, d in mesh.tri_area_density():
                    if wa >= 0.02:
                        self.assertTrue(M.DENSITY[0] - 1e-6 <= d <= M.DENSITY[1] + 1e-6, (module, d))
                rows = [(t, h) for s, (sh, t, h) in T.STRIPS.items() if sh == part["sheet"]]
                for a, b, c in part["faces"]:
                    vs = [(1 - part["uvs"][i][1]) * T.SHEET for i in (a, b, c)]
                    self.assertTrue(any(all(t + M.INSET_PX - 1e-3 <= v <= t + h - M.INSET_PX + 1e-3 for v in vs)
                                        for t, h in rows), (module, vs))
                self.assertLessEqual(len(part["faces"]), M.MAX_TRIS, module)
                for tri in [[part["verts"][i] for i in f] for f in part["faces"]]:
                    self.assertGreater(np.linalg.norm(normal(tri)), 1e-9, module)  # (no face of no size)

    def test_a_court_of_houses_wears_six_maps(self):
        sheets = {p["sheet"] for m in F.MODULES for p in F.module(recipe(m))["parts"]}
        self.assertEqual(len(sheets) * len(T.MAPS), 6)
        self.assertEqual(T.names(), [f"kit_trim_{s}_{m}.png" for s in T.SHEETS for m in T.MAPS])


class OpeningTest(unittest.TestCase):
    def test_the_opening_is_the_building_s_gap_open_through_and_whole_round_it(self):
        for module, gap in (("window", WIN), ("windowb", WIN), ("door", DOOR)):
            cut = F.module(recipe(module))
            stone = polys(cut, "stone")
            half, sill, top = gap["width"] / 2, gap["sill"], gap["height"]
            spring = top - half * np.sqrt(3)
            # through the stone: open across the gap below the springing, and up the middle to just under the crown
            for x in (-half + 0.05, -half / 2, 0.3, half - 0.05):
                for y in (sill + 0.2, (sill + spring) / 2, spring - 0.1):
                    self.assertFalse(through(stone, x, y), (module, x, y))
            self.assertFalse(through(stone, 0.05, top - 0.08), module)
            # ... the crown IS the gap's top, the jambs its sides: stone over it and beside it (in the neighbours)
            self.assertTrue(through(stone, 0.05, top + 0.08), module)
            self.assertTrue(through(stone, 0.0, (top + 14) / 2), module)
            if sill > 0:
                self.assertTrue(through(stone, 0.0, sill / 2), module)
            # the module's own width IS the gap (the walls beside it are the neighbours')
            xs = [v[0] for p in cut["parts"] if p["sheet"] == "stone" for v in p["verts"]
                  if abs(v[2] - TH / 2) < 1e-6 and 0.1 < v[1] < sill + 0.01]
            if xs:
                self.assertAlmostEqual(min(xs), -half, places=6)
                self.assertAlmostEqual(max(xs), half, places=6)

    def test_a_doorway_is_open_no_leaves_and_the_r6_rig_walks_it(self):
        cut = F.module(recipe("door"))
        tris = polys(cut)  # (every part: nothing of any sheet in the doorway)
        for x in (-2.0, -1.0, 0.0, 1.0, 2.0):
            for y in (0.2, 2.5, 5.0):
                self.assertFalse(through(tris, x, y), ("a leaf in the doorway", x, y))
        for x in (-1.0, 0.0, 1.0):  # (the rig: 2 wide, 5 tall, plus a hand over its head)
            self.assertFalse(through(tris, x, 6.0), x)
        self.assertEqual([p["sheet"] for p in cut["parts"]], ["stone"])

    def test_a_window_is_glazed_behind_its_iron(self):
        cut = F.module(recipe("window"))
        glass = polys(cut, "roof")
        self.assertTrue(through(glass, 0.8, 6.0))
        # the glass is seen from the street AND from the room
        self.assertIs(hit(glass, (0.8, 6.0, 9), (0.8, 6.0, 0)), True)
        self.assertIs(hit(glass, (0.8, 6.0, -9), (0.8, 6.0, 0)), True)
        # it stands inside the wall, set back from its face
        zs = [v[2] for p in cut["parts"] if p["sheet"] == "roof" for v in p["verts"]]
        self.assertGreater(min(zs), -TH / 2)
        self.assertLess(max(zs), TH / 2)

    def test_a_gap_that_is_not_the_module_s_width_or_has_no_head_room_is_refused(self):
        with self.assertRaises(ValueError):
            F.module(recipe("window", size=[4, 14, TH]))
        with self.assertRaises(ValueError):
            F.module(recipe("window", gap={"width": 3.4, "height": 4.0, "sill": 3.5}))
        with self.assertRaises(ValueError):
            F.module(dict(recipe("window"), module="turret"))


class WindingTest(unittest.TestCase):
    """Roblox draws ONE side of a face: every look below is from where a player stands"""

    def look(self, tris, eye, target, what):
        self.assertIs(hit(tris, eye, target), True, what)

    def test_walls_and_openings_from_the_street_the_room_and_inside_the_opening(self):
        for module in ("wall", "window", "windowb", "door", "oriel"):
            r = recipe(module)
            tris = polys(F.module(r))
            gap = r.get("gap") or {"width": 0, "sill": 14, "height": 14}
            top, sill, half = gap["height"], gap["sill"], gap["width"] / 2
            y = (top + 14) / 2 if module != "wall" else 7.0
            if module != "oriel":
                self.look(tris, (0.3, y, 9), (0.3, y, 0), (module, "from the street"))
            self.look(tris, (0.3, y, -9), (0.3, y, 0), (module, "from the room"))
            if module in ("window", "windowb", "door"):
                mid = sill + 0.3 * (top - sill)
                for sx in (-1, 1):
                    self.look(tris, (0.0, mid, 0.2), (sx * (half + 1), mid, 0.2), (module, "a jamb", sx))
                self.look(tris, (0.0, top - 3, 0.1), (0.0, top + 0.5, 0.1), (module, "the crown from below"))

    def test_the_hood_mould_and_the_oriel_from_the_street(self):
        tris = polys(F.module(recipe("door")))
        self.look(tris, (0.0, 12.0, 9), (0.0, 10.0, 0.5), "the hood over the door")
        self.look(tris, (0.0, 8.0, 3), (0.0, 9.2, 0.85), "the hood from under it")
        tris = polys(F.module(recipe("oriel")))
        self.look(tris, (0.0, 2.0, 9), (0.0, 2.0, 1.5), "the oriel's corbel from the street")
        self.look(tris, (1.55, 6.0, 9), (1.55, 6.0, 1.0), "the oriel's front pier")
        for sx in (-1, 1):
            self.look(tris, (sx * 8, 6.0, 1.6), (0.0, 6.0, 1.6), ("the oriel's cheek", sx))
        self.look(tris, (0.0, 20.0, 1.5), (0.0, 11.0, 1.5), "the oriel's roof from above")

    def test_the_roof_from_above_from_the_attic_and_its_gables(self):
        cut = F.module(recipe("roof"))
        tris = polys(cut)
        for x in (-7.0, -2.0, 3.0, 8.0):
            for z in (-10.0, 0.0, 9.0):
                self.look(tris, (x, 40, z), (x, 0.5, z), ("the slates from above", x, z))
                self.look(tris, (x, -3, z), (x, 16, z), ("the boards from the attic", x, z))
        for z, eye in ((12.0, 40.0), (-12.0, -40.0)):
            self.look(tris, (1.0, 4.0, eye), (1.0, 4.0, z), ("a gable from outside", z))
            self.look(tris, (1.0, 4.0, 0.0), (1.0, 4.0, z), ("a gable from the attic", z))
        ys = [v[1] for p in cut["parts"] for v in p["verts"]]
        self.assertAlmostEqual(min(ys), 0.0)
        ridge = [v for p in cut["parts"] if p["sheet"] == "roof" for v in p["verts"] if v[1] >= 14 - 1e-6]
        self.assertTrue(all(abs(v[0]) <= 0.41 for v in ridge))  # (the ridge along the depth, over x = 0)
        self.assertAlmostEqual(min(v[2] for v in ridge), -12.0)
        self.assertAlmostEqual(max(v[2] for v in ridge), 12.0)

    def test_a_band_a_chimney_and_a_quoin_from_every_side_a_player_sees(self):
        b = polys(F.module(recipe("band")))
        self.look(b, (1.0, 0.35, 9), (1.0, 0.35, 0.9), "the band from the street")
        self.look(b, (1.0, 5.0, 0.9), (1.0, 0.3, 0.9), "the band from above")
        c = polys(F.module(recipe("chimney")))
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            self.look(c, (dx * 9, 3.0, dz * 9), (0, 3.0, 0), ("the stack", dx, dz))
        self.look(c, (0.2, 12, 0.2), (0.2, 5, 0.2), "the cap from above")
        q = polys(F.module(recipe("quoin")))
        for y in (1.0, 3.0, 7.5, 13.0):
            self.look(q, (1.0, y, 9), (1.0, y, 0.0), ("its long-and-short face", y))
            self.look(q, (-9, y, -1.0), (0.0, y, -1.0), ("its return", y))


class QuoinTest(unittest.TestCase):
    def test_the_quoin_closes_the_corner_the_walls_leave_open_storey_high(self):
        q = polys(F.module(recipe("quoin")))
        # the walls' modules stop on their centre lines: the outer corner's 0.6 x 0.6 is covered from both faces, all
        # the way up (no slit between courses)
        for y in np.linspace(0.05, 13.95, 40):
            self.assertTrue(through(q, 0.3, y, z0=-0.3, z1=3), y)
            self.assertIs(hit(q, (-3, y, -0.3), (0.3, y, -0.3)), True, y)


class PngTest(unittest.TestCase):
    def test_the_sheets_are_written_without_pil_and_only_when_stale(self):
        img = (np.random.default_rng(3).random((6, 9, 3)) * 255).astype(np.uint8)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.png")
            T._png(p, img)
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n")
            try:
                from PIL import Image
            except ImportError:
                Image = None  # noqa: N806
            if Image is not None:
                self.assertTrue((np.array(Image.open(p)) == img).all())
                T._png(p, img[..., 0].copy())
                self.assertTrue((np.array(Image.open(p)) == img[..., 0]).all())
            for n in T.names():  # (fresh files: ensure() writes nothing)
                open(os.path.join(d, n), "wb").close()
            paths, written = T.ensure(d)
            self.assertFalse(written)
            self.assertEqual(len(paths), 6)


if __name__ == "__main__":
    unittest.main()
