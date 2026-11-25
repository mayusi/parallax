"""An island laid over itself (card keak: the karambit's screws, 1.05% of their map painted twice, with no face
flipped - a long band unrolled into a curve that coils back across itself): the high-and-low route's unwrap by part
checks each island on its own grid and re-projects one that lies over itself (rbx_uvparts._folded). On a ribbon swept
two turns round a helix (kit/selftest/blender/build_uv_coil.py): with the check its map paints nothing twice; with
it off (KIT_UV_FOLD=0) the same build paints texels twice and uv_overlap fails it."""

import json
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def build(fold=True):
    env = dict(os.environ, KIT_BAKE_CACHE="0", KIT_UV_FOLD="1" if fold else "0")
    out = subprocess.run([BLENDER, "-b", "--factory-startup", "--python-exit-code", "2", "-P",
                          os.path.join(ROOT, "kit", "selftest", "blender", "build_uv_coil.py")],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200,
                         env=env)
    k = out.stdout.find('{"schema"')
    return out.returncode, (json.JSONDecoder().raw_decode(out.stdout[k:])[0] if k >= 0 else None), \
        out.stdout[-1500:] + out.stderr[-1500:]


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class Coil(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.on, cls.off = build(True), build(False)

    def test_the_coil_is_caught_and_the_map_paints_nothing_twice(self):
        code, st, log = self.on
        self.assertEqual(code, 0, log)
        self.assertGreater(st["facts"]["uv_parts"]["main"].get("folded", 0), 0)
        self.assertEqual(st["facts"]["uv_check"]["main"]["overlap_texels"], 0)
        self.assertEqual(st["status"], "pass", st["summary"])

    def test_without_the_check_the_same_build_paints_twice(self):
        code, st, log = self.off
        self.assertEqual(code, 0, log)
        self.assertNotIn("folded", st["facts"]["uv_parts"]["main"])
        self.assertGreater(st["facts"]["uv_check"]["main"]["overlap_texels"], 0)
        self.assertTrue(any(c["name"] == "uv_overlap" and not c["ok"]
                            for g in st["groups"].values() for c in g["checks"]))


if __name__ == "__main__":
    unittest.main()
