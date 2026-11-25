"""kit/world/worldcheck.py — does a world PLAY: voxel solids, R6 standing, moves (walk / climb / drop / gap-jump), traps."""

import os
import sys
import unittest

import numpy as np

import importlib.util  # noqa: E402

# loaded by PATH under its own name: kit/audio/check.py is also "check", and the combined test run imports both
_spec = importlib.util.spec_from_file_location("kit_world_check", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "world", "worldcheck.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def floor(x, z, w, d, top, name="F"):
    return {"name": name, "pos": [x, top - 1, z], "size": [w, 2, d], "rot": I3, "collide": True, "class": "Part"}


def world(parts, spawns, **extra):
    ps = list(parts)
    for i, (x, y, z) in enumerate(spawns):
        ps.append({"name": f"Spawn{i}", "pos": [x, y + 0.5, z], "size": [4, 1, 4], "rot": I3, "collide": True, "class": "Part", "spawn": True})
    w = {"name": "T", "parts": ps, "terrain": {"ground": [], "solids": [], "water": []}}
    w.update(extra)
    return w


def run(w, tmp="build/selftest/pytest_world"):
    import json

    os.makedirs(tmp, exist_ok=True)
    p = os.path.join(tmp, "w.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(w, fh)
    return C.run(p, tmp)


class Shapes(unittest.TestCase):
    def test_a_wedge_is_high_at_the_back(self):
        wedge = {"pos": [0, 0, 0], "size": [4, 4, 4], "rot": I3, "class": "WedgePart"}
        inside = C.part_inside(wedge, np.array([[0, 1.5, 1.8], [0, 1.5, -1.8]]))
        self.assertTrue(inside[0])  # (high at +Z)
        self.assertFalse(inside[1])  # (low at -Z)

    def test_a_rotated_block(self):
        r = [[0, 0, 1], [0, 1, 0], [-1, 0, 0]]  # 90 degrees about Y: the long X side now runs along Z
        long = {"pos": [0, 0, 0], "size": [10, 2, 2], "rot": r}
        pts = np.array([[0, 0, 4.5], [4.5, 0, 0]])
        self.assertEqual(list(C.part_inside(long, pts)), [True, False])


class Moves(unittest.TestCase):
    def test_a_ledge_within_the_jump_is_climbed_and_one_above_is_not(self):
        base = floor(0, 0, 40, 40, 0)
        low = floor(14, 0, 8, 8, 6, "Low")
        high = floor(-14, 0, 8, 8, 9, "High")
        r = run(world([base, low, high], [(0, 0.5, -12)]))
        self.assertEqual(r["status"], "pass")
        self.assertTrue(any("no one can reach" in w for w in r["warnings"]))  # (the 9-stud one)
        self.assertLess(r["stats"]["unreachable_sq_studs"], 80)  # (only the high one: 8 x 8 minus its edge)

    def test_a_gap_jump_crosses_7_studs_but_not_20(self):
        a = floor(-20, 0, 20, 10, 0, "A")
        b = floor(5, 0, 16, 10, 0, "B")  # (a 7-stud gap: A ends at x=-10, B starts at x=-3)
        c = floor(41, 0, 16, 10, 0, "C")  # (a 20-stud gap after B: past the 8.7-stud flat range)
        r = run(world([a, b, c], [(-20, 0.5, 0)]))
        self.assertTrue(r["stats"]["unreachable_sq_studs"] >= 100)  # (C)
        self.assertTrue(r["stats"]["reachable_sq_studs"] >= 300)  # (A + B)

    def test_two_pits_far_apart_are_two_pockets_and_still_one_error(self):
        def pit(cx):
            bottom = floor(cx, 0, 30, 30, -15, f"Bottom{cx}")
            rim = [floor(cx, -12, 30, 6, 0, "N"), floor(cx, 12, 30, 6, 0, "S"), floor(cx - 12, 0, 6, 18, 0, "W"), floor(cx + 12, 0, 6, 18, 0, "E")]
            return [bottom] + rim
        ground = [floor(0, 40, 200, 40, 0, "Walk")]  # (a walkway joining both pits' rims to the spawns)
        r = run(world(ground + pit(-60) + pit(60), [(-60, 0.5, 40), (60, 0.5, 40)]))
        self.assertEqual(r["status"], "fail")
        msg = next(e for e in r["errors"] if "TRAP" in e)
        self.assertIn("+1 more pocket", msg)  # (named pocket by pocket, the area still summed into the gate)

    def test_a_pit_with_no_way_out_is_a_trap_error(self):
        bottom = floor(0, 0, 60, 60, -15, "Bottom")
        rim = [floor(0, -22, 60, 16, 0, "N"), floor(0, 22, 60, 16, 0, "S"), floor(-22, 0, 16, 28, 0, "W"), floor(22, 0, 16, 28, 0, "E")]
        r = run(world([bottom] + rim, [(-22, 0.5, -22), (22, 0.5, -22)]))
        self.assertEqual(r["status"], "fail")
        self.assertTrue(any("TRAP" in e for e in r["errors"]))

    def test_a_room_sealed_by_walls_thinner_than_a_voxel_is_sealed(self):
        # review 2026-10-13: 0.3-stud walls covered no cell centre and the closed room read as walkable
        base = floor(0, 0, 120, 120, 0)
        t = 0.3
        walls = [
            {"name": "E", "pos": [20.1 + t / 2, 10, 0], "size": [t, 20, 40], "rot": I3, "collide": True, "class": "Part"},
            {"name": "W", "pos": [-20.1 - t / 2, 10, 0], "size": [t, 20, 40], "rot": I3, "collide": True, "class": "Part"},
            {"name": "N", "pos": [0, 10, -20.1 - t / 2], "size": [40.6, 20, t], "rot": I3, "collide": True, "class": "Part"},
            {"name": "S", "pos": [0, 10, 20.1 + t / 2], "size": [40.6, 20, t], "rot": I3, "collide": True, "class": "Part"},
        ]
        r = run(world([base] + walls, [(40, 0.5, 40)]))
        # (the whole room, wall to wall: 40 x 40. Until 2026-11-15 this read "x -19..20" - the body's footprint was
        # tried toward one side only, so the column against the west wall was never stood on)
        self.assertTrue(any("1600 sq studs of floor no one can reach at x -20..20, z -20..20" in w for w in r["warnings"]))

    def test_spawns_that_cannot_meet_fail(self):
        a = floor(-30, 0, 20, 20, 0, "A")
        b = floor(30, 0, 20, 20, 0, "B")  # (40 studs of void between)
        r = run(world([a, b], [(-30, 0.5, 0), (30, 0.5, 0)]))
        self.assertTrue(any("cannot reach the spawn" in e for e in r["errors"]))



class Stairs(unittest.TestCase):
    """a flight of 14 steps a stud high and 1.8 deep, 4 wide between two walls (no way round it), up to a deck 14
    studs over the ground - the same flight laid out to climb toward each of the four sides"""

    def flight(self, axis, way):
        def at(along, across, y, size_along, size_y, size_across, name):
            pos = [along, y, across] if axis == "x" else [across, y, along]
            size = [size_along, size_y, size_across] if axis == "x" else [size_across, size_y, size_along]
            return {"name": name, "pos": pos, "size": size, "rot": I3, "collide": True, "class": "Part"}

        parts = [floor(0, 0, 90, 90, 0)]
        for k in range(1, 15):
            parts.append(at(way * (k - 0.5) * 1.8, 0, k / 2, 1.8, k, 4, "Stair"))
        run_len = 14 * 1.8
        for side in (-2.5, 2.5):
            parts.append(at(way * run_len / 2, side, 12, run_len, 24, 1, "Wall"))
        parts.append(at(way * (run_len + 5), 0, 13, 10, 2, 10, "Deck"))  # (its top 14 up, at the flight's head)
        spawn = (way * -8, 0.5, 0) if axis == "x" else (0, 0.5, way * -8)
        return run(world(parts, [spawn]))

    def test_a_flight_is_climbed_whichever_way_it_runs(self):
        # (toward -x and -z the deck read as "no one can reach": the body's footprint was tried on one side only)
        for axis in ("x", "z"):
            for way in (1, -1):
                r = self.flight(axis, way)
                self.assertEqual(r["status"], "pass", (axis, way))
                self.assertFalse(any("no one can reach" in w for w in r["warnings"]), (axis, way, r["warnings"]))
        # ... and the four agree on how much can be walked, to a few cells
        areas = [self.flight(a, w)["stats"]["reachable_sq_studs"] for a in ("x", "z") for w in (1, -1)]
        self.assertLess(max(areas) - min(areas), 30, areas)


def box(x0, x1, z0, z1, y0=0.0, y1=20.0, name="B"):
    return {"name": name, "pos": [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2], "size": [x1 - x0, y1 - y0, z1 - z0], "rot": I3,
            "collide": True, "class": "Part"}


class BodyWidth(unittest.TestCase):
    """the walker is a BODY 2 studs wide that moves as one piece - through no gap narrower than itself, however the
    gap is shaped - and through nothing solid. Each world is a walled yard 40 x 40 cut in two; the far half holds
    the goal."""

    def reached(self, parts, spawn, goal):
        yard = [box(-22, 22, -22, 22, -2, 0, "F"), box(-22, -20, -22, 22), box(20, 22, -22, 22), box(-20, 20, -22, -20),
                box(-20, 20, 20, 22)]
        w = world(yard + parts, [spawn])
        w["objectives"] = [{"name": "Goal", "pos": list(goal)}]
        r = run(w)
        return not any("cannot reach objective" in e for e in r["errors"])

    def test_a_straight_gap_passes_at_2_studs_and_not_under(self):
        # a wall across the yard at x -1..1 with a gap in it, the gap's edges ON the cells' edges (a gap whose walls
        # stand on the cells' middles is shut in the voxels whatever the body: the first test of this did that)
        for gap, through in ((1, False), (2, True), (3, True)):
            wall = [box(-1, 1, -20, 0), box(-1, 1, gap, 20)]
            self.assertEqual(self.reached(wall, (-10, 0.5, 0.5), (10, 0.5, 0.5)), through, gap)
        # (what the 1-stud cells cannot tell: a gap 1.5 wide that holds two cells' middles reads as 2 - half a stud)

    def test_two_staggered_walls_a_stud_apart_are_no_way(self):
        # two corridors 2 wide that meet shifted by one stud: where they join, the way is ONE stud wide. Each cell
        # there can be stood on through its own corridor's square - no square holds both (a fresh reader: this
        # passed when a cell was "stood on through any square" and the walk joined any two such cells)
        staggered = [box(-20, 0, -20, -1), box(-20, 0, 1, 20), box(0, 20, -20, 0), box(0, 20, 2, 20)]
        self.assertFalse(self.reached(staggered, (-10, 0.5, 0), (10, 0.5, 1)))
        # ... shifted by nothing, the corridor is 2 wide all the way: it passes
        straight = [box(-20, 0, -20, -1), box(-20, 0, 1, 20), box(0, 20, -20, -1), box(0, 20, 1, 20)]
        self.assertTrue(self.reached(straight, (-10, 0.5, 0), (10, 0.5, 0)))
        # a Z-shaped opening between two rooms: 1 and 1.5 studs are no way, 2 studs is
        for gap, through in ((1, False), (1.5, False), (2, True)):
            z_opening = [box(-20, 1, gap, 20), box(1, 20, -20, 0)]
            self.assertEqual(self.reached(z_opening, (-10, 0.5, -10), (10, 0.5, 10)), through, gap)

    def test_a_corridor_2_wide_is_walked_along_either_wall(self):
        # (with the body tried toward one side only, half of such a corridor was never stood on)
        for side in (-1, 1):
            corridor = [box(-20, 20, -20, -1), box(-20, 20, 1, 20)]
            self.assertTrue(self.reached(corridor, (-18, 0.5, 0), (18, 0.5, side * 0.5)), side)


class Solids(unittest.TestCase):
    """nothing solid is passed through: not a roof from above, not a ceiling from below"""

    def hut(self, door):
        # a hut 12 x 12 on a wide floor: walls 6 high, a roof slab over it; steps up to the roof beside it
        parts = [box(-40, 40, -40, 40, -2, 0, "F")]
        walls = [box(-6, -5, -6, 6, 0, 6), box(5, 6, -6, 6, 0, 6), box(-6, 6, -6, -5, 0, 6)]
        walls += [box(-6, -1.5, 5, 6, 0, 6), box(1.5, 6, 5, 6, 0, 6)] if door else [box(-6, 6, 5, 6, 0, 6)]
        roof = [box(-6, 6, -6, 6, 6, 7, "Roof")]
        steps = [box(6, 10, -6 + 2 * k, -4 + 2 * k, 0, 1 + k, "Step") for k in range(6)]  # (up to 6, then the roof at 7)
        w = world(parts + walls + roof + steps, [(20, 0.5, 20)])
        w["objectives"] = [{"name": "Inside", "pos": [0, 0.5, 0]}, {"name": "OnTheRoof", "pos": [0, 7.5, 0]}]
        return run(w)

    def test_a_closed_hut_is_not_entered_through_its_roof(self):
        r = self.hut(False)
        errs = " | ".join(r["errors"])
        self.assertIn('cannot reach objective "Inside"', errs)  # (the walk dropped a body through the roof slab)
        self.assertNotIn('cannot reach objective "OnTheRoof"', errs)  # (the roof itself is climbed, by the steps)
        # the same hut with a doorway 3 wide: walked into
        r = self.hut(True)
        self.assertEqual([e for e in r["errors"] if "cannot reach objective" in e], [])

    def test_a_floor_under_a_low_ceiling_is_not_jumped_up_through(self):
        # a deck 6 studs up (within a jump) over the whole way to it: from under it nobody comes up through it
        parts = [box(-40, 40, -40, 40, -2, 0, "F"), box(-10, 10, -10, 10, 6, 7, "Deck")]
        w = world(parts, [(30, 0.5, 30)])
        w["objectives"] = [{"name": "OnTheDeck", "pos": [0, 7.5, 0]}]
        r = run(w)
        # (from beside the deck it IS climbed: 7 studs is within the 7.2 jump - but only from its edge)
        self.assertEqual([e for e in r["errors"] if "cannot reach objective" in e], [])
        # ... walled in to the sky on all four sides, with a doorway 4 wide and 5.5 high into the room UNDER the deck:
        # the room is walked into, and the only way onto the deck would be up through it
        walls = [box(-11, -10, -11, 11, 0, 30), box(10, 11, -11, 11, 0, 30), box(-11, 11, -11, -10, 0, 30),
                 box(-11, -2, 10, 11, 0, 30), box(2, 11, 10, 11, 0, 30), box(-2, 2, 10, 11, 5.5, 30)]
        w = world(parts + walls, [(30, 0.5, 30)])
        w["objectives"] = [{"name": "UnderTheDeck", "pos": [0, 0.5, 0]}, {"name": "OnTheDeck", "pos": [0, 7.5, 0]}]
        errs = " | ".join(run(w)["errors"])
        self.assertNotIn('cannot reach objective "UnderTheDeck"', errs)
        self.assertIn('cannot reach objective "OnTheDeck"', errs)


def flat_ground(size=64, step=4, h=10.0):
    n = size // step + 1
    return {"x0": -size / 2, "z0": -size / 2, "step": step, "nx": n, "nz": n, "heights": [h] * (n * n)}


class LookLint(unittest.TestCase):
    """look_lint: what a generated world gets wrong that the play check never sees."""

    def lint(self, parts, paints=None):
        w = {"name": "T", "parts": parts, "terrain": {"ground": [flat_ground()], "solids": [], "water": []}}
        if paints:
            w["paints"] = paints
        return C.look_lint(w)

    def box(self, name, x, y, z, s=2.0, collide=True):
        return {"name": name, "pos": [x, y, z], "size": [s, s, s], "rot": I3, "collide": collide}

    def test_floating_part_is_found_and_a_held_one_is_not(self):
        on_land = self.box("Pillar", 0, 11, 0)                    # bottom at 10 = the land
        held = {"name": "Beam", "pos": [0, 12.5, 2], "size": [2, 1, 2], "rot": I3, "collide": True}  # touches the pillar
        floater = self.box("Rock", 20, 30, 20)                    # 19 studs over the land, touching nothing
        msgs = self.lint([on_land, held, floater])
        self.assertTrue(any("1 solid part(s) float" in m and "Rock" in m for m in msgs), msgs)

    def test_buried_part_is_found(self):
        msgs = self.lint([self.box("Rubble", 0, 5, 0)])           # top at 6, land at 10
        self.assertTrue(any("under the land" in m for m in msgs), msgs)

    def test_rock_on_a_worn_trail_is_found_and_a_flush_one_is_not(self):
        trail = [{"material": "Ground", "width": 8, "points": [[-30, 10, 0], [30, 10, 0]]}]
        tall = {"name": "Rock", "pos": [5, 12, 1], "size": [3, 4, 3], "rot": I3, "collide": True}   # 4 studs proud
        flush = {"name": "Rock", "pos": [-5, 10.4, 0], "size": [3, 1, 3], "rot": I3, "collide": True}  # 0.9 proud
        msgs = self.lint([tall, flush], paints=trail)
        self.assertTrue(any("1 rock(s)" in m for m in msgs), msgs)

    def test_clean_world_says_nothing(self):
        self.assertEqual(self.lint([self.box("Pillar", 0, 11, 0)]), [])

    def test_floater_on_a_baseplate_world(self):
        # no terrain: the lowest solid parts are the ground; a block high above nothing is a floater
        w = {"name": "T", "terrain": {"ground": [], "solids": [], "water": []}, "parts": [
            {"name": "Baseplate", "pos": [0, -0.5, 0], "size": [100, 1, 100], "rot": I3, "collide": True},
            {"name": "Crate", "pos": [0, 50, 0], "size": [4, 4, 4], "rot": I3, "collide": True}]}
        msgs = C.look_lint(w)
        self.assertTrue(any("float" in m and "Crate" in m for m in msgs), msgs)


class FineLocal(unittest.TestCase):
    """mission 05 5.6: on a big map (2-stud cells) each unreachable floor and small trap is walked again at 1-stud
    cells around it; only what the fine walk REACHES is dropped (a real platform with no way up stays named)"""

    def test_a_narrow_door_is_walked_through_and_a_sealed_room_is_not(self):
        def wall(x, z, w, d):
            return {"name": "Wall", "pos": [x, 5, z], "size": [w, 10, d], "rot": I3, "collide": True}

        def room(cx, door):
            ws = [wall(cx, 10.5, 22, 1), wall(cx - 10.5, 0, 1, 22), wall(cx + 10.5, 0, 1, 22)]
            if door:  # (a 3-stud doorway: a 2-stud body walks through)
                ws += [wall(cx - 5.25, -10.5, 9.5, 1), wall(cx + 7.25, -10.5, 9.5, 1)]
            else:
                ws.append(wall(cx, -10.5, 22, 1))
            return ws

        solids = [floor(0, 0, 300, 120, 0, "Base")] + room(100, True) + room(-100, False)
        g = C.Grid([-152, -4, -62], [152, 20, 62], 2.0)
        for p in solids:
            g.fill_part(p)
        P = dict(C.PLAYER)
        L = C.standable_levels(g, P["height"])
        nx_, nz_, K = L.shape
        # the coarse pass: every floor outside the two rooms was reached (the case the fine walk starts from)
        ids = np.arange(nx_ * nz_ * K)
        x, z = ids // (nz_ * K), (ids // K) % nz_
        wx, wz = g.lo[0] + (x + 0.5) * 2, g.lo[2] + (z + 0.5) * 2
        inside = (np.abs(np.abs(wx) - 100) < 12) & (np.abs(wz) < 12)
        reach = (L.ravel() >= 0) & ~inside
        terr = {"ground": [], "solids": []}
        doored = C.fine_reach({"x": [90, 110], "z": [-10, 10], "y": 0.0}, g, L, reach, solids, terr, P)
        sealed = C.fine_reach({"x": [-110, -90], "z": [-10, 10], "y": 0.0}, g, L, reach, solids, terr, P)
        self.assertGreaterEqual(doored, 0.9)
        self.assertTrue(sealed is None or sealed == 0.0, sealed)


class MeshShape(unittest.TestCase):
    def test_a_mesh_is_voxelized_as_its_own_shape_not_its_box(self):
        import base64
        import json
        import tempfile

        # a square pyramid, 1 x 1 x 1 in mesh units (apex at the top centre), as kit world import writes it
        apex, a, b, c, d = [0.5, 1, 0.5], [0, 0, 0], [1, 0, 0], [1, 0, 1], [0, 0, 1]
        tris = [apex, a, b, apex, b, c, apex, c, d, apex, d, a, a, b, c, a, c, d]
        buf = base64.b64encode(np.array(tris, "<f4").tobytes()).decode()
        tmp = tempfile.mkdtemp()
        with open(os.path.join(tmp, "pyr.mesh.json"), "w", encoding="utf-8") as fh:
            json.dump({"tris": 6, "min": [0, 0, 0], "max": [1, 1, 1], "position": buf}, fh)
        part = {"name": "KitMesh", "mesh": "pyr", "meshCollide": True, "pos": [0, 10, 0], "size": [20, 20, 20], "rot": I3}
        C.mesh_hulls({"parts": [part]}, tmp)
        self.assertIsNotNone(part.get("_points"))
        g = C.Grid([-12, -2, -12], [12, 24, 12], 1.0)
        g.fill_part(part)

        def top(x, z):
            col = g.occ[g.index([x, 0, z])[0], :, g.index([x, 0, z])[2]]
            return int(np.nonzero(col)[0].max()) if col.any() else -1

        self.assertGreater(top(0.5, 0.5), top(-9.5, -9.5) + 10)  # (the apex column stands far above a corner)
        self.assertEqual(C.mesh_points(None, "nothing"), None)  # (no data: the box fallback)


class Guidance(unittest.TestCase):
    """AAA gaps W2 + W10 along the roads: a landmark in view, and no long walk with nothing to find"""

    def road(self, x0, x1):
        return {"material": "Ground", "points": [[x0, 0, 0], [x1, 0, 0]]}

    def test_a_landmark_behind_a_wall_is_named_and_one_in_view_is_not(self):
        base = floor(0, 0, 400, 60, 0, "Base")
        wall = {"name": "Wall", "pos": [0, 30, 20], "size": [400, 60, 2], "rot": I3, "collide": True}
        hidden = run(world([base, wall], [(-150, 0.5, 0)], paints=[self.road(-150, 150)],
                           landmarks=[{"name": "Tower", "top": [0, 50, 200]}]))
        self.assertTrue(any("landmark is in view from only" in w for w in hidden["warnings"]), hidden["warnings"])
        seen = run(world([base], [(-150, 0.5, 0)], paints=[self.road(-150, 150)],
                         landmarks=[{"name": "Tower", "top": [0, 50, 200]}]))
        self.assertGreater(seen["stats"]["landmark_view_pct"], 95)
        self.assertFalse(any("landmark" in w for w in seen["warnings"]), seen["warnings"])

    def test_no_landmark_and_a_long_empty_road_are_named(self):
        base = floor(0, 0, 2200, 40, 0, "Base")
        r = run(world([base], [(-1050, 0.5, 0)], paints=[self.road(-1050, 1050)]))
        self.assertTrue(any("no landmark" in w for w in r["warnings"]), r["warnings"])
        self.assertTrue(any("of road with nothing to find" in w for w in r["warnings"]), r["warnings"])
        self.assertGreater(r["stats"]["pacing_max_gap_s"], 100)


if __name__ == "__main__":
    unittest.main()
