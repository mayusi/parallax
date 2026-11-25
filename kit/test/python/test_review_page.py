"""kit review (kit/cmd/review.luau) end to end, on the kit's own fixture project (kit/selftest/sheet: "sheetgun"):
the page is served, a model sheet that waits for the owner is approved BY A CLICK, and that click's record is the one
the 3D stage lock reads (Locks.stage through the page's own next answer, and the fixture's locks file) - while the
project's real board/locks.json gets no record of it. What the page must refuse is refused: any answer without the
page's token, a write from another origin, a picture no stage names (a real PNG too), an approval with no words, an
approval of a sheet that is no longer the one the page showed. A --dry page records nothing, also when --dry is
given a value. The approval command itself refuses a sheet that is not the one it is told was looked at (--expect),
and a fixture's folder never rides into the project's own record, however that record's path is spelled.
The VFX side of the page (a beat chart, a style sheet) is kit/test/python/test_review_page_vfx.py.

Needs lune (the kit's own runner); the fixture copy lives in build/selftest/review_page_<this run>/ (git-ignored). The running
page and the fixture are kit/selftest/review/reviewpage.py's (the selftest cases use the same). The clicked approval
runs the kit's own `approve`, which also writes its run verdict .verify/approve.json (git-ignored run state).
"""

import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "selftest", "review"))
import reviewpage as RP  # noqa: E402


