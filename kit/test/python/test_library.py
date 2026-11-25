"""The reference-model library must never let an unusable licence through, never extract outside its folder or
anything that is not a model / texture, and never accept a file that is not really glTF or that reaches outside its
folder — the owner asked: "are any of the models ever unsafe to download?" """

import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "refs"))
import library  # noqa: E402


def _glb(doc):
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    return struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js)) + struct.pack("<II", len(js), 0x4E4F534A) + js


class TestLicence(unittest.TestCase):
    def test_usable(self):
        for label, want in (("CC Attribution", "by"), ("CC Attribution-ShareAlike", "by-sa"),
                            ("CC0 Public Domain", "cc0")):
            self.assertEqual(library.licence_ok(label), want, label)

    def test_never(self):
        for label in ("CC Attribution-NonCommercial", "CC Attribution-NonDerivs", "CC Attribution-NonCommercial-ShareAlike",
                      "Standard", "Editorial", "", None):
            self.assertIsNone(library.licence_ok(label), label)


class TestToken(unittest.TestCase):
    def test_pasted_brackets_quotes_and_spaces_are_stripped(self):
        old = os.environ.get("SKETCHFAB_API_TOKEN")
        try:
            for raw in ("<0123abcd>", " '0123abcd' ", '"0123abcd"\r\n', "0123abcd"):
                os.environ["SKETCHFAB_API_TOKEN"] = raw
                self.assertEqual(library._token(), "0123abcd", repr(raw))
        finally:
            if old is None:
                os.environ.pop("SKETCHFAB_API_TOKEN", None)
            else:
                os.environ["SKETCHFAB_API_TOKEN"] = old


class TestFiles(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_real_glb_passes(self):
        p = os.path.join(self.d, "m.glb")
        with open(p, "wb") as fh:
            fh.write(_glb({"asset": {"version": "2.0"}, "buffers": [{"byteLength": 4}]}))
        self.assertTrue(library.check_glb(p)[0])

    def test_fake_glb_refused(self):
        p = os.path.join(self.d, "m.glb")
        with open(p, "wb") as fh:
            fh.write(b"MZ\x90\x00" + b"\x00" * 64)  # an executable's header, renamed
        self.assertFalse(library.check_glb(p)[0])

    def test_outside_uris_refused(self):
        for uri in ("../../secret.bin", "C:/Windows/x.png", "https://example.com/x.png", "/etc/passwd"):
            self.assertFalse(library.check_gltf_doc({"images": [{"uri": uri}]})[0], uri)
        self.assertTrue(library.check_gltf_doc({"images": [{"uri": "textures/base.png"}]})[0])

    def test_zip_slip_and_executables_skipped(self):
        zp = os.path.join(self.d, "a.zip")
        with zipfile.ZipFile(zp, "w") as z:
            z.writestr("scene.gltf", "{}")
            z.writestr("textures/base.png", b"png")
            z.writestr("../evil.gltf", "{}")
            z.writestr("run_me.exe", b"MZ")
            z.writestr("addon.py", "print(1)")
            z.writestr("scene.blend", b"BLENDER")
        dest = os.path.join(self.d, "out")
        kept, skipped = library.safe_unzip(zp, dest)
        self.assertEqual(sorted(kept), ["scene.gltf", "textures/base.png"])
        self.assertEqual(len(skipped), 4)
        self.assertFalse(os.path.exists(os.path.join(self.d, "evil.gltf")))

    def test_hosts(self):
        self.assertTrue(library._host_ok("https://media.sketchfab.com/x.glb"))
        self.assertTrue(library._host_ok("https://3d-api.si.edu/x.glb"))
        self.assertTrue(library._host_ok("https://dl.polyhaven.org/file/ph-assets/Models/gltf/2k/x/x_2k.gltf"))
        self.assertFalse(library._host_ok("https://api.polyhaven.com.evil.example/x.glb"))
        self.assertFalse(library._host_ok("http://media.sketchfab.com/x.glb"))
        self.assertFalse(library._host_ok("https://evil.example.com/sketchfab.com.glb"))


if __name__ == "__main__":
    unittest.main()
