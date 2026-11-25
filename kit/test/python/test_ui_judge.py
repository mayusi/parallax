"""kit/ui/judge.py record: a verdict is validated (integer parts 0..20, the score is the parts' sum, located gaps),
tied to the build it saw (a changed model is refused), and several judges of the same build keep every verdict
with the screen's score as their median."""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "ui"))

# loaded under its own name: kit/blender/judge.py is imported as `judge` by the 3D tests in the same process
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("kit_ui_judge", os.path.join(HERE, "..", "..", "ui", "judge.py"))
judge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(judge)


class Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def verdict(score_parts, gaps=None, judge_name="j"):
    parts = dict(zip(judge.PARTS, score_parts))
    return {"judge": judge_name, "screens": {"S": {**parts, "tells": [], "gaps": gaps if gaps is not None else [{"where": "S.X", "what": "y"}],
                                                   "score": sum(score_parts)}}, "overall": 70, "verdict": "ok"}


class TestRecord(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.models = os.path.join(self.tmp, "models")
        self.out = os.path.join(self.tmp, "out")
        self.packet = os.path.join(self.tmp, "packet")
        os.makedirs(self.models)
        os.makedirs(self.out)
        os.makedirs(self.packet)
        self.model = os.path.join(self.models, "S.model.json")
        with open(self.model, "w", encoding="utf-8") as fh:
            json.dump({"ClassName": "ScreenGui"}, fh)
        with open(os.path.join(self.packet, "packet.json"), "w", encoding="utf-8") as fh:
            json.dump({"screens": [{"name": "S", "model_sha256": judge.sha256_file(self.model), "quality": "hero"}]}, fh)

    def record(self, v, name="v.json"):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(v, fh)
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = judge.cmd_record(Args(packet=self.packet, verdict=path, models=self.models, out=self.out))
        return code, json.loads(buf.getvalue().strip().splitlines()[-1])

    def stored(self):
        with open(os.path.join(self.out, "S.judge.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_a_good_verdict_is_recorded_with_its_bar_and_sha(self):
        code, r = self.record(verdict([16, 15, 14, 13, 17]))
        self.assertEqual(code, 0, r)
        s = self.stored()
        self.assertEqual(s["score"], 75)
        self.assertEqual(s["bar"], 75)
        self.assertEqual(s["judges"], 1)
        self.assertEqual(s["model_sha256"], judge.sha256_file(self.model))

    def test_bad_parts_bad_gaps_bools_and_a_nameless_judge_are_refused_and_not_written(self):
        v = verdict([16, 15, 14, 13, 17])
        v["screens"]["S"]["craft"] = 25
        code, r = self.record(v)
        self.assertEqual(code, 1)
        self.assertTrue(any("craft" in p for p in r["problems"]))
        self.assertFalse(os.path.exists(os.path.join(self.out, "S.judge.json")), "a bad verdict must not be written")
        v2 = verdict([10, 10, 10, 10, 10], gaps=["not located"])
        code2, r2 = self.record(v2, "v2.json")
        self.assertEqual(code2, 1)
        self.assertTrue(any("gaps" in p for p in r2["problems"]))
        v3 = verdict([10, 10, 10, 10, 10])
        v3["screens"]["S"]["feel"] = True  # a bool is not a score
        code3, _ = self.record(v3, "v3.json")
        self.assertEqual(code3, 1)
        v4 = verdict([10, 10, 10, 10, 10], judge_name="")
        code4, r4 = self.record(v4, "v4.json")
        self.assertEqual(code4, 1)
        self.assertTrue(any("judge" in p for p in r4["problems"]))
        self.assertFalse(os.path.exists(os.path.join(self.out, "S.judge.json")))

    def test_a_claimed_score_that_is_not_the_sum_is_refused(self):
        v = verdict([10, 10, 10, 10, 10])
        v["screens"]["S"]["score"] = 99
        code, r = self.record(v)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(os.path.join(self.out, "S.judge.json")))

    def test_several_judges_keep_each_judges_latest_verdict_and_take_the_median(self):
        self.record(verdict([10, 10, 10, 10, 10], judge_name="a"), "a.json")
        self.record(verdict([16, 16, 16, 16, 16], judge_name="b"), "b.json")
        s = self.stored()
        self.assertEqual(s["judges"], 2)
        self.assertEqual(s["score"], 65)  # (50 + 80) / 2
        self.record(verdict([14, 14, 14, 14, 14], judge_name="c"), "c.json")
        s = self.stored()
        self.assertEqual(s["judges"], 3)
        self.assertEqual(s["score"], 70)  # the middle one
        self.record(verdict([14, 14, 14, 14, 14], judge_name="c"), "c2.json")  # the same judge again: replaced, not added
        s = self.stored()
        self.assertEqual(s["judges"], 3)

    def test_a_look_is_recorded_for_this_build_and_a_short_note_is_refused(self):
        from PIL import Image
        import io as _io
        import contextlib
        ui = os.path.join(self.tmp, "ui")
        os.makedirs(ui)
        Image.new("RGB", (8, 8)).save(os.path.join(ui, "S.png"))
        specs = os.path.join(self.tmp, "specs")
        os.makedirs(specs)

        def look(note):
            buf = _io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = judge.cmd_look(Args(name="S", note=note, by="me@test", ui=ui, specs=specs, models=self.models))
            return code, json.loads(buf.getvalue().strip().splitlines()[-1])

        code, r = look("too short")
        self.assertEqual(code, 1)
        self.assertIn("too short", r["summary"])
        self.assertIsNone(judge.read_look(specs, "S", judge.sha256_file(self.model)))
        code, r = look("the coins pill is tiny on the phone and the quest bar collides with the boosts; I will scale both")
        self.assertEqual(code, 0, r)
        rec = judge.read_look(specs, "S", judge.sha256_file(self.model))
        self.assertEqual(rec["by"], "me@test")
        # the model changes: the look is stale
        with open(self.model, "w", encoding="utf-8") as fh:
            json.dump({"ClassName": "ScreenGui", "Children": []}, fh)
        self.assertIsNone(judge.read_look(specs, "S", judge.sha256_file(self.model)))

    def test_a_changed_model_with_the_same_sheet_still_records(self):
        # kit upload rewrites the model (asset ids) without changing a pixel: the verdict is tied to the sheet
        from PIL import Image
        sheet = os.path.join(self.tmp, "S.png")
        Image.new("RGB", (8, 8)).save(sheet)
        with open(os.path.join(self.packet, "packet.json"), "w", encoding="utf-8") as fh:
            json.dump({"screens": [{"name": "S", "model_sha256": "stale", "sheet_sha256": judge.sha256_file(sheet),
                                    "sheet": sheet, "quality": "hero"}]}, fh)
        code, r = self.record(verdict([16, 15, 14, 13, 17]))
        self.assertEqual(code, 0, r)
        self.assertEqual(self.stored()["model_sha256"], judge.sha256_file(self.model))

    def test_a_changed_model_refuses_the_verdict(self):
        with open(self.model, "w", encoding="utf-8") as fh:
            json.dump({"ClassName": "ScreenGui", "changed": True}, fh)
        code, r = self.record(verdict([16, 15, 14, 13, 17]))
        self.assertEqual(code, 1)
        self.assertTrue(any("changed since" in p for p in r["problems"]))
        self.assertFalse(os.path.exists(os.path.join(self.out, "S.judge.json")))


if __name__ == "__main__":
    unittest.main()
