"""The photogrammetry route, from photos to a built game model (kit/tools/photoscan.py, kit/selftest/scan/capture_urn.py;
his D-R02: "demonstrate a repeatable capture-to-engine result"; the 3D methods audit, stage L).

A synthetic capture (a speckled urn photographed from rings of cameras, so the TRUE shape is known) is scanned:
  good   32 photos -> every photo placed, the scan covering the urn in its photos, within a few percent of the
         true shape, built through the kit as a master and a game version that pass.
  thin   24 smaller photos -> every camera placed and still a doubled shell: the tool must REFUSE it.
About 20 minutes on the RTX 5070 (the dense stereo is most of it). Needs COLMAP (VETLOG 2026-11-16): without it
the test is skipped and says so."""

import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "kit", "tools"))
import cad_check  # noqa: E402
import photoscan  # noqa: E402

BLENDER = cad_check.blender()
OUT = os.path.join(ROOT, "build", "_test_photoscan")

# its own budget in the Python runner (kit/test/python/_proc.py file_timeout; the owner, 2026-11-22: "Per-file budget
# 3600 s"): ~27 minutes of GPU dense stereo on a quiet machine, past the runner's 1200 s default; its subprocesses
# already allow 3600 s each
KIT_PY_FILE_TIMEOUT = 3600


def blender(script, *args):
    return subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P", script, "--", *args],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=3600, env=dict(os.environ, KIT_GAME="none", KIT_BUILD=os.path.join(OUT, "kit")))


def scan(how):
    folder = os.path.join(OUT, how)
    r = blender(os.path.join(ROOT, "kit", "selftest", "scan", "capture_urn.py"), folder, how)
    assert r.returncode == 0, (r.stderr or r.stdout)[-600:]
    tool = subprocess.run([sys.executable, os.path.join(ROOT, "kit", "tools", "photoscan.py"),
                           os.path.join(folder, "images"), f"_scan_{how}", "--quality", "low", "--size", "0.9",
                           "--axis", "height", "--out", folder, "--work", os.path.join(folder, "work")],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    report = os.path.join(folder, f"_scan_{how}.scan.json")
    rep = json.load(open(report, encoding="utf-8")) if os.path.isfile(report) else None
    return folder, tool, rep


BUILD = '''
import os, sys
sys.path.insert(0, os.path.join(sys.argv[sys.argv.index("--") + 1], "kit", "blender"))
import rbx
a = rbx.Asset("_test_scan_urn", tex=512, size=(2.7, 3.2, 2.9), stage="master")
a.real_scale(280)
a.import_mesh("Body", sys.argv[sys.argv.index("--") + 2], height=0.9 * 1000 / 280, rough=0.7)
a.build()
'''


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER) and os.path.isfile(photoscan.COLMAP),
                     "Blender or COLMAP not found (COLMAP: VETLOG.md 2026-11-16)")
