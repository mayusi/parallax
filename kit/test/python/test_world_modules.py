"""kit/world/gothic_blender.py `_module_mesh` - the FACADE MODULES (kit/lib/worldfacade.luau; kind "gothic_module"):
what each one's geometry must be for the compiler to stretch it onto a wall. The builder is plain geometry, so it
runs here with a stand-in for Blender's `bpy` (only the export needs the real one). What a module LOOKS like is
not tested: that is seen in its preview and judged by the owner.
Run: python kit/test/python/run.py -k world_modules"""

import importlib.util
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(HERE, "..", "..", "world")
sys.path.insert(0, WORLD)
sys.modules.setdefault("bpy", types.ModuleType("bpy"))
_spec = importlib.util.spec_from_file_location("kit_gothic_modules", os.path.join(WORLD, "gothic_blender.py"))
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)

T = 1.2  # the wall's depth a module is modelled at
GAP_WINDOW = {"width": 4.0, "height": 10.5, "sill": 3.5}
GAP_DOOR = {"width": 5.0, "height": 8.5, "sill": 0.0}


def recipe(module, **more):
    r = {"name": "m", "kind": "gothic_module", "module": module, "floorHeight": 14, "thickness": T, "seed": 3}
    r["size"] = {"wall": [4, 14, T], "window": [4, 14, T], "windowb": [4, 14, T], "door": [5, 14, T],
                 "oriel": [4, 14, T + 2], "band": [8, 0.7, 0.6], "roof": [20, 14, 24], "chimney": [2.4, 7, 2.4]}[module]
    if module in ("window", "windowb", "oriel"):
        r["gap"] = dict(GAP_WINDOW)
    if module == "door":
        r["gap"] = dict(GAP_DOOR)
    r.update(more)
    return r


def polys(m):
    return [[tuple(float(c) for c in m.v[i]) for i in f] for f in m.f]


def bounds(m):
    xs, ys, zs = zip(*[tuple(float(c) for c in p) for p in m.v])
    return (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs))


def area(poly, drop):
    """a polygon's area seen along axis `drop` (0 x, 1 y, 2 z)"""
    a, b = [k for k in range(3) if k != drop]
    s = 0.0
    for i in range(len(poly)):
        p, q = poly[i], poly[(i + 1) % len(poly)]
        s += p[a] * q[b] - q[a] * p[b]
    return abs(s) / 2


def inside(poly, x, z):
    """is (x, z) inside the polygon seen from the front (along y)"""
    hit = False
    for i in range(len(poly)):
        (x1, _, z1), (x2, _, z2) = poly[i], poly[(i + 1) % len(poly)]
        if (z1 > z) != (z2 > z) and x < x1 + (z - z1) * (x2 - x1) / (z2 - z1):
            hit = not hit
    return hit


def wall_at(m, y, x, z, tol=1e-6):
    """does a face lying in the plane y = const cover (x, z)"""
    return any(all(abs(p[1] - y) < tol for p in poly) and inside(poly, x, z) for poly in polys(m))


def blocked(m, x, z, y0, y1):
    """does ANY face that faces the street or the room (lying in a plane of constant y between y0 and y1) cover
    (x, z) - what a look, or a walk, straight through the wall would meet"""
    for poly in polys(m):
        ys = [p[1] for p in poly]
        if max(ys) - min(ys) < 1e-6 and y0 - 1e-6 <= ys[0] <= y1 + 1e-6 and inside(poly, x, z):
            return True
    return False


def normal(poly):
    """a polygon's normal by its winding (Newell): the side Roblox draws"""
    nx = ny = nz = 0.0
    for i in range(len(poly)):
        (x1, y1, z1), (x2, y2, z2) = poly[i], poly[(i + 1) % len(poly)]
        nx += (y1 - y2) * (z1 + z2)
        ny += (z1 - z2) * (x1 + x2)
        nz += (x1 - x2) * (y1 + y2)
    return nx, ny, nz


