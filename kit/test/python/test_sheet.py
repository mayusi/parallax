"""The two things the owner approves before a 3D piece is detailed (kit/tools/sheet.py, kit/tools/blockout.py) and
their stages in kit plan (kit/tools/plan.py): a hero feature nobody can model from its pictures holds the sheet, each
with its reason; the sheet's id follows everything it shows, so an approval of an older sheet stops counting; the
blockout is of ONE sheet and stays approved while the shape is detailed; a build says when the size moved from it."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
for _p in ("blender", "tools"):
    sys.path.insert(0, os.path.join(ROOT, "kit", _p))
import blockout as BO  # noqa: E402
import plan as PL  # noqa: E402
import rbx_plan as P  # noqa: E402
import sheet as SH  # noqa: E402

FIXTURE = os.path.join(ROOT, "kit", "selftest", "sheet")

BRIEF = """# x — the brief
- what: a block blaster
- end goal: game
- quality: {tier}
- quality bar: https://example.org/a
- style: stylised
- view: first person
- function: static
- moving parts: none
- extras: none
- references: refs/x_side.png
- ownership: the owner's own
- draft: none — a hard-surface block
- hero features:
  1. glow strip | code | the cyan strip along the body | {picture} {box} | 30 mm
  2. grip | code | the dark grip | {picture} 285,91,317,150 | 20 mm

- parts plan:
  1. Body | code: a.box with rounded edges + the strip as its own part | the side picture | dark coat
