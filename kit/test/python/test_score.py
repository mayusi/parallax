"""The quality score's arithmetic (kit/blender/rbx_score.py): the raw formula, the owner calibration, the ratchet, the
wood test and the weight fit. These numbers decide pass / fail for every build — they must hold exactly."""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_score as S  # noqa: E402

FULL = {k: 0.8 for k in S.FIT_COMPONENTS}


def grade(owner, obj="thing", tier="prop", **comp):
    return {"asset": f"{obj}_{owner}", "object": obj, "owner": owner, "tier": tier, "components": {**FULL, **comp}}


class TestRaw(unittest.TestCase):
    def test_weighted_mean_times_craft(self):
        w = {k: 1.0 for k in S.WEIGHTS}
        comp = {"silhouette": 1.0, "detail": 0.5}
        self.assertEqual(S.raw_of(comp, "hero", w), 75.0)
        self.assertEqual(S.raw_of({**comp, "craft": 0.5}, "hero", w), 37.5)

    def test_prop_ignores_markings_and_missing_reference(self):
        w = {k: 1.0 for k in S.WEIGHTS}
        self.assertEqual(S.raw_of({"detail": 1.0, "markings": 0.0}, "prop", w), 100.0)
        self.assertEqual(S.raw_of({"detail": 1.0, "markings": 0.0}, "hero", w), 50.0)
        self.assertEqual(S.raw_of({"detail": 1.0}, "hero", w), 100.0)  # no reference given: not a zero

    def test_empty_components(self):
        self.assertEqual(S.raw_of({}, "prop"), 0.0)


class TestOrganic(unittest.TestCase):
    """an organic model (the share of it that was sculpted) earns variety by its surface detail and materials by its
    colour variation; a hard-surface one — and every grade and floor made before the measure — is scored as before"""
    STUMP = {"detail": 1.0, "texture": 1.0, "variety": 0.0, "materials": 0.15}

    def test_a_hard_model_is_unchanged(self):
        self.assertIs(S.effective(self.STUMP), self.STUMP)
        self.assertEqual(S.effective({**self.STUMP, "organic": 0.0}), {**self.STUMP, "organic": 0.0})

    def test_a_sculpted_model_earns_variety_and_materials_from_its_surface(self):
        e = S.effective({**self.STUMP, "organic": 1.0})
        self.assertEqual((e["variety"], e["materials"]), (1.0, 1.0))
        self.assertEqual((e["detail"], e["texture"]), (1.0, 1.0))   # (the sources themselves untouched)

    def test_blended_by_the_share_never_jumping_at_a_line(self):
        half = S.effective({**self.STUMP, "organic": 0.5})
        self.assertAlmostEqual(half["variety"], 0.5)
        self.assertAlmostEqual(half["materials"], 0.575)

    def test_never_lowers_what_was_measured(self):
        e = S.effective({"detail": 0.2, "texture": 0.1, "variety": 0.9, "materials": 0.8, "organic": 1.0})
        self.assertEqual((e["variety"], e["materials"]), (0.9, 0.8))   # (a stump with real fungi keeps its kinds)

    def test_raw_weighs_the_effective_components(self):
        w = {k: 1.0 for k in S.WEIGHTS}
        hard = S.raw_of(dict(self.STUMP), "prop", w)
        soft = S.raw_of({**self.STUMP, "organic": 1.0}, "prop", w)
        self.assertEqual(hard, round((1.0 + 1.0 + 0.0 + 0.15) / 4 * 100, 1))
        self.assertEqual(soft, 100.0)

    def test_the_fit_sees_what_raw_weighs(self):
        empty = (0.9, 0.1, 0.7, 0.3, 0.5, 0.2)   # (noise the hand weights mis-predict: the fit has to move)
        grades = [grade(30 + 5 * i, obj=f"o{i}", **{"variety": 0.0, "detail": 0.2 + 0.1 * i, "empty": empty[i],
                                                     "organic": 1.0}) for i in range(6)]
        hard = [{**g, "components": {k: v for k, v in g["components"].items() if k != "organic"}} for g in grades]
        # (on the organic grades variety carries detail's signal — on the same numbers called hard, a dead column)
        self.assertNotEqual(S.fit_weights(grades)["variety"], S.fit_weights(hard)["variety"])