def first_hit(m, eye, target):
    """the first face a look from `eye` toward `target` meets (as far as the target and a little past it):
    True = its drawn side is to the eye, False = its BACK is (in Roblox: nothing is seen there), None = no face"""
    d = [target[k] - eye[k] for k in range(3)]
    best = None
    for poly in polys(m):
        n = normal(poly)
        size = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5
        if size < 1e-12:
            continue
        den = sum(n[k] * d[k] for k in range(3))
        if abs(den) < 1e-12:
            continue
        t = sum(n[k] * (poly[0][k] - eye[k]) for k in range(3)) / den
        if t <= 1e-9 or t > 1.05:
            continue
        hit = [eye[k] + d[k] * t for k in range(3)]
        drop = max(range(3), key=lambda k: abs(n[k]))  # (seen along the polygon's own steepest axis)
        a, b = [k for k in range(3) if k != drop]
        inside_ = False
        for i in range(len(poly)):
            p1, p2 = poly[i], poly[(i + 1) % len(poly)]
            if (p1[b] > hit[b]) != (p2[b] > hit[b]) and hit[a] < p1[a] + (hit[b] - p1[b]) * (p2[a] - p1[a]) / (p2[b] - p1[b]):
                inside_ = not inside_
        # (two faces in one plane back to back - slates and the boards under them - are one surface seen from
        # either side: the one whose drawn side is to the eye is what is seen)
        if inside_ and (best is None or t < best[0] - 1e-9 or (abs(t - best[0]) <= 1e-9 and den < 0)):
            best = (t, den < 0)
    return None if best is None else best[1]


