"""PROMPT-X evolve against LIMITATIONS_FIXES_V4 9.2 row 6 / 9.4 stage 4 / 13.7 trap 5 - the gaps the first build left:
  - the held-out benchmark is judged per CASE: a delta that fixes one case by breaking another is rejected, whatever the
    average says ("commits ONLY non-regressing deltas");
  - GEPA's frontier is instance-wise: a candidate that alone passes some held-out case stays on it;
  - the textual gradient says WHERE it points (9.4: "templates/vfx.json + profiles/<model>.json"): a rule the compile
    never had blames the lane template, a rule it had and pruned for the model's budget blames the profile;
  - a failed gate that states its measured bound ("arrival 2f > 1f", 9.4's vfx dailies) blames that bound.
Evolve writes only into a temporary vault. Run: python kit/test/python/run.py -k test_prompt_evolve_loop"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.environ["KIT_GAME"] = "none"
from prompt import evolve, models, route  # noqa: E402
from prompt import compile as comp  # noqa: E402

RAW = "a katana swing animation, calm, one move"
RULE = "the blade arrives on the hit frame with a three frame snap hold and planted feet"


def ev(passed, acc=None, n=20, tokens=900):
    return {"accuracy": acc if acc is not None else round(len(passed) / n, 3), "tokens": tokens, "failed": [], "passed": list(passed), "n": n}


class TempVault(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env = {k: os.environ.get(k) for k in ("KIT_PROMPT_VAULT", "KIT_PROMPT_TRACES")}
        os.environ["KIT_PROMPT_VAULT"] = os.path.join(self.tmp, "vault")
        os.environ["KIT_PROMPT_TRACES"] = os.path.join(self.tmp, "traces.json")
        self._evaluate = evolve.evaluate

    def tearDown(self):
        evolve.evaluate = self._evaluate
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def packet(self, model="claude"):
        return comp.compile_packet(route.route_intent(RAW, "none"), {}, model)

    def fake_evals(self, base, cand):
        """the held-out evaluation, base first then the candidate (reflect_and_propose evaluates in that order)"""
        calls = []

        def fake(cases=None, model=None):
            calls.append(model)
            return base if len(calls) == 1 else cand

        evolve.evaluate = fake
        return calls


class NonRegression(TempVault):
    def test_regressions_lists_the_cases_lost(self):
        self.assertEqual(evolve.regressions(ev(["a", "b", "c"]), ev(["a", "c", "d"])), ["b"])
        self.assertEqual(evolve.regressions(ev(["a"]), ev(["a", "b"])), [])

    def test_a_delta_that_trades_one_case_for_another_is_rejected(self):
        ids = [f"c{i}" for i in range(19)]
        self.fake_evals(ev(ids + ["x"]), ev(ids + ["y"]))  # 95% -> 95%: the average hides the lost case
        r = evolve.reflect_and_propose(self.packet(), {"score": 3, "words": "bad"}, proposed_rules=[RULE])
        self.assertEqual(r["status"], "rejected", r.get("reason"))
        self.assertIn("held-out regression", r["reason"])
        self.assertIn("x", r["reason"])
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, "vault", "changelog.json")))

    def test_a_delta_that_only_adds_cases_is_accepted_with_its_targets(self):
        ids = [f"c{i}" for i in range(19)]
        self.fake_evals(ev(ids), ev(ids + ["y"]))
        r = evolve.reflect_and_propose(self.packet(), {"score": 3, "words": "it still feels floaty"})
        self.assertEqual(r["status"], "accepted", r.get("reason"))
        log = models.load_json(os.path.join(self.tmp, "vault", "changelog.json"))["entries"][-1]
        self.assertEqual(log["targets"], ["template:anim"])
        head = evolve.frontier()["frontiers"]["anim|claude"][0]
        self.assertIn("y", head["passed"])

    def test_the_real_benchmark_reports_its_passed_cases(self):
        r = evolve.evaluate(evolve.benchmark_cases()[:2])
        self.assertEqual(len(r["passed"]) + len(r["failed"]), 2)
        self.assertTrue(all(isinstance(i, str) for i in r["passed"]))


class InstanceFrontier(unittest.TestCase):
    def test_a_candidate_that_alone_passes_a_case_stays(self):
        # (on the average b beats a; per instance a alone passes p1, so a stays)
        a = {"id": "a", "rules": [], "accuracy": 0.33, "tokens": 100, "passed": ["p1"]}
        b = {"id": "b", "rules": [], "accuracy": 0.67, "tokens": 100, "passed": ["p2", "p3"]}
        self.assertEqual({c["id"] for c in evolve._pareto([a, b])}, {"a", "b"})
        both = {"id": "ab", "rules": [], "accuracy": 1.0, "tokens": 100, "passed": ["p1", "p2", "p3"]}
        self.assertEqual([c["id"] for c in evolve._pareto([a, b, both])], ["ab"])

    def test_an_old_entry_without_cases_compares_by_its_average(self):
        old = {"id": "old", "rules": [], "accuracy": 0.9, "tokens": 100}
        new = {"id": "new", "rules": [], "accuracy": 1.0, "tokens": 100, "passed": ["p1"]}
        self.assertEqual([c["id"] for c in evolve._pareto([old, new])], ["new"])


class GradientTargets(unittest.TestCase):
    def _packet(self, model, pruned_rule=None):
        p = comp.compile_packet(route.route_intent(RAW, "none"), {}, model)
        rule = models.template("anim")["failure_lexicon"]["floaty"]
        self.assertNotIn(rule.lower()[:60], p["orchestrator_prompt"].lower())
        if pruned_rule:
            p = dict(p, pruned=list(p["pruned"]) + [{"section": "guardrails", "priority": 2, "text": rule[:120]}])
        return p

    def test_a_rule_never_compiled_blames_the_template(self):
        g = evolve.textual_gradient(self._packet("claude"), {"score": 3, "words": "still floaty"})
        self.assertEqual([(b["word"], b["target"]) for b in g["blame"]], [("floaty", "template:anim")])

    def test_a_rule_pruned_for_the_budget_blames_the_profile(self):
        g = evolve.textual_gradient(self._packet("local", pruned_rule=True), {"score": 3, "words": "still floaty"})
        self.assertEqual([(b["word"], b["target"]) for b in g["blame"]], [("floaty", "profile:local")])

    def test_a_failed_gate_with_a_bound_is_blamed(self):
        p = self._packet("claude")
        verify = {"steps": [{"ok": False, "summary": "vfx dailies katana_slash: the key beat arrives 2f > 1f after the hit"}, {"ok": True, "summary": "lint 0 > 1 fine"}]}
        g = evolve.textual_gradient(p, {"score": 4, "words": "meh"}, verify)
        gates = [b for b in g["blame"] if b["word"] == "gate"]
        self.assertEqual(len(gates), 1, g["blame"])
        self.assertIn("2f > 1f", gates[0]["missing"])
        self.assertEqual(gates[0]["lane"], "anim")
        self.assertIsNone(evolve.lint_rule(gates[0]["missing"]))
        # praise blames nothing, a bound included
        self.assertEqual(evolve.textual_gradient(p, {"score": 8, "words": "great"}, verify)["blame"], [])


if __name__ == "__main__":
    unittest.main()
