"""kit design explore with no local VLM (kit/tools/design.py): the ban screen is never skipped silently - every candidate
plate and every ban go to the AI client as a packet (bans_packet.json + bans_PROMPT.md); its answers come back with
--record and are held to the packet: a stale packet, an unknown candidate or ban id, `true` for an id and a malformed
answer are refused. A recorded design review is held the same way (`true` is no ban id)."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import design  # noqa: E402

BANS = ["no modern parts", "no gold leaf"]


class ExplorePacket(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = design.REPO
        design.REPO = self.tmp
        self.out = os.path.join(self.tmp, "build", "design", "Lantern")
        self.allc = [{"file": os.path.join(self.out, "A", f"plate_{i:02d}.png")} for i in range(3)]
        self.packet = design.write_explore_packet(self.out, "Lantern", self.allc, BANS)

    def tearDown(self):
        design.REPO = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def answers(self, data):
        p = os.path.join(self.tmp, "answers.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(data if isinstance(data, str) else json.dumps(data))
        return design.explore_answers(self.out, p, self.allc, BANS)

    def test_the_packet_holds_every_candidate_and_every_ban_as_a_question(self):
        with open(self.packet, encoding="utf-8") as fh:
            p = json.load(fh)
        self.assertEqual([c["file"] for c in p["candidates"]],
                         [f"build/design/Lantern/A/plate_{i:02d}.png" for i in range(3)])
        self.assertEqual([q["ban"] for q in p["bans"]], BANS)
        with open(os.path.join(self.out, "bans_PROMPT.md"), encoding="utf-8") as fh:
            prompt = fh.read()
        self.assertIn("lune run kit design explore Lantern --record", prompt)
        self.assertIn(design.ban_question(BANS[0]), prompt)

    def test_answers_mark_the_candidates_that_break_a_ban(self):
        broken, problem = self.answers({"broken": {"1": [0, 1]}})
        self.assertIsNone(problem)
        self.assertEqual(broken, {"build/design/Lantern/A/plate_01.png": BANS})
        broken, problem = self.answers({"broken": {}})
        self.assertIsNone(problem)
        self.assertEqual(broken, {})

    def test_bad_answers_are_refused(self):
        for bad in ({"broken": {"9": [0]}},           # no such candidate
                    {"broken": {"0": [5]}},           # no such ban
                    {"broken": {"0": [True]}},        # true is no id
                    {"broken": {"0": 0}},             # not a list
                    {"broken": [0]},                  # not a map
                    [1, 2],                           # not an object
                    "{ not json"):
            broken, problem = self.answers(bad)
            self.assertIsNotNone(problem, bad)
            self.assertEqual(broken, {})

    def test_a_packet_for_other_plates_or_bans_is_stale(self):
        moved = self.allc + [{"file": os.path.join(self.out, "B", "plate_00.png")}]
        p = os.path.join(self.tmp, "answers.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"broken": {}}, fh)
        self.assertIn("other plates", design.explore_answers(self.out, p, moved, BANS)[1])
        self.assertIn("other plates", design.explore_answers(self.out, p, self.allc, BANS + ["no rust"])[1])

    def test_valid_ids_drops_true_and_strangers(self):
        self.assertEqual(design.valid_ids([0, True, 2, "1", 7], range(3)), ([0, 2], [True, "1", 7]))
        self.assertEqual(design.valid_ids(3, range(3)), ([], [3]))


class ExploreScreenEndToEnd(unittest.TestCase):
    """the screening step and the Sheets as cmd_explore runs them, on real plate files (no drawing, no VLM)"""

    def setUp(self):
        from PIL import Image
        self.tmp = tempfile.mkdtemp()
        self.saved = design.REPO
        design.REPO = self.tmp
        self.out = os.path.join(self.tmp, "build", "design", "Lantern")
        self.folder = os.path.join(self.tmp, "assets", "models", "direction")
        os.makedirs(self.folder)
        self.allc = []
        for i in range(3):
            f = os.path.join(self.out, "A", f"plate_{i:02d}.png")
            os.makedirs(os.path.dirname(f), exist_ok=True)
            Image.new("RGB", (8, 8), (40 * i, 0, 0)).save(f)
            self.allc.append({"file": f})
        self.rows = [{"letter": "A", "elites": [self.allc[1]], "sheet": "sheets/Lantern_A.png"}]
        sys.path.insert(0, os.path.join(HERE, "..", "..", "vision"))
        import vlm
        self.no_vlm = mock.patch.object(vlm, "installed", return_value=False)
        self.no_vlm.start()

    def tearDown(self):
        self.no_vlm.stop()
        design.REPO = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sheet(self):
        return os.path.join(os.path.dirname(self.folder), "sheets", "Lantern_A.png")

    def answers(self, data):
        p = os.path.join(self.tmp, "answers.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return p

    def test_no_vlm_writes_the_packet_and_no_sheet(self):
        screen, pending, problem = design.screen_candidates([], BANS, self.allc, self.out, "Lantern")
        self.assertIsNone(problem)
        self.assertTrue(screen.startswith("pending"))
        self.assertTrue(os.path.isfile(pending))
        self.assertEqual(design.write_sheets(self.rows, self.folder, [], pending), 0)
        self.assertFalse(os.path.isfile(self.sheet()))

    def test_recorded_answers_drop_the_breakers_and_the_sheet_is_written(self):
        design.screen_candidates([], BANS, self.allc, self.out, "Lantern")
        rec = self.answers({"broken": {"2": [1]}})
        screen, pending, problem = design.screen_candidates(["--record", rec], BANS, self.allc, self.out, "Lantern")
        self.assertIsNone(problem)
        self.assertIsNone(pending)
        self.assertEqual(self.allc[2]["bans_broken"], [BANS[1]])
        self.assertEqual(self.allc[0]["bans_broken"], [])
        self.assertEqual(design.write_sheets(self.rows, self.folder, [], pending), 1)
        self.assertTrue(os.path.isfile(self.sheet()))

    def test_a_plate_redrawn_under_the_same_name_makes_the_packet_stale(self):
        from PIL import Image
        design.screen_candidates([], BANS, self.allc, self.out, "Lantern")
        Image.new("RGB", (8, 8), (0, 200, 0)).save(self.allc[0]["file"])  # (same name, another picture)
        rec = self.answers({"broken": {}})
        screen, pending, problem = design.screen_candidates(["--record", rec], BANS, self.allc, self.out, "Lantern")
        self.assertIn("other plates", problem)
        self.assertIsNone(screen)

    def test_no_screen_is_a_choice_that_says_so(self):
        screen, pending, problem = design.screen_candidates(["--no-screen"], BANS, self.allc, self.out, "Lantern")
        self.assertEqual((screen, pending, problem), ("skipped (--no-screen)", None, None))
        self.assertFalse(os.path.isfile(design.explore_packet_path(self.out)))

    def test_record_with_fresh_or_n_is_refused_before_anything_is_drawn(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = design.cmd_explore(["Lantern", "--record", "a.json", "--fresh"])
        self.assertEqual(code, 1)
        self.assertIn("--record answers the plates", json.loads(buf.getvalue().strip().splitlines()[-1])["summary"])

    def test_record_never_draws_whatever_n_says(self):
        # (a packet from an `--n 6` run, answered without --n: the default 12 must not top the plates up first)
        self.assertFalse(design.must_draw(["--record", "a.json"], 6, 12, "A", []))
        self.assertFalse(design.must_draw(["--record", "a.json", "--n", "20"], 6, 20, "A", []))
        self.assertTrue(design.must_draw([], 6, 12, "A", []))
        self.assertTrue(design.must_draw(["--fresh"], 12, 12, "B", ["B"]))
        self.assertFalse(design.must_draw(["--fresh"], 12, 12, "A", ["B"]))
        self.assertFalse(design.must_draw([], 12, 12, "A", []))


class ReviewRecord(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved = design.REPO
        design.REPO = self.tmp
        out = os.path.join(self.tmp, "build", "design", "Lantern")
        os.makedirs(out)
        with open(os.path.join(out, "review_lantern_packet.json"), "w", encoding="utf-8") as fh:
            json.dump({"questions": {"bans": [{"id": 0, "ban": BANS[0]}, {"id": 1, "ban": BANS[1]}],
                                     "pillars": [{"id": 0, "pillar": "reads as a lantern"}]}}, fh)

    def tearDown(self):
        design.REPO = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def record(self, verdict):
        p = os.path.join(self.tmp, "verdict.json")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(verdict if isinstance(verdict, str) else json.dumps(verdict))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = design.cmd_review_record(["Lantern", "--asset", "lantern", "--record", p])
        return code, json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_true_a_list_id_and_a_non_object_are_refused(self):
        for bad in ({"bans_broken": [True]}, {"bans_broken": [[0]]}, {"pillars_missed": [3]}, [0], "nope"):
            code, out = self.record(bad)
            self.assertEqual(code, 1, bad)
            self.assertEqual(out["status"], "fail")

    def test_a_good_verdict_is_recorded(self):
        code, out = self.record({"bans_broken": [1], "pillars_missed": []})
        self.assertEqual(out["review"]["bans_broken"], [BANS[1]])

    def test_an_empty_object_is_no_answer(self):
        for partial in ({}, {"bans_broken": []}, {"pillars_missed": []}):
            code, out = self.record(partial)
            self.assertEqual(code, 1, partial)
            self.assertIn("both answers", out["summary"])

    def test_answers_about_an_older_build_are_refused(self):
        build = os.path.join(self.tmp, "build", "models", "lantern.blend")
        os.makedirs(os.path.dirname(build))
        with open(build, "wb") as fh:
            fh.write(b"the build the views were made from")
        packet = os.path.join(self.tmp, "build", "design", "Lantern", "review_lantern_packet.json")
        with open(packet, encoding="utf-8") as fh:
            p = json.load(fh)
        p.update(build="build/models/lantern.blend", build_sha256=design.file_sha(build))
        with open(packet, "w", encoding="utf-8") as fh:
            json.dump(p, fh)
        code, _ = self.record({"bans_broken": [], "pillars_missed": []})
        self.assertEqual(code, 0)
        with open(build, "wb") as fh:
            fh.write(b"rebuilt")
        code, out = self.record({"bans_broken": [], "pillars_missed": []})
        self.assertEqual(code, 1)
        self.assertIn("rebuilt since the packet", out["summary"])


if __name__ == "__main__":
    unittest.main()
