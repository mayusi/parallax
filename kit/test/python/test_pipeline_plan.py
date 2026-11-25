"""kit/tools/plan.py (`kit plan <asset>`): the 3D pipeline's eight stages for one asset, read from its files — the
brief and its parts plan, traced views (photo or reference model), the reference models it cites or measured under
its name, generated drafts, the last verdicts' failing checks by the stage that fixes them, fitted proportions, the
judges' verdict, the showcase — and the first stage that is not done. On a temporary project."""

import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import plan as PL  # noqa: E402

BRIEF = """# x — the brief
- what: a pistol (Example 17)
- end goal: master
- quality: hero
- quality bar: https://example.org/a
- style: realistic PBR
- view: first person; the left side faces the camera
- function: the main parts move
- moving parts: Slide (racks back); Trigger (pulls)
- extras: a magazine
- references: refs/x_side.png
- ownership: the owner's own
- hero features:
  1. the slide | code | serrations, the port
  2. the grip | procedural | textured panels
"""

SCRIPT = """import rbx
a = rbx.Asset("x", quality="hero", stage="master")
a.material("steel", **rbx.finish("blued_steel"))
a.material("grey", color=(0.5, 0.5, 0.5))
a.cad("Slide", "x_slide.py", "steel")
a.cad("Frame", "x_frame.py", "grey")
a.trace_match("x_photo_side", parts={"slide": ["Slide"]})
a.joint("Slide", "slide", "slide", axis=(0, 0, 1), max=0.3)
a.joint("Trigger", "trigger", "hinge", axis=(1, 0, 0), max=12)
a.cut("Slide", a.text("Mark", "EX 17", (0, 0, 0), "engraving", depth=0.002))
a.build()
"""


class Project:
    """a temporary project with assets/models, refs, .verify and build/"""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for d in ("assets/models", "refs", ".verify", "build/showcase/x"):
            os.makedirs(os.path.join(self.root, d), exist_ok=True)

    def write(self, rel, text, mtime=None):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text if isinstance(text, str) else json.dumps(text))
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def trace(self, name, view=None, source=None, mtime=None):
        t = {"source": source or f"refs/{name}.png", "outline": [[0, 0], [1, 0], [1, 1]]}  # (kit trace's own key)
        if view:
            t["view"] = view
        self.write(f"assets/models/{name}.trace.json", t, mtime)

    def verdict(self, chain, design=(), summary="ok", status="pass", stage=None, mtime=None):
        r = {"status": status, "summary": summary, "next_action": "fix the first one",
             "design": [{"name": n, "ok": False, "severity": sev} for n, sev in design],
             "facts": {"stage": stage} if stage else {}}
        self.write(f".verify/{chain}.json", {"status": status, "steps": [{"name": chain, "result": r}]}, mtime)

    def looked(self, *names, verdict="ok"):
        """`kit pack x looked <trace> ok` for each trace (kit plan's gather lock: a trace is data once looked at)"""
        sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
        import pack as PK  # noqa: PLC0415

        path = os.path.join(self.root, "assets", "models", "x.pack.json")
        data = json.load(open(path, encoding="utf-8")) if os.path.isfile(path) else {}
        for n in names:
            sha = PK.file_sha(os.path.join(self.root, "assets", "models", f"{n}.trace.json"))
            data.setdefault("looked", {})[n] = {"verdict": verdict, "sha": sha}
        self.write("assets/models/x.pack.json", data)

    def study(self, n=3):
        """a passing reference study (kit study: kit plan's gather lock reads every reference before the shape)"""
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_study as TS  # noqa: PLC0415

        refs = [self.write(f"refs/study_{i}.png", "png") and f"refs/study_{i}.png" for i in range(n)]
        self.write("assets/models/x.study.md", TS.study_text(refs))

    def stages(self, asset="x"):
        return {st["key"]: st for st in PL.assess(PL.facts(asset, self.root))}

    def close(self):
        self.tmp.cleanup()