class TestCalibration(unittest.TestCase):
    def test_monotone_never_reorders(self):
        rng = random.Random(7)
        grades = [grade(rng.randint(0, 100), detail=rng.random(), texture=rng.random()) for _ in range(15)]
        prev = -1.0
        for raw in range(0, 101):
            now, used = S.calibrate(float(raw), grades)
            self.assertGreaterEqual(now, prev, f"raw {raw} maps below raw {raw - 1}")
            self.assertEqual(used, 15)
            prev = now

    def test_no_grades_is_identity(self):
        self.assertEqual(S.calibrate(42.0, []), (42.0, 0))

    def test_grades_measured_by_todays_code_win(self):
        """once enough grades are measured by today's measuring code, older measurements leave the calibration"""
        old = [dict(grade(o), measure=S.MEASURE_VERSION - 1) for o in (5, 95)]
        few = [dict(grade(o, detail=o / 100), measure=S.MEASURE_VERSION) for o in (10, 30, 50)]
        self.assertEqual(len(S.grade_points(old + few)), 5)  # too few current ones: everything helps
        many = few + [dict(grade(o, detail=o / 100), measure=S.MEASURE_VERSION) for o in (70, 90)]
        self.assertEqual(len(S.grade_points(old + many)), 5)  # enough: only today's measurements

    def test_legacy_raw_only_grades_drop_out(self):
        legacy = {"asset": "old", "raw": 99.0, "owner": 5}
        few = [grade(50), grade(60)]
        self.assertEqual(len(S.grade_points(few + [legacy])), 3)  # too few measured grades: the legacy one helps
        many = [grade(o, detail=o / 100) for o in (10, 30, 50, 70, 90)]
        self.assertEqual(len(S.grade_points(many + [legacy])), 5)  # enough: the other scale is left out


class TestRatchet(unittest.TestCase):
    def test_unchanged_build_never_fails_when_the_scale_moves(self):
        comp = {**FULL, "texture": 0.3, "detail": 0.9, "craft": 1.0}
        acc = {"components": comp, "raw": 1.0}  # (a stale stored raw must not be what is compared)
        rng = random.Random(3)
        for _ in range(50):
            w = {k: rng.uniform(0.5, 30) for k in S.WEIGHTS}
            worse, then, how = S.ratchet(acc, S.raw_of(comp, "prop", w), "prop", w)
            self.assertFalse(worse)
            self.assertEqual(how, "components")
            self.assertAlmostEqual(then, S.raw_of(comp, "prop", w))

    def test_worse_build_fails(self):
        acc = {"components": {**FULL, "craft": 1.0}}
        worse, then, _ = S.ratchet(acc, S.raw_of({**FULL, "detail": 0.1}, "prop"), "prop")
        self.assertTrue(worse, f"a build far below the accepted {then} passed")

    def test_within_margin_passes(self):
        acc = {"components": dict(FULL)}
        then = S.raw_of(FULL, "prop")
        self.assertFalse(S.ratchet(acc, then - S.RATCHET_RAW + 0.1, "prop")[0])
        self.assertTrue(S.ratchet(acc, then - S.RATCHET_RAW - 0.1, "prop")[0])

    def test_other_measuring_code_is_never_compared(self):
        """a build accepted under older measuring code: an unchanged rebuild measures differently — never a fail,
        never a pass: said (re-accept)"""
        acc = {"components": {**FULL, "craft": 1.0}, "measure": S.MEASURE_VERSION - 1}
        worse, then, how = S.ratchet(acc, 0.0, "prop", measure=S.MEASURE_VERSION)
        self.assertIsNone(worse)
        self.assertEqual(how, "measure")
        self.assertIsNotNone(then)
        same = dict(acc, measure=S.MEASURE_VERSION)
        self.assertTrue(S.ratchet(same, 0.0, "prop", measure=S.MEASURE_VERSION)[0])
        self.assertIsNone(S.ratchet({"components": FULL}, 0.0, "prop", measure=S.MEASURE_VERSION)[0])  # no version

    def test_selftest_ratchet_fixture_is_stamped_with_todays_measure(self):
        """the selftest's ratchet fixture compares only if its record carries today's measuring version: bumping
        MEASURE_VERSION without re-stamping it turns the ratchet check into a mere warning"""
        acc = S.accepted("_selftest_ratchet")
        self.assertIsNotNone(acc)
        self.assertEqual(acc.get("measure"), S.MEASURE_VERSION)

    def test_old_records(self):
        self.assertEqual(S.ratchet({"raw": 80.0}, 70.0, "prop"), (True, 80.0, "stored"))
        self.assertEqual(S.ratchet({"score": 80}, 70.0, "prop"), (None, None, None))  # nothing comparable: said, not guessed
        self.assertEqual(S.ratchet(None, 70.0, "prop"), (None, None, None))


