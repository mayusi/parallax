"""kit/tools/lanecheck.py — every lane but 3D asks it before a build (card b6m2, the owner 2026-11-10: "keep going on the
3D ... but don't forget about the other ones" + "Yes, same budgets"): the piece's clock (10 / 30 / 60 minutes by tier, only
the owner's words reopen it, the piece as it was may still be built) and its route (a route its lessons sheet was not
answered for refuses the build until kit answer <lane> <name> --reroute).
Run: python -m pytest kit/test/python/test_lanecheck.py -q"""

import json
import os
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import lanecheck as LC  # noqa: E402


class Project:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def write(self, rel, data):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(data if isinstance(data, str) else json.dumps(data))
        return path

    def dir(self, lane):
        return os.path.join(self.root, LC.LANE_DIR[lane])

    def answers(self):
        with open(os.path.join(self.root, "board", "answers.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def clock(self, lane, name):
        with open(LC.clock_path(lane, name, self.dir(lane)), encoding="utf-8") as fh:
            return json.load(fh)


class LaneTest(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        self.addCleanup(self.p.tmp.cleanup)
        self.keep = LC.ROOT
        LC.ROOT = self.p.root
        self.addCleanup(setattr, LC, "ROOT", self.keep)
        self.t0 = 1_800_000_000.0

    def key(self, lane, name):
        return LC.sheet_key(self.p.dir(lane), name)

    def record(self, lane, name, route=None):
        e = {"dept": lane, "piece": name, "must": []}
        if route is not None:
            e["route"] = list(route)
        self.p.write("board/answers.json", {self.key(lane, name): e})


class TestRoutes(LaneTest):
    def test_vfx_reads_the_technique_families_of_its_layers(self):
        self.p.write("assets/effects/fire.json", {"layers": [{"kind": "mesh"}, {"kind": "sprite"}, {"kind": "sprite"},
                                                             {"kind": "debris"}, {"kind": "shake"}, {"kind": "sound"}]})
        self.assertEqual(LC.route("vfx", "fire", self.p.dir("vfx")), ("camera", "flipbook", "mesh", "particles"))

    def test_anim_reads_its_dossiers_builder_and_source_kinds(self):
        self.p.write("assets/animations/dossiers/greatsword_overhead.json",
                     {"build": {"builder": "strike", "move_file": "assets/animations/GreatswordOverhead.move.json"}})
        self.p.write("assets/animations/dossiers/sg_run.json", {"direction": "SgLocomotion"})
        self.assertEqual(LC.route("anim", "greatsword_overhead", self.p.dir("anim")), ("builder strike", "move"))
        self.assertEqual(LC.route("anim", "sg_run", self.p.dir("anim")), ())

    def test_sfx_tells_a_real_recording_from_synthesis(self):
        self.p.write("assets/sounds/swish.json", {"layers": [{"source": "noise"}, {"source": "fm"}]})
        self.assertEqual(LC.route("sfx", "swish", self.p.dir("sfx")), ("synth",))
        self.p.write("assets/sounds/sets/sword.json", {"dna": {"layers": [{"source": "noise"}]},
                                                       "members": {"hit": {"layers": [{"sample": "lib/hit.wav"}]}}})
        self.assertEqual(LC.route("sfx", "sword", os.path.join(self.p.root, "assets/sounds/sets")), ("recorded", "synth"))

    def test_world_reads_terrain_and_mesh_skins(self):
        self.p.write("assets/worlds/isle.json", {"terrain": [{"op": "rivers"}], "build": [{"building": {"meshes": ["a"]}}]})
        self.p.write("assets/worlds/arena.json", {"build": [{"floor": {}}]})
        self.assertEqual(LC.route("world", "isle", self.p.dir("world")), ("meshes", "terrain"))
        self.assertEqual(LC.route("world", "arena", self.p.dir("world")), ())

    def test_a_clip_is_taken_to_the_dossier_that_builds_it(self):
        d = self.p.dir("anim")
        self.p.write("assets/animations/dossiers/greatsword_overhead.json",
                     {"build": {"builder": "strike", "move_file": "assets/animations/GreatswordOverhead.move.json"}})
        self.p.write("assets/animations/dossiers/spin_drill.json",
                     {"build": {"builder": "fp_weapon", "gestures": {"DTDrillSpin*": "blade_drill_spin"}}})
        self.assertEqual(LC.anim_piece_of("GreatswordOverhead", d), "greatsword_overhead")
        self.assertEqual(LC.anim_piece_of("DTDrillSpinB", d), "spin_drill")
        self.assertIsNone(LC.anim_piece_of("SgRun", d))


class TestClock(LaneTest):
    def setUp(self):
        super().setUp()
        self.p.write("assets/effects/fire.json", {"layers": [{"kind": "sprite"}]})
        self.d = self.p.dir("vfx")

    def pre(self, minutes, tier="simple", use_clock=True):
        return LC.prebuild("vfx", "fire", self.d, tier=tier, use_clock=use_clock, now=self.t0 + minutes * 60)

    def test_the_clock_starts_at_the_first_build_and_stops_a_change_past_its_budget(self):
        stop, _s, _a, lines = self.pre(0)
        self.assertFalse(stop)
        self.assertTrue(any("clock started: 10 min (simple)" in ln for ln in lines), lines)
        self.assertFalse(self.pre(9)[0])
        self.p.write("assets/effects/fire.json", {"layers": [{"kind": "sprite"}, {"kind": "debris"}]})
        stop, summary, action, lines = self.pre(11)
        self.assertTrue(stop)
        self.assertIn("STOP — BUDGET: 11 of 10 min (simple, attempt 1)", summary)
        self.assertIn('lune run kit clock vfx fire --extend <minutes> "<his words>"', action)
        self.assertTrue(any("kit vfx play fire" in ln for ln in lines), lines)

    def test_past_its_budget_the_piece_as_it_was_may_still_be_played_or_rebuilt(self):
        self.pre(0)
        stop, summary, _a, _l = self.pre(30)
        self.assertFalse(stop, summary)
        self.assertIn("unchanged since its last build", summary)

    def test_only_the_owners_words_reopen_it_and_the_tier_is_the_attempts(self):
        self.pre(0, tier="complex")
        self.assertEqual(self.p.clock("vfx", "fire")["tier"], "complex")
        self.p.write("assets/effects/fire.json", {"layers": [{"kind": "mesh"}]})
        self.assertTrue(self.pre(31, tier="hero")[0])  # (a hero tier said mid-attempt lifts nothing)
        LC.write_clock("vfx", "fire", self.d, extend=20, words="go on with the rings", now=self.t0 + 31 * 60)
        self.assertFalse(self.pre(40)[0])
        c = LC.write_clock("vfx", "fire", self.d, tier="simple", restart=True, words="a new take", now=self.t0 + 90 * 60)
        self.assertEqual((c["attempt"], c["tier"], c["budget_min"]), (2, "simple", 10))

    def test_a_look_at_an_unchanged_piece_starts_no_clock_and_a_changed_one_does(self):
        stop, summary, _a, _l = LC.prebuild("vfx", "fire", self.d, look=True, now=self.t0)
        self.assertFalse(stop)
        self.assertFalse(os.path.isfile(LC.clock_path("vfx", "fire", self.d)))
        self.assertIn("no clock (a look at it unchanged)", summary)
        self.assertFalse(LC.prebuild("vfx", "fire", self.d, look=True, now=self.t0 + 60)[0])
        self.assertFalse(os.path.isfile(LC.clock_path("vfx", "fire", self.d)))
        self.p.write("assets/effects/fire.json", {"layers": [{"kind": "sprite"}, {"kind": "light"}]})
        _stop, _s, _a, lines = LC.prebuild("vfx", "fire", self.d, look=True, now=self.t0 + 120)
        self.assertTrue(any("clock started" in ln for ln in lines), lines)
        self.p.write("assets/effects/fire.json", {"layers": [{"kind": "sprite"}]})
        self.assertTrue(LC.prebuild("vfx", "fire", self.d, look=True, now=self.t0 + 120 + 31 * 60)[0])

    def test_the_command_takes_the_owners_words_only(self):
        import contextlib  # noqa: PLC0415
        import io  # noqa: PLC0415
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(LC.main(["extend", "vfx", "fire", "5", "--dir", self.d]), 2)
            self.assertEqual(LC.main(["restart", "vfx", "fire", "--dir", self.d]), 2)
            self.assertEqual(LC.main(["extend", "vfx", "fire", "5", "keep going", "--dir", self.d]), 0)


class TestRoute(LaneTest):
    def setUp(self):
        super().setUp()
        self.p.write("assets/sounds/swish.json", {"layers": [{"source": "noise"}]})
        self.d = self.p.dir("sfx")

    def pre(self, minutes=0):
        return LC.prebuild("sfx", "swish", self.d, use_clock=False, now=self.t0 + minutes * 60)

    def test_a_route_its_sheet_was_not_answered_for_stops_the_build(self):
        self.record("sfx", "swish", route=["synth"])
        self.assertFalse(self.pre()[0])
        self.p.write("assets/sounds/swish.json", {"layers": [{"source": "noise"}, {"sample": "lib/swish.wav"}]})
        stop, summary, action, _l = self.pre()
        self.assertTrue(stop)
        self.assertIn("STOP — ROUTE changed (synth -> recorded, synth)", summary)
        self.assertIn("lune run kit answer sfx swish --reroute", action)

    def test_a_sheet_from_before_routes_takes_the_route_it_first_builds_on(self):
        self.record("sfx", "swish")
        self.assertFalse(self.pre()[0])
        self.assertEqual(self.p.answers()[self.key("sfx", "swish")]["route"], ["synth"])
        self.p.write("assets/sounds/swish.json", {"layers": [{"sample": "lib/swish.wav"}]})
        self.assertTrue(self.pre()[0])

    def test_a_piece_with_no_sheet_is_not_routed(self):
        self.assertFalse(self.pre()[0])


class TestReviewFixes(LaneTest):
    """the core review's findings (card b6m2): each a case the first version got wrong"""

    def sfx(self, layers):
        self.p.write("assets/sounds/swish.json", {"layers": layers})
        return self.p.dir("sfx")

    def test_a_way_dropped_asks_nothing_new(self):
        d = self.sfx([{"source": "noise"}])
        self.record("sfx", "swish", route=["recorded", "synth"])
        stop, summary, _a, _l = LC.prebuild("sfx", "swish", d, use_clock=False)
        self.assertFalse(stop, summary)

    def test_an_empty_route_from_the_luau_side_is_the_empty_route_and_never_stamped_over(self):
        d = self.sfx([{"source": "noise"}])
        key = self.key("sfx", "swish")
        self.p.write("board/answers.json", {key: {"dept": "sfx", "piece": "swish", "must": [], "route": {}}})
        self.assertEqual(LC.answered_route(d, "swish"), ())
        stop, summary, _a, _l = LC.prebuild("sfx", "swish", d, use_clock=False)
        self.assertTrue(stop)
        self.assertIn("(new: synth)", summary)
        self.assertEqual(self.p.answers()[key]["route"], {})

    def test_the_record_is_found_in_any_letter_case(self):
        d = self.sfx([{"source": "noise"}])
        self.record("sfx", "Swish", route=["synth"])
        self.assertEqual(LC.answered_route(d, "swish"), ("synth",))
        self.assertFalse(LC.stamp_route(d, "swish", ("recorded",)))

    def test_a_clip_is_never_taken_by_a_builder_a_base_or_a_note(self):
        d = self.p.dir("anim")
        self.p.write("assets/animations/dossiers/head_hook.json",
                     {"build": {"builder": "GunIdle", "base": "BrawlerIdle",
                                "calibrated": "toward assets/animations/BrawlerIdle.move.json",
                                "move_file": "assets/animations/HeadHook.move.json"}})
        self.assertIsNone(LC.anim_piece_of("BrawlerIdle", d))
        self.assertIsNone(LC.anim_piece_of("GunIdle", d))
        self.assertEqual(LC.anim_piece_of("HeadHook", d), "head_hook")
        self.assertEqual(LC.route("anim", "head_hook", d), ("builder GunIdle", "move"))

    def test_the_digest_is_what_the_piece_is_made_of_never_a_look_or_a_note(self):
        self.p.write("assets/worlds/isle.json", {"terrain": [{"op": "heightmap", "file": "assets/worlds/isle_height.png"}],
                                                 "note": "tuned with kit/world/terrain.py, see board/plans/x.md"})
        self.p.write("assets/worlds/isle_height.png", "v1")
        self.p.write("kit/world/terrain.py", "a = 1")
        self.p.write("board/plans/x.md", "plan")
        d = self.p.dir("world")
        before = LC.digest("world", "isle", d)
        self.p.write("assets/worlds/isle.look.json", {"seen": 1})
        self.p.write("assets/worlds/isle.verdict.json", {"score": 7})
        self.p.write("assets/worlds/isle.lessons.md", "answers")
        self.p.write("kit/world/terrain.py", "a = 22")
        self.p.write("board/plans/x.md", "plan 2")
        self.assertEqual(LC.digest("world", "isle", d), before)
        self.p.write("assets/worlds/isle_height.png", "v22")
        self.assertNotEqual(LC.digest("world", "isle", d), before)

    def test_a_dossiers_digest_holds_the_sources_of_the_clips_it_builds(self):
        d = self.p.dir("anim")
        self.p.write("assets/animations/dossiers/spin_drill.json",
                     {"build": {"builder": "fp_weapon", "gestures": {"DTDrillSpin*": "blade_drill_spin"}}})
        self.p.write("assets/animations/DTDrillSpin4.move.json", {"keys": 1})
        self.p.write("assets/animations/GunFire.move.json", {"keys": 1})
        before = LC.digest("anim", "spin_drill", d)
        self.p.write("assets/animations/GunFire.move.json", {"keys": 22})
        self.assertEqual(LC.digest("anim", "spin_drill", d), before)
        self.p.write("assets/animations/DTDrillSpin4.move.json", {"keys": 22})
        self.assertNotEqual(LC.digest("anim", "spin_drill", d), before)

    def test_a_sound_and_a_set_of_one_name_keep_their_own_clocks(self):
        self.p.write("assets/sounds/hit.json", {"layers": [{"source": "noise"}]})
        self.p.write("assets/sounds/sets/hit.json", {"members": {}})
        sets = os.path.join(self.p.root, "assets", "sounds", "sets")
        self.assertNotEqual(LC.clock_path("sfx", "hit", self.p.dir("sfx")), LC.clock_path("sfx", "hit", sets))
        self.assertEqual(LC.spec_tier("sfx", "hit", sets), "complex")

    def test_a_spec_that_is_a_list_reads_as_empty(self):
        self.p.write("assets/effects/odd.json", [1, 2])
        self.assertEqual(LC.route("vfx", "odd", self.p.dir("vfx")), ())
        self.assertFalse(LC.prebuild("vfx", "odd", self.p.dir("vfx"), look=True)[0])

    def test_an_extension_of_a_clock_never_started_takes_the_specs_tier(self):
        import contextlib  # noqa: PLC0415
        import io  # noqa: PLC0415
        self.p.write("assets/effects/nova.json", {"layers": []})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(LC.main(["extend", "vfx", "nova", "5", "keep going", "--dir", self.p.dir("vfx")]), 0)
        with open(LC.clock_path("vfx", "nova", self.p.dir("vfx")), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["tier"], "complex")

class TestEveryPiece(LaneTest):
    def test_every_piece_reads_an_empty_route_and_stamps_an_unrouted_sheet(self):
        self.p.write("assets/worlds/isle.json", {"terrain": [{"op": "rivers"}]})
        self.p.write("assets/worlds/arena.json", {"build": [{"floor": {}}]})
        d = self.p.dir("world")
        self.p.write("board/answers.json", {
            self.key("world", "isle"): {"dept": "world", "piece": "isle", "must": [], "route": {}},
            self.key("world", "arena"): {"dept": "world", "piece": "arena", "must": [], "note": "\u2014 kept"}})
        stop, _s, _a, lines = LC.prebuild_all("world", "", now=self.t0)
        self.assertTrue(stop)
        self.assertIn("isle: made a new way (+ terrain)", lines[0])
        self.p.write("board/answers.json", {
            self.key("world", "arena"): {"dept": "world", "piece": "arena", "must": [], "note": "\u2014 kept"}})
        self.assertFalse(LC.prebuild_all("world", "", now=self.t0)[0])
        self.assertEqual(self.p.answers()[self.key("world", "arena")]["route"], [])
        with open(os.path.join(self.p.root, "board", "answers.json"), encoding="utf-8") as fh:
            self.assertIn("\u2014 kept", fh.read())  # (non-ASCII kept as it is)

    def test_a_rebuild_of_every_piece_starts_no_clock_and_holds_only_what_it_must(self):
        import contextlib  # noqa: PLC0415
        import io  # noqa: PLC0415
        d = self.p.dir("vfx")
        past = time.time() - 3600
        for n in ("fire", "ice"):
            self.p.write(f"assets/effects/{n}.json", {"layers": [{"kind": "sprite"}]})
            self.assertFalse(LC.prebuild("vfx", n, d, now=past)[0])
        self.p.write("assets/effects/wind.json", {"layers": [{"kind": "sprite"}]})
        self.record("vfx", "wind", route=["flipbook"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(LC.main(["prebuild-all", "vfx"]), 0)
        self.p.write("assets/effects/fire.json", {"layers": [{"kind": "sprite"}, {"kind": "debris"}]})
        self.p.write("assets/effects/wind.json", {"layers": [{"kind": "sprite"}, {"kind": "mesh"}]})
        stop, summary, _a, lines = LC.prebuild_all("vfx", "")
        self.assertTrue(stop)
        self.assertEqual(len(lines), 2, lines)
        self.assertIn("fire: past its budget", lines[0])
        self.assertIn("wind: made a new way (+ mesh)", lines[1])
        self.assertFalse(os.path.isfile(LC.clock_path("vfx", "wind", d)))
        self.assertEqual(self.p.answers()[self.key("vfx", "wind")]["route"], ["flipbook"])

    def test_a_piece_new_or_changed_since_the_last_rebuild_starts_its_clock_there(self):
        d = self.p.dir("world")
        self.p.write("assets/worlds/isle.json", {"build": [{"floor": {}}]})
        self.p.write("assets/worlds/arena.json", {"build": [{"floor": {}}]})
        stop, summary, _a, _l = LC.prebuild_all("world", "", now=self.t0)
        self.assertFalse(stop)
        self.assertNotIn("clock(s) started", summary)  # (the folder's first rebuild only records)
        self.assertFalse(os.path.isfile(LC.clock_path("world", "isle", d)))
        self.p.write("assets/worlds/isle.json", {"build": [{"floor": {}}, {"wall": {}}]})
        self.p.write("assets/worlds/keep.json", {"build": []})
        stop, summary, _a, _l = LC.prebuild_all("world", "", now=self.t0 + 60)
        self.assertFalse(stop)
        self.assertIn("2 clock(s) started", summary)
        self.assertEqual(self.p.clock("world", "isle")["tier"], "complex")
        self.assertFalse(os.path.isfile(LC.clock_path("world", "arena", d)))
        self.assertFalse(LC.prebuild_all("world", "", now=self.t0 + 45 * 60)[0])  # (as it was: it still builds)
        self.p.write("assets/worlds/isle.json", {"build": [{"floor": {}}]})
        stop, _s, _a, lines = LC.prebuild_all("world", "", now=self.t0 + 45 * 60)
        self.assertTrue(stop)
        self.assertIn("isle: past its budget", lines[0])

    def test_a_hero_hour_is_the_owners_to_give_and_a_sound_set_is_complex(self):
        self.p.write("assets/effects/nova.json", {"tier": "hero", "layers": []})
        self.assertEqual(LC.spec_tier("vfx", "nova", self.p.dir("vfx")), "complex")
        self.assertEqual(LC.spec_tier("vfx", "nova", self.p.dir("vfx"), hero_ok=True), "hero")
        self.p.write("assets/sounds/sets/sword.json", {})
        self.p.write("assets/sounds/swish.json", {})
        self.assertEqual(LC.spec_tier("sfx", "sword", os.path.join(self.p.root, "assets/sounds/sets")), "complex")
        self.assertEqual(LC.spec_tier("sfx", "swish", self.p.dir("sfx")), "simple")


class TestTheOwnersExtension(LaneTest):
    """the owner's budgets are BUILD time (2026-11-11: his "Yes, 30 more minutes" on the revolver was eaten by the
    1.5 h it waited for his verdict): minutes he gives after the run-out count from when he gives them"""

    def setUp(self):
        super().setUp()
        self.p.write("assets/effects/fire.json", {"layers": [{"kind": "sprite"}]})
        self.d = self.p.dir("vfx")
        LC.prebuild("vfx", "fire", self.d, tier="simple", now=self.t0)  # (a 10-minute budget from the first build)

    def test_minutes_given_after_the_run_out_count_from_when_he_gives_them(self):
        later = self.t0 + 200 * 60  # (the wait for his verdict)
        LC.write_clock("vfx", "fire", self.d, extend=30, words="Yes, 30 more minutes", now=later)
        c = LC.read_clock("vfx", "fire", self.d, now=later + 60)
        self.assertFalse(c["over"])
        self.assertAlmostEqual(c["left_min"], 29.0, places=1)
        self.assertEqual(c["extended_min"], 30)  # (what he gave, as he gave it)
        self.assertTrue(LC.read_clock("vfx", "fire", self.d, now=later + 31 * 60)["over"])

    def test_minutes_given_before_the_run_out_add_to_the_deadline(self):
        LC.write_clock("vfx", "fire", self.d, extend=30, words="more time", now=self.t0 + 5 * 60)
        self.assertFalse(LC.read_clock("vfx", "fire", self.d, now=self.t0 + 39 * 60)["over"])
        self.assertTrue(LC.read_clock("vfx", "fire", self.d, now=self.t0 + 41 * 60)["over"])

    def test_the_3d_clock_reads_the_same_rule(self):
        start = 1_800_000_000.0
        dl = LC.PL.clock_deadline
        self.assertEqual(dl(start, 60, [{"minutes": 30, "at": start + 200 * 60}]), start + 230 * 60)
        self.assertEqual(dl(start, 60, [{"minutes": 30, "at": start + 10 * 60}]), start + 90 * 60)
        self.assertEqual(dl(start, 60, [{"minutes": 30}]), start + 90 * 60)  # (no time recorded: added to it)
        two = [{"minutes": 30, "at": start + 150 * 60}, {"minutes": 30, "at": start + 209 * 60}]
        self.assertEqual(dl(start, 60, two), start + 239 * 60)  # (each one from its own moment when past it)


if __name__ == "__main__":
    unittest.main()