class WindingTest(unittest.TestCase):
    """Roblox draws ONE side of a face. A fresh reader found a window's head, an oriel's cheeks and its whole front
    drawn for the side nobody stands on - and no test that asked. Every look below is from where a player stands."""

    def look(self, m, eye, target, what):
        self.assertIs(first_hit(m, eye, target), True, what)

    def test_a_wall_and_every_opening_from_the_street_and_from_the_room(self):
        for module in ("wall", "window", "windowb", "door", "oriel"):
            r = recipe(module)
            m = G._module_mesh(r)
            gap = r.get("gap") or {"width": 0, "sill": 14, "height": 14}
            half, sill, top = gap["width"] / 2, gap["sill"], gap["height"]
            spots = [(0.6, (top + 14) / 2), (-1.2, (top + 14) / 2)] if module != "wall" else [(0.6, 3.0), (-1.2, 11.0)]
            if sill > 0.5 and module != "wall":
                spots.append((0.7, sill / 2))
            for x, z in spots:
                if module != "oriel" or z > top + 2.0 or z < 1.0:  # (in front of an oriel's wall stands its bay)
                    self.look(m, (x, -9, z), (x, 0, z), (module, "the wall from the street", x, z))
                self.look(m, (x, 9, z), (x, 0, z), (module, "the wall from the room", x, z))
            if module in ("window", "windowb", "door"):
                mid = sill + 0.3 * (top - sill)
                # the jambs, from inside the opening
                for sx in (-1, 1):
                    self.look(m, (sx * (half - 0.6), 0, mid), (sx * (half + 1), 0, mid), (module, "a jamb", sx))
                # the head, looked up at from the street and from the room
                for y in (-0.3, 0.3):
                    for x in (0.5, -1.1):
                        self.look(m, (x, y * 4, top - 3), (x, y, top + 0.6), (module, "the head from below", x, y))
                if sill > 0.5:
                    self.look(m, (0.7, 0, sill + 2), (0.7, 0, sill - 0.5), (module, "the sill from above"))

    def test_nothing_is_a_face_of_no_size(self):
        for module in ("wall", "window", "windowb", "door", "oriel", "band", "roof", "chimney"):
            for poly in polys(G._module_mesh(recipe(module))):
                n = normal(poly)
                self.assertGreater(n[0] ** 2 + n[1] ** 2 + n[2] ** 2, 1e-10, module)

    def test_an_oriel_from_the_street_from_under_it_and_from_the_room(self):
        m = G._module_mesh(recipe("oriel"))
        out = -(T / 2 + 2)
        mid = 6.5
        # from the street: its piers, both cheeks, its corbel from below and from each side, its little roof
        for x in (-1.8, 1.8):
            self.look(m, (x, -9, mid), (x, out + 0.1, mid), ("a pier from the street", x))
        for sx in (-1, 1):
            self.look(m, (sx * 8, -1.5, mid), (sx * 1.5, -1.5, mid), ("a cheek from outside", sx))
            self.look(m, (sx * 8, -0.9, 2.6), (0, -0.9, 2.6), ("the corbel's side", sx))
            self.look(m, (sx * 8, -0.9, 11.6), (0, -0.9, 11.6), ("the little roof's side", sx))
        self.look(m, (0.5, -3, 0.2), (0.5, -1.2, 3.5), ("the corbel from below"))
        self.look(m, (0.5, -4, 16), (0.5, -1.5, 11.0), ("its roof from above"))
        # from the room: the piers and the strips under and over the light are plaster, not a hole to the street
        for x in (-1.8, 1.8):
            self.look(m, (0, 4, 4.5), (x, out + 0.1, mid), ("a pier from the room", x))
        self.look(m, (0, 4, 4.5), (0.5, out + 0.1, 3.2), "the strip under the light from the room")
        self.look(m, (0, 4, 6.0), (0.5, out + 0.1, 10.8), "the strip over the light from the room")
        # ... the bay's floor from above (the room) and from below (the street), its ceiling from the room
        self.look(m, (0.4, -1.5, 6), (0.4, -1.5, 2.5), "the bay's floor from the room")
        self.look(m, (0.4, -1.5, 3.5), (0.4, -1.5, 11.5), "the bay's ceiling from the room")
        for sx in (-1, 1):
            self.look(m, (0, -1.5, mid), (sx * 3, -1.5, mid), ("a cheek from inside the bay", sx))
        # ... and the light itself is open
        self.assertIsNone(first_hit(m, (0.8, 4, 5.0), (0.8, -9, 5.0)))

    def test_a_roof_from_above_from_the_top_storey_and_from_the_street(self):
        r = recipe("roof")
        m = G._module_mesh(r)
        for x in (-7.0, -2.0, 3.0, 8.0):
            for y in (-10.0, 0.0, 9.0):
                self.look(m, (x, y, 40), (x, y, 0.5), ("the slates from above", x, y))
                self.look(m, (x, y, -3), (x, y, 16), ("the roof from below (a gable house has no ceiling)", x, y))
        for y, eye in ((-12.0, -40.0), (12.0, 40.0)):
            self.look(m, (2.0, eye, 4.0), (2.0, y, 4.0), ("a gable from outside", y))
            self.look(m, (2.0, 0.0, 4.0), (2.0, y, 4.0), ("a gable from inside the roof", y))
        # the ridge roll has no end in the gable's own plane (two faces in one plane flicker)
        for poly in polys(m):
            if all(abs(q[1] - poly[0][1]) < 1e-6 for q in poly) and abs(abs(poly[0][1]) - 12.0) < 1e-6:
                self.assertLess(min(q[2] for q in poly), 13.99)
                self.assertGreater(max(abs(q[0]) for q in poly), 0.26)

    def test_a_chimney_and_a_band_from_every_side_a_player_sees(self):
        c = G._module_mesh(recipe("chimney"))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            self.look(c, (dx * 9, dy * 9, 3.0), (0, 0, 3.0), ("the stack", dx, dy))
            self.look(c, (dx * 9, dy * 9, 6.7), (0, 0, 6.7), ("the cap", dx, dy))
        self.look(c, (0.3, 0.2, 12), (0.3, 0.2, 5), "the cap from above")
        self.look(c, (0.3, 0.2, -4), (0.3, 0.2, 3), "the stack from below (its foot stands over the lower slates)")
        b = G._module_mesh(recipe("band"))
        self.look(b, (1.0, -6, 0.35), (1.0, 0, 0.35), "the band from the street")
        self.look(b, (1.0, -0.9, 4), (1.0, -0.9, 0.2), "the band from above")
        self.look(b, (1.0, -0.9, -4), (1.0, -0.9, 0.5), "the band from below")


