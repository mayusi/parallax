"""The owner's grades and floors cannot be moved quietly (kit/blender/rbx_score.py): a grades file that cannot be read is
never overwritten, a re-measure refreshes only the grade of the script it rebuilt and never one whose model changed, a
floor survives the deletion of its file, a re-base without the owner is the same build only, the fitted weights land
beside their grades, and the adopt / veto rule does what its comment says it does."""

import io
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import rbx_score as S  # noqa: E402

FULL = {k: 0.8 for k in S.FIT_COMPONENTS}


def quiet(fn, *a):
    out = io.StringIO()
    with redirect_stdout(out):
        code = fn(*a)
    return code, (json.loads(out.getvalue().strip().splitlines()[-1]) if out.getvalue().strip() else {})


def write(path, data):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data if isinstance(data, str) else json.dumps(data))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def rf(path, root):
    """read_floor in the temp repository `root`, the restore hint checked and set aside"""
    rec, where = S.read_floor(path, root=root)
    if where == "git":
        assert rec["restore"].startswith("git checkout "), rec
        rec = {k: v for k, v in rec.items() if k != "restore"}
    return rec, where


class TestAdd(unittest.TestCase):
    def test_a_file_it_cannot_read_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            gpath, epath = os.path.join(d, "grades.json"), os.path.join(d, "e.json")
            conflict = '<<<<<<< HEAD\n[{"asset": "a", "owner": 40}]\n=======\n[]\n>>>>>>> theirs\n'
            write(gpath, conflict)
            write(epath, {"asset": "b", "owner": 60})
            code, out = quiet(S._add_main, [gpath, epath])
            self.assertEqual(code, 1)
            self.assertEqual(out["status"], "fail")
            with open(gpath, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), conflict)
            write(gpath, {"not": "a list"})
            self.assertEqual(quiet(S._add_main, [gpath, epath])[0], 1)

    def test_appends_one_grade_or_a_round(self):
        with tempfile.TemporaryDirectory() as d:
            gpath, epath = os.path.join(d, "grades.json"), os.path.join(d, "e.json")
            write(epath, {"asset": "a", "owner": 40})
            self.assertEqual(quiet(S._add_main, [gpath, epath])[0], 0)  # (no file yet: a new one)
            write(epath, [{"asset": "b", "owner": 50}, {"asset": "c", "owner": 60}])
            self.assertEqual(quiet(S._add_main, [gpath, epath])[0], 0)
            self.assertEqual([g["asset"] for g in read(gpath)], ["a", "b", "c"])


