"""kit review (kit/cmd/review.luau) end to end on an EFFECT: the made project of kit/selftest/vfx/stylesheet/
madeproject.py under names of this run's own (kit/selftest/review/reviewpage.py vfx_fixture), its beat chart and its
style sheet drawn by the kit's own tools.

What a click's yes is recorded FOR is what this proves (two reviews, 2026-11-12: the page and its commands read
different folders, and a yes was bound to the preset, not to the pictures he saw):
  * the chart: approved in the folder the page read it in, for the plan the page showed; a chart re-timed since
    reads "changed", and while its picture is still of the earlier plan there is nothing to approve - it is drawn
    again first. The chart tool refuses a plan that is not the one it is told was looked at (--expect-plan).
  * the style sheet: the record names the PICTURES he saw ("drawn"). The same preset recorded again leaves a stale
    sheet (nothing to approve, no pictures shown); drawn again it has the same id and other pictures: "changed", his
    yes is asked again, a click for the old pictures is refused, and the approval command refuses what it is not
    told was looked at (--expect).
  * every record lands in the fixture's own locks file and the fixture's own chart: the project's board/locks.json
    and its own measured folder get none of it.

Needs lune and ffmpeg. The fixture's recording, chart picture and sheet stand in the project's git-ignored build/
under the run's own names and are removed at the end.
"""

import json
import os
import shutil
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "selftest", "review"))
import reviewpage as RP  # noqa: E402

PLAN = "1.20|0.00,0.50,0.00,1;0.50,0.70,0.00,0"                             # the made chart's two beats


