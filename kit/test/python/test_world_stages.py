"""test_world_stages.py - a world's BIBLE and its two ROUTE STAGES (kit/world/bible.py, kit/world/stages.py,
kit/world/corner.py; LIMITATIONS_FIXES_V3.md stage A.2-A.3, the studio route's W1 "World Bible & Walked Greybox" and
W2 "40x40 corner").
Held here: a bible names 1 stud = 0.28 m, a rig sheet, region cards (area, lamp rule, fixtures in words - a starter's
placeholder does not pass) and landmarks; a landmark a wall hides from a spawn is said, one in view is not, its own
parts never hide it; a starter is written only when asked; the greybox stage exists only with its renders and a
bible, its id follows the blueprint and the bible, and renders older than either are stale; the corner stage names
its station and its id follows it; the corner's two views look at the station's target from its own side.
Not claimed: what the owner will say of either - his yes is the stage."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(HERE, "..", "..", "world")
sys.path.insert(0, WORLD)


def _load(name):
    spec = importlib.util.spec_from_file_location(f"kit_world_{name}_stages", os.path.join(WORLD, f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


B, S, K = _load("bible"), _load("stages"), _load("corner")
I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]


def bible(**more):
    b = {"world": "T", "stud_m": 0.28, "scale": "r6",
         "regions": [{"name": "Square", "area": [-40, -40, 40, 40], "lamps": "square",
                      "fixtures": "a well in the middle, benches along the north side"}],
         "landmarks": [{"name": "Tower", "pos": [0, 30, 60]}]}
    b.update(more)
    return b


def part(name, pos, size, **more):
    p = {"name": name, "pos": list(pos), "size": list(size), "rot": I3, "collide": True, "transparency": 0}
    p.update(more)
    return p


class Bible(unittest.TestCase):
    def test_a_good_bible_passes_and_each_missing_field_is_said(self):
        bp = {"scale": "r6"}
        self.assertEqual(B.problems(bible(), bp), [])
        self.assertTrue(any("stud_m" in p for p in B.problems(bible(stud_m=0.3), bp)))
        self.assertTrue(any("rig sheet" in p for p in B.problems(bible(), {})))
        self.assertTrue(any('"regions"' in p for p in B.problems(bible(regions=[]), bp)))
        self.assertTrue(any('"lamps"' in p for p in B.problems(bible(regions=[dict(bible()["regions"][0], lamps="everywhere")]), bp)))
        self.assertTrue(any('"fixtures"' in p for p in B.problems(bible(regions=[dict(bible()["regions"][0], fixtures="lamps")]), bp)))
        self.assertTrue(any('"landmarks"' in p for p in B.problems(bible(landmarks=[]), bp)))
        # a starter's placeholder is not written
        st = B.starter("T", {"build": []})
        self.assertTrue(any('"fixtures"' in p for p in B.problems(st, bp)))

    def test_a_landmark_hidden_from_a_spawn_is_said(self):
        spawn = part("Spawn", (0, 0.5, 0), (6, 1, 6), spawn=True)
        tower = part("Tower", (0, 30, 60), (8, 60, 8))
        wall = part("Wall", (0, 10, 30), (40, 20, 2))
        blocked = B.sightlines({"parts": [spawn, tower, wall]}, bible()["landmarks"])
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0][1:], ("Tower", "Wall"))
        self.assertEqual(B.sightlines({"parts": [spawn, tower]}, bible()["landmarks"]), [])
        low = part("Wall", (0, 1, 30), (40, 2, 2))  # (a low wall under the eye line)
        self.assertEqual(B.sightlines({"parts": [spawn, tower, low]}, bible()["landmarks"]), [])
        # a landmark at ground height over a floor: the floor does not hide it (the line ended ON the floor)
        floor = part("Floor", (0, -0.5, 0), (200, 1, 200))
        ground = [{"name": "Tower", "pos": [60, 0, 0]}]
        self.assertEqual(B.sightlines({"parts": [spawn, floor]}, ground), [])
        glass = part("Wall", (0, 10, 30), (40, 20, 2), transparency=0.8)
        self.assertEqual(B.sightlines({"parts": [spawn, tower, glass]}, bible()["landmarks"]), [])

    def test_the_command_writes_a_starter_only_when_asked(self):
        with tempfile.TemporaryDirectory() as tmp:
            worlds = os.path.join(tmp, "assets", "worlds")
            os.makedirs(worlds)
            with open(os.path.join(worlds, "T.json"), "w", encoding="utf-8") as f:
                json.dump({"name": "T", "scale": "r6", "build": [{"tower": {"name": "Spire", "center": [0, 0, 80], "landmark": True}}]}, f)
            r = B.main(["T", "--worlds", worlds, "--build", os.path.join(tmp, "build")])
            self.assertEqual(r["status"], "fail")
            self.assertIn("--write", r["next_action"])
            self.assertFalse(os.path.isfile(os.path.join(worlds, "bible", "T.json")))
            B.main(["T", "--worlds", worlds, "--build", os.path.join(tmp, "build"), "--write"])
            with open(os.path.join(worlds, "bible", "T.json"), encoding="utf-8") as f:
                st = json.load(f)
            self.assertEqual(st["landmarks"][0]["name"], "Spire")
            self.assertEqual(B.main(["T", "--worlds", worlds, "--build", os.path.join(tmp, "build")])["status"], "fail")


class Stages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.worlds = os.path.join(self.tmp, "assets", "worlds")
        self.build = os.path.join(self.tmp, "build", "worlds")
        os.makedirs(os.path.join(self.worlds, "bible"))
        os.makedirs(self.build)
        self.bp = os.path.join(self.worlds, "T.json")
        with open(self.bp, "w", encoding="utf-8") as f:
            json.dump({"name": "T", "scale": "r6", "build": []}, f)
        with open(os.path.join(self.build, "T.json"), "w", encoding="utf-8") as f:
            json.dump({"parts": [part("Spawn", (0, 0.5, 0), (6, 1, 6), spawn=True)]}, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def shots(self, sub):
        d = os.path.join(self.build, *sub)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "eye_1.png"), "wb").close()
        return d

    def test_the_greybox_needs_its_renders_and_its_bible(self):
        c = S.check("T", "greybox", self.tmp, self.build)
        self.assertFalse(c["exists"])
        with open(os.path.join(self.worlds, "bible", "T.json"), "w", encoding="utf-8") as f:
            json.dump(bible(), f)
        self.assertFalse(S.check("T", "greybox", self.tmp, self.build)["exists"])  # (no renders yet)
        time.sleep(0.05)
        self.shots(("look", "T.greybox"))
        c = S.check("T", "greybox", self.tmp, self.build)
        self.assertTrue(c["exists"])
        self.assertFalse(c["stale"])
        self.assertEqual(c["problems"], [])
        first = c["id"]
        # the blueprint changes: another id, and the renders are older than it
        time.sleep(0.05)
        with open(self.bp, "w", encoding="utf-8") as f:
            json.dump({"name": "T", "scale": "r6", "build": [{"floor": {"size": [10, 10]}}]}, f)
        c = S.check("T", "greybox", self.tmp, self.build)
        self.assertNotEqual(c["id"], first)
        self.assertTrue(c["stale"])

    def test_the_corner_names_its_station(self):
        self.assertFalse(S.check("T", "corner", self.tmp, self.build)["exists"])
        d = self.shots(("corner", "T"))
        with open(os.path.join(d, "corner.json"), "w", encoding="utf-8") as f:
            json.dump({"at": "eye_1"}, f)
        a = S.check("T", "corner", self.tmp, self.build)
        self.assertTrue(a["exists"])
        self.assertEqual(a["at"], "eye_1")
        with open(os.path.join(d, "corner.json"), "w", encoding="utf-8") as f:
            json.dump({"at": "over"}, f)
        self.assertNotEqual(S.check("T", "corner", self.tmp, self.build)["id"], a["id"])

    def test_an_unknown_stage(self):
        self.assertFalse(S.check("T", "facade", self.tmp, self.build)["exists"])


class Corner(unittest.TestCase):
    def test_two_views_of_the_station_s_target(self):
        vs = K.views({"cam": [0, 8, -40], "target": [0, 2, 0]})
        self.assertEqual([v["name"] for v in vs], ["corner_eye", "corner_three"])
        eye, three = vs
        # from the station's own side, pulled in: 32 studs short of the target along the line
        self.assertAlmostEqual(eye["at"][2], -32.0)
        self.assertAlmostEqual(eye["target"][0], 0.0)
        # three-quarter: from above, off the line to one side
        self.assertGreater(three["at"][1], 20)
        self.assertNotAlmostEqual(three["at"][0], 0.0)
        with self.assertRaises(ValueError):
            K.views({"name": "x"})


if __name__ == "__main__":
    unittest.main()
