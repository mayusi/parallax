"""kit/world/worldcheck.py - a lane or a run wall that runs on NEITHER axis (a turned house, a bent street) is
measured on the parts themselves. Before 2026-11-13 the lane's width was marched along one world axis in the voxels:
a lane typed at 45 degrees read 1.4 times too wide, so a 6-stud lane passed the r6 sheet's 8.
Run: python kit/test/python/run.py -k world_oblique"""

import importlib.util
import math
import os
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_world_check_oblique", os.path.join(HERE, "..", "..", "world", "worldcheck.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def yaw(deg):
    """a part's rotation turned `deg` about the vertical, as the compiler writes it (CFrame.Angles(0, yaw, 0))"""
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def along(deg, d):
    """`d` studs along a part's own +X once turned: (x, z)"""
    return d * math.cos(math.radians(deg)), -d * math.sin(math.radians(deg))


def across(deg, d):
    """`d` studs along a part's own +Z once turned: (x, z)"""
    return d * math.sin(math.radians(deg)), d * math.cos(math.radians(deg))


def part(name, x, y, z, size, deg=0.0, **more):
    p = {"name": name, "pos": [x, y, z], "size": list(size), "rot": yaw(deg) if deg else I3, "collide": True, "class": "Part"}
    p.update(more)
    return p


def lane(deg, width, length=64.0, height=12.0, thick=1.0, kind="alley", cx=0.0, cz=0.0):
    """two walls `width` apart (face to face) with a lane between them running at `deg`, and its claim"""
    walls = []
    for side in (-1, 1):
        ox, oz = across(deg, side * (width / 2 + thick / 2))
        walls.append(part(f"Wall{side}", cx + ox, height / 2, cz + oz, (length, height, thick), deg))
    ax, az = along(deg, -length * 0.4)
    bx, bz = along(deg, length * 0.4)
    fit = {"kind": kind, "name": f"Lane {deg}", "pos": [cx, 0, cz], "from": [cx + ax, cz + az], "to": [cx + bx, cz + bz]}
    return walls, fit


def checked(parts, fits, spawn=None):
    """the scale check on a small world, its voxels filled the way the whole check fills them (kit world check's own
    run is proved end to end by kit selftest: kit/selftest/world/_selftest_turned_lane*.json)"""
    ps = list(parts)
    ps.append(part("Ground", 0, -1, 0, (150, 2, 150)))
    w = {"name": "T", "scale": "r6", "parts": ps, "fits": fits}
    g = C.Grid([-76, -3, -76], [76, 20, 76], 1.0)
    for p in ps:
        if C.is_solid(p):
            g.fill_part(p)
    errors, _ = C.scale_check(w, g)
    return [e for e in errors if e.startswith("scale:")]


def span_of(parts, x, z, deg, g=None, grounds=(), terrain_solids=()):
    ux, uz = across(deg, 1.0)
    return C.Lane(parts, grounds, terrain_solids, g).span(x, 0.0, z, ux, uz)


def grid_of(parts, extra=()):
    """the voxels the whole check would make of these parts (and of `extra`: things only the voxels know)"""
    g = C.Grid([-76, -3, -76], [76, 20, 76], 1.0)
    for p in list(parts) + list(extra):
        if C.is_solid(p):
            g.fill_part(p)
    return g


def bank(deg, near, far, top=6.0, half=70, step=1.0):
    """LAND: a ground op whose height is `top` where a point lies between `near` and `far` studs across a line
    through the origin at `deg` (a bank along one side of a lane), 0 elsewhere"""
    n = int(2 * half / step) + 1
    ux, uz = across(deg, 1.0)
    heights = []
    for i in range(n):
        for j in range(n):
            x, z = -half + i * step, -half + j * step
            d = x * ux + z * uz
            heights.append(top if near <= d <= far else 0.0)
    return {"heights": heights, "nx": n, "nz": n, "x0": -half, "z0": -half, "step": step}


