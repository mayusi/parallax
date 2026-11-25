"""Taking the photographed light out of a scan, end to end (kit/tools/delight.py on kit/tools/photoscan.py's scan of
kit/selftest/scan/capture_urn.py's lamp-lit capture; his D-R03: "show held-out improvement without baking lighting
errors into geometry or albedo").

THE BENCHMARK is relighting: the same places photographed with the lamp on the OTHER side (`lit2`). For each
colouring the new light is fitted on some of those photos and the rest - never fitted - are scored, over the
pixels the scan covers. The colour with its light out must match them clearly better than the colour as
photographed; and a deliberately WRONG colour (the lamp's shading doubled, not taken out) must do worse - the
benchmark must tell the two apart. (Under the SAME light the photographed colour wins by definition: the review,
2026-11-16, found the first benchmark scored that and called a fitted light's overfitting a gain.) About 16 minutes
on the RTX 5070. Needs COLMAP and the Mitsuba environment (VETLOG): without them the test is skipped and says so."""

import json
import os
import subprocess
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402
import delight  # noqa: E402
import photoscan  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join(ROOT, "build", "_test_delight")
RUN = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600, cwd=ROOT)


def capture(how):
    r = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                        os.path.join(ROOT, "kit", "selftest", "scan", "capture_urn.py"), "--", os.path.join(OUT, how),
                        how], **RUN)
    assert r.returncode == 0, (r.stderr or r.stdout)[-600:]


def wrong_colour_scores():
    """the benchmark run again on a colour with the lamp's shading DOUBLED -> its report"""
    from PIL import Image  # noqa: PLC0415

    w = os.path.join(OUT, "work", "delight")
    job = json.load(open(os.path.join(w, "job.json"), encoding="utf-8"))
    facing = os.path.join(w, "scan_cameras_frame_facing.png")
    photo = delight.srgb_to_linear(np.asarray(Image.open(job["texture"]).convert("RGB"), float) / 255)
    fac = np.asarray(Image.open(facing).convert("RGB"), float) / 255
    cov = fac.sum(-1) > 0.02
    sh, _ = delight.shading_split(job["texture"], facing)
    b = delight.basis(fac * 2 - 1)
    e = np.stack([b @ np.array(sh[c * 9:(c + 1) * 9]) for c in range(3)], -1)
    bad = np.where(cov[..., None], photo * np.maximum(e, 0.05), photo)
    bad = np.clip(bad * (photo[cov].mean() / bad[cov].mean()), 0.002, 1)
    srgb = np.where(bad <= 0.0031308, bad * 12.92, 1.055 * np.power(bad, 1 / 2.4) - 0.055)
    path = os.path.join(w, "doubled.png")
    Image.fromarray((srgb * 255 + 0.5).astype(np.uint8)).save(path)
    job["delit"], job["out"] = path, os.path.join(w, "doubled")
    os.makedirs(job["out"], exist_ok=True)
    spec = os.path.join(w, "job_doubled.json")
    json.dump(job, open(spec, "w", encoding="utf-8"))
    r = subprocess.run([delight.MITSUBA, "-I", os.path.join(ROOT, "kit", "tools", "delight_mitsuba.py"), spec], **RUN)
    line = next(x for x in reversed(r.stdout.splitlines()) if x.startswith("DELIGHT "))
    return json.loads(line[8:])


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER) and os.path.isfile(photoscan.COLMAP)
                     and os.path.isfile(delight.MITSUBA), "Blender, COLMAP or the Mitsuba environment not found")
class Route(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        capture("lit")
        capture("lit2")
        cls.scan = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "tools", "photoscan.py"),
                                   os.path.join(OUT, "lit", "images"), "_lit", "--quality", "low", "--size", "0.9",
                                   "--out", OUT, "--work", os.path.join(OUT, "work")], **RUN)
        cls.tool = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "tools", "delight.py"), "_lit", "--work",
                                   os.path.join(OUT, "work"), "--out", OUT, "--relight",
                                   os.path.join(OUT, "lit2", "images")], **RUN)
        path = os.path.join(OUT, "_lit.delight.json")
        cls.rep = json.load(open(path, encoding="utf-8")) if os.path.isfile(path) else None
        cls.wrong = wrong_colour_scores() if cls.rep else None

    def test_the_scan_is_good_and_its_cameras_line_up(self):
        self.assertEqual(self.scan.returncode, 0, self.scan.stdout[-600:])
        self.assertEqual(self.tool.returncode, 0, self.tool.stdout[-600:])
        self.assertGreater(self.rep["camera_check"]["median"], 0.95)
        self.assertGreater(self.rep["camera_check"]["colour_median"], 0.8)

    def test_under_another_light_the_colour_without_its_light_does_clearly_better(self):
        rel = self.rep["fits"]["relight"]
        self.assertGreater(rel["held_out_views"], 4)
        self.assertTrue(self.rep["proven"])
        self.assertGreater(self.rep["relight_gain"], 0.15, rel)

    def test_the_benchmark_rejects_a_wrong_colour(self):
        rel, bad = self.rep["fits"]["relight"], self.wrong["fits"]["relight"]
        self.assertGreater(bad["delit"], bad["photographed"], bad)     # (the lamp doubled: worse than as photographed)
        self.assertGreater(bad["delit"], rel["delit"] * 1.5, (bad, rel))

    def test_under_the_same_light_the_photographed_colour_is_said_to_win(self):
        same = self.rep["fits"]["same_light"]
        self.assertLess(same["photographed_even"], same["delit_relit"])     # (said, never hidden)

    def test_the_light_is_out_of_the_colour_and_it_is_delivered(self):
        self.assertGreater(self.rep["shading_tie"]["photographed"], 0.5)
        self.assertLess(abs(self.rep["shading_tie"]["delit"]), 0.15)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, self.rep["glb"])))


if __name__ == "__main__":
    unittest.main()