class TestPlan(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.t0 = time.time() - 1000

    def tearDown(self):
        self.p.close()

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = PL.main(["x", "--root", self.p.root, *args])
        lines = out.getvalue().strip().splitlines()
        return code, json.loads(lines[-1]), out.getvalue()

    def test_no_asset_fails_with_the_command_that_makes_one(self):
        code, v, _ = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(v["status"], "fail")
        self.assertIn("kit new asset x", v["next_action"])

    def test_a_hero_with_only_a_brief_and_a_script_starts_at_the_parts_plan(self):
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT)
        st = self.p.stages()
        self.assertEqual(st["brief"]["status"], PL.PARTIAL)
        self.assertIn("no parts plan", st["brief"]["missing"])
        self.assertEqual(st["gather"]["status"], PL.TODO)
        self.assertIn("no traced front, side, top view", st["gather"]["missing"])
        self.assertEqual(st["draft"]["status"], PL.TODO)
        self.assertEqual(st["shape"]["status"], PL.TODO)  # no build yet
        code, v, text = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(v["status"], "pass")
        self.assertIn("next is stage 0 brief", v["summary"])
        self.assertIn("parts plan", v["next_action"])
        self.assertIn("next — stage 0 Brief", text)

    def test_the_parts_plan_is_read_with_its_routes(self):
        self.p.write("assets/models/x.brief.md", BRIEF + "\n- parts plan:  (help)\n"
                     "  1. Slide | code | a.cad from the side trace | blued steel\n"
                     "  2. Grip panel | code | the sculpted floral carving | wood\n")
        self.p.write("assets/models/build_x.py", SCRIPT)
        f = PL.facts("x", self.p.root)
        self.assertEqual([x["name"] for x in f["parts_plan"]], ["Slide", "Grip panel"])
        st = self.p.stages()
        self.assertNotIn("no parts plan", st["brief"]["missing"])
        self.assertTrue(any("Grip panel: code alone, but it is sculpted" in m for m in st["brief"]["missing"]),
                        st["brief"]["missing"])  # a sculpted part built from code ALONE is named
        self.assertIn("parts plan: 2 part(s), 0 with a multi-module shape", st["brief"]["found"])

    def test_a_stack_of_several_modules_is_read_and_a_sculpted_part_may_use_code_with_a_generator(self):
        self.p.write("assets/models/x.brief.md", BRIEF + "\n- parts plan:\n"
                     "  1. Grip panel | code + generated: the draft's panel, a.cad seat | refs | scan, pattern\n"
                     "  2. Pin | the ISO row | steel\n")
        self.p.write("assets/models/build_x.py", SCRIPT)
        plan = PL.facts("x", self.p.root)["parts_plan"]
        self.assertEqual(plan[0]["routes"], ["code", "generated"])
        st = self.p.stages()["brief"]
        self.assertIn("parts plan: 2 part(s), 1 with a multi-module shape", st["found"])
        self.assertEqual(st["missing"], ["stacks: Pin: no shape modules (the 2nd field: code · sculpt · generated · "
                                         "relief · projected · procedural); Pin: no surface (the 4th field: finish, "
                                         "scan, pattern, markings)"])

    def test_a_sculpted_part_names_its_route_and_a_description_word_is_no_alias(self):
        self.p.write("assets/models/x.brief.md", BRIEF + "\n- parts plan:\n"
                     "  1. Head | sculpted: a.sculpt from the views | refs | skin look\n"
                     "  2. Panel | code: the draft's texture as a guide | refs | paint\n")
        plan = PL.facts("x", self.p.root)["parts_plan"]
        self.assertEqual(plan[0]["routes"], ["sculpt"])
        self.assertEqual(plan[1]["routes"], ["code"])   # ("texture" in a description is no projection)

    def test_route_words_count_only_in_the_shape_field(self):
        plan = PL.parts_plan(BRIEF + "\n- parts plan:\n  1. Feather crest | code | the 3/4 picture | projected detail\n")
        self.assertEqual(plan[0]["routes"], ["code"])  # its surface's "projected" is no shape module
        self.assertEqual(PL.stack_problems(plan), [("Feather crest", "code alone, but it is feather")])
        plan = PL.parts_plan(BRIEF + "\n- parts plan:\n  1. Feather crest | code + relief | the 3/4 picture | scan\n")
        self.assertEqual(PL.stack_problems(plan), [])  # sculpted, with a relief in its stack: fine

    def test_moving_parts_split_at_the_top_level_only(self):
        self.assertEqual(PL.moving_parts("slide (racks 32 mm, after the hammer is cocked), barrel (follows it 3 mm); "
                                         "trigger"), ["slide (racks 32 mm, after the hammer is cocked)",
                                                      "barrel (follows it 3 mm)", "trigger"])
        self.assertEqual(PL.moving_parts("none"), [])

    def test_absent_questions_and_no_hero_features_are_named(self):
        self.p.write("assets/models/x.brief.md", "- what: a pistol\n- quality: hero\n")
        self.p.write("assets/models/build_x.py", SCRIPT)
        b = self.p.stages()["brief"]
        joined = " ".join(b["missing"])
        self.assertIn("questions the brief does not have: end_goal, quality_bar, style, view", joined)
        self.assertEqual(b["status"], PL.PARTIAL)

    def test_a_template_docstring_is_never_read_as_calls(self):
        with open(os.path.join(ROOT, "kit", "templates", "asset.py"), encoding="utf-8") as fh:
            template = fh.read().replace("__NAME__", "x")
        s = PL.read_script(template)
        self.assertEqual((s["imports"], s["params"], s["cad"], s["pack"]), ([], 0, 0, 0))
        broken = template + "\na.param('len', 2.4\n"  # mid-edit: does not parse -> read as text, prose taken out
        s = PL.read_script(broken)
        self.assertEqual((s["imports"], s["cad"]), ([], 0))
        self.assertEqual(s["params"], 1)

    def test_a_parts_plan_right_under_the_hero_features_is_still_the_parts_plan(self):
        text = BRIEF + "- parts plan:\n  1. Slide | code | a.cad | steel\n- draft: none — a flat sign\n"
        plan = PL.parts_plan(text)
        self.assertEqual([x["name"] for x in plan], ["Slide"])
        heroes = PL.P.parse_brief(text)["hero_features"]
        self.assertEqual([h["name"] for h in heroes], ["the slide", "the grip"])  # neither question is a feature
        self.assertEqual(PL.P.parse_brief(text)["answers"]["draft"], "none — a flat sign")

    def test_the_template_asks_for_the_parts_plan_and_the_draft_without_new_placeholders(self):
        with open(os.path.join(ROOT, "kit", "templates", "asset.brief.md"), encoding="utf-8") as fh:
            template = fh.read()
        self.assertIn("- parts plan:", template)
        self.assertIn("- draft:", template)
        self.assertEqual(PL.parts_plan(template), [])  # asked, not yet answered
        self.assertEqual(PL.P.unanswered_count(template), 12)  # optional: no new <answer> a prop must fill

    def test_traced_views_by_name_and_source(self):
        self.p.trace("x_photo_side")
        self.p.trace("x_scan_front", source="build/refs/x_scan_front_mask.png")
        self.p.trace("x_side_left", view="side_left")
        views = PL.traced_views("x", self.p.root, {})
        self.assertEqual(views["side"], ["photo"])
        self.assertEqual(views["front"], ["model"])
        self.assertIn("side_left", views)  # (its own view: the other flank)

    def test_a_view_only_one_reference_model_shows_needs_a_photo_two_models_suffice(self):
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT)
        self.p.trace("x_photo_side")
        for v in ("front", "top"):
            self.p.trace(f"x_scan_{v}", source=f"build/refs/x_scan_{v}_mask.png")
        self.p.write("refs/private/x/x_scan.measure.json", {"length_mm": 186})
        st = self.p.stages()
        self.assertEqual(st["gather"]["status"], PL.PARTIAL)
        self.assertTrue(any(m.startswith("only ONE reference model shows: front, top") for m in
                            st["gather"]["missing"]), st["gather"]["missing"])
        self.p.write("refs/other_pistol.inspect.json", {"parts": []})
        self.p.write("assets/models/x.parts.md", "- Slide [fp]: real: x | ref: refs/other_pistol.inspect.json\n")
        st = self.p.stages()
        self.assertFalse(any(m.startswith("only ONE reference model") for m in st["gather"]["missing"]))
        self.assertIn("reference models: 2 (other_pistol, x_scan)", st["gather"]["found"])
        # (and with a sourced size and measured colours the hero's gather is done)
        self.p.write("assets/models/x.pack.json", {"object": {"length_mm": 202, "source": "dims:len1"},
                                                   "colours": {"slide": {"srgb": [0.1, 0.1, 0.1]}}})
        self.p.looked("x_photo_side", "x_scan_front", "x_scan_top")  # (and every trace looked at)
        self.p.study()  # (and the references read: the study)
        self.assertEqual(self.p.stages()["gather"]["status"], PL.DONE, self.p.stages()["gather"]["missing"])

    def test_a_heros_gather_needs_a_model_a_sourced_size_measured_colours_and_measured_pictures(self):
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT, mtime=self.t0)
        for v in ("side", "front", "top"):
            self.p.trace(f"x_photo_{v}")
        cov = {"features": [{"name": "the slide", "hero": True, "low": False, "best_px_per_mm": 6.1},
                            {"name": "the grip", "hero": True, "low": False, "best_px_per_mm": None}]}
        r = {"status": "pass", "summary": "ok", "design": [], "facts": {"coverage": cov}}
        self.p.write(".verify/asset-geo-x.json", {"steps": [{"result": r}]}, mtime=self.t0 + 10)
        g = self.p.stages()["gather"]
        self.assertEqual(g["status"], PL.PARTIAL)
        joined = " ".join(g["missing"])
        for gap in ("no reference model measured", "no sourced size", "colours not measured",
                    "1 hero feature(s) with NO measured picture"):
            self.assertIn(gap, joined)
        self.p.write("assets/models/x.brief.md", BRIEF + "\n- reference models: none — a one-off prop, no model exists\n")
        self.assertNotIn("no reference model measured", " ".join(self.p.stages()["gather"]["missing"]))

    def test_a_hero_with_a_reference_model_is_cut_beside_it(self):
        # the Glock's frame: solid where the real one is a U-shell, right from every side — only its cross-sections
        # beside the reference model showed it (kit refs sections, 2026-10-10)
        lib = "0200c248eba14385ad2bee8d4dc4e586"
        self.p.write("refs/private/x_scan.measure.json", {"name": "x_scan", "source": f"../../cache/library/{lib}/model.glb"})
        self.p.write("assets/models/build_x.py", SCRIPT, mtime=self.t0)
        self.p.verdict("asset-geo-x", mtime=self.t0 + 10)
        self.assertEqual(PL.reference_sources(["x_scan"], self.p.root), {"x_scan": lib})
        shape = self.p.stages()["shape"]
        self.assertTrue(any("never cut beside its reference model (x_scan)" in m for m in shape["missing"]), shape)
        self.assertTrue(any(f"kit refs sections x --ref {lib}" in c for c in shape["commands"]))
        self.assertEqual(shape["status"], PL.PARTIAL)
        rows = [{"d": 1.0, "p90": 0.4}, {"d": 6.0, "p90": 2.1}]
        self.p.write("build/refs/x_sections.json", {"ref": lib, "rows": rows}, mtime=self.t0 + 20)
        shape = self.p.stages()["shape"]
        self.assertIn(f"cross-sections vs {lib}: 2 stations, worst p90 2.1 mm, 1 over 1.5 mm", shape["found"])
        self.assertFalse(any("never cut" in m for m in shape["missing"]))
        self.assertIn("(advised) 1 cross-section station(s) over 1.5 mm from the reference model", shape["missing"])
        self.p.write("build/refs/x_sections.json", "{not json", mtime=self.t0 + 20)
        self.assertIsNone(PL.sections_report("x", self.p.root))   # (a broken report never crashes the plan)

    def test_an_own_build_inspection_is_no_reference_model(self):
        self.p.write("refs/private/x_build.inspect.json", {})
        self.assertEqual(PL.own_reference_models("x", self.p.root), set())

    def test_a_draft_is_a_generator_record_or_the_brief_saying_why_not(self):
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT)
        self.assertEqual(self.p.stages()["draft"]["status"], PL.TODO)
        self.p.write("assets/models/x_draft.gen.json", {"engine": "pixal3d"})
        self.assertEqual(self.p.stages()["draft"]["status"], PL.DONE)
        os.remove(os.path.join(self.p.root, "assets/models/x_draft.gen.json"))
        self.p.write("assets/models/x.brief.md", BRIEF + "\n- draft: none — a flat sign, nothing to sculpt\n")
        st = self.p.stages()["draft"]
        self.assertEqual(st["status"], PL.DONE)
        self.assertIn("a flat sign", st["found"][0])

    def test_failing_checks_go_to_the_stage_that_fixes_them(self):
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT, mtime=self.t0)
        self.p.verdict("asset-geo-x", design=[("cad_solid", "error"), ("part_match_side", "error"),
                                              ("roughness_variation", "warn"), ("disassembly", "error"),
                                              ("part_review", "error")],
                       summary="GEO check · main.manifold=4 (limit 0)", status="fail")
        st = self.p.stages()
        shape = st["shape"]
        self.assertEqual(shape["status"], PL.PARTIAL)
        self.assertIn("failing: cad_solid, part_match_side, main.manifold", shape["missing"])
        self.assertTrue(any("disassembly" in m for m in st["mechanism"]["missing"]))
        self.assertFalse(any("roughness" in m for m in shape["missing"]))  # a warning, and the surface's

    def test_a_blockout_stage_is_named_first(self):
        self.p.write("assets/models/build_x.py", SCRIPT, mtime=self.t0)
        self.p.verdict("asset-geo-x", design=[("stage", "error")], status="fail",
                       stage={"stage": "blockout", "views": [{"view": "side", "iou": 0.62, "bar": 0.9}]})
        shape = self.p.stages()["shape"]
        self.assertTrue(shape["missing"][0].startswith("failing: stage: blockout"), shape["missing"])
        self.assertIn("views: side IoU 0.62", shape["found"])

    def test_sculpts_are_counted_and_their_lost_detail_is_the_shape_s(self):
        self.p.write("assets/models/build_x.py", SCRIPT + 's = a.sculpt("Head", "steel")\ns.ball((0, 0, 0), 10)\n'
                     's.done()\n', mtime=self.t0)
        self.p.verdict("asset-geo-x", design=[("sculpt_detail", "warn")], mtime=self.t0 + 10)
        shape = self.p.stages()["shape"]
        self.assertTrue(shape["found"][0].startswith("2 a.cad call(s), 1 sculpt(s), 0 imported mesh(es)"), shape)
        self.assertIn("sculpt_detail", PL.SHAPE_CHECKS)

    def test_a_heros_surface_asks_for_looks_and_a_life(self):
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT, mtime=self.t0)
        self.p.verdict("asset-x", mtime=self.t0 + 10)
        surf = self.p.stages()["surface"]
        self.assertIn("(advised) no material has a life: every surface as it left the factory", surf["missing"])
        self.assertTrue(any("rbx.look" in c for c in surf["commands"]))
        worn = SCRIPT.replace('a.material("grey", color=(0.5, 0.5, 0.5))',
                              'a.material("grey", **rbx.look("powder_coat", color=(0.5, 0.5, 0.5)), life="used")')
        self.p.write("assets/models/build_x.py", worn, mtime=self.t0)
        f = PL.facts("x", self.p.root)
        self.assertIn("grey", f["s"]["materials_from_data"])   # (a look is data)
        self.assertEqual(f["s"]["materials_worn"], ["grey"])
        self.assertNotIn("(advised) no material has a life: every surface as it left the factory",
                         self.p.stages()["surface"]["missing"])

    def test_a_script_newer_than_its_last_build_is_said(self):
        self.p.write("assets/models/build_x.py", SCRIPT)
        self.p.verdict("asset-geo-x", mtime=self.t0)
        self.assertIn("the script changed since the last build", self.p.stages()["shape"]["missing"])

    def test_declared_proportions_must_be_fitted(self):
        self.p.write("assets/models/build_x.py", SCRIPT + 'L = a.param("len", 2.4, lo=1.8, hi=3.0)\n', mtime=self.t0)
        self.p.verdict("asset-geo-x")
        shape = self.p.stages()["shape"]
        self.assertIn("1 a.param() proportion(s) never fitted", shape["missing"])
        self.assertTrue(any("kit fit x --write" in c for c in shape["commands"]))
        self.p.write("assets/models/x.params.json", {"params": {"len": 2.5}})
        self.assertNotIn("1 a.param() proportion(s) never fitted", self.p.stages()["shape"]["missing"])

    def test_a_static_prop_needs_no_mechanism(self):
        self.p.write("assets/models/build_x.py", 'a = rbx.Asset("x")\na.box("B", (1, 1, 1), (0, 0, 0), "m")\n')
        self.assertEqual(self.p.stages()["mechanism"]["status"], PL.NOT_NEEDED)
        brief = BRIEF.replace("- moving parts: Slide (racks back); Trigger (pulls)", "- moving parts: none")
        brief = brief.replace("- function: the main parts move", "- function: static")
        self.p.write("assets/models/x.brief.md", brief)
        self.assertEqual(self.p.stages()["mechanism"]["status"], PL.NOT_NEEDED)

    def test_moving_parts_need_their_joints(self):
        self.p.write("assets/models/x.brief.md", BRIEF.replace("Trigger (pulls)", "Trigger (pulls); Magazine (drops)"))
        self.p.write("assets/models/build_x.py", SCRIPT)
        mech = self.p.stages()["mechanism"]
        self.assertEqual(mech["status"], PL.DONE)  # (a count read from free text is a hint, never a gate)
        self.assertTrue(mech["missing"][0].startswith("(advised) the brief names 3 moving part(s), 2 a.joint call(s)"))

    def test_every_stage_done_ends_the_plan(self):
        t = self.t0
        self.p.write("assets/models/x.brief.md", BRIEF + "\n- parts plan:\n  1. Slide | code | a.cad | steel\n"
                     "  2. Frame | code | a.cad | polymer\n")
        self.p.write("assets/models/build_x.py", SCRIPT.replace('color=(0.5, 0.5, 0.5)', '**rbx.real("Iron")')
                     .replace('a.trace_match("x_photo_side"', 'a.trace_match("x_photo_side", albedo="a.npz"'),
                     mtime=t)
        for v in ("side", "front", "top"):
            self.p.trace(f"x_photo_{v}")
        self.p.looked("x_photo_side", "x_photo_front", "x_photo_top")
        self.p.study()
        self.p.write("refs/x_scan.measure.json", {})
        self.p.write("refs/other.inspect.json", {})
        self.p.write("refs/x.spec.json", {"parts": []})
        self.p.write("assets/models/x.parts.md", "- Slide [fp]: ref: refs/other.inspect.json dims:slide_len | "
                     "verdict: ok\n")
        self.p.write("assets/models/x_draft.gen.json", {})
        self.p.verdict("asset-geo-x", mtime=t + 10)
        self.p.verdict("asset-x", mtime=t + 20)
        self.p.write("assets/models/x.review.md", "iteration: 1\n")
        self.p.write("assets/models/x.judge.json", {}, mtime=t + 30)
        self.p.write("build/showcase/x/poster.png", "png", mtime=t + 40)
        # (the model sheet and the blockout, stages since 2026-11-11, are proven on a project with a real picture in
        #  test_sheet.py; this one's pictures are placeholders, so the owner's waiver of both steps stands in here)
        self.p.write("board/locks.json", {"waivers": {"3d": {"x": {"by": "owner", "words": "no sheet for this one",
                                                                  "steps": ["sheet", "blockout"]}}}})
        stages = PL.assess(PL.facts("x", self.p.root))
        not_done = [(s["key"], s["status"], s["missing"]) for s in stages
                    if s["status"] not in (PL.DONE, PL.NOT_NEEDED)]
        self.assertEqual(not_done, [])
        self.assertEqual([s["key"] for s in stages if s["status"] == PL.NOT_NEEDED], ["sheet", "blockout"])
        self.assertIsNone(PL.next_stage(stages))
        code, v, _ = self.run_main()
        self.assertEqual(v["summary"], "plan x: every stage done")

    def test_the_plan_reads_the_pack(self):
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT, mtime=self.t0)
        pack = {"object": {"name": "Example 17", "length_mm": 202, "source": "dims:len1"},
                "sizes": {"slide.length": {"mm": 186, "source": "dims:ab"}}, "colours": {"slide": {"srgb": [0.1] * 3}}}
        pack["inputs_sha"] = PL.PK.inputs_sha(pack)  # (as `kit pack` saves it)
        self.p.write("assets/models/x.pack.json", pack)
        st = self.p.stages()
        gather = st["gather"]
        self.assertIn("sourced sizes: 0 cited, 1 in the pack; real length 202 mm", gather["found"])
        self.assertIn("measured colours: 1 part(s)", gather["found"])
        self.assertFalse(any("colours not measured" in m or "no sourced size" in m for m in gather["missing"]))
        self.p.verdict("asset-geo-x", mtime=self.t0 + 10)
        shape = self.p.stages()["shape"]
        self.assertIn("(advised) the pack has sizes / colours the build never reads (typed numbers instead)",
                      shape["missing"])
        self.assertEqual(shape["status"], PL.DONE)  # (advised: said, but it never holds the next stage back)
        self.p.write("assets/models/build_x.py", SCRIPT + "pk = a.pack()\n", mtime=self.t0)
        r = {"status": "pass", "summary": "ok", "design": [], "facts": {"pack": {"x": {
            "read": 5, "kinds": ["colour", "size"], "unsourced": ["barrel.length"]}}}}
        self.p.write(".verify/asset-geo-x.json", {"steps": [{"result": r}]}, mtime=self.t0 + 10)
        shape = self.p.stages()["shape"]
        self.assertIn("reads 5 value(s) from the pack (colour, size), unsourced: barrel.length", shape["found"])
        self.assertFalse(any("never reads" in m for m in shape["missing"]))

    def test_a_downloaded_photo_under_build_refs_is_a_photo_a_measure_mask_a_model(self):
        self.p.trace("x_side", source="build/refs/glock_17_side/Glock_17.jpg")  # kit refs find saves photos here
        self.p.trace("x_scan_top", source="build/refs/x_scan_top_mask.png")    # kit refs measure's mask
        views = PL.traced_views("x", self.p.root, {})
        self.assertEqual((views["side"], views["top"]), (["photo"], ["model"]))
        self.p.write("assets/models/build_x.py", SCRIPT)
        f = PL.facts("x", self.p.root)
        self.assertEqual(f["trace_pictures"].get("side"), "build/refs/glock_17_side/Glock_17.jpg")  # its "source"
        self.assertNotIn("top", f["trace_pictures"])  # (a model's mask is no picture to take colours from)
        self.p.trace("x_photo_front", source="refs/private/x/front.png")  # any naming: <asset>_photo_<view>
        self.assertEqual(PL.facts("x", self.p.root)["trace_pictures"].get("front"), "refs/private/x/front.png")

    def test_a_blank_answer_is_named_in_the_brief(self):
        self.p.write("assets/models/x.brief.md", BRIEF.replace("- moving parts: Slide (racks back); Trigger (pulls)",
                                                               "- moving parts:"))
        self.p.write("assets/models/build_x.py", SCRIPT)
        self.assertIn("left blank: moving_parts", self.p.stages()["brief"]["missing"])

    def test_an_answer_in_brackets_or_a_numbered_list_is_no_blank(self):
        brief = (BRIEF.replace("- view: first person; the left side faces the camera",
                               "- view: (default) first person and third person, the left side")
                 .replace("- moving parts: Slide (racks back); Trigger (pulls)",
                          "- moving parts:\n  1. Slide (racks back)\n  2. Trigger (pulls)\n  3. Magazine (drops)"))
        self.p.write("assets/models/x.brief.md", brief)
        self.p.write("assets/models/build_x.py", SCRIPT)
        st = self.p.stages()
        self.assertFalse(any(m.startswith("left blank") for m in st["brief"]["missing"]), st["brief"]["missing"])
        self.assertTrue(st["mechanism"]["missing"][0].startswith("(advised) the brief names 3 moving part(s)"),
                        st["mechanism"]["missing"])

    def test_none_and_its_exceptions(self):
        for said in ("No", "no.", "No moving parts — it is a statue", "nothing — it's a prop"):
            self.assertEqual(PL.moving_parts(said), [], said)
        self.assertEqual(PL.moving_parts("none except the trigger (pulls 5 mm)"),
                         ["none except the trigger (pulls 5 mm)"])

    def test_an_unsourced_real_length_is_no_sourced_size(self):
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT)
        self.p.write("assets/models/x.pack.json", {"object": {"length_mm": 186, "source": "given",
                                                              "trust": "unsourced"}})
        g = self.p.stages()["gather"]
        self.assertIn("sourced sizes: 0 cited, 0 in the pack; real length 186 mm (UNSOURCED)", g["found"])
        self.assertTrue(any(m.startswith("no sourced size") for m in g["missing"]))

    def test_every_none_phrasing_is_no_moving_part_and_a_blank_is_no_answer(self):
        for said in ("none — it is a static crate", "none: the rest stay still", "no moving parts", "nothing moves",
                     "None.", "-", "n/a"):
            self.assertEqual(PL.moving_parts(said), [], said)
        self.assertEqual(PL.moving_parts("nozzle cap (twists)"), ["nozzle cap (twists)"])  # 'no' only as a word
        for said in ("it has no moving parts", "(none)", "—", "it doesn't move", "it does not move"):
            self.assertEqual(PL.moving_parts(said), [], said)
        self.assertEqual(PL.moving_parts("Static lid hinge (opens 90 deg)"), ["Static lid hinge (opens 90 deg)"])
        self.assertEqual(PL.moving_parts("No. 1 lever, trigger"), ["No. 1 lever", "trigger"])
        self.p.write("assets/models/build_x.py", SCRIPT.replace("a.joint", "# a.joint"))
        self.p.write("assets/models/x.brief.md", BRIEF.replace("- moving parts: Slide (racks back); Trigger (pulls)",
                                                               "- moving parts:"))
        st = self.p.stages()
        self.assertIn("the brief does not say what moves", st["mechanism"]["missing"])
        self.assertIn("left blank: moving_parts", st["brief"]["missing"])

    def test_checks_held_back_by_a_blockout_still_fail_their_stages(self):
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT, mtime=self.t0)
        self.p.verdict("asset-x", design=[("stage", "error")], status="fail", mtime=self.t0 + 10,
                       stage={"stage": "blockout", "deferred": ["colour_match", "palette", "fastener_support",
                                                                "part_review"]})
        st = self.p.stages()
        self.assertIn("failing: colour_match (held back by the blockout), palette (held back by the blockout)",
                      st["surface"]["missing"])
        self.assertTrue(any("fastener_support (held back" in m for m in st["mechanism"]["missing"]))
        self.assertTrue(any("part_review (held back" in m for m in st["look"]["missing"]))
        self.assertEqual(st["shape"]["missing"][0], "failing: stage: blockout (a traced view below its bar)")

    def test_an_unsourced_pack_size_is_no_sourced_size(self):
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT)
        self.p.write("assets/models/x.pack.json", {"sizes": {"slide.length": {"mm": 186, "source": "given",
                                                                              "trust": "unsourced"}}})
        g = self.p.stages()["gather"]
        self.assertIn("sourced sizes: 0 cited, 0 in the pack (1 UNSOURCED)", g["found"])
        self.assertTrue(any(m.startswith("no sourced size") for m in g["missing"]))

    def test_a_hand_edited_pack_is_named_from_the_pack_itself(self):
        self.p.write("assets/models/build_x.py", SCRIPT + "pk = a.pack()\n", mtime=self.t0)
        self.p.verdict("asset-geo-x", mtime=self.t0 + 10)
        pack = {"sizes": {"slide.length": {"mm": 186, "source": "dims:ab"}}}
        pack["inputs_sha"] = PL.PK.inputs_sha(pack)
        self.p.write("assets/models/x.pack.json", pack)
        self.assertFalse(any("edited by hand" in m for m in self.p.stages()["shape"]["missing"]))
        pack["sizes"]["slide.length"]["mm"] = 190  # by hand, after the build
        self.p.write("assets/models/x.pack.json", pack)
        self.assertTrue(any("edited by hand" in m for m in self.p.stages()["shape"]["missing"]))

    def test_a_list_under_the_question_is_the_parts_and_is_said_back(self):
        self.p.write("assets/models/x.brief.md", BRIEF.replace(
            "- moving parts: Slide (racks back); Trigger (pulls)",
            "- moving parts: three of them:\n  1. Slide (racks back)\n  2. Trigger (pulls)\n  3. Magazine (drops)"))
        self.p.write("assets/models/build_x.py", SCRIPT)
        mech = self.p.stages()["mechanism"]
        self.assertIn("moving parts read as: 3: Slide (racks back); Trigger (pulls); Magazine (drops)", mech["found"])

    def test_a_blank_that_kept_the_templates_help_or_a_star_bullet_is_blank(self):
        brief = BRIEF.replace("- view: first person; the left side faces the camera",
                              "- view:  (how players see it: first person · third person · world prop)")
        brief = brief.replace("- style: realistic PBR", "* style:")
        self.p.write("assets/models/x.brief.md", brief)
        self.p.write("assets/models/build_x.py", SCRIPT)
        self.assertIn("left blank: style, view", self.p.stages()["brief"]["missing"])

    def test_list_items_are_one_part_each_wrapped_or_with_commas(self):
        brief = BRIEF.replace("- moving parts: Slide (racks back); Trigger (pulls)",
                              "- moving parts:\n  1. Slide (racks 30 mm back, the barrel\n     tips with it)\n"
                              "  2. the lid, hinged at the back (opens 110 deg)\n  3. Magazine")
        self.p.write("assets/models/x.brief.md", brief)
        self.p.write("assets/models/build_x.py", SCRIPT)
        mech = self.p.stages()["mechanism"]
        self.assertTrue(mech["missing"][0].startswith("(advised) the brief names 3 moving part(s)"), mech["missing"])

    def test_an_answer_in_brackets_and_exceptions_and_markdown(self):
        self.assertEqual(PL.moving_parts("none, except the lid (opens 110 deg)"), ["the lid (opens 110 deg)"])
        self.assertEqual(PL.moving_parts("None, but it must look heavy"), [])
        self.assertEqual(PL.moving_parts("**none**"), [])
        self.p.write("assets/models/x.brief.md", BRIEF.replace("- moving parts: Slide (racks back); Trigger (pulls)",
                                                               "- moving parts: (none — it is a solid prop)")
                     .replace("- function: the main parts move", "- function: static"))
        self.p.write("assets/models/build_x.py", SCRIPT.replace("a.joint", "# a.joint"))
        self.assertEqual(self.p.stages()["mechanism"]["status"], PL.NOT_NEEDED)

    def test_a_hand_broken_pack_never_crashes_the_plan(self):
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT + "pk = a.pack()\n")
        for broken in ({"sizes": {"slide.length": 186}, "object": "glock 17"}, [1, 2], {"colours": [1]}):
            self.p.write("assets/models/x.pack.json", broken)
            code, v, _ = self.run_main()
            self.assertEqual((code, v["status"]), (0, "pass"), broken)

    def test_read_as_never_cuts_silently(self):
        many = "; ".join(f"part{k}" for k in range(11))
        self.p.write("assets/models/x.brief.md", BRIEF.replace("Slide (racks back); Trigger (pulls)", many))
        self.p.write("assets/models/build_x.py", SCRIPT)
        found = " ".join(self.p.stages()["mechanism"]["found"])
        self.assertIn("moving parts read as: 11: part0", found)
        self.assertIn("(+3 more)", found)

    def test_a_fresh_brief_reads_as_not_said_never_as_a_part(self):
        with open(os.path.join(ROOT, "kit", "templates", "asset.brief.md"), encoding="utf-8") as fh:
            self.p.write("assets/models/x.brief.md", fh.read())
        self.p.write("assets/models/build_x.py", SCRIPT)
        mech = self.p.stages()["mechanism"]
        self.assertIn("moving parts read as: not said", " ".join(mech["found"]))
        self.assertFalse(any("<answer>" in m for m in mech["missing"]), mech["missing"])

    def test_the_templates_help_after_an_answer_is_cut_and_only_is_no_exception(self):
        self.assertEqual(PL._raw_answer("moving_parts", "- moving parts: (none — solid prop)  (only the ones gameplay "
                                        "needs, each with what it does)"), "(none — solid prop)")
        for said in ("none — this is only a display piece", "None. Only the look matters", "no (decorative only)",
                     "static — besides, it hangs on a wall"):
            self.assertEqual(PL.moving_parts(said), [], said)

    def test_a_none_line_wins_over_notes_under_it(self):
        self.p.write("assets/models/x.brief.md", BRIEF.replace("- moving parts: Slide (racks back); Trigger (pulls)",
                                                               "- moving parts: none\n  - it is a static prop")
                     .replace("- function: the main parts move", "- function: static"))
        self.p.write("assets/models/build_x.py", SCRIPT.replace("a.joint", "# a.joint"))
        self.assertEqual(self.p.stages()["mechanism"]["status"], PL.NOT_NEEDED)

    def test_the_question_line_decides_never_a_wrapped_items_tail(self):
        brief = BRIEF.replace("- moving parts: Slide (racks back); Trigger (pulls)",
                              "- moving parts:\n  1. Barrel (tips 2 mm; the bushing stays\n     static)\n"
                              "  2. Slide (racks 30 mm)")
        self.p.write("assets/models/x.brief.md", brief)
        self.p.write("assets/models/build_x.py", SCRIPT)
        mech = self.p.stages()["mechanism"]
        self.assertNotEqual(mech["status"], PL.NOT_NEEDED)
        self.assertIn("moving parts read as: 2:", " ".join(mech["found"]))
        brief = BRIEF.replace("- moving parts: Slide (racks back); Trigger (pulls)",
                              "- moving parts: lid, latch\n  - the owner wants it slow")
        self.p.write("assets/models/x.brief.md", brief)
        self.assertIn("moving parts read as: 2: lid; latch", " ".join(self.p.stages()["mechanism"]["found"]))

    def test_an_answers_own_wrapped_lines_count_and_lead_ins_hand_over_to_the_list(self):
        def read(moving_line):
            self.p.write("assets/models/x.brief.md", BRIEF.replace(
                "- moving parts: Slide (racks back); Trigger (pulls)", moving_line))
            self.p.write("assets/models/build_x.py", SCRIPT)
            return " ".join(self.p.stages()["mechanism"]["found"])
        self.assertIn("read as: 4:", read("- moving parts: slide (racks), trigger (pulls),\n  magazine (drops), "
                                          "hammer (cocks)\n  - the owner wants the reload slow"))
        self.assertIn("read as: 3: lid (opens); latch (flips up 90 deg); handle (folds)",
                      read("- moving parts: lid (opens), latch\n  (flips up 90 deg), handle (folds)"))
        self.assertIn("read as: 2: Slide; Trigger", read("- moving parts: see below\n  1. Slide\n  2. Trigger"))

    def test_moving_parts_with_no_joint_at_all_is_a_real_miss(self):
        self.p.write("assets/models/x.brief.md", BRIEF.replace(
            "- moving parts: Slide (racks back); Trigger (pulls)",
            "- moving parts: lid (opens 110 deg on its hinges), latch (flips up 90 deg)")
            .replace("- function: the main parts move", "- function: the lid and latch move"))
        self.p.write("assets/models/build_x.py", SCRIPT.replace("a.joint", "# a.joint"), mtime=self.t0)
        self.assertNotEqual(self.p.stages()["mechanism"]["status"], PL.DONE)
        self.p.verdict("asset-geo-x", mtime=self.t0 + 10)
        mech = self.p.stages()["mechanism"]
        self.assertNotEqual(mech["status"], PL.DONE)
        self.assertTrue(mech["missing"][0].startswith("the brief names moving parts and the build has no joint"))
        self.assertIsNotNone(PL.next_stage(PL.assess(PL.facts("x", self.p.root))))

    def test_a_static_function_never_asks_for_joints(self):
        for said in ("none at all", "None needed", "static prop", "the lid sits closed"):
            self.p.write("assets/models/x.brief.md", BRIEF.replace(
                "- moving parts: Slide (racks back); Trigger (pulls)", f"- moving parts: {said}")
                .replace("- function: the main parts move", "- function: static"))
            self.p.write("assets/models/build_x.py", SCRIPT.replace("a.joint", "# a.joint"))
            self.assertEqual(self.p.stages()["mechanism"]["status"], PL.NOT_NEEDED, said)

    def test_a_length_that_is_no_number_never_crashes(self):
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT)
        self.p.write("assets/models/x.pack.json", {"object": {"length_mm": "186 mm", "source": "dims:a"}})
        code, v, _ = self.run_main()
        self.assertEqual((code, v["status"]), (0, "pass"))

    def test_check_families(self):
        self.assertEqual(PL._family("part_match_side_left"), "shape")
        self.assertEqual(PL._family("projection_alignment"), "surface")
        self.assertEqual(PL._family("clear:Bore"), "mechanism")
        self.assertEqual(PL._family("expect:grip_touches"), "shape")
        self.assertIsNone(PL._family("part_review"))