def scanned(deg, at, size=(2.0, 6.0, 2.0)):
    """a scanned mesh's placeholder with its own point cloud (what mesh_hulls gives the check): a block of points
    `at` studs across the line"""
    ox, oz = across(deg, at)
    xs = np.arange(-size[0] / 2, size[0] / 2 + 1e-9, 0.25)
    ys = np.arange(0.0, size[1] + 1e-9, 0.25)
    pts = np.array([[ox + a, y, oz + b] for a in xs for y in ys for b in xs], float)
    return {"name": "KitMesh", "mesh": "rock", "meshCollide": True, "collide": False, "class": "Part", "pos": [ox, size[1] / 2, oz],
            "size": list(size), "rot": I3, "_points": pts}


class ExactSpanTest(unittest.TestCase):
    def test_a_lane_at_any_angle_measures_its_own_width(self):
        for deg in (5, 17.5, 30, 45, 60, 77, 110, 200, -35):
            for width in (4.0, 6.0, 8.0, 12.5, 32.0):
                walls, _ = lane(deg, width)
                got = span_of(walls, 0.0, 0.0, deg)
                self.assertIsNotNone(got, (deg, width))
                self.assertAlmostEqual(got, width, delta=0.01, msg=(deg, width))
                # ... anywhere along it, not only at its middle
                x, z = along(deg, 25.0)
                self.assertAlmostEqual(span_of(walls, x, z, deg), width, delta=0.01, msg=(deg, width))

    def test_what_stands_in_the_lane_narrows_it_by_its_real_shape(self):
        walls, _ = lane(30, 12.0)
        # a post 2 wide against one wall: 12 -> 10 where it stands, 12 beside it
        ox, oz = across(30, 5.0)
        post = part("Post", ox, 3, oz, (2, 6, 2), 30)
        self.assertAlmostEqual(span_of(walls + [post], 0, 0, 30), 10.0, delta=0.01)
        x, z = along(30, 10.0)
        self.assertAlmostEqual(span_of(walls + [post], x, z, 30), 12.0, delta=0.01)
        # a barrel (a ball 4 across) in the lane, centred 3 off the line: its side reaches 1 stud from the line
        bx, bz = across(30, 3.0)
        ball = part("Barrel", bx, 3, bz, (4, 4, 4), 0, shape="Ball")
        self.assertAlmostEqual(span_of(walls + [ball], 0, 0, 30), 6.0 + 1.0, delta=0.02)
        # something overhead (above the body band) or underfoot does not narrow it
        beam = part("Beam", 0, 9, 0, (30, 1, 30), 30)
        self.assertAlmostEqual(span_of(walls + [beam], 0, 0, 30), 12.0, delta=0.01)
        # ... and what does not collide (a banner, a pane) is not in the way at all
        banner = part("Banner", ox, 3, oz, (2, 6, 2), 30, collide=False)
        self.assertAlmostEqual(span_of(walls + [banner], 0, 0, 30), 12.0, delta=0.01)

    def test_a_side_with_nothing_on_it_is_open_not_wide(self):
        walls, _ = lane(40, 10.0)
        self.assertIsNone(span_of(walls[:1], 0, 0, 40))
        self.assertIsNone(span_of([], 0, 0, 40))

    def test_a_wall_thinner_than_the_march_is_still_met(self):
        # (the march is 0.25: a 0.3-stud screen across the lane must stop it)
        walls, _ = lane(25, 20.0)
        ox, oz = across(25, 4.0)
        screen = part("Screen", ox, 3, oz, (10, 6, 0.3), 25)
        self.assertAlmostEqual(span_of(walls + [screen], 0, 0, 25), 10.0 + 4.0 - 0.15, delta=0.01)

    def test_a_low_thing_between_any_two_heights_is_met(self):
        """a fresh reader, 2026-11-13: the first version looked at three heights and walked through a bench that lay
        between two of them - the slanted lane passed where the same lane on an axis failed"""
        for deg in (0.001, 30, 45):
            walls, _ = lane(deg, 9.0)
            for low, high in ((1.6, 2.6), (1.05, 1.2), (4.7, 4.95), (2.9, 3.1)):
                ox, oz = across(deg, 3.75)  # 1.5 studs proud of the wall: the lane is 7.5 there
                bench = part("Bench", ox, (low + high) / 2, oz, (6, high - low, 1.5), deg)
                self.assertAlmostEqual(span_of(walls + [bench], 0, 0, deg), 7.5, delta=0.01, msg=(deg, low, high))
            # under the band (a kerb) and over it (a lintel) are not in a body's way
            for low, high in ((0.0, 0.99), (5.01, 6.0)):
                ox, oz = across(deg, 3.75)
                slab = part("Slab", ox, (low + high) / 2, oz, (6, high - low, 1.5), deg)
                self.assertAlmostEqual(span_of(walls + [slab], 0, 0, deg), 9.0, delta=0.01, msg=(deg, low, high))

    def test_a_tilted_box_a_wedge_and_a_cylinder_are_met_by_their_own_shape(self):
        walls, _ = lane(30, 14.0)
        ox, oz = across(30, 4.0)
        # a pipe lying along the lane (a cylinder along its own X), 1 stud in radius, its middle 4 off the line
        pipe = part("Pipe", ox, 2.0, oz, (20, 2, 2), 30, shape="Cylinder")
        self.assertAlmostEqual(span_of(walls + [pipe], 0, 0, 30), 7.0 + 3.0, delta=0.02)
        # the terrain's own ball, 3 in radius, centred 6 off the line at body height
        bx, bz = across(30, 6.0)
        ball = [{"kind": "ball", "spec": {"center": [bx, 3.0, bz], "radius": 3.0}}]
        self.assertAlmostEqual(span_of(walls, 0, 0, 30, terrain_solids=ball), 7.0 + 3.0, delta=0.02)

    def test_the_land_narrows_a_lane_where_it_stands_in_the_bodys_way(self):
        # a bank of land along one wall, 2 studs proud of it and 6 high: the 10-stud lane is 8 there
        for deg in (30, 45):
            walls, _ = lane(deg, 10.0, length=40.0)
            got = span_of(walls, 0, 0, deg, grounds=[bank(deg, 3.0, 8.0)])
            # (the land's edge is a slope between two of its 1-stud height posts: it is "in the way" where it
            # passes 1.5 up, somewhere in that last stud)
            self.assertGreater(got, 7.0, deg)
            self.assertLess(got, 8.3, deg)
        # land lower than a body's knee (1.4 up) is walked over, not round
        walls, _ = lane(30, 10.0, length=40.0)
        self.assertAlmostEqual(span_of(walls, 0, 0, 30, grounds=[bank(30, 3.0, 8.0, top=1.4)]), 10.0, delta=0.01)

    def test_a_scanned_mesh_is_met_by_its_voxels_narrow_by_a_cell_at_most_never_wide(self):
        for deg in (30, 45, 60):
            walls, _ = lane(deg, 16.0)
            rock = scanned(deg, 5.0)  # its near side 4 off the line, give or take its own turn against the lane
            g = grid_of(walls + [rock])
            got = span_of(walls + [rock], 0, 0, deg, g)
            self.assertLessEqual(got, 8.0 + 4.0 + 0.01, deg)
            self.assertGreaterEqual(got, 8.0 + 4.0 - 2.2, deg)  # (its box turned 45 degrees pokes 0.4 nearer; then a cell)
            # with no voxels given, a mesh has no shape to meet: the lane is as wide as its walls
            self.assertAlmostEqual(span_of(walls + [rock], 0, 0, deg), 16.0, delta=0.01)


