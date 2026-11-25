"""THE METHODS LOCK (kit/blender/rbx_plan.py method_problems / methods_locked / methods_check; kit/tools/plan.py's
brief stage; rbx.Asset's build check): the owner, 2026-11-13 - "every method i mentioned ... implmented into each
pipeline and enforced in the terms of being used". A new piece's parts plan names the builder call each coded part
is made with; many alike are repeated or scattered, long curved forms swept or bent; the build is held to what the
plan named and types nothing alike one by one; pieces that existed before are exempt."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
sys.path.insert(0, HERE)
import cad_check  # noqa: E402
import plan as PL  # noqa: E402
import rbx_plan as P  # noqa: E402
from test_pipeline_plan import BRIEF, SCRIPT, Project  # noqa: E402

BLENDER = cad_check.blender()

PLAN = """# x
- parts plan:
  1. Body | code: a.box, then a.loop + a.inset for the lid | side picture | paint
  2. Teeth x12 | code: a.box each | top picture | steel
  3. Horn | code: a.box | side | bone
  4. Grip | code | side | rubber
  5. Crest | sculpt + code: a.sculpt | 3/4 | gold
  6. Rivets | code: a.cylinder + relief | top | steel
  7. Chain | code: a.cad link in a.repeat along a path | side | iron
  8. Tusk | code: a.cylinder, a.taper + a.bend | side | ivory
  9. Scales | code: a.box in a.scatter over the body | top | green
