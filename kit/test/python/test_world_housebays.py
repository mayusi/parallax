"""kit/world/housebays.py - a skin mesh cuts its door where the building generator cuts the building's.

The generator's rule is restated here from kit/lib/world.luau (kind "building", the loop over sides): a side of
length L has n = floor((L - 4) / every) bays, bay k centred at -L/2 + (k - 0.5) * L / n measured along the wall FROM
ITS START CORNER, and the door takes bay ceil(n / 2). Its walls start at: N the west corner, E the north, S the EAST,
W the SOUTH. The mesh lays bays out from the low end of its own axis (west for N / S; south for E / W, Blender y =
-Roblox z). On 2026-11-13 a 27-stud front (2 bays) rendered with the building's window pane inside the mesh's
doorway: on S the two counted from opposite ends.
Run: python kit/test/python/run.py -k world_housebays"""

import importlib.util
import math
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
_spec = importlib.util.spec_from_file_location("kit_world_housebays", os.path.join(ROOT, "kit", "world", "housebays.py"))
HB = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(HB)

# where the generator's wall starts, as a direction along the MESH's own axis for that side (+1: the generator
# walks the way the mesh counts; -1: it starts at the mesh's high end)
GENERATOR_WALKS = {"N": +1, "W": +1, "S": -1, "E": -1}


def generator_door(length, every, side):
    """the door's centre along the mesh's own axis, by the building generator's rule; None = no bay"""
    n = int(math.floor((length - 4) / every))
    if n < 1:
        return None
    k = int(math.ceil(n / 2))
    along = -length / 2 + (k - 0.5) * length / n  # from the generator's start corner
    return along * GENERATOR_WALKS[side]


class DoorBayTest(unittest.TestCase):
    def test_the_mesh_door_stands_in_the_generators_bay_on_every_side_and_width(self):
        checked = even = 0
        for side in "NESW":
            for every in (8, 10, 12):
                for length in [x / 2 for x in range(16, 121)]:  # 8 .. 60 studs in half studs
                    want = generator_door(length, every, side)
                    slot = HB.door_slot(length, every, side)
                    centres = HB.centres(length, every)
                    if want is None:
                        self.assertEqual(slot, 0, (side, every, length))
                        self.assertEqual(centres, [])
                        continue
                    self.assertAlmostEqual(centres[slot - 1], want, places=9, msg=(side, every, length))
                    checked += 1
                    even += len(centres) % 2 == 0
        self.assertGreater(checked, 1000)
        self.assertGreater(even, 300)  # (the even counts are where the two could differ)

    def test_the_case_that_was_seen_wrong(self):
        # a 27-stud front, a window every 10: two bays at -6.75 and +6.75; the building's S wall starts at the east
        # corner, so its door (bay 1 of 2) is the EAST bay; the mesh used to put it in the west one
        self.assertEqual(HB.centres(27, 10), [-6.75, 6.75])
        self.assertEqual(HB.door_slot(27, 10, "S"), 2)
        self.assertEqual(HB.door_slot(27, 10, "N"), 1)
        self.assertEqual(HB.door_slot(27, 10, "E"), 2)
        self.assertEqual(HB.door_slot(27, 10, "W"), 1)

    def test_an_odd_count_keeps_the_middle_bay_either_way(self):
        for side in "NESW":
            self.assertEqual(HB.door_slot(22, 10, side), 1)  # one bay
            self.assertEqual(HB.door_slot(43, 10, side), 2)  # three: the middle

    def test_a_front_too_narrow_for_a_bay_has_no_opening(self):
        # (the mesh used max(1, ...) and cut a door into a wall the building keeps solid)
        self.assertEqual(HB.count(13, 10), 0)
        self.assertEqual(HB.centres(13, 10), [])
        self.assertEqual(HB.door_slot(13, 10, "S"), 0)
        self.assertEqual(HB.count(14, 10), 1)
        self.assertEqual(HB.count(23.999, 10), 1)
        self.assertEqual(HB.count(24, 10), 2)


class MeshUsesTheRuleTest(unittest.TestCase):
    def test_the_house_mesh_reads_its_bays_from_this_module(self):
        """gothic_blender.py needs Blender to run: the least a plain python can hold is that it asks this module
        for the bays and no longer counts them itself."""
        with open(os.path.join(ROOT, "kit", "world", "gothic_blender.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertIn("housebays.centres(run_len, win_every)", text)
        self.assertIn("housebays.door_slot(run_len, win_every, side)", text)
        self.assertNotIn("max(1, int((run_len - 4) / win_every))", text)
        self.assertNotIn("door_slot = (n_win + 1) // 2", text)


if __name__ == "__main__":
    unittest.main()
