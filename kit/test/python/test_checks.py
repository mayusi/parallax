"""kit/checks/checks.py — the owner's recurring words as checks on the work; their status comes from the owner's verdicts
only (proposed reports, validated may gate, retired stops). Run: python kit/test/python/run.py -k test_checks"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "checks"))
import checks as K  # noqa: E402

TOOL = os.path.join(ROOT, "kit", "checks", "checks.py")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def cand(move, rnd, n, sliders, warnings=None):
    c = {"id": f"{move}/r{rnd}/c{n}", "sliders": sliders}
    if warnings is not None:
        c["warnings"] = warnings
    return c


class ChecksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for lane in ("anim", "vfx"):
            os.makedirs(os.path.join(self.root, "kit", "knowledge", "vault", lane, "verdicts"))

    def tearDown(self):
        self.tmp.cleanup()

    def round(self, move, rnd, cands, parents=None):
        d = os.path.join(self.root, "assets", "animations", "candidates", move)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"round_{rnd}.json"), "w", encoding="utf-8") as f:
            json.dump({"round": rnd, "parents": parents or [], "candidates": cands}, f)

    def verdict(self, lane, file, name, body, score=None, source="owner", direction=None):
        extra = (f"score: {score}\n" if score is not None else "") + (f"direction: {direction}\n" if direction else "")
        p = os.path.join(self.root, "kit", "knowledge", "vault", lane, "verdicts", file)
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"---\nkind: verdict\narea: {lane}\nname: {name}\n{extra}date: 2026-11-04\nsource: {source}\n---\n\n"
                    f"{body}\n")

    def checks(self, lane, items):
        p = os.path.join(self.root, "kit", "knowledge", "vault", lane, "checks.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"lane": lane, "checks": items}, f)
        return p

    def cli(self, *args):
        p = subprocess.run([sys.executable, TOOL, *args, "--root", self.root], capture_output=True, text=True,
                           check=False)
        return p.returncode, json.loads(p.stdout.strip().splitlines()[-1])

    # ------------------------------------------------------------------ measures
    def test_slider_spread_compares_numbers_and_counts_a_different_habit_as_one(self):
        self.round("M", 0, [cand("M", 0, 0, {"time": 0.0, "arms": "a"}), cand("M", 0, 1, {"time": 1.0, "arms": "b"})])
        # time differs by 1 on a -1..1 range (0.5), the habit differs (1): sqrt((0.25 + 1) / 2)
        self.assertEqual(K.slider_spread(self.root, "M/round_0"), round(((0.25 + 1) / 2) ** 0.5, 4))
        self.round("M", 1, [cand("M", 1, 0, {"time": 0.5, "arms": "a"}), cand("M", 1, 1, {"time": 0.5, "arms": "a"})])
        self.assertEqual(K.slider_spread(self.root, "M/round_1"), 0.0)
        self.assertIsNone(K.slider_spread(self.root, "M/round_9"))

    def test_a_slider_that_never_changes_or_that_some_candidates_lack_is_left_out(self):
        # the 2026-11-08 review: a constant "arms" slider diluted some rounds against others without it
        self.round("A", 0, [cand("A", 0, 0, {"time": -1.0, "arms": "technique"}),
                            cand("A", 0, 1, {"time": 1.0, "arms": "technique"})])
        self.round("B", 0, [cand("B", 0, 0, {"time": -1.0}), cand("B", 0, 1, {"time": 1.0, "extra": 0.3})])
        self.assertEqual(K.slider_spread(self.root, "A/round_0"), 1.0)
        self.assertEqual(K.slider_spread(self.root, "B/round_0"), 1.0)

    def test_warned_share_never_calls_a_round_made_before_warnings_clean(self):
        self.round("M", 0, [cand("M", 0, i, {}, ["x < loved p10 1"] if i < 3 else []) for i in range(4)])
        self.assertEqual(K.warned_share(self.root, "M/round_0"), 0.75)
        self.round("M", 1, [cand("M", 1, i, {}) for i in range(4)])  # no warnings key at all
        self.assertIsNone(K.warned_share(self.root, "M/round_1"))

    def test_look_spread_is_not_measurable_without_the_rounds_gifs(self):
        self.round("M", 0, [cand("M", 0, i, {}) for i in range(3)])
        self.assertIsNone(K.look_spread(self.root, "M/round_0"))

    def test_motion_energy_tells_a_moving_effect_from_a_still_one(self):
        import cv2
        import numpy as np

        def video(name, moving):
            d = os.path.join(self.root, "library", "vfx", "effects", name, "previews")
            os.makedirs(d, exist_ok=True)
            w = cv2.VideoWriter(os.path.join(d, "hero.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 30, (160, 90))
            if not w.isOpened():
                self.skipTest("this opencv cannot write mp4")
            for i in range(30):
                frame = np.zeros((90, 160, 3), np.uint8)
                x = (i * 5) % 140 if moving else 10
                frame[30:60, x:x + 20] = 255
                w.write(frame)
            w.release()

        video("moving", True)
        video("still", False)
        moving, still = K.motion_energy(self.root, "moving"), K.motion_energy(self.root, "still")
        self.assertIsNotNone(moving)
        self.assertGreater(moving, 0.01)
        self.assertLess(still, 0.002)
        self.assertIsNone(K.motion_energy(self.root, "no_such_effect"))

    # ------------------------------------------------------------------ run
    def test_run_reports_fail_pass_report_and_not_measurable_and_skips_retired(self):
        self.round("M", 0, [cand("M", 0, i, {"time": 0.1 * i}, ["w"]) for i in range(3)])
        self.checks("anim", [
            {"id": "a", "words": ["cousins"], "target": "round", "measure": "slider_spread", "fails_when": "below",
             "threshold": 0.9, "status": "proposed"},
            {"id": "b", "words": ["stilts"], "target": "round", "measure": "warned_share", "fails_when": "above",
             "threshold": 2.0, "status": "proposed"},
            {"id": "c", "words": ["x"], "target": "round", "measure": "slider_spread", "threshold": None,
             "status": "proposed"},
            {"id": "d", "words": ["x"], "target": "round", "measure": "look_spread", "threshold": 0.1,
             "status": "proposed"},
            {"id": "e", "words": ["x"], "target": "round", "measure": "slider_spread", "threshold": 9,
             "status": "retired"},
        ])
        code, out = self.cli("run", "anim", "M/round_0")
        self.assertEqual(code, 0, out)
        text = "\n".join(out["lines"])
        self.assertIn("a [proposed]: FAIL", text)
        self.assertIn("b [proposed]: pass", text)
        self.assertIn("c [proposed]: reports", text)
        self.assertIn("d [proposed]: not measurable", text)
        self.assertNotIn("  e ", text)
        self.assertEqual(out["failed"], ["a"])

    # ------------------------------------------------------------------ validate
    def cousins_check(self, threshold=0.3, status="proposed"):
        return {"id": "anim-cousins", "words": ["cousins"], "target": "round", "measure": "slider_spread",
                "fails_when": "below", "threshold": threshold, "status": status}

    def tight(self, move, rnd, parents=None):
        self.round(move, rnd, [cand(move, rnd, i, {"time": 0.05 * i}) for i in range(4)], parents)

    def wide(self, move, rnd, parents=None):
        self.round(move, rnd, [cand(move, rnd, i, {"time": [-1.0, 1.0][i % 2]}) for i in range(4)], parents)

    def test_two_caught_and_one_spared_stays_proposed_and_says_what_it_needs(self):
        self.tight("A", 0)
        self.tight("B", 0)
        self.wide("C", 0)
        self.round("C", 1, [cand("C", 1, 0, {})], parents=["C/r0/c1"])  # the owner picked from C round 0
        self.verdict("anim", "a.md", "A", "All bad - round 0: cousins", score=2)
        self.verdict("anim", "b.md", "B", "round 0, every one: stilts, cousins", score=1)
        p = self.checks("anim", [self.cousins_check()])
        code, out = self.cli("validate", "anim")
        self.assertEqual(code, 0, out)
        c = load_json(p)["checks"][0]
        self.assertEqual(c["status"], "proposed")
        self.assertEqual((c["validation"]["caught"], c["validation"]["false_alarms"]), (2, 0))
        self.assertIn("needs 1 more rejection", out["lines"][0])

    def test_three_caught_and_three_spared_is_validated_then_one_loved_flag_demotes_it(self):
        for m in ("A", "B", "D"):
            self.tight(m, 0)
            self.verdict("anim", f"{m}.md", m, "round 0: cousins", score=2)
        for m in ("E", "F", "G"):
            self.wide(m, 0)
            self.round(m, 1, [cand(m, 1, 0, {})], parents=[f"{m}/r0/c0"])
        p = self.checks("anim", [self.cousins_check()])
        self.cli("validate", "anim")
        self.assertEqual(load_json(p)["checks"][0]["status"], "validated")
        # a later round the owner LOVED that the check flags: it stops blocking
        self.tight("H", 0)
        self.verdict("anim", "h.md", "H", "round 0 - love these", score=9)
        self.cli("validate", "anim")
        c = load_json(p)["checks"][0]
        self.assertEqual(c["status"], "proposed")
        self.assertEqual(c["validation"]["alarm_targets"], ["H/round_0"])

    def test_a_retest_that_changes_nothing_but_the_date_writes_nothing(self):
        self.two_and_two()
        p = self.checks("anim", [self.cousins_check()])
        self.assertTrue(K.do_validate(self.root, "anim", [])["written"])  # the first validation is news
        data = load_json(p)
        data["checks"][0]["validation"]["date"] = "2026-01-01"  # as if validated on another day
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.write("\n")
        before = read_text(p)
        res = K.do_validate(self.root, "anim", [])
        self.assertFalse(res["written"])
        self.assertEqual(read_text(p), before)  # the old date stays: no churn line in git

    def test_a_file_of_built_in_checks_is_never_rewritten(self):
        p = os.path.join(self.root, "kit", "knowledge", "vault", "vfx", "checks.json")
        text = ('{"lane": "vfx", "checks": [{"id": "v1", "words": ["x"], "measure": "builtin",\n'
                '  "status": "built in", "builtin": "a gate"}]}\n')
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        self.assertFalse(K.do_validate(self.root, "vfx", [])["written"])
        self.assertEqual(read_text(p), text)  # the hand formatting kept

    def test_a_check_that_flags_more_loved_rounds_than_it_catches_is_retired(self):
        self.tight("A", 0)
        self.verdict("anim", "a.md", "A", "round 0: cousins", score=2)
        for m in ("E", "F", "G"):
            self.tight(m, 0, None)
            self.round(m, 1, [cand(m, 1, 0, {})], parents=[f"{m}/r0/c2"])
        p = self.checks("anim", [self.cousins_check()])
        self.cli("validate", "anim")
        self.assertEqual(load_json(p)["checks"][0]["status"], "retired")

    def two_and_two(self):
        for m in ("A", "B"):
            self.tight(m, 0)
            self.verdict("anim", f"{m}.md", m, "round 0: cousins", score=2)
        for m in ("C", "D"):
            self.wide(m, 0)
            self.round(m, 1, [cand(m, 1, 0, {})], parents=[f"{m}/r0/c0"])

    def test_no_threshold_yet_proposes_one_halfway_when_the_owners_rounds_split(self):
        self.two_and_two()
        p = self.checks("anim", [self.cousins_check(threshold=None)])
        _, out = self.cli("validate", "anim")
        c = load_json(p)["checks"][0]
        lo = max(K.slider_spread(self.root, f"{m}/round_0") for m in ("A", "B"))
        hi = min(K.slider_spread(self.root, f"{m}/round_0") for m in ("C", "D"))
        self.assertAlmostEqual(c["threshold"], round((lo + hi) / 2, 5))
        self.assertIn("auto", c["threshold_from"])
        self.assertIn("threshold auto-proposed", out["lines"][0])

    def test_one_rejection_and_one_loved_piece_never_set_a_threshold(self):
        self.tight("A", 0)
        self.verdict("anim", "a.md", "A", "round 0: cousins", score=2)
        self.wide("C", 0)
        self.round("C", 1, [cand("C", 1, 0, {})], parents=["C/r0/c0"])
        p = self.checks("anim", [self.cousins_check(threshold=None)])
        _, out = self.cli("validate", "anim")
        c = load_json(p)["checks"][0]
        self.assertIsNone(c["threshold"])
        self.assertIsNone(c["validation"]["caught"])  # nothing is caught or spared without a threshold
        self.assertIsNone(c["validation"]["spared"])
        self.assertIn("no threshold yet", out["lines"][0])

    def test_a_guessed_number_never_labels_a_round_and_dry_writes_nothing(self):
        self.tight("A", 0)
        self.verdict("anim", "a.md", "A", "round 0: cousins", score=2, source="inferred")
        p = self.checks("anim", [self.cousins_check()])
        before = read_text(p)
        code, out = self.cli("validate", "anim", "--dry")
        self.assertEqual(code, 0, out)
        self.assertIn("caught 0 of 0", out["lines"][0])
        self.assertEqual(read_text(p), before)

    def test_a_redo_saying_the_words_rejects_like_a_low_number(self):
        self.tight("A", 0)
        self.verdict("anim", "a.md", "A", "Redo - round 0, cousins", direction="redo")
        self.checks("anim", [self.cousins_check()])
        _, out = self.cli("validate", "anim", "--dry")
        self.assertIn("caught 1 of 1", out["lines"][0])

    def test_a_threshold_is_never_tested_on_the_pieces_it_was_fit_on(self):
        self.tight("A", 0)
        self.verdict("anim", "a.md", "A", "round 0: cousins", score=2)
        check = self.cousins_check()
        check["fit_on"] = ["A/round_0"]
        p = self.checks("anim", [check])
        _, out = self.cli("validate", "anim")
        v = load_json(p)["checks"][0]["validation"]
        self.assertEqual((v["caught"], v["rejections_measured"]), (0, 0))
        self.assertEqual(v["held_out_fit"], ["A/round_0"])
        self.assertIn("sit out", out["lines"][0])

    def test_an_auto_threshold_records_the_pieces_it_was_fit_on(self):
        self.two_and_two()
        p = self.checks("anim", [self.cousins_check(threshold=None)])
        self.cli("validate", "anim")
        c = load_json(p)["checks"][0]
        self.assertEqual(c["fit_on"], ["A/round_0", "B/round_0", "C/round_0", "D/round_0"])
        self.assertEqual(c["validation"]["caught"], 0)  # tested on nothing it was fit on

    def test_a_pick_the_owners_words_later_ran_down_is_never_spared(self):
        self.wide("C", 0)
        self.round("C", 1, [cand("C", 1, 0, {})], parents=["C/r0/c1"])
        # a candidate note ("C/r0/c1") whose number a model guessed from the owner's words: it can only take away
        self.verdict("anim", "c.md", '"C/r0/c1"', "Dont like the poses man", score=4, source="inferred")
        self.assertNotIn("C/round_0", K.labels(self.root, "anim", {"words": ["cousins"]}))

    def test_a_note_named_after_a_round_counts_for_that_round(self):
        self.tight("R", 1)
        self.verdict("anim", "r1.md", '"R/r1"', "they are all cousins of each other", score=2)
        labs = K.labels(self.root, "anim", {"words": ["cousins"]})
        self.assertEqual(labs["R/round_1"][0], "positive")

    def test_an_unknown_target_is_an_error_not_a_quiet_pass(self):
        self.checks("anim", [self.cousins_check()])
        code, out = self.cli("run", "anim", "Nope/round_0")
        self.assertEqual(code, 1)
        self.assertIn("unknown target", out["error"])

    def test_a_negated_or_partial_word_is_not_the_complaint(self):
        self.assertTrue(K.said("the vfx looks so static", ["static"]))
        self.assertFalse(K.said("it is not static at all", ["static"]))
        self.assertFalse(K.said("static? not at all", ["static"]))
        self.assertFalse(K.said("it doesnt look static", ["static"]))
        self.assertFalse(K.said("no cousinship here", ["cousins"]))
        self.assertTrue(K.said("stilts, arm-only swing", ["arm-only"]))

    def test_a_broken_measure_is_not_measurable_and_never_stops_the_others(self):
        def boom(_root, _target):
            raise RuntimeError("model missing")

        K.MEASURES["boom"] = boom
        try:
            self.round("M", 0, [cand("M", 0, i, {"time": 0.1 * i}) for i in range(3)])
            self.checks("anim", [
                {"id": "x", "words": ["a"], "target": "round", "measure": "boom", "threshold": 1, "status": "proposed"},
                {"id": "y", "words": ["b"], "target": "round", "measure": "slider_spread", "threshold": 9,
                 "status": "proposed"},
            ])
            res = K.do_run(self.root, "anim", ["M/round_0"])
        finally:
            del K.MEASURES["boom"]
        self.assertIn("not measurable (RuntimeError: model missing)", res["lines"][0])
        self.assertIn("y [proposed]: FAIL", res["lines"][1])

    def test_vfx_labels_come_from_the_owners_words_and_numbers(self):
        for name in ("flat", "loved"):
            d = os.path.join(self.root, "library", "vfx", "effects", name, "previews")
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, "hero.mp4"), "wb").close()
        self.verdict("vfx", "flat.md", "flat", "the vfx looks so static, its horrible, like his drawing")
        self.verdict("vfx", "loved.md", "loved", "WOW", score=9)
        labs = K.labels(self.root, "vfx", {"words": ["static"]})
        self.assertEqual(labs["flat"][0], "positive")
        self.assertEqual(labs["loved"][0], "negative")

    def test_vfx_a_middling_score_or_praise_using_the_word_is_never_a_rejection(self):
        for name in ("mid", "praised", "wordsonly"):
            d = os.path.join(self.root, "library", "vfx", "effects", name, "previews")
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, "hero.mp4"), "wb").close()
        self.verdict("vfx", "mid.md", "mid", "nice flow, a touch static at the end but I like it", score=6)
        self.verdict("vfx", "praised.md", "praised", "WOW it looks like a drawing come alive, amazing")
        self.verdict("vfx", "wordsonly.md", "wordsonly", "genuinely surprised, they look real")
        labs = K.labels(self.root, "vfx", {"words": ["static", "like a drawing"]})
        self.assertNotIn("mid", labs)  # a 6 is neither a rejection nor loved
        self.assertEqual(labs["praised"][0], "negative")  # number-free praise counts as loved, never as the complaint
        self.assertEqual(labs["wordsonly"][0], "negative")

    def test_a_new_effect_is_measured_from_the_players_recording(self):
        import cv2
        import numpy as np

        d = os.path.join(self.root, "build", "vfx", "booth")
        os.makedirs(d, exist_ok=True)
        w = cv2.VideoWriter(os.path.join(d, "fresh_play_hero.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 30, (160, 90))
        if not w.isOpened():
            self.skipTest("this opencv cannot write mp4")
        for i in range(20):
            frame = np.zeros((90, 160, 3), np.uint8)
            frame[30:60, (i * 6) % 140:(i * 6) % 140 + 20] = 255
            w.write(frame)
        w.release()
        self.assertIn("fresh", K.targets(self.root, "vfx"))
        self.assertGreater(K.motion_energy(self.root, "fresh"), 0.01)


if __name__ == "__main__":
    unittest.main()