class ModuleBoxTest(unittest.TestCase):
    def test_every_module_stands_in_its_recipes_box_its_origin_at_the_foot_of_its_middle(self):
        # how far each may stand PROUD of its box at the front (a hood mould, a sill, a label) or the sides
        proud = {"wall": (0, 0), "window": (0.2, 0), "windowb": (0.32, 0), "door": (0.2, 0), "oriel": (0.25, 0.16),
                 "band": (0, 0), "roof": (0, 0), "chimney": (0, 0)}
        for module, (front, side) in proud.items():
            r = recipe(module)
            m = G._module_mesh(r)
            w, h, d = r["size"]
            (x0, x1), (y0, y1), (z0, z1) = bounds(m)
            self.assertGreaterEqual(x0, -w / 2 - side - 1e-6, module)
            self.assertLessEqual(x1, w / 2 + side + 1e-6, module)
            self.assertAlmostEqual(x0 + x1, 0, places=6, msg=module)  # (its middle on the origin)
            self.assertGreaterEqual(z0, -1e-6, module)
            self.assertLessEqual(z1, h + 1e-6, module)
            if module in ("wall", "window", "windowb", "door"):
                # through the wall: from its front face (and what stands proud of it) to its back face, no further
                self.assertAlmostEqual(y1, T / 2, places=6, msg=module)
                self.assertGreaterEqual(y0, -T / 2 - front - 1e-6, module)
                self.assertLessEqual(y0, -T / 2 + 1e-6, module)
            if module == "oriel":
                self.assertAlmostEqual(y1, T / 2, places=6)
                self.assertLess(y0, -T / 2 - 1.9)  # (it stands out of the wall)
                self.assertGreaterEqual(y0, -T / 2 - 2 - front - 1e-6)
            self.assertLessEqual(len(m.f), 300, module)  # (a module is a few hundred faces at most)

    def test_what_is_no_module_is_refused(self):
        with self.assertRaises(ValueError):
            G._module_mesh(dict(recipe("wall"), module="turret"))


class WallModuleTest(unittest.TestCase):
    def test_a_wall_panel_is_whole_on_both_faces_and_nothing_else(self):
        for size in ([4, 14, T], [4, 15, T], [4, 12.5, 1.0]):
            r = recipe("wall", size=size)
            m = G._module_mesh(r)
            w, h, d = size
            front = sum(area(p, 1) for p in polys(m) if all(abs(q[1] + d / 2) < 1e-6 for q in p))
            back = sum(area(p, 1) for p in polys(m) if all(abs(q[1] - d / 2) < 1e-6 for q in p))
            self.assertAlmostEqual(front, w * h, places=5)
            self.assertAlmostEqual(back, w * h, places=5)
            # every face is on one of the two: no sides (a neighbour stands against it), no top
            for p in polys(m):
                self.assertTrue(all(abs(abs(q[1]) - d / 2) < 1e-6 for q in p))