class Route(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good_dir, cls.good, cls.rep = scan("good")
        cls.thin_dir, cls.thin, cls.thin_rep = scan("thin")
        glb = os.path.join(cls.good_dir, "_scan_good.scan.glb")
        cls.cmp = blender(os.path.join(ROOT, "kit", "blender", "photoscan_compare.py"), glb,
                          os.path.join(cls.good_dir, "truth.obj"))
        build = os.path.join(OUT, "build_scan.py")
        with open(build, "w", encoding="utf-8") as fh:
            fh.write(BUILD)
        cls.master = blender(build, ROOT, glb, "--no-preview")
        cls.game = blender(build, ROOT, glb, "--no-preview", "--optimize")

    def test_the_good_capture_is_placed_and_covers_the_object_in_its_photos(self):
        self.assertEqual(self.good.returncode, 0, self.good.stdout[-600:])
        self.assertEqual((self.rep["placed"], self.rep["photos"]), (32, 32))
        self.assertLess(self.rep["error_px"], 1.0)
        self.assertGreaterEqual(self.rep["outline"]["median"], photoscan.OUTLINE_BAR)
        self.assertEqual(self.rep["weak"], [])
        self.assertTrue(self.rep["coloured"])
        self.assertGreaterEqual(self.rep["outline"]["height"]["median"], photoscan.HEIGHT_BAR)   # (it stands tall)

    def test_its_scan_lies_on_the_true_shape(self):
        line = next(x for x in self.cmp.stdout.splitlines() if x.startswith("COMPARE "))
        c = json.loads(line[8:])
        self.assertLess(c["p90"], 0.025, c)                 # (90% of the surface within 2.5% of the height)
        for got, true in zip(sorted(c["scan_size"]), sorted(c["truth_size"])):
            self.assertLess(abs(got / true - 1), 0.06, c)    # (the scale from the height alone: a few percent)

    def test_a_thin_capture_is_refused_for_the_base_it_never_saw(self):
        # (before the cut-outs went into the fusion it built a doubled shell and the outline refused it; with them
        #  its shape is right through its own cameras - but its base was never photographed, the height it is
        #  scaled by is short, and it came out 14% too wide: refused for that, by name)
        self.assertEqual(self.thin.returncode, 2, self.thin.stdout[-600:])
        self.assertIn("FAILED its capture checks", self.thin.stdout)
        self.assertIn("the base was not photographed", self.thin.stdout)
        # (by either measure: Blender renders the capture a little differently each time and its base fill went
        #  0.135..0.34 over five renders - the 0.135 one stood 0.923 tall in its photos and came out 10% too wide)
        tall = self.thin_rep["outline"]["height"]["median"]
        self.assertTrue(self.thin_rep["base_filled"] > photoscan.BASE_BAR or tall < photoscan.HEIGHT_BAR,
                        (self.thin_rep["base_filled"], tall))
        self.assertEqual(self.thin_rep["placed"], self.thin_rep["photos"])   # (the cameras alone said nothing)

    def test_the_ground_it_stood_on_is_not_in_the_scan(self):
        # (the good capture stands on a textured wooden floor 2.6 m across: only the cut-out masks keep it out)
        line = next(x for x in self.cmp.stdout.splitlines() if x.startswith("COMPARE "))
        c = json.loads(line[8:])
        self.assertLess(max(c["scan_size"][:2]), 1.0, c)

    def test_the_scan_builds_as_a_master_and_a_game_version(self):
        for r in (self.master, self.game):
            line = next((x for x in reversed(r.stdout.splitlines()) if x.startswith("{") and '"status"' in x), None)
            self.assertIsNotNone(line, (r.stderr or r.stdout)[-600:])
            self.assertEqual(json.loads(line)["status"], "pass", line[:300])
        colour = os.path.join(OUT, "kit", "models", "textures", "_test_scan_urn_game_color.png")
        from PIL import Image  # noqa: PLC0415

        import numpy as np  # noqa: PLC0415

        px = np.asarray(Image.open(colour).convert("L"), float)
        self.assertGreater(float(px.mean()), 40)            # (the photographed colour reached the game map)


@unittest.skipUnless(BLENDER and os.path.isfile(BLENDER) and os.path.isfile(photoscan.COLMAP),
                     "Blender or COLMAP not found (COLMAP: VETLOG.md 2026-11-16)")
class SameCameras(unittest.TestCase):
    """the same photos give the same cameras, bit for bit (2026-11-18, card vcq6: the threaded extractor numbered
    the photos as its threads finished and RANSAC drew at random - the same thin capture was refused for its base,
    refused for its outline, or accepted, from run to run)"""

    def test_two_camera_solves_of_one_capture_are_identical(self):
        import hashlib  # noqa: PLC0415
        import tempfile  # noqa: PLC0415

        import shutil  # noqa: PLC0415

        folder = os.path.join(OUT, "same")
        shutil.rmtree(folder, ignore_errors=True)        # (a capture's photos only: another capture left larger ones)
        # (the thin capture: its solve is the fragile one - the threaded mapper gave it other cameras 1 run in 5)
        r = blender(os.path.join(ROOT, "kit", "selftest", "scan", "capture_urn.py"), folder, "thin")
        self.assertEqual(r.returncode, 0, (r.stderr or r.stdout)[-600:])
        sums = []
        with tempfile.TemporaryDirectory() as d:
            for k in range(2):
                photos = os.path.join(d, f"photos{k}")
                photoscan.prepare(os.path.join(folder, "images"), photos)
                sparse = os.path.join(d, f"sparse{k}")
                os.makedirs(sparse)
                for args in photoscan.sparse_steps(os.path.join(d, f"db{k}.db"), photos, sparse):
                    photoscan.run(args, os.path.join(d, "colmap.log"))
                model, run_sums = os.path.join(sparse, "0"), []
                for f in ("cameras.bin", "images.bin", "points3D.bin"):
                    with open(os.path.join(model, f), "rb") as fh:
                        run_sums.append(hashlib.md5(fh.read()).hexdigest())
                sums.append(run_sums)
        self.assertEqual(sums[0], sums[1], "the same photos gave different cameras")


if __name__ == "__main__":
    unittest.main()