class ClaimTest(unittest.TestCase):
    def test_a_slanted_lane_too_narrow_fails_and_one_wide_enough_passes(self):
        for deg in (30, 45, 60):
            walls, fit = lane(deg, 6.0)
            errs = checked(walls, [fit])
            self.assertEqual(len(errs), 1, (deg, errs))
            self.assertIn("w 6.0 (wants 8.0..)", errs[0])
            walls, fit = lane(deg, 8.0)
            self.assertEqual(checked(walls, [fit]), [], deg)
        walls, fit = lane(45, 29.0, length=80, kind="street")
        errs = checked(walls, [fit])
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("w 29.0 (wants 30.0..)", errs[0])

    def test_the_old_march_would_have_passed_the_45_degree_lane(self):
        """what this replaced: the march along one world axis reads a 6-stud lane at 45 degrees as about 8.5"""
        walls, _ = lane(45, 6.0)
        g = grid_of(walls)
        self.assertGreater(C._span(g, 0.0, 0.0, 0.0, 2), 7.4)
        self.assertAlmostEqual(span_of(walls, 0, 0, 45, g), 6.0, delta=0.01)

    def test_a_lane_gets_the_same_verdict_slanted_as_on_an_axis(self):
        """a fresh reader's probes, 2026-11-13: a bench 1.5 proud in a 9-stud lane (really 7.5) failed on an axis and
        passed at 45 degrees; the reverse for a lane that fits. One verdict now, whatever the angle."""
        for deg in (0, 30, 45, 90):
            for width, proud, fits in ((9.0, 1.5, False), (10.0, 2.0, True), (12.0, 1.0, True), (8.5, 1.0, False)):
                walls, fit = lane(deg, width)
                ox, oz = across(deg, width / 2 - proud / 2)
                bench = part("Bench", ox, 2.1, oz, (64, 1.0, proud), deg)
                errs = checked(walls + [bench], [fit])
                self.assertEqual(errs == [], fits, (deg, width, proud, errs))

    def test_a_lane_on_an_axis_is_measured_as_it_always_was(self):
        calls = []
        real = C.Lane.span
        C.Lane.span = lambda *a, **k: calls.append(1) or real(*a, **k)
        try:
            for deg in (0, 90, 180):
                walls, fit = lane(deg, 6.0)
                errs = checked(walls, [fit])
                self.assertEqual(len(errs), 1, (deg, errs))
                self.assertIn("w 6.0 (wants 8.0..)", errs[0])
        finally:
            C.Lane.span = real
        self.assertEqual(calls, [])
        # ... and a slanted one is measured across itself (the probe above can see a call)
        C.Lane.span = lambda *a, **k: calls.append(1) or real(*a, **k)
        try:
            walls, fit = lane(30, 6.0)
            checked(walls, [fit])
        finally:
            C.Lane.span = real
        self.assertGreater(len(calls), 0)

    def test_a_thin_post_anywhere_along_a_lane_is_seen(self):
        """card mkmc: a street was sampled every 8 studs along it, so a post between two samples stood unseen and
        a town passed or failed by where its lamp posts fell. Every stud of the line is read now."""
        for deg in (0, 30, 90, 135):
            for at in (-21.3, -12.3, -3.9, 5.2, 14.6, 22.75):  # (none of them on one of the old samples)
                walls, fit = lane(deg, 9.5)
                self.assertEqual(checked(walls, [fit]), [], deg)
                ax, az = along(deg, at)
                ox, oz = across(deg, -2.5)  # (half a stud thick, its far face 2.5 studs from the wall: 7 left)
                post = part("Post", ax + ox, 6, az + oz, (0.5, 12, 0.5), deg)
                errs = checked(walls + [post], [fit])
                self.assertEqual(len(errs), 1, (deg, at, errs))
                self.assertIn("w 7.0 (wants 8.0..)", errs[0])
        # a slanted lane is read by lines: four a stud, so a rail a third of a stud thick stands on one wherever it is
        for deg in (30, 135):
            for at in (-21.3, -12.42, -3.9, 5.07, 14.6, 22.75):
                walls, fit = lane(deg, 9.5)
                ax, az = along(deg, at)
                ox, oz = across(deg, -2.4)
                rail = part("Rail", ax + ox, 6, az + oz, (0.3, 12, 0.3), deg)
                errs = checked(walls + [rail], [fit])
                self.assertEqual(len(errs), 1, (deg, at, errs))
                self.assertIn("w 7.0 (wants 8.0..)", errs[0])

    def test_two_posts_face_to_face_take_a_main_street_under_30_and_one_alone_does_not(self):
        for deg in (0, 30, 90):
            for at in (-27.4, 11.7):
                walls, fit = lane(deg, 32.0, length=80, kind="street")
                posts = []
                for side in (-1, 1):
                    ax, az = along(deg, at)
                    ox, oz = across(deg, side * (16 - 1.5))  # (a lamp: a stud and a half out from the house)
                    posts.append(part(f"Post{side}", ax + ox, 6, az + oz, (0.5, 12, 0.5), deg))
                self.assertEqual(checked(walls + posts[:1], [fit]), [], (deg, at))
                errs = checked(walls + posts, [fit])
                self.assertEqual(len(errs), 1, (deg, at, errs))
                self.assertIn("(wants 30.0..)", errs[0])
                self.assertRegex(errs[0], r"w 28(\.5|\.0)? ")

    def test_a_slanted_lane_open_on_a_side_is_said_to_have_no_walls(self):
        walls, fit = lane(35, 10.0)
        errs = checked(walls[:1], [fit])
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("no walls either side", errs[0])


