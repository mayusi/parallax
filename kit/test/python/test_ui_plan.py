"""kit ui plan: the hero route as seven LOCKED stages — refs_too_small (stills under 1080p lock everything after refs),
the right screen type, the owner's waiver, a typed hero piece and an all-typed medium named in the pieces stage, and
the piece routes read from sidecars (kit/ui/routes.py)"""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
UI = os.path.join(HERE, "..", "..", "ui")


def _load(name):
    spec = importlib.util.spec_from_file_location(f"kit_ui_{name}", os.path.join(UI, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


plan = _load("plan")
refsdb = _load("refsdb")
routes = _load("routes")


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.specs = os.path.join(self.root, "ui")
        self.refs = os.path.join(self.specs, "refs")
        os.makedirs(os.path.join(self.specs, "identities"))
        os.makedirs(os.path.join(self.refs, "game"))
        os.makedirs(os.path.join(self.specs, "art", "game"))
        ident = {"name": "game", "fonts": {"font": "Oswald"}, "shape": {"line": "#000000"}, "bans": ["x"], "minimums": {"text": 14},
                 "references": [{"image": os.path.join(self.refs, "game", "a.png").replace("\\", "/"), "measured": {"x": 1}}]}
        write(os.path.join(self.specs, "identities", "game.json"), json.dumps(ident))
        write(os.path.join(self.refs, "game", "REFS.md"), "# game\n- a.png: the HUD in a fight\n- b.png: the HUD in a fight\n")
        # a hero HUD whose hero word is lettered (letter sidecar) and whose small count is typed
        write(os.path.join(self.specs, "art", "game", "w_go.letter.json"), "{}")
        Image.new("RGBA", (40, 20)).save(os.path.join(self.specs, "art", "game", "w_go.png"))
        self.spec = {"name": "Hud", "kind": "hud", "quality": "hero", "identity": "game", "focus": "Root.Go",
                     "root": {"type": "panel", "name": "Root", "children": [
                         {"type": "label", "name": "Go", "text": "GO", "lettering": True},
                         {"type": "label", "name": "Count", "text": "12"}]}}
        write(os.path.join(self.specs, "Hud.json"), json.dumps(self.spec))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def stills(self, size, kind="hud"):
        for f in ("a.png", "b.png"):
            Image.new("RGB", size).save(os.path.join(self.refs, "game", f))
        man = refsdb.index(os.path.join(self.refs, "game"))
        for s in man["stills"]:
            s.update({"kind": kind, "typed": "tag"})
        refsdb.save_manifest(os.path.join(self.refs, "game"), man)

    def run_plan(self):
        stages, nxt = plan.plan("Hud", self.specs, os.path.join(self.root, "models"), os.path.join(self.root, "build"),
                                os.path.join(self.root, "starter"), os.path.join(self.root, "v.json"), self.refs.replace("\\", "/"))
        return {s["stage"]: s for s in stages}, nxt

    def test_refs_too_small_locks_every_later_stage(self):
        self.stills((960, 540))
        st, nxt = self.run_plan()
        self.assertFalse(st["refs"]["done"])
        self.assertIn("0 at >= 1080p", st["refs"]["checks"][0]["detail"])
        for later in ("identity", "pieces", "assemble", "look", "judge", "promote"):
            self.assertTrue(st[later]["locked"], later)
        self.assertIn("kit ui refs game", nxt)

    def test_1080p_stills_of_the_screen_type_open_the_lock(self):
        self.stills((1920, 1080))
        st, _ = self.run_plan()
        self.assertTrue(st["refs"]["done"])
        self.assertFalse(st["identity"]["locked"])

    def test_1080p_stills_of_another_screen_type_do_not(self):
        self.stills((1920, 1080), kind="menu")
        st, _ = self.run_plan()
        self.assertFalse(st["refs"]["done"])
        self.assertIn("0 of this screen type (hud)", st["refs"]["checks"][0]["detail"])

    def test_the_owners_quoted_waiver_opens_it(self):
        self.stills((960, 540))
        man = refsdb.load_manifest(os.path.join(self.refs, "game"))
        man["waiver"] = {"by": "owner", "words": "the 720p stills are all there is, go", "date": "2026-10-16"}
        refsdb.save_manifest(os.path.join(self.refs, "game"), man)
        st, _ = self.run_plan()
        self.assertTrue(st["refs"]["done"])
        self.assertIn("waived", st["refs"]["checks"][0]["detail"])

    def test_pieces_name_routes_and_a_typed_hero_fails(self):
        self.stills((1920, 1080))
        st, _ = self.run_plan()
        checks = {c["check"]: c for c in st["pieces"]["checks"]}
        self.assertTrue(checks["hero piece"]["done"])
        self.assertIn("letter 1", checks["routes"]["detail"])
        self.assertIn("typed 1", checks["routes"]["detail"])
        self.spec["focus"] = "Root.Count"
        self.spec["root"]["children"][0].pop("lettering")
        write(os.path.join(self.specs, "Hud.json"), json.dumps(self.spec))
        st, _ = self.run_plan()
        checks = {c["check"]: c for c in st["pieces"]["checks"]}
        self.assertFalse(checks["hero piece"]["done"])
        self.assertFalse(checks["medium"]["done"])  # every piece typed: the AI-slop medium
        self.assertLessEqual(len(st["pieces"]["cmds"]), plan.MAX_CMDS)

    def test_routes_read_sidecars_digit_sets_and_plates(self):
        art = os.path.join(self.specs, "art")
        write(os.path.join(art, "game", "dg.glyphs.json"), "{}")
        write(os.path.join(art, "game", "gem.render.json"), "{}")
        self.assertEqual(routes.route_of("game", "dg_7", art, {})[0], "digits")
        self.assertEqual(routes.route_of("game", "gem", art, {})[0], "render")
        self.assertEqual(routes.route_of("game", "w_go", art, {})[0], "letter")
        self.assertEqual(routes.route_of("game", "pill_accent", art, {})[0], "plate")
        self.assertEqual(routes.route_of("game", "mystery", art, {})[0], "unknown")
        self.assertEqual(routes.route_of("game", "tape", art, {"tape": "torn paper drawn by a script"})[0], "drawn")
        tab = routes.table()
        self.assertEqual(tab["unknown"]["status"], "graveyard")
        self.assertTrue({"trace", "letter", "ink", "render", "smear"} <= {k for k, v in tab.items() if v["status"] == "golden"})


class TestDerived(unittest.TestCase):
    def test_derived_drops_nodes(self):
        # (StriveCombo copied a fixed node list from StriveDuel and lost every NEW piece; the check names them)
        src = {"root": {"name": "Hud", "children": [{"name": "P1", "children": [{"name": "Frame"}, {"name": "Heart"}]},
                                                    {"name": "Timer"}, {"name": "Rock", "children": [{"name": "Ink"}]}]}}
        derived = {"derived_from": "Duel", "root": {"name": "Combo", "children": [{"name": "P1", "children": [{"name": "Frame"}]},
                                                                                 {"name": "Timer"}]}}
        missing, s = plan.derived_drops(derived, src)
        self.assertIs(s, src)
        self.assertEqual(missing, ["Rock", "P1.Heart"])           # a dropped parent names its children (Rock.Ink is not listed)
        derived["drops"] = ["Rock", "Heart"]
        self.assertEqual(plan.derived_drops(derived, src)[0], [])
        self.assertEqual(plan.derived_drops(derived, None), ([], None))


class TestRefsDb(unittest.TestCase):
    def test_1080p_is_the_short_side_or_a_full_width_crop(self):
        self.assertTrue(refsdb.is_1080([1920, 1080]))
        self.assertTrue(refsdb.is_1080([1920, 950]))     # a letterboxed full-width still
        self.assertTrue(refsdb.is_1080([1200, 1200]))
        self.assertFalse(refsdb.is_1080([960, 540]))
        self.assertFalse(refsdb.is_1080([760, 940]))     # the character-action sheet the gauges plateaued on
        self.assertFalse(refsdb.is_1080(None))

    def test_words_type_a_still_only_when_they_agree(self):
        self.assertEqual(refsdb.kind_from_words("gameplay HUD with health bars"), "hud")
        self.assertEqual(refsdb.kind_from_words("the title screen menu"), "menu")
        self.assertIsNone(refsdb.kind_from_words("screenshot 4"))


if __name__ == "__main__":
    unittest.main()
