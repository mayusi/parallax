"""test_world_zfight.py - Z-FIGHTING IS AN ERROR of `kit world check` (kit/world/worldcheck.py zfight_lint; card my7f,
LIMITATIONS_FIXES_V3.md stage A.1). GothicCourtyard's house floors (WoodPlanks, top at y = 0) lay on the court's Slate
floor (top at y = 0) and flickered in Roblox (one Studio capture stone, the next planks, 2026-11-12) while every gate
passed. Held here: two faces of two looks in one plane (within 0.03 studs) that overlap by more than 0.1 square studs
are an error, at any turn of the parts; a face buried in a third part, a face pressed on the ground, faces 0.08 apart,
an overlap of a sliver and an underside are not; the same look is not counted (it draws the same pixels if Roblox
maps a material in world space - not yet seen in Studio; the compiler's own warning still counts it).
Not claimed: which offsets flicker in Roblox at which distance (not measured in Studio) - 0.03 is the V3 spec's band.
"""
import importlib.util
import json
import os
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_worldcheck_zfight", os.path.join(HERE, "..", "..", "world", "worldcheck.py"))
WC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(WC)
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def part(name, pos, size, mat="Slate", color=(90, 90, 90), rot=None, transparency=0, cls="Part", shape="Block"):
    return {"class": cls, "name": name, "pos": list(pos), "size": list(size), "material": mat, "color": list(color),
            "rot": rot or [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "shape": shape, "transparency": transparency}


def yaw(deg):
    a = np.radians(deg)
    c, s = float(np.cos(a)), float(np.sin(a))
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def pairs(*ps):
    errors, found = WC.zfight_lint({"parts": list(ps)})
    return errors, found


COURT = part("Floor", (0, -0.5, 0), (160, 1, 160), "Slate", (58, 62, 70))


class ZFight(unittest.TestCase):
    def test_house_floor_on_the_court_floor_is_an_error(self):
        # (GothicCourtyard's N1 house, as compiled on 2026-11-12)
        e, p = pairs(COURT, part("Slab", (-35, -0.5, -46), (20, 1, 22), "WoodPlanks", (120, 80, 50)))
        self.assertEqual(len(p), 1)
        self.assertAlmostEqual(p[0]["area"], 440.0, places=3)
        self.assertEqual(len(e), 1)
        self.assertIn("z-fighting", e[0])
        self.assertIn("flicker", e[0])

    def test_a_turned_part_is_measured_too(self):
        # the compiler's own warning skips every part that is not axis-aligned (card px2n)
        e, p = pairs(COURT, part("Slab", (0, -0.5, 0), (10, 1, 10), "WoodPlanks", (120, 80, 50), rot=yaw(30)))
        self.assertEqual(len(p), 1)
        self.assertAlmostEqual(p[0]["area"], 100.0, places=3)
        # and two turned walls whose faces meet in one plane
        e, p = pairs(part("A", (0, 5, 0), (10, 10, 1), rot=yaw(45)),
                     part("B", (4 * np.cos(np.radians(45)), 5, -4 * np.sin(np.radians(45))), (10, 10, 1), "Brick", (140, 60, 50), rot=yaw(45)))
        # (both 10 x 10 faces overlap 6 x 10 where the walls lap, and their tops 6 x 1)
        self.assertEqual(sorted(round(float(x["area"]), 6) for x in p), [6.0, 60.0, 60.0])

    def test_within_the_band_and_clear_of_it(self):
        wood = ("WoodPlanks", (120, 80, 50))
        self.assertEqual(len(pairs(COURT, part("Slab", (0, -0.48, 0), (10, 1, 10), *wood))[1]), 1)  # 0.02 apart: one plane
        self.assertEqual(len(pairs(COURT, part("Slab", (0, -0.46, 0), (10, 1, 10), *wood))[1]), 0)  # 0.04: past the band
        self.assertEqual(len(pairs(COURT, part("Slab", (0, -0.5 + WC.ZFIGHT_TOL * 0.99, 0), (10, 1, 10), *wood))[1]), 1)
        self.assertEqual(len(pairs(COURT, part("Slab", (-0.04, -0.42, 0), (10, 1.16, 10), *wood))[1]), 0)  # the lift: 0.08 clear

    def test_a_sliver_is_not_counted(self):
        # an overlap of 0.1 square studs or less (tops: a strip 0.04 x 2; sides 0.04 x 1)
        e, p = pairs(part("A", (0, 0.5, 0), (2, 1, 2)), part("B", (1.96, 0.5, 0), (2, 1, 2), "Brick", (140, 60, 50)))
        self.assertEqual(len(p), 0)

    def test_one_look_is_not_an_error(self):
        e, p = pairs(part("A", (0, 1, 0), (10, 2, 10)), part("B", (4, 1, 0), (10, 2, 10)))
        self.assertEqual((e, p), ([], []))
        e, p = pairs(part("A", (0, 1, 0), (10, 2, 10)), part("B", (4, 1, 0), (10, 2, 10), color=(91, 90, 90)))
        self.assertEqual(len(p), 3)  # (a colour one step off is another look: the tops and both long sides)

    def test_a_face_buried_in_a_third_part_is_not_an_error(self):
        # a lower wall's top and a wooden slab's top at one height, the wall above sitting on both
        e, p = pairs(part("Wall", (0, 4.75, 0), (8, 9.5, 1), "Brick", (140, 60, 50)),
                     part("Slab", (0, 9.0, 5.25), (7.8, 1, 10.5), "WoodPlanks", (120, 80, 50)),  # (its edge inside the wall)
                     part("Wall", (0, 14.25, 0), (8, 9.5, 1), "Brick", (140, 60, 50)))
        self.assertEqual(p, [])
        # without the wall above, the wall's top shows beside the boards: an error
        e, p = pairs(part("Wall", (0, 4.75, 0), (8, 9.5, 1), "Brick", (140, 60, 50)),
                     part("Slab", (0, 9.0, 5.25), (7.8, 1, 10.5), "WoodPlanks", (120, 80, 50)))
        self.assertEqual(len(p), 1)
        self.assertAlmostEqual(float(p[0]["area"]), 3.9)  # (7.8 x the half of the wall the slab laps)
        # and a slab whose edge lies on the wall's outer face shows a strip of boards on the wall: an error
        e, p = pairs(part("Wall", (0, 4.75, 0), (8, 9.5, 1), "Brick", (140, 60, 50)),
                     part("Slab", (0, 9.0, 5), (7.8, 1, 11), "WoodPlanks", (120, 80, 50)),
                     part("Wall", (0, 14.25, 0), (8, 9.5, 1), "Brick", (140, 60, 50)))
        self.assertEqual([round(float(x["area"]), 6) for x in p], [7.8])  # (its 7.8 x 1 edge on the wall's face)

    def test_what_the_fresh_review_found(self):
        wood = ("WoodPlanks", (120, 80, 50))
        floor = part("Floor", (0, -0.5, 0), (40, 1, 40), "Slate", (58, 62, 70))
        slab = part("Slab", (0, -0.5, 0), (10, 1, 10), *wood)
        # a part over MOST of the overlap leaves a rim you see: still an error (centre + 80 % probes called it buried)
        cover = part("Rug", (0, 0.5, 0), (8.6, 1, 8.6), "Fabric", (120, 30, 30))
        self.assertEqual(len(pairs(floor, slab, cover)[1]), 1)
        # two walls over the probes with a strip between them: still an error
        w1 = part("W1", (-2.75, 1, 0), (4.5, 2, 10), "Brick", (140, 60, 50))
        w2 = part("W2", (2.75, 1, 0), (4.5, 2, 10), "Brick", (140, 60, 50))
        self.assertEqual(len(pairs(floor, slab, w1, w2)[1]), 1)
        # a part over ALL of it buries it; glass over all of it does not (it is seen through)
        full = part("Box", (0, 0.5, 0), (10.2, 1, 10.2), "Brick", (140, 60, 50))
        self.assertEqual(pairs(floor, slab, full)[1], [])
        glass = part("Pane", (0, 0.5, 0), (10.2, 1, 10.2), "Glass", (200, 220, 230), transparency=0.8)
        self.assertEqual(len(pairs(floor, slab, glass)[1]), 1)
        # two slabs turned a hair either side of a bucket's edge (one plane to 1e-4 studs) are found
        a = np.arcsin(0.125)
        tilt = lambda t: [[1, 0, 0], [0, float(np.cos(t)), float(-np.sin(t))], [0, float(np.sin(t)), float(np.cos(t))]]
        e, p = pairs(part("A", (0, 0, 0), (10, 1, 10), rot=tilt(a - 1e-5)), part("B", (0, 0, 0), (10, 1, 10), *wood, rot=tilt(a + 1e-5)))
        self.assertGreaterEqual(len(p), 1)
        self.assertTrue(any(abs(float(x["area"]) - 100) < 0.5 for x in p), p)

    def test_a_tiled_plane_is_measured_in_seconds(self):
        # 2,500 tiles of two looks in a chequer, one plane, touching edges only: no pair (they only meet at edges)
        import time
        tiles = [part(f"T{i}_{j}", (i * 2, 0.5, j * 2), (2, 1, 2), "Slate" if (i + j) % 2 else "Marble",
                      (58, 62, 70) if (i + j) % 2 else (200, 200, 200)) for i in range(50) for j in range(50)]
        t = time.time()
        e, p = pairs(*tiles)
        self.assertEqual(p, [])
        self.assertLess(time.time() - t, 6.0)  # (8.4 s before the face boxes were tested first)

    def test_hidden_parts_undersides_and_round_parts_are_left_out(self):
        wood = ("WoodPlanks", (120, 80, 50))
        self.assertEqual(pairs(COURT, part("Slab", (0, -0.5, 0), (10, 1, 10), *wood, transparency=1))[1], [])
        # two undersides in one plane (their tops apart): seen only from under the world
        self.assertEqual(pairs(part("A", (0, 0.5, 0), (2, 1, 2)), part("B", (0, 1, 0), (4, 2, 4), *wood))[1], [])
        self.assertEqual(pairs(COURT, part("Ball", (0, -0.5, 0), (10, 1, 10), *wood, shape="Ball"))[1], [])

    def test_the_check_run_fails_on_it(self):
        # kit world check's run(): status fail, the error in its errors, the pairs in its stats; the boards lifted 0.08
        # (World.GROUND_LIFT, the building generator's ground floor) pass the same run
        import tempfile
        d = tempfile.mkdtemp()
        spawn = part("Spawn", (20, 0.5, 20), (6, 1, 6), cls="SpawnLocation")
        for slab, status in ((part("Slab", (0, -0.5, 0), (10, 1, 10), "WoodPlanks", (120, 80, 50)), "fail"),
                             (part("Slab", (0, -0.46, 0), (10, 1.08, 10), "WoodPlanks", (120, 80, 50)), "pass")):
            court = part("Floor", (0, -0.5, 0), (60, 1, 60), "Slate", (58, 62, 70))
            path = os.path.join(d, "ZfTiny.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"name": "ZfTiny", "parts": [court, slab, spawn]}, f)
            r = WC.run(path, d)
            self.assertEqual(r["status"], status, r["errors"])
            self.assertEqual(r["stats"]["zfight_pairs"], 1 if status == "fail" else 0)
            if status == "fail":
                self.assertTrue(any(x.startswith("z-fighting:") for x in r["errors"]))


@unittest.skipUnless(os.path.isfile(os.path.join(ROOT, "build", "worlds", "GothicCourtyard.json")), "needs a compiled GothicCourtyard")
class Courtyard(unittest.TestCase):
    def test_the_compiled_courtyard(self):
        with open(os.path.join(ROOT, "build", "worlds", "GothicCourtyard.json"), encoding="utf-8") as f:
            w = json.load(f)
        e, p = WC.zfight_lint(w)
        self.assertEqual(p, [], "GothicCourtyard compiled with z-fighting: rebuild it (lune run kit world) after card my7f")


if __name__ == "__main__":
    unittest.main()
