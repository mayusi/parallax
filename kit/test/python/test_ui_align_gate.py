"""kit/ui/align.py check — the ALIGNMENT gate (LIMITATIONS_FIXES_V4 UI-X 6.4 step 4, the 1-3 px anti-slop lint) as
`kit verify` runs it: every compiled screen laid out at desktop like the engine (preview.layout_screen, nothing drawn)
and its near-misses counted - the SAME boxes the preview draws, a warning with the count by default, a failure with
--fail (kit selftest's bad fixture)."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
UI = os.path.join(ROOT, "kit", "ui")
FIX = os.path.join(ROOT, "kit", "selftest", "ui", "align")
if UI not in sys.path:
    sys.path.insert(0, UI)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(UI, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


preview = load("preview")
align = load("align")


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = align.main(argv)
    return code, json.loads(out.getvalue().strip().splitlines()[-1])


class TestAlignGate(unittest.TestCase):
    def test_the_layout_is_the_one_the_preview_draws(self):
        # desktop_boxes lays the screen out without drawing it: the boxes must be the drawn frame's, node for node
        with open(os.path.join(FIX, "bad", "AlignBad.model.json"), encoding="utf-8") as fh:
            model = json.load(fh)
        preview.draw_viewport(model, 1920, 1080, "desktop")
        self.assertEqual(preview.desktop_boxes(model), dict(preview.ALL_BOXES))
        self.assertEqual(preview.desktop_boxes(model)["Hud.Options"], (142.0, 210.0, 200.0, 60.0))

    def test_the_bad_fixture_is_caught_and_the_control_is_clean(self):
        bad = align.check_models(os.path.join(FIX, "bad"))
        kinds = sorted(k for k, _, _ in bad["AlignBad"])
        self.assertEqual(kinds, ["near_align", "near_align", "uneven_gap"])        # (2 px drift, gaps 10 and 13)
        self.assertEqual(align.check_models(os.path.join(FIX, "good")), {"AlignGood": []})

    def test_a_warning_by_default_a_failure_with_fail(self):
        code, r = run(["check", "--models", os.path.join(FIX, "bad")])
        self.assertEqual((code, r["status"]), (0, "pass"))
        self.assertIn("1 of 1 screen(s) have 1-3 px near-misses", r["summary"])
        self.assertIn("WARNING", r["summary"])
        self.assertTrue(r["next_action"].startswith("improve AlignBad"))           # (kit verify surfaces "improve")
        self.assertEqual(r["warnings"], 3)
        code, r = run(["check", "--models", os.path.join(FIX, "bad"), "--fail"])
        self.assertEqual((code, r["status"]), (1, "fail"))
        code, r = run(["check", "--models", os.path.join(FIX, "good"), "--fail"])
        self.assertEqual((code, r["status"]), (0, "pass"))

    def test_a_named_screen_that_is_not_compiled_fails(self):
        code, r = run(["check", "Nope", "--models", os.path.join(FIX, "good")])
        self.assertEqual((code, r["status"]), (1, "fail"))

    def test_every_compiled_screen_of_the_project_is_measured(self):
        # the gate covers EVERY compiled screen (ScreenGui, BillboardGui, SurfaceGui) - none skipped silently
        models = os.path.join(ROOT, "src", "ui")
        if not os.path.isdir(models):
            self.skipTest("no compiled screens in this checkout")
        want = set()
        for f in os.listdir(models):
            if f.endswith(".model.json"):
                with open(os.path.join(models, f), encoding="utf-8") as fh:
                    if json.load(fh).get("ClassName") in ("ScreenGui", "BillboardGui", "SurfaceGui"):
                        want.add(f[: -len(".model.json")])
        self.assertEqual(set(align.check_models(models)), want)


if __name__ == "__main__":
    unittest.main()