class TestPlanDossier(unittest.TestCase):
    """a hero with a REAL object in its pack gathers only once the object's dossier is approved and current"""

    def setUp(self):
        self.p = Project()
        self.p.write("assets/models/x.brief.md", BRIEF)
        self.p.write("assets/models/build_x.py", SCRIPT)
        pack = {"object": {"name": "Glock 17 Gen5", "length_mm": 202, "source": "dossier:glock_17_gen5:overall.length",
                           "trust": "high"}}
        pack["inputs_sha"] = PL.PK.inputs_sha(pack)
        self.p.write("assets/models/x.pack.json", pack)

    def gather(self, summary):
        from unittest import mock  # noqa: PLC0415

        with mock.patch.object(PL, "dossier_summary", return_value=summary):
            return self.p.stages()["gather"]

    def test_no_dossier_is_a_gap_with_its_command(self):
        g = self.gather(None)
        self.assertTrue(any(m.startswith("no dossier for 'Glock 17 Gen5'") for m in g["missing"]), g["missing"])
        self.assertTrue(any('kit dossier new "Glock 17 Gen5"' in c for c in g["commands"]), g["commands"])

    def test_an_unapproved_or_stale_dossier_holds_gather_back_an_approved_one_does_not(self):
        ds = {"slug": "glock_17_gen5", "score": 84.0, "bar": 80.0, "approved": False, "stale": False, "open": [],
              "problems": [], "missing": []}
        g = self.gather(ds)
        self.assertIn("dossier glock_17_gen5: 84/100 (bar 80), not approved, 0 open", g["found"])
        self.assertIn("the owner has not approved the dossier's reference sheet", g["missing"])
        g = self.gather({**ds, "approved": True, "stale": True})
        self.assertIn("the owner has not approved the dossier's reference sheet (it changed since)", g["missing"])
        g = self.gather({**ds, "approved": True})
        self.assertFalse(any("dossier" in m for m in g["missing"]), g["missing"])

    def test_a_broken_dossier_is_said_never_a_crash(self):
        g = self.gather({"error": "ValueError: bad json"})
        self.assertIn("the dossier for 'Glock 17 Gen5' could not be read: ValueError: bad json", g["missing"])

    def test_a_real_broken_dossier_file_is_read_as_broken_not_as_none(self):
        sys.path.insert(0, os.path.join(ROOT, "kit", "refs"))
        import dossier  # noqa: PLC0415

        from unittest import mock  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "glock_17_gen5.json"), "w") as fh:
                fh.write("{broken")
            with mock.patch.object(dossier, "PRIVATE", tmp), mock.patch.object(dossier, "KNOW",
                                                                               os.path.join(tmp, "none")):
                g = self.p.stages()["gather"]
        self.assertTrue(any(m.startswith("the dossier for 'Glock 17 Gen5' could not be read: Broken") for m in
                            g["missing"]), g["missing"])


