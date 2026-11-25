"""Pairwise judging (kit/blender/judge_pair.py + the pure parts of kit/blender/rbx_judgeviews.py): the tally counts
wins, ties and where the judges disagree, through each judge's own shuffle; the packet hides which build is which (the
key lives outside every packet, the sides are shuffled, the files never name a build); an answer that skips a question
is refused; versions resolve; the sticky frame holds the camera; the brief's game camera is read."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import judge_pair as JP  # noqa: E402
import rbx_judgeviews as JV  # noqa: E402

RED, BLUE = (220, 30, 30), (30, 60, 220)


def full(shape="1", surface="1", why="the collar is engraved, the other is a plain ring", defects=None):
    """one complete item answer in tile terms (#1 / #2)"""
    d = {t: {c: "no" for c, _, _ in JP.DEFECTS} for t in ("1", "2")}
    for (t, c), where in (defects or {}).items():
        d[t][c] = f"yes: {where}"
    return {"shape": shape, "shape_why": why, "surface": surface, "surface_why": why,
            "surface_checks": {t: {k: "yes" for k, _ in JP.SURFACE} for t in ("1", "2")}, "defects": d}


def answer(packet, items):
    return {"packet": packet, "judge": "claude@test, fresh context", "items": items}


class TestTally(unittest.TestCase):
    def test_wins_ties_and_disagreement(self):
        # three judges; "1" means A only where that judge saw A as #1
        firsts = [{"overall": "a", "muzzle": "a", "grip": "b"},
                  {"overall": "b", "muzzle": "b", "grip": "a"},
                  {"overall": "a", "muzzle": "a", "grip": "b"}]
        picks = [  # (overall, muzzle, grip) shape picks, in tile terms
            ("same", "1", "1"),  # -> same, A, B
            ("same", "2", "2"),  # -> same, A, B
            ("1", "2", "1"),  # -> A, B, B
        ]
        entries = [(f, answer("r-1", {"overall": full(p[0], "same"), "muzzle": full(p[1], "same"),
                                      "grip": full(p[2], "same")})) for f, p in zip(firsts, picks)]
        res = JP.tally_answers(entries)
        self.assertEqual(res["judges"], 3)
        m = res["items"]["muzzle"]["shape"]
        self.assertEqual((m["a"], m["b"], m["same"], m["winner"], m["split"]), (2, 1, 0, "a", True))
        self.assertEqual(m["agree"], 0.67)
        g = res["items"]["grip"]["shape"]
        self.assertEqual((g["a"], g["b"], g["winner"], g["split"]), (0, 3, "b", False))
        o = res["items"]["overall"]["shape"]
        self.assertEqual((o["a"], o["b"], o["same"], o["winner"], o["split"]), (1, 0, 2, "a", False))
        self.assertEqual(res["shape"]["b_wins"], ["grip"])
        self.assertEqual(res["shape"]["a_wins"], ["overall", "muzzle"])
        self.assertEqual(res["shape"]["split"], ["muzzle"])
        # the surface is counted on its own: everyone said "same" there
        self.assertEqual(res["surface"]["same"], ["overall", "muzzle", "grip"])
        self.assertEqual(res["surface"]["split"], [])

    def test_a_tie_between_builds_is_same(self):
        entries = [({"x": "a"}, answer("r-1", {"x": full("1")})), ({"x": "a"}, answer("r-2", {"x": full("2")}))]
        r = JP.tally_answers(entries)["items"]["x"]["shape"]
        self.assertEqual((r["a"], r["b"], r["winner"], r["split"]), (1, 1, "same", True))

    def test_defects_need_a_majority_and_keep_where(self):
        where = {("1", "floating_intersecting"): "the scope floats over the rail"}
        entries = [({"x": "a"}, answer("r-1", {"x": full(defects=where)})),
                   ({"x": "b"}, answer("r-2", {"x": full(defects={("2", "floating_intersecting"): "scope, top"})})),
                   ({"x": "a"}, answer("r-3", {"x": full(defects={("2", "seams_stretching"): "grip seam"})}))]
        res = JP.tally_answers(entries)
        cell = res["items"]["x"]["defects"]["a"]["floating_intersecting"]
        self.assertEqual((cell["yes"], cell["of"]), (2, 3))  # judge 1 saw it on #1 = A, judge 2 on #2 = A
        self.assertEqual([d["category"] for d in res["defects"]["a"]], ["floating_intersecting"])
        self.assertIn("the scope floats over the rail", res["defects"]["a"][0]["where"])
        self.assertEqual(res["defects"]["b"], [])  # one judge in three is not a majority

    def test_incomplete_answers_are_refused(self):
        items = ["overall", "grip"]
        self.assertEqual(JP.check_answer(answer("r-1", {"overall": full(), "grip": full()}), items), [])
        bad = answer("r-1", {"overall": full()})
        self.assertTrue(any("grip: no answer" in p for p in JP.check_answer(bad, items)))
        no_place = full(defects={("1", "wrong_shape"): ""})
        no_place["defects"]["1"]["wrong_shape"] = "yes"
        self.assertTrue(any("defects #1 wrong_shape" in p for p in JP.check_answer(answer("r-1", {"overall": no_place,
                                                                                            "grip": full()}), items)))
        template = full(shape="1 | 2 | same", why="one line: the difference you saw")
        probs = JP.check_answer(answer("r-1", {"overall": template, "grip": full()}), items)
        self.assertTrue(any("shape must be 1, 2 or same" in p for p in probs))
        self.assertTrue(any("shape_why" in p for p in probs))
        unsigned = answer("r-1", {"overall": full(), "grip": full()})
        unsigned["judge"] = "<model>@<harness>"
        self.assertTrue(any("who judged" in p for p in JP.check_answer(unsigned, items)))
        # the prompt's example, copied as it is, answers nothing: every pick, check and defect must be chosen
        copied = JP.check_answer(JP._example(["overall"]), ["overall"])
        for want in ("who judged", "shape must be", "surface_checks #1", "defects #1", "defects #2"):
            self.assertTrue(any(want in p for p in copied), want)


def _img(path, colour, size=(512, 384)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, colour).save(path)


def _build(repo, build, colour, iteration, at, regions):
    d = os.path.join(repo, "build", "judge", "x", "builds", build)
    for v, _ in JP.VIEWS:
        _img(os.path.join(d, f"{v}.png"), colour)
    _img(os.path.join(d, "game_first_person.png"), colour, (768, 432))
    files = {}
    for name in regions:
        _img(os.path.join(d, f"r_{name}.png"), colour, (640, 480))
        files[name] = f"r_{name}.png"
    meta = {"build": build, "iteration": iteration, "at": at, "frame": [[0, 0, 0], [1, 1, 1]], "views": [],
            "game": {"first_person": "first person"}, "regions": {**{"tip": None, "body": None}, **files}}
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh)


