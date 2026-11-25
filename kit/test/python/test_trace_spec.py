"""kit trace --spec: a spec feature is checked against the silhouette the trace WRITES — its outline minus the openings
it keeps. A "gap" inside the outline (a thumbhole, a trigger guard, an ejection port) must read as a gap: checked
against the outline with its holes filled it could never pass (the Gjallarhorn's stock opening, 2026-10-06)."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "blender"))
import trace as T  # noqa: E402  (kit/blender/trace.py: system python, no bpy)

BODY = (40, 60, 360, 140)  # px: x0, y0, x1, y1 — the part, 320 px long: 1 mm a pixel with length_mm = 320
HOLE = (180, 85, 220, 115)  # an enclosed opening in it


def picture(path):
    im = Image.new("RGB", (400, 200), (247, 247, 247))
    d = ImageDraw.Draw(im)
    d.rectangle((BODY[0], BODY[1], BODY[2] - 1, BODY[3] - 1), fill=(40, 42, 48))
    d.rectangle((HOLE[0], HOLE[1], HOLE[2] - 1, HOLE[3] - 1), fill=(247, 247, 247))
    im.save(path)


def mm_box(x0, y0, x1, y1):
    """picture pixels -> spec mm [from the back, from the lowest point, to, to] (front = right: the back is the left)"""
    return [x0 - BODY[0], BODY[3] - y1, x1 - BODY[0], BODY[3] - y0]


class TestSpecSeesOpenings(unittest.TestCase):
    def test_a_gap_feature_inside_the_outline_reads_as_a_gap(self):
        spec = {"length_mm": 320, "features": [
            {"name": "opening", "box": mm_box(HOLE[0] + 4, HOLE[1] + 4, HOLE[2] - 4, HOLE[3] - 4), "expect": "gap"},
            {"name": "solid", "box": mm_box(60, 70, 140, 130), "expect": "solid"}]}
        old = T.REPO
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "part.png")
            picture(img)
            T.REPO = d
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    T.trace(img, None, "fixture_spec_hole", front="right", spec=spec, curves=False)
                with open(os.path.join(d, "assets", "models", "fixture_spec_hole.trace.json"), encoding="utf-8") as fh:
                    out = json.load(fh)
            finally:
                T.REPO = old
        # the picture frame: a pixel read off the reference lands on the design point it is (rbx_trace.px)
        import rbx_trace  # noqa: PLC0415

        t = rbx_trace.Trace(out)
        for (x, y), want in (((BODY[0], BODY[3]), (0.0, 0.0)), ((BODY[2], BODY[1]), (1.0, 0.25))):
            got = rbx_trace.px(t, x, y)
            self.assertAlmostEqual(got[0], want[0], places=2)
            self.assertAlmostEqual(got[1], want[1], places=2)
        self.assertEqual(len(out["holes"]), 1)  # the opening is traced ...
        rows = {r["name"]: r for r in out["spec"]}
        self.assertTrue(rows["opening"]["ok"], rows["opening"])  # ... and the spec sees it
        self.assertLess(rows["opening"]["coverage"], 0.05)
        self.assertTrue(rows["solid"]["ok"], rows["solid"])


class TestPartIsNotTheObject(unittest.TestCase):
    def _trace(self, parts):
        old = T.REPO
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "part.png")
            picture(img)
            T.REPO = d
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    code = T.trace(img, None, "fixture_part_whole", front="right", parts=parts, curves=False)
            finally:
                T.REPO = old
        return code, json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_a_part_that_is_the_whole_object_fails_the_trace(self):
        # (a single SAM click on a big structure returns the WHOLE object — the Gjallarhorn's stock and grip did)
        code, out = self._trace([("stock", (0, 0, 400, 200))])
        self.assertEqual(code, 1)
        self.assertIn("PART = WHOLE OBJECT", out["next_action"])
        self.assertIn("stock covers", out["next_action"])

    def test_a_real_part_passes(self):
        code, out = self._trace([("end", (300, 50, 400, 150))])  # the last fifth of the part
        self.assertEqual(code, 0, out)

    def test_a_click_on_the_backdrop_fails_the_trace(self):
        # (a click read off a resized copy lands on the backdrop: SAM returns the backdrop and the part is a speck)
        import numpy as np  # noqa: PLC0415

        class Stub:
            @staticmethod
            def mask(img, **_kw):
                return np.zeros((img.size[1], img.size[0]), bool), 0.99

        old_repo, old_vision = T.REPO, T._vision
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "part.png")
            picture(img)
            T.REPO, T._vision = d, (lambda: Stub)
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    code = T.trace(img, None, "fixture_click", front="right", part_points=[("end", [(20, 20)])],
                                   curves=False)
            finally:
                T.REPO, T._vision = old_repo, old_vision
        out = json.loads(buf.getvalue().strip().splitlines()[-1])
        self.assertEqual(code, 1)
        self.assertIn("PART CLICK OFF THE OBJECT", out["next_action"])
        self.assertIn("end click (20, 20)", out["next_action"])


class TestGameRoot(unittest.TestCase):
    def test_a_games_trace_goes_to_that_game(self):
        # KIT_GAME (set by --game) sends the trace to games/<Name>/assets/models: a SampleRegion piece's once landed in
        # the root's, where its build never looked; "none" is the project root
        if not os.path.isdir(os.path.join(T.REPO, "games")):
            self.skipTest("no games/ in this project")
        games = [g for g in os.listdir(os.path.join(T.REPO, "games"))
                 if os.path.isdir(os.path.join(T.REPO, "games", g)) and not g.startswith((".", "_"))]
        if not games:
            self.skipTest("no games/ in this project")
        old = os.environ.get("KIT_GAME")
        try:
            os.environ["KIT_GAME"] = games[0]
            self.assertEqual(T.game_root(), os.path.join(T.REPO, "games", games[0]))
            os.environ["KIT_GAME"] = "none"
            self.assertEqual(T.game_root(), T.REPO)
        finally:
            if old is None:
                os.environ.pop("KIT_GAME", None)
            else:
                os.environ["KIT_GAME"] = old


if __name__ == "__main__":
    unittest.main()
