"""kit/prompt/ - PROMPT-X (LIMITATIONS_FIXES_V4 9 / 13.7): routing, the questions, the per-model compilation and the
SIX mandatory traps - (1) negative_word_leak, (2) model_drift_cot_on_codex, (3) token_budget_over_2500,
(4) missing_repo_grounding, (5) context_collapse_rewrite, (6) historical_ab_replay (+ the kickoff emission).
Evolve writes only into a temporary vault. Run: python kit/test/python/run.py -k test_prompt_x"""

import contextlib
import json
import re
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit"))
os.environ["KIT_GAME"] = "none"
from prompt import checks, clarify, cli, evolve, expand, models, route, subprompts  # noqa: E402
from prompt import compile as comp  # noqa: E402

V4_RAW = "yo make a fire katana slash ultimate like tanjiro water and fire, make it feel heavy not floaty and make the ui clean not slop"


def packet(raw=V4_RAW, model="claude", answers=None, lane=None):
    return comp.compile_packet(route.route_intent(raw, "none", lane), answers or {}, model)


@contextlib.contextmanager
def fixture_graveyard(rows):
    """route reads a temporary vault holding these graveyard rows ({lane: [(tried, result), ...]}): the kit ships none of
    its author's records, so a test that needs records brings its own"""
    tmp = tempfile.mkdtemp()
    saved = route._vault_dir
    try:
        for lane, items in rows.items():
            d = os.path.join(tmp, models.VAULT_LANE.get(lane, lane))
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "graveyard.md"), "w", encoding="utf-8") as f:
                f.write("| tried | when | result | the owner's words | do not retry because | link |\n|---|---|---|---|---|---|\n")
                for tried, result in items:
                    f.write(f"| {tried} | 2026-01-01 | {result} | - | a fixture record | |\n")
        route._vault_dir = lambda lane: os.path.join(tmp, models.VAULT_LANE.get(lane, lane))
        yield tmp
    finally:
        route._vault_dir = saved
        shutil.rmtree(tmp, ignore_errors=True)


class TempVault(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env = {k: os.environ.get(k) for k in ("KIT_PROMPT_VAULT", "KIT_PROMPT_TRACES", "KIT_PROMPT_TEMPLATES")}
        os.environ["KIT_PROMPT_VAULT"] = os.path.join(self.tmp, "vault")
        os.environ["KIT_PROMPT_TRACES"] = os.path.join(self.tmp, "traces.json")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)


class Routing(unittest.TestCase):
    def test_v4_worked_example_lanes(self):
        r = route.route_intent(V4_RAW, "none")
        self.assertEqual(r["lanes"], ["vfx", "anim", "ui", "sfx", "systems"])  # V4 9.4 stage 1
        self.assertIn("tanjiro", r["entities"]["sources"])
        self.assertEqual({c["lane"] for c in r["xp_coupling"]}, {"sfx", "systems"})

    def test_a_stray_noun_does_not_pull_a_lane(self):
        r = route.route_intent("make a heavy katana swing animation with a big wind-up", "none")
        self.assertEqual(r["lanes"][0], "anim")
        self.assertNotIn("3d", r["lanes"])

    def test_lane_hint_leads(self):
        r = route.route_intent("make it look better", "none", "world")
        self.assertEqual(r["lanes"][0], "world")

    def test_game_none_never_reads_a_game(self):
        self.assertIsNone(route.active_game("none"))
        self.assertIsNone(route.route_intent("a sword model", "none")["repo_grounding"]["game"])

    def test_empty_prompt_refused(self):
        with self.assertRaises(ValueError):
            route.route_intent("   ", "none")


class Clarify(unittest.TestCase):
    def test_at_most_three_questions_with_a_default(self):
        cl = clarify.audit_ambiguity(route.route_intent(V4_RAW, "none"))
        self.assertLessEqual(len(cl["questions"]), 3)
        for q in cl["questions"]:
            self.assertEqual(sum(o.startswith("*") for o in q["options"]), 1, q)
        # the repo's invariants are filled silently, never asked
        self.assertIn("anim.fps60", cl["auto_filled"])
        self.assertTrue(all("fps" not in q["question"].lower() for q in cl["questions"]))

    def test_a_said_slot_is_not_asked(self):
        cl = clarify.audit_ambiguity(route.route_intent("a calm katana swing animation, one move", "none"))
        slots = {q["slot"] for q in cl["questions"]}
        self.assertNotIn("anim.intent", slots)
        self.assertNotIn("anim.scope", slots)

    def test_destructive_scope_is_always_asked(self):
        cl = clarify.audit_ambiguity(route.route_intent("scrap the courtyard and rewrite the world", "none"))
        self.assertEqual(cl["questions"][0]["slot"].split(".")[1], "destructive")

    def test_answers_and_defaults(self):
        self.assertEqual(clarify.parse_answers("q1=b, q2:a"), {"q1": "B", "q2": "A"})
        r = route.route_intent("a katana swing animation", "none")
        cl = clarify.audit_ambiguity(r)
        qid = next(q["id"] for q in cl["questions"] if q["slot"] == "anim.intent")
        d = {x["id"]: x for x in clarify.decisions(cl, {qid: "C"})}
        self.assertTrue(d[qid]["chose"].startswith("aggressive"))
        self.assertEqual(d[qid]["how"], "answered")
        other = [x for x in d.values() if x["id"] != qid]
        self.assertTrue(all(x["how"].startswith("default") for x in other))


