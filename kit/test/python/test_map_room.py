"""A map too small for its islands is said as that (card a2ym: "nothing but the uv gate says a map is too small for
its island count"): the dense optimize fixture's game version - 337 islands on a 64-texel map - fails `uv` with the
cause and the map size that would hold them."""

import json
import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
BLENDER = os.environ.get("BLENDER", os.environ.get("KIT_BLENDER") or os.environ.get("BLENDER") or r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")
FIX = os.path.join(ROOT, "kit", "selftest", "blender", "build_optimize_dense.py")


@unittest.skipUnless(os.path.isfile(BLENDER), "Blender 5.2 is not installed")
class Room(unittest.TestCase):
    def test_the_cause_and_the_size(self):
        run = lambda *a: subprocess.run([BLENDER, "-b", "--factory-startup", "-P", FIX, "--", "--no-preview", *a],  # noqa: E731
                                        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                        timeout=1800)
        if not os.path.isfile(os.path.join(ROOT, "build", "models", "_selftest_optimize_dense.manifest.json")):
            run()
        out = run("--optimize")
        k = out.stdout.find('{"schema"')
        st = json.JSONDecoder().raw_decode(out.stdout[k:])[0]
        uv = [c for g in st["groups"].values() for c in g["checks"] if c["name"] == "uv"][0]
        self.assertFalse(uv["ok"])
        self.assertIn("too SMALL for its 337 islands", uv["fix"])
        self.assertIn("a map of 256 or more", uv["fix"])


if __name__ == "__main__":
    unittest.main()