class OpeningTest(unittest.TestCase):
    def test_the_opening_the_building_cuts_is_open_and_the_wall_round_it_is_closed(self):
        for module in ("window", "windowb", "door"):
            r = recipe(module)
            m = G._module_mesh(r)
            gap = r["gap"]
            half, sill, top = gap["width"] / 2, gap["sill"], gap["height"]
            # THROUGH the opening, clear of the mullion and the transom: nothing between the street and the room
            for fx in (-0.55, 0.55):
                for fz in (0.12, 0.3, 0.85):
                    x, z = fx * half, sill + fz * (top - sill) * (0.75 if module != "windowb" else 1.0)
                    self.assertFalse(blocked(m, x, z, -T / 2 - 0.5, T / 2), (module, x, z))
            # under the sill and over the head the wall is whole, front and back
            for x in (-half + 0.2, 0.0, half - 0.2):
                if sill > 0:
                    self.assertTrue(wall_at(m, -T / 2, x, sill / 2), (module, "under the sill"))
                    self.assertTrue(wall_at(m, T / 2, x, sill / 2), (module, "under the sill, inside"))
                self.assertTrue(wall_at(m, -T / 2, x, (top + 14) / 2), (module, "over the head"))
                self.assertTrue(wall_at(m, T / 2, x, (top + 14) / 2), (module, "over the head, inside"))

    def test_a_pointed_head_closes_the_square_corners_of_the_gap(self):
        # the building's gap is a rectangle; a pointed opening leaves its two upper corners as wall (front and back),
        # and its crown at the gap's own top
        for module in ("window", "door"):
            r = recipe(module)
            m = G._module_mesh(r)
            half, top = r["gap"]["width"] / 2, r["gap"]["height"]
            for sx in (-1, 1):
                self.assertTrue(wall_at(m, -T / 2, sx * (half - 0.15), top - 0.15), module)
                self.assertTrue(wall_at(m, T / 2, sx * (half - 0.15), top - 0.15), module)
            self.assertFalse(blocked(m, 0.3, top - 0.6, -T / 2 - 0.01, T / 2), module)  # (just under the crown: open)
            # the square-headed one is open into those corners
        sq = G._module_mesh(recipe("windowb"))
        half, top = GAP_WINDOW["width"] / 2, GAP_WINDOW["height"]
        self.assertFalse(wall_at(sq, -T / 2, half - 0.15, top - 0.15))

    def test_a_window_has_its_mullion_a_door_has_none(self):
        for module, want in (("window", True), ("windowb", True), ("door", False)):
            r = recipe(module)
            m = G._module_mesh(r)
            sill, top = r["gap"]["sill"], r["gap"]["height"]
            z = sill + 0.25 * (top - sill)
            self.assertEqual(blocked(m, 0.0, z, -T / 2, T / 2), want, module)

    def test_an_opening_cut_for_other_numbers_follows_them(self):
        gap = {"width": 6.0, "height": 9.0, "sill": 2.0}
        r = recipe("window", size=[6, 12, T], gap=gap)
        m = G._module_mesh(r)
        self.assertFalse(blocked(m, 1.5, 4.0, -T / 2 - 0.5, T / 2))
        self.assertTrue(wall_at(m, -T / 2, 1.5, 1.0))
        self.assertTrue(wall_at(m, -T / 2, 1.5, 10.5))
        (_, _), (_, _), (_, z1) = bounds(m)
        self.assertAlmostEqual(z1, 12.0, places=6)


class OrielTest(unittest.TestCase):
    def test_the_bay_stands_out_over_the_wall_s_own_opening_with_a_light_in_its_front(self):
        r = recipe("oriel")
        m = G._module_mesh(r)
        sill, top = GAP_WINDOW["sill"], GAP_WINDOW["height"]
        out = -(T / 2 + 2)  # (its front face)
        mid = sill + 0.3 * (top - sill)
        # the wall's own opening behind it is clear (you look out through the bay) ...
        self.assertFalse(blocked(m, 1.0, mid, -T / 2, T / 2))
        # ... the bay's front has its piers and, between them, a light
        self.assertTrue(wall_at(m, out, 1.9, mid))
        self.assertTrue(wall_at(m, out, -1.9, mid))
        self.assertFalse(wall_at(m, out, 0.8, mid))
        # its cheeks close it at the sides (a face in a plane of constant x at the module's edge)
        cheeks = [p for p in polys(m) if max(q[0] for q in p) - min(q[0] for q in p) < 1e-6 and abs(abs(p[0][0]) - 2.0) < 1e-6
                  and min(q[1] for q in p) < -T / 2 - 1.5]
        self.assertGreaterEqual(len(cheeks), 2)


