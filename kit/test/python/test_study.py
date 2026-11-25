"""kit/tools/study.py — the reference study: each gathered reference read, our version decided, the lessons cited.
Run: python kit/test/python/run.py study"""

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
import study as ST  # noqa: E402

BRIEF = """# x — the brief
- what: a pistol (Example 17), a striker-fired handgun
- quality: {tier}
- hero features:
  1. the slide | code | serrations, the port
"""

LESSON = """---
kind: lesson
area: 3d
date: 2026-10-20
stages: [gather]
---

A pistol slide read from the side photo: measure the serration pitch and the slide-to-frame height ratio before the
shape; a striker-fired handgun slide is a long flat-topped box.
"""


def reference(i, src):
    return f"""### Reference {i}
- source: {src}
- silhouette: a long flat-topped slide over a short raked grip, trigger guard squared at the front {i}
- proportions: length 186 mm to height 128 mm (1.45 : 1), the slide 62% of the height, grip angle 108 deg ({i})
- shape language: square slabs with small chamfers, one curve only at the beavertail, parts spaced evenly {i}
- why it looks good: the slide line runs dead straight from muzzle to rear, the grip rakes back at one clean angle, and the guard repeats the slide's squared front so the whole piece reads as one family {i}
- surface: matte black nitride slide, textured polymer grip, wear only on the edges a holster rubs {i}
- weak: the bare grip sides read as a flat plastic block at range {i}
"""


def study_text(refs, lessons="- none: no vault lesson matched this object at all, nothing to apply yet"):
    body = "\n".join(reference(i, s) for i, s in enumerate(refs, 1))
    return f"""# x — reference study

## References

{body}
## Measured

- real length: 186 mm (dims:len1)

## Common ground

- every good one keeps the slide line straight from the muzzle to the rear
- the grip rakes back between 105 and 110 degrees from the bore line

## Our version

- keep: the straight slide line, the raked grip and the squared trigger guard from the common ground
- change: a stepped slide top with a raised rib, and grip panels cut as three overlapping plates so it is our own design
- signature: a single brass inlay line running the full length of the slide
- proportions: 190 mm long, 1.4 : 1 length to height, slide 60% of the height

## Lessons applied

{lessons}
"""


class Project:
    def __init__(self, tier="prop"):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for d in ("assets/models", "refs"):
            os.makedirs(os.path.join(self.root, d), exist_ok=True)
        self.write("assets/models/x.brief.md", BRIEF.format(tier=tier))
        self.write("assets/models/build_x.py", "import rbx\na = rbx.Asset('x')\na.build()\n")

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text if isinstance(text, str) else json.dumps(text))
        return path

    def check(self):
        return ST.check("x", self.root)

    def close(self):
        self.tmp.cleanup()