class TestRefreshScope(unittest.TestCase):
    """kit grades --remeasure names each rebuilt grade asset@project@sha"""

    def _run(self, grades, hist_entry, tokens):
        with tempfile.TemporaryDirectory() as d:
            gpath = os.path.join(d, "grades.json")
            write(gpath, grades)
            write(os.path.join(d, "x.quality.json"), [hist_entry])
            _code, out = quiet(S._refresh_main, [gpath, d] + tokens)
            return read(gpath), out

    def test_only_the_grade_of_the_rebuilt_script_is_refreshed(self):
        old = {"asset": "x", "project": "p", "script_sha": "AAAA", "owner": 40, "components": dict(FULL), "measure": 1}
        new = {"asset": "x", "project": "p", "script_sha": "BBBB", "owner": 70, "components": dict(FULL), "measure": 1}
        other = {"asset": "x", "project": "q", "script_sha": "BBBB", "owner": 55, "components": dict(FULL), "measure": 1}
        entry = {"components": {**FULL, "detail": 0.2}, "measure": S.MEASURE_VERSION, "raw": 50.0}
        out, _ = self._run([old, new, other], entry, ["x@p@BBBB"])
        self.assertEqual(out[0]["components"]["detail"], FULL["detail"])  # the old script's grade: untouched
        self.assertEqual(out[0]["measure"], 1)
        self.assertEqual(out[1]["components"]["detail"], 0.2)  # the rebuilt script's grade: refreshed
        self.assertEqual(out[1]["owner"], 70)
        self.assertEqual(out[2]["measure"], 1)  # another project's grade of the same name: untouched

    def test_a_changed_model_keeps_its_old_measurements(self):
        g = {"asset": "x", "project": "p", "script_sha": "S", "owner": 40, "components": dict(FULL), "measure": 1,
             "tris": 1000, "size": [1.0, 2.0, 3.0]}
        for entry in ({"components": {**FULL, "detail": 0.2}, "measure": S.MEASURE_VERSION, "tris": 1500,
                       "size": [1.0, 2.0, 3.0]},
                      {"components": {**FULL, "detail": 0.2}, "measure": S.MEASURE_VERSION, "tris": 1010,
                       "size": [1.0, 2.0, 3.3]}):
            out, rep = self._run([g], entry, ["x@p@S"])
            self.assertEqual(out[0]["measure"], 1, entry)
            self.assertEqual(len(rep["changed"]), 1, entry)
        out, rep = self._run([g], {"components": {**FULL, "detail": 0.2}, "measure": S.MEASURE_VERSION,
                                   "tris": 1020, "size": [1.0, 2.01, 3.0]}, ["x@p@S"])
        self.assertEqual(out[0]["measure"], S.MEASURE_VERSION)  # (rebuild drift inside the tolerance: the same model)
        self.assertEqual(rep["changed"], [])

    def test_a_rebuild_from_another_script_is_not_the_graded_build(self):
        g = {"asset": "x", "project": "p", "script_sha": "S", "owner": 40, "components": dict(FULL), "measure": 1}
        out, rep = self._run([g], {"components": {**FULL, "detail": 0.2}, "measure": S.MEASURE_VERSION,
                                   "script_sha": "OTHER"}, ["x@p@S"])
        self.assertEqual(out[0]["measure"], 1)
        self.assertEqual(len(rep["changed"]), 1)

    def test_a_grade_without_a_fingerprint_takes_one(self):
        g = {"asset": "x", "project": "p", "script_sha": "S", "owner": 40, "components": dict(FULL), "measure": 1}
        out, _ = self._run([g], {"components": dict(FULL), "measure": S.MEASURE_VERSION, "tris": 900,
                                 "size": [1, 1, 1]}, ["x@p@S"])
        self.assertEqual(out[0]["tris"], 900)
        self.assertIn("fingerprint_backfilled", out[0])


