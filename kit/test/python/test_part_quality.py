"""kit trace judges every traced part's mask (trace.py part_quality): a box-prompted mask that fills its box, two masks
that are one area, a mask that dropped a thin piece of its part, a plain --part box, an unsure SAM 3 match — the
measured failures of a hero asset's side trace (5 of 13 masks unusable). Also --part-text (SAM 3 by words: parsing,
the missing-environment message, a run with SAM 3 stubbed) and kit refs views carrying the judgement to ref links.
Synthetic masks and pictures; no model runs."""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "blender"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "refs"))
import trace as T  # noqa: E402  (kit/blender/trace.py: system python, no bpy)
import views as V  # noqa: E402


def rect(shape, x0, y0, x1, y1):
    m = np.zeros(shape, bool)
    m[y0:y1, x0:x1] = True
    return m


class TestRules(unittest.TestCase):
    def test_a_mask_filling_its_box_took_the_region(self):
        shape = (200, 300)
        box = (50, 40, 150, 120)
        region = rect(shape, 50, 40, 150, 120)  # SAM gave back the box itself
        part = rect(shape, 70, 50, 120, 115)  # a part inside a looser box
        q = T.part_quality({"grip": {"kind": "box", "box": box}, "guard": {"kind": "box", "box": box}},
                           {"grip": region, "guard": part}, raw={"grip": region, "guard": part})
        self.assertFalse(q["grip"]["ok"])
        self.assertTrue(any(w.startswith("fills its box (100%)") for w in q["grip"]["why"]), q["grip"])
        self.assertFalse(any("fills its box" in w for w in q["guard"]["why"]))

    def test_two_masks_that_are_one_area(self):
        shape = (200, 300)
        grip = rect(shape, 100, 80, 160, 190)
        guard = rect(shape, 110, 80, 170, 150)  # most of it inside the grip's mask
        apart = rect(shape, 200, 20, 260, 60)
        q = T.part_quality({n: {"kind": "points"} for n in ("grip", "guard", "stock")},
                           {"grip": grip, "guard": guard, "stock": apart})
        self.assertFalse(q["grip"]["ok"])
        self.assertFalse(q["guard"]["ok"])
        self.assertIn("'grip' and 'guard'", q["guard"]["why"][0])
        self.assertTrue(q["stock"]["ok"])
        same = T.part_quality({n: {"kind": "points"} for n in ("a", "b")}, {"a": grip, "b": grip.copy()})
        self.assertIn("are one area (100% the same)", same["a"]["why"][0])

    def test_a_small_detail_inside_a_big_part_is_not_one_area(self):
        shape = (200, 300)
        receiver = rect(shape, 20, 20, 280, 120)
        port = rect(shape, 150, 40, 190, 60)  # 3% of the receiver, wholly on it
        q = T.part_quality({n: {"kind": "points"} for n in ("receiver", "port")}, {"receiver": receiver, "port": port})
        self.assertTrue(q["receiver"]["ok"] and q["port"]["ok"], q)

    def test_a_crown_that_dropped_its_claw(self):
        shape = (200, 300)
        crown = rect(shape, 100, 60, 180, 130)  # the crown body
        whole = crown.copy()
        whole[90:96, 180:240] = True  # a thin claw running right, out of the mask, inside the box
        box = (95, 55, 245, 135)
        q = T.part_quality({"crown": {"kind": "box", "box": box}}, {"crown": crown}, raw={"crown": crown}, whole=whole)
        self.assertFalse(q["crown"]["ok"])
        self.assertTrue(any("possible dropped piece" in w and "right edge" in w for w in q["crown"]["why"]), q)
        # the same mask WITH its claw is clean
        q2 = T.part_quality({"crown": {"kind": "box", "box": box}}, {"crown": whole}, raw={"crown": whole}, whole=whole)
        self.assertTrue(q2["crown"]["ok"], q2)

    def test_a_grip_box_that_also_caught_the_receiver_is_not_a_dropped_piece(self):
        shape = (300, 300)
        receiver = rect(shape, 20, 40, 280, 120)
        grip = rect(shape, 120, 120, 170, 260)
        whole = receiver | grip
        box = (115, 60, 175, 265)  # tight across, loose upward: a band of receiver above the grip
        q = T.part_quality({"grip": {"kind": "box", "box": box}}, {"grip": grip}, raw={"grip": grip}, whole=whole)
        self.assertFalse(any("dropped" in w for w in q["grip"]["why"]), q)

    def test_a_plain_box_is_said_to_be_one(self):
        shape = (100, 100)
        q = T.part_quality({"bipod": {"kind": "plain", "box": [10, 10, 60, 60]}},
                           {"bipod": rect(shape, 10, 10, 60, 60)})
        self.assertFalse(q["bipod"]["ok"])
        self.assertIn("a plain box (--part), not a mask", q["bipod"]["why"][0])
        self.assertEqual(q["bipod"]["prompt"], "plain")

    def test_an_unsure_text_match_and_an_empty_part(self):
        shape = (100, 100)
        q = T.part_quality({"claw": {"kind": "text"}, "gone": {"kind": "points"}},
                           {"claw": rect(shape, 10, 10, 30, 30), "gone": None}, scores={"claw": 0.41})
        self.assertIn("SAM 3 was unsure (score 0.41)", q["claw"]["why"][0])
        self.assertTrue(q["gone"]["why"][0].startswith("empty"))


