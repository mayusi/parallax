"""kit/anim/pick_warnings.py — each candidate's kit warnings are shown on the pick sheet, under its own card.
Run: python kit/test/python/run.py -k pick_warnings"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
TOOL = os.path.join(ROOT, "kit", "anim", "pick_warnings.py")

PAGE = """<!doctype html><html><head><title>X picks</title></head><body><main>
<h1>X — round 0: pick 1–2</h1>
<div class="grid">
<figure class="card" data-id="X/r0/c0" data-n="1"><img src="c0.gif"><figcaption><b>X/r0/c0</b></figcaption></figure>
<figure class="card" data-id="X/r0/c2" data-n="2"><img src="c2.gif"><figcaption><b>X/r0/c2</b></figcaption></figure>
</div></main></body></html>"""


class PickWarningsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, "assets", "animations", "candidates", "X"))
        os.makedirs(os.path.join(self.tmp.name, "build", "candidates", "X", "round_0"))
        manifest = {
            "candidates": [
                {"id": "X/r0/c0", "warnings": ["Left Arm rot_range 22.9 < loved p10 30.73"]},
                {"id": "X/r0/c2", "warnings": []},
            ]
        }
        with open(os.path.join(self.tmp.name, "assets", "animations", "candidates", "X", "round_0.json"), "w") as f:
            json.dump(manifest, f)
        self.page = os.path.join(self.tmp.name, "build", "candidates", "X", "round_0", "picks.html")
        with open(self.page, "w", encoding="utf-8") as f:
            f.write(PAGE)

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args):
        p = subprocess.run(
            [sys.executable, TOOL, *args], cwd=self.tmp.name, capture_output=True, text=True, check=False
        )
        return p.returncode, json.loads(p.stdout.strip().splitlines()[-1])

    def test_the_warning_sits_under_its_own_card_and_a_line_on_top(self):
        code, out = self.run_tool("X")
        self.assertEqual(code, 0, out)
        self.assertEqual((out["cards"], out["warned"]), (2, 1))
        doc = open(self.page, encoding="utf-8").read()
        c0 = doc.index('data-id="X/r0/c0"')
        c2 = doc.index('data-id="X/r0/c2"')
        warn = doc.index("Left Arm rot_range 22.9 &lt; loved p10 30.73")
        self.assertTrue(c0 < warn < c2, "the warning belongs to c0's card")
        self.assertIn("1 of 2 candidates on this sheet carry kit warnings", doc)

    def test_a_candidate_dropped_from_the_sheet_is_not_counted(self):
        path = os.path.join(self.tmp.name, "assets", "animations", "candidates", "X", "round_0.json")
        with open(path, encoding="utf-8") as f:
            man = json.load(f)
        man["candidates"].append({"id": "X/r0/c9", "warnings": ["Right Arm rot_range 10 < loved p10 30"]})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(man, f)
        code, out = self.run_tool("X")
        self.assertEqual(code, 0, out)
        self.assertEqual((out["cards"], out["warned"]), (2, 1))  # c9 is in the manifest, not on the sheet
        self.assertIn("1 of 2 candidates on this sheet", open(self.page, encoding="utf-8").read())

    def test_running_again_replaces_its_own_blocks(self):
        self.run_tool("X")
        self.run_tool("X", "--round", "0")
        doc = open(self.page, encoding="utf-8").read()
        self.assertEqual(doc.count('class="kitwarn"'), 1)
        self.assertEqual(doc.count("kitwarn-top"), 1)
        self.assertEqual(doc.count("<!-- kit warnings -->"), 1)

    def write_checks(self, checks):
        d = os.path.join(self.tmp.name, "kit", "knowledge", "vault", "anim")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "checks.json"), "w", encoding="utf-8") as f:
            json.dump({"lane": "anim", "checks": checks}, f)

    def test_the_rounds_checks_sit_at_the_top_of_the_sheet(self):
        self.write_checks([{"id": "anim-limb-range", "words": ["stilts"], "target": "round",
                            "measure": "warned_share", "fails_when": "above", "threshold": 0.5,
                            "status": "proposed"}])
        code, out = self.run_tool("X")
        self.assertEqual(code, 0, out)
        self.assertEqual(out["checks_failed"], ["anim-limb-range"])  # 1 of 2 cards warned: 0.5
        doc = open(self.page, encoding="utf-8").read()
        self.assertIn('class="kitchecks"', doc)
        self.assertIn("anim-limb-range [proposed]: FAIL", doc)

    def test_a_check_that_breaks_never_loses_the_sheet_or_its_warnings(self):
        # a broken measure is "not measurable" and the others still run
        self.write_checks([{"id": "bad", "words": ["x"], "target": "round", "measure": "no_such_measure",
                            "threshold": 1, "status": "proposed"}])
        code, out = self.run_tool("X")
        self.assertEqual(code, 0, out)
        self.assertIn("bad [proposed]: not measurable (KeyError", open(self.page, encoding="utf-8").read())
        # the checks process dying (a corrupt checks.json here; a GPU crash in life): the sheet and its warnings stay
        d = os.path.join(self.tmp.name, "kit", "knowledge", "vault", "anim", "checks.json")
        with open(d, "w", encoding="utf-8") as f:
            f.write("{ not json")
        code, out = self.run_tool("X")
        self.assertEqual(code, 0, out)
        doc = open(self.page, encoding="utf-8").read()
        self.assertIn("not run", doc)
        self.assertIn("Left Arm rot_range 22.9 &lt; loved p10 30.73", doc)  # the warnings stayed

    def test_no_page_yet_is_an_error_not_a_silent_pass(self):
        os.remove(self.page)
        code, out = self.run_tool("X")
        self.assertEqual(code, 1)
        self.assertIn("run kit anim picks first", out["error"])


if __name__ == "__main__":
    unittest.main()
