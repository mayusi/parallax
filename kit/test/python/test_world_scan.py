"""test_world_scan.py - A REAL THING, PHOTOGRAPHED, SET INTO A WORLD (kit/world/scan_world.py; the owner's method list:
"Photo-based environment reconstruction"). Held here: what the command refuses (no real size, a size out of range, no
photos, a bad name) before anything runs; that the photogrammetry tool is found in this checkout or main's; that the
mesh comes into the world's registry in STUDS (0.28 m a stud), its pieces too, stamped with what it was made from; that
a failed scan is a failure even when an earlier scan of that name left its files.
Not claimed here: that the scanned mesh looks like the thing. That is looked at (the audit page says what was seen)."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("kit_world_scan", os.path.join(HERE, "..", "..", "world", "scan_world.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)


def said(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = S.main(argv)
    return code, json.loads(buf.getvalue().strip().splitlines()[-1])


class Refusals(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.photos = os.path.join(self.tmp, "photos")
        os.makedirs(self.photos)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def refused(self, argv, word):
        with mock.patch.object(S.subprocess, "run", side_effect=AssertionError("nothing may run")):
            code, out = said(argv)
        self.assertEqual(code, 1)
        self.assertEqual(out["status"], "fail")
        self.assertIn(word, out["summary"])

    def test_no_size_is_refused(self):
        self.refused(["Rock", "--from", self.photos], "--size")

    def test_sizes_out_of_range_are_refused(self):
        for bad in ("0", "0.005", "501", "-2"):
            self.refused(["Rock", "--from", self.photos, "--size", bad], "--size")

    def test_no_photos_is_refused(self):
        self.refused(["Rock", "--size", "1"], "--from")
        self.refused(["Rock", "--from", os.path.join(self.tmp, "none"), "--size", "1"], "--from")

    def test_a_bad_name_is_refused(self):
        for bad in ("Ro ck", "../Rock", "Rock-1", "Réal"):
            self.refused([bad, "--from", self.photos, "--size", "1"], "name")


class Tool(unittest.TestCase):
    def test_a_given_tool_must_exist(self):
        self.assertIsNone(S.find_tool(os.path.join(tempfile.gettempdir(), "no_such_photoscan.py")))
        self.assertEqual(S.find_tool(__file__), __file__)

    def test_mains_checkout_is_found_by_gits_list(self):
        tmp = tempfile.mkdtemp()
        try:
            main = os.path.join(tmp, "main")
            os.makedirs(os.path.join(main, "kit", "tools"))
            open(os.path.join(main, "kit", "tools", "photoscan.py"), "w").close()
            listing = (f"worktree {os.path.join(tmp, 'other')}\nHEAD 1\nbranch refs/heads/feature\n\n"
                       f"worktree {main}\nHEAD 2\nbranch refs/heads/main\n")
            with mock.patch.object(S, "REPO", os.path.join(tmp, "here")), \
                    mock.patch.object(S.subprocess, "run",
                                      return_value=subprocess.CompletedProcess([], 0, listing, "")):
                self.assertEqual(os.path.normpath(S.find_tool()),
                                 os.path.normpath(os.path.join(main, "kit", "tools", "photoscan.py")))
            # a main checkout without the tool: none (another branch's checkout is not taken)
            os.remove(os.path.join(main, "kit", "tools", "photoscan.py"))
            os.makedirs(os.path.join(tmp, "other", "kit", "tools"))
            open(os.path.join(tmp, "other", "kit", "tools", "photoscan.py"), "w").close()
            with mock.patch.object(S, "REPO", os.path.join(tmp, "here")), \
                    mock.patch.object(S.subprocess, "run",
                                      return_value=subprocess.CompletedProcess([], 0, listing, "")):
                self.assertIsNone(S.find_tool())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_with_main_checked_out_elsewhere_the_main_working_tree_is_used(self):
        tmp = tempfile.mkdtemp()
        try:
            main = os.path.join(tmp, "main")
            os.makedirs(os.path.join(main, "kit", "tools"))
            open(os.path.join(main, "kit", "tools", "photoscan.py"), "w").close()
            listing = (f"worktree {main}\nHEAD 2\ndetached\n\n"
                       f"worktree {os.path.join(tmp, 'other')}\nHEAD 1\nbranch refs/heads/feature\n")
            with mock.patch.object(S, "REPO", os.path.join(tmp, "here")), \
                    mock.patch.object(S.subprocess, "run",
                                      return_value=subprocess.CompletedProcess([], 0, listing, "")):
                self.assertEqual(os.path.normpath(S.find_tool()),
                                 os.path.normpath(os.path.join(main, "kit", "tools", "photoscan.py")))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class IntoTheWorld(unittest.TestCase):
    """the whole command with the two programs it runs stood in for: the tool writes a GLB + its report; the importer
    (as kit/world/import_blender.py does) scales the mesh by the item's "scale" before it writes, and stamps the asset
    and its pieces with the item's "scan"."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.photos = os.path.join(self.tmp, "photos")
        os.makedirs(self.photos)
        self.tool = os.path.join(self.tmp, "photoscan.py")
        open(self.tool, "w").close()
        self.meshes = os.path.join(self.tmp, "games", "G", "build", "worldmeshes")
        self.scan_ok = True
        self.items = None

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_run(self, cmd, **_kw):
        if cmd[0] == "git":
            return subprocess.CompletedProcess(cmd, 0, "abc1234\n" if "rev-parse" in cmd else "", "")
        if cmd[1] == self.tool:  # the photogrammetry route
            if not self.scan_ok:
                return subprocess.CompletedProcess(cmd, 1, "summary: too few photos joined\n", "")
            out, name = cmd[cmd.index("--out") + 1], cmd[3]
            open(os.path.join(out, f"{name}.scan.glb"), "wb").write(b"glTF")
            json.dump({"size_m": [0.795, 0.9, 0.75], "verdict": "ok"},
                      open(os.path.join(out, f"{name}.scan.json"), "w"))
            return subprocess.CompletedProcess(cmd, 0, "summary: scanned\n", "")
        items, meshes = cmd[-2], cmd[-1]  # the importer
        it = json.load(open(items))[0]
        self.items = it
        k, name = it.get("scale", 1.0), it["name"]
        rp = os.path.join(meshes, "meshes.json")
        reg = json.load(open(rp)) if os.path.isfile(rp) else {}
        size = [round(v * k, 4) for v in (0.795, 0.9, 0.75)]
        lo = [round(v * k, 4) for v in (-0.4, 0.0, -0.375)]
        reg[name] = {"kind": "import", "parts": [f"{name}__scan"], "tris": 19000, "size": size, "min": lo}
        reg[f"{name}__scan"] = {"kind": "piece", "tris": 19000, "size": size, "min": lo, "of": name}
        if it.get("scan"):
            reg[name]["scan"] = it["scan"]
            reg[f"{name}__scan"]["scan"] = it["scan"]
        json.dump(reg, open(rp, "w"))
        return subprocess.CompletedProcess(cmd, 0, "ok\n", "")

    def run_scan(self, run=None, exe=__file__):
        with mock.patch.object(S, "REPO", self.tmp), mock.patch.object(S, "blender", return_value=exe), \
                mock.patch.object(S.subprocess, "run", side_effect=run or self.fake_run):
            return said(["Urn", "--from", self.photos, "--size", "0.9", "--axis", "height", "--tool", self.tool,
                         "--meshes", self.meshes])

    def reg(self):
        return json.load(open(os.path.join(self.meshes, "meshes.json")))

    def put(self, reg):
        os.makedirs(self.meshes, exist_ok=True)
        json.dump(reg, open(os.path.join(self.meshes, "meshes.json"), "w"))

    def test_the_mesh_comes_in_studs_into_the_folder_given_and_says_what_made_it(self):
        self.put({"Old": {"kind": "import", "size": [1, 1, 1], "min": [0, 0, 0], "parts": [], "tris": 1}})
        code, out = self.run_scan()
        self.assertEqual(code, 0, out)
        self.assertAlmostEqual(self.items["scale"], 1 / S.STUD_M)  # the importer scales BEFORE it writes anything
        reg = self.reg()
        for key in ("Urn", "Urn__scan"):
            self.assertAlmostEqual(reg[key]["size"][1], 0.9 / S.STUD_M, places=3)
            self.assertAlmostEqual(reg[key]["min"][0], -0.4 / S.STUD_M, places=3)
            self.assertEqual(reg[key]["scan"]["metres"], 0.9)  # the piece is held to its size too
        self.assertEqual(reg["Old"]["size"], [1, 1, 1])  # another mesh untouched
        self.assertEqual(reg["Urn"]["scan"]["axis"], "height")
        self.assertEqual(reg["Urn"]["scan"]["commit"], "abc1234")
        self.assertTrue(reg["Urn"]["scan"]["report"].endswith("Urn.scan.json"))
        self.assertIn("3.2 studs tall", out["summary"])
        # into the folder it was given (the active game's), not the repository's own build
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, "build", "worldmeshes", "meshes.json")))

    def test_a_mesh_that_was_not_scanned_is_never_replaced(self):
        self.put({"Urn": {"kind": "import", "size": [1, 1, 1], "min": [0, 0, 0], "parts": [], "tris": 1}})
        code, out = self.run_scan()
        self.assertEqual(code, 1)
        self.assertIn("was not scanned", out["summary"])
        self.assertIsNone(self.items)
        self.assertEqual(self.reg()["Urn"]["size"], [1, 1, 1])
        # a name that is already a scan: scanned again
        self.put({"Urn": {"kind": "import", "size": [1, 1, 1], "min": [0, 0, 0], "parts": [], "tris": 1,
                          "scan": {"metres": 2}}})
        self.assertEqual(self.run_scan()[0], 0)
        self.assertEqual(self.reg()["Urn"]["scan"]["metres"], 0.9)

    def test_no_blender_is_a_failure_said_not_a_crash(self):
        code, out = self.run_scan(exe=None)
        self.assertEqual(code, 1)
        self.assertIn("no Blender", out["summary"])
        self.assertIsNone(self.items)

    def test_a_failed_scan_fails_even_over_an_earlier_one(self):
        self.assertEqual(self.run_scan()[0], 0)
        self.scan_ok = False
        code, out = self.run_scan()
        self.assertEqual(code, 1)
        self.assertIn("too few photos joined", out["summary"])
        self.assertFalse(os.path.isfile(os.path.join(self.tmp, "build", "worldscans", "Urn.scan.glb")))

    def test_a_scan_the_tool_rejected_fails_though_it_wrote_files(self):
        def run(cmd, **kw):
            r = self.fake_run(cmd, **kw)
            if cmd[0] != "git" and cmd[1] == self.tool:  # it wrote its GLB and report, then its own check said no
                return subprocess.CompletedProcess(cmd, 1, "summary: the outline misses the photos\n", "")
            return r
        code, out = self.run_scan(run)
        self.assertEqual(code, 1)
        self.assertIn("the outline misses the photos", out["summary"])
        self.assertIsNone(self.items)

    def test_an_import_that_did_not_register_or_stamp_fails(self):
        def unregistered(cmd, **kw):
            r = self.fake_run(cmd, **kw)
            if cmd[0] != "git" and cmd[1] != self.tool:
                os.remove(os.path.join(cmd[-1], "meshes.json"))
            return r
        code, out = self.run_scan(unregistered)
        self.assertEqual(code, 1)
        self.assertIn("did not come into the world's meshes", out["summary"])

        def unstamped(cmd, **kw):
            if cmd[0] != "git" and cmd[1] != self.tool:
                it = json.load(open(cmd[-2]))
                it[0].pop("scan")
                json.dump(it, open(cmd[-2], "w"))
            return self.fake_run(cmd, **kw)
        code, out = self.run_scan(unstamped)
        self.assertEqual(code, 1)
        self.assertIn("did not come into the world's meshes", out["summary"])


if __name__ == "__main__":
    unittest.main()