class Trap1NegativeWordLeak(unittest.TestCase):
    def test_flux_prompt_has_no_negation_and_keeps_positives(self):
        p = packet()
        flux = p["tool_subprompts"]["flux2"]
        self.assertEqual(checks.negative_word_leak(flux), [])
        self.assertIn("heavy grounded mass", flux)  # 'not floaty'
        self.assertIn("crisp vector-sharp silhouette", flux)  # 'not slop'

    def test_negated_fire_is_cut_and_replaced(self):
        out = subprompts.positive_substitute("a long katana, no fire or flames, without blur, never smoke")
        self.assertEqual(checks.negative_word_leak(out), [])
        for gone in ("fire", "flames", "blur", "smoke"):
            self.assertNotRegex(out, rf"\b{gone}\b")
        self.assertIn("cold clean blued steel", out)
        self.assertIn("clear still air", out)

    def test_asked_for_fire_survives(self):
        self.assertIn("fire", subprompts.flux2("vfx", "a fire slash with crimson ribbons"))

    def test_bans_are_stripped_anywhere(self):
        out = subprompts.positive_substitute("a hilt with a living flame", bans=["flame"])
        self.assertNotIn("flame", out.replace("cold clean blued steel, sharp unlit edges", ""))

    def test_the_gate_catches_a_leak(self):
        self.assertTrue(checks.negative_word_leak("a katana, no fire"))


class Trap2ModelDrift(unittest.TestCase):
    def test_each_profile_keeps_its_shape(self):
        raw = V4_RAW + " and think step by step about it"
        packets = {m: packet(raw, m) for m in ("claude", "codex", "gemini")}
        self.assertEqual(checks.model_drift(packets), [])
        self.assertIn("think step by step", packets["claude"]["orchestrator_prompt"].lower())  # claude keeps it

    def test_the_gate_catches_a_codex_cot_script(self):
        bad = packet(model="codex")
        bad = dict(bad, orchestrator_prompt=bad["orchestrator_prompt"] + "\nThink step by step before answering.")
        self.assertTrue(checks.model_drift({"codex": bad}))

    def test_model_resolution(self):
        self.assertEqual(comp.resolve_model(None, {"CODEX_CI": "1"}), "codex")
        self.assertEqual(comp.resolve_model(None, {"GEMINI_CLI": "1"}), "gemini")
        self.assertEqual(comp.resolve_model(None, {"KIT_AI_MODEL": "gpt"}), "codex")
        self.assertEqual(comp.resolve_model("local", {"CODEX_CI": "1"}), "local")
        self.assertEqual(comp.resolve_model(None, {}), "claude")

    def test_local_is_flat_json_on_one_lane(self):
        body = json.loads(packet(model="local")["orchestrator_prompt"])
        self.assertEqual(set(body), {"task", "decided", "must", "next", "check", "context", "answer"})
        self.assertLessEqual(len(body["next"]), 1)


class Trap3TokenBudget(unittest.TestCase):
    def test_every_profile_inside_its_budget(self):
        big = V4_RAW + " with a 3d sword model, a gothic courtyard world, footsteps sound set and a shop menu"
        for m in ("claude", "codex", "gemini", "local"):
            p = packet(big, m)
            self.assertEqual(checks.token_budget(p), [], m)
            self.assertTrue(p["pruned"], f"{m} pruned nothing on a six-lane ask")

    def test_priority_one_rules_survive_pruning(self):
        p = packet(model="codex")
        self.assertIn("real frames", p["orchestrator_prompt"])
        self.assertTrue(all(x["priority"] > 1 for x in p["pruned"]), [x for x in p["pruned"] if x["priority"] <= 1])

    def test_the_gate_catches_an_unpruned_render(self):
        r = route.route_intent(V4_RAW + " with a 3d sword model and a gothic courtyard world", "none")
        ir = expand.build_ir(r)
        text = comp._render(ir, comp._items(ir, models.profile("local")), models.profile("local"))
        self.assertTrue(checks.token_budget({"target_model": "local", "orchestrator_prompt": text}))