class TestPartText(unittest.TestCase):
    def test_the_words_and_which_match(self):
        self.assertEqual(T.parse_text("grip=pistol grip"), ("grip", "pistol grip", 1))
        self.assertEqual(T.parse_text('claw="claw"#2'), ("claw", "claw", 2))
        self.assertEqual(T.parse_text("tag=part #4 label"), ("tag", "part #4 label", 1))  # (a # inside the words)

    def test_no_trellis_environment_is_said_with_what_to_do(self):
        old = T._trellis_python
        T._trellis_python = lambda: None
        try:
            with self.assertRaises(T.PromptError) as e:
                T.text_masks("x.png", ["grip"])
        finally:
            T._trellis_python = old
        self.assertIn("TRELLIS.2 environment", e.exception.args[0])
        self.assertIn("--part-point", e.exception.args[1])


BODY = (40, 60, 360, 140)  # the object in a 400 x 200 picture
GRIP = (200, 140, 240, 190)


def picture(path):
    im = Image.new("RGB", (400, 200), (247, 247, 247))
    d = ImageDraw.Draw(im)
    d.rectangle((BODY[0], BODY[1], BODY[2] - 1, BODY[3] - 1), fill=(40, 42, 48))
    d.rectangle((GRIP[0], GRIP[1], GRIP[2] - 1, GRIP[3] - 1), fill=(40, 42, 48))
    im.save(path)


class TestTraceWritesTheJudgement(unittest.TestCase):
    """trace() end to end with SAM stubbed: a box prompt whose mask fills its box, a text prompt"""

    def _trace(self, **kw):
        old = (T.REPO, T._vision, T.text_masks)
        shape = (200, 400)

        class FakeSam:
            @staticmethod
            def mask(_img, points=None, box=None):  # SAM 2.1: the box's whole region (the failure)
                return rect(shape, *[int(v) for v in box]), 0.97

        def fake_text(_image, phrases):
            grip = rect(shape, *GRIP)
            return {p: [(0.93, grip), (0.4, rect(shape, 300, 60, 340, 140))] for p in phrases}

        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "pic.png")
            picture(img)
            T.REPO, T._vision, T.text_masks = d, (lambda: FakeSam), fake_text
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    code = T.trace(img, None, "fixture_quality", curves=False, **kw)
                path = os.path.join(d, "assets", "models", "fixture_quality.trace.json")
                out = json.load(open(path, encoding="utf-8")) if os.path.isfile(path) else None
            finally:
                T.REPO, T._vision, T.text_masks = old
        return code, json.loads(buf.getvalue().strip().splitlines()[-1]), out

    def test_a_box_filling_mask_is_written_and_named(self):
        code, said, t = self._trace(part_boxes=[("stock", [60, 70, 150, 130])])
        self.assertFalse(t["part_quality"]["stock"]["ok"])
        self.assertEqual(t["part_quality"]["stock"]["prompt"], "box")
        self.assertIn("DOUBTFUL part mask(s): stock (fills its box", said["summary"])
        self.assertIn("--part-text", said["next_action"])
        self.assertEqual(code, 0)  # a doubt is said, never a failed trace

    def test_a_text_prompt_takes_the_best_match_or_the_kth(self):
        _code, _said, t = self._trace(part_texts=[("grip", "pistol grip", 1)])
        self.assertTrue(t["part_quality"]["grip"]["ok"], t["part_quality"])
        self.assertEqual(t["part_text"]["grip"], {"phrase": "pistol grip", "pick": 1, "matches": 2, "score": 0.93})
        u0 = min(u for u, _h in t["parts"]["grip"])
        self.assertAlmostEqual(u0, (GRIP[0] - BODY[0]) / (BODY[2] - BODY[0]), places=1)
        _code, _said, t2 = self._trace(part_texts=[("tail", "pistol grip", 2)])
        self.assertIn("SAM 3 was unsure", t2["part_quality"]["tail"]["why"][0])
        code, said, _t = self._trace(part_texts=[("grip", "pistol grip", 3)])
        self.assertEqual(code, 1)
        self.assertIn("found 2 match(es)", said["summary"])


class TestViewsCarryTheJudgement(unittest.TestCase):
    def test_a_doubtful_part_reaches_the_views_file(self):
        side = {"front": "right", "height_ratio": 0.2, "outline": [[0, 0], [1, 0], [1, 0.2], [0, 0.2]],
                "parts": {"grip": [[0.4, 0], [0.5, 0], [0.5, 0.1], [0.4, 0.1]]},
                "part_quality": {"grip": {"ok": False, "prompt": "box", "why": ["fills its box (97%): ..."]}}}
        m = V.measure_views({"side": side}, 1000, stations=4)
        q = m["parts"]["grip"]["side"]["quality"]
        self.assertFalse(q["ok"])
        self.assertTrue(q["why"][0].startswith("fills its box"))


if __name__ == "__main__":
    unittest.main()