class TestFloor(unittest.TestCase):
    """kit accept asks rbx_score.floor_change before replacing a floor: both builds re-scored with TODAY's weights"""

    def test_lowering_is_seen_on_todays_scale(self):
        acc = {"components": {**FULL, "craft": 1.0}, "measure": S.MEASURE_VERSION, "raw": 10.0}  # stale stored raw
        worse = {"components": {**FULL, "detail": 0.1}, "measure": S.MEASURE_VERSION, "raw": 99.0}
        c = S.floor_change(acc, worse)
        self.assertTrue(c["lowering"])
        self.assertFalse(c["rebase"])
        same = {"components": {**FULL, "craft": 1.0}, "measure": S.MEASURE_VERSION}
        self.assertFalse(S.floor_change(acc, same)["lowering"])

    def test_small_steps_still_lower_the_floor(self):
        """a floor walked down 1 raw point at a time is lowered all the same (only rebuild noise is forgiven)"""
        acc = {"components": dict(FULL), "measure": S.MEASURE_VERSION}
        step = {"components": {**FULL, "detail": FULL["detail"] - 0.05}, "measure": S.MEASURE_VERSION}
        c = S.floor_change(acc, step)
        self.assertLess(c["now"], c["then"])
        self.assertGreater(c["now"], c["then"] - S.RATCHET_RAW)  # (inside the ratchet's margin ...)
        self.assertTrue(c["lowering"])  # (... and still a lowering)
        self.assertFalse(S.floor_change(acc, dict(acc))["lowering"])

    def test_broken_or_missing_floors(self):
        entry = {"components": dict(FULL), "measure": S.MEASURE_VERSION}
        self.assertTrue(S.floor_change(None, entry)["first"])
        for broken in ("unreadable", [], {"raw": 80.0}):
            self.assertTrue(S.floor_change(broken, entry)["rebase"], broken)

    def test_a_build_measured_by_older_code_is_stale(self):
        old = {"components": dict(FULL), "measure": S.MEASURE_VERSION - 1}
        self.assertTrue(S.floor_change(None, old)["stale"])
        self.assertFalse(S.floor_change(None, {"components": dict(FULL), "measure": S.MEASURE_VERSION})["stale"])

    def test_other_measuring_code_is_a_rebase(self):
        acc = {"components": dict(FULL), "measure": S.MEASURE_VERSION - 1}
        c = S.floor_change(acc, {"components": dict(FULL), "measure": S.MEASURE_VERSION})
        self.assertTrue(c["rebase"])
        self.assertFalse(c["lowering"])  # (not comparable: neither lower nor higher)