class Trap4Grounding(unittest.TestCase):
    def test_scoped_records_hydrated(self):
        p = packet()
        self.assertEqual(checks.missing_grounding(p), [])
        g = p["repo_grounding"]
        self.assertLessEqual(len(g["graveyard_bans"]), 5)
        self.assertLessEqual(len(g["golden_refs"]), 3)
        self.assertLessEqual(len(g["lessons_top5"]), 5)
        self.assertIn("Workspace.GetServerTimeNow", g["api_docs"])

    def test_source_words_reach_the_vault(self):
        # "tanjiro" is read as the FlameArc records' words (route.SOURCES): a record under the kit's own name is found
        with fixture_graveyard({"vfx": [("flame_arc_v1", "2/10"), ("ember_cloud", "2/10")]}):
            g = route.grounding(["vfx"], "a tanjiro slash", None)
            plain = route.grounding(["vfx"], "a slash", None)
        mine = [b for b in g["graveyard_bans"] if b["tried"].startswith("flame_arc")]
        self.assertTrue(mine and mine[0]["matched"] >= 1, g["graveyard_bans"])
        self.assertFalse([b for b in plain["graveyard_bans"] if b["tried"].startswith("flame_arc") and b["matched"]])

    def test_records_are_asked_for_where_the_vault_holds_them(self):
        p = packet()
        g = p["repo_grounding"]
        # a lane whose vault pages hold rows, and a prompt that came back without them: caught
        bad = dict(p, repo_grounding=dict(g, graveyard_bans=[], golden_refs=[], filed={"graveyard": ["vfx"], "golden": ["vfx"]}))
        problems = checks.missing_grounding(bad)
        for said in ("graveyard_bans is empty", "golden_refs is empty", "no vfx graveyard record"):
            self.assertTrue(any(said in x for x in problems), (said, problems))
        # a project whose pages hold no rows: nothing to hydrate, nothing asked for
        fresh = dict(p, repo_grounding=dict(g, graveyard_bans=[], golden_refs=[], filed={"graveyard": [], "golden": []}))
        self.assertEqual([x for x in checks.missing_grounding(fresh) if "graveyard" in x or "golden" in x], [])

    def test_filed_is_counted_from_the_vault_files_not_the_parser(self):
        page = os.path.join(ROOT, "kit", "knowledge", "vault", "3d", "golden.md")
        if not route._raw_rows(page):
            self.skipTest("the 3d golden page holds no row")
        saved = route._table
        route._table = lambda path: []  # a parser that loses every row
        try:
            g = route.grounding(["3d"], "a wooden chair 3d model", None)
        finally:
            route._table = saved
        self.assertIn("3d", g["filed"]["golden"])
        self.assertEqual(g["golden_refs"], [])
        self.assertTrue(any("golden_refs is empty" in x for x in checks.missing_grounding({"repo_grounding": g, "lanes": ["3d"], "orchestrator_prompt": ""})))

    def test_parts_never_hand_over_excluded_pieces(self):
        saved = route._EXCLUDE
        # a project that lists its private game + pieces (profiles.core.exclude_games / exclude_patterns)
        route._EXCLUDE = (re.compile(r"secret_move|^sp[_A-Z]|SamplePrivateGame", re.I), ["sampleprivategame"])
        try:
            for d in (
                {"piece": "secret_move", "src": "kit/anim/x.json"},
                {"piece": "sp_aura", "src": "library/vfx/x"},
                {"piece": "ok", "src": "games/SamplePrivateGame/assets/x.json"},
                {"piece": "SamplePrivateGame:DataService", "src": "x"},
            ):
                self.assertTrue(route._excluded_doc(d), d)
            for d in ({"piece": "katana_water_slash", "src": "library/vfx/x"}, {"piece": "celestial_crescent", "src": "x"}):
                self.assertFalse(route._excluded_doc(d), d)
        finally:
            route._EXCLUDE = saved
        # the kit's own default excludes nothing
        self.assertEqual(route._exclusions()[1], [])
        for p in packet()["repo_grounding"]["parts"]:
            self.assertFalse(route._excluded_doc(p), p)

    def test_the_gate_catches_an_empty_grounding(self):
        self.assertTrue(checks.missing_grounding(dict(packet(), repo_grounding={})))


