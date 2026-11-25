"""A twisted sweep is cut open on its own (LIMITATIONS_FIXES_V4 Phase 1, 3D-X: rbx.Asset.sweep, SWEEP_SEAM): a section
turned more than half a turn about its path is a helicoid, and the automatic unwrap laid a flat bar twisted two turns
out stretched (8.8% of it over 2x longer than wide). On kit/selftest/blender/build_sweep_twist.py: with the cut, both
twisted parts are cut along their seam line into strips that lie flat (seam_placed holds, uv_stretch passes); with it
off (KIT_SWEEP_CUT=0) the same build fails uv_stretch on the bar."""

import json
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
FIXTURE = os.path.join(ROOT, "kit", "selftest", "blender", "build_sweep_twist.py")


def build(cut):
    env = dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join("build", "_test_sweep_cut" + ("" if cut else "_off")),
               KIT_SWEEP_CUT="1" if cut else "0")
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", FIXTURE, "--",
                        "--no-preview"], cwd=ROOT, capture_output=True, text=True, timeout=1200, env=env,
                       encoding="utf-8", errors="replace")
    line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith('{"schema"')), None)
    assert line, (r.stderr or r.stdout)[-800:]
    return json.loads(line)


def check(report, name):
    """the named check across the build's groups -> {"ok": every group's holds, "rows": each group's}"""
    rows = [dict(c, group=g) for g, row in (report.get("groups") or {}).items() for c in row.get("checks", [])
            if c.get("name") == name]
    assert rows, f"no {name} check in any group"
    return {"ok": all(c["ok"] for c in rows), "rows": rows}


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender not found")
class TwistedSweepCut(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.on, cls.off = build(True), build(False)

    def test_both_twisted_parts_are_cut_open_and_said(self):
        rows = {r["part"]: r for r in self.on["facts"]["sweeps"]}
        self.assertIn("twisted 720 degrees", rows["Bar"].get("cut_open", ""))
        self.assertIn("twisted 1080 degrees", rows["Rope"].get("cut_open", ""))
        placed = {**self.on["facts"]["seams_placed"]["bar"], **self.on["facts"]["seams_placed"]["rope"]}
        self.assertEqual(placed["Bar"]["pieces"], 6)      # its four long faces and its two ends
        self.assertEqual(placed["Rope"]["pieces"], 3)     # one strip round it and its two ends
        for part in ("Bar", "Rope"):
            self.assertEqual(placed[part]["rings"], 0, part)
            self.assertLessEqual(placed[part]["stretched"], 0.01, part)

    def test_the_map_lies_flat_with_the_cut_and_fails_without_it(self):
        self.assertTrue(check(self.on, "uv_stretch")["ok"], check(self.on, "uv_stretch"))
        self.assertTrue(check(self.on, "seam_placed")["ok"], check(self.on, "seam_placed"))
        self.assertTrue(check(self.on, "uv_overlap")["ok"])
        self.assertEqual(self.on["status"], "pass", self.on["summary"])
        self.assertFalse(check(self.off, "uv_stretch")["ok"], "without the cut the twisted bar must stretch")
        self.assertNotIn("cut_open", {k for r in self.off["facts"]["sweeps"] for k in r})


if __name__ == "__main__":
    unittest.main()