def real_record():
    """the project's own record of the fixture piece (there must never be one)"""
    try:
        data = json.load(open(os.path.join("board", "locks.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return ((data.get("stages") or {}).get("3d") or {}).get("sheetgun")


def stored():
    return json.load(open(RP.LOCKS, encoding="utf-8"))


@unittest.skipUnless(RP.lune(), "lune not found")
class TestReviewPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.here = os.getcwd()
        os.chdir(RP.ROOT)
        cls.drawn = RP.fixture()
        cls.page = RP.sheetgun()

    @classmethod
    def tearDownClass(cls):
        cls.page.stop()
        RP.done()
        os.chdir(cls.here)

    def setUp(self):
        # every case starts from a record with no approval in it, in whatever order the cases run (the page reads the
        # record again at every look)
        RP.forget(RP.LOCKS)

    def test_1_the_page_is_served_with_its_own_token_and_the_stages_in_order(self):
        self.assertTrue(self.page.token, "no token in the served page")
        self.assertNotIn(b"__REVIEW_TOKEN__", self.page.page)
        # nothing from anywhere else is loaded or called by the page, and its token is not sent on as a referrer
        headers = self.page.call("/", token=False)[2]
        self.assertIn("default-src 'self'", headers.get("content-security-policy", ""))
        self.assertIn("connect-src 'self'", headers.get("content-security-policy", ""))
        self.assertEqual(headers.get("referrer-policy"), "no-referrer")
        # ... and it is never shown inside another page's frame: a framed page passes every other check (its
        # requests are its own), so the click would be his, on something he cannot see
        self.assertIn("frame-ancestors 'none'", headers.get("content-security-policy", ""))
        self.assertEqual(headers.get("x-frame-options"), "DENY")
        self.assertEqual(self.page.call("/", token=False, headers={"Sec-Fetch-Dest": "iframe"})[0], 403)
        self.assertEqual(self.page.call("/", token=False, headers={"Sec-Fetch-Dest": "document"})[0], 200)
        data = self.page.review()
        self.assertEqual((data["lane"], data["name"], data["dry"]), ("3d", "sheetgun", False))
        self.assertEqual([s["key"] for s in data["stages"]], ["sheet", "blockout", "builds", "final"])
        sheet = data["stages"][0]
        self.assertEqual(sheet["state"], "waiting", self.drawn)            # drawn, and nobody has said yes
        self.assertEqual(sheet["actions"], ["approve", "redo"])
        self.assertTrue(sheet["pictures"] and sheet["pictures"][0]["path"].endswith("sheetgun.sheet.png"))
        self.assertTrue(sheet["seen"].startswith("sheet:") and len(sheet["seen"]) > len("sheet:"))
        # a click names the sheet's id AND its picture file as it was: the same sheet written again is another look
        self.assertTrue(sheet["seen"].startswith(sheet["expect"] + "|") and "sheetgun.sheet.png@" in sheet["seen"])
        blockout = data["stages"][1]
        self.assertEqual(blockout["state"], "missing")                      # nothing true to show him yet
        self.assertEqual((blockout["actions"], blockout["pictures"]), ([], []))   # lists, even when empty
        self.assertEqual(blockout["make"], "lune run kit blockout sheetgun")

    def test_2_nothing_is_told_or_served_without_the_pages_token(self):
        for path in ("/api/review", "/api/stamp"):
            self.assertEqual(self.page.call(path, token=False)[0], 403, path)
            self.assertEqual(self.page.call(path, token="0" * 48)[0], 403, path)
        self.assertEqual(self.page.call("/api/review", headers={"Host": "127.0.0.1.evil.example"})[0], 403)
        named = self.page.stage("sheet")["pictures"][0]["path"]
        status, body, headers = self.page.file(named)
        self.assertEqual((status, headers.get("content-type")), (200, "image/png"))
        self.assertEqual(body[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(self.page.file(named, key=False)[0], 404)          # the picture itself, without the token
        # a REAL picture no stage names: the list of named pictures is what refuses it, not its file type
        other = RP.MODELS + "/not_named.png"
        shutil.copyfile(named, other)
        self.assertEqual(self.page.file(other)[0], 404)
        for path in ("board/locks.json", "kit/init.luau", RP.MODELS + "/sheetgun.brief.md",
                     RP.MODELS + "/../models/sheetgun.sheet.png", named.replace("/", "\\"), "C:/Windows/win.ini"):
            self.assertEqual(self.page.file(path)[0], 404, path)

    def test_3_a_write_needs_the_pages_token_and_the_pages_origin(self):
        yes = {"stage": "sheet", "action": "approve", "words": "must not be recorded"}
        self.assertEqual(self.page.act(yes, token=False)[0], 403)
        self.assertEqual(self.page.act(yes, token="0" * 48)[0], 403)
        self.assertEqual(self.page.act(yes, origin="http://evil.example")[0], 403)
        self.assertEqual(stored()["stages"], {})                            # none of them wrote
        self.assertEqual(self.page.stage("sheet")["state"], "waiting")

    def test_4_what_is_not_offered_or_not_his_words_or_not_what_he_saw_is_refused(self):
        status, answer = self.page.act({"stage": "blockout", "action": "approve", "words": "yes"})
        self.assertEqual(status, 400)
        self.assertIn("nothing to approve here", answer["message"])
        self.assertEqual(self.page.act({"stage": "nope", "action": "approve", "words": "yes"})[0], 404)
        self.assertEqual(self.page.act({"stage": "sheet", "action": "redo", "words": ""})[0], 400)
        # an approval with no words: the page invents none for him
        status, answer = self.page.act({"stage": "sheet", "action": "approve", "words": "  "})
        self.assertEqual(status, 400)
        self.assertIn("in your words", answer["message"])
        # an approval of a sheet that is not the one the page showed (it was redrawn while he was typing)
        status, answer = self.page.act({"stage": "sheet", "action": "approve", "words": "yes", "seen": "sheet:an-older-sheet"})
        self.assertEqual((status, answer.get("stale")), (409, True))
        status, answer = self.page.act({"stage": "sheet", "action": "approve", "words": "yes", "seen": None})
        self.assertEqual(status, 409)                                       # a click that does not say what it saw
        self.assertEqual(stored()["stages"], {})

    def test_4b_a_dry_page_records_nothing_also_when_dry_is_given_a_value(self):
        dry = RP.sheetgun("--dry", "yes")                                   # (--dry yes reads as a flag WITH a value)
        try:
            self.assertTrue(dry.review()["dry"])
            before, tasks = open(RP.LOCKS, "rb").read(), sorted(os.listdir(os.path.join("board", "tasks")))
            status, answer = dry.act({"stage": "sheet", "action": "approve", "words": "yes, this is the gun"})
            self.assertEqual((status, answer.get("dry")), (200, True))
            self.assertIn('lune run kit approve 3d sheetgun "yes, this is the gun" --by owner --stage sheet --via review-page',
                          answer["message"])
            status, answer = dry.act({"stage": "sheet", "action": "redo", "words": "the grip is too short"})
            self.assertEqual((status, answer.get("dry")), (200, True))
            self.assertIn('lune run kit task rework "sheetgun - The model sheet: the grip is too short" --area 3d', answer["message"])
            self.assertEqual(open(RP.LOCKS, "rb").read(), before)           # the approval was not written ...
            self.assertEqual(sorted(os.listdir(os.path.join("board", "tasks"))), tasks)    # ... nor a board card
        finally:
            dry.stop()

    def test_5_an_approval_clicked_on_the_page_is_the_record_the_lock_reads(self):
        sheet_id = json.load(open(os.path.join(RP.PROJ, "assets", "models", "sheetgun.sheet.json"), encoding="utf-8"))["id"]
        status, answer = self.page.act({"stage": "sheet", "action": "approve", "words": "yes, this is the gun"})
        self.assertEqual(status, 200, answer)
        self.assertIn("recorded as the owner's", answer["message"])
        self.assertIn("lune run kit approve 3d sheetgun", answer["ran"])    # the kit's own command, nothing else
        rec = stored()["stages"]["3d"]["sheetgun"]["sheet"]
        self.assertEqual((rec["by"], rec["words"], rec["id"], rec["stage"]), ("owner", "yes, this is the gun", sheet_id, "sheet"))
        self.assertEqual(rec["via"], "review-page")                         # a click says so; a typed approval has no "via"
        after = self.page.stage("sheet")                                    # the page reads it back through Locks.stage
        self.assertEqual((after["state"], after["record"]["words"]), ("approved", "yes, this is the gun"))
        self.assertEqual(after["actions"], ["redo"])                        # a yes is not asked for twice
        self.assertIsNone(real_record())                                    # the project's own record has none of it
        # the command was told what the page showed (it refuses when that is no longer what is there: test_7)
        self.assertIn(f"--expect sheet:{sheet_id}:", answer["ran"])

    def test_6_a_fixtures_folder_never_goes_with_the_projects_own_record(self):
        said = RP.kit("review", "sheetgun", "--models", RP.MODELS, "--stages")
        self.assertIn("--models and --locks go together", said)
        # (a folder with NO sheet in it: were the refusal ever lost, there would still be nothing to record)
        said = RP.kit("approve", "3d", "sheetgun", "a typed yes", "--by", "owner", "--stage", "sheet",
                      "--models", "build/selftest/no_such_project/assets/models")
        self.assertIn("--models is for a fixture project's piece", said)
        # a fixture's record is a plain file under build/: the project's own record under ANY spelling is refused (one
        # file has more spellings on Windows than a comparison can list), and so is a record anywhere else
        own = os.path.join(RP.ROOT, "board", "locks.json")
        for spelled in ("./board/locks.json", "BOARD\\locks.json", "build/../board/locks.json", own, own.replace("\\", "/"),
                        "board/locks.json.", "board/locks.json::$DATA", "kit/selftest/sheet/locks.json"):
            said = RP.kit("review", "sheetgun", "--models", RP.MODELS, "--locks", spelled, "--stages")
            self.assertIn("is not a fixture's own record", said, spelled)
            # (a models folder with NO sheet in it: were the refusal ever lost, nothing could be recorded)
            said = RP.kit("approve", "3d", "sheetgun", "a typed yes", "--by", "owner", "--stage", "sheet",
                          "--models", "build/selftest/no_such_project/assets/models", "--locks", spelled)
            self.assertIn("is not a fixture's own record", said, spelled)
        # a path plainly under build/ whose REAL place is some project's record is refused by where it leads (a
        # folder under build/ can be a junction). Shown here with a real folder of that name - no junction to the
        # project's own board/ is ever made by a test: what deletes the fixture could follow it
        elsewhere = os.path.join(RP.PROJ, "elsewhere", "board")
        os.makedirs(elsewhere, exist_ok=True)
        RP.forget(os.path.join(elsewhere, "locks.json"))
        said = RP.kit("review", "sheetgun", "--models", RP.MODELS, "--locks",
                      RP.PROJ.replace(os.sep, "/") + "/elsewhere/board/locks.json", "--stages")
        self.assertIn("is not a fixture's own record", said)
        self.assertIsNone(real_record())

    def test_7_the_approval_command_refuses_what_was_not_looked_at(self):
        # between the page's look and the command's own read the sheet may be drawn again: the command is told what
        # was looked at (--expect) and records nothing for anything else
        looked = self.page.stage("sheet")["expect"]                       # what the page tells the command
        typed = ("approve", "3d", "sheetgun", "yes, this is the gun", "--by", "owner", "--stage", "sheet",
                 "--models", RP.MODELS, "--locks", RP.LOCKS)
        said = RP.kit(*typed, "--expect", "sheet:an-older-sheet:")
        self.assertIn("is not the one that was looked at", said)
        self.assertEqual(stored()["stages"], {})
        said = RP.kit(*typed, "--expect", looked)
        self.assertIn("recorded as the owner's", said)
        self.assertEqual(stored()["stages"]["3d"]["sheetgun"]["sheet"]["words"], "yes, this is the gun")
        self.assertIsNone(real_record())


if __name__ == "__main__":
    unittest.main()
