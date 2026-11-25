"""kit/vision/vlm.py installed(): the local VLM counts as installed only when every file the manifest lists for it is
in the cache at its recorded size - a download cut short is not installed, so the design review / refs read / explore
routes hand the AI client a packet instead of crashing on half a model."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vision"))
import vlm  # noqa: E402

FILES = {"config.json": b"{}", "tokenizer.json": b'{"t": 1}', "model-00001.safetensors": b"x" * 1000}


class Installed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.models = os.path.join(self.tmp, "models")
        self.folder = os.path.join(self.models, vlm.NAME)
        os.makedirs(self.folder)
        self.kit = os.path.join(self.tmp, "kitvision")
        os.makedirs(self.kit)
        with open(os.path.join(self.kit, "models.json"), "w", encoding="utf-8") as fh:
            json.dump({"models": {vlm.NAME: {"files": [{"path": p, "size": len(b)} for p, b in FILES.items()]}}}, fh)
        for p, b in FILES.items():
            with open(os.path.join(self.folder, p), "wb") as fh:
                fh.write(b)
        self.patches = [mock.patch.dict(os.environ, {"KIT_MODELS": self.models}), mock.patch.object(vlm, "HERE", self.kit)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_file_at_its_size_is_installed(self):
        self.assertTrue(vlm.installed())

    def test_a_download_cut_short_is_not(self):
        with open(os.path.join(self.folder, "model-00001.safetensors"), "wb") as fh:
            fh.write(b"x" * 10)
        self.assertFalse(vlm.installed())

    def test_a_missing_file_is_not(self):
        os.remove(os.path.join(self.folder, "model-00001.safetensors"))
        self.assertFalse(vlm.installed())

    def test_no_folder_is_not(self):
        shutil.rmtree(self.folder)
        self.assertFalse(vlm.installed())


if __name__ == "__main__":
    unittest.main()
