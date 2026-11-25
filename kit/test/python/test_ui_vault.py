"""kit ui vault: everything the UI pipeline makes is saved, packaged by part — and the check fails when it is not"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
VAULT = os.path.join(HERE, "..", "..", "ui", "vault.py")


def run(root, *args):
    r = subprocess.run([sys.executable, VAULT, *args, "--ui", os.path.join(root, "assets", "ui"), "--models", os.path.join(root, "src", "ui"),
                        "--build", os.path.join(root, "build", "ui"), "--out", os.path.join(root, "library", "ui")],
                       capture_output=True, text=True, cwd=root)
    return json.loads(r.stdout.strip().splitlines()[-1])


class TestVault(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.tmp.name
        ui = os.path.join(r, "assets", "ui")
        os.makedirs(os.path.join(ui, "identities"))
        os.makedirs(os.path.join(ui, "art", "x"))
        json.dump({"name": "x", "tokens": {}}, open(os.path.join(ui, "identities", "x.json"), "w"))
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(os.path.join(ui, "art", "x", "badge.png"))
        open(os.path.join(ui, "art", "x", "PROVENANCE.md"), "w").write("| badge | drawn by hand for the test |\n")
        self.spec = {"name": "S", "identity": "x", "kind": "hud", "root": {"type": "panel", "name": "Hud", "children": [
            {"type": "image", "name": "Badge", "image": "art:x/badge"},
            {"type": "label", "name": "Hp", "text": "82"}]}}
        self.spec_path = os.path.join(ui, "S.json")
        json.dump(self.spec, open(self.spec_path, "w"))
        self.root = r

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_screen_is_packaged_by_part_with_its_source(self):
        out = run(self.root, "save")
        self.assertEqual(out["status"], "pass")
        pkg = os.path.join(self.root, "library", "ui", "x", "screens", "S")
        man = json.load(open(os.path.join(pkg, "manifest.json")))
        part = man["parts"][0]
        self.assertEqual(part["part"], "Hud.Badge")
        self.assertEqual(part["file"], "parts/Badge.png")
        self.assertTrue(os.path.isfile(os.path.join(pkg, "parts", "Badge.png")))
        self.assertIn("drawn by hand", part["source"])
        self.assertEqual(man["texts"][0]["text"], "82")
        self.assertTrue(os.path.isfile(os.path.join(self.root, "library", "ui", "x", "pieces", "badge.png")))

    def test_check_fails_on_anything_made_but_not_saved(self):
        self.assertEqual(run(self.root, "check")["status"], "fail")  # nothing saved yet
        run(self.root, "save")
        self.assertEqual(run(self.root, "check")["status"], "pass")
        self.spec["root"]["children"][1]["text"] = "54"
        json.dump(self.spec, open(self.spec_path, "w"))
        self.assertEqual(run(self.root, "check")["status"], "fail")  # a stale package
        run(self.root, "save")
        Image.new("RGBA", (8, 8), (0, 0, 255, 255)).save(os.path.join(self.root, "assets", "ui", "art", "x", "new_piece.png"))
        self.assertEqual(run(self.root, "check")["status"], "fail")  # a piece not saved

    def test_a_second_save_writes_nothing(self):
        run(self.root, "save")
        self.assertEqual(run(self.root, "save")["written"], 0)

    def test_an_owner_rated_version_is_kept_when_the_screen_changes(self):
        json.dump({"screen": "S", "owner": {"score": 90, "words": "great"}}, open(os.path.join(self.root, "assets", "ui", "S.judge.json"), "w"))
        run(self.root, "save")
        self.spec["root"]["children"][1]["text"] = "54"
        json.dump(self.spec, open(self.spec_path, "w"))
        run(self.root, "save")
        versions = os.path.join(self.root, "library", "ui", "x", "screens", "S", "versions")
        self.assertTrue(os.path.isdir(versions))
        kept = os.listdir(versions)[0]
        self.assertIn("owner90", kept)
        self.assertEqual(json.load(open(os.path.join(versions, kept, "screen.json")))["root"]["children"][1]["text"], "82")

    def test_get_brings_a_package_back_as_a_new_screen(self):
        run(self.root, "save")
        out = run(self.root, "get", "S", "--as", "T", "--into", self.root)
        self.assertEqual(out["status"], "pass")
        t = json.load(open(os.path.join(self.root, "assets", "ui", "T.json")))
        self.assertEqual(t["name"], "T")


    def test_a_provenance_row_may_name_a_flipbook_range(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("kit_ui_vault", VAULT)
        vault = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vault)
        self.assertEqual(vault.expand_range("soul_0..soul_4"), ["soul_0", "soul_1", "soul_2", "soul_3", "soul_4"])
        self.assertEqual(vault.expand_range("figurine_cards_0..2"), ["figurine_cards_0", "figurine_cards_1", "figurine_cards_2"])
        self.assertEqual(vault.expand_range("mask_full"), ["mask_full"])
        self.assertEqual(vault.expand_range("frame_01..frame_03"), ["frame_01", "frame_02", "frame_03"])   # (zeros kept)
        self.assertEqual(vault.expand_range("a_3..1"), ["a_3..1"])   # (a backwards range is just a name)

if __name__ == "__main__":
    unittest.main()
