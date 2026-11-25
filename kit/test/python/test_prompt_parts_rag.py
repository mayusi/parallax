"""kit/prompt/partsrag.py - PROMPT-X's Parts RAG over kit/tools/parts.py's libraries (LIMITATIONS_FIXES_V4 9.2 row 1:
"kit parts <lane> find/plan (P0-P8, respecting look-allow vs mechanics-only)"): every lane's OWN library and kinds, the
systems lane asking code's and QA's, a named piece broken into parts from its brief, AVOID cards as guardrails,
know-how, P8 upkeep on what is shown, the look hidden, Sample Game never, and the gate that refuses a packet without it.
Run: python kit/test/python/run.py -k test_prompt_parts_rag"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
# the car_wheel_rim brief is a game asset (assets/models/): a project has it, the kit's own repo does not
HAS_RIM_BRIEF = os.path.isfile(os.path.join(ROOT, "assets", "models", "car_wheel_rim.brief.md"))
sys.path.insert(0, os.path.join(ROOT, "kit"))
os.environ["KIT_GAME"] = "none"
from prompt import checks, expand, models, partsrag, route  # noqa: E402
from prompt import compile as comp  # noqa: E402

V4_RAW = "yo make a fire katana slash ultimate like tanjiro water and fire, make it feel heavy not floaty and make the ui clean not slop"
LANE_WORDS = {
    "3d": "a round alloy rim with five spokes",
    "vfx": "a katana slash with a shockwave ring",
    "anim": "a heavy katana swing with planted feet",
    "world": "a gothic courtyard with stairs and an arch",
    "ui": "a health bar and a cooldown button",
    "sfx": "a heavy sword hit with a sharp transient and a room tail",
    "systems": "a server combo system with rate limited remotes",
}


def lookup(lanes, raw, **kw):
    return route.parts_lookup(lanes, raw, **kw)


class Libraries(unittest.TestCase):
    def test_every_lane_asks_its_own_library(self):
        for lane in models.LANES:
            got = lookup([lane], LANE_WORDS[lane])
            want = partsrag.libraries(lane, LANE_WORDS[lane])[0]
            self.assertEqual(got["libraries"][0]["library"], want, lane)
            self.assertTrue(got["cards"], lane)
            self.assertEqual({c["library"] for c in got["cards"]}, {want}, lane)
            for c in got["cards"]:
                self.assertTrue(c["id"].startswith(want) or c["type"] in ("lesson", "golden", "grave", "rule"), c)

    def test_lane_kinds_axes_reach_the_cards(self):
        # each lane's own vocabulary (P2-P7): animation's limbs and phases, VFX's roles and techniques, UI components
        axes = {"anim": {"limb", "phase", "timing", "motion", "weapon"}, "vfx": {"role", "beat", "technique"}, "ui": {"component", "screen", "route"}}
        for lane, allowed in axes.items():
            cards = lookup([lane], LANE_WORDS[lane])["cards"]
            seen = {a for c in cards for a in c["axes"]}
            self.assertTrue(seen & allowed, (lane, seen))

    def test_systems_asks_qa_for_tests_and_code_otherwise(self):
        self.assertEqual(partsrag.libraries("systems", "a combo system"), ("code",))
        self.assertEqual(partsrag.libraries("systems", "a mutation test for the guard"), ("code", "qa"))
        self.assertEqual(partsrag.libraries("systems", "a combo system", lane_hint="qa"), ("qa", "code"))
        got = lookup(["systems"], "write a mutation test spec for the remote guard")
        self.assertIn("qa", {c["library"] for c in got["cards"]})

    def test_every_routed_lane_answers_not_just_two(self):
        got = lookup(["vfx", "anim", "ui", "sfx", "systems"], V4_RAW)
        self.assertEqual({lib["lane"] for lib in got["libraries"]}, {"vfx", "anim", "ui", "sfx", "systems"})
        self.assertLessEqual(len(got["cards"]), partsrag.CARDS_TOTAL)
        self.assertEqual(got["cards"][0]["lane"], "vfx")  # the lead lane's cards first

    def test_another_lane_uses_its_own_clause(self):
        got = lookup(["vfx", "ui"], "a fire katana slash with water arcs, and the ui health bar clean and drawn")
        ui = [lib for lib in got["libraries"] if lib["lane"] == "ui"][0]
        self.assertIn("ui", ui["parts"][0].lower())
        self.assertNotIn("katana", ui["parts"][0].lower())


class Pieces(unittest.TestCase):
    @unittest.skipUnless(HAS_RIM_BRIEF, "needs the project's assets/models/car_wheel_rim.brief.md (not shipped with the kit)")
    def test_a_named_piece_breaks_into_its_briefs_parts(self):
        got = lookup(["3d"], "make the rim heavier, the spokes thinner", piece="car_wheel_rim")
        lib = got["libraries"][0]
        self.assertIn("brief", lib["from"])
        self.assertTrue(any("spoke" in p.lower() for p in lib["parts"]), lib)
        self.assertTrue(any("spoke" in c["part"].lower() for c in got["cards"]), [c["part"] for c in got["cards"]])
        # never the piece's own parts
        self.assertFalse([c for c in got["cards"] if (c.get("piece") or "").lower() == "car_wheel_rim"])

    def test_without_a_piece_the_prompts_clauses(self):
        got = lookup(["3d"], "a round alloy rim, five spokes from a centre hub")
        self.assertEqual(got["libraries"][0]["from"], "the prompt's clauses")
        self.assertEqual(len(got["libraries"][0]["parts"]), 2)

    def test_a_refused_word_looks_nothing_up(self):
        kinds = lookup(["vfx"], "a katana slash, no fire")["libraries"][0]["kinds"]
        self.assertNotIn("fire", kinds)


class Cards(unittest.TestCase):
    def _idx(self, lane="vfx"):
        return partsrag.library_index(lane)

    def test_look_hidden_unless_the_owner_allowed_it(self):
        idx = self._idx()
        d = {"id": "vfx/x/1", "type": "part", "piece": "old_slash", "title": "a ring", "kinds": {}, "mech": {"life": 0.4}, "look": {"texture": "rbxassetid://1"}}
        c = partsrag.card(idx, "vfx", "vfx", d, "ring", piece="new_slash")
        self.assertEqual(c["look"], "hidden (mechanics only)")
        self.assertNotIn("look_reuse", c)
        self.assertNotIn("rbxassetid", partsrag.line(c))
        self.assertIn("life=0.4", partsrag.line(c))
        saved = idx.allows
        idx.allows = [{"piece": "new_slash", "from": "old_slash", "by": "owner", "words": "yes reuse it"}]
        try:
            c = partsrag.card(idx, "vfx", "vfx", d, "ring", piece="new_slash")
            self.assertIn("rbxassetid://1", partsrag.line(c))
            self.assertEqual(checks.parts_grounding({"lanes": ["vfx"], "target_model": "claude", "orchestrator_prompt": "", "repo_grounding": {"parts": [dict(c, look="hidden (mechanics only)")]}})[0][:15], "parts look leak")
            idx.allows = [{"piece": "new_slash", "from": "old_slash", "by": "a session", "words": "sure"}]
            self.assertNotIn("look_reuse", partsrag.card(idx, "vfx", "vfx", d, "ring", piece="new_slash"))
        finally:
            idx.allows = saved

    def test_p8_upkeep_stale_recipe_and_duplicates(self):
        idx = self._idx()
        self.assertTrue(partsrag._stale(idx, {"type": "recipe", "src": "kit/no/such/file.py:3"}))
        self.assertTrue(partsrag._stale(idx, {"type": "recipe", "src": "kit/prompt/partsrag.py:999999"}))
        self.assertFalse(partsrag._stale(idx, {"type": "recipe", "src": "kit/prompt/partsrag.py:3"}))
        self.assertFalse(partsrag._stale(idx, {"type": "part", "src": "kit/no/such/file.py"}))
        got = lookup(["vfx", "anim", "ui"], V4_RAW)["cards"]
        ids = [c["id"] for c in got]
        self.assertEqual(len(ids), len(set(ids)))

    def test_avoid_cards_become_guardrails(self):
        routed = route.route_intent("a katana swing animation", "none")
        avoid = {"lane": "anim", "library": "anim", "id": "anim/rejected/x/1", "type": "candidate", "piece": "x", "title": "a swing the owner hated",
                 "part": "swing", "kinds": ["swing"], "axes": {}, "avoid": True, "evidence": "owner on its piece: 2/10", "mechanics": "", "know_how": False, "look": ""}
        routed["repo_grounding"]["parts"] = [avoid] + routed["repo_grounding"]["parts"]
        ir = expand.build_ir(routed)
        self.assertTrue(any("AVOID past part `anim/rejected/x/1`" in p["text"] for p in ir["failure_preventers"]))
        self.assertFalse(any("anim/rejected/x/1" in a["text"] for a in ir["api"]))

    def test_real_avoid_card_for_an_animation_ask(self):
        verdicts = os.path.join(ROOT, "kit", "knowledge", "vault", "anim", "verdicts")
        if not route.filed_graveyard(["anim"]) and not (os.path.isdir(verdicts) and os.listdir(verdicts)):
            self.skipTest("no owner verdict or graveyard record on an animation in this project: nothing is marked avoid")
        cards = lookup(["anim"], "a katana slash swing animation")["cards"]
        self.assertTrue(any(c["avoid"] for c in cards), [c["id"] for c in cards])

    def test_know_how_for_the_lead_part(self):
        cards = lookup(["3d"], "a round alloy rim, five spokes from a centre hub")["cards"]
        self.assertTrue(any(c["know_how"] and c["type"] in ("helper", "recipe") for c in cards), [c["id"] for c in cards])


class Cli(unittest.TestCase):
    def test_route_lists_parts_and_api_as_utf8_json(self):
        # (the runner decodes the last JSON line as UTF-8: a cp1252 console once turned "…" into byte 0x85 and
        # `kit prompt route` read as a crash)
        import json
        import subprocess

        env = dict(os.environ, KIT_GAME="none", PYTHONIOENCODING="cp1252")
        out = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "prompt", "cli.py"), "route", "make the rim's spokes thinner", "--piece", "car_wheel_rim", "--lane", "3d", "--game", "none"],
                             capture_output=True, env=env, cwd=ROOT, timeout=300)
        line = out.stdout.decode("utf-8").strip().splitlines()[-1]
        data = json.loads(line)
        self.assertEqual(data["status"], "pass")
        self.assertTrue(any(x.startswith("api [3d|template]") for x in data["lines"]), data["lines"])
        if HAS_RIM_BRIEF:  # (the piece's brief names its parts; without the brief the prompt's clauses do)
            self.assertTrue(any(x.startswith("parts library 3d") and "Spokes" in x for x in data["lines"]), data["lines"])
            self.assertTrue(any(x.startswith("parts [3d]") for x in data["lines"]))


class Gate(unittest.TestCase):
    def test_cards_reach_every_frontier_prompt(self):
        for raw in (V4_RAW, "a katana swing animation", "a gothic courtyard world with stairs"):
            r = route.route_intent(raw, "none")
            for m in ("claude", "codex", "gemini", "local"):
                p = comp.compile_packet(r, {}, m)
                self.assertEqual(checks.parts_grounding(p), [], (raw, m))

    def test_off_switch_fails_the_gate(self):
        os.environ["KIT_PROMPT_PARTS"] = "0"
        try:
            p = comp.compile_packet(route.route_intent("a katana swing animation", "none"), {}, "claude")
        finally:
            os.environ.pop("KIT_PROMPT_PARTS", None)
        problems = checks.parts_grounding(p)
        self.assertTrue(problems and problems[0].startswith("missing repo grounding: parts"), problems)

    def test_pruned_cards_fail_the_gate(self):
        p = comp.compile_packet(route.route_intent("a katana swing animation", "none"), {}, "claude")
        self.assertTrue(checks.parts_grounding(dict(p, orchestrator_prompt="nothing")))

    def test_excluded_cards_never_handed_over(self):
        saved = route._EXCLUDE
        route._EXCLUDE = (re.compile(r"swift|drill", re.I), ["sampleprivategame"])
        try:
            for c in lookup(["anim", "vfx", "ui"], "a spinning drill slash with a swift dash hud")["cards"]:
                self.assertFalse(route._excluded_doc(c), c)
        finally:
            route._EXCLUDE = saved


if __name__ == "__main__":
    unittest.main()
