"""kit/blender/rbx_plan.py: the order of work — the owner's brief read into facts (view, hero features with their
routes, quality bar, style, moving parts), the routes check, pixels per mm for each hero feature in each picture
(coverage), and the stage gate (silhouette first: detail-level failures deferred while an outline is below its bar).
Pure python; kit/refs/coverage.py (the `kit refs coverage` table) on a temporary project."""

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_plan as P  # noqa: E402

# (loaded by its path: a `coverage` on sys.path would be the coverage.py package when pytest-cov is installed)
_spec = importlib.util.spec_from_file_location("kit_refs_coverage", os.path.join(ROOT, "kit", "refs", "coverage.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


TEMPLATE = read("kit/templates/asset.brief.md")


def answered(**over):
    """the template with every question answered (over: question line -> its answer)"""
    text = TEMPLATE
    ans = {"what": "a sword", "end goal": "game", "quality": "hero", "quality bar": "https://example.org/a",
           "style": "realistic PBR", "view": "first person", "function": "static", "moving parts": "none",
           "extras": "none", "references": "refs/x.png", "ownership": "the owner's own"}
    ans.update(over)
    for q, a in ans.items():
        text = text.replace(f"- {q}: <answer>", f"- {q}: {a}")
    return text


def feat(text, rank=1):
    return P.parse_feature(text, rank)


class TestBrief(unittest.TestCase):
    def test_the_template_is_unanswered_with_every_new_question(self):
        b = P.parse_brief(TEMPLATE)
        self.assertFalse(b["answered"])
        for q in ("view", "hero_features", "quality_bar", "style", "moving_parts", "what", "ownership"):
            self.assertIn(q, b["unanswered"])
        self.assertEqual(b["hero_features"], [])  # the `1. <answer>` placeholder is not a feature
        self.assertNotIn("view", b)  # an unanswered question is no fact

    def test_the_intro_naming_answer_is_no_question(self):
        # (the intro says "write their answers over each `<answer>`": kept in an answered brief, it is no question)
        self.assertEqual(P.unanswered_count(TEMPLATE), 12)  # 11 questions + the first hero feature line
        text = answered().replace("  1. <answer>", "  1. fuller | code | a groove")
        self.assertIn("`<answer>`", text)
        self.assertEqual(P.unanswered_count(text), 0)
        self.assertTrue(P.parse_brief(text)["answered"])

    def test_an_old_answered_brief_still_counts_as_answered(self):
        b = P.parse_brief(read("kit/selftest/blender/_selftest_brief_answered.brief.md"))
        self.assertTrue(b["answered"])
        self.assertEqual(b["unanswered"], [])
        self.assertEqual(b["answers"]["end_goal"], "game")
        self.assertNotIn("hero_features", b)  # (never asked: the routes check says so on hero builds)

    def test_answers_become_facts(self):
        text = answered(view="third person, a hand's width on screen; the left side and the top face the camera",
                        style="stylised", **{"moving parts": "trigger, magazine (drops out); bolt"},
                        **{"quality bar": "https://a.example/one, refs/bar_two.png"})
        text = text.replace("  1. <answer>", "  1. wolf head | relief | sculpted wolf\n  2. fuller | code | a groove")
        b = P.parse_brief(text)
        self.assertTrue(b["answered"])
        self.assertEqual(b["view"]["modes"], ["third person"])
        self.assertEqual(b["view"]["on_screen"], "a hand's width on screen")
        self.assertEqual(b["view"]["sides"], ["left", "top"])
        self.assertEqual(b["style"], "stylised")
        self.assertEqual(b["moving_parts"], ["trigger", "magazine (drops out)", "bolt"])
        self.assertEqual(b["quality_bar"], ["https://a.example/one", "refs/bar_two.png"])
        self.assertEqual([f["name"] for f in b["hero_features"]], ["wolf head", "fuller"])
        self.assertEqual([f["rank"] for f in b["hero_features"]], [1, 2])

    def test_help_left_in_place_is_not_part_of_the_answer(self):
        text = TEMPLATE.replace("- style: <answer>", "- style: realistic PBR")  # its `  (realistic PBR · ...)` stays
        text = text.replace("- view: <answer>", "- view: world prop")  # its help runs onto the next line
        b = P.parse_brief(text)
        self.assertEqual(b["answers"]["style"], "realistic PBR")
        self.assertEqual(b["answers"]["view"], "world prop")
        self.assertEqual(b["view"]["modes"], ["world prop"])

    def test_no_moving_parts(self):
        for none in ("none", "None.", "static", "-"):
            self.assertEqual(P.parse_brief(answered(**{"moving parts": none}))["moving_parts"], [])

    def test_unindented_feature_lines_are_features(self):
        text = answered().replace("  1. <answer>", "1. wolf head | relief\n- fuller: code — a groove\n- grip | cord")
        b = P.parse_brief(text + "\n- notes: a question of the owner's own, after a blank line\n")
        self.assertEqual([(f["name"], f["route"]) for f in b["hero_features"]],
                         [("wolf head", "relief"), ("fuller", "code"), ("grip", None)])
        self.assertEqual(b["answers"]["notes"], "a question of the owner's own, after a blank line")
        self.assertEqual(b["answers"]["ownership"], "the owner's own")

    def test_hero_features_written_on_one_line(self):
        b = P.parse_brief(answered().replace("- hero features:", "- hero features: wolf head (relief); fuller (code)"))
        self.assertEqual([(f["name"], f["route"]) for f in b["hero_features"]], [("wolf head", "relief"),
                                                                                 ("fuller", "code")])


class TestFeature(unittest.TestCase):
    def test_the_template_form(self):
        f = feat("wolf head | relief | the pommel's sculpted wolf | refs/side_profile.png 410,120,470,170 | 30 mm")
        self.assertEqual((f["name"], f["route"], f["what"]), ("wolf head", "relief", "the pommel's sculpted wolf"))
        self.assertEqual((f["picture"], f["box"], f["size_mm"]), ("refs/side_profile.png", [410, 120, 470, 170], 30.0))
        self.assertEqual(f["organic"], "sculpted")

    def test_forgiving_forms(self):
        self.assertEqual(feat("wolf head: relief — the wolf @ refs/a.png 1,2,3,4, 3 cm")["size_mm"], 30.0)
        self.assertEqual(feat("wolf head: relief — the wolf @ refs/a.png 1,2,3,4")["route"], "relief")
        self.assertEqual(feat("1. gem (generated) 12 mm")["name"], "gem")
        self.assertEqual(feat("1. gem (generated) 12 mm")["route"], "generated")
        self.assertEqual(feat("gem | kit gen")["route"], "generated")  # an alias, as the whole field
        self.assertEqual(feat("emblem | decal | the clan mark")["route"], "projected")
        self.assertEqual(feat("crest | route: procedural")["route"], "procedural")
        self.assertEqual(feat("head | sculpt | the skull and jaw")["route"], "sculpt")
        self.assertEqual(feat("roots | sculpted | gnarled roots")["route"], "sculpt")   # (an alias)

    def test_a_route_field_beats_a_route_word_in_the_description(self):
        f = feat("wolf | generated | a relief of a wolf, procedural fur")
        self.assertEqual(f["route"], "generated")

    def test_a_size_field_beats_a_size_in_the_description(self):
        self.assertEqual(feat("pommel | code | sits on a 12 mm tang | 40 mm")["size_mm"], 40.0)

    def test_no_route(self):
        f = feat("grip wrap | leather cord wound round the grip")
        self.assertIsNone(f["route"])
        self.assertEqual(f["what"], "leather cord wound round the grip")


class TestRoutes(unittest.TestCase):
    def brief(self, *lines):
        return P.parse_brief(answered().replace("  1. <answer>", "\n".join(f"  {i + 1}. {x}"
                                                                           for i, x in enumerate(lines))))

    def test_a_feature_with_no_route_is_named(self):
        c = P.routes_check(self.brief("grip wrap | leather cord", "fuller | code | a groove"), "hero")
        self.assertFalse(c["ok"])
        self.assertEqual(c["value"], ["grip wrap: no route"])
        self.assertEqual(c["severity"], "warn")
        self.assertIn("grip wrap: no route", c["fix"])

    def test_sculpted_or_organic_built_as_code_is_named(self):
        c = P.routes_check(self.brief("wolf crest | code | a sculpted wolf", "vine | code | a curling vine"), "aaa")
        self.assertEqual(c["value"], ["wolf crest: route code, but it is sculpted", "vine: route code, but it is vine"])
        self.assertIn("sculpt it (a.sculpt)", c["fix"])

    def test_a_sculpted_organic_feature_is_a_good_route(self):
        c = P.routes_check(self.brief("wolf head | sculpt | a sculpted wolf's head", "fuller | code | a groove"), "hero")
        self.assertTrue(c["ok"])

    def test_a_good_plan_passes(self):
        c = P.routes_check(self.brief("wolf crest | relief | a sculpted wolf", "fuller | code | a groove"), "hero")
        self.assertTrue(c["ok"])

    def test_only_hero_and_aaa_builds_are_judged(self):
        self.assertIsNone(P.routes_check(self.brief("grip wrap | leather cord"), "prop"))

    def test_an_unanswered_list_is_the_brief_check_s_job(self):
        self.assertIsNone(P.routes_check(P.parse_brief(TEMPLATE), "hero"))
        self.assertIsNone(P.routes_check(None, "hero"))

    def test_a_hero_build_with_no_hero_features_is_told(self):
        old = P.parse_brief(read("kit/selftest/blender/_selftest_brief_answered.brief.md"))
        c = P.routes_check(old, "hero")
        self.assertFalse(c["ok"])
        self.assertIn("no hero features", c["value"])

    def test_the_verdict_table(self):
        feats = self.brief("wolf head | relief | x | refs/side.png 1,2,3,4", "grip wrap | cord")["hero_features"]
        cov = {"features": [{"name": "wolf head", "best_px_per_mm": 1.4}]}
        self.assertEqual(P.routes_table(feats, cov), ["1. wolf head | relief | side.png 1,2,3,4 | 1.4 px/mm",
                                                      "2. grip wrap | NO ROUTE | - | px/mm ?"])


def trace(source, ppl, parts=None):
    return {"source": source, "pixels_per_length": ppl, "height_ratio": 0.3, "front": "right",
            "outline": [[0, 0], [1, 0], [1, 0.3], [0, 0.3]], "parts": parts or {}}


class TestCoverage(unittest.TestCase):
    def test_a_traced_picture_s_scale(self):
        # a 1000 mm object 452 px long in its side picture: 0.452 px/mm (the M107 case: ornaments at ~145 px)
        s = P.picture_scales({"side": trace("refs/side.png", 452)}, length_mm=1000)
        self.assertAlmostEqual(s["refs/side.png"]["px_per_mm"], 0.452)
        # views.json's mm per unit wins (a front view's is the top view's width)
        s = P.picture_scales({"front": trace("refs/front.png", 300)}, {"views": {"front": {"mm_per_unit": 150}}})
        self.assertAlmostEqual(s["refs/front.png"]["px_per_mm"], 2.0)
        self.assertEqual(P.picture_scales({"front": trace("refs/front.png", 300)}, length_mm=1000), {})

    def test_the_best_picture_wins_and_a_low_hero_feature_is_named(self):
        feats = [feat("wolf head | relief | x | refs/side.png 410,120,470,170 | 30 mm"),
                 feat("wolf head | relief | x | refs/closeup.jpg 0,0,600,400 | 30 mm", 1),
                 feat("fuller | code | a groove | refs/side.png 100,100,400,110 | 400 mm", 2)]
        cov = P.coverage(feats, {"side": trace("refs/side.png", 900)}, length_mm=600)  # 1.5 px/mm in the side view
        by = {(r["feature"], r["picture"]): r for r in cov["rows"]}
        self.assertAlmostEqual(by[("wolf head", "refs/side.png")]["px_per_mm"], 1.5)
        self.assertEqual(by[("wolf head", "refs/side.png")]["feature_px"], 60)  # its box, in the traced picture
        self.assertAlmostEqual(by[("wolf head", "refs/closeup.jpg")]["px_per_mm"], 20.0)  # 600 px / 30 mm
        best = {f["name"]: f for f in cov["features"]}
        self.assertEqual(best["wolf head"]["best_picture"], "refs/closeup.jpg")
        self.assertFalse(best["wolf head"]["low"])
        self.assertTrue(best["fuller"]["low"])  # only the side picture: 1.5 < 2 px/mm
        self.assertEqual([P.low_text(f) for f in cov["low"]], ["fuller: 1.5 px/mm at best (side.png)"])

    def test_a_brief_naming_only_the_file_finds_its_traced_picture(self):
        cov = P.coverage([feat("crown | relief | x | side.png 0,0,10,10")], {"side": trace("refs/side.png", 900)},
                         length_mm=300)
        self.assertAlmostEqual(cov["rows"][0]["px_per_mm"], 3.0)

    def test_a_close_up_without_a_size_is_unmeasured_not_guessed(self):
        cov = P.coverage([feat("crown | relief | x | refs/c.png 0,0,80,40")])
        self.assertIsNone(cov["rows"][0]["px_per_mm"])
        self.assertIn("size in mm", cov["rows"][0]["how"])
        self.assertIsNone(P.coverage_check(cov, "hero"))  # nothing measured: nothing to judge

    def test_traced_parts_give_their_pictures_and_sizes(self):
        # a part traced in the side view (SAM): its picture counts for the hero feature of the same name, and its
        # size in mm (views.json) sizes a close-up box that names no size
        poly = [[0.1, 0.0], [0.15, 0.0], [0.15, 0.05], [0.1, 0.05]]
        traces = {"side": trace("refs/side.png", 1000, {"wolf_head": poly})}
        views = {"views": {"side": {"mm_per_unit": 800}},
                 "parts": {"wolf_head": {"side": {"size_mm": [40.0, 40.0]}}}}
        cov = P.coverage([feat("Wolf Head | relief | x | refs/close.png 0,0,200,180")], traces, views)
        rows = {r["picture"]: r for r in cov["rows"]}
        self.assertAlmostEqual(rows["refs/close.png"]["px_per_mm"], 5.0)  # 200 px over the traced 40 mm
        self.assertAlmostEqual(rows["refs/side.png"]["px_per_mm"], 1.25)  # 1000 px over 800 mm
        self.assertEqual(rows["refs/side.png"]["feature_px"], 50)  # 0.05 of the length
        self.assertTrue(all(r["hero"] for r in cov["rows"]))
        self.assertEqual(cov["features"][0]["best_px_per_mm"], 5.0)

    def test_a_traced_part_that_is_no_hero_feature_is_listed_never_judged(self):
        poly = [[0.1, 0.0], [0.15, 0.0], [0.15, 0.05], [0.1, 0.05]]
        cov = P.coverage([], {"side": trace("refs/side.png", 100, {"screw": poly})}, length_mm=1000)
        self.assertEqual(cov["rows"][0]["feature"], "screw")
        self.assertFalse(cov["rows"][0]["hero"])
        self.assertEqual(cov["low"], [])
        self.assertIsNone(P.coverage_check(cov, "hero"))

    def test_the_check_warns_a_prop_and_fails_a_hero(self):
        cov = P.coverage([feat("wolf head | relief | x | refs/far.png 100,40,142,80 | 30 mm")])
        self.assertAlmostEqual(cov["features"][0]["best_px_per_mm"], 1.4)
        prop, hero = P.coverage_check(cov, "prop", "sword"), P.coverage_check(cov, "hero", "sword")
        self.assertEqual((prop["severity"], hero["severity"]), ("warn", "error"))
        self.assertEqual(hero["value"], ["wolf head: 1.4 px/mm at best (far.png)"])
        self.assertTrue(hero["fix"].startswith("wolf head: 1.4 px/mm at best (far.png) — ask the owner for a "
                                               "close-up picture, or make a clean view (low trust)"))
        self.assertIn("lune run kit refs coverage sword", hero["fix"])
        good = P.coverage([feat("wolf head | relief | x | refs/near.png 0,0,300,200 | 30 mm")])
        self.assertTrue(P.coverage_check(good, "hero")["ok"])


def chk(name, ok, severity="error"):
    return {"name": name, "ok": ok, "severity": severity, "value": 0, "limit": 0, "fix": f"fix {name}"}


class TestStage(unittest.TestCase):
    refs = [{"view": "side", "iou": 0.81, "worst": "middle-right (missing)", "diff": "build/renders/x_ref_side.png"},
            {"view": "top", "iou": 0.95}, {"view": "front", "iou": 0.5}]  # (front: a plain picture, not traced)
    opts = {"side": {"bar": 0.9}, "top": {"bar": 0.9}}

    def test_blockout_while_any_traced_view_is_below_its_bar(self):
        s = P.stage_of(self.refs, self.opts, True)
        self.assertEqual(s["stage"], "blockout")
        self.assertEqual([v["view"] for v in s["below"]], ["side"])
        self.assertEqual(P.below_text(s), "side IoU 0.81 < 0.9")

    def test_detail_once_every_traced_view_reaches_it_and_unmeasured_with_none(self):
        refs = [dict(self.refs[0], iou=0.93), self.refs[1]]
        self.assertEqual(P.stage_of(refs, self.opts, True)["stage"], "detail")
        self.assertEqual(P.stage_of(self.refs, {}, True)["stage"], "unmeasured")
        self.assertEqual(P.stage_of(self.refs, {"side": {"bar": 0.8}}, True)["stage"], "detail")  # its own bar

    def test_the_gate_folds_the_reference_check_and_defers_detail(self):
        design = [chk("floating_parts", True), chk("reference_side", False), chk("reference_side_local", False),
                  chk("part_review", False), chk("quality", False), chk("texel_density", False, "warn"),
                  chk("mechanism", False), chk("review", False), chk("palette", True, "warn")]
        s = P.stage_of(self.refs, self.opts, True)
        out, gate = P.apply_gate(design, s)
        self.assertEqual(out[0], gate)
        self.assertEqual(gate["name"], "stage")
        self.assertEqual(gate["severity"], "error")
        self.assertTrue(gate["fix"].startswith("silhouette first: side IoU 0.81 < 0.9 — fix the outline before "
                                               "detail work"))
        self.assertIn("middle-right (missing)", gate["fix"])
        names = [c["name"] for c in out if not c["ok"]]
        self.assertEqual(names, ["stage", "reference_side_local", "mechanism", "review"])  # never reported twice
        self.assertEqual(s["deferred"], ["part_review", "quality", "texel_density"])
        self.assertIn("held back until then: part_review, quality, texel_density", gate["fix"])

    def test_under_the_gate_an_unmeasured_build_fails_and_holds_nothing_back(self):
        design = [chk("floating_parts", True), chk("part_review", False), chk("quality", False), chk("mechanism", False)]
        s = P.stage_of(self.refs, {}, True)                               # no traced view registered
        self.assertEqual((s["stage"], s["registered"]), ("unmeasured", []))
        out, gate = P.apply_gate(list(design), s)
        self.assertEqual(out[0], gate)
        self.assertEqual((gate["name"], gate["ok"], gate["severity"]), ("stage", False, "error"))
        self.assertEqual(gate["value"], "unmeasured: no traced view registered")
        self.assertIn("lune run kit trace <picture> --name <asset>_side", gate["fix"])
        self.assertIn("assets/models/<asset>_<view>.trace.json by itself", gate["fix"])
        self.assertIn('a.trace_match("<trace>", view="side")', gate["fix"])
        self.assertEqual(out[1:], design)                                 # its other findings stand, all of them
        self.assertEqual(s["deferred"], [])

    def test_a_registered_view_that_could_not_be_measured_is_unmeasured_too_and_named(self):
        s = P.stage_of([{"view": "side", "iou": None}], {"side": {"bar": 0.9}}, True)
        self.assertEqual((s["stage"], s["registered"]), ("unmeasured", ["side"]))
        _out, gate = P.apply_gate([], s)
        self.assertEqual(gate["value"], "unmeasured: registered (side) but none could be measured")

    def test_without_the_gate_an_unmeasured_build_is_left_alone(self):
        design = [chk("part_review", False)]
        s = P.stage_of(self.refs, {}, False)
        self.assertEqual(s["stage"], "unmeasured")
        out, gate = P.apply_gate(list(design), s)
        self.assertIsNone(gate)
        self.assertEqual(out, design)

    def test_no_gate_no_change(self):
        design = [chk("reference_side", False), chk("part_review", False)]
        for s in (P.stage_of(self.refs, self.opts, False), P.stage_of([dict(self.refs[0], iou=0.95)], self.opts, True)):
            out, gate = P.apply_gate(list(design), s)
            self.assertIsNone(gate)
            self.assertEqual(out, design)


class TestCoverageCommand(unittest.TestCase):
    def run_main(self, root, asset):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = C.main([asset, "--root", root])
        lines = buf.getvalue().strip().splitlines()
        return code, lines[:-1], json.loads(lines[-1])

    def test_the_table_and_its_verdict(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "assets", "models"))
            os.makedirs(os.path.join(root, "refs"))
            brief = answered().replace("  1. <answer>", "  1. wolf head | relief | sculpted | side.png 10,10,52,40\n"
                                                         "  2. grip | code | wrap | refs/grip.png 0,0,90,30 | 30 mm")
            with open(os.path.join(root, "assets", "models", "axe.brief.md"), "w", encoding="utf-8") as fh:
                fh.write(brief)
            with open(os.path.join(root, "assets", "models", "axe_side.trace.json"), "w", encoding="utf-8") as fh:
                json.dump(trace("refs/side.png", 700), fh)
            with open(os.path.join(root, "refs", "axe.spec.json"), "w", encoding="utf-8") as fh:
                json.dump({"length_mm": 700}, fh)
            code, table, out = self.run_main(root, "axe")
            self.assertEqual(code, 0)
            self.assertEqual(out["status"], "pass")
            self.assertTrue(table[0].startswith("feature"))
            self.assertEqual(len(table), 3)
            self.assertIn("LOW: wolf head: 1.0 px/mm at best (side.png)", out["summary"])
            self.assertTrue(out["next_action"].startswith("wolf head: 1.0 px/mm at best (side.png) — ask the owner"))

    def test_nothing_to_measure_says_what_to_write(self):
        with tempfile.TemporaryDirectory() as root:
            code, table, out = self.run_main(root, "nothing")
            self.assertEqual((code, table), (0, []))
            self.assertIn("nothing to measure — no brief", out["summary"])
            self.assertIn("hero features", out["next_action"])


if __name__ == "__main__":
    unittest.main()