class TestMetricTests(unittest.TestCase):
    """kit grades --write asks rbx_score.tests() whether a refit beats the hand weights: one test per metric"""

    def _pairs(self, n_obj=6):
        """two builds per object, the owner prefers the first (80 vs 20)"""
        gr = []
        for k in range(n_obj):
            gr.append(grade(80, obj=f"o{k}", detail=0.9))
            gr.append(grade(20, obj=f"o{k}", detail=0.1))
        return gr

    def test_no_difference_is_no_evidence(self):
        gr = self._pairs()
        pred = [float(g["owner"]) for g in gr]
        t = S.tests(gr, pred, pred, n_boot=200)
        self.assertEqual((t["pairs"]["wins_a"], t["pairs"]["wins_b"]), (0, 0))
        self.assertEqual(t["pairs"]["p_worse"], 1.0)
        self.assertEqual(t["pass_agree"]["p_worse"], 1.0)

    def test_six_lost_pairs_veto_a_refit(self):
        """the earlier bootstrap could not veto on pairs (a pair enters a resample only when both builds are drawn):
        the sign test must — six pairs ordered wrong where the hand weights order them right"""
        gr = self._pairs()
        right = [float(g["owner"]) for g in gr]
        wrong = [100.0 - v for v in right]  # every pair reversed
        t = S.tests(gr, wrong, right, n_boot=200)
        self.assertEqual((t["pairs"]["wins_a"], t["pairs"]["wins_b"]), (0, 6))
        self.assertLess(t["pairs"]["p_worse"], S.VETO_P)

    def test_mcnemar_counts_only_disagreements(self):
        gr = [grade(70), grade(70), grade(30), grade(30)]
        a = [60.0, 60.0, 40.0, 40.0]  # all four on the right side of the bar
        b = [60.0, 40.0, 40.0, 60.0]  # two wrong
        t = S.tests(gr, a, b, n_boot=200)
        self.assertEqual((t["pass_agree"]["wins_a"], t["pass_agree"]["wins_b"]), (2, 0))
        self.assertAlmostEqual(t["pass_agree"]["p_better"], 0.25)  # 2 of 2 by chance: 1/4


class TestRefresh(unittest.TestCase):
    def test_measurements_refresh_the_owner_never_changes(self):
        import io
        import json
        import tempfile
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as d:
            gpath = os.path.join(d, "grades.json")
            g = {"asset": "x", "owner": 42, "note": "keep me", "components": dict(FULL), "measure": 1}
            with open(gpath, "w", encoding="utf-8") as fh:
                json.dump([g, {"asset": "y", "owner": 7, "raw": 3.0}], fh)
            hist = [{"iteration": 1, "components": {**FULL, "detail": 0.2}, "measure": S.MEASURE_VERSION,
                     "raw": 50.0, "tier": "hero"}]
            with open(os.path.join(d, "x.quality.json"), "w", encoding="utf-8") as fh:
                json.dump(hist, fh)
            with redirect_stdout(io.StringIO()):
                S._refresh_main([gpath, d, "x", "y"])
            with open(gpath, encoding="utf-8") as fh:
                out = json.load(fh)
        self.assertEqual(out[0]["owner"], 42)
        self.assertEqual(out[0]["note"], "keep me")
        self.assertEqual(out[0]["measure"], S.MEASURE_VERSION)
        self.assertEqual(out[0]["components"]["detail"], 0.2)
        self.assertEqual(out[0]["tier"], "hero")
        self.assertEqual(out[1], {"asset": "y", "owner": 7, "raw": 3.0})  # (no components: untouched)


class TestWood(unittest.TestCase):
    def test_whole_words(self):
        for name in ("wood", "Wood_Dark", "plank2", "oak_trim", "lid_planks", "PINE", "DarkWood", "WoodPlank",
                     "HardwoodFloor", "redwood", "woodgrain", "ashwood"):
            self.assertTrue(S.is_wood_name(name), name)
        for name in ("keyboard", "dashboard", "circuit_board", "spine", "trash", "cash", "cloak", "steel", "", None,
                     "gunmetal_ash", "woodland_camo", "WoodlandCamo"):
            self.assertFalse(S.is_wood_name(name), name)


