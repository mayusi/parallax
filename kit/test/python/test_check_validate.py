"""kit/anim/check_validate.py — the gates' warnings are checked against the owner's rejections and picks; a measure is
proven only when it caught rejections and spared every measured pick. Run: python kit/test/python/run.py -k check_validate"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
TOOL = os.path.join(ROOT, "kit", "anim", "check_validate.py")

STILTS = "kick_leg slide_p95 0.58 < loved p10 0.78"
ARM = "Left Arm rot_range 22.9 < loved p10 30.73"


def cand(move, rnd, n, warnings):
    return {"id": f"{move}/r{rnd}/c{n}", "warnings": warnings}


class CheckValidateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "kit", "knowledge", "vault", "anim", "verdicts"))

    def tearDown(self):
        self.tmp.cleanup()

    def round(self, move, rnd, cands, parents=None):
        d = os.path.join(self.root, "assets", "animations", "candidates", move)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"round_{rnd}.json"), "w", encoding="utf-8") as f:
            json.dump({"round": rnd, "parents": parents or [], "candidates": cands}, f)

    def verdict(self, file, name, score, body, source="owner"):
        p = os.path.join(self.root, "kit", "knowledge", "vault", "anim", "verdicts", file)
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"---\nkind: verdict\narea: anim\nname: {name}\nscore: {score}\ndate: 2026-11-04\nsource: {source}\n---\n\n{body}\n")

    def run_tool(self):
        p = subprocess.run([sys.executable, TOOL, "--root", self.root], capture_output=True, text=True, check=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        with open(os.path.join(self.root, ".verify", "checks-anim.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_a_rejected_round_counts_its_warnings_but_nothing_is_proven_without_picks(self):
        self.round("Spin", 0, [cand("Spin", 0, i, [STILTS, ARM]) for i in range(4)])
        self.verdict("spin.md", "Spin", 2, "bad: All bad - round 0, every one of the 4: stilts, arm-only swing")
        res = self.run_tool()
        self.assertEqual(res["rejected_rounds"], 1)
        self.assertEqual(res["measures"]["kick_leg slide_p95"]["rejected_with"], 4)
        self.assertEqual(res["proven"], [])
        self.assertIn("not proven", res["why"])

    def test_proven_only_when_measured_picks_spare_the_measure(self):
        # round 0: four rejected, all with the stilts warning; three picks (bred round 1) carry only the arm warning
        r0 = [cand("Cut", 0, i, [STILTS]) for i in range(4)] + [cand("Cut", 0, i, [ARM]) for i in (4, 5, 6)]
        self.round("Cut", 0, r0)
        self.round("Cut", 1, [cand("Cut", 1, 0, [])], parents=["Cut/r0/c4", "Cut/r0/c5", "Cut/r0/c6"])
        self.verdict("cut.md", "Cut", 2, "bad: round 0 - c0 c1 c2 c3 read as stilts")
        res = self.run_tool()
        self.assertEqual(res["picked_measured"], 3)
        self.assertEqual(res["proven"], ["kick_leg slide_p95"])  # caught 4, spared every pick
        self.assertNotIn("Left Arm rot_range", res["proven"])  # every pick carried it

    def test_the_owners_redo_rejects_a_round_like_a_low_number(self):
        self.round("Spin", 0, [cand("Spin", 0, i, [STILTS]) for i in range(3)])
        p = os.path.join(self.root, "kit", "knowledge", "vault", "anim", "verdicts", "spin.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("---\nkind: verdict\narea: anim\nname: Spin\ndirection: redo\ndate: 2026-11-08\nsource: owner\n---\n\n"
                    "Redo - round 0, all of them: stilts\n")
        res = self.run_tool()
        self.assertEqual(res["rejected_rounds"], 1)
        self.assertEqual(res["rejected_candidates"], 3)
        self.assertEqual((res["shown_candidates"], res["shown_warned"]), (3, 3))
        self.assertTrue(res["rounds"][0]["owner"].startswith("rejected 3 (Redo"))

    def test_a_dry_run_writes_nothing(self):
        self.round("Spin", 0, [cand("Spin", 0, i, [STILTS]) for i in range(2)])
        p = subprocess.run([sys.executable, TOOL, "--root", self.root, "--dry"], capture_output=True, text=True,
                           check=False)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".verify", "checks-anim.json")))

    def test_a_note_named_after_a_round_rejects_that_round(self):
        self.round("Kick", 1, [cand("Kick", 1, i, [STILTS]) for i in range(3)])
        self.verdict("kick-r1.md", '"Kick/r1"', 3, "the left leg dosent just stay there it looks horrible")
        res = self.run_tool()
        self.assertEqual(res["rejected_rounds"], 1)
        self.assertEqual(res["rejected_candidates"], 3)

    def test_a_guessed_number_is_never_the_owner_rejecting(self):
        self.round("Spin", 0, [cand("Spin", 0, i, [STILTS]) for i in range(4)])
        self.verdict("spin.md", "Spin", 2, "All bad - round 0, every one", source="inferred")
        res = self.run_tool()
        self.assertEqual(res["rejected_rounds"], 0)
        self.assertEqual(res["measures"]["kick_leg slide_p95"]["rejected_with"], 0)


if __name__ == "__main__":
    unittest.main()