"""


class Plan(unittest.TestCase):
    def setUp(self):
        self.plan = P.plan_parts(PLAN)

    def test_the_parts_plan_is_read(self):
        self.assertEqual([p["name"] for p in self.plan],
                         ["Body", "Teeth x12", "Horn", "Grip", "Crest", "Rivets", "Chain", "Tusk", "Scales"])
        self.assertEqual(self.plan[4]["routes"], ["code", "sculpt"])
        self.assertEqual(P.plan_parts("# x\n- what: a thing\n"), [])

    def test_what_a_plan_line_must_say(self):
        bad = dict(P.method_problems(self.plan))
        self.assertEqual(sorted(bad), ["Grip", "Horn", "Teeth x12"])
        self.assertIn("no METHOD", bad["Grip"])                          # code, and not a word of how
        self.assertIn("many alike", bad["Teeth x12"])                    # twelve teeth, a box each
        self.assertIn("a.repeat", bad["Teeth x12"])
        self.assertIn("long and curved", bad["Horn"])                    # a horn from a box
        self.assertIn("a.sweep", bad["Horn"])

    def test_what_passes(self):
        ok = [p for p in self.plan if p["name"] in ("Body", "Crest", "Rivets", "Chain", "Tusk", "Scales")]
        self.assertEqual(P.method_problems(ok), [])
        # (a part on another route than code is not this lock's: its own gates hold it)
        self.assertEqual(P.method_problems(P.plan_parts("# x\n- parts plan:\n  1. Horn | generated: kit gen | a | b\n")),
                         [])

    def test_the_build_is_held_to_what_its_plan_names(self):
        c = P.methods_check(self.plan, {"box modelling", "deform", "scatter", "cad"}, [])
        self.assertFalse(c["ok"])
        self.assertEqual(c["value"], ["Chain: its plan names repeat and the build used none of it"])
        self.assertEqual(c["severity"], "error")
        self.assertTrue(P.methods_check(self.plan, {"box modelling", "deform", "scatter", "repeat", "cad"}, [])["ok"])
        # (the calls a line may name in place of the six are held the same way: a tube that was never made)
        tube = P.plan_parts("# x\n- parts plan:\n  1. Horn | code: a.tube | a | b\n"
                            "  2. Teeth x12 | code: a.box in a.stamp | a | b\n")
        self.assertEqual(P.method_problems(tube), [])
        self.assertEqual(P.methods_check(tube, {}, [])["value"],
                         ["Teeth x12: its plan names stamp and the build used none of it",
                          "Horn: its plan names tube and the build used none of it"])
        self.assertTrue(P.methods_check(tube, {"tube": [1], "stamp": [1]}, [])["ok"])

    def test_one_token_use_does_not_cover_every_part_that_names_the_method(self):
        plan = P.plan_parts("# x\n- parts plan:\n  1. Teeth x12 | code: a.box in a.repeat, a ring | a | b\n"
                            "  2. Fence | code: a.box in a.repeat | a | b\n"
                            "  3. Slats | code: a.box in a.repeat | a | b\n")
        c = P.methods_check(plan, {"repeat": [2]}, [])                   # ONE repeat, of two
        self.assertFalse(c["ok"])
        self.assertIn("3 planned parts name repeat (Teeth x12, Fence, Slats) and the build used it on 1", c["value"])
        self.assertIn("Teeth x12: its plan says x12 by repeat and the build's repeat makes 2", c["value"])
        c = P.methods_check(plan, {"repeat": [4, 12, 6]}, [])            # three, one of them twelve
        self.assertTrue(c["ok"], c["value"])
        self.assertFalse(P.methods_check(plan, {"repeat": [4, 11, 6]}, [])["ok"])   # eleven teeth are not twelve
        # (one a.mirror block serves several parts: only "used at all" is held)
        pair = P.plan_parts("# x\n- parts plan:\n  1. Left ear | code: a.box in a.mirror | a | b\n"
                            "  2. Left eye | code: a.sphere in a.mirror | a | b\n")
        self.assertTrue(P.methods_check(pair, {"mirror": [1]}, [])["ok"])
        self.assertFalse(P.methods_check(pair, {}, [])["ok"])

    def test_a_use_the_build_names_is_held_to_its_own_plan_line(self):
        # (card 988z: by counts the twelve teeth were held against the largest repeat - here the slats' 12)
        plan = P.plan_parts("# x\n- parts plan:\n  1. Teeth x12 | code: a.box in a.repeat | a | b\n"
                            "  2. Slats x6 | code: a.box in a.repeat | a | b\n")
        self.assertTrue(P.methods_check(plan, {"repeat": [6, 12]}, [])["ok"])       # (counts alone: it passed)
        c = P.methods_check(plan, {"repeat": [("Tooth", 6), ("Slat", 12)]}, [])
        self.assertFalse(c["ok"])
        self.assertIn("Teeth x12: its plan says x12 by repeat and the build's repeat on Tooth makes 6", c["value"])
        self.assertTrue(P.methods_check(plan, {"repeat": [("Tooth~1", 12), ("Slat", 6)]}, [])["ok"])

    def test_the_planned_part_a_method_never_made_is_named(self):
        plan = P.plan_parts("# x\n- parts plan:\n  1. Bolts x5 | code: a.cylinder in a.repeat | a | b\n"
                            "  2. Fence | code: a.box in a.repeat | a | b\n")
        c = P.methods_check(plan, {"repeat": [("Bolt", 5)]}, [])
        self.assertFalse(c["ok"])
        self.assertIn("2 planned parts name repeat (Bolts x5, Fence) and the build used it on 1 - not made by it: "
                      "Fence", c["value"])
        c = P.methods_check(plan, {"repeat": [5]}, [])                     # (an unnamed use: no name guessed)
        self.assertNotIn("not made by it", c["value"])

    def test_a_name_that_fits_two_planned_parts_is_left_to_the_counts(self):
        plan = P.plan_parts("# x\n- parts plan:\n  1. Posts x4 | code: a.box in a.repeat | a | b\n"
                            "  2. Post caps x4 | code: a.box in a.repeat | a | b\n")
        self.assertEqual(P._pair_by_name([("Posts x4", 4), ("Post caps x4", 4)], [(("Post",), 4)]), {})
        c = P.methods_check(plan, {"repeat": [("Post", 4)]}, [])
        self.assertFalse(c["ok"])
        self.assertNotIn("not made by it", c["value"])
        self.assertEqual(P.part_key("Teeth x12"), {"tooth"})
        self.assertEqual(P.part_key("FencePost2~3"), {"fence", "post"})

    def test_the_route_word_does_not_decide_it(self):
        dodge = P.plan_parts("# x\n- parts plan:\n  1. Teeth x12 | procedural: a.box each | a | b\n"
                             "  2. Mane | sculpt | a | b\n")
        bad = dict(P.method_problems(dodge))
        self.assertEqual(sorted(bad), ["Teeth x12"])                     # a builder call was named: it is code
        self.assertIn('many alike ("x12")', bad["Teeth x12"])

    def test_a_name_is_read_by_its_own_noun(self):
        fine = ["Hook plate | code: a.box", "Tail light | code: a.box", "Cable port | code: a.cad",
                "Strap loop | code: a.box", "CPU x64 bit label | code: a.box", "Scales pan | code: a.cylinder",
                "Grip (rails cut in) | code: a.box", "Lens x2 | code: a.cylinder",
                "Window bars | code: a.cylinder in a.mirror", "Posts x4 | code: a.box in a.mirror, twice"]
        plan = P.plan_parts("# x\n- parts plan:\n" + "".join(f"  {i}. {x} | a | b\n" for i, x in enumerate(fine, 1)))
        self.assertEqual(len(plan), len(fine))
        self.assertEqual(P.method_problems(plan), [])
        held = ["Lanyard hook | code: a.box", "Window bars | code: a.cylinder", "Teeth x12 | code: a.box in a.mirror",
                "Ring of rivets | code: a.cylinder", "Pegs x3 | code: a.cylinder"]
        plan = P.plan_parts("# x\n- parts plan:\n" + "".join(f"  {i}. {x} | a | b\n" for i, x in enumerate(held, 1)))
        self.assertEqual([n for n, _why in P.method_problems(plan)], [x.split(" | ")[0] for x in held])
        self.assertEqual((P.head_noun("Teeth x12"), P.head_noun("Hook plate"), P.head_noun("Fin (left) x3")),
                         ("teeth", "plate", "fin"))
        self.assertEqual(P.many_of("Teeth x12"), (12, "x12"))
        self.assertEqual(P.many_of("Lens x2"), (2, None))

    def test_alike_parts_typed_one_by_one_are_named(self):
        c = P.methods_check([], set(), [["Bolt1", "Bolt2", "Bolt3", "Bolt4", "Bolt5"]])
        self.assertFalse(c["ok"])
        self.assertIn("5 parts are ONE shape typed 5 times (Bolt1, Bolt2, Bolt3 and 2 more)", c["value"][0])
        self.assertIn("a.repeat", c["fix"])
        self.assertIsNone(P.methods_check([], set(), []))                # nothing to hold it to


class Scope(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "board"))
        os.makedirs(os.path.join(self.root, "assets", "models"))
        os.environ.pop("KIT_METHODS_LOCK", None)

    def tearDown(self):
        os.environ.pop("KIT_METHODS_LOCK", None)
        self.tmp.cleanup()

    def locks(self, data):
        with open(os.path.join(self.root, "board", "locks.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def script(self, rel="assets/models/build_new.py"):
        return os.path.join(self.root, rel)

    def test_off_until_the_project_switched_it_on(self):
        self.assertFalse(P.methods_locked(self.script(), self.root))     # no locks file at all
        self.locks({"grandfathered": {"3d-study": []}})
        self.assertFalse(P.methods_locked(self.script(), self.root))     # locks, but this one never frozen

    def test_a_new_piece_is_held_and_an_old_one_is_not(self):
        self.locks({"grandfathered": {"3d-methods": ["assets/models/build_old.py"]}})
        self.assertTrue(P.methods_locked(self.script(), self.root))
        self.assertFalse(P.methods_locked(self.script("assets/models/build_old.py"), self.root))
        self.assertFalse(P.methods_locked(self.script("ASSETS/models/BUILD_OLD.py"), self.root))
        self.assertTrue(P.methods_locked(self.script("games/SampleDojo/assets/models/build_new.py"), self.root))

    def test_only_a_pieces_own_script_is_in_scope(self):
        self.locks({"grandfathered": {"3d-methods": []}})
        for rel in ("kit/selftest/blender/build_repeat.py", "assets/models/helpers.py", "tools/build_x.py"):
            self.assertFalse(P.methods_locked(self.script(rel), self.root), rel)

    def test_only_the_owner_waives_it(self):
        base = {"grandfathered": {"3d-methods": []}}
        self.locks({**base, "waivers": {"3d": {"new": {"by": "owner", "words": "skip it", "steps": ["methods"]}}}})
        self.assertFalse(P.methods_locked(self.script(), self.root))
        self.locks({**base, "waivers": {"3d": {"new": {"by": "owner", "words": "skip the study", "steps": ["study"]}}}})
        self.assertTrue(P.methods_locked(self.script(), self.root))      # he waived another step
        self.locks({**base, "waivers": {"3d": {"new": {"by": "model", "steps": ["methods"]}}}})
        self.assertTrue(P.methods_locked(self.script(), self.root))      # nobody's waiver but his

    def test_an_empty_list_as_lune_writes_it_is_still_the_lock_switched_on(self):
        self.locks({"grandfathered": {"3d-methods": {}}})                # (Lune's serde: an empty table is {})
        self.assertTrue(P.methods_locked(self.script(), self.root))
        self.locks({"grandfathered": {"3d-methods": {"a": 1}}})          # anything else that is no list: off
        self.assertFalse(P.methods_locked(self.script(), self.root))

    def test_a_games_piece_is_read_from_the_kit_homes_record(self):
        self.locks({"grandfathered": {"3d-methods": ["assets/models/build_new.py",
                                                     "games/Old/assets/models/build_new.py"]}})
        game = os.path.join(self.root, "games", "SampleDojo")
        script = os.path.join(game, "assets", "models", "build_new.py")
        self.assertTrue(P.methods_locked(script, game, self.root))       # (the home's own piece of that name is another)
        self.assertFalse(P.methods_locked(os.path.join(self.root, "games", "Old", "assets", "models", "build_new.py"),
                                          os.path.join(self.root, "games", "Old"), self.root))
        self.assertFalse(P.methods_locked(script, game))                 # no home said, and the game has no record
        os.makedirs(os.path.join(game, "board"))
        with open(os.path.join(game, "board", "locks.json"), "w", encoding="utf-8") as fh:
            json.dump({"grandfathered": {"3d-methods": ["assets/models/build_new.py"]}}, fh)
        self.assertFalse(P.methods_locked(script, game, self.root))      # a project's own record comes first

    def test_a_broken_record_never_crashes_a_build(self):
        for bad in ({"grandfathered": ["x"]}, {"grandfathered": {"3d-methods": []}, "waivers": ["x"]},
                    {"grandfathered": {"3d-methods": []}, "waivers": {"3d": ["x"]}}, ["x"], "x"):
            self.locks(bad)
            P.methods_locked(self.script(), self.root)                   # (whatever it answers, it answers)
        self.locks({"grandfathered": {"3d-methods": []}, "waivers": {"3d": ["x"]}})
        self.assertTrue(P.methods_locked(self.script(), self.root))

    def test_the_owner_is_read_as_the_kit_reads_him(self):
        base = {"grandfathered": {"3d-methods": []}}
        self.locks({**base, "waivers": {"3d": {"new": {"by": "owner", "who": "claude", "steps": ["methods"]}}}})
        self.assertTrue(P.methods_locked(self.script(), self.root))      # `who` says it was not him
        self.locks({**base, "waivers": {"3d": {"new": {"by": " Owner", "steps": ["methods"]}}}})
        self.assertFalse(P.methods_locked(self.script(), self.root))

    def test_the_kits_own_tests_can_force_it(self):
        os.environ["KIT_METHODS_LOCK"] = "1"
        self.assertTrue(P.methods_locked(self.script("anything.py"), self.root))
        os.environ["KIT_METHODS_LOCK"] = "0"
        self.locks({"grandfathered": {"3d-methods": []}})
        self.assertFalse(P.methods_locked(self.script(), self.root))


class BriefStage(unittest.TestCase):
    BAD = ("\n- parts plan:\n  1. Slide | code: a.cad from the side trace | refs | blued steel\n"
           "  2. Serrations x9 | code: a.box each | refs | steel\n  3. Lanyard hook | code | refs | steel\n")
    GOOD = ("\n- parts plan:\n  1. Slide | code: a.cad from the side trace | refs | blued steel\n"
            "  2. Serrations x9 | code: a.box in a.repeat | refs | steel\n"
            "  3. Lanyard hook | code: a.sweep of a round section | refs | steel\n")

    def setUp(self):
        self.p = Project()
        os.environ.pop("KIT_METHODS_LOCK", None)

    def tearDown(self):
        self.p.close()

    def brief(self, plan, locks=None):
        self.p.write("assets/models/x.brief.md", BRIEF + plan)
        self.p.write("assets/models/build_x.py", SCRIPT)
        if locks is not None:
            self.p.write("board/locks.json", locks)
        return self.p.stages()["brief"]

    def test_a_new_pieces_plan_is_held_until_every_coded_part_names_its_method(self):
        st = self.brief(self.BAD, {"grandfathered": {"3d-methods": []}})
        said = [m for m in st["missing"] if m.startswith("methods: ")]
        self.assertEqual(len(said), 1, st["missing"])
        self.assertIn('Serrations x9: many alike ("x9")', said[0])
        self.assertIn("Lanyard hook: code, but no METHOD", said[0])
        self.assertNotIn("Slide", said[0])

    def test_a_plan_that_names_them_passes_and_says_so(self):
        st = self.brief(self.GOOD, {"grandfathered": {"3d-methods": []}})
        self.assertFalse([m for m in st["missing"] if m.startswith("methods: ")], st["missing"])
        self.assertIn("methods: every coded part's line names how it is made", st["found"])

    def test_a_piece_that_existed_before_is_not_held(self):
        st = self.brief(self.BAD, {"grandfathered": {"3d-methods": ["assets/models/build_x.py"]}})
        self.assertFalse([m for m in st["missing"] if m.startswith("methods: ")], st["missing"])

    def test_a_project_that_never_switched_the_lock_on_is_not_held(self):
        st = self.brief(self.BAD)
        self.assertFalse([m for m in st["missing"] if m.startswith("methods: ")], st["missing"])


CUTS = '''
import json, os, sys
sys.path.insert(0, os.path.join(sys.argv[sys.argv.index("--") + 1], "kit", "blender"))
import rbx


def scene(name):
    a = rbx.Asset(name, size=(6, 3, 6), ground=False)
    a.material("iron", color=(0.3, 0.31, 0.33), metal=1.0, rough=0.5)
    return a


t = scene("_test_cut_typed")
t.box("Plate", (3.0, 0.2, 3.0), (0, -0.1, 0), "iron", bevel=0)
for i in range(5):
    t.cut("Plate", t.cylinder(f"Hole{i}", 0.05, 0.4, (-1.0 + 0.5 * i, 0, 0), "iron", axis="Y", segments=8))
typed = t._typed_alike()   # (read before the next scene: a new Asset clears the last one's objects)
r = scene("_test_cut_repeated")
r.box("Plate", (3.0, 0.2, 3.0), (0, -0.1, 0), "iron", bevel=0)
with r.repeat(5, step=(0.5, 0, 0)):
    hole = r.cylinder("Hole", 0.05, 0.4, (-1.0, 0, 0), "iron", axis="Y", segments=8)
r.cut("Plate", hole)
print("CUTS " + json.dumps({"typed": typed, "repeated": r._typed_alike(),
                            "holes": [len(r.parts), len(r._cut_shapes)]}))
'''


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Cutters(unittest.TestCase):
    """card 988z: cutters a.cut uses up are typed alike too - five holes typed as five cylinders"""

    @classmethod
    def setUpClass(cls):
        import tempfile  # noqa: PLC0415

        cls.tmp = tempfile.TemporaryDirectory()
        script = os.path.join(cls.tmp.name, "cuts.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(CUTS)
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join(cls.tmp.name, "build"))
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", ROOT],
                           cwd=ROOT, capture_output=True, text=True, timeout=900, env=e, encoding="utf-8",
                           errors="replace")
        line = next((x for x in r.stdout.splitlines() if x.startswith("CUTS ")), None)
        assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
        cls.d = json.loads(line.split(" ", 1)[1])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_cutters_typed_one_by_one_are_one_shape_typed_many_times(self):
        self.assertEqual(self.d["typed"], [[f"Hole{i}" for i in range(5)]])

    def test_a_cutter_made_in_a_repeat_is_typed_once(self):
        self.assertEqual(self.d["repeated"], [])
        self.assertEqual(self.d["holes"], [1, 1])      # (the plate left; one cutter recorded, its copies never)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER), "Blender not found")
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        e = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_methods"), KIT_METHODS_LOCK="1")
        r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                            os.path.join(ROOT, "kit", "selftest", "blender", "check_methods_lock.py"), "--",
                            "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=900, env=e,
                           encoding="utf-8", errors="replace")
        line = next((x for x in r.stdout.splitlines() if x.startswith("METHODS_LOCK ")), None)
        assert r.returncode == 0 and line, (r.stderr or r.stdout)[-800:]
        cls.d = json.loads(line.split(" ", 1)[1])

    def test_the_build_knows_which_methods_it_really_used_and_how_many_each_made(self):
        counts = {m: [P._use(x)[1] for x in v] for m, v in self.d["used"].items()}
        self.assertEqual(counts, {"box modelling": [1], "deform": [1], "repeat": [3], "scatter": [6],
                                  "smooth": [1], "sweep": [1]})
        # (and the part each use was on, so a use is held to its own plan line: card 988z)
        names = {m: [list(P._use(x)[0]) for x in v] for m, v in self.d["used"].items()}
        self.assertEqual(names, {"box modelling": [["Case"]], "deform": [["Horn"]], "repeat": [["Tooth"]],
                                 "scatter": [["Slab"]], "smooth": [["Pod"]], "sweep": [["Rail"]]})
        self.assertEqual(self.d["used_plain"], {})                       # a model of plain boxes used none
        self.assertEqual(sorted(P._use(x)[1] for x in self.d["used_good"]["repeat"]), [4, 5])  # four posts, five bolts
        self.assertEqual(sorted(P._use(x) for x in self.d["used_good"]["repeat"]), [(("Bolt",), 5), (("Post",), 4)])
        self.assertEqual([P._use(x)[1] for x in self.d["used_hair"]["repeat"]], [2, 2, 2, 2])    # a token repeat

    def test_alike_parts_typed_one_by_one_are_found_and_copies_are_not(self):
        self.assertEqual(sorted(self.d["typed"]), [["Bolt1", "Bolt2", "Bolt3", "Bolt4", "Bolt5"],
                                                   ["Post1", "Post2", "Post3", "Post4"]])   # the bolts and the fence
        self.assertEqual(self.d["typed_good"], [])                       # the same through a.repeat(at=) and a row
        self.assertEqual(self.d["bolts_good"], 5)

    def test_alike_is_alike_by_a_hair_in_another_material_fused_away_or_inside_a_repeat(self):
        self.assertEqual(sorted(self.d["typed_hair"]), [
            [f"Bolt{i}" for i in range(5)],                              # absorbed by a.fuse: counted as they were
            [f"Peg~{i}" for i in range(4)],                              # a "~" in a name is not a copy
            [f"Post{i}" for i in range(4)],                              # 0.0006 apart, two materials
            [f"Tooth{i}" for i in range(4)]])                            # typed INSIDE a repeat of two
        self.assertEqual(self.d["typed_different"], [])                  # four boxes of four sizes are four shapes

    def test_the_builds_check_holds_a_locked_piece_and_says_what_to_do(self):
        bad = self.d["check_bad"]
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["name"], "methods")
        self.assertTrue(any("Fence: its plan names repeat" in v for v in bad["value"]), bad["value"])
        self.assertTrue(any("5 parts are ONE shape typed 5 times" in v for v in bad["value"]), bad["value"])
        self.assertTrue(any("Bolts x5: its plan names repeat" in v for v in bad["value"]), bad["value"])
        self.assertTrue(self.d["check_good"]["ok"], self.d["check_good"])
        self.assertIsNone(self.d["check_blockout"])                      # a blockout is boxes on purpose
        self.assertIsNone(self.d["check_unlocked"])                      # the lock off: not this piece's business

    def test_a_repeat_at_places_starts_where_the_part_is(self):
        self.assertIn("is not where the part was modelled (Nub is round (0, 0.1, 0))", self.d["first_place"])
        self.assertEqual(self.d["pins"], 3)                              # places from a generator, with their count


if __name__ == "__main__":
    unittest.main()