class Trap5ContextCollapse(TempVault):
    def _packet_file(self, raw="a katana swing animation"):
        p = packet(raw)
        path = os.path.join(self.tmp, "p.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(p, f)
        return path, p

    def test_small_delta_accepted_and_learned(self):
        path, p = self._packet_file("a katana swing animation, calm, one move")
        r = evolve.reflect_and_propose(path, {"score": 4, "words": "it still feels floaty"})
        self.assertEqual(r["status"], "accepted", r.get("reason"))
        self.assertTrue(r["delta"]["add"])
        self.assertGreaterEqual(r["candidate"]["accuracy"], r["base"]["accuracy"])
        learned = evolve.learned_rules(["anim"], "claude")
        self.assertTrue(any("snap hold" in x["text"] for x in learned))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "vault", "changelog.json")))

    def test_wholesale_rewrite_rejected(self):
        path, _ = self._packet_file()
        rewrite = [f"rule {n}: be excellent at everything in every way" for n in range(6)]
        r = evolve.reflect_and_propose(path, {"score": 2, "words": "bad"}, proposed_rules=rewrite)
        self.assertEqual(r["status"], "rejected")
        self.assertIn("context collapse", r["reason"])
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, "vault", "pareto_frontier.json")))

    def test_token_explosion_rejected(self):
        path, _ = self._packet_file()
        huge = ["keep the weight " + "very " * 400]
        r = evolve.reflect_and_propose(path, {"score": 2, "words": "bad"}, proposed_rules=huge)
        self.assertEqual(r["status"], "rejected")
        self.assertIn("token growth", r["reason"])

    def test_benchmark_regression_rejected(self):
        path, _ = self._packet_file()
        real = evolve.evaluate
        calls = []

        def fake(cases=None, model=None):
            calls.append(1)
            return {"accuracy": 1.0 if len(calls) == 1 else 0.8, "tokens": 1000, "failed": [], "n": 10}

        evolve.evaluate = fake
        try:
            r = evolve.reflect_and_propose(path, {"score": 3, "words": "floaty and stiff"})
        finally:
            evolve.evaluate = real
        self.assertEqual(r["status"], "rejected")
        self.assertIn("fell", r["reason"])

    def test_counters_and_frontier_cap(self):
        fr = {"schema": 1, "frontiers": {"anim|claude": [{"id": str(n), "rules": [], "accuracy": 1.0 - n * 0.01, "tokens": 1000 + n} for n in range(8)]}}
        self.assertLessEqual(len(evolve._pareto(fr["frontiers"]["anim|claude"])), 5)


class Trap6HistoricalReplay(unittest.TestCase):
    def test_every_real_failure_carries_its_guardrail(self):
        cases = evolve.benchmark_cases()
        self.assertEqual(len(cases), 10)
        for m in ("claude", "codex", "gemini"):
            r = evolve.evaluate([dict(c, model=m) for c in cases])
            self.assertEqual(checks.replay(r), [], m)

    def test_the_gate_catches_a_template_without_the_guardrails(self):
        tmp = tempfile.mkdtemp()
        try:
            for lane in models.LANES:
                t = models.template(lane)
                t["invariants"] = t["invariants"][:1]  # the hard-won rules dropped (context collapse)
                with open(os.path.join(tmp, f"{lane}.json"), "w", encoding="utf-8") as f:
                    json.dump(t, f)
            os.environ["KIT_PROMPT_TEMPLATES"] = tmp
            r = evolve.evaluate()
            self.assertTrue(checks.replay(r))
            self.assertLess(r["accuracy"], 0.9)
        finally:
            os.environ.pop("KIT_PROMPT_TEMPLATES", None)
            shutil.rmtree(tmp, ignore_errors=True)

    def test_kickoff_emission(self):
        p = packet()
        cmd = cli.kickoff_command("FireKatanaUlt", p)
        self.assertEqual(cmd[:5], ["lune", "run", "kit", "kickoff", "FireKatanaUlt"])
        for flag in ("--vfx", "--anim", "--ui", "--sfx", "--code"):
            self.assertIn(flag, cmd)


