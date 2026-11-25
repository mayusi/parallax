"""kit/prompt/docs.py - PROMPT-X's Roblox API grounding (LIMITATIONS_FIXES_V4 9.2 row 1: "docs.py API signatures
scoped to (lane, family, game)"): exact Luau signatures from the kit's type file, the owner's words looked up inside
the lane's scope only, the family and game scopes, and the gate that refuses a member with no signature.
Run: python kit/test/python/run.py -k test_prompt_docs"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit"))
os.environ["KIT_GAME"] = "none"
from prompt import checks, docs, models, route  # noqa: E402
from prompt import compile as comp  # noqa: E402

V4_RAW = "yo make a fire katana slash ultimate like tanjiro water and fire, make it feel heavy not floaty and make the ui clean not slop"


def need_reference(test):
    if docs.index() is None:
        test.skipTest("no Roblox Studio API reference on this machine")


def extras(result):
    return [r for r in result["api"] if r["scope"] != "template"]


class Signatures(unittest.TestCase):
    def setUp(self):
        need_reference(self)

    def test_method_signature_in_call_form(self):
        rows, problems = docs.verify(["Workspace.GetServerTimeNow", "Animator.LoadAnimation"])
        self.assertEqual(problems, [])
        self.assertEqual(rows[0]["signature"], "Workspace:GetServerTimeNow(): number")
        self.assertEqual(rows[1]["signature"], "Animator:LoadAnimation(animation: Animation): AnimationTrack")

    def test_property_and_inherited_member(self):
        rows, _p = docs.verify(["ParticleEmitter.Rate", "Workspace.Raycast"])
        self.assertEqual(rows[0]["signature"], "ParticleEmitter.Rate: number")
        # Raycast is declared on WorldRoot: Workspace inherits it, the signature says Workspace
        self.assertTrue(rows[1]["signature"].startswith("Workspace:Raycast(origin: Vector3"), rows[1]["signature"])

    def test_unknown_and_deprecated_names_are_problems(self):
        _rows, problems = docs.verify(["Workspace.NoSuchThing", "Lighting.Technology"])
        self.assertEqual(len(problems), 2)

    def test_every_template_member_has_a_signature(self):
        # (SurfaceAppearance.ColorMap was named by the 3D template: documented, but the kit's type file does not
        # declare it - a script typed against it fails the types gate; the template now names ColorMapContent)
        for lane in models.LANES:
            rows, problems = docs.verify(models.template(lane)["api"], lane)
            self.assertEqual(problems, [], lane)
            for r in rows:
                if r["kind"] == "member":
                    self.assertTrue(r["signature"], (lane, r["name"]))


class Scope(unittest.TestCase):
    def setUp(self):
        need_reference(self)

    def test_every_scope_class_exists(self):
        for lane, classes in docs.LANE_SCOPE.items():
            self.assertIn(lane, models.LANES)
            for cls in classes:
                self.assertIn(cls, docs.index(), (lane, cls))

    def test_the_prompts_words_inside_the_lanes_scope(self):
        raw = "particles that emit faster with more light emission"
        vfx = [r["name"] for r in extras(docs.scoped(["vfx"], raw))]
        self.assertIn("ParticleEmitter.LightEmission", vfx)
        systems = [r["name"] for r in extras(docs.scoped(["systems"], raw))]
        self.assertFalse([n for n in systems if n.startswith(("ParticleEmitter", "Beam"))], systems)

    def test_a_plain_word_alone_names_no_api(self):
        # "fire" is a flame here, never RemoteEvent:FireClient; "player" alone is no GuiService call
        for lane in ("systems", "ui"):
            names = [r["name"] for r in extras(docs.scoped([lane], "a fire katana for the player"))]
            self.assertEqual(names, [], lane)

    def test_a_refused_word_pulls_no_api(self):
        g = route.grounding(["vfx"], "a katana slash trail, no light emission", None)
        self.assertFalse([n for n in g["api_docs"] if n.endswith("LightEmission")], g["api_docs"])
        g = route.grounding(["vfx"], "a katana slash trail with light emission", None)
        # (the trail's own LightEmission first: both of its words were said)
        self.assertIn("Trail.LightEmission", g["api_docs"])

    def test_family_scope(self):
        got = docs.scoped(["vfx"], "a slash", families=["vfx:light emission"])
        fam = [r for r in got["api"] if r["scope"].startswith("family")]
        self.assertTrue(fam and fam[0]["name"].endswith("LightEmission"), got["api"])

    def test_game_scope_reads_the_kit_runtime_and_never_sample_game(self):
        self.assertIn("Players", docs.game_services(None))
        self.assertEqual(docs.game_services("SampleGame"), set())
        rows = docs.scoped(["systems"], "save their data on player removing")["api"]
        lifted = [r["name"] for r in rows if r["scope"].endswith("+game")]
        self.assertIn("Players.PlayerRemoving", lifted, rows)

    def test_lead_lane_gets_more_names_and_a_cap_holds(self):
        raw = "light emission particles, a list layout flex item, reverb decay, remote event fire client, terrain water waves"
        got = extras(docs.scoped(["vfx", "ui", "sfx", "systems", "world"], raw))
        self.assertLessEqual(len(got), docs.K_TOTAL)
        self.assertEqual(sum(1 for r in got if r["lane"] == "vfx"), docs.K_LEAD)


class InThePacket(unittest.TestCase):
    def test_signatures_reach_every_frontier_prompt(self):
        need_reference(self)
        r = route.route_intent(V4_RAW, "none")
        for m in ("claude", "codex", "gemini", "local"):
            p = comp.compile_packet(r, {}, m)
            self.assertEqual(checks.api_signatures(p), [], m)
        p = comp.compile_packet(r, {}, "codex")
        # (the lead lane's first exact signature survives the five-lane budget)
        self.assertIn("ParticleEmitter.Rate: number", p["orchestrator_prompt"])
        p = comp.compile_packet(route.route_intent("a katana swing animation", "none"), {}, "codex")
        self.assertIn("Animator:LoadAnimation(animation: Animation): AnimationTrack", p["orchestrator_prompt"])
        self.assertIn("api_scope", p["repo_grounding"])

    def test_the_gate_refuses_a_member_with_no_signature(self):
        need_reference(self)
        p = comp.compile_packet(route.route_intent("a katana swing animation", "none"), {}, "claude")
        bad = dict(p, repo_grounding=dict(p["repo_grounding"], api_detail=[dict(a, signature=None) for a in p["repo_grounding"]["api_detail"]]))
        self.assertTrue(any("API signature missing" in x for x in checks.api_signatures(bad)))
        stripped = dict(p, orchestrator_prompt="nothing")
        self.assertTrue(checks.api_signatures(stripped))

    def test_no_reference_keeps_names_unverified(self):
        old = os.environ.get("KIT_PROMPT_DOCS")
        os.environ["KIT_PROMPT_DOCS"] = "0"
        docs.reset()
        try:
            got = docs.scoped(["vfx"], "light emission particles")
            self.assertTrue(got["api"])
            self.assertTrue(all(r["verified"] is False and r["scope"] == "template" for r in got["api"]))
            self.assertIn("none on this machine", got["scope"]["reference"])
        finally:
            if old is None:
                os.environ.pop("KIT_PROMPT_DOCS", None)
            else:
                os.environ["KIT_PROMPT_DOCS"] = old
            docs.reset()


if __name__ == "__main__":
    unittest.main()
