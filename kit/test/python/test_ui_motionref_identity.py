"""kit ui motion-ref --identity (LIMITATIONS_FIXES_V4 UI-X 6.4 step 4: motion measured from the source game's footage,
not typed): the identity's typed motion is compared with the measurement by the compiler's own rule (kit/lib/ui.luau:
within 25%, at least 0.05 s / 0.02 s; an overshoot measured stays one), and --write records it as motion.measured."""
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_ui_motionref_id", os.path.join(HERE, "..", "..", "ui", "motionref.py"))
motionref = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(motionref)

MEASURED = {"clip": "menu.mp4", "duration": 0.42, "ease": "cubic", "stagger": 0.08}


class TestIdentityGaps(unittest.TestCase):
    def test_typed_taste_is_refused_the_measured_numbers_pass(self):
        typed = {"enter": {"type": "slam", "duration": 0.18, "ease": "back"}, "stagger": 0.03}
        gaps = motionref.identity_gaps(typed, MEASURED)
        self.assertEqual(len(gaps), 3)
        self.assertTrue(any("duration 0.18" in g for g in gaps))
        self.assertTrue(any("stagger 0.03" in g for g in gaps))
        self.assertTrue(any("overshoots" in g for g in gaps))
        built = {"enter": {"type": "fade", "duration": 0.4, "ease": "quad"}, "stagger": 0.08}
        self.assertEqual(motionref.identity_gaps(built, MEASURED), [])

    def test_the_tolerances(self):
        # 25% of 0.42 = 0.105 s; the stagger's floor 0.02 s (25% of 0.08 is under it)
        self.assertEqual(motionref.identity_gaps({"enter": {"duration": 0.52}}, MEASURED), [])
        self.assertEqual(len(motionref.identity_gaps({"enter": {"duration": 0.53}}, MEASURED)), 1)
        self.assertEqual(motionref.identity_gaps({"stagger": 0.1}, MEASURED), [])
        self.assertEqual(len(motionref.identity_gaps({"stagger": 0.11}, MEASURED)), 1)
        # a measured overshoot needs back / elastic
        back = dict(MEASURED, ease="back")
        self.assertEqual(len(motionref.identity_gaps({"enter": {"ease": "quad"}}, back)), 1)
        self.assertEqual(motionref.identity_gaps({"enter": {"ease": "elastic"}}, back), [])


class TestMotionRefIdentity(unittest.TestCase):
    def test_measure_compare_and_record(self):
        import cv2
        fps, n = 30, 45
        with tempfile.TemporaryDirectory() as d:
            clip = os.path.join(d, "menu.mp4")
            vw = cv2.VideoWriter(clip, cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 240))
            for i in range(n):
                t = i / fps
                im = np.full((240, 320, 3), 30, np.uint8)
                for t0, y in ((0.2, 40), (0.4, 140)):
                    p = min(1.0, max(0.0, (t - t0) / 0.4))
                    x = int(-120 + (1 - (1 - p) ** 3) * 160)
                    if x > -120:
                        im[y:y + 60, max(0, x):max(0, x + 120)] = (230, 230, 230)
                vw.write(im)
            vw.release()
            ident = os.path.join(d, "x.json")
            with open(ident, "w", encoding="utf-8") as fh:
                json.dump({"name": "x", "motion": {"enter": {"type": "slam", "duration": 1.5, "ease": "back"}, "stagger": 0.5}}, fh)
            args = [clip, "--box", "0,30,320,80", "--box", "0,130,320,80", "--out", d, "--identity", ident]
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = motionref.main(args)
            r = json.loads(out.getvalue().strip().splitlines()[-1])
            self.assertEqual((code, r["status"]), (0, "pass"))
            self.assertEqual(len(r["gaps"]), 3)                                  # (1.5 s, 0.5 s apart, an overshoot)
            self.assertIn("--write", r["next_action"])
            with open(ident, encoding="utf-8") as fh:
                self.assertNotIn("measured", json.load(fh)["motion"])            # (nothing written without --write)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                motionref.main(args + ["--write"])
            with open(ident, encoding="utf-8") as fh:
                rec = json.load(fh)["motion"]["measured"]
            self.assertEqual(rec["clip"], "menu.mp4")
            self.assertAlmostEqual(rec["stagger"], 0.2, delta=0.07)
            self.assertAlmostEqual(rec["duration"], 0.4, delta=0.1)


if __name__ == "__main__":
    unittest.main()