class Negation(unittest.TestCase):
    """the review's adversarial inputs (2026-11-19): every one must come out positive"""

    ADVERSARIAL = [
        "a gold katana, never, ever glowing",
        "NO: fire",
        "a gold katana, it shouldn't have any fire",
        "a katana, don’t add text",
        "a fire-free katana",
        "a non-glowing blade",
        "a katana w/o fire",
        "a katana (no fire) with a gold hilt",
        "a long katana, no fire or flames, without blur, never smoke",
    ]

    def test_flux_never_carries_a_refused_word(self):
        for raw in self.ADVERSARIAL:
            out = subprompts.flux2("3d", raw)
            self.assertEqual(checks.negative_word_leak(out, raw), [], f"{raw!r} -> {out!r}")
            self.assertEqual(checks.negative_word_leak(subprompts.positive_substitute(raw), raw), [], raw)

    def test_the_positive_rest_survives(self):
        out = subprompts.positive_substitute("a red katana without fire and a gold hilt")
        self.assertIn("gold hilt", out)
        self.assertNotRegex(out, r"\bfire\b")
        self.assertIn("gold hilt", subprompts.positive_substitute("a katana (no fire) with a gold hilt"))

    def test_the_gate_catches_a_refused_word(self):
        self.assertTrue(checks.negative_word_leak("a gold katana with fire", "a gold katana, it shouldn't have any fire"))
        self.assertTrue(checks.negative_word_leak("a fire-free katana"))

    def test_routing_reads_negation(self):
        r = route.route_intent("katana swing animation, don't touch the ui or the world", "none")
        self.assertNotIn("ui", r["lanes"])
        self.assertNotIn("world", r["lanes"])
        cl = clarify.audit_ambiguity(route.route_intent("a katana swing animation, not calm", "none"))
        self.assertIn("anim.intent", {q["slot"] for q in cl["questions"]})
        self.assertNotEqual(subprompts.dsl_overrides(["anim"], "a katana swing animation, not calm")["anim"]["intent"], "calm")

    def test_floaty_asked_stays_light_floaty_refused_goes_heavy(self):
        light = subprompts.dsl_overrides(["anim"], "a floaty low-gravity moon jump animation")["anim"]
        heavy = subprompts.dsl_overrides(["anim"], "a sword swing, heavy not floaty")["anim"]
        self.assertEqual(light["pelvis_drop_st"], models.template("anim")["dsl"]["pelvis_drop_st"])
        self.assertEqual(heavy["pelvis_drop_st"], [-0.45, -0.35])

    def test_scrap_metal_is_not_destructive(self):
        self.assertEqual(route.entities("a scrap metal crate 3d model")["destructive"], [])
        self.assertTrue(route.entities("scrap it all and start over")["destructive"])


class CotSpellings(unittest.TestCase):
    VARIANTS = ["Think Step-By-Step", "think through it step by step", "work through this step by step", "Let us think step by step", "use chain-of-thought"]

    def test_codex_strips_every_spelling_and_the_gate_reads_them(self):
        raw = "a katana swing animation. " + ". ".join(self.VARIANTS)
        p = packet(raw, "codex")
        self.assertEqual(checks.model_drift({"codex": p}), [], p["orchestrator_prompt"][:400])
        self.assertNotIn("let us", p["orchestrator_prompt"].lower())
        for v in self.VARIANTS:
            bad = dict(p, orchestrator_prompt=p["orchestrator_prompt"] + "\n" + v)
            self.assertTrue(checks.model_drift({"codex": bad}), v)

    def test_banned_fluff_leaves_no_fragments(self):
        p = packet("make it good: a katana swing animation, high-quality", "claude")
        obj = p["orchestrator_prompt"].split("<objective>")[1].splitlines()[1]
        self.assertFalse(obj.startswith(":"), obj)
        self.assertNotIn("high-quality", obj.lower())


class EvolveLogic(TempVault):
    def _p(self, raw="a katana swing animation, calm, one move", model="claude"):
        return packet(raw, model)

    def test_praise_blames_nothing(self):
        g = evolve.textual_gradient(self._p(), {"score": 9.5, "words": "love it, finally not floaty at all"})
        self.assertEqual(g["blame"], [])
        g = evolve.textual_gradient(self._p(), {"score": 5, "words": "finally not floaty, but stiff"})
        self.assertEqual({b["word"] for b in g["blame"]}, {"stiff"})

    def test_a_negated_virtue_is_a_complaint(self):
        g = evolve.textual_gradient(self._p(), {"score": 4, "words": "it is not heavy enough"})
        self.assertIn("heavy", {b["word"] for b in g["blame"]})

    def test_a_second_delta_heads_the_frontier(self):
        p = self._p()
        r1 = evolve.reflect_and_propose(p, {"score": 4, "words": "still floaty"})
        self.assertEqual(r1["status"], "accepted", r1.get("reason"))
        r2 = evolve.reflect_and_propose(p, {"score": 4, "words": "and stiff"})
        self.assertEqual(r2["status"], "accepted", r2.get("reason"))
        texts = [r["text"] for r in evolve.best_rules("anim", "claude")]
        self.assertTrue(any("snap hold" in t for t in texts) and any("overlap" in t for t in texts), texts)

    def test_junk_rules_rejected_on_any_model(self):
        for model in ("claude", "codex"):
            r = evolve.reflect_and_propose(self._p(model=model), {"score": 3, "words": "bad"}, proposed_rules=["be excellent", "make it good always"])
            self.assertEqual(r["status"], "rejected", model)
            r = evolve.reflect_and_propose(self._p(model=model), {"score": 3, "words": "bad"}, proposed_rules=["a", "b", "c"])
            self.assertEqual(r["status"], "rejected", model)
            self.assertIn("vague", r["reason"])

    def test_packets_by_sha(self):
        p = self._p()
        sha = evolve.save_packet(p)
        self.assertEqual(evolve.load_packet(sha)["orchestrator_prompt"], p["orchestrator_prompt"])
        with self.assertRaises(ValueError):
            evolve.load_packet("deadbeef00")


