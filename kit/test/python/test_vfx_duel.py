"""G2, the 2-fighter scene (LIMITATIONS_FIXES_V4 3.4 step 1 / 11 Phase 2: "the 24-stud 2-fighter arena" the player
is calibrated in): the scene file both renderers build from (kit/vfx/scenes/g2.json) holds to kit/vfx/duel.py's rules,
each rule refuses its own fault, a preset is held to the scene's anchors, and both renderers build the scene from the
file (the player's buildScene, the booth's buildScene, kit vfx play / booth carrying it)."""

import copy
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "vfx"))
import duel  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


class SceneFile(unittest.TestCase):
    def setUp(self):
        self.scene, _ = duel.load("g2")

    def test_the_kit_scene_passes(self):
        self.assertEqual(duel.check(self.scene), [])
        self.assertEqual(self.scene["arena"]["size"], 24)
        self.assertEqual(sorted(f["role"] for f in self.scene["fighters"]), ["attacker", "victim"])

    def test_the_cli_passes_and_says_so(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "vfx", "duel.py"), "check"], capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["status"], "pass")

    def faults(self, change):
        s = copy.deepcopy(self.scene)
        change(s)
        return " | ".join(duel.check(s))

    def test_arena_must_be_24(self):
        self.assertIn("24 studs square", self.faults(lambda s: s["arena"].__setitem__("size", 32)))

    def test_exactly_two_fighters(self):
        self.assertIn("exactly two", self.faults(lambda s: s["fighters"].append(copy.deepcopy(s["fighters"][1]))))

    def test_victim_faces_the_attacker(self):
        self.assertIn("victim: does not face the attacker", self.faults(lambda s: s["fighters"][1].__setitem__("face", [1, 0, 0])))

    def test_victim_in_reach(self):
        def far(s):
            s["fighters"][1]["pos"] = [0, 0, -10]
            s["anchors"] = {}
        self.assertIn("out of the strike's reach", self.faults(far))

    def test_bodies_do_not_meet(self):
        def near(s):
            s["fighters"][1]["pos"] = [0, 0, -1]
            s["anchors"] = {}
        self.assertIn("their bodies meet", self.faults(near))

    def test_fighters_inside_the_arena(self):
        self.assertIn("not whole inside", self.faults(lambda s: s["arena"].__setitem__("center", [0, 0, 6])))

    def test_attacker_on_the_origin(self):
        self.assertIn("effect's origin", self.faults(lambda s: s["fighters"][0].__setitem__("pos", [2, 0, 0])))

    def test_anchor_on_the_victim(self):
        self.assertIn("anchors.victimChest", self.faults(lambda s: s["anchors"].__setitem__("victimChest", [0, 3.5, -2])))

    def test_every_view_sees_both_whole(self):
        msg = self.faults(lambda s: s["views"].__setitem__("close", {"pos": [3, 4, 5], "look": [0, 3.5, 0], "fov": 40}))
        self.assertIn("views.close", msg)
        self.assertIn("not whole in the frame", msg)

    def test_a_moving_views_every_key(self):
        msg = self.faults(lambda s: s["views"]["cine"]["path"].append({"t": 4, "pos": [0, 4, 30], "look": [0, 3, 40], "fov": 50}))
        self.assertIn("views.cine@4", msg)

    def test_camera_not_inside_a_fighter(self):
        self.assertIn("inside the victim", self.faults(lambda s: s["views"].__setitem__("in", {"pos": [0, 3, -6.5], "look": [0, 3, 0], "fov": 60})))


class PresetAnchors(unittest.TestCase):
    def test_a_strike_on_the_scene_anchors(self):
        p = {"booth": {"scene": "g2"}, "layers": [{"point": "@victimChest^1.2"}, {"target": "@victim"}]}
        self.assertEqual(duel.check_preset(p), [])

    def test_an_anchor_the_scene_lacks(self):
        p = {"booth": {"scene": "g2"}, "layers": [{"point": "@victimKnee"}]}
        self.assertIn("not an anchor of scene g2", " ".join(duel.check_preset(p)))

    def test_no_such_scene(self):
        self.assertIn("no scene", " ".join(duel.check_preset({"booth": {"scene": "g3"}, "layers": []})))

    def test_victim_anchors_without_the_scene(self):
        self.assertIn("2-fighter scene", " ".join(duel.check_preset({"booth": {"scene": "bare"}, "layers": [{"point": "@victimChest"}]})))

    def test_the_kit_probe_preset(self):
        # a calibration probe is a kit instrument (kit/vfx/probes), never a piece in the effects folder: it ships with
        # the kit, so it is always here, and the quality locks never see it as a new unjudged preset
        path = os.path.join(ROOT, "kit", "vfx", "probes", "g2_duel.json")
        self.assertTrue(os.path.isfile(path), "the G2 calibration probe ships with the kit")
        self.assertFalse(os.path.isfile(os.path.join(ROOT, "assets", "effects", "g2_duel.json")),
                         "the probe is not a piece: not in the effects folder")
        with open(path, encoding="utf-8") as fh:
            p = json.load(fh)
        self.assertEqual(duel.check_preset(p), [])
        blood = [el.get("name") for el in p["layers"] if isinstance(el.get("color"), list) and len(el["color"]) == 3
                 and el["color"][0] > 150 and el["color"][1] < 60 and el["color"][2] < 60]
        self.assertEqual(blood, [], "light only: no blood-red layer")


class BothRenderersBuildIt(unittest.TestCase):
    """the scene is built from the FILE on both sides (not hand-placed twice): the player's and the booth's builders
    read the scene's arena / fighters / anchors, and kit vfx play / booth carry the file to them"""

    def test_player(self):
        js = read("kit", "vfx", "player", "player.js")
        self.assertIn("buildScene(sc)", js)
        self.assertIn("this.bundle.scene", js)
        self.assertIn("this.sceneAnchors[name]", js)  # "@victimChest" resolves to the scene's point
        self.assertIn("this.actor.victim = this.victim", js)  # "@victim" is the victim's body (highlight)
        self.assertIn("scene: player.metrics.scene", read("kit", "vfx", "player", "index.html"))

    def test_booth(self):
        lu = read("kit", "vfx", "booth.luau")
        self.assertIn("local function buildScene(root: Instance, sc: any)", lu)
        self.assertIn("Enum.HumanoidRigType.R6", lu)
        self.assertIn("sceneAnchors = buildScene(root, job.scene)", lu)

    def test_play_and_booth_carry_it(self):
        lu = read("kit", "cmd", "content.luau")
        self.assertIn("local function vfxScene(", lu)
        self.assertIn("scene = scene, -- the scene the player builds", lu)
        self.assertIn("job.scene = scene", lu)


if __name__ == "__main__":
    unittest.main()