class TestFloorFile(unittest.TestCase):
    """a floor is read from git when its file is deleted or broken: removing it never escapes the ratchet"""

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_deleted_or_broken_floors_come_back_from_git(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                       GIT_COMMITTER_EMAIL="t@t")
            run = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True, env=env, check=True)  # noqa: E731
            run("init", "-q")
            os.makedirs(os.path.join(d, "models"))
            path = os.path.join(d, "models", "box.accepted.json")
            floor = {"asset": "box", "components": dict(FULL), "measure": S.MEASURE_VERSION}
            write(path, floor)
            run("add", "-A")
            run("commit", "-qm", "floor")
            self.assertEqual(rf(path, d), (floor, "file"))
            write(path, "{ broken")
            self.assertEqual(rf(path, d), (floor, "git"))
            os.remove(path)
            self.assertEqual(rf(path, d), (floor, "git"))
            never = os.path.join(d, "models", "new.accepted.json")
            self.assertEqual(rf(never, d), (None, None))
            write(never, "{ broken")
            self.assertEqual(rf(never, d), ({"unreadable": True}, "unreadable"))

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_only_a_committed_floor_holds(self):
        """the committed floor holds whatever the file says (an edit up or down, a stripped record, a NaN, a deletion
        in a commit): a change of floor takes effect once it is committed"""
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                       GIT_COMMITTER_EMAIL="t@t")
            run = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True, env=env, check=True)  # noqa: E731
            run("init", "-q")
            path = os.path.join(d, "box.accepted.json")
            floor = {"asset": "box", "components": dict(FULL), "measure": S.MEASURE_VERSION}
            write(path, floor)
            run("add", "-A")
            run("commit", "-qm", "floor")
            for edited in (dict(floor, components={**FULL, "detail": 0.1}),  # lowered
                           dict(floor, components={**FULL, "detail": 1.0}),  # raised (uncommitted)
                           {"asset": "box", "raw": 0.0},  # stripped to a raw-only record
                           dict(floor, measure=S.MEASURE_VERSION + 1)):  # stamped with another measure
                write(path, edited)
                self.assertEqual(rf(path, d), (floor, "git"), edited)
            write(path, '{"asset": "box", "components": {"detail": NaN}}')
            self.assertEqual(rf(path, d), (floor, "git"))
            raised = dict(floor, components={**FULL, "detail": 1.0})
            write(path, raised)
            run("add", "-A")
            run("commit", "-qm", "owner raised it")
            self.assertEqual(rf(path, d), (raised, "file"))  # committed: now it holds
            run("rm", "-qf", "box.accepted.json")
            run("commit", "-qm", "gone")
            self.assertEqual(rf(path, d), (raised, "git"))  # (the version before the commit that deleted it)

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_aliases_and_git_tricks_still_find_the_committed_floor(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                       GIT_COMMITTER_EMAIL="t@t")
            run = lambda *a: subprocess.run(["git", "-C", d, *a], capture_output=True, env=env, check=True)  # noqa: E731
            run("init", "-q")
            os.makedirs(os.path.join(d, "assets", "models"))
            path = os.path.join(d, "assets", "models", "crate.accepted.json")
            floor = {"asset": "crate", "components": dict(FULL), "measure": S.MEASURE_VERSION}
            write(path, floor)
            run("add", "-A")
            run("commit", "-qm", "floor")
            low = dict(floor, components={**FULL, "detail": 0.1})
            write(path, low)
            # another spelling of the same file (Windows opens it; git matches it case-insensitively here)
            self.assertEqual(rf(os.path.join(d, "Assets", "Models", "Crate.accepted.json"), d), (floor, "git"))
            # the models folder moved in kit.config.json: the committed floor is found by its name
            os.makedirs(os.path.join(d, "models2"))
            moved = os.path.join(d, "models2", "crate.accepted.json")
            write(moved, low)
            self.assertEqual(rf(moved, d), (floor, "git"))
            # the environment pointing git somewhere else changes nothing
            old = os.environ.get("GIT_DIR")
            os.environ["GIT_DIR"] = os.path.join(d, "nowhere")
            try:
                self.assertEqual(rf(path, d), (floor, "git"))
            finally:
                if old is None:
                    os.environ.pop("GIT_DIR", None)
                else:
                    os.environ["GIT_DIR"] = old
            # a replace object (git replace <committed blob> <lenient blob>) is never followed
            blob = subprocess.run(["git", "-C", d, "rev-parse", "HEAD:assets/models/crate.accepted.json"],
                                  capture_output=True, text=True, env=env, check=True).stdout.strip()
            lenient = subprocess.run(["git", "-C", d, "hash-object", "-w", path], capture_output=True, text=True,
                                     env=env, check=True).stdout.strip()
            run("replace", blob, lenient)
            self.assertEqual(rf(path, d), (floor, "git"))

    def test_a_repository_git_cannot_read_is_a_broken_floor(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".git"))  # (a repository on disk ...)
            write(os.path.join(d, "x.accepted.json"), {"components": dict(FULL), "measure": S.MEASURE_VERSION})
            real = S._git
            S._git = lambda *a, **k: (_ for _ in ()).throw(OSError("git is not installed"))  # (... git cannot run)
            try:
                rec, where = S.read_floor(os.path.join(d, "x.accepted.json"), root=d)
            finally:
                S._git = real
            self.assertEqual(where, "unreadable")
            self.assertTrue(rec["unreadable"])

    def test_a_floor_of_nan_is_broken(self):
        nan = {"components": {**FULL, "detail": float("nan")}, "measure": S.MEASURE_VERSION}
        self.assertEqual(S.ratchet(nan, 10.0, "prop", measure=S.MEASURE_VERSION), (None, None, None))
        self.assertTrue(S.floor_change(nan, {"components": dict(FULL), "measure": S.MEASURE_VERSION})["rebase"])

    def test_outside_git_a_missing_floor_is_no_floor(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(rf(os.path.join(d, "x.accepted.json"), d), (None, None))


class TestSameBuildRebase(unittest.TestCase):
    """a re-base without the owner: the build was MADE by the floor's script (the sha written into its history entry
    when it was built — never the file as it is when someone accepts) and it is the floor's model (its fingerprint)"""

    def test_same_script_same_model(self):
        acc = {"components": dict(FULL), "measure": S.MEASURE_VERSION - 1, "script_sha": "s1", "tris": 1000}
        entry = {"components": dict(FULL), "measure": S.MEASURE_VERSION, "tris": 1010, "script_sha": "s1"}
        c = S.floor_change(acc, entry)
        self.assertTrue(c["rebase"])
        self.assertTrue(c["same_script"])

    def test_another_script_or_another_model_needs_the_owner(self):
        acc = {"components": dict(FULL), "measure": S.MEASURE_VERSION - 1, "script_sha": "s1", "tris": 1000}
        entry = {"components": dict(FULL), "measure": S.MEASURE_VERSION, "tris": 1000, "script_sha": "s1"}
        self.assertFalse(S.floor_change(acc, dict(entry, script_sha="s2"))["same_script"])  # built by an edit
        self.assertFalse(S.floor_change(acc, dict(entry, script_sha=None))["same_script"])  # (an old entry)
        self.assertFalse(S.floor_change(dict(acc, script_sha=None), entry)["same_script"])
        moved = S.floor_change(acc, dict(entry, tris=1600))
        self.assertFalse(moved["same_script"])
        self.assertIn("triangles", moved["changed"])

    def test_a_floor_without_a_fingerprint_needs_the_owner(self):
        acc = {"components": dict(FULL), "measure": S.MEASURE_VERSION - 1, "script_sha": "s1"}
        c = S.floor_change(acc, {"components": dict(FULL), "measure": S.MEASURE_VERSION, "tris": 1000,
                                 "script_sha": "s1"})
        self.assertFalse(c["same_script"])
        self.assertIn("fingerprint", c["changed"])

    def test_an_empty_floor_is_a_broken_one(self):
        c = S.floor_change({}, {"components": dict(FULL), "measure": S.MEASURE_VERSION, "script_sha": "s1"})
        self.assertTrue(c["rebase"])
        self.assertFalse(c["same_script"])

    def test_script_identity_ignores_line_endings(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a.py"), os.path.join(d, "b.py")
            with open(a, "wb") as fh:
                fh.write(b"x = 1\r\ny = 2\r\n")
            with open(b, "wb") as fh:
                fh.write(b"x = 1\ny = 2\n")
            self.assertEqual(S.script_sha(a), S.script_sha(b))
            self.assertEqual(len(S.script_sha(a)), 16)
            self.assertIsNone(S.script_sha(os.path.join(d, "none.py")))


class TestWriteRule(unittest.TestCase):
    """kit grades --write: the weights land beside the grades they were fitted on, and the rule decides"""

    def _grades(self, n=8):
        rng = random.Random(3)
        return [{"asset": f"a{i}", "project": "p", "at": f"t{i}", "owner": rng.randint(0, 100), "tier": "prop",
                 "measure": S.MEASURE_VERSION, "components": {k: rng.random() for k in S.FIT_COMPONENTS}}
                for i in range(n)]

    def _main(self, d, report=None):
        env = {"KIT_GRADES": os.path.join(d, "grades.json"), "KIT_WEIGHTS_OUT": os.path.join(d, "weights.json")}
        old = {k: os.environ.get(k) for k in env}
        real = S.fit_report
        os.environ.update(env)
        try:
            if report is not None:
                S.fit_report = lambda grades, lam: report
            return quiet(S._main, ["fit", "--write"])
        finally:
            S.fit_report = real
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def _report(self, tests):
        ev = {"spearman": 0.4, "pairs": 0.7, "pass_agree": 0.7, "mae": 15.0, "n": 8, "pred": [50.0] * 8}
        return {"hand": dict(ev), "current": dict(ev), "fit": dict(ev), "lam": S.FIT_LAMBDA,
                "weights": {**S.HAND_WEIGHTS}, "tests": tests}

    @staticmethod
    def _t(pairs=(1.0, 1.0), passes=(1.0, 1.0), rank=(1.0, 1.0)):
        mk = lambda pb, pw: {"wins_a": 0, "wins_b": 0, "p_better": pb, "p_worse": pw}  # noqa: E731
        return {"pairs": mk(*pairs), "pass_agree": mk(*passes),
                "rank": {"diff": 0.0, "p_better": rank[0], "p_worse": rank[1]}}

    def test_weights_never_land_away_from_their_grades(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            write(os.path.join(d1, "grades.json"), self._grades())
            env = {"KIT_GRADES": os.path.join(d1, "grades.json"), "KIT_WEIGHTS_OUT": os.path.join(d2, "weights.json")}
            old = {k: os.environ.get(k) for k in env}
            os.environ.update(env)
            try:
                code, out = quiet(S._main, ["fit", "--write"])
            finally:
                for k, v in old.items():
                    os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            self.assertEqual(code, 1)
            self.assertIn("beside", out["summary"])
            self.assertFalse(os.path.exists(os.path.join(d2, "weights.json")))

    def test_a_veto_refuses_even_with_a_better_metric(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "grades.json"), self._grades())
            code, out = self._main(d, self._report(self._t(pairs=(1.0, 0.03), rank=(0.01, 0.99))))
            self.assertEqual(code, 0)
            self.assertIsNone(out["wrote"])
            self.assertFalse(os.path.exists(os.path.join(d, "weights.json")))

    def test_no_better_metric_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "grades.json"), self._grades())
            _code, out = self._main(d, self._report(self._t(rank=(0.3, 0.7))))
            self.assertIsNone(out["wrote"])

    def test_a_kept_refit_records_the_grades_it_saw(self):
        with tempfile.TemporaryDirectory() as d:
            grades = self._grades()
            write(os.path.join(d, "grades.json"), grades)
            _code, out = self._main(d, self._report(self._t(passes=(0.06, 0.94))))
            self.assertIsNotNone(out["wrote"])
            w = read(os.path.join(d, "weights.json"))
            self.assertEqual(w["fitted_on"], sorted(S.grade_key(g) for g in grades))