def real_record():
    """the project's OWN record of the fixture's effect, and its own copy of the fixture's chart (there must never be
    either; other sessions write their own records into the same file, so it is not compared whole)"""
    try:
        data = json.load(open(os.path.join("board", "locks.json"), encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    found = [k for k in ("stages", "approvals", "waivers", "proposals")
             if RP.FX in ((data.get(k) or {}).get("vfx") or {}) or RP.FXSET in ((data.get(k) or {}).get("vfx") or {})]
    if os.path.isfile(os.path.join("assets", "effects", "refs_measured", RP.FXSET + ".chart.json")):
        found.append("chart")
    return found


def chart():
    return json.load(open(RP.CHART, encoding="utf-8"))


def drawn(**change):
    """what the chart's picture says it shows, changed (a picture from another folder, one with no test frame)"""
    made = json.load(open(RP.DRAWN, encoding="utf-8"))
    made.update(change)
    json.dump(made, open(RP.DRAWN, "w", encoding="utf-8"))


def set_record(step):
    """the fixture's own record of a stage of the SET (the timing animatic)"""
    data = json.load(open(RP.VFXLOCKS, encoding="utf-8"))
    return (((data.get("stages") or {}).get("vfx") or {}).get(RP.FXSET) or {}).get(step)


def style_record():
    data = json.load(open(RP.VFXLOCKS, encoding="utf-8"))
    return (((data.get("stages") or {}).get("vfx") or {}).get(RP.FX) or {}).get("style")


@unittest.skipUnless(RP.lune() and shutil.which("ffmpeg") and shutil.which("ffprobe"), "lune / ffmpeg not found")
class TestReviewPageEffect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.here = os.getcwd()
        os.chdir(RP.ROOT)
        cls.drew = RP.vfx_fixture()
        cls.page = RP.effect()

    @classmethod
    def tearDownClass(cls):
        cls.page.stop()
        RP.vfx_done()
        os.chdir(cls.here)

    def setUp(self):
        # every case starts from the made effect as it was drawn, with no approval anywhere, in whatever order the
        # cases run: the recording, the chart, both drawings and an empty record - and both drawings DID come out (a
        # case about a missing sheet must not pass because the drawing failed)
        chart_said, sheet_said = RP.vfx_fixture()
        self.assertIn(chart_said.get("status"), ("pass", "warn"), chart_said)
        self.assertEqual(sheet_said.get("status"), "pass", sheet_said)

    def tearDown(self):
        self.assertEqual(real_record(), [], "the fixture's effect was recorded in the project's own files")

    def test_the_page_shows_the_chart_and_the_sheet_it_can_say_yes_to(self):
        self.assertTrue(self.page.token, "no page: " + json.dumps(self.drew)[:400])
        data = self.page.review()
        self.assertEqual((data["lane"], data["name"]), ("vfx", RP.FX))
        self.assertEqual([s["key"] for s in data["stages"]], ["chart", "animatic", "style", "dailies", "final"])
        self.assertEqual(data["stages"][1]["state"], "missing")            # (no animatic of the set made yet)
        data["stages"].pop(1)
        chart_stage, style = data["stages"][0], data["stages"][1]
        self.assertEqual((chart_stage["state"], chart_stage["actions"]), ("waiting", ["approve", "redo"]))
        self.assertEqual(chart_stage["expect"], PLAN)                       # what the chart tool is told
        self.assertTrue(chart_stage["seen"].startswith(f"chart:{PLAN}:{PLAN}|"))    # the plan, its picture's, the file
        self.assertEqual((style["state"], style["actions"]), ("waiting", ["approve", "redo"]))
        self.assertEqual([os.path.basename(p["path"]) for p in style["pictures"]], ["beat0.png", "beat1.png"])
        sheet = json.load(open(os.path.join("build", "vfx", "stylesheet", RP.FX + ".json"), encoding="utf-8"))
        self.assertEqual(style["expect"], f"style:{sheet['id']}:{sheet['drawn']}")  # its id, and its pictures
        self.assertTrue(style["seen"].startswith(style["expect"] + "|"))
        status, body, headers = self.page.file(style["pictures"][0]["path"])
        self.assertEqual((status, body[:8]), (200, b"\x89PNG\r\n\x1a\n"))
        # the chart's picture says what it shows: this plan, drawn from the fixture's own folder, with its test frame
        made = json.load(open(RP.DRAWN, encoding="utf-8"))
        self.assertEqual((made["plan"], made["measured"], made["test"], made["guessed"]), (PLAN, RP.MEASURED, True, False))
        # the pictures shown are the very files the sheet's hash covers - a stray picture in its folder is neither
        shutil.copyfile(style["pictures"][0]["path"], os.path.join("build", "vfx", "stylesheet", RP.FX, "beat9.png"))
        stray = self.page.stage("style")
        self.assertEqual([os.path.basename(p["path"]) for p in stray["pictures"]], ["beat0.png", "beat1.png"])
        self.assertEqual((stray["state"], stray["expect"]), ("waiting", style["expect"]))

    def test_a_chart_approved_by_a_click_is_approved_where_the_page_read_it_for_the_plan_it_showed(self):
        status, answer = self.page.act({"stage": "chart", "action": "approve", "words": "yes, this timing"})
        self.assertEqual(status, 200, answer)
        self.assertIn(f"--expect-plan {PLAN}", answer["ran"])
        self.assertIn(f"--measured {RP.MEASURED}", answer["ran"])
        approved = chart()["approved"]                                      # the fixture's own chart, nobody else's
        self.assertEqual((approved["by"], approved["words"], approved["plan"], approved["via"]),
                         ("owner", "yes, this timing", PLAN, "review-page"))
        after = self.page.stage("chart")
        self.assertEqual((after["state"], after["actions"]), ("approved", ["redo"]))

    def test_a_chart_retimed_after_its_picture_is_drawn_again_before_any_yes(self):
        self.assertEqual(self.page.act({"stage": "chart", "action": "approve", "words": "yes, this timing"})[0], 200)
        shown = self.page.stage("chart")["seen"]
        plan = chart()
        plan["beats"][0]["len"] = 0.4                                       # re-timed after his yes, picture untouched
        json.dump(plan, open(RP.CHART, "w", encoding="utf-8"))
        stale = self.page.stage("chart")
        self.assertEqual((stale["state"], stale["actions"]), ("changed", []))
        self.assertIn("its picture is of an earlier plan", stale["says"])
        status, answer = self.page.act({"stage": "chart", "action": "approve", "words": "yes", "seen": shown})
        self.assertEqual(status, 400, answer)                               # nothing is offered: nothing to approve
        self.assertEqual(chart()["approved"]["plan"], PLAN)                 # his record is still for the plan he saw
        self.assertIn(RP.draw_chart().get("status"), ("pass", "warn"))
        redrawn = self.page.stage("chart")
        self.assertEqual((redrawn["state"], redrawn["actions"]), ("changed", ["approve", "redo"]))
        # a click that saw the OLD picture is refused; one that saw this one is his yes for the new plan
        status, answer = self.page.act({"stage": "chart", "action": "approve", "words": "yes", "seen": shown})
        self.assertEqual((status, answer.get("stale")), (409, True))
        self.assertEqual(self.page.act({"stage": "chart", "action": "approve", "words": "yes, shorter"})[0], 200)
        self.assertEqual(chart()["approved"]["plan"], "1.20|0.00,0.40,0.00,1;0.50,0.70,0.00,0")

    def test_the_chart_tool_refuses_a_plan_that_is_not_the_one_looked_at(self):
        said = RP.tool("chart.py", RP.FXSET, "--approve", "a typed yes", "--by", "owner", "--expect-plan", "9.99|",
                       "--measured", RP.MEASURED)
        self.assertEqual(said.get("status"), "fail")
        self.assertIn("not the chart that was looked at", said.get("summary", ""))
        self.assertNotIn("approved", chart())
        # the SAME plan drawn again with another picture (another test frame): a click that saw the old one is refused
        shown = self.page.stage("chart")["seen"]
        os.utime(os.path.join("build", "vfx", "charts", RP.FXSET + ".png"), (1_700_000_000, 1_700_000_000))
        status, answer = self.page.act({"stage": "chart", "action": "approve", "words": "yes", "seen": shown})
        self.assertEqual((status, answer.get("stale")), (409, True))
        self.assertNotIn("approved", chart())
        # the picture on this machine was drawn from ANOTHER folder's set of the same name (the picture's file is
        # one per set name): it is not this chart's, whatever its plan - on the page, and for the chart tool
        drawn(measured="assets/effects/refs_measured")
        other = self.page.stage("chart")
        self.assertEqual(other["actions"], [])
        self.assertIn("another folder's set of the same name", other["says"])
        said = RP.tool("chart.py", RP.FXSET, "--approve", "a typed yes", "--by", "owner", "--expect-plan", PLAN,
                       "--measured", RP.MEASURED)
        self.assertEqual(said.get("status"), "fail")
        self.assertIn("the picture on this machine is not of this chart", said.get("summary", ""))
        self.assertNotIn("approved", chart())
        # a picture with no test frame of the key beat, or with a key beat that was only guessed: not yet the
        # picture he is asked to approve (the owner, 2026-11-11: the chart and ONE test frame)
        drawn(measured=RP.MEASURED, test=False)
        bare = self.page.stage("chart")
        self.assertEqual(bare["actions"], [])
        self.assertIn("no test frame of the key beat", bare["says"])
        drawn(test=True, guessed=True)
        guessed = self.page.stage("chart")
        self.assertEqual(guessed["actions"], [])
        self.assertIn("only guessed", guessed["says"])
        drawn(guessed=False)
        self.assertEqual(self.page.stage("chart")["actions"], ["approve", "redo"])
        # a chart picture nobody wrote down what it shows (drawn before the kit kept it): not one to say yes to
        os.remove(RP.DRAWN)
        unknown = self.page.stage("chart")
        self.assertEqual(unknown["actions"], [])
        self.assertIn("not known", unknown["says"])

    def test_a_style_sheet_approved_by_a_click_names_the_pictures_he_saw(self):
        looked = self.page.stage("style")["expect"]
        status, answer = self.page.act({"stage": "style", "action": "approve", "words": "yes, these read"})
        self.assertEqual(status, 200, answer)
        self.assertIn(f"--expect {looked}", answer["ran"])
        self.assertIn(f"--effects {RP.EFFECTS}", answer["ran"])
        rec = style_record()
        self.assertEqual((rec["by"], rec["words"], rec["stage"], rec["via"]), ("owner", "yes, these read", "style", "review-page"))
        self.assertEqual(f"style:{rec['id']}:{rec['drawn']}", looked)
        after = self.page.stage("style")
        self.assertEqual((after["state"], after["actions"]), ("approved", ["redo"]))

    def test_the_same_preset_recorded_again_is_asked_again_for_the_new_pictures(self):
        self.assertEqual(self.page.act({"stage": "style", "action": "approve", "words": "yes, these read"})[0], 200)
        first = style_record()
        old = self.page.stage("style")["seen"]
        RP.record(brighter=True)                                            # a texture changed; the preset's file did not
        stale = self.page.stage("style")
        self.assertEqual((stale["state"], stale["actions"], stale["pictures"]), ("missing", [], []))
        self.assertIn("the effect was recorded again since it was drawn", stale["says"])
        self.assertEqual(RP.draw_sheet().get("status"), "pass")
        again = self.page.stage("style")
        self.assertEqual((again["state"], again["actions"]), ("changed", ["approve", "redo"]))
        self.assertIn("drawn again since you approved it", again["says"])
        self.assertEqual(again["expect"].split(":")[1], first["id"])        # the same id ...
        self.assertNotEqual(again["expect"].split(":")[2], first["drawn"])  # ... and other pictures
        status, answer = self.page.act({"stage": "style", "action": "approve", "words": "yes", "seen": old})
        self.assertEqual((status, answer.get("stale")), (409, True))        # a click for the pictures that are gone
        self.assertEqual(style_record()["drawn"], first["drawn"])
        # the approval command itself, told it was the old pictures that were looked at: nothing recorded
        typed = ("approve", "vfx", RP.FX, "a typed yes", "--by", "owner", "--stage", "style", "--effects", RP.EFFECTS,
                 "--locks", RP.VFXLOCKS)
        self.assertIn("is not the one that was looked at",
                      RP.kit(*typed, "--expect", f"style:{first['id']}:{first['drawn']}"))
        self.assertEqual(style_record()["drawn"], first["drawn"])
        self.assertEqual(self.page.act({"stage": "style", "action": "approve", "words": "yes, the new ones"})[0], 200)
        self.assertEqual(f"style:{style_record()['id']}:{style_record()['drawn']}", again["expect"])
        self.assertEqual(self.page.stage("style")["state"], "approved")

    def test_pictures_that_are_not_the_ones_the_sheets_record_was_written_for_are_no_sheet(self):
        # a pair picture replaced after the drawing (or half of another drawing): --check reads the PICTURES
        self.assertEqual(self.page.stage("style")["state"], "waiting")    # (there IS a sheet before it is touched)
        pair = os.path.join("build", "vfx", "stylesheet", RP.FX, "beat1.png")
        shutil.copyfile(os.path.join("build", "vfx", "stylesheet", RP.FX, "beat0.png"), pair)
        swapped = self.page.stage("style")
        self.assertEqual((swapped["state"], swapped["actions"], swapped["pictures"]), ("missing", [], []))
        self.assertIn("not the ones its record was written for", swapped["says"])
        os.remove(pair)                                                     # ... or one that is gone
        gone = self.page.stage("style")
        self.assertEqual((gone["state"], gone["actions"]), ("missing", []))
        self.assertIn("no style sheet drawn on this machine yet", gone["says"])

    def test_the_timing_animatic_is_approved_by_a_click_for_the_video_he_watched(self):
        said = RP.make_animatic()
        self.assertEqual(said.get("status"), "pass", said)
        stages = {s["key"]: s for s in self.page.review()["stages"]}
        self.assertEqual(list(stages), ["chart", "animatic", "style", "dailies", "final"])
        ani = stages["animatic"]
        self.assertEqual((ani["state"], ani["actions"], ani["ref"]), ("waiting", ["approve", "redo"], RP.FXSET))
        # the video first, then each beat's page: the very files its "drawn" is the hash of
        self.assertTrue(ani["pictures"][0]["path"].endswith(f"{RP.FXSET}_side.mp4"))
        self.assertEqual([os.path.basename(p["path"]) for p in ani["pictures"][1:]], ["beat0_page.png", "beat1_page.png"])
        video = ani["pictures"][0]["path"]
        status, body, headers = self.page.file(video)
        self.assertEqual((status, headers.get("content-type"), body[4:8]), (200, "video/mp4", b"ftyp"))
        self.assertEqual(headers.get("accept-ranges"), "bytes")
        # a PART of it when a part is asked for: a browser scrubs a video (and some only play one) through Range
        status, part, headers = self.page.file(video, headers={"Range": "bytes=4-7"})
        self.assertEqual((status, part, headers.get("content-range")), (206, b"ftyp", f"bytes 4-7/{len(body)}"))
        self.assertEqual(headers.get("content-type"), "video/mp4")
        status, tail, headers = self.page.file(video, headers={"Range": f"bytes={len(body) - 10}-"})
        self.assertEqual((status, tail, headers.get("content-range")),
                         (206, body[-10:], f"bytes {len(body) - 10}-{len(body) - 1}/{len(body)}"))
        status, _, headers = self.page.file(video, headers={"Range": f"bytes={len(body)}-"})
        self.assertEqual((status, headers.get("content-range")), (416, f"bytes */{len(body)}"))
        self.assertEqual(self.page.file(video, key=False, headers={"Range": "bytes=0-9"})[0], 404)   # (still the token's)
        status, answer = self.page.act({"stage": "animatic", "action": "approve", "words": "yes, this motion"})
        self.assertEqual(status, 200, answer)
        self.assertIn(f"lune run kit approve vfx {RP.FXSET} ", answer["ran"])     # recorded under the SET's name
        rec = set_record("animatic")
        self.assertEqual((rec["by"], rec["words"], rec["stage"], rec["via"]), ("owner", "yes, this motion", "animatic", "review-page"))
        self.assertEqual(f"animatic:{rec['id']}:{rec['drawn']}", ani["expect"])
        self.assertIsNone(style_record())                                   # (the effect's own stages are another record)
        self.assertEqual(self.page.stage("animatic")["state"], "approved")
        # the chart re-timed after his yes: the animatic here is of another plan - nothing to say yes to until it is
        # made again, and then it is asked again
        plan = chart()
        plan["beats"][0]["len"] = 0.4
        json.dump(plan, open(RP.CHART, "w", encoding="utf-8"))
        stale = self.page.stage("animatic")
        self.assertEqual((stale["state"], stale["actions"], stale["pictures"]), ("missing", [], []))
        self.assertIn("re-timed", stale["says"])
        self.assertEqual(RP.make_animatic().get("status"), "pass")
        again = self.page.stage("animatic")
        self.assertEqual((again["state"], again["actions"]), ("changed", ["approve", "redo"]))
        # the approval command, told it was the first animatic that was watched: nothing recorded
        typed = ("approve", "vfx", RP.FXSET, "a typed yes", "--by", "owner", "--stage", "animatic", "--effects", RP.EFFECTS,
                 "--locks", RP.VFXLOCKS)
        self.assertIn("is not the one that was looked at", RP.kit(*typed, "--expect", ani["expect"]))
        self.assertEqual(set_record("animatic")["id"], rec["id"])
        # a scene SET with no effect yet is a piece too: its chart and its animatic, and the page ends there
        said = RP.kit("review", RP.FXSET, "--lane", "vfx", "--effects", RP.EFFECTS, "--locks", RP.VFXLOCKS, "--stages")
        self.assertIn("1. chart:", said)
        self.assertIn("2. animatic:", said)
        self.assertNotIn("style:", said)

    def test_an_effect_of_another_folder_is_never_recorded_as_this_projects(self):
        # typed without a fixture record: the project's own effects folder is the only one an approval may name.
        # (An effect that does not exist there: were this refusal ever lost, there would still be nothing the
        # command could record in the project's own board/locks.json)
        said = RP.kit("approve", "vfx", RP.FX + "_none", "a typed yes", "--by", "owner", "--stage", "style",
                      "--effects", RP.EFFECTS)
        self.assertIn("is not this project's effects folder", said)
        self.assertIn("go together", RP.kit("review", RP.FX, "--lane", "vfx", "--effects", RP.EFFECTS, "--stages"))
        self.assertIsNone(style_record())


if __name__ == "__main__":
    unittest.main()