PROP_BRIEF = """# x — the brief
- what: a wooden barrel
- end goal: master
- quality: prop
- quality bar: https://example.org/b
- style: realistic PBR
- view: world prop
- function: static
- moving parts: none
- extras: none
- references: refs/x_side.png
- ownership: the owner's own
- hero features:
  1. the staves | generated | bent oak staves
- parts plan:
  1. Body | code: staves, hoops and heads from the measured profile | the side photo, 2 dissected barrels | oak scan, iron hoops
- draft: assets/models/x_draft.gen.json
"""

PROP_SCRIPT = """import rbx
a = rbx.Asset("x", quality="prop")
a.import_mesh("Body", "assets/models/x_draft.glb", size=(1, 1, 1))
a.build()
"""


class TestStageLocks(unittest.TestCase):
    """the route is LOCKED (mission 01-3d §5.1-5.4, 5.15): `kit plan <asset> --stage <key>` refuses a stage while an
    earlier one is not done, naming what is missing; the clock stops everything but the look at the tier's budget"""

    def setUp(self):
        self.p = Project()

    def tearDown(self):
        self.p.close()

    def main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = PL.main(["x", "--root", self.p.root, *args])
        return code, json.loads(out.getvalue().strip().splitlines()[-1]), out.getvalue()

    def prop(self, brief=PROP_BRIEF):
        self.p.write("assets/models/x.brief.md", brief)
        self.p.write("assets/models/build_x.py", PROP_SCRIPT)
        self.p.write("assets/models/x.pack.json", {"object": {"name": "a wooden barrel", "length_mm": 880,
                                                              "source": "dims:barrel_std", "trust": "high"}})

    def test_brief_missing_an_answer_refuses_gather_naming_it(self):  # fixture: brief_missing
        self.prop(PROP_BRIEF.replace("- ownership: the owner's own", "- ownership: <answer>"))
        code, v, text = self.main("--stage", "gather")
        self.assertEqual(code, 1)
        self.assertEqual(v["status"], "fail")
        self.assertIn("stage gather refused", v["summary"])
        self.assertIn("stage 0 brief is not done: unanswered: ownership", v["summary"])
        self.assertIn("REFUSED", text)
        # ... and with the answer written, gather opens
        self.prop()
        code, v, _ = self.main("--stage", "gather")
        self.assertEqual(code, 0, v["summary"])
        self.assertIn("stage gather open", v["summary"])

    def test_no_parts_plan_holds_even_a_prop_at_the_brief(self):
        self.prop(PROP_BRIEF.split("- parts plan:")[0] + "- draft: assets/models/x_draft.gen.json\n")
        st = self.p.stages()
        self.assertIn("no parts plan", st["brief"]["missing"])
        code, v, _ = self.main("--stage", "shape")
        self.assertEqual(code, 1)
        self.assertIn("no parts plan", v["summary"])

    def test_dossier_unapproved_refuses_shape(self):  # fixture: dossier_unapproved
        from unittest import mock  # noqa: PLC0415

        self.prop(PROP_BRIEF.replace("a wooden barrel", "a Example 45 lantern"))
        self.p.write("assets/models/x.pack.json", {"object": {"name": "Example 45 lantern", "length_mm": 300,
                                                              "source": "dims:lantern", "trust": "high"}})
        ds = {"slug": "example_45_lantern", "score": 84.0, "bar": 80.0, "approved": False, "stale": False,
              "open": [], "problems": [], "missing": []}
        with mock.patch.object(PL, "dossier_summary", return_value=ds):
            code, v, _ = self.main("--stage", "shape")
        self.assertEqual(code, 1)
        self.assertIn("stage 1 gather is not done: the owner has not approved the dossier", v["summary"])
        # (a PROP of a real named object needs it too: the 'a red fire hydrant' kind does not — it is generic)
        with mock.patch.object(PL, "dossier_summary", return_value=None):
            g = self.p.stages()["gather"]
        self.assertTrue(any(m.startswith("no dossier for 'Example 45 lantern'") for m in g["missing"]), g["missing"])

    def test_a_generic_prop_needs_no_dossier_but_a_sourced_size(self):
        from unittest import mock  # noqa: PLC0415

        self.prop()
        with mock.patch.object(PL, "dossier_summary", return_value=None):
            g = self.p.stages()["gather"]
        self.assertFalse(any(m.startswith("no dossier") for m in g["missing"]), g["missing"])
        self.p.write("assets/models/x.pack.json", {"object": {"name": "a wooden barrel"}})
        with mock.patch.object(PL, "dossier_summary", return_value=None):
            g = self.p.stages()["gather"]
        self.assertIn("no sourced size (a dims:<id> cited, a size or the real length in the pack)", g["missing"])

    def test_trace_unlooked_refuses_shape_until_looked_and_again_when_retraced(self):  # fixture: trace_unlooked
        from unittest import mock  # noqa: PLC0415

        self.prop()
        self.p.trace("x_photo_side")
        with mock.patch.object(PL, "dossier_summary", return_value=None):
            code, v, text = self.main("--stage", "shape")
            self.assertEqual(code, 1)
            self.assertIn("1 trace(s) never looked at: x_photo_side", v["summary"])
            self.assertIn("build/renders/x_photo_side_trace.png", text)
            self.p.looked("x_photo_side")
            self.p.study(1)
            self.assertEqual(self.p.stages()["gather"]["status"], PL.DONE, self.p.stages()["gather"]["missing"])
            self.p.trace("x_photo_side", source="refs/x_side_v2.png")  # (traced again: the look is stale)
            self.assertIn("1 trace(s) never looked at: x_photo_side", self.p.stages()["gather"]["missing"])

    def test_route_graveyarded_refuses_unless_the_owner_is_quoted(self):  # fixture: route_graveyarded
        hero = BRIEF + ("\n- parts plan:\n  1. Frame | code: extruded from the side outline | the side trace | "
                        "polymer\n")
        self.p.write("assets/models/x.brief.md", hero)
        self.p.write("assets/models/build_x.py", SCRIPT)
        b = self.p.stages()["brief"]
        self.assertTrue(any(m.startswith("graveyarded route — Frame: G1") for m in b["missing"]), b["missing"])
        code, v, _ = self.main("--stage", "gather")
        self.assertEqual(code, 1)
        self.assertIn("graveyarded route", v["summary"])
        # the method that fixed it clears it ...
        self.p.write("assets/models/x.brief.md", hero.replace("extruded from the side outline",
                                                              "extruded from the side outline + sections"))
        self.assertFalse(any("graveyard" in m for m in self.p.stages()["brief"]["missing"]))
        # ... and so do the owner's own words on the line (kept beside it)
        self.p.write("assets/models/x.brief.md", hero.replace("| polymer", '| polymer | owner: "try the extrude"'))
        b = self.p.stages()["brief"]
        self.assertFalse(any("graveyard" in m for m in b["missing"]), b["missing"])
        self.assertTrue(any("the owner allowed it" in x for x in b["found"]), b["found"])

    def test_budget_exceeded_stops_everything_but_the_look(self):  # fixture: budget_exceeded
        self.prop()
        self.p.write("assets/models/x.clock.json", {"started": time.time() - 11 * 60, "attempt": 1, "extensions": []})
        code, v, text = self.main()
        self.assertEqual(code, 0)
        self.assertIn("STOP — BUDGET: 11", v["summary"])
        self.assertIn("of 10 min (prop)", v["summary"])
        self.assertIn("show the owner", text)
        code, v, _ = self.main("--stage", "shape")
        self.assertEqual(code, 1)
        self.assertIn("BUDGET", v["locked"])
        # only the owner's words extend it
        code, v, _ = self.main("--extend", "5")
        self.assertEqual(code, 2)
        code, v, _ = self.main("--extend", "5", "keep going on the hoops")
        self.assertNotIn("STOP", v["summary"])
        clock = json.load(open(os.path.join(self.p.root, "assets", "models", "x.clock.json")))
        self.assertEqual(clock["extensions"][0]["words"], "keep going on the hoops")

    def test_the_budget_follows_the_briefs_tier(self):
        self.prop(PROP_BRIEF.replace("- quality: prop", "- quality: complex (a lantern that opens)"))
        self.p.write("assets/models/x.clock.json", {"started": time.time() - 11 * 60})
        code, v, _ = self.main()
        self.assertNotIn("STOP", v["summary"])
        self.assertEqual(v["clock"]["budget_min"], 30)
        self.assertEqual(v["clock"]["tier"], "complex")

    def test_the_clock_starts_when_the_brief_is_done_and_each_stage_shows_at_most_five_commands(self):
        self.p.write("assets/models/x.brief.md", BRIEF)   # (a hero brief with no parts plan: not done)
        self.p.write("assets/models/build_x.py", SCRIPT)
        clock = os.path.join(self.p.root, "assets", "models", "x.clock.json")
        code, v, text = self.main()
        self.assertFalse(os.path.isfile(clock))          # (the owner's answering time is not the build's)
        self.assertIn("clock not started", text)
        self.assertIsNone(v["clock"])
        self.assertTrue(all(len(st["commands"]) <= PL.MAX_COMMANDS for st in v["stages"]))
        self.assertIn("LOCKED", text)
        self.prop()
        code, v, text = self.main()
        self.assertTrue(os.path.isfile(clock))
        self.assertIn("clock 0", text)

    def test_over_budget_the_look_stays_open(self):
        self.prop()
        self.p.write("assets/models/x.clock.json", {"started": time.time() - 11 * 60})
        code, v, text = self.main("--stage", "look")
        self.assertEqual(code, 0, v["summary"])
        self.assertIn("stage look open", v["summary"])
        self.assertIn("show the owner", " ".join(v["commands"]))

    def test_extend_refuses_non_finite_or_huge_minutes(self):
        self.prop()
        self.p.write("assets/models/x.clock.json", {"started": time.time() - 11 * 60})
        for bad in ("nan", "inf", "-5", "0", "1000"):
            code, v, _ = self.main("--extend", bad, "go on")
            self.assertEqual(code, 2, bad)
        # (and a NaN written by hand never switches the budget off)
        self.p.write("assets/models/x.clock.json", {"started": time.time() - 11 * 60,
                                                    "extensions": [{"minutes": "nan", "words": "x"}]})
        code, v, _ = self.main()
        self.assertIn("STOP", v["summary"])

    def test_the_owners_words_come_only_right_after_the_minutes(self):
        self.prop()
        self.p.write("assets/models/x.clock.json", {"started": time.time() - 11 * 60})
        code, v, _ = self.main("--extend", "5", "--as", "opus@cc")
        self.assertEqual(code, 2)                        # (another flag's value is never the owner's words)
        code, v, _ = self.main("--extend", "5", "the hoops need it", "--as", "opus@cc")
        self.assertEqual(code, 0)
        clock = json.load(open(os.path.join(self.p.root, "assets", "models", "x.clock.json")))
        self.assertEqual(clock["extensions"][-1]["words"], "the hoops need it")

    def test_the_graveyard_reads_the_briefs_tier_and_only_the_parts_name(self):
        hero = BRIEF + ("\n- parts plan:\n  1. Frame | code: extruded from the side outline | the side trace | "
                        "polymer\n  2. Stock | generated | small checkered panel photo | wood\n")
        self.p.write("assets/models/x.brief.md", hero)
        self.p.write("assets/models/build_x.py", SCRIPT.replace(', quality="hero"', ""))  # (the script says nothing)
        missing = self.p.stages()["brief"]["missing"]
        self.assertTrue(any(m.startswith("graveyarded route — Frame: G1") for m in missing), missing)
        self.assertFalse(any("Stock" in m for m in missing), missing)   # ("small" in its data is no 'all')

    def test_a_number_in_a_generic_name_is_no_real_object(self):
        for generic in ("a 55-gallon oil drum", "a 2x4 plank", "a 1950s fridge"):
            self.assertFalse(PL.is_named(generic), generic)
        for real in ("Glock 17 Gen5", "AK-47", "M1911"):
            self.assertTrue(PL.is_named(real), real)

    def test_a_heros_mechanism_waits_for_the_look(self):  # 5.9: exterior first
        stages = [{"key": k, "title": t, "status": PL.DONE, "missing": []} for k, t in PL.STAGES]
        by = {st["key"]: st for st in stages}
        by["mechanism"].update(status=PL.TODO, missing=["the brief names moving parts and the build has no joint"])
        by["look"].update(status=PL.PARTIAL, missing=["no judges' verdict on this build"])
        PL.lock(stages, None, exterior_first=True)
        self.assertNotIn("locked", by["look"])                        # (the look is next ...)
        # (stage 8 since 2026-11-11: the model sheet and the blockout are stages of their own, before the shape)
        self.assertIn("stage 8 look and judge is not done", by["mechanism"]["locked"])  # (... the joints after it)
        self.assertIs(PL.next_stage(stages), by["look"])
        for st in stages:
            st.pop("locked", None)
        PL.lock(stages, None, exterior_first=False)                   # (a prop / complex object: stage order)
        self.assertIs(PL.next_stage(stages), by["mechanism"])

    def test_a_complex_objects_views_must_reach_their_bar(self):  # 5.7
        self.prop(PROP_BRIEF.replace("- quality: prop", "- quality: complex"))
        self.p.write(".verify/asset-geo-x.json", {"steps": [{"result": {
            "status": "pass", "summary": "ok", "design": [],
            "facts": {"stage": {"views": [{"view": "side", "iou": 0.84, "bar": 0.9}]}}}}]})
        sh = self.p.stages()["shape"]
        self.assertIn("views below their bar: side IoU 0.84 < 0.9", sh["missing"])

    def test_g7_refuses_a_public_prop_painted_by_projection_the_regions_route_clears_it(self):
        old = PROP_BRIEF.replace("code: staves, hoops and heads from the measured profile", "generated + projected")
        self.prop(old)
        self.assertTrue(any(m.startswith("graveyarded route — Body: G7") for m in self.p.stages()["brief"]["missing"]))
        regions = PROP_BRIEF.replace("code: staves, hoops and heads from the measured profile", "generated + colour regions (kit finishes)")
        self.prop(regions)   # (the route that replaced it clears G7 ...)
        missing = self.p.stages()["brief"]["missing"]
        self.assertFalse(any("G7" in m for m in missing))
        # ... and is itself graveyarded since 2026-10-17 (batch 3 "ye hhorrible"): G8
        self.assertTrue(any(m.startswith("graveyarded route — Body: G8") for m in missing), missing)
        self.prop()   # (a prop of known shape built per part in code: neither)
        self.assertFalse(any("G7" in m or "G8" in m for m in self.p.stages()["brief"]["missing"]))

    def test_another_assets_traces_are_not_this_ones(self):
        self.prop()
        self.p.write("assets/models/build_x_lib.py", PROP_SCRIPT)
        self.p.trace("x_lib_side")
        self.p.trace("x_photo_side")
        self.assertEqual(PL.asset_traces(PL.facts("x", self.p.root)), ["x_photo_side"])

if __name__ == "__main__":
    unittest.main()