class RoofTest(unittest.TestCase):
    def test_the_slopes_cover_the_whole_box_from_the_eaves_to_a_ridge_along_its_depth(self):
        r = recipe("roof")
        m = G._module_mesh(r)
        w, h, d = r["size"]
        (x0, x1), (y0, y1), (z0, z1) = bounds(m)
        self.assertAlmostEqual(x0, -w / 2)
        self.assertAlmostEqual(x1, w / 2)
        self.assertAlmostEqual(y0, -d / 2)
        self.assertAlmostEqual(y1, d / 2)
        self.assertAlmostEqual(z0, 0)
        self.assertAlmostEqual(z1, h)
        # seen from above, the slates (sloping faces that look up) cover w x d once; so does the underside (sloping
        # faces that look down)
        up = down = 0.0
        for p in polys(m):
            xs, zs = [q[0] for q in p], [q[2] for q in p]
            if max(zs) - min(zs) > 1e-6 and max(xs) - min(xs) > 1e-6 and max(q[1] for q in p) - min(q[1] for q in p) > 1e-6:
                if normal(p)[2] > 0:
                    up += area(p, 2)
                else:
                    down += area(p, 2)
        self.assertAlmostEqual(up, w * d, places=4)
        self.assertGreater(down, w * d * 0.95)  # (a fifth of a stud under the slates: a hair narrower)
        self.assertLessEqual(down, w * d + 1e-6)
        # ... and no face lies in another's plane facing the other way (they flicker where both sides are drawn)
        faces = [(normal(p), p) for p in polys(m)]
        for i, (na, pa) in enumerate(faces):
            la = sum(c * c for c in na) ** 0.5
            for nb, pb in faces[i + 1:]:
                lb = sum(c * c for c in nb) ** 0.5
                if sum(x * y for x, y in zip(na, nb)) / (la * lb) < -0.999:
                    apart = abs(sum(na[k] * (pb[0][k] - pa[0][k]) for k in range(3))) / la
                    cx = [sum(q[k] for q in pa) / len(pa) - sum(q[k] for q in pb) / len(pb) for k in range(3)]
                    near_ = sum(c * c for c in cx) ** 0.5 < 6.0
                    self.assertTrue(apart > 0.04 or not near_, (pa, pb))
        # the ridge runs along the depth: the highest points are on x = 0, from the front to the back
        top = [q for p in polys(m) for q in p if abs(q[2] - h) < 1e-6]
        self.assertTrue(all(abs(q[0]) <= 0.25 + 1e-6 for q in top))
        self.assertAlmostEqual(min(q[1] for q in top), -d / 2)
        self.assertAlmostEqual(max(q[1] for q in top), d / 2)
        # a gable closes each end
        for y in (-d / 2, d / 2):
            gable = sum(area(p, 1) for p in polys(m) if all(abs(q[1] - y) < 1e-6 for q in p) and len(p) == 4
                        and max(q[2] for q in p) - min(q[2] for q in p) > 1.0)
            # (the street's face, stepped: within a fifth of the triangle; the attic's stands a hair inside it)
            self.assertAlmostEqual(gable, w * h / 2, delta=w * h / 2 * 0.2)


class SmallModulesTest(unittest.TestCase):
    def test_a_band_stands_proud_of_the_wall_s_face_and_a_chimney_is_a_stack_with_a_cap(self):
        r = recipe("band")
        m = G._module_mesh(r)
        (x0, x1), (y0, y1), (z0, z1) = bounds(m)
        self.assertAlmostEqual(x1 - x0, 8.0)
        self.assertAlmostEqual(y1, -T / 2)  # (its back on the wall's front face)
        self.assertAlmostEqual(y0, -T / 2 - 0.6)
        self.assertAlmostEqual(z1 - z0, 0.7)
        c = G._module_mesh(recipe("chimney"))
        (x0, x1), (y0, y1), (z0, z1) = bounds(c)
        self.assertAlmostEqual(x1 - x0, 2.4)
        self.assertAlmostEqual(y1 - y0, 2.4)
        self.assertAlmostEqual(z1, 7.0)
        # the cap is wider than the stack under it
        stack = [q for p in polys(c) for q in p if q[2] < 1.0]
        self.assertLess(max(q[0] for q in stack), 1.2 - 0.1)


if __name__ == "__main__":
    unittest.main()