class Fixes(unittest.TestCase):
    def test_kickoff_args_start_at_the_name(self):
        p = packet()
        cmd = cli.kickoff_command("FireKatanaUlt", p)
        self.assertEqual(cmd[4:][0], "FireKatanaUlt")
        self.assertEqual(cmd[4:][1], p["raw_prompt"])

    def test_api_names_verified_against_the_local_reference(self):
        if route._docs_index() is None:
            self.skipTest("no Roblox Studio API reference on this machine")
        for lane in models.LANES:
            _ok, problems = route.api_docs(models.template(lane)["api"])
            self.assertEqual(problems, [], lane)
        _ok, problems = route.api_docs(["Lighting.Technology", "Workspace.NoSuchThing"])
        self.assertEqual(len(problems), 2)

    def test_an_over_long_owner_prompt_is_trimmed_to_budget(self):
        raw = "make a katana swing animation " + "with lots of extra words about the swing " * 150
        p = packet(raw, "local")
        self.assertEqual(checks.token_budget(p), [])
        self.assertEqual(p["raw_prompt"], raw)

    def test_trellis_reads_cleanly(self):
        self.assertNotIn("isolated a ", subprompts.trellis2("3d", "a gold sword"))


class Round2(TempVault):
    """the second review's breakers (2026-11-19)"""

    def test_bare_words_never_open_a_negation(self):
        for raw, lane in (
            ("a stop-motion style katana idle animation", "anim"),
            ("a zero gravity jump animation for the R6 rig", "anim"),
            ("nothing fancy just a wooden crate 3d model", "3d"),
            ("dont make it floaty make it a heavy katana slash animation", "anim"),
        ):
            r = route.route_intent(raw, "none")
            self.assertEqual(r["lanes"][0], lane, raw)
        self.assertEqual(route.negated_spans("No - make a red katana 3d model with fire"), [])
        self.assertIn("red katana", subprompts.flux2("3d", "No - make a red katana 3d model with fire"))

    def test_more_negation_forms(self):
        for raw, gone in (
            ("a katana 3d model, neither fire nor smoke", {"fire", "smoke"}),
            ("a katana 3d model that lacks fire and lacks glow", {"fire", "glow"}),
            ("a smokeless flameless katana", {"smoke", "flame"}),
            ("a katana excluding fire", {"fire"}),
            ("a katana 3d model, glow: none, red hilt", {"glow"}),
            ("a glowing sword instead of a dull one", {"dull"}),
        ):
            self.assertTrue(gone <= route.negated_words(raw), (raw, route.negated_words(raw)))
            out = subprompts.flux2("3d", raw)
            self.assertEqual(checks.negative_word_leak(out, raw), [], (raw, out))
        self.assertEqual(route.negated_spans("a katana slash vfx, nothing but fire on the blade"), [])
        self.assertIn("red", subprompts.flux2("3d", "a katana 3d model, glow: none, red hilt"))

    def test_no_lane_is_refused(self):
        with self.assertRaises(ValueError):
            comp.compile_packet(route.route_intent("hmm idk whatever", "none"), {}, "claude")

    def test_excluded_records_never_reach_a_prompt(self):
        saved = route._EXCLUDE
        try:
            # a project that lists its private pieces (profiles.core.exclude_patterns): those records are never used
            route._EXCLUDE = (re.compile(r"secret_move|SamplePrivateGame", re.I), ["sampleprivategame"])
            self.assertTrue(route._excluded_record("secret_move swing", ""))
            self.assertTrue(route._excluded_record("", "a lesson from SamplePrivateGame's menu"))
            self.assertFalse(route._excluded_record("katana swing", "a calm underhip lesson"))
            # a project that excludes everything gets no record at all: every record source goes through the filter
            route._EXCLUDE = (re.compile(r"."), [])
            for raw, lane in (("a greatsword underhip swing animation", "anim"), ("a dark ink blade smear vfx", "vfx"),
                              ("a pistol fire animation from the side", "anim")):
                g = route.grounding([lane], raw, None)
                self.assertEqual((g["golden_refs"], g["graveyard_bans"], g["lessons_top5"], g["parts"]),
                                 ([], [], [], []), raw)
        finally:
            route._EXCLUDE = saved
        self.assertFalse(route._excluded_record("anything", "the kit's own default excludes nothing"))

    def test_a_long_prompt_keeps_its_rules(self):
        raw = "make a katana swing animation for my game, " + "it has to look really cool and smooth and stuff, " * 40
        for m in ("claude", "local"):
            p = packet(raw, m)
            self.assertEqual(checks.token_budget(p), [], m)
            self.assertIn("dossier", p["orchestrator_prompt"].lower(), m)
        self.assertEqual(checks.missing_grounding(packet(raw, "claude")), [])

    def test_counters_survive_an_accepted_delta(self):
        p = packet("a katana swing animation, calm, one move")
        self.assertEqual(evolve.reflect_and_propose(p, {"score": 4, "words": "still floaty"})["status"], "accepted")
        p2 = packet("a katana swing animation, calm, one move")  # now carries the learned rule
        r = evolve.reflect_and_propose(p2, {"score": 2, "words": "still floaty and stiff"})
        self.assertIn("accepted", r["status"])
        head = evolve.frontier()["frontiers"]["anim|claude"][0]["rules"]
        snap = next(x for x in head if "snap hold" in x["text"])
        self.assertEqual(snap["harmful"], 1, head)

    def test_a_control_prompt_does_not_match_another_failure(self):
        for raw, rec in (("a small green leaf puff vfx", "hollow_purple_v1"), ("a small lobby map", "sampleregion_terrain_v1")):
            for b in route.route_intent(raw, "none")["repo_grounding"]["graveyard_bans"]:
                if b["tried"].lower().startswith(rec):
                    self.assertEqual(b["matched"], 0, (raw, b))

    def test_kickoff_briefs_are_clean(self):
        p = packet("a heavy katana slash ability with fire vfx and a whoosh sound")
        for lane, brief in p["lane_briefs"].items():
            self.assertNotIn("(why:", brief, lane)
            self.assertFalse(re.match(r"^kit/", brief), lane)
            self.assertLessEqual(len(brief), 222, lane)
        for m in ("gemini", "local"):
            self.assertTrue(all("the " not in b[:4] or "part of" not in b for b in packet(model=m)["lane_briefs"].values()))

    def test_more_cot_spellings(self):
        for v in ("Think, step by step.", "think step‑by‑step", "reason it out step by step", "think this through carefully, step by step"):
            self.assertTrue(checks.find_cot(v), v)
            p = packet("a katana swing animation. " + v, "codex")
            self.assertEqual(checks.model_drift({"codex": p}), [], v)

    def test_every_api_named_in_a_template_is_current(self):
        if route._docs_index() is None:
            self.skipTest("no Roblox Studio API reference on this machine")
        for lane in models.LANES:
            text = json.dumps(models.template(lane))
            names = sorted(set(re.findall(r"\b([A-Z][A-Za-z]+\.[A-Z][A-Za-z]+)\b", text)))
            _ok, problems = route.api_docs(names)
            self.assertEqual(problems, [], lane)