class TurnedRunWallTest(unittest.TestCase):
    def wall(self, deg):
        return part("Run", 0, 7, 0, (60, 14, 2), deg)

    def claim(self, deg):
        return {"kind": "runwall", "name": "Run", "size": [60, 14, 2], "pos": [0, 7, 0], "yaw": deg}

    def test_a_turned_run_wall_with_a_clear_face_is_flush(self):
        for deg in (0, 30, 45, 90, 135):
            self.assertEqual(checked([self.wall(deg)], [self.claim(deg)]), [], deg)

    def test_a_turned_run_wall_with_something_proud_on_both_faces_is_not(self):
        for deg in (0, 30, 45, 135):
            proud = []
            for side in (-1, 1):
                ox, oz = across(deg, side * 1.4)
                ax, az = along(deg, 10.0 * side)
                proud.append(part(f"Pilaster{side}", ox + ax, 7, oz + az, (2, 10, 1.2), deg))
            errs = checked([self.wall(deg)] + proud, [self.claim(deg)])
            self.assertEqual(len(errs), 1, (deg, errs))
            self.assertIn("not flush", errs[0])
            # one face clear is enough: a run needs one
            self.assertEqual(checked([self.wall(deg)] + proud[:1], [self.claim(deg)]), [], deg)

    def test_land_proud_of_both_faces_of_a_turned_run_wall_is_seen(self):
        """(a fresh reader: the first version asked only the parts, so land or a scanned mesh against a turned wall
        went unseen where a wall on an axis would have been refused)"""
        w = {"name": "T", "scale": "r6", "parts": [self.wall(45)], "fits": [self.claim(45)],
             "terrain": {"ground": [bank(45, -2.6, 2.6, top=9.0)], "solids": []}}
        g = grid_of(w["parts"])
        g.fill_ground(w["terrain"]["ground"][0])
        errs = [e for e in C.scale_check(w, g)[0] if e.startswith("scale:")]
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("not flush", errs[0])
        w["terrain"]["ground"] = [bank(45, -2.6, 2.6, top=1.0)]  # land at the wall's foot only: its face is clear
        g = grid_of(w["parts"])
        g.fill_ground(w["terrain"]["ground"][0])
        self.assertEqual([e for e in C.scale_check(w, g)[0] if e.startswith("scale:")], [])

    def test_the_claim_without_its_yaw_looks_along_the_axes_and_calls_a_clean_wall_proud(self):
        """why the compiler writes the yaw: the same clean turned wall, claimed with no yaw, is looked for along the
        axes - the search runs through the wall itself and calls it proud of its own face"""
        claim = self.claim(45)
        self.assertEqual(checked([self.wall(45)], [claim]), [])
        del claim["yaw"]
        errs = checked([self.wall(45)], [claim])
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("not flush", errs[0])