class TestRuleErrorRates(unittest.TestCase):
    """what the adopt / veto rule's comment claims, measured"""

    def test_a_sign_test_vetoes_pairs_only_from_five_losses(self):
        def pairs_lost(k):
            gr, a, b = [], [], []
            for i in range(k):
                gr += [{"asset": f"o{i}a", "object": f"o{i}", "owner": 80, "components": dict(FULL)},
                       {"asset": f"o{i}b", "object": f"o{i}", "owner": 20, "components": dict(FULL)}]
                a += [20.0, 80.0]  # a orders every pair wrong ...
                b += [80.0, 20.0]  # ... b right
            return S.tests(gr, a, b, n_boot=50)["pairs"]["p_worse"]

        self.assertGreaterEqual(pairs_lost(4), S.VETO_P)
        self.assertLess(pairs_lost(5), S.VETO_P)

    def test_a_refit_no_better_is_kept_about_one_time_in_four(self):
        path = os.path.join(S.KIT, "grades.json")
        grades = S._graded(S.load_grades(path)) if os.path.isfile(path) else []
        if len(grades) < 15:
            self.skipTest("needs the kit's owner grades")
        owner = [float(g["owner"]) for g in grades]
        rng = random.Random(1)
        kept, sims = 0, 150
        for _ in range(sims):  # two predictors with the SAME error: neither is better
            a = [min(100.0, max(0.0, o + rng.gauss(0, 20))) for o in owner]
            b = [min(100.0, max(0.0, o + rng.gauss(0, 20))) for o in owner]
            t = S.tests(grades, a, b, n_boot=200, seed=rng.randint(0, 10 ** 6))
            if not any(v["p_worse"] < S.VETO_P for v in t.values()) and any(v["p_better"] < S.ADOPT_P
                                                                             for v in t.values()):
                kept += 1
        rate = kept / sims
        self.assertGreater(rate, 0.08, rate)
        self.assertLess(rate, 0.35, rate)


class TestProspective(unittest.TestCase):
    def _grades(self, n):
        rng = random.Random(7)
        out = []
        for i in range(n):
            comp = {k: rng.random() for k in S.FIT_COMPONENTS}
            out.append({"asset": f"a{i}", "project": "p", "at": f"t{i}", "owner": round(100 * comp["texture"]),
                        "tier": "prop", "measure": S.MEASURE_VERSION, "components": comp})
        return out

    def test_fresh_grades_are_the_ones_the_fit_never_saw(self):
        grades = self._grades(14)
        seen = [S.grade_key(g) for g in grades[:10]]
        pro = S.prospective(grades, seen, dict(S.HAND_WEIGHTS))
        self.assertEqual(pro["n"], 4)
        self.assertIn("current", pro)
        self.assertIn("hand", pro)
        self.assertEqual(S.prospective(grades, seen + [S.grade_key(g) for g in grades[10:12]], S.HAND_WEIGHTS),
                         {"n": 2})  # (fewer than 3 fresh: only counted)
        self.assertIsNone(S.prospective(grades, None, S.HAND_WEIGHTS))


if __name__ == "__main__":
    unittest.main()
