"""PROMPT-X evolve over the OWNER's recorded verdicts (LIMITATIONS_FIXES_V4 9.2 row 6 / 9.4 stage 4): the loop reads
`kit verdict` notes (by: owner; a session's inferred reconstruction never counts), matches each to the prompt compiled
for that piece before the verdict's day, runs one TextGrad -> ACE -> GEPA step and consumes the verdict once. A
verdict typed on the command line must quote the record: an invented one moves nothing."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from prompt import cli, evolve, route  # noqa: E402
from prompt import compile as comp  # noqa: E402

RAW = "a katana swing animation, calm, one move"


def note(root, area, stem, **meta):
    words = meta.pop("words")
    d = os.path.join(root, area, "verdicts")
    os.makedirs(d, exist_ok=True)
    head = "\n".join(f"{k}: {v}" for k, v in meta.items())
    with open(os.path.join(d, f"{stem}.md"), "w", encoding="utf-8") as f:
        f.write(f"---\nkind: verdict\narea: {area}\n{head}\n---\n\n{words}\n")


class Loop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._env = {k: os.environ.get(k) for k in ("KIT_PROMPT_VAULT", "KIT_PROMPT_TRACES", "KIT_VERDICT_VAULT",
                                                    "PARALLAX_SESSION_FILE")}
        # (a compile through the CLI stamps the Parallax session token: this test's goes to its own folder, never the
        # checkout's .verify/parallax_session.json - it once replaced a live session's token mid-run)
        os.environ["PARALLAX_SESSION_FILE"] = os.path.join(self.tmp, "parallax_session.json")
        os.environ["KIT_PROMPT_VAULT"] = os.path.join(self.tmp, "vault")
        os.environ["KIT_PROMPT_TRACES"] = os.path.join(self.tmp, "traces.json")
        self.vroot = os.path.join(self.tmp, "verdicts")
        os.environ["KIT_VERDICT_VAULT"] = self.vroot
        note(self.vroot, "anim", "katana_slash--2026-11-21", name="katana_slash", score=4, date="2026-11-21", by="owner",
             source="owner", words="it still feels floaty")
        # not the owner's record: a session's reconstruction, and a model's own score
        note(self.vroot, "anim", "katana_slash--2026-11-22", name="katana_slash", score=2, date="2026-11-22", by="owner",
             source="inferred", words="floaty and stiff")
        note(self.vroot, "anim", "katana_slash--2026-11-23", name="katana_slash", score=1, date="2026-11-23",
             by='"claude-opus@claude-code"', source="owner", words="floaty")
        # the owner's, but no prompt was compiled for this piece
        note(self.vroot, "anim", "roundhouse--2026-11-21", name="roundhouse", score=3, date="2026-11-21", by="owner",
             source="owner", words="too slow")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def compiled(self, day="2026-11-20", piece="katana_slash"):
        p = comp.compile_packet(route.route_intent(RAW, "none"), {}, "claude")
        p["piece"], p["compiled"] = piece, day
        return evolve.save_packet(p), p

    def test_only_the_owners_own_record_is_read(self):
        vs = evolve.owner_verdicts()
        self.assertEqual([v["id"] for v in vs], ["anim/verdicts/katana_slash--2026-11-21", "anim/verdicts/roundhouse--2026-11-21"])
        self.assertEqual(vs[0]["score"], 4.0)
        self.assertEqual(vs[0]["words"], "it still feels floaty")

    def test_the_loop_learns_once_from_a_matched_verdict(self):
        self.compiled()
        r = evolve.evolve_from_verdicts()
        self.assertEqual(r["matched"], 1)
        self.assertEqual(r["unmatched"], ["anim/verdicts/roundhouse--2026-11-21"])
        self.assertEqual(r["results"][0]["status"], "accepted", r["results"][0].get("reason"))
        self.assertIn("floaty", r["results"][0]["blamed"])
        self.assertTrue(any("snap hold" in x["text"] for x in evolve.learned_rules(["anim"], "claude")))
        again = evolve.evolve_from_verdicts()
        self.assertEqual(again["matched"], 0)  # (consumed: one verdict, one step)

    def test_a_prompt_compiled_after_the_verdict_is_not_what_was_judged(self):
        self.compiled(day="2026-11-25")
        r = evolve.evolve_from_verdicts()
        self.assertEqual(r["matched"], 0)
        self.assertIn("anim/verdicts/katana_slash--2026-11-21", r["unmatched"])

    def test_a_dry_run_changes_nothing(self):
        self.compiled()
        r = evolve.evolve_from_verdicts(apply=False)
        self.assertEqual(r["matched"], 1)
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, "vault", "consumed.json")))
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, "vault", "pareto_frontier.json")))

    def run_cli(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(argv)
        return code, json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_the_cli_refuses_a_verdict_the_record_does_not_hold(self):
        sha, _ = self.compiled()
        code, out = self.run_cli(["evolve", sha, "4", "the timing is off", "--dry"])
        self.assertEqual(code, 1)
        self.assertIn("no recorded owner verdict", out["summary"])
        code, out = self.run_cli(["evolve", sha, "2", "floaty and stiff", "--dry"])  # (the inferred note: refused too)
        self.assertEqual(code, 1)
        code, out = self.run_cli(["evolve", sha, "4", "still feels floaty", "--dry"])
        self.assertEqual(code, 0, out)

    def test_the_cli_loop_and_the_piece_flag(self):
        code, out = self.run_cli(["compile", RAW, "--piece", "katana_slash", "--out", os.path.join(self.tmp, "last.json")])
        self.assertEqual(code, 0, out)
        with open(os.path.join(evolve.packets_dir(), f"{out['packet_sha']}.json"), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["piece"], "katana_slash")
        self.assertIn("compiled", saved)
        code, out = self.run_cli(["evolve", "--verdicts", "--dry"])
        self.assertEqual(code, 0)
        # (compiled today, so the 2026-11-21 verdict is matched only if today is on or before it)
        self.assertIn(out["loop"]["matched"], (0, 1))


if __name__ == "__main__":
    unittest.main()