class TestStudy(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.addCleanup(self.p.close)
        self.p.write("refs/a.png", "png")
        self.p.write("refs/b.png", "png")
        self.p.write("refs/c.png", "png")

    def test_no_study_is_a_problem_with_the_command_to_start_one(self):
        probs, _ = self.p.check()
        self.assertTrue(probs[0].startswith("no reference study"), probs)
        self.assertIn("kit study x --new", probs[0])

    def test_a_full_study_passes(self):
        self.p.write("assets/models/x.study.md", study_text(["refs/a.png"]))
        probs, facts = self.p.check()
        self.assertEqual(probs, [])
        self.assertEqual(facts["refs"], 1)

    def test_the_template_hint_is_not_an_answer(self):
        text, _q, _f = ST.scaffold("x", self.p.root)
        self.p.write("assets/models/x.study.md", text)
        probs, _ = self.p.check()
        self.assertTrue(any("'silhouette' is missing or too thin" in p for p in probs), probs)
        self.assertTrue(any("our version: 'change'" in p for p in probs), probs)

    def test_thin_answers_missing_numbers_and_copies_fail(self):
        text = study_text(["refs/a.png", "refs/b.png"])
        text = text.replace("- weak: the bare grip sides read as a flat plastic block at range 1", "- weak: bad")
        text = text.replace("- proportions: length 186 mm to height 128 mm (1.45 : 1), the slide 62% of the height, "
                            "grip angle 108 deg (2)", "- proportions: long and fairly tall, slim overall shape")
        # (reference 2's surface copied word for word from reference 1)
        text = text.replace("wear only on the edges a holster rubs 2", "wear only on the edges a holster rubs 1")
        self.p.write("assets/models/x.study.md", text)
        probs, _ = self.p.check()
        self.assertTrue(any("reference 1: 'weak' is missing or too thin" in p for p in probs), probs)
        self.assertTrue(any("reference 2: 'proportions' needs measured numbers" in p for p in probs), probs)
        self.assertTrue(any("reference 2: 'surface' repeats another reference's answer" in p for p in probs), probs)

    def test_a_source_that_does_not_exist_fails(self):
        self.p.write("assets/models/x.study.md", study_text(["refs/missing.png"]))
        probs, _ = self.p.check()
        self.assertTrue(any("refs/missing.png does not exist" in p for p in probs), probs)

    def test_the_tier_sets_how_many_references(self):
        self.p.write("assets/models/x.brief.md", BRIEF.format(tier="hero"))
        self.p.write("assets/models/x.study.md", study_text(["refs/a.png", "refs/b.png"]))
        probs, _ = self.p.check()
        self.assertTrue(any("2 reference(s) studied, a hero needs 3" in p for p in probs), probs)
        self.p.write("assets/models/x.study.md", study_text(["refs/a.png", "refs/b.png", "refs/c.png"]))
        self.assertEqual(self.p.check()[0], [])

    def test_matching_lessons_must_be_cited_by_their_vault_id(self):
        rel = "3d/lessons/2026-10-20-a-pistol-slide-read-from-the-side.md"
        self.p.write(f"kit/knowledge/vault/{rel}", LESSON)
        lid = ST.lesson_id(rel)
        self.assertRegex(lid, r"^L-3d-[0-9a-f]{6}$")
        _q, found, _g, _gr = ST.matches("x", self.p.root)
        self.assertEqual([d["id"] for _s, d in found], [lid])
        # the scaffold lists it for the session to read
        self.assertIn(lid, ST.scaffold("x", self.p.root)[0])
        # "none" is no longer enough once a lesson matches: each match is answered
        self.p.write("assets/models/x.study.md", study_text(["refs/a.png"]))
        probs, _ = self.p.check()
        self.assertTrue(any(p.startswith(f"lessons applied: 1 matched lesson(s) not answered ({lid})") for p in probs),
                        probs)
        # skipped with a reason is an answer (read, judged not to apply) - but not a citation
        self.p.write("assets/models/x.study.md",
                     study_text(["refs/a.png"], f"- skip {lid}: a revolver: no slide at all, the cylinder and frame carry the whole shape"))
        probs, facts = self.p.check()
        self.assertEqual(probs, [])
        self.assertEqual(facts["lessons"], [])
        self.p.write("assets/models/x.study.md", study_text(["refs/a.png"], f"- skip {lid}: no"))
        self.assertTrue(any(f"skip {lid} needs why" in p for p in self.p.check()[0]))
        # a made-up id fails; the real id with how it is applied passes
        self.p.write("assets/models/x.study.md", study_text(["refs/a.png"], "- L-3d-000000: we measure the slide"))
        self.assertTrue(any("L-3d-000000 is no live 3D lesson" in p for p in self.p.check()[0]))
        self.p.write("assets/models/x.study.md",
                     study_text(["refs/a.png"], f"- {lid}: the slide-to-frame height ratio is read off reference 1"))
        probs, facts = self.p.check()
        self.assertEqual(probs, [])
        self.assertEqual(facts["lessons"], [lid])

    def test_a_study_owes_what_it_was_shown_and_lessons_written_after_it(self):
        # (the owner, 2026-11-10: an older lesson that only moved up the ranking is not owed; a newer one is)
        old_rel = "3d/lessons/2026-10-20-a-pistol-slide-read-from-the-side.md"
        new_rel = "3d/lessons/2026-11-09-a-pistol-slide-serration-pitch-from-the-photo.md"
        self.p.write(f"kit/knowledge/vault/{old_rel}", LESSON)
        self.p.write(f"kit/knowledge/vault/{new_rel}", LESSON.replace("2026-10-20", "2026-11-09"))
        old, new = ST.lesson_id(old_rel), ST.lesson_id(new_rel)
        none = study_text(["refs/a.png"])
        self.p.write("assets/models/x.study.md", none)
        # nothing on record of what it was shown, nor when (no served row, no git): every top match is owed, as before
        probs, _ = self.p.check()
        self.assertTrue(any("2 matched lesson(s) not answered" in p for p in probs), probs)
        # kit study --new served it nothing on 2026-11-01: only the lesson written after that is owed
        self.p.write("board/citations.json", [{"kind": "asset", "name": "x", "dept": "3d", "lessons": [],
                                               "served": True, "date": "2026-11-01", "at": 1}])
        probs, _ = self.p.check()
        self.assertTrue(any(p.startswith(f"lessons applied: 1 matched lesson(s) not answered ({new})") for p in probs),
                        probs)
        self.p.write("assets/models/x.study.md",
                     study_text(["refs/a.png"], f"- {new}: the serration pitch is measured off reference 1's photo"))
        self.assertEqual(self.p.check()[0], [])
        # what it WAS shown stays owed, whatever its date
        self.p.write("board/citations.json", [{"kind": "asset", "name": "x", "dept": "3d", "lessons": [old],
                                               "served": True, "date": "2026-11-01", "at": 1}])
        probs, _ = self.p.check()
        self.assertTrue(any(f"not answered ({old})" in p for p in probs), probs)

    def test_a_game_asset_reads_the_kit_homes_vault(self):
        # a game's asset (--root games/<Name>): its folder has no vault, the project above it does (the Sample Game
        # studies matched no lesson because the vault was looked for inside the game folder)
        rel = "3d/lessons/2026-10-20-a-pistol-slide-read-from-the-side.md"
        self.p.write(f"kit/knowledge/vault/{rel}", LESSON)
        game = os.path.join(self.p.root, "games", "G")
        for name in ("x.brief.md", "build_x.py"):
            with open(os.path.join(self.p.root, "assets", "models", name), encoding="utf-8") as fh:
                text = fh.read()
            os.makedirs(os.path.join(game, "assets", "models"), exist_ok=True)
            with open(os.path.join(game, "assets", "models", name), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
        _q, found, _g, _gr = ST.matches("x", game)
        self.assertEqual([d["id"] for _s, d in found], [ST.lesson_id(rel)])

    def test_a_retired_lesson_is_never_retrieved(self):
        rel = "3d/lessons/2026-10-20-a-pistol-slide-read-from-the-side.md"
        self.p.write(f"kit/knowledge/vault/{rel}", LESSON.replace("stages: [gather]", "stages: [gather]\nsuperseded_by: x"))
        self.assertEqual(ST.matches("x", self.p.root)[1], [])

    def test_a_kit_make_prop_needs_no_study(self):
        self.p.write("assets/models/x.brief.md", "<!-- written by kit make from the owner's request -->\n" +
                     BRIEF.format(tier="prop"))
        self.assertIsNone(ST.gate("x", self.p.root))


class TestPlanGather(unittest.TestCase):
    """kit plan's gather stage holds the shape back until the study passes (unless the asset predates the lock)"""

    def setUp(self):
        self.p = Project()
        self.addCleanup(self.p.close)

    def gate(self):
        return PL.study_gate(PL.facts("x", self.p.root))

    def test_a_new_asset_needs_its_study(self):
        probs, _ = self.gate()
        self.assertTrue(probs[0].startswith("no reference study"))
        gather = {st["key"]: st for st in PL.assess(PL.facts("x", self.p.root))}["gather"]
        self.assertTrue(any(m.startswith("reference study: no reference study") for m in gather["missing"]),
                        gather["missing"])
        self.assertTrue(any("kit study x --new" in c for c in gather["commands"]), gather["commands"])

    def test_grandfathered_or_waived_assets_need_none(self):
        self.p.write("board/locks.json", {"grandfathered": {"3d-study": ["assets/models/build_x.py"]}})
        self.assertIsNone(self.gate())
        self.p.write("board/locks.json", {"grandfathered": {"3d-study": []},
                                          "waivers": {"3d": {"x": {"by": "owner", "words": "skip it",
                                                                   "steps": ["study"]}}}})
        self.assertIsNone(self.gate())
        # (a model's own "waiver" counts for nothing)
        self.p.write("board/locks.json", {"grandfathered": {"3d-study": []},
                                          "waivers": {"3d": {"x": {"by": "claude", "words": "skip it"}}}})
        self.assertIsNotNone(self.gate())


# a game-version lesson learned on another object: it shares none of the pistol's words, only the route's
GAME_LESSON = """---
kind: lesson
area: 3d
date: 2026-11-10
stages: [surface]
---

A game version that baked a cupboard's rounds into the low's normal map stair-stepped them at a low texel density:
keep the rounds the owner looks at as geometry on the low, bake only what is finer than a texel or two.
"""
CAD = "import rbx\na = rbx.Asset('x'{opts})\na.cad('body', {{}}, 'steel'{part})\na.build()\n"
TEMPLATE = '''"""build_x.py - made from kit/templates/asset.py

    a = rbx.Asset("x", size=...) -> Asset(size=..., low=True) for a game version; a.cad(...), a.mesh(...), a.tube(...)
"""
import rbx
# a = rbx.Asset("x", low=True)   (an old line, commented out)
a = rbx.Asset("x"{opts})
a.cad("body", {{"code": "r = cq.Workplane().box(1, 2, 3)"}}, "steel")
a.build()
'''
GAME_REL = "3d/lessons/2026-11-10-a-game-version-that-baked-a-cupboard-s-rounds.md"


class TestRoute(unittest.TestCase):
    """the owner, 2026-11-10: a lesson answered for one route is not answered for the next - the car rim's round 5
    learned that baked bevel normals made the sawtooth and its study cited it, yet its S1 game version baked every
    fillet and the sawtooth came back. A changed route owes every matched lesson again before kit asset builds."""

    def setUp(self):
        self.p = Project()
        self.addCleanup(self.p.close)
        self.p.write("refs/a.png", "png")
        self.pistol = "3d/lessons/2026-10-20-a-pistol-slide-read-from-the-side.md"
        self.p.write(f"kit/knowledge/vault/{self.pistol}", LESSON)
        self.p.write(f"kit/knowledge/vault/{GAME_REL}", GAME_LESSON)
        self.old, self.new = ST.lesson_id(self.pistol), ST.lesson_id(GAME_REL)

    def script(self, opts="", part=""):
        self.p.write("assets/models/build_x.py", CAD.format(opts=opts, part=part))

    def test_the_route_is_the_geometry_or_maps_switches_in_the_code(self):
        self.assertEqual(ST.route_of(CAD.format(opts="", part="")), ())
        self.assertEqual(ST.route_of(CAD.format(opts=", low=True", part="")), ("low",))
        self.assertEqual(ST.route_of(CAD.format(opts=", low=9000", part="")), ("low",))
        self.assertEqual(ST.route_of(CAD.format(opts=", low=None", part="")), ())
        self.assertEqual(ST.route_of(CAD.format(opts=", low=True", part=", low=False")), ("high-only parts", "low"))
        self.assertEqual(ST.route_of(CAD.format(opts=", low=True", part=", low={'round': 0}")), ("baked rounds", "low"))
        self.assertEqual(ST.route_of(CAD.format(opts=", edge_radius=0.0", part="")), ("no bevel",))
        # (a low=False on a part means nothing without the game version; a new part family is no route change)
        self.assertEqual(ST.route_of(CAD.format(opts="", part=", low=False")), ())
        self.assertEqual(ST.route_of(CAD.format(opts="", part="") + "a.pillow('cushion', [], 'cloth')\n"), ())

    def test_a_docstring_or_a_comment_is_never_the_route(self):
        # (the template's docstring shows Asset(... low=True) and a.cad / a.mesh / a.tube: it once hid the real call)
        self.assertEqual(ST.route_of(TEMPLATE.format(opts="")), ())
        self.assertEqual(ST.route_of(TEMPLATE.format(opts=", low=True, edge_radius=0")), ("low", "no bevel"))

    def test_a_wrapper_is_read_through_to_the_script_it_runs(self):
        wrapper = ("import os, runpy\nos.environ['X'] = 'broken'\nrunpy.run_path(os.path.join(os.path.dirname("
                   "os.path.abspath(__file__)), 'build_x_base.py'), run_name='__main__')\n")
        seen = []

        def follow(name):
            seen.append(name)
            return CAD.format(opts=", low=True", part="")

        self.assertEqual(ST.route_of(wrapper, follow=follow), ("low",))
        self.assertEqual(seen, ["build_x_base.py"])
        self.assertEqual(ST.route_of(wrapper), ())

    def test_the_routes_words_bring_its_lessons(self):
        self.script()
        self.assertNotIn(self.new, [d["id"] for _s, d in ST.matches("x", self.p.root)[1]])
        self.script(opts=", low=True")
        self.assertIn(self.new, [d["id"] for _s, d in ST.matches("x", self.p.root)[1]])

    def test_a_changed_route_asks_every_lesson_again_at_the_build_never_in_verify(self):
        self.script()
        answer = "the slide serrations are measured off reference 1's photo before the shape"
        self.p.write("assets/models/x.study.md",
                     study_text(["refs/a.png"], f"<!-- ROUTE: none -->\n- {self.old}: {answer}"))
        self.assertEqual(self.p.check()[0], [])
        self.assertIsNone(ST.route_gate("x", self.p.root))
        # the game version is turned on: the BUILD is refused; kit verify's check still reads the route answered for
        self.script(opts=", low=True")
        self.assertEqual(ST.route_gate("x", self.p.root), ((), ("low",)))
        self.assertEqual(self.p.check()[0], [])
        text, was, now, found = ST.reroute("x", self.p.root, today="2026-11-10")
        self.assertEqual((was, now), ((), ("low",)))
        self.assertIn(self.new, [d["id"] for _s, d in found])
        self.p.write("assets/models/x.study.md", text)
        self.assertIn("## Earlier answers (route: none, before 2026-11-10)", text)
        self.assertIn("<!-- ROUTE: low -->", text)
        self.assertIsNone(ST.route_gate("x", self.p.root))  # (its mark is the route now)
        probs, _ = self.p.check()
        self.assertTrue(any("matched lesson(s) not answered" in p and self.new in p and self.old in p for p in probs),
                        probs)
        # the old answer copied word for word does not count; one for the new route does
        fresh = text.replace(f"- {self.old}: <answer>", f"- {self.old}: {answer}", 1)
        fresh = fresh.replace(f"- {self.new}: <answer>", f"- {self.new}: the slide's rounds stay geometry on the low, "
                                                       "only the serrations' fine edges are baked", 1)
        self.p.write("assets/models/x.study.md", fresh)
        probs, _ = self.p.check()
        self.assertTrue(any(f"{self.old} repeats its answer for the earlier route" in p for p in probs), probs)
        self.p.write("assets/models/x.study.md", fresh.replace(
            f"- {self.old}: {answer}", f"- {self.old}: the low keeps the serration pitch measured off reference 1", 1))
        self.assertEqual(self.p.check()[0], [])

    def test_an_unstamped_study_takes_its_route_at_the_first_build(self):
        # (no git here: nothing to say what route it was written for - it is stamped with the one it builds on)
        self.script(opts=", low=True")
        self.p.write("assets/models/x.study.md", study_text(["refs/a.png"]))
        self.assertIsNone(ST.route_gate("x", self.p.root))
        self.assertTrue(ST.stamp_route("x", self.p.root))
        with open(ST.study_path("x", self.p.root), encoding="utf-8") as fh:
            self.assertEqual(ST.route_stamp(fh.read()), ("low",))
        self.assertFalse(ST.stamp_route("x", self.p.root))  # (once)
        self.script()
        self.assertEqual(ST.route_gate("x", self.p.root), (("low",), ()))


class TestPrebuild(unittest.TestCase):
    """kit asset / kit optimize ask before every build: no build past the piece's budget, none on a changed route"""

    def setUp(self):
        self.p = Project()
        self.addCleanup(self.p.close)
        self.p.write("refs/a.png", "png")
        self.p.write("assets/models/build_x.py", CAD.format(opts="", part=""))
        self.now = PL.BUILD_CLOCK_FROM + 86400.0  # (a day after the budget reached the build)

    def prebuild(self, now=None):
        return PL.prebuild(PL.facts("x", self.p.root), now or self.now)

    def clock(self):
        with open(os.path.join(self.p.root, "assets", "models", "x.clock.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_past_the_budget_nothing_builds_and_the_owner_is_shown_what_there_is(self):
        self.p.write("assets/models/x.clock.json", {"started": self.now - 25 * 60, "attempt": 6, "extensions": []})
        self.p.write("build/models/x.blend", "blend")
        self.p.write("board/tasks/ab12-fix-the-x-first.md", '---\nid: ab12\ntitle: "Yes, fix the x first"\n'
                     "status: doing\n---\n\n## Goal\nShould be reworked: the x\n")
        self.p.write("board/tasks/cd34-an-old-x-card.md", '---\nid: cd34\ntitle: "an old x card"\nstatus: done\n---\n')
        stop, summary, action, lines = self.prebuild()
        self.assertTrue(stop)
        self.assertIn("STOP — BUDGET: 25 of 10 min (prop, attempt 6)", summary)
        text = "\n".join(lines)
        self.assertIn("build/models/x.blend", text)
        self.assertIn("ab12 (doing): Yes, fix the x first", text)
        self.assertNotIn("cd34", text)
        self.assertIn('lune run kit plan x --extend <minutes> "<his words>"', text)
        self.assertIn('--restart "<his words>"', action)
        # the owner's minutes reopen it
        self.p.write("assets/models/x.clock.json", {"started": self.now - 25 * 60, "attempt": 6, "extensions": [
            {"minutes": 20, "words": "go on with the threads", "at": self.now}]})
        self.assertFalse(self.prebuild()[0])

    def test_a_piece_with_no_clock_starts_one_at_its_first_build(self):
        stop, _s, _a, lines = self.prebuild()
        self.assertFalse(stop)
        self.assertEqual((self.clock()["started"], self.clock()["attempt"]), (self.now, 1))
        self.assertTrue(any("clock started: 10 min (prop)" in ln for ln in lines), lines)
        self.assertTrue(self.prebuild(self.now + 11 * 60)[0])  # (and it stops 10 minutes later)

    def test_an_attempt_that_ran_out_before_the_rule_gets_one_fresh_attempt_then_the_budget(self):
        self.p.write("assets/models/x.clock.json", {"started": PL.BUILD_CLOCK_FROM - 86400, "attempt": 6,
                                                    "extensions": []})
        stop, _s, _a, lines = self.prebuild()
        self.assertFalse(stop)
        c = self.clock()
        self.assertEqual((c["attempt"], c["started"]), (7, self.now))
        self.assertIn("fresh", c)
        self.assertEqual(c["previous"]["attempt"], 6)  # (the old clock kept: the owner's minutes and words with it)
        self.assertTrue(self.prebuild(self.now + 11 * 60)[0])  # (one: ten minutes on, it stops like any other)

    def test_an_attempt_still_running_at_the_rule_gets_no_fresh_one(self):
        # (started before the rule but the owner's 60 minutes ran on past it: when they run out, it stops)
        self.p.write("assets/models/x.clock.json", {"started": PL.BUILD_CLOCK_FROM - 5 * 60, "attempt": 3,
                                                    "extensions": [{"minutes": 60, "words": "finish the lip",
                                                                    "at": PL.BUILD_CLOCK_FROM - 4 * 60}]})
        stop, summary, _a, _l = self.prebuild(PL.BUILD_CLOCK_FROM + 2 * 3600)
        self.assertTrue(stop)
        self.assertIn("STOP — BUDGET", summary)
        self.assertEqual(self.clock()["extensions"][0]["words"], "finish the lip")

    def test_a_changed_route_stops_the_build_until_its_lessons_are_answered_again(self):
        self.p.write(f"kit/knowledge/vault/{GAME_REL}", GAME_LESSON)
        self.p.write("assets/models/x.study.md", study_text(["refs/a.png"], "<!-- ROUTE: none -->\n- none: no vault "
                                                            "lesson matched this object at all, nothing to apply yet"))
        self.assertFalse(self.prebuild()[0])
        self.p.write("assets/models/build_x.py", CAD.format(opts=", low=True", part=""))
        stop, summary, action, lines = self.prebuild()
        self.assertTrue(stop)
        self.assertIn("STOP — ROUTE changed (none -> low)", summary)
        self.assertIn("lune run kit study x --reroute", action)
        # rerouted with nothing answered yet: still no build (kit optimize has no quality lock to ask it)
        text = ST.reroute("x", self.p.root)[0]
        self.p.write("assets/models/x.study.md", text)
        stop, summary, _a, _l = self.prebuild()
        self.assertTrue(stop)
        self.assertIn("its new route's lessons are not answered yet", summary)
        lid = ST.lesson_id(GAME_REL)
        self.p.write("assets/models/x.study.md", text.replace(
            f"- {lid}: <answer>", f"- {lid}: the slide's rounds stay geometry on the low, only fine edges baked", 1))
        self.assertFalse(self.prebuild()[0])

    def test_the_tier_is_the_one_the_attempt_started_on(self):
        # (a brief edited mid-attempt - prop to aaa - never turns 10 minutes into 60 and lifts the STOP)
        self.p.write("assets/models/x.clock.json", {"started": self.now - 25 * 60, "attempt": 1, "extensions": [],
                                                    "tier": "prop"})
        self.p.write("assets/models/x.brief.md", BRIEF.format(tier="aaa"))
        stop, summary, _a, _l = self.prebuild()
        self.assertTrue(stop)
        self.assertIn("of 10 min (prop", summary)

    def test_a_maintenance_rebuild_reads_no_clock_but_still_the_route(self):
        self.p.write("assets/models/x.clock.json", {"started": self.now - 25 * 60, "attempt": 2, "extensions": []})
        before = self.clock()
        stop, summary, _a, _l = PL.prebuild(PL.facts("x", self.p.root), self.now, use_clock=False)
        self.assertFalse(stop, summary)
        self.assertEqual(self.clock(), before)  # (no clock started, no fresh attempt spent)
        self.p.write(f"kit/knowledge/vault/{GAME_REL}", GAME_LESSON)
        self.p.write("assets/models/x.study.md", study_text(["refs/a.png"], "<!-- ROUTE: none -->\n- none: no vault "
                                                            "lesson matched this object at all, nothing to apply yet"))
        self.p.write("assets/models/build_x.py", CAD.format(opts=", low=True", part=""))
        self.assertTrue(PL.prebuild(PL.facts("x", self.p.root), self.now, use_clock=False)[0])

    def test_a_route_git_could_not_tell_is_never_stamped_nor_refused(self):
        self.p.write("assets/models/build_x.py", CAD.format(opts=", low=True", part=""))
        self.p.write("assets/models/x.study.md", study_text(["refs/a.png"]))
        keep = ST._route_at_birth
        ST._route_at_birth = lambda asset, root: ST.UNKNOWN_ROUTE  # (git timed out / is missing)
        self.addCleanup(setattr, ST, "_route_at_birth", keep)
        self.assertIsNone(ST.route_gate("x", self.p.root))
        self.assertFalse(ST.stamp_route("x", self.p.root))
        self.assertFalse(self.prebuild()[0])
        with open(ST.study_path("x", self.p.root), encoding="utf-8") as fh:
            self.assertIsNone(ST.route_stamp(fh.read()))

    def test_a_reroute_of_a_study_with_no_lessons_section_still_owes_its_answers(self):
        self.p.write(f"kit/knowledge/vault/{GAME_REL}", GAME_LESSON)
        bare = study_text(["refs/a.png"]).split("## Lessons applied")[0]
        self.p.write("assets/models/x.study.md", bare)
        self.p.write("assets/models/build_x.py", CAD.format(opts=", low=True", part=""))
        self.p.write("assets/models/x.study.md", ST.reroute("x", self.p.root)[0])
        stop, summary, _a, _l = self.prebuild()
        self.assertTrue(stop)
        self.assertIn("its new route's lessons are not answered yet", summary)

    def methods_locked_project(self):
        self.p.write("board/locks.json", {"grandfathered": {"3d-methods": []}})   # (x is a NEW piece: on no list)

    def test_a_new_piece_with_no_brief_does_not_build_and_starts_no_clock(self):
        # (card 988z: the methods lock holds a build to its parts plan - with no brief nothing held it)
        self.methods_locked_project()
        os.remove(os.path.join(self.p.root, "assets", "models", "x.brief.md"))
        stop, summary, action, lines = self.prebuild()
        self.assertTrue(stop)
        self.assertIn("STOP — METHODS: a new piece with no brief", summary)
        self.assertIn("assets/models/x.brief.md", action)
        self.assertIn("--waive methods", "\n".join(lines))
        self.assertFalse(os.path.isfile(os.path.join(self.p.root, "assets", "models", "x.clock.json")))

    def test_a_new_piece_whose_brief_has_no_parts_plan_does_not_build(self):
        self.methods_locked_project()
        stop, summary, _a, _l = self.prebuild()
        self.assertTrue(stop)
        self.assertIn("a brief with no parts plan", summary)

    def test_a_new_piece_with_a_parts_plan_is_not_stopped_by_the_methods_lock(self):
        self.methods_locked_project()
        with open(os.path.join(self.p.root, "assets", "models", "x.brief.md"), "a", encoding="utf-8") as fh:
            fh.write("\n- parts plan:\n  1. Body | CAD a.cad | the box | paint\n")
        with open(os.path.join(self.p.root, "assets", "models", "x.brief.md"), encoding="utf-8") as fh:
            self.assertTrue(PL.parts_plan(fh.read()))
        stop, summary, _a, _l = self.prebuild()
        self.assertNotIn("METHODS", summary)

    def test_the_owner_waives_the_methods_stop_for_one_piece(self):
        self.p.write("board/locks.json", {"grandfathered": {"3d-methods": []}, "waivers": {"3d": {"x": {
            "by": "owner", "words": "build it without a plan", "steps": ["methods"]}}}})
        stop, summary, _a, _l = self.prebuild()
        self.assertNotIn("METHODS", summary)

    def test_open_cards_name_the_piece_never_a_lone_common_word(self):
        self.p.write("board/tasks/aa11-the-world-sky.md", '---\nid: aa11\ntitle: "the world sky, darker"\n'
                     "status: todo\n---\n")
        self.p.write("board/tasks/bb22-x.md", '---\nid: bb22\ntitle: "the_world: its fog"\nstatus: todo\n---\n')
        self.p.write("board/tasks/cc33-rim.md", "---\nid: cc33\ntitle: \"Yes, fix it first [the car rim's lip]\"\n"
                     "status: doing\n---\n")
        self.assertEqual([c[0] for c in PL.open_cards("the_world", self.p.root)], ["aa11", "bb22"])
        self.assertEqual([c[0] for c in PL.open_cards("world_map", self.p.root)], [])
        self.assertEqual([c[0] for c in PL.open_cards("car_wheel_rim", self.p.root)], ["cc33"])

    def test_the_command_exits_nonzero_on_a_stop(self):
        import contextlib  # noqa: PLC0415
        import io  # noqa: PLC0415
        keep = PL.BUILD_CLOCK_FROM
        PL.BUILD_CLOCK_FROM = 0  # (this clock is a fresh one, whatever the day)
        self.addCleanup(setattr, PL, "BUILD_CLOCK_FROM", keep)
        self.p.write("assets/models/x.clock.json", {"started": time.time() - 11 * 60, "attempt": 1, "extensions": []})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = PL.main(["x", "--prebuild", "--root", self.p.root])
        self.assertEqual(code, 1, out.getvalue())
        self.assertEqual(json.loads(out.getvalue().strip().splitlines()[-1])["status"], "fail")
        os.remove(os.path.join(self.p.root, "assets", "models", "x.clock.json"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(PL.main(["x", "--prebuild", "--root", self.p.root]), 0)


if __name__ == "__main__":
    unittest.main()
