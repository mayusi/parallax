"""kit/world/plan.py - the world pilot of "answer the lessons before building": the lessons stage is to do without a
sheet, partial until `kit world lessons <Name>` passes the sheet's very text (kit/lib/answers.luau keeps its digest in
board/answers.json), and done for that text only - one edit after the check and it is partial again. The check itself
lives in Luau alone; the digest is the same on both sides (the pinned values are kit/lib/vault.luau Vault.digest's,
asserted again in kit/test/spec/answers.spec.luau).
Run: python kit/test/python/run.py -k world_lessons"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "world"))
# kit/world/plan.py is loaded BY PATH under its own name: `import plan` hands back kit/tools/plan.py whenever another
# test file of the same process imported that one first (test_sheet, test_pipeline_plan: one pytest process over the
# folder failed every test here, 2026-11-13; kit/test/python/run.py gives each file its own interpreter and never saw it)
_spec = importlib.util.spec_from_file_location("kit_world_plan", os.path.join(ROOT, "kit", "world", "plan.py"))
WP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(WP)

SHEET = """# Town - the world lessons, answered before building (lune run kit world lessons Town)

## Lessons applied

<!-- ANSWER L-world-aaaaaa: terrain from rivers -->

- L-world-aaaaaa: the valleys are carved by the river painter before any dressing
"""


class WorldLessonsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "Town.lessons.md")
        self.record = os.path.join(self.tmp.name, "answers.json")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text):
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def passed(self, text):
        with open(self.record, "w", encoding="utf-8") as f:
            json.dump({WP.answers_key(self.path): {"answered": WP.digest(text.encode("utf-8"))}}, f)

    def test_no_sheet_is_to_do(self):
        self.assertEqual(WP.lessons_state(self.path, self.record), "to do")

    def test_a_sheet_never_checked_is_partial_however_well_it_reads(self):
        self.write(SHEET)
        self.assertEqual(WP.lessons_state(self.path, self.record), "partial")

    def test_done_for_the_text_that_passed_only(self):
        self.write(SHEET)
        self.passed(SHEET)
        self.assertEqual(WP.lessons_state(self.path, self.record), "done")
        self.write(SHEET.replace("<!-- ANSWER L-world-aaaaaa: terrain from rivers -->\n", ""))
        self.assertEqual(WP.lessons_state(self.path, self.record), "partial")

    def test_line_ends_do_not_matter(self):
        self.write(SHEET.replace("\n", "\r\n"))
        self.passed(SHEET)
        self.assertEqual(WP.lessons_state(self.path, self.record), "done")

    def test_a_broken_record_is_partial_not_a_crash(self):
        self.write(SHEET)
        with open(self.record, "w", encoding="utf-8") as f:
            f.write("[1, 2")
        self.assertEqual(WP.lessons_state(self.path, self.record), "partial")

    def test_the_digest_is_the_luau_one(self):
        self.assertEqual(WP.digest(b"abc\n"), "7c93edf5")
        self.assertEqual(WP.digest(b"a\r\nb"), WP.digest(b"a\nb"))
        self.assertEqual(WP.digest("café ✓\n".encode("utf-8")), "3abb63b6")


class LayoutExamplesTest(unittest.TestCase):
    """kit world plan offers the past house layouts as examples to a town / interior world only (sprint 5): an arena or
    an island shares generic words with any layout, so the world's family (kit/lib/families.luau) decides"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        os.makedirs(os.path.join("games", "G", "assets", "worlds", "layouts"))
        with open(os.path.join("games", "G", "assets", "worlds", "layouts", "inn.layout.json"), "w", encoding="utf-8") as f:
            json.dump({"about": "a coaching inn by the market street", "building": {"front": 9.0, "depth": 12.0},
                       "floors": [{"rooms": [{"name": "taproom", "purpose": "tavern"}, {"name": "kitchen"}]},
                                  {"rooms": [{"name": "bedchamber", "purpose": "sleeping"}]}]}, f)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_a_town_world_is_offered_the_layouts_in_one_line_each(self):
        ex = WP.layout_examples("games/G", "Market", {"_about": "a market street with an inn"}, family="town")
        self.assertEqual(len(ex), 1)
        self.assertIn("9.0 x 12.0 m, 2 floor(s), 3 room(s) (tavern, kitchen, sleeping)", ex[0])

    def test_an_arena_or_no_family_gets_none(self):
        self.assertEqual(WP.layout_examples("games/G", "Pit", {"_about": "a market inn arena"}, family="arena"), [])
        self.assertEqual(WP.layout_examples("games/G", "Pit", {"_about": "a market inn"}, family=None), [])


if __name__ == "__main__":
    unittest.main()