class Round3(TempVault):
    """the third review's breakers (2026-11-19)"""

    def test_an_unspaced_dash_is_a_break(self):
        for raw, keep in (("no fire—bright blue glow and sparks", "blue"), ("no fire—blue orb", "orb")):
            self.assertIn(keep, subprompts.flux2("vfx", raw), raw)
            self.assertEqual(route.negated_words(raw), {"fire"}, raw)
        self.assertTrue(checks.find_cot("think step‑by‑step"))  # (a non-breaking HYPHEN still joins)

    def test_postfix_brackets_quotes_and_no_dash(self):
        for raw, gone in (
            ("blue orb, glowing: no", "glowing"),
            ("blue orb (glowing: no)", "glowing"),
            ("no (glowing) runes, blue orb", "glowing"),
            ("a katana, no-smoke trail, red sparks", "smoke"),
            ("no 'glow', red sword", "glow"),
        ):
            out = subprompts.flux2("vfx", raw)
            self.assertIn(gone, route.negated_words(raw), raw)
            self.assertNotRegex(out, rf"\b{gone}\b", (raw, out))
            self.assertEqual(checks.negative_word_leak(out, raw), [], raw)

    def test_free_form_cot_and_clean_briefs(self):
        for v in ("think hard, step by step", "think deeply step by step", "think about the problem step by step"):
            raw = "make a katana slash vfx and a heavy swing animation; " + v
            for m in ("codex", "local"):
                self.assertEqual(checks.model_drift({"codex": packet(raw, "codex")}), [], v)
            briefs = " ".join(packet(raw)["lane_briefs"].values())
            self.assertEqual(checks.find_cot(briefs), [], v)

    def test_a_long_prompt_on_local_keeps_its_records(self):
        raw = "make a heavy katana slash vfx with crimson fire and sparks " * 8
        self.assertEqual(checks.missing_grounding(packet(raw, "local")), [])

    def test_a_space_less_prompt_keeps_its_head(self):
        p = packet("katana" + "x" * 9000, "claude", lane="vfx")
        self.assertIn("katanax", p["orchestrator_prompt"].lower())
        self.assertEqual(checks.token_budget(p), [])

    def test_generic_prompts_fail_the_replay(self):
        # judged WITH the benchmark's own records: the project's, or (the kit ships none of its author's) one fixture row
        # per case carrying only its record name's words - never the prompt's
        cases = evolve.benchmark_cases()
        rows = {}
        for c in cases:
            if c.get("graveyard"):
                rows.setdefault(c["lane"], []).append((c["graveyard"], "2/10"))
        with fixture_graveyard(rows) if evolve.evaluate(cases)["unfiled"] else contextlib.nullcontext():
            self.assertEqual(evolve.evaluate(cases)["unfiled"], [])
            # the records are findable: most real prompts find theirs (a fixture row has only its name's words, so not
            # every one), far above what a generic prompt scores below
            self.assertGreaterEqual(evolve.evaluate(cases)["accuracy"], 0.5)
            for g in ("Build an R6 rig animation.", "Build a region terrain.", "Build an in-game HUD.", "Build a vfx effect."):
                r = evolve.evaluate([dict(c, raw_prompt=g) for c in cases])
                self.assertLessEqual(r["accuracy"], 0.1, g)

    def test_a_proposed_rule_can_land(self):
        p = packet("a katana slash vfx with a heavy hit")
        r = evolve.reflect_and_propose(p, {"score": 4, "words": "the hit has no anticipation"}, proposed_rules=["every slash gets two anticipation frames held before the hit frame"])
        self.assertEqual(r["status"], "accepted", r.get("reason"))