"""


class Project:
    """a temporary project with a REAL picture, its trace and a brief: a sheet can be drawn from it"""

    def __init__(self, tier="hero", box="206,60,296,68"):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "assets", "models"))
        os.makedirs(os.path.join(self.root, "refs"))
        self.picture = os.path.join(self.root, "refs", "x_side.png").replace("\\", "/")
        self.draw()
        self.write("assets/models/x_side.trace.json", {
            "source": self.picture, "front": "left", "height_ratio": 108 / 306,
            "frame": {"x0": 20.0, "y1": 150.0, "length_px": 306.0}, "outline": [[0, 0], [1, 0], [1, 0.35], [0, 0.35]]})
        self.brief(tier, box)

    def draw(self, strip=(26, 204, 242)):
        im = Image.new("RGB", (400, 160), (235, 235, 235))
        d = ImageDraw.Draw(im)
        d.rectangle((166, 42, 325, 91), fill=(46, 48, 56))
        d.rectangle((206, 60, 295, 67), fill=strip)
        d.rectangle((285, 93, 316, 149), fill=(30, 30, 33))
        im.save(self.picture)

    def brief(self, tier="hero", box="206,60,296,68"):
        self.write("assets/models/x.brief.md", BRIEF.format(tier=tier, picture=self.picture, box=box))

    def write(self, rel, data):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(data if isinstance(data, str) else json.dumps(data))
        return path

    def run(self, module, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = module.main(["x", "--root", self.root, *args])
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def approve(self, step, art_id, by="owner"):
        path = os.path.join(self.root, "board", "locks.json")
        data = json.load(open(path, encoding="utf-8")) if os.path.isfile(path) else {}
        data.setdefault("stages", {}).setdefault("3d", {}).setdefault("x", {})[step] = {
            "by": by, "words": "looks right", "date": "2026-11-11", "id": art_id}
        self.write("board/locks.json", data)

    def stages(self):
        return {st["key"]: st for st in PL.assess(PL.facts("x", self.root))}

    def close(self):
        self.tmp.cleanup()


class TestSheet(unittest.TestCase):
    def setUp(self):
        self.p = Project()

    def tearDown(self):
        self.p.close()

    def test_the_tier_is_the_briefs_quality_line(self):
        for said, tier in (("hero 75", "hero"), ("AAA", "aaa"), ("complex — a tool", "complex"), ("prop 55", "prop"),
                           ("clean and simple", "prop")):
            self.assertEqual(SH.tier_of({"answers": {"quality": said}}), tier, said)
        self.assertIsNone(SH.tier_of({"answers": {"quality": "<answer>  (prop 55 · hero 75 · aaa 88)"}}))
        self.assertIsNone(SH.tier_of(None))

    def test_a_good_sheet_is_drawn_and_says_how_to_approve_it(self):
        code, v = self.p.run(SH)
        self.assertEqual((code, v["status"], v["problems"]), (0, "pass", []))
        self.assertIn("--stage sheet", v["next_action"])
        png = os.path.join(self.p.root, "assets", "models", "x.sheet.png")
        with Image.open(png) as im:
            self.assertEqual(im.width, SH.W)
            self.assertGreater(im.height, 1200)
        kept = json.load(open(png[:-4] + ".json", encoding="utf-8"))
        self.assertEqual(kept["id"], v["id"])
        self.assertEqual([f["name"] for f in kept["features"]], ["glow strip", "grip"])
        self.assertEqual(kept["features"][0]["px_per_mm"], 3.0)  # (its 90 px box over its 30 mm)
        self.assertEqual(kept["features"][0]["view"], "side")

    def test_every_reason_a_hero_feature_holds_the_sheet(self):
        # the kit's own bad fixture: a feature with no picture, one with no box, one far under 2 px per mm
        data = SH.gather("nocallout", FIXTURE)
        problems = SH.problems_of(data)
        self.assertEqual(len(problems), 3, problems)
        self.assertTrue(any(p.startswith("wolf crest: no picture") for p in problems), problems)
        self.assertTrue(any(p.startswith("badge: no box in sheetgun_side.png") for p in problems), problems)
        self.assertTrue(any(p.startswith("muzzle: only 0.1 px per mm") for p in problems), problems)
        self.assertEqual(SH.problems_of(SH.gather("sheetgun", FIXTURE)), [])  # (and the good one has none)
        # a picture that is not a file, and a box with no size and no scaled view
        self.p.write("assets/models/x.brief.md", BRIEF.format(tier="hero", picture="refs/nowhere.png", box="1,1,9,9")
                     .replace(" | 30 mm", ""))
        problems = SH.problems_of(SH.gather("x", self.p.root))
        self.assertTrue(any("refs/nowhere.png is not a file" in p for p in problems), problems)
        self.assertTrue(any(p.startswith("glow strip: no scale") for p in problems), problems)

    def test_a_refused_sheet_is_still_drawn_and_exits_as_a_failure(self):
        self.p.brief(box="206,60,296,68")
        self.p.write("assets/models/x.brief.md", BRIEF.format(tier="hero", picture=self.p.picture, box="206,60,296,68")
                     .replace("| 30 mm", "| 300 mm"))  # (0.3 px per mm)
        code, v = self.p.run(SH)
        self.assertEqual((code, v["status"]), (1, "fail"))
        self.assertIn("glow strip: only 0.3 px per mm", v["problems"][0])
        self.assertTrue(os.path.isfile(os.path.join(self.p.root, "assets", "models", "x.sheet.png")))  # (shown, in red)

    def test_the_id_follows_everything_the_sheet_shows(self):
        a = SH.sheet_id(SH.gather("x", self.p.root))
        self.assertEqual(a, SH.sheet_id(SH.gather("x", self.p.root)))
        text = open(os.path.join(self.p.root, "assets", "models", "x.brief.md"), encoding="utf-8").read()
        self.p.write("assets/models/x.brief.md", text.replace("- what: a block blaster", "- what: a block rifle"))
        self.assertNotEqual(a, SH.sheet_id(SH.gather("x", self.p.root)))  # (the title's own words are shown too)
        self.p.write("assets/models/x.brief.md", text)
        self.assertEqual(a, SH.sheet_id(SH.gather("x", self.p.root)))
        self.p.brief(box="206,60,290,68")  # a hero feature's box moved
        b = SH.sheet_id(SH.gather("x", self.p.root))
        self.assertNotEqual(a, b)
        self.p.draw(strip=(240, 40, 40))  # the picture itself changed
        self.assertNotEqual(b, SH.sheet_id(SH.gather("x", self.p.root)))

    def test_state_knows_a_missing_a_current_and_a_stale_sheet(self):
        st = SH.state("x", self.p.root)
        self.assertEqual((st["exists"], st["stale"], st["problems"]), (False, False, []))
        self.p.run(SH)
        st = SH.state("x", self.p.root)
        self.assertEqual((st["exists"], st["stale"], st["id"]), (True, False, st["current"]))
        code, v = self.p.run(SH, "--check")
        self.assertEqual((code, v["status"]), (0, "pass"))
        self.p.brief(box="206,60,290,68")
        st = SH.state("x", self.p.root)
        self.assertTrue(st["stale"])
        self.assertNotEqual(st["id"], st["current"])
        code, v = self.p.run(SH, "--check")
        self.assertEqual(code, 1)
        self.assertIn("older than what it shows", v["summary"])

    def test_a_trial_drawing_leaves_the_assets_own_sheet_alone(self):
        out = os.path.join(self.p.root, "elsewhere", "trial.png")
        os.makedirs(os.path.dirname(out))
        code, _ = self.p.run(SH, "--out", out)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(out))
        self.assertFalse(SH.state("x", self.p.root)["exists"])

    def test_a_pack_broken_by_hand_never_crashes_the_sheet(self):
        self.p.write("assets/models/x.pack.json", {"colours": ["red"], "object": "a gun", "sizes": 3})
        data = SH.gather("x", self.p.root)
        self.assertEqual(data["palette"], [])
        self.assertIsNone(data["length_mm"])

    def test_measured_colours_and_the_real_length_reach_the_sheet(self):
        self.p.write("assets/models/x.pack.json", {"colours": {"body": {"srgb": "#2e3038"}, "strip": {"srgb": [26, 204, 242]}},
                                                   "object": {"name": "blaster", "length_mm": 306}})
        data = SH.gather("x", self.p.root)
        self.assertEqual([c["rgb"] for c in data["palette"]], [[46, 48, 56], [26, 204, 242]])
        self.assertEqual(data["length_mm"], 306.0)
        self.assertNotIn("no measured colours", " ".join(SH.notes_of(data)))

    PACK = {"colours": {"body": {"srgb": "#2e3038"}, "strip": {"srgb": [26, 204, 242]},
                        "grip": {"srgb": [30, 30, 33]}}}

    def silhouette(self):
        """the trace's outline as the picture's own silhouette (the fixture's is its box: with the ground in it) -
        the body 160 x 50 and the grip 32 x 57 under its back, in the trace's own units (the front at u = 1)"""
        px = [(166, 42), (326, 42), (326, 92), (317, 92), (317, 150), (285, 150), (285, 92), (166, 92)]
        self.p.write("assets/models/x_side.trace.json", {
            "source": self.p.picture, "front": "left", "height_ratio": 108 / 306,
            "frame": {"x0": 20.0, "y1": 150.0, "length_px": 306.0},
            "outline": [[1.0 - (x - 20.0) / 306.0, (150.0 - y) / 306.0] for x, y in px], "holes": []})

    def test_the_sheet_carries_its_colour_plan(self):
        # the picture: a body 160 x 50 with a strip 90 x 8 on it, a grip 32 x 57 under it
        self.silhouette()
        self.p.write("assets/models/x.pack.json", self.PACK)
        code, v = self.p.run(SH)
        self.assertEqual((code, v["status"]), (0, "pass"))
        plan = v["colour_plan"]
        self.assertEqual([(r["name"], r["role"]) for r in plan["rows"]],
                         [("body", "main"), ("grip", "second"), ("strip", "accent")])
        got = {r["name"]: r["share"] for r in plan["rows"]}
        self.assertAlmostEqual(got["body"], 0.74, delta=0.02)
        self.assertAlmostEqual(got["grip"], 0.19, delta=0.02)
        self.assertAlmostEqual(got["strip"], 0.07, delta=0.015)
        self.assertEqual((plan["view"], plan["palette_from"], plan["by"], plan["measured"]),
                         ("side", "measured (kit pack colours)", "outline", True))
        self.assertEqual(plan["leads"], "dark")
        self.assertIn(" · colours: main body 7", v["summary"])
        self.assertIn(", second grip 1", v["summary"])
        self.assertIn("; values: dark leads ", v["summary"])
        self.assertTrue(any("body and grip are ONE grey" in n for n in plan["notes"]), plan["notes"])
        kept = json.load(open(os.path.join(self.p.root, "assets", "models", "x.sheet.json"), encoding="utf-8"))
        self.assertEqual(kept["colour_plan"], plan)                    # ... and in the record a build can read
        self.assertNotIn("picture", kept["colour_plan"])               # (which names no picture)

    def test_the_object_is_inside_its_traced_outline(self):
        # the trace's outline moved to the body alone: the grip is no longer the object
        self.p.write("assets/models/x_side.trace.json", {
            "source": self.p.picture, "front": "left", "height_ratio": 108 / 306,
            "frame": {"x0": 20.0, "y1": 150.0, "length_px": 306.0},
            "outline": [[1.0 - (x - 20.0) / 306.0, (150.0 - y) / 306.0]
                        for x, y in ((166, 42), (326, 42), (326, 92), (166, 92))], "holes": []})
        self.p.write("assets/models/x.pack.json", self.PACK)
        _code, v = self.p.run(SH)
        got = {r["name"]: r["share"] for r in v["colour_plan"]["rows"]}
        self.assertEqual(got["grip"], 0.0)
        self.assertGreater(got["body"], 0.88)
        poly, holes = SH.outline_px({"frame": {"x0": 20.0, "y1": 150.0, "length_px": 306.0}, "front": "right",
                                     "outline": [[0, 0], [1, 0], [1, 0.5]], "holes": []})
        self.assertEqual((poly, holes), ([(20.0, 150.0), (326.0, 150.0), (326.0, -3.0)], []))   # front right: u as x
        self.assertEqual(SH.outline_px({"outline": [[0, 0], [1, 0], [1, 1]]}), (None, ()))      # no frame: none
        self.assertEqual(SH.outline_px({"frame": {"x0": 0, "y1": 1, "length_px": 9}, "rotate": 3.0,
                                        "outline": [[0, 0], [1, 0], [1, 1]]}), (None, ()))      # turned: none

    def test_every_palette_colour_is_drawn_the_one_not_in_the_picture_too(self):
        # the owner approves the whole palette: a part that this view does not show keeps its swatch
        self.silhouette()
        pack = {"colours": {**self.PACK["colours"], "inner": {"srgb": [255, 0, 255]}}}
        self.p.write("assets/models/x.pack.json", pack)
        _code, v = self.p.run(SH)
        inner = next(r for r in v["colour_plan"]["rows"] if r["name"] == "inner")
        self.assertEqual((inner["share"], inner["role"]), (0.0, "minor"))
        with Image.open(os.path.join(self.p.root, "assets", "models", "x.sheet.png")) as im:
            import numpy as np

            a = np.asarray(im.convert("RGB")).astype(int)
            self.assertGreater(int((np.abs(a - np.array([255, 0, 255])).sum(-1) < 12).sum()), 5000)   # its swatch

    def test_a_sampled_palette_has_no_roles_and_its_colours_stay_out_of_the_record(self):
        code, v = self.p.run(SH)
        plan = v["colour_plan"]
        self.assertEqual((code, plan["measured"]), (0, False))
        self.assertTrue(plan["palette_from"].startswith("sampled from the side picture"))
        self.assertTrue(plan["rows"] and all(r["role"] is None for r in plan["rows"]))
        self.assertIn("colours: sampled (no roles); values: ", v["summary"])
        self.assertNotIn("colours: main", v["summary"])
        self.assertTrue(any("SAMPLED" in n for n in plan["notes"]))
        kept = json.load(open(os.path.join(self.p.root, "assets", "models", "x.sheet.json"), encoding="utf-8"))
        self.assertEqual(kept["colour_plan"]["rows"], [])              # a picture's own colours: not in the record
        self.assertEqual(kept["colour_plan"]["values"], plan["values"])

    def test_the_colour_plan_is_no_part_of_the_sheets_id(self):
        # it is read off what the id already covers (the picture, its trace, the palette): a sheet the owner
        # approved before the plan was drawn is still the sheet he approved
        self.p.write("assets/models/x.pack.json", self.PACK)
        data = SH.gather("x", self.p.root)
        before = SH.sheet_id(data)
        data["palette_shown"], data["colour_plan"], data["colour_arrays"] = SH.colour_plan_of(data)
        self.assertEqual(SH.sheet_id(data), before)
        _code, v = self.p.run(SH)
        self.assertEqual(v["id"], before)
        self.assertFalse(SH.state("x", self.p.root)["stale"])

    def test_a_note_the_numbers_earn_is_on_the_sheet(self):
        self.silhouette()
        self.p.write("assets/models/x.pack.json", {"colours": {"body": {"srgb": "#2e3038"},
                                                               "grip": {"srgb": [30, 30, 33]}}})   # no strip colour
        _code, v = self.p.run(SH)
        self.assertEqual(v["status"], "pass")                          # (a note never refuses a sheet)
        notes = v["colour_plan"]["notes"]
        self.assertTrue(any("no accent" in n for n in notes), notes)
        self.assertAlmostEqual(v["colour_plan"]["other"], 0.07, delta=0.015)    # the strip nobody listed
        with Image.open(os.path.join(self.p.root, "assets", "models", "x.sheet.png")) as im:
            noted = im.height
        self.p.write("assets/models/x.pack.json", {"colours": {"body": {"srgb": "#2e3038"},
                                                               "strip": {"srgb": [26, 204, 242]}}})   # no grip
        _code, v2 = self.p.run(SH)
        with Image.open(os.path.join(self.p.root, "assets", "models", "x.sheet.png")) as im:
            def room(n):   # a line each, and a gap over them when there are any
                return 30 * len(n) + (12 if n else 0)

            self.assertEqual(noted - im.height, room(notes) - room(v2["colour_plan"]["notes"]))

    def test_colours_that_cannot_be_read_say_so_on_the_sheet_and_never_stop_it(self):
        self.p.write("assets/models/x.pack.json", self.PACK)
        _code, good = self.p.run(SH)
        with Image.open(os.path.join(self.p.root, "assets", "models", "x.sheet.png")) as im:
            whole = im.height
        real = SH.CP.measure

        def broken(*_a, **_k):
            raise OSError("a picture cut short")

        SH.CP.measure = broken
        try:
            code, v = self.p.run(SH)
        finally:
            SH.CP.measure = real
        self.assertEqual((code, v["status"], v["id"]), (0, "pass", good["id"]))
        self.assertIn("could not be read (OSError: a picture cut short)", v["colour_plan"]["notes"][0])
        self.assertEqual(v["colour_plan"]["rows"], [])
        with Image.open(os.path.join(self.p.root, "assets", "models", "x.sheet.png")) as im:
            # no read in three greys (360 px) - and the reason IS on the page: its one line and the gap over it
            self.assertEqual(im.height, whole - 360 - 30 * len(good["colour_plan"]["notes"])
                             - (12 if good["colour_plan"]["notes"] else 0) + 30 + 12)

    def test_a_tall_object_lies_on_its_side_in_the_three_grey_read(self):
        # (drawn through draw() itself: a 40 x 400 object must not become a sliver)
        tall = os.path.join(self.p.root, "refs", "tall.png")
        im = Image.new("RGB", (120, 480), (235, 235, 235))
        ImageDraw.Draw(im).rectangle((40, 40, 79, 439), fill=(46, 48, 56))
        ImageDraw.Draw(im).rectangle((40, 40, 79, 139), fill=(200, 200, 205))
        im.save(tall)
        plan, arrays = SH.CP.measure(tall, [{"name": "body", "rgb": [46, 48, 56]}, {"name": "cap", "rgb": [200, 200, 205]}])
        self.assertEqual(plan["rows"][0]["name"], "body")
        ys, xs = arrays["mask"].nonzero()
        self.assertGreater(ys.max() - ys.min(), 1.5 * (xs.max() - xs.min()))   # the case the panel turns


class TestSheetStage(unittest.TestCase):
    """kit plan: the model sheet is its own stage between gather and the draft, and the owner's yes is for its id"""

    def setUp(self):
        self.p = Project()

    def tearDown(self):
        self.p.close()

    def test_the_stages_are_in_order(self):
        keys = [k for k, _ in PL.STAGES]
        self.assertEqual(keys, ["brief", "gather", "sheet", "draft", "blockout", "shape", "surface", "mechanism", "look",
                                "present"])
        self.assertLess(PL.EXTERIOR_FIRST.index("sheet"), PL.EXTERIOR_FIRST.index("blockout"))
        self.assertLess(PL.EXTERIOR_FIRST.index("blockout"), PL.EXTERIOR_FIRST.index("shape"))

    def test_a_hero_goes_from_no_sheet_to_the_owners_yes(self):
        st = self.p.stages()["sheet"]
        self.assertEqual(st["status"], PL.TODO)
        self.assertIn("no model sheet", st["missing"][0])
        self.assertIn("lune run kit sheet x", st["commands"][0])
        self.assertLessEqual(len(st["commands"]), PL.MAX_COMMANDS)
        _, v = self.p.run(SH)
        st = self.p.stages()["sheet"]
        self.assertEqual(st["status"], PL.PARTIAL)
        self.assertEqual(st["missing"], ["the owner has not approved the model sheet"])
        self.assertIn("--by owner --stage sheet", st["commands"][0])
        self.p.approve("sheet", v["id"], by="model-proposed")  # (a model's own yes is nobody's)
        self.assertEqual(self.p.stages()["sheet"]["status"], PL.PARTIAL)
        self.p.approve("sheet", v["id"])
        st = self.p.stages()["sheet"]
        self.assertEqual((st["status"], st["missing"]), (PL.DONE, []))
        self.assertIn("approved by the owner (2026-11-11)", st["found"])

    def test_the_plan_reads_the_owner_and_the_tier_exactly_as_the_lock_does(self):
        _, v = self.p.run(SH)
        # kit/lib/locks.luau Locks.isOwner: `who`, when given, must be the owner — whatever `by` says
        self.p.write("board/locks.json", {"stages": {"3d": {"x": {"sheet": {"who": "model", "by": "owner", "id": v["id"]}}}}})
        self.assertEqual(self.p.stages()["sheet"]["status"], PL.PARTIAL)
        self.p.write("board/locks.json", {"stages": {"3d": {"x": {"sheet": {"who": "owner", "id": v["id"]}}}}})
        self.assertEqual(self.p.stages()["sheet"]["status"], PL.DONE)
        self.p.write("board/locks.json", {"stages": {"3d": {"x": {"sheet": {"by": 7, "id": v["id"]}}}}})
        self.assertEqual(self.p.stages()["sheet"]["status"], PL.PARTIAL)
        # the tier: the lock (lanelocks briefTier) reads aaa / hero / complex ANYWHERE in the quality line, so this
        # line is a hero to it — the plan must show the sheet as needed, never "not needed" while the build refuses
        text = open(os.path.join(self.p.root, "assets", "models", "x.brief.md"), encoding="utf-8").read()
        self.p.write("assets/models/x.brief.md", text.replace("- quality: hero", "- quality: prop (not a hero piece)"))
        self.assertEqual(SH.tier_of(P.parse_brief(open(os.path.join(self.p.root, "assets", "models", "x.brief.md"),
                                                       encoding="utf-8").read())), "hero")
        self.assertNotEqual(self.p.stages()["sheet"]["status"], PL.NOT_NEEDED)

    def test_a_sheet_that_changed_needs_their_word_again(self):
        _, v = self.p.run(SH)
        self.p.approve("sheet", v["id"])
        self.p.brief(box="206,60,290,68")  # (the brief moved a hero feature: the sheet he saw is no longer the target)
        st = self.p.stages()["sheet"]
        self.assertEqual(st["status"], PL.PARTIAL)
        self.assertIn("older than what it shows", st["missing"][0])
        self.p.run(SH)  # drawn again: a new id, and his yes was for the old one
        st = self.p.stages()["sheet"]
        self.assertEqual(st["missing"], ["the owner has not approved the model sheet as it is now (it changed since "
                                         "their yes)"])

    def test_a_sheet_with_a_problem_cannot_be_the_next_step(self):
        self.p.write("assets/models/x.brief.md", BRIEF.format(tier="hero", picture=self.p.picture, box="206,60,296,68")
                     .replace("| 30 mm", "| 300 mm"))
        self.p.run(SH)
        st = self.p.stages()["sheet"]
        self.assertEqual(st["status"], PL.PARTIAL)
        self.assertIn("1 problem(s) hold the sheet: glow strip: only 0.3 px per mm", st["missing"][0])

    def test_a_prop_and_an_older_piece_need_none(self):
        self.p.brief(tier="prop")
        stages = self.p.stages()
        self.assertEqual((stages["sheet"]["status"], stages["blockout"]["status"]), (PL.NOT_NEEDED, PL.NOT_NEEDED))
        self.p.brief(tier="hero")
        self.p.write("board/locks.json", {"waivers": {"3d": {"x": {"by": "owner", "words": "skip it", "steps": ["sheet"]}}}})
        stages = self.p.stages()
        self.assertEqual(stages["sheet"]["status"], PL.NOT_NEEDED)   # (the owner waived the sheet ...)
        self.assertEqual(stages["blockout"]["status"], PL.TODO)      # (... not the blockout)
        script = os.path.relpath(os.path.join(self.p.root, "assets", "models", "build_x.py"), PL.ROOT).replace("\\", "/")
        self.p.write("board/locks.json", {"grandfathered": {"3d-stages": [script.upper()]}})  # (it predates them)
        stages = self.p.stages()
        self.assertEqual((stages["sheet"]["status"], stages["blockout"]["status"]), (PL.NOT_NEEDED, PL.NOT_NEEDED))

    def test_no_shape_before_the_sheet(self):
        stages = PL.assess(PL.facts("x", self.p.root))
        for st in stages:  # (the stages before it done, as a finished gather leaves them)
            if st["key"] in ("brief", "gather"):
                st.update(status=PL.DONE, missing=[])
        PL.lock(stages, None, exterior_first=True)
        by = {st["key"]: st for st in stages}
        self.assertNotIn("locked", by["sheet"])
        for later in ("draft", "blockout", "shape", "surface"):
            self.assertIn("model sheet is not done", by[later].get("locked", ""), later)
        self.assertIs(PL.next_stage(stages), by["sheet"])


class TestBlockout(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        _, v = self.p.run(SH)
        self.sheet = v["id"]
        self.p.approve("sheet", self.sheet)

    def tearDown(self):
        self.p.close()

    def keep(self, sheet_id, bid="b1"):
        """a blockout as kit blockout leaves it beside the script"""
        self.p.write("assets/models/x.blockout.json", {"id": bid, "sheet": sheet_id, "size": [0.4, 1.0, 3.0], "notes": []})
        Image.new("RGB", (8, 8)).save(os.path.join(self.p.root, "assets", "models", "x.blockout.png"))

    def test_the_id_is_of_the_sheet_the_size_and_the_overlaps(self):
        meta = {"script_sha": "abc", "size": [0.4, 1.0, 3.0], "references": [{"view": "side", "iou": 0.93}]}
        a = BO.blockout_id(self.sheet, meta)
        self.assertEqual(a, BO.blockout_id(self.sheet, dict(meta)))
        self.assertNotEqual(a, BO.blockout_id("another sheet", meta))
        self.assertNotEqual(a, BO.blockout_id(self.sheet, {**meta, "size": [0.4, 1.2, 3.0]}))
        self.assertNotEqual(a, BO.blockout_id(self.sheet, {**meta, "references": [{"view": "side", "iou": 0.81}]}))

    def test_a_blockout_is_of_one_sheet_and_outlives_the_detail(self):
        self.assertFalse(BO.state("x", self.p.root)["exists"])
        self.keep(self.sheet)
        st = BO.state("x", self.p.root)
        self.assertEqual((st["exists"], st["stale"], st["id"]), (True, False, "b1"))
        # the SCRIPT changing never stales it (the shape is detailed after the owner's yes) ...
        self.p.write("assets/models/build_x.py", "import rbx\na = rbx.Asset('x')\na.box('Body', (1, 1, 1), (0, 0, 0), 'm')\n")
        self.assertFalse(BO.state("x", self.p.root)["stale"])
        # ... a new SHEET does: another target needs another blockout
        self.p.brief(box="206,60,290,68")
        self.p.run(SH)
        self.assertTrue(BO.state("x", self.p.root)["stale"])
        code, v = self.p.run(BO, "--check")
        self.assertEqual(code, 1)
        self.assertIn("the model sheet changed since this blockout", v["summary"])

    def test_the_blockout_stage_in_the_plan(self):
        st = self.p.stages()["blockout"]
        self.assertEqual(st["status"], PL.TODO)
        self.assertIn("no build script", st["missing"][0])
        self.p.write("assets/models/build_x.py", "import rbx\na = rbx.Asset('x')\na.box('Body', (1, 1, 1), (0, 0, 0), 'm')\n")
        st = self.p.stages()["blockout"]
        self.assertIn("no blockout sheet", st["missing"][0])
        self.assertIn("lune run kit blockout x", st["commands"][0])
        self.keep(self.sheet)
        st = self.p.stages()["blockout"]
        self.assertEqual((st["status"], st["missing"]), (PL.PARTIAL, ["the owner has not approved the blockout"]))
        self.assertIn("--by owner --stage blockout", st["commands"][0])
        self.p.approve("blockout", "b1")
        self.assertEqual(self.p.stages()["blockout"]["status"], PL.DONE)
        self.keep(self.sheet, bid="b2")  # drawn again: another blockout than the one he approved
        st = self.p.stages()["blockout"]
        self.assertEqual(st["missing"], ["the owner has not approved the blockout as it is now (it was drawn again since "
                                         "their yes)"])

    def test_a_view_far_from_its_reference_is_said_on_the_sheet(self):
        views = [{"view": "side"}, {"view": "top"}]
        meta = {"references": [{"view": "side", "iou": 0.62}, {"view": "top", "iou": 0.97}], "bars": {"side": 0.9},
                "clay": {"refs": {"side": {}}}}
        notes = BO.notes_of(meta, views)
        self.assertEqual(len(notes), 2, notes)
        self.assertIn("the side view overlaps its reference 0.62 (its bar: 0.9)", notes[0])
        self.assertIn("the top view has no plain picture frame", notes[1])
        self.assertIn("no traced view is measured", BO.notes_of({"references": [], "clay": {"refs": {}}}, [])[0])

    def test_the_sheet_needs_a_blockout_round_first(self):
        code, v = self.p.run(BO, "--build", os.path.join(self.p.root, "build"))
        self.assertEqual(code, 1)
        self.assertIn("no shape round of x has kept its pictures", v["summary"])
        self.p.write("build/judge/x/geo/meta.json", {"asset": "x", "views": ["front"]})
        code, v = self.p.run(BO, "--build", os.path.join(self.p.root, "build"))
        self.assertIn("kept no clay views", v["summary"])

    def test_a_build_says_when_the_size_moved_from_the_approved_blockout(self):
        path = os.path.join(self.p.root, "assets", "models", "x.blockout.json")
        locks = os.path.join(self.p.root, "board", "locks.json")
        self.assertIsNone(P.blockout_drift(path, [0.4, 1.0, 3.0], "x", "b1"))  # (no blockout: nothing to say)
        self.keep(self.sheet)
        # drawn, never approved: nothing he said yes to, so nothing to hold the build to
        self.assertIsNone(P.approved_stage(locks, "x", "blockout"))
        self.assertIsNone(P.blockout_drift(path, [0.4, 1.0, 3.6], "x", P.approved_stage(locks, "x", "blockout")))
        self.p.approve("blockout", "b1")
        yes = P.approved_stage(locks, "x", "blockout")
        self.assertEqual(yes, "b1")
        ok = P.blockout_drift(path, [0.41, 1.03, 3.1], "x", yes)
        self.assertTrue(ok["ok"])
        moved = P.blockout_drift(path, [0.4, 1.0, 3.6], "x", yes)
        self.assertEqual((moved["ok"], moved["severity"], moved["name"]), (False, "warn", "blockout_drift"))
        self.assertIn("length 3 -> 3.6 studs (+20%)", moved["fix"])
        self.assertIn("lune run kit blockout x --again", moved["fix"])
        self.assertIsNone(P.blockout_drift(path, None, "x", yes))
        # drawn AGAIN and not shown yet: the file on disk is not the blockout he approved — no baseline moves quietly
        self.keep(self.sheet, bid="b2")
        self.assertIsNone(P.blockout_drift(path, [0.4, 1.0, 3.6], "x", yes))
        # a model's own record is nobody's yes
        self.p.approve("blockout", "b2", by="model-proposed")
        self.assertIsNone(P.approved_stage(locks, "x", "blockout"))


if __name__ == "__main__":
    unittest.main()