class TestFit(unittest.TestCase):
    def test_weights_floor_and_total(self):
        rng = random.Random(11)
        grades = [grade(rng.randint(0, 100), **{k: rng.random() for k in S.FIT_COMPONENTS}) for _ in range(20)]
        w = S.fit_weights(grades)
        self.assertAlmostEqual(sum(w[k] for k in S.FIT_COMPONENTS), S.FIT_TOTAL, delta=0.5)
        self.assertTrue(all(w[k] >= S.FIT_FLOOR - 1e-9 for k in S.FIT_COMPONENTS))
        self.assertEqual(w["markings"], S.HAND_WEIGHTS["markings"])

    def test_finds_what_the_owner_cares_about(self):
        """an owner who grades only texture: the fit moves weight onto texture, away from the rest"""
        rng = random.Random(5)
        grades = []
        for _ in range(24):
            comp = {k: rng.random() for k in S.FIT_COMPONENTS}
            grades.append(grade(round(100 * comp["texture"]), **comp))
        w = S.fit_weights(grades, lam=0.3)
        self.assertGreater(w["texture"], S.HAND_WEIGHTS["texture"] * 1.5)
        self.assertEqual(max(S.FIT_COMPONENTS, key=lambda k: w[k]), "texture")

    def test_report_without_same_object_pairs(self):
        """`kit grade` records no "object": every asset graded once means no pairs — the report says n/a, never crashes"""
        import io
        import json
        import tempfile
        from contextlib import redirect_stdout

        rng = random.Random(4)
        grades = [{"asset": f"a{i}", "owner": rng.randint(0, 100), "tier": "prop",
                   "components": {k: rng.random() for k in S.FIT_COMPONENTS}} for i in range(8)]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "grades.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(grades, fh)
            out = io.StringIO()
            with redirect_stdout(out):
                code = S._main(["fit", "--grades", path])
        self.assertEqual(code, 0)
        self.assertIn("n/a", json.loads(out.getvalue())["summary"])

    def test_too_few_grades_keeps_the_base(self):
        self.assertEqual(S.fit_weights([grade(50)]), S.HAND_WEIGHTS)

    def test_leave_one_out_never_sees_the_held_out_grade(self):
        rng = random.Random(9)
        grades = [grade(rng.randint(0, 100), obj=f"o{i % 4}", **{k: rng.random() for k in S.FIT_COMPONENTS})
                  for i in range(12)]
        before = S.evaluate(grades, lambda t: S.fit_weights(t))["pred"][0]
        changed = [dict(grades[0], owner=100 - grades[0]["owner"])] + grades[1:]
        after = S.evaluate(changed, lambda t: S.fit_weights(t))["pred"][0]
        self.assertEqual(before, after, "the prediction for a grade moved when only that grade changed")


class TestIteration(unittest.TestCase):
    def test_a_rebuild_of_the_same_build_keeps_its_iteration(self):
        hist = [{"iteration": 12, "script_sha": "a1", "score": 60}, {"iteration": 13, "script_sha": "b2", "score": 62}]
        it, kept = S.iteration_of(hist, "b2")  # only a parts answer or the review changed: build 13, measured again
        self.assertEqual(it, 13)
        self.assertEqual([h["iteration"] for h in kept], [12])  # its old entry goes; "previous" is iteration 12
        it, kept = S.iteration_of(hist, "c3")  # the model changed: the next iteration
        self.assertEqual(it, 14)
        self.assertEqual(len(kept), 2)

    def test_the_counter_starts_at_one_and_never_reuses_a_number_without_a_build(self):
        self.assertEqual(S.iteration_of([], "a1"), (1, []))
        self.assertEqual(S.iteration_of(None, None), (1, []))
        hist = [{"iteration": 4, "script_sha": None}]  # (a build with no script: nothing to call "the same")
        self.assertEqual(S.iteration_of(hist, None)[0], 5)
        self.assertEqual(S.iteration_of([{"script_sha": "a1"}], "x")[0], 2)  # (old entries without a number)


if __name__ == "__main__":
    unittest.main()
