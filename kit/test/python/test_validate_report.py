"""kit/blender/rbx_validate.verdict: the score is a REPORT (mission 01-3d 5.10/5.11) — listed last among the
warnings and never the next step while a real check is open (its advice once read "4+ kinds of small detail: screws,
latches, LEDs" and builders greebled the starter props to an owner 0.1/10). bpy / bmesh stubbed: verdict() is pure."""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
for mod in ("bpy", "bmesh"):
    sys.modules.setdefault(mod, types.ModuleType(mod))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_validate as RV  # noqa: E402


def check(name, ok=False, severity="warn", fix=None):
    return {"name": name, "ok": ok, "severity": severity, "value": "v", "limit": "l", "fix": fix or f"fix {name}"}


RESULTS = {"main": {"checks": [], "tris": 100, "size_studs": [1, 1, 1]}}


class ReportLast(unittest.TestCase):
    def test_a_real_warning_is_the_next_step_before_the_score(self):
        status, summary, nxt = RV.verdict(RESULTS, [check("quality"), check("roughness_variation")])
        self.assertEqual(status, "pass")
        self.assertIn("roughness_variation", nxt)
        self.assertNotIn("quality", nxt)
        self.assertLess(summary.index("roughness_variation"), summary.index("quality"))   # (listed last)

    def test_the_small_part_count_is_a_report_too(self):
        status, summary, nxt = RV.verdict(RESULTS, [check("detail"), check("palette")])
        self.assertIn("palette", nxt)

    def test_the_score_alone_is_still_said(self):
        status, summary, nxt = RV.verdict(RESULTS, [check("quality")])
        self.assertIn("quality", nxt)

    def test_an_error_still_fails_first(self):
        status, summary, nxt = RV.verdict(RESULTS, [check("quality"), check("manifold", severity="error")])
        self.assertEqual(status, "fail")
        self.assertIn("fix manifold", nxt)


if __name__ == "__main__":
    unittest.main()