class TestPacket(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self._old = JP.REPO
        JP.REPO = self.repo
        os.makedirs(os.path.join(self.repo, "build", "models"))
        os.makedirs(os.path.join(self.repo, "refs"))
        _img(os.path.join(self.repo, "refs", "x.png"), (128, 128, 128), (400, 120))
        with open(os.path.join(self.repo, "refs", "x.regions.json"), "w", encoding="utf-8") as fh:
            json.dump({"image": "refs/x.png", "regions": [
                {"name": "body", "box": [10, 10, 200, 110], "parts": ["Body"], "questions": ["Is the body boxy?"]},
                {"name": "tip", "box": [200, 10, 390, 110], "parts": ["Tip"], "questions": ["Is the tip round?"]}]}, fh)
        self.new, self.old = "bbbbbbbbbbbb", "aaaaaaaaaaaa"
        with open(os.path.join(self.repo, "build", "models", "x.manifest.json"), "w", encoding="utf-8") as fh:
            json.dump({"build_id": self.new, "reference_image": "refs/x.png"}, fh)
        _build(self.repo, self.old, RED, 1, "2026-10-01 10:00:00", ["body"])  # (its tip did not exist yet)
        _build(self.repo, self.new, BLUE, 2, "2026-10-02 10:00:00", ["body", "tip"])

    def tearDown(self):
        JP.REPO = self._old
        shutil.rmtree(self.repo, ignore_errors=True)

    def run_quiet(self, fn, *a, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = fn(*a, **kw)
        return code, json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_packet_is_blind_and_its_key_is_right(self):
        code, out = self.run_quiet(JP.pair, "x", "current", "previous", judges=3, seed=7)
        self.assertEqual(code, 0, out)
        jroot = os.path.join(self.repo, "build", "judge", "x")
        key = json.load(open(os.path.join(jroot, "pairkeys", f"{out['round']}.json"), encoding="utf-8"))
        self.assertEqual((key["a"]["build"], key["b"]["build"]), (self.new, self.old))
        self.assertEqual(key["items"], ["overall", "game_first_person", "body", "tip"])
        colour = {"a": BLUE, "b": RED}
        for n in ("1", "2", "3"):
            jdir = os.path.join(jroot, "pair", f"judge_{n}")
            names = sorted(os.listdir(jdir))
            self.assertEqual(names, ["PROMPT.md", "game_first_person.png", "r1_body.png", "r2_tip.png", "views.png"])
            text = open(os.path.join(jdir, "PROMPT.md"), encoding="utf-8").read()
            for secret in (self.new[:6], self.old[:6], "iteration", "pairkeys", "current", "previous", "accepted"):
                self.assertNotIn(secret, text + " ".join(names))  # nothing in a packet says which build is which
            first = key["judges"][n]
            # #1 is the left tile: its colour is the build the key says
            views = Image.open(os.path.join(jdir, "views.png")).convert("RGB")
            self.assertEqual(views.width, 1600)
            self.assertEqual(views.getpixel((195, 426 + 146)), colour[first["overall"]])
            self.assertEqual(views.getpixel((1405, 426 + 146)), colour["b" if first["overall"] == "a" else "a"])
            body = Image.open(os.path.join(jdir, "r1_body.png")).convert("RGB")
            self.assertEqual(body.getpixel((800, 36 + 195)), colour[first["body"]])
            self.assertEqual(body.getpixel((260, 36 + 195)), (128, 128, 128))  # the reference crop
            game = Image.open(os.path.join(jdir, "game_first_person.png")).convert("RGB")
            self.assertEqual(game.getpixel((390, 36 + 219)), colour[first["game_first_person"]])
        # the shuffle is balanced: judge 2 sees every item the other way round from judge 1
        self.assertTrue(all(key["judges"]["1"][i] != key["judges"]["2"][i] for i in key["items"]))

    def test_tally_end_to_end(self):
        _, out = self.run_quiet(JP.pair, "x", "current", "previous", judges=3, seed=3)
        jroot = os.path.join(self.repo, "build", "judge", "x")
        key = json.load(open(os.path.join(jroot, "pairkeys", f"{out['round']}.json"), encoding="utf-8"))
        for n in ("1", "2", "3"):
            first = key["judges"][n]
            tile_of = lambda build, item: "1" if first[item] == build else "2"  # noqa: E731
            items = {i: full(tile_of("a", i), tile_of("a", i)) for i in key["items"]}
            items["tip"] = full(tile_of("b" if n == "3" else "a", "tip"))  # judge 3 prefers B's tip
            items["body"] = full(tile_of("b", "body"), "same")  # everyone prefers B's body
            with open(os.path.join(jroot, "pair", f"judge_{n}", "answer.json"), "w", encoding="utf-8") as fh:
                json.dump(answer(f"{out['round']}-{n}", items), fh)
        code, res = self.run_quiet(JP.tally, "x")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["shape"]["b_wins"], ["body"])
        self.assertEqual(res["shape"]["split"], ["tip"])
        self.assertIn("body", res["summary"])
        saved = json.load(open(os.path.join(jroot, "pairwise.json"), encoding="utf-8"))
        self.assertEqual(saved["items"]["tip"]["shape"]["a"], 2)
        self.assertEqual(saved["items"]["tip"]["shape"]["b"], 1)
        verdict = json.load(open(os.path.join(self.repo, "assets", "models", "x.judge.json"), encoding="utf-8"))
        self.assertEqual(verdict["pairwise"]["shape"]["b"], ["body"])
        self.assertEqual(verdict["pairwise"]["b"]["build"], self.old)

    def test_a_new_round_retires_the_old_answers(self):
        _, out = self.run_quiet(JP.pair, "x", judges=1, seed=1)
        jroot = os.path.join(self.repo, "build", "judge", "x", "pair")
        with open(os.path.join(jroot, "judge_1", "answer.json"), "w", encoding="utf-8") as fh:
            json.dump({"packet": f"{out['round']}-1"}, fh)
        self.run_quiet(JP.pair, "x", judges=1, seed=2)
        self.assertEqual(os.listdir(os.path.join(jroot, "judge_1")).count("answer.json"), 0)
        self.assertEqual(len(os.listdir(os.path.join(jroot, "old"))), 1)


class TestVersions(unittest.TestCase):
    KEPT = [{"build": "1111aaaa0000", "iteration": 1, "at": "2026-10-01", "script_sha": "s1"},
            {"build": "2222bbbb0000", "iteration": 2, "at": "2026-10-02", "script_sha": "s2"},
            {"build": "2222cccc0000", "iteration": 3, "at": "2026-10-03", "script_sha": "s3"}]

    def r(self, tok, **kw):
        ctx = {"current": "2222cccc0000", "accepted": {"build": "1111aaaa0000", "iteration": 1}, **kw}
        m, why = JP.resolve(tok, self.KEPT, **ctx)
        return m["build"] if m else why

    def test_tokens(self):
        self.assertEqual(self.r("current"), "2222cccc0000")
        self.assertEqual(self.r("previous"), "2222bbbb0000")
        self.assertEqual(self.r("accepted"), "1111aaaa0000")
        self.assertEqual(self.r("i2"), "2222bbbb0000")
        self.assertEqual(self.r("1"), "1111aaaa0000")
        self.assertEqual(self.r("2222c"), "2222cccc0000")
        self.assertIn("more than one", self.r("2222"))
        self.assertIn("not a version", self.r("bogus!"))
        # an accepted record whose build id is not kept is found by its iteration and script
        self.assertEqual(self.r("accepted", accepted={"build": "zzz", "iteration": 2, "script_sha": "s2"}),
                         "2222bbbb0000")
        self.assertIn("no kept views", self.r("accepted", accepted={"build": "zzz", "iteration": 9}))
        self.assertIn("no accepted build", self.r("accepted", accepted=None))


class TestJudgeViews(unittest.TestCase):
    def test_sticky_frame(self):
        box, kept = JV.sticky_box(None, (0, 0, 0), (1, 2, 4))
        self.assertFalse(kept)
        self.assertAlmostEqual(box[0][2], -0.16)  # padded 4% of the longest side
        same, kept = JV.sticky_box(box, (0, 0, 0), (1, 2, 4))
        self.assertTrue(kept)
        self.assertEqual(same, box)
        _, kept = JV.sticky_box(box, (0, 0, 0), (1, 2, 4.2))  # a part grew 5%: still inside the padded frame
        self.assertTrue(kept)
        _, kept = JV.sticky_box(box, (0, 0, 0), (1, 2, 5))  # outgrew it: a new frame
        self.assertFalse(kept)
        _, kept = JV.sticky_box(box, (0, 0, 0), (1, 2, 2.8))  # shrank well inside it: a new frame
        self.assertFalse(kept)

    def test_game_cameras_from_the_brief(self):
        self.assertEqual(JV.game_cameras("first person (held in the right hand)"), ["first_person"])
        self.assertEqual(JV.game_cameras("FPS, and third-person in the lobby"), ["first_person", "third_person"])
        self.assertEqual(JV.game_cameras("top-down strategy"), ["top_down"])
        self.assertEqual(JV.game_cameras("a crate on the ground"), ["world"])
        self.assertEqual(JV.game_cameras("<answer>  (first person · third person)"), [])
        self.assertEqual(JV.game_cameras("showcase renders only"), [])

    def test_brief_view_from_facts_or_the_brief(self):
        self.assertEqual(JV.brief_view({"brief": {"view": "first person"}}), "first person")
        self.assertEqual(JV.brief_view({"quality": {"brief": {"view": "top-down"}}}), "top-down")
        d = tempfile.mkdtemp()
        try:
            script = os.path.join(d, "build_y.py")
            with open(os.path.join(d, "y.brief.md"), "w", encoding="utf-8") as fh:
                fh.write("# y\n- what: a gun\n- view: third person\n")
            self.assertEqual(JV.brief_view({}, script, "y"), "third person")
            with open(os.path.join(d, "y.brief.md"), "w", encoding="utf-8") as fh:
                fh.write("- view: <answer>  (first person ...)\n")
            self.assertIsNone(JV.brief_view({}, script, "y"))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_prune_keeps_the_newest_and_the_protected(self):
        d = tempfile.mkdtemp()
        try:
            for i in range(5):
                os.makedirs(os.path.join(d, f"b{i}"))
                with open(os.path.join(d, f"b{i}", "meta.json"), "w", encoding="utf-8") as fh:
                    json.dump({"at": f"2026-10-0{i + 1}"}, fh)
            gone = JV.prune(d, keep=2, protect={"b0"})
            self.assertEqual(sorted(gone), ["b1", "b2"])
            self.assertEqual(sorted(os.listdir(d)), ["b0", "b3", "b4"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


def _trace(source="refs/gun_side.png", front="right", frame=True):
    """a traced side view: the object's box is x 20..330, y 40..150 in its picture (310 px long, 110 px high)"""
    return {"source": source, "front": front, "height_ratio": 110 / 310,
            "frame": {"x0": 20.0, "y1": 150.0, "length_px": 310.0} if frame else None}


class TestFeatureViews(unittest.TestCase):
    """the size the owner judges at, and a hero feature's close-up: where its picture box lies on the model"""

    def test_views_are_at_least_1024_wide_for_every_tier(self):
        self.assertEqual(JV.view_size("hero"), (1280, 960))
        self.assertEqual(JV.view_size("prop"), (1024, 768))
        self.assertEqual(JV.view_size("no such tier"), JV.view_size("prop"))
        for tier in ("prop", "complex", "hero", "aaa", None):
            self.assertGreaterEqual(JV.view_size(tier)[0], 1024)
            self.assertGreaterEqual(JV.view_size(tier)[1], 768)
            self.assertGreaterEqual(JV.game_size(tier)[0], 1280)
        self.assertEqual(JV.VIEW_SIZE, (512, 384))  # (what a kept build with no "view_size" was rendered at)

    def test_kept_views_are_used_again_only_at_the_same_size_frame_and_cameras(self):
        box = [[-1, -1, -1], [1, 1, 1]]
        have = {f"{v}.png" for v, _, _ in JV.VIEWS} | {"game_first_person.png", "meta.json"}
        new = {"frame": box, "view_size": [1280, 960], "game": {"first_person": "..."}}
        self.assertTrue(JV.views_kept(new, box, (1280, 960), ["first_person"], have))
        # a build kept before 2026-11-11 has no size in its record (512 x 384): rendered again at today's size
        old = {"frame": box, "game": {"first_person": "..."}}
        self.assertFalse(JV.views_kept(old, box, (1280, 960), ["first_person"], have))
        self.assertFalse(JV.views_kept(new, box, (1024, 768), ["first_person"], have))        # another tier's size
        self.assertFalse(JV.views_kept(new, [[-2, -1, -1], [1, 1, 1]], (1280, 960), ["first_person"], have))  # frame
        self.assertFalse(JV.views_kept(new, box, (1280, 960), ["first_person", "world"], have))  # another camera
        self.assertFalse(JV.views_kept(new, box, (1280, 960), ["first_person"], have - {"top.png"}))  # a picture gone
        self.assertFalse(JV.views_kept(None, box, (1280, 960), [], have))

    def test_a_box_in_a_traced_picture_is_placed_on_the_model(self):
        f = {"name": "glow strip", "picture": "refs/gun_side.png", "box": [200, 60, 300, 72]}
        fr = JV.feature_frame(f, {"side": _trace()})
        self.assertEqual((fr["view"], fr["front"]), ("side", "right"))
        self.assertAlmostEqual(fr["a"][0], 180 / 310, places=4)  # along the picture, from the outline's left edge
        self.assertAlmostEqual(fr["a"][1], 280 / 310, places=4)
        self.assertAlmostEqual(fr["b"][0], (150 - 72) / 110, places=4)  # up from the outline's bottom edge
        self.assertAlmostEqual(fr["b"][1], (150 - 60) / 110, places=4)
        # a picture whose front is on the LEFT: the same fractions of the picture (its camera is turned, not the box)
        left = JV.feature_frame(f, {"side": _trace(front="left")})
        self.assertEqual((left["a"], left["b"], left["front"]), (fr["a"], fr["b"], "left"))
        # the corners given the other way round are the same box
        self.assertEqual(JV.feature_frame({**f, "box": [300, 72, 200, 60]}, {"side": _trace()})["a"], fr["a"])

    def test_the_picture_is_found_by_path_then_by_name(self):
        traces = {"side": _trace("build/refs/gun/01_side.png"), "top": _trace("build/refs/gun/02_top.png")}
        self.assertEqual(JV.trace_of_picture("build/refs/gun/02_top.png", traces)[0], "top")
        self.assertEqual(JV.trace_of_picture("build\\refs\\gun\\01_SIDE.png", traces)[0], "side")
        self.assertEqual(JV.trace_of_picture("01_side.png", traces)[0], "side")  # (its file name: one trace has it)
        self.assertEqual(JV.trace_of_picture("closeup.png", traces), (None, None))
        twins = {"side": _trace("a/x.png"), "top": _trace("b/x.png")}
        self.assertEqual(JV.trace_of_picture("x.png", twins), (None, None))  # (two pictures of that name: not ours to pick)

    def test_a_feature_that_cannot_be_placed_says_why(self):
        traces = {"side": _trace()}
        cases = (
            ({"name": "wolf"}, "no picture"),
            ({"name": "wolf", "picture": "refs/gun_side.png"}, "no box"),
            ({"name": "wolf", "picture": "refs/wolf_closeup.png", "box": [0, 0, 9, 9]}, "not a traced view"),
            ({"name": "wolf", "picture": "refs/gun_side.png", "box": [400, 60, 500, 72]}, "outside the traced object"),
        )
        for feature, needle in cases:
            got = JV.feature_frame(feature, traces)
            self.assertIn(needle, got.get("why", ""), feature)
            self.assertTrue(got["why"].startswith("wolf"))
        rotated = JV.feature_frame({"name": "wolf", "picture": "refs/gun_side.png", "box": [200, 60, 300, 72]},
                                   {"side": _trace(frame=False)})
        self.assertIn("no plain pixel frame", rotated["why"])

    def test_the_picture_camera_lies_like_the_picture(self):
        def cross(a, b):
            return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

        d, r, u, mirror = JV.picture_camera("side", "right")
        self.assertEqual((d, r, u, mirror), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), False))
        d, r, u, mirror = JV.picture_camera("side", "left")  # the LEFT flank: seen from -X, the front points left
        self.assertEqual((d, r, mirror), ((-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), False))
        self.assertEqual(JV.picture_camera("side_left", "left"), JV.picture_camera("side", "left"))
        self.assertTrue(JV.picture_camera("side_left", "right")[3])  # (a flipped picture of the left flank)
        d, r, u, _ = JV.picture_camera("top", "right")  # from above, the front on the right, the left side up
        self.assertEqual((d, r, u), ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (-1.0, 0.0, 0.0)))
        for view, front in (("side", "right"), ("side", "left"), ("top", "right"), ("top", "left"),
                            ("front", "right"), ("back", "right")):
            d, r, u, _ = JV.picture_camera(view, front)
            self.assertEqual(cross(r, u), d, (view, front))  # a real camera: right x up points at it

    def test_a_top_view_is_laid_the_way_its_picture_lies(self):
        def cross(a, b):
            return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

        # a rifle 3 studs long and 0.4 wide. A photo's trace runs back -> front across the picture (hr 0.13);
        # a reference model's mask has its front DOWN (the same outline standing: hr 7.5)
        self.assertEqual(JV.top_lies(0.4 / 3.0, 3.0, 0.4), "side")
        self.assertEqual(JV.top_lies(3.0 / 0.4, 3.0, 0.4), "down")
        self.assertEqual(JV.top_lies(1.0, 2.0, 2.0), "side")  # (a square object cannot tell: the photo's way)
        d, r, u, mirror = JV.picture_camera("top", "right", lies="down")
        self.assertEqual((d, r, u, mirror), ((0.0, 0.0, 1.0), (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0), False))
        self.assertEqual(cross(r, u), d)  # a real camera from above: the front (+y) at the bottom, +x on the left
        self.assertEqual(JV.picture_camera("side", "right", lies="down"), JV.picture_camera("side", "right"))

    def test_the_window_and_its_pixels(self):
        ext = (-2.0, 2.0, 0.0, 1.0)  # the model: 4 studs along the picture's x, 1 stud high — as its outline (hr 0.25)
        cr, cu, w, h = JV.feature_window([0.25, 0.5], [0.5, 1.0], 0.25, ext)
        self.assertAlmostEqual(cr, -0.5)
        self.assertAlmostEqual(cu, 0.75)
        self.assertAlmostEqual(w, 1.0 + 2 * 0.08)  # the margin: 8% of its larger side, all round
        self.assertAlmostEqual(h, 0.5 + 2 * 0.08)
        self.assertAlmostEqual(JV.feature_window([0.25, 0.5], [0.5, 1.0], 0.25, ext, mirror=True)[0], 0.5)
        self.assertEqual(JV.pane_size(w, h), (1024, round(1024 * h / w)))  # its larger side: FEATURE_PX
        self.assertEqual(JV.pane_size(0.1, 0.4)[1], 1024)
        self.assertEqual(JV.FEATURE_PX, 1024)
        # a feature that is 2% of the model's length still fills the close-up (the wolf head was 40 px of a 512 view)
        _, _, w2, h2 = JV.feature_window([0.49, 0.51], [0.4, 0.6], 0.25, ext)
        self.assertEqual(max(JV.pane_size(w2, h2)), 1024)

    def test_a_model_off_in_proportion_is_shown_out_of_place_not_stretched(self):
        # the model is 20% too TALL for its outline: one scale (its length on the outline's length), centres together
        # — the window keeps the picture's millimetres, and the feature is seen where the too-tall model has it
        tall = (-2.0, 2.0, 0.0, 1.2)
        cr, cu, w, h = JV.feature_window([0.25, 0.5], [0.5, 1.0], 0.25, tall)
        self.assertAlmostEqual(w, 1.0 + 2 * 0.08)  # the same size as on a model in proportion: never stretched
        self.assertAlmostEqual(h, 0.5 + 2 * 0.08)
        self.assertAlmostEqual(cr, -0.5)
        self.assertAlmostEqual(cu, 0.6 + 0.25)  # the boxes' centres together: 0.6, then the feature's own offset
        # an upright object (a sword traced standing: its outline 4 x as high as long): its height sets the scale
        up = (0.0, 1.0, 0.0, 4.0)
        _, _, w3, h3 = JV.feature_window([0.0, 1.0], [0.0, 0.25], 4.0, up, margin=0.0)
        self.assertAlmostEqual(w3, 1.0)
        self.assertAlmostEqual(h3, 1.0)
        # the model's window and the picture's crop have ONE shape: the pair's two panes come out the same size
        _, _, ww, wh = JV.feature_window([180 / 310, 280 / 310], [78 / 110, 90 / 110], 110 / 310, tall)
        x0, y0, x1, y1 = JV.picture_box([200, 60, 300, 72])
        self.assertAlmostEqual(ww / wh, (x1 - x0) / (y1 - y0), places=2)

    def test_the_reference_crop_has_the_same_margin(self):
        self.assertEqual(JV.picture_box([200, 60, 300, 72]), (192, 52, 308, 80))
        self.assertEqual(JV.picture_box([300, 72, 200, 60]), (192, 52, 308, 80))
        self.assertEqual(JV.picture_box([2, 2, 52, 30])[:2], (-2, -2))  # (off the picture: padded there, not clamped)
        self.assertEqual(JV.pair_layout(1024, 259), "stack")  # a barrel: reference above, model below
        self.assertEqual(JV.pair_layout(930, 1024), "side")

    def test_the_key_follows_what_the_pairs_are_made_from(self):
        feats = [{"name": "glow strip", "picture": "refs/gun_side.png", "box": [200, 60, 300, 72]}]
        key = JV.features_key(feats, {"side": _trace()})
        self.assertEqual(key, JV.features_key([dict(feats[0])], {"side": _trace()}))
        self.assertNotEqual(key, JV.features_key([{**feats[0], "box": [200, 60, 300, 80]}], {"side": _trace()}))
        self.assertNotEqual(key, JV.features_key(feats, {"side": _trace(front="left")}))

    def test_the_build_says_where_to_look(self):
        line = JV.say({"folder": "build/judge/gun/builds/abc", "views": 6, "view_size": [1280, 960], "features": 3,
                       "feature_gaps": ["wolf: no picture", "rune: no box", "grip: not a traced view"]})
        self.assertIn("build/judge/gun/builds/abc/", line)
        self.assertIn("6 views at 1280 x 960", line)
        self.assertIn("3 hero feature pair(s)", line)
        self.assertIn("3 hero feature(s) have NO close-up", line)
        self.assertIn("wolf: no picture", line)
        self.assertIn("+1 more", line)
        self.assertEqual(JV.say(None), "")


if __name__ == "__main__":
    unittest.main()
