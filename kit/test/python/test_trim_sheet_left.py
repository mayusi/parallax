"""What the trim-sheet review left (card fczy): a new sheet's noise drawn on a LOOP its width long repeats along the
sheet exactly (rbx_wear.wrap_x: no cross-fade at its ends); `kit trim-stale` names a model laid on an older build of
its sheet; the uploader leaves a sheet's own un-faded bake files at home (kit/lib/uploadjobs.luau)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "blender"))
import rbx_wear as W  # noqa: E402

LUNE = shutil.which("lune")


class Loop(unittest.TestCase):
    def test_the_field_repeats_with_the_sheet(self):
        L = 2240.0   # (an 8-stud sheet at 280 mm a stud)
        xs = np.linspace(-L / 2, L / 2, 401)
        p = np.stack([xs, np.zeros_like(xs), np.full_like(xs, 150.0)], axis=1)
        w = W.wrap_x(p, L)
        self.assertTrue(np.allclose(w[0], w[-1], atol=1e-3))          # (its two ends: the same place)
        step = np.linalg.norm(np.diff(w, axis=0), axis=1)
        self.assertTrue(np.allclose(step, L / 400, rtol=1e-3))       # (an arc as long as the x it stood for)
        inside = np.ones((1, 401), bool)
        f = W.fbm3(w.reshape(1, -1, 3), inside, 5, 4, 300.0)
        self.assertAlmostEqual(float(f[0, 0]), float(f[0, -1]), places=5)


@unittest.skipUnless(LUNE, "lune is not installed")
class Stale(unittest.TestCase):
    def run_in(self, files):
        d = tempfile.mkdtemp()
        for name, body in files.items():
            with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                json.dump(body, fh)
        out = subprocess.run([LUNE, "run", "kit", "trim-stale", "--dir", d, "--game", "none"], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        return out.returncode, out.stdout

    def test_a_user_of_an_older_build_is_named(self):
        sheet = {"build_id": "bbbb", "groups": {}}
        code, out = self.run_in({"sheet.manifest.json": sheet,
                                 "wall.manifest.json": {"groups": {"main": {"trim": {"sheet": "sheet",
                                                                                     "sheet_build": "aaaa"}}}},
                                 "cap.manifest.json": {"groups": {"main": {"trim": {"sheet": "sheet",
                                                                                    "sheet_build": "bbbb"}}}}})
        self.assertNotEqual(code, 0, out)
        self.assertIn("wall (main): laid on sheet's build aaaa, the sheet is bbbb now", out)
        self.assertNotIn("cap (main)", out)

    def test_all_current_passes(self):
        code, out = self.run_in({"sheet.manifest.json": {"build_id": "bbbb", "groups": {}},
                                 "cap.manifest.json": {"groups": {"main": {"trim": {"sheet": "sheet",
                                                                                    "sheet_build": "bbbb"}}}}})
        self.assertEqual(code, 0, out)
        self.assertIn("every one of 1 group(s)", out)


BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class TheSheet(unittest.TestCase):
    def test_a_new_sheet_repeats_as_baked_and_its_empty_rows_are_not_black(self):
        env = dict(os.environ, KIT_BAKE_CACHE="0")
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                              os.path.join(ROOT, "kit", "selftest", "blender", "build_trim_sheet_loop.py"), "--",
                              "--no-preview"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=1800, env=env)
        self.assertEqual(out.returncode, 0, out.stdout[-1500:] + out.stderr[-1500:])
        dec = json.JSONDecoder()
        st = dec.raw_decode(out.stdout[out.stdout.find('{"schema"'):])[0]
        ts = st["facts"]["trim_sheet"]
        self.assertTrue(ts["noise_on_a_loop"])
        self.assertFalse(ts["faded"], ts["tile"])                       # (it repeats as baked: no cross-fade)
        self.assertFalse([c for c in st["design"] if c["name"] == "trim_fade" and not c["ok"]])
        i = out.stdout.rfind("LOOP ")
        rows = dec.raw_decode(out.stdout[i + 5:])[0]
        self.assertGreater(rows["off_band_darkest"], 0.5 * rows["on_band_darkest"])   # (no black rows)

    def test_a_geo_round_needs_no_sheet(self):
        d = tempfile.mkdtemp()
        env = dict(os.environ, KIT_BUILD=os.path.relpath(d, ROOT).replace("\\", "/"), KIT_GAME="none")
        out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                              os.path.join(ROOT, "kit", "selftest", "blender", "build_trim_wall.py"), "--", "--geo"],
                             cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=1200, env=env)
        self.assertNotIn("no built trim sheet", out.stdout + out.stderr)
        k = out.stdout.find('{"schema"')
        self.assertGreaterEqual(k, 0, out.stdout[-1500:] + out.stderr[-1500:])   # (the build itself ran to its verdict;
        st = json.JSONDecoder().raw_decode(out.stdout[k:])[0]                       #  the fixture's own reading after it
        self.assertIn("GEO check", st["summary"])                                   #  wants maps a --geo round has not)
        self.assertNotIn("trim", " ".join(c["name"] for c in st["design"] if not c["ok"] and c["severity"] == "error"))


class Upload(unittest.TestCase):
    def test_the_rule_is_in_the_uploader(self):
        with open(os.path.join(ROOT, "kit", "lib", "uploadjobs.luau"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('_trim.png")', src)


if __name__ == "__main__":
    unittest.main()
