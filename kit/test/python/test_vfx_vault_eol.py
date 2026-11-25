"""kit/vfx/vault.py's sha(): a text file hashes the same with CRLF or LF line endings (git's Windows checkout vs a
tool's LF write: kit prove's LF sandbox found all 7 VFX meshes "stale" for their line endings alone); a mesh (.obj /
.mtl) is text; a binary file's bytes are never touched."""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "vfx"))

import vault  # noqa: E402


class Eol(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as fh:
            fh.write(data)
        return p

    def test_a_mesh_hashes_the_same_with_either_line_ending(self):
        body = "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n"
        for ext in (".obj", ".mtl", ".json"):
            lf = self.write("lf" + ext, body.encode())
            crlf = self.write("crlf" + ext, body.replace("\n", "\r\n").encode())
            self.assertEqual(vault.sha(lf), vault.sha(crlf), ext)

    def test_a_changed_mesh_is_still_a_change(self):
        a = self.write("a.obj", b"v 0 0 0\r\nf 1 1 1\r\n")
        b = self.write("b.obj", b"v 0 0 1\nf 1 1 1\n")
        self.assertNotEqual(vault.sha(a), vault.sha(b))

    def test_a_binary_file_is_hashed_as_it_is(self):
        a = self.write("a.png", b"\x89PNG\r\n\x1a\n")
        b = self.write("b.png", b"\x89PNG\n\x1a\n")
        self.assertNotEqual(vault.sha(a), vault.sha(b))


if __name__ == "__main__":
    unittest.main()