class Templates(unittest.TestCase):
    def test_every_template_and_profile_is_complete(self):
        for lane in models.LANES:
            t = models.template(lane)
            for key in ("start", "keywords", "invariants", "slots", "steps", "done_when", "failure_lexicon"):
                self.assertIn(key, t, f"{lane}.{key}")
            for s in t["slots"]:
                self.assertEqual(sum(o.startswith("*") for o in s["options"]), 1, f"{lane}.{s['id']}")
        for name in models.MODELS + models.TOOLS:
            self.assertEqual(models.profile(name)["name"], name)

    def test_substitutions_are_positive(self):
        prof = models.profile("flux2")
        for k, v in prof["substitutions"].items():
            self.assertEqual(checks.negative_word_leak(v), [], k)

    def test_named_files_exist(self):
        for lane in models.LANES:
            for f in models.template(lane).get("context_files", []):
                if "<" not in f:
                    self.assertTrue(os.path.isfile(os.path.join(ROOT, f)), f"{lane}: {f}")


class CaseContracts(unittest.TestCase):
    """PARALLAX spec §3.2-3.3: the router names the CASE of each lane and the lead lane's capability menu; the compiled
    prompt carries the contract as a rule and the menu as a step, inside every model's budget"""

    def test_route_attaches_contracts_and_the_menu(self):
        r = route.route_intent("make a gothic sword with a carved lion pommel", "none", "3d")
        ids = [c["case_id"] for c in r["case_contracts"]]
        self.assertIn("3d:hybrid_hero", ids)
        self.assertEqual(r["capability_lane"], "3d")
        self.assertTrue(0 < len(r["capability_menu"]) <= 25)
        c = next(c for c in r["case_contracts"] if c["case_id"] == "3d:hybrid_hero")
        self.assertTrue(c["required_tools"])
        self.assertIn("whole_object_gen", c["forbidden_tools"])

    def test_systems_prompts_get_code_and_qa_cases(self):
        r = route.route_intent("add a dash ability with a server playtest that fuzzes the remote", "none", "code")
        lanes = {c["lane"] for c in r["case_contracts"]}
        self.assertIn("code", lanes)
        self.assertIn("qa", lanes)

    def test_compiled_prompt_carries_the_case_within_budget(self):
        for model in ("claude", "codex", "gemini", "local"):
            p = packet("make a gothic sword with a carved lion pommel", model, lane="3d")
            self.assertIn("3d:hybrid_hero", [c["case_id"] for c in p["case_contracts"]])
            self.assertLessEqual(p["token_count"], models.profile(model)["budget"], model)
        full = packet("make a gothic sword with a carved lion pommel", "claude", lane="3d")
        self.assertIn("case 3d:hybrid_hero", full["orchestrator_prompt"])
        self.assertIn("capability menu", full["orchestrator_prompt"])

    def test_the_kit_lane_compiles(self):
        # (kit / parallax: the kit's own work routes as systems; it once failed "no lane matched")
        p = packet("implement the enforcement gate in the kit", "claude", lane="kit")
        self.assertIn("systems", p["lanes"])


if __name__ == "__main__":
    unittest.main()