class SlopedStreetTest(unittest.TestCase):
    """a street on sloping ground (a town on a slope) says its floor's height at each end: "ground" """

    RISE = 0.06  # studs up in every stud along x
    BASE = 4.0  # (the whole hill stands over the helper's level ground at 0)

    def hill(self, width, extra=()):
        # a lane along x from -40 to 40 on a floor that climbs 6 in 100; its walls stand on the hill, stepped
        t = math.atan(self.RISE)
        c, sn = math.cos(t), math.sin(t)
        floor = part("Floor", 0, self.BASE - 0.5 / c, 0, (80 / c, 1, 60))
        floor["rot"] = [[c, -sn, 0], [sn, c, 0], [0, 0, 1]]  # (about z: +x climbs)
        ps = [floor]
        for x in range(-36, 40, 8):
            y = self.BASE + self.RISE * x
            for z in (-(width / 2 + 0.5), width / 2 + 0.5):
                ps.append(part("Wall", x, y + 6, z, (8, 14, 1)))
        return ps + list(extra)

    def claim(self, ground=None, y=4.0, a=-36, b=36):
        f = {"kind": "alley", "name": "Hill lane", "pos": [(a + b) / 2, y, 0], "from": [a, 0], "to": [b, 0]}
        if ground is not None:
            f["ground"] = ground
        return f

    def test_a_climbing_lane_read_over_one_height_is_0_wide_and_from_its_own_ground_is_as_built(self):
        # the old way: one height at the lane's middle - toward its upper end the hill stands in the band
        flat = checked(self.hill(10), [self.claim()])
        self.assertEqual(len(flat), 1, flat)
        self.assertIn("(wants 8.0..)", flat[0])
        # from the floor's own height at each end: 10 wide, fits
        ends = [self.BASE + self.RISE * -36, self.BASE + self.RISE * 36]
        self.assertEqual(checked(self.hill(10), [self.claim(ends)]), [])
        # ... and a lane 6 wide is still refused, at its true width
        narrow = checked(self.hill(6), [self.claim(ends)])
        self.assertEqual(len(narrow), 1, narrow)
        self.assertIn("w 6.0 (wants 8.0..)", narrow[0])

    def test_something_low_at_the_downhill_end_is_seen(self):
        # a block 1.5 studs high and 3 proud of the wall at the lane's LOW end (a band read a stud too high misses it)
        low = part("Step", -34, self.BASE + self.RISE * -34 + 0.75, -3.5, (4, 1.5, 3))
        ends = [self.BASE + self.RISE * -36, self.BASE + self.RISE * 36]
        errs = checked(self.hill(10, [low]), [self.claim(ends)])
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("w 7.0 (wants 8.0..)", errs[0])
        # a claim lifted to an even height over the lane's HIGHEST ground (how a sloped town claimed before) never
        # sees it: its band starts 4 studs over the low end's ground
        lifted = checked(self.hill(10, [low]), [self.claim(None, y=8.0)])
        self.assertEqual(lifted, [])

    def across(self, extra=(), cross=0.2, width=8.4):
        # the floor climbs 2 in 10 ACROSS the lane (toward +z, the claim's left); the lane is level along its length
        t = math.atan(0.2)
        c, sn = math.cos(t), math.sin(t)
        floor = part("Floor", 0, 4.9 - 0.5 / c, 0, (80, 1, 60 / c))
        floor["rot"] = [[1, 0, 0], [0, c, sn], [0, -sn, c]]  # (about x: +z climbs)
        half = width / 2
        ps = [floor, part("WallLow", 0, 4.9 - 0.2 * half + 7, -(half + 0.5), (72, 16, 1)),
              part("WallHigh", 0, 4.9 + 0.2 * half + 7, half + 0.5, (72, 16, 1))]
        f = self.claim([4.9, 4.9], y=4.9)
        if cross is not None:
            f["cross"] = cross
        return checked(ps + list(extra), [f])

    def test_the_band_follows_the_hill_across_the_lane_when_the_claim_says_how_it_climbs(self):
        self.assertEqual(self.across(), [])
        # a slab lying on the UPHILL half, its top 0.9 over the ground it lies on (a spawn pad, a kerb): 1.5 over the
        # lane's middle line. With "cross" it is floor; without, the middle line's band reads it as a wall
        pad = part("Pad", 0, 4.9 + 0.2 * 3 + 0.45, 3, (72, 0.9, 2))
        self.assertEqual(self.across([pad]), [])
        middle_only = self.across([pad], cross=None)
        self.assertEqual(len(middle_only), 1, middle_only)
        self.assertIn("(wants 8.0..)", middle_only[0])
        # a block 1.5 over its own ground on the DOWNHILL half (its top 0.9 over the middle line): a real thing in
        # the way. With "cross" it is seen; the middle line's band stands clear of it
        low = part("Crate", 0, 4.9 - 0.2 * 3 + 0.75, -3, (72, 1.5, 2))
        seen = self.across([low])
        self.assertEqual(len(seen), 1, seen)
        self.assertIn("(wants 8.0..)", seen[0])
        self.assertEqual(self.across([low], cross=None), [])

    def test_a_thin_post_anywhere_along_a_sloped_lane_is_seen(self):
        # every stud of a sloped lane is read (it was one sample every 8 studs: a fresh reader's copy that kept the
        # old count on a slope alone passed every test): a post half a stud thick wherever it stands, and a rail a
        # third of a stud thick, two studs in from the wall
        ends = [self.BASE + self.RISE * -36, self.BASE + self.RISE * 36]
        for x in (-35.8, -31.6, -20.45, 3.4, 17.15, 35.6):
            for thick, z in ((0.5, -2.75), (0.3, -2.65)):
                post = part("Post", x, self.BASE + self.RISE * x + 5, z, (thick, 10, thick))
                errs = checked(self.hill(10, [post]), [self.claim(ends)])
                self.assertEqual(len(errs), 1, (x, thick, errs))
                self.assertIn("w 7.5 (wants 8.0..)", errs[0])

    def test_a_post_beside_a_stud_line_and_two_posts_not_quite_opposite_are_seen(self):
        # a post half a stud thick at x = -27.6, two studs in from the wall. A line a hair wide at x = -28 passes it
        # by; a body does not
        ends = [self.BASE + self.RISE * -36, self.BASE + self.RISE * 36]
        post = part("Post", -27.6, self.BASE + self.RISE * -27.6 + 5, -2.75, (0.5, 10, 0.5))
        self.assertEqual(checked(self.hill(10), [self.claim(ends)]), [])
        errs = checked(self.hill(10, [post]), [self.claim(ends)])
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("w 7.5 (wants 8.0..)", errs[0])
        # two posts NOT quite opposite each other (0.4 apart along the lane), one each side: both stand in the stud
        # the sample at -28 reads, so the lane is as wide as the gap between them - not "open on one side"
        left = part("PostL", -27.3, self.BASE + self.RISE * -27.3 + 5, -3.75, (0.5, 10, 0.5))
        right = part("PostR", -27.7, self.BASE + self.RISE * -27.7 + 5, 3.75, (0.5, 10, 0.5))
        both = checked(self.hill(10, [left, right]), [self.claim(ends)])
        self.assertEqual(len(both), 1, both)
        self.assertIn("w 7.0 (wants 8.0..)", both[0])

    def test_ground_given_wrong_is_an_error_and_a_level_claim_is_untouched(self):
        errs = checked(self.hill(10), [self.claim("uphill")])
        self.assertEqual(len(errs), 1, errs)
        self.assertIn('"ground" is the floor\'s height at from and at to', errs[0])
        for bad in ([1.0], [1.0, 2.0, 3.0], [True, False], [1.0, float("nan")], [1.0, "2"]):
            got = checked(self.hill(10), [self.claim(bad)])
            self.assertEqual(len(got), 1, (bad, got))
            self.assertIn('"ground" is the floor', got[0])
        ends = [self.BASE + self.RISE * -36, self.BASE + self.RISE * 36]
        for bad in ("steep", True, [0.1]):
            f = self.claim(ends)
            f["cross"] = bad
            got = checked(self.hill(10), [f])
            self.assertEqual(len(got), 1, (bad, got))
            self.assertIn('"cross" is one number', got[0])
        # "cross" with no "ground" is refused too; a claim on sloping ground with no length is an error, not a crash
        f = self.claim()
        f["cross"] = 0.1
        self.assertIn('"cross" is one number', checked(self.hill(10), [f])[0])
        point = self.claim(ends, a=0, b=0)
        self.assertIn("from and to are one point", checked(self.hill(10), [point])[0])
        # ... and "ground" on a claim that is no street is said, never ignored
        door = {"kind": "opening", "name": "Door", "pos": [0, 4, 0], "size": [5, 8.5, 1], "ground": [4.0, 4.0]}
        got = checked(self.hill(10), [door])
        self.assertEqual(len(got), 1, got)
        self.assertIn('"ground" / "cross" are an alley\'s or a street\'s', got[0])
        # a level lane with no "ground": the voxel march, as before
        level = [part("WallN", 0, 6, -5.5, (72, 12, 1)), part("WallS", 0, 6, 5.5, (72, 12, 1))]
        self.assertEqual(checked(level, [self.claim(y=0.0)]), [])
        self.assertEqual(checked(level, [self.claim([0.0, 0.0])]), [])  # (and the exact measure agrees)


if __name__ == "__main__":
    unittest.main()
